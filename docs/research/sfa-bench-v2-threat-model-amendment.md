# SFA-Bench V2 Threat-Model Amendment

Status: `v2.0.0-alpha.1`

This amendment extends the V1 threat model to governed external-model evidence.
It does not replace the V1 verifier, history, lineage, or ratification controls.

## Protected Assets

- deterministic, history-blind verifier behavior;
- frozen prompt, task, evidence, rule, and taxonomy inputs;
- exact raw candidate evidence;
- benchmark-lock integrity;
- append-only predecessor and successor lineage;
- human ratification authority; and
- bounded public claims.

## Threats And Controls

### Invalid-output score inflation

Threat: empty, refusal-like, malformed, non-finite, or non-object output is
converted into an empty object, and lane defaults receive synthetic credit.

Control: one strict-JSON validity gate classifies the response before lane
dispatch. Invalid output, including `NaN` and infinity constants, receives an
explicit zero-score failure and cannot reach a canonicaliser or scorer. Tests use
failing spies to enforce the boundary.

Residual risk: a valid but semantically poor JSON object still reaches the
existing lane contract. Alpha.1 does not claim semantic completeness.

### Provider or adapter contamination

Threat: model identity, provider metadata, usage data, stop reason, or retry
metadata changes judgment.

Control: those fields remain in the capture/evidence envelope. The scorer sees
only the existing task and canonical candidate contract.

Residual risk: provider metadata may be incomplete or unavailable. It can affect
provenance quality, not the deterministic verdict.

### Post-observation policy changes

Threat: thresholds, exclusions, retry rules, or success criteria are revised
after results are known.

Control: canonical campaign content is bound into the benchmark lock. Mutation
causes a stable verification failure.

Residual risk: the lock cannot prove that an unrecorded planning conversation did
not occur. Reviewers must inspect the publication and commit timeline.

### Protected-input mutation

Threat: prompts, cases, evidence, verifier code, rules, taxonomy, normaliser,
adapter, or schemas change after lock creation.

Control: the lock records repository-relative file digests and a deterministic
aggregate digest. Lock creation resolves the declared Git commit, compares every
bound byte sequence with its commit blob, and compares every declared directory's
lock-eligible membership with the commit tree. The release identifier is derived
from the version source at that commit. Adversarial tests mutate and delete
members from every declared class, including the campaign protocol implementation.

Residual risk: only files in the fixed and declared binding sets are covered.

### Self-asserted lock provenance

Threat: an API caller supplies invented benchmark and verifier commits through
an injected context and produces a lock indistinguishable from a Git-observed
lock.

Control: public construction and verification resolve repository provenance
internally and accept no context override. Pure tests use private content helpers
that are not exposed by the CLI or verification wrappers.

Residual risk: Python does not enforce private-name access. Reviewers should
treat only the public CLI and public lock functions as governed lock surfaces.

### Mutable model aliases

Threat: a provider alias resolves to different model snapshots while results are
reported as one stable candidate.

Control: aliases must be explicitly declared. Execution-time identity and later
observed provider metadata belong in the candidate manifest.

Residual risk: provider metadata may not expose a stable snapshot identifier.
That limitation must remain visible in campaign reporting.

### Credential disclosure

Threat: an API key, token, password, or private key is committed in a campaign or
candidate manifest.

Control: validation normalizes credential-like keys across case and common
separators, rejects credential-like keys and values recursively, and requires no
credentials for core verification.

Residual risk: pattern checks cannot identify every secret format. Repository
secret scanning and human review remain necessary.

### Path traversal and output escape

Threat: a manifest reads files outside the repository or writes a lock outside an
approved runtime directory.

Control: paths are normalized, repository-relative, and containment-checked.
Lock output is confined to `out/campaign_locks` and refuses overwrite.

Residual risk: filesystem and symlink semantics vary by platform; the implemented
checks cover the tested Windows and POSIX-style path cases.

### Self-ratification or automatic promotion

Threat: a candidate or campaign declares itself passed, ratified, promoted, or
official.

Control: candidate manifests reject those fields and states. Validation
normalizes case, separators, and camel-case before recursively scanning arbitrary
configuration. It rejects ratification, promotion, approval, acceptance,
endorsement, execution, and completion claims on untrusted configuration and
provider-metadata surfaces. Ratification policy requires an identified human
reviewer, evidence, reason, and lineage. Automatic ratification and promotion are
invalid.

Residual risk: the software cannot establish the competence or independence of a
human reviewer.

### Non-standard numeric input

Threat: permissive Python JSON constants such as `NaN` or infinity enter
campaign or manifest content and undermine portable deterministic hashing.

Control: CLI parsing rejects non-standard constants, validator APIs reject
non-finite floats and unpaired Unicode surrogates recursively, and canonical
serialization disables non-finite values.

Residual risk: external tools must still preserve the documented JSON schema and
UTF-8 serialization contract.

### Historical evidence rewrite

Threat: the provisional Fable-5 artifact is edited or replaced to conceal the
earlier score-inflation behavior.

Control: predecessor files remain byte-identical. Corrected scoring is emitted as
a new canonically hashed, sealed successor with predecessor hashes, correction reason,
commit references, raw-evidence reference, and explicit lineage.

Residual risk: external copies outside this repository are not controlled.

### Claims inflation

Threat: a draft or passing campaign is represented as a provider ranking,
alignment proof, regulatory approval, or legal conformity.

Control: schemas distinguish draft execution status from development, pilot, and
official run classification; documentation
states explicit non-claims; ratification is separate from scoring.

Residual risk: downstream users can quote results without their qualifications.
Published reports must retain the limitations and campaign identifier.

## Non-Claims

Alpha.1 makes no claim that:

- a live GPT-5.6 or other provider run occurred;
- any provider model identifier is currently valid;
- any model passed or failed SFA-Bench;
- SFA-Bench proves alignment or semantic completeness;
- autonomous self-improvement exists;
- an EU institution or AI Act authority reviewed the project; or
- a passing result establishes legal or regulatory conformity.

Generation reproducibility may be limited; judgment reproducibility is mandatory.

SFA-Bench evidence may support governance review and compliance-oriented
documentation, but passing SFA-Bench does not establish legal or regulatory
conformity.
