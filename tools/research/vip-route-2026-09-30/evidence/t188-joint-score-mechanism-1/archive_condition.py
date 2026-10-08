"""精确封存已闭84单局原件和费用结论，保留原文件，不追加实验。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t188-joint-score-mechanism-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
import hashlib
import io
import json
import sys
import tarfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_project_file(_PROJECT_ROOT, HERE.parent / "t185-evidence-prioritized-joker-evolution-1")))
from common import pin, save
from t185_prepare_confirmation import background_priority


def main():
    """全部自然终态、评分、源身份及资源闭合后逐成员核原字节。"""
    background_priority()
    output = _project_file(_PROJECT_ROOT, HERE / "CONDITION-EVIDENCE-ARCHIVE.json")
    archive_path = _project_file(_PROJECT_ROOT, HERE / "CONDITION-CLOSED.tar.gz")
    assert not output.exists() and not archive_path.exists()
    closed = json.loads((_project_file(_PROJECT_ROOT, HERE / "CONDITION-CLOSED.json")).read_text())
    budget = json.loads((_project_file(_PROJECT_ROOT, HERE / "PILOT-BUDGET-DECISION.json")).read_text())
    assert closed["complete"] and closed["source_stable"] and closed["resources_released"]
    assert closed["counts"]["single_hand_dispatched"] == 84 and budget["complete"]
    assert closed["plan_pin"] == pin(_project_file(_PROJECT_ROOT, HERE / "CONDITION-PLAN.json"))
    assert not budget["natural_strength_or_online_admission"]
    paths = [p for p in (_project_file(_PROJECT_ROOT, HERE / "condition")).rglob("*") if p.is_file() and not p.is_symlink()]
    names = ["CONDITION-PLAN.json", "CONDITION-PLAN-NOTES.json", "CONDITION-CLOSED.json",
        "PILOT-BUDGET-DECISION.json", "prepare_condition.py", "run_condition.py",
        "close_condition.py", "close_budget.py", "archive_condition.py"]
    paths.extend(_project_file(_PROJECT_ROOT, HERE / name) for name in names)
    originals = {str(p.relative_to(HERE)): pin(p) for p in paths}
    assert len(originals) == len(paths)
    with tarfile.open(archive_path, "x:gz") as stored:
        for path in sorted(paths):
            raw = path.read_bytes()
            item = tarfile.TarInfo(str(path.relative_to(HERE)))
            item.size, item.mode, item.mtime = len(raw), 0o644, 0
            stored.addfile(item, io.BytesIO(raw))
    with tarfile.open(archive_path, "r:gz") as stored:
        assert sorted(stored.getnames()) == sorted(originals)
        for relative, expected in originals.items():
            raw = stored.extractfile(relative).read()
            assert {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()} == expected
    assert all(pin(_project_file(_PROJECT_ROOT, HERE / relative)) == expected for relative, expected in originals.items())
    save(output, {"complete": True, "archive": archive_path.name, "archive_pin": pin(archive_path),
        "originals": originals, "verified_exact_bytes": True, "originals_retained_unchanged": True,
        "actual_single_hands": 84, "actual_score_calls": closed["counts"]["actual_score_calls"],
        "actual_complete_tables": 0, "64_table_pilot_budget_eligible": budget["64_table_pilot_budget_eligible"],
        "new_scores_models_HTTP_worlds_tables": 0})
    print(json.dumps({"complete": True, "members": len(originals),
        "archive_bytes": archive_path.stat().st_size}))


if __name__ == "__main__":
    main()
