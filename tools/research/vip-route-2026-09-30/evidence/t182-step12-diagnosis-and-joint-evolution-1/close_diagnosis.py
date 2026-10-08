"""整批七目标闭合后读取三臂贡献；来源重复、未知和负例均保留。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t182-step12-diagnosis-and-joint-evolution-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
import json
from pathlib import Path
from prepare_diagnostics import pin, save

HERE = Path(__file__).resolve().parent


def account(result):
    """单局/续桌积分账，顺序固定物理座位0—3；大牌按至少四番。"""
    a = {"net": 0, "ordinary_hu_income": 0, "large_hu_income": 0, "payments": 0,
         "other_wins": 0, "draws": 0, "own_dealer_net": 0, "own_non_dealer_net": 0}
    for s in result["settlements"]:
        delta = s["score_delta"]
        assert len(delta) == 4 and all(type(v) is int for v in delta) and sum(delta) == 0
        a["net"] += delta[0]
        a["own_dealer_net" if s["dealer_seat"] == 0 else "own_non_dealer_net"] += delta[0]
        if s["is_draw"]:
            assert delta == [0, 0, 0, 0]
            a["draws"] += 1
        elif s["winner_seat"] == 0:
            assert delta[0] > 0
            a["large_hu_income" if s["fan"] >= 4 else "ordinary_hu_income"] += delta[0]
        else:
            assert delta[0] <= 0
            a["payments"] += delta[0]
            a["other_wins"] += 1
    assert a["net"] == result["focal_net_score"] == a["ordinary_hu_income"] + a["large_hu_income"] + a["payments"]
    return a


def main():
    """七原终态齐才读结果，不按中途分数补题或改原型。"""
    plan = json.loads((_project_file(_PROJECT_ROOT, HERE / "CAUSAL-PLAN.json")).read_text())
    panels = [json.loads((_project_file(_PROJECT_ROOT, HERE / d / "CLOSURE.json")).read_text()) for d in
              ("mechanism-comparison", "mechanism-comparison-supplement")]
    assert all(p["complete"] and p["source_stable"] for p in panels)
    files = {str(_project_file(_PROJECT_ROOT, HERE / "CAUSAL-PLAN.json")): pin(_project_file(_PROJECT_ROOT, HERE / "CAUSAL-PLAN.json"))}
    comparisons, totals = [], {}
    roots = set()
    for index, target in enumerate(plan["targets"], 1):
        path = _project_file(_PROJECT_ROOT, HERE / "causal-continuations" / f"target-{index:03d}" / "CLOSURE.json")
        closed = json.loads(path.read_text())
        assert closed["complete"] and closed["source_stable"] and closed["capture"]["terminal"]["terminal_valid"]
        files[str(path)] = pin(path)
        roots.add(target["case"]["root_id"])
        for name, n in closed["counts"].items():
            totals[name] = totals.get(name, 0) + n
        results = closed["results"]
        for endpoint in sorted({r["endpoint"] for r in results}):
            for sample in sorted({r["sample"] for r in results if r["endpoint"] == endpoint}):
                arms = {r["arm"]: r for r in results if (r["sample"], r["endpoint"]) == (sample, endpoint)}
                baseline = account(arms["A"])
                for arm, result in arms.items():
                    if arm == "A":
                        continue
                    own = account(result)
                    contrast = {k: own[k] - baseline[k] for k in baseline}
                    row = {"target": index, "root_id": target["case"]["root_id"], "case": target["case"]["label"],
                           "role": target["role"], "sample": sample, "endpoint": endpoint,
                           "arm": arm, "account": own, "A_account": baseline, "minus_A": contrast,
                           "actual_new_continuation": result["actual_new_continuation"]}
                    if arm.startswith("C:"):
                        b = account(arms["B:" + arm[2:]])
                        row["minus_B"] = {k: own[k] - b[k] for k in own}
                    comparisons.append(row)
    assert totals["single_hand_dispatched"] <= 336 and totals["remaining_table_dispatched"] <= 14
    summary = {"schema": "t182-diagnosis-closed/1", "complete": True, "files": files,
        "panel_mother_sources": 12, "panel_windows": sum(len(p["rows"]) for p in panels),
        "panel_full_score_calls": sum(sum(p["counts"]["score_attempts"].values()) for p in panels),
        "prototype_first_changes": {n: sum(p["changed_windows"][n] for p in panels) for n in ("natural", "pay", "pressure")},
        "causal_targets": len(plan["targets"]), "causal_mother_sources": len(roots),
        "causal_actual_counts": totals, "comparisons": comparisons,
        "sampler_scope": plan["sampler_interpretation"], "new_model_calls": 0,
        "strength_or_formal_deadline_admission": False,
        "remaining_unknowns": ["4个等权隐藏样本不是真实胡牌概率或历史动作后验",
            "少来源分歧不能宣布某机制普遍增分；需新联合候选完整桌开发及独立确认",
            "历史三处原线上评分有脱敏解释，只有数值与存活解释字段完整核对",
            "未对历史四母源或原线上三窗恢复完整反事实世界，其因果贡献未知"]}
    save(_project_file(_PROJECT_ROOT, HERE / "DIAGNOSIS-CLOSED.json"), summary)
    print({k: summary[k] for k in ("complete", "panel_windows", "prototype_first_changes", "causal_targets", "causal_mother_sources", "causal_actual_counts")})


if __name__ == "__main__":
    main()
