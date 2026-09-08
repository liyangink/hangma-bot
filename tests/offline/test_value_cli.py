"""公开离线命令保存生效开关、条件分析成本和真实单局结算。"""

import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]


def test_value_cli_writes_reproducible_limits_and_completed_hand_results(tmp_path):
    experiment = json.loads((ROOT / "review/one-draw-value-2026-09-08/experiment.json").read_text())
    experiment["seeds"] = experiment["seeds"][:1]
    experiment["seat_permutations"] = [[0, 1, 2, 3]]
    experiment["tournament_config"]["rounds_per_game"] = 1
    experiment["challenger_policy"]["weights"]["value_weight"] = 0
    experiment["n_resamples"] = 100
    config = tmp_path / "experiment.json"
    config.write_text(json.dumps(experiment))
    out = tmp_path / "out"
    result = subprocess.run([
        sys.executable, str(ROOT / "scripts/evaluate.py"), "matches", "--experiment", str(config), "--out", str(out),
    ], cwd=ROOT, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
    manifest = json.loads((out / "manifest.json").read_text())
    assert manifest["versions"]["value_limits"] == experiment["value_limits"]
    assert manifest["versions"]["scoring_policies"]["challenger"]["effective_weights"]["value_weight"] == 0
    hands = [json.loads(row) for row in (out / "hands.jsonl").read_text().splitlines()]
    assert len(hands) == 2
    assert all(row["round_no"] == 1 and len(row["score_delta"]) == 4 and sum(row["score_delta"]) == 0 for row in hands)
    assert hands[0]["score_delta"] == hands[1]["score_delta"]
