"""SFA-AutoLab v0 — auditable self-improvement under human ratification.

AutoLab lifts the SFA-Bench research pipeline one level: candidate patches to
this repository may be *proposed* by a builder, *verified* by frozen evaluators,
sealed, inscribed, and *promoted only by a human*. This package holds the
AutoLab scaffolding; the parts of it that the loop must never rewrite live in
the frozen zone (see ``autolab/frozen_zone.py`` and
``autolab/frozen_manifest.json``).

Item 1 (this module set): the frozen-zone manifest, deterministic zone-hash
attestation, and the CI enforcement that fails any diff into the zone absent a
human amendment token.
"""
from __future__ import annotations

__all__ = ["frozen_zone"]
