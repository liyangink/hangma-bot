#!/usr/bin/env python3
"""G213：在 G211 同牌山完整桌中定位首次改弃及其所在单局的配对结算。"""

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
from hashlib import sha256
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
SOURCE = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g211-g210-hm-development-20260929')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g213-first-changed-hand-20260929/result.json')
CANDIDATE = "g210_postclaim_guarded_familiar_v1"
PARENT = "r18_v2"


def digest(path: Path) -> str:
    """绑定已冻结的完整桌输入字节。"""
    return sha256(path.read_bytes()).hexdigest()


def decision_identity(decision_id: str, table_id: str) -> tuple[int, int, int] | None:
    """按离线阶段固定格式读取官方式桌、局、事件序号和物理座位。"""
    prefix = "sitin-stage:" + table_id + ":sitin-stage:" + table_id + ":"
    if not decision_id.startswith(prefix):
        return None
    rest = decision_id[len(prefix):].split(":")
    if (len(rest) != 4 or rest[2] != "draw" or not rest[3].startswith("seat")
            or not rest[0].isdigit() or not rest[1].isdigit()
            or not rest[3][4:].isdigit()):
        raise ValueError("G213 决策身份格式不符")
    return int(rest[0]), int(rest[1]), int(rest[3][4:])


def terminal(record: dict, seat: int) -> str:
    """只用已结算事实标记本座普通胡、高番胡、他家胡或流局。"""
    if record["is_draw"]:
        return "draw"
    if record["winner_seat"] != seat:
        return "other_win"
    return "plain_self" if record["fan"] == 1 else "special_self"


def audit_stage(path: Path) -> tuple[list[dict], int]:
    """成对完整桌只在首次实际改弃所在单局归因，后续单局保持描述边界。"""
    candidate = json.loads(path.read_text(encoding="utf-8"))
    parent_path = path.with_name(path.name.replace(CANDIDATE, PARENT))
    parent = json.loads(parent_path.read_text(encoding="utf-8"))
    if any(candidate[key] != parent[key]
           for key in ("mix", "root_index", "focal_seat")):
        raise ValueError("G213 阶段配对身份不同")
    a_tables, p_tables = candidate["stage"]["tables"], parent["stage"]["tables"]
    if len(a_tables) != 2 or len(p_tables) != 2:
        raise ValueError("G213 阶段完整桌数不足")
    metrics = [row for row in candidate["stage"]["g210_metrics"]
               if row["status"] == "adopted"]
    assigned = 0
    rows = []
    untouched = 0
    for a, p in zip(a_tables, p_tables):
        if a["seed"] != p["seed"] or a["table_id"] != p["table_id"]:
            raise ValueError("G213 完整桌牌山或身份不配对")
        seat = a["hand_account"]["focal_seat"]
        if (seat != p["hand_account"]["focal_seat"]
                or a["stage_situation"]["participant_ids_by_seat"][seat] != "focal"):
            raise ValueError("G213 换座后的本座映射不一致")
        decisions = []
        for metric in metrics:
            parsed = decision_identity(metric["decision_id"], a["table_id"])
            if parsed is not None:
                round_no, seq, decision_seat = parsed
                if decision_seat != seat or not 1 <= round_no <= 8:
                    raise ValueError("G213 改弃窗口不是本桌本座合法局")
                decisions.append((round_no, seq, metric))
        assigned += len(decisions)
        if not decisions:
            untouched += 1
            if (a["hand_records"] != p["hand_records"]
                    or a["scores_by_seat"] != p["scores_by_seat"]):
                raise ValueError("G213 未改弃完整桌两臂不恒等")
            continue
        decisions.sort(key=lambda row: (row[0], row[1]))
        round_no, seq, first = decisions[0]
        a_hand = next(row for row in a["hand_records"] if row["round_no"] == round_no)
        p_hand = next(row for row in p["hand_records"] if row["round_no"] == round_no)
        if a_hand["scores_before"] != p_hand["scores_before"]:
            raise ValueError("G213 首次改弃所在局的起始全桌分已漂移")
        rows.append({
            "mix": candidate["mix"], "root_index": candidate["root_index"],
            "stage_start_seat": candidate["focal_seat"], "table_id": a["table_id"],
            "actual_focal_seat": seat, "round_no": round_no, "first_seq": seq,
            "first_parent_action": first["parent_action"],
            "first_alternate_action": first["alternate_action"],
            "first_ordinary_shanten": first["ordinary_shanten"],
            "first_ordinary_type_gain": (first["ordinary_width_alternate"][0]
                                         - first["ordinary_width_parent"][0]),
            "first_ordinary_capacity_gain": (first["ordinary_width_alternate"][1]
                                             - first["ordinary_width_parent"][1]),
            "adopted_in_first_changed_hand": sum(r == round_no for r, _, _ in decisions),
            "adopted_in_table": len(decisions),
            "scores_before_match": True,
            "parent_terminal": terminal(p_hand, seat),
            "candidate_terminal": terminal(a_hand, seat),
            "parent_focal_delta": p_hand["score_delta"][seat],
            "candidate_focal_delta": a_hand["score_delta"][seat],
            "full_score_delta_vector_match": a_hand["score_delta"] == p_hand["score_delta"],
            "first_hand_delta": a_hand["score_delta"][seat] - p_hand["score_delta"][seat],
            "whole_table_delta": a["scores_by_seat"][seat] - p["scores_by_seat"][seat],
        })
    if assigned != len(metrics):
        raise ValueError("G213 改弃指标未唯一映射到完整桌")
    return rows, untouched


def main() -> None:
    """只读已看 G211 结果，输出探索性行动链证据，不反向修改候选。"""
    if OUT.exists():
        raise FileExistsError("G213 证据已存在，拒绝覆盖")
    manifest = json.loads((_project_file(_PROJECT_ROOT, SOURCE / "manifest.json")).read_text(encoding="utf-8"))
    if manifest["arms"] != [PARENT, CANDIDATE] or manifest["planned_complete_tables"] != 768:
        raise ValueError("G213 G211 清单身份不符")
    paths = sorted((_project_file(_PROJECT_ROOT, SOURCE / "stages")).glob("*" + CANDIDATE + ".json"))
    if len(paths) != 192:
        raise ValueError("G213 候选阶段未齐")
    rows = []
    untouched = 0
    corpus_hash = sha256()
    for path in paths:
        parent_path = path.with_name(path.name.replace(CANDIDATE, PARENT))
        for source_path in (parent_path, path):
            corpus_hash.update(source_path.name.encode("utf-8") + b"\0")
            corpus_hash.update(source_path.read_bytes() + b"\0")
        current, unchanged = audit_stage(path)
        rows.extend(current)
        untouched += unchanged
    if len(rows) + untouched != 384:
        raise ValueError("G213 候选完整桌数不守恒")
    by_mix = {}
    for mix in ("H", "M"):
        selected = [row for row in rows if row["mix"] == mix]
        signs = Counter("positive" if row["first_hand_delta"] > 0 else
                        "negative" if row["first_hand_delta"] < 0 else "zero"
                        for row in selected)
        single = [row for row in selected if row["adopted_in_first_changed_hand"] == 1]
        multiple = [row for row in selected if row["adopted_in_first_changed_hand"] > 1]
        by_mix[mix] = {
            "first_changed_tables": len(selected),
            "first_hand_focal_delta_sum": sum(row["first_hand_delta"] for row in selected),
            "first_hand_signs": dict(signs),
            "same_full_score_delta_vector": sum(
                row["full_score_delta_vector_match"] for row in selected),
            "single_change_first_hand": {
                "tables": len(single), "focal_delta_sum": sum(row["first_hand_delta"] for row in single),
            },
            "multiple_changes_first_hand": {
                "tables": len(multiple),
                "focal_delta_sum": sum(row["first_hand_delta"] for row in multiple),
            },
            "first_terminal_transition": dict(Counter(
                row["parent_terminal"] + "->" + row["candidate_terminal"]
                for row in selected)),
            "first_ordinary_shanten": dict(Counter(str(row["first_ordinary_shanten"])
                                                       for row in selected)),
        }
    output = {
        "schema": "g213-first-changed-hand-audit/1",
        "source_sha256": {name: digest(_project_file(_PROJECT_ROOT, SOURCE / name)) for name in
                          ("manifest.json", "result.json", "analysis.json")},
        "stage_corpus_sha256": corpus_hash.hexdigest(),
        "script_sha256": digest(Path(__file__)),
        "candidate_complete_tables": 384,
        "untouched_identical_tables": untouched,
        "first_changed_tables": len(rows),
        "first_changed_hand_scores_before_match": len(rows),
        "by_mix": by_mix, "rows": rows,
        "boundary": "已看 G211 的首个改弃局配对；同局后续改弃合并在结算里，后续局路径可能受前局影响。按改弃筛样本不能证明线上增益或拟合阈值。",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(output, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                   encoding="utf-8")
    print(json.dumps({"untouched": untouched, "first_changed": len(rows),
                      "by_mix": by_mix}, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
