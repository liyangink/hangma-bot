"""只读解释两个冻结首摸分布，防止把负阶段标签或新增特征直接当修复证据。"""

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
from collections import Counter
from fractions import Fraction

import followup_balance_branch_probe as probe


def main():
    """按同一条件首摸比较合法弃牌前沿；不创建新策略或执行反事实阶段。"""
    b, out = probe.b, probe.OUT
    assert b.read(out / "summary.json")["all_original_q_reproduced"]
    reports = []
    for index in (1, 2):
        data = b.read(out / ("case-" + str(index) + ".json"))
        baseline, candidate = data["variants"]
        a = {r["draw"]: r for r in baseline["branches"]}
        z = {r["draw"]: r for r in candidate["branches"]}
        assert set(a) == set(z)
        counts, differences = Counter(), []
        for draw, first in a.items():
            second = z[draw]
            assert first["unseen_weight"] == second["unseen_weight"]
            left = (first["best_shanten"], -first["best_support"])
            right = (second["best_shanten"], -second["best_support"])
            label = "candidate_better" if right < left else "v2_better" if left < right else "same"
            counts[label] += first["unseen_weight"]
            if left != right:
                differences.append({"draw": draw, "unseen_weight": first["unseen_weight"],
                    "v2": {"shanten": left[0], "support": -left[1]},
                    "candidate": {"shanten": right[0], "support": -right[1]}})
        progress_key = str(data["case"]["direct_shanten"] - 1)
        means = [Fraction(v["groups_by_shanten"][progress_key]["weighted_mean_support"]) for v in data["variants"]]
        reports.append({"case": index, "direction_of_selected_stage": data["case"]["direction"],
            "actions_v2_then_candidate": data["case"]["actions"],
            "progress_mean_support_v2_then_candidate": [str(x) for x in means],
            "additional_progress_mean_preference": "candidate" if means[1] > means[0] else "v2" if means[0] > means[1] else "same",
            "branch_lexicographic_weight_counts": dict(counts), "branch_differences": differences,
            "other_legal_actions": [{"action_key": v["action_key"], "draw": r["draw"], "other_actions": r["other_legal_actions"]}
                for v in data["variants"] for r in v["branches"] if r["other_legal_actions"]]})
    result = {"schema": "followup-branch-interpretation/1", "source_sha256": b.digest(b.Path(__file__).read_bytes()),
        "input_sha256": {name: b.digest((out / name).read_bytes()) for name in ("manifest.json", "summary.json", "case-1.json", "case-2.json")},
        "cases": reports, "finding": "新增推进后质量在负配置首例仍偏向原候选，正配置首例相同；不构成修正原选择的直接证据。各首摸存在方向相反的后继前沿，不能只用阶段标签或均值解释单步。",
        "causal_effect_of_first_decision_measured": False, "new_tables": 0, "model_calls": 0,
        "confirmation_roots": 0, "release_eligible": False}
    b.write(out / "interpretation.json", result)
    print(result["finding"], flush=True)


if __name__ == "__main__":
    main()
