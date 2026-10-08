#!/usr/bin/env python3
"""只读筛查：线上冻结策略是否弃数牌而保留路线牌效更窄的孤张字牌。

仅比较同一可见动作窗口内的规则事实，绝不以赛后牌墙或结果倒推正确动作。
输出窗口数量而不是把同窗多个字牌备选当独立样本；不打印 Token 或报文。
"""

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

import collections
import json
from pathlib import Path


ROOT = _PROJECT_ROOT
ROOMS = (
    "r18-v2-sse-freematch-20260925-pm",
    "r18-v2-sse-freematch-20260925-pm2",
    "r18-v2-sse-freematch-20260925-pm3",
    "r18-v2-sse-freematch-20260925-pm4",
    "r18-v2-sse-free-validated-20260925",
    "r18-v2-sse-auto-match-20260925",
    "r18-sse-freematch-campaign-20260925b",
    "r18-auto-match-campaign-20260923",
)
PARENT_SHA256 = "a2d9b8af93beabdba75716fccae56b0668a6fd84f0bdce558d2ff3e569443618"
PARTICIPANT = "u_13495c3d79c8"
SINGLE_HONORS = frozenset("东南西北中发")


def _useful_capacity(facts: dict, name: str) -> int | None:
    """对已生产分牌型有效牌求公开未见容量；None 保持未知语义。"""
    tiles = facts.get(name)
    if not isinstance(tiles, list):
        return None
    total = 0
    for tile in tiles:
        amount = tile.get("remaining_estimate")
        if type(amount) is not int or not 0 <= amount <= 4:
            return None
        total += amount
    return total


def _compare(request: dict, plan: dict):
    """返回同窗路线帕累托证据；只比较实际首选与合法弃字牌。"""
    observation = request.get("observation") or {}
    if observation.get("phase") != "draw":
        return None
    candidates = plan.get("candidates") or []
    if not candidates:
        return None
    chosen = candidates[0].get("action_key")
    if not isinstance(chosen, str) or not chosen.startswith("discard:") or chosen[-1] not in "wbt":
        return None
    actions = {
        item.get("action_key"): item
        for item in (request.get("rules") or {}).get("legal_candidates") or []
    }
    selected = actions.get(chosen)
    if selected is None or not isinstance(selected.get("facts"), dict):
        return None
    hand = list(observation.get("my_hand") or [])
    if len(hand) == 13 and observation.get("drawn_tile") is not None:
        hand.append(observation["drawn_tile"])
    scores = {item.get("action_key"): item.get("total_score") for item in candidates}
    sf = selected["facts"]
    selected_values = tuple(_useful_capacity(sf, name) for name in (
        "useful_tiles", "standard_useful_tiles", "seven_pairs_useful_tiles"
    ))
    if any(value is None for value in selected_values):
        return None
    alternatives = []
    for key, action in actions.items():
        if not isinstance(key, str) or not key.startswith("discard:"):
            continue
        tile = key[8:]
        if tile not in SINGLE_HONORS or hand.count(tile) != 1:
            continue
        facts = action.get("facts")
        if not isinstance(facts, dict):
            continue
        alt_values = tuple(_useful_capacity(facts, name) for name in (
            "useful_tiles", "standard_useful_tiles", "seven_pairs_useful_tiles"
        ))
        if any(value is None for value in alt_values):
            continue
        shanten_keys = (
            "shanten_after", "standard_shanten_after", "seven_pairs_shanten_after"
        )
        if any(type(facts.get(name)) is not int or type(sf.get(name)) is not int
               for name in shanten_keys):
            continue
        if any(facts[name] > sf[name] for name in shanten_keys):
            continue
        if alt_values[1] <= selected_values[1]:
            continue
        if alt_values[0] < selected_values[0] or alt_values[2] < selected_values[2]:
            continue
        score_gap = scores.get(chosen)
        alternative_score = scores.get(key)
        if not isinstance(score_gap, (int, float)) or not isinstance(alternative_score, (int, float)):
            continue
        alternatives.append((key, alt_values[1] - selected_values[1], score_gap - alternative_score))
    if not alternatives:
        return ("suited", len(hand), hand.count("白"), None)
    return ("pareto", len(hand), hand.count("白"), alternatives)


def _iter_decisions(run_dir: Path):
    """按决策标识配对输入与计划，仅投影所需事实。"""
    path = run_dir / "participants" / PARTICIPANT / "decisions.jsonl"
    if not path.is_file():
        return
    pending = {}
    with path.open(encoding="utf-8", errors="replace") as stream:
        for line in stream:
            if '"decision_input"' not in line and '"decision_planned"' not in line:
                continue
            try:
                record = json.loads(line)
            except ValueError:
                continue
            context = record.get("context") or {}
            ident = context.get("decision_id")
            if record.get("kind") == "decision_input":
                pending[ident] = (record.get("payload") or {}).get("request") or {}
            elif record.get("kind") == "decision_planned" and ident in pending:
                request = pending.pop(ident)
                plan = (record.get("payload") or {}).get("returned_plan") or {}
                yield context, request, plan


def main() -> int:
    """按房与白板数输出可复核的观察性计数。"""
    counts = collections.Counter()
    by_room = collections.Counter()
    examples = []
    seen_windows = set()
    for room in ROOMS:
        audit = _project_file(_PROJECT_ROOT, ROOT / "artifacts" / "sessions" / room / "audit" / "runs")
        for run_dir in sorted(audit.glob("*")):
            manifest = run_dir / "manifest.json"
            if not manifest.is_file():
                continue
            try:
                meta = json.loads(manifest.read_text()).get("payload") or {}
            except ValueError:
                continue
            if (meta.get("policy_release") or {}).get("candidate_source_sha256") != PARENT_SHA256:
                continue
            for context, request, plan in _iter_decisions(run_dir):
                window_key = (
                    context.get("game_id"), context.get("round_no"),
                    context.get("trigger_seq"),
                )
                if window_key in seen_windows:
                    counts["duplicate_audit_windows"] += 1
                    continue
                seen_windows.add(window_key)
                result = _compare(request, plan)
                if result is None:
                    continue
                counts["suited_draw_windows"] += 1
                if result[0] != "pareto":
                    continue
                counts["pareto_windows"] += 1
                counts[f"white_{result[2]}"] += 1
                by_room[room] += 1
                alternatives = result[3]
                best_gap = min(item[2] for item in alternatives)
                counts["same_parent_score" if best_gap == 0 else "different_parent_score"] += 1
                if len(examples) < 8:
                    examples.append((room, context.get("game_id"), context.get("round_no"),
                                     context.get("trigger_seq"),
                                     plan["candidates"][0]["action_key"], alternatives))
    print("窗口计数:", dict(counts))
    print("逐房:", dict(by_room))
    print("前 8 例（无隐藏牌或赛后结果）:")
    for item in examples:
        print(item)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
