"""Audit report generation.

Produces the artifact a customer hands to their own buyer, auditor, or regulator:
a plain-language groundedness summary, severity-ranked findings with recommended
actions, the failure-family breakdown, the independent attestation result, and
the exact command to reproduce it.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable

from . import findings as findings_mod
from . import replay
from .store import TenantStore

REPORT_SCHEMA = "groundledger.audit_report.v1"


def _plain_summary(total: int, passes: int, severity_counts: dict[str, int], attested: bool) -> str:
    if total == 0:
        return "No answers have been verified yet."
    pct = round(passes / total * 100)
    parts = [f"{passes} of {total} answers ({pct}%) were grounded in the provided evidence."]
    failures = total - passes
    if failures:
        breakdown = ", ".join(f"{n} {sev}" for sev, n in severity_counts.items())
        parts.append(f"{failures} answer(s) were flagged: {breakdown}.")
    parts.append(
        "The audit trail is intact (independently attested)."
        if attested else
        "WARNING: the audit trail failed independent attestation - see findings."
    )
    return " ".join(parts)


def build_report(
    store: TenantStore,
    *,
    packs_dir: str | None = None,
    now: Callable[[], str] | None = None,
) -> dict[str, Any]:
    receipts = store.list_receipts()
    total = len(receipts)
    passes = sum(1 for r in receipts if r.get("status") == "PASS")
    failures = total - passes

    family_counts: dict[str, int] = {}
    category_counts: dict[str, int] = {}
    rule_packs: dict[str, str] = {}
    findings: list[dict[str, Any]] = []

    for receipt in receipts:
        rule_packs[receipt.get("rule_pack_id", "?")] = receipt.get("rule_pack_version", "?")
        if receipt.get("status") != "FAIL":
            continue
        fam = receipt.get("family") or "uncategorized"
        cat = receipt.get("category") or "uncategorized"
        family_counts[fam] = family_counts.get(fam, 0) + 1
        category_counts[cat] = category_counts.get(cat, 0) + 1

        described = findings_mod.describe(receipt.get("category"), receipt.get("family"))
        answer_id = receipt.get("answer_id")
        question, conclusion = "", ""
        try:
            submission = store.read_submission(answer_id)
            question = submission.get("task_input", {}).get("question", "")
            conclusion = submission.get("candidate", {}).get("conclusion", "")
        except Exception:  # noqa: BLE001 - report still renders without the submission
            pass
        findings.append(
            {
                "answer_id": answer_id,
                "question": question,
                "assistant_answer": conclusion,
                "category": receipt.get("category"),
                "family": receipt.get("family"),
                "detected": receipt.get("explanation"),
                "detection": "deterministic rule match",
                "receipt_hash": receipt.get("receipt_hash"),
                **described,
            }
        )

    findings.sort(key=lambda f: (findings_mod.severity_rank(f["severity"]), str(f["answer_id"])))
    severity_counts = findings_mod.summarize_counts(findings)

    resolver = None
    if packs_dir is not None:
        from . import rulepacks

        resolver = (lambda pid: rulepacks.load_rule_pack(pid, packs_dir=packs_dir))
    attestation = replay.attest(store, resolver)
    clock = now or (lambda: datetime.now(timezone.utc).isoformat())

    return {
        "schema": REPORT_SCHEMA,
        "tenant": store.tenant,
        "generated_at": clock(),
        "summary": _plain_summary(total, passes, severity_counts, attestation["attested"]),
        "answers_verified": total,
        "grounded": passes,
        "not_grounded": failures,
        "groundedness_rate": round(passes / total, 4) if total else None,
        "severity_counts": severity_counts,
        "findings": findings,
        "failure_families": dict(sorted(family_counts.items())),
        "failure_categories": dict(sorted(category_counts.items())),
        "metadata": {
            "rule_packs": dict(sorted(rule_packs.items())),
            "verifier_version": receipts[0].get("verifier_version") if receipts else None,
        },
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
        report["summary"],
        "",
        f"Answers verified : {report['answers_verified']}",
        f"Grounded (PASS)  : {report['grounded']}",
        f"Not grounded     : {report['not_grounded']}",
    ]
    if report["groundedness_rate"] is not None:
        lines.append(f"Groundedness rate: {report['groundedness_rate'] * 100:.1f}%")
    if report["findings"]:
        lines.append("")
        lines.append("Findings (highest severity first):")
        for f in report["findings"]:
            lines.append(f"  [{f['severity'].upper()}] {f['title']} - {f['answer_id']}")
            lines.append(f"      detected: {f['detected']}")
            lines.append(f"      action  : {f['recommended_action']}")
    att = report["attestation"]
    lines.append("")
    lines.append(f"Independent attestation: {'ATTESTED' if att['attested'] else 'TAMPER DETECTED'}")
    lines.append(f"  entries checked: {att['entries_checked']}  ledger chain ok: {'yes' if att['chain_ok'] else 'no'}")
    for issue in att["issues"]:
        ref = issue.get("answer_id", issue.get("seq"))
        lines.append(f"  - [{issue['code']}] {ref}: {issue['detail']}")
    lines.append("")
    lines.append(f"Reproduce: {report['reproduce_command']}")
    return "\n".join(lines)
