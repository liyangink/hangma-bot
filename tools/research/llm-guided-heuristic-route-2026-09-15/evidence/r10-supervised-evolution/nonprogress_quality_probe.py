"""延伸已见三对弃牌的数学探查：包括暂不降低向听的摸牌，按后继向听分别比较。"""

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
from time import perf_counter

import followup_quality_probe as previous
import confirmation_execution_identity as guard
from hangma_bot.hangma.hand_analysis import analyse_hand, math_backend_info
from hangma_bot.kernel.actions import Tile

b=previous.b
OUT=b.HERE/"nonprogress-quality-probe-20260920"


def prepare():
    """沿用完全相同三对输入，不按上一探查的结果再挑窗口。"""
    assert not OUT.exists()
    old=b.read(previous.OUT/"manifest.json");guard.verify(old["runtime"])
    summary=b.read(previous.OUT/"summary.json")
    assert summary["status"]=="COMPLETE_MATH_DIAGNOSTIC_ONLY"
    OUT.mkdir();b.write(OUT/"manifest.json",{"schema":"nonprogress-hand-math-probe/1",
        "created_at_utc":b.search.utc_now(),"cases":old["cases"],
        "previous_manifest_sha256":b.digest((previous.OUT/"manifest.json").read_bytes()),
        "previous_summary_sha256":b.digest((previous.OUT/"summary.json").read_bytes()),
        "reason":"只考察已知有效牌后三对加权支持均相同；另问未直接降向听的摸牌能否改变后续有效枚数，不改写原探查",
        "max_math_calls":3000,"max_process_seconds":120,"runtime":guard.capture(source_paths=[b.Path(__file__),b.Path(previous.__file__)]),
        "scope":"枚举所有公开未见枚数>0的牌种；每种条件摸牌后按最少数学向听、最大未见有效枚数、牌码排序选择数学弃牌；不同后继向听分别汇总，禁止混成校准期望",
        "units":"分组权重为首摸未见枚数，加权和单位枚²；分组均值单位枚，不是实际牌墙概率",
        "model_calls":0,"effect_tables":0,"confirmation_roots":0,"release_eligible":False})
    print("frozen same 3 pairs; all unseen draw types, separate resulting shanten",flush=True)


def run():
    """记录全部第一步摸牌与数学后继，原有效牌分组须复现首份探查。"""
    plan=b.read(OUT/"manifest.json");guard.verify(plan["runtime"])
    assert not (OUT/"started.json").exists()
    b.write(OUT/"started.json",{"at_utc":b.search.utc_now()})
    total=0;reports=[];start_all=perf_counter()
    def analyze(hand,melds):
        nonlocal total
        total+=1
        if total>plan["max_math_calls"]:raise ValueError("超过冻结数学调用上限")
        return analyse_hand(tuple(hand),melds)
    for index,case in enumerate(plan["cases"]):
        path=b.Path(case["input"]);assert b.digest(path.read_bytes())==case["record_sha256"]
        request,full,melds,unseen=previous.material(b.read(path));before=total;case_start=perf_counter()
        actions={a.action_key:a for a in b.behavior.build_scoring_view(request).actions};variants=[]
        original=b.read(previous.OUT/("case-"+str(index+1)+".json"))
        for key in case["actions"]:
            hand=list(full);hand.remove(actions[key].action.tile);groups={};branches=[]
            useful={t.code for t in actions[key].useful_tiles}
            for code,weight in unseen.items():
                if weight<=0:continue
                drawn=hand+[Tile(code)];after_unseen=dict(unseen);after_unseen[code]-=1
                candidates=[]
                for discard in sorted({t.code for t in drawn}):
                    waiting=list(drawn);waiting.remove(Tile(discard));summary=analyze(waiting,melds)
                    support=sum(after_unseen[t.code] for t in summary.useful_tiles)
                    candidates.append({"discard":discard,"shanten":summary.shanten,"support":support})
                best=min(candidates,key=lambda r:(r["shanten"],-r["support"],r["discard"]))
                expected=case["direct_shanten"]-int(code in useful)
                assert best["shanten"]==expected,("原有效牌与后继数学不符",key,code,best,expected)
                group=groups.setdefault(str(best["shanten"]),{"first_draw_unseen_copies":0,"weighted_followup_support_sum":0})
                group["first_draw_unseen_copies"]+=weight
                group["weighted_followup_support_sum"]+=weight*best["support"]
                branches.append({"draw":code,"unseen_copies":weight,"directly_useful":code in useful,
                    "best_math_discard":best,"all_math_discards":candidates})
            for group in groups.values():
                group["weighted_mean_followup_support"]=group["weighted_followup_support_sum"]/group["first_draw_unseen_copies"]
            direct=groups[str(case["direct_shanten"]-1)]
            prior=next(v for v in original["variants"] if v["action"]==key)
            assert direct["first_draw_unseen_copies"]==prior["initial_support"]
            assert direct["weighted_followup_support_sum"]==prior["weighted_followup_support_sum"]
            variants.append({"action":key,"groups_by_resulting_shanten":groups,"branches":branches})
        lower,higher=variants
        a=lower["groups_by_resulting_shanten"];z=higher["groups_by_resulting_shanten"]
        assert set(a)==set(z) and all(a[k]["first_draw_unseen_copies"]==z[k]["first_draw_unseen_copies"] for k in a)
        row={"index":index,"variants":variants,"math_calls":total-before,"elapsed_seconds":perf_counter()-case_start,
            "different_nonprogress_quality":a[str(case["direct_shanten"])]["weighted_followup_support_sum"]!=z[str(case["direct_shanten"])]["weighted_followup_support_sum"],
            "direct_progress_group_reproduced":True}
        b.write(OUT/("case-"+str(index+1)+".json"),row);reports.append(row)
        print("case",index+1,[(v["action"],v["groups_by_resulting_shanten"]) for v in variants],flush=True)
    guard.verify(plan["runtime"])
    b.write(OUT/"summary.json",{"status":"COMPLETE_MATH_DIAGNOSTIC_ONLY","cases":len(reports),
        "different_nonprogress_quality":sum(r["different_nonprogress_quality"] for r in reports),
        "direct_progress_groups_reproduced":all(r["direct_progress_group_reproduced"] for r in reports),
        "math_calls":total,"elapsed_seconds":perf_counter()-start_all,"case_elapsed_seconds":[r["elapsed_seconds"] for r in reports],
        "math_backend":math_backend_info(),"model_calls":0,"effect_tables":0,"confirmation_roots":0,"release_eligible":False,
        "limits":["同三对事后选择输入，不是泛化或效用证据","未核验条件未来弃牌资格与特殊动作、未枚举他家介入",
            "未改变正式评分接口；不能据此声称原可见输入不可区分或必须扩接口","计时有进程缓存与次序影响，不代表最大并发完整动作链"]})


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("operation",choices=("prepare","run"))
    args=p.parse_args();prepare() if args.operation=="prepare" else run()
