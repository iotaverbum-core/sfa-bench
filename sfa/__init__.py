"""SFA-Bench v0.3: Sealed Failure Artifacts plus tamper detection.

Reasoning failures are preserved, replayable, classified, hash-chained, and
analyzable as historical events. The trust layer can also detect attempts to
corrupt, launder, rewrite, or contaminate that history.

stdlib only; no network, no LLM, no repair.
"""
from . import artifact, case, categories, families, hashing, history, ledger, tamper, validation, verifier  # noqa: F401

__version__ = "0.3.0"
