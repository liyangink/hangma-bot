"""在续打结果曝光前，冻结首分歧与末单局负对照及同起点三臂。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t182-step12-diagnosis-and-joint-evolution-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
import json
from pathlib import Path
from prepare_diagnostics import pin, save

HERE = Path(__file__).resolve().parent
ROOT = _PROJECT_ROOT


def main():
    """按来源及事件顺序选首个行为分歧；不按结局或父代终分挑正例。"""
    comparison = json.loads((_project_file(_PROJECT_ROOT, HERE / "mechanism-comparison/CLOSURE.json")).read_text())
    assert comparison["complete"] and comparison["source_stable"]
    supplement = json.loads((_project_file(_PROJECT_ROOT, HERE / "mechanism-comparison-supplement/CLOSURE.json")).read_text())
    assert supplement["complete"] and supplement["source_stable"]
    comparison = {**comparison, "cases": comparison["cases"] + supplement["cases"],
                  "rows": comparison["rows"] + supplement["rows"]}
    cases = {r["label"]: r for r in comparison["cases"]}
    selected = {}
    controls = []
    for row in comparison["rows"]:
        assert row["status"] == "complete"
        case = cases[row["label"]]
        if row["label"].startswith(("fresh:", "supplement:")) and any(row["first_changed"].values()):
            key = (case["window_key"]["round_no"], case["window_key"]["trigger_seq"])
            current = selected.get(case["root_id"])
            if current is None or key < current[0]:
                selected[case["root_id"]] = (key, case, row)
        elif row["label"].startswith("last-control:"):
            controls.append((case, row))
    targets = []
    for _, case, row in (selected[k] for k in sorted(selected)):
        mechanisms = [n for n, v in row["first_changed"].items() if v]
        targets.append({"case": case, "parent_first": row["scores"]["parent"]["first"],
            "prototype_first": {n: row["scores"][n]["first"] for n in mechanisms},
            "role": "first_divergence_per_fresh_source", "dealer_tail_control": False})
    for case, row in controls:
        targets.append({"case": case, "parent_first": row["scores"]["parent"]["first"],
            "prototype_first": {n: row["scores"][n]["first"] for n in row["first_changed"]},
            "role": "last_hand_no_future_dealer_control", "dealer_tail_control": False})
    # 原型没跨越边界仍可检验真正的问题：当前合法胡与父代继续等的首手代价。
    # 它是合法首动作控制，不是第四份算法，也没有虚构C臂。
    hu_sources = set()
    for row in comparison["rows"]:
        case = cases[row["label"]]
        if (not row["label"].startswith(("fresh:", "supplement:"))
                or "hu" not in case["legal_action_keys"] or row["scores"]["parent"]["first"] == "hu"
                or case["root_id"] in hu_sources or len(hu_sources) >= 4):
            continue
        target = next((t for t in targets if t["case"]["window_key"] == case["window_key"]), None)
        if target is None:
            if len(targets) >= 12:
                continue
            target = {"case": case, "parent_first": row["scores"]["parent"]["first"],
                      "prototype_first": {}, "role": "legal_hu_now_vs_parent_wait",
                      "dealer_tail_control": False}
            targets.append(target)
        target["first_action_controls"] = {"hu_now": "hu"}
        hu_sources.add(case["root_id"])
    dealer_count = 0
    dealer_arms = 0
    for target in targets:
        obs = target["case"]["observation"]
        arms = 1 + 2 * len(target["prototype_first"]) + len(target.get("first_action_controls", {}))
        if obs["dealer_seat"] == 0 and obs["round_no"] < 8 and dealer_count < 2 and dealer_arms + arms <= 14:
            target["dealer_tail_control"] = True
            dealer_count += 1
            dealer_arms += arms
    assert len(targets) <= 12
    assert 4 * sum(1 + 2 * len(t["prototype_first"]) + len(t.get("first_action_controls", {})) for t in targets) <= 336
    files = [_project_file(_PROJECT_ROOT, HERE / "mechanism-comparison/CLOSURE.json"), _project_file(_PROJECT_ROOT, HERE / "PROTOTYPES-FROZEN.json"),
             _project_file(_PROJECT_ROOT, HERE / "mechanism-comparison-supplement/CLOSURE.json"),
             _project_file(_PROJECT_ROOT, HERE / "DIAGNOSTIC-PLAN.json"), _project_file(_PROJECT_ROOT, HERE / "DIAGNOSTIC-EXECUTION-BATCH.json"),
             _project_file(_PROJECT_ROOT, HERE / "parent-source.py"), _project_file(_PROJECT_ROOT, HERE / "prepare_causal.py"), _project_file(_PROJECT_ROOT, HERE / "run_causal.py")]
    files += [_project_file(_PROJECT_ROOT, ROOT / t["case"]["source_closure"]) for t in targets]
    files += sorted((_project_file(_PROJECT_ROOT, HERE / "diagnostic-prototypes")).glob("*.py"))
    save(_project_file(_PROJECT_ROOT, HERE / "CAUSAL-PLAN.json"), {"schema": "t182-mechanism-causal/1", "targets": targets,
        "files": {str(p): pin(p) for p in files}, "source_manifest": comparison["cases"] and
            json.loads((_project_file(_PROJECT_ROOT, HERE / "DIAGNOSTIC-PLAN.json")).read_text())["source_manifest"],
        "worlds_per_target": 4, "sampler": "public-consistent-hidden-world/production-engine",
        "sampler_interpretation": "公开相容等权稳健性样本，非历史策略后验或真实胡牌概率",
        "max_single_hand_continuations": 336, "max_remaining_table_continuations": 14,
        "wall_seconds_per_target": 3600, "step_limit": 50000,
        "capture_limits": {"max_view_json_bytes": 67108864, "max_total_json_bytes": 536870912,
                           "max_unique_views": 4096},
        "A": "固定S02从共同起点持续续打", "B": "首动作改为原型首选，其后全部固定S02",
        "C": "机制原型从共同起点持续续打", "new_model_calls": 0,
        "strength_and_official_deadline_evidence": False,
        "full_table_control": "至多两个当前我方庄家非末单局目标，仅第一个隐藏样本续到桌末",
        "reuse": "同一公开起点、首动作、续策、对手、世界及终点全等的B臂精确复用A或已执行B"})
    print({"targets": len(targets), "divergence_sources": len(selected), "last_hand_controls": len(controls),
           "dealer_tail_controls": dealer_count, "hu_now_source_controls": len(hu_sources),
           "new_worlds_scores_continuations": 0})


if __name__ == "__main__":
    main()
