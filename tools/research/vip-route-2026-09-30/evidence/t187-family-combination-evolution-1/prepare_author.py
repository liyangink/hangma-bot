"""T187复核两个真实父代并封存平衡诊断反馈；不调用模型或启动牌局。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t187-family-combination-evolution-1'

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
LAST = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t186-incremental-opportunity-repair-1')
sys.path.insert(0, str(PRIOR))
from common import canonical, pin, save
from hangma_bot.offline.vip_eoh_generate import VipEohBatch, build_vip_eoh_prompt, load_vip_parents


def main():
    """核身份与既有闭合，排他新建独立费用批次；确认池不读取、不参与提示。"""
    target = _project_file(_PROJECT_ROOT, HERE / "AUTHOR-PREPARATION.json")
    assert not target.exists()
    batchpath = _project_file(_PROJECT_ROOT, HERE / "AUTHOR-BATCH.json")
    batchraw = json.loads((_project_file(_PROJECT_ROOT, LAST / "AUTHOR-BATCH.json")).read_text())
    batchraw["batch_id"] = "t187-two-author-family-combination-20261005"
    if batchpath.exists():
        assert json.loads(batchpath.read_text()) == batchraw
    else:
        save(batchpath, batchraw)
    batch = VipEohBatch.read(batchpath)
    parentpaths = [_project_file(_PROJECT_ROOT, PRIOR / "AUTHOR-speed-model-output"), _project_file(_PROJECT_ROOT, LAST / "AUTHOR-joint-revision-model-output")]
    parents = load_vip_parents(parentpaths, batch)
    expected = ["6876373ea66c9b0a0bd25743517bb1ddacd0742e61822a6a0efd0abc5c157c28",
                "a0c7218a27983bf515ad9c1f5270188fffaec1a99137725036c7e56cc2eda42f"]
    assert [p["identity"]["candidate_id"] for p in parents] == expected
    assert parents[0]["identity"]["deps_digest"] == parents[1]["identity"]["deps_digest"]
    gates = [_project_file(_PROJECT_ROOT, PRIOR / "AUTHOR-speed-model-output-qualification/CLOSURE.json"),
             _project_file(_PROJECT_ROOT, LAST / "joint-revision-qualification/CLOSED.json")]
    files = {str(p): pin(p) for p in [Path(__file__), _project_file(_PROJECT_ROOT, HERE / "run_author.py"), batchpath,
        _project_file(_PROJECT_ROOT, PRIOR / "glm_max_transport.py"), _project_file(_PROJECT_ROOT, LAST / "AUTHOR-BATCH.json"), _project_file(_PROJECT_ROOT, LAST / "AUTHOR-BATCH.vip-eoh-ledger.json")]}
    for parentpath, parent, gatepath in zip(parentpaths, parents, gates):
        gate = json.loads(gatepath.read_text())
        assert gate["complete"] and gate["mechanical_passed"] and gate["source_stable"]
        assert gate["identity"] == parent["identity"]
        if gatepath == gates[1]:
            gateplanpath = _project_file(_PROJECT_ROOT, LAST / "JOINT-REVISION-QUALIFICATION-PLAN.json")
            assert gate["plan_pin"] == pin(gateplanpath)
            gatefiles = json.loads(gateplanpath.read_text())["files"]
            files[str(gateplanpath)] = pin(gateplanpath)
        else:
            gatefiles = gate["files"]
        assert all(pin(Path(p)) == h for p, h in gatefiles.items())
        for p in (parentpath / "candidate.py", parentpath / "generation.json", gatepath):
            files[str(p)] = pin(p)
    oldledger = json.loads((_project_file(_PROJECT_ROOT, LAST / "AUTHOR-BATCH.vip-eoh-ledger.json")).read_text())
    assert all(r["status"] == "settled" for r in oldledger["reservations"])
    assert sum(r["charged"]["model_calls"] for r in oldledger["reservations"]) == 2
    totalpath = _project_file(_PROJECT_ROOT, LAST / "joint-natural-stage-001-dispatch/SUMMARY.json")
    pathclosed = _project_file(_PROJECT_ROOT, LAST / "joint-natural-stage-001-paths/CLOSED.json")
    rowsfile = _project_file(_PROJECT_ROOT, LAST / "joint-natural-stage-001-paths/rows.jsonl")
    publicfile = _project_file(_PROJECT_ROOT, LAST / "joint-natural-stage-001-paths/original-public-first-rows.jsonl.gz")
    total, closed = [json.loads(p.read_text()) for p in (totalpath, pathclosed)]
    assert total["complete"] and total["actual_complete_tables"] == 64 and total["actual_focal_scores"] == 24646
    assert closed["complete"] and closed["actual_paired_tables_read"] == 32
    assert closed["rows_pin"] == pin(rowsfile) and closed["public_rows_pin"] == pin(publicfile)
    accounts = {(r["root"], r["rotation"]): r for r in map(json.loads, rowsfile.read_text().splitlines())}
    selected = {(38, 0), (40, 0), (35, 3)}
    cards = []
    with gzip.open(publicfile, "rt") as stream:
        for line in stream:
            record = json.loads(line)
            pair = (record["root"], record["rotation"])
            if pair not in selected:
                continue
            a, b = record["parent_original_row"], record["child_original_row"]
            relevant = {a["selected_action_key"], b["selected_action_key"]}
            def scores(original):
                return [{"action_key": e["action_key"], "score": e["score"], "detail": e["trace"]["detail"]}
                        for e in original["candidates"] if e["action_key"] in relevant]
            cards.append({"label": f"exposed-development:{pair[0]:03d}:{pair[1]}",
                "visible_state_excerpt": {k: a["observation"][k] for k in (
                    "seat", "dealer_seat", "my_hand", "drawn_tile", "melds", "discards", "remaining_tile_count", "rule_state")},
                "white_count_including_drawn_tile": a["white_count"], "legal_root_keys": a["legal_action_keys"],
                "S02_selected": a["selected_action_key"], "a0_selected": b["selected_action_key"],
                "S02_original_scores": scores(a), "a0_original_scores": scores(b),
                "associated_first_hand_delta": accounts[pair]["first_hand_delta"],
                "aligned_round_large_loss_observations": accounts[pair]["aligned_round_large_loss_observations"],
                "posthoc_diagnostic_not_single_action_cause_or_required_answer": True})
    assert len(cards) == 3
    draftpath = _project_file(_PROJECT_ROOT, LAST / "AUTHOR-NEXT-FEEDBACK-DRAFT.json")
    draft = json.loads(draftpath.read_text())
    for label in ("known-development:002:0", "known-development:003:2", "known-development:015:2"):
        cards.append(next(c for c in draft["cards"] if c["label"] == label))
    conditionpath = _project_file(_PROJECT_ROOT, LAST / "JOINT-REVISION-CONDITION-CLOSED.json")
    condition = json.loads(conditionpath.read_text())
    assert condition["complete"] and condition["source_stable"]
    for p in (totalpath, pathclosed, rowsfile, publicfile, draftpath, conditionpath):
        files[str(p)] = pin(p)
    familyfile = _project_file(_PROJECT_ROOT, PRIOR / "DEVELOPMENT-READOUT-SUMMARY-011.json")
    familydata = json.loads(familyfile.read_text())
    assert familydata["complete"]
    family = next(c for c in familydata["candidates"] if c["candidate_id"] == expected[0])
    files[str(familyfile)] = pin(familyfile)
    packet = {"ordered_actual_parent_candidate_ids": expected,
        "6876_closed_development_mean_delta_vs_S02": family["mean_delta"],
        "6876_exploratory_interval_not_final_confirmation": family["net_source_bootstrap95"],
        "a0_closed_natural_mean_delta_vs_S02": total["mean_delta_per_complete_table"],
        "a0_exploratory_interval_not_final_confirmation": total["net_exploratory_source_bootstrap95"],
        "first_switch_associations_not_causal": closed["by_first_switch"],
        "a0_condition_historical": condition["historical_exposed"],
        "a0_condition_uniform_compatible_not_natural": condition["public_compatible_uniform"],
        "cards": cards, "confirmation_pool_not_read": True}
    text = """本次是e2多父联合机制组合，交付一套完整score_actions；不是只调常数或继续扩大a0。
父A为同速进张家族6876：已闭32来源128配对开发净+6.7421875/桌，普通收入-5.59375、
四番以上+10.5625、支付+1.7734375，探索区间约[-8.45,+22.72]，未独立证强。
父B为a0：333状态666完整评分机械通过；条件题里部分双白等待升番，但新自然64桌
净-10.34375、大牌-14，不合格。各版来源不同，不能把这些数字当两父直接排名。
保留A的多路线/大牌探索思想，吸收B读取实际当前胡结算的增量比较，重新联合设计
自然成型速度、七对/普通、保白目的、备用路线和立即胡/等待的取舍。不要只拼接
高番奖励或普遍延迟胡；要解释什么时候路线负担过大、什么时候当前胡已够好。
038共同起点无白且只有3自然对，不是5对七对规则现成答案；两套记录都选择seven_pairs
为信用家族，所以不能断言新公式选了普通型。检查同速前沿、主目标、备用信用各自
已计价值和损失，保留真实速度/结构差异，避免重复奖励或用包络抹掉代价。原起点
弃1条/2条之后的未来差不是规定弃牌答案，不许按牌码、房号或诊断标签查表。
040单白立即2番而S02后4番是负例；035双白2升4是正例；已胡等待会失胡的反例也保留。
已可胡窗口使用实际合法胡支付作明确机会成本；结算明细含爆头/财飘不能把已实现
白价值笼统当PURPOSES[1]就宣称精确。远目标仍是启发式可能性；未知他家胡率、摸牌
概率保留未知，容量不可除墙冒充概率；不能拿到未来白、不可把各路线当独立机会。
自然型收益和大牌收益一起优化，普通效率损失允许被真实大牌兑现覆盖。庄位、墙余、
副露只是合法公开事实，不新增赛事积分排名干预。所有合法动作族和图的未知边界保持；
杠补按全相容边合并，不挑最好牌。实现尽量窄、有界可计量，避免每动作重扫整图。
六卡是事后选的压缩机制反馈，非六个必绿题、非强度检验；不得为它们强行改选。
parent_differences必须按标准提示中的两父candidate_id顺序完整填写；其他示例ID非父代。
e2的parameter_changes必须为空。严格输出一思想、一机制JSON、一完整Python源码。
"""
    text += "\n开发反馈（仅公开状态、原评分与赛后汇总，不含未来牌墙或他家暗牌）：\n" + canonical(packet).decode() + "\n"
    feedbackpath = _project_file(_PROJECT_ROOT, HERE / "AUTHOR-FEEDBACK.txt")
    with feedbackpath.open("x", encoding="utf-8") as stream:
        stream.write(text)
    prompt, _ = build_vip_eoh_prompt(batch, "e2", parents, text)
    files[str(feedbackpath)] = pin(feedbackpath)
    assert all(pin(Path(p)) == h for p, h in files.items())
    save(target, {"complete": True, "operator": "e2", "parent_paths": [str(p) for p in parentpaths],
        "parent_identities": [p["identity"] for p in parents], "files": files,
        "prompt_sha256": prompt.sha256, "prompt_utf8_bytes_not_precise_tokens": len(prompt.text.encode()),
        "maximum_actual_model_calls_in_new_batch": 2, "actual_previous_model_calls_in_new_batch": 0,
        "previous_batch_actual_calls": 2, "previous_batch_not_modified": True,
        "compact_development_cards": len(cards), "confirmation_pool_not_read": True,
        "new_scores_worlds_tables_models_HTTP": 0, "strength_or_online_admission": False})
    print(json.dumps({"complete": True, "actual_parents": expected, "compact_cards": len(cards),
        "prompt_utf8_bytes": len(prompt.text.encode()), "new_API_calls": 0}))


if __name__ == "__main__":
    main()
