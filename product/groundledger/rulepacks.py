"""Rule-pack loading.

A rule pack is a customer-facing, versioned definition of "what grounded means"
for a domain. It wraps the generic ``sfa`` verifier rule schema with an id,
version, and human-readable description so non-engineers can reason about it.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

PACKS_DIR = Path(__file__).resolve().parent / "rule_packs"

REQUIRED_FIELDS = ("rule_pack_id", "version", "rules")


class RulePackError(ValueError):
    """Raised when a rule pack is missing or malformed."""


def load_rule_pack(rule_pack_id: str, *, packs_dir: str | Path | None = None) -> dict[str, Any]:
    """Load a rule pack by id from the packs directory."""
    base = Path(packs_dir) if packs_dir else PACKS_DIR
    path = base / f"{rule_pack_id}.json"
    if not path.is_file():
        raise RulePackError(f"unknown rule pack: {rule_pack_id!r}")
    pack = json.loads(path.read_text(encoding="utf-8"))
    for field in REQUIRED_FIELDS:
        if field not in pack:
            raise RulePackError(f"rule pack {rule_pack_id!r} missing field {field!r}")
    if pack["rule_pack_id"] != rule_pack_id:
        raise RulePackError(
            f"rule pack id mismatch: file {rule_pack_id!r} declares {pack['rule_pack_id']!r}"
        )
    return pack


def list_rule_packs(*, packs_dir: str | Path | None = None) -> list[dict[str, str]]:
    """Return id/version/title for every available rule pack."""
    base = Path(packs_dir) if packs_dir else PACKS_DIR
    out: list[dict[str, str]] = []
    for path in sorted(base.glob("*.json")):
        pack = json.loads(path.read_text(encoding="utf-8"))
        out.append(
            {
                "rule_pack_id": pack.get("rule_pack_id", path.stem),
                "version": pack.get("version", "unknown"),
                "title": pack.get("title", ""),
            }
        )
    return out
