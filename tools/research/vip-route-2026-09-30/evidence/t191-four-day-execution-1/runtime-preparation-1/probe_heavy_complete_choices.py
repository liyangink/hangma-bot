"""最多32重型公开输入的全输出参考与名义窗口服务补测；不替换官方原预算门。"""
from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t191-four-day-execution-1/runtime-preparation-1'

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
import os
import time
from dataclasses import asdict
from pathlib import Path

from verification_common import (HERE, ROOT, canonical, pin, save, ConfirmedCandidateFactory,
    check_files, digest, make_policy, resource_zero, validated_candidate, planned_scores, research_slots)
import t185_close_development as dev


def heavy_cases(files):
    """读取已封存公开输入；仅解码，不重算规则、图或候选，不读取确认中途分。"""
    from hangma_bot.kernel.serialization import observation_from_json, window_key_from_json
    base = _project_file(_PROJECT_ROOT, HERE / "development-heavy-inputs")
    closed, closed_pin = dev.read(base / "CLOSED.json")
    cases_path = base / "CASES.json"
    cases = dev.read(cases_path)[0]["cases"]
    dev.require(closed["complete"] is True and closed["source_stable"] is True and
        closed["selected_unique_views"] == len(cases) and 0 < len(cases) <= 32 and closed["cases_pin"] == pin(cases_path) and
        closed["new_rule_analyses_scores_worlds_tables_model_calls_HTTP"] == 0,
        "重型原公开输入准备未闭合")
    check_files(closed["files"])
    files.update(closed["files"])
    files.update({str(p): pin(p) for p in (Path(__file__), base / "CLOSED.json", cases_path,
        base / "original-heavy-views.jsonl.gz", _project_file(_PROJECT_ROOT, ROOT / "src/hangma_bot/bootstrap.py"),
        _project_file(_PROJECT_ROOT, ROOT / "src/hangma_bot/application/deadline.py"), _project_file(_PROJECT_ROOT, ROOT / "src/hangma_bot/application/contracts.py"),
        _project_file(_PROJECT_ROOT, ROOT / "src/hangma_bot/application/decision_compute.py"))})
    dev.require(pin(base / "original-heavy-views.jsonl.gz") == closed["original_heavy_views_pin"],
        "重型原完整图封存漂移")
    decoded = []
    for case in cases:
        raw = case["original_public_decision"]
        observation = observation_from_json(raw["observation"])
        key = window_key_from_json(raw["window_key"])
        dev.require(raw["phase"] == observation.phase == key.phase.value and
            type(raw["decision_id"]) is str and raw["decision_id"], "公开输入窗口或决策身份矛盾")
        # 模拟桌ID保持原值；不同换座的相同ID也不会被伪造成并发不同桌。
        dev.require(case["simulation_game_not_official_original_deadline"] is True,
            "名义压力输入不能冒充官方原截止")
        decoded.append((case, observation, key, 3.0 if raw["phase"] == "draw" else 1.0))
    dev.require(len({c[0]["view_sha256"] for c in decoded}) == len(decoded),
        "重型图重复，须检查而非改ID；不同图可能属于父子同一原决策ID")
    return decoded, closed_pin


def prerequisites(arm, runtime, files, *, official_deadlines=False):
    """实际638等价门及绑定核齐；服务名义补测另须59原截止门通过。"""
    name = "native-verification"
    path = _project_file(_PROJECT_ROOT, HERE / name / "CLOSED.json")
    closed, closed_pin = dev.read(path)
    dev.require(closed["complete"] is True and closed["source_stable"] is True and
        closed["compiled_formula_equivalence_admitted"] is True and
        closed["identity"] == arm["identity"] and closed["execution_id"] == runtime.execution_id and
        closed["actual_score_attempts"] == planned_scores() and
        closed["capture"]["terminal"]["terminal_valid"] is True,
        "638实际等价评分未完整通过或不是本轮胜者")
    check_files(closed["files"])
    files.update(closed["files"])
    files.update({str(path): closed_pin,
        str(_project_file(_PROJECT_ROOT, HERE / name / "views.jsonl.gz")): pin(_project_file(_PROJECT_ROOT, HERE / name / "views.jsonl.gz"))})
    if official_deadlines:
        path = _project_file(_PROJECT_ROOT, HERE / "original-deadline-probe/CLOSED.json")
        closed, closed_pin = dev.read(path)
        dev.require(closed["complete"] is True and closed["source_stable"] is True and
            closed["original_deadline_admitted_for_covered_inputs"] is True and
            closed["identity"] == arm["identity"] and closed["execution_id"] == runtime.execution_id and
            closed["actual_service_choose"] == 59 and all(w["resources_released"] for w in closed["waves"]),
            "59原预算门未通过，不能用名义补测抵消")
        check_files(closed["files"])
        files.update(closed["files"])
        files[str(path)] = closed_pin


def request_for(case, observation, key, rules):
    """仅由原公开状态和唯一规则事实构造请求；赛事默认均衡，无隐藏世界。"""
    from hangma_bot.kernel.observation import CompetitionContext
    from hangma_bot.policy.interface import DecisionRequest
    return DecisionRequest(observation, CompetitionContext("t191-heavy-complete", None, None,
        None, None, (), 0), rules, case["original_public_decision"]["decision_id"], key.trigger_seq, key, ())


def source_stable(files, arm):
    """输入、工具与当前生产依赖均保持事前字节；不从路径名继承验收。"""
    return (all(pin(Path(p)) == h for p, h in files.items()) and
        all(pin(_project_file(_PROJECT_ROOT, ROOT / p)) == h for p, h in arm["identity"]["source_manifest"].items()))


async def reference(batch, arm, runtime, files, cases, heavy_pin):
    """N个输入各一次Python和原体完整choose，共2N实际评分；宽功能预算不授时限。"""
    from t185_prepare_confirmation import background_priority, postprocess_lock
    from hangma_bot.application.audit_codec import decision_plan_to_json
    from hangma_bot.hangma.engine import HangmaRules
    from hangma_bot.offline.scoring_input_capture import ScoringInputCapture, ScoringInputCaptureLimits
    from hangma_bot.policy.interface import DecisionBudget
    prerequisites(arm, runtime, files)
    background_priority()
    # 只在完整确认后做新增评分；重型捕获IO与既有后台赛后采集共用锁。
    with postprocess_lock("t191-heavy-full-reference"):
        out = _project_file(_PROJECT_ROOT, HERE / "heavy-complete-reference")
        out.mkdir(exist_ok=False)
        save(out / "START.json", {"files": files, "identity": arm["identity"],
            "execution_id": runtime.execution_id, "heavy_input_closed_pin": heavy_pin,
            "planned_actual_score_attempts": 2 * len(cases), "wide_functional_budget_not_deadline_evidence": True})
        raw = (out / "views.jsonl.gz").open("x+b")
        capture = ScoringInputCapture(raw, limits=ScoringInputCaptureLimits(67108864, 1073741824, 32))
        source = Path(arm["source_file"]).read_text()
        references, attempts, failure, capture_result = [], 0, None, None
        try:
            for case, obs, key, nominal in cases:
                rules = HangmaRules(batch.rule_config).analyze(obs, route_limits=batch.route_limits)
                dev.require(rules.completeness.value == "complete", "重型参考规则分析未完整")
                request = request_for(case, obs, key, rules)
                outputs, timings, receipts = [], [], []
                for name, compiled in (("python", None), ("native", runtime)):
                    policy = make_policy(batch, source, compiled)
                    original_score = policy.executor.score_vip_route
                    saved = []

                    def recorded(view):
                        nonlocal attempts
                        receipt = capture.store(view.candidate_view())
                        dev.require(receipt.saved_before_score and receipt.view_sha256 == case["view_sha256"],
                            "重型完整choose实际图与封存图不同或未事前保存")
                        attempts += 1
                        answer = original_score(view)
                        dev.require(answer.status == "SCORED" and digest(view.candidate_view()) == receipt.view_sha256,
                            "重型完整评分失败或修改输入")
                        saved.append(asdict(receipt))
                        return answer

                    policy.executor.score_vip_route = recorded
                    start = time.monotonic()
                    plan = await policy.choose(request, DecisionBudget(start + 60, start + 61, start + 62))
                    elapsed = time.monotonic() - start
                    dev.require(len(saved) == 1 and not plan.degraded_reasons and plan.candidates,
                        "重型完整choose未一次全评分")
                    outputs.append({"plan": decision_plan_to_json(plan), "operations": policy.executor.last_operation_count})
                    receipts.append({"variant": name, **saved[0]})
                    timings.append({"variant": name, "choose_seconds_with_capture_not_production_timing": elapsed})
                dev.require(canonical(outputs[0]) == canonical(outputs[1]), "重型完整计划及计量两实现不等价")
                references.append({"decision_id": request.decision_id, "game_id": key.game_id,
                    "view_sha256": case["view_sha256"], "full_plan_sha256": digest(outputs[0]["plan"]),
                    "operations": outputs[0]["operations"], "nominal_window_seconds": nominal,
                    "timings": timings, "receipts": receipts})
            dev.require(len(references) == len(cases) and attempts == 2 * len(cases), "重型全输出参考分母不同")
        except BaseException as error:
            failure = {"type": type(error).__name__, "message": str(error)}
        finally:
            try:
                capture_result = capture.finish()
            except BaseException as error:
                failure = failure or {"type": type(error).__name__, "message": str(error)}
            raw.close()
            stable = source_stable(files, arm)
            complete = failure is None and stable and len(references) == len(cases) and attempts == 2 * len(cases) and \
                capture_result is not None and capture_result["terminal"]["terminal_valid"] is True
            save(out / "CLOSED.json", {"complete": complete, "failure": failure, "source_stable": stable,
                "files": files, "identity": arm["identity"], "execution_id": runtime.execution_id,
                "references": references, "actual_score_attempts": attempts, "capture": capture_result,
                "wide_functional_budget_not_deadline_evidence": True, "new_worlds_tables_HTTP_model_calls": 0})
        dev.require(complete, "重型全输出参考未通过，原尝试保留，不自动重试")
        print({"complete": True, "actual_score_attempts": attempts}, flush=True)


async def probe(batch, arm, runtime, files, cases, heavy_pin):
    """正常优先级真实子进程逐个测N个输入；从规则分析前起算，不重置名义窗口。"""
    from hangma_bot import bootstrap
    from hangma_bot.application.audit_codec import decision_plan_to_json
    from hangma_bot.application.deadline import BudgetPolicy, SystemClock
    from hangma_bot.hangma.engine import HangmaRules
    dev.require(os.nice(0) == 0, "名义窗口计时必须正常CPU优先级")
    prerequisites(arm, runtime, files, official_deadlines=True)
    path = _project_file(_PROJECT_ROOT, HERE / "heavy-complete-reference/CLOSED.json")
    reference_closed, reference_pin = dev.read(path)
    dev.require(reference_closed["complete"] is True and reference_closed["source_stable"] is True and
        reference_closed["identity"] == arm["identity"] and reference_closed["execution_id"] == runtime.execution_id and
        reference_closed["actual_score_attempts"] == 2 * len(cases) and len(reference_closed["references"]) == len(cases) and
        reference_closed["capture"]["terminal"]["terminal_valid"] is True, "重型全输出参考未通过")
    check_files(reference_closed["files"])
    files.update(reference_closed["files"])
    files.update({str(path): reference_pin, str(_project_file(_PROJECT_ROOT, HERE / "heavy-complete-reference/views.jsonl.gz")):
        pin(_project_file(_PROJECT_ROOT, HERE / "heavy-complete-reference/views.jsonl.gz"))})
    refs = {r["view_sha256"]: r for r in reference_closed["references"]}
    dev.require(len(refs) == len(cases) and all(refs[c["view_sha256"]]["decision_id"] == c["original_public_decision"]["decision_id"] and
        refs[c["view_sha256"]]["game_id"] == key.game_id and refs[c["view_sha256"]]["nominal_window_seconds"] == nominal
        for c, _, key, nominal in cases), "名义窗口全计划参考身份不同")
    settings = bootstrap.VIP_S02_COMPUTE_SETTINGS
    dev.require(settings.workers == 10 and settings.max_pending == 0 and settings.per_game_workers is True,
        "未使用十个每桌独占预热计算槽")
    factory = ConfirmedCandidateFactory(arm["source_file"], arm["identity"]["candidate_id"], runtime.execution_id)
    service = bootstrap.build_isolated_decision_policy(factory, execution_id=runtime.execution_id,
        clock=SystemClock(), settings=settings)
    out = _project_file(_PROJECT_ROOT, HERE / "heavy-nominal-deadline-probe")
    out.mkdir(exist_ok=False)
    budget_policy = BudgetPolicy()
    save(out / "START.json", {"files": files, "identity": arm["identity"], "execution_id": runtime.execution_id,
        "heavy_input_closed_pin": heavy_pin, "planned_service_choose": len(cases), "planned_rule_analyses": len(cases),
        "cpu_nice": os.nice(0), "compute_settings": asdict(settings), "budget_policy": asdict(budget_policy),
        "serial_distinct_windows_not_concurrent_ten_room_evidence": True,
        "nominal_budget_not_original_official_deadline": True, "HTTP_model_calls_worlds_tables": 0})
    journal = (out / "rows.jsonl").open("x")
    rows, calls, analyses, failure = [], 0, 0, None
    try:
        await service.start()
        gids = sorted({key.game_id for _, _, key, _ in cases})
        dev.require(gids, "重型原模拟桌缺失")
        save(out / "READY.json", {"pre_choose_resources": service.snapshot(), "simulation_game_ids": gids,
            "serial_bind_release_each_original_game_without_renaming": True})
        for case, obs, key, nominal in cases:
            # 串行原窗口逐个绑定；不同开发来源可超过十桌，但同时只有一桌占槽。
            await service.acquire_game(key.game_id)
            dev.require(service.snapshot()["bound_games"] == 1, "重型原模拟桌未独占绑定")
            # 原公开输入与全计划参考先落盘，热区无本工具的压缩、写盘或全计划摘要。
            journal.write(canonical({"kind": "before_rule_and_choose", "public_decision": case["original_public_decision"],
                "view_sha256": case["view_sha256"], "nominal_window_seconds": nominal,
                "expected_full_plan_sha256": refs[case["view_sha256"]]["full_plan_sha256"]}).decode() + "\n")
            journal.flush()
            now = time.monotonic()
            budget = budget_policy.build(now, nominal)
            spans = [getattr(budget, field) - now for field in ("enhancement_deadline_monotonic",
                "fallback_deadline_monotonic", "latest_send_at_monotonic")]
            analyses += 1
            rules = HangmaRules(batch.rule_config).analyze(obs, route_limits=batch.route_limits)
            after_rules = time.monotonic()
            dev.require(rules.completeness.value == "complete", "名义窗口规则分析未完整")
            request = request_for(case, obs, key, rules)
            choose_start = time.monotonic()
            calls += 1
            plan, error = None, None
            try:
                plan = await service.choose(request, budget)
            except BaseException as exc:
                error = {"type": type(exc).__name__, "message": str(exc)}
            returned = time.monotonic()
            exact = plan is not None and digest(decision_plan_to_json(plan)) == refs[case["view_sha256"]]["full_plan_sha256"]
            row = {"kind": "after_choose", "decision_id": request.decision_id, "game_id": key.game_id,
                "view_sha256": case["view_sha256"], "failure": error, "full_plan_exact": exact,
                "nominal_window_seconds": nominal, "budget_relative_seconds": spans,
                "rules_seconds": after_rules - now, "service_roundtrip_seconds_including_IPC": returned - choose_start,
                "total_rules_and_service_seconds": returned - now,
                "isolated_IPC_component_seconds": "unknown;不从带捕获参考的差值推算",
                "returned_before_enhancement": returned <= budget.enhancement_deadline_monotonic,
                "returned_before_fallback": returned <= budget.fallback_deadline_monotonic,
                "returned_before_latest_send": returned <= budget.latest_send_at_monotonic,
                "complete": error is None and exact and returned <= budget.fallback_deadline_monotonic}
            rows.append(row)
            journal.write(canonical(row).decode() + "\n")
            journal.flush()
            await service.release_game(key.game_id)
            dev.require(row["complete"], "名义重型窗口失败，原结果保留并停止后续窗口")
    except BaseException as error:
        failure = {"type": type(error).__name__, "message": str(error)}
    finally:
        try:
            await service.close()
        except BaseException as error:
            failure = failure or {"type": type(error).__name__, "message": str(error)}
        journal.close()
        terminal = service.snapshot()
        stable = source_stable(files, arm)
        complete = failure is None and stable and calls == analyses == len(rows) == len(cases) and \
            all(r["complete"] for r in rows) and resource_zero(terminal)
        save(out / "CLOSED.json", {"complete": complete, "failure": failure, "source_stable": stable,
            "files": files, "identity": arm["identity"], "execution_id": runtime.execution_id,
            "actual_service_choose": calls, "actual_rule_analyses": analyses, "rows": rows,
            "scoring_attempts_inside_service": "unknown;choose失败不按零评分记账",
            "resource_terminal": terminal, "resources_released": resource_zero(terminal),
            "nominal_budget_not_original_official_deadline": True, "online_or_formal_admission": False,
            "HTTP_model_calls_worlds_tables": 0})
    dev.require(complete, "重型名义窗口或资源未通过，原失败保留，不自动重试")
    print({"complete": True, "actual_service_choose": calls, "online_admission": False}, flush=True)


async def main():
    """真实确认是共同第一门；缺终态时不建输出、工厂、执行器或计算服务。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", required=True, choices=("reference", "probe"))
    args = parser.parse_args()
    batch, arm, runtime, files = validated_candidate()
    cases, heavy_pin = heavy_cases(files)
    fn = reference if args.phase == "reference" else probe
    with research_slots(1 if args.phase == "reference" else 4):
        await fn(batch, arm, runtime, files, cases, heavy_pin)


if __name__ == "__main__":
    asyncio.run(main())
