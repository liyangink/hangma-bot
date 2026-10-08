#!/usr/bin/env python3
"""只读比较 G275 锁定窗口在历史 C31 与修正动作链后的行动前事实。

只用每个触发弃牌及之前的官方事件生成观察；官方未来行为仅保留既定正负例标签，
不能当成当时决策特征。输出需指定新路径，不覆盖既有证据或读取 Token。
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
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_project_file(_PROJECT_ROOT, HERE.parents[0] / "baotou-anatomy-20260925")))

import anatomy_lib as anatomy
import c31_action_layer_gap as current
import c32_cards as c32
import g275_visible_response_pair_preflight as g275
from extract_room_scores import load_rooms


def sha(path: Path) -> str:
    """固定参与行动前复算的研究源码原始字节。"""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def top(window: dict) -> str:
    """按冻结父代分数和生产破同分口径读取首选动作键。"""
    return c32.scored_plan(window["view"], window["scores"])[0]


def main() -> None:
    """审计旧标签是否可继续用于 G273 路线门；不生成线上候选。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError("拒绝覆盖已有结果：" + str(args.output))
    selected = g275.source_targets("full")
    frozen = g275.load_frozen_c31()
    frozen_parent = frozen.load_parent()
    current_parent = current.load_parent()
    scorer, _ = c32.load_scorer(c32.R6_FILE)
    if scorer is None:
        raise ValueError("冻结 +6 评分器无法装配")
    by_round = defaultdict(list)
    for row in selected:
        by_round[(row["game_id"], row["round_no"])].append(row)
    wanted = {row["game_id"] for row in selected}
    found = set()
    rows = []
    for _, room, _, game_id, doc in load_rooms():
        if game_id not in wanted:
            continue
        metadata = frozen.round_metadata(doc)
        table_scores = [0, 0, 0, 0]
        for round_no, events, start_hands in anatomy.round_blocks(doc):
            for row in by_round.get((game_id, round_no), ()):
                if room != row["room"] or start_hands is None:
                    raise ValueError("冻结窗口房或起手记录漂移")
                hit = [i for i, event in enumerate(events)
                       if event.get("seq") == row["discard_seq"]]
                if len(hit) != 1 or events[hit[0]].get("type") != "tile_discarded":
                    raise ValueError("冻结触发弃牌非唯一")
                prefix = events[:hit[0] + 1]
                dealer = metadata[round_no]["dealer"]
                old_snap = frozen.reconstruct(
                    prefix, start_hands, table_scores, dealer)[row["discard_seq"]]
                new_snap = current.reconstruct(
                    prefix, start_hands, table_scores, dealer)[row["discard_seq"]]
                old, _, _ = frozen.evaluate_window(
                    old_snap, row["seat"], [row["phase"]], game_id,
                    round_no, frozen_parent)
                new, _, _ = current.evaluate_window(
                    new_snap, row["seat"], [row["phase"]], game_id,
                    round_no, current_parent)
                if old is None or new is None or old["degraded"] or new["degraded"]:
                    raise ValueError("冻结窗口缺失或规则分析降级")
                old_top, new_top = top(old), top(new)
                if old_top != row["parent_key"] or old["margin"] != row["parent_margin"]:
                    raise ValueError("历史 G76 父代标签未复现")
                r6_old = scorer(old["view"])
                r6_new = scorer(new["view"])
                if r6_old.get("status") != r6_new.get("status") or r6_old.get("status") != "SCORED":
                    raise ValueError("+6 评分器弃权或状态漂移")
                r6_old_scores = {item["action_key"]: item["score"] for item in r6_old["entries"]}
                r6_new_scores = {item["action_key"]: item["score"] for item in r6_new["entries"]}
                r6_old_top = c32.scored_plan(old["view"], r6_old_scores)[0]
                r6_new_top = c32.scored_plan(new["view"], r6_new_scores)[0]
                if r6_old_top != row["r6_key"]:
                    raise ValueError("历史 G76 +6 标签未复现")
                old_ob, new_ob = old["observation"], new["observation"]
                entry = {
                    "window_key": {name: row[name] for name in g275.ROW_KEY},
                    "cohort": ("positive" if row["actual"] == "claim" else "explicit_pass"),
                    "accepted_key": row.get("accepted_key"),
                    "old_chain_count": old_ob.rule_state.chain_count,
                    "new_chain_count": new_ob.rule_state.chain_count,
                    "old_chain_piao": old_ob.chain_piao,
                    "new_chain_piao": new_ob.chain_piao,
                    "observation_changed": old_ob != new_ob,
                    "analysis_changed": old["analysis"] != new["analysis"],
                    "view_changed": old["view"] != new["view"],
                    "scores_changed": old["scores"] != new["scores"],
                    "old_parent_top": old_top,
                    "new_parent_top": new_top,
                    "old_r6_top": r6_old_top,
                    "new_r6_top": r6_new_top,
                    "old_margin": old["margin"],
                    "new_margin": new["margin"],
                    "old_scores": old["scores"],
                    "new_scores": new["scores"],
                }
                rows.append(entry)
                found.add(g275.window_key(row))
            ended = next((event for event in events if event.get("type") == "round_ended"), None)
            if ended is None:
                raise ValueError("官方单局缺结算")
            delta = (ended.get("data") or {}).get("scores")
            if not isinstance(delta, list) or len(delta) != 4 or sum(delta) != 0:
                raise ValueError("既往桌分非四座守恒")
            table_scores = [left + right for left, right in zip(table_scores, delta)]
    if found != {g275.window_key(row) for row in selected} or len(rows) != 458:
        raise ValueError("冻结 458 窗不全")
    rows.sort(key=lambda item: tuple(item["window_key"][name] for name in g275.ROW_KEY))
    summary = Counter()
    for row in rows:
        summary["windows"] += 1
        cohort = row["cohort"]
        summary[cohort] += 1
        for field in ("observation_changed", "analysis_changed", "view_changed",
                      "scores_changed"):
            if row[field]:
                summary[cohort + "_" + field] += 1
        if row["old_chain_count"] != row["new_chain_count"]:
            summary[cohort + "_chain_count_changed"] += 1
        if row["old_chain_piao"] != row["new_chain_piao"]:
            summary[cohort + "_chain_piao_changed"] += 1
        if row["old_parent_top"] != row["new_parent_top"]:
            summary[cohort + "_parent_top_changed"] += 1
        if row["old_r6_top"] != row["new_r6_top"]:
            summary[cohort + "_r6_top_changed"] += 1
    result = {
        "summary": dict(sorted(summary.items())),
        "source_sha256": {
            "g76_rows": g275.SOURCE_SHA256,
            "frozen_c31": g275.FROZEN_C31_SHA256,
            "corrected_c31": sha(_project_file(_PROJECT_ROOT, HERE / "c31_action_layer_gap.py")),
            "audit_script": sha(Path(__file__)),
        },
        "rows": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True,
                                      indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result["summary"], ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
