# Verifier Invariants

`invariant_suite.py` protects the verifier's history-blindness boundary.

The suite proves two properties:

1. `sfa/verifier.py` does not import or reference history-adjacent symbols:
   `history`, `ledger`, `artifacts`, `agent_runs`, `provenance`, `warnings`,
   `agent`, or `model_adapter`.
2. Fixed `input`, `evidence`, `candidate`, and `rules` produce identical
   verifier output whether the surrounding working directory has no history
   files or is populated with ambient history-like files.

The dynamic check runs two fixtures:

- a PASS candidate from `cases/case_001_grounded_pass`
- a FAIL candidate from `cases/case_002_contradicts_evidence`

Run it directly:

```bash
python invariant_suite.py
```

This suite is intentionally separate from verifier behavior. It must fail before
any verifier change is made to justify touching `sfa/verifier.py`.
