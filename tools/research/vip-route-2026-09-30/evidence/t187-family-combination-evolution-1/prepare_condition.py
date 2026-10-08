"""机械全闭后绑定条件计划：12原控制加两实际新增改选来源，直接比较S02。"""

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
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PRIOR = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t185-evidence-prioritized-joker-evolution-1')
LAST = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t186-incremental-opportunity-repair-1')
sys.path.insert(0, str(PRIOR))
from common import pin, save
from hangma_bot.offline.vip_eoh_generate import VipEohBatch, load_vip_parents
from prepare_condition_frame import main as unused_frame_main


def main():
    """不按续打结果挑样本；所有实际新改选母来源各取一窗，84实例上限先冻结。"""
    targetpath = _project_file(_PROJECT_ROOT, HERE / "CONDITION-PLAN.json")
    assert not targetpath.exists()
    framepath = _project_file(_PROJECT_ROOT, HERE / "CONDITION-FRAME.json")
    frame = json.loads(framepath.read_text())
    assert frame["complete"] and len(frame["targets"]) == 12
    assert all(pin(Path(p)) == h for p, h in frame["files"].items())
    gatepath = _project_file(_PROJECT_ROOT, HERE / "qualification/CLOSED.json")
    gate = json.loads(gatepath.read_text())
    caseplanpath = _project_file(_PROJECT_ROOT, HERE / "QUALIFICATION-REPAIRED-PLAN.json")
    caseplan = json.loads(caseplanpath.read_text())
    rowsfile = _project_file(_PROJECT_ROOT, HERE / "qualification/rows.jsonl")
    assert gate["complete"] and gate["mechanical_passed"] and gate["source_stable"]
    assert gate["plan_pin"] == pin(caseplanpath) and gate["rows_pin"] == pin(rowsfile)
    assert all(pin(Path(p)) == h for p, h in caseplan["files"].items())
    rows = {r["label"]: r for r in map(json.loads, rowsfile.read_text().splitlines())}
    cases = {c["label"]: c for c in caseplan["cases"]}
    used = {t["case"]["root_id"] for t in frame["targets"]}
    targets = [dict(t) for t in frame["targets"]]
    extra = []
    for label, row in sorted(rows.items()):
        if not row["first_changed"] or cases[label]["root_id"] in used:
            continue
        assert label.startswith("development-stage"), "新增机械改选须有已闭原桌恢复来源"
        _, root, seat = label.split(":")
        closurepath = _project_file(_PROJECT_ROOT, LAST / f"natural-development/root-{int(root):03d}/seat-{int(seat)}-arm-1/CLOSURE.json")
        closure = json.loads(closurepath.read_text())
        assert closure["complete"] and closure["failure"] is None and closure["rotation"] == int(seat)
        case = dict(cases[label])
        case["legal_action_keys"] = sorted(e["action_key"] for e in row["entries"])
        targets.append({"case": case, "composition": closure["root"], "focal_seat": int(seat),
            "source_closure": str(closurepath), "selection": "全部新机械改选母来源各取字典序一窗；尚未续打，不看结局"})
        extra.append(label)
        used.add(case["root_id"])
    assert len(extra) == 2 and len(targets) == 14
    batch = VipEohBatch.read(_project_file(_PROJECT_ROOT, HERE / "AUTHOR-BATCH.json"))
    childpackage = _project_file(_PROJECT_ROOT, HERE / "AUTHOR-family-metadata-repaired")
    child = load_vip_parents([childpackage], batch)[0]
    assert gate["identity"] == child["identity"]
    parent = frame["parent"]
    assert batch.identity(Path(parent["source_file"]).read_text()) == parent["identity"]
    assert parent["identity"]["source_sha256"] == "2a59cbb18aefa3d24aadf0b3df70f5a4359c204b96a3f0dc208f77d53c196f30"
    files = dict(frame["files"])
    for p in (Path(__file__), _project_file(_PROJECT_ROOT, HERE / "run_condition_v2.py"), _project_file(_PROJECT_ROOT, HERE / "close_condition_v2.py"),
              framepath, gatepath, rowsfile, caseplanpath, childpackage / "candidate.py",
              childpackage / "generation.json", childpackage / "DERIVATION.json"):
        files[str(p)] = pin(p)
    for t in targets:
        files[t["source_closure"]] = pin(Path(t["source_closure"]))
        assert sorted(e["action_key"] for e in rows[t["case"]["label"]]["entries"]) == t["case"]["legal_action_keys"]
        t["parent_first"] = None  # 没有当前闭包S02首手缓存，直接真实自行评分，不能猜动作。
        t["candidate_first"] = rows[t["case"]["label"]]["candidate_first"]
    save(targetpath, {"schema": "t187-family-bounded-condition/1", "targets": targets,
        "arms_sources": {"parent": {"source_file": parent["source_file"], "identity": parent["identity"]},
            "child": {"source_file": str(childpackage / "candidate.py"), "identity": child["identity"]}},
        "files": files, "source_manifest": frame["source_manifest"], "worlds_per_target": 2,
        "historical_original_world_per_target": 1, "planned_single_hand_continuations": 84,
        "cpu_worker_count": 4, "step_limit": 50000, "wall_seconds_per_target": 1800,
        "capture_limits": {"max_view_json_bytes": 67108864, "max_total_json_bytes": 536870912, "max_unique_views": 4096},
        "A": "线上S02持续自行选择，首手无缓存但须真实评分/完整合法集；不强制动作",
        "C": "e8dbd753持续自行选择，首手与已闭公开机械评分核同；不强制动作",
        "sample_0": "已暴露原历史世界；不能视为新自然随机验证",
        "samples_1_2": "等权公开相容暗牌和余墙联合洗牌；非真实对手后验或自然频率",
        "additional_mechanical_switch_sources": extra, "condition_frame_pin": pin(framepath),
        "same_source_rotations_and_multiple_cases_not_independent": True,
        "fee_rule_for_64_table_pilot": frame["fee_rule_for_64_table_pilot"],
        "online_or_strength_admission": False, "automatic_table_or_confirmation_dispatch": False})
    print(json.dumps({"complete": True, "targets": len(targets), "additional_mechanical_sources": extra,
        "planned_single_hand_continuations": 84, "actual_worlds_scores_tables_models_HTTP": 0}))


if __name__ == "__main__":
    main()
