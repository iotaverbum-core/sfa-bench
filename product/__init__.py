"""GroundLedger product layer.

A thin SaaS layer built on top of the deterministic ``sfa`` research core. It
turns the verifier + sealing + tamper-evident ledger + replay into a sellable
"groundedness audit trail" for document-grounded AI assistants.

Nothing here modifies the protected research core (``sfa/verifier.py``,
``families.json``, ``sfa/categories.py``, ``history/occurrences.jsonl``). The
core is reused, not changed.
"""

__version__ = "0.1.0"
