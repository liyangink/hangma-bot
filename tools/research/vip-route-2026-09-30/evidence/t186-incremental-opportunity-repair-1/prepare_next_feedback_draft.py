"""将已闭自然路径压成公式修订草稿；不读第三批中途分，不调用模型。"""

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

HERE=Path(__file__).resolve().parent
PRIOR=_project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t185-evidence-prioritized-joker-evolution-1')
sys.path.insert(0,str(PRIOR))
from common import pin,save


def main():
    """兼顾亏损、盈利及未分胜负路线，禁止用单例动作名生成查表策略。"""
    summarypath=_project_file(_PROJECT_ROOT, HERE/"natural-stage-002-dispatch/CUMULATIVE-SUMMARY.json")
    summary=json.loads(summarypath.read_text())
    assert summary["complete"] and summary["independent_roots"]==16
    selection={(2,0),(3,2),(6,1),(15,2),(16,0),(3,1)}
    cards=[];files={str(summarypath):pin(summarypath),str(Path(__file__)):pin(Path(__file__))}
    for stage in (1,2):
        directory=_project_file(_PROJECT_ROOT, HERE/f"natural-stage-{stage:03d}-paths")
        closedpath=directory/"CLOSED.json";closed=json.loads(closedpath.read_text())
        assert closed["complete"] and closed["source_stable"]
        raw=directory/"original-public-first-rows.jsonl.gz"
        assert pin(raw)==closed["public_rows_pin"]
        files[str(raw)]=pin(raw);files[str(closedpath)]=pin(closedpath)
        account={ (r["root"],r["rotation"]):r for r in
            [json.loads(l) for l in (directory/"rows.jsonl").read_text().splitlines()]}
        files[str(directory/"rows.jsonl")]=pin(directory/"rows.jsonl")
        with gzip.open(raw,"rt") as stream:
            for line in stream:
                r=json.loads(line);pair=(r["root"],r["rotation"])
                if pair not in selection:continue
                a,b=r["parent_original_row"],r["child_original_row"]
                obs=a["observation"];table=account[pair]
                relevant={a["selected_action_key"],b["selected_action_key"]}
                firstturn=a["window_key"]["round_no"]
                outcomes=[]
                for arm in (0,1):
                    path=_project_file(_PROJECT_ROOT, HERE/f"natural-development/root-{pair[0]:03d}/seat-{pair[1]}-arm-{arm}/CLOSURE.json")
                    d=json.loads(path.read_text());assert d["complete"]
                    files[str(path)]=pin(path)
                    settlement=d["settlements"][firstturn-1]["settlement"]
                    outcomes.append({k:settlement[k] for k in ("winner_seat","dealer_seat","fan","details","score_delta")})
                def compact(row):
                    return [{"action_key":e["action_key"],"score":e["score"],"detail":e["trace"]["detail"]}
                        for e in row["candidates"] if e["action_key"] in relevant]
                cards.append({"label":f"known-development:{pair[0]:03d}:{pair[1]}",
                    "visible_state_excerpt":{k:obs[k] for k in ("seat","dealer_seat","my_hand","drawn_tile","melds","discards","remaining_tile_count","rule_state")},
                    "white_count":a["white_count"],"original_legal_root_keys":a["legal_action_keys"],
                    "S02_selected":a["selected_action_key"],"357e_selected":b["selected_action_key"],
                    "S02_original_scores":compact(a),"357e_original_scores":compact(b),
                    "associated_first_hand_outcomes_0_S02_1_357e":outcomes,
                    "associated_complete_table_delta":table["table_delta"],
                    "not_single_action_causal_effect_or_required_answer":True})
    assert len(cards)==len(selection)
    cards.sort(key=lambda c:c["label"])
    source=_project_file(_PROJECT_ROOT, HERE/"AUTHOR-resource-release-metadata-repaired/candidate.py")
    files[str(source)]=pin(source)
    packet={"draft_only_not_author_ready":True,"new_parent_candidate_identity":summary["candidate_identity"],
        "closed_16_source_mean_delta_per_table":summary["mean_delta_per_complete_table"],
        "closed_16_source_exploratory_interval":summary["net_exploratory_source_bootstrap95"],
        "third_stage_results_not_read_or_included":True,"formal_parent_scope_results_not_yet_included":True,
        "cards":cards,"files":files,"new_scores_worlds_tables_models_HTTP":0}
    target=_project_file(_PROJECT_ROOT, HERE/"AUTHOR-NEXT-FEEDBACK-DRAFT.json");assert not target.exists();save(target,packet)
    text=_project_file(_PROJECT_ROOT, HERE/"AUTHOR-NEXT-FEEDBACK-DRAFT.txt");assert not text.exists()
    text.write_text("""【草稿，尚不具备作者调用资格】
先补上固定32来源累计结论与正式父代作用范围探针结果，再决定是否调用第二次GLM。
下列卡片全部来自已闭开发，不是未知确认，不是单动作因果效应，也不是强制正确答案。

共同目标：保留有希望的自然成型、高番路线及足够普通效率，联合改善弃牌与已可胡时的等待。允许普通收入损失由真实大牌收入覆盖；不把大牌条件题分数当总体积分。
1. 对同速路线的合并，解释共同进张码如何去重，主路线信用与备用信用如何避免重复计价，同时不要让max包络无意抹平自然形差异。更宽不自动支配七对或已成熟高番路线。
2. 多白释放与未来新增白必须分清。自然成型释放一白后可财飘，与必须再摸财神的机会不同；支付、自然缺张、弃白动作与最终摸牌的成本联合比较。
3. 同时审视早巡双白速胡负例与三白晚巡保听正例。不能按白数、墙余或某个弃牌码硬编码卡片；他家先胡仍未知，副露只是公开风险信号，不能伪称真实胡率。
4. 无白舍弃七对后失胡、无白换弃牌后整桌盈利都保留。先区分正式父代继承与新修订；不将整桌后继收益归因首手，不把每张诊断卡当验收标准。
5. 框架与杭麻规则不改。只生成合同允许的联合公式，合法根全输出、未知保留、确定性、信息权限和操作上限仍必须通过。禁止牌山ID查表，禁止读取隐藏手牌或未来牌墙。

完整输入合同和正式父代源码应由标准EoH提示生成器提供，不从以下缩略卡片发明新字段。预期方向要绑定标准生成器给出的真实父代ID，不能自己填写昵称或猜摘要。
""",encoding="utf-8")
    print(json.dumps({"draft_prepared":True,"compact_cards":len(cards),"bytes":target.stat().st_size,
        "new_API_calls":0,"third_stage_data_read":False}))


if __name__=="__main__":
    main()
