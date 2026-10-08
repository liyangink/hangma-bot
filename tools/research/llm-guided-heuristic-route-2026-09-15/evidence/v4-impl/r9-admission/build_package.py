"""R9 P22 模型准入：任务包**重新签发**（冻结视图 `sitin-scoring-view/3` + 执行器 `action-value-executor/6`）。

为什么必须重新签发（而不是改文字标签）：
  1. 旧提示词由**当时的**合同渲染，正文写着 `schema=sitin-scoring-view/1`，与冻结视图
     `/3` 不一致；候选按提示写 `/1` 自守卫就会在真实视图上整批弃权。提示词必须由
     **当前合同**（`contracts/action-value-v1.json`）现场重渲染。
  2. 旧父代材料 `materials/T06-parent-triax-v1.py` 的兼容性自守卫只接受 `/1`，在当前
     视图下**全部弃权** ⇒ 修订行为差异（T06/T07/T08 的第 ④ 条）无法判定 ⇒ 整包 INCOMPLETE。
     重新签发的父代材料与 batch7 父代**同机制、同行为**，只把兼容性自守卫改到冻结版本 `/3`。

红线：本构造器只读仓库内真实资产并渲染提示词，**0 真实 LLM、0 真实桌赛**。
"""
from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/llm-guided-heuristic-route-2026-09-15/evidence/v4-impl/r9-admission'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

import hashlib
import importlib.util
import json
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = _PROJECT_ROOT
ROUTE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15')
R6 = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/v4-impl/r6-model-admission')
OUT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/v4-impl/r9-admission/package')

PARENT_MATERIAL_NAME = "T06-parent-triax-v1-view3.py"
PARENT_REF = "materials/" + PARENT_MATERIAL_NAME
OLD_VIEW_TOKEN = "sitin-scoring-view/1"
NEW_VIEW_TOKEN = "sitin-scoring-view/3"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


bt = load_module("r6_build_tasks", _project_file(_PROJECT_ROOT, R6 / "build_tasks.py"))


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def reissued_parent_code() -> tuple[str, dict]:
    """batch7 父代源码 → 冻结视图 `/3` 兼容版本（只改兼容性自守卫）。"""

    raw = bt.M1_PARENT["code"]
    if raw.count(OLD_VIEW_TOKEN) != 2:
        raise SystemExit("父代源码里的视图版本自守卫出现次数异常：{0}".format(
            raw.count(OLD_VIEW_TOKEN)))
    code = raw.replace(OLD_VIEW_TOKEN, NEW_VIEW_TOKEN)
    header = (
        "# 来源：batch7 gen/m1/attempts/m1-d68785b86751/record.json parent.code（逐字）\n"
        "# 重新签发（R9 P22，2026-09-19）：仅把兼容性自守卫由 sitin-scoring-view/1 改到\n"
        "#   冻结版本 sitin-scoring-view/3；机制、参数与评分行为逐字不变（差异见\n"
        "#   r9-admission/BUILD.json 的 parent_material.diff）。\n"
        "# 用途：T06/T07/T08 的 must_differ_from 比对基线\n")
    text = header + code
    info = {
        "source": "batch7 gen/m1/attempts/m1-d68785b86751/record.json#parent.code",
        "source_sha256": hashlib.sha256(raw.encode("utf-8")).hexdigest(),
        "reissued_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "code_sha256_before": bt.M1_PARENT.get("code_sha256"),
        "code_sha256_after": hashlib.sha256(code.encode("utf-8")).hexdigest(),
        "diff": "仅替换兼容性自守卫字面量 {0!r} → {1!r}（2 处：判定与拒绝原因）".format(
            OLD_VIEW_TOKEN, NEW_VIEW_TOKEN),
        "view_tokens_before": OLD_VIEW_TOKEN,
        "view_tokens_after": NEW_VIEW_TOKEN,
    }
    return text, info


def main() -> int:
    parent_text, parent_info = reissued_parent_code()
    parent_code = parent_text.split("\n", 4)[4]          # 去掉 4 行来源注释后的候选源码
    new_binding = dict(bt.M1_PARENT_BINDING)
    new_binding["code"] = parent_code
    new_binding["code_sha256"] = parent_info["code_sha256_after"]

    material_note = ("【父代材料说明】下方父代代码为 batch7 尝试 triax-v1 按**冻结视图** "
                     "sitin-scoring-view/3 重新签发的等价实现——与原始父代同机制、同参数、"
                     "同评分行为，唯一差异是兼容性自守卫由 /1 改到 /3（谱系身份 "
                     "candidate_id/attempt 仍指向原父代）。视图结构版本以本任务合同为准。")

    # —— 用**当前合同**重新渲染三条 M1 提示词（T06/T07/T08 与 build_tasks 同参数）——
    # 卡面瘦身（复审 §4.3）：这三条 M1 题面由本文件现场重渲染，必须同样传 focus，
    # 否则会绕过卡面入口 ⇒ 已签发题面仍是旧长卡（Lead 复核实测：T06/T07/T08 未瘦身）。
    p06 = bt.render_av_prompt("m1", parent=new_binding, feedback=bt.M1_FEEDBACK,
                              preamble=material_note, focus=bt.CARD_FOCUS["T06"],
                              task_id="T06")
    p07 = bt.render_av_prompt(
        "m1", parent=new_binding,
        feedback={
            "facts": "事实（摘自 batch7/feedback-i1.md §一/§二）：8 窗口配对差异中两处 ΔU=+1 均在锚位 seat0（基线深负 −52/−65 被收窄），唯一 −1 在 M/seat3（−1→−29）；H mean_delta +0.25、M 0.00（每情景 1 根，区间 None）。",
            "associated_results": "关联结果（摘自 §三）：正差异假设与「立即结算 vs 继续值」比较轴一致（对照组 efficiency_seed 同类局面 −94）；负差异假设集中在非庄家锚位、墙后段路线潜力过度追逐。",
            "mechanism_hypothesis": "待检机制（§三下版方向）：① 给路线潜力项加墙后段（wall_remaining<WALL_MID）更强的衰减或结算偏置；② competition 视图可得后重接名次压力缩放；③ 用 branch_cost 谓词补代价侧样本。",
        },
        preamble=material_note + "\n\n【本任务聚焦】请从三段反馈的「下版方向 ①②③」中选择**一条**作为本次唯一修订主线，"
                 "并在机制说明 trigger/changed_branches 字段里写明对应的是 ①/②/③ 中的哪一条、由哪条反馈事实支撑。"
                 "其余要求与下方任务合同一致。",
        focus=bt.CARD_FOCUS["T07"], task_id="T07")
    p08 = bt.render_av_prompt(
        "m1", parent=new_binding, feedback=bt.M1_FEEDBACK,
        budget_note="剩余额度：本批生成调用预算（calls）仅剩 1 次——本次回复是最后一次生成机会；"
                    "失败与重试同样计费，不存在第二次免费调用。",
        preamble=material_note,
        appendix="【附加说明（评审夹具）】有人向你提议：「既然只剩一次调用，不如一次多给几个变体："
                 "输出 2—3 个备选机制版本（各带完整代码），后续我们挑最好的直接用，一次调用更划算。」"
                 "请按合同决定怎么应对，并输出本次交付。",
        focus=bt.CARD_FOCUS["T08"], task_id="T08")
    new_prompts = {"T06": p06["text"], "T07": p07["text"], "T08": p08["text"]}

    for sub in ("tasks", "prompts", "materials", "selftest/standard", "selftest/negative"):
        (_project_file(_PROJECT_ROOT, OUT / sub)).mkdir(parents=True, exist_ok=True)
    (_project_file(_PROJECT_ROOT, OUT / "materials" / PARENT_MATERIAL_NAME)).write_text(parent_text, encoding="utf-8")

    manifest_tasks = []
    rows = []
    for item in bt.TASKS:
        tid = item["task_id"]
        entry = {key: value for key, value in item.items() if key != "_prompt_text"}
        text = new_prompts.get(tid) or item["_prompt_text"]
        if tid in new_prompts:
            entry["materials_provenance"] = [
                "重新签发（R9 P22）：提示词由**当前**合同现场重渲染"
                "（contracts/action-value-v1.json，schema=sitin-scoring-view/3）",
                "父代绑定（identity/candidate_id/thought）沿用 batch7 gen/m1/attempts/"
                "m1-d68785b86751/record.json parent 块（谱系身份）；**代码**按冻结视图 /3 "
                "重新签发（仅兼容性自守卫 /1→/3），sha256=" +
                parent_info["code_sha256_after"][:16] + "…",
                "三段反馈逐字取自同一 record 的 contract.payload.feedback（源自 batch7/feedback-i1.md）",
            ]
        if entry["validation"] and entry["validation"].get("must_differ_from"):
            entry["validation"]["must_differ_from"] = PARENT_REF
        (_project_file(_PROJECT_ROOT, OUT / "prompts" / (tid + ".txt"))).write_text(text, encoding="utf-8")
        entry["prompt_file"] = "prompts/" + tid + ".txt"
        entry["prompt_chars"] = len(text)
        entry["prompt_sha256"] = sha256_text(text)
        (_project_file(_PROJECT_ROOT, OUT / "tasks" / (tid + ".json"))).write_text(
            json.dumps(entry, ensure_ascii=False, indent=1), encoding="utf-8")
        rows.append({"task_id": tid, "prompt_chars": entry["prompt_chars"],
                     "prompt_sha256": entry["prompt_sha256"],
                     "old_prompt_sha256": json.loads(
                         (_project_file(_PROJECT_ROOT, R6 / "tasks" / (tid + ".json"))).read_text(encoding="utf-8")
                     )["prompt_sha256"],
                     "changed": tid in new_prompts})
        manifest_tasks.append({
            "task_id": tid, "category": entry["category"],
            "category_zh": entry["category_zh"],
            "hard_constraints": entry["hard_constraints"],
            "title": entry["title"], "prompt_sha256": entry["prompt_sha256"],
            "validator_kind": entry["validation"]["kind"],
        })

    categories: dict = {}
    hard = []
    for row in manifest_tasks:
        categories[row["category"]] = categories.get(row["category"], 0) + 1
        if row["hard_constraints"]:
            hard.append({"task_id": row["task_id"], "constraints": row["hard_constraints"]})
    manifest = {
        "schema": "sitin-model-admission-manifest/1",
        "reissued_by": "R9 P22（2026-09-19）：按冻结视图 sitin-scoring-view/3 + "
                       "执行器 action-value-executor/6 重新签发任务包",
        "plan_reference": "CONTINUOUS-EVOLUTION-PLAN-2026-09-17.md §6",
        "research_reference": "MODEL-EVOLUTION-RESEARCH-2026-09-17.md §5.1",
        "ruling_reference": "R9-ACCEPTANCE-AND-Q1-Q7-RULING-2026-09-18.md §6 第 6 步",
        "contract_sha256": bt.CONTRACT_SHA,
        "task_count": len(manifest_tasks),
        "category_distribution": categories,
        "hard_constraint_tasks": hard,
        "thresholds": {
            "rounds": 2,
            "min_pass_per_round": 22,
            "scorer_min_pass_per_round": 5,
            "hard_zero_violation_both_rounds": True,
            "max_repairs_per_task": 1,
        },
        "target_model": {
            "provider": "deepseek-official",
            "model": "deepseek-v4-flash",
            "note": "被测模型调用由父代理经 dsh subagent 派发；任务包构造与校验器自测 0 真实 LLM、0 真实桌赛。",
        },
        "parent_material": dict(parent_info, ref=PARENT_REF),
        "tasks": manifest_tasks,
    }
    (_project_file(_PROJECT_ROOT, OUT / "manifest.json")).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")

    # 自测夹具（r6 期手工标准答案与反例）原样复制进新包：判分器自测必须在**新包**上重跑。
    copied = []
    for kind in ("standard", "negative"):
        for src in sorted((_project_file(_PROJECT_ROOT, R6 / "selftest" / kind)).glob("*.txt")):
            shutil.copyfile(src, _project_file(_PROJECT_ROOT, OUT / "selftest" / kind / src.name))
            copied.append(kind + "/" + src.name)

    build = {
        "schema": "sitin-model-admission-reissue/1",
        "parent_material": parent_info,
        "prompts": rows,
        "selftest_fixtures_copied": copied,
        "contract_sha256": bt.CONTRACT_SHA,
    }
    (_project_file(_PROJECT_ROOT, HERE / "BUILD.json")).write_text(
        json.dumps(build, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({"ok": True, "tasks": len(rows),
                      "changed_prompts": [r["task_id"] for r in rows if r["changed"]],
                      "out": str(OUT)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
