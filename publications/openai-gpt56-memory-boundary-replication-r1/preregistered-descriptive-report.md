# GPT-5.6 Memory-Boundary Replication: Preregistered Descriptive Report

- Replication: `openai-gpt56-memory-boundary-replication-r1`
- Closure: `closure-openai-gpt56-memory-boundary-replication-r1-2026-07`
- Closed executions: `30`
- Report digest: `66c27a1e84eaffbb91e6277154964764b86cc07097aec371f4eb39ee767f75d9`

## Research question

Across 10 fresh governed executions per exact exposed GPT-5.6 tier, what proportion of outputs preserve the frozen memory-state boundary?

## Preregistered results

| Model | Completed / ratified | Pass | Pass 95% Wilson interval | State loss | State-loss 95% Wilson interval | Mean score |
|---|---:|---:|---:|---:|---:|---:|
| `gpt-5.6-sol` | 10/10 | 5/10 (50.0%) | 23.7%–76.3% | 5/10 (50.0%) | 23.7%–76.3% | 0.833333 |
| `gpt-5.6-terra` | 10/10 | 0/10 (0.0%) | 0.0%–27.8% | 10/10 (100.0%) | 72.2%–100.0% | 0.666667 |
| `gpt-5.6-luna` | 10/10 | 5/10 (50.0%) | 23.7%–76.3% | 5/10 (50.0%) | 23.7%–76.3% | 0.833333 |

## Overall execution counts

- Completed and ratified: `30/30`
- Pass: `10/30`
- Partial with `state_loss`: `20/30`
- Interrupted: `0`
- Halted: `0`
- Rejected: `0`
- Replacement executions: `0`

## Exact result-hash frequencies

### `gpt-5.6-sol`

| Result hash | Count |
|---|---:|
| `3b0b0c5a1301d9a1a75b69b8ccbcb7f7427d954450cacb8f53d8337d038c7c4c` | 5 |
| `4cca93fa1e2792ba49410acb2ef69c3bcfee482b039e660ee1b069a18c9fce28` | 5 |

### `gpt-5.6-terra`

| Result hash | Count |
|---|---:|
| `4cca93fa1e2792ba49410acb2ef69c3bcfee482b039e660ee1b069a18c9fce28` | 10 |

### `gpt-5.6-luna`

| Result hash | Count |
|---|---:|
| `3b0b0c5a1301d9a1a75b69b8ccbcb7f7427d954450cacb8f53d8337d038c7c4c` | 5 |
| `4cca93fa1e2792ba49410acb2ef69c3bcfee482b039e660ee1b069a18c9fce28` | 5 |

## Interpretation

All non-pass judgments were partial results containing `state_loss`. No pairwise ranking or significance test was preregistered or performed.

The pilot cohort is excluded from the replication estimates.

## Limits

- This is a descriptive repeated-execution replication of one frozen memory-boundary task.
- The three pilot executions are excluded from every replication estimate.
- The exposed model identifiers were declared mutable provider aliases, not immutable snapshots.
- No pairwise significance test or tier ranking was preregistered or performed.
- Observed differences do not establish general model intelligence, quality, safety, alignment, legal conformity, or regulatory approval.
- The results describe these 30 ratified executions only.

## Authority boundary

This report does not endorse, rank, promote, publish, release, or legally approve any model.

## Evidence bindings

- Closure record SHA-256: `ef519dc8cafb2cfa60eba183aa618770767f0fc3f662971876f5fce2117566fb`
- Closure lineage SHA-256: `9a36d4556ede9df8c6926a56c98c4b09565a4f97e55b31ad9bf0741f7051fca3`
- Slot-plan SHA-256: `1cd8fe1b072bc64a61f587309a7a347861824a1dfc00b5fe0cd5f730f38975ea`
- Preregistration SHA-256: `ab2c59f4b07ee47baa5a8da8c4ee699ca3ce1bdcfca86f70fb8dd84d74872bee`
