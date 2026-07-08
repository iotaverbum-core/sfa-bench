# Ratification Packet CLI Minimal PowerShell Usage

This flow starts with a committed candidate, generates a Unit 9 candidate
packet, then records the human review step through the Item 10 CLI.

```powershell
# 1. Generate a candidate packet from a commit or branch.
py -3 external_candidate_harness.py --target <commit-sha>
# or
py -3 external_candidate_harness.py --branch <branch-name>

# 2. Prepare a review packet from the generated candidate packet.
py -3 ratification_packet_cli.py `
  --packet out/candidate_packets/<candidate-run-id>/candidate_packet.json `
  --prepare

# 3. Record exactly one explicit human decision.
py -3 ratification_packet_cli.py `
  --packet out/candidate_packets/<candidate-run-id>/candidate_packet.json `
  --ratify `
  --rationale "Human review approved the promotion-ready packet."

# Alternative decisions:
py -3 ratification_packet_cli.py `
  --packet out/candidate_packets/<candidate-run-id>/candidate_packet.json `
  --reject `
  --rationale "Human review rejected the candidate."

py -3 ratification_packet_cli.py `
  --packet out/candidate_packets/<candidate-run-id>/candidate_packet.json `
  --halt `
  --rationale "Human review halted the workflow for follow-up."
```

`--ratify` is accepted only when the candidate packet outcome is
`PROMOTION_READY`. The CLI writes artifacts under
`out/ratification_packets/<run_id>/` and does not auto-promote anything.
