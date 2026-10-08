"""P25 · S4 修复：从**真实会话日志**恢复逐次调用账本（零模型、零网络）。

背景（评审 S4）：`dispatch_headless.py` 原先总写 `out_dir.parent/ledger.json`，首答账本被随后的
修复轮派发覆盖 ⇒ 48 条首答调用记录没有留在账本里。评审要求：**只能从真实日志恢复并核验，
不能按平均值或修复均值补造费用**。

做法：以各轮 `plan-merged.json`（含 run_id 与 kind）为索引，逐会话从
`<DSH_HOME>/sessions/*/<run_id>/session.jsonl.zstd` 读出真实事件：
step/start 与 tool/* 计数、turn/end、request/header 的模型身份、assistant/chunk 的 usage、
以及会话首末事件时间戳。产出**每次调用一条**的记录，并按 kind 分账、另出一份总账。
"""
from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/llm-guided-heuristic-route-2026-09-15/evidence/v4-impl/r9-admission/p25-round1'

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
import sys
from pathlib import Path
from typing import Any, Dict, List

HERE = Path(__file__).resolve().parent
ADMISSION = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/v4-impl/r9-admission')
sys.path.insert(0, str(ADMISSION))
import sealed_dispatch as sd                                    # noqa: E402

SESSIONS = Path("/Users/liyang/hangma-bot/.dsh-headless/sessions")


def call_record(row: Dict[str, Any], sessions_root: Path) -> Dict[str, Any]:
    run_id = row.get("run_id")
    path = next(sessions_root.glob("*/" + str(run_id) + "/session.jsonl.zstd"), None)
    record: Dict[str, Any] = {"task": row.get("task"), "kind": row.get("kind") or "first",
                              "run_id": run_id,
                              "prompt_sha256": row.get("prompt_sha256")}
    if path is None:
        record["status"] = "SESSION_MISSING"
        return record
    info = sd.read_session_strict(path)
    records = info["records"]
    types: Dict[str, int] = {}
    usage: Dict[str, int] = {}
    model = None
    times: List[int] = []
    for rec in records:
        types[rec.get("type")] = types.get(rec.get("type"), 0) + 1
        if isinstance(rec.get("time"), int):
            times.append(rec["time"])
        chunk = (rec.get("data") or {}).get("chunk") or {}
        if rec.get("type") == "assistant/chunk" and chunk.get("type") == "usage":
            for key, value in (chunk.get("usage") or {}).items():
                if isinstance(value, int):
                    usage[key] = usage.get(key, 0) + value
        if rec.get("type") == "request/header" and model is None:
            config = ((rec.get("data") or {}).get("header") or {}).get("config") or {}
            model = {"provider": config.get("provider"), "model": config.get("model"),
                     "reasoningEffort": config.get("reasoningEffort")}
    record.update({
        "status": "RECOVERED_FROM_SESSION_LOG",
        "session_sha256": info["session_sha256"],
        "bad_lines": info["bad_lines"],
        "step_start": types.get("step/start", 0),
        "tool_records": sum(v for k, v in types.items() if k.startswith("tool/")),
        "title_llm_requests": types.get("session/title-llm-request", 0),
        "turn_end": types.get("turn/end", 0),
        "request_headers": types.get("request/header", 0),
        "model": model,
        "usage": usage,
        "started_at_ms": min(times) if times else None,
        "finished_at_ms": max(times) if times else None,
        "elapsed_s": (round((max(times) - min(times)) / 1000.0, 2) if times else None),
    })
    return record


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--round", action="append", required=True,
                        help="LABEL:PLAN_JSON")
    parser.add_argument("--sessions-root", default=str(SESSIONS))
    parser.add_argument("--out-dir", required=True)
    args = parser.parse_args()
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    sessions_root = Path(args.sessions_root)
    summary = {"schema": "sitin-headless-call-ledger/2",
               "source": "真实会话日志逐条恢复（不从平均值推导）",
               "sessions_root": str(sessions_root), "rounds": []}
    for spec in args.round:
        label, plan_path = spec.split(":", 1)
        plan = json.loads(Path(plan_path).read_text(encoding="utf-8"))
        records = [call_record(row, sessions_root) for row in plan]
        by_kind: Dict[str, List[Dict[str, Any]]] = {}
        for record in records:
            by_kind.setdefault(record["kind"], []).append(record)
        (out / ("ledger-{0}-all.json".format(label))).write_text(
            json.dumps(records, ensure_ascii=False, indent=1), encoding="utf-8")
        for kind, rows in by_kind.items():
            (out / ("ledger-{0}-{1}.json".format(label, kind))).write_text(
                json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
        totals: Dict[str, int] = {}
        for record in records:
            for key, value in (record.get("usage") or {}).items():
                totals[key] = totals.get(key, 0) + value
        summary["rounds"].append({
            "round": label, "plan": plan_path, "calls": len(records),
            "by_kind": {kind: len(rows) for kind, rows in by_kind.items()},
            "missing_sessions": [r["task"] for r in records
                                 if r.get("status") == "SESSION_MISSING"],
            "usage_totals": totals,
            "non_single_request": [r["task"] for r in records
                                   if r.get("request_headers") not in (None, 1)],
            "with_tools": [r["task"] for r in records if r.get("tool_records")],
            "without_turn_end": [r["task"] for r in records if not r.get("turn_end")],
        })
    (out / "SUMMARY.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1),
                                      encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
