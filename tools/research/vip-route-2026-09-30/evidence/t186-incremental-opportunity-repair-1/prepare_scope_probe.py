"""封存实际首改选公开输入，核新等待修订是否影响无胡窗口；不生成牌桌。"""

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
    """使用首批全部27分歧，不只取亏损例；对照正式9adb父而非S02。"""
    directory=_project_file(_PROJECT_ROOT, HERE/"natural-stage-001-paths")
    closedpath=directory/"CLOSED.json"
    closed=json.loads(closedpath.read_text())
    assert closed["complete"] and closed["source_stable"] and closed["actual_paired_tables_read"]==32
    rowsfile=directory/"original-public-first-rows.jsonl.gz"
    assert pin(rowsfile)==closed["public_rows_pin"]
    generation=_project_file(_PROJECT_ROOT, HERE/"AUTHOR-resource-release-metadata-repaired/generation.json")
    record=json.loads(generation.read_text())
    parent=_project_file(_PROJECT_ROOT, PRIOR/"AUTHOR-incremental-model-output/candidate.py")
    child=_project_file(_PROJECT_ROOT, HERE/"AUTHOR-resource-release-metadata-repaired/candidate.py")
    assert parent.read_text()==record["parents"][0]["source"]
    cases=[]
    with gzip.open(rowsfile,"rt") as stream:
        for line in stream:
            r=json.loads(line); a,b=r["parent_original_row"],r["child_original_row"]
            digest=a["scoring_calls"][0]["input_capture"]["view_sha256"]
            assert digest==b["scoring_calls"][0]["input_capture"]["view_sha256"]
            cases.append({"label":f"closed-stage1:{r['root']:03d}:{r['rotation']}",
                "observation":a["observation"],"window_key":a["window_key"],"view_sha256":digest,
                "legal_action_keys":a["legal_action_keys"],"has_current_hu":"hu" in a["legal_action_keys"],
                "white_count":a["white_count"],"original_S02_first":a["selected_action_key"],
                "original_357e_first":b["selected_action_key"],
                "original_357e_entries":[{"action_key":c["action_key"],"score":c["score"],"trace":c["trace"]["detail"]} for c in b["candidates"]],
                "original_357e_operations":b["scoring_calls"][0]["candidate_operations"]})
    assert len(cases)==27
    files=[Path(__file__),_project_file(_PROJECT_ROOT, HERE/"run_scope_probe.py"),_project_file(_PROJECT_ROOT, HERE/"AUTHOR-BATCH.json"),closedpath,rowsfile,generation,parent,child]
    target=_project_file(_PROJECT_ROOT, HERE/"SCOPE-PROBE-PLAN.json"); assert not target.exists()
    save(target,{"schema":"t186-formal-parent-scope-probe/1","cases":cases,
        "sources":[str(parent),str(child)],"files":{str(p):pin(p) for p in files},
        "planned_actual_score_calls":54,"planned_new_worlds_tables_models_HTTP":0,
        "known_development_public_inputs_not_strength_or_holdout":True,
        "scope_question":"无胡窗口评分值及首选是否继承正式9adb；与S02差异不自动归因新释放修订。"})
    print(json.dumps({"complete":True,"public_cases":len(cases),"planned_scores":54,
        "without_current_hu":sum(not c["has_current_hu"] for c in cases),"actual_scores":0}))


if __name__=="__main__":
    main()
