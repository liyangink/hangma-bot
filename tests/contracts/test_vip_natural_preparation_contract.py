"""自然面子准备从真实观察到受限公式的完整公开接缝契约。"""

from dataclasses import replace

import pytest

from hangma_bot.hangma.natural_preparation import NATURAL_PREPARATION_SEMANTICS_VERSION
from hangma_bot.policy.action_value_executor import ActionValueExecutor
from hangma_bot.policy.route_vip_heuristic import build_vip_route_scoring_view, compute_vip_candidate_identity
from tests.unit.policy.test_route_vip_heuristic import CONFIG, _draw_observation, _request


@pytest.fixture(scope="module")
def preparation_view():
    """T38零白形状只重建公开牌形，不载入历史世界或结果。"""
    request = _request(_draw_observation((
        "2w", "3w", "4w", "4b", "6b", "9b", "9b", "9b",
        "5t", "5t", "5t", "7t", "8t",
    ), drawn="9t"))
    return build_vip_route_scoring_view(request, CONFIG)


def test_preparation_separates_natural_set_damage_at_same_real_shanten(preparation_view):
    mapping = preparation_view.candidate_view()
    nodes = {node["node_key"]: node for node in mapping["nodes"]}
    roots = {action["action_key"]: nodes[action["node_key"]]["waiting"]
             for action in mapping["actions"] if action["action_type"] == "discard"}
    broken, kept = roots["discard:5t"], roots["discard:6b"]
    assert broken["structure"]["standard_shanten"] == kept["structure"]["standard_shanten"] == 0
    assert broken["natural_preparation"]["whites_held"] == kept["natural_preparation"]["whites_held"] == 0
    assert broken["natural_preparation"]["natural_draw_lower_bound"] == 1
    assert kept["natural_preparation"]["natural_draw_lower_bound"] == 0
    assert mapping["binding"]["natural_preparation_semantics_version"] == NATURAL_PREPARATION_SEMANTICS_VERSION
    source = '''
def score_actions(view):
    scores = {node["node_key"]: -node["waiting"]["natural_preparation"]["natural_draw_lower_bound"] if node["waiting"] is not None else 0.0 for node in view["nodes"]}
    return {"status":"SCORED", "entries":[{"action_key":a["action_key"], "score":scores[a["node_key"]], "trace":{}} for a in view["actions"]]}
'''
    scores = {entry.action_key: entry.score for entry in ActionValueExecutor(source).score_vip_route(preparation_view).entries}
    assert scores["discard:6b"] > scores["discard:5t"]


def test_preparation_cannot_be_borrowed_from_a_different_real_hand(preparation_view):
    waiting = next(node.waiting for node in preparation_view.nodes if node.waiting is not None)
    with pytest.raises(ValueError, match="真实结构"):
        replace(waiting, natural_preparation=replace(waiting.natural_preparation, whites_held=1))
    with pytest.raises(ValueError, match="准备语义"):
        replace(preparation_view, natural_preparation_semantics_version="unknown-semantics")
    with pytest.raises(ValueError, match="版本"):
        replace(preparation_view, schema_version="vip-route-scoring-view/2")


def test_new_semantics_changes_candidate_identity(monkeypatch):
    from hangma_bot.policy import route_vip_heuristic

    original = compute_vip_candidate_identity("source", "contract", "dependencies")
    monkeypatch.setattr(route_vip_heuristic, "NATURAL_PREPARATION_SEMANTICS_VERSION", "different-preparation")
    assert compute_vip_candidate_identity("source", "contract", "dependencies") != original
