#!/usr/bin/env python3
"""G164：在 G161 开发世界复跑首弃后的即时他家响应。"""

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
import hashlib
import json
import os
from pathlib import Path

import g46_paired_first_response_audit as response
import g100_g96_visible_trajectory as trajectory
import g126_all_draw_natural_width_exposure as capture
import g160_multi_action_value_source as source
import g161_multi_action_development_teacher as teacher


HERE = Path(__file__).resolve().parent
PREREG = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/G164-FIRST-RESPONSE-AND-SCORE-CONFLICT-PREREG-2026-09-28.md')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g164-first-response-score-conflict-20260928')
G161 = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g161-multi-action-development-teacher-20260928')


def sha(path: Path) -> str:
    """以原始字节绑定量具和已冻结开发证据。"""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def manifest() -> dict:
    """完整锁定首次响应审计的输入身份，不读取机制锁定层。"""
    paths = {
        "prereg": PREREG,
        "script": Path(__file__),
        "g160_selection": source.OUT / "selection.json",
        "g161_manifest": _project_file(_PROJECT_ROOT, G161 / "manifest.json"),
        "g161_rows": _project_file(_PROJECT_ROOT, G161 / "rows.jsonl"),
        "g161_result": _project_file(_PROJECT_ROOT, G161 / "result.json"),
        "g46_response_rule": Path(response.__file__),
        "g100_trajectory": Path(trajectory.__file__),
        "capture": Path(capture.__file__),
    }
    return {
        "schema": "g164-first-response-score-conflict-manifest/1",
        "windows_planned": 49,
        "world_keys": list(teacher.WORLD_KEYS),
        "input_sha256": {name: sha(path) for name, path in paths.items()},
        "boundary": "已看开发收益后的同世界机制复核；非线上特征、隐藏验证或整桌收益。",
    }


def branch_response(*, world, record, plan, contract, versions, runtime,
                    rules, situation, mix: str, forced_key: str | None,
                    round_no: int, old_arm: dict, seat: int) -> dict:
    """捕捉真实模拟决策，再逐臂与 G161 冻结轨迹和结算恒等对账。"""
    module = trajectory.g95.g93
    original = module.resume_match
    outcomes = []

    async def capture_outcome(**kwargs):
        result = await original(**kwargs)
        outcomes.append(result)
        return result

    module.resume_match = capture_outcome
    try:
        branch = trajectory.run_branch(
            world=world, captured=record, plan=plan, contract=contract,
            versions=versions, runtime=runtime, rules=rules,
            situation=situation, mix=mix, forced_key=forced_key)
    finally:
        module.resume_match = original
    if len(outcomes) != 1 or not outcomes[0].decisions:
        raise ValueError("G164 分支缺少唯一模拟决策序列")
    if teacher.compact_arm(branch, seat) != old_arm:
        raise ValueError("G164 分支与 G161 原轨迹或结算不一致")
    outcome = outcomes[0]
    kind, responder = response.immediate_response(
        outcome, outcome.decisions[0].decision_id, round_no)
    return {"kind": kind, "responder_seat": responder}


def one_window(item: dict, old: dict, table: dict, target: dict, plan,
               contract: dict, versions: dict, scorer) -> dict:
    """只重跑固定选样对应的一个开发窗及其 33 个已冻结世界。"""
    g95 = source.source.g95
    original = g95.CaptureWiderPolicy
    g95.CaptureWiderPolicy = capture.CaptureEveryHandAllDrawPolicy
    try:
        captured, runtime, rules, situation, hands, _ = g95.run_full(
            plan, contract, versions, item["mix"])
    finally:
        g95.CaptureWiderPolicy = original
    record = captured.records.get(item["round_no"])
    if (record is None or len(hands) != 8
            or capture.scored_target(record, scorer) != target
            or record.parent_key != item["parent_action"]
            or record.alternate_key != item["alternate_action"]):
        raise ValueError("G164 父代表、观察或合法动作身份漂移")
    reference = runtime["engine"].frame(record.world).decisions[0].observation
    pairs = []
    for old_pair, sample_key in zip(old["world_pairs"], teacher.WORLD_KEYS):
        if old_pair["sample_key"] != sample_key:
            raise ValueError("G164 G161 世界键顺序漂移")
        world = (record.world if sample_key == "historical" else
                 runtime["engine"].resample_public_consistent_hidden_world(
                     record.world, focal_seat=item["focal_seat"],
                     sample_key=sample_key))
        if runtime["engine"].frame(world).decisions[0].observation != reference:
            raise ValueError("G164 重采样改变玩家可见观察")
        parent = branch_response(
            world=world, record=record, plan=plan, contract=contract,
            versions=versions, runtime=runtime, rules=rules,
            situation=situation, mix=item["mix"], forced_key=None,
            round_no=item["round_no"], old_arm=old_pair["parent"],
            seat=item["focal_seat"])
        alternate = branch_response(
            world=world, record=record, plan=plan, contract=contract,
            versions=versions, runtime=runtime, rules=rules,
            situation=situation, mix=item["mix"],
            forced_key=item["alternate_action"],
            round_no=item["round_no"], old_arm=old_pair["alternate"],
            seat=item["focal_seat"])
        pairs.append({"sample_key": sample_key,
                      "parent_response": parent,
                      "alternate_response": alternate,
                      "same_response": parent == alternate,
                      "focal_delta_alt_minus_parent":
                          old_pair["focal_delta_alt_minus_parent"],
                      "parent_class": old_pair["parent_class"],
                      "alternate_class": old_pair["alternate_class"]})
    if len(pairs) != 33:
        raise ValueError("G164 开发世界数不足")
    return {name: item[name] for name in (
        "mix", "root_index", "focal_seat", "round_no", "white_before",
        "observation_sha256", "parent_action", "alternate_action")} | {
        "score_facts": old["score_facts"], "world_pairs": pairs}


def main() -> None:
    """按冻结选样顺序增量落盘，防止长任务中断后更换目标。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-new", type=int, default=0)
    args = parser.parse_args()
    items = teacher.selected()
    previous = [json.loads(line) for line in
                (_project_file(_PROJECT_ROOT, G161 / "rows.jsonl")).read_text(encoding="utf-8").splitlines()]
    if len(items) != 49 or len(previous) != 49:
        raise ValueError("G164 来源未完成 49 个开发窗")
    result = json.loads((_project_file(_PROJECT_ROOT, G161 / "result.json")).read_text(encoding="utf-8"))
    if (result["status"] != "complete" or
            result["rows_sha256"] != sha(_project_file(_PROJECT_ROOT, G161 / "rows.jsonl"))):
        raise ValueError("G164 G161 摘要不守恒")
    expected = manifest()
    targets = teacher.index()
    g95 = source.source.g95
    contract = json.loads(g95.g93.paired.CONTRACT.read_text(encoding="utf-8"))
    versions = g95.g93.natural.stage.contract_versions_block(contract)
    scorer = capture.g87.c31.load_parent()
    plans = {(mix, root, seat): plan
             for mix, root, seat, plan in source.plans(contract)}
    OUT.mkdir(parents=True, exist_ok=True)
    manifest_path = _project_file(_PROJECT_ROOT, OUT / "manifest.json")
    if manifest_path.exists():
        if json.loads(manifest_path.read_text(encoding="utf-8")) != expected:
            raise ValueError("G164 清单或代码变动，拒绝混写")
    else:
        manifest_path.write_text(json.dumps(expected, ensure_ascii=False,
                                            sort_keys=True, indent=2) + "\n",
                                 encoding="utf-8")
    rows_path = _project_file(_PROJECT_ROOT, OUT / "rows.jsonl")
    rows = ([json.loads(line) for line in rows_path.read_text(
        encoding="utf-8").splitlines()] if rows_path.exists() else [])
    for existing, item in zip(rows, items):
        if any(existing[name] != item[name] for name in (
                "mix", "root_index", "focal_seat", "round_no",
                "observation_sha256", "parent_action", "alternate_action")):
            raise ValueError("G164 已有行不是冻结开发选样前缀")
    added = 0
    with rows_path.open("a", encoding="utf-8") as stream:
        for item, old in zip(items[len(rows):], previous[len(rows):]):
            identity = (item["mix"], item["root_index"],
                        item["focal_seat"], item["round_no"])
            if any(old[name] != item[name] for name in (
                    "mix", "root_index", "focal_seat", "round_no",
                    "observation_sha256", "parent_action", "alternate_action")):
                raise ValueError("G164 G161 行不是冻结开发选样前缀")
            table, target = targets[identity]
            row = one_window(item, old, table, target, plans[identity[:3]],
                             contract, versions, scorer)
            stream.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
            added += 1
            print(json.dumps({"windows_completed": len(rows) + added,
                              "mix": item["mix"], "root": item["root_index"]},
                             ensure_ascii=False), flush=True)
            if args.max_new and added >= args.max_new:
                break
    print(json.dumps({"windows_completed": len(rows) + added,
                      "windows_planned": len(items)}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
