"""复算自由赛第 1 场末手的当下与下一次摸牌后爆头事实。

输入为本机原始决策审计，不访问官方网络或隐藏牌墙。输出只含玩家可见牌、
规则推导和发布策略的排名，不含 Token 或请求报文。
"""

from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution'

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


ROOT = _PROJECT_ROOT
sys.path.insert(0, str(_project_file(_PROJECT_ROOT, ROOT / "src")))

from hangma_bot.hangma.hand_analysis import any_tile_win  # noqa: E402
from hangma_bot.kernel.actions import CANONICAL_TILE_ORDER, Tile  # noqa: E402


GAME_ID = "a_6865b26c49db_r1_b1_t0"
ROUND_NO = 8
TRIGGER_SEQ = 1379


def matching_records(path: Path) -> dict[str, dict]:
    """按同一决策窗口提取输入和计划；拒绝缺项或重复项。"""

    records: dict[str, dict] = {}
    for line in path.open(encoding="utf-8"):
        row = json.loads(line)
        context = row.get("context", {})
        kind = row.get("kind")
        if (
            context.get("game_id") != GAME_ID
            or context.get("round_no") != ROUND_NO
            or context.get("trigger_seq") != TRIGGER_SEQ
            or kind not in ("decision_input", "decision_planned")
        ):
            continue
        if kind in records:
            raise ValueError("同一窗口出现重复审计种类：" + kind)
        records[kind] = row
    if set(records) != {"decision_input", "decision_planned"}:
        raise ValueError("缺少完整输入/计划审计")
    return records


def summarize(path: Path) -> dict:
    """使用生产规则的任意听判定，枚举一次本人摸牌后的建爆头能力。"""

    records = matching_records(path)
    request = records["decision_input"]["payload"]["request"]
    observation = request["observation"]
    planned = records["decision_planned"]["payload"]["returned_plan"]
    hand = list(observation["my_hand"])
    drawn = observation["drawn_tile"]
    if drawn is not None and len(hand) == 10:
        hand.append(drawn)
    if len(hand) != 11 or observation["rule_state"]["wealth_god"] != "白":
        raise ValueError("本脚本只复核冻结的本人一副露双白窗口")
    score_by_key = {row["action_key"]: row["total_score"] for row in planned["candidates"]}
    results = []
    for action in request["rules"]["legal_candidates"]:
        key = action["action_key"]
        if not key.startswith("discard:"):
            continue
        tile = key[8:]
        after_first = hand.copy()
        after_first.remove(tile)
        current_baotou = any_tile_win(tuple(Tile(code) for code in after_first), 1)
        if current_baotou != action["facts"]["baotou_after"]:
            raise AssertionError("审计的动作后爆头事实与生产规则不一致：" + key)
        useful = {
            row["code"]: row["remaining_estimate"]
            for row in action["facts"]["useful_tiles"]
        }
        enabled = []
        for next_draw in CANONICAL_TILE_ORDER:
            if after_first.count(next_draw) == 4:
                continue
            after_draw = after_first + [next_draw]
            next_discards = []
            for second_tile in set(after_draw):
                after_second = after_draw.copy()
                after_second.remove(second_tile)
                if any_tile_win(tuple(Tile(code) for code in after_second), 1):
                    next_discards.append(second_tile)
            if next_discards:
                enabled.append({
                    "draw": next_draw,
                    "second_discards": sorted(next_discards),
                    "remaining_estimate": useful.get(next_draw),
                })
        results.append({
            "action_key": key,
            "current_baotou": current_baotou,
            "v2_score": score_by_key[key],
            "next_draw_to_baotou": enabled,
            "support_remaining": sum(
                item["remaining_estimate"] or 0 for item in enabled
            ),
        })
    return {
        "game_id": GAME_ID,
        "round_no": ROUND_NO,
        "trigger_seq": TRIGGER_SEQ,
        "seat": observation["seat"],
        "remaining_tile_count": observation["remaining_tile_count"],
        "hand_including_drawn": hand,
        "wealth_god": observation["rule_state"]["wealth_god"],
        "current_baotou": observation["rule_state"]["baotou"],
        "immediate_hu_score": score_by_key["hu"],
        "results": sorted(results, key=lambda row: row["action_key"]),
    }


def main() -> None:
    """读取本地审计并向标准输出写脱敏复算 JSON。"""

    parser = argparse.ArgumentParser()
    parser.add_argument("decisions_jsonl", type=Path)
    args = parser.parse_args()
    print(json.dumps(summarize(args.decisions_jsonl), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
