#!/usr/bin/env python3
"""G47：G32 即时无人鸣的配对改弃牌桌，追踪本人下一次摸牌与自然牌形。"""

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

import g11_longitudinal_route_audit as hands
import g40_official_natural_gap_reach as natural
import g41_first_divergence_audit as g41
import g46_paired_first_response_audit as paired
from hangma_bot.hangma.engine import _build_context
from hangma_bot.kernel.serialization import observation_from_json


HERE = Path(__file__).resolve().parent
G46 = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g46-paired-first-response-20260927/result.json')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g47-next-own-draw-shape-20260927/result.json')


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def next_draw(own: list, first: int, round_no: int):
    """取首处分歧后的下一个本人摸牌决策，不跨小局。"""

    for request, plan in own[first + 1:]:
        if request.window_key.round_no != round_no:
            return None
        if request.window_key.phase.value == "draw":
            return request, plan
    return None


def intervening(outcome, first_decision_id: str, next_decision_id: str | None,
                round_no: int) -> list[tuple[int, str, str]]:
    """本人下摸前的全座位已执行动作；不保留暗手、牌墙或未来终局。"""

    records = list(outcome.decisions)
    start = next((n for n, row in enumerate(records) if row.decision_id == first_decision_id), None)
    if start is None:
        raise ValueError("首处分歧缺完整桌动作记录")
    tail = []
    for row in records[start + 1:]:
        if row.window_key.get("round_no") != round_no or row.decision_id == next_decision_id:
            break
        tail.append((row.seat, row.window_key["phase"], row.action_key))
    return tail


def _natural_support(facts: dict, name: str) -> dict | None:
    """规则已有的公开逐码有效张；白板是财神，不并入自然进张。"""

    entries = facts.get(name)
    if not isinstance(entries, list):
        return None
    natural_entries = [item for item in entries if item.get("code") != "白"]
    if any(type(item.get("remaining_estimate")) is not int for item in natural_entries):
        raise ValueError("有效牌公开剩余张数缺失")
    by_tile = {item["code"]: item["remaining_estimate"] for item in natural_entries
               if item["remaining_estimate"] > 0}
    if len(by_tile) != sum(item["remaining_estimate"] > 0 for item in natural_entries):
        raise ValueError("有效牌码重复")
    return {"tile_types": len(by_tile), "tile_count": sum(by_tile.values()),
            "by_tile": dict(sorted(by_tile.items()))}


def next_shape(row) -> dict:
    """下一摸后的父代/候选已选动作，按同源生产事实记录自然进张与多路线。"""

    decision = g41._decision(row)
    choice = decision["ranked"][0]["action_key"]
    legal = {item["action_key"]: item.get("facts") or {}
             for item in decision["rules"]["legal_candidates"]}
    if choice not in legal:
        raise ValueError("下一摸已选动作不在合法候选")
    facts = legal[choice]
    obs = decision["observation"]
    decoded = observation_from_json(obs)
    full = Counter(tile.code for tile in _build_context(decoded).full_hand())
    meld_count = len(decoded.melds[decoded.seat])
    result = {"window": decision["window"], "drawn_tile": obs.get("drawn_tile"),
              "remaining_tile_count": obs.get("remaining_tile_count"),
              "choice": choice, "own_white_before": full["白"],
              "standard_shanten_after": facts.get("standard_shanten_after"),
              "seven_pairs_shanten_after": facts.get("seven_pairs_shanten_after"),
              "combined_shanten_after": facts.get("shanten_after"),
              "standard_natural_useful": _natural_support(facts, "standard_useful_tiles"),
              "seven_pairs_natural_useful": _natural_support(facts, "seven_pairs_useful_tiles"),
              "combined_natural_useful": _natural_support(facts, "useful_tiles")}
    if choice.startswith("discard:"):
        after = hands._after_discard(full, choice)
        if after is None:
            raise ValueError("下一摸选择弃牌不在本人手牌")
        result["white_after"] = after["白"]
        result["natural_standard_need_after"] = natural.gap(after, meld_count)
        if natural.standard(after, meld_count) != facts.get("standard_shanten_after"):
            raise ValueError("下一摸自然缺口与官方生产数学向听错配")
    else:
        result["white_after"] = None
        result["natural_standard_need_after"] = None
    return result


def main() -> None:
    """G46 已看开发根只作机制诊断；严禁把下一摸未来牌作为在线输入。"""

    if OUT.exists():
        raise SystemExit("G47 结果已存在，拒绝覆盖")
    source = json.loads(G46.read_text(encoding="utf-8"))
    selected = [row for row in source["rows"] if row["first_divergence_index"] is not None
                and row["baseline_immediate"] == row["candidate_immediate"]
                and row["baseline_immediate"]["kind"] == "none"]
    if len(selected) != 40 or len(source["rows"]) != 192:
        raise ValueError("G46 即时无人鸣冻结切片漂移")
    by_stage = defaultdict(list)
    for row in selected:
        by_stage[row["mix"], row["root"], row["focal_seat"]].append(row)
    manifest = json.loads((paired.FROZEN / "manifest.json").read_text(encoding="utf-8"))
    rows = []
    for (mix, root, seat), targets in sorted(by_stage.items()):
        baseline, b_own, b_outcomes, _ = paired.replay(mix, root, seat, manifest["arms"][0], manifest)
        candidate, c_own, c_outcomes, _ = paired.replay(mix, root, seat, manifest["arms"][1], manifest)
        stage_b = {item["table_id"]: item for item in baseline["tables"]}
        stage_c = {item["table_id"]: item for item in candidate["tables"]}
        for target in targets:
            table_id = target["table_id"]
            if (stage_c[table_id]["hand_account"]["focal_table_delta"] -
                    stage_b[table_id]["hand_account"]["focal_table_delta"] != target["delta"]):
                raise ValueError("G47 复跑与 G46 桌分不一致")
            first = target["first_divergence_index"]
            before = b_own[table_id]
            after = c_own[table_id]
            if (g41._identity(before[first]) == g41._identity(after[first]) or
                    g41._decision(before[first])["observation"] !=
                    g41._decision(after[first])["observation"]):
                raise ValueError("G47 首处分歧身份漂移")
            b_first, c_first = before[first][0], after[first][0]
            round_no = b_first.window_key.round_no
            b_next = next_draw(before, first, round_no)
            c_next = next_draw(after, first, round_no)
            b_id = b_next[0].decision_id if b_next else None
            c_id = c_next[0].decision_id if c_next else None
            b_actions = intervening(b_outcomes["sitin-stage:" + table_id],
                                    b_first.decision_id, b_id, round_no)
            c_actions = intervening(c_outcomes["sitin-stage:" + table_id],
                                    c_first.decision_id, c_id, round_no)
            b_shape = next_shape(b_next) if b_next else None
            c_shape = next_shape(c_next) if c_next else None
            rows.append({"table_id": table_id, "mix": mix, "root": root,
                         "seat_group": seat, "actual_focal_seat": b_first.window_key.seat,
                         "round_no": round_no,
                         "first_baseline_action": target["baseline_action"],
                         "first_candidate_action": target["candidate_action"],
                         "table_delta": target["delta"],
                         "same_intervening_actions": b_actions == c_actions,
                         "intervening_action_count": {"baseline": len(b_actions),
                                                      "candidate": len(c_actions)},
                         "baseline_next": b_shape, "candidate_next": c_shape})
        print(json.dumps({"mix": mix, "root": root, "seat": seat,
                          "selected_tables": len(targets)}, ensure_ascii=False), flush=True)
    if len(rows) != 40:
        raise ValueError("G47 切片缺完整桌")
    counts = Counter()
    by_mix = defaultdict(Counter)
    for row in rows:
        mix = row["mix"]
        b, c = row["baseline_next"], row["candidate_next"]
        if b is None and c is None:
            category = "both_censored"
        elif b is None or c is None:
            category = "one_censored"
        elif b["drawn_tile"] != c["drawn_tile"]:
            category = "different_next_draw"
        elif not row["same_intervening_actions"]:
            category = "same_draw_changed_path"
        else:
            category = "same_draw_same_intervening_actions"
        counts[category] += 1
        by_mix[mix][category] += 1
        row["pair_category"] = category
        if b and c and b["choice"].startswith("discard:") and c["choice"].startswith("discard:"):
            first_b = row["first_baseline_action"].split(":", 1)[1]
            first_c = row["first_candidate_action"].split(":", 1)[1]
            second_b = b["choice"].split(":", 1)[1]
            second_c = c["choice"].split(":", 1)[1]
            row["same_two_discard_multiset"] = (Counter((first_b, second_b)) ==
                                                 Counter((first_c, second_c)))
            for field in ("standard_natural_useful", "seven_pairs_natural_useful",
                          "combined_natural_useful"):
                if b[field] is None or c[field] is None:
                    continue
                delta = c[field]["tile_count"] - b[field]["tile_count"]
                direction = "higher" if delta > 0 else "lower" if delta < 0 else "equal"
                counts[f"next_{field}|{direction}"] += 1
                by_mix[mix][f"next_{field}|{direction}"] += 1
                distribution = "same" if b[field]["by_tile"] == c[field]["by_tile"] else "different"
                counts[f"next_{field}_distribution|{distribution}"] += 1
                by_mix[mix][f"next_{field}_distribution|{distribution}"] += 1
            if row["same_two_discard_multiset"]:
                counts["same_two_discard_multiset"] += 1
                by_mix[mix]["same_two_discard_multiset"] += 1
            if b["natural_standard_need_after"] is not None and c["natural_standard_need_after"] is not None:
                diff = c["natural_standard_need_after"] - b["natural_standard_need_after"]
                direction = "higher" if diff > 0 else "lower" if diff < 0 else "equal"
                counts[f"next_natural_standard_need|{direction}"] += 1
                by_mix[mix][f"next_natural_standard_need|{direction}"] += 1
    result = {"schema": "g47-next-own-draw-shape/1", "source_g46_sha256": sha(G46),
              "script_sha256": sha(Path(__file__)), "rows": rows,
              "counts": dict(sorted(counts.items())),
              "by_mix": {mix: dict(sorted(value.items())) for mix, value in sorted(by_mix.items())},
              "boundary": "旧 G32 开发根的赛后未来摸牌仅作配对诊断，不是在线特征；按首弃后即时双方均无人鸣选择，存在事后分层，不作收益因果推断或确认集。"}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"counts": result["counts"], "by_mix": result["by_mix"]},
                     ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
