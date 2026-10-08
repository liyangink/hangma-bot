#!/usr/bin/env python3
"""G200：把已见大牌榜弃牌分歧对到冻结 R18 v2 的评分分量。"""

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
from hashlib import sha256
import json
from pathlib import Path

import c31_action_layer_gap as c31
import g184_classic_highhand_shadow as classic
from hangma_bot.policy.action_value_policy import build_scoring_view
from hangma_bot.policy.action_value_seeds import ActionValueScorer
from hangma_bot.policy.r18_integrated_positive_v2 import (
    R18_INTEGRATED_POSITIVE_V2_SOURCE,
    R18_INTEGRATED_POSITIVE_V2_SHA256,
)


HERE = Path(__file__).resolve().parent
SOURCE = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g191-highhand-discard-breadth-20260929/result.json')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g200-highhand-score-conflict-20260929/result.json')
COMPONENTS = ("base_score", "wealth_part", "wealth_discard_part",
              "river_part", "style_part")


def digest(path: Path) -> str:
    """绑定已看压力题、复盘原文与评分器源码。"""

    return sha256(path.read_bytes()).hexdigest()


def parts(entry) -> dict[str, float]:
    """用冻结 trace 拆原分；覆盖项等额留在 other，不猜测其语义。"""

    trace = entry.trace
    out = {key: float(trace[key]) for key in COMPONENTS}
    out["risk_part"] = -6.0 * float(trace["risk_units"])
    out["other"] = float(entry.score) - sum(out.values())
    return out


def main() -> None:
    """只作赢家条件样本的确定性重判，不取历史动作作收益标签。"""

    if OUT.exists():
        raise FileExistsError("G200 结果已存在，拒绝覆盖")
    prior = json.loads(SOURCE.read_text(encoding="utf-8"))
    classic_result = json.loads((classic.OUT / "result.json").read_text(encoding="utf-8"))
    if (prior["r18_scorer_sha256"] != R18_INTEGRATED_POSITIVE_V2_SHA256
            or len(prior["rows"]) != 20 or len(classic_result["rows"]) != 16):
        raise ValueError("G200 大牌榜来源或冻结评分源码漂移")
    scorer = ActionValueScorer("g200-r18-shadow", R18_INTEGRATED_POSITIVE_V2_SOURCE)
    documents = {}
    rows = []
    for item in prior["rows"]:
        rank = item["rank"]
        if rank not in documents:
            documents[rank] = json.loads(
                (classic.OUT / f"rank{rank}-round.json").read_text(encoding="utf-8"))
        doc = documents[rank]
        winner = classic_result["rows"][rank - 1]["winner_seat"]
        indices = [index for index, frame in enumerate(doc["frames"])
                   if (frame.get("ev") or {}).get("seq") == item["event_seq"]]
        if len(indices) != 1 or indices[0] == 0:
            raise ValueError("G200 历史事件身份缺失或重复")
        observation = classic.observation(doc, indices[0] - 1, winner)
        request = classic.request_for(observation, rank)
        scored = scorer.score(build_scoring_view(request, value_limits=c31.VALUE_LIMITS))
        if scored.status != "SCORED":
            raise ValueError("G200 冻结 R18 v2 评分失败")
        entries = {entry.action_key: entry for entry in scored.entries}
        if len(entries) != len(scored.entries):
            raise ValueError("G200 评分动作键重复")
        parent = entries[item["r18_action"]]
        alternate = entries[item["strong_action"]]
        top = min(entries, key=lambda key: (-entries[key].score, key))
        if (top != item["r18_action"]
                or abs(parent.score - alternate.score - item["r18_score_gap"]) > 1e-8):
            raise ValueError("G200 首选或原评分差不对账")
        old, new = parts(parent), parts(alternate)
        delta = {key: round(new[key] - old[key], 8) for key in old}
        if abs(sum(delta.values()) + item["r18_score_gap"]) > 1e-8:
            raise ValueError("G200 评分分量差不守恒")
        rows.append({"rank": rank, "game_id": item["game_id"],
                     "round_no": item["round_no"], "event_seq": item["event_seq"],
                     "parent_action": item["r18_action"],
                     "strong_action": item["strong_action"],
                     "score_gap": item["r18_score_gap"],
                     "strong_minus_parent_natural_types":
                         item["strong_minus_r18"].get("natural_types"),
                     "strong_minus_parent_natural_capacity":
                         item["strong_minus_r18"].get("natural_capacity"),
                     "strong_minus_parent_score_parts": delta})
    broad = [row for row in rows
             if row["strong_minus_parent_natural_types"] is not None
             and row["strong_minus_parent_natural_types"] > 0]
    familiar_override = [row for row in broad
                         if row["strong_minus_parent_score_parts"]["base_score"] > 0
                         and row["strong_minus_parent_score_parts"]["river_part"] == -3
                         and row["strong_minus_parent_score_parts"]["style_part"] == -4]
    if len(rows) != 20:
        raise ValueError("G200 大牌榜严格弃牌对数量漂移")
    payload = {
        "schema": "g200-highhand-score-conflict/1",
        "source_sha256": {
            "g191_result": digest(SOURCE), "g184_result": digest(classic.OUT / "result.json"),
            "script": digest(Path(__file__)),
            **{f"rank{rank}_round": digest(classic.OUT / f"rank{rank}-round.json")
               for rank in sorted(documents)},
        },
        "summary": {"strict_discard_pairs": len(rows),
                    "strictly_broader_natural_types": len(broad),
                    "among_broader_familiar_plus_rank1_override":
                        len(familiar_override),
                    "broader_ranks": dict(sorted(Counter(str(row["rank"])
                                                           for row in broad).items()))},
        "rows": rows,
        "boundary": "赢家条件局部评分冲突，不含备选续打、反事实收益或熟牌分量的总体价值。",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True,
                              indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload["summary"], ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
