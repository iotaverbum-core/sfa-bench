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

# Taxonomy file schema versions. v1 = families only (parent/child tree). v2 adds a
# typed directed causal-edge overlay ("edges"). v2 is backward compatible: a v1
# file (no "edges") loads as an empty edge set, and `migrate_to_v2` upgrades one.
TAXONOMY_SCHEMA_V1 = "sfa.taxonomy_schema.v1"
TAXONOMY_SCHEMA_V2 = "sfa.taxonomy_schema.v2"

CATEGORY_TO_FAMILY = {
    categories.UNSUPPORTED_CLAIM: "unsupported_claim",
    categories.CONTRADICTS_EVIDENCE: "contradicts_evidence",
    categories.FABRICATED_ENTITY: "fabricated_entity",
    categories.MISSING_REQUIRED_FIELD: "missing_required_field",
    categories.SCHEMA_VIOLATION: "schema_violation",
}


class Taxonomy:
    def __init__(self, families, edges=None, schema_version=None):
        self._parent = {}
        self._label = {}
        self._children = {}
        self.schema_version = schema_version or TAXONOMY_SCHEMA_V1
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

        self._load_edges(edges or [])

    def _load_edges(self, edges):
        """Load and validate the typed directed causal-edge overlay (a DAG)."""
        self._effects = {}   # source -> [(target, type)]
        self._causes = {}    # target -> [(source, type)]
        self._edge_type = {}
        seen_pairs = set()
        for edge in edges:
            source = edge.get("from")
            target = edge.get("to")
            edge_type = edge.get("type")
            if source not in self._parent:
                raise ValueError(f"causal edge references unknown family {source!r}")
            if target not in self._parent:
                raise ValueError(f"causal edge references unknown family {target!r}")
            if not edge_type:
                raise ValueError(f"causal edge {source!r}->{target!r} has no type")
            if source == target:
                raise ValueError(f"causal edge is a self-loop at {source!r}")
            if (source, target) in seen_pairs:
                raise ValueError(f"duplicate causal edge {source!r}->{target!r}")
            seen_pairs.add((source, target))
            self._effects.setdefault(source, []).append((target, edge_type))
            self._causes.setdefault(target, []).append((source, edge_type))
            self._edge_type[(source, target)] = edge_type
        self._assert_edge_dag()

    def _assert_edge_dag(self):
        """Detect a cycle in the directed causal-edge graph (parent tree is separate)."""
        WHITE, GREY, BLACK = 0, 1, 2
        color = {fid: WHITE for fid in self._parent}

        def visit(node, path):
            color[node] = GREY
            for target, _type in sorted(self._effects.get(node, [])):
                if color[target] == GREY:
                    cycle = " -> ".join(path + [target])
                    raise ValueError(f"cycle detected in causal edges: {cycle}")
                if color[target] == WHITE:
                    visit(target, path + [target])
            color[node] = BLACK

        for fid in sorted(self._parent):
            if color[fid] == WHITE:
                visit(fid, [fid])

    def has_edges(self):
        return bool(self._edge_type)

    def edges(self):
        """Return the causal edges as sorted {from, to, type} dicts."""
        return [
            {"from": source, "to": target, "type": self._edge_type[(source, target)]}
            for source, target in sorted(self._edge_type)
        ]

    def effects(self, family_id):
        """Downstream families this family points to (direct causal successors)."""
        return sorted((target, etype) for target, etype in self._effects.get(family_id, []))

    def causes(self, family_id):
        """Upstream families that point to this family (direct causal predecessors)."""
        return sorted((source, etype) for source, etype in self._causes.get(family_id, []))

    def edge_type(self, source, target):
        return self._edge_type.get((source, target))

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


def taxonomy_schema_version(data):
    """Return the declared taxonomy-file schema version (defaults to v1)."""
    return data.get("taxonomy_schema_version", TAXONOMY_SCHEMA_V1)


def migrate_to_v2(data, edges=None):
    """Upgrade a v1 taxonomy dict to v2 by adding a schema version and edges.

    Backward compatible and idempotent: an already-v2 file keeps its edges unless
    a new edge list is supplied. Families are never altered.
    """
    migrated = dict(data)
    migrated["taxonomy_schema_version"] = TAXONOMY_SCHEMA_V2
    if edges is not None:
        migrated["edges"] = list(edges)
    else:
        migrated.setdefault("edges", list(data.get("edges", [])))
    # Validate the result (unknown endpoints, self-loops, duplicates, cycles).
    Taxonomy(migrated["families"], edges=migrated["edges"], schema_version=TAXONOMY_SCHEMA_V2)
    return migrated


def load_taxonomy(path):
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    taxonomy = Taxonomy(
        data["families"],
        edges=data.get("edges"),
        schema_version=taxonomy_schema_version(data),
    )
    return taxonomy, data.get("taxonomy_version", "unknown")


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
    offending claim makes that possible. Deferred-consequence scoring evidence
    (marked with ``task_family == "deferred_consequence"``) refines a contradiction
    into the ``deferred_consequence_stale`` leaf, since the characteristic failure
    of that task family is preserving the pre-update (stale) value. All other
    categories map directly to a root family. This is deliberately simple and
    deterministic, and inspects only structured evidence - never a model's opinion
    and never the expected verdict.
    """
    if isinstance(evidence, dict) and evidence.get("task_family") == "deferred_consequence":
        if category == categories.CONTRADICTS_EVIDENCE:
            return "deferred_consequence_stale"
        return "deferred_consequence"
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
