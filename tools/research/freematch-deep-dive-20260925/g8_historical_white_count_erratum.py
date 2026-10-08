#!/usr/bin/env python3
"""只读纠正 P24/P85 历史结果盲数据的财神张数标签，不修改冻结效果。"""

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
import json
from pathlib import Path

import g8_two_white_next_draw_census as census


HERE = Path(__file__).resolve().parent
ROOT = _PROJECT_ROOT
EV = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g8-two-white-next-draw-20260927/historical_white_count_erratum.json')


def _audit(label: str, dataset: Path, teacher: Path | None = None) -> dict:
    rows = json.loads(dataset.read_text(encoding="utf-8"))["rows"]
    effect = {}
    if teacher is not None:
        states = json.loads(teacher.read_text(encoding="utf-8"))["states"]
        effect = {int(row["target_id"].rsplit("-", 1)[1]): row for row in states}
        if len(effect) != len(rows):
            raise ValueError("历史教师与暴露状态未一一对应")
    recorded = Counter()
    corrected = Counter()
    changes = []
    two_white = []
    for index, row in enumerate(rows, 1):
        old = row["features"]["wealth_count_in_hand"]
        hand, _ = census._complete_hand(row["request"]["observation"])
        new = hand.count("白")
        recorded[old] += 1
        corrected[new] += 1
        if old != new:
            changes.append({"row": index, "recorded": old, "corrected": new,
                            "drawn_tile": row["request"]["observation"].get("drawn_tile")})
        if new == 2 and effect:
            facts = census._static_witnesses(row["request"])
            first = row["intervention_action"][8:]
            draws = {item["draw"] for item in facts["witnesses"] if item["first"] == first}
            state = effect[index]
            two_white.append({"row": index, "mix": row["source"]["mix"],
                              "intervention_action": row["intervention_action"],
                              "intervention_has_next_draw_static_route": bool(draws),
                              "public_support_upper_for_intervention": sum(
                                  facts["public_support_by_draw"][code] for code in draws),
                              "recheck_table_delta": state[
                                  "recheck_mean_blind_deferral_minus_immediate_hu_current_table"],
                              "recheck_round_delta": state[
                                  "recheck_mean_blind_deferral_minus_immediate_hu_current_round"],
                              "recheck_opponent_hu": state[
                                  "recheck_terminal_counts_intervention"].get("opponent_hu", 0)})
    return {"label": label, "rows": len(rows), "recorded_white_counts": dict(recorded),
            "corrected_white_counts": dict(corrected), "changed_labels": changes,
            "corrected_two_white_p24_effect_rows": two_white}


def main() -> None:
    """以原始请求重算描述标签，保留原教师分数与来源身份。"""

    result = {"schema": "g8-historical-white-count-erratum/1",
              "p24": _audit(
                  "P24", _project_file(_PROJECT_ROOT, EV / "r18-p24-deferral-complement-01-20260925/exposure/dataset.json"),
                  _project_file(_PROJECT_ROOT, EV / "r18-p24-deferral-complement-01-20260925/teacher/result.json")),
              "p85": _audit(
                  "P85", _project_file(_PROJECT_ROOT, EV / "r18-p85-hu-deferral-natural-exposure-01-20260925/dataset.json")),
              "interpretation": "历史谓词和教师动作未使用 wealth_count_in_hand；纠正的是描述标签与后验分层，原配对收益及停线判据不改"}
    OUT.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                   encoding="utf-8")
    print(json.dumps({label: {key: value for key, value in result[label].items()
                              if key not in ("changed_labels", "corrected_two_white_p24_effect_rows")}
                      for label in ("p24", "p85")}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
