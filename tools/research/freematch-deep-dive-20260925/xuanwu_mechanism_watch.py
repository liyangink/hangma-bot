#!/usr/bin/env python3
"""按当前官方归档重跑玄武同桌机制计数，不沿用四房冻结名单。

官方牌谱和发布身份分别由现有审计入口读取；牌形派生量仍由
``independent_xuanwu_four_room_audit`` 调用生产规则模块重建。
"""

from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/freematch-deep-dive-20260925'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

import io
import json
from contextlib import redirect_stdout

import independent_xuanwu_four_room_audit as anatomy
from extract_room_scores import load_rooms
from peer_score_watch import manifest_identity


def main() -> None:
    """输出按当前归档动态选房的同桌机制表；缺失发布身份时失败。"""

    identities = manifest_identity()
    mapping: dict[str, str] = {}
    for _mtime, room, _tag, _game_id, doc in load_rooms():
        seats = [seat.get("user_id") for seat in doc.get("seats") or []]
        if anatomy.US not in seats or anatomy.XUANWU not in seats:
            continue
        if room not in identities:
            raise ValueError(f"玄武同桌房缺发布身份：{room}")
        version = identities[room][0]
        mapping[room] = (
            "R18 v1" if version == "r18_integrated_positive_v1" else
            "R18 v2" if version == "r18_integrated_positive_v2" else
            version
        )
    if not mapping:
        raise ValueError("当前官方归档没有玄武同桌房")
    anatomy.ROOM_VERSION = mapping
    output = io.StringIO()
    with redirect_stdout(output):
        anatomy.main()
    result = json.loads(output.getvalue())
    result["all_shared_rooms"] = result.pop("all_four_rooms")
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
