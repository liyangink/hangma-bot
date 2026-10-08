"""第二结构批次唯一合同修复：仅修 T1/T2/T4 的父代零效应和触发退化。"""
from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution'

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
import sys
from pathlib import Path


HERE = Path(__file__).resolve().parent
ROUTE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15')
ADMISSION = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/v4-impl/r9-admission')
for path in (_project_file(_PROJECT_ROOT, ROUTE / "tools"), _project_file(_PROJECT_ROOT, ADMISSION / "p25-headless"),
             _project_file(_PROJECT_ROOT, ADMISSION / "p25-dev-cards"), HERE):
    sys.path.insert(0, str(path))

import criterion  # noqa: E402
import dispatch_headless as dispatch  # noqa: E402
import sitin_generate as gen  # noqa: E402
import structural_author_batch as first  # noqa: E402
import structural_author_batch_2 as batch2  # noqa: E402


BATCH = batch2.BATCH
TASKS = ("T1", "T2", "T4")
EXPECTED_CONFIG = batch2.EXPECTED_CONFIG
PARENT = batch2.S3


PROBLEMS = {
    "T1": (
        "零配置相对指定S3父代仍改变27/226个分数和2个首选；六配置在226视图上的分数/首选签名完全相同，"
        "说明要求两个可比分支动作的门从未打开。修复必须让零配置逐分回到S3父代；非零结构不得要求"
        "窗口存在多个分支动作，可利用单个动作内部多个分支的相对差、分支分散度或在无可比证据时精确保留父代。"
    ),
    "T2": (
        "零配置相对指定S3父代仍改变27/226个分数和2个首选，因为参数全零回到了V2而非S3。"
        "保留‘直接牌效存在时选择性关闭/收缩后续项’主结构，但零配置必须逐分恢复S3父代；"
        "至少一个非零配置应在父代fbv触发的视图产生新的分数或首选差异。"
    ),
    "T4": (
        "零配置相对指定S3父代仍改变27/226个分数和2个首选，因为FB_TIE_STEP=0回到了V2。"
        "保留序数/破平简化主结构，但零配置必须逐分恢复S3父代；非零配置保持序数简化并产生新行为。"
    ),
}


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def prepare() -> None:
    root = BATCH / "repair-prompts"
    if root.exists():
        raise SystemExit("第二批修复提示已存在；拒绝覆盖")
    parent = PARENT.read_text(encoding="utf-8")
    rows = []
    for task_id in TASKS:
        candidate = (BATCH / f"generations/{task_id}/candidate.py").read_text(encoding="utf-8")
        parts = [
            "这是本题唯一一次合同修复。不得换成第二种研究方向，不得根据效果数据调参。",
            "",
            "【机械预检发现的问题】", PROBLEMS[task_id],
            "",
            "【必须同时满足】",
            "- 以原首答为主结构做最小修复；源码第一行仍是唯一STRUCTURE_SPACE_JSON。",
            "- zero_effect必须在全部合法输入上逐分等价于下列指定S3父代，包括状态、胡排序层、未知锚定；trace/reason可不同。",
            "- 六配置完整互异并包含zero_effect；至少一个非零配置必须具有可执行的新结构，不能六配置行为恒等。",
            "- 不读取H/M、隐藏状态、未来牌墙、实验根或结果；support不是概率；新增值有界。",
            "- 只输出：花括号内一句话；四字段严格JSON围栏；一个完整python围栏。完整源码优先，建议不超过430行。",
            "",
            "【原首答源码】", gen.FENCE + "python", candidate.rstrip("\n"), gen.FENCE,
            "", "【指定S3父代源码；zero_effect必须回到这里】",
            gen.FENCE + "python", parent.rstrip("\n"), gen.FENCE,
            "", "现在直接输出修复后的四字段和完整源码，不写推理过程。",
        ]
        prompt = "\n".join(parts)
        target = root / task_id
        target.mkdir(parents=True, exist_ok=True)
        (target / "prompt.txt").write_text(prompt, encoding="utf-8")
        rows.append({"task": task_id, "prompt_sha256": first.sha256_text(prompt),
                     "prompt_chars": len(prompt), "problem": PROBLEMS[task_id]})
    write_json(BATCH / "repair-manifest.json", {
        "schema": "r10-structural-repair/2", "tasks": rows,
        "expected_request_config": EXPECTED_CONFIG, "max_repairs_per_task": 1,
        "closed_without_repair": ["T3"],
        "reason": "T1/T2/T4违反指定父代零效应；T3只是未见首选变化，不属于合同修复资格",
    })
    print(json.dumps({"status": "REPAIR_PREPARED", "tasks": rows}, ensure_ascii=False, indent=2))


def verify_prompts() -> list[str]:
    manifest = json.loads((BATCH / "repair-manifest.json").read_text(encoding="utf-8"))
    result = []
    for row in manifest["tasks"]:
        text = (BATCH / "repair-prompts" / row["task"] / "prompt.txt").read_text(encoding="utf-8")
        if first.sha256_text(text) != row["prompt_sha256"]:
            raise ValueError("修复提示漂移：" + row["task"])
        result.append(row["task"])
    return result


def call() -> None:
    task_ids = verify_prompts()
    if (BATCH / "repair-replies").exists():
        raise SystemExit("修复回复已存在；拒绝第二次修复")
    dispatch._expected_request_config = lambda _package: dict(EXPECTED_CONFIG)
    report = dispatch.dispatch(
        BATCH, task_ids, BATCH / "repair-replies", BATCH / "plan-repair.json",
        model_patch=str(BATCH / "route.patch.yml"), timeout_s=900, concurrency=2,
        prompt_dir=BATCH / "repair-prompts", kind="structural-repair-2")
    rows, problems = [], []
    for call_row in sorted(report["calls"], key=lambda item: item["task"]):
        usage = criterion.usage_of(call_row.get("run_id"))
        values = usage.get("usage") or {}
        clean = (call_row.get("exit_code") == 0 and call_row.get("protocol_ok") is True
                 and call_row.get("request_config") == EXPECTED_CONFIG
                 and usage.get("source_status") == "OK"
                 and isinstance(values.get("inputTokens"), int)
                 and isinstance(values.get("outputTokens"), int)
                 and values["inputTokens"] <= 196608 and values["outputTokens"] <= 32768)
        rows.append({"task": call_row["task"], "run_id": call_row.get("run_id"),
                     "observed_config": call_row.get("request_config"),
                     "protocol_ok": call_row.get("protocol_ok"),
                     "exit_code": call_row.get("exit_code"), "usage": usage,
                     "ingestable_channel": clean})
        if not clean:
            problems.append(call_row["task"])
    write_json(BATCH / "repair-call-usage.json", {
        "schema": "r10-structural-call-usage/2", "calls": rows,
        "total_input_tokens": sum((row["usage"].get("usage") or {}).get("inputTokens", 0)
                                  for row in rows),
        "total_output_tokens": sum((row["usage"].get("usage") or {}).get("outputTokens", 0)
                                   for row in rows),
        "problems": problems,
    })
    print(json.dumps({"status": "REPAIR_COMPLETE_WITH_PROBLEMS" if problems
                      else "REPAIR_COMPLETE", "problems": problems}, ensure_ascii=False))


def ingest() -> None:
    task_ids = verify_prompts()
    usage = json.loads((BATCH / "repair-call-usage.json").read_text(encoding="utf-8"))
    by_task = {row["task"]: row for row in usage["calls"]}
    rows = []
    for task_id in task_ids:
        raw = (BATCH / "repair-replies" / f"{task_id}.txt").read_text(encoding="utf-8")
        parsed = gen.parse_action_value_reply(raw)
        code = parsed.get("code") or ""
        precheck = gen.precheck_action_value_candidate(code) if code else {
            "ok": False, "problems": ["没有源码"]}
        try:
            space = first.validate_space(code) if code else {
                "ok": False, "problems": ["没有参数空间"]}
        except (SyntaxError, ValueError) as exc:
            space = {"ok": False, "problems": [f"参数空间异常：{type(exc).__name__}: {exc}"]}
        target = BATCH / f"generations/{task_id}/repair"
        target.mkdir(parents=True, exist_ok=True)
        (target / "reply_raw.txt").write_text(raw, encoding="utf-8")
        if code:
            (target / "candidate.py").write_text(code.rstrip("\n") + "\n", encoding="utf-8")
        write_json(target / "parsed.json", {
            key: value for key, value in parsed.items() if key != "code"
        } | ({"code_sha256": first.sha256_text(code)} if code else {}))
        write_json(target / "precheck.json", precheck)
        write_json(target / "structure-space.json", space)
        accepted = (by_task.get(task_id, {}).get("ingestable_channel") is True
                    and parsed.get("status") == "ok" and precheck.get("ok") is True
                    and space.get("ok") is True)
        row = {"task": task_id, "parse_status": parsed.get("status"),
               "static_precheck": precheck.get("ok"), "structure_space": space.get("ok"),
               "accepted_for_behavior_preflight": accepted,
               "code_sha256": first.sha256_text(code) if code else None,
               "problems": list(parsed.get("problems") or [])
                           + list(precheck.get("problems") or [])
                           + list(space.get("problems") or [])}
        write_json(target / "record.json", row)
        rows.append(row)
    write_json(BATCH / "repair-ingest-summary.json", {
        "schema": "r10-structural-repair-ingest/2", "tasks": rows,
        "accepted": [row["task"] for row in rows if row["accepted_for_behavior_preflight"]],
        "closed": [row["task"] for row in rows if not row["accepted_for_behavior_preflight"]],
        "effect_evaluation_started": False,
    })
    print(json.dumps(json.loads((BATCH / "repair-ingest-summary.json").read_text(encoding="utf-8")),
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("prepare", "call", "ingest"))
    args = parser.parse_args()
    {"prepare": prepare, "call": call, "ingest": ingest}[args.operation]()
