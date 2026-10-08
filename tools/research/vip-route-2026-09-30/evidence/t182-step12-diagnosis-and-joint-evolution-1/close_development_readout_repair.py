"""T182 冻结开发读回的独立schema修复；原规则/统计/原件及旧模块globals不改。

只把生产正常V0的两条精确信息归为兼容审计，仍保留原文和计数；自动代理
和V0缺对象ID按真实装配类型核，PAIRING实际declaration身份另外独立验证。
"""
from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t182-step12-diagnosis-and-joint-evolution-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

import argparse
import copy
import ctypes
import fcntl
import gzip
import json
import os
import sys
from collections import Counter
from pathlib import Path

import close_development as dev
from close_development import (ACCOUNT_KEYS, BOOTSTRAP_REPLICATES, BOOTSTRAP_SEED,
    TableEvidence, account, comparisons, decode, frozen, integer, pin, preflight, read, require,
    seat_vector, sha256, validate_plan)
from hangma_bot.policy.action_value import CANDIDATE_KIND
from hangma_bot.policy.r18_integrated_positive_v2 import R18_INTEGRATED_POSITIVE_V2_NAME

HERE, ROOT, PLAN, OUTPUT = dev.HERE, dev.ROOT, dev.PLAN, dev.OUTPUT
CONTRACT = dev.CONTRACT
REPAIR_CONTRACT = _project_file(_PROJECT_ROOT, HERE / "DEVELOPMENT-READOUT-REPAIR-CONTRACT.md")
FAILURE = _project_file(_PROJECT_ROOT, HERE / "DEVELOPMENT-FIRST-INPUT-CHECK-FAILED.json")
VALIDATION = _project_file(_PROJECT_ROOT, HERE / "DEVELOPMENT-READOUT-REPAIR-VALIDATION.json")
LEGACY_INFORMATION = "评分兼容视图[legacy-pass-neutral-v1]：可信过牌恢复旧中性基线；原始规则事实不改写"
CATCH_INFORMATION = "抓打圈生效：排序仅在规则允许的硬约束候选内进行"
NORMAL_INFORMATION = frozenset((LEGACY_INFORMATION, CATCH_INFORMATION))
R18_DYNAMIC_ID = CANDIDATE_KIND + ":" + R18_INTEGRATED_POSITIVE_V2_NAME
KNOWN_TYPES = ("automatic_like", "normal_v0", "r18")


def decision_metadata(table, closure, plan):
    """焦点严格无降级；对手只按冻结物理对应类型接受精确信息和对象ID格式。"""
    seat, root = table.rotation, plan["roots"][table.index - 1]
    arm = [plan["parent"], *plan["candidates"]][table.arm_index]
    pairing, pairing_pin = read(table.directory / "PAIRING-IDENTITY.json")
    require(pairing_pin == table.pairing_pin == closure.get("pairing_identity_pin") and
            pairing.get("root") == root and pairing.get("rotation") == seat and pairing.get("arm") == arm and
            pairing.get("evidence") == "本次运行实际从policies_by_id选取并传入drive_match的映射；焦点席位为None",
            "实际PAIRING原件/来源/臂/换座不符")
    actual_ids = pairing.get("opponent_policy_ids_physical")
    kinds = root.get("opponent_types_logical_1_2_3")
    require(type(kinds) is list and len(kinds) == 3 and all(k in KNOWN_TYPES for k in kinds), "未知对手装配类型")
    require(type(actual_ids) is list and len(actual_ids) == 4 and actual_ids[seat] is None and
            actual_ids == closure.get("opponent_policy_ids_physical"), "实际三对手物理映射不符")
    for logical, kind in enumerate(kinds, 1):
        declaration = actual_ids[(logical + seat) % 4]
        prefix = f"H{logical}:" if kind == "r18" else f"Q{logical}:{kind}:"
        require(type(declaration) is str and declaration.startswith(prefix), "实际对手declaration类型/逻辑座位不符")
        sha256(declaration[len(prefix):], "实际对手declaration摘要")
    focal, opponent_ids, all_ids = {}, {}, set()
    notes = {k: Counter() for k in KNOWN_TYPES}
    missing, totals, diagnostic_decisions = Counter(), Counter(), Counter()
    for d in closure["outcome"]["decisions"]:
        decision_id = d["decision_id"]
        require(type(decision_id) is str and decision_id and decision_id not in all_ids, "驱动决策标识空或重复")
        all_ids.add(decision_id)
        require(d.get("legal") is True and d.get("fallback_reason") is None, "原动作非法或发生回退")
        other = integer(d.get("seat"), "驱动座位", 0)
        require(other < 4 and type(d.get("window_key")) is dict and d["window_key"].get("seat") == other,
                "驱动窗口座位不符")
        reasons = d.get("degraded_reasons")
        require(type(reasons) is list and all(type(r) is str for r in reasons), "驱动诊断字段未知")
        if other == seat:
            require(reasons == [], "焦点含降级或信息诊断，拒绝")
            require(d.get("policy_id") == "vip:" + arm["identity"]["candidate_id"], "驱动焦点策略身份不符")
            focal[decision_id] = d
        else:
            logical = (other - seat) % 4
            kind, dynamic = kinds[logical - 1], d.get("policy_id")
            totals[kind] += 1
            if kind == "normal_v0":
                require(dynamic is None, "冻结正常V0不应伪造对象policy_id")
                require(len(reasons) == len(set(reasons)) and set(reasons) <= NORMAL_INFORMATION,
                        "正常V0含未知/重复诊断或真正降级")
            elif kind == "automatic_like":
                require(dynamic is None and reasons == [], "冻结自动对手对象ID/诊断不符")
            else:
                require(dynamic == R18_DYNAMIC_ID and reasons == [], "R18动态对象ID未知/缺失或含降级")
            if dynamic is None:
                missing[kind] += 1
            if reasons:
                diagnostic_decisions[kind] += 1
                notes[kind].update(reasons)
            opponent_ids.setdefault(logical, set()).add(dynamic)
    audit = {"opponent_decisions_by_type": {k: totals[k] for k in KNOWN_TYPES},
             "opponent_compatibility_diagnostic_decisions_by_type": {k: diagnostic_decisions[k] for k in KNOWN_TYPES},
             "opponent_compatibility_diagnostic_counts_by_type": {k: dict(sorted(notes[k].items())) for k in KNOWN_TYPES},
             "opponent_object_policy_id_missing_counts_by_type": {k: missing[k] for k in KNOWN_TYPES},
             "opponent_pairing_declaration_ids_logical_1_2_3": {str(i): actual_ids[(i + seat) % 4] for i in range(1, 4)},
             "actual_pairing_mapping_independently_verified": True,
             "focal_diagnostic_count": 0, "unknown_diagnostic_count": 0,
             "schema_repair_only_no_original_record_rewritten": True}
    return focal, opponent_ids, audit


def input_receipt_fields(receipt, number, limit):
    """原评分前输入收据严格检查；负例复用这个真实调用接缝，无新输入保存。"""
    require(type(receipt) is dict and receipt.get("store_call_no") == number and
            receipt.get("saved_before_score") is True and receipt.get("error") is None, "评分前输入未真实保存")
    sha, size = receipt.get("view_sha256"), integer(receipt.get("json_bytes"), "输入字节数", 1)
    sha256(sha, "输入视图")
    require(size <= limit, "输入字节数超限")
    return sha, size


def frozen_repair():
    """实际失败、1686收据验证与负例都必须绑定；不是仅凭新文件存在放行。"""
    validation, validation_pin = read(VALIDATION)
    require(validation.get("schema") == "t182-development-readout-repair-validation/1" and
            validation.get("success") is True and validation.get("source_stable") is True and
            validation.get("actual_focal_score_receipts_checked") == 1686 and
            validation.get("actual_complete_tables_receipt_checked") == 4 and
            validation.get("actual_completed_tables_metadata_checked") == 14 and
            validation.get("all_required_negative_checks_passed") is True and
            validation.get("original_statistical_function_identity_unchanged") is True and
            validation.get("selection_ast_unchanged") is True and validation.get("scores_extracted") is False,
            "修复尚未经真实收据/负例/原统计身份验证")
    files = dict(validation["files"])
    files[str(VALIDATION)] = validation_pin
    require(all(str(p) in files for p in (Path(__file__).resolve(), REPAIR_CONTRACT, FAILURE, PLAN, Path(dev.__file__).resolve())),
            "修复未绑定源码/合同/实际失败/原计划")
    for path, expected in files.items():
        require(pin(Path(path)) == expected, "修复验证原件漂移:" + path)
    return files


def aggregate_audits(audits):
    """汇总真实信息诊断/对象ID缺失笔数；不读取积分或合并未知诊断。"""
    simple = ("opponent_decisions_by_type", "opponent_compatibility_diagnostic_decisions_by_type",
              "opponent_object_policy_id_missing_counts_by_type")
    result = {key: {kind: 0 for kind in KNOWN_TYPES} for key in simple}
    notes = {kind: Counter() for kind in KNOWN_TYPES}
    for audit in audits:
        for key in simple:
            for kind in KNOWN_TYPES:
                result[key][kind] += integer(audit[key][kind], key, 0)
        for kind in KNOWN_TYPES:
            notes[kind].update(audit["opponent_compatibility_diagnostic_counts_by_type"][kind])
    result["opponent_compatibility_diagnostic_counts_by_type"] = {k: dict(sorted(notes[k].items())) for k in KNOWN_TYPES}
    return result


def statistical_identity():
    """只比较原函数对象和选择AST；不运行account、bootstrap或开发比较。"""
    import ast
    require(account is dev.account and comparisons is dev.comparisons, "原统计函数对象被替换")
    old = ast.parse(Path(dev.__file__).read_bytes())
    new = ast.parse(Path(__file__).read_bytes())
    def selection(tree):
        function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_readout")
        return [ast.dump(n, include_attributes=False) for n in function.body if isinstance(n, ast.Assign) and
                any(isinstance(t, ast.Name) and t.id in ("eligible", "selected") for t in n.targets)]
    require(len(selection(old)) == 2 and selection(old) == selection(new), "开发预登记选择AST改变")
    require(dev.comparisons.__globals__["bootstrap_interval"] is dev.bootstrap_interval,
            "原比较函数不再使用原bootstrap")
    return True


def score_receipts(table, closure, plan):
    """从评分gzip核实际次数、输入小收据和最终实际动作；不重评分/重构输入。"""
    seat, root = table.rotation, plan["roots"][table.index - 1]
    arm = [plan["parent"], *plan["candidates"]][table.arm_index]
    outcome = closure["outcome"]
    focal, opponent_ids, diagnostics = decision_metadata(table, closure, plan)
    seen, views, stored, repeated, byte_total, operations = set(), {}, 0, 0, 0, []
    decision_path = table.directory / "focal-decisions.jsonl.gz"
    limit = plan["capture_limits"]["max_view_json_bytes"]
    with gzip.open(decision_path, "rb") as stream:
        while raw := stream.readline(limit + 513):
            byte_total += len(raw)
            require(len(raw) <= limit + 512 and byte_total <= 2 * plan["capture_limits"]["max_total_json_bytes"],
                    "评分小收据超预登记读取上界")
            row = decode(raw)
            did = row["decision_id"]
            require(did not in seen and did in focal, "评分决策重复或不在实际动作中")
            seen.add(did)
            require(row.get("root_id") == root["root_id"] and row.get("rotation") == seat and
                    row.get("arm") == table.arm_index and row.get("source_identity") == arm["identity"]["candidate_id"] and
                    row.get("seat") == seat and row.get("focal_vip") is True and
                    row.get("policy_id") == focal[did]["policy_id"] and row.get("window_key") == focal[did]["window_key"],
                    "评分收据来源/窗口/策略身份不符")
            require(row.get("status") == "chosen" and row.get("c_self_scored") is True and
                    row.get("degraded_reasons") == [] and row.get("scoring_cumulative_failed_calls") == 0 and
                    row.get("selected_action_key") == focal[did]["action_key"], "评分失败/降级或实际动作不符")
            calls = row.get("scoring_calls")
            require(type(calls) is list and len(calls) == 1, "每窗实际评分不是恰一次")
            call = calls[0]
            number = len(seen)
            require(call.get("call_no") == number and call.get("status") == "SCORED" and
                    call.get("actual_score_calls") == 1 and call.get("score_completed") is True and
                    call.get("full_legal_keys") is True and call.get("cumulative_failed_calls") == 0,
                    "实际评分次数/完整性不符")
            op = integer(call.get("candidate_operations"), "实际操作数", 1)
            require(op <= arm["identity"]["params"]["max_operations"], "评分超工作量")
            operations.append(op)
            legal, scored = row["legal_action_keys"], call["scored_action_keys"]
            require(len(legal) == len(set(legal)) == len(scored) == len(set(scored)) and set(legal) == set(scored),
                    "评分合法根集合不完整")
            receipt = call["input_capture"]
            sha, size = input_receipt_fields(receipt, number, limit)
            if sha in views:
                require(receipt.get("status") == "deduplicated" and views[sha] == size, "输入去重收据矛盾")
                repeated += 1
            else:
                require(receipt.get("status") == "stored", "首份输入未保存")
                views[sha] = size
                stored += 1
    count = len(seen)
    require(seen == set(focal) and count == closure["actual_focal_decisions"] == closure["actual_focal_score_calls"],
            "实际动作/焦点决策/评分次数分母不一致")
    capture, terminal = closure["capture"], closure["capture"]["terminal"]
    require(capture.get("store_calls") == count and capture.get("unique_views_saved") == stored and
            capture.get("deduplicated_calls") == repeated and capture.get("failed_store_calls") == 0 and
            capture.get("gzip_write_result_uncertain_attempts") == 0 and terminal.get("verified_unique_views") == stored and
            capture.get("unique_json_bytes_saved") == sum(views.values()), "输入捕获计数/字节数未对账")
    views_path = table.directory / "views.jsonl.gz"
    capture_pin = pin(views_path)
    require(capture_pin["sha256"] == terminal.get("compressed_sha256") and
            capture_pin["bytes"] == terminal.get("observed_compressed_bytes"), "原输入压缩文件与核验终态不一致")
    require(stored <= plan["capture_limits"]["max_unique_views"] and
            sum(views.values()) <= plan["capture_limits"]["max_total_json_bytes"], "输入捕获超限")
    return {**diagnostics, "decisions": count, "actual_score_calls": count, "unique_views": stored,
            "maximum_operations": max(operations),
            "opponent_policy_ids_logical_1_2_3": {str(i): sorted(opponent_ids.get(i, set()), key=lambda v: "" if v is None else v)
                                                      for i in range(1, 4)},
            "opponent_actual_identity_independently_exported": all(
                opponent_ids.get(i) and None not in opponent_ids[i] for i in range(1, 4))}, {
                str(decision_path): pin(decision_path), str(views_path): capture_pin}

def _readout(preflight_only=False):
    """全批核完才唯一新建DEVELOPMENT-CLOSED；不完整/失真时退出且不写成绩。"""
    require(not OUTPUT.exists(), "开发闭合已存在，拒绝覆盖或重复查看")
    plan, plan_pin = read(PLAN)
    validate_plan(plan)
    frozen(plan)
    repair_files = frozen_repair()
    evidence = preflight(plan, plan_pin)
    require(pin(PLAN) == plan_pin, "预检期间原计划漂移")
    if preflight_only:
        print(json.dumps({"status": "all_original_terminals_ready_no_score_readout", "planned_tables": len(evidence),
                          "scores_extracted": False, "confirmation_admission": False}, ensure_ascii=False))
        return
    files = {**repair_files, str(PLAN): plan_pin, str(Path(__file__).resolve()): pin(Path(__file__).resolve()), str(CONTRACT): pin(CONTRACT)}
    tables = {}
    for table in evidence:
        start_path, closure_path = table.directory / "START.json", table.directory / "CLOSURE.json"
        pairing_path = table.directory / "PAIRING-IDENTITY.json"
        require(pin(start_path) == table.start_pin, "全批预检后START漂移")
        closure, current_pin = read(closure_path)
        require(current_pin == table.closure_pin, "全批预检后CLOSURE漂移")
        require(pin(pairing_path) == table.pairing_pin, "全批预检后实际配对映射漂移")
        files.update({str(start_path): table.start_pin, str(closure_path): table.closure_pin, str(pairing_path): table.pairing_pin})
        root = plan["roots"][table.index - 1]
        ledger, end = account(closure["settlements"], table.rotation, root["root_id"])
        require(all(proof["dealer_seat"] == exported["settlement"]["dealer_seat"]
                    for proof, exported in zip(closure["pairing_proofs"], closure["settlements"])),
                "公开实际起手庄家与结算庄家不同")
        require(end == seat_vector(closure["outcome"].get("final_scores"), "桌终分") and ledger["net"] == end[table.rotation],
                "八局结算与四座桌终分不一致")
        audit, pins = score_receipts(table, closure, plan)
        files.update(pins)
        tables[(table.index, table.rotation, table.arm_index)] = {
            "root_id": root["root_id"], "rotation": table.rotation, "arm_index": table.arm_index,
            "account": ledger, "audit": audit, "final_scores_0_1_2_3": end,
            "pairing_proofs": closure["pairing_proofs"],
            "pairing": {"root_id": root["root_id"], "seed": root["seed"], "initial_dealer_physical": 0,
                "initial_scores_0_1_2_3": [0, 0, 0, 0], "rounds": 8,
                "opponent_types_logical_1_2_3": root["opponent_types_logical_1_2_3"],
                "opponent_policy_ids_physical": closure["opponent_policy_ids_physical"],
                "logical_to_physical_0_1_2_3": [(i + table.rotation) % 4 for i in range(4)]}}
    candidates = comparisons(plan, tables)
    eligible = sorted((r for r in candidates if r["development_selection_eligible"]),
                      key=lambda r: (-r["net_delta_sum_128_tables"], r["candidate_id"]))
    selected = None if not eligible else eligible[0]["candidate_id"]
    frozen(plan)
    require(all(pin(Path(path)) == expected for path, expected in files.items()), "读回期间原件漂移")
    result = {"schema": "t182-natural-development-closed/1", "complete": True,
        "status": "development_complete_not_confirmed", "files": files, "source_stable": True,
        "readout_schema_repair": "production_opponent_diagnostics_and_object_ids_only_v1",
        "readout_repair_audit_counts": aggregate_audits([t["audit"] for t in tables.values()]),
        "repair_contract_pin": pin(REPAIR_CONTRACT), "original_readout_error_evidence_pin": pin(FAILURE),
        "source_kind": "simulation", "parent_identity": plan["parent"]["identity"],
        "planned_table_instances": plan["planned_table_instances"], "actual_table_instances": len(tables),
        "completed_hand_instances": len(tables) * 8, "independent_mother_sources": 32,
        "actual_focal_decisions": sum(t["audit"]["decisions"] for t in tables.values()),
        "actual_focal_score_calls": sum(t["audit"]["actual_score_calls"] for t in tables.values()),
        "tables": list(tables.values()), "candidates": candidates,
        "selected_candidate_id_for_confirmation_preparation": selected,
        "selection_is_development_screen_only": True,
        "bootstrap": {"seed": BOOTSTRAP_SEED, "replicates": BOOTSTRAP_REPLICATES,
            "unit": "32_mother_sources_each_four_seat_mean", "interval": "percentile_linear_0.025_0.975",
            "shared_resampling_indices_across_candidates": True, "formal_strength_claim": False},
        "pairing_evidence": "public_export_initial_exact_frozen_sampler_all_eight_physical_wall_hashes_and_actual_policy_mapping",
        "physical_wall_digest_public_export_verified": True,
        "actual_opponent_mapping_verified": True,
        "outcome_opponent_policy_id_coverage": all(
            t["audit"]["opponent_actual_identity_independently_exported"] for t in tables.values()),
        "deadline_admission": False, "confirmation_admission": False, "strength_admission": False,
        "release_admission": False, "new_models_scores_worlds_tables": 0}
    payload = json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n"
    with OUTPUT.open("x", encoding="utf-8") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    print(json.dumps({"complete": True, "output": str(OUTPUT), "selected_candidate_id": selected,
                      "development_only": True, "strength_admission": False}, ensure_ascii=False))

def main(preflight_only=False, receipt_precheck=False):
    """nice至少15、macOS后台IO及共用独占锁下读回；只等待赛后锁，不操作续赛。"""
    require(sys.platform == "darwin", "本批读回须使用已冻结的macOS后台IO环境")
    priority = os.getpriority(os.PRIO_PROCESS, 0)
    if priority < 15:
        os.nice(15 - priority)
    require(os.getpriority(os.PRIO_PROCESS, 0) >= 15, "读回CPU优先级未降到nice15")
    io_policy = ctypes.CDLL(None, use_errno=True).setiopolicy_np
    io_policy.argtypes, io_policy.restype = [ctypes.c_int, ctypes.c_int, ctypes.c_int], ctypes.c_int
    require(io_policy(0, 0, 3) == 0, "读回未获得macOS后台IO策略")
    lock_path = _project_file(_PROJECT_ROOT, ROOT / ".private/t165-live-watchdog/postprocess.lock")
    with lock_path.open("a+") as lock:
        print(json.dumps({"state": "waiting_postprocess_lock", "scores_extracted": False,
                          "nice_at_least": 15, "background_io": True}, ensure_ascii=False), flush=True)
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            return receipt_precheck_existing() if receipt_precheck else _readout(preflight_only)
        finally:
            primary = sys.exc_info()[1]
            try:
                fcntl.flock(lock, fcntl.LOCK_UN)
            except BaseException as secondary:
                if primary is None:
                    raise
                primary.add_note("读回释放赛后锁再次失败:" + type(secondary).__name__ + ": " + str(secondary))


def receipt_precheck_existing():
    """核首来源四臂1686原评分收据和全部14桌诊断；不提取结算/候选分值或重评分。"""
    require(not VALIDATION.exists(), "修复验证原件已存在，拒绝覆盖")
    plan, plan_pin = read(PLAN)
    validate_plan(plan)
    frozen(plan)
    failure, failure_pin = read(FAILURE)
    require(failure.get("schema") == "t182-first-actual-input-check-failure/1" and failure.get("actual_exit_code") == 1 and
            failure.get("tool_session") == 36756 and failure.get("actual_error_message") == "原动作非法或含降级" and
            failure.get("original_plan_pin") == plan_pin and failure.get("original_readout_pin") == pin(Path(dev.__file__)) and
            failure.get("outcome_points_extracted") is False and failure.get("old_evidence_retained") is True,
            "原实际失败原件不符")
    handoff_path = _project_file(_PROJECT_ROOT, HERE / "RESOURCE-OLD-RUNNER-HANDOFF.json")
    handoff, handoff_pin = read(handoff_path)
    require(handoff.get("all_started_tables_completed") is True and handoff.get("open_tables") == 0 and
            handoff.get("scores_extracted") is False and len(handoff.get("completed_tables", [])) == 14,
            "未绑定14桌实际交接")
    files = {str(PLAN): plan_pin, str(Path(dev.__file__).resolve()): pin(Path(dev.__file__)),
             str(Path(__file__).resolve()): pin(Path(__file__)), str(REPAIR_CONTRACT): pin(REPAIR_CONTRACT),
             str(_project_file(_PROJECT_ROOT, HERE / "run_development.py")): pin(_project_file(_PROJECT_ROOT, HERE / "run_development.py")),
             str(FAILURE): failure_pin, str(handoff_path): handoff_pin}
    metadata_audits, tables, closures = [], {}, {}
    for relative in handoff["completed_tables"]:
        directory = _project_file(_PROJECT_ROOT, HERE / relative)
        start, sp = read(directory / "START.json")
        closure, cp = read(directory / "CLOSURE.json")
        pairing, pp = read(directory / "PAIRING-IDENTITY.json")
        require(handoff["files"].get(str(directory / "START.json")) == sp and
                handoff["files"].get(str(directory / "CLOSURE.json")) == cp and start.get("plan_pin") == plan_pin,
                "实际交接元数据漂移")
        require(closure.get("complete") is True and closure.get("source_stable") is True and closure.get("failure") is None and
                closure["outcome"].get("status") == "complete" and closure["outcome"].get("completed_hands") == 8 and
                set(closure["outcome"]["runtime_counts"]) == dev.RUNTIME_KEYS and
                all(type(v) is int and v == 0 for v in closure["outcome"]["runtime_counts"].values()) and
                all(closure["capture"]["terminal"].get(k) is True for k in
                    ("terminal_valid", "closed", "verified", "store_calls_reconciled")), "实际14桌终态不完整")
        index = next(i for i, root in enumerate(plan["roots"], 1) if root == closure["root"])
        arm_index = next(i for i, arm in enumerate([plan["parent"], *plan["candidates"]]) if arm == closure["arm"])
        table = TableEvidence(index, closure["rotation"], arm_index, directory, sp, cp, pp)
        focal, _, diagnostics = decision_metadata(table, closure, plan)
        require(start.get("root") == closure["root"] and start.get("rotation") == table.rotation and start.get("arm") == closure["arm"],
                "原START/CLOSURE身份不符")
        metadata_audits.append(diagnostics)
        files.update({str(directory / "START.json"): sp, str(directory / "CLOSURE.json"): cp,
                      str(directory / "PAIRING-IDENTITY.json"): pp})
        tables[(index, table.rotation, arm_index)] = table
        closures[(index, table.rotation, arm_index)] = closure
    full_audits = []
    for arm_index in range(4):
        key = (1, 0, arm_index)
        audit, raw_pins = score_receipts(tables[key], closures[key], plan)
        full_audits.append(audit)
        files.update(raw_pins)
    actual_count = sum(a["actual_score_calls"] for a in full_audits)
    require(actual_count == 1686 and [a["actual_score_calls"] for a in full_audits] == [444, 481, 357, 404],
            "首来源四臂真实收据分母改变")
    first_table, first_closure = tables[(1, 0, 0)], closures[(1, 0, 0)]
    reproduced = False
    try:
        dev.score_receipts(first_table, first_closure, plan)
    except ValueError as error:
        reproduced = str(error) == "原动作非法或含降级"
    require(reproduced, "原函数实际失败未复现，不能证明本修复边界")
    focal_decision = next(d for d in first_closure["outcome"]["decisions"] if d["seat"] == 0)
    normal_decision = next(d for d in first_closure["outcome"]["decisions"] if d["seat"] == 2)
    automatic_decision = next(d for d in first_closure["outcome"]["decisions"] if d["seat"] == 1)
    negative = {}
    def rejected(name, operation):
        try:
            operation()
        except (ValueError, KeyError, TypeError) as error:
            negative[name] = {"rejected": True, "error_type": type(error).__name__, "reason": str(error)}
        else:
            raise ValueError("要求的负例被错误接受:" + name)
    def altered_decision(original, **changes):
        decision = copy.deepcopy(original)
        decision.update(changes)
        closure = {**first_closure, "outcome": {**first_closure["outcome"], "decisions": [decision]}}
        return lambda: decision_metadata(first_table, closure, plan)
    rejected("unknown_normal_reason", altered_decision(normal_decision, degraded_reasons=["UNKNOWN_DIAGNOSTIC_NEGATIVE_CHECK"]))
    rejected("focal_reason_even_known", altered_decision(focal_decision, degraded_reasons=[LEGACY_INFORMATION]))
    rejected("illegal_action", altered_decision(normal_decision, legal=False))
    rejected("fallback_action", altered_decision(normal_decision, fallback_reason="timeout"))
    rejected("automatic_reason", altered_decision(automatic_decision, degraded_reasons=[LEGACY_INFORMATION]))
    rejected("unknown_object_id", altered_decision(normal_decision, policy_id="unknown-policy-negative-check"))
    with gzip.open(first_table.directory / "focal-decisions.jsonl.gz", "rb") as stream:
        actual_row = decode(stream.readline(plan["capture_limits"]["max_view_json_bytes"] + 513))
    actual_receipt = actual_row["scoring_calls"][0]["input_capture"]
    incomplete = {**actual_receipt, "saved_before_score": False}
    rejected("input_not_saved_before_score", lambda: input_receipt_fields(incomplete, 1, plan["capture_limits"]["max_view_json_bytes"]))
    missing_hash = {**actual_receipt, "view_sha256": None}
    rejected("input_missing_hash", lambda: input_receipt_fields(missing_hash, 1, plan["capture_limits"]["max_view_json_bytes"]))
    statistical_identity()
    frozen(plan)
    require(all(pin(Path(p)) == h for p, h in files.items()), "实际验证期间原件/修复源码漂移")
    result = {"schema": "t182-development-readout-repair-validation/1", "success": True, "source_stable": True,
              "files": files, "source_manifest": plan["source_manifest"], "original_failure_pin": failure_pin,
              "actual_focal_score_receipts_checked": actual_count, "actual_complete_tables_receipt_checked": 4,
              "actual_completed_tables_metadata_checked": 14, "first_source_four_arm_audits": full_audits,
              "all_14_metadata_audit_counts": aggregate_audits(metadata_audits),
              "original_readout_misclassification_reproduced": True,
              "negative_checks": negative, "all_required_negative_checks_passed": True,
              "negative_cases_use_in_memory_copies_of_actual_records_only": True,
              "original_statistical_function_identity_unchanged": True, "selection_ast_unchanged": True,
              "scores_extracted": False, "original_frozen_source_modified": False,
              "new_models_worlds_tables_scores": 0, "deadline_admission": False,
              "confirmation_admission": False, "strength_admission": False, "release_admission": False}
    with VALIDATION.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    print(json.dumps({"success": True, "actual_score_receipts_checked": actual_count, "tables": 4,
                      "metadata_tables": 14, "negative_checks_rejected": len(negative),
                      "scores_extracted": False, "output": str(VALIDATION)}, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    options = parser.add_mutually_exclusive_group()
    options.add_argument("--preflight-only", action="store_true")
    options.add_argument("--receipt-precheck-first-source", action="store_true",
                         help="仅核既有首来源四臂收据和14桌元数据，不读积分、不计算开发统计")
    args = parser.parse_args()
    try:
        main(args.preflight_only, args.receipt_precheck_first_source)
    except (OSError, ValueError, RuntimeError, KeyError, TypeError, IndexError, AttributeError, OverflowError) as error:
        print(json.dumps({"complete": False, "status": "unknown_or_invalid_repair_readout", "error_type": type(error).__name__,
                          "reason": str(error), "original_evidence_retained": True, "release_admission": False}, ensure_ascii=False),
              file=sys.stderr)
        raise SystemExit(1)
