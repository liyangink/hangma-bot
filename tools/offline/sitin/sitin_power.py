"""坐隐（Sit-In）第 1.1 步：根组级配对复算与可检测效应。

职责边界（scripts/AGENTS.md）：本脚本只做参数解析与产物读取，
统计逻辑放在本文件内的纯函数里，供测试直接调用；不实现规则、HTTP、
策略或赛事生命周期，不访问网络，不写除 --out 之外的路径。

为什么需要本工具（方案 §1.2、§6.2，审查 R-1/R2-2）：
  1. 统计单位是**牌山根组**，不是桌赛、不是配对、也不是换座；
  2. 同一根组的多次换座**必须先组内平均**，不得当成多个独立样本；
  3. 每个配对要跑**基线臂与候选臂各一桌**，实际桌数是配对数的两倍；
  4. 根组身份**不在 results.jsonl 里**——scenario_id/pair_id 只是本次
     运行内的位置标识，不同 seed_range 的运行会复用同一批标签。
     注意：scenario_id **同时是洗牌输入**（牌墙由 (scenario_id, seed, round_no)
     派生，见 simulation/shuffle.py 的 deal-v1），因此跨运行可比性取决于
     (scenario_id, seed) 对是否相同，不能只看 scenario_id。
     因此必须由 experiment.json 提供种子，否则拒绝输出跨运行合并的口径。

用法：
  python scripts/sitin_power.py RESULTS_JSONL --experiment EXP.json [--out DIR]
  python scripts/sitin_power.py RESULTS_JSONL --prepare   # 从实验文件生成根组映射
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
import json
import math
import statistics
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence, Tuple

# 双侧 5%、80% 功效的标准正态分位数（沿用方案 §1.2 的口径）
Z_ALPHA_TWO_SIDED = 1.9599639845
Z_POWER_80 = 0.8416212336

# 单次完整 8 单局桌赛的单核耗时（秒）。**这是 2026-09-15 实测值，未复测**
# （方案 §1.2 边界）。第 1.2 步会用真实并行吞吐替换它；在替换前，
# 任何墙钟估算都必须标注为"沿用未复测的单核速度"。
SECONDS_PER_TABLE_ASSUMED = 1.68

# 用于功效表的规划目标（积分/完整八单局桌赛）
DEFAULT_EFFECTS = (1.0, 2.0, 3.0, 5.0, 15.0)


@dataclass(frozen=True)
class RootPair:
    """一个根组上的一次配对比较。

    scenario_id / pair_id 是位置标识，只在本运行内唯一；seed 是根组的真实
    身份。**注意 scenario_id 同时参与洗牌派生**（见模块 docstring），因此
    跨运行可比要求 (scenario_id, seed) 对相同。seed 缺失时不能跨运行合并，
    也不能对外声称根组数。
    """

    scenario_id: str  # 位置标识；**同时是洗牌输入**，非稳定身份但影响牌山
    pair_id: str  # 配对组位置标签，非稳定身份
    seed: Optional[int]  # 真实根组身份；来自 experiment.json，缺失为 None
    baseline_score: int  # 基线臂被测座位在桌赛结束时的桌内积分
    challenger_score: int  # 候选臂同一物理座位在桌赛结束时的桌内积分

    @property
    def delta(self) -> int:
        """该配对的桌内积分差（候选 − 基线），单位为积分。"""
        return self.challenger_score - self.baseline_score


@dataclass(frozen=True)
class RootAggregate:
    """一个根组的汇总；**独立统计单位**。"""

    seed: Optional[int]  # 真实身份
    label: str  # scenario_id，仅用于人读与日志关联
    n_pairs: int  # 该根组内的配对数（= 换座数）
    mean_delta: float  # 组内按配对的平均差（单位：积分/桌赛）
    distinct_deltas: int  # 组内不同差值个数；==1 表示换座未产生新信息


def load_seed_map(experiment_path: Path) -> dict:
    """从实验文件读取 scenario_id -> seed 映射。

    返回 {"kind": ..., "seeds": {scenario_id: seed}}；文件不含 seeds 时，
    返回空映射（调用方必须把根组身份标为未知）。
    """

    data = json.loads(Path(experiment_path).read_text(encoding="utf-8"))
    if not isinstance(data, Mapping):
        raise ValueError("实验文件必须是 JSON 对象")
    seeds = {}
    for item in data.get("seeds", ()) or ():
        if not isinstance(item, Mapping):
            continue
        scenario_id = item.get("scenario_id")
        seed = item.get("seed")
        if isinstance(scenario_id, str) and isinstance(seed, int) and not isinstance(seed, bool):
            seeds[scenario_id] = seed
    return {"kind": data.get("kind"), "seeds": seeds}


# 允许进入强度结论的来源；与 offline.evaluation_statistics.STRENGTH_SOURCE_KINDS
# 保持一致（此处独立声明以便本工具不依赖包导入；两边不一致即为缺陷）。
STRENGTH_SOURCE_KINDS = ("simulation", "test_room", "auto_match", "test_tournament")


def _completeness_problems(row: Mapping[str, Any]) -> list:
    """复刻 offline.evaluation_results.check_complete_consistency 的语义。

    `status == "complete"` **不足以**允许结果进入强度统计：还要求完成单局数
    与计划一致、分数已确认、无失效原因。
    """

    problems = []
    if row.get("expected_hands") is None:
        problems.append("expected_hands 为空")
    elif row.get("completed_hands") is None:
        problems.append("completed_hands 为空")
    elif row["completed_hands"] < row["expected_hands"]:
        problems.append("completed_hands={0} < expected_hands={1}".format(
            row["completed_hands"], row["expected_hands"]))
    if row.get("scores_after") is None:
        problems.append("scores_after 未确认")
    if row.get("invalid_reasons"):
        problems.append("invalid_reasons 非空: {0}".format(row["invalid_reasons"]))
    return problems


def _arm_label(row: Mapping[str, Any]) -> Optional[str]:
    """从 game_key.game_id 末段取**臂标签**（本次驱动写入的被测策略标识）。

    这是识别"这一行属于哪个臂"的可靠依据；不能把所有非对子的身份都
    当成被测臂——那样会把三个对手也算进来。
    """

    game_key = row.get("game_key")
    if isinstance(game_key, Mapping):
        game_id = game_key.get("game_id")
    else:
        game_id = game_key
    if not isinstance(game_id, str) or ":" not in game_id:
        return None
    return game_id.rsplit(":", 1)[-1]


def _opponent_key(policy_ids: Sequence[Any], tested_seat: int) -> Tuple[Any, ...]:
    """其余三家的身份元组，按座位序；用于校验两臂对手阵容一致。"""

    return tuple(x for i, x in enumerate(policy_ids) if i != tested_seat)


def _score_at(policy_ids: Sequence[Any], scores: Sequence[int], policy_id: str) -> Optional[int]:
    """取被测策略所在**物理座位**的桌内积分；找不到或座位不唯一时返回 None。

    policy_ids_by_seat 按物理座位 0—3 排列；被测身份每臂恰好占一个座位。
    """

    seats = [i for i, item in enumerate(policy_ids) if item == policy_id]
    if len(seats) != 1:
        return None
    seat = seats[0]
    if seat >= len(scores):
        return None
    value = scores[seat]
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def collect_root_pairs(
    rows: Sequence[Mapping[str, Any]],
    *,
    baseline_policy_id: Optional[str] = None,
    challenger_policy_id: Optional[str] = None,
    seed_map: Optional[Mapping[str, int]] = None,
) -> Tuple[list, list]:
    """把结果行还原成"每个根组一次配对"的列表。

    返回 (roots, exclusions)：
      - roots：RootPair 列表，按 (scenario_id, pair_id) 归并两臂；
      - exclusions：不能进入统计的行及原因（不静默丢弃）。

    基线/候选身份可从版本字段自动推断（要求每个 pair 恰好两个不同的被测身份）。
    """

    # 只给一侧参数必须报错，而不是静默退回字典序：
    # 单侧声明会把差值**符号反转**（实测 +6.3125 → −6.3125），且无警告。
    if (baseline_policy_id is None) != (challenger_policy_id is None):
        raise ValueError(
            "baseline_policy_id 与 challenger_policy_id 必须同时给出或同时省略；"
            "只给一侧会静默退回字典序并反转差值符号")
    seed_map = dict(seed_map or {})
    # 按 (scenario_id, pair_id) 归并——这是**运行内**的位置配对键
    buckets: dict = {}
    exclusions: list = []
    for row in rows:
        status = row.get("status")
        if status != "complete":
            exclusions.append("status={0}（非 complete 不进入强度统计）".format(status))
            continue
        source_kind = row.get("source_kind")
        if source_kind not in STRENGTH_SOURCE_KINDS:
            exclusions.append(
                "source_kind={0} 不进入强度结论".format(source_kind))
            continue
        problems = _completeness_problems(row)
        if problems:
            exclusions.append("结果完整性不足：{0}".format("；".join(problems)))
            continue
        scenario_id = row.get("scenario_id")
        pair_id = row.get("pair_id")
        policy_ids = row.get("policy_ids_by_seat")
        scores = row.get("scores_after")
        if not isinstance(scenario_id, str) or not isinstance(pair_id, str):
            exclusions.append("缺少 scenario_id/pair_id，无法确认同牌山配对")
            continue
        if not isinstance(policy_ids, (list, tuple)) or len(policy_ids) != 4:
            exclusions.append("policy_ids_by_seat 不是长度 4 的序列")
            continue
        if not isinstance(scores, (list, tuple)) or len(scores) != 4:
            exclusions.append("scores_after 不是长度 4 的序列")
            continue
        label = _arm_label(row)
        if label is None:
            exclusions.append("缺少 game_key.game_id 臂标签，无法确定被测臂")
            continue
        tested_seats = [i for i, x in enumerate(policy_ids) if x == label]
        if len(tested_seats) != 1:
            exclusions.append(
                "臂标签 {0} 在 policy_ids_by_seat 中出现 {1} 次，需要恰好 1 次".format(
                    label, len(tested_seats)
                )
            )
            continue
        value = _score_at(policy_ids, scores, label)
        if value is None:
            exclusions.append("臂标签 {0} 的座位积分不可读".format(label))
            continue
        key = (scenario_id, pair_id)
        bucket = buckets.setdefault(key, {"arms": {}, "duplicates": []})
        entry = (value, tested_seats[0], _opponent_key(policy_ids, tested_seats[0]),
                 tuple(row.get("seat_permutation") or ()))
        if label in bucket["arms"]:
            # 同一配对臂出现多行：**不得由文件顺序决定采用哪一行**。
            # 完全相同的记录可去重（声明规则）；分数不同必须报告并整对排除。
            if bucket["arms"][label] == entry:
                bucket["duplicates"].append(label)
            else:
                bucket["conflict"] = True
                bucket["conflict_reason"] = (
                    "pair_id={0} 的臂 {1} 出现多行且取值不同（臂必须恰好一行）".format(
                        pair_id, label))
            continue
        bucket["arms"][label] = entry

    for (scenario_id, pair_id), bucket in buckets.items():
        if bucket.get("conflict"):
            exclusions.append(bucket["conflict_reason"])
            continue
        if bucket.get("duplicates"):
            exclusions.append(
                "scenario={0} pair={1}：臂 {2} 有完全相同的重复行，已去重".format(
                    scenario_id, pair_id, sorted(set(bucket["duplicates"]))))
        arms = bucket["arms"]
        if len(arms) != 2:
            exclusions.append(
                "scenario={0} pair={1}：被测臂数为 {2}，需要恰好 2".format(
                    scenario_id, pair_id, len(arms)
                )
            )
            continue
        ids = sorted(arms)
        # ⚠️ 符号陷阱：缺省按名字字典序定基线/候选，会把差值的**符号**反过来。
        # 报告 §C/§17 要求"显式冻结基线身份"，因此调用方应始终传
        # --baseline / --challenger；缺省推断只用于探索，输出里会标注。
        base_id, chal_id = ids[0], ids[1]
        orientation_inferred = True
        if baseline_policy_id is not None and challenger_policy_id is not None:
            orientation_inferred = False
            if set(ids) != {baseline_policy_id, challenger_policy_id}:
                exclusions.append(
                    "scenario={0} pair={1}：被测臂 {2} 与声明的基线/候选不符".format(
                        scenario_id, pair_id, ids
                    )
                )
                continue
            base_id, chal_id = baseline_policy_id, challenger_policy_id
        base_score, base_seat, base_opp, base_perm = arms[base_id]
        chal_score, chal_seat, chal_opp, chal_perm = arms[chal_id]
        # 与 offline.evaluation_statistics._pair_consistency 同语义：
        # 座位配置必须逐座一致，且**仅测试座位**的策略不同。
        if base_perm != chal_perm:
            exclusions.append(
                "scenario={0} pair={1}：两臂 seat_permutation 不一致（{2} 对 {3}）".format(
                    scenario_id, pair_id, base_perm, chal_perm))
            continue
        if not base_perm:
            exclusions.append(
                "scenario={0} pair={1}：缺少 seat_permutation，无法校验换座一致性".format(
                    scenario_id, pair_id))
            continue
        if base_seat != chal_seat:
            exclusions.append(
                "scenario={0} pair={1}：两臂被测座位不同（{2} 对 {3}）".format(
                    scenario_id, pair_id, base_seat, chal_seat
                )
            )
            continue
        if base_opp != chal_opp:
            exclusions.append(
                "scenario={0} pair={1}：两臂对手阵容不一致（{2} 对 {3}）".format(
                    scenario_id, pair_id, base_opp, chal_opp
                )
            )
            continue
        buckets[(scenario_id, pair_id)] = RootPair(
            scenario_id=scenario_id,
            pair_id=pair_id,
            seed=seed_map.get(scenario_id),
            baseline_score=base_score,
            challenger_score=chal_score,
        )

    roots = [v for v in buckets.values() if isinstance(v, RootPair)]
    if roots and baseline_policy_id is None and challenger_policy_id is None:
        exclusions.append(
            "基线/候选身份未显式声明，按名字字典序推断——"
            "差值的**符号方向未经验证**，不得用于结论"
        )
    return roots, exclusions


def aggregate_by_root(pairs: Sequence[RootPair]) -> list:
    """按根组聚合：**组内先按换座平均**，再得到每根一个值。

    同一根组的多次换座是同一抽样单位，不得当成多个独立样本
    （evaluation_statistics.py 第 258—262 行同一口径）。
    """

    groups: dict = {}
    for item in pairs:
        groups.setdefault(item.scenario_id, []).append(item)
    out = []
    for scenario_id, items in groups.items():
        deltas = [x.delta for x in items]
        seeds = {x.seed for x in items}
        out.append(
            RootAggregate(
                seed=next(iter(seeds)) if len(seeds) == 1 else None,
                label=scenario_id,
                n_pairs=len(items),
                mean_delta=sum(deltas) / len(deltas),
                distinct_deltas=len(set(deltas)),
            )
        )
    out.sort(key=lambda a: a.label)
    return out


def roots_required(effect: float, sd_root: float) -> int:
    """按双侧 5%、80% 功效规划所需**独立根组**数。

    n = ceil(((z_{1-α/2} + z_power) × sd / δ)²)
    """

    if effect <= 0:
        raise ValueError("effect 必须是正数")
    if sd_root <= 0:
        raise ValueError("sd_root 必须是正数")
    return int(math.ceil(((Z_ALPHA_TWO_SIDED + Z_POWER_80) * sd_root / effect) ** 2))


def minimum_detectable_effect(sd_root: float, n_roots: int) -> float:
    """给定根组数下的最小可检测效应（同口径）。"""

    if n_roots <= 0:
        raise ValueError("n_roots 必须是正整数")
    return (Z_ALPHA_TWO_SIDED + Z_POWER_80) * sd_root / math.sqrt(n_roots)


def build_report(
    roots: Sequence[RootAggregate],
    *,
    seconds_per_table: float = SECONDS_PER_TABLE_ASSUMED,
    effects: Sequence[float] = DEFAULT_EFFECTS,
    rotations_for_budget: Optional[int] = None,
    tables_per_second: Optional[float] = None,
) -> dict:
    """生成结构化报告。

    `rotations_for_budget`：**未来实验计划采用的每根换座数**。缺省取本批**观察到的**
    最大换座数（而不是硬编码 4）——两者可能不同，混用会算错桌数预算。
    若计划改用其他换座数，必须显式传入并同时质疑现有单换座样本的方差是否适用。

    `tables_per_second`：真实并行吞吐（第 1.2 步实测）；给出时用它算墙钟，
    不再假定"核数线性"。
    """

    values = [r.mean_delta for r in roots]
    n_roots = len(roots)
    mean = statistics.fmean(values) if values else None
    sd = statistics.stdev(values) if n_roots > 1 else None
    seeds_known = all(r.seed is not None for r in roots)
    observed_rotations = max((r.n_pairs for r in roots), default=0)
    rotations = observed_rotations if rotations_for_budget is None else rotations_for_budget
    rows = []
    planning_note = None
    # 零方差是**期望结果**（自身/等价对照），不是异常：照常输出描述统计，
    # 但功效规划在 sd=0 下没有意义，必须显式说明而不是崩溃。
    if sd is not None and sd > 0:
        for effect in effects:
            need = roots_required(effect, sd)
            tables = need * 2 * rotations
            core_hours = tables * seconds_per_table / 3600.0
            row = {
                "effect_per_table": effect,
                "roots_required": need,
                "tables_required": tables,
                "rotations_per_root": rotations,
                "core_hours": round(core_hours, 1),
            }
            if tables_per_second:
                row["wall_hours_measured_throughput"] = round(tables / tables_per_second / 3600.0, 3)
            else:
                row["wall_hours_15_core_linear_assumed"] = round(core_hours / 15.0, 2)
            rows.append(row)
    elif sd == 0:
        planning_note = (
            "根级标准差为 0（自身或等价对照的期望结果）：描述统计照常给出，"
            "但**零方差样本不足以支持功效外推**——不输出所需根组数，"
            "也不得把零样本量当成可信结论。")
    return {
        "schema": "sitin-power/2",
        "notes": [
            "统计单位是牌山根组；组内换座先平均，不当作独立样本。",
            "桌数 = 根组 × 2 臂 × 每根换座数；配对数不含双臂因子。",
            "预算采用的每根换座数 = {0}（本批观察到的最大值为 {1}）；"
            "两者不同时必须显式说明，不能自动混用两种设计。".format(
                rotations, observed_rotations),
            "墙钟{0}".format(
                "按实测吞吐 {0} 桌/秒折算。".format(tables_per_second)
                if tables_per_second else
                "沿用单核 {0} 秒/桌并假定核数线性——**该假设已被第 1.2 步实测否定**，"
                "请优先传 tables_per_second。".format(seconds_per_table)),
        ],
        "roots": {
            "count": n_roots,
            "seeds_known": seeds_known,
            "mean_delta": None if mean is None else round(mean, 4),
            "sd_root": None if sd is None else round(sd, 6),
            "min_root_delta": min(values) if values else None,
            "max_root_delta": max(values) if values else None,
            "pairs_total": sum(r.n_pairs for r in roots),
            # 实际双臂桌数：与配对数区分（配对不含双臂因子）
            "tables_total": sum(r.n_pairs for r in roots) * 2,
            "observed_rotations_max": observed_rotations,
            "roots_with_identical_rotations": sum(1 for r in roots if r.distinct_deltas == 1),
        },
        "planning_note": planning_note,
        "mde_at_current_n": (
            None if (sd is None or sd <= 0) else round(minimum_detectable_effect(sd, n_roots), 4)
        ),
        "power_table": rows,
        "per_root": [
            {
                "label": r.label,
                "seed": r.seed,
                "n_pairs": r.n_pairs,
                "mean_delta": round(r.mean_delta, 4),
                "distinct_deltas": r.distinct_deltas,
            }
            for r in roots
        ],
    }


def render_markdown(report: Mapping[str, Any]) -> str:
    """人读报告；键序稳定。"""

    roots = report["roots"]
    lines = [
        "# 坐隐 1.1 根组级复算报告",
        "",
        "统计单位：牌山根组。组内换座先平均；桌数 = 根组 × 2 臂 × 换座数。",
        "",
        "## 根组口径",
        "",
        "| 指标 | 值 |",
        "| --- | ---: |",
        "| 独立根组数 | {0} |".format(roots["count"]),
        "| 根组真实身份（seed）已知 | {0} |".format(roots["seeds_known"]),
        "| 配对数合计 | {0} |".format(roots["pairs_total"]),
        "| **实际双臂桌数** | {0} |".format(roots["tables_total"]),
        "| 观察到的每根换座数（最大） | {0} |".format(roots["observed_rotations_max"]),
        "| 组内换座差值完全相同的根组 | {0} |".format(roots["roots_with_identical_rotations"]),
        "| 根级点估计（积分/桌赛） | {0} |".format(roots["mean_delta"]),
        "| **根级样本标准差** | **{0}** |".format(roots["sd_root"]),
        "| 根级极差 | {0} — {1} |".format(roots["min_root_delta"], roots["max_root_delta"]),
        "| 当前根数下的最小可检测效应 | {0} |".format(report["mde_at_current_n"]),
        "",
        "## 功效表",
        "",
        "| 待检效应（积分/桌赛） | 独立根组 | 模拟桌赛 | CPU 核小时 | 墙钟 |",
        "| ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in report["power_table"]:
        wall = row.get("wall_hours_measured_throughput")
        wall_text = ("{0} 小时（实测吞吐）".format(wall) if wall is not None
                     else "{0} 小时（**线性假设，已被否定**）".format(
                         row.get("wall_hours_15_core_linear_assumed")))
        lines.append(
            "| +{0:g} | {1:,} | {2:,} | {3} | {4} |".format(
                row["effect_per_table"],
                row["roots_required"],
                row["tables_required"],
                row["core_hours"],
                wall_text,
            )
        )
    if report.get("planning_note"):
        lines += ["", "> " + report["planning_note"]]
    lines += ["", "## 口径说明", ""]
    lines += ["- " + note for note in report["notes"]]
    return "\n".join(lines) + "\n"


def _load_rows(path: Path) -> list:
    rows = []
    for line_no, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as error:
            raise ValueError("第 {0} 行不是合法 JSON：{1}".format(line_no, error)) from error
    return rows


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="坐隐 1.1：根组级配对复算与可检测效应"
    )
    parser.add_argument("results", help="results.jsonl 路径")
    parser.add_argument("--experiment", help="experiment.json 路径（提供根组真实 seed）")
    parser.add_argument("--out", help="产物目录；缺省只打印报告")
    parser.add_argument("--baseline", help="基线 policy_id；**必须与 --challenger 同时给出**")
    parser.add_argument("--challenger", help="候选 policy_id；**必须与 --baseline 同时给出**")
    parser.add_argument("--rotations", type=int,
                        help="预算采用的每根换座数（缺省取本批观察到的最大值）")
    parser.add_argument("--tables-per-second", type=float,
                        help="实测并行吞吐；给出时按它折算墙钟，不假定核数线性")
    args = parser.parse_args(argv)
    if (args.baseline is None) != (args.challenger is None):
        parser.error("--baseline 与 --challenger 必须同时给出：只给一侧会静默反转差值符号")

    seed_map = {}
    if args.experiment:
        loaded = load_seed_map(Path(args.experiment))
        seed_map = loaded["seeds"]

    pairs, exclusions = collect_root_pairs(
        _load_rows(Path(args.results)),
        baseline_policy_id=args.baseline,
        challenger_policy_id=args.challenger,
        seed_map=seed_map,
    )
    roots = aggregate_by_root(pairs)
    report = build_report(
        roots,
        rotations_for_budget=args.rotations,
        tables_per_second=args.tables_per_second,
    )
    report["exclusions"] = exclusions
    if not seed_map:
        report["notes"].append(
            "未提供 --experiment 或实验文件无 seeds：根组真实身份未知，"
            "本次结果**只能在本运行内使用**，不得与其他 seed 区间的运行合并。"
        )

    text = json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2)
    if args.out:
        out_dir = Path(args.out)
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "power.json").write_text(text + "\n", encoding="utf-8")
        (out_dir / "power.md").write_text(render_markdown(report), encoding="utf-8")
    print(render_markdown(report))
    if exclusions:
        print("排除 {0} 项：".format(len(exclusions)))
        for item in exclusions[:10]:
            print("  - " + item)
    return 0


if __name__ == "__main__":
    sys.exit(main())
