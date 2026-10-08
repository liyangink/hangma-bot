#!/usr/bin/env python3
"""G113：事后复算 G109/G112 听牌窗的父代评分与可见情境混杂。"""

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

from collections import Counter
import hashlib
import json
from pathlib import Path

import g87_post_claim_score_trace as g87
import g95_wider_discard_same_hand_preflight as g95
import g108_fresh_hm_route_exposure as g108
import g109_fresh_hm_high_route_paired_branch as g109
import g112_strict_tenpai_matched_control as g112


HERE = Path(__file__).resolve().parent
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g113-posthoc-visible-score-audit-20260928/result.json')
SOURCES = {
    "high_difference": g109.OUT / "rows.jsonl",
    "strict_control": g112.OUT / "rows.jsonl",
}


def sha(path: Path) -> str:
    """记录来源与本程序的字节摘要。"""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    """只读可见状态重建评分，不用事后结算定义行动前特征。"""
    if OUT.exists():
        raise FileExistsError("G113 事后评分审计已存在，拒绝覆盖")
    contract = json.loads(g95.g93.paired.CONTRACT.read_text(encoding="utf-8"))
    versions = g95.g93.natural.stage.contract_versions_block(contract)
    scorer = g87.c31.load_parent()
    source_rows = {name: [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
                   for name, path in SOURCES.items()}
    frozen_rows = [json.loads(line) for line in (g108.OUT / "rows.jsonl").read_text(
        encoding="utf-8").splitlines()]
    frozen = {(row["mix"], row["root_index"], row["focal_seat"], target["round_no"]): target
              for row in frozen_rows for target in row["target_windows"]}
    result_rows = []
    for group, entries in source_rows.items():
        for old in entries:
            mix, root, seat, round_no = (old["mix"], old["root_index"],
                                         old["focal_seat"], old["round_no"])
            plan = g95.g93.natural.build_seat_stage_plans(
                contract=contract, opponent=mix, root_index=root,
                focal_seat=seat, panel_seed=g108.PANEL_SEED)[0]
            original = g95.CaptureWiderPolicy
            g95.CaptureWiderPolicy = g108.CaptureEveryHandPolicy
            try:
                captured, _, _, _, _, _ = g95.run_full(plan, contract, versions, mix)
            finally:
                g95.CaptureWiderPolicy = original
            record = captured.records.get(round_no)
            if record is None:
                raise ValueError("G113 重跑目标单局缺失")
            target = frozen[(mix, root, seat, round_no)]
            if g109.canonical(g108.target_row(record)) != g109.canonical(target):
                raise ValueError("G113 可见观察或目标窗身份漂移")
            request = record.request
            view = g87.g05.build_scoring_view(
                request, value_limits=g87.c31.VALUE_LIMITS).candidate_view()
            scored = scorer(view)
            if scored["status"] != "SCORED":
                raise ValueError("G113 父代评分失败")
            scores = {entry["action_key"]: float(entry["score"])
                      for entry in scored["entries"]}
            if g87.argmax(scores) != record.parent_key:
                raise ValueError("G113 父代评分排序与原动作不符")
            entries_by_key = {entry["action_key"]: entry for entry in scored["entries"]}
            gap = scores[record.parent_key] - scores[record.alternate_key]
            components = {name: g87.component(entries_by_key[record.parent_key]["trace"], name)
                          - g87.component(entries_by_key[record.alternate_key]["trace"], name)
                          for name in g87.COMPONENTS}
            if abs(sum(components.values()) - gap) > 1e-8:
                raise ValueError("G113 评分分量与差值不守恒")
            observation = request.observation
            result_rows.append({
                "group": group, "mix": mix, "root_index": root,
                "focal_seat": seat, "round_no": round_no,
                "observation_sha256": target["observation_sha256"],
                "white_before": target["white_before"],
                "standard_shanten_after": record.facts[record.parent_key]["standard_shanten_after"],
                "parent_score_gap": gap,
                "component_parent_minus_alternate": components,
                "ordinary_codes_delta": record.facts[record.alternate_key]["ordinary_codes"]
                - record.facts[record.parent_key]["ordinary_codes"],
                "public_unseen_capacity_delta":
                record.facts[record.alternate_key]["public_unseen_capacity"]
                - record.facts[record.parent_key]["public_unseen_capacity"],
                "remaining_tile_count": observation.remaining_tile_count,
                "own_chi_peng_count": sum(meld.kind in ("chi", "peng")
                                         for meld in observation.melds[seat]),
                "opponent_meld_count": sum(len(observation.melds[index])
                                           for index in range(4) if index != seat),
            })
    if len(result_rows) != 20 or Counter(row["group"] for row in result_rows) != {
        "high_difference": 10, "strict_control": 10,
    }:
        raise ValueError("G113 两组窗口数量不守恒")
    result = {
        "schema": "g113-posthoc-visible-score-audit/1",
        "exploratory": True,
        "source_sha256": {"script": sha(Path(__file__)),
                          "g108_rows": sha(g108.OUT / "rows.jsonl"),
                          **{name: sha(path) for name, path in SOURCES.items()}},
        "rows": result_rows,
        "boundary": "已看续打结果后做的可见混杂审计，不用于拟合阈值或独立确认。",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                   encoding="utf-8")
    print(json.dumps({"rows": len(result_rows), "groups": dict(Counter(
        row["group"] for row in result_rows))}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
