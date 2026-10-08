"""R14 第一代：用 GLM 5.3 生成两个针对 H/M 鲁棒性的完整启发式子代。"""

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
import datetime as dt
import hashlib
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
from hangma_bot.policy.action_value_seeds import ActionValueScorer  # noqa: E402


BATCH = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r14-robust-offspring-author-01-20260921')
V2 = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/v2-parent-revalidation-20260920/parent/generation/candidate.py')
HARD = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/strong-seeds-20260920/hard-sol-max/run/iterations/iter-02/generation/candidate.py')
RIVER = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/strong-seeds-20260920/river-sol-high/run/iterations/iter-01/generation/candidate.py')
MF1 = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/multifidelity-prospective-audit-01-20260921/result.json')
DIAG = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/hard-sol-max-m-failure-diagnosis-01-retry01-20260921/summary.json')
CHANGED = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/hard-sol-max-m-failure-diagnosis-01-retry01-20260921/changed-decisions.jsonl')

EXPECTED_CONFIG = {
    "provider": "zai-coding-cn",
    "model": "glm-5.3",
    "reasoningEffort": "max",
    "maxTokens": 32768,
}

REPAIR_CONFIG = {
    "provider": "zai-coding-cn",
    "model": "glm-5.3",
    "reasoningEffort": "high",
    "maxTokens": 32768,
}

TASKS = {
    "R1": {
        "name": "v2-anchored-claim-rebase",
        "objective": (
            "以稳定 V2 为可执行骨架，只把 hard-sol-max 中有完整公开后续分支支持的"
            "吃/碰权衡提炼成一个有界机制；普通弃牌、普通过牌、杠与胡在新机制不触发时"
            "必须精确退化到 V2 排序。"
        ),
        "direction": (
            "诊断显示最差 M 来源的 38 个改选全部由 hard-sol-max 的 direct_common_efficiency"
            "重写触发，没有一个由分支/路线权衡触发。不要继承它的全局 -120 向听刻度、"
            "分段 support_score、全局 option_score 或 wealth_score。只在 chi/peng 拥有完整"
            "followup_branches，且相对可见闭手基线的提速与七对/财神机会损失都可核时改变分数。"
        ),
        "companions": (HARD,),
    },
    "R2": {
        "name": "exclusive-discard-evidence-arbiter",
        "objective": (
            "以稳定 V2 为骨架，设计一个非叠加的弃牌证据裁决器：只有两个动作在 V2 主牌效"
            "同层且额外公开证据足够区分时才允许改选；弱证据精确退化到 V2。"
        ),
        "direction": (
            "把 hard-sol-max 的普通型/七对选择余地与 river-sol-high 的公开牌河机制视为"
            "相互竞争的证据来源，只能通过互斥触发或共同尺度选择一个，不能把两份奖励相加。"
            "不得使用 H/M 标签、来源根、座位效果或终局结果。新增项必须有界，并明确何时"
            "完全不改变 V2；诊断的 35 个 discard->discard 改选只说明全局重排风险，不是动作标签。"
        ),
        "companions": (HARD, RIVER),
    },
}

COMMON = """【R14 机器约束】
- 交付一份完整可执行的 score_actions(view) 源码，不要交补丁；不得 import、调用工具、文件、网络、时间或随机源。
- 只能读取 sitin-scoring-view/3 已投影的 PlayerObservation 与 HangmaRules 事实。不得读取 WorldState、隐藏牌墙、对手暗牌、H/M 标签、面板根、焦点座位效果或终局标签。
- 杭麻冻结边界：只允许自摸；财神、七对、副露资格、抓打圈、立即/条件结算继续由输入事实裁定。不得引入点炮、抢杠胡或其他规则。
- 必须保留全部合法动作、Hu 排序层、未知严格低于全部已知、全未知 ABSTAIN、拒绝动作过滤与有限数。None/布尔不能当数；support 不是概率，条件结算不是期望值。
- 只提出一个可消融的新结构。新结构不触发时，动作分数与稳定 V2 的相对排序必须精确退化；不得顺手重写父代其他刻度。
- trace 必须记录结构名、触发与否、证据、实际加减分和退化原因。说明要给触发、去重、手算例、反例与零效应移除方式。
- 不得宣称提分、通过、确认或可发布。模型只负责离线作者交付，后续所有效果由冻结模拟独立裁定。
"""


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def parent_record(path: Path, name: str) -> dict[str, str]:
    code = path.read_text(encoding="utf-8")
    return {"name": name, "path": str(path), "identity": sha256_text(code),
            "candidate_id": sha256_text(code), "thought": code.splitlines()[0],
            "code": code, "code_sha256": sha256_text(code)}


def diagnosis_facts() -> dict[str, object]:
    result = json.loads(MF1.read_text(encoding="utf-8"))
    summary = json.loads(DIAG.read_text(encoding="utf-8"))
    hard = next(row for row in result["candidate_summaries"]
                if row["candidate_id"] == "hard-sol-max")
    changed = [json.loads(line) for line in CHANGED.read_text(encoding="utf-8").splitlines()]
    return {
        "mf1": {
            "hard_sol_max": hard,
            "warning": "新开发来源且已用于选择；不是独立确认",
        },
        "consumed_m_failure_replay": {
            "source": "M/root03/focal-seat2",
            "baseline_stage_score": 89,
            "candidate_stage_score": -23,
            "views": summary["counts"]["views"],
            "preferred_changed": summary["counts"]["preferred_changed"],
            "transitions": {key.removeprefix("transition:"): value
                            for key, value in summary["counts"].items()
                            if key.startswith("transition:")},
            "selected_basis": summary["changed_candidate_basis"],
            "trace_aggregate": {
                "family_option_nonzero": sum(
                    (row["candidate_trace"].get("family_option") or 0) != 0 for row in changed),
                "route_alternative_present": sum(
                    row["candidate_trace"].get("route_alternative") is not None for row in changed),
                "family_adjustment_nonzero": sum(
                    (row["candidate_trace"].get("family_adjustment") or 0) != 0 for row in changed),
                "call_tradeoff_nonzero": sum(
                    (row["candidate_trace"].get("call_tradeoff") or 0) != 0 for row in changed),
            },
            "interpretation_limit": (
                "确定性复现只证明最差已消费 M 来源中的行为差异集中于全局直接刻度；"
                "不证明任一单窗动作正确，也不证明 H 增益来自何机制。"
            ),
        },
    }


def prompt_for(task_id: str, spec: dict[str, object], primary: dict[str, str]) -> str:
    payload = gen.render_action_value_task_contract(
        objective_summary=str(spec["objective"]),
        panel_boundary=(
            "后续监督器先做静态/算术/真实观察行为预检，再在全新 H/M 同牌山换座位来源上"
            "执行完整两桌；第一桌只排执行顺序，不能淘汰。"
        ),
        prompt_role=f"{task_id} {spec['name']}：H/M 鲁棒子代作者",
        parent=primary,
        feedback={
            "facts": json.dumps(diagnosis_facts(), ensure_ascii=False, indent=2),
            "associated_results": str(spec["direction"]),
            "mechanism_hypothesis": (
                "把已观察到的 H 专长与 M 退化分离：默认保留稳定 V2，只让一项公开、"
                "相容、强证据机制改变少数动作。"
            ),
        },
        budget_note="本题首答计一次调用；只允许后续一次固定语法/合同修复，不能借修复换机制。",
    )
    focus = {
        "objective": str(spec["objective"]),
        "change_point": str(spec["direction"]),
        "input_groups": [
            "actions", "actions[]", "actions[].useful_tiles",
            "actions[].standard_useful_tiles", "actions[].seven_pairs_useful_tiles",
            "actions[].followup_branches", "actions[].routes",
            "actions[].family_progress_entries", "visible_state",
            "visible_state.rule_state", "competition", "analysis_profile",
        ],
        "gate": "none", "guard": "full", "guard_reference": False,
        "examples": "output", "rules": "compact", "input_overview": "contract",
        "budget_note": "不得用开发效果数值选择常数或硬编码来源身份。",
    }
    packet = gen.build_action_value_card_prompt("m1", payload, focus)
    companions = []
    for index, path in enumerate(spec["companions"], start=1):
        code = Path(path).read_text(encoding="utf-8")
        companions.extend([
            f"【机制材料 {index}；只能提炼结构，不能继承其开发得分】",
            f"path={path}; sha256={sha256_text(code)}",
            gen.FENCE + "python", code.rstrip("\n"), gen.FENCE,
        ])
    output_block = gen._av_output_format()
    if packet.text.count(output_block) != 1:
        raise RuntimeError("无法定位唯一输出格式段")
    return packet.text.replace(
        output_block,
        COMMON + "\n\n" + "\n".join(companions) + "\n\n" + output_block)


def prepare() -> None:
    """冻结两个作者题面、父代、失败反馈和模型配置。"""

    if BATCH.exists():
        raise SystemExit("作者批已存在；拒绝覆盖")
    primary = parent_record(V2, "stable-v2")
    task_rows = []
    for task_id, spec in TASKS.items():
        text = prompt_for(task_id, spec, primary)
        target = _project_file(_PROJECT_ROOT, BATCH / "prompts" / task_id)
        target.mkdir(parents=True, exist_ok=True)
        (target / "prompt.txt").write_text(text, encoding="utf-8")
        task_rows.append({"task": task_id, "name": spec["name"],
                          "prompt_sha256": sha256_text(text), "prompt_chars": len(text)})
    settings = """llm-pi-ai:
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
  reasoningEffort: max
"""
    (_project_file(_PROJECT_ROOT, BATCH / "settings.yaml")).write_text(settings, encoding="utf-8")
    (_project_file(_PROJECT_ROOT, BATCH / "route.patch.yml")).write_text(
        "- id: settings\n  config:\n    path: " + str(_project_file(_PROJECT_ROOT, BATCH / "settings.yaml"))
        + "\n    watch: false\n- id: agent-default-model\n  config:\n"
        + "    provider: zai-coding-cn\n    model: glm-5.3\n", encoding="utf-8")
    write_json(_project_file(_PROJECT_ROOT, BATCH / "manifest.json"), {
        "schema": "r14-robust-offspring-author/1",
        "created_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "expected_request_config": EXPECTED_CONFIG,
        "tasks": task_rows,
        "inputs": {str(path): sha256(path) for path in (V2, HARD, RIVER, MF1, DIAG, CHANGED)},
        "effect_evaluation_started": False, "confirmation_reserved": 0,
    })
    write_json(_project_file(_PROJECT_ROOT, BATCH / "authorization.json"), {
        "schema": "sitin-authorization/1",
        "authorization_id": "r14-robust-offspring-author-01",
        "trusted": True, "issued_by": "lead",
        "issued_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "issuance_basis": (
            "用户授权zai-coding-cn GLM5.3在API上限前由root调度，并要求按文献复盘后的新目标推进"
        ),
        "max_initial_calls": 2, "max_repair_calls": 2, "max_total_calls": 4,
        "per_call_limits": {"tokens_input": 196608, "tokens_output": 32768},
        "effect_tables": 0, "confirmation_reserved": 0,
        "scope": "离线生成两个H/M鲁棒子代；不得确认、发布或修改规则",
    })
    (_project_file(_PROJECT_ROOT, BATCH / ".gitignore")).write_text("dispatch-ledger/\n", encoding="utf-8")
    print(json.dumps({"status": "PREPARED", "tasks": task_rows}, ensure_ascii=False, indent=2))


def verified_tasks() -> list[str]:
    manifest = json.loads((_project_file(_PROJECT_ROOT, BATCH / "manifest.json")).read_text(encoding="utf-8"))
    for path, expected in manifest["inputs"].items():
        if sha256(Path(path)) != expected:
            raise RuntimeError("作者输入摘要漂移：" + path)
    result = []
    for row in manifest["tasks"]:
        text = (_project_file(_PROJECT_ROOT, BATCH / "prompts" / row["task"] / "prompt.txt")).read_text(encoding="utf-8")
        if sha256_text(text) != row["prompt_sha256"]:
            raise RuntimeError("提示词摘要漂移：" + row["task"])
        result.append(row["task"])
    return result


def call() -> None:
    """执行两次冻结 GLM 5.3 max 作者调用并核对身份与用量。"""

    tasks = verified_tasks()
    if (_project_file(_PROJECT_ROOT, BATCH / "replies")).exists():
        raise SystemExit("回复目录已存在；拒绝重复调用")
    dispatch._expected_request_config = lambda _package: dict(EXPECTED_CONFIG)
    report = dispatch.dispatch(
        BATCH, tasks, _project_file(_PROJECT_ROOT, BATCH / "replies"), _project_file(_PROJECT_ROOT, BATCH / "plan-initial.json"),
        model_patch=str(_project_file(_PROJECT_ROOT, BATCH / "route.patch.yml")), timeout_s=1200, concurrency=1,
        prompt_dir=_project_file(_PROJECT_ROOT, BATCH / "prompts"), kind="r14-robust-offspring-initial")
    rows = []
    problems = []
    for item in sorted(report["calls"], key=lambda row: row["task"]):
        usage = criterion.usage_of(item.get("run_id"))
        values = usage.get("usage") or {}
        clean = (
            item.get("exit_code") == 0 and item.get("protocol_ok") is True
            and item.get("request_config") == EXPECTED_CONFIG
            and usage.get("source_status") == "OK"
            and isinstance(values.get("inputTokens"), int)
            and isinstance(values.get("outputTokens"), int)
            and values["inputTokens"] <= 196608 and values["outputTokens"] <= 32768
        )
        rows.append({"task": item["task"], "run_id": item.get("run_id"),
                     "exit_code": item.get("exit_code"), "protocol_ok": item.get("protocol_ok"),
                     "observed_config": item.get("request_config"), "usage": usage,
                     "ingestable_channel": clean})
        if not clean:
            problems.append(item["task"])
    write_json(_project_file(_PROJECT_ROOT, BATCH / "call-usage.json"), {
        "schema": "r14-robust-offspring-call-usage/1", "calls": rows,
        "problems": problems,
        "total_input_tokens": sum((row["usage"].get("usage") or {}).get("inputTokens", 0)
                                  for row in rows),
        "total_output_tokens": sum((row["usage"].get("usage") or {}).get("outputTokens", 0)
                                   for row in rows),
    })
    if problems:
        raise RuntimeError("作者通道或用量核对失败：" + ",".join(problems))
    print(json.dumps({"status": "CALLED", "tasks": tasks}, ensure_ascii=False))


def call_retry() -> None:
    """在零 token 传输失败后执行一次独立留痕重试。"""

    tasks = verified_tasks()
    failed = json.loads((_project_file(_PROJECT_ROOT, BATCH / "call-usage.json")).read_text(encoding="utf-8"))
    if failed.get("total_input_tokens") != 0 or failed.get("total_output_tokens") != 0:
        raise RuntimeError("首尝试已产生模型用量，不得作为零成本传输重试")
    if (_project_file(_PROJECT_ROOT, BATCH / "replies-retry01")).exists():
        raise SystemExit("重试回复目录已存在；拒绝重复调用")
    write_json(_project_file(_PROJECT_ROOT, BATCH / "authorization-retry01.json"), {
        "schema": "sitin-authorization/1",
        "authorization_id": "r14-robust-offspring-author-01-transport-retry01",
        "trusted": True, "issued_by": "lead",
        "issued_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "issuance_basis": "首尝试两任务均为TRANSPORT Connection error且输入/输出token均为0；原题原模型各重试一次",
        "max_initial_calls": 2, "max_repair_calls": 0, "max_total_calls": 2,
        "per_call_limits": {"tokens_input": 196608, "tokens_output": 32768},
        "effect_tables": 0, "confirmation_reserved": 0,
        "scope": "只重试冻结的R1/R2原题；不得改题、确认或发布",
    })
    dispatch._expected_request_config = lambda _package: dict(EXPECTED_CONFIG)
    report = dispatch.dispatch(
        BATCH, tasks, _project_file(_PROJECT_ROOT, BATCH / "replies-retry01"), _project_file(_PROJECT_ROOT, BATCH / "plan-initial-retry01.json"),
        model_patch=str(_project_file(_PROJECT_ROOT, BATCH / "route.patch.yml")), timeout_s=1200, concurrency=1,
        prompt_dir=_project_file(_PROJECT_ROOT, BATCH / "prompts"), kind="r14-robust-offspring-initial-retry01")
    rows = []
    problems = []
    for item in sorted(report["calls"], key=lambda row: row["task"]):
        usage = criterion.usage_of(item.get("run_id"))
        values = usage.get("usage") or {}
        clean = (
            item.get("exit_code") == 0 and item.get("protocol_ok") is True
            and item.get("request_config") == EXPECTED_CONFIG
            and usage.get("source_status") == "OK"
            and isinstance(values.get("inputTokens"), int)
            and isinstance(values.get("outputTokens"), int)
            and values["inputTokens"] <= 196608 and values["outputTokens"] <= 32768
        )
        rows.append({"task": item["task"], "run_id": item.get("run_id"),
                     "exit_code": item.get("exit_code"), "protocol_ok": item.get("protocol_ok"),
                     "observed_config": item.get("request_config"), "usage": usage,
                     "ingestable_channel": clean})
        if not clean:
            problems.append(item["task"])
    write_json(_project_file(_PROJECT_ROOT, BATCH / "call-usage-retry01.json"), {
        "schema": "r14-robust-offspring-call-usage/1", "calls": rows,
        "problems": problems,
        "total_input_tokens": sum((row["usage"].get("usage") or {}).get("inputTokens", 0)
                                  for row in rows),
        "total_output_tokens": sum((row["usage"].get("usage") or {}).get("outputTokens", 0)
                                   for row in rows),
        "retry_of": "call-usage.json",
    })
    if problems:
        raise RuntimeError("作者重试通道或用量核对失败：" + ",".join(problems))
    print(json.dumps({"status": "CALLED_RETRY01", "tasks": tasks}, ensure_ascii=False))


def ingest() -> None:
    """解析完整源码并执行静态白名单与受限加载预检。"""

    tasks = verified_tasks()
    usage_path = (_project_file(_PROJECT_ROOT, BATCH / "call-usage-retry01.json")
                  if (_project_file(_PROJECT_ROOT, BATCH / "call-usage-retry01.json")).exists()
                  else _project_file(_PROJECT_ROOT, BATCH / "call-usage.json"))
    reply_root = (_project_file(_PROJECT_ROOT, BATCH / "replies-retry01")
                  if (_project_file(_PROJECT_ROOT, BATCH / "replies-retry01")).exists()
                  else _project_file(_PROJECT_ROOT, BATCH / "replies"))
    usage = json.loads(usage_path.read_text(encoding="utf-8"))
    channel = {row["task"]: row["ingestable_channel"] for row in usage["calls"]}
    rows = []
    for task_id in tasks:
        raw = (reply_root / f"{task_id}.txt").read_text(encoding="utf-8")
        parsed = gen.parse_action_value_reply(raw)
        code = parsed.get("code") or ""
        precheck = gen.precheck_action_value_candidate(code) if code else {
            "ok": False, "problems": ["没有可预检源码"]}
        load_error = None
        if code and precheck.get("ok") is True:
            try:
                ActionValueScorer("r14-" + task_id, code)
            except Exception as exc:  # noqa: BLE001 - 证据中保留具体加载错误
                load_error = type(exc).__name__ + ": " + str(exc)
        accepted = (channel.get(task_id) is True and parsed.get("status") == "ok"
                    and precheck.get("ok") is True and load_error is None)
        target = _project_file(_PROJECT_ROOT, BATCH / "generations" / task_id)
        target.mkdir(parents=True, exist_ok=True)
        (target / "reply_raw.txt").write_text(raw, encoding="utf-8")
        if code:
            (target / "candidate.py").write_text(code.rstrip("\n") + "\n", encoding="utf-8")
        write_json(target / "parsed.json", {
            key: value for key, value in parsed.items() if key != "code"
        } | ({"code_sha256": sha256_text(code)} if code else {}))
        write_json(target / "precheck.json", precheck)
        row = {"task": task_id, "parse_status": parsed.get("status"),
               "static_precheck": precheck.get("ok"), "load_error": load_error,
               "accepted_for_behavior_preflight": accepted,
               "code_sha256": sha256_text(code) if code else None,
               "problems": list(parsed.get("problems") or [])
                           + list(precheck.get("problems") or [])
                           + ([load_error] if load_error else [])}
        write_json(target / "record.json", row)
        rows.append(row)
    write_json(_project_file(_PROJECT_ROOT, BATCH / "ingest-summary.json"), {
        "schema": "r14-robust-offspring-ingest/1", "rows": rows,
        "accepted_for_behavior_preflight": [
            row["task"] for row in rows if row["accepted_for_behavior_preflight"]],
        "repair_eligible": [row["task"] for row in rows
                            if not row["accepted_for_behavior_preflight"]],
        "effect_evaluation_started": False,
    })
    print(json.dumps(json.loads((_project_file(_PROJECT_ROOT, BATCH / "ingest-summary.json")).read_text()),
                     ensure_ascii=False, indent=2))


def prepare_r2_repair() -> None:
    """冻结 R2 输出截断后的唯一合同修复，不允许改变已形成机制。"""

    summary = json.loads((_project_file(_PROJECT_ROOT, BATCH / "ingest-summary.json")).read_text(encoding="utf-8"))
    if summary.get("repair_eligible") != ["R2"]:
        raise RuntimeError("R2 不是唯一修复资格")
    usage = json.loads((_project_file(_PROJECT_ROOT, BATCH / "call-usage-retry01.json")).read_text(encoding="utf-8"))
    r2_usage = next(row for row in usage["calls"] if row["task"] == "R2")
    values = r2_usage["usage"].get("usage") or {}
    if values.get("outputTokens") != 32768 or r2_usage.get("exit_code") == 0:
        raise RuntimeError("R2 不符合输出上限截断修复前提")
    target = _project_file(_PROJECT_ROOT, BATCH / "repair-prompts" / "R2")
    if target.exists():
        raise SystemExit("R2 修复题面已存在；拒绝覆盖")
    raw = (_project_file(_PROJECT_ROOT, BATCH / "replies-retry01/R2.txt")).read_text(encoding="utf-8")
    fixed_design = raw.split("\n\n", 1)[0].strip()
    v2 = V2.read_text(encoding="utf-8")
    prompt = "\n".join([
        "这是 R2 唯一一次合同修复。上次调用已达到 32768 输出 token 上限并截断；",
        "本次只能把已经形成的机制交付成完整短源码，不得改变机制、参数或触发条件。",
        "不要复述推理，不要使用工具。",
        "",
        "【已经形成并冻结的机制】",
        fixed_design,
        "",
        "【交付要求】",
        "- 严格输出：花括号内一句话；一个json围栏，恰含trigger/changed_branches/expected_direction/counterexample四个非空短字符串；一个完整python围栏。",
        "- 以稳定V2作最小修改，建议源码不超过320行；不触发时全部动作的相对排序与V2逐点相同。",
        "- 不得import；只能有一个score_actions(view)入口；保留合法动作、胡层、未知锚定、ABSTAIN和有限数。",
        "- 只读公开输入；不得使用H/M、根、座位效果、终局结果、WorldState、隐藏牌墙或对手暗牌。",
        "- 牌河只表示公开同牌深度，不代表点炮风险；本项目只允许自摸。support不是概率。",
        "- trace记录触发、互斥证据源、领先差和实际+0.04；不宣称提分、确认或发布。",
        "",
        "【稳定V2完整源码】",
        gen.FENCE + "python", v2.rstrip("\n"), gen.FENCE,
        "",
        "现在直接交付完整结果。",
    ])
    target.mkdir(parents=True)
    (target / "prompt.txt").write_text(prompt, encoding="utf-8")
    settings = """llm-pi-ai:
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
    (_project_file(_PROJECT_ROOT, BATCH / "settings-repair.yaml")).write_text(settings, encoding="utf-8")
    (_project_file(_PROJECT_ROOT, BATCH / "route.repair.patch.yml")).write_text(
        "- id: settings\n  config:\n    path: " + str(_project_file(_PROJECT_ROOT, BATCH / "settings-repair.yaml"))
        + "\n    watch: false\n- id: agent-default-model\n  config:\n"
        + "    provider: zai-coding-cn\n    model: glm-5.3\n", encoding="utf-8")
    write_json(_project_file(_PROJECT_ROOT, BATCH / "repair-manifest.json"), {
        "schema": "r14-r2-contract-repair/1",
        "reason": "R2 初答输出达到 32768 token 上限并在JSON说明中截断",
        "expected_request_config": REPAIR_CONFIG,
        "task": "R2", "prompt_sha256": sha256_text(prompt),
        "prompt_chars": len(prompt), "fixed_design_sha256": sha256_text(fixed_design),
        "source_reply_sha256": sha256_text(raw), "max_repairs": 1,
    })
    write_json(_project_file(_PROJECT_ROOT, BATCH / "authorization-repair01.json"), {
        "schema": "sitin-authorization/1",
        "authorization_id": "r14-r2-contract-repair01",
        "trusted": True, "issued_by": "lead",
        "issued_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "issuance_basis": "R2 首答已用满输出上限且形成明确机制；按预登记只补齐同机制完整合同",
        "max_initial_calls": 0, "max_repair_calls": 1, "max_total_calls": 1,
        "per_call_limits": {"tokens_input": 65536, "tokens_output": 32768},
        "effect_tables": 0, "confirmation_reserved": 0,
        "scope": "只补齐R2既定互斥弃牌证据裁决器；不得改变机制、确认或发布",
    })
    print(json.dumps({"status": "R2_REPAIR_PREPARED", "prompt_chars": len(prompt)},
                     ensure_ascii=False))


def call_r2_repair() -> None:
    """执行 R2 唯一合同修复并核对通道。"""

    manifest = json.loads((_project_file(_PROJECT_ROOT, BATCH / "repair-manifest.json")).read_text(encoding="utf-8"))
    text = (_project_file(_PROJECT_ROOT, BATCH / "repair-prompts/R2/prompt.txt")).read_text(encoding="utf-8")
    if sha256_text(text) != manifest["prompt_sha256"]:
        raise RuntimeError("R2 修复题面漂移")
    if (_project_file(_PROJECT_ROOT, BATCH / "replies-repair01")).exists():
        raise SystemExit("R2 修复回复已存在；拒绝重复调用")
    dispatch._expected_request_config = lambda _package: dict(REPAIR_CONFIG)
    report = dispatch.dispatch(
        BATCH, ["R2"], _project_file(_PROJECT_ROOT, BATCH / "replies-repair01"), _project_file(_PROJECT_ROOT, BATCH / "plan-repair01.json"),
        model_patch=str(_project_file(_PROJECT_ROOT, BATCH / "route.repair.patch.yml")), timeout_s=1200, concurrency=1,
        prompt_dir=_project_file(_PROJECT_ROOT, BATCH / "repair-prompts"), kind="r14-r2-contract-repair01")
    item = report["calls"][0]
    usage = criterion.usage_of(item.get("run_id"))
    values = usage.get("usage") or {}
    clean = (
        item.get("exit_code") == 0 and item.get("protocol_ok") is True
        and item.get("request_config") == REPAIR_CONFIG
        and usage.get("source_status") == "OK"
        and isinstance(values.get("inputTokens"), int)
        and isinstance(values.get("outputTokens"), int)
        and values["inputTokens"] <= 65536 and values["outputTokens"] <= 32768
    )
    write_json(_project_file(_PROJECT_ROOT, BATCH / "repair-call-usage.json"), {
        "schema": "r14-r2-repair-call-usage/1", "task": "R2",
        "run_id": item.get("run_id"), "exit_code": item.get("exit_code"),
        "protocol_ok": item.get("protocol_ok"), "observed_config": item.get("request_config"),
        "usage": usage, "ingestable_channel": clean,
    })
    if not clean:
        raise RuntimeError("R2 唯一修复通道或用量核对失败")
    print(json.dumps({"status": "R2_REPAIR_CALLED", "usage": usage}, ensure_ascii=False))


def ingest_r2_repair() -> None:
    """摄入 R2 唯一修复并更新最终作者验收摘要。"""

    channel = json.loads((_project_file(_PROJECT_ROOT, BATCH / "repair-call-usage.json")).read_text(encoding="utf-8"))
    raw = (_project_file(_PROJECT_ROOT, BATCH / "replies-repair01/R2.txt")).read_text(encoding="utf-8")
    parsed = gen.parse_action_value_reply(raw)
    code = parsed.get("code") or ""
    precheck = gen.precheck_action_value_candidate(code) if code else {
        "ok": False, "problems": ["没有可预检源码"]}
    load_error = None
    if code and precheck.get("ok") is True:
        try:
            ActionValueScorer("r14-R2-repair", code)
        except Exception as exc:  # noqa: BLE001
            load_error = type(exc).__name__ + ": " + str(exc)
    accepted = (channel.get("ingestable_channel") is True
                and parsed.get("status") == "ok" and precheck.get("ok") is True
                and load_error is None)
    target = _project_file(_PROJECT_ROOT, BATCH / "generations/R2/repair")
    target.mkdir(parents=True, exist_ok=True)
    (target / "reply_raw.txt").write_text(raw, encoding="utf-8")
    if code:
        (target / "candidate.py").write_text(code.rstrip("\n") + "\n", encoding="utf-8")
    write_json(target / "parsed.json", {
        key: value for key, value in parsed.items() if key != "code"
    } | ({"code_sha256": sha256_text(code)} if code else {}))
    write_json(target / "precheck.json", precheck)
    row = {"task": "R2", "repair": True, "parse_status": parsed.get("status"),
           "static_precheck": precheck.get("ok"), "load_error": load_error,
           "accepted_for_behavior_preflight": accepted,
           "code_sha256": sha256_text(code) if code else None,
           "problems": list(parsed.get("problems") or [])
                       + list(precheck.get("problems") or [])
                       + ([load_error] if load_error else [])}
    write_json(target / "record.json", row)
    initial = json.loads((_project_file(_PROJECT_ROOT, BATCH / "ingest-summary.json")).read_text(encoding="utf-8"))
    accepted_tasks = list(initial["accepted_for_behavior_preflight"])
    if accepted:
        accepted_tasks.append("R2")
    write_json(_project_file(_PROJECT_ROOT, BATCH / "final-ingest-summary.json"), {
        "schema": "r14-robust-offspring-final-ingest/1",
        "initial": initial["rows"], "repair": row,
        "accepted_for_behavior_preflight": accepted_tasks,
        "closed_failed": [] if accepted else ["R2"],
        "effect_evaluation_started": False,
    })
    print(json.dumps(json.loads((_project_file(_PROJECT_ROOT, BATCH / "final-ingest-summary.json")).read_text()),
                     ensure_ascii=False, indent=2))


def normalize_r2() -> None:
    """把 R2 既定机制映射到白名单字典操作和合同中的直接双型字段。"""

    source_path = _project_file(_PROJECT_ROOT, BATCH / "generations/R2/repair/candidate.py")
    original = source_path.read_text(encoding="utf-8")
    normalized = original
    replacements = [
        (
            '        tie_groups.setdefault((item.get("base"), entry.get("score")), []).append(idx)',
            '        group_key = (item.get("base"), entry.get("score"))\n'
            '        if group_key not in tie_groups:\n'
            '            tie_groups[group_key] = []\n'
            '        tie_groups[group_key].append(idx)',
            "用显式白名单字典更新替代语义相同的 setdefault",
        ),
        (
            '            dual = pending[idx].get("action").get("dual_shanten_after")\n'
            '            if not isinstance(dual, dict):\n'
            '                dual_ok = False\n'
            '                break\n'
            '            std = dual.get("standard")\n'
            '            sev = dual.get("seven_pairs")',
            '            target_action = pending[idx].get("action")\n'
            '            std = target_action.get("standard_shanten_after")\n'
            '            sev = target_action.get("seven_pairs_shanten_after")',
            "把模型虚构的 dual_shanten_after 包装映射为合同已有的两个直接字段",
        ),
        (
            '                dual = pending[idx].get("action").get("dual_shanten_after")\n'
            '                gap = abs(float(dual.get("standard")) - float(dual.get("seven_pairs")))',
            '                target_action = pending[idx].get("action")\n'
            '                gap = abs(float(target_action.get("standard_shanten_after"))\n'
            '                          - float(target_action.get("seven_pairs_shanten_after")))',
            "双型证据计算读取相同的合同直接字段",
        ),
    ]
    records = []
    for before, after, reason in replacements:
        count = normalized.count(before)
        if count != 1:
            raise RuntimeError(f"R2 归一化匹配数异常：{count}；{reason}")
        normalized = normalized.replace(before, after)
        records.append({"before": before, "after": after, "reason": reason})
    target = _project_file(_PROJECT_ROOT, BATCH / "generations/R2/normalized")
    if target.exists():
        raise SystemExit("R2 归一化目录已存在；拒绝覆盖")
    target.mkdir(parents=True)
    (target / "candidate.py").write_text(normalized.rstrip("\n") + "\n", encoding="utf-8")
    precheck = gen.precheck_action_value_candidate(normalized)
    load_error = None
    if precheck.get("ok") is True:
        try:
            ActionValueScorer("r14-R2-normalized", normalized)
        except Exception as exc:  # noqa: BLE001
            load_error = type(exc).__name__ + ": " + str(exc)
    record = {
        "schema": "r14-r2-engineering-normalization/1",
        "source_sha256": sha256_text(original),
        "normalized_sha256": sha256_text(normalized),
        "replacements": records,
        "mechanism_changed": False,
        "static_precheck": precheck.get("ok"), "load_error": load_error,
        "accepted_for_behavior_preflight": precheck.get("ok") is True and load_error is None,
        "problems": list(precheck.get("problems") or []) + ([load_error] if load_error else []),
    }
    write_json(target / "precheck.json", precheck)
    write_json(target / "normalization-record.json", record)
    final = json.loads((_project_file(_PROJECT_ROOT, BATCH / "final-ingest-summary.json")).read_text(encoding="utf-8"))
    accepted = list(final["accepted_for_behavior_preflight"])
    if record["accepted_for_behavior_preflight"]:
        accepted.append("R2-normalized")
    write_json(_project_file(_PROJECT_ROOT, BATCH / "normalized-ingest-summary.json"), {
        "schema": "r14-robust-offspring-normalized-ingest/1",
        "accepted_for_behavior_preflight": accepted,
        "r2_normalization": record,
        "closed_failed": [] if record["accepted_for_behavior_preflight"] else ["R2"],
        "effect_evaluation_started": False,
    })
    print(json.dumps(json.loads((_project_file(_PROJECT_ROOT, BATCH / "normalized-ingest-summary.json")).read_text()),
                     ensure_ascii=False, indent=2))


def normalize_r2_v2() -> None:
    """用列表保存等价并列组，满足受限语法不允许下标赋值的约束。"""

    source_path = _project_file(_PROJECT_ROOT, BATCH / "generations/R2/repair/candidate.py")
    original = source_path.read_text(encoding="utf-8")
    normalized = original
    replacements = [
        ("    tie_groups = {}", "    tie_groups = []\n    tie_group_keys = []",
         "并列组容器改为两个同序列表，避免受限语法禁止的动态字典写入"),
        (
            '        tie_groups.setdefault((item.get("base"), entry.get("score")), []).append(idx)',
            '        group_key = (item.get("base"), entry.get("score"))\n'
            '        if group_key in tie_group_keys:\n'
            '            group_pos = tie_group_keys.index(group_key)\n'
            '        else:\n'
            '            tie_group_keys.append(group_key)\n'
            '            tie_groups.append([])\n'
            '            group_pos = len(tie_groups) - 1\n'
            '        tie_groups[group_pos].append(idx)',
            "用白名单列表 append/index 实现与 setdefault 相同的分组",
        ),
        ("    for idxs in tie_groups.values():", "    for idxs in tie_groups:",
         "列表分组直接迭代，保持首次出现顺序"),
        (
            '            dual = pending[idx].get("action").get("dual_shanten_after")\n'
            '            if not isinstance(dual, dict):\n'
            '                dual_ok = False\n'
            '                break\n'
            '            std = dual.get("standard")\n'
            '            sev = dual.get("seven_pairs")',
            '            target_action = pending[idx].get("action")\n'
            '            std = target_action.get("standard_shanten_after")\n'
            '            sev = target_action.get("seven_pairs_shanten_after")',
            "把模型虚构的 dual_shanten_after 包装映射为合同已有的两个直接字段",
        ),
        (
            '                dual = pending[idx].get("action").get("dual_shanten_after")\n'
            '                gap = abs(float(dual.get("standard")) - float(dual.get("seven_pairs")))',
            '                target_action = pending[idx].get("action")\n'
            '                gap = abs(float(target_action.get("standard_shanten_after"))\n'
            '                          - float(target_action.get("seven_pairs_shanten_after")))',
            "双型证据计算读取相同的合同直接字段",
        ),
    ]
    records = []
    for before, after, reason in replacements:
        count = normalized.count(before)
        if count != 1:
            raise RuntimeError(f"R2 第二次归一化匹配数异常：{count}；{reason}")
        normalized = normalized.replace(before, after)
        records.append({"before": before, "after": after, "reason": reason})
    target = _project_file(_PROJECT_ROOT, BATCH / "generations/R2/normalized-v2")
    if target.exists():
        raise SystemExit("R2 第二次归一化目录已存在；拒绝覆盖")
    target.mkdir(parents=True)
    (target / "candidate.py").write_text(normalized.rstrip("\n") + "\n", encoding="utf-8")
    precheck = gen.precheck_action_value_candidate(normalized)
    load_error = None
    if precheck.get("ok") is True:
        try:
            ActionValueScorer("r14-R2-normalized-v2", normalized)
        except Exception as exc:  # noqa: BLE001
            load_error = type(exc).__name__ + ": " + str(exc)
    record = {
        "schema": "r14-r2-engineering-normalization/2",
        "source_sha256": sha256_text(original),
        "normalized_sha256": sha256_text(normalized),
        "supersedes_failed_normalization": "../normalized/normalization-record.json",
        "replacements": records, "mechanism_changed": False,
        "static_precheck": precheck.get("ok"), "load_error": load_error,
        "accepted_for_behavior_preflight": precheck.get("ok") is True and load_error is None,
        "problems": list(precheck.get("problems") or []) + ([load_error] if load_error else []),
    }
    write_json(target / "precheck.json", precheck)
    write_json(target / "normalization-record.json", record)
    accepted = ["R1"] + (["R2-normalized-v2"]
                          if record["accepted_for_behavior_preflight"] else [])
    write_json(_project_file(_PROJECT_ROOT, BATCH / "normalized-v2-ingest-summary.json"), {
        "schema": "r14-robust-offspring-normalized-ingest/2",
        "accepted_for_behavior_preflight": accepted,
        "r2_normalization": record,
        "closed_failed": [] if record["accepted_for_behavior_preflight"] else ["R2"],
        "effect_evaluation_started": False,
    })
    print(json.dumps(json.loads((_project_file(_PROJECT_ROOT, BATCH / "normalized-v2-ingest-summary.json")).read_text()),
                     ensure_ascii=False, indent=2))


def normalize_r2_v3() -> None:
    """以只追加记录的方式表达仲裁结果，消除剩余的下标赋值。"""

    source_path = _project_file(_PROJECT_ROOT, BATCH / "generations/R2/normalized-v2/candidate.py")
    original = source_path.read_text(encoding="utf-8")
    start = original.index("    for idxs in tie_groups:\n")
    end_marker = '    return {"status": "SCORED", "entries": final_entries, "reason": "胡以动态排序层优先；未知动作严格锚定在已知最终分最低值以下；弃牌完全并列组内互斥证据唯一强领先者+0.04"}\n'
    end = original.index(end_marker, start) + len(end_marker)
    replacement = '''    arbiter_records = []
    for idxs in tie_groups:
        if len(idxs) < 2:
            continue
        dual_ok = True
        for idx in idxs:
            target_action = pending[idx].get("action")
            std = target_action.get("standard_shanten_after")
            sev = target_action.get("seven_pairs_shanten_after")
            if std is None or sev is None or std is True or std is False or sev is True or sev is False:
                dual_ok = False
                break
            std_v = float(std)
            sev_v = float(sev)
            if std_v - std_v != 0 or sev_v - sev_v != 0:
                dual_ok = False
                break
        source = None
        evidences = []
        if dual_ok:
            source = "dual_type_flexibility"
            for idx in idxs:
                target_action = pending[idx].get("action")
                gap = abs(float(target_action.get("standard_shanten_after"))
                          - float(target_action.get("seven_pairs_shanten_after")))
                evidences.append(3.0 if gap == 0.0 else (1.5 if gap == 1.0 else 0.0))
        else:
            source = "opponent_river_same_tile_depth"
            for idx in idxs:
                tile_code = pending[idx].get("action").get("action_key")[8:]
                depth = 0
                for river_seat in range(4):
                    if river_seat != seat:
                        depth += discards[river_seat].count(tile_code)
                evidences.append(2.0 if depth >= 2 else (1.0 if depth == 1 else 0.0))
        order = sorted(range(len(idxs)), key=lambda pos: evidences[pos], reverse=True)
        top_evidence = evidences[order[0]]
        lead_gap = top_evidence - evidences[order[1]]
        triggered = top_evidence >= 1.0 and lead_gap >= 1.0
        leader_pos = order[0] if triggered else None
        for pos, idx in enumerate(idxs):
            bonus = 0.04 if (triggered and pos == leader_pos) else 0.0
            arbiter_records.append({"entry_index": idx, "group_size": len(idxs),
                                    "evidence_source": source,
                                    "evidence": evidences[pos],
                                    "lead_gap": round(lead_gap, 6),
                                    "triggered": triggered and pos == leader_pos,
                                    "bonus": bonus})
    resolved_entries = []
    for idx, entry in enumerate(final_entries):
        arbiter = None
        for record in arbiter_records:
            if record.get("entry_index") == idx:
                arbiter = record
        if arbiter is None:
            arbiter = {"entry_index": idx, "group_size": 0,
                       "evidence_source": None, "evidence": None,
                       "lead_gap": None, "triggered": False, "bonus": 0.0}
        old_trace = entry.get("trace")
        trace = {"basis": old_trace.get("basis"),
                 "base_score": old_trace.get("base_score"),
                 "shanten_after": old_trace.get("shanten_after"),
                 "best_shanten_non_pass": old_trace.get("best_shanten_non_pass"),
                 "wealth_part": old_trace.get("wealth_part"),
                 "wealth_discard_part": old_trace.get("wealth_discard_part"),
                 "river_part": old_trace.get("river_part"),
                 "risk_units": old_trace.get("risk_units"),
                 "style_part": old_trace.get("style_part"),
                 "unknown": old_trace.get("unknown"),
                 "unknown_policy": old_trace.get("unknown_policy"),
                 "hu_sorting_layer": old_trace.get("hu_sorting_layer"),
                 "scope": old_trace.get("scope"),
                 "discard_tiebreak": arbiter}
        resolved_entries.append({"action_key": entry.get("action_key"),
                                 "score": round(entry.get("score") + arbiter.get("bonus"), 6),
                                 "trace": trace})
    return {"status": "SCORED", "entries": resolved_entries, "reason": "胡以动态排序层优先；未知动作严格锚定在已知最终分最低值以下；弃牌完全并列组内互斥证据唯一强领先者+0.04"}
'''
    normalized = original[:start] + replacement + original[end:]
    target = _project_file(_PROJECT_ROOT, BATCH / "generations/R2/normalized-v3")
    if target.exists():
        raise SystemExit("R2 第三次归一化目录已存在；拒绝覆盖")
    target.mkdir(parents=True)
    (target / "candidate.py").write_text(normalized.rstrip("\n") + "\n", encoding="utf-8")
    precheck = gen.precheck_action_value_candidate(normalized)
    load_error = None
    if precheck.get("ok") is True:
        try:
            ActionValueScorer("r14-R2-normalized-v3", normalized)
        except Exception as exc:  # noqa: BLE001
            load_error = type(exc).__name__ + ": " + str(exc)
    record = {
        "schema": "r14-r2-engineering-normalization/3",
        "source_sha256": sha256_text(original),
        "normalized_sha256": sha256_text(normalized),
        "supersedes_failed_normalization": "../normalized-v2/normalization-record.json",
        "replacement": {"start": "for idxs in tie_groups",
                        "end": "return SCORED final_entries",
                        "reason": "用追加式仲裁记录与最终重建替代下标赋值；分组、证据、阈值和+0.04不变"},
        "mechanism_changed": False,
        "static_precheck": precheck.get("ok"), "load_error": load_error,
        "accepted_for_behavior_preflight": precheck.get("ok") is True and load_error is None,
        "problems": list(precheck.get("problems") or []) + ([load_error] if load_error else []),
    }
    write_json(target / "precheck.json", precheck)
    write_json(target / "normalization-record.json", record)
    accepted = ["R1"] + (["R2-normalized-v3"]
                          if record["accepted_for_behavior_preflight"] else [])
    write_json(_project_file(_PROJECT_ROOT, BATCH / "normalized-v3-ingest-summary.json"), {
        "schema": "r14-robust-offspring-normalized-ingest/3",
        "accepted_for_behavior_preflight": accepted,
        "r2_normalization": record,
        "closed_failed": [] if record["accepted_for_behavior_preflight"] else ["R2"],
        "effect_evaluation_started": False,
    })
    print(json.dumps(json.loads((_project_file(_PROJECT_ROOT, BATCH / "normalized-v3-ingest-summary.json")).read_text()),
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=(
        "prepare", "call", "call_retry", "ingest", "prepare_r2_repair",
        "call_r2_repair", "ingest_r2_repair", "normalize_r2", "normalize_r2_v2",
        "normalize_r2_v3"))
    args = parser.parse_args()
    globals()[args.operation]()
