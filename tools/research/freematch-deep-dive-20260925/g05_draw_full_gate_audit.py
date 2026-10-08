#!/usr/bin/env python3
"""逐场复核 G0.5 普通摸打窗覆盖与每个纳入窗的信息权限负控。"""

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
EVIDENCE = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g05-strong-draw-feasibility-10games-01')


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run() -> dict:
    """只读已冻结结果及官方牌谱；不读取单局结算作为行为标签。"""
    result_path = _project_file(_PROJECT_ROOT, EVIDENCE / "result.json")
    windows_path = _project_file(_PROJECT_ROOT, EVIDENCE / "windows.json")
    result = json.loads(result_path.read_text(encoding="utf-8"))
    windows = json.loads(windows_path.read_text(encoding="utf-8"))["windows"]
    by_key = {(row["game_id"], row["round_no"], row["draw_seq"]): row
              for row in windows}
    if len(by_key) != len(windows):
        raise ValueError("窗口键重复")
    if result["script_sha256"] != digest(Path(g05.__file__)):
        raise ValueError("冻结重建脚本摘要变化")
    source = {}
    for _, room, _, game_id, doc in load_rooms():
        if room == result["room_id"] and game_id in result["selected_games"]:
            source[game_id] = doc
    if set(source) != set(result["selected_games"]):
        raise ValueError("官方牌谱缺场")

    per_game = []
    checked = 0
    perturbations = 0
    for game_id in result["selected_games"]:
        doc = source[game_id]
        seats = [seat.get("user_id") for seat in doc.get("seats") or []]
        seat = seats.index(result["target_user_id"])
        scores = [0, 0, 0, 0]
        counts = Counter()
        agree = 0
        disagree = 0
        for round_no, events, start_hands in anatomy.round_blocks(doc):
            counts["rounds"] += 1
            if start_hands is None:
                counts["excluded_missing_start_hands_rounds"] += 1
                continue
            dealer = c31.round_metadata(doc).get(round_no, {}).get("dealer")
            if dealer is None:
                counts["excluded_unknown_dealer_rounds"] += 1
                continue
            snapshots = c31.reconstruct(events, start_hands, scores, dealer)
            selected, per_round = g05.clean_draw_windows(events, snapshots, seat)
            counts.update(per_round)
            for before, draw, _discard in selected:
                key = (game_id, round_no, draw["seq"])
                row = by_key.get(key)
                if row is None:
                    raise ValueError("冻结结果缺纳入窗：" + str(key))
                observation = g05.public_observation(
                    before, draw, game_id=game_id, round_no=round_no,
                    dealer=dealer, scores=scores,
                )
                if observation_to_json(observation) != row["observation"]:
                    raise ValueError("原观察重算不吻合：" + str(key))
                for other in range(4):
                    if other == seat:
                        continue
                    modified = [Counter(hand) for hand in before["hands"]]
                    count = sum(modified[other].values())
                    modified[other] = Counter({"1w": count})
                    perturbed = g05.public_observation(
                        before, draw, game_id=game_id, round_no=round_no,
                        dealer=dealer, scores=scores, hand_override=modified,
                    )
                    if perturbed != observation:
                        raise ValueError("他家暗牌改变观察：" + str(key) + ":" + str(other))
                    perturbations += 1
                checked += 1
                counts["legal_verified_windows"] += 1
                agree += bool(row["parent_agrees"])
                disagree += not row["parent_agrees"]
            ended = next((event for event in events if event.get("type") == "round_ended"), None)
            if ended is None:
                counts["excluded_no_round_ended"] += 1
                continue
            delta = (ended.get("data") or {}).get("scores")
            if not isinstance(delta, list) or len(delta) != 4:
                counts["excluded_invalid_round_scores"] += 1
                continue
            scores = [int(a) + int(b) for a, b in zip(scores, delta)]
        per_game.append({
            "game_id": game_id, "counts": dict(sorted(counts.items())),
            "parent_agreement": agree, "parent_disagreement": disagree,
        })
    if checked != len(windows) or checked != result["counts"]["clean_windows"]:
        raise ValueError("纳入窗总数不一致")
    totals = Counter()
    for item in per_game:
        totals.update(item["counts"])
    if dict(totals) != result["counts"]:
        raise ValueError("逐场计数与冻结总数不一致")
    return {
        "schema": "g05-draw-full-gate-audit/1",
        "frozen_result_sha256": digest(result_path),
        "frozen_windows_sha256": digest(windows_path),
        "script_sha256": digest(Path(__file__)),
        "checked_windows": checked,
        "other_hand_perturbations": perturbations,
        "per_game": per_game,
        "outcome_labels_opened": False,
    }


if __name__ == "__main__":
    out = _project_file(_PROJECT_ROOT, EVIDENCE / "full-gate-audit.json")
    if out.exists():
        raise FileExistsError("已有复核结果，拒绝覆盖")
    payload = run()
    out.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                   encoding="utf-8")
    print(json.dumps({"checked_windows": payload["checked_windows"],
                      "other_hand_perturbations": payload["other_hand_perturbations"]},
                     ensure_ascii=False))
