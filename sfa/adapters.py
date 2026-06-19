"""Optional transcript adapter boundary for SFA-Bench v0.7.

Adapters sit on the proposer side. They may produce transcript-shaped raw
source, but they do not normalize candidates and they never call the verifier.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import json
import os
from pathlib import Path
from typing import Any, Mapping, Protocol

from . import transcript as transcript_mod


DEFAULT_ADAPTER_ID = "fixture-transcript-adapter-v0"
LIVE_PLACEHOLDER_ADAPTER_ID = "live-placeholder-adapter-v0"
SFA_ADAPTER_ENV = "SFA_ADAPTER"
SFA_ENABLE_LIVE_ENV = "SFA_ENABLE_LIVE_ADAPTERS"
CI_ENV = "CI"


class AdapterUnavailableError(RuntimeError):
    """Raised when an adapter is disabled by the v0.7 boundary."""


@dataclass(frozen=True)
class AdapterSpec:
    adapter_id: str
    mode: str
    is_live: bool
    ci_allowed: bool
    description: str


@dataclass(frozen=True)
class AdapterRequest:
    """Prompt-side payload accepted by transcript adapters."""

    case_id: str
    prompt: dict[str, Any] | None = None
    input_obj: dict[str, Any] | None = None
    evidence_obj: dict[str, Any] | None = None
    rules_obj: dict[str, Any] | None = None


class TranscriptAdapter(Protocol):
    spec: AdapterSpec

    def produce_transcript(self, request: AdapterRequest) -> dict[str, Any]:
        """Return transcript-shaped raw source for the v0.6 normalizer."""


class FixtureTranscriptAdapter:
    """Deterministic offline adapter backed by a local transcript fixture."""

    spec = AdapterSpec(
        adapter_id=DEFAULT_ADAPTER_ID,
        mode="offline",
        is_live=False,
        ci_allowed=True,
        description="offline fixture adapter returning a local transcript",
    )

    def __init__(self, fixture_path: str | os.PathLike[str] | None = None):
        if fixture_path is None:
            fixture_path = (
                Path(__file__).resolve().parent.parent
                / "examples"
                / "external_transcripts"
                / "bad_transcript.json"
            )
        self.fixture_path = Path(fixture_path)

    def produce_transcript(self, request: AdapterRequest) -> dict[str, Any]:
        with self.fixture_path.open("r", encoding="utf-8") as fh:
            raw = json.load(fh)
        transcript = deepcopy(raw)
        if transcript.get("case_id") != request.case_id:
            raise AdapterUnavailableError(
                f"fixture transcript is for case {transcript.get('case_id')!r}, "
                f"not {request.case_id!r}"
            )

        metadata = transcript.setdefault("metadata", {})
        metadata["adapter_id"] = self.spec.adapter_id
        metadata.setdefault("provider", "fixture-provider")
        metadata.setdefault("model_id", "fixture-model-a")
        metadata.setdefault("parameters", {"temperature": 0, "top_p": 1, "seed": 101})
        transcript.setdefault(
            "prompt",
            request.prompt
            or {
                "text": "Offline fixture prompt.",
                "prompt_hash": "fixture-prompt-hash-contract-status-v0",
            },
        )
        assert_transcript_raw_source(transcript)
        return transcript


class LiveAdapterPlaceholder:
    """Fail-closed placeholder proving the live boundary without a provider."""

    spec = AdapterSpec(
        adapter_id=LIVE_PLACEHOLDER_ADAPTER_ID,
        mode="live",
        is_live=True,
        ci_allowed=False,
        description="disabled v0.7 live adapter placeholder",
    )

    def produce_transcript(self, request: AdapterRequest) -> dict[str, Any]:
        raise AdapterUnavailableError(
            "live adapter placeholder has no provider integration in v0.7; "
            "no API, model, or network call was made"
        )


def all_adapter_specs() -> list[AdapterSpec]:
    """Return every declared adapter spec, including unavailable placeholders."""

    return [FixtureTranscriptAdapter.spec, LiveAdapterPlaceholder.spec]


def list_adapter_specs(env: Mapping[str, str] | None = None) -> list[AdapterSpec]:
    """Return adapters reachable under the supplied environment."""

    env_map = _env_map(env)
    _assert_ci_allows_env(env_map)
    specs = [FixtureTranscriptAdapter.spec]
    if live_adapters_enabled(env_map):
        specs.append(LiveAdapterPlaceholder.spec)
    return specs


def select_adapter(
    adapter_id: str | None = None,
    *,
    env: Mapping[str, str] | None = None,
) -> TranscriptAdapter:
    """Select one adapter under the v0.7 fail-closed policy."""

    env_map = _env_map(env)
    requested = adapter_id or env_map.get(SFA_ADAPTER_ENV) or DEFAULT_ADAPTER_ID
    if requested == DEFAULT_ADAPTER_ID:
        return FixtureTranscriptAdapter()
    if requested == LIVE_PLACEHOLDER_ADAPTER_ID:
        if ci_mode(env_map):
            raise AdapterUnavailableError("live adapters are unavailable when CI=true")
        if not live_adapters_enabled(env_map):
            raise AdapterUnavailableError(
                f"live adapters are disabled; set {SFA_ENABLE_LIVE_ENV}=1 to expose "
                f"{LIVE_PLACEHOLDER_ADAPTER_ID}"
            )
        return LiveAdapterPlaceholder()
    raise AdapterUnavailableError(f"unknown adapter id: {requested}")


def live_adapters_enabled(env: Mapping[str, str] | None = None) -> bool:
    return _env_map(env).get(SFA_ENABLE_LIVE_ENV) == "1"


def ci_mode(env: Mapping[str, str] | None = None) -> bool:
    value = _env_map(env).get(CI_ENV, "")
    return value.lower() in {"1", "true", "yes"}


def assert_transcript_raw_source(raw_source: dict[str, Any]) -> None:
    """Validate the adapter output shape required by the transcript normalizer."""

    if not isinstance(raw_source, dict):
        raise AdapterUnavailableError("adapter output must be a transcript object")
    if raw_source.get("schema") != transcript_mod.TRANSCRIPT_SCHEMA:
        raise AdapterUnavailableError("adapter output has unsupported transcript schema")
    for field in ("case_id", "metadata", "prompt", "raw_response", "captured_at"):
        if field not in raw_source:
            raise AdapterUnavailableError(f"adapter transcript missing {field}")
    metadata = raw_source["metadata"]
    if not isinstance(metadata, dict):
        raise AdapterUnavailableError("adapter transcript metadata must be an object")
    for field in ("adapter_id", "provider", "model_id", "parameters"):
        if field not in metadata:
            raise AdapterUnavailableError(f"adapter transcript metadata missing {field}")
    if not isinstance(metadata["parameters"], dict):
        raise AdapterUnavailableError("adapter transcript parameters must be an object")
    prompt = raw_source["prompt"]
    if not isinstance(prompt, dict) or not ("text" in prompt or "prompt_hash" in prompt):
        raise AdapterUnavailableError("adapter transcript prompt must include text or prompt_hash")
    if not isinstance(raw_source["raw_response"], str):
        raise AdapterUnavailableError("adapter transcript raw_response must be a string")


def _assert_ci_allows_env(env: Mapping[str, str]) -> None:
    if ci_mode(env) and live_adapters_enabled(env):
        raise AdapterUnavailableError("live adapters cannot be enabled when CI=true")


def _env_map(env: Mapping[str, str] | None) -> dict[str, str]:
    if env is None:
        return dict(os.environ)
    return dict(env)
