"""坐隐 1.6：指标来源表与分数类维度实现。

用途：从**既有** `results.jsonl` 事后计算**分数类**维度，不跑新桌赛。
依据 DESIGN §5.4（指标来源表）与 §7 第 1.6 步；审查 S4-1 要求
"历史产物缺字段时应标为不可计算，1.6 可先验收能从现有结果计算的维度"。

实现范围（**只有分数类**）：
  - 桌内净分（每桌、每臂）
  - 桌内前二率（同一桌内比较四家得分；**不是** `table_first_rate`）
  - **候选自身**的积分下尾 `Q05(自身积分)`——**不是** `Q05(候选−基线)`
  - 分位数（Q05/Q25/中位/Q75/Q95）与描述统计

**明确不做**（需要新增过程记录，属第 1.7 步）：
  番型分布、链长、圈开闭、白板条件分布、机制达成率、改选矩阵。
  这些维度在历史产物里**不可计算**，本工具会在来源表中显式标注。

两层区分（README §5.0）：
  维度（测量）→ 评估（推断）→ 标量化（使用）。
  本工具只做**维度**这一层；区间与功效由 sitin_power 负责。
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
import statistics
import sys
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence


def _quantile(values: Sequence[float], q: float) -> Optional[float]:
    """线性插值分位数；样本为空返回 None（**不填 0**）。"""

    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return float(ordered[0])
    pos = q * (len(ordered) - 1)
    low = int(pos)
    high = min(low + 1, len(ordered) - 1)
    frac = pos - low
    return float(ordered[low] * (1 - frac) + ordered[high] * frac)


def _seat_of_testing_policy(row: Mapping[str, Any]) -> Optional[int]:
    """被测臂所在物理座位；依据 game_id 末段臂标签，恰好一次才接受。"""

    game_key = row.get("game_key")
    game_id = game_key.get("game_id") if isinstance(game_key, Mapping) else game_key
    if not isinstance(game_id, str) or ":" not in game_id:
        return None
    label = game_id.rsplit(":", 1)[-1]
    policy_ids = row.get("policy_ids_by_seat")
    if not isinstance(policy_ids, (list, tuple)):
        return None
    seats = [i for i, x in enumerate(policy_ids) if x == label]
    return seats[0] if len(seats) == 1 else None


def collect_score_dimensions(rows: Sequence[Mapping[str, Any]]) -> dict:
    """从结果行收集分数类维度。

    只使用 `status == "complete"` 且分数可读的行；其余计入未使用，
    **不静默丢弃**。
    """

    used = 0
    skipped: list = []
    net_by_arm: dict = {}
    top2_by_arm: dict = {}
    for row in rows:
        if row.get("status") != "complete":
            skipped.append("status={0}".format(row.get("status")))
            continue
        seat = _seat_of_testing_policy(row)
        scores = row.get("scores_after")
        if seat is None or not isinstance(scores, (list, tuple)) or len(scores) != 4:
            skipped.append("座位或分数不可读")
            continue
        mine = scores[seat]
        if isinstance(mine, bool) or not isinstance(mine, int):
            skipped.append("分数不是整数")
            continue
        label = str(row.get("game_key", {}).get("game_id", "")).rsplit(":", 1)[-1] \
            if isinstance(row.get("game_key"), Mapping) else ""
        net_by_arm.setdefault(label, []).append(float(mine))
        # 桌内前二：严格按分数排名，同分按座位序（确定性、可复现）
        ranked = sorted(((s, i) for i, s in enumerate(scores)), key=lambda x: (-x[0], x[1]))
        rank = [i for _, i in ranked].index(seat) + 1
        top2_by_arm.setdefault(label, []).append(1.0 if rank <= 2 else 0.0)
        used += 1

    def summarize(values: Sequence[float]) -> dict:
        if not values:
            return {"n": 0}
        return {
            "n": len(values),
            "mean": round(statistics.fmean(values), 4),
            "sd": round(statistics.stdev(values), 4) if len(values) > 1 else None,
            "q05": round(_quantile(values, 0.05), 4),
            "q25": round(_quantile(values, 0.25), 4),
            "median": round(_quantile(values, 0.5), 4),
            "q75": round(_quantile(values, 0.75), 4),
            "q95": round(_quantile(values, 0.95), 4),
            "min": min(values),
            "max": max(values),
        }

    arms = {}
    for label in sorted(set(net_by_arm) | set(top2_by_arm)):
        arms[label] = {
            "net_score_per_table": summarize(net_by_arm.get(label, [])),
            "top2_rate_in_table": summarize(top2_by_arm.get(label, [])),
        }
    # 两名臂之间的差（若恰好两臂）
    diff = None
    labels = sorted(arms)
    if len(labels) == 2:
        a, b = labels
        na, nb = net_by_arm.get(a, []), net_by_arm.get(b, [])
        if na and nb and len(na) == len(nb):
            deltas = [y - x for x, y in zip(na, nb)]
            diff = {
                "baseline": a,
                "challenger": b,
                "note": "按行序配对；仅描述，不作强度结论（区间见 sitin_power）",
                "delta_mean": round(statistics.fmean(deltas), 4),
            }
    return {"used_rows": used, "skipped": skipped, "arms": arms, "delta": diff}


# ---------------------------------------------------------------------------
# 指标来源表（DESIGN §5.4）：逐项标注来源与当前可计算性
# ---------------------------------------------------------------------------

SOURCE_TABLE = [
    {"dimension": "桌内积分 / 场均净分", "class": "score", "source": "results.jsonl 的 scores_after",
     "computable_now": True, "role": "选择目标 / 确认门禁"},
    {"dimension": "桌内前二率", "class": "score", "source": "同一行四家得分排名",
     "computable_now": True, "role": "确认门禁（诊断）"},
    {"dimension": "候选**自身**积分下尾 Q05", "class": "score", "source": "候选臂得分分位数",
     "computable_now": True,
     "role": "风险诊断",
     "warning": "**不得**用 Q05(候选−基线) 代替——那衡量相对基线的最差退步（审查 R-6）"},
    {"dimension": "番型分布", "class": "process", "source": "单局结算/事件记录",
     "computable_now": False, "role": "诊断（机制达成）",
     "blocker": "MatchResult 不含番型；cmd_matches 不落盘决策序列（审查 S4-1）"},
    {"dimension": "链长分布 / 圈开闭 / 白板条件分布", "class": "process",
     "source": "规则状态与结算记录", "computable_now": False, "role": "诊断（机制达成）",
     "blocker": "同上；需第 1.7 步的最小诊断旁表与关联键"},
    {"dimension": "机制触发 / 实际改选率", "class": "process",
     "source": "同一观察下的候选与基线评分记录", "computable_now": False, "role": "确认门禁（机制是否被走到）",
     "blocker": "需要最小诊断记录；**不得把分叉后的两条轨迹按动作序号当同一局面**"},
]


def build_source_table() -> dict:
    return {
        "schema": "sitin-dimensions/1",
        "note": "历史产物缺字段的维度标为**不可计算**，不猜、不用默认值（AGENTS.md §3）。",
        "dimensions": SOURCE_TABLE,
        "computable_now": [d["dimension"] for d in SOURCE_TABLE if d["computable_now"]],
        "blocked": [d["dimension"] for d in SOURCE_TABLE if not d["computable_now"]],
    }


def render(report: dict) -> str:
    lines = ["# 坐隐 1.6 指标来源表与分数类维度", "",
             "本步**只实现可从既有结果计算的分数类维度**；过程类维度需第 1.7 步的记录。", "",
             "## 指标来源表", "", "| 维度 | 类别 | 可计算 | 来源 / 阻塞 | 角色 |",
             "| --- | --- | --- | --- | --- |"]
    for item in report["source_table"]["dimensions"]:
        detail = item.get("blocker") or item["source"]
        if item.get("warning"):
            detail += "；" + item["warning"]
        lines.append("| {0} | {1} | {2} | {3} | {4} |".format(
            item["dimension"], item["class"],
            "✅" if item["computable_now"] else "**❌**", detail, item["role"]))
    lines += ["", "## 分数类维度实测", ""]
    dims = report["dimensions"]
    lines.append("使用 {0} 行；未使用 {1} 行。".format(dims["used_rows"], len(dims["skipped"])))
    lines.append("")
    for label, arm in dims["arms"].items():
        lines.append("### {0}".format(label))
        lines.append("")
        lines.append("| 维度 | n | 均值 | 标准差 | Q05 | 中位 | Q95 | 最小 | 最大 |")
        lines.append("| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |")
        for name, key in (("桌内净分", "net_score_per_table"), ("桌内前二率", "top2_rate_in_table")):
            s = arm[key]
            if s["n"] == 0:
                lines.append("| {0} | 0 | — | — | — | — | — | — | — |".format(name))
                continue
            lines.append("| {0} | {1} | {2} | {3} | {4} | {5} | {6} | {7} | {8} |".format(
                name, s["n"], s["mean"], s["sd"], s["q05"], s["median"],
                s["q95"], s["min"], s["max"]))
        lines.append("")
    if dims["delta"]:
        d = dims["delta"]
        lines.append("净分配对差（{0} − {1} 的行序均值）：**{2}**".format(
            d["challenger"], d["baseline"], d["delta_mean"]))
        lines.append("")
        lines.append("> " + d["note"])
    return "\n".join(lines) + "\n"


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="坐隐 1.6：指标来源表与分数类维度")
    parser.add_argument("results", help="results.jsonl 路径")
    parser.add_argument("--out", help="产物目录")
    args = parser.parse_args(argv)

    rows = []
    for line in Path(args.results).read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    report = {
        "schema": "sitin-dimensions/1",
        "source_table": build_source_table(),
        "dimensions": collect_score_dimensions(rows),
    }
    text = json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2)
    if args.out:
        out = Path(args.out)
        out.mkdir(parents=True, exist_ok=True)
        (out / "dimensions.json").write_text(text + "\n", encoding="utf-8")
        (out / "dimensions.md").write_text(render(report), encoding="utf-8")
    print(render(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
