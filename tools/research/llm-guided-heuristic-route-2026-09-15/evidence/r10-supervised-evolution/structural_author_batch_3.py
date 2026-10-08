"""R10 第三结构批次：反思第二批稀疏行为，再生成两个吃/过机会成本结构。

本工具只负责冻结反思、作者提示、调用证据和生成端静态摄入。它不运行效果评测，
不把终端阶段差当作单步动作标签，也不改变稳定 V2、规则、协议或发布状态。
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


BATCH = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/structural-search-03-20260921')
V2 = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/v2-parent-revalidation-20260920/parent/generation/candidate.py')
S3 = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/structural-search-01-20260921/behavior-preflight-v2/configurations/s3-cfg-02/candidate.py')
T2 = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/structural-search-02-20260921/behavior-preflight-v2/configurations/s2-cfg-04/candidate.py')
DIAGNOSTIC = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/structural-search-02-20260921/post-close-diagnostic')
EXPECTED_HASHES = {
    "v2": "a0c389b3a4757a38febf5ca6bf16e9c4779159df0c15b82d2e804e1f4ac9638f",
    "s3": "984c2b2e52baa042bbd08ed63b4ff74865b2f310a2f71180b76cde945f909c41",
    "t2": "e41532984aad6a1da953d203969592dac715b975ff3558276fbbf10cb1d0a052",
}
EXPECTED_CONFIG = {
    "provider": "zai-coding-cn",
    "model": "glm-5.3",
    "reasoningEffort": "high",
    "maxTokens": 32768,
}


TASKS = {
    "C1": {
        "name": "contrastive-chi-pass-recombination",
        "objective": (
            "以稳定V2为零效应父代，把S3的后续分支价值和T2的选择性收缩重组为一个"
            "只在同窗吃/过事实可比较时触发的机会成本结构。"
        ),
        "change": (
            "新增项必须显式比较同一response_chi窗口中的chi与pass，而不是给chi独立加一个"
            "绝对后续分。主判据只能使用向听、直接有效牌支持、followup_branches和权威"
            "family_progress_entries；七对因副露关闭只能作为可见机会成本，不能当固定禁止吃。"
        ),
        "hypothesis": (
            "EoH E2与ReEvo式对比重组：父代的弱点来自绝对分支项在极少数平分边界改选；"
            "把动作价值改写为同窗相对净优势，可能扩大可解释覆盖并减少无竞争窗口噪声。"
        ),
    },
    "C2": {
        "name": "minimal-chi-pass-ordinal-gate",
        "objective": (
            "从稳定V2构造一个比S3/T2更短的吃/过序数门，只处理同向听或近似平分的响应窗口。"
        ),
        "change": (
            "删除S3/T2的support/cap多维自由度；只允许一个主序数或分层判据，明确区分"
            "听牌、未听和七对路线关闭事实。不得使用局终结果、H/M标签、对手身份或牌墙。"
        ),
        "hypothesis": (
            "EoH M3和最小描述长度思路：稀疏改选说明复杂绝对项不可辨；更短的局面内"
            "chi/pass门若能在真实观察上产生有界差异，更适合机械配置和后续归因。"
        ),
    },
}


EXTRA_REQUIREMENTS = first.COMMON_REQUIREMENTS + """
- 本批的 zero_effect 必须逐分等价于稳定 V2（sha256=a0c389b3…），不是 S3 或 T2；默认常数可为非零配置。
- 只允许在 phase=response_chi 且同窗同时存在已知 chi 与 pass 时触发新增结构；其他窗口必须精确退化到 V2。
- 不能从四个诊断窗口或阶段终局差推导动作标签；它们只证明旧结构改选稀疏且集中在吃/过边界。
- family_progress_entries 是 HangmaRules 生产的权威可见事实；只能读取结构字段，不解析中文 basis 文本。
- 七对关闭不是固定惩罚。只有同窗 pass 的七对路线仍公开可用且主判据需要比较机会成本时，才可作为有界证据。
- current_stage_scores、座位、庄家和轮号不得作为本批主门控；不得把 M、根号、seed 或窗口摘要写进运行时代码。
- 不再开放 FBV_GAIN/FBV_SUPPORT/FBV_SUPPORT_CAP/FBV_CAP 原四维邻域；参数至多三个，六配置必须含稳定V2零效应。
- 完整源码优先，建议不超过360行；四字段说明每项不超过260个汉字。
"""


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read_parent(name: str, path: Path, thought: str) -> dict:
    code = path.read_text(encoding="utf-8")
    digest = first.sha256_text(code)
    if digest != EXPECTED_HASHES[name]:
        raise ValueError(f"父代{name}摘要漂移：{digest}")
    return {
        "name": name,
        "path": str(path),
        "identity": digest,
        "candidate_id": digest,
        "thought": thought,
        "code": code,
        "code_sha256": digest,
    }


def parents() -> dict[str, dict]:
    return {
        "v2": read_parent("v2", V2, "稳定V2：当前线上可审计研究基线和本批唯一零效应父代。"),
        "s3": read_parent(
            "s3", S3,
            "S3：在V2上加入绝对最佳combined_shanten后续项；跨新来源弱正但未分辨。",
        ),
        "t2": read_parent(
            "t2", T2,
            "T2：选择性收缩S3后续项；优于S3但仍低于V2，只作失败机制材料。",
        ),
    }


def compact_windows() -> list[dict]:
    rows = []
    for path in sorted((_project_file(_PROJECT_ROOT, DIAGNOSTIC / "windows")).glob("*.json")):
        value = json.loads(path.read_text(encoding="utf-8"))
        actions = []
        for action in value["candidate_view"]["actions"]:
            branches = action.get("followup_branches")
            known_branches = branches if isinstance(branches, list) else []
            best_shanten = min(
                (branch.get("combined_shanten") for branch in known_branches
                 if isinstance(branch.get("combined_shanten"), (int, float))
                 and not isinstance(branch.get("combined_shanten"), bool)),
                default=None,
            )
            best_support = max(
                (branch.get("support_remaining") for branch in known_branches
                 if branch.get("combined_shanten") == best_shanten
                 and isinstance(branch.get("support_remaining"), (int, float))
                 and not isinstance(branch.get("support_remaining"), bool)),
                default=None,
            )
            direct_support = sum(
                tile["remaining_estimate"] for tile in (action.get("useful_tiles") or [])
                if isinstance(tile, dict)
                and isinstance(tile.get("remaining_estimate"), (int, float))
                and not isinstance(tile.get("remaining_estimate"), bool)
            )
            actions.append({
                "action_key": action.get("action_key"),
                "action_type": action.get("action_type"),
                "shanten_after": action.get("shanten_after"),
                "standard_shanten_after": action.get("standard_shanten_after"),
                "seven_pairs_shanten_after": action.get("seven_pairs_shanten_after"),
                "direct_support": direct_support,
                "followup_branch_count": len(known_branches),
                "best_branch_shanten": best_shanten,
                "best_branch_support": best_support,
                "family_entries": [
                    {
                        "family": entry.get("family"),
                        "progress": entry.get("progress"),
                        "route_status": entry.get("route_status"),
                    }
                    for entry in (action.get("family_progress_entries") or [])
                    if isinstance(entry, dict)
                ],
            })
        rows.append({
            "view_sha256": value["view_sha256"],
            "phase": value["observation"]["phase"],
            "round_no": value["observation"]["round_no"],
            "transition_s3_to_t2": value["transition"],
            "s3_scores": value["parent"]["scores"],
            "t2_scores": value["child"]["scores"],
            "actions": actions,
            "interpretation_limit": "阶段终局差不是本窗口动作标签",
        })
    if len(rows) != 4:
        raise ValueError(f"诊断窗口数量应为4，实际{len(rows)}")
    return rows


def settings_files() -> None:
    settings = """# R10 第三结构批次；一次反思、两个有界作者题。
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
        + "    provider: zai-coding-cn\n    model: glm-5.3\n",
        encoding="utf-8",
    )


def prepare_reflection() -> None:
    if BATCH.exists():
        raise SystemExit("第三结构批次已存在；拒绝覆盖")
    BATCH.mkdir(parents=True)
    p = parents()
    windows = compact_windows()
    summary = {
        "second_batch_effect": {
            "t2_equal_point": -0.005859375,
            "t2_conservative_fitness": -0.015625,
            "s3_equal_point": -0.01171875,
            "s3_conservative_fitness": -0.01953125,
            "result": "T2优于S3但未超过稳定V2，不进入独立复核",
        },
        "diagnostic": {
            "tables": 16,
            "views": 5587,
            "preferred_changes": 4,
            "scope": "全部M族response_chi；H轨迹零改选",
            "warning": "终局差不可归因到单个动作",
        },
        "windows": windows,
    }
    parts = [
        "你是杭麻离线启发式搜索的反思研究员。本调用只做ReEvo式短期反思，不生成候选源码。",
        "目标是解释第二批为何只产生四次吃/过改选，并提出下一批可证伪的结构设计原则。",
        "严格遵守：只用PlayerObservation/candidate_view公开事实；杭麻只允许规则已生产的合法动作和结算；"
        "support是未见枚数估计而非概率；不得引入点炮、日麻番型、隐藏牌墙、对手暗牌或终局动作标签。",
        "阶段终局差只能说明一个完整阶段的观察结果，不能证明四个窗口中吃或过正确。",
        "请比较三个父代，明确旧项为何稀疏、哪些量重复计数、哪些事实足以表达同窗吃/过机会成本。",
        "输出严格JSON对象，键恰为 diagnosis、preserve、reject、hypotheses、preferred_experiment。",
        "hypotheses恰好三个，每个含 mechanism、observable_trigger、falsifier、rule_risk；"
        "preferred_experiment含primary_structure、why、parameters（最多3个）和zero_effect。不要输出代码。",
        "",
        "【冻结效果与四个真实分歧窗口的压缩证据】",
        json.dumps(summary, ensure_ascii=False, indent=2),
    ]
    for name in ("v2", "s3", "t2"):
        parts.extend([
            "", f"【{name.upper()} 父代身份与完整源码】",
            f"sha256={p[name]['code_sha256']}；{p[name]['thought']}",
            gen.FENCE + "python", p[name]["code"].rstrip("\n"), gen.FENCE,
        ])
    prompt = "\n".join(parts)
    target = _project_file(_PROJECT_ROOT, BATCH / "reflection-prompts/R0")
    target.mkdir(parents=True)
    (target / "prompt.txt").write_text(prompt, encoding="utf-8")
    settings_files()
    write_json(_project_file(_PROJECT_ROOT, BATCH / "reflection-manifest.json"), {
        "schema": "r10-structural-reflection/1",
        "task": "R0",
        "prompt_sha256": first.sha256_text(prompt),
        "prompt_chars": len(prompt),
        "parent_hashes": EXPECTED_HASHES,
        "source_summary_sha256": first.sha256_text(
            json.dumps(summary, ensure_ascii=False, sort_keys=True)),
        "expected_request_config": EXPECTED_CONFIG,
        "effect_evaluation_started": False,
    })
    write_json(_project_file(_PROJECT_ROOT, BATCH / "authorization.json"), {
        "schema": "sitin-authorization/1",
        "authorization_id": "r10-structural-search-03-20260921",
        "trusted": True,
        "issued_by": "Codex root",
        "issued_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "issuance_basis": (
            "用户授权API上限前由root安排zai-coding-cn GLM5.3调用，并要求按文献复盘后继续；"
            "第二结构批次未超过V2，依EoH/ReEvo转入一次反思与两个有界多父代结构题。"
        ),
        "route": "offline_structural_reflection_and_authoring",
        "max_reflection_calls": 1,
        "max_initial_calls": 2,
        "max_repair_calls": 2,
        "max_total_calls": 5,
        "per_call_limits": {"tokens_input": 196608, "tokens_output": 32768},
        "allowed_accounts": {"tokens_input": 983040, "tokens_output": 163840},
        "effect_tables": 0,
        "confirmation_reserved": 0,
        "autonomous_admission": False,
        "scope": "离线反思与结构提案；预检后另冻效果预算；不得确认或发布",
    })
    (_project_file(_PROJECT_ROOT, BATCH / ".gitignore")).write_text("dispatch-ledger/\n", encoding="utf-8")
    print(json.dumps({"status": "REFLECTION_PREPARED", "prompt_chars": len(prompt)},
                     ensure_ascii=False, indent=2))


def checked_usage(call_row: dict) -> tuple[dict, bool]:
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
        and values["outputTokens"] <= 32768
    )
    return usage, clean


def dispatch_calls(task_ids: list[str], prompt_dir: Path, replies: Path,
                   plan: Path, kind: str, usage_path: Path) -> None:
    if replies.exists():
        raise SystemExit(f"回复目录已存在，拒绝重复调用：{replies}")
    dispatch._expected_request_config = lambda _package: dict(EXPECTED_CONFIG)
    report = dispatch.dispatch(
        BATCH, task_ids, replies, plan,
        model_patch=str(_project_file(_PROJECT_ROOT, BATCH / "route.patch.yml")), timeout_s=900, concurrency=1,
        prompt_dir=prompt_dir, kind=kind,
    )
    rows, problems = [], []
    for call_row in sorted(report["calls"], key=lambda item: item["task"]):
        usage, clean = checked_usage(call_row)
        rows.append({
            "task": call_row["task"], "run_id": call_row.get("run_id"),
            "observed_config": call_row.get("request_config"),
            "protocol_ok": call_row.get("protocol_ok"),
            "exit_code": call_row.get("exit_code"), "usage": usage,
            "ingestable_channel": clean,
        })
        if not clean:
            problems.append(call_row["task"])
    write_json(usage_path, {
        "schema": "r10-structural-call-usage/3", "calls": rows,
        "total_input_tokens": sum((row["usage"].get("usage") or {}).get("inputTokens", 0)
                                  for row in rows),
        "total_output_tokens": sum((row["usage"].get("usage") or {}).get("outputTokens", 0)
                                   for row in rows),
        "problems": problems,
    })
    print(json.dumps({"status": "COMPLETE_WITH_PROBLEMS" if problems else "COMPLETE",
                      "problems": problems}, ensure_ascii=False))


def call_reflection() -> None:
    manifest = json.loads((_project_file(_PROJECT_ROOT, BATCH / "reflection-manifest.json")).read_text(encoding="utf-8"))
    prompt = (_project_file(_PROJECT_ROOT, BATCH / "reflection-prompts/R0/prompt.txt")).read_text(encoding="utf-8")
    if first.sha256_text(prompt) != manifest["prompt_sha256"]:
        raise ValueError("反思提示摘要漂移")
    dispatch_calls(
        ["R0"], _project_file(_PROJECT_ROOT, BATCH / "reflection-prompts"), _project_file(_PROJECT_ROOT, BATCH / "reflection-replies"),
        _project_file(_PROJECT_ROOT, BATCH / "plan-reflection.json"), "structural-reflection-3",
        _project_file(_PROJECT_ROOT, BATCH / "reflection-call-usage.json"),
    )


def prepare_authors() -> None:
    usage = json.loads((_project_file(_PROJECT_ROOT, BATCH / "reflection-call-usage.json")).read_text(encoding="utf-8"))
    if len(usage.get("calls") or []) != 1 or usage["calls"][0].get("ingestable_channel") is not True:
        raise ValueError("反思通道证据不完整，拒绝准备作者卡")
    reflection = (_project_file(_PROJECT_ROOT, BATCH / "reflection-replies/R0.txt")).read_text(encoding="utf-8").strip()
    if not reflection:
        raise ValueError("反思回复为空")
    p = parents()
    evidence = json.dumps({
        "aggregate": {
            "t2_vs_v2_equal_point": -0.005859375,
            "t2_vs_v2_conservative": -0.015625,
            "s3_vs_v2_equal_point": -0.01171875,
            "s3_vs_v2_conservative": -0.01953125,
            "effect_tables": 2176,
        },
        "diagnostic": {
            "views": 5587, "preferred_changes": 4,
            "transitions": {"pass_to_chi": 3, "chi_to_pass": 1},
            "all_changes": "response_chi in M diagnostic trajectories",
            "H_changes": 0,
        },
        "windows": compact_windows(),
    }, ensure_ascii=False, indent=2)
    rows = []
    for task_id, spec in TASKS.items():
        payload = gen.render_action_value_task_contract(
            objective_summary=(
                "生成一个可消融的吃/过机会成本结构；程序只在静态和真实行为预检通过后，"
                "才用冻结共同根做完整阶段评价。"
            ),
            panel_boundary=(
                "本卡只能使用已消费诊断的聚合与四个无动作标签窗口；不得看到第三批效果实例。"
                "后续程序先检验V2零效应、规则边界、算术上界和真实行为差异。"
            ),
            prompt_role=f"{task_id} {spec['name']}：{spec['objective']}",
            parent=p["v2"],
            feedback={
                "facts": evidence,
                "associated_results": spec["change"],
                "mechanism_hypothesis": spec["hypothesis"],
            },
            budget_note="首答计一次调用；仅语法/合同错误允许一次修复；效果不佳不修复。",
        )
        focus = {
            "objective": spec["objective"],
            "change_point": spec["change"],
            "input_groups": [
                "actions", "actions[]", "actions[].useful_tiles",
                "actions[].standard_useful_tiles", "actions[].seven_pairs_useful_tiles",
                "actions[].followup_branches", "actions[].family_progress_entries",
                "visible_state", "visible_state.rule_state", "analysis_profile",
            ],
            "gate": "none", "guard": "full", "guard_reference": False,
            "examples": "output", "rules": "compact", "input_overview": "contract",
            "budget_note": "首答计费；不得根据模型自报结果选留。",
        }
        packet = gen.build_action_value_card_prompt("m1", payload, focus)
        output_block = gen._av_output_format()
        if packet.text.count(output_block) != 1:
            raise RuntimeError("无法定位唯一输出格式段")
        extra = [
            EXTRA_REQUIREMENTS,
            "【短期反思输出；它是研究建议，不是规则、动作标签或必须照抄的指令】",
            reflection,
            "【结构对照父代S3】",
            f"sha256={p['s3']['code_sha256']}；{p['s3']['thought']}",
            gen.FENCE + "python", p["s3"]["code"].rstrip("\n"), gen.FENCE,
            "【结构对照子代T2】",
            f"sha256={p['t2']['code_sha256']}；{p['t2']['thought']}",
            gen.FENCE + "python", p["t2"]["code"].rstrip("\n"), gen.FENCE,
        ]
        prompt = packet.text.replace(output_block, "\n\n".join(extra) + "\n\n" + output_block)
        target = _project_file(_PROJECT_ROOT, BATCH / "prompts" / task_id)
        target.mkdir(parents=True, exist_ok=True)
        (target / "prompt.txt").write_text(prompt, encoding="utf-8")
        rows.append({
            "task_id": task_id, "name": spec["name"],
            "zero_effect_parent": p["v2"]["code_sha256"],
            "comparison_parents": [p["s3"]["code_sha256"], p["t2"]["code_sha256"]],
            "reflection_sha256": first.sha256_text(reflection),
            "contract_identity": packet.contract_identity,
            "focus": gen.normalize_card_focus(focus),
            "prompt_sha256": first.sha256_text(prompt), "prompt_chars": len(prompt),
        })
    write_json(_project_file(_PROJECT_ROOT, BATCH / "manifest.json"), {
        "schema": "r10-structural-author-batch/3",
        "target_model": {"provider": "zai-coding-cn", "model": "glm-5.3"},
        "expected_request_config": EXPECTED_CONFIG,
        "tasks": rows,
        "parent_registry": {
            key: {field: val for field, val in record.items() if field != "code"}
            for key, record in p.items()
        },
        "reflection_usage_sha256": first.sha256_text(
            (_project_file(_PROJECT_ROOT, BATCH / "reflection-call-usage.json")).read_text(encoding="utf-8")),
        "effect_evaluation_started": False,
        "confirmation_reserved": 0,
    })
    print(json.dumps({"status": "AUTHORS_PREPARED", "tasks": rows},
                     ensure_ascii=False, indent=2))


def verify_author_prompts() -> list[str]:
    manifest = json.loads((_project_file(_PROJECT_ROOT, BATCH / "manifest.json")).read_text(encoding="utf-8"))
    result = []
    for row in manifest["tasks"]:
        prompt = (_project_file(_PROJECT_ROOT, BATCH / "prompts" / row["task_id"] / "prompt.txt")).read_text(encoding="utf-8")
        if first.sha256_text(prompt) != row["prompt_sha256"]:
            raise ValueError("作者提示摘要漂移：" + row["task_id"])
        result.append(row["task_id"])
    return result


def call_authors() -> None:
    task_ids = verify_author_prompts()
    dispatch_calls(
        task_ids, _project_file(_PROJECT_ROOT, BATCH / "prompts"), _project_file(_PROJECT_ROOT, BATCH / "replies"),
        _project_file(_PROJECT_ROOT, BATCH / "plan-initial.json"), "structural-initial-3",
        _project_file(_PROJECT_ROOT, BATCH / "initial-call-usage.json"),
    )


def ingest() -> None:
    task_ids = verify_author_prompts()
    usage = json.loads((_project_file(_PROJECT_ROOT, BATCH / "initial-call-usage.json")).read_text(encoding="utf-8"))
    by_task = {row["task"]: row for row in usage["calls"]}
    rows = []
    for task_id in task_ids:
        raw = (_project_file(_PROJECT_ROOT, BATCH / "replies" / f"{task_id}.txt")).read_text(encoding="utf-8")
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
            key: val for key, val in parsed.items() if key != "code"
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
    write_json(_project_file(_PROJECT_ROOT, BATCH / "ingest-summary.json"), {
        "schema": "r10-structural-ingest/3", "tasks": rows,
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
    parser.add_argument(
        "operation",
        choices=("prepare-reflection", "call-reflection", "prepare-authors", "call-authors", "ingest"),
    )
    args = parser.parse_args()
    {
        "prepare-reflection": prepare_reflection,
        "call-reflection": call_reflection,
        "prepare-authors": prepare_authors,
        "call-authors": call_authors,
        "ingest": ingest,
    }[args.operation]()
