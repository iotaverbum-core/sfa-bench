"""SFA-AutoLab v0 - auditable self-improvement under human ratification.

AutoLab lifts the SFA-Bench research pipeline one level: candidate patches to
this repository may be *proposed* by a builder, *verified* by frozen evaluators,
sealed, inscribed, and *promoted only by a human*. This package holds the
AutoLab scaffolding; the parts of it that the loop must never rewrite live in
the frozen zone (see ``autolab/frozen_zone.py`` and
``autolab/frozen_manifest.json``).

Item 4 adds human ratification: a deterministic gate-green candidate is still not
promoted unless a sealed human approval record and matching token authorize it.
"""
from __future__ import annotations

__all__ = ["controller", "frozen_zone", "preregistration", "ratification"]
