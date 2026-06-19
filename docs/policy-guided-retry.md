# Policy-Guided Retry

SFA-Bench v0.9 can deterministically choose generator-side remediation
directives from sealed recurrence profiles.

Policy-guided retry means: use recurring failure-family evidence to shape the
next proposal. It does not mean using recurrence evidence to change the
verifier's judgment. A directive may be supplied to a generator prompt, adapter
input, or generator-side warning only.

## Deterministic policy

`sfa/policy.py` implements policy version `sfa-policy-v0.1`. Its input contains
the recurrence scope and family counts/rates, current failure family, retry
attempt number, optional prior remediation history, model or fixture identity,
and versioned config. The recurrence profile and complete input are hashed.

A family recurs when its count is at least 2 in the relevant scope. The
threshold is explicit in every decision. All recurring mapped families compose
in this fixed priority order:

1. `fabricated_entity`
2. `contradicts_evidence`
3. `unsupported_claim`
4. `missing_required_field`

The policy does not select a single winner. It composes every triggered
directive in that order, which also breaks count/rate ties.

## Directive mapping

- `fabricated_entity` → `closed_world_entity`: only use entities, citations,
  fields, and values that resolve explicitly to the evidence pack; omit absent
  entities. This is a closed-world rule, not merely an instruction to add
  citations.
- `contradicts_evidence` → `claim_by_claim_evidence_check`: compare every claim
  value directly with cited evidence and revise or omit conflicts.
- `unsupported_claim` → `evidence_required`: remove claims without direct
  evidence support and prefer fewer supported claims.
- `missing_required_field` → `schema_first`: populate required structure before
  finalizing while keeping every value evidence-grounded.

## Escalation and termination

Escalation is derived from prior applied remediation records and retry ordinal:

- Level 1 applies the family-specific directive.
- Level 2 repeats the directive with a family-specific stricter output
  constraint.
- Level 3 stops automated retry and requires human review.

Policy config v0.1 allows two policy-guided retries. A third retry request fails
closed at level 3. Replaying the same input produces byte-identical decision
output, including escalation and termination.

## Sealing and trust boundary

Each decision records policy/config versions, policy input and recurrence
profile hashes, threshold, composition order, triggering families, counts,
rates, directive text, escalation level, termination recommendation, and a
decision hash. Policy-guided retry is replayable because the policy decision is
derived from sealed inputs.

The verifier remains history-blind and policy-blind. It never receives the
directive, recurrence profile, fingerprint summary, prior failures, retry
count, model/adapter identity, prompt/transcript, warning text, or provenance.
It judges only the task, evidence, normalized candidate, and fixed rules.

## Offline evidence

`examples/policy/` contains clearly illustrative fixtures for a single recurring
family, multiple recurring families, level-2 escalation, and level-3
termination. `policy_demo.py` derives and seals a decision, checks replay, and
shows that verifier output is unchanged after generator metadata is excluded.

The fixtures do not show live provider repair, model improvement, hidden model
reasoning, or a learned policy. No API, model, or network calls are used.
