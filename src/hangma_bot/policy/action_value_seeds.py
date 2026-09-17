"""action_value_v1 首批种子：两个完整实现 + 立即胡优先对照。

每个种子以模块级源码常量（SCORE_ACTIONS_SOURCE）交付，装载必须经过
ActionValueExecutor 的静态检查与插桩编译——种子不享有任何执行器之外的
特权路径（合同 seeds_required：efficiency_seed、route_value_seed、
立即胡优先对照实现）。机制说明四字段：触发条件（trigger）、改变的
动作分支（changed_branches）、预期方向（expected_direction）、反例
（counterexample）。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Mapping, Optional, Tuple

from hangma_bot.hangma.interface import Settlement
from hangma_bot.kernel.actions import Discard, Hu, Pass, Tile
from hangma_bot.kernel.observation import PlayerObservation, RulePublicState

from .action_value import (
    ActionView,
    AnalysisProfileView,
    ScoringView,
)
from .action_value_executor import (
    EXECUTOR_VERSION,
    ActionValueExecutor,
    compute_candidate_identity,
    compute_deps_digest,
)


EFFICIENCY_SEED_SOURCE = '''"""efficiency_seed：牌效优先——followup 分支 combined_shanten 最小 + support_remaining 加权。"""

SHANTEN_WEIGHT = 3.0
SUPPORT_WEIGHT = 0.5
UNKNOWN_FIELD = "combined_shanten"


def branch_number(branch, key):
    value = branch.get(key)
    if value is None:
        return None
    if value is True or value is False:
        return None
    if value < 0:
        return None
    return value


def best_branch(branches):
    best_shanten = None
    best_support = 0.0
    best_key = None
    for branch in branches:
        shanten = branch_number(branch, "combined_shanten")
        if shanten is None:
            continue
        support = branch_number(branch, "support_remaining")
        if support is None:
            support = 0.0
        if best_shanten is None or shanten < best_shanten:
            best_shanten = shanten
            best_support = support
            best_key = branch.get("followup_key")
    if best_shanten is None:
        return None
    return (best_shanten, best_support, best_key)


def make_trace(shanten, support, key):
    if key is None:
        return {"basis": "efficiency", "combined_shanten": shanten, "support_remaining": support}
    return {"basis": "efficiency", "combined_shanten": shanten, "support_remaining": support, "followup_key": key}


def known_entries(actions):
    entries = []
    for action in actions:
        branches = action.get("followup_branches")
        if branches is None:
            continue
        best = best_branch(branches)
        if best is None:
            continue
        shanten = best[0]
        support = best[1]
        key = best[2]
        score = 0.0 - SHANTEN_WEIGHT * shanten + SUPPORT_WEIGHT * support
        entries.append({"action_key": action["action_key"], "score": score, "trace": make_trace(shanten, support, key)})
    return entries


def has_entry(entries, key):
    for entry in entries:
        if entry["action_key"] == key:
            return True
    return False


def min_score(entries):
    lowest = None
    for entry in entries:
        value = entry["score"]
        if lowest is None or value < lowest:
            lowest = value
    return lowest


def score_actions(view):
    actions = view["actions"]
    entries = known_entries(actions)
    if len(entries) == 0:
        results = []
        for action in actions:
            trace = {"basis": "unknown_field_basis", "field": UNKNOWN_FIELD}
            results.append({"action_key": action["action_key"], "score": 0.0, "trace": trace})
        return {"status": "SCORED", "entries": results, "reason": None}
    anchor = min_score(entries) - 1.0
    for action in actions:
        key = action["action_key"]
        if has_entry(entries, key):
            continue
        trace = {"basis": "unknown_field_basis", "field": UNKNOWN_FIELD, "anchor": anchor}
        entries.append({"action_key": key, "score": anchor, "trace": trace})
    return {"status": "SCORED", "entries": entries, "reason": None}
'''


ROUTE_VALUE_SEED_SOURCE = '''"""route_value_seed：路线价值——牌效基础叠加 family_progress 与有界结算因子（非期望积分）。"""

SHANTEN_WEIGHT = 3.0
SUPPORT_WEIGHT = 0.5
UNKNOWN_SHANTEN_PENALTY = 4.0
PROGRESS_BONUS = {"ADVANCE": 2.0, "SAME": 0.0, "RETREAT": -2.0, "CLOSE": -1.0, "UNKNOWN": 0.0}
IMMEDIATE_FAN_WEIGHT = 4.0
ROUTE_FAN_WEIGHT = 0.5
DELTA_WEIGHT = 0.0625
MAX_DELTA = 64
UNKNOWN_FIELD = "combined_shanten"


def num_or_none(branch, key):
    value = branch.get(key)
    if value is None:
        return None
    if value is True or value is False:
        return None
    if value < 0:
        return None
    return value


def fan_scale(fan):
    """有界 log 界缩放：fan 每达到 2/4/8/16/32 各记 1，封顶 5。"""
    marks = 0.0
    if fan >= 2:
        marks = marks + 1.0
    if fan >= 4:
        marks = marks + 1.0
    if fan >= 8:
        marks = marks + 1.0
    if fan >= 16:
        marks = marks + 1.0
    if fan >= 32:
        marks = marks + 1.0
    return marks


def best_branch(branches):
    best_shanten = None
    best_support = 0.0
    best_key = None
    for branch in branches:
        shanten = num_or_none(branch, "combined_shanten")
        if shanten is None:
            continue
        support = num_or_none(branch, "support_remaining")
        if support is None:
            support = 0.0
        if best_shanten is None or shanten < best_shanten:
            best_shanten = shanten
            best_support = support
            best_key = branch.get("followup_key")
    return (best_shanten, best_support, best_key)


def route_fan_best(branches):
    best = 0.0
    for branch in branches:
        fan = num_or_none(branch, "fan")
        if fan is not None and fan > best:
            best = fan
    return best


def settlement_factor(action):
    settle = action.get("immediate_settlement")
    factor = 0.0
    fan = 0.0
    if settle is not None:
        fan = settle.get("fan")
        if fan is None or fan < 0:
            fan = 0.0
        factor = factor + fan_scale(fan) * IMMEDIATE_FAN_WEIGHT
        delta = settle.get("self_delta")
        if delta is not None and delta > 0:
            if delta > MAX_DELTA:
                delta = MAX_DELTA
            factor = factor + delta * DELTA_WEIGHT
    return (factor, fan)


def score_actions(view):
    actions = view["actions"]
    entries = []
    for action in actions:
        branches = action.get("followup_branches")
        best = (None, 0.0, None)
        if branches is not None:
            best = best_branch(branches)
        shanten = best[0]
        support = best[1]
        key = best[2]
        basis = "route_value"
        if shanten is None:
            basis = "route_value_unknown_shanten"
            base = 0.0 - SHANTEN_WEIGHT * UNKNOWN_SHANTEN_PENALTY
        else:
            base = 0.0 - SHANTEN_WEIGHT * shanten + SUPPORT_WEIGHT * support
        progress = action.get("family_progress")
        if progress is None:
            progress = "UNKNOWN"
        bonus = PROGRESS_BONUS.get(progress)
        if bonus is None:
            bonus = 0.0
        settle = settlement_factor(action)
        route_fan = 0.0
        if branches is not None:
            route_fan = route_fan_best(branches)
        score = base + bonus + settle[0] + fan_scale(route_fan) * ROUTE_FAN_WEIGHT
        trace = {"basis": basis, "combined_shanten": shanten, "support_remaining": support, "progress": progress, "immediate_fan": settle[1], "route_fan": route_fan, "note": "fan 因子为 log 界缩放，非期望积分"}
        if key is not None:
            entry = {"action_key": action["action_key"], "score": score, "trace": {"basis": basis, "combined_shanten": shanten, "support_remaining": support, "progress": progress, "immediate_fan": settle[1], "route_fan": route_fan, "followup_key": key, "note": "fan 因子为 log 界缩放，非期望积分"}}
        else:
            entry = {"action_key": action["action_key"], "score": score, "trace": trace}
        entries.append(entry)
    return {"status": "SCORED", "entries": entries, "reason": None}
'''


HU_FIRST_REFERENCE_SOURCE = '''"""hu_first_reference：立即胡优先对照——合法 Hu 恒最高分，其余按牌效种子评分。"""

SHANTEN_WEIGHT = 3.0
SUPPORT_WEIGHT = 0.5
HU_BONUS = 1000000.0
UNKNOWN_FIELD = "combined_shanten"


def branch_number(branch, key):
    value = branch.get(key)
    if value is None:
        return None
    if value is True or value is False:
        return None
    if value < 0:
        return None
    return value


def best_branch(branches):
    best_shanten = None
    best_support = 0.0
    best_key = None
    for branch in branches:
        shanten = branch_number(branch, "combined_shanten")
        if shanten is None:
            continue
        support = branch_number(branch, "support_remaining")
        if support is None:
            support = 0.0
        if best_shanten is None or shanten < best_shanten:
            best_shanten = shanten
            best_support = support
            best_key = branch.get("followup_key")
    if best_shanten is None:
        return None
    return (best_shanten, best_support, best_key)


def make_trace(shanten, support, key):
    if key is None:
        return {"basis": "hu_first_efficiency", "combined_shanten": shanten, "support_remaining": support}
    return {"basis": "hu_first_efficiency", "combined_shanten": shanten, "support_remaining": support, "followup_key": key}


def min_score(entries):
    lowest = None
    for entry in entries:
        value = entry["score"]
        if value is None:
            continue
        if lowest is None or value < lowest:
            lowest = value
    return lowest


def score_actions(view):
    actions = view["actions"]
    entries = []
    hu_entries = []
    for action in actions:
        if action["action_type"] == "hu" and action.get("is_legal") is True:
            trace = {"basis": "hu_first_reference", "legal_hu": True}
            hu_entries.append({"action_key": action["action_key"], "score": HU_BONUS, "trace": trace})
            continue
        branches = action.get("followup_branches")
        best = None
        if branches is not None:
            best = best_branch(branches)
        if best is None:
            key = action["action_key"]
            anchor_entry = {"action_key": key, "score": None, "trace": {"basis": "unknown_field_basis", "field": UNKNOWN_FIELD}}
            entries.append(anchor_entry)
            continue
        shanten = best[0]
        support = best[1]
        branch_key = best[2]
        score = 0.0 - SHANTEN_WEIGHT * shanten + SUPPORT_WEIGHT * support
        entries.append({"action_key": action["action_key"], "score": score, "trace": make_trace(shanten, support, branch_key)})
    if min_score(entries) is None:
        anchor = -1.0
    else:
        anchor = min_score(entries) - 1.0
    results = []
    for entry in entries:
        if entry["score"] is None:
            trace = {"basis": "unknown_field_basis", "field": UNKNOWN_FIELD, "anchor": anchor}
            results.append({"action_key": entry["action_key"], "score": anchor, "trace": trace})
        else:
            results.append(entry)
    for entry in hu_entries:
        results.append(entry)
    return {"status": "SCORED", "entries": results, "reason": None}
'''


@dataclass(frozen=True)
class SeedSpec:
    """一个种子的完整登记：名字、受限源码与四字段机制说明。"""

    name: str  # 注册表键；进入 build_action_value_policy
    source: str  # score_actions 模块源码文本（即候选身份的源材料）
    mechanism: Mapping[str, str]  # trigger/changed_branches/expected_direction/counterexample


EFFICIENCY_SEED_MECHANISM: Dict[str, str] = {
    "trigger": "动作存在带 combined_shanten 的 followup 分支时按牌效评分；任何动作缺该字段时走显式未知处理。",
    "changed_branches": "向听更近（combined_shanten 更小）且有效牌余量（support_remaining）更大的弃牌/吃碰分支前移；无分支事实的动作（如 Pass）垫底。",
    "expected_direction": "分数 = -3.0×向听 + 0.5×有效牌余量；只比较相对大小，不是积分期望。",
    "counterexample": "缺 combined_shanten 的动作不按 0 分处理：取已知动作最低分 -1 的下界锚点并在 trace 标注 unknown_field_basis，不得把未知排在已知负分之前。",
}

ROUTE_VALUE_SEED_MECHANISM: Dict[str, str] = {
    "trigger": "family_progress 为 ADVANCE 或存在立即结算/分支条件 fan 事实时，在牌效基础上叠加路线项。",
    "changed_branches": "进展加分（ADVANCE +2 / RETREAT -2 / CLOSE -1）、立即结算的 log 界缩放 fan 因子（每达 2/4/8/16/32 各记 1，×4）与条件路线 fan 因子（×0.5）使吃碰杠胡相对纯牌效前移。",
    "expected_direction": "分数 = 牌效 + 进展 + 有界结算因子；fan 因子是 log 界缩放的启发量，trace 明确标注非期望积分，不得自称期望积分。",
    "counterexample": "牌效更差且无进展/结算优势的路线不会超过纯牌效最优动作；缺向听事实的动作按保守常数 -12（4 向听惩罚）处理并标注 route_value_unknown_shanten。",
}

HU_FIRST_REFERENCE_MECHANISM: Dict[str, str] = {
    "trigger": "动作表存在合法 Hu（action_type=hu 且 is_legal）时启用对照覆盖。",
    "changed_branches": "合法 Hu 恒得 1000000.0 分居首；其余动作与 efficiency_seed 完全相同的牌效评分（含未知锚点）。",
    "expected_direction": "对照实现：证明骨架按 compare_legal 比较合法胡与继续，胡优先只是本对照的选择，不是骨架强制的规则定理。",
    "counterexample": "动作表无合法 Hu 时，排序与 efficiency_seed 逐项一致；效率种子在同一事实下可以把继续排在胡之前。",
}

EFFICIENCY_SEED = SeedSpec(
    name="efficiency_seed",
    source=EFFICIENCY_SEED_SOURCE,
    mechanism=EFFICIENCY_SEED_MECHANISM,
)
ROUTE_VALUE_SEED = SeedSpec(
    name="route_value_seed",
    source=ROUTE_VALUE_SEED_SOURCE,
    mechanism=ROUTE_VALUE_SEED_MECHANISM,
)
HU_FIRST_REFERENCE = SeedSpec(
    name="hu_first_reference",
    source=HU_FIRST_REFERENCE_SOURCE,
    mechanism=HU_FIRST_REFERENCE_MECHANISM,
)

SEEDS: Dict[str, SeedSpec] = {
    EFFICIENCY_SEED.name: EFFICIENCY_SEED,
    ROUTE_VALUE_SEED.name: ROUTE_VALUE_SEED,
    HU_FIRST_REFERENCE.name: HU_FIRST_REFERENCE,
}

SEED_NAMES: Tuple[str, ...] = (
    "efficiency_seed",
    "route_value_seed",
    "hu_first_reference",
)


class ActionValueScorer:
    """经受限执行器装载的一个 action_value_v1 候选（种子）。

    score() 返回通过完整性验证的 ScoreBatch；任何失败（含 WorkloadExceeded）
    抛给调用方整批降级。candidate_identity() 输出合同身份，供准入与评估绑定。
    """

    def __init__(self, name: str, source: str) -> None:
        self.name = name
        self.source = source
        self._executor = ActionValueExecutor(source, name=name)

    @property
    def executor_version(self) -> str:
        """装载所用执行器版本；进入候选身份。"""
        return EXECUTOR_VERSION

    def score(self, view: ScoringView):
        """受限执行 score_actions；失败整批抛错，绝不部分补零。"""
        return self._executor.score(view)

    def candidate_identity(
        self,
        contract_sha256: str,
        params: Optional[Mapping[str, Any]] = None,
        deps_digest: Optional[str] = None,
    ) -> str:
        """按合同 identity.candidate_id_inputs 计算 candidate_id。"""
        return compute_candidate_identity(
            self.source,
            contract_sha256,
            params,
            EXECUTOR_VERSION,
            deps_digest if deps_digest is not None else compute_deps_digest(),
        )


def build_action_value_policy(name: str) -> ActionValueScorer:
    """按种子名构建受限评分器；静态注册表，不做动态扫描。

    首批三个名字：efficiency_seed / route_value_seed / hu_first_reference。
    本工厂不接线组合根默认策略——B3 才接入 choose 链路。
    """
    spec = SEEDS.get(name)
    if spec is None:
        raise ValueError(
            "未知 action_value 种子名 {0!r}；可用：{1}".format(name, list(SEED_NAMES))
        )
    return ActionValueScorer(spec.name, spec.source)


def make_sample_observation() -> PlayerObservation:
    """构造最小合法 PlayerObservation（样例视图与自测用；非真实牌局）。"""
    hand = ("1w", "2w", "3w", "4w", "5w", "6w", "7w", "8w", "9w", "1b", "2b", "3b", "4b")
    return PlayerObservation(
        game_id="sample-game",
        seat=0,
        round_no=1,
        snapshot_seq=1,
        phase="draw",
        dealer_seat=0,
        turn_seat=0,
        responding_seats=(),
        my_hand=tuple(Tile(code) for code in hand),
        drawn_tile=None,
        discards=((), (), (), ()),
        melds=((), (), (), ()),
        hand_counts=(13, 13, 13, 13),
        last_discard=None,
        remaining_tile_count=60,
        scores=(0, 0, 0, 0),
        rule_state=RulePublicState(
            wealth_god=Tile("白"),
            baotou=False,
            chain_count=0,
            catch_play=False,
        ),
        public_history=(),
    )


def build_sample_view() -> ScoringView:
    """构造含“弃牌/胡/过”三类动作的最小 ScoringView。

    弃牌分支带 combined_shanten/support_remaining 事实；胡带立即结算；
    过无任何分支事实（验证未知锚点路径）。动作表按 action_key 升序。
    """
    discard_branches = (
        {
            "followup_key": "discard:1w",
            "combined_shanten": 1,
            "support_remaining": 6,
            "fan": 2,
        },
    )
    actions = (
        ActionView(
            action_key="discard:1w",
            action=Discard(tile=Tile("1w")),
            action_type="discard",
            is_legal=True,
            followup_branches=discard_branches,
            family_progress="ADVANCE",
        ),
        ActionView(
            action_key="hu",
            action=Hu(),
            action_type="hu",
            is_legal=True,
            immediate_settlement=Settlement(
                score_delta=(8, -3, -3, -2), fan=4, details=("sample",)
            ),
            family_progress="CLOSE",
        ),
        ActionView(
            action_key="pass",
            action=Pass(),
            action_type="pass",
            is_legal=True,
            family_progress="SAME",
        ),
    )
    return ScoringView(
        schema_version="sitin-scoring-view/1",
        visible_state=make_sample_observation(),
        actions=actions,
        analysis_profile=AnalysisProfileView(
            semantics_version="value-analysis-sample/1",
            max_expansions=2048,
            max_routes_per_candidate=128,
            truncation_note="样例视图，无截断",
            ruleset_version="sample",
        ),
    )


def self_check() -> Dict[str, str]:
    """种子自测入口：静态检查 + 装载 + 样例视图完整评分 + 确定性复跑。

    返回每个种子的检查结论；任何一步失败抛出对应异常（静态检查
    StaticCheckError / 执行失败 WorkloadExceeded 或 ValueError）。
    """
    view = build_sample_view()
    expected = set(view.expected_action_keys())
    results: Dict[str, str] = {}
    for name in SEED_NAMES:
        scorer = build_action_value_policy(name)
        first = scorer.score(view)
        if first.status != "SCORED":
            raise ValueError("种子 {0} 样例评分未返回 SCORED".format(name))
        if set(entry.action_key for entry in first.entries) != expected:
            raise ValueError("种子 {0} 评分动作键不完整".format(name))
        second = scorer.score(view)
        if second != first:
            raise ValueError("种子 {0} 同视图两次评分不一致".format(name))
        results[name] = "ok"
    return results
