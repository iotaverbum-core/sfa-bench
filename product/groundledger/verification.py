"""Reproducibility + tamper verification for GroundLedger.

A skeptical stranger runs `python -m product.groundledger.verification`
(or `make verify`, or `groundledger verify`) and the tool proves, on committed
fixtures and with no network or model calls:

  1. Reproducibility - re-deriving the verdicts, the audit report, and the signed
     export bundle from the committed example answers yields hashes that match the
     committed expected manifest exactly. Same input + same tool version =>
     byte-identical output.
  2. Tamper detection - a committed, deliberately corrupted bundle is rejected by
     the verifier with an explicit reason.

If you intentionally change the examples, rule pack, or tool version, regenerate
the committed fixtures with `--update` and review the diff before committing.

The signing key below is a published TEST key, not a secret. It exists only so the
committed expected hashes are reproducible by anyone.
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from itertools import count
from pathlib import Path
from typing import Any

import product
from sfa import verifier
from sfa.hashing import sha256_hex

from . import engine, export as export_mod, extraction, report as report_mod, rulepacks
from .store import TenantStore

HERE = Path(__file__).resolve()
REPO_ROOT = HERE.parents[2]
EXAMPLES_DIR = REPO_ROOT / "product" / "examples"
VERIFICATION_DIR = REPO_ROOT / "product" / "verification"
EXPECTED_MANIFEST = VERIFICATION_DIR / "expected_manifest.json"
TAMPERED_BUNDLE = VERIFICATION_DIR / "tampered_bundle.json"

TENANT = "verification"
RULE_PACK_ID = "insurance_v1"
SIGNING_KEY = "groundledger-verification-key"  # published TEST key, not a secret
ORDER = [
    "grounded_answer.json",
    "fabricated_citation.json",
    "contradicts_evidence.json",
    "unsupported_claim.json",
]
MANIFEST_SCHEMA = "groundledger.verification_manifest.v1"


def _fixed_clock():
    counter = count()
    return lambda: f"2026-01-01T00:00:{next(counter):02d}+00:00"


def _load(name: str) -> dict[str, Any]:
    return json.loads((EXAMPLES_DIR / name).read_text(encoding="utf-8"))


def _build_store(data_root: Path) -> tuple[TenantStore, dict[str, Any]]:
    store = TenantStore(data_root, TENANT)
    pack = rulepacks.load_rule_pack(RULE_PACK_ID)
    clock = _fixed_clock()
    for name in ORDER:
        submission = _load(name)
        store.record(submission, engine.verify_submission(submission, pack, now=clock))
    return store, pack


def _signed_bundle(store: TenantStore) -> dict[str, Any]:
    return export_mod.build_export_bundle(store, signing_key=SIGNING_KEY, now=_fixed_clock())


def build_manifest() -> dict[str, Any]:
    """Deterministically derive a hash manifest from the committed examples."""
    store, pack = _build_store(Path(tempfile.mkdtemp()) / "data")
    receipts = {r["answer_id"]: r["receipt_hash"] for r in store.list_receipts()}
    bundle = _signed_bundle(store)
    return {
        "schema": MANIFEST_SCHEMA,
        "tool": {
            "groundledger": product.__version__,
            "verifier": verifier.VERIFIER_VERSION,
            "extractor": extraction.EXTRACTOR_VERSION,
        },
        "rule_pack": {"id": pack["rule_pack_id"], "version": pack["version"]},
        "inputs": {name: sha256_hex(_load(name)) for name in ORDER},
        "receipts": dict(sorted(receipts.items())),
        "groundedness_rate": bundle["report"]["groundedness_rate"],
        "export_hash": bundle["export_hash"],
        "signature": bundle["signature"]["value"],
    }


def run_verification() -> dict[str, Any]:
    issues: list[dict[str, Any]] = []

    if not EXPECTED_MANIFEST.is_file():
        return {"ok": False, "issues": [{"code": "missing_manifest", "detail": str(EXPECTED_MANIFEST)}]}
    expected = json.loads(EXPECTED_MANIFEST.read_text(encoding="utf-8"))
    actual = build_manifest()
    if actual != expected:
        for key in sorted(set(expected) | set(actual)):
            if expected.get(key) != actual.get(key):
                issues.append({"code": "manifest_mismatch", "field": key,
                               "detail": f"expected {expected.get(key)!r} != actual {actual.get(key)!r}"})

    # Self-consistency: a freshly built signed bundle verifies against its key.
    fresh = _signed_bundle(_build_store(Path(tempfile.mkdtemp()) / "data")[0])
    verdict = export_mod.verify_bundle(fresh, signing_key=SIGNING_KEY)
    if not verdict["verified"]:
        issues.append({"code": "bundle_not_reproducible", "detail": str(verdict["issues"])})

    # The committed corrupted bundle must be rejected.
    if not TAMPERED_BUNDLE.is_file():
        issues.append({"code": "missing_tamper_fixture", "detail": str(TAMPERED_BUNDLE)})
    else:
        tampered = json.loads(TAMPERED_BUNDLE.read_text(encoding="utf-8"))
        tv = export_mod.verify_bundle(tampered, signing_key=SIGNING_KEY)
        codes = {i["code"] for i in tv["issues"]}
        if tv["verified"]:
            issues.append({"code": "tamper_not_detected", "detail": "the corrupted bundle passed verification"})
        elif "seal_broken" not in codes:
            issues.append({"code": "tamper_reason_unexpected", "detail": str(sorted(codes))})

    return {"ok": not issues, "issues": issues}


def update_fixtures() -> None:
    VERIFICATION_DIR.mkdir(parents=True, exist_ok=True)
    manifest = build_manifest()
    EXPECTED_MANIFEST.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    bundle = _signed_bundle(_build_store(Path(tempfile.mkdtemp()) / "data")[0])
    for receipt in bundle["receipts"]:
        if receipt["status"] == "FAIL":
            receipt.update({"status": "PASS", "category": None, "family": None, "violations": [],
                            "explanation": "candidate is consistent with evidence under all rules"})
            break
    TAMPERED_BUNDLE.write_text(json.dumps(bundle, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {EXPECTED_MANIFEST.relative_to(REPO_ROOT)}")
    print(f"wrote {TAMPERED_BUNDLE.relative_to(REPO_ROOT)}")


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="GroundLedger reproducibility + tamper verification")
    parser.add_argument("--update", action="store_true", help="regenerate the committed fixtures")
    args = parser.parse_args(argv)

    if args.update:
        update_fixtures()
        return 0

    print("GroundLedger verification (offline, no model calls)")
    print("=" * 56)
    result = run_verification()
    if result["ok"]:
        print("reproducibility : PASS - re-derived hashes match the committed manifest")
        print("tamper detection: PASS - the committed corrupted bundle was rejected")
        print("=" * 56)
        print("final status: VERIFIED")
        return 0
    for issue in result["issues"]:
        ref = issue.get("field", "")
        print(f"  - [{issue['code']}] {ref}: {issue['detail']}")
    print("=" * 56)
    print("final status: FAILED")
    return 2


if __name__ == "__main__":
    sys.exit(_main())
