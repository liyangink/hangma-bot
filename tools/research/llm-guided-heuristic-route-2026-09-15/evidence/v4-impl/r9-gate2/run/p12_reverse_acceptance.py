#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""P12 · G1 反向验收：两条反例**必须红**（外加必须绿的控制组）。

裁定原文（R9-ACCEPTANCE-AND-Q1-Q7-RULING §5 G1）：

> 反向验收至少包括"删一个目标实例但保留其他通道行"和"修改结果内容而不更新摘要"，
> 两者必须红。

本脚本在**沙箱副本**上做四处比对（绝不改任何真实产物）：

| 用例 | 操作 | 期望 |
| --- | --- | --- |
| control | 原样副本 | 绿（没有缺失、没有摘要不符） |
| A | 删掉一个已完成的目标实例行，**保留其它通道的行** | 红（逐键连接发现未解释缺失） |
| B1 | 改自然面板结果里的一个值，**保留原摘要**（嵌套样本摘要） | 红（重算不一致） |
| B2 | 改家族评价结果文件里的一个值，**保留原摘要**（整文件 sha256） | 红 |

用例 A 同时打印**旧判据**（`len(所有实例行) ≥ 计划自然实例数`）的读数：
它在反例下仍然是绿的 —— 这正是 G1 要修的东西。
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

import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

import p12_reconcile as R        # noqa: E402
import p12_status as S           # noqa: E402


def _copy_run(run_root: Path, target: Path) -> Path:
    """只拷贝对账需要的产物（实例台账 + 结果文件 + 状态），不拷账本本体。"""

    target.mkdir(parents=True, exist_ok=True)
    for iter_dir in R.iter_dirs(run_root):
        out = target / "iterations" / iter_dir.name
        out.mkdir(parents=True, exist_ok=True)
        for name in ("instances.json", "state.json"):
            src = iter_dir / name
            if src.is_file():
                shutil.copy2(src, out / name)
        # 台账里的 result_path 是**绝对路径**（指向真实运行目录）：沙箱副本必须把它
        # 重指到副本内部，否则摘要核验读的还是真实产物，反例永远不会红。
        ledger = out / "instances.json"
        if ledger.is_file():
            payload = _read(ledger)
            instances = dict(payload.get("instances") or {})
            for row in instances.values():
                for attempt in (row.get("attempts") or ()):
                    result_path = attempt.get("result_path")
                    if result_path and str(result_path).startswith(str(run_root)):
                        attempt["result_path"] = str(target) + str(result_path)[
                            len(str(run_root)):]
            payload["instances"] = instances
            _write(ledger, payload)
        for panel in ("natural-H", "natural-M"):
            src = iter_dir / panel / "panel.json"
            if src.is_file():
                (out / panel).mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, out / panel / "panel.json")
        for eval_dir in (iter_dir / "family").glob("*/evaluation.json"):
            dest_dir = out / "family" / eval_dir.parent.name
            dest_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(eval_dir, dest_dir / "evaluation.json")
        for checkpoint in (iter_dir / "checkpoints").glob("*.json"):
            (out / "checkpoints").mkdir(parents=True, exist_ok=True)
            shutil.copy2(checkpoint, out / "checkpoints" / checkpoint.name)
        conditional = iter_dir / "conditional" / "evaluation.json"
        if conditional.is_file():
            (out / "conditional").mkdir(parents=True, exist_ok=True)
            shutil.copy2(conditional, out / "conditional" / "evaluation.json")
    return target


def _read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _first_completed_natural(run_root: Path) -> Optional[Dict[str, Any]]:
    for entry in R.observed_instances(run_root):
        row = entry["row"]
        attempts = list(row.get("attempts") or ())
        if (entry["channel"] in (R.CHANNEL_NATURAL, R.CHANNEL_SHARED_BASELINE)
                and attempts and str(attempts[-1].get("status")) == "completed"):
            return {"entry": entry, "row": row, "path":
                    R.iter_dirs(run_root)[0] if False else None}
    return None


def case_control(run_root: Path, plan: Mapping[str, Any], sandbox: Path) -> Dict[str, Any]:
    join = R.reconcile_instances(run_root, plan)
    checks = {row["name"]: row for row in R.check_rows(join)}
    lost = checks["zero_lost_instances_by_key"]
    fakes = checks["zero_fake_completions"]
    return {
        "case": "control", "expect": "green",
        "unaccounted_missing": lost.get("unaccounted_count"),
        "digest_mismatches": fakes.get("mismatch_count"),
        "ok": bool(lost["ok"]) and not lost.get("unaccounted_count")
              and not fakes.get("mismatch_count"),
        "detail": "原样副本：逐键连接无未解释缺失、无摘要不符",
    }


def case_delete_instance(run_root: Path, plan: Mapping[str, Any],
                         sandbox: Path) -> Dict[str, Any]:
    """反例 A：删掉一个已完成目标实例，保留其它通道的行。"""

    target = _copy_run(run_root, sandbox / "case-a")
    # 旧判据（被修掉的那条）在**删除前**的读数：用于证明"删除对它不可见"。
    by_name = {row["category"]: row for row in plan["budget"]["by_category"]}
    planned_natural = int(by_name["natural_full"]["n_instances"])

    def _row_count(root: Path) -> int:
        return sum(len(list((R.read_json(iter_dir / "instances.json") or {}).get(
            "instances") or {})) for iter_dir in R.iter_dirs(root))

    old_before = _row_count(target) >= planned_natural
    victim = None
    for iter_dir in R.iter_dirs(target):
        payload = _read(iter_dir / "instances.json")
        instances = dict(payload.get("instances") or {})
        for key, row in instances.items():
            attempts = list(row.get("attempts") or ())
            if (str(row.get("source_root_id")).startswith("np-")
                    and attempts and str(attempts[-1].get("status")) == "completed"):
                victim = (iter_dir, key, row)
                break
        if victim:
            del instances[victim[1]]
            payload["instances"] = instances
            _write(iter_dir / "instances.json", payload)
            break
    join = R.reconcile_instances(target, plan)
    checks = {row["name"]: row for row in R.check_rows(join)}
    lost = checks["zero_lost_instances_by_key"]
    all_rows = _row_count(target)
    old_after = all_rows >= planned_natural
    return {
        "case": "A_delete_target_instance",
        "expect": "red",
        "victim_instance_key": (victim[1] if victim else None),
        "old_criterion_reading": {
            "rows": all_rows, "planned_natural_instances": planned_natural,
            "old_check_green_before": old_before, "old_check_green_after": old_after,
            "insensitive_to_deletion": old_before == old_after,
            "note": ("旧判据只比数量：删一条目标实例后它的判定**不变**"
                     "（这就是 G1 缺陷；在行数充足的运行里它仍为绿，"
                     "在本来就不足的中断运行里它本来也是红——两种情形它都看不见这次删除）")},
        "unaccounted_missing": lost.get("unaccounted_count"),
        "unaccounted_keys": lost.get("unaccounted_missing"),
        "ok": (not lost["ok"]) and bool(lost.get("unaccounted_count")),
        "detail": ("删一条已完成自然实例后：新判据按冻结实例键报未解释缺失（红）；"
                   "旧判据读数 前={0}/后={1}（行数余量 {2}：余量 >0 时它对删除**不敏感**，"
                   "余量 =0 时它会因为边界巧合翻红——两种情形它都没「看见」哪一条实例没了）"
                   ).format(old_before, old_after,
                            _row_count(run_root) - planned_natural),
    }


def _mutate_arm_block(panel_path: Path, needle_arm: str) -> Optional[Dict[str, Any]]:
    payload = _read(panel_path)
    for sample in (payload.get("samples") or ()):
        block = (sample.get("arms") or {}).get(needle_arm)
        if isinstance(block, Mapping) and "u" in block:
            before = block.get("u")
            block["u"] = 0.0 if float(before or 0.0) != 0.0 else 1.0
            _write(panel_path, payload)
            return {"path": str(panel_path), "field": "arms.{0}.u".format(needle_arm),
                    "before": before, "after": block["u"]}
    return None


def case_tamper_nested_digest(run_root: Path, plan: Mapping[str, Any],
                              sandbox: Path) -> Dict[str, Any]:
    """反例 B1：改自然面板结果里的一个值，保留原摘要（嵌套样本摘要）。"""

    target = _copy_run(run_root, sandbox / "case-b1")
    mutation = None
    for iter_dir in R.iter_dirs(target):
        for panel in ("natural-H", "natural-M"):
            path = iter_dir / panel / "panel.json"
            if path.is_file():
                mutation = _mutate_arm_block(path, "candidate")
                if mutation:
                    break
        if mutation:
            break
    join = R.reconcile_instances(target, plan)
    checks = {row["name"]: row for row in R.check_rows(join)}
    fakes = checks["zero_fake_completions"]
    return {
        "case": "B1_tamper_nested_result_keep_digest", "expect": "red",
        "mutation": mutation,
        "digest_mismatches": fakes.get("mismatch_count"),
        "mismatch_examples": fakes.get("fakes"),
        "ok": bool(fakes.get("mismatch_count")),
        "detail": ("自然面板嵌套臂结果块被改而台账摘要未更新 ⇒ 按生产 schema "
                   "重算不一致（红）"),
    }


def case_tamper_whole_file_digest(run_root: Path, plan: Mapping[str, Any],
                                  sandbox: Path) -> Dict[str, Any]:
    """反例 B2：改家族评价结果文件里的一个值，保留原摘要（整文件 sha256）。"""

    target = _copy_run(run_root, sandbox / "case-b2")
    mutation = None
    for iter_dir in R.iter_dirs(target):
        for eval_path in sorted((iter_dir / "family").glob("*/evaluation.json")):
            payload = _read(eval_path)
            done = False
            for sample in (payload.get("samples") or ()):
                for arm, block in (sample.get("arms") or {}).items():
                    if isinstance(block, Mapping) and "u" in block:
                        before = block.get("u")
                        block["u"] = 0.0 if float(before or 0.0) != 0.0 else 1.0
                        mutation = {"path": str(eval_path),
                                    "field": "samples[0].arms.{0}.u".format(arm),
                                    "before": before, "after": block["u"]}
                        done = True
                        break
                if done:
                    break
            if done:
                _write(eval_path, payload)
                break
        if mutation:
            break
    join = R.reconcile_instances(target, plan)
    checks = {row["name"]: row for row in R.check_rows(join)}
    fakes = checks["zero_fake_completions"]
    return {
        "case": "B2_tamper_whole_file_keep_digest", "expect": "red",
        "mutation": mutation, "digest_mismatches": fakes.get("mismatch_count"),
        "mismatch_examples": fakes.get("fakes"),
        "ok": bool(fakes.get("mismatch_count")),
        "detail": "家族评价整文件被改而台账摘要未更新 ⇒ 整文件 sha256 不一致（红）",
    }


def run_all(*, run_root: Path, plan: Mapping[str, Any], sandbox: Optional[Path] = None
            ) -> Dict[str, Any]:
    temp = Path(sandbox) if sandbox else Path(tempfile.mkdtemp(prefix="p12-reverse-"))
    temp.mkdir(parents=True, exist_ok=True)
    cases = [
        case_control(run_root, plan, temp),
        case_delete_instance(run_root, plan, temp),
        case_tamper_nested_digest(run_root, plan, temp),
        case_tamper_whole_file_digest(run_root, plan, temp),
    ]
    return {
        "schema": "sitin-gate2-reverse-acceptance/1",
        "run_root": str(run_root), "sandbox_root": str(temp),
        "cases": cases,
        "ok": all(bool(case["ok"]) for case in cases),
        "signoff": S.rollup([{"name": case["case"],
                              "ok": bool(case["ok"]), "applicable": True,
                              "detail": case["detail"]} for case in cases]),
        "note": ("全部在沙箱副本上做：真实运行目录与既有 evidence 一律不改；"
                 "两条反例必须红、控制组必须绿，否则本脚本返回非零"),
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="P12 反向验收（沙箱副本，只读真实产物）")
    parser.add_argument("--run-root", required=True, help="真实运行目录（只读）")
    parser.add_argument("--plan", required=True, help="计划 JSON")
    parser.add_argument("--out", required=True, help="结果 JSON 输出路径")
    parser.add_argument("--keep-sandbox", action="store_true",
                        help="保留沙箱副本（默认删除，避免留下大体积副本）")
    parser.add_argument("--sandbox", default=None, help="沙箱根（默认系统临时目录）")
    args = parser.parse_args(argv)
    plan = json.loads(Path(args.plan).read_text(encoding="utf-8"))
    # 一律解析成**绝对路径**：副本里的 result_path 重写是前缀匹配的，
    # 传相对路径会让核验仍读真实产物 ⇒ 反例静默变绿（假绿，2026-09-18 实测踩过）。
    result = run_all(run_root=Path(args.run_root).resolve(), plan=plan,
                     sandbox=Path(args.sandbox) if args.sandbox else None)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2),
                        encoding="utf-8")
    print("P12 反向验收（沙箱副本，0 桌 / 0 模型调用）")
    for case in result["cases"]:
        print("  {0:<6} {1:<38} 期望 {2:<5} 实际 {3}".format(
            "PASS" if case["ok"] else "FAIL", case["case"], case["expect"],
            json.dumps({key: value for key, value in case.items()
                        if key in ("unaccounted_missing", "digest_mismatches",
                                   "old_criterion_reading", "mutation")},
                       ensure_ascii=False)[:200]))
    print("  总判定：{0}".format("PASS（两条反例都红、控制组绿）"
                                 if result["ok"] else "FAIL（反例未按预期变红）"))
    print("  结果已落盘：{0}".format(out_path))
    if not args.keep_sandbox and not args.sandbox:
        shutil.rmtree(result["sandbox_root"], ignore_errors=True)
        print("  沙箱已清理：{0}".format(result["sandbox_root"]))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
