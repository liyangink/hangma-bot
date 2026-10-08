"""CF1：自然吃碰机会的过牌/鸣牌同快照反事实机械试点。"""

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
import asyncio
import dataclasses
import hashlib
import json
import sys
from enum import Enum
from pathlib import Path
from typing import Any, Mapping


HERE = Path(__file__).resolve().parent
ROUTE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15')
REPO = _PROJECT_ROOT
for path in (_project_file(_PROJECT_ROOT, ROUTE / "tools"), _project_file(_PROJECT_ROOT, ROUTE / "evidence/v4-impl/r9-gate2/run"), HERE):
    sys.path.insert(0, str(path))

import confirmation_execution_identity as guard  # noqa: E402
import cross_specialist_panel_a as phase_a  # noqa: E402
import cross_specialist_policy as specialist  # noqa: E402
import sitin_opportunities as opportunities  # noqa: E402
import sitin_stage as stage  # noqa: E402
import strong_seed_batch as batch  # noqa: E402
from hangma_bot.hangma.engine import HangmaRules  # noqa: E402
from hangma_bot.hangma.interface import ValueAnalysisLimits  # noqa: E402
from hangma_bot.kernel.actions import Chi, Gang, GangKind, Peng  # noqa: E402
from hangma_bot.kernel.config import RuleConfig  # noqa: E402
from hangma_bot.offline.forced_action import ForceFirstActionPolicy  # noqa: E402


OUT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/claim-counterfactual-01-20260921')
PLAN = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/claim-counterfactual-plan-20260921.json')
CONTRACT = phase_a.CONTRACT
ROUTE_SOURCE = phase_a.ROUTE_SOURCE
PANEL_SEED = 2026092301
MIXES = ("H", "M")
MAX_ROOTS_PER_MIX = 16
TARGET_HITS_PER_MIX = 4
TABLES_PER_ARM = 2
MAX_SAMPLES = 8
MAX_TABLES = MAX_SAMPLES * 2 * TABLES_PER_ARM
LABEL = "v2_pass_route_claim"


def digest(path: Path) -> str:
    """返回冻结文件 SHA-256。"""

    return hashlib.sha256(path.read_bytes()).hexdigest()


def normalize(value: Any) -> Any:
    """把玩家可见事实转成稳定 JSON 值，不读取对象私有状态。"""

    if dataclasses.is_dataclass(value):
        return normalize(dataclasses.asdict(value))
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Mapping):
        return {str(key): normalize(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [normalize(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    raise TypeError("不可序列化的公开事实类型：" + type(value).__name__)


def is_claim_action(action: Any) -> bool:
    """识别响应窗口鸣牌动作；不把暗杠或补杠当认领弃牌。"""

    if isinstance(action, (Chi, Peng)):
        return True
    return isinstance(action, Gang) and action.kind is GangKind.EXPOSED


def visible_candidate_features(request: Any, plan: Any, claim_key: str) -> dict:
    """提取学生允许读取的公开观察、规则候选事实和路线审计。"""

    by_key = {item.action_key: item for item in request.rules.legal_candidates}
    ranked = {item.action_key: item for item in plan.candidates}
    observation = request.observation
    competition = request.competition
    return {
        "schema": "r10-claim-observable-features/1",
        "phase": observation.phase,
        "remaining_tile_count": observation.remaining_tile_count,
        "scores_by_seat": list(observation.scores),
        "my_seat": observation.seat,
        "dealer_seat": observation.dealer_seat,
        "round_no": observation.round_no,
        "rule_state": normalize(observation.rule_state),
        "competition": {
            "stage_no": competition.stage_no,
            "stage_role": competition.stage_role,
            "stage_total": competition.stage_total,
            "participant_rank": competition.participant_rank,
            "ranking": normalize(competition.ranking),
        },
        "pass": {
            "facts": normalize(by_key["pass"].facts),
            "value_facts": normalize(by_key["pass"].value_facts),
        },
        "claim": {
            "action_key": claim_key,
            "facts": normalize(by_key[claim_key].facts),
            "value_facts": normalize(by_key[claim_key].value_facts),
            "route_score_trace": normalize(ranked[claim_key].score_trace),
        },
    }


class RouteChangeCapture:
    """截取 V2 过牌而冻结路线父代选择具体吃/碰的首个窗口。"""

    def __init__(self, rules_config: RuleConfig, value_limits: ValueAnalysisLimits) -> None:
        route_source = ROUTE_SOURCE.read_text(encoding="utf-8")
        self.policy = specialist.CrossSpecialistPolicy(
            rules_config,
            lambda: 800.0,
            mode="route_claim_only",
            route_source=route_source,
            identity=digest(ROUTE_SOURCE)[:16],
            value_limits=value_limits,
        )
        self.config = opportunities._driver_config()

    def __call__(self, request: Any) -> dict | None:
        if request.observation.phase not in specialist.CLAIM_PHASES:
            return None
        plan = asyncio.run(self.policy.choose(
            request, self.config.budget_policy.build(800.0, 1.0)
        ))
        audit = self.policy.audit[-1]
        if audit["status"] != "EVALUATED" or audit["base_first"] != "pass":
            return None
        claim_key = audit["selected_first"]
        chosen = next(
            (item for item in plan.candidates if item.action_key == claim_key), None
        )
        if chosen is None or not is_claim_action(chosen.action):
            return None
        return {
            "baseline_action_key": "pass",
            "claim_action_key": claim_key,
            "candidate_id": self.policy.policy_id,
            "observable_features": visible_candidate_features(request, plan, claim_key),
        }


def source_paths() -> list[Path]:
    """列出 CF1 冻结后不得漂移的代码和合同。"""

    import hangma_bot.offline.forced_action as forced_action

    return [
        Path(__file__),
        Path(opportunities.__file__),
        Path(specialist.__file__),
        Path(forced_action.__file__),
        PLAN,
        CONTRACT,
        ROUTE_SOURCE,
    ]


def prepare() -> None:
    """冻结 CF1 来源、顺序取样、预算和机械验收条件。"""

    if OUT.exists():
        raise SystemExit("CF1 目录已存在；拒绝覆盖")
    OUT.mkdir(parents=True)
    authorization = batch.unified_document(
        batch_label="r10-claim-counterfactual-cf1",
        authorization_id="r10-claim-counterfactual-cf1-20260921",
        accounts={"tables_full": MAX_TABLES, "prefix_generation": 32},
        issued_by="lead",
        issued_at_utc=batch.search.utc_now(),
        legacy_alias=False,
    )
    authorization.update({
        "issuance_basis": "用户取消旧目标并要求按文献复盘方向推进；CF1只验证反事实标签接缝、命中和成本",
        "scope": "H/M各按预登记根顺序最多检查16根并取前4个行为命中；每样本过牌/具体鸣牌两臂，各续打两桌；不训练、不选优、不确认、不发布",
        "max_model_calls": 0,
        "confirmation_roots": 0,
    })
    batch.write(_project_file(_PROJECT_ROOT, OUT / "authorization.json"), authorization)
    runtime = guard.capture(source_paths=source_paths() + [_project_file(_PROJECT_ROOT, OUT / "authorization.json")])
    manifest = {
        "schema": "r10-claim-counterfactual-cf1/1",
        "created_at_utc": batch.search.utc_now(),
        "runtime": runtime,
        "plan": str(PLAN),
        "plan_sha256": digest(PLAN),
        "contract": str(CONTRACT),
        "contract_sha256": digest(CONTRACT),
        "route_source": str(ROUTE_SOURCE),
        "route_source_sha256": digest(ROUTE_SOURCE),
        "panel_seed": PANEL_SEED,
        "mixes": list(MIXES),
        "max_roots_per_mix": MAX_ROOTS_PER_MIX,
        "target_hits_per_mix": TARGET_HITS_PER_MIX,
        "seat_schedule": "seat=(root_index-1)%4",
        "capture": "V2首选pass且冻结route_claim_only首选合法chi/peng的首个自然窗口",
        "selection": "每层按root_index升序取前4个命中；只看首动作分歧，不读取续打标签",
        "tables_per_arm": TABLES_PER_ARM,
        "max_samples": MAX_SAMPLES,
        "max_tables": MAX_TABLES,
        "mechanical_pass": "H/M均4命中；两臂完整；首动作逐字匹配；force_count=1；零非法/超时/回退/审计缺失",
        "training": False,
        "selection_effect_claim": False,
        "strength_claim": False,
        "confirmation_eligible": False,
        "release_eligible": False,
    }
    batch.write(_project_file(_PROJECT_ROOT, OUT / "manifest.json"), manifest)
    print(json.dumps({"status": "PREPARED_CF1", "max_tables": MAX_TABLES}, ensure_ascii=False))


def verify_inputs(manifest: dict) -> None:
    """每个试点执行前后核对冻结源码、合同、路线父代和计划。"""

    guard.verify(manifest["runtime"])
    for path_key, sha_key in (
        ("plan", "plan_sha256"),
        ("contract", "contract_sha256"),
        ("route_source", "route_source_sha256"),
    ):
        if digest(Path(manifest[path_key])) != manifest[sha_key]:
            raise ValueError(path_key + " 摘要漂移")


def rule_config_from_contract(contract: dict) -> RuleConfig:
    """从冻结合同构造本批唯一规则配置。"""

    versions = contract["versions"]
    return RuleConfig(
        ruleset_version=str(versions["ruleset_version"]),
        base_score=int(versions["base_score"]),
        you_cai_bi_kao=bool(versions["you_cai_bi_kao"]),
    )


def policies_for_arm(
    *,
    opponent_names: list[str],
    focal_seat: int,
    forced_action_key: str,
    target_window: Any,
    arm_name: str,
) -> tuple[list[Any], ForceFirstActionPolicy]:
    """装配一条臂：对手按合同，焦点首动作干预后恢复稳定 V2。"""

    by_seat = list(opportunities.frozen_generation_policies(
        opponent_names=opponent_names,
        focal_seat=focal_seat,
        monotonic=lambda: 800.0,
    ))
    forced = ForceFirstActionPolicy(
        by_seat[focal_seat],
        target_window=target_window,
        forced_action_key=forced_action_key,
        policy_id="offline-cf1-{0}-{1}".format(arm_name, forced_action_key),
    )
    by_seat[focal_seat] = forced
    return by_seat, forced


def one_sample(
    *,
    manifest: dict,
    contract: dict,
    mix: str,
    root_index: int,
    rules: HangmaRules,
    value_limits: ValueAnalysisLimits,
) -> dict:
    """在一个预登记来源根上寻找首个行为命中，并完成两臂续打。"""

    focal_seat = (root_index - 1) % 4
    descriptor = stage.root_descriptor(
        generator=opportunities.GENERATOR_V2_BEHAVIOR,
        sub_scenario=LABEL,
        opponent_mix=mix,
        panel_seed=PANEL_SEED,
        root_index=root_index,
    )
    source_root_id = str(descriptor["root_id"])
    match_id = "cf1-{0}-r{1:02d}-s{2}".format(mix, root_index, focal_seat)
    opponent_names = opportunities.opponent_policy_names(contract, mix)
    behavior = opportunities.frozen_generation_policies(
        opponent_names=opponent_names,
        focal_seat=focal_seat,
        monotonic=lambda: 800.0,
    )
    runtime = opportunities.build_real_runtime(
        rules_config=rules.config,
        rounds_per_game=int(contract["versions"]["rounds_per_game"]),
        seed=int(descriptor["root_seed"]),
        scenario_id=source_root_id,
    )
    capture = RouteChangeCapture(rules.config, value_limits)
    attempt = opportunities.run_real_prefix_attempt(
        runtime=runtime,
        rules=rules,
        predicate_id=LABEL,
        focal_seat=focal_seat,
        attempt_index=root_index,
        source_root_id=source_root_id,
        match_id=match_id,
        tournament_config=opportunities._snapshot_tournament_config(
            {"rounds_per_game": int(contract["versions"]["rounds_per_game"])}, rules
        ),
        seed=int(descriptor["root_seed"]),
        value_limits=value_limits,
        behavior_policies_by_seat=behavior,
        opponent_names=opponent_names,
        opponent_scenario=mix,
        capture_condition=capture,
    )
    if attempt.status != "hit":
        return {
            "status": "MISS",
            "mix": mix,
            "root_index": root_index,
            "focal_seat": focal_seat,
            "source_root_id": source_root_id,
        }

    runtime_evidence = {
        "runtime_kind": opportunities.runtime_kind_of(runtime),
        "engine_kind": opportunities.ENGINE_KIND_BY_RUNTIME_KIND[
            opportunities.runtime_kind_of(runtime)
        ],
        "execution_kind": opportunities.execution_kind_for(
            prefix_source="v2_behavior", runtime=runtime
        ),
        "runtime_source": str(runtime.get("runtime_entry")),
        "engine_identity": dict(runtime.get("engine_identity") or {}),
        "real_tables": True,
    }
    snapshot = opportunities.build_snapshot(
        prefix_source="v2_behavior",
        attempt=attempt,
        predicate_id=LABEL,
        focal_seat=focal_seat,
        opponent_scenario=mix,
        match_id=match_id,
        stage_ledger={"completed_table_scores": []},
        remaining_schedule={
            "declared_endpoint": "stage_complete",
            "remaining_tables_after_current": TABLES_PER_ARM - 1,
            "rounds_per_game": int(contract["versions"]["rounds_per_game"]),
            "tables_in_stage": TABLES_PER_ARM,
        },
        panel_seed=PANEL_SEED,
        tables_in_stage=TABLES_PER_ARM,
        rounds_per_game=int(contract["versions"]["rounds_per_game"]),
        runtime_evidence=runtime_evidence,
        descriptor=descriptor,
        witness_entry="cf1_behavior_first_hit",
    )
    witness = dict(attempt.predicate_witness or {})
    pass_key = str(witness["baseline_action_key"])
    claim_key = str(witness["claim_action_key"])
    baseline_policies, pass_policy = policies_for_arm(
        opponent_names=opponent_names,
        focal_seat=focal_seat,
        forced_action_key=pass_key,
        target_window=attempt.cut_decision.window_key,
        arm_name="pass",
    )
    candidate_policies, claim_policy = policies_for_arm(
        opponent_names=opponent_names,
        focal_seat=focal_seat,
        forced_action_key=claim_key,
        target_window=attempt.cut_decision.window_key,
        arm_name="claim",
    )
    double_arm = opportunities.run_double_arm(
        rules=rules,
        snapshot=snapshot,
        baseline_policies_by_seat=baseline_policies,
        candidate_policies_by_seat=candidate_policies,
        config=opportunities._driver_config(),
        value_limits=value_limits,
        runtime=runtime,
    )
    window_actions = double_arm.get("window_actions") or {}
    actual = {
        arm: ((window_actions.get("arms") or {}).get(arm) or {}).get("action_key")
        for arm in ("baseline", "candidate")
    }
    reviews = {
        arm: double_arm["arms"][arm].get("execution_review") or {}
        for arm in ("baseline", "candidate")
    }
    mechanical_ok = (
        bool(double_arm.get("valid"))
        and pass_policy.force_count == 1
        and claim_policy.force_count == 1
        and actual["baseline"] == pass_key
        and actual["candidate"] == claim_key
        and all(
            reviews[arm].get("status") == "complete"
            and reviews[arm].get("zero_internal_failures_verified") is True
            for arm in ("baseline", "candidate")
        )
    )
    baseline = double_arm["arms"]["baseline"]
    candidate = double_arm["arms"]["candidate"]
    return {
        "status": "HIT_VALID" if mechanical_ok else "HIT_INVALID",
        "mix": mix,
        "root_index": root_index,
        "focal_seat": focal_seat,
        "source_root_id": source_root_id,
        "root_descriptor": descriptor,
        "snapshot": snapshot,
        "witness": witness,
        "actual_cut_actions": actual,
        "force_count": {"baseline": pass_policy.force_count, "candidate": claim_policy.force_count},
        "double_arm": double_arm,
        "label": {
            "u_delta": float(candidate["u"]) - float(baseline["u"]),
            "u_low_delta": float(candidate["u_low"]) - float(baseline["u_low"]),
            "u_high_delta": float(candidate["u_high"]) - float(baseline["u_high"]),
            "focal_stage_score_delta": int(candidate["focal_stage_score"])
            - int(baseline["focal_stage_score"]),
        },
        "mechanical_ok": mechanical_ok,
    }


def run() -> None:
    """按预登记顺序执行 CF1，命中只由首动作分歧决定。"""

    manifest = batch.read(_project_file(_PROJECT_ROOT, OUT / "manifest.json"))
    verify_inputs(manifest)
    result_path = _project_file(_PROJECT_ROOT, OUT / "result.json")
    if result_path.exists():
        raise SystemExit("CF1 已执行；拒绝覆盖")
    contract = batch.read(CONTRACT)
    rules = HangmaRules(rule_config_from_contract(contract))
    value_limits = ValueAnalysisLimits()
    attempts: list[dict] = []
    hits: list[dict] = []
    for mix in MIXES:
        mix_hits = 0
        for root_index in range(1, MAX_ROOTS_PER_MIX + 1):
            sample = one_sample(
                manifest=manifest,
                contract=contract,
                mix=mix,
                root_index=root_index,
                rules=rules,
                value_limits=value_limits,
            )
            attempts.append({
                key: value
                for key, value in sample.items()
                if key not in {"snapshot", "double_arm", "witness"}
            })
            if sample["status"].startswith("HIT"):
                hits.append(sample)
                mix_hits += 1
            if mix_hits >= TARGET_HITS_PER_MIX:
                break
    counts = {
        mix: sum(1 for item in hits if item["mix"] == mix and item["status"] == "HIT_VALID")
        for mix in MIXES
    }
    all_reviews_ok = all(
        item["mechanical_ok"] for item in hits
    )
    status = (
        "PASS_CF1_MECHANICS"
        if counts == {"H": TARGET_HITS_PER_MIX, "M": TARGET_HITS_PER_MIX}
        and len(hits) == MAX_SAMPLES
        and all_reviews_ok
        else "FAIL_CF1_MECHANICS"
    )
    result = {
        "schema": "r10-claim-counterfactual-cf1-result/1",
        "status": status,
        "manifest_sha256": digest(_project_file(_PROJECT_ROOT, OUT / "manifest.json")),
        "attempts": attempts,
        "hits": hits,
        "summary": {
            "attempts": len(attempts),
            "hits": len(hits),
            "valid_hits_by_mix": counts,
            "label_u_low_deltas": [item["label"]["u_low_delta"] for item in hits],
            "full_or_partial_tables": sum(
                sum(int(value) for value in item["double_arm"]["tables_executed"].values())
                for item in hits
            ),
            "mechanical_only": True,
            "strength_claim": False,
        },
    }
    batch.write(result_path, result)
    verify_inputs(manifest)
    print(json.dumps(result["summary"] | {"status": status}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("prepare", "run"))
    args = parser.parse_args()
    globals()[args.operation]()
