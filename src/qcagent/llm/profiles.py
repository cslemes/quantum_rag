"""Generator backend profiles: ONE description of a generator, ONE code path.

A profile selects a backend; it does not introduce one. The UI, the regression
runner and the by-hand tools all obtain their client from `build_client` and
their reachability from `probe`. There is no second generation or verification
path behind any profile — the client is a `BaseLLMClient`, and everything
downstream of it (graph, validators, records) is the same code.

`client_type` is the load-bearing field. A profile that varied only `base_url`
could never describe an OpenAI-compatible API (different protocol), and adding
one later would mean a second path. `ollama` and `openai_compatible` are the
two protocols; a new backend speaking either is configuration only.

Rules this module enforces, each a defect class that already cost something:

* A profile that cannot be served is REFUSED, by name and with the reason. It
  is never replaced by another profile: the guarantee report would then
  describe a run served by a generator it does not name (F20/F8 in another
  guise — a verdict that does not match what produced it).
* The expected server version belongs to the profile, so a correct run on a
  backend pinned to a different version is not stamped OVERRIDDEN (that stamp
  separates clean runs from exception runs and must not be spent on a clean
  one).
* No credential is ever stored in a profile, displayed, accepted from a
  client, written to a record or put in a log line. `credential_env` is the
  NAME of an environment variable; its value is resolved here, server-side,
  and handed only to the HTTP client.
"""

import os
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

import httpx
import yaml
from dotenv import dotenv_values
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from qcagent.llm.base import BaseLLMClient

PROFILES_FILE = Path(__file__).resolve().parents[3] / "generator_profiles.yaml"
ENV_FILE = Path(__file__).resolve().parents[3] / ".env"

ClientType = Literal["ollama", "openai_compatible"]
_ENV_NAME = re.compile(r"^[A-Z_][A-Z0-9_]*$")


class ProfileError(RuntimeError):
    """A profile is unknown, malformed or cannot be served."""


class Determinism(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    # per_run: reset the server's engine state before EVERY run (F28);
    # none: nothing to reset (a hosted API has no state to unload).
    reset_strategy: Literal["per_run", "none"] = "per_run"
    temperature: float | None = 0.0
    num_ctx: int | None = None


class Profile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(pattern=r"^[a-z0-9][a-z0-9-]*$")
    label: str
    client_type: ClientType
    base_url: str | None = None
    # Optional environment override for base_url (a host path that differs per
    # machine). A NAME, never a value.
    base_url_env: str | None = None
    model: str
    # Nullable: a backend with no pinned version (or no version concept — a
    # hosted API) is recorded as such, not gated.
    expected_server_version: str | None = None
    # NAME of the environment variable holding the credential. Never the value.
    credential_env: str | None = None
    determinism: Determinism = Determinism()
    pricing_usd_per_mtok: tuple[float, float] | None = None
    # Shown when the backend is unreachable: what must already be up.
    setup_hint: str | None = None

    @field_validator("base_url_env", "credential_env")
    @classmethod
    def _is_an_env_name(cls, value: str | None) -> str | None:
        if value is not None and not _ENV_NAME.fullmatch(value):
            raise ValueError(
                "must be the NAME of an environment variable (UPPER_SNAKE_CASE), "
                "not a value — a credential must never be written into a profile"
            )
        return value

    @field_validator("base_url")
    @classmethod
    def _plain_url(cls, value: str | None) -> str | None:
        if value is None:
            return value
        parts = urlsplit(value)
        if parts.scheme not in ("http", "https") or not parts.hostname:
            raise ValueError("base_url must be an http(s) URL")
        if parts.username or parts.password or parts.query or parts.fragment:
            raise ValueError("base_url must not carry credentials, a query or a fragment")
        return value

    @model_validator(mode="after")
    def _client_type_constraints(self) -> "Profile":
        if self.client_type == "ollama":
            if self.determinism.temperature is None or self.determinism.num_ctx is None:
                raise ValueError(
                    "an ollama profile must pin temperature and num_ctx — an inherited "
                    "server default changes the measurement (F15, D10b)"
                )
        else:
            if self.expected_server_version is not None:
                raise ValueError("an openai_compatible endpoint has no server version to pin")
            if self.credential_env is None:
                raise ValueError("an openai_compatible profile needs credential_env")
        return self


class ProfileSet(BaseModel):
    model_config = ConfigDict(extra="forbid")

    default: str
    profiles: list[Profile]

    @model_validator(mode="after")
    def _consistent(self) -> "ProfileSet":
        names = [p.name for p in self.profiles]
        if len(set(names)) != len(names):
            raise ValueError("duplicate profile names")
        if self.default not in names:
            raise ValueError(f"default profile {self.default!r} is not defined")
        return self

    def get(self, name: str) -> Profile:
        for profile in self.profiles:
            if profile.name == name:
                return profile
        raise ProfileError(
            f"unknown generator profile {name!r}; known: {[p.name for p in self.profiles]}"
        )


def load_profiles(path: Path = PROFILES_FILE) -> ProfileSet:
    return ProfileSet.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


def get_profile(name: str, path: Path = PROFILES_FILE) -> Profile:
    return load_profiles(path).get(name)


# ---------------------------------------------------------------------------
# Resolution — values come from the environment / .env, server-side only
# ---------------------------------------------------------------------------


def _env(name: str, env_file: Path = ENV_FILE) -> str | None:
    value = os.environ.get(name)
    if not value and env_file.exists():
        value = dotenv_values(env_file).get(name)
    return value or None


def resolve_base_url(profile: Profile, env_file: Path = ENV_FILE) -> str | None:
    if profile.base_url_env and (override := _env(profile.base_url_env, env_file)):
        return override.rstrip("/")
    return profile.base_url.rstrip("/") if profile.base_url else None


def _resolve_credential(profile: Profile, env_file: Path = ENV_FILE) -> str | None:
    return _env(profile.credential_env, env_file) if profile.credential_env else None


def redact(text: str, profile: Profile, env_file: Path = ENV_FILE) -> str:
    """Strip the profile's credential from any string about to be shown or
    logged. Belt and braces: no code path formats the credential into a
    message, but an exception text from a library is not ours to vouch for."""
    secret = _resolve_credential(profile, env_file)
    return text.replace(secret, "[redacted]") if secret else text


# ---------------------------------------------------------------------------
# Reachability — three states, never two
# ---------------------------------------------------------------------------

State = Literal["reachable", "unreachable", "not_configured"]
VersionGate = Literal["matched", "mismatch", "not_pinned", "not_applicable", "unknown"]


@dataclass(frozen=True)
class ProfileStatus:
    profile: str
    label: str
    state: State
    # Why, in words a person can act on. Always set unless state == reachable.
    reason: str | None = None
    server_version: str | None = None  # what the server ACTUALLY reported
    expected_server_version: str | None = None
    version_gate: VersionGate = "unknown"
    model_digest: str | None = None  # resolved model identity (ollama)
    # When THIS check ran. Reachability is evaluated live every time it is read
    # (never cached at startup: the natural order is app, then pod, then
    # tunnel), so a status without its time would invite reading a stale one.
    checked_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat(timespec="seconds"))

    @property
    def usable(self) -> bool:
        return self.state == "reachable" and self.version_gate != "mismatch"

    def refusal(self) -> str | None:
        """The message for a refused request, or None when it can be served."""
        if self.usable:
            return None
        if self.state == "not_configured":
            return f"Generator profile {self.profile!r} is not configured: {self.reason}."
        if self.state == "unreachable":
            return (
                f"Generator profile {self.profile!r} is configured but unreachable: "
                f"{self.reason}. The request was NOT sent to any other profile."
            )
        return (
            f"Generator profile {self.profile!r} is reachable but its server reports version "
            f"{self.server_version}, and this profile pins {self.expected_server_version}. "
            "Refusing: a different server version is a different system. "
            "The request was NOT sent to any other profile."
        )


def _why(exc: Exception) -> str:
    if isinstance(exc, httpx.ConnectError):
        return "connection refused or host unreachable"
    if isinstance(exc, httpx.TimeoutException):
        return "timed out"
    if isinstance(exc, httpx.HTTPStatusError):
        return f"HTTP {exc.response.status_code}"
    return type(exc).__name__


def _gate(profile: Profile, actual: str | None) -> VersionGate:
    if profile.expected_server_version is None:
        return "not_pinned"
    if actual is None:
        return "unknown"
    return "matched" if actual == profile.expected_server_version else "mismatch"


def probe(
    profile: Profile,
    *,
    timeout: float = 3.0,
    env_file: Path = ENV_FILE,
    client: httpx.Client | None = None,
) -> ProfileStatus:
    """Classify a profile. Cheap, read-only, never generates anything."""
    base = {
        "profile": profile.name,
        "label": profile.label,
        "expected_server_version": profile.expected_server_version,
    }
    url = resolve_base_url(profile, env_file)
    if url is None:
        return ProfileStatus(
            **base, state="not_configured", reason="no base URL is set for this profile"
        )
    if profile.credential_env and _resolve_credential(profile, env_file) is None:
        return ProfileStatus(
            **base,
            state="not_configured",
            reason=f"the credential variable {profile.credential_env} is not set in the "
            "server's environment",
        )

    http = client or httpx.Client(timeout=timeout)
    hint = f" ({profile.setup_hint.strip()})" if profile.setup_hint else ""
    try:
        if profile.client_type == "ollama":
            version = str(http.get(f"{url}/api/version").raise_for_status().json().get("version"))
            tags = http.get(f"{url}/api/tags").raise_for_status().json().get("models", [])
            match = next(
                (m for m in tags if profile.model in (m.get("name"), m.get("model"))), None
            )
            gate = _gate(profile, version)
            common = dict(
                **base,
                server_version=version,
                version_gate=gate,
            )
            if match is None:
                return ProfileStatus(
                    **common,
                    state="unreachable",
                    reason=f"the server is up but model {profile.model!r} is not pulled on it",
                )
            return ProfileStatus(**common, state="reachable", model_digest=match.get("digest"))
        # openai_compatible: authenticated model listing, credential server-side only
        secret = _resolve_credential(profile, env_file)
        http.get(f"{url}/models", headers={"Authorization": f"Bearer {secret}"}).raise_for_status()
        return ProfileStatus(**base, state="reachable", version_gate="not_applicable")
    except httpx.HTTPStatusError as exc:
        reason = (
            "the endpoint rejected the configured credential"
            if exc.response.status_code in (401, 403)
            else _why(exc)
        )
        return ProfileStatus(**base, state="unreachable", reason=reason + hint)
    except (httpx.HTTPError, ValueError) as exc:
        return ProfileStatus(**base, state="unreachable", reason=_why(exc) + hint)
    finally:
        if client is None:
            http.close()


# ---------------------------------------------------------------------------
# The single construction path
# ---------------------------------------------------------------------------


def build_client(profile: Profile, *, env_file: Path = ENV_FILE) -> BaseLLMClient:
    """The ONLY place a generator client is built from configuration."""
    url = resolve_base_url(profile, env_file)
    if url is None:
        raise ProfileError(f"profile {profile.name!r} has no base URL")
    d = profile.determinism
    if profile.client_type == "ollama":
        from qcagent.llm.ollama_client import OllamaClient

        assert d.num_ctx is not None and d.temperature is not None  # pinned by the schema
        return OllamaClient(url, profile.model, d.num_ctx, d.temperature)
    from qcagent.llm.openai_compatible_client import OpenAICompatibleClient

    secret = _resolve_credential(profile, env_file)
    if secret is None:
        raise ProfileError(
            f"profile {profile.name!r}: the credential variable {profile.credential_env} is not set"
        )
    return OpenAICompatibleClient(
        secret,
        profile.model,
        url,
        temperature=d.temperature,
        pricing_usd_per_mtok=profile.pricing_usd_per_mtok,
    )


def reset_server_state(profile: Profile, *, env_file: Path = ENV_FILE) -> None:
    """Apply the profile's reset strategy. A no-op where there is no state."""
    if profile.determinism.reset_strategy != "per_run" or profile.client_type != "ollama":
        return
    from qcagent.llm.ollama_client import reset_generator_state

    url = resolve_base_url(profile, env_file)
    if url is not None:
        reset_generator_state(url, profile.model)


def determinism_stamps(profile: Profile) -> dict[str, str]:
    d = profile.determinism
    return {
        "determinism_reset": d.reset_strategy,
        "determinism_temperature": "not sent" if d.temperature is None else str(d.temperature),
        "determinism_num_ctx": "not applicable" if d.num_ctx is None else str(d.num_ctx),
    }


def identity_stamps(profile: Profile, status: ProfileStatus) -> dict[str, str]:
    """What goes into a run record and a guarantee report to NAME the generator:
    the profile, the model the client was built with (plus its digest where the
    server states one), the server version the server ACTUALLY reported, and
    the determinism settings applied. Names and values only — no credential,
    no URL."""
    stamps = {
        "profile": profile.name,
        "profile_client_type": profile.client_type,
        "model_resolved": profile.model,
        "server_version_reported": status.server_version or "not reported",
        **determinism_stamps(profile),
    }
    if status.model_digest:
        stamps["model_digest"] = status.model_digest
    return stamps
