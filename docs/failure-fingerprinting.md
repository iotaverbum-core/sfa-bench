# Failure Fingerprinting

SFA-Bench v0.8 can compute a sealed, replayable failure-family fingerprint for
model-labelled transcript fixtures under a fixed evidence pack and fixed
prompt/adapter conditions.

Failure fingerprints describe the distribution of observed failure families
under a fixed pack, prompt condition, and taxonomy. They do not describe
absolute model behaviour.

## Derivation

`fingerprint_report.py` performs this offline pipeline:

1. Load the clearly illustrative fixture set from
   `examples/fingerprints/demo_pack/fixture_set.json`.
2. Confirm the evidence-pack, case-set, prompt, adapter, and taxonomy condition
   metadata.
3. Normalize exactly one JSON candidate from every local transcript fixture.
4. Pass only input, evidence, normalized candidate, and verifier rules to the
   unchanged verifier.
5. Seal a reporting occurrence with its model identity, outcome, family,
   condition metadata, transcript hash, candidate hash, verifier-input hash,
   verdict hash, and occurrence hash.
6. Aggregate attempts, pass/fail counts, pass rate, family counts and rates,
   dominant family, and recurrence summary by `model_id`.
7. Compare fixture, condition, fingerprint-input, report, and model-summary
   hashes with `expected_fingerprint.json`.

The derivation has no timestamps generated at runtime, API keys, provider
calls, network access, or live adapter use. Re-running it with the same sealed
inputs produces the same output.

## Interpretation boundary

The demo IDs `fixture-model-a`, `fixture-model-b`, and `fixture-model-c` are
fake. For example, fixture-model-a's illustrative failures in this demo are
dominated by `fabricated_entity`. This is a statement about this fixture set
under its fixed conditions, not a real-world model ranking or general claim.

Comparison is refused when the evidence pack, case set, prompt condition,
adapter condition, or taxonomy differs. Legacy occurrence data with no
`model_id` remains valid and is grouped as `unknown`; existing history is not
rewritten.

## Trust boundary

Fingerprinting is reporting over sealed occurrences. It cannot affect verifier
judgment. The verifier never receives model identity, provider or adapter
identity, prompt or raw transcript, sampling parameters, recurrence data,
fingerprint summaries, prior failures, warnings, cautions, or policy decisions.

The tamper suite mutates temporary copies to confirm that model reassignment and
dropped occurrences change the sealed fingerprint inputs. The invariant suite
confirms verifier blindness, repeatable derivation, and fixed-condition
comparison refusal.
