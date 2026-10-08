"""T17新4母根自然桌的根代理纯读核验，不导入生产或重做评分/规则/世界。"""
from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t17-natural-closure-2'

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
from collections import Counter, defaultdict
import gzip
import hashlib
import json
import math
from pathlib import Path
import statistics

HERE = Path(__file__).resolve().parent
AUTHOR = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t17-public-interruption-trade-author-1')
ROOT = next(p for p in HERE.parents if (p / "review/INDEX.md").exists())
RAW = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t17-public-interruption-trade-author-1/S01-natural-development-64')
RAW_SEAL = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t17-natural-closure-2/RAW-FIRST-SEAL.json')
ROOT_START = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t17-public-interruption-trade-author-1/S01-NATURAL-ROOT-START.json')
PINS = {}
CID = "b198e694fb46bb95cfac31b0d14a08744e018efb5f0966034b4015a31b05f655"
SOURCE = "a32ee8e2f7c6b3a17899ff3a07bf9559ad15cbc38775962f404338074cb1d38b"
INPUTS = {}


def unique(pairs):
    result = {}
    for k, v in pairs:
        assert k not in result, "duplicate JSON key:" + k
        result[k] = v
    return result


def decode(data):
    return json.loads(data, object_pairs_hook=unique, parse_constant=lambda x: (_ for _ in ()).throw(ValueError(x)))


def read(p):
    return decode(Path(p).read_bytes())


def canon(v):
    return json.dumps(v, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def sha(data):
    return hashlib.sha256(data).hexdigest()


def meta(p):
    h = hashlib.sha256()
    size = 0
    with Path(p).open("rb") as f:
        while block := f.read(1024 * 1024):
            h.update(block)
            size += len(block)
    return {"bytes": size, "sha256": h.hexdigest()}


def write(name, value, verify):
    """新审计原件排他写；verify只比较，不更新既封资料。"""
    raw = canon(value) + b"\n"
    if verify:
        assert (_project_file(_PROJECT_ROOT, HERE / name)).read_bytes() == raw, name
    else:
        with (_project_file(_PROJECT_ROOT, HERE / name)).open("xb") as f:
            f.write(raw)


def jsonl(p):
    with p.open() as f:
        return [decode(line) for line in f]


def identity(identity, source):
    """独立算CID和依赖摘要，只做哈希与严格JSON，不装载候选。"""
    assert sha(canon({"source_manifest": identity["source_manifest"], "math_backend": identity["math_backend"]})) == identity["deps_digest"]
    assert sha(source) == identity["source_sha256"]
    payload = {"candidate_kind": "vip_route_heuristic_v1", "source": source.decode(), "contract_sha256": identity["contract_sha256"],
        "deps_digest": identity["deps_digest"], "params": identity["params"], "view_schema_version": identity["view_schema_version"],
        "structure_semantics_version": "vip-route-structure/1", "normal_draw_hu_payment_semantics_version": identity["normal_draw_hu_payment_semantics_version"],
        "executor_version": "action-value-executor/6"}
    assert sha(canon(payload)) == identity["candidate_id"]


def lineage(package, seen=None):
    """按真实原件递归来源，不把额度重绑定写成新模型调用。"""
    seen = set() if seen is None else seen
    package = Path(package).resolve()
    assert package.is_relative_to(ROOT) and package not in seen and len(seen) < 32
    seen.add(package)
    record, source = read(package / "generation.json"), (package / "candidate.py").read_bytes()
    for p in (package / "generation.json", package / "candidate.py"):
        INPUTS[str(p)] = meta(p)
    identity(record["identity"], source)
    assert record["source_sha256"] == sha(source) and record["status"] == "loaded_not_admitted"
    row = {"package": str(package), "candidate_id": record["identity"]["candidate_id"], "source_sha256": sha(source),
        "generation_sha256": meta(package / "generation.json")["sha256"], "artifact_role": record["artifact_role"],
        "max_operations": record["identity"]["params"]["max_operations"], "is_model_output": record["is_model_output"]}
    if record["artifact_role"] in ("research_budget_rebind", "trace_codec_repair"):
        p = record["provenance"]
        old = Path(p["original_package_path"])
        assert (package / "original-generation.json").read_bytes() == (old / "generation.json").read_bytes()
        assert (package / "original-candidate.py").read_bytes() == (old / "candidate.py").read_bytes()
        assert meta(old / "generation.json")["sha256"] == p["original_generation_sha256"]
        assert meta(old / "candidate.py")["sha256"] == p["original_source_sha256"]
        assert record["is_model_output"] is False and record["billing"]["call_started"] is False
        assert all(v == 0 for v in record["billing"]["charged"].values())
        original = read(old / "generation.json")
        assert p["source_identity"] == original["identity"] and p["target_identity"] == record["identity"]
        assert all(original.get(k) == v for k, v in p["original_author_evidence"].items())
        if record["artifact_role"] == "research_budget_rebind":
            assert source == (old / "candidate.py").read_bytes()
        row["origin"] = lineage(old, seen)
    else:
        row["parents"] = []
        for parent in record.get("parents", []):
            p = Path(parent["path"])
            assert meta(p / "generation.json")["sha256"] == parent["record_sha256"]
            assert meta(p / "candidate.py")["sha256"] == parent["source_sha256"]
            assert read(p / "generation.json")["identity"] == parent["identity"]
            assert (p / "candidate.py").read_bytes() == parent["source"].encode()
            row["parents"].append(lineage(p, set(seen)))
    return row


def percentiles(values):
    values = sorted(values)
    return {"count": len(values), "min": values[0], "median": statistics.median(values),
        "p95": values[math.ceil(.95 * len(values)) - 1], "p99": values[math.ceil(.99 * len(values)) - 1], "max": values[-1]}



def full_inputs(identity, batch, costs, summary, end):
    """纯读实际评分前保存的完整DTO，核图闭合、公开字段及费用，不补造输入。"""
    capture = costs["scoring_input_capture"]; terminal = capture["terminal"]
    assert capture == summary["scoring_input_capture"] and terminal == end["scoring_input_capture_terminal"]
    assert terminal["closed"] and terminal["verified"] and terminal["terminal_valid"] and terminal["storage_valid"]
    assert not terminal["errors"] and terminal["store_calls_reconciled"] and terminal["binary_stream_closed"]
    assert terminal["scoring_audit_failed_calls"] == terminal["decision_audit_sink_failed_calls"] == 0
    assert capture["failed_store_calls"] == 0 and capture["last_store_failure"] is None
    assert capture["store_calls"] == capture["encode_attempts"] == capture["unique_views_saved"] + capture["deduplicated_calls"]
    observed = meta(_project_file(_PROJECT_ROOT, RAW / "views.jsonl.gz"))
    assert observed["sha256"] == terminal["compressed_sha256"] and observed["bytes"] == terminal["observed_compressed_bytes"]
    module=ast.parse((_project_file(_PROJECT_ROOT, RAW / "code_snapshot/src/hangma_bot/kernel/actions.py")).read_text())
    codes=next(ast.literal_eval(n.value) for n in module.body if isinstance(n,ast.AnnAssign) and isinstance(n.target,ast.Name) and n.target.id=="CANONICAL_TILE_ORDER")
    expected_binding={**identity["params"]["rule_config"],"executor_version":"action-value-executor/6","structure_semantics_version":"vip-route-structure/1","normal_draw_hu_payment_semantics_version":identity["normal_draw_hu_payment_semantics_version"]}
    views={}; total=0
    with gzip.open(_project_file(_PROJECT_ROOT, RAW / "views.jsonl.gz"),"rt") as f:
        for ordinal,line in enumerate(f,1):
            record=decode(line); dto=record["view"]; raw=canon(dto); key=sha(raw)
            assert set(record)=={"schema","view_sha256","json_bytes","view"}
            assert key==record["view_sha256"] and key not in views and len(raw)==record["json_bytes"]
            assert set(dto)=={"schema_version","candidate_kind","graph_schema_version","tile_order","visible_state","binding","limits","workload","actions","nodes"}
            assert dto["schema_version"]==identity["view_schema_version"] and dto["graph_schema_version"]==identity["graph_schema_version"]
            assert dto["candidate_kind"]=="vip_route_heuristic_v1" and dto["tile_order"]==list(codes)
            assert set(dto["visible_state"])=={"seat","dealer_seat","phase","my_hand","drawn_tile","remaining_tile_count","discards","melds","hand_counts"}
            assert dto["binding"]==expected_binding and dto["limits"]==identity["params"]["projection_limits"]
            nodes={}; edges=0
            for n in dto["nodes"]:
                nk=n["node_key"]
                assert nk not in nodes and n["gap_kind"] is None and not n.get("gap_kinds")
                assert n["expected_child_count"]==n["completed_child_count"]==len(n["children"])
                assert set(n["children"])<=set(nodes)
                nodes[nk]=n;edges+=len(n["children"])
            todo=[a["node_key"] for a in dto["actions"]]; reached=set()
            while todo:
                nk=todo.pop()
                if nk not in reached:reached.add(nk);todo.extend(nodes[nk]["children"])
            assert reached==set(nodes)
            keys=[a["action_key"] for a in dto["actions"]];assert len(keys)==len(set(keys)) and keys
            w=dto["workload"]; lim=dto["limits"]
            assert w["expanded_node_count"]==len(nodes)<=lim["max_nodes"] and w["expanded_branch_count"]==edges<=lim["max_branches"]
            assert type(w["waiting_draw_witness_count"]) is int and 0<=w["waiting_draw_witness_count"]<=lim["max_waiting_draw_witnesses"]
            assert type(w["target_distance_evaluation_count"]) is int and w["target_distance_evaluation_count"]>=0
            assert len(raw)<=batch["scoring_input_capture"]["max_view_json_bytes"]
            views[key]={"visible_state":dto["visible_state"],"legal_action_keys":keys,"json_bytes":len(raw),"workload":w}
            total+=len(raw)
            if ordinal%5000==0:print(json.dumps({"phase":"actual_input_stream","views":ordinal}),flush=True)
    assert len(views)==capture["unique_views_saved"]==terminal["verified_unique_views"]
    assert total==capture["unique_json_bytes_saved"]<=batch["scoring_input_capture"]["max_total_json_bytes"]
    assert len(views)<=batch["scoring_input_capture"]["max_unique_views"]
    return views,capture

def main(verify=False):
    PINS.update({str(RAW_SEAL):meta(RAW_SEAL)["sha256"], str(ROOT_START):meta(ROOT_START)["sha256"]})
    sealed, start = read(RAW_SEAL), read(ROOT_START)
    assert sealed["actual_cli_exit_code"] == 0 and sealed["file_count"] == len(sealed["files"])
    assert sealed["total_bytes"] == sum(r["bytes"] for r in sealed["files"].values())
    assert {str(p.resolve()) for p in RAW.rglob("*") if p.is_file()} == set(sealed["files"])
    for path, expected in sealed["files"].items():
        assert meta(path) == expected, path
        INPUTS[path] = expected
    assert start["status"] == "START" and start["planned_complete_table_instances"] == 64
    assert start["R18_reference_tables"] == start["candidate_tables"] == 32 and start["source_roots"] == 4
    assert start["candidate_id"] == CID and start["development_only"] is True and start["not_confirmation_or_release"] is True
    assert start["seeds_frozen_before_author"] is True and start["new_independent_reviews"] == 0
    assert meta(Path(start["batch_path"]))["sha256"] == start["batch_sha256"]
    assert Path(start["batch_path"]).read_bytes() == (_project_file(_PROJECT_ROOT, RAW / "batch.json")).read_bytes()
    ep=_project_file(_PROJECT_ROOT, AUTHOR / "EVALUATION-PLAN.json"); assert meta(ep)["sha256"]==start["evaluation_plan_sha256"]
    assert read(ep)["fresh_natural_development_frame"]["seed_ids"]==list(range(2026102101,2026102105))
    assert meta(_project_file(_PROJECT_ROOT, AUTHOR / "ROOT-PUBLIC-PROBE-CHECK.json"))["sha256"]==start["root_gate_sha256"]
    for path,digest in start["local_closure_gates"].items(): assert meta(path)["sha256"]==digest
    for p in (RAW_SEAL, ROOT_START, Path(__file__)):
        INPUTS[str(p)] = meta(p)
    ancestry = lineage(_project_file(_PROJECT_ROOT, AUTHOR / "S01-model-output"))
    write("READER-SOURCE-FIRST-SEAL.json", {"schema": "t11-natural-reader-source/1", "files": INPUTS,
        "pins": PINS, "source_sealed_before_full_stream_audit": True}, verify)
    manifest, end, batch, costs, summary = [read(_project_file(_PROJECT_ROOT, RAW / name)) for name in ("manifest.json", "end-freeze.json", "batch.json", "costs.json", "summary.json")]
    gen = read(_project_file(_PROJECT_ROOT, RAW / "candidate-generation.json"))
    assert gen == read(_project_file(_PROJECT_ROOT, AUTHOR / "S01-model-output/generation.json"))
    assert manifest["candidate_identity"] == end["candidate_identity"] == gen["identity"]
    assert gen["identity"]["candidate_id"] == CID and gen["identity"]["source_sha256"] == SOURCE
    identity(gen["identity"], (_project_file(_PROJECT_ROOT, RAW / "candidate.py")).read_bytes())
    assert manifest["source_manifest"] == end["source_manifest"] and end["identity_stable"] is True and end["end_error"] is None
    assert sha((_project_file(_PROJECT_ROOT, RAW / "contract.md")).read_bytes()) == gen["identity"]["contract_sha256"]
    assert sha((_project_file(_PROJECT_ROOT, RAW / "math-native.bin")).read_bytes()) == gen["identity"]["math_backend"]["native_binary"]["sha256"]
    for path, expected in manifest["source_manifest"].items():
        assert meta(_project_file(_PROJECT_ROOT, RAW / "code_snapshot" / path)) == expected
    for path, expected in gen["identity"]["source_manifest"].items():
        assert meta(_project_file(_PROJECT_ROOT, RAW / "code_snapshot" / path)) == expected
    assert meta(_project_file(_PROJECT_ROOT, RAW / "batch.json"))["sha256"] == manifest["batch_sha256"] == meta(_project_file(_PROJECT_ROOT, AUTHOR / "S01-natural-development-64.batch.json"))["sha256"]
    assert (_project_file(_PROJECT_ROOT, RAW / "batch.json")).read_bytes() == (_project_file(_PROJECT_ROOT, AUTHOR / "S01-natural-development-64.batch.json")).read_bytes()
    assert batch["rounds"] == 8 and batch["table_instance_limit"] == 64 and batch["pools"] == ["H", "M"]
    assert [s["seed"] for s in batch["seeds"]] == list(range(2026102101, 2026102105))
    roots = [s["root_id"] for s in batch["seeds"]]
    permutations = [(0,1,2,3), (1,2,3,0), (2,3,0,1), (3,0,1,2)]
    assert all(s["permutations"] == [list(p) for p in permutations] for s in batch["seeds"])
    assert manifest["strict_challenger"] is True and manifest["clock_mode"] == "logical"
    assert manifest["config"]["rounds_per_game"] == 8 and manifest["initial_dealer_physical"] == 0
    assert summary["status"] == "development_complete_not_confirmed" and summary["identity_stable"] is True
    assert summary["duration_wall_seconds"] <= batch["wall_clock_limit_seconds"] == 3600
    expected_pairs = {(pool, root, p) for pool in ("H", "M") for root in roots for p in permutations}
    assert {(x["pool"], x["root_id"], tuple(x["permutation"])) for x in costs["entries"]} == expected_pairs
    assert len(costs["entries"]) == 32 and all(x["status"] == "settled" and all(x[k] == 2 for k in ("reserved_table_instances", "charged_table_instances", "actual_started_table_instances")) for x in costs["entries"])
    assert sum(x["charged_table_instances"] for x in costs["entries"]) == costs["planned_table_instances"] == 64
    metadata = manifest["policy_metadata"]
    aid, cid = metadata["A"]["policy_id"], "vip:" + CID
    assert metadata["C"]["policy_id"] == cid and metadata["C"]["identity"] == gen["identity"]
    assert sha((_project_file(_PROJECT_ROOT, RAW / "r18.py")).read_bytes()) == metadata["A"]["source_sha256"]
    frozen = {k: v for k, v in metadata["A"].items() if k != "policy_id"}
    rid = sha(json.dumps(frozen, ensure_ascii=False, sort_keys=True, allow_nan=False).encode())
    assert aid == "research-r18-v2:" + rid
    for label in ("H1", "H2", "H3", "M1"):
        assert {k:v for k,v in metadata[label].items() if k != "policy_id"} == frozen
        assert metadata[label]["policy_id"] == label + ":" + rid
    for label in ("M2", "M3"):
        body = {k:v for k,v in metadata[label].items() if k != "policy_id"}
        assert metadata[label]["policy_id"] == label + ":" + sha(json.dumps(body, ensure_ascii=False, sort_keys=True, allow_nan=False).encode())
    producer = (_project_file(_PROJECT_ROOT, RAW / "code_snapshot/src/hangma_bot/offline/vip_route_development.py")).read_text()
    # T10 /2 的真实记录器已经签收。以实际AST及成功调用原件核验，
    # 不再套用早期T11“没有candidate_view/逐窗last=None”的旧文本形状。
    producer_tree = ast.parse(producer)
    scoring = next(n for n in producer_tree.body if isinstance(n,ast.ClassDef) and n.name=="_ScoringAudit")
    method = next(n for n in scoring.body if isinstance(n,ast.FunctionDef) and n.name=="score_vip_route")
    vc=[n for n in ast.walk(method) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr=="candidate_view"]
    store=[n for n in ast.walk(method) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr=="store"]
    score=[n for n in ast.walk(method) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr=="score_vip_route"]
    assert len(vc)==len(store)==len(score)==1 and vc[0].lineno < store[0].lineno < score[0].lineno
    assert ast.unparse(store[0].func)=="self.capture.store" and ast.unparse(score[0].func)=="self.executor.score_vip_route"
    begin=next(n for n in scoring.body if isinstance(n,ast.FunctionDef) and n.name=="begin_decision")
    resets=[n for n in ast.walk(begin) if isinstance(n,ast.Assign) and ast.literal_eval(n.value)==(None,[])]
    assert len(resets)==1 and ast.unparse(resets[0].targets[0])=="(self.last, self.decision_calls)"
    policy=next(n for n in producer_tree.body if isinstance(n,ast.ClassDef) and n.name=="VipDevelopmentAuditPolicy")
    choose=next(n for n in policy.body if isinstance(n,ast.AsyncFunctionDef) and n.name=="choose")
    resetcalls=[n for n in ast.walk(choose) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr=="begin_decision"]
    chooses=[n for n in ast.walk(choose) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and ast.unparse(n.func)=="self.inner.choose"]
    assert len(resetcalls)==len(chooses)==1 and resetcalls[0].lineno < chooses[0].lineno
    assert "C未以SCORED完整独立评分本窗口" in producer and "strict_challenger=True" in producer
    views, capture_stats = full_inputs(gen["identity"], batch, costs, summary, end)
    capture_calls, capture_references, encoded_bytes = {}, Counter(), [0]
    pools, all_c_ops, all_c_ms, all_ms = {}, [], [], []
    coverage = {arm:defaultdict(list) for arm in ("A", "C")}
    all_current_hu = []
    total_decisions = 0
    for pool in ("H", "M"):
        results = {r["game_key"]["game_id"]:r for r in jsonl(_project_file(_PROJECT_ROOT, RAW / pool / "results.jsonl"))}
        outcomes = {r["match_id"]:r["outcome"] for r in read(_project_file(_PROJECT_ROOT, RAW / pool / "match-outcomes.json"))}
        assert len(results) == len(outcomes) == 32 and set(results) == set(outcomes)
        expected_decisions, pairs, tables, runtime = {}, defaultdict(dict), [], Counter()
        for root in roots:
            for perm in permutations:
                group = read(_project_file(_PROJECT_ROOT, RAW / pool / ("group-" + sha(root.encode())[:16] + "-" + "".join(map(str,perm)) + ".json")))
                exp = group["experiment"]
                assert not group["excluded"] and len(group["results"]) == len(group["match_records"]) == 2
                assert exp["seeds"] == [{"scenario_id":root, "seed":batch["seeds"][roots.index(root)]["seed"]}]
                assert exp["seat_permutations"] == [list(perm)] and exp["initial_dealer"] == perm.index(0)
                assert exp["initial_scores"] == [0]*4 and exp["clock_mode"] == "logical" and exp["step_limit"] == batch["step_limit"] == 10000
                opponents = [metadata[k]["policy_id"] for k in (("H1","H2","H3") if pool == "H" else ("M1","M2","M3"))]
                assert [x["policy_id"] for x in exp["opponents"]] == opponents
                assert all(r == results[r["game_key"]["game_id"]] for r in group["results"])
                assert all(r["outcome"] == outcomes[r["match_id"]] for r in group["match_records"])
                for arm, policy in (("A",aid),("C",cid)):
                    mid = batch["batch_id"] + ":" + pool + ":" + root + ":" + "".join(map(str,perm)) + ":" + policy
                    r, outcome = results[mid], outcomes[mid]
                    physical = [None]*4
                    for logical, pid in enumerate([policy]+opponents):physical[perm[logical]] = pid
                    assert r["policy_ids_by_seat"] == physical and r["seat_permutation"] == list(perm) and r["scenario_id"] == root
                    assert r["status"] == outcome["status"] == "complete" and r["completed_hands"] == r["expected_hands"] == outcome["completed_hands"] == 8
                    assert r["scores_before"] == [0]*4 and r["scores_after"] == outcome["final_scores"] and sum(r["scores_after"]) == 0
                    assert not r["invalid_reasons"] and outcome["blocked_reason"] is None and outcome["error_reason"] is None
                    assert r["runtime_counts"] == outcome["runtime_counts"] and not any(r["runtime_counts"].values()) and outcome["steps"] <= batch["step_limit"]
                    runtime.update(r["runtime_counts"])
                    pairs[(root,perm)][arm] = r["scores_after"][perm[0]]
                    tables.append(dict(pool=pool,root_id=root,permutation=list(perm),arm=arm,match_id=mid,focal_score=r["scores_after"][perm[0]],four_seat_scores=r["scores_after"]))
                    for d in outcome["decisions"]:
                        assert d["decision_id"] not in expected_decisions and d["legal"] is True and d["fallback_reason"] is None
                        assert not any("action_value_failed" in x for x in d["degraded_reasons"])
                        expected_decisions[d["decision_id"]] = (mid,{k:d[k] for k in ("policy_id","action_key","seat","window_key","degraded_reasons")})
        observed, opportunity_rows, bypolicy = set(), [], Counter()
        cstats, degraded, unknown = Counter(), Counter(), Counter()
        max_trace_bytes = 0
        m3_reordered = []
        with gzip.open(_project_file(_PROJECT_ROOT, RAW / pool / "decisions.jsonl.gz"), "rt") as stream:
            for ordinal,line in enumerate(stream,1):
                row = decode(line)
                did,mid,perm = row["decision_id"],row["match_id"],tuple(row["permutation"])
                assert did not in observed and did in expected_decisions
                observed.add(did)
                emid,d = expected_decisions[did]
                assert emid == mid and d == {"policy_id":row["policy_id"],"action_key":row["selected_action_key"],"seat":row["seat"],"window_key":row["window_key"],"degraded_reasons":row["degraded_reasons"]}
                assert row["pool"] == pool and row["root_id"] in roots and perm in permutations
                assert row["focal_physical_seat"] == perm[0] and row["initial_dealer_physical"] == 0 and row["initial_dealer_logical"] == perm.index(0)
                assert results[mid]["policy_ids_by_seat"][row["seat"]] == row["policy_id"] and row["status"] == "chosen"
                assert row["seat"] == row["window_key"]["seat"] == row["observation"]["seat"] and mid == row["observation"]["game_id"] == row["window_key"]["game_id"]
                white = row["observation"]["my_hand"].count("白") + int(row["observation"]["drawn_tile"] == "白")
                assert white == row["white_count"]
                legal,candidates = row["legal_action_keys"],row["candidates"]
                keys,scores = [c["action_key"] for c in candidates],[c["score"] for c in candidates]
                assert len(legal) == len(set(legal)) == len(keys) == len(set(keys)) and set(legal) == set(keys)
                assert row["selected_action_key"] == keys[0] and [c["rank"] for c in candidates] == list(range(1,len(keys)+1))
                assert all(type(s) in (int,float) and math.isfinite(s) for s in scores)
                descending = scores == sorted(scores,reverse=True)
                promotion = row["policy_id"] == metadata["M3"]["policy_id"] and row["phase"] == "draw" and keys[0].startswith("discard:") and len(keys)>1 and keys[1]=="hu" and scores[1:] == sorted(scores[1:],reverse=True)
                response_pass_promotion = row["policy_id"] == metadata["M3"]["policy_id"] and row["phase"] in ("response_peng","response_chi") and row["observation"]["rule_state"]["baotou"] is True and keys[0]=="pass" and scores[1:]==sorted(scores[1:],reverse=True)
                assert descending or promotion or response_pass_promotion
                if not descending:m3_reordered.append(dict(decision_id=did,phase=row["phase"],selected_action_key=keys[0],legal_action_keys=legal,scores=scores,scope="declared_frozen_M3_strategy_selection_not_C"))
                assert row["action_families"] == sorted({k.split(":")[0] for k in legal})
                assert not any("action_value_failed" in r or "等胡升级失败" in r for r in row["degraded_reasons"])
                degraded.update(row["degraded_reasons"])
                ms = row["policy_compute_ms_observed"]
                assert type(ms) in (int,float) and math.isfinite(ms) and ms >= 0
                all_ms.append(ms)
                opfact = row["current_opportunity"]
                assert opfact["scope"] == "current_legal_hu_only" and opfact["future_qualification"] == "unknown"
                assert opfact["legal_hu"] == ("hu" in legal) and all(type(f) is int and f > 0 for f in opfact["immediate_fans"])
                bypolicy[row["policy_id"]] += 1
                opportunity_rows.append({k:row[k] for k in ("match_id","seat","policy_id","phase","white_count","action_families","current_opportunity","c_self_scored","status")})
                if row["policy_id"] in (aid,cid):
                    arm = "C" if row["policy_id"] == cid else "A"
                    coverage[arm][(pool,row["root_id"],perm,row["observation"]["round_no"])].append(dict(white_count=white,phase=row["phase"],current_legal_hu=opfact["legal_hu"],trigger_seq=row["window_key"]["trigger_seq"]))
                if row["policy_id"] == cid:
                    assert len(row["scoring_calls"]) == 1 and row["scoring_cumulative_failed_calls"] == 0
                    for call in row["scoring_calls"]:
                        assert call == row["scoring_execution"] and call["status"] == "SCORED" and call["actual_score_calls"] == 1 and call["score_completed"] is True
                        assert call["cumulative_failed_calls"] == 0 and call["full_legal_keys"] is True
                        rec = call["input_capture"]; key = rec["view_sha256"]; v = views[key]
                        assert rec["saved_before_score"] is True and rec["error"] is None and rec["status"] in ("stored","deduplicated")
                        assert type(rec["store_call_no"]) is int and rec["store_call_no"] not in capture_calls
                        capture_calls[rec["store_call_no"]] = dict(status=rec["status"], key=key)
                        capture_references[key] += 1; encoded_bytes[0] += rec["json_bytes"]
                        assert rec["json_bytes"] == v["json_bytes"]
                        visible = {k:row["observation"][k] for k in v["visible_state"]}
                        visible["melds"] = [[{k:m[k] for k in ("kind","tiles","from_seat")} for m in seat] for seat in row["observation"]["melds"]]
                        assert v["visible_state"] == visible
                        assert set(v["legal_action_keys"]) == set(legal) and set(call["scored_action_keys"]) == set(legal)
                        assert call["waiting_draw_witness_count"] == v["workload"]["waiting_draw_witness_count"]
                        assert call["target_distance_evaluation_count"] == v["workload"]["target_distance_evaluation_count"]
                    execution = row["scoring_execution"]
                    assert row["seat"] == perm[0] and row["c_self_scored"] is True and execution["status"] == "SCORED" and execution["full_legal_keys"] is True
                    assert set(execution["scored_action_keys"]) == set(legal) and len(execution["scored_action_keys"]) == len(legal)
                    ops = row["candidate_operations"]
                    assert type(ops) is int and 0 < ops <= 2400000 and descending
                    all_c_ops.append(ops);all_c_ms.append(ms)
                    cstats.update({"windows":1,"legal_scored_roots":len(keys),"white_"+str(white):1,"phase_"+row["phase"]:1})
                    unknown["windows_with_explicit_unknown_nodes"] += bool(execution["unknown_nodes"])
                    unknown["explicit_unknown_nodes"] += len(execution["unknown_nodes"])
                    for c in candidates:
                        trace = c["trace"]
                        assert trace["candidate_kind"] == "vip_route_heuristic_v1" and trace["trace_schema"] == "vip-route-score-trace/1"
                        assert trace["view_schema_version"] == "vip-route-scoring-view/2" and trace["normal_draw_hu_payment_semantics_version"] == "vip-normal-draw-hu-payment/1"
                        # 原答在大根表只给一个共用公式标签；不能强求每根重复，未改其评分。
                        if "f" in trace["detail"]: assert trace["detail"]["f"] == "vip_public_interruption_trade_m1/1"
                        elif len(keys) <= 64: raise AssertionError("小根表缺原答公式标签")
                        length = len(json.dumps(trace,ensure_ascii=False).encode());assert length <= 32768;max_trace_bytes=max(max_trace_bytes,length)
                    assert any(c["trace"]["detail"].get("f")=="vip_public_interruption_trade_m1/1" for c in candidates)
                    if opfact["legal_hu"]:
                        cstats["current_hu_windows"] += 1
                        cstats["current_hu_selected" if keys[0]=="hu" else "current_hu_continued"] += 1
                        all_current_hu.append(dict(pool=pool,root_id=row["root_id"],match_id=mid,round_no=row["observation"]["round_no"],selected_hu=keys[0]=="hu",immediate_fans=opfact["immediate_fans"]))
                else:assert row["c_self_scored"] is False
                if ordinal % 5000 == 0:print(json.dumps({"phase":"decision_stream","pool":pool,"read_windows":ordinal}),flush=True)
        assert observed == set(expected_decisions)
        opportunity = read(_project_file(_PROJECT_ROOT, RAW / pool / "current-opportunity-ledger.json"))
        assert opportunity_rows == opportunity["rows"] and len(observed) == opportunity["decision_window_denominator"]
        assert opportunity["focal_windows_by_arm"] == {"A":bypolicy[aid],"C":bypolicy[cid]}
        settlements = jsonl(_project_file(_PROJECT_ROOT, RAW / pool / "settlements.jsonl"))
        ledger = read(_project_file(_PROJECT_ROOT, RAW / pool / "natural-settlement-ledger.json"))
        assert settlements == ledger["rows"] and len(settlements) == 256
        bymatch, counts, hands, high = defaultdict(list),{a:Counter() for a in ("A","C")},{},[]
        for r in settlements:
            s,mid,perm = r["settlement"],r["match_id"],tuple(r["permutation"])
            bymatch[mid].append(r)
            assert r["evidence"] == "public_export_hand_settlement" and s["coverage"] == "settlement_only" and r["observation_scope"] == "completed_hand_only"
            assert r["pool"] == pool and r["root_id"] in roots and r["focal_physical_seat"] == perm[0]
            assert s["round_no"] == r["round_no"] and all(len(s[k])==4 for k in ("score_delta","scores_before","scores_after"))
            assert sum(s["score_delta"]) == 0 and all(s["scores_after"][i]-s["scores_before"][i] == s["score_delta"][i] for i in range(4))
            arm = "C" if mid.endswith(":"+cid) else "A"
            counts[arm]["observed_completed_hands"] += 1
            category = "draw" if s["is_draw"] else "other_seat_hu" if s["winner_seat"] != perm[0] else "self_ge8_hu" if s["fan"]>=8 else "self_ge4_hu" if s["fan"]>=4 else "self_ordinary_hu"
            counts[arm][category] += 1
            hands[(mid,r["round_no"])] = dict(category=category,fan=s["fan"],score_delta=s["score_delta"][perm[0]],root_id=r["root_id"],arm=arm)
            if s["fan"] is not None and s["fan"]>=4:high.append(dict(root_id=r["root_id"],permutation=list(perm),round_no=r["round_no"],arm=arm,focal_winner=s["winner_seat"]==perm[0],fan=s["fan"],focal_delta=s["score_delta"][perm[0]],details=s["details"]))
        assert set(bymatch) == set(results)
        for mid,rows in bymatch.items():
            assert [r["round_no"] for r in rows] == list(range(1,9))
            previous = [0]*4
            for r in rows:assert r["settlement"]["scores_before"] == previous;previous=r["settlement"]["scores_after"]
            assert previous == results[mid]["scores_after"]
        paired = [dict(root_id=root,permutation=list(perm),A=pairs[(root,perm)]["A"],C=pairs[(root,perm)]["C"],delta=pairs[(root,perm)]["C"]-pairs[(root,perm)]["A"]) for root in roots for perm in permutations]
        means = [dict(root_id=root,seat_deltas=[p["delta"] for p in paired if p["root_id"]==root],mean_delta=statistics.mean(p["delta"] for p in paired if p["root_id"]==root)) for root in roots]
        mean = statistics.mean(p["delta"] for p in paired)
        assert mean == summary["pools"][pool]["estimate_natural_score_delta"]
        pools[pool] = dict(table_instances=32,paired_tables=16,completed_hands=256,mean_delta=mean,roots=means,all_tables=tables,all_pairs=paired,
            settlement_categories={a:dict(c) for a,c in counts.items()},highfan_events=high,runtime_counts=dict(runtime),decisions=len(observed),C=dict(cstats),
            C_explicit_unknown=dict(unknown),max_trace_bytes=max_trace_bytes,degraded_reasons=dict(degraded),M3_declared_non_descending_selections=m3_reordered,current_hu_final_hand_outcomes=[{**h,"final":hands[(h["match_id"],h["round_no"])]} for h in all_current_hu if h["pool"]==pool])
        total_decisions += len(observed)
        print(json.dumps({"phase":"pool_closed","pool":pool,"tables":32,"decision_windows":len(observed),"C_windows":cstats["windows"]}),flush=True)
    assert set(capture_calls) == set(range(1, capture_stats["store_calls"]+1))
    assert set(capture_references) == set(views) and encoded_bytes[0] == capture_stats["encoded_complete_json_bytes"]
    seen = set(); stored = 0
    for n in sorted(capture_calls):
        rec = capture_calls[n]
        assert (rec["status"] == "stored") == (rec["key"] not in seen)
        stored += rec["status"] == "stored";seen.add(rec["key"])
    assert stored == len(views) == capture_stats["unique_views_saved"]
    root_means = [dict(root_id=root,H=pools["H"]["roots"][i]["mean_delta"],M=pools["M"]["roots"][i]["mean_delta"],combined=(pools["H"]["roots"][i]["mean_delta"]+pools["M"]["roots"][i]["mean_delta"])/2) for i,root in enumerate(roots)]
    coverage_output = {"schema":"t17-observation-only-white-coverage/1","source_raw_seal_sha256":PINS[str(RAW_SEAL)],"independent_mother_roots":4,
        "initial_hand_deal_claim":False,"definition":"focal PlayerObservation immediately before actual choose; first such observation in a hand is not asserted to be the initial deal",
        "no_actions_scores_settlements_or_effects_in_this_file":True,"arms":{}}
    for arm,items in coverage.items():
        rows=[]
        for (pool,root,perm,n),observations in sorted(items.items()):
            rows.append(dict(pool=pool,root_id=root,permutation=list(perm),round_no=n,windows=len(observations),white_windows=dict(Counter(str(o["white_count"]) for o in observations)),first_focal_pre_action_observation=observations[0]))
        strata=[]
        for white in range(5):
            hit=[(key,obs) for key,obs in items.items() if any(o["white_count"]==white for o in obs)]
            strata.append(dict(white_count=white,windows=sum(sum(o["white_count"]==white for o in obs) for obs in items.values()),unique_pool_table_hands=len(hit),unique_mother_roots=sorted({key[1] for key,obs in hit}),first_focal_observation_hands=sum(obs[0]["white_count"]==white for obs in items.values())))
        coverage_output["arms"][arm]={"trajectory":"frozen_R18" if arm=="A" else "candidate_dependent_C","rows":rows,"strata":strata}
    write("OBSERVATION-ONLY-WHITE-COVERAGE.json",coverage_output,verify)
    assert all(meta(p)==expected for p,expected in INPUTS.items())
    result = {"schema":"t17-natural-root-closure/1","accepted_engineering_chain":True,
        "raw_seal_sha256":PINS[str(RAW_SEAL)],"raw_member_count":sealed["file_count"],"raw_before_after_stable":True,"start_before_after_stable":True,"candidate_lineage":ancestry,
        "candidate_id":CID,"candidate_source_sha256":SOURCE,"tables":64,"paired_tables":32,"completed_hands":512,"independent_mother_roots":4,
        "pools":pools,"root_combined_means":root_means,"combined_mean_delta":statistics.mean(r["combined"] for r in root_means),
        "cluster_standard_error":statistics.stdev(r["combined"] for r in root_means)/math.sqrt(4),"positive_roots":sum(r["combined"]>0 for r in root_means),"negative_roots":sum(r["combined"]<0 for r in root_means),
        "complete_decision_windows":total_decisions,"C_operations":percentiles(all_c_ops),"C_policy_compute_ms_observed":percentiles(all_c_ms),"all_policy_compute_ms_observed":percentiles(all_ms),
        "current_Hu_windows_are_repeated_observations_not_independent_opportunities":True,"runtime_faults_all_zero":True,"charged_tables_no_refund":64,
        "actual_model_calls_in_natural_batch":0,"policy_compute_time_is_not_official_deadline_gate":True,
        "full_legal_scores_trace_execution_proof_saved":True,"every_C_window_actual_full_DTO_saved_before_score":True, "actual_full_DTO_capture":capture_stats,
        "public_full_graph_constructor_and_atomic_executor_guards_static_checked":True,
        "review_role":"root routine same-contract check, not new independent review","full_input_graph_closed_and_public_binding_checked":True, "rule_or_payment_math_reexecuted_by_checker":False,
        "no_producer_impersonation_no_posthoc_input_reconstruction":True,"development_only":True,"confirmation_or_strength_or_release_admission":False,
        "business_calls_by_this_review":dict(construct=0,score=0,rule=0,world=0,continuation=0,model=0,network=0),"production_or_original_evidence_modified":False}
    combined = [r["combined"] for r in root_means]
    se = statistics.stdev(combined) / math.sqrt(len(combined)); mean = statistics.mean(combined)
    result["descriptive_cluster_t95"] = [mean-3.182446305284264*se, mean+3.182446305284264*se]
    result["interval_scope"] = "4 independent mother roots; t approximation under finite-variance assumptions, heavy-tail development only, not confirmation or release"
    result["leave_one_root_out_means_sensitivity_only"] = [{"omitted_root":r["root_id"],"mean_delta":statistics.mean([t["combined"] for t in root_means if t["root_id"]!=r["root_id"]])} for r in root_means]
    write("AUDIT.json",result,verify)
    print(json.dumps({"audit_complete":True,"tables":64,"hands":512,"decisions":total_decisions,"combined_mean":result["combined_mean_delta"],"source_stable":True}),flush=True)


if __name__ == "__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify",action="store_true")
    main(parser.parse_args().verify)
