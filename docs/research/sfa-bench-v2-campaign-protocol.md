# SFA-Bench V2 Campaign Protocol

Status: `v2.0.0-alpha.1` protocol foundation

Generation reproducibility may be limited; judgment reproducibility is mandatory.

## Scope

This protocol governs future external-model candidate studies without moving
provider execution, adapter metadata, retry policy, or ratification into the
deterministic judgment boundary.

The alpha.1 implementation provides:

- candidate-output integrity classification before lane canonicalisation;
- provider-neutral campaign pre-registration validation;
- candidate-manifest validation;
- deterministic benchmark-lock creation and verification;
- offline, machine-readable CLI results; and
- explicit human ratification policy validation.

The following work is planned for later V2 phases and is not implemented here:

- provider capture;
- repeated live runs;
- holdout execution;
- independent campaign replication; and
- provider comparison or ranking.

No live model evaluation occurred as part of this tranche.

## Judgment Boundary

The governed flow is:

```text
provider -> raw capture -> deterministic validity gate -> normaliser
         -> frozen scorer/verifier -> evidence packet -> human review
```

Provider and adapter metadata stay in the evidence envelope. Retry policy may
shape a later candidate, but it cannot alter a verdict for an observed candidate.
Only a valid JSON object reaches a lane canonicaliser. Invalid candidate text is
classified before dispatch:

| Candidate text | Outcome |
|---|---|
| empty or whitespace | `no_model_output` |
| no strict JSON object found, including non-finite constants | `unparseable_model_output` |
| valid JSON that is not an object | `invalid_model_output` |
| valid JSON object | existing lane canonicaliser and scorer path |

For surrounding prose, the first decodable top-level object is used. The first
of multiple top-level objects wins; an object nested inside an array or another
non-object container is not extracted. An incidental leading JSON scalar in
prose does not suppress a later top-level object.

The original raw response remains referenced by its deterministic response-text
SHA-256. The
validity gate does not repair invalid text or invent a replacement object. Valid
JSON objects continue through the existing lane canonicalisers, whose legacy
normalisation may populate lane-specific defaults.

## Pre-Registration

A campaign declaration binds the research question and conditions before an
official observation. Required sections cover:

- campaign identity, title, question, status, and run classification;
- provider, requested model identifier, and snapshot or alias status;
- execution surface, prompts, tools, reasoning, and sampling configuration;
- planned repetitions and execution plan;
- benchmark and verifier commits;
- normaliser and adapter versions and paths;
- frozen cases, evidence, rules, taxonomy, and schemas;
- success, failure, exclusion, retry, and halt policies;
- the invalid-output policy above;
- holdout commitments and declared limitations; and
- a human-only ratification policy.

Mutable aliases are rejected unless their use is explicit. An official campaign
is rejected by the CLI unless it references a lock artifact that is loaded and
verified against current bound files. Its repository, release, and verifier
references must agree with the declaration.

Lock creation also requires resolved system-prompt and user/case-set references.
A file reference declares its byte SHA-256; a directory reference declares the
digest of its canonical, sorted file-binding set. The checked-in example system
prompt is neutral and passes the same forbidden-token preflight used for blinded
candidate prompts.

The checked-in GPT-5.6 example is a schema example only. It is labelled
`draft_not_executed`, uses `TO_BE_CONFIRMED_AT_EXECUTION` where an execution-time
provider identifier must be verified, and records no result.

## Candidate Manifest

Alpha.1 candidate manifests are draft templates only. They record intended
identity and capture conditions separately from
the benchmark declaration. It includes the provider, model string supplied at
execution, later-observed provider metadata when available, configuration, tool
state, environment, capture-boundary version, and campaign reference.

Likely credentials or secrets are rejected. A candidate cannot declare itself
ratified or promoted, and its alpha.1 status must remain `draft_not_executed`.
Executed-state and review records belong to later protocol phases.
Governance-control key variants are normalized across case, separators, and
camel-case before recursive checks. Untrusted configuration and provider metadata
text cannot assert ratification, promotion, official completion, or ranking.
Non-standard JSON constants such as `NaN`, infinity, and unpaired Unicode
surrogates are rejected, as are equivalent malformed values supplied through the
Python validator API.

## Benchmark Lock

The deterministic lock binds:

- the canonical campaign content, excluding only its circular lock reference;
- a Git-resolved benchmark commit, current package release, and declared
  verifier commit;
- protected verifier implementation files;
- declared prompt, case, evidence, rule, taxonomy, normaliser, adapter, schema,
  and authoritative campaign-protocol implementation files;
- the research release identifier; and
- the declared command set.

Each bound file is represented by a repository-relative path and SHA-256. Stable
sorting and compact UTF-8 JSON produce the lock digest. Optional envelope fields,
do not participate in that digest. Alpha.1 permits only a timezone-qualified
`created_at`; all free-form envelope fields are rejected.

Before lock creation, the CLI resolves the declared Git commit and compares every
bound worktree file byte-for-byte with `git show <commit>:<path>`. It also checks
the complete lock-eligible membership of every declared directory against that
commit. The release identifier is read from `sfa/__init__.py` at the declared
benchmark commit, not from dirty worktree bytes. A missing commit blob, member
deletion, extra member, or byte mismatch fails closed, so ignored or untracked
bytes cannot be attributed to an unrelated commit. Public lock construction and
verification do not accept an injected repository context; private content
helpers exist only for pure tests and do not constitute governed provenance.

Changing a threshold, policy, prompt, case, evidence file, rule, taxonomy,
normaliser, adapter, schema, or protected verifier file after lock creation causes
verification to fail. The lock detects those tested mutations; it is not a claim
that every possible attack is prevented.

## Execution Plan

The execution plan declares run classification, repetitions, ordering,
concurrency, retries, error handling, exclusions, output paths, and halt
conditions. Retries create later candidate attempts. They do not revise the
judgment of an earlier attempt. Invalid outputs remain preserved as evidence.

All declared paths must remain canonical, portable, repository-relative, and
within their approved roots. Empty/dot segments, parent traversal, colons,
Windows-reserved names, and trailing spaces or dots are rejected. Runtime lock
files are confined to `out/campaign_locks`. Existing output files are not
overwritten.

## Ratification

The policy schema permits human decisions `prepare`, `ratify`, `reject`, and
`halt`, and requires reviewer identity, evidence references, a reason, and
lineage linkage. Alpha.1 validates that declaration; it does not perform a review
or create a ratification record. Automatic ratification and automatic promotion
are prohibited.

## Offline Commands

```powershell
py -3 campaign_cli.py validate --campaign campaigns/examples/gpt56-draft-preregistration.json
py -3 campaign_cli.py lock --campaign campaigns/examples/gpt56-draft-preregistration.json --output out/campaign_locks/gpt56-future-study-draft-alpha1.benchmark-lock.json
py -3 campaign_cli.py verify-lock --campaign campaigns/examples/gpt56-draft-preregistration.json --lock out/campaign_locks/gpt56-future-study-draft-alpha1.benchmark-lock.json
py -3 campaign_cli.py validate-candidate --manifest campaigns/examples/gpt56-draft-candidate-manifest.json
```

The commands require no network access, provider SDK, model execution, or API
credential. Each command prints one JSON result and returns nonzero on failure.

## Interpretation Boundary

This foundation does not establish provider access, model performance, a model
ranking, alignment, semantic completeness, autonomous self-improvement, or legal
conformity. It permits no automatic promotion.

SFA-Bench evidence may support governance review and compliance-oriented
documentation, but passing SFA-Bench does not establish legal or regulatory
conformity.
