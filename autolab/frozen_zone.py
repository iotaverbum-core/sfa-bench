"""Frozen-zone manifest, attestation, and enforcement (SFA-AutoLab v0, Item 1).

FROZEN ZONE — this module is itself listed in ``autolab/frozen_manifest.json``.
It, the manifest, and ``frozen_zone_check.py`` protect themselves: changing any
of them changes the sealed zone hash and so trips the attestation check. The
frozen zone may only be changed through the human-only amendment channel
(``autolab/amendments/``) with a human-supplied amendment token, never by the
AutoLab loop.

Invariant 1 of the AutoLab mission ("Frozen zone"): the verifier verdict logic,
gate policy, ledger code, invariant suite, holdout access machinery, seed
schedules, and the AutoLab controller are unpatchable by the loop. Enforcement
has two deterministic, offline mechanisms:

  1. Zone-hash attestation (git-free). The manifest records ``zone_hash``, a
     deterministic hash over the canonical content of every frozen file. CI
     recomputes it; any content drift in a frozen file (without a resealed
     manifest) fails closed. This is the ``verify_attestation`` path and is what
     the loop controller uses for pre/post attestation around an iteration.

  2. Amendment gate (git-based, PR-level). Even a change that *also* reseals the
     manifest is rejected unless it is authorized by a human amendment token
     (``SFA_FROZEN_ZONE_AMENDMENT_TOKEN``) that matches an append-only amendment
     record describing exactly this ``prev_zone_hash -> new_zone_hash``
     transition. The token is an out-of-loop human authority: a protected CI
     input the automated builder cannot set. The code cannot cryptographically
     stop a sufficiently privileged actor from rewriting both a frozen file and
     the manifest — that is *why* the token (the human channel) is required, why
     the zone includes its own enforcement code, and why CI runs the gate
     against a trusted base ref.

The module is stdlib-only and standalone. Its canonical encoding mirrors
``sfa.hashing.canonical_bytes`` deliberately (sorted keys, tight separators,
UTF-8), but it does not import the ``sfa`` package so the attestation keeps
working even if that package fails to import.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

SCHEMA = "sfa.autolab.frozen_zone.v0"
MANIFEST_RELPATH = "autolab/frozen_manifest.json"
AMENDMENT_DIRNAME = "autolab/amendments"
AMENDMENT_TOKEN_ENV = "SFA_FROZEN_ZONE_AMENDMENT_TOKEN"
ZONE_HASH_KEY = "zone_hash"
FILE_DIGESTS_KEY = "file_digests"
AMENDMENT_SCHEMA = "sfa.autolab.frozen_zone.amendment.v0"


# ---------------------------------------------------------------------------
# Canonical hashing (mirrors sfa.hashing; kept standalone on purpose).
# ---------------------------------------------------------------------------
def canonical_bytes(obj: Any) -> bytes:
    """Deterministic byte encoding of a JSON-serialisable object."""
    return json.dumps(
        obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def sha256_hex_obj(obj: Any) -> str:
    """SHA-256 hex digest of an object's canonical encoding."""
    return hashlib.sha256(canonical_bytes(obj)).hexdigest()


def sha256_hex_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ---------------------------------------------------------------------------
# Manifest access.
# ---------------------------------------------------------------------------
def manifest_path(root: str | Path) -> Path:
    return Path(root) / MANIFEST_RELPATH


def load_manifest(root: str | Path) -> dict[str, Any]:
    """Load and lightly validate the frozen-zone manifest."""
    path = manifest_path(root)
    if not path.is_file():
        raise FrozenZoneError(f"frozen manifest not found: {MANIFEST_RELPATH}")
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise FrozenZoneError(f"frozen manifest is not valid JSON: {exc}") from exc
    if not isinstance(manifest, dict):
        raise FrozenZoneError("frozen manifest must be a JSON object")
    if manifest.get("schema") != SCHEMA:
        raise FrozenZoneError(
            f"frozen manifest schema {manifest.get('schema')!r} != {SCHEMA!r}"
        )
    if not isinstance(manifest.get("frozen_paths"), list) or not manifest["frozen_paths"]:
        raise FrozenZoneError("frozen manifest has no frozen_paths")
    if MANIFEST_RELPATH not in manifest["frozen_paths"]:
        raise FrozenZoneError(
            "frozen manifest must list itself in frozen_paths (self-protection)"
        )
    return manifest


class FrozenZoneError(RuntimeError):
    """Raised for a malformed manifest or an unresolvable frozen path."""


def frozen_relpaths(root: str | Path, manifest: dict[str, Any]) -> list[str]:
    """Return the sorted, normalized list of frozen file paths.

    Paths are explicit files (most auditable). Each listed path must resolve to
    an existing regular file, so the zone can never silently under-protect.
    """
    root = Path(root)
    out: list[str] = []
    for raw in manifest["frozen_paths"]:
        rel = str(raw).replace("\\", "/")
        if rel.startswith(AMENDMENT_DIRNAME + "/") or rel == AMENDMENT_DIRNAME:
            raise FrozenZoneError(
                f"the amendment channel {AMENDMENT_DIRNAME}/ must not be frozen"
            )
        target = root / rel
        if not target.is_file():
            raise FrozenZoneError(f"frozen path does not resolve to a file: {rel}")
        out.append(rel)
    if len(set(out)) != len(out):
        raise FrozenZoneError("frozen_paths contains duplicates")
    return sorted(out)


# ---------------------------------------------------------------------------
# Per-file digests and the zone hash.
# ---------------------------------------------------------------------------
def compute_file_digest(root: str | Path, relpath: str) -> str:
    """Canonical content digest of a single frozen file.

    The manifest is special-cased: its digest is taken over the parsed JSON with
    the self-referential ``zone_hash`` and ``file_digests`` keys removed. That
    breaks the circularity of a manifest that records a hash of itself, and it
    makes the digest independent of manifest whitespace/formatting.
    """
    root = Path(root)
    path = root / relpath
    if relpath == MANIFEST_RELPATH:
        obj = json.loads(path.read_text(encoding="utf-8"))
        obj.pop(ZONE_HASH_KEY, None)
        obj.pop(FILE_DIGESTS_KEY, None)
        return sha256_hex_obj(obj)
    return sha256_hex_bytes(path.read_bytes())


def compute_digests(root: str | Path, manifest: dict[str, Any]) -> dict[str, str]:
    """Digest every frozen file (including the manifest's self-digest)."""
    return {rel: compute_file_digest(root, rel) for rel in frozen_relpaths(root, manifest)}


def zone_hash_from_digests(digests: dict[str, str]) -> str:
    """Deterministic zone hash over sorted (relpath, digest) pairs."""
    return sha256_hex_obj([[rel, digests[rel]] for rel in sorted(digests)])


def compute_zone_hash(root: str | Path, manifest: dict[str, Any] | None = None) -> str:
    """Deterministic hash of the whole frozen zone's canonical content."""
    if manifest is None:
        manifest = load_manifest(root)
    return zone_hash_from_digests(compute_digests(root, manifest))


def recorded_file_digests(manifest: dict[str, Any]) -> dict[str, str]:
    value = manifest.get(FILE_DIGESTS_KEY, {})
    return dict(value) if isinstance(value, dict) else {}


# ---------------------------------------------------------------------------
# Attestation (git-free).
# ---------------------------------------------------------------------------
@dataclass
class Attestation:
    manifest_version: str
    zone_hash: str
    recorded_zone_hash: Optional[str]
    file_count: int
    digests: dict[str, str]
    recorded_digests: dict[str, str]

    @property
    def matches(self) -> bool:
        return self.recorded_zone_hash is not None and self.zone_hash == self.recorded_zone_hash

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": SCHEMA,
            "manifest_version": self.manifest_version,
            "zone_hash": self.zone_hash,
            "recorded_zone_hash": self.recorded_zone_hash,
            "matches": self.matches,
            "file_count": self.file_count,
            "files": sorted(self.digests),
        }


def attest(root: str | Path, manifest: dict[str, Any] | None = None) -> Attestation:
    """Compute the current attestation of the frozen zone (no git required)."""
    if manifest is None:
        manifest = load_manifest(root)
    digests = compute_digests(root, manifest)
    return Attestation(
        manifest_version=str(manifest.get("manifest_version", "unknown")),
        zone_hash=zone_hash_from_digests(digests),
        recorded_zone_hash=manifest.get(ZONE_HASH_KEY),
        file_count=len(digests),
        digests=digests,
        recorded_digests=recorded_file_digests(manifest),
    )


def verify_attestation(root: str | Path) -> tuple[bool, list[str], Attestation]:
    """Return (ok, issues, attestation). ``ok`` iff the sealed zone is intact."""
    manifest = load_manifest(root)
    a = attest(root, manifest)
    issues: list[str] = []
    if a.recorded_zone_hash is None:
        issues.append("manifest has no recorded zone_hash (run: frozen_zone_check.py seal)")
    elif not a.matches:
        issues.append(
            f"zone hash drift: recorded {a.recorded_zone_hash} != computed {a.zone_hash}"
        )
    # Per-file diagnostics from recorded file_digests (excludes the manifest).
    for rel, digest in a.digests.items():
        if rel == MANIFEST_RELPATH:
            continue
        recorded = a.recorded_digests.get(rel)
        if recorded is not None and recorded != digest:
            issues.append(f"frozen file modified: {rel}")
    for rel in a.recorded_digests:
        if rel not in a.digests:
            issues.append(f"frozen file removed from zone: {rel}")
    return (not issues), issues, a


# ---------------------------------------------------------------------------
# Path rules.
# ---------------------------------------------------------------------------
def path_is_frozen(relpath: str, manifest: dict[str, Any]) -> bool:
    rel = str(relpath).replace("\\", "/")
    return rel in {str(p).replace("\\", "/") for p in manifest.get("frozen_paths", [])}


def zone_touching_paths(changed_paths: list[str], frozen_set: set[str]) -> list[str]:
    normalized = {p.replace("\\", "/") for p in changed_paths}
    return sorted(normalized & frozen_set)


# ---------------------------------------------------------------------------
# Amendment channel (human-only).
# ---------------------------------------------------------------------------
def load_amendments(root: str | Path) -> list[dict[str, Any]]:
    directory = Path(root) / AMENDMENT_DIRNAME
    if not directory.is_dir():
        return []
    out: list[dict[str, Any]] = []
    for path in sorted(directory.glob("*.json")):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise FrozenZoneError(f"amendment {path.name} is not valid JSON: {exc}") from exc
        if isinstance(record, dict):
            out.append(record)
    return out


def validate_amendment(
    root: str | Path,
    token: Optional[str],
    *,
    base_manifest: Optional[dict[str, Any]],
) -> tuple[bool, list[str]]:
    """Validate that ``token`` authorizes the current zone state.

    A valid token is a non-empty value matching one amendment record whose
    ``new_zone_hash`` equals both the current computed zone hash and the sealed
    manifest ``zone_hash``, and (when a base manifest is known) whose
    ``prev_zone_hash`` equals the base's sealed ``zone_hash``. This binds the
    human authorization to exactly one prev->new transition.
    """
    if not token:
        return False, [
            "frozen-zone change requires a human amendment token "
            f"({AMENDMENT_TOKEN_ENV}); none supplied"
        ]
    manifest = load_manifest(root)
    current_zone = compute_zone_hash(root, manifest)
    amendments = load_amendments(root)
    match = next((a for a in amendments if a.get("amendment_id") == token), None)
    if match is None:
        return False, [
            f"amendment token {token!r} has no matching record in {AMENDMENT_DIRNAME}/"
        ]
    issues: list[str] = []
    if match.get("new_zone_hash") != current_zone:
        issues.append(
            f"amendment {token!r} authorizes new_zone_hash "
            f"{match.get('new_zone_hash')} but the current zone hash is {current_zone}"
        )
    if match.get("new_zone_hash") != manifest.get(ZONE_HASH_KEY):
        issues.append(
            f"amendment {token!r} new_zone_hash does not match the sealed manifest zone_hash"
        )
    if base_manifest is not None and match.get("prev_zone_hash") != base_manifest.get(ZONE_HASH_KEY):
        issues.append(
            f"amendment {token!r} prev_zone_hash {match.get('prev_zone_hash')} "
            f"does not match base zone_hash {base_manifest.get(ZONE_HASH_KEY)}"
        )
    return (not issues), issues


# ---------------------------------------------------------------------------
# Git helpers for the amendment gate.
# ---------------------------------------------------------------------------
def _git(root: str | Path, *args: str) -> tuple[int, str, str]:
    result = subprocess.run(
        ["git", *args],
        cwd=str(root),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    return result.returncode, result.stdout, result.stderr


def git_available(root: str | Path) -> bool:
    rc, _, _ = _git(root, "rev-parse", "--is-inside-work-tree")
    return rc == 0


def base_manifest(root: str | Path, base_ref: str) -> Optional[dict[str, Any]]:
    """Return the frozen manifest as of ``base_ref``, or None if it has none."""
    rc, out, _ = _git(root, "show", f"{base_ref}:{MANIFEST_RELPATH}")
    if rc != 0:
        return None
    try:
        record = json.loads(out)
    except json.JSONDecodeError:
        return None
    return record if isinstance(record, dict) else None


def changed_paths_vs_base(root: str | Path, base_ref: str) -> list[str]:
    """Files changed between ``base_ref`` and HEAD (three-dot, with fallback)."""
    rc, out, _ = _git(root, "diff", "--name-only", f"{base_ref}...HEAD")
    if rc != 0:
        rc, out, _ = _git(root, "diff", "--name-only", base_ref, "HEAD")
    if rc != 0:
        raise FrozenZoneError(f"could not diff against base ref {base_ref!r}")
    return [line.strip().replace("\\", "/") for line in out.splitlines() if line.strip()]


# ---------------------------------------------------------------------------
# Amendment gate (git-based).
# ---------------------------------------------------------------------------
@dataclass
class GateResult:
    ran: bool
    ok: bool
    base_ref: Optional[str]
    genesis: bool
    touched: list[str] = field(default_factory=list)
    manifest_zone_altered: bool = False
    requires_amendment: bool = False
    issues: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def check_amendment_gate(
    root: str | Path,
    *,
    base_ref: str,
    amendment_token: Optional[str],
    changed_paths: Optional[list[str]] = None,
) -> GateResult:
    """Reject any change to files frozen *as of the base* absent a human token."""
    base = base_manifest(root, base_ref)
    if base is None:
        return GateResult(
            ran=True, ok=True, base_ref=base_ref, genesis=True,
            notes=[f"genesis: {base_ref} has no frozen manifest; nothing to amend"],
        )
    base_frozen = {str(p).replace("\\", "/") for p in base.get("frozen_paths", [])}
    if changed_paths is None:
        changed_paths = changed_paths_vs_base(root, base_ref)

    touched = zone_touching_paths(changed_paths, base_frozen)

    manifest_zone_altered = False
    if MANIFEST_RELPATH in {p.replace("\\", "/") for p in changed_paths}:
        current = load_manifest(root)
        current_frozen = {str(p).replace("\\", "/") for p in current.get("frozen_paths", [])}
        if current.get(ZONE_HASH_KEY) != base.get(ZONE_HASH_KEY) or current_frozen != base_frozen:
            manifest_zone_altered = True

    requires_amendment = bool(touched) or manifest_zone_altered
    if not requires_amendment:
        return GateResult(
            ran=True, ok=True, base_ref=base_ref, genesis=False,
            notes=["no change to files frozen as of base"],
        )

    ok, issues = validate_amendment(root, amendment_token, base_manifest=base)
    return GateResult(
        ran=True,
        ok=ok,
        base_ref=base_ref,
        genesis=False,
        touched=touched,
        manifest_zone_altered=manifest_zone_altered,
        requires_amendment=True,
        issues=issues,
    )


# ---------------------------------------------------------------------------
# Combined check (attestation + optional amendment gate).
# ---------------------------------------------------------------------------
@dataclass
class CheckResult:
    ok: bool
    attestation: Attestation
    attestation_ok: bool
    attestation_issues: list[str]
    gate: Optional[GateResult]

    @property
    def failures(self) -> list[str]:
        out = list(self.attestation_issues)
        if self.gate is not None and not self.gate.ok:
            out.extend(self.gate.issues)
        return out


def check(
    root: str | Path,
    *,
    base_ref: Optional[str] = None,
    amendment_token: Optional[str] = None,
    changed_paths: Optional[list[str]] = None,
) -> CheckResult:
    """Run the deterministic attestation and, if a base is given, the git gate."""
    attestation_ok, attestation_issues, attestation = verify_attestation(root)

    gate: Optional[GateResult] = None
    if base_ref is not None or changed_paths is not None:
        if base_ref is None:
            raise FrozenZoneError("amendment gate needs a base_ref when changed_paths is given")
        gate = check_amendment_gate(
            root,
            base_ref=base_ref,
            amendment_token=amendment_token,
            changed_paths=changed_paths,
        )

    ok = attestation_ok and (gate is None or gate.ok)
    return CheckResult(
        ok=ok,
        attestation=attestation,
        attestation_ok=attestation_ok,
        attestation_issues=attestation_issues,
        gate=gate,
    )


# ---------------------------------------------------------------------------
# Sealing (human amendment tooling; never runs under --ci).
# ---------------------------------------------------------------------------
def seal(root: str | Path) -> dict[str, Any]:
    """Recompute and write ``zone_hash`` + ``file_digests`` into the manifest.

    This is human amendment tooling. It is deterministic and idempotent: because
    the manifest's own digest excludes ``zone_hash``/``file_digests``, resealing
    an already-sealed zone reproduces the same values. Returns the sealed
    manifest object.
    """
    root = Path(root)
    manifest = load_manifest(root)
    digests = compute_digests(root, manifest)
    zone_hash = zone_hash_from_digests(digests)
    # file_digests records every frozen file except the manifest itself.
    manifest[FILE_DIGESTS_KEY] = {
        rel: digest for rel, digest in sorted(digests.items()) if rel != MANIFEST_RELPATH
    }
    manifest[ZONE_HASH_KEY] = zone_hash
    manifest_path(root).write_text(
        json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return manifest


def resolve_base_ref(explicit: Optional[str]) -> Optional[str]:
    """Resolve the base ref for the amendment gate from CLI/CI environment."""
    if explicit:
        return explicit
    base = os.environ.get("GITHUB_BASE_REF")
    if base:
        # In GitHub Actions the base branch is fetched as origin/<base>.
        return f"origin/{base}"
    return None


def resolve_amendment_token(explicit: Optional[str]) -> Optional[str]:
    if explicit:
        return explicit
    token = os.environ.get(AMENDMENT_TOKEN_ENV)
    return token or None
