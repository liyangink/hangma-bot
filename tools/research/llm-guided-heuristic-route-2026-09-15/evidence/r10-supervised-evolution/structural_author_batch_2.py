"""R10 第二结构作者批次：用首批新来源反馈生成四个有界结构家族。"""
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
import json
import sys
from pathlib import Path


HERE = Path(__file__).resolve().parent
ROUTE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15')
ADMISSION = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/v4-impl/r9-admission')
HEADLESS = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/v4-impl/r9-admission/p25-headless')
DEV_CARDS = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/v4-impl/r9-admission/p25-dev-cards')
TOOLS = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/tools')
for path in (TOOLS, HEADLESS, DEV_CARDS, HERE):
    sys.path.insert(0, str(path))

import criterion  # noqa: E402
import dispatch_headless as dispatch  # noqa: E402
import sitin_generate as gen  # noqa: E402
import structural_author_batch as first  # noqa: E402


BATCH = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/structural-search-02-20260921')
S3 = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/structural-search-01-20260921/behavior-preflight-v2/configurations/s3-cfg-02/candidate.py')
V2 = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/v2-parent-revalidation-20260920/parent/generation/candidate.py')
PATTERN = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/pattern-option-20260920/pattern-option-terra-max/run/iterations/iter-01/generation/candidate.py')
EXPECTED_HASHES = {
    "s3": "984c2b2e52baa042bbd08ed63b4ff74865b2f310a2f71180b76cde945f909c41",
    "v2": "a0c389b3a4757a38febf5ca6bf16e9c4779159df0c15b82d2e804e1f4ac9638f",
    "pattern": "756233cb62cc7759b9a6facea209420e36de0b1e2bb90a16203c9e9351795f31",
}
EXPECTED_CONFIG = {
    "provider": "zai-coding-cn",
    "model": "glm-5.3",
    "reasoningEffort": "high",
    "maxTokens": 32768,
}


COMMON_FACTS = (
    "首批结构冠军 s3-cfg-02 在共同开发 H/M 各32根上的点差为 +0.0390625/+0.0234375；"
    "冻结后用两个全新panel_seed、H/M各128根、4096完整桌复核，点差为"
    "+0.021484375/+0.01171875，保守差为+0.015625/0，等权保守均值+0.0078125，"
    "95%开发近似区间[-0.0128386,+0.0284636]，故结论为INCONCLUSIVE_DEVELOPMENT。"
    "这些只是根级开发反馈，不是动作标签、显著提升或确认结果。候选在226个既有真实视图上"
    "改变27个分数、2个首选，最大计数操作6245；支持权重为0。"
)


TASKS = {
    "T1": {
        "name": "relative-followup-margin",
        "parent": "s3",
        "objective": "把绝对后续向听加分改成同窗可比动作之间的相对后续优势结构。",
        "change": (
            "现父代对每个有分支动作独立加4*(1-best_shanten)，即使窗口没有可比的第二个"
            "分支动作也平移分数。设计一个只在证据可比较时触发的相对、归一化或门控结构；"
            "不得读取H/M标签，不得把support当概率。"
        ),
        "hypothesis": (
            "ReEvo式利用反馈：保留已经跨来源同向的后续分支父代，但减少无竞争动作上的噪声，"
            "可能提高微小信号的稳定性。"
        ),
        "groups": [
            "actions", "actions[]", "actions[].useful_tiles",
            "actions[].followup_branches", "visible_state",
            "visible_state.rule_state", "competition", "analysis_profile",
        ],
    },
    "T2": {
        "name": "selective-followup-trigger",
        "parent": "s3",
        "objective": "在不按对手族分支的前提下，为后续价值设计可审计的选择性触发。",
        "change": (
            "父代对所有携带followup_branches的动作采用同一公式，跨新来源信号为正但M族保守差为0。"
            "根据动作类型、直接牌效是否可比、分支信息完整度或同窗差距选择一个主门控；"
            "不得同时堆叠多套奖励，也不得针对H/M写运行时条件。"
        ),
        "hypothesis": (
            "EoH单父代改良：用公开、局面内事实限制触发范围，保留有效父代并减少错误泛化。"
        ),
        "groups": [
            "actions", "actions[]", "actions[].useful_tiles",
            "actions[].followup_branches", "actions[].family_progress_entries",
            "visible_state", "visible_state.rule_state", "competition", "analysis_profile",
        ],
    },
    "T3": {
        "name": "settlement-route-witness",
        "parent": "v2",
        "companion": "s3",
        "objective": "探索与分支向听不同的、基于已生产结算或路线见证的有界价值结构。",
        "change": (
            "首批证明后续分支方向有弱正信号但未分辨；本题从V2重新出发，只选择"
            "immediate_settlement、routes或conditional_settlement中的一个主见证结构。"
            "结算是条件见证，不是发生概率或期望；不能把它与S3项直接相加。"
        ),
        "hypothesis": (
            "Mxplainer和麻将MDP文献提示局部进度需连接价值，但当前只能迁移有界结构，"
            "不能照搬概率、番型或隐藏状态；一个正交价值见证可扩展过稀的行为覆盖。"
        ),
        "groups": [
            "actions", "actions[]", "actions[].immediate_settlement",
            "actions[].routes", "actions[].routes[].useful_tiles",
            "actions[].routes[].conditions", "actions[].routes[].conditional_settlement",
            "actions[].followup_branches", "visible_state", "visible_state.rule_state",
            "competition", "analysis_profile",
        ],
        "overview": "contract",
    },
    "T4": {
        "name": "followup-simplification",
        "parent": "s3",
        "objective": "简化首批冠军，删除未产生可辨行为的参数和绝对尺度依赖。",
        "change": (
            "s3-cfg-02的FBV_SUPPORT=0，FBV_SUPPORT_CAP不影响可执行分数；cfg-02与cfg-04在226视图上"
            "首选签名相同。至少删除这些无贡献自由度，并把主结构改成更短的序数、分层或打破平分"
            "机制；不能只交同一公式的新常数。"
        ),
        "hypothesis": (
            "EoH M3/最小描述长度思路：更少自由度和更窄作用面可能保留跨来源正向材料并降低方差。"
        ),
        "groups": [
            "actions", "actions[]", "actions[].useful_tiles",
            "actions[].followup_branches", "visible_state",
            "visible_state.rule_state", "competition", "analysis_profile",
        ],
    },
}


EXTRA_REQUIREMENTS = first.COMMON_REQUIREMENTS + """
- 本批特别禁止把上述H/M汇总数值写成运行时阈值、动作标签或隐藏场景识别器；它们只说明父代信号小且仍未分辨。
- 输出尽量短：完整源码优先，建议不超过420行；说明四字段每项不超过260个汉字，避免用满输出上限。
"""


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def parent(name: str) -> dict:
    path = {"s3": S3, "v2": V2, "pattern": PATTERN}[name]
    code = path.read_text(encoding="utf-8")
    digest = first.sha256_text(code)
    if digest != EXPECTED_HASHES[name]:
        raise ValueError(f"父代{name}摘要漂移：{digest}")
    thought = {
        "s3": "默认V2骨架加唯一主结构：只读followup_branches最佳combined_shanten的有界后续价值项。",
        "v2": "默认V2基础排序、胡排序层与严格未知锚定的可审计种子。",
        "pattern": "普通型与七对的可见选项结构研究父代；只作重组材料，不继承效果结论。",
    }[name]
    return {"name": name, "path": str(path), "identity": digest,
            "candidate_id": digest, "thought": thought,
            "code": code, "code_sha256": digest}


def prompt_for(task_id: str, spec: dict, parents: dict) -> tuple[str, dict]:
    primary = parents[spec["parent"]]
    payload = gen.render_action_value_task_contract(
        objective_summary=(
            "在首批弱正但未分辨的结构父代上产生可消融的新结构；只生成结构与六配置，"
            "不接触第二批效果实例。"
        ),
        panel_boundary=(
            "程序先做静态、算术和226个既有真实视图行为预检；通过后才在全新共同开发根上"
            "按统一分段预算竞赛。本卡不得选择实例或判定胜负。"
        ),
        prompt_role=f"{task_id} {spec['name']}：{spec['objective']}",
        parent=primary,
        feedback={
            "facts": COMMON_FACTS,
            "associated_results": spec["change"],
            "mechanism_hypothesis": spec["hypothesis"],
        },
        budget_note="首答计一次调用；仅语法/合同错误允许一次修复；效果不佳不修复。",
    )
    focus = {
        "objective": spec["objective"],
        "change_point": spec["change"],
        "input_groups": spec["groups"],
        "gate": "none", "guard": "full", "guard_reference": False,
        "examples": "output", "rules": "compact",
        "input_overview": spec.get("overview", "none"),
        "budget_note": "首答计费；不得依据模型自报结果选留。",
    }
    packet = gen.build_action_value_card_prompt("m1", payload, focus)
    extra = [EXTRA_REQUIREMENTS]
    companion_name = spec.get("companion")
    if companion_name:
        companion = parents[companion_name]
        extra.extend([
            "【第二父代完整身份】",
            f"- name={companion_name}; sha256={companion['code_sha256']}",
            "- 第二父代只作结构比较材料，不把两个分数项直接相加。",
            "【第二父代机制说明】", companion["thought"],
            "【第二父代代码（逐字）】", gen.FENCE + "python",
            companion["code"].rstrip("\n"), gen.FENCE,
        ])
    output_block = gen._av_output_format()
    if packet.text.count(output_block) != 1:
        raise RuntimeError("无法定位唯一输出格式段")
    prompt = packet.text.replace(output_block, "\n\n".join(extra) + "\n\n" + output_block)
    return prompt, {
        "task_id": task_id, "name": spec["name"],
        "primary_parent": primary["code_sha256"],
        "companion_parent": parents[companion_name]["code_sha256"] if companion_name else None,
        "contract_identity": packet.contract_identity,
        "focus": gen.normalize_card_focus(focus),
        "prompt_sha256": first.sha256_text(prompt), "prompt_chars": len(prompt),
    }


def prepare() -> None:
    if BATCH.exists():
        raise SystemExit("第二结构作者批次已存在；拒绝覆盖")
    parents = {name: parent(name) for name in EXPECTED_HASHES}
    rows = []
    for task_id, spec in TASKS.items():
        prompt, row = prompt_for(task_id, spec, parents)
        target = _project_file(_PROJECT_ROOT, BATCH / "prompts" / task_id)
        target.mkdir(parents=True, exist_ok=True)
        (target / "prompt.txt").write_text(prompt, encoding="utf-8")
        rows.append(row)
    settings = """# R10 第二结构作者批次；中等模型高推理强度，输出上界冻结。
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
    (_project_file(_PROJECT_ROOT, BATCH / "settings.yaml")).write_text(settings, encoding="utf-8")
    (_project_file(_PROJECT_ROOT, BATCH / "route.patch.yml")).write_text(
        "- id: settings\n  config:\n    path: " + str(_project_file(_PROJECT_ROOT, BATCH / "settings.yaml"))
        + "\n    watch: false\n- id: agent-default-model\n  config:\n"
        + "    provider: zai-coding-cn\n    model: glm-5.3\n", encoding="utf-8")
    write_json(_project_file(_PROJECT_ROOT, BATCH / "manifest.json"), {
        "schema": "r10-structural-author-batch/2",
        "target_model": {"provider": "zai-coding-cn", "model": "glm-5.3"},
        "expected_request_config": EXPECTED_CONFIG,
        "tasks": rows,
        "parent_registry": {
            key: {field: value for field, value in value.items() if field != "code"}
            for key, value in parents.items()
        },
        "feedback_source": str(
            _project_file(_PROJECT_ROOT, HERE / "structural-search-01-20260921/new-source-01/summary.json")),
        "effect_evaluation_started": False,
        "confirmation_reserved": 0,
    })
    write_json(_project_file(_PROJECT_ROOT, BATCH / "authorization.json"), {
        "schema": "sitin-authorization/1",
        "authorization_id": "r10-structural-search-02-20260921",
        "trusted": True, "issued_by": "Codex root",
        "issued_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "issuance_basis": (
            "用户授权API上限前由root安排zai-coding-cn GLM5.3调用，并要求进展受挫时按文献复盘后继续；"
            "首批新来源结果弱正但未分辨，本批执行EoH/ReEvo/LLaMEA-HPO式有界改良。"),
        "route": "offline_structural_authoring", "max_initial_calls": 4,
        "max_repair_calls": 4, "max_total_calls": 8,
        "per_call_limits": {"tokens_input": 196608, "tokens_output": 32768},
        "allowed_accounts": {"tokens_input": 1572864, "tokens_output": 262144},
        "effect_tables": 0, "confirmation_reserved": 0,
        "autonomous_admission": False,
        "scope": "离线结构提案；生成预检后另冻效果预算；不得确认或发布",
    })
    (_project_file(_PROJECT_ROOT, BATCH / ".gitignore")).write_text("dispatch-ledger/\n", encoding="utf-8")
    print(json.dumps({"status": "PREPARED", "tasks": rows}, ensure_ascii=False, indent=2))


def verify_prompts() -> list[str]:
    manifest = json.loads((_project_file(_PROJECT_ROOT, BATCH / "manifest.json")).read_text(encoding="utf-8"))
    result = []
    for row in manifest["tasks"]:
        task_id = row["task_id"]
        prompt = (_project_file(_PROJECT_ROOT, BATCH / "prompts" / task_id / "prompt.txt")).read_text(encoding="utf-8")
        if first.sha256_text(prompt) != row["prompt_sha256"]:
            raise ValueError("提示词摘要漂移：" + task_id)
        result.append(task_id)
    return result


def call() -> None:
    task_ids = verify_prompts()
    if (_project_file(_PROJECT_ROOT, BATCH / "replies")).exists():
        raise SystemExit("第二批首答已存在；拒绝重复调用")
    dispatch._expected_request_config = lambda _package: dict(EXPECTED_CONFIG)
    report = dispatch.dispatch(
        BATCH, task_ids, _project_file(_PROJECT_ROOT, BATCH / "replies"), _project_file(_PROJECT_ROOT, BATCH / "plan-initial.json"),
        model_patch=str(_project_file(_PROJECT_ROOT, BATCH / "route.patch.yml")), timeout_s=900, concurrency=2,
        prompt_dir=_project_file(_PROJECT_ROOT, BATCH / "prompts"), kind="structural-initial-2")
    rows, problems = [], []
    for call_row in sorted(report["calls"], key=lambda item: item["task"]):
        usage = criterion.usage_of(call_row.get("run_id"))
        values = usage.get("usage") or {}
        clean = (
            call_row.get("exit_code") == 0 and call_row.get("protocol_ok") is True
            and call_row.get("request_config") == EXPECTED_CONFIG
            and usage.get("source_status") == "OK"
            and isinstance(values.get("inputTokens"), int)
            and isinstance(values.get("outputTokens"), int)
            and values["inputTokens"] <= 196608 and values["outputTokens"] <= 32768)
        rows.append({
            "task": call_row["task"], "run_id": call_row.get("run_id"),
            "observed_config": call_row.get("request_config"),
            "protocol_ok": call_row.get("protocol_ok"),
            "exit_code": call_row.get("exit_code"), "usage": usage,
            "ingestable_channel": clean,
        })
        if not clean:
            problems.append(call_row["task"])
    write_json(_project_file(_PROJECT_ROOT, BATCH / "initial-call-usage.json"), {
        "schema": "r10-structural-call-usage/2", "calls": rows,
        "total_input_tokens": sum((row["usage"].get("usage") or {}).get("inputTokens", 0)
                                  for row in rows),
        "total_output_tokens": sum((row["usage"].get("usage") or {}).get("outputTokens", 0)
                                   for row in rows),
        "problems": problems,
    })
    print(json.dumps({"status": "CALLS_COMPLETE_WITH_CHANNEL_PROBLEMS" if problems
                      else "CALLS_COMPLETE", "problems": problems}, ensure_ascii=False))


def call_retry() -> None:
    """仅在首次四请求供应商记账均为零时，以相同冻结提示和配置重试传输。"""
    task_ids = verify_prompts()
    first_usage = json.loads((_project_file(_PROJECT_ROOT, BATCH / "initial-call-usage.json")).read_text(encoding="utf-8"))
    if (first_usage.get("total_input_tokens") != 0
            or first_usage.get("total_output_tokens") != 0
            or sorted(first_usage.get("problems") or []) != sorted(task_ids)):
        raise ValueError("首次调用并非全量零用量传输失败，拒绝走传输重试")
    if (_project_file(_PROJECT_ROOT, BATCH / "replies-retry")).exists():
        raise SystemExit("传输重试目录已存在；拒绝重复重试")
    dispatch._expected_request_config = lambda _package: dict(EXPECTED_CONFIG)
    report = dispatch.dispatch(
        BATCH, task_ids, _project_file(_PROJECT_ROOT, BATCH / "replies-retry"), _project_file(_PROJECT_ROOT, BATCH / "plan-retry.json"),
        model_patch=str(_project_file(_PROJECT_ROOT, BATCH / "route.patch.yml")), timeout_s=900, concurrency=2,
        prompt_dir=_project_file(_PROJECT_ROOT, BATCH / "prompts"), kind="structural-initial-2-transport-retry")
    rows, problems = [], []
    for call_row in sorted(report["calls"], key=lambda item: item["task"]):
        usage = criterion.usage_of(call_row.get("run_id"))
        values = usage.get("usage") or {}
        clean = (
            call_row.get("exit_code") == 0 and call_row.get("protocol_ok") is True
            and call_row.get("request_config") == EXPECTED_CONFIG
            and usage.get("source_status") == "OK"
            and isinstance(values.get("inputTokens"), int)
            and isinstance(values.get("outputTokens"), int)
            and values["inputTokens"] <= 196608 and values["outputTokens"] <= 32768)
        rows.append({
            "task": call_row["task"], "run_id": call_row.get("run_id"),
            "observed_config": call_row.get("request_config"),
            "protocol_ok": call_row.get("protocol_ok"),
            "exit_code": call_row.get("exit_code"), "usage": usage,
            "ingestable_channel": clean,
        })
        if not clean:
            problems.append(call_row["task"])
    write_json(_project_file(_PROJECT_ROOT, BATCH / "retry-call-usage.json"), {
        "schema": "r10-structural-call-usage/2", "calls": rows,
        "retry_basis": "首次四请求均为TRANSPORT错误且供应商用量为零",
        "first_attempt_usage_sha256": first.sha256_text(
            (_project_file(_PROJECT_ROOT, BATCH / "initial-call-usage.json")).read_text(encoding="utf-8")),
        "total_input_tokens": sum((row["usage"].get("usage") or {}).get("inputTokens", 0)
                                  for row in rows),
        "total_output_tokens": sum((row["usage"].get("usage") or {}).get("outputTokens", 0)
                                   for row in rows),
        "problems": problems,
    })
    print(json.dumps({"status": "RETRY_COMPLETE_WITH_PROBLEMS" if problems
                      else "RETRY_COMPLETE", "problems": problems}, ensure_ascii=False))


def ingest() -> None:
    task_ids = verify_prompts()
    retry = _project_file(_PROJECT_ROOT, BATCH / "retry-call-usage.json")
    usage_path = retry if retry.exists() else _project_file(_PROJECT_ROOT, BATCH / "initial-call-usage.json")
    replies = _project_file(_PROJECT_ROOT, BATCH / ("replies-retry" if retry.exists() else "replies"))
    usage = json.loads(usage_path.read_text(encoding="utf-8"))
    by_task = {row["task"]: row for row in usage["calls"]}
    rows = []
    for task_id in task_ids:
        raw = (replies / f"{task_id}.txt").read_text(encoding="utf-8")
        parsed = gen.parse_action_value_reply(raw)
        code = parsed.get("code") or ""
        precheck = gen.precheck_action_value_candidate(code) if code else {
            "ok": False, "problems": ["没有可预检源码"]}
        try:
            space = first.validate_space(code) if code else {
                "ok": False, "problems": ["没有可解析参数空间"]}
        except (SyntaxError, ValueError) as exc:
            space = {"ok": False, "problems": [f"参数空间预检异常：{type(exc).__name__}: {exc}"]}
        target = _project_file(_PROJECT_ROOT, BATCH / "generations" / task_id)
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
    write_json(_project_file(_PROJECT_ROOT, BATCH / "ingest-summary.json"), {
        "schema": "r10-structural-ingest/2", "tasks": rows,
        "accepted": [row["task"] for row in rows if row["accepted_for_behavior_preflight"]],
        "repair_eligible": [row["task"] for row in rows
                            if not row["accepted_for_behavior_preflight"]],
        "effect_evaluation_started": False,
        "note": "只有语法/合同失败可修复；效果未知，尚未运行行为或效果评测。",
    })
    print(json.dumps(json.loads((_project_file(_PROJECT_ROOT, BATCH / "ingest-summary.json")).read_text(encoding="utf-8")),
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("prepare", "call", "call-retry", "ingest"))
    args = parser.parse_args()
    {"prepare": prepare, "call": call, "call-retry": call_retry,
     "ingest": ingest}[args.operation]()
