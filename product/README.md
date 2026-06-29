# GroundLedger

**A tamper-evident audit trail that proves your AI assistant's answers were
grounded in your source documents — and that you didn't hide the ones that
weren't.**

GroundLedger is a thin product layer on top of the deterministic `sfa` research
core in this repository. It reuses the verifier, canonical hashing, and
failure-family classifier unchanged, and adds the pieces a paying customer needs:
a per-tenant store, a hash-chained receipt ledger, independent replay, an audit
report, and a zero-dependency HTTP API that can run inside a customer VPC.

It is **stdlib-only** and makes **no model calls and no network calls.** That is
a feature: regulated buyers can run it next to their pipeline without sending
documents or answers to a third party.

## What it does

For each assistant answer you submit `{answer + citations, the evidence it used,
a rule pack}`. GroundLedger returns a deterministic **PASS/FAIL with a
categorized reason** (`FABRICATED_ENTITY`, `CONTRADICTS_EVIDENCE`,
`UNSUPPORTED_CLAIM`, `MISSING_REQUIRED_FIELD`, `SCHEMA_VIOLATION`), **seals it**
into a content-addressed receipt, and **appends it** to an append-only,
hash-chained ledger. Anyone can later **replay** the ledger and independently
reproduce every verdict — and any edit to the record is detected.

## Run the demo

```bash
python -m product.demo
```

It verifies four insurance answers (one grounded, three not), prints the audit
report, then quietly forges a sealed failure into a pass and shows replay
catching it: **TAMPER DETECTED**.

## Run the tests

```bash
python -m unittest discover -s product -t . -p 'test_*.py'
```

## Run the API (in-VPC, zero dependencies)

```bash
python -m product.groundledger.api
# POST a submission:
curl -s -X POST http://127.0.0.1:8000/v1/verify \
  -H 'X-API-Key: demo-key' -H 'Content-Type: application/json' \
  --data @product/examples/fabricated_citation.json
# Export the audit report:
curl -s http://127.0.0.1:8000/v1/audit-report -H 'X-API-Key: demo-key'
```

## Independently re-attest a tenant (the "stranger trust" check)

```bash
python -m product.groundledger.replay <data_root> <tenant>
```

## What is reused vs. new

| Reused from `sfa/` (unchanged) | New in `product/groundledger/` |
|---|---|
| `verifier.verify` (deterministic judgment) | `engine.py` — submission → sealed receipt |
| `families.classify_family` | `ledger.py` — hash-chained receipt ledger |
| `hashing.sha256_hex` (content addressing) | `store.py` — per-tenant filesystem store |
| history-blind / gold-blind invariants | `replay.py` — independent attestation |
| | `report.py` — exportable audit report |
| | `api.py` — stdlib HTTP backend |
| | `rule_packs/insurance_v1.json` — domain rule pack |

The protected research core (`sfa/verifier.py`, `families.json`,
`sfa/categories.py`, `history/occurrences.jsonl`) is **not modified**; the
repository release gate still passes.

## Honest scope of v1

v1 verifies **structured, cited answers** (JSON-mode / function-calling RAG with
explicit citation ids and `{subject, value}` claims). Turning free-text answers
into structured claims deterministically is the main piece of follow-on work and
is tracked in [`LAUNCH_PLAN.md`](LAUNCH_PLAN.md). "Tamper-evident" means a covered
edit breaks an integrity check; it is not a cryptographic tamper-proof guarantee.
