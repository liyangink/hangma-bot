"""只纠正模型声明的父代ID；保存原失败，算法源码逐字节不变，无新API。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t186-incremental-opportunity-repair-1'

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
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PRIOR = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t185-evidence-prioritized-joker-evolution-1')
sys.path.insert(0, str(PRIOR))
from common import pin, save
from hangma_bot.policy.action_value_executor import ActionValueExecutor
from hangma_bot.offline.vip_eoh_generate import (VipEohBatch, build_vip_eoh_prompt,
    load_vip_parents, parse_vip_eoh_reply, run_vip_eoh_generate, legacy_generation_tools)


def require(condition, message):
    """身份来源不唯一、额外文字变动或源码变动都拒绝本次修复。"""
    if not condition:
        raise ValueError(message)


def digest(raw):
    """UTF8原字节摘要；不把改过的回复当作原API回复。"""
    return hashlib.sha256(raw.encode()).hexdigest()


def main():
    """有明确实际父代绑定才允许纠正一项非执行字段；通过后仍未准入。"""
    batch = VipEohBatch.read(_project_file(_PROJECT_ROOT, HERE / "AUTHOR-BATCH.json"))
    parent = _project_file(_PROJECT_ROOT, PRIOR / "AUTHOR-incremental-model-output")
    parents = load_vip_parents([parent], batch)
    original = _project_file(_PROJECT_ROOT, HERE / "AUTHOR-resource-release-model-output")
    record = json.loads((original / "generation.json").read_text())
    raw = (original / "reply.txt").read_text()
    require(record["status"] == "failed" and record["backend"] == "api" and
            record["error"]["phase"] == "reply_validation" and not record["reply_redacted"] and
            record["reply"]["finish_reason"] == "stop" and record["reply_sha256"] == digest(raw),
            "不是完整未脱敏的原API回复失败")
    feedback = (_project_file(_PROJECT_ROOT, HERE / "AUTHOR-REPAIR-FEEDBACK.txt")).read_text()
    packet, _ = build_vip_eoh_prompt(batch, "m1", parents, feedback)
    require(digest(packet.text) == record["prompt_sha256"], "本次原提示词已漂移，不能换提示词回放")
    metadata = json.loads(re.search(r"```json\s*\n(.*?)\n```", raw, re.S).group(1))
    require(metadata["operator"] == "m1" and len(metadata["parent_differences"]) == 1, "父代声明不唯一")
    wrong = metadata["parent_differences"][0]["candidate_id"]
    correct = parents[0]["identity"]["candidate_id"]
    require(type(wrong) is str and len(wrong) == 64 and wrong != correct and raw.count(wrong) == 1,
            "不能限定为一项错误ID")
    try:
        parse_vip_eoh_reply(raw, "m1", parents)
    except Exception as error:
        require(str(error) == "逐父差异身份、顺序或预期标签不符", "原拒绝原因不是本次身份字段")
    else:
        raise ValueError("原回复已经通过，不需要改写")
    repaired = raw.replace(wrong, correct, 1)
    parsed = parse_vip_eoh_reply(repaired, "m1", parents)
    original_code = re.search(r"```python\s*\n(.*?)\n```", raw, re.S).group(1)
    require(parsed["source_raw"] == original_code, "修复改变了算法源码")
    ActionValueExecutor(parsed["source"], max_operations=batch.max_operations,
                        max_local_collection_size=batch.projection_limits.max_nodes)
    proof = {"schema": "t186-nonexecutable-parent-id-repair/1", "complete": True,
        "original_generation_pin": pin(original / "generation.json"), "original_reply_pin": pin(original / "reply.txt"),
        "original_api_status_unchanged": "failed", "original_actual_API_calls": 1, "new_API_calls": 0,
        "changed_fields": ["mechanism.parent_differences[0].candidate_id"],
        "before": wrong, "after": correct, "identity_authority": "实际请求中唯一formal_parent，不依据模型猜测",
        "original_source_raw_sha256": digest(original_code), "repaired_source_raw_sha256": digest(parsed["source_raw"]),
        "executable_source_unchanged": True, "is_entire_reply_raw_model_output": False,
        "is_algorithm_source_raw_model_output": True, "repaired_reply_sha256": digest(repaired),
        "strength_or_mechanical_admission": False}
    save(_project_file(_PROJECT_ROOT, HERE / "REPLY-METADATA-REPAIR.json"), proof)
    tools = legacy_generation_tools()
    envelope = _project_file(_PROJECT_ROOT, HERE / "METADATA-REPAIRED-REPLAY.json")
    save(envelope, {"schema": tools.REPLY_FILE_SCHEMA, "origin": tools.ORIGIN_CAPTURED,
        "provider": record["reply"]["provider"], "model": record["reply"]["model"],
        "captured_at_utc": record["reply"]["captured_at_utc"], "prompt_sha256": record["prompt_sha256"],
        "reply": repaired, "finish_reason": "stop", "usage": {},
        "note": "原API算法源码，主机纠正唯一父代ID的派生回放；不是第二次作者输出或原回复原字节",
        "derivation": proof})
    out = _project_file(_PROJECT_ROOT, HERE / "AUTHOR-resource-release-metadata-repaired")
    result = run_vip_eoh_generate(batch_file=_project_file(_PROJECT_ROOT, HERE / "AUTHOR-BATCH.json"), out_dir=out,
        operator="m1", backend="replay", parent_paths=[parent], feedback=feedback, reply_file=envelope)
    require(result["status"] == "loaded_not_admitted" and result["identity_stable"], "派生回放未装载")
    save(out / "DERIVATION.json", {**proof, "derived_generation_pin": pin(out / "generation.json"),
        "derived_reply_pin": pin(out / "reply.txt"), "repair_script_pin": pin(Path(__file__))})
    print(json.dumps({"status": result["status"], "source_unchanged": True, "new_API_calls": 0,
                      "candidate_id": result["identity"]["candidate_id"]}), flush=True)


if __name__ == "__main__":
    main()
