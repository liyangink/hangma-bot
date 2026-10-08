"""R10 条件路线价值微函数第一批：短表达式作者、机械装配与生成端验收。

本工具把稳定 V2 作为不可变骨架。模型只提交一个受限算术表达式和六个参数配置；
监督代码负责字段校验、覆盖退化、幅度限制、源码装配和行为预检前的静态检查。
它不运行完整桌赛，不读取效果标签，也不改变规则、协议或发布状态。
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
import ast
import datetime as dt
import hashlib
import json
import re
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
from hangma_bot.policy.action_value_executor import static_check  # noqa: E402


BATCH = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/route-microfunction-01-20260921')
V2 = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/v2-parent-revalidation-20260920/parent/generation/candidate.py')
ROUTE_PARENT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/strong-seeds-20260920/route-terra-max/run/iterations/iter-01/generation/candidate.py')
EXPECTED_V2_SHA256 = "a0c389b3a4757a38febf5ca6bf16e9c4779159df0c15b82d2e804e1f4ac9638f"
EXPECTED_ROUTE_PARENT_SHA256 = "3dba23031f57343b57c5f87e163c7aa3dbe55adfb517f28bb2fcefa14daaa795"
EXPECTED_CONFIG = {
    "provider": "zai-coding-cn",
    "model": "glm-5.3",
    "reasoningEffort": "high",
    "maxTokens": 8192,
}
TASKS = {
    "M1": {
        "name": "support-density-settlement",
        "direction": (
            "把条件结算强度与动作级可见支持密度结合。表达式应随 self_delta、fan、"
            "direct_support 非减，随 wall_remaining 非增；允许饱和，但不能把 support/wall "
            "称作概率。重点分辨同为听牌但条件结算与可达支持不同的动作。"
        ),
    },
    "M2": {
        "name": "centered-route-premium",
        "direction": (
            "构造有中心的路线溢价：低结算/低支持可为轻微负值，高结算/高支持为正值，"
            "避免像 T3 那样给所有路线动作同向小奖励。仍须对 self_delta、fan、"
            "direct_support 单调非减，对 wall_remaining 单调非增。"
        ),
    },
}
ALLOWED_NAMES = {
    "direct_support", "self_delta", "fan", "wall_remaining", "shape",
}
ALLOWED_CALLS = {"min", "max", "abs"}
ALLOWED_EXPR_NODES = (
    ast.Expression, ast.BinOp, ast.UnaryOp, ast.BoolOp, ast.Compare, ast.IfExp,
    ast.Call, ast.Name, ast.Load, ast.Constant, ast.Add, ast.Sub, ast.Mult,
    ast.Div, ast.USub, ast.UAdd, ast.And, ast.Or, ast.Not, ast.Eq, ast.NotEq,
    ast.Lt, ast.LtE, ast.Gt, ast.GtE,
)
FENCE = "```"


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _settings_files() -> None:
    settings = """# R10 条件路线价值微函数第一批；短输出，禁工具。
llm-pi-ai:
  providers:
    zai-coding-cn:
      apiKeyEnv: ZAI_CODING_CN_API_KEY
      models:
        - id: glm-5.3
          name: GLM-5.3
          contextWindow: 1000000
          maxTokens: 8192

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


def _prompt(task_id: str, spec: dict) -> str:
    schema = {
        "schema": "r10-route-microfunction-proposal/1",
        "id": "lowercase-short-id",
        "hypothesis": "一句可证伪机制假设",
        "expression": "只含指定变量、算术、比较、条件表达式和min/max/abs的Python表达式",
        "default": {"scale": 8.0, "shape": 24.0, "cap": 16.0},
        "configs": [
            {"scale": 0.0, "shape": 24.0, "cap": 16.0},
            {"scale": 4.0, "shape": 24.0, "cap": 8.0},
            {"scale": 8.0, "shape": 24.0, "cap": 16.0},
            {"scale": 12.0, "shape": 24.0, "cap": 24.0},
            {"scale": 8.0, "shape": 12.0, "cap": 16.0},
            {"scale": 8.0, "shape": 48.0, "cap": 16.0},
        ],
        "bounds": "为何表达式经固定[-1,1]夹取和scale/cap后有界",
        "falsifier": "什么真实行为或分段桌赛结果会否定该假设",
    }
    facts = {
        "stable_v2": {
            "sha256": EXPECTED_V2_SHA256,
            "direct_score": "-100*shanten_after + sum(useful_tiles.remaining_estimate)",
            "route_use": "只把非空routes视为已有规则事实；不读取结算数值",
        },
        "prior_route_parent": {
            "sha256": EXPECTED_ROUTE_PARENT_SHA256,
            "research_only": True,
            "formula": "best route: -90*shanten + route_support + 0.10*self_delta",
            "old_first_panel": "H +0.125, M +0.125，各8来源根；区间跨0、无独立确认",
            "later_panel": "H +0.0625, M -0.234375，相对V2为负；不能继承旧成绩",
        },
        "closed_t3": {
            "formula": "最大正self_delta经饱和后只加正分",
            "real_views": 226,
            "score_changes": 43,
            "preferred_changes": 0,
            "lesson": "不能再只做self_delta的小幅同向奖励",
        },
        "frozen_real_distribution": {
            "views": 226,
            "views_with_routes": 43,
            "route_actions": 175,
            "routes": 208,
            "coverage": "175/175 route actions 为 complete",
            "route_support": {"min": 4, "p25": 9, "median": 12, "p75": 15, "p90": 19, "max": 92},
            "self_delta_counts": {"10": 113, "20": 17, "24": 64, "48": 14},
            "fan_counts": {"1": 177, "2": 31},
            "wall_remaining": {"min": 24, "median": 55, "max": 78},
            "v2_gap_to_best": {"median": -5, "p75": 0, "within_8": 115, "within_16": 142},
        },
    }
    constraints = [
        "你只设计一个微函数表达式，不输出完整score_actions、代码块、Markdown或额外文字。",
        "输出必须是单个严格JSON对象，键和值形状严格匹配给定schema。",
        "expression的可用变量只有 direct_support, self_delta, fan, wall_remaining, shape；"
        "可用函数只有min/max/abs；可用运算只有+ - * /、比较、and/or/not与条件表达式。",
        "宿主只在动作value_coverage=complete、墙余量为正、动作直接support完整、"
        "路线support为正、route.shanten=0、conditions.draw_kind合法、四座结算与self_delta一致时调用。",
        "宿主逐路线算expression，先夹到[-1,1]，乘scale，再夹到[-cap,+cap]，动作取最大路线值；"
        "不同路线不相加。scale=0机械保证逐分退化到稳定V2。",
        "route_support只作正支持合法门，不进入表达式；动作级direct_support避免同一路线被拆分后数值变化。",
        "必须保持同一路线拆分/重排不变，不得把不同后继相加，不得把未知当0，不得解析basis/details文字。",
        "support/wall只能叫可见密度代理，不能声称真实摸牌概率、期望积分或下界。",
        "不得使用WorldState、隐藏牌墙、对手暗牌、终局标签、实验根、H/M身份、点炮或其他麻将规则。",
        "表达式在direct_support>0,self_delta>0,fan>0,wall_remaining>0,shape>0域内必须有限；"
        "对self_delta、fan、direct_support单调非减，对wall_remaining单调非增。",
        "configs恰好6个互异配置，均完整含scale/shape/cap；必须含且只含一个scale=0；"
        "default必须恰好等于configs之一。0<=scale<=48，0<shape<=128，0<=cap<=48。",
        "这是离线候选，不得宣称已提分、准入、确认或可发布。",
    ]
    return "\n".join([
        "你是杭麻离线启发式演化的微函数作者。目标是提高有效提案密度，输出将由程序机械装配和评测。",
        "本题方向：" + spec["direction"],
        "",
        "【已冻结事实】",
        json.dumps(facts, ensure_ascii=False, indent=2),
        "",
        "【硬约束】",
        "\n".join("- " + item for item in constraints),
        "",
        "【严格输出schema示例；数值和表达式只是形状示例，不得照抄】",
        json.dumps(schema, ensure_ascii=False, indent=2),
    ])


def prepare() -> None:
    if BATCH.exists():
        raise SystemExit("微函数第一批目录已存在；拒绝覆盖")
    if file_sha256(V2) != EXPECTED_V2_SHA256:
        raise ValueError("稳定V2摘要漂移")
    if file_sha256(ROUTE_PARENT) != EXPECTED_ROUTE_PARENT_SHA256:
        raise ValueError("路线研究父代摘要漂移")
    BATCH.mkdir(parents=True)
    rows = []
    for task_id, spec in TASKS.items():
        prompt = _prompt(task_id, spec)
        target = _project_file(_PROJECT_ROOT, BATCH / "prompts" / task_id)
        target.mkdir(parents=True)
        (target / "prompt.txt").write_text(prompt, encoding="utf-8")
        rows.append({
            "task_id": task_id,
            "name": spec["name"],
            "prompt_sha256": sha256_text(prompt),
            "prompt_chars": len(prompt),
        })
    _settings_files()
    write_json(_project_file(_PROJECT_ROOT, BATCH / "manifest.json"), {
        "schema": "r10-route-microfunction-author-batch/1",
        "created_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "target_model": {"provider": "zai-coding-cn", "model": "glm-5.3"},
        "expected_request_config": EXPECTED_CONFIG,
        "v2_sha256": EXPECTED_V2_SHA256,
        "research_parent_sha256": EXPECTED_ROUTE_PARENT_SHA256,
        "tasks": rows,
        "effect_evaluation_started": False,
        "confirmation_reserved": 0,
    })
    write_json(_project_file(_PROJECT_ROOT, BATCH / "authorization.json"), {
        "schema": "sitin-authorization/1",
        "authorization_id": "r10-route-microfunction-01-20260921",
        "trusted": True,
        "issued_by": "Codex root",
        "issued_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "issuance_basis": "用户授权API上限前由root安排zai-coding-cn GLM5.3调用，并要求按文献复盘后的新路线持续推进。",
        "route": "offline_microfunction_authoring",
        "max_initial_calls": 2,
        "max_repair_calls": 2,
        "max_total_calls": 4,
        "per_call_limits": {"tokens_input": 196608, "tokens_output": 8192},
        "effect_tables": 0,
        "confirmation_reserved": 0,
        "autonomous_admission": False,
        "scope": "只生成短表达式和参数网格；不得确认或发布",
    })
    (_project_file(_PROJECT_ROOT, BATCH / ".gitignore")).write_text("dispatch-ledger/\n", encoding="utf-8")
    print(json.dumps({"status": "PREPARED", "tasks": rows}, ensure_ascii=False, indent=2))


def _verified_tasks() -> list[str]:
    manifest = json.loads((_project_file(_PROJECT_ROOT, BATCH / "manifest.json")).read_text(encoding="utf-8"))
    tasks = []
    for row in manifest["tasks"]:
        task_id = row["task_id"]
        prompt = (_project_file(_PROJECT_ROOT, BATCH / "prompts" / task_id / "prompt.txt")).read_text(encoding="utf-8")
        if sha256_text(prompt) != row["prompt_sha256"]:
            raise ValueError("提示摘要漂移：" + task_id)
        tasks.append(task_id)
    return tasks


def _checked_usage(call_row: dict) -> tuple[dict, bool]:
    usage = criterion.usage_of(call_row.get("run_id"))
    values = usage.get("usage") or {}
    clean = (
        call_row.get("exit_code") == 0
        and call_row.get("protocol_ok") is True
        and call_row.get("request_config") == EXPECTED_CONFIG
        and usage.get("source_status") == "OK"
        and isinstance(values.get("inputTokens"), int)
        and isinstance(values.get("outputTokens"), int)
        and values["inputTokens"] <= 196608
        and values["outputTokens"] <= 8192
    )
    return usage, clean


def call() -> None:
    replies = _project_file(_PROJECT_ROOT, BATCH / "replies")
    if replies.exists():
        raise SystemExit("回复目录已存在；拒绝重复调用")
    dispatch._expected_request_config = lambda _package: dict(EXPECTED_CONFIG)
    report = dispatch.dispatch(
        BATCH, _verified_tasks(), replies, _project_file(_PROJECT_ROOT, BATCH / "plan-initial.json"),
        model_patch=str(_project_file(_PROJECT_ROOT, BATCH / "route.patch.yml")), timeout_s=900, concurrency=1,
        prompt_dir=_project_file(_PROJECT_ROOT, BATCH / "prompts"), kind="route-microfunction-initial-1",
    )
    rows = []
    for item in sorted(report["calls"], key=lambda row: row["task"]):
        usage, clean = _checked_usage(item)
        rows.append({
            "task": item["task"], "run_id": item.get("run_id"),
            "exit_code": item.get("exit_code"), "protocol_ok": item.get("protocol_ok"),
            "observed_config": item.get("request_config"), "usage": usage,
            "ingestable_channel": clean,
        })
    write_json(_project_file(_PROJECT_ROOT, BATCH / "initial-call-usage.json"), {
        "schema": "r10-route-microfunction-call-usage/1",
        "calls": rows,
        "total_input_tokens": sum((r["usage"].get("usage") or {}).get("inputTokens", 0) for r in rows),
        "total_output_tokens": sum((r["usage"].get("usage") or {}).get("outputTokens", 0) for r in rows),
        "problems": [r["task"] for r in rows if not r["ingestable_channel"]],
    })
    print(json.dumps({"status": "CALLED", "calls": rows}, ensure_ascii=False, indent=2))


def _json_reply(raw: str) -> dict:
    text = raw.strip()
    if text.startswith(FENCE):
        match = re.fullmatch(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL)
        if match is None:
            raise ValueError("围栏回复不是单一JSON对象")
        text = match.group(1)
    value = json.loads(text)
    if not isinstance(value, dict):
        raise ValueError("回复必须是JSON对象")
    return value


def _validate_expression(expression: object) -> str:
    if not isinstance(expression, str) or not expression.strip() or len(expression) > 1200:
        raise ValueError("expression必须是1—1200字符字符串")
    tree = ast.parse(expression, mode="eval")
    for node in ast.walk(tree):
        if not isinstance(node, ALLOWED_EXPR_NODES):
            raise ValueError("expression含禁止节点：" + type(node).__name__)
        if isinstance(node, ast.Name) and node.id not in ALLOWED_NAMES | ALLOWED_CALLS:
            raise ValueError("expression含禁止名字：" + node.id)
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name) or node.func.id not in ALLOWED_CALLS:
                raise ValueError("expression只允许min/max/abs调用")
            if node.keywords:
                raise ValueError("expression调用不允许关键字参数")
        if isinstance(node, ast.Constant):
            if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
                raise ValueError("expression常量只能是有限数值")
            number = float(node.value)
            if number - number != 0 or abs(number) > 1000000:
                raise ValueError("expression数值常量越界")
    return ast.unparse(tree.body)


def _config(value: object, where: str) -> dict:
    if not isinstance(value, dict) or set(value) != {"scale", "shape", "cap"}:
        raise ValueError(where + "必须恰含scale/shape/cap")
    result = {}
    for key in ("scale", "shape", "cap"):
        item = value[key]
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            raise ValueError(where + "." + key + "必须是数值")
        item = float(item)
        if item - item != 0:
            raise ValueError(where + "." + key + "必须有限")
        result[key] = item
    if not 0.0 <= result["scale"] <= 48.0:
        raise ValueError(where + ".scale越界")
    if not 0.0 < result["shape"] <= 128.0:
        raise ValueError(where + ".shape越界")
    if not 0.0 <= result["cap"] <= 48.0:
        raise ValueError(where + ".cap越界")
    return result


def _eval_expression(expression: str, values: dict) -> float:
    result = eval(  # noqa: S307 - expression经过上方封闭AST白名单验证
        compile(ast.Expression(ast.parse(expression, mode="eval").body), "<microfunction>", "eval"),
        {"__builtins__": {}, "min": min, "max": max, "abs": abs}, values,
    )
    if isinstance(result, bool) or not isinstance(result, (int, float)):
        raise ValueError("expression结果必须是数值")
    number = float(result)
    if number - number != 0 or abs(number) == float("inf"):
        raise ValueError("expression结果必须有限")
    return max(-1.0, min(1.0, number))


def _arithmetic_checks(expression: str) -> dict:
    base = {"direct_support": 10.0, "self_delta": 10.0, "fan": 1.0,
            "wall_remaining": 55.0, "shape": 24.0}
    cases = []
    def value(changes: dict) -> float:
        return _eval_expression(expression, base | changes)
    base_value = value({})
    tests = [
        ("self_delta_monotone", value({"self_delta": 24.0}) >= base_value),
        ("fan_monotone", value({"fan": 2.0}) >= base_value),
        ("direct_support_monotone", value({"direct_support": 15.0}) >= base_value),
        ("wall_nonincreasing", value({"wall_remaining": 70.0}) <= base_value),
    ]
    for name, passed in tests:
        cases.append({"name": name, "passed": passed})
    grid = []
    for support in (4.0, 9.0, 12.0, 19.0, 92.0):
        for delta in (10.0, 20.0, 24.0, 48.0):
            for fan in (1.0, 2.0):
                for wall in (24.0, 55.0, 78.0):
                    grid.append(_eval_expression(expression, {
                        "direct_support": support, "self_delta": delta, "fan": fan,
                        "wall_remaining": wall, "shape": 24.0,
                    }))
    return {
        "passed": all(row["passed"] for row in cases),
        "cases": cases,
        "grid_points": len(grid),
        "grid_min": min(grid), "grid_max": max(grid),
        "distinct_rounded_values": len(set(round(item, 9) for item in grid)),
    }


def validate_proposal(raw: str) -> tuple[dict, dict]:
    value = _json_reply(raw)
    expected = {"schema", "id", "hypothesis", "expression", "default", "configs",
                "bounds", "falsifier"}
    if set(value) != expected:
        raise ValueError("JSON键必须恰为：" + ",".join(sorted(expected)))
    if value["schema"] != "r10-route-microfunction-proposal/1":
        raise ValueError("schema不匹配")
    if not isinstance(value["id"], str) or re.fullmatch(r"[a-z][a-z0-9-]{2,40}", value["id"]) is None:
        raise ValueError("id格式非法")
    for key in ("hypothesis", "bounds", "falsifier"):
        if not isinstance(value[key], str) or not value[key].strip() or len(value[key]) > 1200:
            raise ValueError(key + "必须是1—1200字符字符串")
    expression = _validate_expression(value["expression"])
    default = _config(value["default"], "default")
    if not isinstance(value["configs"], list) or len(value["configs"]) != 6:
        raise ValueError("configs必须恰好6项")
    configs = [_config(item, "configs[{0}]".format(index))
               for index, item in enumerate(value["configs"])]
    identities = {tuple(row[key] for key in ("scale", "shape", "cap")) for row in configs}
    if len(identities) != 6:
        raise ValueError("configs必须互异")
    if tuple(default[key] for key in ("scale", "shape", "cap")) not in identities:
        raise ValueError("default必须等于configs之一")
    if sum(row["scale"] == 0.0 for row in configs) != 1:
        raise ValueError("configs必须含且只含一个scale=0")
    arithmetic = _arithmetic_checks(expression)
    if not arithmetic["passed"]:
        raise ValueError("表达式单调算术检查失败")
    normalized = dict(value)
    normalized["expression"] = expression
    normalized["default"] = default
    normalized["configs"] = configs
    return normalized, arithmetic


def _candidate_source(proposal: dict) -> str:
    v2 = V2.read_text(encoding="utf-8")
    expression = proposal["expression"]
    default = proposal["default"]
    space = {
        "parameters": {
            "RMF_SCALE": sorted({row["scale"] for row in proposal["configs"]}),
            "RMF_SHAPE": sorted({row["shape"] for row in proposal["configs"]}),
            "RMF_CAP": sorted({row["cap"] for row in proposal["configs"]}),
        },
        "zero_effect": {
            "RMF_SCALE": next(row["scale"] for row in proposal["configs"] if row["scale"] == 0.0),
            "RMF_SHAPE": next(row["shape"] for row in proposal["configs"] if row["scale"] == 0.0),
            "RMF_CAP": next(row["cap"] for row in proposal["configs"] if row["scale"] == 0.0),
        },
        "configs": [
            {"RMF_SCALE": row["scale"], "RMF_SHAPE": row["shape"], "RMF_CAP": row["cap"]}
            for row in proposal["configs"]
        ],
    }
    prefix = (
        "# STRUCTURE_SPACE_JSON: " + json.dumps(space, ensure_ascii=False, separators=(",", ":")) + "\n"
        + "\"\"\"候选机制：稳定V2骨架加条件路线价值微函数；模型只提供受限表达式。\"\"\"\n\n"
        + "RMF_SCALE = " + repr(default["scale"]) + "\n"
        + "RMF_SHAPE = " + repr(default["shape"]) + "\n"
        + "RMF_CAP = " + repr(default["cap"]) + "\n\n"
        + "def route_micro_value(direct_support, self_delta, fan, wall_remaining, shape):\n"
        + "    \"\"\"把已校验的公开条件路线事实压缩为[-1,1]无量纲代理。\"\"\"\n"
        + "    value = " + expression + "\n"
        + "    if value - value != 0:\n        return None\n"
        + "    if value > 1.0:\n        return 1.0\n"
        + "    if value < -1.0:\n        return -1.0\n"
        + "    return float(value)\n\n"
        + '''def finite_number(value):
    """把非布尔有限数转换为浮点；未知保持未知。"""
    if value is None or value is True or value is False:
        return None
    number = float(value)
    if number - number != 0:
        return None
    return number


def support_total(tiles):
    """汇总规则给出的未见枚数；它是计数代理，不解释为概率。"""
    if tiles is None:
        return None
    total = 0.0
    codes = set()
    for tile in tiles:
        code = tile.get("code")
        amount = finite_number(tile.get("remaining_estimate"))
        if (code is None or code is True or code is False or amount is None
                or amount < 0.0 or amount > 4.0 or code in codes):
            return None
        codes.add(code)
        total += amount
    return total


def route_adjustment(action, visible, seat):
    """校验条件路线并返回相对稳定V2的有界增量。"""
    if RMF_SCALE == 0.0:
        return (0.0, "zero_effect", 0)
    if action.get("value_coverage") != "complete":
        return (0.0, "coverage_not_complete", 0)
    issues = action.get("value_issues")
    if issues is None or len(issues) != 0:
        return (0.0, "value_issues", 0)
    wall = finite_number(visible.get("remaining_tile_count"))
    direct_support = support_total(action.get("useful_tiles"))
    if wall is None or wall <= 0.0 or direct_support is None or direct_support <= 0.0:
        return (0.0, "public_support_unavailable", 0)
    best = None
    valid_routes = 0
    routes = action.get("routes")
    if routes is None:
        return (0.0, "routes_unknown", 0)
    for route in routes:
        if route.get("shanten") != 0:
            continue
        route_support = support_total(route.get("useful_tiles"))
        if route_support is None or route_support <= 0.0:
            continue
        conditions = route.get("conditions")
        if conditions is None or conditions.get("draw_kind") not in ("normal", "replacement"):
            continue
        settlement = route.get("conditional_settlement")
        if settlement is None:
            continue
        self_delta = finite_number(settlement.get("self_delta"))
        fan = finite_number(settlement.get("fan"))
        deltas = settlement.get("score_delta")
        if (self_delta is None or self_delta <= 0.0 or fan is None or fan <= 0.0
                or deltas is None or len(deltas) != 4):
            continue
        seat_delta = finite_number(deltas[seat])
        if seat_delta is None or seat_delta != self_delta:
            continue
        raw = route_micro_value(direct_support, self_delta, fan, wall, RMF_SHAPE)
        if raw is None:
            continue
        delta = RMF_SCALE * raw
        if delta > RMF_CAP:
            delta = RMF_CAP
        if delta < -RMF_CAP:
            delta = -RMF_CAP
        valid_routes += 1
        if best is None or delta > best:
            best = delta
    if best is None:
        return (0.0, "no_valid_route", valid_routes)
    return (round(best, 6), "complete_route_max", valid_routes)


'''
    )
    old_header = "\"\"\"候选机制说明：默认 V2 基础排序、胡排序层与严格未知锚定的可审计种子。\"\"\"\n\n"
    if not v2.startswith(old_header):
        raise ValueError("V2头部锚点漂移")
    v2 = v2[len(old_header):]
    route_anchor = '''        if families is not None and len(families) > 0:
            produced = True
'''
    route_insert = route_anchor + '''        route_delta, route_delta_basis, route_valid_count = route_adjustment(
            action, visible, seat)
'''
    if v2.count(route_anchor) != 1:
        raise ValueError("V2 route锚点漂移")
    v2 = v2.replace(route_anchor, route_insert)
    v2 = v2.replace(
        'pending.append({"action": action, "base": base, "basis": "direct_v2", "shanten": shanten})',
        'pending.append({"action": action, "base": base, "basis": "direct_v2", "shanten": shanten, "route_delta": route_delta, "route_delta_basis": route_delta_basis, "route_valid_count": route_valid_count})',
    )
    v2 = v2.replace(
        'pending.append({"action": action, "base": 0.0, "basis": "produced_outside_v2", "shanten": None})',
        'pending.append({"action": action, "base": 0.0, "basis": "produced_outside_v2", "shanten": None, "route_delta": route_delta, "route_delta_basis": route_delta_basis, "route_valid_count": route_valid_count})',
    )
    v2 = v2.replace(
        'pending.append({"action": action, "base": None, "basis": "unknown", "shanten": None})',
        'pending.append({"action": action, "base": None, "basis": "unknown", "shanten": None, "route_delta": 0.0, "route_delta_basis": "unknown_action", "route_valid_count": 0})',
    )
    fixed_anchor = '''            total += fixed
            total = round(total, 6)
        trace = {'''
    fixed_replacement = '''            total += fixed
            total = round(total, 6)
        route_delta = item.get("route_delta")
        total = round(total + route_delta, 6)
        trace = {'''
    if v2.count(fixed_anchor) != 1:
        raise ValueError("V2 final score锚点漂移")
    v2 = v2.replace(fixed_anchor, fixed_replacement)
    trace_anchor = '"style_part": style_part, "unknown": unknown,'
    trace_replacement = (
        '"style_part": style_part, "route_delta": route_delta, '
        '"route_delta_basis": item.get("route_delta_basis"), '
        '"route_valid_count": item.get("route_valid_count"), '
        '"rmf_scale": RMF_SCALE, "rmf_shape": RMF_SHAPE, "rmf_cap": RMF_CAP, '
        '"unknown": unknown,'
    )
    if v2.count(trace_anchor) != 1:
        raise ValueError("V2 trace锚点漂移")
    v2 = v2.replace(trace_anchor, trace_replacement)
    return prefix + v2


def ingest() -> None:
    usage = json.loads((_project_file(_PROJECT_ROOT, BATCH / "initial-call-usage.json")).read_text(encoding="utf-8"))
    by_task = {row["task"]: row for row in usage["calls"]}
    rows = []
    for task_id in _verified_tasks():
        raw = (_project_file(_PROJECT_ROOT, BATCH / "replies" / (task_id + ".txt"))).read_text(encoding="utf-8")
        target = _project_file(_PROJECT_ROOT, BATCH / "generations" / task_id)
        target.mkdir(parents=True, exist_ok=True)
        (target / "reply_raw.txt").write_text(raw, encoding="utf-8")
        problems = []
        proposal = None
        arithmetic = None
        source = None
        try:
            proposal, arithmetic = validate_proposal(raw)
            source = _candidate_source(proposal)
            static_check(source)
        except Exception as exc:  # 生成端合同错误；记录后进入一次修复资格
            problems.append(type(exc).__name__ + ": " + str(exc))
        if proposal is not None:
            write_json(target / "proposal.json", proposal)
        if arithmetic is not None:
            write_json(target / "arithmetic.json", arithmetic)
        if source is not None:
            (target / "candidate.py").write_text(source.rstrip("\n") + "\n", encoding="utf-8")
        accepted = by_task.get(task_id, {}).get("ingestable_channel") is True and not problems
        row = {
            "task": task_id,
            "channel_ok": by_task.get(task_id, {}).get("ingestable_channel") is True,
            "proposal_ok": proposal is not None,
            "arithmetic_ok": arithmetic is not None and arithmetic.get("passed") is True,
            "candidate_static_ok": source is not None and not problems,
            "accepted_for_behavior_preflight": accepted,
            "proposal_sha256": sha256_text(json.dumps(proposal, ensure_ascii=False, sort_keys=True)) if proposal else None,
            "candidate_sha256": sha256_text(source) if source else None,
            "problems": problems,
        }
        write_json(target / "record.json", row)
        rows.append(row)
    write_json(_project_file(_PROJECT_ROOT, BATCH / "ingest-summary.json"), {
        "schema": "r10-route-microfunction-ingest/1",
        "tasks": rows,
        "accepted": [row["task"] for row in rows if row["accepted_for_behavior_preflight"]],
        "repair_eligible": [row["task"] for row in rows if not row["accepted_for_behavior_preflight"]],
        "effect_evaluation_started": False,
        "note": "只允许修复JSON/表达式/参数合同错误；效果不佳不修复。",
    })
    print(json.dumps({"status": "INGESTED", "tasks": rows}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("prepare", "call", "ingest"))
    args = parser.parse_args()
    {"prepare": prepare, "call": call, "ingest": ingest}[args.operation]()
