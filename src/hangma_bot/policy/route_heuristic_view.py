"""VIP 联合启发式的独立只读事实投影，不改变旧 ``ScoringView/4``。

本模块只展开唯一规则源给出的合法动作与条件转移。图按子节点在前排列，
候选一次正向遍历即可联合比较全部跟打与补牌分支；框架不预选最小向听。
赛事阶段、排名和当前桌积分不进入候选映射。
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from typing import Any, Callable, Mapping, Optional, Tuple, TYPE_CHECKING

from hangma_bot.hangma.interface import Settlement
from hangma_bot.kernel.actions import Action, CANONICAL_TILE_ORDER, action_key
from hangma_bot.kernel.observation import PlayerObservation

from .action_value import ActionScore, ScoreBatch, STATUS_ABSTAIN, STATUS_SCORED

if TYPE_CHECKING:
    from hangma_bot.hangma.route_structure import RouteStructureFacts

VIP_ROUTE_CANDIDATE_KIND = "vip_route_heuristic_v1"
VIP_ROUTE_SCORING_VIEW_SCHEMA_VERSION = "vip-route-scoring-view/1"
VIP_ROUTE_GRAPH_SCHEMA_VERSION = "vip-route-action-graph/1"
VIP_ROUTE_TRACE_SCHEMA_VERSION = "vip-route-score-trace/1"


def _plain(value: Any) -> Any:
    """复制冻结事实为原始值；候选修改自己的容器不会改变下一次调用。"""

    if value is None or type(value) in (str, int, float, bool):
        return value
    if isinstance(value, tuple):
        return tuple(_plain(item) for item in value)
    if hasattr(value, "__dataclass_fields__"):
        return {field.name: _plain(getattr(value, field.name)) for field in fields(value)}
    raise ValueError("VIP 事实含未允许的类型: " + type(value).__name__)


@dataclass(frozen=True)
class RouteWaitingView:
    """合法弃后等待态的真实结构与公开容量，不含他家暗牌。

    结构推进码只表示指定用途的自然缺口降低；``legal_hu_draw_codes`` 是
    唯一规则源的局部条件胡见证，不承诺响应裁决、未来存活或摸牌概率。
    未分析用 None 并给原因；已分析为空用 ()，两者不能混淆。
    """

    structure: "RouteStructureFacts"  # 真正 13-3m 暗牌的结构事实
    useful_codes: Tuple[str, ...]  # 真实普通/七对一步推进码并集，规范34牌序
    unseen_capacities: Tuple[Optional[int], ...]  # 34牌序公开未见张数，不是墙内张数
    unseen_evidence: Tuple[str, ...]  # 同序 exact/conservative/unknown
    legal_hu_draw_codes: Optional[Tuple[str, ...]]  # 已分析的条件胡码；未分析为空值
    qualification_scope: str  # conditional_witness 或 unanalysed，不授予高番必达资格
    qualification_missing_reason: Optional[str] = None
    qualification_unknown_codes: Tuple[str, ...] = ()  # 相容码未能精确判资格，不能当已排除
    qualification_math_closed_codes: Tuple[str, ...] = ()  # 同源真实有效码并集以外，数学已证不能当次胡
    restricted_hu_draw_codes: Tuple[str, ...] = ()  # 假设摸切包络下已见证合法胡码
    unrestricted_hu_draw_codes: Tuple[str, ...] = ()  # 假设可自由抓打包络下已见证合法胡码
    useful_code_width: int = 0  # 去重一步推进相容码数；保守/未知零容量仍相容
    legal_hu_code_width: int = 0  # 已见证两包络合法胡并集的相容码数
    target_improvement_code_widths: Tuple[int, ...] = ()  # targets同序的相容自然推进码数
    standard_useful_codes: Tuple[str, ...] = ()  # 普通型独立一步推进码，保留路线标签
    seven_pairs_useful_codes: Optional[Tuple[str, ...]] = None  # 有副露不适用时None，已分析为空()
    combined_useful_codes: Tuple[str, ...] = ()  # 综合最优向听推进码；与逐牌型并集分开
    baotou: bool = False  # 当前条件状态的规则生命周期事实
    chain_count: int = 0  # 当前连续飘/杠动作次数；不是等待收益

    def __post_init__(self) -> None:
        from hangma_bot.hangma.route_structure import RouteStructureFacts

        if not isinstance(self.structure, RouteStructureFacts):
            raise ValueError("RouteWaitingView.structure 必须是 RouteStructureFacts")
        if len(self.unseen_capacities) != 34 or len(self.unseen_evidence) != 34:
            raise ValueError("公开容量和证据必须是规范34牌序")
        if any(type(count) is not int or not 0 <= count <= 4
               for count in self.unseen_capacities if count is not None):
            raise ValueError("公开容量只能是0—4张或None")
        if any(kind not in ("exact", "conservative", "unknown")
               for kind in self.unseen_evidence):
            raise ValueError("公开容量证据不合法")
        if self.qualification_scope not in ("conditional_witness", "unanalysed"):
            raise ValueError("未知资格范围")
        if (self.legal_hu_draw_codes is None) != (self.qualification_scope == "unanalysed"):
            raise ValueError("资格未分析必须使用None，已分析必须使用集合")
        if self.legal_hu_draw_codes is None and not self.qualification_missing_reason:
            raise ValueError("资格未分析必须说明原因")
        if self.legal_hu_draw_codes is not None and self.qualification_missing_reason is not None:
            raise ValueError("已分析资格不得携带缺口原因")
        if (len(self.target_improvement_code_widths) != len(self.structure.targets)
                or any(type(width) is not int or not 0 <= width <= 34 for width in (
                    self.useful_code_width, self.legal_hu_code_width,
                    *self.target_improvement_code_widths))):
            raise ValueError("集合宽度须逐目标同序且为0—34的整数码数")


@dataclass(frozen=True)
class RouteHeuristicNode:
    """一个可审计的条件评分节点；所有 children 必须位于它之前。

    wait 是合法等待态，hu 是已确认的本条件合法结算，choices 含全部同次
    合法续行，replacement 含未知补牌的全部公开相容码，condition 是同一
    根的互斥公开条件包络。后三者都不表示条件已在真实牌局发生。
    """

    node_key: str
    kind: str  # wait/hu/choices/replacement/condition/unknown_draw
    children: Tuple[str, ...] = ()
    condition_codes: Tuple[str, ...] = ()  # replacement每个子节点对应唯一摸牌码
    waiting: Optional[RouteWaitingView] = None
    settlement: Optional[Settlement] = None  # hu四座净积分，座位顺序0—3
    pending_condition: Optional[str] = None  # 公开事件条件，不是已执行计划
    expected_child_count: int = 0  # 应有全部子节点数；不是择优数量
    completed_child_count: int = 0
    gap_kind: Optional[str] = None  # 缺实现/缺输入/预算截断显式失败
    gap_reason: Optional[str] = None
    uncertainty_reason: Optional[str] = None  # 未来未知不是当前机械缺口
    legal_action_key: Optional[str] = None  # 同次规则分析确认的续行动作键
    followup_key: Optional[str] = None  # 吃碰原CandidateFacts的跟打身份，非择优结果

    def __post_init__(self) -> None:
        if not self.node_key or self.kind not in (
            "wait", "hu", "choices", "replacement", "condition", "unknown_draw",
        ):
            raise ValueError("VIP图节点身份或种类不合法")
        if self.completed_child_count != len(self.children):
            raise ValueError("完成子节点数与实际节点不一致")
        if self.expected_child_count < self.completed_child_count:
            raise ValueError("完成子节点数超过应有数量")
        if self.gap_kind is None and self.expected_child_count != self.completed_child_count:
            raise ValueError("缺子节点必须显式登记gap_kind")
        if (self.gap_kind is None) != (self.gap_reason is None):
            raise ValueError("图缺口类别与原因须同时提供")
        if self.kind == "wait" and (self.waiting is None or self.settlement is not None):
            raise ValueError("wait必须携带真实等待事实且不能混入结算")
        if self.kind == "unknown_draw" and (
            self.waiting is None or not self.uncertainty_reason or self.children
        ):
            raise ValueError("未知补牌必须保留补牌前真实等待结构与未知原因")
        if self.kind == "hu" and (self.settlement is None or self.waiting is not None):
            raise ValueError("hu必须携带同源结算")
        if self.kind in ("wait", "hu") and self.children:
            raise ValueError("末端节点不能混入续行")
        if self.kind in ("choices", "replacement", "condition") and not self.children and self.gap_kind is None:
            raise ValueError("完整条件聚合节点不能没有合法子节点")
        if self.kind == "replacement" and (
            len(self.condition_codes) != len(self.children)
            or len(set(self.condition_codes)) != len(self.condition_codes)
        ):
            raise ValueError("补牌条件码须与子节点一一对应且不重复")


@dataclass(frozen=True)
class RouteHeuristicAction:
    """规则确认的一项合法根；actual action仅供最终计划适配。"""

    action_key: str
    action: Action  # 冻结规则值对象，受限候选映射不携带本对象
    action_type: str
    node_key: str
    pending_condition: Optional[str] = None
    skipped_seats: int = 0  # 鸣牌相对供牌者跳过的原行动座位数0/1/2

    def __post_init__(self) -> None:
        if self.action_key != action_key(self.action):
            raise ValueError("VIP根动作键与规则值对象不一致")
        if self.action_type not in ("discard", "hu", "pass", "chi", "peng", "gang"):
            raise ValueError("VIP根动作族未知")
        if self.skipped_seats not in (0, 1, 2):
            raise ValueError("鸣牌跳过座位数必须为0/1/2")


@dataclass(frozen=True)
class VipRouteScoringView:
    """独立版本的玩家可见事实；不承载赛事压力或真实完整世界。"""

    schema_version: str
    visible_state: PlayerObservation  # 只供第一方白名单投影，不送入受限候选
    actions: Tuple[RouteHeuristicAction, ...]
    nodes: Tuple[RouteHeuristicNode, ...]  # 子节点先于父节点，拒绝循环与悬空引用
    ruleset_version: str
    base_score: int  # 官方BaseScore，真实支付归一化时使用
    you_cai_bi_kao: bool
    structure_semantics_version: str
    executor_version: str
    max_nodes: int
    max_branches: int
    max_waiting_draw_witnesses: int = 16384
    waiting_draw_witness_count: int = 0  # 本次规则局部资格分析请求次数，非完整树节点数
    target_distance_evaluation_count: int = 0  # 结构目标距离请求计数，非后端实际节点数

    def __post_init__(self) -> None:
        if self.schema_version != VIP_ROUTE_SCORING_VIEW_SCHEMA_VERSION:
            raise ValueError("VIP视图版本不匹配")
        if not isinstance(self.visible_state, PlayerObservation):
            raise ValueError("VIP视图只接受PlayerObservation")
        if not isinstance(self.actions, tuple) or not isinstance(self.nodes, tuple):
            raise ValueError("VIP根和节点必须是冻结元组")
        if not self.ruleset_version or not self.structure_semantics_version or not self.executor_version:
            raise ValueError("VIP视图必须绑定规则、结构和执行器版本")
        if type(self.base_score) is not int or self.base_score <= 0:
            raise ValueError("BaseScore必须为正整数")
        if any(type(limit) is not int or limit <= 0 for limit in (self.max_nodes, self.max_branches)):
            raise ValueError("图工作量上限必须为正整数")
        if (type(self.max_waiting_draw_witnesses) is not int or self.max_waiting_draw_witnesses <= 0
                or type(self.waiting_draw_witness_count) is not int
                or not 0 <= self.waiting_draw_witness_count <= self.max_waiting_draw_witnesses
                or type(self.target_distance_evaluation_count) is not int
                or self.target_distance_evaluation_count < 0):
            raise ValueError("规则局部见证和结构工作量计数无效")
        keys = tuple(item.action_key for item in self.actions)
        if not keys or keys != tuple(sorted(set(keys))):
            raise ValueError("VIP根必须非空且按动作键严格升序")
        seen = set()
        branches = 0
        for node in self.nodes:
            if node.node_key in seen or any(child not in seen for child in node.children):
                raise ValueError("VIP图必须无重复、无循环且子节点先于父节点")
            seen.add(node.node_key)
            branches += len(node.children)
        if any(item.node_key not in seen for item in self.actions):
            raise ValueError("VIP根存在悬空节点")
        if len(self.nodes) > self.max_nodes or branches > self.max_branches:
            raise ValueError("VIP图超出冻结展开上限")

    def expected_action_keys(self) -> Tuple[str, ...]:
        """完整返回校验的合法根键；拒绝动作也先完成事实与评分。"""

        return tuple(item.action_key for item in self.actions)

    def candidate_view(self) -> dict[str, Any]:
        """返回全新原始值容器；不含积分、阶段、名次或隐藏未来。"""

        observation = self.visible_state
        return {
            "schema_version": self.schema_version,
            "candidate_kind": VIP_ROUTE_CANDIDATE_KIND,
            "graph_schema_version": VIP_ROUTE_GRAPH_SCHEMA_VERSION,
            "tile_order": CANONICAL_TILE_ORDER,
            "visible_state": {
                "seat": observation.seat,
                "dealer_seat": observation.dealer_seat,
                "phase": observation.phase,
                "my_hand": tuple(tile.code for tile in observation.my_hand),
                "drawn_tile": observation.drawn_tile.code if observation.drawn_tile else None,
                "remaining_tile_count": observation.remaining_tile_count,
                "discards": tuple(tuple(tile.code for tile in row) for row in observation.discards),
                "melds": tuple(tuple({
                    "kind": meld.kind,
                    "tiles": tuple(tile.code for tile in meld.tiles),
                    "from_seat": meld.from_seat,
                } for meld in row) for row in observation.melds),
                "hand_counts": observation.hand_counts,
            },
            "binding": {
                "ruleset_version": self.ruleset_version,
                "base_score": self.base_score,
                "you_cai_bi_kao": self.you_cai_bi_kao,
                "structure_semantics_version": self.structure_semantics_version,
                "executor_version": self.executor_version,
            },
            "limits": {"max_nodes": self.max_nodes, "max_branches": self.max_branches,
                       "max_waiting_draw_witnesses": self.max_waiting_draw_witnesses},
            "workload": {"expanded_node_count": len(self.nodes),
                         "expanded_branch_count": sum(len(node.children) for node in self.nodes),
                         "waiting_draw_witness_count": self.waiting_draw_witness_count,
                         "target_distance_evaluation_count": self.target_distance_evaluation_count},
            "actions": tuple({
                "action_key": item.action_key,
                "action_type": item.action_type,
                "node_key": item.node_key,
                "pending_condition": item.pending_condition,
                "skipped_seats": item.skipped_seats,
            } for item in self.actions),
            "nodes": tuple(_plain(node) for node in self.nodes),
        }


def run_vip_route_scoring_skeleton(
    view: VipRouteScoringView,
    candidate_fn: Callable[[Mapping[str, Any]], Mapping[str, Any]],
) -> ScoreBatch:
    """独立实类型入口；共用既有ScoreBatch的有限数与有界解释校验。"""

    if not isinstance(view, VipRouteScoringView):
        raise ValueError("VIP骨架需要VipRouteScoringView输入")
    if any(node.gap_kind is not None for node in view.nodes):
        raise ValueError("VIP当前机械/输入/工作量缺口不能进入成功评分")
    try:
        raw = candidate_fn(view.candidate_view())
    except Exception as exc:
        raise ValueError("VIP候选执行失败: " + type(exc).__name__ + ": " + str(exc)) from exc
    if not isinstance(raw, dict):
        raise ValueError("VIP候选必须返回映射")
    status = raw.get("status")
    if status == STATUS_ABSTAIN:
        if raw.get("entries") not in (None, (), []):
            raise ValueError("ABSTAIN不能携带部分评分")
        return ScoreBatch(status=STATUS_ABSTAIN, entries=(), reason=raw.get("reason"))
    if status != STATUS_SCORED or not isinstance(raw.get("entries"), (list, tuple)):
        raise ValueError("VIP返回必须是SCORED条目或有原因的ABSTAIN")
    entries = []
    for row in raw["entries"]:
        if not isinstance(row, dict) or not {"action_key", "score", "trace"}.issubset(row):
            raise ValueError("VIP评分项必须包含action_key/score/trace")
        entries.append(ActionScore(row["action_key"], row["score"], row["trace"]))
    keys = tuple(entry.action_key for entry in entries)
    if len(set(keys)) != len(keys) or set(keys) != set(view.expected_action_keys()):
        raise ValueError("VIP评分必须覆盖全部合法根各一次，无漏项、重复或越界")
    return ScoreBatch(status=STATUS_SCORED, entries=tuple(entries), reason=raw.get("reason"))
