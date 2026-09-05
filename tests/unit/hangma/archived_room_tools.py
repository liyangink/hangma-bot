#!/usr/bin/env python3
"""归档测试房间数据拉取工具（离线对拍夹具刷新）。

官方依据：指南 §2.5（v14，2026-09-05 抓取）——测试房间任一局结束后，
用房间 id 即可免认证拉取完整对战事件流（含四家开局手牌与官方每局结算）：

    GET https://10.240.169.190:18080/api/test-rooms/{id}/games
    GET https://10.240.169.190:18080/api/test-rooms/{id}/games/{batch}/events

- 限速：每房间独立 5/s（主闸）+ 每来源兜底 1000/s（指南变更日志 v9）；
  本脚本按 0.25s/请求 保守节流。
- TLS：部署实例为内网自签证书，仅对该固定主机关闭证书校验
  （仓库安全约束允许的唯一例外，见根 AGENTS.md §6）；不修改全局 TLS。
- 批次与轮次重号（指南变更日志 v4）：/games/{batch}/events 解析为该房间
  最新一轮同批号场次，历史轮场次需按 game_id 走门户登录态接口，本脚本
  不处理（离线对拍只需最新轮即可）。
- 数据不含 Token/Authorization；房间 id 即凭证，勿公网分享。

本文件是测试代码（拉取工具按任务要求放在测试侧，不进 src/hangma_bot/hangma）；
hangma 模块保持无网络/文件/时间依赖。

用法：
    .venv/bin/python tests/unit/hangma/archived_room_tools.py t_6c121bfda7e8 [输出目录]

输出：{fixtures}/hangma/archived-rooms/{room_id}_b{batch}.json（默认输出目录）。

来源与口径说明见 tests/fixtures/hangma/README.md。
"""

from __future__ import annotations

import json
import ssl
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

_BASE = "https://10.240.169.190:18080"
_RATE_LIMIT_SECONDS = 0.25  # 每房间 5/s 主闸的保守节流

_CTX = ssl.create_default_context()
_CTX.check_hostname = False
_CTX.verify_mode = ssl.CERT_NONE  # 仅针对官方内网自签名证书，见模块 docstring


def _get(path: str):
    """GET JSON；对 404/403/429 给出可读错误，不自动重试。"""

    request = urllib.request.Request(_BASE + path)
    try:
        with urllib.request.urlopen(request, timeout=30, context=_CTX) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise SystemExit(
            "GET {0} -> HTTP {1}: {2}".format(
                path, exc.code, exc.read().decode("utf-8", errors="replace")[:300],
            )
        ) from None


def pull_room(room_id: str, out_dir: Path) -> int:
    """拉取房间游戏列表与各批次事件流，写入 {room_id}_b{batch}.json。"""

    games = _get("/api/test-rooms/{0}/games".format(room_id)).get("games") or []
    batches = sorted({game["batch"] for game in games if game.get("status") == "finished"})
    if not batches:
        raise SystemExit("房间 {0} 无 finished 场次可拉取".format(room_id))
    out_dir.mkdir(parents=True, exist_ok=True)
    written = 0
    for batch in batches:
        doc = _get("/api/test-rooms/{0}/games/{1}/events".format(room_id, batch))
        path = out_dir / "{0}_b{1}.json".format(room_id, batch)
        path.write_text(
            json.dumps(doc, ensure_ascii=False, indent=None), encoding="utf-8"
        )
        written += 1
        print("已保存", path, "(game_id=", doc.get("game_id"), "blocks=", len(doc.get("blocks") or []), ")")
        time.sleep(_RATE_LIMIT_SECONDS)
    return written


def main(argv):
    if not argv:
        raise SystemExit(__doc__)
    room_id = argv[0]
    out_dir = Path(argv[1]) if len(argv) > 1 else (
        Path(__file__).resolve().parents[2] / "fixtures" / "hangma" / "archived-rooms"
    )
    pull_room(room_id, out_dir)


if __name__ == "__main__":
    main(sys.argv[1:])
