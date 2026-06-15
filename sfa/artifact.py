"""Sealed Failure Artifacts v0.2.

An artifact is an immutable, content-addressed, tamper-evident record of a single
distinct failure. v0.2 adds history-bearing fields, set once at seal time and
never edited:

  - failure_family     : leaf taxonomy id
  - parent_artifact_id : predecessor artifact this failure descends from
  - lineage_depth      : root = 0, child = 1, etc.

The artifact_hash covers every other field. Any later edit breaks the seal.
Legacy v0.1 artifacts remain readable by the history engine.
"""
from datetime import datetime, timezone

from .hashing import sha256_hex

ARTIFACT_SCHEMA = "sfa.artifact.v0.2"
LEGACY_SCHEMA = "sfa.artifact.v0.1"


def seal_failure(case_id, input_obj, evidence_obj, candidate_obj, verifier_version, category, family, explanation, parent_artifact_id=None, lineage_depth=0, sealed_at=None):
    artifact = {
        "schema": ARTIFACT_SCHEMA,
        "case_id": case_id,
        "sealed_at": sealed_at or datetime.now(timezone.utc).isoformat(),
        "input_hash": sha256_hex(input_obj),
        "evidence_hash": sha256_hex(evidence_obj),
        "candidate_hash": sha256_hex(candidate_obj),
        "verifier_version": verifier_version,
        "failure_category": category,
        "failure_family": family,
        "failure_explanation": explanation,
        "parent_artifact_id": parent_artifact_id,
        "lineage_depth": int(lineage_depth),
    }
    artifact["artifact_hash"] = _seal_hash(artifact)
    return artifact


def _seal_hash(artifact):
    payload = {k: v for k, v in artifact.items() if k != "artifact_hash"}
    return sha256_hex(payload)


def verify_artifact_integrity(artifact):
    stored = artifact.get("artifact_hash")
    recomputed = _seal_hash(artifact)
    return stored == recomputed, recomputed


def family_of(artifact, category_to_family):
    fam = artifact.get("failure_family")
    if fam:
        return fam
    return category_to_family.get(artifact.get("failure_category"), "uncategorized")
