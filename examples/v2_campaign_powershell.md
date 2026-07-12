# V2 Campaign Foundation: PowerShell Example

This example validates a draft, creates a deterministic lock in the approved
runtime directory, verifies it, and validates the separate candidate manifest.
It performs no provider call and requires no API credential.

```powershell
$Campaign = "campaigns/examples/gpt56-draft-preregistration.json"
$Candidate = "campaigns/examples/gpt56-draft-candidate-manifest.json"
$Lock = "out/campaign_locks/gpt56-future-study-draft-alpha1.benchmark-lock.json"

py -3 campaign_cli.py validate --campaign $Campaign
py -3 campaign_cli.py lock --campaign $Campaign --output $Lock
py -3 campaign_cli.py verify-lock --campaign $Campaign --lock $Lock
py -3 campaign_cli.py validate-candidate --manifest $Candidate
```

Each command prints one JSON object. Validation failures return a nonzero exit
code with stable issue codes. Lock creation refuses an existing output path.

`lock` creates the initial no-overwrite artifact after proving bound files,
including both prompt references, match their declared hashes, Git commit, and
package release. Public commands do not accept an injected repository context.
Routine review uses `verify-lock`.
An official campaign must add the resulting digest/path reference before its
`validate` command can load and verify that artifact.

The historical correction is independently non-mutating:

```powershell
py -3 candidate_evidence_cli.py verify `
  --artifact out/candidate_evidence_successors/fable5-frontier-delta-20260703-corrected-v2-alpha1.json `
  --raw out/fable5_failure_delta/raw_outputs.jsonl `
  --predecessor out/fable5_failure_delta/scored_results.json
```

The GPT-5.6 declaration is `draft_not_executed`. The placeholder model identifier
must be confirmed before any future execution; this example records no result.
