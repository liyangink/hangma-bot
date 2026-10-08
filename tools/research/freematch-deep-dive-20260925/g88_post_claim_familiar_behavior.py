#!/usr/bin/env python3
"""G88：在两套冻结官方摸牌窗上做结果盲候选行为门。"""

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

import c31_action_layer_gap as c31
import c32_cards as c32
import g05_strong_draw_reconstruction as g05
import g87_post_claim_score_trace as g87
from hangma_bot.kernel.serialization import observation_from_json
from hangma_bot.policy.r18_integrated_positive_v2 import R18_INTEGRATED_POSITIVE_V2_SOURCE


HERE = Path(__file__).resolve().parent
G61 = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g61-strong-draw-action-atlas-20260927')
G66 = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g66-survival-transfer-20260928')
G86 = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g86-post-claim-normal-draw-chain-20260928/result.json')
PREREG = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/G88-POST-CLAIM-FAMILIAR-BIAS-PREREG-2026-09-28.md')
CAND = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/candidates/G88-POST-CLAIM-FAMILIAR-BIAS-V1.py')
RISK0 = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/candidates/OPTY-R18-G1-RISK0.py')
G11 = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/candidates/G11-SHAPE-RISK-PARETO-V1.py')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g88-post-claim-familiar-behavior-20260928/result.json')


def sha(path: Path) -> str:
    """读取一次冻结输入的内容摘要。"""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def claimed(observation) -> bool:
    """仅识别本人已经公开吃或碰；单纯明杠不触发。"""
    return any(meld.kind in ("chi", "peng") for meld in observation.melds[observation.seat])


def score_one(window: dict, parent, candidate, old_scorers: dict,
              panel: str, peer: str | None, room: str) -> dict:
    """生产规则同窗重建，并复核父代首选与动作合法性。"""
    observation = observation_from_json(window["observation"])
    request = g87.request_for(observation)
    view = g05.build_scoring_view(request, value_limits=c31.VALUE_LIMITS).candidate_view()
    legal = {item["action_key"] for item in view["actions"] if item["is_legal"] is True}
    before = parent(view)
    after = candidate(view)
    if before.get("status") != "SCORED" or after.get("status") != "SCORED":
        raise ValueError("父代或候选未能评分：" + panel + "/" + room)
    old_entries = {item["action_key"]: item for item in before["entries"]}
    new_entries = {item["action_key"]: item for item in after["entries"]}
    if set(old_entries) != legal or set(new_entries) != legal:
        raise ValueError("合法动作表改变")
    old_top = g87.argmax({key: float(item["score"]) for key, item in old_entries.items()})
    new_top = g87.argmax({key: float(item["score"]) for key, item in new_entries.items()})
    if old_top != window["parent_top_action"]:
        raise ValueError("父代重放与官方存档不符：" + panel + "/" + room)
    if new_top not in legal:
        raise ValueError("候选首选不合法")
    is_claimed = claimed(observation)
    if not is_claimed and new_top != old_top:
        raise ValueError("非目标窗发生改选")
    old_actions = {}
    if new_top != old_top:
        for name, scorer in old_scorers.items():
            result = scorer(view)
            if result.get("status") != "SCORED":
                raise ValueError("旧候选不能评分：" + name)
            scores = {item["action_key"]: float(item["score"]) for item in result["entries"]}
            if set(scores) != legal:
                raise ValueError("旧候选动作集改变：" + name)
            old_actions[name] = g87.argmax(scores)
    action_facts = {item["action_key"]: item for item in view["actions"]}
    wealth = observation.rule_state.wealth_god.code
    return {
        "panel": panel, "peer": peer, "room": room, "game_id": window["game_id"],
        "round_no": window["round_no"], "draw_seq": window["draw_seq"],
        "seat": window["seat"], "claimed": is_claimed,
        "white_before": list(observation.my_hand).count(observation.rule_state.wealth_god),
        "parent_action": old_top, "candidate_action": new_top,
        "strong_action": window.get("actual_action") if panel == "g61" else None,
        "old_top_when_changed": old_actions,
        "parent_shanten": action_facts[old_top].get("shanten_after"),
        "candidate_shanten": action_facts[new_top].get("shanten_after"),
        "parent_wealth_discard": old_top == "discard:" + wealth,
        "candidate_wealth_discard": new_top == "discard:" + wealth,
        "parent_trace": old_entries[old_top]["trace"] if new_top != old_top else None,
        "candidate_trace": new_entries[new_top]["trace"] if new_top != old_top else None,
    }


def main() -> None:
    """验证 SHA、重放两个面板，写不可覆盖的逐窗行为证据。"""
    if OUT.exists():
        raise FileExistsError("G88 行为证据已存在，拒绝覆盖")
    parent = c31.load_parent()
    candidate, _ = c32.load_scorer(CAND.name)
    risk0, _ = c32.load_scorer(RISK0.name)
    g11, _ = c32.load_scorer(G11.name)
    if candidate is None or risk0 is None or g11 is None:
        raise ValueError("候选或旧对照臂缺失")
    old_scorers = {"risk0": risk0, "g11": g11}
    rows = []
    windows_hashes = {}
    targets = {g87.key(row) for row in json.loads(G86.read_text(encoding="utf-8"))["rows"]}
    if len(targets) != 1083:
        raise ValueError("G86 目标数漂移")
    manifest = json.loads((_project_file(_PROJECT_ROOT, G61 / "result.json")).read_text(encoding="utf-8"))
    found = set()
    for unit, entry in sorted(manifest["units"].items()):
        peer, room = unit.split("/", 1)
        path = _project_file(_PROJECT_ROOT, G61 / "rooms" / (peer + "--" + room) / "windows.json")
        digest = sha(path)
        if digest != entry["windows_sha256"]:
            raise ValueError("G61 官方窗摘要漂移")
        windows_hashes["g61/" + unit] = digest
        for window in json.loads(path.read_text(encoding="utf-8"))["windows"]:
            key = (peer, room, window["game_id"], window["round_no"], window["draw_seq"])
            if key not in targets:
                continue
            if key in found:
                raise ValueError("G61 目标窗重复")
            found.add(key)
            rows.append(score_one(window, parent, candidate, old_scorers, "g61", peer, room))
    if found != targets:
        raise ValueError("G61 目标窗缺失")
    batch = json.loads((_project_file(_PROJECT_ROOT, G66 / "batch_result.json")).read_text(encoding="utf-8"))
    if len(batch["rooms"]) != 40 or batch["errors"]:
        raise ValueError("G66 完整房数或错误清单漂移")
    non_target = Counter()
    for room, entry in sorted(batch["rooms"].items()):
        path = _project_file(_PROJECT_ROOT, G66 / "rooms" / room / "windows.json")
        digest = sha(path)
        if digest != entry["windows_sha256"]:
            raise ValueError("G66 官方窗摘要漂移")
        windows_hashes["g66/" + room] = digest
        for window in json.loads(path.read_text(encoding="utf-8"))["windows"]:
            if not window["own_meld_count"]:
                non_target["without_any_meld"] += 1
                continue
            # 一次 JSON 读取先排除只有杠的窗口；受控评分器输入仍从同一观察重建。
            melds = window["observation"]["melds"][window["seat"]]
            if not any(meld["kind"] in ("chi", "peng") for meld in melds):
                non_target["only_gang"] += 1
                continue
            rows.append(score_one(window, parent, candidate, old_scorers, "g66", None, room))
    counts: dict[str, Counter] = defaultdict(Counter)
    changed_rooms: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        panel = row["panel"]
        c = counts[panel]
        c["scored"] += 1
        if row["candidate_action"] == row["parent_action"]:
            continue
        c["changed"] += 1
        changed_rooms[panel].add(row["room"])
        c["strong_matches_parent"] += row["strong_action"] == row["parent_action"]
        c["strong_matches_candidate"] += row["strong_action"] == row["candidate_action"]
        c["old_both_match_candidate"] += all(
            action == row["candidate_action"] for action in row["old_top_when_changed"].values())
        c["old_neither_matches_candidate"] += all(
            action != row["candidate_action"] for action in row["old_top_when_changed"].values())
        if (type(row["parent_shanten"]) is int and type(row["candidate_shanten"]) is int
                and row["candidate_shanten"] > row["parent_shanten"]):
            c["ordinary_shanten_regress"] += 1
        c["changes_to_discard_white"] += (
            row["candidate_wealth_discard"] and not row["parent_wealth_discard"])
        c["changes_away_from_discard_white"] += (
            row["parent_wealth_discard"] and not row["candidate_wealth_discard"])
        c["white_1plus_changes"] += row["white_before"] >= 1
    summary = {panel: {**dict(counts[panel]), "changed_rooms": len(changed_rooms[panel])}
               for panel in ("g61", "g66")}
    g61 = summary["g61"]
    g66 = summary["g66"]
    passed = (g61["changed"] >= 25 and g61["changed_rooms"] >= 8
              and g66["changed"] >= 100 and g66["changed_rooms"] >= 20
              and 5 * g66["old_neither_matches_candidate"] >= g66["changed"])
    result = {
        "schema": "g88-post-claim-familiar-behavior/1", "outcome_blind": True,
        "source_sha256": {
            "parent": hashlib.sha256(R18_INTEGRATED_POSITIVE_V2_SOURCE.encode()).hexdigest(),
            "candidate": sha(CAND), "generator": sha(_project_file(_PROJECT_ROOT, HERE / "make_g88_post_claim_familiar_candidate.py")),
            "prereg": sha(PREREG), "g86": sha(G86),
            "g61_manifest": sha(_project_file(_PROJECT_ROOT, G61 / "result.json")), "g66_batch": sha(_project_file(_PROJECT_ROOT, G66 / "batch_result.json")),
            "risk0": sha(RISK0), "g11": sha(G11), "script": sha(Path(__file__)),
        },
        "windows_sha256": windows_hashes,
        "g66_non_target_count": dict(non_target), "summary": summary,
        "behavior_gate_pass": passed,
        "rows": rows,
        "boundary": "改选与旧臂去重只证明机制可达；不证明整桌积分增加或强手动作最优。",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                   encoding="utf-8")
    print(json.dumps({"summary": summary, "gate_pass": passed}, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
