"""只读描述信用公式在已完成轨迹上的触发分布；不运行新策略或给局部改选因果标签。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
import argparse
from collections import Counter
from fractions import Fraction
import json
from pathlib import Path

import followup_balance_panel as core


def audit(folder):
    """核对已实际执行的排序，并描述上限/归一化对当前轨迹的静态影响。"""
    b = core.b
    folder = Path(folder).resolve()
    assert folder.parent == b.HERE
    plan = b.read(folder / "evaluation-plan.json")
    closed = b.read(folder / "development-decision.json")
    assert closed["candidate_id"] == plan["candidate_id"]
    samples = b.read(folder / "effect-samples.json")
    totals, by_mix, examples = Counter(), {m: Counter() for m in ("H", "M")}, {}
    for sample in samples:
        mix = sample["opponent_mix"]
        for table in sample["raw_arms"]["candidate"]["tables"]:
            for row in table["prototype_audit"]:
                if row["status"] != "EVALUATED":
                    continue
                assert row["ranking_order"] == core.mathematics.expected_order(row["ranking_rows"], row["ranking_context"])
                n, w = row["ranking_context"]["direct_support"], row["ranking_context"]["nonprogress_weight"]
                values = row["ranking_rows"]
                observed = row["selected_first"]
                raw_q_choice = row["parent_selected_first"]
                uncapped = sorted(enumerate(values), key=lambda pair: (
                    -(Fraction(str(pair[1]["v2_total"])) + Fraction(pair[1]["improvement_weighted_sum"], w)),
                    -Fraction(str(pair[1]["v2_total"])), pair[0]))[0][1]["action_key"] if w else row["base_first"]
                clipped = sum(r["improvement_weighted_sum"] > n * w for r in values) if w else 0
                saturated = sum(r["improvement_weighted_sum"] >= n * w for r in values) if w else 0
                flags = {"evaluated_requests": True, "zero_nonprogress_weight": w == 0,
                    "any_credit_strictly_clipped": clipped > 0,
                    "all_credits_at_or_above_cap": saturated == len(values),
                    "cap_changes_first_vs_same_formula_without_cap": observed != uncapped,
                    "actual_changes_first_vs_v2": observed != row["base_first"],
                    "actual_changes_first_vs_raw_q_parent": observed != raw_q_choice,
                    "uncapped_combination_changes_first_vs_raw_q_parent": uncapped != raw_q_choice}
                current = next(v for v in values if v["action_key"] == observed)
                flags["actual_overrides_higher_v2_total"] = current["v2_total"] < values[0]["v2_total"]
                flags["actual_changes_only_v2_total_tie"] = observed != row["base_first"] and current["v2_total"] == values[0]["v2_total"]
                for label, active in flags.items():
                    totals[label] += int(active)
                    by_mix[mix][label] += int(active)
                    if active and label in ("cap_changes_first_vs_same_formula_without_cap", "actual_overrides_higher_v2_total") and (mix, label) not in examples:
                        examples[(mix, label)] = {"opponent_mix": mix, "root_index": sample["root_index"],
                            "focal_anchor_seat": sample["focal_anchor_seat"], "table_id": table["table_id"],
                            "decision_id": row["decision_id"], "trigger_seq": row["trigger_seq"],
                            "actual_first": observed, "uncapped_static_first": uncapped,
                            "parent_static_first": raw_q_choice, "v2_first": row["base_first"],
                            "context": row["ranking_context"], "rows": values, "kind": label}
    result = {"schema": "followup-credit-trajectory-audit/1", "created_at_utc": b.search.utc_now(),
        "candidate_id": plan["candidate_id"], "source_sha256": b.digest(Path(__file__).read_bytes()),
        "input_sha256": {name: b.digest((folder / name).read_bytes()) for name in ("effect-samples.json", "evaluation-plan.json", "development-decision.json")},
        "counts": dict(totals), "by_mix": {m: dict(c) for m, c in by_mix.items()}, "first_examples": list(examples.values()),
        "interpretation": "当前候选实际轨迹上的静态排序分解；没有执行未截断变体或重跑父代。各计数可重叠，不能相加作归因。固定顺序首例避免按终局结果选窗，但仍是已见数据描述。",
        "counterfactual_effect_measured": False, "new_tables": 0, "model_calls": 0, "confirmation_roots": 0,
        "release_eligible": False}
    b.write(folder / "credit-audit.json", result)
    print(json.dumps({"folder": str(folder), "counts": result["counts"], "by_mix": result["by_mix"]}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder")
    audit(parser.parse_args().folder)
