"""按真实改选冻结候选三臂小续打；只读公开开发输入，不按结局挑题。"""

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
import argparse
import json
from pathlib import Path

from hangma_bot.offline.vip_eoh_generate import VipEohBatch, load_vip_parents
from prepare_diagnostics import pin, save

HERE = Path(__file__).resolve().parent
ROOT = _PROJECT_ROOT


def main(packages):
    """每候选最多三母来源，各四隐藏样本；最多108次实际单局续打。"""
    assert 1 <= len(packages) <= 3
    batch = VipEohBatch.read(_project_file(_PROJECT_ROOT, HERE / "AUTHOR-BATCH.json"))
    panels = [json.loads((_project_file(_PROJECT_ROOT, HERE / d / "CLOSURE.json")).read_text()) for d in
              ("mechanism-comparison", "mechanism-comparison-supplement")]
    assert all(p["complete"] and p["source_stable"] for p in panels)
    cases = {c["label"]: c for p in panels for c in p["cases"]}
    targets = []
    files = [_project_file(_PROJECT_ROOT, HERE / "AUTHOR-BATCH.json"), _project_file(_PROJECT_ROOT, HERE / "parent-source.py"), _project_file(_PROJECT_ROOT, HERE / "DIAGNOSTIC-PLAN.json"),
             _project_file(_PROJECT_ROOT, HERE / "NUMERICAL-TIE-AUDIT.json"), Path(__file__), _project_file(_PROJECT_ROOT, HERE / "run_candidate_causal.py"),
             _project_file(_PROJECT_ROOT, HERE / "close_candidate_causal.py"), _project_file(_PROJECT_ROOT, HERE / "close_diagnosis.py"),
             _project_file(_PROJECT_ROOT, HERE / "run_causal.py"), _project_file(_PROJECT_ROOT, HERE / "run_diagnostic_sources.py"), _project_file(_PROJECT_ROOT, HERE / "prepare_diagnostics.py"),
             _project_file(_PROJECT_ROOT, ROOT / "src/hangma_bot/offline/forced_action.py")]
    files += [_project_file(_PROJECT_ROOT, HERE / d / "CLOSURE.json") for d in ("mechanism-comparison", "mechanism-comparison-supplement")]
    candidate_ids = set()
    for name in packages:
        package = Path(name).resolve()
        assert package.parent == HERE
        loaded = load_vip_parents([package], batch)[0]
        assert loaded["identity"]["candidate_id"] not in candidate_ids
        candidate_ids.add(loaded["identity"]["candidate_id"])
        gate = _project_file(_PROJECT_ROOT, HERE / (package.name + "-qualification/CLOSURE.json"))
        qualification = json.loads(gate.read_text())
        assert qualification["complete"] and qualification["development_eligible"]
        assert qualification["identity"] == loaded["identity"]
        eligible_rows = []
        for row in qualification["rows"]:
            if not row.get("meaningful_first_changed") or not row["label"].startswith(("fresh:", "supplement:")):
                continue
            case = cases[row["label"]]
            key = (case["window_key"]["round_no"], case["window_key"]["trigger_seq"])
            eligible_rows.append((case["root_id"], key, case, row))
        assert eligible_rows
        chosen = []
        used_sources = set()
        # 按行动前类别覆盖关键机制，不用任何结局或续打积分选题。
        # 每类别取来源键/窗口序最早且不同母来源的一窗；不足时顺序补齐。
        for group in ("early_discard", "hu_or_gang", "claim", "any"):
            for root_id, _, case, row in sorted(eligible_rows, key=lambda e: (e[0], e[1])):
                classes = case["classes"]
                belongs = (group == "any"
                    or group == "early_discard" and any(c.startswith("early_") for c in classes)
                    or group == "hu_or_gang" and any("current_hu" in c or "gang_option" == c for c in classes)
                    or group == "claim" and "claim_option" in classes)
                if not belongs or root_id in used_sources or len(chosen) >= 3:
                    continue
                chosen.append((case, row, group))
                used_sources.add(root_id)
                if group != "any":
                    break
        for case, row, group in chosen:
            assert row["parent_first"] != row["candidate_first"]
            targets.append({"case": case, "parent_first": row["parent_first"],
                "candidate_first": row["candidate_first"], "package": str(package),
                "candidate_source_file": str(package / "candidate.py"), "identity": loaded["identity"],
                "selection": "先早期弃牌、再胡或杠、再吃碰，各一不同母来源；不足按来源键/窗口序补齐，最多三，不参考结局",
                "selection_group": group})
            files.append(_project_file(_PROJECT_ROOT, ROOT / case["source_closure"]))
        files += [package / "candidate.py", package / "generation.json", gate]
    assert 1 <= len(targets) <= 9
    save(_project_file(_PROJECT_ROOT, HERE / "CANDIDATE-CAUSAL-PLAN.json"), {"schema": "t182-candidate-causal/1", "targets": targets,
        "files": {str(p): pin(p) for p in files},
        "source_manifest": json.loads((_project_file(_PROJECT_ROOT, HERE / "DIAGNOSTIC-PLAN.json")).read_text())["source_manifest"],
        "worlds_per_target": 4, "maximum_actual_single_hand_continuations": 108,
        "planned_single_hand_continuations": len(targets) * 12, "step_limit": 50000,
        "wall_seconds_per_target": 1800,
        "capture_limits": {"max_view_json_bytes": 67108864, "max_total_json_bytes": 536870912,
                           "max_unique_views": 4096},
        "A": "固定S02持续续打", "B": "首动作改为候选选择，其后S02", "C": "候选持续续打",
        "sampler": "public-consistent-hidden-world/production-engine",
        "sampler_interpretation": "等权公开相容样本，非平台真实后验；同母来源共享样本不计独立证据",
        "readout": "全目标终态后统一读B−A、C−A、C−B并分账；负例保留，不用条件积分代替自然桌强度",
        "new_worlds_scores_continuations_models": 0, "official_deadline_or_strength_admission": False})
    print({"targets": len(targets), "planned_continuations": len(targets) * 12, "new_continuations": 0})


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--packages", nargs="+", required=True)
    main(parser.parse_args().packages)
