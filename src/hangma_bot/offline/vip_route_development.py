"""VIP 候选与注册研究 R18 v2 的自然完整桌开发比较。

全选冻结牌山根，H/M 新对手池分别保留四映射 A/C 八行。机会账只记
行动前的当前合法胡；赛后已发生结算另记，不能倒填未来资格或删失分母。
本入口不调用模型、不准入、不发布；假驱动永不冒充生产模拟证据。
"""

from __future__ import annotations

import gzip
import hashlib
import json
import math
import os
import platform
import sys
import time
from collections import Counter
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

from hangma_bot.adapters.recording.project_storage import project_file
from hangma_bot.application.deadline import BudgetPolicy
from hangma_bot.hangma._standard import backend_info
from hangma_bot.hangma.engine import HangmaRules
from hangma_bot.kernel.config import TimingConfig, TournamentConfig
from hangma_bot.kernel.serialization import observation_to_json, window_key_to_json
from hangma_bot.policy.action_value import STATUS_SCORED
from hangma_bot.policy.action_value_executor import WorkloadExceeded
from hangma_bot.policy.action_value_policy import ActionValuePolicy
from hangma_bot.policy.heuristic_v2 import ComparableHeuristicPolicyV2
from hangma_bot.policy.hu_upgrade_calibration import RISK_CELLS, RISK_RULESET_VERSION, RISK_VERSION, SAFETY_MARGIN
from hangma_bot.policy.research_candidates import (
    R18_INTEGRATED_POSITIVE_V2_NAME, build_research_candidate_scorer,
)
from hangma_bot.policy.route_vip_heuristic import RouteVipHeuristicPolicy
from hangma_bot.policy.v2_hu_upgrade import V2HuUpgradePolicy
from hangma_bot.policy.weights_v1 import DEFAULT_WEIGHTS_V1, V2_PARAM_BATCH_WEIGHTS
from hangma_bot.simulation import MatchSpec, SimulationChoice, SimulationEngine
from hangma_bot.simulation.artifacts import compute_rules_hash
from hangma_bot.simulation.engine import WORLD_SCHEMA

from .evaluate import MatchExperiment, MatchSeedSpec, PolicyDeclaration, run_match_experiment
from .scoring_sources import REPO_ROOT, digest_of_file, source_manifest, write_code_snapshot
from .scoring_input_capture import ScoringInputCapture, ScoringInputCaptureLimits
from .vip_eoh_generate import VipEohBatch, load_vip_parents
from .vip_evaluation import FrozenRoot, audit_vip_batch

VIP_DEVELOPMENT_BATCH_SCHEMA = "vip-route-development-batch/1"  # 历史读取保持旧身份
VIP_DEVELOPMENT_CAPTURE_BATCH_SCHEMA = "vip-route-development-batch/2"
VIP_DEVELOPMENT_ROOTS = ("hangma_bot.offline.vip_route_development",)
NEW_POOL_IDS = {"H": "vip-development-newpool-r18-three/1",
                "M": "vip-development-newpool-r18-full-v2-upgrade-v2/1"}


def _sha(value: bytes | str) -> str:
    return hashlib.sha256(value.encode("utf-8") if isinstance(value, str) else value).hexdigest()


def _write(path: Path, value: Any) -> None:
    """仅改写本次新目录中的进度件；费用先落盘，异常不清除预留。"""

    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n"
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)
    directory_fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


@contextmanager
def _close_preserving_primary(stream):
    """私有关闭实现；已有用户中断时，流关闭的第二故障只加说明。"""
    try:
        yield stream
    finally:
        primary = sys.exc_info()[1]
        try:
            stream.close()
        except BaseException as secondary:
            if primary is None:
                raise
            primary.add_note("离线审计流关闭再次失败:" + type(secondary).__name__ + ": " + str(secondary))


def _positive(value: Any, name: str, *, integer: bool = True) -> None:
    if (type(value) not in ((int,) if integer else (int, float))
            or not math.isfinite(value) or value <= 0):
        raise ValueError(name + "须为正有限数，计数须为整数")


@dataclass(frozen=True)
class VipDevelopmentBatch:
    """公开冻结开发预算；时间是墙钟持续秒，积分顺序为物理座位 0—3。"""

    batch_id: str
    generation_batch_file: Path
    candidate_package: Path
    behavior_probe_summary_file: Path  # 桌赛前强制首选行为差异门，不能替代强度门
    seeds: tuple[tuple[FrozenRoot, int], ...]
    pools: tuple[str, ...]
    table_instance_limit: int
    wall_clock_limit_seconds: float
    step_limit: int
    raw: bytes
    frozen_files: Mapping[str, str]  # 实际公开文件绝对路径到字节摘要
    scoring_input_capture: ScoringInputCaptureLimits | None  # /1历史读取为None；新运行须显式/2预算

    @classmethod
    def read(cls, path: Path, *, allow_mock_behavior_fixture: bool = False) -> "VipDevelopmentBatch":
        """核验实际探针、身份、抽样框及预算；只有假驱动可显式允许结构fixture。"""

        if type(allow_mock_behavior_fixture) is not bool:
            raise ValueError("假行为结构fixture豁免须显式布尔值")
        path = path.resolve()
        raw = path.read_bytes()
        data = json.loads(raw)
        keys = {"schema", "batch_id", "generation_batch_file", "generation_batch_sha256",
                "candidate_package", "candidate_generation_sha256", "candidate_source_sha256",
                "behavior_probe_summary_file", "behavior_probe_summary_sha256",
                "seeds", "pools", "rounds", "initial_dealer_physical", "initial_scores",
                "table_instance_limit", "wall_clock_limit_seconds", "step_limit"}
        if not isinstance(data, dict):
            raise ValueError("开发批次须是完整JSON对象")
        schema = data.get("schema")
        capture = None
        if schema == VIP_DEVELOPMENT_CAPTURE_BATCH_SCHEMA:
            keys |= {"scoring_input_capture", "behavior_reference_policy", "behavior_exploration"}
            capture = ScoringInputCaptureLimits.from_json(data.get("scoring_input_capture"))
        elif schema != VIP_DEVELOPMENT_BATCH_SCHEMA:
            raise ValueError("开发批次schema未知")
        if set(data) != keys:
            raise ValueError("开发批次须使用完整独立 schema")
        if not isinstance(data["batch_id"], str) or not data["batch_id"].strip():
            raise ValueError("batch_id不能为空")
        if (type(data["rounds"]) is not int or data["rounds"] != 8
                or type(data["initial_dealer_physical"]) is not int or data["initial_dealer_physical"] != 0
                or data["initial_scores"] != [0, 0, 0, 0]
                or any(type(value) is not int for value in data["initial_scores"])):
            raise ValueError("本档固定8单局、物理起庄0及四席初分0")
        pools = data["pools"]
        if not isinstance(pools, list) or len(pools) != 2 or set(pools) != set(NEW_POOL_IDS):
            raise ValueError("本档须分别运行H/M两个新池")
        seeds = []
        if not isinstance(data["seeds"], list) or not data["seeds"]:
            raise ValueError("须冻结至少一个牌山根")
        for entry in data["seeds"]:
            if not isinstance(entry, dict) or set(entry) != {"root_id", "seed", "permutations"}:
                raise ValueError("牌山根字段不完整")
            if type(entry["seed"]) is not int or entry["seed"] < 0:
                raise ValueError("seed须为非负整数")
            if not isinstance(entry["root_id"], str) or not entry["root_id"].strip():
                raise ValueError("root_id须为非空字符串")
            permutations = entry["permutations"]
            if (not isinstance(permutations, list) or len(permutations) != 4
                    or any(not isinstance(p, list) or any(type(v) is not int for v in p) for p in permutations)):
                raise ValueError("每根须冻结四个整数座位映射")
            root = FrozenRoot(entry["root_id"], tuple(tuple(p) for p in permutations),
                              ("all_natural",) * 4, (0.0,) * 4)
            seeds.append((root, entry["seed"]))
        if len({r.root_id for r, _ in seeds}) != len(seeds) or len({s for _, s in seeds}) != len(seeds):
            raise ValueError("牌山根与seed须一一对应且不重复")
        for name in ("table_instance_limit", "step_limit"):
            _positive(data[name], name)
        _positive(data["wall_clock_limit_seconds"], "wall_clock_limit_seconds", integer=False)
        if data["table_instance_limit"] < len(seeds) * len(pools) * 8:
            raise ValueError("桌实例预算不足以覆盖全部四映射A/C分母")
        def resolved(name):
            if not isinstance(data[name], str) or not data[name].strip():
                raise ValueError(name + "须为公开文件路径")
            return (path.parent / data[name]).resolve()
        generation_file, package = resolved("generation_batch_file"), resolved("candidate_package")
        probe_file = resolved("behavior_probe_summary_file")
        files = {str(path): _sha(raw)}
        for file, expected in ((generation_file, data["generation_batch_sha256"]),
                               (package / "generation.json", data["candidate_generation_sha256"]),
                               (package / "candidate.py", data["candidate_source_sha256"]),
                               (probe_file, data["behavior_probe_summary_sha256"])):
            if not isinstance(expected, str) or len(expected) != 64 or _sha(file.read_bytes()) != expected:
                raise ValueError("公开配置或候选包字节摘要不匹配")
            files[str(file)] = expected
        generation = VipEohBatch.read(generation_file)
        if generation.route_limits.max_expansions != 8192:
            raise ValueError("本档实际共同ValueAnalysisLimits须为8192")
        candidate = load_vip_parents((package,), generation)[0]
        if (candidate["source_sha256"] != files[str(package / "candidate.py")]
                or candidate["record_sha256"] != files[str(package / "generation.json")]):
            raise ValueError("候选在公开摘要检查后发生字节漂移")
        _require_complete_behavior_difference(probe_file, candidate, generation, files,
                                             allow_mock_behavior_fixture=allow_mock_behavior_fixture,
                                             reference_policy=data.get("behavior_reference_policy"),
                                             exploration=data.get("behavior_exploration"),
                                             planned_table_instances=len(seeds) * len(pools) * 8,
                                             table_instance_limit=data["table_instance_limit"],
                                             batch_schema=data["schema"])
        return cls(data["batch_id"], generation_file, package, probe_file, tuple(seeds), tuple(pools),
                   data["table_instance_limit"], float(data["wall_clock_limit_seconds"]),
                   data["step_limit"], raw, files, capture)


def _require_complete_behavior_difference(
    probe_file, candidate, generation, frozen_files, *, allow_mock_behavior_fixture=False,
    reference_policy=None, exploration=None, planned_table_instances=None,
    table_instance_limit=None, batch_schema=VIP_DEVELOPMENT_BATCH_SCHEMA,
):
    """只读冻结探针门；同分尾序、仅分数或未完成比较不能投入完整桌。"""

    raw = probe_file.read_bytes()
    if _sha(raw) != frozen_files[str(probe_file)]:
        raise ValueError("行为探针在公开摘要检查后发生字节漂移")
    summary = json.loads(raw)
    if summary.get("schema") == "vip-eoh-development-probe/2":
        if batch_schema != VIP_DEVELOPMENT_CAPTURE_BATCH_SCHEMA:
            raise ValueError("/2真实来源探针须由显式/2开发批次声明参照及用途")
        from .vip_eoh_probe_v2 import validate_public_input_probe, validate_development_scope
        proof = validate_public_input_probe(probe_file, candidate, generation,
                                            reference_policy=reference_policy)
        validate_development_scope(proof, exploration, planned_table_instances, table_instance_limit)
        frozen_files.update(proof["frozen_files"])
        return
    if batch_schema != VIP_DEVELOPMENT_BATCH_SCHEMA:
        # 假驱动沿用显式结构fixture验证编排，不伪造一套真实/2来源。
        # 自然驱动从不开放此豁免，mock结果也不能取得自然积分信用。
        fixture_only = summary.get("fixture_kind") == "synthetic_structure_not_measured_behavior_for_mock_driver_only"
        if fixture_only and not allow_mock_behavior_fixture:
            raise ValueError("fixture只准假驱动，不能作为真实/2来源证明")
        if not (allow_mock_behavior_fixture and fixture_only):
            raise ValueError("/2开发批次不得借旧/1摘要冒充新来源证明")
    if (not isinstance(summary, dict) or summary.get("schema") != "vip-eoh-development-probe/1"
            or summary.get("status") != "probe_complete_not_admitted"
            or summary.get("identity_stable") is not True or summary.get("drift") != []
            or summary.get("development_only") is not True
            or any(summary.get(key) is not False for key in (
                "confirmation", "admitted", "complete_table_claim", "strength_claim", "release_claim"))):
        raise ValueError("行为探针须完整、未漂移且仅为未准入开发证据")
    windows, packages, comparisons = summary.get("window_count"), summary.get("packages"), summary.get("comparisons")
    if type(windows) is not int or windows <= 0 or not isinstance(packages, list) or not isinstance(comparisons, list):
        raise ValueError("行为探针缺完整窗口与包比较分母")
    expected = len(packages) * windows
    if (any(type(summary.get(key)) is not int or summary[key] != expected
            for key in ("planned_package_windows", "scored_package_windows"))
            or type(summary.get("unfinished_package_windows")) is not int
            or summary["unfinished_package_windows"] != 0):
        raise ValueError("行为探针的完整包乘窗口分母不一致或含未完成")
    fixture = summary.get("fixture_kind")
    if fixture is not None:
        if (not allow_mock_behavior_fixture
                or fixture != "synthetic_structure_not_measured_behavior_for_mock_driver_only"):
            raise ValueError("人工行为结构fixture只准假驱动，不得投入生产桌赛")
    else:
        if summary.get("batch_sha256") != _sha(generation.raw):
            raise ValueError("行为探针未绑定当前实际生成批次字节")
        producer = source_manifest(("hangma_bot.offline.vip_eoh_probe",))
        if summary.get("implementation_manifest") != producer:
            raise ValueError("行为探针生产源码与当前完整依赖闭包不一致")
        panel_name = summary.get("panel_path")
        if not isinstance(panel_name, str) or not panel_name:
            raise ValueError("行为探针缺实际面板路径")
        panel_path = (probe_file.parent / panel_name).resolve()
        if _sha(panel_path.read_bytes()) != summary.get("panel_sha256"):
            raise ValueError("行为探针面板字节摘要不匹配")
        # 公开验证器只重核原始观察、结果盲选择和来源字节，不重跑评分。
        from .vip_eoh_probe import validate_vip_eoh_panel
        checked = validate_vip_eoh_panel(panel_path)
        panel, panel_files = checked["panel"], checked["frozen_files"]
        if panel["window_count"] != windows:
            raise ValueError("行为探针与已重核面板窗口数不匹配")
        if summary.get("input_sha256s") != [w["input_sha256"] for w in panel["windows"]]:
            raise ValueError("行为探针窗口ID序列与已重核面板不匹配")
        frozen_files.update(panel_files)
        frozen_files.update({str(REPO_ROOT / path): value["sha256"] for path, value in producer.items()})
    by_index = {}
    for package in packages:
        if (not isinstance(package, dict) or type(package.get("index")) is not int
                or package["index"] < 0 or package["index"] in by_index):
            raise ValueError("行为探针包序号须唯一且非负")
        by_index[package["index"]] = package
    matches = [p for p in packages if p.get("role") == "candidate" and p.get("loaded") is True
               and p.get("identity") == candidate["identity"]
               and p.get("source_sha256") == candidate["source_sha256"]
               and p.get("record_sha256") == candidate["record_sha256"]]
    if len(matches) != 1:
        raise ValueError("行为探针未唯一绑定当前候选完整身份及两份原始件")
    candidate_index = matches[0]["index"]
    for comparison in comparisons:
        if (not isinstance(comparison, dict) or type(comparison.get("candidate_index")) is not int
                or comparison["candidate_index"] != candidate_index
                or type(comparison.get("parent_index")) is not int):
            continue
        parent = by_index.get(comparison["parent_index"])
        if not parent or parent.get("role") != "parent" or parent.get("loaded") is not True:
            continue
        if (comparison.get("comparison_complete") is not True
                or comparison.get("observed_behavior_difference") is not True
                or any(type(comparison.get(key)) is not int or comparison[key] != windows
                       for key in ("paired_scored_windows", "planned_windows"))
                or type(comparison.get("preferred_action_changed_windows")) is not int
                or not 0 < comparison["preferred_action_changed_windows"] <= windows
                or type(comparison.get("unfinished_windows")) is not int or comparison["unfinished_windows"] != 0):
            continue
        path = parent.get("path")
        if not isinstance(path, str) or not path:
            continue
        parent_path = (probe_file.parent / path).resolve()
        try:
            material = load_vip_parents((parent_path,), generation)[0]
        except (OSError, ValueError, WorkloadExceeded):
            continue
        if (parent.get("identity") != material["identity"]
                or parent.get("source_sha256") != material["source_sha256"]
                or parent.get("record_sha256") != material["record_sha256"]
                or material["identity"] == candidate["identity"]):
            continue
        frozen_files[str(parent_path / "candidate.py")] = material["source_sha256"]
        frozen_files[str(parent_path / "generation.json")] = material["record_sha256"]
        return
    raise ValueError("候选没有与当前合法父包完成全窗口且首选改变的行为比较")


@dataclass
class VipDevelopmentRuntime:
    """开发入口实际装配；冻结元数据直接对应以下实例，允许公开假驱动验证。"""

    rules: HangmaRules
    engine: SimulationEngine
    config: TournamentConfig
    policies_by_id: dict[str, Any]
    declarations: dict[str, PolicyDeclaration]
    policy_metadata: dict[str, Any]
    baseline_policy_id: str
    challenger_policy_id: str


def build_vip_development_runtime(
    generation_batch: VipEohBatch, candidate_source: str, *, clock: Callable[[], float] = lambda: 800.0,
) -> VipDevelopmentRuntime:
    """装配注册R18、完整V2和同bootstrap风险表的upgrade-v2；不使用线上发布包。"""

    config = TournamentConfig(1, 8, generation_batch.rule_config, TimingConfig(1, 1, 3))
    rules = HangmaRules(config.rules)
    engine = SimulationEngine(rules, rules_hash=compute_rules_hash(REPO_ROOT))
    scorer = build_research_candidate_scorer(R18_INTEGRATED_POSITIVE_V2_NAME)
    r18_manifest = source_manifest(("hangma_bot.policy.action_value_policy", "hangma_bot.policy.research_candidates"))
    r18 = {"registered_name": scorer.name, "source_sha256": _sha(scorer.source),
           "source_manifest": r18_manifest, "params": {}, "max_operations": scorer.max_operations,
           "rule_config": asdict(config.rules), "value_limits": asdict(generation_batch.route_limits),
           "provider": "registered_offline_research_not_live_release"}
    r18_id = _sha(json.dumps(r18, sort_keys=True, ensure_ascii=False, allow_nan=False))
    baseline_id, challenger_id = "research-r18-v2:" + r18_id, "vip:" + generation_batch.identity(candidate_source)["candidate_id"]
    declarations, policies, metadata = {}, {}, {}
    for label in ("A", "H1", "H2", "H3", "M1"):
        policy_id = baseline_id if label == "A" else label + ":" + r18_id
        declarations[label] = PolicyDeclaration(policy_id, R18_INTEGRATED_POSITIVE_V2_NAME)
        policies[policy_id] = ActionValuePolicy(build_research_candidate_scorer(scorer.name), value_limits=generation_batch.route_limits)
        metadata[label] = dict(r18, policy_id=policy_id)
    declarations["C"] = PolicyDeclaration(challenger_id, "vip_route_heuristic_v1")
    policies[challenger_id] = RouteVipHeuristicPolicy(config.rules, source=candidate_source,
        max_operations=generation_batch.max_operations, projection_limits=generation_batch.projection_limits)
    metadata["C"] = {"policy_id": challenger_id, "identity": generation_batch.identity(candidate_source)}
    for label, name, weights, factory in (("M2", "weighted_heuristic_v2", DEFAULT_WEIGHTS_V1, ComparableHeuristicPolicyV2),
                                         ("M3", "v2_hu_upgrade_v2", V2_PARAM_BATCH_WEIGHTS, V2HuUpgradePolicy)):
        params = {"weights": asdict(weights), "adjustments": []}
        if label == "M3":
            params.update(risk_cells=[asdict(c) for c in RISK_CELLS], risk_version=RISK_VERSION,
                          risk_ruleset_version=RISK_RULESET_VERSION, safety_margin=SAFETY_MARGIN, upgrade_weight=1.0)
        module = "hangma_bot.policy.heuristic_v2" if label == "M2" else "hangma_bot.policy.v2_hu_upgrade"
        provenance = {"name": name, "params": params, "source_manifest": source_manifest((module, "hangma_bot.policy.hu_upgrade_calibration"))}
        policy_id = label + ":" + _sha(json.dumps(provenance, sort_keys=True, ensure_ascii=False, allow_nan=False))
        declarations[label] = PolicyDeclaration(policy_id, name, tuple(sorted(asdict(weights).items())))
        policies[policy_id] = factory(weights=weights, monotonic=clock, **({
            "risk_cells": RISK_CELLS, "risk_version": RISK_VERSION, "safety_margin": SAFETY_MARGIN,
        } if label == "M3" else {}))
        metadata[label] = dict(provenance, policy_id=policy_id)
    return VipDevelopmentRuntime(rules, engine, config, policies, declarations, metadata, baseline_id, challenger_id)


class VipDevelopmentAuditEngine:
    """透传生产模拟器；仅经公开frame和export_hand_settlement读取已发生结算。"""

    def __init__(self, engine: SimulationEngine, *, settlement_sink: Callable[[dict], None] | None = None) -> None:
        self.engine = engine
        self.settlement_sink = settlement_sink or (lambda row: None)
        self.context: dict[str, Any] = {}
        self.started_table_instances = 0
        self.settlements: list[dict] = []
        self._completed = 0

    def start(self, spec):
        """先计入已尝试桌实例，再调用自然起手；完整世界保持不透明。"""
        self.started_table_instances += 1
        self.context = dict(self.context, match_id=spec.match_id, root_id=spec.scenario_id,
                            initial_dealer_physical=spec.initial_dealer)
        self._completed = 0
        return self.engine.start(spec)

    def frame(self, world):
        """每个已完成单局只导出一次；证据缺口记unknown，不猜赢家或胡型。"""
        frame = self.engine.frame(world)
        for round_no in range(self._completed + 1, frame.completed_hands + 1):
            row = {**self.context, "round_no": round_no, "observation_scope": "completed_hand_only"}
            try:
                row.update(evidence="public_export_hand_settlement", settlement=self.engine.export_hand_settlement(world, round_no))
            except Exception as exc:
                row.update(evidence="unknown", error=type(exc).__name__)
            self.settlements.append(row)
            self.settlement_sink(row)
        self._completed = frame.completed_hands
        return frame

    def advance(self, world, revision, choices):
        """原样传递动作推进，不强制未来摸牌。"""
        return self.engine.advance(world, revision, choices)


class _ScoringAudit:
    """记录同一实际typed view；完整图保存成功之后才调用真实执行器。"""

    def __init__(self, executor, capture: ScoringInputCapture):
        self.executor, self.capture = executor, capture
        self.last: dict | None = None
        self.decision_calls: list[dict] = []
        self.call_count = 0
        self.failed_calls = 0  # 累计失败永不由下一窗成功抹除
        self.audit_sink_failed_calls = 0

    def begin_decision(self):
        self.last, self.decision_calls = None, []

    @property
    def last_operation_count(self):
        return self.executor.last_operation_count

    @last_operation_count.setter
    def last_operation_count(self, value):
        self.executor.last_operation_count = value

    def score_vip_route(self, view):
        self.call_count += 1
        row = {"call_no": self.call_count, "status": "unfinished", "full_legal_keys": False,
            "actual_score_calls": 0, "score_completed": False, "input_capture": None,
            "candidate_operations": None, "score_monotonic_seconds": None,
            "future_qualification": "unknown_beyond_local_conditional_witness"}
        self.last = row
        self.decision_calls.append(row)
        capture_store_attempted = False
        try:
            # 实际typed view产生的同源DTO；不事后重建、不追加完整世界。
            dto = view.candidate_view()
            capture_store_attempted = True
            receipt = self.capture.store(dto)
            row["input_capture"] = asdict(receipt)
            if not receipt.saved_before_score:
                raise ValueError("实际评分输入捕获失败:" + str(receipt.error))
            roots = tuple(action["action_key"] for action in dto["actions"])
            self.executor.last_operation_count = None  # 本次失败不能沿用上一窗操作数
            row["actual_score_calls"] = 1
            score_started = time.monotonic()
            try:
                batch = self.executor.score_vip_route(view)
            finally:
                row["score_monotonic_seconds"] = time.monotonic() - score_started
            entry_keys = [e.action_key for e in batch.entries]
            row.update(status=batch.status, score_completed=True,
                full_legal_keys=batch.status == STATUS_SCORED and len(entry_keys) == len(roots)
                    and len(set(entry_keys)) == len(entry_keys) and set(roots) == set(entry_keys),
                scored_action_keys=entry_keys,
                unknown_nodes=[{"node_key": n.node_key, "kind": n.kind,
                    "unknown_codes": list(n.waiting.qualification_unknown_codes),
                    "unanalysed": n.waiting.legal_hu_draw_codes is None,
                    "reason": n.uncertainty_reason or n.waiting.qualification_missing_reason}
                    for n in view.nodes if n.waiting is not None and (
                        n.kind == "unknown_draw" or n.waiting.qualification_unknown_codes
                        or n.waiting.legal_hu_draw_codes is None)],
                waiting_draw_witness_count=view.waiting_draw_witness_count,
                target_distance_evaluation_count=view.target_distance_evaluation_count)
            if batch.status == STATUS_SCORED and not row["full_legal_keys"]:
                raise ValueError("实际评分没有逐根完整覆盖录制DTO")
            if batch.status != STATUS_SCORED:
                # 审计不能把原ABSTAIN改成SCORING_FAILED；原策略负责停止，失败仍入分母。
                self.failed_calls += 1
                row.update(score_completed=False, error="候选原返回状态:" + batch.status)
            return batch
        except BaseException as exc:
            self.failed_calls += 1
            if row["input_capture"] is None and capture_store_attempted:
                row["input_capture"] = self.capture.costs["last_store_failure"]
            if row["input_capture"] is None:
                row["input_capture"] = {"status": "candidate_view_failed", "view_sha256": None,
                    "json_bytes": None, "saved_before_score": False,
                    "error": type(exc).__name__ + ": " + str(exc)}
            row.update(status="failed", score_completed=False, full_legal_keys=False,
                error=type(exc).__name__ + ": " + str(exc))
            raise
        finally:
            # 捕获失败不读上一调用留下的操作数，也不宣称真正score已完成。
            if row["actual_score_calls"]:
                row["candidate_operations"] = self.executor.last_operation_count
            row["cumulative_failed_calls"] = self.failed_calls


class VipDevelopmentAuditPolicy:
    """行动前机会账与实际调用审计；对手和A不会被标为C自己评分。"""

    def __init__(self, inner, policy_id: str, context, sink, *, challenger=False, capture=None):
        self.inner, self.policy_id, self.context, self.sink = inner, policy_id, context, sink
        if challenger and capture is None:
            raise ValueError("C审计必须显式注入实际评分输入捕获器")
        self.scoring = _ScoringAudit(inner.executor, capture) if challenger else None
        if self.scoring is not None:
            inner.executor = self.scoring

    async def choose(self, request, budget):
        """读行动前请求和预算，原样返回计划；失败原样抛出，成功与失败均写审计。"""

        observation = request.observation
        keys = [c.action_key for c in request.rules.legal_candidates]
        hu = [c for c in request.rules.legal_candidates if c.action_key.split(":")[0] == "hu"]
        immediate = [c.value_facts.immediate_settlement if c.value_facts is not None else None for c in hu]
        row = {**self.context(), "policy_id": self.policy_id, "seat": observation.seat,
            "decision_id": request.decision_id, "window_key": window_key_to_json(request.window_key),
            "observation": observation_to_json(observation), "legal_action_keys": keys,
            "phase": request.window_key.phase, "white_count": sum(t.code == "白" for t in observation.my_hand)
                + int(observation.drawn_tile is not None and observation.drawn_tile.code == "白"),
            "action_families": sorted({key.split(":")[0] for key in keys}),
            "current_opportunity": {"scope": "current_legal_hu_only", "legal_hu": bool(hu),
                "immediate_fans": [None if s is None else s.fan for s in immediate],
                "fan_evidence": "same_source_immediate_settlement" if hu and all(s is not None for s in immediate) else "unknown_or_no_current_hu",
                "future_qualification": "unknown"}, "c_self_scored": False, "status": "unfinished"}
        if self.scoring is not None:
            self.scoring.begin_decision()
        started = time.perf_counter()
        try:
            plan = await self.inner.choose(request, budget)
            row.update(status="chosen", selected_action_key=plan.candidates[0].action_key,
                candidates=[{"rank": c.rank, "action_key": c.action_key, "score": c.total_score,
                             "trace": c.score_trace, "is_emergency": c.is_emergency} for c in plan.candidates],
                degraded_reasons=list(plan.degraded_reasons))
            if self.scoring is not None:
                row["c_self_scored"] = bool(self.scoring.decision_calls and all(
                    call["status"] == STATUS_SCORED and call["full_legal_keys"] and call["score_completed"]
                    and call["input_capture"]["saved_before_score"] for call in self.scoring.decision_calls))
                if not row["c_self_scored"]:
                    raise ValueError("C未以SCORED完整独立评分本窗口")
            return plan
        except BaseException as exc:
            row.update(status="failed", error=type(exc).__name__ + ": " + str(exc))
            raise
        finally:
            row["policy_compute_ms_observed"] = (time.perf_counter() - started) * 1000
            row["timing_scope"] = "policy_choose_with_input_capture_observed_not_official_runtime"
            if self.scoring is not None:
                row["candidate_operations"] = None if self.scoring.last is None else self.scoring.last["candidate_operations"]
                row["scoring_execution"] = self.scoring.last
                row["scoring_calls"] = list(self.scoring.decision_calls)
                row["scoring_cumulative_failed_calls"] = self.scoring.failed_calls
            primary = sys.exc_info()[1]
            try:
                self.sink(row)
            except BaseException as secondary:
                row["audit_write_error"] = type(secondary).__name__ + ": " + str(secondary)
                if self.scoring is not None:
                    self.scoring.audit_sink_failed_calls += 1
                if primary is None:
                    raise
                primary.add_note("决策小收据写入再次失败:" + row["audit_write_error"])


def _pool_summary(frame, results, outcomes, runtime, additional_issues, *, source_kind):
    issues = list(additional_issues)
    try:
        audit = audit_vip_batch(frame, {"all_natural": 1.0}, results,
            baseline_policy_id=runtime.baseline_policy_id, challenger_policy_id=runtime.challenger_policy_id)
    except ValueError as exc:
        # 原始结果已归档；多行、重复或越框同样不允许借异常遗漏整池分母。
        return {"planned_rows": len(frame) * 8, "observed_rows": len(results), "audit": None,
                "extra_failures": issues + ["完整桌核验失败:" + str(exc)],
                "estimate_natural_score_delta": None, "root_deltas": [],
                "positive_tail": [], "negative_tail": [], "development_complete": False}
    for match_id, outcome in outcomes:
        if any("action_value_failed" in reason for d in outcome.decisions for reason in d.degraded_reasons):
            issues.append("内部R18评分回退:" + match_id)
        counts = outcome.runtime_counts
        if (outcome.status != "complete" or any(getattr(counts, key) is None or getattr(counts, key) != 0
                for key in ("timeouts", "illegal_choices", "fallbacks", "auto_actions", "audit_missing"))):
            issues.append("桌未完成或运行计数非全零:" + match_id)
    if source_kind != "simulation":
        issues.append("假驱动只验编排，无自然积分信用")
    usable = audit.confirmable and not issues
    deltas = [{"root_id": root.root_id, "four_seat_deltas": root.deltas,
               "root_mean_delta": None if root.deltas is None else sum(root.deltas) / 4,
               "issues": list(root.issues)} for root in audit.roots]
    return {"planned_rows": len(frame) * 8, "observed_rows": len(results), "audit": asdict(audit),
        "extra_failures": issues, "estimate_natural_score_delta": audit.natural_score_delta if usable else None,
        "root_deltas": deltas, "positive_tail": [r for r in deltas if r["root_mean_delta"] > 0] if usable else [],
        "negative_tail": [r for r in deltas if r["root_mean_delta"] < 0] if usable else [],
        "development_complete": usable}


async def run_vip_route_development(
    batch_file: Path, out_dir: Path, *, match_runner=run_match_experiment,
) -> dict[str, Any]:
    """按预登记预算运行开发完整桌；异常和缺行留分母，禁止覆盖、自动续批或发布。

    match_runner 是已有真实实现的公开故障注入点；传入替代实现则产物来源
    固定 mock。墙钟预算在桌组之间阻止启动新桌，超限观察令估计为空；
    不声称能抢占Python同步评分，也不以逻辑时钟证明线上一秒门。
    """

    started = time.perf_counter()
    source_kind = "simulation" if match_runner is run_match_experiment else "mock"
    batch = VipDevelopmentBatch.read(batch_file, allow_mock_behavior_fixture=source_kind == "mock")
    if batch.scoring_input_capture is None:
        raise ValueError("batch/1仅供历史读取；新开发运行必须用batch/2显式冻结捕获预算")
    generation = VipEohBatch.read(batch.generation_batch_file)
    parent = load_vip_parents((batch.candidate_package,), generation)[0]
    source, identity = parent["source"], parent["identity"]
    runtime = build_vip_development_runtime(generation, source)
    out_dir.mkdir(parents=True, exist_ok=False)
    manifest = source_manifest(VIP_DEVELOPMENT_ROOTS)
    manifest.update(identity["source_manifest"])
    script = "scripts/vip_route_development.py"
    if (REPO_ROOT / script).exists():
        manifest[script] = digest_of_file(REPO_ROOT / script)
    write_code_snapshot(out_dir, manifest)
    (out_dir / "candidate.py").write_text(source, encoding="utf-8")
    (out_dir / "r18.py").write_text(build_research_candidate_scorer(R18_INTEGRATED_POSITIVE_V2_NAME).source, encoding="utf-8")
    (out_dir / "batch.json").write_bytes(batch.raw)
    (out_dir / "generation-batch.json").write_bytes(generation.raw)
    (out_dir / "behavior-probe-summary.json").write_bytes(batch.behavior_probe_summary_file.read_bytes())
    (out_dir / "candidate-generation.json").write_bytes((batch.candidate_package / "generation.json").read_bytes())
    (out_dir / "contract.md").write_bytes(project_file(REPO_ROOT, identity["contract_path"]).read_bytes())
    native_path = backend_info()["native_path"]
    if native_path is not None:
        (out_dir / "math-native.bin").write_bytes(Path(native_path).read_bytes())
    planned = len(batch.seeds) * len(batch.pools) * 8
    prereg = {"schema": "vip-route-development-manifest/2", "batch_id": batch.batch_id,
        "development_only": True, "confirmation_claim": False, "published": False,
        "single_development_view": True, "source_kind": source_kind,
        "batch_sha256": _sha(batch.raw), "frozen_files": dict(batch.frozen_files),
        "candidate_identity": identity, "source_manifest": manifest, "config": asdict(runtime.config),
        "policy_metadata": runtime.policy_metadata, "pool_ids": {p: NEW_POOL_IDS[p] for p in batch.pools},
        "planned_table_instances": planned, "limits": {"table_instances": batch.table_instance_limit,
            "wall_clock_seconds": batch.wall_clock_limit_seconds, "step_limit": batch.step_limit},
        "strict_challenger": True, "value_limits": asdict(generation.route_limits),
        "clock_mode": "logical", "initial_dealer_physical": 0, "initial_scores_physical": [0] * 4,
        "selection_probabilities": {"all_natural": 1.0}, "frame": [asdict(r) for r, _ in batch.seeds],
        "environment": {"python": platform.python_version(), "platform": platform.platform()},
        "opportunity_scope": "current_legal_hu_and_immediate_fan_only_future_unknown",
        "scoring_input_capture": {"schema": "vip-scoring-input-capture/1", "path": "views.jsonl.gz",
            "scope": "same_actual_C_typed_view_candidate_view_before_each_score",
            "limits": asdict(batch.scoring_input_capture), "terminal_verification": "pending",
            "deduplication": "whole_canonical_DTO_sha256", "WorldState_added": False}}
    _write(out_dir / "manifest.json", prereg)
    charges, pool_results, all_decisions, scoring_audits = [], {}, [], []
    capture_stream = (out_dir / "views.jsonl.gz").open("x+b")
    capture = ScoringInputCapture(capture_stream, limits=batch.scoring_input_capture)
    try:
        _write(out_dir / "costs.json", {"planned_table_instances": planned, "entries": charges, "scoring_input_capture": capture.costs})
        for pool in batch.pools:
            pool_dir = out_dir / pool
            pool_dir.mkdir()
            results, outcomes, issues, opportunity_rows = [], [], [], []
            with _close_preserving_primary(gzip.open(pool_dir / "decisions.jsonl.gz", "wt", encoding="utf-8")) as stream, \
                    _close_preserving_primary((pool_dir / "settlements.jsonl").open("w", encoding="utf-8")) as settlements:
                def settlement_sink(row):
                    settlements.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
                    settlements.flush()
                engine = VipDevelopmentAuditEngine(runtime.engine, settlement_sink=settlement_sink)
                def sink(row):
                    stream.write(json.dumps(row, ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n")
                    stream.flush()
                    opportunity_rows.append({key: row[key] for key in ("match_id", "seat", "policy_id", "phase", "white_count", "action_families", "current_opportunity", "c_self_scored", "status")})
                    all_decisions.append({key: row[key] for key in ("policy_id", "phase", "white_count", "action_families", "c_self_scored", "status", "policy_compute_ms_observed")})
                    if row["policy_id"] == runtime.challenger_policy_id and not row["c_self_scored"]:
                        issues.append("C窗口未独立完整评分:" + row["decision_id"])
                    if any("action_value_failed" in reason for reason in row.get("degraded_reasons", ())):
                        issues.append("内部R18评分回退:" + row["decision_id"])
                # 每池独立实例，避免上一池评分观察器或未来可变策略状态进入下一池。
                pool_runtime = build_vip_development_runtime(generation, source)
                policies = {key: VipDevelopmentAuditPolicy(value, key, lambda: dict(engine.context), sink,
                    challenger=key == runtime.challenger_policy_id, capture=capture) for key, value in pool_runtime.policies_by_id.items()}
                scoring_audits.extend(policy.scoring for policy in policies.values() if policy.scoring is not None)
                for root, seed in batch.seeds:
                    for permutation in root.permutations:
                        if time.perf_counter() - started >= batch.wall_clock_limit_seconds:
                            issues.append("批次墙钟预算耗尽，未启动:" + root.root_id + ":" + "".join(map(str, permutation)))
                            continue
                        if sum(r["charged_table_instances"] for r in charges) + 2 > batch.table_instance_limit:
                            issues.append("桌实例预算耗尽，未启动:" + root.root_id + ":" + "".join(map(str, permutation)))
                            continue
                        label = "".join(map(str, permutation))
                        prefix = f"{batch.batch_id}:{pool}"
                        engine.context = {"pool": pool, "new_pool_id": NEW_POOL_IDS[pool],
                            "root_id": root.root_id, "permutation": list(permutation), "focal_physical_seat": permutation[0],
                            "initial_dealer_logical": permutation.index(0), "initial_dealer_physical": 0}
                        entry = {"pool": pool, "root_id": root.root_id, "permutation": list(permutation),
                            "initial_dealer_logical": permutation.index(0), "initial_dealer_physical": 0,
                            "status": "reserved", "reserved_table_instances": 2, "charged_table_instances": 2,
                            "duration_wall_seconds": None, "actual_started_table_instances": None}
                        charges.append(entry)
                        _write(out_dir / "costs.json", {"planned_table_instances": planned, "entries": charges, "scoring_input_capture": capture.costs})
                        group_started, count_before = time.perf_counter(), engine.started_table_instances
                        experiment = MatchExperiment("matches", "logical", runtime.declarations["A"], runtime.declarations["C"],
                            tuple(runtime.declarations[p] for p in (("H1", "H2", "H3") if pool == "H" else ("M1", "M2", "M3"))),
                            runtime.config, (MatchSeedSpec(seed, root.root_id),), (permutation,), permutation.index(0), (0, 0, 0, 0),
                            step_limit=batch.step_limit, match_id_prefix=prefix, simulation_version=WORLD_SCHEMA,
                            input_sha256=_sha(batch.raw), source_namespace="hangma-simulation")
                        try:
                            outcome = await match_runner(experiment, engine=engine, spec_factory=MatchSpec,
                                choice_factory=lambda key, action: SimulationChoice(key, action), policies_by_id=policies,
                                rules=runtime.rules, rules_hash=compute_rules_hash(REPO_ROOT), now_monotonic=lambda: 800.0,
                                wall_clock=None, budget_policy=BudgetPolicy(), source_kind=source_kind,
                                value_limits=generation.route_limits, challenger_route_limits=generation.route_limits,
                                strict_challenger=True)
                            results.extend(outcome.results)
                            outcomes.extend(outcome.match_records)
                            issues.extend(outcome.excluded)
                            _write(pool_dir / f"group-{_sha(root.root_id)[:16]}-{label}.json", {
                                "experiment": asdict(experiment), "results": [r.to_json() for r in outcome.results],
                                "match_records": [{"match_id": key, "outcome": value.to_json()} for key, value in outcome.match_records],
                                "excluded": list(outcome.excluded)})
                            entry["status"] = "settled"
                        except (Exception, WorkloadExceeded) as exc:
                            entry.update(status="failed_cost_retained", error=type(exc).__name__ + ": " + str(exc))
                            issues.append("桌组异常:" + root.root_id + ":" + label + ":" + type(exc).__name__)
                        except BaseException as exc:
                            entry.update(status="interrupted_cost_retained", error=type(exc).__name__ + ": " + str(exc))
                            raise  # 记下原分母与未完成调用，用户中断不启动后续桌
                        finally:
                            entry["actual_started_table_instances"] = engine.started_table_instances - count_before
                            if entry["actual_started_table_instances"] > 2:
                                entry["charged_table_instances"] = entry["actual_started_table_instances"]
                                issues.append("驱动超出预留桌实例:" + root.root_id + ":" + label)
                            entry["duration_wall_seconds"] = time.perf_counter() - group_started
                            primary = sys.exc_info()[1]
                            try:
                                _write(out_dir / "costs.json", {"planned_table_instances": planned, "entries": charges, "scoring_input_capture": capture.costs})
                            except BaseException as secondary:
                                if primary is None:
                                    raise
                                primary.add_note("桌组费用小收据再次失败:" + type(secondary).__name__ + ": " + str(secondary))
                _write(pool_dir / "current-opportunity-ledger.json", {"scope": prereg["opportunity_scope"],
                    "decision_window_denominator": len(opportunity_rows), "rows": opportunity_rows,
                    "focal_windows_by_arm": {arm: sum(row["policy_id"] == policy_id for row in opportunity_rows)
                        for arm, policy_id in (("A", runtime.baseline_policy_id), ("C", runtime.challenger_policy_id))},
                    "no_hindsight_labels": True})
                natural = summarize_vip_natural_settlements(engine.settlements,
                    challenger_policy_id=runtime.challenger_policy_id,
                    planned_hands_by_arm={"A": len(batch.seeds) * 4 * 8, "C": len(batch.seeds) * 4 * 8})
                _write(pool_dir / "natural-settlement-ledger.json", natural)
            with (pool_dir / "results.jsonl").open("w", encoding="utf-8") as stream:
                for row in results:
                    stream.write(json.dumps(row.to_json(), ensure_ascii=False, sort_keys=True) + "\n")
            _write(pool_dir / "match-outcomes.json", [{"match_id": key, "outcome": value.to_json()} for key, value in outcomes])
            pool_results[pool] = _pool_summary([r for r, _ in batch.seeds], results, outcomes, runtime, issues, source_kind=source_kind)
    finally:
        # 原中断优先；关闭/费用落盘的第二故障只加说明，不吞原异常或继续桌。
        primary, cleanup_error = sys.exc_info()[1], None
        capture_final = capture.costs
        try:
            capture_final = capture.finish()
        except BaseException as exc:
            cleanup_error = exc
            capture_final = capture.costs
        terminal = dict(capture_final["terminal"], storage_valid=capture_final["terminal"]["terminal_valid"],
            errors=list(capture_final["terminal"].get("errors", ())),
            scoring_audit_failed_calls=sum(audit.failed_calls for audit in scoring_audits),
            decision_audit_sink_failed_calls=sum(audit.audit_sink_failed_calls for audit in scoring_audits))
        terminal["terminal_valid"] = (terminal["storage_valid"] and terminal["scoring_audit_failed_calls"] == 0
            and terminal["decision_audit_sink_failed_calls"] == 0 and primary is None and cleanup_error is None)
        if primary is not None:
            terminal["pending_run_exception"] = type(primary).__name__ + ": " + str(primary)
        try:
            capture_stream.close()
            terminal["binary_stream_closed"] = True
        except BaseException as exc:
            terminal.update(terminal_valid=False, closed=False, binary_stream_closed=False)
            terminal["errors"].append("底层stream关闭失败:" + type(exc).__name__ + ": " + str(exc))
            if cleanup_error is None:
                cleanup_error = exc
        capture_final = dict(capture_final, terminal=terminal)
        prereg["scoring_input_capture"]["terminal_verification"] = terminal
        for path, value in ((out_dir / "costs.json", {"planned_table_instances": planned,
                                "entries": charges, "scoring_input_capture": capture_final}),
                            (out_dir / "manifest.json", prereg)):
            try:
                _write(path, value)
            except BaseException as exc:
                terminal["terminal_valid"] = False
                terminal["errors"].append("终态小收据落盘失败:" + type(exc).__name__ + ": " + str(exc))
                if cleanup_error is None:
                    cleanup_error = exc
        if primary is not None and cleanup_error is not None:
            primary.add_note("录制终态清理再次失败:" + type(cleanup_error).__name__ + ": " + str(cleanup_error))
        if primary is None and cleanup_error is not None:
            raise cleanup_error
    if not capture_final["terminal"]["terminal_valid"]:
        for pool in pool_results.values():
            pool["estimate_natural_score_delta"] = None
            pool["positive_tail"], pool["negative_tail"], pool["development_complete"] = [], [], False
            pool["extra_failures"].append("实际评分输入捕获不完整或终态关闭未验证")
    stable, drift_error, end_identity = True, None, None
    try:
        final_parent = load_vip_parents((batch.candidate_package,), VipEohBatch.read(batch.generation_batch_file))[0]
        end_manifest = source_manifest(VIP_DEVELOPMENT_ROOTS)
        end_identity = generation.identity(source)
        end_manifest.update(end_identity["source_manifest"])
        if (REPO_ROOT / script).exists():
            end_manifest[script] = digest_of_file(REPO_ROOT / script)
        stable = (identity == final_parent["identity"] and manifest == end_manifest
                  and all(_sha(Path(path).read_bytes()) == expected for path, expected in batch.frozen_files.items()))
    except Exception as exc:
        stable, drift_error = False, type(exc).__name__
        end_manifest = None
    duration = time.perf_counter() - started
    if not stable or duration > batch.wall_clock_limit_seconds:
        for pool in pool_results.values():
            pool["estimate_natural_score_delta"] = None
            pool["positive_tail"], pool["negative_tail"], pool["development_complete"] = [], [], False
            pool["extra_failures"].append("冻结身份漂移" if not stable else "批次墙钟预算超限")
    strata = Counter((r["phase"], r["white_count"], tuple(r["action_families"]), r["c_self_scored"], r["status"]) for r in all_decisions)
    summary = {"schema": "vip-route-development-result/2", "batch_id": batch.batch_id,
        "status": "development_complete_not_confirmed" if stable and all(p["development_complete"] for p in pool_results.values()) else "unfinished_or_invalid_development",
        "identity_stable": stable, "drift_error": drift_error, "development_only": True,
        "confirmation_claim": False, "published": False, "source_kind": source_kind,
        "planned_table_instances": planned, "charged_table_instances": sum(r["charged_table_instances"] for r in charges),
        "duration_wall_seconds": duration, "pools": pool_results,
        "decision_strata": [{"phase": key[0], "white_count": key[1], "action_families": list(key[2]),
                             "c_self_scored": key[3], "status": key[4], "windows": count} for key, count in sorted(strata.items())],
        "timing_scope": "policy_choose_with_input_capture_observed_not_official_runtime",
        "max_policy_compute_ms_observed": max((r["policy_compute_ms_observed"] for r in all_decisions), default=None),
        "scoring_input_capture": capture_final}
    _write(out_dir / "end-freeze.json", {"identity_stable": stable, "source_manifest": end_manifest,
                                        "candidate_identity": end_identity, "end_error": drift_error,
                                        "scoring_input_capture_terminal": capture_final["terminal"]})
    _write(out_dir / "summary.json", summary)
    return summary


def summarize_vip_natural_settlements(
    rows, *, challenger_policy_id: str, planned_hands_by_arm: Mapping[str, int],
):
    """汇总公开已发生结算；保留完整计划单局分母，未知证据不填零或倒填机会。"""

    counts: dict[str, Counter] = {"A": Counter(), "C": Counter()}
    for row in rows:
        arm = "C" if row["match_id"].endswith(":" + challenger_policy_id) else "A"
        counts[arm]["observed_completed_hands"] += 1
        settlement = row.get("settlement")
        if (not settlement or row.get("evidence") != "public_export_hand_settlement"
                or settlement.get("coverage") != "settlement_only"):
            counts[arm]["unknown_settlement"] += 1
            continue
        winner, fan = settlement.get("winner_seat"), settlement.get("fan")
        if settlement.get("is_draw") is True:
            counts[arm]["draw"] += 1
        elif winner == row["focal_physical_seat"]:
            if type(fan) is not int or fan <= 0:
                counts[arm]["unknown_settlement"] += 1
            else:
                counts[arm]["focal_hu"] += 1
                counts[arm]["focal_ordinary_lt4"] += int(fan < 4)
                counts[arm]["focal_ge4"] += int(fan >= 4)
                counts[arm]["focal_ge8"] += int(fan >= 8)
        elif type(winner) is int and winner in range(4):
            counts[arm]["opponent_first_hu"] += 1
        else:
            counts[arm]["unknown_settlement"] += 1
    return {"scope": "natural_observed_completed_hands_not_opportunity_predicates",
            "seat_order": [0, 1, 2, 3], "counts_by_arm": {k: dict(v) for k, v in counts.items()},
            "planned_hands_by_arm": dict(planned_hands_by_arm),
            "rows": rows, "unknown_is_not_zero": True, "chain_success_label": "unknown_not_inferred"}
