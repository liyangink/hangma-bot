#!/usr/bin/env python3
"""G91：事后把 G90 已对账特殊胡收入按全部结算明细拆开。"""

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

import g14_accounted_paired_panel as g14


HERE = Path(__file__).resolve().parent
RUN = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g90-g89-hand-accounting-20260928')
CHECK = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g90-g89-hand-accounting-20260928/verification.json')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g91-g90-special-win-breakdown-20260928/result.json')
ARM = "candidate@review/freematch-deep-dive-20260925/candidates/G88-POST-CLAIM-FAMILIAR-BIAS-V1.py"


def sha(path: Path) -> str:
    """记录本次明细所依赖的冻结文件摘要。"""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    """列出全部实际番型，不按事后显著程度挑选子集。"""
    if OUT.exists():
        raise FileExistsError("G91 已存在，拒绝覆盖")
    check = json.loads(CHECK.read_text(encoding="utf-8"))
    if not check["same_stage_table_score_execution"] or check["complete_tables"] != 768:
        raise ValueError("G90 尚未完整对账")
    aggregate: dict[tuple[str, str, str], Counter] = defaultdict(Counter)
    root_amount: dict[tuple[str, int, str, str], int] = defaultdict(int)
    root_count: dict[tuple[str, int, str, str], int] = defaultdict(int)
    category_metadata: dict[str, dict] = {}
    total_special: dict[tuple[str, str], int] = defaultdict(int)
    table_count = Counter()
    for mix in ("H", "M"):
        for root in range(1, 25):
            for seat in range(4):
                for arm in ("r18_v2", ARM):
                    unit = (mix, root, seat, arm, 2026110801)
                    row = json.loads(g14.paired.unit_path(RUN, unit).read_text(encoding="utf-8"))
                    g14.verify_unit(row, unit=unit, tables_per_stage=2)
                    for table in row["stage"]["tables"]:
                        table_count[(mix, arm)] += 1
                        account = table["hand_account"]
                        own_seat = account["focal_seat"]
                        seen_amount = 0
                        seen_count = 0
                        for hand in table["hand_records"]:
                            if hand["winner_seat"] != own_seat or hand["details"] == ["平胡"]:
                                continue
                            details = hand["details"]
                            fan = hand["fan"]
                            if not isinstance(details, list) or not details or type(fan) is not int:
                                raise ValueError("特殊胡明细缺失")
                            name = "+".join(details) + f"/{fan}番"
                            meta = {"details": details, "fan": fan}
                            if name in category_metadata and category_metadata[name] != meta:
                                raise ValueError("同名番型明细身份不一致")
                            category_metadata[name] = meta
                            amount = hand["score_delta"][own_seat]
                            if type(amount) is not int or amount <= 0:
                                raise ValueError("本人特殊胡收入非法")
                            aggregate[(mix, arm, name)]["wins"] += 1
                            aggregate[(mix, arm, name)]["income"] += amount
                            root_amount[(mix, root, arm, name)] += amount
                            root_count[(mix, root, arm, name)] += 1
                            seen_amount += amount
                            seen_count += 1
                        if (seen_amount != account["special_self_win_delta"] or
                                seen_count != account["special_self_wins"]):
                            raise ValueError("番型逐局合计与 G90 已核收益不符")
                        total_special[(mix, arm)] += seen_amount
    if any(table_count[(mix, arm)] != 192 for mix in ("H", "M")
           for arm in ("r18_v2", ARM)):
        raise ValueError("G91 每池每臂完整桌数不足")
    seven_pair_pairing = {mix: Counter() for mix in ("H", "M")}
    for mix in ("H", "M"):
        for root in range(1, 25):
            for seat in range(4):
                old_unit = (mix, root, seat, "r18_v2", 2026110801)
                new_unit = (mix, root, seat, ARM, 2026110801)
                old = json.loads(g14.paired.unit_path(RUN, old_unit).read_text(encoding="utf-8"))
                new = json.loads(g14.paired.unit_path(RUN, new_unit).read_text(encoding="utf-8"))
                for old_table, new_table in zip(old["stage"]["tables"], new["stage"]["tables"]):
                    if old_table["seed"] != new_table["seed"]:
                        raise ValueError("G91 成对牌山种子不一致")
                    prior_round_outcome_differs = False
                    focal = old_table["hand_account"]["focal_seat"]
                    if focal != new_table["hand_account"]["focal_seat"]:
                        raise ValueError("G91 焦点座位不一致")
                    for before, after in zip(old_table["hand_records"], new_table["hand_records"]):
                        old_seven = (before["winner_seat"] == focal and
                                     "七对" in before["details"][0])
                        new_seven = (after["winner_seat"] == focal and
                                     "七对" in after["details"][0])
                        relevant_difference = any(before[name] != after[name]
                                                  for name in ("winner_seat", "details", "fan", "score_delta"))
                        if (old_seven or new_seven) and relevant_difference:
                            seven_pair_pairing[mix][
                                "after_prior_round_difference" if prior_round_outcome_differs
                                else "at_first_different_round"] += 1
                        if any(before[name] != after[name]
                               for name in ("winner_seat", "is_draw", "fan", "details", "scores_after")):
                            prior_round_outcome_differs = True
    categories = sorted(category_metadata)
    summary = {}
    for mix in ("H", "M"):
        rows = []
        for name in categories:
            parent = aggregate[(mix, "r18_v2", name)]
            candidate = aggregate[(mix, ARM, name)]
            root_deltas = [
                (root_amount[(mix, root, ARM, name)] -
                 root_amount[(mix, root, "r18_v2", name)]) / 8
                for root in range(1, 25)
            ]
            rows.append({"category": name, **category_metadata[name],
                         "parent_wins": parent["wins"], "candidate_wins": candidate["wins"],
                         "parent_income": parent["income"],
                         "candidate_income": candidate["income"],
                         "delta_wins_per_table": (candidate["wins"] - parent["wins"]) / 192,
                         "delta_income_per_table": (candidate["income"] - parent["income"]) / 192,
                         "positive_zero_negative_roots": {
                             "positive": sum(value > 0 for value in root_deltas),
                             "zero": sum(value == 0 for value in root_deltas),
                             "negative": sum(value < 0 for value in root_deltas),
                         }})
        expected = check["mean_delta_per_complete_table"][mix]["special_self_win_delta"]
        actual = sum(row["delta_income_per_table"] for row in rows)
        if abs(actual - expected) > 1e-9:
            raise ValueError("G91 全番型收入差与 G90 不一致")
        summary[mix] = {"categories": rows, "sum_delta_income_per_table": actual,
                        "expected_g90_delta_income_per_table": expected,
                        "parent_special_income": total_special[(mix, "r18_v2")],
                        "candidate_special_income": total_special[(mix, ARM)]}
    result = {"schema": "g91-g90-special-win-breakdown/1", "exploratory": True,
              "input_sha256": {"g90_verification": sha(CHECK),
                               "g90_manifest": sha(_project_file(_PROJECT_ROOT, RUN / "manifest.json")),
                               "script": sha(Path(__file__))},
              "complete_tables": 768, "all_observed_categories": categories,
              "summary": summary,
              "paired_seven_pair_outcome_differences": {
                  mix: dict(seven_pair_pairing[mix]) for mix in ("H", "M")},
              "boundary": "全部番型事后拆账仅解释 G89 旧开发根；不能给 G88 新准入或为同根调阈值。"}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                   encoding="utf-8")
    print(json.dumps({mix: [(row["category"], row["delta_income_per_table"])
                           for row in summary[mix]["categories"]]
                      for mix in ("H", "M")}, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
