"""确认胜者的Python/编译全输出和计量等价；宽功能预算不授原时限。"""
from __future__ import annotations

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

import asyncio
import time
from dataclasses import asdict
from pathlib import Path

from common import HERE, ROOT, canonical, pin, save
import t185_close_development as dev
from candidate_verification_common import (check_files, digest, make_policy, original_cases, validated_candidate)


async def main():
    """115公开图双重复、4耗尽检查、39原请求双实现，共542评分；失败保留原收据。"""
    from t185_prepare_confirmation import background_priority
    from hangma_bot.application.audit_codec import decision_plan_to_json
    from hangma_bot.hangma.engine import HangmaRules
    from hangma_bot.kernel.observation import CompetitionContext
    from hangma_bot.kernel.serialization import observation_from_json, window_key_from_json
    from hangma_bot.offline.scoring_input_capture import ScoringInputCapture, ScoringInputCaptureLimits
    from hangma_bot.policy.action_value_executor import ActionValueExecutor, WorkloadExceeded
    from hangma_bot.policy.interface import DecisionBudget, DecisionRequest
    from hangma_bot.policy.route_vip_heuristic import build_vip_route_scoring_view
    background_priority()
    batch, arm, runtime, files = validated_candidate()
    cases = [c for name in ("CASES.json", "SUPPLEMENT-CASES.json") for c in dev.read(_project_file(_PROJECT_ROOT, HERE / name))[0]["cases"]]
    qualification, _ = dev.read(Path(arm["qualification_file"]))
    prior = {r["label"]: r for r in qualification["rows"]}
    dev.require(qualification["complete"] and qualification["identity"] == arm["identity"] and len(cases) == len(prior) == 115,
        "胜者公开资格面板不完整")
    originals = original_cases()
    files.update({str(_project_file(_PROJECT_ROOT, HERE / n)): pin(_project_file(_PROJECT_ROOT, HERE / n)) for n in ("CASES.json", "SUPPLEMENT-CASES.json", "AUTHOR-BATCH.json")})
    out = _project_file(_PROJECT_ROOT, HERE / "native-verification")
    out.mkdir(exist_ok=False)
    save(out / "START.json", {"identity": arm["identity"], "execution_id": runtime.execution_id, "files": files,
        "source_manifest": arm["identity"]["source_manifest"], "planned_score_attempts": 542,
        "planned_public_views": 115, "planned_original_requests": 39, "original_deadline_admitted": False})
    source = Path(arm["source_file"]).read_text()
    executors = {"python": ActionValueExecutor(source, max_operations=batch.max_operations,
        max_local_collection_size=batch.projection_limits.max_nodes),
        "native": ActionValueExecutor(source, max_operations=batch.max_operations,
        max_local_collection_size=batch.projection_limits.max_nodes, compiled_runtime=runtime)}
    raw = (out / "views.jsonl.gz").open("x+b")
    capture = ScoringInputCapture(raw, limits=ScoringInputCaptureLimits(67108864, 1073741824, 256))
    rows, references, attempts, failure, capture_result, heaviest = [], [], 0, None, None, None

    def score(executor, view):
        """每次真实评分前保存同一公开图；重复图也记独立尝试，超限不免费。"""
        nonlocal attempts
        receipt = capture.store(view.candidate_view())
        dev.require(receipt.saved_before_score, "评分前捕获失败")
        attempts += 1
        answer = executor.score_vip_route(view)
        dev.require(answer.status == "SCORED", "非完整评分")
        entries = sorted([{"action_key": e.action_key, "score": e.score, "trace": dict(e.trace)} for e in answer.entries],
            key=lambda e: e["action_key"])
        legal = {a.action_key for a in view.actions}
        dev.require(len(entries) == len(legal) and {e["action_key"] for e in entries} == legal, "合法根评分缺失或重复")
        dev.require(digest(view.candidate_view()) == receipt.view_sha256, "评分改动公开输入")
        return {"entries": entries, "operations": executor.last_operation_count,
            "ranking": [e["action_key"] for e in sorted(entries, key=lambda e: (-e["score"], e["action_key"]))]}, asdict(receipt)

    try:
        with (out / "rows.jsonl").open("x") as stream:
            for case in cases:
                obs, key = observation_from_json(case["observation"]), window_key_from_json(case["window_key"])
                rules = HangmaRules(batch.rule_config).analyze(obs, route_limits=batch.route_limits)
                dev.require(rules.completeness.value == "complete", "公开请求规则未完整")
                request = DecisionRequest(obs, CompetitionContext("t185-native", None, None, None, None, (), 0),
                    rules, case["label"], key.trigger_seq, key, ())
                view = build_vip_route_scoring_view(request, batch.rule_config, limits=batch.projection_limits)
                dev.require(digest(view.candidate_view()) == prior[case["label"]]["view_sha256"], "原资格图漂移")
                outputs, receipts = [], []
                for name, executor in executors.items():
                    for repeat in range(2):
                        output, receipt = score(executor, view)
                        outputs.append(output)
                        receipts.append({"variant": name, "repeat": repeat, **receipt})
                dev.require(all(canonical(o) == canonical(outputs[0]) for o in outputs) and
                    canonical(outputs[0]["entries"]) == canonical(prior[case["label"]]["entries"]) and
                    outputs[0]["operations"] == prior[case["label"]]["operation_counts"][0], "完整输出、重复或真实计量不等价")
                if heaviest is None or outputs[0]["operations"] > heaviest[0]:
                    heaviest = outputs[0]["operations"], view, case["label"]
                row = {"kind": "public_view", "label": case["label"], "view_sha256": receipts[0]["view_sha256"],
                    "all_outputs_sha256": digest(outputs[0]), "operations": outputs[0]["operations"], "receipts": receipts, "complete": True}
                rows.append(row)
                stream.write(canonical(row).decode() + "\n")
                stream.flush()
            # 正常装载后调同型计量器限制，只测整批耗尽行为，不给实际候选放宽额度。
            for limit in (0, heaviest[0] - 1):
                failures = []
                for name, executor in executors.items():
                    saved_limit = executor._meter.limit
                    executor._meter.limit = limit
                    try:
                        score(executor, heaviest[1])
                        raise ValueError("应耗尽却返回评分")
                    except WorkloadExceeded as error:
                        failures.append({"type": type(error).__name__, "message": str(error), "operations": executor.last_operation_count})
                    finally:
                        executor._meter.limit = saved_limit
                dev.require(canonical(failures[0]) == canonical(failures[1]), "两实现耗尽类型、消息或计量不同")
                row = {"kind": "exhaustion", "label": heaviest[2], "limit": limit, "failure": failures[0], "complete": True}
                rows.append(row)
                stream.write(canonical(row).decode() + "\n")
                stream.flush()
            for request, spans, origin in originals:
                outputs, receipts = [], []
                for name, compiled in (("python", None), ("native", runtime)):
                    policy = make_policy(batch, source, compiled)
                    original_score = policy.executor.score_vip_route
                    saved = []

                    def recorded(view):
                        nonlocal attempts
                        receipt = capture.store(view.candidate_view())
                        dev.require(receipt.saved_before_score, "原请求评分前捕获失败")
                        attempts += 1
                        answer = original_score(view)
                        dev.require(digest(view.candidate_view()) == receipt.view_sha256, "原请求评分改输入")
                        saved.append(asdict(receipt))
                        return answer

                    policy.executor.score_vip_route = recorded
                    now = time.monotonic()
                    plan = await policy.choose(request, DecisionBudget(now + 3, now + 3.5, now + 4))
                    dev.require(len(saved) == 1, "实际请求评分次数不同")
                    outputs.append({"full_plan": decision_plan_to_json(plan), "operations": policy.executor.last_operation_count})
                    receipts.append({"variant": name, **saved[0]})
                dev.require(canonical(outputs[0]) == canonical(outputs[1]) and receipts[0]["view_sha256"] == receipts[1]["view_sha256"],
                    "原请求两实现全分值、解释、排名、计量或公开图不同")
                reference = {"decision_id": request.decision_id, "game_id": request.window_key.game_id,
                    "full_plan_sha256": digest(outputs[0]["full_plan"]), "operations": outputs[0]["operations"],
                    "view_sha256": receipts[0]["view_sha256"], "original_remaining_seconds": list(spans), "origin": origin}
                references.append(reference)
                row = {"kind": "original_request", **reference, "receipts": receipts, "complete": True}
                rows.append(row)
                stream.write(canonical(row).decode() + "\n")
                stream.flush()
        dev.require(attempts == 542 and len(rows) == 156 and len(references) == 39, "实际验证分母错误")
    except BaseException as error:
        failure = {"type": type(error).__name__, "message": str(error), "completed_rows": len(rows), "actual_score_attempts": attempts}
    finally:
        try:
            capture_result = capture.finish()
        except BaseException as error:
            failure = failure or {"type": type(error).__name__, "message": str(error)}
        raw.close()
        stable = all(pin(Path(p)) == h for p, h in files.items()) and all(pin(_project_file(_PROJECT_ROOT, ROOT / p)) == h for p, h in arm["identity"]["source_manifest"].items())
        complete = failure is None and stable and capture_result is not None and capture_result["terminal"]["terminal_valid"]
        save(out / "CLOSED.json", {"complete": complete, "failure": failure, "files": files, "source_stable": stable,
            "identity": arm["identity"], "execution_id": runtime.execution_id, "actual_score_attempts": attempts,
            "completed_rows": len(rows), "references": references, "capture": capture_result,
            "compiled_formula_equivalence_admitted": complete, "original_deadline_admitted": False,
            "wide_functional_budget_not_timing_evidence": True, "new_worlds_tables_HTTP_model_calls": 0})
    dev.require(complete, "候选编译等价未通过，原失败保留")
    print({"complete": complete, "actual_score_attempts": attempts, "original_requests": len(references)}, flush=True)


if __name__ == "__main__":
    asyncio.run(main())
