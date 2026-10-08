#!/usr/bin/env python3
"""G118：一向听宽面冲突的同世界配对及依法可见后继行动链。"""

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
from statistics import mean

import g95_wider_discard_same_hand_preflight as g95
import g100_g96_visible_trajectory as g100
import g100_analyze_visible_trajectory as g100_analyze
import g108_fresh_hm_route_exposure as g108
import g114_fresh_score_matched_route_exposure as g114
import g118_one_shanten_route_select as g118_select


HERE = Path(__file__).resolve().parent
PREREG = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/G118-ONE-SHANTEN-NATURAL-ROUTE-BRANCH-PREREG-2026-09-28.md')
BASE = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g118-one-shanten-natural-route-20260928')


def sha(path: Path) -> str:
    """冻结选样、程序、合同的字节摘要。"""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def selected(split: str) -> list[dict]:
    """只读取相应根组的已冻结行动前清单，不接触另一组结算。"""
    source = json.loads(g118_select.OUT.read_text(encoding="utf-8"))
    if source["schema"] != "g118-one-shanten-route-selection/1":
        raise ValueError("G118 选样 schema 错误")
    rows = [item for item in source["selected"] if item["split"] == split]
    if not rows or len(rows) > 32:
        raise ValueError("G118 本组窗口数非法")
    return rows


def manifest(split: str, count: int) -> dict:
    """每个根组单独锁定证据，防止开发和评估标签混写。"""
    paths = {"prereg": PREREG, "script": Path(__file__),
             "selection": g118_select.OUT,
             "g114_rows": g114.OUT / "rows.jsonl",
             "g100_script": Path(g100.__file__),
             "g95_script": Path(g95.__file__),
             "contract": g95.g93.paired.CONTRACT}
    return {"schema": "g118-one-shanten-route-branch-manifest/1",
            "split": split, "windows_planned": count,
            "world_keys": ["historical", *g95.SAMPLES],
            "input_sha256": {name: sha(path) for name, path in paths.items()},
            "boundary": "开发和锁定根分账；九世界同窗相关，单局收益不等于完整桌。"}


def target_index() -> dict[tuple, tuple[dict, dict]]:
    """把 G114 行动前目标窗以房/根/座/单局键定位。"""
    rows = [json.loads(line) for line in (g114.OUT / "rows.jsonl").read_text(
        encoding="utf-8").splitlines()]
    if len(rows) != 256:
        raise ValueError("G118 G114 目标来源不完整")
    return {(row["mix"], row["root_index"], row["focal_seat"], target["round_no"]):
            (row, target)
            for row in rows for target in row["target_windows"]}


def value_entry(branch: dict, field: str) -> dict:
    """只有沿实际正常摸打轨迹事实完整时才断言入口有无。"""
    draws = g100_analyze.draw_discards(branch)
    unknown = any(row["one_draw_value_coverage"] != "complete" for row in draws)
    first = g100_analyze.first_entry(branch, field)
    return {"first_normal_draw_discard_index": first,
            "status": "reached" if first is not None else
                      "unknown" if unknown else "not_reached",
            "normal_draw_discards": len(draws)}


def one_window(item: dict, source: dict, target: dict, plan,
               contract: dict, versions: dict) -> dict:
    """重建完整父代表目标窗，再按相同世界双臂续打与轨迹记录。"""
    original = g95.CaptureWiderPolicy
    g95.CaptureWiderPolicy = g108.CaptureEveryHandPolicy
    try:
        captured, runtime, rules, situation, hands, _ = g95.run_full(
            plan, contract, versions, source["mix"])
    finally:
        g95.CaptureWiderPolicy = original
    record = captured.records.get(target["round_no"])
    if record is None:
        raise ValueError("G118 重跑目标单局未命中")
    frozen = {key: value for key, value in target.items() if key != "score_facts"}
    if g108.canonical_sha(g108.target_row(record)) != g108.canonical_sha(frozen):
        raise ValueError("G118 重跑目标观察或规则事实漂移")
    if (item["observation_sha256"] != target["observation_sha256"]
            or item["parent_action"] != record.parent_key
            or item["alternate_action"] != record.alternate_key):
        raise ValueError("G118 选样身份与重跑目标不符")
    window = record.request.window_key
    reference = runtime["engine"].frame(record.world).decisions[0].observation
    worlds = [("historical", record.world)]
    for sample_key in g95.SAMPLES:
        sampled = runtime["engine"].resample_public_consistent_hidden_world(
            record.world, focal_seat=window.seat, sample_key=sample_key)
        if runtime["engine"].frame(sampled).decisions[0].observation != reference:
            raise ValueError("G118 重采样改变焦点玩家可见观察")
        worlds.append((sample_key, sampled))
    pairs = []
    for sample_key, world in worlds:
        parent = g100.run_branch(
            world=world, captured=record, plan=plan, contract=contract,
            versions=versions, runtime=runtime, rules=rules,
            situation=situation, mix=source["mix"], forced_key=None)
        alternate = g100.run_branch(
            world=world, captured=record, plan=plan, contract=contract,
            versions=versions, runtime=runtime, rules=rules,
            situation=situation, mix=source["mix"], forced_key=record.alternate_key)
        p, a = parent["settlement"], alternate["settlement"]
        if p["scores_before"] != a["scores_before"]:
            raise ValueError("G118 双臂起点积分不一致")
        if sample_key == "historical":
            old = hands[window.round_no - 1]
            for field in ("round_no", "scores_before", "scores_after", "score_delta",
                          "winner_seat", "is_draw", "fan", "details"):
                if p[field] != old[field]:
                    raise ValueError("G118 历史父代单局恒等失败：" + field)
        pairs.append({
            "sample_key": sample_key, "parent": parent, "alternate": alternate,
            "focal_delta_alt_minus_parent":
                a["score_delta"][window.seat] - p["score_delta"][window.seat],
            "parent_class": g95.classify(p, window.seat),
            "alternate_class": g95.classify(a, window.seat),
            "route_entry": {
                arm: {
                    "ordinary": value_entry(branch, "one_draw_win_routes"),
                    "highfan": value_entry(branch, "one_draw_highfan_routes"),
                } for arm, branch in (("parent", parent), ("alternate", alternate))},
        })
    return {"split": item["split"], "mix": source["mix"],
            "white_bin": item["white_bin"], "root_index": source["root_index"],
            "focal_seat": source["focal_seat"], "round_no": target["round_no"],
            "table_id": source["table_id"],
            "observation_sha256": target["observation_sha256"],
            "parent_action": record.parent_key, "alternate_action": record.alternate_key,
            "score_facts": target["score_facts"], "world_pairs": pairs}


def summary(rows: list[dict], planned: int, split: str) -> dict:
    """按根组/池/白板分层保存描述统计，九世界不算独立样本。"""
    groups = {}
    for mix in ("H", "M"):
        for white in ("0", "1plus"):
            subset = [row for row in rows if row["mix"] == mix
                      and row["white_bin"] == white]
            means = [mean(pair["focal_delta_alt_minus_parent"]
                          for pair in row["world_pairs"]) for row in subset]
            groups[f"{mix}/{white}"] = {
                "windows": len(subset),
                "roots": len({row["root_index"] for row in subset}),
                "world_pairs": 9 * len(subset),
                "window_mean_delta_sum": sum(means),
                "positive_windows": sum(value > 0 for value in means),
                "negative_windows": sum(value < 0 for value in means),
                "zero_windows": sum(value == 0 for value in means),
            }
    return {"schema": "g118-one-shanten-route-branch-summary/1",
            "split": split, "status": "complete" if len(rows) == planned else "in_progress",
            "windows_completed": len(rows), "windows_planned": planned,
            "groups": groups,
            "boundary": "同局机制研究；锁定根在预先冻结特征/规则前不得打开。"}


def main() -> None:
    """本次仅执行明确指定的根组，逐窗保存可续跑证据。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--split", choices=("development", "locked_evaluation"), required=True)
    parser.add_argument("--max-new", type=int, default=0)
    args = parser.parse_args()
    items = selected(args.split)
    expected = manifest(args.split, len(items))
    index = target_index()
    contract = json.loads(g95.g93.paired.CONTRACT.read_text(encoding="utf-8"))
    versions = g95.g93.natural.stage.contract_versions_block(contract)
    plans = {(mix, root, seat): plan for mix, root, seat, plan in g114.plans(contract)}
    out = _project_file(_PROJECT_ROOT, BASE / args.split)
    out.mkdir(parents=True, exist_ok=True)
    manifest_path = out / "manifest.json"
    if manifest_path.exists():
        if json.loads(manifest_path.read_text(encoding="utf-8")) != expected:
            raise ValueError("G118 本根组批次清单变化，拒绝混写")
    else:
        manifest_path.write_text(json.dumps(expected, ensure_ascii=False,
                                            sort_keys=True, indent=2) + "\n", encoding="utf-8")
    rows_path = out / "rows.jsonl"
    rows = ([json.loads(line) for line in rows_path.read_text(encoding="utf-8").splitlines()]
            if rows_path.exists() else [])
    for old, item in zip(rows, items):
        if ([old["mix"], old["root_index"], old["focal_seat"], old["round_no"]]
                != item["window"]
                or old["observation_sha256"] != item["observation_sha256"]):
            raise ValueError("G118 已有行非冻结选样前缀")
    added = 0
    with rows_path.open("a", encoding="utf-8") as stream:
        for item in items[len(rows):]:
            key = tuple(item["window"])
            source, target = index[key]
            plan = plans[key[:3]]
            row = one_window(item, source, target, plan, contract, versions)
            stream.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
            rows.append(row)
            added += 1
            print(json.dumps({"split": args.split, "window": item["window"],
                              "world_pairs": len(row["world_pairs"])},
                             ensure_ascii=False), flush=True)
            if args.max_new > 0 and added >= args.max_new:
                break
    result = summary(rows, len(items), args.split)
    (out / "result.json").write_text(json.dumps(result, ensure_ascii=False,
                                          sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
