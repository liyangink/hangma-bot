"""P25 · 包 A 第 3 项：**无权限单次交付通道**（评审 D1 首选形态）。

用 `dsh --profile headless` + `--patch no-tools-eval.patch.yml`（禁用全部工具插件）把题目发给模型：
- 整轮**只有一次模型请求**（会话标题那次也按 patch 关掉）；
- 模型在**能力上**没有任何工具（实测让它读文件 → 输出 NO_TOOLS、痕迹 tool/call=0）；
- 正文只进 stdout，父进程直接收正文，**不需要 send_message 回传**，因此不存在
  "harness 要求投递 vs 不得使用工具"的冲突（P24 的 17/24 拒收根因）。
- 会话痕迹写在 `<DSH_HOME>/sessions/<cwd-slug>/session-<uuid>/session.jsonl.zstd`，
  仍然可以被 `sealed_dispatch.py audit` 审计（含密封条款、工具痕迹、结束状态、摘要绑定）；
- **单请求协议断言（评审 S3）**：request_headers == 1、turn_end == 1 且终止后无工作记录、
  title_llm_requests == 0、无工具记录、请求配置 == 冻结身份；任一不满足即 fail-closed
  （该次调用不进 plan，CLI 以非零码退出）。

纪律：本工具**不做判分**；产物只写自己的目录；每题记账（步数、工具调用数、用量、耗时）。
"""
from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/llm-guided-heuristic-route-2026-09-15/evidence/v4-impl/r9-admission/p25-headless'

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
import os
import re
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ADMISSION = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/v4-impl/r9-admission')
ROUTE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15')
REPO = _PROJECT_ROOT
sys.path.insert(0, str(ADMISSION))

import sealed_dispatch as sd                                    # noqa: E402

#: 在 DSH 会话里直接跑 `dsh` 会 EPERM（继承 DSH_HOME=~/.dsh 不可写），必须显式指向
#: 仓库内的 .dsh-headless（可写、profile 齐全，凭据由 credentials.patch.yml 只读指回）。
DSH_HOME = _project_file(_PROJECT_ROOT, REPO / ".dsh-headless")
PATCH_DIR = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/v4-impl/r9-admission/p25-channel/patch')
CREDS_PATCH = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/v4-impl/r9-admission/p25-channel/patch/credentials.patch.yml')
NO_TOOLS_PATCH = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/v4-impl/r9-admission/p25-channel/patch/no-tools-eval.patch.yml')
#: 身份与 settings 层（顺序固定）：effort 只能从 settings 层生效，见下。
SETTINGS_PATCH = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/v4-impl/r9-admission/p25-headless/patch/headless-settings.patch.yml')
ROUTE_PATCH = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/v4-impl/r9-admission/p25-headless/patch/route-flash-max.patch.yml')


def _sessions_root() -> Path:
    return _project_file(_PROJECT_ROOT, DSH_HOME / "sessions")


def _all_session_dirs() -> set:
    root = _sessions_root()
    return {path.parent for path in root.glob("*/*/session.jsonl.zstd")} if root.is_dir() else set()


def _expected_request_config(package: Path):
    """冻结请求身份：provider/model 取题包 manifest，effort/maxTokens 取通道常量（评审 S3）。"""
    manifest_path = Path(package) / "manifest.json"
    if not manifest_path.is_file():
        return None
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) or {}
    return sd.expected_request_config(manifest.get("target_model"))


def _counts(session_path: Path, expected_config=None) -> dict:
    """读会话计数 + **单请求协议断言**（评审 S3）。

    断言项（任一不满足即 protocol_ok=False；调用方 fail-closed 报错退出，且该次调用不进
    plan，因此不可能进入准入来源绑定）：
      * request_headers == 1（一次会话只允许一次模型请求）；
      * turn/end 恰好一次，且终止事件之后没有任何工作记录；
      * title_llm_requests == 0（会话标题那次请求必须已被 patch 关掉）；
      * 无任何 tool/* 记录（本通道工具插件全禁）；
      * 请求配置（provider/model/reasoningEffort/maxTokens）与冻结值一致。
    """
    info = sd.read_session_strict(session_path)
    types = {}
    for rec in info["records"]:
        types[rec.get("type")] = types.get(rec.get("type"), 0) + 1
    protocol = sd.request_protocol(info["records"], expected_config)
    config = protocol.get("request_config")
    violations = list(protocol["violations"])
    if types.get("session/title-llm-request", 0):
        violations.append("TITLE_LLM_REQUEST")
    if sum(v for k, v in types.items() if k.startswith("tool/")):
        violations.append("TOOL_RECORD_PRESENT")
    model = ({"provider": config.get("provider"), "model": config.get("model"),
              "reasoningEffort": config.get("reasoningEffort")}
             if isinstance(config, dict) else None)
    return {"step_start": types.get("step/start", 0),
            "tool_calls": sum(v for k, v in types.items() if k.startswith("tool/")),
            "title_llm_requests": types.get("session/title-llm-request", 0),
            "request_headers": protocol["request_headers"],
            "turn_end": protocol["turn_ends"],
            "assistant_messages": types.get("assistant/message", 0),
            "post_termination_work": protocol["post_termination_work"],
            "model": model, "request_config": config,
            "protocol_violations": violations, "protocol_ok": not violations}


def dispatch(package: Path, tasks, out_dir: Path, plan_path: Path,
             model_patch: str = None, timeout_s: int = 900,
             concurrency: int = 1, prompt_dir: Path = None,
             kind: str = "first", suffix: str = "") -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    if prompt_dir is not None:
        # 修复轮：题面由 repair_prompt.py 预先构造好（含脱敏断言），本函数只负责派发。
        prompts_dir = Path(prompt_dir)
    else:
        prompts_dir = _project_file(_PROJECT_ROOT, HERE / "dispatch")
        prompts_dir.mkdir(parents=True, exist_ok=True)
        sd.do_emit(package, prompts_dir, set(tasks) if tasks else None)
    # 固定四件套：凭据 → 工具全禁 → settings（effort 从这里生效）→ 路由（provider/model）。
    patches = [str(CREDS_PATCH), str(NO_TOOLS_PATCH), str(SETTINGS_PATCH), str(ROUTE_PATCH)]
    if model_patch:
        patches.append(model_patch)
    # 每题的**密封提示词**摘要：并发派发时用它把"会话目录 ↔ 题目"配起来（不靠时序猜）。
    expected_prompt = {task_id: hashlib.sha256(
        (prompts_dir / task_id / "prompt.txt").read_bytes()).hexdigest() for task_id in tasks}
    before_all = _all_session_dirs()

    def run_one(task_id: str) -> dict:
        prompt = (prompts_dir / task_id / "prompt.txt").read_text(encoding="utf-8")
        started = time.time()
        env = dict(os.environ)
        env["DSH_HOME"] = str(DSH_HOME)
        command = ["dsh", "--profile", "headless"]
        for patch in patches:
            command += ["--patch", patch]
        command.append(prompt)
        proc = subprocess.run(command, cwd=str(REPO), env=env,
                              capture_output=True, text=True, timeout=timeout_s)
        return {"task": task_id, "exit_code": proc.returncode,
                "elapsed_s": round(time.time() - started, 2),
                "answer_chars": len(proc.stdout.strip()),
                "stdout": proc.stdout.strip(),
                "stderr_tail": proc.stderr.strip()[-200:]}

    ledger = []
    if concurrency and concurrency > 1:
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=int(concurrency)) as pool:
            for row in pool.map(run_one, tasks):
                ledger.append(row)
    else:
        for task_id in tasks:
            ledger.append(run_one(task_id))

    expected_config = _expected_request_config(package)
    # 事后按**提示词摘要**把新会话目录配到题目：并发下唯一可靠的做法（不靠时序）。
    new_dirs = sorted(_all_session_dirs() - before_all)
    by_task: dict = {}
    unmatched = []
    for directory in new_dirs:
        session = directory / "session.jsonl.zstd"
        try:
            info = sd.read_session_strict(session)
        except Exception:                                   # noqa: BLE001
            unmatched.append(directory.name)
            continue
        blocks = sd.first_message_blocks(info["records"])
        digest = hashlib.sha256(blocks["task"].encode("utf-8")).hexdigest()
        owner = next((tid for tid, want in expected_prompt.items()
                      if want == digest and tid not in by_task), None)
        if owner is None:
            unmatched.append(directory.name)
        else:
            by_task[owner] = directory

    plan = []
    for row in ledger:
        task_id = row.pop("task")
        stdout = row.pop("stdout")
        directory = by_task.get(task_id)
        if directory is None:
            row.update({"task": task_id, "run_id": None,
                        "error": "未找到与该题提示词摘要匹配的新会话目录"})
        else:
            session = directory / "session.jsonl.zstd"
            counts = _counts(session, expected_config)
            row.update({"task": task_id, **counts, "run_id": directory.name})
            (out_dir / (task_id + suffix + ".txt")).write_text(stdout, encoding="utf-8")
            if counts["protocol_ok"]:
                plan.append({"task": task_id, "kind": kind, "run_id": directory.name,
                             "prompt_sha256": expected_prompt[task_id]})
            else:
                # fail-closed：不满足单请求协议的会话**不进 plan**（下游无法把它当交付绑定），
                # 同时由 main 具名报错并以非零码退出。
                row["plan_excluded"] = ("单请求协议断言不满足：{0}".format(
                    ", ".join(counts["protocol_violations"])))
        print(json.dumps(row, ensure_ascii=False), flush=True)
    ledger.sort(key=lambda r: r["task"])
    unmatched_note = {"unmatched_session_dirs": unmatched} if unmatched else {}
    plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=1), encoding="utf-8")
    report = {"schema": "sitin-headless-dispatch/2", "dsh_home": str(DSH_HOME),
              "patches": patches, "package": str(package), "calls": ledger,
              "concurrency": concurrency, **unmatched_note,
              "expected_request_config": expected_config,
              "protocol_assertions": ["request_headers == 1", "turn_end == 1",
                                      "post_termination_work == 0",
                                      "title_llm_requests == 0", "tool records == 0",
                                      "request config == frozen identity"],
              "protocol_failures": [row.get("task") for row in ledger
                                    if not row.get("protocol_ok", True)],
              "plan": str(plan_path), "out_dir": str(out_dir),
              "note": ("无权限单次交付：每题一次模型请求、工具插件全禁、正文取 stdout；"
                       "单请求协议断言不满足即 fail-closed（该次调用不进 plan，CLI 非零退出）；"
                       "run_id 为 headless 会话目录名，可直接交给 sealed_dispatch audit。")}
    # 评审 S4：账本**绝不覆盖**。每次派发写独立文件（含 kind 与时间戳），并追加一行到
    # 只增不改的 JSONL 总账；历史账本一旦落盘就不再改写。
    stamp = time.strftime("%Y%m%dT%H%M%S")
    ledger_path = out_dir.parent / ("ledger-{0}-{1}.json".format(kind, stamp))
    suffix_index = 1
    while ledger_path.exists():
        ledger_path = out_dir.parent / ("ledger-{0}-{1}-{2}.json".format(kind, stamp, suffix_index))
        suffix_index += 1
    ledger_path.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    with (out_dir.parent / "ledger.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"kind": kind, "concurrency": concurrency,
                                 "stamp": stamp, "calls": len(ledger),
                                 "path": str(ledger_path)}, ensure_ascii=False) + "\n")
    report["ledger_path"] = str(ledger_path)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--package", default=str(_project_file(_PROJECT_ROOT, ADMISSION / "package")))
    parser.add_argument("--tasks", required=True, help="逗号分隔，如 T01,T11,T17")
    parser.add_argument("--out", default=str(_project_file(_PROJECT_ROOT, HERE / "smoke" / "replies")))
    parser.add_argument("--plan", default=str(_project_file(_PROJECT_ROOT, HERE / "smoke" / "plan.json")))
    parser.add_argument("--model-patch", default=None)
    parser.add_argument("--prompt-dir", default=None,
                        help="改用预先构造好的提示词目录（修复轮用）")
    parser.add_argument("--kind", default="first", help="计划里的 kind（first/repair）")
    parser.add_argument("--suffix", default="", help="回复文件后缀，如 .repair")
    parser.add_argument("--concurrency", type=int, default=1,
                        help="并发派发数；>1 时用提示词摘要事后配对会话目录（不靠时序）")
    args = parser.parse_args()
    tasks = [t.strip() for t in args.tasks.split(",") if t.strip()]
    report = dispatch(Path(args.package), tasks, Path(args.out), Path(args.plan),
                      model_patch=args.model_patch, concurrency=args.concurrency,
                      prompt_dir=(Path(args.prompt_dir) if args.prompt_dir else None),
                      kind=args.kind, suffix=args.suffix)
    # fail-closed：单请求协议断言（含 request_headers/title_llm_requests/工具记录/配置）
    # 任一不满足即视为本次派发失败，非零退出；对应行也不会进入 plan。
    bad = [row for row in report["calls"]
           if row.get("exit_code") != 0 or row.get("step_start") != 1
           or row.get("tool_calls") != 0 or not row.get("run_id")
           or row.get("protocol_ok") is not True]
    print(json.dumps({"tasks": len(tasks), "clean": len(tasks) - len(bad),
                      "protocol_failures": report["protocol_failures"],
                      "problems": bad}, ensure_ascii=False, indent=1))
    return 0 if not bad else 2


if __name__ == "__main__":
    raise SystemExit(main())
