"""Independent replay / attestation.

Replay re-derives every verdict from the stored submission and re-checks every
seal and the ledger chain. It is the "stranger trust" property: an auditor who
does not trust the operator can run this and confirm that

  * no receipt was edited after sealing (seal integrity),
  * every stored verdict still follows from its submission (re-derivation), and
  * no ledger entry was deleted, inserted, reordered, or edited (chain).

Any tamper surfaces as an explicit issue. Replay reports; it never repairs.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Callable

from . import engine, extraction as extraction_mod, ledger as ledger_mod, rulepacks
from .store import TenantStore

_VERDICT_FIELDS = (
    "status",
    "category",
    "family",
    "input_hash",
    "evidence_hash",
    "candidate_hash",
    "rules_hash",
    "verdict_hash",
)


def attest_records(
    *,
    ledger_entries: list[dict[str, Any]],
    receipts: dict[str, Any],
    submissions: dict[str, Any],
    rule_packs: dict[str, Any],
) -> dict[str, Any]:
    """Filesystem-free attestation over in-memory records.

    ``receipts``/``submissions`` are keyed by ``answer_id`` (value ``None`` means
    the record is missing). ``rule_packs`` is keyed by ``rule_pack_id`` (value
    ``None`` means unavailable). This is the shared core behind both store-based
    attestation and self-contained audit-export verification.
    """
    issues: list[dict[str, Any]] = []
    chain_ok, chain_errors, count = ledger_mod.verify_chain_entries(ledger_entries)
    for seq, detail in chain_errors:
        issues.append({"seq": seq, "code": "ledger_chain_broken", "detail": detail})

    for entry in ledger_entries:
        answer_id = entry.get("answer_id")
        receipt = receipts.get(answer_id)
        submission = submissions.get(answer_id)
        if receipt is None or submission is None:
            issues.append(
                {"answer_id": answer_id, "code": "missing_record",
                 "detail": "receipt or submission not found"}
            )
            continue

        if engine.seal_hash(receipt) != receipt.get("receipt_hash"):
            issues.append(
                {"answer_id": answer_id, "code": "seal_broken",
                 "detail": "receipt content does not match its seal"}
            )
        if entry.get("receipt_hash") != receipt.get("receipt_hash"):
            issues.append(
                {"answer_id": answer_id, "code": "ledger_receipt_mismatch",
                 "detail": "ledger entry points at a different receipt hash"}
            )

        rule_pack = rule_packs.get(receipt.get("rule_pack_id"))
        if rule_pack is None:
            issues.append(
                {"answer_id": answer_id, "code": "rule_pack_unavailable",
                 "detail": f"rule pack {receipt.get('rule_pack_id')!r} not available"}
            )
            continue
        if rule_pack.get("version") != receipt.get("rule_pack_version"):
            issues.append(
                {"answer_id": answer_id, "code": "rule_pack_version_changed",
                 "detail": f"stored {receipt.get('rule_pack_version')!r} "
                           f"!= available {rule_pack.get('version')!r}"}
            )

        rederived = engine.verify_submission(submission, rule_pack)
        mismatched = [f for f in _VERDICT_FIELDS if rederived.get(f) != receipt.get(f)]
        if mismatched:
            issues.append(
                {"answer_id": answer_id, "code": "verdict_mismatch",
                 "detail": "re-derived verdict differs on: " + ", ".join(mismatched)}
            )

        # For text answers, re-run the deterministic extraction and confirm the
        # sealed candidate still follows from the original answer text.
        sealed_extraction = receipt.get("extraction")
        if sealed_extraction and submission.get("answer_text") is not None:
            re_extracted = extraction_mod.extract_candidate(
                submission["answer_text"], submission.get("evidence", {}),
                config=rule_pack.get("extraction"),
            )["provenance"]
            if re_extracted.get("answer_text_hash") != sealed_extraction.get("answer_text_hash"):
                issues.append(
                    {"answer_id": answer_id, "code": "extraction_text_mismatch",
                     "detail": "answer text differs from the sealed extraction"}
                )
            if re_extracted.get("candidate_hash") != sealed_extraction.get("candidate_hash"):
                issues.append(
                    {"answer_id": answer_id, "code": "extraction_mismatch",
                     "detail": "re-extracted candidate differs from the sealed extraction"}
                )

    return {
        "attested": not issues,
        "entries_checked": count,
        "chain_ok": chain_ok,
        "issues": issues,
    }


def attest(
    store: TenantStore,
    resolve_rule_pack: Callable[[str], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Re-derive and re-check every record for one tenant from its store."""
    resolver = resolve_rule_pack or (lambda pack_id: rulepacks.load_rule_pack(pack_id))
    try:
        entries = store.read_ledger()
    except ValueError as exc:
        return {
            "attested": False,
            "tenant": store.tenant,
            "entries_checked": 0,
            "chain_ok": False,
            "issues": [{"seq": -1, "code": "ledger_unreadable", "detail": str(exc)}],
        }

    receipts: dict[str, Any] = {}
    submissions: dict[str, Any] = {}
    for entry in entries:
        answer_id = entry.get("answer_id")
        try:
            receipts[answer_id] = store.read_receipt(answer_id)
        except Exception:  # noqa: BLE001 - surfaced as missing_record
            receipts[answer_id] = None
        try:
            submissions[answer_id] = store.read_submission(answer_id)
        except Exception:  # noqa: BLE001
            submissions[answer_id] = None

    rule_packs: dict[str, Any] = {}
    for receipt in receipts.values():
        if not receipt:
            continue
        pack_id = receipt.get("rule_pack_id")
        if pack_id and pack_id not in rule_packs:
            try:
                rule_packs[pack_id] = resolver(pack_id)
            except Exception:  # noqa: BLE001 - surfaced as rule_pack_unavailable
                rule_packs[pack_id] = None

    result = attest_records(
        ledger_entries=entries,
        receipts=receipts,
        submissions=submissions,
        rule_packs=rule_packs,
    )
    result["tenant"] = store.tenant
    return result


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Independently re-attest a GroundLedger tenant.")
    parser.add_argument("data_root", help="storage root directory")
    parser.add_argument("tenant", help="tenant id")
    parser.add_argument("--packs-dir", default=None, help="rule packs directory override")
    args = parser.parse_args(argv)

    store = TenantStore(args.data_root, args.tenant)
    resolver = (lambda pack_id: rulepacks.load_rule_pack(pack_id, packs_dir=args.packs_dir))
    result = attest(store, resolver)

    print(f"GroundLedger attestation - tenant {result['tenant']!r}")
    print("=" * 56)
    print(f"entries checked: {result['entries_checked']}")
    print(f"ledger chain ok: {'yes' if result['chain_ok'] else 'no'}")
    if result["issues"]:
        print("issues:")
        for issue in result["issues"]:
            ref = issue.get("answer_id", issue.get("seq"))
            print(f"  - [{issue['code']}] {ref}: {issue['detail']}")
    print("=" * 56)
    print(f"final status: {'ATTESTED' if result['attested'] else 'TAMPER DETECTED'}")
    return 0 if result["attested"] else 2


if __name__ == "__main__":
    sys.exit(_main())
