"""Frontier Delta Suite v0.

The Frontier Delta Suite establishes a frozen behavioural fixture baseline so
that later, independently identified candidate artifacts can be rerun against
the same unchanged suite and compared as measured behavioural deltas. Model
names retained in historical fixtures are labels, not verified provider
provenance or availability claims.

Scope and honesty:
  * This suite measures behaviour under specific benchmark pressure across eight
    lanes. It does **not** claim AGI or general intelligence. It reports whether a
    model preserves truth, state, objective, and accountability across long,
    open-ended, tool-mediated tasks - nothing more.
  * Scoring is fixture-based and deterministic wherever possible, so CI can run it
    without live API calls. Lanes that cannot be fully decided by machine are
    marked ``rubric_assisted`` and explain why.

The suite reuses the SFA-Bench core conventions (canonical hashing, sealed
artifacts, deterministic replay) and never mutates the ``sfa`` research core.
"""
from . import schemas  # noqa: F401

SUITE_NAME = "Frontier Delta Suite"
SUITE_VERSION = schemas.SUITE_VERSION
__version__ = "0.1.0"
