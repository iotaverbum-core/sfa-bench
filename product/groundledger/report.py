"""Audit report generation.

Produces the artifact a customer hands to their own buyer, auditor, or regulator:
a groundedness summary over the sealed ledger, a failure-family breakdown, the
independent attestation result, and the exact command to reproduce it.
"""
from __future__ import annotations

from typing import Any

from . import replay
from .store import TenantStore

REPORT_SCHEMA = "groundledger.audit_report.v1"


def build_report(store: TenantStore, *, packs_dir: str | None = None) -> dict[str, Any]:
    receipts = store.list_receipts()
    total = len(receipts)
    passes = sum(1 for r in receipts if r.get("status") == "PASS")
    failures = total - passes

    family_counts: dict[str, int] = {}
    category_counts: dict[str, int] = {}
    for r in receipts:
        if r.get("status") == "FAIL":
            fam = r.get("family") or "uncategorized"
            cat = r.get("category") or "uncategorized"
            family_counts[fam] = family_counts.get(fam, 0) + 1
            category_counts[cat] = category_counts.get(cat, 0) + 1

    resolver = None
    if packs_dir is not None:
        from . import rulepacks

        resolver = (lambda pid: rulepacks.load_rule_pack(pid, packs_dir=packs_dir))
    attestation = replay.attest(store, resolver)

    return {
        "schema": REPORT_SCHEMA,
        "tenant": store.tenant,
        "answers_verified": total,
        "grounded": passes,
        "not_grounded": failures,
        "groundedness_rate": round(passes / total, 4) if total else None,
        "failure_families": dict(sorted(family_counts.items())),
        "failure_categories": dict(sorted(category_counts.items())),
        "attestation": {
            "attested": attestation["attested"],
            "entries_checked": attestation["entries_checked"],
            "chain_ok": attestation["chain_ok"],
            "issues": attestation["issues"],
        },
        "reproduce_command": f"python -m product.groundledger.replay <data_root> {store.tenant}",
    }


def render_text(report: dict[str, Any]) -> str:
    lines = [
        f"# GroundLedger audit report - tenant {report['tenant']!r}",
        "",
        f"Answers verified : {report['answers_verified']}",
        f"Grounded (PASS)  : {report['grounded']}",
        f"Not grounded     : {report['not_grounded']}",
    ]
    if report["groundedness_rate"] is not None:
        lines.append(f"Groundedness rate: {report['groundedness_rate'] * 100:.1f}%")
    lines.append("")
    if report["failure_families"]:
        lines.append("Failure families:")
        for fam, n in report["failure_families"].items():
            lines.append(f"  - {fam}: {n}")
        lines.append("")
    att = report["attestation"]
    lines.append(f"Independent attestation: {'ATTESTED' if att['attested'] else 'TAMPER DETECTED'}")
    lines.append(f"  entries checked: {att['entries_checked']}")
    lines.append(f"  ledger chain ok: {'yes' if att['chain_ok'] else 'no'}")
    for issue in att["issues"]:
        ref = issue.get("answer_id", issue.get("seq"))
        lines.append(f"  - [{issue['code']}] {ref}: {issue['detail']}")
    lines.append("")
    lines.append(f"Reproduce: {report['reproduce_command']}")
    return "\n".join(lines)
