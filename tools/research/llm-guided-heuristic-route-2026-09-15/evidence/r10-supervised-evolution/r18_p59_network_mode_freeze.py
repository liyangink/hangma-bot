"""R18 P59：生成并实际装配测试房/测试赛事专用冻结包。"""

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

import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import time
from typing import Any


HERE = Path(__file__).resolve().parent
ROUTE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15')
ROOT = _PROJECT_ROOT
for path in (_project_file(_PROJECT_ROOT, ROOT / "src"), ROOT):
    sys.path.insert(0, str(path))

from hangma_bot.bootstrap import build_runtime, runtime_config_from_mapping  # noqa: E402
from hangma_bot.policy.r18_integrated_positive_v1_release import (  # noqa: E402
    R18_INTEGRATED_POSITIVE_V1_CANDIDATE_ID,
    R18_INTEGRATED_POSITIVE_V1_RELEASE_PACKAGE_ID,
    R18_INTEGRATED_POSITIVE_V1_RELEASE_STRATEGY,
    R18_INTEGRATED_POSITIVE_V1_RULES_SOURCE_HASH,
)


OUT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p59-network-mode-freeze-01-20260923')
CONFIGS = {
    "test_room": _project_file(_PROJECT_ROOT, ROOT / "configs/r18-integrated-positive-v1.test-room.example.json"),
    "test_tournament": _project_file(_PROJECT_ROOT, ROOT
    / "configs/r18-integrated-positive-v1.test-tournament.example.json"),
}
STATUS_EVIDENCE = {
    "p57_release_rebind": _project_file(_PROJECT_ROOT, HERE
    / "r18-p57-network-release-rebind-01-20260923/result.json"),
    "p58_successor_rejected": _project_file(_PROJECT_ROOT, HERE
    / "r18-p58-guarded-successor-confirmation-01-20260923/result.json"),
}
STATUS_SNAPSHOT = "current-status-snapshot.json"


def file_digest(path: Path) -> str:
    """返回文件字节 SHA-256。"""

    return hashlib.sha256(path.read_bytes()).hexdigest()


def value_digest(value: Any) -> str:
    """返回规范 JSON SHA-256；用于冻结包身份。"""

    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def write_json(path: Path, value: Any) -> None:
    """以稳定字段顺序写入 UTF-8 JSON。"""

    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def load_test_room_module() -> Any:
    """加载正式测试房启动器，不复制其配置派生规则。"""

    path = _project_file(_PROJECT_ROOT, ROOT / "scripts/run_test_room.py")
    spec = importlib.util.spec_from_file_location("r18_p59_run_test_room", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("无法加载测试房启动器")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def assert_release_manifest(assembled: Any, mode: str) -> dict[str, Any]:
    """核对组合根产出的发布身份；只读装配结果，不建立网络连接。"""

    metadata = dict(assembled.runtime._manifest_extra["policy_release"])
    if metadata.get("release_package_id") != R18_INTEGRATED_POSITIVE_V1_RELEASE_PACKAGE_ID:
        raise ValueError(mode + " 未装配当前批准发布包")
    if metadata.get("candidate_id") != R18_INTEGRATED_POSITIVE_V1_CANDIDATE_ID:
        raise ValueError(mode + " 候选身份不符")
    if metadata.get("rules_source_hash") != R18_INTEGRATED_POSITIVE_V1_RULES_SOURCE_HASH:
        raise ValueError(mode + " 规则源摘要不符")
    if mode not in metadata.get("allowed_modes", []):
        raise ValueError(mode + " 不在发布包允许范围")
    return metadata


def exercise_configs(temp_root: Path) -> dict[str, Any]:
    """通过正式解析器和组合根使用两份模板；Token/赛事 ID 只用本地替身。"""

    room_module = load_test_room_module()
    room_data = json.loads(CONFIGS["test_room"].read_text())
    room_data["expected_tournament_id"] = "t-r18-p59-fixture"
    room_data["audit_root"] = str(temp_root / "room-audit")
    room_data["identities"] = [
        {"slot": slot, "token": "fixture-token-" + slot}
        for slot in ("qinglong", "baihu", "zhuque", "xuanwu")
    ]
    room_path = temp_root / "test-room.json"
    write_json(room_path, room_data)
    room = room_module.load_room_config(room_path)
    room_checks = []
    for identity in room.identities:
        child = room_module.child_config_mapping(room, identity)
        config = runtime_config_from_mapping(
            child,
            environ={room_module.TOKEN_ENV_VAR: "fixture-child-token"},
        )
        assembled = build_runtime(config, session_factory=lambda: object())
        metadata = assert_release_manifest(assembled, "test_room")
        room_checks.append(
            {
                "slot": identity.slot,
                "strategy": config.strategy,
                "expected_release_exact": config.expected_policy_release_id
                == R18_INTEGRATED_POSITIVE_V1_RELEASE_PACKAGE_ID,
                "manifest_release_exact": metadata["release_package_id"]
                == config.expected_policy_release_id,
            }
        )

    tournament_data = json.loads(CONFIGS["test_tournament"].read_text())
    tournament_data["expected_tournament_id"] = "t-r18-p59-fixture"
    tournament_data["audit_root"] = str(temp_root / "tournament-audit")
    config = runtime_config_from_mapping(
        tournament_data,
        environ={"HM_PARTICIPANT_TOKEN": "fixture-tournament-token"},
    )
    assembled = build_runtime(config, session_factory=lambda: object())
    metadata = assert_release_manifest(assembled, "test_tournament")
    return {
        "test_room": {
            "identities": room_checks,
            "all_four_assembled": len(room_checks) == 4
            and all(
                row["expected_release_exact"] and row["manifest_release_exact"]
                for row in room_checks
            ),
        },
        "test_tournament": {
            "strategy": config.strategy,
            "expected_release_exact": config.expected_policy_release_id
            == R18_INTEGRATED_POSITIVE_V1_RELEASE_PACKAGE_ID,
            "manifest_release_exact": metadata["release_package_id"]
            == config.expected_policy_release_id,
        },
    }


def package_payload(mode: str) -> dict[str, Any]:
    """构造一个模式专用、绑定当前状态材料的冻结载荷。"""

    entrypoint = (
        _project_file(_PROJECT_ROOT, ROOT / "scripts/run_test_room.py")
        if mode == "test_room"
        else _project_file(_PROJECT_ROOT, ROOT / "scripts/run_participant.py")
    )
    return {
        "schema": "r18-network-mode-freeze/1",
        "mode": mode,
        "strategy": R18_INTEGRATED_POSITIVE_V1_RELEASE_STRATEGY,
        "release_package_id": R18_INTEGRATED_POSITIVE_V1_RELEASE_PACKAGE_ID,
        "candidate_id": R18_INTEGRATED_POSITIVE_V1_CANDIDATE_ID,
        "rules_source_hash": R18_INTEGRATED_POSITIVE_V1_RULES_SOURCE_HASH,
        "runtime_config_template": {
            "path": str(CONFIGS[mode].relative_to(ROOT)),
            "sha256": file_digest(CONFIGS[mode]),
            "required_binding_field": "expected_policy_release_id",
        },
        "entrypoint": {
            "path": str(entrypoint.relative_to(ROOT)),
            "sha256": file_digest(entrypoint),
        },
        "implementation": {
            "bootstrap_sha256": file_digest(_project_file(_PROJECT_ROOT, ROOT / "src/hangma_bot/bootstrap.py")),
            "release_module_sha256": file_digest(
                _project_file(_PROJECT_ROOT, ROOT / "src/hangma_bot/policy/r18_integrated_positive_v1_release.py")
            ),
        },
        "current_status_evidence": {
            name: {
                "path": str(path.relative_to(ROOT)),
                "sha256": file_digest(path),
            }
            for name, path in STATUS_EVIDENCE.items()
        },
        "current_status_snapshot": {
            "path": STATUS_SNAPSHOT,
            "sha256": file_digest(_project_file(_PROJECT_ROOT, OUT / STATUS_SNAPSHOT)),
        },
        "authorization": {
            "approved_on": "2026-09-23",
            "source": "当前项目监督会话中的仓库所有者明确授权",
            "scope": mode,
        },
        "official_tournament_allowed": False,
        "production_default": False,
    }


def run() -> None:
    """生成不可覆盖证据，并确保两个冻结配置已经真实走过装配路径。"""

    if OUT.exists():
        raise SystemExit("P59 目录已存在；拒绝覆盖")
    with tempfile.TemporaryDirectory(prefix="r18-p59-") as directory:
        checks = exercise_configs(Path(directory))
    if not checks["test_room"]["all_four_assembled"]:
        raise ValueError("测试房四身份未全部装配当前包")
    tournament = checks["test_tournament"]
    if not tournament["expected_release_exact"] or not tournament["manifest_release_exact"]:
        raise ValueError("测试赛事未装配当前包")

    OUT.mkdir(parents=True)
    p58 = json.loads(STATUS_EVIDENCE["p58_successor_rejected"].read_text())
    auto_match_readme = _project_file(_PROJECT_ROOT, ROOT / "review/r18-auto-match-2026-09-23/README.md")
    search_space = _project_file(_PROJECT_ROOT, ROUTE / "SEARCH-SPACE-REDESIGN-2026-09-16.md")
    write_json(
        _project_file(_PROJECT_ROOT, OUT / STATUS_SNAPSHOT),
        {
            "schema": "r18-p59-current-status-snapshot/1",
            "captured_on": "2026-09-23",
            "active_research_parent": "r18_integrated_positive_v1 (P47)",
            "release_package_id": R18_INTEGRATED_POSITIVE_V1_RELEASE_PACKAGE_ID,
            "latest_successor_confirmation": {
                "status": p58["status"],
                "selection_eligible": p58["selection_eligible"],
                "stage_score_delta_mean": p58["overall"]["stage_score_delta_mean"],
                "source_sha256": file_digest(
                    STATUS_EVIDENCE["p58_successor_rejected"]
                ),
            },
            "real_environment_review_at_capture": {
                "source_path": str(auto_match_readme.relative_to(ROOT)),
                "source_sha256": file_digest(auto_match_readme),
            },
            "evolution_contract_at_capture": {
                "source_path": str(search_space.relative_to(ROOT)),
                "source_sha256": file_digest(search_space),
            },
            "interpretation": (
                "P58 后继候选已拒绝，P47/R18 仍是活动父代；本快照只冻结生成时状态，"
                "后续搜索与真实房证据可以继续追加，不回写本包。"
            ),
        },
    )
    packages = {}
    for mode in ("test_room", "test_tournament"):
        payload = package_payload(mode)
        payload["mode_freeze_package_id"] = value_digest(payload)
        write_json(_project_file(_PROJECT_ROOT, OUT / (mode + "-freeze.json")), payload)
        packages[mode] = payload["mode_freeze_package_id"]

    result = {
        "schema": "r18-p59-network-mode-freeze-result/1",
        "status": "PASS_P59_NETWORK_MODE_FREEZE",
        "release_package_id": R18_INTEGRATED_POSITIVE_V1_RELEASE_PACKAGE_ID,
        "mode_freeze_package_ids": packages,
        "offline_assembly_checks": checks,
        "network_calls": 0,
        "official_platform_calls": 0,
        "model_calls": 0,
        "release_scope": ["test_room", "test_tournament"],
        "official_tournament_allowed": False,
        "production_default": False,
        "next": "由获批测试身份替换模板占位赛事 ID/Token 后运行；结果进入独立测试房与测试赛事证据目录",
    }
    write_json(_project_file(_PROJECT_ROOT, OUT / "result.json"), result)
    write_json(
        _project_file(_PROJECT_ROOT, OUT / "manifest.json"),
        {
            "schema": "r18-p59-network-mode-freeze-manifest/1",
            "created_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "script_sha256": file_digest(Path(__file__)),
            "test_room_freeze_sha256": file_digest(_project_file(_PROJECT_ROOT, OUT / "test_room-freeze.json")),
            "test_tournament_freeze_sha256": file_digest(
                _project_file(_PROJECT_ROOT, OUT / "test_tournament-freeze.json")
            ),
            "result_sha256": file_digest(_project_file(_PROJECT_ROOT, OUT / "result.json")),
            "current_status_snapshot_sha256": file_digest(_project_file(_PROJECT_ROOT, OUT / STATUS_SNAPSHOT)),
        },
    )
    (_project_file(_PROJECT_ROOT, OUT / "README.md")).write_text(
        "# R18 P59 测试模式冻结包\n\n"
        "结论：`r18_integrated_positive_v1` 的测试房四身份和测试赛事单身份配置，"
        "均已通过正式配置解析器与组合根离线装配，并绑定当前发布包 `"
        + R18_INTEGRATED_POSITIVE_V1_RELEASE_PACKAGE_ID
        + "`。配置缺少或错填 `expected_policy_release_id` 会在联网前拒绝。\n\n"
        "本证据没有调用官方平台，不冒充真实测试房或测试赛事结果；实际成绩与协议"
        "证据须由对应入口使用获批 Token 运行后另行归档。正式赛事和默认策略仍关闭。\n",
        encoding="utf-8",
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    run()
