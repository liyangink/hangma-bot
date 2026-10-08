#!/usr/bin/env python3
"""赛后诊断进张多样性与三家暗手占用；暗手绝不作为策略输入。"""

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
import json
from pathlib import Path
import random
import sys

HERE = Path(__file__).resolve().parent
ROOT = _PROJECT_ROOT
sys.path[:0] = [str(HERE), str(_project_file(_PROJECT_ROOT, ROOT / "review/baotou-anatomy-20260925"))]

import anatomy_lib as anatomy  # noqa: E402
import c31_action_layer_gap as c31  # noqa: E402
import natural_shape_loss_screen as screen  # noqa: E402


SETS = {
    "develop": screen.ROOMS[:2],
    "confirm": screen.ROOMS[2:4],
    # 已参与发现问题的战役只能作为探索性扩容，不能冒充独立确认集。
    "explore": ("r18-sse-freematch-campaign-20260925b",),
    # 事后增选的旧战役同样只用于回顾性复核。
    "historical": ("r18-auto-match-campaign-20260923",),
}


def _useful(facts: dict):
    """返回正公开容量有效牌映射；未知保持不可用。"""
    raw = facts.get("useful_tiles")
    if not isinstance(raw, list):
        return None
    result = {}
    for item in raw:
        code = item.get("code")
        amount = item.get("remaining_estimate")
        if not isinstance(code, str) or type(amount) is not int or not 0 <= amount <= 4:
            return None
        if amount > 0:
            result[code] = amount
    return result


def _alternatives(request: dict, plan: dict):
    """冻结公开事实上的比较规则；返回一个宽面备选及其路线安全标记。"""
    obs = request.get("observation") or {}
    if obs.get("phase") != "draw":
        return None
    planned = plan.get("candidates") or []
    if not planned or not str(planned[0].get("action_key", "")).startswith("discard:"):
        return None
    actions = {
        row.get("action_key"): row
        for row in (request.get("rules") or {}).get("legal_candidates") or []
    }
    chosen = planned[0]["action_key"]
    own = actions.get(chosen)
    if not isinstance(own, dict) or not isinstance(own.get("facts"), dict):
        return None
    base = own["facts"]
    base_useful = _useful(base)
    if base_useful is None or type(base.get("shanten_after")) is not int:
        return None
    base_count = sum(base_useful.values())
    eligible = []
    for key, action in actions.items():
        if key == chosen or not isinstance(key, str) or not key.startswith("discard:"):
            continue
        facts = action.get("facts")
        if not isinstance(facts, dict) or facts.get("shanten_after") != base["shanten_after"]:
            continue
        alt_useful = _useful(facts)
        if alt_useful is None or len(alt_useful) <= len(base_useful):
            continue
        alt_count = sum(alt_useful.values())
        gap = alt_count - base_count
        if gap not in (0, -1, -2):
            continue
        route_safe = True
        for name in ("standard_shanten_after", "seven_pairs_shanten_after"):
            b, a = base.get(name), facts.get(name)
            if b is None and a is None:
                continue
            if type(b) is not int or type(a) is not int or a > b:
                route_safe = False
        eligible.append((len(alt_useful)-len(base_useful), alt_count, key,
                         route_safe, gap, alt_useful))
    if not eligible:
        return None
    eligible.sort(key=lambda row: (-row[0], -row[1], row[2]))
    width_gain, _count, alternate, safe, gap, alt_useful = eligible[0]
    return chosen, alternate, base_useful, alt_useful, gap, width_gain, safe


def _official_snapshots(room: str):
    """按赛后完整事件重建我方弃牌后、他家响应前的四手；只用于标签。"""
    source = _project_file(_PROJECT_ROOT, ROOT / "artifacts/sessions" / room / "official")
    snapshots = {}
    seen_games = set()
    for path in sorted(source.glob("dl-*/events.json")):
        doc = json.loads(path.read_text(encoding="utf-8"))
        game = doc.get("game_id")
        if not isinstance(game, str) or game in seen_games:
            continue
        seen_games.add(game)
        metadata = c31.round_metadata(doc)
        for round_no, events, start_hands in anatomy.round_blocks(doc):
            if not start_hands:
                continue
            dealer = (metadata.get(round_no) or {}).get("dealer")
            if dealer is None:
                continue
            for seq, snap in c31.reconstruct(events, start_hands, [0, 0, 0, 0], dealer).items():
                snapshots[(game, round_no, seq)] = snap
    return snapshots


def _rows(rooms):
    """仅关联规则事实与赛后隐藏占用；逐窗唯一。"""
    counters = Counter()
    rows = []
    seen = set()
    for room in rooms:
        snapshots = _official_snapshots(room)
        audit = _project_file(_PROJECT_ROOT, ROOT / "artifacts/sessions" / room / "audit" / "runs")
        for run in sorted(audit.glob("*")):
            manifest = run / "manifest.json"
            if not manifest.is_file():
                continue
            meta = (json.loads(manifest.read_text(encoding="utf-8")).get("payload") or {})
            if (meta.get("policy_release") or {}).get("candidate_source_sha256") != screen.PARENT_SHA256:
                continue
            for context, request, plan in screen._iter_decisions(run):
                key = (context.get("game_id"), context.get("round_no"), context.get("trigger_seq"))
                if key in seen:
                    counters["duplicate_audit_window"] += 1
                    continue
                seen.add(key)
                pair = _alternatives(request, plan)
                if pair is None:
                    continue
                counters["candidate_pair"] += 1
                snap = snapshots.get((key[0], key[1], key[2] + 1))
                if snap is None:
                    counters["no_official_snap"] += 1
                    continue
                obs = request["observation"]
                seat = obs.get("seat")
                chosen, alternate, base_useful, alt_useful, gap, width_gain, safe = pair
                if snap["discarder"] != seat or snap["tile"] != chosen[8:]:
                    counters["official_action_mismatch"] += 1
                    continue
                others = Counter()
                for other_seat, hand in enumerate(snap["hands"]):
                    if other_seat != seat:
                        others.update(hand)
                def wall_capacity(useful):
                    values = [capacity - others[code] for code, capacity in useful.items()]
                    return None if any(value < 0 for value in values) else sum(values)
                a, b = wall_capacity(base_useful), wall_capacity(alt_useful)
                if a is None or b is None:
                    counters["negative_wall_capacity"] += 1
                    continue
                unknown = obs.get("remaining_tile_count")
                if type(unknown) is not int or unknown < 20:
                    counters["invalid_wall_count"] += 1
                    continue
                unknown += sum(sum(hand.values()) for i, hand in enumerate(snap["hands"]) if i != seat)
                if unknown <= 0:
                    continue
                public_by_code = dict(base_useful)
                if any(public_by_code.get(code, count) != count
                       for code, count in alt_useful.items()):
                    counters["counterfactual_capacity_mismatch"] += 1
                    continue
                public_by_code.update(alt_useful)
                if sum(public_by_code.values()) > unknown:
                    counters["invalid_unknown_pool"] += 1
                    continue
                hidden_count = sum(others.values())
                null_delta = gap * (unknown-hidden_count) / unknown
                # 未知池同牌种置换：保持公开每种张数与对手手张数，随机分配三家暗手。
                null_deck = [int(code in alt_useful)-int(code in base_useful)
                             for code, count in public_by_code.items()
                             for _ in range(count)]
                null_deck.extend([0] * (unknown-len(null_deck)))
                rows.append({"game": key[0], "bin": gap, "safe": safe,
                             "width_gain": width_gain, "delta": b-a,
                             "excess": b-a-null_delta,
                             "zero_delta": int(b == 0)-int(a == 0),
                             "null_deck": null_deck, "hidden_count": hidden_count})
                counters["matched"] += 1
    return rows, counters


def _bootstrap(rows, field: str, seed: int = 20260927, repeats: int = 2000):
    """按官方场次重采样，返回窗口加权均值与场次聚类区间。"""
    if not rows:
        return None
    by_game = defaultdict(list)
    for row in rows:
        by_game[row["game"]].append(row[field])
    games = sorted(by_game)
    estimate = sum(row[field] for row in rows) / len(rows)
    if len(games) < 2:
        return {"mean": estimate, "ci95": None, "games": len(games)}
    rng = random.Random(seed)
    replicates = []
    for _ in range(repeats):
        sample = [by_game[rng.choice(games)] for _ in games]
        replicates.append(sum(sum(values) for values in sample) /
                          sum(len(values) for values in sample))
    replicates.sort()
    return {"mean": estimate,
            "ci95": [replicates[int(repeats * .025)], replicates[int(repeats * .975)]],
            "games": len(games)}


def _random_label_null(rows, seed: int = 20260927, repeats: int = 300):
    """在每窗未知池置换对手暗手标签，估计无选择性占用时 B-A 的均值分布。"""
    if not rows:
        return None
    rng = random.Random(seed)
    means = []
    for _ in range(repeats):
        total = 0
        for row in rows:
            deck = row["null_deck"]
            occupied = sum(deck[index] for index in rng.sample(range(len(deck)),
                                                                row["hidden_count"]))
            total += row["bin"] - occupied
        means.append(total/len(rows))
    means.sort()
    return {"mean": sum(means)/len(means),
            "p95": [means[int(repeats*.025)], means[int(repeats*.975)]]}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--set", choices=tuple(SETS), required=True)
    args = parser.parse_args()
    rows, counters = _rows(SETS[args.set])
    result = {"set": args.set, "counters": dict(counters), "bins": {}}
    for gap in (0, -1, -2):
        subset = [row for row in rows if row["bin"] == gap and row["safe"]]
        result["bins"][str(gap)] = {
            "windows": len(subset), "delta": _bootstrap(subset, "delta"),
            "excess_over_random_null": _bootstrap(subset, "excess"),
            "random_label_null": _random_label_null(subset),
            "zero_wall_difference": _bootstrap(subset, "zero_delta"),
            "average_extra_types": None if not subset else sum(row["width_gain"] for row in subset)/len(subset),
        }
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
