#!/usr/bin/env python3
"""第 95 房起被鸣验证十房之后的独立十房，冻结后验证时序差分。"""

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
import hashlib
import json
from pathlib import Path

import numpy as np

import g8_direct_race_train_model as direct
import g8_public_response_train_model as fit
import g8_public_response_training_rows as source
import g8_public_response_validate as official
import g9_temporal_delta_preflight as preflight
import g9_temporal_delta_train as temporal


HERE = Path(__file__).resolve().parent
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g9-temporal-delta-validation-20260927')
COHORT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g9-temporal-delta-validation-20260927/cohort.json')
RESULT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g9-temporal-delta-validation-20260927/result.json')
MODEL = temporal.OUT / "frozen-model.json"
EXPECTED_MODEL_SHA256 = "9327417cbfe98ea65e4a82929e59342c34f12de6d2fcf516aee6d733121785ec"
FROZEN_LABELS_SOURCE_SHA256 = "7eddcf106d3b3235763de318bc9073661fd0fe48cb5242cf3ea23487ee60c4c5"
ROOM_COMPLETENESS_FIX_SOURCE_SHA256 = "6a617548f5cde5807c7e76689f05c68281acd7c834abf479fb0d7b7b717a7507"


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def status() -> dict:
    """只读 watchdog 账本；未凑齐二十间前绝不读取官方事件/标签。"""

    state = json.loads(official.STATE.read_text(encoding="utf-8"))
    completed = [(index, row["room_id"]) for index, row in enumerate(state["rooms"], 1)
                 if index >= 95 and row.get("terminal_reason") == "tournament_finished"]
    return {"completed_after_94": len(completed), "required_before_freeze": 20,
            "cohort_frozen": COHORT.exists(),
            "validation_run": RESULT.exists()}


def freeze() -> dict:
    """只按终局与父代身份/完整牌谱选房，先保留 G8 十房，再选后续十房。"""

    if COHORT.exists():
        raise SystemExit("G9 独立房已冻结，拒绝重选")
    snapshot = status()
    if snapshot["completed_after_94"] < 20:
        raise SystemExit("第 95 房后尚不足二十间完赛，保持验证标签封存")
    if _hash(MODEL) != EXPECTED_MODEL_SHA256:
        raise ValueError("G9 训练模型摘要漂移")
    state = json.loads(official.STATE.read_text(encoding="utf-8"))
    completed = [(index, row) for index, row in enumerate(state["rooms"], 1)
                 if index >= 95 and row.get("terminal_reason") == "tournament_finished"]
    games = defaultdict(dict)
    for _mtime, room, _tag, game_id, doc in source.load_rooms():
        games[room][game_id] = official.complete_official_game(doc)
    parent = json.loads(fit.RESULT.read_text(encoding="utf-8"))["parent_source_sha256"]
    eligible, skipped = [], []
    for sequence, row in completed:
        room_id = row["room_id"]
        audit_dir = row.get("audit_dir")
        manifest = source.ROOT / audit_dir / "manifest.json" if audit_dir else None
        if manifest is None or not manifest.exists():
            skipped.append({"sequence": sequence, "room_id": room_id, "reason": "manifest_missing"})
            continue
        release = (json.loads(manifest.read_text(encoding="utf-8")).get("payload") or {}).get("policy_release") or {}
        if release.get("candidate_source_sha256") != parent:
            skipped.append({"sequence": sequence, "room_id": room_id, "reason": "parent_mismatch"})
            continue
        if len(games[room_id]) != 10 or not all(games[room_id].values()):
            skipped.append({"sequence": sequence, "room_id": room_id, "reason": "official_game_incomplete"})
            continue
        decision_file = source.ROOT / audit_dir / "participants" / source.ACTOR / "decisions.jsonl"
        eligible.append({"sequence": sequence, "room_id": room_id, "audit_dir": audit_dir,
                         "manifest_sha256": _hash(manifest),
                         "decision_bytes": decision_file.stat().st_size})
        if len(eligible) == 20:
            break
    if len(eligible) < 20:
        raise SystemExit("同父代、完整官方牌谱的合格房不足二十间，不冻结")
    g8_rooms, _g8_skipped = official.ready_rooms()
    if [row["room_id"] for row in eligible[:10]] != [row["room_id"] for row in g8_rooms]:
        raise ValueError("前十房与已预登记 G8 信息验证房不一致")
    cohort = {"schema": "g9-temporal-delta-independent-cohort/1",
              "selection": "第95房以后最先20间合格完整父代房，前10保留G8，后10只作G9信息验证",
              "source_model_sha256": EXPECTED_MODEL_SHA256,
              "g8_reserved_rooms": [row["room_id"] for row in eligible[:10]],
              "validation_rooms": eligible[10:20], "skipped_before_20": skipped,
              "target_labels_opened": False}
    OUT.mkdir(parents=True, exist_ok=True)
    COHORT.write_text(json.dumps(cohort, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                      encoding="utf-8")
    return {"cohort_frozen": True, "g8_reserved": len(eligible[:10]),
            "g9_validation": len(eligible[10:20]), "skipped": len(skipped)}


def validation_rows(selected: list[dict]) -> tuple[list[dict], Counter]:
    """冻结房后才读取官方弃牌与下一次本人摸牌/局终标签。"""

    room_ids = {row["room_id"] for row in selected}
    official_discards, counts, _games = source._official_index(room_ids)
    outcomes = official.next_self_draw_outcomes(room_ids)
    rows = []
    seen = set()
    for room in selected:
        audit = source.ROOT / room["audit_dir"]
        if _hash(audit / "manifest.json") != room["manifest_sha256"]:
            raise ValueError("验证房发布清单摘要漂移")
        decision_file = audit / "participants" / source.ACTOR / "decisions.jsonl"
        if decision_file.stat().st_size != room["decision_bytes"]:
            raise ValueError("验证房决策记录字节数漂移")
        accepted = source._accepted(decision_file)
        for context, request, plan in source.screen._iter_decisions(audit):
            if (request.get("window_key") or {}).get("phase") != "draw":
                continue
            action = accepted.get(context.get("decision_id"))
            if not action or not action.startswith("discard:"):
                continue
            key = (context["game_id"], context["round_no"], context["trigger_seq"] + 1)
            if key in seen:
                raise ValueError("验证房已接受弃牌动作重复")
            seen.add(key)
            event = official_discards.get(key)
            tile = action.split(":", 1)[1]
            if event is None or event["tile"] != tile or event["seat"] != request["observation"]["seat"]:
                raise ValueError("已接受弃牌与官方事件不一致")
            outcome = outcomes.get(key)
            if outcome is None or outcome["kind"] == "unknown":
                raise ValueError("下一次本人摸牌/终局标签不可判")
            counts[f"next_{outcome['kind']}"] += 1
            if outcome["kind"] == "draw_before_self_draw":
                continue
            if outcome["kind"] not in ("other_hu_before_self_draw", "self_draw_reached"):
                raise ValueError("出现预登记主二元目标之外的终点")
            legal = [item for item in (request.get("rules") or {}).get("legal_candidates") or []
                     if item.get("action_key") == action]
            scored = [item for item in plan.get("candidates") or []
                      if item.get("action_key") == action]
            if len(legal) != 1 or len(scored) != 1:
                raise ValueError("已执行动作规则/评分事实缺失")
            features = source._feature_row(request["observation"], legal[0], scored[0], tile=tile)
            rows.append({"room_id": room["room_id"], "game_id": key[0],
                         "round_no": key[1], "discard_seq": key[2],
                         "label_claim": int(outcome["kind"] == "other_hu_before_self_draw"),
                         "features": features})
    if {row["room_id"] for row in rows} != room_ids or len(rows) < 1000:
        raise ValueError("独立房目标行覆盖不足")
    return rows, counts


def validate() -> dict:
    """冻结模型一次性打分；确认集不能重拟合或更换房。"""

    if RESULT.exists():
        raise SystemExit("G9 独立结果已存在，拒绝覆盖")
    cohort = json.loads(COHORT.read_text(encoding="utf-8"))
    if cohort["target_labels_opened"] is not False or cohort["source_model_sha256"] != EXPECTED_MODEL_SHA256:
        raise ValueError("独立房封存合同不符")
    if _hash(MODEL) != EXPECTED_MODEL_SHA256:
        raise ValueError("训练模型摘要漂移")
    frozen = json.loads(MODEL.read_text(encoding="utf-8"))
    if frozen["training_script_sha256"] != _hash(Path(temporal.__file__)):
        raise ValueError("时序提取/训练代码变更，拒绝打开验证标签")
    if frozen["temporal_extract_source_sha256"] != _hash(Path(preflight.__file__)):
        raise ValueError("公开前态摘要代码变更，拒绝打开验证标签")
    labels_hash = frozen["labels_source_sha256"]
    actual_labels_source = _hash(Path(official.__file__))
    if labels_hash != actual_labels_source and not (
            labels_hash == FROZEN_LABELS_SOURCE_SHA256
            and actual_labels_source == ROOM_COMPLETENESS_FIX_SOURCE_SHA256):
        raise ValueError("官方下一摸/终局标签代码发生未核准漂移，拒绝打开验证标签")
    # 唯一兼容漂移见 G9-VALIDATION-CODE-DRIFT-AUDIT：f52dde26a 只改房完整性
    # 筛选，next_self_draw_outcomes 的 AST 与冻结版本完全相同。
    if frozen["validation_labels_opened"] is not False:
        raise ValueError("训练期已使用验证标签")
    rows, counts = validation_rows(cohort["validation_rooms"])
    keys = [(row["game_id"], row["round_no"], row["discard_seq"]) for row in rows]
    temporal_map, temporal_counts = temporal.temporal_rows(set(keys), cohort["validation_rooms"])
    base_model = json.loads((direct.OUT / "frozen-model.json").read_text(encoding="utf-8"))
    full_x, y, _risk, names = fit._matrix(rows, base_model["tiles"])
    if names != base_model["all_feature_names"]:
        raise ValueError("静态特征次序漂移")
    state_x = full_x[:, base_model["state_indices"]]
    temporal_x = np.asarray([temporal_map[key] for key in keys], dtype=np.float64)
    matrices = {"state": state_x, "state_plus_temporal": np.column_stack([state_x, temporal_x])}
    predictions = {}
    for name, matrix in matrices.items():
        spec = frozen["models"][name]
        if spec["feature_names"] != ([names[index] for index in base_model["state_indices"]] +
                                      (list(temporal.NAMES) if name == "state_plus_temporal" else [])):
            raise ValueError("模型特征合同漂移")
        predictions[name] = fit._predict(matrix, np.asarray(spec["coefficients"]))
    room_ids = [row["room_id"] for row in cohort["validation_rooms"]]
    row_rooms = np.array([row["room_id"] for row in rows])
    by_room = {}
    for room in room_ids:
        mask = row_rooms == room
        by_room[room] = {"rows": int(mask.sum()),
                         "observed_other_hu_rate": float(y[mask].mean()),
                         "prior_available": int(np.sum(temporal_x[mask, 0] == 1)),
                         "predicted_other_hu_rate": {name: float(p[mask].mean())
                                                     for name, p in predictions.items()},
                         "metrics": {name: fit._metrics(y[mask], p[mask])
                                     for name, p in predictions.items()}}
    wall = np.array([row["features"]["wall_remaining"] for row in rows])
    subgroups = {
        "prior_available": temporal_x[:, 0] == 1,
        "prior_missing": temporal_x[:, 0] == 0,
        "wall_gt_60": wall > 60,
        "wall_21_to_60": (wall > 20) & (wall <= 60),
        "wall_le_20": wall <= 20,
    }
    diagnostic = {}
    for group, mask in subgroups.items():
        if not np.any(mask):
            diagnostic[group] = {"rows": 0}
            continue
        diagnostic[group] = {
            "rows": int(mask.sum()), "observed_other_hu_rate": float(y[mask].mean()),
            "predicted_other_hu_rate": {name: float(p[mask].mean())
                                        for name, p in predictions.items()},
            "metrics": {name: fit._metrics(y[mask], p[mask])
                        for name, p in predictions.items()}}
    rng = np.random.default_rng(20260927)
    samples = rng.integers(0, len(room_ids), size=(20000, len(room_ids)))
    comparison = {}
    for metric in ("brier", "log_loss"):
        differences = np.array([by_room[room]["metrics"]["state_plus_temporal"][metric] -
                                by_room[room]["metrics"]["state"][metric]
                                for room in room_ids])
        boot = differences[samples].mean(axis=1)
        comparison[metric] = {"mean_extended_minus_state": float(differences.mean()),
                              "room_bootstrap_95": [float(np.quantile(boot, 0.025)),
                                                    float(np.quantile(boot, 0.975))],
                              "improved_rooms": int(np.sum(differences < 0))}
    result = {"schema": "g9-temporal-delta-independent-validation/1",
              "cohort_sha256": _hash(COHORT), "model_sha256": EXPECTED_MODEL_SHA256,
              "rooms": room_ids, "rows": len(rows), "label_counts": dict(counts),
              "temporal_coverage": dict(temporal_counts),
              "by_room": by_room, "diagnostic_subgroups": diagnostic,
              "extended_minus_state": comparison,
              "information_gate_passed": all(comparison[metric]["room_bootstrap_95"][1] < 0
                                             for metric in ("brier", "log_loss")),
              "boundary": "仅独立预测信息门；不能推出改动作或整桌收益"}
    RESULT.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                      encoding="utf-8")
    return {key: value for key, value in result.items() if key != "by_room"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--status", action="store_true")
    action.add_argument("--freeze", action="store_true")
    action.add_argument("--validate", action="store_true")
    args = parser.parse_args()
    print(json.dumps(status() if args.status else freeze() if args.freeze else validate(),
                     ensure_ascii=False, indent=2))
