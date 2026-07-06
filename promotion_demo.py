#!/usr/bin/env python3
"""SFA-Bench v1.1.0 AutoLab promotion/rollback demo (SFA-AutoLab v0, Item 4).

Offline, deterministic. Produces a gate-green loop record, promotes the candidate
with a human token, rolls back to the incumbent, and asserts:

  * promotion is refused without a human token and with a red gate (asymmetric);
  * the tagged states carry the pinned v-root anchor;
  * rollback restores the incumbent bit-exact;
  * the promote -> rollback round trip replays byte-for-byte.

Run: python promotion_demo.py
"""
from __future__ import annotations

from pathlib import Path
import sys

from autolab import controller as ctrl
from autolab import promotion as promo

ROOT = Path(__file__).resolve().parent
CONFIG = {"seed": 20260706, "n": 30, "bootstrap": 500}
HUMAN_TOKEN = "human-approve-demo-001"


def main() -> int:
    print("# SFA-Bench v1.1.0 AutoLab promotion/rollback demo")
    print("=" * 56)
    failures: list[str] = []

    loop = ctrl.run_iteration(CONFIG, repo_root=ROOT).record
    print(f"loop gate_green: {loop['gate']['gate_green']}  loop_hash={loop['loop_hash'][:16]}")

    root_payload = {"scaffold": "v0", "policy_order": ["a", "b", "c"]}
    candidate_payload = {"scaffold": "v1", "policy_order": ["a", "c", "b"],
                         "patch": loop["proposal"]["patch_fingerprint"]}
    incumbent = promo.make_root_state(root_payload)

    # Asymmetric refusals.
    for label, token, record in (("no token", None, loop),
                                 ("red gate", HUMAN_TOKEN,
                                  ctrl.run_iteration({**CONFIG, "arm_probabilities": {
                                      "candidate": 0.3, "incumbent": 0.7,
                                      "ancestor_anchor": 0.5}}).record)):
        try:
            promo.promote(incumbent, record, candidate_payload, human_token=token)
            failures.append(f"promotion was NOT refused for: {label}")
            print(f"  refuse[{label}]: NOT REFUSED (bug)")
        except promo.PromotionError as exc:
            print(f"  refuse[{label}]: refused -> {exc}")

    # The authorized round trip.
    rt = promo.promote_rollback_round_trip(root_payload, loop, candidate_payload,
                                           human_token=HUMAN_TOKEN)
    tags = f"{rt['incumbent']['tag']} -> {rt['promoted']['tag']} -> {rt['restored']['tag']}"
    print(f"tagged states: {tags}")
    print(f"anchor pinned at v-root: "
          f"{all(s['anchor_tag'] == 'v-root' for s in (rt['incumbent'], rt['promoted'], rt['restored']))}")
    print(f"promoted state_hash: {rt['promoted']['state_hash'][:16]}")
    print(f"restored state_hash: {rt['restored']['state_hash'][:16]} (== incumbent: "
          f"{rt['restored']['state_hash'] == rt['incumbent']['state_hash']})")
    print(f"restores incumbent bit-exact: {rt['restores_bit_exact']}")
    print(f"lineage_hash: {rt['lineage']['lineage_hash'][:16]}")

    if not rt["restores_bit_exact"]:
        failures.append("rollback did not restore the incumbent bit-exact")
    if rt["restored"]["state_hash"] != rt["incumbent"]["state_hash"]:
        failures.append("restored state hash != incumbent state hash")
    if rt["promoted"]["anchor_tag"] != "v-root":
        failures.append("anchor is not pinned at v-root after promotion")

    replayed = promo.replay_round_trip(rt, root_payload, loop, candidate_payload,
                                       human_token=HUMAN_TOKEN)
    print(f"round-trip replay attested: {replayed['attested']}")
    if not replayed["attested"]:
        failures.append("round trip did not replay byte-for-byte: " + "; ".join(replayed["issues"]))

    print("=" * 56)
    if failures:
        for failure in failures:
            print(f"failure: {failure}")
        print("final status: FAIL")
        return 1
    print("final status: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
