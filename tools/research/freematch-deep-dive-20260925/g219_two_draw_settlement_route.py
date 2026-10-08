#!/usr/bin/env python3
"""G219：在未按价值筛选的官方同层窗口比较两摸互斥结算路线。"""

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
import time

import c31_action_layer_gap as c31
import g52_shared_horizon as g52
import g196_three_draw_competing_route_pilot as g196
import g204_multiwhite_two_action_claim as g204
import g217_two_step_natural_route_preflight as g217
from hangma_bot.application.audit_codec import candidate_value_facts_to_json
from hangma_bot.application.deadline import BudgetPolicy
from hangma_bot.hangma.internal_types import TILE_ORDER


HERE = Path(__file__).resolve().parent
PREREG = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/G219-TWO-DRAW-SETTLEMENT-ROUTE-PREREG-2026-09-29.md')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g219-two-draw-settlement-route-20260929/result.json')
MODES = ("restricted", "unrestricted")
WEIGHTS = (1.0, 0.5)
MAX_ALTERNATES = 6
EPS = 1e-9


def digest(path: Path) -> str:
    """绑定冻结官方窗、生产规则和执行器原始字节。"""
    return sha256(path.read_bytes()).hexdigest()


def selected_rows() -> list[dict]:
    """每房取固定顺序第三、第四个非白严格分歧，避开 G217 所用前两窗。"""
    data = json.loads(g217.SOURCE.read_text(encoding="utf-8"))
    if data["schema"] != "g87-post-claim-score-trace/1" or len(data["rows"]) != 1083:
        raise ValueError("G87 冻结母体漂移")
    rooms = defaultdict(list)
    for row in sorted(data["rows"], key=lambda item: (
            item["peer"], item["room"], item["game_id"],
            item["round_no"], item["draw_seq"])):
        if (row["peer"] in g217.PEERS
                and row["parent_action"].startswith("discard:")
                and row["strong_action"].startswith("discard:")
                and row["parent_action"] != "discard:白"
                and row["strong_action"] != "discard:白"):
            rooms[(row["peer"], row["room"])].append(row)
    if len(rooms) != 32 or any(len(value) < 4 for value in rooms.values()):
        raise ValueError("固定来源不足每房四个非白分歧")
    rows = [row for room in sorted(rooms) for row in rooms[room][2:4]]
    if len(rows) != 64 or {
            (row["peer"], row["room"], row["game_id"],
             row["round_no"], row["draw_seq"]) for row in rows
    } & {
            (row["peer"], row["room"], row["game_id"],
             row["round_no"], row["draw_seq"]) for row in g217.selected_rows()
    }:
        raise ValueError("G219 与 G217 开发窗重合")
    return rows


class ModeSearch(g204.TwoActionSearch):
    """复用 G204 两摸互斥终点，未来合法弃牌另取固定抓打包络。"""

    def __init__(self, observation, config, root_action: str,
                 *, restricted: bool) -> None:
        # G196 的父类只服务三摸先导，硬性要求墙余 >32；本量具只需要两摸。
        # 不改冻结 G196/G204 的源码或证据，按相同状态字段重新构造根。
        if config.you_cai_bi_kao:
            raise ValueError("有财必拷响开启时未来权威资格未知")
        if (observation.phase != "draw" or observation.turn_seat != observation.seat
                or type(observation.remaining_tile_count) is not int
                or observation.remaining_tile_count <= 20):
            raise ValueError("非本人正常摸牌窗或墙余不足两摸先导边界")
        if observation.chain_piao is None:
            raise ValueError("链内飘数未知")
        self.observation = observation
        self.config = config
        self.current = g196._build_context(observation)
        self.meld_count = len(observation.melds[observation.seat])
        if len(self.current.full_hand()) != 14 - 3 * self.meld_count:
            raise ValueError("动作前手牌张数与副露不符")
        if not root_action.startswith("discard:"):
            raise ValueError("先导只接受生产合法弃牌")
        self.root_action = root_action
        root_code = root_action.split(":", 1)[1]
        self.root = g196._drop(self.current.full_hand(), root_code)
        raw_unseen = g196.count_unseen_tiles(observation)
        if any(type(x) is not int or x < 0 for x in raw_unseen):
            raise ValueError("公开未知池不完整")
        self.unseen = tuple(raw_unseen)
        self.root_baotou = g196.progression.baotou_after_discard(
            self.root, self.meld_count)
        self.root_chain, self.root_piao = g196.progression.chain_after_action(
            observation.rule_state.chain_count, observation.chain_piao,
            observation.rule_state.baotou, g196.Discard(g196.Tile(root_code)))
        if self.root_piao is None:
            raise ValueError("根弃牌后飘数未知")
        self.started = time.perf_counter()
        self.legal_leaf_count = 0
        self.win_split_count = 0
        self.third_ready_count = 0
        self.memo_third = {}
        self.memo_second = {}
        self.future_restricted = restricted

    def _legal(self, waiting, draw_code, restricted):
        """G204 原工具只调用不受限包络；此处显式切换规则资格。"""
        del restricted
        return super()._legal(waiting, draw_code, self.future_restricted)


def first_hu_parity(search: ModeSearch, fact, seat: int) -> None:
    """第一次摸牌结算和公开容量逐码与生产价值事实完全相同。"""
    if fact.value_facts is None:
        raise ValueError("根弃牌缺生产一次摸牌价值事实")
    expected = g52._first_hu_routes(
        {"value_facts": candidate_value_facts_to_json(fact.value_facts)}, seat)
    actual = {}
    for index, capacity in enumerate(search.unseen):
        if capacity <= 0:
            continue
        code = TILE_ORDER[index]
        val = search._win(search.root, code, baotou=search.root_baotou,
                          chain=search.root_chain, piao=search.root_piao,
                          depth=1)
        if val is not None:
            actual[code] = (round(val.total), capacity)
    if actual != expected:
        raise ValueError("两摸量具第一次摸牌与生产价值事实不一致")


def shortlist(plan, legal: dict, parent_key: str, wealth: str) -> list[str]:
    """只按父代排序及可见一步容量选臂，不读强手实际弃牌。"""
    parent = legal[parent_key]
    shanten = parent.facts.standard_shanten_after
    same = []
    for ranked in plan.candidates[1:]:
        key = ranked.action_key
        fact = legal.get(key)
        if (key.startswith("discard:") and key != "discard:" + wealth
                and fact is not None and fact.facts is not None
                and fact.facts.standard_shanten_after == shanten
                and g217.candidate._width(fact) is not None):
            same.append(key)
    result = same[:MAX_ALTERNATES]
    if same:
        widest = max(same, key=lambda key: (
            g217.candidate._width(legal[key])[1],
            g217.candidate._width(legal[key])[0], -same.index(key)))
        if widest not in result:
            result.append(widest)
    return result


def one(row: dict, batch: dict, hashes: dict) -> dict:
    """同一可见窗口逐合法根完成两种包络与权重；失败整窗弃权。"""
    observation = g217._observation(row, batch["units"], hashes)
    request = g217.g87.request_for(observation)
    budget = BudgetPolicy().build(800.0, 3.0)
    plan = asyncio.run(g217.candidate.g210.parent_factory(None).choose(request, budget))
    parent = plan.candidates[0].action_key
    if parent != row["parent_action"]:
        raise ValueError("官方原窗的冻结 R18 首选漂移")
    legal = {item.action_key: item for item in request.rules.legal_candidates}
    if parent not in legal or legal[parent].facts is None:
        raise ValueError("父代首选无生产规则事实")
    wealth = observation.rule_state.wealth_god.code
    arms = [parent] + shortlist(plan, legal, parent, wealth)
    output = {"peer": row["peer"], "room": row["room"],
              "game_id": row["game_id"], "round_no": row["round_no"],
              "draw_seq": row["draw_seq"], "seat": row["seat"],
              "parent_action": parent, "strong_action": row["strong_action"],
              "wall_remaining": observation.remaining_tile_count,
              "white_before": row["white_before"],
              "shanten_after": legal[parent].facts.standard_shanten_after,
              "arms": {}, "status": "complete"}
    try:
        for key in arms:
            arm = {"width": g217.candidate._width(legal[key]), "modes": {}}
            for mode in MODES:
                started = time.perf_counter()
                search = ModeSearch(observation, c31.RULE_CONFIG, key,
                                    restricted=(mode == "restricted"))
                first_hu_parity(search, legal[key], observation.seat)
                branches = search.branches()
                values = {}
                for weight in WEIGHTS:
                    value, continued = search.value(branches, weight)
                    values[str(weight)] = {
                        "value": value.json(),
                        "continue_over_hu_codes": continued,
                    }
                arm["modes"][mode] = {
                    "values": values,
                    "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
                    "legal_leaf_count": search.legal_leaf_count,
                    "memo_second_states": len(search.memo_second),
                }
            output["arms"][key] = arm
        output["best"] = {}
        parent_width = output["arms"][parent]["width"]
        for mode in MODES:
            for weight in WEIGHTS:
                name = mode + "/" + str(weight)
                # 父代在同值时胜出；不能把数值噪声冒充真实改选。
                best = max(arms, key=lambda key: (
                    round(output["arms"][key]["modes"][mode]["values"][str(weight)]
                          ["value"]["total"], 9), -arms.index(key)))
                value = output["arms"][best]["modes"][mode]["values"][str(weight)]["value"]
                parent_value = output["arms"][parent]["modes"][mode]["values"][str(weight)]["value"]
                if value["total"] <= parent_value["total"] + EPS:
                    best = parent
                    value = parent_value
                width = output["arms"][best]["width"]
                output["best"][name] = {
                    "action": best, "total_gain": round(value["total"] - parent_value["total"], 9),
                    "plain_gain": round(value["plain"] - parent_value["plain"], 9),
                    "special_gain": round(value["special"] - parent_value["special"], 9),
                    "type_gain": width[0] - parent_width[0],
                    "capacity_gain": width[1] - parent_width[1],
                    "strict_static_wider": width[0] > parent_width[0]
                                           and width[1] > parent_width[1],
                }
    except (g196.RouteLimitExceeded, ValueError) as exc:
        output["status"] = "abstained"
        output["reason"] = type(exc).__name__ + ": " + str(exc)
        output.pop("best", None)
    return output


def summary(rows: list[dict]) -> dict:
    """同一房内多窗相关，只汇总独立房覆盖及情景稳健动作。"""
    complete = [row for row in rows if row["status"] == "complete"]
    counts = {}
    for mode in MODES:
        for weight in WEIGHTS:
            name = mode + "/" + str(weight)
            changed = [row for row in complete
                       if row["best"][name]["action"] != row["parent_action"]]
            counts[name] = {
                "changed_windows": len(changed),
                "changed_rooms": {peer: len({row["room"] for row in changed
                                            if row["peer"] == peer}) for peer in g217.PEERS},
                "non_static_wider": sum(not row["best"][name]["strict_static_wider"]
                                        for row in changed),
                "highfan_gain_positive": sum(row["best"][name]["special_gain"] > EPS
                                              for row in changed),
                "highfan_gain_negative": sum(row["best"][name]["special_gain"] < -EPS
                                              for row in changed),
            }
    stable = [row for row in complete if len({
        row["best"][mode + "/" + str(weight)]["action"]
        for mode in MODES for weight in WEIGHTS}) == 1
        and row["best"]["unrestricted/1.0"]["action"] != row["parent_action"]]
    novel = sum(not row["best"]["unrestricted/1.0"]["strict_static_wider"]
                for row in stable)
    stable_rooms = {peer: len({row["room"] for row in stable if row["peer"] == peer})
                    for peer in g217.PEERS}
    gate = (all(stable_rooms[peer] >= 8 for peer in g217.PEERS)
            and bool(stable) and novel / len(stable) >= 0.2)
    return {"windows": len(rows), "complete_windows": len(complete),
            "abstain_reasons": dict(sorted(Counter(row.get("reason") for row in rows
                                                  if row["status"] != "complete").items())),
            "scenarios": counts, "four_scenario_same_changed_windows": len(stable),
            "four_scenario_same_changed_rooms": stable_rooms,
            "four_scenario_non_static_wider": novel,
            "behavior_gate_pass": gate}


def main() -> None:
    """执行结果盲离线对账；只新写证据，不更动线上候选。"""
    if OUT.exists():
        raise FileExistsError(OUT)
    roots = selected_rows()
    batch = json.loads((g217.G61 / "result.json").read_text(encoding="utf-8"))
    hashes = {}
    rows = []
    for index, root in enumerate(roots, 1):
        rows.append(one(root, batch, hashes))
        if index % 8 == 0:
            print(json.dumps({"windows": index, "complete": sum(
                row["status"] == "complete" for row in rows)},
                ensure_ascii=False), flush=True)
    payload = {
        "schema": "g219-two-draw-settlement-route/1",
        "source_sha256": {
            "prereg": digest(PREREG), "script": digest(Path(__file__)),
            "g87": digest(g217.SOURCE),
            "g61": digest(g217.G61 / "result.json"),
            "g196": digest(_project_file(_PROJECT_ROOT, HERE / "g196_three_draw_competing_route_pilot.py")),
            "g204": digest(_project_file(_PROJECT_ROOT, HERE / "g204_multiwhite_two_action_claim.py")),
        },
        "source_room_sha256": hashes,
        "summary": summary(rows), "rows": rows,
        "boundary": "已见强手房的不同结果盲窗口；两次本人摸牌公开容量条件结算，尚未包含对手先胡、响应鸣牌或未来权威资格。非候选净收益。",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                   encoding="utf-8")
    print(json.dumps(payload["summary"], ensure_ascii=False, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
