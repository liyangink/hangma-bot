"""R17 单叶候选复用硬化执行器的静态与动态边界。"""

import pytest

from hangma_bot.hangma.engine import HangmaRules
from hangma_bot.hangma.interface import ValueAnalysisLimits
from hangma_bot.kernel.actions import Tile
from hangma_bot.kernel.config import RuleConfig
from hangma_bot.policy.action_value_executor import StaticCheckError
from hangma_bot.policy.public_successor_leaf_executor import (
    LEAF_FIRST_PARTY_DIGEST_MODULES,
    LeafProgramExecutor,
    compute_leaf_candidate_identity,
    compute_leaf_deps_digest,
)
from hangma_bot.policy.public_successor_search import reduce_public_successors

from .support import make_observation, make_request


SOURCE = '''
def score_actions(view):
    root = view["root"]
    next_leaf = view["next"]
    value = 0.3 * (root["shanten_after"] - next_leaf["shanten_after"])
    value += 0.01 * next_leaf["support_remaining"]
    if next_leaf["replacement_draw_unknown"]:
        value -= 0.1
    return max(-1.0, min(1.0, value))
'''


def _inputs():
    observation = make_observation(
        my_hand=tuple(
            Tile(code)
            for code in (
                "1w", "2w", "3w", "4w", "5w", "6w", "7w",
                "8w", "9w", "1b", "2b", "3b", "东",
            )
        ),
        drawn_tile=Tile("南"),
        scores=(10, 0, -5, -5),
    )
    rules = HangmaRules(RuleConfig("r17-leaf-executor-test", 1, False))
    analysis = rules.analyze(
        observation,
        value_limits=ValueAnalysisLimits(20_000, 128),
    )
    return (
        make_request(observation, analysis),
        rules.analyze_public_self_draw_successors(observation),
    )


def test_restricted_program_scores_complete_real_graph_with_window_meter() -> None:
    request, successors = _inputs()
    executor = LeafProgramExecutor(SOURCE)
    scorer = executor.window_scorer()
    reduced = reduce_public_successors(request, successors, scorer)
    assert reduced.complete, reduced.reason
    assert scorer.leaf_count == sum(item.leaf_evaluations for item in reduced.roots)
    assert 0 < scorer.operation_count <= executor.max_operations_per_window


def test_static_subset_rejects_import_and_wrong_entrypoint() -> None:
    with pytest.raises(StaticCheckError):
        LeafProgramExecutor("import os\ndef score_actions(view):\n    return 0.0\n")
    with pytest.raises(StaticCheckError):
        LeafProgramExecutor("def score_leaf(leaf):\n    return 0.0\n")


def test_per_leaf_and_per_window_operation_limits_fail_whole_reduction() -> None:
    request, successors = _inputs()
    loop_source = '''
def score_actions(view):
    total = 0
    for index in range(100):
        total += index
    return 0.0
'''
    per_leaf = LeafProgramExecutor(loop_source, max_operations_per_leaf=50)
    failed = reduce_public_successors(
        request, successors, per_leaf.window_scorer()
    )
    assert not failed.complete
    assert "受限执行工作量" in failed.reason

    per_window = LeafProgramExecutor(
        "def score_actions(view):\n"
        "    return float(view[\"next\"][\"support_remaining\"]) * 0.0\n",
        max_operations_per_window=10,
    )
    failed = reduce_public_successors(
        request, successors, per_window.window_scorer()
    )
    assert not failed.complete
    assert "整窗操作数超过固定上限" in failed.reason


@pytest.mark.parametrize(
    "source,reason",
    [
        ("def score_actions(view):\n    return True\n", "必须返回一个数值"),
        ("def score_actions(view):\n    return 2.0\n", "必须在 [-1, 1]"),
    ],
)
def test_invalid_program_output_fails_whole_reduction(source, reason) -> None:
    request, successors = _inputs()
    failed = reduce_public_successors(
        request, successors, LeafProgramExecutor(source).window_scorer()
    )
    assert not failed.complete
    assert reason in failed.reason


def test_leaf_identity_covers_contract_dependencies_source_and_params() -> None:
    files = {name: "content:" + name for name in LEAF_FIRST_PARTY_DIGEST_MODULES}
    deps = compute_leaf_deps_digest(files)
    identity = compute_leaf_candidate_identity(SOURCE, "contract-sha", deps, {"x": 1})
    assert identity == compute_leaf_candidate_identity(
        SOURCE, "contract-sha", deps, {"x": 1}
    )
    assert identity != compute_leaf_candidate_identity(
        SOURCE + "\n", "contract-sha", deps, {"x": 1}
    )
    assert identity != compute_leaf_candidate_identity(
        SOURCE, "other-contract", deps, {"x": 1}
    )
    assert identity != compute_leaf_candidate_identity(
        SOURCE, "contract-sha", deps, {"x": 2}
    )
    changed = dict(files)
    changed[LEAF_FIRST_PARTY_DIGEST_MODULES[0]] += "!"
    assert deps != compute_leaf_deps_digest(changed)


def test_leaf_dependency_digest_requires_exact_first_party_closure() -> None:
    files = {name: name for name in LEAF_FIRST_PARTY_DIGEST_MODULES[:-1]}
    with pytest.raises(ValueError, match="第一方依赖集合不一致"):
        compute_leaf_deps_digest(files)
