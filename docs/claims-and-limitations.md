# Claims and Limitations

This document defines the interpretation boundary for SFA-Bench v1.0.0. Claims
apply to the checked-in implementation, fixtures, and explicit test conditions.

## Supported claims

- Artifacts are tamper-evident under the implemented canonical hashing, sealing,
  and consistency checks.
- Replay attests sealed artifacts and the occurrence-ledger hash chain against
  the records and source fixtures available to the replay process.
- Supported transcript verdicts can be re-derived deterministically from sealed
  normalized inputs.
- The verifier is tested for history-blindness, expected-verdict isolation,
  transcript metadata isolation, and adapter metadata isolation.
- CI and the canonical full verification command remain offline and require no
  provider secrets, model calls, network calls, or live adapters.
- Fixture fingerprinting is deterministic under fixed case, evidence, prompt,
  adapter, transcript, taxonomy, and implementation conditions.
- Policy decisions are deterministic and generator-side. Policy output may
  guide a subsequent proposal but is excluded from verifier judgment.
- The covered tamper and contamination cases are detected or rejected by the
  corresponding implemented checks.

## Unsupported claims

- Real-world model rankings or comparative provider quality.
- Production live-provider benchmarking or production integration readiness.
- Absolute or population-level claims about model behaviour based on fixture
  labels or fixture outcomes.
- Proof that a model improves because generator-side policy guidance is used.
- Proof that all possible tampering is impossible or detectable.
- Cryptographic or security guarantees beyond the implemented hash, seal,
  ledger, replay, and mutation checks.
- Claims about the correctness, faithfulness, or availability of hidden
  chain-of-thought.
- Claims that the rule-based verifier is semantically complete or suitable for
  arbitrary domains.
- Claims that human evaluation is unnecessary.

## Qualification of key terms

“Tamper-evident” means that specified changes cause an implemented integrity or
consistency check to fail. It does not mean tamper-proof.

“Replay” means deterministic re-attestation using the available sealed record,
case material, taxonomy, and verifier implementation. It does not recreate a
historical model execution.

“Fingerprint” means an aggregate over illustrative, fixed-condition fixtures. It
is not an intrinsic identity or stable universal property of a model.

“Policy-guided retry” means a deterministic generator-side directive selected
from sealed recurrence data. The repository does not demonstrate causal model
improvement and does not allow policy data into verifier judgment.

## Scope changes

Any future change to verifier behaviour, taxonomy, provider execution, fixture
provenance, or security assumptions requires a new claim review. v1.0.0 changes
none of those boundaries; it adds reproducibility and documentation hardening.
