#!/usr/bin/env python3
"""C33 可达性逐窗解剖：新事实改到哪些窗、与动作层信号是否同一批、剂量缺口分布。

用途（只读）：回答「新事实相对旧的可得信号到底多买了什么」，并给出下一轮该造什么
候选的数据依据。视图 = p6 生产真实视图 + C33 新字段（只加键，见 p6_lib 桥）。

用法：
    cd /Users/liyang/hangma-bot/.team-work/c33-fact-exposure
    PYTHONPATH=$PWD/src /Users/liyang/hangma-bot/.venv/bin/python \
        review/freematch-deep-dive-20260925/c33_reach_cells.py
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
HERE = Path(__file__).resolve().parent
MAIN_TREE = _PROJECT_ROOT
sys.path.insert(0, str(_project_file(_PROJECT_ROOT, ROOT / ".team-work" / "p6-baotou-route")))
sys.path.insert(0, str(_project_file(_PROJECT_ROOT, ROOT / "src")))
sys.path.insert(0, str(HERE))

import p6_lib  # noqa: E402
from hangma_bot.policy.action_value_seeds import ActionValueScorer  # noqa: E402

CLAIM_TYPES = ("chi", "peng")
CAND_DIR = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/candidates')
ARMS = {
    "main": _project_file(_PROJECT_ROOT, CAND_DIR / "OPTY-R18-C33-FOLLOWUP-BAOTOU.py"),
    "negctrl": _project_file(_PROJECT_ROOT, CAND_DIR / "OPTY-R18-C33-NEGCTRL-MISSINGKEY.py"),
    "audit_action_layer": _project_file(_PROJECT_ROOT, CAND_DIR / "OPTY-R18-C33-AUDIT-ACTIONLAYER.py"),
}


def chosen(entries):
    return min(entries, key=lambda item: (-float(item["score"]), item["action_key"]))


def main() -> int:
    namespace = {"__name__": "c33_frozen"}
    exec(compile(p6_lib.frozen_source(), "frozen", "exec"), namespace)
    parent = namespace["score_actions"]
    scorers = {"parent": parent}
    for name, path in ARMS.items():
        source = path.read_text(encoding="utf-8")
        ActionValueScorer("research:" + path.stem, source)
        scorers[name] = p6_lib.compile_candidate(path)

    windows = 0
    claim_windows = 0
    changed = {name: set() for name in ARMS}
    features = {}
    picks_by_index = {}
    bins = collections.Counter()
    for index, row in enumerate(p6_lib.iter_rooms(p6_lib.ROOMS_PRIMARY + p6_lib.ROOMS_EXTRA)):
        view = row["view"]
        windows += 1
        picks = {}
        for name, scorer in scorers.items():
            out = scorer(view)
            picks[name] = (chosen(out["entries"])["action_key"]
                           if out.get("status") == "SCORED" and out.get("entries") else None)
        scores = {item["action_key"]: float(item["score"])
                  for item in parent(view)["entries"]}
        claims = [item for item in view["actions"]
                  if item["action_type"] in CLAIM_TYPES and item["action_key"] in scores]
        if not claims:
            continue
        claim_windows += 1
        passes = [item for item in view["actions"]
                  if item["action_type"] == "pass" and item["action_key"] in scores]
        best = min(claims, key=lambda item: (-scores[item["action_key"]],
                                             item["action_key"]))
        margin = (None if not passes
                  else scores[best["action_key"]] - scores[passes[0]["action_key"]])
        dosed = [item for item in claims if item.get("followup_baotou") is True]
        feature = {
            "room": row.get("room"), "game_id": row.get("game_id"),
            "round_no": row.get("round_no"), "trigger_seq": row.get("trigger_seq"),
            "seat": view["visible_state"]["seat"], "claim": best["action_key"],
            "claim_type": best["action_type"], "margin": margin,
            "followup_baotou": best.get("followup_baotou"),
            "action_layer_baotou": best.get("baotou_after"),
            "followup_shanten": best.get("followup_shanten"),
            "followup_support": best.get("followup_support"),
            "dosed": [item["action_key"] for item in dosed],
            "dosed_invisible_at_action_layer": [
                item["action_key"] for item in dosed
                if item.get("baotou_after") is not True],
        }
        features[index] = feature
        picks_by_index[index] = dict(picks)
        if dosed:
            bins["windows_with_dosed_claim"] += 1
            if feature["dosed_invisible_at_action_layer"]:
                bins["windows_dosed_invisible_at_action_layer"] += 1
            for item in dosed:
                own = scores[item["action_key"]]
                rivals = [value for key, value in scores.items() if key != item["action_key"]]
                rival = max(rivals or [-1e9])
                dose = 6.0 if item["action_type"] == "peng" else 10.0
                gap = rival - own
                # 父代取首选：分数降序、action_key 升序兜底。gap < 0 = 该候选已是首选；
                # gap == 0 = 与对手同分但键更大（父代把首选给了对手）；
                # 0 < gap < dose = 剂量够；gap == dose = 加完还是同分（键序仍输）；
                # gap > dose = 剂量不够（增量需要更大剂量或另一套价值定义）。
                if gap < 0.0:
                    bucket = "already_pick_strict"
                elif gap == 0.0:
                    bucket = "tied_rival_wins_by_key"
                elif dose > gap:
                    bucket = "dose_flips_pick"
                elif dose == gap:
                    bucket = "dose_exactly_ties_again"
                else:
                    bucket = "dose_too_small"
                bins["dosed_" + bucket] += 1
                bins["gap_" + ("lt0" if gap < 0 else "eq0" if gap == 0
                               else "le6" if gap <= 6.0 else "le10" if gap <= 10.0
                               else "le20" if gap <= 20.0 else "gt20")] += 1
                if item.get("baotou_after") is not True:
                    bins["invisible_" + bucket] += 1
                    if gap > 0.0:
                        bins["invisible_gap_le_dose" if gap <= dose
                             else "invisible_gap_gt_dose"] += 1
                if item.get("baotou_after") is not True:
                    if gap <= 0.0:
                        bins["invisible_dosed_already_pick"] += 1
                    elif dose > gap:
                        bins["invisible_dosed_dose_flips_pick"] += 1
                    else:
                        bins["invisible_dosed_dose_too_small"] += 1
        for name in ARMS:
            if picks[name] is not None and picks["parent"] is not None and \
                    picks[name] != picks["parent"]:
                changed[name].add(index)

    payload = {
        "windows": windows,
        "claim_windows": claim_windows,
        "changed": {
            name: {
                "changed": len(changed[name]),
                "invisible_at_action_layer": len([
                    idx for idx in changed[name]
                    if features.get(idx, {}).get("dosed_invisible_at_action_layer")]),
                "new_baotou_true": len([
                    idx for idx in changed[name]
                    if features.get(idx, {}).get("followup_baotou") is True]),
                "windows": [dict(features[idx],
                                 pick=picks_by_index.get(idx, {}).get(name),
                                 parent_pick=picks_by_index.get(idx, {}).get("parent"))
                            for idx in sorted(changed[name])][:40],
            }
            for name in ARMS
        },
        "changed_sets": {
            "main_equals_audit": changed["main"] == changed["audit_action_layer"],
            "main_only": len(changed["main"] - changed["audit_action_layer"]),
            "audit_only": len(changed["audit_action_layer"] - changed["main"]),
        },
        "dose_gap_bins": dict(bins),
    }
    out = _project_file(_PROJECT_ROOT, ROOT / ".team-work" / "c33-fact-exposure" / "reach-cells.json")
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print("窗 %d；含鸣牌候选窗 %d" % (windows, claim_windows))
    for name in ARMS:
        box = payload["changed"][name]
        print("臂 %-20s 改选 %3d（其中动作层看不见 %d；新口径爆头为真 %d）"
              % (name, box["changed"], box["invisible_at_action_layer"],
                 box["new_baotou_true"]))
    print("主臂 vs 动作层臂：集合相同=%s；主臂独有 %d；动作层独有 %d"
          % (payload["changed_sets"]["main_equals_audit"],
             payload["changed_sets"]["main_only"],
             payload["changed_sets"]["audit_only"]))
    print("剂量缺口分箱（逐「被给剂量的候选」）：%s" % json.dumps(dict(bins), ensure_ascii=False))
    print("写入 %s" % out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
