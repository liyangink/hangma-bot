#!/usr/bin/env python3
"""G204：冻结多白宽进张根的两次本人摸牌与独立鸣牌机会。"""

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
import signal
import time

import c31_action_layer_gap as c31
import g106_local_claim_surface as g106
import g196_three_draw_competing_route_pilot as g196
import g201_multiwhite_near_ready_route as g201
import g201_multiwhite_near_ready_select as source
import g203_future_catch_play_reach as g203
from hangma_bot.hangma import progression
from hangma_bot.hangma.internal_types import TILE_INDEX, TILE_ORDER
from hangma_bot.kernel.actions import Tile


HERE = Path(__file__).resolve().parent
PLAN = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/G204-MULTIWHITE-TWO-ACTION-CLAIM-PREREG-2026-09-29.md')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g204-multiwhite-two-action-claim-20260929/result.json')
SURVIVAL = (1.0, 0.5)
MAX_CLAIM_SECONDS = 30.0


def digest(path: Path) -> str:
    """绑定输入、事前方案和执行器的原始字节。"""

    return sha256(path.read_bytes()).hexdigest()


def identity(row: dict) -> tuple:
    """同一官方正常摸打窗口的房／桌／单局／事件／本人座位。"""

    return (row["room_id"], row["game_id"], row["round_no"],
            row["trigger_seq"], row["seat"])


def frozen_rows() -> list[dict]:
    """只用 G203 事前资格选根，从原审计恢复行动前观察并复核动作。"""

    atlas = json.loads(g203.OUT.read_text(encoding="utf-8"))
    if atlas.get("schema") != "g203-future-catch-play-reach/1":
        raise ValueError("G204 G203 冻结来源版本不符")
    targets = {identity(row): row for row in atlas["rows"] if row["g201_like"]}
    if len(targets) != 29 or len({key[0] for key in targets}) != 25:
        raise ValueError("G204 预设 29 窗／25 房主层漂移")
    gold = json.loads(source.OUT.read_text(encoding="utf-8"))
    gold_keys = {identity(row) for row in gold["selected"]}
    if len(gold_keys) != 8 or not gold_keys <= targets.keys():
        raise ValueError("G204 G201 八窗金例缺失")
    by_room = defaultdict(dict)
    for key, row in targets.items():
        by_room[key[0]][key] = row
    recovered = {}
    for room in sorted(by_room):
        audit = source.g189.atlas.source.ROOT / atlas["source_rooms"][room]["audit_dir"]
        decisions = (audit / "participants" / source.g189.atlas.source.ACTOR
                     / "decisions.jsonl")
        if decisions.stat().st_size != atlas["source_rooms"][room]["decision_bytes"]:
            raise ValueError("G204 原始已接受动作审计字节数漂移")
        accepted = source.g189.atlas.source._accepted(decisions)
        for context, raw, plan in source.g189.atlas.source.screen._iter_decisions(audit):
            o = raw.get("observation") or {}
            key = (room, context.get("game_id"), context.get("round_no"),
                   context.get("trigger_seq"), o.get("seat"))
            if key not in by_room[room]:
                continue
            if key in recovered:
                raise ValueError("G204 同一根重复审计")
            ranked = sorted(plan.get("candidates") or [],
                            key=lambda item: item.get("rank", 10**9))
            if not ranked:
                raise ValueError("G204 父代候选评分缺失")
            parent = ranked[0].get("action_key")
            old = by_room[room][key]
            if (parent != old["parent_action"]
                    or accepted.get(context.get("decision_id")) != parent):
                raise ValueError("G204 冻结父代动作未获官方接受")
            selected = source.candidate(
                {"room_id": room, "game_id": key[1], "round_no": key[2],
                 "trigger_seq": key[3]}, raw, ranked, parent,
            )
            if (selected is None or selected["alternate_action"] != old["alternate_action"]
                    or selected["white_before"] != old["white_before"]
                    or selected["seat"] != key[4]):
                raise ValueError("G204 G201 结果盲备选或当前规则事实漂移")
            if (o["rule_state"]["chain_count"] != 0
                    or o["rule_state"]["catch_play"]):
                raise ValueError("G204 预检的无链／无抓打边界漂移")
            # G201 冻结文件经 JSON 保存，容量对是 list；候选函数刚算出的
            # 同值对象为 tuple。恢复同一序列化形态后才能逐字段对账。
            selected = json.loads(json.dumps(selected, ensure_ascii=False))
            recovered[key] = selected
    if recovered.keys() != targets.keys():
        raise ValueError("G204 原始审计未重建全部冻结主层根")
    return [recovered[key] for key in sorted(recovered)]


class TwoActionSearch(g196.RouteSearch):
    """两次本人正常摸牌的生产合法路径；第一摸可胡也可继续。"""

    def __init__(self, observation, config, root_action: str) -> None:
        super().__init__(observation, config, root_action)
        self.memo_second: dict[tuple, g196.Value] = {}

    def second(self, waiting, unseen, baotou, chain, piao) -> g196.Value:
        """第二次本人摸牌仅可胡即结算，不伪造第三次到达。"""

        key = (waiting, unseen, baotou, chain, piao)
        if key in self.memo_second:
            return self.memo_second[key]
        total = sum(unseen)
        if total <= 0:
            raise ValueError("G204 第二摸公开未知容量为空")
        value = g196.Value()
        for index, capacity in enumerate(unseen):
            if capacity <= 0:
                continue
            terminal = self._win(waiting, TILE_ORDER[index], baotou=baotou,
                                 chain=chain, piao=piao, depth=2)
            if terminal is not None:
                value = value.plus(terminal.scaled(capacity / total))
        self.memo_second[key] = value
        return value

    def branches(self) -> list[tuple[int, g196.Value | None, g196.Value]]:
        """逐首摸牌码保存立即胡与最佳合法继续，便于权重敏感性重算。"""

        if sum(self.unseen) < 2:
            raise ValueError("G204 未知容量不足两次本人条件摸牌")
        output = []
        for index, capacity in enumerate(self.unseen):
            if capacity <= 0:
                continue
            code = TILE_ORDER[index]
            terminal = self._win(self.root, code, baotou=self.root_baotou,
                                 chain=self.root_chain, piao=self.root_piao, depth=1)
            full = self.root + (Tile(code),)
            drawn_baotou = progression.baotou_after_draw(
                self.root_baotou, self.root, self.meld_count, Tile(code),
                replacement=False,
            )
            child_unseen = g196._capacity_after(self.unseen, code)
            options = []
            for discard in self._legal(self.root, code, restricted=False):
                self.legal_leaf_count += 1
                self._check_budget()
                next_hand = g196._drop(full, discard)
                next_chain, next_piao = progression.chain_after_discard(
                    self.root_chain, self.root_piao, drawn_baotou, Tile(discard),
                )
                next_baotou = progression.baotou_after_discard(
                    next_hand, self.meld_count,
                )
                options.append((self.second(next_hand, child_unseen,
                                            next_baotou, next_chain, next_piao),
                                discard))
            if not options:
                raise ValueError("G204 第一摸没有合法后继弃牌")
            continuation = max(options, key=lambda item: (
                item[0].total, -TILE_INDEX[item[1]]))[0]
            output.append((capacity, terminal, continuation))
        return output

    def value(self, branches, survival: float) -> tuple[g196.Value, int]:
        """仅改变第二摸到达敏感性权重；不称它为动作因果概率。"""

        if survival not in SURVIVAL:
            raise ValueError("G204 第二摸权重不在预设包络")
        total = sum(capacity for capacity, _, _ in branches)
        value = g196.Value()
        continue_over_hu = 0
        for capacity, terminal, continuation in branches:
            continue_value = continuation.scaled(survival)
            if terminal is not None and terminal.total >= continue_value.total - 1e-12:
                chosen = terminal
            else:
                chosen = continue_value
                if terminal is not None:
                    continue_over_hu += 1
            value = value.plus(chosen.scaled(capacity / total))
        return value, continue_over_hu


class ClaimLimitExceeded(Exception):
    """单臂局部响应机会超过固定离线计算期限。"""


def claim_surface(observation, action_key: str) -> dict:
    """复用 G106 生产规则局部响应探针，超时整臂弃权。"""

    def alarm(_signum, _frame):
        raise ClaimLimitExceeded("单臂局部鸣牌机会超过 30 秒")

    previous = signal.getsignal(signal.SIGALRM)
    signal.signal(signal.SIGALRM, alarm)
    signal.setitimer(signal.ITIMER_REAL, MAX_CLAIM_SECONDS)
    try:
        return g106.arm_surface(observation, action_key)
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


def opportunity(surface: dict, field: str) -> set[tuple]:
    """只保留独立对手座位、触发牌码与鸣牌种类的机会身份。"""

    return {(entry["trigger_code"], entry["discarder_offset"], entry["kind"])
            for entry in surface["entries"] if entry[field]}


def main() -> None:
    """逐窗先完成两臂两摸，再算独立鸣牌面；任何截断不判优。"""

    if OUT.exists():
        raise FileExistsError("G204 结果已存在，拒绝覆盖")
    rows = frozen_rows()
    output = []
    for index, row in enumerate(rows, 1):
        key = identity(row)
        result = {"room_id": key[0], "game_id": key[1], "round_no": key[2],
                  "trigger_seq": key[3], "seat": key[4],
                  "white_before": row["white_before"],
                  "parent_action": row["parent_action"],
                  "alternate_action": row["alternate_action"],
                  "observation_sha256": row["observation_sha256"], "arms": {}}
        try:
            observation = g201.observe(row)
            legal = g201.check_rules(row, observation)
            for name in ("parent", "alternate"):
                action_key = row[name + "_action"]
                started = time.perf_counter()
                search = TwoActionSearch(observation, c31.RULE_CONFIG, action_key)
                first_hu_capacity = g201.first_hu_check(search, legal[action_key])
                branches = search.branches()
                values = {}
                for survival in SURVIVAL:
                    value, continued = search.value(branches, survival)
                    values[str(survival)] = {"value": value.json(),
                                             "continue_over_hu_codes": continued}
                result["arms"][name] = {
                    "first_hu_public_capacity": first_hu_capacity,
                    "two_draw": values,
                    "draw_elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
                    "legal_leaf_count": search.legal_leaf_count,
                    "memo_second_states": len(search.memo_second),
                }
            result["draw_status"] = "complete"
        except (g196.RouteLimitExceeded, ValueError) as exc:
            result["draw_status"] = "abstained"
            result["draw_reason"] = type(exc).__name__ + ": " + str(exc)
        if result["draw_status"] == "complete":
            try:
                surfaces = {}
                for name in ("parent", "alternate"):
                    started = time.perf_counter()
                    surfaces[name] = claim_surface(observation, row[name + "_action"])
                    result["arms"][name]["claim_elapsed_ms"] = round(
                        (time.perf_counter() - started) * 1000, 3)
                    result["arms"][name]["claim_entries"] = len(surfaces[name]["entries"])
                result["claim_delta"] = {}
                for field in ("any_plain", "any_high"):
                    parent = opportunity(surfaces["parent"], field)
                    alternate = opportunity(surfaces["alternate"], field)
                    result["claim_delta"][field] = {
                        "parent_only": sorted(parent - alternate),
                        "alternate_only": sorted(alternate - parent),
                        "shared": len(parent & alternate),
                    }
                result["claim_status"] = "complete"
            except (ClaimLimitExceeded, ValueError) as exc:
                result["claim_status"] = "abstained"
                result["claim_reason"] = type(exc).__name__ + ": " + str(exc)
        else:
            result["claim_status"] = "not_attempted"
        output.append(result)
        print(json.dumps({"window": index, "total": len(rows), "room": key[0],
                          "draw": result["draw_status"],
                          "claim": result["claim_status"]}, ensure_ascii=False), flush=True)
    complete = [row for row in output if row["draw_status"] == "complete"
                and row["claim_status"] == "complete"]
    consistent = []
    for row in complete:
        diffs = {}
        for survival in SURVIVAL:
            label = str(survival)
            parent = row["arms"]["parent"]["two_draw"][label]
            alternate = row["arms"]["alternate"]["two_draw"][label]
            diffs[label] = {
                "total": alternate["value"]["total"] - parent["value"]["total"],
                "plain": alternate["value"]["plain"] - parent["value"]["plain"],
                "special": alternate["value"]["special"] - parent["value"]["special"],
                "continue_over_hu_codes": (alternate["continue_over_hu_codes"]
                                           - parent["continue_over_hu_codes"]),
            }
        row["alternate_minus_parent"] = diffs
        if (all(diffs[str(s)]["total"] > 1e-9 and
                diffs[str(s)]["plain"] >= -1e-9 for s in SURVIVAL)
                and (any(diffs[str(s)]["continue_over_hu_codes"] != 0 for s in SURVIVAL)
                     or bool(row["claim_delta"]["any_high"]["alternate_only"]))):
            consistent.append(row)
    supporting_rooms = sorted({row["room_id"] for row in consistent})
    payload = {
        "schema": "g204-multiwhite-two-action-claim/1",
        "source_sha256": {"plan": digest(PLAN), "script": digest(Path(__file__)),
                          "g203_result": digest(g203.OUT),
                          "g201_selection": digest(source.OUT),
                          "g196_script": digest(Path(g196.__file__)),
                          "g106_script": digest(Path(g106.__file__))},
        "selected_count": len(rows), "draw_complete": sum(
            row["draw_status"] == "complete" for row in output),
        "claim_complete": sum(row["claim_status"] == "complete" for row in output),
        "supporting_rooms": supporting_rooms,
        "author_gate": len(supporting_rooms) >= 3,
        "rows": output,
        "boundary": "行动前公开未知池的两次本人正常摸牌与独立局部鸣牌机会；两者不相加，不含对手行动/先胡因果概率，不是赛事收益。",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True,
                              indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"selected": len(rows), "draw_complete": payload["draw_complete"],
                      "claim_complete": payload["claim_complete"],
                      "author_gate": payload["author_gate"],
                      "supporting_rooms": supporting_rooms}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
