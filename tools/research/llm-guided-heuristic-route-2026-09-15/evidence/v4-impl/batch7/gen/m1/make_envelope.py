"""构造 M1 回复信封：绑定 prompt_sha256 与生成方血缘元数据。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/llm-guided-heuristic-route-2026-09-15/evidence/v4-impl/batch7/gen/m1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
import json
import datetime
from pathlib import Path

BASE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/v4-impl/batch7/gen/m1')
PROMPT_DIR = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/v4-impl/batch7/gen/m1/pending/m1')

prompt_sha = json.loads((_project_file(_PROJECT_ROOT, PROMPT_DIR / "prompt.json")).read_text(encoding="utf-8"))["prompt_sha256"]
reply = (_project_file(_PROJECT_ROOT, BASE / "reply-639e09e4.txt")).read_text(encoding="utf-8")

envelope = {
    "schema": "sitin-generation-reply/1",
    "origin": "delegated_model_reply",
    "prompt_sha256": prompt_sha,
    "reply": reply,
    "provider": "zai-coding-cn",
    "model": "glm-5.3",
    "captured_at_utc": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "delegator": "lead-session (dsh subagent 639e09e4)",
}

out = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/v4-impl/batch7/gen/m1/reply-m1.json')
out.write_text(json.dumps(envelope, ensure_ascii=False), encoding="utf-8")
print("envelope written; prompt_sha256=%s...; reply_chars=%d" % (prompt_sha[:16], len(reply)))
