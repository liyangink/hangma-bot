"""封存第二次实际作者及已闭机械原件；不收正在写入的条件实验。"""

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
from pathlib import Path
from archive_first_stage import HERE, archive, save
from t185_prepare_confirmation import background_priority


def main():
    """核实际调用已结账、机械完整，逐字节归档；原件保留，不重复实验。"""
    background_priority()
    target = _project_file(_PROJECT_ROOT, HERE / "SECOND-AUTHOR-EVIDENCE-ARCHIVE.json")
    assert not target.exists()
    gate = json.loads((_project_file(_PROJECT_ROOT, HERE / "exploration-qualification/CLOSED.json")).read_text())
    generation = json.loads((_project_file(_PROJECT_ROOT, HERE / "AUTHOR-explore-model-output/generation.json")).read_text())
    ledger = json.loads((_project_file(_PROJECT_ROOT, HERE / "AUTHOR-BATCH.vip-eoh-ledger.json")).read_text())
    assert gate["complete"] and gate["mechanical_passed"] and gate["source_stable"]
    assert generation["status"] == "loaded_not_admitted" and generation["identity_stable"]
    assert generation["billing"]["status"] == "settled" and generation["billing"]["actual"]["model_calls"] == 1
    assert generation["identity"] == gate["identity"]
    reservations = ledger["reservations"]
    if isinstance(reservations, dict):
        reservations = list(reservations.values())
    assert all(r["status"] == "settled" for r in reservations)
    paths = []
    for dirname in ("AUTHOR-explore-model-output", "exploration-qualification"):
        paths.extend(p for p in (_project_file(_PROJECT_ROOT, HERE / dirname)).rglob("*") if p.is_file() and not p.is_symlink() and "code_snapshot" not in p.parts)
    names = ["SECOND-AUTHOR-PREPARATION.json", "SECOND-AUTHOR-FEEDBACK.txt", "SECOND-AUTHOR-START.json",
        "AUTHOR-BATCH.vip-eoh-ledger.json", "EXPLORATION-QUALIFICATION-PLAN.json", "EXPLORATION-PREFLIGHT-FIRST-FAILED.json",
        "prepare_exploration_qualification-FIRST-FAILED.py.gz", "run_exploration_qualification-FIRST-FAILED.py.gz",
        "prepare_second_author.py", "run_second_author.py", "prepare_exploration_qualification.py",
        "run_exploration_qualification.py", "archive_second_author.py"]
    paths.extend(_project_file(_PROJECT_ROOT, HERE / name) for name in names)
    proof = archive("SECOND-AUTHOR-AND-MECHANICAL.tar.gz", paths)
    proof.update({"complete": True, "scope": "第二作者及355机械状态已闭原件，条件续打不在此归档",
        "second_actual_model_calls": 1, "actual_mechanical_score_calls": 710,
        "active_condition_excluded": True, "new_scores_models_HTTP_worlds_tables": 0,
        "preparation_ledger_pin_is_before_second_reservation_not_current_state": True})
    save(target, proof)
    print(json.dumps({"complete": True, "members": len(proof["originals"]),
        "raw_bytes": proof["uncompressed_bytes"], "archive_bytes": proof["archive_pin"]["bytes"]}))


if __name__ == "__main__":
    main()
