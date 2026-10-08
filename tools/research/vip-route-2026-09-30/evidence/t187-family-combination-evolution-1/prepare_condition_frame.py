"""在机械结果读分前固定12来源正负条件集合；线上S02为比较基线。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t187-family-combination-evolution-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
import gzip
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PRIOR = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t185-evidence-prioritized-joker-evolution-1')
LAST = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t186-incremental-opportunity-repair-1')
sys.path.insert(0, str(PRIOR))
from common import pin, save


def main():
    """按既有问题及公开动作类别选不同来源；不读取新机械首选或续打结果。"""
    planpath = _project_file(_PROJECT_ROOT, HERE / "QUALIFICATION-REPAIRED-PLAN.json")
    plan = json.loads(planpath.read_text())
    assert plan["complete"] and all(pin(Path(p)) == h for p, h in plan["files"].items())
    cases = {c["label"]: c for c in plan["cases"]}
    oldrows = _project_file(_PROJECT_ROOT, LAST / "joint-revision-qualification/rows.jsonl")
    old = {r["label"]: r for r in map(json.loads, oldrows.read_text().splitlines())}
    rawpath = _project_file(_PROJECT_ROOT, LAST / "joint-natural-stage-001-paths/original-public-first-rows.jsonl.gz")
    with gzip.open(rawpath, "rt") as stream:
        for line in stream:
            r = json.loads(line)
            c = r["child_original_row"]
            old[f"joint-development:{r['root']:03d}:{r['rotation']}"] = {"entries": c["candidates"]}
    originsfile = _project_file(_PROJECT_ROOT, LAST / "confirmation-paths/rows.jsonl")
    origins = {f"closed-confirmation:{r['ordinal']:03d}": r for r in map(json.loads, originsfile.read_text().splitlines())}
    def source(label):
        """仅按标签找原C桌，恢复时仍须核完整观察、合法集、前缀和实际座位。"""
        if label.startswith("closed-confirmation:"):
            r = origins[label]
            return _project_file(_PROJECT_ROOT, PRIOR / f"natural-confirmation/root-{r['root_index']:03d}/seat-{r['rotation']}-arm-1/CLOSURE.json")
        if label.startswith(("development-stage", "joint-development:")):
            _, root, seat = label.split(":")
            return _project_file(_PROJECT_ROOT, LAST / f"natural-development/root-{int(root):03d}/seat-{int(seat)}-arm-1/CLOSURE.json")
        return None
    selected, used = [], set()
    def add(label, reason):
        """同母来源只选一窗，避免四换座重复放大；公开选择规则记录于计划。"""
        c = cases[label]
        if c["root_id"] in used or source(label) is None:
            return False
        selected.append((label, reason))
        used.add(c["root_id"])
        return True
    for label in ("joint-development:038:0", "joint-development:040:0", "joint-development:035:3",
                  "development-stage2:015:2", "closed-confirmation:004", "closed-confirmation:073"):
        assert add(label, "已暴露七对/提前小胡/双白升番/三白保听/等待失胡正负控制，非指定答案")
    strata = [("chi", lambda c, keys: any(k.startswith("chi:") for k in keys)),
              ("peng", lambda c, keys: any(k.startswith("peng:") for k in keys)),
              ("gang", lambda c, keys: any("gang" in k for k in keys)),
              ("late", lambda c, keys: c["observation"]["remaining_tile_count"] <= 20),
              ("single_white", lambda c, keys: "white_count_1" in c["classes"]),
              ("no_white", lambda c, keys: "white_count_0" in c["classes"])]
    unavailable = []
    for name, predicate in strata:
        matches = [label for label in sorted(cases) if source(label) is not None
                   and cases[label]["root_id"] not in used
                   and predicate(cases[label], [e["action_key"] for e in old[label]["entries"]])]
        if matches:
            assert add(matches[0], f"公开类别{name}中标签字典序首个未用母来源；不看新候选选择或结局")
        else:
            unavailable.append(name)
    for label in sorted(cases):
        if len(selected) == 12:
            break
        add(label, "缺类别按未用来源字典序补齐，不看新评分或未来结局")
    assert len(selected) == 12 and len(used) == 12
    files = {str(p): pin(p) for p in (Path(__file__), _project_file(_PROJECT_ROOT, HERE / "run_condition.py"), _project_file(_PROJECT_ROOT, HERE / "close_condition.py"),
        planpath, oldrows, rawpath, originsfile, _project_file(_PROJECT_ROOT, HERE / "AUTHOR-BATCH.json"), _project_file(_PROJECT_ROOT, PRIOR / "common.py"),
        _project_file(_PROJECT_ROOT, PRIOR / "evaluation_sharding.py"), _project_file(_PROJECT_ROOT, PRIOR / "reuse_causal_helpers.py"), _project_file(_PROJECT_ROOT, LAST / "close_opportunity_probe-v2.py"))}
    targets = []
    for label, reason in selected:
        case = dict(cases[label])
        case["legal_action_keys"] = sorted(e["action_key"] for e in old[label]["entries"])
        closurepath = source(label)
        closure = json.loads(closurepath.read_text())
        assert closure["complete"] and closure["failure"] is None
        assert closure["rotation"] == case["window_key"]["seat"]
        assert sum(r["window_key"] == case["window_key"] for r in closure["outcome"]["decisions"]) == 1
        targets.append({"case": case, "composition": closure["root"], "focal_seat": closure["rotation"],
            "source_closure": str(closurepath), "selection": reason})
        files[str(closurepath)] = pin(closurepath)
    referencepath = _project_file(_PROJECT_ROOT, PRIOR / "CONFIRMATION-PLAN.json")
    reference = json.loads(referencepath.read_text())
    files[str(referencepath)] = pin(referencepath)
    files[reference["parent"]["source_file"]] = pin(Path(reference["parent"]["source_file"]))
    save(_project_file(_PROJECT_ROOT, HERE / "CONDITION-FRAME.json"), {"complete": True, "targets": targets, "files": files,
        "parent": reference["parent"], "source_manifest": reference["source_manifest"],
        "selection_rules_created_before_new_mechanical_readback": True,
        "root_label_validation_fixed_after_mechanical_summary_no_selection_rule_change": True,
        "known_posthoc_controls_not_independent_validation": True,
        "unavailable_public_strata": unavailable, "worlds_per_target": 2,
        "planned_single_hand_continuations": 72, "cpu_worker_count": 4,
        "historical_and_conditional_not_pooled": True, "baseline_is_online_S02_not_failed_research_parent": True,
        "fee_rule_for_64_table_pilot": {"conditional_net_positive": True, "conditional_large_income_nonnegative": True,
            "minimum_distinct_positive_source_groups": 2, "mechanical_complete_required": True,
            "historical_losses_reported_separately_not_all_green_required": True,
            "engineering_budget_choice_not_statistical_guarantee": True},
        "new_scores_worlds_tables_models_HTTP": 0, "natural_or_original_deadline_admission": False})
    print(json.dumps({"complete": True, "targets": len(targets), "origins": len(used),
        "planned_single_hand_continuations": 72, "unavailable_public_strata": unavailable, "new_scores": 0}))


if __name__ == "__main__":
    main()
