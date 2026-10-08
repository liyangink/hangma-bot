#!/usr/bin/env python3
"""冻结 R18 v2 生产观察上的弃牌风险项零权消融；只统计行为。"""

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

import g1_cross_turn_route_exposure as g1
from hangma_bot.application.audit_codec import decision_request_from_json
from hangma_bot.policy.action_value_policy import build_scoring_view
from hangma_bot.policy.action_value_seeds import ActionValueScorer
from hangma_bot.policy.r18_integrated_positive_v2 import R18_INTEGRATED_POSITIVE_V2_SOURCE


ROOT = _PROJECT_ROOT
HERE = Path(__file__).resolve().parent
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g1-discard-risk-ablation-01')
OLD = "total -= round(6.0 * risk_units, 1)"
NEW = "total -= round(0.0 * risk_units, 1)"


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def ranked_top(entries: object) -> object:
    return min(entries, key=lambda item: (-item.score, item.action_key))


def main() -> None:
    """只读生产输入/父代计划；在同一可见视图上比较两个固定源码。"""
    if OUT.exists():
        raise FileExistsError("证据目录已存在，拒绝覆盖")
    if R18_INTEGRATED_POSITIVE_V2_SOURCE.count(OLD) != 1:
        raise ValueError("冻结父代风险扣分语句非唯一")
    candidate_source = R18_INTEGRATED_POSITIVE_V2_SOURCE.replace(OLD, NEW, 1)
    if len(candidate_source) != len(R18_INTEGRATED_POSITIVE_V2_SOURCE):
        raise ValueError("候选不是同长度单行替换")
    parent_scorer = ActionValueScorer("g1-risk0-parent", R18_INTEGRATED_POSITIVE_V2_SOURCE)
    candidate_scorer = ActionValueScorer("g1-risk0-candidate", candidate_source)
    ledger = json.loads(g1.prior.LEDGER.read_text(encoding="utf-8"))
    by_id = {room.get("room_id"): _project_file(_PROJECT_ROOT, ROOT / room["audit_dir"])
             for room in ledger.get("rooms") or []
             if room.get("room_id") in g1.ROOM_IDS}
    if set(by_id) != set(g1.ROOM_IDS):
        raise ValueError("冻结房号缺失于账本")
    reports = []
    changed = []
    total = Counter()
    for room_id in g1.ROOM_IDS:
        audit = by_id[room_id]
        manifest = json.loads((audit / "manifest.json").read_text(encoding="utf-8"))
        payload = manifest.get("payload") or {}
        if payload.get("policy_version") != g1.prior.VERSION or (
            (payload.get("policy_release") or {}).get("release_package_id")
            != g1.prior.RELEASE_ID
        ):
            raise ValueError("父代发布包身份不符：" + room_id)
        decisions = audit / "participants" / g1.prior.ME / "decisions.jsonl"
        inputs = {}
        plans = {}
        counts = Counter()
        for line in decisions.open(encoding="utf-8"):
            record = json.loads(line)
            data = record.get("payload") or {}
            if record.get("kind") == "decision_input":
                req = data.get("request") or {}
                did = req.get("decision_id")
                if did in inputs:
                    counts["duplicate_input"] += 1
                else:
                    inputs[did] = req
            elif record.get("kind") == "decision_planned":
                plan = data.get("returned_plan") or {}
                did = plan.get("decision_id")
                if did in plans:
                    counts["duplicate_plan"] += 1
                else:
                    plans[did] = plan
        seen = set()
        for did, encoded in inputs.items():
            observation = encoded.get("observation") or {}
            if observation.get("phase") != "draw":
                continue
            window = encoded.get("window_key") or {}
            key = tuple(window.get(field) for field in
                        ("game_id", "round_no", "trigger_seq", "phase", "seat"))
            if None in key:
                raise ValueError("不完整 WindowKey")
            if key in seen:
                counts["revised_window"] += 1
                continue
            seen.add(key)
            counts["draw_windows"] += 1
            plan = plans.get(did)
            if not plan or not plan.get("candidates"):
                counts["missing_plan"] += 1
                continue
            planned = min(plan["candidates"], key=lambda item: item.get("rank", 10**9))
            if not str(planned.get("action_key")).startswith("discard:"):
                continue
            counts["planned_discard"] += 1
            request = decision_request_from_json(encoded)
            view = build_scoring_view(request)
            parent_result = parent_scorer.score(view)
            candidate_result = candidate_scorer.score(view)
            if (parent_result.status != "SCORED" or candidate_result.status != "SCORED"
                    or not parent_result.entries or not candidate_result.entries):
                counts["scoring_failure"] += 1
                continue
            parent = ranked_top(parent_result.entries)
            if parent.action_key != planned.get("action_key"):
                counts["parent_positive_control_mismatch"] += 1
                continue
            counts["parent_positive_control_match"] += 1
            candidate = ranked_top(candidate_result.entries)
            if candidate.action_key == parent.action_key:
                continue
            counts["changed"] += 1
            candidate_legal = {item.action_key: item for item in request.rules.legal_candidates}
            if candidate.action_key not in candidate_legal:
                counts["changed_illegal"] += 1
                continue
            counts["changed_to:" + candidate.action_key.split(":", 1)[0]] += 1
            parent_facts = candidate_legal[parent.action_key].facts
            candidate_facts = candidate_legal[candidate.action_key].facts
            delta = None
            if (parent_facts.shanten_after is not None
                    and candidate_facts.shanten_after is not None):
                delta = candidate_facts.shanten_after - parent_facts.shanten_after
            counts["shanten_delta:" + str(delta)] += 1
            changed.append({
                "room_id": room_id, "game_id": key[0], "round_no": key[1],
                "trigger_seq": key[2], "seat": key[4],
                "parent_action": parent.action_key,
                "candidate_action": candidate.action_key,
                "parent_score_gap": parent.score - next(
                    item.score for item in parent_result.entries
                    if item.action_key == candidate.action_key
                ),
                "parent_shanten": parent_facts.shanten_after,
                "candidate_shanten": candidate_facts.shanten_after,
                "parent_risk_units": parent.trace.get("risk_units"),
                "candidate_parent_risk_units": next(
                    item.trace.get("risk_units") for item in parent_result.entries
                    if item.action_key == candidate.action_key
                ),
            })
        total.update(counts)
        reports.append({"room_id": room_id, "manifest_sha256": g1.digest(audit / "manifest.json"),
                        "decisions_sha256": g1.digest(decisions),
                        "counts": dict(sorted(counts.items()))})
    result = {
        "schema": "g1-discard-risk-ablation/1",
        "script_sha256": digest(Path(__file__).read_bytes()),
        "parent_source_sha256": digest(R18_INTEGRATED_POSITIVE_V2_SOURCE.encode("utf-8")),
        "candidate_source_sha256": digest(candidate_source.encode("utf-8")),
        "exact_replacement": {"old": OLD, "new": NEW},
        "room_ids": list(g1.ROOM_IDS),
        "rooms": reports,
        "total_counts": dict(sorted(total.items())),
        "changed_games": len({(row["room_id"], row["game_id"]) for row in changed}),
        "changed_episodes": len({(row["room_id"], row["game_id"], row["round_no"])
                                 for row in changed}),
        "outcome_labels_opened": False,
    }
    OUT.mkdir(parents=True)
    (_project_file(_PROJECT_ROOT, OUT / "result.json")).write_text(
        json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    (_project_file(_PROJECT_ROOT, OUT / "windows.json")).write_text(
        json.dumps({"schema": "g1-discard-risk-ablation-windows/1", "windows": changed},
                   ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"total_counts": result["total_counts"],
                      "changed_games": result["changed_games"],
                      "changed_episodes": result["changed_episodes"]},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
