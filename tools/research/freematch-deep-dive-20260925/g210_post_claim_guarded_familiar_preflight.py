#!/usr/bin/env python3
"""G210：对 G88 已归档改选逐窗重建规则事实，筛查严格宽面且风险不退的独有行为。"""

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
from hashlib import sha256
import json
from pathlib import Path

import c31_action_layer_gap as c31
import c32_cards as c32
import g05_strong_draw_reconstruction as g05
import g87_post_claim_score_trace as g87
from hangma_bot.kernel.serialization import observation_from_json


HERE = Path(__file__).resolve().parent
SOURCE = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g88-post-claim-familiar-behavior-20260928/result.json')
G61 = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g61-strong-draw-action-atlas-20260927/rooms')
G66 = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g66-survival-transfer-20260928/rooms')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g210-post-claim-guarded-familiar-20260929/result.json')


def digest(path: Path) -> str:
    """绑定既有观察和评分源码的原始字节身份。"""
    return sha256(path.read_bytes()).hexdigest()


def width(value) -> tuple[int, int] | None:
    """统计公开正容量牌码和物理剩余张数，不解释成真实牌墙概率。"""
    if value is None:
        return None
    counts = [tile.get("remaining_estimate") for tile in value]
    if any(type(n) is not int or n < 0 or n > 4 for n in counts):
        return None
    return sum(n > 0 for n in counts), sum(counts)


def key(row: dict) -> tuple:
    """本方正常摸牌窗口的官方身份。"""
    return row["game_id"], row["round_no"], row["draw_seq"], row["seat"]


def score_window(window: dict, archived: dict, parent, g88) -> dict:
    """核原首选并用当前生产规则获取两动作的行动前事实。"""
    observation = observation_from_json(window["observation"])
    request = g87.request_for(observation)
    view = g05.build_scoring_view(request, value_limits=c31.VALUE_LIMITS).candidate_view()
    facts = {item["action_key"]: item for item in view["actions"] if item["is_legal"] is True}
    first = parent(view)
    second = g88(view)
    if first.get("status") != "SCORED" or second.get("status") != "SCORED":
        raise ValueError("评分状态漂移")
    first_entries = {item["action_key"]: item for item in first["entries"]}
    second_entries = {item["action_key"]: item for item in second["entries"]}
    if set(facts) != set(first_entries) or set(facts) != set(second_entries):
        raise ValueError("评分与规则合法动作身份不一致")
    first_top = g87.argmax({name: float(row["score"]) for name, row in first_entries.items()})
    second_top = g87.argmax({name: float(row["score"]) for name, row in second_entries.items()})
    if first_top != archived["parent_action"] or second_top != archived["candidate_action"]:
        raise ValueError("当前规则或旧评分与 G88 行为证据漂移")
    parent_fact, alt_fact = facts[first_top], facts[second_top]
    parent_trace = first_entries[first_top]["trace"]
    alt_trace = second_entries[second_top]["trace"]
    fail = []
    if not first_top.startswith("discard:") or not second_top.startswith("discard:"):
        fail.append("not_two_discards")
    wealth = observation.rule_state.wealth_god.code
    if first_top == "discard:" + wealth or second_top == "discard:" + wealth:
        fail.append("wealth_discard")
    if not any(meld.kind in ("chi", "peng")
               for meld in observation.melds[observation.seat]):
        fail.append("no_claimed_meld")
    p_std, a_std = (parent_fact.get("standard_shanten_after"),
                    alt_fact.get("standard_shanten_after"))
    p_w, a_w = width(parent_fact.get("standard_useful_tiles")), width(alt_fact.get("standard_useful_tiles"))
    if type(p_std) is not int or type(a_std) is not int or p_std != a_std:
        fail.append("standard_shanten")
    if p_w is None or a_w is None:
        fail.append("standard_width_unknown")
    elif not (a_w[0] > p_w[0] and a_w[1] > p_w[1]):
        fail.append("not_strict_wider")
    p_comb, a_comb = parent_fact.get("shanten_after"), alt_fact.get("shanten_after")
    p_cw, a_cw = width(parent_fact.get("useful_tiles")), width(alt_fact.get("useful_tiles"))
    if type(p_comb) is not int or type(a_comb) is not int or a_comb > p_comb:
        fail.append("combined_shanten")
    if p_cw is None or a_cw is None or a_cw[1] < p_cw[1]:
        fail.append("combined_capacity")
    if parent_fact.get("baotou_after") is True and alt_fact.get("baotou_after") is not True:
        fail.append("baotou_regression")
    p_risk, a_risk = parent_trace.get("risk_units"), alt_trace.get("risk_units")
    if (type(p_risk) not in (int, float) or type(a_risk) not in (int, float)
            or a_risk > p_risk or p_risk < 0 or a_risk < 0):
        fail.append("risk_increase_or_unknown")
    return {
        "key": list(key(archived)), "panel": archived["panel"], "room": archived["room"],
        "parent_action": first_top, "alternate_action": second_top,
        "strong_action": archived.get("strong_action"),
        "ordinary_shanten": p_std,
        "ordinary_width_parent": p_w, "ordinary_width_alternate": a_w,
        "combined_width_parent": p_cw, "combined_width_alternate": a_cw,
        "parent_risk_units": p_risk, "alternate_risk_units": a_risk,
        "old_top_when_changed": archived["old_top_when_changed"],
        "accepted": not fail, "veto": fail,
    }


def main() -> None:
    """结果盲扫描旧 G88 改选集合；现有证据不可覆盖。"""
    if OUT.exists():
        raise FileExistsError("G210 结果已存在，拒绝覆盖")
    source = json.loads(SOURCE.read_text(encoding="utf-8"))
    if source.get("schema") != "g88-post-claim-familiar-behavior/1" or not source["outcome_blind"]:
        raise ValueError("G88 输入身份不符")
    targets: dict[tuple[str, str, str], dict[tuple, dict]] = defaultdict(dict)
    for row in source["rows"]:
        if row["candidate_action"] == row["parent_action"]:
            continue
        group = (row["panel"], row.get("peer") or "", row["room"])
        if key(row) in targets[group]:
            raise ValueError("目标窗口重复")
        targets[group][key(row)] = row
    parent = c31.load_parent()
    g88, _ = c32.load_scorer("G88-POST-CLAIM-FAMILIAR-BIAS-V1.py")
    if g88 is None:
        raise ValueError("G88 评分器缺失")
    result = []
    file_hashes = {}
    for (panel, peer, room), wanted in sorted(targets.items()):
        path = ((_project_file(_PROJECT_ROOT, G61 / (peer + "--" + room) / "windows.json")) if panel == "g61"
                else (_project_file(_PROJECT_ROOT, G66 / room / "windows.json")))
        file_hashes[panel + "/" + peer + "/" + room] = digest(path)
        found = set()
        for window in json.loads(path.read_text(encoding="utf-8"))["windows"]:
            ident = key(window)
            if ident not in wanted:
                continue
            if ident in found:
                raise ValueError("官方窗口重复")
            found.add(ident)
            result.append(score_window(window, wanted[ident], parent, g88))
        if found != set(wanted):
            raise ValueError("官方窗口缺失: " + panel + "/" + room + " "
                             + repr(list(set(wanted) - found)[:2]))
    count = defaultdict(Counter)
    rooms = defaultdict(set)
    for row in result:
        panel = row["panel"]
        count[panel]["scanned_g88_changes"] += 1
        for name in row["veto"]:
            count[panel]["veto_" + name] += 1
        if not row["accepted"]:
            continue
        count[panel]["accepted"] += 1
        rooms[panel].add(row["room"])
        if panel == "g61":
            count[panel]["strong_match"] += row["alternate_action"] == row["strong_action"]
            count[panel]["old_g11_same"] += row["old_top_when_changed"]["g11"] == row["alternate_action"]
            count[panel]["old_risk0_same"] += row["old_top_when_changed"]["risk0"] == row["alternate_action"]
            count[panel]["old_both_different"] += all(
                action != row["alternate_action"] for action in row["old_top_when_changed"].values())
    summary = {panel: {**dict(sorted(count[panel].items())),
                       "accepted_rooms": len(rooms[panel])} for panel in ("g61", "g66")}
    passed = (summary["g61"].get("accepted", 0) >= 40
              and summary["g61"]["accepted_rooms"] >= 15
              and summary["g61"].get("old_both_different", 0) >= 20
              and summary["g66"].get("accepted", 0) >= 100
              and summary["g66"]["accepted_rooms"] >= 20)
    output = {
        "schema": "g210-post-claim-guarded-familiar-preflight/1",
        "outcome_blind": True, "behavior_gate_pass": passed,
        "input_sha256": {
            "g88_behavior": digest(SOURCE),
            "parent_source": sha256(c31.R18_INTEGRATED_POSITIVE_V2_SOURCE.encode()).hexdigest(),
            "g88_source": digest(_project_file(_PROJECT_ROOT, HERE / "candidates/G88-POST-CLAIM-FAMILIAR-BIAS-V1.py")),
            "script": digest(Path(__file__)),
            "prereg": digest(_project_file(_PROJECT_ROOT, HERE / "G210-POST-CLAIM-GUARDED-FAMILIAR-PREFLIGHT-2026-09-29.md")),
        },
        "official_window_sha256": file_hashes, "summary": summary,
        "rows": result,
        "boundary": "只读合法行为及旧动作去重；既有强手牌谱和旧桌赛不得作为候选净收益。",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(output, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                   encoding="utf-8")
    print(json.dumps({"summary": summary, "behavior_gate_pass": passed}, ensure_ascii=False))


if __name__ == "__main__":
    main()
