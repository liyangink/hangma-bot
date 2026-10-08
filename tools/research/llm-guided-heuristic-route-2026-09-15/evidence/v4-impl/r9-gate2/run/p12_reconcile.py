#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""P12 · G1：按冻结实例键逐项连接 计划 ↔ 尝试 ↔ 结果 ↔ 费用。

裁定原文（R9-ACCEPTANCE-AND-Q1-Q7-RULING §5 G1）：

> `reconcile` 用 `len(所有实例行) ≥ 计划自然实例数` 判断零丢失……别的通道多出的记录
> 可以掩盖目标实例缺失。
> `collect_fake_completions` 只检查摘要非空、路径存在……
> 修复按冻结实例键逐项连接计划、尝试、结果和费用；每项必须是已完成且可核、明确失败，
> 或明确因预算未执行。后两者可以满足账目诚实，但不能满足功能完成。自然、条件、家族、
> 共享缓存均不能靠彼此的数量补齐。现有条件通道没有实例台账时，可先从实际评价产物建立
> 本次验收索引，不强制重写所有生产账本。
> 摘要检查按生产实际摘要 schema 重算相应文件或嵌套样本，不能误把样本摘要当全文件摘要。
> 复用只记引用；失败重试有真实成本，不能把所有多次尝试都当重复收费。

要点：

1. 冻结实例键 = 迭代序号 × 通道 × 情景 × 根身份 × 根序号 × 根种子 × 座位 × 臂 × 赛程；
   候选身份不进键（计划写候选槽名、运行写候选哈希），因此**不靠数量**、只靠键 join。
2. 终态只允许 `completed_verifiable` / `explicit_failure` / `budget_not_executed`
   （另单列"未终结"与"摘要不符"，不混进上面三类）。
3. 摘要按**生产实际 schema**重算：自然面板 = 嵌套臂结果块的 canonical_json sha256
   （**不是**全文件摘要），家族/条件评价 = 整文件 sha256；条件通道生产不落盘实例摘要 ⇒
   该通道摘要一致性记 INSUFFICIENT（既不是 PASS 也不是 FAIL）。
   P25（复审 P24 §1）：条件通道改以**完成时登记值**为准（完成事务的文件字节摘要 /
   迭代状态规范载荷摘要），且**至少完成一次有效摘要比较**才可核；缺摘要残壳、坏登记、
   摘要算不出 ⇒ 具名 INSUFFICIENT / 损坏，**禁止**由被检文件即时反推期望值补绿。
4. 逐通道分开签收：自然 / 共享缓存 / 条件 / 家族谁也补不了谁。
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

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

CHANNEL_NATURAL = "natural_full"
CHANNEL_SHARED_BASELINE = "shared_baseline_cache"
CHANNEL_CONDITIONAL = "conditional"
CHANNEL_FAMILY = "family_fill"
CHANNELS: Tuple[str, ...] = (CHANNEL_NATURAL, CHANNEL_SHARED_BASELINE,
                             CHANNEL_CONDITIONAL, CHANNEL_FAMILY)

TERMINAL_COMPLETED = "completed_verifiable"
TERMINAL_FAILED = "explicit_failure"
TERMINAL_BUDGET = "budget_not_executed"
TERMINAL_UNFINISHED = "unfinished_in_flight"
TERMINAL_MISSING = "missing_from_ledger"
TERMINAL_DIGEST_MISMATCH = "completed_but_digest_mismatch"

DIGEST_SCHEMA_NESTED_ARM = "nested_arm_block_canonical_sha256"
DIGEST_SCHEMA_WHOLE_FILE = "whole_file_sha256"
DIGEST_SCHEMA_NONE = "no_recorded_digest"

#: 自然面板的两个通道共用同一个账本步（natural:<cid>:<mix>:<roots>），
#: 费用 join 按**同粒度分组**比较（分组口径写在行里，不靠总额互相冲抵）。
COST_GROUPS: Dict[str, Tuple[str, ...]] = {
    "natural_panel(H/M)": (CHANNEL_NATURAL, CHANNEL_SHARED_BASELINE),
    CHANNEL_FAMILY: (CHANNEL_FAMILY,),
    "conditional(prefix/refill)": (CHANNEL_CONDITIONAL,),
}

_BUDGET_MARKERS = ("预算", "授权", "超过", "LedgerOverAuthorized", "BudgetExhausted",
                   "LedgerUnauthorized", "拒绝")


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> Optional[str]:
    try:
        return sha256_bytes(Path(path).read_bytes())
    except OSError:
        return None


def canonical_json(payload: Any) -> str:
    """与生产 `sitin_search.canonical_json` 逐字同口径（键序与分隔符都必须一致）。"""

    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def read_json(path: Path) -> Optional[Any]:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def iter_dirs(run_root: Path) -> List[Path]:
    iterations = Path(run_root) / "iterations"
    return sorted(iterations.glob("iter-*")) if iterations.is_dir() else []


def layout_of(run_root: Path) -> str:
    """目录形态：`run_root`（完整运行目录）或 `evidence_copy`（证据副本）。

    证据副本（例如裁定 §4 引用的 `evidence/v4-impl/r9-fixes/P9-famcost/green/e2e-p9c/`）
    没有 `iterations/` 树，只有 `state-iter-0N.json`、`family/*.json`、`ledger.json`
    与 `gate2-run.json`：仍然可以做**逐键对照**与覆盖判据，但实例摘要只存在于完整
    运行目录里 ⇒ 摘要一致性在该形态下记 INSUFFICIENT，绝不写成通过。
    """

    root = Path(run_root)
    if (root / "iterations").is_dir():
        return "run_root"
    if list(root.glob("state-iter-*.json")):
        return "evidence_copy"
    return "unknown"


def state_files(run_root: Path) -> List[Tuple[str, Path]]:
    """迭代序号 → 状态文件（两种形态都支持）。"""

    root = Path(run_root)
    if layout_of(root) == "run_root":
        out = []
        for iter_dir in iter_dirs(root):
            state = read_json(iter_dir / "state.json") or {}
            label = str(state.get("iteration_no") or _ordinal(iter_dir.name))
            out.append((label, iter_dir / "state.json"))
        return out
    out = []
    for path in sorted(root.glob("state-iter-*.json")):
        out.append((_ordinal(path.stem), path))
    return out


def _ordinal(name: Any) -> str:
    """迭代序号（**只有序号进键**）：计划写 cand1/cand2，运行写 iteration_no=1/2。"""

    text = str(name or "")
    digits = re.findall(r"\d+", text)
    return str(int(digits[-1])) if digits else text


def sub_scenario_of_root(root_id: Any) -> Optional[str]:
    """从家族根身份取子场景（cell）：av-eval-<sub>:<sub>:<gen>:<mix>:s<seed>:rootNNN。"""

    text = str(root_id or "")
    if not text.startswith("av-eval-"):
        return None
    return text[len("av-eval-"):].split(":", 1)[0] or None


def descriptor_from_root_id(root_id: Any) -> Dict[str, Any]:
    """从家族根身份串还原唯一根描述符（家族样本**不带** `root_descriptor` 字段）。

    身份串形如 `av-eval-<sub>:<sub>:<generator>:<mix>:s<panel_seed>:rootNNN`；
    还原出来的字段用于按冻结参数**重算**要求摘要（Q3 的"可重算"那一半）。
    """

    text = str(root_id or "")
    if not text.startswith("av-eval-"):
        return {}
    parts = text.split(":")
    if len(parts) < 6:
        return {}
    sub = parts[0][len("av-eval-"):]
    mix = parts[3]
    seed_text = parts[4]
    index_text = parts[5]
    if not seed_text.startswith("s") or not index_text.startswith("root"):
        return {}
    try:
        panel_seed = int(seed_text[1:])
        root_index = int(index_text[len("root"):])
    except ValueError:
        return {}
    return {"schema": "sitin-root-descriptor/2", "generator": parts[2],
            "sub_scenario": sub, "opponent_mix": mix, "panel_seed": panel_seed,
            "root_index": root_index, "root_id": text}


def instance_key(*, iteration: Any, channel: Any, mix: Any, root_id: Any,
                 root_index: Any, root_seed: Any, seat: Any, arm: Any,
                 schedule: Any, cell: Any = None) -> str:
    """**冻结实例键**：候选之外的每一维都进键，缺一维就可能把两个实例并成一条。

    家族通道的根身份在运行期才解析（计划侧只有根序号），因此家族键里用 **cell**
    （子场景）代替完整根 id 并保留根序号 —— 少了 cell 这一维，branch_open|H|idx3
    与 branch_cost|H|idx3 会被并成同一条（本次纯数据自测实测）。
    """

    parts = ["iter={0}".format(_ordinal(iteration)),
             "channel={0}".format(channel), "mix={0}".format(mix)]
    if str(channel) == CHANNEL_FAMILY:
        parts.append("cell={0}".format(cell))
    else:
        parts.append("root={0}".format(root_id))
    parts.extend(["rootidx={0}".format(root_index),
                  "rootseed={0}".format(root_seed),
                  "seat={0}".format(seat), "arm={0}".format(arm),
                  "sched={0}".format(schedule)])
    return "|".join(parts)


def parse_key(key: Any) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for chunk in str(key).split("|"):
        if "=" in chunk:
            name, value = chunk.split("=", 1)
            out[name] = value
    return out


def _norm_runtime_root(key: str) -> str:
    """家族/条件键归一：运行期才解析的根身份不进 join（另有身份判据单独核）。"""

    out = []
    for chunk in key.split("|"):
        if chunk.startswith("root="):
            out.append("root=<runtime>")
        elif chunk.startswith("rootseed="):
            out.append("rootseed=<runtime>")
        else:
            out.append(chunk)
    return "|".join(out)


# ===========================================================================
# 计划侧：展开成臂级冻结实例
# ===========================================================================


def plan_iteration_ordinals(plan: Mapping[str, Any]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for index, item in enumerate(plan.get("iterations") or (), start=1):
        out[str(item.get("iteration_label"))] = str(index)
    return out


def plan_expected_instances(plan: Mapping[str, Any]) -> List[Dict[str, Any]]:
    """计划 → 臂级冻结实例清单（每行都带展开口径，不用"看起来差不多"补数）。"""

    rows: List[Dict[str, Any]] = []
    ordinals = plan_iteration_ordinals(plan)
    for row in (plan.get("instances") or ()):
        category = str(row.get("category"))
        label = str(row.get("iteration"))
        ordinal = ordinals.get(label, _ordinal(label))
        base = {"iteration": ordinal, "iteration_label": label,
                "plan_candidate_slot": row.get("candidate_id"),
                "category": category, "opponent_mix": row.get("opponent_mix"),
                "seat": row.get("seat", 0), "schedule": row.get("schedule"),
                "planned_tables": float(row.get("planned_tables") or 0.0)}
        if category == "natural_full":
            channel = (CHANNEL_SHARED_BASELINE if str(row.get("arm")) == "baseline"
                       else CHANNEL_NATURAL)
            rows.append(dict(base, channel=channel,
                             source_root_id=row.get("source_root_id"),
                             root_index=row.get("root_index"),
                             root_seed=row.get("root_seed"), arm=row.get("arm"),
                             root_purpose=("shared_baseline" if channel
                                           == CHANNEL_SHARED_BASELINE
                                           else "natural_full_tables"),
                             expansion="计划行即臂级实例（每根×座位×臂一条）"))
        elif category == "family_fill":
            per_arm = float(row.get("planned_tables") or 0.0) / 2.0
            # 根用途以**声明的 intent** 为准（裁定 §4.1 / G2；旧产物无 intent 按 discover 读）：
            #   reevaluate_registered_root = 指定旧根 / 共同根重评（逐字用冻结描述符）
            #   discover_new_root          = 新根发现（排除已登记根）
            # root_index 缺省 = 根身份运行期解析（第二候选的"指定旧根"那一行）。
            intent = str(row.get("intent") or "discover_new_root")
            if (row.get("root_index") is None
                    and str(row.get("root_index_resolution") or "").startswith(
                        "runtime")):
                purpose = "family_old_root_review"
            elif intent == "reevaluate_registered_root":
                purpose = "family_reevaluation"
            else:
                purpose = "family_refresh_root"
            for arm in ("baseline", "candidate"):
                rows.append(dict(base, channel=CHANNEL_FAMILY, source_root_id=None,
                                 root_index=row.get("root_index"),
                                 root_seed=row.get("root_seed"),
                                 arm=arm, planned_tables=per_arm,
                                 sub_scenario=row.get("sub_scenario"),
                                 declaration_intent=intent,
                                 root_index_resolution=row.get("root_index_resolution"),
                                 declaration_purpose=row.get("declaration_purpose"),
                                 frozen_root_id=row.get("root_id"),
                                 root_purpose=purpose,
                                 expansion=("家族声明 1 行（arm=both，{0:.0f} 桌）⇒ "
                                            "臂级 2 行 × {1:.0f} 桌；用途 {2}（intent={3}）"
                                            .format(float(row.get("planned_tables") or 0.0),
                                                    per_arm, purpose, intent))))
        elif category in ("conditional_prefix_partial", "conditional_full"):
            rows.append(dict(base, channel=CHANNEL_CONDITIONAL, source_root_id=None,
                             root_index=None, root_seed=None, arm=row.get("arm"),
                             expansion=("条件通道计划行：根身份运行期解析；"
                                        "实际索引从评价产物建立，不由计划编造根 id")))
        else:
            rows.append(dict(base, channel="unmapped:{0}".format(category),
                             source_root_id=None, root_index=None, root_seed=None,
                             arm=row.get("arm"),
                             expansion="未映射类目（显式登记，不静默丢弃）"))
    return rows


def key_of_expected(row: Mapping[str, Any]) -> str:
    return instance_key(iteration=row.get("iteration"), channel=row.get("channel"),
                        mix=row.get("opponent_mix"), root_id=row.get("source_root_id"),
                        root_index=row.get("root_index"), root_seed=row.get("root_seed"),
                        seat=row.get("seat"), arm=row.get("arm"),
                        schedule=row.get("schedule"),
                        cell=row.get("sub_scenario"))


# ===========================================================================
# 运行侧
# ===========================================================================


def channel_of_run_row(row: Mapping[str, Any]) -> str:
    root_id = str(row.get("source_root_id") or "")
    if root_id.startswith("av-eval-"):
        return CHANNEL_FAMILY
    if str(row.get("evaluation_scope")) == "shared_baseline_cache":
        return CHANNEL_SHARED_BASELINE
    return CHANNEL_NATURAL


def observed_instances(run_root: Path) -> List[Dict[str, Any]]:
    """从**逐迭代**实例台账读实际实例（运行级文件是累计镜像，读它会双计）。"""

    rows: List[Dict[str, Any]] = []
    layout = layout_of(Path(run_root))
    if layout == "run_root":
        for iter_dir in iter_dirs(Path(run_root)):
            payload = read_json(iter_dir / "instances.json") or {}
            state = read_json(iter_dir / "state.json") or {}
            label = str(state.get("iteration_no") or _ordinal(iter_dir.name))
            for key, row in (payload.get("instances") or {}).items():
                rows.append({"iteration_dir": iter_dir.name, "iteration": label,
                             "ledger_key": key, "row": dict(row),
                             "channel": channel_of_run_row(row)})
        return rows
    if layout == "evidence_copy":
        # 证据副本：实例行只能从 gate2-run.json 的对账投影里取（没有完整台账）。
        report = read_json(Path(run_root) / "gate2-run.json") or {}
        for item in ((report.get("reconciliation") or {}).get("instance_rows") or ()):
            row = {"instance_key": None, "candidate_id": item.get("candidate_id"),
                   "opponent_mix": item.get("opponent_mix"),
                   "source_root_id": item.get("source_root_id"),
                   "root_index": item.get("root_index"),
                   "root_seed": item.get("root_seed"), "seat": item.get("seat"),
                   "arm": item.get("arm"), "schedule": item.get("schedule"),
                   "evaluation_scope": item.get("scope"),
                   "planned_tables": item.get("planned_tables"),
                   "attempts": [{"status": item.get("status"),
                                 "cost": {"tables": item.get("tables")},
                                 "result_path": None, "result_digest": None,
                                 "note": "证据副本无完整台账/无结果摘要"}]}
            rows.append({"iteration_dir": "evidence-copy",
                         "iteration": _ordinal(item.get("iteration")),
                         "ledger_key": "{0}|evidence-copy".format(item.get("iteration")),
                         "row": row, "channel": channel_of_run_row(row)})
        return rows
    return rows


def key_of_observed(entry: Mapping[str, Any]) -> str:
    row = entry["row"]
    return instance_key(iteration=entry.get("iteration"), channel=entry.get("channel"),
                        mix=row.get("opponent_mix"), root_id=row.get("source_root_id"),
                        root_index=row.get("root_index"), root_seed=row.get("root_seed"),
                        seat=row.get("seat"), arm=row.get("arm"),
                        schedule=row.get("schedule"),
                        cell=sub_scenario_of_root(row.get("source_root_id")))


# ---------------------------------------------------------------------------
# 条件通道：结果摘要的**登记**（完成时写下）与运行期根的**具名绑定**
# ---------------------------------------------------------------------------


CONDITIONAL_DIGEST_SCHEMA = "sitin-conditional-result-digest/1"
CONDITIONAL_REGISTRATION_SCHEMA = "sitin-conditional-result-registration/1"
CONDITIONAL_TX_SCHEMA = "sitin-av-tx-eval-complete/1"

#: 条件通道结果摘要的**状态机**（P25 修复）。三条判据：
#: 1.「登记**来源存在**」与「登记含**有效摘要**」必须分开 —— 完成事务只要是个
#:   Mapping 就算来源，但不含 immutable_summary_sha256 的**残壳**不是可核来源；
#: 2. verified 只发给「**至少完成一次有效摘要比较**、且所有应核来源都一致」的产物；
#:   一次比较都没做成 ⇒ 具名 INSUFFICIENT（不是通过，也不是篡改）；
#: 3. 期望摘要只能来自**完成时登记值**；缺摘要/坏登记时**禁止**由被检文件即时
#:   反推期望值补绿（自签期望值 = 把「文件与自身一致」当成「未被改写」）。
CONDITIONAL_DIGEST_VERIFIED = "verified"
CONDITIONAL_DIGEST_MISMATCH = "mismatch"
#: 一个登记来源都没有（完成事务与迭代状态载荷都不在）。
CONDITIONAL_DIGEST_NO_SOURCE = "no_recorded_digest"
#: 残壳：登记来源记录在，但**一条合法摘要声明都没有**（零比较，不是通过）。
CONDITIONAL_DIGEST_SHELL = "registered_without_digest"
#: 登记了摘要，但当前产物**算不出**对应值（零有效比较）。
CONDITIONAL_DIGEST_UNRECOMPUTABLE = "recorded_digest_unrecomputable"
#: 有有效比较通过，但**仍有应核来源/声明无法核**（不是全部一致 ⇒ 不给 verified）。
CONDITIONAL_DIGEST_PARTIAL = "partially_unverifiable_digest"
#: 失败关闭的具名状态集合（既不是可核也不是篡改）；消费方一律按 INSUFFICIENT 记。
CONDITIONAL_DIGEST_INSUFFICIENT_STATES: Tuple[str, ...] = (
    CONDITIONAL_DIGEST_NO_SOURCE, CONDITIONAL_DIGEST_SHELL,
    CONDITIONAL_DIGEST_UNRECOMPUTABLE, CONDITIONAL_DIGEST_PARTIAL)
#: 摘要声明的规范字段：(比较名, 登记字段, 重算字段)。
CONDITIONAL_DIGEST_CLAIM_FIELDS: Tuple[Tuple[str, str, str], ...] = (
    ("file_sha256", "registered_file_sha256", "file_sha256"),
    ("payload_digest", "registered_payload_digest", "payload_digest"))


def digest_value_shape(recorded: Any) -> str:
    """登记摘要值的形状：ok（合法 sha256）/ absent（没登记）/ malformed（坏登记）。"""

    if recorded is None or str(recorded).strip() == "":
        return "absent"
    text = str(recorded).strip().lower()
    if len(text) != 64 or any(char not in "0123456789abcdef" for char in text):
        return "malformed"
    return "ok"


def conditional_digest_state_is_verified(state: Any,
                                         verdict: Optional[Mapping[str, Any]] = None,
                                         ) -> bool:
    """**唯一**的「可核」判据（:1709 消费点与覆盖判据都走这里）。

    只有 verified 才可核；给出 verdict 时还要求**至少一次有效摘要比较**
    （P25：零比较的残壳在修复前会被读成 verified，不得再被当成可核）。
    """

    if str(state) != CONDITIONAL_DIGEST_VERIFIED:
        return False
    if verdict is None:
        return True
    return int(verdict.get("valid_comparisons") or 0) >= 1


def canonical_payload_digest(payload: Any) -> str:
    """载荷的规范摘要（与生产同一个 canonical 口径；两侧共用同一个函数）。"""

    return sha256_bytes(canonical_json(payload).encode("utf-8"))


def root_identity_of_sample(sample: Mapping[str, Any]) -> Dict[str, Any]:
    """一条条件样本的**完整根身份**：候选之外的每一维都取，缺一维就不算同一个根。"""

    descriptor = dict(sample.get("root_descriptor") or {})
    root_id = str(sample.get("source_root_id") or sample.get("root_id")
                  or descriptor.get("root_id") or "")
    root_index = (sample.get("root_index") if sample.get("root_index") is not None
                  else descriptor.get("root_index"))
    root_seed = (sample.get("root_seed") if sample.get("root_seed") is not None
                 else descriptor.get("root_seed"))
    return {
        "root_id": root_id or None, "root_index": root_index, "root_seed": root_seed,
        "opponent_mix": (sample.get("opponent_mix") or descriptor.get("opponent_mix")),
        "sub_scenario": (sample.get("scenario") or descriptor.get("sub_scenario")
                         or sub_scenario_of_root(root_id)),
        "generator": descriptor.get("generator"),
        "candidate_id": sample.get("candidate_id"),
    }


def conditional_registrations(iter_dir: Path,
                              state: Mapping[str, Any]) -> Dict[str, Any]:
    """条件通道**结果摘要的登记来源**（完成时写下、对账时只读）。

    两个来源互不替代，也**都不从当前评价文件反推**（不从被检文件自签期望值）：

    1. 完成事务 `transactions/tx-eval-conditional-complete.json`
       （schema `{0}`）的 `immutable_summary_sha256`：
       该次评价**结果文件的字节摘要**，对账时重新计算文件摘要并比较；
    2. 迭代状态 `state.json#conditional_result`：生产在完成时登记的**规范结果载荷**，
       本模块用同一个 canonical 口径重算载荷摘要并比较。

    两者都没有 ⇒ 摘要状态 `no_recorded_digest`（INSUFFICIENT）：
    **RootWitness 只证明评价从哪个根出发，不作结果摘要**（复审 C2 定位 823 行附近）。

    P25 补充（复审 P24 §1 定位 428 行附近）：**登记「来源存在」不等于登记
    「含有效摘要」**。因此每个来源都附上摘要声明读数（`digest_claims` /
    `malformed_claims` / `path_without_digest`），并在聚合层给出
    `has_digest_registration` —— 完成事务是个 Mapping 但没有
    `immutable_summary_sha256` 的残壳，不是可核来源。
    """.format(CONDITIONAL_TX_SCHEMA)

    sources: List[Dict[str, Any]] = []
    tx_path = Path(iter_dir) / "transactions" / "tx-eval-conditional-complete.json"
    tx = read_json(tx_path)
    if isinstance(tx, Mapping):
        sources.append({
            "kind": "completion_transaction", "path": str(tx_path),
            "schema": tx.get("schema"),
            "registered_file_sha256": tx.get("immutable_summary_sha256"),
            "registered_result_path": tx.get("immutable_summary_path"),
            "evaluation_id": tx.get("evaluation_id"),
            "cost": (dict(tx.get("cost") or {}) if isinstance(tx.get("cost"), Mapping)
                     else {}),
            "note": ("完成事务登记的结果文件字节摘要：对账时重算文件 sha256 并比较"
                     "（登记值来自完成时，不由当前文件反推）")})
    elif tx_path.is_file():
        # P25：文件在但**读不出来**（截断/非法 JSON）也是损坏登记 —— 不能因为
        # "读不出就当没有来源"而静默降级；具名记一条无摘要来源，由判定函数按
        # INSUFFICIENT 处理（这是损坏证据，不是"没有登记"）。
        sources.append({
            "kind": "completion_transaction_unreadable", "path": str(tx_path),
            "schema": None, "registered_file_sha256": None,
            "registered_result_path": None, "evaluation_id": None, "cost": {},
            "damaged": "transaction_unreadable",
            "note": ("完成事务文件存在但读不出（截断/非法 JSON）⇒ 损坏登记，"
                     "按无有效摘要的具名 INSUFFICIENT 处理")})
    payload = state.get("conditional_result")
    registered_roots: List[Dict[str, Any]] = []
    payload_digest = None
    if isinstance(payload, Mapping):
        payload_digest = canonical_payload_digest(payload)
        for row in (payload.get("samples") or ()):
            if isinstance(row, Mapping):
                registered_roots.append(root_identity_of_sample(row))
        sources.append({
            "kind": "iteration_state_payload", "path": "state.json#conditional_result",
            "schema": payload.get("schema"),
            "registered_payload_digest": payload_digest,
            "evaluation_id": (payload.get("identity") or {}).get("evaluation_id"),
            "registered_roots": registered_roots,
            "note": ("迭代状态登记的规范结果载荷：对账时按同一 canonical 口径重算载荷摘要"
                     "并比较（载荷文本取自完成时的状态文件，不取自被检评价文件）")})
    # P25：「来源记录存在」与「含**有效摘要**」分开读。残壳（有来源、无摘要）在
    # 修复前会被 :542 判成 verified；现在必须在登记阶段就把这件事读出来。
    for source in sources:
        claims: List[str] = []
        malformed: List[str] = []
        absent: List[str] = []
        for name, registered_field, _recomputed_field in CONDITIONAL_DIGEST_CLAIM_FIELDS:
            shape = digest_value_shape(source.get(registered_field))
            if shape == "ok":
                claims.append(name)
            elif shape == "malformed":
                malformed.append(name)
            else:
                absent.append(name)
        source["digest_claims"] = claims
        source["malformed_claims"] = malformed
        source["absent_digest_fields"] = absent
        source["has_digest_claim"] = bool(claims)
        # 有结果路径却没有摘要值 = 残壳的典型形状（迁移/截断后常见）：只作读数，
        # 判据仍按「没有有效摘要声明」走 registered_without_digest。
        source["path_without_digest"] = bool(source.get("registered_result_path")
                                             and "file_sha256" in absent)
    conditional_block = (state.get("conditional")
                         if isinstance(state.get("conditional"), Mapping) else {})
    digest_sources = [row for row in sources if row.get("has_digest_claim")]
    return {
        "schema": CONDITIONAL_REGISTRATION_SCHEMA,
        "sources": sources,
        "source_kinds": [str(row.get("kind")) for row in sources],
        "registered_roots": registered_roots,
        "registered_evaluation_ids": [str(row.get("evaluation_id")) for row in sources
                                      if row.get("evaluation_id")],
        "state_evaluation_id": conditional_block.get("evaluation_id"),
        "state_evaluation_path": conditional_block.get("evaluation_path"),
        "has_registration": bool(sources),
        #: P25 新增：登记里**真正含有效摘要**的来源（不是"来源存在"）。
        "has_digest_registration": bool(digest_sources),
        "digest_source_kinds": [str(row.get("kind")) for row in digest_sources],
        "digest_claim_count": sum(len(row.get("digest_claims") or ())
                                  for row in sources),
        "sources_without_digest": [str(row.get("kind")) for row in sources
                                   if not row.get("has_digest_claim")],
    }


def conditional_result_verdict(*, result_path: Path, result_payload: Any,
                               result_file_sha256: Optional[str],
                               registration: Mapping[str, Any]) -> Dict[str, Any]:
    """重算当前评价产物的摘要，与**登记值**逐项比较（P25 判据）。

    判据（三条，全部失败关闭）：

    1. **有效摘要**才算可核来源：登记来源记录存在但一条合法摘要声明都没有（残壳）
       ⇒ 具名 `registered_without_digest`（INSUFFICIENT），不是通过；
    2. `verified` 只发给「**至少完成一次有效摘要比较**、且所有应核来源都一致」的产物：
       零比较（缺摘要 / 摘要算不出 / 坏登记）⇒ 具名 INSUFFICIENT 或损坏；
       有比较通过但仍有应核声明无法核 ⇒ `partially_unverifiable_digest`（仍不给 verified）；
    3. 任何登记值重算不一致 ⇒ `state=mismatch`（改内容不改登记摘要必须红）；
       坏登记（摘要值不是合法 sha256）按**损坏**记进 `mismatches` 并保持该红档位。

    期望值**只**取自登记侧（完成事务 / 迭代状态载荷）；被检文件只提供"重算值"，
    任何情况下都不由被检文件即时反推期望摘要（否则等于自签）。
    """

    recomputed = {
        "file_sha256": result_file_sha256,
        "payload_digest": (canonical_payload_digest(result_payload)
                           if isinstance(result_payload, Mapping) else None),
        "evaluation_id": ((result_payload.get("identity") or {}).get("evaluation_id")
                          if isinstance(result_payload, Mapping) else None),
    }
    sources = list(registration.get("sources") or ())
    verdict: Dict[str, Any] = {
        "schema": CONDITIONAL_DIGEST_SCHEMA, "state": None,
        "result_path": str(result_path), "recomputed": recomputed,
        "registered": {"sources": sources},
        "registration_kinds": list(registration.get("source_kinds") or ()),
        "identity": {"product_evaluation_id": recomputed["evaluation_id"],
                     "registered_evaluation_ids":
                         list(registration.get("registered_evaluation_ids") or ()),
                     "state_evaluation_id": registration.get("state_evaluation_id")},
        "mismatches": [], "checks": [], "detail": "",
        # P25 新增读数：有效比较次数 / 应核而未核的声明 / 残壳来源 / 损坏登记
        "valid_comparisons": 0, "unverifiable": [], "digest_claims": 0,
        "shell_sources": [], "malformed_claims": [], "damaged": False,
    }
    if not sources:
        verdict.update(state=CONDITIONAL_DIGEST_NO_SOURCE, detail=(
            "本次评价**没有结果摘要登记**（既无完成事务，迭代状态里也没有登记载荷）"
            "⇒ 结果完整性 INSUFFICIENT：不用 RootWitness 顶替结果摘要"))
        return verdict
    mismatches: List[Dict[str, Any]] = []
    unverifiable: List[Dict[str, Any]] = []
    comparisons_ok = 0
    claims = 0
    shell_sources: List[str] = []
    malformed_claims: List[str] = []
    for source in sources:
        source_label = str(source.get("path"))
        source_claims = 0
        for name, registered_field, recomputed_field in CONDITIONAL_DIGEST_CLAIM_FIELDS:
            recorded = source.get(registered_field)
            shape = digest_value_shape(recorded)
            if shape == "malformed":
                # 坏登记：值不是合法 sha256。按**损坏**记进 mismatches（保持既有
                # 篡改检测的红档位，不放宽），同时进 unverifiable（应核而未核）。
                row = {
                    "kind": "malformed_registered_digest", "digest": name,
                    "source": source_label, "registered": str(recorded)[:32],
                    "detail": ("登记摘要值不是合法 sha256（坏登记/截断）：既不能当"
                               "已登记摘要，也不能当已对拍一致")}
                mismatches.append(dict(row))
                unverifiable.append(dict(row))
                malformed_claims.append("{0}:{1}".format(source_label, name))
                continue
            if shape == "absent":
                continue
            claims += 1
            source_claims += 1
            observed = recomputed.get(recomputed_field)
            if not observed:
                # 登记了摘要但当前产物**算不出**对应值 ⇒ 应核而未核。
                unverifiable.append({
                    "kind": "recorded_digest_unrecomputable", "digest": name,
                    "source": source_label, "registered": str(recorded)[:16],
                    "detail": ("登记了 {0} 但当前产物算不出该值（文件读不出 / 载荷"
                               "不是 Mapping）⇒ 核不了，具名 INSUFFICIENT").format(name)})
                continue
            same = str(recorded) == str(observed)
            verdict["checks"].append({"name": name, "ok": same, "source": source_label})
            if same:
                comparisons_ok += 1
            else:
                mismatches.append({
                    "kind": name, "source": source_label,
                    "registered": str(recorded)[:16],
                    "recomputed": str(observed)[:16],
                    "detail": ("结果文件字节摘要与完成事务登记值不一致（内容被改）"
                               if name == "file_sha256" else
                               "规范结果载荷摘要与迭代状态登记值不一致"
                               "（结果被改而登记摘要未更新）")})
        if not source_claims and not source.get("malformed_claims"):
            # 残壳：来源记录在，但一条合法摘要声明都没有 —— **不**算可核来源。
            shell_sources.append(source_label)
            unverifiable.append({
                "kind": "source_without_digest", "source": source_label,
                "source_kind": source.get("kind"),
                "detail": ("该登记来源不含任何摘要字段（残壳）：登记「存在」不等于"
                           "登记「含有效摘要」，不计入可核来源")})
        recorded_id = source.get("evaluation_id")
        if recorded_id and recomputed["evaluation_id"] \
                and str(recorded_id) != str(recomputed["evaluation_id"]):
            mismatches.append({
                "kind": "evaluation_id", "source": source_label,
                "registered": str(recorded_id)[:16],
                "recomputed": str(recomputed["evaluation_id"])[:16],
                "detail": "评价身份与登记值不一致（换了根/候选/执行类别）"})
    verdict.update({"mismatches": mismatches, "unverifiable": unverifiable,
                    "valid_comparisons": comparisons_ok, "digest_claims": claims,
                    "shell_sources": shell_sources,
                    "malformed_claims": malformed_claims,
                    "damaged": bool(shell_sources or malformed_claims)})
    kinds = ",".join(str(row.get("kind")) for row in sources)
    if mismatches:
        verdict.update(state=CONDITIONAL_DIGEST_MISMATCH, detail=(
            "结果摘要/登记与登记值不一致 {0} 条：{1}").format(
                len(mismatches), "；".join(str(row["detail"]) for row in mismatches[:2])))
    elif comparisons_ok == 0:
        if shell_sources and claims == 0:
            verdict.update(state=CONDITIONAL_DIGEST_SHELL, detail=(
                "登记「来源存在」但**不含有效摘要**（残壳来源 {0} 条）⇒ 结果完整性 "
                "INSUFFICIENT：零次有效摘要比较不得写成通过").format(len(shell_sources)))
        else:
            verdict.update(state=CONDITIONAL_DIGEST_UNRECOMPUTABLE, detail=(
                "登记了结果摘要但当前产物**算不出**对应值（应核而未核 {0} 条）⇒ "
                "结果完整性 INSUFFICIENT").format(len(unverifiable)))
    elif unverifiable:
        verdict.update(state=CONDITIONAL_DIGEST_PARTIAL, detail=(
            "已有 {0} 次有效摘要比较通过，但仍有 {1} 条应核来源/声明无法核 ⇒ 不是"
            "「所有应核来源一致」，不给 verified（INSUFFICIENT）").format(
                comparisons_ok, len(unverifiable)))
    else:
        verdict.update(state=CONDITIONAL_DIGEST_VERIFIED, detail=(
            "结果摘要按登记值重算一致（有效比较 {0} 次；登记来源 {1}；文件 {2}｜载荷 {3}）"
        ).format(comparisons_ok, kinds, str(result_file_sha256)[:12],
                 str(recomputed["payload_digest"])[:12]))
    return verdict


def conditional_seat_binding(sample: Mapping[str, Any],
                             hits: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    """座位绑定：座位只能来自**具名来源**（样本字段 / 根见证的焦点座位与窗口座位）。"""

    votes: Dict[str, int] = {}
    if sample.get("focal_anchor_seat") is not None:
        votes["sample.focal_anchor_seat"] = int(sample.get("focal_anchor_seat"))
    for hit in hits:
        witness = dict(hit.get("witness") or {})
        if witness.get("focal_seat") is not None:
            votes["root_witness.focal_seat"] = int(witness.get("focal_seat"))
        window = dict(witness.get("cut_window_key") or {})
        if window.get("seat") is not None:
            votes["root_witness.cut_window_key.seat"] = int(window.get("seat"))
    distinct = sorted(set(votes.values()))
    return {"votes": votes, "seat": (distinct[0] if len(distinct) == 1 else None),
            "conflict": len(distinct) > 1,
            "basis": (", ".join(sorted(votes)) if votes else "无座位来源（按计划座位记）")}


def conditional_instances(run_root: Path) -> List[Dict[str, Any]]:
    """条件通道：生产**没有**实例台账 ⇒ 按裁定从实际评价产物建立本次验收索引。

    每个迭代条目带上：结果摘要**登记**读数（完成事务 / 迭代状态载荷）、样本的完整根身份、
    座位绑定来源。判定（绑定 / 比较 / 进出集合）在 `_conditional_channel` 里做。
    """

    out: List[Dict[str, Any]] = []
    root = Path(run_root)
    layout = layout_of(root)
    for label, state_path in state_files(root):
        state = read_json(state_path) or {}
        iter_dir = (state_path.parent if layout == "run_root"
                    else root / "iterations" / "iter-{0:02d}".format(int(label))
                    if str(label).isdigit() else root)
        path = iter_dir / "conditional" / "evaluation.json"
        payload = read_json(path)
        registration = conditional_registrations(iter_dir, state)
        if not isinstance(payload, Mapping):
            out.append({"iteration": label, "iteration_dir": str(iter_dir),
                        "kind": "evaluation_missing", "path": str(path),
                        "ok": None, "samples": [],
                        "registration": registration,
                        "digest_verdict": {"schema": CONDITIONAL_DIGEST_SCHEMA,
                                           "state": "no_recorded_digest",
                                           "detail": "该迭代没有评价产物，无结果可核"},
                        "iteration_status": state.get("status"),
                        "iteration_stop_reason": state.get("stop_reason"),
                        "note": "该迭代没有条件评价产物（未到该步或预算未执行）"})
            continue
        file_sha256 = sha256_file(path)
        digest_verdict = conditional_result_verdict(
            result_path=path, result_payload=payload, result_file_sha256=file_sha256,
            registration=registration)
        samples = []
        for item in (payload.get("samples") or ()):
            arms = {}
            for name, block in sorted((item.get("arms") or {}).items()):
                arms[name] = {
                    "status": (block or {}).get("status"),
                    "usable": (block or {}).get("usable"),
                    "tables": len(((block or {}).get("tables") or ())),
                    "arm_block_sha256": sha256_bytes(
                        canonical_json(dict(block or {})).encode("utf-8")),
                }
            samples.append({
                "source_root_id": item.get("source_root_id"),
                "root_index": item.get("root_index"),
                "root_seed": item.get("root_seed"),
                "opponent_mix": item.get("opponent_mix"),
                "root_descriptor": dict(item.get("root_descriptor") or {}),
                "root_requirement_digest": item.get("root_requirement_digest"),
                "root_content_digest": item.get("root_content_digest"),
                "focal_anchor_seat": item.get("focal_anchor_seat"),
                "arm_completeness": arms,
                "root_identity": root_identity_of_sample(item),
                "file_sha256": file_sha256})
        out.append({
            "iteration": label, "iteration_dir": str(iter_dir), "kind": "evaluation",
            "path": str(path), "ok": bool(payload.get("ok")),
            "iteration_status": state.get("status"),
            "iteration_stop_reason": state.get("stop_reason"),
            "reason": payload.get("refused"),
            "execution_kind": payload.get("execution_kind"),
            "runtime_kind": payload.get("runtime_kind"),
            "candidate_id": (payload.get("identity") or {}).get("candidate_id"),
            "registration": registration, "digest_verdict": digest_verdict,
            "tables_full_executed": float(
                (payload.get("panel") or {}).get("tables_full_executed") or 0.0),
            "tables_partial_charged": float(payload.get("tables_partial_charged") or 0.0),
            "prefix_attempts": dict((payload.get("panel") or {}).get(
                "prefix_attempts") or {}),
            "samples": samples,
        })
    return out


# ===========================================================================
# 摘要重算（按生产实际 schema）
# ===========================================================================


def verify_result_digest(*, channel: str, row: Mapping[str, Any],
                         attempt: Mapping[str, Any]) -> Dict[str, Any]:
    """一条 completed 尝试的结果摘要核验（见模块 docstring 第 3 条）。"""

    recorded = attempt.get("result_digest")
    result_path = attempt.get("result_path")
    verdict: Dict[str, Any] = {"recorded": recorded, "result_path": result_path,
                               "schema": None, "state": None, "recomputed": None,
                               "projection": None, "detail": ""}
    if str(channel) == CHANNEL_CONDITIONAL:
        verdict.update({"schema": DIGEST_SCHEMA_NONE, "state": "no_recorded_digest",
                        "detail": ("条件通道生产不落盘实例摘要：摘要一致性 "
                                   "INSUFFICIENT（内容存在性另由评价产物索引核）")})
        return verdict
    if not result_path or not Path(str(result_path)).is_file():
        verdict.update({"schema": DIGEST_SCHEMA_WHOLE_FILE,
                        "state": "missing_result_file",
                        "detail": "completed 尝试引用的结果文件不存在"})
        return verdict
    if str(channel) == CHANNEL_FAMILY:
        observed = sha256_file(Path(str(result_path)))
        if not recorded:
            state = "no_recorded_digest"
        else:
            state = "verified" if str(recorded) == observed else "mismatch"
        verdict.update({"schema": DIGEST_SCHEMA_WHOLE_FILE, "recomputed": observed,
                        "state": state,
                        "detail": "整文件 sha256（家族条件评价的落盘格式）"})
        return verdict
    payload = read_json(Path(str(result_path)))
    if not isinstance(payload, Mapping):
        verdict.update({"schema": DIGEST_SCHEMA_NESTED_ARM, "state": "unreadable_result",
                        "detail": "结果文件不可解析为 JSON 映射"})
        return verdict
    hit = None
    for sample in (payload.get("samples") or ()):
        if (str(sample.get("source_root_id")) == str(row.get("source_root_id"))
                and int(sample.get("focal_anchor_seat") or 0) == int(row.get("seat") or 0)):
            hit = dict(sample)
            break
    if hit is None:
        verdict.update({"schema": DIGEST_SCHEMA_NESTED_ARM, "state": "missing_sample",
                        "detail": "结果文件里没有该 (来源根, 座位) 的嵌套样本"})
        return verdict
    block = (hit.get("arms") or {}).get(str(row.get("arm")))
    if not isinstance(block, Mapping):
        verdict.update({"schema": DIGEST_SCHEMA_NESTED_ARM, "state": "missing_arm_block",
                        "detail": "嵌套样本里没有该臂的结果块"})
        return verdict
    plain = sha256_bytes(canonical_json(dict(block)).encode("utf-8"))
    if recorded and str(recorded) == plain:
        verdict.update({"schema": DIGEST_SCHEMA_NESTED_ARM, "recomputed": plain,
                        "state": "verified",
                        "detail": "嵌套臂结果块按生产 canonical_json 重算一致"})
        return verdict
    # 生产在写台账前把样本候选身份**归一**（原值留在 panel_reported_candidate_id）：
    # 允许按这条**已登记**的投影再算一次，并在读数里标明（不是放宽判据）。
    projected = dict(block)
    baseline_id = "v2-baseline-frozen"
    recomputed_projected = None
    if projected.get("candidate_id") not in (None, baseline_id):
        projected["candidate_id"] = row.get("candidate_id")
        recomputed_projected = sha256_bytes(canonical_json(projected).encode("utf-8"))
        if recorded and str(recorded) == recomputed_projected:
            verdict.update({"schema": DIGEST_SCHEMA_NESTED_ARM,
                            "recomputed": recomputed_projected, "state": "verified",
                            "projection": ("candidate_id_identity_projection"
                                           "（生产写台账前归一候选身份；"
                                           "与文件逐字值不同属已登记投影）"),
                            "detail": "按已登记身份投影后重算一致"})
            return verdict
    verdict.update({"schema": DIGEST_SCHEMA_NESTED_ARM, "recomputed": plain,
                    "recomputed_with_projection": recomputed_projected,
                    "state": "mismatch",
                    "detail": ("嵌套臂结果块重算值与台账摘要不一致（文件内容被改而摘要"
                               "未更新，或出现未登记的身份投影）")})
    return verdict


def classify_attempt(attempt: Mapping[str, Any]) -> str:
    status = str(attempt.get("status"))
    reason = str(attempt.get("reason") or "")
    if status == "completed":
        return TERMINAL_COMPLETED
    if status in ("aborted", "failed"):
        if any(marker in reason for marker in _BUDGET_MARKERS):
            return TERMINAL_BUDGET
        return TERMINAL_FAILED
    return TERMINAL_UNFINISHED


def is_failure_cost_attempt(attempt: Mapping[str, Any]) -> bool:
    return str(attempt.get("status")) not in ("completed",) and (
        float((attempt.get("cost") or {}).get("tables") or 0.0) > 0.0)


# ===========================================================================
# 逐键对账
# ===========================================================================


def _terminalize(entry: Mapping[str, Any]) -> Dict[str, Any]:
    row = entry["row"]
    attempts = [dict(item) for item in (row.get("attempts") or ())]
    last = attempts[-1] if attempts else {}
    channel = str(entry.get("channel"))
    terminal = classify_attempt(last) if attempts else TERMINAL_UNFINISHED
    digest: Dict[str, Any] = {"state": "no_attempt", "detail": "无尝试记录"}
    if attempts and str(last.get("status")) == "completed":
        digest = verify_result_digest(channel=channel, row=row, attempt=last)
        if digest.get("state") == "mismatch":
            terminal = TERMINAL_DIGEST_MISMATCH
    charged = sum(float((item.get("cost") or {}).get("tables") or 0.0)
                  for item in attempts)
    failure_cost = sum(float((item.get("cost") or {}).get("tables") or 0.0)
                       for item in attempts if is_failure_cost_attempt(item))
    return {"key": key_of_observed(entry), "channel": channel,
            "iteration": entry.get("iteration"), "candidate_id": row.get("candidate_id"),
            "opponent_mix": row.get("opponent_mix"),
            "source_root_id": row.get("source_root_id"),
            "root_index": row.get("root_index"), "root_seed": row.get("root_seed"),
            "seat": row.get("seat"), "arm": row.get("arm"),
            "schedule": row.get("schedule"), "scope": row.get("evaluation_scope"),
            "attempts": len(attempts),
            "attempt_statuses": [a.get("status") for a in attempts],
            "terminal": terminal, "reason": last.get("reason"),
            "tables_attempted": charged, "tables_failure_cost": failure_cost,
            "tables_planned": row.get("planned_tables"), "digest": digest,
            "ledger_key": entry.get("ledger_key"),
            "iteration_dir": entry.get("iteration_dir")}


#: 家族根身份的命名空间标记（与 `channel_of_run_row` 用**同一个**判据，
#: 不另造一套"看起来像家族"的启发式）。
FAMILY_ROOT_MARKER = "av-eval-"
_FAMILY_STEP_RE = re.compile(r"-s\d+-idx\d+")
_LEDGER_STEP_SUFFIXES = (":tables-full", ":tables-partial", ":tables_full",
                         ":tables_partial", "-tables-full", "-tables-partial")


def parse_ledger_step_identity(step_id: Any) -> Dict[str, Any]:
    """账步 → **结构化归属身份**（通道 / 候选 / 子场景 / 情景 / 根序号 / 根种子 / 完整根）。

    生产实证的三族形状（含 tables-* 后缀）：

    - `natural:<cid12>:<mix>:<roots>`；
    - `evaluate:<cid12>:<sub>:<mix>-s<panel_seed>-idx<n>`= 家族**新根发现**评价，
      `evaluate:<cid12>:<sub>:<sub>|<mix>|<完整家族根 id>:tables-*`= 家族**指定旧根重评**，
      `declare:<iter>:<sub>:<mix>-s<seed>-idx<n>`= 家族补根**声明**；
    - `evaluate:<cid12>:<predicate>`及其 `:tables-full` / `:tables-partial`
      = 条件通道（前缀生成 / 完整评价）。

    家族与条件的区分**不看位置看身份**：家族步里带完整家族根 id 或 `-s<seed>-idx<n>`
    标记，条件步不带。旧口径只认前一种标记，于是第 2 轮`指定旧根重评`的 32 桌被算进
    条件通道（复审 §"现有真实证据怎样签收"里的 ±32 差额）。
    """

    step = str(step_id or "")
    core = step
    for suffix in _LEDGER_STEP_SUFFIXES:
        if core.endswith(suffix):
            core = core[: -len(suffix)]
            break
    parts = core.split(":")
    head = parts[0]
    ident: Dict[str, Any] = {
        "step_id": step, "head": head, "kind": None, "candidate": None,
        "sub_scenario": None, "opponent_mix": None, "root_index": None,
        "root_seed": None, "root_seed_basis": None, "root_id": None,
        "iteration_hint": None, "step_role": None}
    if head == "natural":
        ident.update({"kind": "natural",
                      "candidate": parts[1] if len(parts) > 1 else None,
                      "opponent_mix": parts[2] if len(parts) > 2 else None})
        return ident
    if head == "refresh":
        # 生产实证（`sitin_search._av_refresh_run`，P21/run9）：
        # `step_prefix = "refresh:{cid12}:{mix}:"`，`step_id` 再拼
        # `natural_selection_token(indexes)`（只补缺失根的**选择集记号**，如 `idx3-4`）。
        # 这是**整体(normal)通道刷新批**的真实桌赛（与自然面板同一账户 tables_full、
        # 同一种面板产物 `iterations/*/refresh/<cid12>-<mix>/panel.json`）⇒ 归自然组。
        token = ":".join(parts[3:]) if len(parts) > 3 else ""
        ident.update({"kind": "natural", "step_role": "normal_refresh_batch",
                      "candidate": parts[1] if len(parts) > 1 else None,
                      "opponent_mix": parts[2] if len(parts) > 2 else None,
                      "selection_token": token})
        return ident
    if head == "declare":
        tail = parts[3] if len(parts) > 3 else ""
        marker = re.search(r"([HM])-s(\d+)-idx(\d+)", tail)
        ident.update({"kind": "family", "step_role": "declaration",
                      "iteration_hint": parts[1] if len(parts) > 1 else None,
                      "sub_scenario": parts[2] if len(parts) > 2 else None})
        if marker:
            ident.update({"opponent_mix": marker.group(1),
                          "root_seed": int(marker.group(2)),
                          "root_seed_basis": "panel_seed",
                          "root_index": int(marker.group(3))})
        return ident
    if head != "evaluate":
        ident["kind"] = "other:" + head
        return ident
    ident["candidate"] = parts[1] if len(parts) > 1 else None
    ident["sub_scenario"] = parts[2] if len(parts) > 2 else None
    tail = ":".join(parts[3:])
    family = bool(_FAMILY_STEP_RE.search(core)) or (FAMILY_ROOT_MARKER in core)
    if not family:
        ident["kind"] = "conditional"
        return ident
    ident["kind"] = "family"
    if FAMILY_ROOT_MARKER in core:
        root_id = core[core.index(FAMILY_ROOT_MARKER):]
        descriptor = descriptor_from_root_id(root_id)
        ident.update({"root_id": root_id,
                      "sub_scenario": descriptor.get("sub_scenario")
                      or ident["sub_scenario"],
                      "opponent_mix": descriptor.get("opponent_mix"),
                      "root_index": descriptor.get("root_index"),
                      "root_seed": descriptor.get("root_seed"),
                      "root_seed_basis": "execution_seed"})
        return ident
    marker = re.search(r"([HM])-s(\d+)-idx(\d+)", tail)
    if marker:
        ident.update({"opponent_mix": marker.group(1),
                      "root_seed": int(marker.group(2)),
                      "root_seed_basis": "panel_seed",
                      "root_index": int(marker.group(3))})
    return ident


def classify_ledger_step(step_id: Any) -> str:
    """账步 → 通道（`natural` / `conditional` / `family` / `other:<head>`）。

    与 `parse_ledger_step_identity` **同一个判据**：不在这里另写一套正则，
    否则两个检查器会对同一步给出不同归属（正是本次要修的"归属未闭合"）。
    """

    return str(parse_ledger_step_identity(step_id).get("kind"))


def refresh_batch_records(run_root: Path) -> List[Dict[str, Any]]:
    """整体(normal)通道**刷新批**的盘上记录（生产自己写的，单一来源）。

    来源优先级：
    1. `iterations/*/checkpoints/refresh-<cid12>-<mix>.json`（`sitin-av-checkpoint/1`）：
       带 `cost_charged` / `instance_keys` / `result_path` / `result_sha256` / `step_id`；
    2. `iterations/*/state.json` 的 `refresh_fill.attempts`（回退：带 `root_ids` /
       `root_indexes` / `seats_per_root` / `planned_tables` / `step_id`）。

    背景（P21/run9）：该批是设计 §537 阶段 2`给本次参加通道重排的**所有身份**补齐`
    产生的真实桌赛（2 根 × 4 座 × 2 臂 × 2 桌 = 32 桌/情景），账步前缀是 `refresh:`：
    旧归属把它当"未知类目"，于是自然组少算 64 桌、与实例侧对不上（+64 差额）。
    """

    out: List[Dict[str, Any]] = []
    for iter_dir in iter_dirs(Path(run_root)):
        state = read_json(iter_dir / "state.json") or {}
        attempts = {
            (str(row.get("candidate_id")), str(row.get("opponent_mix"))): dict(row)
            for row in ((state.get("refresh_fill") or {}).get("attempts") or ())
            if isinstance(row, Mapping)}
        for path in sorted((iter_dir / "checkpoints").glob("refresh-*.json")):
            payload = read_json(path) or {}
            key = (str(payload.get("candidate_id")),
                   str(payload.get("mix")))
            attempt = attempts.get(key, {})
            instance_keys = list(payload.get("instance_keys") or ())
            completed = list(((payload.get("instances") or {}).get("completed")) or ())
            root_ids = list(attempt.get("root_ids") or ())
            root_indexes = list(attempt.get("root_indexes") or ())
            if not root_ids and attempt.get("root_ids") is None:
                root_ids = sorted({parse_key(item).get("root") for item in instance_keys
                                   if parse_key(item).get("root")})
            out.append({
                "iteration": _ordinal(state.get("iteration_no")
                                      or iter_dir.name),
                "iteration_dir": iter_dir.name,
                "candidate_id": payload.get("candidate_id"),
                "opponent_mix": payload.get("mix"),
                "step_id": payload.get("step_id") or attempt.get("step_id"),
                "root_ids": root_ids, "root_indexes": root_indexes,
                "seats_per_root": attempt.get("seats_per_root"),
                "status": payload.get("status"),
                "cost_charged": float(payload.get("cost_charged") or 0.0),
                "planned_tables": float(attempt.get("planned_tables")
                                        or payload.get("cost_planned") or 0.0),
                "expected_instances": len(instance_keys),
                "completed_instances": len(completed),
                "instance_keys": instance_keys,
                "panel_path": payload.get("result_path"),
                "result_sha256": payload.get("result_sha256"),
                "checkpoint_path": str(path),
                "basis": ("整体(normal)通道刷新批（设计 §537 阶段 2：给参与重排的所有身份"
                          "补齐新刷新根）——生产检查点 refresh-<cid12>-<mix>.json")})
    return out


def ledger_channel_charges(ledger: Mapping[str, Any]) -> Dict[str, Any]:
    """账本 → 通道费用（逐组比，不用总额互相冲抵），并保留**逐行归属身份**供实例 join。"""

    groups: Dict[str, Dict[str, float]] = {name: {} for name in COST_GROUPS}
    failure_cost: Dict[str, float] = {name: 0.0 for name in COST_GROUPS}
    unmatched: List[Dict[str, Any]] = []
    attributed: List[Dict[str, Any]] = []
    group_of_kind = {"natural": "natural_panel(H/M)", "family": CHANNEL_FAMILY,
                     "conditional": "conditional(prefix/refill)"}
    for row in (ledger.get("reservations") or ()):
        step = str(row.get("step_id") or "")
        account = str(row.get("account") or "")
        charged = float(row.get("charged") or 0.0)
        ident = parse_ledger_step_identity(step)
        kind = str(ident.get("kind"))
        group = group_of_kind.get(kind)
        record = {"step_id": step, "account": account, "charged": charged,
                  "status": row.get("status"),
                  "superseded": bool(row.get("superseded")),
                  "kind": kind, "group": group,
                  "identity": {key: value for key, value in ident.items()
                               if key != "step_id"}}
        if group is None:
            if charged:
                unmatched.append(record)
            continue
        groups[group][account] = round(groups[group].get(account, 0.0) + charged, 6)
        if bool(row.get("superseded")):
            failure_cost[group] = round(failure_cost[group] + charged, 6)
        record["attributed"] = True
        attributed.append(record)
    inflight_rows = []
    for row in (ledger.get("reservations") or ()):
        if str(row.get("status")) == "reserved" \
                and str(row.get("account")) == "tables_full":
            inflight_rows.append(dict(row, kind=classify_ledger_step(
                row.get("step_id"))))
    return {"groups": groups, "failure_cost_retained": failure_cost,
            "inflight_rows": inflight_rows,
            "rows": attributed,
            "unmatched_charged_rows": unmatched,
            "note": ("superseded 行 = 旧尝试让位后**保留的费用**（失败重试的真实成本），"
                     "单列不当作重复收费；重复收费判据是同 (step_id, account) 多条"
                     "非 superseded 的 settled 行；归属按**结构化身份**（通道/候选/子场景/"
                     "情景/根）判，族内两种账步形状（新根发现 / 指定旧根重评）都归家族。")}


def reconcile_instances(run_root: Path, plan: Mapping[str, Any]) -> Dict[str, Any]:
    """逐冻结实例键 join 计划 ↔ 尝试 ↔ 结果 ↔ 费用，并按通道分开出终态。"""

    run_root = Path(run_root)
    expected = plan_expected_instances(plan)
    observed = observed_instances(run_root)
    ledger = read_json(run_root / "av-ledger.json") or {}
    charges = ledger_channel_charges(ledger)
    by_channel: Dict[str, Dict[str, Any]] = {}
    for channel in CHANNELS:
        exp_rows = [row for row in expected if row["channel"] == channel]
        obs_entries = [entry for entry in observed if entry["channel"] == channel]
        drop_root = channel in (CHANNEL_FAMILY,)
        exp_map: Dict[str, List[Dict[str, Any]]] = {}
        for row in exp_rows:
            key = key_of_expected(row)
            exp_map.setdefault(_norm_runtime_root(key) if drop_root else key,
                               []).append(row)
        obs_map: Dict[str, List[Dict[str, Any]]] = {}
        for entry in obs_entries:
            key = key_of_observed(entry)
            obs_map.setdefault(_norm_runtime_root(key) if drop_root else key,
                               []).append(entry)
        missing = sorted(set(exp_map) - set(obs_map))
        unplanned = sorted(set(obs_map) - set(exp_map))
        items = [_terminalize(entry) for entry in obs_entries]
        terminals: Dict[str, int] = {}
        digest_states: Dict[str, int] = {}
        for item in items:
            terminals[item["terminal"]] = terminals.get(item["terminal"], 0) + 1
            state = str((item.get("digest") or {}).get("state"))
            digest_states[state] = digest_states.get(state, 0) + 1
        by_channel[channel] = {
            "expected_instances": len(exp_rows),
            "observed_instances": len(obs_entries),
            "missing_expected_keys": missing,
            "unplanned_observed_keys": unplanned,
            "terminal_counts": terminals, "digest_states": digest_states,
            "retry_instances": [
                {"key": item["key"], "attempts": item["attempt_statuses"],
                 "charged_tables": item["tables_attempted"],
                 "failure_cost_tables": item["tables_failure_cost"]}
                for item in items if int(item["attempts"] or 0) > 1],
            "failure_cost_tables": round(sum(float(item["tables_failure_cost"])
                                             for item in items), 6),
            "instance_tables": round(sum(float(item["tables_attempted"])
                                         for item in items), 6),
            "ledger_charged": dict((charges["groups"].get(channel) or {})),
            "items": items, "expected_rows": exp_rows,
        }
    # RootWitness（P11）：按来源根把见证挂到逐实例读数上（缺见证的实例如实为空）。
    witnesses = witnesses_by_root(run_root)
    for channel in (CHANNEL_FAMILY, CHANNEL_NATURAL, CHANNEL_SHARED_BASELINE):
        for item in ((by_channel.get(channel) or {}).get("items") or ()):
            hits = witnesses.get(str(item.get("source_root_id")) or "")
            if not hits:
                continue
            verdict = witness_verdict(hits[0])
            item["root_witness"] = verdict
            item["digest"] = dict(item.get("digest") or {}, witness=verdict)
    conditional_index = conditional_instances(run_root)
    by_channel[CHANNEL_CONDITIONAL] = _conditional_channel(
        conditional_index, expected, by_channel[CHANNEL_CONDITIONAL],
        witnesses=witnesses, run_root=run_root)
    join: Dict[str, Any] = {
        "schema": "sitin-gate2-instance-join/1",
        "run_root": str(run_root),
        "plan_candidate_slots": sorted({
            str(row.get("plan_candidate_slot")) for row in expected}),
        "channels": by_channel,
        "conditional_index": conditional_index,
        "reuse_references": _reuse_references(run_root),
        "ledger_charges": charges,
        "note": ("逐通道分开 join：自然、条件、家族、共享缓存彼此**不得补齐**；"
                 "逐项终态只允许 completed_verifiable / explicit_failure / "
                 "budget_not_executed（未终结与摘要不符另列，不混进这三类）。"),
    }
    join["missing_split"] = split_missing(run_root, join)
    return join


def _conditional_kind(category: Any) -> str:
    """计划类目 → 条件通道的实例种类（前缀生成 / 完整评价）。"""

    return ("conditional_prefix" if "prefix" in str(category)
            else "conditional_full")


def _conditional_channel(index: Sequence[Mapping[str, Any]],
                         expected: Sequence[Mapping[str, Any]],
                         base: Mapping[str, Any],
                         witnesses: Optional[Mapping[str, List[Dict[str, Any]]]] = None,
                         run_root: Optional[Path] = None) -> Dict[str, Any]:
    """条件通道：**冻结后按完整实例键逐实例连接**（候选 / 通道 / 完整根 / 情景 / 座位 / 臂 / 赛程）。

    复审 C2（R9-FROZEN-CHANGES-REREVIEW §C2）指出的两个缺口与本次口径：

    1. 旧口径按**迭代标签**对账（`missing_labels`），评价产物里有什么臂就认什么臂：
       把 `baseline` 改名成 `unexpected_arm` 后行数不变 ⇒ 全部检查 PASS、缺键为空。
       新口径先把**运行期才解析的根具名绑定**到计划需求项（`requirement_id` 取计划行的
       `instance_key`），再按完整实例键核对完成项：预期臂缺失与额外臂/额外根都进
       缺失 / 计划外集合，别的通道与总行数补不了。
    2. 旧口径用 RootWitness 顶替结果摘要（`witness_verified`）：候选臂同一桌两座位分数各改
       ±100 后仍 PASS。新口径以**完成时登记的结果摘要**（完成事务的文件字节摘要 / 迭代状态
       里的规范结果载荷）为准，对账时重算并比较；没有登记 ⇒ INSUFFICIENT。
       见证只作根见证（`root_witness`），不作结果完整性。
    """

    witnesses = dict(witnesses or {})
    plan_rows = [row for row in expected if row["channel"] == CHANNEL_CONDITIONAL]
    plan_by_iter: Dict[str, List[Dict[str, Any]]] = {}
    for row in plan_rows:
        plan_by_iter.setdefault(_ordinal(row.get("iteration")), []).append(row)

    expected_rows: List[Dict[str, Any]] = []
    observed_rows: List[Dict[str, Any]] = []
    bindings: List[Dict[str, Any]] = []
    identity_conflicts: List[Dict[str, Any]] = []
    seat_conflicts: List[Dict[str, Any]] = []
    attestation_states: Dict[str, int] = {}
    extra_observations: List[Dict[str, Any]] = []
    observed_labels: List[str] = []

    for entry in index:
        label = str(entry.get("iteration"))
        ordinal = _ordinal(label)
        observed_labels.append(label)
        rows_for_iter = list(plan_by_iter.get(ordinal) or ())
        samples = [row for row in (entry.get("samples") or ())
                   if isinstance(row, Mapping)]
        registration = dict(entry.get("registration") or {})
        registered_roots = [dict(row) for row in (registration.get("registered_roots") or ())
                            if isinstance(row, Mapping) and row.get("root_id")]
        registered_ids = {str(row.get("root_id")) for row in registered_roots}
        digest = dict(entry.get("digest_verdict") or {})
        digest_state = str(digest.get("state") or "no_recorded_digest")
        ok = entry.get("ok")
        reason = str(entry.get("reason") or "")
        budget = any(marker in reason for marker in _BUDGET_MARKERS)
        iter_status = str(entry.get("iteration_status") or "")
        iter_stop = str(entry.get("iteration_stop_reason") or "")

        sample_state: List[Dict[str, Any]] = []
        for sample in samples:
            identity = dict(sample.get("root_identity") or {})
            root_id = str(identity.get("root_id") or "")
            hits = witnesses.get(root_id) or []
            witness = (witness_verdict(hits[0], recomputed_requirement=None) if hits
                       else {"present": False, "matched": None,
                             "reason": "该根没有 RootWitness 附属文件"})
            if witness.get("present") and sample.get("root_seed") is not None:
                witness["seed_consistent"] = (witness.get("actual_seed")
                                              == sample.get("root_seed"))
            seat_info = conditional_seat_binding(sample, hits)
            attested_by = []
            if root_id and root_id in registered_ids:
                attested_by.append("iteration_state_payload")
            if witness.get("present"):
                attested_by.append("root_witness")
            seat_bound = seat_info.get("seat")
            if seat_info.get("conflict"):
                seat_conflicts.append({
                    "iteration": ordinal, "root_id": root_id,
                    "votes": dict(seat_info.get("votes") or {}),
                    "detail": "同一个根的**多个具名座位来源互相矛盾**（座位不可信）"})
            sample_state.append({
                "identity": identity, "root_id": root_id, "witness": witness,
                "seat_info": seat_info, "seat_bound": seat_bound,
                "attested_by": attested_by,
                "attestation": ("attested" if attested_by else "unattested"),
                "arm_completeness": dict(sample.get("arm_completeness") or {}),
                "file_sha256": sample.get("file_sha256")})

        # 本迭代的**受证根**：登记载荷里的根 + 有见证的根。没有受证根时按产物自身根绑定，
        # 但读数据实记 unattested（⇒ 该通道摘要必为 INSUFFICIENT，不冒充可核）。
        attested_roots = [str(row.get("root_id")) for row in registered_roots]
        for state_row in sample_state:
            if state_row["witness"].get("present") and state_row["root_id"] \
                    and state_row["root_id"] not in attested_roots:
                attested_roots.append(state_row["root_id"])
        if not rows_for_iter:
            # 计划迭代之外的条件评价：单列，既不当完成、也不当丢失。
            for state_row in sample_state:
                for arm in sorted(state_row["arm_completeness"]):
                    extra_observations.append({
                        "iteration": ordinal, "iteration_label": label,
                        "root_id": state_row["root_id"], "arm": arm,
                        "digest_state": digest_state,
                        "note": "计划迭代之外的条件评价（不计入计划实例）"})
            continue

        # 绑定来源：**受证根优先**（登记载荷写明 / 有见证）。产物里出现而未被证实的根
        # 单列成根身份冲突，它的行只能落进"计划外"，绝不顶替需求项。
        binding_sources: List[Dict[str, Any]] = []
        if attested_roots:
            for root_id in attested_roots:
                product_row = next((row for row in sample_state
                                    if row["root_id"] == root_id), None)
                if product_row is not None:
                    binding_sources.append(dict(product_row))
                    continue
                registered = next((dict(row) for row in registered_roots
                                   if str(row.get("root_id")) == root_id), {})
                binding_sources.append({
                    "identity": registered, "root_id": root_id,
                    "witness": {"present": False, "matched": None,
                                "reason": "该受证根没有现场样本（完成项缺失）"},
                    "seat_info": {"votes": {}, "seat": None, "conflict": False,
                                  "basis": "无座位来源（按计划座位记）"},
                    "seat_bound": None, "attested_by": ["iteration_state_payload"],
                    "attestation": "attested", "arm_completeness": {},
                    "file_sha256": None})
            for state_row in sample_state:
                if state_row["root_id"] not in attested_roots:
                    identity_conflicts.append({
                        "iteration": ordinal, "root_id": state_row["root_id"],
                        "attested_roots": sorted(attested_roots),
                        "detail": ("评价产物里的根**没有被任何登记/见证证实**"
                                   "（受证根另在）：不得当作已完成实例")})
        else:
            binding_sources = [dict(row, attestation="unattested")
                               for row in sample_state[:1]]

        for state_row in binding_sources:
            identity = state_row["identity"]
            root_id = state_row["root_id"]
            bound_seat = (int(state_row["seat_bound"])
                          if state_row.get("seat_bound") is not None else None)
            for row in rows_for_iter:
                plan_seat = int(row.get("seat") or 0)
                if bound_seat is not None and plan_seat != bound_seat:
                    seat_conflicts.append({
                        "iteration": ordinal,
                        "requirement_id": row.get("instance_key") or key_of_expected(row),
                        "plan_seat": plan_seat, "bound_seat": bound_seat,
                        "basis": state_row["seat_info"].get("basis"),
                        "root_id": root_id,
                        "detail": "计划座位的具名来源不一致（座位对不上）"})
                seat = bound_seat if bound_seat is not None else plan_seat
                key = instance_key(iteration=ordinal, channel=CHANNEL_CONDITIONAL,
                                   mix=identity.get("opponent_mix"),
                                   root_id=identity.get("root_id"),
                                   root_index=identity.get("root_index"),
                                   root_seed=identity.get("root_seed"), seat=seat,
                                   arm=row.get("arm"), schedule=row.get("schedule"))
                requirement_id = row.get("instance_key") or key_of_expected(row)
                expected_rows.append({
                    "key": key, "requirement_id": requirement_id,
                    "iteration": ordinal, "iteration_label": label,
                    "channel": CHANNEL_CONDITIONAL, "arm": row.get("arm"),
                    "kind": _conditional_kind(row.get("category")),
                    "schedule": row.get("schedule"), "seat": seat,
                    "planned_tables": row.get("planned_tables"),
                    "opponent_mix": identity.get("opponent_mix"),
                    "source_root_id": identity.get("root_id"),
                    "root_index": identity.get("root_index"),
                    "root_seed": identity.get("root_seed"),
                    "attested_by": list(state_row["attested_by"]),
                    "attestation": state_row["attestation"],
                    "witness": state_row["witness"], "digest_state": digest_state,
                    "binding_basis": ("运行期根身份具名绑定到计划需求项"
                                      "（root_id/root_index/root_seed/mix/cell/seat）")})
                bindings.append({
                    "iteration": ordinal, "requirement_id": requirement_id,
                    "arm": row.get("arm"), "schedule": row.get("schedule"),
                    "bound_root_id": identity.get("root_id"),
                    "bound_root_index": identity.get("root_index"),
                    "bound_root_seed": identity.get("root_seed"),
                    "bound_opponent_mix": identity.get("opponent_mix"),
                    "bound_sub_scenario": identity.get("sub_scenario"),
                    "bound_seat": seat,
                    "seat_basis": state_row["seat_info"].get("basis"),
                    "attested_by": list(state_row["attested_by"]),
                    "binding_basis": ("计划行只给迭代/候选/臂/赛程；根在运行期才解析 ⇒ "
                                      "先具名绑定到该需求项，再核对该键的完成项"),
                })

        # —— 完成项（实际观察）：**按产物逐样本**如实取（未被证实的根也要观察成"计划外"，
        # 不能因为绑定来源不同就少看一条完成项）——
        for state_row in sample_state:
            identity = state_row["identity"]
            bound_seat = (int(state_row["seat_bound"])
                          if state_row.get("seat_bound") is not None else None)
            for arm, block in sorted((state_row["arm_completeness"] or {}).items()):
                plan_row = next((row for row in rows_for_iter
                                 if str(row.get("arm")) == str(arm)
                                 and _conditional_kind(row.get("category"))
                                 == "conditional_full"), None)
                schedule = (plan_row.get("schedule") if plan_row
                            else "conditional_stage:2_tables")
                seat = bound_seat if bound_seat is not None else int(
                    (plan_row or {}).get("seat") or 0)
                terminal = (TERMINAL_COMPLETED
                            if ok and block.get("status") == "complete"
                            and block.get("usable")
                            else (TERMINAL_BUDGET if budget else TERMINAL_FAILED))
                observed_rows.append({
                    "key": instance_key(iteration=ordinal, channel=CHANNEL_CONDITIONAL,
                                        mix=identity.get("opponent_mix"),
                                        root_id=identity.get("root_id"),
                                        root_index=identity.get("root_index"),
                                        root_seed=identity.get("root_seed"), seat=seat,
                                        arm=arm, schedule=schedule),
                    "requirement_id": (plan_row.get("instance_key") if plan_row
                                       else None),
                    "iteration": ordinal, "channel": CHANNEL_CONDITIONAL,
                    "kind": "conditional_full", "arm": arm,
                    "candidate_id": entry.get("candidate_id"),
                    "opponent_mix": identity.get("opponent_mix"),
                    "source_root_id": identity.get("root_id"),
                    "root_index": identity.get("root_index"),
                    "root_seed": identity.get("root_seed"), "seat": seat,
                    "schedule": schedule,
                    "attempts": 1,
                    "attempt_statuses": ["completed" if terminal == TERMINAL_COMPLETED
                                         else "failed"],
                    "tables_attempted": float(block.get("tables") or 0.0),
                    "tables_failure_cost": 0.0, "tables_planned": 2.0,
                    "terminal": terminal, "reason": reason or None,
                    "root_witness": state_row["witness"],
                    "digest": {
                        "schema": CONDITIONAL_DIGEST_SCHEMA, "state": digest_state,
                        "registered": dict(digest.get("registered") or {}),
                        "recomputed": dict(digest.get("recomputed") or {}),
                        "registration_kinds": list(digest.get("registration_kinds") or ()),
                        "result_path": digest.get("result_path"),
                        "mismatches": list(digest.get("mismatches") or ()),
                        "witness": state_row["witness"],
                        "detail": (digest.get("detail") or
                                   "登记摘要缺失 ⇒ 结果完整性 INSUFFICIENT")},
                })

        # —— 前缀生成行（前缀尝试的真实成本）：终态三分，绝不把"没跑到"当通过 ——
        first = sample_state[0] if sample_state else {}
        first_identity = dict(first.get("identity") or {})
        prefix_plan = next((row for row in rows_for_iter
                            if _conditional_kind(row.get("category"))
                            == "conditional_prefix"), None)
        if first_identity or prefix_plan:
            seat = (int(first["seat_bound"]) if first.get("seat_bound") is not None
                    else int((prefix_plan or {}).get("seat") or 0))
            prefix_terminal = (
                TERMINAL_COMPLETED if ok else
                TERMINAL_BUDGET if any(marker in iter_stop for marker in _BUDGET_MARKERS)
                else TERMINAL_UNFINISHED if iter_status in (
                    "RESERVED", "NATURAL_EVALUATED", "CONDITIONAL_EVALUATED",
                    "ARCHIVE_COMMITTED", "SUMMARIZED", "")
                else TERMINAL_FAILED)
            arm = str((prefix_plan or {}).get("arm") or "candidate")
            schedule = str((prefix_plan or {}).get("schedule") or "prefix_attempts_cap:8")
            observed_rows.append({
                "key": instance_key(iteration=ordinal, channel=CHANNEL_CONDITIONAL,
                                    mix=first_identity.get("opponent_mix"),
                                    root_id=first_identity.get("root_id"),
                                    root_index=first_identity.get("root_index"),
                                    root_seed=first_identity.get("root_seed"), seat=seat,
                                    arm=arm, schedule=schedule),
                "requirement_id": (prefix_plan.get("instance_key") if prefix_plan
                                   else None),
                "iteration": ordinal, "channel": CHANNEL_CONDITIONAL,
                "kind": "conditional_prefix", "arm": arm,
                "opponent_mix": first_identity.get("opponent_mix"),
                "source_root_id": first_identity.get("root_id"),
                "root_index": first_identity.get("root_index"),
                "root_seed": first_identity.get("root_seed"), "seat": seat,
                "schedule": schedule,
                "attempts": 1,
                "attempt_statuses": ["completed" if prefix_terminal
                                     == TERMINAL_COMPLETED else "failed"],
                "tables_attempted": float(entry.get("tables_partial_charged") or 0.0),
                "tables_failure_cost": 0.0, "tables_planned": 8.0,
                "terminal": prefix_terminal, "reason": reason or iter_stop or None,
                "prefix_attempts": entry.get("prefix_attempts"),
                "root_witness": dict(first.get("witness") or {}),
                "digest": {
                    "schema": CONDITIONAL_DIGEST_SCHEMA, "state": digest_state,
                    "registered": dict(digest.get("registered") or {}),
                    "recomputed": dict(digest.get("recomputed") or {}),
                    "registration_kinds": list(digest.get("registration_kinds") or ()),
                    "result_path": digest.get("result_path"),
                    "mismatches": list(digest.get("mismatches") or ()),
                    "witness": dict(first.get("witness") or {}),
                    "detail": (digest.get("detail") or
                               "登记摘要缺失 ⇒ 结果完整性 INSUFFICIENT")},
            })

    for row in expected_rows:
        state = str(row.get("attestation"))
        attestation_states[state] = attestation_states.get(state, 0) + 1

    expected_map = {row["key"]: row for row in expected_rows}
    observed_map = {row["key"]: row for row in observed_rows}
    missing = sorted(set(expected_map) - set(observed_map))
    unplanned = sorted(set(observed_map) - set(expected_map))
    terminal_counts: Dict[str, int] = {}
    digest_states: Dict[str, int] = {}
    for row in observed_rows:
        terminal_counts[row["terminal"]] = terminal_counts.get(row["terminal"], 0) + 1
        state = str((row.get("digest") or {}).get("state"))
        digest_states[state] = digest_states.get(state, 0) + 1

    return {
        "expected_instances": len(expected_rows),
        "observed_instances": len(observed_rows),
        "source": "实际评价产物（iterations/*/conditional/evaluation.json）+ 计划需求项的具名绑定",
        "missing_expected_keys": missing,
        "unplanned_observed_keys": unplanned,
        "missing_requirement_ids": [expected_map[key].get("requirement_id")
                                    for key in missing],
        "unplanned_requirements": [observed_map[key].get("arm") for key in unplanned],
        "bindings": bindings,
        "identity_conflicts": identity_conflicts,
        "seat_conflicts": seat_conflicts,
        "attestation_states": attestation_states,
        "expected_rows": expected_rows,
        "terminal_counts": terminal_counts, "digest_states": digest_states,
        "retry_instances": [],
        "failure_cost_tables": 0.0,
        "instance_tables": round(sum(float(row.get("tables_attempted") or 0.0)
                                     for row in observed_rows), 6),
        "ledger_charged": dict(base.get("ledger_charged") or {}),
        "items": observed_rows, "extra_observations": extra_observations,
        "plan_rows": plan_rows, "conditional_index": list(index),
        "note": ("条件通道没有实例台账 ⇒ 从实际评价产物建立索引，但**先按候选/通道/完整根/"
                 "情景/座位/臂/赛程具名绑定到计划需求项**再核对完成项；结果完整性以完成时"
                 "登记的结果摘要为准（无登记记 INSUFFICIENT），RootWitness 只作根见证；"
                 "计划迭代之外的条件评价单列 extra_observations"),
    }


def _reuse_references(run_root: Path) -> List[Dict[str, Any]]:
    """复用**只记引用**：面板级检查点里的 `reused_from`（不重跑就不重复计费）。"""

    out: List[Dict[str, Any]] = []
    for _label, state_path in state_files(Path(run_root)):
        for path in sorted((state_path.parent / "checkpoints").glob("*.json")):
            payload = read_json(path)
            if not isinstance(payload, Mapping):
                continue
            reused = payload.get("reused_from")
            if not reused:
                continue
            out.append({"iteration_dir": str(path.parent), "checkpoint": path.name,
                        "reused_from": reused, "result_path": payload.get("result_path"),
                        "result_sha256": payload.get("result_sha256"),
                        "instance_keys": list(payload.get("instance_keys") or ()),
                        "cost_charged": payload.get("cost_charged"),
                        "reference_only": True})
    return out


# ===========================================================================
# 家族根评价产物索引（共同根比较的覆盖来源；两种目录形态都读）
# ===========================================================================


def root_witnesses(run_root: Path) -> List[Dict[str, Any]]:
    """读 P11 落地的 **RootWitness**（`root-witnesses.jsonl` 附属文件 + 同名目录）。

    裁定 §4.2 要求"内容见证要来自真实运行"，并允许"落生产审计附属文件"。
    生产实现（`AV_ROOT_WITNESS_SIDECAR = "root-witnesses.jsonl"`）在条件入口与
    指定根入口都把见证写成附属文件，字段包含
    `requirement_digest`（冻结参数可重算）/ `content_digest`（现场内容）/ `actual_seed` /
    `seed_matches_descriptor` / `cut_window_key` / `prefix_sha256` /
    `observation_summary_sha256` / `serialization_version`。

    两种落地形态都读：`.../root-witnesses.jsonl`（逐行）与
    `.../root-witnesses/<hash>.json`（逐根）。
    """

    root = Path(run_root)
    records: List[Dict[str, Any]] = []
    for path in sorted(root.glob("iterations/**/root-witnesses.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            payload = read_json_text(line)
            if isinstance(payload, Mapping):
                records.append(dict(payload, _sidecar=str(path)))
    for path in sorted(root.glob("iterations/**/root-witnesses/*.json")):
        payload = read_json(path)
        if isinstance(payload, Mapping):
            records.append(dict(payload, _sidecar=str(path)))
    for row in records:
        witness = dict(row.get("witness") or {})
        row["witness"] = witness
        row["root_id"] = (witness.get("root_id")
                          or (row.get("instance") or {}).get("root_id"))
        row["source_root_id"] = (witness.get("source_root_id")
                                 or (row.get("instance") or {}).get("source_root_id"))
        row["entry"] = (row.get("instance") or {}).get("entry") or witness.get("entry")
    return records


def read_json_text(text: str) -> Optional[Any]:
    try:
        return json.loads(text)
    except ValueError:
        return None


def witness_verdict(record: Mapping[str, Any], *,
                    recomputed_requirement: Optional[str] = None) -> Dict[str, Any]:
    """一条 RootWitness 的**两个结论**：见证存在（`present`）与要求摘要对拍（`matched`）。

    - `present`：见证带内容摘要、`capture.captured is True`、序列化版本与根身份齐全；
    - `matched`：见证里的 `requirement_digest` 与**冻结参数重算值**逐字一致
      （只有在给定 `recomputed_requirement` 时才判定；否则记 `unknown`）。
    """

    witness = dict(record.get("witness") or {})
    capture = dict(witness.get("capture") or {})
    present = bool(witness.get("content_digest")) and bool(
        capture.get("captured", True)) and bool(witness.get("root_id") or
                                                record.get("root_id"))
    verdict: Dict[str, Any] = {
        "present": present,
        "matched": None,
        "actual_seed": witness.get("actual_seed"),
        "seed_matches_descriptor": witness.get("seed_matches_descriptor"),
        "requirement_digest": witness.get("requirement_digest"),
        "content_digest": witness.get("content_digest"),
        "cut_window_key": witness.get("cut_window_key"),
        "prefix_sha256": witness.get("prefix_sha256"),
        "observation_summary_sha256": witness.get("observation_summary_sha256"),
        "serialization_version": witness.get("serialization_version"),
        "entry": record.get("entry"),
        "sidecar": record.get("_sidecar"),
    }
    if recomputed_requirement and verdict["requirement_digest"]:
        verdict["matched"] = str(verdict["requirement_digest"]) == str(
            recomputed_requirement)
    if not present:
        verdict["reason"] = "见证不完整（缺内容摘要或捕获标记）"
    elif verdict["matched"] is False:
        verdict["reason"] = "见证要求摘要与冻结参数重算值不一致"
    elif verdict["matched"] is True:
        verdict["reason"] = "见证要求摘要与冻结参数重算值逐字一致"
    else:
        verdict["reason"] = "见证存在；未给重算值 ⇒ 对拍结论未知"
    return verdict


def witnesses_by_root(run_root: Path) -> Dict[str, List[Dict[str, Any]]]:
    out: Dict[str, List[Dict[str, Any]]] = {}
    for record in root_witnesses(Path(run_root)):
        key = str(record.get("source_root_id") or record.get("root_id") or "")
        if key:
            out.setdefault(key, []).append(record)
    return out


def run_candidates(run_root: Path) -> List[str]:
    """本次运行**出现过的候选身份**（状态文件 + 实例台账 + 家族产物三处并集）。

    为什么必须显式枚举而不是只看"有评价产物的候选"：挑战者若**一条评价都还没跑**，
    它就不会出现在评价产物里 —— 那样"完整比较缺边"会被算成 0（假绿）。
    2026-09-18 run4 实测：run4 只有在席者 8 条家族评价，挑战者 0 条；
    只看产物会把挑战者整个漏掉。
    """

    seen: List[str] = []
    for _label, state_path in state_files(Path(run_root)):
        state = read_json(state_path) or {}
        candidate = str((state.get("identity") or {}).get("candidate_id") or "")
        if candidate and candidate not in seen:
            seen.append(candidate)
    layout = layout_of(Path(run_root))
    if layout == "run_root":
        for iter_dir in iter_dirs(Path(run_root)):
            payload = read_json(iter_dir / "instances.json") or {}
            for row in (payload.get("instances") or {}).values():
                candidate = str(row.get("candidate_id") or "")
                if candidate and candidate not in seen:
                    seen.append(candidate)
    for row in family_evaluation_products(Path(run_root)):
        candidate = str(row.get("candidate_id") or "")
        if candidate and candidate not in seen:
            seen.append(candidate)
    return seen


def family_product_iteration(path: Path, *, layout: str) -> str:
    """家族评价产物 → **迭代序号**（不是文件名）。

    - 完整运行目录：`iterations/iter-NN/family/<dir>/evaluation.json` ⇒ 取 `iter-NN`；
    - 证据副本：`family/iter-NN__<cid>-….json` ⇒ 取文件名前缀。

    缺陷记录（2026-09-19 run7 复核）：旧实现取 `path.name`，在运行目录里得到的是
    `"evaluation.json"`，于是 comparison_gap 的 old_root/refresh 两组读数永远对不上
    已完成产物 —— 明明 8 根 × 2 臂都已评价，却报 16 条"缺"（读数与事实不一致）。
    """

    if str(layout) == "run_root":
        # 逐级上溯找 `iter-NN` 目录（不要写死层数：family 下还有一层根目录）。
        for parent in path.parents:
            if parent.name.startswith("iter-"):
                return _ordinal(parent.name)
    return _ordinal(path.name)


def family_evaluation_products(run_root: Path) -> List[Dict[str, Any]]:
    """家族根评价产物 → 覆盖索引（`subject_root_id` × 候选 × 是否可核）。

    两种形态都支持：
    - 完整运行目录：`iterations/iter-*/family/*/evaluation.json`；
    - 证据副本：`family/*.json`（文件名形如 `iter-02__<cid>-<cell>-<mix>-...json`）。
    这是"共同根比较**在哪个根上有可核评价**"的唯一依据：**不数登记行数**。
    """

    root = Path(run_root)
    layout = layout_of(root)
    paths: List[Path] = []
    if layout == "run_root":
        for iter_dir in iter_dirs(root):
            paths.extend(sorted((iter_dir / "family").glob("*/evaluation.json")))
    else:
        paths.extend(sorted((root / "family").glob("*.json")))
    out: List[Dict[str, Any]] = []
    for path in paths:
        payload = read_json(path)
        if not isinstance(payload, Mapping):
            continue
        iteration = family_product_iteration(path, layout=layout)
        candidate_id = str((payload.get("identity") or {}).get("candidate_id") or "")
        for sample in (payload.get("samples") or ()):
            arms = dict(sample.get("arms") or {})
            out.append({
                "path": str(path), "iteration": iteration,
                "candidate_id": candidate_id,
                "source_root_id": sample.get("source_root_id"),
                "sub_scenario": sub_scenario_of_root(sample.get("source_root_id")),
                "opponent_mix": sample.get("opponent_mix"),
                "root_index": sample.get("root_index"),
                "root_seed": sample.get("root_seed"),
                "ok": bool(payload.get("ok")),
                "arms": sorted(arms),
                "arms_complete": all(
                    str((block or {}).get("status")) == "complete"
                    and bool((block or {}).get("usable"))
                    for block in arms.values()) and len(arms) == 2,
                "root_requirement_digest": sample.get("root_requirement_digest"),
                "root_content_digest": sample.get("root_content_digest"),
                "tables_executed": ((payload.get("panel") or {}).get(
                    "tables_full_executed")),
                "file_sha256": sha256_file(path),
            })
    return out


# ===========================================================================
# 缺失键的**账目归因**：只有生产产物明确记了"这项没跑/跑了但失败"才算已解释
# ===========================================================================


def conditional_roots_by_iteration(run_root: Path) -> Dict[str, Dict[str, Any]]:
    """迭代序号 → 该迭代条件通道落地的那一个根（运行期才解析的根**具名绑定**在这里取值）。"""

    out: Dict[str, Dict[str, Any]] = {}
    for entry in conditional_instances(Path(run_root)):
        samples = [row for row in (entry.get("samples") or ()) if isinstance(row, Mapping)]
        if not samples:
            continue
        identity = dict(samples[0].get("root_identity") or {})
        out[_ordinal(entry.get("iteration"))] = {
            "iteration": _ordinal(entry.get("iteration")),
            "candidate_id": entry.get("candidate_id"),
            "root_id": identity.get("root_id"),
            "root_index": identity.get("root_index"),
            "root_seed": identity.get("root_seed"),
            "opponent_mix": identity.get("opponent_mix"),
            "sub_scenario": identity.get("sub_scenario"),
            "path": entry.get("path"),
            "digest_state": (entry.get("digest_verdict") or {}).get("state"),
            "arms": sorted({arm for sample in samples
                            for arm in (sample.get("arm_completeness") or {})})}
    return out


def cross_channel_coverage(run_root: Path) -> Dict[str, Dict[str, Any]]:
    """**其它通道**的可核产物索引：`候选 | 完整根` → 条件通道的同根评价读数。

    判定链口径（复审 C2`逐实例连接`+ P15 覆盖口径）：家族通道里某个**运行期解析旧根**的
    声明实例，如果同一个候选在**同一个完整根**上已有可核评价（本运行里落在条件通道），
    则该比较义务已由该产物承担 —— 读数必须写明 `basis=conditional_channel_product`、
    产物路径与摘要核验状态；没有可核产物时**不得**判为已覆盖。
    """

    out: Dict[str, Dict[str, Any]] = {}
    for entry in conditional_instances(Path(run_root)):
        digest_verdict = dict(entry.get("digest_verdict") or {})
        digest_state = str(digest_verdict.get("state"))
        for sample in (entry.get("samples") or ()):
            if not isinstance(sample, Mapping):
                continue
            identity = dict(sample.get("root_identity") or {})
            root_id = str(identity.get("root_id") or "")
            if not root_id:
                continue
            arms = {str(arm): {"status": (block or {}).get("status"),
                               "usable": bool((block or {}).get("usable")),
                               "tables": (block or {}).get("tables")}
                    for arm, block in (sample.get("arm_completeness") or {}).items()}
            key = "{0}|{1}".format(str(entry.get("candidate_id") or ""), root_id)
            out[key] = {
                "channel": CHANNEL_CONDITIONAL,
                "candidate_id": entry.get("candidate_id"),
                "iteration": _ordinal(entry.get("iteration")),
                "root_id": root_id, "root_index": identity.get("root_index"),
                "root_seed": identity.get("root_seed"),
                "opponent_mix": identity.get("opponent_mix"),
                "sub_scenario": identity.get("sub_scenario"),
                "path": entry.get("path"), "arms": arms,
                "digest_state": digest_state,
                "digest_valid_comparisons": int(
                    digest_verdict.get("valid_comparisons") or 0),
                "digest_checks_ok": sum(
                    1 for row in (digest_verdict.get("checks") or ())
                    if row.get("ok")),
                #: P25：**唯一**可核判据 —— 零次有效摘要比较的残壳不得再转成
                #: verified=True（修复前 state=verified/checks=[] 会被这里直接放行）。
                "verified": conditional_digest_state_is_verified(
                    digest_state, digest_verdict),
                "evaluation_ok": bool(entry.get("ok"))}
    return out


def conditional_coverage_verdict(*, coverage: Mapping[str, Dict[str, Any]],
                                 candidate_id: str, root_id: str,
                                 arm: str) -> Optional[Dict[str, Any]]:
    """**同一候选 + 同一完整根 + 指定臂**在条件通道的可核产物（单一判定来源）。

    供两处复用，避免各造一套"覆盖"判据：
    - `declaration_coverage()`（家族缺失键的归因）；
    - 执行器步骤 3 的 `refill_*` / `window_digest_basis_available` 判据（`指定旧根`）。
    """

    record = dict((coverage or {}).get("{0}|{1}".format(candidate_id, root_id)) or {})
    if not record:
        return None
    arm_block = dict((record.get("arms") or {}).get(str(arm)) or {})
    #: P25：覆盖义务的承担要求「摘要状态可核」**且**至少做过一次有效摘要比较；
    #: 缺摘要残壳（registered_without_digest / no_recorded_digest / …）一律不承担。
    if not (record.get("verified") and record.get("evaluation_ok")
            and int(record.get("digest_valid_comparisons") or 0) >= 1
            and str(arm_block.get("status")) == "complete" and arm_block.get("usable")):
        return None
    return {"basis": "conditional_channel_product",
            # 注意：字段名用 `product_channel`——叫 `channel` 会在
            # `covered.append(dict(row, **verdict))` 处**覆盖需求项自己的通道**
            # （run9 实测：家族缺失键被记成"条件通道"），这里显式区分"需求通道"与"产物通道"。
            "product_channel": record.get("channel"), "root_id": root_id,
            "root_index": record.get("root_index"), "root_seed": record.get("root_seed"),
            "opponent_mix": record.get("opponent_mix"),
            "sub_scenario": record.get("sub_scenario"),
            "candidate_id": candidate_id, "arm": str(arm),
            "product_path": record.get("path"),
            "product_iteration": record.get("iteration"),
            "digest_state": record.get("digest_state"),
            "arm_tables": arm_block.get("tables"),
            "detail": ("该实例由**条件通道**在同一完整根上的可核评价承担"
                       "（候选 {0} / 根 {1} / 臂 {2} / 摘要 {3}）".format(
                           str(candidate_id)[:12], root_id, arm,
                           record.get("digest_state")))}


def declaration_coverage(key: str, channel: str, *, plan_row: Optional[Mapping[str, Any]],
                         run_root: Path, coverage: Mapping[str, Dict[str, Any]],
                         roots_by_iter: Mapping[str, Mapping[str, Any]],
                         candidates_by_iter: Mapping[str, str]) -> Optional[Dict[str, Any]]:
    """缺失的家族声明实例 → 是否已由**其它通道**的同根可核产物覆盖（否则 None）。"""

    if str(channel) != CHANNEL_FAMILY or not plan_row:
        return None
    resolution = str(plan_row.get("root_index_resolution") or "")
    if not resolution.startswith("runtime:"):
        return None
    parts = parse_key(key)
    arm = str(parts.get("arm") or "")
    ordinal = str(parts.get("iter") or "")
    source = resolution.split(":", 1)[1]
    digits = re.findall(r"\d+", source)
    source_iter = digits[0] if digits else ""
    bound = dict(roots_by_iter.get(source_iter) or {})
    root_id = str(bound.get("root_id") or "")
    if not root_id:
        return None
    candidate = str(candidates_by_iter.get(ordinal) or "")
    verdict = conditional_coverage_verdict(coverage=coverage, candidate_id=candidate,
                                           root_id=root_id, arm=arm)
    if verdict is None:
        return None
    verdict["binding"] = ("运行期解析的根具名绑定：{0} ⇒ {1}（迭代 {2} 的条件通道根）".format(
        resolution, root_id, source_iter))
    return verdict


def production_accounting(run_root: Path) -> Dict[str, Any]:
    """生产产物里关于"哪些实例没跑成"的显式记录（用于缺失键归因）。

    只读三类**生产自己写的**产物：
    - `iterations/*/state.json` 的 `family_fill.attempts/no_progress/missing`（家族根评价）；
    - `iterations/*/checkpoints/natural-<mix>.json`（自然面板是否完成）；
    - `iterations/*/state.json` 的 `status/stop_reason` 与 `natural` 块（停止原因）。
    """

    family: Dict[str, Dict[str, Any]] = {}
    panels: Dict[str, Dict[str, Any]] = {}
    iterations: Dict[str, Dict[str, Any]] = {}
    units: Dict[str, Dict[str, Any]] = {"family_fill_attempts": {}}
    layout = layout_of(Path(run_root))
    for label, state_path in state_files(Path(run_root)):
        state = read_json(state_path) or {}
        iter_dir = (Path(run_root) / "iterations" / "iter-{0:02d}".format(int(label))
                    if layout == "run_root" and str(label).isdigit()
                    else Path(run_root))
        iterations[label] = {"status": state.get("status"),
                             "stop_reason": state.get("stop_reason"),
                             "natural": state.get("natural"),
                             "conditional": state.get("conditional"),
                             "iter_dir": iter_dir.name}
        fill = state.get("family_fill") or {}
        units["family_fill_attempts"][label] = list(fill.get("attempts") or ())
        for row in (fill.get("attempts") or ()):
            for root_id in (row.get("root_ids") or ()):
                family[str(root_id)] = {**family.get(str(root_id), {}),
                                        "status": row.get("status"),
                                        "reason": row.get("reason"),
                                        "iteration": label,
                                        "rounds": row.get("rounds")}
        for block_name in ("no_progress", "missing"):
            for root_id, row in ((fill.get(block_name) or {}) if isinstance(
                    fill.get(block_name), Mapping) else {}).items():
                if isinstance(row, Mapping):
                    family[str(root_id)] = {**family.get(str(root_id), {}),
                                            "status": "no_progress",
                                            "reason": row.get("last_reason"),
                                            "iteration": label,
                                            "accounted": True}
        for mix in ("H", "M"):
            checkpoint = read_json(iter_dir / "checkpoints"
                                   / "natural-{0}.json".format(mix)) or {}
            key = "{0}|{1}".format(label, mix)
            natural = state.get("natural") if isinstance(state.get("natural"),
                                                         Mapping) else {}
            status = checkpoint.get("status")
            if not status and isinstance(natural, Mapping):
                # 证据副本没有检查点：退化为迭代状态里的自然面板块（仍然只认生产记录）。
                status = natural.get("status")
            panels[key] = {"status": status,
                           "reused_from": checkpoint.get("reused_from"),
                           "cost_charged": checkpoint.get("cost_charged"),
                           "iter_dir": str(iter_dir)}
    return {"family_roots": family, "natural_panels": panels,
            "iterations": iterations, "family_fill_attempts":
                units["family_fill_attempts"],
            "note": ("归因只认生产产物里的显式记录：缺失键若在 family_fill 失败/无进展"
                     "清单里，或所在迭代/情景的面板检查点没有 completed 且有停止原因，"
                     "才算**已解释**；否则就是**真丢失**（必须红）。")}


def account_missing_key(key: str, channel: str,
                        accounting: Mapping[str, Any]) -> Optional[str]:
    """缺失键 → 已解释理由（None = 未解释 = 丢失）。"""

    parts = parse_key(key)
    iteration = str(parts.get("iter"))
    iterations = accounting.get("iterations") or {}
    if channel == CHANNEL_FAMILY:
        cell = str(parts.get("cell"))
        mix = str(parts.get("mix"))
        idx = str(parts.get("rootidx"))
        for root_id, row in (accounting.get("family_roots") or {}).items():
            if (sub_scenario_of_root(root_id) == cell
                    and str(row.get("iteration")) == iteration):
                suffix = "root{0:03d}".format(int(idx)) if idx.isdigit() else str(idx)
                if root_id.endswith(suffix):
                    return "生产记录：{0}（{1}）".format(
                        row.get("status"), str(row.get("reason"))[:120])
        state = iterations.get(iteration) or {}
        if str(state.get("stop_reason") or ""):
            return ("该迭代未跑到该根评价即具名停止：{0}".format(
                str(state.get("stop_reason"))[:120]))
        status = str(state.get("status") or "")
        fill = (accounting.get("family_fill_attempts") or {}).get(iteration) or []
        if status and status != "ITERATION_COMPLETE" and not fill:
            # 该迭代**根本没跑到家族补根步**（没有任何 attempts 记录）且未完成 ⇒
            # 计划实例的终态是"未执行"，原因就是这次运行在该步之前停止（不是丢失）。
            # 注意：一旦该迭代完成，本条不再适用 ⇒ 删除已完成迭代里的实例行仍会红。
            return ("该迭代在家族补根步之前即停止（状态 {0}，无 family_fill attempts）"
                    "⇒ 该实例未执行（非丢失）".format(status))
        return None
    if channel in (CHANNEL_NATURAL, CHANNEL_SHARED_BASELINE):
        mix = str(parts.get("mix"))
        panel = (accounting.get("natural_panels") or {}).get(
            "{0}|{1}".format(iteration, mix)) or {}
        if str(panel.get("status")) == "completed":
            # 面板完成却少了这一个实例：没有任何生产记录解释它 ⇒ 真丢失。
            return None
        state = iterations.get(iteration) or {}
        reason = str(state.get("stop_reason") or "")
        natural = state.get("natural") or {}
        return ("自然面板 {0} 未完成（检查点状态 {1}；迭代停止原因 {2}）".format(
            mix, panel.get("status"), reason or (natural.get("status") if isinstance(
                natural, Mapping) else None) or "未记"))
    return None


def split_missing(run_root: Path, join: Mapping[str, Any]) -> Dict[str, Any]:
    """缺失键 → 已覆盖 / 已解释 / 未解释（未解释即"丢失"）。

    `已由其它通道覆盖`与`生产明确记了没跑成`是**两类不同的事**：
    前者是比较义务已由**可核产物**承担（basis 具名 + 产物路径 + 摘要核验状态）；
    后者是功能未完成（账目诚实但 INSUFFICIENT）。两者都不写成"丢失"。
    """

    accounting = production_accounting(run_root)
    coverage = cross_channel_coverage(Path(run_root))
    roots_by_iter = conditional_roots_by_iteration(Path(run_root))
    candidates_by_iter: Dict[str, str] = {}
    for label, state_path in state_files(Path(run_root)):
        state = read_json(state_path) or {}
        candidate = str((state.get("identity") or {}).get("candidate_id") or "")
        if candidate:
            candidates_by_iter[str(_ordinal(label))] = candidate
    planned: Dict[str, Mapping[str, Any]] = {}
    for channel in CHANNELS:
        for row in ((join.get("channels") or {}).get(channel) or {}).get(
                "expected_rows") or ():
            row_key = key_of_expected(row)
            # 家族通道的键与 join 同口径归一（运行期解析的根不进键），否则查不到计划行。
            planned[_norm_runtime_root(row_key)
                    if str(row.get("channel")) == CHANNEL_FAMILY else row_key] = row
    accounted: List[Dict[str, Any]] = []
    covered: List[Dict[str, Any]] = []
    unaccounted: List[Dict[str, Any]] = []
    for channel in CHANNELS:
        block = (join.get("channels") or {}).get(channel) or {}
        for key in (block.get("missing_expected_keys") or ()):
            row = {"channel": channel, "key": key}
            verdict = declaration_coverage(
                key, channel, plan_row=planned.get(key), run_root=Path(run_root),
                coverage=coverage, roots_by_iter=roots_by_iter,
                candidates_by_iter=candidates_by_iter)
            if verdict:
                covered.append(dict(verdict, channel=channel, key=key,
                                    requirement_channel=channel,
                                    product_channel=verdict.get("product_channel")))
                continue
            reason = account_missing_key(key, channel, accounting)
            if reason:
                accounted.append(dict(row, reason=reason))
            else:
                unaccounted.append(row)
    return {"accounted": accounted, "covered_by_other_channel": covered,
            "unaccounted": unaccounted, "accounting": accounting,
            "cross_channel_coverage": {
                key: {"channel": row["channel"], "path": row["path"],
                      "arms": sorted(row["arms"]), "digest_state": row["digest_state"]}
                for key, row in coverage.items()},
            "note": ("已解释 = 生产产物明确记了没跑/失败的原因（功能未完成但账目诚实）；"
                     "已覆盖 = 同一完整根的可核产物在别的通道承担了该义务（basis 具名）；"
                     "未解释 = 丢失（红）")}


# ===========================================================================
# 假完成 / 摘要不足 / 费用 join
# ===========================================================================


def collect_fake_completions(run_root: Path) -> List[Dict[str, Any]]:
    """completed 尝试必须能被**重算核对**（内容与摘要不一致即红）。"""

    bad: List[Dict[str, Any]] = []
    for entry in observed_instances(Path(run_root)):
        row = entry["row"]
        attempts = list(row.get("attempts") or ())
        if not attempts or str(attempts[-1].get("status")) != "completed":
            continue
        last = dict(attempts[-1])
        verdict = verify_result_digest(channel=entry["channel"], row=row, attempt=last)
        if verdict.get("state") == "verified":
            continue
        bad.append({"instance_key": entry.get("ledger_key"),
                    "iteration_dir": entry.get("iteration_dir"),
                    "channel": entry["channel"], "result_path": last.get("result_path"),
                    "recorded_digest": last.get("result_digest"),
                    "recomputed": verdict.get("recomputed"),
                    "schema": verdict.get("schema"), "state": verdict.get("state"),
                    "detail": verdict.get("detail")})
    return bad


def _instance_identity(channel: str, item: Mapping[str, Any]) -> Dict[str, Any]:
    """实例行 → 归属身份（与账步身份同一组维度：候选 / 子场景 / 情景 / 根 / 赛程）。"""

    parts = parse_key(item.get("key"))
    root_id = item.get("source_root_id")
    return {
        "channel": channel,
        "candidate_id": str(item.get("candidate_id") or ""),
        "iteration": str(item.get("iteration")),
        "cell": (parts.get("cell") or sub_scenario_of_root(root_id)),
        "opponent_mix": parts.get("mix") or item.get("opponent_mix"),
        "root_index": item.get("root_index", parts.get("rootidx")),
        "root_seed": item.get("root_seed", parts.get("rootseed")),
        "root_id": root_id, "arm": item.get("arm"), "seat": item.get("seat"),
        "schedule": parts.get("sched") or item.get("schedule"),
        "tables_attempted": float(item.get("tables_attempted") or 0.0),
        "key": item.get("key"),
    }


def _planned_identity(channel: str, row: Mapping[str, Any]) -> Dict[str, Any]:
    """计划实例行 → 归属身份（运行期才解析根的行 root_index 可缺省）。"""

    return {"channel": channel, "candidate_id": str(row.get("plan_candidate_slot") or ""),
            "iteration": _ordinal(row.get("iteration")),
            "cell": row.get("sub_scenario") or sub_scenario_of_root(
                row.get("frozen_root_id")),
            "opponent_mix": row.get("opponent_mix"),
            "root_index": row.get("root_index"), "root_seed": row.get("root_seed"),
            "root_id": row.get("frozen_root_id"), "arm": row.get("arm"),
            "seat": row.get("seat"), "schedule": row.get("schedule"),
            "tables_planned": float(row.get("planned_tables") or 0.0),
            "key": key_of_expected(row), "planned_only": True}


def _ledger_settles_planned(ledger_identity: Mapping[str, Any],
                            planned: Mapping[str, Any]) -> bool:
    """账目是否结算了某条**计划实例**（含运行期才解析根的声明行）。

    运行期才解析根的实例在计划里没有根序号：此时按`迭代 + 子场景 + 情景`具名匹配，
    并在读数里写明它结算的是哪一条计划实例（缺根序号时如实标注，不编造根 id）。
    """

    if not _ledger_settles_instance(ledger_identity, planned):
        return False
    hint = ledger_identity.get("iteration_hint")
    if hint and str(hint) != "iter" + str(planned.get("iteration")):
        return False
    ledger_idx = ledger_identity.get("root_index")
    plan_idx = planned.get("root_index")
    if ledger_idx is not None and plan_idx is not None \
            and str(ledger_idx) != str(plan_idx):
        return False
    return True


def _ledger_settles_instance(ledger_identity: Mapping[str, Any],
                             instance: Mapping[str, Any]) -> bool:
    """一条账目是否结算了某个实例（按身份逐维比，**不按总额**）。"""

    kind = str(ledger_identity.get("kind"))
    candidate = str(ledger_identity.get("candidate") or "")
    inst_candidate = str(instance.get("candidate_id") or "")
    if candidate and inst_candidate and not inst_candidate.startswith(candidate):
        return False
    if kind == "natural":
        return str(instance.get("channel")) in (CHANNEL_NATURAL,
                                                CHANNEL_SHARED_BASELINE) \
            and (not ledger_identity.get("opponent_mix")
                 or str(ledger_identity.get("opponent_mix"))
                 == str(instance.get("opponent_mix")))
    if kind == "family":
        if str(instance.get("channel")) != CHANNEL_FAMILY:
            return False
        if ledger_identity.get("sub_scenario") \
                and str(ledger_identity.get("sub_scenario")) != str(instance.get("cell")):
            return False
        if ledger_identity.get("opponent_mix") \
                and str(ledger_identity.get("opponent_mix")) \
                != str(instance.get("opponent_mix")):
            return False
        ledger_index = ledger_identity.get("root_index")
        instance_index = instance.get("root_index")
        # 计划行的根序号可以为空（运行期才解析）：只在**两侧都有值**时逐字比；
        # 已观测实例的根序号一律严格比（缺一维就不算同一个根）。
        if ledger_index is not None and (instance_index is not None
                                         or not instance.get("planned_only")):
            if str(ledger_index) != str(instance_index):
                return False
        if ledger_identity.get("root_id") and str(ledger_identity.get("root_id")) \
                != str(instance.get("root_id")):
            return False
        return True
    if kind == "conditional":
        return str(instance.get("channel")) == CHANNEL_CONDITIONAL
    return False


def cost_join_rows(join: Mapping[str, Any]) -> List[Dict[str, Any]]:
    """费用 join：逐通道**三方对照**（实例数 / 桌数 / 账本结算）+ 逐行归属到具体实例。

    口径：
    - 账目归属按 `parse_ledger_step_identity` 的结构化身份判（候选/子场景/情景/根）；
    - 每条账目必须能被**具名实例身份**接住（接不住 = 未解释归属 ⇒ 红）；
    - 同粒度比较：`实例已结算桌数 + 该组在途预留 = 账本 tables_full`
      （在途实例在台账里仍是 `started`，不含 `cost.tables`，所以必须单列那一笔）；
    - 条件通道另比 tables_partial（前缀生成的部分桌），其余账号（prefix_generation /
      tables_partial）只作读数：实例台账只在完成时记 `cost.tables`，账号本身不同粒度，
      因此**逐行列出它结算的根身份**而不是把差额抹平（复审：不得靠删断言过关）。
    """

    channels = join.get("channels") or {}
    charge_block = join.get("ledger_charges") or {}
    charges = charge_block.get("groups") or {}
    inflight_rows = list(charge_block.get("inflight_rows") or ())
    ledger_rows = [dict(row) for row in (charge_block.get("rows") or ())]
    rows: List[Dict[str, Any]] = []
    run_root = Path(str(join.get("run_root") or "."))
    refresh_records = refresh_batch_records(run_root)
    missing_split = dict(join.get("missing_split") or {})
    covered_missing = [dict(row) for row in (missing_split.get(
        "covered_by_other_channel") or ())]
    unaccounted_missing = [dict(row) for row in (missing_split.get("unaccounted") or ())]
    accounted_missing = [dict(row) for row in (missing_split.get("accounted") or ())]
    for group, members in COST_GROUPS.items():
        items = [(channel, item)
                 for channel in members
                 for item in ((channels.get(channel) or {}).get("items") or ())]
        identities = [(_instance_identity(channel, item), item)
                      for channel, item in items]
        observed_ledger_keys = {str(item.get("ledger_key")) for _, item in items
                                if item.get("ledger_key")}
        instance_tables = round(sum(row["tables_attempted"]
                                    for row, _ in identities), 6)
        ledger = dict(charges.get(group) or {})
        full = float(ledger.get("tables_full") or 0.0)
        partial = float(ledger.get("tables_partial") or 0.0)
        kinds = {"natural" if member.startswith("natural") else member
                 for member in members}
        inflight = round(sum(float(row.get("amount") or 0.0) for row in inflight_rows
                             if str(row.get("kind")) in kinds), 6)
        group_rows = [row for row in ledger_rows if row.get("group") == group]
        planned = [(_planned_identity(channel, row), row)
                   for channel in members
                   for row in ((channels.get(channel) or {}).get("expected_rows") or ())]
        settlement: List[Dict[str, Any]] = []
        attributed_keys: set = set()
        attributed_planned: set = set()
        for ledger_row in group_rows:
            settled = [identity["key"] for identity, _ in identities
                       if _ledger_settles_instance(ledger_row["identity"], identity)]
            attributed_keys.update(settled)
            planned_hits = [identity["key"] for identity, _ in planned
                            if _ledger_settles_planned(ledger_row["identity"], identity)]
            attributed_planned.update(planned_hits)
            row_charge = float(ledger_row["charged"] or 0.0)
            if settled:
                note = ("该账步按**根×两臂**结算 {0} 桌，实例台账按**臂**分行："
                        "一条账目对应 {1} 条实例行".format(row_charge, len(settled)))
            elif planned_hits:
                note = ("该账目结算的是**计划里未完成的实例**（运行期才解析的根按声明绑定）："
                        "{0}".format("；".join(planned_hits[:2])))
            else:
                note = "该账目没有对应的实例行（未解释）"
            settlement.append({
                "step_id": ledger_row["step_id"], "account": ledger_row["account"],
                "charged": ledger_row["charged"], "status": ledger_row["status"],
                "superseded": ledger_row["superseded"],
                "identity": ledger_row["identity"],
                "settled_instances": settled[:40],
                "settled_instance_count": len(settled),
                "settles_planned_instances": planned_hits[:10],
                "settles_planned_count": len(planned_hits),
                "granularity_note": note})
        unexplained_accounted = [row for row in settlement
                                 if row["settled_instance_count"] == 0
                                 and row["settles_planned_count"] == 0
                                 and float(row["charged"] or 0.0) > 0.0]
        uncovered_instances = [identity["key"] for identity, _ in identities
                               if identity["key"] not in attributed_keys
                               and identity["channel"] in members]
        plan_expected = sum(
            int((channels.get(name) or {}).get("expected_instances") or 0)
            for name in members)
        covered_missing_rows = [row for row in covered_missing
                                if row.get("requirement_channel") in members]
        refresh_block: Dict[str, Any] = {}
        refresh_issues: List[Dict[str, Any]] = []
        expected_total = plan_expected
        if group.startswith("natural") and refresh_records:
            refresh_ledger_rows = [row for row in group_rows
                                   if str((row.get("identity") or {}).get(
                                       "step_role")) == "normal_refresh_batch"]
            refresh_declared_tables = round(sum(float(record.get("cost_charged") or 0.0)
                                                for record in refresh_records), 6)
            refresh_ledger_tables = round(sum(float(row.get("charged") or 0.0)
                                              for row in refresh_ledger_rows), 6)
            refresh_expected = sum(int(record.get("expected_instances") or 0)
                                   for record in refresh_records)
            expected_total = plan_expected + refresh_expected
            refresh_block = {
                "basis": ("整体(normal)通道刷新批（设计 §537 阶段 2：给参与重排的所有身份"
                          "补齐新刷新根）——盘上记录 `checkpoints/refresh-<cid12>-<mix>.json`"),
                "records": [{key: record.get(key) for key in (
                    "iteration", "candidate_id", "opponent_mix", "step_id", "root_ids",
                    "root_indexes", "seats_per_root", "status", "cost_charged",
                    "expected_instances", "completed_instances", "panel_path",
                    "result_sha256")} for record in refresh_records],
                "expected_instances": refresh_expected,
                "declared_tables": refresh_declared_tables,
                "ledger_rows": len(refresh_ledger_rows),
                "ledger_tables": refresh_ledger_tables,
                "basis_note": ("该批的桌数在账本里走 `refresh:<cid12>:<mix>:<选择集记号>` "
                               "账步（归自然组）；实例如在台账中按候选身份分行")}
            # —— 三方一致性（记录 ↔ 账目 ↔ 实例）：任一不闭合即"未解释"（仍 FAIL）——
            if abs(refresh_declared_tables - refresh_ledger_tables) > 1e-6:
                refresh_issues.append({
                    "which": "refresh_ledger_vs_record",
                    "declared_tables": refresh_declared_tables,
                    "ledger_tables": refresh_ledger_tables,
                    "detail": ("刷新批账目与盘上记录不一致：记录 {0} 桌 / 账本 {1} 桌"
                               "（差额逐条可追到 refresh 账步）").format(
                                   refresh_declared_tables, refresh_ledger_tables)})
            if refresh_records and not refresh_ledger_rows:
                refresh_issues.append({
                    "which": "refresh_record_without_ledger",
                    "records": [record.get("step_id") for record in refresh_records],
                    "detail": "刷新批有盘上记录但账本里没有对应 refresh 账步（费用未入账）"})
            if refresh_ledger_rows and not refresh_records:
                refresh_issues.append({
                    "which": "refresh_ledger_without_record",
                    "step_ids": [row.get("step_id") for row in refresh_ledger_rows],
                    "detail": "账本有 refresh 账步但盘上没有对应检查点/记录（账目无对应实例）"})
            missing_keys = [key for record in refresh_records
                            for key in (record.get("instance_keys") or ())
                            if str(key) not in observed_ledger_keys]
            if missing_keys:
                refresh_issues.append({
                    "which": "refresh_instances_absent",
                    "count": len(missing_keys), "keys": missing_keys[:10],
                    "detail": "刷新批记录里的实例键不在实例台账里（实例无账目承接/记录对不上）"})
        # 观察条目数 − 期望行数：多出来的条目必须已有**具名依据**（整体刷新批的 32 条在这里已
        # 进 expected_total；其余多出来的就是"总行数补不平"的额外实例 ⇒ 未解释）。
        unexpected_extra = max(0, len(identities) - expected_total)
        entry = {"group": group, "members": list(members),
                 "instance_instances_plan_expected": plan_expected,
                 "instance_instances_expected": expected_total,
                 "instance_instances_observed": len(identities),
                 "instance_instances_unexpected_extra": unexpected_extra,
                 "instances_missing_covered_count": len(covered_missing_rows),
                 "instance_tables": instance_tables,
                 "ledger_inflight": inflight,
                 "ledger_tables_full": full,
                 "delta": round(instance_tables + inflight - full, 6),
                 "ledger_rows": len(group_rows),
                 "ledger_settled_rows": len(settlement) - len(unexplained_accounted),
                 "unexplained_ledger_rows": unexplained_accounted[:10],
                 "unexplained_ledger_count": len(unexplained_accounted),
                 "instances_without_ledger_row": uncovered_instances[:20],
                 "instances_without_ledger_count": len(uncovered_instances),
                 "settlement": settlement[:60],
                 "basis": ("实例数 / 桌数 / 账本结算三方对照；账目按结构化身份归属，"
                           "每条账目列出它结算的实例键（差额逐条可追到实例）"),
                 "refresh_batch": refresh_block,
                 "refresh_batch_issues": refresh_issues,
                 "instances_missing_covered_by_other_channel": [
                     {"key": row.get("key"), "basis": row.get("basis"),
                      "root_id": row.get("root_id"), "arm": row.get("arm"),
                      "product_channel": row.get("product_channel"),
                      "product_path": row.get("product_path"),
                      "digest_state": row.get("digest_state")}
                     for row in covered_missing
                     if row.get("requirement_channel") in members],
                 "instances_missing_unaccounted": [
                     row.get("key") for row in unaccounted_missing
                     if row.get("channel") in members],
                 # 第三类（P21 补读数）：生产产物**具名记了没跑成**（明确失败 / 预算未执行）。
                 # 它不进 unaccounted（账目诚实、不是丢失），但**也不等于 PASS**：
                 # accounted_missing_are_complete_cases 会把这一档判成 INSUFFICIENT（功能未完成）。
                 # 单列出来是为了让「该组为何转 PASS」必须能指到 covered 的 basis，而不是靠 delta 为 0。
                 "instances_missing_accounted": [
                     {"key": row.get("key"), "reason": row.get("reason")}
                     for row in accounted_missing
                     if row.get("channel") in members],
                 "instances_missing_accounted_count": len([
                     row for row in accounted_missing
                     if row.get("channel") in members]),
                 "ledger_all_accounts": ledger}
        if group == "conditional(prefix/refill)":
            instance_full = round(sum(
                float(item.get("tables_attempted") or 0.0)
                for _, item in items if item.get("kind") == "conditional_full"), 6)
            instance_prefix = round(sum(
                float(item.get("tables_attempted") or 0.0)
                for _, item in items if item.get("kind") == "conditional_prefix"), 6)
            entry.update({"instance_tables_full": instance_full,
                          "ledger_tables_full": full,
                          "delta_full": round(instance_full + inflight - full, 6),
                          "instance_tables_partial": instance_prefix,
                          "ledger_tables_partial": partial,
                          "delta_partial": round(instance_prefix - partial, 6)})
            entry.pop("delta", None)
        rows.append(entry)
    return rows


def check_rows(join: Mapping[str, Any]) -> List[Dict[str, Any]]:
    """逐键对账 → 判定行（四项不变量 + 功能完成 + 摘要可核 + 费用 join）。"""

    rows: List[Dict[str, Any]] = []
    channels = join.get("channels") or {}
    missing_all: List[str] = []
    unplanned_all: List[str] = []
    detail_parts = []
    for channel in CHANNELS:
        block = channels.get(channel) or {}
        missing_all.extend(list(block.get("missing_expected_keys") or ()))
        unplanned_all.extend(list(block.get("unplanned_observed_keys") or ()))
        detail_parts.append(
            "{0}: 计划 {1} / 实际 {2} / 缺 {3} / 计划外 {4} / 终态 {5}".format(
                channel, block.get("expected_instances"), block.get("observed_instances"),
                len(block.get("missing_expected_keys") or ()),
                len(block.get("unplanned_observed_keys") or ()),
                dict(block.get("terminal_counts") or {})))
    split = join.get("missing_split") or {}
    unaccounted = list(split.get("unaccounted") or ())
    accounted = list(split.get("accounted") or ())
    conditional_block = channels.get(CHANNEL_CONDITIONAL) or {}
    rows.append({
        "name": "zero_lost_instances_by_key", "ok": not unaccounted, "applicable": True,
        "detail": ("按冻结实例键逐项连接（缺键即丢失，别的通道多出的行补不了）："
                   + "；".join(detail_parts)
                   + "；缺失键中已由生产产物解释 {0} 条，**未解释（=丢失）{1} 条**".format(
                       len(accounted), len(unaccounted))),
        "missing_keys": missing_all[:50], "missing_count": len(missing_all),
        "unaccounted_missing": unaccounted[:50],
        "unaccounted_count": len(unaccounted),
        "unplanned_keys": unplanned_all[:50], "unplanned_count": len(unplanned_all),
    })
    # C2：**额外实例（额外臂/额外根/额外赛程）同样要拒绝** —— 旧口径只把计划外键当读数，
    # 没有任何判据拦它，因此"把 baseline 改名成 unexpected_arm"能靠总行数不变蒙过去。
    rows.append({
        "name": "zero_unplanned_instances", "ok": not unplanned_all, "applicable": True,
        "detail": ("按冻结实例键反查**计划外完成项** {0} 条（额外臂/额外根/额外赛程；"
                   "总行数不变也补不了）：{1}").format(
                       len(unplanned_all), json.dumps(unplanned_all[:5], ensure_ascii=False)),
        "unplanned_keys": unplanned_all[:50], "unplanned_count": len(unplanned_all),
    })
    # C2：条件通道的**具名绑定**读数（需求项 ↔ 运行期根的连接本身也是判据）。
    binding_conflicts = list(conditional_block.get("identity_conflicts") or ())
    binding_seat_conflicts = list(conditional_block.get("seat_conflicts") or ())
    unattested = [row for row in (conditional_block.get("expected_rows") or ())
                  if str(row.get("attestation")) != "attested"]
    rows.append({
        "name": "conditional_instances_bound_and_attested",
        "ok": bool(conditional_block) and not binding_conflicts
              and not binding_seat_conflicts and not unattested,
        "applicable": True,
        "insufficient": bool(conditional_block) and not binding_conflicts
                        and not binding_seat_conflicts and bool(unattested),
        "detail": ("条件通道具名绑定：需求项 {0} 条 / 绑定 {1} 条；根身份冲突 {2} 条；"
                   "座位冲突 {3} 条；未受证实例 {4} 条（无登记也无见证 ⇒ INSUFFICIENT，"
                   "不写成通过）").format(
                       conditional_block.get("expected_instances"),
                       len(conditional_block.get("bindings") or ()),
                       len(binding_conflicts), len(binding_seat_conflicts),
                       len(unattested)),
        "identity_conflicts": binding_conflicts[:10],
        "seat_conflicts": binding_seat_conflicts[:10],
        "attestation_states": dict(conditional_block.get("attestation_states") or {}),
        "bindings": (conditional_block.get("bindings") or [])[:20],
    })
    covered = list((join.get("missing_split") or {}).get(
        "covered_by_other_channel") or ())
    rows.append({
        "name": "accounted_missing_are_complete_cases", "ok": not accounted,
        "applicable": True, "insufficient": bool(accounted),
        "detail": ("计划实例里被生产产物**显式解释**为未跑成的 {0} 条（明确失败/明确"
                   "因预算未执行）：账目诚实，但不满足功能完成 ⇒ INSUFFICIENT；"
                   "另有 **{1} 条由其它通道的可核产物承担**（basis 具名，"
                   "路径与摘要核验状态见 covered_by_other_channel —— 这一类比"
                   "「账目诚实」更强，不记 INSUFFICIENT）").format(
                       len(accounted), len(covered)),
        "accounted": accounted[:50], "accounted_count": len(accounted),
        "covered_by_other_channel": covered[:50],
        "covered_count": len(covered),
    })
    not_completed: List[Dict[str, Any]] = []
    for channel in CHANNELS:
        for item in ((channels.get(channel) or {}).get("items") or ()):
            if str(item.get("terminal")) != TERMINAL_COMPLETED:
                not_completed.append({"channel": channel, "key": item.get("key"),
                                      "terminal": item.get("terminal"),
                                      "reason": str(item.get("reason") or "")[:80]})
    rows.append({
        "name": "all_planned_instances_completed", "ok": not not_completed,
        "applicable": True, "insufficient": bool(not_completed),
        "detail": ("未完成可核的计划实例 {0} 条（明确失败/明确因预算未执行满足账目诚实，"
                   "但不满足功能完成）").format(len(not_completed)),
        "not_completed": not_completed[:50],
    })
    fakes: List[Dict[str, Any]] = []
    insufficient_digest: List[Dict[str, Any]] = []
    witness_mismatch: List[Dict[str, Any]] = []
    witness_verified = 0
    conditional_unregistered = 0
    for channel in CHANNELS:
        for item in ((channels.get(channel) or {}).get("items") or ()):
            digest = item.get("digest") or {}
            witness = dict(digest.get("witness") or item.get("root_witness") or {})
            if witness.get("present") and witness.get("matched") is not False:
                witness_verified += 1
            if witness.get("matched") is False:
                witness_mismatch.append({"channel": channel, "key": item.get("key"),
                                         "witness": witness})
            if digest.get("state") == "mismatch":
                fakes.append({"channel": channel, "key": item.get("key"),
                              "schema": digest.get("schema"),
                              "detail": digest.get("detail")})
            elif digest.get("state") == "witness_verified":
                # 旧读法（C2 之前的条件通道）：只有根见证、没有结果摘要登记。
                # 见证**不能**顶替结果完整性 ⇒ 记 INSUFFICIENT（只在旧产物里出现）。
                conditional_unregistered += 1
                insufficient_digest.append({"channel": channel, "key": item.get("key"),
                                            "state": "witness_only_no_registered_digest",
                                            "detail": ("只有 RootWitness，无登记结果摘要"
                                                       "⇒ 结果完整性 INSUFFICIENT")})
            elif digest.get("state") in (CONDITIONAL_DIGEST_INSUFFICIENT_STATES
                                        + ("missing_result_file",)):
                #: P25：条件通道的具名 INSUFFICIENT 状态（残壳/算不出/无法核）与
                #: 「没有登记」同档 —— 都不写成通过，均由 result_digest_equality_available
                #: 记 INSUFFICIENT。
                if channel == CHANNEL_CONDITIONAL:
                    conditional_unregistered += 1
                insufficient_digest.append({"channel": channel, "key": item.get("key"),
                                            "state": digest.get("state"),
                                            "detail": digest.get("detail")})
    rows.append({
        "name": "zero_fake_completions", "ok": not fakes, "applicable": True,
        "detail": ("按生产摘要 schema 重算：不一致 {0} 条（自然面板=嵌套臂结果块 canonical "
                   "sha256；家族评价=整文件 sha256；条件评价=**完成时登记的结果摘要**"
                   "（完成事务文件字节摘要 / 迭代状态规范载荷）重算比较）").format(len(fakes)),
        "fakes": fakes[:20], "mismatch_count": len(fakes),
    })
    rows.append({
        "name": "result_digest_equality_available",
        "ok": not insufficient_digest and not witness_mismatch,
        "applicable": True,
        "insufficient": bool(insufficient_digest) and not witness_mismatch,
        "detail": ("结果摘要可核读数：**RootWitness 有效 {0} 条**（P11 附属文件 "
                   "root-witnesses.jsonl，含 requirement_digest/content_digest/"
                   "actual_seed/cut_window_key；只作**根见证**，不作结果摘要）；"
                   "见证要求摘要与冻结参数重算不一致 {1} 条；"
                   "**结果摘要登记缺失/不足 {2} 条**（其中条件通道 {3} 条 ⇒ "
                   "INSUFFICIENT，不写成通过）").format(
                       witness_verified, len(witness_mismatch),
                       len(insufficient_digest), conditional_unregistered),
        "insufficient_items": insufficient_digest[:10],
        "insufficient_count": len(insufficient_digest),
        "witness_verified_count": witness_verified,
        "conditional_unregistered_digest": conditional_unregistered,
        "witness_mismatch": witness_mismatch[:10],
        "witness_mismatch_count": len(witness_mismatch),
    })
    cost_rows = cost_join_rows(join)
    unexplained = []
    for row in cost_rows:
        for key in ("delta", "delta_full", "delta_partial"):
            if key in row and abs(float(row[key] or 0.0)) > 1e-6:
                unexplained.append({"group": row.get("group"), "which": key,
                                    "value": row.get(key),
                                    "instances": row.get("instance_instances_observed"),
                                    "ledger_tables_full": row.get("ledger_tables_full")})
        if int(row.get("instance_instances_unexpected_extra") or 0):
            unexplained.append({"group": row.get("group"),
                                "which": "unexpected_extra_instances",
                                "value": row.get("instance_instances_unexpected_extra"),
                                "observed": row.get("instance_instances_observed"),
                                "expected": row.get("instance_instances_expected"),
                                "detail": ("观察到的实例条目多于期望行数，且没有具名依据"
                                           "（整体刷新批 / 其它通道承担）：总行数补不平")})
        for key in ("unexplained_ledger_count", "instances_without_ledger_count"):
            if int(row.get(key) or 0):
                unexplained.append({"group": row.get("group"), "which": key,
                                    "value": row.get(key),
                                    "rows": (row.get("unexplained_ledger_rows") or [])[:3],
                                    "instances":
                                        (row.get("instances_without_ledger_row")
                                         or [])[:3]})
        # P21：整体(normal)刷新批的**三方一致性**（记录 ↔ 账目 ↔ 实例）任一不闭合即未解释。
        for issue in (row.get("refresh_batch_issues") or ()):
            unexplained.append({"group": row.get("group"),
                                "which": "refresh_batch:" + str(issue.get("which")),
                                "value": issue.get("count") or issue.get("declared_tables"),
                                "detail": issue.get("detail"),
                                "keys": issue.get("keys") or []})
        # P21：家族组里**未解释**的缺失实例（已由其它通道具名承担的另列读数，不算缺口）。
        for key in (row.get("instances_missing_unaccounted") or ()):
            unexplained.append({"group": row.get("group"), "which": "unaccounted_missing",
                                "value": key})
    charges = join.get("ledger_charges") or {}
    unmatched = [row for row in (charges.get("unmatched_charged_rows") or ())
                 if float(row.get("charged") or 0.0) > 0.0]
    if unmatched:
        unexplained.append({"which": "unattributed_charged_rows",
                            "value": len(unmatched), "rows": unmatched[:3]})
    rows.append({
        "name": "cost_joined_per_channel", "ok": not unexplained, "applicable": True,
        "detail": ("逐通道三方对照（实例数 / 桌数 / 账本结算）＋逐行归属到具体实例"
                   "（整体(normal)刷新批按 `refresh:` 账步与 `checkpoints/refresh-*` "
                   "记录三方对账；家族缺失实例若已由条件通道具名承担则单列 basis）："
                   + json.dumps([{key: row.get(key) for key in (
                       "group", "instance_instances_plan_expected",
                       "instance_instances_expected", "instance_instances_observed",
                       "instance_tables", "ledger_tables_full", "delta", "delta_full",
                       "delta_partial", "ledger_rows", "ledger_settled_rows",
                       "unexplained_ledger_count", "instances_without_ledger_count",
                       "instances_missing_covered_count", "ledger_all_accounts")}
                       for row in cost_rows], ensure_ascii=False)),
        "cost_rows": cost_rows, "unexplained": unexplained,
        "unattributed_charged_rows": unmatched[:10],
    })
    return rows


def instance_rows(join: Mapping[str, Any]) -> List[Dict[str, Any]]:
    """报告用逐实例表。"""

    out: List[Dict[str, Any]] = []
    for channel in CHANNELS:
        for item in (((join.get("channels") or {}).get(channel) or {}).get("items") or ()):
            out.append({
                "iteration": item.get("iteration"), "channel": channel,
                "candidate_id": str(item.get("candidate_id") or "")[:12],
                "opponent_mix": item.get("opponent_mix"),
                "source_root_id": item.get("source_root_id"),
                "seat": item.get("seat"), "arm": item.get("arm"),
                "schedule": item.get("schedule"), "scope": item.get("scope"),
                "attempts": item.get("attempts"), "status": item.get("terminal"),
                "tables": item.get("tables_attempted"),
                "planned_tables": item.get("tables_planned"),
                "digest": (item.get("digest") or {}).get("state"),
            })
    return out
