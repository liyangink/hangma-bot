#!/usr/bin/env python3
"""G42：结果盲复核 G30 的全部改选是否真有第三摸牌形区分力。"""

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
import time

import g11_cross_family_action_atlas as atlas
import g7_three_self_draw_probe as g7
from hangma_bot.hangma.engine import _build_context
from hangma_bot.hangma.internal_types import counts_from_tiles
from hangma_bot.hangma.public_tile_counts import count_unseen_tiles
from hangma_bot.kernel.actions import Tile
from hangma_bot.kernel.serialization import observation_from_json


HERE = Path(__file__).resolve().parent
G30 = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g30-edge-behavior-20260927/result.json')
PREREG = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/G42-EDGE-THREE-DRAW-PREREG-2026-09-27.md')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g42-edge-three-draw-20260927/result.json')


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _window(row: dict) -> tuple[str, int, int]:
    return row["game_id"], row["round_no"], row["trigger_seq"]


def _capacity(full: tuple, unseen: tuple[int, ...], melds: int,
              key: str, depth: int) -> int:
    """同一生产数学入口；每臂只删去其合法弃牌。"""
    hand = list(full)
    hand.remove(Tile(key.split(":", 1)[1]))
    return g7.favorable(counts_from_tiles(tuple(hand)), unseen, melds, depth)


def main() -> None:
    """锁定 G30 的全部改选，不因计算结果而缩小样本或调方向。"""
    if OUT.exists():
        raise FileExistsError("拒绝覆盖 G42 冻结证据")
    g30 = json.loads(G30.read_text(encoding="utf-8"))
    frozen = json.loads(atlas.FROZEN.read_text(encoding="utf-8"))
    complete = atlas._complete_ids()
    changed = g30["changed"]
    if (g30.get("outcome_blind") is not True or len(changed) != 608 or
            len(complete) != 909 or
            g30["parent_source_sha256"] != frozen["parent_source_sha256"] or
            g30["candidate_source_sha256"] !=
            "bdfaf823e5b52718f3eefef5ac9972ee455dc9742dfda560c1b53f4e238ae7b2"):
        raise ValueError("G30/G42 冻结输入身份漂移")
    targets = defaultdict(dict)
    for row in changed:
        if row["game_id"] not in complete:
            raise ValueError("G30 改选不在核验完整桌")
        key = _window(row)
        if key in targets[row["room_id"]]:
            raise ValueError("重复窗口")
        targets[row["room_id"]][key] = row
    rows = []
    timings = []
    seen = set()
    for room in frozen["rooms"]:
        pending = targets.get(room["room_id"])
        if not pending:
            continue
        audit = atlas.source.ROOT / room["audit_dir"]
        decisions = audit / "participants" / atlas.source.ACTOR / "decisions.jsonl"
        if decisions.stat().st_size != room["decision_bytes"]:
            raise ValueError("冻结官方审计大小漂移")
        release = ((json.loads((audit / "manifest.json").read_text(encoding="utf-8"))
                    .get("payload") or {}).get("policy_release") or {})
        if release.get("candidate_source_sha256") != frozen["parent_source_sha256"]:
            raise ValueError("房间父代源码漂移")
        for context, raw, plan in atlas.source.screen._iter_decisions(audit):
            key = (context.get("game_id"), context.get("round_no"),
                   context.get("trigger_seq"))
            target = pending.get(key)
            if target is None:
                continue
            if key in seen:
                raise ValueError("目标窗口在审计中重复")
            seen.add(key)
            ranked = sorted(plan.get("candidates") or [],
                            key=lambda item: item.get("rank", 10**9))
            if not ranked or ranked[0].get("action_key") != target["parent_action"]:
                raise ValueError("父代动作与 G30 行为记录不一致")
            legal = {item["action_key"] for item in
                     (raw.get("rules") or {}).get("legal_candidates") or []}
            if (target["parent_action"] not in legal or
                    target["candidate_action"] not in legal):
                raise ValueError("两臂弃牌不在生产合法候选内")
            obs = observation_from_json(raw["observation"])
            unseen = count_unseen_tiles(obs)
            if any(type(value) is not int or value < 0 for value in unseen):
                raise ValueError("公开未见容量缺失或非法")
            pool = tuple(unseen)
            full = _build_context(obs).full_hand()
            melds = len(obs.melds[obs.seat])
            start = time.perf_counter()
            values = {arm: {str(depth): _capacity(full, pool, melds, action, depth)
                            for depth in (2, 3)}
                      for arm, action in (("parent", target["parent_action"]),
                                          ("candidate", target["candidate_action"]))}
            elapsed = (time.perf_counter() - start) * 1000
            timings.append(elapsed)
            d2 = values["candidate"]["2"] - values["parent"]["2"]
            d3 = values["candidate"]["3"] - values["parent"]["3"]
            rows.append({"room_id": target["room_id"], "game_id": key[0],
                         "round_no": key[1], "trigger_seq": key[2],
                         "parent_action": target["parent_action"],
                         "candidate_action": target["candidate_action"],
                         "white_count": sum(tile.code == "白" for tile in full),
                         "unseen_pool": sum(pool), "meld_count": melds,
                         "two_draw_delta": d2, "three_draw_delta": d3,
                         "three_draw_denominator": g7.falling(sum(pool), 3),
                         "elapsed_ms": round(elapsed, 3)})
            if len(rows) % 16 == 0:
                g7.favorable.cache_clear()
                g7.summary.cache_clear()
            if len(rows) % 50 == 0:
                print(json.dumps({"completed": len(rows), "total": len(changed),
                                  "last_elapsed_ms": round(elapsed, 1)}), flush=True)
    if seen != {_window(row) for row in changed} or len(rows) != len(changed):
        raise ValueError("部分 G30 改选未在官方审计中找到")
    timings.sort()
    direction = Counter("positive" if row["three_draw_delta"] > 0 else
                        "negative" if row["three_draw_delta"] < 0 else "equal"
                        for row in rows)
    result = {
        "schema": "g42-edge-three-draw-screen/1", "outcome_blind": True,
        "g30_result_sha256": _sha(G30),
        "frozen_rooms_sha256": _sha(atlas.FROZEN),
        "prereg_sha256": _sha(PREREG),
        "script_sha256": _sha(Path(__file__)),
        "parent_source_sha256": frozen["parent_source_sha256"],
        "complete_official_tables": len(complete),
        "windows": len(rows), "three_draw_direction": dict(sorted(direction.items())),
        "positive_complete_tables": len({row["game_id"] for row in rows
                                         if row["three_draw_delta"] > 0}),
        "two_draw_nonzero": sum(row["two_draw_delta"] != 0 for row in rows),
        "elapsed_ms": {label: round(timings[min(int((len(timings)-1)*fraction),
                                                len(timings)-1)], 3)
                       for label, fraction in (("p50", .5), ("p95", .95),
                                               ("p99", .99), ("max", 1.0))},
        "rows": rows,
        "boundary": "无对手动作、按公开未知池均匀无放回的理想化摸牌容量；不是墙内概率、白板保留率或完整桌收益。",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                   encoding="utf-8")
    print(json.dumps({key: value for key, value in result.items() if key != "rows"},
                     ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
