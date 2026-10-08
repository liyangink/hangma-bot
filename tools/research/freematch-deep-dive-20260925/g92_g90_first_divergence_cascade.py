#!/usr/bin/env python3
"""G92：事后区分成对桌首次不同单局与之后单局的积分传导。"""

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

import g14_accounted_paired_panel as g14


HERE = Path(__file__).resolve().parent
RUN = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g90-g89-hand-accounting-20260928')
CHECK = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g90-g89-hand-accounting-20260928/verification.json')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g92-g90-first-divergence-cascade-20260928/result.json')
ARM = "candidate@review/freematch-deep-dive-20260925/candidates/G88-POST-CLAIM-FAMILIAR-BIAS-V1.py"
OUTCOME_FIELDS = ("winner_seat", "is_draw", "fan", "details", "scores_after")


def sha(path: Path) -> str:
    """固定 G90 来源与本次事后对账实现。"""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    """所有旧根逐桌配对，验证首次及以后积分差合计复现 G89。"""
    if OUT.exists():
        raise FileExistsError("G92 证据已存在，拒绝覆盖")
    verified = json.loads(CHECK.read_text(encoding="utf-8"))
    if not verified["same_stage_table_score_execution"] or verified["complete_hands"] != 6144:
        raise ValueError("G90 完整单局恒等对账尚未通过")
    summaries = {}
    rows = []
    for mix in ("H", "M"):
        c = Counter()
        for root in range(1, 25):
            for seat in range(4):
                old_unit = (mix, root, seat, "r18_v2", 2026110801)
                new_unit = (mix, root, seat, ARM, 2026110801)
                old = json.loads(g14.paired.unit_path(RUN, old_unit).read_text(encoding="utf-8"))
                new = json.loads(g14.paired.unit_path(RUN, new_unit).read_text(encoding="utf-8"))
                g14.verify_unit(old, unit=old_unit, tables_per_stage=2)
                g14.verify_unit(new, unit=new_unit, tables_per_stage=2)
                for before, after in zip(old["stage"]["tables"], new["stage"]["tables"]):
                    if before["seed"] != after["seed"]:
                        raise ValueError("G92 两臂牌山种子不同")
                    focal = before["hand_account"]["focal_seat"]
                    if focal != after["hand_account"]["focal_seat"]:
                        raise ValueError("G92 两臂焦点座位不同")
                    first = None
                    prior_delta = 0
                    first_delta = 0
                    later_delta = 0
                    old_hands = before["hand_records"]
                    new_hands = after["hand_records"]
                    if len(old_hands) != 8 or len(new_hands) != 8:
                        raise ValueError("G92 成对桌单局数不足")
                    for a, b in zip(old_hands, new_hands):
                        if a["round_no"] != b["round_no"]:
                            raise ValueError("G92 单局序号不一致")
                        if first is None and any(a[name] != b[name] for name in OUTCOME_FIELDS):
                            first = a["round_no"]
                        delta = b["score_delta"][focal] - a["score_delta"][focal]
                        if first is None:
                            prior_delta += delta
                        elif a["round_no"] == first:
                            first_delta += delta
                        else:
                            later_delta += delta
                    total = (after["scores_by_seat"][focal] -
                             before["scores_by_seat"][focal])
                    if prior_delta != 0 or prior_delta + first_delta + later_delta != total:
                        raise ValueError("G92 首次差异前非零或时序积分不守恒")
                    c["tables"] += 1
                    c["diverged_tables"] += first is not None
                    c["first_round_delta"] += first_delta
                    c["later_round_delta"] += later_delta
                    c["total_delta"] += total
                    if first is not None:
                        c["first_difference_at_round_" + str(first)] += 1
                    rows.append({"mix": mix, "root_index": root, "focal_seat": seat,
                                 "table_id": before["table_id"], "seed": before["seed"],
                                 "first_different_round": first,
                                 "first_round_delta": first_delta,
                                 "later_round_delta": later_delta, "total_delta": total})
        if c["tables"] != 192:
            raise ValueError("G92 每池配对桌数不足")
        expected = verified["mean_delta_per_complete_table"][mix]["net"]
        if abs(c["total_delta"] / c["tables"] - expected) > 1e-9:
            raise ValueError("G92 净分不等于 G90/G89")
        summaries[mix] = {"counts_and_totals": dict(sorted(c.items())),
                          "mean_delta_per_complete_table": {
                              "first_different_round": c["first_round_delta"] / c["tables"],
                              "later_rounds": c["later_round_delta"] / c["tables"],
                              "net": c["total_delta"] / c["tables"]}}
    result = {"schema": "g92-g90-first-divergence-cascade/1", "exploratory": True,
              "input_sha256": {"g90_verification": sha(CHECK),
                               "g90_manifest": sha(_project_file(_PROJECT_ROOT, RUN / "manifest.json")),
                               "script": sha(Path(__file__))},
              "summary": summaries, "rows": rows,
              "boundary": "首次差异按赛后单局结果定义，不是首次策略动作差；之后局的差是桌赛因果链一部分，不能归因于某个番型或即时弃牌。"}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                   encoding="utf-8")
    print(json.dumps(summaries, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
