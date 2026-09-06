"""CLI 入口测试：summarize 端到端、decisions/matches 的错误与成功路径。"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import time
from pathlib import Path

import pytest

from hangma_bot.kernel.serialization import tournament_config_to_json
from hangma_bot.offline.evaluate import PolicyDeclaration

from support import (
    candidates_for,
    make_decision_source_row,
    make_match_result,
    make_observation,
    make_rules,
    make_tournament_config,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "evaluate.py"


def load_script_module():
    spec = importlib.util.spec_from_file_location("scripts_evaluate", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_cli_v0_factory_preserves_neutral_pass_under_new_rules():
    """实际离线装配入口必须使用旧事实视图，不能只在直接构造测试中适配。"""
    import asyncio
    from hangma_bot.hangma.engine import HangmaRules
    from hangma_bot.kernel.config import RuleConfig
    from tests.unit.hangma.test_pass_progress import response
    from tests.unit.policy.support import make_request, make_budget
    obs = response()
    request = make_request(obs, HangmaRules(RuleConfig("pass-cli", 1, False)).analyze(obs))
    policy = load_script_module().build_policy(PolicyDeclaration("v0", "weighted_heuristic"), lambda: 0)
    plan = asyncio.run(policy.choose(request, make_budget()))
    assert next(c for c in plan.candidates if c.action_key == "pass").total_score == 0
    assert "legacy-pass-neutral-v1" in " ".join(plan.degraded_reasons)


def write_experiment(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def test_summarize_subprocess_end_to_end(tmp_path):
    results = [
        make_match_result(result_id="r-b-1", pair_id="p-1", scenario_id="sc-1", scores_after=(3, 0, 0, 0)),
        make_match_result(
            result_id="r-c-1", pair_id="p-1", scenario_id="sc-1",
            policy_ids_by_seat=("candidate", "opp-1", "opp-2", "opp-3"),
            scores_after=(7, 0, 0, 0),
        ),
        make_match_result(result_id="r-b-2", pair_id="p-2", scenario_id="sc-2", scores_after=(4, 0, 0, 0)),
        make_match_result(
            result_id="r-c-2", pair_id="p-2", scenario_id="sc-2",
            policy_ids_by_seat=("candidate", "opp-1", "opp-2", "opp-3"),
            scores_after=(6, 0, 0, 0),
        ),
    ]
    results_path = tmp_path / "results.jsonl"
    from hangma_bot.offline.evaluation_results import write_results_jsonl

    write_results_jsonl(results_path, results)
    out_dir = tmp_path / "out"
    process = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "summarize",
            str(results_path),
            "--out",
            str(out_dir),
            "--baseline",
            "stable",
            "--challenger",
            "candidate",
            "--n-resamples",
            "500",
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert process.returncode == 0, process.stderr
    assert (out_dir / "report.json").is_file()
    assert (out_dir / "report.md").is_file()
    markdown = (out_dir / "report.md").read_text(encoding="utf-8")
    assert "评估结果汇总" in markdown
    report = json.loads((out_dir / "report.json").read_text(encoding="utf-8"))
    assert report["title"] == "评估结果汇总"


def test_decisions_cli_bad_row_excluded_with_real_codec(tmp_path):
    """集成后（bootstrap 提供 build_decision_codec）：坏行被排除并计数，不伪造决策。"""
    dataset = tmp_path / "dataset"
    dataset.mkdir()
    (dataset / "decisions.jsonl").write_text("{}\n", encoding="utf-8")
    experiment = write_experiment(
        tmp_path / "exp.json",
        {
            "experiment_schema_version": 1,
            "kind": "decisions",
            "decision_mode": "recorded_request",
            "clock_mode": "logical",
            "baseline_policy": {"policy_id": "b", "name": "safe_fallback", "weights": {}},
            "challenger_policy": {"policy_id": "c", "name": "safe_fallback", "weights": {}},
        },
    )
    process = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "decisions",
            str(dataset),
            "--experiment",
            str(experiment),
            "--out",
            str(tmp_path / "out"),
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert process.returncode == 0, process.stderr
    assert "排除 1 行" in process.stdout
    assert (tmp_path / "out" / "manifest.json").is_file()


def test_decisions_cli_missing_codec_hook_fails_in_process(tmp_path, monkeypatch):
    """组合根缺失 codec 钩子时的防御分支：进程内清晰失败（C1 前的旧契约行为）。"""
    import argparse

    import hangma_bot.bootstrap as bootstrap_module

    monkeypatch.setattr(bootstrap_module, "build_decision_codec", lambda: None, raising=False)
    dataset = tmp_path / "dataset"
    dataset.mkdir()
    (dataset / "decisions.jsonl").write_text("{}\n", encoding="utf-8")
    experiment = write_experiment(
        tmp_path / "exp.json",
        {
            "experiment_schema_version": 1,
            "kind": "decisions",
            "decision_mode": "recorded_request",
            "clock_mode": "logical",
            "baseline_policy": {"policy_id": "b", "name": "safe_fallback", "weights": {}},
            "challenger_policy": {"policy_id": "c", "name": "safe_fallback", "weights": {}},
        },
    )
    module = load_script_module()
    args = argparse.Namespace(
        dataset=str(dataset), experiment=str(experiment), out=str(tmp_path / "out")
    )
    with pytest.raises(SystemExit) as excinfo:
        module.cmd_decisions(args)
    assert "codec" in str(excinfo.value)


def test_matches_cli_end_to_end_with_real_engine(tmp_path):
    """集成后（bootstrap 提供 build_evaluation_runtime）：真实引擎完整桌赛实验跑通。"""
    config = tournament_config_to_json(make_tournament_config(rounds_per_game=8))
    experiment = write_experiment(
        tmp_path / "exp.json",
        {
            "experiment_schema_version": 1,
            "kind": "matches",
            "clock_mode": "logical",
            "baseline_policy": {"policy_id": "stable", "name": "safe_fallback", "weights": {}},
            "challenger_policy": {"policy_id": "candidate", "name": "safe_fallback", "weights": {}},
            "opponent_pool": [
                {"policy_id": "opp-1", "name": "safe_fallback", "weights": {}},
                {"policy_id": "opp-2", "name": "safe_fallback", "weights": {}},
                {"policy_id": "opp-3", "name": "safe_fallback", "weights": {}},
            ],
            "tournament_config": config,
            "seeds": [{"seed": 1, "scenario_id": "sc-1"}],
            "seat_permutations": [[0, 1, 2, 3]],
            "initial_dealer": 0,
            "initial_scores": [0, 0, 0, 0],
        },
    )
    process = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "matches",
            "--experiment",
            str(experiment),
            "--out",
            str(tmp_path / "out"),
        ],
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert process.returncode == 0, process.stderr
    out_dir = tmp_path / "out"
    assert (out_dir / "results.jsonl").is_file()
    assert (out_dir / "report.json").is_file()
    assert (out_dir / "report.md").is_file()
    from hangma_bot.offline.evaluation_results import read_results_jsonl

    rows = read_results_jsonl(out_dir / "results.jsonl")
    assert len(rows) == 2  # 1 seed × 1 换座 × 稳定/候选两个完整桌赛
    assert all(row.source_kind == "simulation" for row in rows)


def test_matches_cli_missing_runtime_hook_fails_in_process(tmp_path, monkeypatch):
    """组合根缺失运行时钩子时的防御分支：进程内清晰失败（E3 前的旧契约行为）。"""
    import argparse

    import hangma_bot.bootstrap as bootstrap_module

    monkeypatch.setattr(
        bootstrap_module, "build_evaluation_runtime", lambda kind, experiment: None, raising=False
    )
    config = tournament_config_to_json(make_tournament_config(rounds_per_game=8))
    experiment = write_experiment(
        tmp_path / "exp.json",
        {
            "experiment_schema_version": 1,
            "kind": "matches",
            "clock_mode": "logical",
            "baseline_policy": {"policy_id": "stable", "name": "safe_fallback", "weights": {}},
            "challenger_policy": {"policy_id": "candidate", "name": "safe_fallback", "weights": {}},
            "opponent_pool": [
                {"policy_id": "opp-1", "name": "safe_fallback", "weights": {}},
                {"policy_id": "opp-2", "name": "safe_fallback", "weights": {}},
                {"policy_id": "opp-3", "name": "safe_fallback", "weights": {}},
            ],
            "tournament_config": config,
            "seeds": [{"seed": 1, "scenario_id": "sc-1"}],
            "seat_permutations": [[0, 1, 2, 3]],
            "initial_dealer": 0,
            "initial_scores": [0, 0, 0, 0],
        },
    )
    module = load_script_module()
    args = argparse.Namespace(out=str(tmp_path / "out"), experiment=str(experiment))
    with pytest.raises(SystemExit) as excinfo:
        module.cmd_matches(args)
    message = str(excinfo.value)
    assert "build_evaluation_runtime" in message or "E3" in message


def test_decisions_cli_end_to_end_in_process(tmp_path, monkeypatch):
    import hangma_bot.bootstrap as bootstrap_module

    from support import decode_budget, decode_request

    monkeypatch.setattr(
        bootstrap_module,
        "build_decision_codec",
        lambda: {"decode_request": decode_request, "decode_budget": decode_budget},
        raising=False,
    )
    dataset = tmp_path / "dataset"
    dataset.mkdir()
    from hangma_bot.kernel.actions import Discard, Tile

    candidates = candidates_for([Discard(Tile("1w")), Discard(Tile("2w"))])
    rules = make_rules(candidates, emergency=candidates[0])
    rows = [
        make_decision_source_row(make_observation(), rules, hand_id="h-1", decision_id="d1"),
        make_decision_source_row(make_observation(), rules, hand_id="h-2", decision_id="d2"),
    ]
    (dataset / "decisions.jsonl").write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )
    experiment = write_experiment(
        tmp_path / "exp.json",
        {
            "experiment_schema_version": 1,
            "kind": "decisions",
            "decision_mode": "recorded_request",
            "clock_mode": "logical",
            "baseline_policy": {"policy_id": "b", "name": "safe_fallback", "weights": {}},
            "challenger_policy": {"policy_id": "c", "name": "weighted_heuristic", "weights": {}},
        },
    )
    module = load_script_module()
    out_dir = tmp_path / "out"
    exit_code = module.main(
        ["decisions", str(dataset), "--experiment", str(experiment), "--out", str(out_dir)]
    )
    assert exit_code == 0
    for name in ("decisions.jsonl", "report.json", "report.md", "manifest.json"):
        assert (out_dir / name).is_file()
    lines = (out_dir / "decisions.jsonl").read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 2
    first = json.loads(lines[0])
    assert first["evaluation_schema_version"] == 1
    assert first["clock_mode"] == "logical"
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["contract_id"] == "parallel-v1"
    assert manifest["inputs"][0]["path"] == "decisions.jsonl"
    # 契约 §4.2：可空字段必须写入 missing_fields 说明，不能静默 null。
    missing = set(manifest["missing_fields"])
    assert {"guide_version", "guide_captured_at", "config", "input_sha256"} <= missing
    assert manifest["guide_version"] is None
    assert manifest["guide_captured_at"] is None


def test_load_experiment_decisions(tmp_path):
    module = load_script_module()
    path = write_experiment(
        tmp_path / "exp.json",
        {
            "experiment_schema_version": 1,
            "kind": "decisions",
            "decision_mode": "recomputed_rules",
            "clock_mode": "logical",
            "baseline_policy": {"policy_id": "b", "name": "safe_fallback", "weights": {}},
            "challenger_policy": {"policy_id": "c", "name": "weighted_heuristic", "weights": {"win_now": 5.0}},
            "rules_config": {"ruleset_version": "v2", "base_score": 2, "you_cai_bi_kao": False},
        },
    )
    experiment = module.load_experiment(path)
    assert experiment.kind == "decisions"
    assert experiment.decision_mode == "recomputed_rules"
    assert experiment.rules_config.base_score == 2
    assert dict(experiment.challenger.weights) == {"win_now": 5.0}


def test_load_experiment_matches(tmp_path):
    module = load_script_module()
    config = tournament_config_to_json(make_tournament_config(rounds_per_game=8))
    path = write_experiment(
        tmp_path / "exp.json",
        {
            "experiment_schema_version": 1,
            "kind": "matches",
            "clock_mode": "logical",
            "baseline_policy": {"policy_id": "stable", "name": "safe_fallback", "weights": {}},
            "challenger_policy": {"policy_id": "candidate", "name": "safe_fallback", "weights": {}},
            "opponent_pool": [
                {"policy_id": "opp-1", "name": "safe_fallback", "weights": {}},
                {"policy_id": "opp-2", "name": "safe_fallback", "weights": {}},
                {"policy_id": "opp-3", "name": "safe_fallback", "weights": {}},
            ],
            "tournament_config": config,
            "seeds": [{"seed": 1, "scenario_id": "sc-1"}, {"seed": 2, "scenario_id": "sc-2"}],
            "seat_permutations": [[0, 1, 2, 3], [2, 0, 1, 3]],
            "initial_dealer": 0,
            "initial_scores": [0, 0, 0, 0],
        },
    )
    experiment = module.load_experiment(path)
    assert experiment.kind == "matches"
    assert len(experiment.seeds) == 2
    assert len(experiment.seat_permutations) == 2
    assert len(experiment.opponents) == 3


def test_load_experiment_rejects_unknown_version(tmp_path):
    module = load_script_module()
    path = write_experiment(
        tmp_path / "exp.json",
        {"experiment_schema_version": 99, "kind": "decisions"},
    )
    with pytest.raises(ValueError):
        module.load_experiment(path)


def test_build_policy_weighted_heuristic_and_unknown_name():
    module = load_script_module()
    policy = module.build_policy(
        PolicyDeclaration("p", "weighted_heuristic", weights=(("win_now", 5.0),)),
        time.monotonic,
    )
    assert policy.policy_id == "p"
    assert policy._weights.win_now == 5.0
    with pytest.raises(ValueError):
        module.build_policy(PolicyDeclaration("x", "mystery"), time.monotonic)


@pytest.mark.parametrize('name', ['weighted_heuristic', 'weighted_heuristic_v1'])
def test_policy_factory_uses_experiment_clock_and_declared_weights(name):
    """真实 CLI 工厂必须把同一实验时钟及权重送入策略，不能退化为保底实验。"""
    import asyncio
    from hangma_bot.application.deadline import BudgetPolicy
    from tests.unit.policy.test_v0_baseline import recorded_request, rows
    module = load_script_module()
    calls = []
    def clock():
        calls.append(1)
        return 800.0
    policy = module.build_policy(PolicyDeclaration(name,name,(('shanten_step',50.0),)),clock)
    request = recorded_request(rows()[0])
    plan = asyncio.run(policy.choose(request,BudgetPolicy().build(800.0,3.0)))
    assert calls, '策略必须读取注入时钟'
    candidate = next(c for c in plan.candidates if c.action_key == 'discard:3b')
    shanten = next(c.facts.shanten_after for c in request.rules.legal_candidates if c.action_key == 'discard:3b')
    assert next(p.value for p in candidate.score_parts if p.name == '第三层-向听数') == -50.0*shanten


def test_v1_factory_rejects_unrecognized_weights_instead_of_ignoring():
    module = load_script_module()
    with pytest.raises(TypeError):
        module.build_policy(PolicyDeclaration('v1','weighted_heuristic_v1',(('typo_weight',10.0),)),lambda:800.0)
