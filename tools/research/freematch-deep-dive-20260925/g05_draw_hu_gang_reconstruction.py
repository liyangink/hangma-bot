#!/usr/bin/env python3
"""补全官方摸牌后直接自摸胡或杠的玩家可见观察和合法动作。"""

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
import hashlib
import json
from pathlib import Path

import g05_strong_draw_reconstruction as g05
import anatomy_lib as anatomy
import c31_action_layer_gap as c31
from extract_room_scores import load_rooms
from hangma_bot.application.audit_codec import observation_to_json


HERE = Path(__file__).resolve().parent
ROOMS = (
    ("a_f8ddc4c3bd9b", "g05-strong-draw-feasibility-10games-01"),
    ("a_d773a8e428a0", "g05-strong-draw-replication-01"),
)
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g05-draw-hu-gang-01')
KIND = {"bu": "added", "an": "concealed"}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def action_for(draw: dict, next_event: dict, seat: int) -> str | None:
    """仅映射官方可核的直接胡/杠，不推测中间动作或其他座位事件。"""
    if next_event.get("type") == "round_ended":
        data = next_event.get("data") or {}
        delta = data.get("scores") or []
        if data.get("draw") is False and len(delta) == 4 and delta[seat] > 0:
            return "hu"
        return "round_ended_unattributed"
    if next_event.get("type") == "gang" and next_event.get("seat") == seat:
        kind = (next_event.get("data") or {}).get("kind")
        if kind in KIND and next_event.get("tile"):
            return "gang:" + KIND[kind] + ":" + next_event["tile"]
        return "gang_unmapped"
    return None


def run() -> dict:
    """逐房穷举预登记的非弃牌后继；结果只涉及观察和合法性。"""
    room_games = {}
    frozen_sha = {}
    for room, prior_dir in ROOMS:
        path = _project_file(_PROJECT_ROOT, HERE / "evidence" / prior_dir / "result.json")
        prior = json.loads(path.read_text(encoding="utf-8"))
        if prior["room_id"] != room or prior["target_user_id"] != g05.XUANWU:
            raise ValueError("冻结摸打房身份不符")
        if prior["script_sha256"] != digest(Path(g05.__file__)):
            raise ValueError("普通摸打重建源码已变")
        room_games[room] = set(prior["selected_games"])
        frozen_sha[room] = digest(path)
    selected = {}
    for _, room, _, game_id, doc in load_rooms():
        if room in room_games and game_id in room_games[room]:
            selected[game_id] = (room, doc)
    if set(selected) != set.union(*room_games.values()):
        raise ValueError("目标官方牌谱不完整")

    all_counts = Counter()
    room_counts = {}
    windows = []
    failures = []
    for room, _ in ROOMS:
        counts = Counter()
        for game_id in sorted(room_games[room]):
            doc = selected[game_id][1]
            seats = [seat.get("user_id") for seat in doc.get("seats") or []]
            target = seats.index(g05.XUANWU)
            scores = [0, 0, 0, 0]
            for round_no, events, start_hands in anatomy.round_blocks(doc):
                if start_hands is None:
                    counts["excluded_missing_start_hands_rounds"] += 1
                    continue
                dealer = c31.round_metadata(doc).get(round_no, {}).get("dealer")
                if dealer is None:
                    counts["excluded_unknown_dealer_rounds"] += 1
                    continue
                snapshots = c31.reconstruct(events, start_hands, scores, dealer)
                for index, draw in enumerate(events):
                    if draw.get("type") != "tile_drawn" or draw.get("seat") != target:
                        continue
                    next_event = next((item for item in events[index + 1:]
                                       if item.get("type") not in g05.SKIP_EVENT_TYPES), None)
                    if next_event is None:
                        continue
                    actual = action_for(draw, next_event, target)
                    if actual is None:
                        continue
                    family = "hu" if actual == "hu" or actual.startswith("round_ended") else "gang"
                    counts["target_" + family] += 1
                    if actual in {"round_ended_unattributed", "gang_unmapped"}:
                        counts["excluded_unattributed_or_unmapped"] += 1
                        continue
                    prior = [seq for seq in snapshots if seq < int(draw["seq"])]
                    if not prior:
                        counts["excluded_no_prior_discard"] += 1
                        continue
                    before = snapshots[max(prior)]
                    intervening = [item for item in events
                                   if int(before["seq"]) < int(item["seq"]) < int(draw["seq"])
                                   and item.get("type") not in g05.SKIP_EVENT_TYPES]
                    if intervening:
                        counts["excluded_intervening_action"] += 1
                        continue
                    if before["baotou"][target] is None:
                        counts["excluded_unknown_baotou"] += 1
                        continue
                    if (before["rivers"][target]
                            and before["rivers"][target][-1] == c31.WEALTH):
                        counts["excluded_recent_white_chain_uncertain"] += 1
                        continue
                    try:
                        observation = g05.public_observation(
                            before, draw, game_id=game_id, round_no=round_no,
                            dealer=dealer, scores=scores,
                        )
                        for other in range(4):
                            if other == target:
                                continue
                            modified = [Counter(hand) for hand in before["hands"]]
                            modified[other] = Counter({"1w": sum(modified[other].values())})
                            negative = g05.public_observation(
                                before, draw, game_id=game_id, round_no=round_no,
                                dealer=dealer, scores=scores, hand_override=modified,
                            )
                            if negative != observation:
                                raise ValueError("他家暗手扰动改变本座观察")
                            counts["other_hand_perturbations"] += 1
                        rules = c31.RULES.analyze(observation, value_limits=c31.VALUE_LIMITS)
                        legal = sorted(candidate.action_key for candidate in rules.legal_candidates)
                        if actual not in legal:
                            raise ValueError("官方动作不在规则合法候选：" + actual)
                        windows.append({
                            "room_id": room, "game_id": game_id,
                            "round_no": round_no, "draw_seq": draw["seq"],
                            "actual_action": actual, "legal_action_keys": legal,
                            "observation": observation_to_json(observation),
                        })
                        counts["legal_verified_" + family] += 1
                    except Exception as exc:  # noqa: BLE001
                        counts["analysis_failures"] += 1
                        failures.append({"room_id": room, "game_id": game_id,
                                         "round_no": round_no, "draw_seq": draw["seq"],
                                         "actual_action": actual,
                                         "error": type(exc).__name__ + ": " + str(exc)})
                ended = next((event for event in events if event.get("type") == "round_ended"), None)
                if ended is None:
                    raise ValueError("缺权威局结算事件")
                delta = (ended.get("data") or {}).get("scores")
                if not isinstance(delta, list) or len(delta) != 4:
                    raise ValueError("局分数向量缺失")
                scores = [int(a) + int(b) for a, b in zip(scores, delta)]
        room_counts[room] = dict(sorted(counts.items()))
        all_counts.update(counts)
    return {
        "schema": "g05-draw-hu-gang/1",
        "script_sha256": digest(Path(__file__)),
        "base_reconstruction_sha256": digest(Path(g05.__file__)),
        "frozen_discard_results_sha256": frozen_sha,
        "room_counts": room_counts, "total_counts": dict(sorted(all_counts.items())),
        "failures": failures, "windows": windows,
        "settlement_values_used_only_for_hu_attribution_and_public_scores": True,
        "no_outcome_value_used_as_action_quality_label": True,
    }


if __name__ == "__main__":
    if OUT.exists():
        raise FileExistsError("结果目录已存在，拒绝覆盖")
    payload = run()
    OUT.mkdir(parents=True)
    (_project_file(_PROJECT_ROOT, OUT / "result.json")).write_text(
        json.dumps({key: value for key, value in payload.items() if key != "windows"},
                   ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    (_project_file(_PROJECT_ROOT, OUT / "windows.json")).write_text(
        json.dumps({"schema": "g05-draw-hu-gang-windows/1", "windows": payload["windows"]},
                   ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"total_counts": payload["total_counts"],
                      "failures": len(payload["failures"])}, ensure_ascii=False))
