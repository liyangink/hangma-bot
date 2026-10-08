"""50ms 反事实统计不能把插有动作 POST 的查询算成连续重挂。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/r18-four-arm-evaluation-2026-09-23'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

import importlib.util
import json
from pathlib import Path


SOURCE = Path(__file__).with_name("analyze_spacing_capacity.py")
SPEC = importlib.util.spec_from_file_location("spacing_capacity_report", SOURCE)
REPORT = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(REPORT)


def _state(queued, started, completed, *, seq=1):
    return {"payload": {"endpoint": "GET /api/games/g/state", "seq_requested": seq,
                        "http_status": 200,
                        "request_timing": {"queued_at_monotonic": queued,
                                           "transport_started_at_monotonic": started,
                                           "completed_at_monotonic": completed,
                                           "scheduler_priority": "DISCARD_WATCH",
                                           "query_purpose": "discard_watch"}}}


def test_short_requeue_counts_only_directly_affected_starts(tmp_path):
    path = tmp_path / "participants/u/raw/t_g.jsonl"
    path.parent.mkdir(parents=True)
    rows = [
        _state(0, 0, .1),
        _state(.101, .12, .2),  # 发起距上一响应 20ms，可直接受底档影响
        _state(.201, .4, .5),   # 很快入队，但共享队列已等过 50ms
        {"payload": {"endpoint": "POST /api/games/g/action"}},
        _state(.501, .52, .6),  # 动作提交打断连续性
    ]
    path.write_text("".join(json.dumps(row) + "\n" for row in rows))
    result = REPORT.analyze_slot(tmp_path)
    assert result["state_get"] == 4
    assert result["short_ordinary_requeue"] == 2
    assert result["observed_start_within_spacing"] == 1
