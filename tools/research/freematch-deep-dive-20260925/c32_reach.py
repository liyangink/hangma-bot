#!/usr/bin/env python3
"""C32 第一级验证：可达改选、相对 CELL-R6 的额外改选与新窗审计、1 秒响应窗开销。

用**真实候选源码**在**生产真实视图**上测（口径与 l1_reach.py 一致：分数降序、
action_key 升序兜底取首选；「改到更慢向听」必须为 0）。视图取自 p6 生产视图缓存
（冻结 R18 v2 战役的 32 374 个真实响应窗口），只读。

本脚本只做第一级验证：不跑完整桌、不发网络请求。

用法：
    UV_CACHE_DIR=/tmp/uv-cache .venv/bin/python \
        review/freematch-deep-dive-20260925/c32_reach.py
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
import statistics
import sys
import time
from pathlib import Path

ROOT = _PROJECT_ROOT
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_project_file(_PROJECT_ROOT, ROOT / "src")))
sys.path.insert(0, str(_project_file(_PROJECT_ROOT, ROOT / ".team-work" / "p6-baotou-route")))
sys.path.insert(0, str(HERE))

import p6_lib  # noqa: E402
from hangma_bot.policy.action_value_seeds import ActionValueScorer  # noqa: E402

OUT = _project_file(_PROJECT_ROOT, ROOT / ".team-work" / "c32-cards")
CAND_DIR = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/candidates')

CANDIDATES = collections.OrderedDict((
    ("R6", "OPTY-R18-C27-CELL-R6.py"),
    ("V1-DOSE-C6K6", "OPTY-R18-C32-DOSE-C6K6.py"),
    ("V1-DOSE-C6K3", "OPTY-R18-C32-DOSE-C6K3.py"),
    ("V1-DOSE-C6K9", "OPTY-R18-C32-DOSE-C6K9.py"),
    ("V2-RERANK-R6", "OPTY-R18-C32-RERANK-R6.py"),
    ("V3-DOSE-TENPAI", "OPTY-R18-C32-DOSE-C6-TENPAI.py"),
    ("AUDIT-TENPAI9", "OPTY-R18-C32-AUDIT-TENPAI9.py"),
))
CLAIM_TYPES = ("peng", "chi", "gang")
BASELINE = "PARENT"


def shanten_of(entry):
    """与 l1_reach.py 同一读法：trace 里的 shanten_after / combined_shanten / shanten。"""

    trace = entry.get("trace") or {}
    for key in ("shanten_after", "combined_shanten", "shanten"):
        value = trace.get(key)
        if type(value) is int:
            return value
    return None


def chosen_entry(entries):
    return min(entries, key=lambda item: (-float(item["score"]), item["action_key"]))


def width_of(action):
    """动作表里的有效牌未见张数之和；缺任何一张计数即 None（不猜零）。"""

    tiles = action.get("useful_tiles")
    if tiles is None:
        return None
    total = 0.0
    for item in tiles:
        remaining = item.get("remaining_estimate")
        if remaining is None or remaining is True or remaining is False:
            return None
        total += float(remaining)
    return total


def view_features(view, scores):
    """从父代动作表算该窗的公开特征（与 C27 的 F1/F3/F4 同一空间）。"""

    actions = view["actions"]
    claims = [item for item in actions
              if item["action_type"] in CLAIM_TYPES and item["action_key"] in scores]
    passes = [item for item in actions
              if item["action_type"] == "pass" and item["action_key"] in scores]
    feature = {"claims": len(claims), "types": sorted({item["action_type"] for item in claims})}
    if not claims or not passes:
        feature["margin"] = None
        return feature
    pas = passes[0]
    best = min(claims, key=lambda item: (-float(scores[item["action_key"]]),
                                         item["action_key"]))
    feature["margin"] = float(scores[best["action_key"]]) - float(scores[pas["action_key"]])
    feature["pass_shanten"] = pas.get("shanten_after")
    feature["claim_key"] = best["action_key"]
    feature["claim_type"] = best["action_type"]
    right = width_of(best)
    left = width_of(pas)
    feature["pass_W"] = left
    feature["claim_W"] = right
    feature["dw"] = (None if (left is None or right is None) else right - left)
    cl = best.get("shanten_after")
    feature["dsh"] = (None if (cl is None or isinstance(cl, bool)
                              or not isinstance(feature["pass_shanten"], int))
                      else cl - feature["pass_shanten"])
    visible = view["visible_state"]
    feature["melds"] = len(visible["melds"][visible["seat"]])
    feature["wall"] = visible.get("remaining_tile_count")
    feature["baotou_after"] = best.get("baotou_after")
    feature["followup"] = best.get("best_followup_discard")
    return feature


def classify(arm, feature):
    """给「相对 CELL-R6 的额外改选 / 被移除改选」贴可核因由（逐窗计算，非事后叙述）。"""

    dsh = feature.get("dsh")
    dw = feature.get("dw")
    margin = feature.get("margin")
    bs = feature.get("pass_shanten")
    melds = feature.get("melds")
    wall = feature.get("wall")
    if arm == "V2-RERANK-R6":
        if (melds is not None and melds >= 2) or (wall is not None and wall < 40):
            return "窗级门禁：现有副露 >= 2 或墙余 < 40"
        return "综合键最优候选不是父代首选（剂量改发给别家鸣牌候选）"
    if arm == "AUDIT-TENPAI9":
        return "本臂只覆盖听牌窗（过牌向听 0）且真实张数净增 >= 6"
    if arm == "V3-DOSE-TENPAI":
        return "本臂只覆盖 dsh==0 且真实张数净增 >= 6 的窗，或过牌向听 0 且净增 >= 6 的窗"
    if dw is None:
        return "真实张数不可核（缺 remaining_estimate）"
    if dw <= 0.0:
        return "真实张数未净增（dw <= 0）：本臂不给剂量"
    return "弱增益（0 < dw < k）只给 +3，且父代 margin <= -3"


def extra_reason(arm, feature):
    """本臂改选而 CELL-R6 未改选：新窗因由。"""

    dw = feature.get("dw")
    margin = feature.get("margin")
    bs = feature.get("pass_shanten")
    dsh = feature.get("dsh")
    if arm == "AUDIT-TENPAI9":
        if margin is not None and -9.0 < margin <= -6.0:
            return "父代 margin 在 (-9,-6]：需要 > +6 的剂量才越线（R6 的 +6 够不到）"
        return "听牌窗且净增 >= 6，但父代 margin 不在 (-9,-6]"
    if bs == 0 and dw is not None and dw >= 6.0 and dsh != 0:
        return "听牌窗（过牌向听 0）且真实张数净增 >= 6，且该候选 dsh != 0（R6 只给 dsh==0 剂量）"
    if margin is not None and -6.0 < margin <= 0.0:
        return "候选级剂量归属不同：R6 把 +6 发给另一候选，本臂发给了本候选"
    return "其它（逐窗登记，见 reach.json 的 extra_windows）"


def main():
    started = time.time()
    OUT.mkdir(parents=True, exist_ok=True)
    namespace = {"__name__": "c32_frozen_parent"}
    exec(compile(p6_lib.frozen_source(), "frozen", "exec"), namespace)
    parent = namespace["score_actions"]
    scorers = collections.OrderedDict(((BASELINE, parent),))
    static = {}
    rejected = []
    for name, file_name in CANDIDATES.items():
        path = _project_file(_PROJECT_ROOT, CAND_DIR / file_name)
        if not path.exists():
            rejected.append((name, "缺文件"))
            continue
        source = path.read_text(encoding="utf-8")
        try:
            ActionValueScorer("research:" + path.stem, source)   # 静态合同
        except Exception as exc:  # noqa: BLE001
            rejected.append((name, type(exc).__name__ + ": " + str(exc)[:80]))
            continue
        static[name] = "通过"
        scorers[name] = p6_lib.compile_candidate(path)
    print("静态合同：%s" % json.dumps(static, ensure_ascii=False))
    if rejected:
        print("未通过静态合同的候选（不计入可达性）：%s" % rejected)

    stats = {name: collections.Counter() for name in scorers}
    picks = {name: {} for name in scorers}
    changed_sets = {name: set() for name in scorers if name != BASELINE}
    times = {name: [] for name in scorers}
    features = {}
    illegal = collections.Counter()
    window_keys = {}
    index = -1
    for row in p6_lib.iter_rooms(p6_lib.ROOMS_PRIMARY + p6_lib.ROOMS_EXTRA):
        index += 1
        view = row["view"]
        legal_keys = {item["action_key"] for item in view["actions"]}
        window_keys[index] = [row.get("room"), row.get("game_id"), row.get("round_no"),
                              row.get("trigger_seq"), row.get("phase"), row.get("run_id")]
        parent_entries = None
        for name, scorer in scorers.items():
            mark = time.perf_counter()
            try:
                out = scorer(view)
            except Exception:  # noqa: BLE001
                times[name].append(time.perf_counter() - mark)
                stats[name]["error"] += 1
                continue
            times[name].append(time.perf_counter() - mark)
            stats[name]["windows"] += 1
            if out.get("status") != "SCORED":
                stats[name]["abstain"] += 1
                continue
            entries = out.get("entries") or []
            if not entries:
                stats[name]["empty"] += 1
                continue
            entry = chosen_entry(entries)
            picks[name][index] = entry["action_key"]
            if name != BASELINE and entry["action_key"] not in legal_keys:
                illegal[name] += 1
            if name == BASELINE:
                parent_entries = entries
                scores = {item["action_key"]: float(item["score"]) for item in entries}
                features[index] = view_features(view, scores)
                continue
            if parent_entries is None:
                continue
            base_entry = chosen_entry(parent_entries)
            if entry["action_key"] != base_entry["action_key"]:
                stats[name]["changed"] += 1
                changed_sets[name].add(index)
                base_shanten = shanten_of(base_entry)
                cand_shanten = shanten_of(entry)
                if base_shanten is not None and cand_shanten is not None:
                    if cand_shanten > base_shanten:
                        stats[name]["worse_shanten"] += 1
                    elif cand_shanten < base_shanten:
                        stats[name]["better_shanten"] += 1
                    else:
                        stats[name]["same_shanten"] += 1
                else:
                    stats[name]["unknown_shanten"] += 1
        if parent_entries is None:
            stats[BASELINE]["no_parent_plan"] += 1

    windows = stats[BASELINE]["windows"]
    print()
    print("== 可达性（真实生产视图 %d 窗；与 l1_reach.py 同一口径）" % windows)
    print("| 候选 | 窗口 | 改选 | 改选率 | 改到更慢向听 | 改到更快向听 | 向听不变 | 向听未知 | 异常 | 弃权 | 非法改选 |")
    print("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    table = {}
    for name in scorers:
        box = stats[name]
        rate = 100.0 * box["changed"] / max(1, box["windows"])
        table[name] = {"windows": box["windows"], "changed": box["changed"], "rate": rate,
                       "worse_shanten": box["worse_shanten"],
                       "better_shanten": box["better_shanten"],
                       "same_shanten": box["same_shanten"],
                       "unknown_shanten": box["unknown_shanten"], "error": box["error"],
                       "abstain": box["abstain"], "illegal": illegal.get(name, 0)}
        print("| %s | %d | %d | %.2f%% | %d | %d | %d | %d | %d | %d | %d |"
              % (name, box["windows"], box["changed"], rate, box["worse_shanten"],
                 box["better_shanten"], box["same_shanten"], box["unknown_shanten"],
                 box["error"], box["abstain"], illegal.get(name, 0)))

    print()
    print("== 相对 CELL-R6 的改选集合比较（逐窗可比）")
    base_set = changed_sets.get("R6", set())
    comparison = {}
    for name in changed_sets:
        if name == "R6":
            continue
        extra = changed_sets[name] - base_set
        removed = base_set - changed_sets[name]
        swapped = {idx for idx in (changed_sets[name] & base_set)
                   if picks[name].get(idx) != picks["R6"].get(idx)}
        reason_extra = collections.Counter(extra_reason(name, features.get(idx, {}))
                                           for idx in extra)
        reason_removed = collections.Counter(classify(name, features.get(idx, {}))
                                             for idx in removed)
        comparison[name] = {
            "changed_vs_parent": len(changed_sets[name]), "r6_changed": len(base_set),
            "extra_vs_r6": len(extra), "removed_vs_r6": len(removed),
            "same_set_new_pick": len(swapped),
            "extra_reasons": dict(reason_extra), "removed_reasons": dict(reason_removed),
            "extra_windows": [
                {"key": window_keys.get(idx), "feature": features.get(idx),
                 "pick": picks[name].get(idx), "r6_pick": picks["R6"].get(idx),
                 "reason": extra_reason(name, features.get(idx, {}))}
                for idx in sorted(extra)[:40]],
            "removed_windows": [
                {"key": window_keys.get(idx), "feature": features.get(idx),
                 "pick": picks[name].get(idx), "r6_pick": picks["R6"].get(idx),
                 "reason": classify(name, features.get(idx, {}))}
                for idx in sorted(removed)[:20]],
        }
        print("  %-16s 改选(父代) %5d｜R6 改选 %5d｜额外 %4d｜移除 %4d｜同窗换首选 %4d"
              % (name, len(changed_sets[name]), len(base_set), len(extra), len(removed),
                 len(swapped)))
        for reason, count in reason_extra.most_common():
            print("      额外因由：%s × %d" % (reason, count))
        for reason, count in reason_removed.most_common():
            print("      移除因由：%s × %d" % (reason, count))

    print()
    print("== 1 秒响应窗开销（同一批真实视图；离线重算，线上另有共享的规则分析段）")
    timing = {}
    print("| 打分器 | p50 (ms) | p99 (ms) | max (ms) | 均值 (ms) | 相对父代 p99 增量 (ms) | 占 1000 ms |")
    print("| --- | ---: | ---: | ---: | ---: | ---: | ---: |")
    base_p99 = None
    for name in scorers:
        samples = sorted(times[name])
        if not samples:
            continue
        p50 = statistics.median(samples)
        p99 = samples[min(len(samples) - 1, int(0.99 * len(samples)))]
        worst = samples[-1]
        mean = statistics.fmean(samples)
        if name == BASELINE:
            base_p99 = p99
        delta = None if base_p99 is None else (p99 - base_p99) * 1000.0
        timing[name] = {"p50_ms": p50 * 1000, "p99_ms": p99 * 1000, "max_ms": worst * 1000,
                        "mean_ms": mean * 1000, "n": len(samples),
                        "delta_p99_vs_parent_ms": delta, "p99_share_of_1s": p99}
        print("| %s | %.3f | %.3f | %.3f | %.3f | %s | %.4f%% |"
              % (name, p50 * 1000, p99 * 1000, worst * 1000, mean * 1000,
                 "-" if delta is None else "%.3f" % delta, 100.0 * p99))

    payload = {"windows": windows, "static_contract": static, "rejected": rejected,
               "reach": table, "comparison_vs_r6": comparison, "timing": timing,
               "new_windows_total": {name: entry["extra_vs_r6"]
                                     for name, entry in comparison.items()},
               "elapsed_sec": time.time() - started}
    (_project_file(_PROJECT_ROOT, OUT / "reach.json")).write_text(json.dumps(payload, ensure_ascii=False, indent=2,
                                               default=str), encoding="utf-8")
    (_project_file(_PROJECT_ROOT, OUT / "timing.json")).write_text(json.dumps(timing, ensure_ascii=False, indent=2),
                                     encoding="utf-8")
    print()
    print("结果写入 %s 与 %s；总用时 %.1f 秒"
          % (_project_file(_PROJECT_ROOT, OUT / "reach.json"), _project_file(_PROJECT_ROOT, OUT / "timing.json"), time.time() - started))
    bad = sum(entry["worse_shanten"] for entry in table.values())
    print("第一级合法性检查：「改到更慢向听」合计 %d（必须 0）；非法改选合计 %d（必须 0）"
          % (bad, sum(illegal.values())))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
