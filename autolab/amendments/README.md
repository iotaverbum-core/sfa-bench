# Frozen-zone amendment channel (human-only)

This directory is the **human-only amendment channel** for the SFA-AutoLab
frozen zone. It is **not** itself frozen — otherwise adding an amendment would
require an amendment, forever.

The AutoLab loop must never write here. A frozen-zone change is legitimate only
when a human, working *outside* the loop:

1. Edits the frozen file(s) and/or the manifest's `frozen_paths`.
2. Reseals the manifest: `python frozen_zone_check.py seal`.
3. Adds one append-only amendment record `autolab/amendments/<amendment_id>.json`
   describing exactly the `prev_zone_hash -> new_zone_hash` transition.
4. Supplies the matching amendment token to CI via the protected input
   `SFA_FROZEN_ZONE_AMENDMENT_TOKEN` (a value the automated builder cannot set).

Amendment record schema (`sfa.autolab.frozen_zone.amendment.v0`):

```json
{
  "schema": "sfa.autolab.frozen_zone.amendment.v0",
  "amendment_id": "<token; also the record filename stem>",
  "manifest_version": "fz-v0.2.0",
  "prev_zone_hash": "<sealed zone_hash before the change>",
  "new_zone_hash": "<sealed zone_hash after the change>",
  "reason": "why this frozen-zone change is authorized",
  "author": "human name / handle",
  "authored_on": "YYYY-MM-DD"
}
```

The gate (`autolab/frozen_zone.py::check_amendment_gate`) accepts the change only
if a record's `amendment_id` equals the supplied token, its `new_zone_hash`
equals both the current computed zone hash and the sealed manifest `zone_hash`,
and its `prev_zone_hash` equals the base's sealed `zone_hash`.
