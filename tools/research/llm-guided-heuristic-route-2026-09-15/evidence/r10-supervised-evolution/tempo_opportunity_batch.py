"""以未晋升自摸竞速为研究父代，独立验证吃碰的状态相关机会代价。"""

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
from types import SimpleNamespace

import strong_seed_batch as b
import strong_seed_results as results
import selfdraw_tempo_second_panel as previous
import confirmation_execution_identity as guard
from compare_refinement_terminals import compare

OUT = b.HERE / "tempo-opportunity-20260920"
NAME = "tempo-opportunity-terra-max"


def prepare():
    """冻结负反馈、父代、单次作者及一次真错误修复，不重开旧源码扩评。"""
    assert not OUT.exists(), "提案目录已存在，不覆盖"
    old = b.read(previous.OUT / "manifest.json")
    previous.verify(old)
    parent = b.Path(old["source"]["path"]).parent
    first = parent.parent
    sub_old = previous.SUB
    status = b.read(sub_old / "overall-development-status.json")
    assert status["status"] == "NOT_PROMOTED_AFTER_SECOND_PANEL"
    assert status["source_sha256"] == old["source"]["sha256"]
    second = b.read(previous.OUT / "summary.json")
    assert second["continue_new_development"] is False
    assert second["zero_internal_failures_verified"] is True
    diagnostic = b.HERE / "selfdraw-tempo-diagnostic-20260920"
    assert b.read(diagnostic / "summary.json")["status"] == "COMPLETE_DIAGNOSTIC_ONLY"
    instruction = '''本次M1是一个新的单机制研究提案，不是父代的第三次修复。父代源码附后；父代没有晋升，更没有发布资格。目标仍为完整阶段前二效用group_advance_v1，不以改选数、吃碰次数或胡牌次数作为提升证明。
先读完整负反馈：父代在已曝光核心2026092001的H/M各8来源根、每根4座位配置、共256完整自然桌赛中，相对V2均值H +0.28125、M +0.09375、等权+0.1875。保持源码在第二已曝光清单2026092097同规模评价，H −0.09375、M −0.171875、等权−0.1328125，识别差范围[−0.140625,−0.125]，停止效果扩评。这个区间是次级平分事实不足的识别区间，不是置信区间；抽样不确定性仍较大，不证明父代总体更差。两张清单86,417次自然评分全部成功，无性能降级可用于解释负结果。后附自动父代反馈只来自首清单，不能把其中正向选留当作总体晋升状态。
事后同M情景各选最早严格负和严格正座位配置，双臂复演8桌，完整终局全部复现。2711个请求中124次首选不同，66次候选给V2首选和自身首选相同数值，最后由动作键分开。双臂共享前缀重复，不是独立自然频率；正负都出现同分，不能据此声称同分导致失败。
三个真实例子只作为问题，不是优劣标签：
（1）负配置中过牌与吃1w2w3w后弃4w均为向听1、支持15；V2分别−85/−95，差来自固定吃碰代价。父代均517.391304，按动作键选择吃。
（2）正配置中过牌向听2/支持50，吃7w8w9w后弃1w为向听2/支持55；V2分别−145/−150，父代312.903226/314.925373，严格选择吃。这是有直接进展的改选，不能一律消除。
（3）正配置中过牌与吃7t8t9t后弃9t都有听牌/支持6，条件自摸见证自身分差24、阶段门线距离改善32，父代均831.888889而按动作键选择吃。条件结算仍然不是立即收益。
新的单机制问题：在父代的同刻度自摸竞速前沿上，吃碰是不可逆副露；相对同窗口过牌，应如何利用真实可见的进展、公开规则派生的普通/七对或财神路线事实，表达状态相关机会代价？请设计一项可解释、可移除的机制，兼顾同等进展下保留选项和明确提速时接受吃碰。可反驳监督者假设并给出同范围的更好依据；不规定公式、常数或“正确”样例动作，不必照搬V2。不能仅恢复统一−10、扫描固定罚分、无条件禁止吃碰、按字典序换偏好或给所有未知路线补乐观价值。不要将样例牌码、seed、位置或终局正负编码成识别器。
本次范围聚焦吃碰的机会代价。保留父代tempo_value、直接/分支/条件见证的独立采纳和唯一互斥见证、立即结算及阶段门线公式；不要顺手重写基础竞速刻度、杠的未知补牌、弃牌结构、熟张、其他动作或排序骨架。非吃碰已知动作分数应保持父代数值；新增代价作用于有相容证据的吃碰动作。允许因此改变未知动作最终最低分锚定。修改必须在新增项缺适用证据时精确退化为父代，不得因分支缺失删除独立成功事实。至少一个真实机制条件会使新增项非零；零差或仅注释不算实现。
若比较过牌基线，必须是本窗口已有且量化可信的过牌事实，不从动作类型猜零向听或未来收益；过牌未知不能越过已知动作。不存在过牌时按声明退化，不自造等待候选。若使用吃碰后分支，条件路线、向听、有效牌和弃牌必须来自同一相容见证，不能把不同后续弃牌最好的分项拼合。支持数是公开可见信息下未见枚数，不是真实牌墙或校准概率。followup_branches只包含吃碰后弃牌，不是弃牌后下一摸再弃的前瞻。
规则依据为项目冻结官方指南v34和唯一规则模块：仅自摸，无点炮和抢杠胡；不可用防放铳解释。吃碰可能推进普通型并使七对资格丢失，但资格、财神、财飘/爆头/杠链、抓打圈事实只能消费已生产字段，不自行判胡、算向听、重算结算或合法性。缺失七对事实不是已证明关闭，也不是零；公开喂牌与防放铳区分。visible_state.my_hand不含drawn_tile，若读手牌则追加独立摸牌恰好一次，不按牌码去重；副露组数m时摸牌前13−3m，吃碰后待弃无独立摸牌时14−3m。可完全不使用手牌结构，避免无关几何奖励。
完整覆盖合法动作，胡仍最高层；有限数、布尔不冒充数，未知动作严格低于最终已知最低分，全未知ABSTAIN。view是纯映射，不调用.candidate_view()，不用类型注解/生产导入/外部服务/完整世界。新模块有中文注释，说明量的单位、上下界、缺值语义、实际反例和工作量。
性能努力满足默认100000次计数；仅资源计数不足且机制有价值时可由监督者另立有界200000研究配置，不改候选自行限额、监管或规则。输出、信息权限、数值和结构硬约束不放宽。编译优化不是免验承诺。
交付正式M1结构、完整受限Python源码、规则依据、公式、至少三个独立手算（同前沿但选项代价不同、存在严格直接进展、缺过牌/分支证据精确退化）、反例及消融方法。监督者会独立检查非吃碰不变和直接/条件见证不被误删，再执行固定H/M完整开发。效果负不触发调参修复；最多一次实际合同或数学实现错误修复。后代不继承父代首清单成绩。
'''
    assert len(instruction) <= 12000
    prerequisites = [sub_old / "overall-development-status.json", sub_old / "batch-closure.json",
                     previous.OUT / "summary.json", diagnostic / "summary.json", diagnostic / "README.md"]
    panel = diagnostic / "panel.json"
    auth = b.unified_document(batch_label=NAME, authorization_id="r10-" + NAME,
        accounts={"tokens_input":393216,"tokens_output":131072,"tables_full":300,
                  "tables_partial":8,"prefix_generation":8},
        issued_by="lead",issued_at_utc=b.search.utc_now(),legacy_alias=False)
    auth.update(generation_call_limits={"tokens_input":196608,"tokens_output":65536},
        max_model_calls=2,max_proposals=2,repair_calls_count_in_total=True,wall_clock_limit_seconds=14400,
        author_channel="codex_native_subagent",requested_model="gpt-5.6-terra",requested_reasoning_effort="max",
        autonomous_admission=False,author_feedback_mode="compact_prefix_v1",supervisor_feedback=instruction,
        issuance_basis="用户持续推进与Terra max作者授权；负结果诊断后新立状态相关吃碰机会代价M1，不重开父代扩评",
        scope="1首答+至多1真实错误修复；256自然桌、至多4条件桌；确认0，不发布",
        development_behavior_panel={"path":str(panel),"panel_digest":b.behavior.load_panel(panel)[0]})
    OUT.mkdir(); sub=OUT/NAME; sub.mkdir()
    b.write(sub/"authorization.json",auth)
    b.write(OUT/"manifest.json",{"schema":"tempo-opportunity-batch/1","created_at_utc":b.search.utc_now(),
        "operator":"m1","parent":str(parent),"parent_sha256":old["source"]["sha256"],
        "parent_status":"NOT_PROMOTED_AFTER_SECOND_PANEL","parent_evaluation_dir":str(first),
        "prerequisites":{str(p):b.digest(p.read_bytes()) for p in prerequisites},
        "model":"gpt-5.6-terra","effort":"max","initial_authors":1,"max_author_calls":2,
        "max_native_turn_seconds":1800,"core_panel_seed":2026092001,"roots_per_mix":8,
        "opponents":["H","M"],"seats":4,"core_natural_tables":256,"conditional_tables_limit":4,
        "selection_rule":"H/M对V2均正且同根对父代等权识别差下界正、完整核验及执行通过才签发第二已见清单；仅资源失败单列研究",
        "repair_rule":"仅一次真实合同/数学错误修复；负效果不调参、不重复同批扩评",
        "scope":"保留竞速刻度，研究状态相关吃碰机会代价，非吃碰已知分数不变",
        "runtime":guard.capture(source_paths=[*b.HERE.glob("*.py"),parent/"candidate.py"]),
        "confirmation_roots":0,"release_eligible":False})
    state=b.search.av_start_iteration(sub/"run",operator="m1",parent_dir=parent,
        generation_mode="delegate",predicate="branch_open",opponent="H",natural_roots=8,natural_seats=4,
        prefix_source="v2_behavior",panel_seed=2026092001,authorization=auth,
        archive_in={"source":"empty","path":None,"applied_operator":"m1",
                    "note":"监督按完整正负反馈选择未晋升研究父代，不是自动晋升选父"})
    assert not state.get("stop_reason"),state.get("stop_reason")
    result=b.search.av_iteration_advance(b.search.av_latest_state_path(sub/"run"),sub/"run",
        authorization=auth,stop_after="BEHAVIOR_CHECKED")
    assert result.get("waiting_for_reply"),result
    state=b.search.av_state_load(b.search.av_latest_state_path(sub/"run"))
    prompt=b.Path(state["generation"]["pending_dir"])/"prompt.txt"
    b.write(sub/"author-task.json",{"model":"gpt-5.6-terra","effort":"max","task":"m1",
        "prompt":str(prompt),"prompt_sha256":b.digest(prompt.read_bytes()),"reply_path":str(sub/"author-reply.txt")})
    print("prepared",len(prompt.read_text()),"characters; new author, no new effect tables",flush=True)


def verify():
    """核对新提案的执行依赖及完整父代正负证据。"""
    plan=b.read(OUT/"manifest.json");guard.verify(plan["runtime"])
    assert b.digest((b.Path(plan["parent"])/"candidate.py").read_bytes())==plan["parent_sha256"]
    for path,digest in plan["prerequisites"].items():assert b.digest(b.Path(path).read_bytes())==digest
    return plan


def close():
    """完整评价后同根比较研究父代，正向证据与执行成本分别裁定。"""
    plan=verify();sub=OUT/NAME
    results.summarize(NAME,candidate_dir=sub,parent_specs={"selfdraw-tempo":{
        "dir":plan["parent_evaluation_dir"],"source_sha256":plan["parent_sha256"]}})
    state=b.search.av_state_load(b.search.av_latest_state_path(sub/"run"))
    b.write(sub/"parent-terminal-comparison.json",compare(SimpleNamespace(
        ROOT=OUT,NAME=NAME,PARENT=b.Path(plan["parent"]),ITER_DIR=state["iter_dir"])))
    closure=b.read(sub/"batch-closure.json")
    positive=closure["versus_parents"]["selfdraw-tempo"]["equal_mix_low"]>0 and all(
        value["mean_delta"]>0 for value in closure["versus_v2"].values())
    reviews=b.read(sub/"full-result-reconciliation.json")["results"]
    clean=all(r["execution_review"]["zero_internal_failures_verified"] for r in reviews)
    b.write(sub/"development-decision.json",{"effect_condition_passed":positive,
        "zero_internal_failures_verified":clean,"continue_second_seen_panel":positive and clean,
        "effect_positive_needs_execution_review":positive and not clean,
        "interval_kind":"平分识别区间，非置信区间","release_eligible":False})
    print("effect_condition_passed",positive,"execution_clean",clean,flush=True)


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation",choices=("prepare","ingest","evaluate","close"))
    args=parser.parse_args()
    if args.operation=="prepare":prepare()
    elif args.operation=="close":close()
    else:
        verify();b.BATCH=OUT;b.advance(NAME,args.operation=="evaluate")
