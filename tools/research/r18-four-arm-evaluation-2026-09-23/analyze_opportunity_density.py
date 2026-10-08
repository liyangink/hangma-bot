"""从冻结 R18 v2 自由赛审计测量杭麻机会的自然出现与实际首选动作。"""

from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/r18-four-arm-evaluation-2026-09-23'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path


ROOT = _PROJECT_ROOT


def _wealth_count(observation: dict) -> int:
    """按官方两种摸牌快照形态计数，不把 drawn_tile 双计为财神。"""

    wealth = observation["rule_state"]["wealth_god"]
    hand = observation["my_hand"]
    count = hand.count(wealth)
    drawn = observation.get("drawn_tile")
    expected = 14 - 3 * len(observation["my_melds"])
    if drawn == wealth and len(hand) != expected:
        count += 1
    if not 0 <= count <= 4:
        raise ValueError("玩家可见财神数超范围")
    return count


def analyze(audit_root: Path) -> dict:
    """逐决策统计自见触发和已选评分覆盖，禁止从分项触发推断收益。"""

    runs = []
    phase_wealth = defaultdict(Counter)
    hands_by_key = defaultdict(set)
    overlays_any = Counter()
    overlays_selected = Counter()
    seven_pairs_claim = Counter()
    near_claim_hands = set()
    near_claim_rooms = set()
    gang_draw = Counter()
    gang_draw_hands = set()
    gang_draw_rooms = set()
    decision_ids = set()
    rooms = set()
    for manifest_path in sorted(audit_root.glob("runs/*/manifest.json")):
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))["payload"]
        if manifest.get("policy_version") != "r18_integrated_positive_v2":
            continue
        run_dir = manifest_path.parent
        paths = sorted(run_dir.glob("participants/u_*/decisions.jsonl"))
        if len(paths) != 1:
            raise ValueError("R18 v2 自由赛身份审计不唯一: " + str(run_dir))
        runs.append(run_dir.name)
        inputs = {}
        for line in paths[0].open(encoding="utf-8"):
            row = json.loads(line)
            if row.get("kind") == "decision_input":
                request = row["payload"]["request"]
                key = (request["decision_id"], len(request.get("rejected_attempts") or []) + 1)
                if key in inputs:
                    raise ValueError("决策输入重复: " + str(key))
                inputs[key] = request
                continue
            if row.get("kind") != "decision_planned":
                continue
            payload = row["payload"]
            plan = payload.get("returned_plan") or {}
            candidates = plan.get("candidates") or []
            if not candidates:
                continue
            decision_id = plan["decision_id"]
            if decision_id in decision_ids:
                raise ValueError("决策 ID 重复: " + decision_id)
            decision_ids.add(decision_id)
            request = inputs.get((decision_id, plan["revision"]))
            if request is None:
                raise ValueError("决策计划缺对应输入: " + decision_id)
            observation = payload["observation_snapshot"]
            phase = payload["window"]["phase"]
            game_id = payload["window"]["game_id"]
            rooms.add(game_id.split("_r1_b", 1)[0])
            count = _wealth_count(observation)
            key = (phase, count)
            hands_by_key[key].add((game_id, payload["window"]["round_no"]))
            stats = phase_wealth[key]
            stats["windows"] += 1
            if len(candidates) >= 2:
                stats["multi_action"] += 1
            selected = candidates[0]["action"]["kind"]
            stats["selected_" + selected] += 1
            if phase == "draw":
                if request["observation"].get("gang_draw") is True:
                    gang_draw["windows"] += 1
                    hand_key = (game_id, payload["window"]["round_no"])
                    gang_draw_hands.add(hand_key)
                    gang_draw_rooms.add(game_id.split("_r1_b", 1)[0])
                    legal_keys = {item["action_key"] for item in request["rules"]["legal_candidates"]}
                    if "hu" in legal_keys:
                        gang_draw["legal_hu"] += 1
                        if any(key.startswith("gang") for key in legal_keys):
                            gang_draw["legal_hu_with_gang"] += 1
                        wealth_key = "discard:" + observation["rule_state"]["wealth_god"]
                        if wealth_key in legal_keys:
                            gang_draw["legal_hu_with_wealth_discard"] += 1
                wealth_discard = "discard:" + observation["rule_state"]["wealth_god"]
                if any(item["action_key"] == wealth_discard for item in candidates):
                    stats["can_discard_wealth"] += 1
                if candidates[0]["action_key"] == wealth_discard:
                    stats["selected_discard_wealth"] += 1
                if any(item["action"]["kind"] == "hu" for item in candidates):
                    stats["legal_hu"] += 1
                if observation["rule_state"].get("baotou") is True:
                    stats["already_baotou"] += 1
            elif phase.startswith("response_"):
                if any(item["action"]["kind"] in ("chi", "peng", "gang")
                       for item in candidates):
                    stats["legal_claim"] += 1
                    if selected in ("chi", "peng", "gang"):
                        stats["selected_claim"] += 1
                    if count >= 2 and not observation["my_melds"]:
                        seven_pairs_claim["two_plus_wealth_no_meld_claim_windows"] += 1
                        passes = [item for item in request["rules"]["legal_candidates"]
                                  if item["action_key"] == "pass"]
                        if len(passes) == 1:
                            shanten = passes[0]["facts"].get("seven_pairs_shanten_after")
                            if type(shanten) is int and shanten <= 1:
                                seven_pairs_claim["seven_pairs_near_claim_windows"] += 1
                                near_claim_hands.add((game_id, payload["window"]["round_no"]))
                                near_claim_rooms.add(game_id.split("_r1_b", 1)[0])
                                if selected in ("chi", "peng", "gang"):
                                    seven_pairs_claim["selected_claim_closes_near_seven_pairs"] += 1
                                    pass_standard = passes[0]["facts"].get("standard_shanten_after")
                                    chosen = next((item for item in request["rules"]["legal_candidates"]
                                                   if item["action_key"] == candidates[0]["action_key"]), None)
                                    if chosen is None:
                                        raise ValueError("首选动作缺合法事实: " + decision_id)
                                    claim_standard = chosen["facts"].get("standard_shanten_after")
                                    if type(pass_standard) is int and type(claim_standard) is int:
                                        if claim_standard < pass_standard:
                                            seven_pairs_claim["selected_claim_improves_standard"] += 1
                                        elif claim_standard == pass_standard:
                                            seven_pairs_claim["selected_claim_same_standard"] += 1
                                        else:
                                            seven_pairs_claim["selected_claim_worsens_standard"] += 1
                                    else:
                                        seven_pairs_claim["selected_claim_standard_unknown"] += 1
            found = set()
            for item in candidates:
                detail = (item.get("score_trace") or {}).get("detail") or {}
                for name, value in detail.items():
                    if isinstance(value, dict) and value.get("triggered") is True:
                        found.add(name)
            overlays_any.update(found)
            detail = (candidates[0].get("score_trace") or {}).get("detail") or {}
            overlays_selected.update(name for name, value in detail.items()
                                     if isinstance(value, dict) and value.get("triggered") is True)
    if not runs:
        raise ValueError("没有冻结 R18 v2 自由赛审计")
    return {"schema": "r18-natural-opportunity-density/1",
            "audit_root": str(audit_root.relative_to(ROOT)),
            "run_count": len(runs), "run_ids": runs, "room_count": len(rooms),
            "decision_count": len(decision_ids),
            "phase_wealth": [{"phase": phase, "wealth_count": wealth,
                              "distinct_hands": len(hands_by_key[(phase, wealth)]),
                              **dict(stats)}
                             for (phase, wealth), stats in sorted(phase_wealth.items())],
            "any_candidate_triggered_overlay": dict(overlays_any),
            "selected_candidate_triggered_overlay": dict(overlays_selected),
            "seven_pairs_claim": {**dict(seven_pairs_claim),
                                  "near_claim_distinct_hands": len(near_claim_hands),
                                  "near_claim_distinct_rooms": len(near_claim_rooms)},
            "gang_draw": {"windows": gang_draw["windows"],
                          "distinct_hands": len(gang_draw_hands),
                          "distinct_rooms": len(gang_draw_rooms),
                          "legal_hu": gang_draw["legal_hu"],
                          "legal_hu_with_gang": gang_draw["legal_hu_with_gang"],
                          "legal_hu_with_wealth_discard": gang_draw["legal_hu_with_wealth_discard"]},
            "interpretation": "触发与评分分项均非首选改选、更非收益；须与同观察重放和完整桌赛验证联读。"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit-root", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    result = analyze(args.audit_root.resolve())
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                        encoding="utf-8")
    print(args.out)


if __name__ == "__main__":
    main()
