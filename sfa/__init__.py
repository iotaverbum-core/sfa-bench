"""SFA-Bench v0.4: Sealed Failure Artifacts plus a minimal agent loop.

Reasoning failures are preserved, replayable, classified, hash-chained, and
analyzable as historical events. The trust layer can also detect attempts to
corrupt, launder, rewrite, or contaminate that history.

stdlib only; no network, no LLM, no hidden repair.
"""
from . import agent, artifact, case, categories, families, hashing, history, ledger, model_adapter, tamper, validation, verifier  # noqa: F401

__version__ = "0.4.0"
