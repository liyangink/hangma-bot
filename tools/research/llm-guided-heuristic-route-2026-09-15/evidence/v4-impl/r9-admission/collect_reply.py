"""从 DSH 子代理会话痕迹里**逐字**取出被测模型的回复原文与用量。

为什么要走会话痕迹：重型任务（T06—T10）单次生成常常超过 run_code 的 600 秒墙钟上限，
前台等待会被整程序杀掉、回复丢失。改为**后台派发 + 会话痕迹回收**：派发只拿 runId，
回复从 ~/.dsh/sessions/<project>/<runId>/session.jsonl.zstd 里逐字读回，并同时记录
token 用量。会话记录是运行时自己写的原始轨迹，比任何人工转抄都可靠。

用法：
    python collect_reply.py --session <runId> --task T09 --round r1 --write
    python collect_reply.py --scan --since <epoch>            # 列出可疑孤儿会话
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
import json
import subprocess
from pathlib import Path

SESSIONS = Path.home() / ".dsh" / "sessions"
WORKSPACE = str(Path(__file__).resolve().parents[5])
#: 目录名编码规则：「/」→「-」，前缀一个「-」、后缀「--」（实测形态 --Users-liyang-hangma-bot--）。
PROJECT_DIR = SESSIONS / (("-" + WORKSPACE).replace("/", "-") + "--")


def session_path(run_id: str) -> Path:
    """按 runId 定位会话文件；项目目录名编码规则若不匹配，回退到全库搜索。"""

    direct = PROJECT_DIR / run_id / "session.jsonl.zstd"
    if direct.is_file():
        return direct
    for candidate in SESSIONS.glob("*/" + run_id + "/session.jsonl.zstd"):
        return candidate
    return direct


def read_records(run_id: str) -> list:
    path = session_path(run_id)
    if not path.is_file():
        raise SystemExit("会话不存在：{0}".format(path))
    raw = subprocess.run(["zstd", "-dc", str(path)], capture_output=True, check=True)
    records = []
    for line in raw.stdout.decode("utf-8").splitlines():
        if not line.strip():
            continue
        try:
            records.append(json.loads(line))
        except ValueError:
            continue
    return records


def summarize(run_id: str) -> dict:
    records = read_records(run_id)
    messages = [r["data"]["message"] for r in records
                if r.get("type") == "assistant/message" and "message" in r.get("data", {})]
    usage: dict = {}
    for rec in records:
        data = rec.get("data") or {}
        chunk = data.get("chunk") or {}
        if rec.get("type") == "assistant/chunk" and chunk.get("type") == "usage":
            for key, value in (chunk.get("usage") or {}).items():
                if isinstance(value, int):
                    usage[key] = usage.get(key, 0) + value
    # 任务提示词 = 第一条**不是**系统提醒/运行环境说明的 user 消息（子代理会话里
    # 后续还有 AGENTS.md 提醒等注入，不能取"最后一条"）。
    prompt_text = None
    for rec in records:
        if rec.get("type") != "user/message":
            continue
        data = rec["data"]
        # 两种实测形态：user/message 的 content 直接在 data 上；assistant/message 在 data.message 上。
        content = data.get("content")
        if content is None:
            content = (data.get("message") or {}).get("content")
        texts = None
        if isinstance(content, list):
            texts = "".join(b.get("text") or "" for b in content if b.get("type") == "text")
        elif isinstance(content, str):
            texts = content
        if not texts:
            continue
        head = texts.lstrip()[:40]
        if head.startswith("<system-reminder>") or head.startswith("Current runtime context"):
            continue
        prompt_text = texts
        break
    turn_end = [r for r in records if r.get("type") == "turn/end"]
    # 回复原文的口径（统一规则，不逐题调参）：
    #   1) 先看有没有**符合交付形态**的消息——代码类任务的交付以「{机制一句话}」开头并含
    #      python 围栏（\`\`\`python）；取**最后一条**这样的消息（模型可能先给出完整交付、
    #      随后继续跑自测并补发短消息，短消息不是交付本体）。
    #   2) 没有符合形态的消息（关键词类任务、或模型把答案包在说明里发出）→ 取最后一条
    #      带正文的 assistant 消息。空正文的消息一律跳过。
    texts = []
    for message in messages:
        text = "".join(b.get("text") or "" for b in message.get("content") or []
                       if b.get("type") == "text")
        if text.strip():
            texts.append(text)
    final = None
    for text in reversed(texts):
        if text.lstrip().startswith("{") and "```python" in text:
            final = text
            break
    if final is None and texts:
        final = texts[-1]
    return {"run_id": run_id, "records": len(records), "prompt": prompt_text,
            "answer": final, "usage": usage, "turns": len(turn_end),
            "finished": bool(turn_end) or bool(final),
            "turn_closed": bool(turn_end),
            "mtime": session_path(run_id).stat().st_mtime}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--session")
    parser.add_argument("--task")
    parser.add_argument("--round", default="r1")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--scan", action="store_true")
    parser.add_argument("--since", type=float, default=None)
    parser.add_argument("--out-dir",
                        default=str(_project_file(_PROJECT_ROOT, Path(__file__).resolve().parent / "replies")))
    args = parser.parse_args()
    if args.scan:
        rows = []
        for path in PROJECT_DIR.glob("*/session.jsonl.zstd"):
            mtime = path.stat().st_mtime
            if args.since is not None and mtime < args.since:
                continue
            run_id = path.parent.name
            try:
                info = summarize(run_id)
            except Exception as exc:                       # noqa: BLE001
                rows.append({"run_id": run_id, "error": str(exc)})
                continue
            head = (info.get("prompt") or "").strip().splitlines()
            rows.append({"run_id": run_id, "mtime": mtime, "finished": info["finished"],
                         "answer_chars": len(info.get("answer") or ""),
                         "usage": info["usage"],
                         "prompt_head": head[0][:70] if head else ""})
        print(json.dumps(sorted(rows, key=lambda r: r.get("mtime") or 0),
                         ensure_ascii=False, indent=1))
        return 0
    if not args.session:
        raise SystemExit("需要 --session <runId> 或 --scan")
    info = summarize(args.session)
    if not info["finished"] or not info["answer"]:
        print(json.dumps({"ok": False, "reason": "会话未结束或无回复",
                          "run_id": args.session, "finished": info["finished"]},
                         ensure_ascii=False))
        return 1
    payload = {"ok": True, "run_id": args.session, "task": args.task,
               "round": args.round, "answer_chars": len(info["answer"]),
               "usage": info["usage"], "turns": info["turns"]}
    if args.write and args.task:
        target = Path(args.out_dir) / args.round / (args.task + ".txt")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(info["answer"], encoding="utf-8")
        payload["written"] = str(target)
    print(json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
