#!/usr/bin/env python3
"""G150：冻结官方正常摸打窗的结果盲合法行为与旧候选重合审计。"""

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
import time

import c31_action_layer_gap as c31
import c32_cards as c32
import g05_strong_draw_reconstruction as g05
import g87_post_claim_score_trace as g87
from hangma_bot.kernel.serialization import observation_from_json
from hangma_bot.policy.r18_integrated_positive_v2 import R18_INTEGRATED_POSITIVE_V2_SOURCE


HERE = Path(__file__).resolve().parent
G61 = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g61-strong-draw-action-atlas-20260927')
G66 = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g66-survival-transfer-20260928')
PREREG = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/G150-ONE-WHITE-PLAIN-WAIT-PILOT-PREREG-2026-09-28.md')
CAND = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/candidates/G150-ONE-WHITE-PLAIN-WAIT-V1.py')
OLD = {
    "g11": _project_file(_PROJECT_ROOT, HERE / "candidates/G11-SHAPE-RISK-PARETO-V1.py"),
    "g88": _project_file(_PROJECT_ROOT, HERE / "candidates/G88-POST-CLAIM-FAMILIAR-BIAS-V1.py"),
    "g131": _project_file(_PROJECT_ROOT, HERE / "candidates/G131-STANDARD-SHADOW-HIGH-V1.py"),
}
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g150-one-white-plain-wait-behavior-20260928/result.json')


def sha(path: Path) -> str:
    """核官方窗口、冻结源码和审计器字节身份。"""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def possible_target(row: dict) -> bool:
    """按当前公开观察廉价预筛；不读取未来牌墙或赛后分数。"""
    observation = row["observation"]
    hand = observation["my_hand"]
    white = hand.count("白")
    if (observation.get("drawn_tile") == "白"
            and len(hand) != 14 - 3 * row["own_meld_count"]):
        white += 1
    return (white == 1 and row["remaining_tile_count"] > 20
            and row["baotou"] is False
            and row["legal_action_types"].get("hu", 0) == 0)


def top(result: dict) -> str:
    """使用父代审计同一分数降序、动作键升序排序。"""
    if result.get("status") != "SCORED":
        raise ValueError("评分器弃权")
    return g87.argmax({entry["action_key"]: float(entry["score"])
                       for entry in result["entries"]})


def score_one(row: dict, *, panel: str, room: str, peer: str | None,
              parent, candidate, old_scorers: dict) -> dict | None:
    """生产规则重建一次评分；仅改选时才运行三个旧失败臂。"""
    observation = observation_from_json(row["observation"])
    view = g05.build_scoring_view(g87.request_for(observation),
                                  value_limits=c31.VALUE_LIMITS).candidate_view()
    legal = {a["action_key"] for a in view["actions"] if a["is_legal"] is True}
    prior = parent(view)
    started = time.perf_counter_ns()
    revised = candidate(view)
    candidate_ns = time.perf_counter_ns() - started
    if prior.get("status") != "SCORED" or revised.get("status") != "SCORED":
        raise ValueError("父代或候选评分弃权")
    if ({a["action_key"] for a in prior["entries"]} != legal
            or {a["action_key"] for a in revised["entries"]} != legal):
        raise ValueError("候选合法动作集变化")
    old_top, new_top = top(prior), top(revised)
    if old_top != row["parent_top_action"]:
        raise ValueError("父代重放与官方窗口不符")
    if new_top == old_top:
        return {"changed": False, "candidate_ns": candidate_ns}
    actions = {a["action_key"]: a for a in view["actions"]}
    old = actions[old_top]
    new = actions[new_top]
    old_seven, new_seven = (a.get("seven_pairs_shanten_after") for a in (old, new))
    if (old.get("action_type") != "discard" or new.get("action_type") != "discard"
            or old_top == "discard:白" or new_top == "discard:白"
            or old.get("shanten_after") != new.get("shanten_after")
            or old.get("standard_shanten_after") != 0
            or new.get("standard_shanten_after") != 0
            or (type(old_seven) is int and
                (type(new_seven) is not int or new_seven > old_seven))):
        raise ValueError("G150 改选违反普通胡或七对守门")
    old_scores = {a["action_key"]: a["score"] for a in prior["entries"]}
    if old_scores[old_top] - old_scores[new_top] > 3.0:
        raise ValueError("G150 改选超出父代近分门")
    old_actions = {name: top(scorer(view)) for name, scorer in old_scorers.items()}
    trace = next(a["trace"] for a in revised["entries"]
                 if a["action_key"] == new_top)
    g150 = trace.get("g150_plain_wait")
    if not g150 or g150["chosen_plain_capacity"] < g150["anchor_plain_capacity"] + 3:
        raise ValueError("G150 改选未扩大纯平胡公开容量")
    return {
        "changed": True, "candidate_ns": candidate_ns,
        "panel": panel, "peer": peer, "room": room,
        "game_id": row["game_id"], "round_no": row["round_no"],
        "draw_seq": row["draw_seq"], "seat": row["seat"],
        "parent_action": old_top, "candidate_action": new_top,
        "strong_action": row.get("actual_action") if panel == "g61" else None,
        "old_actions": old_actions,
        "parent_plain_capacity": g150["anchor_plain_capacity"],
        "candidate_plain_capacity": g150["chosen_plain_capacity"],
        "parent_score_gap": old_scores[old_top] - old_scores[new_top],
    }


def main() -> None:
    """两份冻结官方窗逐个来源对账，保留改选行为供新桌赛审查。"""
    if OUT.exists():
        raise FileExistsError("G150 行为结果已存在，拒绝覆盖")
    parent = c31.load_parent()
    candidate, _ = c32.load_scorer(CAND.name)
    old_scorers = {name: c32.load_scorer(path.name)[0]
                   for name, path in OLD.items()}
    if candidate is None or any(scorer is None for scorer in old_scorers.values()):
        raise ValueError("G150 或旧对照臂不能加载")
    changed = []
    counts = defaultdict(Counter)
    rooms = defaultdict(set)
    hashes = {}
    g61 = json.loads((_project_file(_PROJECT_ROOT, G61 / "result.json")).read_text(encoding="utf-8"))
    g66 = json.loads((_project_file(_PROJECT_ROOT, G66 / "batch_result.json")).read_text(encoding="utf-8"))
    sources = []
    for unit, info in sorted(g61["units"].items()):
        peer, room = unit.split("/", 1)
        sources.append(("g61", room, peer, _project_file(_PROJECT_ROOT, G61 / "rooms" / (peer + "--" + room)
                        / "windows.json"), info["windows_sha256"]))
    for room, info in sorted(g66["rooms"].items()):
        sources.append(("g66", room, None, _project_file(_PROJECT_ROOT, G66 / "rooms" / room / "windows.json"),
                        info["windows_sha256"]))
    for panel, room, peer, path, expected in sources:
        digest = sha(path)
        if digest != expected:
            raise ValueError("官方窗口源摘要漂移：" + panel + "/" + room)
        hashes[panel + "/" + (peer + "/" if peer else "") + room] = digest
        for row in json.loads(path.read_text(encoding="utf-8"))["windows"]:
            counts[panel]["all_windows"] += 1
            if not possible_target(row):
                continue
            counts[panel]["possible_target_windows"] += 1
            result = score_one(row, panel=panel, room=room, peer=peer,
                               parent=parent, candidate=candidate,
                               old_scorers=old_scorers)
            counts[panel]["scored_windows"] += 1
            if result["changed"]:
                changed.append(result)
                counts[panel]["changed_windows"] += 1
                rooms[panel].add(room)
                counts[panel]["different_from_all_old"] += all(
                    action != result["candidate_action"]
                    for action in result["old_actions"].values())
                counts[panel]["strong_matches_candidate"] += (
                    result["strong_action"] == result["candidate_action"])
                counts[panel]["strong_matches_parent"] += (
                    result["strong_action"] == result["parent_action"])
    total_changed = len(changed)
    unique_rooms = len(set().union(*rooms.values())) if rooms else 0
    distinct = sum(all(action != row["candidate_action"]
                       for action in row["old_actions"].values()) for row in changed)
    passed = (total_changed >= 30 and unique_rooms >= 10
              and distinct * 2 >= total_changed)
    result = {
        "schema": "g150-one-white-plain-wait-behavior/1",
        "source_sha256": {
            "parent": hashlib.sha256(R18_INTEGRATED_POSITIVE_V2_SOURCE.encode()).hexdigest(),
            "candidate": sha(CAND), "generator": sha(_project_file(_PROJECT_ROOT, HERE / "g150_make_plain_wait_candidate.py")),
            "prereg": sha(PREREG), "g61": sha(_project_file(_PROJECT_ROOT, G61 / "result.json")),
            "g66": sha(_project_file(_PROJECT_ROOT, G66 / "batch_result.json")),
            **{name: sha(path) for name, path in OLD.items()},
            "script": sha(Path(__file__)),
        },
        "windows_sha256": hashes,
        "counts": {name: {**dict(counter), "changed_rooms": len(rooms[name])}
                   for name, counter in counts.items()},
        "changed_total": total_changed,
        "changed_rooms_union": unique_rooms,
        "different_from_all_old": distinct,
        "behavior_gate_pass": passed,
        "changed_rows": changed,
        "boundary": "结果盲合法行为与旧候选动作对照；强手匹配和公开容量均不是策略收益。",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                   encoding="utf-8")
    print(json.dumps({"counts": result["counts"], "changed_total": total_changed,
                      "changed_rooms_union": unique_rooms,
                      "different_from_all_old": distinct,
                      "behavior_gate_pass": passed}, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
