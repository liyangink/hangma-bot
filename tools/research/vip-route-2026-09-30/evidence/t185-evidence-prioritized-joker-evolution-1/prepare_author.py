"""闭合机制诊断后准备小范围作者材料；不含未来牌墙或确认来源。"""

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
import gzip
import json
from pathlib import Path

from hangma_bot.offline.vip_eoh_generate import VipEohBatch, build_vip_eoh_prompt
from common import HERE, ROOT, pin, save


def wait_summary(waiting, seat):
    """只摘公开事实，逐码支付写明抓打假设；这是摘要，不冒充完整DTO。"""
    if waiting is None:
        return None
    fields = ("structure", "standard_useful_codes", "seven_pairs_useful_codes", "natural_preparation",
              "natural_preparation_code_width", "target_improvement_code_widths", "unseen_capacities",
              "unseen_evidence", "legal_hu_draw_codes", "qualification_unknown_codes")
    result = {k: waiting[k] for k in fields}
    payments = waiting["normal_draw_hu_payments"]
    result["normal_draw_payment_summary_not_full_rows"] = None if payments is None else [
        {"draw_code": p["draw_code"], "catch_restricted": p["catch_restricted"],
         "capacity_before": p["draw_capacity_before"], "own_score_delta": p["settlement"]["score_delta"][seat]}
        for p in payments]
    return result


def main():
    """首批最多四作者，但先准备速度/增量两个明确机制，不执行API。"""
    path = _project_file(_PROJECT_ROOT, HERE / "mechanism-comparison-v2/CLOSURE.json")
    closure = json.loads(path.read_text())
    assert closure["complete"] and closure["source_stable"] and closure["actual_completed_views"] == 95
    assert all(pin(Path(p)) == h for p, h in closure["files"].items())
    assert all(pin(_project_file(_PROJECT_ROOT, ROOT / p)) == h for p, h in closure["source_manifest"].items())
    cases = {c["label"]: c for c in json.loads((_project_file(_PROJECT_ROOT, HERE / "CASES.json")).read_text())["cases"]}
    rows = {r["label"]: r for r in closure["rows"]}
    labels = ["anchor:early-one-white-route-speed", "anchor:mature-baotou-current-hu"]
    # 每类取冻结顺序首窗和每原型首个跨源改选；不按未来成功/胡大筛题。
    used_classes = set()
    used_change_sources = set()
    for row in closure["rows"]:
        if row["label"].startswith("anchor:"):
            continue
        new_classes = set(row["classes"]) - used_classes
        changed = any(c["meaningful"] for c in row["changes"].values())
        if (new_classes or (changed and row["root_id"] not in used_change_sources)) and len(labels) < 14:
            labels.append(row["label"])
            used_classes.update(row["classes"])
            if changed:
                used_change_sources.add(row["root_id"])
    views = {}
    needed = {rows[label]["view_sha256"] for label in labels}
    with gzip.open(_project_file(_PROJECT_ROOT, HERE / "mechanism-comparison-v2/views.jsonl.gz"), "rt") as stream:
        for line in stream:
            record = json.loads(line)
            if record["view_sha256"] in needed:
                views[record["view_sha256"]] = record["view"]
    assert set(views) == needed
    examples = []
    for label in labels:
        row, case = rows[label], cases[label]
        view = views[row["view_sha256"]]
        nodes = {n["node_key"]: n for n in view["nodes"]}
        roots = []
        seat = view["visible_state"]["seat"]
        for action in view["actions"]:
            node = nodes[action["node_key"]]
            roots.append({"action": action, "root_kind": node["kind"], "root_children": node["children"],
                "waiting_summary": wait_summary(node["waiting"], seat),
                "root_settlement": node["settlement"]})
        examples.append({"label_for_offline_feedback_only": label, "classes": row["classes"],
            "summary_not_complete_DTO": True, "visible_state": view["visible_state"],
            "node_count_is_computation_not_opportunities": len(view["nodes"]), "direct_root_summaries": roots,
            "full_view_sha256": row["view_sha256"], "all_actual_scores": row["scores"],
            "diagnostic_changes_not_win_labels": row["changes"]})
    base = {"baseline_source": (_project_file(_PROJECT_ROOT, HERE / "parent-source.py")).read_text(),
        "source_role": "S02字节精确参考，不是i1正式父代，旧包成绩不继承",
        "prototype_sources_unvalidated": {n: (_project_file(_PROJECT_ROOT, HERE / "prototypes" / (n + ".py"))).read_text() for n in ("speed", "incremental_wait", "joint")},
        "mechanism_results_not_strength": closure["summary"],
        "all_frozen_window_first_actions": [{"label_offline_only": r["label"], "classes": r["classes"],
            "first": {n: s["first"] for n, s in r["scores"].items()}} for r in closure["rows"]],
        "examples": examples,
        "human_priority": "抓住单白/双白的机会：自然结构要快、多路线要真的补充；已经能胡时保留价值不是新增价值；真实高番净收益可以覆盖合理普通效率损失。不能一律速胡或一律保白追大。",
        "unresolved": ["原型改选不证明积分提高", "容量包含他家暗牌，不是可摸概率", "他家先胡和更远取得白的概率未知",
            "需要跨源普通/七对/自然准备的负例", "牌山和庄位不能被一个白数阈值替代"],
        "mandatory_contract_reminder": "changed_branches为非空字符串而不是列表；禁用list.extend、import、while、递归、下标赋值、默认参数、注解。全合法根每根一个有限score和有界trace；未知不当零；不得用标签/牌局ID/期待弃牌作特判。",
        "scope": "只有当前公开开发DTO摘要/实际评分，不含隐藏世界、后续真实事件和确认来源；保留完全合同以实现所有节点类型"}
    directions = {
        "speed": "重点修正同速路线进张前沿、自然面子成型与备用信用。原型用相同最低向听普通/七对路线进张并集减已计支持，非重合慢路线四分之一信用；权重未验证，允许重新设计。必须联合价格高番目标，不只叠加宽度小奖，也不把低于五自然对的七对硬判非法。处理成熟Hu等待但不要把所有可胡强制止胡。",
        "incremental": "重点修正已可胡时真正新增支付与追加行动费用，去除已经获得的成熟用途重复奖励；已知下一摸升档、远端追加白/飘和可靠普通出口统一比较。原型把自然缺张为零的远目标增量降零、删carry，只是诊断，不要求照搬。须保留便宜真实升档反例，不能全胡优先或关闭多白潜力，也须兼顾早期路线速度。"}
    batch = VipEohBatch.read(_project_file(_PROJECT_ROOT, HERE / "AUTHOR-BATCH.json"))
    sizes = {}
    for name, direction in directions.items():
        feedback = json.dumps({**base, "mechanism_task": direction}, ensure_ascii=False, allow_nan=False)
        with (_project_file(_PROJECT_ROOT, HERE / f"AUTHOR-{name}-FEEDBACK.txt")).open("x") as stream:
            stream.write(feedback)
        packet, _ = build_vip_eoh_prompt(batch, "i1", [], feedback)
        sizes[name] = len(packet.text.encode())
        with (_project_file(_PROJECT_ROOT, HERE / f"AUTHOR-{name}-PREPARED-PROMPT.txt")).open("x") as stream:
            stream.write(packet.text)
    files = [path, _project_file(_PROJECT_ROOT, HERE / "mechanism-comparison-v2/views.jsonl.gz"), _project_file(_PROJECT_ROOT, HERE / "PLAN.json"), _project_file(_PROJECT_ROOT, HERE / "PROTOTYPES.json"),
        _project_file(_PROJECT_ROOT, HERE / "AUTHOR-BATCH.json"), _project_file(_PROJECT_ROOT, HERE / "parent-source.py"), _project_file(_PROJECT_ROOT, HERE / "glm_max_transport.py"), _project_file(_PROJECT_ROOT, HERE / "common.py"),
        Path(__file__), _project_file(_PROJECT_ROOT, HERE / "run_author.py")]
    files += [_project_file(_PROJECT_ROOT, HERE / f"AUTHOR-{n}-FEEDBACK.txt") for n in directions]
    save(_project_file(_PROJECT_ROOT, HERE / "AUTHOR-PREPARATION.json"), {"files": {str(p): pin(p) for p in files},
        "source_manifest": closure["source_manifest"], "initial_prepared_directions": list(directions),
        "maximum_actual_calls": 4, "new_calls": 0, "operator": "i1", "parent_paths": [],
        "prompt_utf8_bytes_not_precise_tokens": sizes, "reasoning_requested": {"thinking": {"type": "enabled"}, "reasoning_effort": "max"},
        "full_table_strength_or_publication_admitted": False, "examples": labels,
        "subsequent_joint_call_requires_closed_actual_first_two_feedback": True})
    print({"author_material_prepared": True, "prompt_bytes": sizes, "new_model_calls": 0}, flush=True)


if __name__ == "__main__":
    main()
