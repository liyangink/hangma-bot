"""用实际R18原记录、完整512桌元数据及精确负例验证读回；不提取积分。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t185-evidence-prioritized-joker-evolution-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
import ast
import copy
import json
from pathlib import Path

from common import HERE, OLD, ROOT, pin, save
import t185_close_development as dev
from readout_compat import copied_readout, metadata_adapter, prior_modules, R18_DONE, CHECKED, FAILURE, CONTRACT
from dispatch_with_readout_compat import dispatch_context


def main():
    """真实误拒红灯、校正绿灯和负例并查；保留原错误、原字段及所有统计代码。"""
    repair, resume, resources = prior_modules()
    plan, plan_pin = dev.read(OLD / "DEVELOPMENT-PLAN.json")
    original_files = {str(p): pin(p) for p in (OLD / "DEVELOPMENT-PLAN.json", Path(repair.__file__),
        Path(resume.__file__), Path(resources.__file__), Path(repair.dev.__file__),
        _project_file(_PROJECT_ROOT, ROOT / "src/hangma_bot/policy/action_value_policy.py"))}
    evidence = OLD / "natural-development/root-002/seat-0-arm-0"
    closure, closure_pin = dev.read(evidence / "CLOSURE.json")
    table = dev.TableEvidence(2,0,0,evidence,dev.pin(evidence / "START.json"),closure_pin,dev.pin(evidence / "PAIRING-IDENTITY.json"))
    bad = next(r for r in closure["outcome"]["decisions"] if r["seat"] == 2)
    minimal = {**closure,"outcome":{**closure["outcome"],"decisions":[copy.deepcopy(bad)]}}
    reds = []
    for _ in range(2):
        try:
            repair.decision_metadata(table,minimal,plan)
        except ValueError as error:
            dev.require(str(error) == "R18动态对象ID未知/缺失或含降级", "没有复现同一错误")
            reds.append(str(error))
        else:
            raise ValueError("原误拒未复现")
    failure, _ = dev.read(FAILURE)
    dev.require(failure["actual_exit_code"] == 1 and failure["tool_session"] == 69528 and
        failure["original_plan_pin"] == plan_pin and not (OLD / "DEVELOPMENT-CLOSED.json").exists(),
        "原失败或闭合边界不符")
    originals = (repair.decision_metadata,dev.decision_metadata)
    adapters = tuple(metadata_adapter(f) for f in originals)
    negative_count = 0
    for adapter in adapters:
        before = json.dumps(minimal,ensure_ascii=False,sort_keys=True)
        _,_,audit = adapter(table,minimal,plan)
        dev.require(audit["r18_success_information_count"] == 1 and
            audit["opponent_compatibility_diagnostic_counts_by_type"]["r18"] == {R18_DONE:1} and
            json.dumps(minimal,ensure_ascii=False,sort_keys=True) == before, "成功信息丢失或原记录改写")
        changes = [
            {"degraded_reasons":[R18_DONE,"unknown"]}, {"degraded_reasons":[R18_DONE,R18_DONE]},
            {"degraded_reasons":["action_value_failed: ABSTAIN"]}, {"degraded_reasons":["规则降级[x]：x"]},
            {"policy_id":None}, {"policy_id":"wrong"}, {"fallback_reason":"failed"}, {"legal":False},
            {"seat":0,"window_key":{**bad["window_key"],"seat":0}},
        ]
        for changed in changes:
            broken=copy.deepcopy(minimal);broken["outcome"]["decisions"][0].update(changed)
            try:adapter(table,broken,plan)
            except ValueError:negative_count+=1
            else:raise ValueError("负例被接受:"+str(changed))
    r18_total=0
    table_files={}
    all_types=set()
    for ix,root in enumerate(plan["roots"],1):
        all_types.update(root["opponent_types_logical_1_2_3"])
        for seat in plan["rotations"]:
            for arm in range(4):
                directory=OLD / "natural-development" / f"root-{ix:03d}" / f"seat-{seat}-arm-{arm}"
                actual,cp=dev.read(directory / "CLOSURE.json")
                current=dev.TableEvidence(ix,seat,arm,directory,dev.pin(directory / "START.json"),cp,dev.pin(directory / "PAIRING-IDENTITY.json"))
                counts=[]
                for adapter in adapters:
                    _,_,audit=adapter(current,actual,plan)
                    counts.append(audit["r18_success_information_count"])
                dev.require(counts[0] == counts[1], "旧/新元数据校验结果不一致")
                r18_total+=counts[0]
                table_files[str(directory / "CLOSURE.json")]=cp
    dev.require(all_types == {"r18","automatic_like","normal_v0"} and r18_total==226102, "真实对手覆盖或R18说明分母不符")
    # 成功说明的生产出处核原AST，不从字段名称推断成降级。
    production=ast.parse((_project_file(_PROJECT_ROOT, ROOT / "src/hangma_bot/policy/action_value_policy.py")).read_bytes())
    scorer=next(n for n in ast.walk(production) if isinstance(n,ast.FunctionDef) and n.name=="_scored_plan")
    dev.require(any(isinstance(n,ast.Constant) and n.value=="action_value: {0} 评分完成" for n in ast.walk(scorer)), "正常成功说明源码不符")
    for module in (repair,dev):
        context=copied_readout(module,unchecked=True)
        for name in ("account","comparisons"):
            dev.require(context[name] is getattr(module,name), "原统计函数被替换:"+name)
        dev.require(context["score_receipts"].__code__ is module.score_receipts.__code__, "实际receipt核验代码被改")
        dev.require(context["decision_metadata"] is not module.decision_metadata, "兼容未进入真实调用接缝")
        dev.require(module.score_receipts.__globals__["decision_metadata"] is module.decision_metadata, "旧模块globals被改")
    import t185_close_confirmation as confirm
    context=copied_readout(confirm,confirmation=True,unchecked=True)
    for name in ("account","summarize","bootstrap_interval"):
        dev.require(context[name] is getattr(confirm,name), "确认原统计函数被替换")
    dispatch_changes={phase:dispatch_context(phase)["compatibility_transform_counts"] for phase in ("development","confirmation")}
    dev.require(all(pin(Path(p))==h for p,h in original_files.items()), "检查期间原源码或计划漂移")
    tools=(Path(__file__), _project_file(_PROJECT_ROOT, HERE / "readout_compat.py"), _project_file(_PROJECT_ROOT, HERE / "close_prior_with_readout_compat.py"),
        _project_file(_PROJECT_ROOT, HERE / "close_with_readout_compat.py"), _project_file(_PROJECT_ROOT, HERE / "dispatch_with_readout_compat.py"), CONTRACT, FAILURE,
        _project_file(_PROJECT_ROOT, HERE / "t185_close_development.py"), _project_file(_PROJECT_ROOT, HERE / "t185_close_confirmation.py"), _project_file(_PROJECT_ROOT, HERE / "dispatch_development.py"),
        _project_file(_PROJECT_ROOT, HERE / "dispatch_confirmation.py"), _project_file(_PROJECT_ROOT, HERE / "DEVELOPMENT-PLAN.json"))
    save(CHECKED,{"complete":True,"original_red_twice":reds,"minimal_actual_decision":bad,
        "actual_metadata_tables":512,"actual_old_new_metadata_validator_calls":1024,
        "r18_success_information_count":r18_total,"opponent_types_covered":sorted(all_types),
        "negative_checks":negative_count,"all_negative_checks_passed":True,
        "statistics_and_selection_unchanged":True,"dispatch_transform_counts":dispatch_changes,
        "original_module_globals_unchanged":True,"files":{**original_files,**{str(p):pin(p) for p in tools}},
        "actual_metadata_table_files":table_files,"new_scores_worlds_tables":0,
        "strength_deadline_release_admission":False})
    print(json.dumps({"original_red":True,"actual_tables_checked":512,"r18_information":r18_total,
        "negative_checks":negative_count,"statistics_unchanged":True,"new_scores_worlds_tables":0},ensure_ascii=False))


if __name__ == "__main__":
    main()
