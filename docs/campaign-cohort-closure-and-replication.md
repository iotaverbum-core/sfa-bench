# Campaign Cohort Closure and Repeated Replication

## Cohort closure

`campaign_cohort_closure_cli.py` creates a separate immutable companion record for a completed cohort. It does not edit the original capture runs, review bundles, ratification packets, or lineage records.

The closure command validates:

- the exact closure specification and member identities;
- all three secret-free review bundles;
- each benchmark lock, capture manifest, deterministic judgment, lifecycle chain, and integrity report through the existing review-bundle validator;
- each canonical ratification packet and ratification lineage record;
- `RATIFIED` human disposition for every member;
- the expected review-bundle, judgment, packet, and lineage hashes;
- identical frozen case, rules, taxonomy, normalizer, system-prompt, and user-prompt binding groups;
- the tier-pilot protocol binding in the Terra and Luna successor locks.

The output directory contains:

- `cohort-closure.json`
- `cohort-closure-lineage.json`
- `cohort-closure.md`

The closure is descriptive. It does not endorse a model, attest provider identity, rank tiers, promote a candidate, publish evidence, create a release, or grant legal or regulatory approval.

### Command

```powershell
py -3 campaign_cohort_closure_cli.py `
  --operator "Matthew Neal"
```

The default inputs are:

- captures: `out/campaign_runs`
- ratifications: `out/campaign_ratifications`
- specification: `campaigns/examples/openai-gpt56-tier-pilot-closure-spec.json`
- output: `out/campaign_cohort_closures`

The operation is exclusive. Reusing the same closure ID fails rather than overwriting an existing record.

## Repeated-run replication preregistration

`campaigns/examples/openai-gpt56-memory-boundary-replication-r1.json` preregisters a fresh repeated-execution study:

- 10 new Sol executions;
- 10 new Terra executions;
- 10 new Luna executions;
- 30 authorized execution slots in total;
- ten fixed blocks, each containing all three exact model identifiers;
- one request and one attempt per execution;
- no retry, replacement execution, silent substitution, tools, storage, optional stopping, or outcome-dependent reordering.

The three completed pilot executions are excluded from both primary and secondary replication analyses. They informed the decision to replicate, but their outcomes do not count toward the new estimates.

The primary descriptive endpoint is the pass proportion for each declared tier. Secondary endpoints are the `state_loss` proportion and mean deterministic score. Completion counts and two-sided 95% Wilson intervals must be reported. Pairwise model ranking and general model-performance claims remain unauthorized.

No provider call is authorized merely by committing or validating the preregistration. A separate guarded execution layer and explicit execution authorization are required before the first replication slot.
