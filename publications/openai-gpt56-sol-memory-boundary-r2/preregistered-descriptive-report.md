# SFA-Bench R2: Preregistered Descriptive Report

- Study: `openai-gpt56-sol-memory-boundary-r2`
- Closure: `closure-openai-gpt56-sol-memory-boundary-r2`
- Closed executions: `48`
- Report digest: `09b1ecda2e993560295b31392fb17c820878e7e4785da6e5ba3d4d38282dcf7c`

## Research question

How do public-state representation and an explicit retention reminder affect preservation of permitted identity state, particularly customer_id, without increasing forbidden-state use?

## Condition-level results

| Condition | Representation | Reminder | Completed / ratified | Complete preservation | 95% Wilson interval | `customer_id` loss | 95% Wilson interval | Forbidden-state use | 95% Wilson interval | Mean score |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `prose-no-reminder` | prose | no | 12/12 | 7/12 (58.3%) | 32.0%–80.7% | 5/12 (41.7%) | 19.3%–68.0% | 0/12 (0.0%) | 0.0%–24.2% | 0.861111 |
| `json-no-reminder` | json | no | 12/12 | 5/12 (41.7%) | 19.3%–68.0% | 7/12 (58.3%) | 32.0%–80.7% | 0/12 (0.0%) | 0.0%–24.2% | 0.805556 |
| `prose-reminder` | prose | yes | 12/12 | 12/12 (100.0%) | 75.8%–100.0% | 0/12 (0.0%) | 0.0%–24.2% | 0/12 (0.0%) | 0.0%–24.2% | 1.000000 |
| `json-reminder` | json | yes | 12/12 | 12/12 (100.0%) | 75.8%–100.0% | 0/12 (0.0%) | 0.0%–24.2% | 0/12 (0.0%) | 0.0%–24.2% | 1.000000 |

## Preregistered descriptive contrasts

All contrasts use the complete permitted-state preservation proportion. No significance test was performed.

- Pooled JSON: `70.8%`; pooled prose: `79.2%`; JSON minus prose: `-8.3 percentage points`.
- Pooled reminder: `100.0%`; pooled no-reminder: `50.0%`; reminder minus no reminder: `+50.0 percentage points`.
- Interaction: `(JSON reminder − prose reminder) − (JSON no-reminder − prose no-reminder)` = `+16.7 percentage points`.

## Overall execution counts

- Planned: `48`
- Completed and ratified: `48`
- Complete permitted-state preservation: `36`
- Partial with `state_loss`: `12`
- `customer_id` loss: `12`
- Forbidden-state use: `0`
- Refusal: `0`
- Malformed output: `0`
- Transport failure: `0`
- Interrupted: `0`
- Halted: `0`
- Rejected: `0`
- Replacement executions: `0`

## Exact result-hash frequencies

### `prose-no-reminder`

| Result hash | Count |
|---|---:|
| `3b0b0c5a1301d9a1a75b69b8ccbcb7f7427d954450cacb8f53d8337d038c7c4c` | 7 |
| `4cca93fa1e2792ba49410acb2ef69c3bcfee482b039e660ee1b069a18c9fce28` | 5 |

### `json-no-reminder`

| Result hash | Count |
|---|---:|
| `3b0b0c5a1301d9a1a75b69b8ccbcb7f7427d954450cacb8f53d8337d038c7c4c` | 5 |
| `4cca93fa1e2792ba49410acb2ef69c3bcfee482b039e660ee1b069a18c9fce28` | 7 |

### `prose-reminder`

| Result hash | Count |
|---|---:|
| `3b0b0c5a1301d9a1a75b69b8ccbcb7f7427d954450cacb8f53d8337d038c7c4c` | 12 |

### `json-reminder`

| Result hash | Count |
|---|---:|
| `3b0b0c5a1301d9a1a75b69b8ccbcb7f7427d954450cacb8f53d8337d038c7c4c` | 12 |

## Interpretation limits

- R2 studies one frozen memory-boundary task under one declared mutable provider alias.
- The design does not establish general model quality, safety, or fitness for a specific deployment.
- The study does not authorize model ranking, endorsement, certification, legal approval, or regulatory approval.
- Condition effects are task-specific and may not generalize to other state schemas, prompts, providers, or execution dates.
- Mutable alias drift limits claims about immutable model identity.
- All reported contrasts are descriptive differences in observed proportions; no null-hypothesis significance test was performed.
- The report describes exactly the 48 completed and ratified R2 executions bound by the formal cohort closure.

## Evidence bindings

- Repository commit: `972ad7ef838dde49601f0b093fbbbc4b6c3d8c82`
- Closure specification SHA-256: `803fd47c6cefe845bb93622e9a89300d8d6adbca4ab1e7eafa59fc45b9f8e59a`
- Closure record SHA-256: `42fccd9a37c48aee23c24731518cb4df243abdcc96dba4c33d668944d04f0e0e`
- Closure lineage SHA-256: `a5bf677b089e2101235ebf69521f66ccb93c76bc99e9dc3a7f6f2275fe9f2101`
- Preregistration SHA-256: `fd90c92f2bce54223408b5702495d999036bbbdf1cca64c27aface825e470535`

## Authority boundary

This report does not make a provider request, rerun an execution, mutate source evidence, perform significance testing, rank or endorse a model, create an evidence snapshot, publish, release, or authorise R3 or any later campaign.
