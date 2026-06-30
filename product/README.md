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

> Evaluating this without trusting us? Start with
> [`TRUST_MODEL.md`](TRUST_MODEL.md) (what it does and does not prove) and
> [`SECURITY.md`](SECURITY.md), then run `make verify` (below) to reproduce the
> results and confirm tampering is detected - all offline.

## Install & verify from a clean checkout

Requirements: **Python 3.11+ and git only**. No third-party packages, no API keys,
no network. From a fresh clone:

```bash
make test     # product test suite (unittest, no deps)
make demo     # end-to-end demo -> writes product/data/demo/report.html + bundle.json
make verify   # reproducibility + tamper verification (the trust check)
```

`make verify` re-derives the committed example answers and asserts the hashes match
`product/verification/expected_manifest.json`, then confirms the committed corrupted
bundle (`product/verification/tampered_bundle.json`) is rejected. Expected output
ends with `final status: VERIFIED`.

Optional - install the `groundledger` CLI (still zero runtime dependencies):

```bash
make setup            # python -m pip install -e .
groundledger verify   # same trust check, as a command
groundledger --help   # replay / export / serve / demo
```

Every target also works without `make` or install via `python -m ...` (see each
section below). The research core remains separately runnable with no install:
`python verify_all.py`.

### Platform notes & troubleshooting

- **Python:** 3.11+ is required (uses `X | Y` type syntax and `ThreadingHTTPServer`).
  Check with `python3 --version`.
- **Run from the repo root.** `make demo` / `make verify` read `product/examples/`
  and write under `product/data/` (git-ignored) using paths relative to the checkout.
- **`make verify` fails with `manifest_mismatch`?** That means a re-derived hash
  drifted from the committed manifest. If you changed examples, the rule pack, or
  the tool version on purpose, regenerate with
  `python -m product.groundledger.verification --update` and review the diff.
  If you changed nothing, that is a real reproducibility failure - tell us.
- **`pip install -e .` offline:** `make setup` passes `--no-build-isolation` and
  degrades gracefully; if it can't run, the `python -m` / `make` paths still work.
- **Windows:** `make` may be unavailable; run the underlying `python -m ...`
  commands shown in each section directly.

## What it does

For each assistant answer you submit `{answer + citations, the evidence it used,
a rule pack}`. GroundLedger returns a deterministic **PASS/FAIL with a
categorized reason** (`FABRICATED_ENTITY`, `CONTRADICTS_EVIDENCE`,
`UNSUPPORTED_CLAIM`, `MISSING_REQUIRED_FIELD`, `SCHEMA_VIOLATION`), **seals it**
into a content-addressed receipt, and **appends it** to an append-only,
hash-chained ledger. Anyone can later **replay** the ledger and independently
reproduce every verdict — and any edit to the record is detected.

Answers can be **structured** (JSON with explicit citations + claims) or
**free text**. For free text, a deterministic extractor turns the prose into the
structured candidate the verifier judges — and seals the extraction so replay
re-runs it. See [Free-text answers](#free-text-answers).

### Rule packs

A rule pack defines "what grounded means" for a domain (the citation/claim rules
plus the free-text extraction config). Shipped packs:

| Pack | For |
|---|---|
| `insurance_v1` | insurance policy Q&A (deductible, coverage limit, premium) |
| `fintech_v1` | consumer finance disclosure Q&A (APR, fees, limits) |

List them at `GET /v1/rule-packs`; pick one per request with `rule_pack=`. New
verticals are added by dropping a JSON pack into
`product/groundledger/rule_packs/` — no engine changes.

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

**Known limitations:** structured answers get the strongest guarantee; free-text
extraction is conservative (catches fabricated citations and contradictions on
evidence-covered facts, under-reports novel claims); HMAC signing is keyed
integrity, not public-key non-repudiation; rule packs are intentionally narrow
(insurance v1 shipped).

**Next product step:** Stripe billing + usage metering (once a pilot converts),
then a hosted report-view UI and additional vertical rule packs (fintech).

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

### Free-text answers

Most assistants emit prose, not JSON. Submit the raw answer text plus the
evidence it used; a **deterministic** extractor (`extraction.py`) turns it into
the structured candidate the verifier judges:

```python
receipt = gl.verify_text(
    answer_id="ans_42",
    answer_text="Good news - your deductible is only $500, per clause_3a and clause_9z.",
    evidence=chunks,
)
# -> FAIL / FABRICATED_ENTITY  (clause_9z is not in the evidence)
```

Or over HTTP: `POST /v1/verify-text`. The extraction is sealed into the receipt
and re-run during replay, so an edited answer or a doctored candidate is caught.

What v1 extraction reliably catches from prose:

- **Fabricated citations** — citation-shaped tokens not present in the evidence; and
- **Contradictions** — a value asserted for an evidence-covered fact (currency,
  number, percentage, date) that disagrees with the evidence.

It is deliberately **conservative**: it does not invent claims about subjects the
evidence does not cover, so it under-reports rather than fabricates findings.
Absence of findings on free text is therefore not a proof of full grounding — for
the strongest guarantee, have the assistant emit structured, cited answers.

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
| | `extraction.py` — deterministic free-text → structured candidate |
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
