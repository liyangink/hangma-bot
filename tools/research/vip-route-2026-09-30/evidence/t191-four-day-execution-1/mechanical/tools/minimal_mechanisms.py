"""T191 小机制红绿执行；只使用已公开完整图，不推进世界或调用作者。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t191-four-day-execution-1/mechanical/tools'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
import argparse
import ctypes
import fcntl
import gzip
import hashlib
import json
import math
import os
import time
from dataclasses import fields, replace
from pathlib import Path

from hangma_bot.hangma.engine import HangmaRules
from hangma_bot.hangma.interface import Settlement
from hangma_bot.hangma.route_structure import RouteStructureFacts, RouteStructureTarget
from hangma_bot.hangma.natural_preparation import NaturalSetPreparationFacts
from hangma_bot.kernel.serialization import observation_from_json
from hangma_bot.policy.action_value_executor import ActionValueExecutor
from hangma_bot.policy.route_heuristic_view import (
    RouteConditionalHuPayment, RouteWaitingView, RouteHeuristicNode,
    RouteHeuristicAction, VipRouteScoringView,
)
from hangma_bot.offline.vip_eoh_generate import VipEohBatch

HERE = Path(__file__).resolve().parents[2]
EVIDENCE = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence')
MECH = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t191-four-day-execution-1/mechanical')
T185 = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t185-evidence-prioritized-joker-evolution-1')
T186 = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t186-incremental-opportunity-repair-1')
T187 = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t187-family-combination-evolution-1')
T188 = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t188-joint-score-mechanism-1')
T189 = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t189-online-issue-ledger-and-offer-diagnosis-1')


def canonical(value):
    """固定JSON字节；有限数检查供输入、输出与源码身份读回。"""
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
        separators=(",", ":"), allow_nan=False).encode()


def pin(path):
    """实际文件字节数与摘要，不继承旧候选成绩。"""
    raw = Path(path).read_bytes()
    return {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def save(path, value):
    """排他写证据；保留失败，不覆盖先前运行。"""
    with Path(path).open("x") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")


def tuples(value):
    """恢复公开缓存中冻结元组，映射仍由具体事实类型恢复。"""
    if isinstance(value, list):
        return tuple(tuples(v) for v in value)
    if isinstance(value, dict):
        return {k: tuples(v) for k, v in value.items()}
    return value


def construct(cls, value):
    """只传可初始化字段；派生常量必须与缓存原件一致。"""
    return cls(**{f.name: tuples(value[f.name]) for f in fields(cls) if f.init})


def typed(dto, case, batch):
    """将完整公开图恢复为正式typed视图，合法动作另向唯一规则源核验。

    没有重新展开条件图；恢复后candidate_view必须逐字节核同缓存。
    """
    obs = observation_from_json(case["observation"])
    analysis = HangmaRules(batch.rule_config).analyze(obs, route_limits=batch.route_limits)
    assert analysis.completeness.value == "complete"
    actions = {c.action_key: c.action for c in analysis.legal_candidates}
    assert set(actions) == {a["action_key"] for a in dto["actions"]}
    nodes = []
    for row in dto["nodes"]:
        data = tuples(row)
        if data["settlement"] is not None:
            data["settlement"] = construct(Settlement, row["settlement"])
        if data["waiting"] is not None:
            w = data["waiting"]
            s = w["structure"]
            s["targets"] = tuple(construct(RouteStructureTarget, t) for t in s["targets"])
            w["structure"] = construct(RouteStructureFacts, s)
            w["natural_preparation"] = construct(NaturalSetPreparationFacts, w["natural_preparation"])
            if w["normal_draw_hu_payments"] is not None:
                payments = []
                for p in w["normal_draw_hu_payments"]:
                    p["settlement"] = construct(Settlement, p["settlement"])
                    payments.append(construct(RouteConditionalHuPayment, p))
                w["normal_draw_hu_payments"] = tuple(payments)
            data["waiting"] = construct(RouteWaitingView, w)
        nodes.append(construct(RouteHeuristicNode, data))
    root_actions = tuple(RouteHeuristicAction(action=actions[a["action_key"]], **a)
                         for a in dto["actions"])
    view = VipRouteScoringView(schema_version=dto["schema_version"], visible_state=obs,
        actions=root_actions, nodes=tuple(nodes), **dto["binding"], **dto["limits"],
        waiting_draw_witness_count=dto["workload"]["waiting_draw_witness_count"],
        target_distance_evaluation_count=dto["workload"]["target_distance_evaluation_count"])
    assert canonical(view.candidate_view()) == canonical(dto)
    return view


def prepare():
    """事前保存三竞争解释、公开控制身份和小机制扰动；不读新成绩。"""
    MECH.mkdir(exist_ok=True)
    batch = VipEohBatch.read(_project_file(_PROJECT_ROOT, HERE / "EXECUTION-BATCH.json"))
    cases = json.loads((_project_file(_PROJECT_ROOT, T187 / "EXPLORATION-QUALIFICATION-PLAN.json")).read_text())["cases"]
    cases += json.loads((_project_file(_PROJECT_ROOT, T188 / "LATER-QUALIFICATION-CASES.json")).read_text())["cases"]
    causal = json.loads((_project_file(_PROJECT_ROOT, T185 / "CANDIDATE-CAUSAL-PLAN.json")).read_text())
    cases += [t["case"] for t in causal["targets"]]
    opportunity = json.loads((_project_file(_PROJECT_ROOT, T186 / "OPPORTUNITY-PROBE-PLAN-v2.json")).read_text())
    cases += [t["case"] for t in opportunity["targets"]]
    index = {c["label"]: c for c in cases}
    labels = json.loads((_project_file(_PROJECT_ROOT, T189 / "DIAGNOSTIC-PLAN.json")).read_text())["case_labels"]
    labels += ["supplement:004:05", "fresh:005:04", "closed-confirmation:060", "closed-confirmation:114"]
    assert len(labels) == len(set(labels)) == 28
    caches = [_project_file(_PROJECT_ROOT, T189 / "diagnostic/views.jsonl.gz"),
              _project_file(_PROJECT_ROOT, T185 / "AUTHOR-speed-model-output-qualification/views.jsonl.gz"),
              _project_file(_PROJECT_ROOT, T186 / "qualification/views.jsonl.gz")]
    views = {}
    for cache in caches:
        with gzip.open(cache, "rt") as stream:
            for line in stream:
                item = json.loads(line)
                if item.get("schema") == "vip-scoring-input-view/1":
                    dto = item["view"]
                    digest = hashlib.sha256(canonical(dto)).hexdigest()
                    assert digest == item["view_sha256"]
                    views[digest] = dto
    records = []
    for label in labels:
        case = index[label]
        digest = case.get("view_sha256", case.get("expected_view_sha256", case.get("expected_parent_view_sha256")))
        assert digest in views, (label, digest)
        records.append({"case": case, "view_sha256": digest, "view": views[digest]})
    save(_project_file(_PROJECT_ROOT, MECH / "PUBLIC-CONTROLS.json"), {"schema": "t191-public-mechanism-controls/1", "records": records})
    save(_project_file(_PROJECT_ROOT, MECH / "MECHANISM-PLAN.json"), {
        "schema": "t191-minimal-mechanism-plan/1", "batch_pin": pin(_project_file(_PROJECT_ROOT, HERE / "EXECUTION-BATCH.json")),
        "parent_pin": pin(_project_file(_PROJECT_ROOT, HERE / "parent-source.py")), "public_controls_pin": pin(_project_file(_PROJECT_ROOT, MECH / "PUBLIC-CONTROLS.json")),
        "actual_public_states_per_source": 28, "repeats_per_source": 2,
        "instrument_calls_per_source": 28, "synthetic_mechanism_states_per_source": 7,
        "planned_score_calls_per_source": 98,
        "competing_explanations": [
            {"id": "same_speed_union_unpaid", "prediction": "同最小向听联合支持缺失；补进两路线基础，目标max前已付，备用不得重复。", "discriminator": "固定目标和容量，纯普通支持与去重并集核齐；单一最快路线不变。"},
            {"id": "slow_route_backup_credit", "prediction": "较慢路线备用已付信用与同速联合缺失可独立共存。", "discriminator": "原1万较慢普通路线备用保留；只核两项增量，不把抹掉备用当同速修复。"},
            {"id": "target_scale_tradeoff", "prediction": "即使并集补齐，目标尺度取舍仍可能维持原选择。", "discriminator": "根分差与端点基础/目标/备用分别报，不要求固定全部历史首选。"}],
        "hard_checks": ["single_physical_code_dedup", "route_target_reorder_and_copy_cannot_increase_score",
            "exact_zero_stock_no_credit", "pure_ordinary_union_monotonic_only", "mature_base_carry_zero"],
        "positive_controls": ["supplement:004:05", "fresh:005:04", "closed-confirmation:060", "closed-confirmation:114"],
        "red_failure_expected": ["same_speed_union_paid", "mature_base_carry_zero"],
        "no_worlds_tables_models_http": True, "strength_or_deadline_admission": False,
        "cache_source_pins": {str(p): pin(p) for p in caches},
        "case_source_pins": {str(p): pin(p) for p in [_project_file(_PROJECT_ROOT, T187 / "EXPLORATION-QUALIFICATION-PLAN.json"), _project_file(_PROJECT_ROOT, T188 / "LATER-QUALIFICATION-CASES.json"), _project_file(_PROJECT_ROOT, T185 / "CANDIDATE-CAUSAL-PLAN.json"), _project_file(_PROJECT_ROOT, T186 / "OPPORTUNITY-PROBE-PLAN-v2.json"), _project_file(_PROJECT_ROOT, T189 / "DIAGNOSTIC-PLAN.json")]},
    })
    print(json.dumps({"prepared_public_states": len(records), "expected_red_mechanisms": 2}))


def instrument(source):
    """仅追加原端点解释；每根数值与非仪器trace须精确一致。"""
    needle = '            pairs.append(("prep", (facts[3][0], facts[3][1], facts[3][2], round(facts[3][3], 3))))'
    assert source.count(needle) == 1
    return source.replace(needle, needle + '''
            pairs.append(("diagnostic_routes", (facts[0], facts[1])))
            pairs.append(("diagnostic_target", facts[2]))
            pairs.append(("diagnostic_portfolio", facts[4]))
            pairs.append(("diagnostic_option", facts[12]))
            pairs.append(("diagnostic_offer", facts[11]))''')


def entries(answer):
    """完整合法根结果；同分按动作键排序与正式运行一致。"""
    assert answer.status == "SCORED"
    return sorted([{"action_key": e.action_key, "score": e.score, "trace": dict(e.trace)}
                   for e in answer.entries], key=lambda e: e["action_key"])


def pure_expected(dto, action_key):
    """原S02同一支持函数离线核算去重并集，单位排序点而非概率。"""
    root = next(a for a in dto["actions"] if a["action_key"] == action_key)
    w = next(n for n in dto["nodes"] if n["node_key"] == root["node_key"])["waiting"]
    s = w["structure"]
    lowest = min(s["standard_shanten"], s["seven_pairs_shanten"] if s["seven_pairs_shanten"] is not None else 999)
    codes = set(w["standard_useful_codes"] if s["standard_shanten"] == lowest else ())
    if s["seven_pairs_shanten"] == lowest:
        codes.update(w["seven_pairs_useful_codes"])
    mass = 0.0
    width = 0
    for code in codes:
        i = dto["tile_order"].index(code)
        cap, kind = w["unseen_capacities"][i], w["unseen_evidence"][i]
        stock = float(cap) if kind == "exact" or kind == "conservative" and cap is not None and cap > 0 else 0.75
        if stock > 0:
            mass += stock
            width += 1
    wall = dto["visible_state"]["remaining_tile_count"]
    scale = 0.70 if wall is None else float(wall > 20)
    support = scale * 4.8 * mass / (12.0 + mass) * width / (4.0 + width)
    return {"min_shanten": lowest, "support": support, "mass": mass, "width": width, "codes": sorted(codes)}


def synthetic(view):
    """固定原事实的计价变形，不作为规则金例或自然局面。"""
    action = next(a for a in view.actions if a.action_key == "discard:9b")
    i = next(i for i, n in enumerate(view.nodes) if n.node_key == action.node_key)
    w = view.nodes[i].waiting
    def changed(name, newwaiting):
        nodes = list(view.nodes)
        nodes[i] = replace(nodes[i], waiting=newwaiting)
        return name, replace(view, nodes=tuple(nodes))
    union = set(w.standard_useful_codes) | set(w.seven_pairs_useful_codes)
    available = [c for c, cap in zip(view.candidate_view()["tile_order"], w.unseen_capacities)
                 if c not in union and cap is not None and cap > 0]
    fresh = available[0]
    slot = view.candidate_view()["tile_order"].index(fresh)
    caps = list(w.unseen_capacities)
    caps[slot] = 0
    targets = w.structure.targets
    widths = w.target_improvement_code_widths
    return [
        changed("duplicate_route_codes", replace(w,
            standard_useful_codes=w.standard_useful_codes * 2,
            seven_pairs_useful_codes=w.seven_pairs_useful_codes * 2)),
        changed("reverse_route_codes", replace(w,
            standard_useful_codes=tuple(reversed(w.standard_useful_codes)),
            seven_pairs_useful_codes=tuple(reversed(w.seven_pairs_useful_codes)))),
        changed("copy_targets", replace(w, structure=replace(w.structure, targets=targets * 2),
            target_improvement_code_widths=widths * 2)),
        changed("reverse_targets", replace(w, structure=replace(w.structure, targets=tuple(reversed(targets))),
            target_improvement_code_widths=tuple(reversed(widths)))),
        changed("union_add_positive_code", replace(w, standard_useful_codes=w.standard_useful_codes + (fresh,))),
        changed("union_add_exact_zero_code", replace(w, standard_useful_codes=w.standard_useful_codes + (fresh,),
            unseen_capacities=tuple(caps))),
        changed("exchange_equal_speed_route_labels", replace(w,
            standard_useful_codes=w.seven_pairs_useful_codes,
            seven_pairs_useful_codes=w.standard_useful_codes)),
    ]


def run(name, source_path):
    """单进程真实受限评分，保留红/绿和仪器核同、操作数、完整分母。"""
    priority = {}
    try:
        priority["cpu_nice_actual"] = os.nice(15)
    except PermissionError as exc:
        priority["cpu_nice_failed"] = str(exc)
    priority["io_background_result"] = ctypes.CDLL(None).setiopolicy_np(0, 0, 3)
    resource_lock = (_project_file(_PROJECT_ROOT, EVIDENCE / "t182-step12-diagnosis-and-joint-evolution-1/.resource-scheduling-worker-0.lock")).open("r+")
    fcntl.flock(resource_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    batch = VipEohBatch.read(_project_file(_PROJECT_ROOT, HERE / "EXECUTION-BATCH.json"))
    plan = json.loads((_project_file(_PROJECT_ROOT, MECH / "MECHANISM-PLAN.json")).read_text())
    assert pin(_project_file(_PROJECT_ROOT, HERE / "EXECUTION-BATCH.json")) == plan["batch_pin"]
    assert pin(_project_file(_PROJECT_ROOT, HERE / "parent-source.py")) == plan["parent_pin"]
    assert pin(_project_file(_PROJECT_ROOT, MECH / "PUBLIC-CONTROLS.json")) == plan["public_controls_pin"]
    source = Path(source_path).read_text()
    instrument_source = instrument(source)
    out = _project_file(_PROJECT_ROOT, MECH / name)
    out.mkdir(exist_ok=False)
    (out / "instrument-source.py").write_text(instrument_source)
    executions = {
        "plain": ActionValueExecutor(source, max_operations=batch.max_operations,
            max_local_collection_size=batch.projection_limits.max_nodes),
        "instrument": ActionValueExecutor(instrument_source, max_operations=batch.max_operations,
            max_local_collection_size=batch.projection_limits.max_nodes)}
    save(out / "START.json", {"source_path": str(Path(source_path).resolve()), "source_pin": pin(source_path),
        "identity": batch.identity(source), "instrument_source_pin": pin(out / "instrument-source.py"),
        "plan_pin": pin(_project_file(_PROJECT_ROOT, MECH / "MECHANISM-PLAN.json")), "planned_score_calls": 98,
        "priority_actual": priority,
        "implementation_type": "frozen_parent" if name == "red-s02" else "human_implementation"})
    rows, calls, failure = [], 0, None
    started = time.monotonic()
    baseview = None
    baseentry = None
    try:
        with (out / "rows.jsonl").open("x") as stream:
            for item in json.loads((_project_file(_PROJECT_ROOT, MECH / "PUBLIC-CONTROLS.json")).read_text())["records"]:
                view = typed(item["view"], item["case"], batch)
                digest = item["view_sha256"]
                answers, operations = [], []
                for _ in range(2):
                    calls += 1
                    answers.append(entries(executions["plain"].score_vip_route(view)))
                    operations.append(executions["plain"].last_operation_count)
                assert canonical(answers[0]) == canonical(answers[1]) and operations[0] == operations[1]
                calls += 1
                detail = entries(executions["instrument"].score_vip_route(view))
                clean = [{**e, "trace": {k: v for k, v in e["trace"].items() if not k.startswith("diagnostic_")}}
                         for e in detail]
                assert canonical(clean) == canonical(answers[0])
                assert set(e["action_key"] for e in detail) == set(view.expected_action_keys())
                assert all(math.isfinite(e["score"]) for e in detail)
                assert hashlib.sha256(canonical(view.candidate_view())).hexdigest() == digest
                row = {"label": item["case"]["label"], "view_sha256": digest, "entries": detail,
                    "operations": operations, "instrument_operations": executions["instrument"].last_operation_count,
                    "preferred_action_key": sorted(detail, key=lambda e: (-e["score"], e["action_key"]))[0]["action_key"],
                    "complete_legal_roots": True, "deterministic": True, "instrument_scores_traces_exact": True,
                    "input_unchanged": True, "cache_rehydration_canonical_exact": True, "synthetic": False}
                rows.append(row)
                stream.write(canonical(row).decode() + "\n")
                stream.flush()
                if row["label"] == "anchor:early-one-white-route-speed":
                    baseview = view
                    baseentry = next(e for e in detail if e["action_key"] == "discard:9b")
            assert baseview is not None
            for label, view in synthetic(baseview):
                answers, operations = [], []
                before = canonical(view.candidate_view())
                for _ in range(2):
                    calls += 1
                    answers.append(entries(executions["instrument"].score_vip_route(view)))
                    operations.append(executions["instrument"].last_operation_count)
                assert canonical(answers[0]) == canonical(answers[1]) and operations[0] == operations[1]
                assert canonical(view.candidate_view()) == before
                e = next(e for e in answers[0] if e["action_key"] == "discard:9b")
                row = {"label": label, "synthetic": True, "entries": answers[0],
                    "operations": operations, "expected_pure": pure_expected(view.candidate_view(), "discard:9b"),
                    "original_root_score": baseentry["score"], "modified_root_score": e["score"],
                    "input_unchanged": True, "deterministic": True, "complete_legal_roots": True}
                rows.append(row)
                stream.write(canonical(row).decode() + "\n")
                stream.flush()
    except BaseException as exc:
        failure = {"type": type(exc).__name__, "message": str(exc), "completed_rows": len(rows)}
    save(out / "CLOSED.json", {"complete": failure is None and len(rows) == 35 and calls == 98,
        "failure": failure, "actual_score_calls": calls, "public_states": sum(not r["synthetic"] for r in rows),
        "synthetic_states": sum(r["synthetic"] for r in rows), "rows_pin": pin(out / "rows.jsonl"),
        "source_stable": pin(source_path) == json.loads((out / "START.json").read_text())["source_pin"],
        "elapsed_monotonic_seconds": time.monotonic() - started, "new_rules_analysis_calls": 28,
        "new_projection_calls": 0, "no_worlds_tables_models_http": True,
        "strength_or_original_deadline_admission": False})
    assert failure is None, failure
    summarize(name)
    resource_lock.close()
    print(json.dumps({"complete": True, "actual_score_calls": calls, "public_states": 28,
        "synthetic_states": 7, "elapsed_monotonic_seconds": time.monotonic() - started}))


def summarize(name):
    """端点机制与根选择分开；红结果是真实失败，不替换成预期值。"""
    out = _project_file(_PROJECT_ROOT, MECH / name)
    closed = json.loads((out / "CLOSED.json").read_text())
    assert closed["complete"]
    rows = list(map(json.loads, (out / "rows.jsonl").read_text().splitlines()))
    controls = {r["case"]["label"]: r["view"] for r in json.loads((_project_file(_PROJECT_ROOT, MECH / "PUBLIC-CONTROLS.json")).read_text())["records"]}
    opening = next(r for r in rows if r["label"] == "anchor:early-one-white-route-speed")
    speed = []
    for key in ("discard:1w", "discard:9b", "discard:中"):
        e = next(e for e in opening["entries"] if e["action_key"] == key)
        target = e["trace"]["diagnostic_target"]
        expected = pure_expected(controls[opening["label"]], key)
        routes = e["trace"]["diagnostic_routes"]
        actual_supports = [r[2] for r in routes if r is not None and r[0] == expected["min_shanten"]]
        speed.append({"action_key": key, "score": e["score"], "expected_pure": expected,
            "actual_min_shanten_supports": actual_supports,
            "same_speed_union_paid": all(v == expected["support"] for v in actual_supports),
            "target": target, "portfolio": e["trace"]["diagnostic_portfolio"]})
    waits = []
    for row in rows:
        if row["synthetic"] or not any(e["action_key"] == "hu" for e in row["entries"]):
            continue
        hu = next(e for e in row["entries"] if e["action_key"] == "hu")
        cont = sorted((e for e in row["entries"] if e["action_key"] != "hu"), key=lambda e: (-e["score"], e["action_key"]))[0]
        offer = cont["trace"].get("diagnostic_offer")
        dto = controls[row["label"]]
        root = next(a for a in dto["actions"] if a["action_key"] == cont["action_key"])
        node = next(n for n in dto["nodes"] if n["node_key"] == root["node_key"])
        settlement = next(n["settlement"] for n in dto["nodes"] if n["kind"] == "hu" and n["node_key"] == next(a["node_key"] for a in dto["actions"] if a["action_key"] == "hu"))
        w = node["waiting"]
        payments = None if w is None else w["normal_draw_hu_payments"]
        seat = dto["visible_state"]["seat"]
        routes = cont["trace"].get("diagnostic_routes")
        main = None if routes is None else max((r for r in routes if r is not None), key=lambda r: r[6])
        waits.append({"label": row["label"], "preferred_action_key": row["preferred_action_key"],
            "hu_score": hu["score"], "best_continue": cont["action_key"], "continue_score": cont["score"],
            "continue_minus_hu": cont["score"] - hu["score"], "current_certain_hu_settlement": settlement,
            "next_draw_fans": None if payments is None else sorted(set(p["settlement"]["fan"] for p in payments)),
            "next_draw_above_current_rows": None if payments is None else sum(p["settlement"]["score_delta"][seat] > settlement["score_delta"][seat] for p in payments),
            "main_route": main, "mature_base_carry_zero": None if offer is None or main[0] > 0 else offer[5] == 0.0,
            "offer_full": offer, "extra_natural_terminal_white_option": cont["trace"].get("diagnostic_option"),
            "selected_target": cont["trace"].get("diagnostic_target"), "not_single_action_strength_claim": True})
    origin = next(e for e in opening["entries"] if e["action_key"] == "discard:9b")
    tests = []
    original_pure = origin["trace"]["diagnostic_routes"][0][2]
    for row in rows:
        if not row["synthetic"]:
            continue
        e = next(e for e in row["entries"] if e["action_key"] == "discard:9b")
        pure = e["trace"]["diagnostic_routes"][0][2]
        if row["label"] in ("duplicate_route_codes", "reverse_route_codes", "copy_targets", "reverse_targets", "exchange_equal_speed_route_labels"):
            passed = e["score"] == origin["score"]
        elif row["label"] == "union_add_positive_code":
            passed = pure >= original_pure
        else:
            passed = pure == original_pure
        tests.append({"name": row["label"], "passed": passed, "scope": "pure_ordinary_support" if "union_add" in row["label"] else "root_total",
            "actual_pure_support": pure, "baseline_pure_support": original_pure,
            "expected_union_support": row["expected_pure"]["support"]})
    save(out / "MECHANISM-SUMMARY.json", {"complete": True, "speed_endpoints": speed,
        "opening_preferred": opening["preferred_action_key"], "hu_wait_controls": waits, "invariants": tests,
        "red_capable_checks": {"same_speed_union_paid": all(s["same_speed_union_paid"] for s in speed),
            "mature_base_carry_zero": all(w["mature_base_carry_zero"] for w in waits if w["mature_base_carry_zero"] is not None)},
        "offer_fields": ["net", "channel", "upgrade", "downside", "maintained", "carry", "exposure", "remote", "remote_anchor_price", "fallback", "offer_value"],
        "source_results_pin": pin(out / "rows.jsonl"), "strength_or_original_deadline_admission": False})


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("prepare", "run", "summarize"))
    parser.add_argument("--name")
    parser.add_argument("--source", type=Path)
    args = parser.parse_args()
    if args.mode == "prepare":
        prepare()
    elif args.mode == "run":
        run(args.name, args.source)
    else:
        summarize(args.name)
