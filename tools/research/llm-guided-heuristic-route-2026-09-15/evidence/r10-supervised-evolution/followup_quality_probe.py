"""仅诊断既有真实弃牌的后续手牌数学与成本；不生成策略、不改变评分接口。"""

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
from collections import Counter
from time import perf_counter

import strong_seed_batch as b
import confirmation_execution_identity as guard
from hangma_bot.hangma.hand_analysis import analyse_hand, math_backend_info
from hangma_bot.hangma.public_tile_counts import count_public_tiles
from hangma_bot.kernel.actions import CANONICAL_TILE_ORDER, Tile

OUT=b.HERE/"followup-quality-probe-20260920"
INPUT=b.HERE/"selfdraw-tempo-diagnostic-20260920"


def material(record):
    """还原依法可见请求，并构造当前完整暗牌、公开计数及未见枚数。"""
    request=b.behavior.decision_request_from_json(record["request"])
    assert b.behavior.capture_request(request)==record
    observation=request.observation
    hand=tuple(observation.my_hand)+(observation.drawn_tile,) if observation.drawn_tile is not None else tuple(observation.my_hand)
    melds=len(observation.melds[observation.seat])
    known=Counter(tile.code for tile in hand)
    public=count_public_tiles(observation)
    assert all(value is not None for value in public),"公开计数不完整，不虚构剩余数"
    unseen={code:max(0,4-known[code]-public[index]) for index,code in enumerate(CANONICAL_TILE_ORDER)}
    return request,hand,melds,unseen


def prepare():
    """按既有窗口次序选最早3个可比弃牌对，先冻结后计算后继。"""
    assert not OUT.exists(),"不覆盖原探查或隐式追加输入"
    selected=[];seen=set()
    for item in b.read(INPUT/"panel.json")["windows"]:
        path=INPUT/item["file"];record=b.read(path)
        request,hand,melds,unseen=material(record);obs=request.observation
        if (obs.phase!="draw" or obs.drawn_tile is None or obs.rule_state.catch_play
                or obs.rule_state.chain_count!=0 or any(t.code=="白" for t in hand)
                or len(hand)!=14-3*melds):continue
        actions=[a for a in b.behavior.build_scoring_view(request).actions
                 if a.action_type=="discard" and a.is_legal and a.shanten_after is not None
                 and a.shanten_after>=1 and all(t.remaining_estimate is not None for t in a.useful_tiles)]
        if len(actions)<2:continue
        order=lambda a:(a.shanten_after,-sum(t.remaining_estimate for t in a.useful_tiles))
        target=min(order(a) for a in actions)
        tied=sorted([a for a in actions if order(a)==target],key=lambda a:a.action_key)
        if len(tied)<2 or -target[1]<=0:continue
        signature=(tuple(sorted(t.code for t in hand)),melds,tuple(unseen.items()))
        if signature in seen:continue
        seen.add(signature)
        selected.append({"input":str(path),"record_sha256":b.digest(path.read_bytes()),
            "view_sha256":record["candidate_view_sha256"],"actions":[a.action_key for a in tied[:2]],
            "direct_shanten":target[0],"direct_support":-target[1],"melds":melds})
        if len(selected)==3:break
    assert len(selected)==3,"当前诊断清单不足3对，不追加其他来源凑数"
    OUT.mkdir()
    b.write(OUT/"manifest.json",{"schema":"followup-hand-math-probe/1","created_at_utc":b.search.utc_now(),
        "cases":selected,"selection_rule":"原30诊断窗口顺序；无白/无抓打圈/无动作链的摸后弃牌；当前最佳直接向听>=1且支持数相同的前2弃牌；最早3个不同可见手牌/公开计数组合",
        "max_cases":3,"max_actions_per_case":2,"max_first_draw_codes":34,"max_discard_codes_per_draw":14,
        "max_math_calls":3000,"max_process_seconds":120,"model_calls":0,"effect_tables":0,"confirmation_roots":0,
        "math_backend":math_backend_info(),"runtime":guard.capture(source_paths=[b.Path(__file__)]),
        "scope":"数学条件探查。仅取当前已知有效牌，假设轮到本人且公开计数没有额外变化；枚举其后数学弃牌，不裁定未来合法动作、财神/爆头资格、兑现或晋级概率",
        "units":"first_support为未见枚数；weighted_followup_support_sum单位枚²；weighted_mean_followup_support为条件加权枚数代理，权重不是已校准摸牌概率",
        "permission":"仅PlayerObservation与既有RuleAnalysis；不读取WorldState、真实未来牌墙、他家暗牌或终局标签",
        "release_eligible":False})
    print("frozen",[(r["actions"],r["direct_shanten"],r["direct_support"]) for r in selected],flush=True)


def run():
    """复用唯一手牌数学核对初始事实，记录每个条件分支而非只保留有利均值。"""
    plan=b.read(OUT/"manifest.json");guard.verify(plan["runtime"])
    assert not (OUT/"started.json").exists(),"已启动的探查不得隐式重跑"
    b.write(OUT/"started.json",{"at_utc":b.search.utc_now()})
    calls=0;total_start=perf_counter();reports=[]
    def analyze(hand,melds):
        nonlocal calls
        calls+=1
        if calls>plan["max_math_calls"]:raise ValueError("超过冻结数学调用上限")
        return analyse_hand(tuple(hand),melds)
    for index,case in enumerate(plan["cases"]):
        path=b.Path(case["input"]);assert b.digest(path.read_bytes())==case["record_sha256"]
        record=b.read(path);request,full,melds,unseen=material(record)
        actions={a.action_key:a for a in b.behavior.build_scoring_view(request).actions}
        variants=[];case_start=perf_counter()
        for key in case["actions"]:
            before=calls;start=perf_counter();a=actions[key];hand=list(full);hand.remove(a.action.tile)
            initial=analyze(hand,melds)
            computed={t.code:unseen[t.code] for t in initial.useful_tiles}
            original={t.code:t.remaining_estimate for t in a.useful_tiles}
            assert initial.shanten==a.shanten_after and computed==original,("初始规则事实不一致",key)
            branches=[]
            for draw in initial.useful_tiles:
                weight=unseen[draw.code]
                if weight<=0:continue
                drawn=hand+[Tile(draw.code)]
                # 首次弃牌只是已知牌从手里转入牌河；假设摸入一张后，该牌未见数恰减少1。
                after_unseen=dict(unseen);after_unseen[draw.code]-=1
                candidates=[]
                for discard in sorted({t.code for t in drawn}):
                    waiting=list(drawn);waiting.remove(Tile(discard))
                    summary=analyze(waiting,melds)
                    support=sum(after_unseen[t.code] for t in summary.useful_tiles)
                    candidates.append({"discard":discard,"shanten":summary.shanten,"support":support,
                        "useful_tiles":{t.code:after_unseen[t.code] for t in summary.useful_tiles}})
                best=min(candidates,key=lambda r:(r["shanten"],-r["support"],r["discard"]))
                assert best["shanten"]==case["direct_shanten"]-1,("单张有效牌的后继向听需单独核验",key,draw.code,best)
                branches.append({"draw":draw.code,"unseen_copies":weight,"best_math_discard":best,
                    "all_math_discards":candidates,"note":"数学最优弃牌，不声称满足未来动作资格"})
            weight=sum(r["unseen_copies"] for r in branches)
            assert weight==case["direct_support"]
            numerator=sum(r["unseen_copies"]*r["best_math_discard"]["support"] for r in branches)
            variants.append({"action":key,"initial_shanten":initial.shanten,"initial_support":weight,
                "initial_useful_tiles":computed,"weighted_followup_support_sum":numerator,
                "weighted_mean_followup_support":numerator/weight,"branches":branches,
                "math_calls":calls-before,"elapsed_seconds":perf_counter()-start})
        report={"index":index,"input":case["input"],"variants":variants,
            "same_initial_useful_map":variants[0]["initial_useful_tiles"]==variants[1]["initial_useful_tiles"],
            "different_followup_quality":variants[0]["weighted_followup_support_sum"]!=variants[1]["weighted_followup_support_sum"],
            "elapsed_seconds":perf_counter()-case_start}
        b.write(OUT/("case-"+str(index+1)+".json"),report);reports.append(report)
        print("case",index+1,"quality",[v["weighted_mean_followup_support"] for v in variants],"calls",calls,flush=True)
    guard.verify(plan["runtime"])
    b.write(OUT/"summary.json",{"status":"COMPLETE_MATH_DIAGNOSTIC_ONLY","cases":len(reports),
        "different_followup_quality":sum(r["different_followup_quality"] for r in reports),
        "same_initial_useful_map":sum(r["same_initial_useful_map"] for r in reports),
        "math_calls":calls,"elapsed_seconds":perf_counter()-total_start,
        "case_elapsed_seconds":[r["elapsed_seconds"] for r in reports],"math_backend":math_backend_info(),
        "quality_pairs":[[v["weighted_mean_followup_support"] for v in r["variants"]] for r in reports],
        "effect_tables":0,"model_calls":0,"confirmation_roots":0,"release_eligible":False,
        "limits":["三对事后诊断输入不是分布或效果样本","不证明当前完整评分视图不可区分或表达空间耗尽",
                  "只测手牌数学，不裁定未来动作资格、计番、他家先胡、保留20张后可摸次数或晋级概率",
                  "计时包括本进程缓存及动作次序影响，不是全链预算或最大并发证据"]})


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("operation",choices=("prepare","run"))
    args=parser.parse_args();prepare() if args.operation=="prepare" else run()
