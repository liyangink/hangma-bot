#!/usr/bin/env python3
"""结果盲核验 G9 时序模型对同向听弃牌备选的输入是否完全相同。"""

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

import g8_direct_race_train_model as direct
import g8_public_response_actionability as actionability
import g8_public_response_train_model as fit
import g8_public_response_training_rows as extract
import g9_temporal_delta_train as temporal


HERE = Path(__file__).resolve().parent
ROOT = _PROJECT_ROOT
FROZEN = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g8-two-white-next-draw-20260927/frozen_rooms.json')
MODEL = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g9-temporal-delta-training-20260927/frozen-model.json')
ACTIONABILITY = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g8-public-response-actionability-20260927/result.json')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g9-temporal-action-invariance-20260927/result.json')


def _state_key(features: dict) -> tuple:
    """仅投影冻结 G9 模型使用的静态列；牌码、风险和同牌外露不在其中。"""

    return (features["dealer_relative"], features["wall_remaining"],
            features["shanten_after"], features["white_count"],
            features["catch_play"], tuple(features["river_lengths_relative"]),
            tuple(features["meld_lengths_relative"]))


def main() -> None:
    """逐窗比较冻结父代与合法同向听备选，不读取未来事件或积分。"""

    if OUT.exists():
        raise SystemExit("时序输入不变性结果已存在，拒绝覆盖")
    frozen_bytes = FROZEN.read_bytes()
    frozen = json.loads(frozen_bytes)
    model_bytes = MODEL.read_bytes()
    model = json.loads(model_bytes)
    old = json.loads(ACTIONABILITY.read_text(encoding="utf-8"))
    base_model = json.loads((direct.OUT / "frozen-model.json").read_text(encoding="utf-8"))
    all_names = fit._feature_names(base_model["tiles"])
    state_names = [all_names[index] for index in direct.state_columns(all_names)]
    if model["models"]["state"]["feature_names"] != state_names:
        raise ValueError("冻结静态模型列与结果盲投影不一致")
    if model["models"]["state_plus_temporal"]["feature_names"] != state_names + list(temporal.NAMES):
        raise ValueError("冻结时序模型列或次序漂移")
    if model["training_script_sha256"] != hashlib.sha256(Path(temporal.__file__).read_bytes()).hexdigest():
        raise ValueError("冻结时序训练源码摘要漂移")
    if old["counts"]["same_shanten_support_not_lower_windows"] < 1:
        raise ValueError("既有动作面板不含目标窗口")

    totals = Counter()
    by_room = {}
    for room in frozen["rooms"]:
        audit = _project_file(_PROJECT_ROOT, ROOT / room["audit_dir"])
        decision_file = audit / "participants" / extract.ACTOR / "decisions.jsonl"
        if decision_file.stat().st_size != room["decision_bytes"]:
            raise ValueError("冻结房动作审计字节数漂移")
        release = (json.loads((audit / "manifest.json").read_text(encoding="utf-8")).get("payload") or {}).get("policy_release") or {}
        if release.get("candidate_source_sha256") != frozen["parent_source_sha256"]:
            raise ValueError("冻结父代源码身份漂移")
        counts = Counter()
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
            parent_key = ranked[0]["action_key"]
            parent = legal.get(parent_key)
            if parent is None:
                raise ValueError("父代首选不在合法候选")
            shanten = (parent.get("facts") or {}).get("shanten_after")
            support = actionability._immediate_support(parent)
            if type(shanten) is not int or support is None:
                counts["top_facts_unknown"] += 1
                continue
            parent_features = extract._feature_row(
                request["observation"], parent, ranked[0], tile=parent_key.split(":", 1)[1])
            parent_state = _state_key(parent_features)
            eligible = 0
            for item in ranked[1:]:
                alternative_key = item["action_key"]
                if not alternative_key.startswith("discard:"):
                    continue
                alternative = legal.get(alternative_key)
                if alternative is None:
                    raise ValueError("备选弃牌不在合法候选")
                if (alternative.get("facts") or {}).get("shanten_after") != shanten:
                    continue
                alternative_support = actionability._immediate_support(alternative)
                if alternative_support is None or alternative_support < support:
                    continue
                features = extract._feature_row(
                    request["observation"], alternative, item,
                    tile=alternative_key.split(":", 1)[1])
                if _state_key(features) != parent_state:
                    raise ValueError("同向听备选意外改变冻结 G9 静态模型输入")
                eligible += 1
            if eligible:
                counts["same_shanten_support_not_lower_windows"] += 1
                counts["same_state_input_alternatives"] += eligible
        totals.update(counts)
        by_room[room["room_id"]] = dict(sorted(counts.items()))
    if totals["same_shanten_support_not_lower_windows"] != old["counts"]["same_shanten_support_not_lower_windows"]:
        raise ValueError("本次目标动作窗与既有结果盲面板不一致")
    result = {
        "schema": "g9-temporal-action-invariance/1", "outcome_blind": True,
        "source_parent_sha256": frozen["parent_source_sha256"],
        "source_frozen_rooms_sha256": hashlib.sha256(frozen_bytes).hexdigest(),
        "frozen_temporal_model_sha256": hashlib.sha256(model_bytes).hexdigest(),
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "counts": dict(sorted(totals.items())), "by_room": by_room,
        "conclusion": "同一窗口的前态差分由观察决定；同向听时静态输入亦完全相同，故冻结 G9 模型无法给这些弃牌备选排序",
        "boundary": "仅模型输入的结果盲结构核验；不评估动作价值或桌赛收益"}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in result.items() if key != "by_room"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
