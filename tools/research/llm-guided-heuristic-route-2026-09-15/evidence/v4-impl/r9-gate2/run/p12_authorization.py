#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""P12 · 授权形态对齐（Q6 / 裁定 §2 Q6 落实）。

裁定原文：
> 应改成统一、受信的授权身份/范围校验；**不能直接去掉授权约束**。启用新批次前，
> 上下层统一核对授权 ID、允许操作/账户、额度；模型无权改允许标签集，保留失败关闭。

Lead 定义的**新形态**（JSON 字段名照写，双方必须一致）：

```json
{
  "schema": "sitin-authorization/1",
  "authorization_id": "<不透明标识>",
  "batch_label": "<本批运行标签>",
  "trusted": true,
  "allowed_operations": ["natural_panel","conditional_prefix","family_fill",
                         "conditional_refill","evaluate","summarize"],
  "allowed_accounts": {"tables_full": 0,"tables_partial": 0,"prefix_generation": 0,
                       "tokens_input": 0,"tokens_output": 0,"confirm_reserved": 0.0},
  "issued_by": "lead",
  "issued_at_utc": "<ISO8601>"
}
```

旧形态（生产 `_step_natural` / v2 前缀路由的历史门值）：
`{"authorized": true, "batch": 7, "budgets": {...}}`。

本模块**同时支持两种形态**，并给出 `authorization_form` 供审计：
`legacy_batch7` / `sitin-authorization/1` / `dual`（同文档同时带两族字段）。
两族字段都在时**两族都要通过**（任一族不合规即整体拒绝，失败关闭）。
**不允许去掉授权约束**：文档缺失、`trusted != true`、允许操作清单为空、
账户额度非数/为负、`issued_by` 为空、`issued_at_utc` 不是 ISO8601，一律拒绝。
"""
from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/llm-guided-heuristic-route-2026-09-15/evidence/v4-impl/r9-gate2/run'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

from datetime import datetime
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

UNIFIED_SCHEMA = "sitin-authorization/1"
FORM_LEGACY = "legacy_batch7"
FORM_UNIFIED = "sitin-authorization/1"
FORM_DUAL = "dual:legacy_batch7+sitin-authorization/1"
FORM_UNKNOWN = "unknown"

#: 新形态允许的操作清单（Lead 冻结；**模型无权改**，此处是唯一白名单）。
ALLOWED_OPERATIONS: Tuple[str, ...] = (
    "natural_panel", "conditional_prefix", "family_fill", "conditional_refill",
    "evaluate", "summarize")

#: 账户名（两种形态共用同一组名字：legacy 的 `budgets` 与新形态的 `allowed_accounts`）。
ACCOUNTS: Tuple[str, ...] = (
    "tables_full", "tables_partial", "prefix_generation", "tokens_input",
    "tokens_output", "confirm_reserved")

#: 生产侧历史门值（`_step_natural` / v2 前缀路由的判据是 batch == 7）。
LEGACY_BATCH_VALUE = 7


def _parse_iso8601(text: Any) -> Optional[datetime]:
    raw = str(text or "").strip()
    if not raw:
        return None
    candidate = raw[:-1] + "+00:00" if raw.endswith("Z") else raw
    try:
        return datetime.fromisoformat(candidate)
    except ValueError:
        return None


def _clean_accounts(block: Mapping[str, Any]) -> Tuple[Dict[str, float], List[str]]:
    out: Dict[str, float] = {}
    problems: List[str] = []
    for account in ACCOUNTS:
        value = block.get(account)
        if value is None:
            problems.append("账户 {0} 未声明额度（不得省略：省略等于无授权）".format(account))
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            problems.append("账户 {0} 额度不是数字：{1!r}".format(account, value))
            continue
        number = float(value)
        if number < 0:
            problems.append("账户 {0} 额度为负：{1}".format(account, number))
            continue
        out[account] = number
    return out, problems


def classify(doc: Optional[Mapping[str, Any]]) -> str:
    """只判形态（不做合规判定）：legacy / unified / dual / unknown。"""

    if not isinstance(doc, Mapping):
        return FORM_UNKNOWN
    unified = (str(doc.get("schema") or "") == UNIFIED_SCHEMA
               or any(key in doc for key in ("allowed_operations", "allowed_accounts",
                                             "trusted", "authorization_id")))
    legacy = ("authorized" in doc) or ("batch" in doc) or ("budgets" in doc)
    if unified and legacy:
        return FORM_DUAL
    if unified:
        return FORM_UNIFIED
    if legacy:
        return FORM_LEGACY
    return FORM_UNKNOWN


def validate(doc: Optional[Mapping[str, Any]], *,
             expected_batch_label: Optional[str] = None,
             required_operations: Sequence[str] = ()) -> Dict[str, Any]:
    """授权文档校验（**失败关闭**）：返回审计行（含 `authorization_form`）。

    - `ok=False` 表示拒绝：调用方必须不执行任何真实副作用；
    - `budgets` 是**统一口径**的账户额度（供预检逐账户核对），两族字段都会转进来；
    - `operations` 是本批允许的操作清单（legacy 形态没有该清单 ⇒ 记为空并标
      `operations_declared=False`，由调用方决定是否接受；本包默认要求新形态）。
    """

    form = classify(doc)
    problems: List[str] = []
    budgets: Dict[str, float] = {}
    operations: List[str] = []
    if not isinstance(doc, Mapping):
        return {"schema": "sitin-gate2-authorization-check/1",
                "authorization_form": FORM_UNKNOWN, "ok": False,
                "problems": ["授权文档缺失或不是映射（fail-closed）"],
                "budgets": {}, "operations": [],
                "note": "没有授权就不跑任何真实桌赛"}
    if form == FORM_UNKNOWN:
        # 既不是 legacy 也不是 sitin-authorization/1：**必须拒绝**（失败关闭），
        # 不允许"看不懂的授权文档"静默通过。
        problems.append("无法识别的授权形态（既无 authorized/batch/budgets，"
                        "也无 schema=sitin-authorization/1 的字段面）")
    # —— legacy 族 ——
    if form in (FORM_LEGACY, FORM_DUAL):
        if doc.get("authorized") is not True:
            problems.append("legacy: authorized 必须为 true（得到 {0!r}）".format(
                doc.get("authorized")))
        if doc.get("batch") != LEGACY_BATCH_VALUE:
            problems.append("legacy: batch 必须是历史门值 {0}（得到 {1!r}）".format(
                LEGACY_BATCH_VALUE, doc.get("batch")))
        block = doc.get("budgets")
        if not isinstance(block, Mapping):
            problems.append("legacy: budgets 必须是映射（生产按它建账本授权额度）")
        else:
            cleaned, account_problems = _clean_accounts(block)
            budgets.update(cleaned)
            problems.extend("legacy: " + row for row in account_problems)
    # —— 新形态 ——
    if form in (FORM_UNIFIED, FORM_DUAL):
        if str(doc.get("schema") or "") != UNIFIED_SCHEMA:
            problems.append("unified: schema 必须是 {0!r}（得到 {1!r}）".format(
                UNIFIED_SCHEMA, doc.get("schema")))
        if not str(doc.get("authorization_id") or "").strip():
            problems.append("unified: authorization_id 不得为空（不透明标识，但必须存在）")
        if doc.get("trusted") is not True:
            problems.append("unified: trusted 必须为 true（得到 {0!r}）".format(
                doc.get("trusted")))
        label = str(doc.get("batch_label") or "")
        if not label:
            problems.append("unified: batch_label 不得为空")
        elif expected_batch_label and label != str(expected_batch_label):
            problems.append("unified: batch_label 不符（文档 {0!r} / 本次运行 {1!r}）".format(
                label, expected_batch_label))
        raw_ops = doc.get("allowed_operations")
        if not isinstance(raw_ops, (list, tuple)) or not raw_ops:
            problems.append("unified: allowed_operations 必须是非空清单")
        else:
            operations = [str(item) for item in raw_ops]
            unknown = sorted(set(operations) - set(ALLOWED_OPERATIONS))
            if unknown:
                problems.append("unified: allowed_operations 含白名单外操作 {0}"
                                "（模型无权扩标签集）".format(unknown))
            missing = sorted(set(required_operations) - set(operations))
            if missing:
                problems.append("unified: allowed_operations 缺本批必需操作 {0}".format(
                    missing))
        accounts_block = doc.get("allowed_accounts")
        if not isinstance(accounts_block, Mapping):
            problems.append("unified: allowed_accounts 必须是映射")
        else:
            cleaned, account_problems = _clean_accounts(accounts_block)
            problems.extend("unified: " + row for row in account_problems)
            if form == FORM_DUAL:
                # 两族都在：**逐账户必须逐字相等**（同一批算力不能有两份额度）。
                clash = sorted(account for account, value in cleaned.items()
                               if account in budgets
                               and abs(float(budgets[account]) - float(value)) > 1e-9)
                if clash:
                    problems.append("dual: budgets 与 allowed_accounts 额度不一致：{0}".format(
                        {account: (budgets[account], cleaned[account])
                         for account in clash}))
            budgets.update(cleaned)
        if not str(doc.get("issued_by") or "").strip():
            problems.append("unified: issued_by 不得为空（谁授权必须可追）")
        if _parse_iso8601(doc.get("issued_at_utc")) is None:
            problems.append("unified: issued_at_utc 必须是 ISO8601（得到 {0!r}）".format(
                doc.get("issued_at_utc")))
    return {
        "schema": "sitin-gate2-authorization-check/1",
        "authorization_form": form,
        "authorization_id": doc.get("authorization_id"),
        "batch_label": doc.get("batch_label"),
        "trusted": doc.get("trusted"),
        "issued_by": doc.get("issued_by"),
        "issued_at_utc": doc.get("issued_at_utc"),
        "operations": operations,
        "operations_declared": bool(operations),
        "budgets": budgets,
        "ok": not problems,
        "problems": problems,
        "note": ("两种形态都支持；同时带两族字段时两族都必须通过。"
                 "失败关闭：不合规即不执行任何真实副作用。"),
    }


def unified_document(*, batch_label: str, authorization_id: str,
                     accounts: Mapping[str, Any],
                     operations: Sequence[str] = ALLOWED_OPERATIONS,
                     issued_by: str = "lead",
                     issued_at_utc: str,
                     legacy_alias: bool = True,
                     legacy_note: str = "") -> Dict[str, Any]:
    """产出**统一形态**的授权文档；可选带 legacy 兼容字段（同一文档、同一批额度）。

    `legacy_alias=True` 时同时写入 `authorized/batch/budgets`：这是**现有生产**
    （`_step_natural` 的 `authorized is True and batch == 7`、`av_ledger_budgets_from_authorization`
    读 `budgets`）在 P11 落地之前仍然需要的字段。字段名与额度逐字相同，
    不新增任何"第二份额度"；P11 落地后可把 `legacy_alias` 关掉，
    验收器两条路径都已覆盖（见 p12_authorization 的自测）。
    """

    doc: Dict[str, Any] = {
        "schema": UNIFIED_SCHEMA,
        "authorization_id": str(authorization_id),
        "batch_label": str(batch_label),
        "trusted": True,
        "allowed_operations": [str(item) for item in operations],
        "allowed_accounts": {account: float(accounts.get(account) or 0.0)
                             for account in ACCOUNTS},
        "issued_by": str(issued_by),
        "issued_at_utc": str(issued_at_utc),
    }
    if legacy_alias:
        doc.update({
            "authorized": True,
            "batch": LEGACY_BATCH_VALUE,
            "budgets": {account: float(accounts.get(account) or 0.0)
                        for account in ACCOUNTS},
            "legacy_alias_note": legacy_note or (
                "legacy 兼容字段：现有生产 _step_natural / v2 前缀路由的判据是 "
                "authorized is True and batch == 7，账本额度取自 budgets；"
                "与 allowed_accounts 逐账户同值，P11 落地统一校验后可移除"),
        })
    return doc
