"""杭麻规则深模块公开实现：组装子模块并施加故障隔离与最终复核。

职责（模块 AGENTS.md 主 Agent 独占）：
- 从 `PlayerObservation` 提取机械事实构造 `WindowContext`；
- 先取独立紧急路径，再隔离地执行手牌分析与六动作族生成；
- 应用有财必拷响过滤（special_rules 判定，保守方向宁漏胡不 409）；
- 保证 `RuleAnalysis` 接口不变量（action_key 唯一、紧急候选成员性、
  降级显式可审计）；
- `validate` 以"重新分析 + 候选成员关系"实现单一规则源复核；
- `score` 委托 settlement，爆头/链以 `rule_state` 平台权威状态为准。

故障隔离设计：`hand_analysis` 在方法内延迟导入——该子模块缺失或
import 期损坏时，`analyze` 降级为 RuleIssue（其余候选与紧急路径照常），
而不是整个模块不可用；这与"任一复杂分支异常不得丢失紧急动作"的
模块约束一致。规则依据：`RULES_EVIDENCE.md`（官方指南 v9）。
"""

from __future__ import annotations

from typing import Optional, Tuple

from hangma_bot.kernel.actions import Action, Tile, action_key
from hangma_bot.kernel.config import RuleConfig
from hangma_bot.kernel.observation import PlayerObservation

from . import action_families, settlement, special_rules
from .emergency import emergency_action
from .interface import (
    ActionValidation,
    RuleAnalysis,
    RuleCandidate,
    RuleCompleteness,
    RuleIssue,
    Settlement,
    WinDescription,
)
from .internal_types import TILE_INDEX, WEALTH_CODE, Counts34, WindowContext

# 稳定 RuleIssue.area：与子模块命名（action_families.<族> / hand_analysis / candidate_facts）对齐。
_AREA_CONTEXT = "engine.context"
_AREA_EMERGENCY = "engine.emergency"
_AREA_HAND = "hand_analysis"
_AREA_FAMILY = "action_families"
_AREA_YOUCAI = "special_rules.youcai"
_AREA_FACTS = "candidate_facts"

_DRAW_PHASE = "draw"


class HangmaRules:
    """杭麻合法动作、胡牌、向听、有效牌和结算的唯一规则深模块。"""

    def __init__(self, config: RuleConfig) -> None:
        """把不可变赛事规则绑定到实例；运行中不得替换。"""

        self.config = config

    # ------------------------------------------------------------------
    # analyze：一个动作窗口的完整规则分析
    # ------------------------------------------------------------------

    def analyze(self, observation: PlayerObservation) -> RuleAnalysis:
        """先构造紧急动作，再隔离分析各动作族；不访问网络或时钟。"""

        issues: list = []

        emergency = self._safe_emergency(observation, issues)
        context = self._safe_context(observation, issues)

        candidates: Tuple[RuleCandidate, ...] = ()
        if context is not None:
            hand = self._safe_hand_summary(observation, context, issues)
            try:
                outcome = action_families.generate_candidates(context, hand)
                candidates = outcome.candidates
                issues.extend(outcome.issues)
            except Exception as exc:  # 故障边界：组合器异常不得整体崩溃
                issues.append(
                    RuleIssue(
                        _AREA_FAMILY,
                        "动作族组合器异常: {0}: {1}".format(type(exc).__name__, exc),
                    )
                )
                candidates = ()
            candidates = self._filter_youcai(observation, context, candidates, issues)
            candidates = self._attach_facts(observation, context, candidates, issues)

        candidates = _ensure_emergency_membership(candidates, emergency)

        completeness = (
            RuleCompleteness.DEGRADED if issues else RuleCompleteness.COMPLETE
        )
        return RuleAnalysis(
            legal_candidates=candidates,
            emergency_candidate=emergency,
            completeness=completeness,
            ruleset_version=self.config.ruleset_version,
            issues=tuple(issues),
        )

    def validate(self, observation: PlayerObservation, action: Action) -> ActionValidation:
        """按当前观察重新复核动作；无副作用且不调用官方 API。

        复核语义是"重新分析 + 候选成员关系"：合法候选由同一规则源生成，
        避免在 validate 中出现第二套合法性判断。
        """

        try:
            key = action_key(action)
        except TypeError as exc:
            return ActionValidation(legal=False, reason="未知动作类型: {0}".format(exc))
        analysis = self.analyze(observation)
        if any(candidate.action_key == key for candidate in analysis.legal_candidates):
            return ActionValidation(legal=True, reason=None)
        return ActionValidation(
            legal=False,
            reason=(
                "动作 {0} 不在当前窗口合法候选中（phase={1}, turn={2}, "
                "responding={3}, 候选 {4} 个）".format(
                    key,
                    observation.phase,
                    observation.turn_seat,
                    tuple(observation.responding_seats),
                    len(analysis.legal_candidates),
                )
            ),
        )

    def emergency_action(self, observation: PlayerObservation) -> Optional[RuleCandidate]:
        """以独立最小路径返回过、抓打牌或最右弃牌；不可调用复杂搜索。"""

        return emergency_action(observation)

    def score(self, win: WinDescription) -> Settlement:
        """按绑定规则计算四家结算；不读取运行时外部状态。

        爆头与链计数取 `rule_state` 平台权威状态；链内飘出白板数按
        公共历史 best-effort 推断（settlement.infer_piao_count，【假设】
        口径见 RULES_EVIDENCE §8）。未成胡（分解为空）返回流局口径的
        全零结算，供审计路径防御性调用。
        """

        observation = win.observation
        full_hand = _full_hand(observation)
        meld_count = len(observation.melds[observation.seat])
        split = None
        try:
            from . import hand_analysis

            split = hand_analysis.win_split(full_hand, meld_count)
        except Exception:  # 分解失败按未确认胡处理，不臆造番数
            split = None
        if split is None:
            return Settlement(score_delta=(0, 0, 0, 0), fan=0, details=())

        chain_count = observation.rule_state.chain_count
        piao = settlement.infer_piao_count(
            observation.public_history, observation.seat, chain_count
        )
        return settlement.settle_win(
            split,
            chain_count,
            piao,
            observation.rule_state.baotou,
            self.config.base_score,
            win.winner_seat,
            observation.dealer_seat,
        )

    # ------------------------------------------------------------------
    # 内部装配与故障边界
    # ------------------------------------------------------------------

    def _safe_emergency(
        self, observation: PlayerObservation, issues: list
    ) -> Optional[RuleCandidate]:
        """紧急路径独立可用；其自身异常不得影响候选生成。"""

        try:
            return emergency_action(observation)
        except Exception as exc:
            issues.append(
                RuleIssue(
                    _AREA_EMERGENCY,
                    "紧急路径异常: {0}: {1}".format(type(exc).__name__, exc),
                )
            )
            return None

    def _safe_context(
        self, observation: PlayerObservation, issues: list
    ) -> Optional[WindowContext]:
        """观察 → 机械事实；提取失败时保留紧急路径、放弃候选生成。"""

        try:
            return _build_context(observation)
        except Exception as exc:
            issues.append(
                RuleIssue(
                    _AREA_CONTEXT,
                    "窗口上下文提取异常: {0}: {1}".format(type(exc).__name__, exc),
                )
            )
            return None

    def _safe_hand_summary(
        self,
        observation: PlayerObservation,
        context: WindowContext,
        issues: list,
    ):
        """摸牌出牌窗口才需要手牌分析；失败降级为 None（胡族保守降级）。"""

        if not _is_own_draw(context):
            return None
        try:
            from . import hand_analysis

            return hand_analysis.analyse_hand(
                context.full_hand(), len(observation.melds[observation.seat])
            )
        except Exception as exc:
            issues.append(
                RuleIssue(
                    _AREA_HAND,
                    "手牌分析异常: {0}: {1}".format(type(exc).__name__, exc),
                )
            )
            return None

    def _filter_youcai(
        self,
        observation: PlayerObservation,
        context: WindowContext,
        candidates: Tuple[RuleCandidate, ...],
        issues: list,
    ) -> Tuple[RuleCandidate, ...]:
        """有财必拷响：手留财神且非爆头/杠上摸牌时排除胡候选（§7）。

        保守方向：宁漏胡不 409；判定委托 special_rules，被排除时记录
        RuleIssue 而非静默丢弃。
        """

        if not self.config.you_cai_bi_kao:
            return candidates
        if not any(candidate.action_key == "hu" for candidate in candidates):
            return candidates
        whites_held = sum(
            1 for tile in _full_hand(observation) if tile.code == WEALTH_CODE
        )
        if whites_held == 0:
            return candidates
        try:
            from . import hand_analysis

            split = hand_analysis.win_split(
                _full_hand(observation), len(observation.melds[observation.seat])
            )
        except Exception as exc:
            issues.append(
                RuleIssue(
                    _AREA_YOUCAI,
                    "有财必拷响判定所需分解异常: {0}: {1}".format(
                        type(exc).__name__, exc
                    ),
                )
            )
            split = None
        if split is None:
            issues.append(
                RuleIssue(
                    _AREA_YOUCAI,
                    "有财必拷响：手留财神 {0} 张但无法确认爆头/杠开，保守排除胡候选（§7）".format(
                        whites_held
                    ),
                )
            )
            return tuple(c for c in candidates if c.action_key != "hu")
        block = special_rules.you_cai_bi_kao_block(
            True,
            split,
            observation.rule_state.baotou,
            special_rules.is_gang_draw(
                observation.public_history, observation.seat
            ),
        )
        if block is None:
            return candidates
        issues.append(RuleIssue(_AREA_YOUCAI, block))
        return tuple(c for c in candidates if c.action_key != "hu")

    def _attach_facts(
        self,
        observation: PlayerObservation,
        context: WindowContext,
        candidates: Tuple[RuleCandidate, ...],
        issues: list,
    ) -> Tuple[RuleCandidate, ...]:
        """给合法候选附加动作后牌效事实（契约 §4.1）；失败兜底为未生产。

        事实模块延迟导入（与 hand_analysis 同一故障隔离思路）：模块缺失
        或整体异常时保留原候选（facts=None）并记 RuleIssue——消费方按
        未知处理，不影响候选合法性与紧急路径。单个候选的分析失败由
        candidate_facts 内部收敛为 ANALYSIS_FAILED 事实与对应 Issue。
        """

        try:
            from . import candidate_facts

            attached, fact_issues = candidate_facts.attach_facts(
                context,
                _public_counts(observation),
                len(observation.melds[observation.seat]),
                candidates,
            )
        except Exception as exc:
            issues.append(
                RuleIssue(
                    _AREA_FACTS,
                    "牌效事实生产异常: {0}: {1}".format(type(exc).__name__, exc),
                )
            )
            return candidates
        issues.extend(fact_issues)
        return attached


# ---------------------------------------------------------------------------
# 纯装配助手
# ---------------------------------------------------------------------------


def _build_context(observation: PlayerObservation) -> WindowContext:
    """从观察提取动作族生成所需机械事实（信息权限不变）。

    副露种类按 kernel 约定（`PublicMeld.kind` 为 chi/peng/gang 前缀
    字符串，适配器负责映射）统计：吃次数用于两摊上限，碰牌值用于补杠。
    """

    seat = observation.seat
    my_melds = observation.melds[seat]
    chi_count = sum(1 for meld in my_melds if meld.kind.startswith("chi"))
    peng_codes = tuple(
        meld.tiles[0].code for meld in my_melds if meld.kind.startswith("peng")
    )
    return WindowContext(
        seat=seat,
        phase=observation.phase,
        turn_seat=observation.turn_seat,
        responding_seats=tuple(observation.responding_seats),
        hand_tiles=tuple(observation.my_hand),
        drawn_tile=observation.drawn_tile,
        my_chi_count=chi_count,
        my_peng_codes=peng_codes,
        last_discard=observation.last_discard,
        catch_play=observation.rule_state.catch_play,
        remaining_tile_count=observation.remaining_tile_count,
    )


def _public_counts(observation: PlayerObservation) -> Counts34:
    """四家牌河与副露的 34 维可见牌计数（牌效事实的剩余张数口径）。

    只统计公开可见的牌：本人视角合法；不含他家手牌与牌墙。
    """

    counts = [0] * 34
    for river in observation.discards:
        for tile in river:
            counts[TILE_INDEX[tile.code]] += 1
    for seat_melds in observation.melds:
        for meld in seat_melds:
            for tile in meld.tiles:
                counts[TILE_INDEX[tile.code]] += 1
    return tuple(counts)


def _is_own_draw(context: WindowContext) -> bool:
    """本人摸牌出牌窗口（与 action_families._own_draw 同语义的机械判定）。"""

    return context.phase == _DRAW_PHASE and context.turn_seat == context.seat


def _full_hand(observation: PlayerObservation) -> Tuple[Tile, ...]:
    """暗牌全集 = 手牌 + 刚摸牌；保留官方顺序，摸牌置尾。"""

    if observation.drawn_tile is None:
        return tuple(observation.my_hand)
    return tuple(observation.my_hand) + (observation.drawn_tile,)


def _ensure_emergency_membership(
    candidates: Tuple[RuleCandidate, ...], emergency: Optional[RuleCandidate]
) -> Tuple[RuleCandidate, ...]:
    """接口不变量：紧急候选存在时必须出现在合法候选中。

    紧急路径按最小规则构造（响应过 / 抓打牌 / 官方顺序最右一张），
    其合法性由构造保证；正常情况下动作族已包含同一候选，此函数只在
    出牌族整体降级等边界补齐成员关系。
    """

    if emergency is None:
        return candidates
    if any(candidate.action_key == emergency.action_key for candidate in candidates):
        return candidates
    return candidates + (emergency,)
