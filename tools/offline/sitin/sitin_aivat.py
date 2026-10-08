# -*- coding: utf-8 -*-
"""AIVAT 旁路净效率实验（v4 合同 §12 六步验收；批次 7b）。

规范来源：review/llm-guided-heuristic-route-2026-09-15/SEARCH-SPACE-REDESIGN-2026-09-16.md
§12（AIVAT 独立增强：默认关闭、旁路报告、只使用同一终端效用 U 的配对差、
不先校正积分再阈值化）与 [AIVAT 论文](https://arxiv.org/html/1612.06915)
（按精确已知概率构造零均值校正；扑克降方差倍数不可移植）。

核心构造（零均值可证，Doob 补偿子式，不需要整棵博弈树）：
  - 机会节点 = 洗牌根的牌墙（simulation-v1:deal-v1，每局均匀随机排列）；
  - 对焦点座位每次**实际摸牌** j：S_j = 该次摸牌前暗牌（不含摸牌）在唯一
    规则源 analyse_hand 下的有效牌集合；W_j = 摸牌前未消费牌墙多重集
    （可摸区 wall[wall_front:wall_back] + 保留区 wall[round_start_wall_back:]
    + 本次摸牌本身；含保留区因为游标位置与一切未见位置可交换）；
  - p_j = |S_j ∩ W_j| / |W_j| 是**精确已知**的条件概率（均匀洗牌下任一
    未消费物理位置的牌在剩余多重集上均匀）；hit_j = 1{摸到的牌 ∈ S_j}；
  - Z = Σ hit_j（进张命中数，定义在**实际摸牌序列**上——策略改变吃碰杠会
    改变摸牌位置与次数，因此两臂同根天然牌墙相同而 Z 可分叉，不落入
    "两臂相同校正相消"）；A = Σ p_j（补偿子，沿各臂实际轨迹求值）；
  - M = Z − A 对**任意**行为策略期望恰为 0（每次摸牌项的条件期望为 0，
    求和与有界停时保持零期望；见 FROZEN-DESIGN.md 论证）；
  - d_adj(r) = d_raw(r) − c×(M_cand(r) − M_base(r))；c 在 fit 根上冻结，
    测量用新独立根（§12 步骤 3 分离）。

红线（机器可核）：
  - 校正只作用于同一终端效用 U 的配对差（u_low/u_high 识别区间原样保留，
    未分辨样本不计点值、不平均、不删根；不先校正积分再阈值化）；
  - Z/A 只在模拟边界内**事后统计**（AivatSpyEngine 只读包装组合根引擎，
    不进策略输入、不改任何窗口决策——单测断言有无侦察引擎逐决策一致）；
  - AIVAT 结果只写入 evidence/v4-impl/batch7b/，不进 LLM 反馈、档案排序
    或发布结论（不改任何现有文件；T19 保持）；
  - 全部真实桌赛记 ActionValueLedger（授权 batch=7 fail-closed）；
    本批 tables_full 总额 ≤ AIVAT_BATCH_TABLE_CAP=256（预留前机器核对）；
  - **统计单位 = 来源根**（主合同 §12）：R 的方差、标准误与 bootstrap 都在
    "每根 4 换座先取均值"的**根观测**上计算，座位行不是独立观测——同一根的
    四个换座高度相关，把座位行当独立样本会把方差/标准误算小（评审 v4 §5 口径
    修正；根聚合见 root_observations/_r_core）。
  - **合并口径同样是来源根、一根一票**（R6 复审 §5 M3）：先把根内各策略对
    聚合成一根一个观测，再算合并方差/区间/bootstrap；(pair, root) 单元不是
    独立观测，复制逐行相同的策略对不得提高有效样本量或缩窄区间
    （见 pooled_root_observations 与 POOLED_ESTIMAND）。

用法（六步验收，详见 evidence/v4-impl/batch7b/FROZEN-DESIGN.md）：

    .venv/bin/python review/llm-guided-heuristic-route-2026-09-15/tools/sitin_aivat.py toy-verify
    .venv/bin/python review/llm-guided-heuristic-route-2026-09-15/tools/sitin_aivat.py fit \
        --authorization .team-work/tasks/sitin-phase3-v4/llm-authorization.json
    .venv/bin/python review/llm-guided-heuristic-route-2026-09-15/tools/sitin_aivat.py measure \
        --authorization .team-work/tasks/sitin-phase3-v4/llm-authorization.json
    .venv/bin/python review/llm-guided-heuristic-route-2026-09-15/tools/sitin_aivat.py report
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
import random
import statistics
import sys
import time
from collections import Counter
from dataclasses import dataclass
from itertools import permutations
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

REPO = _PROJECT_ROOT
_HERE = Path(__file__).resolve().parent
for _entry in (str(_project_file(_PROJECT_ROOT, REPO / "src")), str(_HERE)):
    if _entry not in sys.path:
        sys.path.insert(0, _entry)

import sitin_stage as stage  # noqa: E402
import sitin_natural_panel as natp  # noqa: E402
from hangma_bot.hangma.hand_analysis import analyse_hand  # noqa: E402
from hangma_bot.hangma.interface import ValueAnalysisLimits  # noqa: E402
from hangma_bot.kernel.config import RuleConfig, TimingConfig, TournamentConfig  # noqa: E402
from hangma_bot.offline.evaluate import (  # noqa: E402
    BOOTSTRAP_RUNTIME_HOOK,
    MatchDriverConfig,
    MatchExperiment,
    MatchSeedSpec,
    PolicyDeclaration,
    StageSituationProjection,
    build_match_result,
    drive_match,
    seat_policies_from,
)
from hangma_bot.offline.evaluation_results import compute_rules_hash  # noqa: E402
from hangma_bot.simulation.shuffle import RESERVE_TILES  # noqa: E402

#: 产物 schema。
AIVAT_SCHEMA = "sitin-aivat/1"
#: 本批（batch7b）真实桌赛实例硬上限（红线：fit+measure 合计 ≤ 256）。
AIVAT_BATCH_TABLE_CAP = 256.0
#: fit 根 = batch7 自然面板根（panel_seed 20260916，H/M 各 root 1）。
FIT_PANEL_SEED = int(natp.DEFAULT_PANEL_SEED)
#: 测量根 = 新独立保留根（panel_seed 20260917，H/M 各 root 1..3；与 fit 不同源）。
MEASURE_PANEL_SEED = 20260917
#: fit/测量根清单（冻结于 FROZEN-DESIGN.md；measure 启动前机器核对与 fit 不相交）。
FIT_MIX_ROOTS: Dict[str, List[int]] = {"H": [1], "M": [1]}
MEASURE_MIX_ROOTS: Dict[str, List[int]] = {"H": [1, 2, 3], "M": [1, 2, 3]}
#: 策略对：候选源 = batch7 真实 I1/M1 生成物；基线 = weighted_heuristic_v2。
PAIR_SOURCES: Dict[str, str] = {
    "i1-vs-v2": "evidence/v4-impl/batch7/gen/i1/attempts/i1-641296497a9b/candidate.py",
    "m1-vs-v2": "evidence/v4-impl/batch7/gen/m1/attempts/m1-d68785b86751/candidate.py",
}
#: 证据目录（相对仓库根）。
EVIDENCE_DIR = "review/llm-guided-heuristic-route-2026-09-15/evidence/v4-impl/batch7b"
#: 路线目录（PAIR_SOURCES 等路线内相对路径的锚点）。
ROUTE_DIR = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15')
#: bootstrap 固定种子（可复跑）。
BOOTSTRAP_SEED = 20260917
BOOTSTRAP_DRAWS = 10000
#: 统计单位标记：统计量（方差/标准误/bootstrap）的输入是**根观测**（每来源根一个），
#: 不是座位行（评审 v4 §5 口径修正；见 root_observations）。
ROOT_OBSERVATION_KIND = "aivat-root-observation/1"
#: 每根应有座位行数（seats_per_root 的契约值；缺座位时聚合仍在 n_seats 里明示）。
SEATS_PER_ROOT = 4
#: 合并（跨策略对）口径的观测标记：根内各策略对先聚合，一根只留**一个**观测；
#: 复制完全相同的策略对因此不增加独立观测（R6 复审 §5 M3）。
POOLED_PAIR_LABEL = "__pooled_across_pairs__"
#: 合并口径的估计目标声明（先定义目标再选口径；原样写入报告供审计）。
POOLED_ESTIMAND: Dict[str, Any] = {
    "quantity": "各来源根上「根内各策略对配对差等权平均」的均值"
                 "（配对差 d_raw = U_candidate − U_baseline，同一终端效用 U）",
    "unit": "来源根",
    "within_root_weighting": "同一根内各策略对等权（先按对取根均值，再对该根各对取均值）",
    "cost_unit": "一个观测 = 在该根上跑完该根全部策略对的双臂成本之和"
                 "（R 为比值，成本口径必须与观测单位一致）",
    "why_not_cells": "(pair, root) 单元不是独立观测：把它们当独立样本会"
                     "重现座位行口径错误——复制策略对会让标准误除以 √(2n)、"
                     "并按 ddof 把样本方差压小（复审 §5 M3：0.251106 应为 0.372450）",
    "duplicate_pair_invariance": "复制完全相同的策略对不增加独立观测：点估计、"
                                 "方差、区间与 R 均不变（同一根只贡献一个观测）",
}


def evidence_path(*parts: str) -> Path:
    return _project_file(_PROJECT_ROOT, REPO / EVIDENCE_DIR / Path(*parts))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2)
                    + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# 1. 校正核心：单次摸牌的命中指示与精确条件概率（玩具/引擎共用唯一实现）
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DrawMoment:
    """一次焦点摸牌的 AIVAT 统计：hit、精确条件概率 p 与牌墙计数事实。"""

    hit: bool
    p: float
    drawn_code: str
    effective_codes: Tuple[str, ...]
    effective_in_wall: int  # |S_j ∩ W_j|（分子）
    wall_remaining: int  # |W_j|（分母；含保留区与本次摸牌）


def draw_moment(effective_codes: Sequence[str],
                remaining_without_drawn: Mapping[str, int],
                drawn_code: str) -> DrawMoment:
    """摸牌校正统计的唯一实现（玩具过程与引擎侦察共用，不设第二套公式）。

    remaining_without_drawn：摸牌前未消费牌墙**不含本次摸牌**的多重集计数
    （引擎口径 = 可摸区 + 保留区；W_j = remaining ∪ {drawn}）。
    p = |S ∩ W_j| / |W_j|，在均匀洗牌下是该游标位置命中 S 的精确条件概率。
    """
    remaining = Counter(remaining_without_drawn)
    remaining[drawn_code] += 1
    total = sum(remaining.values())
    effective = frozenset(effective_codes)
    hits = sum(count for code, count in remaining.items() if code in effective)
    probability = (float(hits) / float(total)) if total > 0 else 0.0
    return DrawMoment(hit=drawn_code in effective, p=probability,
                      drawn_code=drawn_code, effective_codes=tuple(sorted(effective)),
                      effective_in_wall=int(hits), wall_remaining=int(total))


# ---------------------------------------------------------------------------
# 2. 玩具过程（步骤 2 可穷举验证；结构对齐真实引擎：双游标+保留区+策略敏感摸牌）
# ---------------------------------------------------------------------------

#: 玩具牌墙 = **单一排列**（与真实引擎同构）：前 TOY_DRAWABLE_LEN 张可摸，
#: 末 2 张保留区永不摸但与可摸区同属一次洗牌——p_j 分母必须含保留区，
#: 因为游标位置与一切未见位置（含保留区）可交换（步骤 2 曾拦截过
#: "保留区独立洗牌"的错误玩具结构：那会令 p_j 与真实抽牌概率不一致）。
TOY_WALL_CODES = ("A", "A", "B", "B", "C", "C", "E", "F")
TOY_DRAWABLE_LEN = 6
#: 玩具终局条件：暗牌保留 3 张即"胡"（U=1），可摸区耗尽未胡 U=0。
TOY_WIN_HAND = 3


def toy_effective_codes(hand: Mapping[str, int]) -> Tuple[str, ...]:
    """玩具有效牌集合：暗牌中恰持 1 张的种类（凑对推进）。"""

    return tuple(sorted(code for code, count in hand.items() if count == 1))


def toy_keep(policy: str, hand: Mapping[str, int], drawn: str, draws: int) -> bool:
    """玩具策略——是否保留摸到的牌（策略敏感：改变后续 S_j 与胡牌时点）。"""

    effective = set(toy_effective_codes(hand))
    if policy == "pair_seeker":
        return drawn in effective
    if policy == "hoarder":
        return True
    if policy == "discarder":
        return False
    if policy == "late_seeker":
        return drawn in effective or draws >= 3
    raise ValueError("未知玩具策略 {0!r}".format(policy))


def toy_meld(policy: str, hand: Mapping[str, int], draws: int) -> Optional[str]:
    """玩具策略——是否把一对暗牌副露（触发补牌端摸牌，策略敏感摸牌位置）。"""

    pairs = [code for code, count in sorted(hand.items()) if count >= 2]
    if policy in ("pair_seeker", "hoarder") and pairs and draws >= 1:
        return pairs[0]
    if policy == "discarder" and pairs and draws >= 4:
        return pairs[0]
    if policy == "late_seeker" and pairs and draws >= 2:
        return pairs[0]
    return None


def toy_play(wall: Sequence[str], drawable_len: int, policy: str) -> Dict[str, Any]:
    """跑一局玩具过程，返回 (z, a, m, u, 逐次摸牌统计)。

    wall 是**完整单一排列**：前 drawable_len 张为可摸区，其余为保留区
    （永不摸）。摸牌结构对齐真实引擎：普通摸牌从前端游标、副露补牌从
    可摸区尾端游标；W_j = 可摸区剩余 ∪ 保留区 ∪ {本次摸牌}（游标位置
    与一切未见位置可交换——保留区必须计入 p_j 的分母，这是引擎同构点）。
    """

    wall = list(wall)
    front = 0
    back = int(drawable_len)
    hand: Counter = Counter()
    melds = 0
    draws = 0
    z = 0
    a = 0.0
    moments: List[Dict[str, Any]] = []
    replacement = False
    win = False
    while front < back:
        if replacement:
            index = back - 1
            back -= 1
        else:
            index = front
            front += 1
        replacement = False
        drawn = wall[index]
        effective = toy_effective_codes(hand)
        remaining: Counter = (Counter(wall[front:back])
                              + Counter(wall[drawable_len:]))
        moment = draw_moment(effective, remaining, drawn)
        z += int(moment.hit)
        a += moment.p
        draws += 1
        moments.append({"hit": int(moment.hit), "p": round(moment.p, 9),
                        "drawn": drawn,
                        "effective": list(moment.effective_codes),
                        "wall_remaining": moment.wall_remaining})
        meld_code = toy_meld(policy, hand, draws)
        if meld_code is not None:
            hand[meld_code] -= 2
            if hand[meld_code] <= 0:
                del hand[meld_code]
            melds += 1
            replacement = True
            continue
        if toy_keep(policy, hand, drawn, draws):
            hand[drawn] += 1
            if sum(hand.values()) >= TOY_WIN_HAND:
                win = True
                break
    return {"policy": policy, "z": z, "a": a, "m": z - a, "u": 1 if win else 0,
            "draws": draws, "melds": melds, "moments": moments}


def toy_distinct_permutations(multiset: Sequence[str]) -> List[Tuple[str, ...]]:
    return sorted(set(permutations(multiset)))


def toy_enumerate(wall_codes: Sequence[str], drawable_len: int,
                  policy: str) -> Dict[str, Any]:
    """全置换枚举：E[Z] 与 E[A] 的精确值（样本均值接近不是无偏证明）。"""

    perms = toy_distinct_permutations(wall_codes)
    runs = [toy_play(perm, drawable_len, policy) for perm in perms]
    mean_z = sum(run["z"] for run in runs) / len(runs)
    mean_a = sum(run["a"] for run in runs) / len(runs)
    mean_u = sum(run["u"] for run in runs) / len(runs)
    return {"policy": policy, "n_permutations": len(perms),
            "mean_z": mean_z, "mean_a": mean_a,
            "abs_mean_m": abs(mean_z - mean_a), "mean_u": mean_u}


def toy_verify_all(wall_codes: Sequence[str] = TOY_WALL_CODES,
                   drawable_len: int = TOY_DRAWABLE_LEN) -> Dict[str, Any]:
    """步骤 2 全套可穷举验证（写证据 JSON 的同一入口；单测复用）。"""

    checks: List[Dict[str, Any]] = []
    policies = ("pair_seeker", "hoarder", "discarder", "late_seeker")
    # (a) 每个确定性策略 E[Z − A] = 0 精确成立。
    for policy in policies:
        stats = toy_enumerate(wall_codes, drawable_len, policy)
        checks.append({
            "name": "zero_mean_exact:{0}".format(policy),
            "pass": stats["abs_mean_m"] < 1e-9,
            "detail": {"mean_z": stats["mean_z"], "mean_a": stats["mean_a"],
                       "n_permutations": stats["n_permutations"]},
        })
    # (b) 行为策略混合（随机化策略）按线性性保持零期望：混合期望 = 期望混合。
    half = toy_enumerate(wall_codes, drawable_len, "pair_seeker")
    other = toy_enumerate(wall_codes, drawable_len, "hoarder")
    mixed_m = 0.5 * (half["mean_z"] - half["mean_a"]) + 0.5 * (
        other["mean_z"] - other["mean_a"])
    checks.append({"name": "zero_mean_behavioral_mixture_linearity",
                   "pass": abs(mixed_m) < 1e-9,
                   "detail": {"mixed_mean_m": mixed_m}})
    # (c) 确定性机会（整墙单一种类）下校正恒 0：p ∈ {0,1} 且与命中逐点相等。
    # 注：不能构造"可摸区全 A + 保留区含 E,F"——单一均匀排列下该事件概率为 0，
    # 洗牌横跨可摸区与保留区全部位置；机会退化只能来自整墙单一多重集。
    degenerate = ("A",) * 10
    degenerate_ok = True
    for policy in policies:
        for perm in toy_distinct_permutations(degenerate):
            run = toy_play(perm, 8, policy)
            if abs(run["m"]) > 1e-12:
                degenerate_ok = False
    checks.append({"name": "deterministic_chance_correction_identically_zero",
                   "pass": degenerate_ok,
                   "detail": {"wall": "A×10（可摸 8 + 保留 2）", "policies": list(policies)}})
    # (d) 两臂同策略（确定性动作相同）时校正差恒 0（相同轨迹逐点相消）。
    same_policy_zero = all(
        abs(toy_play(perm, drawable_len, pol)["m"]
            - toy_play(perm, drawable_len, pol)["m"]) < 1e-12
        for pol in policies for perm in toy_distinct_permutations(wall_codes))
    checks.append({"name": "identical_arms_correction_difference_zero",
                   "pass": same_policy_zero,
                   "detail": {"note": "同策略两臂同轨迹 ⇒ M 差恒 0"}})
    # (e) 配对差口径：E[d_adj] = E[d_raw] 精确成立（c 取 0.5 的演示值）。
    c_demo = 0.5
    base_stats = toy_enumerate(wall_codes, drawable_len, "hoarder")
    cand_stats = toy_enumerate(wall_codes, drawable_len, "pair_seeker")
    mean_d_raw = cand_stats["mean_u"] - base_stats["mean_u"]
    perms = toy_distinct_permutations(wall_codes)
    d_adj_sum = 0.0
    for perm in perms:
        cand = toy_play(perm, drawable_len, "pair_seeker")
        base = toy_play(perm, drawable_len, "hoarder")
        d_raw = cand["u"] - base["u"]
        d_adj_sum += d_raw - c_demo * (cand["m"] - base["m"])
    mean_d_adj = d_adj_sum / len(perms)
    checks.append({"name": "paired_difference_unbiasedness",
                   "pass": abs(mean_d_adj - mean_d_raw) < 1e-9,
                   "detail": {"mean_d_raw": mean_d_raw, "mean_d_adj": mean_d_adj,
                              "c_demo": c_demo}})
    # (f) 策略敏感性：存在同牌墙下两策略 Z 不同的置换（Z 定义在实际摸牌序列）。
    strategy_sensitive = any(
        toy_play(perm, drawable_len, "pair_seeker")["z"]
        != toy_play(perm, drawable_len, "hoarder")["z"]
        for perm in perms)
    checks.append({"name": "z_defined_on_actual_draws_policy_sensitive",
                   "pass": strategy_sensitive,
                   "detail": {"note": "同根不同策略可产生不同实际摸牌序列 ⇒ Z 可分叉"}})
    return {"schema": AIVAT_SCHEMA, "step": "2-zero-expectation-verification",
            "toy": {"wall_codes": list(wall_codes),
                    "drawable_len": int(drawable_len),
                    "reserve_len": len(wall_codes) - int(drawable_len),
                    "enumeration": "全置换精确枚举（样本均值接近不作证据）"},
            "checks": checks, "all_pass": all(item["pass"] for item in checks)}


# ---------------------------------------------------------------------------
# 3. 引擎旁路统计：AivatSpyEngine（只读包装组合根引擎；不改现有文件）
# ---------------------------------------------------------------------------


class AivatSpyEngine:
    """只读侦察引擎：委托全部推进，仅在焦点摸牌窗口事后统计 Z/A。

    信息分区（红线）：牌墙真值与四家暗牌只在本类内部用于统计校正，
    不进入任何策略输入；frame/advance/start 原样透传，世界对象即内部
    引擎对象（不复制、不改写）。单测断言有无本包装逐决策一致。
    """

    def __init__(self, inner: Any, focal_seat: int) -> None:
        self.inner = inner
        self.focal_seat = int(focal_seat)
        self.rounds: Dict[int, Dict[str, Any]] = {}
        self._seen: set = set()
        self.stats_ms = 0.0
        self.wrapper_ms = 0.0
        self.inner_ms = 0.0

    # —— 委托接口（drive_match 只使用这三个方法）——

    def start(self, spec: Any) -> Any:
        began = time.perf_counter()
        world = self.inner.start(spec)
        self.inner_ms += time.perf_counter() - began
        try:
            self._observe(world)
        finally:
            self.wrapper_ms += time.perf_counter() - began
        return world

    def frame(self, world: Any) -> Any:
        return self.inner.frame(world)

    def advance(self, world: Any, revision: int, choices: Any) -> Any:
        began = time.perf_counter()
        next_world = self.inner.advance(world, revision, choices)
        self.inner_ms += time.perf_counter() - began
        try:
            self._observe(next_world)
        finally:
            self.wrapper_ms += time.perf_counter() - began
        return next_world

    # —— 统计（只读）——

    def _observe(self, world: Any) -> None:
        state = world.progression
        if state.window != "draw" or state.turn_seat != self.focal_seat:
            return
        seat = state.seats[self.focal_seat]
        if seat.drawn is None:
            return  # 碰/吃后的出牌窗口：无实际摸牌（drawn 为空），不计 Z。
        key = (int(world.round_no), int(world.revision))
        if key in self._seen:
            return
        self._seen.add(key)
        began = time.perf_counter()
        summary = analyse_hand(seat.hand, len(seat.melds))
        effective = tuple(sorted({item.code for item in summary.useful_tiles}))
        drawable_remaining = Counter(
            tile.code for tile in world.wall[world.wall_front:world.wall_back])
        reserve_remaining = Counter(
            tile.code for tile in world.wall[world.round_start_wall_back:])
        moment = draw_moment(
            effective, drawable_remaining + reserve_remaining, seat.drawn.code)
        self.stats_ms += (time.perf_counter() - began) * 1000.0
        record = self.rounds.setdefault(int(world.round_no), {
            "draws": 0, "z": 0, "a": 0.0, "p_values": [], "hits": []})
        record["draws"] += 1
        record["z"] += int(moment.hit)
        record["a"] += moment.p
        record["p_values"].append(round(moment.p, 6))
        record["hits"].append(int(moment.hit))

    def aggregates(self) -> Dict[str, Any]:
        rounds = {str(no): dict(data) for no, data in sorted(self.rounds.items())}
        z = sum(data["z"] for data in self.rounds.values())
        a = sum(data["a"] for data in self.rounds.values())
        return {"focal_seat": self.focal_seat, "draws": sum(
            data["draws"] for data in self.rounds.values()),
            "z": z, "a": round(a, 9), "m": round(z - a, 9),
            "rounds": rounds, "stats_ms": round(self.stats_ms, 3),
            "wrapper_overhead_ms": round(
                max(0.0, (self.wrapper_ms - self.inner_ms) * 1000.0
                    - self.stats_ms), 3)}


# ---------------------------------------------------------------------------
# 4. 编排：复用自然面板计划/装配，仅替换驱动引擎为侦察包装（外科式注入）
# ---------------------------------------------------------------------------


def execute_table_with_spy(*, plan: Any, policies_by_seat: Sequence[Any],
                           versions_block: Mapping[str, Any], step_limit: int,
                           value_limits: ValueAnalysisLimits,
                           focal_seat: Optional[int] = None,
                           stage_situation: Optional[StageSituationProjection] = None
                           ) -> Dict[str, Any]:
    """与 natp.execute_natural_table 同构的执行，唯一差别：
    focal_seat 非 None 时用 AivatSpyEngine 包装组合根引擎（只读旁路统计）。

    stage_situation（M1 同类缺口的 AIVAT 侧修复）是该桌**开始前**已完成桌账的
    可见投影，与自然面板逐字同约：非 None 时经 drive_match 注入每个座位策略
    请求的 CompetitionContext（策略可见自己座位的阶段积分/名次分与剩余桌数）；
    None 保持旧空上下文（既有单桌调用零变化）。**真实测量路径恒传投影**
    （见 run_arm_stage_aivat）。

    返回 row（同 natp）+ aivat（侦察统计；未启用侦察时为 None）。
    """

    from hangma_bot import bootstrap
    from hangma_bot.application.deadline import BudgetPolicy, ManualClock
    from hangma_bot.hangma.engine import HangmaRules

    rules_config = RuleConfig(ruleset_version=str(versions_block["ruleset_version"]),
                              base_score=int(versions_block["base_score"]),
                              you_cai_bi_kao=bool(versions_block["you_cai_bi_kao"]))
    timing = TimingConfig(**dict(stage.DEFAULT_TIMING))
    tournament_config = TournamentConfig(
        max_games=1, rounds_per_game=int(versions_block["rounds_per_game"]),
        rules=rules_config, timing=timing)
    runtime = getattr(bootstrap, BOOTSTRAP_RUNTIME_HOOK)("matches", MatchExperiment(
        kind="matches", clock_mode=str(versions_block["clock_mode"]),
        baseline=PolicyDeclaration(policy_id="aivat-slot-a", name="panel", weights=()),
        challenger=PolicyDeclaration(policy_id="aivat-slot-b", name="panel", weights=()),
        opponents=tuple(PolicyDeclaration(policy_id="aivat-slot-{0}".format(index),
                                          name="panel", weights=())
                        for index in (3, 4, 5)),
        tournament_config=tournament_config,
        seeds=(MatchSeedSpec(seed=plan.seed, scenario_id=plan.scenario_id),),
        seat_permutations=(stage.IDENTITY_PERMUTATION,), initial_dealer=0,
        initial_scores=(0, 0, 0, 0)))
    if not isinstance(runtime, Mapping):
        raise RuntimeError("组合根未装配 matches 运行时；本工具不伪造模拟引擎")
    clock = ManualClock(start_monotonic=800.0, wait_scale=1.0)
    now_monotonic = (clock.now if str(versions_block["clock_mode"]) == "logical"
                     else time.monotonic)
    rules = HangmaRules(rules_config)
    engine = runtime["engine"]
    spy = AivatSpyEngine(engine, int(focal_seat)) if focal_seat is not None else None
    spec = runtime["spec_factory"](match_id=plan.match_id, scenario_id=plan.scenario_id,
                                   config=tournament_config, seed=plan.seed,
                                   initial_dealer=plan.initial_dealer,
                                   initial_scores=[0, 0, 0, 0])
    version_pairs = [
        ("clock_mode", str(versions_block["clock_mode"])),
        ("driver", "tools/sitin_aivat.py (spy over offline.evaluate drive_match)"),
        ("panel_policy_names", sorted(set(str(name) for name in plan.policy_names))),
        ("rules_hash", compute_rules_hash(REPO)),
        ("ruleset_version", rules_config.ruleset_version),
        ("value_limits", json.dumps({"max_expansions": value_limits.max_expansions,
                                     "max_routes_per_candidate":
                                         value_limits.max_routes_per_candidate},
                                    sort_keys=True)),
    ]
    for seat, policy in enumerate(policies_by_seat):
        version_pairs.append(("natural_seat_policy:{0}".format(seat),
                              str(getattr(policy, "policy_id", type(policy).__name__))))
    started = time.monotonic()
    outcome = asyncio.run(drive_match(
        engine=(spy if spy is not None else engine), spec=spec,
        policies_by_seat=tuple(policies_by_seat), rules=rules,
        choice_factory=runtime["choice_factory"],
        config=MatchDriverConfig(clock_mode=str(versions_block["clock_mode"]),
                                 step_limit=int(step_limit),
                                 budget_policy=BudgetPolicy(),
                                 competition_tournament_id=plan.scenario_id),
        now_monotonic=now_monotonic, wall_clock=None, value_limits=value_limits,
        stage_situation=stage_situation))
    wall_ms = (time.monotonic() - started) * 1000.0
    result = build_match_result(
        match_id=plan.match_id, scenario_id=plan.scenario_id, pair_id=plan.pair_id,
        config=tournament_config, policy_ids_by_seat=plan.seats(),
        seat_permutation=plan.permutation, initial_scores_physical=(0, 0, 0, 0),
        outcome=outcome, versions=tuple(sorted(version_pairs)),
        source_refs=({"note": "aivat bypass measurement table",
                      "producer": "tools/sitin_aivat.py"},),
        result_id="r-" + plan.match_id, source_kind="simulation")
    row = {
        "table_id": plan.table_id,
        "seed": int(plan.seed),
        "match_status": outcome.status,
        "wall_ms": round(wall_ms, 3),
        "scores_by_seat": (None if outcome.final_scores is None
                           else [int(item) for item in outcome.final_scores]),
        "result": result.to_json(),
    }
    return {"row": row, "aivat": (spy.aggregates() if spy is not None else None),
            "outcome": outcome}


def run_arm_stage_aivat(*, arm: str, plans: Sequence[Any], candidate_scorer: Any,
                        opponent_policies: Sequence[str],
                        versions_block: Mapping[str, Any], step_limit: int,
                        value_limits: ValueAnalysisLimits) -> Dict[str, Any]:
    """跑一臂的完整阶段（tables_per_group 桌）+ 逐桌 Z/A 统计与费用。

    与 natp.run_arm_stage 同构（T16 故障隔离、group_advance_utility 求值）；
    差别：每桌按计划轮换的焦点物理座位注入 AivatSpyEngine，并记录
    校正状态求值开销（stats_ms）与包装开销（wrapper_overhead_ms）。

    阶段账注入（M1 同类缺口，契约与自然面板一致、单一实现
    natp.build_stage_situation）：**每桌开始前**按「参赛者身份 → 物理座位」
    注入已完成桌累计积分/名次分（第 1 桌为空账表头），当前桌结果只在其结束后
    并入阶段账（不重复累计）。测量用的执行器因此与正式评估同语义：第 2 桌起
    的策略请求能读到已完成桌账，R 与配对差不来自不一致的 harness。
    """

    from hangma_bot.application.deadline import ManualClock

    record: Dict[str, Any] = {"arm": arm, "status": None, "usable": False,
                              "error": None, "tables": [], "aivat_tables": [],
                              "stage_totals_by_participant": None,
                              "focal_stage_score": None, "u": None, "u_low": None,
                              "u_high": None, "unresolved": None, "elapsed_ms": None,
                              "stats_ms": 0.0, "overhead_ms": 0.0,
                              "z": 0, "a": 0.0, "m": None}
    started = time.monotonic()
    totals: Dict[str, int] = {}
    place_totals: Dict[str, int] = {}
    rounds_per_game = int(versions_block["rounds_per_game"])
    try:
        for table_index, plan in enumerate(plans):
            # M1（P12）：本桌开始前注入**已完成桌**的阶段账（不含当前桌；桌内
            # 结果由驱动的 PlayerObservation.scores 单独维护，不重复累计）。
            situation = natp.build_stage_situation(
                plan=plan, table_no=table_index + 1, tables_completed=table_index,
                totals=totals, place_totals=place_totals,
                rounds_per_game=rounds_per_game)
            clock = ManualClock(start_monotonic=800.0, wait_scale=1.0)
            logical = natp.arm_logical_policies(
                arm=arm, candidate_scorer=candidate_scorer,
                logical_participants=plan.logical_participants,
                opponent_policies=opponent_policies, monotonic=clock.now)
            policies_by_seat = seat_policies_from(
                logical, plan.permutation, plan.logical_participants)
            focal_seat = list(plan.seats()).index(natp.FOCAL_PARTICIPANT)
            executed = execute_table_with_spy(
                plan=plan, policies_by_seat=policies_by_seat,
                versions_block=versions_block, step_limit=step_limit,
                value_limits=value_limits, focal_seat=focal_seat,
                stage_situation=situation)
            row = executed["row"]
            aivat = executed["aivat"]
            table_record = {key: row[key] for key in
                            ("table_id", "seed", "match_status", "wall_ms",
                             "scores_by_seat")}
            # 证据留存：本桌策略实际收到的阶段账投影（与自然面板同口径，可核）。
            table_record["stage_situation"] = situation.to_json()
            record["tables"].append(table_record)
            if aivat is None:
                raise RuntimeError("侦察统计缺失（focal_seat={0}）".format(focal_seat))
            record["aivat_tables"].append({
                "table_id": row["table_id"], "focal_seat": aivat["focal_seat"],
                "draws": aivat["draws"], "z": aivat["z"], "a": aivat["a"],
                "m": aivat["m"], "stats_ms": aivat["stats_ms"],
                "overhead_ms": aivat["wrapper_overhead_ms"],
                "rounds": aivat["rounds"]})
            if row["match_status"] != "complete" or row["scores_by_seat"] is None:
                raise RuntimeError("场次 {0} 未完成（status={1}）".format(
                    row["table_id"], row["match_status"]))
            points = stage.place_points_for_table(row["scores_by_seat"])
            for seat, participant in enumerate(plan.seats()):
                totals[participant] = totals.get(participant, 0) + int(
                    row["scores_by_seat"][seat])
                place_totals[participant] = place_totals.get(participant, 0) + int(
                    points[seat])
        rows = [stage.LedgerRow(participant_id=pid, total_score=totals[pid],
                                place_points=place_totals[pid])
                for pid in sorted(totals)]
        utility = stage.group_advance_utility(rows, focal_id=natp.FOCAL_PARTICIPANT)
        record.update({
            "status": "complete", "usable": True,
            "stage_totals_by_participant": dict(sorted(totals.items())),
            "focal_stage_score": int(totals[natp.FOCAL_PARTICIPANT]),
            "u": (float(utility["u_low"] + utility["u_high"]) / 2.0
                  if utility["u_low"] == utility["u_high"] else None),
            "u_low": float(utility["u_low"]), "u_high": float(utility["u_high"]),
            "unresolved": utility["unresolved"],
        })
    except Exception as error:  # T16：数值保留但不冒充可用
        record["status"] = "error"
        record["error"] = "{0}: {1}".format(type(error).__name__, error)
    record["elapsed_ms"] = round((time.monotonic() - started) * 1000.0, 3)
    if record["aivat_tables"]:
        record["z"] = sum(item["z"] for item in record["aivat_tables"])
        record["a"] = round(sum(item["a"] for item in record["aivat_tables"]), 9)
        record["m"] = round(record["z"] - record["a"], 9)
        record["stats_ms"] = round(sum(item["stats_ms"]
                                       for item in record["aivat_tables"]), 3)
        record["overhead_ms"] = round(sum(item["overhead_ms"]
                                          for item in record["aivat_tables"]), 3)
    return record


def assemble_sample(*, pair_name: str, opponent: str, root_index: int,
                    root_seed: int, panel_seed: int, focal_seat: int,
                    arms: Mapping[str, Mapping[str, Any]],
                    table_ids: Sequence[str]) -> Dict[str, Any]:
    """把双臂阶段记录组装为一个配对样本（识别区间原样保留，不阈值化）。"""

    def view(arm: Mapping[str, Any]) -> Dict[str, Any]:
        return {"status": arm["status"], "usable": arm["usable"],
                "error": arm["error"], "u": arm["u"], "u_low": arm["u_low"],
                "u_high": arm["u_high"], "unresolved": arm["unresolved"],
                "focal_stage_score": arm["focal_stage_score"],
                "z": arm["z"], "a": arm["a"], "m": arm["m"],
                "elapsed_ms": arm["elapsed_ms"], "stats_ms": arm["stats_ms"],
                "overhead_ms": arm["overhead_ms"]}

    baseline, candidate = arms["baseline"], arms["candidate"]
    resolved = all(arm["usable"] and not arm["unresolved"]
                   for arm in (baseline, candidate))
    d_raw = (float(candidate["u"] - baseline["u"]) if resolved else None)
    m_diff = ((round(candidate["m"] - baseline["m"], 9))
              if candidate["m"] is not None and baseline["m"] is not None else None)
    stats_ms = float(baseline["stats_ms"]) + float(candidate["stats_ms"])
    overhead_ms = float(baseline["overhead_ms"]) + float(candidate["overhead_ms"])
    elapsed_ms = float(baseline["elapsed_ms"]) + float(candidate["elapsed_ms"])
    return {
        "schema": AIVAT_SCHEMA, "sample_kind": "aivat-paired-stage/1",
        "pair": pair_name, "opponent_mix": opponent, "root_index": int(root_index),
        "root_id": "{0}-root{1:02d}".format(opponent, int(root_index)),
        "root_seed": int(root_seed), "panel_seed": int(panel_seed),
        "focal_seat": int(focal_seat), "table_ids": list(table_ids),
        "completeness": ("complete" if all(arm["usable"] for arm in arms.values())
                         else "invalid"),
        "resolved": resolved, "d_raw": d_raw, "m_diff": m_diff,
        "cost": {"elapsed_ms": round(elapsed_ms, 3),
                 "stats_ms": round(stats_ms, 3),
                 "overhead_ms": round(overhead_ms, 3),
                 # cost_raw：同一运行去掉校正状态求值开销的反事实成本
                 "cost_raw_sec": round(max(0.0, elapsed_ms - stats_ms - overhead_ms)
                                       / 1000.0, 6),
                 "cost_adjusted_sec": round(elapsed_ms / 1000.0, 6)},
        "arms": {"baseline": view(baseline), "candidate": view(candidate)},
    }


def run_pair_panel(*, pair_name: str, candidate_source: str,
                   contract: Mapping[str, Any], authorization: Mapping[str, Any],
                   panel_seed: int, mixes_roots: Mapping[str, Sequence[int]],
                   phase: str, ledger_path: Optional[Path] = None,
                   seats_per_root: int = 4) -> Dict[str, Any]:
    """一对策略在给定根集上的双臂 AIVAT 样本编排（fit/measure 共用）。"""

    from hangma_bot.policy.action_value_seeds import ActionValueScorer
    from sitin_search import ActionValueLedger

    natp.require_authorization(authorization)
    out_dir = evidence_path(phase, "{0}-{1}".format(
        pair_name, "fit" if phase == "fit" else "measure"))
    scenario_names = {mix: (contract["panel"]["opponent_scenarios"] or {})[mix]
                      for mix in mixes_roots}
    opponent_policies_by_mix = {
        mix: [str(name) for name in block["opponent_policies"]]
        for mix, block in scenario_names.items()}
    versions_block = stage.contract_versions_block(contract)
    value_limits = ValueAnalysisLimits()
    step_limit = int(contract["stop"]["step_limit"])
    tables_per_group = int(contract["group"]["tables_per_group"])
    av_contract_sha = hashlib.sha256(
        (_project_file(_PROJECT_ROOT, REPO / natp.AV_CONTRACT)).read_bytes()).hexdigest()
    # ActionValueScorer 收源码文本（与 natp.run_natural_panel 同口径），此处
    # 由路径读入；路径本身记录进 identity 供追溯。
    candidate_text = Path(candidate_source).read_text(encoding="utf-8")
    scorer = ActionValueScorer("av-candidate", candidate_text)
    candidate_id = scorer.candidate_identity(av_contract_sha)

    ledger = None
    reservations: Dict[str, Any] = {}
    planned_tables = sum(len(roots) for roots in mixes_roots.values()) \
        * int(seats_per_root) * 2 * tables_per_group
    if ledger_path is not None:
        ledger = ActionValueLedger.load(Path(ledger_path))
        already = ledger.spent("tables_full")
        if already + planned_tables > AIVAT_BATCH_TABLE_CAP:
            raise SystemExit(
                "AIVAT 批次桌赛上限拒绝：已记 {0} + 计划 {1} > {2}（fit+measure "
                "合计硬上限）".format(already, planned_tables, AIVAT_BATCH_TABLE_CAP))
        for mix, roots in mixes_roots.items():
            amount = len(roots) * int(seats_per_root) * 2 * tables_per_group
            reservations[mix] = ledger.reserve(
                step_id="aivat:{0}:{1}:{2}".format(phase, pair_name, mix),
                account="tables_full", amount=float(amount),
                note="AIVAT {0}：{1} {2} 根 {3} × {4} 座位 × 2 臂 × {5} 桌".format(
                    phase, pair_name, mix, list(roots), int(seats_per_root),
                    tables_per_group))

    samples: List[Dict[str, Any]] = []
    executed = 0
    for mix, roots in mixes_roots.items():
        opponent_policies = opponent_policies_by_mix[mix]
        for root_index in roots:
            root_seed = natp.natural_root_seed(panel_seed, mix, root_index)
            root_failures: List[str] = []
            for focal_seat in range(int(seats_per_root)):
                plans = natp.build_seat_stage_plans(
                    contract=contract, opponent=mix, root_index=root_index,
                    focal_seat=focal_seat, panel_seed=panel_seed)
                arms = {
                    "baseline": run_arm_stage_aivat(
                        arm="baseline", plans=plans, candidate_scorer=scorer,
                        opponent_policies=opponent_policies,
                        versions_block=versions_block, step_limit=step_limit,
                        value_limits=value_limits),
                    "candidate": run_arm_stage_aivat(
                        arm="candidate", plans=plans, candidate_scorer=scorer,
                        opponent_policies=opponent_policies,
                        versions_block=versions_block, step_limit=step_limit,
                        value_limits=value_limits),
                }
                executed += sum(len(arm["tables"]) for arm in arms.values())
                if not arms["candidate"]["usable"]:
                    root_failures.append("seat{0}: {1}".format(
                        focal_seat, arms["candidate"]["error"]))
                samples.append(assemble_sample(
                    pair_name=pair_name, opponent=mix, root_index=root_index,
                    root_seed=root_seed, panel_seed=panel_seed,
                    focal_seat=focal_seat, arms=arms,
                    table_ids=[plan.table_id for plan in plans]))
            if root_failures:  # T16：候选臂失败 ⇒ 整根 invalid，费用照记
                for sample in samples:
                    if (sample["opponent_mix"] == mix
                            and sample["root_index"] == root_index):
                        sample["completeness"] = "invalid"
                        sample["invalid_reasons"] = [
                            "候选臂执行失败（T16 整根 invalid）：{0}".format(
                                "; ".join(root_failures))]

    if ledger is not None:
        for mix, reservation in reservations.items():
            executed_mix = sum(2 * len(sample["table_ids"])
                               for sample in samples
                               if sample["opponent_mix"] == mix)
            ledger.settle(reservation, actual=float(executed_mix),
                          note="AIVAT {0} {1} {2}：实跑桌赛实例 {3}（失败桌照记）".format(
                              phase, pair_name, mix, executed_mix))
        ledger.save()

    contract_sha = hashlib.sha256(
        json.dumps(contract, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    product = {
        "schema": AIVAT_SCHEMA, "phase": phase,
        "identity": {"pair": pair_name, "candidate_id": candidate_id,
                     "candidate_source": candidate_source,
                     "baseline_id": natp.BASELINE_FOCAL_POLICY,
                     "contract_id": contract.get("contract_id"),
                     "contract_sha256": contract_sha,
                     "panel_seed": int(panel_seed),
                     "panel_epoch": "aivat-{0}-v1@{1}".format(phase, pair_name),
                     # M1/P12：阶段账注入口径（与自然面板同一标识、单一来源）。
                     # 只增不改：既不改 R 口径，也不 bump panel_epoch（根集与
                     # 统计口径未变；既有冻结证据的 epoch 必须保持可对照）。
                     "stage_projection": str(natp.STAGE_ACCOUNT_MODE),
                     "mixes_roots": {mix: list(roots)
                                     for mix, roots in mixes_roots.items()}},
        "config": {"seats_per_root": int(seats_per_root),
                   "tables_per_group": tables_per_group,
                   "opponent_policies": opponent_policies_by_mix,
                   "step_limit": step_limit,
                   "value_limits": {"max_expansions": value_limits.max_expansions,
                                    "max_routes_per_candidate":
                                        value_limits.max_routes_per_candidate}},
        "samples": samples,
        "cost": {"tables_full_planned": planned_tables,
                 "tables_full_executed": executed,
                 "wall_sec": round(sum(sample["cost"]["elapsed_ms"]
                                       for sample in samples) / 1000.0, 3),
                 "correction_stats_sec": round(sum(sample["cost"]["stats_ms"]
                                                   for sample in samples) / 1000.0, 3)},
        "red_lines": {
            "correction_uses_paired_u_only": "d_raw = U_cand − U_base；未分辨区间不计点值",
            "post_hoc_only": "Z/A 只经 AivatSpyEngine 事后统计，不进策略输入",
            "ledger_cap": "fit+measure 合计 tables_full ≤ {0}".format(
                AIVAT_BATCH_TABLE_CAP)},
    }
    write_json(out_dir / "panel.json", product)
    return product


# ---------------------------------------------------------------------------
# 5. 统计：c 冻结（fit 根）、R 计算与簇 bootstrap（§12 步骤 3—5）
# ---------------------------------------------------------------------------


def usable_samples(samples: Sequence[Mapping[str, Any]]) -> List[Mapping[str, Any]]:
    """统计可用样本：completeness=complete 且 resolved（未分辨区间不计点值）。

    本函数只做**行级过滤**：被排除的行（未分辨/不完整）原样留在 samples 里，
    但一旦 len(samples) > len(usable)，剩余行就不再是原抽样的完整根集——
    "保留原始行"不等于统计里没有被删根。因此调用方（r_measurement_report）
    必须在 n_excluded > 0 时**阻断点值 R**，只报告 n_excluded 与阻断原因
    （评审 v4 §5 P2：过滤后继续算点值 R 会把缩水的根集当成完整根集）。
    """

    return [item for item in samples
            if item.get("completeness") == "complete"
            and item.get("resolved") and item.get("d_raw") is not None
            and item.get("m_diff") is not None]


def fit_c(samples: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    """在 fit 根样本上冻结 c：pooled OLS（方差最小方向），负值截 0（保守）。

    c 最小化 Var(d_raw − c·m_diff) 的最优值 = Cov(d_raw, m_diff)/Var(m_diff)；
    只用 fit 根（batch7 种子），测量根不得参与（§12 步骤 3 分离）。
    """

    usable = usable_samples(samples)
    if len(usable) < 2:
        raise SystemExit("fit 样本不足（usable={0}），拒绝冻结 c".format(len(usable)))

    def ols(items: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
        xs = [float(item["m_diff"]) for item in items]
        ys = [float(item["d_raw"]) for item in items]
        mean_x = statistics.fmean(xs)
        mean_y = statistics.fmean(ys)
        cov = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
        var_x = sum((x - mean_x) ** 2 for x in xs)
        var_y = sum((y - mean_y) ** 2 for y in ys)
        c_hat = (cov / var_x) if var_x > 0 else 0.0
        return {"n": len(items), "cross_product": round(cov, 9),
                "ss_m": round(var_x, 9), "ss_d_raw": round(var_y, 9),
                "c_hat_raw": round(c_hat, 9),
                "c_clipped": max(0.0, c_hat)}

    per_pair = {pair: ols([item for item in usable if item["pair"] == pair])
                for pair in sorted({item["pair"] for item in usable})}
    pooled = ols(usable)
    c = pooled["c_clipped"]
    var_raw = statistics.variance([float(item["d_raw"]) for item in usable])
    sensitivity = {}
    for label, value in (("c_frozen", c), ("prior_0.25", 0.25),
                         ("half_c", 0.5 * c)):
        adjusted = [float(item["d_raw"]) - value * float(item["m_diff"])
                    for item in usable]
        sensitivity[label] = {"c": round(value, 9),
                              "var_adjusted_fit": round(statistics.variance(adjusted), 9)}
    return {"method": "pooled OLS c* = Cov(d_raw, m_diff)/Var(m_diff)，负值截 0",
            "c": round(c, 9), "pooled": pooled, "per_pair": per_pair,
            "var_d_raw_fit": round(var_raw, 9),
            "note_fields": "ols 块内 cross_product/ss_m/ss_d_raw 为离差交叉积与平方和"
                           "（无 n 分母；c 为其比值不受影响）；var_d_raw_fit 与 "
                           "sensitivity 内为样本方差（statistics.variance，ddof=1）",
            "sensitivity": sensitivity,
            "n_usable": len(usable),
            "n_excluded": len(samples) - len(usable)}


def root_observations(items: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    """按来源根聚合统计单位：同一来源根的 4 个换座行先取均值成**一根观测**。

    主合同的统计单位是来源根（v4 §12；评审 v4 §5 口径修正）：同一根的四个
    换座共享同一牌墙根，彼此高度相关；把它们当独立观测会把方差与标准误
    算小（原报告 0.6445 就是座位行口径的产物）。聚合口径：

      - d_raw = 该根各座位 d_raw 的**均值**（根级点估计，不放大独立样本数）；
      - m_diff = 该根各座位 m_diff 的均值（c 为线性校正，先均值后校正与
        先校正后均值等价）；
      - cost = 该根各座位成本**之和**（整根双臂阶段成本，单位秒；R 的分子
        分母同乘同一因子，量纲选择不影响 R，但报告数字与重算脚本一致）。

    聚合对根观测**幂等**（一元素分组：均值=自身、和=自身），因此
    root_observations(root_observations(rows)) == root_observations(rows)；
    也正因如此，需要保留"同一根被重抽 k 次计 k 次"的语义时（bootstrap），
    必须调用 _r_stat 而不是再次聚合。

    拒绝条件（fail loudly，不静默换单位）：
      - 行未分辨（d_raw/m_diff 为 None）⇒ 调用方必须先经 usable_samples 过滤；
      - 同 root_id 出现多个 root_seed ⇒ 根身份冲突（评审 v4 Q7）。
    """

    groups: Dict[Tuple[str, str], List[Mapping[str, Any]]] = {}
    for item in items:
        key = (str(item.get("pair")), str(item.get("root_id")))
        groups.setdefault(key, []).append(item)
    observations: List[Dict[str, Any]] = []
    for (pair, root_id), rows in groups.items():
        if any(row.get("d_raw") is None or row.get("m_diff") is None
               for row in rows):
            raise ValueError(
                "root_observations 拒绝未分辨行（pair={0} root={1}）："
                "必须先用 usable_samples 过滤，未分辨样本不计点值".format(
                    pair, root_id))
        seeds = {row.get("root_seed") for row in rows}
        if len(seeds) > 1:
            raise ValueError(
                "root_observations 拒绝同 root_id 不同 root_seed：{0} → {1}".format(
                    root_id, sorted(str(seed) for seed in seeds)))
        observations.append({
            "sample_kind": ROOT_OBSERVATION_KIND,
            "pair": pair, "root_id": root_id,
            "root_seed": rows[0].get("root_seed"),
            "stratum": rows[0].get("opponent_mix", rows[0].get("stratum")),
            # n_seats 累计"这一根贡献了几个座位行"：座位行默认 1，已是根观测时
            # 沿用其 n_seats —— 聚合因此对根观测严格幂等（统计量不变）。
            "n_seats": int(sum(int(row.get("n_seats", 1)) for row in rows)),
            "d_raw": statistics.fmean(float(row["d_raw"]) for row in rows),
            "m_diff": statistics.fmean(float(row["m_diff"]) for row in rows),
            "cost": {"cost_raw_sec": sum(float(row["cost"]["cost_raw_sec"])
                                         for row in rows),
                     "cost_adjusted_sec": sum(
                         float(row["cost"]["cost_adjusted_sec"]) for row in rows),
                     "stats_ms": sum(float(row["cost"].get("stats_ms", 0.0))
                                     for row in rows)},
        })
    return observations


def pooled_root_observations(
        items: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    """合并（多策略对）口径的来源根观测：**一根一票**，策略对复制不增加信息。

    估计目标（先定义目标再选口径，R6 复审 §5 M3）：
      合并点估计 = 全部**来源根**上「根内各策略对配对差等权平均」的均值，
      即每根恰好贡献一个观测，与该根上跑了几个策略对无关。

    为什么不能把 (pair, root) 当独立观测：两对策略在逐根数据上完全相同时，
    12 个单元里只有 6 个独立来源根；按 12 除 √n 会同时把样本方差（ddof=1 在
    重复样本上被压小）与标准误算小——旧实现因此把原始差区间半宽从 0.372450
    压到 0.251106（缩窄 32.6%）。聚合口径下复制策略对不改变任何统计量。

    口径选择理由（与根簇协方差口径对比）：等对数的根内聚合就是标准的两阶段
    （cluster-mean）估计量，G=6 的小样本下比带小样本修正的 CR 估计更稳，且与
    非合并口径在同一数据上逐项一致；_cluster_bootstrap_r 仍按 root_id 整簇
    联动重抽，既有正确部分不动。

    单位与成本：一个观测 = 在一根上跑完该根**全部策略对**（成本取和）。R 是
    两个单位时间方差之比，成本随观测单位同步缩放，所以复制策略对只加倍成本、
    不改变 R，也不缩窄区间。

    拒绝条件（fail loudly）：
      - 行未分辨 ⇒ 同 root_observations（调用方先用 usable_samples 过滤）；
      - 同 root_id 跨策略对的 root_seed 冲突 ⇒ 不是同一随机世界，拒绝合并。
    """

    per_pair = root_observations(items)
    seeds: Dict[str, Any] = {}
    groups: Dict[str, List[Mapping[str, Any]]] = {}
    for observation in per_pair:
        root_id = str(observation["root_id"])
        seed = observation.get("root_seed")
        if root_id in seeds and seeds[root_id] != seed:
            raise ValueError(
                "pooled_root_observations 拒绝同 root_id 跨策略对的 root_seed "
                "冲突：{0} → {1} / {2}（根身份 = 共享随机世界，冲突即不可合并）"
                .format(root_id, seeds[root_id], seed))
        seeds.setdefault(root_id, seed)
        groups.setdefault(root_id, []).append(observation)
    pooled: List[Dict[str, Any]] = []
    for root_id in sorted(groups):
        rows = groups[root_id]
        pooled.append({
            "sample_kind": ROOT_OBSERVATION_KIND,
            "pair": POOLED_PAIR_LABEL, "root_id": root_id,
            "root_seed": rows[0].get("root_seed"),
            "stratum": rows[0].get("stratum"),
            # n_pairs/n_seats 用累加而非计数，使聚合对根观测幂等（同 n_seats）。
            "n_pairs": int(sum(int(row.get("n_pairs", 1)) for row in rows)),
            "n_seats": int(sum(int(row.get("n_seats", 1)) for row in rows)),
            "pair_d_raw": {str(row["pair"]): float(row["d_raw"]) for row in rows},
            "d_raw": statistics.fmean(float(row["d_raw"]) for row in rows),
            "m_diff": statistics.fmean(float(row["m_diff"]) for row in rows),
            "cost": {"cost_raw_sec": sum(float(row["cost"]["cost_raw_sec"])
                                         for row in rows),
                     "cost_adjusted_sec": sum(
                         float(row["cost"]["cost_adjusted_sec"]) for row in rows),
                     "stats_ms": sum(float(row["cost"].get("stats_ms", 0.0))
                                     for row in rows)},
        })
    return pooled


def _r_stat(observations: Sequence[Mapping[str, Any]],
            c: float,
            variance_unit: str = "来源根（每根四换座先取均值成一根观测）"
            ) -> Optional[Dict[str, Any]]:
    """在**独立观测**上算 R 与区间宽度：R = Var(Δraw)×cost_raw / (Var(Δadj)×cost_adj)。

    输入契约：每个元素是一个独立统计单位（来源根观测）。本函数**不再聚合**，
    以便 bootstrap 用重复元素表达"同一根被抽中 k 次"；把座位行直接喂进来会
    重现座位行口径错误，入口请走 _r_core（先做根聚合）或合并口径
    （pooled_root_observations 先做根内各对聚合）。

    variance_unit 只影响报告文案：单对口径为「每根四换座取均值」，合并口径为
    「根内各对先聚合、一根一票」；两种口径都要求输入已是独立根观测。
    """

    if len(observations) < 2:
        return None
    d_raw = [float(item["d_raw"]) for item in observations]
    d_adj = [value - c * float(item["m_diff"])
             for value, item in zip(d_raw, observations)]
    var_raw = statistics.variance(d_raw)
    var_adj = statistics.variance(d_adj)
    cost_raw = statistics.fmean([float(item["cost"]["cost_raw_sec"])
                                 for item in observations])
    cost_adj = statistics.fmean([float(item["cost"]["cost_adjusted_sec"])
                                 for item in observations])
    n = len(observations)
    half_raw = 1.959964 * (statistics.stdev(d_raw) / (n ** 0.5))
    half_adj = 1.959964 * (statistics.stdev(d_adj) / (n ** 0.5))
    mean_raw = statistics.fmean(d_raw)
    mean_adj = statistics.fmean(d_adj)
    r_value = ((var_raw * cost_raw) / (var_adj * cost_adj)) if var_adj > 0 else None
    return {"n": n, "n_observations": n,
            "n_seat_rows": int(sum(int(item.get("n_seats", 1))
                                   for item in observations)),
            "variance_unit": variance_unit,
            "var_delta_raw": round(var_raw, 9),
            "var_delta_adjusted": round(var_adj, 9),
            "cost_raw_sec": round(cost_raw, 6),
            "cost_adjusted_sec": round(cost_adj, 6),
            "r": (round(r_value, 6) if r_value is not None else None),
            "mean_d_raw": round(mean_raw, 9), "mean_d_adjusted": round(mean_adj, 9),
            "target_estimate_diff": round(mean_adj - mean_raw, 9),
            "ci95_halfwidth_raw": round(half_raw, 9),
            "ci95_halfwidth_adjusted": round(half_adj, 9),
            "ci_width_ratio_adj_over_raw": (round(half_adj / half_raw, 6)
                                            if half_raw > 0 else None)}


def _r_core(items: Sequence[Mapping[str, Any]],
            c: float) -> Optional[Dict[str, Any]]:
    """统计单位 = 来源根：先按 (pair, root_id) 聚合（每根四换座均值），再算方差/区间。

    座位行不是独立观测；本函数是 R 的公开入口，内部固定走
    root_observations → _r_stat（评审 v4 §5 口径修正）。
    """

    return _r_stat(root_observations(items), c)


def _cluster_bootstrap_r(items: Sequence[Mapping[str, Any]], c: float,
                         n_boot: int = BOOTSTRAP_DRAWS,
                         seed: int = BOOTSTRAP_SEED) -> Dict[str, Any]:
    """按**来源根**整簇重抽的 R bootstrap（同根多窗只算一个统计根，T10）。

    重抽单位是根观测（不是座位行）：先聚合出一根一观测，再对根簇有放回重抽；
    同一根被抽中 k 次就在统计里计 k 次（用重复元素表达，不经 _r_core 二次聚合）。
    合并口径下按 root_id 联动——同一 root_id 的不同策略对观测一起进出抽样
    （同根两对样本不独立，不能拆开当两份独立信息）。合并调用方必须先经
    pooled_root_observations 把根内各对聚合成一根一个观测（复审 §5 M3），
    否则 12 个 (pair, root) 单元会被当成 12 个独立抽样单元。
    """

    by_root: Dict[str, List[Mapping[str, Any]]] = {}
    for observation in root_observations(items):
        by_root.setdefault(str(observation["root_id"]), []).append(observation)
    roots = sorted(by_root)
    rng = random.Random(int(seed))
    values: List[float] = []
    degenerate = 0
    for _ in range(int(n_boot)):
        chosen = [rng.choice(roots) for _ in roots]
        drawn: List[Mapping[str, Any]] = []
        for root in chosen:  # 根被抽中 k 次 ⇒ 其观测计 k 次（簇内联动）
            drawn.extend(by_root[root])
        stats = _r_stat(drawn, c)
        if stats is None or stats["r"] is None:
            degenerate += 1
            continue
        values.append(float(stats["r"]))
    if not values:
        return {"n_boot": 0, "degenerate": degenerate, "lower95": None,
                "median": None, "upper95": None,
                "quantile_rule": "sorted[round(q*(n-1))]；退化比值（Var(Δadj)=0）"
                                 "不入分位数，次数在 degenerate 单列"}
    values.sort()

    def percentile(fraction: float) -> float:
        index = int(round(fraction * (len(values) - 1)))
        return round(values[index], 6)

    return {"n_boot": len(values), "degenerate": degenerate,
            "lower95": percentile(0.025), "median": percentile(0.5),
            "upper95": percentile(0.975),
            "quantile_rule": "sorted[round(q*(n-1))]；退化比值（Var(Δadj)=0）"
                             "不入分位数，次数在 degenerate 单列"}


def r_measurement_report(samples: Sequence[Mapping[str, Any]],
                         c: float) -> Dict[str, Any]:
    """步骤 5：每策略对一个 R + 合并 R；统计单位为来源根，含簇 bootstrap 不确定性。

    阻断规则（评审 v4 §5 P2）：存在被排除行（未分辨/不完整，n_excluded > 0）时
    **不输出任何点值 R / 区间**——被排除的根不在独立根集合里，剩余根不是原抽样
    的完整根集，点值与区间都不再适用；此时只返回样本计数、阻断原因与成本账目。
    本批 n_excluded=0，规则不触发，但逻辑必须存在（未来批次的度量门禁）。
    """

    usable = usable_samples(samples)
    n_excluded = len(samples) - len(usable)
    # 合并口径的统计单位仍是来源根：n_root_observations 是**独立根数**，
    # (pair, root) 单元数只作如实记录（不参与 √n），见 pooled_root_observations。
    unit = {"unit": "来源根",
            "unit_definition": "每根 4 换座先取均值成一根观测；合并口径下根内"
                               "各策略对再取均值，一根一票",
            "n_root_observations": len({item.get("root_id") for item in usable}),
            "n_pair_root_cells": len({(item.get("pair"), item.get("root_id"))
                                      for item in usable}),
            "n_pairs": len({item.get("pair") for item in usable}),
            "n_seat_rows": len(usable),
            "note": "座位行不是独立观测；方差/标准误/bootstrap 都在根观测上计算。"
                    "合并统计先做根内各对聚合：跨策略对的同一 root_id 只计一个"
                    "观测，复制逐行相同的策略对不提高有效样本量、不缩窄区间"}
    per_root_costs = []
    seen = sorted({(item["pair"], item["root_id"]) for item in samples})
    for pair, root_id in seen:
        roots = [item for item in samples
                 if item["pair"] == pair and item["root_id"] == root_id]
        per_root_costs.append({
            "pair": pair, "root_id": root_id, "n_samples": len(roots),
            "cost_raw_sec": round(sum(float(i["cost"]["cost_raw_sec"])
                                      for i in roots), 6),
            "cost_adjusted_sec": round(sum(float(i["cost"]["cost_adjusted_sec"])
                                           for i in roots), 6),
            "correction_stats_sec": round(sum(float(i["cost"]["stats_ms"])
                                              for i in roots) / 1000.0, 6)})
    if n_excluded > 0:
        return {
            "c": c, "blocked": True, "statistics_unit": unit,
            "block_reason": (
                "存在被排除行（n_excluded={0}，未分辨/不完整根不计点值）："
                "过滤后剩余根集不是原抽样的完整根集，点值 R 与区间均不适用；"
                "保留原始行不等于统计中没有删根，需另版区间方法或补足根后重算"
                .format(n_excluded)),
            "pairs_blocked": sorted({item["pair"] for item in usable}),
            "per_pair": {},
            "pooled": {"core": None, "bootstrap": None, "blocked": True,
                       "estimand": dict(POOLED_ESTIMAND,
                                        independent_unit_count=len(
                                            {item.get("root_id")
                                             for item in usable}),
                                        pair_root_cells=len(
                                            {(item.get("pair"), item.get("root_id"))
                                             for item in usable}))},
            "per_root_costs": per_root_costs,
            "n_samples_total": len(samples), "n_usable": len(usable),
            "n_excluded": n_excluded}
    pairs = sorted({item["pair"] for item in usable})
    per_pair: Dict[str, Any] = {}
    for pair in pairs:
        items = [item for item in usable if item["pair"] == pair]
        per_pair[pair] = {"core": _r_core(items, c),
                          "bootstrap": _cluster_bootstrap_r(items, c)}
    # 合并口径（R6 复审 §5 M3）：统计单位是来源根——先把根内各策略对聚合，
    # 再在独立根观测上算方差/区间；bootstrap 仍按 root_id 整簇联动重抽。
    pooled_observations = pooled_root_observations(usable)
    pooled_core = _r_stat(
        pooled_observations, c,
        variance_unit="来源根（根内各策略对先取均值，一根一票）")
    if pooled_core is not None:
        pooled_core.update({
            "n_pair_root_cells": len({(item["pair"], item["root_id"])
                                      for item in usable}),
            "n_pairs": len(pairs),
            "estimand": dict(POOLED_ESTIMAND,
                             independent_unit_count=pooled_core["n"],
                             pair_root_cells=len({(item["pair"], item["root_id"])
                                                  for item in usable})),
        })
    pooled_boot = _cluster_bootstrap_r(pooled_observations, c)
    return {"c": c, "blocked": False, "statistics_unit": unit,
            "per_pair": per_pair,
            "pooled": {"core": pooled_core, "bootstrap": pooled_boot,
                       "estimand": dict(POOLED_ESTIMAND,
                                        independent_unit_count=len(
                                            pooled_observations),
                                        pair_root_cells=len(
                                            {(item["pair"], item["root_id"])
                                             for item in usable})),
                       "note": "合并口径按 root_id 联动重抽；根内各对先聚合，"
                               "复制逐行相同的策略对不增加独立观测"
                               "（R6 复审 §5 M3）"},
            "per_root_costs": per_root_costs,
            "n_samples_total": len(samples),
            "n_usable": len(usable),
            "n_excluded": n_excluded}


def measurement_root_ids(panel_seed: int,
                         mixes_roots: Mapping[str, Sequence[int]]) -> List[int]:
    """根种子清单（fit/测量分离断言的输入；按 seed 而非标签）。"""

    return sorted({natp.natural_root_seed(panel_seed, mix, index)
                   for mix, roots in mixes_roots.items() for index in roots})


def frozen_c_ok(frozen: Mapping[str, Any],
                measure_roots: Sequence[int]) -> Tuple[bool, str]:
    """分离断言：冻结记录必须含 fit 根清单，且与测量根不相交。"""

    fit_roots = frozen.get("fit_root_seeds")
    if not isinstance(fit_roots, list) or not fit_roots:
        return False, "C-FROZEN 缺 fit_root_seeds（冻结来源不完整）"
    overlap = sorted(set(int(v) for v in fit_roots)
                     & set(int(v) for v in measure_roots))
    if overlap:
        return False, "fit/测量根相交：{0}".format(overlap)
    if not isinstance(frozen.get("c"), (int, float)) or float(frozen["c"]) < 0:
        return False, "c 冻结值非法：{0!r}".format(frozen.get("c"))
    return True, "fit {0} 根与测量 {1} 根不相交".format(len(fit_roots),
                                                        len(measure_roots))


# ---------------------------------------------------------------------------
# 6. CLI：toy-verify / fit / measure / report（六步验收的机器入口）
# ---------------------------------------------------------------------------


def _load_contract(contract_file: Optional[str]) -> Dict[str, Any]:
    path = Path(contract_file) if contract_file else (_project_file(_PROJECT_ROOT, REPO / natp.DEFAULT_CONTRACT))
    return json.loads(path.read_text(encoding="utf-8"))


def cmd_toy_verify(args: argparse.Namespace) -> int:
    report = toy_verify_all()
    write_json(evidence_path("step2-toy-verification.json"), report)
    print(json.dumps({"ok": report["all_pass"],
                      "checks": {item["name"]: item["pass"]
                                 for item in report["checks"]}},
                     ensure_ascii=False))
    return 0 if report["all_pass"] else 1


def cmd_fit(args: argparse.Namespace) -> int:
    contract = _load_contract(args.contract_file)
    authorization = json.loads(Path(args.authorization).read_text(encoding="utf-8"))
    ledger_path = evidence_path("av-ledger.json")
    all_samples: List[Dict[str, Any]] = []
    products = {}
    for pair, source in PAIR_SOURCES.items():
        product = run_pair_panel(
            pair_name=pair, candidate_source=str(_project_file(_PROJECT_ROOT, ROUTE_DIR / source)), contract=contract,
            authorization=authorization, panel_seed=FIT_PANEL_SEED,
            mixes_roots=FIT_MIX_ROOTS, phase="fit",
            ledger_path=ledger_path, seats_per_root=4)
        products[pair] = {"out": str(product["identity"]["panel_epoch"]),
                          "tables_full": product["cost"]["tables_full_executed"]}
        all_samples.extend(product["samples"])
    frozen = fit_c(all_samples)
    fit_roots = measurement_root_ids(FIT_PANEL_SEED, FIT_MIX_ROOTS)
    write_json(evidence_path("fit", "C-FROZEN.json"), {
        "schema": AIVAT_SCHEMA, "frozen_at": "2026-09-17",
        "c": frozen["c"], "method": frozen["method"],
        "fit_panel_seed": FIT_PANEL_SEED, "fit_mixes_roots": FIT_MIX_ROOTS,
        "fit_root_seeds": fit_roots,
        "n_usable": frozen["n_usable"], "n_excluded": frozen["n_excluded"],
        "pooled": frozen["pooled"], "per_pair": frozen["per_pair"],
        "var_d_raw_fit": frozen["var_d_raw_fit"],
        "sensitivity": frozen["sensitivity"],
        "note": "c 只在 fit 根（batch7 种子）上冻结；测量根独立（步骤 3 分离）"})
    write_json(evidence_path("fit", "FIT-REPORT.json"), {
        "schema": AIVAT_SCHEMA, "phase": "fit", "products": products,
        "fit": frozen, "fit_root_seeds": fit_roots,
        "ledger": str(ledger_path.relative_to(REPO)),
        "tables_full": sum(item["tables_full"] for item in products.values())})
    print(json.dumps({"ok": True, "c": frozen["c"], "products": products,
                      "n_usable": frozen["n_usable"]}, ensure_ascii=False))
    return 0


def cmd_measure(args: argparse.Namespace) -> int:
    contract = _load_contract(args.contract_file)
    authorization = json.loads(Path(args.authorization).read_text(encoding="utf-8"))
    frozen_path = evidence_path("fit", "C-FROZEN.json")
    if not frozen_path.is_file():
        raise SystemExit("拒绝测量：缺少 {0}（c 必须先在 fit 根上冻结，步骤 3 分离）"
                         .format(frozen_path))
    frozen = json.loads(frozen_path.read_text(encoding="utf-8"))
    measure_roots = measurement_root_ids(MEASURE_PANEL_SEED, MEASURE_MIX_ROOTS)
    ok, detail = frozen_c_ok(frozen, measure_roots)
    if not ok:
        raise SystemExit("拒绝测量：{0}".format(detail))
    c = float(frozen["c"])
    ledger_path = evidence_path("av-ledger.json")
    all_samples: List[Dict[str, Any]] = []
    products = {}
    for pair, source in PAIR_SOURCES.items():
        product = run_pair_panel(
            pair_name=pair, candidate_source=str(_project_file(_PROJECT_ROOT, ROUTE_DIR / source)), contract=contract,
            authorization=authorization, panel_seed=MEASURE_PANEL_SEED,
            mixes_roots=MEASURE_MIX_ROOTS, phase="measure",
            ledger_path=ledger_path, seats_per_root=4)
        products[pair] = {"out": str(product["identity"]["panel_epoch"]),
                          "tables_full": product["cost"]["tables_full_executed"]}
        all_samples.extend(product["samples"])
    measurement = {
        "schema": AIVAT_SCHEMA, "phase": "measure",
        "identity": {"panel_seed": MEASURE_PANEL_SEED,
                     "mixes_roots": MEASURE_MIX_ROOTS,
                     "measure_root_seeds": measure_roots,
                     "c_frozen_from": "fit/C-FROZEN.json", "c": c,
                     "separation_check": detail,
                     "candidates": {pair: str(_project_file(_PROJECT_ROOT, ROUTE_DIR / source))
                                    for pair, source in PAIR_SOURCES.items()}},
        "products": products, "samples": all_samples,
        "cost": {"tables_full": sum(item["tables_full"]
                                    for item in products.values())}}
    write_json(evidence_path("measure", "MEASUREMENT.json"), measurement)
    print(json.dumps({"ok": True, "c": c, "products": products,
                      "n_samples": len(all_samples)}, ensure_ascii=False))
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    measurement = json.loads(
        evidence_path("measure", "MEASUREMENT.json").read_text(encoding="utf-8"))
    frozen = json.loads(
        evidence_path("fit", "C-FROZEN.json").read_text(encoding="utf-8"))
    step2_path = evidence_path("step2-toy-verification.json")
    step2_pass = None
    if step2_path.is_file():
        step2_pass = bool(json.loads(
            step2_path.read_text(encoding="utf-8")).get("all_pass"))
    c = float(measurement["identity"]["c"])
    stats = r_measurement_report(measurement["samples"], c)
    pooled = stats["pooled"]
    boot_lower = (pooled["bootstrap"] or {}).get("lower95")
    if stats.get("blocked"):
        # 点值被阻断（n_excluded > 0）：不得输出任何点值 R，也不得据此启用。
        verdict = {
            "step2_legal_correction": step2_pass,
            "pooled_r": None, "pooled_r_bootstrap_lower95": None,
            "pooled_ci95_halfwidth_raw": None,
            "n_independent_roots": stats["statistics_unit"]["n_root_observations"],
            "blocked": True, "n_excluded": stats["n_excluded"],
            "block_reason": stats["block_reason"],
            "rule": "启用判据（FROZEN-DESIGN.md 预声明）：步骤 2 全过 且 合并 R 的 "
                    "bootstrap 下界 > 1 ⇒ 建议另版启用进确认降方差；否则停用",
            "recommendation": "disengage"}
        print(json.dumps({"ok": True, "verdict": verdict, "per_pair": {}},
                         ensure_ascii=False))
    else:
        verdict = {
            "step2_legal_correction": step2_pass,
            "pooled_r": (pooled["core"] or {}).get("r"),
            "pooled_r_bootstrap_lower95": boot_lower,
            # 合并口径的区间半宽与有效独立根数随判据一并留痕（R6 复审 §5 M3
            # 验收数字：0.372450；旧口径 0.251106 属缺陷值）。
            "pooled_ci95_halfwidth_raw": (pooled["core"] or {}).get(
                "ci95_halfwidth_raw"),
            "n_independent_roots": stats["statistics_unit"]["n_root_observations"],
            "blocked": False, "n_excluded": stats["n_excluded"],
            "rule": "启用判据（FROZEN-DESIGN.md 预声明）：步骤 2 全过 且 合并 R 的 "
                    "bootstrap 下界 > 1 ⇒ 建议另版启用进确认降方差；否则停用",
            "recommendation": ("enable-candidate" if (step2_pass is True
                                                      and boot_lower is not None
                                                      and boot_lower > 1.0)
                               else "disengage")}
        print(json.dumps({"ok": True, "verdict": verdict,
                          "per_pair": {pair: {
                              "r": ((block["core"] or {}).get("r")),
                              "boot_lower95": ((block["bootstrap"] or {}).get("lower95"))}
                              for pair, block in stats["per_pair"].items()}},
                         ensure_ascii=False))
    report = {"schema": AIVAT_SCHEMA, "step": "5-r-report",
              "identity": measurement["identity"], "statistics": stats,
              "fit_provenance": {"c": frozen["c"], "method": frozen["method"],
                                 "fit_root_seeds": frozen["fit_root_seeds"]},
              "verdict": verdict}
    # --out 默认 R-REPORT.json（冻结口径不变）；口径修正版另落 R-REPORT-v2.json，
    # 原文件保留不删（新结论必须可与旧结论逐项对照）。
    write_json(evidence_path(getattr(args, "out", None) or "R-REPORT.json"), report)
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="AIVAT 旁路净效率实验（v4 §12 六步验收；批次 7b）")
    sub = parser.add_subparsers(dest="command", required=True)

    toy = sub.add_parser("toy-verify", help="步骤 2：可穷举零期望/确定性/分区验证")
    toy.set_defaults(func=cmd_toy_verify)

    fit = sub.add_parser("fit", help="步骤 3：fit 根（batch7 种子）上冻结 c")
    fit.add_argument("--authorization", required=True)
    fit.add_argument("--contract-file", default=None)
    fit.set_defaults(func=cmd_fit)

    measure = sub.add_parser("measure", help="步骤 4：独立保留根上测量（需 C-FROZEN）")
    measure.add_argument("--authorization", required=True)
    measure.add_argument("--contract-file", default=None)
    measure.set_defaults(func=cmd_measure)

    report = sub.add_parser("report", help="步骤 5：R 与 bootstrap 报告")
    report.add_argument("--out", default=None,
                        help="报告输出文件名（默认 R-REPORT.json；口径修正版用 "
                             "R-REPORT-v2.json，原文件保留）")
    report.set_defaults(func=cmd_report)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
