#!/usr/bin/env python3
"""G197：在 G196 三摸量具中允许合法弃胡续行，核查高番路线遗漏。"""

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

from hashlib import sha256
import json
import math
from pathlib import Path
import time

import c31_action_layer_gap as c31
import g184_classic_highhand_shadow as g184
import g196_three_draw_competing_route_pilot as g196
from hangma_bot.hangma import progression
from hangma_bot.hangma.interface import WinDescription
from hangma_bot.hangma.internal_types import TILE_INDEX, TILE_ORDER
from hangma_bot.kernel.actions import Tile
from hangma_bot.policy.action_value_policy import build_scoring_view
from hangma_bot.policy.action_value_seeds import ActionValueScorer
from hangma_bot.policy.r18_integrated_positive_v2 import R18_INTEGRATED_POSITIVE_V2_SOURCE


HERE = Path(__file__).resolve().parent
PLAN = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/G197-OPTIONAL-HU-THREE-DRAW-PREREG-2026-09-29.md')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g197-optional-hu-three-draw-pilot-20260929/result.json')
CASES = ((1, 905, "discard:1b"), (2, 122, "discard:1b"),
         (3, 401, "discard:1t"), (1, 964, None))


def digest(path: Path) -> str:
    """读取原文摘要，防止复盘、预登记或量具静默改变。"""

    return sha256(path.read_bytes()).hexdigest()


class OptionalHuSearch(g196.RouteSearch):
    """未来合法可胡时，择优立即胡或继续弃牌；不改生产规则。"""

    def __init__(self, observation, config, root_action: str) -> None:
        super().__init__(observation, config, root_action)
        self.continue_over_hu = [0, 0]

    def _second_optional(self, waiting, unseen, baotou, chain, piao, restricted):
        """第二摸可胡也可合法弃牌；第三摸仍按 G196 终结。"""

        total = sum(unseen)
        if total <= 0:
            raise ValueError("第二摸公开未知池为空")
        value = g196.Value()
        for index, capacity in enumerate(unseen):
            if capacity <= 0:
                continue
            code = TILE_ORDER[index]
            terminal = self._win(waiting, code, baotou=baotou,
                                 chain=chain, piao=piao, depth=2)
            full = waiting + (Tile(code),)
            drawn_baotou = progression.baotou_after_draw(
                baotou, waiting, self.meld_count, Tile(code), replacement=False,
            )
            child_unseen = g196._capacity_after(unseen, code)
            options = []
            for discard in self._legal(waiting, code, restricted):
                self.legal_leaf_count += 1
                self._check_budget()
                next_hand = g196._drop(full, discard)
                next_chain, next_piao = progression.chain_after_discard(
                    chain, piao, drawn_baotou, Tile(discard),
                )
                next_baotou = progression.baotou_after_discard(next_hand, self.meld_count)
                options.append((self._third(next_hand, child_unseen, next_baotou,
                                            next_chain, next_piao), discard))
            if not options:
                raise ValueError("第二摸没有合法后继弃牌")
            continuation = max(options, key=lambda item: (item[0].total,
                                                            -TILE_INDEX[item[1]]))[0]
            if terminal is None or continuation.total > terminal.total + 1e-12:
                branch = continuation
                if terminal is not None:
                    self.continue_over_hu[1] += 1
            else:
                branch = terminal
            value = value.plus(branch.scaled(capacity / total))
        return value

    def evaluate(self, *, restricted: bool) -> g196.Value:
        """按同一合法路径计算可选择弃胡的三摸条件本人自胡净分。"""

        total = sum(self.unseen)
        if total < 3:
            raise ValueError("公开未知池不足三次条件摸牌")
        value = g196.Value()
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
            for discard in self._legal(self.root, code, restricted):
                self.legal_leaf_count += 1
                self._check_budget()
                next_hand = g196._drop(full, discard)
                next_chain, next_piao = progression.chain_after_discard(
                    self.root_chain, self.root_piao, drawn_baotou, Tile(discard),
                )
                next_baotou = progression.baotou_after_discard(next_hand, self.meld_count)
                options.append((self._second_optional(
                    next_hand, child_unseen, next_baotou, next_chain, next_piao,
                    restricted), discard))
            if not options:
                raise ValueError("第一摸没有合法后继弃牌")
            continuation = max(options, key=lambda item: (item[0].total,
                                                            -TILE_INDEX[item[1]]))[0]
            if terminal is None or continuation.total > terminal.total + 1e-12:
                branch = continuation
                if terminal is not None:
                    self.continue_over_hu[0] += 1
            else:
                branch = terminal
            value = value.plus(branch.scaled(capacity / total))
        if not math.isfinite(value.total) or value.total < 0:
            raise ValueError("允许弃胡的三摸条件值非有限")
        return value


def _case(rank: int, seq: int, root_action: str | None, scorer) -> tuple:
    """官方全知帧仅投影赢家合法观察，核同窗胡/弃与冻结父代。"""

    doc = json.loads(g184.SOURCE_FILES[rank - 1].read_text(encoding="utf-8"))
    leaderboard = json.loads((g184.OUT / "leaderboard.json").read_text(encoding="utf-8"))
    user_id = leaderboard["top"][rank - 1]["user_id"]
    seat = next(index for index, person in enumerate(doc["seats"])
                if person["user_id"] == user_id)
    frame_index = next(index for index, frame in enumerate(doc["frames"])
                       if (frame.get("ev") or {}).get("seq") == seq)
    event = doc["frames"][frame_index]["ev"]
    actual = g184.actual_key(event)
    if root_action is not None and actual != root_action:
        raise ValueError("预登记历史弃牌与复盘不一致")
    observation = g184.observation(doc, frame_index - 1, seat)
    request = g184.request_for(observation, rank)
    legal = {candidate.action_key for candidate in request.rules.legal_candidates}
    if "hu" not in legal:
        raise ValueError("预登记可胡窗口不再合法可胡")
    scored = scorer.score(build_scoring_view(request, value_limits=c31.VALUE_LIMITS))
    if scored.status != "SCORED" or not scored.entries:
        raise ValueError("冻结 R18 v2 未能重判经典窗口")
    scores = {entry.action_key: entry.score for entry in scored.entries}
    parent = min(scores, key=lambda key: (-scores[key], key))
    if root_action is None:
        root_action = min((key for key in legal if key.startswith("discard:")),
                          key=lambda key: (-scores[key], key))
    if root_action not in legal:
        raise ValueError("根弃牌不在生产合法集合")
    immediate = c31.RULES.score(WinDescription(observation, seat))
    return doc, observation, actual, parent, root_action, immediate


def main() -> None:
    """保存四个已见压力题的规则与量具差异，不推断反事实收益。"""

    if OUT.exists():
        raise FileExistsError("G197 结果已存在，拒绝覆盖")
    scorer = ActionValueScorer("g197-r18-shadow", R18_INTEGRATED_POSITIVE_V2_SOURCE)
    rows = []
    stop_reason = None
    for rank, seq, fixed_root in CASES:
        doc, observation, actual, parent, root, immediate = _case(
            rank, seq, fixed_root, scorer,
        )
        row = {"rank": rank, "game_id": doc["game_id"], "round_no": doc["round_no"],
               "event_seq": seq, "actual": actual, "r18_top": parent,
               "root_discard": root, "wall_remaining": observation.remaining_tile_count,
               "white_before": sum(tile.code == "白" for tile in observation.my_hand),
               "immediate_hu_fan": immediate.fan,
               "immediate_hu_self_delta": immediate.score_delta[observation.seat],
               "modes": {}}
        for mode in ("restricted", "unrestricted"):
            restricted = mode == "restricted"
            result = {}
            for name, cls in (("forced_hu", g196.RouteSearch),
                              ("optional_hu", OptionalHuSearch)):
                search = cls(observation, c31.RULE_CONFIG, root)
                started = time.perf_counter()
                try:
                    value = search.evaluate(restricted=restricted)
                    result[name] = {"status": "complete", "value": value.json(),
                                    "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
                                    "legal_leaf_count": search.legal_leaf_count,
                                    "continue_over_hu": (
                                        search.continue_over_hu if name == "optional_hu" else None)}
                except g196.RouteLimitExceeded as exc:
                    stop_reason = str(exc)
                    result[name] = {"status": "limit_exceeded", "reason": stop_reason,
                                    "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
                                    "legal_leaf_count": search.legal_leaf_count}
                    break
            if not stop_reason:
                base = result["forced_hu"]["value"]
                optional = result["optional_hu"]["value"]
                if optional["total"] + 1e-8 < base["total"]:
                    raise ValueError("允许弃胡反而低于强制胡，同叶最优化有误")
                result["optional_minus_forced"] = {
                    key: round(optional[key] - base[key], 9)
                    for key in ("plain", "special", "depth1", "depth2", "depth3", "total")}
            row["modes"][mode] = result
            if stop_reason:
                break
        rows.append(row)
        print(json.dumps({"rank": rank, "seq": seq, "completed": len(rows),
                          "stop_reason": stop_reason}, ensure_ascii=False), flush=True)
        if stop_reason:
            break
    payload = {"schema": "g197-optional-hu-three-draw-pilot/1",
               "source_sha256": {"plan": digest(PLAN), "script": digest(Path(__file__)),
                                 "g196_script": digest(_project_file(_PROJECT_ROOT, HERE / "g196_three_draw_competing_route_pilot.py")),
                                 "g184_result": digest(g184.OUT / "result.json"),
                                 "leaderboard": digest(g184.OUT / "leaderboard.json"),
                                 **{f"rank{rank}_round": digest(g184.SOURCE_FILES[rank - 1])
                                    for rank in (1, 2, 3)}},
               "status": "stopped_on_cost" if stop_reason else "complete",
               "stop_reason": stop_reason, "rows": rows,
               "boundary": "已看大牌赢家条件样本与公开未知池三摸条件代理；不含对手先胡、实际墙后验和未来权威抓打圈；非策略收益。"}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True,
                              indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
