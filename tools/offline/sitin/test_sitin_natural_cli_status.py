"""自然面板命令行必须用非零退出码暴露不可用结果；零模拟、零模型调用。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/llm-guided-heuristic-route-2026-09-15/tools'

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

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sitin_natural_panel as natural


@pytest.mark.parametrize("status,completeness,expected_ok", [
    ("ok", ["complete", "complete"], True),
    ("invalid_only", ["invalid", "invalid"], False),
    ("ok", ["complete", "invalid"], False),
    ("insufficient_roots", ["complete"], False),
    ("empty", [], False),
])
def test_cli_exit_and_ok_agree_with_usable_complete_panel(tmp_path, monkeypatch, capsys,
                                                        status, completeness, expected_ok):
    """即使统计对象误称ok，存在坏样本仍不能向自动监督器报告成功。"""
    source = tmp_path / "candidate.py"
    source.write_text("# no execution in this test\n")
    auth = tmp_path / "auth.json"
    auth.write_text("{}")
    panel = {"identity": {"candidate_id": "fixture"},
        "samples": [{"completeness": value} for value in completeness],
        "cost": {"tables_full_executed": 0, "wall_sec": 0},
        "statistics": {"by_candidate": {"fixture": {"panels": {"normal": {
            "panels": {"H": {"status": status}}}}}}}}
    monkeypatch.setattr(natural, "run_natural_panel", lambda **kwargs: panel)
    code = natural.main(["--candidate-source", str(source), "--opponent", "H",
        "--contract-file", str(natural.REPO / natural.DEFAULT_CONTRACT),
        "--out", str(tmp_path / "out"), "--authorization", str(auth),
        "--ledger", str(tmp_path / "ledger.json")])
    result = json.loads(capsys.readouterr().out)
    assert result["ok"] is expected_ok
    assert (code == 0) is expected_ok
