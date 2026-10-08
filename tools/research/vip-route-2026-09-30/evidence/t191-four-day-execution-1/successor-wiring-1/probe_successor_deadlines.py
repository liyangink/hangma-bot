"""胜者真实计算服务验原余量：39串行和两个十桌同时突发，不向官方发请求。"""
from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t191-four-day-execution-1/successor-wiring-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

import asyncio
import os
import time
from dataclasses import asdict
from pathlib import Path

from successor_verification_common import HERE, ROOT, canonical, pin, save
import t185_close_development as dev
from successor_verification_common import (check_files, digest, original_cases,
    resource_zero, validated_assembly, planned_scores, research_slots, PRIOR_PREPARATION)


async def main():
    """只在独立增强和编译等价通过后测真实往返；CPU正常优先级，原三段截止不扩。"""
    from successor_verification_common import bootstrap
    from hangma_bot.application.audit_codec import decision_plan_to_json, decision_request_to_json
    from hangma_bot.application.deadline import SystemClock
    from hangma_bot.policy.interface import DecisionBudget
    dev.require(os.nice(0) == 0, "性能探针必须正常CPU优先级，后台nice15不当线上速度")
    _, arm, runtime, files = validated_assembly()
    closed_file = PRIOR_PREPARATION / "native-verification/CLOSED.json"
    equivalent, equivalent_pin = dev.read(closed_file)
    dev.require(equivalent["complete"] is True and equivalent["compiled_formula_equivalence_admitted"] is True and
        equivalent["identity"] == arm["identity"] and equivalent["execution_id"] == runtime.original_execution_id and
        equivalent["actual_score_attempts"] == planned_scores() and len(equivalent["references"]) == 39,
        "胜者完整编译等价未通过")
    check_files(equivalent["files"])
    refs = {r["decision_id"]: r for r in equivalent["references"]}
    values = original_cases()
    dev.require(len(refs) == 39 and all(refs[q.decision_id]["game_id"] == q.window_key.game_id and
        refs[q.decision_id]["original_remaining_seconds"] == list(spans) for q, spans, _ in values), "原请求参考或余量不同")
    settings = bootstrap.VIP_S02_COMPUTE_SETTINGS
    dev.require(settings.workers == 10 and settings.max_pending == 0 and settings.per_game_workers is True,
        "探针未使用每桌专属十进程配置")
    factory = bootstrap._VipWorkerFactory(runtime.execution_id, bootstrap.VIP_S03_FREE_STRATEGY)
    out = _project_file(_PROJECT_ROOT, HERE / "original-deadline-probe")
    out.mkdir(exist_ok=False)
    files.update({str(closed_file): equivalent_pin, str(PRIOR_PREPARATION / "native-verification/views.jsonl.gz"):
        pin(PRIOR_PREPARATION / "native-verification/views.jsonl.gz")})
    save(out / "START.json", {"identity": arm["identity"], "execution_id": runtime.execution_id,
        "files": files, "planned_actual_service_choose": 59, "cpu_nice": os.nice(0),
        "compute_settings": asdict(settings),
        "cold_scope": "计算进程已预热后的首次choose；不是机器冷启动",
        "synthetic_burst_not_official_same_instant": True, "HTTP_calls": 0,
        "actual_typed_scoring_inputs_frozen_by_prior_equivalence": True})
    journal = (out / "rows.jsonl").open("x")
    waves, failure, calls = [], None, 0

    async def wave(label, selected, concurrent):
        """单波先预热和绑定最多十桌，结束回收；计时包括IPC，摘要在返回计时后算。"""
        nonlocal calls
        gids = sorted({q.window_key.game_id for q, _, _ in selected})
        dev.require(0 < len(gids) <= 10 and (not concurrent or len(gids) == len(selected) == 10), "并发波有同桌重复或超过资源")
        service = bootstrap.build_isolated_decision_policy(factory, execution_id=runtime.execution_id,
            clock=SystemClock(), settings=settings)
        started = time.monotonic()
        result = {"wave": label, "concurrent": concurrent, "real_distinct_game_ids": gids, "rows": [], "complete": False}
        burst_start = None  # 并发波共用新单调起点，串行请求分别起算；都保持原三段余量
        save(out / (label + "-START.json"), {"real_distinct_game_ids": gids, "planned_service_choose": len(selected),
            "execution_id": runtime.execution_id, "frozen_formula_source_file": arm["source_file"], "actual_public_factory": asdict(factory)})

        async def one(case):
            nonlocal calls
            request, spans, origin = case
            now = burst_start if concurrent else time.monotonic()
            calls += 1
            plan = None
            try:
                plan = await service.choose(request, DecisionBudget(*(now + v for v in spans)))
                elapsed = time.monotonic() - now
                row = {"status": "SCORED",
                    "returned_before_original_enhancement": elapsed <= spans[0],
                    "returned_before_original_fallback": elapsed <= spans[1],
                    "returned_before_original_latest_send": elapsed <= spans[2],
                    "complete": elapsed <= spans[1]}
            except BaseException as error:
                elapsed = time.monotonic() - now
                row = {"status": "FAILED", "complete": False,
                    "failure": {"type": type(error).__name__, "message": str(error)}}
            row.update(kind="after_choose", wave=label, decision_id=request.decision_id,
                game_id=request.window_key.game_id, roundtrip_seconds=elapsed,
                original_remaining_seconds=list(spans), origin=origin)
            return row, plan

        try:
            await service.start()
            result["startup_seconds"] = time.monotonic() - started
            for game in gids:
                await service.acquire_game(game)
            result["pre_choose_resources"] = service.snapshot()
            dev.require(result["pre_choose_resources"]["bound_games"] == len(gids), "每桌专属绑定未成立")
            # 全波原请求先落盘；热区没有工具自己的写盘、输入压缩或全计划摘要。
            for request, spans, origin in selected:
                before = {"kind": "before_choose", "wave": label, "decision_id": request.decision_id,
                    "request": decision_request_to_json(request), "original_remaining_seconds": list(spans),
                    "frozen_actual_typed_view_sha256": refs[request.decision_id]["view_sha256"], "origin": origin}
                journal.write(canonical(before).decode() + "\n")
            journal.flush()
            burst_start = time.monotonic() if concurrent else None
            answers = await asyncio.gather(*(one(c) for c in selected)) if concurrent else [await one(c) for c in selected]
            # 全波choose返回后才核摘要，避免父进程核第一份阻碍其余请求的响应处理。
            for row, plan in answers:
                if plan is not None:
                    row["full_child_plan_exact"] = digest(decision_plan_to_json(plan)) == refs[row["decision_id"]]["full_plan_sha256"]
                    row["complete"] = row["complete"] and row["full_child_plan_exact"]
                result["rows"].append(row)
                journal.write(canonical(row).decode() + "\n")
            journal.flush()
            result["after_choose_resources"] = service.snapshot()
            for game in gids:
                await service.release_game(game)
        except BaseException as error:
            result["failure"] = {"type": type(error).__name__, "message": str(error)}
        finally:
            try:
                await service.close()
            except BaseException as error:
                result["close_failure"] = {"type": type(error).__name__, "message": str(error)}
            result["resource_terminal"] = service.snapshot()
            result["resources_released"] = resource_zero(result["resource_terminal"])
            result["complete"] = (not result.get("failure") and not result.get("close_failure") and
                len(result["rows"]) == len(selected) and all(r["complete"] for r in result["rows"]) and result["resources_released"])
            save(out / (label + "-CLOSED.json"), result)
        return result

    try:
        # 原十九输入来自七桌；两首摸房分别十桌。新波不复用已关闭资源，失败不自动重试。
        groups = sorted({source["group"] for _, _, source in values[19:]})
        jobs = [("serial-original-19", values[:19], False)]
        for index, group in enumerate(groups, 1):
            selected = [c for c in values[19:] if c[2]["group"] == group]
            jobs.append((f"serial-supplement-{index}", selected, False))
        for index, group in enumerate(groups, 1):
            selected = [c for c in values[19:] if c[2]["group"] == group]
            jobs.append((f"concurrent-ten-{index}", selected, True))
        for label, selected, concurrent in jobs:
            result = await wave(label, selected, concurrent)
            waves.append(result)
            if not result["complete"]:
                raise ValueError("原窗口失败，保留该波并停止后续波:" + label)
        dev.require(calls == 59, "原时限服务choose分母不同")
    except BaseException as error:
        failure = {"type": type(error).__name__, "message": str(error)}
    finally:
        journal.close()
        stable = all(pin(Path(p)) == h for p, h in files.items()) and all(pin(_project_file(_PROJECT_ROOT, ROOT / p)) == h for p, h in arm["identity"]["source_manifest"].items())
        complete = failure is None and stable and len(waves) == 5 and all(w["complete"] for w in waves)
        save(out / "CLOSED.json", {"complete": complete, "failure": failure, "source_stable": stable,
            "identity": arm["identity"], "execution_id": runtime.execution_id, "files": files,
            "actual_service_choose": calls, "actual_scoring_attempts_if_choose_failed": "unknown;不得把失败按零评分记账",
            "waves": waves, "original_deadline_admitted_for_covered_inputs": complete,
            "all_dark_gang_replacement_extremes_covered": False, "online_or_formal_admission": False,
            "strength_evidence_not_extended_by_performance_inputs": True, "HTTP_model_calls_worlds_tables": 0})
    dev.require(complete, "胜者原时限或资源验证未通过")
    print({"complete": complete, "actual_service_choose": calls}, flush=True)


if __name__ == "__main__":
    with research_slots(4):
        asyncio.run(main())
