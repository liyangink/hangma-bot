"""R18 P71：第二版累计能力候选的全链并发、截止、重规划与降级预检。"""

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
from pathlib import Path
import platform
import sys
import time
from types import SimpleNamespace
from typing import Any


HERE = Path(__file__).resolve().parent
ROUTE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15')
ROOT = _PROJECT_ROOT
for path in (_project_file(_PROJECT_ROOT, ROOT / "src"), _project_file(_PROJECT_ROOT, ROUTE / "tools"), HERE):
    sys.path.insert(0, str(path))

import confirmation_execution_identity as guard  # noqa: E402
import r18_p41_full_chain_release_preflight as p41  # noqa: E402
import r18_p70_integrated_positive_v2_registration as p70  # noqa: E402
from hangma_bot.policy.research_candidates import (  # noqa: E402
    R18_INTEGRATED_POSITIVE_V2_SHA256,
)


OUT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p71-integrated-positive-v2-full-chain-preflight-01-20260923')
P69 = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p69-nonwhite-baotou-table-confirmation-01-20260923/result.json')
P70 = p70.OUT / "result.json"
STRATEGY = "action_value:r18_integrated_positive_v2"


def digest(path: Path) -> str:
    """返回文件字节 SHA-256。"""

    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: Any) -> None:
    """稳定写入 UTF-8 JSON。"""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def configure() -> None:
    """把已验证的 P41 全链探针绑定到累计候选及扩展请求集。"""

    p41.STRATEGY = STRATEGY
    p41.R18_TWO_WEALTH_BAOTOU_V1_SHA256 = R18_INTEGRATED_POSITIVE_V2_SHA256
    # P41 只需可重放请求入口。使用独立代理绑定 P70 的 409 个
    # 累计请求，避免改写旧模块全局状态造成递归或身份漂移。
    p41.p38 = SimpleNamespace(current_requests=p70.current_requests)


def run() -> None:
    """核对前置身份后执行完整应用动作链。"""

    if OUT.exists():
        raise SystemExit("P71 目录已存在；拒绝覆盖")
    p69 = json.loads(P69.read_text(encoding="utf-8"))
    p70_result = json.loads(P70.read_text(encoding="utf-8"))
    if p69.get("status") != "PASS_P69_NONWEALTH_BAOTOU_TABLE_CONFIRMATION":
        raise ValueError("P69 未通过")
    if p70_result.get("status") != "PASS_P70_INTEGRATED_POSITIVE_V2_REGISTRATION":
        raise ValueError("P70 未通过")
    if p69.get("candidate_sha256") != R18_INTEGRATED_POSITIVE_V2_SHA256:
        raise ValueError("P69 候选身份漂移")
    if p70_result.get("candidate_sha256") != R18_INTEGRATED_POSITIVE_V2_SHA256:
        raise ValueError("P70 候选身份漂移")

    configure()
    raw = asyncio.run(p41.execute())
    passed = all(raw["gate_checks"].values())
    result = dict(raw)
    result.update({
        "schema": "r18-p71-integrated-positive-v2-full-chain-preflight-result/1",
        "status": (
            "PASS_P71_INTEGRATED_POSITIVE_V2_FULL_CHAIN_PREFLIGHT"
            if passed else "FAIL_P71_INTEGRATED_POSITIVE_V2_FULL_CHAIN_PREFLIGHT"
        ),
        "candidate_sha256": R18_INTEGRATED_POSITIVE_V2_SHA256,
        "requests_source": (
            "P70冻结的409个请求：P47累计377个与P63非财神建爆头"
            "开发/复验32个；每次重新执行HangmaRules.analyze"
        ),
        "confirmation_eligible": passed,
        "release_eligible": False,
        "next": (
            "允许生成v2只读测试房/测试赛事审核包；真实网络注册仍关闭"
            if passed else "保持候选离线，按失败探针修复后使用新批次复验"
        ),
    })
    if not passed:
        raise RuntimeError(json.dumps(result["gate_checks"], ensure_ascii=False))
    OUT.mkdir(parents=True)
    write_json(_project_file(_PROJECT_ROOT, OUT / "result.json"), result)
    tracked = [Path(__file__), Path(p41.__file__), Path(p70.__file__), P69, P70]
    write_json(_project_file(_PROJECT_ROOT, OUT / "manifest.json"), {
        "schema": "r18-p71-integrated-positive-v2-full-chain-preflight-manifest/1",
        "created_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "runtime": guard.capture(source_paths=tracked),
        "script_sha256": digest(Path(__file__)),
        "p41_probe_implementation_sha256": digest(Path(p41.__file__)),
        "p69_sha256": digest(P69),
        "p70_sha256": digest(P70),
        "result_sha256": digest(_project_file(_PROJECT_ROOT, OUT / "result.json")),
        "platform": {
            "python": platform.python_version(),
            "implementation": platform.python_implementation(),
            "machine": platform.machine(),
            "system": platform.system(),
        },
        "network_calls": 0,
        "model_calls": 0,
        "release_eligible": False,
    })
    print(json.dumps(
        {key: value for key, value in result.items() if key != "rows"},
        ensure_ascii=False,
        indent=2,
    ))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("run",))
    globals()[parser.parse_args().operation]()
