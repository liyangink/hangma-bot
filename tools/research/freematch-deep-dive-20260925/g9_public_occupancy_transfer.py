#!/usr/bin/env python3
"""检验公开牌类先验能否在时间留房中预测宽面真实墙容量差。"""

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

import g9_diversity_hidden_occupancy_91room as base


HERE = Path(__file__).resolve().parent
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g9-public-occupancy-transfer-20260927/result.json')
PRIOR = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g9-diversity-hidden-occupancy-91room-20260927/result.json')
HONORS = frozenset(("东", "南", "西", "北", "中", "发"))
BUCKETS = ("white", "other_honor", "terminal", "near_edge", "middle")


def _bucket(code: str) -> str:
    """只按牌码归入事前固定五类；未知牌码不悄悄兜底。"""
    if code == "白":
        return "white"
    if code in HONORS:
        return "other_honor"
    if len(code) == 2 and code[0] in "123456789" and code[1] in "wbt":
        rank = int(code[0])
        if rank in (1, 9):
            return "terminal"
        if rank in (2, 8):
            return "near_edge"
        return "middle"
    raise ValueError(f"未知牌码 {code!r}")


def _extract() -> tuple[list[dict], dict]:
    """复用已冻结 A/B 选择，完整核对官方弃后状态；暗手仅作标签。"""
    frozen_bytes = base.FROZEN.read_bytes()
    frozen = json.loads(frozen_bytes)
    prior_result = json.loads(PRIOR.read_text(encoding="utf-8"))
    if hashlib.sha256(frozen_bytes).hexdigest() != prior_result["source_frozen_rooms_sha256"]:
        raise ValueError("冻结房清单摘要漂移")
    selected = {room["room_id"] for room in frozen["rooms"]}
    docs = defaultdict(dict)
    fingerprints = []
    for _mtime, room, _tag, game_id, doc in base.source.load_rooms():
        if room not in selected:
            continue
        docs[room][game_id] = doc
        fingerprints.append((game_id, hashlib.sha256(json.dumps(
            doc, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")).hexdigest()))
    fingerprint = hashlib.sha256(json.dumps(
        sorted(fingerprints), separators=(",", ":")
    ).encode()).hexdigest()
    if fingerprint != prior_result["official_docs_fingerprint_sha256"]:
        raise ValueError("官方牌谱摘要漂移")

    rows = []
    totals = Counter()
    room_order = {room["room_id"]: index for index, room in enumerate(frozen["rooms"])}
    for room in frozen["rooms"]:
        room_id = room["room_id"]
        audit = base.source.ROOT / room["audit_dir"]
        decision_file = audit / "participants" / base.source.ACTOR / "decisions.jsonl"
        if decision_file.stat().st_size != room["decision_bytes"]:
            raise ValueError("冻结房审计字节数漂移")
        release = ((json.loads((audit / "manifest.json").read_text(encoding="utf-8"))
                    .get("payload") or {}).get("policy_release") or {})
        if release.get("candidate_source_sha256") != frozen["parent_source_sha256"]:
            raise ValueError("冻结父代摘要漂移")
        accepted = base.source._accepted(decision_file)
        snapshots = base._room_snapshots(docs[room_id])
        seen = set()
        for context, request, plan in base.source.screen._iter_decisions(audit):
            key = (context["game_id"], context["round_no"], context["trigger_seq"])
            phase = (request.get("window_key") or {}).get("phase")
            if (*key, phase) in seen:
                raise ValueError("同一动作窗口重复")
            seen.add((*key, phase))
            pair = base.prior._alternatives(request, plan)
            if pair is None:
                continue
            totals["public_candidate_pair"] += 1
            chosen, _alternate, a_useful, b_useful, gap, _width, safe = pair
            if accepted.get(context["decision_id"]) != chosen:
                totals["parent_plan_not_accepted"] += 1
                continue
            snap = snapshots.get((key[0], key[1], key[2] + 1))
            if snap is None:
                totals["official_snapshot_missing"] += 1
                continue
            obs = request["observation"]
            seat = obs["seat"]
            if snap["discarder"] != seat or snap["tile"] != chosen[8:]:
                totals["official_discard_mismatch"] += 1
                continue
            hand = list(obs["my_hand"])
            if obs.get("drawn_tile") is not None and len(hand) % 3 == 1:
                hand.append(obs["drawn_tile"])
            expected = Counter(hand)
            expected[chosen[8:]] -= 1
            expected += Counter()
            if expected != Counter(snap["hands"][seat]):
                totals["own_hand_mismatch"] += 1
                continue
            others = Counter()
            for other_seat, other_hand in enumerate(snap["hands"]):
                if other_seat != seat:
                    others.update(other_hand)
            if any(amount < others[code] for useful in (a_useful, b_useful)
                   for code, amount in useful.items()):
                totals["negative_wall_capacity"] += 1
                continue
            wall_remaining = obs.get("remaining_tile_count")
            if type(wall_remaining) is not int or wall_remaining < 20:
                totals["invalid_wall_count"] += 1
                continue
            unknown = wall_remaining + sum(others.values())
            public = dict(a_useful)
            if any(public.get(code, amount) != amount
                   for code, amount in b_useful.items()):
                totals["counterfactual_capacity_mismatch"] += 1
                continue
            public.update(b_useful)
            if sum(public.values()) > unknown:
                totals["invalid_unknown_pool"] += 1
                continue
            totals["matched"] += 1
            if gap != 0 or not safe:
                continue
            tiles = [{"bucket": _bucket(code), "capacity": amount,
                      "held": others[code], "a": a_useful.get(code, 0),
                      "b": b_useful.get(code, 0)}
                     for code, amount in sorted(public.items())]
            a_wall = sum(amount - others[code] for code, amount in a_useful.items())
            b_wall = sum(amount - others[code] for code, amount in b_useful.items())
            exact_delta = b_wall - a_wall
            # 重叠牌码容量相同，对差值为零；逐牌展开仍须和独立求和一致。
            expanded_delta = sum((tile["b"] - tile["a"]) -
                                 (int(tile["b"] > 0) - int(tile["a"] > 0)) * tile["held"]
                                 for tile in tiles)
            if expanded_delta != exact_delta:
                raise ValueError("墙容量差与逐牌展开不一致")
            rows.append({"room_id": room_id, "room_order": room_order[room_id],
                         "game_id": key[0], "actual_delta": int(exact_delta),
                         "tiles": tiles})
    if dict(sorted(totals.items())) != prior_result["totals"]:
        raise ValueError("与 91 房原诊断排除计数不一致")
    primary = prior_result["groups"]["0"]["wall_capacity_difference"]
    if (len(rows), len({row["room_id"] for row in rows}),
            len({row["game_id"] for row in rows})) != (
            primary["windows"], primary["rooms"],
            prior_result["groups"]["0"]["complete_table_ids"]):
        raise ValueError("与 91 房原诊断主样本身份不一致")
    if abs(np.mean([row["actual_delta"] for row in rows]) - primary["mean"]) > 1e-12:
        raise ValueError("与 91 房原诊断墙容量均值不一致")
    return rows, {"totals": dict(sorted(totals.items())),
                  "official_docs_fingerprint_sha256": fingerprint,
                  "frozen_rooms_sha256": hashlib.sha256(frozen_bytes).hexdigest()}


def _model(train: list[dict]) -> tuple[dict[str, float], float, float]:
    """只由前 45 房估计五类对手占用率和截距。"""
    by_bucket = defaultdict(lambda: [0, 0])
    for row in train:
        for tile in row["tiles"]:
            cell = by_bucket[tile["bucket"]]
            cell[0] += tile["held"]
            cell[1] += tile["capacity"]
    held = sum(cell[0] for cell in by_bucket.values())
    capacity = sum(cell[1] for cell in by_bucket.values())
    global_rate = held / capacity
    rates = {bucket: (by_bucket[bucket][0] + 50 * global_rate) /
             (by_bucket[bucket][1] + 50) for bucket in BUCKETS}
    train_mean = float(np.mean([row["actual_delta"] for row in train]))
    raw_mean = float(np.mean([_raw(row, rates) for row in train]))
    return rates, train_mean - raw_mean, train_mean


def _raw(row: dict, rates: dict[str, float]) -> float:
    """对每种可见有效牌累加 B−A 的预期牌墙容量差。"""
    return sum((tile["b"] - tile["a"]) * (1 - rates[tile["bucket"]])
               for tile in row["tiles"])


def _summary(rows: list[dict], rates: dict[str, float], intercept: float,
             constant: float) -> dict:
    """以房为重采样单位估计平方误差差与方向分层。"""
    if not rows:
        raise ValueError("时间留出房没有主样本")
    for row in rows:
        row["predicted"] = intercept + _raw(row, rates)
        row["model_sqerr"] = (row["predicted"] - row["actual_delta"]) ** 2
        row["constant_sqerr"] = (constant - row["actual_delta"]) ** 2
        row["loss_delta"] = row["model_sqerr"] - row["constant_sqerr"]
    by_room = defaultdict(list)
    for row in rows:
        by_room[row["room_id"]].append(row)
    room_names = sorted(by_room)
    sums = np.asarray([sum(row["loss_delta"] for row in by_room[room])
                       for room in room_names], dtype=float)
    counts = np.asarray([len(by_room[room]) for room in room_names], dtype=float)
    rng = np.random.default_rng(20260927)
    indices = rng.integers(0, len(room_names), size=(20000, len(room_names)))
    samples = sums[indices].sum(axis=1) / counts[indices].sum(axis=1)
    values = np.asarray([row["actual_delta"] for row in rows], dtype=float)
    preds = np.asarray([row["predicted"] for row in rows], dtype=float)
    correlation = None if np.std(preds) == 0 or np.std(values) == 0 else float(
        np.corrcoef(preds, values)[0, 1])
    return {"windows": len(rows), "rooms": len(room_names),
            "true_mean": float(values.mean()), "predicted_mean": float(preds.mean()),
            "model_mse": float(np.mean([row["model_sqerr"] for row in rows])),
            "constant_mse": float(np.mean([row["constant_sqerr"] for row in rows])),
            "model_minus_constant_mse": float(sums.sum() / counts.sum()),
            "room_bootstrap_95": [float(np.quantile(samples, 0.025)),
                                  float(np.quantile(samples, 0.975))],
            "pearson_correlation": correlation,
            "by_room": {room: {"windows": len(group),
                               "loss_delta_mean": float(np.mean([r["loss_delta"] for r in group]))}
                        for room, group in sorted(by_room.items())}}


def main() -> None:
    """仅首次写入时间留房结果，原 91 房诊断不改写。"""
    if OUT.exists():
        raise SystemExit("公开牌类时间留房结果已存在，拒绝覆盖")
    rows, source = _extract()
    train = [row for row in rows if row["room_order"] < 45]
    holdout = [row for row in rows if row["room_order"] >= 45]
    if len(train) != 229 or len(holdout) != 220:
        raise ValueError("与原诊断时间分半窗口数不一致")
    rates, intercept, constant = _model(train)
    training = _summary(train, rates, intercept, constant)
    test = _summary(holdout, rates, intercept, constant)
    lower, upper = np.quantile([row["predicted"] for row in train], [0.25, 0.75])
    strata = {}
    for label, subset in (
        ("low", [row for row in holdout if row["predicted"] < lower]),
        ("middle", [row for row in holdout if lower <= row["predicted"] <= upper]),
        ("high", [row for row in holdout if row["predicted"] > upper]),
    ):
        strata[label] = {"windows": len(subset),
                         "rooms": len({row["room_id"] for row in subset}),
                         "true_mean": None if not subset else float(np.mean(
                             [row["actual_delta"] for row in subset]))}
    result = {"schema": "g9-public-occupancy-transfer/1",
              "source": source, "source_prereg_sha256": hashlib.sha256(
                  (_project_file(_PROJECT_ROOT, HERE / "G9-PUBLIC-OCCUPANCY-TRANSFER-PREREG-2026-09-27.md")).read_bytes()
              ).hexdigest(),
              "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "buckets": list(BUCKETS), "shrinkage_physical_tiles": 50,
              "train_room_count": 45, "holdout_room_count": 46,
              "training_global_mean": constant, "training_calibration_intercept": intercept,
              "training_bucket_held_rates": rates,
              "training": training, "holdout": test,
              "training_prediction_quartiles": [float(lower), float(upper)],
              "holdout_prediction_strata": strata,
              "time_transfer_passed": test["model_minus_constant_mse"] < 0 and
                  test["room_bootstrap_95"][1] < 0,
              "boundary": "仅离线赛后暗手标签；不证明动作价值，不读留出 G8/G9 新房"}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                   encoding="utf-8")
    display = {key: value for key, value in result.items() if key not in ("training", "holdout")}
    display["training"] = {key: value for key, value in training.items() if key != "by_room"}
    display["holdout"] = {key: value for key, value in test.items() if key != "by_room"}
    print(json.dumps(display, ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
