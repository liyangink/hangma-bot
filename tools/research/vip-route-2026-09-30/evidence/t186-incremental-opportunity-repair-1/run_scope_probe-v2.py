"""持统一研究槽核公开面板的父子作用范围；无世界、牌桌或模型调用。"""

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
import fcntl
import hashlib
import json
import math
import os
import sys
import time
from pathlib import Path

HERE=Path(__file__).resolve().parent
PRIOR=_project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t185-evidence-prioritized-joker-evolution-1')
sys.path.insert(0,str(PRIOR))
from common import OLD,canonical,pin,save
from t185_prepare_confirmation import background_priority
from hangma_bot.hangma.engine import HangmaRules
from hangma_bot.kernel.observation import CompetitionContext
from hangma_bot.kernel.serialization import observation_from_json,window_key_from_json
from hangma_bot.policy.interface import DecisionRequest
from hangma_bot.policy.action_value_executor import ActionValueExecutor
from hangma_bot.policy.route_vip_heuristic import build_vip_route_scoring_view
from hangma_bot.offline.scoring_input_capture import ScoringInputCapture,ScoringInputCaptureLimits
from hangma_bot.offline.vip_eoh_generate import VipEohBatch


def main():
    """先记录原图，后双实现评分；输入不变、完整根、原子输出及计量均核对。"""
    background_priority()
    planpath=_project_file(_PROJECT_ROOT, HERE/"SCOPE-PROBE-STAGE2-PLAN.json"); plan=json.loads(planpath.read_text())
    assert plan["planned_actual_score_calls"]==2*len(plan["cases"])==58
    assert all(pin(Path(p))==h for p,h in plan["files"].items())
    batch=VipEohBatch.read(_project_file(_PROJECT_ROOT, HERE/"AUTHOR-BATCH.json"))
    directory=_project_file(_PROJECT_ROOT, HERE/"formal-parent-scope-probe-stage2"); directory.mkdir(exist_ok=False)
    slotpath=OLD/".resource-scheduling-worker-0.lock"
    save(directory/"WAIT.json",{"pid":os.getpid(),"plan_pin":pin(planpath),"waiting_shared_research_slot":str(slotpath),
        "actual_scores_worlds_tables_models_HTTP":0})
    prior=json.loads(Path(plan["prior_campaign_closed"]).read_text())
    assert prior["complete"] and prior["resources_released"] and prior["worker_returncodes"]==[0]*4
    # 必须先闭合整个派发，避免先抢槽造成原派发的资源释放误拒。
    with slotpath.open("a+") as slot:
        fcntl.flock(slot,fcntl.LOCK_EX)
        assert all(pin(Path(p))==h for p,h in plan["files"].items())
        save(directory/"START.json",{"pid":os.getpid(),"plan_pin":pin(planpath),"shared_slot_held":str(slotpath),
            "planned_actual_scores":58,"new_worlds_tables_models_HTTP":0})
        executors=[ActionValueExecutor(Path(p).read_text(),max_operations=batch.max_operations,
            max_local_collection_size=batch.projection_limits.max_nodes) for p in plan["sources"]]
        raw=(directory/"views.jsonl.gz").open("x+b")
        capture=ScoringInputCapture(raw,limits=ScoringInputCaptureLimits(67108864,268435456,64))
        rows,attempts,failure,terminal=[],0,None,None
        try:
            with (directory/"rows.jsonl").open("x") as output:
                for case in plan["cases"]:
                    obs=observation_from_json(case["observation"]); key=window_key_from_json(case["window_key"])
                    analysis=HangmaRules(batch.rule_config).analyze(obs,route_limits=batch.route_limits)
                    assert analysis.completeness.value=="complete"
                    request=DecisionRequest(obs,CompetitionContext("t186-scope",None,None,None,None,(),0),
                        analysis,case["label"],key.trigger_seq,key,())
                    view=build_vip_route_scoring_view(request,batch.rule_config,limits=batch.projection_limits)
                    assert hashlib.sha256(canonical(view.candidate_view())).hexdigest()==case["view_sha256"]
                    legal=set(case["legal_action_keys"]); entries,firsts,ops,seconds=[],[],[],[]
                    for executor in executors:
                        receipt=capture.store(view.candidate_view()); assert receipt.saved_before_score
                        attempts+=1; started=time.monotonic(); answer=executor.score_vip_route(view)
                        seconds.append(time.monotonic()-started)
                        assert answer.status=="SCORED"
                        values=sorted([{"action_key":e.action_key,"score":e.score,"trace":dict(e.trace)} for e in answer.entries],key=lambda e:e["action_key"])
                        assert len(values)==len(legal) and {e["action_key"] for e in values}==legal
                        assert all(type(e["score"]) in (int,float) and math.isfinite(e["score"]) for e in values)
                        assert hashlib.sha256(canonical(view.candidate_view())).hexdigest()==case["view_sha256"]
                        entries.append(values); ops.append(executor.last_operation_count)
                        firsts.append(sorted(values,key=lambda e:(-e["score"],e["action_key"]))[0]["action_key"])
                    original=sorted(case["original_357e_entries"],key=lambda e:e["action_key"])
                    assert canonical(entries[1])==canonical(original) and ops[1]==case["original_357e_operations"]
                    numeric_same=[(e["action_key"],e["score"]) for e in entries[0]]==[(e["action_key"],e["score"]) for e in entries[1]]
                    row={"label":case["label"],"has_current_hu":case["has_current_hu"],"white_count":case["white_count"],
                        "formal_parent_first":firsts[0],"new_candidate_first":firsts[1],"full_numeric_scores_equal":numeric_same,
                        "first_equal":firsts[0]==firsts[1],"operations":ops,"score_monotonic_seconds":seconds,
                        "view_sha256":case["view_sha256"],"entries":entries}
                    rows.append(row); output.write(canonical(row).decode()+"\n"); output.flush()
        except BaseException as error:
            failure={"type":type(error).__name__,"message":str(error)}
        finally:
            try: terminal=capture.finish()
            except BaseException as error: failure=failure or {"type":type(error).__name__,"message":str(error)}
            raw.close()
        stable=all(pin(Path(p))==h for p,h in plan["files"].items())
        complete=failure is None and stable and len(rows)==29 and terminal["terminal"]["terminal_valid"]
        unanchored=[r for r in rows if not r["has_current_hu"]]
        result={"complete":complete,"failure":failure,"source_stable":stable,"plan_pin":pin(planpath),
            "actual_completed_cases":len(rows),"actual_score_attempts":attempts,
            "without_current_hu_cases":len(unanchored),
            "without_current_hu_full_numeric_scores_equal":all(r["full_numeric_scores_equal"] for r in unanchored),
            "without_current_hu_first_equal":all(r["first_equal"] for r in unanchored),
            "with_current_hu_first_changed":sum(not r["first_equal"] for r in rows if r["has_current_hu"]),
            "rows_pin":pin(directory/"rows.jsonl"),"capture":terminal,
            "new_worlds_tables_models_HTTP":0,"original_deadline_or_strength_admission":False}
        save(directory/"CLOSED.json",result)
        assert complete,"作用范围探针失败，保留原件与费用，不自动重试"
        print(json.dumps({k:result[k] for k in ("complete","actual_score_attempts","without_current_hu_cases",
            "without_current_hu_full_numeric_scores_equal","without_current_hu_first_equal","with_current_hu_first_changed")}))


if __name__=="__main__":
    main()
