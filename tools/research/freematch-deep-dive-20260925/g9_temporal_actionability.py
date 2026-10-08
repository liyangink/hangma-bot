#!/usr/bin/env python3
"""结果盲检查冻结时序风险是否遇到真实可比较的分牌型动作取舍。"""

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
import gzip
import hashlib
import json
from pathlib import Path

import numpy as np

import g8_direct_race_train_model as direct
import g8_public_response_train_model as fit
import g8_public_response_training_rows as source
import g9_action_space_atlas as atlas
import g9_temporal_delta_train as temporal


HERE = Path(__file__).resolve().parent
MODEL = temporal.OUT / "frozen-model.json"
FEATURES = temporal.OUT / "temporal-features.jsonl.gz"
EXPECTED_MODEL_SHA256 = "9327417cbfe98ea65e4a82929e59342c34f12de6d2fcf516aee6d733121785ec"
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g9-temporal-actionability-20260927/result.json')


def _probabilities() -> tuple[dict[tuple, float], list[float]]:
    """冻结训练模型只用于暴露分层，不读取或优化未来房标签。"""

    if hashlib.sha256(MODEL.read_bytes()).hexdigest() != EXPECTED_MODEL_SHA256:
        raise ValueError("G9 时序模型摘要漂移")
    frozen = json.loads(MODEL.read_text(encoding="utf-8"))
    original_rows, _metadata = fit._load()
    base = json.loads((direct.OUT / "frozen-model.json").read_text(encoding="utf-8"))
    by_key = {}
    with gzip.open(FEATURES, "rt", encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            key = (row["game_id"], row["round_no"], row["discard_seq"])
            if key in by_key:
                raise ValueError("时序特征动作键重复")
            by_key[key] = row["temporal"]
    selected = [(row["game_id"], row["round_no"], row["discard_seq"], row["features"])
                for row in original_rows
                if (row["game_id"], row["round_no"], row["discard_seq"]) in by_key]
    keys = [row[:3] for row in selected]
    if len(keys) != len(by_key) or set(keys) != set(by_key):
        raise ValueError("时序特征键与训练行不一致")
    # 编码器需要一个标签字段；固定为 0，仅复用公开特征，不消费被鸣或先胡标签。
    feature_only = [{"features": row[3], "label_claim": 0} for row in selected]
    x, _y, _risk, names = fit._matrix(feature_only, base["tiles"])
    if names != base["all_feature_names"]:
        raise ValueError("静态特征次序漂移")
    matrix = np.column_stack([x[:, base["state_indices"]],
                              np.asarray([by_key[key] for key in keys])])
    spec = frozen["models"]["state_plus_temporal"]
    probability = fit._predict(matrix, np.asarray(spec["coefficients"]))
    quantiles = np.quantile(probability, [1 / 3, 2 / 3]).tolist()
    return dict(zip(keys, map(float, probability))), quantiles


def main() -> None:
    """只查实际已执行父代首选与未执行合法备选的动作前规则事实。"""

    if OUT.exists():
        raise SystemExit("G9 时序动作覆盖证据已冻结，拒绝覆盖")
    probability, cutoffs = _probabilities()
    frozen = json.loads(source.FROZEN.read_text(encoding="utf-8"))
    totals = Counter()
    by_room = {}
    examples = defaultdict(list)
    for room in frozen["rooms"]:
        audit = source.ROOT / room["audit_dir"]
        decision_file = audit / "participants" / source.ACTOR / "decisions.jsonl"
        if decision_file.stat().st_size != room["decision_bytes"]:
            raise ValueError("冻结房决策审计漂移")
        accepted = source._accepted(decision_file)
        counts = Counter()
        for context, request, plan in source.screen._iter_decisions(audit):
            if (request.get("window_key") or {}).get("phase") != "draw":
                continue
            action = accepted.get(context.get("decision_id"))
            if not action or not action.startswith("discard:"):
                continue
            key = (context["game_id"], context["round_no"], context["trigger_seq"] + 1)
            chance = probability.get(key)
            if chance is None:
                continue
            ranked = sorted(plan.get("candidates") or [], key=lambda item: item.get("rank", 10**9))
            if not ranked or ranked[0].get("action_key") != action:
                counts["accepted_differs_from_parent_first"] += 1
                continue
            group = "low" if chance <= cutoffs[0] else "mid" if chance <= cutoffs[1] else "high"
            counts[f"executed_parent_first_{group}"] += 1
            legal = {row["action_key"]: row for row in
                     (request.get("rules") or {}).get("legal_candidates") or []}
            top = (legal.get(action) or {}).get("facts") or {}
            top_shanten, top_support, top_score = top.get("shanten_after"), atlas._support(top), ranked[0].get("total_score")
            if type(top_shanten) is not int or top_support is None or type(top_score) not in (int, float):
                continue
            hits = set()
            for alternative in ranked[1:]:
                alt_key = alternative.get("action_key")
                if not isinstance(alt_key, str) or not alt_key.startswith("discard:"):
                    continue
                alt = (legal.get(alt_key) or {}).get("facts") or {}
                alt_score = alternative.get("total_score")
                alt_support = atlas._support(alt)
                if alt.get("shanten_after") != top_shanten or alt_support is None or type(alt_score) not in (int, float):
                    continue
                gap = float(top_score - alt_score)
                if alt_support < top_support or gap > 10 or gap < 0:
                    continue
                for kind, field in (("standard_faster", "standard_shanten_after"),
                                    ("seven_pairs_faster", "seven_pairs_shanten_after")):
                    if not atlas._lower(alt.get(field), top.get(field)):
                        continue
                    hits.add(kind)
                    counts[f"eligible_alternative_{kind}_{group}"] += 1
                    if len(examples[kind]) < 16:
                        examples[kind].append({"room_id": room["room_id"],
                                               "game_id": key[0], "round_no": key[1],
                                               "discard_seq": key[2], "group": group,
                                               "risk": chance, "parent_action": action,
                                               "alternative_action": alt_key,
                                               "score_gap": gap,
                                               "support_delta": alt_support - top_support})
            for kind in hits:
                counts[f"eligible_window_{kind}_{group}"] += 1
        by_room[room["room_id"]] = dict(sorted(counts.items()))
        totals.update(counts)
    result = {
        "schema": "g9-temporal-actionability/1",
        "source_rooms": len(by_room), "source_model_sha256": EXPECTED_MODEL_SHA256,
        "source_training_feature_gzip_sha256": hashlib.sha256(FEATURES.read_bytes()).hexdigest(),
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "outcome_blind_for_actionability": True,
        "risk_tertile_cutoffs_training_only": cutoffs,
        "totals": dict(sorted(totals.items())),
        "rooms_with_eligible_window": {f"{kind}_{group}": sum(row.get(f"eligible_window_{kind}_{group}", 0) > 0
                                                    for row in by_room.values())
                                       for kind in ("standard_faster", "seven_pairs_faster")
                                       for group in ("low", "mid", "high")},
        "by_room": by_room, "first_examples": dict(examples),
        "boundary": "仅动作前可达性，风险分位值不得当收益阈值或在训练房反复调参"}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                   encoding="utf-8")
    print(json.dumps({key: value for key, value in result.items()
                      if key not in ("by_room", "first_examples")}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
