# Ratification Packet + Lineage CLI

Item 10 adds a minimal CLI that consumes a Unit 9 `candidate_packet.json` and
records the human review step as a ratification packet plus a lineage decision
record. It does not promote a candidate, update branch pointers, or modify
AutoLab governance code. Promotion remains a separate human-controlled action.

## Commands

```powershell
py -3 ratification_packet_cli.py --packet <candidate_packet.json> --prepare
py -3 ratification_packet_cli.py --packet <candidate_packet.json> --ratify
py -3 ratification_packet_cli.py --packet <candidate_packet.json> --reject
py -3 ratification_packet_cli.py --packet <candidate_packet.json> --halt
```

The optional `--rationale` field records human review context:

```powershell
py -3 ratification_packet_cli.py --packet <candidate_packet.json> --reject `
  --rationale "Documentation is unclear for the proposed workflow."
```

## Inputs

The CLI expects the Unit 9 schema:

```text
sfa.external_candidate_harness.packet.v0
```

It validates that the packet includes the candidate run ID, base ref and commit,
target ref and commit, changed files, verification command results, frozen-path
status, and candidate outcome.

`--ratify` is refused unless the candidate outcome is `PROMOTION_READY`.
`--reject` and `--halt` may record a human decision for any valid candidate
packet. `--prepare` creates a review packet and does not count as approval.

## Outputs

Every successful action writes:

```text
out/ratification_packets/<run_id>/ratification_packet.json
out/ratification_packets/<run_id>/ratification_packet.md
out/ratification_packets/<run_id>/lineage_record.json
```

The ratification packet includes:

- target ref and commit;
- base ref and commit;
- changed files;
- protected verification results;
- frozen-path status;
- human action, timestamp, and rationale; and
- the ratification outcome.

The lineage record repeats the same decision-critical fields and records:

```text
LINEAGE_RECORDED
```

This means the decision was recorded. It does not mean the candidate was
promoted.

## Outcome Classes

Ratification packet outcomes:

- `RATIFICATION_READY`: `--prepare` wrote a review packet.
- `RATIFIED`: `--ratify` recorded explicit human approval for a
  `PROMOTION_READY` candidate.
- `REJECTED_BY_HUMAN`: `--reject` recorded explicit human rejection.
- `HALTED_BY_HUMAN`: `--halt` recorded an explicit halt, or validation refused
  the requested action.

Lineage record outcome:

- `LINEAGE_RECORDED`: the human decision was recorded with no promotion effect.

## Example Fixture

See
[`tests/fixtures/ratification_packet_example.json`](../tests/fixtures/ratification_packet_example.json)
for a compact example of the JSON packet shape.
