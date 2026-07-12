"""Deterministic tests for the SFA-AutoLab frozen zone (stdlib unittest only).

Run from the repository root:

    python -m unittest discover -s tests -v

Covers the Item-1 acceptance criteria:
  * attestation determinism (same inputs -> same zone hash; order-independent);
  * an attempted zone-touch fixture fails the check (what CI enforces);
  * the git-based amendment gate rejects a zone change absent a human token and
    accepts it with a valid token + append-only amendment record;
  * the real repository's sealed manifest matches its frozen files.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from autolab import frozen_zone as fz  # noqa: E402

CLI = REPO_ROOT / "frozen_zone_check.py"


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _mini_manifest(frozen_paths: list[str], *, version: str = "fz-test-v0") -> dict:
    return {
        "schema": fz.SCHEMA,
        "manifest_version": version,
        "amendment_channel": fz.AMENDMENT_DIRNAME + "/",
        "frozen_paths": sorted(frozen_paths),
    }


def _build_mini_zone(root: Path) -> dict:
    """Create a minimal, self-consistent frozen zone under ``root`` and seal it."""
    _write(root / "frozen_a.py", "# frozen a\nVALUE = 1\n")
    _write(root / "frozen_b.txt", "frozen b payload\n")
    _write(root / "loose.py", "# not frozen\n")
    manifest = _mini_manifest(
        [fz.MANIFEST_RELPATH, "frozen_a.py", "frozen_b.txt"]
    )
    _write(fz.manifest_path(root), json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return fz.seal(root)


class AttestationDeterminismTests(unittest.TestCase):
    def test_zone_hash_is_deterministic_and_order_independent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _build_mini_zone(root)
            manifest = fz.load_manifest(root)
            h1 = fz.compute_zone_hash(root, manifest)
            h2 = fz.compute_zone_hash(root, manifest)
            self.assertEqual(h1, h2)
            # Order of the digest mapping must not affect the hash.
            digests = fz.compute_digests(root, manifest)
            shuffled = dict(reversed(list(digests.items())))
            self.assertEqual(
                fz.zone_hash_from_digests(digests),
                fz.zone_hash_from_digests(shuffled),
            )

    def test_seal_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sealed = _build_mini_zone(root)
            first = sealed[fz.ZONE_HASH_KEY]
            again = fz.seal(root)
            self.assertEqual(first, again[fz.ZONE_HASH_KEY])
            ok, issues, att = fz.verify_attestation(root)
            self.assertTrue(ok, issues)
            self.assertEqual(att.zone_hash, first)

    def test_manifest_digest_ignores_its_own_seal_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _build_mini_zone(root)
            d_before = fz.compute_file_digest(root, fz.MANIFEST_RELPATH)
            # Rewrite the manifest with different formatting + a stale zone_hash;
            # the self-digest (which excludes zone_hash/file_digests) is unchanged.
            manifest = fz.load_manifest(root)
            manifest[fz.ZONE_HASH_KEY] = "0" * 64
            fz.manifest_path(root).write_text(
                json.dumps(manifest, indent=4), encoding="utf-8"
            )
            d_after = fz.compute_file_digest(root, fz.MANIFEST_RELPATH)
            self.assertEqual(d_before, d_after)


class ZoneTouchTests(unittest.TestCase):
    def test_modifying_a_frozen_file_fails_attestation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _build_mini_zone(root)
            self.assertTrue(fz.verify_attestation(root)[0])
            # Tamper with a frozen file without resealing the manifest.
            (root / "frozen_a.py").write_text("# frozen a\nVALUE = 999\n", encoding="utf-8")
            ok, issues, _ = fz.verify_attestation(root)
            self.assertFalse(ok)
            self.assertTrue(any("zone hash drift" in i for i in issues), issues)
            self.assertTrue(any("frozen_a.py" in i for i in issues), issues)

    def test_removing_a_frozen_file_is_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _build_mini_zone(root)
            (root / "frozen_b.txt").unlink()
            with self.assertRaises(fz.FrozenZoneError):
                fz.verify_attestation(root)

    def test_amendment_channel_may_not_be_frozen(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(root / fz.AMENDMENT_DIRNAME / "x.json", "{}")
            manifest = _mini_manifest([fz.MANIFEST_RELPATH, fz.AMENDMENT_DIRNAME + "/x.json"])
            _write(fz.manifest_path(root), json.dumps(manifest))
            with self.assertRaises(fz.FrozenZoneError):
                fz.compute_zone_hash(root, manifest)

    def test_manifest_must_list_itself(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(root / "frozen_a.py", "x = 1\n")
            manifest = _mini_manifest(["frozen_a.py"])
            _write(fz.manifest_path(root), json.dumps(manifest))
            with self.assertRaises(fz.FrozenZoneError):
                fz.load_manifest(root)

    def test_cli_attestation_fails_on_tampered_zone(self):
        """End-to-end: the real CLI exits non-zero when a frozen file drifts."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            # A self-contained zone that reuses the real enforcement modules.
            (root / "autolab").mkdir()
            for name in ("__init__.py", "frozen_zone.py"):
                (root / "autolab" / name).write_bytes(
                    (REPO_ROOT / "autolab" / name).read_bytes()
                )
            (root / "frozen_zone_check.py").write_bytes(
                (REPO_ROOT / "frozen_zone_check.py").read_bytes()
            )
            _write(root / "guard_a.py", "GUARD = 1\n")
            manifest = _mini_manifest([
                fz.MANIFEST_RELPATH, "autolab/frozen_zone.py",
                "frozen_zone_check.py", "guard_a.py",
            ])
            _write(fz.manifest_path(root), json.dumps(manifest, indent=2) + "\n")
            fz.seal(root)

            env = dict(os.environ, PYTHONPATH=str(root))
            env.pop("GITHUB_BASE_REF", None)
            clean = subprocess.run(
                [sys.executable, "frozen_zone_check.py", "--ci"],
                cwd=root, env=env, text=True, capture_output=True,
            )
            self.assertEqual(clean.returncode, 0, clean.stdout + clean.stderr)
            self.assertIn("final status: PASS", clean.stdout)

            (root / "guard_a.py").write_text("GUARD = 999\n", encoding="utf-8")
            tampered = subprocess.run(
                [sys.executable, "frozen_zone_check.py", "--ci"],
                cwd=root, env=env, text=True, capture_output=True,
            )
            self.assertEqual(tampered.returncode, 2, tampered.stdout + tampered.stderr)
            self.assertIn("final status: FAIL", tampered.stdout)
            self.assertIn("guard_a.py", tampered.stdout)


class AmendmentTokenTests(unittest.TestCase):
    def test_validate_amendment_requires_token(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _build_mini_zone(root)
            ok, issues = fz.validate_amendment(root, None, base_manifest=None)
            self.assertFalse(ok)
            self.assertTrue(any("requires a human amendment token" in i for i in issues))

    def test_valid_amendment_authorizes_transition(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base = _build_mini_zone(root)
            prev_hash = base[fz.ZONE_HASH_KEY]
            # Human amendment: change a frozen file, then reseal.
            (root / "frozen_a.py").write_text("# frozen a\nVALUE = 2\n", encoding="utf-8")
            resealed = fz.seal(root)
            new_hash = resealed[fz.ZONE_HASH_KEY]
            self.assertNotEqual(prev_hash, new_hash)
            token = "amend-0001"
            _write(root / fz.AMENDMENT_DIRNAME / f"{token}.json", json.dumps({
                "schema": fz.AMENDMENT_SCHEMA,
                "amendment_id": token,
                "prev_zone_hash": prev_hash,
                "new_zone_hash": new_hash,
                "reason": "test",
                "author": "tester",
            }))
            base_manifest = _mini_manifest([fz.MANIFEST_RELPATH, "frozen_a.py", "frozen_b.txt"])
            base_manifest[fz.ZONE_HASH_KEY] = prev_hash
            ok, issues = fz.validate_amendment(root, token, base_manifest=base_manifest)
            self.assertTrue(ok, issues)
            # Wrong token -> rejected.
            bad, bad_issues = fz.validate_amendment(root, "nope", base_manifest=base_manifest)
            self.assertFalse(bad)
            self.assertTrue(any("no matching record" in i for i in bad_issues))

    def test_amendment_prev_hash_must_match_base(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _build_mini_zone(root)
            (root / "frozen_a.py").write_text("# frozen a\nVALUE = 3\n", encoding="utf-8")
            resealed = fz.seal(root)
            token = "amend-x"
            _write(root / fz.AMENDMENT_DIRNAME / f"{token}.json", json.dumps({
                "amendment_id": token,
                "prev_zone_hash": "deadbeef",  # wrong
                "new_zone_hash": resealed[fz.ZONE_HASH_KEY],
            }))
            base_manifest = _mini_manifest([fz.MANIFEST_RELPATH, "frozen_a.py", "frozen_b.txt"])
            base_manifest[fz.ZONE_HASH_KEY] = "the-real-base-hash"
            ok, issues = fz.validate_amendment(root, token, base_manifest=base_manifest)
            self.assertFalse(ok)
            self.assertTrue(any("prev_zone_hash" in i for i in issues))


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True)


def _init_git_zone(root: Path) -> dict:
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "t@example.com")
    _git(root, "config", "user.name", "tester")
    _git(root, "config", "commit.gpgsign", "false")
    sealed = _build_mini_zone(root)
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "base zone")
    return sealed


class AmendmentGateTests(unittest.TestCase):
    def test_genesis_base_without_manifest_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _git(root, "init", "-q")
            _git(root, "config", "user.email", "t@example.com")
            _git(root, "config", "user.name", "tester")
            _git(root, "config", "commit.gpgsign", "false")
            _write(root / "readme.txt", "hello\n")
            _git(root, "add", "-A")
            _git(root, "commit", "-q", "-m", "no zone yet")
            base = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, text=True,
                                  capture_output=True).stdout.strip()
            _build_mini_zone(root)  # introduce the zone (genesis)
            _git(root, "add", "-A")
            _git(root, "commit", "-q", "-m", "introduce zone")
            gate = fz.check_amendment_gate(root, base_ref=base, amendment_token=None)
            self.assertTrue(gate.ok, gate.issues)
            self.assertTrue(gate.genesis)

    def test_touching_frozen_file_without_token_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_git_zone(root)
            base = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, text=True,
                                  capture_output=True).stdout.strip()
            (root / "frozen_a.py").write_text("# frozen a\nVALUE = 7\n", encoding="utf-8")
            fz.seal(root)  # reseal so attestation would pass; gate must still fail
            _git(root, "add", "-A")
            _git(root, "commit", "-q", "-m", "loop touches frozen file")
            gate = fz.check_amendment_gate(root, base_ref=base, amendment_token=None)
            self.assertFalse(gate.ok)
            self.assertIn("frozen_a.py", gate.touched)

    def test_touching_frozen_file_with_valid_token_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base_sealed = _init_git_zone(root)
            base = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, text=True,
                                  capture_output=True).stdout.strip()
            prev_hash = base_sealed[fz.ZONE_HASH_KEY]
            (root / "frozen_a.py").write_text("# frozen a\nVALUE = 8\n", encoding="utf-8")
            resealed = fz.seal(root)
            token = "amend-42"
            _write(root / fz.AMENDMENT_DIRNAME / f"{token}.json", json.dumps({
                "schema": fz.AMENDMENT_SCHEMA,
                "amendment_id": token,
                "prev_zone_hash": prev_hash,
                "new_zone_hash": resealed[fz.ZONE_HASH_KEY],
                "reason": "authorized test change",
                "author": "human",
            }))
            _git(root, "add", "-A")
            _git(root, "commit", "-q", "-m", "human amendment")
            gate = fz.check_amendment_gate(root, base_ref=base, amendment_token=token)
            self.assertTrue(gate.ok, gate.issues)

    def test_non_frozen_change_needs_no_token(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_git_zone(root)
            base = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, text=True,
                                  capture_output=True).stdout.strip()
            (root / "loose.py").write_text("# not frozen, edited\n", encoding="utf-8")
            _git(root, "add", "-A")
            _git(root, "commit", "-q", "-m", "edit loose file")
            gate = fz.check_amendment_gate(root, base_ref=base, amendment_token=None)
            self.assertTrue(gate.ok, gate.issues)
            self.assertFalse(gate.requires_amendment)


class RealRepositoryTests(unittest.TestCase):
    def test_sealed_manifest_matches_frozen_files(self):
        ok, issues, att = fz.verify_attestation(REPO_ROOT)
        self.assertTrue(ok, f"frozen zone drifted from its seal: {issues}")
        self.assertEqual(att.zone_hash, att.recorded_zone_hash)

    def test_every_frozen_path_exists(self):
        manifest = fz.load_manifest(REPO_ROOT)
        for rel in manifest["frozen_paths"]:
            self.assertTrue((REPO_ROOT / rel).is_file(), rel)

    def test_manifest_lists_the_enforcement_files(self):
        manifest = fz.load_manifest(REPO_ROOT)
        for required in ("sfa/verifier.py", "sfa/ledger.py", "release_gate.py",
                         "invariant_suite.py", "autolab/frozen_zone.py",
                         "frozen_zone_check.py", fz.MANIFEST_RELPATH):
            self.assertIn(required, manifest["frozen_paths"], required)

    def test_manifest_preserves_provisional_and_corrected_fable_evidence(self):
        manifest = fz.load_manifest(REPO_ROOT)
        required = (
            "out/fable5_failure_delta/raw_outputs.jsonl",
            "out/fable5_failure_delta/scored_results.json",
            "out/candidate_evidence_successors/"
            "fable5-frontier-delta-20260703-corrected-v2-alpha1.json",
        )
        for relative in required:
            self.assertIn(relative, manifest["frozen_paths"], relative)


if __name__ == "__main__":
    unittest.main()
