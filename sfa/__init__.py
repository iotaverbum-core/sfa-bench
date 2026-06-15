"""SFA-Bench v0.2: Sealed Failure Artifacts plus failure history.

Reasoning failures are preserved, replayable, classified, hash-chained, and
analyzable as historical events. stdlib only; no network, no LLM, no repair.
"""
from . import artifact, case, categories, families, hashing, history, ledger, verifier  # noqa: F401

__version__ = "0.2.0"
