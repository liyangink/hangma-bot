"""从已闭条件原件分组诊断等待与弃牌，不重算分数、不作单动作因果推断。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t186-incremental-opportunity-repair-1'

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
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
PRIOR = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t185-evidence-prioritized-joker-evolution-1')
sys.path.insert(0, str(PRIOR))
from common import canonical, pin, save


def main():
    """白数取分歧前依法可见的手牌；原历史、四条件世界分别累加实际结算。"""
    source = _project_file(_PROJECT_ROOT, HERE / "JOINT-REVISION-CONDITION-CLOSED.json")
    planpath = _project_file(_PROJECT_ROOT, HERE / "JOINT-REVISION-CONDITION-PLAN.json")
    viewsfile = _project_file(_PROJECT_ROOT, HERE / "joint-revision-qualification/views.jsonl.gz")
    closed, plan = (json.loads(p.read_text()) for p in (source, planpath))
    assert closed["complete"] and closed["resources_released"] and closed["plan_pin"] == pin(planpath)
    views, details, gaps = {}, Counter(), []
    with gzip.open(viewsfile, "rt") as stream:
        for line in stream:
            record = json.loads(line)
            assert hashlib.sha256(canonical(record["view"])).hexdigest() == record["view_sha256"]
            view = record["view"]
            assert record["view_sha256"] not in views
            views[record["view_sha256"]] = view
            nodes = {n["node_key"]: n for n in view["nodes"]}
            for root in view["actions"]:
                node = nodes[root["node_key"]]
                if node["kind"] != "hu":
                    continue
                text = tuple(node["settlement"]["details"])
                details[text] += 1
                marked = any(d in ("爆头", "财飘") for d in text)
                other_white = any(d in ("双财飘", "三财飘") or d.startswith(("连飘×", "杠飘链×")) for d in text)
                if other_white and not marked:
                    gaps.append({"view_sha256": record["view_sha256"], "action_key": root["action_key"],
                        "fan": node["settlement"]["fan"], "details": list(text)})
    groups = {"first_action_kinds": {}, "public_white_count": {}}
    rows = []
    for target, summary in zip(plan["targets"], closed["target_summaries"]):
        assert target["case"]["label"] == summary["label"]
        view = views[target["case"]["view_sha256"]]
        state = view["visible_state"]
        # 公开观察把本次摸入牌单列，不在my_hand内；须计入可用于胡/弃的白。
        assert state["hand_counts"][state["seat"]] == len(state["my_hand"]) + int(state["drawn_tile"] is not None)
        white = state["my_hand"].count("白") + int(state["drawn_tile"] == "白")
        assert 0 <= white <= 4
        kind = summary["parent_first"].split(":")[0] + "→" + summary["candidate_first"].split(":")[0]
        row = {"target": summary["target"], "label": summary["label"], "root_id": summary["root_id"],
            "white_count_before_choice": white, "first_action_kinds": kind,
            "historical_delta": summary["historical"]["C_minus_A"],
            "four_conditional_delta_sum": summary["four_conditional"]["sum_C_minus_A"]}
        rows.append(row)
        for grouping, key in (("first_action_kinds", kind), ("public_white_count", str(white))):
            group = groups[grouping].setdefault(key, {"targets": 0, "root_ids": set(),
                "historical": Counter(), "four_conditional": Counter()})
            group["targets"] += 1
            group["root_ids"].add(summary["root_id"])
            group["historical"].update(row["historical_delta"])
            group["four_conditional"].update(row["four_conditional_delta_sum"])
    for mapping in groups.values():
        for group in mapping.values():
            group["root_ids"] = sorted(group["root_ids"])
            group["historical"] = dict(group["historical"])
            group["four_conditional"] = dict(group["four_conditional"])
    for grouping, mapping in groups.items():
        assert sum(g["targets"] for g in mapping.values()) == 32
        for field, key in (("historical", "historical_exposed"), ("four_conditional", "public_compatible_uniform")):
            total = Counter()
            for group in mapping.values():
                total.update(group[field])
            assert dict(total) == closed[key]["sum_C_minus_A"]
    output = _project_file(_PROJECT_ROOT, HERE / "JOINT-CONDITION-MECHANISM-READBACK-008.json")
    assert not output.exists()
    save(output, {"complete": True, "source_pin": pin(source), "plan_pin": pin(planpath),
        "qualification_views_pin": pin(viewsfile), "reader_pin": pin(Path(__file__)),
        "groups": groups, "rows": rows,
        "current_hu_marker_audit": {"views": len(views), "current_hu_root_nodes": sum(details.values()),
            "details_counts": [{"details": list(k), "count": v} for k, v in sorted(details.items())],
            "white_chain_current_hu_without_exact_marker": gaps,
            "covers_only_closed_public_panel_not_all_legal_states": True,
            "binary_proxy_not_precise_real_settlement_increment": True},
        "persistent_policy_pair_not_first_action_causal_effect": True,
        "first_action_kind_groups_not_disjoint_module_attributions": True,
        "no_natural_frequency_or_strength_admission": True,
        "new_scores_worlds_tables_models_HTTP": 0})
    print(json.dumps({"complete": True, "groups": groups, "marker_gaps": len(gaps)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
