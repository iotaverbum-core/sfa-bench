# Alpha.2 Campaign Capture Contributor Guide

## Before editing

1. Confirm `main`, `origin/main`, and `v2.0.0-alpha.1` ancestry.
2. Run `py -3 verify_all.py`, `py -3 release_gate.py --ci`, and
   `py -3 frozen_zone_check.py --ci --base origin/main`.
3. Read `autolab/frozen_manifest.json` and the alpha.2 decision log.
4. Keep `campaign_cli.py`, `campaigns/schemas/`,
   `sfa_bench/campaigns/{__init__,locking,protocol}.py`, and every frozen path
   unchanged.

## Development rules

- Use only stdlib modules in the canonical core.
- Never add a live provider SDK, credential requirement, or network test.
- Bind every alpha.2 core/schema file in campaigns that execute.
- Preserve bytes before metadata interpretation.
- Use exclusive no-overwrite publication and immutable successor lineage.
- Keep adapter/provider/retry/authorization metadata out of judgment.
- Do not expose ratify, promote, merge, tag, push, publish, or release actions.
- Use temporary output roots for tests; never stage runtime evidence.

## Verification

```powershell
py -3 -m unittest tests.test_campaign_capture
py -3 -m unittest discover -s tests -t . -p "test_*.py"
py -3 campaign_capture_check.py
py -3 verify_all.py
py -3 release_gate.py --ci
py -3 frozen_zone_check.py --ci --base origin/main
git diff --check
git diff --name-only origin/main...HEAD
git status --short --untracked-files=all
```

Run a full-history clean clone with LF checkout and a Windows clone honoring
`core.autocrlf=true`. Verify product packaging separately; do not change the
independent GroundLedger `0.1.0` version for this research tranche.

## Claims review

Describe only checked-in implementation behavior and executed tests. Qualify
"exact" as adapter-boundary bytes and "provenance" as internal consistency plus
declared metadata. Do not imply live execution, provider/model identity,
rankings, regulatory conformity, semantic completeness, or autonomous authority.
