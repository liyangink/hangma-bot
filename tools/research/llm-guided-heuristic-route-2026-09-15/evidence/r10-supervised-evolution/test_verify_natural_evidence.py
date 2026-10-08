"""历史桌赛摘要复算及篡改反例：仅内存核算，零新桌赛和模型调用。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
import copy
import json
from pathlib import Path

import pytest

import verify_natural_evidence as verify

HERE = Path(__file__).resolve().parent
PILOT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r9-takeover-2026-09-19/pilot/run/iterations')
CONTRACT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/contracts/group-dev-v1.json')


def fixture(iteration="iter-02", mix="H"):
    """读取已消费开发根，独立保存期望身份；测试不会改写历史产物。"""
    panel = json.loads((_project_file(_PROJECT_ROOT, PILOT / iteration / f"natural-{mix}/panel.json")).read_text())
    return panel, json.loads(CONTRACT.read_text()), copy.deepcopy(panel["identity"])


def check(panel, contract, identity, roots=(1,)):
    return verify.verify_panel(panel, contract, expected_identity=identity, expected_root_indices=roots)


@pytest.mark.parametrize("iteration,mix,expected_mean", [
    ("iter-02", "H", 0.0), ("iter-02", "M", 0.0),
    ("iter-03", "H", -0.75), ("iter-03", "M", -0.25),
])
def test_historical_raw_totals_and_target_reconcile(iteration, mix, expected_mean):
    panel, contract, identity = fixture(iteration, mix)
    result = check(panel, contract, identity)
    assert result["n_roots"] == 1
    assert result["n_table_summaries"] == 16
    assert result["selection_eligible"] is False and result["release_eligible"] is False
    assert result["statistics"]["by_candidate"][identity["candidate_id"]]["panels"]["normal"][
        "panels"][mix]["mean_delta"] == expected_mean


@pytest.mark.parametrize("mutation", [
    lambda p: p["samples"].pop(),
    lambda p: p["samples"].append(copy.deepcopy(p["samples"][0])),
    lambda p: p["samples"][0].update(focal_anchor_seat=True),
    lambda p: p["samples"][0].update(root_index=2),
    lambda p: p["samples"][0].update(source_root_id="renamed"),
    lambda p: p["samples"][0].update(root_content_digest="0" * 64),
    lambda p: p["samples"][0].update(root_seed=10),
    lambda p: p["samples"][0].update(opponent_mix="M"),
    lambda p: p["samples"][0].update(self_comparison=True),
    lambda p: p["samples"][0]["root_expected"].update(seats=4.0),
    lambda p: p["samples"][0]["seat_participants_by_table"][0].reverse(),
    lambda p: p["samples"][0]["table_seeds"].__setitem__(0, 1),
    lambda p: p["samples"][0]["table_ids"].reverse(),
    lambda p: p["samples"][0]["raw_arms"].pop("candidate"),
    lambda p: p["samples"][0]["raw_arms"]["candidate"]["tables"].pop(),
    lambda p: p["samples"][0]["raw_arms"]["candidate"]["tables"].reverse(),
    lambda p: p["samples"][0]["raw_arms"]["candidate"]["tables"][0].update(seed=0),
    lambda p: p["samples"][0]["raw_arms"]["candidate"]["tables"][0].update(match_status="step_limit"),
    lambda p: p["samples"][0]["raw_arms"]["candidate"]["tables"][0].update(scores_by_seat=[1, 2, 3, 4]),
    lambda p: p["samples"][0]["raw_arms"]["candidate"]["tables"][0].update(scores_by_seat=[0, 0, 0, False]),
    lambda p: p["samples"][0]["raw_arms"]["candidate"]["tables"][0].update(scores_by_seat=[0, 0, 0, 0.0]),
    lambda p: p["samples"][0]["raw_arms"]["candidate"]["tables"][1]["stage_situation"].update(
        stage_scores_by_seat=[0, 0, 0, 0]),
    lambda p: p["samples"][0]["raw_arms"]["candidate"]["tables"][1]["stage_situation"].update(
        rounds_per_game=7),
    lambda p: p["samples"][0]["raw_arms"]["candidate"].update(focal_stage_score=123),
    lambda p: p["samples"][0]["raw_arms"]["candidate"]["stage_place_points_by_participant"].update(focal=100),
    lambda p: p["samples"][0]["raw_arms"]["candidate"]["u_interval"].update(a=1),
    lambda p: p["samples"][0]["arms"]["baseline"].update(candidate_id="other-baseline"),
    lambda p: p["samples"][0]["arms"]["baseline"].update(policy_id="weighted_heuristic_v1"),
    lambda p: p["samples"][0]["arms"]["candidate"].update(u_low=False),
    lambda p: p["samples"][0]["arms"]["candidate"].update(u_high=float("nan")),
    lambda p: p["statistics"].update(n_samples=100),
    lambda p: p["config"].update(seats_per_root=3),
    lambda p: p["config"]["focal_policy"].update(baseline="weighted_heuristic_v1"),
    lambda p: p["identity"].update(stage_projection="unknown"),
])
def test_missing_drifted_or_corrupt_evidence_rejected(mutation):
    panel, contract, identity = fixture()
    mutation(panel)
    with pytest.raises(ValueError):
        check(panel, contract, identity)


def test_fabricating_both_raw_and_slim_u_cannot_bypass_recalculation():
    panel, contract, identity = fixture()
    for label in ("raw_arms", "arms"):
        panel["samples"][0][label]["candidate"].update(u=0.0, u_low=0.0, u_high=0.0)
    with pytest.raises(ValueError, match="u_low"):
        check(panel, contract, identity)


def test_deleting_an_entire_root_cannot_override_external_frozen_list():
    panel, contract, identity = fixture()
    with pytest.raises(ValueError, match="根数"):
        check(panel, contract, identity, roots=(1, 2))


def test_missing_god_count_tie_stays_interval_not_arbitrary_rank():
    panel, contract, identity = fixture()
    for sample in panel["samples"]:
        for arm_name in ("baseline", "candidate"):
            raw = sample["raw_arms"][arm_name]
            zeros = {pid: 0 for pid in raw["stage_totals_by_participant"]}
            for table in raw["tables"]:
                table["scores_by_seat"] = [0, 0, 0, 0]
                table["stage_situation"]["stage_scores_by_seat"] = [0, 0, 0, 0]
                table["stage_situation"]["place_points_by_seat"] = [0, 0, 0, 0]
            for record in (raw, sample["arms"][arm_name]):
                record.update(stage_totals_by_participant=zeros, focal_stage_score=0,
                              u=None, u_low=0.0, u_high=1.0, unresolved=True)
            raw.update(stage_place_points_by_participant=zeros,
                       u_interval={"a": 1, "b": 4, "tie_block": sorted(zeros)})
    panel["statistics"] = verify.archive.paired_stage_statistics(panel["samples"], min_roots=1)
    result = check(panel, contract, identity)
    stats = result["statistics"]["by_candidate"][identity["candidate_id"]]["panels"]["normal"]["panels"]["H"]
    assert stats["delta_bounds"]["mean_delta_low"] == -1
    assert stats["delta_bounds"]["mean_delta_high"] == 1
    assert result["release_eligible"] is False


def test_modified_contract_rejected_against_frozen_identity():
    panel, contract, identity = fixture()
    contract["versions"]["rounds_per_game"] = 16
    with pytest.raises(ValueError, match="完整合同摘要"):
        check(panel, contract, identity)


@pytest.mark.parametrize("section,key,value", [
    ("ranking", "place_points_values", [4, 2, 0, -2]),
    ("group", "group_advance", 1),
    ("group", "group_size", 3),
    ("objective", "ranking_keys_offline", ["place_points", "total_score"]),
    ("objective", "missing_key_policy", "sort_by_name"),
])
def test_unsupported_target_contract_cannot_silently_use_old_formula(section, key, value):
    panel, contract, identity = fixture()
    contract[section][key] = value
    # 即使另一次预登记接受新合同，本版分析器也必须拒绝自己未实现的计算口径。
    panel["identity"]["contract_sha256"] = verify._digest(contract)
    with pytest.raises(ValueError):
        check(panel, contract, copy.deepcopy(panel["identity"]))
