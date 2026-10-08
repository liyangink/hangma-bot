"""独立代入新M1的保留值公式，并检查互斥见证与未知锚定；不模拟效果。"""

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
from dataclasses import replace
from fractions import Fraction as F
import math

import tempo_opportunity_checks as checks
from selfdraw_tempo_arithmetic import branch, route
from hangma_bot.hangma.interface import UsefulTileFact
from hangma_bot.policy.action_value import CompetitionView
from hangma_bot.policy.action_value_seeds import ActionValueScorer

b=checks.b


def tiles(total):
    """合成未见枚数，单牌上限4；仅验证评分算术，不冒充合法完整牌谱。"""
    result=[]
    for suit in ("t","b","w"):
        for rank in range(1,10):
            count=min(4,total)
            if count>0:result.append(UsefulTileFact(str(rank)+suit,count))
            total-=count
    assert total==0
    return tuple(result)


def direct(kind,shanten,support):
    """创建一个合法键形状动作，分值事实使用调用方给定单位。"""
    obj=checks.action("" if kind=="pass" else "4b",0,shanten,kind)
    return replace(obj,useful_tiles=tiles(support),best_followup_discard="9b" if kind=="peng" else None)


def cases():
    """期望以独立有理数写出；不复用候选内部T函数或新代价循环。"""
    pass15=replace(direct("pass",1,15),standard_shanten_after=1,standard_useful_tiles=tiles(15),
        seven_pairs_shanten_after=1,seven_pairs_useful_tiles=tiles(15))
    call15=direct("peng",1,15)
    p=F(11900,23)
    weak=replace(pass15,seven_pairs_shanten_after=3,seven_pairs_useful_tiles=tiles(16))
    pass50=replace(direct("pass",2,50),standard_shanten_after=2,standard_useful_tiles=tiles(50),
        seven_pairs_shanten_after=3,seven_pairs_useful_tiles=tiles(16))
    ready=replace(direct("pass",0,2),standard_shanten_after=0,standard_useful_tiles=tiles(2),
        seven_pairs_shanten_after=2,seven_pairs_useful_tiles=tiles(12),routes=(route(None),))
    negative=replace(direct("pass",8,0),standard_shanten_after=8,standard_useful_tiles=(),
        seven_pairs_shanten_after=8,seven_pairs_useful_tiles=())
    r=F(10000,13)  # T(0,2)=760；条件自身分差12的奖励为120/13，未提供阶段账。
    return [
        ("same_frontier_two_close_routes",(pass15,call15),{"pass":p,"peng:4b":p*F(7,8)},F(2975,46),"direct_frontier","9b"),
        ("same_frontier_weaker_second_route",(weak,call15),{"pass":p,"peng:4b":p-F(65,4)},F(65,4),"direct_frontier","9b"),
        ("strict_support_progress",(pass50,direct("peng",2,55)),{"pass":F(9700,31),"peng:4b":F(21100,67)},None,"direct_frontier","9b"),
        ("strict_shanten_progress",(pass50,direct("peng",1,5)),{"pass":F(9700,31),"peng:4b":F(6100,13)},None,"direct_frontier","9b"),
        ("missing_seven_shanten",(replace(pass15,seven_pairs_shanten_after=None),call15),{"pass":p,"peng:4b":p},None,"direct_frontier","9b"),
        ("missing_seven_support",(replace(pass15,seven_pairs_useful_tiles=None),call15),{"pass":p,"peng:4b":p},None,"direct_frontier","9b"),
        ("missing_standard_shanten",(replace(pass15,standard_shanten_after=None),call15),{"pass":p,"peng:4b":p},None,"direct_frontier","9b"),
        ("known_zero_support_is_not_missing",(replace(pass15,seven_pairs_shanten_after=2,seven_pairs_useful_tiles=()),call15),{"pass":p,"peng:4b":p-5},F(5),"direct_frontier","9b"),
        ("nonpositive_reserve_is_inactive",(negative,direct("peng",8,0)),{"pass":F(-55),"peng:4b":F(-55)},None,"direct_frontier","9b"),
        ("pass_conditional_witness_not_direct",(ready,direct("peng",0,2)),{"pass":r,"peng:4b":F(760)},None,"direct_frontier","9b"),
        ("call_conditional_witness_not_direct_exemption",(weak,replace(direct("peng",1,16),routes=(route("8b"),))),{"pass":p,"peng:4b":r-F(65,4)},F(65,4),"conditional_witness","8b"),
        ("one_winning_branch_not_mixed_frontier",(weak,replace(call15,followup_branches=(branch("8b",1,16),branch("7b",2,100)))),{"pass":p,"peng:4b":F(520)},None,"followup_frontier","8b"),
        ("missing_branch_keeps_direct",(weak,replace(call15,followup_branches=None)),{"pass":p,"peng:4b":p-F(65,4)},F(65,4),"direct_frontier","9b"),
        ("unknown_branch_keeps_direct",(weak,replace(call15,followup_branches=(branch("8b",True,True),))),{"pass":p,"peng:4b":p-F(65,4)},F(65,4),"direct_frontier","9b"),
        ("unknown_floor_after_penalty",(pass15,call15,checks.action("9w")),{"pass":p,"peng:4b":p*F(7,8),"discard:9w":p*F(7,8)-1},F(2975,46),"direct_frontier","9b"),
    ]


def run():
    """验证明确分值、代价和胜出见证的绑定，不把数学通过当策略增强。"""
    checks.configure();source=checks.common.source_path()
    output=checks.batch.OUT/checks.batch.NAME/"independent-arithmetic.json"
    assert not output.exists(),"保留原始算术结果"
    scorer=ActionValueScorer("opportunity-arithmetic",source.read_text());rows=[]
    for name,actions,expected,cost,origin,discard in cases():
        sample=replace(checks.view(actions,familiar=()),competition=CompetitionView())
        result=scorer.score(sample);actual={e.action_key:e.score for e in result.entries}
        traces={e.action_key:dict(e.trace) for e in result.entries};trace=traces.get("peng:4b",{})
        errors=[]
        if result.status!="SCORED":errors.append("status")
        for key,number in expected.items():
            if key not in actual or not math.isclose(actual[key],float(number),rel_tol=0,abs_tol=1e-9):errors.append("score:"+key)
        observed=trace.get("opportunity_cost")
        if (cost is None and observed is not None) or (cost is not None and
                (observed is None or not math.isclose(observed,float(cost),rel_tol=0,abs_tol=1e-9))):errors.append("cost")
        if trace.get("source")!=origin or trace.get("followup_discard")!=discard:errors.append("witness_binding")
        rows.append({"name":name,"expected":{k:float(v) for k,v in expected.items()},
            "expected_cost":float(cost) if cost is not None else None,"actual":actual,"trace":traces,
            "errors":errors,"input_sha256":b.behavior.digest(sample.candidate_view()),
            "operations":scorer.last_operation_count})
    report={"status":"FAIL" if any(r["errors"] for r in rows) else "PASS","cases":len(rows),"rows":rows,
        "source_sha256":b.digest(source.read_bytes()),"runner_sha256":b.digest(b.Path(__file__).read_bytes()),
        "scope":"15项独立合成算术与见证绑定，不声称完整牌谱可达或效果增强","release_eligible":False}
    b.write(output,report);print(report["status"],[(r["name"],r["errors"]) for r in rows if r["errors"]],flush=True)


if __name__=="__main__":run()
