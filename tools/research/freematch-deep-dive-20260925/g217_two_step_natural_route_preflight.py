#!/usr/bin/env python3
"""G217：固定 G87 64 个官方同向听分歧窗，结果盲核行为独有性与成本。"""

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
from collections import Counter, defaultdict
from hashlib import sha256
import json
from pathlib import Path

import g87_post_claim_score_trace as g87
import g217_two_step_natural_route_policy as candidate
from hangma_bot.application.deadline import BudgetPolicy
from hangma_bot.kernel.serialization import observation_from_json


HERE = Path(__file__).resolve().parent
PREREG = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/G217-TWO-STEP-NATURAL-ROUTE-PREFLIGHT-2026-09-29.md')
SOURCE = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g87-post-claim-score-trace-20260928/result.json')
G61 = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g61-strong-draw-action-atlas-20260927')
G215 = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g215-first-divergence-visible-trace-20260929/result.json')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g217-two-step-natural-route-preflight-20260929/result.json')
PEERS = ("xuanwu_2346", "tengshe_0638")


def digest(path: Path) -> str:
    """内容摘要锁定固定行为母体、原始观察及候选源码。"""
    return sha256(path.read_bytes()).hexdigest()


def selected_rows() -> list[dict]:
    """每房按固定身份顺序取前两个非白同层分歧，不按宽度或结算筛选。"""
    data = json.loads(SOURCE.read_text(encoding="utf-8"))
    if data["schema"] != "g87-post-claim-score-trace/1" or len(data["rows"]) != 1083:
        raise ValueError("G87 官方同层分歧母体身份改变")
    rooms: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for row in sorted(data["rows"], key=lambda item:
                      (item["peer"], item["room"], item["game_id"],
                       item["round_no"], item["draw_seq"])):
        if (row["peer"] in PEERS
                and row["parent_action"].startswith("discard:")
                and row["strong_action"].startswith("discard:")
                and row["parent_action"] != "discard:白"
                and row["strong_action"] != "discard:白"):
            rooms[(row["peer"], row["room"])].append(row)
    if len(rooms) != 32 or any(len(items) < 2 for items in rooms.values()):
        raise ValueError("G87 非白分歧房或每房两窗不足")
    rows = [item for room in sorted(rooms) for item in rooms[room][:2]]
    if len(rows) != 64 or Counter(row["peer"] for row in rows) != {
            "xuanwu_2346": 30, "tengshe_0638": 34}:
        raise ValueError("G217 预登记 64 窗身份不守恒")
    return rows


def _observation(row: dict, index: dict, source_hashes: dict) -> object:
    """从 G61 已冻结原始窗口读玩家可见观察，不读赛后结算。"""
    unit = row["peer"] + "/" + row["room"]
    if unit not in index:
        raise ValueError("G87 来源房未在 G61 归档")
    path = _project_file(_PROJECT_ROOT, G61 / "rooms" / (row["peer"] + "--" + row["room"]) / "windows.json")
    actual_hash = digest(path)
    if actual_hash != index[unit]["windows_sha256"]:
        raise ValueError("G61 原始房窗口摘要改变")
    source_hashes[path.name + ":" + unit] = actual_hash
    matches = [window for window in json.loads(path.read_text(encoding="utf-8"))["windows"]
               if (window["game_id"], window["round_no"], window["draw_seq"])
               == (row["game_id"], row["round_no"], row["draw_seq"])]
    if len(matches) != 1:
        raise ValueError("官方可见目标窗口不唯一")
    raw = matches[0]
    if (raw["parent_top_action"] != row["parent_action"]
            or raw["actual_action"] != row["strong_action"]):
        raise ValueError("G87/G61 对手与父代动作漂移")
    return observation_from_json(raw["observation"])


def _width(request, key: str) -> tuple[int, int]:
    """只读该窗生产规则普通型有效牌及公开容量。"""
    candidate_fact = next(item for item in request.rules.legal_candidates
                          if item.action_key == key)
    width = candidate._width(candidate_fact)
    if width is None:
        raise ValueError("改选窗口宽度规则事实缺失")
    return width


def main() -> None:
    """先核官方行为和算法时延，绝不读取该批房的赛后成绩。"""
    if OUT.exists():
        raise FileExistsError(OUT)
    candidate._assert_source()
    roots = selected_rows()
    batch = json.loads((_project_file(_PROJECT_ROOT, G61 / "result.json")).read_text(encoding="utf-8"))
    source_hashes = {}
    rows = []
    durations = []
    changed_rooms = {peer: set() for peer in PEERS}
    for position, item in enumerate(roots, 1):
        observation = _observation(item, batch["units"], source_hashes)
        request = g87.request_for(observation)
        metrics: list[dict] = []
        policy = candidate.policy_factory(metrics)(None)
        budget = BudgetPolicy().build(800.0, 3.0)
        plan = asyncio.run(policy.choose(request, budget))
        if len(metrics) != 1:
            raise ValueError("G217 窗口未生成唯一选择器指标")
        metric = metrics[0]
        parent_plan = asyncio.run(candidate.g210.parent_factory(None).choose(request, budget))
        if parent_plan.candidates[0].action_key != item["parent_action"]:
            raise ValueError("G217 冻结 R18 首选与 G87 官方重判不一致")
        selected = plan.candidates[0].action_key
        if selected not in {row.action_key for row in request.rules.legal_candidates}:
            raise ValueError("G217 输出不在同窗合法集合")
        changed = selected != item["parent_action"]
        parent_width = _width(request, item["parent_action"])
        selected_width = _width(request, selected)
        strict_one_step_wider = (selected_width[0] > parent_width[0]
                                 and selected_width[1] > parent_width[1])
        if changed:
            changed_rooms[item["peer"]].add(item["room"])
        durations.append(metric["elapsed_ms"])
        rows.append({
            "peer": item["peer"], "room": item["room"],
            "game_id": item["game_id"], "round_no": item["round_no"],
            "draw_seq": item["draw_seq"],
            "parent_action": item["parent_action"],
            "strong_action": item["strong_action"],
            "g217_action": selected,
            "changed": changed,
            "matches_strong": selected == item["strong_action"],
            "strict_one_step_wider": strict_one_step_wider,
            "type_gain": selected_width[0] - parent_width[0],
            "capacity_gain": selected_width[1] - parent_width[1],
            "selector": metric,
        })
        if position % 8 == 0:
            print(json.dumps({"windows_completed": position,
                              "changed": sum(row["changed"] for row in rows)}), flush=True)
    durations.sort()
    changed = [row for row in rows if row["changed"]]
    novelty = sum(not row["strict_one_step_wider"] for row in changed)
    latency = {name: durations[int((len(durations) - 1) * fraction)]
               for name, fraction in (("p50", .5), ("p95", .95), ("max", 1.0))}
    behavior_gate = (all(len(changed_rooms[peer]) >= 8 for peer in PEERS)
                     and len(changed) > 0 and novelty / len(changed) >= 0.2)
    latency_gate = latency["p95"] < 300 and latency["max"] < 600
    result = {
        "schema": "g217-two-step-natural-route-preflight/1",
        "outcome_blind": True,
        "source_sha256": {
            "prereg": digest(PREREG), "script": digest(Path(__file__)),
            "candidate": digest(_project_file(_PROJECT_ROOT, HERE / "g217_two_step_natural_route_policy.py")),
            "g52": digest(_project_file(_PROJECT_ROOT, HERE / "g52_shared_horizon.py")),
            "g87": digest(SOURCE), "g61": digest(_project_file(_PROJECT_ROOT, G61 / "result.json")),
            "g216": digest(candidate.G216_RESULT), "g215": digest(G215),
        },
        "source_room_sha256": source_hashes,
        "window_count": len(rows),
        "rooms": len({(row["peer"], row["room"]) for row in rows}),
        "changed_windows": len(changed),
        "changed_rooms": {peer: len(value) for peer, value in changed_rooms.items()},
        "non_static_wider_changes": novelty,
        "novelty_fraction": None if not changed else novelty / len(changed),
        "selector_elapsed_ms": latency,
        "behavior_gate_pass": behavior_gate,
        "latency_gate_pass": latency_gate,
        "preflight_pass": behavior_gate and latency_gate,
        "reason_counts": dict(sorted(Counter(row["selector"]["reason"] for row in rows).items())),
        "rows": rows,
        "boundary": "已见强手分歧窗口只作结果盲行为和成本探针；匹配强手不等于收益。",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                   encoding="utf-8")
    print(json.dumps({key: result[key] for key in
                      ("changed_windows", "changed_rooms", "non_static_wider_changes",
                       "novelty_fraction", "selector_elapsed_ms", "behavior_gate_pass",
                       "latency_gate_pass", "preflight_pass", "reason_counts")},
                     ensure_ascii=False, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
