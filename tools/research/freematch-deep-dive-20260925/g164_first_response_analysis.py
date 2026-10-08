#!/usr/bin/env python3
"""G164：按开发窗口等权拆即时响应相同/不同的配对结算贡献。"""

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

from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
from statistics import mean

import g161_multi_action_development_analysis as accounted


HERE = Path(__file__).resolve().parent
BASE = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g164-first-response-score-conflict-20260928')
SOURCE = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g161-multi-action-development-teacher-20260928')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g164-first-response-score-conflict-20260928/analysis.json')
PARTS = ("plain_self_win", "special_self_win", "other_win_payment", "draw_delta")


def sha(path: Path) -> str:
    """输入按原始字节绑定，拒绝混用部分复跑结果。"""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load() -> list[dict]:
    """逐窗逐世界核身份、结算和配对积分恒等。"""
    manifest = json.loads((_project_file(_PROJECT_ROOT, BASE / "manifest.json")).read_text(encoding="utf-8"))
    if manifest["schema"] != "g164-first-response-score-conflict-manifest/1":
        raise ValueError("G164 清单 schema 漂移")
    rows = [json.loads(line) for line in (_project_file(_PROJECT_ROOT, BASE / "rows.jsonl")).read_text(
        encoding="utf-8").splitlines()]
    old = [json.loads(line) for line in (_project_file(_PROJECT_ROOT, SOURCE / "rows.jsonl")).read_text(
        encoding="utf-8").splitlines()]
    if len(rows) != len(old) or len(rows) != 49:
        raise ValueError("G164 只分析全部 49 个开发窗口")
    if manifest["input_sha256"]["g161_rows"] != sha(_project_file(_PROJECT_ROOT, SOURCE / "rows.jsonl")):
        raise ValueError("G164 与 G161 来源摘要不符")
    paired = []
    for row, prior in zip(rows, old):
        for name in ("mix", "root_index", "focal_seat", "round_no",
                     "white_before", "observation_sha256", "parent_action",
                     "alternate_action", "score_facts"):
            if row[name] != prior[name]:
                raise ValueError("G164 与 G161 窗口身份或评分漂移")
        if len(row["world_pairs"]) != len(prior["world_pairs"]) or len(
                row["world_pairs"]) != 33:
            raise ValueError("G164 世界数不足")
        pairs = []
        for response_pair, outcome_pair in zip(row["world_pairs"],
                                               prior["world_pairs"]):
            for name in ("sample_key", "focal_delta_alt_minus_parent",
                         "parent_class", "alternate_class"):
                if response_pair[name] != outcome_pair[name]:
                    raise ValueError("G164 与 G161 同世界结算漂移")
            seat = row["focal_seat"]
            p = accounted._parts(outcome_pair["parent"], seat)
            a = accounted._parts(outcome_pair["alternate"], seat)
            changes = {name: a[name] - p[name] for name in PARTS}
            if abs(sum(changes.values()) - response_pair[
                    "focal_delta_alt_minus_parent"]) > 1e-9:
                raise ValueError("G164 本座积分拆账不守恒")
            pairs.append({"same": response_pair["same_response"],
                          "parent_kind": response_pair["parent_response"]["kind"],
                          "alternate_kind": response_pair["alternate_response"]["kind"],
                          "delta": response_pair["focal_delta_alt_minus_parent"],
                          "components": changes})
        paired.append({"mix": row["mix"], "white_before": row["white_before"],
                       "root_index": row["root_index"], "pairs": pairs,
                       "score_facts": row["score_facts"]})
    return paired


def summarize(rows: list[dict]) -> dict:
    """保留相关世界、窗口与根三个分母，贡献按 33 世界/窗等权。"""
    totals = Counter()
    transitions = Counter()
    by_root = defaultdict(list)
    contributions = defaultdict(list)
    parts = {key: defaultdict(list) for key in PARTS}
    for row in rows:
        pairs = row["pairs"]
        for pair in pairs:
            bucket = "same" if pair["same"] else "changed"
            totals[bucket] += 1
            transitions[(pair["parent_kind"], pair["alternate_kind"])] += 1
        for bucket in ("same", "changed"):
            selected = [pair for pair in pairs if pair["same"] == (bucket == "same")]
            contribution = sum(pair["delta"] for pair in selected) / len(pairs)
            contributions[bucket].append(contribution)
            by_root[row["root_index"]].append((bucket, contribution))
            for name in PARTS:
                parts[name][bucket].append(sum(
                    pair["components"][name] for pair in selected) / len(pairs))
    summary = {
        "windows": len(rows),
        "roots": len(by_root),
        "related_world_pairs": sum(totals.values()),
        "response_same_pairs": totals["same"],
        "response_changed_pairs": totals["changed"],
        "window_equal_score_contribution": {
            bucket: mean(contributions[bucket]) if rows else None
            for bucket in ("same", "changed")},
        "window_equal_component_contribution": {
            name: {bucket: mean(parts[name][bucket]) if rows else None
                   for bucket in ("same", "changed")}
            for name in PARTS},
        "root_equal_score_contribution": {
            bucket: mean(
                mean(value for name, value in items if name == bucket)
                for _, items in sorted(by_root.items())) if rows else None
            for bucket in ("same", "changed")},
        "response_kind_transitions": {
            parent + " -> " + alternate: count
            for (parent, alternate), count in sorted(transitions.items())},
    }
    for bucket in ("same", "changed"):
        parts_sum = sum(summary["window_equal_component_contribution"][name][bucket]
                        for name in PARTS)
        if abs(parts_sum - summary["window_equal_score_contribution"][bucket]) > 1e-9:
            raise ValueError("G164 窗口等权积分分量不守恒")
    return summary


def main() -> None:
    """完整开发层才生成机读报告；不作显著性或候选选择。"""
    if OUT.exists():
        raise FileExistsError("G164 分析已有结果，不覆盖")
    rows = load()
    groups = {mix: summarize([r for r in rows if r["mix"] == mix])
              for mix in ("H", "M")}
    for mix in ("H", "M"):
        for white in (0, 1):
            groups[f"{mix}/{white}"] = summarize([
                r for r in rows if r["mix"] == mix and r["white_before"] == white])
    payload = {
        "schema": "g164-first-response-score-conflict-analysis/1",
        "source_sha256": {
            "manifest": sha(_project_file(_PROJECT_ROOT, BASE / "manifest.json")),
            "rows": sha(_project_file(_PROJECT_ROOT, BASE / "rows.jsonl")),
            "g161_rows": sha(_project_file(_PROJECT_ROOT, SOURCE / "rows.jsonl")),
            "script": sha(Path(__file__)),
        },
        "groups": groups,
        "boundary": "G161 收益已看后的相关世界机制诊断；不是独立家族能力或完整桌收益。",
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False,
                              sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: {k: groups[key][k] for k in (
        "windows", "roots", "response_same_pairs", "response_changed_pairs",
        "window_equal_score_contribution",
        "window_equal_component_contribution")} for key in ("H", "M", "M/1")},
        ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
