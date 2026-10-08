"""根签收不可变原答后做标准解析与装载；不评分、不改候选、不另调模型。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t25-public-assistance-cost-control-author-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
import hashlib
import json
from pathlib import Path
from datetime import datetime, timezone

B = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t25-public-assistance-cost-control-author-1')
P = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t24-discard-route-portfolio-author-1/S01-model-output')


def pin(path):
    raw = path.read_bytes()
    return {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def write(name, value):
    with (_project_file(_PROJECT_ROOT, B / name)).open("x") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def main():
    delivery = json.loads((_project_file(_PROJECT_ROOT, B / "ROOT-AUTHOR-DELIVERY.json")).read_bytes())
    assert delivery["status"] == "FINAL_ANSWER_delivered_one_original"
    start = json.loads((_project_file(_PROJECT_ROOT, B / "ROOT-AUTHOR-START.json")).read_bytes())
    for path, expected in start["files"].items():
        assert pin(Path(path)) == expected, path
    for name, expected in delivery["files"].items():
        assert pin(_project_file(_PROJECT_ROOT, B / name)) == expected, name
    write("ROOT-AUTHOR-REPLY-FIRST-SEAL.json", {
        "schema": "root-author-reply-first-seal/1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "files": {str(_project_file(_PROJECT_ROOT, B / name)): pin(_project_file(_PROJECT_ROOT, B / name)) for name in ("RAW-REPLY.txt", "candidate.py", "STATIC-CHECKS.json")},
        "actual_author_delegations": 1, "requested_model": "gpt-6.1-sol",
        "requested_reasoning_effort": "max", "actual_backend_model_and_tokens": "unknown",
        "business_calls": 0, "repair_calls": 0})
    from hangma_bot.offline.vip_eoh_generate import (
        VipEohBatch, load_vip_parents, parse_vip_eoh_reply, build_vip_eoh_prompt)
    from hangma_bot.policy.action_value_executor import ActionValueExecutor
    batch = VipEohBatch.read(_project_file(_PROJECT_ROOT, B / "S01-generation.batch.json"))
    parents = load_vip_parents([P], batch)
    raw = (_project_file(_PROJECT_ROOT, B / "RAW-REPLY.txt")).read_text()
    parsed = parse_vip_eoh_reply(raw, "m1", parents)
    assert parsed["source_raw"].encode() == (_project_file(_PROJECT_ROOT, B / "candidate.py")).read_bytes().rstrip(b"\n")
    assert parsed["source"].strip() == (_project_file(_PROJECT_ROOT, B / "candidate.py")).read_text().strip()
    assert len(parsed["source"].encode()) <= 65536
    ActionValueExecutor(parsed["source"], max_operations=batch.max_operations)
    emitted = json.loads((_project_file(_PROJECT_ROOT, B / "S01-prompt-emission/generation.json")).read_text())
    feedback = (_project_file(_PROJECT_ROOT, B / "FROZEN-FEEDBACK.txt")).read_text()
    packet, _ = build_vip_eoh_prompt(batch, "m1", parents, feedback)
    assert packet.sha256 == emitted["prompt_sha256"] == pin(_project_file(_PROJECT_ROOT, B / "S01-prompt-emission/prompt.txt"))["sha256"]
    assert hashlib.sha256(feedback.encode()).hexdigest() == emitted["feedback_sha256"]
    write("ROOT-LOAD-PREFLIGHT.json", {
        "schema": "t25-load-preflight/1", "status": "parser_and_executor_constructor_pass_no_scoring",
        "parent_candidate_id": parents[0]["identity"]["candidate_id"],
        "parsed_source_sha256": hashlib.sha256(parsed["source"].encode()).hexdigest(),
        "raw_code_source_sha256": pin(_project_file(_PROJECT_ROOT, B / "candidate.py"))["sha256"],
        "emitted_prompt_sha256": emitted["prompt_sha256"],
        "frozen_feedback_sha256": hashlib.sha256(feedback.encode()).hexdigest(),
        "source_raw_byte_identity": True, "reply_format_version": parsed["reply_format_version"],
        "actual_business_scores": 0, "new_author_calls": 0})
    write("REPLAY-ENVELOPE.json", {
        "schema": "sitin-generation-reply/1",
        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
        "origin": "delegated_model_reply", "provider": "codex-collaboration", "model": "unknown",
        "delegator": "/root via /root/t25_sol_max_public_assistance_cost_control_author",
        "finish_reason": "stop", "prompt_sha256": emitted["prompt_sha256"], "reply": raw,
        "note": "One delivered immutable original. stop is root delivery attestation, not vendor finish metadata. Backend and tokens unknown. Replay makes no new model call."})
    print(json.dumps({"status": "preflight_pass", "source_raw": pin(_project_file(_PROJECT_ROOT, B / "candidate.py")),
                      "prompt_sha256": emitted["prompt_sha256"]}))


if __name__ == "__main__":
    main()
