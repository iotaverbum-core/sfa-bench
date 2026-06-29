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

## Phase 1 demo (the sales-call path)

One command runs the whole thing on bundled sample data:

```bash
./scripts/demo.sh          # or: python -m product.demo
```

**For whom:** a Head of AI / founding engineer at an insurance or fintech company
whose document-grounded assistant must pass AI-risk review and produce an audit
trail.

**What it does:** verifies four insurance answers against the evidence each used,
then writes two artifacts to `product/data/demo/`:

- `report.html` — a customer-facing audit report you open in a browser (or print
  to PDF): a plain-language summary, **severity-ranked findings** (critical /
  high / medium) each with *what we detected*, *why it matters*, and a
  *recommended action*, the sealed ledger, and an independent **VERIFIED** badge.
- `bundle.json` — a signed, self-verifying bundle an auditor checks offline.

It then quietly forges a sealed failure into a pass and shows replay catching it:
**TAMPER DETECTED**.

**Sample input** (`product/examples/grounded_answer.json`): an answer with
`conclusion`, `cited_evidence` ids, and `{subject, value}` claims, plus the
`evidence` (`documents` + `facts`) it used.

**Sample output** (abridged):

```
1 of 4 answers (25%) were grounded in the provided evidence. 3 answer(s) were
flagged: 2 critical, 1 high. The audit trail is intact (independently attested).

Findings (highest severity first):
  [CRITICAL] Fabricated citation - ans_fabricated_002
      detected: cited evidence id(s) not present in evidence: clause_9z
      action  : Block the answer and route to human review ...
```

**What the result means:** a low groundedness rate or any *critical* finding is a
ship-blocker; the **VERIFIED**/**TAMPER DETECTED** badge is the auditor-grade
guarantee that the record itself wasn't edited.

**Known limitations:** v1 checks **structured, cited answers** (JSON-mode /
function-calling RAG); HMAC signing is keyed integrity, not public-key
non-repudiation; rule packs are intentionally narrow (insurance v1 shipped).

**Next product step:** free-text → structured **claim extraction** so any RAG
answer can be checked, kept deterministic by sealing the extraction step.

## Run the tests

```bash
python -m unittest discover -s product -t . -p 'test_*.py'
```

## Integrate with the Python SDK (an afternoon, no server needed)

```python
from product.sdk import GroundLedgerClient

# Embedded: seals a tamper-evident ledger to a local directory, no server.
gl = GroundLedgerClient.embedded(data_root="gl-data", tenant="acme",
                                 rule_pack="insurance_v1")

receipt = gl.verify(answer_id="ans_1", candidate=answer, evidence=chunks)
if not gl.is_grounded(receipt):
    log.warning("ungrounded: %s", receipt["explanation"])  # gate or flag

report = gl.audit_report()      # groundedness rate + attestation
bundle = gl.audit_export()      # portable, self-verifying audit bundle
```

Point the same client at an in-VPC server instead with
`GroundLedgerClient.http(base_url=..., api_key=...)`. Runnable example:

```bash
python -m product.sdk.example
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

## Export a portable, self-verifying audit bundle

This is the artifact a customer hands to their buyer, auditor, or regulator. It
embeds the ledger, receipts, submissions, and the exact rule packs used, plus a
content hash and an optional HMAC signature — so it can be **reproduced offline
with one command**, without access to the live system.

```bash
# build a signed bundle + a printable (print-to-PDF) HTML report
python -m product.groundledger.export build <data_root> <tenant> \
  --out bundle.json --html report.html --key SHARED_SECRET

# the auditor verifies it offline (re-derives every verdict from the bundle)
python -m product.groundledger.export verify bundle.json --key SHARED_SECRET
```

Verification fails (`TAMPER DETECTED`) if the bundle content, the signature, any
sealed receipt, or the ledger chain was edited. The same bundle is available over
the API at `GET /v1/audit-export`.

## Deploy in your VPC (one command, no dependencies)

```bash
docker build -t groundledger -f product/Dockerfile .
docker run -p 8000:8000 -v gl-data:/data \
  -e GROUNDLEDGER_API_KEYS="prod-key:acme-insurance" \
  -e GROUNDLEDGER_SIGNING_KEYS="acme-insurance:CHANGE_ME" \
  groundledger
```

The image is `python:3.11-slim` plus this repo — no pip install, no network
egress. Data persists in the mounted volume.

## What is reused vs. new

| Reused from `sfa/` (unchanged) | New in `product/groundledger/` |
|---|---|
| `verifier.verify` (deterministic judgment) | `engine.py` — submission → sealed receipt |
| `families.classify_family` | `ledger.py` — hash-chained receipt ledger |
| `hashing.sha256_hex` (content addressing) | `store.py` — per-tenant filesystem store |
| history-blind / gold-blind invariants | `replay.py` — independent attestation |
| | `report.py` — exportable audit report |
| | `export.py` — signed, self-verifying audit bundle + HTML |
| | `api.py` — stdlib HTTP backend |
| | `sdk/` — embedded + HTTP Python client |
| | `Dockerfile` — one-command in-VPC deploy |
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
