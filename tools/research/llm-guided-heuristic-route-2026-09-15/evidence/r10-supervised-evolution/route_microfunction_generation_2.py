"""R10 路线微函数第二代：用比较反馈生成幅度恢复与动作族分治提案。"""
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
import re
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


BATCH = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/route-microfunction-generation-02-20260921')
ANALYSIS = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/route-microfunction-contrastive-01-20260921/outcome-diagnostic-01/outcome-feature-analysis.json')
NEW_SOURCE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/route-microfunction-contrastive-01-20260921/new-source-01/summary.json')
PARENT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/route-microfunction-contrastive-01-20260921/behavior-preflight-v2/configurations/r2-cfg-02/candidate.py')
EXPECTED_CONFIG = {
    "provider": "zai-coding-cn",
    "model": "glm-5.3",
    "reasoningEffort": "high",
    "maxTokens": 4096,
}
TASKS = {
    "C1": (
        "恢复幅度：优先选择 raw_threshold、margin、hybrid 中能区分微弱相对第一名与"
        "强路线的结构；不得把同窗第一名再次无条件映射为1。"
    ),
    "C2": (
        "动作族分治：在同一置信映射上分别给 discard 与 chi/peng 设上限；副露改变"
        "后续自由度，应提出可证伪的保守上限，不得臆造杭麻规则。"
    ),
}
ALLOWED_FAMILIES = {"raw_threshold", "margin", "hybrid"}
ALLOWED_CLAIM_POLICIES = {"same", "half", "quarter", "zero"}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def prompt(task_id: str, direction: str) -> str:
    facts = {
        "stable_parent": "ComparableHeuristicPolicyV2，零效应控制，合法动作与规则事实均来自hangma",
        "current_structural_parent": {
            "sha256": sha256(PARENT),
            "mechanism": "同窗 route_raw 最高动作获得固定 +8；其他动作 +0",
            "development": "旧开发H/M各28根保守等权差+0.035714",
            "new_source": "H/M各128根保守等权差+0.018555，95%区间[-0.009264,+0.046373]",
            "disposition": "方向复现但不确定；只可作结构父代，不可确认或发布",
        },
        "diagnostic": {
            "deduplicated_changed_views": 309,
            "all_route_bonuses": 8,
            "route_raw": {"min": -0.2811, "median": -0.0723, "max": 1.0},
            "route_span": {"min": 0.0147, "median": 0.0741, "max": 1.0036},
            "base_gap": {"min": 0, "median": 3, "max": 8},
            "changes": {"discard": 171, "chi": 94, "peng": 43, "pass": 1},
            "warning": "正负极值根差异是事后相关，不可当动作标签或因果事实",
        },
        "available_inputs": {
            "route_raw": "已校验动作内最强条件路线无量纲原值，范围夹到[-1,1]",
            "route_margin": "最高原值减第二高原值；不足两个已知路线动作时为0",
            "raw_floor": "raw_threshold/hybrid 的可搜索起点",
            "raw_width": "把 route_raw-raw_floor 映射到[0,1]所需宽度",
            "margin_ref": "把 route_margin 映射到[0,1]所需参考宽度",
            "discard_cap": "弃牌路线加分上限",
            "claim_policy": "吃碰上限相对弃牌上限的离散策略",
        },
    }
    schema = {
        "schema": "r10-route-confidence-proposal/1",
        "id": "lowercase-short-id",
        "hypothesis": "一句可证伪机制假设",
        "family": "raw_threshold | margin | hybrid",
        "raw_floor": -0.12,
        "raw_width": 0.30,
        "margin_ref": 0.15,
        "discard_cap": 8.0,
        "claim_policy": "same | half | quarter | zero",
        "reasoning": "说明如何恢复幅度，以及为何不把代理称作概率或期望分",
        "falsifier": "真实观察预检或分段完整阶段中什么结果否定该结构",
    }
    constraints = [
        "只输出一个严格JSON对象，不要Markdown、代码块或额外文字。",
        "键必须与schema完全一致；family与claim_policy必须取枚举值。",
        "-1<=raw_floor<=0.25；0.02<=raw_width<=1.5；0.01<=margin_ref<=1.5；0<=discard_cap<=12。",
        "raw_threshold置信度定义为clip((route_raw-raw_floor)/raw_width,0,1)。",
        "margin置信度定义为clip(route_margin/margin_ref,0,1)。",
        "hybrid置信度定义为上述两项的乘积；不得另创公式。",
        "claim_policy只控制chi/peng上限：same=1、half=0.5、quarter=0.25、zero=0倍discard_cap。",
        "不得读取WorldState、隐藏牌墙、对手暗牌、终局标签、H/M身份或事后效果类。",
        "不得修改合法动作、向听、有效牌或条件结算；未知路线不给奖励。",
        "不得宣称support/wall、route_raw或route_margin是真实概率、期望积分或数学下界。",
        "这是待预检结构提案，不得宣称已提分、已确认、准入或可发布。",
    ]
    return "\n".join([
        "你是杭麻离线启发式演化的有界微函数作者。监督器将机械装配和独立评价你的提案。",
        "本题方向：" + direction,
        "",
        "【已冻结比较反馈】",
        json.dumps(facts, ensure_ascii=False, indent=2),
        "",
        "【硬约束】",
        "\n".join("- " + item for item in constraints),
        "",
        "【严格输出形状；示例数值不得照抄】",
        json.dumps(schema, ensure_ascii=False, indent=2),
    ])


def prepare() -> None:
    if BATCH.exists():
        raise SystemExit("第二代微函数生成目录已存在；拒绝覆盖")
    analysis = json.loads(ANALYSIS.read_text(encoding="utf-8"))
    source = json.loads(NEW_SOURCE.read_text(encoding="utf-8"))
    if analysis.get("all_changed_bonuses_equal") is not True:
        raise ValueError("固定满额诊断前提漂移")
    if source.get("disposition") != "INCONCLUSIVE_DEVELOPMENT":
        raise ValueError("新来源处置前提漂移")
    BATCH.mkdir(parents=True)
    task_rows = []
    for task_id, direction in TASKS.items():
        text = prompt(task_id, direction)
        target = _project_file(_PROJECT_ROOT, BATCH / "prompts" / task_id)
        target.mkdir(parents=True)
        (target / "prompt.txt").write_text(text, encoding="utf-8")
        task_rows.append({
            "task_id": task_id,
            "direction": direction,
            "prompt_sha256": sha256_text(text),
            "prompt_chars": len(text),
        })
    settings = """# R10 第二代路线置信微函数；短JSON输出，禁工具。
llm-pi-ai:
  providers:
    zai-coding-cn:
      apiKeyEnv: ZAI_CODING_CN_API_KEY
      models:
        - id: glm-5.3
          name: GLM-5.3
          contextWindow: 1000000
          maxTokens: 4096

agent-default-model:
  provider: zai-coding-cn
  model: glm-5.3
  reasoningEffort: high
"""
    (_project_file(_PROJECT_ROOT, BATCH / "settings.yaml")).write_text(settings, encoding="utf-8")
    (_project_file(_PROJECT_ROOT, BATCH / "route.patch.yml")).write_text(
        "- id: settings\n  config:\n    path: " + str(_project_file(_PROJECT_ROOT, BATCH / "settings.yaml"))
        + "\n    watch: false\n- id: agent-default-model\n  config:\n"
        + "    provider: zai-coding-cn\n    model: glm-5.3\n",
        encoding="utf-8",
    )
    write_json(_project_file(_PROJECT_ROOT, BATCH / "manifest.json"), {
        "schema": "r10-route-confidence-author-batch/1",
        "created_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "target_model": {"provider": "zai-coding-cn", "model": "glm-5.3"},
        "expected_request_config": EXPECTED_CONFIG,
        "inputs": {
            "parent": {"path": str(PARENT), "sha256": sha256(PARENT)},
            "analysis": {"path": str(ANALYSIS), "sha256": sha256(ANALYSIS)},
            "new_source": {"path": str(NEW_SOURCE), "sha256": sha256(NEW_SOURCE)},
        },
        "tasks": task_rows,
        "effect_evaluation_started": False,
        "confirmation_reserved": 0,
    })
    write_json(_project_file(_PROJECT_ROOT, BATCH / "authorization.json"), {
        "schema": "sitin-authorization/1",
        "authorization_id": "r10-route-confidence-02-20260921",
        "trusted": True,
        "issued_by": "Codex root",
        "issued_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "issuance_basis": (
            "用户授权API用量上限前由root安排zai-coding-cn GLM5.3，并要求受挫时"
            "回顾参考文献；本批依据ReEvo比较反馈生成两个有界结构提案。"
        ),
        "route": "offline_route_confidence_authoring",
        "max_initial_calls": 2,
        "max_repair_calls": 0,
        "max_total_calls": 2,
        "per_call_limits": {"tokens_input": 196608, "tokens_output": 4096},
        "effect_tables": 0,
        "confirmation_reserved": 0,
        "autonomous_admission": False,
        "scope": "只生成枚举内置信结构与有界参数；不得确认或发布",
    })
    (_project_file(_PROJECT_ROOT, BATCH / ".gitignore")).write_text("dispatch-ledger/\n", encoding="utf-8")
    print(json.dumps({"status": "PREPARED", "tasks": task_rows}, ensure_ascii=False, indent=2))


def verified_tasks() -> list[str]:
    manifest = json.loads((_project_file(_PROJECT_ROOT, BATCH / "manifest.json")).read_text(encoding="utf-8"))
    for item in manifest["inputs"].values():
        if sha256(Path(item["path"])) != item["sha256"]:
            raise ValueError("生成输入摘要漂移：" + item["path"])
    result = []
    for row in manifest["tasks"]:
        text = (_project_file(_PROJECT_ROOT, BATCH / "prompts" / row["task_id"] / "prompt.txt")).read_text(encoding="utf-8")
        if sha256_text(text) != row["prompt_sha256"]:
            raise ValueError("提示词摘要漂移：" + row["task_id"])
        result.append(row["task_id"])
    return result


def call() -> None:
    replies = _project_file(_PROJECT_ROOT, BATCH / "replies")
    if replies.exists():
        raise SystemExit("回复目录已存在；拒绝重复调用")
    dispatch._expected_request_config = lambda _package: dict(EXPECTED_CONFIG)
    report = dispatch.dispatch(
        BATCH, verified_tasks(), replies, _project_file(_PROJECT_ROOT, BATCH / "plan-initial.json"),
        model_patch=str(_project_file(_PROJECT_ROOT, BATCH / "route.patch.yml")), timeout_s=900, concurrency=1,
        prompt_dir=_project_file(_PROJECT_ROOT, BATCH / "prompts"), kind="route-confidence-initial-2",
    )
    rows = []
    for item in sorted(report["calls"], key=lambda row: row["task"]):
        usage = criterion.usage_of(item.get("run_id"))
        values = usage.get("usage") or {}
        clean = (
            item.get("exit_code") == 0 and item.get("protocol_ok") is True
            and item.get("request_config") == EXPECTED_CONFIG
            and usage.get("source_status") == "OK"
            and isinstance(values.get("inputTokens"), int)
            and isinstance(values.get("outputTokens"), int)
            and values["inputTokens"] <= 196608 and values["outputTokens"] <= 4096
        )
        rows.append({
            "task": item["task"], "run_id": item.get("run_id"),
            "exit_code": item.get("exit_code"), "protocol_ok": item.get("protocol_ok"),
            "observed_config": item.get("request_config"), "usage": usage,
            "ingestable_channel": clean,
        })
    write_json(_project_file(_PROJECT_ROOT, BATCH / "call-usage.json"), {
        "schema": "r10-route-confidence-call-usage/1",
        "calls": rows,
        "total_input_tokens": sum((row["usage"].get("usage") or {}).get("inputTokens", 0) for row in rows),
        "total_output_tokens": sum((row["usage"].get("usage") or {}).get("outputTokens", 0) for row in rows),
        "problems": [row["task"] for row in rows if not row["ingestable_channel"]],
    })
    print(json.dumps({"status": "CALLED", "calls": rows}, ensure_ascii=False, indent=2))


def parse_reply(raw: str) -> dict:
    text = raw.strip()
    if text.startswith("```"):
        match = re.fullmatch(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL)
        if match is None:
            raise ValueError("围栏回复不是单一JSON对象")
        text = match.group(1)
    value = json.loads(text)
    expected = {"schema", "id", "hypothesis", "family", "raw_floor", "raw_width",
                "margin_ref", "discard_cap", "claim_policy", "reasoning", "falsifier"}
    if not isinstance(value, dict) or set(value) != expected:
        raise ValueError("JSON键集合不匹配")
    if value["schema"] != "r10-route-confidence-proposal/1":
        raise ValueError("schema不匹配")
    if not isinstance(value["id"], str) or re.fullmatch(r"[a-z][a-z0-9-]{2,40}", value["id"]) is None:
        raise ValueError("id格式非法")
    for key in ("hypothesis", "reasoning", "falsifier"):
        if not isinstance(value[key], str) or not value[key].strip() or len(value[key]) > 1500:
            raise ValueError(key + "必须是非空短字符串")
    if value["family"] not in ALLOWED_FAMILIES:
        raise ValueError("family不在枚举内")
    if value["claim_policy"] not in ALLOWED_CLAIM_POLICIES:
        raise ValueError("claim_policy不在枚举内")
    bounds = {
        "raw_floor": (-1.0, 0.25), "raw_width": (0.02, 1.5),
        "margin_ref": (0.01, 1.5), "discard_cap": (0.0, 12.0),
    }
    result = dict(value)
    for key, (low, high) in bounds.items():
        item = value[key]
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            raise ValueError(key + "必须是数值")
        number = float(item)
        if number - number != 0 or not low <= number <= high:
            raise ValueError(key + "越界")
        result[key] = number
    return result


def ingest() -> None:
    usage = json.loads((_project_file(_PROJECT_ROOT, BATCH / "call-usage.json")).read_text(encoding="utf-8"))
    by_task = {row["task"]: row for row in usage["calls"]}
    rows = []
    for task_id in verified_tasks():
        raw = (_project_file(_PROJECT_ROOT, BATCH / "replies" / (task_id + ".txt"))).read_text(encoding="utf-8")
        target = _project_file(_PROJECT_ROOT, BATCH / "generations" / task_id)
        target.mkdir(parents=True)
        (target / "reply_raw.txt").write_text(raw, encoding="utf-8")
        proposal = None
        problems = []
        try:
            proposal = parse_reply(raw)
        except Exception as exc:
            problems.append(type(exc).__name__ + ": " + str(exc))
        if proposal is not None:
            write_json(target / "proposal.json", proposal)
        accepted = by_task.get(task_id, {}).get("ingestable_channel") is True and not problems
        row = {
            "task": task_id,
            "channel_ok": by_task.get(task_id, {}).get("ingestable_channel") is True,
            "proposal_ok": proposal is not None,
            "accepted_for_mechanical_assembly": accepted,
            "proposal_sha256": (
                sha256_text(json.dumps(proposal, ensure_ascii=False, sort_keys=True))
                if proposal is not None else None
            ),
            "problems": problems,
        }
        write_json(target / "record.json", row)
        rows.append(row)
    write_json(_project_file(_PROJECT_ROOT, BATCH / "ingest-summary.json"), {
        "schema": "r10-route-confidence-ingest/1",
        "tasks": rows,
        "accepted": [row["task"] for row in rows if row["accepted_for_mechanical_assembly"]],
        "closed": [row["task"] for row in rows if not row["accepted_for_mechanical_assembly"]],
        "repair_calls_allowed": 0,
        "effect_evaluation_started": False,
        "confirmation_reserved": 0,
    })
    print(json.dumps({"status": "INGESTED", "tasks": rows}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("prepare", "call", "ingest"))
    args = parser.parse_args()
    {"prepare": prepare, "call": call, "ingest": ingest}[args.operation]()
