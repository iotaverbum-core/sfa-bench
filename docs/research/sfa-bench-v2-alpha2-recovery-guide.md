# Alpha.2 Interruption and Recovery Guide

An interruption is evidence, not a transient status to hide.

## Detection

Verification fails closed when it finds an attempt directory without an
immutable terminal record, a partial blob marked complete, a missing response
body, a ledger gap, or `capturing` state without a terminal event. It never
infers success from a response file, manifest temporary, or directory name.

## Operator actions

1. Do not delete or edit the run directory.
2. Preserve any remaining response chunks with `recover --partial-file`.
3. Record `record_interruption` when the process stopped before it could append
   the interruption event.
4. Choose `resume` only if the exact retry reason was preregistered and the
   authorization attempt budget remains. Resume creates a new attempt number;
   it never rewrites the interrupted attempt.
5. Choose `abort` when execution outcome is unknown or no retry is authorized.
6. Seal the aborted evidence and build an unjudged, unratified review bundle.

Synthetic command forms:

```powershell
py -3 campaign_capture_cli.py recover --run <run-dir> --action record_interruption --reason "operator observed process termination" --partial-file <partial.bin> --now 2026-07-12T20:00:00+02:00
py -3 campaign_capture_cli.py recover --run <run-dir> --action resume --reason "<exact preregistered reason>" --now 2026-07-12T20:01:00+02:00
py -3 campaign_capture_cli.py recover --run <run-dir> --action abort --reason "execution outcome unknown" --now 2026-07-12T20:01:00+02:00
```

The software never resends automatically. If a request may have reached a
provider but no terminal response event exists, the recorded outcome remains
`unknown` until human review.

## Corrections

Historical attempt bytes and events are immutable. A correction uses a new
execution ID or an explicitly linked successor. Never copy corrected bytes over
the predecessor or describe a redaction as original raw evidence.
