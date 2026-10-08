"""把**外部委派拿回的原始回复**封装成工具要求的回复文件（sitin-generation-reply/1）。

为什么要单独一个脚本：封套里的 `prompt_sha256` 必须与**工具产出的提示词**逐字节一致，
`origin` 必须如实声明来源。手工拼 JSON 极易把这两处写错，而工具会因此拒绝摄入
（这正是设计意图：不接受把另一次回复当作本次回复）。

    # 委派回复（真实模型）
    .venv/bin/python make_reply_envelope.py \
        --raw   delegated/i1-reply.raw.txt \
        --out   delegated/i1-reply.json \
        --prompt-file run-delegate/pending/i1/prompt.txt \
        --origin delegated_model_reply \
        --provider "dsh-harness/native-subagent" --model "平台默认（未显式选档）" \
        --delegator "本会话 Agent（坐隐 3.1 包 genloop）"

    # 人工格式夹具
    .venv/bin/python make_reply_envelope.py --raw r.txt --out f.json \
        --prompt-file p.txt --origin format_fixture --author "..." --purpose "..."
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

import argparse
import hashlib
import json
import sys
from pathlib import Path

REPLY_FILE_SCHEMA = "sitin-generation-reply/1"
ORIGIN_DELEGATED = "delegated_model_reply"
ORIGIN_CAPTURED = "model_capture"
ORIGIN_FIXTURE = "format_fixture"


def main() -> int:
    parser = argparse.ArgumentParser(description="封装委派/夹具回复文件")
    parser.add_argument("--raw", required=True, help="回复原文文件（逐字）")
    parser.add_argument("--out", required=True)
    parser.add_argument("--prompt-file", required=True,
                        help="工具产出的 prompt.txt（其字节哈希即 prompt_sha256）")
    parser.add_argument("--origin", required=True,
                        choices=(ORIGIN_DELEGATED, ORIGIN_CAPTURED, ORIGIN_FIXTURE))
    parser.add_argument("--provider", default=None)
    parser.add_argument("--model", default=None)
    parser.add_argument("--captured-at", default=None, help="墙钟 UTC 时间")
    parser.add_argument("--delegator", default=None)
    parser.add_argument("--author", default=None, help="origin=format_fixture 时必填")
    parser.add_argument("--purpose", default=None, help="origin=format_fixture 时必填")
    parser.add_argument("--note", default=None)
    args = parser.parse_args()

    raw_path = Path(args.raw)
    prompt_path = Path(args.prompt_file)
    if not raw_path.is_file() or not prompt_path.is_file():
        print("输入文件不存在", file=sys.stderr)
        return 2
    reply = raw_path.read_text(encoding="utf-8")
    prompt_sha = hashlib.sha256(prompt_path.read_bytes()).hexdigest()
    payload = {
        "schema": REPLY_FILE_SCHEMA,
        "origin": args.origin,
        "prompt_sha256": prompt_sha,
        "reply": reply,
        "provider": args.provider,
        "model": args.model,
        "captured_at_utc": args.captured_at,
        "delegator": args.delegator,
        "author": args.author,
        "purpose": args.purpose,
        "note": args.note,
    }
    if args.origin != ORIGIN_FIXTURE and not (args.provider and args.model
                                              and args.captured_at):
        print("origin={0} 必须给出 --provider/--model/--captured-at".format(args.origin),
              file=sys.stderr)
        return 2
    if args.origin == ORIGIN_FIXTURE and not (args.author and args.purpose):
        print("origin=format_fixture 必须给出 --author/--purpose", file=sys.stderr)
        return 2
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"out": str(out), "prompt_sha256": prompt_sha,
                      "reply_chars": len(reply),
                      "reply_sha256": hashlib.sha256(reply.encode()).hexdigest()},
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
