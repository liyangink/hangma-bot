#!/usr/bin/env python3
"""C27 可达性：候选在真实父代视图上的改选率，并按第一步的条件格分层。

与 l1_reach.py 的三点区别（口径相同，只加列）：
1. 把每个**被改选的窗口**映射到 C27 第一步的格标签（复用 c27_claim_cells.cells，
   特征从父代 view 现场算，与官方重建侧同一份定义）；
2. 输出**格内改选率** = 该格窗口中被改选的窗口数 / 该格窗口数（PREREG 第 7.3 节：
   判定用这一列，因为全局分母 32,374 而只有 2,181 个窗口带碰/吃候选）；
3. 每个格都同时给出「改到更慢向听 / 向听不变 / 更快 / 未知」四列。

用法（与 l1_reach.py 同）：
    UV_CACHE_DIR=/tmp/uv-cache .venv/bin/python \
        review/freematch-deep-dive-20260925/c27_reach_cells.py \
        review/freematch-deep-dive-20260925/candidates/OPTY-R18-C27-*.py
"""

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

import collections
import json
import sys
from pathlib import Path

ROOT = _PROJECT_ROOT
P6 = _project_file(_PROJECT_ROOT, ROOT / ".team-work" / "p6-baotou-route")
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(P6))
sys.path.insert(0, str(HERE))

import p6_lib  # noqa: E402
import c27_claim_cells as C27C  # noqa: E402

from hangma_bot.policy.action_value_seeds import ActionValueScorer  # noqa: E402


def chosen_entry(entries):
    return min(entries, key=lambda e: (-float(e["score"]), e.get("action_key") or ""))


def shanten_of(entry):
    trace = entry.get("trace") or {}
    for key in ("shanten_after", "combined_shanten", "shanten"):
        value = trace.get(key)
        if type(value) is int:
            return value
    return None


def support_of(action):
    tiles = action.get("useful_tiles")
    if not tiles:
        return None
    total = 0
    for tile in tiles:
        remaining = tile.get("remaining_estimate")
        if remaining is None or remaining is True or remaining is False:
            return None
        total += float(remaining)
    return total


def view_feature(view):
    """父代 view → C27 第一步的 9 个特征（键与官方重建侧逐字相同）。

    返回 None 表示这个窗口没有碰/吃候选（不属于任何鸣牌条件格）。
    """

    visible = view.get("visible_state") or {}
    actions = view.get("actions") or []
    kinds = collections.Counter(action.get("action_type") for action in actions)
    claims = [action for action in actions
              if action.get("action_type") in ("peng", "chi")]
    if not claims:
        return None

    def claim_key(action):
        shanten = action.get("shanten_after")
        support = support_of(action)
        return (shanten if type(shanten) is int else 99,
                -(support if support is not None else -1),
                action.get("action_key") or "")

    best_claim = min(claims, key=claim_key)
    passes = [action for action in actions if action.get("action_type") == "pass"]
    discards = [action for action in actions if action.get("action_type") == "discard"]
    if passes:
        before_shanten = passes[0].get("shanten_after")
        before_support = support_of(passes[0])
    elif discards:
        ranked = sorted(discards, key=claim_key)
        before_shanten = ranked[0].get("shanten_after")
        before_support = support_of(ranked[0])
    else:
        return None
    if type(before_shanten) is not int:
        return None

    after_shanten = best_claim.get("shanten_after")
    after_support = support_of(best_claim)
    if type(after_shanten) is not int or before_support is None or after_support is None:
        return None

    seat = visible.get("seat")
    melds = visible.get("melds") or ()
    rivers = visible.get("discards") or ()
    last = visible.get("last_discard") or {}
    tile = last.get("tile") or ""
    wall = visible.get("remaining_tile_count")
    delta_sh = after_shanten - before_shanten
    delta_w = after_support - before_support
    meld_count = len(melds[seat]) if seat is not None and seat < len(melds) else 0
    turn = len(rivers[seat]) if seat is not None and seat < len(rivers) else 0
    return {
        "sh": before_shanten,
        "fam": "peng" if kinds.get("peng") else "chi",
        "dsh": "down" if delta_sh < 0 else ("same" if delta_sh == 0 else "up"),
        "dw": "wider" if delta_w > 0 else ("equal" if delta_w == 0 else "narrower"),
        "ml": "m0" if meld_count == 0 else ("m1" if meld_count == 1 else "m2p"),
        "tn": "t0_2" if turn <= 2 else ("t3_6" if turn <= 6 else "t7p"),
        "wl": ("unknown" if type(wall) is not int else
               ("w60p" if wall >= 60 else ("w40_59" if wall >= 40 else "wlt40"))),
        "tc": "number" if tile[:1] in tuple("123456789") else "honor",
        "bt": "yes" if best_claim.get("baotou_after") is True else "no",
    }


def main(argv) -> int:
    if not argv:
        print("用法: c27_reach_cells.py <候选源码路径> [更多路径...]")
        return 2

    namespace = {"__name__": "frozen"}
    exec(compile(p6_lib.frozen_source(), "frozen", "exec"), namespace)
    parent = namespace["score_actions"]

    candidates, rejected = [], []
    for raw in argv:
        path = Path(raw)
        try:
            ActionValueScorer("research:" + path.stem, path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            rejected.append((path.name, type(exc).__name__ + ": " + str(exc)[:90]))
            continue
        candidates.append((path.name, p6_lib.compile_candidate(path)))
    if rejected:
        print("未通过静态合同（不计入可达性）：")
        for name, why in rejected:
            print("  %s — %s" % (name, why))
    if not candidates:
        print("全部候选未通过静态合同。")
        return 3

    stats = {name: collections.Counter() for name, _ in candidates}
    by_cell = {name: collections.defaultdict(collections.Counter)
               for name, _ in candidates}
    cell_windows = collections.Counter()
    changed_windows = {name: collections.Counter() for name, _ in candidates}
    for row in p6_lib.iter_rooms(p6_lib.ROOMS_PRIMARY + p6_lib.ROOMS_EXTRA):
        view = row["view"]
        feature = view_feature(view)
        if feature is not None:
            labels = C27C.cells(feature)
            for key in labels.values():
                cell_windows[key] += 1
        else:
            labels = {}
        try:
            parent_entry = chosen_entry(parent(view)["entries"])
            baseline = parent_entry["action_key"]
            baseline_shanten = shanten_of(parent_entry)
        except Exception:  # noqa: BLE001
            baseline = row["plan_rank1"]
            baseline_shanten = None
        for name, scorer in candidates:
            stats[name]["windows"] += 1
            try:
                out = scorer(view)
            except Exception:  # noqa: BLE001
                stats[name]["error"] += 1
                continue
            if out.get("status") != "SCORED":
                stats[name]["abstain"] += 1
                continue
            entry = chosen_entry(out["entries"])
            if entry["action_key"] == baseline:
                continue
            stats[name]["changed"] += 1
            candidate_shanten = shanten_of(entry)
            bucket = by_cell[name]
            if (baseline_shanten is not None and candidate_shanten is not None
                    and candidate_shanten > baseline_shanten):
                stats[name]["worse_shanten"] += 1
                verdict = "worse"
            elif (baseline_shanten is not None and candidate_shanten is not None
                  and candidate_shanten < baseline_shanten):
                stats[name]["better_shanten"] += 1
                verdict = "better"
            elif baseline_shanten is None or candidate_shanten is None:
                stats[name]["unknown_shanten"] += 1
                verdict = "unknown"
            else:
                stats[name]["same_shanten"] += 1
                verdict = "same"
            for key in labels.values():
                changed_windows[name][key] += 1
                bucket[key][verdict] += 1

    print()
    print("| 候选 | 窗口 | 改选 | 改选率 | 过 10% 全局门 | 改到更慢向听 | 更快 | 不变 | 未知 | 异常 | 弃权 |")
    print("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for name, _ in candidates:
        item = stats[name]
        windows = max(1, item["windows"])
        rate = 100.0 * item["changed"] / windows
        print("| %s | %d | %d | %.2f%% | %s | %d | %d | %d | %d | %d | %d |"
              % (name, item["windows"], item["changed"], rate,
                 "是" if rate >= 10.0 else "否",
                 item["worse_shanten"], item["better_shanten"], item["same_shanten"],
                 item["unknown_shanten"], item["error"], item["abstain"]))

    claim_windows = sum(cell_windows[key] for key in ("F2:peng", "F2:chi"))
    print()
    print("有碰/吃候选的窗口 %d（占全部 %.2f%%）—— 全局改选率的结构上界"
          % (claim_windows, 100.0 * claim_windows / max(1, stats[candidates[0][0]]["windows"])))

    for name, _ in candidates:
        print()
        print("== %s：分格改选率（窗口数 >= 20 的格；四个向听列）" % name)
        print("| 格 | 窗口 | 改选 | 格内改选率 | 更慢向听 | 更快 | 不变 | 未知 |")
        print("| --- | --- | --- | --- | --- | --- | --- | --- |")
        keys = [key for key in sorted(cell_windows) if cell_windows[key] >= 20]
        for key in keys:
            windows = cell_windows[key]
            changed = changed_windows[name][key]
            item = by_cell[name][key]
            print("| %s | %d | %d | %.2f%% | %d | %d | %d | %d |"
                  % (key, windows, changed, 100.0 * changed / windows,
                     item["worse"], item["better"], item["same"], item["unknown"]))

    payload = {
        "windows": stats[candidates[0][0]]["windows"],
        "claim_windows": claim_windows,
        "cell_windows": dict(cell_windows),
        "candidates": {
            name: {
                "stats": dict(stats[name]),
                "changed_by_cell": dict(changed_windows[name]),
                "verdict_by_cell": {key: dict(value)
                                    for key, value in by_cell[name].items()},
            }
            for name, _ in candidates
        },
        "rejected": rejected,
    }
    (_project_file(_PROJECT_ROOT, ROOT / ".team-work" / "c27-claim-cells" / "reach-cells.json")).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8")
    print()
    print("结果写入 %s" % (_project_file(_PROJECT_ROOT, ROOT / ".team-work" / "c27-claim-cells" / "reach-cells.json")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
