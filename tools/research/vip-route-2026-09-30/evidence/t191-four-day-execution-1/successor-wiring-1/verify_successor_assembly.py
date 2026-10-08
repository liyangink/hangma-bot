"""真实公开组合根验八包隔离、启动拒绝和编译公式选择，不连接官方平台。"""
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

import argparse
import asyncio
import hashlib
import json
import sys
import tempfile
from dataclasses import asdict
from pathlib import Path


def pin(path):
    """指定原文件的完整字节身份。"""
    raw = path.read_bytes()
    return {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def canonical(value):
    """全计划规范JSON，用于比较全部动作、分值、解释及排序。"""
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def save(path, value):
    """真实结果独占保存；失败不能覆盖或自动重跑。"""
    with path.open("x") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


async def main():
    """先核固定输入，再逐个验证；宽功能预算不授动作时限。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    args = parser.parse_args()
    work, out = args.workspace.resolve(), args.evidence.resolve()
    sys.path[:0] = [str(work / "src"), str(work)]
    from hangma_bot import bootstrap as b
    from hangma_bot.application.auto_match_runtime import AutoMatchSettings
    from hangma_bot.application.audit_codec import decision_plan_to_json
    from hangma_bot.hangma.engine import HangmaRules
    from hangma_bot.kernel.serialization import observation_from_json, window_key_from_json
    from hangma_bot.kernel.observation import CompetitionContext
    from hangma_bot.policy.interface import DecisionRequest, DecisionBudget
    from hangma_bot.policy.route_vip_heuristic import RouteVipHeuristicPolicy
    from hangma_bot.kernel.config import RuleConfig
    from hangma_bot.kernel.actions import Hu
    import time
    assert Path(b.__file__).resolve().is_relative_to(work)
    packages = json.loads((out / "PACKAGES-CLOSED.json").read_text())
    assert packages["complete"] and packages["source_manifest"] == b._vip_runtime_sources()
    rows = packages["rows"]
    assert len(rows) == 8
    files = {str(Path(__file__).resolve()): pin(Path(__file__).resolve()),
        str(out / "PACKAGES-CLOSED.json"): pin(out / "PACKAGES-CLOSED.json")}
    for row in rows:
        for kind in ("package", "config"):
            path = work / row[kind + "_path"]
            assert pin(path) == row[kind + "_pin"]
            files[str(path)] = pin(path)
    inputs = out.parent / "runtime-preparation-1/VALIDATION-INPUTS.json"
    public = json.loads(inputs.read_text())["public_cases"]
    files[str(inputs)] = pin(inputs)
    save(out / "ASSEMBLY-VALIDATION-START.json", {"files": files, "source_manifest": packages["source_manifest"],
        "planned_mode_checks": 32, "planned_missing_or_wrong_id_checks": 16,
        "planned_sse_and_guide_checks": 16, "planned_parent_functional_score_calls": 10,
        "planned_real_compute_children": 0, "new_worlds_tables_HTTP_model_calls": 0})
    checks, scored, units, analyses, failure = [], 0, [], 0, None
    selected = None

    def config_for(row, **changes):
        """公开配置入口；凭据为无效测试字串，绝不读取真实Token。"""
        mode = changes.pop("mode", row["mode"])
        values = dict(mode=mode, token_kind="test" if mode in ("test_room", "test_tournament") else "official",
            token="public-fake-only", base_url="https://platform.invalid", expected_tournament_id="public-t1",
            known_guide_version=35, audit_root=str(audit / row["strategy"]), strategy=row["strategy"],
            sse_enabled=True, discard_pacing_enabled=False, expected_policy_release_id=row["package_id"])
        values.update(changes)
        return b.runtime_config_from_mapping(values)

    def reject(name, call, contains=None):
        """只接受预期配置/验签错误；异常类型或原因不同不能算通过。"""
        try:
            call()
        except (ValueError, RuntimeError) as error:
            if contains is not None:
                assert contains in str(error), str(error)
            checks.append({"check": name, "rejected": True, "error_type": type(error).__name__, "reason": str(error)})
        else:
            raise AssertionError("未拒绝: " + name)

    with tempfile.TemporaryDirectory(prefix="t191-successor-assembly-") as temp:
        audit = Path(temp)
        try:
            for row in rows:
                for mode in ("test_room", "auto_match", "test_tournament", "official_tournament"):
                    label = row["strategy"] + ":mode:" + mode
                    if mode == row["mode"]:
                        config_for(row, mode=mode)
                        checks.append({"check": label, "accepted": True})
                    else:
                        reject(label, lambda row=row, mode=mode: config_for(row, mode=mode), "各自绑定的模式")
                for label, values in (("missing_id", {"expected_policy_release_id": None}),
                        ("wrong_id", {"expected_policy_release_id": "0" * 64}),
                        ("sse_off", {"sse_enabled": False}), ("old_guide", {"known_guide_version": 34})):
                    reject(row["strategy"] + ":" + label, lambda row=row, values=values: config_for(row, **values))
            # 首个具有合法胡候选的已有机械控制；不按成绩、评分差或耗时挑选。
            selected = None
            rule_config = RuleConfig(b.DEFAULT_RULESET_VERSION, 1, False)
            for case in public[:35]:
                obs, key = observation_from_json(case["observation"]), window_key_from_json(case["window_key"])
                analyses += 1
                rules = HangmaRules(rule_config).analyze(obs, route_limits=b.VIP_S02_ROUTE_LIMITS)
                if any(isinstance(c.action, Hu) for c in rules.legal_candidates):
                    selected = case, obs, key, rules
                    break
            assert selected is not None, "机械控制缺Hu输入，不能临时制造样本"
            case, obs, key, rules = selected
            request = DecisionRequest(obs, CompetitionContext("t191-successor-assembly", None, None, None, None, (), 0),
                rules, "t191-successor-functional", key.trigger_seq, key, ())
            references = {}

            async def choose(policy):
                """一次完整评分；计入真实调用，功能预算不是原窗口证据。"""
                nonlocal scored
                original = policy.executor.score_vip_route
                calls = []

                def recorded(view):
                    nonlocal scored
                    scored += 1
                    result = original(view)
                    calls.append(result.status)
                    return result

                policy.executor.score_vip_route = recorded
                now = time.monotonic()
                plan = await policy.choose(request, DecisionBudget(now + 10, now + 11, now + 12))
                assert calls == ["SCORED"] and not plan.degraded_reasons and plan.candidates
                return {"full_plan": decision_plan_to_json(plan), "operations": policy.executor.last_operation_count}

            for family, source in (("T110-S03", b.VIP_S03_SOURCE), ("T110-S02-backup", b.VIP_S02_SOURCE)):
                policy = RouteVipHeuristicPolicy(rule_config, source=source, max_operations=4_800_000,
                    projection_limits=b.VIP_S02_PROJECTION_LIMITS)
                references[family] = await choose(policy)
            for row in rows:
                cfg = config_for(row)
                unit = (b.build_auto_match_runtime(cfg, AutoMatchSettings(), session_factory=lambda: object())
                    if row["mode"] == "auto_match" else b.build_runtime(cfg, session_factory=lambda: object()))
                units.append(unit)
                assert asdict(unit.compute.factory) == {"expected_id": row["package_id"], "strategy": row["strategy"]}
                actual = unit.compute.factory()
                assert actual.execution_id == row["package_id"]
                answer = await choose(actual.policy)
                assert canonical(answer) == canonical(references[row["family"]])
                await unit.compute.close()
                await unit.sink.aclose(timeout_seconds=2)
                terminal = unit.compute.snapshot()
                assert terminal["closed"] is True and all(terminal[k] == 0 for k in
                    ("active", "current", "owned", "pending", "ready", "live_processes", "bound_games", "releasing_games",
                     "transport_inflight", "transport_threads_alive", "late_reap_inflight", "late_reap_threads_alive"))
                checks.append({"check": row["strategy"] + ":actual_factory", "complete": True,
                    "full_plan_sha256": hashlib.sha256(canonical(answer["full_plan"])).hexdigest(),
                    "actual_operations": answer["operations"], "resource_terminal": terminal})
            from scripts.run_test_room import _require_strategy
            for row in rows:
                if row["mode"] != "test_room":
                    reject(row["strategy"] + ":room_launcher", lambda row=row: _require_strategy(row["strategy"]), "不能用于测试房")
            old = [b.VIP_S02_FREE_SUCCESSOR_STRATEGY, b.VIP_S02_TESTROOM_SUCCESSOR_STRATEGY]
            for strategy in old:
                reject(strategy + ":old_source_drift", lambda strategy=strategy: b._load_vip_manifest(strategy), "完整运行源码摘要漂移")
            assert len(checks) == 80 and scored == 10
        except BaseException as error:
            failure = {"type": type(error).__name__, "message": str(error)}
        finally:
            for unit in units:
                try:
                    await unit.compute.close()
                    await unit.sink.aclose(timeout_seconds=2)
                except BaseException as error:
                    failure = failure or {"type": type(error).__name__, "message": "资源关闭: " + str(error)}
            stable = (b._vip_runtime_sources() == packages["source_manifest"] and
                all(pin(Path(path)) == expected for path, expected in files.items()))
            complete = failure is None and stable and len(checks) == 80 and scored == 10
            save(out / "ASSEMBLY-VALIDATION-CLOSED.json", {"complete": complete, "failure": failure,
                "source_stable": stable, "files": files, "actual_checks": checks,
                "actual_functional_score_calls": scored, "actual_rule_analyses": analyses,
                "selected_public_control_input_sha256": selected[0]["input_sha256"] if selected else None,
                "source_manifest": packages["source_manifest"], "wide_functional_budget_not_deadline_evidence": True,
                "real_compute_children_HTTP_worlds_tables_model_calls": 0,
                "new_online_or_formal_admission": False})
            assert complete, "真实验装未通过，原失败保留，不自动重试"
    print(json.dumps({"complete": True, "actual_checks": len(checks), "actual_functional_scores": scored}))


if __name__ == "__main__":
    asyncio.run(main())
