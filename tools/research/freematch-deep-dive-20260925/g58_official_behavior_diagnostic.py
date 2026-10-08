#!/usr/bin/env python3
"""G58 两份人工查过调用范围的原程序在冻结官方父代轨迹上的结果盲诊断。"""

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

import ast
import builtins
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import time

import g11_cross_family_action_atlas as atlas
import g11_longitudinal_route_audit as longitudinal
import g56_route_switch_reach as g56
import g58_answer_screen as screen
import g58_executable_search_wave as wave


HERE = Path(__file__).resolve().parent
OUT = wave.OUT / "official_behavior_diagnostic.json"
CARDS = ("a_contextual_width", "d_tempo_dealer")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _program(card: str):
    """仅载入人工确认过的两个纯函数；A 非严格 JSON 只作次级诊断。"""

    path = wave.OUT / f"{card}.answer.txt"
    raw = path.read_text(encoding="utf-8").lstrip()
    payload, _end = json.JSONDecoder().raw_decode(raw)
    program = payload["program"]
    static = screen.program_screen(program)
    if not static["syntax_ok"] or static["flags"]:
        raise ValueError("待诊断程序未通过 AST 静态门：" + card)
    tree = ast.parse(program, mode="exec")
    allowed = {name: getattr(builtins, name) for name in screen.CALLS}
    namespace: dict = {}
    exec(compile(tree, f"<g58-{card}-read-only-diagnostic>", "exec"),
         {"__builtins__": allowed}, namespace)
    return namespace["choose"]


def _support(facts: dict, name: str) -> list[dict] | None:
    """仅把规则事实投影到 G58 冻结接口，不估计真实牌墙概率。"""

    entries = facts.get(name)
    if entries is None:
        return None
    if not isinstance(entries, list):
        raise ValueError("生产支持表编码不合法")
    return [{"tile": item.get("code"), "remaining": item.get("remaining_estimate")}
            for item in entries]


def _context(observation: dict, full_hand: Counter) -> dict | None:
    seat = observation.get("seat")
    melds = observation.get("melds")
    scores = observation.get("scores")
    dealer = observation.get("dealer_seat")
    if (type(seat) is not int or not 0 <= seat < 4 or type(dealer) is not int
            or not isinstance(melds, list) or len(melds) != 4
            or not all(isinstance(item, list) for item in melds)
            or not isinstance(scores, list) or len(scores) != 4
            or any(type(value) not in (int, float) for value in scores)):
        return None
    return {"white_count": full_hand["白"], "own_melds": len(melds[seat]),
            "wall_remaining": observation.get("remaining_tile_count"),
            "dealer": dealer == seat,
            "table_rank": 1 + sum(value > scores[seat] for value in scores),
            "opponent_melds": [len(melds[(seat + offset) % 4]) for offset in (1, 2, 3)],
            "drawn_tile": observation.get("drawn_tile")}


def main() -> None:
    """生产父代动作事实已核接受；输出只报告可见行为，不读结算标签。"""

    if OUT.exists():
        raise SystemExit("G58 官方行为诊断结果已存在，拒绝覆盖")
    static_path = wave.OUT / "static_screen.json"
    static = json.loads(static_path.read_text(encoding="utf-8"))
    if {row["card"] for row in static["rows"]} != set(wave.CARDS):
        raise ValueError("四卡静态初筛不完整")
    programs = {card: _program(card) for card in CARDS}
    frozen = json.loads(atlas.FROZEN.read_text(encoding="utf-8"))
    complete_ids = atlas._complete_ids()
    g10, g11, g49 = g56._old_actions()
    counts = Counter()
    per_card: dict[str, Counter] = defaultdict(Counter)
    scopes = {card: {"tables": set(), "rooms": set()} for card in CARDS}
    changes = {card: [] for card in CARDS}
    timing = {card: [] for card in CARDS}
    for room in frozen["rooms"]:
        audit = atlas.source.ROOT / room["audit_dir"]
        decisions = audit / "participants" / atlas.source.ACTOR / "decisions.jsonl"
        if decisions.stat().st_size != room["decision_bytes"]:
            raise ValueError("冻结决策文件字节数漂移")
        release = ((json.loads((audit / "manifest.json").read_text(encoding="utf-8"))
                    .get("payload") or {}).get("policy_release") or {})
        if release.get("candidate_source_sha256") != frozen["parent_source_sha256"]:
            raise ValueError("冻结父代源码摘要漂移")
        accepted = atlas.source._accepted(decisions)
        for identity, raw, plan in atlas.source.screen._iter_decisions(audit):
            if identity.get("game_id") not in complete_ids:
                continue
            if (raw.get("window_key") or {}).get("phase") != "draw":
                continue
            ranked = sorted(plan.get("candidates") or [],
                            key=lambda item: item.get("rank", 10**9))
            if not ranked or not isinstance(ranked[0].get("action_key"), str):
                continue
            parent = ranked[0]["action_key"]
            if not parent.startswith("discard:") or accepted.get(identity.get("decision_id")) != parent:
                continue
            if any(item.get("action_key", "").startswith("hu") for item in
                   (raw.get("rules") or {}).get("legal_candidates") or []):
                continue
            parsed = longitudinal._hand(raw.get("observation") or {})
            if parsed is None:
                continue
            full, _before, _meld_count = parsed
            ctx = _context(raw["observation"], full)
            if ctx is None:
                continue
            rules = (raw.get("rules") or {}).get("legal_candidates") or []
            legal = {item["action_key"]: item.get("facts") or {} for item in rules}
            if len(legal) != len(rules) or parent not in legal:
                raise ValueError("父代已接受弃牌不在生产合法动作集合")
            ranked_by_key = {item["action_key"]: item for item in ranked}
            if len(ranked_by_key) != len(ranked):
                raise ValueError("生产评分动作键重复")
            options = []
            for key, facts in legal.items():
                if not key.startswith("discard:"):
                    continue
                scored = ranked_by_key.get(key)
                if scored is None:
                    raise ValueError("合法弃牌未进入生产评分计划")
                options.append({"key": key, "score": scored.get("total_score"),
                                "is_parent": key == parent,
                                "combined": facts.get("shanten_after"),
                                "ordinary": facts.get("standard_shanten_after"),
                                "seven": facts.get("seven_pairs_shanten_after"),
                                "support": _support(facts, "useful_tiles"),
                                "ordinary_support": _support(facts, "standard_useful_tiles"),
                                "seven_support": _support(facts, "seven_pairs_useful_tiles"),
                                "baotou_after": facts.get("baotou_after"),
                                "white_after": full["白"] - (key == "discard:白")})
            options.sort(key=lambda item: item["key"])
            counts["eligible_parent_draw_discard"] += 1
            key_id = (identity["game_id"], identity["round_no"], identity["trigger_seq"])
            old = {"g10": g10.get(key_id), "g11": g11.get(key_id), "g49": g49.get(key_id)}
            for card, program in programs.items():
                start = time.perf_counter()
                try:
                    candidate = program(ctx, options)
                except Exception as error:
                    per_card[card]["exception_" + type(error).__name__] += 1
                    continue
                timing[card].append((time.perf_counter() - start) * 1000)
                per_card[card]["evaluated"] += 1
                if candidate is None:
                    continue
                option = next((item for item in options if item["key"] == candidate), None)
                if option is None or candidate == parent:
                    per_card[card]["invalid_return"] += 1
                    continue
                before = next(item for item in options if item["key"] == parent)
                per_card[card]["changed"] += 1
                scopes[card]["tables"].add(identity["game_id"])
                scopes[card]["rooms"].add(room["room_id"])
                overlap = [name for name, action in old.items() if action == candidate]
                for name in overlap:
                    per_card[card]["same_old_" + name] += 1
                if before["baotou_after"] is True and option["baotou_after"] is not True:
                    per_card[card]["loses_baotou"] += 1
                changes[card].append({
                    "room_id": room["room_id"], "game_id": identity["game_id"],
                    "round_no": identity["round_no"], "trigger_seq": identity["trigger_seq"],
                    "parent_action": parent, "candidate_action": candidate,
                    "parent_score": before["score"], "candidate_score": option["score"],
                    "parent_combined": before["combined"], "candidate_combined": option["combined"],
                    "parent_ordinary": before["ordinary"], "candidate_ordinary": option["ordinary"],
                    "parent_seven": before["seven"], "candidate_seven": option["seven"],
                    "parent_white_after": before["white_after"],
                    "candidate_white_after": option["white_after"],
                    "parent_baotou_after": before["baotou_after"],
                    "candidate_baotou_after": option["baotou_after"],
                    "wall_remaining": ctx["wall_remaining"], "dealer": ctx["dealer"],
                    "same_old": overlap,
                })
    output = {
        "schema": "g58-official-behavior-diagnostic/1", "outcome_blind": True,
        "script_sha256": sha(Path(__file__)), "static_screen_sha256": sha(static_path),
        "frozen_rooms_sha256": sha(atlas.FROZEN),
        "parent_source_sha256": frozen["parent_source_sha256"],
        "complete_official_tables": len(complete_ids), "official_rooms": len(frozen["rooms"]),
        "counts": dict(counts),
        "cards": {
            card: {"counts": dict(per_card[card]),
                   "changed_tables": len(scopes[card]["tables"]),
                   "changed_rooms": len(scopes[card]["rooms"]),
                   "elapsed_ms_p95": (sorted(timing[card])[int((len(timing[card])-1)*0.95)]
                                      if timing[card] else None),
                   "changes": changes[card],
                   "answer_sha256": sha(wave.OUT / f"{card}.answer.txt"),
                   "strict_json_contract": next(row["strict_json_contract"]
                                                for row in static["rows"] if row["card"] == card)}
            for card in CARDS},
        "boundary": "A 仅从非严格 JSON 前缀提取作诊断，D 原程序尚未通过爆头保护审查；程序动作只在父代已接受的官方观察重判，不含未来墙、他家暗手或桌分，亦不代表可上线。",
    }
    OUT.write_text(json.dumps(output, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                   encoding="utf-8")
    print(json.dumps({"eligible": counts["eligible_parent_draw_discard"],
                      "cards": {card: {key: value for key, value in output["cards"][card].items()
                                       if key != "changes"} for card in CARDS}},
                     ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
