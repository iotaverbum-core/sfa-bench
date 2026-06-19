# SFA-Bench v0.7 Verifier Invariants

`invariant_suite.py` protects the verifier's history-blindness and adapter
airlock boundaries.

These invariants are a continuing spine for the architecture, not a completed
one-time rung. Every future layer must preserve the same boundary.

The suite proves these properties:

1. `sfa/verifier.py` does not import or reference history-adjacent or
   adapter-adjacent symbols.
2. Fixed `input`, `evidence`, `candidate`, and `rules` produce identical
   verifier output whether the surrounding working directory has no history
   files or is populated with ambient history-like files.
3. Transcript metadata, prompt text, raw response wrappers, model id, provider,
   and parameters do not affect verifier judgment when two transcripts normalize
   to byte-identical candidates.
4. The adapter airlock holds: adapter output is transcript-shaped raw source,
   the normalizer receives the transcript, and the verifier receives the
   normalized candidate only.
5. Adapter/model metadata blindness holds: two transcripts with different
   adapter and model metadata normalize to the same candidate and produce the
   same verifier output.
6. With `CI=true`, live adapters cannot be listed, selected, enabled, or
   invoked through the registry.
7. Verifier call-site arguments exclude raw transcript, provenance, warning,
   adapter state, and model metadata fields.

The dynamic check runs:

- a PASS candidate from `cases/case_001_grounded_pass`
- a FAIL candidate from `cases/case_002_contradicts_evidence`
- a normalization-isolation pair that differs in transcript metadata but
  normalizes to the same candidate bytes
- an adapter-airlock case using the offline fixture adapter
- an adapter metadata differential using different adapter/provider/model
  metadata
- CI live-adapter unreachability checks

Run it directly:

```bash
python invariant_suite.py
```

This suite is intentionally separate from verifier behavior. It must fail before
any verifier change is made to justify touching `sfa/verifier.py`.

Warnings, prior-attempt context, provenance, adapter metadata, and future policy
guidance may shape generator prompts only. They must never shape verifier
judgment.
