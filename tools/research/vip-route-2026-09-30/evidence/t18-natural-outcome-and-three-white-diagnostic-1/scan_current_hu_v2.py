"""纯读全部已可胡的实际C公开输入；筛查保持听牌的条件升级，不作存活估计。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t18-natural-outcome-and-three-white-diagnostic-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
import gzip,hashlib,json,time
from pathlib import Path
from collections import Counter
HERE=Path(__file__).resolve().parent
PLAN=json.loads((_project_file(_PROJECT_ROOT, HERE/"PLAN.json")).read_text())
def canon(x):return json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(",",":"),allow_nan=False).encode()
def write(n,x):
    data=json.dumps(x,ensure_ascii=False,indent=2,allow_nan=False).encode()+b"\n"
    assert len(data)<=PLAN["output_byte_limit"]
    with (_project_file(_PROJECT_ROOT, HERE/n)).open("xb") as f:f.write(data)
def main():
    raw=Path(PLAN["source_raw_directory"]);manifest=json.loads((raw/"manifest.json").read_text());cid=manifest["policy_metadata"]["C"]["policy_id"]
    inputs=[]
    for pool in ("H","M"):
        path=raw/pool/"decisions.jsonl.gz"
        with gzip.open(path,"rt") as stream:
            for line_no,line in enumerate(stream,1):
                r=json.loads(line)
                if r["policy_id"]==cid and r["current_opportunity"]["legal_hu"]:
                    inputs.append({"pool":pool,"root_id":r["root_id"],"permutation":r["permutation"],"round_no":r["observation"]["round_no"],"source_file":str(path.resolve()),"source_line":line_no,"source_line_sha256":hashlib.sha256(line.encode()).hexdigest(),"white_count":r["white_count"],"public_observation":r["observation"],"window_key":r["window_key"],"all_legal_action_keys":r["legal_action_keys"],"current_opportunity":r["current_opportunity"],"selected_action_key":r["selected_action_key"],"actual_scored_candidates":r["candidates"],"input_capture":r["scoring_execution"]["input_capture"]})
    wanted={r["input_capture"]["view_sha256"] for r in inputs};views={}
    with gzip.open(raw/"views.jsonl.gz","rt") as stream:
        for line in stream:
            r=json.loads(line)
            if r["view_sha256"] in wanted:
                assert hashlib.sha256(canon(r["view"])).hexdigest()==r["view_sha256"]
                views[r["view_sha256"]]=r["view"]
    assert set(views)==wanted
    facts=[]
    for r in inputs:
        dto=views[r["input_capture"]["view_sha256"]];nodes={n["node_key"]:n for n in dto["nodes"]};seat=dto["visible_state"]["seat"]
        root_action=next(a for a in dto["actions"] if a["action_key"]=="hu")
        current=nodes[root_action["node_key"]];assert current["kind"]=="hu"
        fan=current["settlement"]["fan"];assert fan in r["current_opportunity"]["immediate_fans"];offers=[]
        for a in dto["actions"]:
            n=nodes[a["node_key"]]
            if not a["action_key"].startswith("discard:") or a["action_key"]=="discard:白" or n["kind"]!="wait":continue
            w=n["waiting"];ps=w["normal_draw_hu_payments"]
            if not ps:continue
            code_fans={}
            for p in ps:code_fans.setdefault(p["draw_code"],[]).append(p["settlement"]["fan"])
            capacities=w["unseen_capacities"];evidence=w["unseen_evidence"]
            exact_all=all(e=="exact" and type(c) is int and c>=0 for e,c in zip(evidence,capacities))
            unseen={c:k for c,k in zip(dto["tile_order"],capacities) if type(k) is int and k>0}
            qualified=set(code_fans);covers=exact_all and set(unseen)<=qualified and not w["qualification_unknown_codes"]
            lower=min(min(v) for v in code_fans.values());upper=max(max(v) for v in code_fans.values())
            offers.append({"action_key":a["action_key"],"minimum_qualified_next_fan":lower,"maximum_qualified_next_fan":upper,"qualified_codes":len(qualified),"exact_unseen_capacity_sum":sum(unseen.values()) if exact_all else None,"qualified_capacity_sum":sum(unseen.get(c,0) for c in qualified) if exact_all else None,"all_publicly_unseen_codes_qualified":covers,"all_qualified_next_fans_above_current":lower>fan,"standard_shanten":w["structure"]["standard_shanten"],"seven_pairs_shanten":w["structure"]["seven_pairs_shanten"]})
        facts.append({k:r[k] for k in ("pool","root_id","permutation","round_no","window_key","white_count","selected_action_key","input_capture")}|{"current_fan":fan,"alternatives":offers,"qualification_scope":"normal draw conditional public facts; surviving to own next draw unknown; capacity includes other hands, not wall probability"})
    write("ALL-C-CURRENT-HU-PUBLIC-INPUTS.json",{"selection":"all actual C current legal Hu windows, no score or outcome filter","rows":inputs,"views":views,"business_calls":0})
    write("CURRENT-HU-MAINTAINED-WAIT-FACTS.json",{"status":"closed_pure_read_existing_facts_not_causal_result","rows":facts,"source_windows":len(inputs),"unique_DTOs":len(views),"business_calls":0})
    matching=[r for r in facts if any(a["all_publicly_unseen_codes_qualified"] and a["all_qualified_next_fans_above_current"] for a in r["alternatives"])]
    print(json.dumps({"current_Hu_windows":len(inputs),"unique_DTOs":len(views),"full_coverage_conditional_upgrade_windows":len(matching),"matching_root_ids":sorted({r["root_id"] for r in matching}),"three_white_matching":[r for r in matching if r["white_count"]>=3]},ensure_ascii=False))
if __name__=="__main__":main()
