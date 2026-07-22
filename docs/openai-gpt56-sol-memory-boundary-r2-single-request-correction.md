# R2 single-provider-request correction

## Status

This correction replaces the executable R2 entrypoint before any R2 provider
request or block authorization is recorded.

The original guarded control plane delegates through the historical pilot
implementation. That implementation performs a model-availability preflight
against `GET /v1/models/{model}` before it sends the Responses API generation.
The R2 authorization policy permits one provider request per slot, so the
preflight would exceed the authorized request count.

No R2 provider request was made before this defect was detected.

## Canonical entrypoint

All R2 commands must now use:

```text
openai_gpt56_r2_single_request.py
```

The historical entrypoint `openai_gpt56_r2.py` remains an implementation module
for the control plane but is not an authorized R2 execution entrypoint.

The canonical wrapper:

- binds the exact preregistered request alias `gpt-5.6-sol` offline;
- performs no model-preflight HTTP request;
- keeps the exact model identifier in the sealed request;
- preserves the provider response model label in captured transport metadata;
- permits no fallback or silent substitution;
- leaves the single authorized Responses API POST as the only provider HTTP
  request reachable for a slot;
- binds both the wrapper and the underlying control-plane module into the
  benchmark lock;
- restores the historical preflight function and execution references after
  every invocation.

## Corrected commands

Initialization and status may be run through the corrected entrypoint:

```powershell
py -3 .\openai_gpt56_r2_single_request.py status
```

A new block authorization must be created only after this correction is merged
and pulled to the campaign machine:

```powershell
py -3 .\openai_gpt56_r2_single_request.py authorize-block `
  --operator "Matthew Neal" `
  --block 1 `
  --rationale "Authorize only R2 block 1 through the corrected single-request entrypoint."
```

Each exact slot is then executed through the same entrypoint:

```powershell
py -3 .\openai_gpt56_r2_single_request.py execute-next `
  --operator "Matthew Neal" `
  --block-authorization "<canonical block authorization path>" `
  --execute
```

## Authority reset

Any human authorization stated before this correction is not used to create a
block-authorization record. A fresh authorization must explicitly bind:

- the corrected entrypoint;
- the merged correction commit;
- R2 block 1 only;
- slots 001 through 004 in fixed order;
- one Responses API POST and one attempt per slot;
- no retries, replacements, tools, storage, reordering, fallback, or
  substitution;
- no judgment, ratification, publication, promotion, ranking, release, or later
  block.
