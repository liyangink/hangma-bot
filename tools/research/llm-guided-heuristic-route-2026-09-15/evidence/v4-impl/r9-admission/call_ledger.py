"""P22 准入调用的**派发台账**：把本轮所有被测模型调用（含被墙钟杀掉的、重复派发的）
逐条登记，并逐字回收回复原文。

为什么需要它：run_code 的 600 秒墙钟上限会杀掉重型任务的前台等待，回复可能已由模型
生成、却没能写盘。DSH 把每次子代理会话逐字节写在
~/.dsh/sessions/<project>/<runId>/session.jsonl.zstd 里——直接从这里回收是**逐字**的，
比人工转抄可靠；同时能读到该次调用的 token 用量。

判据（防止把别的会话误认成本轮派遣）：
  1. 会话提示词必须以**本包某个任务的提示词原文**开头；
  2. 末尾必须带本轮派发追加的交付方式行（MARKER）。

用法：
    python call_ledger.py --scan --since <epoch> [--out <json>]
    python call_ledger.py --write <TASK> <RUNID> --round r1
"""
from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/llm-guided-heuristic-route-2026-09-15/evidence/v4-impl/r9-admission'

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
import importlib.util
import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
_spec = importlib.util.spec_from_file_location("cr", _project_file(_PROJECT_ROOT, HERE / "collect_reply.py"))
cr = importlib.util.module_from_spec(_spec)
sys.modules["cr"] = cr
_spec.loader.exec_module(cr)

PROMPTS = {p.stem: p.read_text(encoding="utf-8")
           for p in sorted((_project_file(_PROJECT_ROOT, HERE / "package" / "prompts")).glob("T*.txt"))}
MARKER = "【交付方式】直接输出你的答案正文本身，不要任何前言、后记、解释或元说明。"


def identify(prompt: str) -> str | None:
    """按**提示词原文前缀**认任务：任务包提示词是会话提示词的严格前缀。

    取**最长**匹配：同族任务（如 T05 的 I1 正文被 T10 复用并追加夹具段）存在
    「A 的提示词是 B 的提示词前缀」的关系，只取第一个匹配会把 B 认成 A。
    """

    matches = [task_id for task_id, text in PROMPTS.items()
               if prompt.startswith(text)]
    if not matches:
        return None
    return max(matches, key=lambda task_id: len(PROMPTS[task_id]))


def scan(since: float | None) -> list:
    rows = []
    for path in cr.SESSIONS.glob("*/*/session.jsonl.zstd"):
        mtime = path.stat().st_mtime
        if since is not None and mtime < since:
            continue
        run_id = path.parent.name
        if run_id.startswith("session-"):
            continue
        try:
            info = cr.summarize(run_id)
        except SystemExit:
            continue
        prompt = info.get("prompt") or ""
        if MARKER not in prompt:
            continue
        task_id = identify(prompt)
        answer = info.get("answer") or ""
        rows.append({
            "run_id": run_id,
            "task_id": task_id,
            "dispatched_at": None,
            "finished": info["finished"],
            "finished_at": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(mtime)),
            "answer_chars": len(answer),
            "answer_sha256": (hashlib.sha256(answer.encode("utf-8")).hexdigest()
                              if answer else None),
            "usage": info["usage"],
            "dispatch_note": "R9 P22 模型准入派发（提示词逐字取自 r9-admission/package/prompts）",
        })
    return sorted(rows, key=lambda row: row["finished_at"] or "")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scan", action="store_true")
    parser.add_argument("--since", type=float, default=None)
    parser.add_argument("--out", default=str(_project_file(_PROJECT_ROOT, HERE / "replies" / "call-ledger.json")))
    parser.add_argument("--write", nargs=2, metavar=("TASK", "RUNID"))
    parser.add_argument("--collect", default=None,
                        help="按计划 JSON（[{task,kind,run_id}]）批量回收回复原文")
    parser.add_argument("--round", default="r1")
    args = parser.parse_args()
    if args.collect:
        plan = json.loads(Path(args.collect).read_text(encoding="utf-8"))
        rows = []
        for item in plan:
            task_id, kind, run_id = item["task"], item["kind"], item["run_id"]
            try:
                info = cr.summarize(run_id)
            except SystemExit:
                rows.append({"task": task_id, "kind": kind, "run_id": run_id,
                             "status": "MISSING"})
                continue
            answer = info.get("answer") or ""
            if not info["finished"] or not answer:
                rows.append({"task": task_id, "kind": kind, "run_id": run_id,
                             "status": "PENDING",
                             "usage_out": info["usage"].get("outputTokens")})
                continue
            round_dir = "r1" if kind == "repair" else "r2"
            name = task_id + (".repair.txt" if kind == "repair" else ".txt")
            target = _project_file(_PROJECT_ROOT, HERE / "replies" / round_dir / name)
            target.write_text(answer, encoding="utf-8")
            rows.append({"task": task_id, "kind": kind, "run_id": run_id,
                         "status": "WRITTEN", "written": str(target),
                         "chars": len(answer),
                         "sha256": hashlib.sha256(answer.encode("utf-8")).hexdigest(),
                         "usage_out": info["usage"].get("outputTokens")})
        print(json.dumps(rows, ensure_ascii=False, indent=1))
        return 0
    if args.write:
        task_id, run_id = args.write
        info = cr.summarize(run_id)
        answer = info.get("answer") or ""
        if not info["finished"] or not answer:
            print(json.dumps({"ok": False, "run_id": run_id}, ensure_ascii=False))
            return 1
        target = _project_file(_PROJECT_ROOT, HERE / "replies" / args.round / (task_id + ".txt"))
        target.write_text(answer, encoding="utf-8")
        print(json.dumps({"ok": True, "written": str(target), "chars": len(answer),
                          "sha256": hashlib.sha256(answer.encode()).hexdigest()},
                         ensure_ascii=False))
        return 0
    rows = scan(args.since)
    Path(args.out).write_text(json.dumps(
        {"schema": "sitin-model-admission-call-ledger/1",
         "model": {"provider": "deepseek-official", "model": "deepseek-v4-flash",
                   "reasoning_effort": "默认（未显式指定，两轮一致）"},
         "source": "DSH 子代理会话痕迹（~/.dsh/sessions/**/session.jsonl.zstd）",
         "calls": rows}, ensure_ascii=False, indent=1), encoding="utf-8")
    for row in rows:
        print(row["finished_at"], row["run_id"][:8], row["task_id"],
              "fin={0}".format(row["finished"]), "ans={0}".format(row["answer_chars"]),
              "out_tokens={0}".format((row["usage"] or {}).get("outputTokens")))
    print("total", len(rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
