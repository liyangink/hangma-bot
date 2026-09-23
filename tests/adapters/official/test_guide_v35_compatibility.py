"""官方指南 v35：同 HTTP 404 的两种房间语义按完整条目审查。"""

import copy
import json
from pathlib import Path

from hangma_bot.adapters.official.dto import KNOWN_GUIDE_VERSION, parse_guide_version


GUIDE = Path(__file__).parents[3] / "doc/references/official-guide-version-v35.json"


def test_reviewed_v35_breaking_is_accepted_only_for_known_entry() -> None:
    """实际调用路径认可已审条目，改写同版本 breaking 时仍拒绝。"""
    document = json.loads(GUIDE.read_text(encoding="utf-8"))
    parsed = parse_guide_version(document, scoped_tournament=True)
    assert parsed.version == KNOWN_GUIDE_VERSION == 35
    assert parsed.has_unknown_breaking_change is False

    changed = copy.deepcopy(document)
    entry = next(item for item in changed["changes"] if item.get("version") == 35)
    entry["detail"] += " 未经审查的附加规则"
    assert parse_guide_version(changed, scoped_tournament=True).has_unknown_breaking_change


def test_v35_without_call_context_stays_conservative() -> None:
    """不带已核调用路径的通用解析不可越过 breaking 门禁。"""
    document = json.loads(GUIDE.read_text(encoding="utf-8"))
    assert parse_guide_version(document).has_unknown_breaking_change
