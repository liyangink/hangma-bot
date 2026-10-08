"""只读补采 R18 或旧 V2 自由赛的官方牌谱；按 room×batch 断点续传。"""

from __future__ import annotations

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

import argparse
import json
from pathlib import Path
import sys
import time

ROOT = _PROJECT_ROOT
sys.path.insert(0, str(_project_file(_PROJECT_ROOT, ROOT / "src")))

from hangma_bot.adapters.official.archive_download import collect_test_room  # noqa: E402
from hangma_bot.bootstrap import build_public_archive_client  # noqa: E402


ROOM_SUMMARIES = _project_file(_PROJECT_ROOT, 'review/r18-auto-match-2026-09-23/rooms')
CONFIG = _project_file(_PROJECT_ROOT, ROOT / "configs/auto-match.local.json")


def main() -> None:
    """下载公开赛后档案并记录缺失；不访问认证接口或创建赛事。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campaign", choices=("r18", "v2"), default="r18")
    args = parser.parse_args()
    if args.campaign == "r18":
        rooms = sorted(path.stem for path in ROOM_SUMMARIES.glob("a_*.md"))
        out = _project_file(_PROJECT_ROOT, ROOT / "artifacts/sessions/r18-history-redownload-20260923")
        expected_rooms = 31
    else:
        ledger = json.loads((_project_file(_PROJECT_ROOT, ROOT / "review/auto-match-value-2026-09-08/ledger-snapshot.json"))
                            .read_text(encoding="utf-8"))
        rooms = [row["room_id"] for row in ledger["rooms"]]
        out = _project_file(_PROJECT_ROOT, ROOT / "artifacts/sessions/v2-history-redownload-20260923")
        expected_rooms = 40
    if len(rooms) != expected_rooms or len(set(rooms)) != expected_rooms:
        raise SystemExit("房间清单数量或唯一性不符：{0}".format(len(rooms)))
    existing = {}
    for path in (out / "official").glob("dl-*/source.json"):
        source = json.loads(path.read_text(encoding="utf-8"))
        existing[(source["room_id"], source["batch"])] = str(path.parent)
    rows = []
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    with build_public_archive_client(config) as client:
        for index, room in enumerate(rooms, 1):
            completed = 0
            for batch in range(10):
                if (room, batch) in existing:
                    rows.append({"room_id": room, "batch": batch, "status": "present",
                                 "directory": existing[(room, batch)]})
                    completed += 1
                    continue
                for attempt in range(3):
                    try:
                        source = collect_test_room(client, room, batch, out)
                    except ValueError as exc:
                        transient = "HTTP 429" in str(exc) or "ConnectError" in str(exc)
                        if transient and attempt < 2:
                            time.sleep(2 ** (attempt + 1))
                            continue
                        rows.append({"room_id": room, "batch": batch, "status": "failed",
                                     "error_type": type(exc).__name__, "error": str(exc)})
                        break
                    except OSError as exc:
                        rows.append({"room_id": room, "batch": batch, "status": "failed",
                                     "error_type": type(exc).__name__, "error": str(exc)})
                        break
                    else:
                        rows.append({"room_id": room, "batch": batch, "status": "downloaded",
                                     "directory": source["directory"],
                                     "game_id": source["game_id"],
                                     "guide_version": source["guide_version"],
                                     "original_sha256": source["original_sha256"]})
                        completed += 1
                        break
                # archive_download 自身按每次 GET 至少 0.21 秒限速；这里再拉开
                # 批次间的指南请求，避免公共 /portal/api/guide/version 的 429。
                time.sleep(0.5)
            print("{0:02d}/{1} {2}: {3}/10 批次已有官方牌谱".format(
                index, expected_rooms, room, completed), flush=True)
    target = out / "redownload-manifest.json"
    target.write_text(json.dumps({"schema": "r18-free-room-redownload/1", "rows": rows},
                                 ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                      encoding="utf-8")
    print("{0}/{1} 已下载或原已存在；清单：{2}".format(
        sum(row["status"] != "failed" for row in rows), expected_rooms * 10, target), flush=True)


if __name__ == "__main__":
    main()
