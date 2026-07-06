#!/usr/bin/env python3
"""SFA-Bench v1.1.0 frozen-zone check (SFA-AutoLab v0, Item 1).

FROZEN ZONE — this command is itself listed in ``autolab/frozen_manifest.json``.

Usage:

    python frozen_zone_check.py            # attestation (+ gate if base detected)
    python frozen_zone_check.py --ci       # CI enforcement (attestation + gate)
    python frozen_zone_check.py --base origin/main [--amendment-token TOK]
    python frozen_zone_check.py attest     # print the current attestation JSON
    python frozen_zone_check.py seal       # human tool: (re)seal the manifest hash

Deterministic and offline. ``seal`` is human amendment tooling and is refused
under ``--ci``. See docs/autolab-frozen-zone.md.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from autolab import frozen_zone as fz

ROOT = Path(__file__).resolve().parent


def _print_header() -> None:
    print("# SFA-Bench v1.1.0 frozen-zone check")
    print("=" * 56)


def _report(result: fz.CheckResult, *, mode: str) -> None:
    att = result.attestation
    print(f"manifest version: {att.manifest_version}")
    print(f"frozen files: {att.file_count}")
    print(f"recorded zone hash: {att.recorded_zone_hash}")
    print(f"computed zone hash: {att.zone_hash}")
    print(f"attestation: {'PASS' if result.attestation_ok else 'FAIL'}")
    for issue in result.attestation_issues:
        print(f"  - {issue}")
    if result.gate is None:
        print("amendment gate: not run (no base ref)")
    else:
        gate = result.gate
        print(f"amendment gate base: {gate.base_ref}")
        if gate.genesis:
            print("amendment gate: PASS (genesis; base has no frozen manifest)")
        elif not gate.requires_amendment:
            print("amendment gate: PASS (no change to files frozen as of base)")
        else:
            print(f"amendment gate: {'PASS' if gate.ok else 'FAIL'}")
            if gate.touched:
                print(f"  frozen files touched: {', '.join(gate.touched)}")
            if gate.manifest_zone_altered:
                print("  manifest zone definition altered")
            for issue in gate.issues:
                print(f"  - {issue}")
        for note in gate.notes:
            print(f"  note: {note}")
    print(f"mode: {mode}")
    print("=" * 56)
    print(f"final status: {'PASS' if result.ok else 'FAIL'}")


def _cmd_seal(args: argparse.Namespace) -> int:
    if args.ci:
        print("refusing to seal under --ci: sealing is a human amendment operation")
        return 2
    before = fz.load_manifest(ROOT)
    manifest = fz.seal(ROOT)
    changed = before.get(fz.ZONE_HASH_KEY) != manifest[fz.ZONE_HASH_KEY]
    _print_header()
    print(f"manifest version: {manifest['manifest_version']}")
    print(f"frozen files: {len(manifest[fz.FILE_DIGESTS_KEY]) + 1}")
    print(f"sealed zone hash: {manifest[fz.ZONE_HASH_KEY]}")
    print(f"zone hash changed by seal: {'yes' if changed else 'no'}")
    print("=" * 56)
    print("final status: SEALED")
    return 0


def _cmd_attest(args: argparse.Namespace) -> int:
    attestation = fz.attest(ROOT)
    print(json.dumps(attestation.to_dict(), indent=2, sort_keys=True))
    return 0 if attestation.matches else 2


def _cmd_check(args: argparse.Namespace) -> int:
    base_ref = fz.resolve_base_ref(args.base)
    token = fz.resolve_amendment_token(args.amendment_token)
    # Only consult git for the gate when a base is known and git is present.
    if base_ref is not None and not fz.git_available(ROOT):
        base_ref = None
    try:
        result = fz.check(ROOT, base_ref=base_ref, amendment_token=token)
    except fz.FrozenZoneError as exc:
        _print_header()
        print(f"failure: {exc}")
        print("=" * 56)
        print("final status: FAIL")
        return 2
    _print_header()
    _report(result, mode="ci" if args.ci else "local")
    return 0 if result.ok else 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", nargs="?", default="check",
                        choices=["check", "attest", "seal"],
                        help="check (default), attest, or seal")
    parser.add_argument("--ci", action="store_true",
                        help="identify the check as the offline CI gate")
    parser.add_argument("--base", metavar="REF",
                        help="base ref for the amendment gate (default: $GITHUB_BASE_REF)")
    parser.add_argument("--amendment-token", metavar="TOKEN",
                        help=f"human amendment token (default: ${fz.AMENDMENT_TOKEN_ENV})")
    args = parser.parse_args(argv)

    if args.command == "seal":
        return _cmd_seal(args)
    if args.command == "attest":
        return _cmd_attest(args)
    return _cmd_check(args)


if __name__ == "__main__":
    sys.exit(main())
