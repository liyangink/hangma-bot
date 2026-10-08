#!/usr/bin/env python3
"""用当前判据重判既有门禁跑，写独立的 reevaluated.json（**不改写 gate.json**）。

用途：判据升级（如 round 15 新增符号检验）后，不必重跑模拟即可得到新判词。
原始 gate.json 与 freeze.json 保持原样，历史不被改写；新判词另存一份并记录来源摘要。

用法：
  reevaluate_gate.py --dir review/.../gate-tiera-highpower
"""
from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/heuristic-balanced-2026-09-10'

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

import gate_candidate as gate
from hangma_bot.offline.evaluation_results import read_results_jsonl


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dir", required=True)
    args = parser.parse_args()
    directory = Path(args.dir)
    freeze = json.loads((directory / "freeze.json").read_text(encoding="utf-8"))
    if freeze.get("expect_identical"):
        # 零差异模式用的是另一套判据（identical_arms），本工具只覆盖"强度"模式；
        # 混用会让 identical_arms 检查静默消失，宁可显式拒绝。
        raise SystemExit("该门禁是 --expect-identical 零差异模式，reevaluate 不支持：" + str(directory))
    results = read_results_jsonl(directory / "results.jsonl")
    verdict = gate.evaluate(results, freeze["baseline"], freeze["candidate"],
                            freeze.get("expect_identical", False))
    checks = dict(
        reliability_zero=all(verdict["runtime_counts"][name] == 0
                             for name in gate.THRESHOLDS["required_zero"]),
        excluded_zero=len(verdict.get("excluded") or []) <= gate.THRESHOLDS["excluded_max"],
        mean_delta_positive=verdict["mean_delta"] is not None
                             and verdict["mean_delta"] > gate.THRESHOLDS["mean_delta_gt"],
        ci_lower_positive=verdict["delta_ci95"][0] is not None
                           and verdict["delta_ci95"][0] > gate.THRESHOLDS["ci_lower_gt"],
        first_rate_not_worse=verdict["first_rate_delta"] is not None
                             and verdict["first_rate_delta"] >= -gate.THRESHOLDS["first_rate_drop_max"],
        robust_not_heavy_tail=(
            verdict["sign_test"]["positive"] + verdict["sign_test"]["negative"]
            >= gate.THRESHOLDS["min_informative_roots"]
            and verdict["sign_test"]["positive"] > verdict["sign_test"]["negative"]
            and verdict["sign_test"]["p"] < gate.THRESHOLDS["sign_test_max_p"]),
    )
    payload = dict(schema="candidate-gate-reevaluated/1",
                   source_gate=str(directory / "gate.json"),
                   source_results_sha256=hashlib.sha256(
                       (directory / "results.jsonl").read_bytes()).hexdigest(),
                   thresholds=gate.THRESHOLDS, verdict=verdict, checks=checks,
                   passed=all(checks.values()))
    target = directory / "reevaluated.json"
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + chr(10), encoding="utf-8")
    print(json.dumps({key: verdict[key] for key in
                      ("tables", "roots", "mean_delta", "delta_ci95", "median_delta",
                       "trimmed_mean_delta", "sign_test")}, ensure_ascii=False))
    print("checks:", json.dumps(checks, ensure_ascii=False))
    print("passed:", payload["passed"], "->", target)


if __name__ == "__main__":
    main()
