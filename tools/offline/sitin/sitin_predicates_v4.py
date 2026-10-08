# -*- coding: utf-8 -*-
"""sitin 场景矩阵 v4 合同 §7.3「八个机器谓词的冻结合同」的纯函数实现。

规范来源：review/llm-guided-heuristic-route-2026-09-15/SEARCH-SPACE-REDESIGN-2026-09-16.md
§7.3。本模块只实现该合同的三值判定，不解释“机会好坏”，不读取任何被测评分器；
经验阈值只定义采样条件，不构成策略偏好。

输入合同（facts：同一根规则事实的 JSON 投影，dict）
--------------------------------------------------
- 「wall_left」：int，牌墙剩余枚数（非负）；null 或缺省表示未知。
- 「branches」：行动分支列表（list），每项为 dict：
  - 「action_key」：str，当前合法动作键（非空）；
  - 「combined_shanten」：int|null，该分支等待态已知分牌型向听的最小值；没有同一
    分析范围的比较值时为 null（不可比较）。缺省视为 null；
  - 「shanten_state」（P9 FAMCOST 修复，2026-09-18）：known/not_applicable/unknown
    三态判别标签，区分"不适用"与"未知"。not_applicable = **有事实**但没有等待态
    分牌型（典型：胡牌窗口 WIN/NOT_APPLICABLE），按判定算法第 2 条**永不可比较**
    ——不是"待补全的缺失值"；unknown = 没有事实（facts 为空），才是真的未知。
    缺省（未给该键）按 combined_shanten 是否为 null 回退为 known/unknown，
    旧夹具行为逐字不变。修复前两种情形都写作 null，存在性分析把 not_applicable
    当缺失 ⇒ 合法 hu 窗口被判 UNKNOWN（P9 Q1 实测：代价侧 4/331 帧）。
  - 「family_progress」：dict，键固定为 branch/chain/four_white/baotou，值为
    ADVANCE/SAME/RETREAT/CLOSE/UNKNOWN 之一；
  - 「route_status」：WITNESSED/OPEN_UNCERTAIN/CLOSED_PROVEN/UNANALYZED 之一；
  - 「support_remaining」：dict，键同上，值为该家族一步推进有效牌未见枚数总和
    （非负 int；null=未知）。
结构约束：family_progress / support_remaining 采用封闭键集，出现四个家族之外的键
视为结构非法（抛 ValueError）；facts 顶层的其他键一律忽略（同一投影可能携带其他
字段，本模块不做 schema 之外的推测）。

判定算法（§7.3 冻结）
--------------------
对家族 f 枚举来自**不同当前合法 action_key** 的有序分支对 (b, c)（分支按 action_key
稳定排序后双重枚举，b 为推进侧、c 为参照侧）：

1. 结构条件：b 对 f 为 ADVANCE 且 c ∈ {SAME, RETREAT, CLOSE}；或 b 为 SAME 且
   c ∈ {RETREAT, CLOSE}。b 的 route_status 必须为 WITNESSED 或 OPEN_UNCERTAIN
   （自身不被证明关闭；合同只约束 b，不约束 c）。
2. 数据条件：b/c 的 combined_shanten 均非 null 才算候选对，gap = shanten(b) −
   shanten(c)；wall_left 与 support_remaining(b, f) 必须已知。
**【P9c 修正（2026-09-18，Lead 裁定路线 (b)①）：取舍代价量换成 Δsupp】**

2'. 数据条件（改写）：b/c 都必须有等待态（可比较，P9）；**b 的动作后
    combined_shanten ≤ PAIR_SHANTEN_MAX(1)**（决策相关性：取舍只在距成牌一步内才有决策
    意义——实测这正是两侧位置选择性的来源）；对确定见证还要求 **b/c 的
    support_remaining(f) 都已知**。
3. f_open 为 TRUE：存在满足对且 wall_left ≥ WALL_OPEN_MIN(16) 且
   Δsupp(b,c) = support_remaining(b,f) − support_remaining(c,f) ≥ SUPPORT_DELTA_OPEN_MIN(−16)（全 AND）。
4. f_cost 为 TRUE：存在满足对且（wall_left ≤ WALL_COST_MAX(15) 或
   Δsupp(b,c) ≤ SUPPORT_DELTA_COST_MAX(−17)）（OR）。

为什么换掉 gap：gap（向听差）在真实帧上的取值域只有 {−2,−1,0,1}（−1 占 99.3%），
它区分的其实只是"跨路线取最小"的算术后果；Δsupp 的域是 [−71,+31]（合格对内
p1=−49 / p50=−16 / p95=−2），直接刻画设计 §7.3 想要的"推进分支的进张比不推进的参照
多多少/少多少"（"关键进张耗尽"正是它的下侧）。旧数字（墙 8/16、gap 1/2 与 0/1、
support 0）作为**历史**保留在文档 §7.3 的修正块里。
open 与 cost 各自独立判定，不要求同一分支对同时满足两个方向。

**【S4 范围声明（2026-09-18 独立验收裁定，仅注释，判据与阈值一字未改）】**
本版**只启用 branch**；chain / four_white / baotou 显式 inactive，由调度
（sitin_search.av_family_scope / _av_family_fill）明确跳过并留下具名原因。依据：
已归档 6 根 / 2,129 帧的独立复算显示，这三族原有的机会侧 TRUE（3/10/5 帧）在本谓词下
**全部转 UNKNOWN**——确定见证要求 b **与 c 两侧**的家族支持量都已知（Δsupp 需要参照
分支），而特殊家族无对应路线时投影返回 None，于是既不能确证也不能证伪。
**把 None 当 0 一律禁止**（那会把"未知"伪造成"没有取舍"，使判定从 UNKNOWN 变成 FALSE，
是结论方向的篡改）。三族的启用需要单独的合同收口（补足该族的支持量来源），不在本版。
本模块的判定逻辑对四族同构：族名不在启用集内时不是"算不出来"，而是**上层不调度**。

三值语义
--------
- TRUE：已知存在满足全部条件的分支对，附事实见证键 witness = {"b", "c"}。
- FALSE：所有必要比较已知但均不满足，witness 与 missing 均为 null。
- UNKNOWN：没有确定见证、且存在“补全后可能翻转为 TRUE”的缺失值，missing 为
  原因列表（单列，不当作 FALSE）。缺失值包括：wall_left 未知、分支对缺
  combined_shanten（gap 不可算；仅限 shanten_state=unknown）、
  support_remaining(b, f) 未知、family_progress[f]
  为 UNKNOWN（该分支可能本可充当 b 或 c）。
  **shanten_state=not_applicable 的分支不进入缺失分析**（P9 修复）：它永不可比较，
  补全任何值都不会让该分支对满足第 2 条，因此它的 null 不是"可能改变判定的缺失"。

歧义处理决定（合同未逐字规定、由本模块冻结的解释）
--------------------------------------------------
1. cost 的墙阈值边界按合同测试行“8/9”与 WALL_COST_MAX=8 实现：wall_left=8 判
   TRUE、9 不因墙判 TRUE。
   **P9b 补充**：gap 的边界按重锚后的 0/1 实现（open 侧 gap=0 判 TRUE、1 不判；
   cost 侧 gap=1 判 TRUE、0 不判）；原 1/2 边界因落在实测取值域之外而作废
   （见上方 GAP_OPEN_MAX/GAP_COST_MIN 注释与 §7.3 的 2026-09-18 修正块）。
2. family_progress[f] = UNKNOWN 的分支不能充当 b（也不能充当 c），但按三值语义视
   为“可能改变判定的缺失”：若因此没有确定见证，该家族谓词为 UNKNOWN 并单列原因。
3. route_status = CLOSED_PROVEN / UNANALYZED 按合同硬门槛处理：definitive 排除，
   不产生 UNKNOWN（合同三值语义的缺失例子只含 wall/shanten/support 数值缺失）。
4. c 的 route_status 不受约束（合同只写“b 的路线状态必须为 ……”）。
5. 缺失值是否“可能改变判定”按存在性分析：只有当某分支对在补全缺失后可能满足
   open/cost 条件时，其缺失才触发 UNKNOWN；即使补全也不可能满足的缺失不触发，
   此时谓词照常判 FALSE。

纯函数约束：无 I/O、无时间/随机/网络；不修改输入；同输入必同输出（含 witness 与
missing 的顺序，均为稳定枚举序）。
"""

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

from typing import Any, Dict, List, Optional, Tuple

__all__ = [
    "PREDICATE_IDS",
    "WALL_OPEN_MIN",
    "WALL_COST_MAX",
    "PAIR_SHANTEN_MAX",
    "SUPPORT_DELTA_OPEN_MIN",
    "SUPPORT_DELTA_COST_MAX",
    "GAP_OPEN_MAX_HISTORICAL",
    "GAP_COST_MIN_HISTORICAL",
    "FAMILY_PREDICATES",
    "evaluate_predicates",
    "evaluate_predicate",
]

#: 八个机器谓词的固定 ID（§7.3 冻结，顺序固定）。
PREDICATE_IDS: Tuple[str, ...] = (
    "branch_open",
    "branch_cost",
    "chain_open",
    "chain_cost",
    "four_white_open",
    "four_white_cost",
    "baotou_open",
    "baotou_cost",
)

#: open 需要墙余量 ≥ 16（合同阈值，不得内联魔法数）。
WALL_OPEN_MIN: int = 16
#: cost 的 OR 条件之一：墙余量 ≤ 15。
#: P9c（2026-09-18）：按"两侧分量互补"规则（P9b 规则②）与机会侧的 ≥16 严丝合缝
#: （原值 8 会留下 9..15 的中性带，使"墙"这一分量不能把局面二分成机会/代价）。
WALL_COST_MAX: int = 15
#: 取舍对的**决策相关性**门槛（P9c 新增，合同第 2 条的数据条件）：
#: 推进分支 b 的动作后 combined_shanten 必须 ≤ 1（距成牌一步之内）——
#: "关键进张耗尽 / 距离明显增大"这类取舍只在接近成牌时才有决策意义；
#: 实测这也正是两侧**位置选择性**的来源（开局首帧不可能满足 ⇒ 首命中有中位数）。
PAIR_SHANTEN_MAX: int = 1
#: 新的取舍代价量（P9c，取代 P9b 的向听差 gap）：Δsupp = support_remaining(b,f) − support_remaining(c,f)。
#: 域实测 [−71, +31]（合格对 = 决策相关性门槛内，p1=−49 / p50=−16 / p95=−2），
#: 机会侧取上侧、代价侧取下侧，互补于 −16/−17（边界 = 合格对 Δsupp 的中位数）。
SUPPORT_DELTA_OPEN_MIN: int = -16
#: cost 的 OR 条件之一：Δsupp ≤ −17（与机会侧的 ≥−16 互补）。
SUPPORT_DELTA_COST_MAX: int = -17
#: open 需要 gap ≤ 0（P9b 重锚：推进分支**不比**参照分支贵）。
#:
#: P9b 可达性重锚（2026-09-18，Lead 裁定：冻结阈值设定时未做真实帧可达性检查）：
#: 真实帧实测 gap 取值域 = {−2,−1,0,1}（21,146 个严格分支对，−1 占 99.3%），
#: 原阈值对（open ≤1 / cost ≥2）因此 **open 恒真、cost 恒假**——阈值落在分布之外。
#: 重锚规则（四条，**一次性冻结**，不许迭代调到期望形状）：
#:   ① 阈值必须落在实测分布**内部**（两侧都有真实见证）；
#:   ② 同一分量两侧**互补**（open 取下侧、cost 取上侧，不重叠不留空隙）；
#:   ③ 每侧合成命中率 ∈ (0.1%, 50%)（真实帧）；
#:   ④ 选定即写进文档 + 可达性回归测试（tools/test_sitin_predicates_reachability.py）。
#: 证据：review/llm-guided-heuristic-route-2026-09-15/evidence/v4-impl/r9-fixes/P9-famcost/
#: （probes/distributions.json、probes/threshold-candidates*.json）。
#: 【历史存档，判定已不再使用】P9b 的 gap 边界（0/1）。P9c 起 gap（向听差）整体被
#: Δsupp 取代：gap 域只有 {−2,−1,0,1}（−1 占 99.3%），信息量不足以区分"推进 vs 不推进"。
#: 保留数值只为让后来人看得到演进（设计文档 §7.3 同步标注"已由 2026-09-18 修正块取代"）。
GAP_OPEN_MAX_HISTORICAL: int = 0
GAP_COST_MIN_HISTORICAL: int = 1

#: 四个专长家族（family_progress / support_remaining 的键）。
FAMILIES: Tuple[str, ...] = ("branch", "chain", "four_white", "baotou")

#: 家族 → (open 谓词 ID, cost 谓词 ID) 的冻结映射。
FAMILY_PREDICATES: Dict[str, Tuple[str, str]] = {
    "branch": ("branch_open", "branch_cost"),
    "chain": ("chain_open", "chain_cost"),
    "four_white": ("four_white_open", "four_white_cost"),
    "baotou": ("baotou_open", "baotou_cost"),
}

_PREDICATE_TO_FAMILY_KIND: Dict[str, Tuple[str, str]] = {
    predicate_id: (family, kind)
    for family, (open_id, cost_id) in FAMILY_PREDICATES.items()
    for predicate_id, kind in ((open_id, "open"), (cost_id, "cost"))
}

_PROGRESS_LABELS = frozenset(("ADVANCE", "SAME", "RETREAT", "CLOSE", "UNKNOWN"))
#: 可比较性三态（P9 修复）：投影 side-car 字段 shanten_state 的合法取值。
_SHANTEN_STATES = frozenset(("known", "not_applicable", "unknown"))
_ROUTE_STATUSES = frozenset(("WITNESSED", "OPEN_UNCERTAIN", "CLOSED_PROVEN", "UNANALYZED"))
#: b 允许的路线状态：自身不被证明关闭（WITNESSED 或 OPEN_UNCERTAIN）。
_B_ROUTE_STATUSES = frozenset(("WITNESSED", "OPEN_UNCERTAIN"))
#: b=ADVANCE 时 c 允许的已知进展标签。
_C_PROGRESS_WHEN_B_ADVANCE = frozenset(("SAME", "RETREAT", "CLOSE"))
#: b=SAME 时 c 允许的已知进展标签。
_C_PROGRESS_WHEN_B_SAME = frozenset(("RETREAT", "CLOSE"))


# ---------------------------------------------------------------------------
# 输入校验
# ---------------------------------------------------------------------------


def _validate_facts(facts: Any) -> None:
    """校验 facts 的结构，非法时抛 ValueError 并指明字段路径。

    facts 必须是 dict；branches 必须存在且为 list；每个分支必须含非空 str 的
    action_key、int|null 的 combined_shanten、封闭键集的 family_progress /
    support_remaining（值类型见模块 docstring）、合法枚举的 route_status。
    wall_left 可缺省或为 null（=未知），否则必须是非负 int（bool 视为非法）。
    """
    if not isinstance(facts, dict):
        raise ValueError(
            f"facts 必须是 dict（同一根规则事实的 JSON 投影），实际类型: {type(facts).__name__}"
        )
    if "wall_left" in facts and facts["wall_left"] is not None:
        wall = facts["wall_left"]
        if isinstance(wall, bool) or not isinstance(wall, int):
            raise ValueError(
                f"facts.wall_left 必须是 int（牌墙剩余枚数）或 null（未知），实际: {wall!r}"
            )
        if wall < 0:
            raise ValueError(f"facts.wall_left 是牌墙剩余枚数，不能为负: {wall!r}")
    if "branches" not in facts:
        raise ValueError("facts 缺少 branches 字段（行动分支列表）")
    branches = facts["branches"]
    if not isinstance(branches, list):
        raise ValueError(
            f"facts.branches 必须是 list，实际类型: {type(branches).__name__}"
        )
    for index, branch in enumerate(branches):
        _validate_branch(index, branch)


def _validate_branch(index: int, branch: Any) -> None:
    """校验单个分支结构；非法时抛 ValueError，消息含 branches[index] 路径。"""
    where = f"facts.branches[{index}]"
    if not isinstance(branch, dict):
        raise ValueError(f"{where} 必须是 dict，实际类型: {type(branch).__name__}")
    action_key = branch.get("action_key")
    if not isinstance(action_key, str) or not action_key:
        raise ValueError(f"{where}.action_key 必须是非空 str，实际: {action_key!r}")
    shanten = branch.get("combined_shanten")
    if shanten is not None and (isinstance(shanten, bool) or not isinstance(shanten, int)):
        raise ValueError(
            f"{where}.combined_shanten 必须是 int（向听距离）或 null（不可比较），实际: {shanten!r}"
        )
    state = branch.get("shanten_state")
    if state is not None and (not isinstance(state, str) or state not in _SHANTEN_STATES):
        raise ValueError(
            f"{where}.shanten_state 必须是 known/not_applicable/unknown 之一或"
            f"缺省，实际: {state!r}"
        )
    _validate_family_map(
        where,
        "family_progress",
        branch.get("family_progress"),
        _validate_progress_value,
    )
    route_status = branch.get("route_status")
    if not isinstance(route_status, str) or route_status not in _ROUTE_STATUSES:
        raise ValueError(
            f"{where}.route_status 必须是 WITNESSED/OPEN_UNCERTAIN/CLOSED_PROVEN/"
            f"UNANALYZED 之一，实际: {route_status!r}"
        )
    _validate_family_map(
        where,
        "support_remaining",
        branch.get("support_remaining"),
        _validate_support_value,
    )


def _validate_family_map(where: str, field: str, value: Any, value_checker) -> None:
    """校验 family_progress / support_remaining：必须是封闭键集 dict，值逐键校验。"""
    if not isinstance(value, dict):
        raise ValueError(
            f"{where}.{field} 必须是 dict，实际类型: {type(value).__name__}"
        )
    for family in FAMILIES:
        if family not in value:
            raise ValueError(f"{where}.{field} 缺少家族键 {family}")
        value_checker(where, field, family, value[family])
    extra = sorted(set(value) - set(FAMILIES))
    if extra:
        legal_keys = "/".join(FAMILIES)
        raise ValueError(
            f"{where}.{field} 含未知家族键 {extra}（合法键: {legal_keys}）"
        )


def _validate_progress_value(where: str, field: str, family: str, value: Any) -> None:
    """校验单个进展标签：必须是五个冻结标签之一。"""
    if not isinstance(value, str) or value not in _PROGRESS_LABELS:
        raise ValueError(
            f"{where}.{field}[{family}] 必须是 ADVANCE/SAME/RETREAT/CLOSE/UNKNOWN "
            f"之一，实际: {value!r}"
        )


def _validate_support_value(where: str, field: str, family: str, value: Any) -> None:
    """校验单个支持计数：非负 int 或 null（未知）；bool 视为非法。"""
    if value is None:
        return
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(
            f"{where}.{field}[{family}] 必须是非负 int（未见枚数总和）或 null（未知），"
            f"实际: {value!r}"
        )
    if value < 0:
        raise ValueError(
            f"{where}.{field}[{family}] 是未见枚数总和，不能为负: {value!r}"
        )


# ---------------------------------------------------------------------------
# 判定核心
# ---------------------------------------------------------------------------


def _by_action_key(branch: Dict[str, Any]) -> str:
    """sorted 的排序键：action_key（sorted 本身稳定，重复键保持输入序）。"""
    return branch["action_key"]


def _shanten_state(branch: Dict[str, Any]) -> str:
    """分支的可比较性三态：显式 shanten_state 优先，缺省按 combined_shanten 推断。

    缺省路径（未给 shanten_state）回退为 known/unknown——旧夹具与旧投影的行为
    逐字不变；投影侧显式给出 not_applicable 时才启用"不适用 ≠ 缺失"的语义。
    """

    state = branch.get("shanten_state")
    if state in _SHANTEN_STATES:
        return str(state)
    return "known" if branch.get("combined_shanten") is not None else "unknown"


def _comparable(branch: Dict[str, Any]) -> bool:
    """合同第 2 条：分支对的 b 与 c 都必须有**可比较**的 combined_shanten。

    shanten_state=not_applicable（有事实但无等待态分牌型，如胡牌窗口）永远不
    可比较 ⇒ 不进入分支对枚举（既不当 b 也不当 c），也不触发 UNKNOWN。
    """

    return _shanten_state(branch) == "known"


def _strict_pair(b_progress: Any, c_progress: Any) -> bool:
    """结构条件（两端进展均为已知标签，不含 UNKNOWN）。

    b=ADVANCE 时 c ∈ {SAME, RETREAT, CLOSE}；b=SAME 时 c ∈ {RETREAT, CLOSE}；
    其他（含 b 为 RETREAT/CLOSE/UNKNOWN）不构成满足对。
    """
    if b_progress == "ADVANCE":
        return c_progress in _C_PROGRESS_WHEN_B_ADVANCE
    if b_progress == "SAME":
        return c_progress in _C_PROGRESS_WHEN_B_SAME
    return False


def _possible_pair(b_progress: Any, c_progress: Any) -> bool:
    """结构条件的存在性放宽：任一端为 UNKNOWN 时，是否存在补全后的合法组合。

    用于三值语义的“可能改变判定”分析：UNKNOWN 进展的分支可能本可充当 b（ADVANCE/
    SAME）或 c（SAME/RETREAT/CLOSE）。两端均为已知标签时与 _strict_pair 一致。
    """
    if b_progress == "ADVANCE":
        return c_progress in _C_PROGRESS_WHEN_B_ADVANCE or c_progress == "UNKNOWN"
    if b_progress == "SAME":
        return c_progress in _C_PROGRESS_WHEN_B_SAME or c_progress == "UNKNOWN"
    if b_progress == "UNKNOWN":
        # b 可能补全为 ADVANCE（c ∈ {SAME,RETREAT,CLOSE} 或 UNKNOWN）；补全为 SAME
        # 的 c 需求（RETREAT/CLOSE）被该集合包含。
        return c_progress in _C_PROGRESS_WHEN_B_ADVANCE or c_progress == "UNKNOWN"
    return False


def _open_possible(wall: Optional[int], delta: Optional[int],
                   eligible: bool) -> bool:
    """open 条件的存在性放宽：None 表示该值缺失（可能补全为任意合法值）。

    全 AND：墙、决策相关性（b 的动作后向听 ≤ PAIR_SHANTEN_MAX）、Δsupp 三项
    要么已知且满足，要么缺失（可能补全为满足）。eligible=False 表示决策相关性
    **确定不合格**（b 的向听已知且超门槛）⇒ 该对永不可能满足，不触发 UNKNOWN。
    """
    if not eligible:
        return False
    return ((wall is None or wall >= WALL_OPEN_MIN)
            and (delta is None or delta >= SUPPORT_DELTA_OPEN_MIN))


def _cost_possible(wall: Optional[int], delta: Optional[int],
                   eligible: bool) -> bool:
    """cost 条件的存在性放宽：None 表示该值缺失（可能补全为任意合法值）。

    OR：存在一个析取项不 definitively 为假（取值缺失，或已知且满足）。
    墙短析取项与 Δsupp 无关，因此即使 Δsupp 未知也可由墙决定 TRUE。
    """
    if not eligible:
        return False
    return ((wall is None or wall <= WALL_COST_MAX)
            or (delta is None or delta <= SUPPORT_DELTA_COST_MAX))


def _evaluate_family_kind(
    branches: List[Dict[str, Any]],
    wall: Optional[int],
    family: str,
    kind: str,
    predicate_id: str,
) -> Dict[str, Any]:
    """对家族 family 的 kind（open/cost）执行三值判定，返回结果 dict。

    branches 必须已按 action_key 稳定排序；wall 为 None 表示墙余量未知。
    返回结构：{"predicate": 谓词 ID, "value": TRUE/FALSE/UNKNOWN,
    "witness": {"b","c"} 或 null, "missing": [原因...] 或 null}。
    """
    # 第一步：TRUE 扫描——寻找确定见证（结构 + 决策相关性 + Δsupp + 墙，全部已知且满足）。
    for b in branches:
        if not _comparable(b):
            continue  # 合同第 2 条：b 必须有等待态（P9：not_applicable 不可比较）
        if b["route_status"] not in _B_ROUTE_STATUSES:
            continue  # b 必须不被证明关闭（合同硬门槛，definitive 排除）
        b_progress = b["family_progress"][family]
        b_shanten = b.get("combined_shanten")
        if b_shanten is None:
            continue  # 决策相关性未知 ⇒ 不能作确定见证（进缺失分析）
        if b_shanten > PAIR_SHANTEN_MAX:
            continue  # 决策相关性**确定不合格**（离成牌太远，取舍无决策意义）
        b_support = b["support_remaining"][family]
        for c in branches:
            if c["action_key"] == b["action_key"]:
                continue  # 分支对必须来自不同当前合法 action_key
            if not _comparable(c):
                continue  # 合同第 2 条：c 也必须有等待态
            if not _strict_pair(b_progress, c["family_progress"][family]):
                continue
            if wall is None:
                continue  # 墙余量未知 ⇒ 不能作确定见证
            if kind == "cost" and wall <= WALL_COST_MAX:
                # 墙短析取项成立，与支持计数无关（OR 语义）。
                return {
                    "predicate": predicate_id, "value": "TRUE",
                    "witness": {"b": b["action_key"], "c": c["action_key"]},
                    "missing": None,
                }
            c_support = c["support_remaining"][family]
            if b_support is None or c_support is None:
                continue  # Δsupp 未知 ⇒ 进缺失分析
            delta = b_support - c_support
            if kind == "open":
                satisfied = wall >= WALL_OPEN_MIN and delta >= SUPPORT_DELTA_OPEN_MIN
            else:
                satisfied = delta <= SUPPORT_DELTA_COST_MAX
            if satisfied:
                return {
                    "predicate": predicate_id,
                    "value": "TRUE",
                    "witness": {"b": b["action_key"], "c": c["action_key"]},
                    "missing": None,
                }
    # 第二步：缺失扫描——无确定见证时，是否存在补全后可能翻转为 TRUE 的缺失值。
    # P9：shanten_state=not_applicable 的分支永不可比较（合同第 2 条）⇒ 不进入
    # 本扫描——它的 null 不是"可能改变判定的缺失"（修复前合法 hu 窗口被判 UNKNOWN）。
    missing: List[str] = []
    for b in branches:
        if _shanten_state(b) == "not_applicable":
            continue
        if b["route_status"] not in _B_ROUTE_STATUSES:
            continue
        b_progress = b["family_progress"][family]
        b_shanten = b.get("combined_shanten")
        b_support = b["support_remaining"][family]
        if b_shanten is not None and b_shanten > PAIR_SHANTEN_MAX:
            continue  # 决策相关性确定不合格：该对永不可能满足，缺失不触发 UNKNOWN
        for c in branches:
            if c["action_key"] == b["action_key"]:
                continue
            if _shanten_state(c) == "not_applicable":
                continue
            c_progress = c["family_progress"][family]
            if not _possible_pair(b_progress, c_progress):
                continue
            c_support = c["support_remaining"][family]
            delta: Optional[int]
            if b_support is None or c_support is None:
                delta = None
            else:
                delta = b_support - c_support
            possible = (
                _open_possible(wall, delta, True)
                if kind == "open"
                else _cost_possible(wall, delta, True)
            )
            if not possible:
                continue  # 即使补全缺失也不可能满足，不触发 UNKNOWN
            pair_missing: List[str] = []
            if wall is None:
                pair_missing.append("wall_left 缺失")
            if b_progress == "UNKNOWN":
                pair_missing.append(
                    f"分支 {b['action_key']} 的 family_progress[{family}] 为 UNKNOWN，"
                    f"分支对角色无法确定"
                )
            if c_progress == "UNKNOWN":
                pair_missing.append(
                    f"分支 {c['action_key']} 的 family_progress[{family}] 为 UNKNOWN，"
                    f"分支对角色无法确定"
                )
            if b_shanten is None:
                pair_missing.append(
                    f"分支 {b['action_key']} 的动作后向听未知"
                    f"（shanten_state={_shanten_state(b)}），决策相关性无法判定"
                )
            if b_support is None:
                pair_missing.append(
                    f"分支 {b['action_key']} 的 support_remaining[{family}] 未知"
                )
            if c_support is None:
                pair_missing.append(
                    f"分支 {c['action_key']} 的 support_remaining[{family}] 未知"
                )
            if pair_missing:
                missing.extend(pair_missing)
    if missing:
        ordered: List[str] = []
        for reason in missing:  # 去重并保持稳定枚举序，保证确定性
            if reason not in ordered:
                ordered.append(reason)
        return {
            "predicate": predicate_id,
            "value": "UNKNOWN",
            "witness": None,
            "missing": ordered,
        }
    return {"predicate": predicate_id, "value": "FALSE", "witness": None, "missing": None}


# ---------------------------------------------------------------------------
# 公共入口
# ---------------------------------------------------------------------------


def evaluate_predicates(facts: dict) -> dict:
    """对同一根规则事实一次计算全部八个机器谓词（§7.3 冻结合同）。

    输入：facts 为规则事实的 JSON 投影（dict）。字段含义、单位与可空条件见模块
    docstring；wall_left 为牌墙剩余枚数（int；null/缺省=未知）。

    返回：dict，键为 PREDICATE_IDS 中的八个谓词 ID（固定顺序），值为
    {"predicate": ID, "value": "TRUE"|"FALSE"|"UNKNOWN",
    "witness": {"b": action_key, "c": action_key} 或 null,
    "missing": [缺失原因, ...] 或 null}。TRUE 附命中的分支对见证键；UNKNOWN 附
    缺失原因列表（单列，不当作 FALSE）；FALSE 的 witness 与 missing 均为 null。

    错误处理：输入结构非法（缺 branches、标签/枚举非法、类型不符等）抛
    ValueError，消息指明非法字段路径；纯函数，不修改输入、无 I/O。
    """
    _validate_facts(facts)
    wall = facts.get("wall_left")
    branches = sorted(facts["branches"], key=_by_action_key)
    results: Dict[str, Dict[str, Any]] = {}
    for family in FAMILIES:
        open_id, cost_id = FAMILY_PREDICATES[family]
        for predicate_id, kind in ((open_id, "open"), (cost_id, "cost")):
            results[predicate_id] = _evaluate_family_kind(
                branches, wall, family, kind, predicate_id
            )
    return results


def evaluate_predicate(facts: dict, predicate_id: str) -> dict:
    """计算单个机器谓词（§7.3 冻结合同）。

    输入：facts 同 evaluate_predicates；predicate_id 必须是 PREDICATE_IDS 中的
    一个（family_open / family_cost 形式），否则抛 ValueError。

    返回：与 evaluate_predicates 中该谓词逐字段相同的结果 dict（结构见
    evaluate_predicates 的 docstring）。

    错误处理：predicate_id 非法或 facts 结构非法均抛 ValueError 并指明字段。
    """
    if predicate_id not in _PREDICATE_TO_FAMILY_KIND:
        raise ValueError(
            f"predicate_id 必须是八个小写谓词 ID 之一（见 PREDICATE_IDS），实际: {predicate_id!r}"
        )
    _validate_facts(facts)
    family, kind = _PREDICATE_TO_FAMILY_KIND[predicate_id]
    wall = facts.get("wall_left")
    branches = sorted(facts["branches"], key=_by_action_key)
    return _evaluate_family_kind(branches, wall, family, kind, predicate_id)
