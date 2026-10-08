"""坐隐 3.0：评分相关**规则可枚举场景类**清单、逐类覆盖账与分量—场景类矩阵。

## 这份清单回答什么

第三阶段的评分器要按**官方番型表的价值路径**组织分量。要让"每个分量作用在哪些场景上"
变成可核验的事实，就必须先把**场景类**枚举出来：每条含稳定 id、官方依据（文件+行号）、
可判定谓词（用哪些 `EvaluationContext` / `CandidateFacts` 字段判定）、判定位点（哪些
动作族上存在翻转可能）、与其他类的关系（互斥 / 蕴含 / 叠加）。

**口径（用户 2026-09-16 裁定）**：覆盖按**规则可枚举场景**度量，**与语料频率无关**。
不得用语料频率给机制下稀缺性判断，不得据此做预算规划。**记录缺口 ≠ 机制稀有**。

## 四种"类"必须分开读（本文件的一等区分）

| kind | 含义 | 覆盖怎么算 |
| --- | --- | --- |
| `rule_scenario` | 官方/规则可枚举的**局面类** | 由谓词在窗口上判定 |
| `evidence_state` | **事实可判定性**本身构成的类（未知不等于零） | 谓词判定"该事实是否未知" |
| `settlement_outcome` | 结算**支付角色**类（庄/闲；胡家身份） | 窗口侧只判"本人庄/闲"；胡家是未来事件 |
| `official_bound` | 官方给出的**上界组合**（最大牌型） | 只校验"与该上界相容的必要条件" |

**一个位点可以同时属于多个类**（官方明文叠加例：指南第 23 / 61 / 63 / 65 行）。
因此 `classify_window` 返回**集合**，逐类各记一笔，**不得**把多类压成单一分类。

## 覆盖四态（逐类独立，**不得合并成单一总分**）

    sufficient      该类在面板上判定出的窗口数 >= MIN_CLASS_WINDOWS
    insufficient    该类有窗口，但少于下限（证据不足，不是"无影响"）
    unknown         该类**一个窗口都没判定出来**，且有窗口因事实缺失无法判定
                    —— **不得填零、不得等同于"无影响"、不得并入 not_applicable**
    not_applicable  该类在面板上可判定且一个窗口都不属于它

汇总只另存字段并注明**不得作为准入依据**（`summary.not_admission_basis=true`）；
汇总里**只有一个 verdict 计数表**，没有分数、没有加权、没有排序。

## 权重口径（用户 2026-09-16 裁定，写进产物）

**不得按场景类拍权重。** 规则给的是"番 → 分"的兑换率（×2 番 = ×2 分，log2 下相加；
四分量同尺度 40 分/log2 番是**正确**的）；规则**没给**的是 ①兑现概率 ②得失比
（庄 24 / 闲 10、付 8 / 付 1）。清单与矩阵里**没有**任何"每类一个权重"的字段——
`--check` 会核对这一点（见 `check_weight_fields`）。

## 命令

    .venv/bin/python tools/sitin_scenario_classes.py --check
    .venv/bin/python tools/sitin_scenario_classes.py --emit DIR
    .venv/bin/python tools/sitin_scenario_classes.py --coverage --input TRIGGER.jsonl --out DIR

`--check` 把**每条官方依据对到指南行**（行号越界或该行不含标记即非零退出）、
把**每个谓词对到源码符号**（类改名或字段改名即失败），并**现算**结算表核对支付角色组合。
`--coverage` 逐类出账（四态 + 逐候选触发/改选 + 类外零增量核对）。

## 修订（2026-09-16，3.6b 包）：三个门控类由「不可判定」改为「已接线 ⇒ 有谓词」

起因：3.6d（corpus 包）把 `you_cai_bi_kao` / `remaining_tile_count` / `catch_play_owner_seat`
接进了评分上下文，于是旧的 `undecidable_but_wired` 断言（"标了不可判定，字段却已在上下文里"）
**正确地**开始报红。修正落在本清单内：

- 三个门控类不再带 `undecidable`，改为**可判定谓词**（见 `GATE_FACT_WIRING` 接线契约表）；
- 新增 `rule_enforcement`：规则层强制点的源码符号（原来挂在 `undecidable` 里，不丢信息）；
- `check_undecidable()` → `check_gate_wiring()`：断言极性**反转**——字段必须**真的在**
  `EvaluationContext` 里；未接线即 `gate_wiring_missing` 且非零退出（跨包时序依赖，属预期红）；
- 产物新增 `gate_wiring` 段：读的人据此知道门控类为什么是 `unknown`，
  而不是把它读成"机制稀有"或"工具坏了"。

**不得**为了让 `--check` 变绿而回退接线，也不得把这三类重新标成不可判定：
接线未落地时谓词返回 None（**未知不填零**）是**运行时事实缺失**的自描述，
与"把缺失写成规则性质"是两件事。

## 边界（必须与产物一起引用）

1. 触发集是**构造集**：只证明接线与提供可触发作用面；**不得**用于效应估计、排序、
   淘汰或晋级声明；**不得**据此放开准入。
2. 本工具**不跑桌赛**、不做效果结论、不产出任何"分量有效性"判断。
3. `declared` 是**静态弱声明**（`spec.scope` ∩ 类的判定位点 ≠ ∅ **且** 候选源码含该类的
   事实记号），不是语义证明；矩阵把命中的记号一并落盘供人复核。
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
import dataclasses
import hashlib
import importlib
import importlib.util
import json
import sys
from pathlib import Path
from typing import (Any, Callable, Dict, Iterable, Iterator, List, Mapping, Optional,
                    Sequence, Tuple)

REPO = _PROJECT_ROOT
sys.path.insert(0, str(_project_file(_PROJECT_ROOT, REPO / "src")))
_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))

from hangma_bot.application.deadline import ManualClock  # noqa: E402
from hangma_bot.bootstrap import build_decision_codec  # noqa: E402
# 末局禁杠的规则层门限：**直接复用规则模块的常量**（不抄数字；--check 会解析同一符号）。
from hangma_bot.hangma.action_families import WALL_RESERVE_TILES  # noqa: E402
from hangma_bot.hangma.engine import HangmaRules  # noqa: E402
from hangma_bot.hangma.interface import RuleCompleteness  # noqa: E402
from hangma_bot.kernel.actions import Discard, Pass  # noqa: E402
from hangma_bot.kernel.config import RuleConfig  # noqa: E402
from hangma_bot.offline.evaluate import translate_budget  # noqa: E402
from hangma_bot.policy.evaluation_v1 import EvaluationContext, build_context  # noqa: E402
from hangma_bot.policy.heuristic_v2 import ComparableHeuristicPolicyV2  # noqa: E402
from hangma_bot.policy.heuristics.four_component_path_value import (  # noqa: E402
    four_white_state,
    known_piao,
    locked_luxury_groups,
    meld_count_of,
)
from hangma_bot.policy.heuristics.meld_opportunity_cost import (  # noqa: E402
    natural_draw_value,
)
from hangma_bot.policy.interface import DecisionRequest  # noqa: E402

SCHEMA = "sitin-scenario-classes/1"
COVERAGE_SCHEMA = "sitin-scenario-classes-coverage/1"

#: 官方指南快照（v34，2026-09-14 抓取）。所有官方依据都必须对到本文件的**行号**。
GUIDE = "doc/references/official-guide-v34-content.txt"

#: 覆盖账面板参数。**评分上下文看不到它**（见 `gate.you_cai_bi_kao`）。
PANEL_RULESET = "v26"
PANEL_BASE_SCORE = 1
PANEL_YOU_CAI_BI_KAO = False

#: 类覆盖下限。与门禁的 `G2_MIN_FIRED_WINDOWS` **同值同义**（同一份证据下限口径）；
#: `--check` 会现读 `sitin_gates.G2_MIN_FIRED_WINDOWS` 核对，防两处漂移。
MIN_CLASS_WINDOWS = 8

#: 动作族词汇表（判定位点只能取这些值）。
ACTION_FAMILIES: Tuple[str, ...] = ("chi", "peng", "gang", "discard", "pass", "hu")

#: 证据分级（根 AGENTS.md §3）。工程推理不得写成规则事实。
LEVEL_OFFICIAL = "【官方已确认】"
LEVEL_IMPL = "【当前观察·实现】"
LEVEL_DERIVED = "【推导·未一手核实】"
LEVEL_ASSUMPTION = "【待确认假设·工程】"

#: 关系种类：mutex（互斥）/ implies（蕴含）/ overlay（可同时成立且同一位点上叠加计分）。
RELATION_KINDS: Tuple[str, ...] = ("mutex", "implies", "overlay")

#: 类种类；语义见模块 docstring 的四类分离表。
CLASS_KINDS: Tuple[str, ...] = (
    "rule_scenario", "evidence_state", "settlement_outcome", "official_bound",
)

#: 覆盖四态（本文件唯一允许的 verdict 取值）。
VERDICTS: Tuple[str, ...] = (
    "sufficient", "insufficient", "not_applicable", "unknown",
)

#: 符号常量（--check 逐条解析）。
SYM_CONTEXT = "hangma_bot.policy.evaluation_v1:EvaluationContext"
SYM_FACTS = "hangma_bot.hangma.interface:CandidateFacts"
SYM_OBS = "hangma_bot.kernel.observation:PlayerObservation"
SYM_RULE_STATE = "hangma_bot.kernel.observation:RulePublicState"
SYM_FOUR_WHITE = "hangma_bot.hangma.special_rules:four_white_indicator"
SYM_PIAO = "hangma_bot.hangma.special_rules:is_piao_discard"
SYM_CATCH = "hangma_bot.hangma.special_rules:catch_play_restriction"
SYM_CHAIN_ACTION = "hangma_bot.hangma.progression:chain_after_action"
SYM_BAOTOU_ACTION = "hangma_bot.hangma.progression:baotou_after_action"
SYM_CHAIN_DETAIL = "hangma_bot.hangma.settlement:_chain_detail"
SYM_FAN = "hangma_bot.hangma.settlement:compute_fan"
SYM_SETTLE = "hangma_bot.hangma.settlement:settle_scores"
SYM_CHI_FAMILY = "hangma_bot.hangma.action_families:chi_candidates"
SYM_GANG_FAMILY = "hangma_bot.hangma.action_families:gang_candidates"
SYM_WALL_GANG = "hangma_bot.hangma.action_families:_wall_allows_gang"
SYM_ENGINE = "hangma_bot.hangma.engine:HangmaRules"
SYM_CONFIG = "hangma_bot.kernel.config:RuleConfig"
SYM_RISK_CELLS = "hangma_bot.policy.hu_upgrade_calibration:RISK_CELLS"
SYM_MELD_NATURAL = "hangma_bot.policy.heuristics.meld_opportunity_cost:natural_draw_value"
SYM_MELD_COUNT = "hangma_bot.policy.heuristics.four_component_path_value:meld_count_of"
SYM_KNOWN_PIAO = "hangma_bot.policy.heuristics.four_component_path_value:known_piao"
SYM_LUXURY = "hangma_bot.policy.heuristics.four_component_path_value:locked_luxury_groups"
SYM_WEIGHTS_V1 = "hangma_bot.policy.weights_v1:HeuristicWeightsV1"
SYM_HU_UPGRADE = "hangma_bot.policy.hu_upgrade:UpgradeRiskCell"
SYM_RECOMPUTE = "sitin_m4_recompute:_first_key"
SYM_GATES_MIN = "sitin_gates:G2_MIN_FIRED_WINDOWS"
SYM_GATES_TRIGGER = "sitin_gates:looks_like_trigger_set"

#: 与门禁共用的**口径锚点**（--check 逐条解析，防止两处对同一件事各写一份）。
SYM_SHARED_ANCHORS: Tuple[Tuple[str, str], ...] = (
    (SYM_GATES_MIN, "类覆盖下限与门禁触发面下限同值"),
    (SYM_GATES_TRIGGER, "构造触发集的识别与门禁同一实现"),
    (SYM_RECOMPUTE, "首选动作口径与重算驱动同一实现"),
)


def _basis(line: int, marker: str, note: str) -> Dict[str, Any]:
    """一条官方依据：指南**行号** + 该行**必须出现的标记**（--check 逐条核对）。"""

    return {"file": GUIDE, "line": line, "marker": marker, "note": note}


def _field(symbol: str, field: str, note: str = "") -> Dict[str, Any]:
    """一个可判定谓词字段：源码符号 + 字段名（--check 解析并断言字段存在）。"""

    return {"symbol": symbol, "field": field, "note": note}


def _src(symbol: str, note: str) -> Dict[str, Any]:
    """一条实现侧依据：源码符号 + 说明（--check 解析）。"""

    return {"symbol": symbol, "note": note}


def _rel(target: str, kind: str, note: str) -> Dict[str, Any]:
    return {"target": target, "kind": kind, "note": note}


# ---------------------------------------------------------------------------
# 1.5 门控事实的**接线契约**（3.6b 修订，2026-09-16）
#
# 三个门控类（有财必拷响 / 末局禁杠 / 抓打圈主）起初标为"评分上下文不可判定"：
# 当时 `EvaluationContext` 不带 `you_cai_bi_kao` / `remaining_tile_count` /
# `catch_play_owner_seat`。**3.6d（corpus 包）把这三个事实接进了评分上下文**，
# 于是本清单的判定极性**反向**：
#
#   旧：标 `undecidable`，并断言字段**不在**上下文里；
#   新：不给 `undecidable`，给出可判定谓词，并断言字段**确实在**上下文里
#       （`check_gate_wiring()`；未接线即 `gate_wiring_missing`，非零退出）。
#
# **允不允许为了 --check 变绿而回退接线？不允许**：那会把"事实可读"重新变成"猜"。
# 接线未落地时谓词一律返回 None（**未知不填零**），面板上这三类因此仍是 `unknown`——
# 这与"把它们重新标成不可判定"是两件不同的事：前者是**运行时事实缺失**的自描述，
# 后者是把缺失写成规则性质。接线落地后 `--check` 自动转绿，无需再改本文件。
# ---------------------------------------------------------------------------

#: 门控类的接线契约：类 id → 评分上下文字段。**接线状态只有这一处口径**
#: （谓词读取点、`--check` 断言对象、缺口清单 `required_fact` 判据共用）。
GATE_FACT_WIRING: Mapping[str, Dict[str, Any]] = {
    "gate.you_cai_bi_kao": {
        "field": "you_cai_bi_kao",
        "symbol": SYM_CONTEXT,
        "kind": "bool",
        "note": "有财必拷响开关；打开 ⇒ 胡牌成为爆头的必要条件（该类成立 = 开关打开）",
        "wired_by": "3.6d（corpus 包）",
    },
    "gate.wall_end_gang_ban": {
        "field": "remaining_tile_count",
        "symbol": SYM_CONTEXT,
        "kind": "Optional[int]",
        "note": "含保留区的剩余牌墙张数；<= WALL_RESERVE_TILES 时禁杠生效",
        "wired_by": "3.6d（corpus 包）",
    },
    "gate.catch_play_owner": {
        "field": "catch_play_owner_seat",
        "symbol": SYM_CONTEXT,
        "kind": "Optional[int]",
        "note": "抓打圈主席位；== my_seat ⇒ 本人是圈主（不受吃碰限制）",
        "wired_by": "3.6d（corpus 包）",
    },
}

#: 末局禁杠门限的源码符号（`WALL_RESERVE_TILES` 由顶部 import 复用规则模块，值不在本文件里写死）。
SYM_WALL_RESERVE = "hangma_bot.hangma.action_families:WALL_RESERVE_TILES"


def _gate_field(class_id: str, note: str = "") -> Dict[str, Any]:
    """门控事实的 `fields` 条目：**字段名从接线契约表现取**，不复制字符串。"""

    entry = GATE_FACT_WIRING[class_id]
    return _field(entry["symbol"], entry["field"], note or entry["note"])


_CONTEXT_FIELDS: Optional[frozenset] = None


def context_field_names() -> frozenset:
    """评分上下文（`EvaluationContext`）**当前**声明的字段名集合。

    跨包接线状态的唯一运行时读取点：字段在 ⇒ 该门控类可判定；不在 ⇒ 谓词返回 None
    （未知不填零），并由 `check_gate_wiring()` 报 `gate_wiring_missing`（预期红）。
    """

    global _CONTEXT_FIELDS
    if _CONTEXT_FIELDS is None:
        _CONTEXT_FIELDS = frozenset(field.name for field in dataclasses.fields(EvaluationContext))
    return _CONTEXT_FIELDS


#: 事实字段未接线时的哨兵（与"字段存在但值为 None"**必须分开**：后者是未知，前者是缺接线）。
_MISSING = object()


def _gate_fact(class_id: str, ctx: Any) -> Any:
    """读一个门控事实：字段未接线返回哨兵，字段存在但为 None 返回 None。"""

    entry = GATE_FACT_WIRING[class_id]
    if entry["field"] not in context_field_names():
        return _MISSING
    return getattr(ctx, entry["field"], _MISSING)

# ---------------------------------------------------------------------------
# 1. 评分分量（价值分量）清单：每个分量在**哪些场景类**上取值
#
# **权重纪律（用户 2026-09-16 裁定）**：不得按场景类拍权重。规则给的是"番 → 分"的
# 兑换率（×2 番 = ×2 分；log2 下相加，四个分量共用同一尺度 40 分/log2 番是对的）；
# 规则**没给**的是 ①兑现概率 ②得失比（庄 24 / 闲 10、付 8 / 付 1）。
# 因此本清单**没有** "每类一个权重" 字段，只有"分量 → 类"的绑定与量纲说明。
# ---------------------------------------------------------------------------

COMPONENTS: Tuple[Dict[str, Any], ...] = (
    {
        "id": "branch",
        "name": "分支因子",
        "level": LEVEL_OFFICIAL,
        "unit": "log2 番（平胡 0 / 七对 1 / 豪华 N 组 1+N，N=0—3）",
        "official": (_basis(29, "总番 = 1 × 分支因子", "总番公式的第一个乘子"),
                     _basis(33, "平胡", "平胡 ×1 ⇒ log2 0"),
                     _basis(35, "7 对胡牌", "七对 ×2 ⇒ log2 1"),
                     _basis(37, "豪华七对", "豪华 1/2/3 组 ×4/×8/×16 ⇒ log2 2/3/4")),
        "source": (_src(SYM_FAN, "分支与豪华组数的唯一计算点"),),
        "classes": (
            "branch.chiitoi_live", "branch.luxury_locked", "branch.closer_seven_pairs",
            "overlay.chiitoi_baotou", "overlay.global_max",
        ),
        "note": "分量只依赖状态（暗牌形态与副露数），不按动作标签给分。",
    },
    {
        "id": "chain",
        "name": "动作链次数",
        "level": LEVEL_OFFICIAL,
        "unit": "log2 番（每飘/杠动作 +1；对应总番 ×2）",
        "official": (_basis(29, "2^动作链次数", "总番公式的第二个乘子"),
                     _basis(57, "打出非飘非杠的牌", "链的定义与断链条件"),
                     _basis(47, "爆头状态打出财神继续听任意牌胡", "飘的动作定义")),
        "source": (_src(SYM_CHAIN_ACTION, "任意动作后的链状态（单一规则来源）"),
                   _src(SYM_CHAIN_DETAIL, "链明细命名：杠开 / 财飘 / 杠飘链")),
        "classes": (
            "chain.open", "chain.gang_step", "chain.gang_draw_open", "chain.piao_discard",
            "chain.break_discard", "chain.claim_repiao_circle", "overlay.gang_piao_mix",
            "overlay.plain_branch_max", "overlay.global_max",
        ),
        "note": "吃碰**不改链**（官方明文允许圈内吃碰后再打财神续飘），因此不能用动作标签加减分。",
    },
    {
        "id": "four_white",
        "name": "4 个白板",
        "level": LEVEL_OFFICIAL,
        "unit": "log2 番（等值指示成立 ⇒ +1，对应总番 ×2）",
        "official": (_basis(53, "正好 4 张", "手留白 + 链内飘出 == 4 的等值条件"),
                     _basis(106, "手留白 + piao ≤ 4", "fan-calc 的字段约束（白板共 4 张）")),
        "source": (_src(SYM_FOUR_WHITE, "等值条件的单一规则来源"),
                   _src(SYM_KNOWN_PIAO, "链内飘出的可判定性（未知不填零）")),
        "classes": (
            "four_white.at_four", "four_white.derivable_held4", "four_white.unknown_piao",
            "overlay.four_white_baotou", "overlay.plain_branch_max", "overlay.global_max",
        ),
        "note": "**等值条件，不是单调量**：留 2 张不算、留 4 张算、留 3 张 + 飘 1 张也算。",
    },
    {
        "id": "baotou",
        "name": "爆头",
        "level": LEVEL_OFFICIAL,
        "unit": "log2 番（爆头 ⇒ +1，对应总番 ×2）",
        "official": (_basis(23, "正好 4 张白板亦按此判定", "任意听判定与四白叠加"),
                     _basis(55, "见 1.2 判定", "爆头 ×2（最后统一加）"),
                     _basis(61, "七客", "七对也可以爆头（七客 / 豪华七客）")),
        "source": (_src(SYM_BAOTOU_ACTION, "确定性动作后的爆头（弃牌重判；吃碰杠继承）"),),
        "classes": (
            "baotou.active", "baotou.discard_recheck", "baotou.meld_inherit",
            "baotou.decline_win_for_piao", "overlay.four_white_baotou", "overlay.chiitoi_baotou",
        ),
        "note": "爆头同时是飘的前置条件：非爆头态打白板不是飘，而是断链。",
    },
    {
        "id": "pay_multiplier",
        "name": "庄闲 / 支付倍率",
        "level": LEVEL_OFFICIAL,
        "unit": "得分倍率（庄家侧 ×8、闲家对闲家 ×1；兑现代理常数：本人庄 +24、本人闲 +10）",
        "official": (_basis(69, "得分 = 底分", "计分公式：底分 × 番型倍率 ×（庄 ×8 / 闲 ×1）"),
                     _basis(71, "庄家胡：三家闲家各付", "庄家胡：三家各付 ×8"),
                     _basis(73, "闲家胡：庄家付", "闲家胡：庄家付 ×8、另两闲家各付 ×1")),
        "source": (_src(SYM_SETTLE, "四家结算的唯一实现（系数由本函数现算核对）"),),
        "classes": ("payrole.self_dealer", "payrole.self_nondealer"),
        "note": ("**这是一等场景维度，不是番型分量**：对「本人所有胡牌结果」它是同一个常数"
                 "（24 或 10），所以**不改变同一手内的番型排序**；它改变的是**得失比**"
                 "⇒ 攻防取舍（庄家放任别人胡的代价是闲家的 8 倍）。"
                 "**不得把它当成一个番型分量混进 log2 番里。**"),
    },
    {
        "id": "waiting_progress",
        "name": "牌效（向听 + 有效牌剩余估计）",
        "level": LEVEL_IMPL,
        "unit": "评分点（shanten_step=100 / effective_tile=1.0，见 HeuristicWeightsV1）",
        "official": (),
        "source": (_src(SYM_WEIGHTS_V1, "V1/V2 基线权重的唯一来源（11 项，**无庄闲**）"),),
        "classes": ("meld.claim_window", "meld.waiting_facts_available",
                    "baotou.decline_win_for_piao"),
        "note": "这是现行基线评分器的实际分量（不是官方番型分量）；本清单只登记它所绑定的场景类。",
    },
    {
        "id": "meld_opportunity",
        "name": "鸣牌机会成本",
        "level": LEVEL_ASSUMPTION,
        "unit": "评分点（β 表示把鸣牌-vs-Pass 的有效牌系数抬高多少）",
        "official": (_basis(15, "吃最多 2 摊", "鸣牌窗口的官方结构（碰/明杠窗口先于吃窗口）"),),
        "source": (_src(SYM_MELD_NATURAL, "等待有效牌剩余估计（机制输入的唯一来源）"),),
        "classes": ("meld.claim_window", "meld.waiting_facts_available"),
        "note": "与 V2 既有项共线，是有界重加权，不是新增事实维度；机制属工程假设。",
    },
    {
        "id": "meld_waiting_conditional",
        "name": "鸣牌等待条件校准",
        "level": LEVEL_ASSUMPTION,
        "unit": "评分点（以参考等待牌效为中心的双向调整）",
        "official": (_basis(15, "吃最多 2 摊", "同上：鸣牌窗口的官方结构"),),
        "source": (_src(SYM_MELD_NATURAL, "与机会成本共用同一等待事实来源"),),
        "classes": ("meld.claim_window", "meld.waiting_facts_available"),
        "note": "补 P-3 缺口（允许正负调整，同一批窗口上可产生两个方向的改选）。",
    },
    {
        "id": "reachability_gate",
        "name": "可达性门控（**不是价值分量**）",
        "level": LEVEL_OFFICIAL,
        "unit": "无（门控量：决定别的分量是否可达，不直接给分）",
        "official": (_basis(13, "最后 10 墩之内禁止杠牌", "末局禁杠：杠位点在动作空间上消失"),
                     _basis(152, "有财必拷响", "开关决定胡是否可达，从而决定弃胡续飘位点"),
                     _basis(7, "打财神者本人不受此限", "抓打圈决定吃碰位点是否可达")),
        "source": (_src(SYM_WALL_GANG, "末局禁杠的规则实现"),
                   _src(SYM_ENGINE, "有财必拷响在规则层过滤 hu 候选"),
                   _src(SYM_CATCH, "抓打圈按圈主限制动作")),
        "classes": ("gate.you_cai_bi_kao", "gate.wall_end_gang_ban", "gate.catch_play_owner"),
        "note": ("登记它是为了让**每个场景类都有明确的分量归属**（或明确的不归属）："
                 "门控在规则层已生效，但评分上下文看不到 ⇒ 三类的覆盖必须是 unknown 而不是 zero。"),
    },
)

#: 权重纪律的**机读**声明；--check 断言清单里不存在"每类一个权重"的字段。
WEIGHT_POLICY: Dict[str, Any] = {
    "rule_provides": "番 → 分的兑换率（×2 番 = ×2 分；log2 下四个加数同尺度）",
    "rule_does_not_provide": (
        "①兑现概率（路径存活不等于兑现）②得失比（庄 24 / 闲 10、付 8 / 付 1）"),
    "verdict": "不得按场景类拍权重；类只用于判定机制是否按声明起作用",
    "forbidden_fields": ("weight", "weights", "权重", "score", "score_share"),
}

#: 支付角色组合：{本人庄, 本人闲} × {胡家=本人 / 胡家=庄 / 胡家=闲} 的**完整交叉**。
#: coefficient 是「本人净增量 / (底分 × 番)」的系数；--check 用 settlement.settle_scores
#: **现算**核对（不抄数字）。窗口侧只能判本人庄/闲，胡家是谁是未来事件。
PAY_ROLE_COMBOS: Tuple[Dict[str, Any], ...] = (
    {"id": "pay.self_dealer.winner_self", "self_role": "dealer", "winner_role": "self",
     "class_id": "payrole.self_dealer", "coefficient": 24.0,
     "meaning": "本人坐庄且本人胡：三家闲家各付 底分×番×8 ⇒ 本人 +24×番×底分",
     "basis_line": 71},
    {"id": "pay.self_dealer.winner_dealer", "self_role": "dealer", "winner_role": "dealer",
     "class_id": "payrole.self_dealer", "coefficient": 24.0,
     "meaning": "本人即庄家，此格与 winner_self 是同一支付事实（交叉表的折叠项）",
     "basis_line": 71},
    {"id": "pay.self_dealer.winner_other_nondealer", "self_role": "dealer",
     "winner_role": "other_nondealer", "class_id": "payrole.self_dealer",
     "coefficient": -8.0,
     "meaning": "本人坐庄、他人自摸胡：本人付 底分×番×8（两家共 −16×番×底分）",
     "basis_line": 71},
    {"id": "pay.self_nondealer.winner_self", "self_role": "nondealer", "winner_role": "self",
     "class_id": "payrole.self_nondealer", "coefficient": 10.0,
     "meaning": "本人闲家且本人胡：庄家付 ×8、另两闲家各付 ×1 ⇒ 本人 +10×番×底分",
     "basis_line": 73},
    {"id": "pay.self_nondealer.winner_dealer", "self_role": "nondealer",
     "winner_role": "dealer", "class_id": "payrole.self_nondealer", "coefficient": -8.0,
     "meaning": "本人闲家、庄家自摸胡：本人付 底分×番×8", "basis_line": 73},
    {"id": "pay.self_nondealer.winner_other_nondealer", "self_role": "nondealer",
     "winner_role": "other_nondealer", "class_id": "payrole.self_nondealer",
     "coefficient": -1.0,
     "meaning": "本人闲家、另一闲家自摸胡：本人付 底分×番×1（庄家付 8）", "basis_line": 73},
)

# ---------------------------------------------------------------------------
# 2. 场景类清单（id 冻结后为他包引用口径）
#
# 每条：官方依据（指南行 + 该行标记）、实现依据（源码符号）、可判定谓词（字段）、
# 判定位点（动作族）、关系（互斥 / 蕴含 / 叠加）、该类对评分的作用（只描述机制）。
# predicate_scope=state 表示谓词只看窗口状态；state+sites 表示还要求"位点存在"。
# ---------------------------------------------------------------------------

CLASSES: Tuple[Dict[str, Any], ...] = (
    # ---- 分支因子 --------------------------------------------------------
    {
        "id": "branch.chiitoi_live",
        "name": "七对路径存活（本人无副露）",
        "kind": "rule_scenario",
        "level": LEVEL_OFFICIAL,
        "official": (_basis(21, "禁止吃碰明杠暗杠", "七对子禁止任何副露 ⇒ 副露永久关闭该路径"),
                     _basis(35, "7 对胡牌", "七对 ×2 ⇒ log2 1（分支因子的取值之一）")),
        "source": (_src(SYM_MELD_COUNT, "由暗牌张数反推副露数（形态不合法即 None，不猜）"),),
        "predicate_text": "meld_count_of(combined_codes) == 0（本人无副露 ⇒ 七对路径仍可能）",
        "predicate_scope": "state",
        "fields": (_field(SYM_CONTEXT, "combined_codes", "本人暗牌（含刚摸牌），用于反推副露数"),),
        "fact_tokens": ("seven_pairs_shanten_after", "seven_pairs_useful_tiles", "meld_count_of"),
        "sites": ("chi", "peng", "gang"),
        "relations": (),
        "complement": "暗牌张数形态不可判时谓词返回 None（未知，不得当作「已关闭」）",
        "scoring_effect": "分支分量在该类上取七对侧的 log2 价值（1 + 已锁定豪华组数）；任何副露把它一次性归零。",
        "undecidable": None,
    },
    {
        "id": "branch.luxury_locked",
        "name": "已锁定豪华组（暗牌含恰好 4 张自然牌码）",
        "kind": "rule_scenario",
        "level": LEVEL_OFFICIAL,
        "official": (_basis(37, "豪华七对", "豪华七对 ×4（1 组四张）"),
                     _basis(39, "双豪华七对", "双豪华 ×8（2 组四张）"),
                     _basis(41, "三豪华七对", "三豪华 ×16（3 组四张）")),
        "source": (_src(SYM_LUXURY, "豪华组数的确定性代理（只少算不多算）"),),
        "predicate_text": "meld_count_of(...) == 0 且 locked_luxury_groups(combined_codes, wealth_code) >= 1",
        "predicate_scope": "state",
        "fields": (_field(SYM_CONTEXT, "combined_codes", "暗牌计数来源"),
                   _field(SYM_CONTEXT, "wealth_code", "财神牌码；财神不计入豪华组")),
        "fact_tokens": ("locked_luxury_groups", "WEALTH_TOTAL"),
        "sites": ("discard",),
        "relations": (_rel("branch.chiitoi_live", "implies", "豪华组只在七对路径存活时有分支意义"),),
        "complement": "官方还有一条「4 张真白板算 1 组」的结算条件，依赖成胡时才可判定的信息，本类不猜。",
        "scoring_effect": "把分支分量的上界从 1 抬到 1+N（N=1—3）；打掉该牌码使其归零。",
        "undecidable": None,
    },
    {
        "id": "branch.closer_seven_pairs",
        "name": "七对是更近路径",
        "kind": "rule_scenario",
        "level": LEVEL_IMPL,
        "official": (_basis(35, "7 对胡牌", "七对与平胡是两条不同分支（×2 与 ×1）"),
                     _basis(61, "七客", "七对同样可以叠爆头 ⇒ 路径选择有实际价值")),
        "source": (_src(SYM_FACTS, "动作后两型向听（standard/seven_pairs）"),
                   _src(SYM_RECOMPUTE, "动作前参考口径：过牌候选代表手牌不变的状态"),),
        "predicate_text": ("窗口内存在带完整事实的 pass 候选（代表动作前状态）且 "
                           "seven_pairs_shanten_after < standard_shanten_after；无参考 ⇒ None"),
        "predicate_scope": "state",
        "fields": (_field(SYM_FACTS, "seven_pairs_shanten_after", "七对向听"),
                   _field(SYM_FACTS, "standard_shanten_after", "普通型向听")),
        "fact_tokens": ("standard_shanten_after", "seven_pairs_shanten_after", "closer_bonus"),
        "sites": ("discard", "chi", "peng", "gang"),
        "relations": (_rel("branch.chiitoi_live", "implies", "无副露是该类成立的必要条件"),),
        "complement": "纯弃牌窗口没有手牌不变的参考候选 ⇒ 本类在该窗口不可判定（返回 None，不填 False）。",
        "scoring_effect": "决定分支分量在「七对更近」时的额外权重（closer_bonus 类参数），是路径取舍位点。",
        "undecidable": None,
    },
    # ---- 动作链 ----------------------------------------------------------
    {
        "id": "chain.open",
        "name": "链已开启（本人链次数 >= 1）",
        "kind": "rule_scenario",
        "level": LEVEL_OFFICIAL,
        "official": (_basis(29, "2^动作链次数", "链次数是总番指数上的加数"),
                     _basis(57, "打出非飘非杠的牌", "非飘非杠的弃牌断链清零")),
        "source": (_src(SYM_CONTEXT, "窗口状态 chain_count（官方 god.chain_count）"),),
        "predicate_text": "ctx.chain_count >= 1",
        "predicate_scope": "state",
        "fields": (_field(SYM_CONTEXT, "chain_count", "本人飘/杠动作链次数，非负"),),
        "fact_tokens": ("chain_count",),
        "sites": ("discard", "gang"),
        "relations": (),
        "complement": "链次数为 0 时断链位点不存在（弃牌不会扣掉任何已积累的番）。",
        "scoring_effect": "链分量在该类上存在负向位点（断链）与正向位点（续飘/杠）。",
        "undecidable": None,
    },
    {
        "id": "chain.gang_step",
        "name": "杠推进链（窗口存在杠候选）",
        "kind": "rule_scenario",
        "level": LEVEL_OFFICIAL,
        "official": (_basis(57, "每个飘/杠动作 ×2", "杠每个动作使链 +1"),
                     _basis(43, "杠开", "杠后补牌自摸 = 链 1 动作 ×2")),
        "source": (_src(SYM_CHAIN_ACTION, "杠后的链转移（rule_transition）"),),
        "predicate_text": "窗口内存在 gang 候选（含暗杠/明杠/补杠）",
        "predicate_scope": "state+sites",
        "fields": (),
        "fact_tokens": ("chain_after_gang", "chain_after_action", "Gang"),
        "sites": ("gang",),
        "relations": (_rel("gate.wall_end_gang_ban", "mutex",
                           "末局禁杠期内规则层不产出杠候选 ⇒ 该位点不存在"),),
        "complement": ("末局禁杠（指南第 13 行）由规则层直接不产出杠候选 ⇒ 该位点在动作空间上消失，"
                       "但评分器无法判定自己处于哪一类（见 gate.wall_end_gang_ban）。"),
        "scoring_effect": "链分量在该位点上 +scale；杠同时是唯一能无条件推进链的动作族。",
        "undecidable": None,
    },
    {
        "id": "chain.gang_draw_open",
        "name": "杠前已听（杠开位点）",
        "kind": "rule_scenario",
        "level": LEVEL_OFFICIAL,
        "official": (_basis(43, "杠后补的那张牌直接自摸胡", "杠开 = 链 1 动作 ×2"),
                     _basis(45, "杠爆", "爆头状态下杠补牌胡 = 爆头 × 杠开 ×4")),
        "source": (_src(SYM_FACTS, "杠候选的动作后事实（replacement_draw_unknown=True）"),),
        "predicate_text": ("存在事实完整且 shanten_after == 0 的杠候选（补牌前余牌口径）；"
                           "杠候选存在但事实不完整 ⇒ None"),
        "predicate_scope": "state+sites",
        "fields": (_field(SYM_FACTS, "shanten_after", "动作后向听；杠为补牌前口径"),
                   _field(SYM_FACTS, "replacement_draw_unknown", "杠补牌未知标记")),
        "fact_tokens": ("replacement_draw_unknown", "shanten_after"),
        "sites": ("gang",),
        "relations": (_rel("chain.gang_step", "overlay", "同一个杠位点同时是链推进位点与杠开位点"),),
        "complement": "补牌本身的值未知（待随机事件），本类只判「杠前是否已听」，不假设补到哪张。",
        "scoring_effect": "链分量与兑现概率在这里交叉：链 +1 是确定的，补牌是否成胡不是。",
        "undecidable": None,
    },
    {
        "id": "chain.piao_discard",
        "name": "飘（爆头态打出财神）",
        "kind": "rule_scenario",
        "level": LEVEL_OFFICIAL,
        "official": (_basis(47, "爆头状态打出财神继续听任意牌胡", "财飘 = 爆头 × 飘 1 动作"),
                     _basis(57, "含非爆头态打白板", "非爆头态打白板不是飘，是断链"),
                     _basis(59, "弃胡打白飘", "爆头摸到白板：可胡，也可弃胡打白博财飘")),
        "source": (_src(SYM_PIAO, "飘的判定（爆头 ∧ 财神）——单一规则来源"),),
        "predicate_text": "ctx.baotou 为真 且 窗口存在「打出财神」的 discard 候选",
        "predicate_scope": "state+sites",
        "fields": (_field(SYM_CONTEXT, "baotou", "本人是否爆头（飘的前置条件）"),
                   _field(SYM_CONTEXT, "wealth_code", "财神牌码（本项目为白板）")),
        "fact_tokens": ("baotou", "wealth_code"),
        "sites": ("discard",),
        "relations": (_rel("baotou.active", "overlay", "飘以爆头为前提，两个类在同一位点上叠加计分"),),
        "complement": "非爆头态打财神属于 chain.break_discard（断链），不是本类。",
        "scoring_effect": "链分量 +1 且链内飘出 +1；后者同时影响四白等值条件。",
        "undecidable": None,
    },
    {
        "id": "chain.break_discard",
        "name": "断链位点（链非零时打出非飘非杠的牌）",
        "kind": "rule_scenario",
        "level": LEVEL_OFFICIAL,
        "official": (_basis(57, "链断重新计数", "打出非飘非杠的牌 ⇒ 链断清零"),
                     _basis(29, "2^动作链次数", "断链等价于把指数加数清零")),
        "source": (_src(SYM_CHAIN_ACTION, "断链结局把链与链内飘出两项归零"),),
        "predicate_text": "ctx.chain_count >= 1 且窗口存在「非飘」的 discard 候选",
        "predicate_scope": "state+sites",
        "fields": (_field(SYM_CONTEXT, "chain_count", "链次数"),),
        "fact_tokens": ("chain_after_action", "chain_after_discard", "baotou"),
        "sites": ("discard",),
        "relations": (_rel("chain.open", "implies", "链为 0 时不存在断链位点"),),
        "complement": "同类位点也覆盖「非爆头态打白板」（规则上等同普通弃牌）。",
        "scoring_effect": "链分量在该位点上取负值；同时把链内飘出归零，可能连带打掉四白条件。",
        "undecidable": None,
    },
    {
        "id": "chain.claim_repiao_circle",
        "name": "抓打圈内吃碰后再打财神（财飘链 +1 位点）",
        "kind": "rule_scenario",
        "level": LEVEL_OFFICIAL,
        "official": (_basis(7, "财飘链 +1", "圈内吃碰后再打财神 = 财飘链 +1；圈以本人为新打财神者重启"),
                     _basis(5, "白板 = 财神", "财神可主动打出；打出即开圈")),
        "source": (_src(SYM_CATCH, "抓打圈内其余玩家的动作限制（圈主不受限）"),),
        "predicate_text": ("ctx.catch_play 为真 且 窗口存在 chi 或 peng 候选 且 存在打出财神的 discard 候选 "
                           "且 ctx.baotou 为真（财飘的定义要求爆头）"),
        "predicate_scope": "state+sites",
        "fields": (_field(SYM_CONTEXT, "catch_play", "本人是否处于抓打圈"),
                   _field(SYM_CONTEXT, "baotou", "财飘要求爆头")),
        "fact_tokens": ("catch_play",),
        "sites": ("chi", "peng", "discard"),
        "relations": (_rel("chain.piao_discard", "implies", "在位点侧本类包含飘的全部条件"),
                      _rel("baotou.active", "implies", "财飘定义要求爆头")),
        "complement": ("圈主身份（catch_play_owner_seat）**未接入评分上下文**，因此本类只能用"
                       "「圈内出现吃碰候选」间接推断本人是圈主（规则层已按圈主限制过滤候选）。"
                       "该推断属推导，见 unresolved。"),
        "scoring_effect": "吃碰本身不改链，但让「随后打财神」成为链 +1 的位点；按动作标签扣吃碰分是错的。",
        "undecidable": None,
    },
    # ---- 四白 ------------------------------------------------------------
    {
        "id": "four_white.at_four",
        "name": "四白等值条件成立（手留白 + 链内飘出 == 4）",
        "kind": "rule_scenario",
        "level": LEVEL_OFFICIAL,
        "official": (_basis(53, "正好 4 张", "手牌留存 + 链内飘出 = 4（普通打出的、杠出的不算）"),
                     _basis(106, "手留白 + piao ≤ 4", "白板共 4 张的字段约束")),
        "source": (_src(SYM_FOUR_WHITE, "等值条件的单一规则来源"),),
        "predicate_text": "four_white_indicator(wealth_count, known_piao(...)) is True；任一输入未知 ⇒ None",
        "predicate_scope": "state",
        "fields": (_field(SYM_CONTEXT, "wealth_count", "动作前手留财神张数"),
                   _field(SYM_CONTEXT, "chain_piao", "链内飘出白板数；为空表示依据不足")),
        "fact_tokens": ("four_white_indicator", "four_white_state", "wealth_count"),
        "sites": ("discard",),
        "relations": (),
        "complement": "留 2 张不算、留 4 张算、留 3 张 + 飘 1 张也算；**不是单调量**。",
        "scoring_effect": "四白分量 +1 log2 番；打白自身（飘）保持和不变，断链打白会让和减少。",
        "undecidable": None,
    },
    {
        "id": "four_white.derivable_held4",
        "name": "手留 4 张 ⇒ 链内飘出必为 0（可推导）",
        "kind": "rule_scenario",
        "level": LEVEL_DERIVED,
        "official": (_basis(106, "手留白 + piao ≤ 4", "白板共 4 张：手留已占满时飘出必为 0"),
                     _basis(5, "白板 = 财神", "财神不可被吃碰杠胡，飘出的白板不会回到手上")),
        "source": (_src(SYM_KNOWN_PIAO, "两条可推导情形（链为 0 / 手留 4 张）的唯一实现"),),
        "predicate_text": "ctx.chain_piao is None 且 ctx.wealth_count == 4",
        "predicate_scope": "state",
        "fields": (_field(SYM_CONTEXT, "wealth_count", "手留财神张数"),
                   _field(SYM_CONTEXT, "chain_piao", "为空才需要推导")),
        "fact_tokens": ("known_piao",),
        "sites": (),
        "relations": (_rel("four_white.unknown_piao", "mutex", "可推导时该事实并非未知"),),
        "complement": "链次数为 0 时同样可推导飘出为 0（本类只登记手留 4 张这一条官方直接给出的情形）。",
        "scoring_effect": "让四白分量在缺少 chain_piao 记录时仍可判定（不接线的替代路径）。",
        "undecidable": None,
    },
    {
        "id": "four_white.unknown_piao",
        "name": "链内飘出不可判定（未知态）",
        "kind": "evidence_state",
        "level": LEVEL_IMPL,
        "official": (_basis(106, "piao ≤ count", "链内飘出是独立字段，缺它不能反推"),
                     _basis(53, "正好 4 张", "等值条件：任一侧未知就不能判成立/不成立")),
        "source": (_src(SYM_KNOWN_PIAO, "返回 None 的唯一条件：chain_piao 为空且链非零且手留不足 4 张"),),
        "predicate_text": "known_piao(wealth_count, ctx.chain_piao, ctx.chain_count) is None",
        "predicate_scope": "state",
        "fields": (_field(SYM_CONTEXT, "chain_piao", "为空 ⇒ 依据不足"),
                   _field(SYM_CONTEXT, "chain_count", "链为 0 时可推导为 0")),
        "fact_tokens": ("known_piao", "chain_piao"),
        "sites": (),
        "relations": (_rel("four_white.derivable_held4", "mutex", "可推导时不属于未知态"),),
        "complement": "该类**必须报 unknown**：不得填 0、不得当作「四白不成立」、不得并入类外。",
        "scoring_effect": "评分器在这里的唯一正确行为是「不参与」（不加不减），而不是按 0 计分。",
        "undecidable": None,
    },
    # ---- 爆头 ------------------------------------------------------------
    {
        "id": "baotou.active",
        "name": "当前爆头",
        "kind": "rule_scenario",
        "level": LEVEL_OFFICIAL,
        "official": (_basis(23, "听牌态摸任意 1 张牌上来即胡", "爆头的判定（任意听）"),
                     _basis(55, "见 1.2 判定", "爆头 ×2（最后统一加）")),
        "source": (_src(SYM_CONTEXT, "窗口状态 baotou（官方 god.baotou 为权威）"),),
        "predicate_text": "ctx.baotou 为真",
        "predicate_scope": "state",
        "fields": (_field(SYM_CONTEXT, "baotou", "本人是否爆头"),),
        "fact_tokens": ("baotou",),
        "sites": ("discard", "chi", "peng", "gang", "hu"),
        "relations": (),
        "complement": "四白与爆头**可以叠加**（指南第 23 行），不是互斥条件。",
        "scoring_effect": "爆头分量 +1 log2 番，并且是飘（继续听任意牌）的前置条件。",
        "undecidable": None,
    },
    {
        "id": "baotou.discard_recheck",
        "name": "弃牌后重判爆头",
        "kind": "rule_scenario",
        "level": LEVEL_OFFICIAL,
        "official": (_basis(23, "听牌态摸任意 1 张牌上来即胡", "任意听定义：弃牌后按弃后暗牌重判"),
                     _basis(55, "见 1.2 判定", "爆头 ×2")),
        "source": (_src(SYM_BAOTOU_ACTION, "用弃后暗牌重新判定的规则转移"),),
        "predicate_text": "ctx.baotou 为真 且 窗口存在 discard 候选",
        "predicate_scope": "state+sites",
        "fields": (_field(SYM_CONTEXT, "baotou", "动作前爆头状态"),),
        "fact_tokens": ("baotou_after_action", "baotou_after_discard"),
        "sites": ("discard",),
        "relations": (_rel("baotou.active", "implies", "弃牌重判只在爆头态下构成失分位点"),),
        "complement": "弃牌也可能**进入**爆头（指南第 23 行的任意听判定，不区分是否曾经爆头）。",
        "scoring_effect": "爆头分量在该位点可能从 1 掉到 0（−1 log2 番），也可能从 0 升到 1。",
        "undecidable": None,
    },
    {
        "id": "baotou.meld_inherit",
        "name": "吃碰杠继承爆头",
        "kind": "rule_scenario",
        "level": LEVEL_IMPL,
        "official": (),
        "source": (_src(SYM_BAOTOU_ACTION, "吃/碰/杠继承动作前状态（官方未逐事件写出赋值公式）"),),
        "predicate_text": "ctx.baotou 为真 且 窗口存在 chi / peng / gang 候选",
        "predicate_scope": "state+sites",
        "fields": (_field(SYM_CONTEXT, "baotou", "动作前爆头状态"),),
        "fact_tokens": ("baotou_after_action",),
        "sites": ("chi", "peng", "gang"),
        "relations": (_rel("baotou.active", "implies", "继承语义只在爆头态下可观察"),),
        "complement": ("**证据级别必须与结论一起引用**：官方指南未逐事件写出吃碰杠后的爆头赋值公式；"
                       "本类依据是 RULES_EVIDENCE §158—168 的生命周期表与官方本人快照轨迹，"
                       "不得扩大为「所有动作的官方对拍覆盖」。"),
        "scoring_effect": "说明吃碰在该实现下不改爆头分量，因此不能用动作标签给吃碰加减爆头分。",
        "undecidable": None,
    },
    {
        "id": "baotou.decline_win_for_piao",
        "name": "弃胡续飘位点（可胡而选择不胡）",
        "kind": "rule_scenario",
        "level": LEVEL_OFFICIAL,
        "official": (_basis(25, "弃胡", "摸牌后不强制自动胡：可提交 hu，也可弃胡打牌（飘/杠链前提）"),
                     _basis(59, "弃胡打白飘", "爆头摸到白板：可胡，也可弃胡打白博财飘"),
                     _basis(47, "爆头状态打出财神继续听任意牌胡", "财飘 ×4 起")),
        "source": (_src(SYM_WEIGHTS_V1, "基线权重 win_now=1000：立即胡的固定加分来源"),),
        "predicate_text": "ctx.baotou 为真 且 窗口存在 hu 候选 且 存在打出财神的 discard 候选",
        "predicate_scope": "state+sites",
        "fields": (_field(SYM_CONTEXT, "baotou", "爆头态下才有财飘的期权价值"),
                   _field(SYM_CONTEXT, "wealth_code", "被打出的财神牌码")),
        "fact_tokens": ("Hu", "win_now"),
        "sites": ("hu", "discard"),
        "relations": (_rel("baotou.active", "implies", "本类以爆头为前提"),
                      _rel("chain.piao_discard", "overlay", "同一张打出的财神同时是飘位点")),
        "complement": "类谓词判的是「位点存在」（可胡 + 可打白），不判「是否真的弃胡」。",
        "scoring_effect": "这是官方的显式取舍位点（×2 立即兑现 vs ×4 起的财飘期权）；估值需要兑现概率，规则不给。",
        "undecidable": None,
    },
    # ---- 官方明文叠加 / 上界组合 -----------------------------------------
    {
        "id": "overlay.four_white_baotou",
        "name": "四白 × 爆头 叠加",
        "kind": "rule_scenario",
        "level": LEVEL_OFFICIAL,
        "official": (_basis(23, "4 白听任意即胡时计爆头并与「4 个白板 ×2」叠加",
                            "官方明文：正好 4 张白板亦按爆头判定，且与四白倍率叠加"),),
        "source": (_src(SYM_FAN, "两个乘子分别左移：four_white 与 baotou 各 ×2"),),
        "predicate_text": "ctx.baotou 为真 且 四白等值条件为真（四白不可判定 ⇒ None；非爆头 ⇒ False）",
        "predicate_scope": "state",
        "fields": (_field(SYM_CONTEXT, "baotou", "爆头分量"),
                   _field(SYM_CONTEXT, "wealth_count", "四白分量的一侧")),
        "fact_tokens": ("four_white_indicator", "four_white_state", "baotou"),
        "sites": ("discard",),
        "relations": (_rel("baotou.active", "implies", "先决条件是爆头"),
                      _rel("four_white.at_four", "overlay", "同一状态上两个乘子同时成立")),
        "complement": "指南旧计番表曾有「爆头（正好 4 白板除外）」字样；v23 实测与第 23 行明文均已改为叠加。",
        "scoring_effect": "两个 log2 加数同时 +1 ⇒ ×4；这是**同一状态**上的叠加，不是条件互斥。",
        "undecidable": None,
    },
    {
        "id": "overlay.chiitoi_baotou",
        "name": "七对 × 爆头（七客 / 豪华七客）",
        "kind": "rule_scenario",
        "level": LEVEL_OFFICIAL,
        "official": (_basis(61, "6 对 + 1 财神单吊 = 七对 ×2 × 爆头 ×2 = ×4",
                            "官方明文给出七对与爆头的叠加算例"),),
        "source": (_src(SYM_FAN, "分支 ×2 与爆头 ×2 分别左移"),),
        "predicate_text": "ctx.baotou 为真 且 七对路径存活（无副露）；副露数不可判 ⇒ None",
        "predicate_scope": "state",
        "fields": (_field(SYM_CONTEXT, "baotou", "爆头分量"),
                   _field(SYM_CONTEXT, "combined_codes", "用于反推副露数")),
        "fact_tokens": ("seven_pairs_shanten_after", "meld_count_of", "baotou"),
        "sites": ("chi", "peng", "gang", "discard"),
        "relations": (_rel("branch.chiitoi_live", "implies", "七对路径必须存活"),
                      _rel("baotou.active", "implies", "爆头必须成立")),
        "complement": "七对禁副露：任何吃碰杠都会**永久**关闭这条路径，此时叠加不成立。",
        "scoring_effect": "分支与爆头两个加数同时存在时的上界抬升（×4 起，豪华七对更高）。",
        "undecidable": None,
    },
    {
        "id": "overlay.gang_piao_mix",
        "name": "杠飘混合链",
        "kind": "rule_scenario",
        "level": LEVEL_OFFICIAL,
        "official": (_basis(57, "杠飘组合叠加计算", "飘与杠可连续、可组合"),
                     _basis(45, "杠爆", "爆头状态下杠补牌胡 = 爆头 × 杠开")),
        "source": (_src(SYM_CHAIN_DETAIL, "链明细命名：count>piao>=1 ⇒ 杠飘链×N（同一规则来源）"),),
        "predicate_text": "ctx.chain_count >= 2 且 chain_piao 已知且 1 <= chain_piao < chain_count",
        "predicate_scope": "state",
        "fields": (_field(SYM_CONTEXT, "chain_count", "链次数"),
                   _field(SYM_CONTEXT, "chain_piao", "链内飘出；为空 ⇒ None")),
        "fact_tokens": ("chain_piao", "chain_count"),
        "sites": ("gang", "discard"),
        "relations": (_rel("chain.open", "implies", "混合链以链非零为前提"),),
        "complement": "chain_piao 未知时返回 None（不得按纯杠链或纯飘链处理）。",
        "scoring_effect": "同一个链里两种动作族各自贡献 ×2，链分量不区分动作标签但明细命名不同。",
        "undecidable": None,
    },
    {
        "id": "overlay.plain_branch_max",
        "name": "平胡分支上界组合（3 连杠 + 三财飘 + 爆头 + 四白板）",
        "kind": "official_bound",
        "level": LEVEL_OFFICIAL,
        "official": (_basis(63, "3 连杠 + 三财飘 + 爆头 + 4 白板 = 2⁶ × 2 × 2 = ×256",
                            "官方给出的平胡分支最大牌型"),),
        "source": (_src(SYM_FAN, "四个乘子的左移次数与官方上界一致"),),
        "predicate_text": ("有副露（平胡分支）且 chain_count == 6 且 chain_piao == 3 且 爆头 且 四白成立；"
                           "任一侧不可判 ⇒ None"),
        "predicate_scope": "state",
        "fields": (_field(SYM_CONTEXT, "chain_count", "链次数上界由官方给出"),
                   _field(SYM_CONTEXT, "chain_piao", "三财飘 = 3"),
                   _field(SYM_CONTEXT, "baotou", "爆头"),
                   _field(SYM_CONTEXT, "wealth_count", "四白一侧")),
        "fact_tokens": ("chain_count", "chain_piao", "baotou", "meld_count_of"),
        "sites": (),
        "relations": (_rel("overlay.gang_piao_mix", "implies", "6 链 3 飘即杠飘混合链"),
                      _rel("four_white.at_four", "implies", "四白条件必须成立"),
                      _rel("baotou.active", "implies", "爆头必须成立")),
        "complement": ("**本类只校验与该上界相容的必要条件，不是可达性证明**："
                       "副露数只能由暗牌张数反推（暗杠与明杠的差异在此不可见）。"),
        "scoring_effect": "官方上界用于校验评分器的量级声明（bound 推导），不用于估计可达概率。",
        "undecidable": None,
    },
    {
        "id": "overlay.global_max",
        "name": "全局上界组合（三豪华七对 + 三财飘 + 四白 + 爆头）",
        "kind": "official_bound",
        "level": LEVEL_OFFICIAL,
        "official": (_basis(65, "三豪华七对 + 三财飘 + 4 白板 + 爆头 = ×16 × 2³ × 2 × 2 = ×512",
                            "官方给出的全局最大组合"),),
        "source": (_src(SYM_FAN, "豪华组数上界 3 与链上界由结算校验"),),
        "predicate_text": ("无副露 且 locked_luxury_groups >= 3 且 chain_count == 3 且 chain_piao == 3 "
                           "且 爆头 且 四白成立；任一侧不可判 ⇒ None"),
        "predicate_scope": "state",
        "fields": (_field(SYM_CONTEXT, "chain_count", "三财飘 = 链 3"),
                   _field(SYM_CONTEXT, "chain_piao", "三财飘 = 飘 3"),
                   _field(SYM_CONTEXT, "baotou", "爆头"),
                   _field(SYM_CONTEXT, "combined_codes", "豪华组代理的输入")),
        "fact_tokens": ("locked_luxury_groups", "chain_piao", "baotou"),
        "sites": (),
        "relations": (_rel("overlay.chiitoi_baotou", "implies", "全局上界包含七对与爆头"),
                      _rel("chain.piao_discard", "implies", "三财飘包含飘位点")),
        "complement": ("**只校验与上界相容的必要条件**：豪华组数用确定性代理（只少算不多算）；"
                       "链上界 3 与官方 2³ 一致（三财飘 = 3 个飘动作）。"),
        "scoring_effect": "官方上界用于校验四个分量共同作用时的量级声明，不用于估计可达概率。",
        "undecidable": None,
    },
    # ---- 支付角色（结算结果类） -------------------------------------------
    {
        "id": "payrole.self_dealer",
        "name": "本人坐庄（付方恒为 ×8）",
        "kind": "settlement_outcome",
        "level": LEVEL_OFFICIAL,
        "official": (_basis(71, "庄家胡：三家闲家各付", "本人坐庄：三家各付 ×8；他人胡时本人付 ×8"),
                     _basis(69, "庄家 ×8", "庄家倍率恒 ×8（直上三连庄，无递增）")),
        "source": (_src(SYM_SETTLE, "四家结算的唯一实现"),),
        "predicate_text": "ctx.my_seat == ctx.dealer_seat",
        "predicate_scope": "state",
        "fields": (_field(SYM_CONTEXT, "my_seat", "本人座位"),
                   _field(SYM_CONTEXT, "dealer_seat", "庄家座位")),
        "fact_tokens": ("dealer_seat", "my_seat"),
        "sites": ("discard", "chi", "peng", "gang", "hu"),
        "relations": (_rel("payrole.self_nondealer", "mutex", "庄闲互斥且穷尽（同座位比较）"),),
        "complement": "「胡家是谁」是未来事件：窗口侧只判本人庄/闲，见 PAY_ROLE_COMBOS。",
        "scoring_effect": ("对本人所有胡牌结果是同一个常数 ⇒ **不改变同一手内的番型排序**；"
                           "改变的是得失比 ⇒ 攻防取舍（庄家放任别人胡的代价是闲家的 8 倍）。"),
        "undecidable": None,
    },
    {
        "id": "payrole.self_nondealer",
        "name": "本人闲家（本人胡 +10；庄家胡付 8；闲家胡付 1）",
        "kind": "settlement_outcome",
        "level": LEVEL_OFFICIAL,
        "official": (_basis(73, "闲家胡：庄家付 底分 × 倍率 × 8", "闲家胡：庄家付 ×8、另两闲家各付 ×1"),
                     _basis(69, "闲家 ×1", "闲家倍率为 ×1")),
        "source": (_src(SYM_SETTLE, "四家结算的唯一实现"),),
        "predicate_text": "ctx.my_seat != ctx.dealer_seat",
        "predicate_scope": "state",
        "fields": (_field(SYM_CONTEXT, "my_seat", "本人座位"),
                   _field(SYM_CONTEXT, "dealer_seat", "庄家座位")),
        "fact_tokens": ("dealer_seat", "my_seat"),
        "sites": ("discard", "chi", "peng", "gang", "hu"),
        "relations": (_rel("payrole.self_dealer", "mutex", "庄闲互斥且穷尽"),),
        "complement": "「胡家是庄还是另一闲家」是未来事件：支付分别是 ×8 与 ×1。",
        "scoring_effect": ("兑现代理常数 10；同样不改变同一手内的番型排序，只改变得失比。"),
        "undecidable": None,
    },
    # ---- 鸣牌窗口类（行为分量的作用面） -----------------------------------
    {
        "id": "meld.claim_window",
        "name": "鸣牌窗口（存在吃/碰候选）",
        "kind": "rule_scenario",
        "level": LEVEL_OFFICIAL,
        "official": (_basis(15, "碰（含明杠）窗口先于吃窗口", "鸣牌窗口的官方结构"),
                     _basis(15, "吃最多 2 摊", "吃的官方上限（服务端强制）")),
        "source": (_src(SYM_CHI_FAMILY, "吃候选生成处（含 2 摊上限）"),
                   _src(SYM_GANG_FAMILY, "杠候选生成处")),
        "predicate_text": "窗口存在 chi 或 peng 候选",
        "predicate_scope": "state+sites",
        "fields": (),
        "fact_tokens": ("Chi", "Peng"),
        "sites": ("chi", "peng"),
        "relations": (),
        "complement": "吃最多 2 摊与圈内限制都由规则层过滤候选 ⇒ 位点不出现即自动消失。",
        "scoring_effect": "鸣牌族分量（机会成本 / 等待条件校准）唯一的作用面；吃碰本身不改链。",
        "undecidable": None,
    },
    {
        "id": "meld.waiting_facts_available",
        "name": "等待事实可用（窗口内有带完整等待事实的 Pass 候选）",
        "kind": "evidence_state",
        "level": LEVEL_IMPL,
        "official": (),
        "source": (_src(SYM_MELD_NATURAL, "等待有效牌剩余估计的唯一来源；缺事实返回 None"),),
        "predicate_text": "natural_draw_value(candidates) is not None",
        "predicate_scope": "state",
        "fields": (_field(SYM_FACTS, "useful_tiles", "有效牌及剩余估计"),
                   _field(SYM_FACTS, "completeness", "事实完整性")),
        "fact_tokens": ("natural_draw_value", "useful_tiles"),
        "sites": ("chi", "peng"),
        "relations": (_rel("meld.claim_window", "overlay", "同在鸣牌位点上决定该分量是否参与"),),
        "complement": "同族的两个候选都缺此事实时返回 0（不加不减）：证据不足不等于无影响。",
        "scoring_effect": "该类的存在是鸣牌族分量在本窗口能否参与的前提。",
        "undecidable": None,
    },
    # ---- 门控类：规则层已强制，评分层**已接线 ⇒ 有谓词**（3.6b 修订） ---------
    {
        "id": "gate.you_cai_bi_kao",
        "name": "有财必拷响（手上有财神时不允许平胡）",
        "kind": "rule_scenario",
        "level": LEVEL_OFFICIAL,
        "official": (_basis(152, "有财必拷响", "手上有财神时不允许平胡，必须爆头/杠开才能胡"),
                     _basis(123, "有财必拷响", "由创建者配置，每场可能不同，必须以 API 返回为准")),
        "source": (_src(SYM_ENGINE, "规则层按开关过滤 hu 候选（engine.py:288/323）"),),
        "predicate_text": ("**已接线，可判定**：ctx.you_cai_bi_kao is True（开关打开 ⇒ 该类成立）；"
                           "字段未接线时谓词为 None（未知不填零）"),
        "predicate_scope": "state",
        "fields": (_gate_field("gate.you_cai_bi_kao"),),
        "fact_tokens": ("you_cai_bi_kao",),
        "sites": ("hu", "discard"),
        "relations": (_rel("baotou.active", "overlay", "开关打开后，爆头成为胡的必要条件"),),
        "complement": ("规则层按开关过滤候选（动作空间上生效）；评分层现在**也能读到该开关**，"
                       "因此可以显式表达「该类成立时胡必须爆头」。"),
        "scoring_effect": "开关决定「胡」这个动作是否可达，从而改变弃胡续飘位点的存在性。",
        "rule_enforcement": (_src(SYM_ENGINE, "engine 按开关过滤 hu 候选，规则层生效"),),
        "undecidable": None,
    },
    {
        "id": "gate.wall_end_gang_ban",
        "name": "末局禁杠（牌墙最后 10 墩内禁止杠）",
        "kind": "rule_scenario",
        "level": LEVEL_OFFICIAL,
        "official": (_basis(13, "最后 10 墩之内禁止杠牌", "牌墙最后 20 张保留不摸，且禁杠"),
                     _basis(13, "最后 10 墩（20 张）保留不摸", "保留区的定义")),
        "source": (_src(SYM_GANG_FAMILY, "规则层按剩余牌墙关闭杠候选（action_families.py:148-155）"),),
        "predicate_text": ("**已接线，可判定**：ctx.remaining_tile_count <= WALL_RESERVE_TILES"
                           "（保留区口径，门限取规则模块常量）；牌墙数未知（None）或未接线时为 None"),
        "predicate_scope": "state",
        "fields": (_gate_field("gate.wall_end_gang_ban"),),
        "fact_tokens": ("remaining_tile_count",),
        "sites": ("gang",),
        "relations": (_rel("chain.gang_step", "mutex", "禁杠期内该位点在动作空间上不存在"),),
        "complement": ("规则层已经在动作空间上生效（不产出杠候选）；评分层现在也能判定自己"
                       "是否处于该边界内。"),
        "scoring_effect": "链分量的杠位点在末局自然消失；但分量的量级（bound）声明不含该边界。",
        "rule_enforcement": (
            _src(SYM_GANG_FAMILY, "remaining_tile_count <= WALL_RESERVE_TILES 时不产出杠候选"),
            _src(SYM_WALL_RESERVE, "门限常量本身（本文件直接 import，不抄数字）"),),
        "undecidable": None,
    },
    {
        "id": "gate.catch_play_owner",
        "name": "抓打圈主身份（圈内本人是否为新打财神者）",
        "kind": "rule_scenario",
        "level": LEVEL_OFFICIAL,
        "official": (_basis(7, "打财神者本人不受此限", "圈主可吃碰明杠、可任意出牌；其余玩家受限"),
                     _basis(7, "圈以本人为新打财神者重启", "圈主身份随打财神者切换")),
        "source": (_src(SYM_CATCH, "抓打圈限制按圈主判定（圈主不受限）"),),
        "predicate_text": ("**已接线，可判定**：不在圈内 ⇒ False；在圈内时 "
                           "ctx.catch_play_owner_seat == ctx.my_seat；席位未知（None）或未接线时为 None"),
        "predicate_scope": "state",
        "fields": (_field(SYM_CONTEXT, "catch_play", "只有「是否在圈内」：不在圈内时该类**可判定为不成立**"),
                   _gate_field("gate.catch_play_owner"),),
        "fact_tokens": ("catch_play_owner_seat",),
        "sites": ("chi", "peng", "gang", "discard"),
        "relations": (_rel("chain.claim_repiao_circle", "overlay", "该类是该位点成立的充分条件的直接事实"),),
        "complement": ("旧口径下只能**间接**推断本人是圈主（圈内出现吃碰候选 ⇒ 规则层已过滤）；"
                       "接线后改用**直接事实**，间接推断只作对照，不再参与判定。"),
        "scoring_effect": "圈主身份决定吃碰位点是否存在，从而决定「吃碰后打财神」这条链位点是否可达。",
        "rule_enforcement": (_src(SYM_CATCH, "规则层按圈主身份限制其余玩家的动作"),),
        "undecidable": None,
    },
)

# ---------------------------------------------------------------------------
# 3. 可判定谓词（每条都是纯函数，只读上下文 / 候选事实 / 面板事实）
#
# 返回值三态：True / False / **None**。None 专指"该类在本窗口**不可判定**"
# （事实缺失），**不得**被读成 False，也不得填零（术语表：空与 0 必须区分）。
# ---------------------------------------------------------------------------


def _registry():
    """候选注册表（惰性导入，避免在只做静态检查时拉起全部候选模块）。"""

    from hangma_bot.policy import heuristics as module

    return module


def _candidate_kind(candidate: Any) -> str:
    """动作类别名（与适配器 `action_kind` 同口径：`peng:1w` -> `peng`）。"""

    key = getattr(candidate, "action_key", "") or ""
    return key.split(":", 1)[0]


def _kind_set(candidates: Sequence[Any]) -> set:
    return {_candidate_kind(item) for item in candidates}


def _has_kind(candidates: Sequence[Any], kind: str) -> bool:
    return kind in _kind_set(candidates)


def _discard_codes(candidates: Sequence[Any]) -> Tuple[str, ...]:
    """窗口内全部 discard 候选打出的牌码。"""

    codes: List[str] = []
    for item in candidates:
        action = getattr(item, "action", None)
        if isinstance(action, Discard):
            codes.append(action.tile.code)
    return tuple(codes)


def _pass_reference(candidates: Sequence[Any]):
    """窗口内带完整行牌事实的 pass 候选（代表「手牌不变」的动作前状态）。

    没有过牌候选时返回 None——纯弃牌窗口的每个候选都会改变手牌，此时**不猜**。
    """

    for item in candidates:
        if not isinstance(getattr(item, "action", None), Pass):
            continue
        facts = getattr(item, "facts", None)
        if facts is None or facts.completeness is not RuleCompleteness.COMPLETE:
            continue
        return item
    return None


def _piao_of(ctx: Any) -> Optional[int]:
    """链内飘出白板数；不可判定返回 None（单一来源：known_piao）。"""

    return known_piao(ctx.wealth_count, ctx.chain_piao, ctx.chain_count)


def _four_white_of(ctx: Any) -> Optional[bool]:
    """四白等值条件的判定；不可判定返回 None（单一来源：special_rules）。"""

    return four_white_state(ctx.wealth_count, _piao_of(ctx))


def _pred_branch_chiitoi_live(ctx, candidates, panel) -> Optional[bool]:
    melds = meld_count_of(ctx.combined_codes)
    if melds is None:
        return None
    return melds == 0


def _pred_branch_luxury_locked(ctx, candidates, panel) -> Optional[bool]:
    melds = meld_count_of(ctx.combined_codes)
    if melds is None:
        return None
    if melds != 0:
        return False
    return locked_luxury_groups(ctx.combined_codes, ctx.wealth_code) >= 1


def _pred_branch_closer_seven_pairs(ctx, candidates, panel) -> Optional[bool]:
    melds = meld_count_of(ctx.combined_codes)
    if melds is None:
        return None
    if melds != 0:
        return False
    reference = _pass_reference(candidates)
    if reference is None:
        return None
    facts = reference.facts
    seven = facts.seven_pairs_shanten_after
    standard = facts.standard_shanten_after
    if seven is None or standard is None:
        return None
    return seven < standard


def _pred_chain_open(ctx, candidates, panel) -> Optional[bool]:
    return ctx.chain_count >= 1


def _pred_chain_gang_step(ctx, candidates, panel) -> Optional[bool]:
    return _has_kind(candidates, "gang")


def _pred_chain_gang_draw_open(ctx, candidates, panel) -> Optional[bool]:
    """杠前已听：需要完整事实；有杠候选但事实不完整 ⇒ None（不猜）。"""

    gangs = [item for item in candidates if _candidate_kind(item) == "gang"]
    if not gangs:
        return False
    decided = False
    for item in gangs:
        facts = getattr(item, "facts", None)
        if facts is None or facts.completeness is not RuleCompleteness.COMPLETE:
            continue
        if facts.shanten_after is None:
            continue
        decided = True
        if facts.shanten_after == 0:
            return True
    # 有杠候选但一个完整事实都没有 ⇒ 不可判定（不得当成「杠前没听」）。
    return False if decided else None


def _pred_chain_piao_discard(ctx, candidates, panel) -> Optional[bool]:
    return bool(ctx.baotou) and ctx.wealth_code in _discard_codes(candidates)


def _pred_chain_break_discard(ctx, candidates, panel) -> Optional[bool]:
    if ctx.chain_count < 1:
        return False
    for code in _discard_codes(candidates):
        if not (ctx.baotou and code == ctx.wealth_code):
            return True
    return False


def _pred_chain_claim_repiao_circle(ctx, candidates, panel) -> Optional[bool]:
    if not ctx.catch_play:
        return False
    if not (_has_kind(candidates, "chi") or _has_kind(candidates, "peng")):
        return False
    if ctx.wealth_code not in _discard_codes(candidates):
        return False
    return bool(ctx.baotou)


def _pred_four_white_at_four(ctx, candidates, panel) -> Optional[bool]:
    return _four_white_of(ctx)


def _pred_four_white_derivable_held4(ctx, candidates, panel) -> Optional[bool]:
    return ctx.chain_piao is None and ctx.wealth_count == 4


def _pred_four_white_unknown_piao(ctx, candidates, panel) -> Optional[bool]:
    return _piao_of(ctx) is None


def _pred_baotou_active(ctx, candidates, panel) -> Optional[bool]:
    return bool(ctx.baotou)


def _pred_baotou_discard_recheck(ctx, candidates, panel) -> Optional[bool]:
    return bool(ctx.baotou) and _has_kind(candidates, "discard")


def _pred_baotou_meld_inherit(ctx, candidates, panel) -> Optional[bool]:
    return bool(ctx.baotou) and any(
        _has_kind(candidates, kind) for kind in ("chi", "peng", "gang"))


def _pred_baotou_decline_win_for_piao(ctx, candidates, panel) -> Optional[bool]:
    if not ctx.baotou:
        return False
    if not _has_kind(candidates, "hu"):
        return False
    return ctx.wealth_code in _discard_codes(candidates)


def _pred_overlay_four_white_baotou(ctx, candidates, panel) -> Optional[bool]:
    if not ctx.baotou:
        return False
    return _four_white_of(ctx)


def _pred_overlay_chiitoi_baotou(ctx, candidates, panel) -> Optional[bool]:
    if not ctx.baotou:
        return False
    return _pred_branch_chiitoi_live(ctx, candidates, panel)


def _pred_overlay_gang_piao_mix(ctx, candidates, panel) -> Optional[bool]:
    if ctx.chain_count < 2:
        return False
    if ctx.chain_piao is None:
        return None
    return 1 <= ctx.chain_piao < ctx.chain_count


def _pred_overlay_plain_branch_max(ctx, candidates, panel) -> Optional[bool]:
    if ctx.chain_count != 6:
        return False
    melds = meld_count_of(ctx.combined_codes)
    if melds is None:
        return None
    if melds < 1:
        return False
    if not ctx.baotou:
        return False
    return _four_white_of(ctx)


def _pred_overlay_global_max(ctx, candidates, panel) -> Optional[bool]:
    if ctx.chain_count != 3:
        return False
    melds = meld_count_of(ctx.combined_codes)
    if melds is None:
        return None
    if melds != 0:
        return False
    if not ctx.baotou:
        return False
    if ctx.chain_piao is None:
        return None
    if ctx.chain_piao != 3:
        return False
    if locked_luxury_groups(ctx.combined_codes, ctx.wealth_code) < 3:
        return False
    return _four_white_of(ctx)


def _pred_payrole_self_dealer(ctx, candidates, panel) -> Optional[bool]:
    return ctx.my_seat == ctx.dealer_seat


def _pred_payrole_self_nondealer(ctx, candidates, panel) -> Optional[bool]:
    return ctx.my_seat != ctx.dealer_seat


def _pred_meld_claim_window(ctx, candidates, panel) -> Optional[bool]:
    return _has_kind(candidates, "chi") or _has_kind(candidates, "peng")


def _pred_meld_waiting_facts_available(ctx, candidates, panel) -> Optional[bool]:
    return natural_draw_value(list(candidates)) is not None


def _pred_gate_you_cai_bi_kao(ctx, candidates, panel) -> Optional[bool]:
    """有财必拷响：开关打开 ⇒ 该类成立（胡必须爆头/杠开）。

    **已接线（3.6b 修订）**：读 EvaluationContext.you_cai_bi_kao。
    字段未接线 ⇒ None（**未知不填零**，不是 False）；接线状态由 check_gate_wiring() 断言。
    """

    value = _gate_fact("gate.you_cai_bi_kao", ctx)
    if value is _MISSING:
        return None
    return bool(value)


def _pred_gate_wall_end_gang_ban(ctx, candidates, panel) -> Optional[bool]:
    """末局禁杠：剩余牌墙 <= WALL_RESERVE_TILES（规则模块常量）⇒ 该类成立。

    牌墙张数未知（None）或字段未接线 ⇒ None：**不猜**（0 张是合法值，必须与"未知"分开）。
    """

    value = _gate_fact("gate.wall_end_gang_ban", ctx)
    if value is _MISSING or value is None:
        return None
    return int(value) <= WALL_RESERVE_TILES


def _pred_gate_catch_play_owner(ctx, candidates, panel) -> Optional[bool]:
    """抓打圈主：本人是新打财神者（圈主可吃碰明杠、可任意出牌）。

    三态是刻意的：**不在圈内 ⇒ False**（规则层事实，可判定，不算未知）；
    在圈内但圈主席位未知 ⇒ None（未知不填零）；有席位 ⇒ 与本人座位比较。
    """

    if not getattr(ctx, "catch_play", False):
        return False
    seat = _gate_fact("gate.catch_play_owner", ctx)
    if seat is _MISSING or seat is None:
        return None
    return seat == ctx.my_seat


CLASS_PREDICATES: Mapping[str, Callable[..., Optional[bool]]] = {
    "branch.chiitoi_live": _pred_branch_chiitoi_live,
    "branch.luxury_locked": _pred_branch_luxury_locked,
    "branch.closer_seven_pairs": _pred_branch_closer_seven_pairs,
    "chain.open": _pred_chain_open,
    "chain.gang_step": _pred_chain_gang_step,
    "chain.gang_draw_open": _pred_chain_gang_draw_open,
    "chain.piao_discard": _pred_chain_piao_discard,
    "chain.break_discard": _pred_chain_break_discard,
    "chain.claim_repiao_circle": _pred_chain_claim_repiao_circle,
    "four_white.at_four": _pred_four_white_at_four,
    "four_white.derivable_held4": _pred_four_white_derivable_held4,
    "four_white.unknown_piao": _pred_four_white_unknown_piao,
    "baotou.active": _pred_baotou_active,
    "baotou.discard_recheck": _pred_baotou_discard_recheck,
    "baotou.meld_inherit": _pred_baotou_meld_inherit,
    "baotou.decline_win_for_piao": _pred_baotou_decline_win_for_piao,
    "overlay.four_white_baotou": _pred_overlay_four_white_baotou,
    "overlay.chiitoi_baotou": _pred_overlay_chiitoi_baotou,
    "overlay.gang_piao_mix": _pred_overlay_gang_piao_mix,
    "overlay.plain_branch_max": _pred_overlay_plain_branch_max,
    "overlay.global_max": _pred_overlay_global_max,
    "payrole.self_dealer": _pred_payrole_self_dealer,
    "payrole.self_nondealer": _pred_payrole_self_nondealer,
    "meld.claim_window": _pred_meld_claim_window,
    "meld.waiting_facts_available": _pred_meld_waiting_facts_available,
    "gate.you_cai_bi_kao": _pred_gate_you_cai_bi_kao,
    "gate.wall_end_gang_ban": _pred_gate_wall_end_gang_ban,
    "gate.catch_play_owner": _pred_gate_catch_play_owner,
}

#: 类 id 列表（**冻结口径**：顺序即引用顺序，测试逐条断言）。
CLASS_IDS: Tuple[str, ...] = tuple(item["id"] for item in CLASSES)


def classify_window(ctx: Any, candidates: Sequence[Any],
                    panel: Optional[Mapping[str, Any]] = None
                    ) -> Dict[str, Optional[bool]]:
    """逐类判定一个窗口；返回 类 id -> True / False / None。

    **一个窗口可以同时属于多个类**（官方明文叠加），因此这里是映射而不是单选。
    None 表示该类在本窗口**不可判定**（事实缺失）——不得当作 False。
    """

    facts = dict(panel or {})
    return {cid: CLASS_PREDICATES[cid](ctx, candidates, facts) for cid in CLASS_IDS}

# ---------------------------------------------------------------------------
# 4. 候选的静态弱声明（`declared` 的唯一来源，两段都可核验）
#
#   ① `spec.scope` ∩ 类的判定位点 ≠ ∅（scope 是机器可读的声明）；
#   ② 候选**源码**含该类的至少一个事实记号（记号表见每条类的 fact_tokens）。
#
# 这是**记号级**弱声明，不是语义证明：它回答"候选有没有碰到这条事实"，
# 不回答"碰到了就一定算对"。矩阵把命中的记号一并落盘供人复核。
# ---------------------------------------------------------------------------


def candidate_declarations(candidate_name: str) -> Dict[str, Any]:
    """单个候选的静态声明表：类 id -> {declared, scope_hit, token_hit}。"""

    registry = _registry()
    module = registry.candidate_module(candidate_name)
    source = Path(module.__file__).read_text(encoding="utf-8")
    spec = registry.CANDIDATE_FACTORIES[candidate_name]({}, "").spec
    scope = tuple(spec.scope)
    table: Dict[str, Any] = {}
    for item in CLASSES:
        sites = tuple(item["sites"])
        scope_hit = tuple(sorted(set(scope) & set(sites)))
        token_hit = tuple(token for token in item["fact_tokens"] if token in source)
        # 无判定位点的类（状态类 / 证据态类 / 官方上界类）只按事实记号判定。
        scope_ok = True if not sites else bool(scope_hit)
        table[item["id"]] = {
            "declared": bool(scope_ok and token_hit),
            "scope_hit": list(scope_hit),
            "token_hit": list(token_hit),
        }
    return {
        "candidate": candidate_name,
        "declared_scope": list(scope),
        "spec_version": spec.version,
        "spec_name": spec.name,
        "declaration_basis": "scope ∩ 判定位点 ≠ ∅ 且 源码含事实记号（记号级弱声明，非语义证明）",
        "classes": table,
    }


def declared_from_table(table: Mapping[str, Any]) -> Tuple[str, ...]:
    """从声明表里取"声明的类 id"（单一口径；源码现算与注入表共用）。"""

    return tuple(cid for cid in CLASS_IDS if table[cid]["declared"])


def declared_class_ids(candidate_name: str) -> Tuple[str, ...]:
    """该候选声明覆盖的类 id（无声明即空元组）。"""

    return declared_from_table(candidate_declarations(candidate_name)["classes"])

# ---------------------------------------------------------------------------
# 5. 覆盖账：四态判定、逐候选状态、类外零增量、缺口清单
#
# **逐类独立出账，不得合并成单一总分**：汇总里只有 verdict 计数表，
# 没有分数、没有加权、没有排序，并显式标注不得作为准入依据。
# ---------------------------------------------------------------------------

_TOOL_CACHE: Dict[str, Any] = {}


def _tool(name: str):
    """按名加载同目录下的坐隐工具（复用既有口径，不复制实现）。"""

    if name not in _TOOL_CACHE:
        spec = importlib.util.spec_from_file_location(name, _project_file(_PROJECT_ROOT, _HERE / (name + ".py")))
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        assert spec.loader is not None
        spec.loader.exec_module(module)
        _TOOL_CACHE[name] = module
    return _TOOL_CACHE[name]


def class_verdict(windows_in_class: int, windows_undecided: int) -> str:
    """覆盖四态判定（纯函数，便于精确测试）。

      sufficient      该类判定出的窗口数 >= MIN_CLASS_WINDOWS；
      insufficient    该类有窗口，但少于下限（证据不足，不是"无影响"）；
      unknown         该类**一个窗口都没判定出来**且有窗口不可判定
                      —— 不得填零、不得等同于"无影响"、不得并入 not_applicable；
      not_applicable  该类在面板上可判定且一个窗口都不属于它。

    优先级是**刻意的**：先看是否够量、再看是否有量、最后才区分"未知"与"不适用"。
    空面板（两个计数都为 0）判 not_applicable，由上层另行标注"面板为空"。
    """

    if windows_in_class >= MIN_CLASS_WINDOWS:
        return "sufficient"
    if windows_in_class > 0:
        return "insufficient"
    if windows_undecided > 0:
        return "unknown"
    return "not_applicable"


#: 四态的读法（**必须与数字一起引用**，否则 unknown 会被读成零、not_applicable 会被读成稀有）。
VERDICT_NOTES: Mapping[str, str] = {
    "sufficient": "本面板该类的覆盖达到下限；结论只针对本面板，不是效果结论。",
    "insufficient": "本面板该类有窗口但少于下限：**证据不足**，不是「无影响」。",
    "not_applicable": ("本面板没有可判定窗口属于该类 —— 这是**面板覆盖**的陈述，"
                       "不是规则上不存在，也不是机制稀有。"),
    "unknown": ("本面板无法判定该类（事实缺失）：**不得填零**、不得读成「无影响」、"
                "不得并入 not_applicable。"),
}


def verdict_note(verdict: str) -> str:
    """四态的固定读法（单一来源）。"""

    return VERDICT_NOTES[verdict]


def candidate_class_status(declared: bool, windows_in_class: int,
                           fired: int, changed: int) -> str:
    """候选 × 类的证据状态（描述现状，**不给效果结论**）。

      undeclared        候选没有声明覆盖该类；
      no_window         本面板上该类一个窗口都没有（**不是**"机制稀有"的结论）；
      no_fire           类内有窗口但候选一次都没给出非零调整；
      fired_no_change   触发过但没改变首选；
      changed           触发且改变了首选。
    """

    if not declared:
        return "undeclared"
    if windows_in_class == 0:
        return "no_window"
    if fired == 0:
        return "no_fire"
    if changed == 0:
        return "fired_no_change"
    return "changed"


def aggregate_records(records: Sequence[Mapping[str, Any]],
                      candidate_names: Sequence[str]) -> Dict[str, Any]:
    """把逐窗口记录聚合成逐类账（纯函数）。"""

    classes: Dict[str, Any] = {
        cid: {"windows_in_class": 0, "windows_undecided": 0, "windows_out_of_class": 0,
              "candidates": {name: {"fired": 0, "changed": 0} for name in candidate_names}}
        for cid in CLASS_IDS
    }
    for record in records:
        in_class = set(record["in_class"])
        undecided = set(record["undecided"])
        for cid in CLASS_IDS:
            bucket = classes[cid]
            if cid in in_class:
                bucket["windows_in_class"] += 1
            elif cid in undecided:
                bucket["windows_undecided"] += 1
            else:
                bucket["windows_out_of_class"] += 1
            if cid in in_class:
                for name in candidate_names:
                    entry = record["per_candidate"][name]
                    if entry["fired"]:
                        bucket["candidates"][name]["fired"] += 1
                    if entry["changed"]:
                        bucket["candidates"][name]["changed"] += 1
    return {"windows": len(records), "classes": classes}


def class_scope_violations(records: Sequence[Mapping[str, Any]], candidate_name: str,
                           declared: Sequence[str]) -> Dict[str, List[Dict[str, Any]]]:
    """**类外零增量核对**：该候选的改选必须落在它**已声明**的类内。

    返回两类（**必须分开读**）：
      violations        改选窗口里既没有已声明类成立、也没有已声明类不可判定
                        ⇒ 明确的**类外改选**（声明与实际不符）；
      undecided_changes 改选窗口里有已声明类**不可判定** ⇒ 归属未知，
                        既不能算违规、也不能算合规（unknown 不得填零）。
    """

    declared_set = set(declared)
    violations: List[Dict[str, Any]] = []
    undecided_changes: List[Dict[str, Any]] = []
    for record in records:
        entry = record["per_candidate"][candidate_name]
        if not entry["changed"]:
            continue
        in_class = set(record["in_class"])
        undecided = set(record["undecided"])
        if in_class & declared_set:
            continue
        sample = {"window": record["window"], "in_class": sorted(in_class),
                  "undecided": sorted(undecided)}
        if undecided & declared_set:
            undecided_changes.append(sample)
        else:
            violations.append(sample)
    return {"violations": violations, "undecided_changes": undecided_changes}


def class_fact_wiring(item: Mapping[str, Any]) -> Dict[str, Any]:
    """该类所需事实**是否已接线**（缺口清单的必备字段）。

    3.6b 修订：门控类不再走 undecidable 分支，而是按**接线契约表**现读上下文：
    `wired_to_context` 直接回答"这个字段现在在不在 EvaluationContext 里"，
    规则层强制点（源码符号）一并带出。
    """

    undecidable = item.get("undecidable")
    if undecidable:
        return {"wired": False, "missing": dict(undecidable["missing"]),
                "reason": undecidable["reason"]}
    out: Dict[str, Any] = {"wired": True,
                           "fields": [dict(entry) for entry in item["fields"]]}
    if item.get("rule_enforcement"):
        out["rule_enforcement"] = [dict(entry) for entry in item["rule_enforcement"]]
    wired = GATE_FACT_WIRING.get(item["id"])
    if wired:
        out["wired_to_context"] = wired["field"] in context_field_names()
        out["field"] = wired["field"]
        out["wired_by"] = wired["wired_by"]
    return out


def gap_report(declarations: Mapping[str, Any],
               aggregate: Optional[Mapping[str, Any]] = None) -> List[Dict[str, Any]]:
    """缺口清单：**当前没有任何候选覆盖**的场景类（评分器未做）逐条列出。

    判据（两条都写进条目，不合并）：
      undeclared_by_all             六个静态注册候选没有一个声明覆盖它；
      declared_but_no_fire_on_panel 有声明，但本面板上一次都没触发（**面板覆盖问题**，
                                    不是"机制稀有"的结论）。
    不可判定的类另标 undecidable_in_scoring_context，并给出补齐所需的字段。
    """

    by_class: Dict[str, List[str]] = {cid: [] for cid in CLASS_IDS}
    for name, table in declarations.items():
        for cid, entry in table["classes"].items():
            if entry["declared"]:
                by_class[cid].append(name)
    observed: Dict[str, List[str]] = {cid: [] for cid in CLASS_IDS}
    if aggregate is not None:
        for cid, bucket in aggregate["classes"].items():
            for name, counts in bucket["candidates"].items():
                if counts["fired"] > 0:
                    observed[cid].append(name)

    gaps: List[Dict[str, Any]] = []
    for item in CLASSES:
        cid = item["id"]
        declared_by = sorted(by_class[cid])
        reasons: List[str] = []
        if not declared_by:
            reasons.append("undeclared_by_all")
        if aggregate is not None and declared_by and not observed[cid]:
            reasons.append("declared_but_no_fire_on_panel")
        if item.get("undecidable"):
            reasons.append("undecidable_in_scoring_context")
        if not reasons:
            continue
        gaps.append({
            "class_id": cid,
            "class_name": item["name"],
            "reasons": reasons,
            "declared_by": declared_by,
            "observed_fired_on_panel": sorted(observed[cid]),
            "official": [dict(entry) for entry in item["official"]],
            "required_fact": class_fact_wiring(item),
            "note": ("记录缺口 **≠** 机制稀有：语料/面板没有位点不构成对机制稀缺性的判断，"
                     "也不得据此做预算规划。"),
        })
    return gaps

def _cite(file: str, line: int, marker: str, note: str) -> Dict[str, Any]:
    """一条**源码/实测**依据：文件 + 行号 + 该行必须出现的标记（--check 逐条核对）。"""

    return {"file": file, "line": line, "marker": marker, "note": note}


#: **有据可查的现存缺口**（不是"待研究"）：每条都给出文件与行号，--check 逐条核对标记。
#: 这些缺口与场景类一一挂钩，供 `"评分器未做"` 清单直接引用。
KNOWN_GAPS: Tuple[Dict[str, Any], ...] = (
    {
        "id": "gap.payrole_absent_in_scoring_layer",
        "classes": ("payrole.self_dealer", "payrole.self_nondealer"),
        "title": "庄闲在评分层缺席（且已有一次被判定为结构性空操作的尝试）",
        "level": LEVEL_IMPL,
        "citations": (
            _cite("src/hangma_bot/policy/weights_v1.py", 13, "class HeuristicWeightsV1",
                  "V1/V2 基线权重共 11 项，**没有庄闲字段**"),
            _cite("src/hangma_bot/policy/hu_upgrade.py", 42, "真实支付结构不对称",
                  "全仓唯一有庄闲建模的地方：风险表 (wall_band, threat, dealer) 三元分组"),
            _cite("src/hangma_bot/policy/hu_upgrade_calibration.py", 22, "不改变任何决策",
                  "庄闲分离定价**已试过**：方向 B 风险表 v3 相对 v2 表差分 0 / 10,769 窗口"),
            _cite("src/hangma_bot/policy/hu_upgrade_calibration.py", 23, "仍然为 0",
                  "把 loss_absolute 归零（比 v2 更宽松）后差异仍为 0 ⇒ 不是数值标定问题"),
            _cite("src/hangma_bot/policy/hu_upgrade_calibration.py", 27, "恒松弛",
                  "根因：上游先要求「可证明任意下一摸必翻倍」，风险表恒松弛 ⇒ 结构性空操作"),
            _cite("src/hangma_bot/policy/hu_upgrade_calibration.py", 32, "顺序反过来的话",
                  "顺序是硬约束：先解锁可证明性，再给庄闲定价"),
            _cite("src/hangma_bot/policy/hu_upgrade_calibration.py", 37, "10.75 / 4.78",
                  "实测（真实平台两池 27,824 个「我方弃牌后摸牌」样本，墙余 40—63）：失败均付 庄 10.75 / 闲 4.78"),
            _cite("src/hangma_bot/policy/hu_upgrade_calibration.py", 38, "9.59 / 4.62",
                  "实测（墙余 >=64）：庄 9.59 / 闲 4.62 ⇒ 约 2.2—2.25 倍，与官方 ×8/×1 支付结构一致"),
        ),
        "measured_facts": {
            "samples": 27824,
            "dealer_vs_nondealer_loss_ratio": "约 2.2—2.25 倍（两池一致）",
            "official_structure": "庄家侧 ×8、闲家对闲家 ×1（指南第 69—73 行）",
        },
        "why_not_a_parameter_problem": (
            "差分 0 与 loss_absolute 归零后仍为 0 说明：不是参数没调对，"
            "而是上游的**可证明性门槛**（要求「任意下一摸必翻倍」）让风险项恒松弛。"),
        "precondition": (
            "**硬前置条件**：兑现概率层（非终局价值）先能表达「不保证但很可能」的概率路径，"
            "庄闲定价才不是空操作；顺序反过来永远是空操作（hu_upgrade_calibration.py:29—32）。"),
        "current_state": (
            "UpgradeRiskCell.dealer / loss_absolute 只是**保留的扩展点**（类型安全 + 回归），"
            "冻结表 RISK_CELLS 的两条 cell 都是 dealer=None（庄闲通用价），"
            "v3 表与其两个实验臂已移出可用策略清单。"),
        "fact_wiring": {"wired": True,
                        "note": "dealer_seat 已在 EvaluationContext；缺的不是接线，是定价的前置层"},
        "source": (_src(SYM_WEIGHTS_V1, "基线权重无庄闲字段的核对点"),
                   _src(SYM_HU_UPGRADE, "dealer 扩展点（保留，未定价）"),),
    },
    {
        "id": "gap.risk_not_scaled_by_fan_or_pay_multiplier",
        "classes": ("payrole.self_dealer", "payrole.self_nondealer", "meld.claim_window"),
        "title": "风险项不随番值 / 支付倍率缩放（固定常数）",
        "level": LEVEL_IMPL,
        "citations": (
            _cite("src/hangma_bot/policy/weights_v1.py", 23, "claim_risk_peng",
                  "碰牌固定风险分 6.0（与 ×8/×1 支付倍率、对手番型无关）"),
            _cite("src/hangma_bot/policy/weights_v1.py", 24, "claim_risk_chi",
                  "吃牌固定风险分 10.0（同上）"),
            _cite("src/hangma_bot/policy/weights_v1.py", 25, "feed_risk",
                  "弃牌喂牌风险 6.0/单位（同上）"),
            _cite("src/hangma_bot/policy/weights_v1.py", 26, "safe_tile_bonus",
                  "熟张安全加分 3.0（同上）"),
        ),
        "why_it_matters": (
            "支付结构是 ×8/×1 且随番型倍率放大（官方第 69—73 行）：庄位大番场景下，"
            "固定常数风险项与实际支付量级脱钩。"),
        "precondition": (
            "与上一条同源：风险要与支付量级挂钩，必须先有能表达概率与量级的兑现层；"
            "否则调大常数只是把同一个空操作换成另一种标定。"),
        "fact_wiring": {"wired": True,
                        "note": "风险项是纯常数，不需要新事实；缺的是与支付量级挂钩的形式"},
        "source": (_src(SYM_WEIGHTS_V1, "四个固定风险常数的唯一来源"),),
    },
)


# ---------------------------------------------------------------------------
# 6. 覆盖账运行器（真实窗口做骨架：解码 -> 规则分析 -> 建上下文 -> 基线/候选跑一遍）
#
# 与门禁 gate_g2 同口径的地方**直接复用**（首选动作取 `sitin_m4_recompute._first_key`，
# 构造集标记取 `sitin_gates.looks_like_trigger_set`），不复制第二套判定。
# ---------------------------------------------------------------------------

#: 执行失败明细的样本上限（计数不受限；与门禁同口径）。
MAX_FAILURE_SAMPLES = 20

#: 原始覆盖诊断的字段说明（与 `sitin_trigger_windows.coverage_of_corpus` 同口径的**raw 层**）。
PANEL_DIAGNOSTICS_NOTE: str = (
    "**只统计原始观察（未过滤）**：回答「这份语料到底有没有该类的位点」。"
    "只报过滤后的可用窗口，会把「被规则层降级排除」误读成「数据里不存在」"
    "（§F.4 的教训）。可用窗口数见同一份产物的 panel 段。")


#: 记录层视图（3.6b 返工，F7）：
#:   raw    = **记录原样**（observation.chain_piao 是落盘时的即时值；链内飘出未知的行会被规则层降级排除）；
#:   filled = **记录层归一化后**（用适配器的同一生产函数按本人动作史归因；不可归因仍记 unknown）。
#: 归一化视图是 Lead 裁定的 canonical 面板口径；两个视图**必须并列报**，分母不得混用、不得相加。
RECORD_LAYER_RAW = "raw"
RECORD_LAYER_FILLED = "filled"
RECORD_LAYER_MODES: Tuple[str, ...] = (RECORD_LAYER_RAW, RECORD_LAYER_FILLED)

_CHAIN_PIAO: Optional[Any] = None


def chain_piao_module():
    """惰性导入记录层适配器（**推导的唯一来源**，本文件不复制任何归因规则）。"""

    global _CHAIN_PIAO
    if _CHAIN_PIAO is None:
        from hangma_bot.adapters.recording import chain_piao as module
        _CHAIN_PIAO = module
    return _CHAIN_PIAO


def normalize_record_layer(row: Mapping[str, Any],
                           mode: str = RECORD_LAYER_RAW) -> Mapping[str, Any]:
    """把一个决策行按记录层视图归一化；`raw` 原样返回，`filled` 走**生产函数**。

    `filled` 只改两处（与落盘路径完全一致）：`request.observation.chain_piao` 与新增的
    归因块。推导失败时生产函数原样返回并附 `status=error` 的归因块——本函数因此**不会**
    因补全失败丢记录，也不会把补全失败当成"值为 0"。
    """

    if mode == RECORD_LAYER_RAW:
        return row
    if mode not in RECORD_LAYER_MODES:
        raise ValueError("record_layer 必须是 {0}，得到 {1!r}".format(
            list(RECORD_LAYER_MODES), mode))
    request = row.get("request")
    if not isinstance(request, Mapping):
        return row
    module = chain_piao_module()
    normalized = module.normalize_decision_input_payload({"request": request})
    out = dict(row)
    filled = normalized.get("request")
    if isinstance(filled, Mapping):
        out["request"] = filled
    attribution = normalized.get(module.CHAIN_PIAO_ATTRIBUTION_KEY)
    if isinstance(attribution, Mapping):
        out[module.CHAIN_PIAO_ATTRIBUTION_KEY] = attribution
    return out


class RawCoverageDiagnostics:
    """raw 层覆盖诊断的**累加器**（3.6b 返工：单次遍历即可，无需二次读入）。

    与 `panel_diagnostics()` 同口径（后者现在也走本累加器），因此两个入口的数字**必然一致**。
    """

    def __init__(self) -> None:
        self.rows = 0
        self.undecodable = 0
        self.catch_play_true = 0
        self.catch_play_owner_known = 0
        self.chain_count_nonzero = 0
        self.chain_piao_known = 0
        self.chain_piao_undecidable = 0
        self.baotou_true = 0
        self.hand_holds_wealth = 0

    def add(self, recorded: Any) -> None:
        """累加一条**已解码**的记录（解码失败由调用方计入 undecodable）。"""

        observation = recorded.observation
        state = observation.rule_state
        self.rows += 1
        if state.catch_play:
            self.catch_play_true += 1
        if state.catch_play_owner_seat is not None:
            self.catch_play_owner_known += 1
        if state.chain_count > 0:
            self.chain_count_nonzero += 1
        if observation.chain_piao is not None:
            self.chain_piao_known += 1
        elif state.chain_count > 0:
            self.chain_piao_undecidable += 1
        if state.baotou:
            self.baotou_true += 1
        if any(tile.code == state.wealth_god.code for tile in observation.my_hand):
            self.hand_holds_wealth += 1

    def as_dict(self) -> Dict[str, Any]:
        return {
            "raw_windows": self.rows,
            "undecodable": self.undecodable,
            "raw_catch_play_true": self.catch_play_true,
            "raw_catch_play_owner_known": self.catch_play_owner_known,
            "raw_chain_count_nonzero": self.chain_count_nonzero,
            "raw_chain_piao_known": self.chain_piao_known,
            "raw_chain_piao_undecidable": self.chain_piao_undecidable,
            "raw_baotou_true": self.baotou_true,
            "raw_hand_holds_wealth": self.hand_holds_wealth,
            "note": PANEL_DIAGNOSTICS_NOTE,
        }


def panel_diagnostics(rows: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    """原始覆盖诊断（raw 层）：换语料先跑它，避免拿没有位点的语料去判候选。

    **与覆盖判定无关**：它只描述输入面板，不参与任何 verdict（覆盖仍按规则可枚举度量）。
    """

    codec = build_decision_codec()
    decode_request = codec["decode_request"]
    diagnostics = RawCoverageDiagnostics()
    for row in rows:
        payload = row.get("request")
        if not isinstance(payload, Mapping):
            diagnostics.undecodable += 1
            continue
        try:
            recorded = decode_request(payload)
        except Exception:
            diagnostics.undecodable += 1
            continue
        diagnostics.add(recorded)
    return diagnostics.as_dict()




def evaluate_panel(rows: Iterable[Mapping[str, Any]], candidate_names: Sequence[str], *,
                   ruleset: str = PANEL_RULESET, limit: Optional[int] = None,
                   weights_by_candidate: Optional[Mapping[str, Mapping[str, float]]] = None,
                   you_cai_bi_kao: Optional[bool] = PANEL_YOU_CAI_BI_KAO,
                   record_layer: str = RECORD_LAYER_RAW,
                   diagnostics: bool = True
                   ) -> Dict[str, Any]:
    """在面板（触发集或语料）上逐窗口分类 + 逐候选测量。

    返回 `{"records": [...], "panel": {...}, "panel_facts": {...}}`：
      records 每行含 window / in_class / undecided / per_candidate（fired、changed）；
      panel 是"总行数 = 排除 + 失败 + 计分"的对账表；
      panel_facts 是**工具侧**的面板事实（评分上下文看不到，见 gate.you_cai_bi_kao）。

    `weights_by_candidate`（2026-09-16 新增，缺省 None）：按候选名给出 `adj.*` 权重，
    供门禁侧（G-2C 逐类判定）要求"判定针对同一个 `bound_identity` 的候选"。
    **缺省不传时行为与 3.6a 覆盖账完全一致**（注册表默认参数），本参数不改变既有口径。
    """

    recompute = _tool("sitin_m4_recompute")
    codec = build_decision_codec()
    decode_request, decode_budget = codec["decode_request"], codec["decode_budget"]
    rules = HangmaRules(RuleConfig(ruleset_version=ruleset, base_score=PANEL_BASE_SCORE,
                                   you_cai_bi_kao=PANEL_YOU_CAI_BI_KAO))
    clock = ManualClock(start_monotonic=100.0)
    baseline = ComparableHeuristicPolicyV2(monotonic=clock.now)
    registry = _registry()
    # **候选参数按名传入**（3.6b 门禁侧的新增用法；缺省 None = 不传参数）：
    # 逐类判定必须针对**与门禁记录同一个 bound_identity** 的候选，而身份里含 adj.* 参数。
    # 不传参数的路径**逐字节**保持 3.6a 覆盖账的原行为（构造调用的形状都不变），
    # 因此既有覆盖产物不因本参数而改变。
    given_weights = dict(weights_by_candidate or {})
    policies = {}
    for name in candidate_names:
        given = given_weights.get(name)
        if given is None:
            policies[name] = registry.build_candidate(name, monotonic=clock.now)
        else:
            policies[name] = registry.build_candidate(
                name, weights=dict(given), monotonic=clock.now)

    # **单次遍历**（3.6b 返工，F7）：canonical 面板 359k 行，若先把行物化进内存约 28 GB；
    # 因此本函数接受**任意可迭代**，并把 raw 层诊断折进同一遍循环（不再二次读入）。
    raw_diagnostics = RawCoverageDiagnostics()
    records: List[Dict[str, Any]] = []
    excluded_decode = 0
    excluded_degraded = 0
    # 面板自洽核对：本地规则重算出的合法候选 vs 记录里落盘的合法候选。
    # 它回答"这份面板的规则配置（含 you_cai_bi_kao / base_score）是否与产生记录时一致"，
    # 是**面板声明**的数据侧旁证（不一致时结论必须降级读）。
    legal_match = 0
    legal_mismatch = 0
    legal_absent = 0
    baseline_failures: List[Dict[str, Any]] = []
    candidate_failures: List[Dict[str, Any]] = []
    baseline_failed = 0
    candidate_failed = 0
    rows_seen = 0
    for row in rows:
        rows_seen += 1
        if limit is not None and len(records) >= limit:
            break
        row = normalize_record_layer(row, record_layer)
        payload = row.get("request")
        if not isinstance(payload, Mapping):
            excluded_decode += 1
            raw_diagnostics.undecodable += 1
            continue
        try:
            recorded = decode_request(payload)
            budget = translate_budget(
                decode_budget(row.get("budget"), row.get("budget_origin_monotonic", 0.0)),
                row.get("budget_origin_monotonic", 0.0), 100.0)
            analysis = rules.analyze(recorded.observation)
        except Exception:
            excluded_decode += 1
            raw_diagnostics.undecodable += 1
            continue
        # raw 层诊断按**归一化后**的观察记账：归一化视图下"修前未知 ⇒ 修后可判"的行
        # 会体现在 raw_chain_piao_known 上，这正是新建面板要报的差异。
        raw_diagnostics.add(recorded)
        if analysis.completeness is RuleCompleteness.DEGRADED or not analysis.legal_candidates:
            excluded_degraded += 1
            continue
        request = DecisionRequest(
            observation=recorded.observation, competition=recorded.competition,
            rules=analysis, decision_id=recorded.decision_id,
            trigger_seq=recorded.trigger_seq, window_key=recorded.window_key,
            rejected_attempts=())
        window = str(recorded.decision_id)
        try:
            base_plan = asyncio.run(baseline.choose(request, budget))
        except Exception as exc:
            baseline_failed += 1
            if len(baseline_failures) < MAX_FAILURE_SAMPLES:
                baseline_failures.append({"window": window,
                                          "error": type(exc).__name__ + ": " + str(exc)})
            continue
        recorded_rules = payload.get("rules")
        if isinstance(recorded_rules, Mapping):
            recorded_keys = {entry.get("action_key")
                             for entry in (recorded_rules.get("legal_candidates") or ())}
        else:
            recorded_keys = set()
        if recorded_keys:
            if recorded_keys == {candidate.action_key for candidate in analysis.legal_candidates}:
                legal_match += 1
            else:
                legal_mismatch += 1
        else:
            legal_absent += 1
        try:
            # **评分上下文按面板规则配置构造**（3.6b：you_cai_bi_kao 已接进上下文）。
            # 另两个门控字段（remaining_tile_count / catch_play_owner_seat）由观察自动填充。
            ctx = build_context(recorded.observation, you_cai_bi_kao=you_cai_bi_kao)
            classes = classify_window(ctx, analysis.legal_candidates)
        except Exception as exc:
            candidate_failed += 1
            if len(candidate_failures) < MAX_FAILURE_SAMPLES:
                candidate_failures.append({"window": window, "stage": "classify",
                                           "error": type(exc).__name__ + ": " + str(exc)})
            continue
        base_first = recompute._first_key(base_plan)
        per_candidate: Dict[str, Any] = {}
        failed = False
        for name, policy in policies.items():
            before = policy.adjustment.fired_count
            try:
                plan = asyncio.run(policy.choose(request, budget))
            except Exception as exc:
                candidate_failed += 1
                if len(candidate_failures) < MAX_FAILURE_SAMPLES:
                    candidate_failures.append({"window": window, "stage": name,
                                               "error": type(exc).__name__ + ": " + str(exc)})
                failed = True
                break
            per_candidate[name] = {
                "fired": policy.adjustment.fired_count > before,
                "changed": recompute._first_key(plan) != base_first,
            }
        if failed:
            continue
        records.append({
            "window": window,
            "in_class": [cid for cid in CLASS_IDS if classes[cid] is True],
            "undecided": [cid for cid in CLASS_IDS if classes[cid] is None],
            "per_candidate": per_candidate,
        })

    # 行总数：可迭代输入（streaming）无法取 len，用**实际遍历计数**；列表输入保持旧语义（len）。
    try:
        rows_total = len(rows)                     # type: ignore[arg-type]
    except TypeError:
        rows_total = rows_seen
    panel = {
        "rows_seen": rows_seen,
        "rows_total": rows_total,
        "record_layer": record_layer,
        "excluded_decode": excluded_decode,
        "excluded_degraded": excluded_degraded,
        "baseline_failed": baseline_failed,
        "candidate_failed": candidate_failed,
        "scored": len(records),
        "accounting_sum": (excluded_decode + excluded_degraded + baseline_failed
                           + candidate_failed + len(records)),
        "baseline_failure_samples": baseline_failures,
        "candidate_failure_samples": candidate_failures,
    }
    panel["reconciles"] = panel["accounting_sum"] == rows_seen
    panel["legal_reconciliation"] = {
        "match": legal_match,
        "mismatch": legal_mismatch,
        "recorded_absent": legal_absent,
        "note": ("本地规则重算的合法候选与记录落盘合法候选相同的窗口数。match 高 ⇒ "
                 "面板的规则配置（ruleset / base_score / you_cai_bi_kao）与产生记录时一致；"
                 "mismatch 高 ⇒ 结论必须降级读（先解释差异，别把差异算进候选行为）。"),
    }
    if diagnostics:
        panel["raw_coverage"] = raw_diagnostics.as_dict()
    panel_facts = {
        "ruleset_version": ruleset,
        "base_score": PANEL_BASE_SCORE,
        # 记录层视图（F7）：canonical 面板是 filled 视图；raw 视图是它的前态，两列并列报。
        "record_layer": record_layer,
        # 3.6b：开关**已接进评分上下文**，因此它现在是一条真正的面板参数（而不是"看不见"）。
        "you_cai_bi_kao": you_cai_bi_kao,
        "you_cai_bi_kao_source": ("面板声明参数（CLI/调用方可覆盖）；记录里不含该开关 ⇒ "
                                  "只能声明，不能从记录反推。一致性由 legal_reconciliation 旁证。"),
        "note": ("工具侧面板事实；you_cai_bi_kao 已接线（其余两项由观察填充）。"
                 "两者都不是效果证据。"),
    }
    return {"records": records, "panel": panel, "panel_facts": panel_facts}


def known_gap_entries() -> List[Dict[str, Any]]:
    """有据可查的现存缺口（KNOWN_GAPS）转成产物条目。"""

    entries: List[Dict[str, Any]] = []
    for item in KNOWN_GAPS:
        entry = {"kind": "known_gap", "gap_id": item["id"], "title": item["title"],
                 "class_ids": list(item["classes"]), "level": item["level"],
                 "citations": [dict(c) for c in item["citations"]],
                 "fact_wiring": dict(item["fact_wiring"]),
                 "precondition": item.get("precondition"),
                 "note": "**不是「待研究」**：本条有实测记录与被淘汰的尝试，按引用可逐条复核。"}
        for extra in ("measured_facts", "why_not_a_parameter_problem", "why_it_matters",
                      "current_state", "source"):
            if extra in item:
                value = item[extra]
                entry[extra] = ([dict(v) for v in value] if isinstance(value, tuple)
                                else value)
        entries.append(entry)
    return entries


def coverage_ledger(input_info: Mapping[str, Any], evaluation: Mapping[str, Any],
                    candidate_names: Sequence[str],
                    declarations: Optional[Mapping[str, Any]] = None
                    ) -> Dict[str, Any]:
    """逐类出账 + 逐候选状态 + 类外零增量 + 缺口清单（**不得合并成单一总分**）。

    @@declarations@@ 缺省时从候选源码现算；显式传入只用于**构造面板测试**
    （合成候选名不在注册表里），生产路径不会用到它。
    """

    records = evaluation["records"]
    aggregate = aggregate_records(records, candidate_names)
    if declarations is None:
        declarations = {name: candidate_declarations(name) for name in candidate_names}

    classes_out: List[Dict[str, Any]] = []
    for item in CLASSES:
        cid = item["id"]
        bucket = aggregate["classes"][cid]
        verdict = class_verdict(bucket["windows_in_class"], bucket["windows_undecided"])
        candidates_out = {}
        for name in candidate_names:
            decl = declarations[name]["classes"][cid]
            counts = bucket["candidates"][name]
            candidates_out[name] = {
                "declared": decl["declared"],
                "scope_hit": decl["scope_hit"],
                "token_hit": decl["token_hit"],
                "fired_windows": counts["fired"],
                "changed_windows": counts["changed"],
                "status": candidate_class_status(
                    decl["declared"], bucket["windows_in_class"],
                    counts["fired"], counts["changed"]),
            }
        classes_out.append({
            "id": cid,
            "name": item["name"],
            "kind": item["kind"],
            "level": item["level"],
            "verdict": verdict,
            "verdict_note": verdict_note(verdict),
            "windows_in_class": bucket["windows_in_class"],
            "windows_undecided": bucket["windows_undecided"],
            "windows_out_of_class": bucket["windows_out_of_class"],
            "candidates": candidates_out,
            "undecidable": item.get("undecidable"),
            "rule_enforcement": [dict(entry) for entry in item.get("rule_enforcement", ())],
        })

    out_of_class = {}
    for name in candidate_names:
        declared = declared_from_table(declarations[name]["classes"])
        scoped = class_scope_violations(records, name, declared)
        out_of_class[name] = {
            "declared_classes": list(declared),
            "changed_windows": sum(
                1 for record in records if record["per_candidate"][name]["changed"]),
            "violations": scoped["violations"][:MAX_FAILURE_SAMPLES],
            "violation_total": len(scoped["violations"]),
            "undecided_changes": scoped["undecided_changes"][:MAX_FAILURE_SAMPLES],
            "undecided_change_total": len(scoped["undecided_changes"]),
        }

    verdict_counts: Dict[str, int] = {key: 0 for key in VERDICTS}
    for entry in classes_out:
        verdict_counts[entry["verdict"]] += 1

    gaps = [{"kind": "class_gap", **entry} for entry in gap_report(declarations, aggregate)]
    gaps += known_gap_entries()

    return {
        "schema": COVERAGE_SCHEMA,
        "input": dict(input_info),
        "panel": dict(evaluation["panel"]),
        "panel_facts": dict(evaluation["panel_facts"]),
        "min_class_windows": MIN_CLASS_WINDOWS,
        # 跨包接线状态（3.6b 修订）：读的人据此知道门控类为什么是 unknown。
        "gate_wiring": gate_wiring_status(),
        "classes": classes_out,
        "out_of_class_increment": out_of_class,
        "gaps": gaps,
        "summary": {
            "verdict_counts": verdict_counts,
            "candidate_class_status_counts": _status_counts(classes_out, candidate_names),
            "not_admission_basis": True,
            "note": ("汇总只用于阅读：**逐类 verdict 才是账**。本文件不含分数、加权或排序，"
                     "**不得作为准入依据**（触发集是构造集，见 §边界）。"),
        },
        "boundaries": [
            "触发集是构造集：只证明接线与提供可触发作用面；不得用于效应估计、排序、淘汰或晋级声明。",
            "unknown 表示「该类一个窗口都没判定出来且有窗口不可判定」，**不是**「无影响」，也不得填零。",
            "记录缺口 ≠ 机制稀有：不得用语料频率给机制下稀缺性判断，不得据此做预算规划。",
            "逐类账不得合并成单一总分；汇总字段只供阅读，不得作为准入依据。",
        ],
    }


def _status_counts(classes_out: Sequence[Mapping[str, Any]],
                   candidate_names: Sequence[str]) -> Dict[str, Dict[str, int]]:
    table: Dict[str, Dict[str, int]] = {}
    for name in candidate_names:
        counts: Dict[str, int] = {}
        for entry in classes_out:
            status = entry["candidates"][name]["status"]
            counts[status] = counts.get(status, 0) + 1
        table[name] = counts
    return table

# ---------------------------------------------------------------------------
# 7. 静态核对（--check）：官方依据对到指南行、谓词对到源码符号、关系自洽、结算现算
# ---------------------------------------------------------------------------


def resolve(symbol: str) -> Any:
    """解析 `模块:属性` 形式的源码符号；失败抛 ImportError/AttributeError。"""

    module_name, _, attribute = symbol.partition(":")
    module = importlib.import_module(module_name)
    return getattr(module, attribute)


def _dataclass_fields(symbol: str) -> Optional[Tuple[str, ...]]:
    obj = resolve(symbol)
    if dataclasses.is_dataclass(obj):
        return tuple(field.name for field in dataclasses.fields(obj))
    return None


def _source_line(relative: str, line: int) -> Optional[str]:
    path = _project_file(_PROJECT_ROOT, REPO / relative)
    if not path.is_file():
        return None
    lines = path.read_text(encoding="utf-8").splitlines()
    if line < 1 or line > len(lines):
        return None
    return lines[line - 1]


def check_citations(entries: Sequence[Mapping[str, Any]], where: str) -> List[Dict[str, Any]]:
    """逐条核对"文件 + 行号 + 标记"；行号越界或该行不含标记即失败。"""

    failures: List[Dict[str, Any]] = []
    for entry in entries:
        text = _source_line(entry["file"], entry["line"])
        if text is None:
            failures.append({"kind": "citation", "where": where, "file": entry["file"],
                             "line": entry["line"], "reason": "文件缺失或行号越界"})
            continue
        if entry["marker"] not in text:
            failures.append({"kind": "citation", "where": where, "file": entry["file"],
                             "line": entry["line"], "marker": entry["marker"],
                             "reason": "该行不含声明的标记（依据漂移）"})
    return failures


def check_predicate_symbols() -> List[Dict[str, Any]]:
    """每个可判定谓词字段都必须能解析到真实符号与真实字段。"""

    failures: List[Dict[str, Any]] = []
    for item in CLASSES:
        for entry in item["fields"]:
            symbol = entry["symbol"]
            try:
                names = _dataclass_fields(symbol)
            except Exception as exc:
                failures.append({"kind": "symbol", "class_id": item["id"], "symbol": symbol,
                                 "reason": type(exc).__name__ + ": " + str(exc)})
                continue
            if names is None:
                try:
                    resolve(symbol)
                except Exception as exc:
                    failures.append({"kind": "symbol", "class_id": item["id"],
                                     "symbol": symbol,
                                     "reason": type(exc).__name__ + ": " + str(exc)})
                continue
            if entry["field"] not in names:
                failures.append({"kind": "field", "class_id": item["id"], "symbol": symbol,
                                 "field": entry["field"],
                                 "reason": "字段不存在（改名或删除）"})
    return failures


def check_class_structure() -> List[Dict[str, Any]]:
    """id 唯一、kind / sites / predicate_scope 合法、谓词已注册。"""

    failures: List[Dict[str, Any]] = []
    seen: set = set()
    for item in CLASSES:
        cid = item["id"]
        if cid in seen:
            failures.append({"kind": "duplicate_id", "class_id": cid})
        seen.add(cid)
        if item["kind"] not in CLASS_KINDS:
            failures.append({"kind": "class_kind", "class_id": cid, "value": item["kind"]})
        for site in item["sites"]:
            if site not in ACTION_FAMILIES:
                failures.append({"kind": "site", "class_id": cid, "value": site})
        if item["predicate_scope"] not in ("state", "state+sites"):
            failures.append({"kind": "predicate_scope", "class_id": cid,
                             "value": item["predicate_scope"]})
        if cid not in CLASS_PREDICATES:
            failures.append({"kind": "predicate_missing", "class_id": cid})
        if not item["fact_tokens"]:
            failures.append({"kind": "fact_tokens_empty", "class_id": cid})
        if not item["official"] and item["level"] == LEVEL_OFFICIAL:
            failures.append({"kind": "official_basis_missing", "class_id": cid,
                             "reason": "标为官方级别却没有官方依据行"})
    for cid in CLASS_PREDICATES:
        if cid not in seen:
            failures.append({"kind": "predicate_orphan", "class_id": cid})
    return failures


def check_relations() -> List[Dict[str, Any]]:
    """关系目标必须存在；mutex 必须对称；implies 不得成环。"""

    failures: List[Dict[str, Any]] = []
    by_id = {item["id"]: item for item in CLASSES}
    for item in CLASSES:
        for relation in item["relations"]:
            target = relation["target"]
            if target not in by_id:
                failures.append({"kind": "relation_target", "class_id": item["id"],
                                 "target": target})
                continue
            if relation["kind"] not in RELATION_KINDS:
                failures.append({"kind": "relation_kind", "class_id": item["id"],
                                 "value": relation["kind"]})
            if relation["kind"] == "mutex":
                back = [r for r in by_id[target]["relations"]
                        if r["target"] == item["id"] and r["kind"] == "mutex"]
                if not back:
                    failures.append({"kind": "mutex_asymmetry", "class_id": item["id"],
                                     "target": target})
    graph = {item["id"]: [r["target"] for r in item["relations"] if r["kind"] == "implies"]
             for item in CLASSES}
    visiting: set = set()
    done: set = set()

    def walk(node: str, path: List[str]) -> None:
        if node in done:
            return
        if node in visiting:
            failures.append({"kind": "implies_cycle", "path": path + [node]})
            return
        visiting.add(node)
        for nxt in graph.get(node, []):
            walk(nxt, path + [node])
        visiting.discard(node)
        done.add(node)

    for cid in graph:
        walk(cid, [])
    return failures


def gate_wiring_status() -> Dict[str, Any]:
    """三个门控事实的**接线状态**（跨包；3.6b 修订引入，随产物落盘）。

    为什么要有这一段：接线由**另一个包**（3.6d）落地，落地前后本工具的行为不同
    （谓词 None ↔ True/False）。把状态写进产物，读的人才知道"这三类为什么是 unknown"，
    而不是把它读成"机制稀有"或"工具坏了"。
    """

    fields = context_field_names()
    items = []
    for class_id, wired in GATE_FACT_WIRING.items():
        items.append({
            "class_id": class_id,
            "field": wired["field"],
            "symbol": wired["symbol"],
            "kind": wired["kind"],
            "wired_to_context": wired["field"] in fields,
            "wired_by": wired["wired_by"],
            "note": wired["note"],
        })
    return {
        "classes": items,
        "all_wired": all(item["wired_to_context"] for item in items),
        "note": ("未接线的门控类在面板上**不可判定（None）**：未知不填零；"
                 "check_gate_wiring() 会以 gate_wiring_missing 报出（跨包时序依赖，属预期红）。"
                 "**不得**把未接线读成机制稀有，也不得为了变绿而把类改回不可判定。"),
    }


def check_gate_wiring() -> List[Dict[str, Any]]:
    """门控类的**接线极性反转**断言（3.6b 修订，2026-09-16）。

    旧口径：三个门控类标 undecidable，并断言其字段**不在**评分上下文里。
    新口径（3.6d 把三个事实接进 EvaluationContext 之后）：
      · 三个门控类**不得**再标不可判定；
      · 每个类的 fields 必须声明接线契约表里的那个字段（符号 = EvaluationContext）；
      · 每个类必须带 rule_enforcement（规则层强制点的源码符号，逐条可解析）；
      · 字段**必须真的在 EvaluationContext 里**——否则报 gate_wiring_missing 并**非零退出**。
        接线未落地时这条会红：那是**预期**（跨包时序依赖），不是回退接线的理由。

    对**其它**仍标 undecidable 的类，保留旧断言（字段必须确实不在上下文里），
    防止反向漂移：一边说"不可判定"，一边其实已经接线。
    """

    failures: List[Dict[str, Any]] = []
    context_fields = context_field_names()
    for class_id, wired in GATE_FACT_WIRING.items():
        item = next((entry for entry in CLASSES if entry["id"] == class_id), None)
        if item is None:
            failures.append({"kind": "gate_class_missing", "class_id": class_id})
            continue
        if item.get("undecidable"):
            failures.append({"kind": "gate_still_undecidable", "class_id": class_id,
                             "reason": "接线契约要求该类可判定，不得再标不可判定"})
        declared = {(entry["symbol"], entry["field"]) for entry in item["fields"]}
        if (wired["symbol"], wired["field"]) not in declared:
            failures.append({"kind": "gate_field_not_declared", "class_id": class_id,
                             "field": wired["field"], "symbol": wired["symbol"]})
        enforcement = item.get("rule_enforcement")
        if not enforcement:
            failures.append({"kind": "gate_rule_enforcement_missing", "class_id": class_id})
        else:
            failures.extend(check_symbols(enforcement, class_id))
        if wired["field"] not in context_fields:
            failures.append({"kind": "gate_wiring_missing", "class_id": class_id,
                             "field": wired["field"], "symbol": wired["symbol"],
                             "reason": ("3.6d（corpus 包）应把该字段接进 EvaluationContext；"
                                        "未接线时谓词返回 None（未知不填零）")})
    # 其余仍标不可判定的类：保留旧断言（字段必须确实不在评分上下文里）。
    for item in CLASSES:
        if item["id"] in GATE_FACT_WIRING:
            continue
        entry = item.get("undecidable")
        if not entry:
            continue
        for key in ("reason", "missing", "rule_level_enforcement"):
            if key not in entry:
                failures.append({"kind": "undecidable_incomplete", "class_id": item["id"],
                                 "missing_key": key})
        missing = entry.get("missing", {})
        symbol = missing.get("symbol")
        if symbol:
            try:
                names = _dataclass_fields(symbol)
                if names is not None and missing.get("field") not in names:
                    failures.append({"kind": "undecidable_field", "class_id": item["id"],
                                     "symbol": symbol, "field": missing.get("field"),
                                     "reason": "声明的缺失字段在该符号上不存在"})
            except Exception as exc:
                failures.append({"kind": "undecidable_symbol", "class_id": item["id"],
                                 "symbol": symbol,
                                 "reason": type(exc).__name__ + ": " + str(exc)})
        if missing.get("field") in context_fields:
            failures.append({"kind": "undecidable_but_wired", "class_id": item["id"],
                             "field": missing.get("field"),
                             "reason": "该字段已在 EvaluationContext 中，不得再标不可判定"})
        if missing.get("wired_to_context") is not False:
            failures.append({"kind": "undecidable_flag", "class_id": item["id"]})
        for source in entry.get("rule_level_enforcement", ()):
            failures.extend(check_symbols([source], item["id"]))
    return failures


def check_symbols(entries: Sequence[Mapping[str, Any]], where: str) -> List[Dict[str, Any]]:
    failures: List[Dict[str, Any]] = []
    for entry in entries:
        try:
            resolve(entry["symbol"])
        except Exception as exc:
            failures.append({"kind": "symbol", "where": where, "symbol": entry["symbol"],
                             "reason": type(exc).__name__ + ": " + str(exc)})
    return failures


def check_source_symbols() -> List[Dict[str, Any]]:
    """类与分量声明的实现侧符号必须全部可解析。"""

    failures: List[Dict[str, Any]] = []
    for item in CLASSES:
        failures.extend(check_symbols(item["source"], item["id"]))
    for item in COMPONENTS:
        failures.extend(check_symbols(item["source"], item["id"]))
    for item in KNOWN_GAPS:
        failures.extend(check_symbols(item["source"], item["id"]))
    for symbol, _note in SYM_SHARED_ANCHORS:
        failures.extend(check_symbols([{"symbol": symbol, "note": _note}], "shared_anchor"))
    return failures


def check_components() -> List[Dict[str, Any]]:
    """每个分量绑定的类必须存在；每个场景类必须至少被一个分量（或门控）登记。"""

    failures: List[Dict[str, Any]] = []
    known = set(CLASS_IDS)
    bound: set = set()
    for item in COMPONENTS:
        for cid in item["classes"]:
            if cid not in known:
                failures.append({"kind": "component_binding", "component": item["id"],
                                 "class_id": cid})
            bound.add(cid)
    for cid in CLASS_IDS:
        if cid not in bound:
            failures.append({"kind": "class_unbound", "class_id": cid,
                             "reason": "没有任何分量（含门控）登记该类"})
    return failures


def check_weight_fields() -> List[Dict[str, Any]]:
    """**不得按场景类拍权重**：清单与矩阵里不得出现权重类字段。"""

    failures: List[Dict[str, Any]] = []
    forbidden = set(WEIGHT_POLICY["forbidden_fields"])

    def walk(node: Any, path: str) -> None:
        if isinstance(node, Mapping):
            for key, value in node.items():
                if key in forbidden:
                    failures.append({"kind": "weight_field", "path": path + "." + str(key)})
                walk(value, path + "." + str(key))
        elif isinstance(node, (list, tuple)):
            for index, value in enumerate(node):
                walk(value, path + "[" + str(index) + "]")

    walk(CLASSES, "CLASSES")
    walk(COMPONENTS, "COMPONENTS")
    return failures


def check_pay_roles() -> List[Dict[str, Any]]:
    """支付角色组合：全交叉必须齐备，系数必须由 settlement **现算**核对。"""

    from hangma_bot.hangma.settlement import settle_scores

    failures: List[Dict[str, Any]] = []
    seen = {(row["self_role"], row["winner_role"]) for row in PAY_ROLE_COMBOS}
    for self_role in ("dealer", "nondealer"):
        for winner_role in ("self", "dealer", "other_nondealer"):
            if (self_role, winner_role) not in seen:
                failures.append({"kind": "pay_combo_missing", "self_role": self_role,
                                 "winner_role": winner_role})
    fan, base = 6, 3
    for row in PAY_ROLE_COMBOS:
        self_seat = 0
        dealer_seat = 0 if row["self_role"] == "dealer" else 1
        if row["winner_role"] == "self":
            winner_seat = self_seat
        elif row["winner_role"] == "dealer":
            winner_seat = dealer_seat
        else:
            winner_seat = next(seat for seat in range(4)
                               if seat != self_seat and seat != dealer_seat)
        vector = settle_scores(fan, base, winner_seat, dealer_seat)
        coefficient = vector[self_seat] / float(base * fan)
        if abs(coefficient - row["coefficient"]) > 1e-9:
            failures.append({"kind": "pay_coefficient", "combo": row["id"],
                             "declared": row["coefficient"], "computed": coefficient})
        if row["class_id"] not in CLASS_IDS:
            failures.append({"kind": "pay_class", "combo": row["id"],
                             "class_id": row["class_id"]})
    return failures


def check_risk_cells() -> List[Dict[str, Any]]:
    """冻结风险表必须仍是**庄闲通用价**（dealer=None）：与缺口清单的陈述一致。"""

    failures: List[Dict[str, Any]] = []
    try:
        cells = resolve(SYM_RISK_CELLS)
    except Exception as exc:
        return [{"kind": "risk_cells", "reason": type(exc).__name__ + ": " + str(exc)}]
    for index, cell in enumerate(cells):
        dealer = getattr(cell, "dealer", "missing")
        if dealer is not None:
            failures.append({"kind": "risk_cells_dealer", "index": index, "dealer": dealer,
                             "reason": "冻结表应为庄闲通用价（dealer=None）"})
    return failures


def check_min_windows() -> List[Dict[str, Any]]:
    """类覆盖下限必须与门禁 `G2_MIN_FIRED_WINDOWS` 同值（防两处漂移）。"""

    try:
        gates = _tool("sitin_gates")
    except Exception as exc:
        return [{"kind": "gates_load", "reason": type(exc).__name__ + ": " + str(exc)}]
    if gates.G2_MIN_FIRED_WINDOWS != MIN_CLASS_WINDOWS:
        return [{"kind": "min_windows", "ours": MIN_CLASS_WINDOWS,
                 "gates": gates.G2_MIN_FIRED_WINDOWS}]
    return []


def check() -> List[Dict[str, Any]]:
    """全部静态核对；返回失败清单（空表示通过）。"""

    failures: List[Dict[str, Any]] = []
    for item in CLASSES:
        failures.extend(check_citations(item["official"], item["id"]))
    for item in COMPONENTS:
        failures.extend(check_citations(item["official"], "component:" + item["id"]))
    for item in KNOWN_GAPS:
        failures.extend(check_citations(item["citations"], item["id"]))
    failures.extend(check_predicate_symbols())
    failures.extend(check_class_structure())
    failures.extend(check_relations())
    failures.extend(check_gate_wiring())
    failures.extend(check_source_symbols())
    failures.extend(check_components())
    failures.extend(check_weight_fields())
    failures.extend(check_pay_roles())
    failures.extend(check_risk_cells())
    failures.extend(check_min_windows())
    return failures


def citation_count() -> int:
    """本次核对的行级依据条数（供 --check 输出对账）。"""

    total = sum(len(item["official"]) for item in CLASSES)
    total += sum(len(item["official"]) for item in COMPONENTS)
    total += sum(len(item["citations"]) for item in KNOWN_GAPS)
    return total


# ---------------------------------------------------------------------------
# 6.5 **效果层 / 预算层**（与覆盖账**分列、分标题、互不污染**）
#
# 用途（Lead 2026-09-16 裁定）：覆盖账判"好坏中的坏"（接线 / 覆盖 / 越界 / 证据充分），
# 强度只能靠结算；但覆盖账应当**反过来指导把桌赛的钱花在哪**。本节就是那一列。
#
# **硬约束**：本节的任何数字（出现率、无差别类、活跃分量分布）**只用于效果层与预算分配**，
# **不得回改、不得支撑任何覆盖判定**。覆盖仍按规则可枚举度量、与语料频率无关。
# 代码层保证：`coverage_ledger` **不接受**本节数据作参数
# （见 test_effect_layer_cannot_feed_coverage）。
#
# 两条纪律必须同时成立、互不污染：
#   ① **记录缺口 ≠ 机制稀有**：不得用语料频率给机制下稀缺性判断，也不得据此做预算规划；
#   ② 但"该类出现率低 ⇒ 其强度无法用有限桌数分辨"是**效果层的合法事实**。
# ---------------------------------------------------------------------------

#: "该分量在本窗口有没有翻转余地"的类映射（**只服务效果层**，不参与覆盖判定）。
COMPONENT_ACTIVITY_CLASSES: Mapping[str, Tuple[str, ...]] = {
    "branch": ("branch.chiitoi_live", "branch.luxury_locked", "branch.closer_seven_pairs"),
    "chain": ("chain.open", "chain.gang_step", "chain.gang_draw_open",
              "chain.piao_discard", "chain.break_discard"),
    "four_white": ("four_white.at_four",),
    "baotou": ("baotou.active",),
}

#: 效果层的用途声明（与产物一起落盘，防止这一列被拿去改覆盖判定）。
EFFECT_LAYER_PURPOSE: str = (
    "本节只用于**效果层与预算分配**（把桌赛的钱花在哪）；不得回改、不得支撑任何覆盖判定；"
    "覆盖仍按规则可枚举度量、与语料频率无关。")

#: 条件化评估的硬要求（特殊局要评强度只能这样做）。
CONDITIONAL_EVALUATION_REQUIREMENTS: Tuple[str, ...] = (
    "预先冻结采样规则与种子（不得按候选表现挑局面）；",
    "局面选取规则与候选身份一起落盘，先冻结后运行；",
    "结论只落在**条件效应**上，不外推整体积分；",
    "样本不足时输出未分辨，而不是用点估计宣称强弱。",
)


def active_components(in_class: Sequence[str]) -> Tuple[str, ...]:
    """本窗口上"有翻转余地"的分量名（按 COMPONENT_ACTIVITY_CLASSES 判定）。"""

    present = set(in_class)
    return tuple(name for name, class_ids in COMPONENT_ACTIVITY_CLASSES.items()
                 if present & set(class_ids))


def effect_layer(input_info: Mapping[str, Any], evaluation: Mapping[str, Any],
                 candidate_names: Sequence[str]) -> Dict[str, Any]:
    """效果层/预算层报告：逐类出现率 + 逐类信息量预判 + 用途结论。

    **输入与覆盖账共用**同一次 evaluate_panel（同一批窗口、同一次运行），
    但输出对象**完全独立**：覆盖判定读不到这里的任何数字。
    """

    records = evaluation["records"]
    aggregate = aggregate_records(records, candidate_names)
    total = len(records)

    per_class: List[Dict[str, Any]] = []
    for item in CLASSES:
        cid = item["id"]
        bucket = aggregate["classes"][cid]
        numerator = bucket["windows_in_class"]
        changed = {name: bucket["candidates"][name]["changed"] for name in candidate_names}
        fired = {name: bucket["candidates"][name]["fired"] for name in candidate_names}
        per_class.append({
            "class_id": cid,
            "name": item["name"],
            "numerator": numerator,
            "denominator": total,
            "rate": (numerator / float(total)) if total else None,
            "undecided": bucket["windows_undecided"],
            "changed_by_candidate": changed,
            "fired_by_candidate": fired,
            "discriminating": any(changed.values()),
            "note": ("出现率只用于效果层与预算分配；**不得**回改覆盖判定，"
                     "也不得读成机制稀有。"),
        })

    patterns: Dict[Tuple[str, ...], int] = {}
    for record in records:
        key = active_components(record["in_class"])
        patterns[key] = patterns.get(key, 0) + 1
    pattern_rows = []
    for key in sorted(patterns, key=lambda item: (-patterns[item], item)):
        pattern_rows.append({
            "active_components": list(key),
            "windows": patterns[key],
            "share": (patterns[key] / float(total)) if total else None,
        })
    plain = patterns.get(("branch",), 0)

    indifferent = [entry["class_id"] for entry in per_class
                   if entry["numerator"] > 0 and not entry["discriminating"]]
    discriminating = [entry["class_id"] for entry in per_class if entry["discriminating"]]

    return {
        "title": "效果层 / 预算层（**不是**覆盖判定）",
        "purpose": EFFECT_LAYER_PURPOSE,
        "hard_constraint": ("本节数字只用于效果层与预算分配：不得回改、不得支撑任何覆盖判定。"
                            "coverage_ledger 不接受本节数据作参数（代码层保证）。"),
        "input": dict(input_info),
        "panel": dict(evaluation["panel"]),
        "per_class": per_class,
        "active_component_patterns": pattern_rows,
        "plain_games": {
            "definition": "只有分支分量活跃（链 / 四白 / 爆头三个分量在本窗口都没有翻转余地）",
            "windows": plain,
            "denominator": total,
            "share": (plain / float(total)) if total else None,
        },
        "information_prejudgement": {
            "discriminating_classes": discriminating,
            "indifferent_classes": indifferent,
            "basis": ("判据是**可复算的**：本语料上该类里六个静态注册候选的改选数是否全为 0；"
                      "全为 0 的类对现有候选是**无差别类**（提供的是噪声，不是强度证据）。"),
            "note": ("链条 / 四白 / 爆头三个分量在普通局里恒不活跃时，只有分支分量活着 ⇒ "
                     "这类局对多数候选是**无差别局**。"),
        },
        "conclusion": {
            "plain_vs_special": ("**普通局可以评强度、特殊局多半只能评行为**：特殊类出现太少、"
                                 "在有限桌数内攒不够样本 ⇒ 其强度无法分辨。"),
            "conditional_evaluation": list(CONDITIONAL_EVALUATION_REQUIREMENTS),
            "not_rareness": ("本节的低出现率**只**说明效果层样本不足，**不**构成"
                             "「机制稀有」的判断，也不得据此做预算规划（记录缺口 ≠ 机制稀有）。"),
        },
    }


def render_effect_layer_markdown(data: Mapping[str, Any]) -> str:
    """人读效果层报告；与 JSON 同源，标题写明用途。"""

    lines = [
        "# 坐隐 3.0 效果层 / 预算层（**不是**覆盖判定）",
        "",
        "> " + data["purpose"],
        "> " + data["hard_constraint"],
        "",
        "## 1. 逐类出现率（真实语料分布）",
        "",
        "| 类 | 出现窗口（分子） | 计分窗口（分母） | 出现率 | 不可判定 | 有改选的候选 |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for entry in data["per_class"]:
        holders = [name for name, changed in entry["changed_by_candidate"].items() if changed]
        rate = entry["rate"]
        lines.append("| `{0}` | {1} | {2} | {3} | {4} | {5} |".format(
            entry["class_id"], entry["numerator"], entry["denominator"],
            ("{0:.4%}".format(rate) if rate is not None else "—"), entry["undecided"],
            ", ".join(holders) or "—"))
    lines += ["", "## 2. 活跃分量分布（普通局 vs 特殊局）", "",
              "| 活跃分量 | 窗口 | 占比 |", "| --- | --- | --- |"]
    for row in data["active_component_patterns"]:
        share = row["share"]
        lines.append("| {0} | {1} | {2} |".format(
            "+".join(row["active_components"]) or "（无）", row["windows"],
            ("{0:.4%}".format(share) if share is not None else "—")))
    plain = data["plain_games"]
    lines += ["",
              "**普通局**（{0}）：{1} / {2}（{3}）".format(
                  plain["definition"], plain["windows"], plain["denominator"],
                  ("{0:.4%}".format(plain["share"]) if plain["share"] is not None else "—")),
              "",
              "## 3. 信息量预判（可复算）", "",
              "判据：{0}".format(data["information_prejudgement"]["basis"]),
              "",
              "- **可分辨类**：{0}".format(
                  ", ".join(data["information_prejudgement"]["discriminating_classes"]) or "—"),
              "- **无差别类**：{0}".format(
                  ", ".join(data["information_prejudgement"]["indifferent_classes"]) or "—"),
              "",
              "## 4. 用途结论", "",
              "- {0}".format(data["conclusion"]["plain_vs_special"]),
              "- 特殊局的强度只能做**条件化评估**："]
    for item in data["conclusion"]["conditional_evaluation"]:
        lines.append("  - {0}".format(item))
    lines += ["- {0}".format(data["conclusion"]["not_rareness"]), ""]
    return chr(10).join(lines)



def class_matrix(coverage: Mapping[str, Any]) -> Dict[str, Any]:
    """**分量—场景类矩阵**：逐候选 × 逐类给出"是否声明覆盖 / 触发数 / 改选数 / 证据状态"。

    口径与覆盖账**同一份数据**（`coverage_ledger` 的输出），不另算一套：
      declared    = 静态弱声明（scope ∩ 判定位点 ≠ ∅ 且源码含事实记号）；
      undeclared  = 没有声明覆盖该类（派单要求的显式标记）；
      fired/changed = 本面板该类窗口上候选给出非零增量 / 改变首选的窗口数；
      status      = 证据状态（undeclared / no_window / no_fire / fired_no_change / changed）。

    **只描述现状与缺口，不给效果结论。**
    """

    classes = coverage["classes"]
    names = sorted({name for entry in classes for name in entry["candidates"]})
    rows: List[Dict[str, Any]] = []
    for name in names:
        cells: Dict[str, Any] = {}
        counts: Dict[str, int] = {}
        for entry in classes:
            cell = entry["candidates"][name]
            cells[entry["id"]] = {
                "declared": cell["declared"],
                "status": cell["status"],
                "fired_windows": cell["fired_windows"],
                "changed_windows": cell["changed_windows"],
                "token_hit": cell["token_hit"],
                "scope_hit": cell["scope_hit"],
            }
            counts[cell["status"]] = counts.get(cell["status"], 0) + 1
        rows.append({
            "candidate": name,
            "declared_classes": sum(1 for cell in cells.values() if cell["declared"]),
            "undeclared_classes": sum(1 for cell in cells.values() if not cell["declared"]),
            "status_counts": counts,
            "cells": cells,
        })
    return {
        "schema": "sitin-scenario-class-matrix/1",
        "class_ids": [entry["id"] for entry in classes],
        "candidates": rows,
        "legend": {
            "undeclared": "候选没有声明覆盖该类（派单口径：无声明即标 undeclared）",
            "no_window": "本面板该类一个窗口都没有（**不是**机制稀有的结论）",
            "no_fire": "类内有窗口但候选一次都没给出非零调整",
            "fired_no_change": "触发过但没改变首选",
            "changed": "触发且改变了首选",
        },
        "note": ("矩阵只描述**现状与缺口**，不给任何效果结论；数字由 coverage.json 同一份"
                 "逐窗口记录聚合而来，可用 --coverage 复算。"),
    }


def render_matrix_markdown(matrix: Mapping[str, Any]) -> str:
    """人读矩阵：行=候选，列=类；单元格=证据状态（触发/改选）。"""

    class_ids = matrix["class_ids"]
    short = {cid: cid.split(".", 1)[0][:4] + "." + cid.split(".", 1)[1][:10] for cid in class_ids}
    lines = [
        "# 坐隐 3.0 分量—场景类矩阵（逐候选 × 逐类）",
        "",
        "> 由 [tools/sitin_scenario_classes.py](../../tools/sitin_scenario_classes.py) 生成，",
        "> 与 coverage.json 同一份数据；单元格 = 证据状态（触发/改选）。",
        "> **只描述现状与缺口，不给效果结论。**",
        "",
        "## 1. 候选汇总",
        "",
        "| 候选 | 声明覆盖类数 | 未声明类数 | 证据状态分布 |",
        "| --- | --- | --- | --- |",
    ]
    for row in matrix["candidates"]:
        lines.append("| {0} | {1} | {2} | {3} |".format(
            row["candidate"], row["declared_classes"], row["undeclared_classes"],
            ", ".join("{0}={1}".format(key, value)
                      for key, value in sorted(row["status_counts"].items()))))
    lines += ["", "## 2. 逐类单元格（undeclared 用 — 表示）", "",
              "| 候选 | " + " | ".join(short[cid] for cid in class_ids) + " |",
              "| --- | " + " | ".join("---" for _ in class_ids) + " |"]
    for row in matrix["candidates"]:
        cells = []
        for cid in class_ids:
            cell = row["cells"][cid]
            if not cell["declared"]:
                cells.append("—")
            else:
                cells.append("{0}/{1} {2}".format(cell["fired_windows"],
                                                  cell["changed_windows"], cell["status"]))
        lines.append("| {0} | {1} |".format(row["candidate"], " | ".join(cells)))
    lines += ["", "## 3. 列名对照", "",
              "| 简写 | 完整类 id |", "| --- | --- |"]
    for cid in class_ids:
        lines.append("| {0} | `{1}` |".format(short[cid], cid))
    lines += ["", "## 4. 证据状态定义", "",
              "| 状态 | 含义 |", "| --- | --- |"]
    for key, value in sorted(matrix["legend"].items()):
        lines.append("| {0} | {1} |".format(key, value))
    lines += ["", matrix["note"], ""]
    return chr(10).join(lines)


# ---------------------------------------------------------------------------
# 8. 机读产物与人读渲染
# ---------------------------------------------------------------------------

#: 与产物一起引用的边界（**任何引用本清单的地方都必须带上**）。
BOUNDARIES: Tuple[str, ...] = (
    "触发集是构造集：只证明接线与提供可触发作用面；不得用于效应估计、排序、淘汰或晋级声明。",
    "unknown 表示「该类一个窗口都没判定出来且有窗口不可判定」，**不是**「无影响」，也不得填零。",
    "记录缺口 ≠ 机制稀有：不得用语料频率给机制下稀缺性判断，不得据此做预算规划。",
    "逐类账不得合并成单一总分；汇总字段只供阅读，不得作为准入依据。",
    "庄闲/支付倍率是一等场景维度，但不是番型分量：它不改变同一手内的番型排序。",
)


def _jsonable(value: Any) -> Any:
    """把元组递归转成列表，保证产物是严格 JSON。"""

    if isinstance(value, Mapping):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value


def catalog() -> Dict[str, Any]:
    """机读清单：类、分量、支付角色组合、权重纪律、缺口与边界。"""

    guide_path = _project_file(_PROJECT_ROOT, REPO / GUIDE)
    lines = guide_path.read_text(encoding="utf-8").splitlines() if guide_path.is_file() else []
    digest = (hashlib.sha256(guide_path.read_bytes()).hexdigest()
              if guide_path.is_file() else None)
    return {
        "schema": SCHEMA,
        "guide": {"file": GUIDE, "lines": len(lines), "sha256": digest,
                  "note": "所有官方依据都必须对到本文件的**行号 + 该行标记**（--check）。"},
        "class_ids": list(CLASS_IDS),
        "classes": _jsonable(CLASSES),
        "components": _jsonable(COMPONENTS),
        "pay_role_combos": _jsonable(PAY_ROLE_COMBOS),
        "weight_policy": _jsonable(WEIGHT_POLICY),
        "known_gaps": _jsonable(known_gap_entries()),
        "min_class_windows": MIN_CLASS_WINDOWS,
        # 跨包接线状态（3.6b 修订）：门控三类由"不可判定"改为"已接线 ⇒ 有谓词"，
        # 这里把**当前有没有真的接线**一并落盘（未接线时谓词为 None，未知不填零）。
        "gate_wiring": gate_wiring_status(),
        # 出处与依赖（3.6b 返工，Challenger risk ③ + info）：这两条是"结论必须一起引用"的事实，
        # 因此写进**生成器**而不是手写进产物，重跑 --emit 不会丢。
        "provenance": {
            "wiring_dependency": {
                "what": ("三个门控类的「已接线 ⇒ 可判定」要求 EvaluationContext 带 "
                         "you_cai_bi_kao / remaining_tile_count / catch_play_owner_seat"),
                "landed_in": ("提交 13543459（3.6d，corpus 包）；"
                              "src/hangma_bot/policy/evaluation_v1.py sha256 b3198fcfc030a235…"),
                "first_commit_of_this_list": ("081be82f（3.6b）：evaluation_v1.py sha256 "
                                              "ff620155626ab91a… ⇒ --check 报 3×field + "
                                              "3×gate_wiring_missing、exit 2 —— 该提交**不自洽**"),
                "green_since": ("≥13543459 的 HEAD；tests 产物 raw/check.txt 的 exit=0 取自该状态"),
                "note": ("跨提交依赖必须与结论一起引用；不得回退接线，也不得把三类改回不可判定。"
                         "复现见 review/llm-guided-heuristic-route-2026-09-15/evidence/"
                         "3.6b-perclass/raw/52-check-at-081be82f.txt"),
            },
            "you_cai_bi_kao_source": {
                "what": "gate.you_cai_bi_kao 的取值来自**面板声明参数**，不是从记录反推",
                "evidence": ("决策行携带该开关 0 / 359,262（canonical 面板 panel-canonical-20260910）；"
                             "运行级清单 runs/{run_id}/manifest.json 98/100 在场且**全为 false**，"
                             "true 样本 0（详见 3.6d 的 run-facts 探针）"),
                "consequence": ("该门控类在面板上恒 not_applicable 是**面板参数**的结果，"
                                "不得读成机制稀缺；需要 true 侧样本时用 --you-cai-bi-kao true 复跑"),
                "cross_check": ("面板自洽核对 legal_reconciliation（本地规则重算 == 记录落盘合法候选）"
                                "见同批次覆盖账产物"),
            },
        },
        "verdicts": {
            "sufficient": "该类判定出的窗口数 >= min_class_windows",
            "insufficient": "该类有窗口，但少于下限（证据不足，不是无影响）",
            "unknown": "一个窗口都没判定出来且有窗口不可判定（不得填零、不得并入 not_applicable）",
            "not_applicable": "可判定且一个窗口都不属于该类",
        },
        "boundaries": list(BOUNDARIES),
        "counts": {"classes": len(CLASSES), "components": len(COMPONENTS),
                   "pay_role_combos": len(PAY_ROLE_COMBOS), "known_gaps": len(KNOWN_GAPS),
                   "citations": citation_count()},
    }


def render_provenance_markdown(provenance: Mapping[str, Any]) -> List[str]:
    """出处与依赖段（跨提交依赖 + 面板声明参数）：**必须与清单一起读**。"""

    wiring = provenance.get("wiring_dependency", {})
    switch = provenance.get("you_cai_bi_kao_source", {})
    return [
        "## 出处与依赖（必须与清单一起读）",
        "",
        "### 1. 跨提交依赖：门控类的「已接线 ⇒ 可判定」",
        "",
        "| 项 | 值 |",
        "| --- | --- |",
        "| 依赖什么 | {0} |".format(wiring.get("what")),
        "| 接线落在 | {0} |".format(wiring.get("landed_in")),
        "| 本清单首次落盘的提交 | {0} |".format(wiring.get("first_commit_of_this_list")),
        "| 什么时候为绿 | {0} |".format(wiring.get("green_since")),
        "",
        wiring.get("note", ""),
        "",
        "### 2. gate.you_cai_bi_kao 的取值来自面板声明参数",
        "",
        "| 项 | 值 |",
        "| --- | --- |",
        "| 口径 | {0} |".format(switch.get("what")),
        "| 证据 | {0} |".format(switch.get("evidence")),
        "| 读法 | {0} |".format(switch.get("consequence")),
        "| 旁证 | {0} |".format(switch.get("cross_check")),
        "",
    ]


def render_catalog_markdown(data: Mapping[str, Any]) -> str:
    """人读清单；与 JSON 同源。"""

    lines = [
        "# 坐隐 3.0 评分相关场景类清单（规则可枚举）",
        "",
        "> 由 [tools/sitin_scenario_classes.py](../../tools/sitin_scenario_classes.py) 生成；",
        "> 每条官方依据都指向指南**行号与标记**，每条谓词都指向**源码符号与字段**，",
        "> `--check` 逐条解析，依据漂移或字段改名即失败。",
        "> **口径**：覆盖按规则可枚举场景度量，**与语料频率无关**；下表不含任何效果结论。",
        "",
    ]
    lines += render_provenance_markdown(data.get("provenance", {}))
    lines += [
        "## 1. 分量 → 场景类绑定",
        "",
        "| 分量 | 名称 | 证据 | 量纲 | 绑定的场景类 |",
        "| --- | --- | --- | --- | --- |",
    ]
    for item in data["components"]:
        lines.append("| {0} | {1} | {2} | {3} | {4} |".format(
            item["id"], item["name"], item["level"], item["unit"],
            ", ".join(item["classes"])))
    lines += ["",
              "**权重纪律**：{0}".format(data["weight_policy"]["verdict"]),
              "",
              "## 2. 场景类",
              "",
              "| id | 名称 | 种类 | 证据 | 判定位点 | 谓词 | 关系 |",
              "| --- | --- | --- | --- | --- | --- | --- |"]
    for item in data["classes"]:
        relations = ", ".join("{0} {1}".format(r["kind"], r["target"])
                              for r in item["relations"]) or "—"
        lines.append("| `{0}` | {1} | {2} | {3} | {4} | {5} | {6} |".format(
            item["id"], item["name"], item["kind"], item["level"],
            "+".join(item["sites"]) or "—", item["predicate_text"], relations))
    lines += ["", "## 3. 支付角色组合（现算核对）", "",
              "| 组合 | 本人角色 | 胡家 | 系数（本人净增量 / 底分×番） | 归属类 |",
              "| --- | --- | --- | --- | --- |"]
    for row in data["pay_role_combos"]:
        lines.append("| {0} | {1} | {2} | {3} | `{4}` |".format(
            row["id"], row["self_role"], row["winner_role"], row["coefficient"],
            row["class_id"]))
    lines += ["", "## 4. 有据可查的现存缺口", "",
              "| 缺口 | 涉及类 | 依据（文件:行） | 前置条件 |",
              "| --- | --- | --- | --- |"]
    for item in data["known_gaps"]:
        citations = "; ".join("{0}:{1}".format(c["file"], c["line"])
                              for c in item["citations"])
        lines.append("| {0} | {1} | {2} | {3} |".format(
            item["title"], ", ".join(item["class_ids"]), citations,
            item.get("precondition") or "—"))
    lines += ["", "## 5. 边界（必须与清单一起引用）", ""]
    for index, text in enumerate(data["boundaries"], start=1):
        lines.append("{0}. {1}".format(index, text))
    lines.append("")
    return chr(10).join(lines)


def render_coverage_markdown(data: Mapping[str, Any]) -> str:
    """人读覆盖账；与 JSON 同源。"""

    summary = data["summary"]
    lines = [
        "# 坐隐 3.0 逐类覆盖账（构造触发集）",
        "",
        "> 由 [tools/sitin_scenario_classes.py](../../tools/sitin_scenario_classes.py) 生成。",
        "> **逐类出账，不得合并成单一总分**；汇总只供阅读，**不得作为准入依据**。",
        "",
        "## 1. 输入与面板",
        "",
        "| 项 | 值 |",
        "| --- | --- |",
        "| 输入 | `{0}` |".format(data["input"].get("path")),
        "| 行数 / 计分窗口 | {0} / {1} |".format(
            data["panel"]["rows_total"], data["panel"]["scored"]),
        "| 构造集 | {0} |".format(data["input"].get("constructed")),
        "| 证据类别 | {0} |".format(data["input"].get("evidence_kind")),
        "| 对账（总行 = 排除 + 失败 + 计分） | {0} |".format(data["panel"]["reconciles"]),
        "| 覆盖下限 | {0} |".format(data["min_class_windows"]),
        "| 门控事实接线（跨包） | {0} |".format(
            "全部已接线" if data.get("gate_wiring", {}).get("all_wired") else
            "**未全部接线** ⇒ 未接线的门控类在面板上不可判定（None），未知不填零"),
        "",
        "## 2. 逐类覆盖（四态）",
        "",
        "| 类 | 四态 | 类内窗口 | 不可判定 | 类外窗口 | 候选（触发/改选） |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for entry in data["classes"]:
        detail = ", ".join(
            "{0} {1}/{2} ({3})".format(name, item["fired_windows"],
                                       item["changed_windows"], item["status"])
            for name, item in sorted(entry["candidates"].items()))
        lines.append("| `{0}` | **{1}** | {2} | {3} | {4} | {5} |".format(
            entry["id"], entry["verdict"], entry["windows_in_class"],
            entry["windows_undecided"], entry["windows_out_of_class"], detail))
    lines += ["", "## 3. 类外零增量核对", "",
              "| 候选 | 声明类数 | 改选窗口 | 类外改选 | 归属未知 |",
              "| --- | --- | --- | --- | --- |"]
    for name, item in sorted(data["out_of_class_increment"].items()):
        lines.append("| {0} | {1} | {2} | {3} | {4} |".format(
            name, len(item["declared_classes"]), item["changed_windows"],
            item["violation_total"], item["undecided_change_total"]))
    lines += ["", "## 4. 缺口清单", "",
              "| 类型 | 缺口 | 涉及类 | 所需事实是否已接线 |", "| --- | --- | --- | --- |"]
    for gap in data["gaps"]:
        if gap["kind"] == "class_gap":
            lines.append("| 类缺口 | {0}（{1}） | `{2}` | {3} |".format(
                gap["class_name"], "+".join(gap["reasons"]), gap["class_id"],
                gap["required_fact"]["wired"]))
        else:
            lines.append("| 已知缺口 | {0} | {1} | {2} |".format(
                gap["title"], ", ".join(gap["class_ids"]),
                gap["fact_wiring"]["wired"]))
    lines += ["", "## 5. 边界（必须与账一起引用）", ""]
    for index, text in enumerate(data["boundaries"], start=1):
        lines.append("{0}. {1}".format(index, text))
    lines.append("")
    return chr(10).join(lines)


def load_rows(path: Path, limit: Optional[int] = None) -> List[dict]:
    """读取 JSONL（触发集或语料）；与门禁同口径复用 `sitin_gates.load_corpus`。

    输入也可以是**语料清单**（多文件面板，见 `sitin_gates.CORPUS_MANIFEST_SCHEMA`）：
    清单把"选了哪些文件、各多少行、各是什么哈希、按什么规则挑的"一起落盘，
    从而让"先冻结选择规则、后运行"这件事**可复核**。
    """

    return _tool("sitin_gates").load_corpus(path, limit=limit)


def iter_rows(path: Path, limit: Optional[int] = None) -> Iterator[dict]:
    """**惰性**读取 JSONL / 语料清单（每次只持有一行）。

    canonical 面板（105 份 / 359,262 行）把行全部物化约需 28 GB（实测 82 KB/行），
    因此覆盖账走本入口：逐行 yield，交给 `evaluate_panel` 的单次遍历。
    """

    for row in _tool("sitin_gates").iter_corpus(path, limit=limit):
        yield row


def scan_corpus(path: Path, limit: Optional[int] = None) -> Dict[str, Any]:
    """**先扫一遍**：行数 + 是否构造集（fail-closed 的屏障先于计分，见 `--coverage`）。

    它只做解析与标记检查，不跑任何候选；代价是再读一次 JSONL（canonical 面板约 1—2 分钟）。
    """

    rows = 0
    constructed = False
    for row in iter_rows(path, limit=None):
        rows += 1
        if not constructed and isinstance(row.get("trigger_grid"), Mapping):
            constructed = True
        if limit is not None and rows >= limit:
            break
    return {"rows": rows, "constructed": constructed}


def manifest_info(path: Path) -> Optional[Dict[str, Any]]:
    """输入是语料清单时返回可复核摘要（否则 None）；摘要随产物落盘。"""

    manifest = _tool("sitin_gates").corpus_manifest(path)
    if manifest is None:
        return None
    return {
        "schema": manifest.get("schema"),
        # 面板身份四件套（F7）：panel_id + 指纹 + 行数 + record_layer_filled。
        # 摘要必须**原样透传**清单里的口径声明，否则调用方会以为面板没有声明视图。
        "panel_id": manifest.get("panel_id"),
        "panel_role": manifest.get("panel_role"),
        "record_layer": manifest.get("record_layer"),
        "record_layer_filled": manifest.get("record_layer_filled"),
        "record_layer_source": manifest.get("record_layer_source"),
        "fingerprint": manifest.get("fingerprint"),
        "canonical_panel": manifest.get("canonical_panel"),
        "row_cap": manifest.get("row_cap"),
        "rows": manifest.get("rows"),
        # 排除账（整文件行数）：纳入 + 排除 = 家族总行数；引用面板时必须能一起给。
        "excluded_rows": manifest.get("excluded_rows"),
        "excluded_ratio": manifest.get("excluded_ratio"),
        "family_rows": manifest.get("family_rows"),
        "family_files": manifest.get("family_files"),
        "cross_package": manifest.get("cross_package"),
        "files": manifest.get("files"),
        "selection_rule": manifest.get("selection_rule"),
        "frozen_before_run": manifest.get("frozen_before_run"),
        "generator": manifest.get("generator"),
        "note": ("清单在**运行前**冻结：文件按路径升序整份取，不按候选表现挑语料；"
                 "引用时必须写明 panel_id + 指纹 + 行数 + 是否记录层归一化。"),
    }


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="坐隐 3.0 评分相关场景类清单与逐类覆盖账")
    ap.add_argument("--check", action="store_true", help="静态核对（依据行 / 源码符号 / 结算现算）")
    ap.add_argument("--emit", default=None, help="写出机读清单（目录或 .json 路径）")
    ap.add_argument("--coverage", action="store_true", help="在 --input 上逐类出账")
    ap.add_argument("--effect-layer", dest="effect_layer", action="store_true",
                    help="效果层/预算层：逐类出现率 + 信息量预判（**只对真实语料**；"
                         "不得回改覆盖判定）")
    ap.add_argument("--input", default=None, help="输入 JSONL（触发集或真实语料）")
    ap.add_argument("--out", default=None,
                    help="产物目录（coverage.json / COVERAGE.md / effect-layer.json / EFFECT-LAYER.md）")
    ap.add_argument("--candidates", default="",
                    help="逗号分隔的候选名（缺省=注册表里的全部静态注册候选）")
    ap.add_argument("--limit", type=int, default=None, help="最多计分窗口数")
    ap.add_argument("--ruleset", default=PANEL_RULESET,
                    help="面板规则语义版本（新语料自带 hangma-mvp-v10-public-counts；"
                         "缺省 {0} = 历史面板口径）".format(PANEL_RULESET))
    ap.add_argument("--you-cai-bi-kao", dest="you_cai_bi_kao",
                    choices=("true", "false", "unknown"), default=None,
                    help="面板的「有财必拷响」开关（面板声明参数；unknown = 上下文取 None）")
    ap.add_argument("--record-layer", dest="record_layer", choices=list(RECORD_LAYER_MODES),
                    default=None,
                    help="记录层视图：缺省 = 清单声明的视图（canonical 面板声明 filled），再退回 raw")
    ap.add_argument("--evidence-kind", default=None, choices=["trigger", "admission"],
                    help="证据类别；构造集不得标为 admission（拒绝而不是静默降级）")
    args = ap.parse_args(argv)

    failures = check()
    for item in failures:
        print("FAIL {0}".format(json.dumps(item, ensure_ascii=False)))
    print("核对 {0} 条行级依据 + {1} 条类结构/符号/关系/结算，失败 {2} 条".format(
        citation_count(), len(CLASSES), len(failures)))
    if args.check and not (args.emit or args.coverage or args.effect_layer):
        return 2 if failures else 0

    if args.emit:
        data = catalog()
        target = Path(args.emit)
        if target.suffix == ".json":
            _write(target, json.dumps(data, ensure_ascii=False, indent=2) + chr(10))
            print("已写出 {0}".format(target))
        else:
            _write(target / "scenario-classes.json",
                   json.dumps(data, ensure_ascii=False, indent=2) + chr(10))
            _write(target / "CLASSES.md", render_catalog_markdown(data))
            print("已写出 {0}".format(target))

    if args.coverage or args.effect_layer:
        if not args.input:
            print("--coverage / --effect-layer 需要 --input")
            return 2
        input_path = Path(args.input)
        # **先扫一遍**（fail-closed）：构造集标记必须在计分之前判掉。
        # 这一步也为**惰性**遍历铺路：canonical 面板 359,262 行全物化约 28 GB。
        scan = scan_corpus(input_path, limit=args.limit)
        constructed = scan["constructed"]
        evidence_kind = args.evidence_kind or ("trigger" if constructed else "admission")
        if constructed and evidence_kind == "admission":
            print("拒绝：输入是构造触发集（带 trigger_grid 标记），不得标为 admission 证据")
            return 2
        if args.candidates:
            candidate_names = tuple(item.strip() for item in args.candidates.split(",")
                                    if item.strip())
        else:
            candidate_names = _registry().candidate_names()
        you_cai_bi_kao = {"true": True, "false": False, "unknown": None,
                          None: PANEL_YOU_CAI_BI_KAO}[args.you_cai_bi_kao]
        # 记录层视图：显式参数优先；否则取**清单自己声明的视图**（canonical 面板声明 filled），
        # 再退回 raw。两者不一致时只警告不拒绝——"同一面板换个视图再跑一遍"正是前后对比的用法。
        manifest = manifest_info(input_path)
        declared_layer = (manifest or {}).get("record_layer")
        record_layer = args.record_layer or declared_layer or RECORD_LAYER_RAW
        if declared_layer and record_layer != declared_layer:
            print("提示：清单声明 record_layer={0}，本次按 {1} 运行（前后对比可如此，引用时不得混用分母）".format(
                declared_layer, record_layer))
        # **一次运行、两个互不污染的输出**：覆盖账与效果层共用同一批窗口；
        # 输入走**惰性**遍历，raw 诊断折进同一次遍历（不再二次读入）。
        evaluation = evaluate_panel(iter_rows(input_path, limit=args.limit), candidate_names,
                                    limit=args.limit, ruleset=args.ruleset,
                                    you_cai_bi_kao=you_cai_bi_kao,
                                    record_layer=record_layer)
        input_info = {
            "path": str(input_path),
            # 语料清单（多文件面板）时，这里哈希的是**清单**：清单里逐文件带 sha256，
            # 因此它同样钉住了内容身份（换任何一份文件都会改清单）。
            "sha256": hashlib.sha256(input_path.read_bytes()).hexdigest(),
            "rows": evaluation["panel"]["rows_total"],
            "constructed": constructed,
            "evidence_kind": evidence_kind,
            # 记录层视图（F7）：canonical 面板 = filled；raw = 它的前态。**两者不得混用分母**。
            "record_layer": record_layer,
            "raw_coverage": evaluation["panel"]["raw_coverage"],
        }
        if manifest is not None:
            input_info["manifest"] = manifest
            # 面板身份的四件套（F7）：panel_id + 指纹 + 行数 + 是否记录层归一化。
            input_info["panel_identity"] = {
                "panel_id": manifest.get("panel_id") or "(未声明 panel_id)",
                "fingerprint": input_info["sha256"],
                "rows": input_info["rows"],
                "record_layer_filled": record_layer == RECORD_LAYER_FILLED,
                "record_layer": record_layer,
            }
        out = Path(args.out) if args.out else None
        if args.coverage:
            data = coverage_ledger(input_info, evaluation, candidate_names)
            data["boundaries"] = list(BOUNDARIES)
            text = json.dumps(data, ensure_ascii=False, indent=2) + chr(10)
            matrix = class_matrix(data)
            if out:
                _write(out / "coverage.json", text)
                _write(out / "COVERAGE.md", render_coverage_markdown(data))
                _write(out / "matrix.json",
                       json.dumps(matrix, ensure_ascii=False, indent=2) + chr(10))
                _write(out / "MATRIX.md", render_matrix_markdown(matrix))
                print("已写出 {0}".format(out))
            else:
                print(text)
        if args.effect_layer:
            if constructed:
                print("拒绝：出现率只对**真实语料**有意义（构造触发集不是分布抽样， "
                      "用它的频率指导预算就是放开了准入口径）")
                return 2
            effect = effect_layer(input_info, evaluation, candidate_names)
            text = json.dumps(effect, ensure_ascii=False, indent=2) + chr(10)
            if out:
                _write(out / "effect-layer.json", text)
                _write(out / "EFFECT-LAYER.md", render_effect_layer_markdown(effect))
                print("已写出 {0}".format(out))
            else:
                print(text)
    return 2 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())












