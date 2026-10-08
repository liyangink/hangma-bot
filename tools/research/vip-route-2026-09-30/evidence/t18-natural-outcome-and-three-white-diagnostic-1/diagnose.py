"""纯读已闭T17，分解积分与三白实际公开决策；不装载候选或重评。"""

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
from collections import Counter,defaultdict
HERE=Path(__file__).resolve().parent
ROOT=_PROJECT_ROOT
def read(p):return json.loads(p.read_text())
def write(n,v):
    data=json.dumps(v,ensure_ascii=False,indent=2,allow_nan=False).encode()+b"\n"
    assert len(data)<=PLAN["output_byte_limit"]
    with (_project_file(_PROJECT_ROOT, HERE/n)).open("xb") as f:f.write(data)
PLAN=read(_project_file(_PROJECT_ROOT, HERE/"PLAN.json"))
def main():
    began=time.monotonic();af=Path(PLAN["audit_file"]);assert hashlib.sha256(af.read_bytes()).hexdigest()==PLAN["audit_sha256"]
    audit=read(af);assert audit["accepted_engineering_chain"] and audit["runtime_faults_all_zero"]
    raw=Path(PLAN["source_raw_directory"]);manifest=read(raw/"manifest.json");aid=manifest["policy_metadata"]["A"]["policy_id"];cid=manifest["policy_metadata"]["C"]["policy_id"]
    rows=[];partitions={};draws=[];rarehand=defaultdict(list);files={}
    for pool in ("H","M"):
        st=raw/pool/"settlements.jsonl";de=raw/pool/"decisions.jsonl.gz"
        for p in (st,de):files[str(p.resolve())]={"bytes":p.stat().st_size,"sha256":hashlib.sha256(p.read_bytes()).hexdigest()}
        groups={arm:{"own_hu":0,"other_hu":0,"draw":0,"hands":0,"self_hu_fan_counts":Counter(),"own_hu_details":Counter()} for arm in ("A","C")}
        for line in st.read_text().splitlines():
            row=json.loads(line);s=row["settlement"];f=row["focal_physical_seat"];arm="C" if row["match_id"].endswith(":"+cid) else "A"
            assert arm=="C" or row["match_id"].endswith(":"+aid)
            delta=s["score_delta"][f];kind="draw" if s["is_draw"] else "own_hu" if s["winner_seat"]==f else "other_hu"
            g=groups[arm];g[kind]+=delta;g["hands"]+=1
            if kind=="own_hu":
                g["self_hu_fan_counts"][str(s["fan"])]+=1;g["own_hu_details"][" / ".join(s["details"])]+=1
            rows.append({"pool":pool,"root_id":row["root_id"],"permutation":row["permutation"],"arm":arm,"match_id":row["match_id"],"round_no":row["round_no"],"focal_score_delta":delta,"category":kind,"fan":s["fan"],"details":s["details"]})
        for arm,g in groups.items():
            expected=sum(t["focal_score"] for t in audit["pools"][pool]["all_tables"] if t["arm"]==arm)
            assert g["own_hu"]+g["other_hu"]+g["draw"]==expected
            g["total_score"]=expected
        partitions[pool]=groups
        with gzip.open(de,"rt") as stream:
            for line in stream:
                row=json.loads(line)
                if row["policy_id"] not in (aid,cid) or row["white_count"]<3:continue
                arm="C" if row["policy_id"]==cid else "A";k=(pool,row["root_id"],tuple(row["permutation"]),row["observation"]["round_no"],arm)
                simple={"phase":row["phase"],"trigger_seq":row["window_key"]["trigger_seq"],"white_count":row["white_count"],"selected_action_key":row["selected_action_key"],"current_legal_hu":row["current_opportunity"]["legal_hu"]}
                rarehand[k].append(simple)
                if row["phase"]=="draw":
                    draws.append({"pool":pool,"root_id":row["root_id"],"permutation":row["permutation"],"arm":arm,"round_no":row["observation"]["round_no"],"source_file":str(de.resolve()),"source_json_line_sha256":hashlib.sha256(line.encode()).hexdigest(),"public_observation":row["observation"],"window_key":row["window_key"],"all_legal_action_keys":row["legal_action_keys"],"selected_action_key":row["selected_action_key"],"current_opportunity":row["current_opportunity"],"actual_scored_candidates":row["candidates"],"C_input_capture":None if arm=="A" else row["scoring_execution"]["input_capture"]})
    write("SETTLEMENT-DECOMPOSITION.json",{"status":"closed_pure_read_diagnostic_not_strength","source_roots":4,"pool_partitions":partitions,"hand_rows":rows,"business_calls":0})
    write("THREE-WHITE-PUBLIC-DRAWS.json",{"selection":PLAN["selection"],"rows":draws,"reveals_other_hands_or_future_wall":False,"business_calls":0,"not_expert_action_labels":True})
    hands=[]
    for (pool,root,perm,n,arm),values in rarehand.items():
        terminal=next(r for r in rows if r["pool"]==pool and r["root_id"]==root and tuple(r["permutation"])==perm and r["round_no"]==n and r["arm"]==arm)
        hands.append({"pool":pool,"root_id":root,"permutation":list(perm),"round_no":n,"arm":arm,"observation_count":len(values),"choices":values,"final":terminal,"not_same_A_C_current_world":True})
    for p,v in files.items():assert Path(p).stat().st_size==v["bytes"] and hashlib.sha256(Path(p).read_bytes()).hexdigest()==v["sha256"]
    result={"status":"closed_pure_read_diagnostic_not_strength","files":files,"source_roots":4,"all_hands":len(rows),"three_white_public_draws":len(draws),"three_white_unique_mother_roots":len({h["root_id"] for h in hands}),"three_white_pool_arm_hand_records":hands,"business_calls":0,"independent_reviews":0,"elapsed_monotonic_seconds":time.monotonic()-began}
    write("RESULT.json",result)
    print(json.dumps({"partitions":partitions,"three_white_public_draws":len(draws),"rare_hand_endpoints":[{k:v for k,v in h.items() if k!="choices"} for h in hands]},ensure_ascii=False))
if __name__=="__main__":main()
