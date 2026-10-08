"""P24 证据表：逐例机械复核 + 每个开发根的三数（先胡率 / 均番 / 桌级均值差）+ 听口宽度列。"""

from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p24-deferral-complement-01-20260925'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

import collections
import json
import statistics
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p24-deferral-complement-01-20260925/teacher')
FIT = 16


def main() -> int:
    manifest = json.loads((_project_file(_PROJECT_ROOT, OUT / "manifest.json")).read_text(encoding="utf-8"))
    targets = json.loads((_project_file(_PROJECT_ROOT, OUT / "targets.json")).read_text(encoding="utf-8"))["targets"]
    keys = manifest["sample_keys"]
    checks = collections.Counter()
    states = []
    for target in targets:
        rows = [json.loads((_project_file(_PROJECT_ROOT, OUT / "rollouts" / "{0}-future-{1:02d}.json".format(
            target["target_id"], index))).read_text(encoding="utf-8"))
            for index in range(1, 33)]
        for row in rows:
            divergence = row["divergence"]
            checks["rollouts"] += 1
            checks["force_ok"] += (row["force_count"] == {"reference": 1, "intervention": 1})
            checks["actions_ok"] += (
                row["actual_actions"] == {"baseline": target["reference_action"],
                                          "candidate": target["intervention_action"]})
            checks["divergence_index_is_target"] += (
                divergence["first_divergence_index"] == divergence["target_index_reference"]
                == divergence["target_index_intervention"] == 0)
            checks["prefix_identical"] += divergence["prefix_identical"]
            checks["diverge_actions_ok"] += (
                divergence["first_divergence_actions"]
                == [target["reference_action"], target["intervention_action"]])
            checks["mechanical_ok"] += row["mechanical_ok"]
            checks["hu_arm_settlement_ok"] += (
                row["reference"]["terminal"] == "focal_hu"
                and row["reference"]["fan"] == target["expected_hu_settlement"]["fan"]
                and row["reference"]["score_delta"]
                    == target["expected_hu_settlement"]["score_delta"])
        fit, recheck = rows[:FIT], rows[FIT:]

        def arm(items, name):
            won = [r[name]["terminal"] == "focal_hu" for r in items]
            fans = [float(r[name]["fan"]) for r in items
                    if r[name]["terminal"] == "focal_hu" and r[name]["fan"] is not None]
            return {"hu_rate": sum(won) / len(items),
                    "mean_fan": (statistics.fmean(fans) if fans else None),
                    "hu_n": sum(won)}

        widths = {name: [r["focal_widths"][name][0]["chosen_useful_kinds"]
                         for r in recheck if r["focal_widths"][name]]
                  for name in ("baseline", "candidate")}
        states.append({
            "target_id": target["target_id"], "mix": target["source"]["mix"],
            "root": target["source"]["source_root_id"],
            "seat": target["focal_physical_seat"],
            "round_no": target["features"]["round_no"],
            "hu_fan": target["features"]["hu_fan"],
            "hu_self_delta": target["expected_hu_settlement"]["score_delta"][
                target["focal_physical_seat"]],
            "intervention_action": target["intervention_action"],
            "intervention_useful_kinds": target["features"]["intervention_useful_kinds"],
            "intervention_shanten_after": target["features"]["intervention_shanten_after"],
            "fit_round_mean": statistics.fmean(
                r["focal_current_round_settlement_delta"] for r in fit),
            "fit_table_mean": statistics.fmean(
                r["focal_current_table_score"]["delta"] for r in fit),
            "recheck_round_mean": statistics.fmean(
                r["focal_current_round_settlement_delta"] for r in recheck),
            "recheck_table_mean": statistics.fmean(
                r["focal_current_table_score"]["delta"] for r in recheck),
            "selected": (statistics.fmean(r["focal_current_round_settlement_delta"]
                                          for r in fit) > 0
                         and statistics.fmean(r["focal_current_table_score"]["delta"]
                                              for r in fit) > 0),
            "recheck_hu_arm": arm(recheck, "reference"),
            "recheck_deferral_arm": arm(recheck, "intervention"),
            "fit_hu_arm": arm(fit, "reference"),
            "fit_deferral_arm": arm(fit, "intervention"),
            "recheck_arm_b_next_draw_width_mean": (
                statistics.fmean(widths["candidate"]) if widths["candidate"] else None),
            "recheck_arm_a_next_draw_width_mean": (
                statistics.fmean(widths["baseline"]) if widths["baseline"] else None),
            "recheck_arm_a_draw_windows_after_cut": len(widths["baseline"]),
            "recheck_arm_b_draw_windows_after_cut": len(widths["candidate"]),
            "terminal_transitions": dict(sorted(collections.Counter(
                r["reference"]["terminal"] + "->" + r["intervention"]["terminal"]
                for r in rows).items())),
        })
    payload = {"schema": "r18-p24-deferral-complement-evidence/1",
               "checks": dict(sorted(checks.items())), "states": states}
    (_project_file(_PROJECT_ROOT, HERE / "evidence-tables.json")).write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + chr(10),
        encoding="utf-8")
    print(json.dumps(payload["checks"], ensure_ascii=False, indent=2))
    print()
    columns = ["#", "mix", "根", "座", "局", "立即胡番", "立即胡得分", "臂B弃牌",
               "B后有效种数", "fit Δ局", "fit Δ桌", "复查 Δ局", "复查 Δ桌", "选中",
               "复查A先胡率", "复查B先胡率", "复查B均番"]
    print("| " + " | ".join(columns) + " |")
    print("| " + " --- |" * len(columns))
    for state in states:
        print(("| {0} | {1} | {2} | {3} | {4} | {5} | {6} | {7} | {8} | {9:+.3f} | {10:+.3f} "
               "| {11:+.3f} | {12:+.3f} | {13} | {14:.3f} | {15:.3f} | {16} |").format(
            state["target_id"].rsplit("-", 1)[1], state["mix"], state["root"][-6:],
            state["seat"], state["round_no"], state["hu_fan"], state["hu_self_delta"],
            state["intervention_action"], state["intervention_useful_kinds"],
            state["fit_round_mean"], state["fit_table_mean"],
            state["recheck_round_mean"], state["recheck_table_mean"],
            "是" if state["selected"] else "否",
            state["recheck_hu_arm"]["hu_rate"], state["recheck_deferral_arm"]["hu_rate"],
            (None if state["recheck_deferral_arm"]["mean_fan"] is None
             else round(state["recheck_deferral_arm"]["mean_fan"], 3))))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
