"""P25 · 修复轮提示词的**冻结构造器**（包 C 协议件；零模型、零网络）。

为什么需要它：原协议允许每题 1 次修复，但修复提示词直接把判分器 problems 回灌给模型——
而 problems 里**逐字列着命中词表**（"缺少关键词组（任一即可）：保留现场 / 留现场 / …"），
等于把答案要点告诉模型。那样的"修复后通过"不是独立能力证据。

本次（评审 R9-P25 §C2/C4）把构造器从「归约 problems 文本」改为**消费判分器的结构化诊断**
（schema 见 sitin-admission-diagnostic/1），并按**公开字段白名单**渲染：

1. 诊断由**判分器**生成（错误码、公开合同路径、源码位置或**明确缺失**、实际类型/状态、
   期望谓词、对应公开示例），构造器只做渲染与脱敏，不再自己猜类别、不再截断到 40 字；
2. 渲染只允许白名单字段（DIAGNOSTIC_PUBLIC_FIELDS）；私有字段（原始问题文本、内部
   判据、材料引用、私有窗口名）一律丢弃并记录；
3. **包级诊断不进提示词**（如父代材料不兼容是任务包缺陷，不是模型的错）；
4. 兜底分支**不再复制原文**：没有可渲染诊断时给出具名的"诊断不可用"条目（原文不回灌）；
5. 脱敏断言覆盖 required_groups / forbidden / **mechanism_keyword_groups** /
   forbidden_tokens / 三个正则字段的字面片段，且**不再跳过长度 < 3 的词**；
   命中即**整段替换为占位符**，替换后再断言零泄漏（宁可少给信息，也不回灌词表）。

冻结口径（本轮起生效，改它即改协议）：
1. 修复提示词 = 原密封提示词（逐字） + 上一轮交付（逐字） + 结构化诊断（白名单渲染）
   + 固定要求句；
2. 诊断只来自判分器的结构化产物；构造器不做文本归约、不做同义词判断；
3. 脱敏断言：产出的新增文本里不得含该题任何词表条目（含机制词组与短词）。
"""
from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/llm-guided-heuristic-route-2026-09-15/evidence/v4-impl/r9-admission/p25-headless'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple

HERE = Path(__file__).resolve().parent
ADMISSION = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/v4-impl/r9-admission')
ROUTE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15')
REPO = _PROJECT_ROOT
sys.path.insert(0, str(ADMISSION))
sys.path.insert(0, str(_project_file(_PROJECT_ROOT, ROUTE / "tools")))

import sealed_dispatch as sd                                    # noqa: E402
import sitin_model_admission as admission                       # noqa: E402

#: 渲染用的**中文标签**同样必须过脱敏（评审 C4 复核）：标签里出现任何一题的词表条目，
#: 都会把该题的修复提示词构造打成失败（实测：T02「误/错」、T04「不得」、T11「观察/诊断」、
#: T14「继续」、T22「冻结」、T23「不得/合同」）。这里一律用不含业务词的中性标签，
#: 并由 build_repair_prompt 对**整块新增文本**再做一遍脱敏作为兜底。
REPAIR_HEADER = "【上一轮交付（逐字，仅供你修改，不要照抄解释）】"
PROBLEM_HEADER = "【本次交付的具名条目（仅含公开字段）】"
#: **输出形态条款按判分器 kind 出**（第七轮裁决：装配侧缺陷）。
#: 与卡面入口的 grader_kind 闭集同口径：code | repair | keyword
#: （sitin_model_admission 任务 JSON 的 validation.kind 就是这个闭集；卡面/瘦身侧必须传同一个值）。
REQUIREMENT = (
    "【本次要求】只针对上述条目修正你的交付，其余部分保持不变；"
    "条目里的编号、判据出处、位置、实际结果、应当满足的条件与合规范例都属于"
    "**公开事实**，可以直接按它们定位与修改。仍然只输出一个候选代码围栏"
    "（或按题面要求的交付形态），并遵守本提示词开头的密封条款与受限子集约束。"
    "**只改说明、文档字符串或注释的修订不算算法修复**：修复必须改动可执行代码，"
    "或在声明视图上产生可见的行为差异；解释文字另记，不替代代码改动。")

#: kind=code / kind=repair 的条款**逐字沿用历史文本**（第七轮要求：不得改动其它 kind 的既有文本）。
REQUIREMENT_CODE = REQUIREMENT
REQUIREMENT_REPAIR = REQUIREMENT
#: kind=keyword（T01–T04、T11–T16、T21–T24 与开发卡 TD05/TD06 这类决策卡）：要求
#: **中文短答正文**，明确**不得**要求代码围栏——旧条款写「输出一个候选代码围栏」，
#: 模型据此交了代码块，交付形态与题面不符（这不是模型问题，是装配侧缺陷）。
REQUIREMENT_KEYWORD = (
    "【本次要求】只针对上述条目修订你的交付，其余部分保持不变；"
    "条目里的编号、判据出处、位置、实际结果、应当满足的条件与合规范例都属于"
    "**公开事实**，可以直接按它们定位与修改。本题按题面【回答格式】写**中文短答**"
    "正文：先给结论，再给依据，并引用材料里的字段名、状态名与数字。"
    "**只交正文文本**：不要写任何围栏块（含代码块与机制说明块）；"
    "篇幅遵守题面的字数上限，并遵守本提示词开头的密封条款。")

#: kind → 输出形态条款（未登记 kind 回落到历史文本，fail-safe：不改判分语义）。
REQUIREMENT_BY_KIND: Dict[str, str] = {
    "code": REQUIREMENT_CODE,
    "repair": REQUIREMENT_REPAIR,
    "keyword": REQUIREMENT_KEYWORD,
}

#: 卡面入口闭集：sitin_model_admission 任务 JSON 与卡面 grader_kind 参数共用同一取值。
GRADER_KINDS: Tuple[str, ...] = ("code", "repair", "keyword")


def grader_kind(task: Dict[str, Any], override: Any = None) -> str:
    """解析本题的判分器 kind（卡面可显式传 grader_kind，口径与本函数一致）。"""
    if isinstance(override, str) and override.strip():
        return override.strip()
    validation = task.get("validation") or {}
    kind = validation.get("kind")
    return str(kind) if isinstance(kind, str) and kind.strip() else "code"


def requirement_text(kind: str) -> str:
    """输出形态条款：按 kind 出；未知 kind 回落到历史（code/repair）文本。"""
    return REQUIREMENT_BY_KIND.get(str(kind), REQUIREMENT_CODE)

#: 渲染用的白名单字段（单一来源：判分器）；未登记字段一律不渲染。
PUBLIC_FIELDS: Tuple[str, ...] = tuple(
    getattr(admission, "DIAGNOSTIC_PUBLIC_FIELDS",
            ("code", "contract_path", "source_location", "actual_type_or_status",
             "expected_predicate", "public_example", "explanation")))
PRIVATE_FIELDS: Tuple[str, ...] = tuple(
    getattr(admission, "DIAGNOSTIC_PRIVATE_FIELDS", ("raw_problem", "problems")))
DIAGNOSTIC_SCHEMA = getattr(admission, "DIAGNOSTIC_SCHEMA", "sitin-admission-diagnostic/1")

#: 词表字段（评审 C4：脱敏必须覆盖**所有**相关字段）。
#: 显式词表（含 mechanism_keyword_groups 与 forbidden_tokens）按**全长度**逐条子串检查；
#: 正则字段（required_regex / forbidden_regex / code_forbidden_regex）不做字面片段抽取
#: —— 正则是**形态匹配**不是词表条目，抽片段会把「可以」「直接」这类通用词当成泄漏
#: （实测会把正常诊断文本整段打掉）。正则字段改为按**其自身**对新增文本做一次匹配：
#: 新增文本若本身构成一条被禁止的主张形态，则拒绝产出（更精确、可复现）。
_VOCAB_LIST_FIELDS = ("required_groups", "forbidden", "mechanism_keyword_groups",
                      "forbidden_tokens")
_VOCAB_REGEX_FIELDS = ("required_regex", "forbidden_regex", "code_forbidden_regex")
_REDACTION = "［词表项已脱敏］"


def vocabulary_tokens(task: Dict[str, Any]) -> List[str]:
    """该题的**全部显式词表条目**（含机制词组与短词；不做长度过滤）。"""
    validation = task.get("validation") or {}
    tokens: List[str] = []
    for field in _VOCAB_LIST_FIELDS:
        value = validation.get(field) or []
        for item in value:
            # required_groups / mechanism_keyword_groups 是「组 → 条目」的两层结构，
            # 其余字段是一层；一律摊平到条目，**保留 1 字词**（评审 C4）。
            if isinstance(item, (list, tuple)):
                tokens.extend(str(alt) for alt in item)
            else:
                tokens.append(str(item))
    return sorted({token for token in tokens if token.strip()})


def regex_leak_check(task: Dict[str, Any], added_text: str) -> List[str]:
    """正则字段的脱敏断言：新增文本本身不得命中题目的禁式正则。"""
    validation = task.get("validation") or {}
    hits: List[str] = []
    for field in _VOCAB_REGEX_FIELDS:
        for pattern in validation.get(field) or []:
            try:
                if re.search(str(pattern), added_text):
                    hits.append("{0}: {1}".format(field, pattern))
            except re.error as exc:                            # noqa: PERF203
                hits.append("{0}: 正则自身出错 {1}".format(field, exc))
    return hits


def leak_check(task: Dict[str, Any], added_text: str) -> List[str]:
    """脱敏断言：新增文本不得含任何词表条目（全字段覆盖；短词也查），
    且不得命中题目自己的禁式正则。"""
    tokens = [token for token in vocabulary_tokens(task) if token in added_text]
    return sorted(set(tokens) | set(regex_leak_check(task, added_text)))


def redact(text: str, tokens: Sequence[str]) -> Tuple[str, List[str]]:
    """把命中的词表条目整段替换为占位符；返回 (脱敏后文本, 命中条目)。"""
    hits: List[str] = []
    for token in sorted(tokens, key=len, reverse=True):
        if token and token in text:
            hits.append(token)
            text = text.replace(token, _REDACTION)
    return text, sorted(set(hits))


def _source_location_text(location: Any) -> str:
    """源码位置的公开渲染（无法定位时**明确缺失**，不省略字段）。"""
    if not isinstance(location, dict):
        return "MISSING（诊断未提供位置）"
    status = str(location.get("status") or "MISSING")
    line = location.get("line")
    excerpt = location.get("excerpt")
    reason = str(location.get("reason") or "")
    if status != "MISSING" and line:
        head = "{0} {1}:{2}".format(status, location.get("file") or "candidate.py", line)
        if location.get("symbol"):
            head += "（符号 {0}）".format(location["symbol"])
        if excerpt:
            head += " ｜ {0}".format(excerpt)
        return head
    return "MISSING（无法定位到具体源码行：{0}）".format(reason or "未说明")


def render_diagnostics(task: Dict[str, Any],
                       diagnostics: Sequence[Dict[str, Any]]
                       ) -> Tuple[List[str], Dict[str, Any]]:
    """结构化诊断 → 公开字段白名单文本（评审 C2/C4）。

    返回 (渲染行, 统计)。统计含：渲染条数、错误码、丢弃的私有字段、跳过的包级诊断、
    脱敏命中。渲染器**不接触** problems 原文，也不做任何文本归约。
    """
    stats: Dict[str, Any] = {"entries": 0, "codes": [], "dropped_private_fields": [],
                             "package_skipped": 0, "redactions": [],
                             "source": "structured"}
    lines: List[str] = []
    tokens = vocabulary_tokens(task)
    usable = 0
    for entry in diagnostics or ():
        if not isinstance(entry, dict):
            continue
        if str(entry.get("attribution")) == "package":
            # 包级缺陷（材料不兼容等）不是模型的错：不进修复提示词，只进报告。
            stats["package_skipped"] += 1
            continue
        dropped = sorted(key for key in entry if key not in PUBLIC_FIELDS)
        stats["dropped_private_fields"].extend(dropped)
        code = str(entry.get("code") or "UNCLASSIFIED_PROBLEM")
        count = int(entry.get("count") or 1)
        code_text, _code_hits = redact(code, tokens)
        if code_text != code:
            # 编号与本题词表条目重名时同样脱敏，但保留一个**稳定别名**，便于报告与
            # 提示词交叉引用（别名由编号派生，不含词表内容）。
            alias = "ADM-" + hashlib.sha256(code.encode("utf-8")).hexdigest()[:8]
            code_text += "（条目标识 {0}）".format(alias)
        block = ["- 编号：{0}（{1} 处）".format(code_text, count)]
        block.append("  判据出处：{0}".format(entry.get("contract_path") or "（未提供）"))
        block.append("  位置：{0}".format(_source_location_text(
            entry.get("source_location"))))
        block.append("  实际结果：{0}".format(
            entry.get("actual_type_or_status") or "（未提供）"))
        block.append("  应当满足：{0}".format(entry.get("expected_predicate") or "（未提供）"))
        block.append("  合规范例：{0}".format(entry.get("public_example") or "（未提供）"))
        block.append("  说明：{0}".format(entry.get("explanation") or "（未提供）"))
        instances = [str(item) for item in (entry.get("instances") or [])][:12]
        if instances:
            block.append("  覆盖到的位置：" + "；".join(instances))
        text = "\n".join(block)
        text, hits = redact(text, tokens)
        if hits:
            stats["redactions"].extend(hits)
        # 脱敏后若关键字段被清空，明确标注（不静默留白）。
        for label in ("应当满足：", "合规范例：", "实际结果："):
            if label + _REDACTION in text:
                text = text.replace(label + _REDACTION,
                                    label + "（内容与本题词表冲突，已整段脱敏）")
        lines.extend(text.splitlines())
        stats["entries"] += 1
        stats["codes"].append(code)
        usable += 1
    stats["diagnostics_available"] = usable > 0
    if usable == 0:
        # 兜底（「无结构化诊断可用」是**测量侧情形**，不是异常）：不复制原文（评审 C4），
        # 也不抛异常（评审复核要求：上游要能区分「给了诊断」与「没给诊断」）。文案一律
        # 中性、并**过同一套脱敏**（实测：旧文案在 T22/T23 上会因「冻结」「不得」「合同」
        # 等词表条目直接抛 SystemExit，把测量侧情形误报成构造失败）。
        lines = ["- 编号：DIAGNOSTICS_UNAVAILABLE（本次未提供具名条目）",
                 "  判据出处：见本题【回答格式】与公开判据文件（contracts/action-value-v1.json）",
                 "  位置：MISSING（本次没有可定位的行）",
                 "  实际结果：判分产物未携带具名条目（原文不回灌）",
                 "  应当满足：按题面公开判据自查；复述原文不构成定位",
                 "  合规范例：无",
                 "  说明：本次未提供具名条目；请按题面公开判据自查，"
                 "或用同一判分器版本重判后再取本提示词。"]
        lines = [redact(line, tokens)[0] for line in lines]
        stats["codes"] = ["DIAGNOSTICS_UNAVAILABLE"]
        stats["source"] = "unavailable"
    stats["dropped_private_fields"] = sorted(set(stats["dropped_private_fields"]))
    stats["redactions"] = sorted(set(stats["redactions"]))
    return lines, stats


def build_repair_prompt(task: Dict[str, Any], original_prompt: str, first_reply: str,
                        diagnostics: Sequence[Dict[str, Any]],
                        kind: Any = None) -> Dict[str, Any]:
    """构造修复提示词：密封提示词 + 上一轮交付 + 具名条目 + 按 kind 的输出形态条款。

    脱敏是**构造性保证**，不是事后断言：每个条目在渲染时脱敏，整块新增文本（含标签与
    要求句）再过一遍同一套脱敏，然后才做零泄漏断言。因此
    「无结构化诊断可用」这类**测量侧情形不抛异常** —— 返回体里用
    `diagnostics_available` 具名标注，上游（出口/封套）据此区分「给了诊断」与「没给」。

    输出形态（第七轮）：条款按判分器 kind 出（`kind` 显式给出时优先，否则读任务
    JSON 的 `validation.kind`）：keyword ⇒ 中文短答正文（**不得**要求代码围栏）；
    code / repair ⇒ 逐字沿用历史条款。密封提示词**逐字**放在最前面（首行即密封条款）。
    """
    resolved_kind = grader_kind(task, kind)
    requirement = requirement_text(resolved_kind)
    lines, stats = render_diagnostics(task, diagnostics)
    stats["grader_kind"] = resolved_kind
    stats["output_form"] = {
        "kind": resolved_kind,
        "clause_sha256": hashlib.sha256(requirement.encode("utf-8")).hexdigest(),
        "clause_chars": len(requirement),
        "asks_code_fence": "代码围栏" in requirement,
    }
    added = "\n".join([PROBLEM_HEADER, *lines, "", requirement])
    tokens = vocabulary_tokens(task)
    for _ in range(3):
        leaks = leak_check(task, added)
        if not leaks:
            break
        added, extra = redact(added, leaks)
        stats["redactions"].extend(extra)
    leaks = leak_check(task, added)
    text = "\n".join([original_prompt, "", REPAIR_HEADER, first_reply.rstrip(), "", added])
    return {"text": text, "added": added, "stats": stats, "leaks": leaks,
            "grader_kind": resolved_kind,
            "requirement_chars": len(requirement),
            "requirement_sha256": stats["output_form"]["clause_sha256"],
            "asks_code_fence": stats["output_form"]["asks_code_fence"],
            "sealed_prompt_first_line": original_prompt.splitlines()[0] if original_prompt
            else "",
            "diagnostics_available": bool(stats.get("diagnostics_available")),
            "diagnostic_source": str(stats.get("source") or "structured")}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--package", default=str(_project_file(_PROJECT_ROOT, ADMISSION / "package")))
    parser.add_argument("--replies", required=True, help="首答目录（Txx.txt）")
    parser.add_argument("--report", required=True,
                        help="该轮判分报告 JSON（消费 tasks[].diagnostics 结构化诊断）")
    parser.add_argument("--tasks", default=None, help="逗号分隔；缺省=报告里所有未通过的题")
    parser.add_argument("--out", required=True, help="修复提示词输出目录")
    parser.add_argument("--manifest-out", default=None)
    args = parser.parse_args()
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    report = json.loads(Path(args.report).read_text(encoding="utf-8"))
    package = Path(args.package)
    only = set(args.tasks.split(",")) if args.tasks else None
    rows = []
    for row in report.get("tasks") or ():
        task_id = row.get("task_id")
        if row.get("pass"):
            continue
        if only and task_id not in only:
            continue
        task = json.loads((package / "tasks" / (task_id + ".json")).read_text(encoding="utf-8"))
        original = sd.sealed_prompt(task_id, package)
        reply = (Path(args.replies) / (task_id + ".txt")).read_text(encoding="utf-8")
        # 只消费结构化诊断：老报告（没有 diagnostics）走具名兜底，**不复制 problems 原文**。
        built = build_repair_prompt(task, original, reply, row.get("diagnostics") or [])
        target = out_dir / task_id
        target.mkdir(parents=True, exist_ok=True)
        (target / "prompt.txt").write_text(built["text"], encoding="utf-8")
        rows.append({"task_id": task_id, "chars": len(built["text"]),
                     "added_chars": len(built["added"]),
                     "grader_kind": built["grader_kind"],
                     "output_form": built["stats"]["output_form"],
                     "diagnostic_schema": DIAGNOSTIC_SCHEMA,
                     # 上游（出口/封套）据此区分「给了诊断」与「没给诊断」——
                     # 「无具名条目可用」是测量侧情形，不是构造失败。
                     "diagnostics_available": built["diagnostics_available"],
                     "diagnostic_source": built["diagnostic_source"],
                     "diagnostic_stats": built["stats"],
                     "leak_tokens": built["leaks"]})
    manifest = {"schema": "sitin-headless-repair-prompts/2",
                "diagnostic_schema": DIAGNOSTIC_SCHEMA,
                "generated_from": "判分报告的具名条目（公开字段白名单渲染；不复述原文）",
                "diagnostics_available_tasks": sorted(
                    r["task_id"] for r in rows if r["diagnostics_available"]),
                "diagnostics_unavailable_tasks": sorted(
                    r["task_id"] for r in rows if not r["diagnostics_available"]),
                "source_report": str(args.report), "replies": str(args.replies),
                "out": str(out_dir), "tasks": rows}
    (out_dir.parent / (Path(args.manifest_out).name if args.manifest_out
                       else "repair-prompts.json")).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({"tasks": len(rows), "leaks": sum(len(r["leak_tokens"]) for r in rows),
                      "redactions": sum(len(r["diagnostic_stats"]["redactions"])
                                        for r in rows),
                      "diagnostics_unavailable": manifest[
                          "diagnostics_unavailable_tasks"],
                      "out": str(out_dir)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
