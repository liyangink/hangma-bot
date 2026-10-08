"""以完整32来源及正式父代作用范围准备一次联合公式修订，不调用模型。"""

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
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PRIOR = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t185-evidence-prioritized-joker-evolution-1')
sys.path.insert(0, str(PRIOR))
from common import canonical, pin, save
from hangma_bot.offline.vip_eoh_generate import VipEohBatch, build_vip_eoh_prompt, load_vip_parents


def main():
    """全阶段及路径自然闭合后压缩正负反馈；保持来源与真实父代身份可核。"""
    target = _project_file(_PROJECT_ROOT, HERE / "AUTHOR-JOINT-REVISION-PREPARATION-v2.json")
    assert not target.exists()
    budgetpath = _project_file(_PROJECT_ROOT, HERE / "STAGE-003-BUDGET-DECISION-006.json")
    totalpath = _project_file(_PROJECT_ROOT, HERE / "natural-stage-003-dispatch/CUMULATIVE-SUMMARY.json")
    scopepath = _project_file(_PROJECT_ROOT, HERE / "FORMAL-PARENT-SCOPE-READBACK-006.json")
    pathdir = _project_file(_PROJECT_ROOT, HERE / "natural-stage-003-paths")
    pathclosed = pathdir / "CLOSED.json"
    budget, total, scope, paths = [json.loads(p.read_text()) for p in (budgetpath, totalpath, scopepath, pathclosed)]
    assert all(d["complete"] for d in (budget, total, scope, paths))
    assert budget["independent_roots"] == total["independent_roots"] == 32
    assert not total["independent_confirmation_budget_eligible"] and not total["optional_64_source_development_budget_eligible"]
    assert paths["actual_paired_tables_read"] == 64 and paths["source_stable"]
    assert scope["actual_scores"] == 112 and scope["without_current_hu_cases"] == 42
    assert scope["without_current_hu_full_numeric_scores_equal"]
    batchpath = _project_file(_PROJECT_ROOT, HERE / "AUTHOR-BATCH.json")
    batch = VipEohBatch.read(batchpath)
    parent = _project_file(_PROJECT_ROOT, HERE / "AUTHOR-resource-release-metadata-repaired")
    parents = load_vip_parents([parent], batch)
    assert parents[0]["identity"] == total["candidate_identity"]
    ledgerpath = _project_file(_PROJECT_ROOT, HERE / "AUTHOR-BATCH.vip-eoh-ledger.json")
    ledger = json.loads(ledgerpath.read_text())
    assert all(r["status"] == "settled" for r in ledger["reservations"])
    charged = {k: sum(r["charged"][k] for r in ledger["reservations"]) for k in ledger["budgets"]}
    assert charged["model_calls"] == 1 and ledger["budgets"]["model_calls"] == 2
    draftpath = _project_file(_PROJECT_ROOT, HERE / "AUTHOR-NEXT-FEEDBACK-DRAFT.json")
    draft = json.loads(draftpath.read_text())
    assert all(pin(Path(p)) == h for p, h in draft["files"].items())
    files = {str(p): pin(p) for p in (Path(__file__), budgetpath, totalpath, scopepath, pathclosed,
        draftpath, _project_file(_PROJECT_ROOT, HERE / "AUTHOR-NEXT-FEEDBACK-DRAFT.txt"), batchpath, ledgerpath,
        parent / "generation.json", parent / "candidate.py", _project_file(_PROJECT_ROOT, PRIOR / "glm_max_transport.py"))}
    rowsfile = pathdir / "rows.jsonl"
    publicfile = pathdir / "original-public-first-rows.jsonl.gz"
    assert paths["rows_pin"] == pin(rowsfile) and paths["public_rows_pin"] == pin(publicfile)
    rows = [json.loads(line) for line in rowsfile.read_text().splitlines()]
    selected = set()
    # 选择新增块两个大牌负来源及最高净正来源，保留明确的事后选择边界。
    for root, negative in ((19, True), (20, True), (24, False)):
        choices = [r for r in rows if r["root"] == root and r["status"] == "first_divergence"]
        assert choices
        choices.sort(key=lambda r: (r["first_hand_delta"]["large_income"], r["table_delta"]["large_hu_income"], r["table_delta"]["net"], r["rotation"]))
        chosen = choices[0] if negative else max(choices, key=lambda r: (r["table_delta"]["net"], -r["rotation"]))
        selected.add((root, chosen["rotation"]))
    accounts = {(r["root"], r["rotation"]): r for r in rows}
    cards = list(draft["cards"])
    with gzip.open(publicfile, "rt") as stream:
        for line in stream:
            record = json.loads(line)
            pair = (record["root"], record["rotation"])
            if pair not in selected:
                continue
            a, b = record["parent_original_row"], record["child_original_row"]
            row = accounts[pair]
            relevant = {a["selected_action_key"], b["selected_action_key"]}
            def scores(original):
                return [{"action_key": e["action_key"], "score": e["score"], "detail": e["trace"]["detail"]}
                        for e in original["candidates"] if e["action_key"] in relevant]
            cards.append({"label": f"known-development:{pair[0]:03d}:{pair[1]}",
                "visible_state_excerpt": {k: a["observation"][k] for k in (
                    "seat", "dealer_seat", "my_hand", "drawn_tile", "melds", "discards", "remaining_tile_count", "rule_state")},
                "white_count": a["white_count"], "original_legal_root_keys": a["legal_action_keys"],
                "S02_selected": a["selected_action_key"], "357e_selected": b["selected_action_key"],
                "S02_original_scores": scores(a), "357e_original_scores": scores(b),
                "associated_complete_table_delta": row["table_delta"],
                "associated_first_hand_delta": row["first_hand_delta"],
                "aligned_round_large_loss_observations": row["aligned_round_large_loss_observations"],
                "posthoc_selected_development_card_not_single_action_cause_or_required_answer": True})
    assert len(cards) == 9
    for p in (rowsfile, publicfile):
        files[str(p)] = pin(p)
    assert all(pin(Path(p)) == h for p, h in paths["files"].items())
    packet = {"formal_parent_candidate_id": parents[0]["identity"]["candidate_id"],
              "fixed_source_count": 32, "actual_complete_tables": 256,
              "mean_delta_per_complete_table": total["mean_delta_per_complete_table"],
              "exploratory_interval_not_final_confirmation": total["net_exploratory_source_bootstrap95"],
              "maximum_positive_source_removed_net_mean": total["net_mean_excluding_maximum_positive_source"],
              "new_block_net_mean": total["new_block_net_direction"],
              "large_positive_independent_roots": total["positive_large_income_sources"],
              "formal_parent_scope": {"actual_scores": 112, "without_hu_numeric_equal_cases": 42,
                                      "changed_independent_root_count": 1},
              "stage3_first_switch_groups_observational_not_causal": paths["by_first_switch"],
              "cards": cards, "confirmation_pool_not_read_or_included": True, "current_hu_plain_counterexample": {"root": 19, "rotation": 1, "window_round_no": 4, "window_trigger_seq": 835, "captured_view_sha256": "9ddfaca757d180551dad0432cab82a1d2783aa9e1aa54337148b04f64d03e1cc", "current_hu_settlement": {"details": ["平胡"], "fan": 1, "score_delta": [-8, 10, -1, -1]}, "cause_not_proved": True}}
    text = (_project_file(_PROJECT_ROOT, HERE / "AUTHOR-NEXT-FEEDBACK-DRAFT.txt")).read_text()
    text += """

【现在是作者正式开发反馈；前文的草稿待补要求已由以下32来源及112范围评分补齐】
本次不是仅调等待阈值。正式357e父代的jointwait和waitvalue沿用了9adb弃牌聚合：
frontextra=max(0,front_value-main_value)再相加；可能压平某些主路线差异。
这不等于max本身有错，也不证明同分的某一个动作应当被强制选择。请联合解释并
修订自然成型速度、保白目标与备用路线信用，审视相互重叠和主路线已含信用，
保留对七对子、高番成熟度及不同动作窗的适当取舍，不能按诊断题牌码查表。
继续保留已持财神被自然进张释放的机会；不要用普遍延迟胡来补偿弃牌缺陷。
公开容量、墙余、副露、庄位都只是合同事实，未知他家胡率不伪装成概率。
若损失单局的实际起手已不同，不能当成同手同动作反事实；整桌后继收益仅用于
综合开发结账。九卡是事后压缩诊断集，不是九个规定正确答案。
另一个事实反例：来源019双白可胡窗口的合法hu节点settlement明细只有平胡、fan=1，
但父代RELEASEBASEWHITE=1及注释都按已兑现一次爆头扣PURPOSES[1]。
该注释假设并非所有当前胡都成立。请核当前胡已经兑现的价值与保白代理增量，
参考合同中合法胡节点已有的公开settlement，而非按白数猜已实现的番值；
这是待修估值假设，不是单独已证损失原因，也不是要求该窗口无条件继续。
请用清晰、可计量且尽量窄的联合排序公式；所有合法根和所有机械动作族覆盖保留。
完整标准提示中的父代摘要才是parent_differences唯一真实candidate_id。
"""
    text += "\n开发证据JSON（不含未来牌墙或他家暗牌）：\n" + canonical(packet).decode() + "\n"
    feedbackpath = _project_file(_PROJECT_ROOT, HERE / "AUTHOR-JOINT-REVISION-FEEDBACK-v2.txt")
    assert not feedbackpath.exists()
    feedbackpath.write_text(text, encoding="utf-8")
    prompt, _ = build_vip_eoh_prompt(batch, "m1", parents, text)
    files[str(feedbackpath)] = pin(feedbackpath)
    result = {"complete": True, "formal_parent_identity": parents[0]["identity"], "operator": "m1",
              "actual_previous_model_calls": 1, "maximum_author_calls": 2,
              "previous_actual_charged": charged, "files": files,
              "compact_development_cards": len(cards), "prompt_utf8_bytes_not_precise_tokens": len(prompt.text.encode()),
              "prompt_sha256": prompt.sha256, "new_scores_worlds_tables_models_HTTP": 0,
              "confirmation_pool_not_read": True, "source_and_original_deadline_admission": False}
    assert all(pin(Path(p)) == h for p, h in files.items())
    save(target, result)
    print(json.dumps({"complete": True, "compact_cards": len(cards),
                      "prompt_utf8_bytes": result["prompt_utf8_bytes_not_precise_tokens"], "new_API_calls": 0}))


if __name__ == "__main__":
    main()
