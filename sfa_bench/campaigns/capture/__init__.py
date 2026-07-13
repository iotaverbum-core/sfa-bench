"""SFA-Bench alpha.2 locked campaign execution and evidence capture."""

from .adapters import (
    ADAPTER_PROTOCOL_VERSION,
    CaptureAdapter,
    LockedCaptureRequest,
    SyntheticAdapter,
    TransportResult,
)
from .authorization import (
    AUTHORIZATION_SCHEMA,
    authorization_digest,
    seal_authorization,
    validate_authorization,
)
from .canonical import CaptureError, canonical_bytes, sha256_bytes, strict_json_file
from .context import REQUIRED_ALPHA2_BINDINGS, verify_governed_context
from .judgment import JUDGMENT_SCHEMA, judge_run, verify_judgment
from .lifecycle import EVENT_SCHEMA, STATES, verify_ledger
from .review import REVIEW_BUNDLE_SCHEMA, build_review_bundle, verify_review_bundle
from .run import (
    CAPTURE_MANIFEST_SCHEMA,
    capture_attempt,
    initialize_run,
    recover_run,
    seal_run,
    verify_run,
)

__all__ = [
    "ADAPTER_PROTOCOL_VERSION",
    "AUTHORIZATION_SCHEMA",
    "CAPTURE_MANIFEST_SCHEMA",
    "CaptureAdapter",
    "CaptureError",
    "EVENT_SCHEMA",
    "JUDGMENT_SCHEMA",
    "LockedCaptureRequest",
    "REQUIRED_ALPHA2_BINDINGS",
    "REVIEW_BUNDLE_SCHEMA",
    "STATES",
    "SyntheticAdapter",
    "TransportResult",
    "authorization_digest",
    "build_review_bundle",
    "canonical_bytes",
    "capture_attempt",
    "initialize_run",
    "judge_run",
    "recover_run",
    "seal_authorization",
    "seal_run",
    "sha256_bytes",
    "strict_json_file",
    "validate_authorization",
    "verify_governed_context",
    "verify_judgment",
    "verify_ledger",
    "verify_review_bundle",
    "verify_run",
]
