"""Canonical, deterministic hashing for SFA-Bench.

Every hash in the benchmark is computed over a canonical JSON encoding:
sorted keys, tight separators, UTF-8. A hash is therefore a function of the
*content* of an object, independent of key order or incidental whitespace.
That property is what lets a sealed artifact be content-addressed and
replay-verified: the same failure always hashes to the same value, and any
edit changes the hash.
"""
import hashlib
import json


def canonical_bytes(obj) -> bytes:
    """Deterministic byte encoding of a JSON-serialisable object."""
    return json.dumps(
        obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def sha256_hex(obj) -> str:
    """SHA-256 hex digest of an object's canonical encoding."""
    return hashlib.sha256(canonical_bytes(obj)).hexdigest()
