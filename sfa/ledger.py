"""Append-only occurrence ledger.

Artifacts identify distinct sealed failures. The ledger records each observation
of a failure over time. Recurrence, growth, decline, and extinction are derived
from this ledger without mutating artifacts.

Every entry carries prev_hash and entry_hash. New transcript-derived entries
may also carry model_id for reporting; legacy entries resolve to ``unknown``.
This hash chain makes the entire history tamper-evident: deleting, inserting,
reordering, or editing an entry breaks replay.
"""
import json
import os

from .hashing import sha256_hex

GENESIS = "GENESIS"


def _entry_hash(entry):
    payload = {k: v for k, v in entry.items() if k != "entry_hash"}
    return sha256_hex(payload)


def read_ledger(path):
    if not os.path.exists(path):
        return []
    out = []
    with open(path, "r", encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, start=1):
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError as exc:
                    raise ValueError(f"invalid ledger JSON on line {line_no}: {exc}") from exc
    return out


def append_occurrence(path, *, artifact_hash, case_id, category, family, observed_at, period, run_id, synthetic=False, model_id=None):
    """Append one occurrence. This is the only write operation the ledger permits."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    entries = read_ledger(path)
    seq = len(entries)
    prev = entries[-1]["entry_hash"] if entries else GENESIS
    entry = {
        "seq": seq,
        "observed_at": observed_at,
        "period": period,
        "run_id": run_id,
        "artifact_hash": artifact_hash,
        "case_id": case_id,
        "category": category,
        "family": family,
        "synthetic": bool(synthetic),
        "prev_hash": prev,
    }
    if model_id is not None:
        entry["model_id"] = model_id or "unknown"
    entry["entry_hash"] = _entry_hash(entry)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, sort_keys=True, ensure_ascii=False) + "\n")
    return entry


def occurrence_model_id(entry):
    """Return the reporting identity for new or backward-compatible entries."""
    value = entry.get("model_id")
    return value if isinstance(value, str) and value.strip() else "unknown"


def verify_chain(path):
    """Return (ok, errors, count). Detects deletion, insertion, reorder, or edit."""
    try:
        entries = read_ledger(path)
    except ValueError as exc:
        return False, [(-1, str(exc))], 0
    errors = []
    prev = GENESIS
    for i, entry in enumerate(entries):
        if entry.get("seq") != i:
            errors.append((i, f"seq mismatch: stored {entry.get('seq')} expected {i}"))
        if entry.get("prev_hash") != prev:
            errors.append((i, "broken link: prev_hash does not match previous entry"))
        if _entry_hash(entry) != entry.get("entry_hash"):
            errors.append((i, "entry hash mismatch: entry was edited"))
        prev = entry.get("entry_hash")
    return len(errors) == 0, errors, len(entries)
