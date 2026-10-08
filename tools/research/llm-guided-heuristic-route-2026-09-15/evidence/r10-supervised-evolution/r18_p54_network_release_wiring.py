"""R18 P54：核验人工批准冻结包的真实入口身份与 377 请求等价性。"""

from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution'

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
import math
from pathlib import Path
import platform
import sys
import time
from typing import Any, Iterable


HERE = Path(__file__).resolve().parent
ROUTE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15')
ROOT = _PROJECT_ROOT
for path in (_project_file(_PROJECT_ROOT, ROOT / "src"), HERE):
    sys.path.insert(0, str(path))

import r18_p47_integrated_parent_registration as p47  # noqa: E402
from hangma_bot.bootstrap import (  # noqa: E402
    AVAILABLE_STRATEGIES,
    DEFAULT_STRATEGY,
    build_research_policy,
    runtime_config_from_mapping,
)
from hangma_bot.policy.interface import DecisionBudget  # noqa: E402
from hangma_bot.policy.r18_integrated_positive_v1_release import (  # noqa: E402
    R18IntegratedPositiveV1ReleasePolicy,
    R18_INTEGRATED_POSITIVE_V1_ALLOWED_MODES,
    R18_INTEGRATED_POSITIVE_V1_CANDIDATE_ID,
    R18_INTEGRATED_POSITIVE_V1_EVIDENCE,
    R18_INTEGRATED_POSITIVE_V1_RELEASE_PACKAGE_ID,
    R18_INTEGRATED_POSITIVE_V1_RELEASE_STRATEGY,
)


OUT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p54-network-release-wiring-01-20260923')
P49 = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p49-integrated-human-release-review-01-20260922/review-package.json')
EVIDENCE_PATHS = {
    "p45_capability_merge": _project_file(_PROJECT_ROOT, HERE / "r18-p45-integrated-positive-parent-01-20260922/result.json"),
    "p46_fresh_table_safety": _project_file(_PROJECT_ROOT, HERE / "r18-p46-integrated-parent-table-safety-01-20260922/result.json"),
    "p47_package_registration": _project_file(_PROJECT_ROOT, HERE / "r18-p47-integrated-parent-registration-01-20260922/result.json"),
    "p48_full_chain_preflight": _project_file(_PROJECT_ROOT, HERE / "r18-p48-integrated-full-chain-preflight-01-20260922/result.json"),
}


def digest(path: Path) -> str:
    """返回文件字节 SHA-256。"""

    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: Any) -> None:
    """稳定写入 UTF-8 JSON。"""

    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def percentile(values: Iterable[float], q: float) -> float:
    """用最近秩计算诊断分位数。"""

    ordered = sorted(values)
    if not ordered:
        raise ValueError("分位数输入不能为空")
    index = max(0, min(len(ordered) - 1, math.ceil(q * len(ordered)) - 1))
    return ordered[index]


def config(mode: str) -> dict[str, Any]:
    """构造无真实凭证的组合根校验输入。"""

    return {
        "mode": mode,
        "token_kind": "test" if mode != "auto_match" else "official",
        "token": "fixture-not-a-real-token",
        "base_url": "https://platform.invalid",
        "expected_tournament_id": None if mode == "auto_match" else "t-r18-p54",
        "known_guide_version": 34,
        "audit_root": "/tmp/r18-p54-audit",
        "strategy": R18_INTEGRATED_POSITIVE_V1_RELEASE_STRATEGY,
    }


async def replay() -> tuple[list[dict[str, Any]], list[float]]:
    """逐请求核对冻结发布策略与 P47 研究装配的完整计划。"""

    release = R18IntegratedPositiveV1ReleasePolicy()
    reference = build_research_policy("action_value:r18_integrated_positive_v1")
    budget = DecisionBudget(1_000_000_000.0, 1_000_000_000.0, 1_000_000_000.0)
    rows: list[dict[str, Any]] = []
    latencies: list[float] = []
    for label, request in p47.current_requests():
        expected = await reference.choose(request, budget)
        started = time.perf_counter_ns()
        actual = await release.choose(request, budget)
        elapsed_ms = (time.perf_counter_ns() - started) / 1_000_000.0
        if actual != expected:
            raise ValueError("发布包与 P47 完整计划不等价：" + label)
        if any("action_value_failed" in reason for reason in actual.degraded_reasons):
            raise ValueError("发布包发生 action_value 降级：" + label)
        rows.append(
            {
                "label": label,
                "candidate_count": len(actual.candidates),
                "top_action": None if not actual.candidates else actual.candidates[0].action_key,
                "elapsed_ms": elapsed_ms,
                "exact_plan_equal": True,
            }
        )
        latencies.append(elapsed_ms)
    return rows, latencies


def run() -> None:
    """生成不可覆盖的 P54 接线验收包。"""

    if OUT.exists():
        raise SystemExit("P54 目录已存在；拒绝覆盖")
    evidence_checks = {
        name: digest(path) == R18_INTEGRATED_POSITIVE_V1_EVIDENCE[name]
        for name, path in EVIDENCE_PATHS.items()
    }
    mode_checks = {
        mode: runtime_config_from_mapping(config(mode)).mode.value == mode
        for mode in R18_INTEGRATED_POSITIVE_V1_ALLOWED_MODES
    }
    official_rejected = False
    try:
        runtime_config_from_mapping(
            {
                **config("test_tournament"),
                "mode": "official_tournament",
                "token_kind": "official",
            }
        )
    except ValueError as exc:
        official_rejected = "只获批测试房、测试赛事和自由赛" in str(exc)
    release = R18IntegratedPositiveV1ReleasePolicy()
    metadata = dict(release.release_metadata)
    identity_checks = {
        "strategy_registered": R18_INTEGRATED_POSITIVE_V1_RELEASE_STRATEGY in AVAILABLE_STRATEGIES,
        "not_default": DEFAULT_STRATEGY != R18_INTEGRATED_POSITIVE_V1_RELEASE_STRATEGY,
        "package_id_exact": metadata.get("release_package_id")
        == R18_INTEGRATED_POSITIVE_V1_RELEASE_PACKAGE_ID,
        "candidate_id_exact": metadata.get("candidate_id")
        == R18_INTEGRATED_POSITIVE_V1_CANDIDATE_ID,
        "allowed_modes_exact": tuple(metadata.get("allowed_modes", ()))
        == R18_INTEGRATED_POSITIVE_V1_ALLOWED_MODES,
        "official_tournament_rejected": official_rejected,
        "production_default_false": metadata.get("production_default") is False,
    }
    if not all(evidence_checks.values()) or not all(mode_checks.values()) or not all(
        identity_checks.values()
    ):
        raise ValueError(
            "P54 身份或范围检查失败："
            + repr(
                {
                    "evidence": evidence_checks,
                    "modes": mode_checks,
                    "identity": identity_checks,
                }
            )
        )

    rows, latencies = asyncio.run(replay())
    if len(rows) != 377:
        raise ValueError("P47 冻结请求数漂移：" + str(len(rows)))

    OUT.mkdir(parents=True)
    approval = {
        "schema": "r18-p54-human-approval/1",
        "approved_on": "2026-09-23",
        "approved_by": "repository_owner",
        "authorization_source": "当前项目监督会话中的用户明确授权",
        "candidate": {
            "strategy": R18_INTEGRATED_POSITIVE_V1_RELEASE_STRATEGY,
            "candidate_id": R18_INTEGRATED_POSITIVE_V1_CANDIDATE_ID,
            "candidate_source_sha256": metadata["candidate_source_sha256"],
            "release_package_id": R18_INTEGRATED_POSITIVE_V1_RELEASE_PACKAGE_ID,
        },
        "allow": ["test_room", "test_tournament", "auto_match"],
        "deny": ["official_tournament", "production_default"],
        "git_publish": {
            "remote": "git@github.com:liyangink/hangma-bot.git",
            "branch": "main",
            "scope": "当前 main 的候选源码、评测反馈、完整桌/全链证据和审核材料",
        },
        "p49_review_package": {
            "path": str(P49.relative_to(ROOT)),
            "sha256": digest(P49),
        },
    }
    result = {
        "schema": "r18-p54-network-release-wiring-result/1",
        "status": "PASS_P54_NETWORK_RELEASE_WIRING",
        "release_package_id": R18_INTEGRATED_POSITIVE_V1_RELEASE_PACKAGE_ID,
        "candidate_id": R18_INTEGRATED_POSITIVE_V1_CANDIDATE_ID,
        "allowed_modes": list(R18_INTEGRATED_POSITIVE_V1_ALLOWED_MODES),
        "official_tournament_allowed": False,
        "production_default": False,
        "checks": {
            "evidence_sha256": evidence_checks,
            "mode_config": mode_checks,
            "identity": identity_checks,
        },
        "choose_replay": {
            "requests": len(rows),
            "all_exact_plan_equal": True,
            "action_value_failures": 0,
            "latency_ms": {
                "p50": percentile(latencies, 0.50),
                "p95": percentile(latencies, 0.95),
                "p99": percentile(latencies, 0.99),
                "max": max(latencies),
            },
        },
        "release_scope": "test_room + test_tournament + auto_match",
        "release_eligible": False,
        "next": "收集测试房、官方测试赛事和自由赛证据后再审正式赛事准入",
    }
    write_json(_project_file(_PROJECT_ROOT, OUT / "approval.json"), approval)
    write_json(_project_file(_PROJECT_ROOT, OUT / "choose-replay.json"), rows)
    write_json(_project_file(_PROJECT_ROOT, OUT / "result.json"), result)
    write_json(
        _project_file(_PROJECT_ROOT, OUT / "manifest.json"),
        {
            "schema": "r18-p54-network-release-wiring-manifest/1",
            "created_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "script_sha256": digest(Path(__file__)),
            "release_module_sha256": digest(
                _project_file(_PROJECT_ROOT, ROOT / "src/hangma_bot/policy/r18_integrated_positive_v1_release.py")
            ),
            "bootstrap_sha256": digest(_project_file(_PROJECT_ROOT, ROOT / "src/hangma_bot/bootstrap.py")),
            "approval_sha256": digest(_project_file(_PROJECT_ROOT, OUT / "approval.json")),
            "result_sha256": digest(_project_file(_PROJECT_ROOT, OUT / "result.json")),
            "choose_replay_sha256": digest(_project_file(_PROJECT_ROOT, OUT / "choose-replay.json")),
            "platform": {
                "python": platform.python_version(),
                "implementation": platform.python_implementation(),
                "machine": platform.machine(),
                "system": platform.system(),
            },
            "network_calls": 0,
            "model_calls": 0,
            "official_platform_calls": 0,
        },
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("run",))
    globals()[parser.parse_args().operation]()
