"""VIP 人工联合启发式种子与失败显式的独立研究包装。

排名点是候选内的无量纲启发式；当前胡的实际支付先按底分归一化，再经
同一候选公式变换。未知杠补按条件分支下端与改善码宽度比较，不挑最好
未来牌、不以公开容量除墙余伪造概率。线上外部接缝仍只有 choose。
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Mapping, Optional

from hangma_bot.hangma import hand_analysis, route_transition
from hangma_bot.hangma.interface import RuleCompleteness
from hangma_bot.hangma.natural_preparation import (
    NATURAL_PREPARATION_SEMANTICS_VERSION, analyze_natural_set_preparation,
)
from hangma_bot.hangma.route_hu_witness import analyze_waiting_hu_witness
from hangma_bot.hangma.route_structure import (
    ROUTE_STRUCTURE_SCHEMA_VERSION, analyze_route_structure,
)
from hangma_bot.hangma.route_transition import ConditionalPhase
from hangma_bot.kernel.actions import (
    CANONICAL_TILE_ORDER, Chi, Discard, Gang, Hu, Pass, Peng, Tile,
)
from hangma_bot.kernel.config import RuleConfig

from .action_value import STATUS_SCORED
from .action_value_executor import (
    ActionValueExecutor, EXECUTOR_VERSION, MAX_SUPPORTED_LOCAL_COLLECTION_SIZE, WorkloadExceeded,
)
from .errors import PolicyError
from .interface import DecisionBudget, DecisionPlan, DecisionRequest, RankedCandidate, ScorePart
from .route_heuristic_view import (
    VIP_ROUTE_CANDIDATE_KIND, VIP_ROUTE_SCORING_VIEW_SCHEMA_VERSION,
    VIP_ROUTE_TRACE_SCHEMA_VERSION, VIP_NORMAL_DRAW_HU_PAYMENT_SEMANTICS_VERSION,
    RouteConditionalHuPayment, RouteHeuristicAction, RouteHeuristicNode,
    RouteWaitingView, VipRouteScoringView,
)
from .safe_fallback import SafeFallbackPolicy


def _counts_from_visible_tiles(tiles: tuple[Tile, ...]) -> tuple[int, ...]:
    """仅把本座已知实体转为规范计数；不实现规则或访问内部规则类型。"""

    indexes = {code: index for index, code in enumerate(CANONICAL_TILE_ORDER)}
    counts = [0] * len(CANONICAL_TILE_ORDER)
    for tile in tiles:
        counts[indexes[tile.code]] += 1
    return tuple(counts)


VIP_ROUTE_HEURISTIC_SEED_SOURCE = '''
def waiting_score(waiting, context_adjustment):
    structure = waiting["structure"]
    standard = structure["standard_shanten"]
    seven = structure["seven_pairs_shanten"]
    shanten = standard if seven is None else min(standard, seven)
    ordinary_width = waiting["useful_code_width"]
    hu_width = waiting["legal_hu_code_width"]
    backup = 0.0
    for target, width in zip(structure["targets"], waiting["target_improvement_code_widths"]):
        if target["target_stage"] == "waiting_predecessor":
            proposal = 3.0 - 1.4 * target["natural_need"]
            proposal += 0.04 * width
            proposal -= 0.7 * target["target_white_discard_lower_bound"]
            proposal -= 0.25 * target["target_natural_discard_lower_bound"]
            backup = max(backup, proposal)
    # 两种牌型共有码只计并集；五自然对只是有界经验奖励，不过滤四对两白。
    natural_pairs = 0.7 * min(2, max(0, structure["natural_pair_count"] - 4))
    chain = min(2.0, 0.5 * waiting["chain_count"]) if waiting["baotou"] else 0.0
    return 20.0 - 4.0 * shanten + 0.10 * ordinary_width + 0.08 * hu_width + backup + natural_pairs + chain + context_adjustment

def score_actions(view):
    context = view["visible_state"]
    wall = context["remaining_tile_count"]
    late = 0.0 if wall is None else 0.2 * max(0, 35 - wall)
    opponents = sum([len(melds) for seat, melds in enumerate(context["melds"]) if seat != context["seat"]])
    dealer = 0.25 if context["seat"] == context["dealer_seat"] else 0.0
    context_adjustment = dealer - late - 0.10 * opponents
    node_indexes = {node["node_key"]: index for index, node in enumerate(view["nodes"])}
    values = []
    chosen = []
    for node in view["nodes"]:
        kind = node["kind"]
        key = node["node_key"]
        if kind == "wait":
            value = waiting_score(node["waiting"], context_adjustment)
            selected = key
        elif kind == "unknown_draw":
            # 真正补牌前结构的保守代理；不声称已知补牌后最好合法动作。
            value = waiting_score(node["waiting"], context_adjustment) - 3.0
            selected = key
        elif kind == "hu":
            normalized = node["settlement"]["score_delta"][context["seat"]] / view["binding"]["base_score"]
            value = 23.0 + 8.0 * normalized / (6.0 + abs(normalized))
            selected = key
        elif kind == "choices":
            best = node["children"][0]
            for child in node["children"]:
                if values[node_indexes[child]] > values[node_indexes[best]]:
                    best = child
            value = values[node_indexes[best]]
            selected = chosen[node_indexes[best]]
        else:
            # 全相容补牌码下端；码宽度仅是启发式，不是概率或积分下界。
            lower = min([values[node_indexes[child]] for child in node["children"]])
            if kind == "replacement":
                improvements = sum([1 for child in node["children"] if values[node_indexes[child]] > lower + 1.0])
                value = lower + 0.06 * improvements
            else:
                value = lower
            selected = key
        values.append(value)
        chosen.append(selected)
    entries = []
    for action in view["actions"]:
        key = action["node_key"]
        entries.append({"action_key": action["action_key"], "score": values[node_indexes[key]], "trace": {
            "unit": "heuristic_rank_points", "selected_conditional_node": chosen[node_indexes[key]],
            "root_condition": action["pending_condition"], "formula": "vip_balanced_seed/1",
        }})
    return {"status": "SCORED", "entries": entries}
'''


class RouteHeuristicResearchError(PolicyError):
    """严格研发未完成原因；合法保底已备好也不能把本次记为成功。"""

    def __init__(self, category: str, reason: str, *, action_key: Optional[str] = None) -> None:
        self.category = category
        self.reason = reason
        self.action_key = action_key
        super().__init__(f"VIP {category} [{action_key or 'request'}]: {reason}")


@dataclass(frozen=True)
class VipRouteProjectionLimits:
    """整次第一方事实展开上限，不代替候选100,000计数操作限额。"""

    max_nodes: int = 4096
    max_branches: int = 16384
    max_waiting_draw_witnesses: int = 16384

    def __post_init__(self) -> None:
        if any(type(value) is not int or value <= 0 for value in (
            self.max_nodes, self.max_branches, self.max_waiting_draw_witnesses,
        )):
            raise ValueError("VIP展开上限必须为正整数")
        if self.max_nodes > MAX_SUPPORTED_LOCAL_COLLECTION_SIZE:
            raise ValueError("VIP节点上限不能超过受限执行器16384项硬容量")


class _Projection:
    """仅一次请求内的条件图构造，不留跨请求可变事实缓存。"""

    def __init__(self, request: DecisionRequest, config: RuleConfig,
                 limits: VipRouteProjectionLimits) -> None:
        self.request = request
        self.config = config
        self.limits = limits
        self.nodes: list[RouteHeuristicNode] = []
        self.branch_count = 0
        self.witness_count = 0
        self.target_distance_count = 0
        self.waiting_cache: dict[tuple, RouteWaitingView] = {}
        self.semantic_nodes: dict[tuple, str] = {}

    @staticmethod
    def code_width(codes, state) -> int:
        """计数去重的公开相容码；保守零仅是下界，不能当已耗尽。"""

        possible = set(_Projection.compatible_codes(state))
        return len(set(codes) & possible)

    def add(self, key: str, kind: str, *, children=(), codes=(), waiting=None,
            settlement=None, pending=None, uncertainty=None, legal_action_key=None,
            followup_key=None) -> str:
        # 同一请求中只复用整个冻结节点事实，不能只按手牌合并。条件边的
        # 顺序和重复引用均保留，故补牌码及互斥包络的权重没有被去重。
        # node_key只是引用名称；合法动作、跟打身份和未知说明都参与比较。
        semantic = (kind, tuple(children), tuple(codes), waiting, settlement,
                    pending, uncertainty, legal_action_key, followup_key)
        existing = self.semantic_nodes.get(semantic)
        if existing is not None:
            return existing
        self.branch_count += len(children)
        if len(self.nodes) >= self.limits.max_nodes or self.branch_count > self.limits.max_branches:
            raise RouteHeuristicResearchError("SEARCH_TRUNCATED", "VIP条件图展开达到冻结工作量上限")
        self.nodes.append(RouteHeuristicNode(
            key, kind, tuple(children), tuple(codes), waiting, settlement, pending,
            len(children), len(children), uncertainty_reason=uncertainty,
            legal_action_key=legal_action_key, followup_key=followup_key,
        ))
        self.semantic_nodes[semantic] = key
        return key

    @staticmethod
    def compatible_codes(state) -> tuple[str, ...]:
        if state.unseen_capacities is None or state.unseen_evidence is None:
            raise RouteHeuristicResearchError("INPUT_EVIDENCE_GAP", "条件状态缺规范公开容量或证据")
        held = _counts_from_visible_tiles(state.concealed)
        return tuple(code for index, code in enumerate(CANONICAL_TILE_ORDER)
                     if held[index] < 4 and (
                         state.unseen_evidence[index] != "exact"
                         or state.unseen_capacities[index] is None
                         or state.unseen_capacities[index] > 0))

    def waiting(self, state, *, qualification: bool = True) -> RouteWaitingView:
        counts = _counts_from_visible_tiles(state.concealed)
        if sum(counts) != 13 - 3 * state.meld_count:
            raise RouteHeuristicResearchError("MECHANICAL_GAP", "等待态暗牌数量未守恒")
        key = (counts, state.meld_count, state.baotou, state.chain_count,
               state.chain_piao, state.wall_remaining, state.unseen_capacities,
               state.unseen_evidence, state.phase, qualification)
        cached = self.waiting_cache.get(key)
        if cached is not None:
            return cached
        codes = self.compatible_codes(state)
        structure = analyze_route_structure(counts, state.meld_count)
        self.target_distance_count += structure.target_distance_evaluation_count
        preparation = analyze_natural_set_preparation(counts, state.meld_count)
        self.target_distance_count += preparation.target_distance_evaluation_count
        summary = hand_analysis.analyse_hand(state.concealed, state.meld_count)
        if summary.shanten < 0:
            raise RouteHeuristicResearchError("MECHANICAL_GAP", "等待态真实向听不能是已胡-1")
        combined_codes = tuple(tile.code for tile in summary.useful_tiles)
        standard_codes = tuple(tile.code for tile in summary.standard_useful_tiles or ())
        seven_codes = (tuple(tile.code for tile in summary.seven_pairs_useful_tiles)
                       if summary.seven_pairs_useful_tiles is not None else None)
        union_set = set(standard_codes) | set(seven_codes or ()) | set(combined_codes)
        union_codes = tuple(code for code in CANONICAL_TILE_ORDER if code in union_set)
        known_hu: set[str] = set()
        hu_by_scope: dict[bool, set[str]] = {False: set(), True: set()}
        payments: list[RouteConditionalHuPayment] = []
        unknown: list[str] = []
        if qualification and state.wall_remaining is None:
            raise RouteHeuristicResearchError("INPUT_EVIDENCE_GAP", "终点胡条件见证缺墙余")
        if qualification and state.wall_remaining > 20:
            for code in codes:
                # 未列为真实一步推进的码不能从等待态直接成胡；这只省掉
                # 已被同源手牌数学关闭的胡资格查询，不删除任何根或杠补续行。
                if code not in combined_codes:
                    continue
                index = CANONICAL_TILE_ORDER.index(code)
                if state.unseen_evidence[index] != "exact" or state.unseen_capacities[index] is None:
                    unknown.append(code)
                    continue
                for restricted in (False, True):
                    self.witness_count += 1
                    if self.witness_count > self.limits.max_waiting_draw_witnesses:
                        raise RouteHeuristicResearchError("SEARCH_TRUNCATED", "终点胡条件见证达到冻结上限")
                    analysis = analyze_waiting_hu_witness(
                        state, Tile(code), wall_remaining_before_draw=state.wall_remaining,
                        catch_restricted=restricted, config=self.config,
                    )
                    if analysis.issues:
                        raise RouteHeuristicResearchError("MECHANICAL_GAP", "; ".join(issue.reason for issue in analysis.issues))
                    if analysis.legal_hu:
                        if analysis.immediate_settlement is None:
                            raise RouteHeuristicResearchError("INPUT_EVIDENCE_GAP", "给定摸牌合法胡缺结算")
                        known_hu.add(code)
                        hu_by_scope[restricted].add(code)
                        # 保留本次已算的窄见证，不再求解或调用规则。两抓打
                        # 假设分别记录，支付只在给定下一次普通摸牌发生时成立。
                        payments.append(RouteConditionalHuPayment(
                            draw_code=code, catch_restricted=restricted,
                            wall_remaining_before_draw=analysis.wall_remaining_before_draw,
                            wall_remaining_after_draw=analysis.wall_remaining_after_draw,
                            draw_capacity_before=analysis.draw_capacity_before,
                            draw_capacity_after=analysis.draw_capacity_after,
                            baotou_after_draw=analysis.baotou_after_draw,
                            chain_count=state.chain_count, chain_piao=state.chain_piao,
                            winner_seat=state.seat, dealer_seat=state.dealer_seat,
                            ruleset_version=analysis.ruleset_version,
                            settlement=analysis.immediate_settlement,
                        ))
        result = RouteWaitingView(
            structure=structure, useful_codes=union_codes,
            unseen_capacities=state.unseen_capacities,
            unseen_evidence=state.unseen_evidence,
            legal_hu_draw_codes=(tuple(code for code in CANONICAL_TILE_ORDER if code in known_hu)
                                if qualification else None),
            qualification_scope="conditional_witness" if qualification else "unanalysed",
            normal_draw_hu_payments=tuple(payments) if qualification else None,
            natural_preparation=preparation,
            natural_preparation_code_width=self.code_width(preparation.natural_need_improvement_codes, state),
            qualification_missing_reason=None if qualification else "补牌码公开容量未知，保留真实补牌前结构",
            qualification_unknown_codes=tuple(unknown) if qualification else codes,
            qualification_math_closed_codes=tuple(code for code in codes if code not in combined_codes)
            if qualification else (),
            restricted_hu_draw_codes=tuple(code for code in CANONICAL_TILE_ORDER if code in hu_by_scope[True]),
            unrestricted_hu_draw_codes=tuple(code for code in CANONICAL_TILE_ORDER if code in hu_by_scope[False]),
            useful_code_width=self.code_width(union_codes, state),
            legal_hu_code_width=self.code_width(known_hu, state),
            target_improvement_code_widths=tuple(self.code_width(
                target.conditional_need_improvement_codes, state) for target in structure.targets),
            standard_useful_codes=standard_codes, seven_pairs_useful_codes=seven_codes,
            combined_useful_codes=combined_codes,
            baotou=state.baotou, chain_count=state.chain_count,
        )
        self.waiting_cache[key] = result
        return result

    def action_choices(self, analysis, key: str, *, followup_keys=None) -> str:
        if analysis.issues or not analysis.legal_candidates:
            raise RouteHeuristicResearchError("MECHANICAL_GAP", "给定条件后的合法续行缺失或有规则问题")
        children = []
        for candidate in sorted(analysis.legal_candidates, key=lambda item: item.action_key):
            child = key + "/" + candidate.action_key
            if isinstance(candidate.action, Hu):
                if analysis.immediate_settlement is None:
                    raise RouteHeuristicResearchError("INPUT_EVIDENCE_GAP", "合法条件胡缺同源结算")
                children.append(self.add(child, "hu", settlement=analysis.immediate_settlement,
                                         legal_action_key=candidate.action_key))
            elif isinstance(candidate.action, Discard):
                apply = (route_transition.apply_legal_claim_discard
                         if isinstance(analysis, route_transition.GivenClaimAnalysis)
                         else route_transition.apply_legal_draw_discard)
                state = apply(analysis, candidate.action_key)
                children.append(self.add(
                    child, "wait", waiting=self.waiting(state),
                    legal_action_key=candidate.action_key,
                    followup_key=(followup_keys or {}).get(candidate.action_key),
                ))
            elif isinstance(candidate.action, Gang):
                state = route_transition.apply_legal_followup_gang(analysis, candidate.action_key)
                children.append(self.replacement(state, child))
            else:
                raise RouteHeuristicResearchError("MECHANICAL_GAP", "本人动作暂态出现未知续行族")
        return self.add(key, "choices", children=children, pending="given_condition_legal_action")

    def replacement(self, state, key: str) -> str:
        if state.phase is not ConditionalPhase.REPLACEMENT_DRAW or state.structural_only:
            raise RouteHeuristicResearchError("MECHANICAL_GAP", "补牌根未通过条件裁决或来源不符")
        if state.wall_remaining is None:
            raise RouteHeuristicResearchError("INPUT_EVIDENCE_GAP", "合法杠缺墙余")
        if state.wall_remaining <= 20:
            raise RouteHeuristicResearchError("MECHANICAL_GAP", "规则确认杠后却不能补牌")
        codes = self.compatible_codes(state)
        if not codes:
            raise RouteHeuristicResearchError("MECHANICAL_GAP", "合法杠没有公开相容补牌码")
        children = []
        for code in codes:
            child = key + "/draw:" + code
            index = CANONICAL_TILE_ORDER.index(code)
            if state.unseen_evidence[index] != "exact" or state.unseen_capacities[index] is None:
                children.append(self.add(
                    child, "unknown_draw", waiting=self.waiting(state, qualification=False),
                    pending="replacement_draw:" + code,
                    uncertainty="公开容量非精确，尚未给定此补牌及资格；不删除相容码",
                ))
                continue
            landed = route_transition.apply_given_draw(state, Tile(code), replacement=True)
            analysis = route_transition.analyze_given_replacement_draw(
                landed, seat=self.request.observation.seat,
                dealer_seat=self.request.observation.dealer_seat, config=self.config,
            )
            children.append(self.action_choices(analysis, child))
        return self.add(key, "replacement", children=children, codes=codes, pending="unknown_replacement_draw")

    def claim_success(self, root, candidate):
        observation = self.request.observation
        trigger = observation.last_discard
        if trigger is None:
            raise RouteHeuristicResearchError("INPUT_EVIDENCE_GAP", "鸣牌根缺触发弃牌")
        choices = tuple((seat, candidate.action if seat == observation.seat else Pass())
                        for seat in observation.responding_seats)
        awarded = route_transition.advance_given_response(
            root, window=observation.phase, discard_seat=trigger.seat,
            discarded_tile=trigger.tile, responding=observation.responding_seats,
            choices=choices, retained_in_river=False,
        )
        if awarded.gap_kinds or not awarded.state.claim_awarded:
            raise RouteHeuristicResearchError("MECHANICAL_GAP", "本家鸣牌及其他响应过牌的显式条件未能获裁决")
        return awarded.state


def build_vip_route_scoring_view(
    request: DecisionRequest, config: RuleConfig, *,
    limits: Optional[VipRouteProjectionLimits] = None,
) -> VipRouteScoringView:
    """投影同次全部合法根；正常机械缺口抛错，未知未来保持条件。

    所有合法根先分析、评分，再在严格包装中过滤明确拒绝项。吃碰的成功
    前缀明示“本家鸣牌、其他响应过牌、领取移河”，实际获裁决后仍须以
    新权威观察重新评分，旧跟打节点从不成为可盲执行的动作计划。
    """

    rules = request.rules
    if config.ruleset_version != rules.ruleset_version:
        raise RouteHeuristicResearchError("INPUT_EVIDENCE_GAP", "实际RuleConfig与规则分析版本不一致")
    if config.base_score != 1 or config.you_cai_bi_kao:
        raise RouteHeuristicResearchError("INPUT_EVIDENCE_GAP", "条件机械首版仅支持BaseScore=1、YouCaiBiKao=false")
    if rules.completeness is not RuleCompleteness.COMPLETE:
        raise RouteHeuristicResearchError("RULES_DEGRADED", "; ".join(issue.reason for issue in rules.issues))
    roots = rules.conditional_roots
    keys = tuple(item.action_key for item in rules.legal_candidates)
    if roots is None:
        raise RouteHeuristicResearchError("INPUT_EVIDENCE_GAP", "未请求同次全合法条件根")
    if not keys or len(set(keys)) != len(keys) or tuple(root.action_key for root in roots) != keys:
        raise RouteHeuristicResearchError("MECHANICAL_GAP", "条件根与同次全部合法动作未一一对应")
    emergency = rules.emergency_candidate
    if emergency is None or emergency.action_key not in keys:
        raise RouteHeuristicResearchError("MECHANICAL_GAP", "研究入口启动前未备好合法规则紧急动作")
    projection = _Projection(request, config, limits or VipRouteProjectionLimits())
    actions = []
    for candidate, root in sorted(zip(rules.legal_candidates, roots), key=lambda row: row[0].action_key):
        key = candidate.action_key
        if root.gap_kind is not None or root.gap_kinds:
            category = root.gap_kind.name if root.gap_kind is not None else root.gap_kinds[0].name
            raise RouteHeuristicResearchError(category, "; ".join(issue.reason for issue in root.issues), action_key=key)
        states = tuple(branch.state for branch in root.branches) + tuple(
            state for state in (root.claim_state, root.proposal_state) if state is not None)
        if any(state.identity is None or state.identity.ruleset_version != config.ruleset_version
               or state.identity.root_action_key != key
               or state.identity.game_id != request.observation.game_id
               or state.identity.round_no != request.observation.round_no
               or state.seat != request.observation.seat
               or state.dealer_seat != request.observation.dealer_seat
               or state.root_public_view is None
               or state.root_public_view.snapshot_seq != request.observation.snapshot_seq
               or state.local_witness_only for state in states):
            raise RouteHeuristicResearchError("INPUT_EVIDENCE_GAP", "条件根身份、座位或规则绑定不一致", action_key=key)
        try:
            if isinstance(candidate.action, Hu):
                if root.settlement is None or root.pending_condition is not None:
                    raise RouteHeuristicResearchError("MECHANICAL_GAP", "当前胡缺同源即时结算", action_key=key)
                node = projection.add(key, "hu", settlement=root.settlement)
                kind = "hu"
            elif isinstance(candidate.action, (Chi, Peng)):
                state = projection.claim_success(root, candidate)
                analysis = route_transition.analyze_given_claim_action(
                    state, seat=request.observation.seat, config=config)
                facts = candidate.facts
                if facts is None or facts.followup_branches is None:
                    raise RouteHeuristicResearchError("MECHANICAL_GAP", "吃碰缺完整同次跟打身份", action_key=key)
                followup_keys = {"discard:" + branch.followup_discard: branch.followup_key
                                 for branch in facts.followup_branches}
                actual = {item.action_key for item in analysis.legal_candidates if isinstance(item.action, Discard)}
                if actual != set(followup_keys):
                    raise RouteHeuristicResearchError("MECHANICAL_GAP", "吃碰条件续行与同次全部合法弃牌不一致", action_key=key)
                node = projection.action_choices(analysis, key, followup_keys=followup_keys)
                kind = "chi" if isinstance(candidate.action, Chi) else "peng"
            elif isinstance(candidate.action, Gang):
                if len(root.branches) != 1:
                    raise RouteHeuristicResearchError("MECHANICAL_GAP", "合法杠缺唯一待补牌状态", action_key=key)
                state = (projection.claim_success(root, candidate) if root.proposal_state is not None
                         else root.branches[0].state)
                node = projection.replacement(state, key)
                kind = "gang"
            elif isinstance(candidate.action, (Discard, Pass)):
                if len(root.branches) != 1:
                    raise RouteHeuristicResearchError("MECHANICAL_GAP", "弃牌/过牌缺唯一等待状态", action_key=key)
                node = projection.add(key, "wait", waiting=projection.waiting(root.branches[0].state))
                kind = "discard" if isinstance(candidate.action, Discard) else "pass"
            else:
                raise RouteHeuristicResearchError("MECHANICAL_GAP", "未知合法根动作族", action_key=key)
        except RouteHeuristicResearchError:
            raise
        except (ValueError, TypeError, KeyError) as exc:
            raise RouteHeuristicResearchError("MECHANICAL_GAP", str(exc), action_key=key) from exc
        pending = ("claim_awarded_if_own_claim_others_pass_and_removed_from_river"
                   if isinstance(candidate.action, (Chi, Peng)) or root.proposal_state is not None
                   and isinstance(candidate.action, Gang)
                   else root.pending_condition.value if root.pending_condition is not None else None)
        skipped = ((request.observation.seat - request.observation.last_discard.seat - 1) % 4
                   if isinstance(candidate.action, (Chi, Peng)) or root.proposal_state is not None
                   and isinstance(candidate.action, Gang) else 0)
        actions.append(RouteHeuristicAction(key, candidate.action, kind, node, pending, skipped))
    return VipRouteScoringView(
        schema_version=VIP_ROUTE_SCORING_VIEW_SCHEMA_VERSION,
        visible_state=request.observation, actions=tuple(actions), nodes=tuple(projection.nodes),
        ruleset_version=config.ruleset_version, base_score=config.base_score,
        you_cai_bi_kao=config.you_cai_bi_kao,
        structure_semantics_version=ROUTE_STRUCTURE_SCHEMA_VERSION,
        normal_draw_hu_payment_semantics_version=VIP_NORMAL_DRAW_HU_PAYMENT_SEMANTICS_VERSION,
        natural_preparation_semantics_version=NATURAL_PREPARATION_SEMANTICS_VERSION,
        executor_version=EXECUTOR_VERSION,
        max_nodes=projection.limits.max_nodes, max_branches=projection.limits.max_branches,
        max_waiting_draw_witnesses=projection.limits.max_waiting_draw_witnesses,
        waiting_draw_witness_count=projection.witness_count,
        target_distance_evaluation_count=projection.target_distance_count,
    )


def compute_vip_candidate_identity(
    source: str, contract_sha256: str, deps_digest: str,
    params: Optional[Mapping[str, Any]] = None,
) -> str:
    """新种类的源码身份；离线调用方须提供真实合同与完整依赖文件摘要。"""

    if not isinstance(source, str) or not contract_sha256 or not deps_digest:
        raise ValueError("VIP候选身份必须提供源码、合同摘要和第一方依赖摘要")
    payload = {
        "candidate_kind": VIP_ROUTE_CANDIDATE_KIND,
        "source": source,
        "contract_sha256": contract_sha256,
        "deps_digest": deps_digest,
        "params": dict(params or {}),
        "view_schema_version": VIP_ROUTE_SCORING_VIEW_SCHEMA_VERSION,
        "structure_semantics_version": ROUTE_STRUCTURE_SCHEMA_VERSION,
        "normal_draw_hu_payment_semantics_version": VIP_NORMAL_DRAW_HU_PAYMENT_SEMANTICS_VERSION,
        "natural_preparation_semantics_version": NATURAL_PREPARATION_SEMANTICS_VERSION,
        "executor_version": EXECUTOR_VERSION,
    }
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()


class RouteVipHeuristicPolicy:
    """严格离线研究策略；所有评分异常显式未完成，不补分、不自动回退。

    ``emergency_policy`` 为未来部署提供独立规则保底。研究choose启动时先
    备好该保底，但只返回成功评分的全合法计划；首选碰巧与保底同键不算
    回退。不能把本类型未经运行门验证装入生产组合根。
    """

    name = VIP_ROUTE_CANDIDATE_KIND

    def __init__(self, config: RuleConfig, *, source: str = VIP_ROUTE_HEURISTIC_SEED_SOURCE,
                 max_operations: int = 100_000,
                 projection_limits: Optional[VipRouteProjectionLimits] = None) -> None:
        self.config = config
        self.projection_limits = projection_limits or VipRouteProjectionLimits()
        # 候选必须能为声明的整图建索引。容量随可信投影档绑定，仅本执行器
        # 生效；旧评分器仍采用4096，不放宽共享全局或跳过计费。
        self.executor = ActionValueExecutor(source, name=self.name, max_operations=max_operations,
            max_local_collection_size=self.projection_limits.max_nodes)
        self.emergency_policy = SafeFallbackPolicy()

    async def choose(self, request: DecisionRequest, budget: DecisionBudget) -> DecisionPlan:
        """以同次权威事实调用候选一次，输出排名；任何失败抛研发异常。"""

        self.executor.last_operation_count = None  # 本次若建图失败，不冒认上次评分工作量
        emergency_plan = await self.emergency_policy.choose(request, budget)
        if not emergency_plan.candidates:
            raise RouteHeuristicResearchError("NO_EMERGENCY", "独立规则保底为空，研究窗口未完成")
        view = build_vip_route_scoring_view(request, self.config, limits=self.projection_limits)
        try:
            batch = self.executor.score_vip_route(view)
        except WorkloadExceeded as exc:
            raise RouteHeuristicResearchError("WORKLOAD_EXCEEDED", str(exc)) from exc
        except Exception as exc:
            raise RouteHeuristicResearchError("SCORING_FAILED", str(exc)) from exc
        if batch.status != STATUS_SCORED:
            raise RouteHeuristicResearchError("ABSTAIN", batch.reason or "候选拒绝评分")
        rejected = {item.action_key for item in request.rejected_attempts}
        by_key = {item.action_key: item for item in view.actions}
        ordered = sorted((entry for entry in batch.entries if entry.action_key not in rejected),
                         key=lambda entry: (-entry.score, entry.action_key))
        if not ordered:
            raise RouteHeuristicResearchError("NO_CANDIDATE", "全部合法根已明确拒绝")
        emergency_key = request.rules.emergency_candidate.action_key
        candidates = tuple(RankedCandidate(
            action=by_key[entry.action_key].action, action_key=entry.action_key, rank=index,
            total_score=entry.score, score_parts=(ScorePart(self.name, entry.score),),
            reasons=("完整联合评分成功；排名点不是实际积分或未来期望积分",),
            is_emergency=entry.action_key == emergency_key,
            score_trace={"trace_schema": VIP_ROUTE_TRACE_SCHEMA_VERSION,
                         "candidate_kind": self.name,
                         "view_schema_version": VIP_ROUTE_SCORING_VIEW_SCHEMA_VERSION,
                         "normal_draw_hu_payment_semantics_version": VIP_NORMAL_DRAW_HU_PAYMENT_SEMANTICS_VERSION,
                         "natural_preparation_semantics_version": NATURAL_PREPARATION_SEMANTICS_VERSION,
                         "detail": dict(entry.trace)},
        ) for index, entry in enumerate(ordered, start=1))
        return DecisionPlan(
            request.decision_id, request.window_key, request.observation.snapshot_seq,
            len(request.rejected_attempts) + 1, candidates, (),
        )
