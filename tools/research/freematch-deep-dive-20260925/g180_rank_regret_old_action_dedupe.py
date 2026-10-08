#!/usr/bin/env python3
"""G180：在同一冻结官方窗调用 G168/G171 原选择器核精确改弃重合。"""

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

from collections import Counter
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import g11_cross_family_action_atlas as atlas
import g11_longitudinal_route_audit as g11
import g168_zero_white_first_width_policy as g168
import g171_pareto_width_policy as g171


HERE = Path(__file__).resolve().parent
PLAN = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/G180-RANK-REGRET-OLD-ACTION-DEDUPE-PREREG-2026-09-28.md')
G179 = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g179-rank-regret-core-reach-20260928/result.json')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g180-rank-regret-old-action-dedupe-20260928/result.json')


def sha(path: Path) -> str:
    """绑定已冻结行为、旧选择器及本程序源码。"""

    return hashlib.sha256(path.read_bytes()).hexdigest()


def _facts(raw: dict) -> SimpleNamespace:
    """将官方审计 JSON 还原为两个旧选择器实际读取的生产规则事实。"""

    values = {}
    for field in ("standard_shanten_after", "shanten_after", "seven_pairs_shanten_after"):
        values[field] = raw.get(field)
    for field in ("standard_useful_tiles", "useful_tiles"):
        entries = raw.get(field)
        values[field] = (None if entries is None else
                         tuple(SimpleNamespace(**entry) for entry in entries))
    return SimpleNamespace(**values)


def _request_plan(row: dict) -> tuple[SimpleNamespace, SimpleNamespace]:
    """仅重建 G168/G171 的读取投影；零白门清事实由核心入口保证。"""

    if row["white_count"] != 0 or row["own_melds"] != 0:
        raise ValueError("G180 目标不再零白门清")
    parent = row["parent_action"]
    legal = row["legal"]
    if parent not in legal or set(legal) != set(row["scores"]):
        raise ValueError("G180 冻结合法候选与原评分动作集不一致")
    if len(legal) != len(set(legal)):
        raise ValueError("G180 重复合法动作")
    order = [parent, *sorted(set(legal) - {parent})]
    request = SimpleNamespace(
        window_key=SimpleNamespace(phase=SimpleNamespace(value="draw")),
        rejected_attempts=(),
        observation=SimpleNamespace(
            seat=row["seat"], my_hand=(), drawn_tile=None,
            melds=tuple(() for _ in range(4))),
        rules=SimpleNamespace(legal_candidates=tuple(
            SimpleNamespace(action_key=key, facts=_facts(legal[key])) for key in order)))
    plan = SimpleNamespace(candidates=tuple(
        SimpleNamespace(action_key=key,
                        score_trace={"trace_schema": "sitin-action-score-trace/1",
                                     "detail": row["traces"].get(key, {})})
        for key in order))
    return request, plan


def _key(row: dict) -> tuple:
    """官方窗口身份，防止把不同座位或摸打混到同一个样本。"""

    return (row["game_id"], row["round_no"], row["seat"], row["trigger_seq"])


def main() -> None:
    """结果盲地核对首次改弃与两个旧选择器的同动作比例。"""

    if OUT.exists():
        raise FileExistsError("G180 结果已存在，拒绝覆盖")
    prior = json.loads(G179.read_text(encoding="utf-8"))
    if (prior["schema"] != "g179-rank-regret-core-reach/1"
            or prior["core_windows"] != 363
            or prior["counts"]["strict_wider_changes"] != 134):
        raise ValueError("G179 冻结行为身份漂移")
    by_hand = {}
    for item in prior["rows"]:
        if not (item.get("strict_wider") or item.get("selected_other_change")):
            continue
        hand = (item["game_id"], item["round_no"], item["seat"])
        if hand not in by_hand or item["trigger_seq"] < by_hand[hand]["trigger_seq"]:
            by_hand[hand] = item
    first_wider = { _key(item): item for item in by_hand.values() if item["strict_wider"] }
    if len(first_wider) != 116:
        raise ValueError(f"G180 首次严格宽面改弃数漂移：{len(first_wider)}")
    first_core = {}
    for item in prior["rows"]:
        hand = (item["game_id"], item["round_no"], item["seat"])
        if hand not in first_core or item["trigger_seq"] < first_core[hand]["trigger_seq"]:
            first_core[hand] = item
    first_core_keys = {_key(item) for item in first_core.values()}

    frozen = json.loads(atlas.FROZEN.read_text(encoding="utf-8"))
    complete = atlas._complete_ids()
    if len(complete) != 909:
        raise ValueError("G180 冻结完整桌计数漂移")
    rows, coverage = g11._draw_rows(complete, frozen)
    if coverage["accepted_normal_draw_discards"] != 55170:
        raise ValueError("G180 冻结正常弃牌计数漂移")
    records = {_key(row): row for row in rows if _key(row) in first_wider}
    if set(records) != set(first_wider):
        raise ValueError("G180 首次宽面目标窗口无法逐个复原")
    output = []
    for key, observed in first_wider.items():
        row = records[key]
        if (row["room_id"] != observed["room_id"] or
                row["parent_action"] != observed["parent"] or
                observed["choice"] not in row["legal"]):
            raise ValueError("G180 官方父代/合法目标身份漂移")
        request, plan = _request_plan(row)
        old168, _, consumed168 = g168.select(request, plan)
        old171, _, consumed171 = g171.select(request, plan)
        old168 = old168 or observed["parent"]
        old171 = old171 or observed["parent"]
        unique = observed["choice"] not in (old168, old171)
        output.append({"room_id": row["room_id"], "game_id": row["game_id"],
                       "round_no": row["round_no"], "seat": row["seat"],
                       "trigger_seq": row["trigger_seq"],
                       "first_core_in_hand": key in first_core_keys,
                       "parent": observed["parent"], "g179": observed["choice"],
                       "g168": old168, "g171": old171,
                       "g168_consumed": consumed168, "g171_consumed": consumed171,
                       "same_g168": observed["choice"] == old168,
                       "same_g171": observed["choice"] == old171,
                       "different_both": unique})
    output.sort(key=lambda item: (item["room_id"], item["game_id"],
                                  item["round_no"], item["seat"], item["trigger_seq"]))
    counts = Counter()
    for row in output:
        counts["first_wider_hands"] += 1
        for flag in ("same_g168", "same_g171", "different_both", "first_core_in_hand"):
            counts[flag] += int(row[flag])
        counts["same_either"] += int(not row["different_both"])
        counts["different_both_first_core"] += int(row["different_both"]
                                                    and row["first_core_in_hand"])
    unique = [row for row in output if row["different_both"]]
    scopes = {"tables": len({row["game_id"] for row in unique}),
              "rooms": len({row["room_id"] for row in unique})}
    gate = len(unique) >= 30 and scopes["tables"] >= 20 and scopes["rooms"] >= 12
    payload = {"schema": "g180-rank-regret-old-action-dedupe/1",
               "outcome_blind": True,
               "source_sha256": {
                   "plan": sha(PLAN), "script": sha(Path(__file__)),
                   "g179": sha(G179), "g168_selector": sha(Path(g168.__file__)),
                   "g171_selector": sha(Path(g171.__file__)),
                   "frozen_rooms": sha(atlas.FROZEN)},
               "counts": dict(sorted(counts.items())),
               "different_both_scopes": scopes,
               "preregistered_novel_action_gate_pass": gate,
               "rows": output,
               "boundary": "只核同一父代窗口旧选择器的精确动作，尚未复原旧包装器整手消费、P28 叶程序或积分收益。"}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                   encoding="utf-8")
    print(json.dumps({"counts": payload["counts"], "scopes": scopes,
                      "gate": gate}, ensure_ascii=False, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
