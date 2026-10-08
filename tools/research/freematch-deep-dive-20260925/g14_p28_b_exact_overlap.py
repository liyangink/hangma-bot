#!/usr/bin/env python3
"""G14：P28-A 不同动作的 114 窗，继续原封重放 P28-B 叶程序。"""

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
A = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g14-p28-exact-overlap-20260927')
ROUTE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15')
P28 = (_project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r17-generation1-vs-r18v2-01-20260925/manifest.json'))
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g14-p28-b-exact-overlap-20260927')
P28_B_SOURCE_SHA = "fb9764faa2a01ded3f8cea94eeee27d59929f014f1dcc0ffbd56380e5b1384a2"
P28_B_IDENTITY = "73c2833da12f2844f69559d4ad6202c44fc4a1adc1b60e0b8b140c82590b4c37"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _policy(source: str) -> tuple:
    """按 P28 冻结配置装配 B，记录后继归约完成性。"""

    rules = HangmaRules(RuleConfig(ruleset_version="hangma-mvp-v10-public-counts",
                                   base_score=1, you_cai_bi_kao=False))
    baseline = bootstrap.build_research_policy("action_value:r18_integrated_positive_v2")
    details = {}

    def orderer(reduction, baseline_keys):
        details["called"] = details.get("called", 0) + 1
        details["complete"] = reduction.complete
        details["reason"] = str(reduction.reason)[:200]
        return order_discard_keys_by_fronts(reduction, baseline_keys)

    policy = PublicSuccessorSearchPolicy(
        rules.analyze_public_self_draw_successors,
        LeafProgramExecutor(source, name="g14-p28-b-replay"),
        candidate_identity=P28_B_IDENTITY, baseline=baseline, orderer=orderer)
    return baseline, policy, details


async def _replay(request, baseline, policy, details) -> dict:
    """额外离线预算只排除截止干扰，不作为线上动作尾延迟证明。"""

    now = time.monotonic()
    budget = DecisionBudget(now + 3600.0, now + 3601.0, now + 3602.0)
    details.clear()
    parent = await baseline.choose(request, budget)
    candidate = await policy.choose(request, budget)
    return {"parent": parent.candidates[0].action_key,
            "p28_b": candidate.candidates[0].action_key,
            "reduction_called": details.get("called", 0),
            "reduction_complete": details.get("complete"),
            "reduction_reason": details.get("reason")}


def main() -> None:
    """只在 A 不同动作的 114 窗标记 B 精确同动作，全部来源带摘要。"""

    if OUT.exists():
        raise SystemExit("G14/P28-B 去重结果已存在，拒绝覆盖")
    frozen = json.loads(FROZEN.read_text(encoding="utf-8"))
    a = json.loads((_project_file(_PROJECT_ROOT, A / "result.json")).read_text(encoding="utf-8"))
    p28 = json.loads(P28.read_text(encoding="utf-8"))
    if (a.get("outcome_blind") is not True or
            a["rows_sha256"] != _sha(_project_file(_PROJECT_ROOT, A / "rows.jsonl.gz")) or
            p28["candidates"]["B"]["sha256"] != P28_B_SOURCE_SHA or
            p28["candidates"]["B"]["identity"] != P28_B_IDENTITY):
        raise ValueError("A 去重或 P28-B 身份漂移")
    source_path = Path(p28["candidates"]["B"]["path"])
    if _sha(source_path) != P28_B_SOURCE_SHA:
        raise ValueError("P28-B 原始叶程序源码漂移")
    targets = {}
    with gzip.open(_project_file(_PROJECT_ROOT, A / "rows.jsonl.gz"), "rt", encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            if row["status"] == "p28_same_as_g14":
                continue
            key = (row["game_id"], row["round_no"], row["trigger_seq"])
            targets[key] = row
    if len(targets) != 114:
        raise ValueError("A 不同动作 114 窗入口漂移")
    baseline, policy, details = _policy(source_path.read_text(encoding="utf-8"))
    rows = []
    seen = set()
    counts = Counter()
    for room in frozen["rooms"]:
        audit = atlas.source.ROOT / room["audit_dir"]
        decisions = audit / "participants" / atlas.source.ACTOR / "decisions.jsonl"
        if decisions.stat().st_size != room["decision_bytes"]:
            raise ValueError("冻结父代审计大小漂移")
        release = ((json.loads((audit / "manifest.json").read_text(encoding="utf-8"))
                    .get("payload") or {}).get("policy_release") or {})
        if release.get("candidate_source_sha256") != frozen["parent_source_sha256"]:
            raise ValueError("冻结 R18 v2 父代源码漂移")
        accepted = atlas.source._accepted(decisions)
        for context, raw, plan in atlas.source.screen._iter_decisions(audit):
            key = (context["game_id"], context["round_no"], context["trigger_seq"])
            target = targets.get(key)
            if target is None:
                continue
            if key in seen or target["room_id"] != room["room_id"]:
                raise ValueError("目标窗口重复或房间错配")
            seen.add(key)
            ranked = sorted(plan.get("candidates") or [],
                            key=lambda item: item.get("rank", 10**9))
            legal = {item["action_key"] for item in
                     (raw.get("rules") or {}).get("legal_candidates") or []}
            if (not ranked or ranked[0].get("action_key") != target["parent_action"] or
                    accepted.get(context["decision_id"]) != target["parent_action"] or
                    target["g14_alternative_action"] not in legal):
                raise ValueError("父代接受或 G14 备选合法性漂移")
            observed = asyncio.run(_replay(decision_request_from_json(raw),
                                           baseline, policy, details))
            if observed["parent"] != target["parent_action"]:
                raise ValueError("R18 v2 重放与官方父代行动不一致")
            if observed["reduction_called"] != 1:
                counts["reduction_not_called_once"] += 1
            elif observed["reduction_complete"] is not True:
                counts["reduction_incomplete"] += 1
            status = ("p28_b_same_as_g14" if observed["p28_b"] == target["g14_alternative_action"]
                      else "p28_b_keeps_parent" if observed["p28_b"] == target["parent_action"]
                      else "p28_b_other")
            counts[status] += 1
            rows.append({"room_id": room["room_id"], "game_id": key[0],
                         "round_no": key[1], "trigger_seq": key[2],
                         "parent_action": target["parent_action"],
                         "g14_alternative_action": target["g14_alternative_action"],
                         "p28_a_action": target["p28_a_action"],
                         "p28_b_action": observed["p28_b"],
                         "status": status,
                         "reduction_called": observed["reduction_called"],
                         "reduction_complete": observed["reduction_complete"],
                         "reduction_reason": observed["reduction_reason"]})
    if seen != set(targets):
        raise ValueError("114 窗未全量重放")
    OUT.mkdir(parents=True)
    rows_path = _project_file(_PROJECT_ROOT, OUT / "rows.jsonl.gz")
    with rows_path.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as stream:
            for row in rows:
                stream.write((json.dumps(row, ensure_ascii=False, sort_keys=True,
                                         separators=(",", ":")) + "\n").encode("utf-8"))
    surviving = [row for row in rows if row["status"] != "p28_b_same_as_g14"]
    summary = {"schema": "g14-p28-b-exact-overlap/1", "outcome_blind": True,
               "source_frozen_rooms_sha256": _sha(FROZEN),
               "source_a_result_sha256": _sha(_project_file(_PROJECT_ROOT, A / "result.json")),
               "source_a_rows_sha256": _sha(_project_file(_PROJECT_ROOT, A / "rows.jsonl.gz")),
               "p28_manifest_sha256": _sha(P28),
               "p28_b_source_sha256": P28_B_SOURCE_SHA,
               "p28_b_identity": P28_B_IDENTITY,
               "script_sha256": _sha(Path(__file__)), "rows_sha256": _sha(rows_path),
               "tested_windows": len(rows), "tested_complete_tables": len({row["game_id"] for row in rows}),
               "counts": dict(sorted(counts.items())),
               "surviving_windows": len(surviving),
               "surviving_complete_tables": len({row["game_id"] for row in surviving}),
               "surviving_rooms": len({row["room_id"] for row in surviving}),
               "boundary": "仅扣 P28-A/B 精确同动作；不同动作不证明机制新颖。离线预算不构成线上时限或整桌收益证据。"}
    (_project_file(_PROJECT_ROOT, OUT / "result.json")).write_text(
        json.dumps(summary, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
