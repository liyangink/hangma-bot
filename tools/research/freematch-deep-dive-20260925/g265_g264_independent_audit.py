#!/usr/bin/env python3
"""G265：只读验收 G264 开发批；不修改冻结执行器或任何牌局证据。

``--partial`` 只核已经落盘的阶段和完整三臂配对，不输出中途收益。
不带 ``--partial`` 时必须收齐 H/M×32 根×四座×三臂，并独立重算汇总。
"""

from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/freematch-deep-dive-20260925'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

import argparse
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any

import g264_first_divergence_triarm_panel as g264


HERE = Path(__file__).resolve().parent
DEFAULT_OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g264-first-divergence-development-20260929')
PANEL_SEED = 2026122964
ROOT_START = 3
ROOTS_PER_MIX = 32
ROOT_FILE = re.compile(r"^[HM]-r(\d{4})-s[0-3]-.+\.json(?:\.tmp)?$")
RUNTIME_FIELDS = ("illegal_choices", "fallbacks", "timeouts",
                  "auto_actions", "audit_missing")
POLICY_FAILURE_FIELDS = ("action_value_failed", "ambiguous_diagnostics",
                         "unclassified_action_value")


def _read_json(path: Path) -> dict[str, Any]:
    """从指定文件读取完整 JSON 对象；缺失、坏格式均拒绝。"""

    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("验收证据不是 JSON 对象：" + str(path))
    return value


def _zero_integer(mapping: dict[str, Any], name: str, *, where: str) -> None:
    """验收计数必须为整数零，不能让 bool 或缺失值冒充无故障。"""

    if type(mapping.get(name)) is not int or mapping[name] != 0:
        raise ValueError(f"{where} 的 {name} 非零或缺失")


def verify_execution(table: dict[str, Any]) -> None:
    """核驱动实际动作及评分内部降级，复核座位身份和审计摘要。"""

    where = str(table.get("table_id"))
    runtime = table["result"]["runtime_counts"]
    if not isinstance(runtime, dict):
        raise ValueError(where + " 缺驱动计数")
    for name in RUNTIME_FIELDS:
        _zero_integer(runtime, name, where=where)
    audit = g264.panel.natural.execution_audit.verify_table(table)
    if not isinstance(audit, dict):
        raise ValueError(where + " 缺评分执行审计")
    for name in POLICY_FAILURE_FIELDS:
        _zero_integer(audit, name, where=where)
    kinds = audit.get("failure_kinds")
    if not isinstance(kinds, dict):
        raise ValueError(where + " 缺评分失败分类")
    for name in g264.panel.natural.execution_audit.FAILURE_KINDS:
        _zero_integer(kinds, name, where=where)


def verify_confirmation_closed(evidence_parent: Path) -> None:
    """检查同一证据目录下所有 G264 阶段，确认预留根 35–66 未打开。"""

    for batch in evidence_parent.glob("g264-first-divergence-*"):
        stages = batch / "stages"
        if not stages.is_dir():
            continue
        for path in stages.iterdir():
            if not path.is_file():
                continue
            match = ROOT_FILE.fullmatch(path.name)
            if match is None:
                raise ValueError("G264 阶段文件名无法核根身份：" + str(path))
            root = int(match.group(1))
            if 35 <= root <= 66:
                raise ValueError("G264 确认根已提前打开：" + str(path))
            if path.suffix == ".json":
                row = _read_json(path)
                if row.get("root_index") != root:
                    raise ValueError("G264 阶段文件名与内容根身份不符：" + str(path))


def audit(out: Path, *, partial: bool) -> dict[str, Any]:
    """逐阶段和三臂桌复核；完整模式还要求严格收齐并重算已存汇总。"""

    args = argparse.Namespace(panel_seed=PANEL_SEED, root_start=ROOT_START,
                              roots_per_mix=ROOTS_PER_MIX)
    frozen = _read_json(out / "manifest.json")
    if frozen != g264.manifest(args):
        raise ValueError("G264 开发清单或冻结源码/规则身份漂移")
    if (frozen.get("development_roots") != [3, 34]
            or frozen.get("confirmation_roots") != [35, 66]
            or frozen.get("planned_complete_tables") != 1536):
        raise ValueError("G264 开发/确认根或完整桌规模与预注册不符")
    verify_confirmation_closed(out.parent)
    errors = list((out / "errors").glob("*.json"))
    if errors:
        raise ValueError("G264 存在失败阶段诊断，不得签发无偏效果：" + str(errors[0]))

    units = [(mix, root, seat, arm, PANEL_SEED)
             for mix in g264.panel.MIXES
             for root in range(ROOT_START, ROOT_START + ROOTS_PER_MIX)
             for seat in g264.panel.SEATS for arm in g264.ARMS]
    known = {g264.panel.paired.unit_path(out, unit): unit for unit in units}
    stages = out / "stages"
    available = sorted(stages.glob("*.json")) if stages.is_dir() else []
    extra = [path for path in available if path not in known]
    if extra:
        raise ValueError("G264 开发批存在计划外阶段：" + str(extra[0]))

    grouped: dict[tuple[str, int, int], dict[str, dict[str, Any]]] = {}
    for path in available:
        unit = known[path]
        row = _read_json(path)
        g264.verify_unit(row, unit=unit,
                         tables_per_stage=frozen["tables_per_stage"])
        for table in row["stage"]["tables"]:
            verify_execution(table)
        grouped.setdefault(unit[:3], {})[unit[3]] = row

    paired_tables = 0
    for arms in grouped.values():
        if set(arms) != set(g264.ARMS):
            continue
        for index in range(frozen["tables_per_stage"]):
            rows = {arm: arms[arm]["stage"]["tables"][index] for arm in g264.ARMS}
            routes = {arm: arms[arm]["stage"]["route_tables"][index]
                      for arm in g264.ARMS}
            g264.verify_triplet(rows, routes)
            paired_tables += 1

    complete = len(available) == len(units)
    if not partial and not complete:
        raise ValueError(f"G264 开发批未收齐：{len(available)}/{len(units)} 阶段")
    result_path = out / "result.json"
    if result_path.exists() and not complete:
        raise ValueError("G264 汇总早于全部开发阶段出现")
    if not partial:
        if not result_path.exists():
            raise ValueError("G264 开发批缺完整汇总 result.json")
        recomputed = g264.result(args=args, units=units, out=out,
                                 tables_per_stage=frozen["tables_per_stage"])
        recomputed["manifest_sha256"] = sha256(
            (out / "manifest.json").read_bytes()).hexdigest()
        if _read_json(result_path) != recomputed:
            raise ValueError("G264 汇总与全部原始阶段重新计算结果不一致")
        if len(recomputed["root_clusters"]) != 64 or paired_tables != 512:
            raise ValueError("G264 独立牌山根或自然桌配对数量错误")
    return {
        "schema": "g265-g264-independent-audit/1",
        "status": "complete_verified" if not partial else
                  "partial_wiring_verified" if not complete else "complete_wiring_verified",
        "verified_stages": len(available),
        "planned_stages": len(units),
        "verified_arm_tables": len(available) * frozen["tables_per_stage"],
        "verified_natural_triplets": paired_tables,
        "confirmation_roots_unopened": True,
        "effect_claim_allowed": not partial,
    }


def main() -> None:
    """只打印验收状态；不写或改任何研究、线上文件。"""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--partial", action="store_true")
    args = parser.parse_args()
    print(json.dumps(audit(args.out, partial=args.partial), ensure_ascii=False,
                     sort_keys=True))


if __name__ == "__main__":
    main()
