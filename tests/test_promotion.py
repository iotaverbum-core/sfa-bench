"""Deterministic tests for promotion/rollback (stdlib unittest only).

Run from the repository root:

    python -m unittest discover -s tests -v

Covers the Item-4 acceptance criteria:
  * promote -> rollback -> replay round-trip restores the incumbent bit-exact;
  * promotion needs a human token AND a gate-green loop record (asymmetric);
  * tagged states pin the v-root anchor;
  * the lineage is append-only and hash-chained.
"""
from __future__ import annotations

from pathlib import Path
import sys
import unittest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from autolab import controller as ctrl  # noqa: E402
from autolab import promotion as promo  # noqa: E402

CONFIG = {"seed": 20260706, "n": 30, "bootstrap": 500}
ROOT_PAYLOAD = {"scaffold": "v0", "policy_order": ["a", "b", "c"]}
CANDIDATE_PAYLOAD = {"scaffold": "v1", "policy_order": ["a", "c", "b"]}
TOKEN = "human-approve-001"


def _green_loop():
    return ctrl.run_iteration(CONFIG).record


def _red_loop():
    return ctrl.run_iteration({**CONFIG, "arm_probabilities": {
        "candidate": 0.3, "incumbent": 0.7, "ancestor_anchor": 0.5}}).record


class PromotionGuardTests(unittest.TestCase):
    def setUp(self):
        self.incumbent = promo.make_root_state(ROOT_PAYLOAD)
        self.green = _green_loop()

    def test_promotion_refused_without_token(self):
        with self.assertRaises(promo.PromotionError) as ctx:
            promo.promote(self.incumbent, self.green, CANDIDATE_PAYLOAD, human_token=None)
        self.assertIn("human token", str(ctx.exception))

    def test_promotion_refused_with_red_gate(self):
        with self.assertRaises(promo.PromotionError) as ctx:
            promo.promote(self.incumbent, _red_loop(), CANDIDATE_PAYLOAD, human_token=TOKEN)
        self.assertIn("gate is not green", str(ctx.exception))

    def test_promotion_refused_if_loop_claims_self_promotion(self):
        tampered = dict(self.green)
        tampered["promotion"] = dict(tampered["promotion"])
        tampered["promotion"]["promoted"] = True
        with self.assertRaises(promo.PromotionError) as ctx:
            promo.promote(self.incumbent, tampered, CANDIDATE_PAYLOAD, human_token=TOKEN)
        self.assertIn("self-promote", str(ctx.exception))

    def test_authorization_must_bind_loop_hash(self):
        auth = {"schema": promo.AUTHORIZATION_SCHEMA, "token": TOKEN, "loop_hash": "wrong"}
        with self.assertRaises(promo.PromotionError) as ctx:
            promo.promote(self.incumbent, self.green, CANDIDATE_PAYLOAD,
                          human_token=TOKEN, authorization=auth)
        self.assertIn("loop_hash", str(ctx.exception))

    def test_valid_authorization_allows_promotion(self):
        auth = {"schema": promo.AUTHORIZATION_SCHEMA, "token": TOKEN,
                "loop_hash": self.green["loop_hash"]}
        promoted = promo.promote(self.incumbent, self.green, CANDIDATE_PAYLOAD,
                                 human_token=TOKEN, authorization=auth)
        self.assertEqual(promoted.origin, promo.ORIGIN_PROMOTION)
        self.assertEqual(promoted.loop_hash, self.green["loop_hash"])


class TaggedStateTests(unittest.TestCase):
    def test_root_is_anchor(self):
        root = promo.make_root_state(ROOT_PAYLOAD)
        self.assertEqual(root.tag, promo.ANCHOR_TAG)
        self.assertEqual(root.anchor_tag, promo.ANCHOR_TAG)
        self.assertEqual(root.sequence, 0)

    def test_promotion_pins_anchor_and_links_parent(self):
        root = promo.make_root_state(ROOT_PAYLOAD)
        promoted = promo.promote(root, _green_loop(), CANDIDATE_PAYLOAD, human_token=TOKEN)
        self.assertEqual(promoted.anchor_tag, promo.ANCHOR_TAG)
        self.assertEqual(promoted.parent_tag, root.tag)
        self.assertEqual(promoted.sequence, 1)
        self.assertEqual(promoted.state_hash, promo.payload_hash(CANDIDATE_PAYLOAD))


class RollbackTests(unittest.TestCase):
    def test_rollback_restores_incumbent_bit_exact(self):
        root = promo.make_root_state(ROOT_PAYLOAD)
        promoted = promo.promote(root, _green_loop(), CANDIDATE_PAYLOAD, human_token=TOKEN)
        restored = promo.rollback(promoted, root)
        self.assertEqual(restored.origin, promo.ORIGIN_ROLLBACK)
        self.assertEqual(restored.state_hash, root.state_hash)
        self.assertEqual(restored.payload, root.payload)
        self.assertTrue(promo.restores_bit_exact(restored, root))
        self.assertEqual(restored.restored_from, root.tag)

    def test_rollback_is_tagged_event(self):
        root = promo.make_root_state(ROOT_PAYLOAD)
        promoted = promo.promote(root, _green_loop(), CANDIDATE_PAYLOAD, human_token=TOKEN)
        restored = promo.rollback(promoted, root)
        # Rollback is append-only: a new tag/sequence, not a mutation of the root.
        self.assertNotEqual(restored.tag, root.tag)
        self.assertEqual(restored.sequence, promoted.sequence + 1)
        self.assertEqual(restored.anchor_tag, promo.ANCHOR_TAG)


class RoundTripTests(unittest.TestCase):
    def test_round_trip_restores_and_replays(self):
        loop = _green_loop()
        rt = promo.promote_rollback_round_trip(ROOT_PAYLOAD, loop, CANDIDATE_PAYLOAD,
                                               human_token=TOKEN)
        self.assertTrue(rt["restores_bit_exact"])
        self.assertEqual(rt["restored"]["state_hash"], rt["incumbent"]["state_hash"])
        replayed = promo.replay_round_trip(rt, ROOT_PAYLOAD, loop, CANDIDATE_PAYLOAD,
                                           human_token=TOKEN)
        self.assertTrue(replayed["attested"], replayed["issues"])
        self.assertEqual(replayed["round_trip_hash"], rt["round_trip_hash"])

    def test_round_trip_is_deterministic(self):
        loop = _green_loop()
        a = promo.promote_rollback_round_trip(ROOT_PAYLOAD, loop, CANDIDATE_PAYLOAD, human_token=TOKEN)
        b = promo.promote_rollback_round_trip(ROOT_PAYLOAD, loop, CANDIDATE_PAYLOAD, human_token=TOKEN)
        self.assertEqual(a["round_trip_hash"], b["round_trip_hash"])

    def test_lineage_is_hash_chained(self):
        loop = _green_loop()
        rt = promo.promote_rollback_round_trip(ROOT_PAYLOAD, loop, CANDIDATE_PAYLOAD, human_token=TOKEN)
        events = rt["lineage"]["events"]
        self.assertEqual([e["origin"] for e in events],
                         [promo.ORIGIN_ROOT, promo.ORIGIN_PROMOTION, promo.ORIGIN_ROLLBACK])
        prev = "GENESIS"
        for event in events:
            self.assertEqual(event["prev_hash"], prev)
            prev = event["entry_hash"]
        self.assertEqual(rt["lineage"]["head_hash"], prev)

    def test_anchor_never_moves(self):
        loop = _green_loop()
        rt = promo.promote_rollback_round_trip(ROOT_PAYLOAD, loop, CANDIDATE_PAYLOAD, human_token=TOKEN)
        for event in rt["lineage"]["events"]:
            self.assertEqual(event["anchor_tag"], "v-root")


class FrozenZoneIntegrationTests(unittest.TestCase):
    def test_promotion_module_is_frozen(self):
        from autolab import frozen_zone as fz
        manifest = fz.load_manifest(REPO_ROOT)
        self.assertIn("autolab/promotion.py", manifest["frozen_paths"])


if __name__ == "__main__":
    unittest.main()
