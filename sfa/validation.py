"""Read-only validation helpers for SFA-Bench trust records.

These functions attest existing artifacts, cases, ledgers, lineage references,
and taxonomy references. They report problems and never repair, rewrite, or
normalise corrupted state.
"""
from dataclasses import dataclass
import json
import os

from . import artifact as artifact_mod
from . import families as fam_mod
from . import hashing
from . import ledger as ledger_mod


@dataclass(frozen=True)
class ValidationIssue:
    code: str
    message: str
    path: str = ""
    subject: str = ""


def _read_json(path):
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _issue(code, message, path="", subject=""):
    return ValidationIssue(code=code, message=message, path=path, subject=subject)


def _artifact_paths(artifacts_dir):
    if not os.path.isdir(artifacts_dir):
        return []
    return [
        os.path.join(artifacts_dir, name)
        for name in sorted(os.listdir(artifacts_dir))
        if name.endswith(".sealed.json")
    ]


def _load_artifact(artifact_or_path):
    if isinstance(artifact_or_path, str):
        return _read_json(artifact_or_path), artifact_or_path
    return artifact_or_path, ""


def validate_artifact_integrity(artifact_or_path):
    """Validate one sealed artifact's content hash."""
    try:
        artifact, path = _load_artifact(artifact_or_path)
    except (OSError, json.JSONDecodeError) as exc:
        path = artifact_or_path if isinstance(artifact_or_path, str) else ""
        return [_issue("artifact_json_invalid", str(exc), path)]

    if not isinstance(artifact, dict):
        return [_issue("artifact_invalid", "artifact must be a JSON object", path)]

    if "artifact_hash" not in artifact:
        return [_issue("artifact_hash_missing", "artifact_hash is missing", path)]

    intact, recomputed = artifact_mod.verify_artifact_integrity(artifact)
    if intact:
        return []
    stored = artifact.get("artifact_hash")
    return [
        _issue(
            "seal_hash_mismatch",
            f"stored {str(stored)[:12]} != recomputed {recomputed[:12]}",
            path,
            artifact.get("case_id", ""),
        )
    ]


def validate_case_hashes(artifact_or_path, cases_dir):
    """Validate that a case still matches the hashes sealed in an artifact."""
    try:
        artifact, artifact_path = _load_artifact(artifact_or_path)
    except (OSError, json.JSONDecodeError) as exc:
        path = artifact_or_path if isinstance(artifact_or_path, str) else ""
        return [_issue("artifact_json_invalid", str(exc), path)]

    case_id = artifact.get("case_id")
    if not case_id:
        return [_issue("case_id_missing", "artifact has no case_id", artifact_path)]

    case_dir = os.path.join(cases_dir, case_id)
    if not os.path.isdir(case_dir):
        return [_issue("case_missing", f"case directory not found: {case_id}", case_dir, case_id)]

    files = (
        ("input_hash", "input.json", "input_hash_mismatch"),
        ("evidence_hash", "evidence.json", "evidence_hash_mismatch"),
        ("candidate_hash", "candidate_answer.json", "candidate_hash_mismatch"),
    )
    issues = []
    for field, filename, code in files:
        path = os.path.join(case_dir, filename)
        try:
            obj = _read_json(path)
        except (OSError, json.JSONDecodeError) as exc:
            issues.append(_issue("case_json_invalid", str(exc), path, case_id))
            continue
        recomputed = hashing.sha256_hex(obj)
        if artifact.get(field) != recomputed:
            issues.append(
                _issue(
                    code,
                    f"{filename} hash changed: stored {str(artifact.get(field))[:12]} != recomputed {recomputed[:12]}",
                    path,
                    case_id,
                )
            )
    return issues


def validate_ledger_chain(ledger_path):
    """Validate the occurrence ledger hash chain."""
    ok, errors, _count = ledger_mod.verify_chain(ledger_path)
    if ok:
        return []
    issues = []
    for index, message in errors:
        code = "ledger_chain_invalid"
        if "entry hash mismatch" in message:
            code = "ledger_entry_hash_mismatch"
        elif "broken link" in message:
            code = "ledger_chain_broken"
        elif "seq mismatch" in message:
            code = "ledger_seq_mismatch"
        elif "invalid ledger JSON" in message:
            code = "ledger_json_invalid"
        issues.append(_issue(code, message, ledger_path, f"entry {index}"))
    return issues


def validate_lineage_parents(artifacts_dir):
    """Validate parent_artifact_id references and lineage depths."""
    issues = []
    artifacts = []
    by_hash = {}

    for path in _artifact_paths(artifacts_dir):
        try:
            art = _read_json(path)
        except (OSError, json.JSONDecodeError) as exc:
            issues.append(_issue("artifact_json_invalid", str(exc), path))
            continue
        artifacts.append((path, art))
        h = art.get("artifact_hash")
        if h in by_hash:
            issues.append(_issue("duplicate_artifact_hash", f"duplicate artifact hash {h}", path, h or ""))
        elif h:
            by_hash[h] = (path, art)

    for path, art in artifacts:
        parent = art.get("parent_artifact_id")
        if not parent:
            continue
        if parent not in by_hash:
            issues.append(
                _issue(
                    "missing_lineage_parent",
                    f"parent_artifact_id does not exist: {parent}",
                    path,
                    art.get("artifact_hash", ""),
                )
            )
            continue
        parent_art = by_hash[parent][1]
        expected_depth = int(parent_art.get("lineage_depth", 0)) + 1
        if int(art.get("lineage_depth", 0)) != expected_depth:
            issues.append(
                _issue(
                    "lineage_depth_mismatch",
                    f"lineage_depth {art.get('lineage_depth')} should be {expected_depth}",
                    path,
                    art.get("artifact_hash", ""),
                )
            )

    return issues + _validate_lineage_cycles(by_hash)


def _validate_lineage_cycles(by_hash):
    issues = []
    for artifact_hash, (path, _art) in by_hash.items():
        seen = set()
        cur = artifact_hash
        while cur:
            if cur in seen:
                issues.append(_issue("lineage_cycle", f"lineage cycle at {cur}", path, artifact_hash))
                break
            seen.add(cur)
            parent_tuple = by_hash.get(cur)
            if not parent_tuple:
                break
            cur = parent_tuple[1].get("parent_artifact_id")
    return issues


def validate_taxonomy_references(taxonomy_path, artifacts_dir=None, ledger_path=None):
    """Validate that artifacts and ledger entries reference known families."""
    try:
        taxonomy, _version = fam_mod.load_taxonomy(taxonomy_path)
    except (OSError, json.JSONDecodeError, KeyError, ValueError) as exc:
        return [_issue("taxonomy_invalid", str(exc), taxonomy_path)]

    issues = []
    required = set(fam_mod.CATEGORY_TO_FAMILY.values()) | {"uncategorized"}
    for family_id in sorted(required):
        if not taxonomy.known(family_id):
            issues.append(
                _issue(
                    "taxonomy_missing_required_family",
                    f"required family is missing: {family_id}",
                    taxonomy_path,
                    family_id,
                )
            )

    if artifacts_dir:
        for path in _artifact_paths(artifacts_dir):
            try:
                art = _read_json(path)
            except (OSError, json.JSONDecodeError) as exc:
                issues.append(_issue("artifact_json_invalid", str(exc), path))
                continue
            family_id = artifact_mod.family_of(art, fam_mod.CATEGORY_TO_FAMILY)
            if not taxonomy.known(family_id):
                issues.append(
                    _issue(
                        "unknown_artifact_family",
                        f"artifact references unknown family: {family_id}",
                        path,
                        family_id,
                    )
                )
                continue
            expected_root = fam_mod.CATEGORY_TO_FAMILY.get(art.get("failure_category"))
            if expected_root and expected_root not in taxonomy.ancestry(family_id):
                issues.append(
                    _issue(
                        "artifact_family_ancestry_mismatch",
                        f"{family_id} is not under category root {expected_root}",
                        path,
                        family_id,
                    )
                )

    if ledger_path:
        try:
            entries = ledger_mod.read_ledger(ledger_path)
        except ValueError as exc:
            return issues + [_issue("ledger_json_invalid", str(exc), ledger_path)]
        for index, entry in enumerate(entries):
            family_id = entry.get("family")
            if not taxonomy.known(family_id):
                issues.append(
                    _issue(
                        "unknown_ledger_family",
                        f"ledger entry references unknown family: {family_id}",
                        ledger_path,
                        f"entry {index}",
                    )
                )
                continue
            expected_root = fam_mod.CATEGORY_TO_FAMILY.get(entry.get("category"))
            if expected_root and expected_root not in taxonomy.ancestry(family_id):
                issues.append(
                    _issue(
                        "ledger_family_ancestry_mismatch",
                        f"{family_id} is not under category root {expected_root}",
                        ledger_path,
                        f"entry {index}",
                    )
                )
    return issues


def validate_taxonomy_ancestry_consistency(taxonomy_path, baseline_taxonomy_path=None):
    """Validate taxonomy ancestry, optionally against a known-good baseline."""
    try:
        taxonomy, _version = fam_mod.load_taxonomy(taxonomy_path)
    except (OSError, json.JSONDecodeError, KeyError, ValueError) as exc:
        return [_issue("taxonomy_invalid", str(exc), taxonomy_path)]

    issues = []
    for family_id in taxonomy.all_ids():
        try:
            taxonomy.ancestry(family_id)
        except ValueError as exc:
            issues.append(_issue("taxonomy_ancestry_invalid", str(exc), taxonomy_path, family_id))

    if baseline_taxonomy_path is None:
        return issues

    try:
        baseline, _baseline_version = fam_mod.load_taxonomy(baseline_taxonomy_path)
    except (OSError, json.JSONDecodeError, KeyError, ValueError) as exc:
        return issues + [_issue("baseline_taxonomy_invalid", str(exc), baseline_taxonomy_path)]

    for family_id in baseline.all_ids():
        if not taxonomy.known(family_id):
            issues.append(
                _issue(
                    "taxonomy_family_removed",
                    f"baseline family is missing: {family_id}",
                    taxonomy_path,
                    family_id,
                )
            )
            continue
        baseline_ancestry = baseline.ancestry(family_id)
        current_ancestry = taxonomy.ancestry(family_id)
        if current_ancestry != baseline_ancestry:
            issues.append(
                _issue(
                    "taxonomy_ancestry_drift",
                    f"{family_id} ancestry changed: {baseline_ancestry} -> {current_ancestry}",
                    taxonomy_path,
                    family_id,
                )
            )

    return issues
