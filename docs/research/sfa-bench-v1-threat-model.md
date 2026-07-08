# SFA-Bench v1.0 Threat Model

This threat model covers the v1.0 research release-pack governance path. It is
focused on local candidate evaluation, packet review, ratification, lineage, and
release hygiene. It does not claim complete security coverage.

## Assets

- Frozen governance files and manifests.
- Candidate packets and ratification packets.
- Verification command outputs and outcome classifications.
- Lineage records and failure memory.
- Release cleanliness and reviewer trust.

## Trust Boundaries

Candidate generation is outside the trust boundary. Deterministic verification,
frozen-zone inspection, packet validation, release-gate checks, and recorded
human actions are inside the trust boundary. Human judgment is required at the
ratification boundary.

## Threats And Controls

### Frozen-Path Tampering

Risk: A candidate modifies frozen governance code, manifests, holdout data, or
other protected paths while presenting itself as an ordinary improvement.

Controls: The external candidate harness records changed paths against
`origin/main`, frozen-zone checks compare the candidate to the frozen manifest,
and adversarial cases expect frozen-path proposals to halt before promotion.

Limit: These controls depend on the selected base, the checked-in manifest, and
the implemented path rules. They do not prove that every future protected path
has been modeled.

### Metric Gaming

Risk: A candidate optimizes for a visible metric, weakens evaluation intent, or
claims improvement by exploiting the gate rather than improving the system.

Controls: The governed runner separates proposal, declared evaluation, fixed
gate computation, human ratification, and lineage. Policy and history can guide
proposals but cannot enter verifier judgment.

Limit: Deterministic gates can only enforce the metrics and decision rules they
encode. Reviewers must still judge whether a metric is meaningful.

### Malformed Packets

Risk: A malformed or incomplete candidate packet is passed into the ratification
path to bypass required evidence.

Controls: The ratification CLI validates required fields before recording an
action. The adversarial suite includes a malformed-packet case that must reject
with a predictable reason.

Limit: Packet validation checks structure and required decision fields. It does
not make malformed external context impossible.

### Ratification Misuse

Risk: A reviewer or automation tries to ratify a candidate that was not
classified as `PROMOTION_READY`, or treats packet preparation as approval.

Controls: `--ratify` is refused for non-`PROMOTION_READY` packets. `--prepare`
creates review material only. Ratification packets and lineage records describe
the human action rather than silently promoting code.

Limit: The system records the action. It cannot guarantee that an organization
assigned the right reviewer or that the reviewer made a wise decision.

### Lineage Spoofing

Risk: A candidate or operator fabricates lineage records, rewrites promotion
history, or presents an unverified decision as a recorded lineage event.

Controls: The CLI writes lineage records from validated packet fields and
explicit human actions. The architecture treats lineage as a record derived from
reviewed packets rather than an input to verifier judgment.

Limit: Local files can still be copied or misrepresented outside the repository.
Reviewers must inspect the repository state and packet provenance they are
asked to trust.

### Erased Failure Memory

Risk: Failure history, rejection records, or circuit-breaker evidence is removed
so repeated failures look like new or isolated events.

Controls: The AutoLab runner appends rejection and halt events, lineage records
preserve decisions, and replay-oriented repository checks protect history and
sealed artifacts covered by the implementation.

Limit: The system cannot recover evidence that was never recorded, and it cannot
protect external storage that is outside the repository and review process.

### Dirty Release Artifacts

Risk: Generated outputs, runtime directories, untracked files, or staged sealed
artifacts contaminate a release candidate.

Controls: `release_gate.py --ci` inspects `git status --short
--untracked-files=all`, rejects untracked files, rejects staged runtime output,
and rejects staged generated sealed artifacts covered by its rules.

Limit: Release hygiene checks cover the repository's known generated paths and
protected files. Reviewers must still inspect unusual new artifacts.

## Out Of Scope

This threat model does not claim resistance to compromised developer machines,
malicious Git hosting, social engineering, undisclosed reviewer conflicts,
provider-side model failures, or all possible future governance attacks.