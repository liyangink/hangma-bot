#!/usr/bin/env python3
"""冻结官方自由赛房，结果盲筛查“双白先胡或下一摸建爆头”的自然入口。

仅读取本人依法可见的决策输入与冻结父代的返回计划；不读取结算、他家暗手或未来牌墙。
这里的“下一摸建爆头”只是条件性规则路径，绝不是这条路线的净收益估计。
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

import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import re
import sys


HERE = Path(__file__).resolve().parent
ROOT = _PROJECT_ROOT
sys.path.insert(0, str(_project_file(_PROJECT_ROOT, ROOT / "src")))

from hangma_bot.hangma.hand_analysis import any_tile_win  # noqa: E402
from hangma_bot.kernel.actions import CANONICAL_TILE_ORDER, Tile  # noqa: E402


PARENT_SHA256 = "a2d9b8af93beabdba75716fccae56b0668a6fd84f0bdce558d2ff3e569443618"
PARTICIPANT = "u_13495c3d79c8"
DECISION_ID = re.compile(r'"decision_id": "([^"]+)"')
TOP_HU = '"candidates": [{"action_key": "hu"'


def freeze_rooms(ledger: Path, output: Path) -> dict:
    """从已结束房创建只含路径、大小和身份的固定输入清单；不写分数。"""

    state = json.loads(ledger.read_text(encoding="utf-8"))
    rooms = []
    for room in state["rooms"]:
        if room.get("terminal_reason") != "tournament_finished":
            continue
        audit = _project_file(_PROJECT_ROOT, ROOT / room["audit_dir"])
        decisions = audit / "participants" / PARTICIPANT / "decisions.jsonl"
        manifest = audit / "manifest.json"
        if not decisions.is_file() or not manifest.is_file():
            raise FileNotFoundError(audit)
        release = (json.loads(manifest.read_text(encoding="utf-8")).get("payload") or {}).get("policy_release") or {}
        if release.get("candidate_source_sha256") != PARENT_SHA256:
            continue
        rooms.append({
            "room_id": room["room_id"],
            "audit_dir": room["audit_dir"],
            "decision_bytes": decisions.stat().st_size,
            "games": len(room.get("games") or []),
        })
    ids = [room["room_id"] for room in rooms]
    if len(ids) != len(set(ids)):
        raise ValueError("冻结清单内存在重复官方房")
    result = {"schema": "g8-two-white-freeze/1", "parent_source_sha256": PARENT_SHA256,
              "source_ledger": str(ledger.relative_to(ROOT)), "rooms": rooms,
              "note": "仅已结束房；未读取结算或净分；文件大小用于阻止运行中日志进入统计"}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def _complete_hand(observation: dict) -> tuple[list[str], int]:
    """复原摸牌后本人暗手；一副露减少三个暗手位。"""

    seat = observation.get("seat")
    melds = observation.get("melds") or []
    if type(seat) is not int or seat < 0 or seat >= len(melds):
        raise ValueError("本人座位或副露缺失")
    meld_count = len(melds[seat])
    expected = 14 - 3 * meld_count
    hand = list(observation.get("my_hand") or [])
    if len(hand) == expected - 1 and observation.get("drawn_tile") is not None:
        hand.append(observation["drawn_tile"])
    if len(hand) != expected:
        raise ValueError("摸牌后的暗手张数不符")
    if any(hand.count(code) > 4 for code in set(hand)):
        raise ValueError("暗手中的物理牌张数超过四")
    return hand, meld_count


def _static_witnesses(request: dict) -> dict:
    """枚举当前合法弃牌及下一次本人摸牌、再弃牌后是否能爆头。"""

    observation = request["observation"]
    hand, meld_count = _complete_hand(observation)
    if (observation.get("rule_state") or {}).get("wealth_god") != "白":
        raise ValueError("冻结研究入口要求白板为财神")
    # 模拟器的弃牌河会保留被吃/碰/杠牌，故不能与副露逐张相加。
    # 对每种牌取“弃牌河张数、副露张数”的较大者，是公开已知张数的保守下界；
    # 再加本人暗手，得到公开剩余张数上界（可能仍包含他家暗手和保留牌墙）。
    discard_counts = Counter()
    for discards in observation.get("discards") or []:
        discard_counts.update(discards)
    exposed_counts = Counter()
    for exposed in observation.get("melds") or []:
        for meld in exposed:
            exposed_counts.update(meld.get("tiles") or [])
    known = Counter(hand)
    for code in set(discard_counts) | set(exposed_counts):
        known[code] += max(discard_counts[code], exposed_counts[code])
    if any(amount > 4 for amount in known.values()):
        raise ValueError("公开已知牌超过四张")
    actions = (request.get("rules") or {}).get("legal_candidates") or []
    legal = {action.get("action_key"): action for action in actions}
    if "hu" not in legal:
        raise ValueError("父代计划胡，但规则候选中无胡")
    settlement = (legal["hu"].get("value_facts") or {}).get("immediate_settlement") or {}
    result = {"white_count": hand.count("白"), "wall": observation.get("remaining_tile_count"),
              "meld_count": meld_count, "hu_fan": settlement.get("fan"),
              "first_discards": 0, "immediate_baotou_discards": 0,
              "draw_codes": set(), "witnesses": [], "public_support_by_draw": {}}
    if result["white_count"] != 2 or (observation.get("rule_state") or {}).get("baotou") is True:
        return result
    for key, action in legal.items():
        if not isinstance(key, str) or not key.startswith("discard:"):
            continue
        first_tile = key[8:]
        if first_tile == "白" or first_tile not in hand:
            continue
        result["first_discards"] += 1
        after_first = hand.copy()
        after_first.remove(first_tile)
        immediate = any_tile_win(tuple(Tile(code) for code in after_first), meld_count)
        if immediate != (action.get("facts") or {}).get("baotou_after"):
            raise ValueError("生产规则爆头事实与独立枚举入口不一致")
        if immediate:
            result["immediate_baotou_discards"] += 1
            continue
        for next_draw in CANONICAL_TILE_ORDER:
            public_remaining_upper = 4 - known[next_draw]
            if next_draw == "白" or public_remaining_upper <= 0:
                continue
            after_draw = after_first + [next_draw]
            second_discards = []
            for second_tile in set(after_draw) - {"白"}:
                after_second = after_draw.copy()
                after_second.remove(second_tile)
                if any_tile_win(tuple(Tile(code) for code in after_second), meld_count):
                    second_discards.append(second_tile)
            if second_discards:
                result["draw_codes"].add(next_draw)
                result["public_support_by_draw"][next_draw] = public_remaining_upper
                result["witnesses"].append({"first": first_tile, "draw": next_draw,
                                            "second": sorted(second_discards)})
    result["public_support_upper"] = sum(result["public_support_by_draw"].values())
    return result


def _iter_parent_hu(audit: Path):
    """流式配对完整输入与首位为胡的计划，避免保存整房审计。"""

    path = audit / "participants" / PARTICIPANT / "decisions.jsonl"
    pending = {}
    with path.open(encoding="utf-8", errors="replace") as stream:
        for line in stream:
            if '"decision_input"' in line:
                found = DECISION_ID.search(line[:600])
                if found:
                    pending[found.group(1)] = line
            elif '"decision_planned"' in line:
                found = DECISION_ID.search(line[:600])
                if not found:
                    continue
                first_input = pending.pop(found.group(1), None)
                if first_input is None or TOP_HU not in line:
                    continue
                plan = json.loads(line)
                if ((plan.get("payload") or {}).get("returned_plan") or {}).get("candidates", [{}])[0].get("action_key") != "hu":
                    continue
                input_record = json.loads(first_input)
                yield input_record.get("context") or {}, (input_record.get("payload") or {}).get("request") or {}
            if len(pending) > 16:
                raise ValueError("同房存在超过 16 个未配对决策输入")


def census(frozen: dict) -> dict:
    """按房、完整桌和单局计数，产出不含结局的可审查例子。"""

    counts = Counter()
    rooms = defaultdict(set)
    games = defaultdict(set)
    tables = defaultdict(set)
    examples = []
    support_histogram = Counter()
    hu_fan_histogram = Counter()
    seen = set()
    for row in frozen["rooms"]:
        audit = _project_file(_PROJECT_ROOT, ROOT / row["audit_dir"])
        path = audit / "participants" / PARTICIPANT / "decisions.jsonl"
        if path.stat().st_size != row["decision_bytes"]:
            raise ValueError("冻结后审计大小变化：" + row["room_id"])
        release = (json.loads((audit / "manifest.json").read_text(encoding="utf-8")).get("payload") or {}).get("policy_release") or {}
        if release.get("candidate_source_sha256") != frozen["parent_source_sha256"]:
            raise ValueError("冻结后父代身份变化：" + row["room_id"])
        for context, request in _iter_parent_hu(audit):
            observation = request.get("observation") or {}
            if observation.get("phase") != "draw":
                continue
            key = (context.get("game_id"), context.get("round_no"), context.get("trigger_seq"))
            if key in seen:
                counts["duplicate_windows"] += 1
                continue
            seen.add(key)
            counts["parent_hu_draw"] += 1
            try:
                facts = _static_witnesses(request)
            except ValueError:
                counts["invalid_input_or_rule_fact"] += 1
                continue
            if facts["white_count"] != 2:
                continue
            counts["parent_hu_two_white"] += 1
            if facts["immediate_baotou_discards"]:
                counts["parent_hu_two_white_immediate_baotou"] += 1
            if not facts["witnesses"]:
                continue
            counts["next_draw_static_witness"] += 1
            support_histogram[facts["public_support_upper"]] += 1
            hu_fan_histogram[str(facts["hu_fan"])] += 1
            wall = facts["wall"]
            if type(wall) is int and wall > 20:
                counts["next_draw_static_witness_wall_gt20"] += 1
            if type(wall) is int and wall > 24 and facts["hu_fan"] == 1 and not facts["immediate_baotou_discards"]:
                counts["focused_fan1_wall_gt24_no_immediate_target"] += 1
            rooms["next_draw_static_witness"].add(row["room_id"])
            tables["next_draw_static_witness"].add(context.get("game_id"))
            games["next_draw_static_witness"].add((context.get("game_id"), context.get("round_no")))
            if len(examples) < 30:
                examples.append({"room_id": row["room_id"], "game_id": context.get("game_id"),
                                 "round_no": context.get("round_no"), "trigger_seq": context.get("trigger_seq"),
                                 "wall": wall, "meld_count": facts["meld_count"],
                                 "hu_fan": facts["hu_fan"],
                                 "first_discards": facts["first_discards"],
                                 "immediate_baotou_discards": facts["immediate_baotou_discards"],
                                 "next_draw_codes": sorted(facts["draw_codes"]),
                                 "public_support_upper": facts["public_support_upper"],
                                 "witness_count": len(facts["witnesses"]),
                                 "first_witness": facts["witnesses"][0]})
    return {"schema": "g8-two-white-natural-census/1", "parent_source_sha256": frozen["parent_source_sha256"],
            "frozen_official_rooms": len(frozen["rooms"]), "frozen_official_tables": sum(row["games"] for row in frozen["rooms"]),
            "counts": dict(counts), "rooms_with_static_witness": len(rooms["next_draw_static_witness"]),
            "tables_with_static_witness": len(tables["next_draw_static_witness"]),
            "rounds_with_static_witness": len(games["next_draw_static_witness"]), "examples": examples,
            "public_support_upper_histogram": dict(sorted(support_histogram.items())),
            "hu_fan_histogram": dict(sorted(hu_fan_histogram.items())),
            "interpretation": "下一摸与再弃牌的合法静态爆头路径；公开剩余张数是上界，未考虑他家暗手、牌墙顺序、对手抢胡与整桌积分"}


def main() -> None:
    """先冻结已完房，再对固定清单运行结果盲统计。"""

    parser = argparse.ArgumentParser()
    parser.add_argument("--freeze", action="store_true")
    parser.add_argument("--ledger", type=Path, default=_project_file(_PROJECT_ROOT, ROOT / "runs/auto-match-watchdog/auto-match-watchdog-state.json"))
    parser.add_argument("--manifest", type=Path, default=_project_file(_PROJECT_ROOT, HERE / "evidence/g8-two-white-next-draw-20260927/frozen_rooms.json"))
    parser.add_argument("--output", type=Path, default=_project_file(_PROJECT_ROOT, HERE / "evidence/g8-two-white-next-draw-20260927/census.json"))
    args = parser.parse_args()
    frozen = freeze_rooms(args.ledger, args.manifest) if args.freeze else json.loads(args.manifest.read_text(encoding="utf-8"))
    result = census(frozen)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in result.items() if key != "examples"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
