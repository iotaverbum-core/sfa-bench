# AutoLab Frozen Zone (Item 1)

SFA-AutoLab lets a *builder* propose patches to this repository, has *frozen
evaluators* verify them, and promotes only by explicit human ratification. For
that to mean anything, the parts that decide, measure, and record must be
**unpatchable by the loop**. This is the frozen zone and its enforcement.

This is scaffold-level self-improvement, not an autonomous agent editing its own
judge. The frozen zone is the boundary that keeps the distinction honest.

## What is frozen (v0.3.0)

The manifest (`autolab/frozen_manifest.json`) declares the frozen paths. v0.3.0:

| Path | Why it is frozen |
| --- | --- |
| `sfa/verifier.py` | verifier verdict logic |
| `sfa/categories.py` | verifier verdict logic (failure categories) |
| `sfa/ledger.py` | append-only ledger code |
| `sfa/hashing.py` | canonical hashing under the ledger + all attestation/sealing |
| `sfa/invariants.py` | invariant suite implementation |
| `invariant_suite.py` | invariant suite runner |
| `release_gate.py` | gate policy |
| `seed_history.py` | seed schedule machinery |
| `holdout/frontier-delta-holdout_hd-v0.1.0_PREREGISTRATION.md` | holdout access machinery (sealed public commitment) |
| `autolab/frozen_zone.py` | frozen-zone enforcement (self-protecting) |
| `autolab/preregistration.py` | gate policy (pre-registration declaration + asymmetric gate) |
| `autolab/controller.py` | controller, meta-ledger, and holdout budget guard |
| `autolab/frozen_manifest.json` | frozen-zone manifest (self-protecting) |
| `frozen_zone_check.py` | frozen-zone CI check (self-protecting) |

The zone is intentionally tight: it covers verdict logic and integrity machinery,
not the improvable scaffold (task families, taxonomy tree, metrics, generators,
docs). Over-freezing would defeat the point of AutoLab. The taxonomy tree
(`families.json`) stays improvable; it keeps its own release-gate protection.

## Two enforcement mechanisms

Both are deterministic and offline.

### 1. Zone-hash attestation (git-free)

The manifest records `zone_hash`: a SHA-256 over the sorted `(relpath, digest)`
pairs of every frozen file. Per-file `file_digests` are recorded for diagnostics.
The manifest's own digest is taken over its JSON with the self-referential
`zone_hash` and `file_digests` keys removed — that breaks the "a file that hashes
itself" circularity and makes the digest independent of formatting.

CI recomputes the zone hash and compares. **Any content drift in a frozen file
that does not also reseal the manifest fails closed.** This is what the loop
controller uses for pre/post attestation: hash the zone before an iteration and
after, and assert equality — the loop must not have touched the zone.

```bash
python frozen_zone_check.py          # attestation (+ gate if a base is detected)
python frozen_zone_check.py attest   # print the attestation JSON
```

### 2. Amendment gate (git-based, PR-level)

Attestation alone cannot catch a change that *also* reseals the manifest (a
self-consistent manifest always attests). The amendment gate closes that gap. It
diffs the PR against a trusted base ref and, if any file **frozen as of the base**
changed — or the manifest's zone definition changed — it **requires a human
amendment token**:

```bash
python frozen_zone_check.py --ci                 # uses origin/$GITHUB_BASE_REF
python frozen_zone_check.py --base origin/main --amendment-token <TOKEN>
```

The token (`SFA_FROZEN_ZONE_AMENDMENT_TOKEN`) is an **out-of-loop human
authority**: a protected CI input the automated builder cannot set. A valid token
must match an append-only amendment record whose `new_zone_hash` equals both the
current computed zone hash and the sealed manifest `zone_hash`, and whose
`prev_zone_hash` equals the base's sealed `zone_hash`. This binds one human
authorization to exactly one `prev -> new` transition.

When PR CI cannot receive the protected input, `frozen_zone_check.py --ci` may
infer the token only from a checked-in amendment record that already binds the
trusted base zone hash to the current sealed zone hash. The lower-level
amendment gate still validates the same token/record/hash binding; no unmatched
or future frozen-zone transition is authorized by this fallback.

If the base has no frozen manifest (genesis), the gate passes — you cannot
violate a zone that did not yet exist.

## Honest limits

The code cannot cryptographically stop a sufficiently privileged actor from
rewriting both a frozen file and the manifest in one commit. That is *why* the
amendment token exists (the human channel), why the zone includes its own
enforcement code so tampering with the check is itself a zone change, and why CI
runs the gate against a trusted base. The guarantee is: **no green CI path exists
that mutates the zone without a human token committed through the amendment
channel.**

## The human amendment workflow

To legitimately change the zone (e.g., add the AutoLab controller in Item 3):

1. Edit the frozen file(s) and/or `frozen_paths`.
2. Reseal: `python frozen_zone_check.py seal`.
3. Add `autolab/amendments/<amendment_id>.json` recording the
   `prev_zone_hash -> new_zone_hash` transition (schema
   `sfa.autolab.frozen_zone.amendment.v0`; see `autolab/amendments/README.md`).
4. Supply the token to CI via the protected `SFA_FROZEN_ZONE_AMENDMENT_TOKEN`.

`seal` is human tooling and refuses to run under `--ci`.

## Where it runs

- `tests/test_frozen_zone.py` — attestation determinism, zone-touch failure, the
  amendment gate with/without a token, genesis, and a check that the real
  repository's sealed manifest matches its frozen files. Run by the CI `frontier`
  job's `unittest discover`.
- `frozen_zone_check.py --ci` — a dedicated CI enforcement step.
- `verify_all.py` — attestation runs as part of the standing offline suite.
