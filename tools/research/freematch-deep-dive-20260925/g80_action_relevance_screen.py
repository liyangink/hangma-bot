#!/usr/bin/env python3
"""G80：固定合法弃牌对，核验 G79B 公开占用模型的动作相关性。"""

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
import hashlib
import json
from pathlib import Path

import numpy as np

import diversity_hidden_occupancy as pairs
import g8_public_response_training_rows as audit_source
import g79_tile_occupancy_transfer as occupancy
import g9_diversity_hidden_occupancy_91room as official
from hangma_bot.hangma.public_tile_counts import count_unseen_tiles
from hangma_bot.kernel.serialization import observation_from_json


HERE = Path(__file__).resolve().parent
PREREG = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/G80-ACTION-RELEVANCE-PREREG-2026-09-28.md')
G79B = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g79b-corrected-occupancy-transfer-20260928/result.json')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g80-action-relevance-20260928/result.json')
ORDER = tuple(occupancy.c31.TILE_ORDER)
INDEX = {code: index for index, code in enumerate(ORDER)}


def _observation_features(raw: dict) -> tuple[np.ndarray, np.ndarray, int, int]:
    """仅从正式玩家观察构造 G79B 输入，不读赛后暗手、牌墙或未来事件。"""

    obs = observation_from_json(raw)
    seat = obs.seat
    hand = [tile.code for tile in obs.my_hand]
    own_melds = len(obs.melds[seat])
    if obs.drawn_tile is not None:
        without = 13 - 3 * own_melds
        with_drawn = without + 1
        if len(hand) == without:
            hand.append(obs.drawn_tile.code)
        elif len(hand) != with_drawn or obs.drawn_tile.code not in hand:
            raise ValueError("本人摸牌形态不满足生产规则归一化")
    own = Counter(hand)
    unseen = count_unseen_tiles(obs)
    if any(value is None for value in unseen):
        raise ValueError("生产逐牌码未知容量含不可判定值")
    n = np.asarray(unseen, dtype=np.int16)
    if len(n) != 34:
        raise ValueError("生产未知牌码维度不是 34")
    rivers = [[tile.code for tile in river] for river in obs.discards]
    own_river = Counter(rivers[seat])
    other_river = Counter(code for other, river in enumerate(rivers)
                          if other != seat for code in river)
    meld_suit = Counter()
    for other, seat_melds in enumerate(obs.melds):
        if other == seat:
            continue
        for meld in seat_melds:
            codes = [tile.code for tile in meld.tiles]
            if codes and len(codes[0]) == 2 and codes[0][1] in "wbt":
                meld_suit[codes[0][1]] += 1
    X = np.zeros((34, len(occupancy.FEATURES)), dtype=np.float64)
    for index, code in enumerate(ORDER):
        honor = code == occupancy.c31.WEALTH or not (len(code) == 2 and code[1] in "wbt")
        X[index, 0] = honor
        X[index, 1] = not honor and code[0] in "19"
        X[index, 2] = not honor and code[0] in "28"
        X[index, 3] = int(n[index]) - 2
        X[index, 4] = min(2, other_river[code])
        X[index, 5] = min(2, own_river[code])
        if not honor:
            number, suit = int(code[0]), code[1]
            X[index, 6] = min(4, sum(other_river[f"{neighbor}{suit}"]
                                     for neighbor in (number - 1, number + 1)
                                     if 1 <= neighbor <= 9))
            X[index, 7] = min(2, meld_suit[suit])
    H = sum(count for other, count in enumerate(obs.hand_counts) if other != seat)
    wall = obs.remaining_tile_count
    if wall is None or H <= 0 or wall <= 0:
        raise ValueError("观察的墙余或他家暗手张数不可判定")
    if int(n.sum()) != H + wall:
        if obs.chain_piao:
            raise ValueError("观察的 136 张牌守恒失败：财飘链")
        raise ValueError("观察的 136 张牌守恒失败：非财飘链")
    if sum(own.values()) != obs.hand_counts[seat]:
        raise ValueError("归一化本人手牌张数与官方暗手张数不符")
    return X, n, H, wall


def _bootstrap(rows: list[dict], field: str, seed: int) -> list[float] | None:
    """按房间重采样差值均值，房间是观察性相关单位。"""

    by_room = defaultdict(list)
    for row in rows:
        by_room[row["room_id"]].append(row[field])
    if not by_room:
        return None
    rooms = sorted(by_room)
    sums = np.asarray([sum(by_room[room]) for room in rooms], dtype=float)
    counts = np.asarray([len(by_room[room]) for room in rooms], dtype=float)
    rng = np.random.default_rng(seed)
    picks = rng.integers(0, len(rooms), size=(20_000, len(rooms)))
    samples = sums[picks].sum(axis=1) / counts[picks].sum(axis=1)
    return [float(np.quantile(samples, 0.025)), float(np.quantile(samples, 0.975))]


def _summary(rows: list[dict], seed: int) -> dict:
    """固定误差和、房级区间、非零真差方向与有效覆盖。"""

    if not rows:
        return {"windows": 0, "rooms": 0}
    by_room = defaultdict(lambda: {"windows": 0, "squared_error_difference": 0.0})
    for row in rows:
        record = by_room[row["room_id"]]
        record["windows"] += 1
        record["squared_error_difference"] += row["squared_error_difference"]
    nz = [row for row in rows if row["actual_difference"] != 0]
    def direction(value: float) -> int:
        # 公开张数差为零时，浮点加减的 1e-15 残差不是真实动作方向。
        return 0 if abs(value) < 1e-9 else (1 if value > 0 else -1)
    return {
        "windows": len(rows), "rooms": len(by_room),
        "complete_tables": len({row["game_id"] for row in rows}),
        "baseline_squared_error_sum": float(sum(row["baseline_squared_error"] for row in rows)),
        "model_squared_error_sum": float(sum(row["model_squared_error"] for row in rows)),
        "mean_squared_error_difference": float(np.mean(
            [row["squared_error_difference"] for row in rows])),
        "room_bootstrap_95": _bootstrap(rows, "squared_error_difference", seed),
        "mean_absolute_error_difference": float(np.mean(
            [row["absolute_error_difference"] for row in rows])),
        "actual_nonzero_windows": len(nz),
        "model_correct_direction_nonzero": int(sum(
            direction(row["model_difference"]) == direction(row["actual_difference"])
            for row in nz)),
        "baseline_correct_direction_nonzero": int(sum(
            direction(row["baseline_difference"]) == direction(row["actual_difference"])
            for row in nz)),
        "rooms_model_better": sum(row["squared_error_difference"] < 0 for row in by_room.values()),
        "rooms_model_worse": sum(row["squared_error_difference"] > 0 for row in by_room.values()),
        "by_room": dict(sorted(by_room.items())),
    }


def main() -> None:
    """冻结输入身份，逐房重建并将赛后暗手严格限制在误差标签。"""

    if OUT.exists():
        raise SystemExit("G80 已有结果，拒绝覆盖")
    g60 = json.loads(occupancy.G60.read_text(encoding="utf-8"))
    old = {row["room_id"] for row in json.loads(occupancy.G9.read_text(encoding="utf-8"))["rooms"]}
    selected = {room: set(games) for room, games in g60["included"].items() if room not in old}
    if len(selected) != 98 or sum(map(len, selected.values())) != 980:
        raise ValueError("G60 的 98 房/980 完整桌身份漂移")
    g79b = json.loads(G79B.read_text(encoding="utf-8"))
    beta = np.asarray([g79b["model"]["coefficients"][name] for name in occupancy.FEATURES])
    if len(beta) != 8 or not np.isfinite(beta).all():
        raise ValueError("G79B 冻结系数缺失")
    documents = defaultdict(dict)
    document_hashes = []
    for _, room, _, game_id, doc in occupancy.load_rooms():
        if room not in selected or game_id not in selected[room] or game_id in documents[room]:
            continue
        documents[room][game_id] = doc
        document_hashes.append((game_id, hashlib.sha256(json.dumps(
            doc, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode()).hexdigest()))
    if {room: set(games) for room, games in documents.items()} != selected:
        raise ValueError("98 房官方完整桌缺失")
    audit_dirs = defaultdict(list)
    for manifest in (occupancy.ROOT / "artifacts/sessions").glob("*/audit/runs/*/manifest.json"):
        metadata = json.loads(manifest.read_text(encoding="utf-8"))
        room = (metadata.get("context") or {}).get("tournament_id")
        if room not in selected:
            continue
        payload = metadata.get("payload") or {}
        release = payload.get("policy_release") or {}
        if (release.get("release_package_id") != g60["release_package_id"]
                or release.get("candidate_source_sha256") !=
                json.loads(occupancy.G9.read_text(encoding="utf-8"))["parent_source_sha256"]):
            raise ValueError("冻结外部房发布身份漂移")
        audit_dirs[room].append(manifest.parent)
    if set(audit_dirs) != set(selected) or any(len(paths) != 1 for paths in audit_dirs.values()):
        raise ValueError("98 房动作审计目录不唯一")

    counts = Counter()
    by_room_counts = {}
    rows = []
    for number, room in enumerate(sorted(selected), start=1):
        snapshots = official._room_snapshots(documents[room])
        positions = defaultdict(int)
        for game_id, round_no, seq in sorted(snapshots):
            snap = snapshots[(game_id, round_no, seq)]
            if snap["discarder"] == next(
                index for index, seat in enumerate(documents[room][game_id]["seats"])
                if seat.get("user_id") == occupancy.g59.US
            ):
                positions[(game_id, round_no)] += 1
                snap["own_discard_position"] = positions[(game_id, round_no)]
        audit = audit_dirs[room][0]
        decision_file = audit / "participants" / audit_source.ACTOR / "decisions.jsonl"
        accepted = audit_source._accepted(decision_file)
        local = Counter()
        seen = set()
        for context, request, plan in audit_source.screen._iter_decisions(audit):
            key = (context.get("game_id"), context.get("round_no"),
                   context.get("trigger_seq"))
            phase = (request.get("window_key") or {}).get("phase")
            if (*key, phase) in seen:
                raise ValueError("同一动作窗口重复")
            seen.add((*key, phase))
            pair = pairs._alternatives(request, plan)
            if pair is None:
                continue
            local["public_candidate_pair"] += 1
            chosen, alternate, a_useful, b_useful, gap, width_gain, safe = pair
            if not safe:
                local["route_regression"] += 1
                continue
            if accepted.get(context.get("decision_id")) != chosen:
                local["parent_plan_not_accepted"] += 1
                continue
            snap = snapshots.get((key[0], key[1], key[2] + 1))
            if snap is None:
                local["official_snapshot_missing"] += 1
                continue
            raw = request["observation"]
            seat = raw["seat"]
            if snap["discarder"] != seat or snap["tile"] != chosen.split(":", 1)[1]:
                local["official_discard_mismatch"] += 1
                continue
            try:
                X, n, H, wall = _observation_features(raw)
            except (ValueError, KeyError, TypeError) as exc:
                local[f"observation_invalid:{type(exc).__name__}:{str(exc)[:65]}"] += 1
                continue
            try:
                cX, cn, cH, cwall = occupancy._features(snap, seat)
            except ValueError:
                local["official_projection_invalid"] += 1
                continue
            if not np.array_equal(n, cn) or H != cH or wall != cwall:
                local["observation_official_unknown_mismatch"] += 1
                continue
            if not np.array_equal(X, cX):
                local["observation_official_feature_mismatch"] += 1
                continue
            union = {**a_useful, **b_useful}
            if any(n[INDEX[code]] != amount for code, amount in union.items()):
                local["rule_unknown_capacity_mismatch"] += 1
                continue
            hidden = Counter()
            for other, hand in enumerate(snap["hands"]):
                if other != seat:
                    hidden.update(hand)
            y = np.asarray([hidden[code] for code in ORDER], dtype=np.int16)
            if np.any(y > n) or int(y.sum()) != H:
                raise ValueError("赛后他家暗手标签违反物理容量")
            base, model = occupancy._predict(occupancy.Window(room, 0, X, n, y, H, wall), beta)
            def delta(capacity: np.ndarray) -> float:
                return float(sum(capacity[INDEX[code]] for code in b_useful) -
                             sum(capacity[INDEX[code]] for code in a_useful))
            actual = delta(n - y)
            baseline = delta(n - base)
            predicted = delta(n - model)
            row = {"room_id": room, "game_id": key[0], "gap": gap,
                   "width_gain": width_gain, "position": snap["own_discard_position"],
                   "actual_difference": actual, "baseline_difference": baseline,
                   "model_difference": predicted,
                   "baseline_squared_error": (baseline - actual) ** 2,
                   "model_squared_error": (predicted - actual) ** 2,
                   "squared_error_difference": (predicted - actual) ** 2 - (baseline - actual) ** 2,
                   "absolute_error_difference": abs(predicted - actual) - abs(baseline - actual)}
            rows.append(row)
            local["matched"] += 1
        by_room_counts[room] = dict(sorted(local.items()))
        counts.update(local)
        if number % 10 == 0:
            print(json.dumps({"rooms_processed": number, "matched": counts["matched"]},
                             ensure_ascii=False), flush=True)
    primary = [row for row in rows if row["gap"] == 0]
    groups = {str(gap): _summary([row for row in rows if row["gap"] == gap],
                                 20260928 + gap) for gap in (0, -1, -2)}
    benchmark = groups["0"]
    qualified = benchmark["windows"] >= 100 and benchmark["rooms"] >= 30
    directional = (qualified and benchmark["mean_squared_error_difference"] < 0
                   and benchmark["room_bootstrap_95"][1] < 0)
    positions = {name: _summary([row for row in primary if check(row["position"])], seed)
                 for name, check, seed in (("1-3", lambda p: p <= 3, 20261028),
                                           ("4-6", lambda p: 4 <= p <= 6, 20261128),
                                           ("7+", lambda p: p >= 7, 20261228))}
    result = {
        "schema": "g80-action-relevance/1", "preregistered": True,
        "source_sha256": {"prereg": occupancy.sha(PREREG), "g60": occupancy.sha(occupancy.G60),
                          "g9": occupancy.sha(occupancy.G9), "g79b": occupancy.sha(G79B),
                          "script": occupancy.sha(Path(__file__)),
                          "official_docs_fingerprint": hashlib.sha256(json.dumps(
                              sorted(document_hashes), separators=(",", ":")
                          ).encode()).hexdigest()},
        "source_rooms": len(selected), "source_complete_tables": sum(map(len, selected.values())),
        "totals": dict(sorted(counts.items())), "by_room_counts": by_room_counts,
        "groups": groups, "primary_by_position": positions,
        "primary_sample_qualified": qualified, "primary_directional": directional,
        "boundary": "98 房曾用于 G79A 逐码评分；本动作读数是探索性的，不是桌赛收益。"
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                   encoding="utf-8")
    print(json.dumps({key: value for key, value in result.items() if key != "by_room_counts"},
                     ensure_ascii=False, sort_keys=True, indent=2), flush=True)


if __name__ == "__main__":
    main()
