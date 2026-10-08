#!/usr/bin/env python3
"""C32 分格可达性：格内改选率 + 改选类型拆分（鸣/过翻转 vs 鸣牌首选换位）。

与 c27_reach_cells.py 同一口径（同一 p6 生产视图、同一 C27 第一步格定义、同一
l1_reach 首选序），但**写自己的产物**（.team-work/c32-cards/reach-cells.json），
不覆盖 C27 的 .team-work/c27-claim-cells/reach-cells.json。

新增两列（回答任务书第三节「额外改选数与因由」所需的拆分）：
* claim_flip：父代首选与候选首选在「是否鸣牌」上不同（真正的鸣/过翻转）；
* pick_swap：两侧都鸣但首选鸣牌候选不同（同族换位）。
全局分母 32 374，只有 2 181 个窗口带碰/吃候选 ⇒ 判定看**格内改选率**（C27 第 7.3 节）。

用法：
    UV_CACHE_DIR=/tmp/uv-cache .venv/bin/python \
        review/freematch-deep-dive-20260925/c32_reach_cells.py
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

import c27_claim_cells as C27C  # noqa: E402
import p6_lib  # noqa: E402

from hangma_bot.policy.action_value_seeds import ActionValueScorer  # noqa: E402

OUT = _project_file(_PROJECT_ROOT, ROOT / ".team-work" / "c32-cards")
CAND = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/candidates')
CLAIM_TYPES = ("peng", "chi", "gang")
FILES = ("OPTY-R18-C27-CELL-R6.py",
         "OPTY-R18-C32-DOSE-C6K6.py",
         "OPTY-R18-C32-DOSE-C6K3.py",
         "OPTY-R18-C32-DOSE-C6K9.py",
         "OPTY-R18-C32-RERANK-R6.py",
         "OPTY-R18-C32-DOSE-C6-TENPAI.py",
         "OPTY-R18-C32-AUDIT-TENPAI9.py")


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
    """父代 view → C27 第一步的 9 个特征（与 c27_reach_cells.view_feature 逐字同构）。"""

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


def kind_of(key):
    return "claim" if key and key.split(":")[0] in CLAIM_TYPES else "other"


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    namespace = {"__name__": "frozen"}
    exec(compile(p6_lib.frozen_source(), "frozen", "exec"), namespace)
    parent = namespace["score_actions"]
    candidates, rejected = [], []
    for file_name in FILES:
        path = _project_file(_PROJECT_ROOT, CAND / file_name)
        if not path.exists():
            rejected.append((file_name, "缺文件"))
            continue
        source = path.read_text(encoding="utf-8")
        try:
            ActionValueScorer("research:" + path.stem, source)
        except Exception as exc:  # noqa: BLE001
            rejected.append((file_name, type(exc).__name__ + ": " + str(exc)[:90]))
            continue
        candidates.append((file_name[:-3], p6_lib.compile_candidate(path)))
    if rejected:
        print("未通过静态合同（不计入可达性）：%s" % rejected)

    stats = {name: collections.Counter() for name, _ in candidates}
    by_cell = {name: collections.defaultdict(collections.Counter) for name, _ in candidates}
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
            item = stats[name]
            item["windows"] += 1
            try:
                out = scorer(view)
            except Exception:  # noqa: BLE001
                item["error"] += 1
                continue
            if out.get("status") != "SCORED":
                item["abstain"] += 1
                continue
            entry = chosen_entry(out["entries"])
            if entry["action_key"] == baseline:
                continue
            item["changed"] += 1
            if kind_of(entry["action_key"]) != kind_of(baseline):
                item["claim_flip"] += 1
                verdict_kind = "claim_flip"
            else:
                item["pick_swap"] += 1
                verdict_kind = "pick_swap"
            cand_shanten = shanten_of(entry)
            if (baseline_shanten is not None and cand_shanten is not None
                    and cand_shanten > baseline_shanten):
                item["worse_shanten"] += 1
                verdict = "worse"
            elif (baseline_shanten is not None and cand_shanten is not None
                  and cand_shanten < baseline_shanten):
                item["better_shanten"] += 1
                verdict = "better"
            elif baseline_shanten is None or cand_shanten is None:
                item["unknown_shanten"] += 1
                verdict = "unknown"
            else:
                item["same_shanten"] += 1
                verdict = "same"
            for key in labels.values():
                changed_windows[name][key] += 1
                by_cell[name][key][verdict] += 1
                by_cell[name][key][verdict_kind] += 1

    print()
    print("| 候选 | 窗口 | 改选 | 改选率 | 鸣/过翻转 | 鸣牌首选换位 | 改到更慢向听 | 更快 | 不变 | 未知 | 异常 |")
    print("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    payload = {"windows": stats[candidates[0][0]]["windows"] if candidates else 0,
               "rejected": rejected, "cell_windows": dict(cell_windows), "candidates": {}}
    for name, _ in candidates:
        item = stats[name]
        windows = max(1, item["windows"])
        rate = 100.0 * item["changed"] / windows
        payload["candidates"][name] = {
            "stats": dict(item), "changed_by_cell": dict(changed_windows[name]),
            "verdict_by_cell": {key: dict(value) for key, value in by_cell[name].items()},
        }
        print("| %s | %d | %d | %.2f%% | %d | %d | %d | %d | %d | %d | %d |"
              % (name, item["windows"], item["changed"], rate, item["claim_flip"],
                 item["pick_swap"], item["worse_shanten"], item["better_shanten"],
                 item["same_shanten"], item["unknown_shanten"], item["error"]))

    print()
    print("== 判定格 F3:same 的格内改选率（C27 第 7.3 节判定列）")
    print("| 候选 | F3:same 窗口 | 改选 | 格内改选率 | 鸣/过翻转 | 换位 | ≥10% |")
    print("| --- | --- | --- | --- | --- | --- | --- |")
    for name, _ in candidates:
        windows = cell_windows.get("F3:same", 0)
        changed = changed_windows[name].get("F3:same", 0)
        entry = by_cell[name].get("F3:same", {})
        rate = 100.0 * changed / max(1, windows)
        payload["candidates"][name]["cell_rate_F3same"] = rate
        print("| %s | %d | %d | %.2f%% | %d | %d | %s |"
              % (name, windows, changed, rate, entry.get("claim_flip", 0),
                 entry.get("pick_swap", 0), "是" if rate >= 10.0 else "否"))

    print()
    print("== 各候选改选窗的格落点（窗口数 >= 20 的格）")
    for name, _ in candidates:
        keys = [key for key in sorted(cell_windows)
                if cell_windows[key] >= 20 and changed_windows[name].get(key)]
        if not keys:
            continue
        print("  [%s] %s" % (name, "；".join(
            "%s %d/%d=%.2f%%" % (key, changed_windows[name][key], cell_windows[key],
                                 100.0 * changed_windows[name][key] / cell_windows[key])
            for key in keys)))

    (_project_file(_PROJECT_ROOT, OUT / "reach-cells.json")).write_text(json.dumps(payload, ensure_ascii=False, indent=2,
                                                     default=str), encoding="utf-8")
    print()
    print("结果写入 %s" % (_project_file(_PROJECT_ROOT, OUT / "reach-cells.json")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
