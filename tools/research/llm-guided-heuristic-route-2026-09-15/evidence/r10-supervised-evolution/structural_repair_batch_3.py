"""第三结构批次唯一通道修复：缩短题面，重交两个耗尽输出上限的作者题。"""
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
import structural_author_batch_3 as batch3  # noqa: E402


BATCH = batch3.BATCH
TASKS = ("C1", "C2")
REPAIR_CONFIG = {
    "provider": "zai-coding-cn",
    "model": "glm-5.3",
    "reasoningEffort": "medium",
    "maxTokens": 32768,
}
HIGH_RETRY_CONFIG = {
    "provider": "zai-coding-cn",
    "model": "glm-5.3",
    "reasoningEffort": "high",
    "maxTokens": 32768,
}


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def failure_evidence() -> dict:
    usage = json.loads((BATCH / "initial-call-usage.json").read_text(encoding="utf-8"))
    by_task = {row["task"]: row for row in usage["calls"]}
    for task_id in TASKS:
        row = by_task.get(task_id) or {}
        values = (row.get("usage") or {}).get("usage") or {}
        reply = BATCH / "replies" / f"{task_id}.txt"
        if not (
            row.get("exit_code") == 1
            and row.get("protocol_ok") is True
            and row.get("ingestable_channel") is False
            and values.get("outputTokens") == 32768
            and reply.exists()
            and reply.stat().st_size == 0
        ):
            raise ValueError(f"{task_id}不是已证明的输出上限耗尽，拒绝通道修复")
    return by_task


def prepare() -> None:
    failures = failure_evidence()
    root = BATCH / "repair-prompts"
    if root.exists():
        raise SystemExit("第三批修复提示已存在；拒绝覆盖")
    p = batch3.parents()
    reflection = (BATCH / "reflection-replies/R0.txt").read_text(encoding="utf-8").strip()
    rows = []
    compact_contract = """【冻结机器合同】
- 这是上次输出耗尽后的唯一通道修复，不得换研究方向，不得声称已经提分。
- 只输出一个完整 score_actions(view)；不得 import、读工具/文件/网络/时间/随机源。
- 第一行必须是唯一的 `# STRUCTURE_SPACE_JSON: <严格JSON>`。JSON恰含parameters、zero_effect、configs；参数1—3个模块级数值常数；configs恰好六个完整互异映射并含zero_effect；默认常数等于其中一组。
- zero_effect必须在全部合法输入上逐分等价于后附稳定V2，包括胡排序、未知锚定、ABSTAIN和动作集合；trace文字可不同。
- 新结构只在phase=response_chi且同窗同时有已知chi/pass时触发；其他窗口精确退化V2。不能读取H/M、seed、根、终局、WorldState、隐藏牌墙或对手暗牌。
- support/remaining_estimate是未见枚数估计，不是概率；未知/None/布尔不得当0或数值。
- 只读family_progress_entries的family/progress/route_status结构字段，不解析basis中文；七对关闭不得写成固定禁止吃。
- 新增项必须有界、可消融并在trace中记录触发、参数和实际增减分；不能重做原FBV四维邻域。
- 禁止生成器表达式、lambda、eval/exec/open、属性反射和模块级可变状态。使用直白for循环，完整源码不超过280行。
- 先直接形成最终答案，不写内部推理；四字段每项不超过180个汉字。
"""
    for task_id in TASKS:
        spec = batch3.TASKS[task_id]
        parts = [
            "上一次调用已经精确耗尽32768输出token且没有最终答案。现在用更短题面重交同一题。",
            "请把推理压缩在内部，立即给最终四字段和完整代码；不要复述父代或证据。",
            "", "【同一冻结任务】",
            f"任务={task_id} {spec['name']}",
            f"目标={spec['objective']}",
            f"变更点={spec['change']}",
            f"假设={spec['hypothesis']}",
            "", compact_contract,
            "【已验证的短期反思；只是研究建议，不是规则或动作标签】",
            reflection,
            "【唯一零效应父代：稳定V2逐字源码】",
            f"sha256={p['v2']['code_sha256']}",
            gen.FENCE + "python", p["v2"]["code"].rstrip("\n"), gen.FENCE,
            "", gen._av_output_format(),
        ]
        prompt = "\n".join(parts)
        target = root / task_id
        target.mkdir(parents=True, exist_ok=True)
        (target / "prompt.txt").write_text(prompt, encoding="utf-8")
        rows.append({
            "task": task_id,
            "failure_run_id": failures[task_id]["run_id"],
            "failure_output_tokens": 32768,
            "prompt_sha256": first.sha256_text(prompt),
            "prompt_chars": len(prompt),
            "config": REPAIR_CONFIG,
        })
    settings = """# R10 第三结构批次唯一通道修复；缩短题面并降低无效长推理。
llm-pi-ai:
  providers:
    zai-coding-cn:
      apiKeyEnv: ZAI_CODING_CN_API_KEY
      models:
        - id: glm-5.3
          name: GLM-5.3
          contextWindow: 1000000
          maxTokens: 32768

agent-default-model:
  provider: zai-coding-cn
  model: glm-5.3
  reasoningEffort: medium
"""
    (BATCH / "repair-settings.yaml").write_text(settings, encoding="utf-8")
    (BATCH / "repair-route.patch.yml").write_text(
        "- id: settings\n  config:\n    path: " + str(BATCH / "repair-settings.yaml")
        + "\n    watch: false\n- id: agent-default-model\n  config:\n"
        + "    provider: zai-coding-cn\n    model: glm-5.3\n",
        encoding="utf-8",
    )
    write_json(BATCH / "repair-manifest.json", {
        "schema": "r10-structural-channel-repair/3",
        "reason": "两题协议正常但均精确耗尽32768输出token且零答案；缩短题面并降至medium",
        "max_repairs_per_task": 1,
        "tasks": rows,
        "effect_evaluation_started": False,
    })
    print(json.dumps({"status": "REPAIR_PREPARED", "tasks": rows},
                     ensure_ascii=False, indent=2))


def verify_prompts() -> list[str]:
    manifest = json.loads((BATCH / "repair-manifest.json").read_text(encoding="utf-8"))
    result = []
    for row in manifest["tasks"]:
        prompt = (BATCH / "repair-prompts" / row["task"] / "prompt.txt").read_text(encoding="utf-8")
        if first.sha256_text(prompt) != row["prompt_sha256"]:
            raise ValueError("修复提示摘要漂移：" + row["task"])
        result.append(row["task"])
    return result


def call() -> None:
    task_ids = verify_prompts()
    replies = BATCH / "repair-replies"
    if replies.exists():
        raise SystemExit("第三批修复回复已存在；拒绝第二次修复")
    dispatch._expected_request_config = lambda _package: dict(REPAIR_CONFIG)
    report = dispatch.dispatch(
        BATCH, task_ids, replies, BATCH / "plan-repair.json",
        model_patch=str(BATCH / "repair-route.patch.yml"), timeout_s=900, concurrency=1,
        prompt_dir=BATCH / "repair-prompts", kind="structural-channel-repair-3",
    )
    rows, problems = [], []
    for call_row in sorted(report["calls"], key=lambda item: item["task"]):
        usage = criterion.usage_of(call_row.get("run_id"))
        values = usage.get("usage") or {}
        clean = (
            call_row.get("exit_code") == 0
            and call_row.get("protocol_ok") is True
            and call_row.get("request_config") == REPAIR_CONFIG
            and usage.get("source_status") == "OK"
            and isinstance(values.get("inputTokens"), int)
            and isinstance(values.get("outputTokens"), int)
            and values["inputTokens"] <= 196608
            and values["outputTokens"] <= 32768
        )
        rows.append({
            "task": call_row["task"], "run_id": call_row.get("run_id"),
            "observed_config": call_row.get("request_config"),
            "protocol_ok": call_row.get("protocol_ok"),
            "exit_code": call_row.get("exit_code"), "usage": usage,
            "ingestable_channel": clean,
        })
        if not clean:
            problems.append(call_row["task"])
    write_json(BATCH / "repair-call-usage.json", {
        "schema": "r10-structural-call-usage/3", "calls": rows,
        "total_input_tokens": sum((row["usage"].get("usage") or {}).get("inputTokens", 0)
                                  for row in rows),
        "total_output_tokens": sum((row["usage"].get("usage") or {}).get("outputTokens", 0)
                                   for row in rows),
        "problems": problems,
    })
    print(json.dumps({"status": "REPAIR_COMPLETE_WITH_PROBLEMS" if problems
                      else "REPAIR_COMPLETE", "problems": problems}, ensure_ascii=False))


def call_high_retry() -> None:
    """仅在medium被本地适配器零请求拒绝后，用同一提示改回受支持的high。"""
    task_ids = verify_prompts()
    failed = json.loads((BATCH / "repair-call-usage.json").read_text(encoding="utf-8"))
    if sorted(failed.get("problems") or []) != sorted(task_ids):
        raise ValueError("medium尝试不是全量失败，拒绝配置重试")
    for row in failed.get("calls") or []:
        values = (row.get("usage") or {}).get("usage") or {}
        if values.get("inputTokens", 0) or values.get("outputTokens", 0):
            raise ValueError("medium尝试已有供应商用量，拒绝配置重试")
        if row.get("observed_config") is not None or row.get("protocol_ok") is not False:
            raise ValueError("medium失败不是请求前适配器拒绝")
    replies = BATCH / "repair-replies-high-retry"
    if replies.exists():
        raise SystemExit("high配置重试已存在；拒绝重复")
    settings = """# medium不受适配器支持后的零请求配置重试；提示逐字不变。
llm-pi-ai:
  providers:
    zai-coding-cn:
      apiKeyEnv: ZAI_CODING_CN_API_KEY
      models:
        - id: glm-5.3
          name: GLM-5.3
          contextWindow: 1000000
          maxTokens: 32768

agent-default-model:
  provider: zai-coding-cn
  model: glm-5.3
  reasoningEffort: high
"""
    (BATCH / "repair-high-settings.yaml").write_text(settings, encoding="utf-8")
    route = BATCH / "repair-high-route.patch.yml"
    route.write_text(
        "- id: settings\n  config:\n    path: " + str(BATCH / "repair-high-settings.yaml")
        + "\n    watch: false\n- id: agent-default-model\n  config:\n"
        + "    provider: zai-coding-cn\n    model: glm-5.3\n",
        encoding="utf-8",
    )
    dispatch._expected_request_config = lambda _package: dict(HIGH_RETRY_CONFIG)
    report = dispatch.dispatch(
        BATCH, task_ids, replies, BATCH / "plan-repair-high-retry.json",
        model_patch=str(route), timeout_s=900, concurrency=1,
        prompt_dir=BATCH / "repair-prompts", kind="structural-channel-repair-3-high-retry",
    )
    rows, problems = [], []
    for call_row in sorted(report["calls"], key=lambda item: item["task"]):
        usage = criterion.usage_of(call_row.get("run_id"))
        values = usage.get("usage") or {}
        clean = (
            call_row.get("exit_code") == 0
            and call_row.get("protocol_ok") is True
            and call_row.get("request_config") == HIGH_RETRY_CONFIG
            and usage.get("source_status") == "OK"
            and isinstance(values.get("inputTokens"), int)
            and isinstance(values.get("outputTokens"), int)
            and values["inputTokens"] <= 196608
            and values["outputTokens"] <= 32768
        )
        rows.append({
            "task": call_row["task"], "run_id": call_row.get("run_id"),
            "observed_config": call_row.get("request_config"),
            "protocol_ok": call_row.get("protocol_ok"),
            "exit_code": call_row.get("exit_code"), "usage": usage,
            "ingestable_channel": clean,
        })
        if not clean:
            problems.append(call_row["task"])
    write_json(BATCH / "repair-high-retry-call-usage.json", {
        "schema": "r10-structural-call-usage/3", "calls": rows,
        "retry_basis": "medium不受适配器支持；两题均request_headers=0且零token",
        "prompt_identity_preserved": True,
        "total_input_tokens": sum((row["usage"].get("usage") or {}).get("inputTokens", 0)
                                  for row in rows),
        "total_output_tokens": sum((row["usage"].get("usage") or {}).get("outputTokens", 0)
                                   for row in rows),
        "problems": problems,
    })
    print(json.dumps({"status": "HIGH_RETRY_COMPLETE_WITH_PROBLEMS" if problems
                      else "HIGH_RETRY_COMPLETE", "problems": problems}, ensure_ascii=False))


def ingest() -> None:
    task_ids = verify_prompts()
    high_retry = BATCH / "repair-high-retry-call-usage.json"
    usage_path = high_retry if high_retry.exists() else BATCH / "repair-call-usage.json"
    replies = BATCH / ("repair-replies-high-retry" if high_retry.exists() else "repair-replies")
    usage = json.loads(usage_path.read_text(encoding="utf-8"))
    by_task = {row["task"]: row for row in usage["calls"]}
    rows = []
    for task_id in task_ids:
        raw = (replies / f"{task_id}.txt").read_text(encoding="utf-8")
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
        accepted = (
            by_task.get(task_id, {}).get("ingestable_channel") is True
            and parsed.get("status") == "ok"
            and precheck.get("ok") is True
            and space.get("ok") is True
        )
        row = {
            "task": task_id, "parse_status": parsed.get("status"),
            "static_precheck": precheck.get("ok"), "structure_space": space.get("ok"),
            "accepted_for_behavior_preflight": accepted,
            "code_sha256": first.sha256_text(code) if code else None,
            "problems": list(parsed.get("problems") or [])
                        + list(precheck.get("problems") or [])
                        + list(space.get("problems") or []),
        }
        write_json(target / "record.json", row)
        rows.append(row)
    write_json(BATCH / "repair-ingest-summary.json", {
        "schema": "r10-structural-repair-ingest/3", "tasks": rows,
        "accepted": [row["task"] for row in rows if row["accepted_for_behavior_preflight"]],
        "closed": [row["task"] for row in rows if not row["accepted_for_behavior_preflight"]],
        "effect_evaluation_started": False,
    })
    print(json.dumps(json.loads((BATCH / "repair-ingest-summary.json").read_text(encoding="utf-8")),
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("prepare", "call", "call-high-retry", "ingest"))
    args = parser.parse_args()
    {"prepare": prepare, "call": call, "call-high-retry": call_high_retry,
     "ingest": ingest}[args.operation]()
