"""Filesystem-backed, tenant-scoped storage.

Layout (one directory per tenant)::

    <root>/<tenant>/submissions/<answer_id>.json   raw structured submission
    <root>/<tenant>/receipts/<answer_id>.json      sealed verdict receipt
    <root>/<tenant>/ledger.jsonl                    hash-chained receipt entries

The store keeps the submission so a verdict can be independently re-derived
during replay. v1 is intentionally a flat filesystem; a database is a later
concern and does not change the data contract.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from . import ledger as ledger_mod

_SAFE_ID = re.compile(r"^[A-Za-z0-9._-]{1,128}$")


class StoreError(ValueError):
    """Raised on unsafe identifiers or missing records."""


def _safe(name: str, label: str) -> str:
    if not isinstance(name, str) or not _SAFE_ID.match(name):
        raise StoreError(f"unsafe {label}: {name!r}")
    return name


class TenantStore:
    def __init__(self, root: str | Path, tenant: str):
        self.root = Path(root)
        self.tenant = _safe(tenant, "tenant")
        self.base = self.root / self.tenant
        self.submissions_dir = self.base / "submissions"
        self.receipts_dir = self.base / "receipts"
        self.ledger_path = self.base / "ledger.jsonl"

    def record(self, submission: dict[str, Any], receipt: dict[str, Any]) -> dict[str, Any]:
        """Persist a submission + receipt and append the ledger entry."""
        answer_id = _safe(str(receipt["answer_id"]), "answer_id")
        self.submissions_dir.mkdir(parents=True, exist_ok=True)
        self.receipts_dir.mkdir(parents=True, exist_ok=True)
        self._write_json(self.submissions_dir / f"{answer_id}.json", submission)
        self._write_json(self.receipts_dir / f"{answer_id}.json", receipt)
        return ledger_mod.append_receipt(str(self.ledger_path), receipt)

    def read_submission(self, answer_id: str) -> dict[str, Any]:
        return self._read_json(self.submissions_dir / f"{_safe(answer_id, 'answer_id')}.json")

    def read_receipt(self, answer_id: str) -> dict[str, Any]:
        return self._read_json(self.receipts_dir / f"{_safe(answer_id, 'answer_id')}.json")

    def read_ledger(self) -> list[dict[str, Any]]:
        return ledger_mod.read_ledger(str(self.ledger_path))

    def list_receipts(self) -> list[dict[str, Any]]:
        return [self.read_receipt(entry["answer_id"]) for entry in self.read_ledger()]

    @staticmethod
    def _write_json(path: Path, obj: dict[str, Any]) -> None:
        path.write_text(
            json.dumps(obj, sort_keys=True, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    @staticmethod
    def _read_json(path: Path) -> dict[str, Any]:
        if not path.is_file():
            raise StoreError(f"record not found: {path}")
        return json.loads(path.read_text(encoding="utf-8"))


def list_tenants(root: str | Path) -> list[str]:
    base = Path(root)
    if not base.is_dir():
        return []
    return sorted(p.name for p in base.iterdir() if p.is_dir())
