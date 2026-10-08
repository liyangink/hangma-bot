#!/usr/bin/env python3
"""G128：未吃碰二向听窗口的同世界父代/备选一次弃牌续打。"""

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
import g118_one_shanten_route_branch as g118
import g126_all_draw_natural_width_exposure as g126
import g128_no_claim_two_shanten_select as select


HERE = Path(__file__).resolve().parent
BASE = select.OUT.parent
PREREG = select.PREREG


def sha(path: Path) -> str:
    """绑定冻结选样、来源、分支程序和赛事合同。"""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def selected(split: str) -> list[dict]:
    """只返回指定根组的结果盲名单。"""
    source = json.loads(select.OUT.read_text(encoding="utf-8"))
    if source["schema"] != "g128-no-claim-two-shanten-selection/1":
        raise ValueError("G128 选样 schema 不符")
    items = [item for item in source["selected"] if item["split"] == split]
    if len(items) != (38 if split == "development" else 42):
        raise ValueError("G128 指定根组选窗数漂移")
    return items


def manifest(split: str, count: int) -> dict:
    """各根组单独锁定，不允许开发和锁定标签混写。"""
    paths = {"prereg": PREREG, "script": Path(__file__),
             "selection": select.OUT,
             "g126_rows": g126.OUT / "rows.jsonl",
             "g100_script": Path(g100.__file__),
             "g95_script": Path(g95.__file__),
             "g126_script": Path(g126.__file__),
             "contract": g95.g93.paired.CONTRACT}
    return {"schema": "g128-no-claim-two-shanten-branch-manifest/1",
            "split": split, "windows_planned": count,
            "world_keys": ["historical", *g95.SAMPLES],
            "input_sha256": {name: sha(path) for name, path in paths.items()},
            "boundary": "同窗九世界相关；仅作单局机制分析，不作发布积分。"}


def target_index() -> dict[tuple, tuple[dict, dict]]:
    """把 G126 全部目标窗按池、根、座、单局唯一定位。"""
    rows = [json.loads(line) for line in (g126.OUT / "rows.jsonl").read_text(
        encoding="utf-8").splitlines()]
    if len(rows) != 256:
        raise ValueError("G128 G126 来源不完整")
    index = {(row["mix"], row["root_index"], row["focal_seat"], target["round_no"]):
             (row, target) for row in rows for target in row["target_windows"]}
    if len(index) != 847:
        raise ValueError("G128 G126 目标窗口身份不唯一")
    return index


def one_window(item: dict, source: dict, target: dict, plan,
               contract: dict, versions: dict, scorer) -> dict:
    """重建父代表；同世界仅强制备选第一弃牌，随后冻结策略续打。"""
    original = g95.CaptureWiderPolicy
    g95.CaptureWiderPolicy = g126.CaptureEveryHandAllDrawPolicy
    try:
        captured, runtime, rules, situation, hands, _ = g95.run_full(
            plan, contract, versions, source["mix"])
    finally:
        g95.CaptureWiderPolicy = original
    record = captured.records.get(target["round_no"])
    if record is None:
        raise ValueError("G128 重跑未命中目标单局")
    if g126.scored_target(record, scorer) != target:
        raise ValueError("G128 重跑行动前观察、动作或评分漂移")
    if (item["observation_sha256"] != target["observation_sha256"]
            or item["parent_action"] != record.parent_key
            or item["alternate_action"] != record.alternate_key):
        raise ValueError("G128 选样身份与目标窗不符")
    window = record.request.window_key
    reference = runtime["engine"].frame(record.world).decisions[0].observation
    worlds = [("historical", record.world)]
    for sample_key in g95.SAMPLES:
        sampled = runtime["engine"].resample_public_consistent_hidden_world(
            record.world, focal_seat=window.seat, sample_key=sample_key)
        if runtime["engine"].frame(sampled).decisions[0].observation != reference:
            raise ValueError("G128 重采样改变焦点依法可见观察")
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
            raise ValueError("G128 两臂起点积分不一致")
        if sample_key == "historical":
            old = hands[window.round_no - 1]
            for field in ("round_no", "scores_before", "scores_after", "score_delta",
                          "winner_seat", "is_draw", "fan", "details"):
                if p[field] != old[field]:
                    raise ValueError("G128 历史父代单局恒等失败：" + field)
        pairs.append({
            "sample_key": sample_key, "parent": parent, "alternate": alternate,
            "focal_delta_alt_minus_parent":
                a["score_delta"][window.seat] - p["score_delta"][window.seat],
            "parent_class": g95.classify(p, window.seat),
            "alternate_class": g95.classify(a, window.seat),
            "route_entry": {
                arm: {
                    "ordinary": g118.value_entry(branch, "one_draw_win_routes"),
                    "highfan": g118.value_entry(branch, "one_draw_highfan_routes"),
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
    """窗口等权、按池和当前实持白板分层；不把世界作独立桌。"""
    groups = {}
    for mix in ("H", "M"):
        for white in ("0", "1"):
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
    return {"schema": "g128-no-claim-two-shanten-branch-summary/1",
            "split": split, "status": "complete" if len(rows) == planned else "in_progress",
            "windows_completed": len(rows), "windows_planned": planned,
            "groups": groups,
            "boundary": "开发或锁定单局续打；不是完整桌发布门。"}


def main() -> None:
    """仅执行显式指定根组，逐窗 fsync 并精确前缀续跑。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--split", choices=("development", "locked_evaluation"), required=True)
    parser.add_argument("--max-new", type=int, default=0)
    args = parser.parse_args()
    items = selected(args.split)
    expected = manifest(args.split, len(items))
    index = target_index()
    contract = json.loads(g95.g93.paired.CONTRACT.read_text(encoding="utf-8"))
    versions = g95.g93.natural.stage.contract_versions_block(contract)
    scorer = g126.g87.c31.load_parent()
    plans = {(mix, root, seat): plan for mix, root, seat, plan in g126.plans(contract)}
    out = BASE / args.split
    out.mkdir(parents=True, exist_ok=True)
    manifest_path = out / "manifest.json"
    if manifest_path.exists():
        if json.loads(manifest_path.read_text(encoding="utf-8")) != expected:
            raise ValueError("G128 根组批次清单变化，拒绝混写")
    else:
        manifest_path.write_text(json.dumps(expected, ensure_ascii=False,
                                            sort_keys=True, indent=2) + "\n", encoding="utf-8")
    rows_path = out / "rows.jsonl"
    rows = ([json.loads(line) for line in rows_path.read_text(encoding="utf-8").splitlines()]
            if rows_path.exists() else [])
    if len(rows) > len(items):
        raise ValueError("G128 已有窗口超过事前选样")
    for old, item in zip(rows, items):
        if ([old["mix"], old["root_index"], old["focal_seat"], old["round_no"]]
                != item["window"]
                or old["observation_sha256"] != item["observation_sha256"]):
            raise ValueError("G128 已有行非冻结选样前缀")
    added = 0
    with rows_path.open("a", encoding="utf-8") as stream:
        for item in items[len(rows):]:
            key = tuple(item["window"])
            source, target = index[key]
            row = one_window(item, source, target, plans[key[:3]],
                             contract, versions, scorer)
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
