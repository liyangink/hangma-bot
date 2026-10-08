#!/usr/bin/env python3
"""G106：在冻结可见弃牌对上枚举局部条件鸣牌机会，不预测对手动作。"""

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

import argparse
from collections import Counter, defaultdict
from dataclasses import replace
import gzip
import hashlib
import json
from pathlib import Path

import c31_action_layer_gap as c31
import g52_shared_horizon as g52
from hangma_bot.hangma import action_families, progression
from hangma_bot.hangma.candidate_facts import FactsAnalysisError, _remaining
from hangma_bot.hangma.engine import _build_context
from hangma_bot.hangma.interface import ValueAnalysisLimits
from hangma_bot.hangma.internal_types import TILE_ORDER, counts_from_tiles
from hangma_bot.hangma.public_tile_counts import count_public_tiles
from hangma_bot.kernel.actions import Chi, Discard, Gang, Peng, Tile
from hangma_bot.kernel.observation import PlayerObservation, PublicDiscard
from hangma_bot.kernel.serialization import observation_from_json


HERE = Path(__file__).resolve().parent
SOURCE = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g101-new-free-wider-route-20260928/selection')
PREREG = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/G106-LOCAL-CLAIM-SURFACE-PREREG-2026-09-28.md')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g106-local-claim-surface-20260928')
G102_ROWS = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g102-white-arrival-fan-20260928/rows.jsonl.gz')
LIMITS = ValueAnalysisLimits(max_expansions=8192, max_routes_per_candidate=512)


def sha(path: Path) -> str:
    """绑定冻结选择、实验合同、程序和结果的原始字节。"""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def root_observation(observation: PlayerObservation, key: str) -> PlayerObservation:
    """仅推进一个已合法非白弃牌；爆头/链由生产规则计算。"""
    if observation.rule_state.catch_play or observation.rule_state.chain_count != 0:
        raise ValueError("G106 固定窗口的抓打圈或动作链非零")
    if not key.startswith("discard:") or key == "discard:白":
        raise ValueError("G106 根必须是非白弃牌")
    code = key.split(":", 1)[1]
    seat = observation.seat
    root = g52._drop(_build_context(observation).full_hand(), code)
    melds = len(observation.melds[seat])
    chain, piao = progression.chain_after_action(
        observation.rule_state.chain_count, observation.chain_piao,
        observation.rule_state.baotou, Discard(Tile(code)),
    )
    if (chain, piao) != (0, 0):
        raise ValueError("非白根弃牌没有断链")
    rivers = list(observation.discards)
    rivers[seat] = rivers[seat] + (Tile(code),)
    counts = list(observation.hand_counts)
    counts[seat] = len(root)
    return replace(
        observation,
        phase="draw", turn_seat=(seat + 1) % 4,
        responding_seats=(), my_hand=root, drawn_tile=None,
        discards=tuple(rivers), hand_counts=tuple(counts),
        last_discard=PublicDiscard(seat, Tile(code), observation.snapshot_seq + 1),
        rule_state=replace(
            observation.rule_state,
            baotou=progression.baotou_after_discard(root, melds),
            chain_count=chain, catch_play=False, catch_play_owner_seat=None,
        ),
        chain_piao=piao, public_history=(), consumed_seq=None,
    )


def response_observation(root: PlayerObservation, discarder: int,
                         trigger: str, phase: str) -> PlayerObservation:
    """构造独立局部响应条件；不宣称中间他家行动已完整模拟。"""
    peng, chi = c31.C23.window_members(discarder, trigger, None)
    members = peng if phase == "response_peng" else chi
    if root.seat not in members:
        raise ValueError("本人不在生产定义的响应成员中")
    rivers = list(root.discards)
    rivers[discarder] = rivers[discarder] + (Tile(trigger),)
    seq = root.snapshot_seq + 3
    return replace(
        root, phase=phase, turn_seat=discarder,
        responding_seats=tuple(members), discards=tuple(rivers),
        last_discard=PublicDiscard(discarder, Tile(trigger), seq),
        remaining_tile_count=root.remaining_tile_count - 1,
        snapshot_seq=seq, consumed_seq=None,
    )


def route_summary(candidate, seat: int) -> dict:
    """只读生产一次自摸条件胡；吃碰按全部合法跟打分别记账。"""
    facts = candidate.facts
    value = candidate.value_facts
    if value is None or value.coverage.value != "complete":
        raise ValueError("生产条件价值事实不完整")
    if facts is None or facts.completeness.value != "complete":
        raise ValueError("生产牌效事实不完整")
    action = candidate.action
    if isinstance(action, (Chi, Peng)):
        branches = facts.followup_branches
        if not branches or any(b.support_remaining is None for b in branches):
            raise ValueError("吃碰后的合法跟打分支不完整")
        branch_codes = {branch.followup_discard for branch in branches}
        expected_kind = "normal"
    elif isinstance(action, Gang):
        branches = ()
        branch_codes = {None}
        expected_kind = "replacement"
    else:
        raise ValueError("G106 收到非鸣牌候选")
    if any(route.followup_discard not in branch_codes or
           route.conditions.draw_kind != expected_kind for route in value.routes):
        raise ValueError("条件胡路线和合法跟打/补牌种类不一致")
    capacity_by_branch: dict[str | None, Counter] = defaultdict(Counter)
    for route in value.routes:
        settlement = route.conditional_settlement
        if settlement.fan < 1 or settlement.score_delta[seat] <= 0:
            raise ValueError("条件胡结算非本人正收入")
        key = "high" if settlement.fan >= 2 else "plain"
        for useful in route.useful_tiles:
            if not 0 <= useful.remaining_estimate <= 4:
                raise ValueError("公开未见容量越界")
            capacity_by_branch[route.followup_discard][key] += useful.remaining_estimate
    return {
        "action": candidate.action_key,
        "kind": "chi" if isinstance(action, Chi) else
                "peng" if isinstance(action, Peng) else "gang",
        "followup_count": len(branches),
        "best_standard_shanten": min(
            (branch.standard_shanten_after for branch in branches
             if branch.standard_shanten_after is not None), default=None,
        ),
        "any_plain": any(item["plain"] > 0 for item in capacity_by_branch.values()),
        "any_high": any(item["high"] > 0 for item in capacity_by_branch.values()),
        "max_plain_capacity": max((item["plain"] for item in capacity_by_branch.values()), default=0),
        "max_high_capacity": max((item["high"] for item in capacity_by_branch.values()), default=0),
    }


def arm_surface(observation: PlayerObservation, key: str) -> dict:
    """每个牌码、座位、响应阶段只衡量条件上存在的合法选择。"""
    root = root_observation(observation, key)
    if root.remaining_tile_count is None or root.remaining_tile_count <= 20:
        raise ValueError("没有可证明的下一次正常摸牌")
    public = count_public_tiles(root)
    own = counts_from_tiles(root.my_hand)
    entries = []
    unknown = Counter()
    for trigger in TILE_ORDER:
        if trigger == "白":
            continue  # 官方白板弃牌不打开吃碰/明杠窗口。
        try:
            physical_upper = _remaining(trigger, own, public, {})
        except FactsAnalysisError:
            unknown["public_count_unknown"] += 1
            continue
        if physical_upper <= 0:
            continue
        for discarder in range(4):
            if discarder == root.seat:
                continue
            for phase in ("response_peng", "response_chi"):
                members = c31.C23.window_members(discarder, trigger, None)
                if root.seat not in (members[0] if phase == "response_peng" else members[1]):
                    continue
                response = response_observation(root, discarder, trigger, phase)
                context = _build_context(response)
                if phase == "response_peng":
                    possible = (action_families.peng_candidates(context).candidates +
                                action_families.gang_candidates(context).candidates)
                else:
                    possible = action_families.chi_candidates(context).candidates
                if not possible:
                    continue
                analysis = c31.RULES.analyze(response, value_limits=LIMITS)
                candidates = {item.action_key: item for item in analysis.legal_candidates}
                for preliminary in possible:
                    candidate = candidates.get(preliminary.action_key)
                    if candidate is None:
                        raise ValueError("生产动作族与完整规则分析合法集合不一致")
                    try:
                        route = route_summary(candidate, root.seat)
                    except ValueError as exc:
                        unknown[type(exc).__name__ + ": " + str(exc)] += 1
                        continue
                    entries.append({
                        "trigger_code": trigger, "trigger_physical_upper": physical_upper,
                        "discarder_offset": (discarder - root.seat) % 4,
                        "phase": phase, **route,
                    })
    if unknown:
        raise ValueError("局部响应机会含未知事实：" + repr(dict(unknown)))
    return {"action": key, "entries": entries}


def compare(row: dict) -> dict:
    """同一当前可见观察分别评估父代与备选的局部机会。"""
    obs = observation_from_json(row["observation"])
    legal = {item.action_key for item in c31.RULES.analyze(obs).legal_candidates}
    if row["parent_action"] not in legal or row["alternate_action"] not in legal:
        raise ValueError("冻结根弃牌不在生产合法动作中")
    arms = {name: arm_surface(obs, row[name + "_action"])
            for name in ("parent", "alternate")}
    def opportunities(name: str, field: str) -> set[tuple]:
        return {(entry["trigger_code"], entry["discarder_offset"], entry["kind"])
                for entry in arms[name]["entries"] if entry[field]}
    delta = {}
    for field in ("any_plain", "any_high"):
        parent = opportunities("parent", field)
        alternate = opportunities("alternate", field)
        delta[field] = {
            "parent_only": sorted(parent - alternate),
            "alternate_only": sorted(alternate - parent),
            "shared": len(parent & alternate),
        }
    return {"key": row["key"], "white_before": row["white_before"],
            "parent_action": row["parent_action"],
            "alternate_action": row["alternate_action"],
            "arms": arms, "delta": delta, "status": "complete"}


def main() -> None:
    """全量分析冻结输入；试运行只读前几行、不写冻结输出。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()
    rows_path = _project_file(_PROJECT_ROOT, SOURCE / "rows.jsonl.gz")
    source = json.loads((_project_file(_PROJECT_ROOT, SOURCE / "result.json")).read_text(encoding="utf-8"))
    if source["counts"]["target_windows"] != 203 or source["outcome_labels_opened"] is not False:
        raise ValueError("G101 冻结选择集身份漂移")
    with gzip.open(rows_path, "rt", encoding="utf-8") as stream:
        rows = [json.loads(line) for line in stream]
    if len(rows) != 203:
        raise ValueError("G101 逐窗数量漂移")
    if args.limit:
        rows = rows[:args.limit]
    elif OUT.exists():
        raise FileExistsError("G106 冻结输出已存在，拒绝覆盖")
    result_rows = []
    counts = Counter()
    rooms: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        try:
            result = compare(row)
            counts["complete"] += 1
            for field in ("any_plain", "any_high"):
                direction = result["delta"][field]
                for label in ("parent_only", "alternate_only"):
                    if direction[label]:
                        counts[field + "/" + label + "/windows"] += 1
                        rooms[field + "/" + label].add(row["key"][0])
        except (ValueError, TypeError) as exc:
            result = {"key": row["key"], "status": "unavailable",
                      "reason": type(exc).__name__ + ": " + str(exc)[:250]}
            counts["unavailable"] += 1
            counts["unavailable/" + result["reason"]] += 1
        result_rows.append(result)
    high_rows = [row for row in result_rows if row["status"] == "complete" and
                 (row["delta"]["any_high"]["parent_only"] or
                  row["delta"]["any_high"]["alternate_only"])]
    first_per_hand = {}
    for row in result_rows:
        first_per_hand.setdefault(tuple(row["key"][:3]), row)
    first_high = [row for row in first_per_hand.values() if row in high_rows]
    with gzip.open(G102_ROWS, "rt", encoding="utf-8") as stream:
        old_rows = [json.loads(line) for line in stream]
    old_high = {
        tuple(row["key"]) for row in old_rows
        if row["status"] == "complete" and
        row["delta"]["highfan_preferred"]["special_capacity"] != 0
    }
    if len(old_rows) != 203 or len(old_high) != 2:
        raise ValueError("G102 冻结两摸高番分歧数量漂移")
    high_keys = {tuple(row["key"]) for row in high_rows}
    summary = {
        "schema": "g106-local-claim-surface/1", "exploratory": True,
        "outcome_labels_read": False, "windows": len(rows),
        "input_sha256": {"g101_selection": sha(_project_file(_PROJECT_ROOT, SOURCE / "result.json")),
                         "g101_rows": sha(rows_path), "g102_rows": sha(G102_ROWS),
                         "prereg": sha(PREREG),
                         "script": sha(Path(__file__))},
        "counts": dict(sorted(counts.items())),
        "room_coverage": {key: len(value) for key, value in sorted(rooms.items())},
        "high_opportunity_difference": {
            "windows": len(high_rows),
            "rooms": len({row["key"][0] for row in high_rows}),
            "first_per_hand_windows": len(first_high),
            "first_per_hand_rooms": len({row["key"][0] for row in first_high}),
            "root_white_count": dict(sorted(Counter(
                str(min(2, row["white_before"])) for row in high_rows
            ).items())),
            "also_distinguished_by_g102": len(high_keys & old_high),
            "new_beyond_g102": len(high_keys - old_high),
        },
        "boundary": "局部独立响应条件，非可达全事件链；物理上界非概率；不可作收益标签。",
    }
    if args.limit:
        print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
        return
    OUT.mkdir(parents=True)
    (_project_file(_PROJECT_ROOT, OUT / "result.json")).write_text(
        json.dumps(summary, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    body = "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n"
                   for row in result_rows)
    (_project_file(_PROJECT_ROOT, OUT / "rows.jsonl.gz")).write_bytes(gzip.compress(body.encode(), compresslevel=9, mtime=0))
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
