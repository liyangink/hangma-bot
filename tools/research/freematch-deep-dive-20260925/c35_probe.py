#!/usr/bin/env python3
"""C35 探针：验证能否在**不修改任何生产文件**的前提下，从既有引擎取到
焦点座位的**每局机制状态**（爆头、首次听牌、庄位、胡牌与番值），并测机制
计数器的额外开销。

做法：把组合根的运行时装配钩子 \`bootstrap.build_evaluation_runtime\` 临时换成
一个包装版本，只把返回字典里的 \`engine\` 换成**只读转发包装**
（start/frame/advance 原样转发，额外记录既有公开事实），其余键逐字不变。
被包装的引擎是同一个 SimulationEngine 实例，驱动、规则与策略路径零变化。

本探针只跑 1 个阶段单元（1 根 × 1 座位 × 1 臂），打印：
  * 每个决策窗口焦点座位的可见事实形状（暗牌张数/phase/爆头标记）；
  * 每局结束后的**公开单局记录**（庄/胡家/番/流局/增量）；
  * 每次裁决的选项结构（吃碰杠动作能否从 choice 直接分类）；
  * \`hangma\` 口径函数的单次耗时（用于估算机制计数器开销）；
  * 阶段积分（与 paired_study 同一口径）。
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

import json
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = _PROJECT_ROOT
ROUTE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15')
for entry in (_project_file(_PROJECT_ROOT, ROOT / "src"), _project_file(_PROJECT_ROOT, ROUTE / "tools"), _project_file(_PROJECT_ROOT, ROOT / "review/r18-four-arm-evaluation-2026-09-23")):
    sys.path.insert(0, str(entry))

import paired_study  # noqa: E402
import sitin_natural_panel as natural  # noqa: E402
from hangma_bot import bootstrap  # noqa: E402
from hangma_bot.hangma import hand_analysis  # noqa: E402
from hangma_bot.hangma.engine import HangmaRules  # noqa: E402
from hangma_bot.kernel.actions import Chi, Gang, Peng  # noqa: E402

PANEL_SEED = 2026110101
CLAIM_TYPES = (Chi, Peng, Gang)


class RecordingEngine:
    """只读转发包装：不改任何决策输入，只记录已公开事实。"""

    def __init__(self, inner, focal_seat, rules):
        self._inner = inner
        self._focal = int(focal_seat)
        self._rules = rules
        self.windows = []
        self.rounds = []
        self.choices = Counter()
        self.tables_done = 0

    def start(self, spec):
        world = self._inner.start(spec)
        self._record(world)
        return world

    def frame(self, world):
        frame = self._inner.frame(world)
        for decision in frame.decisions:
            window_key = decision.window_key
            if int(window_key.seat) != self._focal:
                continue
            obs = decision.observation
            meld_count = len(obs.melds[self._focal])
            self.windows.append({
                "seat": int(window_key.seat),
                "round_no": int(obs.round_no),
                "phase": str(obs.phase),
                "seq": int(window_key.trigger_seq),
                "hand": len(obs.my_hand),
                "drawn": None if obs.drawn_tile is None else obs.drawn_tile.code,
                "baotou": bool(obs.rule_state.baotou),
                "chain": int(obs.rule_state.chain_count),
                "melds": meld_count,
                "my_discards": len(obs.discards[self._focal]),
                "wall": obs.remaining_tile_count,
                "dealer": int(obs.dealer_seat),
                "_obs": obs,
            })
        return frame

    def advance(self, world, revision, choices):
        for choice in choices:
            if int(choice.window_key.seat) == self._focal:
                self.choices[type(choice.action).__name__] += 1
        new_world = self._inner.advance(world, revision, choices)
        self._record(new_world)
        return new_world

    def _record(self, world):
        for record in list(getattr(world, "round_records", ()) or ()):
            if any(row["round_no"] == record.round_no for row in self.rounds):
                continue
            self.rounds.append({
                "round_no": int(record.round_no),
                "dealer": int(record.dealer_seat),
                "winner": None if record.winner_seat is None else int(record.winner_seat),
                "draw": bool(record.is_draw),
                "fan": int(record.fan),
                "delta": [int(x) for x in record.score_delta],
            })


def main() -> int:
    contract = json.loads(paired_study.CONTRACT.read_text(encoding="utf-8"))
    plans = natural.build_seat_stage_plans(contract=contract, opponent="H", root_index=1,
                                           focal_seat=0, panel_seed=PANEL_SEED)
    focal = plans[0].permutation[list(plans[0].logical_participants).index("focal")]
    sinks = []
    original = bootstrap.build_evaluation_runtime

    def patched(kind, experiment):
        runtime = original(kind, experiment)
        if runtime is None:
            return runtime
        rules = HangmaRules(experiment.tournament_config.rules)
        sink = RecordingEngine(runtime["engine"], focal, rules)
        sinks.append(sink)
        return {**runtime, "engine": sink}

    bootstrap.build_evaluation_runtime = patched
    started = time.monotonic()
    try:
        stage = natural.run_arm_stage(
            arm="candidate", plans=plans, candidate_scorer=None,
            candidate_policy_factory=paired_study.policy_factory("r18_v2"),
            opponent_policies=contract["panel"]["opponent_scenarios"]["H"]["opponent_policies"],
            versions_block=natural.stage.contract_versions_block(contract),
            step_limit=int(contract["stop"]["step_limit"]),
            value_limits=paired_study.LIMITS)
    finally:
        bootstrap.build_evaluation_runtime = original
    wall = time.monotonic() - started

    print("阶段状态=%s 焦点物理座位(table1)=%d 用时=%.1fs 积分=%s"
          % (stage["status"], focal, wall, stage["focal_stage_score"]))
    print("每桌 sink 数=%d（应等于桌数 %d）" % (len(sinks), len(stage["tables"])))
    for index, sink in enumerate(sinks):
        print("  桌%d：窗口 %d、单局记录 %d %s" % (
            index + 1, len(sink.windows), len(sink.rounds),
            json.dumps(sink.rounds, ensure_ascii=False)))
        print("      焦点动作分类=%s" % json.dumps(dict(sink.choices), ensure_ascii=False))
    windows = [row for row in sinks[0].windows]
    print("phase 计数=%s" % json.dumps(dict(Counter(r["phase"] for r in windows)), ensure_ascii=False))
    print("(phase, 暗牌张数) 计数=%s" % json.dumps(
        {"%s/%d" % (r["phase"], r["hand"]): 0 for r in []} or
        {k: v for k, v in Counter("%s|hand%d|melds%d" % (r["phase"], r["hand"], r["melds"])
                                  for r in windows).items()}, ensure_ascii=False))
    print("爆头标记为真的窗口数=%d" % sum(1 for r in windows if r["baotou"]))

    # 口径对拍 1：摸牌窗口静态 any_tile_win vs 观察里的持续爆头标记
    agree = Counter()
    from hangma_bot.kernel.actions import Tile
    for row in windows:
        if row["phase"] != "draw" or row["drawn"] is None:
            continue
        obs = row["_obs"]
        static = hand_analysis.any_tile_win(tuple(obs.my_hand), len(obs.melds[focal]))
        agree["static"] += int(static)
        agree["flag"] += int(row["baotou"])
        agree["both"] += int(static and row["baotou"])
        agree["flag_only"] += int(row["baotou"] and not static)
    print("摸牌窗口静态对拍=%s" % json.dumps(agree, ensure_ascii=False))

    # 耗时：rules.analyze（无 value_limits）与 analyse_hand
    samples = [row["_obs"] for row in windows if row["phase"] == "draw"][:150]
    from hangma_bot.kernel.config import RuleConfig
    block = natural.stage.contract_versions_block(contract)
    rules = HangmaRules(RuleConfig(ruleset_version=str(block["ruleset_version"]),
                                   base_score=int(block["base_score"]),
                                   you_cai_bi_kao=bool(block["you_cai_bi_kao"])))
    t0 = time.monotonic()
    for obs in samples:
        rules.analyze(obs)
    t1 = time.monotonic()
    for obs in samples:
        full = tuple(obs.my_hand) + (() if obs.drawn_tile is None else (obs.drawn_tile,))
        hand_analysis.analyse_hand(full, len(obs.melds[focal]))
    t2 = time.monotonic()
    n = max(1, len(samples))
    print("rules.analyze 平均 %.3f ms/窗口；analyse_hand(14 张) 平均 %.3f ms/窗口（n=%d）"
          % ((t1 - t0) * 1000 / n, (t2 - t1) * 1000 / n, n))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
