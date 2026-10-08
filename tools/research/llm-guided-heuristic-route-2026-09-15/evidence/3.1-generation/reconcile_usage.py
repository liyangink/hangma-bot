"""headless 通道的**用量对账**：把会话日志里的真实消耗与台账记账逐条对齐。

为什么需要它（第四轮 Challenger 指出）：台账只记"当时测得出来的"用量——
第 1—3 次 headless 运行发生在用量解析补全**之前**，台账里是 0；
另有一次运行（42,817 tokens）的产物目录在重跑时被删除，**连记录都没有**。
"默认通道可直接计量"这句话只在**修复之后**成立，所以这里把真实消耗摊开：

    .venv/bin/python review/llm-guided-heuristic-route-2026-09-15/evidence/3.1-generation/reconcile_usage.py

口径：
  - 会话日志 = `<DSH_HOME>/sessions/**/session.jsonl.zstd`；用量取
    `assistant/chunk` 且 `data.chunk.type == "usage"` 的
    `data.chunk.usage.totalTokens` 并**累加**（每个 step 一条）；
  - 归属 = 记录里 `reply.session_file` 的 UUID 与会话目录名比对；
  - **不追溯改写旧记录**：旧记录按原样保留，差额在这里如实列出。
"""
from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/llm-guided-heuristic-route-2026-09-15/evidence/3.1-generation'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = _PROJECT_ROOT      # HERE = <repo>/review/<route>/evidence/3.1-generation
DSH_HOME = _project_file(_PROJECT_ROOT, REPO / ".dsh-headless")
USAGE_FIELDS = ("inputTokens", "outputTokens", "totalTokens", "cacheReadTokens",
                "reasoningTokens")


def session_files():
    root = _project_file(_PROJECT_ROOT, DSH_HOME / "sessions")
    if not root.is_dir():
        return []
    return sorted(root.rglob("session.jsonl.zstd"), key=lambda path: path.stat().st_mtime)


def session_usage(path: Path) -> dict:
    """一个会话的用量合计与首条提示词（用来认领"没有记录的会话"）。"""

    out = subprocess.run(["zstd", "-dc", str(path)], capture_output=True)
    totals = {field: 0 for field in USAGE_FIELDS}
    events = 0
    first_prompt = ""
    cwd = ""
    for line in out.stdout.decode("utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("type") == "session" and not cwd:
            cwd = str((event.get("data") or {}).get("cwd") or event.get("cwd") or "")
        if event.get("type") == "user/message" and not first_prompt:
            content = (event.get("data") or {}).get("content") or []
            if isinstance(content, list) and content:
                first_prompt = str((content[0] or {}).get("text", ""))[:60]
        elif event.get("type") == "assistant/chunk":
            chunk = (event.get("data") or {}).get("chunk") or {}
            if chunk.get("type") != "usage":
                continue
            events += 1
            for field in USAGE_FIELDS:
                value = (chunk.get("usage") or {}).get(field)
                if isinstance(value, int) and not isinstance(value, bool):
                    totals[field] += value
    totals["events"] = events
    totals["first_prompt"] = first_prompt
    totals["cwd"] = cwd
    return totals


def recorded_sessions() -> dict:
    """记录引用的会话 UUID → 归属说明。"""

    mapping = {}
    records_path = _project_file(_PROJECT_ROOT, HERE / "run-headless" / "records.jsonl")
    if not records_path.is_file():
        return mapping
    for line in records_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        # attempt_dir 是**相对产物目录**的路径（attempts/xxx），不要少拼一层。
        record_path = _project_file(_PROJECT_ROOT, HERE / "run-headless" / row["attempt_dir"] / "record.json")
        if not record_path.is_file():
            continue
        record = json.loads(record_path.read_text(encoding="utf-8"))
        session = record["reply"].get("session_file") or ""
        match = re.search(r"session-[0-9a-f-]+", session)
        if match:
            mapping[match.group(0)] = {
                "attempt": record["attempt_ordinal"],
                "operator": record["operator"],
                "load_ok": record["load"]["ok"],
                "ledger_tokens": record["budget"]["call_tokens"],
                "usage_source": record["reply"].get("usage_source"),
            }
    return mapping


def main() -> int:
    mapping = recorded_sessions()
    rows = []
    for path in session_files():
        usage = session_usage(path)
        uuid = path.parent.name
        rows.append({"session": uuid, "tokens": usage["totalTokens"],
                     "events": usage["events"], "prompt": usage["first_prompt"],
                     "cwd": usage["cwd"], "owner": mapping.get(uuid)})
    ledger = json.loads((_project_file(_PROJECT_ROOT, HERE / "run-headless" / "budget.json")).read_text(encoding="utf-8"))
    ledger_total = sum((entry.get("tokens") or 0) for entry in ledger.get("entries", []))
    recorded_total = sum(row["tokens"] for row in rows if row["owner"])
    unrecorded_total = sum(row["tokens"] for row in rows if not row["owner"])
    lines = ["# headless 用量对账（会话日志 ↔ 台账）", "",
             "**口径**：会话日志里 `assistant/chunk` → `data.chunk.usage.totalTokens`",
             "逐条累加；归属按记录里的 `reply.session_file` UUID 与会话目录名比对；",
             "**不追溯改写旧记录**。".replace("`", chr(96)), "",
             "| 会话 UUID | tokens | usage 事件 | 归属 | 台账记账 | 备注 |",
             "| --- | ---: | ---: | --- | ---: | --- |"]
    for row in rows:
        owner = row["owner"]
        if owner:
            who = "attempt {0}（{1}，load_ok={2}）".format(
                owner["attempt"], owner["operator"], owner["load_ok"])
            booked = owner["ledger_tokens"]
            note = "已记账" if booked else "**未记账**（用量解析补全之前）"
        else:
            who, booked = "**无对应记录**", "—"
            # 区分两种"没记录"：① 不是本工具的调用（cwd 在仓库外 / 探针提示词）；
            # ② 本工具的运行，但产物目录在重跑时被删除（连记录都没有）。
            # 本工具每次调用都用 mkdtemp(prefix="sitin-headless-") 当工作目录，
            # 因此 cwd 是识别"这是不是本工具的调用"的可靠指纹（比"在不在仓库里"准）。
            ours = Path(row["cwd"] or "/").name.startswith("sitin-headless-")
            note = ("本工具的运行，但产物目录在重跑时被删除（**连记录都没有**）"
                    if ours else
                    "**不是本工具的调用**（外部探针，cwd={0}）".format(row["cwd"] or "未知"))
        lines.append("| {0} | {1} | {2} | {3} | {4} | {5} |".format(
            row["session"].replace("session-", "")[:8], row["tokens"], row["events"],
            who, booked, note))
    lines += ["",
              "- 会话日志合计：**{0} tokens**".format(recorded_total + unrecorded_total),
              "- 有记录的运行：**{0} tokens**".format(recorded_total),
              "- 无记录的运行：**{0} tokens**".format(unrecorded_total),
              "- 台账实际记账：**{0} tokens**（只含用量解析补全之后的调用）".format(ledger_total),
              "",
              "**结论（诚实版）**：默认通道的用量**从用量解析补全之后**才可计量；",
              "之前几次只能靠会话日志追溯，其中一次（产物目录在重跑时被删除）**连记录都没有**。",
              "这些数字列在上面，**不并入台账、也不回溯改写旧记录**。"]
    text = "\n".join(lines) + "\n"
    (_project_file(_PROJECT_ROOT, HERE / "USAGE-RECONCILIATION.md")).write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
