"""P28：把 R17 的 2 步公开后继搜索（叶程序 A/B）重新基线到 R18 v2 上评估。

与 r17_generation1_reproduction.py 的差别**只有基线策略**：

- 原来 focal 基线是 ComparableHeuristicPolicyV2（weighted_heuristic_v2）；
- 本批 focal 基线是 bootstrap.build_research_policy(
  "action_value:r18_integrated_positive_v2")；
- 候选 A/B 的包装器 PublicSuccessorSearchPolicy 显式传 baseline=<R18 v2>
  （原批次走的是包装器默认的 V2，见 public_successor_policy.py 第 70-74 行）。

自然面板、配对单元、U 口径、配对阶段分全部沿用同一实现（sitin_natural_panel），
根计划与臂无关，配对红线不变。

不改任何既有源码：基线注入走**运行期装配补丁**（只在本脚本的进程与其子进程内
生效），并逐桌记录 focal 策略 policy_id 供事后核对。

产物只写进 OUT（新目录），R17 既有批次目录全程只读。
"""

from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

import argparse
import concurrent.futures
import hashlib
import json
import statistics
import sys
import time
from pathlib import Path
from typing import Any, Mapping


HERE = Path(__file__).resolve().parent
ROUTE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15')
ROOT = _PROJECT_ROOT
for path in (
    _project_file(_PROJECT_ROOT, ROOT / "src"),
    _project_file(_PROJECT_ROOT, ROUTE / "tools"),
    _project_file(_PROJECT_ROOT, ROUTE / "evidence/v4-impl/r9-gate2/run"),
    HERE,
):
    sys.path.insert(0, str(path))

import confirmation_execution_identity as guard  # noqa: E402
import sitin_natural_panel as natural  # noqa: E402
import sitin_search as search  # noqa: E402
import sitin_stage as stage  # noqa: E402
import strong_seed_batch as batch  # noqa: E402
from hangma_bot import bootstrap  # noqa: E402
from hangma_bot.hangma.engine import HangmaRules  # noqa: E402
from hangma_bot.hangma.interface import ValueAnalysisLimits  # noqa: E402
from hangma_bot.kernel.config import RuleConfig  # noqa: E402
from hangma_bot.policy.action_value import CANDIDATE_KIND  # noqa: E402
from hangma_bot.policy.r18_integrated_positive_v2 import (  # noqa: E402
    R18_INTEGRATED_POSITIVE_V2_NAME,
)
from hangma_bot.policy.public_successor_leaf_executor import (  # noqa: E402
    LeafProgramExecutor,
)
from hangma_bot.policy.public_successor_policy import (  # noqa: E402
    PublicSuccessorSearchPolicy,
)
from hangma_bot.policy.public_successor_search import (  # noqa: E402
    order_discard_keys_by_fronts,
)


# ============================================================ 批次常量
OUT_NAME = "r17-generation1-vs-r18v2-01-20260925"
OUT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r17-generation1-vs-r18v2-01-20260925')

#: P28 专用新面板种子；既不是 R17 第一来源 2026092917，也不是第二来源 2026093017。
PANEL_SEED = 2026093028
MIXES = ("H", "M")
#: 24 根 x 4 焦点座位 x 2 混合 = 192 个来源单元；每单元 2 桌 => 每臂 384 张完整桌。
ROOTS = tuple(range(1, 25))
SEATS = (0, 1, 2, 3)
SOURCE_UNITS = len(MIXES) * len(ROOTS) * len(SEATS)
TABLES_PER_STAGE = 2
WORKERS = 4

#: 预登记基线：R18 v2（研究注册表键名）。
BASELINE_STRATEGY = "action_value:r18_integrated_positive_v2"
#: 装配后策略自我报告的 identity（行动值策略的 policy_id = "<kind>:<scorer name>"）。
BASELINE_POLICY_ID = "{0}:{1}".format(CANDIDATE_KIND, R18_INTEGRATED_POSITIVE_V2_NAME)
#: R18 v2 在**面板白名单**里的注入名（不是合同对手名；对手仍是 V2/V2_guard/V1）。
R18V2_PANEL_NAME = "r18_integrated_positive_v2"
#: 参考臂（**不参与预登记判定**）用的旧基线名，用于在同一新面板上取 R18 v2 与 V2
#: 的父代差，作为解释「增量是否被父代吸收」的旁证。
V2_PANEL_NAME = "weighted_heuristic_v2"

ARMS = ("baseline", "reference:v2", "candidate:A", "candidate:B")
CANDIDATE_INPUTS = {
    "A": {
        "author_dir": _project_file(_PROJECT_ROOT, HERE / "r17-seed-author-a-astra-01-20260921"),
        "gate_dir": _project_file(_PROJECT_ROOT, HERE / "r17-seed-gate-a-astra-03-20260921"),
    },
    "B": {
        "author_dir": _project_file(_PROJECT_ROOT, HERE / "r17-seed-author-b-sol-repair-01-20260921"),
        "gate_dir": _project_file(_PROJECT_ROOT, HERE / "r17-seed-gate-b-sol-repair-03-20260921"),
    },
}
PLAN = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/R17-RULE-OWNED-PUBLIC-SEARCH-EVOLUTION-PLAN-2026-09-21.md')
CONTRACT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/contracts/group-dev-v1.json')
LEAF_CONTRACT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/contracts/r17-public-successor-leaf-v1.json')
PREREG = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/P28-PREREG-R17-VS-R18V2.md')


# ============================================================ 基线注入（运行期补丁）
_ORIGINAL_BUILD_PANEL_POLICY = stage.build_panel_policy
_ORIGINAL_ARM_LOGICAL_POLICIES = natural.arm_logical_policies


def build_r18v2_policy():
    """经组合根装配 R18 v2；与真实离线研究入口同一条路径。"""

    policy = bootstrap.build_research_policy(BASELINE_STRATEGY)
    if getattr(policy, "policy_id", None) != BASELINE_POLICY_ID:
        raise RuntimeError(
            "R18 v2 装配身份异常：{0!r} != {1!r}".format(
                getattr(policy, "policy_id", None), BASELINE_POLICY_ID
            )
        )
    return policy


def _rebased_build_panel_policy(name: str, monotonic):
    """只把面板基线名重定向到 R18 v2；其它白名单名逐字走原实现。"""

    if str(name) == R18V2_PANEL_NAME:
        return build_r18v2_policy()
    return _ORIGINAL_BUILD_PANEL_POLICY(str(name), monotonic)


stage.build_panel_policy = _rebased_build_panel_policy


#: 逐桌 focal 策略身份与规则侧成本（真实读数的暂存，不是事后声明）。
_LIVE: dict[str, Any] = {}


def _reset_live() -> None:
    _LIVE.clear()
    _LIVE.update(
        {
            "focal_policy_ids": [],
            "eligible_draw_windows": 0,
            "complete_reductions": 0,
            "incomplete_reductions": 0,
            "incomplete_reasons": [],
            "changed_discard_orders": 0,
            "provider_calls": 0,
            "provider_failures": 0,
            "provider_failure_reasons": [],
            "t_analysis_ms": [],
            "t_reduce_ms": [],
            "t_focal_choose_ms": [],
            "last_provider_exit": None,
        }
    )


def _observing_arm_logical_policies(**kwargs):
    policies = _ORIGINAL_ARM_LOGICAL_POLICIES(**kwargs)
    focal = policies[natural.FOCAL_PARTICIPANT]
    inner = getattr(focal, "inner", focal)
    _LIVE["focal_policy_ids"].append(
        str(getattr(inner, "policy_id", type(inner).__name__))
    )
    return policies


natural.arm_logical_policies = _observing_arm_logical_policies


class _TimedFocalPolicy:
    """薄计时包装：只测量焦点策略 choose 的墙钟耗时，不改行为。"""

    def __init__(self, policy):
        self.inner = policy
        self.policy_id = policy.policy_id
        self.max_operations = getattr(policy, "max_operations", None)

    async def choose(self, request, budget):
        started = time.perf_counter()
        try:
            return await self.inner.choose(request, budget)
        finally:
            _LIVE["t_focal_choose_ms"].append((time.perf_counter() - started) * 1000.0)


def _timed_provider(analyze):
    """规则侧后继分析计时；异常原样抛出，由包装器整窗回退。"""

    def provider(observation):
        _LIVE["provider_calls"] += 1
        started = time.perf_counter()
        try:
            analysis = analyze(observation)
        except Exception as exc:  # noqa: BLE001
            _LIVE["provider_failures"] += 1
            _LIVE["provider_failure_reasons"].append(
                "{0}: {1}".format(type(exc).__name__, str(exc)[:200])
            )
            raise
        finally:
            _LIVE["t_analysis_ms"].append((time.perf_counter() - started) * 1000.0)
            _LIVE["last_provider_exit"] = time.perf_counter()
        return analysis

    return provider


def _counting_orderer(reduction, baseline_keys):
    """固定归约器出口：统计改序与归约失败，并把耗时归到规则侧归约段。"""

    now = time.perf_counter()
    exit_at = _LIVE["last_provider_exit"]
    if exit_at is not None:
        _LIVE["t_reduce_ms"].append((now - exit_at) * 1000.0)
    _LIVE["eligible_draw_windows"] += 1
    ordered = order_discard_keys_by_fronts(reduction, baseline_keys)
    if reduction.complete:
        _LIVE["complete_reductions"] += 1
        if ordered != tuple(baseline_keys):
            _LIVE["changed_discard_orders"] += 1
    else:
        _LIVE["incomplete_reductions"] += 1
        _LIVE["incomplete_reasons"].append(str(reduction.reason)[:200])
    return ordered


def build_candidate_policy(source: str, candidate_identity: str, name: str,
                           versions: Mapping[str, Any]):
    """候选 = R17 叶程序包装器，**其内部基线显式指定为 R18 v2**。"""

    def factory(monotonic_clock):
        rules = HangmaRules(
            RuleConfig(
                ruleset_version=str(versions["ruleset_version"]),
                base_score=int(versions["base_score"]),
                you_cai_bi_kao=bool(versions["you_cai_bi_kao"]),
            )
        )
        policy = PublicSuccessorSearchPolicy(
            _timed_provider(rules.analyze_public_self_draw_successors),
            LeafProgramExecutor(source, name=name),
            candidate_identity=candidate_identity,
            baseline=build_r18v2_policy(),
            monotonic=monotonic_clock,
            orderer=_counting_orderer,
        )
        return _TimedFocalPolicy(policy)

    return factory


# ============================================================ 通用小工具
def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    path.write_text(text, encoding="utf-8")


def sources() -> list[dict[str, Any]]:
    return [
        {
            "mix": mix,
            "root_index": root,
            "focal_seat": seat,
            "source_id": "{0}:r{1:02d}:s{2}".format(mix, root, seat),
        }
        for mix in MIXES
        for root in ROOTS
        for seat in SEATS
    ]


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, max(0, round((len(ordered) - 1) * fraction)))]


def cost_summary(values: list[float]) -> "dict[str, Any] | None":
    if not values:
        return None
    return {
        "samples": len(values),
        "p50_ms": round(percentile(values, 0.50), 3),
        "p90_ms": round(percentile(values, 0.90), 3),
        "p99_ms": round(percentile(values, 0.99), 3),
        "max_ms": round(max(values), 3),
        "mean_ms": round(statistics.fmean(values), 3),
    }


def passing_candidates() -> dict[str, dict[str, str]]:
    """只接收零桌门已通过、且源码与门记录逐字节一致的 A/B 冻结源码。

    本批**不做效果侧选择**：A、B 以原身份同时进入，没有事后挑选。
    """

    passed = {}
    for candidate_id, inputs in CANDIDATE_INPUTS.items():
        candidate_path = inputs["author_dir"] / "candidate.py"
        gate_path = inputs["gate_dir"] / "result.json"
        result = json.loads(gate_path.read_text(encoding="utf-8"))
        if (
            result.get("status") != "PASS_R17_SEED_ZERO_TABLE"
            or not result.get("coverage_pass")
            or not result.get("behavior_pass")
            or result.get("failures")
        ):
            raise RuntimeError("R17 种子未通过冻结零桌门: " + candidate_id)
        if result.get("candidate_source_sha256") != digest(candidate_path):
            raise RuntimeError("R17 种子源码与零桌身份漂移: " + candidate_id)
        passed[candidate_id] = {
            "path": str(candidate_path),
            "sha256": digest(candidate_path),
            "identity": str(result["candidate_identity"]),
            "gate_result": str(gate_path),
            "gate_result_sha256": digest(gate_path),
        }
    return passed


def source_paths(candidates: Mapping[str, Mapping[str, str]]) -> list[Path]:
    paths = [
        Path(__file__),
        PREREG,
        PLAN,
        CONTRACT,
        LEAF_CONTRACT,
        Path(natural.__file__),
        Path(stage.__file__),
        Path(search.__file__),
        _project_file(_PROJECT_ROOT, ROOT / "src/hangma_bot/policy/public_successor_policy.py"),
        _project_file(_PROJECT_ROOT, ROOT / "src/hangma_bot/policy/public_successor_search.py"),
        _project_file(_PROJECT_ROOT, ROOT / "src/hangma_bot/policy/public_successor_leaf_executor.py"),
        _project_file(_PROJECT_ROOT, ROOT / "src/hangma_bot/policy/r18_integrated_positive_v2.py"),
        _project_file(_PROJECT_ROOT, ROOT / "src/hangma_bot/bootstrap.py"),
    ]
    for item in candidates.values():
        paths.extend((Path(item["path"]), Path(item["gate_result"])))
    return paths


# ============================================================ prepare
def prepare() -> None:
    if OUT.exists():
        raise SystemExit("P28 输出目录已存在；拒绝覆盖：" + str(OUT))
    candidates = passing_candidates()
    for candidate_id, item in candidates.items():
        LeafProgramExecutor(
            Path(item["path"]).read_text(encoding="utf-8"),
            name="p28-precheck-" + candidate_id,
        )
    planned_tables = SOURCE_UNITS * len(ARMS) * TABLES_PER_STAGE
    OUT.mkdir(parents=True)
    authorization = batch.unified_document(
        batch_label=OUT.name,
        authorization_id="p28-r17-vs-r18v2-01",
        accounts={"tables_full": planned_tables},
        issued_by="lead",
        issued_at_utc=search.utc_now(),
        legacy_alias=False,
    )
    authorization.update(
        {
            "issuance_basis": (
                "P28 预登记：R17 A/B 冻结源码原样进入；评价基线从稳定 V2 换成 "
                "R18 v2，用于测量 2 步公开后继搜索相对当前部署父代有无增量"
            ),
            "scope": (
                "R18 v2（预登记基线）+ 稳定 V2（参考臂，不参与判定）+ R17 冻结叶"
                "程序 A/B；全新 panel_seed 2026093028；H/M 各 24 根、4 焦点座位、"
                "每单元 2 桌；每臂 384 张完整桌"
            ),
            "max_model_calls": 0,
            "confirmation_roots": 0,
        }
    )
    write_json(_project_file(_PROJECT_ROOT, OUT / "authorization.json"), authorization)
    manifest = {
        "schema": "p28-r17-vs-r18v2/1",
        "created_at_utc": search.utc_now(),
        "runtime": guard.capture(
            source_paths=source_paths(candidates) + [_project_file(_PROJECT_ROOT, OUT / "authorization.json")]
        ),
        "prereg": str(PREREG),
        "prereg_sha256": digest(PREREG),
        "plan": str(PLAN),
        "plan_sha256": digest(PLAN),
        "contract": str(CONTRACT),
        "contract_sha256": digest(CONTRACT),
        "leaf_contract": str(LEAF_CONTRACT),
        "leaf_contract_sha256": digest(LEAF_CONTRACT),
        "candidates": candidates,
        "baseline": {
            "strategy": BASELINE_STRATEGY,
            "panel_name": R18V2_PANEL_NAME,
            "assembly": "hangma_bot.bootstrap.build_research_policy",
            "injection": (
                "运行期补丁：sitin_stage.build_panel_policy 只把面板基线名重定向到 "
                "R18 v2；sitin_natural_panel.BASELINE_FOCAL_POLICY 逐臂设置；"
                "合同对手名（weighted_heuristic_v2 / _white_guard / _v1）逐字不变"
            ),
        },
        "reference_arm": {
            "arm": "reference:v2",
            "panel_name": V2_PANEL_NAME,
            "role": "旧基线（稳定 V2）在同一新面板上的读数；不参与预登记判定",
        },
        "rules_hash": natural.compute_rules_hash(natural.REPO),
        "panel_seed": PANEL_SEED,
        "source_relation": (
            "panel_seed 2026093028 与 R17 第一来源 2026092917、第二来源 2026093017 "
            "都不同；根号沿用 1-24，世界由新 seed 重建；既有批次结果不参与来源生成"
        ),
        "mixes": list(MIXES),
        "root_indices": list(ROOTS),
        "focal_seats": list(SEATS),
        "source_units": SOURCE_UNITS,
        "tables_per_stage": TABLES_PER_STAGE,
        "arms": list(ARMS),
        "planned_tables": planned_tables,
        "tables_per_arm": SOURCE_UNITS * TABLES_PER_STAGE,
        "workers": WORKERS,
        "judgement_rules": {
            "overall": "总体保守 U 差 = mean(candidate.u_low - baseline.u_high)，单元均值",
            "stage_score": "阶段积分差均值（分/桌口径的诊断量）",
            "fourth": "第四率差 = candidate_fourth_rate - baseline_fourth_rate",
            "next_level": "保守 U 差>0 且 阶段积分差均值>0 且 正效应跨>=2根与>=2座位",
            "no_conclusion": "两者符号相反",
            "close_axis": "两者都 <=0，关闭 2 步公开后继搜索 这条轴",
        },
        "strength_claim": False,
        "confirmation_reserved": 0,
    }
    write_json(_project_file(_PROJECT_ROOT, OUT / "manifest.json"), manifest)
    print(
        json.dumps(
            {
                "status": "PREPARED",
                "candidates": sorted(candidates),
                "sources": SOURCE_UNITS,
                "arms": list(ARMS),
                "planned_tables": planned_tables,
                "tables_per_arm": SOURCE_UNITS * TABLES_PER_STAGE,
                "panel_seed": PANEL_SEED,
            },
            ensure_ascii=False,
        )
    )


def verify_manifest() -> dict[str, Any]:
    manifest = json.loads((_project_file(_PROJECT_ROOT, OUT / "manifest.json")).read_text(encoding="utf-8"))
    for key, sha_key in (
        ("prereg", "prereg_sha256"),
        ("plan", "plan_sha256"),
        ("contract", "contract_sha256"),
        ("leaf_contract", "leaf_contract_sha256"),
    ):
        if digest(Path(manifest[key])) != manifest[sha_key]:
            raise RuntimeError("冻结输入摘要漂移: " + key)
    for candidate_id, item in manifest["candidates"].items():
        if digest(Path(item["path"])) != item["sha256"]:
            raise RuntimeError("冻结候选摘要漂移: " + candidate_id)
        if digest(Path(item["gate_result"])) != item["gate_result_sha256"]:
            raise RuntimeError("冻结零桌门摘要漂移: " + candidate_id)
    guard.verify(manifest["runtime"])
    return manifest


# ============================================================ 执行
def execute_stage(arm: str, source_row: Mapping[str, Any],
                  candidates: Mapping[str, Mapping[str, str]]) -> dict[str, Any]:
    """跑一个（臂 x 来源）的真实两桌阶段，并把焦点策略身份与规则侧成本带回。"""

    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    versions = natural.stage.contract_versions_block(contract)
    plans = natural.build_seat_stage_plans(
        contract=contract,
        opponent=str(source_row["mix"]),
        root_index=int(source_row["root_index"]),
        focal_seat=int(source_row["focal_seat"]),
        panel_seed=PANEL_SEED,
    )
    _reset_live()
    is_candidate = str(arm).startswith("candidate:")
    factory = None
    requests: list[Any] = []
    if is_candidate:
        candidate_id = str(arm).split(":", 1)[1]
        item = candidates[candidate_id]
        source = Path(item["path"]).read_text(encoding="utf-8")
        factory = build_candidate_policy(
            source, str(item["identity"]), "p28-" + candidate_id, versions
        )
    elif arm == "reference:v2":
        natural.BASELINE_FOCAL_POLICY = V2_PANEL_NAME
    else:
        natural.BASELINE_FOCAL_POLICY = R18V2_PANEL_NAME

    def wrapped_factory(monotonic):
        return factory(monotonic)

    result = natural.run_arm_stage(
        arm="candidate" if is_candidate else "baseline",
        plans=plans,
        candidate_scorer=None,
        opponent_policies=contract["panel"]["opponent_scenarios"][
            str(source_row["mix"])
        ]["opponent_policies"],
        versions_block=versions,
        step_limit=int(contract["stop"]["step_limit"]),
        value_limits=ValueAnalysisLimits(),
        decision_observer=(requests.append if is_candidate else None),
        candidate_policy_factory=(wrapped_factory if is_candidate else None),
    )
    result["arm"] = arm
    result["focal_policy_ids_by_table"] = [
        {"table_id": plan.table_id, "policy_id": policy_id}
        for plan, policy_id in zip(plans, _LIVE["focal_policy_ids"])
    ]
    result["p28_live"] = {
        "eligible_draw_windows": _LIVE["eligible_draw_windows"],
        "complete_reductions": _LIVE["complete_reductions"],
        "incomplete_reductions": _LIVE["incomplete_reductions"],
        "incomplete_reasons": _LIVE["incomplete_reasons"][:20],
        "changed_discard_orders": _LIVE["changed_discard_orders"],
        "provider_calls": _LIVE["provider_calls"],
        "provider_failures": _LIVE["provider_failures"],
        "provider_failure_reasons": _LIVE["provider_failure_reasons"][:20],
        "t_analysis_ms": _LIVE["t_analysis_ms"],
        "t_reduce_ms": _LIVE["t_reduce_ms"],
        "t_focal_choose_ms": _LIVE["t_focal_choose_ms"],
    }
    if is_candidate:
        total_decisions = len(requests)
        response_windows = sum(
            1
            for request in requests
            if request.observation.phase != "draw"
            or request.window_key.phase.value != "draw"
        )
        result["p28_windows"] = {
            "focal_decisions": total_decisions,
            "response_windows_exact_fallback": response_windows,
            "draw_windows": total_decisions - response_windows,
        }
    else:
        result["p28_windows"] = None
    return {"arm": arm, "source": dict(source_row), "stage": result}


def _stage_path(arm: str, source_row: Mapping[str, Any]) -> Path:
    safe_arm = arm.replace(":", "-")
    safe_source = str(source_row["source_id"]).replace(":", "-")
    return _project_file(_PROJECT_ROOT, OUT / "stages" / "{0}-{1}.json".format(safe_arm, safe_source))


def _failed_stage_path(arm: str, source_row: Mapping[str, Any]) -> Path:
    safe_arm = arm.replace(":", "-")
    safe_source = str(source_row["source_id"]).replace(":", "-")
    return _project_file(_PROJECT_ROOT, OUT / "failed-stages" / "{0}-{1}.json".format(safe_arm, safe_source))


def run() -> None:
    """并行执行冻结阶段；中断后只跳过身份仍匹配的完整文件。"""

    manifest = verify_manifest()
    authorization = json.loads((_project_file(_PROJECT_ROOT, OUT / "authorization.json")).read_text(encoding="utf-8"))
    natural.require_authorization(authorization)
    ledger = search.ActionValueLedger.load(
        _project_file(_PROJECT_ROOT, OUT / "ledger.json"),
        authorized_budgets=search.av_ledger_budgets_from_authorization(authorization),
    )
    pending = []
    completed_tables = 0
    for source_row in sources():
        for arm in manifest["arms"]:
            path = _stage_path(arm, source_row)
            if path.exists():
                row = json.loads(path.read_text(encoding="utf-8"))
                if (
                    row.get("stage", {}).get("status") != "complete"
                    or len(row["stage"].get("tables") or []) != TABLES_PER_STAGE
                ):
                    raise RuntimeError("既有阶段文件不完整: " + str(path))
                completed_tables += TABLES_PER_STAGE
            else:
                pending.append((arm, source_row))
    preexisting_complete_tables = completed_tables
    reservation = ledger.reserve(
        step_id="p28-r17-vs-r18v2:full-stages",
        account="tables_full",
        amount=manifest["planned_tables"] - completed_tables,
        note="P28 每个（臂 x 来源）完整两桌；异常按未完成预留保守结算",
    )
    failures = []
    executed_tables_this_run = 0
    usage_unknown = False
    started = time.monotonic()
    try:
        with concurrent.futures.ProcessPoolExecutor(
            max_workers=int(manifest["workers"])
        ) as pool:
            futures = {
                pool.submit(execute_stage, arm, source_row, manifest["candidates"]):
                    (arm, source_row)
                for arm, source_row in pending
            }
            for future in concurrent.futures.as_completed(futures):
                arm, source_row = futures[future]
                row = None
                try:
                    row = future.result()
                    returned_tables = len(row.get("stage", {}).get("tables") or [])
                    executed_tables_this_run += returned_tables
                    if (
                        row["stage"]["status"] != "complete"
                        or returned_tables != TABLES_PER_STAGE
                    ):
                        write_json(_failed_stage_path(arm, source_row), row)
                        raise RuntimeError(row["stage"].get("error") or "阶段未完整")
                    write_json(_stage_path(arm, source_row), row)
                    completed_tables += TABLES_PER_STAGE
                    if (completed_tables % 64 == 0
                            or completed_tables == manifest["planned_tables"]):
                        print(
                            json.dumps(
                                {
                                    "completed_tables": completed_tables,
                                    "planned_tables": manifest["planned_tables"],
                                    "wall_s": round(time.monotonic() - started, 1),
                                },
                                ensure_ascii=False,
                            ),
                            flush=True,
                        )
                except Exception as exc:  # noqa: BLE001
                    if row is None:
                        usage_unknown = True
                    failures.append(
                        {
                            "arm": arm,
                            "source": source_row,
                            "error": type(exc).__name__ + ": " + str(exc),
                            "known_executed_tables": (
                                None
                                if row is None
                                else len(row.get("stage", {}).get("tables") or [])
                            ),
                        }
                    )
    except BaseException:
        ledger.settle(
            reservation,
            usage_unknown=True,
            note="进程中断，实际执行桌数未知，按预留额度保守结算",
        )
        raise
    all_files = (
        list((_project_file(_PROJECT_ROOT, OUT / "stages")).glob("*.json")) if (_project_file(_PROJECT_ROOT, OUT / "stages")).exists() else []
    )
    actual_tables = sum(
        len(json.loads(path.read_text(encoding="utf-8"))["stage"].get("tables") or [])
        for path in all_files
    )
    if usage_unknown:
        ledger.settle(
            reservation,
            usage_unknown=True,
            note="至少一个子进程未返回阶段对象，按预留额度保守结算",
        )
    else:
        ledger.settle(
            reservation,
            actual=executed_tables_this_run,
            note="按本次成功及后置审计失败阶段实际返回的桌数结算",
        )
    write_json(
        _project_file(_PROJECT_ROOT, OUT / "run-summary.json"),
        {
            "schema": "p28-r17-vs-r18v2-run/1",
            "stage_files": len(all_files),
            "actual_tables": actual_tables,
            "preexisting_complete_tables": preexisting_complete_tables,
            "executed_tables_this_run": executed_tables_this_run,
            "usage_unknown": usage_unknown,
            "wall_seconds": round(time.monotonic() - started, 1),
            "failures": failures,
            "spent": ledger.account_summary(),
        },
    )
    expected_files = SOURCE_UNITS * len(manifest["arms"])
    if (failures or len(all_files) != expected_files
            or actual_tables != manifest["planned_tables"]):
        raise RuntimeError("P28 执行不完整")
    print(json.dumps({"status": "RUN_COMPLETE", "tables": actual_tables},
                     ensure_ascii=False))


# ============================================================ 分析
def mean(rows: list[dict[str, Any]], key: str) -> float:
    return statistics.fmean(float(row[key]) for row in rows)


def quantiles(values: list[float]) -> dict[str, float]:
    ordered = sorted(values)

    def pick(fraction: float) -> float:
        return ordered[round((len(ordered) - 1) * fraction)]

    return {
        "min": ordered[0],
        "p10": pick(0.10),
        "median": pick(0.50),
        "p90": pick(0.90),
        "max": ordered[-1],
    }


def focal_score(table: Mapping[str, Any]) -> int:
    participants = table["stage_situation"]["participant_ids_by_seat"]
    seat = participants.index(natural.FOCAL_PARTICIPANT)
    return int(table["scores_by_seat"][seat])


def fourth(stage_row: Mapping[str, Any]) -> bool:
    interval = stage_row.get("u_interval") or {}
    return interval.get("a") == 4 and interval.get("b") == 4


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "sources": len(rows),
        "first_table_delta_mean": mean(rows, "first_table_delta"),
        "stage_score_delta_mean": mean(rows, "stage_score_delta"),
        "stage_score_delta_quantiles": quantiles(
            [float(row["stage_score_delta"]) for row in rows]
        ),
        "u_delta_low_mean": mean(rows, "u_delta_low"),
        "u_delta_high_mean": mean(rows, "u_delta_high"),
        "candidate_fourth_rate": mean(rows, "candidate_fourth"),
        "baseline_fourth_rate": mean(rows, "baseline_fourth"),
        "fourth_rate_delta": (mean(rows, "candidate_fourth")
                              - mean(rows, "baseline_fourth")),
        "candidate_unresolved_rate": mean(rows, "candidate_unresolved"),
        "baseline_unresolved_rate": mean(rows, "baseline_unresolved"),
    }


def collect_live(stage_rows: list[dict[str, Any]]) -> dict[str, Any]:
    keys_int = (
        "eligible_draw_windows",
        "complete_reductions",
        "incomplete_reductions",
        "changed_discard_orders",
        "provider_calls",
        "provider_failures",
    )
    totals = {key: 0 for key in keys_int}
    t_analysis: list[float] = []
    t_reduce: list[float] = []
    t_choose: list[float] = []
    reasons: list[str] = []
    for row in stage_rows:
        live = row.get("p28_live")
        if not live:
            continue
        for key in keys_int:
            totals[key] += int(live.get(key) or 0)
        t_analysis.extend(float(v) for v in live.get("t_analysis_ms") or ())
        t_reduce.extend(float(v) for v in live.get("t_reduce_ms") or ())
        t_choose.extend(float(v) for v in live.get("t_focal_choose_ms") or ())
        reasons.extend(live.get("incomplete_reasons") or ())
    return {
        **totals,
        "incomplete_reason_samples": sorted(set(reasons))[:10],
        "analysis_cost": cost_summary(t_analysis),
        "reduction_cost": cost_summary(t_reduce),
        "focal_choose_cost": cost_summary(t_choose),
    }


def analyze() -> None:
    manifest = verify_manifest()
    run_summary = json.loads((_project_file(_PROJECT_ROOT, OUT / "run-summary.json")).read_text(encoding="utf-8"))
    if (run_summary.get("failures")
            or run_summary.get("actual_tables") != manifest["planned_tables"]):
        raise RuntimeError("执行未完整，拒绝分析")
    by_key: dict[tuple[str, str], dict[str, Any]] = {}
    all_tables = []
    for source_row in sources():
        for arm in manifest["arms"]:
            file_row = json.loads(_stage_path(arm, source_row).read_text(encoding="utf-8"))
            by_key[(arm, str(source_row["source_id"]))] = file_row["stage"]
            all_tables.extend(file_row["stage"]["tables"])
    simulation_audit = natural.execution_audit.review_tables(all_tables)

    baseline_identity: dict[str, dict[str, int]] = {}
    for source_row in sources():
        for arm in manifest["arms"]:
            stage_row = by_key[(arm, str(source_row["source_id"]))]
            for item in stage_row.get("focal_policy_ids_by_table") or ():
                bucket = baseline_identity.setdefault(arm, {})
                bucket[str(item["policy_id"])] = bucket.get(str(item["policy_id"]), 0) + 1

    results = {}
    all_paired: dict[str, list[dict[str, Any]]] = {}
    for arm in manifest["arms"]:
        if not arm.startswith("candidate:"):
            continue
        candidate_id = arm.split(":", 1)[1]
        paired = []
        stage_rows = []
        for source_row in sources():
            source_id = str(source_row["source_id"])
            baseline = by_key[("baseline", source_id)]
            candidate = by_key[(arm, source_id)]
            stage_rows.append(candidate)
            paired.append(
                {
                    **dict(source_row),
                    "candidate_id": candidate_id,
                    "baseline_first_table_score": focal_score(baseline["tables"][0]),
                    "candidate_first_table_score": focal_score(candidate["tables"][0]),
                    "first_table_delta": (
                        focal_score(candidate["tables"][0])
                        - focal_score(baseline["tables"][0])
                    ),
                    "baseline_stage_score": baseline["focal_stage_score"],
                    "candidate_stage_score": candidate["focal_stage_score"],
                    "stage_score_delta": (
                        candidate["focal_stage_score"] - baseline["focal_stage_score"]
                    ),
                    "u_delta_low": candidate["u_low"] - baseline["u_high"],
                    "u_delta_high": candidate["u_high"] - baseline["u_low"],
                    "candidate_unresolved": candidate["unresolved"],
                    "baseline_unresolved": baseline["unresolved"],
                    "candidate_fourth": fourth(candidate),
                    "baseline_fourth": fourth(baseline),
                }
            )
        window_counts = {
            "focal_decisions": 0,
            "draw_windows": 0,
            "response_windows_exact_fallback": 0,
        }
        for source_row in sources():
            windows = by_key[(arm, str(source_row["source_id"]))].get("p28_windows") or {}
            for key in window_counts:
                window_counts[key] += int(windows.get(key) or 0)
        overall = summarize(paired)
        by_mix = {
            mix: summarize([row for row in paired if row["mix"] == mix])
            for mix in MIXES
        }
        by_seat = {
            str(seat): summarize([row for row in paired if row["focal_seat"] == seat])
            for seat in SEATS
        }
        positive = [row for row in paired if row["u_delta_low"] > 0]
        results[arm] = {
            "candidate_id": candidate_id,
            "candidate_identity": manifest["candidates"][candidate_id]["identity"],
            "candidate_sha256": manifest["candidates"][candidate_id]["sha256"],
            "overall": overall,
            "by_mix": by_mix,
            "by_seat": by_seat,
            "positive_u_units": len(positive),
            "positive_u_distinct_roots": sorted({row["root_index"] for row in positive}),
            "positive_u_distinct_seats": sorted({row["focal_seat"] for row in positive}),
            "window_counts": window_counts,
            "live": collect_live(stage_rows),
        }
        all_paired[arm] = paired

    reference = None
    if "reference:v2" in by_key:
        paired = []
        for source_row in sources():
            source_id = str(source_row["source_id"])
            baseline = by_key[("baseline", source_id)]
            ref = by_key[("reference:v2", source_id)]
            paired.append(
                {
                    "mix": source_row["mix"],
                    "root_index": source_row["root_index"],
                    "focal_seat": source_row["focal_seat"],
                    "first_table_delta": (
                        focal_score(ref["tables"][0]) - focal_score(baseline["tables"][0])
                    ),
                    "u_delta_low": ref["u_low"] - baseline["u_high"],
                    "u_delta_high": ref["u_high"] - baseline["u_low"],
                    "stage_score_delta": (
                        ref["focal_stage_score"] - baseline["focal_stage_score"]
                    ),
                    "candidate_fourth": fourth(ref),
                    "baseline_fourth": fourth(baseline),
                    "candidate_unresolved": ref["unresolved"],
                    "baseline_unresolved": baseline["unresolved"],
                }
            )
        reference = {
            "arm": "reference:v2",
            "note": "旧基线（稳定 V2）减 R18 v2；不参与预登记判定，只作父代差旁证",
            "overall": summarize(paired),
            "by_mix": {
                mix: summarize([row for row in paired if row["mix"] == mix])
                for mix in MIXES
            },
        }

    judgement = {}
    for arm, row in results.items():
        u = float(row["overall"]["u_delta_low_mean"])
        s = float(row["overall"]["stage_score_delta_mean"])
        spread = (
            len(row["positive_u_distinct_roots"]) >= 2
            and len(row["positive_u_distinct_seats"]) >= 2
        )
        if u > 0 and s > 0 and spread:
            verdict = "NEXT_LEVEL_ALLOWED"
            reason = "保守 U 差>0、阶段积分差均值>0，且正效应跨>=2根与>=2座位"
        elif u > 0 and s > 0 and not spread:
            verdict = "INSUFFICIENT_SPREAD"
            reason = "两个主口径都>0，但正效应未跨>=2根与>=2座位；报实测值交回主审"
        elif u <= 0 and s <= 0:
            verdict = "CLOSE_AXIS"
            reason = "两者都 <=0，关闭 2 步公开后继搜索这条轴（在当前 R18 v2 父代之上无增量）"
        elif (u > 0) != (s > 0):
            verdict = "NO_CONCLUSION"
            reason = "保守 U 差与阶段积分差均值符号相反；不给结论，报实测值交回主审"
        else:
            verdict = "NO_CONCLUSION"
            reason = "口径未落入预登记任一行；报实测值交回主审"
        judgement[arm] = {
            "u_delta_low_mean": u,
            "stage_score_delta_mean": s,
            "fourth_rate_delta": float(row["overall"]["fourth_rate_delta"]),
            "verdict": verdict,
            "reason": reason,
        }

    result = {
        "schema": "p28-r17-vs-r18v2-result/1",
        "manifest_sha256": digest(_project_file(_PROJECT_ROOT, OUT / "manifest.json")),
        "baseline": manifest["baseline"],
        "panel_seed": manifest["panel_seed"],
        "source_units": manifest["source_units"],
        "tables_per_arm": manifest["tables_per_arm"],
        "baseline_policy_identity_by_arm": baseline_identity,
        "candidates": results,
        "reference_arm": reference,
        "judgement": judgement,
        "simulation_execution_audit": simulation_audit,
        "run_summary": run_summary,
        "strength_claim": False,
        "sign_frame": (
            "本批所有差值的符号都是相对 R18 v2（r18_integrated_positive_v2）的；"
            "R17 原批次（相对稳定 V2 为正）与本批不冲突"
        ),
    }
    write_json(
        _project_file(_PROJECT_ROOT, OUT / "paired-units.json"),
        {"schema": "p28-r17-vs-r18v2-paired/1", "by_candidate": all_paired},
    )
    write_json(_project_file(_PROJECT_ROOT, OUT / "result.json"), result)
    print(json.dumps(result, ensure_ascii=False, indent=2))


# ============================================================ 成本标定（单进程）
def cost(subset_roots: int = 2, subset_seats: int = 2) -> None:
    """单进程串行标定规则侧耗时，避免多 worker 争用污染 p99。"""

    candidates = passing_candidates()
    rows = []
    for root in ROOTS[:subset_roots]:
        for seat in SEATS[:subset_seats]:
            rows.append(
                {
                    "mix": "H",
                    "root_index": root,
                    "focal_seat": seat,
                    "source_id": "H:r{0:02d}:s{1}".format(root, seat),
                }
            )
    out = {"schema": "p28-cost-probe/1", "sources": len(rows), "arms": {}}
    for arm in ("candidate:A", "candidate:B", "baseline"):
        live_rows = []
        elapsed = 0.0
        for source_row in rows:
            started = time.monotonic()
            row = execute_stage(arm, source_row, candidates)
            elapsed += time.monotonic() - started
            if row["stage"]["status"] != "complete":
                raise RuntimeError("成本标定阶段不完整：" + str(row["stage"].get("error")))
            live_rows.append(row["stage"])
        out["arms"][arm] = {
            "tables": len(rows) * TABLES_PER_STAGE,
            "wall_seconds": round(elapsed, 1),
            "live": collect_live(live_rows),
        }
    write_json(_project_file(_PROJECT_ROOT, OUT / "cost-probe.json"), out)
    print(json.dumps(out, ensure_ascii=False, indent=2))


def smoke() -> None:
    """小样冒烟：只打印，不留产物；用于确认装配路径与量级。"""

    candidates = passing_candidates()
    rows = [
        {"mix": "H", "root_index": 1, "focal_seat": 0, "source_id": "H:r01:s0"},
        {"mix": "M", "root_index": 1, "focal_seat": 0, "source_id": "M:r01:s0"},
    ]
    for arm in ARMS:
        for source_row in rows:
            started = time.monotonic()
            row = execute_stage(arm, source_row, candidates)
            stage_row = row["stage"]
            print(
                json.dumps(
                    {
                        "arm": arm,
                        "source": source_row["source_id"],
                        "status": stage_row["status"],
                        "error": stage_row["error"],
                        "elapsed_s": round(time.monotonic() - started, 1),
                        "focal_stage_score": stage_row["focal_stage_score"],
                        "u_low": stage_row["u_low"],
                        "u_high": stage_row["u_high"],
                        "policy_ids": [
                            item["policy_id"]
                            for item in stage_row["focal_policy_ids_by_table"]
                        ],
                        "live": {
                            key: stage_row["p28_live"][key]
                            for key in (
                                "eligible_draw_windows",
                                "complete_reductions",
                                "incomplete_reductions",
                                "changed_discard_orders",
                                "provider_failures",
                            )
                        },
                        "windows": stage_row["p28_windows"],
                    },
                    ensure_ascii=False,
                ),
                flush=True,
            )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "operation", choices=("prepare", "run", "analyze", "cost", "smoke")
    )
    arguments = parser.parse_args()
    globals()[arguments.operation]()
