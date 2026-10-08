#!/usr/bin/env python3
"""G222：只读 G221 同墙完整桌，核首次改弃局与后续局的分账传播。"""

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

from collections import Counter
from hashlib import sha256
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
SOURCE = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g221-settlement-route-panel-20260929')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g222-g221-table-path-audit-20260929/result.json')
ARM = "g221_settlement_route_v1"
PARENT = "r18_v2"


def digest(path: Path) -> str:
    """绑定已完成而不可重写的 G221 阶段证据。"""
    return sha256(path.read_bytes()).hexdigest()


def decision_identity(decision_id: str, table_id: str) -> tuple[int, int, int] | None:
    """解析模拟桌内唯一局号、触发序号和物理座位。"""
    prefix = f"sitin-stage:{table_id}:sitin-stage:{table_id}:"
    if not decision_id.startswith(prefix):
        return None
    parts = decision_id[len(prefix):].split(":")
    if (len(parts) != 4 or not parts[0].isdigit() or not parts[1].isdigit()
            or parts[2] != "draw" or not parts[3].startswith("seat")
            or not parts[3][4:].isdigit()):
        raise ValueError("G221 改弃决策身份格式不符")
    return int(parts[0]), int(parts[1]), int(parts[3][4:])


def terminal(hand: dict, seat: int) -> str:
    """同一结算局的互斥本座终点。"""
    if hand["is_draw"]:
        return "draw"
    if hand["winner_seat"] != seat:
        return "other_win"
    return "plain_self" if hand["fan"] == 1 else "special_self"


def audit_stage(path: Path) -> list[dict]:
    """逐桌验证第一次改弃前恒等、首次局起分相同及整桌分账守恒。"""
    candidate = json.loads(path.read_text(encoding="utf-8"))
    parent_path = path.with_name(path.name.replace(ARM, PARENT))
    parent = json.loads(parent_path.read_text(encoding="utf-8"))
    if any(candidate[key] != parent[key] for key in ("mix", "root_index", "focal_seat")):
        raise ValueError("G221 两臂阶段身份不一致")
    if candidate["stage"]["status"] != "complete" or parent["stage"]["status"] != "complete":
        raise ValueError("G221 阶段未完成")
    if len(candidate["stage"]["tables"]) != 2 or len(parent["stage"]["tables"]) != 2:
        raise ValueError("G221 阶段未包含两张完整桌")
    metrics = [row for row in candidate["stage"]["g221_metrics"]
               if row["status"] == "adopted"]
    assigned = 0
    rows = []
    for a, p in zip(candidate["stage"]["tables"], parent["stage"]["tables"]):
        if a["table_id"] != p["table_id"] or a["seed"] != p["seed"]:
            raise ValueError("G221 两臂桌身份或牌山不一致")
        seat = a["hand_account"]["focal_seat"]
        if (seat != p["hand_account"]["focal_seat"]
                or a["stage_situation"]["participant_ids_by_seat"][seat] != "focal"):
            raise ValueError("G221 换座后本座映射不一致")
        decisions = []
        for metric in metrics:
            identity = decision_identity(metric["decision_id"], a["table_id"])
            if identity is not None:
                round_no, seq, decision_seat = identity
                if decision_seat != seat or not 1 <= round_no <= 8:
                    raise ValueError("G221 改弃不在本桌本座的合法单局")
                decisions.append((round_no, seq, metric))
        assigned += len(decisions)
        decisions.sort(key=lambda item: item[:2])
        first_round = decisions[0][0] if decisions else None
        a_hands, p_hands = a["hand_records"], p["hand_records"]
        if len(a_hands) != len(p_hands) or len(a_hands) != 8:
            raise ValueError("G221 八局结算不完整")
        first_delta = later_delta = 0
        first_plain_delta = first_special_delta = 0
        later_plain_delta = later_special_delta = 0
        first_transition = None
        first_hand_vector_match = None
        for ah, ph in zip(a_hands, p_hands):
            round_no = ah["round_no"]
            if round_no != ph["round_no"]:
                raise ValueError("G221 两臂局号不匹配")
            if first_round is None or round_no < first_round:
                if ah != ph:
                    raise ValueError("G221 首次改弃前的单局结算已分叉")
                continue
            if round_no == first_round:
                if ah["scores_before"] != ph["scores_before"]:
                    raise ValueError("G221 首次改弃局四座起分不同")
                first_transition = terminal(ph, seat) + "->" + terminal(ah, seat)
                first_hand_vector_match = ah["score_delta"] == ph["score_delta"]
            delta = ah["score_delta"][seat] - ph["score_delta"][seat]
            plain = ((ah["score_delta"][seat] if terminal(ah, seat) == "plain_self" else 0)
                     - (ph["score_delta"][seat] if terminal(ph, seat) == "plain_self" else 0))
            special = ((ah["score_delta"][seat] if terminal(ah, seat) == "special_self" else 0)
                       - (ph["score_delta"][seat] if terminal(ph, seat) == "special_self" else 0))
            if round_no == first_round:
                first_delta += delta
                first_plain_delta += plain
                first_special_delta += special
            else:
                later_delta += delta
                later_plain_delta += plain
                later_special_delta += special
        whole = a["scores_by_seat"][seat] - p["scores_by_seat"][seat]
        if whole != first_delta + later_delta:
            raise ValueError("G221 首次局＋后续局不等于整桌分差")
        if first_round is None and (whole != 0 or a_hands != p_hands):
            raise ValueError("G221 未改弃桌并未与父代恒等")
        rows.append({
            "mix": candidate["mix"], "root_index": candidate["root_index"],
            "stage_start_seat": candidate["focal_seat"], "table_id": a["table_id"],
            "physical_focal_seat": seat, "first_changed_round": first_round,
            "adopted_in_table": len(decisions),
            "adopted_in_first_changed_round": sum(r == first_round for r, _, _ in decisions),
            "first_action": None if not decisions else decisions[0][2]["alternate_action"],
            "first_parent_action": None if not decisions else decisions[0][2]["parent_action"],
            "first_selector_half_gain": None if not decisions else decisions[0][2]["half_total_gain"],
            "first_terminal_transition": first_transition,
            "first_hand_full_score_vector_match": first_hand_vector_match,
            "first_hand_focal_delta": first_delta,
            "first_hand_plain_income_delta": first_plain_delta,
            "first_hand_special_income_delta": first_special_delta,
            "later_hands_focal_delta": later_delta,
            "later_hands_plain_income_delta": later_plain_delta,
            "later_hands_special_income_delta": later_special_delta,
            "whole_table_focal_delta": whole,
        })
    if assigned != len(metrics):
        raise ValueError("G221 改弃记录未唯一分配到两张桌")
    return rows


def summarize(rows: list[dict]) -> dict:
    """只报告加法恒等和描述性分层，不按赛后正负选择新阈值。"""
    result = {}
    for mix in ("H", "M"):
        selected = [row for row in rows if row["mix"] == mix]
        changed = [row for row in selected if row["first_changed_round"] is not None]
        result[mix] = {
            "complete_tables": len(selected), "changed_tables": len(changed),
            "untouched_identical_tables": len(selected) - len(changed),
            "adopted_actions": sum(row["adopted_in_table"] for row in selected),
            "first_hand_focal_delta_sum": sum(row["first_hand_focal_delta"] for row in changed),
            "later_hands_focal_delta_sum": sum(row["later_hands_focal_delta"] for row in changed),
            "whole_table_focal_delta_sum": sum(row["whole_table_focal_delta"] for row in selected),
            "first_hand_plain_income_delta_sum": sum(row["first_hand_plain_income_delta"] for row in changed),
            "first_hand_special_income_delta_sum": sum(row["first_hand_special_income_delta"] for row in changed),
            "later_hands_plain_income_delta_sum": sum(row["later_hands_plain_income_delta"] for row in changed),
            "later_hands_special_income_delta_sum": sum(row["later_hands_special_income_delta"] for row in changed),
            "first_hand_signs": dict(sorted(Counter(
                "positive" if row["first_hand_focal_delta"] > 0 else
                "negative" if row["first_hand_focal_delta"] < 0 else "zero"
                for row in changed).items())),
            "first_terminal_transitions": dict(sorted(Counter(
                row["first_terminal_transition"] for row in changed).items())),
            "first_hand_same_full_vector": sum(
                row["first_hand_full_score_vector_match"] for row in changed),
            "later_delta_after_same_first_vector": sum(
                row["later_hands_focal_delta"] for row in changed
                if row["first_hand_full_score_vector_match"]),
        }
        if result[mix]["complete_tables"] != 32:
            raise ValueError("G221 每池候选完整桌数不足")
        if (result[mix]["first_hand_focal_delta_sum"]
                + result[mix]["later_hands_focal_delta_sum"]
                != result[mix]["whole_table_focal_delta_sum"]):
            raise ValueError("G221 本座整桌分差分解不守恒")
    return result


def main() -> None:
    """G221 结果已看后只读诊断；不能反向拟合该面板的新算子。"""
    if OUT.exists():
        raise FileExistsError(OUT)
    stage_files = sorted((_project_file(_PROJECT_ROOT, SOURCE / "stages")).glob("*" + ARM + ".json"))
    if len(stage_files) != 32:
        raise ValueError("G221 候选阶段应为 32 个")
    corpus = sha256()
    rows = []
    for candidate in stage_files:
        parent = candidate.with_name(candidate.name.replace(ARM, PARENT))
        for path in (candidate, parent):
            corpus.update(path.name.encode("utf-8") + b"\0" + path.read_bytes() + b"\0")
        rows.extend(audit_stage(candidate))
    if len(rows) != 64:
        raise ValueError("G221 候选完整桌数不守恒")
    by_mix = summarize(rows)
    g221 = json.loads((_project_file(_PROJECT_ROOT, SOURCE / "result.json")).read_text(encoding="utf-8"))
    expected = g221["descriptive_mean_delta_vs_baseline_per_table"][ARM] * 64
    if sum(item["whole_table_focal_delta_sum"] for item in by_mix.values()) != expected:
        raise ValueError("G222 与 G221 已归档整桌净分不一致")
    result = {
        "schema": "g222-g221-table-path-audit/1",
        "source_sha256": {name: digest(_project_file(_PROJECT_ROOT, SOURCE / name)) for name in
                          ("manifest.json", "result.json", "analysis.json")},
        "stage_corpus_sha256": corpus.hexdigest(),
        "script_sha256": digest(Path(__file__)),
        "by_mix": by_mix, "rows": rows,
        "boundary": "已看 G221 的完整桌首次改弃局与后续局加法诊断；后续局包含先前积分传播、额外改弃与对手动作，不是首次动作的独立因果贡献。",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True,
                              indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result["by_mix"], ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
