# Campaign Evidence Ratification

`campaign_ratification_cli.py` records an explicit human disposition for one verified, secret-free campaign `review-bundle.json`.

The ratification layer is deliberately separate from the alpha.2 capture run. It does not add lifecycle events to the original run, rewrite its `ratification_status`, or change any captured, sealed, judged, or review-bundle bytes. Instead, it creates an immutable companion packet and lineage record under `out/campaign_ratifications/`.

## Authority vocabulary

The CLI reuses the Item 10 human-action vocabulary:

- `--prepare` creates `RATIFICATION_READY`; it is not an explicit disposition.
- `--ratify` creates `RATIFIED`; it accepts the sealed deterministic judgment for the named execution.
- `--reject` creates `REJECTED_BY_HUMAN`; it disputes that deterministic judgment.
- `--halt` creates `HALTED_BY_HUMAN`; it defers disposition and stops that evidence workflow.

`--ratify` does **not** endorse a provider or model, attest provider identity, promote a candidate, publish evidence, create a release, or grant legal or regulatory approval. All of those effects are explicitly `false` or `none` in the packet and lineage record.

## Source verification

Before any human record is written, the CLI independently checks the public review bundle:

- canonical JSON bytes and outer bundle digest;
- benchmark-lock digest and campaign binding;
- complete capture-manifest shape and digest;
- raw-evidence hash binding, including the judged response hash;
- deterministic judgment content and artifact digests;
- the complete lifecycle event sequence, event hashes, previous-hash chain, seal event, and judgment event;
- the embedded integrity-report digest and cross-bindings;
- `unratified`, body-free, non-approval source status.

A modified summary cannot be ratified merely by recomputing the outer bundle digest; the nested manifest, judgment, lifecycle, and integrity seals must all reproduce.

## Usage

Prepare only:

```powershell
py -3 campaign_ratification_cli.py `
  --review-bundle "C:\path\to\review-bundle.json" `
  --reviewer "Matthew Neal" `
  --prepare
```

Explicitly accept a deterministic judgment:

```powershell
py -3 campaign_ratification_cli.py `
  --review-bundle "C:\path\to\review-bundle.json" `
  --reviewer "Matthew Neal" `
  --rationale "The frozen task required customer_id to survive; the state_loss judgment is accurate." `
  --ratification-id "rat-sol-pilot-002" `
  --ratify
```

The reviewer identity and rationale are intentionally included in the companion packet. Do not place credentials, private keys, tokens, or confidential personal information in either field.

## Outputs

Each ratification directory contains:

- `ratification-packet.json` — canonical, hash-sealed human disposition;
- `ratification-packet.md` — an inspectable summary of the same bounded decision;
- `lineage-record.json` — a separately sealed record binding the decision to the source bundle and packet.

The output directory can be changed with `SFA_CAMPAIGN_RATIFICATION_ROOT`.

Schemas:

- `campaigns/ratification/schemas/campaign-ratification-packet.schema.json`
- `campaigns/ratification/schemas/campaign-ratification-lineage.schema.json`

## Non-effects

A ratification companion does not mutate the source run. It also does not make one pilot execution representative of a model, provider, release family, or broader benchmark population. Comparative or general performance claims require separately preregistered repeated campaigns.
