"""自然完赛后的补充采集：首个postgame只覆盖b0，补b1至b9并独立复核十桌。

只发官方公开档案GET，不建房、续房或重启玩家。首个制品不修改、不删除。
首个制品明确保留其一桌范围；不重复处理全部巨大审计流来复核剩余牌谱。
"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t155-pruned-s02-engineering-testroom-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys

ROOT = _PROJECT_ROOT
HERE = Path(__file__).resolve().parent
BASE = _project_file(_PROJECT_ROOT, ROOT / "artifacts/sessions/t155-vip-s02-testroom-v5")
PRIVATE = _project_file(_PROJECT_ROOT, '.private/t155-vip-s02-testroom-v5')


def main():
    """首个真实外层结束后补九桌；错误保留下载诊断，不伪造全房完整性。"""
    os.chdir(ROOT)
    assert json.loads((_project_file(_PROJECT_ROOT, HERE / "ACTUAL-OUTER-TERMINAL.json")).read_text())["actual_exit_code"] == 0
    assert json.loads((_project_file(_PROJECT_ROOT, HERE / "POSTGAME-CHILD-TERMINAL.json")).read_text())["exit_code"] == 0
    sys.path.insert(0, str(_project_file(_PROJECT_ROOT, ROOT / "src")))
    from hangma_bot.bootstrap import build_public_archive_client, DEFAULT_RULESET_VERSION
    from hangma_bot.adapters.official.archive_download import collect_test_room
    from hangma_bot.offline.postgame import diagnose_official
    room = json.loads((_project_file(_PROJECT_ROOT, HERE / "ROOM-CREATED-REDACTED.json")).read_text())["room_id"]
    results = []
    with build_public_archive_client({"base_url": "https://10.240.169.190:18080",
                                      "insecure_hosts": ["10.240.169.190"]}) as client:
        for batch in range(1, 10):
            result = collect_test_room(client, room, batch, BASE)
            results.append({"batch": batch, "result": result})
            print(json.dumps({"batch": batch, "captured": True}), flush=True)
    with (_project_file(_PROJECT_ROOT, HERE / "SUPPLEMENTAL-OFFICIAL-CAPTURE.json")).open("x") as stream:
        json.dump({"room_id": room, "first_capture_batch": 0, "additional_results": results,
                   "created_at_utc": datetime.now(timezone.utc).isoformat()}, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    checks = []
    config = json.loads((_project_file(_PROJECT_ROOT, PRIVATE / "rule-config.json")).read_text())
    for path in sorted(BASE.glob("official/dl-*/events.json")):
        check = diagnose_official(path, path.parent / "rule-readback", ruleset_version=DEFAULT_RULESET_VERSION,
                                  rule_config=config)
        checks.append(check)
    assert len(checks) == 10 and len({c["game_id"] for c in checks}) == 10
    assert sum(len(c["rounds"]) for c in checks) == 80
    with (_project_file(_PROJECT_ROOT, HERE / "ALL-TABLES-OFFICIAL-RULE-READBACK.json")).open("x") as stream:
        json.dump({"checks": checks, "first_postgame_scope_tables": 1,
                   "first_postgame_scope_hands": 8, "full_audit_validation_in_first_postgame": True,
                   "all_40_observation_views_official_field_recheck": False}, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(json.dumps({"official_tables_checked": 10, "official_hands_checked": 80,
                      "existing_postgame_not_rebuilt": True}), flush=True)


if __name__ == "__main__":
    main()
