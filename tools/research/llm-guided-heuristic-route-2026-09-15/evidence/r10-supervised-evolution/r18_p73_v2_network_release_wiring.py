"""R18 P73：复核 v2 四模式发布身份、启动配置和 409 请求等价性。"""

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

import asyncio
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
from typing import Any


HERE = Path(__file__).resolve().parent
ROOT = _PROJECT_ROOT
for path in (_project_file(_PROJECT_ROOT, ROOT / "src"), _project_file(_PROJECT_ROOT, ROOT / "tests/unit/application"), HERE):
    sys.path.insert(0, str(path))

import r18_p70_integrated_positive_v2_registration as p70  # noqa: E402
from fakes import FakeTournamentSession  # noqa: E402
from hangma_bot.application.auto_match_runtime import AutoMatchSettings  # noqa: E402
from hangma_bot.bootstrap import (  # noqa: E402
    AVAILABLE_STRATEGIES,
    DEFAULT_STRATEGY,
    build_auto_match_runtime,
    build_research_policy,
    build_runtime,
    runtime_config_from_mapping,
)
from hangma_bot.hangma.interface import ValueAnalysisLimits  # noqa: E402
from hangma_bot.kernel.config import RuleConfig  # noqa: E402
from hangma_bot.policy.interface import DecisionBudget  # noqa: E402
from hangma_bot.policy.r18_integrated_positive_v2_release import (  # noqa: E402
    R18IntegratedPositiveV2ReleasePolicy,
    R18_INTEGRATED_POSITIVE_V2_ALLOWED_MODES,
    R18_INTEGRATED_POSITIVE_V2_EVIDENCE,
    R18_INTEGRATED_POSITIVE_V2_RELEASE_PACKAGE_ID,
    R18_INTEGRATED_POSITIVE_V2_RELEASE_STRATEGY,
    R18_INTEGRATED_POSITIVE_V2_RULES_SOURCE_HASH,
    R18_INTEGRATED_POSITIVE_V2_VALUE_ANALYSIS_SHA256,
)
from hangma_bot.simulation.artifacts import compute_rules_hash  # noqa: E402


OUT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p73-v2-network-release-wiring-01-20260923')
EVIDENCE_PATHS = {
    "p45_capability_merge": _project_file(_PROJECT_ROOT, HERE / "r18-p45-integrated-positive-parent-01-20260922/result.json"),
    "p46_fresh_table_safety": _project_file(_PROJECT_ROOT, HERE / "r18-p46-integrated-parent-table-safety-01-20260922/result.json"),
    "p55_white_value_route_repair": _project_file(_PROJECT_ROOT, HERE / "r18-p55-white-value-route-repair-01-20260923/result.json"),
    "p66b_candidate_preflight": _project_file(_PROJECT_ROOT, HERE / "r18-p66b-nonwhite-baotou-candidate-preflight-01-20260923/result.json"),
    "p67_blind_replication": _project_file(_PROJECT_ROOT, HERE / "r18-p67-nonwhite-baotou-blind-replication-01-20260923/result.json"),
    "p69_table_confirmation": _project_file(_PROJECT_ROOT, HERE / "r18-p69-nonwhite-baotou-table-confirmation-01-20260923/result.json"),
    "p70_registration": _project_file(_PROJECT_ROOT, HERE / "r18-p70-integrated-positive-v2-registration-01-20260923/result.json"),
    "p71_full_chain_preflight": _project_file(_PROJECT_ROOT, HERE / "r18-p71-integrated-positive-v2-full-chain-preflight-01-20260923/result.json"),
}
CONFIG_PATHS = {
    mode: _project_file(_PROJECT_ROOT, ROOT / "configs" / f"r18-integrated-positive-v2.{mode.replace('_', '-')}.example.json")
    for mode in R18_INTEGRATED_POSITIVE_V2_ALLOWED_MODES
}


def digest(path: Path) -> str:
    """返回文件原始字节的 SHA-256。"""

    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: Any) -> None:
    """按固定格式写出可复核的 JSON 证据。"""

    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n")


def load_script(name: str) -> Any:
    """加载生产启动器的配置解析函数，不启动网络。"""

    path = _project_file(_PROJECT_ROOT, ROOT / "scripts" / name)
    spec = importlib.util.spec_from_file_location("r18_p73_" + path.stem, path)
    if spec is None or spec.loader is None:
        raise RuntimeError("无法加载启动器 " + name)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def config_check(mode: str, temp_root: Path) -> dict[str, Any]:
    """由生产配置解析器与组合根验证示例配置的身份和范围。"""

    source = CONFIG_PATHS[mode]
    data = json.loads(source.read_text())
    if mode == "test_room":
        room_script = load_script("run_test_room.py")
        data["identities"] = [
            {"slot": row["slot"], "token": "fixture-not-a-real-token"}
            for row in data["identities"]
        ]
        path = temp_root / "room.json"
        write_json(path, data)
        room = room_script.load_room_config(path)
        configs = [
            runtime_config_from_mapping(
                room_script.child_config_mapping(room, identity),
                environ={room_script.TOKEN_ENV_VAR: "fixture-not-a-real-token"},
            )
            for identity in room.identities
        ]
        if len(configs) != 4:
            raise ValueError("测试房必须有四个身份")
    elif mode == "auto_match":
        match_script = load_script("run_auto_match.py")
        path = temp_root / "match.json"
        write_json(path, data)
        config, settings = match_script.load_config(
            path, environ={"HM_AUTO_MATCH_TOKEN": "fixture-not-a-real-token"}
        )
        if not isinstance(settings, AutoMatchSettings):
            raise ValueError("自由赛设置解析失败")
        configs = [config]
    else:
        data.pop("token_env")
        data["token"] = "fixture-not-a-real-token"
        configs = [runtime_config_from_mapping(data)]
    for config in configs:
        session = FakeTournamentSession(bootstrap=None)
        assembled = (
            build_auto_match_runtime(
                config, AutoMatchSettings(), session_factory=lambda: session
            )
            if mode == "auto_match"
            else build_runtime(config, session_factory=lambda: session)
        )
        if not isinstance(assembled.policy, R18IntegratedPositiveV2ReleasePolicy):
            raise ValueError("实际策略类型不符：" + mode)
        if assembled.runtime._value_limits != ValueAnalysisLimits():
            raise ValueError("条件分值分析配置不符：" + mode)
        metadata = assembled.runtime._manifest_extra["policy_release"]
        if metadata["release_package_id"] != R18_INTEGRATED_POSITIVE_V2_RELEASE_PACKAGE_ID:
            raise ValueError("审计发布包身份不符：" + mode)
        assembled.runtime._rules_factory(RuleConfig("hangma-mvp-v10-public-counts", 1, False))
        try:
            assembled.runtime._rules_factory(RuleConfig("hangma-mvp-v10-public-counts", 2, False))
        except ValueError:
            pass
        else:
            raise ValueError("规则范围越界未拒绝：" + mode)
    return {
        "mode": mode,
        "config_sha256": digest(source),
        "identities": len(configs),
        "package_id": R18_INTEGRATED_POSITIVE_V2_RELEASE_PACKAGE_ID,
        "rule_scope_rejected": True,
        "network_calls": 0,
    }


async def replay() -> int:
    """用正式策略接缝核对冻结发布策略与离线研究父代的完整计划。"""

    release = R18IntegratedPositiveV2ReleasePolicy(
        rules_source_hash=R18_INTEGRATED_POSITIVE_V2_RULES_SOURCE_HASH,
        value_analysis_sha256=R18_INTEGRATED_POSITIVE_V2_VALUE_ANALYSIS_SHA256,
    )
    research = build_research_policy("action_value:r18_integrated_positive_v2")
    budget = DecisionBudget(1_000_000_000.0, 1_000_000_000.0, 1_000_000_000.0)
    count = 0
    for label, request in p70.current_requests():
        actual = await release.choose(request, budget)
        expected = await research.choose(request, budget)
        if actual != expected:
            raise ValueError("冻结策略与研究父代完整计划不等价：" + label)
        if any("action_value_failed" in reason for reason in actual.degraded_reasons):
            raise ValueError("冻结策略发生评分失败：" + label)
        count += 1
    return count


def run() -> None:
    """生成不可覆盖的四模式接线审核证据。"""

    if OUT.exists():
        raise SystemExit("P73 证据目录已存在；拒绝覆盖")
    checks = {
        "all_evidence_hashes_match": all(
            digest(path) == R18_INTEGRATED_POSITIVE_V2_EVIDENCE[name]
            for name, path in EVIDENCE_PATHS.items()
        ),
        "p69_passed": json.loads(EVIDENCE_PATHS["p69_table_confirmation"].read_text())[
            "status"
        ] == "PASS_P69_NONWEALTH_BAOTOU_TABLE_CONFIRMATION",
        "p71_passed": json.loads(EVIDENCE_PATHS["p71_full_chain_preflight"].read_text())[
            "status"
        ] == "PASS_P71_INTEGRATED_POSITIVE_V2_FULL_CHAIN_PREFLIGHT",
        "rules_hash_matches": compute_rules_hash(ROOT) == R18_INTEGRATED_POSITIVE_V2_RULES_SOURCE_HASH,
        "strategy_registered": R18_INTEGRATED_POSITIVE_V2_RELEASE_STRATEGY in AVAILABLE_STRATEGIES,
        "not_default": DEFAULT_STRATEGY != R18_INTEGRATED_POSITIVE_V2_RELEASE_STRATEGY,
        "all_four_modes_approved": set(R18_INTEGRATED_POSITIVE_V2_ALLOWED_MODES) == {
            "test_room", "test_tournament", "auto_match", "official_tournament"
        },
    }
    if not all(checks.values()):
        raise ValueError("P73 身份证据不一致：" + repr(checks))
    with tempfile.TemporaryDirectory(prefix="r18-p73-") as temp:
        configs = [
            config_check(mode, Path(temp)) for mode in R18_INTEGRATED_POSITIVE_V2_ALLOWED_MODES
        ]
    count = asyncio.run(replay())
    if count != 409:
        raise ValueError("累计冻结请求数应为409")
    OUT.mkdir(parents=True)
    result = {
        "schema": "r18-p73-v2-network-release-wiring-result/1",
        "status": "PASS_P73_V2_FOUR_MODE_RELEASE_WIRING",
        "strategy": R18_INTEGRATED_POSITIVE_V2_RELEASE_STRATEGY,
        "release_package_id": R18_INTEGRATED_POSITIVE_V2_RELEASE_PACKAGE_ID,
        "checks": checks,
        "modes": configs,
        "exact_plan_replay_requests": count,
        "network_calls": 0,
        "next": "使用各模式有效身份启动；正式赛事运行结果仍需单独审核",
    }
    write_json(_project_file(_PROJECT_ROOT, OUT / "result.json"), result)
    write_json(_project_file(_PROJECT_ROOT, OUT / "release-package.json"), dict(R18IntegratedPositiveV2ReleasePolicy(
        rules_source_hash=R18_INTEGRATED_POSITIVE_V2_RULES_SOURCE_HASH,
        value_analysis_sha256=R18_INTEGRATED_POSITIVE_V2_VALUE_ANALYSIS_SHA256,
    ).release_metadata))
    write_json(_project_file(_PROJECT_ROOT, OUT / "manifest.json"), {
        "schema": "r18-p73-v2-network-release-wiring-manifest/1",
        "script_sha256": digest(Path(__file__)),
        "result_sha256": digest(_project_file(_PROJECT_ROOT, OUT / "result.json")),
        "release_package_sha256": digest(_project_file(_PROJECT_ROOT, OUT / "release-package.json")),
        "evidence_sha256": {name: digest(path) for name, path in EVIDENCE_PATHS.items()},
        "network_calls": 0,
    })
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    run()
