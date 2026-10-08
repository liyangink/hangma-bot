#!/usr/bin/env python3
"""冻结 G7a 窗口上核对廉价牌形代理能否分辨第三摸优势；仅供研究。"""

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

from collections import Counter
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import g7_g6_overlap as overlap  # noqa: E402
from hangma_bot.application.audit_codec import decision_request_from_json  # noqa: E402
from hangma_bot.hangma.internal_types import TILE_INDEX  # noqa: E402
from hangma_bot.hangma.public_tile_counts import count_unseen_tiles  # noqa: E402

OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g7-latent-feature-screen-20260927/result.json')


def _useful_shape(action: dict):
    tiles = (action.get("facts") or {}).get("useful_tiles")
    if not isinstance(tiles, list):
        raise ValueError("一步有效牌事实缺失")
    capacities = []
    for item in tiles:
        value = item.get("remaining_estimate")
        if type(value) is not int or not 0 <= value <= 4:
            raise ValueError("一步有效容量缺失")
        if value:
            capacities.append(value)
    total = sum(capacities)
    return (len(capacities),
            total * total / sum(value * value for value in capacities) if capacities else 0.0)


def _motifs(hand: list[str], unseen: tuple[int, ...]):
    """数自然牌二张搭子潜在完成口；不是胡牌规则或实际进张概率。"""
    patterns = []
    completion_codes = set()
    for suit in "wbt":
        counts = Counter(int(code[0]) for code in hand
                         if len(code) == 2 and code[-1] == suit)
        for first in range(1, 10):
            for second in range(first, 10):
                if counts[first] < 1 or counts[second] < (2 if first == second else 1):
                    continue
                if first == second:
                    completion = (first,)
                elif second == first + 1:
                    completion = (first - 1, second + 1)
                elif second == first + 2:
                    completion = (first + 1,)
                else:
                    continue
                codes = [f"{rank}{suit}" for rank in completion if 1 <= rank <= 9]
                available = [code for code in codes if unseen[TILE_INDEX[code]] > 0]
                if available:
                    patterns.append(sum(unseen[TILE_INDEX[code]] for code in available))
                    completion_codes.update(available)
    return len(patterns), sum(patterns), len(completion_codes)


def _sign(value):
    return (value > 0) - (value < 0)


def main() -> int:
    selected = json.loads(overlap.SELECTED.read_text(encoding="utf-8"))
    rows = selected["selected"]
    if len(rows) != 72 or not selected.get("selection_lock_sha256"):
        raise SystemExit("冻结 G7a 选样缺失")
    requests = overlap._requests(rows)
    cells = Counter()
    for row in rows:
        key = (row["game_id"], row["round_no"], row["trigger_seq"])
        raw, _plan = requests[key]
        parsed = decision_request_from_json(raw)
        obs = parsed.observation
        hand = [tile.code for tile in obs.my_hand]
        expected = 14 - 3 * len(obs.melds[obs.seat])
        if len(hand) == expected - 1 and obs.drawn_tile is not None:
            hand.append(obs.drawn_tile.code)
        if len(hand) != expected:
            raise ValueError("暗手与副露张数不符：" + str(key))
        unseen = count_unseen_tiles(obs)
        if any(item is None for item in unseen):
            raise ValueError("未知容量缺失：" + str(key))
        actions = {item.action_key: item for item in parsed.rules.legal_candidates}
        # 审计源事实用于一步有效分布；仍由生产序列化字段与合法候选核对。
        raw_actions = {item["action_key"]: item for item in raw["rules"]["legal_candidates"]}
        features = []
        for action_key in (row["a"], row["b"]):
            if action_key not in actions:
                raise ValueError("冻结 A/B 不合法：" + str(key))
            after = hand.copy()
            after.remove(action_key[8:])
            features.append(_useful_shape(raw_actions[action_key]) + _motifs(after, unseen))
        truth = _sign(row["delta_3"])
        groups = ["all"]
        if row["delta_2"] == 0 and row["shanten"] <= 1:
            groups.append("two_tie_sh01")
            if row["whites"] >= 2:
                groups.append("two_tie_sh01_white2plus")
        for index, name in enumerate(("useful_distinct", "useful_simpson",
                                      "motif_count", "motif_weighted", "motif_union")):
            sign = _sign(features[1][index] - features[0][index])
            for group in groups:
                cells[(name, group, sign, truth)] += 1
    aggregate = {}
    for (feature, group, sign, truth), count in sorted(cells.items()):
        bucket = aggregate.setdefault(feature, {}).setdefault(group, {})
        bucket[f"proxy_{sign:+d}_teacher_{truth:+d}"] = count
    output = {"schema": "g7-latent-feature-screen/1",
              "g7_selection_lock_sha256": selected["selection_lock_sha256"],
              "aggregate": aggregate,
              "note": "同一开发样本的代理符合度；第三摸标签仍是无对手乐观容量，不是赛事收益"}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    print(json.dumps(aggregate, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
