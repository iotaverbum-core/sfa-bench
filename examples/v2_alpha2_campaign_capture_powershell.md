# Alpha.2 Synthetic Campaign Capture Commands

These commands are offline and synthetic. They do not authorize or execute a
live provider campaign and do not ratify evidence.

```powershell
py -3 -m unittest tests.test_campaign_capture
py -3 campaign_capture_check.py
py -3 campaign_capture_cli.py --help
```

For an operator-prepared lock, request file, and separately supplied
execution-only authorization artifact:

```powershell
$env:SFA_CAMPAIGN_CAPTURE_ROOT = "C:\tmp\sfa-campaign-runs"

py -3 campaign_capture_cli.py validate-authorization `
  --campaign <preregistration.json> `
  --lock <benchmark-lock.json> `
  --authorization <execution-authorization.json> `
  --request <exact-request.bin> `
  --mode valid_json_object

py -3 campaign_capture_cli.py init `
  --campaign <preregistration.json> `
  --lock <benchmark-lock.json> `
  --authorization <execution-authorization.json> `
  --request <exact-request.bin> `
  --mode valid_json_object `
  --now 2026-07-12T20:00:00+02:00

py -3 campaign_capture_cli.py capture-synthetic `
  --run <campaign-run-directory> `
  --request <exact-request.bin> `
  --mode valid_json_object `
  --now 2026-07-12T20:00:01+02:00

py -3 campaign_capture_cli.py seal --run <campaign-run-directory> --now 2026-07-12T20:00:02+02:00
py -3 campaign_capture_cli.py judge --run <campaign-run-directory> --task-reference sfa_bench/frontier_delta/tasks/memory_boundary_001.json --now 2026-07-12T20:00:03+02:00
py -3 campaign_capture_cli.py bundle --run <campaign-run-directory> --now 2026-07-12T20:00:04+02:00
py -3 campaign_capture_cli.py verify --run <campaign-run-directory>
```

The CLI intentionally provides no live adapter, credential option, ratification,
promotion, merge, tag, push, publication, or release command.
