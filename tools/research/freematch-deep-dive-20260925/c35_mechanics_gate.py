#!/usr/bin/env python3
"""C35 第二级门禁 runner：带机制/赛事计数器的同墙四座轮转配对批。

预登记（运行前落盘）：review/freematch-deep-dive-20260925/C35-PREREG-LEVEL2-MECHANICS.md
配对与合同**沿用** review/r18-four-arm-evaluation-2026-09-23/paired_study.py：
同一 build_seat_stage_plans、同一 offline.evaluate.drive_match 驱动、同一阶段积分口径。

**不改任何生产文件**。机制计数器走两个**运行期只读钩子**：

1. 把 sitin_natural_panel.execute_natural_table 换成薄包装（原函数原样调用），
   在包装内临时把 bootstrap.build_evaluation_runtime 返回字典里的 engine 换成
   只读转发代理（start/frame/advance 原样转发，其余键逐字不变）。代理只记录
   已到达决策边界的**公开事实**：焦点座位的 PlayerObservation、该帧的 choices、
   以及每局结束后的公开单局记录 RoundRecord（庄/胡家/流局/番/增量）。
2. candidate_policy_factory 返回对象外包只读记录器：转发 choose、原样抛异常，
   并用驱动传入的 request.rules.legal_candidates 复核首选动作（与驱动同判据）。

子命令：
  run     跑批（或断点续跑；已完成的阶段文件不重算）
  verdict 读批并输出冻结判定的逐项读数
  verify  逐点对拍：本 runner 的阶段积分 vs paired_study 参考批
"""

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
import asyncio
import concurrent.futures
import json
import math
import statistics
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

ROOT = _PROJECT_ROOT
ROUTE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15')
for _entry in (_project_file(_PROJECT_ROOT, ROOT / "src"), _project_file(_PROJECT_ROOT, ROUTE / "tools"),
               _project_file(_PROJECT_ROOT, ROOT / "review/r18-four-arm-evaluation-2026-09-23")):
    if str(_entry) not in sys.path:
        sys.path.insert(0, str(_entry))

import paired_study  # noqa: E402
import sitin_natural_panel as natural  # noqa: E402
from hangma_bot import bootstrap  # noqa: E402
from hangma_bot.hangma import hand_analysis  # noqa: E402
from hangma_bot.hangma.engine import HangmaRules  # noqa: E402
from hangma_bot.kernel.actions import Chi, Gang, Peng, action_key  # noqa: E402
from hangma_bot.kernel.config import RuleConfig  # noqa: E402
from hangma_bot.policy.errors import PolicyTimeoutError  # noqa: E402

#: 预登记冻结的批身份（不得在本文件里改动；改批身份 = 新实验）。
PANEL_SEED = 2026110101
BASELINE_ARM = "r18_v2"
CANDIDATE_ARM = ("candidate@review/freematch-deep-dive-20260925/"
                 "candidates/OPTY-R18-C27-CELL-R6.py")
ARMS = (BASELINE_ARM, CANDIDATE_ARM)
MIXES = ("H", "M")
SEATS = (0, 1, 2, 3)
CLAIM_ACTION_TYPES = (Chi, Peng, Gang)
RESPONSE_PHASES = ("response_peng", "response_chi")
ROUNDS_PER_TABLE = 8
SCHEMA = "c35-mechanics-gate/1"


def write_json(path: Path, payload: Any) -> None:
    """UTF-8 原子写入（与 paired_study 同形）。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                         encoding="utf-8")
    temporary.replace(path)


def unit_path(out: Path, unit: Sequence[Any]) -> Path:
    """阶段文件路径（与 paired_study 同构：不含执行结果）。"""
    mix, root_index, seat, arm, _seed = unit
    return out / "stages" / ("%s-r%04d-s%d-%s.json"
                             % (mix, root_index, seat, paired_study.safe_arm_name(arm)))


# ---------------------------------------------------------------------------
# 只读引擎代理
# ---------------------------------------------------------------------------


class _RoundMechanics:
    """一个焦点座位在一局内的机制计数（只有计数与首次听牌快照）。"""

    __slots__ = ("windows", "response_windows", "baotou_entry", "baotou_static",
                 "first_turn", "first_kinds", "first_tiles", "claims",
                 "claim_opportunities", "anomalies")

    def __init__(self) -> None:
        self.windows = 0
        self.response_windows = 0
        self.baotou_entry = False
        self.baotou_static = False
        self.first_turn: Optional[int] = None
        self.first_kinds: Optional[int] = None
        self.first_tiles: Optional[List[str]] = None
        self.claims = 0
        self.claim_opportunities = 0
        self.anomalies = 0

    def to_json(self) -> Dict[str, Any]:
        return {name: getattr(self, name) for name in self.__slots__}


class _EngineProxy:
    """只读转发包装：不改任何决策输入，只记录已公开事实。"""

    def __init__(self, inner: Any, mechanics: "_TableMechanics", rules: HangmaRules,
                 focal_seat: int) -> None:
        self._inner = inner
        self._mech = mechanics
        self._rules = rules
        self._focal = int(focal_seat)

    # -- 驱动只调用这三个方法 ------------------------------------------------
    def start(self, spec: Any) -> Any:
        world = self._inner.start(spec)
        self._snapshot(world)
        return world

    def frame(self, world: Any) -> Any:
        frame = self._inner.frame(world)
        for decision in frame.decisions:
            if int(decision.window_key.seat) != self._focal:
                continue
            self._on_window(decision.observation)
        return frame

    def advance(self, world: Any, revision: int, choices: Sequence[Any]) -> Any:
        for choice in choices:
            if int(choice.window_key.seat) != self._focal:
                continue
            if isinstance(choice.action, CLAIM_ACTION_TYPES):
                state = self._mech.round_state(int(choice.window_key.round_no))
                state.claims += 1
        world = self._inner.advance(world, revision, choices)
        self._snapshot(world)
        return world

    # -- 记录 ---------------------------------------------------------------
    def _on_window(self, observation: Any) -> None:
        """焦点座位的一个决策窗口：按预登记口径更新本局机制计数。"""
        round_no = int(observation.round_no)
        state = self._mech.round_state(round_no)
        state.windows += 1
        if bool(observation.rule_state.baotou):
            state.baotou_entry = True
        melds = len(observation.melds[self._focal])
        phase = str(observation.phase)
        if phase == "draw":
            drawn = observation.drawn_tile
            full = tuple(observation.my_hand) + (() if drawn is None else (drawn,))
            if len(full) != 14 - 3 * melds:
                state.anomalies += 1
                return
            if drawn is not None and hand_analysis.any_tile_win(tuple(observation.my_hand), melds):
                state.baotou_static = True
            if state.first_turn is not None:
                return
            try:
                if hand_analysis.analyse_hand(full, melds).shanten != 0:
                    return
                turn = len(observation.discards[self._focal]) + 1
                kinds, tiles = _best_wait_face(full, melds)
                if kinds is None:
                    return
                state.first_turn = int(turn)
                state.first_kinds = int(kinds)
                state.first_tiles = list(tiles)
            except Exception:  # 统计失败必须显式计数，不得静默当成"未听牌"
                state.anomalies += 1
        elif phase in RESPONSE_PHASES:
            state.response_windows += 1
            try:
                analysis = self._rules.analyze(observation)
                if any(isinstance(candidate.action, CLAIM_ACTION_TYPES)
                       for candidate in analysis.legal_candidates):
                    state.claim_opportunities += 1
            except Exception:
                state.anomalies += 1

    def _snapshot(self, world: Any) -> None:
        """记录已完成的**公开单局记录**（RoundRecord = 牌谱口径的赛后结果）。"""
        for record in list(getattr(world, "round_records", ()) or ()):
            self._mech.public.setdefault(int(record.round_no), {
                "dealer_seat": int(record.dealer_seat),
                "winner_seat": None if record.winner_seat is None else int(record.winner_seat),
                "is_draw": bool(record.is_draw),
                "fan": int(record.fan),
                "details": [str(item) for item in record.details],
                "score_delta": [int(value) for value in record.score_delta],
            })


def _best_wait_face(full: Tuple[Any, ...], melds: int) -> Tuple[Optional[int], Tuple[str, ...]]:
    """等待面（预登记口径）：逐张试弃，取向听为 0 的等待手牌里有效牌种数最大者。

    并列时按规范牌序（TILE_ORDER）取最小弃牌的那一个，保证确定性。
    """
    best: Optional[Tuple[int, Tuple[str, ...]]] = None
    for index, tile in enumerate(full):
        after = full[:index] + full[index + 1:]
        try:
            summary = hand_analysis.analyse_hand(after, melds)
        except Exception:
            continue
        if summary.shanten != 0:
            continue
        codes = tuple(sorted({item.code for item in summary.useful_tiles},
                             key=lambda code: hand_analysis.TILE_ORDER.index(code)))
        if not codes:
            continue
        if best is None or len(codes) > best[0] or (len(codes) == best[0] and codes < best[1]):
            best = (len(codes), codes)
    if best is None:
        return None, ()
    return best[0], best[1]


class _TableMechanics:
    """一桌（一个阶段单元的一张桌）的焦点座位机制记录。"""

    def __init__(self, focal_seat: int) -> None:
        self.focal_seat = int(focal_seat)
        self.rounds: Dict[str, _RoundMechanics] = {}
        self.public: Dict[int, Dict[str, Any]] = {}

    def round_state(self, round_no: int) -> _RoundMechanics:
        return self.rounds.setdefault(str(int(round_no)), _RoundMechanics())


class _PolicyRecorder:
    """只读记录器：转发 choose、原样抛异常，并按驱动同一判据复核首选动作。"""

    def __init__(self, inner: Any, counters: Dict[str, int]) -> None:
        self._inner = inner
        self._counters = counters
        self.policy_id = getattr(inner, "policy_id", type(inner).__name__)
        self.max_operations = getattr(inner, "max_operations", None)

    async def choose(self, request: Any, budget: Any) -> Any:
        try:
            plan = await self._inner.choose(request, budget)
        except asyncio.CancelledError:
            self._counters["timeout"] += 1
            raise
        except PolicyTimeoutError:
            self._counters["timeout"] += 1
            raise
        except BaseException:
            self._counters["exceptions"] += 1
            raise
        try:
            candidates = tuple(getattr(plan, "candidates", ()) or ())
            if candidates:
                key = action_key(candidates[0].action)
                legal = {candidate.action_key for candidate in request.rules.legal_candidates}
                if key not in legal:
                    self._counters["illegal"] += 1
        except Exception:
            self._counters["recorder_errors"] += 1
        return plan


# ---------------------------------------------------------------------------
# 单个阶段单元
# ---------------------------------------------------------------------------


def run_unit(unit: Tuple[str, int, int, str, int]) -> Dict[str, Any]:
    """跑一个（对手组合, 牌山根, 焦点座位, 策略臂）的完整阶段，附带机制计数。"""
    mix, root_index, seat, arm, panel_seed = unit
    contract = json.loads(paired_study.CONTRACT.read_text(encoding="utf-8"))
    plans = natural.build_seat_stage_plans(
        contract=contract, opponent=mix, root_index=root_index,
        focal_seat=seat, panel_seed=panel_seed)
    sinks: List[_TableMechanics] = []
    counters = {"illegal": 0, "timeout": 0, "exceptions": 0, "recorder_errors": 0}
    build_policy = paired_study.policy_factory(arm)
    original_execute = natural.execute_natural_table

    def policy_factory(monotonic):
        return _PolicyRecorder(build_policy(monotonic), counters)

    def instrumented_execute(**kwargs: Any) -> Dict[str, Any]:
        plan = kwargs["plan"]
        focal_logical = list(plan.logical_participants).index(natural.FOCAL_PARTICIPANT)
        focal_physical = int(plan.permutation[focal_logical])
        block = kwargs["versions_block"]
        rules = HangmaRules(RuleConfig(ruleset_version=str(block["ruleset_version"]),
                                       base_score=int(block["base_score"]),
                                       you_cai_bi_kao=bool(block["you_cai_bi_kao"])))
        mechanics = _TableMechanics(focal_physical)
        sinks.append(mechanics)
        original_runtime = bootstrap.build_evaluation_runtime

        def patched_runtime(kind: str, experiment: Any):
            runtime = original_runtime(kind, experiment)
            if runtime is None:
                return runtime
            return {**runtime,
                    "engine": _EngineProxy(runtime["engine"], mechanics, rules, focal_physical)}

        bootstrap.build_evaluation_runtime = patched_runtime
        try:
            return original_execute(**kwargs)
        finally:
            bootstrap.build_evaluation_runtime = original_runtime

    natural.execute_natural_table = instrumented_execute
    started = time.monotonic()
    try:
        stage = natural.run_arm_stage(
            arm="candidate", plans=plans, candidate_scorer=None,
            candidate_policy_factory=policy_factory,
            opponent_policies=contract["panel"]["opponent_scenarios"][mix]["opponent_policies"],
            versions_block=natural.stage.contract_versions_block(contract),
            step_limit=int(contract["stop"]["step_limit"]),
            value_limits=paired_study.LIMITS)
    finally:
        natural.execute_natural_table = original_execute
    elapsed_ms = (time.monotonic() - started) * 1000.0

    rounds = _stage_rounds(sinks)
    return {
        "mix": mix, "root_index": int(root_index), "focal_seat": int(seat), "arm": arm,
        "stage": stage,
        "mechanics": {
            "schema": SCHEMA,
            "sinks": len(sinks),
            "expected_tables": len(plans),
            "focal_physical_by_table": [sink.focal_seat for sink in sinks],
            "runner_illegal": counters["illegal"],
            "runner_timeout": counters["timeout"],
            "policy_exceptions": counters["exceptions"],
            "recorder_errors": counters["recorder_errors"],
            "elapsed_ms": round(elapsed_ms, 3),
            "rounds": rounds,
            "totals": _round_totals(rounds),
            "table_runtime_counts": _table_runtime_counts(stage),
        },
    }


def _table_runtime_counts(stage: Mapping[str, Any]) -> Dict[str, int]:
    """驱动自报的保底计数（含**全部四个座位**，作为焦点计数的交叉核对）。"""
    totals: Counter = Counter()
    for table in stage.get("tables") or ():
        runtime = ((table.get("result") or {}).get("runtime_counts")) or {}
        for key, value in runtime.items():
            if isinstance(value, int):
                totals[key] += value
    return dict(sorted(totals.items()))


def _stage_rounds(sinks: Sequence[_TableMechanics]) -> List[Dict[str, Any]]:
    """把两张桌的机制记录拍平成逐局行（局号在同一桌内唯一）。"""
    rows: List[Dict[str, Any]] = []
    for table_index, sink in enumerate(sinks):
        numbers = sorted({int(key) for key in sink.rounds} | set(sink.public))
        for round_no in numbers:
            state = sink.rounds.get(str(round_no))
            public = sink.public.get(round_no, {})
            state = state if state is not None else _RoundMechanics()
            dealer = public.get("dealer_seat")
            winner = public.get("winner_seat")
            details = [str(item) for item in (public.get("details") or ())]
            delta = public.get("score_delta")
            focal_delta = (int(delta[sink.focal_seat])
                           if isinstance(delta, list) and len(delta) == 4 else None)
            rows.append({
                "table": table_index + 1,
                "round_no": round_no,
                "dealer_seat": dealer,
                "winner_seat": winner,
                "is_draw": bool(public.get("is_draw", True)),
                "fan": int(public.get("fan", 0)),
                "is_dealer": dealer == sink.focal_seat,
                "won": winner == sink.focal_seat,
                "focal_score_delta": focal_delta,
                "win_score": (focal_delta if (winner == sink.focal_seat and focal_delta is not None)
                              else None),
                "baotou_win": bool(winner == sink.focal_seat and any("爆头" in item for item in details)),
                "fan_details": details,
                "baotou_entry": bool(state.baotou_entry),
                "baotou_static_entry": bool(state.baotou_static),
                "first_tenpai_turn": state.first_turn,
                "first_tenpai_wait_kinds": state.first_kinds,
                "first_tenpai_wait_tiles": state.first_tiles,
                "claims_made": int(state.claims),
                "claim_opportunities": int(state.claim_opportunities),
                "decisions": int(state.windows),
                "response_windows": int(state.response_windows),
                "anomalies": int(state.anomalies),
            })
    return rows


def _round_totals(rounds: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    """逐局行的阶段合计（判定的唯一输入）。"""
    tenpai = [row for row in rounds if row.get("first_tenpai_turn") is not None]
    turns = [int(row["first_tenpai_turn"]) for row in tenpai]
    kinds = [int(row["first_tenpai_wait_kinds"]) for row in tenpai
             if row.get("first_tenpai_wait_kinds") is not None]
    histogram = Counter()
    for row in rounds:
        if not row["won"]:
            continue
        fan = int(row["fan"])
        histogram["fan%d_wins" % fan if fan in (1, 2, 4, 8) else "fan_other_wins"] += 1
    return {
        "rounds": len(rounds),
        "baotou_entry_rounds": sum(1 for row in rounds if row["baotou_entry"]),
        **{key: int(histogram.get(key, 0)) for key in
           ("fan1_wins", "fan2_wins", "fan4_wins", "fan8_wins", "fan_other_wins")},
        "baotou_wins": sum(1 for row in rounds if row["baotou_win"]),
        "score_sum_wins": sum(int(row["win_score"]) for row in rounds
                              if row["win_score"] is not None),
        "score_sum_all": sum(int(row["focal_score_delta"]) for row in rounds
                             if row["focal_score_delta"] is not None),
        "baotou_static_rounds": sum(1 for row in rounds if row["baotou_static_entry"]),
        "wins": sum(1 for row in rounds if row["won"]),
        "dealer_rounds": sum(1 for row in rounds if row["is_dealer"]),
        "dealer_wins": sum(1 for row in rounds if row["is_dealer"] and row["won"]),
        "fan_sum": sum(int(row["fan"]) for row in rounds if row["won"]),
        "fan_sum_all": sum(int(row["fan"]) for row in rounds),
        "claims_made": sum(int(row["claims_made"]) for row in rounds),
        "claim_opportunities": sum(int(row["claim_opportunities"]) for row in rounds),
        "decisions": sum(int(row["decisions"]) for row in rounds),
        "response_windows": sum(int(row["response_windows"]) for row in rounds),
        "anomalies": sum(int(row["anomalies"]) for row in rounds),
        "tenpai_rounds": len(tenpai),
        "first_tenpai_turn_sum": sum(turns),
        "first_tenpai_kinds_sum": sum(kinds),
    }


# ---------------------------------------------------------------------------
# run
# ---------------------------------------------------------------------------


def command_run(args: argparse.Namespace) -> int:
    out: Path = args.out
    arms = ARMS
    units = [(mix, root, seat, arm, args.panel_seed)
             for mix in MIXES
             for root in range(args.root_start, args.root_start + args.roots_per_mix)
             for seat in SEATS
             for arm in arms]
    contract = json.loads(paired_study.CONTRACT.read_text(encoding="utf-8"))
    manifest = {
        "schema": SCHEMA,
        "experiment": "C35-LEVEL2-MECHANICS",
        "prereg": "review/freematch-deep-dive-20260925/C35-PREREG-LEVEL2-MECHANICS.md",
        "panel_seed": int(args.panel_seed),
        "root_start": int(args.root_start),
        "roots_per_mix": int(args.roots_per_mix),
        "mixes": list(MIXES), "seats": list(SEATS), "arms": list(arms),
        "tables_per_stage": int(contract["group"]["tables_per_group"]),
        "rounds_per_table": int(contract["versions"]["rounds_per_game"]),
        "planned_units": len(units),
        "planned_complete_tables": len(units) * int(contract["group"]["tables_per_group"]),
        "statistical_unit": "opponent_mix×root_index；四座位先在根内平均；CI 为根级聚类",
        "rules_source_hash": paired_study.compute_rules_hash(ROOT),
        "r18_v2_release_id": paired_study.R18_INTEGRATED_POSITIVE_V2_RELEASE_PACKAGE_ID,
        "input_identity": paired_study.input_identity(),
        "candidate_sources": paired_study.candidate_sources(arms),
    }
    manifest_path = out / "manifest.json"
    if manifest_path.exists():
        if json.loads(manifest_path.read_text(encoding="utf-8")) != manifest:
            raise SystemExit("现有运行清单与本次输入不同，拒绝混合或覆盖")
    else:
        write_json(manifest_path, manifest)
    pending = []
    for unit in units:
        path = unit_path(out, unit)
        if path.exists():
            row = json.loads(path.read_text(encoding="utf-8"))
            if row["stage"]["status"] != "complete":
                raise SystemExit("已有阶段不完整：" + str(path))
        else:
            pending.append(unit)
    print("待跑 %d / 共 %d 个阶段单元（workers=%d）" % (len(pending), len(units), args.workers))
    if pending:
        started = time.monotonic()
        done = 0
        with concurrent.futures.ProcessPoolExecutor(max_workers=args.workers) as executor:
            futures = {executor.submit(run_unit, unit): unit for unit in pending}
            for future in concurrent.futures.as_completed(futures):
                unit = futures[future]
                row = future.result()
                if row["stage"]["status"] != "complete":
                    raise RuntimeError("阶段失败，已保留证据：" + str(unit_path(out, unit)))
                write_json(unit_path(out, unit), row)
                done += 1
                if done % 100 == 0 or done == len(pending):
                    rate = done / max(1e-9, time.monotonic() - started)
                    print("  %d/%d 完成（%.1f 单元/秒，已用 %.1f 分钟）"
                          % (done, len(pending), rate, (time.monotonic() - started) / 60.0),
                          flush=True)
    print("完成：%s" % (out / "stages"))
    return 0


# ---------------------------------------------------------------------------
# verdict
# ---------------------------------------------------------------------------


def _load_rows(batch: Path) -> List[Dict[str, Any]]:
    rows = []
    for path in sorted((batch / "stages").glob("*.json")):
        rows.append(json.loads(path.read_text(encoding="utf-8")))
    if not rows:
        raise SystemExit("批目录没有阶段文件：" + str(batch / "stages"))
    return rows


def _summary(values: Sequence[float]) -> Tuple[float, float, float, float]:
    n = len(values)
    if n == 0:
        return float("nan"), float("nan"), float("nan"), float("nan")
    mean = statistics.fmean(values)
    # 与 c29_verdict.py 同一算式（总体标准差 / √n，1.96 正态分位），保持判定血缘一致。
    se = statistics.pstdev(values) / math.sqrt(n) if n > 1 else float("nan")
    return mean, se, mean - 1.96 * se, mean + 1.96 * se


def _unit_cells(rows: Sequence[Mapping[str, Any]], tables_per_stage: int) -> Dict[Tuple[str, int], Dict[str, Dict[str, float]]]:
    """(mix, root) → 臂 → 该根内四个焦点座位先平均后的指标。"""
    cells: Dict[Tuple[str, int], Dict[str, Dict[str, float]]] = {}
    grouped: Dict[Tuple[str, int, str], List[Mapping[str, Any]]] = {}
    for row in rows:
        grouped.setdefault((row["mix"], row["root_index"], row["arm"]), []).append(row)
    for (mix, root, arm), units in grouped.items():
        per_seat = []
        for row in units:
            totals = row["mechanics"]["totals"]
            rounds = max(1, int(totals["rounds"]))
            per_seat.append({
                "score_per_table": row["stage"]["focal_stage_score"] / float(tables_per_stage),
                "baotou_rate": totals["baotou_entry_rounds"] / float(rounds),
                "baotou_static_rate": totals["baotou_static_rounds"] / float(rounds),
                "win_rate": totals["wins"] / float(rounds),
                "dealer_win_rate": (totals["dealer_wins"] / float(totals["dealer_rounds"])
                                    if totals["dealer_rounds"] else float("nan")),
                "idle_win_rate": ((totals["wins"] - totals["dealer_wins"])
                                  / float(rounds - totals["dealer_rounds"])
                                  if rounds > totals["dealer_rounds"] else float("nan")),
                "fan_per_win": (totals["fan_sum"] / float(totals["wins"])
                                if totals["wins"] else float("nan")),
                "win_score_per_win": (totals["score_sum_wins"] / float(totals["wins"])
                                      if totals["wins"] else float("nan")),
                "baotou_win_share": (totals["baotou_wins"] / float(totals["wins"])
                                     if totals["wins"] else float("nan")),
                "fan_ge2_share": ((totals["wins"] - totals["fan1_wins"]) / float(totals["wins"])
                                  if totals["wins"] else float("nan")),
                "fan1_share": (totals["fan1_wins"] / float(totals["wins"])
                               if totals["wins"] else float("nan")),
                "fan2_share": (totals["fan2_wins"] / float(totals["wins"])
                               if totals["wins"] else float("nan")),
                "fan4_share": (totals["fan4_wins"] / float(totals["wins"])
                               if totals["wins"] else float("nan")),
                "fan8_share": (totals["fan8_wins"] / float(totals["wins"])
                               if totals["wins"] else float("nan")),
                "fan_per_round": totals["fan_sum"] / float(rounds),
                "claims_per_round": totals["claims_made"] / float(rounds),
                "claim_opportunities_per_round": totals["claim_opportunities"] / float(rounds),
                "tenpai_rate": totals["tenpai_rounds"] / float(rounds),
                "first_tenpai_turn_mean": (totals["first_tenpai_turn_sum"] / float(totals["tenpai_rounds"])
                                           if totals["tenpai_rounds"] else float("nan")),
                "first_tenpai_kinds_mean": (totals["first_tenpai_kinds_sum"] / float(totals["tenpai_rounds"])
                                            if totals["tenpai_rounds"] else float("nan")),
                "decisions_per_round": totals["decisions"] / float(rounds),
                "illegal": float(row["mechanics"]["runner_illegal"]),
                "timeout": float(row["mechanics"]["runner_timeout"]),
                "exceptions": float(row["mechanics"]["policy_exceptions"]),
                "anomalies": float(totals["anomalies"]) + float(row["mechanics"]["recorder_errors"]),
            })
        cell = cells.setdefault((mix, root), {})
        keys = per_seat[0].keys()
        cell[arm] = {key: statistics.fmean([seat[key] for seat in per_seat]) for key in keys}
        cell[arm]["units"] = float(len(per_seat))
    return cells


def _pooled_rates(rows: Sequence[Mapping[str, Any]], pool: Optional[str]) -> Dict[str, Any]:
    """整批（或单池）**按局池化**的原始计数与率：庄/闲胡率等的最直接读数。"""
    keys = ("rounds", "baotou_entry_rounds", "baotou_static_rounds", "wins", "dealer_rounds",
            "dealer_wins", "fan_sum", "claims_made", "claim_opportunities", "tenpai_rounds",
            "decisions", "response_windows", "first_tenpai_turn_sum", "first_tenpai_kinds_sum",
            "fan1_wins", "fan2_wins", "fan4_wins", "fan8_wins", "fan_other_wins",
            "baotou_wins", "score_sum_wins", "score_sum_all")
    out: Dict[str, Dict[str, int]] = {}
    for row in rows:
        if pool is not None and row["mix"] != pool:
            continue
        bucket = out.setdefault(row["arm"], {key: 0 for key in keys} | {"stages": 0})
        totals = row["mechanics"]["totals"]
        for key in keys:
            bucket[key] += int(totals[key])
        bucket["stages"] += 1

    def rate(bucket: Mapping[str, int], numerator: str, denominator: str) -> float:
        return (bucket[numerator] / float(bucket[denominator])) if bucket[denominator] else float("nan")

    result: Dict[str, Any] = {}
    for arm, bucket in sorted(out.items()):
        result[arm] = {
            **{key: int(bucket[key]) for key in keys},
            "stages": int(bucket["stages"]),
            "baotou_rate": rate(bucket, "baotou_entry_rounds", "rounds"),
            "baotou_static_rate": rate(bucket, "baotou_static_rounds", "rounds"),
            "win_rate": rate(bucket, "wins", "rounds"),
            "dealer_win_rate": rate(bucket, "dealer_wins", "dealer_rounds"),
            "idle_win_rate": ((bucket["wins"] - bucket["dealer_wins"])
                              / float(bucket["rounds"] - bucket["dealer_rounds"])
                              if bucket["rounds"] > bucket["dealer_rounds"] else float("nan")),
            "fan_per_win": rate(bucket, "fan_sum", "wins"),
            "win_score_per_win": rate(bucket, "score_sum_wins", "wins"),
            "baotou_win_share": rate(bucket, "baotou_wins", "wins"),
            "fan1_share": rate(bucket, "fan1_wins", "wins"),
            "fan2_share": rate(bucket, "fan2_wins", "wins"),
            "fan4_share": rate(bucket, "fan4_wins", "wins"),
            "fan8_share": rate(bucket, "fan8_wins", "wins"),
            "fan_ge2_share": ((bucket["wins"] - bucket["fan1_wins"]) / float(bucket["wins"])
                              if bucket["wins"] else float("nan")),
            "claims_per_round": rate(bucket, "claims_made", "rounds"),
            "claim_opportunities_per_round": rate(bucket, "claim_opportunities", "rounds"),
            "tenpai_rate": rate(bucket, "tenpai_rounds", "rounds"),
            "first_tenpai_turn_mean": rate(bucket, "first_tenpai_turn_sum", "tenpai_rounds"),
            "first_tenpai_kinds_mean": rate(bucket, "first_tenpai_kinds_sum", "tenpai_rounds"),
        }
    return result


def command_verdict(args: argparse.Namespace) -> int:
    batch: Path = args.batch
    manifest = json.loads((batch / "manifest.json").read_text(encoding="utf-8"))
    rows = _load_rows(batch)
    tables_per_stage = int(manifest["tables_per_stage"])
    cells = _unit_cells(rows, tables_per_stage)
    metrics = ["score_per_table", "baotou_rate", "baotou_static_rate", "win_rate",
               "dealer_win_rate", "idle_win_rate", "fan_per_win", "fan_per_round",
               "win_score_per_win", "baotou_win_share", "fan1_share", "fan2_share",
               "fan4_share", "fan8_share", "fan_ge2_share",
               "claims_per_round",
               "claim_opportunities_per_round", "tenpai_rate", "first_tenpai_turn_mean",
               "first_tenpai_kinds_mean", "decisions_per_round"]

    def deltas(metric: str, pool: Optional[str] = None) -> List[float]:
        out = []
        for (mix, _root), arms in sorted(cells.items()):
            if pool is not None and mix != pool:
                continue
            base = arms.get(BASELINE_ARM, {}).get(metric)
            cand = arms.get(CANDIDATE_ARM, {}).get(metric)
            if base is None or cand is None:
                continue
            if isinstance(base, float) and math.isnan(base):
                continue
            if isinstance(cand, float) and math.isnan(cand):
                continue
            out.append(cand - base)
        return out

    def levels(metric: str, arm: str, pool: Optional[str] = None) -> List[float]:
        out = []
        for (mix, _root), arms in sorted(cells.items()):
            if pool is not None and mix != pool:
                continue
            value = arms.get(arm, {}).get(metric)
            if value is None or (isinstance(value, float) and math.isnan(value)):
                continue
            out.append(value)
        return out

    def counters() -> Dict[str, float]:
        totals: Counter = Counter()
        for row in rows:
            mech = row["mechanics"]
            totals["runner_illegal"] += int(mech["runner_illegal"])
            totals["runner_timeout"] += int(mech["runner_timeout"])
            totals["policy_exceptions"] += int(mech["policy_exceptions"])
            totals["recorder_errors"] += int(mech["recorder_errors"])
            totals["anomalies"] += int(mech["totals"]["anomalies"])
            totals["driver_timeouts"] += int(row["mechanics"]["table_runtime_counts"].get("timeouts", 0))
            totals["driver_illegal"] += int(row["mechanics"]["table_runtime_counts"].get("illegal_choices", 0))
            totals["driver_fallbacks"] += int(row["mechanics"]["table_runtime_counts"].get("fallbacks", 0))
            totals["rounds"] += int(mech["totals"]["rounds"])
            totals["stages"] += 1
        return dict(sorted(totals.items()))

    report: Dict[str, Any] = {"schema": SCHEMA, "batch": str(batch), "manifest": manifest,
                              "counters": counters(), "metrics": {}, "judgements": {},
                              "pooled": {pool: _pooled_rates(rows, None if pool == "ALL" else pool)
                                         for pool in ("ALL",) + MIXES}}
    print("批次：%s（panel_seed=%s，单元 %d，根×mix %d）"
          % (batch, manifest["panel_seed"], len(rows), len(cells)))
    print()
    print("| 指标（候选 − 基准） | n根 | Δ均值 | 95% CI | 基准水平 | 候选水平 |")
    print("| --- | --- | --- | --- | --- | --- |")
    for metric in metrics:
        values = deltas(metric)
        if not values:
            continue
        mean, _se, low, high = _summary(values)
        base_level = statistics.fmean(levels(metric, BASELINE_ARM)) if levels(metric, BASELINE_ARM) else float("nan")
        cand_level = statistics.fmean(levels(metric, CANDIDATE_ARM)) if levels(metric, CANDIDATE_ARM) else float("nan")
        report["metrics"][metric] = {"n": len(values), "delta_mean": mean, "ci_low": low,
                                     "ci_high": high, "baseline": base_level, "candidate": cand_level,
                                     "pools": {pool: {"delta_mean": _summary(deltas(metric, pool))[0],
                                                      "ci_low": _summary(deltas(metric, pool))[2],
                                                      "ci_high": _summary(deltas(metric, pool))[3],
                                                      "n": len(deltas(metric, pool))}
                                               for pool in MIXES}}
        print("| %s | %d | %+.5f | [%+.5f, %+.5f] | %.5f | %.5f |"
              % (metric, len(values), mean, low, high, base_level, cand_level))
    print()
    print("### 按局池化（整批 / 分池）")
    print()
    print("| 池 | 臂 | 阶段 | 局 | 爆头进入率 | 胡率 | 庄胡率 | 闲胡率 | 每胡番 | 赢时均分 | 爆头胡占比 | 吃碰/局 | 吃碰机会/局 | 听牌率 | 首听巡目 | 首听种数 |")
    print("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for pool in ("ALL", "H", "M"):
        for arm, bucket in sorted(report["pooled"][pool].items()):
            short = arm.split("/")[-1].replace("OPTY-R18-C27-", "").replace(".py", "")
            print("| %s | %s | %d | %d | %.4f | %.4f | %.4f | %.4f | %.3f | %.3f | %.4f | %.3f | %.3f | %.4f | %.3f | %.3f |"
                  % (pool, short, bucket["stages"], bucket["rounds"], bucket["baotou_rate"],
                     bucket["win_rate"], bucket["dealer_win_rate"], bucket["idle_win_rate"],
                     bucket["fan_per_win"], bucket["win_score_per_win"], bucket["baotou_win_share"],
                     bucket["claims_per_round"],
                     bucket["claim_opportunities_per_round"], bucket["tenpai_rate"],
                     bucket["first_tenpai_turn_mean"], bucket["first_tenpai_kinds_mean"]))
    print()
    print("### 胡牌番分布（焦点座位胡局，按 1/2/4/8 番；分母 = 该臂胡局数）")
    print()
    print("| 池 | 臂 | 胡局 | 1 番 | 2 番 | 4 番 | 8 番 | 其他 | ≥2 番占比 |")
    print("| --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for pool in ("ALL", "H", "M"):
        for arm, bucket in sorted(report["pooled"][pool].items()):
            short = arm.split("/")[-1].replace("OPTY-R18-C27-", "").replace(".py", "")
            wins = max(1, bucket["wins"])
            print("| %s | %s | %d | %d (%.1f%%) | %d (%.1f%%) | %d (%.1f%%) | %d (%.1f%%) | %d | %.1f%% |"
                  % (pool, short, bucket["wins"],
                     bucket["fan1_wins"], 100.0 * bucket["fan1_wins"] / wins,
                     bucket["fan2_wins"], 100.0 * bucket["fan2_wins"] / wins,
                     bucket["fan4_wins"], 100.0 * bucket["fan4_wins"] / wins,
                     bucket["fan8_wins"], 100.0 * bucket["fan8_wins"] / wins,
                     bucket["fan_other_wins"],
                     100.0 * (bucket["wins"] - bucket["fan1_wins"]) / wins))
    integrity = {}
    for pool in ("ALL",) + MIXES:
        for arm, bucket in report["pooled"][pool].items():
            integrity["%s/%s" % (pool, arm)] = {
                "baotou_entry_rounds": bucket["baotou_entry_rounds"],
                "baotou_static_rounds": bucket["baotou_static_rounds"],
                "static_implies_flag": bucket["baotou_static_rounds"] <= bucket["baotou_entry_rounds"],
                "inherited_only_rounds": bucket["baotou_entry_rounds"] - bucket["baotou_static_rounds"],
            }
    report["integrity"] = integrity
    print()
    print("同源核对（静态 any_tile_win ⇒ 观察爆头标记，持续态可继承）：%s"
          % json.dumps(integrity, ensure_ascii=False))
    print()
    print("运行计数：%s" % json.dumps(report["counters"], ensure_ascii=False))

    counters_row = report["counters"]
    score = report["metrics"]["score_per_table"]
    baotou = report["metrics"]["baotou_rate"]
    dealer = report["metrics"]["dealer_win_rate"]
    j1 = bool(score["ci_low"] > 0)
    j2 = bool(baotou["delta_mean"] > 0 and baotou["ci_low"] > 0)
    j3 = bool(counters_row.get("runner_illegal", 0) == 0
              and counters_row.get("runner_timeout", 0) == 0
              and counters_row.get("policy_exceptions", 0) == 0
              and counters_row.get("anomalies", 0) == 0
              and counters_row.get("recorder_errors", 0) == 0
              and maths_safe(dealer["delta_mean"]) >= -0.01)
    same_sign = {}
    for metric in ("score_per_table", "baotou_rate"):
        pools = report["metrics"][metric]["pools"]
        values = [pools[pool]["delta_mean"] for pool in MIXES]
        same_sign[metric] = bool(values[0] > 0 and values[1] > 0) or bool(values[0] < 0 and values[1] < 0)
    j4 = bool(all(same_sign.values()))
    report["judgements"] = {
        "1_score_reproduced": {"pass": j1, "detail": score},
        "2_mechanism_same_direction": {"pass": j2, "detail": baotou},
        "3_auxiliary_not_regressed": {"pass": j3, "detail": {"counters": counters_row,
                                                             "dealer_win_rate": dealer}},
        "4_pool_consistency": {"pass": j4, "detail": same_sign},
    }
    if j1 and j2 and j3 and j4:
        verdict = "第二级通过"
    elif j1 and not j2:
        verdict = "增益机制不明（不通过）"
    else:
        missing = [name for name, ok in (("①积分复现", j1), ("②机制同向", j2),
                                         ("③辅助不退步", j3), ("④池一致", j4)) if not ok]
        verdict = "不通过（缺：" + "、".join(missing) + "）"
    report["verdict"] = verdict
    print()
    print("判定：①积分复现=%s ②机制同向=%s ③辅助不退步=%s ④池一致=%s ⇒ **%s**"
          % (j1, j2, j3, j4, verdict))
    write_json(batch / "mechanics.json", report)
    write_json(batch / "result.json", {
        "schema": SCHEMA,
        "manifest": manifest,
        "root_clusters": [
            {"mix": mix, "root_index": root,
             "score_per_table": {arm: arms[arm]["score_per_table"] for arm in sorted(arms)},
             "delta_score_per_table": (arms[CANDIDATE_ARM]["score_per_table"]
                                       - arms[BASELINE_ARM]["score_per_table"]),
             "delta_vs_baseline_per_table": (arms[CANDIDATE_ARM]["score_per_table"]
                                             - arms[BASELINE_ARM]["score_per_table"]),
             "metrics": {arm: {key: value for key, value in sorted(arms[arm].items())}
                         for arm in sorted(arms)}}
            for (mix, root), arms in sorted(cells.items())],
        "judgements": report["judgements"],
        "verdict": verdict,
    })
    print("写出：%s、%s" % (batch / "mechanics.json", batch / "result.json"))
    return 0


def maths_safe(value: float) -> float:
    """NaN 视为不满足下界条件（缺数据的判定不得当成通过）。"""
    return -1.0 if value is None or (isinstance(value, float) and math.isnan(value)) else float(value)


def command_verify(args: argparse.Namespace) -> int:
    """逐点对拍：本 runner 的 focal_stage_score vs paired_study 参考批。"""
    batch: Path = args.batch
    reference: Path = args.reference
    manifest = json.loads((batch / "manifest.json").read_text(encoding="utf-8"))
    checked = 0
    mismatched = []
    for mix in MIXES:
        for root in range(manifest["root_start"], manifest["root_start"] + manifest["roots_per_mix"]):
            for seat in SEATS:
                for arm in manifest["arms"]:
                    unit = (mix, root, seat, arm, manifest["panel_seed"])
                    mine = unit_path(batch, unit)
                    theirs = unit_path(reference, unit)
                    if not mine.exists() or not theirs.exists():
                        continue
                    a = json.loads(mine.read_text(encoding="utf-8"))["stage"]["focal_stage_score"]
                    b = json.loads(theirs.read_text(encoding="utf-8"))["stage"]["focal_stage_score"]
                    checked += 1
                    if a != b:
                        mismatched.append({"unit": list(unit), "c35": a, "reference": b})
    print("对拍 %d 个阶段单元；不一致 %d 个" % (checked, len(mismatched)))
    for row in mismatched[:20]:
        print("  " + json.dumps(row, ensure_ascii=False))
    return 1 if mismatched else 0


def main(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="跑批（可续跑）")
    run.add_argument("--out", type=Path, required=True)
    run.add_argument("--panel-seed", type=int, default=PANEL_SEED)
    run.add_argument("--root-start", type=int, default=1)
    run.add_argument("--roots-per-mix", type=int, default=99)
    run.add_argument("--workers", type=int, default=8)
    run.set_defaults(func=command_run)
    verdict = sub.add_parser("verdict", help="冻结判定读数")
    verdict.add_argument("--batch", type=Path, required=True)
    verdict.set_defaults(func=command_verdict)
    verify = sub.add_parser("verify", help="与 paired_study 参考批逐点对拍")
    verify.add_argument("--batch", type=Path, required=True)
    verify.add_argument("--reference", type=Path, required=True)
    verify.set_defaults(func=command_verify)
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
