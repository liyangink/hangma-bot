#!/usr/bin/env python3
"""冻结第 95 房起的十间新房，验证公开被鸣预测；不足十房时不打开标签。"""

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
import gzip
import hashlib
import json
from pathlib import Path

import numpy as np

import g8_public_response_train_model as model_math
import g8_public_response_training_rows as training
from extract_room_scores import load_rooms


HERE = Path(__file__).resolve().parent
ROOT = _PROJECT_ROOT
STATE = _project_file(_PROJECT_ROOT, ROOT / "runs/auto-match-watchdog/auto-match-watchdog-state.json")
MODEL = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g8-public-response-training-20260927/frozen-model.json')
TRAIN_META = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g8-public-response-training-20260927/result.json')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g8-public-response-validation-20260927')
EXPECTED_MODEL_SHA256 = "6c3978109aabc51a1555555f75894affd546c9791e7aeceeff907ecbcc448116"


def complete_official_game(doc: dict) -> bool:
    """按八个完整事件单局核验牌谱；顶层 rounds 摘要可能漏记流局。"""

    if doc.get("status") != "finished":
        return False
    blocks = list(training.round_blocks(doc))
    if [number for number, _events, _start in blocks] != list(range(1, 9)):
        return False
    sequences = []
    game_ends = 0
    for _number, events, start_hands in blocks:
        if start_hands is None or len(start_hands) != 4:
            return False
        if sum(event.get("type") == "round_ended" for event in events) != 1:
            return False
        game_ends += sum(event.get("type") == "game_ended" for event in events)
        sequences.extend(event.get("seq") for event in events)
    return (game_ends == 1 and all(type(seq) is int for seq in sequences)
            and len(sequences) == len(set(sequences)))


def ready_rooms() -> tuple[list[dict], list[dict]]:
    """按 watchdog 结算顺序和十桌牌谱覆盖选房，不用弃牌响应标签选房。"""

    state = json.loads(STATE.read_text(encoding="utf-8"))
    completed = [(index, row) for index, row in enumerate(state["rooms"], 1)
                 if index >= 95 and row.get("terminal_reason") == "tournament_finished"]
    if len(completed) < 10:
        return [], [{"reason": "waiting_for_ten_completed", "completed": len(completed)}]
    official_games = defaultdict(dict)
    for _mtime, room, _tag, game_id, doc in load_rooms():
        official_games[room][game_id] = complete_official_game(doc)
    parent = json.loads(TRAIN_META.read_text(encoding="utf-8"))["parent_source_sha256"]
    selected, skipped = [], []
    for sequence, row in completed:
        room = row["room_id"]
        audit_dir = row.get("audit_dir")
        manifest = _project_file(_PROJECT_ROOT, ROOT / audit_dir / "manifest.json") if audit_dir else None
        if manifest is None or not manifest.exists():
            skipped.append({"sequence": sequence, "room_id": room, "reason": "missing_audit_manifest"})
            continue
        release = (json.loads(manifest.read_text(encoding="utf-8")).get("payload") or {}).get("policy_release") or {}
        if release.get("candidate_source_sha256") != parent:
            skipped.append({"sequence": sequence, "room_id": room, "reason": "different_parent_source"})
            continue
        if len(official_games[room]) != 10:
            skipped.append({"sequence": sequence, "room_id": room,
                            "reason": "official_game_coverage_incomplete",
                            "available_games": len(official_games[room])})
            continue
        if not all(official_games[room].values()):
            skipped.append({"sequence": sequence, "room_id": room,
                            "reason": "official_game_incomplete"})
            continue
        selected.append({"sequence": sequence, "room_id": room, "audit_dir": audit_dir})
        if len(selected) == 10:
            break
    return selected, skipped


def next_self_draw_outcomes(room_ids: set[str]) -> dict[tuple, dict]:
    """赛后诊断标签：该次真实弃牌后，本人下一次摸牌与终局谁先发生。"""

    result = {}
    for _mtime, room, _tag, game_id, doc in load_rooms():
        if room not in room_ids:
            continue
        seats = [seat.get("user_id") for seat in doc.get("seats") or []]
        if training.ACTOR not in seats:
            raise ValueError("验证房官方牌谱缺本人座位")
        actor = seats.index(training.ACTOR)
        for round_no, events, _start_hands in training.round_blocks(doc):
            for index, event in enumerate(events):
                if event.get("type") != "tile_discarded" or event.get("seat") != actor:
                    continue
                key = (game_id, round_no, event["seq"])
                if key in result:
                    raise ValueError("验证房本人弃牌重复")
                outcome = {"kind": "unknown", "winner_seat": None}
                for following in events[index + 1:]:
                    if following.get("type") == "tile_drawn" and following.get("seat") == actor:
                        outcome = {"kind": "self_draw_reached", "winner_seat": None}
                        break
                    if following.get("type") == "round_ended":
                        data = following.get("data") or {}
                        winner = None if data.get("draw") else following.get("seat")
                        if winner is None:
                            outcome = {"kind": "draw_before_self_draw", "winner_seat": None}
                        elif type(winner) is int and 0 <= winner < 4:
                            outcome = {"kind": ("self_hu_before_self_draw" if winner == actor else
                                                "other_hu_before_self_draw"),
                                       "winner_seat": winner}
                        break
                result[key] = outcome
    return result


def validation_rows(selected: list[dict]) -> tuple[list[dict], Counter]:
    """只对已接受且与官方序号/牌码一致的实际弃牌打开被鸣标签。"""

    room_ids = {row["room_id"] for row in selected}
    official, counts, _games = training._official_index(room_ids)
    next_outcomes = next_self_draw_outcomes(room_ids)
    rows = []
    seen = set()
    for room in selected:
        audit = _project_file(_PROJECT_ROOT, ROOT / room["audit_dir"])
        accepted = training._accepted(audit / "participants" / training.ACTOR / "decisions.jsonl")
        for context, request, plan in training.screen._iter_decisions(audit):
            if (request.get("window_key") or {}).get("phase") != "draw":
                continue
            key_action = accepted.get(context.get("decision_id"))
            if not key_action or not key_action.startswith("discard:"):
                continue
            key = (context["game_id"], context["round_no"], context["trigger_seq"] + 1)
            if key in seen:
                counts["duplicate_draw_window"] += 1
                continue
            seen.add(key)
            event = official.get(key)
            if event is None or event["tile"] != key_action.split(":", 1)[1] or event["seat"] != request["observation"]["seat"]:
                raise ValueError("验证房已接受弃牌与官方事件不一致")
            if event["label"] == "unknown":
                counts["unknown_response"] += 1
                continue
            legal = [item for item in (request.get("rules") or {}).get("legal_candidates") or []
                     if item.get("action_key") == key_action]
            scored = [item for item in plan.get("candidates") or []
                      if item.get("action_key") == key_action]
            if len(legal) != 1 or len(scored) != 1:
                raise ValueError("验证房已接受动作规则/评分事实缺失")
            features = training._feature_row(request["observation"], legal[0], scored[0], tile=event["tile"])
            following = next_outcomes.get(key)
            if following is None:
                raise ValueError("已接受弃牌缺下一次本人摸牌/终局诊断")
            rows.append({"room_id": room["room_id"], "game_id": key[0], "round_no": key[1],
                         "discard_seq": key[2], "label_claim": int(event["label"] == "claim"),
                         "next_self_draw_or_terminal": following,
                         "features": features})
            counts[f"validation_{event['label']}"] += 1
            counts[f"next_{following['kind']}"] += 1
    if len(rows) < 1000 or {row["room_id"] for row in rows} != {row["room_id"] for row in selected}:
        raise ValueError("验证房行数或房级覆盖不足")
    if counts["duplicate_draw_window"] or counts["unknown_response"]:
        raise ValueError("验证房出现重复动作窗或未知响应标签，先审查测量链")
    return rows, counts


def predict(rows: list[dict], frozen: dict) -> tuple[np.ndarray, dict[str, np.ndarray]]:
    """只应用冻结系数与计数，不在验证房重拟合。"""

    x, y, risk, names = model_math._matrix(rows, frozen["tiles"])
    if names != frozen["features"]:
        raise ValueError("公开特征顺序漂移")
    full = model_math._predict(x, np.array(frozen["coefficients"], dtype=np.float64))
    risk_only = model_math._predict(risk, np.array(frozen["risk_baseline_coefficients"], dtype=np.float64))
    tile_prior = []
    strength = frozen["tile_dealer_baseline_strength"]
    global_rate = frozen["tile_dealer_baseline_global_rate"]
    for row in rows:
        f = row["features"]
        cell = frozen["tile_dealer_baseline_counts"].get(
            f"{f['tile']}|{f['dealer_relative']}", {"claimed": 0, "total": 0})
        tile_prior.append((cell["claimed"] + strength * global_rate) / (cell["total"] + strength))
    return y, {"public_full": full, "risk_units": risk_only,
               "tile_dealer_prior": np.array(tile_prior, dtype=np.float64)}


def main() -> None:
    """十间新房齐全后一次性开标签；未齐时只报告准备进度。"""

    parser = argparse.ArgumentParser()
    parser.add_argument("--status", action="store_true", help="只查看房数，不读取标签")
    args = parser.parse_args()
    if args.status:
        state = json.loads(STATE.read_text(encoding="utf-8"))
        completed = [row["room_id"] for index, row in enumerate(state["rooms"], 1)
                     if index >= 95 and row.get("terminal_reason") == "tournament_finished"]
        print(json.dumps({"completed_after_94": len(completed), "required_rooms": 10,
                          "room_ids": completed}, ensure_ascii=False, indent=2))
        return
    selected, skipped = ready_rooms()
    if len(selected) < 10:
        print(json.dumps({"ready_rooms": len(selected), "required_rooms": 10,
                          "selected": [row["room_id"] for row in selected],
                          "skipped": skipped}, ensure_ascii=False, indent=2))
        return
    if OUT.exists():
        raise SystemExit("该十房验证目录已存在，拒绝重复打开")
    digest = hashlib.sha256(MODEL.read_bytes()).hexdigest()
    if digest != EXPECTED_MODEL_SHA256:
        raise ValueError("验证前模型摘要变动")
    frozen = json.loads(MODEL.read_text(encoding="utf-8"))
    if frozen["trainer_source_sha256"] != hashlib.sha256((_project_file(_PROJECT_ROOT, HERE / "g8_public_response_train_model.py")).read_bytes()).hexdigest():
        raise ValueError("冻结训练器源码变动")
    if frozen["extractor_source_sha256"] != hashlib.sha256((_project_file(_PROJECT_ROOT, HERE / "g8_public_response_training_rows.py")).read_bytes()).hexdigest():
        raise ValueError("冻结特征抽取器源码变动")
    rows, counts = validation_rows(selected)
    y, probabilities = predict(rows, frozen)
    rooms = [row["room_id"] for row in selected]
    by_room = {}
    for room in rooms:
        mask = np.array([row["room_id"] == room for row in rows], dtype=bool)
        by_room[room] = {"rows": int(mask.sum()), "observed_claim_rate": float(y[mask].mean()),
                         "models": {name: {**model_math._metrics(y[mask], p[mask]),
                                            "mean_predicted_claim_rate": float(p[mask].mean())}
                                    for name, p in probabilities.items()}}
    rng = np.random.default_rng(20260927)
    samples = rng.integers(0, len(rooms), size=(20000, len(rooms)))
    comparisons = {}
    for baseline in ("tile_dealer_prior", "risk_units"):
        comparisons[baseline] = {}
        for metric in ("brier", "log_loss"):
            values = np.array([by_room[room]["models"]["public_full"][metric] -
                               by_room[room]["models"][baseline][metric] for room in rooms])
            means = values[samples].mean(axis=1)
            comparisons[baseline][metric] = {
                "mean_candidate_minus_baseline": float(values.mean()),
                "room_bootstrap_95": [float(np.quantile(means, 0.025)),
                                      float(np.quantile(means, 0.975))],
                "improved_rooms": int(np.sum(values < 0))}
    passed = all(comparisons[baseline][metric]["room_bootstrap_95"][1] < 0
                 for baseline in comparisons for metric in ("brier", "log_loss"))
    OUT.mkdir(parents=True)
    packed = _project_file(_PROJECT_ROOT, OUT / "rows.jsonl.gz")
    with packed.open("wb") as stream:
        with gzip.GzipFile(fileobj=stream, mode="wb", filename="", mtime=0) as compressor:
            for row in rows:
                compressor.write((json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8"))
    result = {"schema": "g8-public-response-validation/1",
              "frozen_model_sha256": digest,
              "validation_rooms_in_completion_order": rooms,
              "skipped_earlier_rooms": skipped,
              "rows_gzip_sha256": hashlib.sha256(packed.read_bytes()).hexdigest(),
              "counts": dict(sorted(counts.items())),
              "by_room": by_room, "room_bootstrap_comparisons": comparisons,
              "prediction_gate_passed": passed,
              "boundary": "仅对十间新房已执行弃牌验证被鸣概率；不代表备选牌反事实或完整桌收益"}
    (_project_file(_PROJECT_ROOT, OUT / "result.json")).write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                                     encoding="utf-8")
    print(json.dumps({"rooms": rooms, "rows": len(rows), "prediction_gate_passed": passed,
                      "room_bootstrap_comparisons": comparisons}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
