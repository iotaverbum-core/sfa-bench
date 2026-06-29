"""Append-only, hash-chained receipt ledger.

Each tenant has one ledger. Every verified answer appends exactly one entry that
links to the previous entry by hash. Deleting, inserting, reordering, or editing
an entry breaks the chain, which is what makes the audit trail tamper-evident.

This mirrors the design of ``sfa.ledger`` but chains over product receipts.
"""
from __future__ import annotations

import json
import os
from typing import Any

from sfa.hashing import sha256_hex

GENESIS = "GENESIS"


def _entry_hash(entry: dict[str, Any]) -> str:
    return sha256_hex({k: v for k, v in entry.items() if k != "entry_hash"})


def read_ledger(path: str) -> list[dict[str, Any]]:
    if not os.path.exists(path):
        return []
    out: list[dict[str, Any]] = []
    with open(path, "r", encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, start=1):
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError as exc:
                    raise ValueError(f"invalid ledger JSON on line {line_no}: {exc}") from exc
    return out


def append_receipt(path: str, receipt: dict[str, Any]) -> dict[str, Any]:
    """Append one receipt reference. The only write the ledger permits."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    entries = read_ledger(path)
    prev = entries[-1]["entry_hash"] if entries else GENESIS
    entry = {
        "seq": len(entries),
        "answer_id": receipt["answer_id"],
        "status": receipt["status"],
        "category": receipt.get("category"),
        "family": receipt.get("family"),
        "sealed_at": receipt["sealed_at"],
        "receipt_hash": receipt["receipt_hash"],
        "prev_hash": prev,
    }
    entry["entry_hash"] = _entry_hash(entry)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, sort_keys=True, ensure_ascii=False) + "\n")
    return entry


def verify_chain(path: str) -> tuple[bool, list[tuple[int, str]], int]:
    """Return (ok, errors, count). Detects deletion, insertion, reorder, or edit."""
    try:
        entries = read_ledger(path)
    except ValueError as exc:
        return False, [(-1, str(exc))], 0
    errors: list[tuple[int, str]] = []
    prev = GENESIS
    for i, entry in enumerate(entries):
        if entry.get("seq") != i:
            errors.append((i, f"seq mismatch: stored {entry.get('seq')} expected {i}"))
        if entry.get("prev_hash") != prev:
            errors.append((i, "broken link: prev_hash does not match previous entry"))
        if _entry_hash(entry) != entry.get("entry_hash"):
            errors.append((i, "entry hash mismatch: ledger entry was edited"))
        prev = entry.get("entry_hash")
    return len(errors) == 0, errors, len(entries)
