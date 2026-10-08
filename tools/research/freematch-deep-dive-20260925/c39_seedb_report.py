#!/usr/bin/env python3
"""C39 seed B 专项读数：账本分解（判据⑤）、机制同向（判据④）、零缺陷（判据⑥）。

数据来源：**只读**复用 `c35_mechanics_gate.py` 产出的批目录（本脚本不改 runner、不改生产文件）。
统计口径与 runner 的 `verdict` 完全一致：**根级聚类**——先在同一 (对手池, 根) 内对四个焦点座位取均值，
再对每根求「候选 − 基准」的差值，最后按 `pstdev/√n` 与 1.96 正态分位给 95% CI。

账本分解（逐局公开单局记录 `RoundRecord.score_delta` 的焦点座位分量）：
  * 爆头胡收入 = 焦点胡牌且官方明细含「爆头」的局，其 score_delta 之和；
  * 普通胡收入 = 焦点胡牌且非爆头的局，其 score_delta 之和；
  * 非胡付分   = 焦点未胡的局，其 score_delta 之和（通常为负）。
三者之和恒等于该阶段 `focal_stage_score`（脚本内先做恒等式核对，不通过即退出非零）。

单位：分/桌（一个阶段 = `tables_per_stage` 张完整桌，每桌 8 局）。
"""

from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/freematch-deep-dive-20260925'

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
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

SCHEMA = "c39-seedb-report/1"
BASELINE_ARM = "r18_v2"
CANDIDATE_ARM = ("candidate@review/freematch-deep-dive-20260925/"
                 "candidates/OPTY-R18-C27-CELL-R6.py")
LEDGER_KEYS = ("baotou_income_per_table", "normal_income_per_table",
               "nonwin_paid_per_table")


def load_rows(batch: Path) -> List[Dict[str, Any]]:
    """读入批内全部阶段文件（不读 result.json，避免依赖 runner 的汇总版本）。"""
    rows = []
    for path in sorted((batch / "stages").glob("*.json")):
        rows.append(json.loads(path.read_text(encoding="utf-8")))
    if not rows:
        raise SystemExit("批目录没有阶段文件：" + str(batch / "stages"))
    return rows


def _ledger(rounds: Sequence[Mapping[str, Any]], tables: float) -> Dict[str, float]:
    """把一个阶段的逐局行折成三项账本（分/桌）。缺 score_delta 的行按 0 计并单独计数。"""
    baotou = normal = nonwin = 0.0
    missing = 0
    for row in rounds:
        delta = row.get("focal_score_delta")
        if delta is None:
            missing += 1
            delta = 0
        delta = float(delta)
        if row.get("won"):
            if row.get("baotou_win"):
                baotou += delta
            else:
                normal += delta
        else:
            nonwin += delta
    return {
        "baotou_income_per_table": baotou / tables,
        "normal_income_per_table": normal / tables,
        "nonwin_paid_per_table": nonwin / tables,
        "ledger_missing_delta_rounds": float(missing),
    }


def stage_metrics(row: Mapping[str, Any], tables: int) -> Dict[str, float]:
    """一个阶段单元 → 全部指标（分/桌、率、账本三项、番分布、赢时均分）。"""
    mech = row["mechanics"]
    totals = mech["totals"]
    rounds = mech["rounds"]
    n_rounds = max(1, int(totals["rounds"]))
    wins = int(totals["wins"])
    metrics: Dict[str, float] = {
        "score_per_table": float(row["stage"]["focal_stage_score"]) / float(tables),
        "baotou_rate": int(totals["baotou_entry_rounds"]) / float(n_rounds),
        "baotou_static_rate": int(totals["baotou_static_rounds"]) / float(n_rounds),
        "win_rate": wins / float(n_rounds),
        "baotou_win_share": (int(totals.get("baotou_wins", 0)) / float(wins)) if wins else float("nan"),
        "fan_per_win": (int(totals["fan_sum"]) / float(wins)) if wins else float("nan"),
        "fan_per_round": int(totals["fan_sum"]) / float(n_rounds),
        "win_score_per_win": (int(totals.get("score_sum_wins", 0)) / float(wins)) if wins else float("nan"),
        "fan1_share": (int(totals.get("fan1_wins", 0)) / float(wins)) if wins else float("nan"),
        "fan2_share": (int(totals.get("fan2_wins", 0)) / float(wins)) if wins else float("nan"),
        "fan4_share": (int(totals.get("fan4_wins", 0)) / float(wins)) if wins else float("nan"),
        "fan8_share": (int(totals.get("fan8_wins", 0)) / float(wins)) if wins else float("nan"),
        "fan_other_share": (int(totals.get("fan_other_wins", 0)) / float(wins)) if wins else float("nan"),
        "claims_per_round": int(totals["claims_made"]) / float(n_rounds),
        "claim_opportunities_per_round": int(totals["claim_opportunities"]) / float(n_rounds),
        "dealer_win_rate": (int(totals["dealer_wins"]) / float(totals["dealer_rounds"])
                            if totals["dealer_rounds"] else float("nan")),
        "idle_win_rate": ((wins - int(totals["dealer_wins"])) / float(n_rounds - int(totals["dealer_rounds"]))
                          if n_rounds > int(totals["dealer_rounds"]) else float("nan")),
        "tenpai_rate": int(totals["tenpai_rounds"]) / float(n_rounds),
        "first_tenpai_turn_mean": (int(totals["first_tenpai_turn_sum"]) / float(totals["tenpai_rounds"])
                                   if totals["tenpai_rounds"] else float("nan")),
        "illegal": float(mech["runner_illegal"]),
        "timeout": float(mech["runner_timeout"]),
        "exceptions": float(mech["policy_exceptions"]),
        "recorder_errors": float(mech["recorder_errors"]),
        "anomalies": float(totals["anomalies"]),
        "driver_timeouts": float(mech["table_runtime_counts"].get("timeouts", 0)),
        "driver_illegal": float(mech["table_runtime_counts"].get("illegal_choices", 0)),
        "driver_fallbacks": float(mech["table_runtime_counts"].get("fallbacks", 0)),
        "driver_auto": float(mech["table_runtime_counts"].get("auto_actions", 0)),
        "driver_audit_missing": float(mech["table_runtime_counts"].get("audit_missing", 0)),
    }
    metrics.update(_ledger(rounds, float(tables)))
    return metrics


def unit_cells(rows: Sequence[Mapping[str, Any]], tables: int) -> Dict[Tuple[str, int], Dict[str, Dict[str, float]]]:
    """(池, 根) → 臂 → 指标（根内四座位先平均），与 runner `_unit_cells` 同构。"""
    grouped: Dict[Tuple[str, int, str], List[Mapping[str, Any]]] = {}
    for row in rows:
        grouped.setdefault((row["mix"], int(row["root_index"]), row["arm"]), []).append(row)
    cells: Dict[Tuple[str, int], Dict[str, Dict[str, float]]] = {}
    for (mix, root, arm), units in grouped.items():
        per_seat = [stage_metrics(row, tables) for row in units]
        keys = per_seat[0].keys()
        cell = cells.setdefault((mix, root), {})
        cell[arm] = {key: statistics.fmean([seat[key] for seat in per_seat]) for key in keys}
    return cells


def pooled(rows: Sequence[Mapping[str, Any]], tables: int,
           pool: Optional[str]) -> Dict[str, Dict[str, Any]]:
    """整批或单池**按局池化**的读数（与 C35 §二 的表同口径：先加计数、再相除）。"""
    keys = ("rounds", "wins", "baotou_entry_rounds", "baotou_static_rounds", "baotou_wins",
            "fan1_wins", "fan2_wins", "fan4_wins", "fan8_wins", "fan_other_wins",
            "fan_sum", "score_sum_wins", "score_sum_all", "claims_made", "stages")
    buckets: Dict[str, Dict[str, float]] = {}
    ledger: Dict[str, Dict[str, float]] = {}
    for row in rows:
        if pool is not None and row["mix"] != pool:
            continue
        arm = row["arm"]
        bucket = buckets.setdefault(arm, {key: 0.0 for key in keys})
        mech = row["mechanics"]
        for key in keys:
            if key == "stages":
                bucket[key] += 1.0
            else:
                bucket[key] += float(mech["totals"].get(key, 0))
        parts = ledger.setdefault(arm, {k: 0.0 for k in LEDGER_KEYS})
        for key, value in _ledger(mech["rounds"], 1.0).items():
            if key in parts:
                parts[key] += value
    out: Dict[str, Dict[str, Any]] = {}
    for arm, bucket in sorted(buckets.items()):
        wins = max(1.0, bucket["wins"])
        rounds = max(1.0, bucket["rounds"])
        tables_total = max(1.0, bucket["stages"] * tables)
        out[arm] = {
            "stages": int(bucket["stages"]), "rounds": int(bucket["rounds"]),
            "wins": int(bucket["wins"]),
            "score_per_table": bucket["score_sum_all"] / tables_total,
            "baotou_rate": bucket["baotou_entry_rounds"] / rounds,
            "win_rate": bucket["wins"] / rounds,
            "baotou_win_share": bucket["baotou_wins"] / wins,
            "win_score_per_win": bucket["score_sum_wins"] / wins,
            "fan_per_win": bucket["fan_sum"] / wins,
            "fan1_share": bucket["fan1_wins"] / wins,
            "fan2_share": bucket["fan2_wins"] / wins,
            "fan4_share": bucket["fan4_wins"] / wins,
            "fan8_share": bucket["fan8_wins"] / wins,
            "fan_other_share": bucket["fan_other_wins"] / wins,
            **{key: ledger[arm][key] / tables_total for key in LEDGER_KEYS},
        }
    return out


def summary(values: Sequence[float]) -> Dict[str, float]:
    """与 runner/\`c29_verdict.py\` 同一算式：pstdev/√n + 1.96 正态分位。"""
    clean = [v for v in values if v is not None and not (isinstance(v, float) and math.isnan(v))]
    n = len(clean)
    if n == 0:
        return {"n": 0, "mean": float("nan"), "se": float("nan"),
                "ci_low": float("nan"), "ci_high": float("nan")}
    mean = statistics.fmean(clean)
    se = statistics.pstdev(clean) / math.sqrt(n) if n > 1 else float("nan")
    return {"n": n, "mean": mean, "se": se,
            "ci_low": mean - 1.96 * se, "ci_high": mean + 1.96 * se}


def main(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch", type=Path, required=True)
    parser.add_argument("--json", type=Path, default=None)
    args = parser.parse_args(argv)

    manifest = json.loads((args.batch / "manifest.json").read_text(encoding="utf-8"))
    if tuple(manifest["arms"]) != (BASELINE_ARM, CANDIDATE_ARM):
        raise SystemExit("批身份与预期臂不一致，停止读数：" + repr(manifest["arms"]))
    tables = int(manifest["tables_per_stage"])
    rows = load_rows(args.batch)

    # --- 恒等式与口径核对（在任何读数之前） -------------------------------
    checks: Dict[str, Any] = {"stages": len(rows), "identity_failures": [], "status_not_complete": 0,
                              "rounds_per_stage": Counter(), "missing_delta_rounds": 0}
    for row in rows:
        mech = row["mechanics"]
        if row["stage"]["status"] != "complete":
            checks["status_not_complete"] += 1
        checks["rounds_per_stage"][int(mech["totals"]["rounds"])] += 1
        total = (int(mech["totals"].get("score_sum_all", 0)))
        if "score_sum_all" in mech["totals"] and total != int(row["stage"]["focal_stage_score"]):
            checks["identity_failures"].append({"unit": [row["mix"], row["root_index"], row["focal_seat"], row["arm"]],
                                                "score_sum_all": total,
                                                "focal_stage_score": int(row["stage"]["focal_stage_score"])})
        led = _ledger(mech["rounds"], float(tables))
        checks["missing_delta_rounds"] += int(led["ledger_missing_delta_rounds"])
        if abs(sum(led[k] for k in LEDGER_KEYS) - float(row["stage"]["focal_stage_score"]) / tables) > 1e-9:
            checks["identity_failures"].append({"unit": [row["mix"], row["root_index"], row["focal_seat"], row["arm"]],
                                                "reason": "ledger_sum != score_per_table"})
    checks["rounds_per_stage"] = dict(checks["rounds_per_stage"])
    if checks["identity_failures"] or checks["status_not_complete"] or checks["missing_delta_rounds"]:
        print(json.dumps(checks, ensure_ascii=False, indent=2))
        raise SystemExit("口径核对未通过：账本恒等式/阶段状态/缺失增量存在异常，停止读数。")

    cells = unit_cells(rows, tables)
    metrics = ["score_per_table", "baotou_rate", "baotou_static_rate", "win_rate",
               "win_score_per_win", "fan_per_win", "fan_per_round",
               "baotou_win_share", "fan1_share", "fan2_share", "fan4_share", "fan8_share",
               "claims_per_round", "claim_opportunities_per_round", "dealer_win_rate",
               "idle_win_rate", "tenpai_rate", "first_tenpai_turn_mean"] + list(LEDGER_KEYS)

    def deltas(metric: str, pool: Optional[str] = None) -> List[float]:
        out = []
        for (mix, _root), arms in sorted(cells.items()):
            if pool is not None and mix != pool:
                continue
            base = arms.get(BASELINE_ARM, {}).get(metric)
            cand = arms.get(CANDIDATE_ARM, {}).get(metric)
            if base is None or cand is None:
                continue
            if isinstance(base, float) and math.isnan(base):
                continue
            if isinstance(cand, float) and math.isnan(cand):
                continue
            out.append(cand - base)
        return out

    def levels(metric: str, arm: str, pool: Optional[str] = None) -> List[float]:
        out = []
        for (mix, _root), arms in sorted(cells.items()):
            if pool is not None and mix != pool:
                continue
            value = arms.get(arm, {}).get(metric)
            if value is None or (isinstance(value, float) and math.isnan(value)):
                continue
            out.append(value)
        return out

    report: Dict[str, Any] = {"schema": SCHEMA, "batch": str(args.batch),
                              "manifest": manifest, "checks": checks, "metrics": {}}
    print("批次：%s（panel_seed=%s，单元 %d，根×池 %d，桌 %d）"
          % (args.batch, manifest["panel_seed"], len(rows), len(cells),
             len(rows) * tables))
    print()
    print("| 指标（候选 − 基准，根级聚类） | n根 | Δ均值 | 95% CI | 基准水平 | 候选水平 |")
    print("| --- | --- | --- | --- | --- | --- |")
    for metric in metrics:
        values = deltas(metric)
        if not values:
            continue
        s = summary(values)
        base_level = statistics.fmean(levels(metric, BASELINE_ARM))
        cand_level = statistics.fmean(levels(metric, CANDIDATE_ARM))
        report["metrics"][metric] = {
            **s, "baseline": base_level, "candidate": cand_level,
            "pools": {pool: summary(deltas(metric, pool)) for pool in ("H", "M")},
            "pool_levels": {pool: {arm: statistics.fmean(levels(metric, arm, pool))
                                   for arm in (BASELINE_ARM, CANDIDATE_ARM)}
                            for pool in ("H", "M")},
        }
        print("| %s | %d | %+.5f | [%+.5f, %+.5f] | %.5f | %.5f |"
              % (metric, s["n"], s["mean"], s["ci_low"], s["ci_high"], base_level, cand_level))

    # --- 按局池化（与 C35 §二 同口径的"水平"读数，供逐项对照） --------------
    report["pooled"] = {pool: pooled(rows, tables, None if pool == "ALL" else pool)
                        for pool in ("ALL", "H", "M")}
    print()
    print("### 按局池化（水平，与 C35 同口径）")
    print()
    print("| 池 | 臂 | 阶段 | 局 | 分/桌 | 爆头进入率 | 胡率 | 赢时均分 | 番分布 1/2/4/8 番占比 | 爆头胡收入/桌 | 普通胡收入/桌 | 非胡付分/桌 |")
    print("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for pool in ("ALL", "H", "M"):
        for arm, bucket in sorted(report["pooled"][pool].items()):
            short = arm.split("/")[-1].replace("OPTY-R18-C27-", "").replace(".py", "")
            print("| %s | %s | %d | %d | %.3f | %.4f | %.4f | %.3f | %.1f%%/%.1f%%/%.1f%%/%.1f%% | %+.2f | %+.2f | %+.2f |"
                  % (pool, short, bucket["stages"], bucket["rounds"], bucket["score_per_table"],
                     bucket["baotou_rate"], bucket["win_rate"], bucket["win_score_per_win"],
                     100.0 * bucket["fan1_share"], 100.0 * bucket["fan2_share"],
                     100.0 * bucket["fan4_share"], 100.0 * bucket["fan8_share"],
                     bucket["baotou_income_per_table"], bucket["normal_income_per_table"],
                     bucket["nonwin_paid_per_table"]))

    # --- 逐项判据 ---------------------------------------------------------
    score = report["metrics"]["score_per_table"]
    baotou = report["metrics"]["baotou_rate"]
    led_b = report["metrics"]["baotou_income_per_table"]
    led_n = report["metrics"]["normal_income_per_table"]
    led_x = report["metrics"]["nonwin_paid_per_table"]
    pool_sign = {m: {pool: report["metrics"][m]["pools"][pool]["mean"] for pool in ("H", "M")}
                 for m in ("score_per_table", "baotou_rate")}
    max_ratio = None
    if abs(led_b["mean"]) > 1e-12:
        max_ratio = abs(led_n["mean"]) / abs(led_b["mean"])
    j3 = bool(score["mean"] > 0)
    j4 = bool(baotou["mean"] > 0 and baotou["ci_low"] > 0)
    j5 = bool(led_b["mean"] > 0 and abs(led_n["mean"]) <= 1.2 * led_b["mean"])
    defects = {name: sum(int(row["mechanics"]["totals"].get(name, 0)) if name == "anomalies"
                         else int(row["mechanics"][name]) for row in rows)
               for name in ("runner_illegal", "runner_timeout", "policy_exceptions", "recorder_errors")}
    defects["counter_anomalies"] = sum(int(row["mechanics"]["totals"]["anomalies"]) for row in rows)
    driver: Counter = Counter()
    for row in rows:
        for key, value in row["mechanics"]["table_runtime_counts"].items():
            driver[key] += int(value)
    j6 = bool(all(v == 0 for v in defects.values())
              and driver.get("timeouts", 0) == 0 and driver.get("illegal_choices", 0) == 0
              and driver.get("fallbacks", 0) == 0)
    same_sign_score = bool(pool_sign["score_per_table"]["H"] > 0) == bool(pool_sign["score_per_table"]["M"] > 0)
    same_sign_baotou = bool(pool_sign["baotou_rate"]["H"] > 0) == bool(pool_sign["baotou_rate"]["M"] > 0)

    report["judgements"] = {
        "3_seed_b_point_estimate_positive": {"pass": j3, "delta_score_per_table": score},
        "4_mechanism_same_direction": {"pass": j4, "delta_baotou_rate": baotou,
                                       "pools": report["metrics"]["baotou_rate"]["pools"]},
        "5_normal_win_income_not_regressed": {
            "pass": j5,
            "delta_baotou_income_per_table": led_b, "delta_normal_income_per_table": led_n,
            "delta_nonwin_paid_per_table": led_x,
            "bound_1.2x_baotou": 1.2 * led_b["mean"],
            "abs_normal_over_baotou": max_ratio},
        "6_zero_defects_and_pool_signs": {
            "pass": j6, "defects": defects, "driver": dict(sorted(driver.items())),
            "pool_signs": pool_sign, "pool_same_sign_score": same_sign_score,
            "pool_same_sign_baotou": same_sign_baotou},
    }
    print()
    print("判据③ seed B 点估计 > 0：%s（Δ = %+.3f 分/桌，CI [%+.3f, %+.3f]）"
          % (j3, score["mean"], score["ci_low"], score["ci_high"]))
    print("判据④ 爆头进入率同向：%s（Δ = %+.4f（+%.2fpp 相对 %+.4f），CI [%+.4f, %+.4f]，n=%d）"
          % (j4, baotou["mean"], 100.0 * baotou["mean"],
             report["metrics"]["baotou_rate"]["baseline"], baotou["ci_low"], baotou["ci_high"], baotou["n"]))
    print("判据⑤ |Δ普通胡收入| ≤ 1.2×Δ爆头收入：%s（Δ爆头 = %+.3f，Δ普通 = %+.3f，比值 %.3f ≤ 1.2）"
          % (j5, led_b["mean"], led_n["mean"], -1.0 if max_ratio is None else max_ratio))
    print("判据⑥ 零缺陷：%s；异常计数 %s；驱动自报 %s"
          % (j6, json.dumps(defects, ensure_ascii=False), json.dumps(dict(sorted(driver.items())), ensure_ascii=False)))
    print("分池同号：积分 H%+.3f / M%+.3f（同号 %s）；爆头进入 H%+.4f / M%+.4f（同号 %s）"
          % (pool_sign["score_per_table"]["H"], pool_sign["score_per_table"]["M"], same_sign_score,
             pool_sign["baotou_rate"]["H"], pool_sign["baotou_rate"]["M"], same_sign_baotou))
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                             encoding="utf-8")
        print("写出：%s" % args.json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
