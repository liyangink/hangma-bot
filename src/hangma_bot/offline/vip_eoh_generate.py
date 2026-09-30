"""VIP EoH 五算子的独立提案生成档；不运行桌赛、不准入、不发布。

复用旧工具的调用、回复封套、解析和脱敏入口；候选与父代身份只使用
``freeze_vip_identity``。本档自己的预算与多父谱系不借用旧 runner。
预留先原子落盘，凭据只在 API 分支预留完成后读取。未结算调用禁止重发。
"""

from __future__ import annotations

import ast
import datetime
import fcntl
import hashlib
import importlib.util
import inspect
import json
import math
import multiprocessing
import os
import re
import signal
import sys
import time
import uuid
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from hangma_bot.hangma.route_structure import RouteStructureFacts, RouteStructureTarget
from hangma_bot.hangma.interface import ValueAnalysisLimits
from hangma_bot.kernel.config import RuleConfig
from hangma_bot.policy.action_value import ActionScore, ScoreBatch
from hangma_bot.policy.action_value_executor import (
    ALLOWED_BUILTINS, ALLOWED_METHODS, EXECUTOR_VERSION, MAX_LOCAL_COLLECTION_SIZE,
    MAX_SOURCE_BYTES, MAX_TRACE_BYTES, ActionValueExecutor,
)
from hangma_bot.policy.route_heuristic_view import (
    VIP_ROUTE_CANDIDATE_KIND, VIP_ROUTE_SCORING_VIEW_SCHEMA_VERSION,
    RouteHeuristicAction, RouteHeuristicNode, RouteWaitingView, VipRouteScoringView,
)
from hangma_bot.policy.route_vip_heuristic import (
    VIP_ROUTE_HEURISTIC_SEED_SOURCE, VipRouteProjectionLimits,
)

from .scoring_sources import REPO_ROOT, digest_of_file, source_manifest, write_code_snapshot
from .vip_heuristic_smoke import freeze_vip_identity

VIP_EOH_PROFILE = "vip-route-eoh/1"
VIP_EOH_GENERATION_SCHEMA = "vip-route-eoh-generation/1"
VIP_EOH_BATCH_SCHEMA = "vip-route-eoh-batch/1"
VIP_EOH_LEDGER_SCHEMA = "vip-route-eoh-budget-ledger/1"
OPERATORS = ("i1", "e1", "e2", "m1", "m2")
ACCOUNTS = ("model_calls", "input_tokens", "output_tokens", "table_instances", "wall_clock_seconds")
_TOOLS = REPO_ROOT / "review/llm-guided-heuristic-route-2026-09-15/tools"
_MECHANISM_FIELDS = {
    "operator", "trigger", "changed_branches", "expected_direction", "counterexample",
    "parent_differences", "parameter_changes",
}


class VipEohError(ValueError):
    """生成材料、父代、预算或恢复合同不满足；不会切换后端重试。"""


class VipEohCallError(VipEohError):
    """隔离调用失败的有限脱敏分类；不携带响应正文、URL或凭据对象。"""

    def __init__(self, diagnostics: Mapping[str, Any]) -> None:
        self.diagnostics = dict(diagnostics)
        super().__init__(self.diagnostics["reason"])


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True,
                       allow_nan=False) + "\n").encode("utf-8")


def _sha(data: bytes | str) -> str:
    return hashlib.sha256(data.encode("utf-8") if isinstance(data, str) else data).hexdigest()


def _utc() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")


def _atomic(path: Path, data: bytes) -> None:
    """同目录临时文件、fsync和原子替换；只覆盖本次独立账本/记录。"""

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp-" + uuid.uuid4().hex)
    try:
        with temporary.open("xb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        # rename的目录项也须持久化；机器中断后仍能证明先预留后调用。
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        temporary.unlink(missing_ok=True)


@lru_cache(maxsize=1)
def legacy_generation_tools():
    """只装载已有工具定义；不调用旧runner、不收集凭据或实例化后端。"""

    name = "_vip_eoh_legacy_generation_tools"
    spec = importlib.util.spec_from_file_location(name, _TOOLS / "sitin_generate.py")
    if spec is None or spec.loader is None:
        raise VipEohError("旧生成底层工具不可装载")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _positive(value: Any, name: str, *, integer=False, zero=False) -> None:
    if (isinstance(value, bool) or not isinstance(value, (int, float))
            or not math.isfinite(value) or value < 0 or (not zero and value == 0)
            or integer and type(value) is not int):
        raise VipEohError(name + "必须是" + ("非负" if zero else "正") + "有限数，计数须为整数")


@dataclass(frozen=True)
class VipEohBatch:
    """本批冻结上限；token单位个、调用单位次、墙钟持续时间单位秒。"""

    batch_id: str
    budgets: Mapping[str, int | float]
    input_tokens_per_call: int  # 保守预留，不宣称是精确tokenizer结果
    max_tokens_per_call: int  # 实际请求max_tokens，也是输出预留上限
    timeout_seconds: float  # API单次超时及墙钟预留；外层持续时间用单调时钟
    max_operations: int
    projection_limits: VipRouteProjectionLimits
    rule_config: RuleConfig  # 实际目标规则；不得借默认值沿用另一规则的父代
    route_limits: ValueAnalysisLimits  # 实际规则分析额度，与后续研究驱动共用
    input_bound: Mapping[str, Any] | None  # 已核模型输入上限；未知只允许emit/replay
    sampling: Mapping[str, Any]
    raw: bytes  # 原始冻结配置字节，不含凭据

    @classmethod
    def read(cls, path: Path) -> "VipEohBatch":
        """读公开预算配置；缺字段、未知账户或本档非零桌赛预算直接拒绝。"""

        raw = Path(path).read_bytes()
        data = json.loads(raw)
        if not isinstance(data, dict) or set(data) != {
            "schema", "batch_id", "budgets", "per_call", "max_operations",
            "projection_limits", "rule_config", "route_limits", "input_bound", "sampling"}:
            raise VipEohError("公开批次字段不完整或含未知字段；凭据应单独配置")
        if data.get("schema") != VIP_EOH_BATCH_SCHEMA or not isinstance(data.get("batch_id"), str) or not data["batch_id"]:
            raise VipEohError("批次schema或batch_id不合法")
        budgets = data.get("budgets")
        if not isinstance(budgets, dict) or set(budgets) != set(ACCOUNTS):
            raise VipEohError("批次须冻结全部五个独立账户")
        for account, value in budgets.items():
            _positive(value, account, integer=account != "wall_clock_seconds", zero=True)
        if budgets["table_instances"] != 0:
            raise VipEohError("此生成profile桌赛预算必须为0")
        call = data.get("per_call", {})
        for name in ("input_tokens", "max_tokens"):
            _positive(call.get(name), name, integer=True)
        _positive(call.get("timeout_seconds"), "timeout_seconds")
        _positive(data.get("max_operations"), "max_operations", integer=True)
        limits = VipRouteProjectionLimits(**data.get("projection_limits", {}))
        if (not isinstance(data["rule_config"], dict)
                or set(data["rule_config"]) != {"ruleset_version", "base_score", "you_cai_bi_kao"}
                or not isinstance(data["route_limits"], dict)
                or set(data["route_limits"]) != {"max_expansions", "max_routes_per_candidate"}):
            raise VipEohError("须冻结实际完整RuleConfig和ValueAnalysisLimits")
        rule_config = RuleConfig(**data["rule_config"])
        route_limits = ValueAnalysisLimits(**data["route_limits"])
        bound = data["input_bound"]
        if bound is not None:
            if (not isinstance(bound, dict) or set(bound) != {"kind", "model", "max_input_tokens", "evidence"}
                    or bound["kind"] != "verified_model_input_limit"
                    or not isinstance(bound["model"], str) or not bound["model"].strip()):
                raise VipEohError("input_bound须完整冻结已核模型输入上限")
            _positive(bound["max_input_tokens"], "input_bound.max_input_tokens", integer=True)
            evidence = bound["evidence"]
            if (not isinstance(evidence, dict) or set(evidence) != {"sources", "verified_on", "interpretation"}
                    or not isinstance(evidence["sources"], list) or not evidence["sources"]
                    or any(not isinstance(item, str) or not item.strip() for item in evidence["sources"])
                    or any(not isinstance(evidence[name], str) or not evidence[name].strip()
                           for name in ("verified_on", "interpretation"))):
                raise VipEohError("input_bound证据须保留来源、核验日期与工程预留解释")
        sampling = data.get("sampling", {"temperature": None, "top_p": None, "seed": None})
        if not isinstance(sampling, dict) or set(sampling) != {"temperature", "top_p", "seed"}:
            raise VipEohError("sampling仅允许temperature/top_p/seed")
        for name in ("temperature", "top_p"):
            value = sampling[name]
            if value is not None:
                _positive(value, name, zero=True)
        if sampling["seed"] is not None:
            _positive(sampling["seed"], "sampling.seed", integer=True, zero=True)
        return cls(data["batch_id"], budgets, call["input_tokens"], call["max_tokens"],
                   call["timeout_seconds"], data["max_operations"], limits,
                   rule_config, route_limits, bound, sampling, raw)

    def identity(self, source: str) -> dict[str, Any]:
        """生成、父代验证、恢复与后续评测共用当前唯一身份封装。"""

        return freeze_vip_identity(source, max_operations=self.max_operations,
                                   projection_limits=self.projection_limits,
                                   rule_config=self.rule_config, route_limits=self.route_limits)


class VipEohLedger:
    """独立五账户原子账本；互斥重读、不清除失败费用、不自动恢复调用。"""

    def __init__(self, batch_file: Path, batch: VipEohBatch) -> None:
        self.path = Path(batch_file).with_suffix(".vip-eoh-ledger.json")
        self.batch = batch

    @contextmanager
    def _locked(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.with_suffix(self.path.suffix + ".lock").open("a+") as stream:
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
            try:
                if self.path.exists():
                    data = json.loads(self.path.read_bytes())
                    if (data.get("schema") != VIP_EOH_LEDGER_SCHEMA
                            or data.get("batch_sha256") != _sha(self.batch.raw)
                            or not isinstance(data.get("reservations"), list)):
                        raise VipEohError("账本与本批原始预算字节不一致或账本损坏")
                else:
                    data = {"schema": VIP_EOH_LEDGER_SCHEMA, "batch_id": self.batch.batch_id,
                            "batch_sha256": _sha(self.batch.raw), "budgets": dict(self.batch.budgets),
                            "reservations": []}
                yield data
            finally:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)

    def reserve(self, attempt_id: str, backend: str) -> dict[str, Any]:
        """预留落盘后才可读API凭据；任何旧在途调用须先人工审核结算。"""

        if backend not in ("emit", "replay", "api") or not isinstance(attempt_id, str) or not attempt_id:
            raise VipEohError("预留须有独立尝试ID与本profile后端")
        amounts = {"model_calls": int(backend == "api"),
                   "input_tokens": self.batch.input_tokens_per_call if backend == "api" else 0,
                   "output_tokens": self.batch.max_tokens_per_call if backend == "api" else 0,
                   "table_instances": 0, "wall_clock_seconds": self.batch.timeout_seconds}
        with self._locked() as data:
            if any(row["status"] == "reserved" for row in data["reservations"]):
                raise VipEohError("本批有未结算调用；只能人工审核显式结算，禁止自动重发")
            if any(row["attempt_id"] == attempt_id for row in data["reservations"]):
                raise VipEohError("同一attempt_id不得重复预留")
            for account, amount in amounts.items():
                used = sum(row["charged"][account] for row in data["reservations"])
                if used + amount > self.batch.budgets[account]:
                    raise VipEohError("冻结预算不足: " + account)
            row = {"attempt_id": attempt_id, "attempt_no": len(data["reservations"]) + 1,
                   "backend": backend, "status": "reserved", "reserved": amounts,
                   "charged": dict(amounts), "actual": None, "call_started": False,
                   "reserved_at_utc": _utc()}
            data["reservations"].append(row)
            _atomic(self.path, _json_bytes(data))
            return dict(row)

    def mark_call_started(self, attempt_id: str) -> None:
        """请求前落盘发起标记；网络结果未知也不能当成免费或可重发。"""

        with self._locked() as data:
            row = self._row(data, attempt_id)
            if row["status"] != "reserved" or row["call_started"]:
                raise VipEohError("调用已发起或已结算，拒绝再次发起")
            if row["backend"] != "api":
                raise VipEohError("只有API预留可以标为模型调用已发起")
            row["call_started"] = True
            row["started_at_utc"] = _utc()
            _atomic(self.path, _json_bytes(data))

    @staticmethod
    def _row(data, attempt_id):
        row = next((row for row in data["reservations"] if row["attempt_id"] == attempt_id), None)
        if row is None:
            raise VipEohError("未知调用预留")
        return row

    def settle(self, attempt_id: str, *, actual: Mapping[str, Any], outcome: str,
               reviewed_recovery: str | None = None) -> dict[str, Any]:
        """逐账户未知值保留预留收费；人工恢复只结算原调用，绝不执行重试。"""

        if set(actual) != set(ACCOUNTS):
            raise VipEohError("结算必须逐一说明五个账户，未知用None")
        for name, value in actual.items():
            if value is not None:
                _positive(value, name, integer=name != "wall_clock_seconds", zero=True)
        with self._locked() as data:
            row = self._row(data, attempt_id)
            if row["status"] != "reserved":
                raise VipEohError("原调用已结算，禁止覆盖费用")
            if reviewed_recovery is not None and not reviewed_recovery.strip():
                raise VipEohError("人工恢复须写明审核依据")
            if row["call_started"] and actual["model_calls"] == 0:
                raise VipEohError("已发起调用不能结算为零次")
            if actual["table_instances"] != 0:
                raise VipEohError("此profile没有执行桌赛，不能记桌赛成本")
            row.update(status="settled", actual=dict(actual), outcome=outcome,
                       charged={name: row["reserved"][name] if value is None else value
                                for name, value in actual.items()},
                       usage_unknown=any(value is None for value in actual.values()),
                       settled_at_utc=_utc(), reviewed_recovery=reviewed_recovery)
            row["budget_exceeded"] = any(sum(item["charged"][name] for item in data["reservations"])
                                          > self.batch.budgets[name] for name in ACCOUNTS)
            _atomic(self.path, _json_bytes(data))
            return dict(row)


def reconcile_vip_eoh_call(batch_file: Path, attempt_id: str, *, review_note: str) -> dict[str, Any]:
    """人工明确审核后保守结算中断调用；不删除费用、不重新发送请求。"""

    if not isinstance(review_note, str) or not review_note.strip():
        raise VipEohError("显式恢复需要非空人工审核说明")
    batch = VipEohBatch.read(batch_file)
    return VipEohLedger(batch_file, batch).settle(
        attempt_id, actual={name: 0 if name == "table_instances" else None for name in ACCOUNTS},
        outcome="manually_reconciled_unknown", reviewed_recovery=review_note,
    )


def _framework(batch: VipEohBatch) -> dict[str, Any]:
    """生成档及动态工具也取真实字节；运行中变化使提案无效。"""

    manifest = source_manifest(("hangma_bot.offline.vip_eoh_generate",))
    for relative in ("scripts/vip_route_eoh_generate.py",
                     "review/llm-guided-heuristic-route-2026-09-15/tools/sitin_generate.py",
                     "review/llm-guided-heuristic-route-2026-09-15/tools/sitin_process.py"):
        manifest[relative] = digest_of_file(REPO_ROOT / relative)
    return {"seed_identity": batch.identity(VIP_ROUTE_HEURISTIC_SEED_SOURCE),
            "generation_source_manifest": dict(sorted(manifest.items()))}


def vip_readonly_appendix(batch: VipEohBatch) -> dict[str, Any]:
    """从实际版本类型与白名单映射取完整字段附录，不传真实观察对象。"""

    classes = (RouteStructureFacts, RouteStructureTarget, RouteWaitingView,
               RouteHeuristicNode, RouteHeuristicAction, ActionScore, ScoreBatch)
    return {
        "schema_version": VIP_ROUTE_SCORING_VIEW_SCHEMA_VERSION,
        "candidate_kind": VIP_ROUTE_CANDIDATE_KIND,
        "readonly_mapping_source": inspect.getsource(VipRouteScoringView.candidate_view),
        "fact_type_definitions": {cls.__name__: inspect.getsource(cls) for cls in classes},
        "executor": {"version": EXECUTOR_VERSION, "allowed_builtins": sorted(ALLOWED_BUILTINS),
                     "allowed_methods": sorted(ALLOWED_METHODS),
                     "max_operations": batch.max_operations,
                     "max_local_collection_size": MAX_LOCAL_COLLECTION_SIZE,
                     "max_source_bytes": MAX_SOURCE_BYTES, "max_trace_bytes": MAX_TRACE_BYTES,
                     "projection_limits": asdict(batch.projection_limits),
                     "rule_config": asdict(batch.rule_config), "route_limits": asdict(batch.route_limits)},
        "subset": "禁止import/while/递归/try/注解/默认参数/下标赋值/下划线名字；"
                  "仅纯函数、常量和受限局部容器；无文件、网络、时钟、随机或跨调用缓存。",
        "result": "返回status=SCORED及entries，每个输入action_key恰一有限评分点和有界trace；"
                  "评分点越大越优，不是积分或真实EV。ABSTAIN/漏项/异常/超量使研究未完成。",
    }


def _validate_operator(operator: str, parents: Sequence[Mapping[str, Any]]) -> None:
    if operator not in OPERATORS:
        raise VipEohError("未知算子")
    count = len(parents)
    if operator == "i1" and count != 0 or operator in ("m1", "m2") and count != 1 or operator in ("e1", "e2") and count < 2:
        raise VipEohError("算子与父代数量不匹配")
    if len({parent["identity"]["candidate_id"] for parent in parents}) != count:
        raise VipEohError("多父代必须是不同候选，不能重复同一身份")


def load_vip_parents(paths: Sequence[Path], batch: VipEohBatch) -> list[dict[str, Any]]:
    """按输入顺序逐字节核验父包；仅接受当前新profile与相同实际额度。"""

    parents = []
    for path in paths:
        path = Path(path)
        record_bytes = (path / "generation.json").read_bytes()
        record = json.loads(record_bytes)
        if (record.get("schema") != VIP_EOH_GENERATION_SCHEMA
                or record.get("profile") != VIP_EOH_PROFILE
                or record.get("candidate_kind") != VIP_ROUTE_CANDIDATE_KIND
                or record.get("status") != "loaded_not_admitted"
                or record.get("load", {}).get("ok") is not True
                or record.get("identity_stable") is not True
                or record.get("artifact_role") not in ("candidate_proposal", "manual_seed")):
            raise VipEohError("父代不是新版已装载且未失效提案或人工种子")
        source = (path / "candidate.py").read_bytes().decode("utf-8")
        identity = batch.identity(source)
        if record.get("identity") != identity or record.get("source_sha256") != _sha(source):
            raise VipEohError("父代源码、合同、依赖或额度与当前逐字节身份不一致")
        if record["artifact_role"] == "manual_seed" and source != VIP_ROUTE_HEURISTIC_SEED_SOURCE:
            raise VipEohError("人工种子身份不对应当前完整人工种子源码")
        ActionValueExecutor(source, max_operations=batch.max_operations)
        parents.append({"path": str(path.resolve()), "identity": identity, "source": source,
                        "source_sha256": _sha(source), "record_sha256": _sha(record_bytes),
                        "thought": record.get("thought"), "mechanism": record.get("mechanism"),
                        "artifact_role": record["artifact_role"], "load": record["load"],
                        "admission": record.get("admission"),
                        "thought_sha256": _sha(record.get("thought") or "")})
    return parents


def numeric_constant_manifest(source: str) -> list[dict[str, Any]]:
    """按AST字段/列表路径列出全部数值常量；bool不当参数，顺序确定。"""

    found = []

    def visit(node, path, ancestors):
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            control = any(isinstance(parent, (ast.Subscript, ast.Compare))
                          or isinstance(parent, ast.Call) and isinstance(parent.func, ast.Name)
                          and parent.func.id == "range" for parent in ancestors)
            found.append({"ast_path": path, "value": node.value, "type": type(node.value).__name__,
                          "literal_role": "control_or_index" if control else "parameter_or_other",
                          "context": ast.unparse(ancestors[-1])[:500] if ancestors else ast.unparse(node),
                          "role_evidence": "AST上下文分类，不证明此数字仅为权重"})
        for field, value in ast.iter_fields(node):
            if isinstance(value, ast.AST):
                visit(value, path + "." + field, ancestors + (node,))
            elif isinstance(value, list):
                for index, child in enumerate(value):
                    if isinstance(child, ast.AST):
                        visit(child, path + "." + field + "[" + str(index) + "]", ancestors + (node,))

    visit(ast.parse(source), "module", ())
    return found


def _numeric_normalized_ast(source: str) -> str:
    class Normalize(ast.NodeTransformer):
        def visit_Constant(self, node):
            if type(node.value) in (int, float):
                # 该Name的id不是合法Python标识符，任何真实源码都无法伪造它。
                return ast.copy_location(ast.Name(id="<vip numeric literal>", ctx=ast.Load()), node)
            return node

    return ast.dump(Normalize().visit(ast.parse(source)), include_attributes=False)


def _m2_changes(parent_source: str, source: str) -> list[dict[str, Any]]:
    if _numeric_normalized_ast(parent_source) != _numeric_normalized_ast(source):
        raise VipEohError("m2仅允许数值常量变化；去数值后的AST结构不同")
    before, after = numeric_constant_manifest(parent_source), numeric_constant_manifest(source)
    if (len(before) != len(after)
            or [item["ast_path"] for item in before] != [item["ast_path"] for item in after]):
        raise VipEohError("m2继承数值常量数量或完整AST位置不同")
    changes = [{"ast_path": a["ast_path"], "before": a["value"], "after": b["value"],
                "literal_role": a["literal_role"], "context_before": a["context"],
                "context_after": b["context"]}
               for a, b in zip(before, after) if (a["type"], a["value"]) != (b["type"], b["value"])]
    if not changes:
        raise VipEohError("m2没有实际数值常量变化")
    return changes


def build_vip_eoh_prompt(batch: VipEohBatch, operator: str, parents: Sequence[Mapping[str, Any]],
                         feedback: str = ""):
    """统一完整只读附录、种子与开发反馈；父代次序保留在提示词与摘要。"""

    _validate_operator(operator, parents)
    tools = legacy_generation_tools()
    appendix = vip_readonly_appendix(batch)
    contract_path = REPO_ROOT / batch.identity(VIP_ROUTE_HEURISTIC_SEED_SOURCE)["contract_path"]
    prompt_parents = [{name: parent[name] for name in ("identity", "source", "thought", "mechanism")}
                      for parent in parents]
    payload = {"profile": VIP_EOH_PROFILE, "operator": operator,
               "readonly_appendix": appendix, "manual_seed_source": VIP_ROUTE_HEURISTIC_SEED_SOURCE,
               "parents": prompt_parents, "development_feedback": feedback,
               "feedback_scope": "仅开发反馈，不包含确认池或赛后隐藏信息",
               "m2_inherited_numeric_constants": numeric_constant_manifest(parents[0]["source"])
               if operator == "m2" else []}
    instructions = {
        "i1": "无父代：提出新的均衡联合机制，完整实现全部动作排名。",
        "e1": "参考有序多父，探索不同形式；逐父写预期行为差异，不能自报已测提升。",
        "e2": "提炼多父共同骨架，写继承与新增取舍；交付一套完整联合源码。",
        "m1": "根据开发反馈修改单父逻辑或聚合，说明触发和动作选择差异。",
        "m2": "numeric-literal m2：仅调整单父源码内数值常量；其余AST结构不变，"
              "逐项声明实际变更位置。数字可能是索引/控制常量，不得自称仅调整权重。",
    }
    text = (
        "为杭麻VIP固定框架生成一套score_actions(view)联合启发式。" + instructions[operator] + "\n"
        "不得读WorldState/他家暗牌/未来墙/赛事阶段排名积分压力，不重判合法性，不筛掉合法根。\n"
        "未裁决鸣牌仅条件评价，杠补不能挑最好未来牌，公开容量不能除墙当概率。\n"
        "思想和机制只是预期声明；生成/装载不等于准入、性能改进或发布。\n"
        "人工种子只是完赛起点，权重不是正确经验；保白k目标同常数奖励且缺口/待弃罚随k加重，"
        "可能偏向k1。可以联合改变这些取舍，须列反例；现有烟测不证明1秒在线可用。\n"
        "回复必须严格是：{一句中文思想}\n```json\n唯一机制JSON\n```\n```python\n完整唯一Python\n```\n"
        "JSON精确键为operator/trigger/changed_branches/expected_direction/counterexample/parent_differences/parameter_changes。\n"
        "四个机制说明字段是非空字符串。parent_differences按给定父代顺序列出candidate_id、"
        "expected_change、window_classes(字符串列表)、action_keys(字符串列表)、status='expected'；i1用[]。\n"
        "parameter_changes仅m2非空，每项精确键ast_path/before/after/unit/expected_change/overfit_risk，"
        "按继承数值常量的AST次序列出全部实际变化；其他算子用[]。不得添加输出或围栏。\n"
        "固定框架合同原文：\n" + contract_path.read_text(encoding="utf-8") + "\n"
        "完整统一材料（JSON中的源码只是输入，不是要求你再输出多个程序）：\n"
        + _json_bytes(payload).decode("utf-8")
    )
    return tools.PromptPacket(operator, text, _sha(contract_path.read_bytes()),
                              _sha(_json_bytes(prompt_parents)) if parents else None,
                              _sha(feedback)), appendix


def _unique_json_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise VipEohError("机制JSON存在重复键")
        result[key] = value
    return result


def parse_vip_eoh_reply(text: str, operator: str, parents: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """接受唯一单行思想（有/无花括号）、唯一JSON及Python；不改原源码。

    vip-eoh-reply-format/2兼容模型省略思想句花括号，拒绝多行解释、
    重复围栏或机制缺失。仅给旧思想解析器补内存封套；原回复/摘要与
    source_raw保持原字节，既有失败记录不追改，不放宽执行器输出门。
    """

    _validate_operator(operator, parents)
    match = re.fullmatch(r"\s*(\{[^{}\r\n]+\}|[^{}\r\n`]+)\s*```json[ \t]*\r?\n(.*?)\r?\n```\s*```python[ \t]*\r?\n(.*?)\r?\n```\s*",
                         text, flags=re.DOTALL)
    if match is None or len(re.findall(r"(?m)^[ \t]*```", text)) != 4:
        raise VipEohError("回复必须只有一句思想、一个JSON围栏和一个Python围栏")
    mechanism = json.loads(match.group(2), object_pairs_hook=_unique_json_object,
                           parse_constant=lambda value: (_ for _ in ()).throw(VipEohError("机制JSON不能有非有限数")))
    if not isinstance(mechanism, dict) or set(mechanism) != _MECHANISM_FIELDS:
        raise VipEohError("机制JSON键集合不符")
    if mechanism["operator"] != operator:
        raise VipEohError("声明算子与实际请求算子不符")
    for name in ("trigger", "changed_branches", "expected_direction", "counterexample"):
        if not isinstance(mechanism[name], str) or not mechanism[name].strip():
            raise VipEohError("机制字段必须是非空字符串: " + name)
    differences = mechanism["parent_differences"]
    if not isinstance(differences, list) or len(differences) != len(parents):
        raise VipEohError("逐父预期差异必须按父代列表完整保留")
    for difference, parent in zip(differences, parents):
        if (not isinstance(difference, dict) or set(difference) != {
            "candidate_id", "expected_change", "window_classes", "action_keys", "status"}
                or difference["candidate_id"] != parent["identity"]["candidate_id"]
                or difference["status"] != "expected"
                or not isinstance(difference["expected_change"], str) or not difference["expected_change"].strip()):
            raise VipEohError("逐父差异身份、顺序或预期标签不符")
        for name in ("window_classes", "action_keys"):
            if not isinstance(difference[name], list) or not difference[name] or any(
                not isinstance(value, str) or not value for value in difference[name]):
                raise VipEohError("预期窗口/动作键须为非空字符串列表")
    thought_line = match.group(1).strip()
    thought_envelope = "braced" if thought_line.startswith("{") else "plain_single_line"
    thought_content = thought_line[1:-1].strip() if thought_envelope == "braced" else thought_line
    if not thought_content or len(thought_content.splitlines()) != 1:
        raise VipEohError("思想必须是唯一非空单行，不接受空白或Unicode换行")
    legacy_text = (text if thought_envelope == "braced" else
                   "{" + thought_line + "}\n```json\n" + match.group(2)
                   + "\n```\n```python\n" + match.group(3) + "\n```")
    parsed = legacy_generation_tools().parse_model_reply(
        legacy_text, entry_name="score_actions", require_entry_definition=True)
    if parsed.status != "ok" or parsed.code is None or parsed.thought is None or not parsed.thought.strip():
        raise VipEohError("底层思想/完整入口解析失败")
    source = parsed.code
    parameter_changes = mechanism["parameter_changes"]
    if not isinstance(parameter_changes, list):
        raise VipEohError("parameter_changes必须是列表")
    if operator == "m2":
        actual_changes = _m2_changes(parents[0]["source"], source)
        if len(parameter_changes) != len(actual_changes):
            raise VipEohError("m2参数声明必须完整对应全部实际数值变化")
        for declared, actual in zip(parameter_changes, actual_changes):
            if (not isinstance(declared, dict) or set(declared) != {
                "ast_path", "before", "after", "unit", "expected_change", "overfit_risk"}
                    or any(declared[name] != actual[name] or type(declared[name]) is not type(actual[name])
                           for name in ("ast_path", "before", "after"))
                    or any(not isinstance(declared[name], str) or not declared[name].strip()
                           for name in ("unit", "expected_change", "overfit_risk"))):
                raise VipEohError("m2参数声明位置、值、单位或风险不符")
    elif parameter_changes:
        raise VipEohError("仅m2可带参数变化声明")
    return {"thought": parsed.thought, "mechanism": mechanism,
            "source": source, "source_raw": match.group(3),
            "numeric_literal_changes": actual_changes if operator == "m2" else [],
            "reply_format_version": "vip-eoh-reply-format/2", "thought_envelope": thought_envelope}


def _usage(reply, backend: str) -> dict[str, Any]:
    raw = dict(reply.usage or {})
    actual = {}
    for target, aliases in (("input_tokens", ("prompt_tokens", "inputTokens")),
                            ("output_tokens", ("completion_tokens", "outputTokens"))):
        actual[target] = next((raw[name] for name in aliases
                               if type(raw.get(name)) is int and raw[name] >= 0), None)
        if backend == "api" and reply.usage_source != "response_body":
            actual[target] = None  # 缺响应来源证据，不把自述用量当本次准确结算。
    return {"raw": raw, "raw_types": {name: type(value).__name__ for name, value in raw.items()},
            "reported": actual, "usage_unknown": any(value is None for value in actual.values()),
            "source": reply.usage_source if backend == "api" else "historical_envelope_self_declared",
            "billing_scope": "current_call" if backend == "api" else "historical_not_rebilled"}


def _safe_text(text: str, secrets: Sequence[str]) -> str:
    text = legacy_generation_tools().redact(text, secrets)
    for secret in secrets:
        if secret:
            text = text.replace(secret, "[REDACTED]")
    return re.sub(r"(?im)(Authorization\s*[:=]\s*)(?:Bearer\s+)?[^\r\n]+", r"\1[REDACTED]", text)


def _safe_value(value: Any, secrets: Sequence[str]) -> Any:
    """逐字符串脱敏，保留JSON容器形状；不用正则改写已序列化JSON。"""

    if isinstance(value, str):
        return _safe_text(value, secrets)
    if isinstance(value, dict):
        return {_safe_text(str(key), secrets): _safe_value(item, secrets) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_safe_value(item, secrets) for item in value]
    return value


def _reject_public_credentials(text: str) -> None:
    """预览不读私有凭据；原始公共输入含明显认证明文时在落盘前拒绝。"""

    if (re.search(r"(?i)\bauthorization\s*[:=]\s*(?:(?:bearer|basic)\s+)?[a-z0-9][^\s\"']*", text)
            or re.search(r"(?i)\bbearer\s+[a-z0-9][a-z0-9._~+/=-]*", text)
            or re.search(r'''(?i)["'](?:api_key|access_token|refresh_token)["']\s*:\s*["'][^"'\r\n]+["']''', text)
            or re.search(r'''(?i)\b(?:api_key|access_token|refresh_token)\s*=\s*["'][^"'\r\n]+["']''', text)):
        raise VipEohError("公开材料含认证明文；拒绝写盘或发送，不静默改写提示词摘要")


def _reject_known_key_artifacts(out_dir: Path, secrets: Sequence[str], record: dict[str, Any]) -> None:
    """API取得已知key后再查本次原始件；清除敏感件并停止，绝不发送原提示词。"""

    removed = []
    for path in sorted(out_dir.rglob("*")):
        if path.is_file() and any(secret.encode("utf-8") in path.read_bytes() for secret in secrets if secret):
            removed.append(str(path.relative_to(out_dir)))
            path.unlink()
    if removed:
        record["sensitive_material_removed"] = removed
        raise VipEohError("本次原始件含已知API密钥，已清除敏感件且没有发出调用")


def _error_diagnostics(error: BaseException, secrets: Sequence[str], phase: str) -> dict[str, Any]:
    """仅输出可行动分类与白名单错误码；底层原文可能含URL/config，禁止落盘。"""

    if isinstance(error, VipEohCallError):
        return dict(error.diagnostics, phase=phase)
    safe = _safe_text(str(error)[:4096], secrets).lower()
    status_match = re.search(r"\bhttp\s+([45][0-9]{2})\b", safe)
    status = int(status_match.group(1)) if status_match else None
    known_codes = (
        "insufficient_quota", "quota_exceeded", "billing_hard_limit_reached",
        "rate_limit_exceeded", "context_length_exceeded", "invalid_api_key",
        "model_not_found", "account_deactivated",
    )
    code = next((code for code in known_codes if code in safe), None)
    if code in {"insufficient_quota", "quota_exceeded", "billing_hard_limit_reached"} or any(
        word in safe for word in ("余额不足", "配额耗尽", "额度已用尽")):
        category, reason = "quota_exhausted", "模型配额或余额已耗尽；审核预算与账户，禁止自动重发"
    elif code == "rate_limit_exceeded" or status == 429:
        category, reason = "rate_limited_or_quota", "模型端限流或配额拒绝；核对账户，不自动重发"
    elif code in {"invalid_api_key", "account_deactivated"} or status in (401, 403):
        category, reason = "authentication_rejected", "模型认证或账户拒绝；审核私有配置，不打印凭据"
    elif code == "context_length_exceeded":
        category, reason = "context_limit", "完整提示词超过模型上下文；本次失败费用保留"
    elif code == "model_not_found":
        category, reason = "model_unavailable", "请求模型不可用；不自动切换模型或后端"
    elif isinstance(error, TimeoutError) or "timeout" in safe or "timed out" in safe:
        category, reason = "timeout", "调用或编排超过单次截止；结果未确认费用保留，禁止自动重发"
    elif status is not None:
        category, reason = "http_rejected", "模型HTTP明确拒绝；按状态审核，保留费用"
    elif isinstance(error, VipEohError) or isinstance(error, (ValueError, SyntaxError)):
        category, reason = "material_or_contract", "材料、格式、身份或额度校验失败；未完成准入"
    else:
        category, reason = "transport_or_runtime", "传输或运行失败且结果未确认；保留费用，禁止自动重发"
    return {"type": type(error).__name__, "category": category, "phase": phase,
            "http_status": status, "provider_error_code": code, "reason": reason}


def _complete_isolated(transport, prompt: str, timeout_seconds: float):
    """隔离API到可整组终止的进程；绝对超时不依赖socket分块间隔。"""

    context = multiprocessing.get_context("fork")
    receiver, sender = context.Pipe(duplex=False)

    def complete():
        receiver.close()
        os.setsid()
        try:
            reply = transport.complete(prompt)
            if len(reply.text.encode("utf-8")) > 8 * MAX_SOURCE_BYTES:
                sender.send((False, "ReplyTooLarge"))
            else:
                sender.send((True, reply))
        except BaseException as error:
            secret = getattr(transport, "_api_key", None)
            sender.send((False, _error_diagnostics(error, (secret,) if secret else (), "model_call")))
        finally:
            sender.close()

    process = context.Process(target=complete)
    if timeout_seconds <= 0:
        receiver.close()
        sender.close()
        raise TimeoutError("本次API调用前墙钟预算已耗尽")
    process.start()
    sender.close()
    received = False
    try:
        if not receiver.poll(timeout_seconds):
            raise TimeoutError("API隔离调用超过剩余墙钟上限")
        ok, result = receiver.recv()
        received = True
        if not ok:
            if isinstance(result, dict):
                raise VipEohCallError(result)
            raise VipEohError("API隔离调用未完成: " + result)
        return result
    finally:
        receiver.close()
        if received:
            process.join(timeout=0.05)
        if process.is_alive():
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                process.kill()
        process.join()


def write_vip_seed_parent(out_dir: Path, batch_file: Path) -> dict[str, Any]:
    """显式生成当前人工种子父包；只装载，不自报桌赛、准入或模型出处。"""

    batch = VipEohBatch.read(batch_file)
    identity = batch.identity(VIP_ROUTE_HEURISTIC_SEED_SOURCE)
    ActionValueExecutor(VIP_ROUTE_HEURISTIC_SEED_SOURCE, max_operations=batch.max_operations)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=False)
    record = {"schema": VIP_EOH_GENERATION_SCHEMA, "profile": VIP_EOH_PROFILE,
              "candidate_kind": VIP_ROUTE_CANDIDATE_KIND, "artifact_role": "manual_seed",
              "status": "loaded_not_admitted", "identity": identity, "identity_stable": True,
              "source_sha256": _sha(VIP_ROUTE_HEURISTIC_SEED_SOURCE),
              "thought": "均衡人工种子：联合普通出口、自然白用途与保守杠补。", "mechanism": None,
              "load": {"ok": True, "method": "ActionValueExecutor_constructor", "gates_run": []},
              "admission": {"eligible": False, "gates_run": []},
              "publication": {"published": False}, "parents": [], "is_model_output": False}
    _atomic(out_dir / "candidate.py", VIP_ROUTE_HEURISTIC_SEED_SOURCE.encode("utf-8"))
    _atomic(out_dir / "generation.json", _json_bytes(record))
    return record


def run_vip_eoh_generate(
    *, batch_file: Path, out_dir: Path, operator: str, backend: str = "emit",
    parent_paths: Sequence[Path] = (), feedback: str = "", reply_file: Path | None = None,
    config: Path | None = None, endpoint: str | None = None, model: str | None = None,
    tier: str | None = None, backend_factory: Callable[..., Any] | None = None,
    now_monotonic: Callable[[], float] = time.monotonic,
) -> dict[str, Any]:
    """独立生成一次提案；未完成费用留存，不自动重试、不运行任何桌赛。

    emit只输出交接提示词；replay读哈希相符的历史封套，本次模型成本为零；
    api只有预留持久化之后才构造既有后端读取凭据。backend_factory是测试
    注入的传输接缝，默认唯一使用旧build_backend；生成源码只进受限执行器。
    """

    started = now_monotonic()  # 覆盖父代、提示词、快照、装载与调用的完整生成持续时间。
    if backend not in ("emit", "replay", "api"):
        raise VipEohError("此profile仅提供emit/replay/api，不自动切后端")
    batch = VipEohBatch.read(batch_file)
    parents = load_vip_parents(parent_paths, batch)
    packet, appendix = build_vip_eoh_prompt(batch, operator, parents, feedback)
    framework = _framework(batch)
    # 整个公共提示词与将复制的源码均先扫描；此路径不会收集任何私有凭据。
    _reject_public_credentials(feedback)  # JSON封套会转义引号，先检查未序列化原输入。
    for parent in parents:
        _reject_public_credentials(parent["source"])
        _reject_public_credentials(parent["thought"] or "")
    _reject_public_credentials(packet.text)
    _reject_public_credentials(batch.raw.decode("utf-8"))
    for relative in framework["generation_source_manifest"]:
        _reject_public_credentials((REPO_ROOT / relative).read_bytes().decode("utf-8", errors="ignore"))
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=False)
    attempt_id = uuid.uuid4().hex
    ledger = VipEohLedger(batch_file, batch)
    record = {"schema": VIP_EOH_GENERATION_SCHEMA, "profile": VIP_EOH_PROFILE,
              "candidate_kind": VIP_ROUTE_CANDIDATE_KIND, "operator_requested": operator,
              "operator_actual": None, "batch_id": batch.batch_id, "batch_sha256": _sha(batch.raw),
              "attempt_id": attempt_id, "status": "prepared", "started_at_utc": _utc(),
              "framework": framework, "identity": None, "identity_stable": False,
              "prompt_sha256": packet.sha256, "readonly_appendix_sha256": _sha(_json_bytes(appendix)),
              "feedback_sha256": _sha(feedback), "parents": parents,
              "parents_sha256": _sha(_json_bytes(parents)), "backend": backend,
              "reply": None, "reply_sha256": None, "thought": None, "mechanism": None,
              "source_sha256": None, "load": {"ok": False, "gates_run": []},
              "artifact_role": "prompt_handoff" if backend == "emit" else None,
              "admission": {"eligible": False, "gates_run": []},
              "publication": {"published": False}, "tables_run": 0,
              "behavior_change_credit": False, "error": None}
    _atomic(out_dir / "prompt.txt", packet.text.encode("utf-8"))
    _atomic(out_dir / "batch.json", batch.raw)
    _atomic(out_dir / "readonly-appendix.json", _json_bytes(appendix))
    contract = REPO_ROOT / framework["seed_identity"]["contract_path"]
    _atomic(out_dir / "contract.md", contract.read_bytes())
    write_code_snapshot(out_dir, framework["generation_source_manifest"])
    _atomic(out_dir / "generation.json", _json_bytes(record))
    reservation = None
    secrets: tuple[str, ...] = ()
    call_started = False
    usage = None
    phase = "preflight"
    try:
        record["input_reservation_evidence"] = {
            "prompt_utf8_bytes": len(packet.text.encode("utf-8")),
            "minimum_reserved_tokens": batch.input_bound["max_input_tokens"] if batch.input_bound else None,
            "input_bound": batch.input_bound,
            "basis": "已核模型整输入上限的工程预留；UTF-8字节仅记规模，不作为token上界或精准token数",
        }
        if backend == "api":
            if batch.input_bound is None:
                raise VipEohError("模型输入上限证据未知，禁止读取凭据或真实调用")
            if batch.input_tokens_per_call < batch.input_bound["max_input_tokens"]:
                raise VipEohError("冻结输入预留小于已核模型输入上限，禁止读取凭据")
            if model is not None and model != batch.input_bound["model"]:
                raise VipEohError("CLI请求模型与冻结input_bound模型不符")
        phase = "budget_reservation"
        reservation = ledger.reserve(attempt_id, backend)
        record["attempt_no"] = reservation["attempt_no"]
        record["reservation"] = reservation
        _atomic(out_dir / "generation.json", _json_bytes(record))
        if backend == "emit":
            record.update(status="prompt_emitted", identity_stable=framework == _framework(batch))
            if not record["identity_stable"]:
                record["status"] = "framework_changed_invalid"
        else:
            phase = "backend_configuration"
            if now_monotonic() - started >= batch.timeout_seconds:
                raise TimeoutError("构造传输前本次墙钟预算已耗尽")
            tools = legacy_generation_tools()
            sampling = tools.SamplingSpec(max_tokens=batch.max_tokens_per_call, **batch.sampling)
            factory = backend_factory or tools.build_backend
            # 此行是唯一凭据读取边界；其上方预留和尝试记录已经fsync落盘。
            transport = factory(backend, prompt_sha256=packet.sha256, reply_file=reply_file,
                                config=config, endpoint=endpoint, model=model, tier=tier,
                                sampling=sampling, timeout_sec=batch.timeout_seconds)
            if backend == "api":
                secret = getattr(transport, "_api_key", None)
                secrets = (secret,) if isinstance(secret, str) and secret else ()
                _reject_known_key_artifacts(out_dir, secrets, record)
                if getattr(transport, "model", None) != batch.input_bound["model"]:
                    raise VipEohError("实际传输请求模型与已核输入上限不匹配，不发出调用")
                if now_monotonic() - started >= batch.timeout_seconds:
                    raise TimeoutError("请求前本次墙钟预算已耗尽")
                ledger.mark_call_started(attempt_id)
                call_started = True
            remaining = batch.timeout_seconds - (now_monotonic() - started)
            phase = "model_call" if backend == "api" else "replay_read"
            reply = (_complete_isolated(transport, packet.text, remaining) if backend == "api"
                     else transport.complete(packet.text))
            raw = reply.text
            phase = "reply_validation"
            safe = _safe_text(raw, secrets)
            record["reply"] = reply.to_json()
            record["reply_sha256"] = _sha(raw)
            record["reply_redacted"] = raw != safe
            record["sampling"] = {"actual_request_fields": sampling.to_request_fields(),
                                  "source": "request_body"} if backend == "api" else None
            record["model_identity"] = {
                "requested": reply.model_requested or model, "returned": reply.model,
                "source": ("response_body" if backend == "api" and reply.model != reply.model_requested
                           else "response_or_request_fallback" if backend == "api"
                           else "historical_envelope_self_declared"),
                "observed_exact_response_model": backend == "api" and reply.model != reply.model_requested,
            }
            usage = _usage(reply, backend)
            record["usage"] = usage
            _atomic(out_dir / "reply.txt", safe.encode("utf-8"))
            if safe != raw:
                raise VipEohError("回复含需脱敏内容，不能把被改写的源码当完整候选")
            if reply.finish_reason != "stop" and not (
                reply.origin == tools.ORIGIN_FIXTURE and reply.finish_reason is None):
                record["status"] = "truncated" if reply.finish_reason is not None else "finish_unknown"
                raise VipEohError("模型终止原因未证明完整回复，费用仍结算")
            parsed = parse_vip_eoh_reply(raw, operator, parents)
            record.update(thought=parsed["thought"], mechanism=parsed["mechanism"],
                          source_sha256=_sha(parsed["source"]), operator_actual=operator,
                          numeric_literal_changes=parsed["numeric_literal_changes"],
                          m2_scope="numeric-literal m2" if operator == "m2" else None,
                          thought_sha256=_sha(parsed["thought"]),
                          mechanism_sha256=_sha(_json_bytes(parsed["mechanism"])),
                          source_raw_sha256=_sha(parsed["source_raw"]),
                          reply_format_version=parsed["reply_format_version"],
                          thought_envelope=parsed["thought_envelope"])
            _atomic(out_dir / "source-raw.py", parsed["source_raw"].encode("utf-8"))
            _atomic(out_dir / "candidate.py", parsed["source"].encode("utf-8"))
            phase = "candidate_load"
            ActionValueExecutor(parsed["source"], name=VIP_ROUTE_CANDIDATE_KIND,
                                max_operations=batch.max_operations)
            record["identity"] = batch.identity(parsed["source"])
            phase = "identity_verification"
            record["load"] = {"ok": True, "method": "ActionValueExecutor_constructor", "gates_run": [],
                              "full_return_or_behavior_verified": False}
            record["is_model_output"] = reply.origin != tools.ORIGIN_FIXTURE
            record["artifact_role"] = "candidate_proposal" if record["is_model_output"] else "format_fixture"
            record["identity_stable"] = framework == _framework(batch)
            record["status"] = "loaded_not_admitted" if record["identity_stable"] else "framework_changed_invalid"
    except Exception as error:
        if record["status"] == "prepared":
            record["status"] = "failed"
        record["error"] = _error_diagnostics(error, secrets, phase)
    finally:
        elapsed = max(0.0, now_monotonic() - started)
        record["ended_at_utc"] = _utc()
        record["elapsed_monotonic_seconds"] = elapsed
        if elapsed > batch.timeout_seconds:
            record["status"] = "deadline_exceeded_invalid"
        if reservation is not None:
            reported = usage["reported"] if usage and backend == "api" else {}
            actual = {"model_calls": int(call_started),
                      "input_tokens": reported.get("input_tokens") if backend == "api" and call_started else 0,
                      "output_tokens": reported.get("output_tokens") if backend == "api" and call_started else 0,
                      "table_instances": 0, "wall_clock_seconds": elapsed}
            record["billing"] = ledger.settle(attempt_id, actual=actual, outcome=record["status"])
            if record["billing"]["budget_exceeded"]:
                record["status"] = "budget_exceeded_invalid"
        safe_record = _safe_value(record, secrets)
        if legacy_generation_tools().find_leaked_secrets(safe_record, secrets):
            raise VipEohError("脱敏后仍有凭据泄漏，拒绝落盘")
        _atomic(out_dir / "generation.json", _json_bytes(safe_record))
    return safe_record
