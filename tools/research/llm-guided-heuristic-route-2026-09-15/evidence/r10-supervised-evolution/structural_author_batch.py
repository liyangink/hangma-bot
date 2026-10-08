"""R10 第一结构批次：冻结四张作者卡、经禁工具 GLM 通道派发并静态摄入。

本工具只完成作者交付与生成端预检，不运行效果模拟、不确认、不发布。四份任务的结构
方向来自 2026-09-21 文献复盘；模型提出结构和至多四个离散参数，后续程序负责六配置
装配与共同实例竞赛。
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
import math
import re
import shutil
import sys
from pathlib import Path


HERE = Path(__file__).resolve().parent
ROUTE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15')
REPO = _PROJECT_ROOT
BATCH = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/structural-search-01-20260921')
TOOLS = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/tools')
ADMISSION = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/v4-impl/r9-admission')
HEADLESS = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/v4-impl/r9-admission/p25-headless')
DEV_CARDS = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/v4-impl/r9-admission/p25-dev-cards')
for path in (TOOLS, HEADLESS, DEV_CARDS):
    sys.path.insert(0, str(path))

import criterion  # noqa: E402
import dispatch_headless as dispatch  # noqa: E402
import sitin_generate as gen  # noqa: E402


V2 = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/v2-parent-revalidation-20260920/parent/generation')
COHESION = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/comparable-shape-20260920/comparable-shape-terra-max/run/iterations/iter-01/generation')
PATTERN = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/pattern-option-20260920/pattern-option-terra-max/run/iterations/iter-01/generation')

EXPECTED_PARENT_HASHES = {
    "v2": "a0c389b3a4757a38febf5ca6bf16e9c4779159df0c15b82d2e804e1f4ac9638f",
    "cohesion": "3a4850b2433f7c18457c7a08d1f0328a5475fa986c1d67b50131ed0085f5cc06",
    "pattern": "756233cb62cc7759b9a6facea209420e36de0b1e2bb90a16203c9e9351795f31",
}

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

COMMON_REQUIREMENTS = """【本批结构搜索的额外机器约束】
- 这是结构提案，不是只换常数：只能提出一个可消融的新结构；不得改变杭麻规则、合法动作、向听/胡牌计算、评测器或目标 U。
- 杭麻边界：只允许自摸和规则已生产的立即/条件结算；不得引入点炮、抢杠胡或其他麻将番型；财神、七对与副露资格继续由输入事实裁定。
- 信息边界：只能读取 candidate_view 已投影事实；不得读取 WorldState、隐藏牌墙、对手暗牌、实验根、H/M 标签或终局结果；support/remaining_estimate 只是未见枚数估计，不是概率。
- 数值边界：不得把未知/None/布尔当 0 或数值；新增项有界、有限、可审计，并保留父代的全部合法动作、胡排序层、未知锚定和 ABSTAIN 语义。
- 结构与参数分工：源码开头必须有且仅有一行注释 `# STRUCTURE_SPACE_JSON: <严格JSON>`。JSON 恰含 parameters、zero_effect、configs 三键。parameters 含 1—4 个模块级数值常数及各自离散取值；zero_effect 给出关闭新增结构的完整参数映射；configs 恰好给出六个完整且互异的参数映射，并包含 zero_effect。源码中这些常数的默认值必须等于六配置之一。后续由程序改常数，模型不得用评测结果挑选配置。
- 说明义务：四字段说明必须给出触发条件、避免重复计数的方法、至少一个可手算例、一个会失败或应精确退化的反例、零效应消融方式。新增 trace 必须能看到触发、参数和实际加减分。
- 只交付一个完整 score_actions(view) 源码；不得 import，不得访问工具/文件/网络/时间/随机源，不得宣称已经提分、通过或可发布。
"""


TASKS = {
    "S1": {
        "name": "single-parent-stability",
        "parent": "cohesion",
        "objective": "改良统一残余凝聚度结构，使其跨 H/M 对手族更稳定；不得只改原权重。",
        "change": (
            "保留统一残余凝聚度作为可消融研究材料，但针对它在第二开发清单 H +0.125、"
            "M -0.03125 的分层差异，改变触发、归一化或与直接牌效/风险的交互结构。"
            "历史点值只用于指出不稳定性，不是动作标签。"
        ),
        "facts": (
            "父代 sha=3a4850b2…；新清单等权 +0.046875，但 H/M 方向不一致且未晋升。"
            "父代残余项范围约 [-2,+2]，只在可信普通型、直接弃牌、最佳向听边界触发。"
        ),
        "hypothesis": (
            "寻找比候选牌类型一致性更强的结构判据，并让弱证据精确退化；不得依据 H/M 标签分支。"
        ),
        "groups": [
            "actions", "actions[]", "actions[].useful_tiles",
            "actions[].standard_useful_tiles", "visible_state",
            "visible_state.rule_state", "analysis_profile",
        ],
    },
    "S2": {
        "name": "dual-parent-recombination",
        "parent": "cohesion",
        "companion": "pattern",
        "objective": "非叠加式重组残余凝聚度与普通型/七对选项结构，相同事实只计一次。",
        "change": (
            "比较两个父代的触发、未知退化和尺度，设计一个共同的选择余地结构；禁止简单把"
            "residual_part 与 pattern_bonus 相加。普通型/七对父代在全新开发 H=0、M=+0.0078125，"
            "只表明它近零且分层稳定，不表明动作正确。"
        ),
        "facts": (
            "凝聚度父代 H/M 分化；选项父代在新清单近零。两个结构都只作用于直接已知弃牌，"
            "并读取普通型有效牌事实，存在重复计数风险。"
        ),
        "hypothesis": (
            "用互斥触发、单一归一化分数或门控选择其中一种证据，避免两份代理值机械累加。"
        ),
        "groups": [
            "actions", "actions[]", "actions[].useful_tiles",
            "actions[].standard_useful_tiles", "actions[].seven_pairs_useful_tiles",
            "visible_state", "visible_state.rule_state", "analysis_profile",
        ],
    },
    "S3": {
        "name": "bounded-followup-value",
        "parent": "v2",
        "objective": "探索一个基于已生产路线/后续分支/阶段处境的有界后续价值近似。",
        "change": (
            "从 V2 研究骨架出发，只使用 routes、followup_branches 或可映射 current_stage_scores。"
            "选择一个主结构，不能同时堆叠三套奖励；条件结算是见证值而非期望值，"
            "support 不是胡率，剩余赛程尚未投影。"
        ),
        "facts": (
            "上一轮六维静态权重在 256 个全新 H/M 根上保守差 -0.001953125，说明局部常数邻域"
            "不足；麻将价值建模文献支持有限后续价值，但杭麻事实与信息权限必须保持。"
        ),
        "hypothesis": (
            "把已有分支/路线压缩为有上界且能逐项退化的相对选择信息，可能产生比常数微调更大的行为差异。"
        ),
        "groups": [
            "actions", "actions[]", "actions[].useful_tiles",
            "actions[].followup_branches", "actions[].routes",
            "actions[].routes[].useful_tiles", "actions[].routes[].conditions",
            "actions[].routes[].conditional_settlement", "actions[].immediate_settlement",
            "actions[].family_progress_entries", "competition", "visible_state",
            "visible_state.rule_state", "analysis_profile",
        ],
        "overview": "contract",
    },
    "S4": {
        "name": "v2-simplification",
        "parent": "v2",
        "objective": "压缩 V2 中缺乏新来源支持的风格/安全代理和重复局部项，形成更少参数的结构。",
        "change": (
            "审查 style_adjust、牌河熟悉度和副露邻近旧代理的相互作用，至少删除或合并一类项；"
            "style_adjust=0 在 256 个全新 H/M 根上保守差 -0.001953125，只能作为删减证据，"
            "不得当作动作标签。保持向听、支持、财神和胡排序骨架。"
        ),
        "facts": (
            "24→8→3 联合参数冠军只关闭 style_adjust，开发信号在新来源归零；继续微调六个常数已结案。"
        ),
        "hypothesis": (
            "减少互相竞争的弱代理并改为一个有清楚触发/退化的结构，可能降低跨来源方差。"
        ),
        "groups": [
            "actions", "actions[]", "actions[].useful_tiles", "visible_state",
            "visible_state.rule_state", "competition", "analysis_profile",
        ],
        "overview": "contract",
    },
}


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def parent_record(name: str) -> dict:
    directory = {"v2": V2, "cohesion": COHESION, "pattern": PATTERN}[name]
    code = (directory / "candidate.py").read_text(encoding="utf-8")
    digest = sha256_text(code)
    if digest != EXPECTED_PARENT_HASHES[name]:
        raise RuntimeError(f"父代 {name} 摘要漂移：{digest}")
    parsed_path = directory / "parsed.json"
    parsed = json.loads(parsed_path.read_text(encoding="utf-8")) if parsed_path.exists() else {}
    return {
        "name": name,
        "path": str(directory / "candidate.py"),
        "identity": digest,
        "candidate_id": digest,
        "thought": parsed.get("thought") or code.splitlines()[0].strip('"'),
        "code": code,
        "code_sha256": digest,
    }


def prompt_for(task_id: str, spec: dict, parents: dict) -> tuple[str, dict]:
    parent = parents[spec["parent"]]
    payload = gen.render_action_value_task_contract(
        objective_summary=(
            "在共同新开发来源上提高完整阶段进入前二的效用 U；本调用只产生结构和参数空间，"
            "不接触效果结果。"
        ),
        panel_boundary=(
            "后续程序先做静态/算术/真实行为预检，再在冻结 H/M 共同实例上按 30→10→3、"
            "累计 16→32→64 根竞赛；本卡不得选择实例或判定胜负。"
        ),
        prompt_role=f"{task_id} {spec['name']}：{spec['objective']}",
        parent=parent,
        feedback={
            "facts": spec["facts"],
            "associated_results": spec["change"],
            "mechanism_hypothesis": spec["hypothesis"],
        },
        budget_note="首答计一次模型调用；只允许一次后续语法/合同修复；失败同样计费。",
    )
    focus = {
        "objective": spec["objective"],
        "change_point": spec["change"],
        "input_groups": spec["groups"],
        "gate": "none",
        "guard": "full",
        "guard_reference": False,
        "examples": "output",
        "rules": "compact",
        "input_overview": spec.get("overview", "none"),
        "budget_note": "首答计费；生成端不依据模型自报结果选留。",
    }
    packet = gen.build_action_value_card_prompt("m1", payload, focus)
    extra = [COMMON_REQUIREMENTS]
    companion_name = spec.get("companion")
    if companion_name:
        companion = parents[companion_name]
        extra.extend([
            "【第二父代完整身份】",
            f"- name={companion_name}; sha256={companion['code_sha256']}",
            "- 第二父代只作结构重组材料，不继承历史选留分。",
            "【第二父代机制说明（逐字）】",
            companion["thought"],
            "【第二父代代码（逐字）】",
            gen.FENCE + "python",
            companion["code"].rstrip("\n"),
            gen.FENCE,
        ])
    output_block = gen._av_output_format()
    if packet.text.count(output_block) != 1:
        raise RuntimeError("无法定位唯一输出格式段")
    prompt = packet.text.replace(output_block, "\n\n".join(extra) + "\n\n" + output_block)
    record = {
        "task_id": task_id,
        "name": spec["name"],
        "primary_parent": parent["code_sha256"],
        "companion_parent": parents[companion_name]["code_sha256"] if companion_name else None,
        "contract_identity": packet.contract_identity,
        "focus": gen.normalize_card_focus(focus),
        "prompt_sha256": sha256_text(prompt),
        "prompt_chars": len(prompt),
    }
    return prompt, record


def prepare() -> None:
    if BATCH.exists():
        raise SystemExit("批次目录已存在；冻结后不得覆盖")
    parents = {name: parent_record(name) for name in EXPECTED_PARENT_HASHES}
    prompts = _project_file(_PROJECT_ROOT, BATCH / "prompts")
    task_rows = []
    for task_id, spec in TASKS.items():
        prompt, row = prompt_for(task_id, spec, parents)
        target = prompts / task_id
        target.mkdir(parents=True, exist_ok=True)
        (target / "prompt.txt").write_text(prompt, encoding="utf-8")
        task_rows.append(row)
    settings = """# R10 第一结构作者批次；输出上界显式冻结。
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
        "schema": "r10-structural-author-batch/1",
        "target_model": {"provider": "zai-coding-cn", "model": "glm-5.3"},
        "expected_request_config": EXPECTED_CONFIG,
        "tasks": task_rows,
        "parent_registry": {
            key: {field: value for field, value in row.items() if field != "code"}
            for key, row in parents.items()
        },
        "effect_evaluation_started": False,
        "confirmation_reserved": 0,
    })
    write_json(_project_file(_PROJECT_ROOT, BATCH / "authorization.json"), {
        "schema": "sitin-authorization/1",
        "authorization_id": "r10-structural-search-01-20260921",
        "trusted": True,
        "issued_by": "Codex root",
        "issued_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "issuance_basis": (
            "用户授权在 API 上限前由 root 安排 zai-coding-cn GLM5.3 调用，并要求按文献复盘后的"
            "新目标继续推进；本批只含四次首答与每题至多一次合同修复。"
        ),
        "route": "offline_structural_authoring",
        "max_initial_calls": 4,
        "max_repair_calls": 4,
        "max_total_calls": 8,
        "per_call_limits": {"tokens_input": 196608, "tokens_output": 32768},
        "allowed_accounts": {"tokens_input": 1572864, "tokens_output": 262144},
        "effect_tables": 0,
        "confirmation_reserved": 0,
        "autonomous_admission": False,
        "scope": "离线结构提案；生成预检后另行冻结效果预算；不得确认或发布",
    })
    (_project_file(_PROJECT_ROOT, BATCH / ".gitignore")).write_text("dispatch-ledger/\n", encoding="utf-8")
    print(json.dumps({"status": "PREPARED", "batch": str(BATCH), "tasks": task_rows},
                     ensure_ascii=False, indent=2))


def verify_frozen_prompts() -> list[str]:
    manifest = json.loads((_project_file(_PROJECT_ROOT, BATCH / "manifest.json")).read_text(encoding="utf-8"))
    task_ids = []
    for row in manifest["tasks"]:
        task_id = row["task_id"]
        prompt = (_project_file(_PROJECT_ROOT, BATCH / "prompts" / task_id / "prompt.txt")).read_text(encoding="utf-8")
        if sha256_text(prompt) != row["prompt_sha256"]:
            raise RuntimeError(f"提示词摘要漂移：{task_id}")
        task_ids.append(task_id)
    return task_ids


def call_initial() -> None:
    task_ids = verify_frozen_prompts()
    if (_project_file(_PROJECT_ROOT, BATCH / "replies")).exists():
        raise SystemExit("首答目录已存在；不得重复调用")
    dispatch._expected_request_config = lambda _package: dict(EXPECTED_CONFIG)
    report = dispatch.dispatch(
        BATCH,
        task_ids,
        _project_file(_PROJECT_ROOT, BATCH / "replies"),
        _project_file(_PROJECT_ROOT, BATCH / "plan-initial.json"),
        model_patch=str(_project_file(_PROJECT_ROOT, BATCH / "route.patch.yml")),
        timeout_s=900,
        concurrency=2,
        prompt_dir=_project_file(_PROJECT_ROOT, BATCH / "prompts"),
        kind="structural-initial",
    )
    usage_rows = []
    problems = []
    for row in sorted(report["calls"], key=lambda item: item["task"]):
        usage = criterion.usage_of(row.get("run_id"))
        observed = row.get("request_config")
        clean = (
            row.get("exit_code") == 0
            and row.get("protocol_ok") is True
            and observed == EXPECTED_CONFIG
            and usage.get("source_status") == "OK"
        )
        values = usage.get("usage") or {}
        if not isinstance(values.get("inputTokens"), int) or not isinstance(values.get("outputTokens"), int):
            clean = False
        if values.get("inputTokens", 10**18) > 196608 or values.get("outputTokens", 10**18) > 32768:
            clean = False
        usage_rows.append({
            "task": row["task"],
            "run_id": row.get("run_id"),
            "observed_config": observed,
            "protocol_ok": row.get("protocol_ok"),
            "exit_code": row.get("exit_code"),
            "usage": usage,
            "ingestable_channel": clean,
        })
        if not clean:
            problems.append(row["task"])
    write_json(_project_file(_PROJECT_ROOT, BATCH / "initial-call-usage.json"), {
        "schema": "r10-structural-call-usage/1",
        "calls": usage_rows,
        "total_input_tokens": sum((row["usage"].get("usage") or {}).get("inputTokens", 0)
                                  for row in usage_rows),
        "total_output_tokens": sum((row["usage"].get("usage") or {}).get("outputTokens", 0)
                                   for row in usage_rows),
        "problems": problems,
    })
    if problems:
        raise SystemExit("通道或用量核验失败：" + ",".join(problems))
    print(json.dumps({"status": "INITIAL_CALLS_COMPLETE", "tasks": task_ids,
                      "usage_path": str(_project_file(_PROJECT_ROOT, BATCH / "initial-call-usage.json"))}, ensure_ascii=False))


SPACE_RE = re.compile(r"^# STRUCTURE_SPACE_JSON: (\{.*\})\s*$", re.MULTILINE)


def numeric(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))


def module_numeric_constants(code: str) -> dict[str, float]:
    tree = ast.parse(code)
    found = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        value = node.value
        if isinstance(target, ast.Name) and isinstance(value, ast.Constant) and numeric(value.value):
            found[target.id] = value.value
    return found


def validate_space(code: str) -> dict:
    matches = SPACE_RE.findall(code)
    if len(matches) != 1:
        return {"ok": False, "problems": ["STRUCTURE_SPACE_JSON 注释必须恰好一行"]}
    try:
        space = json.loads(matches[0])
    except json.JSONDecodeError as exc:
        return {"ok": False, "problems": [f"STRUCTURE_SPACE_JSON 不可解析：{exc}"]}
    problems = []
    if set(space) != {"parameters", "zero_effect", "configs"}:
        problems.append("参数空间必须恰含 parameters/zero_effect/configs")
    parameters = space.get("parameters")
    zero = space.get("zero_effect")
    configs = space.get("configs")
    if not isinstance(parameters, dict) or not 1 <= len(parameters) <= 4:
        problems.append("parameters 数量必须为 1—4")
        parameters = {}
    names = set(parameters)
    for name, domain in parameters.items():
        if not re.fullmatch(r"[A-Z][A-Z0-9_]*", str(name)):
            problems.append(f"参数不是大写常数名：{name}")
        if not isinstance(domain, list) or len(domain) < 2 or not all(numeric(value) for value in domain):
            problems.append(f"参数域必须含至少两个有限数：{name}")
        elif len({float(value) for value in domain}) != len(domain):
            problems.append(f"参数域含重复值：{name}")
    if not isinstance(zero, dict) or set(zero) != names:
        problems.append("zero_effect 必须覆盖全部参数且不得多键")
        zero = {}
    if not isinstance(configs, list) or len(configs) != 6:
        problems.append("configs 必须恰好六个")
        configs = []
    normalized_configs = []
    for index, config in enumerate(configs):
        if not isinstance(config, dict) or set(config) != names:
            problems.append(f"config[{index}] 未完整覆盖参数")
            continue
        if not all(numeric(value) for value in config.values()):
            problems.append(f"config[{index}] 含非有限数或布尔")
            continue
        for name, value in config.items():
            domain = parameters.get(name)
            if (isinstance(domain, list) and all(numeric(item) for item in domain)
                    and float(value) not in {float(item) for item in domain}):
                problems.append(f"config[{index}].{name} 不在离散域")
        normalized_configs.append(tuple(sorted((name, float(value)) for name, value in config.items())))
    if len(set(normalized_configs)) != len(normalized_configs):
        problems.append("六配置不互异")
    if zero and tuple(sorted((name, float(value)) for name, value in zero.items())) not in normalized_configs:
        problems.append("六配置未包含 zero_effect")
    constants = module_numeric_constants(code)
    if not names.issubset(constants):
        problems.append("参数未全部定义为模块级数值常数")
    elif normalized_configs:
        default = tuple(sorted((name, float(constants[name])) for name in names))
        if default not in normalized_configs:
            problems.append("源码默认常数不属于六配置")
    return {"ok": not problems, "problems": problems, "space": space,
            "module_constants": constants}


def ingest() -> None:
    task_ids = verify_frozen_prompts()
    usage_doc = json.loads((_project_file(_PROJECT_ROOT, BATCH / "initial-call-usage.json")).read_text(encoding="utf-8"))
    usage_by_task = {row["task"]: row for row in usage_doc["calls"]}
    summary = []
    for task_id in task_ids:
        raw = (_project_file(_PROJECT_ROOT, BATCH / "replies" / f"{task_id}.txt")).read_text(encoding="utf-8")
        parsed = gen.parse_action_value_reply(raw)
        code = parsed.get("code") or ""
        precheck = gen.precheck_action_value_candidate(code) if code else {
            "ok": False, "problems": ["没有可预检源码"]
        }
        try:
            space = validate_space(code) if code else {
                "ok": False, "problems": ["没有可解析参数空间"]
            }
        except (SyntaxError, ValueError) as exc:
            space = {"ok": False, "problems": [f"参数空间预检异常：{type(exc).__name__}: {exc}"]}
        generation = _project_file(_PROJECT_ROOT, BATCH / "generations" / task_id)
        generation.mkdir(parents=True, exist_ok=True)
        (generation / "reply_raw.txt").write_text(raw, encoding="utf-8")
        if code:
            (generation / "candidate.py").write_text(code.rstrip("\n") + "\n", encoding="utf-8")
        write_json(generation / "parsed.json", {
            key: value for key, value in parsed.items() if key != "code"
        } | ({"code_sha256": sha256_text(code)} if code else {}))
        write_json(generation / "precheck.json", precheck)
        write_json(generation / "structure-space.json", space)
        accepted = (
            usage_by_task.get(task_id, {}).get("ingestable_channel") is True
            and parsed.get("status") == "ok"
            and precheck.get("ok") is True
            and space.get("ok") is True
        )
        row = {
            "task": task_id,
            "parse_status": parsed.get("status"),
            "static_precheck": precheck.get("ok"),
            "structure_space": space.get("ok"),
            "accepted_for_behavior_preflight": accepted,
            "code_sha256": sha256_text(code) if code else None,
            "problems": list(parsed.get("problems") or [])
                        + list(precheck.get("problems") or [])
                        + list(space.get("problems") or []),
        }
        write_json(generation / "record.json", row)
        summary.append(row)
    write_json(_project_file(_PROJECT_ROOT, BATCH / "ingest-summary.json"), {
        "schema": "r10-structural-ingest/1",
        "tasks": summary,
        "accepted": [row["task"] for row in summary if row["accepted_for_behavior_preflight"]],
        "repair_eligible": [row["task"] for row in summary
                            if not row["accepted_for_behavior_preflight"]],
        "effect_evaluation_started": False,
        "note": "首答失败只进入一次合同/语法修复资格；尚未运行行为或效果评测。",
    })
    print(json.dumps(json.loads((_project_file(_PROJECT_ROOT, BATCH / "ingest-summary.json")).read_text(encoding="utf-8")),
                     ensure_ascii=False, indent=2))


def repair_prompt(task_id: str, spec: dict, parents: dict) -> str:
    """为输出截断任务生成短修复卡；仍逐字携带父代，避免让模型凭记忆补源码。"""
    primary = parents[spec["parent"]]
    raw = (_project_file(_PROJECT_ROOT, BATCH / "replies" / f"{task_id}.txt")).read_text(encoding="utf-8")
    parsed = gen.parse_action_value_reply(raw)
    mechanism = parsed.get("mechanism")
    if mechanism:
        design = json.dumps(mechanism, ensure_ascii=False, indent=1)
    else:
        first_line = raw.splitlines()[0] if raw.splitlines() else ""
        design = first_line + "\n" + spec["change"] + "\n" + spec["hypothesis"]
    parts = [
        "这是唯一一次合同修复。上一次请求已经完整终止并结算，但因输出 token 用满而截断；"
        "不要分析失败历史，只把既定结构交付成短而完整的源码。",
        "",
        "【既定任务】",
        spec["objective"],
        spec["change"],
        "",
        "【上次已经形成的结构设计；只压缩表述，不改成第二种机制】",
        design,
        "",
        "【修复要求】",
        "- 以父代作最小源码修改；不要重写无关分支。完整代码优先于解释。",
        "- 回复严格为：花括号内一句话；一个 json 围栏，恰含 trigger/changed_branches/"
        "expected_direction/counterexample 四个非空短字符串且每个不超过 220 个汉字；一个完整 python 围栏。",
        "- Python 必须完整闭合，建议不超过 420 行。禁止 import。模块级只允许首个 docstring、"
        "1—4 个数值常数和 score_actions 函数；不要定义辅助函数或第二个裸字符串表达式。",
        "- 源码第一行必须是唯一的 `# STRUCTURE_SPACE_JSON: <严格JSON>`；JSON 恰含 parameters/"
        "zero_effect/configs，六配置完整互异并含零效应，默认常数属于六配置。",
        "- 保留父代 Hu 层、全部合法动作、未知低于全部已知、ABSTAIN、有限数和只读约束；"
        "None/布尔不得当数。新增项必须有界并写 trace。",
        "- 不复述合同、父代或长手算过程；不要宣称提分、通过或发布。",
        "",
        "【主父代完整源码】",
        gen.FENCE + "python",
        primary["code"].rstrip("\n"),
        gen.FENCE,
    ]
    companion_name = spec.get("companion")
    if companion_name:
        companion = parents[companion_name]
        parts.extend([
            "",
            "【第二父代完整源码；只提取结构，不与主父代逐项相加】",
            gen.FENCE + "python",
            companion["code"].rstrip("\n"),
            gen.FENCE,
        ])
    parts.extend([
        "",
        "现在直接输出短四字段和完整源码。不要先写推理过程。",
    ])
    return "\n".join(parts)


def prepare_repair() -> None:
    summary = json.loads((_project_file(_PROJECT_ROOT, BATCH / "ingest-summary.json")).read_text(encoding="utf-8"))
    failed = summary["repair_eligible"]
    if not failed:
        raise SystemExit("没有需要修复的任务")
    target_root = _project_file(_PROJECT_ROOT, BATCH / "repair-prompts")
    if target_root.exists():
        raise SystemExit("修复提示词已冻结；不得覆盖")
    parents = {name: parent_record(name) for name in EXPECTED_PARENT_HASHES}
    rows = []
    for task_id in failed:
        prompt = repair_prompt(task_id, TASKS[task_id], parents)
        target = target_root / task_id
        target.mkdir(parents=True, exist_ok=True)
        (target / "prompt.txt").write_text(prompt, encoding="utf-8")
        rows.append({"task": task_id, "prompt_sha256": sha256_text(prompt),
                     "prompt_chars": len(prompt), "source_initial_reply":
                     sha256_text((_project_file(_PROJECT_ROOT, BATCH / "replies" / f"{task_id}.txt")).read_text(encoding="utf-8"))})
    settings = """# 输出截断的唯一修复轮；降低推理强度，优先完整交付源码。
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
    (_project_file(_PROJECT_ROOT, BATCH / "settings-repair.yaml")).write_text(settings, encoding="utf-8")
    (_project_file(_PROJECT_ROOT, BATCH / "route.repair.patch.yml")).write_text(
        "- id: settings\n  config:\n    path: " + str(_project_file(_PROJECT_ROOT, BATCH / "settings-repair.yaml"))
        + "\n    watch: false\n- id: agent-default-model\n  config:\n"
        + "    provider: zai-coding-cn\n    model: glm-5.3\n",
        encoding="utf-8",
    )
    write_json(_project_file(_PROJECT_ROOT, BATCH / "repair-manifest.json"), {
        "schema": "r10-structural-repair/1",
        "reason": "首答输出达到 32768 token 上限，S1/S3 源码截断，S2 结构化说明截断",
        "expected_request_config": REPAIR_CONFIG,
        "tasks": rows,
        "max_repairs_per_task": 1,
    })
    print(json.dumps({"status": "REPAIR_PREPARED", "tasks": rows}, ensure_ascii=False, indent=2))


def verify_repair_prompts() -> list[str]:
    manifest = json.loads((_project_file(_PROJECT_ROOT, BATCH / "repair-manifest.json")).read_text(encoding="utf-8"))
    result = []
    for row in manifest["tasks"]:
        task_id = row["task"]
        text = (_project_file(_PROJECT_ROOT, BATCH / "repair-prompts" / task_id / "prompt.txt")).read_text(encoding="utf-8")
        if sha256_text(text) != row["prompt_sha256"]:
            raise RuntimeError(f"修复提示词摘要漂移：{task_id}")
        result.append(task_id)
    return result


def call_repair() -> None:
    task_ids = verify_repair_prompts()
    if (_project_file(_PROJECT_ROOT, BATCH / "repair-replies")).exists():
        raise SystemExit("修复回复目录已存在；每题不得第二次修复")
    dispatch._expected_request_config = lambda _package: dict(REPAIR_CONFIG)
    report = dispatch.dispatch(
        BATCH,
        task_ids,
        _project_file(_PROJECT_ROOT, BATCH / "repair-replies"),
        _project_file(_PROJECT_ROOT, BATCH / "plan-repair.json"),
        model_patch=str(_project_file(_PROJECT_ROOT, BATCH / "route.repair.patch.yml")),
        timeout_s=900,
        concurrency=2,
        prompt_dir=_project_file(_PROJECT_ROOT, BATCH / "repair-prompts"),
        kind="structural-repair",
    )
    rows = []
    problems = []
    for row in sorted(report["calls"], key=lambda item: item["task"]):
        usage = criterion.usage_of(row.get("run_id"))
        values = usage.get("usage") or {}
        clean = (
            row.get("exit_code") == 0
            and row.get("protocol_ok") is True
            and row.get("request_config") == REPAIR_CONFIG
            and usage.get("source_status") == "OK"
            and isinstance(values.get("inputTokens"), int)
            and isinstance(values.get("outputTokens"), int)
            and values["inputTokens"] <= 196608
            and values["outputTokens"] <= 32768
        )
        rows.append({"task": row["task"], "run_id": row.get("run_id"),
                     "observed_config": row.get("request_config"),
                     "protocol_ok": row.get("protocol_ok"), "exit_code": row.get("exit_code"),
                     "usage": usage, "ingestable_channel": clean})
        if not clean:
            problems.append(row["task"])
    write_json(_project_file(_PROJECT_ROOT, BATCH / "repair-call-usage.json"), {
        "schema": "r10-structural-call-usage/1", "calls": rows, "problems": problems,
        "total_input_tokens": sum((row["usage"].get("usage") or {}).get("inputTokens", 0)
                                  for row in rows),
        "total_output_tokens": sum((row["usage"].get("usage") or {}).get("outputTokens", 0)
                                   for row in rows),
    })
    if problems:
        raise SystemExit("修复通道或用量核验失败：" + ",".join(problems))
    print(json.dumps({"status": "REPAIR_CALLS_COMPLETE", "tasks": task_ids}, ensure_ascii=False))


def ingest_repair() -> None:
    task_ids = verify_repair_prompts()
    usage_doc = json.loads((_project_file(_PROJECT_ROOT, BATCH / "repair-call-usage.json")).read_text(encoding="utf-8"))
    usage_by_task = {row["task"]: row for row in usage_doc["calls"]}
    rows = []
    for task_id in task_ids:
        raw = (_project_file(_PROJECT_ROOT, BATCH / "repair-replies" / f"{task_id}.txt")).read_text(encoding="utf-8")
        parsed = gen.parse_action_value_reply(raw)
        code = parsed.get("code") or ""
        precheck = gen.precheck_action_value_candidate(code) if code else {
            "ok": False, "problems": ["没有可预检源码"]}
        try:
            space = validate_space(code) if code else {
                "ok": False, "problems": ["没有可解析参数空间"]}
        except (SyntaxError, ValueError) as exc:
            space = {"ok": False, "problems": [f"参数空间预检异常：{type(exc).__name__}: {exc}"]}
        target = _project_file(_PROJECT_ROOT, BATCH / "generations" / task_id / "repair")
        target.mkdir(parents=True, exist_ok=True)
        (target / "reply_raw.txt").write_text(raw, encoding="utf-8")
        if code:
            (target / "candidate.py").write_text(code.rstrip("\n") + "\n", encoding="utf-8")
        write_json(target / "parsed.json", {
            key: value for key, value in parsed.items() if key != "code"
        } | ({"code_sha256": sha256_text(code)} if code else {}))
        write_json(target / "precheck.json", precheck)
        write_json(target / "structure-space.json", space)
        accepted = (
            usage_by_task.get(task_id, {}).get("ingestable_channel") is True
            and parsed.get("status") == "ok"
            and precheck.get("ok") is True
            and space.get("ok") is True
        )
        row = {"task": task_id, "parse_status": parsed.get("status"),
               "static_precheck": precheck.get("ok"), "structure_space": space.get("ok"),
               "accepted_for_behavior_preflight": accepted,
               "code_sha256": sha256_text(code) if code else None,
               "problems": list(parsed.get("problems") or [])
                           + list(precheck.get("problems") or [])
                           + list(space.get("problems") or [])}
        write_json(target / "record.json", row)
        rows.append(row)
    initial = json.loads((_project_file(_PROJECT_ROOT, BATCH / "ingest-summary.json")).read_text(encoding="utf-8"))
    accepted = ["S4"] if "S4" in initial["accepted"] else []
    accepted.extend(row["task"] for row in rows if row["accepted_for_behavior_preflight"])
    write_json(_project_file(_PROJECT_ROOT, BATCH / "repair-ingest-summary.json"), {
        "schema": "r10-structural-repair-ingest/1", "repairs": rows,
        "all_accepted_for_behavior_preflight": sorted(accepted),
        "closed_failed": [row["task"] for row in rows
                          if not row["accepted_for_behavior_preflight"]],
        "effect_evaluation_started": False,
        "note": "每题修复额度已用尽；失败项关闭，不再调用模型。",
    })
    print(json.dumps(json.loads((_project_file(_PROJECT_ROOT, BATCH / "repair-ingest-summary.json")).read_text(encoding="utf-8")),
                     ensure_ascii=False, indent=2))


def canonicalize_space_comment(code: str) -> tuple[str, dict]:
    """把模型给出的六配置表规范成冻结 schema；只改注释，不改可执行源码。"""
    match = SPACE_RE.search(code)
    if match is None:
        raise ValueError("缺 STRUCTURE_SPACE_JSON")
    raw = json.loads(match.group(1))
    configs_raw = raw.get("configs")
    if not isinstance(configs_raw, list) or len(configs_raw) != 6:
        raise ValueError("没有恰好六个原始配置")
    constants = module_numeric_constants(code)
    if not 1 <= len(constants) <= 4:
        raise ValueError("模块数值常数数量不在 1—4")
    names = list(constants)

    def canonical_name(name: str) -> str | None:
        if name in constants:
            return name
        upper = str(name).upper()
        return upper if upper in constants else None

    configs = []
    labels = []
    for index, item in enumerate(configs_raw):
        if not isinstance(item, dict):
            raise ValueError(f"config[{index}] 不是对象")
        labels.append(item.get("name"))
        row = {}
        for key, value in item.items():
            if key == "name":
                continue
            target = canonical_name(key)
            if target is None:
                raise ValueError(f"config[{index}] 含未知参数 {key}")
            if not numeric(value):
                raise ValueError(f"config[{index}].{key} 不是有限数")
            row[target] = value
        if set(row) != set(names):
            raise ValueError(f"config[{index}] 未完整覆盖模块常数")
        configs.append(row)
    if len({tuple((name, float(row[name])) for name in names) for row in configs}) != 6:
        raise ValueError("六个原始配置不互异")
    raw_zero = raw.get("zero_effect")
    if not isinstance(raw_zero, dict) or not raw_zero:
        raise ValueError("zero_effect 缺失")
    zero_subset = {}
    for key, value in raw_zero.items():
        target = canonical_name(key)
        if target is None or not numeric(value):
            raise ValueError(f"zero_effect 含无效参数 {key}")
        zero_subset[target] = value
    zero_candidates = [row for row in configs if all(
        float(row[name]) == float(value) for name, value in zero_subset.items())]
    if len(zero_candidates) != 1:
        named = [row for label, row in zip(labels, configs) if label in ("zero", "zero_effect")]
        if len(named) != 1:
            raise ValueError("无法唯一确定完整 zero_effect 配置")
        zero_candidates = named
    zero = dict(zero_candidates[0])
    parameters = {}
    for name in names:
        domain = []
        for row in configs:
            value = row[name]
            if float(value) not in {float(item) for item in domain}:
                domain.append(value)
        if len(domain) < 2:
            raise ValueError(f"参数 {name} 在六配置中没有变化")
        parameters[name] = domain
    canonical = {"parameters": parameters, "zero_effect": zero, "configs": configs}
    header = "# STRUCTURE_SPACE_JSON: " + json.dumps(
        canonical, ensure_ascii=False, separators=(",", ":"))
    normalized = code[:match.start()] + header + code[match.end():]
    return normalized, {"raw": raw, "canonical": canonical,
                        "normalizations": ["参数域由六配置逐参数投影",
                                           "删除仅供人读的 config.name",
                                           "参数名绑定模块级大写常数",
                                           "zero_effect 扩展为完整配置"]}


def normalize_deliveries() -> None:
    """生成工程归一化副本；模型原始回复和修复源码保持不变。"""
    repair_usage = json.loads((_project_file(_PROJECT_ROOT, BATCH / "repair-call-usage.json")).read_text(encoding="utf-8"))
    clean_channel = {row["task"]: row["ingestable_channel"] for row in repair_usage["calls"]}
    rows = []
    for task_id in ("S1", "S2", "S3"):
        source_path = _project_file(_PROJECT_ROOT, BATCH / "generations" / task_id / "repair" / "candidate.py")
        original = source_path.read_text(encoding="utf-8")
        normalized, space_record = canonicalize_space_comment(original)
        executable_changes = []
        if task_id == "S3":
            replacements = [
                ("if branches is not None and isinstance(branches, (list, tuple)):",
                 "if branches is not None:"),
                ("                if not isinstance(branch, dict):\n                    continue\n", ""),
                (" or not isinstance(combined, (int, float))", ""),
                (" or not isinstance(remain, (int, float))", ""),
            ]
            for before, after in replacements:
                count = normalized.count(before)
                if count != 1:
                    raise RuntimeError(f"S3 合同等价替换匹配数异常：{before!r} -> {count}")
                normalized = normalized.replace(before, after)
                executable_changes.append({"before": before, "after": after,
                                           "reason": "输入合同已限定容器/数值形状；移除非白名单 isinstance"})
        target = _project_file(_PROJECT_ROOT, BATCH / "generations" / task_id / "normalized")
        target.mkdir(parents=True, exist_ok=True)
        (target / "candidate.py").write_text(normalized.rstrip("\n") + "\n", encoding="utf-8")
        precheck = gen.precheck_action_value_candidate(normalized)
        space = validate_space(normalized)
        write_json(target / "precheck.json", precheck)
        write_json(target / "structure-space.json", space)
        record = {
            "task": task_id,
            "source_sha256": sha256_text(original),
            "normalized_sha256": sha256_text(normalized),
            "comment_only_normalization": not executable_changes,
            "space_normalization": space_record["normalizations"],
            "executable_changes": executable_changes,
            "static_precheck": precheck.get("ok"),
            "structure_space": space.get("ok"),
            "channel_clean": clean_channel.get(task_id),
            "accepted_for_behavior_preflight": (
                clean_channel.get(task_id) is True
                and precheck.get("ok") is True
                and space.get("ok") is True
            ),
            "problems": list(precheck.get("problems") or []) + list(space.get("problems") or []),
        }
        write_json(target / "normalization-record.json", record)
        rows.append(record)
    initial_s4 = json.loads((_project_file(_PROJECT_ROOT, BATCH / "ingest-summary.json")).read_text(encoding="utf-8"))
    accepted = ["S4"] if "S4" in initial_s4["accepted"] else []
    accepted.extend(row["task"] for row in rows if row["accepted_for_behavior_preflight"])
    write_json(_project_file(_PROJECT_ROOT, BATCH / "normalization-summary.json"), {
        "schema": "r10-structural-engineering-normalization/1",
        "rows": rows,
        "accepted_for_behavior_preflight": sorted(accepted),
        "effect_evaluation_started": False,
        "note": "原始模型交付不覆盖；S1/S2 只规范注释，S3 另做输入合同等价的白名单替换。",
    })
    print(json.dumps(json.loads((_project_file(_PROJECT_ROOT, BATCH / "normalization-summary.json")).read_text(encoding="utf-8")),
                     ensure_ascii=False, indent=2))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "call-initial", "ingest",
                                           "prepare-repair", "call-repair", "ingest-repair",
                                           "normalize"))
    args = parser.parse_args()
    if args.action == "prepare":
        prepare()
    elif args.action == "call-initial":
        call_initial()
    elif args.action == "ingest":
        ingest()
    elif args.action == "prepare-repair":
        prepare_repair()
    elif args.action == "call-repair":
        call_repair()
    elif args.action == "ingest-repair":
        ingest_repair()
    else:
        normalize_deliveries()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
