"""Per-call provenance for a hosted (routed) model.

OpenRouter routes: the model and provider that answered a request are facts
about the CALL, not about the configuration. The rule here is the one the run
record already follows for the generator: stamp what actually served the
request, next to what was requested, and keep the raw evidence the stamp was
read from.

Two rules about what is not known:

* The response's non-content metadata is stored WHOLESALE (``response_metadata``)
  and the named fields (``derived``) are read out of it. A field is never
  assumed to exist: ``data["provider"]`` is not documented on the pages
  reachable when this was written, so nothing depends on it. A key that is
  absent is ``"unavailable"``; a key that is present with a JSON null is
  ``"returned-null"``. Neither is ``None``: "the response said nothing" and "we
  did not look" are different facts, and ``derived_from`` records which source
  path each named field was read from.
* The provider options are recorded as they were actually SENT (read from the
  request body at send time), never as configured.

Content (the completion text and any reasoning text) is excluded from the
metadata; the dataset stores the raw response separately.
"""

from datetime import UTC, datetime
from typing import Any

UNAVAILABLE = "unavailable"
RETURNED_NULL = "returned-null"
NONE_SENT = "none-sent"

_CONTENT_KEYS = ("content", "reasoning", "reasoning_details")

# named field -> path in the raw response it is read from
_DERIVED_FROM: dict[str, tuple[str, ...]] = {
    "served_model": ("model",),
    "served_provider": ("provider",),
    "generation_id": ("id",),
    "system_fingerprint": ("system_fingerprint",),
    "usage": ("usage",),
    "reported_cost": ("usage", "cost"),
    "finish_reason": ("choices", "0", "finish_reason"),
    "native_finish_reason": ("choices", "0", "native_finish_reason"),
    "choice_error": ("choices", "0", "error"),
}


def pick(data: Any, path: tuple[str, ...]) -> Any:
    """The value at ``path``, ``UNAVAILABLE`` if any key on it is absent, and
    ``RETURNED_NULL`` if it is present and null."""
    node = data
    for key in path:
        if isinstance(node, list):
            if not key.isdigit() or int(key) >= len(node):
                return UNAVAILABLE
            node = node[int(key)]
        elif isinstance(node, dict):
            if key not in node:
                return UNAVAILABLE
            node = node[key]
        else:
            return UNAVAILABLE
    return RETURNED_NULL if node is None else node


def _without_content(data: dict) -> dict:
    """The response with every completion/reasoning text removed, and a list of
    which keys were removed, so the omission is itself a recorded fact."""
    out = {k: v for k, v in data.items() if k != "choices"}
    stripped: list[str] = []
    choices = []
    for i, choice in enumerate(data.get("choices") or []):
        kept = {k: v for k, v in choice.items() if k != "message"}
        message = choice.get("message")
        if isinstance(message, dict):
            kept["message"] = {k: v for k, v in message.items() if k not in _CONTENT_KEYS}
            stripped += [f"choices.{i}.message.{k}" for k in _CONTENT_KEYS if k in message]
        choices.append(kept)
    out["choices"] = choices
    out["_content_keys_removed"] = stripped
    return out


def build_provenance(
    *, requested_model: str, body: dict, http_status: int, data: dict
) -> dict[str, Any]:
    return {
        "requested_model": requested_model,
        # as SENT, from the request body; NONE_SENT when the body had no
        # `provider` object (a fact, distinct from "unavailable")
        "provider_options_sent": body.get("provider", NONE_SENT),
        "http_status": http_status,
        "received_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "response_metadata": _without_content(data),
        "derived": {name: pick(data, path) for name, path in _DERIVED_FROM.items()},
        "derived_from": {name: ".".join(path) for name, path in _DERIVED_FROM.items()},
    }
