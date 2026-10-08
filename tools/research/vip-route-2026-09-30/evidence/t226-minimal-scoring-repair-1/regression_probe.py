"""在真实规则/共享图/受限执行器接缝复现三白评分缺陷；不连接平台。"""
from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t226-minimal-scoring-repair-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

import argparse
import hashlib
import json
from pathlib import Path
import time

from hangma_bot.hangma.engine import HangmaRules
from hangma_bot.hangma.interface import ValueAnalysisLimits
from hangma_bot.kernel.config import RuleConfig
from hangma_bot.kernel.observation import CompetitionContext
from hangma_bot.kernel.serialization import observation_from_json, window_key_from_json
from hangma_bot.policy.action_value_executor import ActionValueExecutor
from hangma_bot.policy.interface import DecisionRequest
from hangma_bot.policy.route_vip_heuristic import (
    VipRouteProjectionLimits, build_vip_route_scoring_view,
)

ROOT = _PROJECT_ROOT
FIXTURE = _project_file(_PROJECT_ROOT, ROOT / "tests/fixtures/vip_scoring_repair/mature_three_white.json")


def build_view():
    """从原公开观察重建完整类型化输入，隐藏世界与未来牌墙不参与。"""
    data = json.loads(FIXTURE.read_text())
    config = RuleConfig(**data["rule_config"])
    obs = observation_from_json(data["observation"])
    key = window_key_from_json(data["window_key"])
    analysis = HangmaRules(config).analyze(obs, route_limits=ValueAnalysisLimits(**data["route_limits"]))
    assert sorted(c.action_key for c in analysis.legal_candidates) == data["legal_action_keys"]
    request = DecisionRequest(obs, CompetitionContext("t200-mechanical", None, None, None, None, (), 0),
                              analysis, data["label"], key.trigger_seq, key, ())
    view = build_vip_route_scoring_view(request, config, limits=VipRouteProjectionLimits(**data["projection_limits"]))
    raw = json.dumps(view.candidate_view(), ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    assert hashlib.sha256(raw).hexdigest() == data["original_view_sha256"], "真实完整共享图与原故障输入不同"
    return view, data


def probe(source: Path):
    """真实双重复评分；检查用途可参与与同价继续动作能传递质量。"""
    start = time.monotonic()  # 持续时间为单调秒，不是官方动作截止时间。
    view, data = build_view()
    executor = ActionValueExecutor(source.read_text(), max_operations=4_800_000, max_local_collection_size=8192)
    results = [executor.score_vip_route(view) for _ in range(2)]
    assert results[0] == results[1], "双重复不一致"
    assert results[0].status == "SCORED"
    entries = {e.action_key: e for e in results[0].entries}
    assert sorted(entries) == data["legal_action_keys"]
    a, b = entries["discard:3b"], entries["discard:7b"]
    failures = []
    if dict(a.trace).get("target") is None:
        failures.append("PURPOSE_EXCLUDED_BY_FEES")
    qa, qb = dict(a.trace).get("repair_shadow"), dict(b.trace).get("repair_shadow")
    if qa is None or qb is None:
        failures.append("MEANINGFUL_SECONDARY_QUALITY_NOT_TRANSMITTED")
    elif qa != qb:
        if (qa > qb) != (a.score > b.score) or a.score == b.score:
            failures.append("DISTINCT_SECONDARY_QUALITY_LOST_IN_ROOT_RANKING")
    else:
        failures.append("REGRESSION_CASE_SECONDARY_QUALITY_STILL_FLAT")
    return {"complete": True, "repair_passed": not failures, "failures": failures,
            "score_calls": 2, "rule_calls": 1, "projection_calls": 1,
            "World": 0, "HTTP": 0, "API": 0,
            "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            "entries": [{"action_key": e.action_key, "score": e.score,
                         "score_hex": e.score.hex(), "trace": dict(e.trace)} for e in results[0].entries],
            "counted_operations": executor.last_operation_count,
            "elapsed_monotonic_seconds": time.monotonic() - start}


def main():
    """显式输入源码与新收据路径；退出1表示真实问题仍在，不自动重试。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    assert not args.out.exists(), "保留已有原件，不覆盖或暗中重跑"
    result = probe(args.source)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    print(json.dumps({k: result[k] for k in ("complete", "repair_passed", "failures", "score_calls", "rule_calls", "projection_calls", "counted_operations")}, ensure_ascii=False))
    return 0 if result["repair_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
