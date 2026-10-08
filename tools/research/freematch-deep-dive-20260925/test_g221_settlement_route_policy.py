"""G221 同窗生产规则改弃及整窗预算的定向回归。"""

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
import json
import time

import pytest

import c31_action_layer_gap as c31
import g196_three_draw_competing_route_pilot as g196
import g217_two_step_natural_route_preflight as source
import g219_two_draw_settlement_route as g219
import g221_settlement_route_policy as g221
from hangma_bot.application.deadline import BudgetPolicy


def _official_window():
    """G219 已归档的一张实际同层强手窗，只提供玩家可见状态。"""
    row = next(row for row in g219.selected_rows()
               if row["room"] == "a_5e16dfc1305b"
               and row["round_no"] == 3 and row["draw_seq"] == 595)
    batch = json.loads((source.G61 / "result.json").read_text(encoding="utf-8"))
    observation = source._observation(row, batch["units"], {})
    request = source.g87.request_for(observation)
    plan = asyncio.run(source.candidate.g210.parent_factory(None).choose(
        request, BudgetPolicy().build(800.0, 3.0)))
    return request, plan


def test_same_shanten_settlement_trade_stays_legal_and_balanced() -> None:
    """非严格加宽动作可因互斥胡分胜出，且分量严格守恒。"""
    request, parent = _official_window()
    chosen, evidence = g221.select(request, parent)
    legal = {item.action_key: item for item in request.rules.legal_candidates}
    assert parent.candidates[0].action_key == "discard:3b"
    assert chosen == "discard:1w"
    assert chosen in legal
    assert legal[chosen].facts.standard_shanten_after == legal["discard:3b"].facts.standard_shanten_after
    assert evidence["type_gain"] == 0 and evidence["capacity_gain"] == 2
    assert evidence["half_total_gain"] == pytest.approx(
        evidence["half_plain_gain"] + evidence["half_special_gain"], abs=1e-8)
    ranked = {item.action_key: item for item in parent.candidates}
    assert g221.g210._risk(ranked[chosen]) <= g221.g210._risk(ranked["discard:3b"])


def test_expired_absolute_deadline_stops_before_rule_search() -> None:
    """单臂搜索内部每个条件胡终点都接受同一整窗截止。"""
    request, _parent = _official_window()
    search = g221.BoundedSearch(
        request.observation, c31.RULE_CONFIG, "discard:3b",
        restricted=False, deadline=time.perf_counter() - 1.0)
    with pytest.raises(g196.RouteLimitExceeded, match="内部预算截止"):
        search._win(search.root, "1w", baotou=search.root_baotou,
                    chain=search.root_chain, piao=search.root_piao, depth=1)
