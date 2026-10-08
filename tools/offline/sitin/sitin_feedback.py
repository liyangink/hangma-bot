# -*- coding: utf-8 -*-
"""R6 三段开发反馈自动生成（事实 / 关联结果 / 机制假设）。

依据：CONTINUOUS-EVOLUTION-PLAN-2026-09-17.md §7 步 6（"程序生成根级结果；
模型最多提出有证据引用的机制解释"）与 §11 交付物 4—6；人写参照样例见
evidence/v4-impl/r6-e-revalidation/feedback-i1-r6.md。

三段的分工（这是本工具唯一的边界，不能互换）：

1. **事实段**（程序）：候选 cid、面板身份、双臂终局、逐窗口差异。数字逐项读自
   产物（`evaluation.json` / `natural-*/panel.json` / `samples.jsonl`），不推算、
   不补零、不编造；产物缺字段就显式写"产物未给该字段"。
2. **关联结果段**（程序）：根级配对差、识别区间（`delta_bounds`）、抽样区间
   （`interval_95`）、未分辨根数与无效/不可计算计数、声明混合值（权重读自产物的
   `declared_mix.weights`）。程序只报数字与产物自带的口径说明，**不判定优胜、
   不发布、不把"未分辨"说成失败或改进**。
3. **机制假设段**（模型）：程序只产出**槽位**——候选 trace 的实测字段名（从候选
   源码的 trace 字典字面量里扫出来；扫不到就退回 prompt 合同要求的类别），加上
   "相对父代方向 / 引用窗口 / 反例面" 的占位符。内容由监督者或候选作者填写，
   并标注"模型解释，须引用具体字段"。

**投影与可执行性判定（R7/P9 修复）**：三段正文由 `build_feedback_projection`
统一产出，并给出 `status`（ok/refused）与 `executable`。任何一条拒绝条件命中时，
反馈**仍如实写出**（缺什么写什么），但下游（M1 任务包）**不得**据此生成可执行修订
任务——这正是 R6 试跑的缺陷：`branch_open: mean_delta=None, n_roots=None,
status=None` 与「覆盖层：None」被渲染进 M1 提示词，模型引用错误事实作改动依据。
拒绝条件（fail-closed，不猜、不回退）：

- `identity.evaluation_binding`：条件评估产物的候选身份与本次候选不符；
- `identity.panel_binding`：自然面板存在但身份绑不上本次候选——**不退回「所有面板」**；
- `identity.source_binding`：产物登记了候选源码摘要却没有匹配的源码文件——**不退回
  「第一份源码」**；身份不可核验时同样拒绝；
- `reading.statistics_missing` / `reading.numbers_missing` / `reading.arms_missing`：
  本批该面板块缺失，或本应报出的数字是 null（**不得把 null 当事实**）；
- `boundary.confirmation_data` / `boundary.root_usage_unknown` /
  `boundary.root_usage_manifest`：**根用途边界**。R9/P5（复审 R8 §6 F1）把这一条从
  「只扫统计块」改成「**在任何渲染/汇总之前扫描完整实际读取文档**」：条件评估产物、
  自然面板 `panel.json` 的**整份文档**（含正在被渲染的 `samples`，以及
  `config/identity/cost`）、独立 `samples.jsonl` 的**逐行**、机会面板、
  `summary/statistics.json` 与选留说明。`usage` 与 `root_usage` 同义，
  `confirmation_eligible` 是与 `usage == confirmation` 等价的布尔形态；三者冲突、
  取词表外的用途词、或与冻结根用途清单
  （`sitin-root-usage-manifest/1`）不一致，一律拒绝。**拒绝时三段正文与机制槽位
  一律不渲染**：拒绝产物只暴露诊断定位（哪份文档、哪个字段、哪条 JSON 路径），
  不把确认结果复制进反馈或任务包。

每个条目（item）都带 `evidence`：产物路径 + JSON 定位 + **原值**，事实/结果因此可
逐项追到来源根与窗口；程序不推算、不补零、不编造。

预算与副作用红线：本工具纯读文件、纯字符串处理；不跑桌赛、不调模型、不读时钟
（输出对同输入逐字节确定，便于测试与审计）、不写除 `out_path` 以外的文件。
"""

from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/llm-guided-heuristic-route-2026-09-15/tools'

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
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

#: 本文档的 schema 名（写进 Markdown 抬头，供下游核对来源）。
FEEDBACK_SCHEMA = "sitin-three-segment-feedback-md/1"

#: 程序化投影 schema：主状态机 summary 与 CLI 共用同一份（R7/P9）。
PROJECTION_SCHEMA = "sitin-feedback-projection/1"

#: 投影状态：ok = 可作为可执行修订任务的事实底座；refused = 只看不改（见模块 docstring）。
PROJECTION_OK = "ok"
PROJECTION_REFUSED = "refused"

#: 拒绝码（前缀即类别，便于下游聚合与测试）。
REFUSAL_IDENTITY_EVALUATION = "identity.evaluation_binding"
REFUSAL_IDENTITY_PANELS = "identity.panel_binding"
REFUSAL_IDENTITY_SOURCE = "identity.source_binding"
REFUSAL_IDENTITY_STATISTICS = "identity.statistics_candidate_ambiguous"
REFUSAL_READING_STATISTICS_MISSING = "reading.statistics_missing"
REFUSAL_READING_NUMBERS_MISSING = "reading.numbers_missing"
REFUSAL_READING_ARMS_MISSING = "reading.arms_missing"
REFUSAL_BOUNDARY_CONFIRMATION = "boundary.confirmation_data"
#: 词表外/自相冲突的根用途：用途未冻结或声明互相矛盾，一律不进开发反馈。
REFUSAL_BOUNDARY_USAGE_UNKNOWN = "boundary.root_usage_unknown"
#: 冻结根用途清单缺失/不可解析，或产物与清单不符（含清单里的确认根出现在产物中）。
REFUSAL_BOUNDARY_USAGE_MANIFEST = "boundary.root_usage_manifest"

#: 根用途分区里的确认集标签（Q2/T13）：出现即拒绝（确认材料不进开发反馈）。
CONFIRMATION_USAGE = "confirmation"

#: 根用途三分区词表（与 `sitin_archive.ROOT_USAGES` 同一冻结词汇表；测试锁死一致）。
ROOT_USAGE_DEVELOPMENT_CORE = "development_core"
ROOT_USAGE_DEVELOPMENT_REFRESH = "development_refresh"
ROOT_USAGES: Tuple[str, ...] = (ROOT_USAGE_DEVELOPMENT_CORE,
                                ROOT_USAGE_DEVELOPMENT_REFRESH, CONFIRMATION_USAGE)

#: 声明根用途的字段名：`usage` 与 `root_usage` 同义（R8 §6 F1 要求统一语义）。
USAGE_FIELDS: Tuple[str, ...] = ("usage", "root_usage")

#: 布尔形态的"确认可用"标记（与 `usage == confirmation` 等价，取并集判定）。
CONFIRMATION_FLAG_FIELD = "confirmation_eligible"

#: 根身份字段：冻结用途清单按根名核对时用。
ROOT_ID_FIELDS: Tuple[str, ...] = ("root_id", "source_root_id")

#: 冻结根用途清单 schema（与 `sitin_archive.ROOT_USAGE_SCHEMA` 同值；测试锁死一致）。
ROOT_USAGE_MANIFEST_SCHEMA = "sitin-root-usage-manifest/1"

#: 用途扫描的节点上限：超过即判"扫描不完整"，仍按边界拒绝（fail-closed，不静默放行）。
USAGE_SCAN_NODE_LIMIT = 1000000

#: 拒绝诊断里确认根名的替身（诊断只暴露定位，不复制确认结果）。
REDACTED_ROOT = "<confirmation-root>"

#: 段名（与旧 JSON 键逐字一致，供 sitin_generate 渲染复用）。
SEGMENT_FACTS = "facts"
SEGMENT_RESULTS = "associated_results"
SEGMENT_MECHANISM = "mechanism_hypothesis"

HEADING_FACTS = "## 一、事实（程序实测；数字逐项读自产物）"
HEADING_RESULTS = "## 二、关联结果（根级差 / 区间 / 未分辨计数；数字逐项读自产物）"
HEADING_MECHANISM = "## 三、机制假设（模型解释，须引用具体字段）"

#: 第三段槽位的口径说明（模型必须看到这句，避免把槽位当结论）。
MECHANISM_RULE = (
    "**本段是模型解释，须引用具体字段**：每条结论必须写出候选 trace 的字段名、"
    "该字段的实际读数、所在窗口的 `source_root_id`，并说明与父代的方向关系；"
    "给不出字段引用的句子不要写。程序不代填本段，也不把任何槽位当作事实。"
)

#: 第三段的边界声明（复审 §4 A5）：源码里存在的字段名**不是**已采集的实际读数。
FIELD_NOT_READING_NOTE = (
    "**槽位名 ≠ 读数**：下面列出的 trace 字段名是程序从**候选源码的 trace 字面量**里"
    "扫出的**槽位名**，用来指出「该在哪里引用证据」；程序**没有**这些字段的任何实际"
    "读数（本批产物未采集 trace 读数，readings_collected=false），因此这些名字"
    "**不是已采集的读数**，不得当作事实引用，也不得据此填任何数值。"
)

#: 找不到候选源码时的槽位回退：prompt 合同要求 trace 覆盖的类别（不是实测字段名）。
TRACE_SLOT_FALLBACK: Tuple[str, ...] = (
    "分支选择（所选分支键）",
    "所用事实键（fact_source 等）",
    "代理与分项（parts 下各分项）",
    "组合方式（非线性组合与权重）",
    "降级原因（unanalyzed_floor / ABSTAIN reason）",
)

#: 候选源码里 trace 字典字面量的定位模式（按出现顺序扫描，跨模式取并集）。
_TRACE_REGION_PATTERNS = (
    r"traces?\.append\(\s*\{",
    r"[\"']trace[\"']\s*:\s*\{",
    r"\btrace\s*=\s*\{",
)


class FeedbackInputError(ValueError):
    """评估产物缺失或结构不可解读：fail-closed，不产出半份反馈。"""


# ---------------------------------------------------------------------------
# 1. 纯读文件与数值渲染
# ---------------------------------------------------------------------------


def _load_json(path: Path) -> Any:
    """读 JSON；不可解析即报错（不静默当空产物）。"""

    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise FeedbackInputError("产物不存在：{0}".format(path)) from exc
    except json.JSONDecodeError as exc:
        raise FeedbackInputError("产物不可解析：{0}（{1}）".format(path, exc)) from exc


def _num(value: Any) -> str:
    """渲染产物里的数值；缺失/非数值一律显式标注，绝不用 0 顶替。"""

    if value is None:
        return "（产物未给该字段）"
    if isinstance(value, bool):
        return "（产物给的是布尔值 {0}，非数值）".format(value)
    if isinstance(value, (int, float)):
        return repr(value)
    return "（产物字段非数值：{0}）".format(
        json.dumps(value, ensure_ascii=False, default=str))


def _flag(value: Any) -> str:
    """渲染布尔标记；缺失即标注缺失。"""

    if isinstance(value, bool):
        return "true" if value else "false"
    return "（产物未给该字段）"


def _short(cid: Optional[str]) -> str:
    """身份短写：12 位前缀，便于人读；空值显式标注。"""

    text = str(cid or "").strip()
    return text[:12] if text else "（未提供）"


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _sequence(value: Any) -> Sequence[Any]:
    return value if isinstance(value, (list, tuple)) else ()


def _is_number(value: Any) -> bool:
    """数值判据（布尔不算数值——True/False 不是读数）。"""

    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _pointer(parts: Sequence[Any]) -> str:
    """拼 JSON 指针（`/a/b/0`）；下游按它在产物里取值对账。"""

    return "".join("/{0}".format(part) for part in parts)


def _evidence(path: Any, locator: str, value: Any) -> Dict[str, Any]:
    """证据：产物路径 + JSON 定位 + 原值（三件齐全才算可追）。"""

    return {"artifact": str(path), "locator": locator, "value": value}


def _pointer_value(document: Any, parts: Sequence[Any]) -> Tuple[bool, Any]:
    """按 JSON 指针取值；路径不存在返回 (False, None)——**不造假证据**。"""

    node = document
    for part in parts:
        if isinstance(node, Mapping) and part in node:
            node = node[part]
        elif isinstance(node, list):
            index = part if isinstance(part, int) else (
                int(part) if isinstance(part, str) and part.lstrip("-").isdigit()
                else None)
            if index is None or not (0 <= index < len(node)):
                return False, None
            node = node[index]
        else:
            return False, None
    return True, node


def _ev(path: Any, document: Any, *parts: Any) -> Optional[Dict[str, Any]]:
    """能对上的证据（产物路径 + 定位 + 原值）；路径不存在返回 None。"""

    ok, value = _pointer_value(document, parts)
    return _evidence(path, _pointer(parts), value) if ok else None


def _evs(path: Any, document: Any,
         *part_lists: Sequence[Any]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for parts in part_lists:
        item = _ev(path, document, *parts)
        if item is not None:
            out.append(item)
    return out


def _item(key: str, segment: str, text: str,
          evidences: Sequence[Mapping[str, Any]], *,
          root_id: Optional[str] = None,
          window: Optional[Mapping[str, Any]] = None,
          fallback: Optional[Tuple[Any, Any]] = None) -> Dict[str, Any]:
    """一条可对账的反馈条目：至少一条证据（产物 + 定位 + 原值）。

    `fallback=(路径, 整份产物)`：具体数字的证据都取不到时，退到**产物根**作证据
    （条目文本此时说的是"产物未给该字段"），仍然有出处、不编造。
    """

    if not evidences:
        if fallback is None:
            raise FeedbackInputError(
                "条目 {0} 没有任何证据：不允许无出处的反馈".format(key))
        path, document = fallback
        if path is None:
            raise FeedbackInputError(
                "条目 {0} 没有任何证据（也没有产物可退）".format(key))
        evidences = [_evidence(path, "", document)]
    return {
        "key": key,
        "segment": segment,
        "text": text,
        "root_id": root_id,
        "window": dict(window) if window else None,
        "evidence": dict(evidences[0]),
        "extra_evidences": [dict(item) for item in evidences[1:]],
    }


def _refusal(code: str, detail: str) -> Dict[str, str]:
    return {"code": code, "detail": detail}


def _gap(code: str, detail: str) -> Dict[str, str]:
    return {"code": code, "detail": detail}


# ---------------------------------------------------------------------------
# 2. 产物发现（条件评估 / 自然面板）
# ---------------------------------------------------------------------------


def _is_evaluation(data: Any) -> bool:
    return isinstance(data, Mapping) and "identity" in data and (
        "double_arm" in data or "statistics" in data or "samples" in data)


def _is_natural_panel(data: Any) -> bool:
    if not isinstance(data, Mapping):
        return False
    generator = str(data.get("generator") or "")
    epoch = str(_mapping(data.get("identity")).get("panel_epoch") or "")
    if generator.startswith("natural") or epoch.startswith("natural"):
        return True
    return isinstance(data.get("samples"), list) and isinstance(
        data.get("statistics"), Mapping) and not _is_evaluation(data)


def _discover_evaluation(eval_dir: Path,
                         candidate_cid: Optional[str]) -> Optional[Path]:
    """定位条件评估产物：优先 <eval_dir>/evaluation.json，其次按身份匹配。"""

    direct = eval_dir / "evaluation.json"
    if direct.is_file():
        return direct
    found: List[Tuple[int, str, Path]] = []
    for path in sorted(eval_dir.rglob("evaluation.json")):
        data = _load_json(path)
        if not _is_evaluation(data):
            continue
        cid = str(_mapping(data.get("identity")).get("candidate_id") or "")
        # 0 = 身份命中（最强）；1 = 路径像条件面板；2 = 其余（保持确定性排序）。
        rank = 0 if (candidate_cid and cid == candidate_cid) else (
            1 if "conditional" in str(path) else 2)
        found.append((rank, str(path), path))
    if not found:
        return None
    found.sort(key=lambda item: (item[0], item[1]))
    return found[0][2]


def _samples_from_jsonl(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if text:
            rows.append(json.loads(text))
    return rows


def _candidate_digests(evaluation: Optional[Mapping[str, Any]]) -> List[str]:
    """条件评估产物里登记的候选源码摘要（用于把自然面板对到同一候选）。"""

    digests: List[str] = []
    admission = _mapping(_mapping(evaluation).get("admission"))
    for block in (admission.get("identity"), _mapping(evaluation).get("identity"),
                  _mapping(admission.get("layers")).get("identity")):
        digest = str(_mapping(block).get("candidate_source_sha256") or "")
        if digest and digest not in digests:
            digests.append(digest)
    return digests


def _panel_digest_conflict(panel: Mapping[str, Any],
                           digests: Sequence[str]) -> bool:
    """面板登记的候选源码摘要与产物登记的摘要是否冲突（登记了且不在其中即冲突）。"""

    recorded = str(_mapping(panel.get("identity")).get("candidate_source_sha256") or "")
    return bool(digests) and bool(recorded) and recorded not in digests


def _select_panels(panels: Sequence[Mapping[str, Any]],
                   evaluation: Optional[Mapping[str, Any]],
                   candidate_cid: Optional[str]
                   ) -> Tuple[List[Mapping[str, Any]], str, Optional[Dict[str, str]]]:
    """把自然面板挑到本次候选上；**绑不上就拒绝绑定**（不退回「所有面板」）。

    绑定顺序（只接受正面命中）：① 候选源码摘要（产物登记，最精确）；
    ② 面板自报 candidate_id（或兼容布局里样本自报的 candidate_id）。
    两者都不命中即返回空集 + 拒绝码——R6 的旧行为是"绑不上就保留全部面板"，
    等于把别的候选（甚至确认根）的数字混进本次反馈，属复审 §4 A5 明确要修的点。
    """

    digests = _candidate_digests(evaluation)
    if digests:
        matched = [panel for panel in panels
                   if str(_mapping(panel.get("identity")).get(
                       "candidate_source_sha256") or "") in digests]
        if matched:
            return matched, "按产物 candidate_source_sha256={0} 绑定".format(
                digests[0][:16]), None
    if candidate_cid:
        matched = [panel for panel in panels
                   if str(_mapping(panel.get("identity")).get("candidate_id") or "")
                   == str(candidate_cid)
                   or str(panel.get("reported_candidate_id") or "") == str(candidate_cid)]
        conflicting = [panel for panel in matched
                       if _panel_digest_conflict(panel, digests)]
        if conflicting:
            # 复审 R8 §6 F2"冲突源码摘要均被拒"：按 candidate_id 命中、但面板登记的
            # 候选源码摘要与条件评估产物登记的**不是同一份源码**——身份对不上，
            # 不退回摘要绑定、也不采用它的任何数字。
            return [], ("**自然面板与条件评估产物的候选源码摘要冲突**（{0} 份面板自报 "
                        "candidate_id 命中，但 candidate_source_sha256 与产物登记的 "
                        "{1} 不一致）：拒绝绑定").format(
                            len(conflicting),
                            _short(digests[0]) if digests else "（产物未登记）"), _refusal(
                REFUSAL_IDENTITY_SOURCE,
                "自然面板登记的候选源码摘要与产物不一致（面板 {0} 份冲突）："
                "拒绝绑定，面板数字不进反馈".format(len(conflicting)))
        if matched:
            return matched, "按面板自报 candidate_id 绑定", None
    if not panels:
        return [], "无自然面板产物", None
    return [], ("**未能把自然面板绑定到本次候选**（产物登记的候选源码摘要与面板 "
                "identity 不符，candidate_id 也不匹配）：按 A5 拒绝绑定——不退回"
                "「所有面板」，未绑定面板的数字一律不进入反馈"), _refusal(
        REFUSAL_IDENTITY_PANELS,
        "自然面板 {0} 份绑不上本次候选（candidate_id={1}，产物摘要={2}）："
        "拒绝绑定，未绑定面板数字不进反馈".format(
            len(panels), _short(candidate_cid),
            _short(digests[0]) if digests else "（产物未登记）"))


def _discover_natural_panels(eval_dir: Path) -> List[Dict[str, Any]]:
    """收集自然面板产物（panel.json 优先；兼容 samples.jsonl 分离布局）。

    返回 [{path, mix, identity, config, cost, samples, statistics, statistics_path}]，
    按 mix 排序，保证输出确定。
    """

    panels: List[Dict[str, Any]] = []
    for path in sorted(eval_dir.rglob("panel.json")):
        data = _load_json(path)
        if not _is_natural_panel(data):
            continue
        identity = _mapping(data.get("identity"))
        mix = str(identity.get("opponent_mix") or "")
        if not mix:
            mix = path.parent.name.rsplit("-", 1)[-1]
        panels.append({
            "path": path,
            "mix": mix,
            "identity": identity,
            "reported_candidate_id": identity.get("candidate_id"),
            "config": _mapping(data.get("config")),
            "cost": _mapping(data.get("cost")),
            "samples": [row for row in _sequence(data.get("samples"))
                        if isinstance(row, Mapping)],
            "statistics": _mapping(data.get("statistics")),
            "statistics_path": path,
            # R9/P5 F1：用途扫描要扫**整份实际读过的文档**——含正在渲染的 samples
            # 与 config/identity/cost，而不是只扫 statistics。
            "document": data,
            "document_paths": [path],
            "scan_documents": [{"artifact": path, "document": data, "prefix": ""}],
        })
    if panels:
        panels.sort(key=lambda item: (item["mix"], str(item["path"])))
        return panels
    # 兼容布局：无 panel.json，但有 samples.jsonl（+ 可选 statistics JSON）。
    for samples_path in sorted(eval_dir.rglob("samples.jsonl")):
        rows = _samples_from_jsonl(samples_path)
        container = samples_path.parent
        stats_path = None
        for name in ("natural-statistics.json", "statistics.json"):
            if (container / name).is_file():
                stats_path = container / name
                break
        mix = ""
        for row in rows:
            mix = str(_mapping(row).get("opponent_mix") or "")
            if mix:
                break
        if not mix:
            mix = container.name.rsplit("-", 1)[-1]
        statistics = _load_json(stats_path) if stats_path else {}
        scan_documents = [
            {"artifact": samples_path, "document": row,
             "prefix": "/line/{0}".format(index)}
            for index, row in enumerate(rows)]
        if stats_path is not None:
            scan_documents.append({"artifact": stats_path, "document": statistics,
                                   "prefix": ""})
        panels.append({
            "path": samples_path,
            "mix": mix,
            "identity": {},
            "reported_candidate_id": next(
                (str(_mapping(row).get("candidate_id")) for row in rows
                 if _mapping(row).get("candidate_id")), None),
            "config": {},
            "cost": {},
            "samples": rows,
            "statistics": statistics,
            "statistics_path": stats_path or samples_path,
            # 独立 JSONL 布局：逐行扫描（原始样本），外加统计 JSON。
            "document": statistics,
            "document_paths": [p for p in (samples_path, stats_path) if p is not None],
            "scan_documents": scan_documents,
        })
    panels.sort(key=lambda item: (item["mix"], str(item["path"])))
    return panels


def _is_opportunity_panel(data: Any) -> bool:
    """条件机会面板产物（`sitin-opportunity-panel/1`）：逐场景带 snapshot。"""

    return (isinstance(data, Mapping)
            and str(data.get("schema") or "").startswith("sitin-opportunity-panel")
            and isinstance(data.get("scenarios"), list))


def _discover_opportunity_panels(eval_dir: Path) -> List[Dict[str, Any]]:
    """收集条件机会面板产物（证据路径 + 已解析数据），按路径排序保证确定性。"""

    panels: List[Dict[str, Any]] = []
    for path in sorted(eval_dir.rglob("panel.json")):
        data = _load_json(path)
        if _is_opportunity_panel(data):
            panels.append({"path": path, "data": data})
    return panels


def _select_opportunity_panels(eval_path: Optional[Path],
                               discovered: Sequence[Mapping[str, Any]]
                               ) -> Tuple[List[Mapping[str, Any]], Optional[str]]:
    """把机会面板绑到**本次条件评估**上：只取与 evaluation.json 同目录的面板。

    目录里同时存在多代产物（例如 i1-conditional / m1-conditional）时，rglob 会把
    别人的窗口、掩码混进本次反馈——这属"身份不匹配"，宁可少报也不混用。返回
    （绑定到的面板, 未绑定说明）。
    """

    if not discovered:
        return [], None
    if eval_path is None:
        return [], ("目录里有 {0} 份机会面板但**没有条件评估产物**可绑定："
                    "窗口与掩码不进入反馈（不混用别人的窗口）".format(len(discovered)))
    parent = Path(eval_path).parent
    matched = [entry for entry in discovered
               if Path(entry["path"]).parent.parent == parent]
    if matched:
        return matched, None
    return [], ("目录里有 {0} 份机会面板，但没有一份与条件评估产物 {1} 同目录："
                "窗口与掩码不进入反馈（不混用别的候选/代际的窗口）".format(
                    len(discovered), Path(eval_path).name))


def _load_selection_notes(eval_dir: Path) -> Tuple[Optional[Path], Mapping[str, Any]]:
    """读 summary/selection-notes.json（选留排除/去重计数；主状态机写入）。"""

    path = eval_dir / "summary" / "selection-notes.json"
    if not path.is_file():
        return None, {}
    return path, _mapping(_load_json(path))


# ---------------------------------------------------------------------------
# 3. 候选 trace 字段槽位（源码扫描）
# ---------------------------------------------------------------------------


def _skip_string(text: str, index: int) -> int:
    """跳过以 text[index] 为引号的字符串字面量，返回结束后的下标。"""

    quote = text[index]
    cursor = index + 1
    while cursor < len(text):
        char = text[cursor]
        if char == "\\":
            cursor += 2
            continue
        if char == quote:
            return cursor + 1
        cursor += 1
    raise FeedbackInputError("源码字符串未闭合（无法扫描 trace 字段）")


def _balanced_block(text: str, start: int) -> str:
    """取 text[start] == '{' 起的花括号平衡块（跳过字符串与注释）。"""

    depth = 0
    cursor = start
    while cursor < len(text):
        char = text[cursor]
        if char == "#":
            line_end = text.find("\n", cursor)
            cursor = len(text) if line_end < 0 else line_end + 1
            continue
        if char in "\"'":
            cursor = _skip_string(text, cursor)
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start:cursor + 1]
        cursor += 1
    raise FeedbackInputError("源码花括号不平衡（无法扫描 trace 字段）")


def _top_level_fields(block: str) -> List[Tuple[str, Optional[str]]]:
    """提取字典字面量块 depth=1 的顶层项：[(键, 嵌套块或 None)]。"""

    fields: List[Tuple[str, Optional[str]]] = []
    depth = 0
    cursor = 0
    pending: Optional[str] = None
    while cursor < len(block):
        char = block[cursor]
        if char == "#":
            line_end = block.find("\n", cursor)
            cursor = len(block) if line_end < 0 else line_end + 1
            continue
        if char in "\"'":
            end = _skip_string(block, cursor)
            if depth == 1 and pending is None:
                probe = end
                while probe < len(block) and block[probe] in " \t\r\n":
                    probe += 1
                if probe < len(block) and block[probe] == ":":
                    pending = block[cursor + 1:end - 1]
                    cursor = probe + 1
                    continue
            if depth == 1 and pending is not None:
                # 字符串外壳的值（如 "mech": "ready_width_frontier_v1"）：记键。
                fields.append((pending, None))
            pending = None
            cursor = end
            continue
        if char == "{":
            if depth == 1 and pending is not None:
                nested = _balanced_block(block, cursor)
                fields.append((pending, nested))
                pending = None
                cursor += len(nested)
                continue
            depth += 1
            cursor += 1
            continue
        if char == "}":
            depth -= 1
            cursor += 1
            continue
        if depth == 1 and pending is not None and (
                char.isalnum() or char in "_[(."):
            fields.append((pending, None))
            pending = None
        cursor += 1
    return fields


def _strip_comments(text: str) -> str:
    """把注释替换成等长空白（保持下标不变），供模式匹配使用。

    为什么必须做：trace 定位是正则匹配，注释里的 `# trace = {...}` 会被误当成
    真实代码；先抹掉注释再匹配，才不会被示例/说明文字骗到。
    """

    out = list(text)
    cursor = 0
    length = len(text)
    while cursor < length:
        char = text[cursor]
        if char in "\"'":
            cursor = _skip_string(text, cursor)
            continue
        if char == "#":
            end = text.find("\n", cursor)
            end = length if end < 0 else end
            for index in range(cursor, end):
                out[index] = " "
            cursor = end
            continue
        cursor += 1
    return "".join(out)


def trace_field_slots(source_text: str, *, max_depth: int = 2) -> List[str]:
    """从候选源码里扫出 trace 字段路径（`mech`、`parts.width` ...）。

    扫描对象是 trace 字典的**字面量**（`traces.append({...})`、`"trace": {...}`、
    `trace = {...}`）；字符串与注释内的花括号不参与配对。返回按首次出现顺序去重
    的字段路径；扫不到返回空列表（由调用方退回合同类别槽位）。
    """

    paths: List[str] = []

    def _collect(block: str, prefix: str, depth: int) -> None:
        for key, nested in _top_level_fields(block):
            path = "{0}{1}".format(prefix, key)
            if nested is not None and depth < max_depth:
                _collect(nested, path + ".", depth + 1)
            else:
                paths.append(path)

    code = _strip_comments(source_text)
    for pattern in _TRACE_REGION_PATTERNS:
        for match in re.finditer(pattern, code):
            start = code.index("{", match.start())
            _collect(_balanced_block(code, start), "", 1)
    seen: List[str] = []
    for path in paths:
        if path not in seen:
            seen.append(path)
    # 父路径已被更细路径覆盖时不再单列（如同时扫到 `parts` 与 `parts.width`）。
    return [path for path in seen
            if not any(other.startswith(path + ".") for other in seen)]


def _collect_source_digests(evaluation: Optional[Mapping[str, Any]],
                            panels: Sequence[Mapping[str, Any]]) -> List[str]:
    """把候选源码与产物对上号：**以条件评估产物登记的摘要为准**（R9/P5 F2）。

    只有在条件评估产物没有登记任何摘要时，才退到自然面板自报的摘要（此时绑定本身
    已被 `_select_panels` 判为"身份不可核验"）。旧实现把面板摘要并进同一张表，
    等于允许面板自己给自己的源码背书。
    """

    primary = _candidate_digests(evaluation)
    if primary:
        return primary
    digests: List[str] = []
    for block in [panel.get("identity") for panel in panels]:
        digest = str(_mapping(block).get("candidate_source_sha256") or "")
        if digest and digest not in digests:
            digests.append(digest)
    return digests


def _find_candidate_source(eval_dir: Path,
                           digests: Sequence[str]
                           ) -> Tuple[Optional[Path], str, Optional[Dict[str, str]]]:
    """定位候选源码：eval_dir 与其父目录下的 candidate.py，**只按产物摘要绑定**。

    找不到摘要命中的源码即返回 None + 拒绝码——旧行为是"退回第一份找到的
    candidate.py"，那会把**别的候选**的 trace 字段名当成本次候选的槽位
    （复审 §4 A5：候选/源码/评价身份不匹配必须拒绝绑定）。
    """

    roots = [eval_dir, eval_dir.parent]
    found: List[Path] = []
    for root in roots:
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("candidate.py")):
            if path not in found:
                found.append(path)
    for path in found:
        digest = _sha256_text(path.read_text(encoding="utf-8"))
        if digest in digests:
            return path, "按产物 candidate_source_sha256 绑定", None
    if not digests:
        return None, ("产物未登记候选源码摘要（candidate_source_sha256）：无法核验"
                      "源码身份，按 A5 不绑定任何源码"), _refusal(
            REFUSAL_IDENTITY_SOURCE, "产物未登记候选源码摘要：拒绝按'第一份源码'绑定")
    if found:
        return None, ("未与产物摘要绑定（产物的 candidate_source_sha256 与 {0} 份 "
                      "candidate.py 都不相等）：按 A5 不退回第一份源码").format(
            len(found)), _refusal(
            REFUSAL_IDENTITY_SOURCE,
            "候选源码与产物登记的摘要不一致（候选源码 {0} 份，无一命中 {1}）："
            "拒绝绑定".format(len(found), _short(digests[0])))
    return None, "未在评估目录及其父目录找到 candidate.py", _refusal(
        REFUSAL_IDENTITY_SOURCE,
        "评估目录及其父目录没有 candidate.py：源码身份不可核验，拒绝绑定")


# ---------------------------------------------------------------------------
# 4. 三段正文
# ---------------------------------------------------------------------------


def _identity_lines(candidate_cid: Optional[str], parent_cid: Optional[str],
                    evaluation: Optional[Mapping[str, Any]],
                    panels: Sequence[Mapping[str, Any]]) -> List[str]:
    identity = _mapping(_mapping(evaluation).get("identity"))
    lines = [
        "- 候选 candidate_id（调用方给出）：`{0}`".format(
            candidate_cid or "（未提供）"),
        "- 父代 parent_cid（调用方给出；M1 由主状态机按**父代产物**重算，"
        "消费端再与父代产物逐项核对）：`{0}`".format(
            parent_cid or "（无父代：首代 I1）"),
    ]
    if evaluation is not None:
        lines.append("- 条件评估 evaluation_id（读自产物）：`{0}`".format(
            identity.get("evaluation_id") or "（产物未给该字段）"))
        lines.append("- 产物登记的候选身份（读自产物）：candidate_id=`{0}`，"
                     "baseline_id=`{1}`".format(
                         identity.get("candidate_id") or "（缺）",
                         identity.get("baseline_id") or "（缺）"))
    else:
        lines.append("- 条件评估产物：**未提供**（本次反馈只有自然面板）")
    for panel in panels:
        panel_identity = _mapping(panel.get("identity"))
        lines.append(
            "- 自然面板 {0}：panel_epoch=`{1}`，panel_seed={2}，"
            "candidate_source_sha256=`{3}`".format(
                panel.get("mix") or "（mix 未知）",
                panel_identity.get("panel_epoch") or "（缺）",
                _num(panel_identity.get("panel_seed")),
                str(panel_identity.get("candidate_source_sha256") or "（缺）")[:16]))
    return lines


def _conditional_fact_items(eval_path: Path,
                           evaluation: Mapping[str, Any]) -> List[Dict[str, Any]]:
    """条件面板事实条目：面板身份 / 前缀尝试 / 覆盖层 / 执行类别 / 双臂终局。

    每一条都带证据（evaluation.json + JSON 定位 + 原值），因此可逐项对账；
    覆盖层读 `admission.coverage.status`（**该块没有 layers 键**，R6 旧代码取
    `admission.layers.coverage.status` 才恒为 None）。
    """

    panel = _mapping(evaluation.get("panel"))
    identity = _mapping(evaluation.get("identity"))
    admission = _mapping(evaluation.get("admission"))
    coverage = (_mapping(_mapping(admission.get("layers")).get("coverage"))
                or _mapping(admission.get("coverage")))
    items: List[Dict[str, Any]] = [
        _item("conditional.panel_identity", SEGMENT_FACTS,
              "**条件面板身份（读自 evaluation.json）**\n"
              "- generator=`{0}`，prefix_source=`{1}`，predicate=`{2}`，"
              "opponent_mix=`{3}`".format(
                  panel.get("generator") or "（缺）",
                  panel.get("prefix_source") or "（缺）",
                  panel.get("predicate") or "（缺）",
                  identity.get("opponent_mix") or "（缺）"),
              _evs(eval_path, evaluation, ("panel", "generator"),
                   ("panel", "prefix_source"), ("panel", "predicate"),
                   ("identity", "opponent_mix")),
              fallback=(eval_path, evaluation)),
    ]
    attempts = _mapping(panel.get("prefix_attempts"))
    if attempts:
        items.append(_item(
            "conditional.prefix_attempts", SEGMENT_FACTS,
            "- 前缀尝试：total={0}，hit={1}，missed={2}，unknown={3}，errors={4}，"
            "cap={5}，exhausted={6}".format(
                _num(attempts.get("total")), _num(attempts.get("hit")),
                _num(attempts.get("missed")), _num(attempts.get("unknown")),
                _num(attempts.get("errors")), _num(attempts.get("cap")),
                _flag(attempts.get("attempts_exhausted"))),
            _evs(eval_path, evaluation, ("panel", "prefix_attempts"))))
    items.append(_item(
        "conditional.coverage", SEGMENT_FACTS,
        "- 执行安全（读自产物 admission 投影）：execution_safety_pass={0}，"
        "覆盖层：{1}".format(
            _flag(admission.get("execution_safety_pass")),
            coverage.get("status") or "（产物未给该字段）"),
        _evs(eval_path, evaluation, ("admission", "coverage", "status"),
             ("admission", "execution_safety_pass")),
        fallback=(eval_path, evaluation)))
    items.append(_item(
        "conditional.execution_kind", SEGMENT_FACTS,
        "- 执行类别：{0}（引擎 {1}；真实桌赛实例 {2}，替身桌 {3}）".format(
            evaluation.get("execution_kind") or "（产物未给该字段）",
            evaluation.get("engine_kind") or "（产物未给该字段）",
            _num(evaluation.get("real_table_instances")),
            _num(evaluation.get("double_table_instances"))),
        _evs(eval_path, evaluation, ("execution_kind",), ("engine_kind",),
             ("real_table_instances",), ("double_table_instances",))))
    if not evaluation.get("usable_for_selection", True):
        items.append(_item(
            "conditional.selection_eligible", SEGMENT_FACTS,
            "- 本结果**不可用于开发选留**（非真实运行时执行；字面读自产物的 "
            "usable_for_selection）",
            _evs(eval_path, evaluation, ("usable_for_selection",))))
    arms = _mapping(_mapping(evaluation.get("double_arm")).get("arms"))
    arm_lines = [
        "", "**双臂终局（读自 evaluation.json 的 double_arm；U 区间为识别区间）**",
        "| 臂 | status | 终端 U（点） | U 下界 | U 上界 | unresolved | "
        "focal_stage_score | elapsed_ms | decisions_after_cut |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for name in ("baseline", "candidate"):
        arm = _mapping(arms.get(name))
        arm_lines.append(
            "| {0} | {1} | {2} | {3} | {4} | {5} | {6} | {7} | {8} |".format(
                name, arm.get("status") or "（产物缺该字段）", _num(arm.get("u")),
                _num(arm.get("u_low")), _num(arm.get("u_high")),
                _flag(arm.get("unresolved")), _num(arm.get("focal_stage_score")),
                _num(arm.get("elapsed_ms")), _num(arm.get("decisions_after_cut"))))
    if not arms:
        arm_lines.append("| （产物无 double_arm.arms） | | | | | | | | |")
    arm_lines.append("- 双臂完整性（读自产物）：valid={0}，声明终点=`{1}`".format(
        _flag(_mapping(evaluation.get("double_arm")).get("valid")),
        _mapping(evaluation.get("double_arm")).get("declared_endpoint") or "（缺）"))
    items.append(_item(
        "conditional.arms", SEGMENT_FACTS, "\n".join(arm_lines),
        _evs(eval_path, evaluation, ("double_arm", "arms"),
             ("double_arm", "valid"), ("double_arm", "declared_endpoint"))))
    return items


def _window_fact_items(eval_dir: Path,
                       opportunity_panels: Sequence[Mapping[str, Any]]
                       ) -> Tuple[List[Dict[str, Any]], List[Dict[str, str]]]:
    """窗口级事实条目（v4 §8.2 事实段前半）：可见窗口 / 触发与未知掩码 / 见证键 /
    合法动作前缀（**同窗口双方动作的已采集部分**）。返回（条目, 缺口）。

    诚实边界：`sitin-opportunity-snapshot/1` 记录的是**行为策略的前缀动作**
    （逐座位 window_key→action_key）与截取窗口的**观察摘要**；候选/基线两臂在截取
    窗口各自选了什么，当前产物**没有采集**——这里如实标缺，不拿源码里的字段名或
    任何推测顶替（复审 §4 A5：「不要把源码中存在的 trace 字段名当作已采集的实际
    读数」）。若上游将来在 `snapshot.window_actions` 或
    `scenario.double_arm.arms[*].focal_action_at_cut` 里登记读数，本函数会直接采用。
    """

    items: List[Dict[str, Any]] = []
    gaps: List[Dict[str, str]] = []
    for entry in opportunity_panels:
        path = Path(entry["path"])
        document = entry["data"]
        base = ("scenarios",)
        for index, scenario in enumerate(document.get("scenarios") or ()):
            scenario = _mapping(scenario)
            snapshot = _mapping(scenario.get("snapshot"))
            if not snapshot:
                items.append(_item(
                    "window.absent.{0}".format(index), SEGMENT_FACTS,
                    "- 场景 {0}：产物没有 snapshot（status=`{1}`，reason={2}）——"
                    "本场景的窗口与掩码不可追，已如实标缺".format(
                        index, scenario.get("status") or "（缺）",
                        scenario.get("reason") or "（产物未给）"),
                    _evs(path, document, base + (index,))))
                gaps.append(_gap("window.snapshot_absent",
                                 "场景 {0} 缺 snapshot：窗口/掩码不可追".format(index)))
                continue
            window = _mapping(snapshot.get("cut_window"))
            root_id = str(scenario.get("source_root_id")
                          or snapshot.get("source_root_id") or "")
            window_key = {
                "round_no": window.get("round_no"),
                "trigger_seq": window.get("trigger_seq"),
                "phase": window.get("phase"),
                "seat": window.get("seat"),
            }
            scope = base + (index, "snapshot")
            items.append(_item(
                "window.observation", SEGMENT_FACTS,
                "**同一可见窗口（读自机会面板快照 `{0}`）**\n"
                "- source_root_id=`{1}`，sub_scenario=`{2}`，window="
                "round_no={3} / trigger_seq={4} / phase={5} / seat={6}".format(
                    path.name, root_id or "（缺）",
                    scenario.get("sub_scenario") or snapshot.get("sub_scenario")
                    or "（缺）", _num(window.get("round_no")),
                    _num(window.get("trigger_seq")),
                    window.get("phase") or "（缺）", _num(window.get("seat"))),
                _evs(path, document, scope + ("cut_window",),
                     ("scenarios", index, "source_root_id")),
                root_id=root_id or None, window=window_key))
            labels = _mapping(snapshot.get("labels"))
            values = _mapping(labels.get("predicate_values_at_cut"))
            mask_text = "，".join(
                "{0}={1}".format(name, values[name]) for name in sorted(values))
            unknown = sorted(name for name in values if str(values[name]) == "UNKNOWN")
            items.append(_item(
                "window.mask", SEGMENT_FACTS,
                "- 触发与未知掩码（读自快照 labels.predicate_values_at_cut；"
                "八谓词逐项原值）：{0}\n"
                "  - 主谓词=`{1}`；UNKNOWN 掩码={2}".format(
                    mask_text or "（产物未给该字段）",
                    labels.get("main") or "（缺）",
                    "、".join(unknown) if unknown else "（无：八谓词均已知）"),
                _evs(path, document, scope + ("labels", "predicate_values_at_cut"),
                     scope + ("labels", "main")),
                root_id=root_id or None, window=window_key))
            items.append(_item(
                "window.witness", SEGMENT_FACTS,
                "- 触发见证键（读自快照 labels.witness）：{0}".format(
                    json.dumps(_mapping(labels.get("witness")), ensure_ascii=False,
                               sort_keys=True)),
                _evs(path, document, scope + ("labels", "witness")),
                root_id=root_id or None, window=window_key))
            prefix = _sequence(snapshot.get("legal_action_prefix"))
            actions = "；".join(
                "{0}→{1}".format(
                    json.dumps(_mapping(step.get("window_key")), ensure_ascii=False,
                               sort_keys=True), step.get("action_key"))
                for step in prefix if isinstance(step, Mapping))
            # —— 两臂在截取窗口的动作读数（P9b 采集）与其**实际取值来源** ——
            reading = _window_action_reading(path, document, index)
            legacy_evidences = _evs(
                path, document, scope + ("legal_action_prefix",),
                scope + ("observation_summary",))
            if reading["collected"]:
                # 已采集：指针**必须**指向实际取值来源（聚合读数 + 逐臂读数），
                # 旧字段（合法动作前缀 / 观察摘要）作为前缀部分的来源排在后面。
                evidences = (list(reading["evidences"]) + legacy_evidences) or None
                text = (
                    "- 同一可见窗口的动作（读自快照）：\n"
                    "  - **候选/基线两臂在截取窗口各自选了什么**（读自快照 {0}）：\n{1}"
                    "\n  - 逐臂动作（臂 → action_key，照录自读数）：{2}"
                    "\n  - 已采集=**行为策略的合法动作前缀**（逐座位 "
                    "window_key→action_key，共 {3} 步）：{4}".format(
                        "、".join("`{0}`".format(item) for item in reading["sources"])
                        or "（读数来源字段）",
                        "\n".join(reading["lines"]),
                        json.dumps(
                            {name: {"action_key": entry.get("action_key")}
                             for name, entry in sorted(reading["arms"].items())},
                            ensure_ascii=False, sort_keys=True),
                        len(prefix), actions or "（空：截取窗口就是前缀起点）"))
            else:
                # 未采集：指针回退到旧字段（那正是文本里那段前缀动作的来源），
                # 并如实记 input gap——不放宽任何判定。
                evidences = legacy_evidences or None
                text = (
                    "- 同一可见窗口的动作（读自快照）：已采集=**行为策略的合法动作前缀**"
                    "（逐座位 window_key→action_key，共 {0} 步）：{1}\n"
                    "  - 候选/基线两臂在截取窗口各自选了什么：**本批产物未采集该读数**"
                    "（sitin-opportunity-snapshot/1 没有逐臂窗口动作字段）"
                    "——不推算、不拿字段名顶替".format(
                        len(prefix), actions or "（空：截取窗口就是前缀起点）"))
            items.append(_item(
                "window.actions", SEGMENT_FACTS, text,
                evidences or [], fallback=(path, document),
                root_id=root_id or None, window=window_key))
            if not reading["collected"]:
                gaps.append(_gap(
                    "window.arm_actions_not_collected",
                    "根 {0} 窗口 round_no={1}/trigger_seq={2}：候选与基线两臂在截取"
                    "窗口的动作未采集（产物无该字段）".format(
                        root_id or "（缺）", window.get("round_no"),
                        window.get("trigger_seq"))))
            elif reading["missing_arms"]:
                gaps.append(_gap(
                    "window.arm_actions_partial",
                    "根 {0} 窗口 round_no={1}/trigger_seq={2}：臂 {3} 的动作读数不是"
                    "`collected`（逐臂 status/reason 已如实写进事实条目）".format(
                        root_id or "（缺）", window.get("round_no"),
                        window.get("trigger_seq"),
                        "、".join(reading["missing_arms"]))))
    return items, gaps


#: 两臂读数的臂序（与 P9b 产物的固定键序一致；其余臂名按字典序追加）。
WINDOW_ARM_ORDER: Tuple[str, ...] = ("baseline", "candidate")

#: 臂动作读数状态「已采集」：与上游 `sitin_opportunities.ARM_ACTION_COLLECTED`
#: 同一字面量（P9b 的 `sitin-window-arm-actions/1` 契约）。本模块**不导入上游模块**，
#: 只按契约读产物——投影不绑死在某个上游实现上。
ARM_ACTION_COLLECTED = "collected"


def _reading_arms(scenario: Mapping[str, Any],
                  aggregate: Mapping[str, Any]) -> List[str]:
    """读数的臂名顺序：固定臂序优先，其余按字典序（保证输出逐字节确定）。"""

    present = set(_mapping(_mapping(scenario.get("double_arm")).get("arms"))) | \
        set(_mapping(aggregate.get("arms")))
    ordered = [name for name in WINDOW_ARM_ORDER if name in present]
    return ordered + [name for name in sorted(present) if name not in ordered]


def _window_action_reading(path: Any, document: Mapping[str, Any], index: int
                           ) -> Dict[str, Any]:
    """截取窗口两臂动作读数 + **其实际取值来源**（P9b：`sitin-window-arm-actions/1`）。

    返回（全部为产物实测，无推测值）：

    - `collected`：是否存在**已采集**的臂动作读数（聚合 `snapshot.window_actions`
      或逐臂 `scenarios[i].double_arm.arms[*].focal_action_at_cut`）；
    - `arms`：{臂名: {action_key, status, reason, root_id, window_key}}；
    - `evidences`：读数来源的证据，顺序 = **聚合读数指针 → 逐臂读数指针 →
      产物自报指针（`window_actions.artifact_locator.pointers`，去重并入）**；
    - `sources`：与指针同序的来源字段名（写进条目文本，保证"文本说的来源 = 指针指的
      位置"）；
    - `missing_arms`：读数不是 `collected` 的臂（逐臂如实标注，不补默认值）；
    - `lines`：逐臂人读行（供条目文本）。

    未采集时 `collected=False`、`evidences=[]`：调用方回退到旧字段指针并记 input
    gap（不放宽任何 fail-closed 判定）。
    """

    scenario = _mapping(_sequence(document.get("scenarios"))[index]
                        if index < len(_sequence(document.get("scenarios"))) else {})
    snapshot = _mapping(scenario.get("snapshot"))
    aggregate = _mapping(snapshot.get("window_actions"))
    arms_block = _mapping(_mapping(scenario.get("double_arm")).get("arms"))
    names = _reading_arms(scenario, aggregate)
    evidences: List[Mapping[str, Any]] = []
    sources: List[str] = []
    seen: List[str] = []

    def _add(label: str, parts: Sequence[Any]) -> Optional[Mapping[str, Any]]:
        evidence = _ev(path, document, *parts)
        if evidence is None:
            return None
        key = "{0}#{1}".format(evidence["artifact"], evidence["locator"])
        if key not in seen:
            seen.append(key)
            evidences.append(evidence)
            sources.append(label)
        return evidence

    arms: Dict[str, Dict[str, Any]] = {}
    # ① 聚合读数（P9b 登记位置之一）：两臂动作的**首选来源**。
    if aggregate:
        _add("snapshot.window_actions", _snapshot_pointer(index, "window_actions"))
        for name, entry in _mapping(aggregate.get("arms")).items():
            entry = _mapping(entry)
            arms[str(name)] = {
                "action_key": entry.get("action_key"),
                "status": entry.get("status"),
                "reason": entry.get("reason"),
                "root_id": entry.get("root_id"),
                "window_key": _mapping(entry.get("window_key")),
            }
    # ② 逐臂读数（P9b 登记位置之二）：可独立定位、独立核对。
    for name in names:
        arm = _mapping(arms_block.get(name))
        pointer = _scenario_pointer(index, "double_arm", "arms", name,
                                    "focal_action_at_cut")
        reading = _mapping(arm.get("focal_action_at_cut"))
        if reading:
            _add("double_arm.arms.{0}.focal_action_at_cut".format(name), pointer)
        if name in arms:
            continue
        arms[name] = {
            "action_key": reading.get("action_key") if reading else None,
            "status": (ARM_ACTION_COLLECTED if reading else
                       arm.get("focal_action_at_cut_status")),
            "reason": None if reading else arm.get("focal_action_at_cut_reason"),
            "root_id": reading.get("root_id") if reading else None,
            "window_key": _mapping(reading.get("window_key")) if reading else {},
        }
    # ③ 产物自报指针（上游 artifact_locator）：解析得到的并入证据（去重）。
    declared = _mapping(_mapping(aggregate.get("artifact_locator")).get("pointers"))
    for label in sorted(declared):
        parts = tuple(str(declared[label]).split("/")[1:])
        if label == "snapshot.window_actions":
            _add(label, _snapshot_pointer(index, "window_actions"))
        else:
            _add(label, parts)
    collected = [name for name, item in arms.items()
                 if item.get("status") == ARM_ACTION_COLLECTED
                 and item.get("action_key") is not None]
    missing = [name for name in arms if name not in collected]
    lines: List[str] = []
    for name in ([n for n in names if n in arms] + [n for n in sorted(arms)
                                                    if n not in names]):
        item = _mapping(arms.get(name))
        window = _mapping(item.get("window_key"))
        where = "root={0}，window=round_no={1}/trigger_seq={2}/{3}/seat{4}".format(
            item.get("root_id") or "（缺）", _num(window.get("round_no")),
            _num(window.get("trigger_seq")), window.get("phase") or "（缺）",
            _num(window.get("seat")))
        if item.get("status") == ARM_ACTION_COLLECTED \
                and item.get("action_key") is not None:
            lines.append("    - {0}：action_key=`{1}`（status=`collected`，{2}）".format(
                name, item.get("action_key"), where))
        else:
            lines.append(
                "    - {0}：**该臂未采集**（status=`{1}`；reason={2}）——不推算、"
                "不补默认值".format(
                    name, item.get("status") or "（产物未给该字段）",
                    item.get("reason") or "（未给原因）"))
    return {
        "collected": bool(collected),
        "arms": arms,
        "evidences": evidences,
        "sources": sources,
        "missing_arms": missing,
        "lines": lines,
    }


def _snapshot_pointer(index: int, *parts: Any) -> Tuple[Any, ...]:
    """快照内字段的 JSON 指针（`/scenarios/<i>/snapshot/...`）。"""

    return ("scenarios", index, "snapshot") + tuple(parts)


def _scenario_pointer(index: int, *parts: Any) -> Tuple[Any, ...]:
    """场景内字段的 JSON 指针（`/scenarios/<i>/...`）。"""

    return ("scenarios", index) + tuple(parts)


def _window_rows(panels: Sequence[Mapping[str, Any]]) -> List[List[str]]:
    """自然面板逐窗口差异表（候选 U − 基线 U；逐样本读，不重算根级均值）。"""

    rows: List[List[str]] = []
    for panel in panels:
        for sample in panel.get("samples") or ():
            sample = _mapping(sample)
            arms = _mapping(sample.get("arms"))
            baseline = _mapping(arms.get("baseline"))
            candidate = _mapping(arms.get("candidate"))
            base_u = baseline.get("u")
            cand_u = candidate.get("u")
            diff = (cand_u - base_u) if isinstance(base_u, (int, float)) and not isinstance(
                base_u, bool) and isinstance(cand_u, (int, float)) and not isinstance(
                cand_u, bool) else None
            rows.append([
                str(panel.get("mix") or sample.get("opponent_mix") or "（缺）"),
                str(sample.get("source_root_id") or "（缺）"),
                _num(sample.get("focal_anchor_seat")),
                "{0}（[{1}, {2}]，unresolved={3}）".format(
                    _num(base_u), _num(baseline.get("u_low")),
                    _num(baseline.get("u_high")), _flag(baseline.get("unresolved"))),
                "{0}（[{1}, {2}]，unresolved={3}）".format(
                    _num(cand_u), _num(candidate.get("u_low")),
                    _num(candidate.get("u_high")), _flag(candidate.get("unresolved"))),
                _num(diff),
                str(sample.get("completeness") or "（缺）"),
            ])
    return rows


def _json_fallback_path(*groups: Any) -> Optional[Path]:
    """挑一个**可解析的 JSON 产物**作为"目录级"证据兜底（samples.jsonl 不算）。

    兜底证据只用于"本目录没有该产物"这类条目，仍然是真实存在的产物文件。
    """

    for group in groups:
        candidates = group if isinstance(group, (list, tuple)) else [group]
        for candidate in candidates:
            if candidate is None:
                continue
            path = Path(candidate)
            if path.suffix == ".json" and path.is_file():
                return path
    return None


def _panel_evidence_source(panel: Mapping[str, Any],
                           path: Path) -> Tuple[Mapping[str, Any], Optional[Dict[str, Any]]]:
    """自然面板的证据源：panel.json / natural-statistics.json（JSON）或 samples.jsonl。

    兼容布局（只有 samples.jsonl + statistics JSON）没有可解析成单个 JSON 的对象树：
    此时证据指向 **samples.jsonl 全文**（locator 为空串 = 文件根），原值 = 解析出的
    样本清单——仍然有出处、可核对，不编造。
    """

    if path.suffix == ".json" and path.is_file():
        return _load_json(path), None
    samples = list(panel.get("samples") or ())
    return {}, {"artifact": str(path), "locator": "", "value": samples}


def _natural_fact_items(panels: Sequence[Mapping[str, Any]],
                        fallback_path: Optional[Path]
                        ) -> List[Dict[str, Any]]:
    """自然面板事实条目：身份/实跑与逐窗口差异（每行一个样本窗口，逐项带证据）。"""

    items: List[Dict[str, Any]] = []
    if not panels:
        if fallback_path is not None:
            document = _load_json(fallback_path)
            items.append(_item(
                "natural.panel_absent", SEGMENT_FACTS,
                "**未找到自然面板产物**（evaluation.json 之外没有 panel.json / "
                "samples.jsonl）",
                [_evidence(fallback_path, "", document)]))
        return items
    row_lists: List[Tuple[Mapping[str, Any], List[List[str]]]] = []
    for panel in panels:
        path = Path(panel.get("statistics_path") or panel.get("path"))
        document, jsonl_evidence = _panel_evidence_source(panel, path)
        config = _mapping(panel.get("config"))
        cost = _mapping(panel.get("cost"))
        mix = panel.get("mix") or "（mix 未知）"
        items.append(_item(
            "natural.panel.{0}".format(mix), SEGMENT_FACTS,
            "- {0}：roots={1}，seats_per_root={2}，tables_per_group={3}，"
            "min_roots={4}；tables_full_executed={5} / planned={6}"
            "（读到 `{7}`）".format(
                mix, _num(config.get("roots")),
                _num(config.get("seats_per_root")),
                _num(config.get("tables_per_group")), _num(config.get("min_roots")),
                _num(cost.get("tables_full_executed")),
                _num(cost.get("tables_full_planned")), path.name),
            _evs(path, document, ("config",), ("cost",), ("identity",))
            or ([jsonl_evidence] if jsonl_evidence else []),
            fallback=(path, document)))
        rows = _window_rows([panel])
        row_lists.append((panel, rows))
        if not rows:
            items.append(_item(
                "natural.window_rows.{0}".format(mix), SEGMENT_FACTS,
                "- {0}：（自然面板产物里没有 samples：无窗口级数字可报）".format(mix),
                _evs(path, document, ("samples",))
                or ([jsonl_evidence] if jsonl_evidence else []),
                fallback=(path, document)))
            continue
        lines = ["**逐窗口差异（{0}；候选 U − 基线 U；每行一个样本窗口）**".format(mix),
                 "| 情景 | source_root_id | 焦点座位 | 基线 U（区间，unresolved） | "
                 "候选 U（区间，unresolved） | 窗口差 | 完整性 |",
                 "| --- | --- | --- | --- | --- | --- | --- |"]
        lines += ["| " + " | ".join(row) + " |" for row in rows]
        lines.append("- {0} 窗口行数={1}（程序计数）".format(mix, len(rows)))
        items.append(_item(
            "natural.window_rows.{0}".format(mix), SEGMENT_FACTS, "\n".join(lines),
            _evs(path, document, ("samples",), ("statistics",))
            or ([jsonl_evidence] if jsonl_evidence else []),
            fallback=(path, document)))
    total = sum(len(rows) for _panel, rows in row_lists)
    evidences: List[Mapping[str, Any]] = []
    for panel in panels:
        path = Path(panel.get("statistics_path") or panel.get("path"))
        _document, jsonl_evidence = _panel_evidence_source(panel, path)
        evidence = _ev(path, _document, "samples") or jsonl_evidence
        if evidence is not None:
            evidences.append(evidence)
    if evidences:
        items.append(_item(
            "natural.window_rows_count", SEGMENT_FACTS,
            "- 窗口行数={0}（程序计数；逐行数字读自产物，未做任何汇总替换）".format(
                total),
            evidences))
    return items


def _cost_failure_items(eval_path: Optional[Path],
                        evaluation: Optional[Mapping[str, Any]],
                        opportunity_panels: Sequence[Mapping[str, Any]],
                        panels: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    """成本与失败条目（v4 §8.2 事实段后半）：逐字段读自产物，缺失显式标注。"""

    items: List[Dict[str, Any]] = []
    records: List[Tuple[Path, Mapping[str, Any]]] = []
    multiple = len(opportunity_panels) > 1
    for entry in opportunity_panels:
        path = Path(entry["path"])
        document = entry["data"]
        # 只有一个机会面板时用稳定键（cost.execution / failure.masks），多个才加目录后缀。
        suffix = ".{0}".format(path.parent.name) if multiple else ""
        ledger = _sequence(document.get("cost_ledger"))
        record = _mapping(ledger[0]) if ledger else {}
        records.append((path, document))
        arms = _mapping(evaluation.get("double_arm")).get("arms") if evaluation else {}
        elapsed = _mapping(record.get("elapsed_ms_by_arm")) or {
            name: _mapping(arm).get("elapsed_ms")
            for name, arm in _mapping(arms).items()}
        items.append(_item(
            "cost.execution{0}".format(suffix), SEGMENT_FACTS,
            "**成本与失败（读自机会面板 cost_ledger / budget_red_line / "
            "prefix_attempt_errors）**\n"
            "- 臂耗时 elapsed_ms_by_arm={0}；执行桌数 tables_executed_by_arm={1}；"
            "实际桌赛实例 actual_table_instances={2}；完整性 completeness=`{3}`\n"
            "- 降级（degradations）：{4}\n"
            "- 计费红线（budget_red_line）：{5}".format(
                json.dumps(elapsed, ensure_ascii=False, sort_keys=True),
                json.dumps(_mapping(record.get("tables_executed_by_arm")),
                           ensure_ascii=False, sort_keys=True),
                _num(record.get("actual_table_instances")),
                record.get("completeness") or "（产物未给该字段）",
                json.dumps(list(record.get("degradations") or []),
                           ensure_ascii=False),
                json.dumps(_mapping(document.get("budget_red_line")),
                           ensure_ascii=False, sort_keys=True)),
            _evs(path, document, ("cost_ledger",), ("budget_red_line",),
                 ("wall_ms_total",), ("prefix_attempt_errors",)),
            fallback=(path, document)))
        errors = list(document.get("prefix_attempt_errors") or [])
        attempts = _mapping(document.get("prefix_attempts"))
        items.append(_item(
            "failure.masks{0}".format(suffix), SEGMENT_FACTS,
            "**失败与未知面（读自产物各计数；缺失即标缺，不补零）**\n"
            "- 前缀尝试：errors={0}，unknown={1}，missed={2}，attempt_errors={3}\n"
            "- 统计层：{4}\n- 自然面板样本无效原因：{5}".format(
                _num(attempts.get("errors")), _num(attempts.get("unknown")),
                _num(attempts.get("missed")),
                json.dumps(errors, ensure_ascii=False) if errors else "（无）",
                _statistics_failure_text(evaluation, eval_path),
                json.dumps(
                    [list(_mapping(sample).get("invalid_reasons") or [])
                     for panel in panels
                     for sample in (panel.get("samples") or ())],
                    ensure_ascii=False) if panels else "（无自然面板产物）"),
            _evs(path, document, ("prefix_attempts",), ("prefix_attempt_errors",)),
            fallback=(path, document)))
    if not records and evaluation is not None and eval_path is not None:
        arms = _mapping(_mapping(evaluation.get("double_arm")).get("arms"))
        items.append(_item(
            "cost.execution.evaluation", SEGMENT_FACTS,
            "**成本与失败（读自 evaluation.json；无机会面板产物）**\n"
            "- 臂耗时/状态：{0}".format(json.dumps(
                {name: {"elapsed_ms": _mapping(arm).get("elapsed_ms"),
                        "status": _mapping(arm).get("status")}
                 for name, arm in arms.items()}, ensure_ascii=False, sort_keys=True)),
            _evs(eval_path, evaluation, ("double_arm", "arms"))))
        items.append(_item(
            "failure.masks.evaluation", SEGMENT_FACTS,
            "**失败与未知面（读自 evaluation.json）**\n- 统计层：{0}".format(
                _statistics_failure_text(evaluation, eval_path)),
            _evs(eval_path, evaluation, ("statistics", "invalid_count"),
                 ("statistics", "uncomputable_count"))))
    return items


def _statistics_failure_text(evaluation: Optional[Mapping[str, Any]],
                             eval_path: Optional[Path]) -> str:
    """统计层失败计数（逐项读自产物；缺字段显式标注）。"""

    if evaluation is None:
        return "（无条件评估产物）"
    statistics = _mapping(evaluation.get("statistics"))
    arms = _mapping(_mapping(evaluation.get("double_arm")).get("arms"))
    arm_state = "，".join(
        "{0}: status=`{1}`，error={2}".format(
            name, _mapping(arm).get("status") or "（缺）",
            _mapping(arm).get("error") if _mapping(arm).get("error") else "（无）")
        for name, arm in sorted(arms.items())) or "（产物无 arms）"
    return ("invalid_count={0}，uncomputable_count={1}；臂级：{2}（读自 `{3}`）".format(
        _num(statistics.get("invalid_count")),
        _num(statistics.get("uncomputable_count")), arm_state,
        eval_path.name if eval_path is not None else "（缺）"))


def _candidate_key(statistics: Mapping[str, Any],
                   candidate_cid: Optional[str]) -> Optional[str]:
    """在统计块里定位候选键：**有期望身份就必须精确匹配**（R9/P5 F2）。

    旧行为是"只有一个候选就采用它"——汇总结算里的唯一外来候选因此可以覆盖正确结果
    （复审 R8 §6 F2 反例：外来候选 blocks 的均值 777.0 被当成本次候选的读数）。
    现在没有精确命中就返回 None：调用方跳过该统计块，并由拒绝判定拦住可执行性。
    """

    if not candidate_cid:
        return None
    by_candidate = _mapping(statistics.get("by_candidate"))
    return str(candidate_cid) if str(candidate_cid) in by_candidate else None


def _stat_line(label: str, block: Mapping[str, Any],
               statistics: Mapping[str, Any]) -> List[str]:
    """把一块面板统计渲染成"数字 + 产物自带口径"的条目列表。"""

    bounds = _mapping(block.get("delta_bounds"))
    lines = [
        "- {0}：n_roots={1}，n_samples={2}，status=`{3}`".format(
            label, _num(block.get("n_roots")), _num(block.get("n_samples")),
            block.get("status") or "（产物未给该字段）"),
        "  - 根级差 mean_delta={0}；识别区间 d_low={1} ~ d_high={2}"
        "（保守配对，产物的 delta_bounds）".format(
            _num(block.get("mean_delta")), _num(bounds.get("mean_delta_low")),
            _num(bounds.get("mean_delta_high"))),
        "  - 抽样区间 interval_95={0}（{1}）；根间 standard_error={2}".format(
            _num(block.get("interval_95")),
            block.get("interval_note") or "（产物未给口径说明）",
            _num(block.get("standard_error"))),
        "  - 未分辨计数：unresolved_roots={0}，invalid_roots={1}，"
        "invalid_samples={2}，uncomputable_samples={3}（min_roots={4}）".format(
            _num(bounds.get("unresolved_roots")), _num(block.get("n_invalid_roots")),
            _num(block.get("n_invalid_samples")),
            _num(block.get("n_uncomputable_samples")),
            _num(statistics.get("min_roots"))),
    ]
    rows = _sequence(block.get("root_rows"))
    if rows:
        lines.append("  - 根明细：")
        for row in rows:
            row = _mapping(row)
            lines.append(
                "    - root_id=`{0}`：n_windows={1}，d_point={2}，d_low={3}，"
                "d_high={4}，unresolved={5}".format(
                    row.get("root_id") or "（缺）", _num(row.get("n_windows")),
                    _num(row.get("d_point")), _num(row.get("d_low")),
                    _num(row.get("d_high")), _flag(row.get("unresolved"))))
    return lines


def _mixed_value(blocks: Mapping[str, Mapping[str, Any]],
                 weights: Mapping[str, Any]) -> Tuple[Optional[float], List[str]]:
    """按产物声明的权重合成 H/M 混合值；权重或某情景缺值即返回 None（不猜）。"""

    used: List[str] = []
    total = 0.0
    weight_sum = 0.0
    for mix in sorted(weights):
        weight = weights.get(mix)
        if not isinstance(weight, (int, float)) or isinstance(weight, bool):
            return None, []
        value = _mapping(blocks.get(mix)).get("mean_delta")
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            return None, []
        total += float(weight) * float(value)
        weight_sum += float(weight)
        used.append("{0}×{1}（{2} 根）".format(
            _num(weight), _num(value), _num(_mapping(blocks.get(mix)).get("n_roots"))))
    if weight_sum <= 0:
        return None, []
    return total / weight_sum, used


def _block_locator(prefix: str, mix: str) -> str:
    """统计块的 JSON 指针（prefix 已含 `.../panels/<情景>`，此处只补 H/M 层）。"""

    return "{0}/panels/{1}".format(prefix, mix)


def _name_of(path: Any) -> str:
    """产物文件名（用于文本里的"读自哪份产物"）。"""

    return Path(path).name if path else "（未记录产物）"


def _block_slot(block: Mapping[str, Any], statistics: Mapping[str, Any],
                document: Mapping[str, Any], path: Optional[Path],
                locator: str) -> Dict[str, Any]:
    """一个 (情景, H/M) 统计块槽位：块本身 + 它读自哪份产物 + JSON 定位。

    `document` 必须是**整份产物**（evaluation.json / summary/statistics.json /
    panel.json 的根），因为 `locator` 是从文件根起算的指针。
    """

    return {"block": block, "statistics": statistics, "path": path,
            "document": document, "locator": locator}


def _collect_result_blocks(eval_path: Optional[Path],
                           evaluation: Optional[Mapping[str, Any]],
                           panels: Sequence[Mapping[str, Any]],
                           summary_path: Optional[Path],
                           summary_statistics: Optional[Mapping[str, Any]],
                           candidate_cid: Optional[str]) -> Dict[str, Any]:
    """汇总"每个情景 × H/M"的统计块，并记下它读自哪份产物（可对账）。

    优先级：**主状态机写出的 summary/statistics.json（已验证：已做替身/夹具排除与
    同实例去重）** > 条件评估产物自带 statistics > 自然面板 panel.json 自带 statistics。
    每个块都带 `path` + `prefix`（JSON 指针前缀），证据因此可逐项追到产物。
    """

    blocks: Dict[str, Dict[str, Any]] = {}
    key = _candidate_key(_mapping(summary_statistics), candidate_cid)
    if summary_statistics is not None and key is not None and summary_path is not None:
        for scenario, scenario_block in sorted(
                _mapping(_mapping(_mapping(summary_statistics).get("by_candidate"))
                         .get(key)).get("panels", {}).items()):
            scenario_block = _mapping(scenario_block)
            prefix = "/by_candidate/{0}/panels/{1}".format(key, scenario)
            entry = {"path": summary_path, "document": summary_statistics,
                     "statistics": summary_statistics, "prefix": prefix,
                     "declared_mix": _mapping(scenario_block.get("declared_mix")),
                     "mixes": {}}
            for mix, mix_block in sorted(
                    _mapping(scenario_block.get("panels")).items()):
                entry["mixes"][str(mix)] = _block_slot(
                    _mapping(mix_block), summary_statistics, summary_statistics,
                    summary_path, _block_locator(prefix, str(mix)))
            blocks[str(scenario)] = entry
    if evaluation is not None and eval_path is not None:
        statistics = _mapping(evaluation.get("statistics"))
        key = _candidate_key(statistics, candidate_cid)
        if key is not None:
            for scenario, scenario_block in sorted(
                    _mapping(_mapping(_mapping(statistics).get("by_candidate"))
                             .get(key)).get("panels", {}).items()):
                scenario = str(scenario)
                if scenario in blocks:
                    continue
                scenario_block = _mapping(scenario_block)
                prefix = "/statistics/by_candidate/{0}/panels/{1}".format(key, scenario)
                entry = {"path": eval_path, "document": evaluation,
                         "statistics": statistics, "prefix": prefix,
                         "declared_mix": _mapping(scenario_block.get("declared_mix")),
                         "mixes": {}}
                for mix, mix_block in sorted(
                        _mapping(scenario_block.get("panels")).items()):
                    entry["mixes"][str(mix)] = _block_slot(
                        _mapping(mix_block), statistics, evaluation, eval_path,
                        _block_locator(prefix, str(mix)))
                blocks[scenario] = entry
    for panel in panels:
        path = Path(panel.get("statistics_path") or panel.get("path"))
        document = _load_json(path)
        statistics = _mapping(panel.get("statistics")) or _mapping(
            document.get("statistics"))
        mix = str(panel.get("mix") or "")
        key = _candidate_key(statistics, panel.get("reported_candidate_id")
                             or candidate_cid)
        if key is None:
            continue
        scenario_block = _mapping(_mapping(_mapping(statistics.get("by_candidate"))
                                           .get(key)).get("panels", {}).get("normal"))
        block = _mapping(_mapping(scenario_block.get("panels")).get(mix))
        if not block:
            continue
        # 兼容布局里 statistics_path 就是 natural-statistics.json 本体（根即统计块），
        # 此时指针不带 /statistics 前缀；panel.json 布局则带。
        root_prefix = "" if "by_candidate" in document else "/statistics"
        entry = blocks.setdefault("normal", {
            "path": path, "document": document, "statistics": statistics,
            "prefix": "{0}/by_candidate/{1}/panels/normal".format(root_prefix, key),
            "declared_mix": _mapping(scenario_block.get("declared_mix")),
            "mixes": {}})
        entry["mixes"].setdefault(mix, _block_slot(
            block, statistics, document, path,
            _block_locator(entry["prefix"], mix)))
    return blocks


def _result_items(blocks: Mapping[str, Mapping[str, Any]],
                  evaluation: Optional[Mapping[str, Any]],
                  eval_path: Optional[Path],
                  fallback_path: Optional[Path],
                  panels: Sequence[Mapping[str, Any]] = (),
                  ) -> Tuple[List[Dict[str, Any]], List[Dict[str, str]]]:
    """第二段条目：根级差 / 识别区间 / 未分辨计数 / 声明混合（全部读自产物统计块）。"""

    items: List[Dict[str, Any]] = []
    gaps: List[Dict[str, str]] = []
    # 没有条件评估产物时，条目仍要有出处：退到目录里真实存在的 JSON 产物（根指针）。
    fallback_doc = _load_json(fallback_path) if fallback_path is not None else None
    fallback_ev = ([_evidence(fallback_path, "", fallback_doc)]
                   if fallback_doc is not None else [])
    fallback_pair = ((fallback_path, fallback_doc)
                     if fallback_doc is not None else None)
    predicate = str(_mapping(_mapping(evaluation).get("panel")).get("predicate")
                    or "branch_open")
    expected_mix = str(_mapping(_mapping(evaluation).get("identity"))
                       .get("opponent_mix") or "H")
    if evaluation is None or eval_path is None:
        if fallback_ev:
            items.append(_item(
                "result.conditional_absent", SEGMENT_RESULTS,
                "**条件面板：本目录没有条件评估产物**（无 evaluation.json）：条件面板的"
                "根级差与识别区间**不可报**（不推算）",
                fallback_ev))
        gaps.append(_gap("result.conditional_absent",
                         "本目录没有 evaluation.json：条件面板读数缺失"))
    entry = blocks.get(predicate)
    if entry is None or not entry.get("mixes"):
        items.append(_item(
            "result.{0}.{1}".format(predicate, expected_mix), SEGMENT_RESULTS,
            "**条件面板 `{0}/{1}`（读自 {2} 的 statistics）**\n"
            "- （产物里没有该候选的 `{0}`/`{1}` 面板块：不推算、不留空白数字）".format(
                predicate, expected_mix,
                _name_of(entry["path"] if entry else eval_path)),
            _evs(eval_path, evaluation, ("statistics", "by_candidate"))
            or fallback_ev, fallback=fallback_pair))
        gaps.append(_gap("result.conditional_block_absent",
                         "条件面板 {0}/{1} 无统计块".format(predicate, expected_mix)))
    else:
        for index, mix in enumerate(sorted(entry["mixes"])):
            slot = entry["mixes"][mix]
            header = ("**条件面板 `{0}/{1}`（读自 {2} 的 statistics）**\n".format(
                predicate, mix, _name_of(slot.get("path") or entry["path"]))
                if index == 0 else "")
            items.append(_item(
                "result.{0}.{1}".format(predicate, mix), SEGMENT_RESULTS,
                header + "\n".join(_stat_line(
                    "{0}/{1}".format(predicate, mix), slot["block"],
                    slot["statistics"])),
                _evs(slot.get("path") or entry["path"],
                     slot.get("document") or entry["document"],
                     tuple(slot["locator"].split("/")[1:]))))
    statistics = _mapping(_mapping(evaluation).get("statistics"))
    if statistics:
        items.append(_item(
            "result.global_counts", SEGMENT_RESULTS,
            "- 全局计数（读自产物）：invalid_count={0}，uncomputable_count={1}，"
            "n_samples={2}".format(
                _num(statistics.get("invalid_count")),
                _num(statistics.get("uncomputable_count")),
                _num(statistics.get("n_samples"))),
            _evs(eval_path, evaluation, ("statistics", "invalid_count"),
                 ("statistics", "uncomputable_count"), ("statistics", "n_samples"))))
    normal = blocks.get("normal")
    if normal and normal.get("mixes"):
        for index, mix in enumerate(sorted(normal["mixes"])):
            slot = normal["mixes"][mix]
            header = ("**自然面板 `normal`（读自 {0} 的 statistics）**\n".format(
                _name_of(slot.get("path") or normal["path"])) if index == 0 else "")
            items.append(_item(
                "result.normal.{0}".format(mix), SEGMENT_RESULTS,
                header + "\n".join(_stat_line(
                    "normal/{0}".format(mix), slot["block"], slot["statistics"])),
                _evs(slot.get("path") or normal["path"],
                     slot.get("document") or normal["document"],
                     tuple(slot["locator"].split("/")[1:]))))
    else:
        # 逐情景如实标缺（哪一份面板缺哪一侧就说哪一侧），不退回"没有就是零"。
        for panel in panels:
            mix = str(panel.get("mix") or "（mix 未知）")
            path = Path(panel.get("statistics_path") or panel.get("path"))
            document = _load_json(path)
            items.append(_item(
                "result.normal.{0}".format(mix), SEGMENT_RESULTS,
                "- {0}：产物里没有该候选的 normal/{0} 面板块（不推算数字）".format(mix),
                _evs(path, document, ("statistics", "by_candidate")),
                fallback=(path, document)))
            gaps.append(_gap("result.normal_block_absent",
                             "自然面板 normal/{0} 无统计块".format(mix)))
        if not panels:
            items.append(_item(
                "result.normal_absent", SEGMENT_RESULTS,
                "**自然面板 `normal`：产物里没有该候选的面板块**（不推算数字）",
                _evs(eval_path, evaluation, ("statistics", "by_candidate"))
                or fallback_ev, fallback=fallback_pair))
            gaps.append(_gap("result.normal_block_absent", "自然面板 normal 无统计块"))
    declared = _mapping((normal or entry or {}).get("declared_mix"))
    weights = _mapping(declared.get("weights"))
    mix_blocks = {mix: slot["block"]
                  for mix, slot in _mapping((normal or {}).get("mixes")).items()}
    declared_evidence_path = (normal or entry or {}).get("path") or eval_path
    declared_evidence_doc = (normal or entry or {}).get("document") or evaluation
    declared_prefix = (normal or entry or {}).get("prefix") or ""
    declared_locator = "{0}/declared_mix".format(declared_prefix)
    if mix_blocks and weights:
        value, used = _mixed_value(mix_blocks, weights)
        if value is None:
            text = ("- 声明混合值：**不可计算**（权重或某情景缺 mean_delta；"
                    "产物权重={0}）".format(json.dumps(weights, ensure_ascii=False)))
        else:
            text = ("- 声明混合值（权重读自产物 declared_mix.weights="
                    "{0}）：{1} = {2}".format(
                        json.dumps(weights, ensure_ascii=False, sort_keys=True),
                        " + ".join(used), _num(round(value, 6))))
    else:
        text = "- 声明混合值：**不可计算**（产物未给权重或只有一个情景在场）"
    items.append(_item(
        "result.declared_mix", SEGMENT_RESULTS, text,
        (_evs(declared_evidence_path, declared_evidence_doc,
              tuple(declared_locator.split("/")[1:]))
         if declared_evidence_path is not None else []) or fallback_ev,
        fallback=((declared_evidence_path, declared_evidence_doc)
                  if declared_evidence_path is not None else fallback_pair)))
    # 程序口径条目：min_roots 逐项读自产物（定位随"统计块读自哪份产物"变化）。
    chosen = None
    for candidate_entry in (normal, entry):
        if candidate_entry and _mapping(candidate_entry.get("statistics")).get(
                "min_roots") is not None:
            chosen = candidate_entry
            break
    chosen = chosen or normal or entry
    if chosen:
        statistics_path = chosen.get("path")
        statistics_doc = chosen.get("document")
        prefix = str(chosen.get("prefix") or "")
        stats_locator = ("/statistics/min_roots" if prefix.startswith("/statistics/")
                         else "/min_roots")
        min_roots = _mapping(chosen.get("statistics")).get("min_roots")
    else:
        statistics_path, statistics_doc = eval_path, evaluation
        stats_locator, min_roots = "/statistics/min_roots", None
    if statistics_path is None and fallback_pair is not None:
        statistics_path, statistics_doc = fallback_pair
        stats_locator, min_roots = "/min_roots", None
    items.append(_item(
        "result.boundary_note", SEGMENT_RESULTS,
        "**程序口径（不判定优胜）**：上表数字全部读自产物；`interval_95` 是抽样"
        "不确定性、`delta_bounds` 是识别区间，二者分开报告；n_roots < "
        "min_roots（产物值={0}）时无根间标准误，该面板记为**未分辨**——未分辨是有效"
        "评价结果，既不是执行失败，也不是改进证明。程序不提名、不发布、不替人下结论。".format(
            _num(min_roots)),
        _evs(statistics_path, statistics_doc,
             tuple(stats_locator.split("/")[1:]))))
    return items, gaps


def _family_side_items(blocks: Mapping[str, Mapping[str, Any]]
                       ) -> Tuple[List[Dict[str, Any]], List[Dict[str, str]]]:
    """机会/代价两侧条目（v4 §8.1）：同族两个子场景的**原值**一起报，缺侧标缺。"""

    families: Dict[str, List[str]] = {}
    for name in blocks:
        if name.endswith("_open") or name.endswith("_cost"):
            family, side = name.rsplit("_", 1)
            families.setdefault(family, [])
            if side not in families[family]:
                families[family].append(side)
    items: List[Dict[str, Any]] = []
    gaps: List[Dict[str, str]] = []
    for family in sorted(families):
        lines = ["**机会/代价两侧（族 {0}；原值逐项读自产物统计块）**".format(family)]
        evidences: List[Mapping[str, Any]] = []
        for side in ("open", "cost"):
            name = "{0}_{1}".format(family, side)
            entry = blocks.get(name)
            if entry and entry.get("mixes"):
                for mix in sorted(entry["mixes"]):
                    slot = entry["mixes"][mix]
                    block = slot["block"]
                    bounds = _mapping(block.get("delta_bounds"))
                    lines.append(
                        "- `{0}`/{1}：n_roots={2}，mean_delta={3}，"
                        "识别区间 [{4}, {5}]，status=`{6}`".format(
                            name, mix, _num(block.get("n_roots")),
                            _num(block.get("mean_delta")),
                            _num(bounds.get("mean_delta_low")),
                            _num(bounds.get("mean_delta_high")),
                            block.get("status") or "（产物未给该字段）"))
                    evidences += _evs(slot.get("path") or entry["path"],
                                      slot.get("document") or entry["document"],
                                      tuple(slot["locator"].split("/")[1:]))
            else:
                lines.append(
                    "- `{0}`：**本批未评价**（产物 statistics 无该侧面板块）——"
                    "§8.1 要求同族机会/代价两侧原值一起报，不得只报有利侧；"
                    "缺侧不补零、不外推".format(name))
                gaps.append(_gap(
                    "family.side_not_evaluated",
                    "族 {0} 的 {1} 侧本批无统计块（未评价）".format(family, name)))
        if evidences:
            items.append(_item("result.family_sides.{0}".format(family),
                               SEGMENT_RESULTS, "\n".join(lines), evidences))
    return items, gaps


def _selection_note_items(notes_path: Optional[Path],
                          notes: Mapping[str, Any]) -> List[Dict[str, Any]]:
    """选留口径条目（排除量 / 去重量 / 自然面板样本数），逐条读自 selection-notes.json。"""

    if notes_path is None or not notes:
        return []
    items: List[Dict[str, Any]] = []
    document = _load_json(notes_path)
    for index, note in enumerate(_sequence(notes.get("notes"))):
        note = _mapping(note)
        text = str(note.get("text") or "")
        if not text:
            continue
        items.append(_item(
            "selection.{0}".format(note.get("key") or index), SEGMENT_FACTS, text,
            _evs(notes_path, document, ("notes", index, "text")),
            fallback=(notes_path, document)))
    return items


def _read_usage_manifest(path: Path) -> Dict[str, str]:
    """读冻结根用途清单 → {root_id: usage}（schema 不符或根跨界即拒绝，fail-closed）。

    与 `sitin_archive.load_root_usage_manifest` 同一 schema 与三分区词表；本模块不
    依赖档案模块（保持"纯读文件 + 纯字符串处理"），两者一致由测试锁死。
    """

    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise FeedbackInputError("根用途清单不可读：{0}".format(error))
    if not isinstance(data, Mapping) or \
            data.get("schema") != ROOT_USAGE_MANIFEST_SCHEMA:
        raise FeedbackInputError(
            "根用途清单 schema 必须是 {0}".format(ROOT_USAGE_MANIFEST_SCHEMA))
    sections = _mapping(data.get("usage"))
    usage: Dict[str, str] = {}
    for section in ROOT_USAGES:
        for root_id in _sequence(sections.get(section)):
            key = str(root_id)
            if key in usage:
                raise FeedbackInputError("根 {0!r} 在用途清单中跨界重复".format(key))
            usage[key] = section
    return usage


def _redact(text: str, secrets: Sequence[str]) -> str:
    """把确认根名从诊断文本里抹掉（诊断只暴露定位，不复制确认结果）。"""

    redacted = str(text)
    for secret in secrets:
        if secret:
            redacted = redacted.replace(str(secret), REDACTED_ROOT)
    return redacted


def _scan_usage_documents(sources: Sequence[Sequence[Any]],
                          manifest: Optional[Mapping[str, str]] = None,
                          node_limit: int = USAGE_SCAN_NODE_LIMIT) -> Dict[str, Any]:
    """在**任何渲染/汇总之前**扫描完整实际读取文档的根用途标记。

    `sources` 每项 = (产物路径, 文档对象, 定位前缀)；定位前缀用于独立 JSONL
    （`/line/<i>`），单文档用空串。返回：

    - `confirmation`：确认用途命中（`usage/root_usage == confirmation`、
      `confirmation_eligible is True`，或冻结清单把它划进确认分区）；
    - `unknown`：词表外的用途词、同节点内自相冲突的声明、或与冻结清单不一致；
    - `secrets`：命中节点自报的根名（诊断里要抹掉的确认结果）；
    - `nodes` / `truncated`：扫描是否完整（不完整同样拒绝，不静默放行）。
    """

    confirmation: List[Dict[str, Any]] = []
    unknown: List[Dict[str, Any]] = []
    secrets: List[str] = []
    documents: List[str] = []
    state = {"nodes": 0, "truncated": False}

    def _record(bucket: List[Dict[str, Any]], artifact: Any, locator: str,
                field: str, declared: str, roots: Sequence[str]) -> None:
        entry = {"artifact": str(artifact), "locator": locator, "field": field,
                 "declared": str(declared), "roots": list(roots)}
        if entry not in bucket:
            bucket.append(entry)

    def _inspect(node: Mapping[str, Any], parts: Sequence[Any],
                 artifact: Any, prefix: str) -> None:
        locator = prefix + _pointer(parts)
        declared = []
        for field in USAGE_FIELDS:
            raw = node.get(field)
            if isinstance(raw, str) and raw.strip():
                declared.append((field, raw.strip()))
        flag = node.get(CONFIRMATION_FLAG_FIELD)
        flag = flag if isinstance(flag, bool) else None
        roots = [str(node.get(field)) for field in ROOT_ID_FIELDS
                 if isinstance(node.get(field), str) and node.get(field)]
        values = sorted({value.lower() for _field, value in declared})
        if len(values) > 1:
            _record(unknown, artifact, locator, "usage/root_usage",
                    "、".join(values), roots)
        confirmed = False
        developed = False
        for field, value in declared:
            lowered = value.lower()
            if lowered == CONFIRMATION_USAGE:
                confirmed = True
                _record(confirmation, artifact, locator, field, value, roots)
            elif lowered in ROOT_USAGES:
                developed = True
            else:
                _record(unknown, artifact, locator, field, value, roots)
        if flag is True:
            if developed:
                _record(unknown, artifact, locator, CONFIRMATION_FLAG_FIELD,
                        "true", roots)
            elif not confirmed:
                _record(confirmation, artifact, locator, CONFIRMATION_FLAG_FIELD,
                        "true", roots)
            confirmed = True
        if flag is False and confirmed:
            _record(unknown, artifact, locator, CONFIRMATION_FLAG_FIELD, "false", roots)
        if manifest is not None and (declared or flag is not None or roots):
            for root in roots:
                usage = manifest.get(root)
                if usage is None:
                    if declared or flag is not None:
                        _record(unknown, artifact, locator, "root_id",
                                "{0}（不在冻结清单中）".format(root), roots)
                    continue
                if usage == CONFIRMATION_USAGE:
                    _record(confirmation, artifact, locator, "(usage-manifest)",
                            root, roots)
                    confirmed = True
                else:
                    for field, value in declared:
                        lowered = value.lower()
                        if lowered in ROOT_USAGES and lowered != usage:
                            _record(unknown, artifact, locator, field,
                                    "{0}（清单为 {1}）".format(value, usage), roots)
        if confirmed:
            for root in roots:
                if root and root not in secrets:
                    secrets.append(root)

    def _walk(node: Any, parts: List[Any], artifact: Any, prefix: str) -> None:
        if state["truncated"]:
            return
        state["nodes"] += 1
        if state["nodes"] > node_limit:
            state["truncated"] = True
            return
        if isinstance(node, Mapping):
            _inspect(node, parts, artifact, prefix)
            for key in sorted(node, key=str):
                _walk(node[key], parts + [key], artifact, prefix)
        elif isinstance(node, list):
            for index, value in enumerate(node):
                _walk(value, parts + [index], artifact, prefix)

    for source in sources:
        artifact, document = source[0], source[1]
        prefix = str(source[2]) if len(source) > 2 and source[2] else ""
        documents.append(str(artifact))
        _walk(document, [], artifact, prefix)
    return {"confirmation": confirmation, "unknown": unknown, "secrets": secrets,
            "nodes": state["nodes"], "truncated": state["truncated"],
            "documents": documents}


def _usage_refusal_details(scan: Mapping[str, Any]) -> List[Dict[str, str]]:
    """把用途扫描命中转成拒绝条目：**只写文档 / 字段 / JSON 路径**，并抹掉确认根名。"""

    secrets = list(scan.get("secrets") or [])
    refusals: List[Dict[str, str]] = []
    for hit in list(scan.get("confirmation") or [])[:8]:
        refusals.append(_refusal(REFUSAL_BOUNDARY_CONFIRMATION, _redact(
            "确认用途数据混入（{0}#{1} 字段 {2}={3}）：确认根不得进入开发反馈或"
            "任务包；本反馈不复制任何产物内容".format(
                Path(str(hit["artifact"])).name, hit["locator"],
                hit["field"], hit["declared"]), secrets)))
    for hit in list(scan.get("unknown") or [])[:8]:
        refusals.append(_refusal(REFUSAL_BOUNDARY_USAGE_UNKNOWN, _redact(
            "根用途未冻结或自相冲突（{0}#{1} 字段 {2}={3}）：未统一到冻结用途词表的"
            "根不得进入开发反馈；本反馈不复制任何产物内容".format(
                Path(str(hit["artifact"])).name, hit["locator"],
                hit["field"], hit["declared"]), secrets)))
    if scan.get("truncated"):
        refusals.append(_refusal(
            REFUSAL_BOUNDARY_USAGE_UNKNOWN,
            "根用途扫描超过节点上限（{0}）：扫描不完整即按边界拒绝，不静默放行".format(
                USAGE_SCAN_NODE_LIMIT)))
    return refusals


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _admission_identity(evaluation: Optional[Mapping[str, Any]]
                        ) -> Optional[Dict[str, Any]]:
    """产物登记的准入身份块（原样带入；缺即 None——消费端据此拒绝，不替它编）。

    P4/M1 起该块含 `materials_sha256` / `executor_version` / `thresholds` 等
    评价材料与评判语义字段；反馈只做**搬运**，核对由 M1 读取闸门按字段做。
    """

    identity = _mapping(_mapping(_mapping(evaluation).get("admission")).get("identity"))
    if not identity:
        return None
    return {str(key): identity[key] for key in sorted(identity, key=str)}


def _evidence_identity(inputs: Mapping[str, Any]) -> Dict[str, Any]:
    """来源摘要：投影实际读过的产物文件 + 逐文件**字节**摘要 + 合成摘要。

    下游（M1 读取闸门）据此从盘上重算：反馈生成之后产物被改写/替换即不一致，
    于是不能只信产物自身的布尔声明。`rel` 相对评估目录（路径被搬走时仍可解析）。
    """

    eval_dir = Path(inputs["eval_dir"]) if inputs.get("eval_dir") else None
    entries: List[Dict[str, Any]] = []

    def _add(kind: str, path: Any) -> None:
        if path is None:
            return
        candidate = Path(path)
        if not candidate.is_file():
            return
        if any(entry["path"] == str(candidate) for entry in entries):
            return
        rel = None
        if eval_dir is not None:
            try:
                rel = os.path.relpath(str(candidate), str(eval_dir))
            except ValueError:
                rel = None
        entries.append({"kind": kind, "path": str(candidate), "rel": rel,
                        "sha256": _sha256_bytes(candidate.read_bytes())})

    _add("evaluation", inputs.get("evaluation_path"))
    _add("summary_statistics", inputs.get("summary_statistics_path"))
    _add("selection_notes", inputs.get("selection_notes_path"))
    for panel in list(inputs.get("panels") or []) + \
            list(inputs.get("panels_unbound") or []):
        paths = list(panel.get("document_paths") or ())
        if not paths:
            paths = [panel.get("statistics_path") or panel.get("path")]
        for path in paths:
            _add("natural_panel", path)
    for entry in inputs.get("opportunity_panels") or []:
        _add("opportunity_panel", entry.get("path"))
    _add("candidate_source", inputs.get("candidate_source"))
    entries.sort(key=lambda entry: entry["path"])
    return {
        "algorithm": "sha256(文件字节) + 相对评估目录的路径；合成摘要对排序后的清单取 sha256",
        "files": entries,
        "digest": _sha256_text(json.dumps(
            [{"kind": e["kind"], "rel": e["rel"], "sha256": e["sha256"]}
             for e in entries], ensure_ascii=False, sort_keys=True)),
    }


def _scan_sources(inputs: Mapping[str, Any]) -> List[Tuple[Any, Any, str]]:
    """投影**实际读过**的全部文档（含原始样本与独立 JSONL），供用途扫描。

    与旧实现的差别（复审 R8 §6 F1）：自然面板不再只交 `statistics`——整份
    `panel.json`（含正在渲染的 `samples` 与 `config/identity/cost`）都在扫描范围内；
    独立 `samples.jsonl` 逐行扫描（定位前缀 `/line/<i>`）；未绑定的面板同样扫描
    （它们已被解析过，属于"实际读取文档"）。
    """

    documents: List[Tuple[Any, Any, str]] = []
    seen: List[str] = []

    def _add(path: Any, document: Any, prefix: str = "") -> None:
        if path is None:
            return
        key = "{0}#{1}".format(path, prefix)
        if key in seen:
            return
        seen.append(key)
        documents.append((path, document, prefix))

    if inputs.get("evaluation_path"):
        _add(Path(inputs["evaluation_path"]), inputs.get("evaluation"))
    for panel in list(inputs.get("panels") or []) + \
            list(inputs.get("panels_unbound") or []):
        sources = panel.get("scan_documents")
        if sources:
            for entry in sources:
                _add(Path(entry["artifact"]), entry["document"],
                     str(entry.get("prefix") or ""))
            continue
        path = Path(panel.get("statistics_path") or panel.get("path"))
        _add(path, _mapping(panel.get("statistics")))
        for index, row in enumerate(panel.get("samples") or ()):
            _add(path, row, "/line/{0}".format(index))
    for entry in inputs.get("opportunity_panels") or []:
        _add(Path(entry["path"]), entry["data"])
    if inputs.get("summary_statistics_path"):
        _add(Path(inputs["summary_statistics_path"]),
             inputs.get("summary_statistics"))
    if inputs.get("selection_notes_path"):
        _add(Path(inputs["selection_notes_path"]),
             inputs.get("selection_notes") or {})
    return documents


def _mechanism_projection(source_path: Optional[Path], source_note: str,
                          fields: Sequence[str], parent_cid: Optional[str],
                          candidate_cid: Optional[str]) -> Dict[str, Any]:
    """第三段：只产槽位（trace 字段 + 父代差异方向占位符），不产内容、不填数值。

    **字段名 ≠ 读数**：`fields` 是程序从候选源码的 trace 字面量里扫出的**槽位名**；
    程序没有这些字段的任何实际读数（本批产物不采集 trace 读数），因此不得把它们
    当成"已采集的事实"引用（复审 §4 A5）。
    """

    lines = [MECHANISM_RULE, "", FIELD_NOT_READING_NOTE, ""]
    if source_path is not None:
        lines.append("- 槽位来源：候选源码 `{0}`（{1}）".format(source_path, source_note))
        fields_source = "candidate_source={0}".format(source_path)
    else:
        lines.append("- 槽位来源：**未绑定候选源码**（{0}）".format(source_note))
        fields_source = "unbound_candidate_source（{0}）".format(source_note)
    lines.append("- 候选 trace 字段（程序从源码 trace 字面量扫出{0}）：".format(
        "" if source_path is not None and fields else "，或退回合同类别"))
    if fields:
        for field in fields:
            lines.append("  - `{0}`".format(field))
    else:
        for slot in TRACE_SLOT_FALLBACK:
            lines.append("  - {0}（合同类别槽位，非实测字段名）".format(slot))
    lines.append("")
    lines.append("**父代差异方向槽位（逐条填写；方向只写 增大 / 减小 / 不变 / 无法判断）**")
    parent = parent_cid or "（无父代：首代 I1，方向槽位填「无父代」）"
    candidate = _short(candidate_cid)
    slots = list(fields) if fields else list(TRACE_SLOT_FALLBACK)
    for field in slots:
        lines.append(
            "- `{0}`：候选 {1} 相对父代 {2} 的方向 = ____；引用窗口 "
            "source_root_id = ____；该字段在该窗口的实际读数 = ____"
            "（程序未采集该读数；填不出就写「未采集」）".format(
                field, candidate, parent))
    lines.append("")
    lines.append("**其余必填槽位**")
    lines.append("- 关联窗口：本假设由哪些 `source_root_id`（含情景 H/M）支撑 = ____；"
                 "反例窗口 = ____")
    lines.append("- 与第二段数字的关系（点估计与区间方向，不得只挑有利根）= ____")
    lines.append("- 预计反例失效面（什么局面下本机制不该生效）= ____")
    lines.append("- 下一版有界改动（M1 用；一次一个机制、可判定成败）= ____ 提出人 = ____")
    return {
        "rule": MECHANISM_RULE,
        "fields": list(slots),
        "fields_source": fields_source,
        "readings_collected": False,
        "readings_note": FIELD_NOT_READING_NOTE,
        "direction_slots": len(slots),
        "text": "\n".join(lines),
    }


# ---------------------------------------------------------------------------
# 5. 组装与入口
# ---------------------------------------------------------------------------


def collect_feedback_inputs(eval_dir: Path, *, parent_cid: Optional[str],
                            candidate_cid: Optional[str],
                            usage_manifest_path: Optional[Path] = None,
                            usage_manifest: Optional[Mapping[str, str]] = None
                            ) -> Dict[str, Any]:
    """读取并整理反馈输入（供 generate_feedback 与主状态机 summary 复用）。

    输入只读产物：
    - `evaluation.json`（条件面板：身份 / 双臂 / 统计 / 准入投影）；
    - `panel-<谓词>/panel.json`（机会面板：逐场景 snapshot = 窗口、触发与未知掩码、
      合法动作前缀、成本账、失败面）；
    - `natural-<H|M>/panel.json`（自然面板：身份 / 配置 / 成本 / 逐窗口样本）；
    - `summary/statistics.json`（主状态机写出的**已验证**根级统计，优先于原始产物的
      自制统计）；
    - `summary/selection-notes.json`（选留排除/去重计数）；
    - 候选 `candidate.py`（**只用于扫出 trace 槽位名**，不是读数来源）。

    `usage_manifest_path` / `usage_manifest`：冻结的根用途清单（Q2/T13）。给出时
    产物的用途声明必须与清单一致，且清单里的确认根不得出现在任何产物中；两者都不给
    时自动发现 `<eval_dir>/root-usage.json`（没有清单则退化为"以产物自报为准"，
    但词表外的用途词与自相冲突的声明**同样拒绝**）。

    绑不上身份时把拒绝码放进 `refusals`，由投影统一判定可执行性；**产物的根用途
    扫描在任何渲染/汇总之前完成**（见 `_scan_usage_documents`）。
    """

    eval_dir = Path(eval_dir)
    if not eval_dir.is_dir():
        raise FeedbackInputError("评估目录不存在：{0}".format(eval_dir))
    manifest_path = usage_manifest_path
    if manifest_path is None and usage_manifest is None:
        for name in ("root-usage.json", "usage-manifest.json"):
            if (eval_dir / name).is_file():
                manifest_path = eval_dir / name
                break
    if usage_manifest is not None:
        resolved_manifest: Optional[Dict[str, str]] = {
            str(key): str(value) for key, value in dict(usage_manifest).items()}
    elif manifest_path is not None:
        resolved_manifest = _read_usage_manifest(Path(manifest_path))
    else:
        resolved_manifest = None
    evaluation_path = _discover_evaluation(eval_dir, candidate_cid)
    evaluation = _load_json(evaluation_path) if evaluation_path else None
    discovered = _discover_natural_panels(eval_dir)
    discovered_opportunity = _discover_opportunity_panels(eval_dir)
    opportunity_panels, opportunity_note = _select_opportunity_panels(
        evaluation_path, discovered_opportunity)
    if evaluation is None and not discovered and not discovered_opportunity:
        raise FeedbackInputError(
            "评估目录没有任何可读产物（找过 evaluation.json / panel.json / "
            "samples.jsonl）：{0}".format(eval_dir))
    refusals: List[Dict[str, str]] = []
    panels, binding_note, binding_refusal = _select_panels(
        discovered, evaluation, candidate_cid)
    if binding_refusal:
        refusals.append(binding_refusal)
    # 自然面板历史上可按源码绑定条件结果，研究配置必须另外相同，不能只看源码。
    import sitin_execution_profile as execution_profiles
    profile_documents = ([evaluation] if evaluation is not None else []) + [
        entry.get("document") or {} for entry in panels]
    selected_profile = None
    for document in profile_documents:
        value = document.get("candidate_execution_profile",
            _mapping(document.get("identity")).get("candidate_execution_profile"))
        try:
            current_profile = execution_profiles.resolve(value)
            if selected_profile is not None:
                execution_profiles.require_same(current_profile, selected_profile)
            selected_profile = current_profile
        except ValueError as error:
            raise FeedbackInputError("反馈执行配置不一致：" + str(error)) from error
    # 未绑定的面板**不进反馈数字**，但仍作为"目录里存在哪些产物"的事实来源
    # （只用于条目证据兜底，绝不参与任何读数）。
    unbound_panels = [panel for panel in discovered if panel not in panels]
    # 某一个情景的面板绑不上（同目录里别的候选面板属正常多代目录，不算）：
    # 若该情景**只有**未绑定的面板可用，则该情景的证据缺失 → 拒绝绑定。
    bound_mixes = {str(panel.get("mix") or "") for panel in panels}
    orphan_mixes = sorted({str(panel.get("mix") or "") for panel in unbound_panels}
                          - bound_mixes)
    if orphan_mixes:
        refusals.append(_refusal(
            REFUSAL_IDENTITY_PANELS,
            "情景 {0} 的自然面板绑不上本次候选（面板登记的 "
            "candidate_source_sha256 与产物登记的候选不符）：拒绝绑定，"
            "未绑定面板数字不进反馈".format("、".join(orphan_mixes))))
    digests = _collect_source_digests(evaluation, panels)
    source_path, source_note, source_refusal = _find_candidate_source(eval_dir, digests)
    if source_refusal:
        refusals.append(source_refusal)
    fields: List[str] = []
    source_text: Optional[str] = None
    if source_path is not None:
        source_text = source_path.read_text(encoding="utf-8")
        fields = trace_field_slots(source_text)
    summary_path = eval_dir / "summary" / "statistics.json"
    summary_statistics = _load_json(summary_path) if summary_path.is_file() else None
    notes_path, selection_notes = _load_selection_notes(eval_dir)
    if evaluation is not None and candidate_cid:
        recorded = str(_mapping(evaluation.get("identity")).get("candidate_id") or "")
        if recorded and recorded != str(candidate_cid):
            refusals.append(_refusal(
                REFUSAL_IDENTITY_EVALUATION,
                "条件评估产物登记的候选身份 {0} 与本次候选 {1} 不符：拒绝绑定".format(
                    _short(recorded), _short(candidate_cid))))
    inputs: Dict[str, Any] = {
        "eval_dir": eval_dir,
        "evaluation_path": evaluation_path,
        "evaluation": evaluation,
        "panels": panels,
        "panels_unbound": unbound_panels,
        "panel_binding_note": binding_note,
        "natural_panels_found": len(discovered),
        "candidate_source": source_path,
        "candidate_source_note": source_note,
        "candidate_source_sha256": (_sha256_text(source_text)
                                    if source_text is not None else None),
        "candidate_source_file_sha256": (_sha256_bytes(source_path.read_bytes())
                                         if source_path is not None else None),
        "trace_fields": fields,
        "parent_cid": parent_cid,
        "candidate_cid": candidate_cid,
        "opportunity_panels": opportunity_panels,
        "opportunity_panels_found": len(discovered_opportunity),
        "opportunity_binding_note": opportunity_note,
        "summary_statistics_path": (summary_path if summary_path.is_file() else None),
        "summary_statistics": summary_statistics,
        "selection_notes_path": notes_path,
        "selection_notes": selection_notes,
        "usage_manifest": resolved_manifest,
        "usage_manifest_path": (Path(manifest_path) if manifest_path else None),
        "refusals": refusals,
    }
    # 用途扫描：**在任何渲染/汇总之前**跑完整实际读取文档（R9/P5 F1）。
    inputs["usage_scan"] = _scan_usage_documents(_scan_sources(inputs),
                                                 manifest=resolved_manifest)
    return inputs


def _summary_identity_refusals(summary_statistics: Optional[Mapping[str, Any]],
                               summary_path: Optional[Path],
                               candidate_cid: Optional[str]
                               ) -> List[Dict[str, str]]:
    """汇总结算产物（`summary/statistics.json`）的候选身份必须**精确命中**本次候选。

    复审 R8 §6 F2：summary 正是"唯一候选回退"的入口——只有外来候选时旧实现直接采用
    它。这里独立判一次：summary 存在但键集合不含本次候选 → 拒绝（不猜、不回退）。
    """

    if not summary_statistics or not candidate_cid:
        return []
    by_candidate = _mapping(_mapping(summary_statistics).get("by_candidate"))
    if not by_candidate or str(candidate_cid) in by_candidate:
        return []
    return [_refusal(
        REFUSAL_IDENTITY_STATISTICS,
        "汇总统计 {0} 含 {1} 个候选且不含本次候选 {2}：拒绝绑定（不回退到唯一候选，"
        "也不采用它的任何数字）".format(
            _name_of(summary_path), len(by_candidate), _short(candidate_cid)))]


def _reading_refusals(evaluation: Optional[Mapping[str, Any]],
                      eval_path: Optional[Path],
                      candidate_cid: Optional[str],
                      blocks: Mapping[str, Mapping[str, Any]]) -> List[Dict[str, str]]:
    """缺读数拒绝：本批该报的数字缺失或为 null 时，**不得**当成事实喂给模型。

    逐条判据（全部读自产物）：
    - 无条件评估产物 / 统计块为空 → `reading.statistics_missing`；
    - 统计块里有多个候选却对不上本次候选 → `identity.statistics_candidate_ambiguous`；
    - 被评谓词的面板块缺失 → `reading.statistics_missing`；
    - 面板块的 n_roots / mean_delta / status 任一为 null → `reading.numbers_missing`
      （R6 缺陷正是这三个 null 被渲染进 M1 提示词）；
    - 双臂读数缺失（无 arms / 无 status / U 与 U 区间全缺）→ `reading.arms_missing`。
    """

    refusals: List[Dict[str, str]] = []
    if evaluation is None or eval_path is None:
        refusals.append(_refusal(REFUSAL_READING_STATISTICS_MISSING,
                                 "本目录没有条件评估产物：无可核对的条件面板读数"))
        return refusals
    statistics = _mapping(evaluation.get("statistics"))
    by_candidate = _mapping(statistics.get("by_candidate"))
    if not statistics or not by_candidate:
        refusals.append(_refusal(
            REFUSAL_READING_STATISTICS_MISSING,
            "产物 statistics 缺 by_candidate（{0}）：本批无根级读数".format(
                eval_path.name)))
    elif candidate_cid and str(candidate_cid) not in by_candidate:
        if len(by_candidate) > 1:
            refusals.append(_refusal(
                REFUSAL_IDENTITY_STATISTICS,
                "统计块含 {0} 个候选且不含本次候选 {1}：不猜（拒绝绑定）".format(
                    len(by_candidate), _short(candidate_cid))))
        else:
            refusals.append(_refusal(
                REFUSAL_IDENTITY_STATISTICS,
                "统计块唯一候选 {0} 与本次候选 {1} 不符：拒绝绑定".format(
                    _short(sorted(by_candidate)[0]), _short(candidate_cid))))
    predicate = str(_mapping(evaluation.get("panel")).get("predicate") or "")
    entry = blocks.get(predicate) if predicate else None
    if predicate and (entry is None or not entry.get("mixes")):
        refusals.append(_refusal(
            REFUSAL_READING_STATISTICS_MISSING,
            "产物里没有被评谓词 `{0}` 的面板块：本批无条件面板读数".format(predicate)))
    for name, slot in sorted(
            (entry or {}).get("mixes", {}).items() if entry else []):
        block = _mapping(slot.get("block"))
        missing = [field for field in ("n_roots", "mean_delta", "status")
                   if block.get(field) is None]
        if missing:
            refusals.append(_refusal(
                REFUSAL_READING_NUMBERS_MISSING,
                "面板块 `{0}`/{1} 的 {2} 为 null（产物未给读数）：不得当事实"
                "渲染进任务包".format(predicate, name, "、".join(missing))))
    arms = _mapping(_mapping(evaluation.get("double_arm")).get("arms"))
    if not arms:
        refusals.append(_refusal(REFUSAL_READING_ARMS_MISSING,
                                 "产物无 double_arm.arms：双臂读数缺失"))
    else:
        for name in ("baseline", "candidate"):
            arm = _mapping(arms.get(name))
            has_u = any(_is_number(arm.get(field))
                        for field in ("u", "u_low", "u_high"))
            if not arm or arm.get("status") is None or not has_u:
                refusals.append(_refusal(
                    REFUSAL_READING_ARMS_MISSING,
                    "臂 {0} 缺 status 或 U/U 区间读数（status={1}）：不得当事实".format(
                        name, arm.get("status") if arm else "（缺该臂）")))
    return refusals


def _execution_scope_items(eval_path, evaluation, panels):
    """把研究配置与内部失败原值送入作者反馈；缺审计不推断为零或发布通过。"""
    documents = [(eval_path, evaluation)] if evaluation is not None and eval_path is not None else []
    documents += [(entry.get("path"), entry.get("document")) for entry in panels]
    items = []
    for path, document in documents:
        if path is None or not isinstance(document, Mapping):
            continue
        location = (("candidate_execution_profile",) if "candidate_execution_profile" in document
                    else ("identity", "candidate_execution_profile"))
        profile = document.get("candidate_execution_profile") or _mapping(document.get("identity")).get("candidate_execution_profile")
        if profile is None:
            continue
        items.append(_item("execution.profile", SEGMENT_FACTS,
            "候选执行配置（计数上限，不是毫秒）：{0}。研究成绩不代表发布通过，"
            "不得与另一额度的成绩混用。".format(json.dumps(profile, ensure_ascii=False, sort_keys=True)),
            _evs(path, document, location)))
        arms = _mapping(_mapping(document.get("double_arm")).get("arms"))
        for name, arm in arms.items():
            review = _mapping(arm).get("execution_review")
            if review is not None:
                items.append(_item("execution.conditional." + name, SEGMENT_FACTS,
                    "条件{0}臂内部评分诊断：{1}。计数范围为截取窗口之后及剩余桌。".format(
                        name, json.dumps(review, ensure_ascii=False, sort_keys=True)),
                    _evs(path, document, ("double_arm", "arms", name, "execution_review"))))
        if "execution_review" in document:
            items.append(_item("execution.natural", SEGMENT_FACTS,
                "自然面板内部评分诊断：{0}。驱动fallbacks不能替代内部失败计数。".format(
                    json.dumps(document["execution_review"], ensure_ascii=False, sort_keys=True)),
                _evs(path, document, ("execution_review",))))
    return items


def build_feedback_projection(inputs: Mapping[str, Any]) -> Dict[str, Any]:
    """把整理好的输入投影成三段反馈（程序化、可对账、带可执行性判定）。

    返回结构（`PROJECTION_SCHEMA`）：

    - `status` / `executable` / `refusals` / `gaps`：可执行性与拒绝/缺口清单；
    - `facts` / `associated_results` / `mechanism_hypothesis` / `boundary`：
      与旧 JSON 键逐字兼容（下游 sitin_generate 按这三键渲染提示词）；
    - `facts_items` / `result_items`：逐条
      条目（key / text / root_id / window /
      evidence / extra_evidences），每条都能在产物里逐项对账；
    - `mechanism_slots`：机制槽位（字段名来自源码扫描，**不是读数**）；
    - `reconciliation`：对账表（条目 → 产物 → 定位 → 原值）。
    """

    candidate_cid = inputs.get("candidate_cid")
    parent_cid = inputs.get("parent_cid")
    evaluation = inputs.get("evaluation")
    eval_path = inputs.get("evaluation_path")
    panels = list(inputs.get("panels") or [])
    opportunity_panels = list(inputs.get("opportunity_panels") or [])
    refusals = list(inputs.get("refusals") or [])
    gaps: List[Dict[str, str]] = []
    # —— 边界优先（复审 R8 §6 F1）：**在任何渲染/汇总之前**扫描完整实际读取文档。
    #    确认用途或未冻结用途一旦命中，立刻返回"只带诊断定位"的拒绝投影：三段正文、
    #    条目与对账表一律不渲染，确认结果因此不会被复制进反馈或任务包。
    scan = inputs.get("usage_scan")
    if not isinstance(scan, Mapping):
        scan = _scan_usage_documents(_scan_sources(inputs),
                                     manifest=inputs.get("usage_manifest"))
    boundary = _usage_refusal_details(scan)
    if boundary:
        return _boundary_refused_projection(inputs, scan, refusals + boundary)
    facts_items = _conditional_fact_items(eval_path, evaluation) \
        if evaluation is not None and eval_path is not None else []
    window_items, window_gaps = _window_fact_items(Path(inputs["eval_dir"]),
                                                   opportunity_panels)
    facts_items += window_items
    gaps += window_gaps
    if inputs.get("opportunity_binding_note"):
        gaps.append(_gap("window.opportunity_panel_unbound",
                         str(inputs["opportunity_binding_note"])))
    fallback_path = _json_fallback_path(
        eval_path,
        [Path(entry["path"]) for entry in opportunity_panels],
        [Path(panel.get("statistics_path") or panel.get("path")) for panel in panels],
        [Path(panel.get("statistics_path") or panel.get("path"))
         for panel in (inputs.get("panels_unbound") or [])])
    facts_items += _natural_fact_items(panels, fallback_path)
    facts_items += _cost_failure_items(eval_path, evaluation, opportunity_panels,
                                       panels)
    facts_items += _execution_scope_items(eval_path, evaluation, panels)
    facts_items += _selection_note_items(inputs.get("selection_notes_path"),
                                         inputs.get("selection_notes") or {})
    blocks = _collect_result_blocks(eval_path, evaluation, panels,
                                    inputs.get("summary_statistics_path"),
                                    inputs.get("summary_statistics"), candidate_cid)
    result_items, result_gaps = _result_items(blocks, evaluation, eval_path,
                                              fallback_path, panels)
    gaps += result_gaps
    side_items, side_gaps = _family_side_items(blocks)
    result_items += side_items
    gaps += side_gaps
    refusals += _reading_refusals(evaluation, eval_path, candidate_cid, blocks)
    refusals += _summary_identity_refusals(
        inputs.get("summary_statistics"), inputs.get("summary_statistics_path"),
        candidate_cid)
    mechanism = _mechanism_projection(
        inputs.get("candidate_source"),
        str(inputs.get("candidate_source_note") or ""),
        list(inputs.get("trace_fields") or []), parent_cid, candidate_cid)
    status = PROJECTION_REFUSED if refusals else PROJECTION_OK
    facts = [item["text"] for item in facts_items]
    results = [item["text"] for item in result_items]
    projection: Dict[str, Any] = {
        "schema": PROJECTION_SCHEMA,
        "status": status,
        "executable": status == PROJECTION_OK,
        "refusals": refusals,
        "gaps": gaps,
        "identity": {
            "candidate_id": candidate_cid,
            "parent_id": parent_cid,
            "evaluation_id": _mapping(_mapping(evaluation).get("identity"))
            .get("evaluation_id"),
            "evaluation_path": str(eval_path) if eval_path else None,
            "candidate_source": (str(inputs.get("candidate_source"))
                                 if inputs.get("candidate_source") else None),
            "panel_binding": inputs.get("panel_binding_note"),
            "source_binding": inputs.get("candidate_source_note"),
            "summary_statistics_path": (str(inputs.get("summary_statistics_path"))
                                        if inputs.get("summary_statistics_path")
                                        else None),
            # —— R9/P5（复审 R8 §6 F2）：身份不再只是"调用方给的字符串"。
            #    source_sha256 是**绑定到的候选源码内容**摘要（与产物登记的
            #    candidate_source_sha256 同口径）；source_file_sha256 是同一份源码
            #    的**文件字节**摘要（与父代产物 record 的 code_sha256 同口径）——
            #    下游 M1 用后者与父代实际产物逐字节核对。
            "source_sha256": inputs.get("candidate_source_sha256"),
            "source_file_sha256": inputs.get("candidate_source_file_sha256"),
            # 准入身份（P4/M1 起含 materials_sha256 / executor_version / thresholds）：
            # 原样带入，供消费端按字段核对，而不是只信 executable 布尔。
            "admission": _admission_identity(evaluation),
            # 来源摘要：投影实际读过的产物清单 + 逐文件字节摘要 + 合成摘要。
            "evidence": _evidence_identity(inputs),
        },
        SEGMENT_FACTS: facts,
        SEGMENT_RESULTS: results,
        SEGMENT_MECHANISM: mechanism["text"],
        "boundary": (
            "未做单动作反事实实验；反馈只含开发结果与来源根/窗口，**不含确认集数据**"
            "（确认根不进入任务包、生成反馈、参数拟合与开发挑选）。程序不推算、不补零、"
            "不判定优胜。"),
        "facts_items": facts_items,
        "result_items": result_items,
        "mechanism_slots": mechanism,
        # 扫描摘要（正常投影也留证）：扫了哪些文档、命中几个、是否完整。
        "usage_scan": {
            "documents": list(scan.get("documents") or []),
            "confirmation_hits": len(scan.get("confirmation") or []),
            "unknown_hits": len(scan.get("unknown") or []),
            "nodes": int(scan.get("nodes") or 0),
            "truncated": bool(scan.get("truncated")),
        },
        "reconciliation": [
            {"key": item["key"], "text": item["text"],
             "artifact": item["evidence"]["artifact"],
             "locator": item["evidence"]["locator"],
             "value": item["evidence"]["value"],
             "root_id": item["root_id"], "window": item["window"],
             "extra": [{"artifact": extra["artifact"], "locator": extra["locator"],
                        "value": extra["value"]}
                       for extra in item["extra_evidences"]]}
            for item in facts_items + result_items
        ],
    }
    return projection


#: 边界拒绝（确认用途 / 未冻结用途）时的机制段正文：只有诊断，没有内容。
BOUNDARY_MECHANISM_NOTE = (
    "【本反馈因根用途边界被拒：三段正文与机制槽位一律不渲染——不把任何产物内容、"
    "样本、数字或根名复制进反馈或任务包；诊断见 refusals（哪份文档、哪个字段、哪条"
    "JSON 路径）】")

#: 边界拒绝时的 boundary 声明（与正常投影同一句话加边界说明）。
BOUNDARY_REFUSED_NOTE = (
    "根用途边界拒绝：产物中存在确认用途或未冻结用途的根，反馈**不渲染任何内容**，"
    "只保留诊断定位；确认结果不进任务包、生成反馈、参数拟合与开发挑选。")


def _boundary_refused_projection(inputs: Mapping[str, Any],
                                 scan: Mapping[str, Any],
                                 refusals: Sequence[Mapping[str, str]]
                                 ) -> Dict[str, Any]:
    """边界拒绝的投影：**只暴露诊断定位**，不复制确认结果。

    三段正文（facts / associated_results / mechanism_hypothesis）、逐条 item、对账表
    一律为空——确认用途命中后，程序无法证明任何汇总（均值、声明混合）不含确认根，
    因此按 fail-closed 全部不渲染。
    """

    return {
        "schema": PROJECTION_SCHEMA,
        "status": PROJECTION_REFUSED,
        "executable": False,
        "refusals": list(refusals),
        "gaps": [],
        "identity": {
            "candidate_id": inputs.get("candidate_cid"),
            "parent_id": inputs.get("parent_cid"),
            "evaluation_path": (str(inputs.get("evaluation_path"))
                                if inputs.get("evaluation_path") else None),
            "summary_statistics_path": (
                str(inputs.get("summary_statistics_path"))
                if inputs.get("summary_statistics_path") else None),
            "boundary_refused": True,
        },
        SEGMENT_FACTS: [],
        SEGMENT_RESULTS: [],
        SEGMENT_MECHANISM: BOUNDARY_MECHANISM_NOTE,
        "boundary": BOUNDARY_REFUSED_NOTE,
        "facts_items": [],
        "result_items": [],
        "mechanism_slots": {
            "rule": MECHANISM_RULE, "fields": [], "fields_source": "boundary_refused",
            "readings_collected": False, "readings_note": FIELD_NOT_READING_NOTE,
            "direction_slots": 0, "text": BOUNDARY_MECHANISM_NOTE},
        "reconciliation": [],
        # 扫描摘要：只报计数与文档清单（回答"扫了哪些文档"），不复制用途内容。
        "usage_scan": {
            "documents": list(scan.get("documents") or []),
            "confirmation_hits": len(scan.get("confirmation") or []),
            "unknown_hits": len(scan.get("unknown") or []),
            "nodes": int(scan.get("nodes") or 0),
            "truncated": bool(scan.get("truncated")),
        },
    }


AUTHOR_FEEDBACK_MODES = ("full_v1", "compact_prefix_v1")


def author_feedback_mode(value: Any = None) -> str:
    """验证作者正文渲染版本；缺省沿用完整正文，未知版本在计费前拒绝。"""
    mode = "full_v1" if value is None else value
    if not isinstance(mode, str) or mode not in AUTHOR_FEEDBACK_MODES:
        raise FeedbackInputError("未知 author_feedback_mode：{0!r}".format(value))
    return mode


def _compact_action_prefix(item: Mapping[str, Any]) -> str:
    """只替换可与结构化证据逐字对账的长前缀；两臂动作及缺失说明原样保留。"""
    text = item["text"]
    evidences = [item.get("evidence")] + list(item.get("extra_evidences") or [])
    matches = [e for e in evidences if isinstance(e, Mapping)
               and str(e.get("locator", "")).endswith("/snapshot/legal_action_prefix")]
    if len(matches) != 1:
        raise FeedbackInputError("前缀压缩要求唯一 legal_action_prefix 证据")
    evidence = matches[0]
    prefix = evidence.get("value")
    if not isinstance(prefix, list) or not isinstance(evidence.get("artifact"), str):
        raise FeedbackInputError("前缀证据必须含动作数组及来源产物")
    counts: Dict[str, int] = {}
    rendered: List[str] = []
    for step in prefix:
        if (not isinstance(step, Mapping) or not isinstance(step.get("window_key"), Mapping)
                or not isinstance(step.get("action_key"), str) or not step["action_key"]):
            raise FeedbackInputError("前缀动作缺少窗口或动作键，不能静默略去")
        action = step["action_key"]
        family = action.split(":", 1)[0]
        counts[family] = counts.get(family, 0) + 1
        rendered.append("{0}→{1}".format(
            json.dumps(step["window_key"], ensure_ascii=False, sort_keys=True), action))
    detail = "（逐座位 window_key→action_key，共 {0} 步）：{1}".format(
        len(prefix), "；".join(rendered) or "（空：截取窗口就是前缀起点）")
    if text.count(detail) != 1:
        raise FeedbackInputError("前缀正文与结构化证据不一致，拒绝压缩")
    # 短前缀无需摘要；避免用更长的定位/摘要信息替代少量原文。
    if len(detail) <= 2048:
        return text
    digest = _sha256_bytes(json.dumps(prefix, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode("utf-8"))
    summary = (
        "（作者前缀摘要 compact_prefix_v1；共 {0} 步）：动作族计数={1}；"
        "有序前缀规范JSON SHA256={2}；原始证据={3}#{4}。"
        "完整逐步轨迹保留在审计产物，未随本正文传递；摘要不替代截取窗口的两臂动作读数。"
    ).format(len(prefix), json.dumps(counts, ensure_ascii=False, sort_keys=True),
             digest, evidence["artifact"], evidence["locator"])
    return text.replace(detail, summary, 1)


def author_projection_segments(projection: Mapping[str, Any], *,
                               mode: Any = None) -> Dict[str, str]:
    """从已通过消费检查的开发反馈生成作者正文，不修改原投影或结果/机制段。

    完整模式与历史渲染逐字相同。压缩模式要求可执行投影及逐条事实一致；
    仅长动作前缀按结构证据压缩，失败不回退成另一份未声明提示。
    """
    selected = author_feedback_mode(mode)
    if selected == "full_v1":
        return projection_segments(projection)
    if (projection.get("status") != PROJECTION_OK or projection.get("executable") is not True
            or projection.get("refusals")):
        raise FeedbackInputError("不可执行反馈不得生成压缩作者正文")
    items = projection.get("facts_items")
    if not isinstance(items, list) or any(
            not isinstance(i, Mapping) or not isinstance(i.get("text"), str) for i in items):
        raise FeedbackInputError("压缩作者正文缺 facts_items")
    if projection.get(SEGMENT_FACTS) != [i.get("text") for i in items]:
        raise FeedbackInputError("事实正文与逐条投影不一致，拒绝压缩")
    facts = [_compact_action_prefix(i) if i.get("key") == "window.actions" else i["text"]
             for i in items]
    rendered = projection_segments(dict(projection, **{SEGMENT_FACTS: facts}))
    source_digest = _sha256_bytes(json.dumps(projection, ensure_ascii=False, sort_keys=True,
                                            separators=(",", ":")).encode("utf-8"))
    rendered[SEGMENT_FACTS] = (
        "【作者反馈渲染 compact_prefix_v1；原投影规范JSON SHA256=" + source_digest + "】\n"
        + rendered[SEGMENT_FACTS])
    return rendered


def projection_segments(projection: Mapping[str, Any]) -> Dict[str, str]:
    """把投影渲染成提示词三段文本（`sitin_generate` 按字符串渲染）。

    与旧 JSON 键同名同序：`facts` / `associated_results` / `mechanism_hypothesis`。
    拒绝时在开头写明拒绝码——**调用方必须先看 `executable` 再决定是否发任务**。
    """

    lines: List[str] = []
    if projection.get("status") != PROJECTION_OK or not projection.get("executable"):
        lines.append("【本反馈不可执行：{0}】".format(
            "；".join("{0}={1}".format(item.get("code"), item.get("detail"))
                     for item in projection.get("refusals") or []) or "（未给拒绝原因）"))
    facts = list(projection.get(SEGMENT_FACTS) or [])
    results = list(projection.get(SEGMENT_RESULTS) or [])
    gaps = list(projection.get("gaps") or [])
    if gaps:
        facts = facts + ["- 输入缺口（程序如实标注，未补造读数）：{0}".format(
            "；".join("{0}={1}".format(item.get("code"), item.get("detail"))
                     for item in gaps))]
    return {
        SEGMENT_FACTS: "\n".join(str(line) for line in facts),
        SEGMENT_RESULTS: "\n".join(str(line) for line in results),
        SEGMENT_MECHANISM: str(projection.get(SEGMENT_MECHANISM) or ""),
    }


def build_feedback_document(inputs: Mapping[str, Any]) -> str:
    """把整理好的输入渲染成三段反馈 Markdown（同输入逐字节确定）。"""

    projection = build_feedback_projection(inputs)
    candidate_cid = inputs.get("candidate_cid")
    parent_cid = inputs.get("parent_cid")
    evaluation = inputs.get("evaluation")
    eval_path = inputs.get("evaluation_path")
    panels = inputs.get("panels") or []
    refusal_lines = ["**可执行性**：{0}（拒绝 {1} 条；缺口 {2} 条）".format(
        "可执行" if projection["executable"] else "**不可执行**",
        len(projection["refusals"]), len(projection["gaps"]))]
    for item in projection["refusals"]:
        refusal_lines.append("- 拒绝 `{0}`：{1}".format(item["code"], item["detail"]))
    for item in projection["gaps"]:
        refusal_lines.append("- 缺口 `{0}`：{1}".format(item["code"], item["detail"]))
    lines: List[str] = [
        "# 三段开发反馈：候选 {0}（父代 {1}）".format(
            _short(candidate_cid), _short(parent_cid) if parent_cid else "无（首代）"),
        "",
        "> schema={0}；由 `tools/sitin_feedback.py generate` 从评估产物程序生成。"
        "第一、二段的所有数字逐项读自产物（`evaluation.json` / "
        "`panel-<谓词>/panel.json` / `natural-*/panel.json` / "
        "`summary/statistics.json`），缺失字段显式标注而不补零；每条都带证据定位，"
        "可追到来源根与窗口；第三段只有槽位，内容由监督者或候选作者填写。"
        "本文件不含确认集数据，也不构成优胜判定。".format(FEEDBACK_SCHEMA),
        "",
        "**读取到的产物**：{0}".format("、".join(
            ["`{0}`".format(path) for path in
             [eval_path, inputs.get("summary_statistics_path"),
              inputs.get("selection_notes_path")]
             + [panel.get("statistics_path") for panel in panels]
             + [entry.get("path") for entry in (inputs.get("opportunity_panels") or [])]
             if path]) or "（无）"),
        "**自然面板绑定**：{0}（目录里共 {1} 份自然面板产物）".format(
            inputs.get("panel_binding_note") or "（未记录）",
            inputs.get("natural_panels_found", len(panels))),
        "**候选源码绑定**：{0}".format(inputs.get("candidate_source_note") or "（未记录）"),
        "",
    ] + refusal_lines + [
        "",
        HEADING_FACTS,
        "",
    ]
    lines += _identity_lines(candidate_cid, parent_cid, evaluation, panels)
    lines.append("")
    lines += list(projection[SEGMENT_FACTS])
    lines += ["", HEADING_RESULTS, ""]
    lines += list(projection[SEGMENT_RESULTS])
    lines += ["", HEADING_MECHANISM, ""]
    lines += projection[SEGMENT_MECHANISM].split("\n")
    return "\n".join(lines) + "\n"


def generate_feedback(eval_dir, *, parent_cid, candidate_cid, out_path,
                      usage_manifest_path=None) -> Path:
    """从评估产物生成三段反馈 Markdown 并写盘；返回写出的路径。

    参数（均为位置/关键字混合，与调用方约定一致）：

    - `eval_dir`：评估产物目录（含 `evaluation.json` 与/或 `natural-*/panel.json`、
      `samples.jsonl`）。只读。
    - `parent_cid`：父代候选身份；首代 I1 传 `None`（程序不替它编父代）。
    - `candidate_cid`：本次候选身份，用于在产物里定位该候选的面板块。
    - `out_path`：Markdown 写出路径（父目录自动创建）。
    - `usage_manifest_path`：可选，冻结根用途清单（Q2/T13）；给出时产物的用途声明
      必须与清单一致，清单里的确认根不得出现在任何产物中。

    错误：产物缺失或不可解析时抛 `FeedbackInputError`（不产出半份反馈）；
    本函数不做模型调用、不跑桌赛、不判定优胜。
    """

    inputs = collect_feedback_inputs(Path(eval_dir), parent_cid=parent_cid,
                                     candidate_cid=candidate_cid,
                                     usage_manifest_path=usage_manifest_path)
    document = build_feedback_document(inputs)
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(document, encoding="utf-8")
    return out


def cmd_generate(args: Any) -> int:
    """CLI：generate 子命令（缺产物即拒绝，退出码 3）。"""

    try:
        manifest_path = (Path(args.usage_manifest) if getattr(
            args, "usage_manifest", None) else None)
        out = generate_feedback(Path(args.eval_dir), parent_cid=args.parent_cid,
                                candidate_cid=args.candidate_cid,
                                out_path=Path(args.out),
                                usage_manifest_path=manifest_path)
    except FeedbackInputError as exc:
        print(json.dumps({"ok": False, "refused": str(exc)}, ensure_ascii=False))
        return 3
    inputs = collect_feedback_inputs(Path(args.eval_dir), parent_cid=args.parent_cid,
                                     candidate_cid=args.candidate_cid,
                                     usage_manifest_path=manifest_path)
    print(json.dumps({
        "ok": True,
        "out": str(out),
        "schema": FEEDBACK_SCHEMA,
        "evaluation": str(inputs["evaluation_path"]) if inputs["evaluation_path"] else None,
        "natural_panels": [str(panel["statistics_path"]) for panel in inputs["panels"]],
        "trace_fields": inputs["trace_fields"],
        "candidate_source": (str(inputs["candidate_source"])
                             if inputs["candidate_source"] else None),
    }, ensure_ascii=False))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="R6 三段开发反馈生成（事实/关联结果由程序从产物读出；机制假设只给槽位）")
    sub = parser.add_subparsers(dest="command", required=True)
    gen = sub.add_parser(
        "generate",
        help="从评估产物生成三段反馈 Markdown（不调模型、不跑桌赛、不判定优胜）")
    gen.add_argument("--eval-dir", required=True,
                     help="评估产物目录（evaluation.json / natural-*/panel.json / samples.jsonl）")
    gen.add_argument("--candidate-cid", default=None, help="本次候选身份（建议给出）")
    gen.add_argument("--parent-cid", default=None,
                     help="父代候选身份；首代 I1 省略（程序不替它编父代）")
    gen.add_argument("--out", required=True, help="写出的 Markdown 路径")
    gen.add_argument("--usage-manifest", default=None,
                     help="可选：冻结根用途清单（sitin-root-usage-manifest/1）；"
                          "给出时产物的用途声明必须与清单一致")
    gen.set_defaults(func=cmd_generate)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args) or 0)


if __name__ == "__main__":
    sys.exit(main())
