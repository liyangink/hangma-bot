"""仅读已闭评分输入，分开当前结算、下一摸支付和远端先验，不补评分。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t189-online-issue-ledger-and-offer-diagnosis-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
import gzip
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PREVIOUS = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t188-joint-score-mechanism-1')
sys.path.insert(0, str(_project_file(_PROJECT_ROOT, HERE.parent / "t185-evidence-prioritized-joker-evolution-1")))
from common import canonical, pin, save


def main():
    """将完整原评分与公开图事实交叉核对；路径后果不当单动作因果。"""
    closedpath = _project_file(_PROJECT_ROOT, HERE / "diagnostic/CLOSED.json")
    closed = json.loads(closedpath.read_text())
    assert closed["complete"] and closed["source_stable"]
    assert closed["all_original_scores_traces_and_choices_exact"] and closed["actual_score_calls"] == 48
    rowpath, viewpath = _project_file(_PROJECT_ROOT, HERE / "diagnostic/rows.jsonl"), _project_file(_PROJECT_ROOT, HERE / "diagnostic/views.jsonl.gz")
    assert pin(rowpath) == closed["rows_pin"]
    rows = list(map(json.loads, rowpath.read_text().splitlines()))
    views = {}
    with gzip.open(viewpath, "rt") as stream:
        for line in stream:
            item = json.loads(line)
            if item.get("schema") == "vip-scoring-input-view/1":
                digest = hashlib.sha256(canonical(item["view"])).hexdigest()
                assert digest == item["view_sha256"]
                assert len(canonical(item["view"])) == item["json_bytes"]
                assert digest not in views
                views[digest] = item["view"]
    assert len(views) == len(rows) == 24
    findings, opening = [], []
    for row in rows:
        view = views[row["view_sha256"]]
        actions = {a["action_key"]: a for a in view["actions"]}
        nodes = {n["node_key"]: n for n in view["nodes"]}
        ordered = sorted(row["entries"], key=lambda e: (-e["score"], e["action_key"]))
        if "hu" in actions:
            hu = next(e for e in ordered if e["action_key"] == "hu")
            continuation = next(e for e in ordered if e["action_key"] != "hu")
            root = nodes[actions[continuation["action_key"]]["node_key"]]
            current = nodes[actions["hu"]["node_key"]]["settlement"]
            entry = {"label": row["label"], "view_sha256": row["view_sha256"],
                "chosen": row["candidate_first"], "best_continue": continuation["action_key"],
                "current_hu_settlement": current, "hu_score": hu["score"],
                "continue_minus_hu": continuation["score"] - hu["score"],
                "full_trace": continuation["trace"], "continue_root_kind": root["kind"],
                "public_visible_state": view["visible_state"],
                "natural_strength_or_single_action_cause": False}
            if root["waiting"] is not None:
                waiting = root["waiting"]
                selected = continuation["trace"].get("diagnostic_target_full")
                entry["selected_target"] = None if selected is None else waiting["structure"][selected[0]]
                entry["natural_preparation"] = waiting["natural_preparation"]
                entry["qualification_unknown_codes"] = waiting["qualification_unknown_codes"]
                payments = waiting["normal_draw_hu_payments"]
                entry["next_draw_payments_analyzed"] = payments is not None
                if payments is not None:
                    seat = view["visible_state"]["seat"]
                    own = current["score_delta"][seat]
                    entry["next_draw_payment_rows"] = len(payments)
                    entry["next_draw_payments_above_current"] = sum(
                        p["settlement"]["score_delta"][seat] > own for p in payments)
                    entry["next_draw_fan_values"] = sorted(set(p["settlement"]["fan"] for p in payments))
            findings.append(entry)
        if row["label"] == "anchor:early-one-white-route-speed":
            for e in ordered:
                if e["action_key"] in ("discard:1w", "discard:中", "discard:9b"):
                    root = nodes[actions[e["action_key"]]["node_key"]]
                    w = root["waiting"]
                    opening.append({"action_key": e["action_key"], "score": e["score"], "trace": e["trace"],
                        "standard_shanten": w["structure"]["standard_shanten"],
                        "seven_pairs_shanten": w["structure"]["seven_pairs_shanten"],
                        "standard_useful_codes": w["standard_useful_codes"],
                        "seven_pairs_useful_codes": w["seven_pairs_useful_codes"],
                        "natural_preparation": w["natural_preparation"]})
    save(_project_file(_PROJECT_ROOT, HERE / "DIAGNOSTIC-SUMMARY.json"), {"complete": True, "public_states": 24,
        "hu_states": len(findings), "findings": findings, "opening_control": opening,
        "offer_tuple_fields": ["net", "channel", "upgrade", "downside", "maintained", "carry",
            "exposure", "remote", "remote_anchor_price", "fallback", "offer_value", "held_white_credit", "new_white_credit"],
        "files": {str(p): pin(p) for p in (Path(__file__), closedpath, rowpath, viewpath)},
        "new_scores_worlds_tables_models_HTTP": 0,
        "online_fix_or_natural_strength_admission": False})
    print(json.dumps({"complete": True, "hu_states": len(findings), "public_states": 24,
        "new_scores_worlds_tables_models_HTTP": 0}))


if __name__ == "__main__":
    main()
