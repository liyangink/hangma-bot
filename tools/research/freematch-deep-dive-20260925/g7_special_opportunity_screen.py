#!/usr/bin/env python3
"""冻结父代的三白或已爆头自然动作窗：结果盲核对合法动作与价值事实覆盖。"""

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
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = _PROJECT_ROOT
sys.path.insert(0, str(HERE))
import natural_shape_loss_screen as screen  # noqa: E402
from hangma_bot.hangma.special_rules import is_piao_discard  # noqa: E402
from hangma_bot.kernel.actions import Tile  # noqa: E402

GROUPS = {
    "pm": screen.ROOMS[:6],
    "recent": ("r18-sse-freematch-campaign-20260925b",),
    "historical": ("r18-auto-match-campaign-20260923",),
}


def _classify(request: dict, plan: dict):
    obs = request.get("observation") or {}
    if obs.get("phase") != "draw":
        return None
    hand = list(obs.get("my_hand") or [])
    seat = obs.get("seat")
    melds = obs.get("melds") or []
    if type(seat) is not int or not 0 <= seat < len(melds):
        raise ValueError("缺少本人副露座位事实")
    expected = 14 - 3 * len(melds[seat])
    if len(hand) == expected - 1 and obs.get("drawn_tile") is not None:
        hand.append(obs["drawn_tile"])
    if len(hand) != expected:
        raise ValueError("摸牌窗口暗手张数与副露不符")
    whites = hand.count("白")
    baotou = (obs.get("rule_state") or {}).get("baotou") is True
    if whites < 3 and not baotou:
        return None
    actions = {a.get("action_key"): a for a in
               (request.get("rules") or {}).get("legal_candidates") or []}
    discards = {key for key in actions if isinstance(key, str) and key.startswith("discard:")}
    first = (plan.get("candidates") or [{}])[0].get("action_key")
    white = actions.get("discard:白") or {}
    white_value = white.get("value_facts") or {}
    top_value = (actions.get(first) or {}).get("value_facts") or {}
    return {"whites": whites, "baotou": baotou, "discards": len(discards),
            "white_legal": "discard:白" in discards,
            "piao_legal": "discard:白" in discards and is_piao_discard(Tile("白"), baotou),
            "top": first, "top_type": first.split(":")[0] if isinstance(first, str) else "missing",
            "top_white": first == "discard:白",
            "white_coverage": white_value.get("coverage"),
            "white_routes": len(white_value.get("routes") or []),
            "white_baotou_after": (white.get("facts") or {}).get("baotou_after"),
            "top_coverage": top_value.get("coverage"),
            "top_routes": len(top_value.get("routes") or [])}


def main() -> int:
    counters = Counter()
    by_group = defaultdict(Counter)
    games = defaultdict(set)
    non_hu_games = defaultdict(set)
    seen = set()
    for group, rooms in GROUPS.items():
        for room in rooms:
            audit = _project_file(_PROJECT_ROOT, ROOT / "artifacts/sessions" / room / "audit/runs")
            for run in sorted(audit.glob("*")):
                manifest = run / "manifest.json"
                if not manifest.is_file():
                    continue
                release = ((json.loads(manifest.read_text(encoding="utf-8")).get("payload") or {})
                           .get("policy_release") or {})
                if release.get("candidate_source_sha256") != screen.PARENT_SHA256:
                    continue
                for context, request, plan in screen._iter_decisions(run):
                    key = (context.get("game_id"), context.get("round_no"),
                           context.get("trigger_seq"))
                    if key in seen:
                        counters["duplicate_audit"] += 1
                        continue
                    seen.add(key)
                    obs = request.get("observation") or {}
                    if obs.get("phase") == "draw":
                        by_group[group]["all_draw"] += 1
                    try:
                        row = _classify(request, plan)
                    except ValueError:
                        by_group[group]["invalid_draw_shape"] += 1
                        continue
                    if row is None:
                        continue
                    games[group].add(key[0])
                    target = by_group[group]
                    target["special_union"] += 1
                    if row["whites"] >= 3:
                        target["white3plus"] += 1
                    if row["whites"] == 4:
                        target["white4"] += 1
                    if row["baotou"]:
                        target["baotou"] += 1
                    if row["whites"] >= 3 and row["baotou"]:
                        target["white3_baotou"] += 1
                    if row["discards"] >= 2:
                        target["multiple_legal_discards"] += 1
                    if row["white_legal"]:
                        target["white_legal"] += 1
                    if row["piao_legal"]:
                        target["piao_legal"] += 1
                    if row["top_white"]:
                        target["top_white"] += 1
                    target["top_type_" + row["top_type"]] += 1
                    if row["top_type"] != "hu":
                        target["not_immediate_hu"] += 1
                        non_hu_games[group].add(key[0])
                        if row["whites"] >= 3:
                            target["not_hu_white3plus"] += 1
                        if row["baotou"]:
                            target["not_hu_baotou"] += 1
                        if row["discards"] >= 2 and row["white_legal"]:
                            target["not_hu_white_choice"] += 1
                    if row["white_coverage"] == "complete":
                        target["white_value_complete"] += 1
                    if row["white_routes"]:
                        target["white_has_route"] += 1
                    if row["top_routes"]:
                        target["top_has_route"] += 1
                    if row["white_baotou_after"] is True:
                        target["white_keeps_baotou"] += 1
    output = {"schema": "g7-special-opportunity-screen/1",
              "parent_source_sha256": screen.PARENT_SHA256,
              "groups": {group: {"counts": dict(by_group[group]),
                                   "independent_official_games": len(games[group]),
                                   "not_hu_official_games": len(non_hu_games[group])}
                         for group in GROUPS},
              "counters": dict(counters),
              "note": "动态官方审计结果盲频数，不是冻结收益样本；需先锁选样再评分"}
    out = _project_file(_PROJECT_ROOT, HERE / "evidence/g7-special-opportunity-screen-20260927/result.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(output, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                   encoding="utf-8")
    print(json.dumps(output, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
