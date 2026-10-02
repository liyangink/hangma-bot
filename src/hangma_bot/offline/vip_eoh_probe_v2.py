"""显式来源/2严格探针与仅读证明验证；共享生产typed规则、投影及受限评分接口。"""
from __future__ import annotations

import gzip
import json
import math
import os
from dataclasses import asdict
from pathlib import Path
import time

from hangma_bot.hangma.engine import HangmaRules
from hangma_bot.kernel.observation import CompetitionContext
from hangma_bot.kernel.actions import CANONICAL_TILE_ORDER
from hangma_bot.hangma.route_structure import ROUTE_STRUCTURE_SCHEMA_VERSION
from hangma_bot.hangma.natural_preparation import NATURAL_PREPARATION_SEMANTICS_VERSION
from hangma_bot.policy.route_heuristic_view import VIP_ROUTE_CANDIDATE_KIND
from hangma_bot.kernel.serialization import observation_from_json, window_key_from_json
from hangma_bot.policy.action_value_executor import ActionValueExecutor, WorkloadExceeded, EXECUTOR_VERSION
from hangma_bot.policy.action_value import MAX_TRACE_BYTES
from hangma_bot.policy.interface import DecisionRequest
from hangma_bot.policy.route_vip_heuristic import build_vip_route_scoring_view
from .scoring_sources import REPO_ROOT, source_manifest, write_code_snapshot
from .vip_eoh_generate import VipEohBatch, load_vip_parents
from .vip_eoh_input_sources import CLAIMS, canonical, fingerprint, sha, validate_public_input_panel

PROBE_SCHEMA = "vip-eoh-development-probe/2"
PLAN_SCHEMA = "vip-eoh-development-probe-plan/2"
PRODUCER_ROOTS = ("hangma_bot.offline.vip_eoh_probe_v2", "hangma_bot.offline.vip_eoh_input_sources")


def _write(path, value):
    path.write_bytes(canonical(value) + b"\n")


def _verify(files):
    for path, digest in files.items():
        if fingerprint(Path(path))["sha256"] != digest:
            raise ValueError("探针完整来源漂移:" + path)


def _load(path, batch, frozen, cost=None):
    """公共递归装载的实际读取闭包也冻结；只临时记录读取，不改生产文件。"""
    original = Path.read_bytes
    original_constructor = ActionValueExecutor.__init__
    def counted_constructor(instance, *args, **kwargs):
        if cost is not None:
            cost["executor_constructors"] += 1
        original_constructor(instance, *args, **kwargs)
    def tracked(file):
        raw = original(file)
        name, digest = str(file.resolve()), sha(raw)
        if name in frozen and frozen[name] != digest:
            raise ValueError("公共装载来源漂移:" + name)
        frozen[name] = digest
        return raw
    Path.read_bytes = tracked
    ActionValueExecutor.__init__ = counted_constructor
    try:
        return load_vip_parents([path], batch)[0]
    finally:
        Path.read_bytes = original
        ActionValueExecutor.__init__ = original_constructor


def validate_reference_policy(policy, candidates):
    """参照须是真生成直接父，或在当前/2批次明确冻结的参考；不凭parent标签自证。"""
    if type(policy) is not list or len(policy) != len(candidates):
        raise ValueError("每候选须有完整比较参照声明")
    ids = {c["identity"]["candidate_id"] for c in candidates}
    if len(ids) != len(candidates) or {p.get("candidate_id") for p in policy} != ids:
        raise ValueError("参照声明重复或未绑定当前候选")
    for declaration in policy:
        if set(declaration) != {"candidate_id", "basis", "reference_ids"}:
            raise ValueError("比较参照字段不完整")
        refs = declaration["reference_ids"]
        if type(refs) is not list or not refs or len(refs) != len(set(refs)) or declaration["candidate_id"] in refs:
            raise ValueError("比较参照重复、为空或冒用候选本人")
        candidate = next(c for c in candidates if c["identity"]["candidate_id"] == declaration["candidate_id"])
        if declaration["basis"] == "generation_direct_parents":
            generation = json.loads((Path(candidate["path"]) / "generation.json").read_bytes())
            actual = {p["identity"]["candidate_id"] for p in generation["parents"]}
            if not set(refs) <= actual:
                raise ValueError("比较参照不是生成真父")
        elif declaration["basis"] != "explicit_batch_reference":
            raise ValueError("未知比较参照来源")


def _read_plan(path):
    raw = path.read_bytes()
    plan = json.loads(raw)
    if set(plan) != {"schema", "purpose", "references", "input_view_limits", "wall_clock_seconds"} or plan["schema"] != PLAN_SCHEMA or plan["purpose"] != "development_behavior_diagnostic":
        raise ValueError("须显式/2探针计划")
    limits = plan["input_view_limits"]
    if set(limits) != {"max_single_view_bytes", "max_total_view_bytes", "max_views"} or any(type(v) is not int or v < 1 for v in limits.values()):
        raise ValueError("完整输入预算须显式正整数")
    if type(plan["wall_clock_seconds"]) not in (int, float) or not math.isfinite(plan["wall_clock_seconds"]) or plan["wall_clock_seconds"] <= 0:
        raise ValueError("探针单调秒额度不合法")
    return plan, raw


def run_public_input_probe(panel_file, batch_file, plan_file, out_dir, *, parent_paths, candidate_paths):
    """每包×窗全部真实评分；完整DTO评分前保存，失败/未调用保持分母，缓存不实施。"""
    began = time.monotonic()
    checked = validate_public_input_panel(panel_file)
    panel, frozen = checked["panel"], dict(checked["frozen_files"])
    plan, plan_raw = _read_plan(plan_file)
    batch = VipEohBatch.read(batch_file)
    frozen.update({str(plan_file.resolve()): sha(plan_raw), str(batch_file.resolve()): sha(batch.raw)})
    producer = source_manifest(PRODUCER_ROOTS)
    producer["scripts/vip_route_eoh_probe.py"] = fingerprint(REPO_ROOT / "scripts/vip_route_eoh_probe.py")
    frozen.update({str(REPO_ROOT / path): value["sha256"] for path, value in producer.items()})
    if not candidate_paths:
        raise ValueError("至少一候选包")
    paths = [*parent_paths, *candidate_paths]
    if len({str(Path(p).resolve()) for p in paths}) != len(paths):
        raise ValueError("探针包不得重复")
    packages, candidates = [], []
    cost = {"public_load_entries": 0, "executor_constructors": 0, "rule_calls": 0, "projection_calls": 0,
            "score_calls": 0, "dto_encoding_attempts": 0, "dto_write_attempts": 0, "dto_raw_bytes": 0, "dto_capture_monotonic_seconds": 0.0,
            "dto_capture_timing_scope": "candidate_view_encode_hash_gzip_write_flush_fsync_excludes_projection_score_stream_open_and_footer_close",
            "model_calls": 0, "world_advances": 0, "table_instances": 0}
    for index, path in enumerate(paths):
        path = Path(path).resolve()
        metadata = {"index": index, "role": "parent" if index < len(parent_paths) else "candidate", "path": str(path), "loaded": False}
        try:
            cost["public_load_entries"] += 1
            material = _load(path, batch, frozen, cost)
            metadata.update({"loaded": True, "identity": material["identity"], "source_sha256": material["source_sha256"], "record_sha256": material["record_sha256"]})
            cost["executor_constructors"] += 1
            executor = ActionValueExecutor(material["source"], max_operations=batch.max_operations,
                                           max_local_collection_size=batch.projection_limits.max_nodes)
            if metadata["role"] == "candidate":
                candidates.append(material)
        except (Exception, WorkloadExceeded) as error:
            material, executor = None, None
            metadata["error"] = {"type": type(error).__name__, "reason": str(error)}
        packages.append((metadata, material, executor))
    # 装载失败仍写全部分母；成功候选才能核真实参照，失败不能冒称通过。
    references_valid = False
    try:
        validate_reference_policy(plan["references"], candidates)
        loaded_refs = {p[0].get("identity", {}).get("candidate_id") for p in packages if p[0]["role"] == "parent" and p[0]["loaded"]}
        if not all(set(r["reference_ids"]) <= loaded_refs for r in plan["references"]):
            raise ValueError("冻结参照包未全部真实装载")
        references_valid = True
    except (Exception, WorkloadExceeded) as error:
        reference_error = {"type": type(error).__name__, "reason": str(error)}
    out_dir.mkdir(parents=True, exist_ok=False)
    write_code_snapshot(out_dir, producer)
    manifest = {"schema": PROBE_SCHEMA, **CLAIMS, "status": "planned", "implementation_manifest": producer,
                "panel_path": str(panel_file.resolve()), "panel_sha256": sha(panel_file.read_bytes()),
                "plan_path": str(plan_file.resolve()), "plan_sha256": sha(plan_raw), "references": plan["references"],
                "batch_path": str(batch_file.resolve()), "batch_sha256": sha(batch.raw), "packages": [p[0] for p in packages],
                "window_count": panel["window_count"], "input_sha256s": [r["input_sha256"] for r in panel["windows"]],
                "planned_package_windows": len(paths) * panel["window_count"], "frozen_files": frozen,
                "input_view_limits": plan["input_view_limits"], "full_input_capture": "actual_candidate_view_before_score_all_windows_no_cache/1",
                "ranking": "score_descending_then_action_key_lexicographic", "references_valid": references_valid}
    if not references_valid:
        manifest["reference_error"] = reference_error
    _write(out_dir / "manifest.json", manifest)
    rows, stop, dto_count = [], None, 0
    rules = HangmaRules(batch.rule_config)
    raw_output_errors = []
    try:
        with gzip.open(out_dir / "views.jsonl.gz", "xb") as views, (out_dir / "results.jsonl").open("x") as stream:
            for item in panel["windows"]:
                view, dto_sha, window_error = None, None, None
                if time.monotonic() - began >= plan["wall_clock_seconds"]:
                    stop = "monotonic_budget_exhausted_no_retry"
                if stop is None and references_valid:
                    capture_began = None
                    try:
                        observation, window = observation_from_json(item["observation"]), window_key_from_json(item["window_key"])
                        cost["rule_calls"] += 1
                        analysis = rules.analyze(observation, route_limits=batch.route_limits)
                        if sorted(c.action_key for c in analysis.legal_candidates) != item["legal_action_keys"]:
                            raise ValueError("真实规则全部合法根与面板不一致")
                        request = DecisionRequest(observation, CompetitionContext("vip-eoh-probe/2", None, None, None, None, (), 0), analysis,
                                                  "probe:" + item["input_sha256"], window.trigger_seq, window, ())
                        cost["projection_calls"] += 1
                        view = build_vip_route_scoring_view(request, batch.rule_config, limits=batch.projection_limits)
                        capture_began = time.monotonic()
                        cost["dto_encoding_attempts"] += 1
                        dto = view.candidate_view()
                        raw = canonical(dto)
                        limits = plan["input_view_limits"]
                        if len(raw) > limits["max_single_view_bytes"] or cost["dto_raw_bytes"] + len(raw) > limits["max_total_view_bytes"] or dto_count >= limits["max_views"]:
                            raise ValueError("完整DTO预算耗尽，不能跳过记录继续评分")
                        dto_sha = sha(raw)
                        cost["dto_write_attempts"] += 1
                        views.write(canonical({"input_sha256": item["input_sha256"], "view_sha256": dto_sha, "candidate_view": dto, "origins": item["origins"]}) + b"\n")
                        views.flush()
                        os.fsync(views.fileno())
                        dto_count += 1
                        cost["dto_raw_bytes"] += len(raw)
                    except (Exception, WorkloadExceeded) as error:
                        window_error = {"type": type(error).__name__, "reason": str(error)}
                        # 编码/写失败之后不尝试别的输入；规则或投影失败只使此窗失效。
                        if cost["dto_encoding_attempts"] > dto_count:
                            stop = "full_dto_capture_failed_no_further_scores"
                    finally:
                        if capture_began is not None:
                            cost["dto_capture_monotonic_seconds"] += time.monotonic() - capture_began
                for package, material, executor in packages:
                    if time.monotonic() - began >= plan["wall_clock_seconds"]:
                        stop = "monotonic_budget_exhausted_no_retry"
                    row = {"input_sha256": item["input_sha256"], "observation_sha256": item["observation_sha256"], "origins": item["origins"],
                           "package_index": package["index"], "candidate_id": package.get("identity", {}).get("candidate_id"), "status": "unfinished",
                           "score_calls": 0, "entries": [], "ordered_action_keys": [], "preferred_action_key": None,
                           "view_sha256_before": dto_sha, "view_sha256_after": None, "candidate_counted_operations": None,
                           "score_monotonic_ms": None, "cache_reused": False}
                    if stop or window_error or not references_valid or not package["loaded"]:
                        row["error"] = window_error or package.get("error") or {"reason": stop or "invalid_reference_policy"}
                    else:
                        tick = time.monotonic()
                        try:
                            row["score_calls"] = 1
                            cost["score_calls"] += 1
                            scored = executor.score_vip_route(view)
                            if scored.status != "SCORED":
                                raise ValueError("严格候选没有完成SCORED")
                            entries = sorted(scored.entries, key=lambda e: (-e.score, e.action_key))
                            if sorted(e.action_key for e in entries) != item["legal_action_keys"] or any(type(e.score) not in (int, float) or not math.isfinite(e.score) for e in entries):
                                raise ValueError("评分必须全合法根、有限且不重复")
                            # 执行器的计费容器是dict/list子类；递归转成线格式基础类型，
                            # 再核有限值、深度与字节。只转格式，不改变解释内容或评分。
                            normalized = [{"action_key": e.action_key, "score": e.score,
                                           "trace": json.loads(canonical(dict(e.trace)))} for e in entries]
                            for entry in normalized:
                                validate_trace(entry["trace"])
                            row.update(status="scored", entries=normalized,
                                       ordered_action_keys=[e.action_key for e in entries], preferred_action_key=entries[0].action_key)
                        except (Exception, WorkloadExceeded) as error:
                            row["error"] = {"type": type(error).__name__, "reason": str(error)}
                        finally:
                            row["candidate_counted_operations"] = executor.last_operation_count
                            row["score_monotonic_ms"] = (time.monotonic() - tick) * 1000
                            try:
                                row["view_sha256_after"] = sha(canonical(view.candidate_view()))
                            except (Exception, WorkloadExceeded) as error:
                                row["status"] = "unfinished"
                                row["error"] = {"type": type(error).__name__, "reason": str(error)}
                                stop = "typed_view_read_failed_no_further_scores"
                            if row["view_sha256_after"] != dto_sha:
                                row["status"] = "unfinished"
                                stop = "typed_view_mutation_no_further_scores"
                    if time.monotonic() - began >= plan["wall_clock_seconds"]:
                        stop = "monotonic_budget_exhausted_no_retry"
                    rows.append(row)
                    stream.write(canonical(row).decode() + "\n")
                    stream.flush()
    except (Exception, WorkloadExceeded) as error:
        # 流写入或关闭失败不能消失分母；不再调用业务，另存完整已调用前缀与未调用尾项。
        stop = "raw_stream_processing_failed_no_further_scores"
        failure = {"type": type(error).__name__, "reason": str(error)}
        raw_output_errors.append(failure)
        seen = {(r["input_sha256"], r["package_index"]) for r in rows}
        for item in panel["windows"]:
            for package, _, _ in packages:
                if (item["input_sha256"], package["index"]) in seen:
                    continue
                rows.append({"input_sha256": item["input_sha256"], "observation_sha256": item["observation_sha256"],
                    "origins": item["origins"], "package_index": package["index"],
                    "candidate_id": package.get("identity", {}).get("candidate_id"), "status": "unfinished",
                    "score_calls": 0, "entries": [], "ordered_action_keys": [], "preferred_action_key": None,
                    "view_sha256_before": None, "view_sha256_after": None, "candidate_counted_operations": None,
                    "score_monotonic_ms": None, "cache_reused": False, "error": failure})
        _write(out_dir / "failed-full-denominator.json", {"planned_package_windows": manifest["planned_package_windows"], "rows": rows, "raw_output_errors": raw_output_errors})
    drift = []
    try:
        _verify(frozen)
        validate_public_input_panel(panel_file)
        current = source_manifest(PRODUCER_ROOTS)
        current["scripts/vip_route_eoh_probe.py"] = fingerprint(REPO_ROOT / "scripts/vip_route_eoh_probe.py")
        if current != producer:
            raise ValueError("探针实际producer闭包漂移")
        for package, material, _ in packages:
            if package["loaded"]:
                cost["public_load_entries"] += 1
                if _load(Path(package["path"]), batch, frozen, cost) != material:
                    raise ValueError("包或递归来源漂移")
        _verify(frozen)
    except (Exception, WorkloadExceeded) as error:
        drift.append({"type": type(error).__name__, "reason": str(error)})
    if time.monotonic() - began >= plan["wall_clock_seconds"]:
        stop = "monotonic_budget_exhausted_no_retry"
    complete = sum(r["status"] == "scored" for r in rows)
    cost.update(monotonic_elapsed_seconds=time.monotonic() - began, dto_gzip_bytes=(out_dir / "views.jsonl.gz").stat().st_size if (out_dir / "views.jsonl.gz").exists() else 0,
                raw_output_errors=raw_output_errors)
    _write(out_dir / "costs.json", cost)
    raw_files = {str(path.resolve()): fingerprint(path) for path in sorted(out_dir.rglob("*")) if path.is_file()}
    _write(out_dir / "RAW-FIRST-SEAL.json", {"schema":"vip-eoh-probe-raw-first-seal/2", "files":raw_files, "before_summary":True})
    result = {**manifest, "frozen_files": frozen, "status": "invalidated" if drift else "probe_complete_not_admitted" if complete == len(rows) and stop is None else "probe_unfinished_not_admitted",
              "identity_stable": not drift, "drift": drift, "scored_package_windows": complete, "unfinished_package_windows": len(rows)-complete,
              "actual_score_calls": cost["score_calls"], "captured_input_windows": dto_count, "stop_reason": stop, "cost": cost,
              "raw_files": raw_files, "raw_output_errors": raw_output_errors, "raw_first_seal_sha256": sha((out_dir / "RAW-FIRST-SEAL.json").read_bytes()),
              "behavior_difference_scope": "this_source_panel_only_diagnostic_not_strength_or_admission"}
    _write(out_dir / "summary.json", result)
    return result


def validate_public_input_probe(summary_file, candidate, generation, *, reference_policy):
    """仅读重核真实/2producer、全图、所有包×窗及真参考身份；首选差异仅诊断。"""
    summary = json.loads(summary_file.read_bytes())
    if summary.get("schema") != PROBE_SCHEMA or summary.get("status") != "probe_complete_not_admitted" or summary.get("identity_stable") is not True or summary.get("drift") != [] or summary.get("raw_output_errors") != [] or any(summary.get(k) is not v for k,v in CLAIMS.items()):
        raise ValueError("/2探针必须完整、源稳定且未准入")
    if summary["references"] != reference_policy or summary["references_valid"] is not True or summary["batch_sha256"] != sha(generation.raw):
        raise ValueError("探针没有绑定当前生成批次及显式参照")
    producer = source_manifest(PRODUCER_ROOTS)
    producer["scripts/vip_route_eoh_probe.py"] = fingerprint(REPO_ROOT / "scripts/vip_route_eoh_probe.py")
    if producer != summary["implementation_manifest"]:
        raise ValueError("/2真实producer闭包漂移")
    frozen = dict(summary["frozen_files"])
    _verify(frozen)
    panel_file = Path(summary["panel_path"])
    if sha(panel_file.read_bytes()) != summary["panel_sha256"]:
        raise ValueError("面板摘要变化")
    checked = validate_public_input_panel(panel_file)
    panel = checked["panel"]
    frozen.update(checked["frozen_files"])
    if summary["window_count"] != panel["window_count"] or summary["input_sha256s"] != [r["input_sha256"] for r in panel["windows"]]:
        raise ValueError("探针未覆盖真实面板")
    if sha((summary_file.parent / "RAW-FIRST-SEAL.json").read_bytes()) != summary["raw_first_seal_sha256"]:
        raise ValueError("探针原始首封漂移")
    seal = json.loads((summary_file.parent / "RAW-FIRST-SEAL.json").read_bytes())
    if seal["schema"] != "vip-eoh-probe-raw-first-seal/2" or seal["files"] != summary["raw_files"]:
        raise ValueError("探针摘要不能替代原始首封")
    for path, expected in seal["files"].items():
        if fingerprint(Path(path)) != expected:
            raise ValueError("原始评分或完整图缺项/变化")
        frozen[path] = expected["sha256"]
    directory = summary_file.parent.resolve()
    required_files = {str(directory / name) for name in ("manifest.json", "results.jsonl", "views.jsonl.gz", "costs.json")}
    required_files.update(str(directory / "code_snapshot" / path) for path in producer)
    if set(seal["files"]) != required_files or seal.get("before_summary") is not True:
        raise ValueError("实际producer源码快照或RAW分母缺项")
    raw_manifest = json.loads((directory / "manifest.json").read_bytes())
    for field in raw_manifest:
        if field not in {"status", "frozen_files"} and raw_manifest[field] != summary[field]:
            raise ValueError("探针摘要冒充实际producer清单")
    if raw_manifest.get("status") != "planned" or raw_manifest["frozen_files"] != summary["frozen_files"]:
        raise ValueError("探针首尾来源清单变化")
    for relative, expected in producer.items():
        if fingerprint(directory / "code_snapshot" / relative) != expected:
            raise ValueError("真实producer源码快照漂移")
    plan_path = Path(summary["plan_path"])
    plan, plan_raw = _read_plan(plan_path)
    if sha(plan_raw) != summary["plan_sha256"] or plan["references"] != reference_policy or plan["input_view_limits"] != summary["input_view_limits"]:
        raise ValueError("实际探针前定计划漂移")
    frozen[str(plan_path.resolve())] = sha(plan_raw)
    cost = json.loads((directory / "costs.json").read_bytes())
    if cost != summary["cost"] or summary["stop_reason"] is not None or cost["monotonic_elapsed_seconds"] >= plan["wall_clock_seconds"]:
        raise ValueError("实际成本/单调秒额度不闭合")
    packages, materials = summary["packages"], []
    if (not packages or any(type(p["index"]) is not int or p["role"] not in ("parent", "candidate") for p in packages)
            or [p["index"] for p in packages] != list(range(len(packages))) or any(p["loaded"] is not True for p in packages)):
        raise ValueError("包序号/完整装载分母错误")
    for package in packages:
        material = _load(Path(package["path"]), generation, frozen)
        if any(package[k] != material[k] for k in ("identity", "source_sha256", "record_sha256")):
            raise ValueError("比较包身份冒充或来源漂移")
        materials.append(material)
    matches = [p["index"] for p,m in zip(packages,materials) if p["role"] == "candidate" and all(m[k] == candidate[k] for k in ("identity","source_sha256","record_sha256"))]
    if len(matches) != 1:
        raise ValueError("探针未唯一绑定当前真实候选")
    validate_reference_policy(reference_policy, [m for p,m in zip(packages,materials) if p["role"] == "candidate"])
    candidate_index = matches[0]
    refs = next(r["reference_ids"] for r in reference_policy if r["candidate_id"] == candidate["identity"]["candidate_id"])
    reference_indexes = [p["index"] for p in packages if p["role"] == "parent" and p["identity"]["candidate_id"] in refs]
    if {packages[i]["identity"]["candidate_id"] for i in reference_indexes} != set(refs):
        raise ValueError("冻结真参考没有完整实际评分")
    with gzip.open(summary_file.parent / "views.jsonl.gz", "rt") as stream:
        views = [json.loads(line) for line in stream]
    if len(views) != panel["window_count"] or [v["input_sha256"] for v in views] != summary["input_sha256s"]:
        raise ValueError("完整输入图分母缺项")
    view_index, dto_bytes = {}, 0
    for item, record in zip(panel["windows"], views):
        dto = record["candidate_view"]
        validate_dto_binding(dto, item, generation, candidate["identity"])
        raw_dto = canonical(dto)
        dto_bytes += len(raw_dto)
        if len(raw_dto) > plan["input_view_limits"]["max_single_view_bytes"]:
            raise ValueError("实际DTO超过单输入前定字节额度")
        if record["view_sha256"] != sha(canonical(dto)) or record["origins"] != item["origins"] or sorted(a["action_key"] for a in dto["actions"]) != item["legal_action_keys"]:
            raise ValueError("实际DTO/合法根/来源簇不完整")
        seen, nodes = set(), {}
        for node in dto["nodes"]:
            key = node["node_key"]
            if key in seen or node["gap_kind"] is not None or node.get("gap_kinds") or node["expected_child_count"] != node["completed_child_count"] or node["completed_child_count"] != len(node["children"]) or not set(node["children"]) <= seen:
                raise ValueError("实际完整图缺子、重复或有环")
            seen.add(key); nodes[key] = node
        todo, reached = [a["node_key"] for a in dto["actions"]], set()
        while todo:
            key = todo.pop()
            if key not in reached:
                reached.add(key); todo.extend(nodes[key]["children"])
        if reached != seen:
            raise ValueError("图含不可达节点")
        view_index[item["input_sha256"]] = record
    if (dto_bytes != cost["dto_raw_bytes"] or dto_bytes > plan["input_view_limits"]["max_total_view_bytes"]
            or len(views) > plan["input_view_limits"]["max_views"] or cost["dto_encoding_attempts"] != len(views)
            or cost["dto_write_attempts"] != len(views) or cost["rule_calls"] != len(views) or cost["projection_calls"] != len(views)
            or cost["dto_gzip_bytes"] != (directory / "views.jsonl.gz").stat().st_size):
        raise ValueError("全图记录成本/前定预算缺项")
    rows = [json.loads(line) for line in (summary_file.parent / "results.jsonl").read_text().splitlines()]
    expected_pairs = [(w["input_sha256"],p["index"]) for w in panel["windows"] for p in packages]
    if [(r["input_sha256"],r["package_index"]) for r in rows] != expected_pairs or len(rows) != summary["planned_package_windows"] or summary["scored_package_windows"] != len(rows) or summary["unfinished_package_windows"] != 0:
        raise ValueError("包乘窗口完整分母缺项/重复")
    lookup = {}
    for row in rows:
        item = next(w for w in panel["windows"] if w["input_sha256"] == row["input_sha256"])
        entries = row["entries"]
        if type(row["package_index"]) is not int or type(row["score_calls"]) is not int or row["status"] != "scored" or row["score_calls"] != 1 or row["cache_reused"] is not False or row["candidate_id"] != packages[row["package_index"]]["identity"]["candidate_id"]:
            raise ValueError("未真实评分或包身份不一致")
        if sorted(e["action_key"] for e in entries) != item["legal_action_keys"] or any(type(e["score"]) not in (int,float) or not math.isfinite(e["score"]) or type(e["trace"]) is not dict for e in entries):
            raise ValueError("全合法根有限评分/trace缺项")
        for entry in entries:
            validate_trace(entry["trace"])
        ordered = sorted(entries,key=lambda e:(-e["score"],e["action_key"]))
        if entries != ordered or row["ordered_action_keys"] != [e["action_key"] for e in ordered] or row["preferred_action_key"] != ordered[0]["action_key"]:
            raise ValueError("首选或完整排序冒充")
        if row["view_sha256_before"] != row["view_sha256_after"] or row["view_sha256_before"] != view_index[row["input_sha256"]]["view_sha256"] or type(row["candidate_counted_operations"]) is not int or not 0 <= row["candidate_counted_operations"] <= generation.max_operations:
            raise ValueError("输入或操作量漂移")
        lookup[row["input_sha256"],row["package_index"]] = row
    if (summary["actual_score_calls"] != sum(r["score_calls"] for r in rows) or cost["score_calls"] != len(rows)
            or summary["captured_input_windows"] != panel["window_count"]
            or any(cost[k] != 0 for k in ("model_calls", "world_advances", "table_instances"))):
        raise ValueError("真实调用/完整图成本分母不匹配")
    changed = {packages[i]["identity"]["candidate_id"]: sum(lookup[w["input_sha256"],i]["preferred_action_key"] != lookup[w["input_sha256"],candidate_index]["preferred_action_key"] for w in panel["windows"]) for i in reference_indexes}
    _verify(frozen)
    return {"frozen_files":frozen,"preferred_changes":changed,"observed_behavior_difference":any(changed.values()),
            "scope":"this_source_panel_only_diagnostic_not_strength_or_admission"}


def validate_trace(trace):
    """仅读复核公共评分合同的trace字节、有限值及JSON类型。"""
    if type(trace) is not dict or len(canonical(trace)) > MAX_TRACE_BYTES:
        raise ValueError("trace非字典或超合同字节额度")
    todo = [(trace, 0)]
    while todo:
        value, depth = todo.pop()
        if depth > 12:
            raise ValueError("trace嵌套超合同额度")
        if type(value) is dict:
            if any(type(k) is not str for k in value):
                raise ValueError("trace键须字符串")
            todo.extend((v, depth + 1) for v in value.values())
        elif type(value) in (list, tuple):
            todo.extend((v, depth + 1) for v in value)
        elif type(value) not in (str, int, float, bool, type(None)) or type(value) is float and not math.isfinite(value):
            raise ValueError("trace须有限JSON数据")


def validate_development_scope(proof, exploration, planned_table_instances, table_instance_limit):
    """没有观察首选改变只准显式≤16桌实例记录/覆盖探索；不产生强度准入。"""
    if exploration is not None:
        if (type(exploration) is not dict or set(exploration) != {"purpose", "max_table_instances"}
                or exploration["purpose"] != "recording_and_coverage_exploration"
                or type(exploration["max_table_instances"]) is not int
                or not 1 <= exploration["max_table_instances"] <= 16):
            raise ValueError("探索须显式用途及≤16桌实例额度")
        if (type(planned_table_instances) is not int or type(table_instance_limit) is not int
                or not 1 <= planned_table_instances <= table_instance_limit <= exploration["max_table_instances"]):
            raise ValueError("探索实际完整分母或预算超过前定小额额度")
    if proof["observed_behavior_difference"] is not True and exploration is None:
        raise ValueError("本真实来源面板未观察首选改变，不能默认投入大批自然开发")


def validate_dto_binding(dto, item, generation, identity):
    """复核实际DTO的玩家公开字段、规则、版本与展开额度；不重跑规则或投影。"""
    if (set(dto) != {"schema_version", "candidate_kind", "graph_schema_version", "tile_order", "visible_state", "binding", "limits", "workload", "actions", "nodes"}
            or dto["schema_version"] != identity["view_schema_version"]
            or dto["graph_schema_version"] != identity["graph_schema_version"]
            or dto["candidate_kind"] != VIP_ROUTE_CANDIDATE_KIND
            or dto["tile_order"] != list(CANONICAL_TILE_ORDER)
            or dto["limits"] != asdict(generation.projection_limits)):
        raise ValueError("实际DTO schema/完整字段/展开额度不是真共同合同")
    visible = observation_from_json(item["observation"])
    projected = {"seat": visible.seat, "dealer_seat": visible.dealer_seat, "phase": visible.phase,
                 "my_hand": [t.code for t in visible.my_hand], "drawn_tile": visible.drawn_tile.code if visible.drawn_tile else None,
                 "remaining_tile_count": visible.remaining_tile_count,
                 "discards": [[t.code for t in row] for row in visible.discards],
                 "melds": [[{"kind": m.kind, "tiles": [t.code for t in m.tiles], "from_seat": m.from_seat} for m in row] for row in visible.melds],
                 "hand_counts": list(visible.hand_counts)}
    if dto["visible_state"] != projected:
        raise ValueError("完整DTO不是面板的实际玩家公开观察")
    binding = dto["binding"]
    if (any(binding[k] != v for k,v in asdict(generation.rule_config).items())
            or binding["normal_draw_hu_payment_semantics_version"] != identity["normal_draw_hu_payment_semantics_version"]
            or binding["structure_semantics_version"] != ROUTE_STRUCTURE_SCHEMA_VERSION
            or binding["natural_preparation_semantics_version"] != NATURAL_PREPARATION_SEMANTICS_VERSION
            or binding["executor_version"] != EXECUTOR_VERSION):
        raise ValueError("完整DTO规则或条件支付语义漂移")
    workload = dto["workload"]
    if (workload["expanded_node_count"] != len(dto["nodes"])
            or workload["expanded_branch_count"] != sum(len(n["children"]) for n in dto["nodes"])
            or workload["expanded_node_count"] > generation.projection_limits.max_nodes
            or workload["expanded_branch_count"] > generation.projection_limits.max_branches
            or type(workload["waiting_draw_witness_count"]) is not int
            or not 0 <= workload["waiting_draw_witness_count"] <= generation.projection_limits.max_waiting_draw_witnesses
            or type(workload["target_distance_evaluation_count"]) is not int or workload["target_distance_evaluation_count"] < 0):
        raise ValueError("完整DTO展开/等待计量不闭合")
