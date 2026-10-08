"""保留两次失败后补b3至b9；公开指南采集之间额外间隔2秒。

只复用已成功封存的b0至b2来源；有download-error或缺source的目录隔离，
即使已有events.json也不计成功。没有建房、参赛、续局或候选评分。
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

import json
import os
from pathlib import Path
import sys
import time

ROOT = _PROJECT_ROOT
HERE = Path(__file__).resolve().parent
BASE = _project_file(_PROJECT_ROOT, ROOT / "artifacts/sessions/t155-vip-s02-testroom-v5")


def main():
    """只读既有来源后补固定七桌，再用生产唯一规则核验十桌80单局。"""
    os.chdir(ROOT)
    sys.path.insert(0, str(_project_file(_PROJECT_ROOT, ROOT / "src")))
    from hangma_bot.bootstrap import build_public_archive_client, DEFAULT_RULESET_VERSION
    from hangma_bot.adapters.official.archive_download import collect_test_room
    from hangma_bot.offline.postgame import diagnose_official
    room = json.loads((_project_file(_PROJECT_ROOT, HERE / "ROOM-CREATED-REDACTED.json")).read_text())["room_id"]
    valid = {}
    for path in BASE.glob("official/dl-*"):
        if (path / "download-error.json").exists() or not (path / "source.json").exists():
            continue
        source = json.loads((path / "source.json").read_text())
        assert source["room_id"] == room and source["batch"] not in valid
        valid[source["batch"]] = path
    assert set(valid) == {0, 1, 2}
    with (_project_file(_PROJECT_ROOT, HERE / "SUPPLEMENTAL-CAPTURE-V2-START.json")).open("x") as stream:
        json.dump({"fixed_existing_valid_batches": [0, 1, 2], "fixed_remaining_batches": list(range(3, 10)),
                   "extra_spacing_between_batches_seconds": 2, "previous_failures_preserved": True,
                   "new_rooms": 0, "new_candidate_choose": 0}, stream, indent=2)
        stream.write("\n")
    results = []
    with build_public_archive_client({"base_url": "https://10.240.169.190:18080",
                                      "insecure_hosts": ["10.240.169.190"]}) as client:
        for batch in range(3, 10):
            time.sleep(2)
            result = collect_test_room(client, room, batch, BASE)
            results.append(result)
            valid[batch] = Path(result["directory"])
            print(json.dumps({"batch": batch, "captured": True}), flush=True)
    with (_project_file(_PROJECT_ROOT, HERE / "SUPPLEMENTAL-OFFICIAL-CAPTURE-V2.json")).open("x") as stream:
        json.dump({"room_id": room, "additional_results": results}, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    assert set(valid) == set(range(10))
    config = json.loads((_project_file(_PROJECT_ROOT, ROOT / ".private/t155-vip-s02-testroom-v5/rule-config.json")).read_text())
    checks = [diagnose_official(path / "events.json", path / "rule-readback", ruleset_version=DEFAULT_RULESET_VERSION,
                                rule_config=config) for batch, path in sorted(valid.items())]
    assert len({c["game_id"] for c in checks}) == 10 and sum(len(c["rounds"]) for c in checks) == 80
    with (_project_file(_PROJECT_ROOT, HERE / "ALL-TABLES-OFFICIAL-RULE-READBACK.json")).open("x") as stream:
        json.dump({"checks": checks, "first_postgame_scope_tables": 1, "first_postgame_scope_hands": 8,
                   "full_audit_validation_in_first_postgame": True,
                   "all_40_observation_views_official_field_recheck": False}, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(json.dumps({"official_tables_checked": 10, "official_hands_checked": 80,
                      "existing_postgame_not_rebuilt": True}), flush=True)


if __name__ == "__main__":
    main()
