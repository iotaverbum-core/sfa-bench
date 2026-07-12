"""Strict canonical data and exclusive byte-publication helpers.

This module is an additive alpha.2 surface. It deliberately does not import or
modify the frozen ``sfa.hashing`` implementation.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import re
import tempfile
from typing import Any, Iterable


SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
SAFE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
TIMESTAMP_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$"
)
_WINDOWS_RESERVED = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{i}" for i in range(1, 10)}
    | {f"LPT{i}" for i in range(1, 10)}
)
_SECRET_KEY_FRAGMENTS = frozenset(
    {
        "apikey",
        "accesstoken",
        "authtoken",
        "bearertoken",
        "authorizationheader",
        "cookie",
        "password",
        "passwd",
        "clientsecret",
        "privatekey",
        "credential",
        "credentials",
    }
)
_SECRET_TEXT_PATTERNS = (
    re.compile(r"\bsk-[A-Za-z0-9_-]{12,}\b"),
    re.compile(r"\b(?:ghp|github_pat|glpat)-?[A-Za-z0-9_-]{12,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"\bBearer\s+[A-Za-z0-9._~+/-]{12,}", re.IGNORECASE),
)
_FORBIDDEN_METADATA_TERMS = re.compile(
    r"\b(?:ratified|approved|promoted|published|released|certified|"
    r"compliant|legal(?:ity)?|regulatory\s+conformity|official\s+result)\b",
    re.IGNORECASE,
)


class CaptureError(ValueError):
    """Stable fail-closed error for governed campaign capture."""

    def __init__(self, code: str, message: str, path: str = "$") -> None:
        super().__init__(message)
        self.code = code
        self.path = path
        self.message = message

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code, "path": self.path, "message": self.message}


def _normalized_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.casefold())


def _check_value(value: Any, path: str = "$") -> None:
    if value is None or isinstance(value, (str, bool, int)):
        if isinstance(value, str):
            for char in value:
                point = ord(char)
                if 0xD800 <= point <= 0xDFFF:
                    raise CaptureError(
                        "INVALID_UNICODE_SCALAR",
                        "unpaired Unicode surrogates are not permitted",
                        path,
                    )
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise CaptureError(
                "NONFINITE_NUMBER", "non-finite numbers are not permitted", path
            )
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _check_value(item, f"{path}[{index}]")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise CaptureError(
                    "NONSTRING_JSON_KEY", "JSON object keys must be strings", path
                )
            _check_value(key, f"{path}.<key>")
            _check_value(item, f"{path}.{key}")
        return
    raise CaptureError(
        "NON_JSON_VALUE", f"unsupported JSON value type: {type(value).__name__}", path
    )


def canonical_bytes(value: Any) -> bytes:
    """Return strict, sorted, compact UTF-8 JSON bytes."""
    _check_value(value)
    try:
        text = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        raise CaptureError("NONCANONICAL_JSON", "value cannot be canonicalized") from exc
    return text.encode("utf-8")


def sha256_bytes(data: bytes) -> str:
    if not isinstance(data, bytes):
        raise TypeError("sha256_bytes requires bytes")
    return hashlib.sha256(data).hexdigest()


def sha256_value(value: Any) -> str:
    return sha256_bytes(canonical_bytes(value))


def _reject_constant(value: str) -> None:
    raise CaptureError("NONSTANDARD_JSON_CONSTANT", f"invalid JSON constant {value!r}")


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise CaptureError("DUPLICATE_JSON_KEY", f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def strict_json_loads(data: bytes | str) -> Any:
    """Parse strict JSON, rejecting duplicate keys and non-standard constants."""
    if isinstance(data, bytes):
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise CaptureError("INVALID_JSON_ENCODING", "JSON must be UTF-8") from exc
    elif isinstance(data, str):
        text = data
    else:
        raise TypeError("strict_json_loads requires bytes or str")
    try:
        value = json.loads(
            text,
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
    except CaptureError:
        raise
    except json.JSONDecodeError as exc:
        raise CaptureError("MALFORMED_JSON", "input is not valid JSON") from exc
    _check_value(value)
    return value


def strict_json_file(path: Path, *, require_canonical: bool = False) -> Any:
    data = path.read_bytes()
    value = strict_json_loads(data)
    if require_canonical and canonical_bytes(value) != data:
        raise CaptureError(
            "NONCANONICAL_JSON_FILE",
            "stored governed JSON is not in canonical byte form",
            str(path),
        )
    return value


def require_object(value: Any, path: str = "$") -> dict[str, Any]:
    if not isinstance(value, dict):
        raise CaptureError("MALFORMED_DOCUMENT", "document must be an object", path)
    return value


def require_exact_fields(
    value: dict[str, Any], required: Iterable[str], path: str = "$"
) -> None:
    expected = set(required)
    actual = set(value)
    missing = sorted(expected - actual)
    extra = sorted(actual - expected)
    if missing:
        raise CaptureError(
            "MISSING_FIELD", "missing required fields: " + ", ".join(missing), path
        )
    if extra:
        raise CaptureError(
            "UNKNOWN_FIELD", "unknown fields: " + ", ".join(extra), path
        )


def validate_safe_id(value: Any, path: str) -> str:
    if not isinstance(value, str) or not SAFE_ID_RE.fullmatch(value):
        raise CaptureError(
            "INVALID_PORTABLE_ID",
            "identifier must use 1-64 lowercase ASCII letters, digits, dot, dash, or underscore",
            path,
        )
    stem = value.split(".", 1)[0].upper()
    if stem in _WINDOWS_RESERVED or value in {".", ".."}:
        raise CaptureError("RESERVED_PATH_SEGMENT", "reserved path segment", path)
    return value


def validate_timestamp(value: Any, path: str) -> str:
    if not isinstance(value, str) or not TIMESTAMP_RE.fullmatch(value):
        raise CaptureError(
            "INVALID_TIMESTAMP",
            "timestamp must be timezone-qualified ISO 8601",
            path,
        )
    return value


def validate_repo_relative_path(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value or "\\" in value:
        raise CaptureError("INVALID_REPOSITORY_PATH", "path must use portable '/' form", path)
    if value.startswith("/") or re.match(r"^[A-Za-z]:", value) or value.startswith("//"):
        raise CaptureError("PATH_ESCAPE", "absolute paths are forbidden", path)
    parts = value.split("/")
    if any(not part or part in {".", ".."} for part in parts):
        raise CaptureError("PATH_ESCAPE", "empty, dot, and parent segments are forbidden", path)
    for part in parts:
        if ":" in part or part.endswith((" ", ".")):
            raise CaptureError("NONPORTABLE_PATH", "nonportable path segment", path)
        if part.split(".", 1)[0].upper() in _WINDOWS_RESERVED:
            raise CaptureError("RESERVED_PATH_SEGMENT", "reserved path segment", path)
    if any(part.casefold() in {".git", ".hg", ".svn"} for part in parts):
        raise CaptureError("REPOSITORY_CONTROL_PATH", "repository-control paths are forbidden", path)
    return value


def _is_reparse_point(path: Path) -> bool:
    try:
        stat_result = os.lstat(path)
    except FileNotFoundError:
        return False
    attributes = getattr(stat_result, "st_file_attributes", 0)
    return path.is_symlink() or bool(attributes & 0x400)


def ensure_no_reparse_ancestors(root: Path, target: Path) -> None:
    root_abs = root.absolute()
    target_abs = target.absolute()
    try:
        relative = target_abs.relative_to(root_abs)
    except ValueError as exc:
        raise CaptureError("PATH_ESCAPE", "target escapes approved output root") from exc
    current = root_abs
    if current.exists() and _is_reparse_point(current):
        raise CaptureError("REPARSE_POINT_REJECTED", "output root is a reparse point")
    for part in relative.parts:
        current = current / part
        if current.exists() and _is_reparse_point(current):
            raise CaptureError(
                "REPARSE_POINT_REJECTED",
                "symlink, junction, or reparse-point output paths are forbidden",
                str(current),
            )


def safe_child(root: Path, *segments: str) -> Path:
    for index, segment in enumerate(segments):
        validate_safe_id(segment, f"$.path[{index}]")
    target = root.joinpath(*segments)
    ensure_no_reparse_ancestors(root, target)
    return target


def _fsync_directory(path: Path) -> None:
    try:
        descriptor = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    except OSError:
        pass
    finally:
        os.close(descriptor)


def write_exclusive_bytes(path: Path, data: bytes) -> Path:
    """Publish fully flushed bytes without overwriting an existing target."""
    if not isinstance(data, bytes):
        raise TypeError("write_exclusive_bytes requires bytes")
    path.parent.mkdir(parents=True, exist_ok=True)
    ensure_no_reparse_ancestors(path.parent, path)
    descriptor, temporary_name = tempfile.mkstemp(prefix=".capture-staging-", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError as exc:
            raise CaptureError("NO_OVERWRITE", "refusing to overwrite existing artifact", str(path)) from exc
        except OSError as exc:
            if path.exists():
                raise CaptureError("NO_OVERWRITE", "refusing to overwrite existing artifact", str(path)) from exc
            raise CaptureError("ATOMIC_PUBLISH_FAILED", "exclusive artifact publication failed", str(path)) from exc
        _fsync_directory(path.parent)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
    return path


def write_exclusive_json(path: Path, value: Any) -> Path:
    return write_exclusive_bytes(path, canonical_bytes(value))


def secret_findings(value: Any, path: str = "$") -> list[str]:
    findings: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            normalized = _normalized_key(str(key))
            if any(fragment in normalized for fragment in _SECRET_KEY_FRAGMENTS):
                findings.append(f"{path}.{key}")
            findings.extend(secret_findings(item, f"{path}.{key}"))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            findings.extend(secret_findings(item, f"{path}[{index}]"))
    elif isinstance(value, str):
        if any(pattern.search(value) for pattern in _SECRET_TEXT_PATTERNS):
            findings.append(path)
    return sorted(set(findings))


def bytes_may_contain_secret(data: bytes) -> bool:
    text = data.decode("utf-8", errors="ignore")
    return any(pattern.search(text) for pattern in _SECRET_TEXT_PATTERNS)


def assert_secret_free(value: Any, path: str = "$") -> None:
    findings = secret_findings(value, path)
    if findings:
        raise CaptureError(
            "SECRET_MATERIAL_REJECTED",
            "credential-like material is forbidden in public capture metadata",
            findings[0],
        )


def assert_no_governance_claims(value: Any, path: str = "$") -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            assert_no_governance_claims(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            assert_no_governance_claims(item, f"{path}[{index}]")
    elif isinstance(value, str) and _FORBIDDEN_METADATA_TERMS.search(value):
        raise CaptureError(
            "GOVERNANCE_CLAIM_REJECTED",
            "untrusted metadata cannot assert governance or legal status",
            path,
        )
