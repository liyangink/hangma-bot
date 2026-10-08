"""子代理**取证卫生审计**：这批复用的都是完整 DSH 子代理（有工作区读写权限），
必须查清有没有人把"现成答案"读进上下文——那会让"真实模型成绩"变成抄写成绩。

判据：
  * 读入 = 该会话里出现过对下列路径的 `read`/\`cat\`/grep 命中**且工具结果带回实质正文**
    （>200 字符命中窗口）：`.../replies/**`（本轮 r1/r2 回复）、
    `r6-model-admission/replies/**`（旧轮同题回复）、`selftest/standard/**`（手工标准答案）、
    `admission-selftest.json`；
  * 写入 = 出现 `write`/`edit` 工具调用，或 bash 里带重定向/建目录/删除/复制。

用法：python audit_hygiene.py --plan <plan.json>
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
import importlib.util
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
_spec = importlib.util.spec_from_file_location("cr", _project_file(_PROJECT_ROOT, HERE / "collect_reply.py"))
cr = importlib.util.module_from_spec(_spec)
sys.modules["cr"] = cr
_spec.loader.exec_module(cr)

ANSWER_PATTERNS = (
    r"/replies/r[12]/T\d+\.txt",
    r"r6-model-admission/replies/",
    r"selftest/standard/",
    r"admission-selftest\.json",
)
WRITE_TOOL_NAMES = ("write", "edit")
BASH_WRITE_RE = re.compile(r">\s*[^ &|\n]|\bmkdir\b|\brm\b|\bcp\b|\bmv\b|\btee\b|>>")


def audit(run_id: str) -> dict:
    path = cr.session_path(run_id)
    if not path.is_file():
        return {"run_id": run_id, "status": "MISSING_SESSION"}
    records = cr.read_records(run_id)
    reads: list = []
    writes: list = []
    for rec in records:
        kind = rec.get("type")
        blob = json.dumps(rec, ensure_ascii=False)
        if kind in ("tool/call", "tool/code-dispatch-start"):
            for pattern in ANSWER_PATTERNS:
                if re.search(pattern, blob):
                    reads.append({"pattern": pattern,
                                  "snippet": blob[:200]})
        if kind == "tool/code-dispatch":
            # 工具结果正文里带回实质答案内容（只算确有正文的情形）
            for pattern in ANSWER_PATTERNS:
                for match in re.finditer(pattern, blob):
                    window = blob[match.start():match.start() + 600]
                    if len(window) > 300:
                        reads.append({"pattern": pattern, "result_window": window[:200]})
                        break
        if kind == "tool/call":
            data = rec.get("data") or {}
            name = data.get("name")
            args = str(data.get("arguments") or "")
            if name in WRITE_TOOL_NAMES:
                writes.append({"tool": name, "args": args[:160]})
            elif name == "bash" and BASH_WRITE_RE.search(args):
                writes.append({"tool": "bash", "args": args[:160]})
    tools_used = sorted({(rec.get("data") or {}).get("name")
                         for rec in records if rec.get("type") == "tool/call"})
    return {"run_id": run_id, "status": "OK", "tools_used": tools_used,
            "answer_reads": reads, "writes": writes,
            "read_count": len(reads), "write_count": len(writes)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", required=True)
    parser.add_argument("--out", default=str(_project_file(_PROJECT_ROOT, HERE / "audit-hygiene.json")))
    args = parser.parse_args()
    plan = json.loads(Path(args.plan).read_text(encoding="utf-8"))
    rows = []
    for item in plan:
        row = audit(item["run_id"])
        row.update({"task": item.get("task"), "kind": item.get("kind")})
        rows.append(row)
    payload = {"schema": "sitin-model-admission-hygiene-audit/1", "rows": rows}
    Path(args.out).write_text(json.dumps(payload, ensure_ascii=False, indent=1),
                              encoding="utf-8")
    for row in rows:
        print(row.get("task"), row.get("kind"), row["run_id"][:8],
              "reads=%s" % row.get("read_count"), "writes=%s" % row.get("write_count"),
              "tools=%s" % ",".join(row.get("tools_used") or []))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
