"""作者与完整桌反馈后仍沿用原七份压力输入及原截止；只冻结输入，不评分。"""

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
import importlib.util
import json
import math
from pathlib import Path

from common import HERE, ROOT, pin, save


def main():
    """调用已核真实工厂的输入解码，记录原预算；不把S02分数当新候选金答案。"""
    origin = _project_file(_PROJECT_ROOT, HERE.parent / "t179-production-wiring-1/probe_real_factory.py")
    spec = importlib.util.spec_from_file_location("t185_original_deadline_case_reader", origin)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    cases = module.cases()
    files = {str(p): pin(p) for p in (Path(__file__), origin,
        _project_file(_PROJECT_ROOT, HERE.parent / "t173-joint-exact-equivalence-1/joint-actual-001/JOINT-RESULT.json"))}
    inputs = sorted((_project_file(_PROJECT_ROOT, HERE.parent / "t169-closed-state-pressure-1")).glob("dec-*.json"))
    files.update({str(p): pin(p) for p in inputs})
    from hangma_bot.application import audit_codec
    from hangma_bot.policy import route_vip_heuristic
    files.update({str(Path(m.__file__)): pin(Path(m.__file__)) for m in (audit_codec, route_vip_heuristic)})
    rows = []
    for request, spans, reference in cases:
        assert all(math.isfinite(v) for v in spans) and 0 < spans[0] <= spans[1] <= spans[2]
        assert [v*1000 for v in spans] == reference["original_remaining_ms"]
        assert type(request.observation.phase) is str
        rows.append({"decision_id": request.decision_id, "game_id": request.window_key.game_id,
            "phase": request.observation.phase, "legal_action_keys": [c.action_key for c in request.rules.legal_candidates],
            "original_remaining_ms_enhancement_fallback_latest_send": [v*1000 for v in spans],
            "original_input_sha256": reference["original_input_sha256"],
            "old_S02_scores_are_not_new_candidate_expected_scores": True})
    assert len(rows) == len(inputs) == 7 and len({r["decision_id"] for r in rows}) == 7
    save(_project_file(_PROJECT_ROOT, HERE / "ORIGINAL-DEADLINE-INPUTS.json"), {"complete": True, "files": files, "rows": rows,
        "source": "既有闭合T169原请求；T179真实生产工厂已核的同一输入解码",
        "budget_rule": "只把原三段相对单调截止平移到新请求时刻，不增加任何原窗口余量",
        "formula_rule": "胜者Python完整计划先作本候选参考，再核原体编译全分值、解释、排序和操作数一致",
        "runtime_rule": "独立每桌预热计算、实际返回且资源归零；冷启动和并发另列，不继承S02原时限结果",
        "new_rule_analyses_scores_worlds_tables_or_HTTP": 0, "deadline_admission": False})
    print("seven_original_inputs_and_original_budget_spans_frozen_no_scoring")


if __name__ == "__main__":
    main()
