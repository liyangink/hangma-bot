#!/usr/bin/env python3
"""G230：用官方赛后完整暗手重建，检验多牌码进张的真实墙库存。"""

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

from collections import Counter, defaultdict
from hashlib import sha256
import json
from pathlib import Path
import random

import c31_action_layer_gap as c31
import g05_strong_draw_reconstruction as g05
import g178_natural_vs_standard_support as g178
import g191_highhand_discard_breadth as g191
from extract_room_scores import load_rooms
from hangma_bot.hangma import public_tile_counts
from hangma_bot.hangma.engine import _build_context
from hangma_bot.hangma.internal_types import TILE_ORDER
from hangma_bot.kernel.serialization import observation_from_json


HERE = Path(__file__).resolve().parent
PLAN = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/G230-CODE-DIVERSITY-WALL-ALLOCATION-PREREG-2026-09-29.md')
G61 = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g61-strong-draw-action-atlas-20260927')
G63 = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g63-code-diversity-census-20260928/result.json')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g230-code-diversity-wall-allocation-20260929/result.json')
BOOT_SEED = 20260929230
BOOT_DRAWS = 5000


def digest(path: Path) -> str:
    """返回当前冻结输入或程序的原始字节摘要。"""
    return sha256(path.read_bytes()).hexdigest()


def official_wall(before: dict, drawn_seat: int, drawn_code: str) -> dict[str, int]:
    """赛后完整暗手反推摸后未弃时的真实牌墙；只供标签使用。"""
    hands = [Counter(hand) for hand in before["hands"]]
    hands[drawn_seat][drawn_code] += 1
    held = Counter()
    for hand in hands:
        held.update(hand)
    exposed = Counter()
    for river in before["rivers"]:
        exposed.update(river)
    for seat_melds in before["melds"]:
        for meld in seat_melds:
            exposed.update(meld["tiles"])
    if (set(held) | set(exposed)) - set(TILE_ORDER):
        raise ValueError("官方重建包含未知牌码")
    wall = {code: 4 - held[code] - exposed[code] for code in TILE_ORDER}
    if any(amount < 0 or amount > 4 for amount in wall.values()):
        raise ValueError("官方重建牌码守恒失败")
    return wall


def action_support(observation, key: str, candidates: dict, unseen: tuple):
    """行动前可见规则事实与无白自然缺口；不读取官方未来。"""
    candidate = candidates.get(key)
    if candidate is None or candidate.facts is None or not key.startswith("discard:"):
        raise ValueError("目标弃牌已不在当前生产合法动作集合")
    if key == "discard:白":
        raise ValueError("本项只比较非白弃牌")
    standard = g191.production(candidate.facts)
    standard.pop("白", None)
    full = _build_context(observation).full_hand()
    root = g178._drop(full, key.split(":", 1)[1])
    need, natural = g178.natural(root, unseen, len(observation.melds[observation.seat]))
    return {
        "standard_shanten": candidate.facts.standard_shanten_after,
        "natural_need": need,
        "production_nonwhite": standard,
        "natural": natural,
    }


def stock(support: dict[str, int], wall: dict[str, int], wall_total: int,
          unknown_total: int) -> dict:
    """公开容量与赛后真实墙库存分别记账；期望依赖可交换基准。"""
    capacity = sum(support.values())
    actual = sum(wall[code] for code in support)
    return {
        "types": len(support), "capacity": capacity,
        "actual_wall": actual,
        "exchangeable_expected_wall": wall_total * capacity / unknown_total,
    }


def pair_measure(parent: dict, strong: dict) -> dict:
    """强手减父代，不将墙库存差冒充胡牌概率或赛事净分。"""
    actual = strong["actual_wall"] - parent["actual_wall"]
    expected = (strong["exchangeable_expected_wall"]
                - parent["exchangeable_expected_wall"])
    return {
        "parent": parent, "strong": strong,
        "types_delta": strong["types"] - parent["types"],
        "capacity_delta": strong["capacity"] - parent["capacity"],
        "actual_wall_delta": actual,
        "exchangeable_expected_delta": expected,
        "wall_residual_delta": actual - expected,
    }


def first_per_seat_hand(rows: list[dict]) -> list[dict]:
    """同一强手座位单局只保留官方时间最早的目标窗。"""
    first = {}
    for row in sorted(rows, key=lambda item: item["identity"][4]):
        peer, room, game_id, round_no, _ = row["identity"]
        first.setdefault((peer, room, game_id, round_no, row["seat"]), row)
    return list(first.values())


def summarize(rows: list[dict], field: str) -> dict:
    """按官方房重采样平均剩余墙库存差，防止共房窗伪独立。"""
    values = [row[field]["wall_residual_delta"] for row in rows]
    rooms = defaultdict(list)
    for row in rows:
        rooms[row["identity"][1]].append(row[field]["wall_residual_delta"])
    if not values:
        return {"windows": 0, "rooms": 0}
    keys = sorted(rooms)
    rng = random.Random(BOOT_SEED)
    samples = []
    for _ in range(BOOT_DRAWS):
        chosen = [rng.choice(keys) for _ in keys]
        sample = [value for key in chosen for value in rooms[key]]
        samples.append(sum(sample) / len(sample))
    samples.sort()
    return {
        "windows": len(rows), "rooms": len(keys),
        "positive_actual_wall_delta": sum(row[field]["actual_wall_delta"] > 0 for row in rows),
        "same_public_capacity": sum(row[field]["capacity_delta"] == 0 for row in rows),
        "mean_actual_wall_delta": sum(row[field]["actual_wall_delta"] for row in rows) / len(rows),
        "mean_expected_wall_delta": sum(row[field]["exchangeable_expected_delta"] for row in rows) / len(rows),
        "mean_wall_residual_delta": sum(values) / len(values),
        "room_bootstrap_95_mean_residual": [samples[124], samples[4874]],
    }


def main() -> None:
    """锁行动前 56 对后，才读取官方完整暗手并导出聚合标签。"""
    if OUT.exists():
        raise FileExistsError("G230 赛后结果已存在，拒绝覆盖")
    fixed = json.loads(G63.read_text(encoding="utf-8"))
    if (fixed.get("schema") != "g63-code-diversity-result/1"
            or fixed.get("targets") != 56
            or fixed.get("outcome_labels_opened") is not False):
        raise ValueError("G63 固定来源漂移")
    targets = {tuple(row["key"]): row for row in fixed["rows"]}
    if len(targets) != 56:
        raise ValueError("G63 目标身份重复")
    batch = json.loads((_project_file(_PROJECT_ROOT, G61 / "result.json")).read_text(encoding="utf-8"))
    if batch.get("outcome_labels_opened") is not False:
        raise ValueError("G61 行动前来源不再结果盲")
    windows = {}
    source_windows = {}
    for unit, record in sorted(batch["units"].items()):
        peer, room = unit.split("/", 1)
        if not any(key[:2] == (peer, room) for key in targets):
            continue
        path = _project_file(_PROJECT_ROOT, G61 / "rooms" / (peer + "--" + room) / "windows.json")
        if digest(path) != record["windows_sha256"]:
            raise ValueError("G61 逐窗原文摘要漂移")
        source_windows[unit] = digest(path)
        for window in json.loads(path.read_text(encoding="utf-8"))["windows"]:
            key = (peer, room, window["game_id"], window["round_no"], window["draw_seq"])
            if key in targets:
                if key in windows:
                    raise ValueError("G61 目标观察重复")
                windows[key] = window
    if set(windows) != set(targets):
        raise ValueError("G61 行动前观察未覆盖全部 G63 目标")

    # 官方案例只用于重建墙标签；不在标签打开后改变目标身份或动作。
    wanted_games = {key[2] for key in targets}
    official = {}
    for _mtime, room, _tag, game_id, doc in load_rooms():
        if game_id in wanted_games:
            if game_id in official or room not in {key[1] for key in targets if key[2] == game_id}:
                raise ValueError("官方完整桌身份重复或房间不符")
            official[game_id] = doc
    if set(official) != wanted_games:
        raise ValueError("官方完整桌缺失")
    official_digest = {gid: sha256(json.dumps(doc, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
                       for gid, doc in official.items()}

    rows = []
    for game_id, doc in sorted(official.items()):
        target_rounds = {key[3] for key in targets if key[2] == game_id}
        for round_no, events, start_hands in g05.anatomy.round_blocks(doc):
            if round_no not in target_rounds:
                continue
            if start_hands is None:
                raise ValueError("官方目标单局无起手暗手")
            dealer = c31.round_metadata(doc)[round_no]["dealer"]
            snapshots = c31.reconstruct(events, start_hands, [0, 0, 0, 0], dealer)
            target_seats = {windows[key]["seat"] for key in targets
                            if key[2] == game_id and key[3] == round_no}
            clean = {}
            for seat in target_seats:
                selected, _counts = g05.clean_draw_windows(events, snapshots, seat)
                for before, draw, discard in selected:
                    clean[(seat, draw["seq"])] = (before, draw, discard)
            for key in sorted(k for k in targets if k[2] == game_id and k[3] == round_no):
                source, target = windows[key], targets[key]
                seat = source["seat"]
                triple = clean.get((seat, key[4]))
                if triple is None:
                    raise ValueError("G05 已核官方摸打目标不能重建")
                before, draw, discard = triple
                if (source["actual_action"] != target["strong_action"]
                        or source["parent_top_action"] != target["parent_action"]
                        or source["actual_action"] != "discard:" + discard["tile"]):
                    raise ValueError("目标强手动作或父代身份漂移")
                observation = observation_from_json(source["observation"])
                if (observation.snapshot_seq != key[4] or observation.seat != seat
                        or observation.drawn_tile.code != draw["tile"]):
                    raise ValueError("官方摸牌与可见观察身份不一致")
                wall = official_wall(before, seat, draw["tile"])
                wall_total = sum(wall.values())
                if wall_total != observation.remaining_tile_count:
                    raise ValueError("官方牌墙总数与行动前可见墙余不一致")
                unseen = public_tile_counts.count_unseen_tiles(observation)
                other_hand_total = sum(sum(hand.values()) for index, hand in enumerate(before["hands"])
                                       if index != seat)
                unknown_total = wall_total + other_hand_total
                if (unknown_total <= 0 or any(item is None for item in unseen)
                        or sum(unseen) != unknown_total
                        or any(wall[code] > unseen[i]
                               for i, code in enumerate(TILE_ORDER))):
                    raise ValueError("公开未知池与赛后墙／他家暗手守恒失败")
                analysis = c31.RULES.analyze(observation, value_limits=c31.VALUE_LIMITS)
                legal = {item.action_key: item for item in analysis.legal_candidates}
                facts = {label: action_support(observation, target[action], legal, unseen)
                         for label, action in (("parent", "parent_action"),
                                               ("strong", "strong_action"))}
                comparisons = {}
                for field in ("production_nonwhite", "natural"):
                    parent = stock(facts["parent"][field], wall, wall_total, unknown_total)
                    strong = stock(facts["strong"][field], wall, wall_total, unknown_total)
                    comparisons[field] = pair_measure(parent, strong)
                natural_eligible = (facts["strong"]["natural_need"] == facts["parent"]["natural_need"]
                                    and comparisons["natural"]["types_delta"] > 0
                                    and comparisons["natural"]["capacity_delta"] <= 0)
                rows.append({
                    "identity": list(key), "seat": seat, "whites": target["white_before"],
                    "wall_total": wall_total, "unknown_total": unknown_total,
                    "standard_shanten": {label: item["standard_shanten"] for label, item in facts.items()},
                    "natural_need": {label: item["natural_need"] for label, item in facts.items()},
                    "natural_primary_eligible": natural_eligible,
                    "production_nonwhite": comparisons["production_nonwhite"],
                    "natural": comparisons["natural"],
                })
    if len(rows) != 56 or {tuple(row["identity"]) for row in rows} != set(targets):
        raise ValueError("G230 目标窗口没有全量导出")
    first = first_per_seat_hand(rows)
    cohorts = {"all": rows, "first_per_seat_hand": first,
               "natural_primary": [row for row in first if row["natural_primary_eligible"]]}
    for peer in ("xuanwu_2346", "tengshe_0638"):
        cohorts["natural_primary/" + peer] = [row for row in cohorts["natural_primary"]
                                               if row["identity"][0] == peer]
    summary = {name: {field: summarize(layer, field) for field in ("production_nonwhite", "natural")}
               for name, layer in cohorts.items()}
    result = {
        "schema": "g230-code-diversity-wall-allocation/1",
        "source_sha256": {"plan": digest(PLAN), "script": digest(Path(__file__)),
                          "g61_result": digest(_project_file(_PROJECT_ROOT, G61 / "result.json")), "g61_windows": source_windows,
                          "g63_result": digest(G63), "official_games_canonical": official_digest,
                          "production_hand_math": digest(_project_file(_PROJECT_ROOT, HERE.parents[1] / "src/hangma_bot/hangma/hand_analysis.py"))},
        "bootstrap": {"seed": BOOT_SEED, "draws": BOOT_DRAWS, "unit": "official_room"},
        "summary": summary, "rows": rows,
        "boundary": "官方隐藏牌只用于赛后牌墙库存标签；可交换期望是比较假设，不是实际下次本人摸牌或候选整桌收益。",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                   encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
