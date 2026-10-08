#!/usr/bin/env python3
"""G23：冻结父代广层同牌效动作对的三次本人摸牌离线教师。"""

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
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g23-three-draw-teacher-20260927')
SELECTION = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g23-three-draw-teacher-20260927/selection.json')
ROWS = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g23-three-draw-teacher-20260927/rows.jsonl.gz')
RESULT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g23-three-draw-teacher-20260927/result.json')
G14 = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g14-latent-natural-links-20260927')
QUOTAS = {0: 40, 1: 120, 2: 40}
SELECTION_SALT = "g23-three-draw-broad-v1"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def key(row: dict) -> tuple[str, int, int]:
    return row["game_id"], row["round_no"], row["trigger_seq"]


def _g14_keys(frozen: dict) -> set[tuple[str, int, int]]:
    """显式排除已经按潜在连接优势选入 G21 的严格窗。"""

    source = json.loads((_project_file(_PROJECT_ROOT, G14 / "result.json")).read_text(encoding="utf-8"))
    if (source.get("outcome_blind") is not True or
            source.get("parent_source_sha256") != frozen["parent_source_sha256"] or
            source.get("rows_sha256") != sha(_project_file(_PROJECT_ROOT, G14 / "rows.jsonl.gz"))):
        raise ValueError("G14 排除名单身份漂移")
    result = set()
    with gzip.open(_project_file(_PROJECT_ROOT, G14 / "rows.jsonl.gz"), "rt", encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            if row["tier"] == "same_exact_immediate_vectors":
                result.add(key(row))
    if len(result) != 237:
        raise ValueError("G14 严格排除窗应为 237")
    return result


def _eligible(facts: dict) -> bool:
    """普通型离胡尚需两次本人摸牌，七对三摸内不可达。"""

    std, seven = facts.get("standard_shanten_after"), facts.get("seven_pairs_shanten_after")
    return std == 1 and type(std) is int and (seven is None or type(seven) is int and seven > 2)


def _selection(frozen: dict, complete: set[str]) -> dict:
    """只按父代行为、合法事实和固定哈希采样；绝不读取教师值。"""

    excluded = _g14_keys(frozen)
    options: dict[int, list[dict]] = defaultdict(list)
    counts = Counter()
    for room in frozen["rooms"]:
        audit = atlas.source.ROOT / room["audit_dir"]
        decision_file = audit / "participants" / atlas.source.ACTOR / "decisions.jsonl"
        if decision_file.stat().st_size != room["decision_bytes"]:
            raise ValueError("冻结房动作文件字节数漂移")
        release = ((json.loads((audit / "manifest.json").read_text(encoding="utf-8"))
                    .get("payload") or {}).get("policy_release") or {})
        if release.get("candidate_source_sha256") != frozen["parent_source_sha256"]:
            raise ValueError("冻结房父代源码身份漂移")
        accepted = atlas.source._accepted(decision_file)
        for context, raw, plan in atlas.source.screen._iter_decisions(audit):
            gid = context.get("game_id")
            if gid not in complete or (raw.get("window_key") or {}).get("phase") != "draw":
                continue
            ranked = sorted(plan.get("candidates") or [], key=lambda row: row.get("rank", 10**9))
            if not ranked or not (ranked[0].get("action_key") or "").startswith("discard:"):
                continue
            parent = ranked[0]["action_key"]
            if accepted.get(context.get("decision_id")) != parent:
                continue
            counts["accepted_discard_windows"] += 1
            window = (gid, context.get("round_no"), context.get("trigger_seq"))
            if window in excluded:
                counts["g14_strict_window_excluded"] += 1
                continue
            legal_rows = (raw.get("rules") or {}).get("legal_candidates") or []
            legal = {row["action_key"]: row.get("facts") or {} for row in legal_rows}
            if len(legal) != len(legal_rows) or parent not in legal:
                raise ValueError("生产合法弃牌事实缺失或重复")
            pf = legal[parent]
            if not _eligible(pf) or parent == "discard:白":
                continue
            pstd, pcombined = (g17._vector(pf, field) for field in
                              ("standard_useful_tiles", "useful_tiles"))
            if pstd is None or pcombined is None:
                continue
            counts["parent_standard_shanten_one"] += 1
            top_score = ranked[0].get("total_score")
            if type(top_score) not in (int, float):
                raise ValueError("父代总分缺失")
            chosen = None
            gap = None
            for item in ranked[1:]:
                action = item.get("action_key")
                if not isinstance(action, str) or not action.startswith("discard:") or action == "discard:白":
                    continue
                facts = legal.get(action)
                if facts is None or not _eligible(facts):
                    continue
                if (g17._vector(facts, "standard_useful_tiles") != pstd or
                        g17._vector(facts, "useful_tiles") != pcombined):
                    continue
                score = item.get("total_score")
                if type(score) not in (int, float):
                    continue
                gap = top_score - score
                if 0 <= gap <= 3:
                    chosen = action
                    break
            if chosen is None:
                continue
            obs = observation_from_json(raw["observation"])
            full = _build_context(obs).full_hand()
            white = sum(tile.code == "白" for tile in full)
            if white > 4:
                raise ValueError("本人白板数超过四")
            bucket = min(white, 2)
            row = {"room_id": room["room_id"], "game_id": gid,
                   "round_no": window[1], "trigger_seq": window[2],
                   "parent_action": parent, "alternative_action": chosen,
                   "white_after": white, "score_gap": gap}
            options[bucket].append(row)
            counts["eligible_windows"] += 1
            counts[f"eligible_white_{bucket}"] += 1
    selected = []
    used_tables = set()
    for bucket in (1, 2, 0):
        ordered = sorted(options[bucket], key=lambda row: hashlib.sha256(
            (SELECTION_SALT + ":" + row["game_id"] + ":" + str(row["round_no"]) +
             ":" + str(row["trigger_seq"])).encode()).hexdigest())
        taken = 0
        for row in ordered:
            if row["game_id"] in used_tables:
                continue
            selected.append(row)
            used_tables.add(row["game_id"])
            taken += 1
            if taken == QUOTAS[bucket]:
                break
        counts[f"selected_white_{bucket}"] = taken
    if not selected:
        raise ValueError("G23 结果盲入口无样本")
    return {"schema": "g23-three-draw-selection/1", "outcome_blind": True,
            "source_frozen_rooms_sha256": sha(atlas.FROZEN),
            "source_g14_rows_sha256": sha(_project_file(_PROJECT_ROOT, G14 / "rows.jsonl.gz")),
            "parent_source_sha256": frozen["parent_source_sha256"],
            "quota_white_0_1_2plus": [QUOTAS[i] for i in (0, 1, 2)],
            "selection_salt": SELECTION_SALT,
            "counts": dict(sorted(counts.items())), "selected": selected}


def _write_selection(record: dict) -> None:
    encoded = json.dumps(record, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    if SELECTION.exists():
        if SELECTION.read_text(encoding="utf-8") != encoded:
            raise ValueError("G23 已冻结抽样与当前来源不一致")
    else:
        OUT.mkdir(parents=True, exist_ok=True)
        SELECTION.write_text(encoded, encoding="utf-8")


def _calculate(frozen: dict, selected: list[dict]) -> list[dict]:
    """冻结选入后才算 G7 三摸；保存可复算的本人暗手和公开未知计数。"""

    targets = {key(row): row for row in selected}
    observed = set()
    result = []
    for room in frozen["rooms"]:
        if not any(row["room_id"] == room["room_id"] for row in selected):
            continue
        audit = atlas.source.ROOT / room["audit_dir"]
        for context, raw, plan in atlas.source.screen._iter_decisions(audit):
            window = (context.get("game_id"), context.get("round_no"),
                      context.get("trigger_seq"))
            target = targets.get(window)
            if target is None:
                continue
            if window in observed or target["room_id"] != room["room_id"]:
                raise ValueError("G23 目标窗重复或来源房漂移")
            observed.add(window)
            ranked = sorted(plan.get("candidates") or [], key=lambda row: row.get("rank", 10**9))
            if not ranked or ranked[0].get("action_key") != target["parent_action"]:
                raise ValueError("G23 父代动作漂移")
            legal = {row["action_key"]: row.get("facts") or {} for row in
                     (raw.get("rules") or {}).get("legal_candidates") or []}
            pf, af = legal[target["parent_action"]], legal[target["alternative_action"]]
            if (not _eligible(pf) or not _eligible(af) or
                    any(g17._vector(pf, field) != g17._vector(af, field)
                        for field in ("standard_useful_tiles", "useful_tiles"))):
                raise ValueError("G23 生产规则事实漂移")
            obs = observation_from_json(raw["observation"])
            unknown = count_unseen_tiles(obs)
            if any(value is None for value in unknown):
                raise ValueError("G23 公开未知牌计数不完整")
            melds = len(obs.melds[obs.seat])
            full = _build_context(obs).full_hand()
            if len(full) != 14 - 3 * melds:
                raise ValueError("G23 本人完整暗手张数漂移")
            arms = {}
            started = time.perf_counter()
            for name, action in (("parent", target["parent_action"]),
                                 ("alternative", target["alternative_action"])):
                counts = counts_from_tiles(joint._drop(full, action.split(":", 1)[1]))
                arms[name] = {"counts34": counts,
                              "depth2": natural.favorable(counts, unknown, melds, 2),
                              "depth3": natural.favorable(counts, unknown, melds, 3)}
            elapsed_ms = (time.perf_counter() - started) * 1000
            natural.favorable.cache_clear()
            natural.summary.cache_clear()
            n = sum(unknown)
            result.append({**target, "meld_count": melds,
                           "unknown_counts34": unknown, "unknown_pool": n,
                           "parent": arms["parent"], "alternative": arms["alternative"],
                           "delta_2": arms["alternative"]["depth2"] - arms["parent"]["depth2"],
                           "delta_3": arms["alternative"]["depth3"] - arms["parent"]["depth3"],
                           "elapsed_ms": round(elapsed_ms, 3),
                           "split": ("holdout" if int(hashlib.sha256(
                               room["room_id"].encode()).hexdigest()[:2], 16) % 5 == 0
                                     else "development")})
            if len(result) % 20 == 0:
                print("G23 evaluated", len(result), "of", len(selected), flush=True)
    if observed != set(targets):
        raise ValueError("G23 抽样目标未全部复算")
    return result


def main() -> None:
    """冻结抽样、计算教师、写出不可覆盖的证据。"""

    if RESULT.exists() or ROWS.exists():
        raise SystemExit("G23 教师结果已存在，拒绝覆盖")
    frozen = json.loads(atlas.FROZEN.read_text(encoding="utf-8"))
    complete = atlas._complete_ids()
    if len(complete) != 909:
        raise ValueError("冻结完整桌数漂移")
    selection = _selection(frozen, complete)
    _write_selection(selection)
    rows = _calculate(frozen, selection["selected"])
    with ROWS.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as stream:
            for row in rows:
                stream.write((json.dumps(row, ensure_ascii=False, sort_keys=True,
                                         separators=(",", ":")) + "\n").encode())
    counts = Counter()
    tables: dict[str, set[str]] = defaultdict(set)
    duration = []
    for row in rows:
        counts["pairs"] += 1
        duration.append(row["elapsed_ms"])
        for depth in (2, 3):
            delta = row[f"delta_{depth}"]
            label = f"depth{depth}_" + ("positive" if delta > 0 else "negative" if delta < 0 else "equal")
            counts[label] += 1
            tables[label].add(row["game_id"])
        if row["delta_2"] == 0 and row["delta_3"] != 0:
            counts["new_three_only"] += 1
            tables["new_three_only"].add(row["game_id"])
        counts[f"split_{row['split']}"] += 1
        counts[f"white_{min(row['white_after'], 2)}"] += 1
    duration.sort()
    record = {"schema": "g23-three-draw-teacher/1", "outcome_blind": True,
              "selection_sha256": sha(SELECTION), "rows_sha256": sha(ROWS),
              "g7_math_script_sha256": sha(_project_file(_PROJECT_ROOT, HERE / "g7_three_self_draw_probe.py")),
              "probe_script_sha256": sha(Path(__file__)),
              "sampled_pairs": len(rows), "counts": dict(sorted(counts.items())),
              "table_coverage": {name: len(ids) for name, ids in sorted(tables.items())},
              "elapsed_ms_p50": duration[len(duration) // 2],
              "elapsed_ms_p95": duration[int(len(duration) * .95)],
              "boundary": "均匀公开未知池的无对手三摸容量；无抓打圈/末20张/番值/他家先胡，不是赛事收益。"}
    RESULT.write_text(json.dumps(record, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                      encoding="utf-8")
    print(json.dumps({"selection": selection["counts"], "teacher": record["counts"]},
                     ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
