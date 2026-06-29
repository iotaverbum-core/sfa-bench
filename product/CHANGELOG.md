# GroundLedger Changelog

GroundLedger is the commercial product layer built on top of the `sfa` research
core. It is versioned **independently** of the SFA-Bench research instrument and
is not part of that instrument's release line or Zenodo DOI.

## Unreleased

No unreleased changes.

## v0.1.0 — Initial product layer

### Added

- Verification engine: a free-text or structured answer + the evidence it used →
  a deterministic, content-addressed groundedness receipt (`engine.py`,
  reusing the unchanged `sfa` verifier, classifier, and hashing).
- Per-tenant, append-only, hash-chained receipt ledger and filesystem store
  (`ledger.py`, `store.py`).
- Independent replay / attestation that re-derives every verdict and detects
  receipt, submission, and ledger tampering (`replay.py`).
- Deterministic free-text → structured extraction, sealed and re-run during
  replay; reliably catches fabricated citations and contradictions
  (`extraction.py`).
- Customer-facing audit report with severity-ranked findings and recommended
  actions, plus a signed, self-verifying export bundle and printable HTML
  (`report.py`, `export.py`, `findings.py`).
- Stdlib-only HTTP API and one-command in-VPC Dockerfile (`api.py`, `Dockerfile`).
- Python SDK with embedded and HTTP transports (`sdk/`).
- Two vertical rule packs: `insurance_v1` and `fintech_v1`.
- One-command demo (`scripts/demo.sh`) and 49 tests.

### Boundaries

- Stdlib-only; no model calls and no network egress.
- The protected `sfa` research core is reused unchanged.
- v1 free-text extraction is deterministic and conservative (under-reports rather
  than fabricates findings); structured/cited answers get the strongest coverage.
