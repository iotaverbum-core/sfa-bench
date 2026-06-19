# SFA-Bench v0.6 Verifier Invariants

`invariant_suite.py` protects the verifier's history-blindness boundary.

These invariants are a continuing spine for the architecture, not a completed
one-time rung. Every future layer must preserve the same boundary.

The suite proves four properties:

1. `sfa/verifier.py` does not import or reference history-adjacent symbols:
   `history`, `ledger`, `artifacts`, `agent_runs`, `provenance`, `warnings`,
   `agent`, or `model_adapter`.
2. Fixed `input`, `evidence`, `candidate`, and `rules` produce identical
   verifier output whether the surrounding working directory has no history
   files or is populated with ambient history-like files.
3. Transcript metadata, prompt text, raw response wrappers, model id, provider,
   and parameters do not affect verifier judgment when two transcripts normalize
   to byte-identical candidates.
4. Verifier call-site arguments exclude raw transcript, provenance, warning,
   and model metadata fields.

The dynamic check runs two fixtures:

- a PASS candidate from `cases/case_001_grounded_pass`
- a FAIL candidate from `cases/case_002_contradicts_evidence`
- a normalization-isolation pair that differs in transcript metadata but
  normalizes to the same candidate bytes

Run it directly:

```bash
python invariant_suite.py
```

This suite is intentionally separate from verifier behavior. It must fail before
any verifier change is made to justify touching `sfa/verifier.py`.

Warnings, prior-attempt context, provenance, and future policy guidance may
shape generator prompts only. They must never shape verifier judgment.
