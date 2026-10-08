"""R18 首代机会专长作者：三财保财边界与四财飘边界。

作者只能看到冻结开发集摘要；隐藏题库既不进入提示词，也不进入首轮评分。
模型只交付受限 ``score_actions(view)`` 源码，规则与效果均由本地正式链路裁定。
"""

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
import asyncio
import datetime as dt
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import sys


HERE = Path(__file__).resolve().parent
ROUTE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15')
ADMISSION = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/v4-impl/r9-admission')
for path in (
    _project_file(_PROJECT_ROOT, ROUTE / "tools"),
    _project_file(_PROJECT_ROOT, ADMISSION / "p25-headless"),
    _project_file(_PROJECT_ROOT, ADMISSION / "p25-dev-cards"),
    HERE,
):
    sys.path.insert(0, str(path))

import criterion  # noqa: E402
import dispatch_headless as dispatch  # noqa: E402
import r18_multi_wealth_bank as bank  # noqa: E402
import sitin_generate as gen  # noqa: E402
from hangma_bot.offline.opportunity_capability import (  # noqa: E402
    evaluate_pair,
    summarize_family,
)
from hangma_bot.policy.action_value_policy import ActionValuePolicy  # noqa: E402
from hangma_bot.policy.action_value_seeds import ActionValueScorer  # noqa: E402
from hangma_bot.policy.heuristic_v2 import ComparableHeuristicPolicyV2  # noqa: E402


BATCH = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-opportunity-author-01-20260922')
V2 = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/v2-parent-revalidation-20260920/parent/generation/candidate.py')
BANK = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-multi-wealth-bank-02-20260922')
DEVELOPMENT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-multi-wealth-bank-02-20260922/development.json')

EXPECTED_CONFIG = {
    "provider": "zai-coding-cn",
    "model": "glm-5.3",
    "reasoningEffort": "max",
    "maxTokens": 20000,
}

REPAIR_CONFIG = {
    "provider": "zai-coding-cn",
    "model": "glm-5.3",
    "reasoningEffort": "low",
    "maxTokens": 16000,
}

TASKS = {
    "K3": {
        "name": "three-wealth-keep-boundary",
        "objective": (
            "在稳定 V2 上增加一个窄的三财保财决策器：仅当当前可胡、权威状态为爆头、"
            "准确持有三张财神，且某个非飘弃牌拥有完整的动作后爆头与条件结算事实时，"
            "才允许它与立即胡跨动作族比较。其他窗口必须精确退化到 V2 相对排序。"
        ),
        "direction": (
            "开发尺显示六个三财状态中，V2 因胡层固定优先而错过保财；优势多数很小。"
            "请设计保守、可证伪的边界，明确等待失败风险折扣。不得把一次自摸条件代理"
            "冒充完整牌局期望，也不得把财神数本身当成无条件继续理由。"
        ),
    },
    "P4": {
        "name": "four-wealth-piao-boundary",
        "objective": (
            "在稳定 V2 上增加一个窄的四财飘决策器：仅当当前可胡、准确持有四张财神、"
            "弃财神被规则事实证明推进飘链且具有完整条件结算路线时，才允许弃白越过胡层。"
            "其他窗口必须精确退化到 V2 相对排序。"
        ),
        "direction": (
            "开发尺有一个四财状态：弃白的条件路线结算与广覆盖证据明显强于当前胡；"
            "该信号仍未计他家先胡与轮转风险。请提出只在强证据下触发的边界，不能扩张"
            "到三财、普通弃牌或任意 ADVANCE 动作。"
        ),
    },
}

COMMON = """【R18 机会专长机器约束】
- 交付一份完整可执行的 score_actions(view) 源码，不交补丁；建议不超过 300 行。不得 import、调用工具、文件、网络、时间或随机源。
- 以随题提供的稳定 V2 完整源码为唯一回退。目标机会机制不触发或任一必要事实未知/不完整时，全部动作相对排序必须与 V2 精确一致；不得顺手改写牌效、牌河、赛事处境、杠、吃碰、过或未知锚定。
- 只能读取 sitin-scoring-view/3 已投影的 PlayerObservation 与 HangmaRules 事实。不得重算胡牌、向听、爆头、链、结算或合法动作；不得读取 WorldState、牌墙顺序、对手暗牌、题目答案、隐藏 split 或效果标签。
- 严禁按 game_id、case_id、生成 seed、确切手牌或确切摸牌硬编码。财神牌码只能从 rule_state.wealth_god 读取；三财/四财计数必须兼容 my_hand 已含或未含 drawn_tile 两种官方快照，不能重复计摸牌。
- 条件路线只证明“动作后某类进张能立即胡及其结算”；support/remaining_estimate 不是概率，路线 score_delta 不是已经获得的收益。若使用风险折扣或阈值，必须给出结构解释、触发边界和反例，不能声称是无偏期望。
- 只有 action.value_coverage=complete、value_issues 为空，且所有用于比较的结算、进张余量与进展事实均为已知有限数时才可触发；否则精确回退 V2。
- 必须保留全部合法动作、动态胡排序层、未知严格低于全部已知、全未知 ABSTAIN、拒绝动作过滤与有限数。None/布尔不能当数。
- 只新增一个可消融结构。trace 必须记录结构名、是否触发、财神数、即时胡证据、继续证据、风险折扣/阈值、实际改分和退化原因。
- 不得宣称提分、通过、确认或可发布。作者输出只进入开发预检；隐藏题和真实桌赛另行裁定。
"""


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def parent_record() -> dict[str, str]:
    code = V2.read_text(encoding="utf-8")
    digest = sha256_text(code)
    return {
        "name": "stable-v2",
        "path": str(V2),
        "identity": digest,
        "candidate_id": digest,
        "thought": code.splitlines()[0],
        "code": code,
        "code_sha256": digest,
    }


def development_cases():
    """只从开发文件重建题目；避免作者包构建路径碰触隐藏制品。"""

    payload = json.loads(DEVELOPMENT.read_text(encoding="utf-8"))
    rows = []
    for row in payload["cases"]:
        request = bank.decision_request_from_json(row["request"])
        if bank.digest_value(row["request"]) != row["request_sha256"]:
            raise RuntimeError(row["case_id"] + " request 哈希不符")
        if (
            bank.digest_value(row["reachability_witness"])
            != row["reachability_witness_sha256"]
        ):
            raise RuntimeError(row["case_id"] + " 可达见证哈希不符")
        rows.append(bank.OpportunityCapabilityCase(
            case_id=row["case_id"],
            base_scenario_id=row["base_scenario_id"],
            family=row["family"],
            split=row["split"],
            generator_seed=row["generator_seed"],
            rules_hash=row["rules_hash"],
            generator_sha256=row["generator_sha256"],
            oracle_version=row["oracle_version"],
            oracle_level=row["oracle_level"],
            request_sha256=row["request_sha256"],
            reachability_witness_sha256=row["reachability_witness_sha256"],
            request=request,
            action_values=tuple(
                bank.OracleActionValue(**item) for item in row["action_values"]
            ),
        ))
    return rows


async def _score_v2_development(cases):
    policy = ComparableHeuristicPolicyV2()
    return [await evaluate_pair(policy, policy, case, bank.budget) for case in cases]


def development_feedback() -> dict[str, object]:
    """只构造作者可见开发摘要；本函数禁止读取 hidden.json。"""

    payload = json.loads(DEVELOPMENT.read_text(encoding="utf-8"))
    scored = {
        row.candidate.case_id: row.candidate
        for row in asyncio.run(_score_v2_development(development_cases()))
    }
    failures = []
    correct_by_wealth: dict[str, int] = {}
    for case in payload["cases"]:
        row = scored[case["case_id"]]
        if row.regret == 0:
            key = str(case["wealth_count"])
            correct_by_wealth[key] = correct_by_wealth.get(key, 0) + 1
            continue
        best = max(float(item["value"]) for item in case["action_values"])
        failures.append({
            "wealth_count": case["wealth_count"],
            "decision_type": case["decision_type"],
            "v2_action": row.chosen_action_key,
            "oracle_best_action_types": sorted({
                item["action_key"].split(":", 1)[0]
                + (":wealth" if item["action_key"] == "discard:白" else ":nonwealth")
                for item in case["action_values"]
                if float(item["value"]) == best
            }),
            "proxy_regret": row.regret,
            "immediate_hu_value": next(
                float(item["value"])
                for item in case["action_values"]
                if item["action_key"] == "hu"
            ),
            "best_proxy_value": best,
        })
    return {
        "bank_schema": payload["schema"],
        "development_file_sha256": sha256(DEVELOPMENT),
        "development_cases": len(payload["cases"]),
        "v2_correct_cases_not_expanded_in_prompt": correct_by_wealth,
        "v2_failure_count": len(failures),
        "v2_failures_aggregated_without_hands_or_case_ids": failures,
        "oracle": (
            "下一次本人自摸立即胡的条件代理；数值未建模他家先胡、鸣牌、轮转生存率"
            "与更远续值，未做配对反事实校准"
        ),
        "leakage_boundary": (
            "没有向作者读取或序列化 hidden.json；开发摘要也删除 case_id、手牌、摸牌"
            "和生成 seed，只保留机制级错误形状"
        ),
    }


def prompt_for(task_id: str, spec: dict[str, str], parent: dict[str, str]) -> str:
    feedback = development_feedback()
    payload = gen.render_action_value_task_contract(
        objective_summary=spec["objective"],
        panel_boundary=(
            "首轮只做静态/受限加载、冻结开发题与作者不可见的普通正确题负控；"
            "隐藏题在代理经配对反事实校准前不运行，完整桌赛只在专长通过后作安全门。"
        ),
        prompt_role=f"{task_id} {spec['name']}：R18 机会专长作者",
        parent=parent,
        feedback={
            "facts": json.dumps(feedback, ensure_ascii=False, indent=2),
            "associated_results": spec["direction"],
            "mechanism_hypothesis": spec["objective"],
        },
        budget_note=(
            "本题首答计一次作者调用；只允许后续一次纯语法/合同修复，不能借修复"
            "改变机会机制、阈值或触发域。"
        ),
    )
    focus = {
        "objective": spec["objective"],
        "change_point": spec["direction"],
        "input_groups": [
            "actions",
            "actions[]",
            "actions[].useful_tiles",
            "actions[].standard_useful_tiles",
            "actions[].seven_pairs_useful_tiles",
            "actions[].followup_branches",
            "actions[].routes",
            "actions[].family_progress_entries",
            "visible_state",
            "visible_state.rule_state",
            "competition",
            "analysis_profile",
        ],
        "gate": "none",
        "guard": "full",
        "guard_reference": False,
        "examples": "output",
        "rules": "compact",
        "input_overview": "contract",
        "budget_note": (
            "不得针对七个开发错误逐手记忆；只提交一个跨手牌结构。"
        ),
    }
    packet = gen.build_action_value_card_prompt("m1", payload, focus)
    output = gen._av_output_format()
    if packet.text.count(output) != 1:
        raise RuntimeError("无法定位唯一输出格式段")
    return packet.text.replace(output, COMMON + "\n\n" + output)


def prepare() -> None:
    """冻结两张作者题、开发反馈、模型配置与调用授权。"""

    if BATCH.exists():
        raise SystemExit("R18 作者批已存在；拒绝覆盖")
    parent = parent_record()
    rows = []
    for task_id, spec in TASKS.items():
        text = prompt_for(task_id, spec, parent)
        target = _project_file(_PROJECT_ROOT, BATCH / "prompts" / task_id)
        target.mkdir(parents=True, exist_ok=True)
        (target / "prompt.txt").write_text(text, encoding="utf-8")
        rows.append({
            "task": task_id,
            "name": spec["name"],
            "prompt_sha256": sha256_text(text),
            "prompt_chars": len(text),
        })
    settings = """llm-pi-ai:
  providers:
    zai-coding-cn:
      apiKeyEnv: ZAI_CODING_CN_API_KEY
      models:
        - id: glm-5.3
          name: GLM-5.3
          contextWindow: 1000000
          maxTokens: 20000

agent-default-model:
  provider: zai-coding-cn
  model: glm-5.3
  reasoningEffort: max
"""
    (_project_file(_PROJECT_ROOT, BATCH / "settings.yaml")).write_text(settings, encoding="utf-8")
    (_project_file(_PROJECT_ROOT, BATCH / "route.patch.yml")).write_text(
        "- id: settings\n  config:\n    path: " + str(_project_file(_PROJECT_ROOT, BATCH / "settings.yaml"))
        + "\n    watch: false\n- id: agent-default-model\n  config:\n"
        + "    provider: zai-coding-cn\n    model: glm-5.3\n",
        encoding="utf-8",
    )
    write_json(_project_file(_PROJECT_ROOT, BATCH / "manifest.json"), {
        "schema": "r18-opportunity-author/1",
        "created_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "expected_request_config": EXPECTED_CONFIG,
        "tasks": rows,
        "inputs": {
            str(V2): sha256(V2),
            str(DEVELOPMENT): sha256(DEVELOPMENT),
        },
        "explicitly_excluded_from_prompt": [str(_project_file(_PROJECT_ROOT, BANK / "hidden.json"))],
        "hidden_evaluation_started": False,
        "effect_tables": 0,
        "confirmation_reserved": 0,
    })
    write_json(_project_file(_PROJECT_ROOT, BATCH / "authorization.json"), {
        "schema": "sitin-authorization/1",
        "authorization_id": "r18-opportunity-author-01",
        "trusted": True,
        "issued_by": "lead",
        "issued_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "issuance_basis": (
            "用户授权 zai-coding-cn GLM 5.3 在 API 上限前由 root 调度，并明确要求"
            "取消旧目标后持续推进机会优先的新目标"
        ),
        "max_initial_calls": 2,
        "max_repair_calls": 2,
        "max_total_calls": 4,
        "per_call_limits": {"tokens_input": 196608, "tokens_output": 20000},
        "effect_tables": 0,
        "confirmation_reserved": 0,
        "scope": (
            "离线生成三财保财与四财飘两个窄机会专长；不得读取隐藏题、"
            "运行效果确认、修改规则或发布"
        ),
    })
    (_project_file(_PROJECT_ROOT, BATCH / ".gitignore")).write_text("dispatch-ledger/\n", encoding="utf-8")
    print(json.dumps({"status": "PREPARED", "tasks": rows}, ensure_ascii=False, indent=2))


def verified_tasks() -> list[str]:
    manifest = json.loads((_project_file(_PROJECT_ROOT, BATCH / "manifest.json")).read_text(encoding="utf-8"))
    for path, expected in manifest["inputs"].items():
        if sha256(Path(path)) != expected:
            raise RuntimeError("作者输入摘要漂移：" + path)
    result = []
    for row in manifest["tasks"]:
        text = (_project_file(_PROJECT_ROOT, BATCH / "prompts" / row["task"] / "prompt.txt")).read_text(
            encoding="utf-8"
        )
        if sha256_text(text) != row["prompt_sha256"]:
            raise RuntimeError("提示词摘要漂移：" + row["task"])
        result.append(row["task"])
    return result


def call() -> None:
    """执行两次冻结 GLM 5.3 max 作者调用并核验请求身份与用量。"""

    tasks = verified_tasks()
    if (_project_file(_PROJECT_ROOT, BATCH / "replies")).exists():
        raise SystemExit("回复目录已存在；拒绝重复调用")
    dispatch._expected_request_config = lambda _package: dict(EXPECTED_CONFIG)
    report = dispatch.dispatch(
        BATCH,
        tasks,
        _project_file(_PROJECT_ROOT, BATCH / "replies"),
        _project_file(_PROJECT_ROOT, BATCH / "plan-initial.json"),
        model_patch=str(_project_file(_PROJECT_ROOT, BATCH / "route.patch.yml")),
        timeout_s=1200,
        concurrency=1,
        prompt_dir=_project_file(_PROJECT_ROOT, BATCH / "prompts"),
        kind="r18-opportunity-author-initial",
    )
    rows = []
    problems = []
    for item in sorted(report["calls"], key=lambda row: row["task"]):
        usage = criterion.usage_of(item.get("run_id"))
        values = usage.get("usage") or {}
        clean = (
            item.get("exit_code") == 0
            and item.get("protocol_ok") is True
            and item.get("request_config") == EXPECTED_CONFIG
            and usage.get("source_status") == "OK"
            and isinstance(values.get("inputTokens"), int)
            and isinstance(values.get("outputTokens"), int)
            and values["inputTokens"] <= 196608
            and values["outputTokens"] <= 20000
        )
        rows.append({
            "task": item["task"],
            "run_id": item.get("run_id"),
            "exit_code": item.get("exit_code"),
            "protocol_ok": item.get("protocol_ok"),
            "observed_config": item.get("request_config"),
            "usage": usage,
            "ingestable_channel": clean,
        })
        if not clean:
            problems.append(item["task"])
    write_json(_project_file(_PROJECT_ROOT, BATCH / "call-usage.json"), {
        "schema": "r18-opportunity-author-call-usage/1",
        "calls": rows,
        "problems": problems,
        "total_input_tokens": sum(
            (row["usage"].get("usage") or {}).get("inputTokens", 0) for row in rows
        ),
        "total_output_tokens": sum(
            (row["usage"].get("usage") or {}).get("outputTokens", 0) for row in rows
        ),
    })
    if problems:
        raise RuntimeError("作者通道或用量核验失败：" + ",".join(problems))
    print(json.dumps({"status": "CALLED", "tasks": tasks}, ensure_ascii=False))


def call_retry() -> None:
    """首发零 token 传输失败后，以同题同配置执行一次留痕重试。"""

    tasks = verified_tasks()
    failed = json.loads((_project_file(_PROJECT_ROOT, BATCH / "call-usage.json")).read_text(encoding="utf-8"))
    if failed.get("total_input_tokens") != 0 or failed.get("total_output_tokens") != 0:
        raise RuntimeError("首发已经产生模型用量，不符合零成本传输重试条件")
    if (_project_file(_PROJECT_ROOT, BATCH / "replies-retry01")).exists():
        raise SystemExit("重试回复目录已存在；拒绝重复调用")
    write_json(_project_file(_PROJECT_ROOT, BATCH / "authorization-retry01.json"), {
        "schema": "sitin-authorization/1",
        "authorization_id": "r18-opportunity-author-01-transport-retry01",
        "trusted": True,
        "issued_by": "lead",
        "issued_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "issuance_basis": (
            "K3/P4 首发均为 TRANSPORT Connection error，输入输出 token 均为 0；"
            "原题、原模型、原配置各重试一次"
        ),
        "max_initial_calls": 2,
        "max_repair_calls": 0,
        "max_total_calls": 2,
        "per_call_limits": {"tokens_input": 196608, "tokens_output": 20000},
        "effect_tables": 0,
        "confirmation_reserved": 0,
        "scope": "只重试冻结 K3/P4 原题；不得改题、读取隐藏题、确认或发布",
    })
    dispatch._expected_request_config = lambda _package: dict(EXPECTED_CONFIG)
    report = dispatch.dispatch(
        BATCH,
        tasks,
        _project_file(_PROJECT_ROOT, BATCH / "replies-retry01"),
        _project_file(_PROJECT_ROOT, BATCH / "plan-initial-retry01.json"),
        model_patch=str(_project_file(_PROJECT_ROOT, BATCH / "route.patch.yml")),
        timeout_s=1200,
        concurrency=1,
        prompt_dir=_project_file(_PROJECT_ROOT, BATCH / "prompts"),
        kind="r18-opportunity-author-initial-retry01",
    )
    rows = []
    problems = []
    for item in sorted(report["calls"], key=lambda row: row["task"]):
        usage = criterion.usage_of(item.get("run_id"))
        values = usage.get("usage") or {}
        clean = (
            item.get("exit_code") == 0
            and item.get("protocol_ok") is True
            and item.get("request_config") == EXPECTED_CONFIG
            and usage.get("source_status") == "OK"
            and isinstance(values.get("inputTokens"), int)
            and isinstance(values.get("outputTokens"), int)
            and values["inputTokens"] <= 196608
            and values["outputTokens"] <= 20000
        )
        rows.append({
            "task": item["task"],
            "run_id": item.get("run_id"),
            "exit_code": item.get("exit_code"),
            "protocol_ok": item.get("protocol_ok"),
            "observed_config": item.get("request_config"),
            "usage": usage,
            "ingestable_channel": clean,
        })
        if not clean:
            problems.append(item["task"])
    write_json(_project_file(_PROJECT_ROOT, BATCH / "call-usage-retry01.json"), {
        "schema": "r18-opportunity-author-call-usage/1",
        "retry_of": "call-usage.json",
        "calls": rows,
        "problems": problems,
        "total_input_tokens": sum(
            (row["usage"].get("usage") or {}).get("inputTokens", 0) for row in rows
        ),
        "total_output_tokens": sum(
            (row["usage"].get("usage") or {}).get("outputTokens", 0) for row in rows
        ),
    })
    if problems:
        raise RuntimeError("作者重试通道或用量核验失败：" + ",".join(problems))
    print(json.dumps({"status": "CALLED_RETRY01", "tasks": tasks}, ensure_ascii=False))


def _repair_design(task_id: str) -> str:
    common = """固定公共算法（不得更换）：
1. 完整复制稳定 V2 行为；只在最终胡排序层后增加一个窄覆盖。非触发窗口的全部分数与相对排序逐点等于 V2。
2. 从合法 hu 动作的 immediate_settlement.score_delta[seat] 读取立即胡本座积分。None、布尔、长度非4、非有限即不触发。
3. 从目标 discard 动作的 routes 读取条件路线。只接受 value_coverage == "complete"、value_issues 为已知空序列、每条使用的 route.followup_discard is None、route.shanten == 0、route.support == "conditional_witness"；conditional_settlement.score_delta[seat] 与 useful_tiles[].remaining_estimate 必须为有限数，余量在[0,4]，牌码在全部路线中不得重复。任一项未知即不触发。
4. 公开未知池分母 = visible_state.remaining_tile_count + 其他三个座位的 visible_state.hand_counts；两字段完整、非布尔、有限、分母>0才可用。这不是重算规则，只是玩家视角未知实体数。
5. continue_proxy = Σ(route.score_delta[seat] × useful.remaining_estimate) / unknown_pool。该值只是“下一次本人自摸立即胡”的条件代理，不是完整牌局期望；trace 必须写明这一限制。
6. 触发时只把唯一目标弃牌的最终分设为 V2 最终 hu 分 + 1.0；其他动作仍是 V2 分数。未知锚定和全未知 ABSTAIN 完全保留。
7. trace 只在目标弃牌条目增加一个小字典，记录 structure、triggered、wealth_count、immediate_hu_value、continue_proxy、required_ratio、actual_ratio、score_delta、degrade_reason。
8. 不得按题号、手牌、摸牌或 seed 硬编码；不得宣称这是真实期望、通过或可发布。"""
    if task_id == "K3":
        specific = """K3 固定边界：
- 必须当前有合法 hu、rule_state.baotou is True、准确财富计数恰为3。
- 目标只能是非财神 discard；其 family_progress_entries 必须有 family="baotou"、route_status="witnessed" 且 progress 为 "same" 或 "advance"。
- 在所有满足完整事实的非财神 discard 中取 continue_proxy 最大者；仅当 continue_proxy >= immediate_hu_value × 1.25 才触发。1.25 是未建模他家先胡/轮转风险的25%证据缓冲，不得改小。
- 四财、弃财神、普通无胡窗口全部精确回退 V2。"""
    else:
        specific = """P4 固定边界：
- 必须当前有合法 hu、rule_state.baotou is True、准确财富计数恰为4。
- 目标只能是 discard:<wealth_god>；其 family_progress_entries 必须有 family="chain"、route_status="witnessed"、progress="advance"。
- 仅当 continue_proxy >= immediate_hu_value × 1.50 才触发。1.50 是未建模他家先胡/轮转风险的50%证据缓冲，不得改小。
- 三财、非财神弃牌、普通无胡窗口全部精确回退 V2。"""
    return common + "\n\n" + specific


def prepare_repair() -> None:
    """把两次 max-token 截断收缩为固定算法的短源码交付题。"""

    usage = json.loads((_project_file(_PROJECT_ROOT, BATCH / "call-usage-retry01.json")).read_text(encoding="utf-8"))
    if usage.get("total_output_tokens") != 40000:
        raise RuntimeError("两题不是各自触及 20000 输出上限的截断状态")
    if any(row.get("exit_code") == 0 for row in usage["calls"]):
        raise RuntimeError("存在已完成首答，不应进入双题交付修复")
    if (_project_file(_PROJECT_ROOT, BATCH / "repair-prompts")).exists():
        raise SystemExit("修复题面已存在；拒绝覆盖")
    parent = V2.read_text(encoding="utf-8")
    rows = []
    for task_id in verified_tasks():
        prompt = "\n".join([
            "这是 max-token 截断后的唯一交付修复。上次调用只有内部推理、没有最终答复。",
            "算法已由监督器冻结；本次只把固定算法写成完整短源码，不得改变触发域、",
            "风险比率、回退或父代其他公式。不要分析，不要使用工具。",
            "",
            "【固定算法】",
            _repair_design(task_id),
            "",
            "【输出格式】",
            "严格只输出：花括号内一句中文机制；一个 json 围栏，恰含 trigger/changed_branches/expected_direction/counterexample 四个非空短字符串；一个完整 python 围栏。",
            "Python 不得 import；只能有模块 docstring 和 score_actions(view)；以父代作最小修改，建议不超过280行；必须返回全部合法动作且通过受限子集。",
            "",
            "【稳定 V2 完整源码】",
            gen.FENCE + "python",
            parent.rstrip("\n"),
            gen.FENCE,
            "",
            "现在直接交付完整结果。",
        ])
        target = _project_file(_PROJECT_ROOT, BATCH / "repair-prompts" / task_id)
        target.mkdir(parents=True, exist_ok=True)
        (target / "prompt.txt").write_text(prompt, encoding="utf-8")
        rows.append({
            "task": task_id,
            "prompt_sha256": sha256_text(prompt),
            "prompt_chars": len(prompt),
            "fixed_design_sha256": sha256_text(_repair_design(task_id)),
        })
    settings = """llm-pi-ai:
  providers:
    zai-coding-cn:
      apiKeyEnv: ZAI_CODING_CN_API_KEY
      models:
        - id: glm-5.3
          name: GLM-5.3
          contextWindow: 1000000
          maxTokens: 16000

agent-default-model:
  provider: zai-coding-cn
  model: glm-5.3
  reasoningEffort: low
"""
    (_project_file(_PROJECT_ROOT, BATCH / "settings-repair.yaml")).write_text(settings, encoding="utf-8")
    (_project_file(_PROJECT_ROOT, BATCH / "route.repair.patch.yml")).write_text(
        "- id: settings\n  config:\n    path: " + str(_project_file(_PROJECT_ROOT, BATCH / "settings-repair.yaml"))
        + "\n    watch: false\n- id: agent-default-model\n  config:\n"
        + "    provider: zai-coding-cn\n    model: glm-5.3\n",
        encoding="utf-8",
    )
    write_json(_project_file(_PROJECT_ROOT, BATCH / "repair-manifest.json"), {
        "schema": "r18-opportunity-delivery-repair/1",
        "reason": "K3/P4 初答均耗尽 20000 输出 token，只有推理块且没有最终答复",
        "expected_request_config": REPAIR_CONFIG,
        "tasks": rows,
        "parent_sha256": sha256_text(parent),
        "max_repairs": 2,
        "effect_feedback_used": False,
        "hidden_input_used": False,
    })
    write_json(_project_file(_PROJECT_ROOT, BATCH / "authorization-repair01.json"), {
        "schema": "sitin-authorization/1",
        "authorization_id": "r18-opportunity-author-01-delivery-repair01",
        "trusted": True,
        "issued_by": "lead",
        "issued_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "issuance_basis": (
            "两题首答均达到输出上限且没有最终答复；使用原授权中的每题一次修复额度，"
            "只交付监督器冻结的同方向保守机制"
        ),
        "max_initial_calls": 0,
        "max_repair_calls": 2,
        "max_total_calls": 2,
        "per_call_limits": {"tokens_input": 65536, "tokens_output": 16000},
        "effect_tables": 0,
        "confirmation_reserved": 0,
        "scope": "只交付冻结 K3/P4 短源码；不得读隐藏题、改机制、确认或发布",
    })
    print(json.dumps({"status": "REPAIR_PREPARED", "tasks": rows}, ensure_ascii=False, indent=2))


def call_repair() -> None:
    """执行两次固定机制的低推理交付修复并核验通道。"""

    manifest = json.loads((_project_file(_PROJECT_ROOT, BATCH / "repair-manifest.json")).read_text(encoding="utf-8"))
    tasks = []
    for row in manifest["tasks"]:
        text = (_project_file(_PROJECT_ROOT, BATCH / "repair-prompts" / row["task"] / "prompt.txt")).read_text(
            encoding="utf-8"
        )
        if sha256_text(text) != row["prompt_sha256"]:
            raise RuntimeError("修复题面漂移：" + row["task"])
        tasks.append(row["task"])
    if (_project_file(_PROJECT_ROOT, BATCH / "replies-repair01")).exists():
        raise SystemExit("修复回复目录已存在；拒绝重复调用")
    dispatch._expected_request_config = lambda _package: dict(REPAIR_CONFIG)
    report = dispatch.dispatch(
        BATCH,
        tasks,
        _project_file(_PROJECT_ROOT, BATCH / "replies-repair01"),
        _project_file(_PROJECT_ROOT, BATCH / "plan-repair01.json"),
        model_patch=str(_project_file(_PROJECT_ROOT, BATCH / "route.repair.patch.yml")),
        timeout_s=1200,
        concurrency=1,
        prompt_dir=_project_file(_PROJECT_ROOT, BATCH / "repair-prompts"),
        kind="r18-opportunity-delivery-repair01",
    )
    rows = []
    problems = []
    for item in sorted(report["calls"], key=lambda row: row["task"]):
        usage = criterion.usage_of(item.get("run_id"))
        values = usage.get("usage") or {}
        clean = (
            item.get("exit_code") == 0
            and item.get("protocol_ok") is True
            and item.get("request_config") == REPAIR_CONFIG
            and usage.get("source_status") == "OK"
            and isinstance(values.get("inputTokens"), int)
            and isinstance(values.get("outputTokens"), int)
            and values["inputTokens"] <= 65536
            and values["outputTokens"] <= 16000
        )
        rows.append({
            "task": item["task"],
            "run_id": item.get("run_id"),
            "exit_code": item.get("exit_code"),
            "protocol_ok": item.get("protocol_ok"),
            "observed_config": item.get("request_config"),
            "usage": usage,
            "ingestable_channel": clean,
        })
        if not clean:
            problems.append(item["task"])
    write_json(_project_file(_PROJECT_ROOT, BATCH / "repair-call-usage.json"), {
        "schema": "r18-opportunity-repair-call-usage/1",
        "calls": rows,
        "problems": problems,
        "total_input_tokens": sum(
            (row["usage"].get("usage") or {}).get("inputTokens", 0) for row in rows
        ),
        "total_output_tokens": sum(
            (row["usage"].get("usage") or {}).get("outputTokens", 0) for row in rows
        ),
    })
    if problems:
        raise RuntimeError("交付修复通道或用量核验失败：" + ",".join(problems))
    print(json.dumps({"status": "REPAIR_CALLED", "tasks": tasks}, ensure_ascii=False))


def ingest() -> None:
    """解析完整源码并执行静态白名单与受限装载预检。"""

    tasks = verified_tasks()
    if (_project_file(_PROJECT_ROOT, BATCH / "repair-call-usage.json")).exists():
        usage_path = _project_file(_PROJECT_ROOT, BATCH / "repair-call-usage.json")
        reply_root = _project_file(_PROJECT_ROOT, BATCH / "replies-repair01")
    elif (_project_file(_PROJECT_ROOT, BATCH / "call-usage-retry01.json")).exists():
        usage_path = _project_file(_PROJECT_ROOT, BATCH / "call-usage-retry01.json")
        reply_root = _project_file(_PROJECT_ROOT, BATCH / "replies-retry01")
    else:
        usage_path = _project_file(_PROJECT_ROOT, BATCH / "call-usage.json")
        reply_root = _project_file(_PROJECT_ROOT, BATCH / "replies")
    usage = json.loads(usage_path.read_text(encoding="utf-8"))
    channel = {row["task"]: row["ingestable_channel"] for row in usage["calls"]}
    rows = []
    for task_id in tasks:
        raw = (reply_root / f"{task_id}.txt").read_text(encoding="utf-8")
        parsed = gen.parse_action_value_reply(raw)
        code = parsed.get("code") or ""
        precheck = gen.precheck_action_value_candidate(code) if code else {
            "ok": False,
            "problems": ["没有可预检源码"],
        }
        load_error = None
        if code and precheck.get("ok") is True:
            try:
                ActionValueScorer("r18-" + task_id, code)
            except Exception as exc:  # noqa: BLE001 - 证据保留实际装载错误
                load_error = type(exc).__name__ + ": " + str(exc)
        accepted = (
            channel.get(task_id) is True
            and parsed.get("status") == "ok"
            and precheck.get("ok") is True
            and load_error is None
        )
        target = _project_file(_PROJECT_ROOT, BATCH / "generations" / task_id)
        target.mkdir(parents=True, exist_ok=True)
        (target / "reply_raw.txt").write_text(raw, encoding="utf-8")
        if code:
            (target / "candidate.py").write_text(
                code.rstrip("\n") + "\n", encoding="utf-8"
            )
        write_json(target / "parsed.json", {
            key: value for key, value in parsed.items() if key != "code"
        } | ({"code_sha256": sha256_text(code)} if code else {}))
        write_json(target / "precheck.json", precheck)
        row = {
            "task": task_id,
            "parse_status": parsed.get("status"),
            "static_precheck": precheck.get("ok"),
            "load_error": load_error,
            "accepted_for_development_preflight": accepted,
            "code_sha256": sha256_text(code) if code else None,
            "problems": list(parsed.get("problems") or [])
            + list(precheck.get("problems") or [])
            + ([load_error] if load_error else []),
        }
        write_json(target / "record.json", row)
        rows.append(row)
    write_json(_project_file(_PROJECT_ROOT, BATCH / "ingest-summary.json"), {
        "schema": "r18-opportunity-author-ingest/1",
        "rows": rows,
        "accepted_for_development_preflight": [
            row["task"] for row in rows
            if row["accepted_for_development_preflight"]
        ],
        "repair_eligible": [
            row["task"] for row in rows
            if not row["accepted_for_development_preflight"]
        ],
        "hidden_evaluation_started": False,
    })
    print(json.dumps(
        json.loads((_project_file(_PROJECT_ROOT, BATCH / "ingest-summary.json")).read_text(encoding="utf-8")),
        ensure_ascii=False,
        indent=2,
    ))


async def _evaluate_development() -> dict[str, object]:
    normalized = _project_file(_PROJECT_ROOT, BATCH / "normalized-v2-ingest-summary.json")
    if normalized.exists():
        accepted = json.loads(normalized.read_text(encoding="utf-8"))[
            "accepted_for_development_preflight"
        ]
        source_suffix = Path("normalized-v2/candidate.py")
    else:
        accepted = json.loads(
            (_project_file(_PROJECT_ROOT, BATCH / "ingest-summary.json")).read_text(encoding="utf-8")
        )["accepted_for_development_preflight"]
        source_suffix = Path("candidate.py")
    cases = development_cases()
    baseline = ComparableHeuristicPolicyV2()
    outputs = {}
    baseline_rows = None
    for task_id in accepted:
        source = (_project_file(_PROJECT_ROOT, BATCH / "generations" / task_id / source_suffix)).read_text(
            encoding="utf-8"
        )
        policy = ActionValuePolicy(ActionValueScorer("r18-" + task_id, source))
        rows = []
        for case in cases:
            rows.append(await evaluate_pair(policy, baseline, case, bank.budget))
        if baseline_rows is None:
            baseline_rows = [asdict(row.baseline) for row in rows]
        summary = summarize_family(
            rows, family="multi_wealth_baotou", split="development"
        )
        changed = []
        regressions = []
        improvements = []
        for row in rows:
            item = asdict(row)
            if row.candidate.chosen_action_key != row.baseline.chosen_action_key:
                changed.append(item)
            if (
                row.capability_gain is not None
                and row.capability_gain < 0
            ):
                regressions.append(item)
            if (
                row.capability_gain is not None
                and row.capability_gain > 0
            ):
                improvements.append(item)
        outputs[task_id] = {
            "candidate_sha256": sha256_text(source),
            "summary": asdict(summary),
            "changed_count": len(changed),
            "improved_count": len(improvements),
            "regressed_count": len(regressions),
            "rows": [asdict(row) for row in rows],
        }
    return {
        "schema": "r18-opportunity-author-development-preflight/1",
        "candidate_count": len(outputs),
        "case_count": len(cases),
        "split": "development",
        "hidden_evaluation_started": False,
        "baseline_rows": baseline_rows or [],
        "candidates": outputs,
    }


def evaluate_development() -> None:
    """只跑作者可见开发分割；隐藏题继续密封。"""

    target = _project_file(_PROJECT_ROOT, BATCH / (
        "development-preflight-v2.json"
        if (BATCH / "normalized-v2-ingest-summary.json").exists()
        else "development-preflight.json"
    ))
    if target.exists():
        raise SystemExit("开发预检已存在；拒绝覆盖")
    result = asyncio.run(_evaluate_development())
    write_json(target, result)
    compact = {
        task: {
            "summary": row["summary"],
            "changed_count": row["changed_count"],
            "improved_count": row["improved_count"],
            "regressed_count": row["regressed_count"],
        }
        for task, row in result["candidates"].items()
    }
    print(json.dumps(compact, ensure_ascii=False, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "operation",
        choices=(
            "prepare",
            "call",
            "call-retry",
            "prepare-repair",
            "call-repair",
            "ingest",
            "evaluate-development",
        ),
    )
    args = parser.parse_args()
    globals()[args.operation.replace("-", "_")]()


if __name__ == "__main__":
    main()
