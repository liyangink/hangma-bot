"""VIP 自然价值账：整根完整性与分层包含概率口径。"""

from dataclasses import replace
from itertools import product

import pytest

from hangma_bot.offline.evaluation_results import GameKey, SIMULATION_SOURCE_NAMESPACE
from hangma_bot.offline.vip_evaluation import FrozenRoot, audit_vip_batch
from support import make_match_result


PERMUTATIONS = (
    (0, 1, 2, 3),
    (1, 2, 3, 0),
    (2, 3, 0, 1),
    (3, 0, 1, 2),
)


def root(draws=(0.0, 0.0, 0.0, 0.0)):
    return FrozenRoot("r1", PERMUTATIONS, ("ordinary", "ordinary", "rare", "ordinary"), draws)


def rows(deltas=(1, -3, 12, 2)):
    output = []
    for index, (permutation, delta) in enumerate(zip(PERMUTATIONS, deltas)):
        focal = permutation[0]
        a_ids, c_ids = ["opp"] * 4, ["opp"] * 4
        a_ids[focal], c_ids[focal] = "A", "C"
        a_scores, c_scores = [0] * 4, [0] * 4
        c_scores[focal] = delta
        common = dict(
            scenario_id="r1", pair_id=f"r1:{''.join(map(str, permutation))}",
            seat_permutation=permutation,
            game_key=GameKey(SIMULATION_SOURCE_NAMESPACE, "r1", f"m-{index}"),
            versions=(("rules_hash", "rules-abc"), ("ruleset_version", "fixture-rules"),
                      ("simulation_version", "simulation-v1")),
        )
        output.append(make_match_result(
            **common, result_id=f"a{index}", policy_ids_by_seat=tuple(a_ids),
            scores_after=tuple(a_scores),
        ))
        output.append(make_match_result(
            **common, result_id=f"c{index}", policy_ids_by_seat=tuple(c_ids),
            scores_after=tuple(c_scores),
        ))
    return output


def audit(frame, results, probabilities=None):
    return audit_vip_batch(
        frame, probabilities or {"ordinary": 1.0, "rare": 1.0}, results,
        baseline_policy_id="A", challenger_policy_id="C",
    )


def test_full_four_seat_reconstructs_natural_mean_and_strata():
    result = audit([root()], rows())
    assert result.confirmable
    assert (result.frame_root_count, result.selected_root_count, result.complete_root_count) == (1, 1, 1)
    assert dict(result.frame_stratum_counts) == {"ordinary": 3, "rare": 1}
    assert result.natural_score_delta == pytest.approx(3.0)
    assert dict(result.stratum_contributions) == pytest.approx({"ordinary": 0.0, "rare": 3.0})


def test_missing_mapping_blocks_whole_batch_instead_of_survivor_mean():
    result = audit([root()], rows()[:-2])
    assert not result.confirmable
    assert result.selected_root_count == 1 and result.complete_root_count == 0
    assert result.natural_score_delta is None
    assert result.stratum_contributions == ()
    assert "缺少" in " ".join(result.roots[0].issues)


def test_mechanical_gap_and_candidate_fallback_are_not_strength_rows():
    data = rows()
    data[3] = replace(data[3], status="error", invalid_reasons=("MECHANICAL_GAP",))
    result = audit([root()], data)
    assert not result.confirmable
    assert "MECHANICAL_GAP" in " ".join(result.roots[0].issues)

    data = rows()
    counts = data[1].runtime_counts
    data[1] = replace(data[1], runtime_counts=replace(counts, fallbacks=1))
    assert not audit([root()], data).confirmable


def test_heterogeneous_filter_uses_root_inclusion_probability():
    probabilities = {"ordinary": 0.1, "rare": 0.5}
    result = audit_vip_batch([root()], probabilities, rows(), baseline_policy_id="A", challenger_policy_id="C")
    assert result.roots[0].inclusion_probability == pytest.approx(0.6355)
    assert result.natural_score_delta == pytest.approx(3 / 0.6355)

    # 对 2^4 种筛选结果逐一求期望，不能把补齐四座后的权重错用成 1/b_h。
    expected = 0.0
    for picked in product((False, True), repeat=4):
        chance = 1.0
        for label, flag in zip(root().strata, picked):
            b = probabilities[label]
            chance *= b if flag else (1 - b)
        draws = tuple(0.0 if flag else 0.999 for flag in picked)
        selected = any(picked)
        experiment = audit_vip_batch(
            [root(draws)], probabilities, rows() if selected else [],
            baseline_policy_id="A", challenger_policy_id="C",
        )
        expected += chance * (experiment.natural_score_delta or 0.0)
    assert expected == pytest.approx(3.0)


def test_unselected_root_with_rows_and_duplicate_row_are_rejected():
    probabilities = {"ordinary": 0.1, "rare": 0.5}
    with pytest.raises(ValueError, match="未抽中根"):
        audit_vip_batch([root((0.9,) * 4)], probabilities, rows(), baseline_policy_id="A", challenger_policy_id="C")
    with pytest.raises(ValueError, match="重复结果行"):
        audit([root()], rows() + rows()[:1])


def test_no_root_selected_has_no_strength_estimate():
    result = audit_vip_batch(
        [root((0.9,) * 4)], {"ordinary": 0.1, "rare": 0.5}, [],
        baseline_policy_id="A", challenger_policy_id="C",
    )
    assert not result.confirmable
    assert result.natural_score_delta is None


def test_frame_requires_four_distinct_focal_seats():
    with pytest.raises(ValueError, match="不同座位映射"):
        FrozenRoot("r1", (PERMUTATIONS[0], PERMUTATIONS[0], PERMUTATIONS[1], PERMUTATIONS[2]),
                   ("ordinary",) * 4, (0.0,) * 4)
    with pytest.raises(ValueError, match="焦点身份"):
        FrozenRoot("r1", (PERMUTATIONS[0], (0, 2, 1, 3), PERMUTATIONS[1], PERMUTATIONS[2]),
                   ("ordinary",) * 4, (0.0,) * 4)


@pytest.mark.parametrize("field,value,reason", [
    ("config", None, "缺少赛事配置"),
    ("scores_before", None, "缺少初始积分"),
    ("expected_hands", None, "缺少计划单局数"),
    ("expected_hands", 7, "计划单局数与赛事配置不一致"),
])
def test_missing_mandatory_pair_facts_block_confirmation(field, value, reason):
    data = rows()
    data[0] = replace(data[0], **{field: value})
    result = audit([root()], data)
    assert not result.confirmable
    assert reason in " ".join(result.roots[0].issues)


@pytest.mark.parametrize("key", ("rules_hash", "ruleset_version", "simulation_version"))
def test_both_arms_missing_same_version_does_not_pass(key):
    data = rows()
    for position in (0, 1):
        versions = tuple(item for item in data[position].versions if item[0] != key)
        data[position] = replace(data[position], versions=versions)
    result = audit([root()], data)
    assert not result.confirmable
    assert f"缺少 {key}" in " ".join(result.roots[0].issues)


def test_equal_but_unbound_pair_id_is_rejected():
    data = rows()
    for position in (0, 1):
        data[position] = replace(data[position], pair_id="some-other-pair")
    result = audit([root()], data)
    assert not result.confirmable
    assert "配对身份未绑定根和座位映射" in " ".join(result.roots[0].issues)


@pytest.mark.parametrize("field,value,reason", [
    ("config", None, "缺少赛事配置"),
    ("scores_before", None, "缺少初始积分"),
    ("expected_hands", None, "缺少计划单局数"),
])
def test_both_arms_missing_same_fact_does_not_pass(field, value, reason):
    data = rows()
    for position in (0, 1):
        data[position] = replace(data[position], **{field: value})
    result = audit([root()], data)
    assert not result.confirmable
    assert reason in " ".join(result.roots[0].issues)
