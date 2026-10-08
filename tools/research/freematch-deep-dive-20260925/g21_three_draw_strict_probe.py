#!/usr/bin/env python3
"""G21 冻结官方动作：G7 三摸自然容量在当前相关牌效全同层的压力测试。"""

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
import gzip
import hashlib
import json
from pathlib import Path
import time

import g11_cross_family_action_atlas as atlas
import g17_one_draw_value_gap as g17
import g18_two_self_draw_joint as joint
import g7_three_self_draw_probe as natural
from hangma_bot.hangma.engine import _build_context
from hangma_bot.hangma.internal_types import counts_from_tiles
from hangma_bot.hangma.public_tile_counts import count_unseen_tiles
from hangma_bot.kernel.serialization import observation_from_json


HERE = Path(__file__).resolve().parent
SOURCE = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g14-latent-natural-links-20260927')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g21-three-draw-strict-20260927/result.json')
ROWS = OUT.with_name("rows.jsonl.gz")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _source_targets(frozen: dict) -> dict[tuple[str, int, int], dict]:
    """G14 已选 237 个逐牌即时向量全同对，不根据三摸结果重选。"""

    source = json.loads((_project_file(_PROJECT_ROOT, SOURCE / "result.json")).read_text(encoding="utf-8"))
    if (source.get("outcome_blind") is not True or
            source.get("rows_sha256") != _sha(_project_file(_PROJECT_ROOT, SOURCE / "rows.jsonl.gz")) or
            source.get("parent_source_sha256") != frozen["parent_source_sha256"]):
        raise ValueError("G14 源结果或冻结父代摘要漂移")
    targets = {}
    for row in (json.loads(line) for line in gzip.open(_project_file(_PROJECT_ROOT, SOURCE / "rows.jsonl.gz"), "rt")):
        if row.get("tier") != "same_exact_immediate_vectors":
            continue
        key = (row["game_id"], row["round_no"], row["trigger_seq"])
        if key in targets:
            raise ValueError("G14 严层目标窗口重复")
        targets[key] = row
    if len(targets) != 237:
        raise ValueError("G14 严层应为 237 个动作对")
    return targets


def _eligible(a: dict, b: dict) -> bool:
    """普通型可在三摸内到胡、七对型三摸内不可到胡。"""

    sa, sb = a.get("standard_shanten_after"), b.get("standard_shanten_after")
    qa, qb = a.get("seven_pairs_shanten_after"), b.get("seven_pairs_shanten_after")
    return (type(sa) is int and sa == sb and sa <= 2 and
            (qa is None or type(qa) is int and qa > 2) and
            (qb is None or type(qb) is int and qb > 2))


def _sign(value: int) -> str:
    return "positive" if value > 0 else "negative" if value < 0 else "equal"


def main() -> None:
    """对预登记动作对运行同源 G7 理想化动态规划，赛果保持未读。"""

    if OUT.exists() or ROWS.exists():
        raise SystemExit("G21 结果已存在，拒绝覆盖")
    frozen = json.loads(atlas.FROZEN.read_text(encoding="utf-8"))
    targets = _source_targets(frozen)
    complete = atlas._complete_ids()
    if len(complete) != 909:
        raise ValueError("冻结完整桌母体漂移")
    counts = Counter()
    tables: dict[str, set[str]] = defaultdict(set)
    rows = []
    seen = set()
    durations = []
    for room in frozen["rooms"]:
        audit = atlas.source.ROOT / room["audit_dir"]
        decisions = audit / "participants" / atlas.source.ACTOR / "decisions.jsonl"
        if decisions.stat().st_size != room["decision_bytes"]:
            raise ValueError("冻结房动作文件字节数漂移")
        payload = json.loads((audit / "manifest.json").read_text(encoding="utf-8")).get("payload") or {}
        if (payload.get("policy_release") or {}).get("candidate_source_sha256") != frozen["parent_source_sha256"]:
            raise ValueError("冻结房父代源码摘要漂移")
        if (payload.get("ruleset_version") != "hangma-mvp-v10-public-counts" or
                payload.get("base_score") != 1 or
                payload.get("you_cai_bi_kao") is not False):
            raise ValueError("G21 冻结房规则配置漂移")
        accepted = atlas.source._accepted(decisions)
        for context, raw, plan in atlas.source.screen._iter_decisions(audit):
            key = (context.get("game_id"), context.get("round_no"),
                   context.get("trigger_seq"))
            target = targets.get(key)
            if target is None:
                continue
            if key in seen or target["room_id"] != room["room_id"] or key[0] not in complete:
                raise ValueError("G21 动作来源房/完整桌/唯一性漂移")
            seen.add(key)
            ranked = sorted(plan.get("candidates") or [], key=lambda row: row.get("rank", 10**9))
            if (not ranked or ranked[0].get("action_key") != target["parent_action"] or
                    accepted.get(context.get("decision_id")) != target["parent_action"]):
                raise ValueError("父代已接受动作不等于 G14 根动作")
            legal_list = (raw.get("rules") or {}).get("legal_candidates") or []
            legal = {row.get("action_key"): row for row in legal_list}
            if (len(legal) != len(legal_list) or target["parent_action"] not in legal or
                    target["alternative_action"] not in legal):
                raise ValueError("G21 生产合法动作对缺失")
            a = legal[target["parent_action"]].get("facts") or {}
            b = legal[target["alternative_action"]].get("facts") or {}
            if not all(g17._vector(a, field) == g17._vector(b, field) and
                       g17._vector(a, field) is not None
                       for field in ("standard_useful_tiles", "useful_tiles")):
                raise ValueError("G14 旧逐牌即时有效向量不再相同")
            if not _eligible(a, b):
                counts["excluded_seven_reachable_or_standard"] += 1
                continue
            observation = observation_from_json(raw["observation"])
            unseen = count_unseen_tiles(observation)
            if any(amount is None for amount in unseen):
                raise ValueError("G21 公开未知牌容量不完整")
            context_now = _build_context(observation)
            meld_count = len(observation.melds[observation.seat])
            full = context_now.full_hand()
            if len(full) != 14 - 3 * meld_count:
                raise ValueError("G21 当前完整暗手张数错误")
            started = time.perf_counter()
            values = {}
            for name, action in (("parent", target["parent_action"]),
                                 ("alternative", target["alternative_action"])):
                root = joint._drop(full, action.split(":", 1)[1])
                hand_counts = counts_from_tiles(root)
                values[name] = {depth: natural.favorable(hand_counts, unseen, meld_count, depth)
                                for depth in (2, 3)}
            duration = (time.perf_counter() - started) * 1000
            natural.favorable.cache_clear()
            natural.summary.cache_clear()
            durations.append(duration)
            n = sum(unseen)
            if n <= 2:
                raise ValueError("未知牌池不足三次理想化抽牌")
            d2 = values["alternative"][2] - values["parent"][2]
            d3 = values["alternative"][3] - values["parent"][3]
            row = {"room_id": room["room_id"], "game_id": key[0],
                   "round_no": key[1], "trigger_seq": key[2],
                   "parent_action": target["parent_action"],
                   "alternative_action": target["alternative_action"],
                   "standard_shanten": a["standard_shanten_after"],
                   "seven_shanten": a.get("seven_pairs_shanten_after"),
                   "white_after": target["white_after"],
                   "unknown_pool": n, "parent": values["parent"],
                   "alternative": values["alternative"],
                   "delta_2": d2, "delta_3": d3,
                   "delta_2_percentage_points": 100 * d2 / natural.falling(n, 2),
                   "delta_3_percentage_points": 100 * d3 / natural.falling(n, 3),
                   "elapsed_ms": round(duration, 3)}
            rows.append(row)
            counts["eligible"] += 1
            tables["eligible"].add(key[0])
            for depth, delta in ((2, d2), (3, d3)):
                label = f"depth{depth}_{_sign(delta)}"
                counts[label] += 1
                tables[label].add(key[0])
            if d2 == 0 and d3 != 0:
                counts["new_three_only"] += 1
                tables["new_three_only"].add(key[0])
            if len(rows) % 25 == 0:
                print("G21 evaluated", len(rows), "of 219", flush=True)
    if (seen != set(targets) or counts["eligible"] != 219 or
            counts["excluded_seven_reachable_or_standard"] != 18):
        raise ValueError("G21 219 对/18 排除层与预登记不符")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with ROWS.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as stream:
            for row in rows:
                stream.write((json.dumps(row, ensure_ascii=False, sort_keys=True,
                                         separators=(",", ":")) + "\n").encode("utf-8"))
    durations.sort()
    result = {"schema": "g21-three-draw-strict/1", "outcome_blind": True,
              "source_g14_result_sha256": _sha(_project_file(_PROJECT_ROOT, SOURCE / "result.json")),
              "source_g14_rows_sha256": _sha(_project_file(_PROJECT_ROOT, SOURCE / "rows.jsonl.gz")),
              "source_frozen_rooms_sha256": _sha(atlas.FROZEN),
              "parent_source_sha256": frozen["parent_source_sha256"],
              "g7_math_script_sha256": _sha(_project_file(_PROJECT_ROOT, HERE / "g7_three_self_draw_probe.py")),
              "probe_script_sha256": _sha(Path(__file__)),
              "target_pairs": len(targets), "eligible_pairs": len(rows),
              "counts": dict(sorted(counts.items())),
              "table_coverage": {name: len(ids) for name, ids in sorted(tables.items())},
              "elapsed_ms_p50": durations[len(durations)//2],
              "elapsed_ms_p95": durations[int(len(durations)*0.95)],
              "elapsed_ms_max": durations[-1],
              "rows_sha256": _sha(ROWS),
              "boundary": "仅三次本人抽牌的无对手最优弃牌容量；无未来抓打圈、墙末、番值、他家先胡或真实牌墙分布，不是赛事效果。"}
    OUT.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                   encoding="utf-8")
    print(json.dumps({"counts": result["counts"], "table_coverage": result["table_coverage"],
                      "elapsed_ms_p95": result["elapsed_ms_p95"]},
                     ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
