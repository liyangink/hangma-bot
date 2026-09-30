"""VIP开发行为面板与候选窗口探针；不调用模型、不运行桌赛、不授予准入。

抽卡只读取行动前观察、窗口键和合法动作键。仅首选改变可记作开发行为
差异；装载、评分、观察耗时都不证明完赛、效果、官方时限或发布资格。
"""

from __future__ import annotations

import gzip
import hashlib
import io
import json
import time
from collections import Counter
from pathlib import Path
from typing import Any, Sequence

from hangma_bot.hangma.engine import HangmaRules
from hangma_bot.kernel.observation import CompetitionContext
from hangma_bot.kernel.serialization import observation_from_json, window_key_from_json
from hangma_bot.policy.action_value import STATUS_SCORED
from hangma_bot.policy.action_value_executor import ActionValueExecutor, WorkloadExceeded
from hangma_bot.policy.interface import DecisionRequest
from hangma_bot.policy.route_vip_heuristic import build_vip_route_scoring_view

from .scoring_sources import source_manifest
from .vip_eoh_generate import VipEohBatch, load_vip_parents

VIP_EOH_PANEL_SCHEMA = "vip-eoh-development-panel/1"
VIP_EOH_PROBE_SCHEMA = "vip-eoh-development-probe/1"
PANEL_SELECTION = {
    "version": "action_before_strata/1",
    "strata": ["phase", "own_white_count", "legal_action_families", "own_natural_pair_count"],
    "within_stratum": "unique_input_sha256_ascending",
    "across_strata": "phase_round_robin_then_stratum_tuple_ascending",
    "natural_pairs": "own_hand_plus_drawn_tile_excluding_white_sum_floor_count_over_2",
    "forbidden_selection_fields": ["outcome", "selected_action_key", "score", "compute_time", "status"],
}
_CLAIMS = {"development_only": True, "confirmation": False, "admitted": False,
           "complete_table_claim": False, "strength_claim": False, "release_claim": False}


def _json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                      allow_nan=False).encode("utf-8")


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _write(path: Path, value: Any) -> None:
    path.write_bytes(_json_bytes(value) + b"\n")


def _checked_bytes(path: Path, expected: str) -> bytes:
    if not isinstance(expected, str) or len(expected) != 64:
        raise ValueError("须显式提供冻结文件的完整SHA256")
    raw = path.read_bytes()
    if _sha(raw) != expected:
        raise ValueError(f"冻结文件SHA256漂移: {path.name}")
    return raw


def _read_audit(audit_dir: Path, manifest_sha256: str, decisions_sha256: str):
    manifest_raw = _checked_bytes(audit_dir / "manifest.json", manifest_sha256)
    decisions_raw = _checked_bytes(audit_dir / "decisions.jsonl.gz", decisions_sha256)
    manifest = json.loads(manifest_raw)
    if (manifest.get("schema") != "vip-heuristic-smoke-manifest/1"
            or manifest.get("strict_policy") is not True
            or manifest.get("normal_fallback_allowed") is not False
            or manifest.get("kind") != "mechanical_smoke_not_strength_or_runtime_gate"):
        raise ValueError("面板来源须是冻结的VIP严格机械审计")
    identity = manifest["identity"]
    if manifest["config"]["rules"] != identity["params"]["rule_config"]:
        raise ValueError("来源manifest的实际规则与候选身份不一致")
    if _sha((audit_dir / "candidate.py").read_bytes()) != identity["source_sha256"]:
        raise ValueError("来源人工种子源码与manifest不一致")
    # 从核过摘要的同一份gzip字节解压，避免核验与读取之间换文件。
    with gzip.GzipFile(fileobj=io.BytesIO(decisions_raw)) as stream:
        records = [json.loads(line) for line in stream if line.strip()]
    return manifest, records


def _input_record(record: dict[str, Any], line: int) -> dict[str, Any]:
    observation, window = record["observation"], record["window_key"]
    visible = observation_from_json(observation)
    key = window_key_from_json(window)
    if (visible.game_id, visible.round_no, visible.seat, visible.phase) != (
            key.game_id, key.round_no, key.seat, key.phase):
        raise ValueError("公开观察与窗口键绑定不一致")
    legal = record["legal_action_keys"]
    if (not isinstance(legal, list) or not legal or any(not isinstance(k, str) for k in legal)
            or len(set(legal)) != len(legal)):
        raise ValueError("来源合法动作键必须完整、非空且不重复")
    families = tuple(sorted({k.split(":", 1)[0] for k in legal}))
    if not set(families) <= {"discard", "chi", "peng", "gang", "hu", "pass"}:
        raise ValueError("来源含未知动作族")
    held = visible.my_hand + (() if visible.drawn_tile is None else (visible.drawn_tile,))
    counts = Counter(tile.code for tile in held)
    # 仅自己可见实体的描述计数，四张计两对；不充当七对/完整胡判定。
    stratum = (visible.phase, counts["白"], families,
               sum(count // 2 for code, count in counts.items() if code != "白"))
    payload = {"observation": observation, "window_key": window,
               "legal_action_keys": sorted(legal)}
    return {**payload, "source_line": line, "observation_sha256": _sha(_json_bytes(observation)),
            "input_sha256": _sha(_json_bytes(payload)),
            "stratum": [stratum[0], stratum[1], list(stratum[2]), stratum[3]]}


def _select(records, per_stratum, max_windows):
    strata: dict[tuple, dict[str, dict]] = {}
    for line, record in enumerate(records, start=1):
        item = _input_record(record, line)
        phase, white, families, pairs = item["stratum"]
        strata.setdefault((phase, white, tuple(families), pairs), {}).setdefault(item["input_sha256"], item)
    if not strata:
        raise ValueError("来源没有可抽取的公开动作窗口")
    # 超过默认64层时仍轮流覆盖各行动前阶段，不能因字符串排序吞掉后面的阶段。
    phases = sorted({key[0] for key in strata})
    phase_keys = {phase: sorted(key for key in strata if key[0] == phase) for phase in phases}
    keys = [phase_keys[phase][position] for position in range(max(map(len, phase_keys.values())))
            for phase in phases if position < len(phase_keys[phase])]
    groups = [sorted(strata[key].values(), key=lambda item: item["input_sha256"]) for key in keys]
    selected = [group[depth] for depth in range(per_stratum) for group in groups if depth < len(group)][:max_windows]
    return groups, selected


def build_vip_eoh_panel(
    audit_dir: Path, out_dir: Path, *, manifest_sha256: str, decisions_sha256: str,
    per_stratum: int = 1, max_windows: int = 64,
) -> dict[str, Any]:
    """核冻结审计摘要后按行动前事实抽卡，向新目录写panel.json。

    每层默认一张、默认最多64，可显式扩至128；层内以输入摘要确定选择，层间轮流选取。
    不读取成绩、首选、评分、耗时或成功状态来选择；错误与漂移抛异常。
    """

    if (type(per_stratum) is not int or per_stratum < 1 or type(max_windows) is not int
            or not 1 <= max_windows <= 128):
        raise ValueError("每层数量须为正整数，总面板须为1—128张")
    audit_dir, out_dir = Path(audit_dir), Path(out_dir)
    manifest, records = _read_audit(audit_dir, manifest_sha256, decisions_sha256)
    groups, selected = _select(records, per_stratum, max_windows)
    _checked_bytes(audit_dir / "manifest.json", manifest_sha256)
    _checked_bytes(audit_dir / "decisions.jsonl.gz", decisions_sha256)
    result = {"schema": VIP_EOH_PANEL_SCHEMA, **_CLAIMS,
              "selection": json.loads(_json_bytes(PANEL_SELECTION)),
              "per_stratum": per_stratum, "max_windows": max_windows,
              "source": {"audit_dir": str(audit_dir.resolve()), "manifest_sha256": manifest_sha256,
                         "decisions_sha256": decisions_sha256, "candidate_identity": manifest["identity"]},
              "source_window_count": len(records), "unique_input_count": sum(map(len, groups)),
              "stratum_count": len(groups), "stratum_sizes": [
                  {"stratum": group[0]["stratum"], "unique_input_count": len(group)} for group in groups],
              "window_count": len(selected), "windows": selected}
    out_dir.mkdir(parents=True, exist_ok=False)
    _write(out_dir / "panel.json", result)
    return result


def _read_panel(path: Path):
    raw = path.read_bytes()
    panel = json.loads(raw)
    if (panel.get("schema") != VIP_EOH_PANEL_SCHEMA or panel.get("selection") != PANEL_SELECTION
            or any(panel.get(k) != v for k, v in _CLAIMS.items())
            or not 1 <= panel.get("window_count", 0) <= 128
            or panel["window_count"] != len(panel["windows"])):
        raise ValueError("不是冻结的开发行为面板")
    source = panel["source"]
    manifest, records = _read_audit(Path(source["audit_dir"]), source["manifest_sha256"], source["decisions_sha256"])
    if source["candidate_identity"] != manifest["identity"]:
        raise ValueError("面板来源身份漂移")
    for item in panel["windows"]:
        line = item["source_line"]
        if type(line) is not int or not 1 <= line <= len(records) or item != _input_record(records[line - 1], line):
            raise ValueError("面板窗口或观察SHA256与原始审计不一致")
    if len({item["input_sha256"] for item in panel["windows"]}) != panel["window_count"]:
        raise ValueError("面板不得重复同一输入")
    if (type(panel.get("per_stratum")) is not int or panel["per_stratum"] < 1
            or type(panel.get("max_windows")) is not int or not 1 <= panel["max_windows"] <= 128
            or _select(records, panel["per_stratum"], panel["max_windows"])[1] != panel["windows"]):
        raise ValueError("面板选择不符合预定义口径")
    return panel, raw



def validate_vip_eoh_panel(panel_file: Path) -> dict[str, Any]:
    """重核开发面板、原审计摘要及行动前选择，返回只读用途的材料封套。

    返回panel与frozen_files；后者是实际路径到SHA256，供另一个离线驱动
    首尾冻结。只读取文件，无评分、模型、桌赛或写入；漂移/选择错误抛异常。
    """

    panel_file = Path(panel_file).resolve()
    panel, raw = _read_panel(panel_file)
    source = Path(panel["source"]["audit_dir"])
    frozen = {str(panel_file): _sha(raw),
              str((source / "manifest.json").resolve()): panel["source"]["manifest_sha256"],
              str((source / "decisions.jsonl.gz").resolve()): panel["source"]["decisions_sha256"],
              str((source / "candidate.py").resolve()): panel["source"]["candidate_identity"]["source_sha256"]}
    return {"panel": panel, "frozen_files": frozen}


def run_vip_eoh_probe(
    panel_file: Path, batch_file: Path, out_dir: Path, *,
    parent_paths: Sequence[Path], candidate_paths: Sequence[Path],
) -> dict[str, Any]:
    """共享每窗一次冻结事实，对有序父包/候选包逐项严格评分并落新目录。

    每个包独立受限executor；装载、建图、拒绝评分及超额均保留包×窗口分母。
    毫秒是单调时钟的本地观察，非官方动作时限；只首选改变计行为差异。
    比较未完成时保留已观察改变数量，但不发完整面板的行为差异信用。
    运行首尾重核包、输入及源码；漂移保留诊断输出并将整份报告标失效。
    """

    started_probe = time.perf_counter()
    panel_file, batch_file, out_dir = Path(panel_file), Path(batch_file), Path(out_dir)
    panel, panel_raw = _read_panel(panel_file)
    batch = VipEohBatch.read(batch_file)
    paths = [Path(p) for p in (*parent_paths, *candidate_paths)]
    if not candidate_paths:
        raise ValueError("探针至少需要一个有序候选包")
    implementation = source_manifest(("hangma_bot.offline.vip_eoh_probe",))
    packages = []
    for index, path in enumerate(paths):
        record = {"index": index, "role": "parent" if index < len(parent_paths) else "candidate",
                  "path": str(path.resolve()), "loaded": False}
        try:
            material = load_vip_parents([path], batch)[0]
            record.update({"loaded": True, "identity": material["identity"],
                           "record_sha256": material["record_sha256"], "source_sha256": material["source_sha256"]})
            executor = ActionValueExecutor(material["source"], max_operations=batch.max_operations)
        except (Exception, WorkloadExceeded) as error:
            material, executor = None, None
            record["error"] = {"type": type(error).__name__, "reason": str(error)}
        packages.append((record, material, executor))
    out_dir.mkdir(parents=True, exist_ok=False)
    _write(out_dir / "panel.json", panel)
    (out_dir / "batch.json").write_bytes(batch.raw)
    prereg = {"schema": VIP_EOH_PROBE_SCHEMA, **_CLAIMS, "status": "planned",
              "panel_path": str(panel_file.resolve()), "panel_sha256": _sha(panel_raw),
              "batch_path": str(batch_file.resolve()), "batch_sha256": _sha(batch.raw),
              "implementation_manifest": implementation, "packages": [p[0] for p in packages],
              "window_count": panel["window_count"],
              "input_sha256s": [item["input_sha256"] for item in panel["windows"]],
              "planned_package_windows": len(paths) * panel["window_count"],
              "ranking": "score_descending_then_action_key_lexicographic",
              "timing_scope": "local_monotonic_compute_ms_observed"}
    _write(out_dir / "manifest.json", prereg)
    rows = []
    rules = HangmaRules(batch.rule_config)
    with (out_dir / "results.jsonl").open("x", encoding="utf-8") as stream:
        for item in panel["windows"]:
            view, window_error = None, None
            analysis_ms, projection_ms = None, None
            try:
                observation = observation_from_json(item["observation"])
                window = window_key_from_json(item["window_key"])
                started = time.perf_counter()
                analysis = rules.analyze(observation, route_limits=batch.route_limits)
                analysis_ms = (time.perf_counter() - started) * 1000
                if sorted(c.action_key for c in analysis.legal_candidates) != item["legal_action_keys"]:
                    raise ValueError("当前规则的全部合法键与面板不一致")
                request = DecisionRequest(observation, CompetitionContext(
                    "vip-eoh-development-probe", None, None, None, None, (), 0), analysis,
                    "probe:" + item["input_sha256"], window.trigger_seq, window, ())
                started = time.perf_counter()
                view = build_vip_route_scoring_view(request, batch.rule_config, limits=batch.projection_limits)
                projection_ms = (time.perf_counter() - started) * 1000
            except (Exception, WorkloadExceeded) as error:
                window_error = {"type": type(error).__name__, "reason": str(error)}
            for package, material, executor in packages:
                row = {"input_sha256": item["input_sha256"], "observation_sha256": item["observation_sha256"],
                       "package_index": package["index"], "package_role": package["role"],
                       "candidate_id": package.get("identity", {}).get("candidate_id"), "status": "unfinished",
                       "rules_compute_ms_observed": analysis_ms, "projection_compute_ms_observed": projection_ms,
                       "scoring_compute_ms_observed": None, "candidate_counted_operations": None,
                       "preferred_action_key": None, "entries": [], "ordered_action_keys": []}
                if not package["loaded"] or window_error:
                    row["error"] = package.get("error") if not package["loaded"] else window_error
                else:
                    started = time.perf_counter()
                    try:
                        scored = executor.score_vip_route(view)
                        row["batch_status"] = scored.status
                        if scored.status != STATUS_SCORED:
                            raise ValueError("候选未完成SCORED: " + (scored.reason or "ABSTAIN"))
                        # 与RouteVipHeuristicPolicy.choose同源口径：分数降序，同分键字典序。
                        ordered = sorted(scored.entries, key=lambda entry: (-entry.score, entry.action_key))
                        row.update({"status": "scored", "preferred_action_key": ordered[0].action_key,
                                    "ordered_action_keys": [entry.action_key for entry in ordered],
                                    "entries": [{"action_key": entry.action_key, "score": entry.score,
                                                 "trace": dict(entry.trace)} for entry in ordered]})
                    except (Exception, WorkloadExceeded) as error:
                        row["error"] = {"type": type(error).__name__, "reason": str(error)}
                    finally:
                        row["scoring_compute_ms_observed"] = (time.perf_counter() - started) * 1000
                        row["candidate_counted_operations"] = executor.last_operation_count
                rows.append(row)
                stream.write(_json_bytes(row).decode("utf-8") + "\n")
                stream.flush()
    drift = []
    try:
        if panel_file.read_bytes() != panel_raw or batch_file.read_bytes() != batch.raw:
            raise ValueError("panel或batch字节漂移")
        _read_panel(panel_file)
        if source_manifest(("hangma_bot.offline.vip_eoh_probe",)) != implementation:
            raise ValueError("探针/第一方源码漂移")
    except Exception as error:
        drift.append({"type": type(error).__name__, "reason": str(error)})
    for package, material, _ in packages:
        if not package["loaded"]:
            continue
        try:
            final = load_vip_parents([Path(package["path"])], batch)[0]
            if final != material:
                raise ValueError("包身份或完整材料漂移")
        except (Exception, WorkloadExceeded) as error:
            drift.append({"package_index": package["index"], "type": type(error).__name__, "reason": str(error)})
    comparisons = []
    for index in range(len(parent_paths), len(paths)):
        candidate_rows = {r["input_sha256"]: r for r in rows if r["package_index"] == index}
        for parent_index in range(len(parent_paths)):
            parent_rows = [r for r in rows if r["package_index"] == parent_index]
            pairs = [(r, candidate_rows[r["input_sha256"]]) for r in parent_rows
                     if r["status"] == "scored" and candidate_rows[r["input_sha256"]]["status"] == "scored"]
            changed = sum(a["preferred_action_key"] != b["preferred_action_key"] for a, b in pairs)
            comparison_complete = len(pairs) == panel["window_count"] and not drift
            comparisons.append({"candidate_index": index, "parent_index": parent_index,
                                "planned_windows": panel["window_count"], "paired_scored_windows": len(pairs),
                                "unfinished_windows": panel["window_count"] - len(pairs),
                                "comparison_complete": comparison_complete,
                                "preferred_action_changed_windows": changed,
                                "score_changed_windows": sum({e["action_key"]: e["score"] for e in a["entries"]}
                                    != {e["action_key"]: e["score"] for e in b["entries"]} for a, b in pairs),
                                "nonpreferred_order_only_changed_windows": sum(
                                    a["preferred_action_key"] == b["preferred_action_key"]
                                    and a["ordered_action_keys"] != b["ordered_action_keys"] for a, b in pairs),
                                "observed_behavior_difference": bool(changed) and comparison_complete})
    complete = sum(r["status"] == "scored" for r in rows)
    result = {**prereg, "status": "invalidated" if drift else (
                  "probe_complete_not_admitted" if complete == len(rows) else "probe_unfinished_not_admitted"),
              "identity_stable": not drift, "drift": drift, "scored_package_windows": complete,
              "wall_clock_seconds_observed": time.perf_counter() - started_probe,
              "model_calls": 0, "table_instances": 0,
              "unfinished_package_windows": len(rows) - complete, "comparisons": comparisons,
              "per_package": [{"package_index": i, "planned_windows": panel["window_count"],
                               "scored_windows": sum(r["status"] == "scored" for r in rows if r["package_index"] == i)}
                              for i in range(len(paths))]}
    _write(out_dir / "summary.json", result)
    return result
