# Pilot delivery checklist

Keeps the pilot software, not consulting. Time-boxed to two weeks.

## Setup (days 1-3)
- [ ] Deploy: `docker build -t groundledger -f product/Dockerfile .` (in-VPC) or
      `pip`-free embedded SDK in their repo (`product/sdk`).
- [ ] Load the data: map their fields to the rule pack's candidate/evidence shape.
- [ ] One tuning pass on citation patterns + subject aliases (no more).
- [ ] Smoke test on 10 answers; confirm verdicts look sane.

## First run (days 3-5)
- [ ] Verify all answers via the SDK/API; seal the per-tenant ledger.
- [ ] Run `python -m product.groundledger.replay <data> <tenant>` -> ATTESTED.
- [ ] Skim findings for mapping errors (a flood of identical false flags = bad mapping).

## Review of findings (days 5-8)
- [ ] Triage true findings vs. extraction misses; note coverage honestly.
- [ ] Pull 2-3 sharp examples for the executive summary.
- [ ] Confirm the groundedness rate and severity counts.

## Report (days 8-11)
- [ ] Build the signed bundle + HTML: `python -m product.groundledger.export build <data> <tenant> --out bundle.json --html report.html --key <secret>`.
- [ ] Verify it reproduces on a clean machine: `... export verify bundle.json --key <secret>` -> VERIFIED.
- [ ] Write the one-page executive summary (use `report-outline.md`).

## Final presentation (days 11-13)
- [ ] Walk the report top-to-bottom; show the tamper/replay proof live.
- [ ] Agree the first finding to fix.
- [ ] Present the monitoring + subscription proposal (Team tier).

## Follow-up (day 14+)
- [ ] Send the report + bundle + the one-line replay command for their auditor.
- [ ] One week later: did the report help with the prospect/auditor? Convert or get
      the honest "no" and the reason.

**Guardrails:** one assistant, one rule pack, one tuning pass, shipped checks only.
New connectors or check types = a separate paid follow-on.
