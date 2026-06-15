"""Failure taxonomy: hierarchical families with deterministic classification.

The taxonomy is declared in families.json and is the single source of truth for
inheritance. Artifacts store only the leaf `failure_family`; parents, ancestry,
depth, and descendants are derived from the taxonomy. This prevents the
hierarchy from drifting across artifacts.

Classification is model-agnostic. It inspects structured evidence and candidate
objects, never a model's opinion and never the expected verdict.
"""
import json
import re

from . import categories

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}")

CATEGORY_TO_FAMILY = {
    categories.UNSUPPORTED_CLAIM: "unsupported_claim",
    categories.CONTRADICTS_EVIDENCE: "contradicts_evidence",
    categories.FABRICATED_ENTITY: "fabricated_entity",
    categories.MISSING_REQUIRED_FIELD: "missing_required_field",
    categories.SCHEMA_VIOLATION: "schema_violation",
}


class Taxonomy:
    def __init__(self, families):
        self._parent = {}
        self._label = {}
        self._children = {}
        for fam in families:
            fid = fam["id"]
            parent = fam.get("parent")
            self._parent[fid] = parent
            self._label[fid] = fam.get("label", fid)
            self._children.setdefault(fid, [])
        for fid, parent in self._parent.items():
            if parent is not None:
                self._children.setdefault(parent, []).append(fid)

        # Validate after loading so bad taxonomies fail loudly.
        for fid, parent in self._parent.items():
            if parent is not None and parent not in self._parent:
                raise ValueError(f"family {fid!r} refers to unknown parent {parent!r}")
            self.ancestry(fid)  # detects loops through the `seen` guard

    def known(self, family_id):
        return family_id in self._parent

    def parent(self, family_id):
        return self._parent.get(family_id)

    def label(self, family_id):
        return self._label.get(family_id, family_id)

    def children(self, family_id):
        return sorted(self._children.get(family_id, []))

    def ancestry(self, family_id):
        """Root -> ... -> leaf, inclusive."""
        if family_id not in self._parent:
            return [family_id]
        chain = []
        cur = family_id
        seen = set()
        while cur is not None:
            if cur in seen:
                raise ValueError(f"cycle detected in taxonomy at {cur!r}")
            seen.add(cur)
            chain.append(cur)
            cur = self._parent.get(cur)
        return list(reversed(chain))

    def depth(self, family_id):
        return max(0, len(self.ancestry(family_id)) - 1)

    def descendants(self, family_id):
        out = []
        stack = list(self._children.get(family_id, []))
        while stack:
            fid = stack.pop(0)
            out.append(fid)
            stack.extend(self._children.get(fid, []))
        return out

    def all_ids(self):
        return sorted(self._parent.keys())


def load_taxonomy(path):
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    return Taxonomy(data["families"]), data.get("taxonomy_version", "unknown")


def _refine_unsupported(subject, value):
    subject = (subject or "").lower()
    if isinstance(value, bool):
        return "unsupported_claim"
    if isinstance(value, (int, float)):
        return "unsupported_number"
    if isinstance(value, str) and _DATE_RE.match(value):
        return "unsupported_date"
    if any(k in subject for k in ("source", "author", "attribution", "attributed", "vendor", "speaker")):
        return "unsupported_attribution"
    if any(k in subject for k in ("citation", "cite", "reference", "record", "doc")):
        return "unsupported_citation"
    return "unsupported_claim"


def classify_family(category, candidate, evidence):
    """Map a verifier category to a deterministic leaf family.

    UNSUPPORTED_CLAIM is refined into number/date/attribution/citation where the
    offending claim makes that possible. All other categories map directly to a
    root family. This is deliberately simple and deterministic.
    """
    if category == categories.UNSUPPORTED_CLAIM:
        facts = {f.get("subject") for f in evidence.get("facts", []) if isinstance(f, dict)}
        for claim in candidate.get("claims", []):
            if not isinstance(claim, dict):
                return "schema_violation"
            subj = claim.get("subject")
            if subj not in facts:
                return _refine_unsupported(subj, claim.get("value"))
        return "unsupported_claim"
    return CATEGORY_TO_FAMILY.get(category, "uncategorized")
