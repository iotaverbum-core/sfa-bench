# Claims and Limitations

This document defines the interpretation boundary for SFA-Bench
v2.0.0-alpha.2. Claims apply to the checked-in implementation, fixtures,
synthetic adapter, and documented offline verification conditions. No new live
provider campaign occurred, and captured evidence remains unratified.

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
- Empty, refusal-like plaintext, malformed, non-finite, and non-object candidate
  responses are classified before lane canonicalisation and receive zero credit.
- The corrected Fable-5 successor is deterministically re-derived from preserved
  raw evidence and linked to a byte-preserved provisional predecessor. It is not
  a ratified result.
- Campaign pre-registrations and draft candidate manifests are validated
  deterministically without provider access or credentials.
- Benchmark locks bind declared campaign policy, prompt references, and tested
  file classes; the CLI proves bound files match the declared Git commit and
  current release of record without accepting an injected provenance context.
- Alpha.2 lifecycle state is derived from canonical, immutable, hash-chained
  event files and covered illegal/interrupted transitions fail closed.
- Exact request and response-body bytes observed at the synthetic adapter
  boundary round-trip through content-addressed private blobs, including binary
  and non-UTF-8 content.
- Covered duplicate execution/attempt, concurrent writer, partial capture,
  response/manifest/ledger, secret-metadata, and path-safety cases are detected
  or rejected.
- Sealed capture and deterministic judgment are separate offline operations;
  provider, adapter, retry, and authorization metadata have an empty judgment
  projection.
- Deterministic review bundles contain public hashes and warnings, exclude raw
  bodies, and remain explicitly unratified.

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
- Claims that GPT-5.6 API access or any public execution identifier is available.
- Claims that a GPT-5.6 study or any new live provider campaign has run.
- Claims that historical Frontier Delta model or variant labels identify real
  provider products, verified snapshots, execution provenance, or established
  training cutoffs. Protected preregistration statements remain historical
  assumptions.
- Provider rankings, alignment proof, semantic completeness, autonomous
  self-improvement, or autonomous ratification, promotion, publication, merge,
  tag, or release authority.
- Claims of EU AI Act approval, legal conformity, certification, or regulatory
  conformity from an SFA-Bench result.
- Claims that adapter-boundary bytes prove provider-side origin, complete wire
  fidelity, absence of SDK/proxy transformations, or access to hidden reasoning.
- Claims that provider/model labels or request identifiers authenticate a real
  provider product, model snapshot, execution origin, or training cutoff.
- Claims that a structurally valid execution authorization proves the submitter
  is human or establishes legal authority, consent, entitlement, ownership, or
  provider approval.

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

"Corrected successor" means a new canonically hashed and lineage-linked artifact
derived from preserved evidence. It does not overwrite or erase its predecessor,
and correction does not itself ratify the result.

"Benchmark lock" means the deterministic binding implemented and tested here.
It detects changes within its fixed and declared path sets; it is not a universal
security proof.

"Exact captured bytes" means the bytes observed by the named adapter at the
declared capture boundary. It does not mean independently authenticated provider
wire bytes.

"Execution authorized" means a supplied execution-only artifact passed the
implemented schema, digest, campaign, lock, request, adapter, and retry binding
checks. It does not authenticate the operator or authorize ratification.

"Capture provenance" means internal consistency among Git-bound code,
preregistration, lock, declared metadata, lifecycle events, and captured byte
hashes. Provider/model/request identifiers remain
`provider_declared_unverified` unless a separate signed-provider mechanism is
implemented and reviewed; alpha.2 implements no such mechanism.

## Scope changes

Any future change to verifier behaviour, taxonomy, provider execution, fixture
provenance, or security assumptions requires a new claim review. Alpha.1 adds
candidate-output integrity and campaign controls without changing the frozen
verifier. Alpha.2 delivers a provider-neutral capture envelope outside
deterministic judgment, verified offline with synthetic evidence. It does not
establish that a live campaign ran, ratify captured evidence, or move
provider/adapter metadata into verifier judgment.

Generation reproducibility may be limited; judgment reproducibility is mandatory.

SFA-Bench evidence may support governance review and compliance-oriented
documentation, but passing SFA-Bench does not establish legal or regulatory
conformity.
