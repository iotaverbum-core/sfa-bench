# SFA-Bench v0.7 Tamper & Contamination Suite

SFA-Bench preserves failure history as sealed artifacts plus an append-only
occurrence ledger. The tamper suite exists to prove that this history cannot be
silently falsified by editing artifacts, laundering case inputs, rewriting the
ledger, drifting taxonomy, or leaking gold labels into the verifier path.

Run it with:

```bash
python tamper_suite.py
```

## What It Tests

The suite creates temporary copies of valid benchmark state, corrupts those
copies, and confirms the read-only validation layer detects the corruption.
The real repository artifacts, cases, taxonomy, and ledger are not mutated.

The checks cover:

- edited sealed artifacts
- edited evidence files
- edited candidate answers
- edited input files
- deleted ledger entries
- reordered ledger entries
- edited ledger entries
- fake lineage parents
- taxonomy drift or missing families
- edited transcript raw source
- edited transcript normalized-candidate replay hash
- live adapter CI guard
- adapter metadata blindness guard
- gold leakage into the verifier path
- hidden repair of failing candidates

## What Corruption Means

In SFA-Bench, corruption is any change that makes the preserved record no longer
match the evidence that produced it.

Examples include:

- changing `failure_explanation` inside a sealed artifact
- changing `input.json`, `evidence.json`, or `candidate_answer.json` after the
  artifact was sealed
- deleting, reordering, or editing a ledger line
- pointing `parent_artifact_id` to a nonexistent artifact
- removing or moving taxonomy families that existing records reference
- making a live adapter reachable in CI
- letting adapter/model metadata alter verifier output
- allowing `expected_verdict.json` to influence verification
- changing a failing candidate so the original failure is not preserved

## Why Temporary Copies

The suite is intentionally destructive, but only inside temporary workspaces.
Each test copies the repository state, performs one corruption, runs validation,
and discards the copy.

This keeps the production failure record append-only and immutable while still
proving that attempted edits would be detected.

## Stranger Trust

The suite supports stranger-trust: a reviewer who did not create the benchmark
can run one command and observe that falsification attempts fail visibly. The
claim is not based on reputation or a hidden service. It is based on local,
deterministic, stdlib-only checks over JSON files.

## Detection Over Repair

SFA-Bench does not repair corrupted history. Repair would create ambiguity about
what happened and when. The trust layer reports mismatches so a human reviewer
can decide how to handle the corrupted copy.

The invariant remains:

```text
Evidence -> verdict -> artifact -> ledger -> replay -> history -> tamper detection
```
