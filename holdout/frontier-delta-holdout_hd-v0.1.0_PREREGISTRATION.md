# Pre-registration — Frontier Delta Holdout `hd-v0.1.0`

This file is a **public, dated commitment** made *before* any model is run on the
holdout. It publishes the sealing hashes **only**. The case prompts
(`prompts/`) and the sealed gold/specs (`sealed/`) are deliberately **withheld**
until post-run disclosure, so that the cases provably could not have been tuned
to any model's results.

## Committed hashes

```
suite              : frontier-delta-holdout
version            : hd-v0.1.0
sealed_date        : 2026-07-04
manifest_sha256    : a7075a36124b398a7003ef7c61b89673180aba2f93f5ea3890d28af22992df49
pack_hash_chained  : 5fa92f6d55e57fd0d913d0b05f0cac9df5a36bb2d2b3fb0886bd8dcba17a604f
```

`manifest_sha256` is the SHA-256 of the sealed `manifest.json`. `pack_hash_chained`
is `SHA-256(case_hash_1 ‖ … ‖ case_hash_8)` over the eight per-case digests, where
`case_hash = SHA-256(prompt_bytes ‖ 0x00 ‖ spec_bytes)`.

## What is committed

- **Eight blinded cases**, one per Frontier Delta lane, authored by Claude Fable 5.
- **Deterministic pure-function scoring**: 67 named binary sub-checks; the scorer
  (`holdout_verify.py`) uses no model, no network, and no randomness. Gold is
  derived programmatically from `engines.py`, which the builder and verifier both
  import (single source of truth).
- **Self-tested** before sealing: 8/8 reference solutions satisfiable; three
  negative fixtures trip exactly their intended failure modes; double verification
  is byte-identical.

## Claim scope (sealed)

**Valid:**
- Candidate-only performance evidence for GPT-5.5 and GPT-5.6 on this
  Fable-5-authored holdout.
- Per-lane failure-mode fingerprints for the models run under the stated protocol.
- Within-holdout comparison between GPT-5.5 and GPT-5.6 (identical cases,
  identical protocol).

**Not valid:**
- Any Fable-5-vs-GPT delta against the public-suite probe (different case sets, and
  the holdout author is one of the compared models).
- Lane-level "clustered weakness" claims (n = 1 per lane).

The case author (Claude Fable 5) is disclosed as a **first-class confound**: case
content is drawn from the authoring model's distribution and its bias direction is
unknown. A *fresh* Claude Fable 5 instance with **no access to the authoring
session** may run the holdout as an optional third arm (cross-instance
contamination is zero by construction).

## Run protocol (summary)

Send each `prompts/hd_00N.txt` verbatim as the sole user message — no system prompt
beyond the provider default, temperature 0 (or provider minimum), one attempt, no
tools, no retries. Save each raw completion byte-for-byte **before** scoring. Score
only after all raws for a model are captured.

## Contamination status

Zero by construction: all case content was authored 2026-07-04 and is unpublished,
post-dating any plausible GPT-5.5/5.6 training cutoff.

## Verifying this pre-registration at disclosure

After all pre-registered runs complete, the full pack (`prompts/`, `sealed/`,
`manifest.json`, and the raw `runs/`) is published. Anyone can then confirm nothing
was altered:

```bash
# 1. the disclosed manifest must hash to the value committed above
python3 -c "import hashlib; print(hashlib.sha256(open('manifest.json','rb').read()).hexdigest())"
#   -> a7075a36124b398a7003ef7c61b89673180aba2f93f5ea3890d28af22992df49

# 2. re-derive the pack hash from the disclosed prompts + specs
python3 seal.py    # prints pack_hash_chained = 5fa92f6d…a17a604f and manifest_sha256 = a7075a36…992df49
```

If either value differs from what is committed here, a file changed after sealing.
At disclosure the pack retires from holdout status — it can no longer be run blind.

---

*This document publishes hashes only. It intentionally contains no prompt or gold
content.*
