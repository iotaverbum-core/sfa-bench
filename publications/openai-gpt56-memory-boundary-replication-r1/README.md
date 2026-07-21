# GPT-5.6 Memory-Boundary Replication R1

This directory publishes the closed, preregistered repeated-execution replication:

`
openai-gpt56-memory-boundary-replication-r1
`

Publication was approved by **Matthew Neal** for a GitHub pull request and a
GitHub Release.

## Result

| Declared mutable model alias | Pass | Partial with `state_loss` | Total |
|---|---:|---:|---:|
| `gpt-5.6-sol` | 5 | 5 | 10 |
| `gpt-5.6-terra` | 0 | 10 | 10 |
| `gpt-5.6-luna` | 5 | 5 | 10 |
| **Total** | **10** | **20** | **30** |

All 30 executions were completed and separately ratified. The three pilot
executions are excluded from the replication estimates.

The analysis is descriptive. It does not authorize a tier ranking, a general
model-performance claim, a model endorsement, promotion, legal approval, or
regulatory approval.

## Published records

- `preregistration.json` â€” frozen post-pilot preregistration.
- `slot-plan.json` â€” canonical 30-slot order.
- `final-harness-status.json` â€” final offline completion verification.
- `replication-closure-spec.json` â€” exact 30-member closure input.
- `cohort-closure.json` â€” immutable closure record.
- `cohort-closure-lineage.json` â€” closure lineage.
- `cohort-closure.md` â€” readable closure summary.
- `preregistered-descriptive-report.json` â€” machine-readable report.
- `preregistered-descriptive-report.md` â€” readable report.
- `evidence-manifest.json` â€” manifest for 773 preserved evidence files.
- `snapshot-record.json` â€” binding for the release archive.
- `publication-authorization.json` â€” post-closure publication approval.
- `SHA256SUMS.txt` â€” repository artifact hashes and the release-asset hash.

## Core evidence digests

- Closure record: `ef519dc8cafb2cfa60eba183aa618770767f0fc3f662971876f5fce2117566fb`
- Closure lineage: `9a36d4556ede9df8c6926a56c98c4b09565a4f97e55b31ad9bf0741f7051fca3`
- Descriptive report: `66c27a1e84eaffbb91e6277154964764b86cc07097aec371f4eb39ee767f75d9`
- Snapshot manifest: `e37097e17cf1f86284e7fe3a6f2774d314aa228f3192623148ec9420ba1a6ee4`
- Snapshot archive: `41a8b5f532c530a9b0fc8723e82c429073167ae51af54a9426d9c535d92027ae`
- Snapshot record: `ac5ba6b3e08d0f59680ab82721291f1b5765bbc4ec16a672ab05c786f36ef25d`
- Slot plan: `1cd8fe1b072bc64a61f587309a7a347861824a1dfc00b5fe0cd5f730f38975ea`

## Release asset

The complete 773-file evidence snapshot is not committed to the source tree.
It must be attached to the GitHub Release as:

`
snapshot-openai-gpt56-memory-boundary-replication-r1-2026-07.tar.gz
`

Expected SHA-256:

`
41a8b5f532c530a9b0fc8723e82c429073167ae51af54a9426d9c535d92027ae
`

Recommended release tag:

`
gpt56-memory-boundary-replication-r1-2026-07
`

The closure and report are evidence records. Publishing them does not alter any
capture run or ratification record.
