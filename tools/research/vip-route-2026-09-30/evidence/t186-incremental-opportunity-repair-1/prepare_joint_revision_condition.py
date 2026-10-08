"""封存全部可精确恢复的实际改选与正负控制，区分原历史世界和条件抽样。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t186-incremental-opportunity-repair-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PRIOR = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t185-evidence-prioritized-joker-evolution-1')
sys.path.insert(0, str(PRIOR))
from common import pin, save
from hangma_bot.offline.vip_eoh_generate import VipEohBatch, load_vip_parents


def main():
    """32目标、320条单局；不将已暴露反例、重复换座和原世界算独立强度。"""
    path = _project_file(_PROJECT_ROOT, HERE / "JOINT-REVISION-CONDITION-PLAN.json")
    assert not path.exists()
    batch = VipEohBatch.read(_project_file(_PROJECT_ROOT, HERE / "AUTHOR-BATCH.json"))
    child = load_vip_parents([_project_file(_PROJECT_ROOT, HERE / "AUTHOR-joint-revision-model-output")], batch)[0]
    parent = load_vip_parents([_project_file(_PROJECT_ROOT, HERE / "AUTHOR-resource-release-metadata-repaired")], batch)[0]
    gatepath = _project_file(_PROJECT_ROOT, HERE / "joint-revision-qualification/CLOSED.json")
    gate = json.loads(gatepath.read_text())
    assert gate["complete"] and gate["mechanical_passed"] and gate["identity"] == child["identity"]
    rowsfile = _project_file(_PROJECT_ROOT, HERE / "joint-revision-qualification/rows.jsonl")
    assert gate["rows_pin"] == pin(rowsfile)
    rows = [json.loads(line) for line in rowsfile.read_text().splitlines()]
    caseplanpath = _project_file(_PROJECT_ROOT, HERE / "JOINT-REVISION-QUALIFICATION-PLAN.json")
    caseplan = json.loads(caseplanpath.read_text())
    assert gate["plan_pin"] == pin(caseplanpath)
    assert all(pin(Path(p)) == h for p, h in caseplan["files"].items())
    cases = {c["label"]: c for c in caseplan["cases"]}
    recoverable = lambda r: r["label"].startswith(("closed-confirmation:", "development-stage"))
    selected = [(r, "公开面板全部可恢复实际改选，不挑续打结果") for r in rows if r["first_changed"] and recoverable(r)]
    excluded = [{k: r[k] for k in ("label", "root_id", "classes", "parent_first", "candidate_first")}
                for r in rows if r["first_changed"] and not recoverable(r)]
    assert len(selected) == 29 and len(excluded) == 2
    old_cases = {c["label"]: c for c in json.loads((_project_file(_PROJECT_ROOT, HERE / "CASES.json")).read_text())["cases"]}
    negative = next(r for r in rows if r["root_id"] == "t185-confirmation-002" and "wait_lost" in r["classes"])
    positive = next(r for r in rows if r["label"] == "development-stage2:015:2")
    unresolved = next(r for r in rows if r["label"] == "development-stage3:020:0")
    assert not negative["first_changed"] and not positive["first_changed"] and not unresolved["first_changed"]
    selected.extend([(negative, "历史失胡未改选控制，原世界与随机相容世界分开报告"),
                     (positive, "三白保听已兑现财飘爆头正控制，首手相同仍分别持续续打"),
                     (unresolved, "尚未改选的无白大牌损失控制，后继路径仍可能不同")])
    assert len(selected) == 32 and len({r["label"] for r, _ in selected}) == 32
    originals = {f"closed-confirmation:{r['ordinal']:03d}": r for r in
                 map(json.loads, (_project_file(_PROJECT_ROOT, HERE / "confirmation-paths/rows.jsonl")).read_text().splitlines())}
    targets, closures = [], []
    for row, reason in selected:
        case = dict(cases[row["label"]])
        case["legal_action_keys"] = sorted(e["action_key"] for e in row["entries"])
        if row["label"].startswith("development-stage"):
            _, rootstr, seatstr = row["label"].split(":")
            seat, root = int(seatstr), int(rootstr)
            closurepath = _project_file(_PROJECT_ROOT, HERE / f"natural-development/root-{root:03d}/seat-{seat}-arm-1/CLOSURE.json")
        else:
            old = originals[row["label"]]
            seat, root = old["rotation"], old["root_index"]
            closurepath = _project_file(_PROJECT_ROOT, PRIOR / f"natural-confirmation/root-{root:03d}/seat-{seat}-arm-1/CLOSURE.json")
        closure = json.loads(closurepath.read_text())
        assert closure["complete"] and closure["failure"] is None and closure["rotation"] == seat
        targets.append({"case": case, "composition": closure["root"], "focal_seat": seat,
            "source_closure": str(closurepath), "parent_first": row["parent_first"],
            "candidate_first": row["candidate_first"], "selection": reason})
        closures.append(closurepath)
    files = [Path(__file__), _project_file(_PROJECT_ROOT, HERE / "run_joint_revision_condition.py"), _project_file(_PROJECT_ROOT, HERE / "AUTHOR-BATCH.json"),
        gatepath, rowsfile, caseplanpath, _project_file(_PROJECT_ROOT, HERE / "CASES.json"), _project_file(_PROJECT_ROOT, HERE / "confirmation-paths/rows.jsonl"),
        _project_file(_PROJECT_ROOT, HERE / "AUTHOR-joint-revision-model-output/candidate.py"), _project_file(_PROJECT_ROOT, HERE / "AUTHOR-joint-revision-model-output/generation.json"),
        _project_file(_PROJECT_ROOT, HERE / "AUTHOR-resource-release-metadata-repaired/candidate.py"), _project_file(_PROJECT_ROOT, HERE / "AUTHOR-resource-release-metadata-repaired/generation.json"),
        _project_file(_PROJECT_ROOT, PRIOR / "reuse_causal_helpers.py"), _project_file(_PROJECT_ROOT, PRIOR / "evaluation_sharding.py"), _project_file(_PROJECT_ROOT, PRIOR / "common.py"), *closures]
    original = json.loads((_project_file(_PROJECT_ROOT, PRIOR / "CONFIRMATION-PLAN.json")).read_text())
    plan = {"schema": "t186-joint-revision-conditional-screen/1", "targets": targets,
        "arms_sources": {"parent": {"source_file": str(_project_file(_PROJECT_ROOT, HERE / "AUTHOR-resource-release-metadata-repaired/candidate.py")),
                                    "identity": parent["identity"]},
                         "child": {"source_file": str(_project_file(_PROJECT_ROOT, HERE / "AUTHOR-joint-revision-model-output/candidate.py")),
                                   "identity": child["identity"]}},
        "files": {str(p): pin(p) for p in files}, "source_manifest": original["source_manifest"],
        "worlds_per_target": 4, "historical_original_world_per_target": 1,
        "planned_single_hand_continuations": 320, "cpu_worker_count": 4,
        "step_limit": 50000, "wall_seconds_per_target": 1800,
        "capture_limits": {"max_view_json_bytes": 67108864, "max_total_json_bytes": 536870912, "max_unique_views": 4096},
        "A": "357e持续自行选择", "C": "a0c7218a持续自行选择；首手相同也不得复用A",
        "sample_0": "已暴露原历史世界；精确原前缀动作恢复，不属于新的自然独立抽样",
        "samples_1_2_3_4": "等权公开相容暗牌及余墙联合洗牌；非真实对手后验或自然频率",
        "readout": "全目标资源自然闭合后，原历史世界和相容抽样分两表；按不同来源分组，逐评分及番值、支付、失胡对账。",
        "excluded_changed_public_windows": excluded,
        "excluded_boundary": "官方及早期诊断两改选窗仅机械通过；当前工具未封存可精确恢复的原完整桌，不冒充已续打。",
        "same_source_rotations_and_multiple_cases_not_independent": True,
        "online_or_strength_admission": False, "additional_model_calls": 0,
        "automatic_table_or_confirmation_dispatch": False}
    save(path, plan)
    print(json.dumps({"prepared": True, "targets": 32, "planned_single_hand_continuations": 320,
        "actual_worlds_scores_tables": 0, "excluded_public_changed_windows": 2}))


if __name__ == "__main__":
    main()
