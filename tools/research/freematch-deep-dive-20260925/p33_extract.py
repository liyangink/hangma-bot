#!/usr/bin/env python3
"""P33 步骤 1：把 P24 / P86-02 的既有逐桌配对结果与状态特征抽成可复跑的 CSV。

只读既有证据，不改任何既有文件；输出全部落在 .team-work/p33-deferral-heterogeneity/。

冻结口径（见 review/freematch-deep-dive-20260925/P33-PREREG-DEFERRAL-HETEROGENEITY.md）：
- 主变量 Δtable = 弃胡臂 − 立刻胡臂（分）。P24: intervention=盲弃胡/reference=立即胡，
  故 Δ = focal_current_table_score.delta；P86-02: intervention=立即胡/reference=父代弃胡，
  故 Δ = −focal_current_table_score.delta。
- 聚类单位 = 根（target_id / source_root_id），不是窗口、不是墙。
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

import csv
import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = _PROJECT_ROOT
EV = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution')
P24 = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p24-deferral-complement-01-20260925')
P86 = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p86-hu-deferral-development-teacher-02-20260925')
OUT = _project_file(_PROJECT_ROOT, ROOT / ".team-work/p33-deferral-heterogeneity")

BATCHES = {
    # batch: (result.json, rollouts dir, 弃胡臂名, 立刻胡臂名, Δ 符号, 逐墙数组键名)
    "P24": (_project_file(_PROJECT_ROOT, P24 / "teacher/result.json"), _project_file(_PROJECT_ROOT, P24 / "teacher/rollouts"), "intervention", "reference", +1,
            "fit_table_values", "recheck_table_values"),
    "P86-02": (_project_file(_PROJECT_ROOT, P86 / "result.json"), _project_file(_PROJECT_ROOT, P86 / "rollouts"), "reference", "intervention", -1,
               "fit_table_values", "future_wall_recheck_table_values"),
}


def sha16(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def load_walls(batch, result_path, rollout_dir, defer_arm, hu_arm, sign, fit_key, recheck_key):
    """逐墙配对行 + 机械核对。返回 (rows, verify)。"""
    result = json.loads(result_path.read_text(encoding="utf-8"))
    states = {s["target_id"]: s for s in result["states"]}
    rows = []
    verify = Counter()
    arrays = {fit_key: [], recheck_key: []}
    focal_by_target = defaultdict(set)
    dealer_by_target = defaultdict(set)
    for path in sorted(rollout_dir.glob("*.json")):
        d = json.loads(path.read_text(encoding="utf-8"))
        tid = d["target_id"]
        score = d["focal_current_table_score"]
        # 机械核对①：delta == intervention - reference
        if score["delta"] == score["intervention"] - score["reference"]:
            verify["delta_identity_ok"] += 1
        else:
            verify["delta_identity_bad"] += 1
        # 机械核对②：两臂各强制一次
        if d["force_count"][defer_arm] == 1 and d["force_count"][hu_arm] == 1:
            verify["force_ok"] += 1
        else:
            verify["force_bad"] += 1
        if d.get("mechanical_ok"):
            verify["mechanical_ok"] += 1
        else:
            verify["mechanical_bad"] += 1

        defer = d[defer_arm]
        hu = d[hu_arm]
        # 立刻胡臂的 winner_seat 就是焦点家的**物理座位**（source.focal_seat 是来源/日志座位号，二者不同）
        if hu["terminal"] == "focal_hu":
            focal_by_target[tid].add(hu["winner_seat"])
        dealer_by_target[tid].add(defer.get("dealer_seat"))
        rows.append(
            {
                "batch": batch,
                "target_id": tid,
                "root_id": states[tid]["source"]["source_root_id"],
                "wall_index": int(d["rollout_index"]),
                "delta_table_defer_minus_hu": sign * float(score["delta"]),
                "delta_round_defer_minus_hu": sign * float(d["focal_current_round_settlement_delta"]),
                "defer_terminal": defer["terminal"],
                "defer_fan": defer.get("fan"),
                "defer_settlement": defer.get("focal_settlement"),
                "hu_terminal": hu["terminal"],
                "hu_fan": hu.get("fan"),
                "hu_settlement": hu.get("focal_settlement"),
                "dealer_seat": defer.get("dealer_seat"),
                "round_no": defer.get("round_no"),
            }
        )
    # 机械核对③：与 result.json 的逐墙数组逐项相等
    for tid, st in states.items():
        vals = [r["delta_table_defer_minus_hu"] for r in rows if r["target_id"] == tid]
        fit = [r["delta_table_defer_minus_hu"] for r in rows if r["target_id"] == tid and r["wall_index"] <= 16]
        recheck = [r["delta_table_defer_minus_hu"] for r in rows if r["target_id"] == tid and r["wall_index"] > 16]
        # 冻结产物里的逐墙数组恒为「intervention − reference」方向（= sign * 本分析的 Δtable）
        arrays[fit_key].append((tid, [sign * v for v in fit] == [float(v) for v in st[fit_key]], len(vals)))
        arrays[recheck_key].append(
            (tid, [sign * v for v in recheck] == [float(v) for v in st[recheck_key]], len(vals))
        )
    verify["fit_arrays_match"] = sum(1 for _, ok, _ in arrays[fit_key] if ok)
    verify["recheck_arrays_match"] = sum(1 for _, ok, _ in arrays[recheck_key] if ok)
    verify["walls_per_target"] = sorted({n for _, _, n in arrays[fit_key]})
    # 每个状态的焦点物理座位与目标局庄位必须在它自己的 32 面墙上唯一
    verify["focal_seat_unique_targets"] = sum(1 for t, s in focal_by_target.items() if len(s) == 1)
    verify["dealer_seat_unique_targets"] = sum(1 for t, s in dealer_by_target.items() if len(s) == 1)
    verify["targets"] = len(states)
    focal_seat = {t: next(iter(s)) if len(s) == 1 else None for t, s in focal_by_target.items()}
    dealer_seat = {t: next(iter(s)) if len(s) == 1 else None for t, s in dealer_by_target.items()}
    return rows, verify, result, focal_seat, dealer_seat


def state_features(batch, result, rows, focal_seat, dealer_seat):
    """每个状态的公开特征（单位见预登记 §三）+ 由 512 面墙重算的两臂机制量。"""
    out = []
    per_target = defaultdict(list)
    for r in rows:
        per_target[r["target_id"]].append(r)
    for st in result["states"]:
        f = st["features"]
        trace = (f.get("hu_trace") or {}).get("hu_vs_nonwealth_baotou_cf", {}) or {}
        src = st["source"]
        tid = st["target_id"]
        phys = focal_seat.get(tid)
        walls = per_target[tid]
        hu_walls = [w for w in walls if w["hu_terminal"] == "focal_hu"]
        dfr_walls = [w for w in walls if w["defer_terminal"] == "focal_hu"]
        hu_fan = (st.get("immediate_hu_settlement") or {}).get("fan")
        if hu_fan is None:
            hu_fan = f.get("hu_fan") or trace.get("hu_fan")
        min_route = trace.get("min_route_fan")
        out.append(
            {
                "batch": batch,
                "target_id": st["target_id"],
                "root_id": src["source_root_id"],
                "mix": src["mix"],
                "source_focal_seat": src["focal_seat"],
                "focal_seat_physical": phys,
                "dealer_seat_physical": dealer_seat.get(tid),
                "is_dealer": int(dealer_seat.get(tid) == phys),
                "n_walls": len(walls),
                "hu_arm_hu_rate": len(hu_walls) / len(walls) if walls else None,
                "hu_arm_mean_fan": (
                    sum(w["hu_fan"] for w in hu_walls) / len(hu_walls) if hu_walls else None
                ),
                "hu_arm_settlement_mean": (
                    sum(w["hu_settlement"] for w in walls) / len(walls) if walls else None
                ),
                "defer_arm_hu_rate": len(dfr_walls) / len(walls) if walls else None,
                "defer_arm_mean_fan": (
                    sum(w["defer_fan"] for w in dfr_walls) / len(dfr_walls) if dfr_walls else None
                ),
                "defer_arm_settlement_mean": (
                    sum(w["defer_settlement"] for w in walls) / len(walls) if walls else None
                ),
                "remaining_tile_count": f.get("remaining_tile_count"),
                "round_no": f.get("round_no"),
                "own_meld_count": f.get("own_meld_count"),
                "other_meld_sum": sum(f.get("other_meld_counts") or []),
                "other_meld_counts": "|".join(str(x) for x in (f.get("other_meld_counts") or [])),
                "hu_fan": hu_fan,
                "hu_score": f.get("hu_score"),
                "useful_kinds": f.get("intervention_useful_kinds"),
                "wealth_count_in_hand": f.get("wealth_count_in_hand"),
                "baotou": f.get("baotou"),
                "route_fan": min_route,
                "route_over_hu_ratio": (min_route / hu_fan) if (min_route and hu_fan) else None,
                "hu_settlement_self": (
                    sum(w["hu_settlement"] for w in walls) / len(walls) if walls else None
                ),
                "defer_has_target": int(bool(min_route)),
            }
        )
    return out


def pool_rows():
    """覆盖率用池：P24（主池，无靶 1 番窗）与 P85（参考池，有靶弃胡窗）的去重合格行。"""
    sources = {
        "P24_pool": _project_file(_PROJECT_ROOT, P24 / "exposure/sources"),
        "P85_pool": _project_file(_PROJECT_ROOT, EV / "r18-p85-hu-deferral-natural-exposure-01-20260925/sources"),
    }
    rows = []
    for tag, folder in sources.items():
        for path in sorted(folder.glob("*.json")):
            d = json.loads(path.read_text(encoding="utf-8"))
            audit = d.get("audit") or {}
            for r in audit.get("eligible_rows") or []:
                f = r["features"]
                trace = (f.get("hu_trace") or {}).get("hu_vs_nonwealth_baotou_cf", {}) or {}
                focal = r.get("focal_physical_seat")
                rows.append(
                    {
                        "pool": tag,
                        "source_id": d["source"]["source_id"],
                        "root_id": d["source"]["source_root_id"],
                        "mix": d["source"]["mix"],
                        "focal_seat": focal,
                        "dealer_seat": f.get("dealer_seat"),
                        "is_dealer": int(f.get("dealer_seat") == focal),
                        "remaining_tile_count": f.get("remaining_tile_count"),
                        "round_no": f.get("round_no"),
                        "own_meld_count": f.get("own_meld_count"),
                        "other_meld_sum": sum(f.get("other_meld_counts") or []),
                        "hu_fan": trace.get("hu_fan") or f.get("hu_fan"),
                        "hu_score": f.get("hu_score"),
                        "useful_kinds": f.get("intervention_useful_kinds"),
                        "wealth_count_in_hand": f.get("wealth_count_in_hand"),
                        "route_fan": trace.get("min_route_fan"),
                        "baotou": f.get("baotou"),
                    }
                )
    return rows


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    log = []

    def say(msg):
        print(msg)
        log.append(msg)

    all_rows, all_states, verifies = [], [], {}
    for batch, (res_path, rollout_dir, defer_arm, hu_arm, sign, fit_key, recheck_key) in BATCHES.items():
        rows, verify, result, focal_seat, dealer_seat = load_walls(
            batch, res_path, rollout_dir, defer_arm, hu_arm, sign, fit_key, recheck_key
        )
        states = state_features(batch, result, rows, focal_seat, dealer_seat)
        verifies[batch] = dict(verify)
        all_rows.extend(rows)
        all_states.extend(states)
        say(f"[{batch}] 墙数={len(rows)} 状态数={len(states)} 机械核对={dict(verify)}")
        say(f"[{batch}] 冻结摘要 result.json={sha16(res_path)}")

    walls_path = _project_file(_PROJECT_ROOT, OUT / "paired_walls.csv")
    with open(walls_path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(all_rows[0].keys()))
        writer.writeheader()
        writer.writerows(all_rows)

    states_path = _project_file(_PROJECT_ROOT, OUT / "states.csv")
    with open(states_path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(all_states[0].keys()))
        writer.writeheader()
        writer.writerows(all_states)

    pool = pool_rows()
    pool_path = _project_file(_PROJECT_ROOT, OUT / "pool_rows.csv")
    with open(pool_path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(pool[0].keys()))
        writer.writeheader()
        writer.writerows(pool)
    say(f"池行：P24_pool={sum(1 for r in pool if r['pool']=='P24_pool')} "
        f"P85_pool={sum(1 for r in pool if r['pool']=='P85_pool')}")

    verify_path = _project_file(_PROJECT_ROOT, OUT / "verify.json")
    verify_path.write_text(
        json.dumps(
            {
                "batches": verifies,
                "pool_rows": Counter(r["pool"] for r in pool),
                "pool_roots": {t: len({r["root_id"] for r in pool if r["pool"] == t})
                               for t in {r["pool"] for r in pool}},
                "pool_hu_fan": {t: dict(Counter(r["hu_fan"] for r in pool if r["pool"] == t))
                                for t in {r["pool"] for r in pool}},
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    (_project_file(_PROJECT_ROOT, OUT / "extract.log")).write_text("\n".join(log) + "\n", encoding="utf-8")
    say(f"写出 {walls_path} / {states_path} / {pool_path} / {verify_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
