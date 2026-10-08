#!/usr/bin/env python3
"""结果盲检查公开被鸣模型在同向听、即刻有效张不减的弃牌间是否有排序空间。"""

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

import g8_public_response_train_model as fit
import g8_public_response_training_rows as extract


HERE = Path(__file__).resolve().parent
ROOT = _PROJECT_ROOT
FROZEN = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g8-two-white-next-draw-20260927/frozen_rooms.json')
MODEL = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g8-public-response-training-20260927/frozen-model.json')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g8-public-response-actionability-20260927/result.json')


def _immediate_support(candidate: dict) -> int | None:
    """规则事实中公开剩余估计数之和，未知时不猜。"""

    facts = candidate.get("facts") or {}
    entries = facts.get("useful_tiles")
    if not isinstance(entries, list):
        return None
    values = [entry.get("remaining_estimate") for entry in entries]
    if any(type(value) is not int for value in values):
        return None
    return sum(values)


def main() -> None:
    """只读冻结审计的动作前观察，不读已执行后的响应或结算。"""

    frozen = json.loads(FROZEN.read_text(encoding="utf-8"))
    model = json.loads(MODEL.read_text(encoding="utf-8"))
    if model["extractor_source_sha256"] != hashlib.sha256(
            (_project_file(_PROJECT_ROOT, HERE / "g8_public_response_training_rows.py")).read_bytes()).hexdigest():
        raise ValueError("模型所绑定的公开特征抽取器漂移")
    if model["trainer_source_sha256"] != hashlib.sha256(
            (_project_file(_PROJECT_ROOT, HERE / "g8_public_response_train_model.py")).read_bytes()).hexdigest():
        raise ValueError("模型所绑定的训练器漂移")
    if model["validation_labels_opened"] is not False:
        raise ValueError("结果盲模型身份不符")
    beta = np.array(model["coefficients"], dtype=np.float64)
    counts = Counter()
    rooms = defaultdict(set)
    first_examples = []
    reductions = []
    for room in frozen["rooms"]:
        audit = _project_file(_PROJECT_ROOT, ROOT / room["audit_dir"])
        decisions = audit / "participants" / extract.ACTOR / "decisions.jsonl"
        if decisions.stat().st_size != room["decision_bytes"]:
            raise ValueError("冻结房审计漂移")
        release = (json.loads((audit / "manifest.json").read_text(encoding="utf-8")).get("payload") or {}).get("policy_release") or {}
        if release.get("candidate_source_sha256") != frozen["parent_source_sha256"]:
            raise ValueError("父代身份漂移")
        feature_rows = []
        windows = []
        seen = set()
        for context, request, plan in extract.screen._iter_decisions(audit):
            if (request.get("window_key") or {}).get("phase") != "draw":
                continue
            key = (context.get("game_id"), context.get("round_no"), context.get("trigger_seq"))
            if key in seen:
                counts["duplicate_draw_window"] += 1
                continue
            seen.add(key)
            ranked = sorted(plan.get("candidates") or [], key=lambda item: item.get("rank", 10**9))
            if not ranked or not ranked[0]["action_key"].startswith("discard:"):
                continue
            counts["parent_discard_windows"] += 1
            legal = {item["action_key"]: item for item in
                     (request.get("rules") or {}).get("legal_candidates") or []}
            top_key = ranked[0]["action_key"]
            top_legal = legal.get(top_key)
            if top_legal is None:
                raise ValueError("父代弃牌不在合法候选")
            shanten = (top_legal.get("facts") or {}).get("shanten_after")
            support = _immediate_support(top_legal)
            if type(shanten) is not int or support is None:
                counts["top_facts_unknown"] += 1
                continue
            eligible = []
            for item in ranked[1:]:
                action_key = item["action_key"]
                if not action_key.startswith("discard:"):
                    continue
                candidate = legal.get(action_key)
                if candidate is None:
                    raise ValueError("备选弃牌不在合法候选")
                if (candidate.get("facts") or {}).get("shanten_after") != shanten:
                    continue
                alternative_support = _immediate_support(candidate)
                if alternative_support is None or alternative_support < support:
                    continue
                eligible.append((item, candidate, alternative_support))
            if not eligible:
                continue
            counts["same_shanten_support_not_lower_windows"] += 1
            start = len(feature_rows)
            entries = [(ranked[0], top_legal, support)] + eligible
            for ranked_item, rule_item, _support in entries:
                tile = ranked_item["action_key"].split(":", 1)[1]
                features = extract._feature_row(request["observation"], rule_item,
                                                ranked_item, tile=tile)
                feature_rows.append({"features": features, "label_claim": 0})
            windows.append((key, start, len(entries), top_key, shanten, support,
                            ranked[0].get("total_score"),
                            [item[0]["action_key"] for item in eligible],
                            [item[0].get("total_score") for item in eligible]))
        if not feature_rows:
            continue
        x, _y, _risk, names = fit._matrix(feature_rows, model["tiles"])
        if names != model["features"]:
            raise ValueError("公开特征映射漂移")
        probability = fit._predict(x, beta)
        for key, start, size, top_key, shanten, support, top_score, alternative_keys, alternative_scores in windows:
            top_p = float(probability[start])
            alt_p = probability[start + 1:start + size]
            best = int(np.argmin(alt_p))
            reduction = top_p - float(alt_p[best])
            reductions.append(reduction)
            if reduction <= 0:
                continue
            counts["lower_predicted_claim_available"] += 1
            rooms["lower_predicted_claim_available"].add(room["room_id"])
            alt_score = alternative_scores[best]
            if type(top_score) in (int, float) and type(alt_score) in (int, float):
                gap = float(top_score) - float(alt_score)
                bucket = "equal" if gap == 0 else "within_10" if 0 < gap <= 10 else "over_10" if gap > 10 else "inverted"
                counts[f"lower_risk_parent_score_gap_{bucket}"] += 1
            else:
                gap = None
                counts["lower_risk_parent_score_gap_unknown"] += 1
            counts[f"lower_risk_shanten_{shanten}"] += 1
            if reduction >= 0.02:
                counts["reduction_at_least_2pp"] += 1
                rooms["reduction_at_least_2pp"].add(room["room_id"])
            if len(first_examples) < 20:
                first_examples.append({"room_id": room["room_id"], "game_id": key[0],
                                       "round_no": key[1], "trigger_seq": key[2],
                                       "parent_action": top_key,
                                       "alternative_action": alternative_keys[best],
                                       "shanten_after": shanten,
                                       "parent_immediate_support": support,
                                       "parent_score_gap": gap,
                                       "parent_predicted_claim": top_p,
                                       "alternative_predicted_claim": float(alt_p[best])})
    result = {"schema": "g8-public-response-actionability/1", "outcome_blind": True,
              "official_rooms": len(frozen["rooms"]),
              "frozen_model_sha256": hashlib.sha256(MODEL.read_bytes()).hexdigest(),
              "counts": dict(sorted(counts.items())),
              "rooms_with_lower_predicted_claim": len(rooms["lower_predicted_claim_available"]),
              "rooms_with_at_least_2pp_reduction": len(rooms["reduction_at_least_2pp"]),
              "reduction_quantiles_all_eligible": {
                  str(q): float(np.quantile(reductions, q)) for q in (0.0, 0.25, 0.5, 0.75, 0.9, 0.99, 1.0)
              } if reductions else {},
              "first_examples": first_examples,
              "boundary": "只读动作前规则事实与冻结预测器；即刻向听和有效张不减不是整桌收益担保；未执行备选牌存在分布外风险"}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                   encoding="utf-8")
    print(json.dumps({key: value for key, value in result.items() if key != "first_examples"},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
