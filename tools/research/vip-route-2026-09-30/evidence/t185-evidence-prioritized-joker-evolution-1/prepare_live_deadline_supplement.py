"""补足原压力七窗只有吃碰响应的覆盖；冻结两个既有官方片段的全部十二输入。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t185-evidence-prioritized-joker-evolution-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
import hashlib
import math
from pathlib import Path

from common import HERE, pin, save
import t185_close_development as dev

ORIGINS = (_project_file(_PROJECT_ROOT, HERE.parent / "t183-baotou-wait-case-a40864715552-1/WINDOW-AUDIT.jsonl"),
           _project_file(_PROJECT_ROOT, HERE.parent / "t184-white-strata-and-strong-gap-1/OPENING-ORIGINAL-AUDIT.jsonl"))


def cases():
    """原请求按输入出现顺序解码；不挑有利动作，不补规则事实，不改变原截止。"""
    from hangma_bot.application.audit_codec import decision_request_from_json, decision_budget_from_json
    result = []
    for path in ORIGINS:
        for raw in path.read_bytes().splitlines():
            row = dev.decode(raw)
            if row.get("kind") != "decision_input":
                continue
            request = decision_request_from_json(row["payload"]["request"])
            budget = decision_budget_from_json(row["payload"]["budget"])
            spans = tuple(getattr(budget,k) - row["monotonic_ns"]/1e9 for k in
                ("enhancement_deadline_monotonic", "fallback_deadline_monotonic", "latest_send_at_monotonic"))
            dev.require(all(math.isfinite(v) for v in spans) and 0 < spans[0] <= spans[1] <= spans[2],
                "原截止余量非正或不完整，不临时扩窗")
            result.append((request, spans, {"origin": str(path), "original_line_sha256": hashlib.sha256(raw).hexdigest(),
                "trigger_seq": row["context"]["trigger_seq"], "original_S02_score_not_new_gold_answer": True}))
    dev.require(len(result) == len({r[0].decision_id for r in result}) == 12, "两个官方片段原输入分母不是十二")
    return result


def main():
    """只保存十二原输入的索引；原七压力窗保持原字节，合计十九不冒称全场景覆盖。"""
    values = cases()
    rows = [{"decision_id": request.decision_id, "game_id": request.window_key.game_id,
        "phase": request.observation.phase, "legal_action_keys": [c.action_key for c in request.rules.legal_candidates],
        "original_remaining_ms_enhancement_fallback_latest_send": [v*1000 for v in spans], **source}
        for request,spans,source in values]
    dev.require(sum(r["phase"] == "draw" for r in rows) == 4, "补充摸打窗口缺失")
    from hangma_bot.application import audit_codec
    files = {str(p): pin(p) for p in (*ORIGINS, Path(__file__), Path(audit_codec.__file__), _project_file(_PROJECT_ROOT, HERE / "ORIGINAL-DEADLINE-INPUTS.json"))}
    save(_project_file(_PROJECT_ROOT, HERE / "LIVE-DEADLINE-SUPPLEMENT.json"), {"complete": True, "files": files, "rows": rows,
        "draw_windows": 4, "response_windows": 8, "total_with_original_pressure_windows": 19,
        "early_one_white_and_mature_baotou_are_development_diagnostics_not_independent_strength_confirmation": True,
        "new_rule_analyses_scores_worlds_tables_HTTP": 0, "deadline_admission": False})
    print("twelve_original_live_inputs_with_four_draw_windows_frozen_no_scoring")


if __name__ == "__main__":
    main()
