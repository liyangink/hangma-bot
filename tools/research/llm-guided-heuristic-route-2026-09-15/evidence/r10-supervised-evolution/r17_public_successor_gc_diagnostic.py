"""R17 P0：循环 GC 与大对象证据物化的尾延迟诊断。

协议冻结为六遍完整 226 窗重放。每遍开始前 ``gc.collect()``；只在一次
``evaluate_once`` 临界段关闭循环垃圾回收，并在 ``finally`` 中恢复原状态；
保存摘要后删除完整逐边对象，再执行 ``gc.collect()``。不启用 tracemalloc，
不落盘完整逐边 JSON，不修改生产代码或冻结性能阈值。
"""

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

import gc
import hashlib
import json
from pathlib import Path
import resource
import sys
import time
from typing import Any


HERE = Path(__file__).resolve().parent
ROUTE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15')
ROOT = _PROJECT_ROOT
for path in (_project_file(_PROJECT_ROOT, ROOT / "src"), _project_file(_PROJECT_ROOT, ROUTE / "tools"), HERE):
    sys.path.insert(0, str(path))

import r17_public_successor_batch_performance_probe as batch  # noqa: E402
import r17_public_successor_pilot as raw  # noqa: E402


OUT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r17-public-successor-performance-04-20260921')
RAW_RESULT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r17-public-successor-pilot-01-20260921/result.json')
PASSES = 6


def _peak_rss() -> dict[str, Any]:
    """返回进程累计峰值 RSS；macOS 是字节，Linux 是 KiB。"""

    value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    if sys.platform == "darwin":
        mib = float(value) / (1024.0 * 1024.0)
        unit = "bytes"
    else:
        mib = float(value) / 1024.0
        unit = "KiB"
    return {
        "ru_maxrss_raw": value,
        "platform_unit": unit,
        "peak_rss_mib": mib,
        "meaning": "进程生命周期累计高水位，不是该遍独占内存，也不是当前RSS",
    }


def _generation_counts() -> list[dict[str, int]]:
    return [
        {
            "collections": int(row["collections"]),
            "collected": int(row["collected"]),
            "uncollectable": int(row["uncollectable"]),
        }
        for row in gc.get_stats()
    ]


def main() -> None:
    if OUT.exists():
        raise SystemExit("R17 GC诊断目录已存在；拒绝覆盖")
    OUT.mkdir(parents=True)
    expected = json.loads(RAW_RESULT.read_text(encoding="utf-8"))["semantic_digest"]
    windows = raw.r16.load_windows()
    initial_enabled = gc.isenabled()
    pass_results = []
    per_window = []
    protocol_restored = True

    for pass_index in range(1, PASSES + 1):
        collected_before = gc.collect()
        state_before = gc.isenabled()
        stats_before = _generation_counts()
        rss_before = _peak_rss()
        entered_disabled = False
        edges = None
        rows = None
        meta = None
        wall_started = time.perf_counter()
        try:
            if state_before:
                gc.disable()
            entered_disabled = not gc.isenabled()
            edges, rows, meta = batch.evaluate_once(windows)
        finally:
            if state_before and not gc.isenabled():
                gc.enable()
            elif not state_before and gc.isenabled():
                gc.disable()
        wall_seconds = time.perf_counter() - wall_started
        restored_after_critical = gc.isenabled() == state_before
        protocol_restored = protocol_restored and restored_after_critical
        latency = batch._latency(rows)
        digest = meta["semantic_digest"]
        summary = {
            "pass_index": pass_index,
            "digest": digest,
            "digest_matches_raw": digest == expected,
            "latency": latency,
            "gate": {
                "passed": (
                    latency["p99_ms"] <= raw.RESEARCH_P99_MS_MAX
                    and latency["max_ms"] <= raw.RESEARCH_WINDOW_MS_MAX
                ),
                "p99_ms_max": raw.RESEARCH_P99_MS_MAX,
                "window_max_ms": raw.RESEARCH_WINDOW_MS_MAX,
            },
            "wall_seconds_including_digest": wall_seconds,
            "gc": {
                "collected_before": collected_before,
                "enabled_before": state_before,
                "disabled_inside_critical": entered_disabled,
                "restored_after_critical": restored_after_critical,
                "stats_before": stats_before,
            },
            "peak_rss_after_critical": _peak_rss(),
            "counts": meta["counts"],
            "performance_counts": meta["performance_counts"],
            "issues": {
                "route": len(meta["route_issues"]),
                "projection": len(meta["projection_issues"]),
            },
        }
        per_window.append({
            "pass_index": pass_index,
            "rows": rows,
        })
        # 完整边和 meta 含大量短命容器；不把它们带入下一遍。
        del edges
        del meta
        del rows
        collected_after = gc.collect()
        summary["gc"].update({
            "collected_after_deleting_large_objects": collected_after,
            "enabled_after_cleanup": gc.isenabled(),
            "garbage_len_after_cleanup": len(gc.garbage),
            "stats_after_cleanup": _generation_counts(),
        })
        summary["peak_rss_after_cleanup"] = _peak_rss()
        pass_results.append(summary)

    if initial_enabled and not gc.isenabled():
        gc.enable()
    elif not initial_enabled and gc.isenabled():
        gc.disable()
    final_restored = gc.isenabled() == initial_enabled
    protocol_restored = protocol_restored and final_restored

    all_digest_equal = all(row["digest"] == expected for row in pass_results)
    all_gate_pass = all(row["gate"]["passed"] for row in pass_results)
    all_gc_protocol = all(
        row["gc"]["disabled_inside_critical"]
        and row["gc"]["restored_after_critical"]
        and row["gc"]["enabled_after_cleanup"] == row["gc"]["enabled_before"]
        for row in pass_results
    ) and final_restored
    result = {
        "schema": "r17-public-successor-gc-diagnostic-result/1",
        "status": (
            "PASS_EVIDENCE_HARNESS_GC_DIAGNOSIS_PRODUCTION_NOT_ADMITTED"
            if all_digest_equal and all_gate_pass and all_gc_protocol
            else "FAIL_GC_DIAGNOSTIC_OR_PERFORMANCE"
        ),
        "passes": PASSES,
        "windows_per_pass": len(windows),
        "tables": 0,
        "model_calls": 0,
        "strength_claim": False,
        "selection_eligible": False,
        "raw_digest": expected,
        "all_digests_equal": all_digest_equal,
        "all_performance_gates_passed": all_gate_pass,
        "gc_protocol": {
            "initial_enabled": initial_enabled,
            "final_enabled": gc.isenabled(),
            "final_restored": final_restored,
            "all_passes_restored": protocol_restored,
            "all_passes_followed_protocol": all_gc_protocol,
            "tracemalloc": False,
        },
        "latency_ranges": {
            "mean_ms_min": min(row["latency"]["mean_ms"] for row in pass_results),
            "mean_ms_max": max(row["latency"]["mean_ms"] for row in pass_results),
            "p99_ms_min": min(row["latency"]["p99_ms"] for row in pass_results),
            "p99_ms_max": max(row["latency"]["p99_ms"] for row in pass_results),
            "window_max_ms_min": min(row["latency"]["max_ms"] for row in pass_results),
            "window_max_ms_max": max(row["latency"]["max_ms"] for row in pass_results),
        },
        "passes_summary": pass_results,
        "diagnosis": (
            "在语义与工作量相同、只改变证据工具循环GC时，六遍全部通过冻结性能门；"
            "结合performance-03暖遍连续尾延迟，支持其主因是循环GC扫描/大对象证据物化，"
            "不支持把该探针直接认定为生产可准入实现。"
        ),
        "production_admission_remaining": [
            "把34摸牌批量接口下沉到hangma唯一规则边界，policy不重算规则数学",
            "生产路径不得物化完整edge_rows；固定reducer应流式消费或只保留有界前沿",
            "增加重复调用RSS/对象数量无增长与循环引用检查",
            "在正式1秒/3秒动作链包含最终复核、审计和提交余量的性能门复验",
        ],
    }
    raw.write_json(_project_file(_PROJECT_ROOT, OUT / "result.json"), result)
    raw.write_json(_project_file(_PROJECT_ROOT, OUT / "per-window.json"), {
        "schema": "r17-public-successor-gc-diagnostic-per-window/1",
        "passes": per_window,
    })
    runner = Path(__file__)
    batch_runner = _project_file(_PROJECT_ROOT, HERE / "r17_public_successor_batch_performance_probe.py")
    raw.write_json(_project_file(_PROJECT_ROOT, OUT / "manifest.json"), {
        "schema": "r17-public-successor-gc-diagnostic-manifest/1",
        "protocol_frozen_before_run": {
            "passes": PASSES,
            "collect_before_each_pass": True,
            "disable_cyclic_gc_only_during_evaluate_once": True,
            "restore_in_finally": True,
            "delete_large_objects_then_collect": True,
            "tracemalloc": False,
        },
        "runner": {
            "path": str(runner),
            "sha256": hashlib.sha256(runner.read_bytes()).hexdigest(),
        },
        "batch_runner": {
            "path": str(batch_runner),
            "sha256": hashlib.sha256(batch_runner.read_bytes()).hexdigest(),
        },
        "raw_result": {
            "path": str(RAW_RESULT),
            "sha256": hashlib.sha256(RAW_RESULT.read_bytes()).hexdigest(),
        },
        "peak_rss": "resource.RUSAGE_SELF.ru_maxrss进程生命周期累计高水位；macOS字节、Linux KiB；不冒充单遍独占或当前RSS",
        "outputs": ["result.json", "per-window.json"],
    })
    print(json.dumps({
        "status": result["status"],
        "all_digests_equal": all_digest_equal,
        "all_gates_passed": all_gate_pass,
        "gc_protocol": result["gc_protocol"],
        "latency_ranges": result["latency_ranges"],
        "peak_rss_final": _peak_rss(),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
