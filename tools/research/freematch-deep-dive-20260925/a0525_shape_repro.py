#!/usr/bin/env python3
"""重放 a_0525f4514164 第 6 单局的两次争议弃牌，检测同分盲区。

只输出牌码、分数和判据；原始审计可能含运行身份，不整行打印。
退出码 1 表示线上冻结评分器仍将数牌与西并列、按键序弃数牌。
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
from dataclasses import replace
from pathlib import Path

from hangma_bot.application.audit_codec import decision_request_from_json
from hangma_bot.hangma.engine import HangmaRules
from hangma_bot.kernel.actions import Tile
from hangma_bot.kernel.config import RuleConfig
from hangma_bot.policy.action_value_policy import build_scoring_view
from hangma_bot.policy.action_value_seeds import ActionValueScorer
from hangma_bot.policy.r18_integrated_positive_v2 import (
    R18_INTEGRATED_POSITIVE_V2_NAME,
    R18_INTEGRATED_POSITIVE_V2_SOURCE,
)


AUDIT = Path(
    "artifacts/sessions/r18-sse-freematch-campaign-20260925b/audit/runs/"
    "run-147bb0adc21e47e783abb465f6b68388/participants/"
    "u_13495c3d79c8/decisions.jsonl"
)
GAME = "a_0525f4514164_r1_b1_t0"
TARGETS = {1274: "discard:1b", 1350: "discard:4w"}
FOLLOWUPS = (1376, 1402)


def _top_score(scorer: ActionValueScorer, request):
    """返回冻结候选在一个可见决策请求上的首选与完整分表。"""
    batch = scorer.score(build_scoring_view(request))
    scores = {entry.action_key: entry.score for entry in batch.entries}
    return sorted(scores, key=lambda key: (-scores[key], key))[0], scores


def _west_first_counterfactual(request):
    """只交换 1351 本人弃牌与持牌；不声称他家反应或未来墙保持不变。"""
    observation = request.observation
    seat = observation.seat
    hand = list(observation.my_hand)
    hand[hand.index(Tile("西"))] = Tile("4w")
    rivers = [list(river) for river in observation.discards]
    rivers[seat][rivers[seat].index(Tile("4w"))] = Tile("西")
    history = tuple(
        replace(event, tiles=(Tile("西"),))
        if event.seq == 1351 and event.kind == "tile_discarded"
        else event
        for event in observation.public_history
    )
    altered = replace(
        observation,
        my_hand=tuple(hand),
        discards=tuple(tuple(river) for river in rivers),
        public_history=history,
    )
    rules = HangmaRules(RuleConfig(request.rules.ruleset_version, 1, False))
    return replace(request, observation=altered, rules=rules.analyze(altered))


def main() -> int:
    """从真实决策输入重算评分；发现同分且机械键序选数牌则返回 1。"""
    if not AUDIT.is_file():
        raise SystemExit(f"审计输入缺失：{AUDIT}")
    requests = {}
    for line in AUDIT.read_text().splitlines():
        record = json.loads(line)
        context = record.get("context") or {}
        seq = context.get("trigger_seq")
        if (
            record.get("kind") == "decision_input"
            and context.get("game_id") == GAME
            and context.get("round_no") == 6
            and seq in set(TARGETS) | set(FOLLOWUPS)
        ):
            requests[seq] = decision_request_from_json(record["payload"]["request"])
    if set(requests) != set(TARGETS) | set(FOLLOWUPS):
        raise SystemExit(f"目标决策输入不完整：{sorted(requests)}")
    scorer = ActionValueScorer(
        R18_INTEGRATED_POSITIVE_V2_NAME, R18_INTEGRATED_POSITIVE_V2_SOURCE
    )
    failures = []
    for seq in sorted(TARGETS):
        chosen, scores = _top_score(scorer, requests[seq])
        suited = TARGETS[seq]
        west = "discard:西"
        if suited not in scores or west not in scores:
            raise SystemExit(f"seq={seq} 缺少对照动作")
        tied = scores[suited] == scores[west]
        print(
            f"seq={seq} top={chosen} {suited}={scores[suited]} "
            f"{west}={scores[west]} tie={tied}"
        )
        by_key = {
            action.action_key: action
            for action in build_scoring_view(requests[seq]).actions
        }
        for key in ("discard:1b", "discard:西", "discard:4b", "discard:4w"):
            action = by_key.get(key)
            if action is None:
                continue
            standard = action.standard_useful_tiles or ()
            seven = action.seven_pairs_useful_tiles or ()
            combined = action.useful_tiles or ()
            print(
                f"  {key}: sh={action.shanten_after}, "
                f"standard={action.standard_shanten_after}/"
                f"{sum(tile.remaining_estimate for tile in standard)}张/"
                f"{len(standard)}种, "
                f"seven={action.seven_pairs_shanten_after}/"
                f"{sum(tile.remaining_estimate for tile in seven)}张/"
                f"{len(seven)}种, "
                f"combined={sum(tile.remaining_estimate for tile in combined)}张/"
                f"{len(combined)}种"
            )
        if tied and chosen == suited:
            failures.append(seq)
    for seq in FOLLOWUPS:
        chosen, _ = _top_score(
            scorer, _west_first_counterfactual(requests[seq])
        )
        print(f"条件重放 seq={seq} 若先弃西，则此窗首选={chosen}")
    if failures:
        print(f"RED：同分按键序弃数牌，seq={failures}")
        return 1
    print("GREEN：争议数牌不再因同分键序被弃")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
