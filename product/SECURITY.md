# Security & Privacy - GroundLedger

Scope: the GroundLedger product layer in `product/`. Claims here are stated to be
checkable against the source; if you find a discrepancy, treat the code as
authoritative and tell us (see Reporting).

## Data handled

- **Your answers and evidence.** Submitted to the engine as function/CLI arguments
  or HTTP request bodies. Written to the local store you configure
  (`GROUNDLEDGER_DATA`) as submissions, sealed receipts, and a ledger.
- **No external transmission by the core.** The verifier, extraction, replay,
  export, and report code make no network calls and load no remote resources. You
  can confirm this: there are no `requests`/`urllib`/socket calls in the core
  modules. The only networking in the product is the **client SDK's HTTP
  transport** (talking to a server you run) and the **HTTP API server** itself.

## Network access

- **Core checks (verify, replay, export, report, engine, extraction):** none.
- **API server (`api.py`):** binds a local HTTP socket you configure; serves only
  the documented endpoints; no outbound calls.
- **SDK HTTP transport:** connects only to the base URL you pass, and explicitly
  bypasses environment proxies (no accidental egress through a proxy).
- There is no telemetry, analytics, phone-home, license check, or update check.

## Secrets & environment variables

See `product/.env.example`. None are needed for the core checks. For the API:

- `GROUNDLEDGER_API_KEYS` - API-key-to-tenant map; treat keys like passwords.
- `GROUNDLEDGER_SIGNING_KEYS` - optional HMAC signing keys for exports. **Keyed
  integrity, not non-repudiation.** Anyone with the key can sign; keep them secret.
- The app does not auto-load `.env`; you export these yourself or pass via Docker.

## Local files written

- Under `GROUNDLEDGER_DATA` (default `product/data/`, git-ignored): one directory
  per tenant containing `submissions/`, `receipts/`, and `ledger.jsonl`.
- The demo writes `product/data/demo/` (report.html, bundle.json) - git-ignored.
- Identifiers are validated (`store.py`) against `^[A-Za-z0-9._-]{1,128}$` to keep
  tenant/answer ids from escaping the data directory.

## Third-party services & dependencies

- **None at runtime.** Zero third-party Python dependencies (stdlib only); see
  `pyproject.toml` (`dependencies = []`). No subprocessors are required to run the
  checks. The optional `pip install` uses standard build tooling but installs no
  runtime packages.
- The optional Docker image is `python:3.11-slim` plus this repository.

## Known risks & limitations

- **Tamper-evident, not tamper-proof.** An operator with write access to the store
  and the signing key can attempt an internally consistent forgery; detection
  relies on an independent copy + replay. Keep an off-box copy of bundles you care
  about.
- **API authentication is a static API-key check.** There is no rate limiting,
  RBAC, SSO, or audit logging of access in v1. Run the API on a trusted network or
  behind your own gateway. Do not expose it to the public internet as-is.
- **HMAC, not PKI.** Export signatures prove the holder of the shared key produced
  them; they do not prove *which* party did, and do not survive key compromise.
- **No encryption at rest** is provided by the product; rely on your disk/volume
  encryption for the data directory.

## Safe usage recommendations

- Run in your own environment/VPC; keep `GROUNDLEDGER_HOST=127.0.0.1` or behind a
  gateway. Generate strong random API and signing keys; rotate on suspicion.
- Keep independent copies of export bundles so replay can detect store tampering.
- Verify exports on a machine the producer does not control.

## Reporting a vulnerability

Email the maintainer (see `CITATION.cff` / repository contact) with steps to
reproduce. Please do not open a public issue for an unfixed security report.
There is no formal SLA yet; we will acknowledge and triage as fast as we can.
