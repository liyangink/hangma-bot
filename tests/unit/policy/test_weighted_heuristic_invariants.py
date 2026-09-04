"""WeightedHeuristicPolicy 的计划不变量契约测试。

覆盖：排序稳定性、去重、已拒绝排除、紧急候选保留、确定性复现、
空计划、降级规则分析与防御性过滤。
"""

from __future__ import annotations

import dataclasses
import json
import unittest

from hangma_bot.hangma.interface import RuleCandidate, RuleCompleteness, RuleIssue
from hangma_bot.kernel.actions import Discard, Pass, Tile
from hangma_bot.policy import WeightedHeuristicPolicy

from .support import (
    make_budget,
    make_observation,
    make_request,
    make_rules,
    rejected,
    run_choose,
)

HAND_CODES = (
    "1w", "2w", "3w", "4w", "5w", "6w", "7w", "8w", "9w",
    "1b", "2b", "3b", "4t",
)


def draw_observation(**overrides):
    """构造带 13 张手牌并摸入 4t 的摸牌窗口观察。"""

    defaults = dict(
        my_hand=tuple(Tile(code) for code in HAND_CODES),
        drawn_tile=Tile("4t"),
    )
    defaults.update(overrides)
    return make_observation(**defaults)


class PlanInvariantTests(unittest.TestCase):
    """计划结构满足接口协议第 4 节的全部不变量。"""

    def test_ranks_contiguous_sorted_and_stable_on_ties(self) -> None:
        """排名从 1 连续编号，总分非升序，同分按动作键稳定排序。"""

        candidates = _all_discard_candidates()
        request = make_request(draw_observation(), make_rules(candidates))
        plan = run_choose(WeightedHeuristicPolicy(monotonic=lambda: 0.0), request, make_budget())

        ranks = [item.rank for item in plan.candidates]
        self.assertEqual(ranks, list(range(1, len(candidates) + 1)))
        totals = [item.total_score for item in plan.candidates]
        self.assertEqual(totals, sorted(totals, reverse=True))
        for before, after in zip(plan.candidates, plan.candidates[1:]):
            if before.total_score == after.total_score:
                self.assertLess(before.action_key, after.action_key)

    def test_candidates_are_subset_of_ruleset_without_duplicates(self) -> None:
        """计划只引用规则候选且动作键唯一。"""

        candidates = _all_discard_candidates()
        request = make_request(draw_observation(), make_rules(candidates))
        plan = run_choose(WeightedHeuristicPolicy(monotonic=lambda: 0.0), request, make_budget())

        keys = [item.action_key for item in plan.candidates]
        rule_keys = {item.action_key for item in candidates}
        self.assertEqual(len(keys), len(set(keys)))
        self.assertTrue(set(keys) <= rule_keys)

    def test_rejected_attempts_excluded_with_filter_reason(self) -> None:
        """官方明确拒绝的动作不进入计划，且有明确过滤原因。"""

        candidates = _all_discard_candidates()
        request = make_request(
            draw_observation(),
            make_rules(candidates),
            rejected=(rejected("discard:1w"), rejected("discard:9w")),
        )
        plan = run_choose(WeightedHeuristicPolicy(monotonic=lambda: 0.0), request, make_budget())

        keys = {item.action_key for item in plan.candidates}
        self.assertNotIn("discard:1w", keys)
        self.assertNotIn("discard:9w", keys)
        joined = "；".join(plan.degraded_reasons)
        self.assertIn("过滤已拒绝候选：discard:1w", joined)

    def test_emergency_candidate_preserved_and_flagged(self) -> None:
        """紧急候选即使评分最低也保留在计划中并带标记（不做 Top-K 删除）。"""

        candidates = _all_discard_candidates()
        # 把紧急候选设为结构上最差的弃牌（拆顺子的中张）。
        emergency = _candidate_for("discard:5w", candidates)
        request = make_request(
            draw_observation(),
            make_rules(candidates, emergency=emergency),
        )
        plan = run_choose(WeightedHeuristicPolicy(monotonic=lambda: 0.0), request, make_budget())

        by_key = {item.action_key: item for item in plan.candidates}
        self.assertIn("discard:5w", by_key)
        self.assertTrue(by_key["discard:5w"].is_emergency)
        self.assertEqual(len(plan.candidates), len(candidates))

    def test_revision_increments_while_decision_id_stable(self) -> None:
        """同一窗口重新规划时 decision_id 不变、revision 随拒绝次数增加。"""

        candidates = _all_discard_candidates()
        policy = WeightedHeuristicPolicy(monotonic=lambda: 0.0)
        first = run_choose(
            policy,
            make_request(draw_observation(), make_rules(candidates), decision_id="dX"),
            make_budget(),
        )
        second = run_choose(
            policy,
            make_request(
                draw_observation(),
                make_rules(candidates),
                rejected=(rejected("discard:1w"),),
                decision_id="dX",
            ),
            make_budget(),
        )

        self.assertEqual(first.decision_id, "dX")
        self.assertEqual(first.revision, 1)
        self.assertEqual(second.decision_id, "dX")
        self.assertEqual(second.revision, 2)

    def test_same_input_same_config_reproduces_byte_identical_plan(self) -> None:
        """同输入同配置两次调用输出逐字节一致（含序列化视图）。"""

        candidates = _all_discard_candidates()
        policy = WeightedHeuristicPolicy(monotonic=lambda: 0.0)
        request = make_request(draw_observation(), make_rules(candidates))
        first = run_choose(policy, request, make_budget())
        second = run_choose(policy, request, make_budget())

        self.assertEqual(first, second)
        serialize = lambda plan: json.dumps(
            dataclasses.asdict(plan), ensure_ascii=False, sort_keys=True, default=str
        )
        self.assertEqual(serialize(first), serialize(second))
        self.assertTrue(all(item.reasons for item in first.candidates))
        self.assertTrue(all(item.score_parts for item in first.candidates))

    def test_empty_rules_candidates_yield_empty_plan_with_reason(self) -> None:
        """规则未产生合法候选时输出空计划并说明原因。"""

        request = make_request(draw_observation(), make_rules(()))
        plan = run_choose(WeightedHeuristicPolicy(monotonic=lambda: 0.0), request, make_budget())

        self.assertEqual(plan.candidates, ())
        self.assertTrue(any("规则未产生任何合法候选" in r for r in plan.degraded_reasons))

    def test_all_candidates_rejected_yields_exhaustion_reason(self) -> None:
        """全部候选被官方拒绝时输出候选耗尽原因。"""

        request = make_request(
            draw_observation(),
            make_rules(_all_discard_candidates()[:2]),
            rejected=(rejected("discard:1b"), rejected("discard:1w")),
        )
        plan = run_choose(WeightedHeuristicPolicy(monotonic=lambda: 0.0), request, make_budget())

        self.assertEqual(plan.candidates, ())
        self.assertTrue(any("候选耗尽" in r for r in plan.degraded_reasons))

    def test_degraded_rules_still_rank_conservatively(self) -> None:
        """规则分析 DEGRADED 时仍形成保守计划并记录降级原因。"""

        candidates = _all_discard_candidates()
        request = make_request(
            draw_observation(),
            make_rules(
                candidates,
                completeness=RuleCompleteness.DEGRADED,
                issues=(RuleIssue(area="gang", reason="杠分支异常"),),
            ),
        )
        plan = run_choose(WeightedHeuristicPolicy(monotonic=lambda: 0.0), request, make_budget())

        self.assertEqual(len(plan.candidates), len(candidates))
        joined = "；".join(plan.degraded_reasons)
        self.assertIn("规则降级[gang]", joined)
        self.assertIn("规则分析不完整", joined)

    def test_duplicate_rule_candidates_deduplicated(self) -> None:
        """规则候选重复时防御性去重并记录原因，不输出重复计划。"""

        base = _all_discard_candidates()[:3]
        duplicated = base + (base[0],)
        request = make_request(draw_observation(), make_rules(duplicated))
        plan = run_choose(WeightedHeuristicPolicy(monotonic=lambda: 0.0), request, make_budget())

        keys = [item.action_key for item in plan.candidates]
        self.assertEqual(len(keys), len(set(keys)))
        self.assertTrue(any("过滤重复候选" in r for r in plan.degraded_reasons))

    def test_candidate_with_mismatched_action_key_filtered(self) -> None:
        """动作键与规范键不一致的候选被过滤且有原因，不让计划失效。"""

        good = _all_discard_candidates()[:2]
        bad = RuleCandidate(action=Discard(Tile("9w")), action_key="discard:8w", evidence=())
        request = make_request(draw_observation(), make_rules(good + (bad,)))
        plan = run_choose(WeightedHeuristicPolicy(monotonic=lambda: 0.0), request, make_budget())

        keys = {item.action_key for item in plan.candidates}
        self.assertEqual(keys, {"discard:1b", "discard:1w"})
        self.assertTrue(any("过滤动作键不一致候选" in r for r in plan.degraded_reasons))

    def test_pass_only_window_exhaustion_after_rejection(self) -> None:
        """响应窗口只剩过且已被拒绝时，输出候选耗尽的空计划。"""

        pass_candidate = RuleCandidate(action=Pass(), action_key="pass", evidence=())
        request = make_request(
            draw_observation(),
            make_rules((pass_candidate,)),
            rejected=(rejected("pass"),),
        )
        plan = run_choose(WeightedHeuristicPolicy(monotonic=lambda: 0.0), request, make_budget())

        self.assertEqual(plan.candidates, ())
        self.assertTrue(any("候选耗尽" in r for r in plan.degraded_reasons))

    def test_based_on_authoritative_seq_follows_snapshot(self) -> None:
        """计划基于的权威序号取自玩家观察快照序号。"""

        candidates = _all_discard_candidates()[:2]
        observation = draw_observation(snapshot_seq=77)
        request = make_request(observation, make_rules(candidates))
        plan = run_choose(WeightedHeuristicPolicy(monotonic=lambda: 0.0), request, make_budget())

        self.assertEqual(plan.based_on_authoritative_seq, 77)

    def test_rejected_emergency_noted_by_main_policy(self) -> None:
        """主策略路径：紧急候选被官方拒绝时记录降级文案并从计划排除。"""

        candidates = _all_discard_candidates()
        emergency = _candidate_for("discard:1b", candidates)
        request = make_request(
            draw_observation(),
            make_rules(candidates, emergency=emergency),
            rejected=(rejected("discard:1b"),),
        )
        plan = run_choose(WeightedHeuristicPolicy(monotonic=lambda: 0.0), request, make_budget())

        keys = {item.action_key for item in plan.candidates}
        self.assertNotIn("discard:1b", keys)
        self.assertTrue(
            any("紧急候选已被官方拒绝：discard:1b" in r for r in plan.degraded_reasons)
        )


def _all_discard_candidates():
    """给默认手牌生成全部弃牌候选。"""

    from .support import discards_for

    return discards_for(sorted(set(HAND_CODES) | {"4t"}))


def _candidate_for(key: str, candidates):
    """按键取候选；测试内部使用。"""

    for item in candidates:
        if item.action_key == key:
            return item
    raise KeyError(key)


if __name__ == "__main__":
    unittest.main()
