# Checkpoint — AutoLab Item 1: Frozen-zone manifest + enforcement

Scope: path manifest, deterministic zone-hash attestation, and a CI check that
fails any diff into the frozen zone absent a human amendment token.

## Deliverables

- `autolab/frozen_zone.py` — attestation + amendment-gate library (stdlib-only,
  standalone, itself frozen).
- `autolab/frozen_manifest.json` — the sealed path manifest (frozen; lists 12
  paths; `zone_hash = e0c98d37…828e662`).
- `frozen_zone_check.py` — CLI: `check` (default), `attest`, `seal`, `--ci`,
  `--base`, `--amendment-token` (frozen).
- `autolab/amendments/` — human-only amendment channel (not frozen) with schema
  docs.
- `tests/test_frozen_zone.py` — 18 deterministic tests.
- CI: `fetch-depth: 0` + a `frozen_zone_check.py --ci` step; attestation added to
  `verify_all.py`.
- `docs/autolab-frozen-zone.md`.

## Acceptance criteria

- **Attempted zone-touch fixture fails CI.** Proven two ways:
  `test_cli_attestation_fails_on_tampered_zone` (real CLI, exit 2 on a drifted
  frozen file) and `test_touching_frozen_file_without_token_fails` (real temp git
  repo: a frozen file changed + resealed still fails the amendment gate without a
  token).
- **Attestation determinism test.** `test_zone_hash_is_deterministic_and_order_
  independent`, `test_seal_is_idempotent`, `test_manifest_digest_ignores_its_own_
  seal_fields`, and `test_sealed_manifest_matches_frozen_files` on the real repo.

## The six hard invariants — explicit accounting

1. **Frozen zone.** *This item implements it.* Path manifest + pre/post zone-hash
   attestation, checked deterministically in CI. The zone protects itself (the
   manifest, the enforcement library, and the CI command are all frozen). Changes
   flow only through the human-only amendment channel with a token the loop
   cannot set. The verifier, gate, ledger, invariant suite, holdout commitment,
   and seed machinery are all listed frozen. ✔ Enforced.

2. **Asymmetric gate.** Untouched and not weakened. The frozen-zone check can
   only **reject** (exit 2) or pass; it grants no promotion. It adds a new veto,
   consistent with "the gate may only reject." No autonomous promotion path is
   introduced. ✔ Respected.

3. **Builder cannot attest.** The attestation and zone hash are computed by this
   frozen tooling from raw file bytes — never from builder-supplied metadata.
   Amendment records are advisory provenance for humans; the gate's decision is a
   pure function of file content, the sealed manifest, and the token's match to a
   record. No builder rationale enters the verdict. ✔ Respected.

4. **Append-only lineage.** The amendment channel is append-only by convention
   (one record per authorized transition, each binding `prev_zone_hash ->
   new_zone_hash`), mirroring the ledger's hash-chain discipline. The full
   meta-ledger and human ratification are implemented by Items 3 and 4; this
   item laid the amendment-record substrate without claiming them. Consistent.

5. **Budgeted holdout.** Not exercised here, and not weakened: the holdout
   pre-registration commitment is *added to the frozen zone*, so its sealed
   hashes can no longer be silently edited. No holdout data is exposed. ✔
   Respected (strengthened).

6. **Determinism and offline CI.** The attestation is a pure function of file
   bytes; no wall-clock, network, model, or randomness. `seal` is idempotent.
   The git amendment gate is deterministic given a base ref and degrades to
   attestation-only when git/base is absent (e.g., inside `verify_all.py`'s
   isolated copy). All 18 tests and the full offline suite pass with no live
   calls. ✔ Enforced.

## Verification run

- `python -m unittest discover -s tests` → 45 tests OK (18 new).
- `python verify_all.py` → 18/18 PASS (includes `frozen_zone_check.py`).
- `python release_gate.py --ci` → PASS (run post-commit; no protected-path or
  version drift; frozen files unchanged; version of record stays `v1.1.0`).
- `python frozen_zone_check.py --base origin/main` → PASS (genesis; base has no
  manifest).

## Conflicts encountered

None. No invariant had to be bent. The zone was scoped to verdict logic and
integrity machinery only, leaving the improvable scaffold free — which is the
intended surface for AutoLab.

## Not in this item

Version-of-record stays `v1.1.0` (the version bump is proposed in the final PR).
The AutoLab controller path is added by the Item 3 amendment (`fz-v0.3.0-add-controller`); the human ratification path is added by Item 4 (`fz-v0.4.0-add-ratification`); the lineage and rollback guard is added by Item 5 (`fz-v0.5.0-add-lineage-rollback`); the circuit-breaker restart guard is added by Item 6 (`fz-v0.6.0-add-circuit-breakers`); the end-to-end runner is added by Item 7 (`fz-v0.7.0-add-runner`).
