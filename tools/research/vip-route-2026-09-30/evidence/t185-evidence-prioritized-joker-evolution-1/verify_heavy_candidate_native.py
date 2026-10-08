"""确认胜者的19重型图补充等价验证；不替换原542评分及59原时限调用。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t185-evidence-prioritized-joker-evolution-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
import time
from pathlib import Path

from common import HERE, canonical, pin, save
import t185_close_development as dev
from candidate_verification_common import check_files, digest, validated_candidate


def main():
    """只有真实确认及原体编译通过才评分；19图四重复加4耗尽，共80次。"""
    from t185_prepare_confirmation import background_priority
    from hangma_bot.hangma.engine import HangmaRules
    from hangma_bot.kernel.observation import CompetitionContext
    from hangma_bot.kernel.serialization import observation_from_json, window_key_from_json
    from hangma_bot.offline.scoring_input_capture import ScoringInputCapture, ScoringInputCaptureLimits
    from hangma_bot.policy.action_value_executor import ActionValueExecutor, WorkloadExceeded
    from hangma_bot.policy.interface import DecisionRequest
    from hangma_bot.policy.route_vip_heuristic import build_vip_route_scoring_view
    background_priority()
    batch, arm, runtime, files = validated_candidate()
    base = _project_file(_PROJECT_ROOT, HERE / "development-heavy-inputs")
    closed, closed_pin = dev.read(base / "CLOSED.json")
    cases_file = base / "CASES.json"
    cases = dev.read(cases_file)[0]["cases"]
    dev.require(closed["complete"] is True and closed["source_stable"] is True and
        closed["selected_unique_views"] == len(cases) == 19 and closed["cases_pin"] == pin(cases_file) and
        closed["new_rule_analyses_scores_worlds_tables_model_calls_HTTP"] == 0,
        "19重型输入准备未全闭合")
    check_files(closed["files"])
    files.update(closed["files"])
    files.update({str(p): pin(p) for p in (Path(__file__), base / "CLOSED.json", cases_file,
        base / "original-heavy-views.jsonl.gz")})
    dev.require(files[str(base / "original-heavy-views.jsonl.gz")] == closed["original_heavy_views_pin"],
        "封存完整重型图漂移")
    out = _project_file(_PROJECT_ROOT, HERE / "heavy-native-verification")
    out.mkdir(exist_ok=False)
    save(out / "START.json", {"identity": arm["identity"], "execution_id": runtime.execution_id,
        "files": files, "heavy_input_closed_pin": closed_pin, "planned_score_attempts": 80,
        "nominal_or_official_deadline_admission": False, "original_verification_contract_unchanged": True})
    source = Path(arm["source_file"]).read_text()
    executors = {"python": ActionValueExecutor(source, max_operations=batch.max_operations,
        max_local_collection_size=batch.projection_limits.max_nodes),
        "native": ActionValueExecutor(source, max_operations=batch.max_operations,
        max_local_collection_size=batch.projection_limits.max_nodes, compiled_runtime=runtime)}
    raw = (out / "views.jsonl.gz").open("x+b")
    capture = ScoringInputCapture(raw, limits=ScoringInputCaptureLimits(67108864, 1073741824, 32))
    rows, attempts, failure, capture_result, heaviest = [], 0, None, None, None

    def score(executor, view):
        """评分前捕获，记录真实操作数；测时不含捕获且不冒称完整choose耗时。"""
        nonlocal attempts
        receipt = capture.store(view.candidate_view())
        dev.require(receipt.saved_before_score, "重型评分前捕获失败")
        attempts += 1
        started = time.monotonic()
        answer = executor.score_vip_route(view)
        elapsed = time.monotonic() - started
        dev.require(answer.status == "SCORED", "重型输入未全评分")
        entries = sorted([{"action_key": e.action_key, "score": e.score, "trace": dict(e.trace)}
            for e in answer.entries], key=lambda e: e["action_key"])
        legal = {a.action_key for a in view.actions}
        dev.require(len(entries) == len(legal) and {e["action_key"] for e in entries} == legal and
            digest(view.candidate_view()) == receipt.view_sha256, "重型合法集合或输入不变失败")
        return {"entries": entries, "operations": executor.last_operation_count,
            "ranking": [e["action_key"] for e in sorted(entries, key=lambda e: (-e["score"], e["action_key"]))]}, elapsed

    try:
        for case in cases:
            original = case["original_public_decision"]
            obs = observation_from_json(original["observation"])
            key = window_key_from_json(original["window_key"])
            rules = HangmaRules(batch.rule_config).analyze(obs, route_limits=batch.route_limits)
            dev.require(rules.completeness.value == "complete", "重型公开状态的规则分析未完整")
            request = DecisionRequest(obs, CompetitionContext("t185-heavy-equivalence", None, None, None, None, (), 0),
                rules, original["decision_id"], key.trigger_seq, key, ())
            view = build_vip_route_scoring_view(request, batch.rule_config, limits=batch.projection_limits)
            dev.require(digest(view.candidate_view()) == case["view_sha256"], "重建图与原实际完整图不同")
            outputs, timings = [], []
            for name, executor in executors.items():
                for repeat in range(2):
                    result, elapsed = score(executor, view)
                    outputs.append(result)
                    timings.append({"variant": name, "repeat": repeat, "scoring_seconds_not_pipeline": elapsed})
            dev.require(all(canonical(v) == canonical(outputs[0]) for v in outputs),
                "重型两实现全输出、排序、重复或计量不一致")
            # 父代来源只给公开输入，不冒充新候选答案；同胜者身份才核原全输出。
            if original["source_identity"] == arm["identity"]["candidate_id"]:
                expected = sorted([{"action_key": c["action_key"], "score": c["score"],
                    "trace": c["trace"]["detail"]} for c in original["candidates"]], key=lambda c: c["action_key"])
                dev.require(canonical(outputs[0]["entries"]) == canonical(expected) and
                    outputs[0]["operations"] == original["candidate_operations"], "同胜者原重型输出或计量漂移")
            if heaviest is None or outputs[0]["operations"] > heaviest[0]:
                heaviest = outputs[0]["operations"], view, case["view_sha256"]
            rows.append({"view_sha256": case["view_sha256"], "complete": True,
                "all_outputs_sha256": digest(outputs[0]), "operations": outputs[0]["operations"],
                "timings": timings, "groups": sorted({r["group"] for r in case["selected_for"]})})
        for limit in (0, heaviest[0] - 1):
            errors = []
            for executor in executors.values():
                original_limit = executor._meter.limit
                executor._meter.limit = limit
                try:
                    score(executor, heaviest[1])
                    raise ValueError("重型耗尽检查应失败却返回评分")
                except WorkloadExceeded as error:
                    errors.append({"type": type(error).__name__, "message": str(error),
                        "operations": executor.last_operation_count})
                finally:
                    executor._meter.limit = original_limit
            dev.require(canonical(errors[0]) == canonical(errors[1]), "重型耗尽类型、消息或真实计量不同")
            rows.append({"kind": "exhaustion", "limit": limit, "view_sha256": heaviest[2],
                "error": errors[0], "complete": True})
        dev.require(attempts == 80, "重型补充实际评分分母不同")
    except BaseException as error:
        failure = {"type": type(error).__name__, "message": str(error), "actual_score_attempts": attempts}
    finally:
        try:
            capture_result = capture.finish()
        except BaseException as error:
            failure = failure or {"type": type(error).__name__, "message": str(error)}
        raw.close()
        stable = all(pin(Path(p)) == expected for p, expected in files.items())
        complete = failure is None and len(rows) == 21 and attempts == 80 and stable and \
            capture_result is not None and capture_result["terminal"]["terminal_valid"] is True
        save(out / "CLOSED.json", {"complete": complete, "failure": failure, "source_stable": stable,
            "files": files, "identity": arm["identity"], "execution_id": runtime.execution_id,
            "actual_score_attempts": attempts, "rows": rows, "capture": capture_result,
            "new_worlds_tables_model_calls_HTTP": 0, "nominal_or_official_deadline_admission": False})
    dev.require(complete, "重型原体等价未通过，保留原失败，不自动重试")
    print({"complete": True, "actual_score_attempts": attempts, "deadline_admission": False})


if __name__ == "__main__":
    main()
