#!/usr/bin/env python3
"""G196：对少量冻结开发窗做三摸合法弃牌与普通／高番竞争终点先导。"""

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
from dataclasses import dataclass
from hashlib import sha256
import json
import math
from pathlib import Path
import time

import c31_action_layer_gap as c31
import g52_shared_horizon as g52
import g126_all_draw_natural_width_exposure as capture
import g160_multi_action_value_source as source
import g181_two_draw_settlement_value as g181
from hangma_bot.application.audit_codec import candidate_value_facts_to_json
from hangma_bot.hangma import action_families, hand_analysis, progression, settlement
from hangma_bot.hangma import value_analysis
from hangma_bot.hangma.engine import _build_context
from hangma_bot.hangma.internal_types import TILE_INDEX, TILE_ORDER, counts_from_tiles
from hangma_bot.hangma.public_tile_counts import count_unseen_tiles
from hangma_bot.kernel.actions import Discard, Tile
from hangma_bot.policy.r18_integrated_positive_v2_rules_20260929_release import (
    R18IntegratedPositiveV2Rules20260929ReleasePolicy,
    R18_V2_RULES_20260929_SOURCE_HASH,
)


HERE = Path(__file__).resolve().parent
PLAN = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/G196-THREE-DRAW-COMPETING-ROUTE-PILOT-PREREG-2026-09-29.md')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g196-three-draw-competing-route-pilot-20260929/result.json')
MAX_LEAVES = 2_000_000
MAX_SECONDS_PER_ARM = 30.0


class RouteLimitExceeded(Exception):
    """离线先导触及事前操作数或墙钟停止线，不截断冒充完整结果。"""


@dataclass(frozen=True)
class Value:
    """公开容量条件模型下，本座三摸内的互斥普通／高番净分。"""

    plain: float = 0.0
    special: float = 0.0
    depth1: float = 0.0
    depth2: float = 0.0
    depth3: float = 0.0

    @property
    def total(self) -> float:
        return self.plain + self.special

    def scaled(self, factor: float) -> "Value":
        return Value(*(getattr(self, field) * factor for field in
                       ("plain", "special", "depth1", "depth2", "depth3")))

    def plus(self, other: "Value") -> "Value":
        return Value(*(getattr(self, field) + getattr(other, field) for field in
                       ("plain", "special", "depth1", "depth2", "depth3")))

    def json(self) -> dict[str, float]:
        return {field: round(getattr(self, field), 9) for field in
                ("plain", "special", "depth1", "depth2", "depth3", "total")}


def digest(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _drop(hand: tuple[Tile, ...], code: str) -> tuple[Tile, ...]:
    """机械移除一张已由生产动作族确认为合法的弃牌。"""

    held = list(hand)
    held.remove(Tile(code))
    return tuple(sorted(held, key=lambda tile: TILE_INDEX[tile.code]))


def _capacity_after(unseen: tuple[int, ...], drawn_code: str) -> tuple[int, ...]:
    """条件本人摸到一张牌后，从公开未知池机械扣除该张。"""

    index = TILE_INDEX[drawn_code]
    if unseen[index] <= 0:
        raise ValueError("条件摸牌超出公开未知容量")
    counts = list(unseen)
    counts[index] -= 1
    return tuple(counts)


class RouteSearch:
    """只在离线枚举未来本人摸牌；规则判定全部委托生产 hangma。"""

    def __init__(self, observation, config, root_action: str) -> None:
        if config.you_cai_bi_kao:
            raise ValueError("有财必拷响开启时未来权威资格未知")
        if (observation.phase != "draw" or observation.turn_seat != observation.seat
                or type(observation.remaining_tile_count) is not int
                or observation.remaining_tile_count <= 32):
            raise ValueError("非本人正常摸牌窗或墙余不足三摸先导边界")
        if observation.chain_piao is None:
            raise ValueError("链内飘数未知")
        self.observation = observation
        self.config = config
        self.current = _build_context(observation)
        self.meld_count = len(observation.melds[observation.seat])
        if len(self.current.full_hand()) != 14 - 3 * self.meld_count:
            raise ValueError("动作前手牌张数与副露不符")
        if not root_action.startswith("discard:"):
            raise ValueError("先导只接受生产合法弃牌")
        self.root_action = root_action
        root_code = root_action.split(":", 1)[1]
        self.root = _drop(self.current.full_hand(), root_code)
        raw_unseen = count_unseen_tiles(observation)
        if any(type(x) is not int or x < 0 for x in raw_unseen):
            raise ValueError("公开未知池不完整")
        self.unseen = tuple(raw_unseen)
        self.root_baotou = progression.baotou_after_discard(self.root, self.meld_count)
        self.root_chain, self.root_piao = progression.chain_after_action(
            observation.rule_state.chain_count, observation.chain_piao,
            observation.rule_state.baotou, Discard(Tile(root_code)),
        )
        if self.root_piao is None:
            raise ValueError("根弃牌后飘数未知")
        self.started = time.perf_counter()
        self.legal_leaf_count = 0
        self.win_split_count = 0
        self.third_ready_count = 0
        self.memo_third: dict[tuple, Value] = {}

    def _check_budget(self) -> None:
        if self.legal_leaf_count > MAX_LEAVES:
            raise RouteLimitExceeded("合法后继叶超过 200 万")
        if self.legal_leaf_count % 256 == 0 and time.perf_counter() - self.started > MAX_SECONDS_PER_ARM:
            raise RouteLimitExceeded("单臂超过 30 秒")

    def _legal(self, waiting: tuple[Tile, ...], draw_code: str, restricted: bool) -> tuple[str, ...]:
        """由生产动作族给未来普通摸牌后的合法弃牌，不自写摸切规则。"""

        context = g52._first_context(self.current, waiting, draw_code, restricted)
        legal, issues = action_families.discard_tile_codes(context)
        if issues or not legal:
            raise ValueError("未来合法弃牌资格未知")
        return legal

    def _win(self, waiting: tuple[Tile, ...], code: str, *, baotou: bool,
             chain: int, piao: int, depth: int) -> Value | None:
        """用生产胡牌分解、爆头转移和结算得唯一互斥终点。"""

        tile = Tile(code)
        self.win_split_count += 1
        if self.win_split_count % 1024 == 0:
            self._check_budget()
        split = hand_analysis.win_split(waiting + (tile,), self.meld_count)
        if split is None:
            return None
        after_baotou = progression.baotou_after_draw(
            baotou, waiting, self.meld_count, tile, replacement=False,
        )
        result = settlement.settle_win(
            split, chain, piao, after_baotou, self.config.base_score,
            self.observation.seat, self.observation.dealer_seat,
        )
        gain = result.score_delta[self.observation.seat]
        if type(gain) is not int or gain <= 0 or result.fan < 1:
            raise ValueError("生产胡牌结算非正或番数未知")
        values = {"plain": 0.0, "special": 0.0,
                  "depth1": 0.0, "depth2": 0.0, "depth3": 0.0}
        values["plain" if result.fan == 1 else "special"] = float(gain)
        values[f"depth{depth}"] = float(gain)
        return Value(**values)

    def _third(self, waiting: tuple[Tile, ...], unseen: tuple[int, ...],
               baotou: bool, chain: int, piao: int) -> Value:
        """第二次合法弃牌后，只在生产规则判定听牌时枚举第三摸胡。"""

        key = (waiting, unseen, baotou, chain, piao)
        cached = self.memo_third.get(key)
        if cached is not None:
            return cached
        summary = hand_analysis.analyse_hand_progress(waiting, self.meld_count)
        if summary.shanten != 0:
            value = Value()
        else:
            self.third_ready_count += 1
            total = sum(unseen)
            if total <= 0:
                raise ValueError("第三摸公开未知池为空")
            value = Value()
            for index, capacity in enumerate(unseen):
                if capacity <= 0:
                    continue
                terminal = self._win(waiting, TILE_ORDER[index], baotou=baotou,
                                     chain=chain, piao=piao, depth=3)
                if terminal is not None:
                    value = value.plus(terminal.scaled(capacity / total))
        self.memo_third[key] = value
        return value

    def _after_second(self, waiting: tuple[Tile, ...], unseen: tuple[int, ...],
                      baotou: bool, chain: int, piao: int, restricted: bool) -> Value:
        """第二摸立即胡；否则在**同一合法弃牌**上选择第三摸终点。"""

        total = sum(unseen)
        if total <= 0:
            raise ValueError("第二摸公开未知池为空")
        value = Value()
        for index, capacity in enumerate(unseen):
            if capacity <= 0:
                continue
            code = TILE_ORDER[index]
            terminal = self._win(waiting, code, baotou=baotou,
                                 chain=chain, piao=piao, depth=2)
            if terminal is not None:
                branch = terminal
            else:
                full = waiting + (Tile(code),)
                drawn_baotou = progression.baotou_after_draw(
                    baotou, waiting, self.meld_count, Tile(code), replacement=False,
                )
                child_unseen = _capacity_after(unseen, code)
                options = []
                for discard in self._legal(waiting, code, restricted):
                    self.legal_leaf_count += 1
                    self._check_budget()
                    next_hand = _drop(full, discard)
                    next_chain, next_piao = progression.chain_after_discard(
                        chain, piao, drawn_baotou, Tile(discard))
                    next_baotou = progression.baotou_after_discard(next_hand, self.meld_count)
                    options.append((self._third(next_hand, child_unseen, next_baotou,
                                                next_chain, next_piao), discard))
                if not options:
                    raise ValueError("第二摸没有合法后继弃牌")
                branch = max(options, key=lambda item: (item[0].total, -TILE_INDEX[item[1]]))[0]
            value = value.plus(branch.scaled(capacity / total))
        return value

    def evaluate(self, *, restricted: bool) -> Value:
        """以本座自胡条件期望净分选未来动作；不访问未来实墙或对手暗手。"""

        total = sum(self.unseen)
        if total < 3:
            raise ValueError("公开未知池不足三次条件摸牌")
        value = Value()
        for index, capacity in enumerate(self.unseen):
            if capacity <= 0:
                continue
            code = TILE_ORDER[index]
            terminal = self._win(self.root, code, baotou=self.root_baotou,
                                 chain=self.root_chain, piao=self.root_piao, depth=1)
            if terminal is not None:
                branch = terminal
            else:
                full = self.root + (Tile(code),)
                drawn_baotou = progression.baotou_after_draw(
                    self.root_baotou, self.root, self.meld_count, Tile(code),
                    replacement=False,
                )
                child_unseen = _capacity_after(self.unseen, code)
                options = []
                for discard in self._legal(self.root, code, restricted):
                    self.legal_leaf_count += 1
                    self._check_budget()
                    next_hand = _drop(full, discard)
                    next_chain, next_piao = progression.chain_after_discard(
                        self.root_chain, self.root_piao, drawn_baotou, Tile(discard),
                    )
                    next_baotou = progression.baotou_after_discard(next_hand, self.meld_count)
                    options.append((self._after_second(
                        next_hand, child_unseen, next_baotou, next_chain, next_piao,
                        restricted), discard))
                if not options:
                    raise ValueError("第一摸没有合法后继弃牌")
                branch = max(options, key=lambda item: (item[0].total, -TILE_INDEX[item[1]]))[0]
            value = value.plus(branch.scaled(capacity / total))
        if not math.isfinite(value.total) or value.total < 0:
            raise ValueError("三摸条件价值非有限")
        return value


def _selected() -> list[dict]:
    """固定四层每层前两个不同根，仅用 G160 结果盲身份与白板层。"""

    rows = [row for row in g181._selected() if row["split"] == "development"]
    selected = []
    for mix in ("H", "M"):
        for white in (0, 1):
            group = sorted((row for row in rows if row["mix"] == mix and row["white_before"] == white),
                           key=lambda row: (row["root_index"], row["focal_seat"], row["round_no"]))
            seen_roots = set()
            for row in group:
                if row["root_index"] in seen_roots:
                    continue
                selected.append(row)
                seen_roots.add(row["root_index"])
                if len(seen_roots) == 2:
                    break
            if len(seen_roots) != 2:
                raise ValueError("G196 分层不足两个不同根")
    return selected


def main() -> None:
    """先首臂成本门，再对固定 8 窗两臂跑两种未来抓打包络。"""

    if OUT.exists():
        raise FileExistsError("G196 结果已存在；拒绝覆盖")
    selected = _selected()
    targets = g181._table_targets(selected)
    g95 = source.source.g95
    contract = json.loads(g95.g93.paired.CONTRACT.read_text(encoding="utf-8"))
    versions = g95.g93.natural.stage.contract_versions_block(contract)
    plans = {(mix, root, seat): plan for mix, root, seat, plan in source.plans(contract)}
    scorer = capture.g87.c31.load_parent()
    grouped = defaultdict(list)
    for row in selected:
        grouped[(row["mix"], row["root_index"], row["focal_seat"])].append(row)
    output = []
    first_arm = True
    stop_reason = None
    for table_key, members in sorted(grouped.items()):
        mix, root, seat = table_key
        original = g95.CaptureWiderPolicy
        old_factory = g95.g93.paired.policy_factory
        def current_factory(arm: str):
            """G194 新包只用于当前规则重放；旧研究臂保持原工厂。"""
            if arm != "r18_v2":
                return old_factory(arm)
            def build(monotonic):
                del monotonic
                return R18IntegratedPositiveV2Rules20260929ReleasePolicy(
                    rules_source_hash=R18_V2_RULES_20260929_SOURCE_HASH,
                    value_analysis_sha256=digest(Path(value_analysis.__file__)),
                )
            return build
        g95.CaptureWiderPolicy = capture.CaptureEveryHandAllDrawPolicy
        g95.g93.paired.policy_factory = current_factory
        try:
            captured, *_ = g95.run_full(plans[table_key], contract, versions, mix)
        finally:
            g95.CaptureWiderPolicy = original
            g95.g93.paired.policy_factory = old_factory
        for item in members:
            key = (mix, root, seat, item["round_no"])
            record = captured.records.get(item["round_no"])
            if (record is None or capture.scored_target(record, scorer) != targets[key]
                    or item["observation_sha256"] != targets[key]["observation_sha256"]
                    or item["parent_action"] != record.parent_key
                    or item["alternate_action"] != record.alternate_key):
                raise ValueError("G196 行动前观察或冻结双臂身份漂移")
            legal = {action.action_key: action for action in record.request.rules.legal_candidates}
            result = {"mix": mix, "root_index": root, "focal_seat": seat,
                      "round_no": item["round_no"], "white_before": item["white_before"],
                      "observation_sha256": item["observation_sha256"],
                      "parent_action": record.parent_key,
                      "alternate_action": record.alternate_key, "arms": {}}
            for name, action_key in (("parent", record.parent_key),
                                     ("alternate", record.alternate_key)):
                action = legal.get(action_key)
                if action is None or action.value_facts is None:
                    raise ValueError("G196 原始合法动作或生产价值事实缺失")
                started = time.perf_counter()
                try:
                    search = RouteSearch(record.request.observation, c31.RULE_CONFIG, action_key)
                    expected_first = g52._first_hu_routes(
                        {"value_facts": candidate_value_facts_to_json(action.value_facts)}, seat)
                    direct = {}
                    for index, capacity in enumerate(search.unseen):
                        if capacity <= 0:
                            continue
                        val = search._win(search.root, TILE_ORDER[index],
                                          baotou=search.root_baotou, chain=search.root_chain,
                                          piao=search.root_piao, depth=1)
                        if val is not None:
                            direct[TILE_ORDER[index]] = (round(val.total), capacity)
                    if direct != expected_first:
                        raise ValueError("G196 第一次摸牌胡分与生产 value_facts 不一致")
                    restricted_value = search.evaluate(restricted=True)
                    unrestricted_value = search.evaluate(restricted=False)
                    status, reason = "complete", None
                    values = {"restricted": restricted_value.json(),
                              "unrestricted": unrestricted_value.json()}
                    counters = {"legal_leaf_count": search.legal_leaf_count,
                                "win_split_count": search.win_split_count,
                                "third_ready_count": search.third_ready_count,
                                "third_memo_states": len(search.memo_third)}
                except RouteLimitExceeded as exc:
                    status, reason, values = "limit_exceeded", str(exc), None
                    counters = {"legal_leaf_count": search.legal_leaf_count,
                                "win_split_count": search.win_split_count,
                                "third_ready_count": search.third_ready_count,
                                "third_memo_states": len(search.memo_third)}
                    stop_reason = reason
                elapsed = (time.perf_counter() - started) * 1000.0
                result["arms"][name] = {"status": status, "reason": reason,
                                        "values": values, "counters": counters,
                                        "elapsed_ms": round(elapsed, 3)}
                if first_arm:
                    first_arm = False
                    if elapsed > MAX_SECONDS_PER_ARM * 1000 or counters["legal_leaf_count"] > MAX_LEAVES:
                        stop_reason = "首臂超过预定成本门"
                if stop_reason:
                    break
            output.append(result)
            print(json.dumps({"windows_completed": len(output), "last": key,
                              "stop_reason": stop_reason}, ensure_ascii=False), flush=True)
            if stop_reason:
                break
        if stop_reason:
            break
    payload = {
        "schema": "g196-three-draw-competing-route-pilot/1",
        "source_sha256": {"plan": digest(PLAN), "script": digest(Path(__file__)),
                          "g160_selection": digest(source.OUT / "selection.json"),
                          "g160_rows": digest(source.OUT / "rows.jsonl"),
                          "parent_source": digest(_project_file(_PROJECT_ROOT, HERE.parents[1] / "src/hangma_bot/policy/r18_integrated_positive_v2.py"))},
        "selected": [{key: row[key] for key in ("mix", "root_index", "focal_seat", "round_no", "white_before")}
                     for row in selected],
        "status": "stopped_on_cost" if stop_reason else "complete",
        "stop_reason": stop_reason,
        "rows": output,
        "boundary": "公开未知池可交换且本人连续获三次普通摸牌的离线条件值；未来抓打仅两包络，未估他家先胡、响应鸣牌或真实牌墙后验；非线上候选。",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                   encoding="utf-8")
    print(json.dumps({"status": payload["status"], "stop_reason": stop_reason,
                      "windows": len(output)}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
