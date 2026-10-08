"""已闭公开输入的完整选择成本定位；新解释器隔离缓存，不读取当前桌积分。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t186-incremental-opportunity-repair-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
import argparse
import asyncio
import cProfile
import json
import pstats
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
PRIOR = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t185-evidence-prioritized-joker-evolution-1')
sys.path.insert(0, str(PRIOR))
from common import ROOT, canonical, pin, save
from t185_prepare_confirmation import background_priority
from hangma_bot.hangma.engine import HangmaRules
from hangma_bot.kernel.observation import CompetitionContext
from hangma_bot.kernel.serialization import observation_from_json, window_key_from_json
from hangma_bot.offline.scoring_input_capture import ScoringInputCapture, ScoringInputCaptureLimits
from hangma_bot.offline.vip_eoh_generate import VipEohBatch
from hangma_bot.policy.interface import DecisionBudget, DecisionRequest
from hangma_bot.policy.route_vip_heuristic import RouteVipHeuristicPolicy


async def main(mode):
    """只测公开资格面板中操作数最大输入；逻辑宽预算，不授实际1/3秒通过。"""
    background_priority()
    batch = VipEohBatch.read(_project_file(_PROJECT_ROOT, HERE / "AUTHOR-BATCH.json"))
    rows = [json.loads(x) for x in (_project_file(_PROJECT_ROOT, HERE / "qualification/rows.jsonl")).read_text().splitlines()]
    row = max(rows, key=lambda x: (x["operation_counts"][0], x["label"]))
    case = next(c for c in json.loads((_project_file(_PROJECT_ROOT, HERE / "CASES.json")).read_text())["cases"] if c["label"] == row["label"])
    source_file = _project_file(_PROJECT_ROOT, HERE / "AUTHOR-resource-release-metadata-repaired/candidate.py")
    directory = _project_file(_PROJECT_ROOT, HERE / ("closed-choice-cost-v2-" + mode))
    directory.mkdir(exist_ok=False)
    files = {str(p): pin(p) for p in [Path(__file__), _project_file(_PROJECT_ROOT, HERE / "AUTHOR-BATCH.json"), _project_file(_PROJECT_ROOT, HERE / "CASES.json"),
        _project_file(_PROJECT_ROOT, HERE / "qualification/rows.jsonl"), source_file]}
    save(directory / "START.json", {"mode": mode, "label": row["label"], "files": files,
        "fresh_process": True, "new_worlds_tables_models_HTTP": 0, "logical_budget_not_original_deadline": True})
    obs, key = observation_from_json(case["observation"]), window_key_from_json(case["window_key"])
    policy = RouteVipHeuristicPolicy(batch.rule_config, source=source_file.read_text(),
        projection_limits=batch.projection_limits, max_operations=batch.max_operations)
    rules = HangmaRules(batch.rule_config)
    phases, output, score_calls = {}, None, 0
    raw = (directory / "views.jsonl.gz").open("x+b")
    capture = ScoringInputCapture(raw, limits=ScoringInputCaptureLimits(67108864, 134217728, 4))
    original = policy.executor.score_vip_route

    def score(view):
        """评分前保存原图，记录计量与全输出，不给排序器读取完整世界。"""
        nonlocal score_calls
        t = time.monotonic()
        receipt = capture.store(view.candidate_view())
        phases["score_input_capture_seconds"] = time.monotonic() - t
        assert receipt.saved_before_score and receipt.view_sha256 == row["view_sha256"]
        score_calls += 1
        t = time.monotonic()
        value = original(view)
        phases["actual_score_seconds"] = time.monotonic() - t
        return value

    policy.executor.score_vip_route = score
    profiler = cProfile.Profile()
    failure, terminal = None, None
    try:
        if mode == "profile":
            profiler.enable()
        t = time.monotonic()
        analysis = rules.analyze(obs, route_limits=batch.route_limits)
        phases["rules_analyze_seconds"] = time.monotonic() - t
        assert analysis.completeness.value == "complete"
        request = DecisionRequest(obs, CompetitionContext("T186-cost", None, None, None, None, (), 0),
            analysis, case["label"], key.trigger_seq, key, ())
        t = time.monotonic()
        plan = await policy.choose(request, DecisionBudget(803.0, 803.5, 804.0))
        phases["policy_choose_including_capture_seconds"] = time.monotonic() - t
        output = sorted([{"action_key": c.action_key, "score": c.total_score,
                          "trace": c.score_trace["detail"]} for c in plan.candidates], key=lambda c: c["action_key"])
        assert not plan.degraded_reasons and canonical(output) == canonical(row["entries"])
        assert policy.executor.last_operation_count == row["operation_counts"][0] and score_calls == 1
    except BaseException as error:
        failure = {"type": type(error).__name__, "message": str(error)}
    finally:
        profiler.disable()
        if mode == "profile":
            profiler.dump_stats(str(directory / "profile.pstats"))
            stats = pstats.Stats(profiler)
            top = [{"file": k[0], "line": k[1], "function": k[2], "primitive_calls": v[0], "total_calls": v[1],
                    "exclusive_seconds": v[2], "inclusive_seconds": v[3]} for k,v in stats.stats.items()]
            save(directory / "FUNCTIONS.json", {"by_exclusive": sorted(top,key=lambda x:-x["exclusive_seconds"]),
                "by_inclusive": sorted(top,key=lambda x:-x["inclusive_seconds"]),
                "overlapping_inclusive_times_must_not_be_summed": True})
        try:
            terminal = capture.finish()
        except BaseException as error:
            failure = failure or {"type": type(error).__name__, "message": str(error)}
        raw.close()
        stable = all(pin(Path(p)) == v for p,v in files.items())
        complete = failure is None and stable and terminal is not None and terminal["terminal"]["terminal_valid"]
        result = {"complete": complete, "failure": failure, "label": row["label"], "mode": mode, "files": files,
            "phases": phases, "source_stable": stable, "actual_score_calls": score_calls, "capture": terminal,
            "actual_operations": policy.executor.last_operation_count, "full_output_matches_closed_qualification": failure is None,
            "new_worlds_tables_models_HTTP": 0, "original_deadline_or_strength_admission": False}
        save(directory / "CLOSED.json", result)
    assert complete, failure
    print(json.dumps({k:result[k] for k in ["complete","mode","label","phases","actual_score_calls","actual_operations"]}))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--mode", choices=["plain", "profile"], required=True)
    asyncio.run(main(p.parse_args().mode))
