# -*- coding: utf-8 -*-
"""C2 根级配对统计、有限档案（8 席）、panel_epoch 通道替换、父代调度与提名。

规范来源：review/llm-guided-heuristic-route-2026-09-15/SEARCH-SPACE-REDESIGN-2026-09-16.md
§8.1（统计量）、§8.3（独立确认合同的提名算法）、§9.1—§9.3（容量资格/选择规则/
panel_epoch/父代与算子调度）、§13 C2 行、§14 T10/T11/T12；contracts/group-dev-v1.json
（H/M 等权声明混合、机会家族开发值=机会/代价两子场景均值各 1/2 冻结混合）。

本模块是纯数据/纯函数实现：不做真实桌赛执行、不读时钟/网络/随机源；同输入恒等
输出（确定性排序，不依赖 dict 迭代序）。

与 src/hangma_bot/offline/evaluation_statistics.py 的复用边界（§13 C2 行要求
"复用 evaluation_statistics"）：

- 复用点 1（语义复用，测试锁死）：抽样单位等权 mean-of-means。本模块按
  source_root_id 聚类、根内先平均再取差、根间等权求 mean_delta——与
  evaluation_statistics.clustered_bootstrap_ci 的点估计（每 scenario 先取组内
  配对差均值、再对 scenario 均值等权平均）是同一语义；tools/test_sitin_archive.py
  用真实 MatchResult 夹具调用 clustered_bootstrap_ci 断言两者数值一致。
- 复用点 2（纪律复用）：无效/缺事实样本不补零、保留原始记录并逐条计数——与
  evaluation_statistics 的 metric None 只计数排除（_paired_diffs_by_scenario 的
  excluded）和 pair_matches 的 unpaired_reasons 同构。
- 不直接调用的原因（边界）：evaluation_statistics 面向 MatchResult 完整桌赛
  双行复式配对 + 聚类 Bootstrap 置信区间；C2 输入是 C1 面板双臂单快照字典
  （u_hook.target=group_advance_v1 的 U/U 区间），且本版要求 95% 正态近似区间
  与 §2 保守配对差区间。类型与区间方法均不同，强行适配会复制第二套语义不同的
  实现，故只共享上述语义/纪律并用测试锁死一致。

统计口径要点（§8.1 逐条）：

- 无效样本（invalid 标记/单臂失败）按 status 标注并保留原始记录，**不补零**、
  不进均值；目标不可计算（执行完成但 U 缺失）单列 uncomputable。
- 同一 source_root_id 跨多窗口/换座/样本只算一个统计根（T10）；根内先平均
  各臂，再取差 d_r。
- 配对差区间按 §2 保守公式：d_low_r = mean(u_low,候选) − mean(u_high,基线)、
  d_high_r = mean(u_high,候选) − mean(u_low,基线)（识别不确定性，与正态近似
  抽样区间分开报告）。
- 自比较（两臂同 candidate_id）d 恒 0，不做两次独立区间运算（§2
  self_comparison：不得把自比较变成 [-1,1]）。
- interval 是**抽样不确定性**的 95% 正态近似，不是识别区间，也不作为反复看数
  后"已证明提升"的证据。
- H/M 分层统计 + group-dev-v1 声明的 0.5/0.5 等权混合值；机会家族开发值 =
  机会/代价两子场景均值各 1/2（冻结条件混合），两子场景原值同时输出。
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
import hashlib
import json
import math
import sys
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

REPO = _PROJECT_ROOT
_SRC = str(_project_file(_PROJECT_ROOT, REPO / "src"))
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

#: 档案产物 schema（§9.1：8 席 = overall×2 + family×4 + exploration×2）。
#: v2（R9 实施包 P6 / 计划 §13）：① 探索席相对**提交后的在案席位**重算（不再把
#: 「冻结的在案席位」与「面板视角探索席」拼接提交）；② 席位排序键换成确定性代价
#: 口径（不含墙上时钟）。席位口径变更 ⇒ 旧 v1 档案的 slots/total_cost 语义不同，
#: 一律不续跑（R9 §11.5：旧身份产物不续跑）。
ARCHIVE_SCHEMA = "sitin-archive/2"
#: 选席口径身份串（§9.1 容量/§9.2 选择规则）：随排序键或探索席重算口径变更升版，
#: 与档案、事务件一起落盘，供跨轮核对"这份席位是按哪一版口径选的"。
#: v3（R9 实施包 P13 / 复审 A4r）：探索席**彼此**按行为签名摘要去重——每选入一个
#: 探索候选即排除其同行为候选并登记重复来源；无第二种行为时第二席留空。旧 v2 档案
#: 的两个探索席可能代表同一行为，席位语义不同，一律不续跑（§9.1 旧身份产物纪律）。
SLOT_SELECTION_VERSION = "sitin-slot-selection/3"
#: 根级配对统计产物 schema（§8.1）。
STATISTICS_SCHEMA = "sitin-stage-statistics/1"
#: 通道 panel_epoch 产物 schema（§9.2 替换复核；根集=核心根+历次已提交刷新根）。
CHANNEL_EPOCH_SCHEMA = "sitin-channel-epoch/1"
#: 提名冻结包 schema（§8.3）。
NOMINATION_SCHEMA = "sitin-nomination/1"
#: 根用途清单 schema（Q2：development_core/development_refresh/confirmation 三分区）。
ROOT_USAGE_SCHEMA = "sitin-root-usage-manifest/1"
#: 根用途三分区（Q2/T13）：只有从未用于生成/选择/诊断/拟合的 confirmation 根
#: 可进独立确认集；development_* 根一经开发通道使用即永久排除在确认集外。
ROOT_USAGES: Tuple[str, ...] = ("development_core", "development_refresh", "confirmation")

#: 四个专长家族（§7.3；与谓词 id 前缀一致）。
FAMILIES: Tuple[str, ...] = ("branch", "chain", "four_white", "baotou")
#: 八谓词子场景 id（§7.3 冻结合同；C1 sitin_predicates_v4.PREDICATE_IDS 同序）。
SUB_SCENARIOS: Tuple[str, ...] = tuple(
    "{0}_{1}".format(family, kind) for family in FAMILIES for kind in ("open", "cost")
)
#: 正常开局面板场景名（§7.1 正常面板：阶段零分完整 2 桌开发阶段）。
SCENARIO_NORMAL = "normal"
#: 对手情景（group-dev-v1 panel.opponent_scenarios：H=三家冻结 V2；M=V2/白守/V1 各一）。
OPPONENT_MIXES: Tuple[str, ...] = ("H", "M")
#: 声明的工程混合目标（group-dev-v1 panel.development_mix：H/M 各 1/2 冻结）。
DECLARED_MIX_WEIGHTS: Dict[str, float] = {"H": 0.5, "M": 0.5}

#: 通道清单：正常通道 + 四家族通道（§9.2 通道面板版本与替换复核）。
CHANNELS: Tuple[str, ...] = ("normal",) + FAMILIES

#: 专长家族的两个子场景侧（§7.3：机会 open / 代价 cost）。
FAMILY_SIDES: Tuple[str, ...] = ("open", "cost")
#: 家族通道每个受影响子场景的刷新根配额（§9.2：每子场景 4 根、H/M 各 2）。
FAMILY_REFRESH_ROOTS_PER_SIDE = 4


def family_channel_of(predicate: Any) -> Optional[str]:
    """子场景谓词 → 家族通道名（"{family}_{kind}" 或族名本身）；非家族谓词返回 None。

    （唯一映射点：计划里的 predicate 是子场景 id，通道名是族名。）
    """

    text = str(predicate or "")
    for family in FAMILIES:
        if text in (family, "{0}_open".format(family), "{0}_cost".format(family)):
            return family
    return None


def family_cell_key(opponent_mix: Any, root_id: Any) -> str:
    """家族证据格键：对手情景 × 根身份。

    家族根身份形如 av-eval-{谓词}:{谓词}:rootNNN，**不含**对手情景（P7b §5.4）：
    同一根被 H 与 M 两个情景各评一次是两个真实实例（对手不同、牌局不同），
    单靠 root_id 做格键会让后者静默覆盖前者，家族两侧/两情景永远无法齐备。
    """

    return "{0}|{1}".format(opponent_mix, root_id)


def family_cell_lookup(rows: Mapping[str, Any], opponent_mix: Any,
                       root_id: Any) -> Optional[Mapping[str, Any]]:
    """家族证据格查询：先试情景限定键，再回退裸根 id（兼容历史/手工记录）。"""

    if not isinstance(rows, Mapping):
        return None
    for key in (family_cell_key(opponent_mix, root_id), str(root_id)):
        record = rows.get(key)
        if isinstance(record, Mapping):
            return record
    return None


def _family_bucket_key(bucket: Mapping[str, Any], root_id: str,
                       record: Mapping[str, Any]) -> str:
    """增量合并时的家族格键：同 root_id 不同对手情景 → 情景限定键（不覆盖）。"""

    existing = bucket.get(root_id)
    if isinstance(existing, Mapping) and \
            existing.get("opponent_mix") != record.get("opponent_mix"):
        return family_cell_key(record.get("opponent_mix"), root_id)
    return root_id


def _channel_slot_key(channel: str) -> str:
    """通道 → 档案席位键：正常通道对应整体席 overall，家族通道同名。

    （歧义处理：epoch 通道名用 §9.2 的"正常通道 normal"，档案席位名用 §9.1 的
    "整体 overall"；本函数是两者之间唯一映射点。）
    """
    return "overall" if channel == "normal" else channel
#: 档案席位容量（§9.1）。
SLOT_CAPACITY: Dict[str, int] = {
    "overall": 2,
    "branch": 1,
    "chain": 1,
    "four_white": 1,
    "baotou": 1,
    "exploration": 2,
}
#: 探索席通道名（§9.1：探索 2 席）。
EXPLORATION_CHANNEL = "exploration"
#: 同行为排除的来源类别（§9.2 规则 4；P13）：在案席持有者 / 已选探索席者。
#: 报告按此区分"谁被谁排除"，使两个来源不混为一谈，也便于事后核对口径。
SEATED_DUPLICATE_BASIS = "seated_holder"
EXPLORATION_DUPLICATE_BASIS = "exploration_seat"
#: **占席通道**（探索席的"剩余安全候选"排除集 = 这些通道的持有者；R9 §13 A 项）。
#: 探索席自身不在其中：它是由本集合派生出的结论，不作自己的排除项。
SEATING_CHANNELS: Tuple[str, ...] = ("overall",) + FAMILIES
#: V2 固定基线身份：只作对照，不占 8 席、不当父代（§9.1；虚拟配对值 0 见 §8.3）。
V2_BASELINE_IDS: Tuple[str, ...] = ("weighted_heuristic_v2",)
#: 人工种子身份（§9.3 初始化）。
SEED_IDS: Tuple[str, ...] = ("efficiency_seed", "route_value_seed")

#: 95% 正态近似 z 值（抽样不确定性区间；非识别区间）。
Z_95 = 1.959963984540054
#: 统计状态：ok / insufficient / invalid_only / uncomputable（§8.1 分别标注）。
STATUSES: Tuple[str, ...] = ("ok", "insufficient", "invalid_only", "uncomputable")

NEWLINE = chr(10)


# ---------------------------------------------------------------------------
# 1. 根级配对统计（§8.1）
# ---------------------------------------------------------------------------


def _arm_u(arm: Optional[Mapping[str, Any]]) -> Tuple[Optional[float], Optional[float]]:
    """臂的 (u_low, u_high)；只有点值 u 时上下界同值，全缺返回 (None, None)。

    不补零：缺 U 就是缺事实，由调用方标注 uncomputable。
    """
    if not isinstance(arm, Mapping):
        return None, None
    point = arm.get("u")
    low = arm.get("u_low")
    high = arm.get("u_high")
    if low is None:
        low = point
    if high is None:
        high = point
    if low is None or high is None:
        return None, None
    return float(low), float(high)


def _u_point(arm: Mapping[str, Any]) -> Optional[float]:
    """臂的点值 U：有点值用点值；只有区间时用中点（工程选择，见模块 docstring）。"""
    low, high = _arm_u(arm)
    if low is None or high is None:
        return None
    if arm.get("u") is not None:
        return float(arm["u"])
    return (low + high) / 2.0


#: 排序代价口径（§9.2 规则 1「整链成本较低」的 tiebreak 键）：确定性预算单元。
SORT_COST_BASIS = "deterministic_budget_units"
#: 墙上时钟/CPU 字段名：**只留档审计，一律不参与席位排序**。这些是实测值，参与
#: tiebreak 会让同一冻结输入跨运行漂移（R9 计划 §13 C 的根因）。
COST_WALL_CLOCK_KEYS: Tuple[str, ...] = ("elapsed_ms", "wall_ms", "wall_sec",
                                         "cpu_sec", "stats_ms", "duration_ms")


def _sample_budget_units(sample: Mapping[str, Any]) -> float:
    """样本的**确定性预算单元**：冻结期望清单声明的完整桌实例数（§11 的预算单位）。

    每窗口两臂各跑 tables_per_arm 桌（Q4 已强制 root_expected 随样本落档）→
    单元 = 臂数 × 每臂桌数。清单缺失时退回 1.0/窗口（粗粒度，但仍是冻结输入的
    纯函数，不消费任何墙钟读数）。
    """
    expected = sample.get("root_expected") if isinstance(sample, Mapping) else None
    arms = expected.get("arms") if isinstance(expected, Mapping) else None
    tables = expected.get("tables_per_arm") if isinstance(expected, Mapping) else None
    n_arms = (len(arms) if isinstance(arms, Sequence) and not isinstance(arms, str)
              else 1)
    n_tables = (int(tables) if isinstance(tables, int) and not isinstance(tables, bool)
                else 1)
    return float(max(n_arms, 1) * max(n_tables, 1))


def _sample_cost(sample: Mapping[str, Any]) -> float:
    """样本**排序代价**（§9.2 规则 1 tiebreak「整链成本较低」）——确定性口径。

    R9 计划 §13 C 裁定：排序键必须是**冻结输入的纯函数**，elapsed_ms 等墙上时钟
    实测值只留档与审计。取数优先级：

      ① cost 为数值：冻结输入里显式声明的确定性费用（旧档案/夹具形状）原样使用；
      ② cost 为映射：显式 budget_units 优先；否则取**排除墙钟/CPU 字段**后的数值和；
         只剩墙钟字段时（生产自然面板形状 {"elapsed_ms": …}）转 ③；
      ③ 冻结期望清单的完整桌实例数（臂数 × 每臂桌数；§11 预算单位）；
      ④ 全无 → 0.0（宁可不分辨，也不消费墙钟噪声）。

    口径后果（写进 P6 报告）：同一矩阵下 ③ 退化为常量，tiebreak 落到 candidate_id
    ——这正是"同输入同结论"所要求的；覆盖/每臂桌数不同的候选仍按预算单位区分。
    """
    cost = sample.get("cost") if isinstance(sample, Mapping) else None
    if isinstance(cost, bool) or cost is None:
        return _sample_budget_units(sample)
    if isinstance(cost, (int, float)):
        return float(cost)
    if isinstance(cost, Mapping):
        explicit = cost.get("budget_units")
        if isinstance(explicit, (int, float)) and not isinstance(explicit, bool):
            return float(explicit)
        values = [float(v) for key, v in cost.items()
                  if isinstance(v, (int, float)) and not isinstance(v, bool)
                  and str(key) not in COST_WALL_CLOCK_KEYS]
        if values:
            return sum(values)
        return _sample_budget_units(sample)
    return _sample_budget_units(sample)


def _sample_recorded_cost(sample: Mapping[str, Any]) -> float:
    """样本**记录代价**（留档与审计）：数值原样；dict 取 total 或数值和。

    与 _sample_cost 分开：本函数保留墙钟实测值（含 elapsed_ms），只用于审计与报告，
    **不参与任何排序键**（R9 §13 C）。
    """
    cost = sample.get("cost")
    if isinstance(cost, bool) or cost is None:
        return 0.0
    if isinstance(cost, (int, float)):
        return float(cost)
    if isinstance(cost, Mapping):
        total = cost.get("total")
        if isinstance(total, (int, float)) and not isinstance(total, bool):
            return float(total)
        return float(sum(v for v in cost.values()
                         if isinstance(v, (int, float)) and not isinstance(v, bool)))
    return 0.0


def _is_self_comparison(sample: Mapping[str, Any]) -> bool:
    """自比较判定：两臂 candidate_id 相同（§2 self_comparison）。"""
    if sample.get("self_comparison") is True:
        return True
    arms = sample.get("arms") or {}
    baseline = arms.get("baseline") or {}
    candidate = arms.get("candidate") or {}
    ids = (baseline.get("candidate_id"), candidate.get("candidate_id"))
    return ids[0] is not None and ids[0] == ids[1]


def _arm_failed(arm: Any) -> bool:
    """单臂失败判定：显式 usable=False / 状态非 complete / 异常信息非空。"""
    if not isinstance(arm, Mapping):
        return True
    if arm.get("usable") is False:
        return True
    status = arm.get("status")
    if status is not None and status != "complete":
        return True
    if arm.get("error"):
        return True
    return False


def classify_sample(sample: Mapping[str, Any]) -> Tuple[str, Optional[str]]:
    """单样本三态分类：usable / invalid / uncomputable（附原因，不补零）。

    - invalid：invalid 标记、invalid_reasons 非空、arms 缺失、任一臂失败、
      source_root_id/scenario/opponent_mix/candidate_id 缺失或非法；
    - uncomputable：执行完成但任一臂 U（u/u_low/u_high）缺失（目标不可计算）；
    - usable：进入根级聚合。
    """
    if not isinstance(sample, Mapping):
        return "invalid", "样本不是对象"
    if sample.get("invalid") is True:
        return "invalid", "样本标记 invalid"
    if sample.get("invalid_reasons"):
        return "invalid", "invalid_reasons 非空: {0}".format(list(sample["invalid_reasons"]))
    if sample.get("completeness") == "invalid":
        return "invalid", "completeness=invalid"
    root_id = sample.get("source_root_id")
    if not isinstance(root_id, str) or not root_id:
        return "invalid", "缺少 source_root_id，无法按根聚类"
    candidate_id = sample.get("candidate_id")
    if not isinstance(candidate_id, str) or not candidate_id:
        return "invalid", "缺少 candidate_id"
    scenario = sample.get("scenario")
    known = SUB_SCENARIOS + (SCENARIO_NORMAL,)
    if scenario not in known:
        return "invalid", "未知 scenario {0!r}（八谓词之一或 normal）".format(scenario)
    if sample.get("opponent_mix") not in OPPONENT_MIXES:
        return "invalid", "opponent_mix 必须是 {0}".format(list(OPPONENT_MIXES))
    arms = sample.get("arms")
    if not isinstance(arms, Mapping):
        return "invalid", "缺少 arms 双臂记录"
    for arm_name in ("baseline", "candidate"):
        if _arm_failed(arms.get(arm_name)):
            return "invalid", "臂 {0} 执行失败（单臂失败整样本 invalid，T16）".format(arm_name)
    for arm_name in ("baseline", "candidate"):
        low, high = _arm_u(arms.get(arm_name))
        if low is None or high is None:
            return "uncomputable", "臂 {0} 缺终端 U/u_low/u_high（目标不可计算）".format(arm_name)
    return "usable", None


def _sample_deltas(sample: Mapping[str, Any]) -> Dict[str, Any]:
    """单窗口（样本）配对差：d_point/d_low/d_high + 未分辨标记。

    d_low = u_low(候选) − u_high(基线)、d_high = u_high(候选) − u_low(基线)
    （§2 保守配对差区间：识别不确定性）。自比较（同 candidate_id）d 恒 0，
    不做两次独立区间运算（§2 self_comparison）。
    """
    arms = sample["arms"]
    cand, base = arms["candidate"], arms["baseline"]
    if _is_self_comparison(sample):
        return {"d_point": 0.0, "d_low": 0.0, "d_high": 0.0,
                "unresolved": False, "self": True}
    c_low, c_high = _arm_u(cand)
    b_low, b_high = _arm_u(base)
    c_point, b_point = _u_point(cand), _u_point(base)
    return {
        "d_point": c_point - b_point,
        "d_low": c_low - b_high,
        "d_high": c_high - b_low,
        "unresolved": (c_low < c_high) or (b_low < b_high),
        "self": False,
    }


def _mean(values: Sequence[float]) -> Optional[float]:
    """等权均值；空序列返回 None（不补零）。"""
    if not values:
        return None
    return sum(values) / len(values)


def _se_and_interval(values: Sequence[float]) -> Tuple[Optional[float], Optional[list]]:
    """根间标准误与 95% 正态近似区间（抽样不确定性，非识别区间）。

    n>=2 用样本标准差(ddof=1)/sqrt(n)；n<2 无标准误（None），区间也为 None，
    由面板 status=insufficient 表达，不伪造零误差。
    """
    n = len(values)
    if n < 2:
        return None, None
    mean = sum(values) / n
    variance = sum((v - mean) ** 2 for v in values) / (n - 1)
    se = math.sqrt(variance) / math.sqrt(n)
    return se, [mean - Z_95 * se, mean + Z_95 * se]


def _panel_statistics(
    samples: Sequence[Mapping[str, Any]],
    *,
    min_roots: int,
) -> Dict[str, Any]:
    """一个面板（同候选 × 同 scenario × 同对手情景）的根级配对统计。

    逐条实现 §8.1：按 source_root_id 聚类（同根多窗口先平均，T10）；无效样本
    不补零、保留计数；U 区间同时给上下界两套统计；自比较 d 恒 0。
    """
    usable: List[Mapping[str, Any]] = []
    invalid: List[Mapping[str, Any]] = []
    uncomputable: List[Mapping[str, Any]] = []
    n_invalid = n_uncomputable = 0
    for sample in samples:
        status, _reason = classify_sample(sample)
        if status == "usable":
            usable.append(sample)
        elif status == "invalid":
            invalid.append(sample)
            n_invalid += 1
        else:
            uncomputable.append(sample)
            n_uncomputable += 1

    # Q4：聚合前先按根聚合**全部**样本（含无效/不可计算）做整根校验——
    # 任一臂失败/漏行/重复行使整根失效，不用剩余座位算选择值（T16）。
    by_root_all: Dict[str, List[Mapping[str, Any]]] = {}
    for sample in samples:
        root_id = sample.get("source_root_id") if isinstance(sample, Mapping) else None
        if isinstance(root_id, str) and root_id:
            by_root_all.setdefault(root_id, []).append(sample)

    invalid_roots: List[Dict[str, Any]] = []
    for root_id in sorted(by_root_all):
        members_all = by_root_all[root_id]
        reasons: List[str] = []
        for member in members_all:
            member_status, member_reason = classify_sample(member)
            if member_status != "usable":
                reasons.append("{0}样本：{1}".format(member_status, member_reason))
        # Q7：同 ID 不同内容的根直接拒绝（内容摘要校验，fail-closed）。
        digests = sorted({str(member.get("root_content_digest"))
                          for member in members_all
                          if member.get("root_content_digest")})
        if len(digests) > 1:
            raise ValueError(
                "根身份碰撞（Q7）：根 {0!r} 同 ID 不同内容摘要 {1}——拒绝混入同一"
                "统计（换 panel_seed/根序号重建，禁止目录名后缀补丁）".format(
                    root_id, digests))
        # Q4：冻结期望座位清单——根内行数必须与期望座位数一致（漏行/重复行）。
        expected_seats: Optional[int] = None
        for member in members_all:
            expected = member.get("root_expected")
            if isinstance(expected, Mapping) and isinstance(expected.get("seats"), int):
                expected_seats = max(expected_seats or 0, int(expected["seats"]))
        if expected_seats is not None and len(members_all) != expected_seats:
            reasons.append("清单不符：根内 {0} 行 ≠ 期望 {1} 座位行（漏行/重复行）".format(
                len(members_all), expected_seats))
        if reasons:
            invalid_roots.append({"root_id": root_id, "reasons": reasons})
    gated_roots = {row["root_id"] for row in invalid_roots}

    by_root: Dict[str, List[Mapping[str, Any]]] = {}
    for sample in usable:
        if sample["source_root_id"] not in gated_roots:
            by_root.setdefault(sample["source_root_id"], []).append(sample)

    root_rows: List[Dict[str, Any]] = []
    for root_id in sorted(by_root):
        members = by_root[root_id]
        deltas = [_sample_deltas(m) for m in members]
        digest = next((str(m.get("root_content_digest")) for m in members
                       if m.get("root_content_digest")), None)
        root_rows.append({
            "root_id": root_id,
            "n_windows": len(members),
            "d_point": _mean([d["d_point"] for d in deltas]),
            "d_low": _mean([d["d_low"] for d in deltas]),
            "d_high": _mean([d["d_high"] for d in deltas]),
            "unresolved": any(d["unresolved"] for d in deltas),
            "self": all(d["self"] for d in deltas),
            "role": members[0].get("root_role", "core"),
            "usage": members[0].get("root_usage", "development_core"),
            "root_content_digest": digest,
            "opponent_mix": members[0]["opponent_mix"],
            # 排序用途（确定性，§9.2 规则 1）；recorded_cost 是墙钟留档（R9 §13 C）。
            "cost": sum(_sample_cost(m) for m in members),
            "recorded_cost": sum(_sample_recorded_cost(m) for m in members),
        })

    d_points = [r["d_point"] for r in root_rows]
    d_lows = [r["d_low"] for r in root_rows]
    d_highs = [r["d_high"] for r in root_rows]
    all_self = bool(root_rows) and all(r["self"] for r in root_rows)
    if all_self:
        # 自比较：两臂完全相同 → d 恒 0（§2），不做两次独立区间运算。
        mean_delta, se, interval = 0.0, 0.0, [0.0, 0.0]
        mean_low, se_low, interval_low = 0.0, 0.0, [0.0, 0.0]
        mean_high, se_high, interval_high = 0.0, 0.0, [0.0, 0.0]
    else:
        mean_delta = _mean(d_points)
        se, interval = _se_and_interval(d_points)
        mean_low = _mean(d_lows)
        se_low, interval_low = _se_and_interval(d_lows)
        mean_high = _mean(d_highs)
        se_high, interval_high = _se_and_interval(d_highs)

    n_roots = len(root_rows)
    if n_roots == 0:
        status = "invalid_only" if n_invalid else "uncomputable"
    elif n_roots < min_roots:
        status = "insufficient"
    else:
        status = "ok"

    return {
        "n_samples": len(samples),
        "n_roots": n_roots,
        "n_invalid_samples": n_invalid,
        "n_uncomputable_samples": n_uncomputable,
        "n_invalid_roots": len(invalid_roots),
        "invalid_roots": invalid_roots,
        # Q4：清单完整 = 本面板没有任何整根失效（无失败/漏行/重复行根）。
        # manifest_complete=False 的面板不得进入档案排序/提名/效果结论。
        "manifest_complete": not invalid_roots,
        "n_refresh_roots": sum(1 for r in root_rows if r["role"] == "refresh"),
        "status": status,
        "mean_delta": mean_delta,
        "standard_error": se,
        "interval_95": interval,
        "interval_kind": "sampling_uncertainty_normal_approx",
        "interval_note": "95% 正态近似抽样不确定性区间，非识别区间，不作为已证明提升的证据",
        "self_comparison": all_self,
        "delta_bounds": {
            "mean_delta_low": mean_low,
            "mean_delta_high": mean_high,
            "standard_error_low": se_low,
            "standard_error_high": se_high,
            "interval_95_low": interval_low,
            "interval_95_high": interval_high,
            "unresolved_roots": sum(1 for r in root_rows if r["unresolved"]),
            "note": "识别区间（缺 god_count 等事实造成）：d_low=候选U下界−基线U上界、"
                    "d_high=候选U上界−基线U下界（§2 保守配对）；与 interval_95 分开报告",
        },
        "roots": [r["root_id"] for r in root_rows],
        "root_rows": root_rows,
        "invalid_records": invalid,
        "uncomputable_records": uncomputable,
    }


def _panel_value(panel: Optional[Dict[str, Any]], key: str) -> Optional[float]:
    """面板取值：mean_delta 在顶层；mean_delta_low/high 在 delta_bounds 内。"""
    if panel is None:
        return None
    if key in ("mean_delta_low", "mean_delta_high"):
        return panel["delta_bounds"].get(key)
    return panel.get(key)


def _declared_mix_value(panels_by_mix: Mapping[str, Dict[str, Any]], key: str) -> Optional[float]:
    """H/M 等权声明混合值（group-dev-v1：0.5/0.5 冻结）；任一混合缺数据为 None。

    不偷偷改权重：缺某一混合就输出 None 并由 status 表达，不用单侧值冒充混合。
    """
    values = {}
    for mix in OPPONENT_MIXES:
        values[mix] = _panel_value(panels_by_mix.get(mix), key)
    if any(v is None for v in values.values()):
        return None
    return sum(DECLARED_MIX_WEIGHTS[mix] * values[mix] for mix in OPPONENT_MIXES)


def _scenario_block(
    samples: Sequence[Mapping[str, Any]],
    *,
    min_roots: int,
) -> Dict[str, Any]:
    """一个 scenario 的分层块：H/M 两面板 + 声明混合值（不猜官方对手比例）。"""
    by_mix: Dict[str, List[Mapping[str, Any]]] = {mix: [] for mix in OPPONENT_MIXES}
    for sample in samples:
        # 无效/不可计算样本只保留计数（classify 已入全局清单），不进面板分组：
        # mix 非法的样本在此被跳过而不是撑爆分层字典。
        if sample.get("opponent_mix") in OPPONENT_MIXES:
            by_mix[sample["opponent_mix"]].append(sample)
    panels = {mix: _panel_statistics(by_mix[mix], min_roots=min_roots)
              for mix in OPPONENT_MIXES if by_mix[mix]}
    return {
        "panels": panels,
        "declared_mix": {
            "weights": dict(DECLARED_MIX_WEIGHTS),
            "mean_delta": _declared_mix_value(panels, "mean_delta"),
            "mean_delta_low": _declared_mix_value(panels, "mean_delta_low"),
            "mean_delta_high": _declared_mix_value(panels, "mean_delta_high"),
            "status": "ok" if len(panels) == len(OPPONENT_MIXES) else "missing_mix",
            "note": "声明的工程混合目标（group-dev-v1 development_mix）；"
                    "H/M 分层原值同时保留，不以外推官方对手比例",
        },
    }


def paired_stage_statistics(
    samples: Sequence[Mapping[str, Any]],
    *,
    min_roots: int = 2,
) -> Dict[str, Any]:
    """根级配对统计主入口（§8.1）。

    输入样本 = C1 面板一条双臂记录（source_root_id/scenario/opponent_mix/
    candidate_id/arms{baseline,candidate}/invalid 标记/费用字段；scenario 为八
    谓词之一或 normal）。输出按 (candidate_id, scenario, opponent_mix) 分面板：
    n_roots、mean_delta、standard_error（根间）、interval_95（正态近似，抽样
    不确定性非识别区间）、status（ok/insufficient/invalid_only/uncomputable）、
    delta_bounds（U 区间上下界两套，§2 保守配对）；无效/不可计算样本保留原始
    记录不补零；同根多窗口只算一个统计根（T10）；自比较 d 恒 0；每候选另给
    H/M 分层 + 声明混合 + 机会家族开发值（机会/代价两子场景均值各 1/2，两子
    场景原值同时输出）。
    """
    by_candidate: Dict[str, List[Mapping[str, Any]]] = {}
    invalid_records: List[Mapping[str, Any]] = []
    uncomputable_records: List[Mapping[str, Any]] = []
    for sample in samples:
        status, _ = classify_sample(sample)
        if status == "invalid":
            invalid_records.append(sample)
        elif status == "uncomputable":
            uncomputable_records.append(sample)
        # 无效/不可计算样本也归入候选面板（candidate_id 可用时），使面板能
        # 标注 invalid_only/uncomputable；_panel_statistics 只把 usable 样本
        # 计入根级统计，其余保留原记录。
        candidate_id = sample.get("candidate_id") if isinstance(sample, Mapping) else None
        if isinstance(candidate_id, str) and candidate_id:
            by_candidate.setdefault(candidate_id, []).append(sample)

    legal_scenarios = SUB_SCENARIOS + (SCENARIO_NORMAL,)
    by_candidate_out: Dict[str, Any] = {}
    for candidate_id in sorted(by_candidate):
        candidate_samples = by_candidate[candidate_id]
        by_scenario: Dict[str, List[Mapping[str, Any]]] = {}
        for sample in candidate_samples:
            # 非法 scenario 的样本不形成面板（其违规已入全局 invalid 清单）；
            # 合法 scenario 的无效样本保留在面板中以标注 invalid_only。
            if sample.get("scenario") in legal_scenarios:
                by_scenario.setdefault(sample["scenario"], []).append(sample)
        scenarios = {
            scenario: _scenario_block(members, min_roots=min_roots)
            for scenario, members in sorted(by_scenario.items())
        }
        family_values: Dict[str, Any] = {}
        for family in FAMILIES:
            open_block = scenarios.get("{0}_open".format(family))
            cost_block = scenarios.get("{0}_cost".format(family))

            def _sub_value(block: Optional[Dict[str, Any]]) -> Optional[float]:
                if block is None:
                    return None
                return block["declared_mix"]["mean_delta"]

            open_value, cost_value = _sub_value(open_block), _sub_value(cost_block)
            value = None
            if open_value is not None and cost_value is not None:
                value = 0.5 * open_value + 0.5 * cost_value
            family_values[family] = {
                "value": value,
                "open": {"declared_mix_value": open_value},
                "cost": {"declared_mix_value": cost_value},
                "complete": value is not None,
                "note": "机会家族开发值=机会/代价两子场景均值各 1/2（冻结条件混合，"
                        "group-dev-v1）；两子场景原值同时输出，不能只报有利部分",
            }
        by_candidate_out[candidate_id] = {
            "panels": scenarios,
            "family_development_values": family_values,
        }

    return {
        "schema": STATISTICS_SCHEMA,
        "n_samples": len(samples),
        "min_roots": min_roots,
        "by_candidate": by_candidate_out,
        "invalid_count": len(invalid_records),
        "uncomputable_count": len(uncomputable_records),
        "invalid_records": invalid_records,
        "uncomputable_records": uncomputable_records,
        "notes": [
            "抽样单位=来源根（source_root_id）：同根多窗口/换座先根内平均，不放大 n（T10）",
            "interval_95 为抽样不确定性（正态近似），与 delta_bounds 识别区间分开",
            "无效样本不补零：原始记录保留于 invalid_records/uncomputable_records",
        ],
    }


# ---------------------------------------------------------------------------
# 2. 有限档案 Archive（8 席，§9.1/§9.2）
# ---------------------------------------------------------------------------


def _slot_eligibility(entry: Mapping[str, Any]) -> Tuple[bool, Optional[str]]:
    """席位与父代资格（§9.1；Q6 加固）：只接受绑定当前完整身份的安全 PASS。

    - 安全状态非 PASS（UNKNOWN/FAIL/缺失/任意其它值）不得占席当父代；
    - Mapping 形式的 PASS 若声明了 bound_candidate_id 必须与当前条目一致
      （过期/串档拒绝）；stale=True 视为过期拒绝；
    - V2 固定基线不占席；无数据不得用自报价值填档（sort_value=None 落空）。
    """
    candidate_id = entry.get("candidate_id")
    if entry.get("kind") == "v2_baseline" or candidate_id in V2_BASELINE_IDS:
        return False, "V2 是固定比较基线，不占 8 席"
    safety = entry.get("safety")
    status = safety.get("status") if isinstance(safety, Mapping) else safety
    if status != "PASS":
        return False, "安全状态 {0!r} 非 PASS：UNKNOWN/FAIL/缺失/过期均不得入档当父代（Q6）".format(status)
    if isinstance(safety, Mapping):
        bound = safety.get("bound_candidate_id")
        if bound is not None and bound != candidate_id:
            return False, "安全 PASS 绑定身份 {0!r} 与当前候选 {1!r} 不符（过期/串档，Q6）".format(bound, candidate_id)
        if safety.get("stale") is True:
            return False, "安全 PASS 已标记过期（stale，Q6）"
    if entry.get("effect_failure_unresolved"):
        return False, "效果执行故障未修复，不得占席或当父代"
    return True, None


def _overall_summary(candidate_stats: Mapping[str, Any]) -> Optional[Dict[str, Any]]:
    """整体席排序材料（§9.2 规则 1）：正常面板声明混合差值下界均值 + 未分辨标记。"""
    normal = candidate_stats.get("panels", {}).get(SCENARIO_NORMAL)
    if normal is None:
        return None
    panels = normal["panels"]
    # Q4：清单未补齐（任一根整根失效/漏行）本批不得进档案排序/提名/效果结论。
    if not all(p.get("manifest_complete", True) for p in panels.values()):
        return None
    # 声明混合需要 H/M 两层都有可用根：缺任一层 mean_delta_low 为 None，
    # 不填零争席（§9.1"缺某一子场景不填零争席"的同构纪律）。
    sort_value = normal["declared_mix"]["mean_delta_low"]
    if sort_value is None:
        return None
    n_roots = sum(p["n_roots"] for p in panels.values())
    unresolved = sum(p["delta_bounds"]["unresolved_roots"] for p in panels.values())
    # §9.2 规则 1 第 3 键：**确定性**整链成本（预算单元，R9 §13 C）；墙钟实测值
    # 只进 recorded_total_cost（留档审计），绝不参与排序。
    total_cost = sum(sum(r["cost"] for r in p["root_rows"]) for p in panels.values())
    recorded_cost = sum(sum(r.get("recorded_cost") or 0.0 for r in p["root_rows"])
                        for p in panels.values())
    return {
        "sort_value": sort_value,
        "mean_delta": normal["declared_mix"]["mean_delta"],
        "unknown_ratio": (unresolved / n_roots) if n_roots else None,
        "total_cost": total_cost,
        "cost_basis": SORT_COST_BASIS,
        "recorded_total_cost": recorded_cost,
        "n_roots": n_roots,
        "unresolved": unresolved > 0,
        "note": "目标有区间时用差值下界均值排序并标未分辨（§9.2 规则 1）",
        "cost_note": ("排序键为确定性预算单元（完整桌实例数，§11 预算单位）；"
                      "elapsed_ms 等墙钟实测值只记在 recorded_total_cost（R9 §13 C）"),
    }


def _family_summary(candidate_stats: Mapping[str, Any]) -> Dict[str, Dict[str, Any]]:
    """家族席排序材料（§9.2 规则 2）：该族机会/代价两子场景等权均值最大者。

    缺某一子场景不填零争席（complete=False），可保留探索身份。
    """
    values = candidate_stats.get("family_development_values", {})
    panels = candidate_stats.get("panels", {})
    out: Dict[str, Dict[str, Any]] = {}
    for family in FAMILIES:
        block = values.get(family) or {}
        open_block = panels.get("{0}_open".format(family))
        cost_block = panels.get("{0}_cost".format(family))
        manifest_ok = True
        n_roots = 0
        unresolved = 0
        total_cost = 0.0
        recorded_cost = 0.0
        for sub_block in (open_block, cost_block):
            if sub_block is None:
                continue
            for panel in sub_block["panels"].values():
                if not panel.get("manifest_complete", True):
                    manifest_ok = False  # Q4：清单未补齐不进家族席排序
                n_roots += panel["n_roots"]
                unresolved += panel["delta_bounds"]["unresolved_roots"]
                total_cost += sum(r["cost"] for r in panel["root_rows"])
                recorded_cost += sum(r.get("recorded_cost") or 0.0
                                     for r in panel["root_rows"])
        out[family] = {
            "manifest_complete": manifest_ok,
            "value": block.get("value"),
            "complete": bool(block.get("complete")),
            "open_value": (block.get("open") or {}).get("declared_mix_value"),
            "cost_value": (block.get("cost") or {}).get("declared_mix_value"),
            "unknown_ratio": (unresolved / n_roots) if n_roots else None,
            "total_cost": total_cost,
            "cost_basis": SORT_COST_BASIS,
            "recorded_total_cost": recorded_cost,
            "n_roots": n_roots,
            "unresolved": unresolved > 0,
        }
    return out


def family_side_status(entry: Mapping[str, Any], channel: str) -> Dict[str, Any]:
    """家族候选的**两侧登记**（机会 / 代价）：逐侧根数、情景覆盖、是否齐备。

    入席判据（§9.2 规则 2）必须两侧都可算（complete）才成立：任一侧缺对手情景
    或根本没有根记录 → 该侧 incomplete，缺格标「输入不足」，不填零争席。
    """

    evals = entry.get("family_evaluations") or {}
    block = (entry.get("family") or {}).get(channel) or {}
    out: Dict[str, Any] = {"channel": channel,
                           "quota_per_mix": SCENARIO_ROOT_QUOTA,
                           "quota_note": ("每侧 H/M 各 {0} 根配额（§7.3）；缺格标"
                                          "输入不足".format(SCENARIO_ROOT_QUOTA))}
    for side in FAMILY_SIDES:
        sub = "{0}_{1}".format(channel, side)
        rows = evals.get(sub) or {}
        records = [record for record in rows.values()
                   if isinstance(record, Mapping)]
        mixes = sorted({str(record.get("opponent_mix")) for record in records
                        if record.get("opponent_mix")})
        missing_mixes = [mix for mix in OPPONENT_MIXES if mix not in mixes]
        out[side] = {
            "sub_scenario": sub, "n_cells": len(rows), "n_roots": len(records),
            "mixes": mixes, "missing_mixes": missing_mixes,
            "declared_mix_value": block.get(side + "_value"),
            "complete": bool(records) and not missing_mixes,
            "note": ("机会/代价两侧齐备才入席（缺一侧不填零争席）"
                     if side == "open" else ""),
        }
    out["complete"] = bool(block.get("complete")) and all(
        out[side]["complete"] for side in FAMILY_SIDES)
    out["value"] = block.get("value")
    out["manifest_complete"] = block.get("manifest_complete", True)
    return out


#: 每（子场景 × 对手情景）格的开发根配额（§7.3 首版配额：每子场景首批目标 4 个
#: 独立来源根，H/M 各 2）。缺配额即"输入不足"，不当已知。
SCENARIO_ROOT_QUOTA = 2
#: 场景矩阵的格子清单：正常开局面板 + 八谓词子场景（§7.3）。
MATRIX_SCENARIOS: Tuple[str, ...] = (SCENARIO_NORMAL,) + SUB_SCENARIOS


#: 行为签名**首选动作口径的唯一来源**（复审 R8 §5 M2）：签名由
#: sitin_model_admission.behavior_signature 产出，其中的 action_key 直接来自
#: 生产排序 hangma_bot.policy.action_value.batch_to_ranked_candidates
#: （分数降序、同分按 action_key 升序；原始分数，不先舍入）。
#: 档案侧只**消费**已确定的 action_key，不重新排序、不做任何舍入：
#: 消费端若再写一遍取最大值（尤其是先 round 再取最大），就会与生产分叉出第二套
#: 口径——等行为的正比例缩放会被误判成行为差异。
BEHAVIOR_SIGNATURE_ORDER_SOURCE = (
    "hangma_bot.policy.action_value.batch_to_ranked_candidates（生产排序，"
    "经 sitin_model_admission.behavior_signature 产出）")


def behavior_signature_digest(signature: Optional[Mapping[str, Any]]) -> Optional[str]:
    """行为签名摘要（首选动作 + 未知掩码）；无窗口证据返回 None。

    签名相同 ⇔ 冻结窗口上的首选动作与缺失掩码逐窗一致。无窗口（未取得任何行为
    证据）返回 None——不把"没跑过"当成"与谁都一样"（§9.2 规则 4 的行为去重纪律）。

    摘要**只读** window_id / action_key / missing，以及真实面板可选的
    plan_signature（生产计划的动作序列、紧急标记和修订号），不重算分数、不做舍入（口径见
    BEHAVIOR_SIGNATURE_ORDER_SOURCE）：首选动作是上游按生产排序定好的结果，档案侧
    再排一次就是第二套实现（复审 R8 §5 M2 反例）。
    """

    if not isinstance(signature, Mapping):
        return None
    if signature.get("comparable") is False:
        return None
    windows = list(signature.get("windows") or ())
    if not windows:
        return None
    payload = [[str(row.get("window_id")), row.get("action_key"),
                bool(row.get("missing"))] + ([row["plan_signature"]]
                    if "plan_signature" in row else []) for row in windows
               if isinstance(row, Mapping)]
    if not payload:
        return None
    text = json.dumps(payload, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _panel_block_from_rows(rows: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    """由**存储的根记录**重建一个面板块（字段与 _panel_statistics 同形状）。

    增量合并后必须能从累计根记录重算均值/未知比例/成本，否则"补齐不覆盖"只是
    换了个地方丢证据。未分辨根（unknown）仍计入 n_roots 并单列计数，不补零。
    """

    materialized = [dict(row) for row in rows]
    resolved = [row for row in materialized if not row.get("unknown")]

    def _values(key: str) -> List[float]:
        return [float(row[key]) for row in resolved if row.get(key) is not None]

    return {
        "n_samples": len(materialized),
        "n_roots": len(materialized),
        "mean_delta": _mean(_values("d_point")),
        "standard_error": None,
        "interval_95": None,
        "status": ("ok" if resolved else
                   ("insufficient" if not materialized else "uncomputable")),
        "delta_bounds": {
            "mean_delta_low": _mean(_values("d_low")),
            "mean_delta_high": _mean(_values("d_high")),
            "unresolved_roots": len(materialized) - len(resolved),
        },
        "root_rows": materialized,
        "manifest_complete": True,
        "rebuilt_from_root_records": True,
    }


def _scenario_block_from_records(records: Mapping[str, Mapping[str, Any]],
                                 manifest: Optional[Mapping[str, bool]] = None,
                                 *, scenario: str = "") -> Dict[str, Any]:
    """一个 scenario 的分层块：按 §8.1 同语义从根记录重建 H/M 两面板+声明混合。

    manifest[(scenario, mix)] 记录该面板本批是否清单完整（Q4）；False 即该面板
    不得进档案排序/提名（不得拿"剩余根"重算均值当完整面板）。
    """

    by_mix: Dict[str, List[Mapping[str, Any]]] = {}
    for root_id in sorted(records):
        rec = records[root_id]
        mix = rec.get("opponent_mix")
        if mix not in OPPONENT_MIXES:
            continue
        by_mix.setdefault(mix, []).append(dict(rec, root_id=root_id))
    panels = {mix: _panel_block_from_rows(rows) for mix, rows in sorted(by_mix.items())}
    for mix, block in panels.items():
        key = "{0}|{1}".format(scenario, mix)
        if manifest is not None and manifest.get(key) is False:
            block["manifest_complete"] = False
    return {
        "panels": panels,
        "declared_mix": {
            "weights": dict(DECLARED_MIX_WEIGHTS),
            "mean_delta": _declared_mix_value(panels, "mean_delta"),
            "mean_delta_low": _declared_mix_value(panels, "mean_delta_low"),
            "mean_delta_high": _declared_mix_value(panels, "mean_delta_high"),
            "status": ("ok" if len(panels) == len(OPPONENT_MIXES) else "missing_mix"),
            "note": "声明的工程混合目标（group-dev-v1 development_mix）；缺混合不填零",
        },
        "rebuilt_from_root_records": True,
    }


def _stats_from_root_records(normal_evals: Mapping[str, Any],
                             family_evals: Mapping[str, Any],
                             manifest: Optional[Mapping[str, bool]] = None
                             ) -> Dict[str, Any]:
    """由累计根记录重建 candidate_stats（形状与 paired_stage_statistics 一致）。"""

    panels: Dict[str, Any] = {}
    if normal_evals:
        panels[SCENARIO_NORMAL] = _scenario_block_from_records(
            normal_evals, manifest, scenario=SCENARIO_NORMAL)
    for sub in sorted(family_evals):
        rows = family_evals.get(sub) or {}
        if rows:
            panels[sub] = _scenario_block_from_records(rows, manifest, scenario=sub)
    family_values: Dict[str, Any] = {}
    for family in FAMILIES:
        open_block = panels.get("{0}_open".format(family))
        cost_block = panels.get("{0}_cost".format(family))
        open_value = (open_block or {}).get("declared_mix", {}).get("mean_delta")
        cost_value = (cost_block or {}).get("declared_mix", {}).get("mean_delta")
        value = (0.5 * open_value + 0.5 * cost_value
                 if open_value is not None and cost_value is not None else None)
        family_values[family] = {
            "value": value,
            "open": {"declared_mix_value": open_value},
            "cost": {"declared_mix_value": cost_value},
            "complete": value is not None,
            "note": "机会家族开发值=机会/代价两子场景均值各 1/2（冻结条件混合）",
        }
    return {"panels": panels, "family_development_values": family_values}


def _known_roots_per_cell(normal_evals: Mapping[str, Any],
                          family_evals: Mapping[str, Any]) -> Dict[str, Dict[str, List[str]]]:
    """每个（scenario × mix）格子里已取得的**完整根身份**（root_id）清单。"""

    out: Dict[str, Dict[str, List[str]]] = {}

    def _add(scenario: str, records: Mapping[str, Any]) -> None:
        bucket = out.setdefault(scenario, {mix: [] for mix in OPPONENT_MIXES})
        for root_id in sorted(records):
            mix = (records[root_id] or {}).get("opponent_mix")
            if mix in OPPONENT_MIXES:
                bucket[mix].append(root_id)

    _add(SCENARIO_NORMAL, normal_evals)
    for sub in family_evals:
        _add(sub, family_evals.get(sub) or {})
    return out


def evaluation_matrix(normal_evals: Mapping[str, Any],
                      family_evals: Mapping[str, Any]) -> Dict[str, Any]:
    """待评价场景矩阵（§7.3）：每格标 known / input_gap，缺格不伪装成已知。

    格子 = 正常开局面板 + 八谓词子场景，各 × H/M。配额来自 §7.3 首版配额
    （每子场景 H/M 各 2 根）；配额未满或未取得根一律 status=input_gap 并给出
    原因文本"输入不足"。小批次可以只补部分格，但不得据此宣称全搜索空间已验收。
    """

    known = _known_roots_per_cell(normal_evals, family_evals)
    matrix: Dict[str, Any] = {}
    known_cells = 0
    for scenario in MATRIX_SCENARIOS:
        matrix[scenario] = {}
        for mix in OPPONENT_MIXES:
            roots = list((known.get(scenario) or {}).get(mix) or [])
            count = len(roots)
            if count >= SCENARIO_ROOT_QUOTA:
                status, reason = "known", None
                known_cells += 1
            elif count == 0:
                status = "input_gap"
                reason = "输入不足：未取得任何独立来源根"
            else:
                status = "input_gap"
                reason = "输入不足：根配额 {0}/{1}（§7.3 每子场景 H/M 各 {1} 根）".format(
                    count, SCENARIO_ROOT_QUOTA)
            matrix[scenario][mix] = {
                "status": status, "n_roots": count, "quota": SCENARIO_ROOT_QUOTA,
                "roots": roots, "reason": reason,
            }
    total = len(MATRIX_SCENARIOS) * len(OPPONENT_MIXES)
    return {"cells": matrix,
            "summary": {
                "n_cells": total, "known_cells": known_cells,
                "input_gap_cells": total - known_cells,
                "quota_per_cell": SCENARIO_ROOT_QUOTA,
                "note": "缺格标输入不足；只补部分格的小批次不得宣称全搜索空间已验收",
            }}


def _entry_from_root_records(
        candidate_id: str, normal_evals: Dict[str, Any], family_evals: Dict[str, Any],
        *, safety: Any = "PASS", effect_failure_unresolved: bool = False,
        behavior_signature: Optional[Mapping[str, Any]] = None,
        kind: str = "action_value_v1",
        source_ref: Optional[Mapping[str, Any]] = None,
        self_reported_value: Optional[float] = None,
        evidence_merge: Optional[Mapping[str, Any]] = None,
        manifest: Optional[Mapping[str, bool]] = None) -> Dict[str, Any]:
    """由**累计根记录**构建档案条目（增量合并的出口；聚合全部从根记录重算）。"""

    stats = _stats_from_root_records(normal_evals, family_evals, manifest)
    candidate_stats = {"panels": stats["panels"],
                       "family_development_values": stats["family_development_values"]}
    matrix = evaluation_matrix(normal_evals, family_evals)
    evidence_roots = 0
    for block in candidate_stats["panels"].values():
        for panel in block["panels"].values():
            evidence_roots += panel["n_roots"]
    return {
        "candidate_id": candidate_id,
        "kind": kind,
        "safety": safety if isinstance(safety, Mapping) else {"status": safety},
        "effect_failure_unresolved": bool(effect_failure_unresolved),
        "overall": _overall_summary(candidate_stats),
        "family": _family_summary(candidate_stats),
        "behavior_signature": behavior_signature,
        "behavior_digest": behavior_signature_digest(behavior_signature),
        "evidence_count": evidence_roots,
        "source_ref": source_ref,
        "self_reported_value": self_reported_value,
        "normal_evaluations": {rid: dict(rec) for rid, rec in normal_evals.items()},
        "family_evaluations": {sub: {rid: dict(rec) for rid, rec in rows.items()}
                               for sub, rows in family_evals.items()},
        "evaluation_matrix": matrix["cells"],
        "matrix_summary": matrix["summary"],
        "evidence_merge": dict(evidence_merge) if evidence_merge else None,
        "evidence_manifest": dict(manifest) if manifest else None,
    }


def _root_records_from_samples(samples: Sequence[Mapping[str, Any]],
                               candidate_id: str) -> Dict[str, Any]:
    """本批样本的根记录：{records: {(scenario, root_id): 记录}, manifest: 清单完整性}。

    manifest[(scenario, mix)] = 该面板本批是否**清单完整**（Q4：任一根失效/漏行
    即 False）。清单完整性必须随根记录一起传下去——否则增量合并会拿"剩余根"
    重算均值并把它当完整面板送进排序（Q4 回归）。
    """

    stats = paired_stage_statistics(samples, min_roots=1)
    if samples and candidate_id not in stats["by_candidate"]:
        raise ValueError(
            "candidate_id={0!r} 不在所给样本中（样本实际身份：{1}）；"
            "拒绝身份不符的静默空条目".format(candidate_id,
                                              sorted(stats["by_candidate"])))
    candidate_stats = stats["by_candidate"].get(candidate_id)
    records: Dict[str, Dict[str, Any]] = {}
    manifest: Dict[str, bool] = {}
    for scenario, block in sorted((candidate_stats or {}).get("panels", {}).items()):
        for mix, panel in sorted(block["panels"].items()):
            manifest["{0}|{1}".format(scenario, mix)] = bool(
                panel.get("manifest_complete", True))
            for row in panel["root_rows"]:
                record = {
                    "d_point": row["d_point"], "d_low": row["d_low"],
                    "d_high": row["d_high"], "unknown": row["unresolved"],
                    "opponent_mix": mix, "cost": row["cost"],
                    "recorded_cost": row.get("recorded_cost"),
                    "role": row["role"],
                    "root_content_digest": row.get("root_content_digest"),
                }
                bucket = records.setdefault(scenario, {})
                key = row["root_id"] if scenario == SCENARIO_NORMAL else \
                    _family_bucket_key(bucket, row["root_id"], record)
                bucket[key] = record
    return {"records": records, "manifest": manifest}


def _record_incomplete(record: Optional[Mapping[str, Any]]) -> bool:
    """根记录是否缺事实（未分辨/缺配对差）：可被更完整的证据补齐。"""

    if not isinstance(record, Mapping):
        return True
    return (record.get("unknown") is True or record.get("d_point") is None
            or record.get("d_low") is None)


def merge_archive_entry(
        previous_entry: Optional[Mapping[str, Any]],
        candidate_id: str,
        samples: Sequence[Mapping[str, Any]],
        *, safety: Any = "PASS",
        effect_failure_unresolved: bool = False,
        behavior_signature: Optional[Mapping[str, Any]] = None,
        kind: str = "action_value_v1",
        source_ref: Optional[Mapping[str, Any]] = None,
        self_reported_value: Optional[float] = None,
        declared_cells: Sequence[str] = ()) -> Dict[str, Any]:
    """**按完整根身份增量合并**候选证据（A3；不丢已有证据、不静默覆盖）。

    合并规则（§7.3/§9.1—9.4）：
      - 格子键 = (scenario, root_id)；新批次里旧条目没有的格子 → 补齐（added）；
      - 同一格已有**完整**证据 → 保留旧证据（retained，不覆盖）；
      - 同一格旧证据缺事实而新证据完整 → 升级（upgraded）；
      - 旧条目里有、本批未覆盖的根 → preserved（显式列出，不静默丢）；
      - 聚合（overall/family/matrix）一律从**合并后的根记录**重算。

    previous_entry 为 None 或空条目时等价于首次建档（build_archive_entry 的
    同语义入口，另附行为签名与场景矩阵）。
    """

    if behavior_signature is not None and behavior_signature.get("comparable") is False:
        raise ValueError("不可判定行为不得合并进有效档案；保留原条目，先完成行为重评")
    previous = previous_entry or {}
    normal_evals: Dict[str, Any] = {rid: dict(rec) for rid, rec in
                                    (previous.get("normal_evaluations") or {}).items()}
    family_evals: Dict[str, Dict[str, Any]] = {
        sub: {rid: dict(rec) for rid, rec in (rows or {}).items()}
        for sub, rows in (previous.get("family_evaluations") or {}).items()}
    before_normal = set(normal_evals)
    before_family = {sub: set(rows) for sub, rows in family_evals.items()}
    batch = _root_records_from_samples(samples, candidate_id)
    incoming = batch["records"]
    # 清单完整性（Q4）：以**最近一次覆盖该格的批次**为准——本批清单不完整（整根
    # 失效/漏行）时该格标记不完整，合并出的面板不得进排序/提名；后续批次用完整
    # 清单重新覆盖同一格时恢复完整（Q4 管的是"本批"，不永久毒化历史）。
    manifest: Dict[str, bool] = dict(previous.get("evidence_manifest") or {})
    for key, complete in (batch["manifest"] or {}).items():
        manifest[key] = bool(complete)
    merge = {"added": [], "retained": [], "upgraded": [], "preserved": [],
             "cells_touched": sorted(incoming),
             "manifest_incomplete_cells": sorted(key for key, complete
                                                 in manifest.items() if not complete)}
    for scenario in sorted(incoming):
        for root_id in sorted(incoming[scenario]):
            record = incoming[scenario][root_id]
            if scenario == SCENARIO_NORMAL:
                bucket = normal_evals
                key = root_id
            else:
                bucket = family_evals.setdefault(scenario, {})
                # 家族格键：同 root_id 跨对手情景是两个真实实例 → 情景限定键，
                # 绝不静默覆盖（后者覆盖前者会让两情景证据永远只剩一个）。
                key = _family_bucket_key(bucket, root_id, record)
                if key != root_id:
                    merge.setdefault("cell_qualified", []).append(
                        {"root_id": root_id, "cell_key": key,
                         "opponent_mix": record.get("opponent_mix")})
            existing = bucket.get(key)
            if existing is None:
                bucket[key] = record
                merge["added"].append(key if key != root_id else root_id)
            elif _record_incomplete(existing) and not _record_incomplete(record):
                bucket[key] = record
                merge["upgraded"].append(key if key != root_id else root_id)
            else:
                merge["retained"].append(key if key != root_id else root_id)
    # preserved：旧条目里有、本批**未触及**的根（显式列出，不静默丢）。
    incoming_normal = set(incoming.get(SCENARIO_NORMAL) or {})
    incoming_family = {sub: set(rows) for sub, rows in incoming.items()
                       if sub != SCENARIO_NORMAL}
    merge["preserved"] = sorted(
        (before_normal - incoming_normal)
        | {rid for sub, rows in before_family.items() for rid in rows
           if rid not in incoming_family.get(sub, set())})
    merge["n_roots_total"] = len(normal_evals) + sum(len(rows)
                                                     for rows in family_evals.values())
    signature = behavior_signature if behavior_signature is not None else \
        previous.get("behavior_signature")
    return _entry_from_root_records(
        candidate_id, normal_evals, family_evals, safety=safety,
        effect_failure_unresolved=(effect_failure_unresolved
                                   or bool(previous.get("effect_failure_unresolved"))),
        behavior_signature=signature, kind=kind,
        source_ref=source_ref if source_ref is not None else previous.get("source_ref"),
        self_reported_value=(self_reported_value if self_reported_value is not None
                             else previous.get("self_reported_value")),
        evidence_merge=merge, manifest=manifest)


def build_archive_entry(
    candidate_id: str,
    samples: Sequence[Mapping[str, Any]],
    *,
    safety: Any = "PASS",
    effect_failure_unresolved: bool = False,
    behavior_signature: Optional[Mapping[str, Any]] = None,
    kind: str = "action_value_v1",
    source_ref: Optional[Mapping[str, Any]] = None,
    self_reported_value: Optional[float] = None,
    min_roots: int = 2,
) -> Dict[str, Any]:
    """由样本构建档案条目：统计材料 + 根级评估记录（供 panel_epoch 比较与提名）。

    self_reported_value 只是携带候选自报字段：选择规则从不读它（§9.2 规则 5，
    无数据不得以自报价值填档）。
    """
    stats = paired_stage_statistics(samples, min_roots=min_roots)
    # fail-closed（回归修正）：candidate_id 与样本实际身份不符时立即报错，
    # 不再静默返回空条目——空 normal_evaluations 会让下游把"全部根缺失"误报成
    # nomination_pending_budget（batch7 efficiency_seed 63/64 字符转写事故）。
    if samples and candidate_id not in stats["by_candidate"]:
        raise ValueError(
            "candidate_id={0!r} 不在所给样本中（样本实际身份：{1}）；"
            "拒绝身份不符的静默空条目".format(
                candidate_id, sorted(stats["by_candidate"])))
    candidate_stats = stats["by_candidate"].get(candidate_id, {
        "panels": {}, "family_development_values": {}})

    normal_evals: Dict[str, Dict[str, Any]] = {}
    normal_block = candidate_stats["panels"].get(SCENARIO_NORMAL)
    if normal_block:
        for mix, panel in sorted(normal_block["panels"].items()):
            for row in panel["root_rows"]:
                normal_evals[row["root_id"]] = {
                    "d_point": row["d_point"], "d_low": row["d_low"],
                    "d_high": row["d_high"], "unknown": row["unresolved"],
                    "opponent_mix": mix, "cost": row["cost"],
                    "recorded_cost": row.get("recorded_cost"), "role": row["role"],
                    "usage": row.get("usage", "development_core"),
                    "root_content_digest": row.get("root_content_digest"),
                }
    family_evals: Dict[str, Dict[str, Dict[str, Any]]] = {}
    for family in FAMILIES:
        for sub_kind in ("open", "cost"):
            sub = "{0}_{1}".format(family, sub_kind)
            block = candidate_stats["panels"].get(sub)
            if not block:
                continue
            per_root: Dict[str, Dict[str, Any]] = {}
            for mix, panel in sorted(block["panels"].items()):
                for row in panel["root_rows"]:
                    per_root[row["root_id"]] = {
                        "d_point": row["d_point"], "d_low": row["d_low"],
                        "d_high": row["d_high"], "unknown": row["unresolved"],
                        "opponent_mix": mix, "cost": row["cost"],
                        "recorded_cost": row.get("recorded_cost"), "role": row["role"],
                    }
            family_evals[sub] = per_root

    evidence_roots = 0
    for block in candidate_stats["panels"].values():
        for panel in block["panels"].values():
            evidence_roots += panel["n_roots"]
    # A3：显式待评价场景矩阵（缺格标输入不足，不伪装成已知）＋行为签名摘要。
    matrix = evaluation_matrix(normal_evals, family_evals)

    return {
        "candidate_id": candidate_id,
        "kind": kind,
        "safety": safety if isinstance(safety, Mapping) else {"status": safety},
        "effect_failure_unresolved": bool(effect_failure_unresolved),
        "overall": _overall_summary(candidate_stats),
        "family": _family_summary(candidate_stats),
        "behavior_signature": behavior_signature,
        "behavior_digest": behavior_signature_digest(behavior_signature),
        "evidence_count": evidence_roots,
        "evaluation_matrix": matrix["cells"],
        "matrix_summary": matrix["summary"],
        "source_ref": source_ref,
        "self_reported_value": self_reported_value,
        "normal_evaluations": normal_evals,
        "family_evaluations": family_evals,
    }


def signature_distance(sig_a: Optional[Mapping[str, Any]],
                       sig_b: Optional[Mapping[str, Any]]) -> float:
    """行为签名距离：固定可见窗口上 action_key 不一致比例（§9.2 规则 3）。

    签名=固定可见窗口上实际 action_key 序列+缺失掩码。取两签名窗口 id 的并集
    （稳定排序）；任一侧缺失该窗口或缺失掩码为真都计一次不一致；两侧都无窗口
    视为 0（无证据不放大距离）。
    """
    def _windows(sig: Optional[Mapping[str, Any]]) -> Dict[str, Optional[str]]:
        if not isinstance(sig, Mapping):
            return {}
        out: Dict[str, Optional[str]] = {}
        for window in sig.get("windows", ()):
            if isinstance(window, Mapping):
                out[str(window.get("window_id"))] = (
                    None if window.get("missing") else window.get("action_key"))
        return out

    windows_a, windows_b = _windows(sig_a), _windows(sig_b)
    ids = sorted(set(windows_a) | set(windows_b))
    if not ids:
        return 0.0
    mismatches = sum(1 for wid in ids if windows_a.get(wid) != windows_b.get(wid))
    return mismatches / len(ids)


def _select_exploration(
    pool_entries: Sequence[Mapping[str, Any]],
    seated_signatures: Sequence[Optional[Mapping[str, Any]]],
    *,
    count: int = 2,
) -> Tuple[List[str], List[Dict[str, Any]], Dict[str, Dict[str, Any]]]:
    """探索席选择：行为签名最小距离最大化迭代选 2（§9.2 规则 3/4；P13 席间去重）。

    迭代：每轮给每个剩余候选打分 = 与"已入档签名集"（席位者+已选探索者）的最小
    距离；取最大者。并列先证据较少者、再 candidate_id 字典序。已入档签名集为空
    时（档案无任何席位者）首轮以"与池内其他候选的最大距离"作种子分——合同未规定
    迭代起点，这是本模块冻结的工程选择（歧义处理见模块 docstring）。

    **探索席彼此同行为去重（P13 / R9 复审 A4r）**：每选中一个候选，立即按行为签名
    摘要把它在池内的**同签名**候选移出剩余集，并把重复来源作为第三返回值
    `exclusions` 逐条登记（{被排除者: {"owners": [排除它的身份], "digest": 依据的
    签名摘要}}）。没有第二种行为时**第二席留空**，绝不用同签名候选填满（§9.2 规则 4：
    不凭代码排版增加探索名额）；被排除者只退出本次选席，档案条目（结果缓存与血缘）不动。
    打分、并列裁决与排除都只读签名/摘要、按 sorted(candidate_id) 迭代 → 输入顺序不
    影响结果。
    """
    remaining = {e["candidate_id"]: e for e in pool_entries}
    reference = list(seated_signatures)
    selected: List[str] = []
    steps: List[Dict[str, Any]] = []
    exclusions: Dict[str, Dict[str, Any]] = {}
    while len(selected) < count and remaining:
        scores: Dict[str, Dict[str, Any]] = {}
        for cid in sorted(remaining):
            entry = remaining[cid]
            if reference:
                dists = [signature_distance(entry.get("behavior_signature"), sig)
                         for sig in reference]
                score: Optional[float] = min(dists)
            elif len(remaining) == 1:
                score = 0.0
            else:
                others = [signature_distance(entry.get("behavior_signature"),
                                             other.get("behavior_signature"))
                          for other in remaining.values()
                          if other["candidate_id"] != cid]
                score = max(others)
            scores[cid] = {"score": score,
                           "evidence_count": entry.get("evidence_count", 0)}
        # 排序键：分数降序 → 证据较少 → candidate_id 升序（确定性）。
        ranked = sorted(scores.items(),
                        key=lambda kv: (-(kv[1]["score"] if kv[1]["score"] is not None
                                          else -1.0),
                                        kv[1]["evidence_count"], kv[0]))
        chosen = ranked[0][0]
        chosen_entry = remaining.pop(chosen)
        chosen_digest = behavior_signature_digest(chosen_entry.get("behavior_signature"))
        # 席间同行为去重：本轮被选中者的同签名候选出局（谁被谁排除 + 依据哪条摘要）。
        # 摘要缺失（无窗口证据）不作"与谁都一样"处理：不外推、也不排除。
        round_excluded: Dict[str, str] = {}
        if chosen_digest:
            for cid in sorted(remaining):
                if behavior_signature_digest(
                        remaining[cid].get("behavior_signature")) == chosen_digest:
                    round_excluded[cid] = chosen_digest
            for cid in sorted(round_excluded):
                record = exclusions.setdefault(
                    cid, {"owners": [], "digest": chosen_digest})
                if chosen not in record["owners"]:
                    record["owners"].append(chosen)
                remaining.pop(cid)
        steps.append({
            "round": len(selected) + 1,
            "scores": {cid: scores[cid]["score"] for cid in sorted(scores)},
            "chosen": chosen,
            # 本轮席间同行为排除：{被排除者: 依据的签名摘要}（空 = 本轮无同行为者）。
            "excluded_same_behavior": {cid: round_excluded[cid]
                                       for cid in sorted(round_excluded)},
        })
        selected.append(chosen)
        reference.append(chosen_entry.get("behavior_signature"))
    return selected, steps, exclusions


def _seated_holders(slots: Mapping[str, Any]) -> List[str]:
    """在案席位持有者（overall + 四家族席；**不含**探索席自身）。

    探索席是由本集合派生的结论，不能拿它当自己的排除项——否则重算会把上一轮的
    探索席成员当成"已占席者"而永远换不了人（R9 §13 A 项：探索席相对在案席位重算）。
    """
    out: List[str] = []
    for channel in SEATING_CHANNELS:
        for cid in (slots or {}).get(channel) or ():
            if isinstance(cid, str) and cid not in out:
                out.append(cid)
    return sorted(out)


def select_exploration_seat(
        entries: Sequence[Mapping[str, Any]],
        committed_seats: Mapping[str, Any],
        *,
        count: Optional[int] = None,
) -> Dict[str, Any]:
    """探索席选择（§9.2 规则 3/4）：**相对提交后的在案席位**重算（R9 §13 A 项）。

    - 排除集 = committed_seats 里的 **overall + 四家族席**持有者（SEATING_CHANNELS）；
    - 去重参考 = 这些持有者的**行为签名摘要**（规则 4：源码不同但同签名者不重复占
      探索名额；被排除者显式登记，不静默丢）；
    - **探索席彼此**同样按行为签名摘要去重（P13 / 复审 A4r）：每选入一个探索候选即
      排除其同行为候选并登记重复来源；只有一种行为时第二席留空，不用同行为候选填满；
      同签名候选仍保留在档案条目里（缓存/血缘不丢）。
    - 资格仍由 _slot_eligibility 把关（安全 PASS、非 V2 基线、非故障未修复），且必须
      有行为签名证据（无数据不得填档）——本函数只做选择，不新增任何入选可能。

    这是探索席的唯一选择实现：update_archive 用它（在案席位 = 本次重排出的整体/家族
    席），档案事务的提交点也用它（在案席位 = **本次提交后的**整体/家族席）。返回
    {"slots", "seated", "reference_digests", "report"}；report 形状即档案
    selection_report.exploration（pool / steps / excluded_behavior_duplicates /
    excluded_behavior_duplicate_sources + 口径登记）：两类同行为排除都进
    excluded_behavior_duplicates（{被排除者: [排除它的身份]}），来源类别与依据摘要
    单列在 excluded_behavior_duplicate_sources（谁被谁排除、依据哪条摘要）。
    """
    capacity = (SLOT_CAPACITY[EXPLORATION_CHANNEL] if count is None else int(count))
    pool: Dict[str, Mapping[str, Any]] = {}
    for entry in entries:
        cid = entry.get("candidate_id")
        if isinstance(cid, str) and cid:
            pool[cid] = entry
    seated = _seated_holders(committed_seats)
    # 在案席持有者的签名（去重参考）：缺条目/缺签名不伪造（None 在距离口径里表示
    # "该窗口无证据"，不放大也不缩小距离）。
    seated_signatures = [pool[cid].get("behavior_signature") for cid in seated
                         if cid in pool]
    seated_by_digest: Dict[str, List[str]] = {}
    for cid in seated:
        digest = behavior_signature_digest((pool.get(cid) or {}).get("behavior_signature"))
        if digest:
            seated_by_digest.setdefault(digest, []).append(cid)
    exploration_pool: List[Mapping[str, Any]] = []
    #: 同行为排除登记（§9.2 规则 4；P13 席间去重）：{被排除者: {"basis", "digest",
    #: "owners"}}。两类来源分别标注：在案席持有者（进入探索池前剔除）与已选探索席者
    #: （席间去重）。被排除者只退出选席——条目照旧留在档案里（缓存/血缘保留），
    #: 排除来源逐条可核，绝不静默丢。
    duplicate_sources: Dict[str, Dict[str, Any]] = {}
    for cid in sorted(pool):
        if cid in seated:
            continue
        ok, _reason = _slot_eligibility(pool[cid])
        if not ok:
            continue
        signature = pool[cid].get("behavior_signature")
        if signature is None:
            continue
        digest = behavior_signature_digest(signature)
        if digest and digest in seated_by_digest:
            duplicate_sources[cid] = {"basis": SEATED_DUPLICATE_BASIS,
                                      "digest": digest,
                                      "owners": list(seated_by_digest[digest])}
            continue
        exploration_pool.append(pool[cid])
    chosen, steps, seat_duplicates = _select_exploration(
        exploration_pool, seated_signatures, count=capacity)
    for cid, record in sorted(seat_duplicates.items()):
        duplicate_sources[cid] = {"basis": EXPLORATION_DUPLICATE_BASIS,
                                  "digest": record["digest"],
                                  "owners": list(record["owners"])}
    reference = {digest: list(owners)
                 for digest, owners in sorted(seated_by_digest.items())}
    return {
        "slots": list(chosen),
        "seated": seated,
        "reference_digests": reference,
        "report": {
            "pool": [e["candidate_id"] for e in exploration_pool],
            "steps": steps,
            "excluded_behavior_duplicates": {
                cid: list(record["owners"])
                for cid, record in sorted(duplicate_sources.items())},
            # 排除来源逐条可核：谁被谁排除、依据哪条签名摘要、依据哪类来源
            # （在案席持有者 / 已选探索席者）。
            "excluded_behavior_duplicate_sources": {
                cid: {"basis": record["basis"], "digest": record["digest"],
                      "owners": list(record["owners"])}
                for cid, record in sorted(duplicate_sources.items())},
            # 口径登记：排除集与去重参考逐次可核（不是"非空即通过"）。
            "excluded_seated": list(seated),
            "reference_digests": reference,
            "slot_selection_version": SLOT_SELECTION_VERSION,
        },
    }


def rebase_exploration_seat(
        archive: Mapping[str, Any],
        *,
        slots: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """把档案的探索席**相对在案席位**重算，并同步报告与 distinct 记账（R9 §13 A）。

    slots 给定时以它为在案席位表（调用方正在提交的席位），否则用 archive["slots"]。
    返回 {"slots", "selection_report", "distinct_candidates", "exploration_report",
    "slot_selection_version"}；**不修改入参**。探索席与在案席位互斥使 8 席上限
    天然成立（整体 2 + 家族 4 + 探索 2），越界即断言失败（fail-closed）。
    """
    seats = {channel: list(ids or [])
             for channel, ids in ((slots if slots is not None
                                   else archive.get("slots")) or {}).items()}
    result = select_exploration_seat(list((archive.get("entries") or {}).values()), seats)
    seats[EXPLORATION_CHANNEL] = list(result["slots"])
    report = dict(archive.get("selection_report") or {})
    report[EXPLORATION_CHANNEL] = result["report"]
    distinct = sorted(set(_seated_holders(seats)) | set(result["slots"]))
    if len(distinct) > sum(SLOT_CAPACITY.values()):
        raise AssertionError("档案超过 8 个不同 candidate_id：{0}".format(distinct))
    return {
        "slots": seats,
        "selection_report": report,
        "distinct_candidates": distinct,
        "exploration_report": result,
        "slot_selection_version": SLOT_SELECTION_VERSION,
    }


def update_archive(
    entries: Sequence[Mapping[str, Any]],
    *,
    previous: Optional[Mapping[str, Any]] = None,
    exploration_queue: Sequence[str] = (),
) -> Dict[str, Any]:
    """确定性重排 8 席档案（§9.1/§9.2）。

    - 整体席：正常面板声明混合差值下界均值（sort_value）降序取前 2；并列依次
      未知目标比例较低 → 整链成本较低 → candidate_id 字典序；
    - 家族席：该族机会/代价两子场景等权均值最大者（complete 才参席），并列同上；
    - 探索席：剩余安全候选中行为签名最不同者（最小距离最大化迭代选 2）；两席**彼此**
      同行为者不重复占（每选入一席即排除其同行为候选并登记来源），只有一种行为时第二
      席留空（P13 / 复审 A4r）；
    - 同一候选多席只存一份（entries 单存，slots 引用）；V2/安全 FAIL/故障未
      修复者不占席；缺子场景不填零争席。
    """
    pool: Dict[str, Mapping[str, Any]] = {}
    for entry in entries:
        cid = entry.get("candidate_id")
        if isinstance(cid, str) and cid:
            pool[cid] = entry

    eligible: Dict[str, Mapping[str, Any]] = {}
    rejected: Dict[str, str] = {}
    for cid in sorted(pool):
        ok, reason = _slot_eligibility(pool[cid])
        if ok:
            eligible[cid] = pool[cid]
        else:
            rejected[cid] = reason or "不合格"

    slots: Dict[str, List[str]] = {channel: [] for channel in SLOT_CAPACITY}
    report: Dict[str, Any] = {"overall": [], "family": {}, "exploration": {}}

    # 整体席（规则 1）。
    overall_ranked = []
    for cid in sorted(eligible):
        overall = eligible[cid].get("overall")
        if not overall or overall.get("sort_value") is None:
            continue
        overall_ranked.append({
            "candidate_id": cid,
            "sort_value": overall["sort_value"],
            "unknown_ratio": overall["unknown_ratio"],
            "total_cost": overall["total_cost"],
            "unresolved": overall["unresolved"],
        })
    overall_ranked.sort(key=lambda row: (
        -row["sort_value"],
        row["unknown_ratio"] if row["unknown_ratio"] is not None else math.inf,
        row["total_cost"],
        row["candidate_id"],
    ))
    slots["overall"] = [row["candidate_id"] for row in overall_ranked[:SLOT_CAPACITY["overall"]]]
    report["overall"] = overall_ranked

    # 家族席（规则 2）。
    for family in FAMILIES:
        family_ranked = []
        for cid in sorted(eligible):
            fam = (eligible[cid].get("family") or {}).get(family)
            if not fam or not fam.get("complete") or fam.get("value") is None:
                continue
            if not fam.get("manifest_complete", True):
                continue  # Q4：清单未补齐（任一根失效/漏行）不进家族席
            family_ranked.append({
                "candidate_id": cid,
                "value": fam["value"],
                "open_value": fam["open_value"],
                "cost_value": fam["cost_value"],
                "unknown_ratio": fam["unknown_ratio"],
                "total_cost": fam["total_cost"],
                "unresolved": fam["unresolved"],
            })
        family_ranked.sort(key=lambda row: (
            -row["value"],
            row["unknown_ratio"] if row["unknown_ratio"] is not None else math.inf,
            row["total_cost"],
            row["candidate_id"],
        ))
        slots[family] = [row["candidate_id"]
                         for row in family_ranked[:SLOT_CAPACITY[family]]]
        report["family"][family] = family_ranked

    # 探索席（规则 3/4）：**相对本档案的在案席位**（整体 + 四家族席）重算剩余安全
    # 候选与同行为去重——排除集与去重参考都取自这些席位，绝不与其它视角拼接提交
    # （R9 §13 A：一个候选不得同时持有整体席与探索席）。**席间**同行为去重（P13 /
    # 复审 A4r）也在此完成：只有一种行为时第二席留空。选择实现唯一来源 =
    # select_exploration_seat（档案事务的提交点用同一函数重算）。
    exploration = select_exploration_seat(list(pool.values()), slots)
    slots[EXPLORATION_CHANNEL] = list(exploration["slots"])
    report[EXPLORATION_CHANNEL] = exploration["report"]

    distinct = sorted(set(exploration["seated"]) | set(exploration["slots"]))
    if len(distinct) > sum(SLOT_CAPACITY.values()):
        raise AssertionError("档案超过 8 个不同 candidate_id：{0}".format(distinct))

    queue = list(exploration_queue)
    if previous and previous.get("exploration_queue"):
        for cid in previous["exploration_queue"]:
            if cid not in queue and cid in pool:
                queue.append(cid)

    return {
        "schema": ARCHIVE_SCHEMA,
        "slots": slots,
        "entries": pool,
        "distinct_candidates": distinct,
        "selection_report": report,
        "ineligible": rejected,
        # 行为去重登记（§9.2 规则 4；P13 起含席间来源）：{候选: [与之同行为的提出
        # 排除者]}——提出者可以是在案席持有者，也可以是本轮另一个探索席者。
        "behavior_duplicates": {
            cid: list(owners) for cid, owners in sorted(
                exploration["report"]["excluded_behavior_duplicates"].items())},
        "exploration_queue": queue,
        # 选席口径身份串（R9 §13）：排序键与探索席重算口径随本版变更。
        "slot_selection_version": SLOT_SELECTION_VERSION,
        "notes": [
            "席位容量 overall=2 / 四家族各 1 / exploration=2；同候选多席单存（entries 一份）",
            "排序为开发启发式，不称统计证明（§9.2）",
            "探索席相对在案席位（overall+四家族）重算；排序代价为确定性预算单元（R9 §13）",
            "探索席彼此按行为签名摘要去重：每选入一席即排除同行为候选并登记来源；"
            "只有一种行为时第二席留空（P13 / 复审 A4r）",
        ],
    }


# ---------------------------------------------------------------------------
# 3. panel_epoch 与挑战替换（§9.2 通道面板版本与替换复核；T12）
# ---------------------------------------------------------------------------


def build_root_usage_manifest(*, development_core: Sequence[str] = (),
                              development_refresh: Sequence[str] = (),
                              confirmation: Sequence[str] = ()) -> Dict[str, Any]:
    """构建根用途清单（Q2）：三分区互斥、每个根恰属一区，重复/跨界即 ValueError。

    文件级分离纪律：确认清单由确认侧入口独占读写；生成/选择进程只持有开发
    分区内容，不读取 confirmation 键（见 load_root_usage_manifest 的分区读取）。
    """
    sections = {
        "development_core": sorted({str(r) for r in development_core}),
        "development_refresh": sorted({str(r) for r in development_refresh}),
        "confirmation": sorted({str(r) for r in confirmation}),
    }
    seen: Dict[str, str] = {}
    for usage, roots in sections.items():
        for root_id in roots:
            if root_id in seen:
                raise ValueError(
                    "根 {0!r} 同时出现在 {1} 与 {2}：用途分区必须互斥".format(
                        root_id, seen[root_id], usage))
            seen[root_id] = usage
    return {"schema": ROOT_USAGE_SCHEMA, "usage": sections}


def load_root_usage_manifest(path: Path, *, include_confirmation: bool = True) -> Dict[str, str]:
    """读取根用途清单 → {root_id: usage}。

    Q2 文件级分离：生成/选择进程调用时 include_confirmation=False——它只拿到
    自己根的 development_* 用途，任何确认根名都不进入其内存（确认材料对生成
    进程不可访问）。清单缺 schema/根跨界即 ValueError（fail-closed）。
    """
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if data.get("schema") != ROOT_USAGE_SCHEMA:
        raise ValueError("根用途清单 schema 必须是 {0}".format(ROOT_USAGE_SCHEMA))
    sections = data.get("usage") or {}
    usage: Dict[str, str] = {}
    for section in ROOT_USAGES:
        if section == "confirmation" and not include_confirmation:
            continue
        for root_id in sections.get(section) or ():
            if root_id in usage:
                raise ValueError("根 {0!r} 在用途清单中跨界重复".format(root_id))
            usage[str(root_id)] = section
    return usage


def build_channel_epoch(
    channel: str,
    core_roots: Sequence[Mapping[str, Any]],
    *,
    refresh_roots: Sequence[Mapping[str, Any]] = (),
    epoch_no: int = 1,
    usage_manifest: Optional[Mapping[str, str]] = None,
    usage_manifest_path: Optional[Path] = None,
    include_confirmation_roots: bool = True,
) -> Dict[str, Any]:
    """构建通道 panel_epoch：根集=核心根+历次已提交刷新根（§9.2；Q2 用途三分区）。

    根记录：{root_id, role: core|refresh, usage: 三分区之一, opponent_mix,
    sub_scenario(家族通道)}。confirmation_eligible 只在 usage==confirmation 时
    为 True——开发核心根/刷新根都是开发通道已消费根，永不流入确认集（Q2/T13）。
    用途来源：usage_manifest（映射 root_id→usage）或 usage_manifest_path 清单
    文件；两者皆无时保守缺省 core→development_core、refresh→development_refresh
    （即无人确认可用）。清单给出但根未列出 → ValueError（fail-closed）。
    """
    if channel not in CHANNELS:
        raise ValueError("channel 必须是 {0} 之一".format(list(CHANNELS)))
    if channel != "normal" and channel not in FAMILIES:
        raise ValueError("channel 必须是 normal 或四家族之一")
    if usage_manifest is None and usage_manifest_path is not None:
        # Q2 文件级分离：开发侧入口以 include_confirmation=False 读取——确认根
        # 名不进入生成进程内存；确认侧入口独占完整清单。
        usage_manifest = load_root_usage_manifest(
            Path(usage_manifest_path), include_confirmation=include_confirmation_roots)

    def _usage_of(root_id: str, role: str) -> str:
        if usage_manifest is not None:
            usage = usage_manifest.get(root_id)
            if usage is None:
                raise ValueError(
                    "根 {0!r} 不在用途清单中（Q2 fail-closed）：用途未冻结的根"
                    "不得进入通道 epoch".format(root_id))
            return usage
        # 无清单时的保守缺省：core→development_core、refresh→development_refresh。
        # 开发根**不再**默认确认可用（Q2 修复：role==core 正是开发通道核心根）。
        return "development_core" if role == "core" else "development_refresh"

    def _rows(roots: Sequence[Mapping[str, Any]], role: str) -> List[Dict[str, Any]]:
        rows = []
        for root in roots:
            usage = _usage_of(root["root_id"], role)
            row = {
                "root_id": root["root_id"],
                "role": role,
                "usage": usage,
                "confirmation_eligible": usage == "confirmation",
                "opponent_mix": root.get("opponent_mix"),
            }
            if channel in FAMILIES:
                sub = root.get("sub_scenario", "{0}_open".format(channel))
                row["sub_scenario"] = sub
            rows.append(row)
        return rows

    roots = _rows(core_roots, "core") + _rows(refresh_roots, "refresh")
    if channel in FAMILIES:
        subs = {row.get("sub_scenario") for row in roots}
        allowed = {"{0}_open".format(channel), "{0}_cost".format(channel)}
        if not subs <= allowed:
            raise ValueError("家族通道 {0} 的根只能属于 {1}".format(channel, sorted(allowed)))
    for mix in OPPONENT_MIXES:
        if not any(row["opponent_mix"] == mix for row in roots):
            raise ValueError("通道根集缺对手情景 {0}，无法按声明混合比较".format(mix))
    return {
        "schema": CHANNEL_EPOCH_SCHEMA,
        "channel": channel,
        "epoch": epoch_no,
        "roots": roots,
        "pending": None,
    }


def confirmation_eligible_roots(epoch: Mapping[str, Any]) -> List[str]:
    """确认集可用根（Q2/T13）：只返回用途分区为 confirmation 的根。

    开发核心根（development_core）正是开发通道用过的根——**不是**未消费确认根；
    刷新根（development_refresh）同样被开发消费。二者一律排除；所有已用于
    生成、选择、诊断或拟合的根都不能作为未消费确认根（T13）。
    """
    return [row["root_id"] for row in epoch.get("roots", ())
            if row.get("usage") == "confirmation"
            and row.get("confirmation_eligible", True)]


def _epoch_root_ids(epoch: Mapping[str, Any]) -> List[str]:
    return [row["root_id"] for row in epoch.get("roots", ())]


def _mix_mean(values_by_mix: Mapping[str, Mapping[str, float]], key: str) -> Optional[float]:
    """按声明混合（H/M 各 1/2）对根记录求均值；缺任一混合返回 None。"""
    means = {}
    for mix in OPPONENT_MIXES:
        rows = values_by_mix.get(mix) or {}
        means[mix] = _mean([v for v in rows.values()]) if rows else None
    if any(v is None for v in means.values()):
        return None
    return sum(DECLARED_MIX_WEIGHTS[mix] * means[mix] for mix in OPPONENT_MIXES)


def _normal_sort_value(evals: Mapping[str, Any], roots: Sequence[Mapping[str, Any]]) -> Optional[float]:
    """正常通道排序值：声明混合下差值下界均值（只用给定根集，T12 同根集比较）。"""
    by_mix: Dict[str, Dict[str, float]] = {}
    for root in roots:
        rec = evals.get(root["root_id"])
        if rec is None:
            return None
        by_mix.setdefault(root["opponent_mix"], {})[root["root_id"]] = float(rec["d_low"])
    return _mix_mean(by_mix, "d_low")


def _family_sort_value(evals: Mapping[str, Any],
                       roots: Sequence[Mapping[str, Any]]) -> Optional[float]:
    """家族通道排序值：该族机会/代价两子场景等权均值的等权混合（差值下界）。"""
    by_sub: Dict[str, Dict[str, Dict[str, float]]] = {}
    for root in roots:
        sub = root.get("sub_scenario")
        rec = family_cell_lookup(evals.get(sub) or {}, root.get("opponent_mix"),
                                 root["root_id"])
        if rec is None:
            return None
        by_sub.setdefault(sub, {}).setdefault(root["opponent_mix"], {})[root["root_id"]] = \
            float(rec["d_low"])
    sub_values = {}
    for sub, mix_map in by_sub.items():
        sub_values[sub] = _mix_mean(mix_map, "d_low")
    if any(v is None for v in sub_values.values()) or len(sub_values) != 2:
        return None
    return 0.5 * sum(sub_values.values())


def _channel_value(channel: str, evals: Mapping[str, Any],
                   roots: Sequence[Mapping[str, Any]]) -> Optional[float]:
    """通道排序值分派：正常通道用 normal_evaluations；家族通道用 family_evaluations。"""
    if channel == "normal":
        return _normal_sort_value(evals, roots)
    return _family_sort_value(evals, roots)


def challenge_plan(
    archive: Mapping[str, Any],
    epoch: Mapping[str, Any],
    challenger_id: str,
    *,
    refresh_roots: Sequence[Mapping[str, Any]] = (),
    contenders: Sequence[str] = (),
) -> Dict[str, Any]:
    """挑战计划（§9.2 两阶段）：

    - 阶段 1：挑战者补齐该通道当前全部根（核心+已提交刷新根）的评估；
    - 阶段 2（仅当有望入席）：预留新刷新批（每受影响子场景 4 根、整体 4 根、
      H/M 均衡），并给本次全部参与重排身份（含原席者）补齐。
    """
    channel = epoch["channel"]
    current_roots = list(epoch.get("roots", ()))
    incumbents = list(archive.get("slots", {}).get(_channel_slot_key(channel), ()))
    participants = sorted(set(incumbents) | {challenger_id} | set(contenders))
    return {
        "channel": channel,
        "phase1_challenger_roots": [r["root_id"] for r in current_roots],
        "promising_check": "阶段 1 完成后：挑战者排序值 ≥ 原席者最小值（同根集比较）",
        "phase2_participants": participants,
        "phase2_refresh_roots": [dict(r) for r in refresh_roots],
        "phase2_requirement": {
            cid: {
                "current_roots": [r["root_id"] for r in current_roots],
                "refresh_roots": [r["root_id"] for r in refresh_roots],
            }
            for cid in participants
        },
        "note": "全部完成后原子提交新 epoch 统一重排；部分完成保持原 epoch 原席，"
                "结果暂存 pending，不混合新旧均值",
    }


def _validate_refresh_roots(channel: str, refresh_roots: Sequence[Mapping[str, Any]]) -> None:
    """刷新批校验：整体 4 根；家族每子场景 4 根；H/M 各 2（均衡配额）。"""
    if channel == "normal":
        if len(refresh_roots) != 4:
            raise ValueError("整体通道刷新批必须是 4 根，得到 {0}".format(len(refresh_roots)))
        counts = {"H": 0, "M": 0}
        for root in refresh_roots:
            counts[root["opponent_mix"]] += 1
        if counts != {"H": 2, "M": 2}:
            raise ValueError("整体刷新批 H/M 必须均衡（各 2），得到 {0}".format(counts))
        return
    by_sub: Dict[str, List[Mapping[str, Any]]] = {}
    for root in refresh_roots:
        by_sub.setdefault(root.get("sub_scenario"), []).append(root)
    for sub_kind in ("open", "cost"):
        sub = "{0}_{1}".format(channel, sub_kind)
        rows = by_sub.get(sub, [])
        if len(rows) != 4:
            raise ValueError("家族 {0} 每受影响子场景刷新 4 根：{1} 得到 {2}".format(
                channel, sub, len(rows)))
        counts = {"H": 0, "M": 0}
        for root in rows:
            counts[root["opponent_mix"]] += 1
        if counts != {"H": 2, "M": 2}:
            raise ValueError("子场景 {0} 刷新批 H/M 必须均衡（各 2），得到 {1}".format(sub, counts))


def family_refresh_batch_verdict(channel: str,
                                 refresh_roots: Sequence[Mapping[str, Any]]
                                 ) -> Dict[str, Any]:
    """家族刷新批复核：**复用** _validate_refresh_roots 的同一套规则（§9.2）。

    返回结构化复核结果（不抛异常）：ok=False 时 reason 逐字来自同一条校验规则，
    调用方据此保持原席原 epoch，绝不静默放行一个不合规的刷新批。
    """

    counts: Dict[str, Dict[str, int]] = {}
    for root in refresh_roots:
        sub = str(root.get("sub_scenario"))
        mix = str(root.get("opponent_mix"))
        bucket = counts.setdefault(sub, {mix_key: 0 for mix_key in OPPONENT_MIXES})
        bucket[mix] = int(bucket.get(mix, 0)) + 1
    try:
        _validate_refresh_roots(channel, list(refresh_roots))
        ok, reason = True, ""
    except ValueError as error:
        ok, reason = False, str(error)
    return {"ok": ok, "reason": reason, "channel": channel,
            "by_sub": {sub: dict(bucket) for sub, bucket in sorted(counts.items())},
            "n_roots": len(refresh_roots),
            "roots_per_side": FAMILY_REFRESH_ROOTS_PER_SIDE,
            "sub_scenarios": ["{0}_open".format(channel),
                              "{0}_cost".format(channel)]}


# ===========================================================================
# P14（评审 G2 收口）· 家族通道缺失集合 = **冻结核心根清单逐键**（不按"当时的行集合"）
#
# 缺陷（P11 生产侧已实测，本模块是遗留的另一套口径）：apply_challenge 的 missing 由
# "epoch 根 + 刷新批"这两个**当时的行集合**推出 ⇒ 冻结清单里那条不在该行集合内的键
# （实测 branch_open|H|root000）永远报不出来：生产调度按逐键覆盖说 8 根，这里说 7 根。
#
# 修法（需求集合与覆盖判据都改成逐键，旧口径原样留作对照）：
#   - 需求集合 = 冻结核心根清单（archive/family-core-roots.json，一次冻结、只读；
#     schema 与 sitin_search.AV_FAMILY_CORE_LIST_SCHEMA 同字面量），或调用方注入的
#     core_rows/core_missing —— **单一入口**见 family_core_requirement；
#   - 覆盖判据 = 该（子场景 × 情景 × 根）有没有**合格**记录（unknown=true 或
#     d_point/d_low 缺失即不合格），与 sitin_search._av_family_core_evidence_gaps 同判据；
#   - 旧口径原样保留为对照字段 missing_reported_row_set，并给"逐键 vs 自报"对照表
#     （字段名与 sitin_search._av_family_core_coverage_vs_reported 同构，可直接对拍）；
#   - 工作项/预算用两者**并集**（reported_only 一条不丢）。
#
# 为什么本模块自己读冻结件而不是 import sitin_search：sitin_search 把本模块作为 sibling
# 装载，反向 import 会成环；因此这里只认 schema 字面量 + 文件名约定，跨模块一致性由
# tools/test_sitin_p14_smallfix.py::test_frozen_list_schema_stays_in_sync_with_production 锁死。
# ===========================================================================

#: 冻结核心根清单 schema（需求集合；archive/family-core-roots.json）。
FAMILY_CORE_LIST_SCHEMA = "sitin-av-family-core-roots/1"
#: 需求集合来源标注（进返回值，报告据此区分"冻结清单逐键"与"当时的行集合"）。
FAMILY_CORE_REQUIREMENT_SOURCES: Tuple[str, ...] = (
    "frozen_core_list", "injected_core_rows", "injected_core_missing", "epoch_row_set")
#: 冻结件在档案树内的固定文件名（不猜用途：文件名 + schema + channel 三重核对）。
FAMILY_CORE_LIST_FILENAME = "family-core-roots.json"


def _json_mapping(path: Path) -> Tuple[Optional[Mapping[str, Any]], str]:
    """读 JSON 对象；失败返回 (None, 原因原文)——不抛、不伪造空对象。"""

    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        return None, "{0}: {1}".format(type(error).__name__, error)
    if not isinstance(payload, Mapping):
        return None, "顶层不是 JSON 对象（得到 {0}）".format(type(payload).__name__)
    return payload, ""


def family_core_list_candidates(persist_dir: Optional[Path]) -> List[Path]:
    """冻结核心根清单的候选路径（**档案树内固定名**，由近及远，去重保序）。

    生产调用链：家族提交目录 `<run_root>/archive/family-commit/<channel>`（persist_dir）
    → `<run_root>/archive/family-core-roots.json`（冻结件）。向上最多三级 + 每级两种
    形态（`<dir>/family-core-roots.json` / `<dir>/archive/family-core-roots.json`），
    命中后仍要过 schema/channel 核对，避免拿错文件当需求集合。
    """

    if persist_dir is None:
        return []
    base = Path(persist_dir)
    out: List[Path] = []
    seen = set()
    for depth in range(4):
        root = base
        for _ in range(depth):
            root = root.parent
        for candidate in (root / FAMILY_CORE_LIST_FILENAME,
                          root / "archive" / FAMILY_CORE_LIST_FILENAME):
            key = str(candidate)
            if key not in seen:
                seen.add(key)
                out.append(candidate)
    return out


def family_core_requirement(*, channel: str,
                            core_rows: Optional[Sequence[Mapping[str, Any]]] = None,
                            core_missing: Optional[Mapping[str, Sequence[str]]] = None,
                            persist_dir: Optional[Path] = None) -> Dict[str, Any]:
    """**需求集合的唯一来源**：冻结核心根清单逐键（调用方注入 > 档案树内冻结件 > 降级）。

    优先级与语义：
      1. `core_missing`（权威逐键缺失，来自 sitin_search.av_family_core_coverage 的
         missing_tokens）：**直接采用**，本模块不再自算覆盖——真正的"同一口径"路径；
      2. `core_rows`（冻结行，逐键需求集合）：按行逐键判定；
      3. 档案树内 `family-core-roots.json`（schema + channel 核对通过）：按行逐键判定；
      4. 都没有 ⇒ 降级为"当时的行集合"（epoch 根 + 刷新批），并在返回值里**具名标注**
         该降级（source=epoch_row_set + note）：这是会少算的旧口径，只作标注、不冒充
         逐键权威结论。

    不静默：读不动的冻结件、schema/channel 不符、缺字段的行都进 `problems` 逐条列出。
    """

    problems: List[Dict[str, Any]] = []
    if core_missing is not None:
        return {"source": "injected_core_missing", "path": None, "rows": [],
                "authoritative_missing": {str(cid): sorted(str(token) for token in (tokens or ()))
                                          for cid, tokens in core_missing.items()},
                "rows_seen": 0, "problems": problems,
                "note": ("调用方注入的权威逐键缺失（sitin_search.av_family_core_coverage"
                         " 口径）：本模块直接采用，不再自算覆盖")}
    if core_rows is not None:
        rows = [dict(row) for row in core_rows]
        return {"source": "injected_core_rows", "path": None, "rows": rows,
                "authoritative_missing": None, "rows_seen": len(rows),
                "problems": problems,
                "note": "调用方注入的冻结核心根行（逐键需求集合）"}
    for path in family_core_list_candidates(persist_dir):
        if not path.is_file():
            continue
        payload, error = _json_mapping(path)
        if payload is None:
            problems.append({"code": "frozen_core_list_unreadable", "path": str(path),
                             "detail": error})
            continue
        if str(payload.get("schema")) != FAMILY_CORE_LIST_SCHEMA:
            problems.append({"code": "frozen_core_list_schema_mismatch", "path": str(path),
                             "detail": "schema={0!r} 不是 {1}".format(
                                 payload.get("schema"), FAMILY_CORE_LIST_SCHEMA)})
            continue
        if str(payload.get("channel") or "") != str(channel):
            problems.append({"code": "frozen_core_list_channel_mismatch", "path": str(path),
                             "detail": "channel={0!r} 不是 {1!r}".format(
                                 payload.get("channel"), str(channel))})
            continue
        rows = [dict(item) for item in (payload.get("roots") or ())
                if isinstance(item, Mapping)]
        for item in (payload.get("roots") or ()):
            if not isinstance(item, Mapping):
                problems.append({"code": "frozen_core_list_row_invalid", "path": str(path),
                                 "detail": "roots 含非对象项，已忽略该项（逐条列出）"})
        return {"source": "frozen_core_list", "path": str(path), "rows": rows,
                "authoritative_missing": None, "rows_seen": len(rows),
                "problems": problems,
                "note": "档案树内冻结核心根清单（一次冻结、只读）：需求集合逐键" }
    return {"source": "epoch_row_set", "path": None, "rows": [],
            "authoritative_missing": None, "rows_seen": 0, "problems": problems,
            "note": ("未取得冻结核心根清单（core_rows/core_missing 未注入，档案树内也没有"
                     " archive/family-core-roots.json）：需求集合**降级**为当时的行集合"
                     "（epoch 根 + 刷新批）。该口径会漏掉不在行集合里的核心根（P9c 实测"
                     "少 1：branch_open|H|root000），故本条只作降级标注，不冒充逐键权威结论")}


def family_missing_comparison(*, authoritative: Sequence[str],
                              reported: Sequence[str]) -> Dict[str, Any]:
    """逐键 vs 自报**对照表**（字段与 sitin_search._av_family_core_coverage_vs_reported 同构）。"""

    frozen_tokens = sorted(str(token) for token in authoritative)
    reported_tokens = sorted(str(token) for token in reported)
    return {
        "frozen_missing": frozen_tokens, "reported_missing": reported_tokens,
        "both": sorted(set(frozen_tokens) & set(reported_tokens)),
        "frozen_only": sorted(set(frozen_tokens) - set(reported_tokens)),
        "reported_only": sorted(set(reported_tokens) - set(frozen_tokens)),
        "consistent": frozen_tokens == reported_tokens,
        "n_frozen": len(frozen_tokens), "n_reported": len(reported_tokens),
        "note": ("对照表：frozen_missing = **权威逐键**口径的缺失；reported_missing = 旧口径"
                 "（当时的行集合）自报值。frozen_only 就是旧口径少算的那几条；reported_only"
                 " 是不在需求集合里的额外点名（如本批刷新根，属不同证据来源）。工作项用"
                 "两者并集：谁也不顶掉谁")}


def family_key_usable(rows: Mapping[str, Any], *, sub_scenario: Any,
                      opponent_mix: Any, root_id: Any) -> bool:
    """该（子场景 × 情景 × 根）是否已有**合格**记录（与生产 A1 缺口判据同一口径）。"""

    cell = (rows or {}).get(str(sub_scenario)) or {}
    record = family_cell_lookup(cell, opponent_mix, root_id)
    if record is None:
        return False
    return not (record.get("unknown") is True or record.get("d_point") is None
                or record.get("d_low") is None)


def apply_challenge(
    archive: Mapping[str, Any],
    epoch: Mapping[str, Any],
    challenger_id: str,
    evaluations: Mapping[str, Any],
    *,
    refresh_roots: Sequence[Mapping[str, Any]],
    budget: Optional[float] = None,
    extra_incumbent_evaluations: Optional[Mapping[str, Any]] = None,
    contenders: Sequence[str] = (),
    persist_dir: Optional[Path] = None,
    core_rows: Optional[Sequence[Mapping[str, Any]]] = None,
    core_missing: Optional[Mapping[str, Sequence[str]]] = None,
) -> Dict[str, Any]:
    """挑战与替换（§9.2；T12 核心）。纯函数：返回新档案/新 epoch 或 pending。

    evaluations 形状：{candidate_id: 根记录}（正常通道 flat；家族通道嵌套
    {sub_scenario: {root_id: rec}}）。排序只用 epoch 根集内的记录——不同样本集
    不直接争冠军：多余根被忽略并记 note，缺失根 → pending 补齐，绝不混均值。

    结果 status：
    - committed：全部身份补齐 → 原子提交新 epoch（epoch+1，刷新根入根集且
      confirmation_eligible=False），通道统一重排（含原席者）；
    - pending_partial：部分完成 → 保持原 epoch 原席，结果暂存 pending；
    - not_promising：阶段 1 完成但排序值无望入席 → 原席保持；
    - budget_insufficient：预算不足 → 原席保持，挑战者留探索候选队列。

    缺失集合（P14 收口，评审 G2）：家族通道一律按**冻结核心根清单逐键**判定
    （`core_rows` / `core_missing` / 档案树内 `family-core-roots.json` 三个来源，
    见 family_core_requirement），旧口径（当时的行集合）原样留作对照：

      - `missing`：**有效缺失 = 逐键 ∪ 自报**（工作项与预算吃这个，谁也不少算）；
      - `missing_authoritative`：逐键值；`missing_reported_row_set`：旧口径自报值；
      - `missing_comparison`：逐键 vs 自报对照表（`frozen_only` = 旧口径少算的那几条）；
      - `missing_requirement`：需求集合来源与冻结件路径（降级时具名标注，不冒充权威）。

    正常通道的键就是根身份（无子场景/对手情景维度），需求集合与旧口径同集合，故两者恒一致。
    """
    channel = epoch["channel"]
    if channel not in CHANNELS:
        raise ValueError("channel 必须是 {0} 之一".format(list(CHANNELS)))
    entries = archive.get("entries", {})
    if challenger_id not in entries:
        raise ValueError("挑战者 {0} 不在档案 entries 中".format(challenger_id))
    ok, reason = _slot_eligibility(entries[challenger_id])
    if not ok:
        raise ValueError("挑战者 {0} 无资格：{1}".format(challenger_id, reason))
    _validate_refresh_roots(channel, refresh_roots)

    current_roots = list(epoch.get("roots", ()))
    current_ids = [r["root_id"] for r in current_roots]
    refresh_ids = [r["root_id"] for r in refresh_roots]
    incumbents = list(archive.get("slots", {}).get(_channel_slot_key(channel), ()))
    participants = sorted(set(incumbents) | {challenger_id} | set(contenders))

    def _merge_evals(cid: str) -> Dict[str, Any]:
        """身份的评估记录：档案存量 + 本次 evaluations + 补充覆盖。"""
        entry = entries.get(cid, {})
        merged: Dict[str, Any] = {}
        if channel == "normal":
            merged.update(entry.get("normal_evaluations", {}))
        else:
            for sub, rows in (entry.get("family_evaluations", {}) or {}).items():
                merged[sub] = dict(rows)
        extra = (evaluations.get(cid) or {})
        if channel == "normal":
            merged.update(extra)
        else:
            for sub, rows in extra.items():
                merged.setdefault(sub, {}).update(rows or {})
        if extra_incumbent_evaluations and cid in extra_incumbent_evaluations:
            more = extra_incumbent_evaluations[cid] or {}
            if channel == "normal":
                merged.update(more)
            else:
                for sub, rows in more.items():
                    merged.setdefault(sub, {}).update(rows or {})
        return merged

    evals_by_cid = {cid: _merge_evals(cid) for cid in participants}
    notes: List[str] = []

    def _known_root_ids(cid: str) -> List[str]:
        evals = evals_by_cid[cid]
        if channel == "normal":
            return list(evals)
        return [rid for sub in evals.values() for rid in sub]

    ignored = sorted({
        rid for cid in participants for rid in _known_root_ids(cid)
        if rid not in current_ids + refresh_ids
    })
    if ignored:
        notes.append("不同样本集不直接争冠军：忽略 epoch 外多余根 {0}".format(ignored))

    def _phase_missing(cid: str, ids: Sequence[str]) -> List[str]:
        evals = evals_by_cid[cid]
        if channel == "normal":
            return [rid for rid in ids if rid not in evals]
        missing = []
        for root in current_roots + list(refresh_roots):
            if root["root_id"] not in ids:
                continue
            rows = evals.get(root.get("sub_scenario")) or {}
            if family_cell_lookup(rows, root.get("opponent_mix"),
                                  root["root_id"]) is None:
                # 家族令牌带对手情景：家族根身份不含情景，同一 root_id 的 H/M
                # 是两个不同实例，令牌必须可分（补根层据此按情景复现）。
                missing.append("{0}|{1}|{2}".format(root.get("sub_scenario"),
                                                   root.get("opponent_mix"),
                                                   root["root_id"]))
        return missing

    # —— P14：需求集合（逐键）与权威缺失 ——
    requirement = (family_core_requirement(
        channel=channel, core_rows=core_rows, core_missing=core_missing,
        persist_dir=persist_dir) if channel in FAMILIES
        else {"source": "epoch_row_set", "path": None, "rows": [],
              "authoritative_missing": None, "rows_seen": 0, "problems": [],
              "note": ("正常通道的键就是根身份（无子场景/对手情景维度）：需求集合 = "
                       "epoch 根 + 刷新批，与旧口径同集合，对照表恒一致")})
    # P14-FU1 收残留：家族通道 + 调用方**声明了运行目录**（persist_dir）却拿不到冻结核心根
    # 清单 ⇒ **拒绝**，不用"当时的行集合"降级口径给缺失集合——那正是 P9c 少算 1 的口径
    # （评审 G2：不得以数量补齐）。纯函数式调用（未给 persist_dir，例如单元测试/离线复算）
    # 仍走降级路径，但在返回值里具名标注（见 family_core_requirement 的 note/problems）。
    if (channel in FAMILIES and persist_dir is not None
            and requirement["source"] == "epoch_row_set"):
        problems = "；".join(str(item.get("detail"))
                             for item in (requirement.get("problems") or ()))
        raise ValueError(
            "家族通道 {0} 的缺失集合必须按**冻结核心根清单**逐键判定，但档案树内没有可用的 "
            "{1}（persist_dir={2}{3}）：拒绝用「当时的行集合」降级口径给出缺失集合"
            "（该口径会漏掉不在行集合里的核心根，P9c 实测少 1：branch_open|H|root000）。"
            "处置：先按 sitin_search.av_family_core_root_list 冻结清单，或由调用方显式注入 "
            "core_rows / core_missing".format(
                channel, FAMILY_CORE_LIST_FILENAME, persist_dir,
                "；冻结件问题：" + problems if problems else "（文件不存在）"))
    requirement_annotation = {
        "schema": FAMILY_CORE_LIST_SCHEMA, "channel": channel,
        "source": requirement["source"], "path": requirement["path"],
        "rows_seen": requirement.get("rows_seen"),
        "problems": list(requirement.get("problems") or ()),
        "core_list_path": requirement["path"],
        "note": requirement["note"]}

    def _requirement_keys(*, include_refresh: bool) -> List[Tuple[str, str, str]]:
        """逐键需求（子场景 × 情景 × 根身份）：冻结清单行 ∪ epoch 根 ∪（本批刷新根）。

        同一根多行**取并集**：令牌（`子场景|情景|根身份`）去重，任何一行要求它，
        它就必须被覆盖——旧实现只在该行集合里找根，行集合外的核心根永远报不出来。
        """

        rows = list(requirement["rows"]) + current_roots \
            + (list(refresh_roots) if include_refresh else [])
        keys: List[Tuple[str, str, str]] = []
        seen = set()
        for row in rows:
            token = (str(row.get("sub_scenario") or ""), str(row.get("opponent_mix") or ""),
                     str(row.get("root_id") or ""))
            if token in seen or not token[2]:
                continue
            seen.add(token)
            keys.append(token)
        return keys

    def _authoritative_missing(cid: str, *, include_refresh: bool) -> List[str]:
        """**权威逐键**缺失：需求集合里的每个键都要有合格记录（不合格即缺失）。

        调用方注入了权威结论（core_missing，来自 sitin_search.av_family_core_coverage）
        时**直接采用**——那才是真正的同源口径；否则按上面同一套逐键判据自算。
        """

        injected = requirement.get("authoritative_missing") or {}
        if str(cid) in injected:
            return sorted(str(token) for token in (injected[str(cid)]) or ())
        # 该身份不在注入结论里（或未注入）：不拿"没有点名"当"没有缺失"（失败关闭），
        # 落到下面的自算路径；需求集合来源与降级标注一并在 missing_requirement。
        if channel == "normal":
            return _phase_missing(cid, current_ids + (
                refresh_ids if include_refresh else []))
        return ["{0}|{1}|{2}".format(sub, mix, root_id)
                for (sub, mix, root_id) in _requirement_keys(include_refresh=include_refresh)
                if not family_key_usable(evals_by_cid[cid], sub_scenario=sub,
                                         opponent_mix=mix, root_id=root_id)]

    def _missing_block(cid: str, *, include_refresh: bool) -> Dict[str, Any]:
        """一个身份的缺失三件套：有效值（逐键 ∪ 自报）、逐键值、自报值、对照表。"""

        authoritative = _authoritative_missing(cid, include_refresh=include_refresh)
        reported = _phase_missing(cid, current_ids + (
            refresh_ids if include_refresh else []))
        return {"missing": sorted(set(authoritative) | set(reported)),
                "authoritative": authoritative, "reported": reported,
                "comparison": family_missing_comparison(
                    authoritative=authoritative, reported=reported)}

    def _with_missing(result: Dict[str, Any], *, cids: Sequence[str],
                      include_refresh: bool) -> Dict[str, Any]:
        """给结果补上缺失三件套 + 需求来源标注（每条返回路径口径一致）。"""

        blocks = {cid: _missing_block(cid, include_refresh=include_refresh)
                  for cid in cids}
        result["missing"] = {cid: blocks[cid]["missing"] for cid in cids}
        result["missing_authoritative"] = {cid: blocks[cid]["authoritative"]
                                           for cid in cids}
        result["missing_reported_row_set"] = {cid: blocks[cid]["reported"]
                                              for cid in cids}
        result["missing_comparison"] = {cid: blocks[cid]["comparison"] for cid in cids}
        result["missing_requirement"] = dict(requirement_annotation)
        return result

    # 阶段 1：挑战者补齐需求集合（冻结清单逐键 ∪ epoch 根）。
    phase1_block = _missing_block(challenger_id, include_refresh=False)
    if phase1_block["missing"]:
        return _with_missing({
            "status": "pending_partial",
            "phase": "phase1",
            "epoch": dict(epoch),
            "archive": archive,
            "missing": {challenger_id: phase1_block["missing"]},
            "pending": {
                "challenger_id": challenger_id,
                "received": {challenger_id: dict(evaluations.get(challenger_id) or {})},
                "missing": {challenger_id: phase1_block["missing"]},
                "note": "阶段 1 未补齐当前根集：保持原 epoch 原席，结果暂存 pending",
            },
            "notes": notes,
        }, cids=[challenger_id], include_refresh=False)

    # 有望入席：挑战者排序值 ≥ 原席者最小排序值（同根集比较）。
    challenger_value = _channel_value(channel, evals_by_cid[challenger_id], current_roots)
    if challenger_value is None:
        raise ValueError("挑战者在当前根集上无法计算排序值（缺 H/M 混合）")
    if incumbents:
        incumbent_values = {}
        for cid in incumbents:
            value = _channel_value(channel, evals_by_cid[cid], current_roots)
            if value is None:
                # 原席者缺当前根记录：也必须补齐（不拿不同根集排序）。
                incumbent_block = _missing_block(cid, include_refresh=False)
                fallback = incumbent_block["missing"] or list(current_ids)
                return _with_missing({
                    "status": "pending_partial",
                    "phase": "phase1",
                    "epoch": dict(epoch),
                    "archive": archive,
                    "missing": {cid: fallback},
                    "pending": {
                        "challenger_id": challenger_id,
                        "received": {cid: dict(evaluations.get(cid) or {})
                                     for cid in participants},
                        "missing": {cid: fallback},
                        "note": "原席者缺当前根记录：补齐前不比较（同根集原则）",
                    },
                    "notes": notes,
                }, cids=[cid], include_refresh=False)
            incumbent_values[cid] = value
        threshold = min(incumbent_values.values())
    else:
        threshold = None
    promising = threshold is None or challenger_value >= threshold
    if not promising:
        return {
            "status": "not_promising",
            "phase": "phase1",
            "epoch": dict(epoch),
            "archive": archive,
            "challenger_value": challenger_value,
            "incumbent_values": incumbent_values if incumbents else {},
            "notes": notes + ["挑战者当前根集排序值无望入席：原席保持，不预留刷新批"],
        }

    # 阶段 2：本次全部参与重排身份（含原席者）补齐当前+刷新根。
    required: Dict[str, List[str]] = {}
    for cid in participants:
        # P14：逐键 ∪ 自报（刷新根这种"不在冻结清单里的额外需求"一条不丢）。
        missing = _missing_block(cid, include_refresh=True)["missing"]
        if missing:
            required[cid] = missing

    refresh_eval_count = sum(
        len(refresh_ids if channel == "normal" else refresh_ids)
        for _ in participants)
    if budget is not None:
        needed = sum(len(v) for v in required.values())
        if needed > budget:
            queue = list(archive.get("exploration_queue", []))
            if challenger_id not in queue:
                queue.append(challenger_id)
            new_archive = dict(archive)
            new_archive["exploration_queue"] = queue
            return {
                "status": "budget_insufficient",
                "epoch": dict(epoch),
                "archive": new_archive,
                "budget": budget,
                "needed": needed,
                "refresh_eval_count": refresh_eval_count,
                "exploration_queue": queue,
                "notes": notes + ["预算不足：保持原席，挑战者留探索候选队列"],
            }

    if required:
        return _with_missing({
            "status": "pending_partial",
            "phase": "phase2",
            "epoch": dict(epoch),
            "archive": archive,
            "missing": required,
            "pending": {
                "challenger_id": challenger_id,
                "received": {cid: dict(evaluations.get(cid) or {}) for cid in participants},
                "missing": required,
                "note": "部分身份未补齐：保持原 epoch 原席，结果暂存 pending，"
                        "不混合新旧均值（T12）",
            },
            "notes": notes,
        }, cids=[cid for cid in participants if cid in required], include_refresh=True)

    # 原子提交：新 epoch（刷新根入根集，永不流入确认集）+ 通道统一重排。
    core_usage = {row["root_id"]: row.get("usage", "development_core")
                  for row in current_roots}
    new_roots = current_roots + [
        {
            "root_id": root["root_id"],
            "role": "refresh",
            "usage": "development_refresh",
            "confirmation_eligible": False,
            "opponent_mix": root["opponent_mix"],
            **({"sub_scenario": root["sub_scenario"]} if channel in FAMILIES else {}),
        }
        for root in refresh_roots
    ]
    for row in new_roots:
        # 保留核心根原有用途标记（Q2）；缺省即 development_core。
        row.setdefault("usage", core_usage.get(row["root_id"], "development_core"))
    new_epoch = {
        "schema": CHANNEL_EPOCH_SCHEMA,
        "channel": channel,
        "epoch": int(epoch.get("epoch", 1)) + 1,
        "roots": new_roots,
        "pending": None,
    }
    ranked = []
    for cid in participants:
        value = _channel_value(channel, evals_by_cid[cid], new_roots)
        if value is None:
            raise ValueError("身份 {0} 在新根集上无法计算排序值（提交中止）".format(cid))
        entry = entries.get(cid, {})
        if channel == "normal":
            overall = entry.get("overall") or {}
            cost = overall.get("total_cost", 0.0)
            unknown = overall.get("unknown_ratio")
        else:
            fam = (entry.get("family") or {}).get(channel) or {}
            cost = fam.get("total_cost", 0.0)
            unknown = fam.get("unknown_ratio")
        ranked.append({"candidate_id": cid, "sort_value": value,
                       "unknown_ratio": unknown, "total_cost": cost})
    ranked.sort(key=lambda row: (
        -row["sort_value"],
        row["unknown_ratio"] if row["unknown_ratio"] is not None else math.inf,
        row["total_cost"],
        row["candidate_id"],
    ))
    capacity = SLOT_CAPACITY[_channel_slot_key(channel)]
    new_slots = dict(archive.get("slots", {}))
    new_slots[_channel_slot_key(channel)] = [row["candidate_id"] for row in ranked[:capacity]]

    new_entries = dict(entries)
    for cid in participants:
        entry = dict(entries.get(cid, {}))
        if channel == "normal":
            normal = dict(entry.get("normal_evaluations", {}))
            normal.update(evaluations.get(cid) or {})
            entry["normal_evaluations"] = normal
        else:
            fam = dict(entry.get("family_evaluations", {}))
            for sub, rows in (evaluations.get(cid) or {}).items():
                merged = dict(fam.get(sub) or {})
                merged.update(rows or {})
                fam[sub] = merged
            entry["family_evaluations"] = fam
        new_entries[cid] = entry

    new_archive = dict(archive)
    new_archive["slots"] = new_slots
    new_archive["entries"] = new_entries
    new_archive["selection_report"] = dict(archive.get("selection_report", {}))
    new_archive["selection_report"]["challenge_{0}".format(new_epoch["epoch"])] = {
        "channel": channel,
        "ranking": ranked,
        "committed": True,
    }
    queue = [cid for cid in archive.get("exploration_queue", []) if cid != challenger_id]
    new_archive["exploration_queue"] = queue

    result = {
        "status": "committed",
        "epoch_before": int(epoch.get("epoch", 1)),
        "epoch_after": new_epoch["epoch"],
        "archive": new_archive,
        "new_epoch": new_epoch,
        "ranking": ranked,
        "confirmation_eligible_roots": confirmation_eligible_roots(new_epoch),
        "notes": notes + [
            "原子提交：新 epoch 统一用核心+刷新根集重排；核心/刷新根用途均为 "
            "development_*（Q2），永不流入确认集",
        ],
    }
    if persist_dir is not None:
        # Q9：提交即完整持久化——档案/epoch/参与者补根材料/重算摘要全部落盘，
        # 进程重启后从盘上重载即可提名，不再出现"缺根"误报。
        result["persisted"] = _persist_challenge_commit(Path(persist_dir), result,
                                                        evals_by_cid, channel)
    return result


def _persist_challenge_commit(out_dir: Path, result: Mapping[str, Any],
                              evals_by_cid: Mapping[str, Any],
                              channel: str) -> Dict[str, Any]:
    """把一次 committed 挑战的全部材料原子落盘（Q9）。

    产物：archive.json / epoch.json（tmp+rename 原子替换）、participants/<cid>.json
    （该身份本通道合并后的全部根评估）、commit-summary.json（重排摘要与根覆盖）。
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    def _atomic_write(path: Path, payload: Any) -> None:
        tmp_path = path.with_name(path.name + ".tmp")
        tmp_path.write_text(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + NEWLINE,
            encoding="utf-8")
        tmp_path.replace(path)

    archive = result["archive"]
    new_epoch = result["new_epoch"]
    _atomic_write(out_dir / "archive.json", archive)
    _atomic_write(out_dir / "epoch.json", new_epoch)
    root_ids = [row["root_id"] for row in new_epoch.get("roots", ())]
    participants_out: Dict[str, Any] = {}
    (out_dir / "participants").mkdir(parents=True, exist_ok=True)
    for cid in sorted(evals_by_cid):
        evals = evals_by_cid[cid]
        if channel == "normal":
            covered = sorted(rid for rid in root_ids if rid in evals)
            payload = {"candidate_id": cid, "normal_evaluations": evals,
                       "roots_covered": covered,
                       "roots_missing": sorted(set(root_ids) - set(covered))}
        else:
            # 家族通道：逐（子场景 × 对手情景 × 根）核对覆盖——情景限定格键下
            # 「键在不在 root_ids 里」不再等于「该根证据在不在」。
            covered, uncovered = [], []
            for row in new_epoch.get("roots", ()):
                rows = evals.get(row.get("sub_scenario")) or {}
                if family_cell_lookup(rows, row.get("opponent_mix"),
                                      row["root_id"]) is not None:
                    covered.append(row["root_id"])
                else:
                    uncovered.append(row["root_id"])
            payload = {"candidate_id": cid, "family_evaluations": evals,
                       "roots_covered": sorted(set(covered)),
                       "roots_missing": sorted(set(uncovered))}
        participants_out[cid] = payload
        _atomic_write(out_dir / "participants" / "{0}.json".format(cid), payload)
    summary = {
        "schema": "sitin-challenge-commit/1",
        "channel": channel,
        "epoch_before": result["epoch_before"],
        "epoch_after": result["epoch_after"],
        "ranking": result["ranking"],
        "root_ids": root_ids,
        "confirmation_eligible_roots": result["confirmation_eligible_roots"],
        "participants": {cid: {"roots_covered": payload["roots_covered"],
                               "roots_missing": payload["roots_missing"]}
                         for cid, payload in participants_out.items()},
        "slots_after": archive.get("slots", {}),
    }
    _atomic_write(out_dir / "commit-summary.json", summary)
    return {
        "dir": str(out_dir),
        "archive": str(out_dir / "archive.json"),
        "epoch": str(out_dir / "epoch.json"),
        "participants": sorted(participants_out),
        "commit_summary": str(out_dir / "commit-summary.json"),
    }


# ---------------------------------------------------------------------------
# 4. 父代与算子调度（§9.3）
# ---------------------------------------------------------------------------

#: M1 父代通道循环（§9.3）：整体→专长→整体→专长→探索。
CHANNEL_CYCLE: Tuple[str, ...] = ("overall", "specialty", "overall", "specialty", "exploration")
#: 生成序列（§9.3）：初始化 I1；此后每 4 提案 = 3×M1 + 1×I1（失败/重复也消耗额度）。
BLOCK_SIZE = 4
M1_PER_BLOCK = 3


def _m1_operator_for(proposal_no: int) -> bool:
    """提案 n≥2 是否为 M1：块内 0/1/2 位 M1，第 3 位 I1。"""
    return (proposal_no - 2) % BLOCK_SIZE < M1_PER_BLOCK


#: 提案历史**内容键**（P18）：同一提案被登记两次（事件账本 + 状态投影）时，只允许
#: 这些**影响调度且可核**的字段一致；created_at_utc / source / iter_dir 等纯登记面
#: 字段允许不同（搬运目录后事件里的 iter_dir 仍指原路径，投影用当前路径）。
HISTORY_CONTENT_KEYS: Tuple[str, ...] = (
    "operator", "planned_operator", "applied_operator", "parent_candidate_id",
    "channel", "family", "candidate_id", "terminal_status", "failed", "duplicate",
    "recorded_proposal_no")


def _proposal_identity(row: Mapping[str, Any]) -> Optional[Tuple[str, ...]]:
    """提案**显式身份**（P18）：(run_id, iteration_no) → iter_dir → 记录号；全缺为 None。

    只用产物里**显式写出**的身份字段，不做内容散列、不猜：没有身份字段的旧历史一律
    视为"不可判重复"，交给 check_proposal_history 标 unverified。
    """

    def _positive_int(value: Any) -> bool:
        return isinstance(value, int) and not isinstance(value, bool) and value > 0

    run_id = row.get("run_id")
    run_id = run_id.strip() if isinstance(run_id, str) else ""
    recorded = row.get("recorded_proposal_no")
    iteration_no = row.get("iteration_no")
    # ① (运行, 迭代序) 最精确——两者都是产物自己写的显式身份。
    if run_id and _positive_int(iteration_no):
        return ("iteration", run_id, str(iteration_no))
    # ② (运行, 记录号)：历史行里**一定有**的一对（事件与状态投影都带 run_id 与记录号），
    #    也是跨目录搬运后唯一能把"同一提案的两条登记"认成一体的键（搬运后 iter_dir 不同源）。
    if run_id and _positive_int(recorded):
        return ("proposal", run_id, str(recorded))
    # ③ 目录 / ④ 仅记录号：缺运行身份时的保守回退（仍不猜内容）。
    iter_dir = row.get("iter_dir")
    if isinstance(iter_dir, str) and iter_dir.strip():
        return ("iter_dir", iter_dir.strip())
    if _positive_int(recorded):
        return ("proposal_no", str(recorded))
    return None


def _history_content(row: Mapping[str, Any]) -> Tuple[Any, ...]:
    """提案记录的**调度内容键**（HISTORY_CONTENT_KEYS 的规范化取值）。"""

    out: List[Any] = []
    for key in HISTORY_CONTENT_KEYS:
        value = row.get(key)
        if key in ("failed", "duplicate"):
            out.append(bool(value))
        elif value is None or isinstance(value, (str, int, float, bool)):
            out.append(value)
        else:
            out.append(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                  separators=(",", ":")))
    return tuple(out)


def check_proposal_history(history: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    """提案历史完整性检查（§9.3 计数口径；P18）：同一提案只计一次，缺项即具名报错。

    裁定依据（R9 计划 §13 A / 复审 R6「声明 M1 实跑 I1」）：提案号与算子位次由**已消费
    提案序列**决定，`proposal_no = len(history) + 1`；所以历史必须是"每个提案恰一条"。
    本函数把这条合同变成**可判**的检查，不用位置号把坏数据凑成一个看起来合理的答案：

    - **重复项**：同一提案被登记两次（跨目录搬运后事件账本里的 iter_dir 仍指原路径、
      状态投影用当前路径 → 两条记录都在，显式身份不同源）→ 按显式身份
      (run_id, iteration_no) / iter_dir / 记录号 判为同一提案：调度内容一致即折叠为一条
      （`collapsed_same_proposal` 逐条留档），内容冲突即 ValueError（不猜哪条为准）。
    - **缺项**：带记录号的记录必须**连续递增**（允许从 >1 起——跨运行链只持有后半段）；
      断层即 ValueError：缺了哪次提案无法还原，位置号硬凑会算错算子位次。
      无记录号/无身份的旧历史不做猜测，标 integrity=unverified（可判的部分仍然判）。
    - **失败迭代**：失败/重复的提案同样消耗提案额度（§9.3），照常计入并单列计数。

    返回 {"records_in", "proposals", "canonical", "failed_proposals",
    "duplicate_proposals", "collapsed_same_proposal", "integrity", "note"}。
    """

    rows = [row for row in history if isinstance(row, Mapping)]
    dropped = [row for row in history if not isinstance(row, Mapping)]
    identities = [_proposal_identity(row) for row in rows]
    groups: Dict[Tuple[str, ...], List[int]] = {}
    for index, identity in enumerate(identities):
        if identity is not None:
            groups.setdefault(identity, []).append(index)
    keep = [True] * len(rows)
    collapsed: List[Dict[str, Any]] = []
    for identity in sorted(groups):
        members = groups[identity]
        if len(members) < 2:
            continue
        first = rows[members[0]]
        contents = {_history_content(rows[index]) for index in members}
        if len(contents) > 1:
            raise ValueError(
                "提案历史同一身份出现互相矛盾的记录（{0}={1}）：{2}；"
                "不得猜测哪条为准（P18）".format(
                    identity[0], identity[1:],
                    [rows[index] for index in members]))
        for index in members[1:]:
            keep[index] = False
        collapsed.append({
            "identity": list(identity),
            "records": len(members),
            "kept": {"iter_dir": first.get("iter_dir"),
                     "source": first.get("source"),
                     "recorded_proposal_no": first.get("recorded_proposal_no")},
            "dropped": [{"iter_dir": rows[index].get("iter_dir"),
                         "source": rows[index].get("source")} for index in members[1:]],
            "note": "同一提案的重复登记（事件账本 + 状态投影）：只计一次",
        })
    canonical = [row for index, row in enumerate(rows) if keep[index]]
    numbered: List[int] = []
    for row in canonical:
        value = row.get("recorded_proposal_no")
        if isinstance(value, int) and not isinstance(value, bool) and value > 0:
            numbered.append(value)
    integrity = "unverified"
    if numbered and len(numbered) == len(canonical):
        # 按**记录号的多重集**判连续：清单的先后由派生侧的时间序决定（事件行不带
        # created_at_utc，排序会把事件排在投影前），而"有没有缺项/重复"与先后无关。
        ordered = sorted(numbered)
        expected = list(range(ordered[0], ordered[0] + len(ordered)))
        if ordered != expected:
            raise ValueError(
                "提案历史缺项或编号断层：记录号 {0} 不是连续的一组（期望 {1}）；"
                "缺了哪次提案无法从产物还原，不用位置号硬凑（P18）".format(
                    ordered, expected))
        integrity = "verified"
    notes: List[str] = []
    if dropped:
        notes.append("忽略 {0} 条非对象历史记录（不猜其含义）".format(len(dropped)))
    if collapsed:
        notes.append("折叠 {0} 组同一提案的重复登记（{1} 条 → {2} 条）".format(
            len(collapsed), len(rows), len(canonical)))
    if integrity != "verified":
        notes.append("记录号不齐或缺失：只能按位置计数，缺项不可判（integrity=unverified）")
    return {
        "records_in": len(history),
        "proposals": len(canonical),
        "canonical": canonical,
        "failed_proposals": sum(1 for row in canonical if row.get("failed")),
        "duplicate_proposals": sum(1 for row in canonical if row.get("duplicate")),
        "collapsed_same_proposal": collapsed,
        "integrity": integrity,
        "note": "；".join(notes),
    }


def next_generation_plan(archive: Mapping[str, Any],
                         history: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    """父代与算子调度（§9.3 固定序列）。纯函数：同 archive+history 恒等输出。

    - 初始化：两个人工种子（efficiency_seed/route_value_seed，均为完整评分函数，
      在档案内作为普通身份参席）+ 一次 I1；
    - 此后每 4 提案 = 3×M1 + 1×I1；失败/重复提案同样消耗额度（history 全量计数）；
    - M1 父代通道按 整体→专长→整体→专长→探索 循环；专长家族轮转；通道内按
      最少被使用次数、candidate_id 排序；空通道跳下一非空；档案空 → I1。

    **提案计数口径（P18，可判合同）**：`proposal_no = 已消费提案数 + 1`；输入 history
    必须是"每个已消费提案恰一条"的时间序序列。因此本函数先做
    `check_proposal_history`：**同一提案的重复登记折叠为一条**（跨目录搬运后事件账本与
    状态投影会各出一条；不折叠会每轮多计一次、把算子位次算错），**编号断层/同身份冲突
    具名 ValueError**（不猜、不用位置号硬凑）。检查结论随计划返回 `history_check`
    （records_in / proposals / collapsed_same_proposal / integrity），使"重算=实际"可对拍。
    """

    history_check = check_proposal_history(history)
    plan = _schedule_from_history(archive, history_check["canonical"])
    plan["history_check"] = {key: value for key, value in history_check.items()
                             if key != "canonical"}
    return plan


def _schedule_from_history(archive: Mapping[str, Any],
                           history: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    """按**已规范化**的提案历史排下一步（入参必须来自 check_proposal_history）。"""

    proposal_no = len(history) + 1
    archive_entries = archive.get("entries", {}) if archive else {}
    slots = archive.get("slots", {}) if archive else {}

    def _usage_counts() -> Dict[str, Dict[str, Dict[str, int]]]:
        counts: Dict[str, Dict[str, Dict[str, int]]] = {
            "overall": {}, "exploration": {},
            "specialty": {family: {} for family in FAMILIES},
        }
        for record in history:
            if record.get("operator") != "M1":
                continue
            channel = record.get("channel")
            parent = record.get("parent_candidate_id")
            if not isinstance(parent, str):
                continue
            if channel == "specialty":
                family = record.get("family")
                if family in counts["specialty"]:
                    bucket = counts["specialty"][family]
                    bucket[parent] = bucket.get(parent, 0) + 1
            elif channel in counts:
                bucket = counts[channel]
                bucket[parent] = bucket.get(parent, 0) + 1
        return counts

    usage = _usage_counts()

    def _pick_parent(candidates: Sequence[str], bucket: Dict[str, int]) -> Optional[str]:
        eligible_ids = sorted(c for c in candidates if c in archive_entries)
        if not eligible_ids:
            return None
        return min(eligible_ids, key=lambda cid: (bucket.get(cid, 0), cid))

    def _with_usage(operator: str, channel: Optional[str], family: Optional[str],
                    parent: Optional[str]) -> Dict[str, Dict[str, int]]:
        out = {"overall": dict(usage["overall"]),
               "specialty": {f: dict(usage["specialty"][f]) for f in FAMILIES},
               "exploration": dict(usage["exploration"])}
        if operator == "M1" and parent is not None:
            if channel == "specialty" and family in out["specialty"]:
                out["specialty"][family][parent] = out["specialty"][family].get(parent, 0) + 1
            elif channel in out:
                out[channel][parent] = out[channel].get(parent, 0) + 1
        return out

    archive_has_seated = any(slots.get(ch) for ch in
                             ("overall", "exploration") + FAMILIES)
    seeds_in_archive = sorted(cid for cid, entry in archive_entries.items()
                              if (entry or {}).get("kind") == "seed" or cid in SEED_IDS)

    # 档案空（无任何已入档身份）→ I1（不把无评价失败候选伪装成冠军）。
    if not archive_entries or not archive_has_seated:
        return {
            "proposal_no": proposal_no,
            "operator": "I1",
            "parent_candidate_id": None,
            "channel": None,
            "family": None,
            "slot_usage_after": _with_usage("I1", None, None, None),
            "initialization": {"seeds": seeds_in_archive} if proposal_no == 1 else None,
            "reason": "档案空或无已入档席位：使用 I1",
        }

    # 初始化提案（第 1 次）固定 I1。
    if proposal_no == 1:
        return {
            "proposal_no": proposal_no,
            "operator": "I1",
            "parent_candidate_id": None,
            "channel": None,
            "family": None,
            "slot_usage_after": _with_usage("I1", None, None, None),
            "initialization": {"seeds": seeds_in_archive},
        }

    if not _m1_operator_for(proposal_no):
        return {
            "proposal_no": proposal_no,
            "operator": "I1",
            "parent_candidate_id": None,
            "channel": None,
            "family": None,
            "slot_usage_after": _with_usage("I1", None, None, None),
            "initialization": None,
        }

    m1_count = sum(1 for record in history if record.get("operator") == "M1")
    specialty_count = sum(1 for record in history
                          if record.get("operator") == "M1"
                          and record.get("channel") == "specialty")
    cycle_pos = m1_count % len(CHANNEL_CYCLE)

    def _specialty_family_and_parent(turn: int):
        """专长家族轮转：从第 turn 个专长位起找第一个非空家族（轮转序）。"""
        for step in range(len(FAMILIES)):
            family = FAMILIES[(turn + step) % len(FAMILIES)]
            parent = _pick_parent(slots.get(family, ()), usage["specialty"][family])
            if parent is not None:
                return family, parent, step
        return None, None, None

    for _skip in range(len(CHANNEL_CYCLE)):
        channel = CHANNEL_CYCLE[(cycle_pos + _skip) % len(CHANNEL_CYCLE)]
        if channel == "overall":
            parent = _pick_parent(slots.get("overall", ()), usage["overall"])
            if parent is not None:
                return {
                    "proposal_no": proposal_no,
                    "operator": "M1",
                    "parent_candidate_id": parent,
                    "channel": "overall",
                    "family": None,
                    "slot_usage_after": _with_usage("M1", "overall", None, parent),
                    "initialization": None,
                }
        elif channel == "specialty":
            family, parent, _advanced = _specialty_family_and_parent(specialty_count)
            if family is not None and parent is not None:
                return {
                    "proposal_no": proposal_no,
                    "operator": "M1",
                    "parent_candidate_id": parent,
                    "channel": "specialty",
                    "family": family,
                    "slot_usage_after": _with_usage("M1", "specialty", family, parent),
                    "initialization": None,
                }
        else:
            parent = _pick_parent(slots.get("exploration", ()), usage["exploration"])
            if parent is not None:
                return {
                    "proposal_no": proposal_no,
                    "operator": "M1",
                    "parent_candidate_id": parent,
                    "channel": "exploration",
                    "family": None,
                    "slot_usage_after": _with_usage("M1", "exploration", None, parent),
                    "initialization": None,
                }
    return {
        "proposal_no": proposal_no,
        "operator": "I1",
        "parent_candidate_id": None,
        "channel": None,
        "family": None,
        "slot_usage_after": _with_usage("I1", None, None, None),
        "initialization": None,
        "reason": "M1 通道全部为空：回退 I1",
    }


# ---------------------------------------------------------------------------
# 5. 提名算法（§8.3 独立确认合同）
# ---------------------------------------------------------------------------


def _canonical_json(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _source_digest(payload: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def nominate_candidate(
    archive: Mapping[str, Any],
    panel_epoch: Mapping[str, Any],
    *,
    budget: Optional[float] = None,
    extra_evaluations: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """提名算法（§8.3）。纯函数。

    - 候选池 = 档案全部安全有效身份（安全 FAIL/效果故障未修复剔除；V2 不在池内，
      其虚拟配对值恒 0 作为对照行）；
    - 用正常通道 panel_epoch 把池内每个候选缺失的开发根补齐（预算不足 →
      nomination_pending_budget，不偷偷排除昂贵候选、不拿不同根集排序）；
    - 按 §9.2 整体席排序键取第一（排序只用 epoch 根集：多余根忽略并记 note）；
    - 最高候选值 ≤ 0 → 不提名（no_positive_candidate），保留档案并报告；
    - 成功 → 冻结 {pool, epoch, ranking, source_ref}，之后才允许打开确认数据。
    """
    if panel_epoch.get("channel") != "normal":
        raise ValueError("提名必须使用正常通道 panel_epoch")
    entries = archive.get("entries", {})
    pool: List[str] = []
    excluded: Dict[str, str] = {}
    for cid in sorted(entries):
        ok, reason = _slot_eligibility(entries[cid])
        if ok:
            pool.append(cid)
        else:
            excluded[cid] = reason or "不合格"

    roots = list(panel_epoch.get("roots", ()))
    root_ids = [r["root_id"] for r in roots]

    def _evals(cid: str) -> Dict[str, Any]:
        merged = dict(entries.get(cid, {}).get("normal_evaluations", {}) or {})
        if extra_evaluations and cid in extra_evaluations:
            merged.update(extra_evaluations[cid] or {})
        return merged

    ignored_roots = sorted({
        rid for cid in pool for rid in _evals(cid) if rid not in root_ids
    })
    notes = []
    if ignored_roots:
        notes.append("不同根集不参与排序：忽略 epoch 外多余根 {0}".format(ignored_roots))

    missing = {
        cid: [rid for rid in root_ids if rid not in _evals(cid)]
        for cid in pool
    }
    required = sum(len(v) for v in missing.values())
    if budget is not None and required > budget:
        return {
            "schema": NOMINATION_SCHEMA,
            "nominated": False,
            "status": "nomination_pending_budget",
            "pool": pool,
            "budget": budget,
            "required_evaluations": required,
            "missing_detail": {cid: v for cid, v in missing.items() if v},
            "notes": notes + [
                "补齐预算不足：不偷偷排除昂贵候选、不拿不同根集排序（§8.3）",
            ],
        }

    if required:
        raise ValueError(
            "预算已覆盖但补齐结果缺失（纯函数要求调用方先完成补齐并把数据放入 "
            "extra_evaluations）：{0}".format(
                {cid: v for cid, v in missing.items() if v}))

    ranking = []
    for cid in pool:
        value = _normal_sort_value(_evals(cid), roots)
        if value is None:
            raise ValueError("候选 {0} 在 epoch 根集上无法计算排序值".format(cid))
        overall = entries.get(cid, {}).get("overall") or {}
        ranking.append({
            "candidate_id": cid,
            "sort_value": value,
            "unknown_ratio": overall.get("unknown_ratio"),
            "total_cost": overall.get("total_cost", 0.0),
        })
    ranking.sort(key=lambda row: (
        -row["sort_value"],
        row["unknown_ratio"] if row["unknown_ratio"] is not None else math.inf,
        row["total_cost"],
        row["candidate_id"],
    ))
    v2_row = {
        "candidate_id": V2_BASELINE_IDS[0],
        "sort_value": 0.0,
        "virtual": True,
        "note": "V2 固定基线虚拟配对值恒 0（§8.3），不在池内、不占席",
    }
    merged_view = sorted(ranking + [v2_row],
                         key=lambda row: (-row["sort_value"], row["candidate_id"]))

    best = ranking[0] if ranking else None
    if best is None or best["sort_value"] <= 0:
        return {
            "schema": NOMINATION_SCHEMA,
            "nominated": False,
            "reason": "no_positive_candidate",
            "pool": pool,
            "best": best,
            "v2_virtual_paired_value": 0.0,
            "ranking_view_with_v2": merged_view,
            "notes": notes + ["最高候选值≤0：不提名，保留档案并报告本次开发未选出整体优胜"],
        }

    frozen = {
        "pool": pool,
        "epoch": {
            "channel": panel_epoch["channel"],
            "epoch": panel_epoch.get("epoch"),
            "root_ids": root_ids,
            "confirmation_eligible_roots": confirmation_eligible_roots(panel_epoch),
        },
        "ranking": ranking,
        "ranking_view_with_v2": merged_view,
    }
    return {
        "schema": NOMINATION_SCHEMA,
        "nominated": True,
        "candidate_id": best["candidate_id"],
        "sort_value": best["sort_value"],
        "frozen": frozen,
        "source_ref": _source_digest({
            "archive_slots": archive.get("slots", {}),
            "pool": pool,
            "epoch": frozen["epoch"],
            "ranking": ranking,
        }),
        "notes": notes + [
            "提名池、面板、排序结果冻结于 source_ref；之后才允许打开确认数据（§8.3）",
        ],
    }


# ---------------------------------------------------------------------------
# CLI（argparse 风格对齐 sitin_stage / sitin_opportunities）
# ---------------------------------------------------------------------------


def _load_json(path: str) -> Any:
    if path == "-":
        return json.loads(sys.stdin.read())
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _write_json(path: Optional[str], payload: Any) -> None:
    if not path:
        return
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + NEWLINE,
        encoding="utf-8",
    )


def cmd_statistics(args: argparse.Namespace) -> int:
    samples = _load_json(args.samples)
    if not isinstance(samples, list):
        print(json.dumps({"ok": False, "reason": "--samples 必须是样本 JSON 数组"},
                         ensure_ascii=False))
        return 2
    stats = paired_stage_statistics(samples, min_roots=args.min_roots)
    _write_json(args.out, stats)
    print(json.dumps({
        "ok": True,
        "schema": stats["schema"],
        "n_samples": stats["n_samples"],
        "invalid_count": stats["invalid_count"],
        "uncomputable_count": stats["uncomputable_count"],
        "candidates": sorted(stats["by_candidate"]),
    }, ensure_ascii=False))
    return 0


def cmd_update_archive(args: argparse.Namespace) -> int:
    previous = _load_json(args.archive_in) if args.archive_in else None
    safety_map = _load_json(args.safety) if args.safety else {}
    signatures = _load_json(args.signatures) if args.signatures else {}
    entries: List[Dict[str, Any]] = []
    if args.entries:
        loaded = _load_json(args.entries)
        if not isinstance(loaded, list):
            print(json.dumps({"ok": False, "reason": "--entries 必须是条目 JSON 数组"},
                             ensure_ascii=False))
            return 2
        entries = loaded
    if args.samples:
        samples = _load_json(args.samples)
        by_candidate: Dict[str, List[Mapping[str, Any]]] = {}
        for sample in samples:
            status, _ = classify_sample(sample)
            if status == "usable":
                by_candidate.setdefault(sample["candidate_id"], []).append(sample)
        for cid in sorted(by_candidate):
            entries.append(build_archive_entry(
                cid, by_candidate[cid],
                safety=(safety_map or {}).get(cid, "PASS"),
                behavior_signature=(signatures or {}).get(cid),
                min_roots=args.min_roots,
            ))
    archive = update_archive(entries, previous=previous)
    _write_json(args.out, archive)
    print(json.dumps({
        "ok": True,
        "schema": archive["schema"],
        "slots": archive["slots"],
        "distinct_candidates": archive["distinct_candidates"],
        "exploration_queue": archive["exploration_queue"],
    }, ensure_ascii=False))
    return 0


def cmd_next_plan(args: argparse.Namespace) -> int:
    archive = _load_json(args.archive) if args.archive else {"entries": {}, "slots": {}}
    history = _load_json(args.history) if args.history else []
    plan = next_generation_plan(archive, history)
    _write_json(args.out, plan)
    print(json.dumps(plan, ensure_ascii=False, sort_keys=True))
    return 0


def cmd_nominate(args: argparse.Namespace) -> int:
    archive = _load_json(args.archive)
    epoch = _load_json(args.epoch)
    extra = _load_json(args.extra_evaluations) if args.extra_evaluations else None
    try:
        result = nominate_candidate(
            archive, epoch, budget=args.budget, extra_evaluations=extra)
    except ValueError as error:
        print(json.dumps({"ok": False, "reason": str(error)}, ensure_ascii=False))
        return 2
    _write_json(args.out, result)
    print(json.dumps({
        "ok": True,
        "nominated": result["nominated"],
        "candidate_id": result.get("candidate_id"),
        "reason": result.get("reason"),
        "status": result.get("status"),
    }, ensure_ascii=False))
    return 0


def build_arg_parser() -> argparse.ArgumentParser:
    here = str(Path(__file__).resolve())
    epilog = NEWLINE.join((
        "真实调用示例：",
        "  " + sys.executable + " " + here + " statistics --samples samples.json --out stats",
        "  " + sys.executable + " " + here + " update-archive --samples samples.json"
        + " --safety safety.json --signatures sigs.json --archive-in archive.json"
        + " --out archive",
        "  " + sys.executable + " " + here + " next-plan --archive archive.json"
        + " --history history.json",
        "  " + sys.executable + " " + here + " nominate --archive archive.json"
        + " --epoch epoch.json --budget 24",
    ))
    parser = argparse.ArgumentParser(
        description="C2 根级配对统计、有限档案（8 席）、panel_epoch 通道替换、"
                    "父代调度与提名（SEARCH-SPACE-REDESIGN §8—§9；纯数据工具，"
                    "零真实桌赛执行）",
        epilog=epilog,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    statistics = sub.add_parser(
        "statistics", help="根级配对统计（§8.1）：按 (候选×场景×H/M) 分面板输出 "
                           "n_roots/mean_delta/standard_error/interval_95/status")
    statistics.add_argument("--samples", required=True,
                            help="样本 JSON 数组（'-' 读 stdin）；每条为 C1 面板双臂记录")
    statistics.add_argument("--min-roots", type=int, default=2,
                            help="面板 status=ok 所需最少可用根数（默认 2，不足标 insufficient）")
    statistics.add_argument("--out", default=None, help="完整统计 JSON 写出路径（可省）")
    statistics.set_defaults(func=cmd_statistics)

    update = sub.add_parser(
        "update-archive", help="确定性重排 8 席档案（§9.1/§9.2）：overall×2+家族×4+探索×2")
    update.add_argument("--samples", default=None,
                        help="样本 JSON 数组（自动按 candidate_id 聚合建条目）")
    update.add_argument("--entries", default=None,
                        help="预构建条目 JSON 数组（与 --samples 可同时给）")
    update.add_argument("--safety", default=None,
                        help="JSON：{candidate_id: PASS|FAIL}（安全 FAIL 不占席不当父代）")
    update.add_argument("--signatures", default=None,
                        help="JSON：{candidate_id: 行为签名}（探索席最小距离最大化用）")
    update.add_argument("--archive-in", default=None, help="既有档案 JSON（承接探索队列）")
    update.add_argument("--min-roots", type=int, default=2)
    update.add_argument("--out", default=None, help="档案 JSON 写出路径（可省）")
    update.set_defaults(func=cmd_update_archive)

    plan = sub.add_parser(
        "next-plan", help="父代与算子调度（§9.3）：初始化 I1；此后每 4 提案=3×M1+1×I1；"
                          "失败/重复也消耗额度")
    plan.add_argument("--archive", required=True, help="档案 JSON（update-archive 产物）")
    plan.add_argument("--history", default=None,
                      help="历史提案 JSON 数组（省略视为空历史）")
    plan.add_argument("--out", default=None)
    plan.set_defaults(func=cmd_next_plan)

    nominate = sub.add_parser(
        "nominate", help="提名算法（§8.3）：正常通道 panel_epoch 补齐池内缺失开发根后"
                         "按整体席排序键取第一；≤0 不提名；预算不足 pending")
    nominate.add_argument("--archive", required=True)
    nominate.add_argument("--epoch", required=True,
                          help="正常通道 panel_epoch JSON（build_channel_epoch 产物）")
    nominate.add_argument("--budget", type=float, default=None,
                          help="补齐预算（缺失根评估数；不足输出 nomination_pending_budget）")
    nominate.add_argument("--extra-evaluations", default=None,
                          help="JSON：{candidate_id: {root_id: {d_point,d_low,d_high,...}}}，"
                               "预算覆盖后由调用方补齐的数据")
    nominate.add_argument("--out", default=None)
    nominate.set_defaults(func=cmd_nominate)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
