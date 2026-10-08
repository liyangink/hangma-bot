#!/usr/bin/env python3
"""四间强手开发房：结果盲核潜在自然连接是否解释其与父代的弃牌分歧。"""

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

import c31_action_layer_gap as c31
import g05_parent_dev_behavior as baseline
import g11_longitudinal_route_audit as hand_tools
import g13_two_draw_baotou_support as public
import g14_latent_natural_links_probe as links
from hangma_bot.application.audit_codec import observation_from_json
from hangma_bot.hangma.interface import RuleCompleteness


HERE = Path(__file__).resolve().parent
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g14-strong-latent-link-preference-20260927/result.json')


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _facts(candidate) -> dict:
    """只提取生产规则已产生的自然/综合向听和即时有效牌向量。"""
    value = candidate.facts
    def tiles(items):
        return None if items is None else [
            {"code": item.code, "remaining_estimate": item.remaining_estimate}
            for item in items]
    return {"shanten_after": value.shanten_after,
            "standard_shanten_after": value.standard_shanten_after,
            "seven_pairs_shanten_after": value.seven_pairs_shanten_after,
            "standard_useful_tiles": tiles(value.standard_useful_tiles),
            "useful_tiles": tiles(value.useful_tiles)}


def main() -> None:
    """只看四间预定开发房的强手真实弃牌与父代同窗动作；不读结算。"""
    if OUT.exists():
        raise SystemExit("强手潜在连接结果已存在，拒绝覆盖")
    counts = Counter()
    rooms = defaultdict(Counter)
    source = {}
    examples = []
    for directory in baseline.DISCARD_DIRS:
        path = _project_file(_PROJECT_ROOT, HERE / "evidence" / directory / "windows.json")
        source[directory] = _sha(path)
        for row in json.loads(path.read_text(encoding="utf-8"))["windows"]:
            actual = row["actual_action"]
            parent = row["parent_top_action"]
            if (not isinstance(actual, str) or not isinstance(parent, str)
                    or not actual.startswith("discard:")
                    or not parent.startswith("discard:") or actual == parent):
                continue
            observation = row["observation"]
            parsed = hand_tools._hand(observation)
            if parsed is None:
                counts["hand_unavailable"] += 1
                continue
            full, _, _melds = parsed
            after_a = hand_tools._after_discard(full, actual)
            after_p = hand_tools._after_discard(full, parent)
            if after_a is None or after_p is None:
                raise ValueError("已记录的强手/父代弃牌不在本人手牌")
            if after_a["白"] < 1 or after_p["白"] != after_a["白"]:
                continue
            analysis = c31.RULES.analyze(observation_from_json(observation),
                                         value_limits=c31.VALUE_LIMITS)
            if analysis.completeness is not RuleCompleteness.COMPLETE:
                counts["analysis_incomplete"] += 1
                continue
            candidates = {item.action_key: item for item in analysis.legal_candidates}
            if actual not in candidates or parent not in candidates:
                raise ValueError("强手/父代弃牌不在生产合法动作")
            fa, fp = _facts(candidates[actual]), _facts(candidates[parent])
            discards, exposed = public._public_counts(observation)
            la = links._latent(after_a, actual, fa, discards, exposed)
            lp = links._latent(after_p, parent, fp, discards, exposed)
            if la is None or lp is None:
                counts["latent_unknown"] += 1
                continue
            room = row["room_id"]
            delta = la["capacity_upper"] - lp["capacity_upper"]
            direction = "strong_more" if delta > 0 else "strong_less" if delta < 0 else "same"
            counts[direction] += 1
            rooms[room][direction] += 1
            exact = (fa["shanten_after"] == fp["shanten_after"] and
                     fa["standard_shanten_after"] == fp["standard_shanten_after"] and
                     fa["seven_pairs_shanten_after"] == fp["seven_pairs_shanten_after"] and
                     links._support_vector(fa, "standard_useful_tiles") ==
                     links._support_vector(fp, "standard_useful_tiles") and
                     links._support_vector(fa, "useful_tiles") ==
                     links._support_vector(fp, "useful_tiles"))
            if exact:
                counts["exact_immediate_" + direction] += 1
                rooms[room]["exact_immediate_" + direction] += 1
            if len(examples) < 12:
                examples.append({"room_id": room, "game_id": row["game_id"],
                                 "round_no": row["round_no"], "draw_seq": row["draw_seq"],
                                 "actual": actual, "parent": parent,
                                 "white_after": after_a["白"],
                                 "strong_minus_parent_latent_upper": delta,
                                 "same_immediate_vectors": exact,
                                 "parent_score_gap": row["parent_score_gap_top_minus_actual"]})
    result = {"schema": "g14-strong-latent-link-preference/1", "outcome_blind": True,
              "source_sha256": source, "script_sha256": _sha(Path(__file__)),
              "counts": dict(sorted(counts.items())),
              "rooms": {name: dict(sorted(value.items())) for name, value in sorted(rooms.items())},
              "examples": examples,
              "boundary": "仅强手四开发房观察性弃牌偏好；不读五间留出房和任何结算。偏好不是反事实收益。"}
    OUT.parent.mkdir(parents=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True,
                              indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"counts": result["counts"], "rooms": result["rooms"]},
                     ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
