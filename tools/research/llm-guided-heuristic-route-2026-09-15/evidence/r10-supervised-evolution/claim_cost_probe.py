"""非推进鸣牌代价的真实例子、合成边界和关闭机制消融；零模拟、零作者。"""
from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

import argparse
import json
from dataclasses import replace
from pathlib import Path

import collect_real_disagreements as base
import sitin_real_behavior as behavior

HERE = Path(__file__).resolve().parent


def probe(parent_source, child_source):
    """只通过公开受限评分器评分；临时关闭常量只作消融，不登记为候选源码。"""
    parent = base.ActionValueScorer("parent", parent_source)
    child = base.ActionValueScorer("candidate", child_source)
    declaration = "NONADVANCE_COST = 1.5"
    assert child_source.count(declaration) == 1
    ablated = base.ActionValueScorer("diagnostic-ablation-only", child_source.replace(declaration, "NONADVANCE_COST = 0.0"))
    _, windows = behavior.load_panel(_project_file(_PROJECT_ROOT, HERE / "batch03-known-root-diagnostic/panel.json"))
    requests = dict(windows)
    for _, request in windows:
        view = behavior.build_scoring_view(request)
        p, a = parent.score(view), ablated.score(view)
        assert p.status == a.status == "SCORED"
        assert {e.action_key: e.score for e in p.entries} == {e.action_key: e.score for e in a.entries}
    case = behavior.build_scoring_view(requests["ca5aa75c35ec39d2d4cdc1023e424adf734a970da4f95445bf81d43ab012914f"])
    improving = behavior.build_scoring_view(requests["93f26c414afa4732e51de5bf42be11fe08231040e037735a51d3932e74113188"])
    cases = [("real_equal_shanten", case, True), ("real_improving_shanten", improving, False),
        ("synthetic_no_pass", replace(case, actions=tuple(a for a in case.actions if a.action_type != "pass")), False),
        ("synthetic_unknown_pass_shanten", replace(case, actions=tuple(replace(a, shanten_after=None)
            if a.action_type == "pass" else a for a in case.actions)), False),
        ("synthetic_unknown_claim_shanten", replace(case, actions=tuple(replace(a, shanten_after=None)
            if a.action_type in ("chi", "peng") else a for a in case.actions)), False)]
    results = []
    for name, view, expect in cases:
        p, c = parent.score(view), child.score(view)
        assert p.status == c.status == "SCORED"
        before = {e.action_key: e.score for e in p.entries}
        action_types = {a.action_key: a.action_type for a in view.actions}
        for entry in c.entries:
            is_claim = action_types[entry.action_key] in ("chi", "peng")
            assert bool(entry.trace["nonadvance_cost_applied"]) == (is_claim and expect)
            assert abs(entry.score - (before[entry.action_key] - (1.5 if is_claim and expect else 0.0))) < 1e-10
        results.append({"case": name, "expected_cost_trigger": expect,
            "parent_scores": before, "child_scores": {e.action_key: e.score for e in c.entries}})
    return {"cases": results, "ablation_matches_parent_windows": len(windows),
        "ablation_source_was_only_temporary_diagnostic": True, "selection_eligible": False,
        "release_eligible": False, "limitations": "真实窗口非随机采样；合成边界不是规则生成局面；未验证赛事效果"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parent", required=True, type=Path)
    parser.add_argument("--candidate", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    if args.out.exists():
        raise SystemExit("不覆盖历史探针")
    result = probe(args.parent.read_text(), args.candidate.read_text())
    with args.out.open("x") as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print(json.dumps({"cases": len(result["cases"]), "ablation_matches_parent_windows": result["ablation_matches_parent_windows"]}))
