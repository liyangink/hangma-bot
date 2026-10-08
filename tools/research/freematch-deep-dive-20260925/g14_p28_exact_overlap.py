#!/usr/bin/env python3
"""G14：在冻结父代窗口原封重放 P28-A，并统计精确弃牌动作重合。"""

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

import asyncio
from collections import Counter
import gzip
import hashlib
import json
from pathlib import Path
import time

import g11_cross_family_action_atlas as atlas
from hangma_bot import bootstrap
from hangma_bot.application.audit_codec import decision_request_from_json
from hangma_bot.hangma.engine import HangmaRules
from hangma_bot.kernel.config import RuleConfig
from hangma_bot.policy.interface import DecisionBudget
from hangma_bot.policy.public_successor_leaf_executor import LeafProgramExecutor
from hangma_bot.policy.public_successor_policy import PublicSuccessorSearchPolicy
from hangma_bot.policy.public_successor_search import order_discard_keys_by_fronts


HERE = Path(__file__).resolve().parent
FROZEN = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g8-two-white-next-draw-20260927/frozen_rooms.json')
SUPPORT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g14-second-public-support-20260927')
ROUTE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15')
P28 = (_project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r17-generation1-vs-r18v2-01-20260925/manifest.json'))
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g14-p28-exact-overlap-20260927')
P28_A_SOURCE_SHA = "b0ae33525f46c66c7b462e4db9825df13d8608d5748b803e759b49c2a16eb76d"
P28_A_IDENTITY = "a7e6f529e42b6ac81985877925bca878d01f592a2328459968feb97ef19ba1a8"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _policy(source: str, identity: str) -> tuple:
    """沿用 P28 的生产后继提供者、叶执行器、R18 v2 基线和归约器。"""

    rules = HangmaRules(RuleConfig(ruleset_version="hangma-mvp-v10-public-counts",
                                   base_score=1, you_cai_bi_kao=False))
    baseline = bootstrap.build_research_policy("action_value:r18_integrated_positive_v2")
    details = {}

    def orderer(reduction, baseline_keys):
        """只观察原封归约结果，出口顺序交回同一生产函数。"""

        details["called"] = details.get("called", 0) + 1
        details["complete"] = reduction.complete
        details["reason"] = str(reduction.reason)[:200]
        return order_discard_keys_by_fronts(reduction, baseline_keys)

    policy = PublicSuccessorSearchPolicy(
        rules.analyze_public_self_draw_successors,
        LeafProgramExecutor(source, name="g14-p28-a-replay"),
        candidate_identity=identity, baseline=baseline, orderer=orderer)
    return baseline, policy, details


async def _replay(request, baseline, policy, details) -> dict:
    """同一请求分别取父代与 P28-A 首选；额外预算只消除离线截止干扰。"""

    now = time.monotonic()
    budget = DecisionBudget(now + 3600.0, now + 3601.0, now + 3602.0)
    details.clear()
    parent = await baseline.choose(request, budget)
    candidate = await policy.choose(request, budget)
    return {"parent": parent.candidates[0].action_key,
            "p28_a": candidate.candidates[0].action_key,
            "reduction_called": details.get("called", 0),
            "reduction_complete": details.get("complete"),
            "reduction_reason": details.get("reason")}


def main() -> None:
    """精确动作重合只按冻结 371 窗报告，不读终局积分与未来墙。"""

    if OUT.exists():
        raise SystemExit("G14/P28 精确重合产物已存在，拒绝覆盖")
    frozen = json.loads(FROZEN.read_text(encoding="utf-8"))
    support = json.loads((_project_file(_PROJECT_ROOT, SUPPORT / "result.json")).read_text(encoding="utf-8"))
    p28 = json.loads(P28.read_text(encoding="utf-8"))
    if (support.get("outcome_blind") is not True or
            support["rows_sha256"] != _sha(_project_file(_PROJECT_ROOT, SUPPORT / "rows.jsonl.gz")) or
            p28["candidates"]["A"]["sha256"] != P28_A_SOURCE_SHA or
            p28["candidates"]["A"]["identity"] != P28_A_IDENTITY):
        raise ValueError("G14 或 P28 冻结输入身份漂移")
    source_path = Path(p28["candidates"]["A"]["path"])
    if _sha(source_path) != P28_A_SOURCE_SHA:
        raise ValueError("P28-A 原始叶程序源码漂移")
    targets = {}
    with gzip.open(_project_file(_PROJECT_ROOT, SUPPORT / "rows.jsonl.gz"), "rt", encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            if (row["weighted"]["standard_worse_capacity"] != 0 or
                    row["public_width_gain"] <= 0):
                continue
            key = (row["game_id"], row["round_no"], row["trigger_seq"])
            targets[key] = row
    if len(targets) != 371:
        raise ValueError("371 窗入口漂移")
    baseline, policy, details = _policy(source_path.read_text(encoding="utf-8"),
                                        P28_A_IDENTITY)
    rows = []
    counts = Counter()
    seen = set()
    for room in frozen["rooms"]:
        audit = atlas.source.ROOT / room["audit_dir"]
        decisions = audit / "participants" / atlas.source.ACTOR / "decisions.jsonl"
        if decisions.stat().st_size != room["decision_bytes"]:
            raise ValueError("冻结父代审计大小漂移")
        release = ((json.loads((audit / "manifest.json").read_text(encoding="utf-8"))
                    .get("payload") or {}).get("policy_release") or {})
        if release.get("candidate_source_sha256") != frozen["parent_source_sha256"]:
            raise ValueError("冻结父代源码身份漂移")
        accepted = atlas.source._accepted(decisions)
        for context, raw, plan in atlas.source.screen._iter_decisions(audit):
            key = (context["game_id"], context["round_no"], context["trigger_seq"])
            target = targets.get(key)
            if target is None:
                continue
            if key in seen or target["room_id"] != room["room_id"]:
                raise ValueError("目标窗口重复或房间不一致")
            seen.add(key)
            ranked = sorted(plan.get("candidates") or [],
                            key=lambda item: item.get("rank", 10**9))
            legal = {item["action_key"] for item in
                     (raw.get("rules") or {}).get("legal_candidates") or []}
            if (not ranked or ranked[0].get("action_key") != target["parent_action"] or
                    accepted.get(context["decision_id"]) != target["parent_action"] or
                    target["alternative_action"] not in legal):
                raise ValueError("父代已接受或备选合法性漂移")
            request = decision_request_from_json(raw)
            started = time.perf_counter()
            observed = asyncio.run(_replay(request, baseline, policy, details))
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            if observed["parent"] != target["parent_action"]:
                raise ValueError("R18 v2 重放首选与冻结父代审计不符")
            if observed["reduction_called"] != 1:
                counts["reduction_not_called_once"] += 1
            elif observed["reduction_complete"] is not True:
                counts["reduction_incomplete"] += 1
            status = ("p28_same_as_g14" if observed["p28_a"] == target["alternative_action"]
                      else "p28_keeps_parent" if observed["p28_a"] == target["parent_action"]
                      else "p28_other")
            counts[status] += 1
            rows.append({"room_id": room["room_id"], "game_id": key[0],
                         "round_no": key[1], "trigger_seq": key[2],
                         "parent_action": target["parent_action"],
                         "g14_alternative_action": target["alternative_action"],
                         "p28_a_action": observed["p28_a"], "status": status,
                         "reduction_called": observed["reduction_called"],
                         "reduction_complete": observed["reduction_complete"],
                         "reduction_reason": observed["reduction_reason"],
                         "offline_replay_ms": round(elapsed_ms, 3)})
    if seen != set(targets):
        raise ValueError("371 窗未全量重放")
    OUT.mkdir(parents=True)
    rows_path = _project_file(_PROJECT_ROOT, OUT / "rows.jsonl.gz")
    with rows_path.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as stream:
            for row in rows:
                stream.write((json.dumps(row, ensure_ascii=False, sort_keys=True,
                                         separators=(",", ":")) + "\n").encode("utf-8"))
    summary = {"schema": "g14-p28-exact-overlap/1", "outcome_blind": True,
               "source_frozen_rooms_sha256": _sha(FROZEN),
               "source_support_result_sha256": _sha(_project_file(_PROJECT_ROOT, SUPPORT / "result.json")),
               "source_support_rows_sha256": _sha(_project_file(_PROJECT_ROOT, SUPPORT / "rows.jsonl.gz")),
               "p28_manifest_sha256": _sha(P28),
               "p28_a_source_sha256": P28_A_SOURCE_SHA,
               "p28_a_identity": P28_A_IDENTITY,
               "script_sha256": _sha(Path(__file__)), "rows_sha256": _sha(rows_path),
               "windows": len(rows), "complete_tables": len({row["game_id"] for row in rows}),
               "rooms": len({row["room_id"] for row in rows}),
               "counts": dict(sorted(counts.items())),
               "same_action_tables": len({row["game_id"] for row in rows
                                          if row["status"] == "p28_same_as_g14"}),
               "different_action_tables": len({row["game_id"] for row in rows
                                               if row["status"] != "p28_same_as_g14"}),
               "boundary": "只核 P28-A 精确弃牌；不同动作不证明数学机制新颖或整桌收益。离线扩大增强预算，不构成线上时限证据。"}
    (_project_file(_PROJECT_ROOT, OUT / "result.json")).write_text(
        json.dumps(summary, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
