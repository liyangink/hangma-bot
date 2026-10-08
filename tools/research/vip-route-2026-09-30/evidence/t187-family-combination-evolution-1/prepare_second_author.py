"""以闭合负信号准备第二次e1作者，探索不同联合聚合而非微调同一包络。"""

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
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PRIOR = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t185-evidence-prioritized-joker-evolution-1')
sys.path.insert(0, str(PRIOR))
from common import canonical, pin, save
from hangma_bot.offline.vip_eoh_generate import VipEohBatch, build_vip_eoh_prompt, load_vip_parents


def main():
    """复核一实调用、一零API回放和条件失败，冻结两真父及公平反馈，不调用API。"""
    output = _project_file(_PROJECT_ROOT, HERE / "SECOND-AUTHOR-PREPARATION.json")
    assert not output.exists()
    budgetpath = _project_file(_PROJECT_ROOT, HERE / "PILOT-BUDGET-DECISION.json")
    budget = json.loads(budgetpath.read_text())
    assert budget["complete"] and not budget["64_table_pilot_budget_eligible"]
    conditionpath = _project_file(_PROJECT_ROOT, HERE / "CONDITION-CLOSED.json")
    condition = json.loads(conditionpath.read_text())
    assert condition["complete"] and condition["resources_released"]
    assert all(pin(Path(p)) == h for p, h in budget["files"].items())
    ledgerpath = _project_file(_PROJECT_ROOT, HERE / "AUTHOR-BATCH.vip-eoh-ledger.json")
    ledger = json.loads(ledgerpath.read_text())
    assert all(r["status"] == "settled" for r in ledger["reservations"])
    charged = {k: sum(r["charged"][k] for r in ledger["reservations"]) for k in ledger["budgets"]}
    assert charged["model_calls"] == 1 and ledger["budgets"]["model_calls"] == 2
    batch = VipEohBatch.read(_project_file(_PROJECT_ROOT, HERE / "AUTHOR-BATCH.json"))
    parentpaths = [_project_file(_PROJECT_ROOT, PRIOR / "AUTHOR-speed-model-output"), _project_file(_PROJECT_ROOT, HERE / "AUTHOR-family-metadata-repaired")]
    parents = load_vip_parents(parentpaths, batch)
    proofpath = parentpaths[1] / "DERIVATION.json"
    proof = json.loads(proofpath.read_text())
    assert proof["complete"] and proof["executable_source_unchanged"]
    assert proof["derived_generation_pin"] == pin(parentpaths[1] / "generation.json")
    gatepath = _project_file(_PROJECT_ROOT, HERE / "qualification/CLOSED.json")
    rowsfile = _project_file(_PROJECT_ROOT, HERE / "qualification/rows.jsonl")
    gate = json.loads(gatepath.read_text())
    assert gate["complete"] and gate["mechanical_passed"] and gate["identity"] == parents[1]["identity"]
    assert gate["rows_pin"] == pin(rowsfile)
    rows = {r["label"]: r for r in map(json.loads, rowsfile.read_text().splitlines())}
    tracelabel = "joint-development:038:0"
    traces = [{"action_key": e["action_key"], "score": e["score"], "trace": e["trace"]}
              for e in rows[tracelabel]["entries"] if e["action_key"] in ["discard:1t", "discard:2t"]]
    feedback = (_project_file(_PROJECT_ROOT, HERE / "AUTHOR-FEEDBACK.txt")).read_text()
    feedback += """

【第二实际作者；前文父B a0仅历史，不是本次正式父，正式父列表以标准附录为准】
这次operator=e1，实际父为保留大牌家族6876与新e8。目标是探索不同形式的联合公式；
不是继续在相同max家族包络、线性缺张罚、凸PURPOSES代理上增减两三个常数。
首个e2实际只把FRONTSHARE从.5改.65，加SATEANCHOR=12和余墙松弛3：355状态710评分
机械通过，相对a0仅4窗口/2来源改选。14母来源84单局/2842评分直接对S02，原历史
净-30/大牌-96，相容28配对净-66/大牌-40，已停止自然小桌。给出新机制，不自报涨分。
038初始无白3自然对；e8两弃牌主目标值同为-8.038，1条的前沿信用.492而2条.058，
导致排名4.1265比3.6926高；仍选1条，后继平胡1番而S02七对爆头4番。该历史结局
不能证明应该总弃2条，但主目标同值而并集信用主导正是需研究的取舍。请解释每
条路线实际速度/准备/用途差异如何保留、同码跨路线如何避免重复奖励；不能用
较快家族的包络完全抹平慢而有价值的路线，也不能为七对普遍加分迎合单例。
考虑改用更紧凑的逐路线价值—额外代价—独特出口联合聚合，或另一个确有不同
机制的有界公式；不要把所有远端目标硬砍、强制只比较当前胡与下一摸支付。
当前Hu与继续的取舍必须用当前实际支付作机会成本，保留直接条件升档、真实
已有白的释放与追加链可能性；分别解释不可达/等待更久/已高番/未知三家竞速。
容量和向听下界不是概率、平均等待时间；未知要保留，所有合法根/图动作族不删。
035双白及015三白仍有2升4正例，002失胡避免有+56正例；038和040与首手以外
后继共同引发大牌损失。保留正机制，不能以普遍速胡消除所有风险。
建议把不确定性限定在排序公式，减少冗余扫描，留清晰trace用于逐分量核验。
实现可以比父代短，但必须完整处理普通/七对、无白到多白、胡/弃/鸣牌/补牌/
未知节点；不读房号、历史标签或未来牌墙，不按题牌码查表。
本次parent_differences只能按实际两父6876/e8的完整ID顺序，不引用前文a0/357。
e1 parameter_changes为空。严格交付一句思想、一机制JSON、一完整Python源码。
"""
    packet = {"e8_038_original_trace_not_required_answer": traces,
        "e8_condition_historical": condition["historical_exposed"],
        "e8_condition_uniform_compatible_not_natural": condition["public_compatible_uniform"],
        "per_target_deltas": [{"label": t["label"], "historical": t["historical"]["C_minus_A"],
            "historical_fans": t["historical"]["actual_focal_fans"], "conditional": t["two_conditional"]["sum_C_minus_A"]}
            for t in condition["target_summaries"]]}
    feedback += "\n第二作者闭合开发反馈：\n" + canonical(packet).decode() + "\n"
    feedbackpath = _project_file(_PROJECT_ROOT, HERE / "SECOND-AUTHOR-FEEDBACK.txt")
    with feedbackpath.open("x", encoding="utf-8") as stream:
        stream.write(feedback)
    prompt, _ = build_vip_eoh_prompt(batch, "e1", parents, feedback)
    files = {str(p): pin(p) for p in (Path(__file__), _project_file(_PROJECT_ROOT, HERE / "run_second_author.py"), budgetpath, conditionpath,
        ledgerpath, gatepath, rowsfile, proofpath, feedbackpath, _project_file(_PROJECT_ROOT, HERE / "AUTHOR-FEEDBACK.txt"), _project_file(_PROJECT_ROOT, HERE / "AUTHOR-BATCH.json"),
        _project_file(_PROJECT_ROOT, PRIOR / "glm_max_transport.py"), *(p / name for p in parentpaths for name in ("generation.json", "candidate.py")))}
    assert all(pin(Path(p)) == h for p, h in files.items())
    save(output, {"complete": True, "operator": "e1", "formal_parent_paths": [str(p) for p in parentpaths],
        "formal_parent_identities": [p["identity"] for p in parents], "files": files,
        "actual_previous_model_calls": 1, "maximum_actual_model_calls": 2, "previous_actual_charged": charged,
        "prompt_sha256": prompt.sha256, "prompt_utf8_bytes_not_precise_tokens": len(prompt.text.encode()),
        "confirmation_pool_not_read": True, "new_scores_worlds_tables_models_HTTP": 0})
    print(json.dumps({"complete": True, "operator": "e1", "actual_previous_model_calls": 1,
        "prompt_utf8_bytes": len(prompt.text.encode()), "new_model_calls": 0}))


if __name__ == "__main__":
    main()
