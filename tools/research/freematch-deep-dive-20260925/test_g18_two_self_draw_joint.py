"""G18 实战观察金例：两摸合法性、条件结算与抓打包络对拍。"""

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

from dataclasses import replace
import json

import pytest

import g11_cross_family_action_atlas as atlas
from g18_two_self_draw_joint import _drop, evaluate_root
from hangma_bot.hangma import progression
from hangma_bot.hangma.engine import HangmaRules, _build_context
from hangma_bot.hangma.interface import ValueAnalysisLimits
from hangma_bot.kernel.actions import Discard, Tile
from hangma_bot.kernel.config import RuleConfig
from hangma_bot.kernel.serialization import observation_from_json


def _target():
    """冻结官方完整桌的第 4 单局 seq788；本例不读取赛后暗手或积分。"""

    frozen = json.loads(atlas.FROZEN.read_text(encoding="utf-8"))
    room = next(item for item in frozen["rooms"] if item["room_id"] == "a_3cc4c40be504")
    audit = atlas.source.ROOT / room["audit_dir"]
    for context, raw, _ in atlas.source.screen._iter_decisions(audit):
        if (context.get("game_id"), context.get("round_no"), context.get("trigger_seq")) == (
            "a_3cc4c40be504_r1_b0_t0", 4, 788
        ):
            observation = observation_from_json(raw["observation"])
            legal = {action["action_key"]: action for action in raw["rules"]["legal_candidates"]}
            return observation, legal
    raise AssertionError("冻结官方金例丢失")


def _rules(*, youcai: bool = False):
    return RuleConfig(ruleset_version="hangma-mvp-v10-public-counts",
                      base_score=1, you_cai_bi_kao=youcai)


def test_first_draw_exact_and_restricted_discard_envelope():
    observation, legal = _target()
    parent = evaluate_root(observation, legal["discard:1b"], _rules())
    other = evaluate_root(observation, legal["discard:4b"], _rules())
    assert parent["first_hu_mass"] == 120
    assert other["first_hu_mass"] == 300
    assert parent["first_draw_public_capacity"] == 89
    assert parent["root_whites_held"] == other["root_whites_held"] == 2
    assert all(edge["best_second"]["restricted"]["legal_discard_count"] == 1
               for edge in parent["edges"])
    assert all(edge["best_second"]["restricted"]["best_second_hu"]["discard"] == edge["draw"]
               for edge in parent["edges"])
    assert all(edge["best_second"]["unrestricted"]["best_second_hu"]["mass"] >=
               edge["best_second"]["restricted"]["best_second_hu"]["mass"]
               for edge in parent["edges"])
    one_wan = next(edge for edge in parent["edges"] if edge["draw"] == "1w")
    assert one_wan["best_second"]["unrestricted"]["best_second_hu"]["mass"] == 120
    assert one_wan["best_second"]["unrestricted"]["best_second_hu"]["capacity"] == 88
    assert one_wan["best_second"]["unrestricted"]["best_natural_progress"][
        "ordinary_natural_progress_capacity"] == 10


def test_second_draw_hu_matches_production_rule_analysis():
    observation, _ = _target()
    meld_count = len(observation.melds[observation.seat])
    root = _drop(_build_context(observation).full_hand(), "1b")
    waiting = _drop(root + (Tile("1w"),), "1w")
    root_baotou = progression.baotou_after_discard(root, meld_count)
    first_baotou = progression.baotou_after_draw(
        root_baotou, root, meld_count, Tile("1w"), replacement=False
    )
    root_chain, root_piao = progression.chain_after_action(
        observation.rule_state.chain_count, observation.chain_piao,
        observation.rule_state.baotou, Discard(Tile("1b")),
    )
    chain, piao = progression.chain_after_discard(
        root_chain, root_piao, first_baotou, Tile("1w")
    )
    second_baotou = progression.baotou_after_draw(
        progression.baotou_after_discard(waiting, meld_count), waiting,
        meld_count, Tile("2b"), replacement=False,
    )
    rivers = list(observation.discards)
    rivers[observation.seat] += (Tile("1b"), Tile("1w"))
    counts = list(observation.hand_counts)
    counts[observation.seat] = len(waiting) + 1
    future = replace(
        observation, my_hand=waiting, drawn_tile=Tile("2b"),
        discards=tuple(rivers), hand_counts=tuple(counts),
        remaining_tile_count=max(20, observation.remaining_tile_count - 5),
        rule_state=replace(observation.rule_state, baotou=second_baotou,
                           chain_count=chain, catch_play=False,
                           catch_play_owner_seat=None),
        chain_piao=piao, public_history=(), history_complete=False,
        last_discard=None,
    )
    analysis = HangmaRules(_rules()).analyze(future, value_limits=ValueAnalysisLimits())
    hu = next(candidate for candidate in analysis.legal_candidates if candidate.action_key == "hu")
    assert hu.value_facts.immediate_settlement.score_delta[observation.seat] == 10


def test_future_youcai_rule_switch_fails_closed():
    observation, legal = _target()
    with pytest.raises(ValueError, match="有财必拷响"):
        evaluate_root(observation, legal["discard:1b"], _rules(youcai=True))
