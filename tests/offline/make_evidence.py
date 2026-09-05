"""手动证据生成器：生成 E1/E2 样例产物并打印 SHA-256（不被 pytest 收集）。

用法（仓库根目录）：
  PYTHONPATH=src:tests/offline uv run python tests/offline/make_evidence.py

产物目录 tests/offline/evidence/：
  - sample-results/：summarize 子命令的真实运行产物（report.json/report.md）
  - sample-decisions/：固定决策比较（recorded_request，fixture codec）产物
  - test-run.txt：tests/offline 测试运行记录（退出码与摘要）

全部产物为实际运行生成；mock/fixture 数据只用于编排与格式验证，
不进入强度结论（报告内已声明）。
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from hangma_bot.kernel.actions import Discard, Tile  # noqa: E402
from hangma_bot.offline.evaluate import (  # noqa: E402
    DecisionExperiment,
    PolicyDeclaration,
    build_decision_report,
    run_decisions_comparison,
    write_decision_rows,
    write_report_files,
)
from hangma_bot.offline.evaluation_results import (  # noqa: E402
    GameKey,
    ManifestInput,
    new_evaluation_manifest,
    write_manifest,
    write_results_jsonl,
)

from support import (  # noqa: E402
    ScriptedPolicy,
    candidates_for,
    decode_budget,
    decode_request,
    make_decision_source_row,
    make_match_result,
    make_observation,
    make_rules,
    pick_key,
)

NL = chr(10)
EVIDENCE = _REPO_ROOT / "tests" / "offline" / "evidence"
SAMPLE_RESULTS = EVIDENCE / "sample-results"
SAMPLE_DECISIONS = EVIDENCE / "sample-decisions"


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def make_sample_results() -> Path:
    SAMPLE_RESULTS.mkdir(parents=True, exist_ok=True)
    rows = []
    for scenario in range(4):
        for pair in range(2):
            index = scenario * 2 + pair
            baseline = make_match_result(
                result_id="r-b-{0}".format(index),
                pair_id="p-{0}".format(index),
                scenario_id="sc-{0}".format(scenario),
                game_key=GameKey("hangma-simulation", "sc-{0}".format(scenario), "m-b-{0}".format(index)),
                scores_before=(0, 0, 0, 0),
                scores_after=(2, 0, 0, 0),
                # 证据数据为 fixture 构造，不是真实 SimulationEngine 产物：
                # 必须报 mock，不冒充强度证据（修订轮修复项 7 口径）。
                source_kind="mock",
            )
            challenger = make_match_result(
                result_id="r-c-{0}".format(index),
                pair_id="p-{0}".format(index),
                scenario_id="sc-{0}".format(scenario),
                game_key=GameKey("hangma-simulation", "sc-{0}".format(scenario), "m-c-{0}".format(index)),
                policy_ids_by_seat=("candidate", "opp-1", "opp-2", "opp-3"),
                scores_before=(0, 0, 0, 0),
                scores_after=(5 + index, 0, 0, 0),
                source_kind="mock",
            )
            rows.extend([baseline, challenger])
    path = SAMPLE_RESULTS / "results.jsonl"
    write_results_jsonl(path, rows)
    return path


def run_summarize(results_path: Path) -> None:
    script = _REPO_ROOT / "scripts" / "evaluate.py"
    process = subprocess.run(
        [
            sys.executable,
            str(script),
            "summarize",
            str(results_path),
            "--out",
            str(SAMPLE_RESULTS),
            "--baseline",
            "stable",
            "--challenger",
            "candidate",
            "--n-resamples",
            "2000",
            "--seed",
            "7",
        ],
        capture_output=True,
        text=True,
        timeout=300,
    )
    print("summarize 退出码:", process.returncode)
    if process.returncode != 0:
        print(process.stderr)
        raise SystemExit(1)


def make_sample_decisions() -> None:
    SAMPLE_DECISIONS.mkdir(parents=True, exist_ok=True)
    dataset = SAMPLE_DECISIONS / "dataset"
    dataset.mkdir(exist_ok=True)
    candidates = candidates_for([Discard(Tile("1w")), Discard(Tile("2w")), Discard(Tile("3w"))])
    rules = make_rules(candidates, emergency=candidates[0])
    rows = [
        make_decision_source_row(make_observation(), rules, hand_id="h-1", decision_id="d1"),
        make_decision_source_row(make_observation(), rules, hand_id="h-2", decision_id="d2"),
        make_decision_source_row(make_observation(), rules, hand_id="h-3", decision_id="d3"),
    ]
    del rows[2]["request"]  # 缺完整 request：应被排除并计数
    (dataset / "decisions.jsonl").write_text(
        NL.join(json.dumps(row, ensure_ascii=False) for row in rows) + NL,
        encoding="utf-8",
    )
    experiment = DecisionExperiment(
        kind="decisions",
        decision_mode="recorded_request",
        clock_mode="logical",
        baseline=PolicyDeclaration("stable-v1", "scripted"),
        challenger=PolicyDeclaration("candidate-v1", "scripted"),
        input_sha256=None,
        source_namespace="hangma-official",
        rules_config=None,
        tournament_config=None,
    )
    outcome = asyncio.run(
        run_decisions_comparison(
            dataset,
            experiment,
            baseline_policy=ScriptedPolicy(pick_key("discard:1w")),
            challenger_policy=ScriptedPolicy(pick_key("discard:3w")),
            decode_request=decode_request,
            decode_budget=decode_budget,
            now_monotonic=lambda: 800.0,
            wall_clock=None,
        )
    )
    write_decision_rows(SAMPLE_DECISIONS / "decisions.jsonl", outcome.rows)
    write_report_files(SAMPLE_DECISIONS, build_decision_report(outcome, experiment))
    manifest = new_evaluation_manifest(
        source_namespace=experiment.source_namespace,
        producer_commit=None,
        dirty=None,
        inputs=(ManifestInput(path="decisions.jsonl", sha256=outcome.input_sha256),),
        missing_fields=("input_sha256", "guide_version", "guide_captured_at", "rules_hash", "producer_commit", "dirty"),
        versions=(
            ("decision_mode", experiment.decision_mode),
            ("clock_mode", experiment.clock_mode),
            ("scoring_policies", {
                "baseline": experiment.baseline.to_json(),
                "challenger": experiment.challenger.to_json(),
            }),
        ),
    )
    write_manifest(SAMPLE_DECISIONS / "manifest.json", manifest)


def make_test_transcript() -> Path:
    path = EVIDENCE / "test-run.txt"
    process = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/offline",
            "-q",
        ],
        capture_output=True,
        text=True,
        timeout=600,
        cwd=str(_REPO_ROOT),
    )
    transcript = (
        "命令: python -m pytest tests/offline -q"
        + NL
        + "退出码: {0}".format(process.returncode)
        + NL
        + NL
        + process.stdout
        + process.stderr
    )
    path.write_text(transcript, encoding="utf-8")
    return path


def main() -> None:
    results_path = make_sample_results()
    run_summarize(results_path)
    make_sample_decisions()
    transcript = make_test_transcript()
    print(NL + "证据产物 SHA-256：")
    for path in sorted(EVIDENCE.rglob("*")):
        if path.is_file():
            relative = path.relative_to(_REPO_ROOT).as_posix()
            print("{0}  {1}".format(sha256_of(path), relative))


if __name__ == "__main__":
    main()
