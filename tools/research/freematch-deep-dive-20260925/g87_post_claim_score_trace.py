#!/usr/bin/env python3
"""G87：逐窗复核已吃碰后 R18 v2 评分分量与旧风险消融重合。"""

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
from hangma_bot.kernel.serialization import observation_from_json


HERE = Path(__file__).resolve().parent
SOURCE = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g86-post-claim-normal-draw-chain-20260928/result.json')
G61 = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g61-strong-draw-action-atlas-20260927')
PREREG = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/G87-POST-CLAIM-SCORE-TRACE-PREREG-2026-09-28.md')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g87-post-claim-score-trace-20260928/result.json')
EXPECTED_SOURCE = "fd029d1b0a6e23ea1ccd2813bed320f4075ef8f1da5ae53d8a53b686c30f974e"
RISK0 = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/candidates/OPTY-R18-G1-RISK0.py')
COMPONENTS = ("base_score", "wealth_part", "wealth_discard_part",
              "river_part", "risk_part", "style_part", "hu_baotou_overlay")


def sha(path: Path) -> str:
    """固定发现集与评分源码身份。"""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def key(row: dict) -> tuple:
    """目标座位-官方摸牌序号键，避免同房另一强手碰撞。"""
    return (row["peer"], row["room"], row["game_id"], row["round_no"], row["draw_seq"])


def request_for(observation):
    """只由本人依法可见观察和生产规则建立冻结策略评分请求。"""
    rules = c31.RULES.analyze(observation, value_limits=c31.VALUE_LIMITS)
    return g05.DecisionRequest(
        observation=observation,
        competition=g05.CompetitionContext(
            tournament_id="g87-score-trace", stage_no=None, stage_role=None,
            stage_total=None, participant_rank=None, ranking=(), observed_at_unix_ms=0),
        rules=rules, decision_id="g87:" + str(observation.snapshot_seq),
        trigger_seq=observation.snapshot_seq,
        window_key=g05.WindowKey(
            game_id=observation.game_id, round_no=observation.round_no,
            trigger_seq=observation.snapshot_seq,
            phase=g05.WindowPhase.DRAW, seat=observation.seat),
        rejected_attempts=(),
    )


def argmax(scores: dict[str, float]) -> str:
    """按 G05 冻结排序：分数降序，动作键升序。"""
    return min(scores, key=lambda action: (-scores[action], action))


def component(trace: dict, name: str) -> float:
    """把冻结评分 trace 投影为各项对总分的正负贡献。"""
    if name == "hu_baotou_overlay":
        overlay = trace.get("hu_vs_nonwealth_baotou_cf") or {}
        value = overlay.get("score_delta", 0.0)
        if type(value) not in (int, float):
            raise ValueError("胡与保包头覆盖增分不是数值")
        return float(value)
    value = trace.get("risk_units") if name == "risk_part" else trace.get(name)
    if type(value) not in (int, float):
        raise ValueError("评分分量缺失或非数值：" + name)
    return -6.0 * float(value) if name == "risk_part" else float(value)


def main() -> None:
    """重算 1,083 个官方可见窗，并对账旧 RISK0 行为重合。"""
    if OUT.exists():
        raise SystemExit("G87 证据已存在，拒绝覆盖")
    if sha(SOURCE) != EXPECTED_SOURCE:
        raise ValueError("G86 冻结目标摘要漂移")
    source = json.loads(SOURCE.read_text(encoding="utf-8"))
    targets = {key(row): row for row in source["rows"]}
    if len(targets) != 1083:
        raise ValueError("G86 目标键数漂移")
    batch = json.loads((_project_file(_PROJECT_ROOT, G61 / "result.json")).read_text(encoding="utf-8"))
    parent = c31.load_parent()
    risk0, _ = c32.load_scorer(RISK0.name)
    if risk0 is None:
        raise ValueError("旧 RISK0 源码不可装配")
    rows = []
    found = set()
    for unit, record in sorted(batch["units"].items()):
        peer, room = unit.split("/", 1)
        path = _project_file(_PROJECT_ROOT, G61 / "rooms" / (peer + "--" + room) / "windows.json")
        if sha(path) != record["windows_sha256"]:
            raise ValueError("G61 逐窗冻结摘要漂移")
        for window in json.loads(path.read_text(encoding="utf-8"))["windows"]:
            k = (peer, room, window["game_id"], window["round_no"], window["draw_seq"])
            target = targets.get(k)
            if target is None:
                continue
            if k in found:
                raise ValueError("G87 目标窗口重复")
            found.add(k)
            if (target["strong_action"] != window["actual_action"] or
                    target["parent_action"] != window["parent_top_action"]):
                raise ValueError("G86/G61 强手或父代动作漂移")
            observation = observation_from_json(window["observation"])
            request = request_for(observation)
            view = g05.build_scoring_view(request, value_limits=c31.VALUE_LIMITS).candidate_view()
            result = parent(view)
            old = risk0(view)
            if result.get("status") != "SCORED" or old.get("status") != "SCORED":
                raise ValueError("冻结父代或旧 RISK0 评分失败")
            entries = {item["action_key"]: item for item in result["entries"]}
            scores = {action: float(item["score"]) for action, item in entries.items()}
            if argmax(scores) != target["parent_action"]:
                raise ValueError("重算父代首选动作与 G61 不一致")
            strong = target["strong_action"]
            chosen = target["parent_action"]
            if strong not in entries:
                raise ValueError("强手弃牌不在父代合法动作表")
            gap = scores[chosen] - scores[strong]
            if abs(gap - target["parent_score_gap"]) > 1e-8:
                raise ValueError("冻结评分差与 G61 不一致")
            old_scores = {item["action_key"]: float(item["score"])
                          for item in old["entries"]}
            if set(old_scores) != set(scores):
                raise ValueError("旧 RISK0 合法动作集改变")
            traces = {action: entries[action]["trace"] for action in (chosen, strong)}
            delta = {name: component(traces[chosen], name) - component(traces[strong], name)
                     for name in COMPONENTS}
            residual = gap - sum(delta.values())
            if abs(residual) < 1e-8:
                residual = 0.0
            river0_scores = {
                action: scores[action] - component(entry["trace"], "river_part")
                for action, entry in entries.items()
            }
            chain = target["chain"]
            bucket = ("gang_intervened" if chain["intervening_own_gang_count"] else
                      "first" if chain["normal_draw_ordinal_since_claim"] == 1 else
                      "second" if chain["normal_draw_ordinal_since_claim"] == 2 else
                      "third_plus")
            rows.append({"peer": peer, "room": room, "game_id": k[2],
                         "round_no": k[3], "draw_seq": k[4], "seat": window["seat"],
                         "bucket": bucket, "white_before": target["white_before"],
                         "strong_action": strong, "parent_action": chosen,
                         "parent_gap": gap, "component_parent_minus_strong": delta,
                         "component_residual": residual,
                         "strong_ordinary_codes_delta": target["ordinary_codes_delta"],
                         "strong_ordinary_capacity_delta": target["ordinary_capacity_delta"],
                         "risk0_top": argmax(old_scores),
                         "river0_top": argmax(river0_scores),
                         "parent_trace": traces[chosen], "strong_trace": traces[strong]})
    if found != set(targets):
        raise ValueError("G86 目标未全部重算")
    summaries = {}
    stratum_counts: dict[str, Counter] = defaultdict(Counter)
    stratum_rooms: dict[str, set[str]] = defaultdict(set)
    for peer in ("xuanwu_2346", "tengshe_0638"):
        peer_rows = [row for row in rows if row["peer"] == peer]
        totals = Counter()
        rooms = defaultdict(set)
        for row in peer_rows:
            wide = row["strong_ordinary_codes_delta"] > 0 and row["strong_ordinary_capacity_delta"] > 0
            stratum = peer + "/" + row["bucket"] + "/white_" + (
                "0" if row["white_before"] == 0 else "1plus")
            sc = stratum_counts[stratum]
            sc["windows"] += 1
            sc["strong_both_wider"] += wide
            sc["risk0_matches_strong"] += row["risk0_top"] == row["strong_action"]
            sc["river0_matches_strong"] += row["river0_top"] == row["strong_action"]
            for name in ("base_score", "river_part", "risk_part", "style_part"):
                sc[name + ":favours_parent"] += row["component_parent_minus_strong"][name] > 0
            stratum_rooms[stratum].add(row["room"])
            totals["windows"] += 1
            totals["strong_both_wider"] += wide
            totals["strong_base_higher"] += row["component_parent_minus_strong"]["base_score"] < 0
            totals["risk0_matches_strong"] += row["risk0_top"] == row["strong_action"]
            totals["river0_matches_strong"] += row["river0_top"] == row["strong_action"]
            totals["nonzero_residual"] += row["component_residual"] != 0.0
            for name, value in row["component_parent_minus_strong"].items():
                totals[name + (":favours_parent" if value > 0 else ":favours_strong" if value < 0 else ":same")] += 1
            if wide:
                totals["wide_risk0_matches_strong"] += row["risk0_top"] == row["strong_action"]
                totals["wide_river0_matches_strong"] += row["river0_top"] == row["strong_action"]
                rooms["both_wider"].add(row["room"])
                for name in COMPONENTS:
                    if row["component_parent_minus_strong"][name] > 0:
                        rooms["wide_parent_adv:" + name].add(row["room"])
                for name, value in row["component_parent_minus_strong"].items():
                    totals["wide_" + name + (":favours_parent" if value > 0 else ":favours_strong" if value < 0 else ":same")] += 1
        summaries[peer] = {"counts": dict(sorted(totals.items())),
                           "rooms": {name: len(values) for name, values in sorted(rooms.items())}}
    result = {"schema": "g87-post-claim-score-trace/1", "exploratory": True,
              "terminal_score_labels_opened": False,
              "source_sha256": {"g86": sha(SOURCE), "prereg": sha(PREREG),
                                "script": sha(Path(__file__)), "risk0": sha(RISK0)},
              "summaries": summaries,
              "strata": {name: {"counts": dict(sorted(counts.items())),
                                "rooms": len(stratum_rooms[name])}
                         for name, counts in sorted(stratum_counts.items())},
              "rows": sorted(rows, key=lambda row: (row["peer"], row["room"], row["game_id"],
                                                  row["round_no"], row["draw_seq"])),
              "boundary": "评分分量解释父代排序，不证明强手动作收益；RISK0 已在独立确认失败。"}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                   encoding="utf-8")
    print(json.dumps(summaries, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
