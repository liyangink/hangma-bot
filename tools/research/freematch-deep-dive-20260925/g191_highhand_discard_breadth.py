#!/usr/bin/env python3
"""G191：大牌榜强手与 R18 严格弃牌分歧的可见自然进张逐项对账。"""

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

from hangma_bot.hangma import public_tile_counts
from hangma_bot.hangma.engine import _build_context
from hangma_bot.policy.action_value_policy import build_scoring_view
from hangma_bot.policy.action_value_seeds import ActionValueScorer
from hangma_bot.policy.r18_integrated_positive_v2 import (
    R18_INTEGRATED_POSITIVE_V2_SOURCE, R18_INTEGRATED_POSITIVE_V2_SHA256,
)

import c31_action_layer_gap as c31
import g178_natural_vs_standard_support as natural
import g184_classic_highhand_shadow as classic


HERE = Path(__file__).resolve().parent
SOURCE = classic.OUT / "result.json"
OUTPUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g191-highhand-discard-breadth-20260929/result.json')


def digest(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def direction(value: int) -> str:
    return "up" if value > 0 else "down" if value < 0 else "equal"


def production(facts) -> dict[str, int]:
    """保留生产普通型有效牌的正公开容量，包括白板本身。"""
    if facts is None or facts.standard_useful_tiles is None:
        raise ValueError("G191 普通型生产进张缺失")
    out = {}
    for item in facts.standard_useful_tiles:
        if item.code in out or not 0 <= item.remaining_estimate <= 4:
            raise ValueError("G191 生产进张向量非法")
        if item.remaining_estimate:
            out[item.code] = item.remaining_estimate
    return out


def action_facts(candidate) -> dict:
    """原规则事实的向听和正容量摘要；未知七对保持空值。"""
    facts = candidate.facts
    if facts is None or facts.standard_shanten_after is None:
        raise ValueError("G191 合法弃牌缺普通型事实")
    support = production(facts)
    return {
        "standard_shanten": facts.standard_shanten_after,
        "seven_pairs_shanten": facts.seven_pairs_shanten_after,
        "production_standard_support": support,
        "production_standard_types": len(support),
        "production_standard_capacity": sum(support.values()),
    }


def compare_one(rank: int, doc: dict, item: dict, winner: int,
                scorer: ActionValueScorer) -> dict:
    """只在历史同窗重判；不将后续赢家轨迹当反事实收益。"""
    seq = item["event_seq"]
    matches = [index for index, frame in enumerate(doc["frames"])
               if (frame.get("ev") or {}).get("seq") == seq]
    if len(matches) != 1 or matches[0] == 0:
        raise ValueError("G191 历史动作序号非唯一")
    visible = classic.observation(doc, matches[0] - 1, winner)
    request = classic.request_for(visible, rank)
    candidates = {candidate.action_key: candidate
                  for candidate in request.rules.legal_candidates}
    if len(candidates) != len(request.rules.legal_candidates):
        raise ValueError("G191 合法动作键重复")
    original, selected = item["r18_top"], item["actual"]
    if original not in candidates or selected not in candidates:
        raise ValueError("G191 两个弃牌不在同窗合法集合")
    scored = scorer.score(build_scoring_view(request, value_limits=c31.VALUE_LIMITS))
    if scored.status != "SCORED" or not scored.entries:
        raise ValueError("G191 冻结 R18 重评分失败")
    scores = {entry.action_key: entry.score for entry in scored.entries}
    top = min(scores, key=lambda key: (-scores[key], key))
    if (top != original or
            round(scores[original] - scores[selected], 8) != item["r18_score_gap"]):
        raise ValueError("G191 父代首选或严格分差漂移")
    facts = {key: action_facts(candidates[key]) for key in (original, selected)}
    old, new = facts[original], facts[selected]
    deltas = {
        "standard_shanten": new["standard_shanten"] - old["standard_shanten"],
        "production_standard_types": (new["production_standard_types"] -
                                      old["production_standard_types"]),
        "production_standard_capacity": (new["production_standard_capacity"] -
                                         old["production_standard_capacity"]),
        "seven_pairs_shanten": (
            None if new["seven_pairs_shanten"] is None
            or old["seven_pairs_shanten"] is None else
            new["seven_pairs_shanten"] - old["seven_pairs_shanten"]),
    }
    natural_facts = None
    if original != "discard:白" and selected != "discard:白":
        full = _build_context(visible).full_hand()
        unseen = public_tile_counts.count_unseen_tiles(visible)
        meld_count = len(visible.melds[visible.seat])
        if any(value is None for value in unseen[:33]):
            raise ValueError("G191 公开未知牌容量不完整")
        natural_facts = {}
        for key in (original, selected):
            need, support = natural.natural(
                natural._drop(full, key.split(":", 1)[1]), unseen, meld_count)
            natural_facts[key] = {"need": need, "support": support,
                                  "types": len(support),
                                  "capacity": sum(support.values())}
        deltas.update({
            "natural_need": (natural_facts[selected]["need"] -
                             natural_facts[original]["need"]),
            "natural_types": (natural_facts[selected]["types"] -
                              natural_facts[original]["types"]),
            "natural_capacity": (natural_facts[selected]["capacity"] -
                                 natural_facts[original]["capacity"]),
        })
    return {
        "rank": rank, "game_id": doc["game_id"], "round_no": doc["round_no"],
        "event_seq": seq, "white_held_before": item["white_held"],
        "baotou_before": item["baotou"], "chain_count_before": item["chain_count"],
        "strong_action": selected, "r18_action": original,
        "r18_score_gap": item["r18_score_gap"],
        "rule_facts": facts, "natural_facts": natural_facts,
        "strong_minus_r18": deltas,
    }


def main() -> None:
    """固定 G184 已确认的严格弃牌分歧；拒绝覆盖结果。"""
    if OUTPUT.exists():
        raise FileExistsError("G191 结果已存在；拒绝覆盖")
    source = json.loads(SOURCE.read_text(encoding="utf-8"))
    if (source.get("schema") != "g184-classic-highhand-shadow/1"
            or source["parent_scorer_sha256"] != R18_INTEGRATED_POSITIVE_V2_SHA256
            or len(source["rows"]) != 16):
        raise ValueError("G191 经典复盘来源、父代或数量漂移")
    scorer = ActionValueScorer("g191-r18-shadow", R18_INTEGRATED_POSITIVE_V2_SOURCE)
    records = []
    source_files = {}
    for row in source["rows"]:
        rank = row["rank"]
        path = classic.OUT / f"rank{rank}-round.json"
        source_files[f"rank{rank}"] = digest(path)
        doc = json.loads(path.read_text(encoding="utf-8"))
        if doc["game_id"] != row["game_id"] or doc["round_no"] != row["round_no"]:
            raise ValueError("G191 大牌赢家身份漂移")
        for item in row["actions"]:
            if (item["r18_score_gap"] > 1e-8
                    and item["actual"].startswith("discard:")
                    and item["r18_top"].startswith("discard:")):
                records.append(compare_one(rank, doc, item, row["winner_seat"], scorer))
    if len(records) != 20:
        raise ValueError("G191 严格弃牌分歧数量漂移")
    summary = {"strict_discard_pairs": len(records),
               "nonwhite_comparable_pairs": sum(item["natural_facts"] is not None
                                                for item in records),
               "directions": {}}
    for field in ("standard_shanten", "production_standard_types",
                  "production_standard_capacity", "seven_pairs_shanten",
                  "natural_need", "natural_types", "natural_capacity"):
        counts = Counter("unknown" if field not in row["strong_minus_r18"]
                         or row["strong_minus_r18"][field] is None else
                         direction(row["strong_minus_r18"][field])
                         for row in records)
        summary["directions"][field] = dict(sorted(counts.items()))
    payload = {
        "schema": "g191-highhand-discard-breadth/1",
        "source_sha256": {"g184_result": digest(SOURCE),
                          "g184_replays": source_files,
                          "g184_projection": digest(Path(classic.__file__)),
                          "natural_math": digest(Path(natural.__file__)),
                          "script": digest(Path(__file__))},
        "r18_scorer_sha256": R18_INTEGRATED_POSITIVE_V2_SHA256,
        "summary": summary, "rows": records,
        "boundary": ("大牌赢家条件样本的同窗、行动前可见进张事实对账；"
                     "后续历史动作在首次分歧后不代表 R18 可达轨迹，"
                     "牌种和公开容量不是真实牌墙概率或反事实净收益。"),
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True,
                                 indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
