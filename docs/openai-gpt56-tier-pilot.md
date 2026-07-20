# OpenAI GPT-5.6 Tier Pilot

This workflow extends the ratified `gpt-5.6-sol` memory-boundary pilot with one
separately preregistered `gpt-5.6-terra` execution and one separately preregistered
`gpt-5.6-luna` execution.

The cohort is exploratory. One execution per tier does not support ranking the
models or making general performance claims.

## Frozen cohort

| Role | Model | Campaign | Execution |
|---|---|---|---|
| Ratified anchor | `gpt-5.6-sol` | `openai-gpt56-memory-boundary-pilot-alpha2-r1` | `openai-gpt56-sol-pilot-002` |
| Planned successor | `gpt-5.6-terra` | `openai-gpt56-terra-memory-boundary-tier-pilot-alpha2-r1` | `openai-gpt56-terra-pilot-001` |
| Planned successor | `gpt-5.6-luna` | `openai-gpt56-luna-memory-boundary-tier-pilot-alpha2-r1` | `openai-gpt56-luna-pilot-001` |

The lock-bound cohort protocol is
`campaigns/examples/openai-gpt56-tier-pilot-protocol.json`.

## Execution

Use one direct execution invocation. The command first verifies that the account
exposes the exact model identifier, then prepares the governed pack and dispatches
the single authorized request:

```powershell
py -3 openai_gpt56_tier_pilot.py `
  --operator "Matthew Neal" `
  --model gpt-5.6-terra `
  --execute
```

The helper defaults to the exact preregistered execution ID. Supplying a different
ID fails closed.

Do not run a separate preparation-only command for these fixed cohort IDs. A
preparation pack is immutable, so consuming an ID without `--execute` would require
a new explicitly amended cohort rather than silently reusing that ID.

After Terra is captured and fully processed, repeat with `gpt-5.6-luna`.

Each invocation permits one attempt, uses `store:false`, supplies no tools, performs
no automatic retry, and stops before sealing or judgment.

## Post-capture order

For each completed run, preserve the existing order:

1. `campaign_capture_cli.py seal`
2. `campaign_capture_cli.py judge`
3. `campaign_capture_cli.py bundle`
4. `campaign_capture_cli.py verify`
5. explicit human disposition through `campaign_ratification_cli.py`

Do not compare headline scores until both successor executions have been separately
verified and disposed. Even then, describe the result as a three-execution
exploratory cohort, not a model ranking.
