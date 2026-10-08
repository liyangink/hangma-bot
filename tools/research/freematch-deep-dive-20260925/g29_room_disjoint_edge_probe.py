#!/usr/bin/env python3
"""G29：先冻结未看教师的独立房间样本，再作两/三摸方向复核。"""

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

import argparse
from collections import Counter, defaultdict
import gzip
import hashlib
import json
from pathlib import Path

import g11_cross_family_action_atlas as atlas
import g17_one_draw_value_gap as g17
import g23_three_draw_teacher as teacher
import g28_c01_context_gate_screen as c01
import g28_c01_simple_controls as controls
from hangma_bot.hangma.engine import _build_context
from hangma_bot.kernel.serialization import observation_from_json


HERE = Path(__file__).resolve().parent
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g29-room-disjoint-edge-20260927')
SELECTION = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g29-room-disjoint-edge-20260927/selection.json')
ROWS = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g29-room-disjoint-edge-20260927/rows.jsonl.gz')
RESULT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g29-room-disjoint-edge-20260927/result.json')
SALT = "g29-room-disjoint-edge-v1"
QUOTA = 80


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def row_key(row: dict) -> tuple[str, int, int]:
    return row["game_id"], row["round_no"], row["trigger_seq"]


def _sources() -> tuple[dict, set[str], set[tuple[str, int, int]], dict]:
    """确认完整桌、父代与 G23 已使用房间；不读取旧教师标签。"""

    frozen = json.loads(atlas.FROZEN.read_text(encoding="utf-8"))
    complete = atlas._complete_ids()
    prior = json.loads(teacher.SELECTION.read_text(encoding="utf-8"))
    if (len(complete) != 909 or prior.get("outcome_blind") is not True or
            prior.get("source_frozen_rooms_sha256") != sha(atlas.FROZEN) or
            prior.get("parent_source_sha256") != frozen["parent_source_sha256"]):
        raise ValueError("冻结来源身份漂移")
    used_rooms = {row["room_id"] for row in prior["selected"]}
    eligible_rooms = {room["room_id"] for room in frozen["rooms"]} - used_rooms
    if len(eligible_rooms) != 15:
        raise ValueError("G23 房间排除后应余 15 间")
    return frozen, complete, teacher._g14_keys(frozen), {
        "g23_selection_sha256": sha(teacher.SELECTION),
        "frozen_rooms_sha256": sha(atlas.FROZEN),
        "parent_source_sha256": frozen["parent_source_sha256"],
        "eligible_rooms": sorted(eligible_rooms),
    }


def select() -> None:
    """仅读动作前信息和父代评分，用固定盐取至多 80 个独立完整桌。"""

    if SELECTION.exists() or ROWS.exists() or RESULT.exists():
        raise SystemExit("G29 已有抽样/结果，拒绝覆盖")
    frozen, complete, g14_excluded, meta = _sources()
    eligible_rooms = set(meta["eligible_rooms"])
    old_keys = {row_key(row) for row in json.loads(teacher.SELECTION.read_text(encoding="utf-8"))["selected"]}
    options = []
    counts = Counter()
    for room in frozen["rooms"]:
        if room["room_id"] not in eligible_rooms:
            continue
        audit = atlas.source.ROOT / room["audit_dir"]
        decision_file = audit / "participants" / atlas.source.ACTOR / "decisions.jsonl"
        if decision_file.stat().st_size != room["decision_bytes"]:
            raise ValueError("冻结房决策审计大小漂移")
        release = ((json.loads((audit / "manifest.json").read_text(encoding="utf-8"))
                    .get("payload") or {}).get("policy_release") or {})
        if release.get("candidate_source_sha256") != frozen["parent_source_sha256"]:
            raise ValueError("父代源码身份漂移")
        accepted = atlas.source._accepted(decision_file)
        for context, raw, plan in atlas.source.screen._iter_decisions(audit):
            game_id = context.get("game_id")
            if game_id not in complete or (raw.get("window_key") or {}).get("phase") != "draw":
                continue
            ranked = sorted(plan.get("candidates") or [], key=lambda row: row.get("rank", 10**9))
            if not ranked or not (ranked[0].get("action_key") or "").startswith("discard:"):
                continue
            parent = ranked[0]["action_key"]
            if accepted.get(context.get("decision_id")) != parent:
                continue
            window = game_id, context.get("round_no"), context.get("trigger_seq")
            if window in g14_excluded or window in old_keys or parent == "discard:白":
                continue
            legal_rows = (raw.get("rules") or {}).get("legal_candidates") or []
            legal = {row["action_key"]: row.get("facts") or {} for row in legal_rows}
            if len(legal) != len(legal_rows) or parent not in legal or not teacher._eligible(legal[parent]):
                continue
            pstd = g17._vector(legal[parent], "standard_useful_tiles")
            pcombined = g17._vector(legal[parent], "useful_tiles")
            if pstd is None or pcombined is None:
                continue
            top_score = ranked[0].get("total_score")
            if type(top_score) not in (int, float):
                continue
            chosen = None
            gap = None
            for item in ranked[1:]:
                action = item.get("action_key")
                if not isinstance(action, str) or not action.startswith("discard:") or action == "discard:白":
                    continue
                facts = legal.get(action)
                if facts is None or not teacher._eligible(facts):
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
            if sum(tile.code == "白" for tile in _build_context(obs).full_hand()) != 1:
                continue
            is_open, _levels = c01.gate(obs)
            options.append({"room_id": room["room_id"], "game_id": game_id,
                            "round_no": window[1], "trigger_seq": window[2],
                            "parent_action": parent, "alternative_action": chosen,
                            "white_after": 1, "score_gap": gap,
                            "c01_public_opponent_gate_open": is_open})
            counts["eligible_windows"] += 1
    options.sort(key=lambda row: hashlib.sha256(
        (SALT + ":" + row["game_id"] + ":" + str(row["round_no"]) +
         ":" + str(row["trigger_seq"])).encode()).hexdigest())
    selected = []
    used_tables = set()
    for row in options:
        if row["game_id"] in used_tables:
            continue
        selected.append(row)
        used_tables.add(row["game_id"])
        if len(selected) == QUOTA:
            break
    if not selected:
        raise ValueError("独立房间无持一白可比动作对")
    result = {"schema": "g29-room-disjoint-selection/1", "outcome_blind": True,
              "selection_salt": SALT, "quota": QUOTA, **meta,
              "counts": {**counts, "selected_pairs": len(selected),
                         "selected_rooms": len({row["room_id"] for row in selected}),
                         "selected_tables": len(used_tables)},
              "selected": selected}
    OUT.mkdir(parents=True, exist_ok=True)
    SELECTION.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                         encoding="utf-8")
    print(json.dumps(result["counts"], ensure_ascii=False, sort_keys=True))


def _prediction(row: dict, parent_key: tuple, alternative_key: tuple) -> int:
    """键较小者优先：+1 是改选备选，-1 是保持父代，0 是弃权。"""

    return int(alternative_key < parent_key) - int(alternative_key > parent_key)


def evaluate() -> None:
    """只读已冻结的选入名单，调用 G23 同源生产规则教师。"""

    if ROWS.exists() or RESULT.exists():
        raise SystemExit("G29 教师结果已存在，拒绝覆盖")
    if not SELECTION.exists():
        raise ValueError("请先执行 --select 冻结样本")
    frozen, _complete, _g14_excluded, meta = _sources()
    selection = json.loads(SELECTION.read_text(encoding="utf-8"))
    if (selection.get("outcome_blind") is not True or selection.get("schema") !=
            "g29-room-disjoint-selection/1" or selection.get("quota") != QUOTA or
            selection.get("selection_salt") != SALT or
            any(selection.get(name) != value for name, value in meta.items())):
        raise ValueError("G29 样本清单漂移")
    selected = selection["selected"]
    if len(selected) != selection["counts"]["selected_pairs"]:
        raise ValueError("G29 样本数漂移")
    teacher_rows = teacher._calculate(frozen, selected)
    rows = []
    metrics = Counter()
    tables: dict[str, set[str]] = defaultdict(set)
    for row in teacher_rows:
        parent, alternative = row["parent"], row["alternative"]
        predictions = {
            "c01": _prediction(row, c01.key(row["parent_action"], parent),
                               c01.key(row["alternative_action"], alternative)),
            "edge": _prediction(row, controls.edge_key(row["parent_action"]),
                                controls.edge_key(row["alternative_action"])),
            "honor": _prediction(row, controls.honor_key(row["parent_action"]),
                                 controls.honor_key(row["alternative_action"])),
        }
        truth = (row["delta_3"] > 0) - (row["delta_3"] < 0)
        cohort = "two_equal" if row["delta_2"] == 0 else "two_non_equal"
        for name, direction in predictions.items():
            label = ("correct" if direction == truth and truth else
                     "wrong" if direction and truth else
                     "zero_alarm" if direction else "abstain")
            metrics[f"{cohort}_{name}_{label}"] += 1
            metrics[f"all_{name}_{label}"] += 1
            if direction > 0:
                metrics[f"{cohort}_{name}_change"] += 1
                tables[name].add(row["game_id"])
                if row["c01_public_opponent_gate_open"]:
                    metrics[f"{cohort}_{name}_gated_change"] += 1
        if predictions["c01"] != predictions["edge"]:
            metrics[f"{cohort}_c01_edge_disagree"] += 1
            metrics[f"{cohort}_c01_edge_disagree_c01_correct"] += int(predictions["c01"] == truth and truth != 0)
            metrics[f"{cohort}_c01_edge_disagree_edge_correct"] += int(predictions["edge"] == truth and truth != 0)
        rows.append({**row, "predictions": predictions,
                     "c01_edge_disagree": predictions["c01"] != predictions["edge"]})
    OUT.mkdir(parents=True, exist_ok=True)
    with ROWS.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as stream:
            for row in rows:
                stream.write((json.dumps(row, ensure_ascii=False, sort_keys=True,
                                         separators=(",", ":")) + "\n").encode())
    result = {"schema": "g29-room-disjoint-teacher/1", "outcome_blind_selection": True,
              "source_selection_sha256": sha(SELECTION),
              "source_g23_math_sha256": sha(teacher.HERE / "g7_three_self_draw_probe.py"),
              "probe_script_sha256": sha(Path(__file__)), "rows_sha256": sha(ROWS),
              "pairs": len(rows), "rooms": len({row["room_id"] for row in rows}),
              "tables": len({row["game_id"] for row in rows}),
              "metrics": dict(sorted(metrics.items())),
              "table_coverage": {name: len(ids) for name, ids in sorted(tables.items())},
              "boundary": "旧官方流中未曾入G23作者/留出样本的房间；无他家行动三摸理想容量，不是新赛事环境或完整桌净收益。"}
    RESULT.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                      encoding="utf-8")
    print(json.dumps({"pairs": result["pairs"], "rooms": result["rooms"],
                      "metrics": result["metrics"]}, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("select", "evaluate"))
    args = parser.parse_args()
    (select if args.mode == "select" else evaluate)()
