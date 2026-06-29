"""GroundLedger core: engine, store, ledger, replay, report, api.

Stdlib-only. Reuses ``sfa`` for the deterministic verifier, canonical hashing,
and failure-family classification. Designed to run inside a customer VPC with no
network egress.
"""
# Submodules are imported explicitly where used (engine, store, ledger, replay,
# report, export, rulepacks, api). They are intentionally not eagerly imported
# here so that `python -m product.groundledger.<module>` entry points run cleanly.

