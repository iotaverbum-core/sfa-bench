"""SFA-Bench v2.0.0-alpha.2: Locked campaign execution and evidence capture.

Reasoning failures are preserved, replayable, classified, hash-chained, and
analyzable as historical events. The trust layer can also detect attempts to
corrupt, launder, rewrite, or contaminate that history.

stdlib only by default; no network, no LLM, no hidden repair.
"""
from . import adapters, agent, artifact, case, categories, external_adapter, families, fingerprints, hashing, history, ledger, model_adapter, policy, provenance, rederive, tamper, transcript, validation, verifier  # noqa: F401

__version__ = "2.0.0a2"
