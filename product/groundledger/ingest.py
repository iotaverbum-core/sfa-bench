"""Bulk ingest of a pilot's answers from a JSONL or CSV file.

One command loads a whole batch of answers plus the evidence each used, verifies
and seals every one into the tenant's ledger, and prints a summary. Structured
answers (with a `candidate`) and free-text answers (with `answer_text`) are both
supported, mixed freely.

JSONL (recommended, lossless) - one submission object per line, exactly the shape
the SDK and API accept:

    {"answer_id": "a1", "rule_pack": "insurance_v1",
     "candidate": {...}  OR  "answer_text": "...",
     "evidence": {"documents": [...], "facts": [...]}, "task_input": {"question": "..."}}

CSV (convenience for spreadsheet exports) - columns:
    answer_id, [question], [answer_text], [candidate_json], evidence_json, [rule_pack]
The *_json columns hold JSON strings; provide either answer_text or candidate_json.

Behaviour built for messy real data: a bad row is reported and skipped, not fatal;
answer_ids already in the ledger are skipped (re-running is safe); a duplicate
answer_id within one file is an error.

Run: python -m product.groundledger.ingest <file> --tenant <t> [--data-root DIR]
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any, Callable

from . import engine, findings as findings_mod, rulepacks
from .store import TenantStore

DEFAULT_RULE_PACK = "insurance_v1"
# (reference, submission_or_None, parse_error_or_None)
ParsedRecord = tuple[str, dict[str, Any] | None, str | None]


def parse_source(path: str | Path, fmt: str = "auto") -> list[ParsedRecord]:
    """Read a JSONL or CSV file into parsed records (row errors captured, not raised)."""
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"no such file: {path}")
    resolved = _resolve_format(path, fmt)
    text = path.read_text(encoding="utf-8")
    if resolved == "jsonl":
        return _parse_jsonl(text)
    if resolved == "csv":
        return _parse_csv(text)
    raise ValueError(f"unsupported format: {resolved!r} (use jsonl or csv)")


def _resolve_format(path: Path, fmt: str) -> str:
    if fmt != "auto":
        return fmt
    suffix = path.suffix.lower()
    if suffix in (".jsonl", ".ndjson"):
        return "jsonl"
    if suffix == ".csv":
        return "csv"
    raise ValueError(f"cannot infer format from {path.name!r}; pass --format jsonl|csv")


def _parse_jsonl(text: str) -> list[ParsedRecord]:
    out: list[ParsedRecord] = []
    for line_no, raw in enumerate(text.splitlines(), start=1):
        raw = raw.strip()
        if not raw:
            continue
        try:
            obj = json.loads(raw)
            if not isinstance(obj, dict):
                raise ValueError("line is not a JSON object")
            out.append((f"line {line_no}", obj, None))
        except (json.JSONDecodeError, ValueError) as exc:
            out.append((f"line {line_no}", None, str(exc)))
    return out


def _parse_csv(text: str) -> list[ParsedRecord]:
    out: list[ParsedRecord] = []
    reader = csv.DictReader(text.splitlines())
    for index, row in enumerate(reader, start=2):  # row 1 is the header
        ref = f"row {index}"
        try:
            out.append((ref, _csv_row_to_submission(row), None))
        except (json.JSONDecodeError, ValueError) as exc:
            out.append((ref, None, str(exc)))
    return out


def _csv_row_to_submission(row: dict[str, str]) -> dict[str, Any]:
    answer_id = (row.get("answer_id") or "").strip()
    if not answer_id:
        raise ValueError("missing answer_id")
    submission: dict[str, Any] = {"answer_id": answer_id}
    rule_pack = (row.get("rule_pack") or "").strip()
    if rule_pack:
        submission["rule_pack"] = rule_pack
    question = (row.get("question") or "").strip()
    if question:
        submission["task_input"] = {"question": question}
    candidate = (row.get("candidate_json") or "").strip()
    answer_text = (row.get("answer_text") or "").strip()
    if candidate:
        submission["candidate"] = json.loads(candidate)
    elif answer_text:
        submission["answer_text"] = answer_text
    else:
        raise ValueError("row needs candidate_json or answer_text")
    evidence = (row.get("evidence_json") or "").strip()
    if not evidence:
        raise ValueError("missing evidence_json")
    submission["evidence"] = json.loads(evidence)
    return submission


def ingest(
    store: TenantStore,
    parsed: list[ParsedRecord],
    *,
    default_rule_pack: str = DEFAULT_RULE_PACK,
    packs_dir: str | None = None,
    now: Callable[[], str] | None = None,
) -> dict[str, Any]:
    """Verify and seal each parsed submission; skip duplicates; collect errors."""
    pre_existing = {entry["answer_id"] for entry in store.read_ledger()}
    seen: set[str] = set()
    errors: list[dict[str, Any]] = []
    receipts: list[dict[str, Any]] = []
    skipped = 0
    pack_cache: dict[str, dict[str, Any]] = {}

    for ref, submission, parse_error in parsed:
        if parse_error is not None:
            errors.append({"ref": ref, "answer_id": None, "error": parse_error})
            continue
        try:
            answer_id = str(submission.get("answer_id") or "")
            if not answer_id:
                raise ValueError("missing answer_id")
            if answer_id in pre_existing:
                skipped += 1  # already in the ledger before this run -> idempotent skip
                continue
            if answer_id in seen:
                raise ValueError(f"duplicate answer_id in this file: {answer_id}")
            pack_id = submission.get("rule_pack", default_rule_pack)
            if pack_id not in pack_cache:
                pack_cache[pack_id] = rulepacks.load_rule_pack(pack_id, packs_dir=packs_dir)
            pack = pack_cache[pack_id]

            if "candidate" in submission:
                receipt = engine.verify_submission(submission, pack, now=now)
                stored = submission
            elif "answer_text" in submission:
                receipt, stored = engine.verify_text_submission(submission, pack, now=now)
            else:
                raise ValueError("record needs 'candidate' or 'answer_text'")

            store.record(stored, receipt)
            seen.add(answer_id)
            receipts.append(receipt)
        except Exception as exc:  # noqa: BLE001 - reported per record, batch continues
            errors.append({"ref": ref, "answer_id": submission.get("answer_id"), "error": str(exc)})

    return {
        "ingested": len(receipts),
        "skipped": skipped,
        "errors": errors,
        "summary": _summarize(receipts),
    }


def ingest_file(
    path: str | Path,
    *,
    tenant: str,
    data_root: str | Path,
    default_rule_pack: str = DEFAULT_RULE_PACK,
    fmt: str = "auto",
    packs_dir: str | None = None,
    now: Callable[[], str] | None = None,
) -> tuple[TenantStore, dict[str, Any]]:
    store = TenantStore(data_root, tenant)
    parsed = parse_source(path, fmt)
    result = ingest(store, parsed, default_rule_pack=default_rule_pack, packs_dir=packs_dir, now=now)
    return store, result


def _summarize(receipts: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(receipts)
    passed = sum(1 for r in receipts if r.get("status") == "PASS")
    severity: dict[str, int] = {}
    for receipt in receipts:
        if receipt.get("status") == "FAIL":
            sev = findings_mod.describe(receipt.get("category"), receipt.get("family"))["severity"]
            severity[sev] = severity.get(sev, 0) + 1
    return {
        "total": total,
        "passed": passed,
        "failed": total - passed,
        "groundedness_rate": round(passed / total, 4) if total else None,
        "severity_counts": dict(sorted(severity.items(), key=lambda kv: findings_mod.severity_rank(kv[0]))),
    }


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Bulk-ingest answers from JSONL or CSV.")
    parser.add_argument("file", help="path to a .jsonl or .csv batch of answers")
    parser.add_argument("--tenant", required=True, help="tenant id to seal into")
    parser.add_argument("--data-root", default="product/data", help="storage root (default: product/data)")
    parser.add_argument("--rule-pack", default=DEFAULT_RULE_PACK, help="default rule pack for rows that don't set one")
    parser.add_argument("--format", default="auto", choices=["auto", "jsonl", "csv"])
    parser.add_argument("--packs-dir", default=None)
    args = parser.parse_args(argv)

    try:
        store, result = ingest_file(
            args.file, tenant=args.tenant, data_root=args.data_root,
            default_rule_pack=args.rule_pack, fmt=args.format, packs_dir=args.packs_dir,
        )
    except (FileNotFoundError, ValueError) as exc:
        print(f"ingest failed: {exc}")
        return 2

    summary = result["summary"]
    rate = summary["groundedness_rate"]
    print(f"GroundLedger ingest - tenant {store.tenant!r}")
    print("=" * 56)
    print(f"source           : {args.file}")
    print(f"ingested         : {result['ingested']}")
    print(f"skipped (existing): {result['skipped']}")
    print(f"errors           : {len(result['errors'])}")
    if summary["total"]:
        rate_txt = f"{rate * 100:.0f}%" if rate is not None else "n/a"
        sev = ", ".join(f"{n} {s}" for s, n in summary["severity_counts"].items()) or "none"
        print(f"grounded         : {summary['passed']}/{summary['total']} ({rate_txt})")
        print(f"findings         : {sev}")
    for err in result["errors"]:
        print(f"  ! {err['ref']} ({err.get('answer_id')}): {err['error']}")
    print("=" * 56)
    if result["errors"]:
        print("final status: INGESTED WITH ERRORS (good rows were sealed; fix and re-run - duplicates are skipped)")
        return 1
    print("final status: OK")
    return 0


if __name__ == "__main__":
    sys.exit(_main())
