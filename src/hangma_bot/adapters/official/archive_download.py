"""免认证官方赛后采集；HTTP 客户端由组合根注入，原始响应字节不改写。"""
import hashlib
import json
import re
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import httpx


def collect_test_room(client, room: str, batch: int, out: Path, *, sleep=time.sleep) -> dict:
    """下载一个完成批次；失败保存状态诊断并抛错，不生成伪造空牌谱。

    每次创建独立目录；请求间隔至少 0.21 秒，遵守房间数据 5/s 上限。
    不发送认证头；source 保存原文字节摘要、采集 UTC 时间和实际指南版本。
    """
    if not re.fullmatch(r"[A-Za-z0-9_-]+", room) or batch < 0:
        raise ValueError("房间标识或批次号不合法")
    folder = out / "official" / ("dl-" + uuid.uuid4().hex)
    folder.mkdir(parents=True, exist_ok=False)
    (folder / "download-started.json").write_text(json.dumps({"room_id": room, "batch": batch}))
    def fail(endpoint, reason, status=None):
        (folder / "download-error.json").write_text(json.dumps({"endpoint": endpoint, "reason": reason, "http_status": status}))
        raise ValueError(f"官方数据下载失败：{reason}，已保存诊断")

    def get(name, endpoint):
        try:
            response = client.get(endpoint)
        except httpx.HTTPError as exc:
            fail(endpoint, type(exc).__name__)
        if response.status_code != 200:
            fail(endpoint, f"HTTP {response.status_code}", response.status_code)
        partial = folder / (name + ".partial")
        partial.write_bytes(response.content)
        partial.replace(folder / name)
        sleep(.21)
        try:
            data = response.json()
        except ValueError:
            fail(endpoint, "invalid_json")
        if not isinstance(data, dict):
            fail(endpoint, "expected_json_object")
        return data
    get("games.json", f"/api/test-rooms/{room}/games")
    events = get("events.json", f"/api/test-rooms/{room}/games/{batch}/events")
    if events.get("room_id") != room or events.get("batch") != batch or events.get("status") != "finished":
        fail(f"/api/test-rooms/{room}/games/{batch}/events", "房间/批次/完赛状态不符")
    version = get("guide-version.json", "/portal/api/guide/version")
    get("guide.json", "/portal/api/guide?format=text")
    source = {"download_id": folder.name, "room_id": room, "batch": batch, "game_id": events["game_id"],
        "guide_version": version.get("version"), "captured_at": datetime.now(timezone.utc).isoformat(),
        "endpoint": f"/api/test-rooms/{room}/games/{batch}/events", "original_sha256": hashlib.sha256((folder / "events.json").read_bytes()).hexdigest()}
    (folder / "source.json").write_text(json.dumps(source, ensure_ascii=False, indent=2) + "\n")
    return {"directory": str(folder), **source}
