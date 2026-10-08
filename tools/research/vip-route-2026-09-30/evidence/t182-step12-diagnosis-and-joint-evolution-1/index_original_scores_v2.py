"""v2先用小头识别并去重外层记录，只对必要记录读取完整字段前缀。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t182-step12-diagnosis-and-joint-evolution-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
import ctypes
import fcntl
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time

from prepare_diagnostics import pin, save

HERE = Path(__file__).resolve().parent
ROOT = _PROJECT_ROOT
MAX_SEARCH_BYTES = 1536 * 1024 * 1024
MAX_EXCERPT_BYTES = 64 * 1024 * 1024
PREFIX_BYTES = 2 * 1024 * 1024
DECODER = json.JSONDecoder()


def field(prefix, name):
    """解码一个完整字段；值未在摘录内闭合时拒绝，不截断后冒充完整对象。"""
    hit = re.search(r'"' + re.escape(name) + r'"\s*:\s*', prefix)
    if hit is None:
        raise ValueError("字段不存在于有界前缀:" + name)
    value, _ = DECODER.raw_decode(prefix, hit.end())
    return value


def main():
    """沿闭合原件建立字节偏移小索引；不解析/复制巨大的重复规则树。"""
    os.nice(15)
    assert ctypes.CDLL(None).setiopolicy_np(0, 0, 3) == 0
    qualification = json.loads((_project_file(_PROJECT_ROOT, HERE / "SNAPSHOT-HU-QUALIFICATION.json")).read_text())
    groups = {}
    raw_reads = 0
    for case in qualification["cases"]:
        source = _project_file(_PROJECT_ROOT, ROOT / case["source"])
        ids = set()
        with gzip.open(source, "rb") as stream:
            for line in stream:
                raw_reads += len(line)
                assert raw_reads < 16 * 1024 * 1024
                row = json.loads(line)
                c = row.get("context") or {}
                if (c.get("round_no"), c.get("trigger_seq")) == (case["round_no"], case["trigger_seq"]):
                    if c.get("decision_id") is not None:
                        ids.add(c["decision_id"])
        assert len(ids) == 1
        did = next(iter(ids))
        # 原件路径由已核官方快照所在run/participant确定，不由model或外部文本注入。
        decision_file = source.parent.parent / "decisions.jsonl"
        groups.setdefault(decision_file, {})[did] = case
    search_bytes = sum(p.stat().st_size for p in groups)
    assert search_bytes <= MAX_SEARCH_BYTES
    target = _project_file(_PROJECT_ROOT, HERE / "ORIGINAL-SCORE-FIELDS.json")
    assert not target.exists()
    result = {"schema": "t182-indexed-original-score-fields/1", "cases": [],
        "search_file_bytes_upper_bound": search_bytes,
        "max_search_bytes": MAX_SEARCH_BYTES, "raw_protocol_read_bytes": raw_reads,
        "full_decision_input_rule_tree_recovered": False,
        "new_rules_scores_models_worlds_tables": 0,
        "scope": "original full observation/window and actual full returned plan; rule tree prefix excluded"}
    excerpt_bytes = 0
    with (_project_file(_PROJECT_ROOT, ROOT / ".private/t165-live-watchdog/postprocess.lock")).open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        for path, cases in groups.items():
            before = path.stat()
            command = ["rg", "--byte-offset", "--only-matching", "--fixed-strings"]
            for did in cases:
                command.extend(["-e", '"decision_id": "' + did + '"'])
            command.append(str(path))
            began = time.monotonic()
            found = subprocess.run(command, capture_output=True, timeout=60)
            assert found.returncode == 0 and len(found.stdout) < 128 * 1024
            located = {did: {} for did in cases}
            seen_record_starts = set()
            with path.open("rb") as stream:
                for hit in found.stdout.splitlines():
                    offset_text, term = hit.split(b":", 1)
                    offset = int(offset_text)
                    did = term.decode().split('"')[3]
                    assert did in cases
                    begin = max(0, offset - 2048)
                    stream.seek(begin)
                    raw = stream.read(4096)
                    excerpt_bytes += len(raw)
                    prefix_end = offset - begin
                    boundary = raw.rfind(b"\n", 0, prefix_end)
                    start = begin + boundary + 1 if boundary >= 0 else 0 if begin == 0 else None
                    if start is None:
                        continue  # 嵌套字段命中而非外层上下文，不作为记录来源。
                    if start in seen_record_starts:
                        continue
                    seen_record_starts.add(start)
                    stream.seek(start)
                    head = stream.read(8192)
                    excerpt_bytes += len(head)
                    header = head.decode("utf-8", errors="ignore")
                    context = field(header, "context")
                    kind = field(header, "kind")
                    if context.get("decision_id") != did or kind not in ("decision_input", "decision_planned"):
                        continue
                    if kind in located[did]:
                        assert located[did][kind]["offset"] == start
                        continue
                    stream.seek(start)
                    raw = stream.read(PREFIX_BYTES)
                    excerpt_bytes += len(raw)
                    assert excerpt_bytes <= MAX_EXCERPT_BYTES
                    # 摘录可能结束于UTF-8字符中间；仅丢末尾不完整字符，完整字段仍需闭合。
                    prefix = raw.decode("utf-8", errors="ignore")
                    if not prefix.startswith('{"schema_version"'):
                        continue
                    context = field(prefix, "context")
                    if context.get("decision_id") != did:
                        continue
                    case = cases[did]
                    assert (context["game_id"], context["round_no"], context["trigger_seq"]) == (
                        case["game_id"], case["round_no"], case["trigger_seq"])
                    kind = field(prefix, "kind")
                    if kind not in ("decision_input", "decision_planned"):
                        continue
                    if kind in located[did]:
                        assert located[did][kind]["offset"] == start
                        continue
                    record = {"offset": start, "prefix_bytes": len(raw),
                              "prefix_sha256": hashlib.sha256(raw).hexdigest(), "context": context}
                    if kind == "decision_input":
                        record.update(observation=field(prefix, "observation"),
                                      window_key=field(prefix, "window_key"),
                                      legal_candidates=field(prefix, "legal_candidates"))
                    else:
                        record.update(returned_plan=field(prefix, "returned_plan"),
                                      effective_candidates=field(prefix, "effective_candidates"),
                                      degraded_reasons=field(prefix, "degraded_reasons"))
                    located[did][kind] = record
            after = path.stat()
            assert (before.st_size, before.st_mtime_ns) == (after.st_size, after.st_mtime_ns)
            for did, fields in located.items():
                assert set(fields) == {"decision_input", "decision_planned"}
                case = cases[did]
                result["cases"].append({"game_id": case["game_id"], "round_no": case["round_no"],
                    "trigger_seq": case["trigger_seq"], "decision_id": did, "rule_config": case["rule_config"],
                    "source": str(path.relative_to(ROOT)), "source_file_bytes": before.st_size,
                    "rg_wall_seconds": time.monotonic() - began,
                    "records": fields, "source_protocol_pins": case["source_pins"]})
        result.update(complete=len(result["cases"]) == 3, excerpt_read_bytes=excerpt_bytes,
                      qualification_pin=pin(_project_file(_PROJECT_ROOT, HERE / "SNAPSHOT-HU-QUALIFICATION.json")))
        save(target, result)
    print(json.dumps({"complete": result["complete"], "cases": len(result["cases"]),
                      "search_file_bytes_upper_bound": search_bytes, "excerpt_bytes": excerpt_bytes}))


if __name__ == "__main__":
    try:
        main()
    except BaseException as error:
        failure = _project_file(_PROJECT_ROOT, HERE / "ORIGINAL-SCORE-FIELDS-FAILURE-02.json")
        if not failure.exists():
            save(failure, {"type": type(error).__name__, "message": str(error)})
        raise
