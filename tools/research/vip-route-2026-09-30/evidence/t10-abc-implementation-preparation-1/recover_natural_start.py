"""冻结自然 A 起点恢复量具；只在 execute/显式 START 门内调用业务。

prepare/static 只用标准库核文件、真实动作记录和运行源码，不导入业务。
execute 从完整 MatchSpec 重放四座实际动作，再导出/导入当前单局并重放
本局前缀；不调用策略、评分器或评分输入图投影器，不读取 WorldState 字段。
失败保留已成功前缀与实际费用；不换目标、补动作或自动重试。
"""
from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t10-abc-implementation-preparation-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

import argparse
from collections import Counter
from dataclasses import dataclass
import gzip
import hashlib
import json
import math
from pathlib import Path
import sys
import time
from typing import Any, Callable

ROOT = _PROJECT_ROOT
NATURAL = "frozen_natural_A_R18_action_before/1"
PREPARED_SCHEMA = "t10-natural-start-recovery-prepared/1"
START_SCHEMA = "t10-natural-start-recovery-start/1"


def canonical(value: Any) -> bytes:
    """规范 UTF-8 JSON；保留 None/0，拒绝非有限数。"""
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode()


def fingerprint(path: Path) -> dict:
    """流式文件身份；bytes 是原始字节数，sha256 是全部字节摘要。"""
    digest, size = hashlib.sha256(), 0
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
            size += len(chunk)
    return {"bytes": size, "sha256": digest.hexdigest()}


def read_json(path: Path) -> Any:
    """只读 JSON 原件；格式/缺失错误原样抛出。"""
    return json.loads(path.read_bytes())


def write_new(path: Path, value: Any) -> None:
    """独占创建 JSON，立即 flush；不覆盖已有批次文件。"""
    with path.open("xb") as stream:
        stream.write(canonical(value) + b"\n")
        stream.flush()


def require(condition: bool, message: str) -> None:
    """明确失败，不用可由 Python -O 关闭的 assert。"""
    if not condition:
        raise ValueError(message)


def window_id(window: dict) -> bytes:
    """完整窗口身份；schema 字段亦参与核对，不省略阶段或座位。"""
    require(set(window) == {"schema_version", "game_id", "round_no", "trigger_seq", "phase", "seat"},
            "窗口字段不完整")
    return canonical(window)


def frame_id(window: dict) -> tuple:
    """原驱动同期帧分组；同序号吃/碰仍是不同帧。"""
    return tuple(window[key] for key in ("game_id", "round_no", "trigger_seq", "phase"))


def load_material(panel_file: Path, input_sha256: str, output_dir: Path) -> tuple[dict, dict]:
    """纯文件准备；返回可冻结计划和内存中的真实前缀，不调用任何业务。"""
    panel_file, output_dir = panel_file.resolve(), output_dir.resolve()
    panel = read_json(panel_file)
    require(panel.get("schema") == "vip-eoh-development-panel/2", "仅接受冻结来源 /2 面板")
    require(panel.get("development_only") is True and panel.get("confirmation") is False,
            "面板必须是未确认开发材料")
    selected = [w for w in panel["windows"] if w["input_sha256"] == input_sha256]
    require(len(selected) == 1, "input_sha256 不唯一或不在面板中")
    item = selected[0]
    payload = {k: item[k] for k in ("observation", "window_key", "legal_action_keys")}
    require(hashlib.sha256(canonical(payload)).hexdigest() == input_sha256, "完整行动前输入摘要不符")
    require(len(item["origins"]) == 1 and item["origins"][0]["source_kind"] == NATURAL,
            "量具只接受唯一自然 A origin，不自动选择或合并来源")
    origin = item["origins"][0]
    require(origin["policy_role"] == "A" and origin["hidden_variant"] == "natural", "不是自然 A 原世界")
    frozen = {str(Path(p).resolve()): digest for p, digest in panel["frozen_files"].items()}
    require(len(frozen) == len(panel["frozen_files"]), "冻结路径别名重复")
    for name, digest in frozen.items():
        require(fingerprint(Path(name))["sha256"] == digest, "面板冻结原件漂移: " + name)

    def bound(path: Path) -> dict:
        path = path.resolve()
        require(str(path) in frozen, "实际来源未被面板绑定: " + str(path))
        facts = fingerprint(path)
        require(facts["sha256"] == frozen[str(path)], "实际来源漂移: " + str(path))
        return {"path": str(path), **facts}

    sources = []
    for reference in panel["source_refs"]:
        path = Path(reference["path"]).resolve()
        facts = bound(path)
        require(facts["sha256"] == reference["sha256"], "source_ref 摘要不符")
        source = read_json(path)
        if source["source_id"] == origin["source_id"]:
            sources.append(source)
    require(len(sources) == 1, "自然来源定义缺失或不唯一")
    source = sources[0]
    require(source["schema"] == "vip-eoh-input-source/2" and source["source_kind"] == NATURAL,
            "自然来源 schema/kind 不符")
    directory = Path(source["audit_dir"]).resolve()
    log = Path(origin["source_file"]).resolve()
    require(log == directory / origin["pool"] / "decisions.jsonl.gz", "origin 未指向该池自然行动日志")
    manifest_path = directory / "manifest.json"
    manifest = read_json(manifest_path)
    baseline = manifest["policy_metadata"]["A"]
    require(manifest["schema"] in ("vip-route-development-manifest/1", "vip-route-development-manifest/2")
            and manifest["source_kind"] == "simulation" and manifest["development_only"] is True
            and manifest["confirmation_claim"] is False and manifest["published"] is False,
            "不是已冻结自然开发生产来源")
    require(origin["pool"] in manifest["pool_ids"]
            and baseline["policy_id"] == origin["policy_id"]
            and baseline["registered_name"] == "r18_integrated_positive_v2"
            and baseline["provider"] == "registered_offline_research_not_live_release",
            "焦点 A/R18/对手池身份不符")
    root, permutation = origin["mother_root"], origin["permutation"]
    require(len(permutation) == 4 and all(type(v) is int for v in permutation)
            and set(permutation) == {0, 1, 2, 3}, "换座无效")
    require(any(r["root_id"] == root and permutation in r["permutations"] for r in manifest["frame"]),
            "origin 不在自然冻结抽样框")
    label = "".join(map(str, permutation))
    group_path = log.parent / ("group-" + hashlib.sha256(root.encode()).hexdigest()[:16] + "-" + label + ".json")
    refs = [bound(path) for path in (log, manifest_path, group_path, directory / "r18.py")]
    for field, path in (("manifest", manifest_path), ("raw_seal", Path(source["raw_seal"]["path"]))):
        ref = source[field]
        require(Path(ref["path"]).resolve() == path.resolve()
                and bound(path)["sha256"] == ref["sha256"], field + " 未绑定原件")
    seal = read_json(Path(source["raw_seal"]["path"]))
    if isinstance(seal.get("files"), dict):
        members = {str(Path(p).resolve()): v for p, v in seal["files"].items()}
    else:
        members = {str((_project_file(_PROJECT_ROOT, ROOT / v["path"])).resolve()): {k: v[k] for k in ("bytes", "sha256")}
                   for v in seal["members"]}
    for ref in refs:
        require(members.get(ref["path"]) == {k: ref[k] for k in ("bytes", "sha256")},
                "恢复原件未列入真实 RAW 首封: " + ref["path"])
    require(refs[-1]["sha256"] == baseline["source_sha256"], "R18 原件源码摘要不符")

    # 窄工具只支持规则/模拟/值对象来源未改的恢复，不自动解释语义版本差异。
    core = {}
    for name, expected in manifest["source_manifest"].items():
        if any(name.startswith("src/hangma_bot/" + p + "/") for p in ("hangma", "kernel", "simulation")):
            snapshot = directory / "code_snapshot" / name
            require({k: bound(snapshot)[k] for k in ("bytes", "sha256")} == expected,
                    "生产快照与声明不符: " + name)
            require(fingerprint(_project_file(_PROJECT_ROOT, ROOT / name)) == expected, "规则/模拟/值对象源码已变，拒绝自动兼容: " + name)
            core[name] = expected
    require(all("src/hangma_bot/" + name in core for name in
                ("simulation/engine.py", "simulation/shuffle.py", "simulation/projection.py",
                 "kernel/serialization.py", "hangma/engine.py")), "核心恢复生产依赖缺失")

    group = read_json(group_path)
    experiment = group["experiment"]
    match_id, round_no = origin["mother_single_hand"]
    require(match_id == item["window_key"]["game_id"] and round_no == item["window_key"]["round_no"]
            and item["window_key"]["seat"] == permutation[0], "母单局/焦点窗口身份不符")
    require(experiment["seat_permutations"] == [permutation]
            and experiment["baseline"]["policy_id"] == origin["policy_id"]
            and experiment["tournament_config"] == manifest["config"], "真实 experiment 装配身份不符")
    require(baseline["value_limits"] == manifest["value_limits"]
            and set(manifest["value_limits"]) == {"max_expansions", "max_routes_per_candidate"},
            "旧规则分析预算未完整冻结或与自然 A 身份不符")
    seeds = [s for s in experiment["seeds"] if s["scenario_id"] == root]
    require(len(seeds) == 1 and type(seeds[0]["seed"]) is int, "真实 seed 缺失或重复")
    require(match_id == f"{experiment['match_id_prefix']}:{root}:{label}:{origin['policy_id']}", "真实 match_id 不符")
    matches = [m for m in group["match_records"] if m["match_id"] == match_id]
    require(len(matches) == 1, "真实 MatchRunOutcome 缺失或重复")
    outcome = matches[0]["outcome"]
    require(outcome["status"] == "complete" and outcome["completed_hands"] == manifest["config"]["rounds_per_game"],
            "选定自然 A 来源不是完整实际记录")
    actual, groups, seen = outcome["decisions"], [], set()
    for record in actual:
        key = window_id(record["window_key"])
        require(key not in seen and record["window_key"]["game_id"] == match_id, "真实动作窗口重复/串桌")
        seen.add(key)
        identity = frame_id(record["window_key"])
        if not groups or frame_id(groups[-1][0]["window_key"]) != identity:
            groups.append([])
        groups[-1].append(record)
    target = window_id(item["window_key"])
    indexes = [i for i, records in enumerate(groups) if any(window_id(r["window_key"]) == target for r in records)]
    require(len(indexes) == 1, "实际动作中缺目标或重复目标")
    target_index = indexes[0]
    needed = {window_id(r["window_key"]) for records in groups[:target_index + 1] for r in records}
    audit, chosen_line = {}, None
    with gzip.open(log, "rt", encoding="utf-8") as stream:
        for line, text in enumerate(stream, 1):
            row = json.loads(text)
            if line == origin["source_line"]:
                chosen_line = row
            if row.get("match_id") == match_id and window_id(row["window_key"]) in needed:
                key = window_id(row["window_key"])
                require(key not in audit, "行动前原件窗口重复")
                audit[key] = row
    require(set(audit) == needed, "恢复所需四座完整行动前原件缺失")
    require(chosen_line == audit[target] and chosen_line["policy_id"] == origin["policy_id"]
            and chosen_line["observation"] == item["observation"]
            and chosen_line["window_key"] == item["window_key"]
            and sorted(chosen_line["legal_action_keys"]) == item["legal_action_keys"],
            "面板 origin 行号/完整输入与原件不符")
    for records in groups[:target_index + 1]:
        for record in records:
            row = audit[window_id(record["window_key"])]
            require(record["seat"] == record["window_key"]["seat"]
                    and record["policy_id"] == row["policy_id"], "真实动作与行动前策略/座位身份不符")
    prefix = groups[:target_index]
    require(all(r["legal"] is True and isinstance(r["action_key"], str)
                for records in prefix for r in records), "旧实际前缀没有合法已执行动作")
    current_prefix = [records for records in prefix if records[0]["window_key"]["round_no"] == round_no]
    runtime_files = {str(p.resolve()): fingerprint(p) for p in sorted((_project_file(_PROJECT_ROOT, ROOT / "src/hangma_bot")).rglob("*"))
                     if p.is_file() and p.suffix in {".py", ".c", ".h", ".so", ".dylib", ".pyd"}}
    spec = {"match_id": match_id, "scenario_id": root, "config": experiment["tournament_config"],
            "seed": seeds[0]["seed"], "initial_dealer": permutation[experiment["initial_dealer"]],
            "initial_scores": [experiment["initial_scores"][permutation.index(seat)] for seat in range(4)]}
    prepared = {"schema": PREPARED_SCHEMA, "panel_file": str(panel_file), "panel_sha256": fingerprint(panel_file)["sha256"],
        "input_sha256": input_sha256, "target_window": item["window_key"],
        "output_dir": str(output_dir), "tool_sha256": fingerprint(Path(__file__))["sha256"],
        "origin": origin, "source_refs": refs, "match_spec": spec, "simulation_version": experiment["simulation_version"],
        "value_limits": manifest["value_limits"],
        "expected_math_backend": manifest["candidate_identity"]["math_backend"], "runtime_files": runtime_files,
        "python_version": sys.version, "whole_table_prefix_frames": len(prefix), "single_hand_prefix_frames": len(current_prefix),
        "target_frame": [{k: audit[window_id(r["window_key"])][k] for k in
                          ("window_key", "observation", "legal_action_keys", "policy_id")} for r in groups[target_index]],
        "endpoint": "current_single_hand_end", "candidate_score_policy_scoring_projection_model_api_calls": 0}
    return prepared, {"prefix": prefix, "current_prefix": current_prefix, "audit": audit,
                      "target": groups[target_index], "frozen_files": frozen}


def prepare(panel_file: Path, input_sha256: str, output_dir: Path) -> dict:
    """纯文件创建 PREPARED.json；新目录副作用，失败留下 PREPARE-FAILED.json。"""
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=False)
    try:
        prepared, _ = load_material(panel_file, input_sha256, output_dir)
        write_new(output_dir / "PREPARED.json", prepared)
        return prepared
    except BaseException as exc:
        write_new(output_dir / "PREPARE-FAILED.json", {"status": "failed", "error": type(exc).__name__ + ": " + str(exc),
                                                    "business_calls": 0})
        raise


@dataclass(frozen=True)
class RecoveredNaturalStart:
    """同进程单局起点结果；只有静态身份与目标观察全部核齐才返回。"""
    rules: Any  # 同源规则实例；调用方重新装配冻结策略，不使用旧评分器
    engine: Any  # 公开 SimulationEngine；世界只经其方法消费
    world: Any  # 不可变不透明单局中途句柄，不读取其暗手/牌墙字段
    frame: Any  # 当前公开决策帧；所有同期回应者尚未提交动作
    target_window: Any  # 原完整 WindowKey，含座位与阶段，供 B 精确一次干预
    stage_snapshot: dict  # 本单局 frame_observation_summary；revision/completed_hands 已重新生成
    receipt_path: Path  # 本次恢复成功 JSON 的绝对路径；隐藏物理来源另存在同目录


def recover_natural_start(panel_file: Path, input_sha256: str, output_dir: Path, *,
                          start_path: Path, charge: Callable[[str], None] | None = None,
                          parent_prepared_file: Path | None = None,
                          parent_recovery_id: str | None = None,
                          save_json: Callable[[Path, Any], None] | None = None,
                          open_output: Callable[[Path, str], Any] | None = None) -> RecoveredNaturalStart:
    """execute 门：输入冻结面板/输入摘要/已prepare的新目录及明确 START。

    charge(name) 在每次实际 API 调用前触发；回调可因总预算抛错，此时该 API
    未派发。费用计实际派发含失败；耗时为单调持续秒，限额是协作检查而非抢占。
    文件副作用为 ENTRY、逐次前缀、单局教师来源与终态收据。异常不返回句柄，
    留下已成功重放前缀和累计费用；没有规则/策略/世界自动重试。
    ABC 调用方只能从自身 execute 命令进入此同一 START 门。
    parent_prepared_file 仅接受 t10-abc-pilot-prepared/1 父登记；复用其 ROOT
    START 与嵌入 recovery 材料，不生成子 START/PREPARED。save_json/open_output
    可注入父批总输出字节门；默认保留原独占文件接口与 standalone schema。
    """
    output_dir = output_dir.resolve()
    prepared_path = (parent_prepared_file.resolve() if parent_prepared_file else output_dir / "PREPARED.json")
    document, start = read_json(prepared_path), read_json(start_path.resolve())
    diagnostic = parent_prepared_file is not None and document.get("schema") == "t10-abc-diagnostic-prepared/1"
    if diagnostic:
        selected = [r for r in document["roots"] if r["root_id"] == parent_recovery_id and r["source_kind"] == "natural"]
        require(len(selected) == 1, "父登记自然恢复身份缺失或重复")
        prepared = selected[0]["recovery"]
    else:
        require(parent_recovery_id is None, "单根恢复不接受批次身份")
        prepared = document["recovery"] if parent_prepared_file else document
    schema = "t10-abc-diagnostic-start/1" if diagnostic else ("t10-abc-pilot-start/1" if parent_prepared_file else START_SCHEMA)
    require(start.get("schema") == schema and start.get("status") == "START", "缺明确恢复 START")
    require(Path(start["prepared_file"]).resolve() == prepared_path
            and start["prepared_sha256"] == fingerprint(prepared_path)["sha256"], "START/准备材料绑定不符")
    recovery_sha256 = fingerprint(Path(__file__))["sha256"]
    require(recovery_sha256 == prepared["tool_sha256"], "恢复工具与准备材料绑定不符")
    if parent_prepared_file:
        require(document.get("schema") in {"t10-abc-pilot-prepared/1", "t10-abc-diagnostic-prepared/1"}
                and document["recovery_tool_sha256"] == recovery_sha256
                and start["tool_sha256"] == document["tool_sha256"] == fingerprint(Path(document["tool_file"]))["sha256"],
                "ABC父工具/ROOT START绑定不符")
    else:
        require(start["tool_sha256"] == recovery_sha256, "START/恢复工具绑定不符")
    require(str(panel_file.resolve()) == prepared["panel_file"] and input_sha256 == prepared["input_sha256"]
            and str(output_dir) == prepared["output_dir"], "execute 不得换面板、目标或目录")
    budgets = start["budgets"]["recovery"] if parent_prepared_file else start["budgets"]
    require(set(budgets) == {"max_replay_frames", "wall_clock_seconds"}
            and type(budgets["max_replay_frames"]) is int and budgets["max_replay_frames"] > 0
            and type(budgets["wall_clock_seconds"]) in (int, float)
            and math.isfinite(budgets["wall_clock_seconds"]) and budgets["wall_clock_seconds"] > 0, "恢复预算须显式正数")
    start_sha256 = fingerprint(start_path.resolve())["sha256"]
    save = save_json or write_new
    open_file = open_output or (lambda path, mode: path.open(mode))
    save(output_dir / "RECOVERY-ENTRY.json", {"start_path": str(start_path.resolve()),
        "start_sha256": start_sha256, "input_sha256": input_sha256,
        "status": "entered", "budgets": budgets})
    counts, started, active = Counter(), time.monotonic(), True
    result, primary_error = {"status": "unfinished", "input_sha256": input_sha256, "prefix_file": "replay-prefix.jsonl"}, None
    trace = open_file(output_dir / "replay-prefix.jsonl", "xb")

    def call(name, fn, *args, **kwargs):
        if time.monotonic() - started >= budgets["wall_clock_seconds"]:
            raise RuntimeError("recovery_wall_clock_limit")
        if name == "world_advance_calls" and counts[name] >= budgets["max_replay_frames"]:
            raise RuntimeError("recovery_replay_frame_limit")
        if charge is not None:
            charge(name)
        counts[name] += 1
        return fn(*args, **kwargs)

    def record(value):
        trace.write(canonical(value) + b"\n")
        trace.flush()

    try:
        current, material = call("source_validation_entries", load_material, panel_file, input_sha256, output_dir)
        require(current == prepared and sys.version == prepared["python_version"], "prepare 后来源/运行环境漂移")
        sys.path.insert(0, str(_project_file(_PROJECT_ROOT, ROOT / "src")))
        # 所有业务导入位于已绑定 START 内；没有策略构造或评分入口。
        from hangma_bot.hangma.engine import HangmaRules
        from hangma_bot.hangma.interface import ValueAnalysisLimits
        from hangma_bot.kernel.config import RuleConfig, TimingConfig, TournamentConfig
        from hangma_bot.kernel.serialization import observation_to_json, window_key_to_json, window_key_from_json
        from hangma_bot.simulation.engine import SimulationEngine, WORLD_SCHEMA
        from hangma_bot.simulation.interface import MatchSpec, SimulationChoice
        from hangma_bot.simulation.artifacts import compute_rules_hash, hand_math_runtime_metadata
        from hangma_bot.offline.evaluate import frame_observation_summary
        require(WORLD_SCHEMA == prepared["simulation_version"], "模拟世界版本不符")
        for name, module in tuple(sys.modules.items()):
            if name.startswith("hangma_bot.") and getattr(module, "__file__", None):
                path = Path(module.__file__).resolve()
                require(str(path) in prepared["runtime_files"] and fingerprint(path) == prepared["runtime_files"][str(path)],
                        "实际导入不在冻结运行源码/原生文件中: " + str(path))
        backend = call("runtime_identity_calls", hand_math_runtime_metadata)
        expected = prepared["expected_math_backend"]
        require(all(backend.get(k) == expected.get(k) for k in ("implementation", "semantics_version", "fallback_reason"))
                and backend.get("native_sha256") == (expected.get("native_binary") or {}).get("sha256"), "真实数学后端与自然来源不符")
        result["math_backend"] = backend

        class RecoveryRules(HangmaRules):
            """只在恢复阶段计唯一规则实现的实际分析；返回后不计后续 ABC 费用。"""
            def analyze(self, *args, **kwargs):
                return call("rules_analyze_calls", super().analyze, *args, **kwargs) if active else super().analyze(*args, **kwargs)

        raw = prepared["match_spec"]
        cfg = raw["config"]
        config = TournamentConfig(cfg["max_games"], cfg["rounds_per_game"], RuleConfig(**cfg["rules"]), TimingConfig(**cfg["timing"]))
        rules = call("rules_constructors", RecoveryRules, config.rules)
        route_limits = ValueAnalysisLimits(**prepared["value_limits"])
        rules_hash = call("rules_identity_calls", compute_rules_hash, ROOT)
        engine = call("world_engine_constructors", SimulationEngine, rules, rules_hash=rules_hash)
        spec = MatchSpec(raw["match_id"], raw["scenario_id"], config, raw["seed"], raw["initial_dealer"], tuple(raw["initial_scores"]))

        def check_frame(frame, records):
            require(frame.blocked_reason is None and frame.final_scores is None, "恢复提前终局或阻塞")
            require([window_id(window_key_to_json(d.window_key)) for d in frame.decisions]
                    == [window_id(r["window_key"]) for r in records], "同期帧/完整回应者/实际前缀错位")
            analyses = []
            for decision, old in zip(frame.decisions, records):
                frozen_row = material["audit"][window_id(old["window_key"])]
                require(observation_to_json(decision.observation) == frozen_row["observation"], "完整玩家观察与旧行动前原件不等")
                analysis = rules.analyze(decision.observation, route_limits=route_limits)
                require(analysis.completeness.value == "complete", "恢复规则分析不完整")
                require(sorted(c.action_key for c in analysis.legal_candidates) == sorted(frozen_row["legal_action_keys"]),
                        "完整合法键与旧原件不等")
                analyses.append(analysis)
            return analyses

        def replay(world, prefix, phase):
            for ordinal, records in enumerate(prefix, 1):
                frame = call("world_frame_calls", engine.frame, world)
                analyses = check_frame(frame, records)
                choices = []
                for decision, old, analysis in zip(frame.decisions, records, analyses):
                    candidates = [c for c in analysis.legal_candidates if c.action_key == old["action_key"]]
                    require(old["legal"] is True and len(candidates) == 1, "旧实际动作当前不唯一合法")
                    choices.append(SimulationChoice(decision.window_key, candidates[0].action))
                entry = {"phase": phase, "ordinal": ordinal, "revision": frame.revision,
                         "choices": [{"window_key": r["window_key"], "action_key": r["action_key"]} for r in records]}
                record({**entry, "status": "advance_pending"})
                world = call("world_advance_calls", engine.advance, world, frame.revision, tuple(choices))
                record({**entry, "status": "advanced"})
            return world

        world = call("world_start_calls", engine.start, spec)
        world = replay(world, material["prefix"], "whole_table")
        target_frame = call("world_frame_calls", engine.frame, world)
        check_frame(target_frame, material["target"])
        round_no = prepared["origin"]["mother_single_hand"][1]
        hand = call("world_export_hand_calls", engine.export_hand, world, round_no)
        save(output_dir / "single-hand-teacher-origin.json", {"scope": "offline_teacher_full_world_only", "hand": hand})
        single = call("world_import_calls", engine.from_replay, hand)
        single = replay(single, material["current_prefix"], "single_hand")
        frame = call("world_frame_calls", engine.frame, single)
        check_frame(frame, material["target"])
        require([observation_to_json(d.observation) for d in frame.decisions]
                == [observation_to_json(d.observation) for d in target_frame.decisions], "单局转换改变目标完整观察")
        # 单局导入重置 revision/completed_hands；核观察后生成它自己的摘要。
        snapshot = {"observation_summary": frame_observation_summary(frame),
                    "match_spec": {"match_id": raw["match_id"]}, "origin_match_spec": raw,
                    "endpoint": "current_single_hand_end"}
        result.update(status="recovered_single_hand_start", origin=prepared["origin"], rules_hash=rules_hash,
            target_frame=prepared["target_frame"], stage_snapshot=snapshot,
            whole_table_summary=frame_observation_summary(target_frame),
            candidate_score_policy_scoring_projection_model_api_calls=0)
        for name, digest in material["frozen_files"].items():
            require(fingerprint(Path(name))["sha256"] == digest, "恢复后来源漂移: " + name)
        for name, facts in prepared["runtime_files"].items():
            require(fingerprint(Path(name)) == facts, "恢复后运行代码漂移: " + name)
        for path, digest in ((panel_file, prepared["panel_sha256"]),
                             (prepared_path, start["prepared_sha256"]),
                             (Path(__file__), recovery_sha256), (start_path, start_sha256)):
            require(fingerprint(path)["sha256"] == digest, "恢复后执行身份漂移: " + str(path))
        return RecoveredNaturalStart(rules, engine, single, frame,
            window_key_from_json(prepared["target_window"]), snapshot, output_dir / "RECOVERY-RESULT.json")
    except BaseException as exc:
        primary_error = exc
        result.update(status="failed_no_start_returned", error=type(exc).__name__ + ": " + str(exc))
        raise
    finally:
        active = False
        result.update(actual_calls=dict(counts), elapsed_monotonic_seconds=time.monotonic() - started,
                      timing_scope="cooperative_monotonic_duration_not_official_action_timeout",
                      automatic_retries=0)
        try:
            trace.close()
            save(output_dir / "RECOVERY-RESULT.json", result)
        except BaseException as secondary:
            if primary_error is None:
                raise
            primary_error.add_note("恢复费用/终态写入再次失败: " + type(secondary).__name__ + ": " + str(secondary))


def main() -> None:
    """CLI：prepare/static 不导入业务；execute 必须显式提供 START 路径。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "static", "execute"))
    parser.add_argument("--panel-file", required=True, type=Path)
    parser.add_argument("--input-sha256", required=True)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--start", type=Path)
    args = parser.parse_args()
    if args.command == "execute":
        if args.start is None:
            parser.error("execute 必须提供 --start")
        recovered = recover_natural_start(args.panel_file, args.input_sha256, args.output_dir, start_path=args.start)
        print(canonical({"status": "recovered_single_hand_start", "receipt_path": str(recovered.receipt_path)}).decode())
    else:
        require(args.start is None, "prepare/static 不消费 START")
        prepared = prepare(args.panel_file, args.input_sha256, args.output_dir) if args.command == "prepare" else load_material(args.panel_file, args.input_sha256, args.output_dir)[0]
        print(canonical({k: prepared[k] for k in ("schema", "input_sha256", "output_dir", "whole_table_prefix_frames", "single_hand_prefix_frames")}).decode())


if __name__ == "__main__":
    main()
