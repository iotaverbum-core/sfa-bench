"""Failure categories for SFA-Bench.

A category names *why* a candidate answer was rejected. Categories are
verifier-assigned, deterministic, and sealed into the artifact. They are the
unit a downstream learner would cluster on, so they must be stable across runs
and machines.
"""

# Reasoning failures - the cases this benchmark exists to catch.
CONTRADICTS_EVIDENCE = "CONTRADICTS_EVIDENCE"   # a claim conflicts with a fact in evidence
UNSUPPORTED_CLAIM = "UNSUPPORTED_CLAIM"         # a claim has no supporting fact in evidence
FABRICATED_ENTITY = "FABRICATED_ENTITY"         # cites an evidence id that does not exist

# Structural failures - malformed answers, caught before reasoning is judged.
MISSING_REQUIRED_FIELD = "MISSING_REQUIRED_FIELD"
SCHEMA_VIOLATION = "SCHEMA_VIOLATION"

ALL = (
    CONTRADICTS_EVIDENCE,
    UNSUPPORTED_CLAIM,
    FABRICATED_ENTITY,
    MISSING_REQUIRED_FIELD,
    SCHEMA_VIOLATION,
)
