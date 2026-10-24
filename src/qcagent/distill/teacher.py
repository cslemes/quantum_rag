"""One teacher call, as a state machine with terminal states.

The teacher is a hosted, routed model called with the distillation guarantee
(`provider.enforce_distillable_text`). The rules this module makes mechanical:

* A refusal is a refusal. Whatever the API says no to is recorded with its raw
  status and body and the statement moves on. There is no second attempt
  without the flag, no other model, no other route. (Transient failures, 429
  and 5xx, are retried by the client with the SAME request body, so a retry
  cannot drop the flag.)
* Provenance is per call: the outcome carries the provenance block of the call
  that produced the response (the model and provider that served it, as the
  response says, beside the model requested, and the options actually SENT).
* A teacher call is impossible without the guarantee in the client and in the
  request that actually went out.

Terminal states
---------------
RESPONDED               a completion came back, with the flag in the sent request.
REFUSED                 the API rejected the request (a 4xx other than auth/credits).
PROVIDER_ERROR          a 200 whose choice reports an error. Never cached.
NONCONFORMING           a response whose SENT request lacks the flag (cannot be
                        used; should be unreachable).
INFRASTRUCTURE_FAILED   transient failures survived every retry. Not a verdict on
                        the statement; re-running it is allowed and uses the same flag.
HARD_STOP               credits exhausted or authentication failed. Not "move
                        on": every following call would fail the same way.
"""

import hashlib
import json
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

import httpx

from qcagent.llm.base import BaseLLMClient, InfrastructureError, LLMResponse
from qcagent.llm.openrouter_client import ProviderReportedError
from qcagent.llm.profiles import Profile

_BODY_LIMIT = 2000


class TeacherState(StrEnum):
    RESPONDED = "responded"
    REFUSED = "refused"
    PROVIDER_ERROR = "provider_error"
    NONCONFORMING = "nonconforming"
    INFRASTRUCTURE_FAILED = "infrastructure_failed"
    HARD_STOP = "hard_stop"


class TeacherConfigError(RuntimeError):
    """The client handed to the state machine is not a teacher client."""


class PipelineHalt(RuntimeError):
    """Raised by the breaker: stop the whole pipeline, do not move on."""


@dataclass(frozen=True)
class TeacherOutcome:
    statement_id: str
    state: TeacherState
    response: LLMResponse | None = None
    reason_code: str | None = None
    detail: dict[str, Any] = field(default_factory=dict)
    from_cache: bool = False
    # Recorded, not enforced: a dataset with more than one served model has two
    # teachers in it and its documentation must say so.
    served_model_differs: bool | None = None


def require_teacher_client(client: BaseLLMClient, profile: Profile | None = None) -> None:
    if profile is not None and profile.role != "teacher":
        raise TeacherConfigError(f"profile {profile.name!r} is not a teacher profile")
    options = getattr(client, "provider_options", None)
    if not options or json.loads(options).get("enforce_distillable_text") is not True:
        raise TeacherConfigError(
            "this client was not built with provider.enforce_distillable_text: true; "
            "refusing to make a teacher call"
        )


def _error_body(response: httpx.Response) -> dict[str, Any]:
    text = response.text[:_BODY_LIMIT]
    parsed: dict[str, Any] = {"status": response.status_code, "body": text}
    try:
        error = response.json().get("error")
    except ValueError:
        return parsed
    if isinstance(error, dict):
        parsed["error_code"] = error.get("code", "unavailable")
        parsed["error_message"] = error.get("message", "unavailable")
    return parsed


def request_hash(system: str, prompt: str, seed: int, max_tokens: int, client: Any) -> str:
    raw = json.dumps(
        [
            client.model_id,
            getattr(client, "provider_options", None),
            seed,
            max_tokens,
            system,
            prompt,
        ],
        sort_keys=True,
    )
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def call_teacher(
    client: BaseLLMClient,
    *,
    statement_id: str,
    system: str,
    prompt: str,
    seed: int,
    max_tokens: int,
) -> TeacherOutcome:
    require_teacher_client(client)
    digest = request_hash(system, prompt, seed, max_tokens, client)
    try:
        response = client.generate(system=system, prompt=prompt, seed=seed, max_tokens=max_tokens)
    except ProviderReportedError as exc:
        return TeacherOutcome(
            statement_id,
            TeacherState.PROVIDER_ERROR,
            reason_code="choice_error",
            detail={"message": str(exc), "provenance": exc.provenance, "request_hash": digest},
        )
    except InfrastructureError as exc:
        return TeacherOutcome(
            statement_id,
            TeacherState.INFRASTRUCTURE_FAILED,
            reason_code="retries_exhausted",
            detail={"message": str(exc)[:_BODY_LIMIT], "request_hash": digest},
        )
    except httpx.HTTPStatusError as exc:
        body = _error_body(exc.response)
        body["request_hash"] = digest
        status = exc.response.status_code
        if status == 402:
            return TeacherOutcome(
                statement_id, TeacherState.HARD_STOP, reason_code="credits", detail=body
            )
        if status in (401, 403):
            return TeacherOutcome(
                statement_id, TeacherState.HARD_STOP, reason_code="auth", detail=body
            )
        return TeacherOutcome(
            statement_id, TeacherState.REFUSED, reason_code=f"http_{status}", detail=body
        )

    provenance = response.provenance
    sent = (provenance or {}).get("provider_options_sent")
    if not isinstance(sent, dict) or sent.get("enforce_distillable_text") is not True:
        return TeacherOutcome(
            statement_id,
            TeacherState.NONCONFORMING,
            response=response,
            reason_code="flag_not_in_sent_request",
            detail={"provider_options_sent": sent if provenance else "no-provenance"},
        )
    served = provenance["derived"]["served_model"]
    # A snapshot id resolves to a dated canonical slug and a response may name
    # either: the client carries the set it accepts (default: the requested id).
    accepted = getattr(client, "accepted_served_models", None) or {client.model_id}
    return TeacherOutcome(
        statement_id,
        TeacherState.RESPONDED,
        response=response,
        from_cache=client.last_call_cache_hit,
        served_model_differs=(None if served == "unavailable" else served not in accepted),
    )


class RefusalBreaker:
    """Pipeline-level stop. A single refusal is a statement's verdict; a run of
    them means the chosen model is not distillable at all, and going on would
    only fail the rest one at a time. A HARD_STOP halts at once."""

    def __init__(self, consecutive_limit: int = 10) -> None:
        self.limit = consecutive_limit
        self._consecutive = 0

    def record(self, outcome: TeacherOutcome) -> None:
        if outcome.state is TeacherState.HARD_STOP:
            raise PipelineHalt(f"hard stop: {outcome.reason_code}")
        if outcome.state is TeacherState.REFUSED:
            self._consecutive += 1
            if self._consecutive >= self.limit:
                raise PipelineHalt(
                    f"{self._consecutive} consecutive refusals "
                    f"(last: {outcome.reason_code}); the model is probably not distillable"
                )
        else:
            self._consecutive = 0
