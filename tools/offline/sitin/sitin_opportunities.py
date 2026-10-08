# -*- coding: utf-8 -*-
"""C1 机会面板构造（legal-prefix-v1）与受控中途续打（v4 §7.2/§7.3/§7.4；R3 修复 Q1/Q8）。

规范来源：review/llm-guided-heuristic-route-2026-09-15/SEARCH-SPACE-REDESIGN-2026-09-16.md
§7（面板构造、legal-prefix-v1 六步、场景矩阵与八谓词）、§13 C1 行、§14 T09/T16；
返工依据 REVIEW-V4-COMPLETION-2026-09-17.md Q1（真实条件续打）与补充缺口 Q8
（阶段处境投影）、CONTINUOUS-EVOLUTION-PLAN-2026-09-17.md R3 行与 §4。

预算红线（最高优先级）：本包验收零真实桌赛实例（搜索账 384/384 已用尽）。
两条前缀路径分层（Q1 修复）：

- prefix_source=scripted_fixture：ScriptedFixtureEngine（fixture_mode=True，
  仅工具测试/夹具验收可用）+ 脚本帧模板；生成器 scripted-prefix-fixture-v1；
- prefix_source=v2_behavior：真实路径——组合根运行时（bootstrap.
  build_evaluation_runtime("matches") 提供 SimulationEngine 公开 start/frame/
  advance + spec_factory/choice_factory）+ 冻结行为策略（焦点=
  weighted_heuristic_v2、对手按 group-dev-v1 合同 H/M 情景装配），从自然开局
  生成真实合法前缀；生成器 v2-behavior-prefix-v1。真实路径绝不调用
  ScriptedFixtureEngine/build_fixture_frames。真实执行需批次 7 预算授权令牌
  （R6 E 重验时按新授权跑；本包只用注入的公开契约验证替身做接线/夹具验收，
  0 真实桌赛）。

legal-prefix-v1 六步落点（§7.2 逐条）：
1. prefix_source 枚举 scripted_fixture / v2_behavior，生成器版本独立分层；
2. 每个生成尝试预分配主子场景（八谓词之一）+ 独立 source_root_id；焦点座位
   行动前仅用玩家可见事实判预分配谓词，首次命中即截取；同根只贡献一个样本
   一个主子场景，其他谓词命中仅作标签；
3. 快照保存阶段累计账、MatchSpec 等价信息、截取窗口、观察摘要与合法动作
   前缀；重建走模拟器公开 start/frame/advance 重放合法前缀并核对观察摘要
   一致才接受（合法前缀重建，不做通用 WorldState 序列化）；
4. 双臂续打：同快照出发，候选/基线各自持 PlayerObservation 决策；截取帧
   尚未推进的响应者按该帧观察重新决策，不沿用基线预先选好的响应；
   续完当前桌及全部剩余桌（完整剩余阶段）再算 group_advance_v1 阶段 U
   （R3 修复③：声明终点 stage_complete，不再止于 current_table_end）；
5. 费用账按 §7.4 逐字段记录；条件启动的桌赛计部分桌赛执行；
6. 每子场景前缀尝试不超过 PREFIX_ATTEMPT_CAP（256），夹具模式同样执行该
   上限；未命中如实报 attempts_exhausted，不改状态字段冒充合法世界。

Q8（阶段处境投影）：双臂续打经 offline.evaluate 的 StageSituationProjection
把已完成桌赛积分/名次分与剩余赛程按当时可见权限注入每个策略请求（策略可见
自己座位的阶段累计与剩余桌数；不泄未来）。

隐藏信息红线（T09）：快照与谓词判定只用玩家可见事实（观察+规则分析）；
面板产物不含牌墙真值/他家暗牌/未来事件；策略/候选在续打中只收
PlayerObservation。
"""

from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/llm-guided-heuristic-route-2026-09-15/tools'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

import argparse
import asyncio
import hashlib
import json
import math
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

REPO = _PROJECT_ROOT
_HERE = Path(__file__).resolve().parent
for _entry in (str(_project_file(_PROJECT_ROOT, REPO / "src")), str(_HERE)):
    if _entry not in sys.path:
        sys.path.insert(0, _entry)

from hangma_bot.hangma.engine import HangmaRules
from hangma_bot.hangma.interface import RuleAnalysis, ValueAnalysisLimits
from hangma_bot.kernel.actions import Action, Tile, WindowKey, WindowPhase, action_key
from hangma_bot.kernel.config import RuleConfig
from hangma_bot.kernel.observation import PlayerObservation, PublicDiscard, RulePublicState
from hangma_bot.kernel.serialization import window_key_to_json
from hangma_bot.offline.evaluate import (
    MatchDriverConfig,
    StageSituationProjection,
    frame_observation_summary,
    resume_match,
)
from hangma_bot.policy.interface import (
    DecisionPlan,
    RankedCandidate,
    DecisionRequest,
)
from sitin_predicates_v4 import (PREDICATE_IDS, _B_ROUTE_STATUSES, _strict_pair,
                                 evaluate_predicates)
#: 探针读数用的别名（单一来源仍是谓词模块的冻结合同常量，不在这里复制一份）。
_B_ROUTE_STATUSES_FOR_PROBE = _B_ROUTE_STATUSES
_strict_pair_for_probe = _strict_pair
import sitin_stage as stage  # noqa: E402  单一实现复用（计划/名次分/目标求值/白名单装配）
import sitin_execution_audit as execution_audit  # noqa: E402

#: 面板产物 schema（场景清单 + 费用账）。
PANEL_SCHEMA = "sitin-opportunity-panel/1"
#: 单场景快照 schema（合法前缀重建的载体）。
SNAPSHOT_SCHEMA = "sitin-opportunity-snapshot/1"
#: 费用账行 schema（§7.4）。
COST_RECORD_SCHEMA = "sitin-opportunity-cost/1"

#: 前缀来源枚举（§7.2 条 1）：夹具（工具测试）/ 真实 V2 行为（批次 7 预算门后）。
PREFIX_SOURCES: Tuple[str, ...] = ("scripted_fixture", "v2_behavior")
#: 夹具生成器版本（分层报告：与真实 V2 前缀生成器互不冒充）。
GENERATOR_SCRIPTED_FIXTURE = "scripted-prefix-fixture-v1"
#: 真实 V2 行为前缀生成器版本（批次 7 授权后才可运行）。
GENERATOR_V2_BEHAVIOR = "v2-behavior-prefix-v1"
#: 每子场景前缀尝试上限（§7.2 条 6；夹具模式同样执行）。
PREFIX_ATTEMPT_CAP = 256
#: v2_behavior 的预算授权令牌文件名（批次 7 预算门后由授权流程生成；当前不存在）。
V2_AUTHORIZATION_FILENAME = "v2-prefix-authorization.json"
#: 焦点参赛者身份（阶段账 participant_id；与 sitin_natural_panel 同名同义）。
FOCAL_PARTICIPANT = "focal"
#: 基线臂焦点策略（group-dev-v1 白名单成员；行为策略同源）。
BASELINE_FOCAL_POLICY = "weighted_heuristic_v2"
#: 真实路径的组合根运行时来源标识（进入快照/费用账的可追溯字段）。
REAL_RUNTIME_SOURCE = "bootstrap.build_evaluation_runtime(matches)"

# ---------------------------------------------------------------------------
# A1 修复（R7 / 复审 P1）：运行时装配来源与执行证据
#
# 缺陷：条件步调 run_av_evaluation 未传 runtime → 触发缺省替身；外层元数据仍记
# fixture_mode=false 并照常记账，把"替身执行"冒充"真实执行"，engine_kind 还把
#「传了 runtime」与「替身」混为一谈（复审 A1）。
# 修复：运行时种类由**装配入口**决定并打标签（不从"是否传入 runtime"推断）；
# 真实路径缺运行时**拒绝**（fail-closed，不自动注入替身）；替身只能经显式测试
# 入口 build_test_runtime_double 传入；engine_kind / execution_kind / 逐桌决策
# 计数 / 完成原因 / 费用一律来自执行记录，并交结果准入程序交叉校验。
# ---------------------------------------------------------------------------

#: 运行时种类（装配入口标签）：真实组合根引擎 / 显式测试入口的验证替身 / 脚本夹具。
RUNTIME_KIND_REAL = "real_simulation_engine"
RUNTIME_KIND_TEST_DOUBLE = "test_double_runtime"
RUNTIME_KIND_FIXTURE = "scripted_fixture_engine"
RUNTIME_KINDS: Tuple[str, ...] = (RUNTIME_KIND_REAL, RUNTIME_KIND_TEST_DOUBLE,
                                 RUNTIME_KIND_FIXTURE)

#: 执行类别（进产物的三态事实，与运行时种类一一对应）。
EXECUTION_REAL = "real_runtime"
EXECUTION_TEST_DOUBLE = "test_double"
EXECUTION_SCRIPTED_FIXTURE = "scripted_fixture"

#: 运行时种类 → engine_kind（产物字段；由实际装配对象决定，不由调用形态决定）。
ENGINE_KIND_BY_RUNTIME_KIND: Dict[str, str] = {
    RUNTIME_KIND_REAL: "simulation_engine_public",
    RUNTIME_KIND_TEST_DOUBLE: "simulation_runtime_double",
    RUNTIME_KIND_FIXTURE: "scripted_fixture_engine",
}
#: 运行时种类 → 执行类别。
EXECUTION_KIND_BY_RUNTIME_KIND: Dict[str, str] = {
    RUNTIME_KIND_REAL: EXECUTION_REAL,
    RUNTIME_KIND_TEST_DOUBLE: EXECUTION_TEST_DOUBLE,
    RUNTIME_KIND_FIXTURE: EXECUTION_SCRIPTED_FIXTURE,
}
#: 只有真实运行时的执行记录才允许用于开发选留与效果反馈（复审 A1 验收）。
SELECTION_ELIGIBLE_RUNTIME_KINDS: Tuple[str, ...] = (RUNTIME_KIND_REAL,)


class RuntimeAssemblyError(ValueError):
    """真实路径的运行时未在组合处显式装配、或来源不可辨：fail-closed（A1）。"""

#: 四个专长家族（与 sitin_predicates_v4.FAMILIES 同序）。
FAMILIES: Tuple[str, ...] = ("branch", "chain", "four_white", "baotou")
#: 谓词输入合同要求的 route_status 单值聚合优先级（最开放证据优先；见
#: project_predicate_facts 的歧义处理说明）。
_ROUTE_STATUS_PRIORITY: Dict[str, int] = {
    "WITNESSED": 0,
    "OPEN_UNCERTAIN": 1,
    "UNANALYZED": 2,
    "CLOSED_PROVEN": 3,
}
#: 快照/面板产物禁止出现的 WorldState 私有字段名（T09 隐藏信息红线，inspect 核查）。
FORBIDDEN_SNAPSHOT_KEYS: Tuple[str, ...] = (
    "wall",
    "wall_front",
    "wall_back",
    "progression",
    "round_initial_hands",
    "initial_hands",
    "round_start_wall",
    "events",
    "round_records",
    "seats",
)

NEWLINE = chr(10)

DEFAULT_RULESET_VERSION = "hangma-mvp-v10-public-counts"


# ---------------------------------------------------------------------------
# 任务 2：谓词事实投影器（PlayerObservation + RuleAnalysis → 八谓词输入合同）
# ---------------------------------------------------------------------------


def _combined_shanten(facts: Any) -> Optional[int]:
    """facts 分牌型向听最小值（standard/seven_pairs 非 None 项取 min；全空 None 透传）。

    WIN/NOT_APPLICABLE 等无等待态事实的分牌型为空 → None（不可比较），不冒充 0。
    """
    values = [
        value
        for value in (facts.standard_shanten_after, facts.seven_pairs_shanten_after)
        if value is not None
    ]
    return min(values) if values else None


def _family_maps(facts: Any) -> Tuple[Dict[str, str], Dict[str, str]]:
    """展开 facts.family_progress 元组 → (进展标签 dict, 路线证据 dict)。

    直接取 FamilyProgress 条目按家族展开（不用任何坍缩单字符串）；空元组
    （未分析）按 UNKNOWN/UNANALYZED 透传，不冒充已知。
    """
    progress = {family: "UNKNOWN" for family in FAMILIES}
    route = {family: "UNANALYZED" for family in FAMILIES}
    if facts is None:
        return progress, route
    for entry in facts.family_progress:
        family = entry.family.value
        progress[family] = entry.progress.value.upper()
        route[family] = entry.route_status.value.upper()
    return progress, route


def _route_status_aggregate(route_by_family: Mapping[str, str]) -> str:
    """把按家族的路线证据聚合为谓词合同要求的单值 route_status。

    歧义处理决定（合同未逐字规定、由本模块冻结）：谓词输入合同的
    route_status 是分支级单值（sitin_predicates_v4 docstring），而 B1 载荷按
    家族给出证据。聚合取「最开放证据」优先级 WITNESSED > OPEN_UNCERTAIN >
    UNANALYZED > CLOSED_PROVEN。在当前 B1 生产端（progression_payload）下，
    家族间证据只会在 branch=CLOSED_PROVEN（开门，同时该家族 progress=CLOSE，
    本就不能充当推进侧 b）或预算超限（四家族同为 UNANALYZED）时分叉，故该
    聚合不改变 b 门槛语义；按家族明细另存 family_route_status 供审计。
    """
    return sorted(
        (route_by_family[family] for family in FAMILIES),
        key=lambda value: _ROUTE_STATUS_PRIORITY[value],
    )[0]


def _support_remaining(facts: Any, value_facts: Any) -> Dict[str, Optional[int]]:
    """每家族一步推进有效牌未见枚数总和（牌码去重）；未知 None。

    - branch：CandidateFacts.useful_tiles（最佳等待态有效牌）的
      remaining_estimate 求和（同码不重复计）；
    - chain/four_white/baotou：从 ValueRoute 条件见证（route.useful_tiles）中
      见证该家族的路线取有效牌，按牌码去重后求和；
    - 无事实/无路线 → None（未知），不写 0 冒充已知空缺。
    """
    support: Dict[str, Optional[int]] = {family: None for family in FAMILIES}
    if facts is not None and facts.useful_tiles:
        support["branch"] = sum(tile.remaining_estimate for tile in facts.useful_tiles)
    routes = [] if value_facts is None else tuple(value_facts.routes)
    witnessed: Dict[str, Dict[str, int]] = {family: {} for family in FAMILIES}
    for route in routes:
        conditions = route.conditions
        families = set()
        if conditions.chain_count > 0:
            families.add("chain")
        if conditions.baotou:
            families.add("baotou")
        whites = sum(1 for code in conditions.pre_draw_hand if code == "白")
        for tile in route.useful_tiles:
            win_whites = whites + (1 if tile.code == "白" else 0)
            if win_whites + conditions.chain_piao == 4:
                families.add("four_white")
                break
        for family in families:
            for tile in route.useful_tiles:
                witnessed[family].setdefault(tile.code, tile.remaining_estimate)
    for family, codes in witnessed.items():
        if codes:
            support[family] = sum(codes.values())
    return support


def wall_reserve_tiles() -> int:
    """保留区张数（规则唯一来源：hangma.action_families.WALL_RESERVE_TILES）。"""

    from hangma_bot.hangma.action_families import WALL_RESERVE_TILES

    return int(WALL_RESERVE_TILES)


def wall_left_drawable(remaining_tile_count: Any) -> Optional[int]:
    """观察的公开余量 → 八谓词合同口径的 wall_left（**可摸牌墙余量**）。

    P9 FAMCOST 修复（2026-09-18，投影单位缺陷）：观察的 remaining_tile_count
    （官方 wall_remaining）**含保留区 20 张**——官方测试房 30,096 条快照逐窗
    对拍确认开局恒为 83 = 136 − 53、且 136 − 已发牌 − 已摸牌
    （doc/official-platform-api-v2.md §9.4.5）；模拟器侧同理
    （wall_total = drawable + RESERVE_TILES，simulation/engine.py:688）。
    一局在可摸区摸完即结束 ⇒ 该字段的**取值下界是 20**，永远表达不出 §7.3 的
    "墙短"阈值 wall_left ≤ 8；反过来机会侧的 wall_left ≥ 16 在该口径下恒真
    （vacuous）。两个方向同时退化正是单位错的指纹（P9 实测：32 根 × 10,705 帧
    的 wall_left ∈ [21,83]，代价侧 TRUE = 0 帧）。

    因此本投影把 wall_left 定义为**可摸牌墙余量** = max(0, 公开余量 − 保留区)：
    合同阈值不动（8/16 仍是 §7.3 的阈值，三值语义不变），只让它们重新有内容。
    """

    if remaining_tile_count is None:
        return None
    return max(0, int(remaining_tile_count) - wall_reserve_tiles())


#: 无等待语义的候选事实分类（接口契约禁止它们携带向听/有效牌数值）。
_NON_WAITING_FACT_KINDS: Tuple[str, ...] = ("win", "not_applicable", "analysis_failed")


def _combined_shanten_state(facts: Any) -> Tuple[Optional[int], str]:
    """可比较向听 + 判别标签（P9 修复：区分"不适用"与"未知"）。

    - known：有可比较的分牌型向听值（standard/seven_pairs 至少一个非空）；
    - not_applicable：**无等待语义的候选事实**（fact_kind ∈ WIN /
      NOT_APPLICABLE / ANALYSIS_FAILED —— 接口契约禁止这三类携带向听数值，
      见 hangma/interface.py CandidateFacts 不变量）。按 §7.3 第 2 条这类分支
      **永不可比较**：既不能当 b 也不能当 c，补全任何值都不会让它满足条件 ⇒
      判定为 definitive 排除，不触发 UNKNOWN；
    - unknown：HAND_PROGRESS 但分牌型未分析/无事实——真正的缺失（可补全），
      维持原三值语义。

    修复前 not_applicable 与 unknown 都投影成 combined_shanten=null，谓词的存在性
    分析把"不适用"当"缺失" ⇒ 合法 hu 窗口被判 UNKNOWN（P9 Q1 实测：代价侧
    4/331 帧、机会侧 4/331 帧）。
    """

    if facts is None:
        return None, "unknown"
    kind = getattr(facts, "fact_kind", None)
    kind_name = str(getattr(kind, "value", kind) or "")
    if kind_name in _NON_WAITING_FACT_KINDS:
        return None, "not_applicable"
    shanten = _combined_shanten(facts)
    return shanten, ("known" if shanten is not None else "unknown")


def project_predicate_facts(observation: PlayerObservation, analysis: RuleAnalysis) -> dict:
    """把一个动作窗口的玩家可见事实投影为八谓词输入合同形状（纯函数）。

    输入只允许 (PlayerObservation, RuleAnalysis)：wall_left 取
    observation.remaining_tile_count 换算出的**可摸牌墙余量**（见
    wall_left_drawable；None 透传为未知），分支逐个来自
    analysis.legal_candidates；不读取 WorldState 或任何世界私有字段，不预测
    未来事件（T09 红线）。

    输出形状与 tools/sitin_predicates_v4.evaluate_predicates 的输入合同逐字段
    一致：{"wall_left": int|None, "branches": [{action_key, combined_shanten,
    shanten_state, family_progress, route_status, support_remaining}, ...]}；另附
    family_route_status（按家族路线证据明细；谓词模块忽略额外键，仅供审计）。

    歧义处理决定：
    - combined_shanten 只取分牌型（standard/seven_pairs）非空项的最小值，整体
      shanten_after 不参与（与 FollowupBranchFacts.combined_shanten 口径一致）；
    - shanten_state（P9 修复）区分"不适用"（not_applicable）与"未知"
      （unknown）：前者永不可比较，后者才是可能补全的缺失；
    - route_status 聚合见 _route_status_aggregate。
    """

    branches = []
    for candidate in analysis.legal_candidates:
        facts = candidate.facts
        progress, route = _family_maps(facts)
        support = _support_remaining(facts, candidate.value_facts)
        shanten, shanten_state = _combined_shanten_state(facts)
        branches.append(
            {
                "action_key": candidate.action_key,
                "combined_shanten": shanten,
                "shanten_state": shanten_state,
                "family_progress": progress,
                "route_status": _route_status_aggregate(route),
                "support_remaining": support,
                "family_route_status": dict(route),
            }
        )
    return {
        "wall_left": wall_left_drawable(observation.remaining_tile_count),
        "branches": branches,
    }


# ---------------------------------------------------------------------------
# 夹具：观察构造与脚本帧（零真实桌赛；窗口观察为纯构造，不含未来牌值）
# ---------------------------------------------------------------------------


def fixture_observation(
    *,
    game_id: str,
    seat: int,
    phase: str,
    hand: str,
    drawn: Optional[str],
    trigger_seq: int,
    wall_left: int,
    scores: Tuple[int, int, int, int],
    last_discard: Optional[Tuple[int, str]] = None,
) -> PlayerObservation:
    """构造夹具窗口观察；hand 为空格分隔牌值串（该座位自己可见的手牌）。

    P9 FAMCOST（投影单位修正）：wall_left 参数按**八谓词口径**声明
    （= 可摸牌墙余量），本函数换算成观察的公开余量
    （remaining_tile_count = 声明的 wall_left + 保留区 20 张）。
    这样夹具声明的阈值语义与投影后的 wall_left 逐字一致，夹具用例不需要
    改写阈值意图；公开余量的物理下界（20）也由同一个换算点保证。
    """

    tiles = tuple(Tile(code) for code in hand.split())
    public_wall = int(wall_left) + wall_reserve_tiles()
    # turn_seat 语义：摸牌窗口=本人回合；响应窗口=弃牌者回合（官方口径，
    # 决定合法性分析能否给出候选）。
    turn_seat = seat if phase == "draw" else (last_discard[0] if last_discard else 0)
    return PlayerObservation(
        game_id=game_id,
        seat=seat,
        round_no=1,
        snapshot_seq=trigger_seq,
        phase=phase,
        dealer_seat=0,
        turn_seat=turn_seat,
        responding_seats=() if phase == "draw" else (seat,),
        my_hand=tiles,
        drawn_tile=None if drawn is None else Tile(drawn),
        discards=((), (), (), ()),
        melds=((), (), (), ()),
        hand_counts=(len(tiles), 13, 13, 13),
        last_discard=(
            None if last_discard is None
            else PublicDiscard(last_discard[0], Tile(last_discard[1]), trigger_seq)
        ),
        remaining_tile_count=public_wall,
        scores=scores,
        rule_state=RulePublicState(Tile("白"), False, 0, False),
        public_history=(),
    )


@dataclass(frozen=True)
class FixtureWindowSpec:
    """夹具帧里一个决策窗口的构造参数（不含任何未来牌值/牌墙顺序）。"""

    game_id: str
    seat: int
    phase: str
    hand: str
    drawn: Optional[str]
    trigger_seq: int
    wall_left: int
    scores: Tuple[int, int, int, int]
    last_discard: Optional[Tuple[int, str]] = None


@dataclass(frozen=True)
class FixtureFrameSpec:
    """夹具脚本的一帧：决策窗口列表或终局（scores_from_outcome 用上一帧选择映射）。"""

    revision: int
    windows: Tuple[FixtureWindowSpec, ...] = ()
    completed_hands: int = 0
    final_scores: Optional[Tuple[int, int, int, int]] = None
    scores_from_outcome: bool = False
    outcome_branch: Optional[Mapping[str, Tuple[int, int, int, int]]] = None


@dataclass(frozen=True)
class FixtureSpec:
    """MatchSpec 等价信息（座位/对手策略/剩余赛程由快照另行携带）。"""

    match_id: str
    scenario_id: str
    seed: int
    rounds_per_game: int
    initial_dealer: int
    initial_scores: Tuple[int, int, int, int]


@dataclass(frozen=True)
class _FixtureWorld:
    """夹具世界（不透明 token；评估侧不读其字段）。"""

    token: int


class ScriptedFixtureEngine:
    """脚本帧假引擎：公开 start/frame/advance 接口形状 + 真规则合法动作见证。

    - **fixture_mode=True（Q1 修复⑤）：仅工具测试/夹具验收可用**；v2_behavior
      真实路径绝不调用本类（_forbid_fixture_engine 强制拒绝）；
    - 不运行任何真实桌赛（预算红线）；帧序列由夹具模板确定性生成；
    - advance 对每个选择用注入规则重新 rules.analyze 并要求动作在合法候选
      中（合法动作见证），非法选择 ValueError（与真实引擎的拒绝语义一致）；
    - outcome_branch 把截取帧焦点座位的选择映射到下一终局帧积分（夹具
      语义，非规则结算；费用账记 fixture_outcome_mapping 降级）。
    """

    fixture_mode = True

    def __init__(self, frames: Sequence[FixtureFrameSpec], rules: Any, *,
                 value_limits: Optional[ValueAnalysisLimits] = None) -> None:
        self._frames = tuple(frames)
        self._rules = rules
        self._value_limits = value_limits
        self._cursor: Dict[int, int] = {}
        self._pending: Dict[int, Tuple[int, int, int, int]] = {}
        self._last: Dict[int, Any] = {}
        self._next_token = 0
        self.advance_calls: List[Tuple[int, int, Tuple[Any, ...]]] = []

    def start(self, spec: Any) -> _FixtureWorld:
        token = self._next_token
        self._next_token += 1
        self._cursor[token] = 0
        return _FixtureWorld(token)

    def frame(self, world: _FixtureWorld) -> Any:
        cursor = self._cursor.get(world.token, 0)
        if cursor >= len(self._frames):
            raise AssertionError("夹具脚本帧已耗尽；驱动不应在终态后继续取帧")
        spec = self._frames[cursor]
        if spec.final_scores is not None or spec.scores_from_outcome:
            scores = spec.final_scores
            if spec.scores_from_outcome:
                scores = self._pending.get(world.token)
                if scores is None:
                    raise ValueError("终局帧缺少上一帧选择映射的结果积分")
            frame = SimpleNamespace(
                revision=spec.revision,
                decisions=(),
                completed_hands=spec.completed_hands,
                final_scores=scores,
                blocked_reason=None,
            )
            self._last[world.token] = frame
            return frame
        decisions = tuple(
            SimpleNamespace(
                window_key=WindowKey(
                    game_id=window.game_id,
                    round_no=1,
                    trigger_seq=window.trigger_seq,
                    phase=WindowPhase(window.phase),
                    seat=window.seat,
                ),
                observation=fixture_observation(
                    game_id=window.game_id,
                    seat=window.seat,
                    phase=window.phase,
                    hand=window.hand,
                    drawn=window.drawn,
                    trigger_seq=window.trigger_seq,
                    wall_left=window.wall_left,
                    scores=window.scores,
                    last_discard=window.last_discard,
                ),
                timeout_seconds=3.0,
            )
            for window in spec.windows
        )
        frame = SimpleNamespace(
            revision=spec.revision,
            decisions=decisions,
            completed_hands=spec.completed_hands,
            final_scores=None,
            blocked_reason=None,
        )
        self._last[world.token] = frame
        return frame

    def advance(self, world: _FixtureWorld, revision: int, choices: Tuple[Any, ...]) -> _FixtureWorld:
        last = self._last.get(world.token)
        if last is None or revision != last.revision:
            raise ValueError("旧 revision 拒绝：{0}".format(revision))
        expected = [decision.window_key for decision in last.decisions]
        provided = [choice.window_key for choice in choices]
        if provided != expected:
            raise ValueError("窗口集合不匹配：期望 {0}，得到 {1}".format(expected, provided))
        spec = self._frames[self._cursor[world.token]]
        for decision, choice in zip(last.decisions, choices):
            key = action_key(choice.action)
            analysis = self._analyze(decision.observation)
            if not any(cand.action_key == key for cand in analysis.legal_candidates):
                raise ValueError(
                    "动作 {0} 不在座位 {1} 的窗口合法候选中（夹具合法动作见证）".format(
                        key, decision.window_key.seat
                    )
                )
        if spec.outcome_branch is not None:
            focal_key = None
            for decision, choice in zip(last.decisions, choices):
                if decision.window_key.seat == 0:
                    focal_key = action_key(choice.action)
            table = dict(spec.outcome_branch)
            self._pending[world.token] = table.get(
                "seat0:{0}".format(focal_key), table["default"]
            )
        self.advance_calls.append((world.token, revision, tuple(choices)))
        self._cursor[world.token] = self._cursor[world.token] + 1
        return _FixtureWorld(world.token)

    def _analyze(self, observation: PlayerObservation) -> RuleAnalysis:
        if self._value_limits is None:
            return self._rules.analyze(observation)
        return self._rules.analyze(observation, value_limits=self._value_limits)


#: 夹具模板表：固定顺序（miss → unknown → hit 的 branch_open 种子局面）。
#: 模板在先、判定在后：生成尝试按 attempt_index 循环取模板，预分配谓词是否
#: TRUE 由真规则分析 + 八谓词在生成时真实判定（本表实测种子局面由
#: hangma 规则引擎对构造观察的纯分析得出，零真实桌赛）。
FIXTURE_TEMPLATE_SEQUENCE: Tuple[str, ...] = (
    "pair_wait",     # branch_open FALSE（pass 单分支，无满足对）
    "draw_unknown",  # branch_open UNKNOWN（hu 分支 shanten 缺失触发缺失分析）
    "peng_branch",   # branch_open TRUE（peng:5w 分支对 pass 的可见取舍）
)


def build_fixture_frames(template_id: str, *, match_id: str, focal_seat: int = 0) -> List[FixtureFrameSpec]:
    """按模板 id 构造夹具帧序列：[前缀帧, 截取候选帧, 终局帧]。

    - 前缀帧：焦点外座位 1 的摸牌窗口（生成尝试未命中时按固定行为策略推进，
      形成合法动作前缀）；
    - 截取候选帧：焦点座位窗口（响应或摸牌）；peng_branch 模板另含座位 2
      同帧响应窗口（验证"未推进响应者续打时按帧观察重新决策"）；
    - 终局帧：scores_from_outcome——按截取帧焦点座位的选择映射积分（夹具
      语义，非规则结算；费用账记 fixture_outcome_mapping 降级）。
    """
    prefix_window = FixtureWindowSpec(
        game_id=match_id,
        seat=1,
        phase="draw",
        hand="1w 2w 3w 4w 5w 6w 7w 8w 9w 1t 2t 3t 5b",
        drawn="5b",
        trigger_seq=7,
        wall_left=60,
        scores=(2, -1, 0, -1),
    )
    if template_id == "pair_wait":
        cut_windows = (
            FixtureWindowSpec(
                game_id=match_id,
                seat=focal_seat,
                phase="response_peng",
                hand="2t 2t 3t 4t 5t 6t 7t 8t 9t 1b 2b 3b 4b",
                drawn=None,
                trigger_seq=10,
                wall_left=60,
                scores=(2, -1, 0, -1),
                last_discard=(3, "5w"),
            ),
        )
    elif template_id == "draw_unknown":
        cut_windows = (
            FixtureWindowSpec(
                game_id=match_id,
                seat=focal_seat,
                phase="draw",
                hand="1w 2w 3w 4w 5w 6w 7w 8w 9w 1t 2t 3t 5b",
                drawn="5b",
                trigger_seq=10,
                wall_left=60,
                scores=(2, -1, 0, -1),
            ),
        )
    elif template_id == "peng_branch":
        cut_windows = (
            FixtureWindowSpec(
                game_id=match_id,
                seat=focal_seat,
                phase="response_peng",
                hand="5w 5w 1t 2t 3t 4t 5t 6t 7t 8t 9t 2b 3b",
                drawn=None,
                trigger_seq=10,
                wall_left=60,
                scores=(2, -1, 0, -1),
                last_discard=(3, "5w"),
            ),
            FixtureWindowSpec(
                game_id=match_id,
                seat=2,
                phase="response_peng",
                hand="1b 2b 4b 5b 6b 7b 8b 9b 3t 4t 5t 6t 7t",
                drawn=None,
                trigger_seq=10,
                wall_left=60,
                scores=(2, -1, 0, -1),
                last_discard=(3, "5w"),
            ),
        )
    else:
        raise ValueError("未知夹具模板 {0!r}".format(template_id))
    return [
        FixtureFrameSpec(revision=1, windows=(prefix_window,), completed_hands=0),
        FixtureFrameSpec(revision=2, windows=cut_windows, completed_hands=0,
                         outcome_branch={
                             "seat0:peng:5w": (6, -2, -2, -2),
                             "default": (2, 0, -1, -1),
                         }),
        FixtureFrameSpec(revision=3, completed_hands=1, scores_from_outcome=True),
    ]


# ---------------------------------------------------------------------------
# 夹具策略：固定行为策略（前缀生成）与双臂策略（只收 PlayerObservation）
# ---------------------------------------------------------------------------


class FixtureBehaviorPolicy:
    """夹具行为策略：固定确定性偏好序列，不随被测候选改变（v4 §7.2 条 1）。

    只读 DecisionRequest（观察+规则分析）；无合法偏好时按 action_key 升序取
    第一个合法候选；无合法候选返回空计划（由驱动按保底规则处理）。
    """

    def __init__(self, policy_id: str, prefer: Sequence[str] = ()) -> None:
        self.policy_id = policy_id
        self._prefer = tuple(prefer)

    async def choose(self, request: Any, budget: Any) -> DecisionPlan:
        candidates = {c.action_key: c for c in request.rules.legal_candidates}
        chosen = None
        for key in self._prefer:
            if key in candidates:
                chosen = candidates[key]
                break
        if chosen is None and candidates:
            chosen = candidates[min(candidates)]
        ranked = ()
        if chosen is not None:
            ranked = (
                RankedCandidate(
                    action=chosen.action,
                    action_key=chosen.action_key,
                    rank=1,
                    total_score=1.0,
                    score_parts=(),
                    reasons=("fixture-behavior:" + self.policy_id,),
                    is_emergency=False,
                ),
            )
        return DecisionPlan(
            decision_id=request.decision_id,
            window_key=request.window_key,
            based_on_authoritative_seq=request.observation.snapshot_seq,
            revision=1,
            candidates=ranked,
            degraded_reasons=(),
        )


class RaisingPolicy:
    """总抛错的策略（T16 构造：一臂执行失败）。"""

    def __init__(self, policy_id: str = "fixture-raising") -> None:
        self.policy_id = policy_id

    async def choose(self, request: Any, budget: Any) -> DecisionPlan:
        raise RuntimeError("T16 构造：本臂策略执行失败（policy_id={0}）".format(self.policy_id))


def fixture_choice(window_key: WindowKey, action: Action) -> Any:
    """choice_factory：夹具选择对象与真实引擎同形（SimulationChoice 形状）。"""
    from hangma_bot.simulation.interface import SimulationChoice

    return SimulationChoice(window_key=window_key, action=action)


# ---------------------------------------------------------------------------
# legal-prefix-v1：生成尝试（§7.2 条 1/2/6）
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AttemptOutcome:
    """一次前缀生成尝试的结果。"""

    status: str  # hit / miss / unknown / exhausted
    template_id: Optional[str] = None
    attempt_index: int = 0
    source_root_id: Optional[str] = None
    spec_seed: int = 0  # 生成尝试实际使用的 spec.seed（快照持久化，重建用）
    prefix: Tuple[Mapping[str, Any], ...] = ()
    cut_frame: Any = None
    cut_decision: Any = None
    predicate_values: Optional[Mapping[str, str]] = None
    predicate_witness: Optional[Mapping[str, Any]] = None
    projected_facts: Optional[Mapping[str, Any]] = None
    #: 前缀行为策略装配/执行绑定记录（M2：装配对象 ↔ 执行记录 ↔ 根摘要）。
    prefix_execution: Optional[Mapping[str, Any]] = None


def analyze_window(rules: Any, observation: PlayerObservation,
                   value_limits: Optional[ValueAnalysisLimits]) -> RuleAnalysis:
    """窗口规则分析（生成与续打同口径：同一 value_limits）。"""
    if value_limits is None:
        return rules.analyze(observation)
    return rules.analyze(observation, value_limits=value_limits)


def run_prefix_attempt(
    *,
    rules: Any,
    template_id: str,
    predicate_id: str,
    focal_seat: int,
    attempt_index: int,
    source_root_id: str,
    match_id: str,
    value_limits: Optional[ValueAnalysisLimits] = None,
    behavior_policy: Optional[Any] = None,
    choice_factory: Optional[Callable[[WindowKey, Action], Any]] = None,
) -> AttemptOutcome:
    """跑一次夹具前缀尝试：焦点座位行动前判预分配谓词，首次命中即截取。

    - 谓词判定只用 (观察, 规则分析) 玩家可见事实（project_predicate_facts
      + evaluate_predicates），不读世界私有状态、不看未来帧；
    - 未命中时整帧按固定行为策略推进（合法动作见证由引擎 advance 核验）；
    - 尝试结束：hit（首次 TRUE）/ miss（全程 FALSE）/ unknown（出现过
      UNKNOWN 且无 TRUE）。
    """
    if predicate_id not in PREDICATE_IDS:
        raise ValueError("predicate_id 必须是八谓词之一：{0}".format(predicate_id))
    frames = build_fixture_frames(template_id, match_id=match_id, focal_seat=focal_seat)
    engine = ScriptedFixtureEngine(frames, rules, value_limits=value_limits)
    spec = FixtureSpec(
        match_id=match_id,
        scenario_id=source_root_id,
        seed=attempt_index,
        rounds_per_game=8,
        initial_dealer=0,
        initial_scores=(0, 0, 0, 0),
    )
    behavior = behavior_policy or FixtureBehaviorPolicy(
        "fixture-behavior-v2-standin", prefer=("pass",)
    )
    chooser = choice_factory or fixture_choice
    world = engine.start(spec)
    prefix: List[Mapping[str, Any]] = []
    seen_unknown = False
    last_values: Dict[str, str] = {}
    last_witness: Dict[str, Any] = {}
    last_facts: Optional[Mapping[str, Any]] = None
    last_cut = None
    while True:
        frame = engine.frame(world)
        if frame.final_scores is not None or frame.blocked_reason is not None:
            break
        focal = [d for d in frame.decisions if d.window_key.seat == focal_seat]
        if focal:
            decision = focal[0]
            analysis = analyze_window(rules, decision.observation, value_limits)
            facts = project_predicate_facts(decision.observation, analysis)
            results = evaluate_predicates(facts)
            last_values = {key: item["value"] for key, item in results.items()}
            last_facts = facts
            last_cut = decision
            if results[predicate_id]["value"] == "TRUE":
                return AttemptOutcome(
                    status="hit",
                    template_id=template_id,
                    attempt_index=attempt_index,
                    source_root_id=source_root_id,
                    spec_seed=attempt_index,
                    prefix=tuple(prefix),
                    cut_frame=frame,
                    cut_decision=decision,
                    predicate_values=last_values,
                    predicate_witness=results[predicate_id].get("witness"),
                    projected_facts=facts,
                )
            if results[predicate_id]["value"] == "UNKNOWN":
                seen_unknown = True
        choices = []
        for decision in frame.decisions:
            analysis = analyze_window(rules, decision.observation, value_limits)
            plan = asyncio.run(behavior.choose(_window_request(decision, analysis, match_id), None))
            action = None if not plan.candidates else plan.candidates[0].action
            if action is None:
                raise ValueError("行为策略在窗口 {0} 未给出动作（夹具前缀无法推进）".format(
                    decision.window_key))
            choices.append(chooser(decision.window_key, action))
        world = engine.advance(world, frame.revision, tuple(choices))
        prefix.extend(
            {"window_key": window_key_to_json(choice.window_key),
             "action_key": action_key(choice.action)}
            for choice in choices
        )
    return AttemptOutcome(
        status="unknown" if seen_unknown else "miss",
        template_id=template_id,
        attempt_index=attempt_index,
        source_root_id=source_root_id,
        prefix=tuple(prefix),
        predicate_values=last_values,
        predicate_witness=None,
        projected_facts=last_facts,
    )


def _window_request(decision: Any, analysis: RuleAnalysis, match_id: str) -> Any:
    """给行为策略组装最小 DecisionRequest 形状（只用该窗口可见事实）。"""
    from hangma_bot.kernel.observation import CompetitionContext

    window_key = decision.window_key
    return SimpleNamespace(
        observation=decision.observation,
        competition=CompetitionContext(
            tournament_id=match_id, stage_no=None, stage_role=None,
            stage_total=None, participant_rank=None, ranking=(), observed_at_unix_ms=0,
        ),
        rules=analysis,
        decision_id="{0}:gen:{1}:{2}:seat{3}".format(
            match_id, window_key.round_no, window_key.trigger_seq, window_key.seat),
        trigger_seq=window_key.trigger_seq,
        window_key=window_key,
        rejected_attempts=(),
    )


# ---------------------------------------------------------------------------
# 真实路径（R3 修复 Q1）：组合根运行时 + 冻结行为策略 + 自然开局真实合法前缀
# ---------------------------------------------------------------------------


def runtime_kind_of(runtime: Any) -> Optional[str]:
    """读运行时装配标签；无标签返回 None（调用方据此拒绝，不猜真伪）。"""

    if isinstance(runtime, Mapping):
        kind = runtime.get("runtime_kind")
        if kind in RUNTIME_KINDS:
            return str(kind)
    return None


def _module_source_digest(cls: Any) -> Optional[str]:
    """引擎类所在模块源文本摘要（无 rules_hash 时的可复算版本见证；取不到记 None）。"""

    module = sys.modules.get(getattr(cls, "__module__", "") or "")
    path = Path(getattr(module, "__file__", "") or "")
    if not path.is_file():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def engine_identity(engine: Any) -> Dict[str, Any]:
    """引擎身份事实（**来自引擎对象本身**）：类名/模块/fixture_mode/实际引擎版本。

    实际引擎版本优先取真实引擎的组合根注入 rules_hash（规则源清单稳定哈希，
    simulation.artifacts.compute_rules_hash 口径）；缺失则取引擎类所在模块源
    摘要；两者都取不到如实记 None，不伪造版本。
    """

    cls = type(engine)
    rules_hash = getattr(engine, "rules_hash", None)
    return {
        "class": cls.__name__,
        "qualname": "{0}.{1}".format(cls.__module__, cls.__qualname__),
        "fixture_mode": bool(getattr(engine, "fixture_mode", False)),
        "engine_version": (str(rules_hash) if rules_hash
                           else _module_source_digest(cls)),
    }


def _tag_runtime(runtime: Mapping[str, Any], *, kind: str, entry: str) -> Dict[str, Any]:
    """给运行时打装配标签（种类 + 入口 + 引擎身份）；不改 engine/工厂三件套。"""

    tagged = dict(runtime)
    tagged["runtime_kind"] = kind
    tagged["runtime_entry"] = entry
    tagged["real_tables"] = kind in SELECTION_ELIGIBLE_RUNTIME_KINDS
    tagged["engine_identity"] = engine_identity(runtime["engine"])
    return tagged


def resolve_declared_runtime(runtime: Any, *, where: str) -> Mapping[str, Any]:
    """核对注入运行时：缺失 / 夹具引擎 / 无装配标签一律拒绝（fail-closed）。

    A1 修复要点：**不得按「是否传入 runtime」推断真伪**，也不得在缺省时注入
    替身；真实运行时由 build_real_runtime（组合根）装配并带 RUNTIME_KIND_REAL
    标签，替身只能经显式测试入口 build_test_runtime_double 装配并带
    RUNTIME_KIND_TEST_DOUBLE 标签。
    """

    if runtime is None:
        raise RuntimeAssemblyError(
            "{0}：真实路径的运行时必须在**组合处显式装配**"
            "（sitin_opportunities.build_real_runtime(...)，或组合根 "
            "bootstrap.build_evaluation_runtime('matches', ...)）；缺省不再注入"
            "替身（A1 fail-closed；替身只能经显式测试入口 "
            "build_test_runtime_double 传入）".format(where))
    if not isinstance(runtime, Mapping) or "engine" not in runtime:
        raise RuntimeAssemblyError(
            "{0}：运行时必须是含 engine/spec_factory/choice_factory 的映射，"
            "得到 {1}".format(where, type(runtime).__name__))
    _forbid_fixture_engine(runtime["engine"], where)
    kind = runtime_kind_of(runtime)
    if kind is None:
        raise RuntimeAssemblyError(
            "{0}：运行时缺少装配标签 runtime_kind，无法区分真实运行时与验证替身"
            "（A1：不得按「是否传入 runtime」推断）；请经 build_real_runtime 或"
            "显式测试入口 build_test_runtime_double 装配".format(where))
    if kind == RUNTIME_KIND_FIXTURE:
        raise RuntimeAssemblyError(
            "{0}：夹具引擎不得进入真实路径（runtime_kind={1}）".format(where, kind))
    return runtime


def engine_kind_for(*, prefix_source: str, runtime: Any) -> str:
    """引擎种类（A1(c)）：由**运行时种类**决定，不从「是否传入 runtime」推断。"""

    if prefix_source == "scripted_fixture":
        return ENGINE_KIND_BY_RUNTIME_KIND[RUNTIME_KIND_FIXTURE]
    kind = runtime_kind_of(runtime)
    if kind is None:
        raise RuntimeAssemblyError(
            "engine_kind_for：真实路由（{0}）需要已装配的运行时（缺 runtime_kind "
            "标签）".format(prefix_source))
    return ENGINE_KIND_BY_RUNTIME_KIND[kind]


def execution_kind_for(*, prefix_source: str, runtime: Any) -> str:
    """执行类别：夹具路径=scripted_fixture；真实路由按运行时种类分 real/替身。"""

    if prefix_source == "scripted_fixture":
        return EXECUTION_SCRIPTED_FIXTURE
    kind = runtime_kind_of(runtime)
    if kind is None:
        raise RuntimeAssemblyError(
            "execution_kind_for：真实路由（{0}）需要已装配的运行时".format(prefix_source))
    return EXECUTION_KIND_BY_RUNTIME_KIND[kind]


def selection_eligible_for(runtime_kind: Optional[str]) -> bool:
    """只有真实运行时的结果可用于开发选留与效果反馈（替身/夹具一律不可）。"""

    return runtime_kind in SELECTION_ELIGIBLE_RUNTIME_KINDS


def _forbid_fixture_engine(engine: Any, where: str) -> None:
    """Q1 修复⑤：真实路径绝不使用夹具引擎（fixture_mode=True 仅工具测试可用）。"""
    if getattr(engine, "fixture_mode", False):
        raise ValueError(
            "{0} 不得使用 fixture_mode 引擎（仅工具测试/夹具验收可用；v2_behavior "
            "真实路径必须走组合根 SimulationEngine 公开 start/frame/advance 或"
            "注入的公开契约验证替身）".format(where)
        )
    if isinstance(ScriptedFixtureEngine, type) and isinstance(engine, ScriptedFixtureEngine):
        raise ValueError(
            "{0} 不得使用 ScriptedFixtureEngine（fixture_mode=True 仅工具测试/"
            "夹具验收可用；v2_behavior 真实路径必须走组合根 SimulationEngine "
            "公开 start/frame/advance 或注入的公开契约验证替身）".format(where)
        )


def build_real_runtime(
    *,
    rules_config: RuleConfig,
    rounds_per_game: int,
    clock_mode: str = "logical",
    seed: int = 0,
    scenario_id: str = "sitin-opportunities-real",
) -> Mapping[str, Any]:
    """装配组合根真实运行时（与 sitin_stage.execute_table / natural panel 同一路径）。

    还认 {"engine": SimulationEngine, "spec_factory", "choice_factory"}；只做装配
    （零桌赛执行）——start/advance 由调用方在授权预算内驱动。测试/夹具验收可
    用等价公开契约替身注入 runtime 参数，不触本函数。
    """
    from hangma_bot import bootstrap
    from hangma_bot.kernel.config import TimingConfig, TournamentConfig
    from hangma_bot.offline.evaluate import (
        BOOTSTRAP_RUNTIME_HOOK,
        MatchExperiment,
        MatchSeedSpec,
        PolicyDeclaration,
    )

    tournament_config = TournamentConfig(
        max_games=1,
        rounds_per_game=int(rounds_per_game),
        rules=rules_config,
        timing=TimingConfig(**dict(stage.DEFAULT_TIMING)),
    )
    runtime = getattr(bootstrap, BOOTSTRAP_RUNTIME_HOOK)("matches", MatchExperiment(
        kind="matches", clock_mode=clock_mode,
        baseline=PolicyDeclaration(policy_id="opp-slot-a", name="panel", weights=()),
        challenger=PolicyDeclaration(policy_id="opp-slot-b", name="panel", weights=()),
        opponents=tuple(PolicyDeclaration(policy_id="opp-slot-{0}".format(index),
                                          name="panel", weights=())
                        for index in (3, 4, 5)),
        tournament_config=tournament_config,
        seeds=(MatchSeedSpec(seed=int(seed), scenario_id=scenario_id),),
        seat_permutations=(stage.IDENTITY_PERMUTATION,), initial_dealer=0,
        initial_scores=(0, 0, 0, 0),
    ))
    if not isinstance(runtime, Mapping):
        raise RuntimeError("组合根未装配 matches 运行时；本工具不伪造模拟引擎")
    _forbid_fixture_engine(runtime["engine"], "build_real_runtime")
    return _tag_runtime(runtime, kind=RUNTIME_KIND_REAL, entry="build_real_runtime")


def build_test_runtime_double(*, rules: Any,
                              value_limits: Any = None) -> Mapping[str, Any]:
    """**显式测试入口**：装配公开契约验证替身（RUNTIME_KIND_TEST_DOUBLE，0 真实桌赛）。

    只有测试/夹具验收可以调用本函数并把结果注入 runtime；生产路径（正式 CLI、
    状态机缺省、build_panel 缺省）不会调用它——run_av_evaluation 在缺 runtime 时
    直接拒绝（A1 fail-closed），所以替身在正式路径不可达。返回的运行时带
    runtime_kind 标签，产物据此标注 execution_kind=test_double，且
    selection_eligible=False（不得参与开发选留与效果反馈）。
    """

    import c1_runtime_double as double

    runtime = double.build_runtime_double(rules, value_limits)
    if not isinstance(runtime, Mapping):
        raise RuntimeAssemblyError("公开契约替身未返回运行时映射")
    return _tag_runtime(runtime, kind=RUNTIME_KIND_TEST_DOUBLE,
                        entry="build_test_runtime_double")


def opponent_policy_names(contract: Mapping[str, Any], opponent_scenario: str) -> List[str]:
    """从 group-dev-v1 合同读对手情景的 per-seat 策略名（H/M 单一事实源）。"""
    scenario = (contract.get("panel", {}).get("opponent_scenarios") or {}).get(
        str(opponent_scenario))
    if not scenario:
        raise ValueError("合同缺少对手情景 {0!r}".format(opponent_scenario))
    names = [str(name) for name in scenario.get("opponent_policies") or ()]
    if len(names) != 3:
        raise ValueError("对手情景 {0} 应有 3 家策略，得到 {1}".format(
            opponent_scenario, names))
    return names


def participant_ids_by_seat(focal_seat: int) -> Tuple[str, str, str, str]:
    """座位 0—3 的参赛者身份：焦点座位=focal，其余=opp-N（对手顺序按座位升序）。"""
    by_seat = [""] * 4
    opp_index = 0
    for seat in range(4):
        if seat == focal_seat:
            by_seat[seat] = FOCAL_PARTICIPANT
        else:
            by_seat[seat] = "opp-{0}".format(opp_index)
            opp_index += 1
    return (by_seat[0], by_seat[1], by_seat[2], by_seat[3])


def frozen_generation_policies(
    *, opponent_names: Sequence[str], focal_seat: int,
    monotonic: Callable[[], float],
) -> Tuple[Any, Any, Any, Any]:
    """冻结行为策略（§7.2 条 1）：焦点座位=固定 V2；对手按合同情景装配。

    行为策略不随被评估候选改变；装配走 sitin_stage.build_panel_policy 白名单
    （单一实现）。"""
    by_seat: List[Any] = [None] * 4
    opponents = iter(stage.build_panel_policy(str(name), monotonic)
                     for name in opponent_names)
    for seat in range(4):
        if seat == focal_seat:
            by_seat[seat] = stage.build_panel_policy(BASELINE_FOCAL_POLICY, monotonic)
        else:
            by_seat[seat] = next(opponents)
    return (by_seat[0], by_seat[1], by_seat[2], by_seat[3])


def _object_token(policy: Any) -> Optional[str]:
    """进程内对象身份 token（核对「执行记录用的是不是装配的那个对象」）。

    只在同进程装配/执行核对里有效（跨进程重放不可比），持久化字段另存
    policy_id/policy_class 供事后审计。
    """

    return None if policy is None else "obj:{0:x}".format(id(policy))


def _expected_policy_class(name: str) -> str:
    """冻结合同策略名 → 白名单装配出的策略类名（单一实现 sitin_stage 白名单）。"""

    return type(stage.build_panel_policy(str(name), lambda: 800.0)).__name__


def verify_prefix_behavior_binding(
    *,
    opponent_scenario: str,
    expected_opponent_names: Sequence[str],
    policies_by_seat: Sequence[Any],
    focal_seat: int,
    execution: Optional[Mapping[str, Any]] = None,
    check_object_identity: bool = False,
) -> Dict[str, Any]:
    """M2 修复：核对**装配对象**与合同情景、执行记录是否一致（不只看字符串标签）。

    逐座位产出身份行 {seat, assigned_name, policy_id, policy_class, object_token,
    windows}：
    - assigned_name：由冻结合同情景推出的该座位应有策略名（焦点=V2 基线，其余按
      对手名顺序铺开）；
    - policy_class：装配对象的**类**，必须等于 sitin_stage 白名单按该名字装配出的
      类（对象级核对；只对标签字符串不足以防 M 情景前缀由 H 对手生成）；
    - object_token/windows：执行记录里该座位实际使用的策略对象与决策窗口数；
      check_object_identity=True 时要求执行对象 token 与装配对象 token 相同
      （证明"执行记录用的是装配的那个对象"，而不是同名替身）。
    """

    names = [str(name) for name in expected_opponent_names or ()]
    problems: List[str] = []
    if len(names) != 3:
        problems.append("冻结合同情景 {0} 应有 3 家对手策略，得到 {1}".format(
            opponent_scenario, len(names)))
    rows: List[Dict[str, Any]] = []
    executed: Dict[int, Mapping[str, Any]] = {}
    for row in (execution or {}).get("by_seat") or ():
        executed[int(row.get("seat", -1))] = row
    assigned_iter = iter(names)
    policies = list(policies_by_seat or ())
    for seat in range(4):
        assigned = (BASELINE_FOCAL_POLICY if seat == focal_seat
                    else next(assigned_iter, None))
        policy = policies[seat] if seat < len(policies) else None
        row = {
            "seat": seat, "assigned_name": assigned,
            "policy_id": str(getattr(policy, "policy_id", "") or ""),
            "policy_class": (None if policy is None else type(policy).__name__),
            "object_token": _object_token(policy),
            "windows": int((executed.get(seat) or {}).get("windows") or 0),
        }
        rows.append(row)
        if policy is None:
            problems.append("座位 {0} 缺行为策略对象（合同情景 {1} 应有 {2}）".format(
                seat, opponent_scenario, assigned))
            continue
        if assigned is None:
            continue
        expected_class = _expected_policy_class(assigned)
        if row["policy_class"] != expected_class:
            problems.append(
                "座位 {0} 的装配对象 {1} 与冻结合同情景 {2} 应有的 {3}（{4}）不符："
                "机会前缀不得由合同外对手生成".format(
                    seat, row["policy_class"], opponent_scenario, expected_class,
                    assigned))
        if check_object_identity:
            record = executed.get(seat)
            if record is not None and record.get("object_token") != row["object_token"]:
                problems.append(
                    "座位 {0} 执行记录中的策略对象不是装配对象（记录 {1} ≠ 装配 {2}）："
                    "只核对名字标签不足以证明前缀由合同对手生成".format(
                        seat, record.get("object_token"), row["object_token"]))
    if len(policies) != 4:
        problems.append("行为策略必须按座位给 4 个对象，得到 {0}".format(len(policies)))
    return {
        "ok": not problems,
        "verified": not problems,
        "problems": problems,
        "opponent_scenario": opponent_scenario,
        "expected_opponent_names": names,
        "focal_seat": focal_seat,
        # 装配对象身份（逐座位：合同名 + 对象类 + 对象 token）
        "by_seat": rows,
        # 执行记录（逐座位：实际被调用的策略对象/窗口数）——与 by_seat 对账。
        "execution": {"by_seat": [dict(row)
                                  for row in (execution or {}).get("by_seat") or ()]},
        "object_identity_checked": bool(check_object_identity),
    }


def real_window_request(
    *,
    decision: Any,
    analysis: RuleAnalysis,
    match_id: str,
    config: MatchDriverConfig,
    now_monotonic: Callable[[], float],
    stage_situation: Optional[StageSituationProjection] = None,
) -> DecisionRequest:
    """给冻结行为策略组装真实 DecisionRequest（真实策略需要真实请求形状）。"""
    from hangma_bot.kernel.observation import CompetitionContext

    window_key = decision.window_key
    if stage_situation is None:
        competition = CompetitionContext(
            tournament_id=config.competition_tournament_id, stage_no=None,
            stage_role=None, stage_total=None, participant_rank=None,
            ranking=(), observed_at_unix_ms=0,
        )
    else:
        competition = stage_situation.competition_context(
            config.competition_tournament_id, window_key.seat)
    budget = config.budget_policy.build(now_monotonic(), decision.timeout_seconds)
    return DecisionRequest(
        observation=decision.observation,
        competition=competition,
        rules=analysis,
        decision_id="{0}:gen:{1}:{2}:{3}:seat{4}".format(
            match_id, window_key.game_id, window_key.round_no,
            window_key.trigger_seq, window_key.seat),
        trigger_seq=window_key.trigger_seq,
        window_key=window_key,
        rejected_attempts=(),
    )


def _frame_probe_summary(*, frame_index: int, decision: Any, facts: Mapping[str, Any],
                         results: Mapping[str, Any]) -> Dict[str, Any]:
    """一个判定帧的**只读读数摘要**（P9：根见证探针逐条留痕的载荷）。

    只含玩家可见事实派生量：帧号、局号、可摸牌墙余量、分支的进展/路线/支持计数、
    严格分支对的 gap 列表、八谓词三值。不含世界私有字段（T09 红线）。
    """

    branches = list(facts.get("branches") or ())
    pairs: List[Dict[str, Any]] = []
    for b in branches:
        if b.get("route_status") not in _B_ROUTE_STATUSES_FOR_PROBE:
            continue
        b_progress = (b.get("family_progress") or {}).get("branch")
        for c in branches:
            if c.get("action_key") == b.get("action_key"):
                continue
            c_progress = (c.get("family_progress") or {}).get("branch")
            if not _strict_pair_for_probe(b_progress, c_progress):
                continue
            b_shanten = b.get("combined_shanten")
            c_shanten = c.get("combined_shanten")
            pairs.append({
                "b": b.get("action_key"), "c": c.get("action_key"),
                "b_progress": b_progress, "c_progress": c_progress,
                "b_shanten": b_shanten, "c_shanten": c_shanten,
                "gap": (None if b_shanten is None or c_shanten is None
                        else int(b_shanten) - int(c_shanten))})
    return {
        "frame": int(frame_index),
        "round_no": int(decision.window_key.round_no),
        "wall_left": facts.get("wall_left"),
        "branch_progress": sorted({str((b.get("family_progress") or {}).get("branch"))
                                   for b in branches}),
        "support_branch": sorted({b.get("support_remaining", {}).get("branch")
                                  for b in branches},
                                 key=lambda value: (value is None, value)),
        "shanten_states": sorted({str(b.get("shanten_state")) for b in branches}),
        "strict_pairs": len(pairs),
        "gaps": sorted({item["gap"] for item in pairs if item["gap"] is not None}),
        "predicate_values": {str(key): str(value.get("value"))
                             for key, value in results.items()},
    }


def run_real_prefix_attempt(
    *,
    runtime: Mapping[str, Any],
    rules: Any,
    predicate_id: str,
    focal_seat: int,
    attempt_index: int,
    source_root_id: str,
    match_id: str,
    tournament_config: Any,
    seed: int,
    value_limits: Optional[ValueAnalysisLimits] = None,
    behavior_policies_by_seat: Optional[Sequence[Any]] = None,
    opponent_names: Sequence[str] = (),
    opponent_scenario: str = "",
    config: Optional[MatchDriverConfig] = None,
    stage_situation: Optional[StageSituationProjection] = None,
    max_frames: int = 100000,
    frame_sink: Optional[Callable[[Mapping[str, Any]], None]] = None,
    capture_condition: Optional[
        Callable[[DecisionRequest], Optional[Mapping[str, Any]]]
    ] = None,
) -> AttemptOutcome:
    """真实前缀生成尝试（Q1 修复①）：组合根引擎 + 冻结行为策略 + 自然开局。

    - runtime 必须来自 build_real_runtime（组合根 SimulationEngine）或经显式测试
      入口 build_test_runtime_double 装配的替身，且**必须带 runtime_kind 标签**；
      缺失/无标签/夹具引擎一律拒绝（_resolve：fail-closed，不注入替身）；
    - behavior_policies_by_seat + opponent_names + opponent_scenario 必须显式传入
      （M2 修复）：对手行为策略由调用方**从冻结合同装配**，此处只做对象级核对
      （verify_prefix_behavior_binding），缺省不再落回「三家 V2」——否则 M 情景的
      机会前缀会实际由 H 对手生成，标签与采样分布不一致；
    - 世界只经 engine.start/frame/advance 交互；谓词判定与夹具路径同一投影
      （project_predicate_facts + evaluate_predicates），只看焦点座位行动前
      的玩家可见事实；
    - 未命中时整帧按冻结行为策略推进（advance 前经 rules.analyze 合法性
      复核，前缀每步都有合法性见证）；帧数超过 max_frames 按尝试失败计；
    - 执行记录（每座位实际使用的策略对象/窗口数）随 AttemptOutcome 返回，供
      上层把「装配对象」与「执行记录」绑定到根摘要；
    - frame_sink（P9 FAMCOST，可选）：焦点座位每个判定帧回调一次，载荷为
      {frame, round_no, wall_left, predicate_values, strict_pairs, gaps} 的只读
      摘要——供**根见证探针**逐条留痕（"为什么这个根不见证谓词"）。缺省 None
      时行为逐字不变（生产前缀生成不付任何额外开销）。
    - capture_condition（R10 反事实标签，可选）：接收只含玩家观察与规则分析的
      ``DecisionRequest``；返回非空映射即截取该窗口并把映射登记为见证，返回
      ``None`` 继续自然前缀。启用时 ``predicate_id`` 是实验标签，不受八谓词
      枚举限制；缺省路径仍逐字使用冻结八谓词。
    """
    if capture_condition is None and predicate_id not in PREDICATE_IDS:
        raise ValueError("predicate_id 必须是八谓词之一：{0}".format(predicate_id))
    if capture_condition is not None and (
        not isinstance(predicate_id, str) or not predicate_id
    ):
        raise ValueError("自定义截取条件必须携带非空 predicate_id 实验标签")
    runtime = resolve_declared_runtime(runtime, where="run_real_prefix_attempt")
    engine = runtime["engine"]
    spec_factory = runtime["spec_factory"]
    chooser = runtime["choice_factory"]
    driver_config = config or _driver_config()
    if not behavior_policies_by_seat:
        raise RuntimeAssemblyError(
            "run_real_prefix_attempt：必须显式传入 behavior_policies_by_seat"
            "（M2：对手行为策略从冻结合同情景装配；缺省不再落回「三家 V2」"
            "——那会让 M 情景的机会前缀实际由 H 对手生成）")
    if not opponent_names:
        raise RuntimeAssemblyError(
            "run_real_prefix_attempt：必须显式传入 opponent_names（冻结合同情景 "
            "{0!r} 的三家对手策略名），用于核对装配对象与执行记录".format(
                opponent_scenario))
    behavior = tuple(behavior_policies_by_seat)
    preflight = verify_prefix_behavior_binding(
        opponent_scenario=opponent_scenario, expected_opponent_names=opponent_names,
        policies_by_seat=behavior, focal_seat=focal_seat)
    if not preflight["ok"]:
        raise RuntimeAssemblyError(
            "前缀行为策略装配与冻结合同不符（M2 fail-closed，不执行该尝试）：{0}".format(
                "；".join(preflight["problems"])))
    spec = spec_factory(
        match_id=match_id,
        scenario_id=source_root_id,
        config=tournament_config,
        seed=int(seed),
        initial_dealer=0,
        initial_scores=[0, 0, 0, 0],
    )
    world = engine.start(spec)
    prefix: List[Mapping[str, Any]] = []
    seen_unknown = False
    last_values: Dict[str, str] = {}
    last_facts: Optional[Mapping[str, Any]] = None
    frames_seen = 0
    #: 逐座位执行记录（窗口数 + 实际使用的策略对象 token）：M2 的「执行记录」见证。
    executed: Dict[int, Dict[str, Any]] = {}

    def _binding(execution: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
        verdict = verify_prefix_behavior_binding(
            opponent_scenario=opponent_scenario, expected_opponent_names=opponent_names,
            policies_by_seat=behavior, focal_seat=focal_seat, execution=execution,
            check_object_identity=execution is not None)
        verdict["runtime_kind"] = runtime_kind_of(runtime)
        verdict["execution_kind"] = execution_kind_for(
            prefix_source="v2_behavior", runtime=runtime)
        verdict["engine_identity"] = dict(runtime.get("engine_identity") or {})
        verdict["prefix_actions_sha256"] = hashlib.sha256(
            json.dumps([dict(step) for step in prefix], ensure_ascii=False,
                       sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        verdict["source_root_id"] = source_root_id
        return verdict

    while frames_seen < int(max_frames):
        frames_seen += 1
        frame = engine.frame(world)
        if frame.final_scores is not None or frame.blocked_reason is not None:
            break
        focal = [d for d in frame.decisions if d.window_key.seat == focal_seat]
        if focal:
            decision = focal[0]
            analysis = analyze_window(rules, decision.observation, value_limits)
            facts = project_predicate_facts(decision.observation, analysis)
            results = evaluate_predicates(facts)
            last_values = {key: item["value"] for key, item in results.items()}
            last_facts = facts
            if frame_sink is not None:
                frame_sink(_frame_probe_summary(
                    frame_index=frames_seen, decision=decision, facts=facts,
                    results=results))
            custom_witness = None
            if capture_condition is not None:
                custom_request = real_window_request(
                    decision=decision,
                    analysis=analysis,
                    match_id=match_id,
                    config=driver_config,
                    now_monotonic=lambda: 800.0,
                    stage_situation=stage_situation,
                )
                custom_witness = capture_condition(custom_request)
                if custom_witness is not None and not isinstance(custom_witness, Mapping):
                    raise ValueError("capture_condition 必须返回 Mapping 或 None")
            predicate_hit = (
                custom_witness is not None
                if capture_condition is not None
                else results[predicate_id]["value"] == "TRUE"
            )
            if predicate_hit:
                return AttemptOutcome(
                    status="hit",
                    template_id=None,
                    attempt_index=attempt_index,
                    source_root_id=source_root_id,
                    spec_seed=int(seed),
                    prefix=tuple(prefix),
                    cut_frame=frame,
                    cut_decision=decision,
                    predicate_values=last_values,
                    predicate_witness=(
                        dict(custom_witness)
                        if custom_witness is not None
                        else results[predicate_id].get("witness")
                    ),
                    projected_facts=facts,
                    prefix_execution=_binding({"by_seat": list(executed.values())}),
                )
            if capture_condition is None and results[predicate_id]["value"] == "UNKNOWN":
                seen_unknown = True
        choices = []
        for decision in frame.decisions:
            analysis = analyze_window(rules, decision.observation, value_limits)
            request = real_window_request(
                decision=decision, analysis=analysis, match_id=match_id,
                config=driver_config, now_monotonic=lambda: 800.0,
                stage_situation=stage_situation,
            )
            seat = int(decision.window_key.seat)
            seat_policy = behavior[seat]
            row = executed.setdefault(seat, {
                "seat": seat, "policy_id": str(getattr(seat_policy, "policy_id", "") or ""),
                "policy_class": type(seat_policy).__name__,
                "object_token": _object_token(seat_policy), "windows": 0,
            })
            row["windows"] += 1
            try:
                plan = asyncio.run(seat_policy.choose(
                    request, driver_config.budget_policy.build(
                        800.0, decision.timeout_seconds)))
                action = None if not plan.candidates else plan.candidates[0].action
            except Exception as error:  # 行为策略失败：本尝试失败（不保底冒充前缀）
                raise ValueError(
                    "冻结行为策略在窗口 {0} 失败（尝试作废）：{1}: {2}".format(
                        decision.window_key, type(error).__name__, error)
                ) from error
            if action is None:
                raise ValueError("冻结行为策略在窗口 {0} 未给出动作（尝试作废）".format(
                    decision.window_key))
            key = action_key(action)
            if not any(c.action_key == key for c in analysis.legal_candidates):
                raise ValueError(
                    "冻结行为策略动作 {0} 不在窗口合法候选中（尝试作废）".format(key))
            choices.append(chooser(decision.window_key, action))
        world = engine.advance(world, frame.revision, tuple(choices))
        prefix.extend(
            {"window_key": window_key_to_json(choice.window_key),
             "action_key": action_key(choice.action)}
            for choice in choices
        )
    if frames_seen >= int(max_frames):
        raise ValueError("真实前缀尝试超过帧数上限 {0}（尝试作废）".format(max_frames))
    return AttemptOutcome(
        status="unknown" if seen_unknown else "miss",
        template_id=None,
        attempt_index=attempt_index,
        source_root_id=source_root_id,
        prefix=tuple(prefix),
        predicate_values=last_values,
        predicate_witness=None,
        projected_facts=last_facts,
        prefix_execution=_binding({"by_seat": list(executed.values())}),
    )


def build_fixture_full_table_frames(
    *, match_id: str, focal_seat: int, table_no: int,
) -> List[FixtureFrameSpec]:
    """夹具完整桌（剩余桌赛用）：焦点座位一个摸牌窗口 + 终局映射。

    仅 scripted_fixture 路径的剩余桌演示使用（fixture_mode=True）；终局积分由
    焦点座位在该窗口的选择映射（夹具语义，费用账记 fixture_outcome_mapping）。
    """
    window = FixtureWindowSpec(
        game_id=match_id,
        seat=focal_seat,
        phase="draw",
        hand="1w 2w 3w 4w 5w 6w 7w 8w 9w 2t 2t 3t 5b",
        drawn="5b",
        trigger_seq=7 + 10 * int(table_no),
        wall_left=50,
        scores=(0, 0, 0, 0),
    )
    return [
        FixtureFrameSpec(revision=1, windows=(window,), completed_hands=0,
                         outcome_branch={
                             "seat0:hu": (8, -2, -2, -2),
                             "default": (2, 0, -1, -1),
                         }),
        FixtureFrameSpec(revision=2, completed_hands=1, scores_from_outcome=True),
    ]


def generate_opportunity(
    *,
    prefix_source: str,
    rules: Any,
    predicate_id: str,
    focal_seat: int,
    opponent_scenario: str,
    root_label: str,
    match_id: str,
    stage_ledger: Mapping[str, Any],
    remaining_schedule: Mapping[str, Any],
    value_limits: Optional[ValueAnalysisLimits] = None,
    attempts_cap: int = PREFIX_ATTEMPT_CAP,
    template_sequence: Sequence[str] = FIXTURE_TEMPLATE_SEQUENCE,
    authorization_token: Optional[Mapping[str, Any]] = None,
    panel_seed: int = 20260916,
    runtime: Optional[Mapping[str, Any]] = None,
    tournament_config: Any = None,
    behavior_policies_by_seat: Optional[Sequence[Any]] = None,
    opponent_names: Sequence[str] = (),
    tables_in_stage: int = 2,
    rounds_per_game: int = 8,
) -> Tuple[Optional[Mapping[str, Any]], Mapping[str, Any]]:
    """生成一个机会场景快照（§7.2 条 1/2/6）；返回 (快照|None, 尝试计数账)。

    - prefix_source=scripted_fixture：夹具路径（fixture_mode，仅工具测试/
      夹具验收），run_prefix_attempt + ScriptedFixtureEngine；
    - prefix_source=v2_behavior：真实路径（Q1 修复①）——必须携带批次 7 预算
      授权令牌，否则直接拒绝；runtime 缺省经 build_real_runtime 装配组合根
      SimulationEngine（公开 start/frame/advance，**真实引擎，不是替身**），
      替身只能由调用方经显式测试入口 build_test_runtime_double 注入；
      behavior_policies_by_seat/opponent_names 由调用方**从冻结合同装配**
      （M2 修复；缺省即拒绝，不落回「三家 V2」）；行为策略失败/超帧按 errors
      计数作废该尝试（不保底冒充）；装配与合同不符同样 fail-closed（不执行）；
    - 尝试计数按 256 上限（attempts_cap 可在测试中收紧）如实记录：
      total/hit/missed/unknown/errors/attempts_exhausted；
    - 同根只贡献一个样本一个主子场景：首次命中即返回；其他谓词值仅作标签。
    """
    if prefix_source not in PREFIX_SOURCES:
        raise ValueError("prefix_source 必须是 {0} 之一".format(PREFIX_SOURCES))
    if prefix_source == "v2_behavior":
        _require_v2_authorization(authorization_token)
    counters: Dict[str, Any] = {
        "total": 0, "hit": 0, "missed": 0, "unknown": 0, "errors": 0,
        "cap": int(attempts_cap), "attempts_exhausted": False,
        "generator": GENERATOR_V2_BEHAVIOR if prefix_source == "v2_behavior"
        else GENERATOR_SCRIPTED_FIXTURE,
        "attempt_errors": [],  # R6 集成补：逐尝试错误文本（cap 16，可诊断）
    }
    # 运行时种类（A1）：由装配标签决定；缺省路径在此装配的是**真实**运行时。
    if prefix_source == "v2_behavior":
        counters["runtime_kind"] = (runtime_kind_of(runtime)
                                    if runtime is not None else RUNTIME_KIND_REAL)
        counters["engine_kind"] = ENGINE_KIND_BY_RUNTIME_KIND[counters["runtime_kind"]]
        counters["execution_kind"] = EXECUTION_KIND_BY_RUNTIME_KIND[
            counters["runtime_kind"]]
    else:
        counters["runtime_kind"] = RUNTIME_KIND_FIXTURE
        counters["engine_kind"] = ENGINE_KIND_BY_RUNTIME_KIND[RUNTIME_KIND_FIXTURE]
        counters["execution_kind"] = EXECUTION_SCRIPTED_FIXTURE
    # 运行时证据（进快照/费用账；全部来自实际装配对象与执行记录）。
    runtime_evidence: Dict[str, Any] = {
        "runtime_kind": counters["runtime_kind"],
        "engine_kind": counters["engine_kind"],
        "execution_kind": counters["execution_kind"],
        "runtime_source": (
            "ScriptedFixtureEngine（夹具路径，零真实桌赛）"
            if prefix_source != "v2_behavior"
            else (REAL_RUNTIME_SOURCE if runtime is None
                  else str(runtime.get("runtime_entry") or "injected_runtime"))),
        "engine_identity": ({} if prefix_source != "v2_behavior"
                            else dict((runtime or {}).get("engine_identity") or {})),
        "real_tables": counters["runtime_kind"] in SELECTION_ELIGIBLE_RUNTIME_KINDS,
    }
    for attempt_index in range(int(attempts_cap)):
        # A3（R9 修复）：根的**唯一描述符**在两条入口上同源——身份（生成器版本 ×
        # 子场景 × 对手情景 × 实际种子 × 根索引）与执行种子由同五个维度派生。
        # 旧实现这里另写 "{root_label}:{predicate}:rootNNN" 并用 "prefix" 命名空间
        # 单独派生前缀种子，家族登记/补根却用 "family" 命名空间另算一个 → 同名根
        # 不是同一座牌山（复审 A3 反例：6080762621504 != 15025786951857）。
        descriptor = stage.root_descriptor(
            generator=counters["generator"], sub_scenario=predicate_id,
            opponent_mix=opponent_scenario, panel_seed=int(panel_seed),
            root_index=attempt_index)
        source_root_id = str(descriptor["root_id"])
        counters["total"] += 1
        if prefix_source == "v2_behavior":
            effective_runtime = runtime or build_real_runtime(
                rules_config=rules.config,
                rounds_per_game=int(rounds_per_game),
                seed=stage.derive_seed(panel_seed, "opp-real", source_root_id),
                scenario_id=source_root_id,
            )
            # 真实执行种子 = 描述符种子（不再另立派生式）：补根逐字沿用同一个数。
            seed = int(descriptor["root_seed"])
            try:
                attempt = run_real_prefix_attempt(
                    runtime=effective_runtime,
                    rules=rules,
                    predicate_id=predicate_id,
                    focal_seat=focal_seat,
                    attempt_index=attempt_index,
                    source_root_id=source_root_id,
                    match_id=match_id,
                    tournament_config=tournament_config,
                    seed=seed,
                    value_limits=value_limits,
                    behavior_policies_by_seat=behavior_policies_by_seat,
                    opponent_names=opponent_names,
                    opponent_scenario=opponent_scenario,
                )
            except RuntimeAssemblyError:
                # 装配错误 fail-closed：不上报为"尝试失败"（不烧尝试上限、不
                # 用错误文本掩盖"运行时/对手策略没装配对"这一事实）。
                raise
            except ValueError as error:
                # 不静默吞错（R6 集成补）：errors 计数 + 逐尝试文本（cap 16）。
                counters["errors"] += 1
                if len(counters["attempt_errors"]) < 16:
                    counters["attempt_errors"].append({
                        "attempt_index": attempt_index,
                        "source_root_id": source_root_id,
                        "error": str(error),
                    })
                continue
        else:
            template_id = template_sequence[attempt_index % len(template_sequence)]
            attempt = run_prefix_attempt(
                rules=rules,
                template_id=template_id,
                predicate_id=predicate_id,
                focal_seat=focal_seat,
                attempt_index=attempt_index,
                source_root_id=source_root_id,
                match_id=match_id,
                value_limits=value_limits,
            )
        if attempt.status == "hit":
            counters["hit"] += 1
            snapshot = build_snapshot(
                prefix_source=prefix_source,
                attempt=attempt,
                predicate_id=predicate_id,
                focal_seat=focal_seat,
                opponent_scenario=opponent_scenario,
                match_id=match_id,
                stage_ledger=stage_ledger,
                remaining_schedule=remaining_schedule,
                panel_seed=panel_seed,
                tables_in_stage=int(tables_in_stage),
                rounds_per_game=int(rounds_per_game),
                runtime_evidence=runtime_evidence,
                # A3/Q3：根描述符与真实捕获的根见证在**唯一构造点**（build_snapshot）
                # 落进快照——普通（首命中）入口与指定根入口走同一段序列化代码。
                descriptor=descriptor,
                witness_entry="conditional_first_hit_root",
            )
            return snapshot, counters
        if attempt.status == "unknown":
            counters["unknown"] += 1
        else:
            counters["missed"] += 1
    counters["attempts_exhausted"] = True
    return None, counters


# ===========================================================================
# Q6（R9 裁定 2026-09-18）· 统一**受信**授权校验（sitin-authorization/1）
#
# 缺陷：生产在 _step_natural / 补根 / 家族补根三处各写一遍
# "authorized is True and batch == 7"——只认一个历史门值，既不校验"这一批是哪个
# 标签"、也不校验"这次操作是否在允许集内、账户额度是否够"，而且判据散落三处。
#
# 修法（裁定原文：改成统一、受信的授权身份/范围校验；**不能直接去掉授权约束**）：
# 单一入口 av_authorization_check，逐项校验身份（authorization_id）、批次标签
# （batch_label）、受信标记（trusted）、允许操作集（allowed_operations ⊆ 冻结集合：
# **模型无权修改允许标签集**）、账户额度（allowed_accounts ≥ required），任一项
# 不满足即 ok=False（失败关闭，调用方据此拒绝执行，不降级替身/夹具）。
#
# 兼容（裁定明确要求）：原已授权的 batch7 同范围复验可继续——legacy 形态
# （无 sitin-authorization/1 字段，但 authorized=true 且 batch==7）按**同范围**接受，
# 并在运行审计里记 authorization_form=legacy_batch7（见 legacy_removal_condition）。
# ===========================================================================

#: 授权文档 schema（Lead 定义，双方必须一致；字段名照写）。
AUTHORIZATION_SCHEMA = "sitin-authorization/1"
#: 校验结论 schema（进运行审计；字段固定，便于逐项复核）。
AUTHORIZATION_CHECK_SCHEMA = "sitin-authorization-check/1"
#: **冻结**的允许操作集（生产侧唯一定义）：授权文件的 allowed_operations 必须是
#: 本集合的子集；出现集合外的操作即判"允许标签集被改"，失败关闭（不静默忽略）。
AV_AUTHORIZATION_OPERATIONS: Tuple[str, ...] = (
    "natural_panel", "conditional_prefix", "family_fill",
    "conditional_refill", "evaluate", "summarize",
)
#: 冻结的账户集合（与 sitin_search.AV_LEDGER_ACCOUNTS 同口径；授权文档照写）。
AV_AUTHORIZATION_ACCOUNTS: Tuple[str, ...] = (
    "tables_full", "tables_partial", "prefix_generation",
    "tokens_input", "tokens_output", "confirm_reserved",
)
#: 受信签发方（授权文件由 Lead 签发；**不是**模型可写字段）。扩名单需要人工决定。
AV_TRUSTED_ISSUERS: Tuple[str, ...] = ("lead",)
#: legacy 形态的历史门值（batch==7 与 authorized=true）。
AV_LEGACY_BATCH = 7
#: legacy 形态在审计里的批次标签缺省记号（授权文件自带 batch_label 时以文件为准）。
AV_LEGACY_BATCH_LABEL = "batch7"
#: legacy 形态的**移除条件**（写进审计，见裁定"写清移除条件"）。
AV_LEGACY_REMOVAL_CONDITION = (
    "legacy（无 sitin-authorization/1 字段但 authorized=true 且 batch==7）仅在本轮"
    "同范围复验期接受：新批次授权（schema=sitin-authorization/1，含 authorization_id/"
    "batch_label/trusted/allowed_operations/allowed_accounts/issued_by/issued_at_utc）"
    "首次启用后，同一账号与同一产物的下一次运行必须改用新形态；此时 legacy 一律拒绝"
    "（authorization_form_unknown）。移除动作由 Lead 在授权文件里显式改形，不由运行期"
    "自动升级、更不由模型修改允许标签集。"
)


def _av_auth_number(value: Any) -> Optional[float]:
    """授权额度字段 → 非负有限数；bool/非数/NaN/Inf/负数一律 None（不猜、不放宽）。"""

    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    if not math.isfinite(number) or number < 0:
        return None
    return number


def _av_auth_text(value: Any) -> Optional[str]:
    """授权文本字段 → 非空字符串；其它一律 None（缺字段不放行）。"""

    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip()


#: dual 形态的审计记号（同一文档里两种形态都在）。
AV_AUTHORIZATION_FORM_DUAL = "dual_sitin_authorization_1"


def av_authorization_form(authorization: Optional[Mapping[str, Any]]) -> str:
    """授权形态判定：sitin-authorization/1 / dual / legacy_batch7 / absent / invalid。

    - legacy 判据 = **authorized=true 且 batch==7**（与裁定一致）：文档自带别的 schema
      标签（例如历史 gate2 的 sitin-gate2-authorization/1）也**照样按 legacy 接受**，
      并在审计里显式标成 legacy_batch7——不因为多了一个旧标签就把在案的 batch7 授权
      判成"无法识别"而拒绝（那会让原已授权的同范围复验跑不动）。
    - dual = 同一文档里**既有** sitin-authorization/1 字段、又带 authorized=true/batch=7：
      按完整形态校验，并额外核对两条额度表是否一致（冲突即拒绝，见 av_authorization_check）。
    """

    if not isinstance(authorization, Mapping):
        return "absent"
    schema = authorization.get("schema")
    full = schema is not None and str(schema) == AUTHORIZATION_SCHEMA
    legacy = (authorization.get("authorized") is True
              and not isinstance(authorization.get("batch"), bool)
              and authorization.get("batch") == AV_LEGACY_BATCH)
    if full and legacy:
        return AV_AUTHORIZATION_FORM_DUAL
    if full:
        return AUTHORIZATION_SCHEMA
    if legacy:
        return "legacy_batch7"
    return "invalid"


def _av_dual_form_account_conflicts(authorization: Mapping[str, Any]) -> List[Dict[str, Any]]:
    """dual 形态：新形态 allowed_accounts 与 legacy budgets 的**额度冲突**逐项列出。"""

    accounts = authorization.get("allowed_accounts")
    budgets = authorization.get("budgets")
    problems: List[Dict[str, Any]] = []
    if not isinstance(accounts, Mapping) or not isinstance(budgets, Mapping):
        return problems
    for name in sorted(set(str(key) for key in accounts)
                       & set(str(key) for key in budgets)):
        left = _av_auth_number(accounts.get(name))
        right = _av_auth_number(budgets.get(name))
        if left is None or right is None:
            continue
        if abs(left - right) > 1e-9:
            problems.append({"code": "dual_form_account_conflict", "detail": (
                "dual 形态下账户 {0} 的两份额度不一致（allowed_accounts={1} != "
                "budgets={2}）：同一份授权不得有两个口径，拒绝").format(
                    name, left, right)})
    return problems


def _av_auth_verdict(*, form: str, operation: str, problems: Sequence[Mapping[str, Any]],
                     authorization: Mapping[str, Any], allowed_operations: Sequence[str],
                     allowed_accounts: Mapping[str, float],
                     required: Optional[Mapping[str, Any]],
                     accounts_sufficient: Optional[bool]) -> Dict[str, Any]:
    """校验结论（统一形状；ok = 无任何问题项——失败关闭的唯一判据）。"""

    return {
        "schema": AUTHORIZATION_CHECK_SCHEMA,
        "ok": not problems,
        "authorization_form": form,
        "authorization_id": _av_auth_text(authorization.get("authorization_id")),
        "batch_label": _av_auth_text(authorization.get("batch_label")),
        "trusted": (authorization.get("trusted")
                    if form in (AUTHORIZATION_SCHEMA, AV_AUTHORIZATION_FORM_DUAL)
                    else (True if form == "legacy_batch7" else None)),
        "issued_by": _av_auth_text(authorization.get("issued_by")),
        "issued_at_utc": _av_auth_text(authorization.get("issued_at_utc")),
        "operation": str(operation),
        "operation_allowed": str(operation) in set(allowed_operations),
        "allowed_operations": sorted(allowed_operations),
        "allowed_accounts": {name: float(value)
                             for name, value in sorted(allowed_accounts.items())},
        "required": ({str(name): float(value)
                      for name, value in sorted(dict(required or {}).items())}
                     if required is not None else None),
        "accounts_sufficient": accounts_sufficient,
        "problems": [dict(item) for item in problems],
        "legacy_removal_condition": (AV_LEGACY_REMOVAL_CONDITION
                                     if form == "legacy_batch7" else None),
        "frozen_operations": list(AV_AUTHORIZATION_OPERATIONS),
        "checked_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "note": ("统一受信授权校验：身份（authorization_id）/批次标签（batch_label）/"
                 "trusted/允许操作集（模型无权修改）/账户额度逐项核对，任一项不满足"
                 "即失败关闭"),
    }


def av_authorization_check(
    authorization: Optional[Mapping[str, Any]], *,
    operation: str,
    required: Optional[Mapping[str, Any]] = None,
    expected_batch_label: Optional[str] = None,
    expected_authorization_id: Optional[str] = None,
) -> Dict[str, Any]:
    """统一**受信**授权校验（Q6）：操作是否允许、账户额度是否足够、批次标签是否

    匹配、trusted 是否为真；任一不满足返回 ok=False 并逐项给具名原因（失败关闭）。

    参数：
      - operation：本次要执行的操作，必须取自**冻结集合** AV_AUTHORIZATION_OPERATIONS，
        且出现在授权的 allowed_operations 里（模型无权修改允许标签集）；
      - required：本次操作各账户所需额度（如 {"tables_full": 4.0}）；给出即逐项比较
        授权额度（allowed_accounts），不足即拒绝；缺该账户声明同样拒绝（不当作无限额）；
      - expected_batch_label / expected_authorization_id：调用方（冻结计划/运行目录）
        冻结的期望值；给出即必须逐字一致。
    """

    problems: List[Dict[str, Any]] = []
    form = av_authorization_form(authorization)
    authorization = authorization if isinstance(authorization, Mapping) else {}
    if form == "absent":
        problems.append({"code": "authorization_missing", "detail": (
            "缺授权令牌：真实桌赛/前缀生成/评测一律失败关闭（Q6：去掉 batch==7 不等于"
            "去掉授权约束）")})
        return _av_auth_verdict(form=form, operation=operation, problems=problems,
                                authorization=authorization, allowed_operations=(),
                                allowed_accounts={}, required=required,
                                accounts_sufficient=None)
    if form == "invalid":
        problems.append({"code": "authorization_form_unknown", "detail": (
            "授权形态无法识别：schema={0!r}（既不是 {1}，也不是 legacy"
            "（authorized=true 且 batch=={2}））；不按 legacy 放行").format(
                authorization.get("schema"), AUTHORIZATION_SCHEMA, AV_LEGACY_BATCH)})
        return _av_auth_verdict(form=form, operation=operation, problems=problems,
                                authorization=authorization, allowed_operations=(),
                                allowed_accounts={}, required=required,
                                accounts_sufficient=None)
    if str(operation) not in AV_AUTHORIZATION_OPERATIONS:
        problems.append({"code": "operation_not_frozen", "detail": (
            "请求的操作 {0!r} 不在冻结操作集 {1} 内：调用方写错或试图扩权，拒绝").format(
                str(operation), list(AV_AUTHORIZATION_OPERATIONS))})
    if form in (AUTHORIZATION_SCHEMA, AV_AUTHORIZATION_FORM_DUAL):
        if form == AV_AUTHORIZATION_FORM_DUAL:
            # dual：两条额度表必须同口径（P12 已实测"双形态额度冲突"必须拒绝）。
            problems.extend(_av_dual_form_account_conflicts(authorization))
        allowed_operations: List[str] = []
        declared = authorization.get("allowed_operations")
        if not isinstance(declared, (list, tuple)) or not declared:
            problems.append({"code": "allowed_operations_missing", "detail": (
                "授权缺 allowed_operations（非空列表）：未声明允许操作集即拒绝执行")})
        else:
            for item in declared:
                name = _av_auth_text(item)
                if name is None:
                    problems.append({"code": "allowed_operations_invalid",
                                     "detail": "allowed_operations 含非字符串项：拒绝"})
                    continue
                if name not in AV_AUTHORIZATION_OPERATIONS:
                    problems.append({"code": "operation_set_modified", "detail": (
                        "授权声明了冻结操作集外的操作 {0!r}：允许标签集被修改"
                        "（模型无权修改），拒绝该授权").format(name)})
                    continue
                allowed_operations.append(name)
        if authorization.get("trusted") is not True:
            problems.append({"code": "trusted_false", "detail": (
                "trusted 不是 true（得到 {0!r}）：非受信授权，拒绝执行").format(
                    authorization.get("trusted"))})
        if _av_auth_text(authorization.get("authorization_id")) is None:
            problems.append({"code": "authorization_id_missing",
                             "detail": "缺 authorization_id（不透明标识）：身份不可核，拒绝"})
        if _av_auth_text(authorization.get("issued_at_utc")) is None:
            problems.append({"code": "issued_at_missing",
                             "detail": "缺 issued_at_utc（ISO8601）：授权没有签发时间，拒绝"})
        issuer = _av_auth_text(authorization.get("issued_by"))
        if issuer is None:
            problems.append({"code": "issued_by_missing",
                             "detail": "缺 issued_by：无法判定受信签发方，拒绝"})
        elif issuer not in AV_TRUSTED_ISSUERS:
            problems.append({"code": "issuer_untrusted", "detail": (
                "签发方 {0!r} 不在受信名单 {1}：拒绝（扩名单须人工决定，"
                "不由运行期或模型修改）").format(issuer, list(AV_TRUSTED_ISSUERS))})
        if _av_auth_text(authorization.get("batch_label")) is None:
            problems.append({"code": "batch_label_missing", "detail": (
                "缺 batch_label：本批运行标签不可核（不能只用历史门值 batch==7）")})
        accounts = authorization.get("allowed_accounts")
        if not isinstance(accounts, Mapping):
            problems.append({"code": "allowed_accounts_missing", "detail": (
                "缺 allowed_accounts（账户额度表）：未声明额度即拒绝执行")})
            accounts = {}
        else:
            for name in accounts:
                if str(name) not in AV_AUTHORIZATION_ACCOUNTS:
                    problems.append({"code": "account_set_modified", "detail": (
                        "授权声明了冻结账户集外的账户 {0!r}：账户表被修改，拒绝").format(
                            str(name))})
        allowed_accounts: Dict[str, float] = {}
        for name in AV_AUTHORIZATION_ACCOUNTS:
            value = (_av_auth_number(accounts.get(name))
                     if isinstance(accounts, Mapping) else None)
            if value is None:
                # 完整形态按 Lead 的 schema 逐字段落全：少一个账户额度就是授权不完整，
                # 失败关闭（legacy 形态才允许"未声明账户"存在，见下）。
                problems.append({"code": "account_value_invalid", "detail": (
                    "账户 {0} 的额度缺失或非法（须为 >=0 的有限数）：授权不完整，"
                    "不放行").format(name)})
                continue
            allowed_accounts[name] = value
    else:  # legacy_batch7
        allowed_operations = list(AV_AUTHORIZATION_OPERATIONS)
        budgets = authorization.get("budgets")
        budgets = budgets if isinstance(budgets, Mapping) else {}
        allowed_accounts = {}
        # legacy 同范围口径：budgets 表里**已声明**的账户按原值接受；集合外的键忽略
        # （与账本 av_ledger_budgets_from_authorization 同一取舍——不因未知键就拒一个
        # 本来合法的旧令牌）。未声明的账户**不当作无限额**：本次操作需要它时在下文
        # account_not_declared 拒绝（账本同样会拒绝该账户的正数记账）。
        for name in AV_AUTHORIZATION_ACCOUNTS:
            raw = budgets.get(name)
            if name == "confirm_reserved" and raw is None:
                raw = authorization.get("confirm_budget")
            value = _av_auth_number(raw)
            if value is None:
                continue
            allowed_accounts[name] = value
    if str(operation) not in set(allowed_operations):
        problems.append({"code": "operation_not_allowed", "detail": (
            "本次操作 {0!r} 不在授权允许集 {1} 内：拒绝执行该操作").format(
                str(operation), sorted(allowed_operations))})
    effective_label = _av_auth_text(authorization.get("batch_label")) or (
        AV_LEGACY_BATCH_LABEL if form == "legacy_batch7" else None)
    if expected_batch_label is not None and str(expected_batch_label) != str(effective_label):
        problems.append({"code": "batch_label_mismatch", "detail": (
            "批次标签不符（本批冻结 {0!r}，授权 {1!r}）：不同批次的授权不得混用").format(
                str(expected_batch_label), str(effective_label))})
    if (expected_authorization_id is not None
            and str(expected_authorization_id)
            != str(_av_auth_text(authorization.get("authorization_id")))):
        problems.append({"code": "authorization_id_mismatch", "detail": (
            "authorization_id 不符（本批冻结 {0!r}，授权 {1!r}）：拒绝").format(
                str(expected_authorization_id),
                str(_av_auth_text(authorization.get("authorization_id"))))})
    accounts_sufficient: Optional[bool] = None
    if required:
        accounts_sufficient = True
        for name, amount in sorted(dict(required).items()):
            need = _av_auth_number(amount)
            if need is None:
                problems.append({"code": "required_invalid", "detail": (
                    "调用方给出的所需额度非法：账户 {0} 值 {1!r}").format(
                        str(name), amount)})
                accounts_sufficient = False
                continue
            have = allowed_accounts.get(str(name))
            if have is None:
                problems.append({"code": "account_not_declared", "detail": (
                    "所需账户 {0} 未在授权里声明额度：不按无限额处理，拒绝").format(
                        str(name))})
                accounts_sufficient = False
                continue
            if have + 1e-9 < need:
                problems.append({"code": "account_insufficient", "detail": (
                    "账户 {0} 额度不足：授权 {1} < 本次所需 {2}（不超限执行）").format(
                        str(name), have, need)})
                accounts_sufficient = False
    return _av_auth_verdict(form=form, operation=operation, problems=problems,
                            authorization=authorization,
                            allowed_operations=allowed_operations,
                            allowed_accounts=allowed_accounts, required=required,
                            accounts_sufficient=accounts_sufficient)


def av_authorization_stamp(authorization: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    """授权文件 → **盖上形态标签**的副本（原字段一字不改；P2 要求）。

    调用方（授权文件的产出方）把返回值落盘，授权文件因此自带 authorization_form：
    形态不会被事后猜测，legacy 也**显式标注**而不是静默接受。
    """

    payload = dict(authorization) if isinstance(authorization, Mapping) else {}
    form = av_authorization_form(authorization)
    payload["authorization_form"] = form
    payload["authorization_form_note"] = (
        "形态判定见 sitin_opportunities.av_authorization_form："
        "{0} / {1} / legacy_batch7 / absent / invalid".format(
            AUTHORIZATION_SCHEMA, AV_AUTHORIZATION_FORM_DUAL))
    if form == "legacy_batch7":
        payload["legacy_removal_condition"] = AV_LEGACY_REMOVAL_CONDITION
    return payload


def av_authorization_archive_entry(
    authorization: Optional[Mapping[str, Any]], *, operation: str,
    required: Optional[Mapping[str, Any]] = None,
    expected_batch_label: Optional[str] = None,
    expected_authorization_id: Optional[str] = None,
) -> Dict[str, Any]:
    """授权档案条目（authorization-archive.json 用）：形态 + 核对结论 + 额度（P2）。

    P12 的验收器读这些字段：authorization_form / authorization_id / batch_label /
    trusted / allowed_operations / allowed_accounts / problems / ok。
    """

    verdict = av_authorization_check(
        authorization, operation=operation, required=required,
        expected_batch_label=expected_batch_label,
        expected_authorization_id=expected_authorization_id)
    return {
        "schema": "sitin-authorization-archive-entry/1",
        "authorization_form": verdict["authorization_form"],
        "authorization_id": verdict["authorization_id"],
        "batch_label": verdict["batch_label"],
        "trusted": verdict["trusted"], "issued_by": verdict["issued_by"],
        "issued_at_utc": verdict["issued_at_utc"],
        "operation": verdict["operation"],
        "allowed_operations": verdict["allowed_operations"],
        "allowed_accounts": verdict["allowed_accounts"],
        "required": verdict["required"],
        "ok": verdict["ok"], "problems": verdict["problems"],
        "legacy_removal_condition": verdict["legacy_removal_condition"],
        "checked_at_utc": verdict["checked_at_utc"],
    }


def av_authorization_refusal(verdict: Mapping[str, Any]) -> str:
    """校验结论 → 单行具名拒绝原因（写进停因/审计；不改写结论本身）。"""

    codes = "；".join("{0}:{1}".format(item.get("code"), item.get("detail"))
                      for item in (verdict.get("problems") or ()))
    return "authorization_refused[{0}]（form={1}，operation={2}）：{3}".format(
        len(verdict.get("problems") or ()), verdict.get("authorization_form"),
        verdict.get("operation"), codes or "（无问题项）")


def _require_v2_authorization(authorization_token: Optional[Mapping[str, Any]]) -> None:
    """v2_behavior 的预算门：无批次 7 授权令牌直接拒绝（§11 预算红线）。"""
    verdict = av_authorization_check(authorization_token, operation="conditional_prefix")
    if verdict["ok"]:
        return
    raise ValueError(
        "v2_behavior（真实 V2 行为前缀，生成器 {0}）未取得**受信**授权：{1}。"
        "授权形态见 sitin-authorization/1（{2}，字段：authorization_id/batch_label/"
        "trusted/allowed_operations/allowed_accounts/issued_by/issued_at_utc）；"
        "原「批次 7」同范围复验按 legacy 形态继续接受（authorized=true 且 batch=7，"
        "审计记 authorization_form=legacy_batch7）。本包验收请用 --prefix-source "
        "scripted_fixture（生成器 {3}，独立分层报告）或注入公开契约验证替身".format(
            GENERATOR_V2_BEHAVIOR, av_authorization_refusal(verdict),
            V2_AUTHORIZATION_FILENAME, GENERATOR_SCRIPTED_FIXTURE)
    )


# ===========================================================================
# Q3（R9 裁定 2026-09-18）· 真实内容见证 RootWitness
#
# 裁定原文：普通条件入口与指定根入口**共用同一规范序列化**，输出紧凑根见证
# （RootWitness，记录根实际生成内容和截点的审计产物），至少含：根描述符、实际 seed、
# 前缀摘要、截取窗口键、决策前可见观察摘要、内容摘要、序列化版本。必须是**真实捕获
# 内容**；不接受由计划参数重新构造一个非空摘要。完整世界仅供离线内部核验，不得进入
# 模型可见输入。可落生产审计附属文件（优先，便于长期恢复）。
#
# 实现要点：
#   - 唯一构造点 root_witness：**只能**从真实执行结果（AttemptOutcome）捕获，参数化
#     重建（只有计划参数）无法构造出见证（缺截取帧/窗口/前缀即在此拒绝）；
#   - 规范序列化只此一份：两个生产入口（普通首命中入口与指定根入口）都在
#     build_snapshot 里经同一函数落见证，字段与摘要算法逐字相同；
#   - 只放玩家可见事实（观察摘要 = player_observation_summary，覆盖牌河/副露/
#     最近弃牌/规则状态/公开事件等**规则与评分器消费的可见事实**；不含墙真值/
#     他家暗牌/未来事件），完整世界**不进**见证；
#   - 见证里的 requirement_digest（可重算）与 content_digest（真实捕获）分开落字段：
#     root_witness_verdict 据此把"可重算"与"已对拍一致"判成两个结论。
# ===========================================================================

#: 根见证 schema 与序列化版本（同一记号：见证内容口径变化即换版本，旧见证不可混用）。
#: /2（P16-C3）：观察摘要换成**完整规范摘要**（玩家可见事实全字段）——同一份计划参数在
#: 旧口径下算出的摘要与新口径不可混用，因此版本必须换（旧见证一律判为口径不符）。
ROOT_WITNESS_SCHEMA = "sitin-root-witness/2"
#: 见证里**逐项可比**的核心字段（两入口对拍只比这些；entry/时间戳属溯源，不参与对拍）。
ROOT_WITNESS_COMPARABLE_FIELDS: Tuple[str, ...] = (
    "serialization_version", "source_root_id", "root_id", "root_index", "root_seed",
    "generator", "sub_scenario", "opponent_mix", "panel_seed",
    "actual_seed", "prefix_sha256", "prefix_len", "cut_window_key",
    "observation_summary_schema", "observation_summary_sha256",
    "observation_field_digests", "content_digest",
)


def _witness_json(payload: Any) -> str:
    """规范序列化（与 sitin_search.canonical_json 同口径：排序键 + 紧凑分隔符）。"""

    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _witness_digest(payload: Any) -> str:
    return hashlib.sha256(_witness_json(payload).encode("utf-8")).hexdigest()


def _witness_window_key(window_key: Any) -> Dict[str, Any]:
    """截取窗口键（观察窗口唯一键的 JSON 形状；缺字段不猜，落 None）。"""

    return {
        "game_id": getattr(window_key, "game_id", None),
        "round_no": getattr(window_key, "round_no", None),
        "trigger_seq": getattr(window_key, "trigger_seq", None),
        "phase": getattr(getattr(window_key, "phase", None), "value", None),
        "seat": getattr(window_key, "seat", None),
    }


# ===========================================================================
# P16-C3 · **实际玩家观察**的完整、版本化规范摘要（RootWitness 的观察口径）
#
# 缺陷复述（R9 冻结复审 C3）：根见证复用了 offline.evaluate 的**稀疏**帧摘要
# （定位 / 手牌摘要 / 摸牌 / 墙余量 / 分数）。牌河、副露、最近弃牌、规则状态
# （含包头）、公开事件都没有进摘要 —— 只改牌河 1w→9w、只改包头状态，观察摘要与
# 内容摘要都不变，判定仍是 MATCHED。这份见证因此既证明不了"两入口看到同一份
# 玩家可见事实"，也检测不到牌河/规则状态接线的改动。
#
# 修法：为**实际玩家的观察**（截取窗口里焦点座位依法可见的全部事实）建一份
# 规范摘要：
#   - 覆盖规则与评分器实际消费的可见事实：定位、手牌（摘要+张数，保留顺序语义）、
#     摸牌、四家牌河、四家副露、最近弃牌、墙公开余量、四家积分、规则状态
#     （财神/包头/链计数/抓打圈）、已公开事件（含终局公开读数）；
#   - **不加入**他家暗牌（只摘要本人手牌）与未来牌墙（墙只记官方公开余量）；
#   - **版本化**：口径变化即换 schema，旧摘要不与新摘要混用；
#   - 逐字段摘要（player_observation_field_digests）：两入口/两次捕获对拍时按字段名
#     给出"哪个字段不同"的读数，而不是只有一个总摘要相等/不等。
# ===========================================================================

#: 实际玩家观察的规范摘要 schema（版本化：观察口径变化即换版本）。
PLAYER_OBSERVATION_SUMMARY_SCHEMA = "sitin-player-observation/1"
#: 规范摘要的字段清单（逐字段可比；缺任一字段即判"摘要不完整"）。
PLAYER_OBSERVATION_SUMMARY_FIELDS: Tuple[str, ...] = (
    "window", "location", "turn", "my_hand", "drawn_tile", "hand_counts",
    "scores", "discards", "melds", "last_discard", "remaining_tile_count",
    "rule_state", "public_history", "turn_flags", "observation_issues",
)


def _observation_code(tile: Any) -> Any:
    """牌 → 规范码（无牌返回 None，不猜）。"""

    if tile is None:
        return None
    code = getattr(tile, "code", None)
    return code if isinstance(code, str) else str(tile)


def _observation_meld(meld: Any) -> Dict[str, Any]:
    """副露 → 规范形状（种类 / 牌序 / 供牌者；顺序本身是公开事实，不排序）。"""

    return {
        "kind": str(getattr(meld, "kind", "") or ""),
        "tiles": [_observation_code(tile) for tile in (getattr(meld, "tiles", ()) or ())],
        "from_seat": getattr(meld, "from_seat", None),
    }


def _observation_event(event: Any) -> Dict[str, Any]:
    """公开事件 → 规范形状（官方字段原样透传；缺失即 None，不补默认值）。"""

    result = {
        "seq": getattr(event, "seq", None),
        "kind": getattr(event, "kind", None),
        "seat": getattr(event, "seat", None),
        "tiles": [_observation_code(tile) for tile in (getattr(event, "tiles", ()) or ())],
        "detail_kind": getattr(event, "detail_kind", None),
        "catch_play": getattr(event, "catch_play", None),
        "gang_replenish": getattr(event, "gang_replenish", None),
        "response_window": getattr(event, "response_window", None),
        "result_draw": getattr(event, "result_draw", None),
        "result_fan": getattr(event, "result_fan", None),
        "result_details": (None if getattr(event, "result_details", None) is None
                           else [str(item) for item in event.result_details]),
        "result_scores": (None if getattr(event, "result_scores", None) is None
                          else [int(value) for value in event.result_scores]),
        "final_scores": (None if getattr(event, "final_scores", None) is None
                         else [int(value) for value in event.final_scores]),
        "claimed_tile": _observation_code(getattr(event, "claimed_tile", None)),
    }
    return result


def player_observation_summary(observation: Any, *,
                               window_key: Any = None) -> Dict[str, Any]:
    """**实际玩家观察**的完整规范摘要（P16-C3；只含玩家依法可见事实）。

    输入是一个座位在自己动作窗口里的观察对象（PlayerObservation），可选窗口键
    （WindowKey）——窗口键进摘要，两入口对拍时"是不是同一个窗口"同样可核。

    信息权限：只摘要**本人**手牌（且只落摘要+张数，不落牌值清单），他家手牌在本
    类型上不存在；墙只记官方公开余量（不记物理顺序/未来牌）；公开事件只记已经收到
    的那部分。摘要键名与 FORBIDDEN_SNAPSHOT_KEYS 无交集。
    """

    if observation is None:
        raise ValueError("规范观察摘要必须来自一个真实观察对象（None 不接受）")
    my_hand = tuple(getattr(observation, "my_hand", ()) or ())
    hand_codes = [_observation_code(tile) for tile in my_hand]
    discards = [[_observation_code(tile) for tile in (river or ())]
                for river in (getattr(observation, "discards", ()) or ())]
    melds = [[_observation_meld(meld) for meld in (row or ())]
             for row in (getattr(observation, "melds", ()) or ())]
    last = getattr(observation, "last_discard", None)
    rule_state = getattr(observation, "rule_state", None)
    window = (None if window_key is None else {
        "game_id": getattr(window_key, "game_id", None),
        "round_no": getattr(window_key, "round_no", None),
        "trigger_seq": getattr(window_key, "trigger_seq", None),
        "phase": getattr(getattr(window_key, "phase", None), "value", None),
        "seat": getattr(window_key, "seat", None),
    })
    return {
        "schema": PLAYER_OBSERVATION_SUMMARY_SCHEMA,
        "window": window,
        "location": {
            "game_id": getattr(observation, "game_id", None),
            "seat": getattr(observation, "seat", None),
            "round_no": getattr(observation, "round_no", None),
            "snapshot_seq": getattr(observation, "snapshot_seq", None),
            "consumed_seq": getattr(observation, "consumed_seq", None),
            "phase": getattr(observation, "phase", None),
        },
        "turn": {
            "dealer_seat": getattr(observation, "dealer_seat", None),
            "turn_seat": getattr(observation, "turn_seat", None),
            # 键名用 responding（不是 responding_seats）：面板隐藏信息红线按**键名**
            # 递归核对，"seats" 是 WorldState 私有字段名之一。
            "responding": [int(seat) for seat in
                           (getattr(observation, "responding_seats", ()) or ())],
        },
        "my_hand": {
            "digest": _witness_digest(hand_codes),
            "count": len(hand_codes),
        },
        "drawn_tile": _observation_code(getattr(observation, "drawn_tile", None)),
        "hand_counts": [int(value) for value in
                        (getattr(observation, "hand_counts", ()) or ())],
        "scores": [int(value) for value in (getattr(observation, "scores", ()) or ())],
        "discards": discards,
        "melds": melds,
        "last_discard": (None if last is None else {
            "seat": getattr(last, "seat", None),
            "tile": _observation_code(getattr(last, "tile", None)),
            "seq": getattr(last, "seq", None),
        }),
        "remaining_tile_count": getattr(observation, "remaining_tile_count", None),
        "rule_state": (None if rule_state is None else {
            "wealth_god": _observation_code(getattr(rule_state, "wealth_god", None)),
            "baotou": getattr(rule_state, "baotou", None),
            "chain_count": getattr(rule_state, "chain_count", None),
            "catch_play": getattr(rule_state, "catch_play", None),
            "catch_play_owner_seat": getattr(rule_state, "catch_play_owner_seat", None),
        }),
        "public_history": [_observation_event(event) for event in
                           (getattr(observation, "public_history", ()) or ())],
        "turn_flags": {
            "chain_piao": getattr(observation, "chain_piao", None),
            "gang_draw": getattr(observation, "gang_draw", None),
            "history_complete": getattr(observation, "history_complete", None),
        },
        "observation_issues": [str(item) for item in
                               (getattr(observation, "observation_issues", ()) or ())],
    }


def player_observation_field_digests(summary: Mapping[str, Any]) -> Dict[str, str]:
    """规范摘要的**逐字段**摘要（对拍读数用：哪一类可见事实变了，逐字段具名）。"""

    payload = dict(summary or {})
    out: Dict[str, str] = {}
    for field in PLAYER_OBSERVATION_SUMMARY_FIELDS:
        out[field] = _witness_digest(payload.get(field))
    return out


def player_observation_summary_problems(summary: Any) -> List[str]:
    """规范摘要自洽性核对：schema 版本 + 字段齐备（缺即具名，不静默补）。"""

    problems: List[str] = []
    if not isinstance(summary, Mapping):
        return ["观察摘要不是映射：不接受"]
    if str(summary.get("schema")) != PLAYER_OBSERVATION_SUMMARY_SCHEMA:
        problems.append("观察摘要 schema 不是 {0}（{1!r}）：旧/异口径摘要不混用".format(
            PLAYER_OBSERVATION_SUMMARY_SCHEMA, summary.get("schema")))
    missing = [field for field in PLAYER_OBSERVATION_SUMMARY_FIELDS
               if field not in summary]
    if missing:
        problems.append("观察摘要缺字段 {0}：不完整，判未对拍".format(sorted(missing)))
    return problems


def root_witness_content_digest(*, source_root_id: Any, actual_seed: Any,
                                prefix_sha256: Any, prefix_len: Any,
                                cut_window_key: Any,
                                observation_summary_sha256: Any) -> str:
    """内容摘要（**只吃真实捕获的内容**）：由截取现场的五项物化量算出。

    这里刻意不吃计划参数：同一份计划参数（哪怕逐字相同）在没跑过的情况下也算不出
    与现场一致的内容摘要——"可重算"与"已对拍一致"因此是两个结论。
    """

    return _witness_digest({
        "schema": ROOT_WITNESS_SCHEMA,
        "kind": "content",
        "source_root_id": source_root_id,
        "actual_seed": actual_seed,
        "prefix_sha256": prefix_sha256,
        "prefix_len": prefix_len,
        "cut_window_key": dict(cut_window_key or {}),
        "observation_summary_sha256": observation_summary_sha256,
    })


def root_witness(*, attempt: AttemptOutcome, prefix_source: str, predicate_id: str,
                 focal_seat: int, opponent_scenario: str, descriptor: Mapping[str, Any],
                 match_id: Optional[str] = None, panel_seed: Optional[int] = None,
                 requirement_digest: Optional[str] = None, entry: str = "",
                 runtime_kind: Optional[str] = None,
                 execution_kind: Optional[str] = None) -> Dict[str, Any]:
    """从**真实执行结果**捕获紧凑根见证（Q3）：普通入口与指定根入口共用本函数。

    失败关闭：不是 AttemptOutcome、或该尝试没有真实截取（status != hit 或缺截取帧/
    窗口）时直接拒绝——见证必须来自现场内容，不接受由计划参数重新构造的摘要。
    """

    if not isinstance(attempt, AttemptOutcome):
        raise TypeError(
            "根见证只能从真实执行结果（AttemptOutcome）捕获：不接受由计划参数重建的"
            "摘要（Q3：只按计划参数重算必须判为未对拍）")
    if str(attempt.status) != "hit" or attempt.cut_decision is None \
            or attempt.cut_frame is None:
        raise ValueError(
            "根见证要求已完成截取的尝试（status=hit 且有截取帧/窗口）：未截取的尝试"
            "没有可核内容（状态 {0!r}）".format(attempt.status))
    descriptor = dict(descriptor or {})
    if not descriptor.get("root_id"):
        raise ValueError("根见证必须带根描述符（root_id 等）：没有描述符即无从核对"
                         "跑的是哪个根")
    prefix = [dict(step) for step in (attempt.prefix or ())]
    prefix_sha256 = _witness_digest(prefix)
    window_key = _witness_window_key(attempt.cut_decision.window_key)
    # P16-C3：观察摘要换成**实际玩家观察的完整规范摘要**（牌河/副露/最近弃牌/
    # 规则状态/公开事件等决定动作的可见事实全部进摘要），并同时落**逐字段摘要**
    # 供两入口逐字段对拍。见证只落摘要与摘要值，不落观察全文（观察本体在快照里）。
    observation = player_observation_summary(
        attempt.cut_decision.observation,
        window_key=attempt.cut_decision.window_key)
    observation_sha256 = _witness_digest(dict(observation))
    observation_fields = player_observation_field_digests(observation)
    actual_seed = int(attempt.spec_seed)
    descriptor_root_seed = descriptor.get("root_seed")
    content_digest = root_witness_content_digest(
        source_root_id=attempt.source_root_id, actual_seed=actual_seed,
        prefix_sha256=prefix_sha256, prefix_len=len(prefix),
        cut_window_key=window_key, observation_summary_sha256=observation_sha256)
    return {
        "schema": ROOT_WITNESS_SCHEMA,
        "serialization_version": ROOT_WITNESS_SCHEMA,
        "root_descriptor": {key: descriptor.get(key) for key in (
            "root_id", "root_index", "root_seed", "generator", "sub_scenario",
            "opponent_mix", "panel_seed", "root_identity_schema", "seed_derivation")},
        "root_id": descriptor.get("root_id"),
        "root_index": descriptor.get("root_index"),
        "root_seed": (int(descriptor_root_seed)
                      if isinstance(descriptor_root_seed, int) else None),
        "generator": descriptor.get("generator"),
        "sub_scenario": descriptor.get("sub_scenario") or str(predicate_id),
        "opponent_mix": descriptor.get("opponent_mix") or str(opponent_scenario),
        "panel_seed": (descriptor.get("panel_seed") if descriptor.get("panel_seed")
                       is not None else panel_seed),
        "prefix_source": str(prefix_source),
        "predicate": str(predicate_id),
        "focal_seat": int(focal_seat),
        "match_id": match_id,
        "source_root_id": attempt.source_root_id,
        "actual_seed": actual_seed,
        "seed_matches_descriptor": bool(
            isinstance(descriptor_root_seed, int)
            and int(descriptor_root_seed) == actual_seed),
        "prefix_sha256": prefix_sha256,
        "prefix_len": len(prefix),
        "cut_window_key": window_key,
        "observation_summary_schema": observation.get("schema"),
        "observation_summary_sha256": observation_sha256,
        "observation_summary_fields": sorted(str(key) for key in observation),
        # 逐字段摘要：对拍时按字段名给出"哪一类可见事实不同"的读数（P16-C3）。
        "observation_field_digests": dict(observation_fields),
        "content_digest": content_digest,
        # 可重算的那一半（由冻结计划参数算出）与真实捕获的那一半分开落字段。
        "requirement_digest": requirement_digest,
        "capture": {
            "source": "attempt_outcome",
            "entry": str(entry or ""),
            "captured": True,
            "attempt_status": str(attempt.status),
            "attempt_index": int(attempt.attempt_index),
            "runtime_kind": runtime_kind,
            "execution_kind": execution_kind,
            "at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        },
        "note": ("真实捕获的根见证：截取自实际执行的截取帧/窗口/合法动作前缀与**完整"
                 "规范观察摘要**（只含玩家可见事实：定位/手牌摘要/摸牌/四家牌河/四家副露/"
                 "最近弃牌/墙公开余量/积分/规则状态/公开事件）；完整世界不进本产物。"
                 "requirement_digest 由冻结计划参数可重算，content_digest 只能来自现场内容"),
    }


def root_witness_comparison(witness: Mapping[str, Any]) -> Dict[str, Any]:
    """见证的**逐项可比核心**（两入口对拍用；溯源字段 entry/时间戳不参与比较）。"""

    payload = dict(witness or {})
    out: Dict[str, Any] = {}
    for field in ROOT_WITNESS_COMPARABLE_FIELDS:
        value = payload.get(field)
        out[field] = dict(value) if isinstance(value, Mapping) else value
    return out


#: 见证判定 schema（P16-C3：分列读数 + 明确总体验证状态，不用一个"一致"糊过去）。
ROOT_WITNESS_VERDICT_SCHEMA = "sitin-root-witness-verdict/2"
#: 总体验证状态（封闭集合；调用方据此判定"这一份见证能不能当根验证通过"）。
#:   - VERIFIED：现场捕获 + 内部绑定成立 + （给了要求就要求通过）+（给了对拍对象就对拍通过）；
#:   - CONTENT_ONLY_SOFT_BINDING：内容对拍成立，但绑定只有**具名软条件**（如夹具路径的
#:     实际种子是尝试序号）——只能当夹具自洽证据，不得当真实根等价证据；
#:   - REJECTED：任一硬缺口（未捕获 / 不自洽 / 绑定错 / 对拍对象未捕获 / 逐项不一致 /
#:     要求摘要不符）——调用方必须拒绝，不得只读 content 轴的 MATCHED。
ROOT_WITNESS_OVERALL_VERIFIED = "VERIFIED"
ROOT_WITNESS_OVERALL_CONTENT_ONLY = "CONTENT_ONLY_SOFT_BINDING"
ROOT_WITNESS_OVERALL_REJECTED = "REJECTED"


def _root_witness_observation_readings(payload: Mapping[str, Any], *,
                                       observation_summary: Any = None
                                       ) -> Dict[str, Any]:
    """观察摘要口径读数：schema 版本 + 逐字段摘要齐备 + （给了摘要本体就逐字段重算）。"""

    problems: List[str] = []
    checked = False
    summary = observation_summary
    if str(payload.get("observation_summary_schema") or "") != \
            PLAYER_OBSERVATION_SUMMARY_SCHEMA:
        problems.append(
            "见证的观察摘要口径不是 {0}（{1!r}）：旧/异口径摘要不参与内容对拍".format(
                PLAYER_OBSERVATION_SUMMARY_SCHEMA, payload.get("observation_summary_schema")))
    digests = payload.get("observation_field_digests")
    if not isinstance(digests, Mapping):
        problems.append("见证缺逐字段观察摘要（observation_field_digests）："
                        "无法证明关键可见事实被覆盖")
    else:
        absent = [field for field in PLAYER_OBSERVATION_SUMMARY_FIELDS
                  if not digests.get(field)]
        if absent:
            problems.append("逐字段观察摘要缺字段 {0}：摘要不完整".format(sorted(absent)))
    if summary is None:
        # 见证是紧凑审计产物（不带观察全文）：这里只能核口径与逐字段摘要形状；
        # 调用方拿到产物里的规范摘要本体时（observation_summary=...）应传入重算。
        return {"problems": problems, "checked_against_body": False}
    problems.extend(player_observation_summary_problems(summary))
    if not problems:
        if str(payload.get("observation_summary_sha256") or "") != \
                _witness_digest(dict(summary)):
            problems.append("见证的观察摘要总摘要与产物里的规范摘要不一致：不是同一份观察")
        elif dict(digests) != player_observation_field_digests(summary):
            problems.append("见证的逐字段观察摘要与产物里的规范摘要不一致："
                            "关键可见事实至少有一类不同")
        else:
            checked = True
    return {"problems": problems, "checked_against_body": bool(checked)}


def _root_witness_capture_state(payload: Mapping[str, Any], *,
                                  observation_summary: Any = None
                                  ) -> Dict[str, Any]:
    """一份见证的**现场捕获状态**（捕获物 + 六项捕获字段 + 内容摘要自洽 + 观察摘要口径）。

    captured=False 即"没有可核内容"：由计划参数重算出来的东西、被改写的摘要、
    旧口径（缺完整观察摘要）的见证都在此判 False（不给 MATCHED 的机会）。
    """

    problems: List[str] = []
    captured_fields = ("source_root_id", "actual_seed", "prefix_sha256", "prefix_len",
                       "cut_window_key", "observation_summary_sha256")
    capture = payload.get("capture")
    capture_ok = (isinstance(capture, Mapping)
                  and str(capture.get("source")) == "attempt_outcome")
    missing = [name for name in captured_fields if payload.get(name) in (None, "")]
    consistent = False
    if capture_ok and not missing:
        recomputed = root_witness_content_digest(
            source_root_id=payload.get("source_root_id"),
            actual_seed=payload.get("actual_seed"),
            prefix_sha256=payload.get("prefix_sha256"),
            prefix_len=payload.get("prefix_len"),
            cut_window_key=payload.get("cut_window_key"),
            observation_summary_sha256=payload.get("observation_summary_sha256"))
        consistent = str(recomputed) == str(payload.get("content_digest") or "")
    if not capture_ok:
        problems.append("见证没有现场捕获物（capture.source != attempt_outcome）："
                        "只有可重算参数，不能充当真实内容见证")
    if missing:
        problems.append("见证缺捕获字段 {0}：无法对拍".format(sorted(missing)))
    if capture_ok and not missing and not consistent:
        problems.append("见证的内容摘要与捕获物不自洽（被改写或伪造）")
    observation_readings = _root_witness_observation_readings(
        payload, observation_summary=observation_summary)
    problems.extend(observation_readings["problems"])
    return {
        "captured": bool(capture_ok and not missing and consistent
                         and not observation_readings["problems"]),
        "capture_ok": bool(capture_ok), "missing": missing, "consistent": bool(consistent),
        "observation": observation_readings, "problems": problems,
    }


def _root_witness_binding_readings(payload: Mapping[str, Any], *,
                                   observation_summary: Any = None
                                   ) -> Dict[str, Any]:
    """见证的**内部绑定**读数：根 / 种子 / 窗口 / 观察四者的接线是否自洽。

    硬缺口（hard_problems）即拒绝：来源根标识与描述符不一致、真实路由的实际执行
    种子与描述符不符、截取窗口座位与焦点座位不符、观察本体给的窗口与截取窗口不符、
    观察摘要口径/逐字段摘要不完整。
    软缺口（soft_problems）**具名**保留：夹具路径的实际执行种子按设计是尝试序号
    （run_prefix_attempt 的 spec_seed=attempt_index），与描述符种子本就不同——这类
    见证只能当夹具自洽证据，不能当"同一座牌山"的真实等价证据（seed_matches_descriptor
    为 False 时前置分支必须显式具名，缺 prefix_source 一律按硬缺口处理）。
    """

    hard: List[str] = []
    soft: List[str] = []
    descriptor = payload.get("root_descriptor")
    descriptor = dict(descriptor) if isinstance(descriptor, Mapping) else {}
    source_root_id = str(payload.get("source_root_id") or "")
    descriptor_root_id = str(descriptor.get("root_id") or "")
    root_id_matches = bool(source_root_id) and bool(descriptor_root_id) and \
        source_root_id == descriptor_root_id
    if not root_id_matches:
        hard.append("来源根标识与根描述符不一致（{0!r} != {1!r}）：见证绑在别的根上".format(
            source_root_id, descriptor_root_id))
    declared_seed = descriptor.get("root_seed")
    declared_seed = (int(declared_seed) if isinstance(declared_seed, int)
                     and not isinstance(declared_seed, bool) else None)
    actual_seed = payload.get("actual_seed")
    actual_seed = (int(actual_seed) if isinstance(actual_seed, int)
                   and not isinstance(actual_seed, bool) else None)
    seed_matches = (declared_seed is not None and actual_seed is not None
                    and declared_seed == actual_seed)
    prefix_source = str(payload.get("prefix_source") or "")
    if declared_seed is None or actual_seed is None:
        hard.append("见证缺实际执行种子或描述符种子（实际 {0!r} / 描述符 {1!r}）："
                    "无法证明跑的是同一个根".format(actual_seed, declared_seed))
    elif not seed_matches:
        if prefix_source == "scripted_fixture":
            soft.append("夹具路径的实际执行种子（{0}）与描述符种子（{1}）不同："
                        "按 run_prefix_attempt 的既有口径（spec_seed=attempt_index）"
                        "接受，但只能作夹具自洽证据".format(actual_seed, declared_seed))
        else:
            hard.append("实际执行种子与根描述符不一致（实际 {0} != 描述符 {1}，"
                        "prefix_source={2!r}）：同一根不等价，拒绝".format(
                            actual_seed, declared_seed, prefix_source))
    window = payload.get("cut_window_key")
    window = dict(window) if isinstance(window, Mapping) else {}
    focal_seat = payload.get("focal_seat")
    window_seat = window.get("seat")
    seat_ok = (focal_seat is not None and window_seat is not None
               and int(focal_seat) == int(window_seat))
    if not seat_ok:
        hard.append("截取窗口座位与见证焦点座位不一致（窗口 {0!r} != 焦点 {1!r}）："
                    "窗口不是该座位的动作窗口".format(window_seat, focal_seat))
    # 观察摘要口径缺口单独一列（它与"根/种子/窗口"绑定是两类事，分列后不重复报）。
    observation_readings = _root_witness_observation_readings(
        payload, observation_summary=observation_summary)
    window_binding: Optional[bool] = None
    if isinstance(observation_summary, Mapping):
        # 观察本体 ↔ 窗口绑定：同一窗口的同一座位才是"这份观察"的出处。
        summary_window = observation_summary.get("window")
        summary_window = (dict(summary_window)
                          if isinstance(summary_window, Mapping) else {})
        summary_location = observation_summary.get("location")
        summary_location = (dict(summary_location)
                            if isinstance(summary_location, Mapping) else {})
        window_binding = bool(window) and summary_window == window and \
            summary_location.get("game_id") == window.get("game_id") and \
            summary_location.get("round_no") == window.get("round_no") and \
            summary_location.get("seat") == window.get("seat")
        if not window_binding:
            hard.append("规范观察摘要的窗口/定位与见证截取窗口不一致："
                        "观察不是这个窗口这一座位的")
    return {
        "root_id_matches_source": bool(root_id_matches),
        "seed_matches_descriptor": (None if (declared_seed is None and actual_seed is None)
                                    else bool(seed_matches)),
        "seed_binding_basis": ("descriptor_seed_equality" if seed_matches
                               else "scripted_fixture_attempt_index"
                               if prefix_source == "scripted_fixture" else "mismatch"),
        "window_seat_matches_focal": bool(seat_ok),
        "observation_summary_checked_against_body":
            bool(observation_readings["checked_against_body"]),
        "window_bound_to_observation": window_binding,
        "hard_problems": hard, "soft_problems": soft,
        "observation_problems": list(observation_readings["problems"]),
    }


def root_witness_field_readings(witness: Optional[Mapping[str, Any]], *,
                                expected: Optional[Mapping[str, Any]] = None
                                ) -> Dict[str, Any]:
    """两入口见证的**逐字段**对拍读数（P16-C3）：哪个核心字段不同，逐条具名。"""

    left = root_witness_comparison(witness)
    right = root_witness_comparison(expected or {})
    fields: Dict[str, Any] = {}
    for field in ROOT_WITNESS_COMPARABLE_FIELDS:
        fields[field] = {"left": left.get(field), "right": right.get(field),
                         "match": left.get(field) == right.get(field)}
    # 观察类的**逐字段**读数：observation_field_digests 里哪一个可见事实不同，
    # 单独具名（"牌河变了"与"整份观察变了"是两回事，读数要能分开）。
    observation_fields: Dict[str, Any] = {}
    left_digests = left.get("observation_field_digests")
    right_digests = right.get("observation_field_digests")
    if isinstance(left_digests, Mapping) or isinstance(right_digests, Mapping):
        left_digests = left_digests if isinstance(left_digests, Mapping) else {}
        right_digests = right_digests if isinstance(right_digests, Mapping) else {}
        for name in sorted(set(left_digests) | set(right_digests)):
            observation_fields[name] = {
                "left": left_digests.get(name), "right": right_digests.get(name),
                "match": left_digests.get(name) == right_digests.get(name)}
    mismatched = sorted(name for name, item in fields.items() if not item["match"])
    mismatched.extend("observation_field_digests.{0}".format(name)
                      for name, item in sorted(observation_fields.items())
                      if not item["match"])
    return {
        "schema": "sitin-root-witness-field-readings/1",
        "matched": not mismatched,
        "mismatched_fields": mismatched,
        "fields": fields,
        "observation_fields": observation_fields,
    }


def root_witness_verdict(witness: Optional[Mapping[str, Any]], *,
                         requirement: Optional[str] = None,
                         expected: Optional[Mapping[str, Any]] = None,
                         observation_summary: Any = None) -> Dict[str, Any]:
    """见证判定：把"可重算""已对拍一致""绑定成立"分成**分列读数**（Q3/P16-C3）。

    返回（机器可判，不用散文）：
      - content_captured：见证确实带现场捕获物（capture.source=attempt_outcome、
        六项捕获字段齐备、内容摘要与捕获物自洽、观察摘要口径与逐字段摘要齐备）；
      - requirement_recomputable：给出 requirement（按冻结计划参数重算的摘要）时，
        见证里的 requirement_digest 是否逐字一致；未给则 None（未核）；
      - requirement_passed：要求摘要一致**且**内部绑定成立（未给 requirement 则 None）；
      - content_matched：给出 expected（另一个真实入口的见证）时，逐项可比核心是否
        完全一致；未给则 None（未核）；expected 自身未捕获 ⇒ 直接拒绝（不给 MATCHED）；
      - binding：根标识 / 实际种子 / 窗口座位 / 观察摘要的逐项绑定读数（硬缺口即拒绝，
        软条件具名保留）；
      - overall_status：VERIFIED / CONTENT_ONLY_SOFT_BINDING / REJECTED；
      - status（内容轴）：MATCHED / NOT_CAPTURED / INCONSISTENT / MISMATCH /
        UNVERIFIED / EXPECTED_NOT_CAPTURED。
    """

    problems: List[str] = []
    hard_problems: List[str] = []
    payload = dict(witness or {})
    capture_state = _root_witness_capture_state(payload,
                                               observation_summary=observation_summary)
    hard_problems.extend(capture_state["problems"])
    binding = _root_witness_binding_readings(payload,
                                            observation_summary=observation_summary)
    hard_problems.extend(binding["hard_problems"])
    hard_problems.extend(binding["observation_problems"])
    problems.extend(hard_problems)
    problems.extend(binding["soft_problems"])
    requirement_recomputable: Optional[bool] = None
    requirement_passed: Optional[bool] = None
    if requirement is not None:
        requirement_recomputable = (payload.get("requirement_digest") is not None
                                    and str(payload.get("requirement_digest"))
                                    == str(requirement))
        if not requirement_recomputable:
            hard_problems.append("根要求摘要（由冻结计划参数重算）与见证不一致："
                                 "参数不是同一个根")
            problems.append(hard_problems[-1])
    content_matched: Optional[bool] = None
    counterpart_captured: Optional[bool] = None
    mismatched_fields: List[str] = []
    if expected is not None:
        counterpart = _root_witness_capture_state(expected)
        counterpart_captured = bool(counterpart["captured"])
        if not counterpart_captured:
            hard_problems.append("对拍对象（expected）自身没有现场捕获物："
                                 "未捕获的对拍对象不得给出 MATCHED（{0}）".format(
                                     "；".join(counterpart["problems"])))
            problems.append(hard_problems[-1])
        readings = root_witness_field_readings(payload, expected=expected)
        content_matched = bool(readings["matched"]) and counterpart_captured
        mismatched_fields = list(readings["mismatched_fields"])
        if mismatched_fields:
            hard_problems.append("两个入口的见证逐项对拍不一致：{0}".format(
                {field: [root_witness_comparison(payload).get(field),
                         root_witness_comparison(expected).get(field)]
                 for field in mismatched_fields}))
            problems.append(hard_problems[-1])
    if requirement is not None and requirement_recomputable:
        requirement_passed = bool(requirement_recomputable
                                  and not binding["hard_problems"])
    if not capture_state["capture_ok"] or capture_state["missing"]:
        status = "NOT_CAPTURED"
    elif not capture_state["consistent"]:
        status = "INCONSISTENT"
    elif counterpart_captured is False:
        status = "EXPECTED_NOT_CAPTURED"
    elif mismatched_fields:
        status = "MISMATCH"
    elif content_matched is True:
        status = "MATCHED"
    else:
        status = "UNVERIFIED"
    if status in ("MATCHED", "UNVERIFIED") and (
            binding["hard_problems"] or binding["observation_problems"]):
        # 内容轴没问题但内部绑定有硬缺口：内容轴单独看会误导，另给具名状态。
        status = "BINDING_MISMATCH"
    if hard_problems:
        overall = ROOT_WITNESS_OVERALL_REJECTED
    elif binding["soft_problems"]:
        overall = ROOT_WITNESS_OVERALL_CONTENT_ONLY
    else:
        overall = ROOT_WITNESS_OVERALL_VERIFIED
    return {
        "schema": ROOT_WITNESS_VERDICT_SCHEMA,
        "status": status,
        "overall_status": overall,
        "content_captured": bool(capture_state["captured"]),
        "requirement_recomputable": requirement_recomputable,
        "requirement_passed": requirement_passed,
        "content_matched": content_matched,
        "counterpart_captured": counterpart_captured,
        "binding_ok": (not binding["hard_problems"]
                       and not binding["observation_problems"]),
        "binding": binding,
        "mismatched_fields": mismatched_fields,
        "problems": problems,
        "comparable": root_witness_comparison(payload),
        "note": ("分列读数：content_captured 只认现场捕获物；content_matched 只在**双方都"
                 "已捕获**时给出；requirement_passed = 要求摘要一致且内部绑定成立；"
                 "binding 逐项报根/种子/窗口/观察绑定；overall_status 才是总体验证状态"
                 "（REJECTED 一律不得当根验证通过）"),
    }


def build_snapshot(
    *,
    prefix_source: str,
    attempt: AttemptOutcome,
    predicate_id: str,
    focal_seat: int,
    opponent_scenario: str,
    match_id: str,
    stage_ledger: Mapping[str, Any],
    remaining_schedule: Mapping[str, Any],
    panel_seed: int,
    tables_in_stage: int = 2,
    rounds_per_game: int = 8,
    runtime_source: str = "bootstrap.build_evaluation_runtime(matches)",
    runtime_evidence: Optional[Mapping[str, Any]] = None,
    descriptor: Optional[Mapping[str, Any]] = None,
    requirement_digest: Optional[str] = None,
    witness_entry: str = "",
) -> Mapping[str, Any]:
    """截取窗口快照（§7.2 条 3）：阶段累计账、MatchSpec 等价信息、截取窗口、
    观察摘要与合法动作前缀；只含玩家可见事实（T09 红线）。

    阶段累计账 = 已完成桌赛积分（stage_ledger 声明）+ 当前桌已发生积分（取
    截取帧观察的公开四家积分，不读世界私有状态）。真实快照（v2_behavior）
    另记 engine_kind/stage_plan/runtime_source 作为前缀可重建见证的身份。

    Q3（R9 裁定）：descriptor 给出时，本函数在**同一处**为两个生产入口落
    RootWitness（root_witness，真实捕获；见本模块 Q3 节），并把描述符写进快照。
    见证只含玩家可见事实，完整世界不进见证产物。
    """
    cut = attempt.cut_decision
    frame = attempt.cut_frame
    fixture_mode = prefix_source == "scripted_fixture"
    generator = GENERATOR_V2_BEHAVIOR if prefix_source == "v2_behavior" else GENERATOR_SCRIPTED_FIXTURE
    current_scores = (
        frame.decisions[0].observation.scores if frame.decisions else (0, 0, 0, 0)
    )
    snapshot: Dict[str, Any] = {
        "schema": SNAPSHOT_SCHEMA,
        "snapshot_id": "{0}:{1}:snap{2:03d}".format(panel_seed, predicate_id, attempt.attempt_index),
        "prefix_source": prefix_source,
        "generator": generator,
        "fixture_mode": fixture_mode,
        "source_root_id": attempt.source_root_id,
        "sub_scenario": predicate_id,
        "labels": {
            "main": predicate_id,
            "predicate_values_at_cut": dict(attempt.predicate_values or {}),
            "witness": dict(attempt.predicate_witness or {}),
            "note": "其他谓词命中仅作标签；同根只贡献一个样本一个主子场景",
        },
        "cut_window": {
            "round_no": cut.window_key.round_no,
            "trigger_seq": cut.window_key.trigger_seq,
            "phase": cut.window_key.phase.value,
            "seat": cut.window_key.seat,
        },
        "match_spec": {
            "match_id": match_id,
            "scenario_id": attempt.source_root_id,
            "seed": int(attempt.spec_seed),
            "rounds_per_game": int(rounds_per_game),
            "initial_dealer": 0,
            "initial_scores": [0, 0, 0, 0],
        },
        "seating": {
            "focal_seat": focal_seat,
            "opponent_scenario": opponent_scenario,
            "participant_ids_by_seat": list(participant_ids_by_seat(focal_seat)),
            "note": (
                "夹具演示以脚本行为策略替代执行" if fixture_mode
                else "对手/行为策略按 group-dev-v1 合同情景装配（sitin_stage 白名单）"
            ),
        },
        "stage_ledger": {
            "completed_table_scores": [
                list(row) for row in stage_ledger.get("completed_table_scores", ())
            ],
            "current_table_scores_at_cut": list(current_scores),
        },
        "stage_plan": {
            "table_index": 1,
            "tables_in_stage": int(tables_in_stage),
            "rounds_per_game": int(rounds_per_game),
            "participant_ids_by_seat": list(participant_ids_by_seat(focal_seat)),
        },
        "remaining_schedule": {
            "declared_endpoint": remaining_schedule.get("declared_endpoint", "stage_complete"),
            "remaining_tables_after_current": int(
                remaining_schedule.get("remaining_tables_after_current",
                                       max(0, int(tables_in_stage) - 1))
            ),
            "rounds_per_game": int(rounds_per_game),
            "tables_in_stage": int(tables_in_stage),
        },
        # 观察摘要（既有口径）：合法前缀重建核对用（rebuild_world/inspect_panel）。
        "observation_summary": frame_observation_summary(frame),
        # P16-C3：**实际玩家观察**的完整规范摘要（截取窗口焦点座位依法可见的全部事实：
        # 牌河/副露/最近弃牌/规则状态/公开事件等），与见证里的摘要值同源；含牌河与
        # 规则状态，因此牌河/包头的接线改动在内容摘要上必然可见。只含本人手牌摘要。
        "player_observation_summary": player_observation_summary(
            cut.observation, window_key=cut.window_key),
        "legal_action_prefix": [dict(step) for step in attempt.prefix],
    }
    if fixture_mode:
        snapshot["fixture"] = {
            "template_id": attempt.template_id,
            "attempt_index": attempt.attempt_index,
            "windows_total": len(attempt.prefix) + 1,
        }
    else:
        evidence = dict(runtime_evidence or {})
        snapshot["real"] = {
            "runtime_source": evidence.get("runtime_source", runtime_source),
            # engine_kind 由**实际运行时种类**决定（A1(c)）：显式传入的真实运行时
            # 不再被误标成替身，替身也不会被标成真实引擎。
            "engine_kind": evidence.get(
                "engine_kind", ENGINE_KIND_BY_RUNTIME_KIND[RUNTIME_KIND_REAL]),
            "runtime_kind": evidence.get("runtime_kind", RUNTIME_KIND_REAL),
            "execution_kind": evidence.get("execution_kind", EXECUTION_REAL),
            "engine_identity": dict(evidence.get("engine_identity") or {}),
            "real_tables": bool(evidence.get(
                "real_tables", RUNTIME_KIND_REAL in SELECTION_ELIGIBLE_RUNTIME_KINDS)),
            "replay": "公开 start/frame/advance 重放合法动作前缀并核对观察摘要",
            "prefix_seed_witness": "match_spec.seed + legal_action_prefix 唯一决定重建",
        }
    if attempt.prefix_execution is not None:
        # M2：前缀行为策略装配 ↔ 执行记录 ↔ 根摘要（对手情景身份可核对）。
        snapshot["prefix_behavior"] = dict(attempt.prefix_execution)
    if descriptor is not None:
        # A3/Q3：描述符与根见证在**唯一构造点**落进快照——普通入口与指定根入口
        # 走同一段代码，两个入口的见证因此逐项可比（不各写一套序列化）。
        snapshot["root_descriptor"] = dict(descriptor)
        snapshot["root_witness"] = root_witness(
            attempt=attempt, prefix_source=prefix_source, predicate_id=predicate_id,
            focal_seat=focal_seat, opponent_scenario=opponent_scenario,
            descriptor=descriptor, match_id=match_id, panel_seed=panel_seed,
            requirement_digest=requirement_digest, entry=witness_entry,
            runtime_kind=(runtime_evidence or {}).get("runtime_kind"),
            execution_kind=(runtime_evidence or {}).get("execution_kind"))
    return snapshot


# ---------------------------------------------------------------------------
# 合法前缀重建（§7.2 条 3）：公开 start/frame/advance 重放 + 观察摘要核对
# ---------------------------------------------------------------------------


def _prefix_key(window: Mapping[str, Any]) -> str:
    return "{0}:{1}:{2}".format(
        window.get("phase"), window.get("seat"), window.get("trigger_seq")
    )


def rebuild_world(
    *,
    rules: Any,
    snapshot: Mapping[str, Any],
    value_limits: Optional[ValueAnalysisLimits] = None,
    choice_factory: Optional[Callable[[WindowKey, Action], Any]] = None,
    runtime: Optional[Mapping[str, Any]] = None,
) -> Tuple[Any, Any]:
    """按快照重建世界：start(spec) → 逐帧重放合法动作前缀 → 返回 (engine, world)。

    - 只走模拟器公开接口（start/frame/advance）重放合法前缀，不做通用
      WorldState 序列化、不写任何私有字段；
    - 夹具快照（fixture_mode=True）用 ScriptedFixtureEngine（模板重放）；
      真实快照（v2_behavior，fixture_mode=false）用 runtime 的引擎（生产=
      组合根 SimulationEngine；夹具验收=注入的公开契约验证替身；runtime
      缺省经 build_real_runtime 装配）——绝不回落夹具引擎（Q1 修复⑤）；
    - 每步对窗口重新 rules.analyze 并要求前缀动作在合法候选中（重建即再次
      见证合法性）；缺失/非法前缀 ValueError（fail-closed）；
    - 观察摘要核对由 resume_match 执行（fail-closed），本函数不重复实现
      一套核对口径。
    """
    if snapshot.get("schema") != SNAPSHOT_SCHEMA:
        raise ValueError("快照 schema 必须是 {0}".format(SNAPSHOT_SCHEMA))
    generator = snapshot.get("generator")
    if generator not in (GENERATOR_SCRIPTED_FIXTURE, GENERATOR_V2_BEHAVIOR):
        raise ValueError(
            "未知快照生成器 {0!r}（可重建：{1}/{2}）".format(
                generator, GENERATOR_SCRIPTED_FIXTURE, GENERATOR_V2_BEHAVIOR)
        )
    fixture_mode = bool(snapshot.get("fixture_mode", generator == GENERATOR_SCRIPTED_FIXTURE))
    if generator == GENERATOR_SCRIPTED_FIXTURE and not fixture_mode:
        raise ValueError("夹具生成器快照必须携带 fixture_mode=true（快照损坏）")
    match_spec = snapshot.get("match_spec") or {}
    match_id = str(match_spec.get("match_id"))
    focal_seat = int((snapshot.get("seating") or {}).get("focal_seat", 0))
    if fixture_mode:
        template = (snapshot.get("fixture") or {}).get("template_id")
        if template is None:
            raise ValueError("夹具快照缺少 fixture.template_id（快照损坏）")
        frames = build_fixture_frames(str(template), match_id=match_id, focal_seat=focal_seat)
        engine = ScriptedFixtureEngine(frames, rules, value_limits=value_limits)
        spec = FixtureSpec(
            match_id=match_id,
            scenario_id=str(match_spec.get("scenario_id")),
            seed=int(match_spec.get("seed", 0)),
            rounds_per_game=int(match_spec.get("rounds_per_game", 8)),
            initial_dealer=int(match_spec.get("initial_dealer", 0)),
            initial_scores=tuple(int(x) for x in match_spec.get("initial_scores", (0, 0, 0, 0))),
        )
        chooser = choice_factory or fixture_choice
    else:
        if runtime is None:
            effective_runtime = build_real_runtime(
                rules_config=rules.config,
                rounds_per_game=int(match_spec.get("rounds_per_game", 8)),
                seed=int(match_spec.get("seed", 0)),
                scenario_id=str(match_spec.get("scenario_id")),
            )
        else:
            effective_runtime = resolve_declared_runtime(
                runtime, where="rebuild_world(real)")
        engine = effective_runtime["engine"]
        _forbid_fixture_engine(engine, "rebuild_world(real)")
        spec = effective_runtime["spec_factory"](
            match_id=match_id,
            scenario_id=str(match_spec.get("scenario_id")),
            config=_snapshot_tournament_config(match_spec, rules),
            seed=int(match_spec.get("seed", 0)),
            initial_dealer=int(match_spec.get("initial_dealer", 0)),
            initial_scores=list(match_spec.get("initial_scores", (0, 0, 0, 0))),
        )
        chooser = choice_factory or effective_runtime["choice_factory"]
    world = engine.start(spec)
    return (engine, _replay_prefix(
        engine=engine, world=world, rules=rules, snapshot=snapshot,
        value_limits=value_limits, chooser=chooser,
    ))


def _snapshot_tournament_config(match_spec: Mapping[str, Any], rules: Any) -> Any:
    """从快照 match_spec 恢复 TournamentConfig（真实 spec_factory 需要真配置）。"""
    from hangma_bot.kernel.config import TimingConfig, TournamentConfig

    return TournamentConfig(
        max_games=1,
        rounds_per_game=int(match_spec.get("rounds_per_game", 8)),
        rules=rules.config,
        timing=TimingConfig(**dict(stage.DEFAULT_TIMING)),
    )


def _replay_prefix(
    *,
    engine: Any,
    world: Any,
    rules: Any,
    snapshot: Mapping[str, Any],
    value_limits: Optional[ValueAnalysisLimits],
    chooser: Callable[[WindowKey, Action], Any],
) -> Any:
    """逐帧重放合法动作前缀（引擎无关：只经公开 frame/advance 交互）。"""
    steps_left = {
        _prefix_key(step.get("window_key") or {}): step.get("action_key")
        for step in snapshot.get("legal_action_prefix") or []
    }
    if len(steps_left) != len(snapshot.get("legal_action_prefix") or []):
        raise ValueError("重建失败：合法动作前缀含重复窗口键（快照损坏）")
    while steps_left:
        frame = engine.frame(world)
        if frame.final_scores is not None or frame.blocked_reason is not None:
            raise ValueError("重建失败：前缀未耗尽但引擎已到终态（快照与引擎不一致）")
        choices = []
        for decision in frame.decisions:
            key = _prefix_key(window_key_to_json(decision.window_key))
            wanted = steps_left.pop(key, None)
            if wanted is None:
                raise ValueError(
                    "重建失败：窗口 {0} 不在合法动作前缀中（截取必须在帧边界）".format(key)
                )
            analysis = analyze_window(rules, decision.observation, value_limits)
            candidate = next(
                (c for c in analysis.legal_candidates if c.action_key == wanted), None
            )
            if candidate is None:
                raise ValueError(
                    "重建失败：前缀动作 {0} 不在窗口 {1} 的合法候选中".format(wanted, key)
                )
            choices.append(chooser(decision.window_key, candidate.action))
        world = engine.advance(world, frame.revision, tuple(choices))
    return world


# ---------------------------------------------------------------------------
# 双臂续打（§7.2 条 4）：同快照出发，各自 PlayerObservation 决策到声明终点
# ---------------------------------------------------------------------------


def _accumulate_table(
    totals: Dict[str, int], place_totals: Dict[str, int],
    scores_by_seat: Sequence[int], participants_by_seat: Sequence[str],
) -> None:
    """把一桌终局积分与名次分累计进阶段账（participant 级；单一实现来自
    sitin_stage.place_points_for_table）。"""
    points = stage.place_points_for_table(scores_by_seat)
    for seat, participant in enumerate(participants_by_seat):
        totals[participant] = totals.get(participant, 0) + int(scores_by_seat[seat])
        place_totals[participant] = place_totals.get(participant, 0) + int(points[seat])


def _stage_situation_for(
    *,
    snapshot: Mapping[str, Any],
    table_no: int,
    totals: Dict[str, int],
    place_totals: Dict[str, int],
    participants_by_seat: Sequence[str],
    permutation: Sequence[int],
) -> StageSituationProjection:
    """当前桌的阶段处境可见投影（Q8）：按实际座位展开已完成桌账。

    totals/place_totals 按 participant 累计；permutation[逻辑位]=实际座位，
    与 sitin_stage.TablePlan 同口径。不包含当前桌进行中的积分（那已在
    PlayerObservation.scores 里）。"""
    logical_by_seat = [permutation.index(seat) for seat in range(4)]
    scores = [0, 0, 0, 0]
    places = [0, 0, 0, 0]
    for seat in range(4):
        participant = participants_by_seat[logical_by_seat[seat]]
        scores[seat] = int(totals.get(participant, 0))
        places[seat] = int(place_totals.get(participant, 0))
    tables_in_stage = int((snapshot.get("remaining_schedule") or {}).get(
        "tables_in_stage", 2))
    return StageSituationProjection(
        stage_table_no=int(table_no),
        tables_in_stage=tables_in_stage,
        tables_completed=int(table_no) - 1,
        rounds_per_game=int((snapshot.get("match_spec") or {}).get("rounds_per_game", 8)),
        stage_scores_by_seat=(scores[0], scores[1], scores[2], scores[3]),
        place_points_by_seat=(places[0], places[1], places[2], places[3]),
        participant_ids_by_seat=tuple(participants_by_seat[logical_by_seat[seat]]
                                      for seat in range(4)),  # type: ignore[arg-type]
    )


# ---------------------------------------------------------------------------
# P9b（R8 修复轮 · 复审 §4 A5 上游读数）：截取窗口内两臂各自的动作
#
# 缺陷（P9 收口时如实上报）：sitin-opportunity-snapshot/1 只采集截取窗口的观察
# 摘要与行为策略的合法动作前缀，**候选臂与基线臂在截取窗口各自选了什么**没有
# 字段；sitin-feedback-projection/1 因此在事实段记 input gap
# window.arm_actions_not_collected（「同一可见窗口双方动作」缺失）。
#
# 修复：把两臂在截取窗口的**已执行动作**登记到 P9 预留的两个位置
# （snapshot.window_actions / scenarios[i].double_arm.arms[*].focal_action_at_cut）。
# 读数只来自 resume_match 在截取帧写下的执行记录（MatchDecisionRecord）：不填
# 默认值、不推测；某臂未到达或在该窗口不可行动时，如实登记 unavailable /
# not_reached 并给原因（两臂都没有读数时连 window_actions 都不写——宁可让 P9
# 按缺读数上报，也不给空壳）。
# ---------------------------------------------------------------------------

#: 截取窗口两臂动作读数 schema（P9 预留位置 snapshot.window_actions）。
WINDOW_ACTIONS_SCHEMA = "sitin-window-arm-actions/1"
#: 臂顺序（聚合读数固定键序：产物逐字节可比）。
ARM_ORDER: Tuple[str, ...] = ("baseline", "candidate")
#: 读数状态：**已采集**——动作来自该臂在截取帧写下的执行记录。
ARM_ACTION_COLLECTED = "collected"
#: 读数状态：**不可用**——该臂到达了窗口，但该窗口没有可执行动作。
ARM_ACTION_UNAVAILABLE = "unavailable"
#: 读数状态：**未到达**——该臂在截取窗口之前就失败（无执行记录）。
ARM_ACTION_NOT_REACHED = "not_reached"


def cut_window_key(snapshot: Mapping[str, Any]) -> Dict[str, Any]:
    """快照截取窗口的形状化键（身份绑定用；与 snapshot.cut_window 逐字段一致）。"""

    window = snapshot.get("cut_window") or {}
    return {
        "round_no": window.get("round_no"),
        "trigger_seq": window.get("trigger_seq"),
        "phase": window.get("phase"),
        "seat": window.get("seat"),
    }


def window_actions_locator(scenario_index: int = 0) -> Dict[str, Any]:
    """读数在机会面板产物里的 JSON 指针对照（对账：产物路径 + 指针逐项取回）。

    指针以承载读数的 **panel.json** 为根（`/scenarios/<i>/...`），与
    sitin_feedback 对账表同一口径；本模块不把绝对路径写进产物（产物可搬迁、
    逐字节可比）。
    """

    base = "/scenarios/{0}".format(int(scenario_index))
    pointers = {
        # P9 采用的**第一个**登记位置（聚合读数）。
        "snapshot.window_actions": base + "/snapshot/window_actions",
    }
    for name in ARM_ORDER:
        # P9 采用的**第二个**登记位置（逐臂读数，可独立定位）。
        pointers["arms.{0}.focal_action_at_cut".format(name)] = (
            base + "/double_arm/arms/{0}/focal_action_at_cut".format(name))
    return {
        "artifact": "panel.json（承载本读数的 sitin-opportunity-panel/1 产物）",
        "pointers": pointers,
    }


def _record_field(record: Any, name: str) -> Any:
    """执行记录字段读取（MatchDecisionRecord 数据类与 JSON 映射两种形状同口径）。"""

    if isinstance(record, Mapping):
        return record.get(name)
    return getattr(record, name, None)


def _record_window_key(record: Any) -> Dict[str, Any]:
    """执行记录的窗口键形状化（与 cut_window_key 同字段）。"""

    raw = _record_field(record, "window_key") or {}
    if not isinstance(raw, Mapping):
        return {}
    return {
        "round_no": raw.get("round_no"),
        "trigger_seq": raw.get("trigger_seq"),
        "phase": raw.get("phase"),
        "seat": raw.get("seat"),
    }


def _same_window(left: Mapping[str, Any], right: Mapping[str, Any]) -> bool:
    """两个窗口键是否同一窗口（只比身份四元组，不比 schema_version/game_id）。"""

    keys = ("round_no", "trigger_seq", "phase", "seat")
    return all(left.get(key) == right.get(key) for key in keys)


def _cut_frame_window_keys(snapshot: Mapping[str, Any]) -> Tuple[Dict[str, Any], ...]:
    """快照观察摘要所列**截取帧**的全部窗口键（续打首帧对齐的见证口径）。"""

    summary = snapshot.get("observation_summary") or {}
    return tuple(
        {"round_no": entry.get("round_no"), "trigger_seq": entry.get("trigger_seq"),
         "phase": entry.get("phase"), "seat": entry.get("seat")}
        for entry in (summary.get("decisions") or ())
        if isinstance(entry, Mapping)
    )


def _window_label(window: Mapping[str, Any]) -> str:
    return "round_no={0}/trigger_seq={1}/{2}/seat{3}".format(
        window.get("round_no"), window.get("trigger_seq"),
        window.get("phase"), window.get("seat"))


def cut_window_arm_reading(
    *,
    arm_name: str,
    snapshot: Mapping[str, Any],
    decisions: Sequence[Any],
    arm_status: Optional[str],
    reached: bool,
    reason: Optional[str] = None,
) -> Dict[str, Any]:
    """一臂在截取窗口的动作读数（**只来自执行记录**；三键并入臂记录）。

    判据（不读世界私有状态、不推算、不填默认值）：

    - `reached=False`（该臂在取到执行记录前就失败）→ `not_reached`；
    - 执行记录里没有截取窗口的决策 → `unavailable`（附实际记录到的窗口，可对账）；
    - 该窗口的决策 `action_key` 为空（策略失败/超时且无紧急候选，或复核非法且
      无保底）→ `unavailable`（原因带 fallback_reason）；
    - 否则 → `collected`：登记该臂实际执行的动作键与合法/紧急/降级事实。

    读数对象带 root_id 与 window_key（身份绑定），另带
    `cut_frame_records_matched`：本臂执行记录中与快照观察摘要所列截取帧窗口
    逐一对应的条数（= 续打确实从截取帧开始的见证，不解释为策略行为）。
    """

    window = cut_window_key(snapshot)
    if not reached:
        return {
            "focal_action_at_cut": None,
            "focal_action_at_cut_status": ARM_ACTION_NOT_REACHED,
            "focal_action_at_cut_reason": (
                reason or "该臂在截取窗口之前失败（没有执行记录）"),
        }
    records = list(decisions)
    frame_keys = _cut_frame_window_keys(snapshot)
    matched = [record for record in records
               if any(_same_window(_record_window_key(record), key)
                      for key in frame_keys)]
    found = [record for record in records
             if _same_window(_record_window_key(record), window)]
    if not found:
        seen = "、".join(_window_label(_record_window_key(record))
                        for record in records) or "（空：该臂没有任何窗口决策）"
        return {
            "focal_action_at_cut": None,
            "focal_action_at_cut_status": ARM_ACTION_UNAVAILABLE,
            "focal_action_at_cut_reason": (
                "本臂执行记录里没有截取窗口 {0} 的决策（实际记录到：{1}）"
                "——不填默认值、不推测".format(_window_label(window), seen)),
        }
    record = found[0]
    action = _record_field(record, "action_key")
    if not action:
        return {
            "focal_action_at_cut": None,
            "focal_action_at_cut_status": ARM_ACTION_UNAVAILABLE,
            "focal_action_at_cut_reason": (
                "本臂到达截取窗口 {0} 但没有可执行动作（fallback_reason={1}，"
                "legal={2}）——不填默认值、不推测".format(
                    _window_label(window), _record_field(record, "fallback_reason"),
                    _record_field(record, "legal"))),
        }
    return {
        "focal_action_at_cut": {
            "schema": WINDOW_ACTIONS_SCHEMA,
            "arm": arm_name,
            "root_id": snapshot.get("source_root_id"),
            "window_key": window,
            "seat": window.get("seat"),
            "action_key": str(action),
            "policy_id": _record_field(record, "policy_id"),
            "decision_id": _record_field(record, "decision_id"),
            "legal": _record_field(record, "legal"),
            "is_emergency": bool(_record_field(record, "is_emergency")),
            "fallback_reason": _record_field(record, "fallback_reason"),
            "arm_status": arm_status,
            "cut_frame_records_matched": len(matched),
            "source": ("resume_match 执行记录（截取帧 MatchDecisionRecord）"
                       "——本臂在该窗口实际执行的动作"),
        },
        "focal_action_at_cut_status": ARM_ACTION_COLLECTED,
        "focal_action_at_cut_reason": None,
    }


def window_actions_from_arms(
    *,
    snapshot: Mapping[str, Any],
    arms: Mapping[str, Any],
    scenario_index: int = 0,
) -> Optional[Dict[str, Any]]:
    """聚合两臂在截取窗口的动作读数（P9 预留位置 snapshot.window_actions）。

    返回 None 表示**两臂都没有读数**：此时不写空壳（P9 侧按缺读数如实上报
    input gap，比给一个空对象诚实）。任一侧采集到读数即返回完整映射：root_id
    与 window_key 身份绑定、逐臂 status/action_key/reason、以及对账指针。
    """

    entries: Dict[str, Any] = {}
    collected: List[str] = []
    window = cut_window_key(snapshot)
    for name in ARM_ORDER:
        arm = arms.get(name)
        arm = arm if isinstance(arm, Mapping) else {}
        reading = arm.get("focal_action_at_cut")
        if isinstance(reading, Mapping):
            entry = dict(reading)
            entry["status"] = ARM_ACTION_COLLECTED
            entry["reason"] = None
            entries[name] = entry
            collected.append(name)
            continue
        entries[name] = {
            "schema": WINDOW_ACTIONS_SCHEMA,
            "arm": name,
            "root_id": snapshot.get("source_root_id"),
            "window_key": window,
            "action_key": None,
            "status": arm.get("focal_action_at_cut_status") or ARM_ACTION_UNAVAILABLE,
            "arm_status": arm.get("status"),
            "reason": (arm.get("focal_action_at_cut_reason")
                       or "该臂在截取窗口的动作读数为空（原因未登记）"),
        }
    if not collected:
        return None
    return {
        "schema": WINDOW_ACTIONS_SCHEMA,
        "root_id": snapshot.get("source_root_id"),
        "sub_scenario": snapshot.get("sub_scenario"),
        "window_key": window,
        "collected_arms": collected,
        "arms": entries,
        "artifact_locator": window_actions_locator(scenario_index),
        "source": ("resume_match 执行记录（两臂在截取帧实际执行的动作）：本批真实采集，"
                   "未采集的臂在 status/reason 里如实标注——无默认值、无推测值"),
    }


def _completion_reason(outcome: Any) -> str:
    """完成原因（来自执行记录）：complete + 阻塞/错误原因（有则如实拼接）。"""

    parts = [str(getattr(outcome, "status", "unknown"))]
    for field in ("blocked_reason", "error_reason"):
        value = getattr(outcome, field, None)
        if value:
            parts.append("{0}={1}".format(field, value))
    return "；".join(parts)


def run_conditional_stage_arm(
    *,
    arm_name: str,
    rules: Any,
    snapshot: Mapping[str, Any],
    policies_by_seat: Sequence[Any],
    config: MatchDriverConfig,
    value_limits: Optional[ValueAnalysisLimits] = None,
    now_monotonic: Optional[Callable[[], float]] = None,
    runtime: Optional[Mapping[str, Any]] = None,
    current_world_transform: Optional[Callable[[Any], Any]] = None,
) -> Dict[str, Any]:
    """一臂的**完整剩余阶段**续打（R3 修复③）：当前桌续完 + 全部剩余桌 + 阶段 U。

    - 当前桌：rebuild_world（合法前缀重放）→ 可选离线世界变换 → resume_match（截取帧尚未行动的
      响应者按各自观察重新决策）；终局积分经 place_points 计名次分；
    - 剩余桌：按快照 stage_plan/remaining_schedule 逐桌执行（夹具快照用
      build_fixture_full_table_frames 的完整桌脚本；真实快照用 runtime 的
      spec_factory + drive_match 自然完整桌）；桌 seed 只由根身份派生，不含
      臂标识（同根两臂同随机映射，配对可比）；
    - ``current_world_transform`` 只供离线教师研究，在重建完成后、首帧观察
      摘要复核前作用于不透明世界；变换若改变当前玩家观察会被 resume_match
      fail-closed 拒绝。缺省 None 时原执行逐字不变；
    - 每桌把已完成桌账经 StageSituationProjection 注入该桌策略请求（Q8）；
    - 阶段 U：sitin_stage.group_advance_utility（缺 god_count 识别区间，
      不补零、不读投影名次）。
    """
    clock = now_monotonic or (lambda: 800.0)
    focal_seat_for_arm = int((snapshot.get("seating") or {}).get("focal_seat", 0))
    # A1：运行时种类只认**装配标签**（夹具快照=夹具）；注入的运行时若没有标签，
    # 记 unverified 而**不猜成真实**（后续 rebuild_world/剩余桌会被 fail-closed 拒绝）。
    arm_runtime_kind = (RUNTIME_KIND_FIXTURE if bool(snapshot.get("fixture_mode", False))
                        else runtime_kind_of(runtime))
    record: Dict[str, Any] = {
        "arm": arm_name, "status": None, "usable": False, "error": None,
        # A1：运行时种类/执行类别来自实际使用的运行时（夹具 / 真实 / 替身）。
        "runtime_kind": arm_runtime_kind,
        "execution_kind": EXECUTION_KIND_BY_RUNTIME_KIND.get(arm_runtime_kind,
                                                              "unverified_runtime"),
        "selection_eligible": selection_eligible_for(arm_runtime_kind),
        # 焦点策略身份（供消费方把样本臂绑定到真实策略，而非替身名）。
        "focal_policy_id": str(getattr(policies_by_seat[focal_seat_for_arm],
                                       "policy_id",
                                       type(policies_by_seat[focal_seat_for_arm]).__name__)),
        # P9b：截取窗口动作读数（P9 预留位置 arms[*].focal_action_at_cut）。
        # 初始全空；续打后按**执行记录**填入，未到达/不可用带原因（不填默认值）。
        "focal_action_at_cut": None, "focal_action_at_cut_status": None,
        "focal_action_at_cut_reason": None,
        "tables": [], "decisions_after_cut": None, "decisions_total": None,
        "stage_totals_by_participant": None, "stage_place_points_by_participant": None,
        "focal_stage_score": None, "u": None, "u_low": None, "u_high": None,
        "unresolved": None, "u_interval": None, "elapsed_ms": None,
    }
    started = time.monotonic()
    fixture_mode = bool(snapshot.get("fixture_mode",
                                     snapshot.get("generator") == GENERATOR_SCRIPTED_FIXTURE))
    stage_plan = snapshot.get("stage_plan") or {}
    participants = list(stage_plan.get("participant_ids_by_seat")
                        or participant_ids_by_seat(int((snapshot.get("seating") or {}).get("focal_seat", 0))))
    current_permutation = tuple(stage_plan.get("permutation") or (0, 1, 2, 3))
    tables_in_stage = int((snapshot.get("remaining_schedule") or {}).get("tables_in_stage", 2))
    totals: Dict[str, int] = {}
    place_totals: Dict[str, int] = {}
    ledger = snapshot.get("stage_ledger") or {}
    for row in ledger.get("completed_table_scores") or []:
        for logical, participant in enumerate(participants):
            totals[participant] = totals.get(participant, 0) + int(row[logical])
    try:
        # --- 当前桌：重建 + 受控续打（截取帧未行动响应者重新决策） ---
        engine, world = rebuild_world(
            rules=rules, snapshot=snapshot, value_limits=value_limits,
            runtime=(None if fixture_mode else runtime),
        )
        if current_world_transform is not None:
            world = current_world_transform(world)
        chooser = fixture_choice if fixture_mode else engine_choice(engine, runtime, fixture_mode)
        situation = _stage_situation_for(
            snapshot=snapshot, table_no=int(stage_plan.get("table_index", 1)),
            totals=totals, place_totals=place_totals,
            participants_by_seat=participants, permutation=current_permutation,
        )
        outcome = asyncio.run(resume_match(
            engine=engine,
            world=world,
            policies_by_seat=tuple(policies_by_seat),
            rules=rules,
            choice_factory=chooser,
            config=config,
            now_monotonic=clock,
            wall_clock=None,
            remaining_schedule=snapshot.get("remaining_schedule"),
            stage_snapshot={
                "observation_summary": snapshot["observation_summary"],
                "match_spec": snapshot["match_spec"],
            },
            value_limits=value_limits,
            stage_situation=situation,
        ))
        record["decisions_after_cut"] = len(outcome.decisions)
        # P9b：本臂在截取窗口实际执行的动作（读数只来自这条执行记录；
        # 该臂若在截取窗口就没有动作，此处如实登记 unavailable + 原因）。
        record.update(cut_window_arm_reading(
            arm_name=arm_name, snapshot=snapshot, decisions=outcome.decisions,
            arm_status=str(outcome.status), reached=True))
        record["runtime_engine_identity"] = (
            {} if arm_runtime_kind == RUNTIME_KIND_FIXTURE
            else dict((runtime or {}).get("engine_identity") or {}))  # type: ignore[union-attr]
        if outcome.status != "complete" or outcome.final_scores is None:
            raise RuntimeError("当前桌续打未完成（status={0}）：{1}".format(
                outcome.status,
                outcome.error_reason or outcome.blocked_reason or "无终局积分"))
        record["tables"].append({
            "table_id": "{0}:current".format(snapshot.get("source_root_id")),
            "match_status": outcome.status,
            "scores_by_seat": [int(item) for item in outcome.final_scores],
            "partial": True,
            # A1(d)：逐桌决策计数与完成原因取自执行记录（不靠调用方转述）。
            "decisions": len(outcome.decisions),
            "completion_reason": _completion_reason(outcome),
            "final_scores": [int(item) for item in outcome.final_scores],
            **execution_audit.conditional_fields(
                "{0}:current".format(snapshot.get("source_root_id")),
                outcome.decisions, policies_by_seat),
        })
        _accumulate_table(totals, place_totals, outcome.final_scores,
                          [participants[seat] for seat in range(4)])
        # --- 剩余桌：逐桌自然完整执行（同根两臂同 seed） ---
        root_seed = int((snapshot.get("match_spec") or {}).get("seed", 0))
        match_id = str((snapshot.get("match_spec") or {}).get("match_id"))
        focal_seat = int((snapshot.get("seating") or {}).get("focal_seat", 0))
        for table_no in range(int(stage_plan.get("table_index", 1)) + 1, tables_in_stage + 1):
            table_seed = stage.derive_seed(root_seed, "table", str(table_no), "residual")
            # 歧义处理决定（冻结）：条件续打的剩余桌**不轮换座位**——条件场景的
            # 座位由快照声明（焦点固定在 focal_seat，两臂可比）；换座轮换属自然
            # 面板的赛程计划语义（sitin_stage.build_table_plan + permutation），
            # 不在条件续打里隐式引入。
            permutation = (0, 1, 2, 3)
            situation = _stage_situation_for(
                snapshot=snapshot, table_no=table_no, totals=totals,
                place_totals=place_totals, participants_by_seat=participants,
                permutation=permutation,
            )
            if fixture_mode:
                table_match_id = "{0}:t{1}".format(match_id, table_no)
                frames = build_fixture_full_table_frames(
                    match_id=table_match_id, focal_seat=focal_seat, table_no=table_no)
                table_engine = ScriptedFixtureEngine(frames, rules, value_limits=value_limits)
                spec = FixtureSpec(
                    match_id=table_match_id,
                    scenario_id=str((snapshot.get("match_spec") or {}).get("scenario_id")),
                    seed=table_seed, rounds_per_game=int(
                        (snapshot.get("match_spec") or {}).get("rounds_per_game", 8)),
                    initial_dealer=0, initial_scores=(0, 0, 0, 0),
                )
                table_outcome = drive_table_via_driver(
                    engine=table_engine, spec=spec, policies_by_seat=policies_by_seat,
                    rules=rules, chooser=fixture_choice, config=config, clock=clock,
                    value_limits=value_limits, situation=situation,
                )
            else:
                effective_runtime = (
                    resolve_declared_runtime(runtime, where="run_conditional_stage_arm")
                    if runtime is not None else build_real_runtime(
                        rules_config=rules.config,
                        rounds_per_game=int(
                            (snapshot.get("match_spec") or {}).get("rounds_per_game", 8)),
                        seed=table_seed,
                        scenario_id=str((snapshot.get("match_spec") or {}).get("scenario_id")),
                    ))
                spec = effective_runtime["spec_factory"](
                    match_id="{0}:t{1}".format(match_id, table_no),
                    scenario_id=str((snapshot.get("match_spec") or {}).get("scenario_id")),
                    config=_snapshot_tournament_config(snapshot.get("match_spec") or {}, rules),
                    seed=table_seed, initial_dealer=0, initial_scores=[0, 0, 0, 0],
                )
                table_outcome = drive_table_via_driver(
                    engine=effective_runtime["engine"], spec=spec,
                    policies_by_seat=policies_by_seat, rules=rules,
                    chooser=effective_runtime["choice_factory"], config=config,
                    clock=clock, value_limits=value_limits, situation=situation,
                )
            if table_outcome.status != "complete" or table_outcome.final_scores is None:
                raise RuntimeError("剩余桌 {0} 未完成（status={1}）".format(
                    table_no, table_outcome.status))
            record["tables"].append({
                "table_id": "{0}:t{1}".format(snapshot.get("source_root_id"), table_no),
                "match_status": table_outcome.status,
                "scores_by_seat": [int(item) for item in table_outcome.final_scores],
                "partial": False,
                "decisions": len(table_outcome.decisions),
                "completion_reason": _completion_reason(table_outcome),
                "final_scores": [int(item) for item in table_outcome.final_scores],
                **execution_audit.conditional_fields(
                    "{0}:t{1}".format(snapshot.get("source_root_id"), table_no),
                    table_outcome.decisions, policies_by_seat),
            })
            _accumulate_table(totals, place_totals, table_outcome.final_scores,
                              [participants[current_table_logical(permutation, seat)]
                               for seat in range(4)])
        rows = [stage.LedgerRow(participant_id=pid, total_score=totals[pid],
                                place_points=place_totals[pid])
                for pid in sorted(totals)]
        utility = stage.group_advance_utility(rows, focal_id=FOCAL_PARTICIPANT)
        record.update({
            "status": "complete", "usable": True,
            "stage_totals_by_participant": dict(sorted(totals.items())),
            "stage_place_points_by_participant": dict(sorted(place_totals.items())),
            "focal_stage_score": int(totals[FOCAL_PARTICIPANT]),
            "u": (float(utility["u_low"] + utility["u_high"]) / 2.0
                  if utility["u_low"] == utility["u_high"] else None),
            "u_low": float(utility["u_low"]), "u_high": float(utility["u_high"]),
            "unresolved": utility["unresolved"],
            "u_interval": {"a": utility["a"], "b": utility["b"],
                           "tie_block": list(utility["tie_block"])},
        })
    except Exception as error:  # 臂级故障隔离（T16）：数值不冒充可用
        record["status"] = "error"
        record["error"] = "{0}: {1}".format(type(error).__name__, error)
        if record.get("focal_action_at_cut_status") is None:
            # P9b：异常发生在取到执行记录之前 → 该臂**未到达**截取窗口，
            # 如实登记状态与原因（不填默认动作、不猜测）。
            record.update(cut_window_arm_reading(
                arm_name=arm_name, snapshot=snapshot, decisions=(),
                arm_status="error", reached=False,
                reason="本臂在到达截取窗口之前失败（{0}: {1}）".format(
                    type(error).__name__, error)))
    if record.get("focal_action_at_cut_status") is None:
        # 防御（正常路径不可达）：任何异常路径都必须给出显式状态，不静默留空。
        record.update(cut_window_arm_reading(
            arm_name=arm_name, snapshot=snapshot, decisions=(),
            arm_status=str(record.get("status")), reached=False,
            reason="本臂未产生截取窗口的执行记录（读数缺失）"))
    record["elapsed_ms"] = round((time.monotonic() - started) * 1000.0, 3)
    # A1(d)：逐桌决策计数合计与完成原因一律来自执行记录（可被准入程序交叉校验）。
    record["decisions_total"] = sum(int(table.get("decisions") or 0)
                                    for table in record.get("tables") or [])
    record["tables_executed"] = len(record.get("tables") or [])
    record["completion_reasons"] = [str(table.get("completion_reason"))
                                    for table in record.get("tables") or []]
    record["execution_review"] = execution_audit.review_tables(record["tables"])
    return record


def engine_choice(engine: Any, runtime: Optional[Mapping[str, Any]],
                  fixture_mode: bool) -> Callable[[WindowKey, Action], Any]:
    """当前引擎配套的 choice_factory（真实 runtime 用组合根 choice_factory）。"""
    if fixture_mode or runtime is None:
        return fixture_choice
    return runtime["choice_factory"]


def current_table_logical(permutation: Sequence[int], seat: int) -> int:
    """实际座位 seat 上的逻辑位（permutation[逻辑位]=实际座位 的逆映射）。"""
    return list(permutation).index(seat)


def drive_table_via_driver(
    *,
    engine: Any, spec: Any, policies_by_seat: Sequence[Any], rules: Any,
    chooser: Callable[[WindowKey, Action], Any], config: MatchDriverConfig,
    clock: Callable[[], float], value_limits: Optional[ValueAnalysisLimits],
    situation: StageSituationProjection,
) -> Any:
    """drive_match 驱动一张完整桌（带 Q8 阶段处境注入；共享驱动循环单一实现）。"""
    from hangma_bot.offline.evaluate import drive_match

    return asyncio.run(drive_match(
        engine=engine, spec=spec, policies_by_seat=tuple(policies_by_seat),
        rules=rules, choice_factory=chooser, config=config,
        now_monotonic=clock, wall_clock=None, value_limits=value_limits,
        stage_situation=situation,
    ))


def run_double_arm(
    *,
    rules: Any,
    snapshot: Mapping[str, Any],
    baseline_policies_by_seat: Sequence[Any],
    candidate_policies_by_seat: Sequence[Any],
    config: MatchDriverConfig,
    value_limits: Optional[ValueAnalysisLimits] = None,
    now_monotonic: Optional[Callable[[], float]] = None,
    runtime: Optional[Mapping[str, Any]] = None,
    scenario_index: int = 0,
    current_world_transform: Optional[Callable[[Any], Any]] = None,
) -> Mapping[str, Any]:
    """从同一快照出发跑候选/基线两臂的**完整剩余阶段**；一臂失败整样本 invalid（T16）。

    - 每臂独立重建（fresh engine 重放合法前缀）+ 可选同一确定性离线世界变换
      + 观察摘要核对（不一致即该
      臂失败，fail-closed）；
    - 重建后截取帧尚未推进的响应者按该帧观察重新决策（resume_match 逐窗口
      请求策略，不沿用任何预先选好的响应）；
    - 续完当前桌及全部剩余桌后计算 group_advance_v1 阶段 U（识别区间）；
    - 任一臂 rebuild 异常 / 摘要不一致 / 任一桌未完成 → 样本整体 invalid：
      成功臂的数值保留在 arms 明细里但标记 usable=False，不冒充可用样本
      （T16：不保留半成品成功臂）。
    - P9b：返回值另带 `window_actions`（P9 预留位置 snapshot.window_actions 的
      聚合读数）；`scenario_index` 只用于生成对账用的 JSON 指针（缺省 0：机会
      面板每份只含一个场景）。
    """
    arms: Dict[str, Any] = {}
    for arm_name, policies in (
        ("baseline", baseline_policies_by_seat),
        ("candidate", candidate_policies_by_seat),
    ):
        arms[arm_name] = run_conditional_stage_arm(
            arm_name=arm_name, rules=rules, snapshot=snapshot,
            policies_by_seat=policies, config=config,
            value_limits=value_limits, now_monotonic=now_monotonic,
            runtime=runtime,
            current_world_transform=current_world_transform,
        )
    valid = all(arm["usable"] for arm in arms.values())
    # A1(d)：整样本的执行证据汇总（来自各臂执行记录，不靠调用方转述）。
    runtime_kinds = sorted({str(arm.get("runtime_kind")) for arm in arms.values()})
    uniform_kind = runtime_kinds[0] if len(runtime_kinds) == 1 else None
    if uniform_kind not in RUNTIME_KINDS:
        uniform_kind = None  # 无标签/混合：不猜真实，标 unverified
    return {
        "valid": valid, "arms": arms,
        # P9b：两臂在截取窗口的动作读数（两臂都没有读数时为 None：不写空壳，
        # 由 P9 侧按缺读数如实上报 input gap）。
        "window_actions": window_actions_from_arms(
            snapshot=snapshot, arms=arms, scenario_index=scenario_index),
        "declared_endpoint": "stage_complete",
        "runtime_kind": uniform_kind,
        "execution_kind": (EXECUTION_KIND_BY_RUNTIME_KIND[uniform_kind]
                           if uniform_kind else "unverified_runtime"),
        "selection_eligible": all(bool(arm.get("selection_eligible"))
                                   for arm in arms.values()),
        "tables_executed": {name: int(arm.get("tables_executed") or 0)
                            for name, arm in arms.items()},
        "decisions_total": {name: int(arm.get("decisions_total") or 0)
                            for name, arm in arms.items()},
        "completion_reasons": {name: list(arm.get("completion_reasons") or [])
                               for name, arm in arms.items()},
    }


def build_cost_record(
    *,
    snapshot: Mapping[str, Any],
    double_arm: Mapping[str, Any],
    counters: Mapping[str, Any],
    opponent_policies: Sequence[str],
    rule_config: Mapping[str, Any],
    focal_seat: int,
) -> Mapping[str, Any]:
    """§7.4 逐字段费用账行。

    字段清单：来源根、场景谓词/生成器身份、候选/基线/对手、座位、规则配置、
    终点、完整性、终端 U 或 U 区间（完整剩余阶段续打后由
    sitin_stage.group_advance_utility 求值；另留 C2 挂接点）、本座位净积分、
    四家座位序、合法大额结算贡献、支付、耗时、降级、实际执行单局/桌赛数、
    前缀尝试计数（含未命中/UNKNOWN/errors 计数）与部分桌赛执行标注。
    """
    match_spec = snapshot.get("match_spec") or {}
    ledger = snapshot.get("stage_ledger") or {}
    completed_tables = ledger.get("completed_table_scores") or []
    at_cut = list(ledger.get("current_table_scores_at_cut") or (0, 0, 0, 0))
    fixture_mode = bool(snapshot.get("fixture_mode",
                                     snapshot.get("generator") == GENERATOR_SCRIPTED_FIXTURE))
    large_threshold = 8
    large_settlements = []
    payments = {}
    net_by_arm = {}
    stage_net_by_arm = {}
    current_final_by_arm = {}
    stage_u_by_arm = {}
    rounds_by_arm = {}
    for arm_name, arm in (double_arm.get("arms") or {}).items():
        tables = arm.get("tables") or []
        current_final = next((table["scores_by_seat"] for table in tables
                              if table.get("partial")), None)
        current_final_by_arm[arm_name] = current_final
        if current_final is None:
            net_by_arm[arm_name] = None
            payments[arm_name] = None
        else:
            net = int(current_final[focal_seat]) - int(at_cut[focal_seat])
            net_by_arm[arm_name] = net
            payments[arm_name] = [int(current_final[seat]) - int(at_cut[seat])
                                  for seat in range(4)]
            for seat in range(4):
                delta = int(current_final[seat]) - int(at_cut[seat])
                if abs(delta) >= large_threshold:
                    large_settlements.append({
                        "arm": arm_name, "seat": seat, "delta": delta,
                        "threshold": large_threshold,
                        "note": ("夹具 outcome_branch 映射积分，非规则结算"
                                 if fixture_mode else "当前桌终局积分差"),
                    })
        totals = arm.get("stage_totals_by_participant") or {}
        # 阶段总账已含快照携带的已完成桌积分（run_conditional_stage_arm 初始化
        # 时累计），此处直接取焦点总账，不重复叠加。
        stage_net_by_arm[arm_name] = (
            int(totals.get(FOCAL_PARTICIPANT, 0)) if totals else None
        )
        stage_u_by_arm[arm_name] = {
            "u": arm.get("u"), "u_low": arm.get("u_low"),
            "u_high": arm.get("u_high"), "unresolved": arm.get("unresolved"),
            "u_interval": arm.get("u_interval"),
            "policy": "recognition_interval（sitin_stage.group_advance_utility）",
        }
        rounds_by_arm[arm_name] = len(tables)
    return {
        "record_schema": COST_RECORD_SCHEMA,
        "source_root_id": snapshot.get("source_root_id"),
        "scenario_predicate": snapshot.get("sub_scenario"),
        "generator": snapshot.get("generator"),
        "prefix_source": snapshot.get("prefix_source"),
        "fixture_mode": fixture_mode,
        # A1(c)(d)：运行时种类/引擎种类/执行类别来自实际装配对象与执行记录。
        "runtime_kind": double_arm.get("runtime_kind"),
        "execution_kind": double_arm.get("execution_kind"),
        "engine_kind": ENGINE_KIND_BY_RUNTIME_KIND.get(
            str(double_arm.get("runtime_kind")), "scripted_fixture_engine"),
        "engine_identity": dict((snapshot.get("real") or {}).get("engine_identity") or {}),
        "selection_eligible": bool(double_arm.get("selection_eligible")),
        "tables_executed_by_arm": dict(double_arm.get("tables_executed") or {}),
        "decisions_total_by_arm": dict(double_arm.get("decisions_total") or {}),
        "completion_reasons_by_arm": {
            name: list(reasons) for name, reasons
            in (double_arm.get("completion_reasons") or {}).items()},
        "opponent_scenario": (snapshot.get("seating") or {}).get("opponent_scenario"),
        "opponent_policies": list(opponent_policies),
        # M2：前缀行为策略装配/执行绑定（对手情景身份 + 根摘要，可事后核对）。
        "prefix_behavior": dict(snapshot.get("prefix_behavior") or {}) or None,
        "focal_seat": focal_seat,
        "seats_order": [0, 1, 2, 3],
        "policy_ids": {
            "baseline_focal": ("fixture-baseline-focal" if fixture_mode
                               else BASELINE_FOCAL_POLICY),
            "candidate_focal": ("fixture-candidate-focal" if fixture_mode
                                else "arm-candidate(注入)"),
            "note": ("夹具演示以脚本行为策略执行" if fixture_mode
                     else "行为/对手策略经 sitin_stage.build_panel_policy 白名单装配"),
        },
        "rule_config": dict(rule_config),
        "declared_endpoint": (snapshot.get("remaining_schedule") or {}).get(
            "declared_endpoint", "stage_complete"),
        "completeness": "complete" if double_arm.get("valid") else "invalid",
        "invalid_reasons": [
            arm["error"] for arm in (double_arm.get("arms") or {}).values() if arm.get("error")
        ],
        "u_or_interval_by_arm": stage_u_by_arm,
        "u_hook": {
            "target": "group_advance_v1",
            "consumer": "C2 tools/sitin_archive（消费 u_or_interval_by_arm/stage_totals）",
            "attachment_point": {
                "stage_net_score_by_arm": stage_net_by_arm,
                "stage_totals_by_participant_by_arm": {
                    name: arm.get("stage_totals_by_participant")
                    for name, arm in (double_arm.get("arms") or {}).items()
                },
                "current_table_final_by_arm": current_final_by_arm,
            },
        },
        "net_score_focal_by_arm": net_by_arm,
        "stage_net_score_focal_by_arm": stage_net_by_arm,
        "current_table_final_by_arm": current_final_by_arm,
        "stage_totals_by_participant_by_arm": {
            name: arm.get("stage_totals_by_participant")
            for name, arm in (double_arm.get("arms") or {}).items()
        },
        "seat_order_scores_final_by_arm": current_final_by_arm,
        "large_settlement_contributions": large_settlements,
        "payments_by_seat_by_arm": payments,
        "elapsed_ms_by_arm": {
            name: arm.get("elapsed_ms") for name, arm in (double_arm.get("arms") or {}).items()
        },
        "degradations": (
            ["fixture_outcome_mapping：终局积分来自夹具选择映射，非规则结算",
             "fixture_policies：对手/基线为脚本行为策略，非真实 H/M 策略强度证据"]
            if fixture_mode else
            ["conditional_prefix：条件截取后的续打（固定行为分布到达条件 C 的效果）"]
        ),
        "tables_executed_by_arm": {
            name: len(arm.get("tables") or [])
            for name, arm in (double_arm.get("arms") or {}).items()
        },
        "actual_rounds_executed_by_arm": rounds_by_arm,
        "actual_table_instances": 0,
        "fixture_table_instances": (len(double_arm.get("arms") or {}) if fixture_mode else 0),
        "partial_table_execution": True,
        "partial_table_note": "条件启动的当前桌（截取时进行中）只执行剩余部分；计一笔部分桌赛执行",
        "prefix_attempts": {
            "total": counters.get("total"),
            "hit": counters.get("hit"),
            "missed": counters.get("missed"),
            "unknown": counters.get("unknown"),
            "errors": counters.get("errors", 0),
            "cap": counters.get("cap"),
            "attempts_exhausted": counters.get("attempts_exhausted"),
        },
        "strength_evidence": False,
    }


def quota_declaration(filled: Optional[Mapping[str, int]] = None) -> Mapping[str, Any]:
    """首版配额声明结构（§7.3）：4 家族 × 2 子场景 × 4 根，H/M 各 2。

    本包只建账结构+夹具演示，不填满配额；roots_filled 如实计数，缺配额不
    伪装完成。
    """
    filled = filled or {}
    rows = []
    for family in FAMILIES:
        for kind in ("open", "cost"):
            sub_scenario = "{0}_{1}".format(family, kind)
            rows.append({
                "sub_scenario": sub_scenario,
                "target_roots": 4,
                "opponent_split": {"H": 2, "M": 2},
                "roots_filled": int(filled.get(sub_scenario, 0)),
                "status": (
                    "partially_filled_fixture_demo" if filled.get(sub_scenario)
                    else "structure_declared_not_filled"
                ),
            })
    return {
        "note": "首版配额为开发分辨起点；本包只建结构+夹具演示，真实前缀填额在批次 7",
        "rows": rows,
    }


# ---------------------------------------------------------------------------
# CLI：build-panel / inspect（参照 sitin_stage 的 argparse/JSON 输出风格）
# ---------------------------------------------------------------------------


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + NEWLINE,
        encoding="utf-8",
    )


def _driver_config() -> MatchDriverConfig:
    from hangma_bot.application.deadline import BudgetPolicy

    return MatchDriverConfig(
        clock_mode="logical",
        # 完整桌（真实引擎/验证替身）需要数百帧（8 单局 × 每局数十窗口）；
        # 旧值 100 只够夹具脚本，真实/替身续打会被步数上限误杀（取合同
        # stop.step_limit 口径 100000）。
        step_limit=100000,
        budget_policy=BudgetPolicy(),
        competition_tournament_id="sitin-opportunities-c1",
    )


def build_panel(
    *,
    prefix_source: str,
    predicate_id: str,
    focal_seat: int,
    opponent_scenario: str,
    root_label: str,
    out_dir: Path,
    ruleset_version: str,
    base_score: int,
    you_cai_bi_kao: bool,
    attempts_cap: int,
    panel_seed: int,
    authorization_token: Optional[Mapping[str, Any]] = None,
    runtime: Optional[Mapping[str, Any]] = None,
    tables_in_stage: int = 2,
    rounds_per_game: int = 8,
    contract_file: Optional[Path] = None,
    candidate_policy: Optional[Any] = None,
) -> Mapping[str, Any]:
    """构造机会面板：场景清单 + 费用账 + 配额声明结构。

    - prefix_source=scripted_fixture：夹具模式（fixture_mode，工具测试/验收），
      零真实桌赛；双臂经完整剩余阶段夹具续打（当前桌 + 剩余桌 + 阶段 U）；
    - prefix_source=v2_behavior：真实路径（需批次 7 授权令牌）；runtime 缺省
      经 build_real_runtime 装配组合根 SimulationEngine（**真实引擎**，不是
      替身）；注入的运行时必须带 runtime_kind 标签，替身只能经显式测试入口
      build_test_runtime_double 装配（fixture 引擎一律拒绝：_forbid_fixture_engine）。
    - 前缀对手行为策略（M2 修复）：按冻结合同情景装配（frozen_generation_policies
      + sitin_stage 白名单）并显式下传；H/M 的装配对象与执行记录逐座位核对，
      身份摘要绑定根摘要写进面板/快照（不再让缺省的「三家 V2」冒充 M 对手）。
    - candidate_policy：候选臂焦点策略（真实路由传入被评候选的
      ActionValuePolicy；缺省用 route_value_seed 种子；夹具路由忽略——夹具臂
      保持脚本行为策略）。
    """
    rule_config = {
        "ruleset_version": ruleset_version,
        "base_score": base_score,
        "you_cai_bi_kao": you_cai_bi_kao,
    }
    rules = HangmaRules(RuleConfig(ruleset_version, base_score, you_cai_bi_kao))
    value_limits = ValueAnalysisLimits()
    contract = {}
    if contract_file is not None:
        contract = json.loads(Path(contract_file).read_text(encoding="utf-8"))
    if contract:
        opponent_names = opponent_policy_names(contract, opponent_scenario)
        tables_in_stage = int(contract.get("group", {}).get("tables_per_group",
                                                           tables_in_stage))
        rounds_per_game = int(contract.get("versions", {}).get("rounds_per_game",
                                                              rounds_per_game))
    else:
        opponent_names = (["weighted_heuristic_v2"] * 3 if opponent_scenario == "H"
                          else ["weighted_heuristic_v2", "weighted_heuristic_v2_white_guard",
                                "weighted_heuristic_v1"])
    fixture_mode = prefix_source == "scripted_fixture"
    # 组合处显式装配运行时（A1）：真实路由缺 runtime 时在此装配**真实**组合根
    # 运行时（不是替身）；注入了 runtime 则必须带装配标签，否则拒绝。
    effective_runtime: Optional[Mapping[str, Any]] = None
    prefix_behavior_policies: Optional[Tuple[Any, Any, Any, Any]] = None
    if not fixture_mode:
        effective_runtime = (
            resolve_declared_runtime(runtime, where="build_panel")
            if runtime is not None else build_real_runtime(
                rules_config=rules.config,
                rounds_per_game=int(rounds_per_game),
                seed=stage.derive_seed(panel_seed, "prefix-runtime", root_label),
                scenario_id=root_label))
        # M2：前缀行为策略从冻结合同情景装配（对手名按座位升序铺开，焦点=V2）。
        prefix_behavior_policies = frozen_generation_policies(
            opponent_names=opponent_names, focal_seat=focal_seat,
            monotonic=lambda: 800.0)
    match_id = "{0}-{1}-match".format(root_label, prefix_source)
    stage_ledger = {
        "completed_table_scores": [],
    }
    remaining_schedule = {
        "declared_endpoint": "stage_complete",
        "remaining_tables_after_current": max(0, int(tables_in_stage) - 1),
        "rounds_per_game": int(rounds_per_game),
        "tables_in_stage": int(tables_in_stage),
    }
    started = time.monotonic()
    snapshot, counters = generate_opportunity(
        prefix_source=prefix_source,
        rules=rules,
        predicate_id=predicate_id,
        focal_seat=focal_seat,
        opponent_scenario=opponent_scenario,
        root_label=root_label,
        match_id=match_id,
        stage_ledger=stage_ledger,
        remaining_schedule=remaining_schedule,
        value_limits=value_limits,
        attempts_cap=attempts_cap,
        authorization_token=authorization_token,
        panel_seed=panel_seed,
        runtime=effective_runtime,
        tournament_config=_snapshot_tournament_config(
            {"rounds_per_game": int(rounds_per_game)}, rules),
        behavior_policies_by_seat=prefix_behavior_policies,
        opponent_names=opponent_names,
        tables_in_stage=int(tables_in_stage),
        rounds_per_game=int(rounds_per_game),
    )
    scenarios: List[Mapping[str, Any]] = []
    cost_records: List[Mapping[str, Any]] = []
    if snapshot is None:
        scenarios.append({
            "sub_scenario": predicate_id,
            "status": "insufficient",
            "reason": "前缀尝试未命中预分配谓词（INSUFFICIENT，不伪装完成）",
        })
    else:
        if fixture_mode:
            opponent = FixtureBehaviorPolicy("fixture-opponent-standin", prefer=("pass",))
            baseline_focal = FixtureBehaviorPolicy("fixture-baseline-focal", prefer=("pass",))
            candidate_focal = FixtureBehaviorPolicy("fixture-candidate-focal", prefer=("peng:5w",))
            by_seat_baseline = [None] * 4
            by_seat_candidate = [None] * 4
            for seat in range(4):
                by_seat_baseline[seat] = baseline_focal if seat == focal_seat else opponent
                by_seat_candidate[seat] = candidate_focal if seat == focal_seat else opponent
        else:
            clock = (lambda: 800.0)
            opponents = [stage.build_panel_policy(name, clock) for name in opponent_names]
            baseline_focal = stage.build_panel_policy(BASELINE_FOCAL_POLICY, clock)
            candidate_focal = (candidate_policy or _panel_candidate_arm_policy(clock))
            by_seat_baseline = [None] * 4
            by_seat_candidate = [None] * 4
            opponent_iter_b = iter(opponents)
            opponent_iter_c = iter(opponents)
            for seat in range(4):
                by_seat_baseline[seat] = (baseline_focal if seat == focal_seat
                                          else next(opponent_iter_b))
                by_seat_candidate[seat] = (candidate_focal if seat == focal_seat
                                           else next(opponent_iter_c))
        double_arm = run_double_arm(
            rules=rules,
            snapshot=snapshot,
            baseline_policies_by_seat=by_seat_baseline,
            candidate_policies_by_seat=by_seat_candidate,
            config=_driver_config(),
            value_limits=value_limits,
            runtime=effective_runtime,
        )
        # P9b：把两臂在截取窗口的动作读数登记到 P9 预留位置
        # （snapshot.window_actions；逐臂读数同时已在 double_arm.arms[*].
        # focal_action_at_cut）。两臂都没有读数时为 None → **不写空壳**，
        # 由 P9 侧按缺读数如实上报 input gap。
        window_actions = double_arm.get("window_actions")
        if window_actions is not None:
            snapshot["window_actions"] = window_actions
        cost_records.append(build_cost_record(
            snapshot=snapshot,
            double_arm=double_arm,
            counters=counters,
            opponent_policies=opponent_names,
            rule_config=rule_config,
            focal_seat=focal_seat,
        ))
        scenarios.append({
            "sub_scenario": predicate_id,
            "status": "sampled" if double_arm.get("valid") else "invalid",
            "source_root_id": snapshot.get("source_root_id"),
            "snapshot": snapshot,
            "double_arm": double_arm,
        })
    filled = {predicate_id: (1 if snapshot is not None else 0)}
    # —— A1：运行时/执行证据一律来自实际装配对象与执行记录 ——
    runtime_kind = str(counters.get("runtime_kind"))
    execution_kind = str(counters.get("execution_kind"))
    engine_kind = str(counters.get("engine_kind"))
    started_instances = int(counters.get("total") or 0)
    real_instances = (started_instances if runtime_kind == RUNTIME_KIND_REAL else 0)
    double_instances = (started_instances
                        if runtime_kind == RUNTIME_KIND_TEST_DOUBLE else 0)
    engine_evidence = (dict((effective_runtime or {}).get("engine_identity") or {})
                       if not fixture_mode else
                       {"class": "ScriptedFixtureEngine", "fixture_mode": True,
                        "engine_version": None})
    prefix_behavior = (dict(snapshot.get("prefix_behavior") or {})
                       if snapshot is not None else None)
    panel = {
        "schema": PANEL_SCHEMA,
        "generator": GENERATOR_SCRIPTED_FIXTURE if prefix_source == "scripted_fixture"
        else GENERATOR_V2_BEHAVIOR,
        "prefix_source": prefix_source,
        "fixture_mode": fixture_mode,
        # engine_kind 由运行时**种类**决定（A1(c)）：显式注入的真实运行时不再被
        # 误标成替身；替身不会被标成真实引擎。execution_kind 是三态执行事实。
        "engine_kind": engine_kind,
        "execution_kind": execution_kind,
        "runtime_kind": runtime_kind,
        "engine_identity": engine_evidence,
        "runtime_assembly": {
            "entry": (str((effective_runtime or {}).get("runtime_entry")) if not fixture_mode
                      else "scripted_fixture_engine"),
            "runtime_kind": runtime_kind,
            "engine_kind": engine_kind,
            "engine_identity": engine_evidence,
            "explicitly_injected": bool(runtime is not None) if not fixture_mode else False,
            "note": ("运行时在组合处装配（A1）：缺省=build_real_runtime 真实组合根"
                     "引擎；替身只能经显式测试入口 build_test_runtime_double"),
        },
        "prefix_behavior": prefix_behavior,
        "selection_eligible": selection_eligible_for(runtime_kind),
        "predicate": predicate_id,
        "focal_seat": focal_seat,
        "opponent_scenario": opponent_scenario,
        "tables_in_stage": int(tables_in_stage),
        "prefix_attempt_cap": PREFIX_ATTEMPT_CAP,
        "prefix_attempt_errors": list(counters.get("attempt_errors") or []),
        "prefix_attempts": {
            "total": counters.get("total"), "hit": counters.get("hit"),
            "missed": counters.get("missed"), "unknown": counters.get("unknown"),
            "errors": counters.get("errors", 0),
            "cap": counters.get("cap"),
            "attempts_exhausted": counters.get("attempts_exhausted"),
        },
        "quota_declaration": quota_declaration(filled),
        "scenarios": scenarios,
        "cost_ledger": cost_records,
        "budget_red_line": {
            # A1：真实桌赛实例数**从执行记录数出来**，不再硬编码 0；替身/夹具
            # 执行时真实桌赛恒 0，替身次数另记 double_table_instances（不混为一谈）。
            "real_table_instances_started": real_instances,
            "double_table_instances": double_instances,
            "fixture_table_instances": sum(
                int(record.get("fixture_table_instances") or 0)
                for record in cost_records
            ),
            "execution_kind": execution_kind,
            "engine_kind": engine_kind,
            "runtime_kind": runtime_kind,
            "table_instance_basis": "前缀生成每次尝试启动 1 个桌赛实例（执行记录 counters.total）",
            "search_ledger_note": (
                "运行时种类 {0}：{1}".format(
                    runtime_kind,
                    "真实组合根引擎执行（真实桌赛实例 {0} 个）".format(real_instances)
                    if runtime_kind == RUNTIME_KIND_REAL else
                    ("验证替身执行（真实桌赛实例 0；替身桌 {0} 个，不得作为强度证据）".format(
                        double_instances) if runtime_kind == RUNTIME_KIND_TEST_DOUBLE
                     else "脚本夹具执行（真实桌赛实例 0）"))
            ),
        },
        "strength_evidence": False,
        "wall_ms_total": round((time.monotonic() - started) * 1000.0, 3),
    }
    write_json(out_dir / "panel.json", panel)
    return panel


def _panel_candidate_arm_policy(clock: Callable[[], float]) -> Any:
    """真实路径候选臂焦点策略：受限执行器装载的 ActionValuePolicy 种子。

    与 offline.evaluate.build_action_value_offline_policy 同一工厂（B3）；
    夹具模式不使用本函数（脚本行为策略替身）。"""
    from hangma_bot.offline.evaluate import build_action_value_offline_policy

    return build_action_value_offline_policy("route_value_seed")



def _iter_keys(payload: Any):
    if isinstance(payload, Mapping):
        for key, value in payload.items():
            yield key
            yield from _iter_keys(value)
    elif isinstance(payload, (list, tuple)):
        for item in payload:
            yield from _iter_keys(item)


def inspect_panel(*, panel_path: Path) -> Mapping[str, Any]:
    """读取场景清单并核对可重建性：重放合法前缀 → 观察摘要一致才通过。

    另核查隐藏信息红线（T09）：面板产物键名不含 WorldState 私有字段名。篡改
    摘要/前缀必须报 problem（fail-closed），不以缺字段静默通过。
    """
    panel = json.loads(panel_path.read_text(encoding="utf-8"))
    if panel.get("schema") != PANEL_SCHEMA:
        raise SystemExit("面板 schema 必须是 {0}".format(PANEL_SCHEMA))
    problems: List[str] = []
    leaked = sorted(set(_iter_keys(panel)) & set(FORBIDDEN_SNAPSHOT_KEYS))
    if leaked:
        problems.append("面板产物含 WorldState 私有字段名（T09 红线）：{0}".format(leaked))
    rules = HangmaRules(RuleConfig(DEFAULT_RULESET_VERSION, 1, False))
    checked = 0
    for scenario in panel.get("scenarios", []):
        snapshot = scenario.get("snapshot")
        if snapshot is None:
            continue
        checked += 1
        try:
            engine, world = rebuild_world(rules=rules, snapshot=snapshot)
            frame = engine.frame(world)
            summary = frame_observation_summary(frame)
            if summary != dict(snapshot.get("observation_summary") or {}):
                problems.append(
                    "快照 {0} 观察摘要不一致（重建失败）".format(snapshot.get("snapshot_id"))
                )
        except Exception as error:
            problems.append(
                "快照 {0} 重建异常 {1}: {2}".format(
                    snapshot.get("snapshot_id"), type(error).__name__, error)
            )
    return {
        "schema": "sitin-opportunity-inspect/1",
        "panel": str(panel_path),
        "snapshots_checked": checked,
        "problems": problems,
        "ok": not problems,
    }


def cmd_build_panel(args: argparse.Namespace) -> int:
    try:
        authorization = None
        if args.v2_authorization:
            authorization = json.loads(Path(args.v2_authorization).read_text(encoding="utf-8"))
        panel = build_panel(
            prefix_source=args.prefix_source,
            predicate_id=args.sub_scenario,
            focal_seat=args.focal_seat,
            opponent_scenario=args.opponent,
            root_label=args.root_label,
            out_dir=Path(args.out),
            ruleset_version=args.ruleset_version,
            base_score=args.base_score,
            you_cai_bi_kao=args.you_cai_bi_kao == "true",
            attempts_cap=args.attempts_cap,
            panel_seed=args.panel_seed,
            authorization_token=authorization,
            contract_file=(Path(args.contract_file) if args.contract_file else None),
            tables_in_stage=int(args.tables_in_stage),
            rounds_per_game=int(args.rounds_per_game),
        )
    except ValueError as error:
        print(json.dumps({"ok": False, "reason": str(error)}, ensure_ascii=False))
        return 2
    print(json.dumps({
        "ok": True,
        "out": str(Path(args.out) / "panel.json"),
        "scenarios": len(panel.get("scenarios", [])),
        "status": panel.get("scenarios", [{}])[0].get("status"),
        "prefix_attempts": panel.get("prefix_attempts"),
        "declared_endpoint": (panel.get("cost_ledger") or [{}])[0].get("declared_endpoint"),
        "real_table_instances_started": 0,
    }, ensure_ascii=False))
    return 0


def cmd_inspect(args: argparse.Namespace) -> int:
    verdict = inspect_panel(panel_path=Path(args.panel))
    write_json(Path(args.out) / "inspect.json", verdict)
    print(json.dumps({
        "ok": verdict["ok"],
        "snapshots_checked": verdict["snapshots_checked"],
        "problems": verdict["problems"],
    }, ensure_ascii=False))
    return 0 if verdict["ok"] else 2


def build_arg_parser() -> argparse.ArgumentParser:
    here = str(Path(__file__).resolve())
    epilog = NEWLINE.join((
        "真实调用示例：",
        "  " + sys.executable + " " + here
        + " build-panel --prefix-source scripted_fixture --sub-scenario branch_open"
        + " --opponent H --focal-seat 0 --out"
        + " review/llm-guided-heuristic-route-2026-09-15/evidence/v4-impl/batch4/demo",
        "  " + sys.executable + " " + here
        + " inspect --panel"
        + " review/llm-guided-heuristic-route-2026-09-15/evidence/v4-impl/batch4/demo/panel.json"
        + " --out review/llm-guided-heuristic-route-2026-09-15/evidence/v4-impl/batch4/demo/inspect",
    ))
    parser = argparse.ArgumentParser(
        description="C1 机会面板构造（legal-prefix-v1）与受控中途续打；"
                    "零真实桌赛实例（搜索账 384/384 已用尽），夹具验收生成器 "
                    + GENERATOR_SCRIPTED_FIXTURE,
        epilog=epilog,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    build = sub.add_parser(
        "build-panel",
        help="生成机会场景清单+费用账（--prefix-source scripted_fixture 为本包验收"
             "模式；v2_behavior 无批次 7 授权令牌直接拒绝）",
    )
    build.add_argument("--prefix-source", choices=PREFIX_SOURCES, default="scripted_fixture")
    build.add_argument("--sub-scenario", default="branch_open",
                       help="预分配主子场景（八谓词之一：{0}）".format("/".join(PREDICATE_IDS)))
    build.add_argument("--opponent", choices=("H", "M"), default="H",
                       help="对手情景（group-dev-v1 合同：H=三家冻结 V2；M=V2/白守/V1 各一）")
    build.add_argument("--focal-seat", type=int, default=0, choices=(0, 1, 2, 3))
    build.add_argument("--root-label", default="fixture-root")
    build.add_argument("--out", required=True)
    build.add_argument("--ruleset-version", default=DEFAULT_RULESET_VERSION)
    build.add_argument("--base-score", type=int, default=1)
    build.add_argument("--you-cai-bi-kao", choices=("true", "false"), default="false")
    build.add_argument("--attempts-cap", type=int, default=PREFIX_ATTEMPT_CAP,
                       help="每子场景前缀尝试上限（合同冻结 256；测试可收紧）")
    build.add_argument("--panel-seed", type=int, default=20260916)
    build.add_argument("--v2-authorization", default=None,
                       help="v2_behavior 的批次 7 预算授权令牌 JSON（当前不存在；"
                            "缺失时该来源直接拒绝）")
    build.add_argument("--contract-file", default=None,
                       help="group-dev-v1 合同 JSON（读对手情景/每阶段桌数/每桌单局数）")
    build.add_argument("--tables-in-stage", type=int, default=2,
                       help="阶段总桌数（group-dev-v1.tables_per_group；缺省 2）")
    build.add_argument("--rounds-per-game", type=int, default=8,
                       help="每桌单局数（冻结配置口径；缺省 8）")
    build.set_defaults(func=cmd_build_panel)

    inspect_parser = sub.add_parser(
        "inspect", help="读场景清单核对可重建性（重放前缀→观察摘要一致才通过）")
    inspect_parser.add_argument("--panel", required=True)
    inspect_parser.add_argument("--out", required=True)
    inspect_parser.set_defaults(func=cmd_inspect)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
