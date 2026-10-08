"""吃碰机会代价提案：冻结工程输入、非目标差分及跨执行器检查。"""

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
import ast
import json
import sys
from dataclasses import replace

import tempo_opportunity_batch as batch
import selfdraw_tempo_checks as common
import check_candidate_python_semantics as semantics
from check_discard_arithmetic import action, view
from hangma_bot.policy.action_value_seeds import ActionValueScorer
from sitin_process import run_supervised

b=batch.b
PANEL=batch.OUT/"diagnostic-panel.json"
BOUNDARIES=batch.OUT/"boundary-inputs.json"


def freeze():
    """追加30份真实诊断窗口；在作者交付前冻结输入与非目标行为约束。"""
    assert not PANEL.exists() and not BOUNDARIES.exists()
    old=b.HERE/"selfdraw-tempo-20260920/diagnostic-panel.json"
    rows=b.read(old)["rows"]
    diagnosis=b.HERE/"selfdraw-tempo-diagnostic-20260920"
    for index,item in enumerate(b.read(diagnosis/"panel.json")["windows"]):
        rows.append({"origin":"tempo_real_diagnostic","name":"tempo_diag_"+str(index),
                     "record":b.read(diagnosis/item["file"])})
    for row in rows:
        record=row["record"]
        assert b.behavior.digest(record["request"])==record["request_sha256"]
        assert b.behavior.capture_request(b.behavior.decision_request_from_json(record["request"]))==record
    b.write(PANEL,{"created_at_utc":b.search.utc_now(),"rows":rows,
        "deps_digest":b.search.av_gates().av_deps_digest(),
        "sources":{str(p):b.digest(p.read_bytes()) for p in (old,diagnosis/"panel.json")},
        "scope":"112份既有工程输入与30份新保存但已曝光的真实诊断；不作为强度样本", "selection_eligible":False})
    b.write(BOUNDARIES,{"created_at_utc":b.search.utc_now(),
        "rows":[{"name":name,"view":sample.candidate_view(),"invariant":invariant}
                for name,sample,invariant in common.cases()],
        "scope":"一般合同不变量，机制专属算术待交付后独立推导"})
    b.write(batch.OUT/"scope-inputs.json",{"created_at_utc":b.search.utc_now(),
        "rows":[{"name":name,"view":sample.candidate_view(),"expectation":"same_parent"}
                for name,sample in fallback_cases()],
        "scope":"无过牌或过牌无可信量化事实，新增代价按题面退化；合成合同形状，不声称真实牌谱可达"})
    print("frozen",len(rows),"diagnostic requests",len(common.cases()),"boundaries",len(fallback_cases()),"fallbacks",flush=True)


def fallback_cases():
    """从合同形状覆盖无过牌、无量化过牌及未知分支等退化。"""
    call=action("4b",12,1,"peng")
    return [
        ("no_pass",view((call,action("8t",12,1)),familiar=())),
        ("unknown_pass",view((call,action("",kind="pass")),familiar=())),
        ("unknown_pass_missing_branches",view((replace(call,followup_branches=None),action("",kind="pass")),familiar=())),
        ("no_calls",view((action("4b",12,1),action("8t",10,1)),familiar=())),
    ]


def configure():
    """仅设置本进程辅助器的输入输出路径，不改生产实现或历史文件。"""
    batch.verify()
    common.batch=batch;common.PANEL=PANEL;common.BOUNDARIES=BOUNDARIES


def scope():
    """142请求中比较全部动作，另检查无可比基线时精确退化。"""
    configure();source=common.source_path();plan=b.read(batch.OUT/"manifest.json")
    parent=b.Path(plan["parent"])/"candidate.py"
    scorers={"parent":ActionValueScorer("tempo-parent",parent.read_text()),
             "candidate":ActionValueScorer("tempo-opportunity",source.read_text())}
    rows=[];errors=[];changed=0;noncall=0
    for row in b.read(PANEL)["rows"]:
        request=b.behavior.decision_request_from_json(row["record"]["request"])
        sample=b.behavior.build_scoring_view(request)
        got={name:scorer.score(sample) for name,scorer in scorers.items()}
        if any(result.status!="SCORED" for result in got.values()):
            errors.append([row["name"],"unscored"]);continue
        maps={name:{entry.action_key:entry for entry in result.entries} for name,result in got.items()}
        changes=[]
        for a in sample.actions:
            old,new=maps["parent"][a.action_key],maps["candidate"][a.action_key]
            if a.action_type not in ("chi","peng") and dict(old.trace).get("source")!="unknown":
                noncall+=1
                if new.score!=old.score:errors.append([row["name"],a.action_key,"non_call_known_changed"])
            if new.score!=old.score:
                changes.append({"action":a.action_key,"parent":old.score,"candidate":new.score,"trace":dict(new.trace)})
                changed+=int(a.action_type in ("chi","peng"))
        rows.append({"name":row["name"],"origin":row["origin"],"changes":changes,
                     "operations":scorers["candidate"].last_operation_count})
    fallbacks=[]
    fixed=b.read(batch.OUT/"scope-inputs.json")["rows"]
    for (name,sample),frozen in zip(fallback_cases(),fixed,strict=True):
        assert sample.candidate_view()==frozen["view"] or b.behavior.digest(sample.candidate_view())==b.behavior.digest(frozen["view"])
        values={label:scorer.score(sample) for label,scorer in scorers.items()}
        summaries={label:{"status":value.status,"scores":{e.action_key:e.score for e in value.entries}} for label,value in values.items()}
        same=summaries["parent"]==summaries["candidate"]
        fallbacks.append({"name":name,"same_parent":same,"actual":summaries})
        if not same:errors.append([name,"fallback_changed"])
    def helpers(path):
        root=ast.parse(path.read_text())
        fn=next(n for n in root.body if isinstance(n,ast.FunctionDef) and n.name=="score_actions")
        return {n.name:ast.dump(n,include_attributes=False) for n in fn.body if isinstance(n,ast.FunctionDef)}
    a,z=helpers(parent),helpers(source)
    helper_changes=[name for name,node in a.items() if z.get(name)!=node]
    b.write(batch.OUT/batch.NAME/"scope-check.json",{"status":"PASS" if not errors and changed else "FAIL",
        "source_sha256":b.digest(source.read_bytes()),"parent_sha256":b.digest(parent.read_bytes()),
        "inputs":len(rows),"non_call_known_scores_checked":noncall,"changed_call_scores":changed,
        "parent_helper_ast_changes":helper_changes,"rows":rows,"fallbacks":fallbacks,"errors":errors,
        "limits":"固定输入及语法树比较不能证明所有输入全域等价；辅助函数变动须另作监督审查"})
    print("scope",len(rows),"inputs",changed,"call score changes",len(errors),"errors",helper_changes,flush=True)


def reference(worker=False):
    """人工静态审查后，30秒有界进程比较标准Python与受限语义。"""
    configure();semantics.experiment.OUT=batch.OUT;semantics.checks.PANEL=PANEL
    if worker:
        semantics.worker(batch.NAME,common.source_path());return
    process=run_supervised([sys.executable,__file__,"reference","--worker"],
        cwd=b.ROUTE.parents[1],timeout_sec=30,max_output_chars=200000)
    sub=batch.OUT/batch.NAME;b.write(sub/"reference-process.json",process.to_json())
    assert process.returncode==0 and not process.timed_out and not process.group_still_alive and not process.output_truncated
    result=json.loads(process.stdout)
    result["scope"]=str(result["cases"])+"固定输入跨执行器差分，不证明全域等价或策略增强"
    b.write(sub/"python-semantics-check.json",result);print(result["status"],result["cases"],flush=True)


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation",choices=("freeze","boundary","behavior","scope","reference"))
    parser.add_argument("--worker",action="store_true")
    args=parser.parse_args()
    if args.operation=="freeze":freeze()
    elif args.operation=="reference":reference(args.worker)
    elif args.operation=="scope":scope()
    else:
        configure();getattr(common,args.operation)()
