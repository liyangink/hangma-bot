"""以112次单变量实测准备联合修订作者；机械问题和未决强度明确分开。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t188-joint-score-mechanism-1'

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
SOURCE = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t187-family-combination-evolution-1')
PRIOR = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t185-evidence-prioritized-joker-evolution-1')
sys.path.insert(0, str(PRIOR))
from common import canonical, pin, save
from hangma_bot.offline.vip_eoh_generate import VipEohBatch, build_vip_eoh_prompt, load_vip_parents


def main():
    """固定两个真实父代、全部14诊断来源与单变量结果，不读取新确认池。"""
    destination = _project_file(_PROJECT_ROOT, HERE / "AUTHOR-PREPARATION.json")
    assert not destination.exists()
    closed = json.loads((_project_file(_PROJECT_ROOT, HERE / "probes/CLOSED.json")).read_text())
    assert closed["complete"] and closed["source_stable"] and closed["actual_score_calls"] == 112
    assert closed["rows_pin"] == pin(_project_file(_PROJECT_ROOT, HERE / "probes/rows.jsonl"))
    assert closed["summary"]["I"]["changed_vs_C"] == []
    assert closed["summary"]["D"]["maximum_duplicate_codes"] == 0
    assert closed["summary"]["DE"]["maximum_duplicate_codes"] == 0
    raw_batch = json.loads((_project_file(_PROJECT_ROOT, SOURCE / "AUTHOR-BATCH.json")).read_text())
    raw_batch["batch_id"] = "t188-joint-score-correction-20261005"
    batch_file = _project_file(_PROJECT_ROOT, HERE / "AUTHOR-BATCH.json")
    assert not batch_file.exists()
    save(batch_file, raw_batch)
    batch = VipEohBatch.read(batch_file)
    parent_paths = [_project_file(_PROJECT_ROOT, PRIOR / "AUTHOR-speed-model-output"), _project_file(_PROJECT_ROOT, SOURCE / "AUTHOR-explore-model-output")]
    parents = load_vip_parents(parent_paths, batch)
    assert parents[0]["identity"]["candidate_id"] == "6876373ea66c9b0a0bd25743517bb1ddacd0742e61822a6a0efd0abc5c157c28"
    assert parents[1]["identity"]["candidate_id"] == "76d9d496cd47259250f7d352ff3dc0ddd6c52ae4a2b556c9e28a18b233b401a7"
    assert parents[0]["identity"]["deps_digest"] == parents[1]["identity"]["deps_digest"]
    with gzip.open(_project_file(_PROJECT_ROOT, HERE / "FIRST-CHOICES.jsonl.gz"), "rt") as stream:
        cases = list(map(json.loads, stream))
    probes = list(map(json.loads, (_project_file(_PROJECT_ROOT, HERE / "probes/rows.jsonl")).read_text().splitlines()))
    cards = []
    for case in cases:
        relevant = {case["A"]["selected_action_key"], case["C"]["selected_action_key"]}
        local = [r for r in probes if r["target"] == case["target"]]
        relevant.update(r["candidate_first"] for r in local)
        cards.append({
            "label": case["label"],
            "public_observation": {k: case["observation"][k] for k in (
                "seat", "dealer_seat", "my_hand", "drawn_tile", "melds",
                "discards", "remaining_tile_count", "rule_state",
            )},
            "legal_root_keys": case["A"]["legal_action_keys"],
            "online_S02": {
                "first": case["A"]["selected_action_key"],
                "entries": [e for e in case["A"]["candidates"] if e["action_key"] in relevant],
            },
            "model_parent_76": {
                "first": case["C"]["selected_action_key"],
                "entries": [e for e in case["C"]["candidates"] if e["action_key"] in relevant],
            },
            "manual_diagnostic_not_models_or_strength": [
                {"probe": r["probe"], "first": r["candidate_first"],
                 "entries": [e for e in r["entries"] if e["action_key"] in relevant]}
                for r in local
            ],
            "associated_historical_continuation_C_minus_A": case["historical_sum_C_minus_A"],
            "associated_uniform_compatible_C_minus_A": case["conditional_sum_C_minus_A"],
            "not_single_action_cause_or_required_answer": True,
        })
    baseline = _project_file(_PROJECT_ROOT, PRIOR / "parent-source.py")
    assert pin(baseline)["sha256"] == "2a59cbb18aefa3d24aadf0b3df70f5a4359c204b96a3f0dc208f77d53c196f30"
    feedback = """【本次e2：真实父为6876大牌家族和76不同路线形式；S02只作精确参考】
联合改进弃牌的自然成型速度、宽进张、普通/七对选择与保白高番路线，及当前胡的
增量等待取舍。不是只研究等待，不删除合法动作，不更改规则或输入图，不进入
赛事压力策略。当前线上S02仍冻结。父A旧32自然来源大牌+10.5625、普通-5.59375、
净+6.7422，但区间跨零；父B最新84单局条件为负，未通过完整桌费用门。
这不是父A已增强、父B全球更弱或题库答案。不要机械复制父代码再仅调两个常数。

【已验证的代码问题，112评分；I纯仪器与父B每根分值精确】
1. 父Broutepair为主路线外独占码给followercredit，但jointwait的credited只含主
路线码等，没有登记这些已计价跟随码。自然准备随后又计这些码，totalcredit=
followercredit+backup。14原窗中8窗实际重复，最多19码。D将已计价跟随码登记到
credited后重复为0，却把原有正控制单白弃4条改回弃北，无白另一窗也改选；不能
只删除信用就宣布取舍更正确。需统一每种物理进张的增量预算，保留其改善多条
路线的选择价值，按速度、额外自然代价、宽度与用途分配，不一刀切归零自然
准备，也不能同码因同时属于普通、七对、自然形而多次累加。所有未知保留。
2. 父B的成熟单白need=0统一禁止追加白option，连自然准备已完成的场景也禁止。
E只对retained=1、need=0、prep.need=0放开：040当前胡14.71698排序点，等7万由
13.81339变14.81599（net .09899），恢复继续；002失胡负控制仍立即胡20，等5饼
18.90862仍低，且三白015等北不变。这只是公开评分差异，没有E续打涨分证明。
不普遍延胡；应比较当前真实支付与更大用途的增量，公开余墙、他家副露、庄位
和未来资格未知都须保留。不开拆掉已成形自然搭子的泛化等待，以通用条件表达。
3. 无白3自然对子038：1条/2条主七对值一样，但父B独占跟随信用把1条排前。
消重后1条3.84859/2条3.79007，仍未解该取舍；原S02是2条3.50250/1条3.46301。
实际1条在已暴露原历史流局，而S02七对爆头4番；相容两配对另少32。不得将
这个结局变成房号/牌码查表或强制2条答案。要解释主路线同价时真正的备选
自然路径、进张宽度与代价为何能正确参与。其他正负14题全提供，不只迎合038。

【联合公式要求】
给出紧凑而完整的统一路线价值/额外代价/独特出口聚合，可借鉴S02有效普通
行为和父A同速宽进张，但不整体回退或只补两个if。同码多条路线取最高有效
增量或有明确上限的可解释组合；基数多、最大目标高、已持白多都不代表概率。
现在胡与继续必须放在相同可解释排序单位，已兑现用途不重复计分；需要追加白
的事实不因自然形成熟自动变成无价值，也不因为远端凸目标高就忽视当前胡的
机会成本。吃碰跳位/七对阻断、明暗补杠条件、保听财飘和杠链继续完整消费
图事实，不挑最好未知补牌，不删除根。多白价值保留，合理普通效率损失可接受，
但要在综合净分与自然频率下验证。只修受限联合公式，不假称计算了真实EV。
禁止读取历史标签、房号、未来牌山或他家暗牌；反馈中历史结局仅离线研发标签。
应有简洁trace能核单码预算、主备用路线、当前胡基线、额外等待成本与未知。
交付标准e2：一句思想、mechanism JSON、完整受限Python，不自报增强或准入。
"""
    packet = {
        "baseline_S02_source_reference_not_formal_parent": baseline.read_text(),
        "all_14_public_diagnostic_cards": cards,
        "four_probe_definitions": json.loads((_project_file(_PROJECT_ROOT, HERE / "PROBE-PREPARATION.json")).read_text())["probes"],
        "strength_and_pilot_budget_currently_false": True,
    }
    # 模型只获公开字段和离线反馈；诊断定义去掉本机路径/执行身份清单。
    packet["four_probe_definitions"] = [
        {k: p[k] for k in ("name", "purpose", "model_output", "admission")}
        for p in packet["four_probe_definitions"]
    ]
    feedback += "\n公开反馈与精确基线参考：\n" + canonical(packet).decode() + "\n"
    feedback_path = _project_file(_PROJECT_ROOT, HERE / "AUTHOR-FEEDBACK.txt")
    with feedback_path.open("x") as stream:
        stream.write(feedback)
    prompt, _ = build_vip_eoh_prompt(batch, "e2", parents, feedback)
    paths = [
        Path(__file__), _project_file(_PROJECT_ROOT, HERE / "run_author.py"), batch_file, feedback_path,
        _project_file(_PROJECT_ROOT, HERE / "FIRST-CHOICE-CLOSED.json"), _project_file(_PROJECT_ROOT, HERE / "FIRST-CHOICES.jsonl.gz"),
        _project_file(_PROJECT_ROOT, HERE / "PROBE-PREPARATION.json"), _project_file(_PROJECT_ROOT, HERE / "probes/CLOSED.json"), _project_file(_PROJECT_ROOT, HERE / "probes/rows.jsonl"),
        _project_file(_PROJECT_ROOT, PRIOR / "glm_max_transport.py"), baseline,
    ] + [path / name for path in parent_paths for name in ("candidate.py", "generation.json")]
    save(destination, {
        "complete": True, "operator": "e2", "formal_parent_paths": [str(p) for p in parent_paths],
        "formal_parent_identities": [p["identity"] for p in parents],
        "files": {str(p): pin(p) for p in paths}, "prompt_sha256": prompt.sha256,
        "prompt_utf8_bytes_not_precise_tokens": len(prompt.text.encode()),
        "confirmation_pool_not_read": True, "actual_previous_model_calls_this_batch": 0,
        "maximum_actual_model_calls_this_batch": 2, "new_scores_worlds_tables_models_HTTP": 0,
    })
    print(json.dumps({"complete": True, "operator": "e2",
                      "prompt_utf8_bytes": len(prompt.text.encode()), "new_model_calls": 0}))


if __name__ == "__main__":
    main()
