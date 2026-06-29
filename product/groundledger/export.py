"""Self-contained, signed audit export.

The export bundle is the artifact a customer hands to their buyer, auditor, or
regulator. It embeds everything needed to reproduce every verdict offline - the
ledger, receipts, submissions, and the exact rule packs used - plus a content
hash and an optional HMAC signature. ``verify_bundle`` re-derives every verdict
from the embedded records with no access to the live system, which is the
"stranger trust" property in portable form.

HMAC is a keyed integrity signature shared between operator and auditor; it is
not public-key PKI. The honest claim is tamper-evidence, not non-repudiation.
"""
from __future__ import annotations

import argparse
import hmac
import json
import sys
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any, Callable

from sfa.hashing import canonical_bytes, sha256_hex

from . import replay, report as report_mod, rulepacks
from .store import TenantStore

EXPORT_SCHEMA = "groundledger.audit_export.v1"


def _strip(bundle: dict[str, Any], *fields: str) -> dict[str, Any]:
    return {k: v for k, v in bundle.items() if k not in fields}


def _hmac_hex(key: str, payload: bytes) -> str:
    return hmac.new(key.encode("utf-8"), payload, sha256).hexdigest()


def build_export_bundle(
    store: TenantStore,
    *,
    packs_dir: str | None = None,
    signing_key: str | None = None,
    now: Callable[[], str] | None = None,
) -> dict[str, Any]:
    """Assemble a portable, self-verifying audit bundle for one tenant."""
    entries = store.read_ledger()
    receipts = [store.read_receipt(e["answer_id"]) for e in entries]
    submissions = [store.read_submission(e["answer_id"]) for e in entries]
    pack_ids = sorted({r["rule_pack_id"] for r in receipts})
    rule_packs = {pid: rulepacks.load_rule_pack(pid, packs_dir=packs_dir) for pid in pack_ids}
    clock = now or (lambda: datetime.now(timezone.utc).isoformat())
    report = report_mod.build_report(store, packs_dir=packs_dir, now=clock)

    bundle: dict[str, Any] = {
        "schema": EXPORT_SCHEMA,
        "tenant": store.tenant,
        "generated_at": clock(),
        "report": report,
        "ledger": entries,
        "receipts": receipts,
        "submissions": submissions,
        "rule_packs": rule_packs,
        "reproduce_command": "python -m product.groundledger.export verify <bundle.json>",
    }
    bundle["export_hash"] = sha256_hex(_strip(bundle, "export_hash", "signature"))
    if signing_key:
        bundle["signature"] = {
            "alg": "HMAC-SHA256",
            "value": _hmac_hex(signing_key, canonical_bytes(_strip(bundle, "signature"))),
        }
    return bundle


def verify_bundle(bundle: dict[str, Any], *, signing_key: str | None = None) -> dict[str, Any]:
    """Re-verify an export bundle offline using only its embedded records."""
    issues: list[dict[str, Any]] = []

    if bundle.get("schema") != EXPORT_SCHEMA:
        issues.append({"code": "unsupported_schema", "detail": str(bundle.get("schema"))})

    recomputed = sha256_hex(_strip(bundle, "export_hash", "signature"))
    if recomputed != bundle.get("export_hash"):
        issues.append({"code": "export_hash_mismatch", "detail": "bundle content was edited"})

    signature_checked = signing_key is not None
    if signature_checked:
        signature = bundle.get("signature")
        if not isinstance(signature, dict) or "value" not in signature:
            issues.append({"code": "signature_missing", "detail": "bundle is not signed"})
        else:
            expected = _hmac_hex(signing_key, canonical_bytes(_strip(bundle, "signature")))
            if not hmac.compare_digest(expected, str(signature.get("value", ""))):
                issues.append({"code": "signature_invalid", "detail": "signature does not match key"})

    receipts = {r.get("answer_id"): r for r in bundle.get("receipts", [])}
    submissions = {s.get("answer_id"): s for s in bundle.get("submissions", [])}
    attestation = replay.attest_records(
        ledger_entries=bundle.get("ledger", []),
        receipts=receipts,
        submissions=submissions,
        rule_packs=bundle.get("rule_packs", {}),
    )
    issues.extend(attestation["issues"])

    return {
        "verified": not issues,
        "tenant": bundle.get("tenant"),
        "entries_checked": attestation["entries_checked"],
        "chain_ok": attestation["chain_ok"],
        "signature_checked": signature_checked,
        "issues": issues,
    }


def _esc(value: Any) -> str:
    return (
        str(value)
        .replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
    )


def render_html(bundle: dict[str, Any]) -> str:
    """Printable (print-to-PDF), customer-facing audit report from a bundle."""
    report = bundle.get("report", {})
    verdict = verify_bundle(bundle)
    meta = report.get("metadata", {})
    rate = report.get("groundedness_rate")
    rate_txt = f"{rate * 100:.0f}%" if rate is not None else "n/a"
    status = "VERIFIED" if verdict["verified"] else "TAMPER DETECTED"
    badge = "ok" if verdict["verified"] else "bad"
    packs = ", ".join(f"{k} v{v}" for k, v in meta.get("rule_packs", {}).items()) or "n/a"

    finding_cards = ""
    for f in report.get("findings", []):
        finding_cards += f"""
<div class="finding sev-{_esc(f.get('severity'))}">
  <div class="fhead"><span class="sev">{_esc(f.get('severity','').upper())}</span>
    <span class="ftitle">{_esc(f.get('title'))}</span>
    <span class="muted">· {_esc(f.get('answer_id'))}</span></div>
  {f'<div class="q">Q: {_esc(f.get("question"))}</div>' if f.get('question') else ''}
  {f'<div class="a">Assistant said: “{_esc(f.get("assistant_answer"))}”</div>' if f.get('assistant_answer') else ''}
  <div class="row"><b>What we detected:</b> {_esc(f.get('detected'))} ({_esc(f.get('detection'))})</div>
  <div class="row"><b>Why it matters:</b> {_esc(f.get('why_it_matters'))}</div>
  <div class="row"><b>Recommended action:</b> {_esc(f.get('recommended_action'))}</div>
</div>"""
    if not finding_cards:
        finding_cards = '<p class="muted">No ungrounded answers found in this period.</p>'

    rows = "".join(
        f"<tr><td>{e.get('seq')}</td><td>{_esc(e.get('answer_id'))}</td>"
        f"<td class='{ 'pass' if e.get('status') == 'PASS' else 'fail' }'>{e.get('status')}</td>"
        f"<td>{_esc(e.get('family') or '')}</td><td class='mono'>{_esc((e.get('receipt_hash') or '')[:16])}…</td></tr>"
        for e in bundle.get("ledger", [])
    )

    return f"""<!doctype html><html><head><meta charset="utf-8">
<title>GroundLedger Audit Report — {_esc(bundle.get('tenant'))}</title>
<style>
body{{font:14px/1.55 -apple-system,Segoe UI,Roboto,Arial,sans-serif;color:#0f172a;margin:40px;max-width:860px;}}
h1{{font-size:24px;margin:0 0 2px;}} h3{{margin-top:28px;}} .muted{{color:#64748b;}}
table{{border-collapse:collapse;width:100%;margin-top:8px;}}
th,td{{border-bottom:1px solid #e2e8f0;padding:6px 10px;text-align:left;}}
.mono{{font-family:ui-monospace,Menlo,monospace;font-size:12px;}} .pass{{color:#15803d;}} .fail{{color:#b91c1c;}}
.badge{{display:inline-block;padding:3px 10px;border-radius:8px;font-weight:700;}}
.badge.ok{{background:#dcfce7;color:#15803d;}} .badge.bad{{background:#fee2e2;color:#b91c1c;}}
.box{{background:#f8fafc;border:1px solid #e2e8f0;border-radius:12px;padding:16px;margin-top:14px;}}
.kpi{{font-size:30px;font-weight:800;}}
.finding{{border:1px solid #e2e8f0;border-left-width:6px;border-radius:10px;padding:12px 14px;margin:10px 0;}}
.finding .fhead{{font-size:16px;margin-bottom:6px;}} .ftitle{{font-weight:700;}}
.finding .q,.finding .a{{color:#334155;margin:2px 0;}} .finding .a{{font-style:italic;}}
.finding .row{{margin-top:6px;}} .sev{{font-size:11px;font-weight:800;letter-spacing:.04em;padding:2px 7px;border-radius:6px;color:#fff;}}
.sev-critical{{border-left-color:#b91c1c;}} .sev-critical .sev{{background:#b91c1c;}}
.sev-high{{border-left-color:#c2410c;}} .sev-high .sev{{background:#c2410c;}}
.sev-medium{{border-left-color:#a16207;}} .sev-medium .sev{{background:#a16207;}}
</style></head><body>
<h1>GroundLedger Audit Report</h1>
<div class="muted">Tenant: {_esc(bundle.get('tenant'))} · Generated: {_esc(bundle.get('generated_at'))}
 · Rules: {_esc(packs)} · Verifier: {_esc(meta.get('verifier_version'))}</div>

<div class="box">
  <div class="kpi">{rate_txt} grounded</div>
  <p>{_esc(report.get('summary'))}</p>
  <p>Independent verification of this report:
    <span class="badge {badge}">{status}</span>
    ({verdict['entries_checked']} sealed records, chain {'ok' if verdict['chain_ok'] else 'broken'})</p>
</div>

<h3>What we analysed</h3>
<p class="muted">{report.get('answers_verified')} assistant answers, each checked against the
source evidence it cited, using deterministic groundedness rules. No answer key, history, or
model metadata reaches the verifier.</p>

<h3>Findings</h3>
{finding_cards}

<h3>Sealed ledger</h3>
<table><tr><th>#</th><th>Answer</th><th>Status</th><th>Failure family</th><th>Receipt</th></tr>{rows}</table>

<p class="muted" style="margin-top:22px;">Reproduce this report offline:
<code>python -m product.groundledger.export verify bundle.json</code></p>
</body></html>"""


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build or verify a GroundLedger audit export.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("build", help="build a signed export bundle for a tenant")
    b.add_argument("data_root")
    b.add_argument("tenant")
    b.add_argument("--out", help="write bundle JSON to this path")
    b.add_argument("--html", help="write printable HTML report to this path")
    b.add_argument("--key", default=None, help="HMAC signing key")
    b.add_argument("--packs-dir", default=None)

    v = sub.add_parser("verify", help="verify a bundle offline")
    v.add_argument("bundle")
    v.add_argument("--key", default=None, help="HMAC signing key to check the signature")

    args = parser.parse_args(argv)

    if args.cmd == "build":
        store = TenantStore(args.data_root, args.tenant)
        bundle = build_export_bundle(store, packs_dir=args.packs_dir, signing_key=args.key)
        text = json.dumps(bundle, indent=2, ensure_ascii=False)
        if args.out:
            Path(args.out).write_text(text, encoding="utf-8")
            print(f"wrote {args.out}")
        else:
            print(text)
        if args.html:
            Path(args.html).write_text(render_html(bundle), encoding="utf-8")
            print(f"wrote {args.html}")
        return 0

    bundle = json.loads(Path(args.bundle).read_text(encoding="utf-8"))
    result = verify_bundle(bundle, signing_key=args.key)
    print(f"GroundLedger export verification - tenant {result['tenant']!r}")
    print("=" * 56)
    print(f"entries checked   : {result['entries_checked']}")
    print(f"ledger chain ok   : {'yes' if result['chain_ok'] else 'no'}")
    print(f"signature checked : {'yes' if result['signature_checked'] else 'no'}")
    for issue in result["issues"]:
        ref = issue.get("answer_id", issue.get("seq", "-"))
        print(f"  - [{issue['code']}] {ref}: {issue['detail']}")
    print("=" * 56)
    print(f"final status: {'VERIFIED' if result['verified'] else 'TAMPER DETECTED'}")
    return 0 if result["verified"] else 2


if __name__ == "__main__":
    sys.exit(_main())
