#!/usr/bin/env python3
"""G7a 离线诊断：无新杠飘的三摸胡牌番值与普通/七对路线。"""

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

from functools import lru_cache
import json
from pathlib import Path
import sys
from time import perf_counter

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import g7_three_self_draw_probe as speed  # noqa: E402
from hangma_bot.application.audit_codec import decision_request_from_json  # noqa: E402
from hangma_bot.hangma.hand_analysis import win_split  # noqa: E402
from hangma_bot.hangma.internal_types import TILE_INDEX, TILE_ORDER, counts_from_tiles  # noqa: E402
from hangma_bot.hangma.progression import baotou_after_discard  # noqa: E402
from hangma_bot.hangma.public_tile_counts import count_unseen_tiles  # noqa: E402
from hangma_bot.hangma.settlement import compute_fan  # noqa: E402
from hangma_bot.kernel.actions import Tile  # noqa: E402

WHITE_INDEX = TILE_INDEX["白"]
SELECTED = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g7-three-draw-exposure-20260927/result.json')


@lru_cache(maxsize=300_000)
def _hand(counts: tuple[int, ...]):
    return tuple(Tile(code) for index, code in enumerate(TILE_ORDER)
                 for _ in range(counts[index]))


@lru_cache(maxsize=300_000)
def _baotou(counts: tuple[int, ...], melds: int):
    """普通自摸前的静态爆头；不模拟杠补的跨动作继承。"""
    return baotou_after_discard(_hand(counts), melds)


@lru_cache(maxsize=300_000)
def _win_vector(pre_counts: tuple[int, ...], draw_index: int, melds: int):
    """(番,普通胡,七对胡,爆头胡,胡)；番由官方规则层计算。"""
    after = speed.changed(pre_counts, draw_index, 1)
    win = win_split(_hand(after), melds)
    if win is None:
        raise ValueError("向听与胡牌分解不一致")
    baotou = _baotou(pre_counts, melds)
    fan = compute_fan(win, chain_count=0, piao=0, baotou=baotou).fan
    return fan, int(win.branch == "平胡"), int(win.branch == "七对"), int(baotou), 1


@lru_cache(maxsize=300_000)
def favorable_fan(counts: tuple[int, ...], unseen: tuple[int, ...], melds: int, depth: int):
    """普通自摸、无新链、摸间只弃非白牌的乐观番值容量。"""
    current = speed.summary(counts, melds)
    if current.shanten >= depth:
        return (0, 0, 0, 0, 0)
    total = [0, 0, 0, 0, 0]
    n = sum(unseen)
    if depth == 1:
        if current.shanten != 0:
            return tuple(total)
        for code in current.useful_codes:
            index = TILE_INDEX[code]
            if unseen[index] <= 0:
                continue
            terminal = _win_vector(counts, index, melds)
            for part in range(5):
                total[part] += unseen[index] * terminal[part]
        return tuple(total)
    for draw_index, available in enumerate(unseen):
        if available <= 0:
            continue
        drawn = speed.changed(counts, draw_index, 1)
        next_unseen = speed.changed(unseen, draw_index, -1)
        if speed.summary(drawn, melds).is_win:
            multiplier = speed.falling(n-1, depth-1)
            best = tuple(item*multiplier for item in _win_vector(counts, draw_index, melds))
        else:
            best = (0, 0, 0, 0, 0)
            for discard_index, held in enumerate(drawn):
                if held <= 0 or discard_index == WHITE_INDEX:
                    continue
                after = speed.changed(drawn, discard_index, -1)
                if speed.summary(after, melds).shanten >= depth-1:
                    continue
                value = favorable_fan(after, next_unseen, melds, depth-1)
                if value[0] > best[0] or (value[0] == best[0] and value[4] > best[4]):
                    best = value
        for part in range(5):
            total[part] += available * best[part]
    return tuple(total)


def evaluate(request: dict, a_key: str, b_key: str):
    """同一个玩家可见观察上的 A/B；仅返代理路径容量与时间。"""
    parsed = decision_request_from_json(request)
    obs = parsed.observation
    unseen = count_unseen_tiles(obs)
    if any(value is None for value in unseen):
        raise ValueError("公开未知容量不完整")
    melds = len(obs.melds[obs.seat])
    hand = list(obs.my_hand)
    expected = 14 - 3*melds
    if len(hand) == expected-1 and obs.drawn_tile is not None:
        hand.append(obs.drawn_tile)
    if len(hand) != expected:
        raise ValueError("暗手张数不合法")
    start = perf_counter()
    result = {}
    for key in (a_key, b_key):
        after = list(hand)
        after.remove(Tile(key[8:]))
        counts = counts_from_tiles(tuple(after))
        result[key] = favorable_fan(counts, unseen, melds, 3)
    elapsed_ms = (perf_counter()-start)*1000
    favorable_fan.cache_clear()
    _win_vector.cache_clear()
    _baotou.cache_clear()
    _hand.cache_clear()
    speed.summary.cache_clear()
    return result, unseen, elapsed_ms


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("three_only", "highwhite"), default="three_only")
    parser.add_argument("--per-group", type=int, default=4,
                        help="三组各取哈希最小的 N 场；只做机制诊断")
    args = parser.parse_args()
    rows = json.loads(SELECTED.read_text(encoding="utf-8"))["selected"]
    if args.mode == "highwhite":
        selected = sorted((row for row in rows if row["whites"] >= 2),
                          key=lambda row: (row["group"], row["hash"]))
    else:
        selected = []
        for group in ("pm", "recent", "historical"):
            eligible = [row for row in rows if row["group"] == group
                        and row["delta_2"] == 0 and row["delta_3"] != 0]
            selected.extend(sorted(eligible, key=lambda row: row["hash"])[:args.per_group])
    output = []
    import natural_shape_loss_screen as screen
    targets = {}
    for selected_row in selected:
        target = (selected_row["game_id"], selected_row["round_no"],
                  selected_row["trigger_seq"])
        targets.setdefault(selected_row["room"], set()).add(target)
    requests = {}
    for room, needed in targets.items():
        for run in sorted((screen.ROOT / "artifacts/sessions" / room / "audit/runs").glob("*")):
            manifest = run / "manifest.json"
            if not manifest.is_file():
                continue
            release = ((json.loads(manifest.read_text(encoding="utf-8")).get("payload") or {})
                       .get("policy_release") or {})
            if release.get("candidate_source_sha256") != screen.PARENT_SHA256:
                continue
            for context, raw, _plan in screen._iter_decisions(run):
                key = (context.get("game_id"), context.get("round_no"),
                       context.get("trigger_seq"))
                if key in needed:
                    if key in requests and requests[key] != raw:
                        raise SystemExit("同一冻结窗口出现不一致的官方观察：" + str(key))
                    requests[key] = raw
            if needed.issubset(requests):
                break
    for selected_row in selected:
        target = (selected_row["game_id"], selected_row["round_no"],
                  selected_row["trigger_seq"])
        request = requests.get(target)
        if request is None:
            raise SystemExit("冻结观察消失：" + str(target))
        capacity, unseen, elapsed_ms = evaluate(request, selected_row["a"], selected_row["b"])
        output.append({"group": selected_row["group"], "game_id": target[0],
                       "round_no": target[1], "trigger_seq": target[2],
                       "a": selected_row["a"], "b": selected_row["b"],
                       "whites": selected_row["whites"], "unknown_pool": sum(unseen),
                       "a_vector": capacity[selected_row["a"]],
                       "b_vector": capacity[selected_row["b"]],
                       "fan_delta": capacity[selected_row["b"]][0]-capacity[selected_row["a"]][0],
                       "elapsed_ms": round(elapsed_ms, 3)})
    folder = ("g7-fan-route-highwhite-20260927" if args.mode == "highwhite"
              else "g7-fan-route-probe-20260927")
    out = _project_file(_PROJECT_ROOT, HERE / "evidence" / folder / "result.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"schema": "g7-fan-route-probe/1", "mode": args.mode,
                               "rows": output,
                               "scope": "无对手动作、无新杠飘、摸间只弃非白牌的三摸乐观番值"},
                              ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("windows",len(output),"fan_delta_positive",sum(row["fan_delta"]>0 for row in output),
          "zero",sum(row["fan_delta"]==0 for row in output),
          "negative",sum(row["fan_delta"]<0 for row in output),
          "max_ms",round(max((row["elapsed_ms"] for row in output),default=0),1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
