"""离线等胡候选必须保留风险表版本、生效参数与校准适用范围。"""

from dataclasses import asdict, replace
import json
from pathlib import Path
import subprocess
import sys

import pytest

from hangma_bot.offline.evaluate import load_experiment
from hangma_bot.policy.hu_upgrade_calibration import RISK_CELLS, RISK_VERSION, SAFETY_MARGIN
from scripts.evaluate import validate_upgrade_scope

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "review/hu-upgrade-2026-09-08/experiments/development.json"


def test_frozen_parameters_match_the_recorded_independent_calibration():
    table = json.loads((ROOT / "review/hu-upgrade-2026-09-08/risk-table.json").read_text())
    assert RISK_VERSION == table["version"]
    assert [asdict(cell) for cell in RISK_CELLS] == table["cells"]
    assert SAFETY_MARGIN == table["fit_spec"]["safety_margin"]
    assert all(item["samples"] >= 100 and item["roots"] >= 50 for item in table["diagnostics"] if item["enabled"])


@pytest.mark.parametrize("policy_name,base_name", [("hu_upgrade_v1", "one_draw_value_v1"), ("v2_hu_upgrade_v1", "weighted_heuristic_v2")])
def test_cli_records_risk_inputs_and_disabled_upgrade_matches_previous_candidate(tmp_path, policy_name, base_name):
    config = json.loads(CONFIG.read_text())
    config["baseline_policy"] = {"policy_id": base_name, "name": base_name, "weights": {}}
    config["challenger_policy"].update(policy_id=policy_name, name=policy_name)
    config["seeds"] = config["seeds"][:1]
    config["seat_permutations"] = [[0, 1, 2, 3]]
    config["tournament_config"]["rounds_per_game"] = 1
    config["challenger_policy"]["weights"]["upgrade_weight"] = 0
    config["n_resamples"] = 100
    path = tmp_path / "experiment.json"
    path.write_text(json.dumps(config))
    out = tmp_path / "out"
    result = subprocess.run([sys.executable, str(ROOT / "scripts/evaluate.py"), "matches", "--experiment", str(path), "--out", str(out)],
                            cwd=ROOT, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
    manifest = json.loads((out / "manifest.json").read_text())
    actual = manifest["versions"]["scoring_policies"]["challenger"]["effective_weights"]
    assert actual["upgrade_weight"] == 0
    assert actual["risk_version"] == RISK_VERSION
    assert actual["risk_cells"] == [asdict(cell) for cell in RISK_CELLS]
    assert actual["safety_margin"] == SAFETY_MARGIN
    assert actual["base_policy"] == base_name
    hands = [json.loads(line) for line in (out / "hands.jsonl").read_text().splitlines()]
    assert len(hands) == 2
    assert hands[0]["score_delta"] == hands[1]["score_delta"]


@pytest.mark.parametrize("change", ["youcai", "base", "ruleset", "opponents", "limits"])
@pytest.mark.parametrize("policy_name", ["hu_upgrade_v1", "v2_hu_upgrade_v1"])
def test_matches_rejects_unvalidated_risk_table_scope(change, policy_name):
    experiment = load_experiment(CONFIG)
    experiment = replace(experiment, challenger=replace(experiment.challenger, name=policy_name))
    validate_upgrade_scope(experiment)
    if change in ("youcai", "base", "ruleset"):
        updates = {"youcai": {"you_cai_bi_kao": True}, "base": {"base_score": 2}, "ruleset": {"ruleset_version": "unknown"}}[change]
        experiment = replace(experiment, tournament_config=replace(experiment.tournament_config,
                             rules=replace(experiment.tournament_config.rules, **updates)))
    elif change == "opponents":
        experiment = replace(experiment, opponents=tuple(replace(d, name="one_draw_value_v1") for d in experiment.opponents))
    else:
        experiment = replace(experiment, value_limits=None)
    with pytest.raises(ValueError, match="hu_upgrade_v1"):
        validate_upgrade_scope(experiment)
