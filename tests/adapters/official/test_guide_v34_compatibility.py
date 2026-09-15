"""指南 v34 的审查登记：本轮 4 条条目已逐条评审，并防回溯改写。

来源为 2026-09-15 同步的官方完整指南快照
（doc/references/official-guide-version-v34.json，updated_at=2026-09-14）。
本批审查覆盖：

- v31（changed）：局间固定停 5 秒——窗口内 phase="settled"、round_no 仍是刚结束那一局；
- v32（changed）：杠爆判定改在杠动作时重算——不自行构造结算者零改动；
- v33（changed）：杠后补牌停出决策窗口——与普通摸牌同构，主动判胡提交 hu 者零改动；
- v34（added）：门户今日榜 last 垫底行——纯 Portal 面加法，玩家 API 零影响。

**v31—v34 没有 breaking 条目，因此版本门不会拦截它们**；这里额外把四条已审查条目
按完整内容指纹钉住，使官方变更日志的**回溯改写**（同版本改写既有条目）能被检出——
这正是 dto.py 中「v16 之后仍逐条验摘要，不能仅按顶层版本放行」的落地方式。
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from hangma_bot.adapters.official.dto import KNOWN_GUIDE_VERSION, parse_guide_version


GUIDE_V34 = Path(__file__).parents[3] / "doc/references/official-guide-version-v34.json"

# 2026-09-15 评审时四条条目的完整内容指纹（键序无关、非 ASCII 不转义）。
REVIEWED_V34_ENTRIES = {
    31: ("changed", "2589060b121107842731c33d8e435e06dc8155743d50c32add6045d11f511b8e"),
    32: ("changed", "de547f0f26b1127a7c4edd9940965ad04a72b0af5e2f4df0145a40c90f20f740"),
    33: ("changed", "e9d1bdcaf63b613d29fcc9e28dbc2c492a8316c7962ef195d19d9f76d59ae759"),
    34: ("added", "f90104094ea6e0517e73853058a6058858b6c4115c529425af6dd7dafbeae144"),
}


def _entry_hash(entry: dict) -> str:
    """按 dto.parse_guide_version 的同一规范化口径计算条目指纹。"""

    canonical = json.dumps(
        entry, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _load_v34() -> dict:
    return json.loads(GUIDE_V34.read_text(encoding="utf-8"))


def test_reference_guide_v34_snapshot_parses() -> None:
    """v34 真实快照按本 bot 的实际调用路径解析，且无未审查 breaking。

    必须带 scoped_tournament=True：v24 的 breaking 只对赛事令牌路径放行，
    无调用上下文时 parse_guide_version 会（按设计）保守地报未知 breaking。
    """

    parsed = parse_guide_version(_load_v34(), scoped_tournament=True)
    assert parsed.version == 34
    assert parsed.updated_at == "2026-09-14"
    assert parsed.has_unknown_breaking_change is False
    # 本地已审查基线不得落后于快照版本，否则启动自检会误拦当前平台。
    assert KNOWN_GUIDE_VERSION >= parsed.version


def test_v31_to_v34_entries_are_the_reviewed_ones() -> None:
    """四条已审查条目的类型与完整内容未被回溯改写。"""

    changes = {item.get("version"): item for item in _load_v34()["changes"]}
    for version, (expected_type, expected_hash) in REVIEWED_V34_ENTRIES.items():
        entry = changes.get(version)
        assert entry is not None, "v{} 条目缺失：官方变更日志被改写或抓取不完整".format(version)
        assert entry["type"] == expected_type
        assert _entry_hash(entry) == expected_hash, (
            "v{} 条目内容与 2026-09-15 评审时不一致，需重新逐条审查".format(version)
        )


def test_retroactive_breaking_entry_is_still_blocked() -> None:
    """本轮 0 条 breaking 不等于门禁放行未来条目：新增 breaking 仍必须拦下。"""

    doc = _load_v34()
    doc["changes"] = list(doc["changes"]) + [{
        "version": 35,
        "date": "2026-09-16",
        "type": "breaking",
        "summary": "假设的未来破坏性变更",
        "detail": "本用例只验证门禁行为，不对应任何真实官方条目。",
    }]
    assert parse_guide_version(doc, scoped_tournament=True).has_unknown_breaking_change is True
