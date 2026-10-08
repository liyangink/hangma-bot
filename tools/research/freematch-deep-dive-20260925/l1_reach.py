#!/usr/bin/env python3
"""L1 可达性门槛：用**真实候选源码**在真实观察上测首选改选率。

为什么必须用真实源码：2026-09-25 我用简化公式代理测 P7，得到 10.15%，
而真实候选源码只有 3.16%——差 3 倍，导致一个够不到门槛的候选进了完整桌。
本脚本统一走 P6 分析者留下的 p6_lib（真实 view 构造 + 真实父代重算），
任何 r18 源码变体都能零成本测。

门槛：改选率 < 10% 不进入完整桌预算。

用法：
    .venv/bin/python review/freematch-deep-dive-20260925/l1_reach.py \
        review/freematch-deep-dive-20260925/candidates/OPTY-R18-C06-ROUTEVALUE*.py
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
import sys
from pathlib import Path

ROOT = _PROJECT_ROOT
P6 = _project_file(_PROJECT_ROOT, ROOT / ".team-work" / "p6-baotou-route")
sys.path.insert(0, str(P6))

import p6_lib  # noqa: E402

GATE = 10.0


def main(argv) -> int:
    if not argv:
        print("用法: l1_reach.py <候选源码路径> [更多路径...]")
        return 2

    namespace = {"__name__": "frozen"}
    exec(compile(p6_lib.frozen_source(), "frozen", "exec"), namespace)
    parent = namespace["score_actions"]

    # 静态合同必须在这里先过一遍：p6_lib.compile_candidate 只做 exec，
    # 不跑 ActionValueScorer 的只读白名单与赋值目标检查。2026-09-25 因此出过
    # 一次错——154 个候选全部报出 10%–12% 的改选率，却一个都装不进真实策略路径
    # （.remove 不在只读白名单、下标赋值被拒）。改选率必须建立在可装载之上。
    sys.path.insert(0, str(_project_file(_PROJECT_ROOT, ROOT / "src")))
    from hangma_bot.policy.action_value_seeds import ActionValueScorer

    candidates = []
    rejected = []
    for raw in argv:
        path = Path(raw)
        try:
            ActionValueScorer("research:" + path.stem, path.read_text(encoding="utf-8"))
        except Exception as exc:
            rejected.append((path.name, type(exc).__name__ + ": " + str(exc)[:90]))
            continue
        candidates.append((path.name, p6_lib.compile_candidate(path)))

    if rejected:
        print("未通过静态合同（不计入可达性）：")
        for name, why in rejected:
            print("  %s — %s" % (name, why))
        print()
    if not candidates:
        print("全部候选未通过静态合同，无可达性可测。")
        return 3

    def chosen_entry(entries):
        """与 p6_lib.pick 同序（分数降序、action_key 升序兜底）取整个 entry。

        需要 entry 而不只是 action_key，是为了读 trace.shanten_after——
        「改到更慢向听」必须与改选率一起报，否则会把「换了个更慢的打法」
        误读成「换了个更好的打法」。
        """

        return min(entries, key=lambda e: (-float(e["score"]), e["action_key"]))


    def shanten_of(entry):
        """读该候选 trace 里的向听数。

        注意：字段名不统一——发布父代与 R18 变体用 `shanten_after`，
        而 action_value 种子（route_value_seed 等）用 `combined_shanten`。
        2026-09-25 因此出过一次静默误报：种子候选的该列为 0，
        看起来像「零速度牺牲」，实际是字段缺失被当成「无退化」。
        两个键都读不到时返回 None，并单独计数（`unknown_shanten`），
        不再计入「相同或未知」。
        """

        trace = entry.get("trace") or {}
        for key in ("shanten_after", "combined_shanten", "shanten"):
            value = trace.get(key)
            if type(value) is int:
                return value
        return None


    stats = {name: collections.Counter() for name, _ in candidates}
    for row in p6_lib.iter_rooms(p6_lib.ROOMS_PRIMARY + p6_lib.ROOMS_EXTRA):
        view = row["view"]
        try:
            parent_entry = chosen_entry(parent(view)["entries"])
            baseline = parent_entry["action_key"]
            baseline_shanten = shanten_of(parent_entry)
        except Exception:
            baseline = row["plan_rank1"]
            baseline_shanten = None
        for name, scorer in candidates:
            stats[name]["windows"] += 1
            try:
                out = scorer(view)
            except Exception:
                stats[name]["error"] += 1
                continue
            if out.get("status") != "SCORED":
                stats[name]["abstain"] += 1
                continue
            entry = chosen_entry(out["entries"])
            if entry["action_key"] != baseline:
                stats[name]["changed"] += 1
                candidate_shanten = shanten_of(entry)
                if (baseline_shanten is not None and candidate_shanten is not None
                        and candidate_shanten > baseline_shanten):
                    stats[name]["worse_shanten"] += 1
                elif (baseline_shanten is not None and candidate_shanten is not None
                      and candidate_shanten < baseline_shanten):
                    stats[name]["better_shanten"] += 1
                elif baseline_shanten is None or candidate_shanten is None:
                    stats[name]["unknown_shanten"] += 1
                else:
                    stats[name]["same_shanten"] += 1

    print("| 候选 | 窗口 | 改选 | 改选率 | 过 %g%% 门 | 改到更慢向听 | 改到更快向听 | 向听未知 | 异常 |" % GATE)
    print("| --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for name, _ in candidates:
        s = stats[name]
        windows = max(1, s["windows"])
        rate = 100.0 * s["changed"] / windows
        print("| %s | %d | %d | %.2f%% | %s | %d | %d | %d | %d |"
              % (name, s["windows"], s["changed"], rate,
                 "是" if rate >= GATE else "否",
                 s["worse_shanten"], s["better_shanten"],
                 s["unknown_shanten"], s["error"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))