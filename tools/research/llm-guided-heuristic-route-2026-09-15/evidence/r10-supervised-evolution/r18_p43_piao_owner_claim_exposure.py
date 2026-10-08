"""R18 P43：首飘后圈主首次吃碰杠机会的定向可达暴露。

本批不从稳定 P5 的自然轨迹等待抓打圈。它生成与 P3 相同规则谓词下、但
不与 P3 题库重叠的新三财神可达中局，执行合法前缀并强制一次已经验证的
首次飘白，随后由当前 P37 研究父代续打。只冻结圈主下一次摸牌以前首次
同时存在 ``pass`` 与吃、碰或明杠的正式请求；不读取该请求之后的结算。

这些来源是完整物理世界中的可重放定向状态，不冒充自然随机桌样本。若后续
教师、作者和盲态门通过，仍须另做自然可达确认和完整桌安全门。
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
import asyncio
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Mapping


HERE = Path(__file__).resolve().parent
ROUTE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15')
ROOT = _PROJECT_ROOT
for path in (_project_file(_PROJECT_ROOT, ROOT / "src"), _project_file(_PROJECT_ROOT, ROUTE / "tools"), HERE):
    sys.path.insert(0, str(path))

import confirmation_execution_identity as guard  # noqa: E402
import r18_p3_reachable_midgame as p3  # noqa: E402
import r18_p16_catch_play_natural_exposure as p16  # noqa: E402
import r18_p37_two_wealth_active_parent as p37  # noqa: E402
import sitin_natural_panel as natural  # noqa: E402
import sitin_opportunities as opportunities  # noqa: E402
import sitin_search as search  # noqa: E402
import strong_seed_batch as batch  # noqa: E402
from hangma_bot.application.audit_codec import (  # noqa: E402
    decision_request_from_json,
    decision_request_to_json,
)
from hangma_bot.hangma.catch_play import analyze_catch_play  # noqa: E402
from hangma_bot.kernel.actions import action_key  # noqa: E402
from hangma_bot.kernel.serialization import (  # noqa: E402
    window_key_from_json,
    window_key_to_json,
)
from hangma_bot.offline.forced_action import ForceFirstActionPolicy  # noqa: E402
from hangma_bot.policy.action_value_policy import ActionValuePolicy  # noqa: E402
from hangma_bot.policy.action_value_seeds import ActionValueScorer  # noqa: E402
from hangma_bot.policy.heuristic_v2 import ComparableHeuristicPolicyV2  # noqa: E402
from hangma_bot.simulation import SimulationChoice, SimulationEngine  # noqa: E402


OUT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p43-piao-owner-claim-exposure-01-20260922')
P3_BANK = p3.OUT / "bank.json"
P3_RESULT = p3.OUT / "result.json"
PARENT = p37.OUT / "candidate.py"
CONTRACT = p16.CONTRACT
LIMITS = p16.LIMITS
SOURCE_COUNT = 256
CASE_INDEX_OFFSET = 10_000
MIN_STATES = 24
MIN_PER_ROLE = 8
DEVELOPMENT_STATES = 16
MAX_HIDDEN_STATES = 16
SELECTION_SALT = "r18-p43-piao-owner-claim-split-v1"


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def value_digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")).hexdigest()


def source_path(source_id: str) -> Path:
    return _project_file(_PROJECT_ROOT, OUT / "sources" / (source_id + ".json"))


def exposure_path(source_id: str) -> Path:
    return _project_file(_PROJECT_ROOT, OUT / "exposures" / (source_id + ".json"))


def verify_preregistered() -> dict[str, Any]:
    manifest = json.loads((_project_file(_PROJECT_ROOT, OUT / "manifest.json")).read_text(encoding="utf-8"))
    for label, expected, path in (
        ("P3题库", manifest["p3_bank_sha256"], P3_BANK),
        ("P3结果", manifest["p3_result_sha256"], P3_RESULT),
        ("P37父代", manifest["parent_sha256"], PARENT),
        ("评分合同", manifest["contract_sha256"], CONTRACT),
        ("P3生成器", manifest["p3_generator_sha256"], Path(p3.__file__)),
    ):
        if expected != digest(path):
            raise ValueError(label + "漂移")
    guard.verify(manifest["runtime"])
    return manifest


def preregister() -> None:
    """在生成新来源或观察圈内机会前冻结样本量、统计单位和停止门。"""

    if OUT.exists():
        raise SystemExit("P43目录已存在；拒绝覆盖")
    p3_result = json.loads(P3_RESULT.read_text(encoding="utf-8"))
    checks = p3_result.get("checks") or {}
    if not checks or not all(checks.values()):
        raise ValueError("P3可达中局证据未通过")
    OUT.mkdir(parents=True)
    (_project_file(_PROJECT_ROOT, OUT / "sources")).mkdir()
    (_project_file(_PROJECT_ROOT, OUT / "exposures")).mkdir()
    authorization = batch.unified_document(
        batch_label=OUT.name,
        authorization_id="r18-p43-piao-owner-claim-exposure-01",
        accounts={"tables_full": SOURCE_COUNT * 2},
        issued_by="lead", issued_at_utc=search.utc_now(), legacy_alias=False,
    )
    authorization.update({
        "issuance_basis": (
            "P3首飘为正控，P18观察到4/32个圈主响应机会；扩大独立新形状，"
            "检验首飘后圈主吃碰杠家族是否有足够因果支持"
        ),
        "scope": "256个新形状各一次可达前缀生成和一次首飘后圈内暴露",
        "max_model_calls": 0,
        "confirmation_roots": 0,
    })
    write_json(_project_file(_PROJECT_ROOT, OUT / "authorization.json"), authorization)
    tracked = [
        Path(__file__), P3_BANK, P3_RESULT, PARENT, CONTRACT,
        Path(p3.__file__), Path(p16.__file__), Path(opportunities.__file__),
        _project_file(_PROJECT_ROOT, OUT / "authorization.json"),
    ]
    write_json(_project_file(_PROJECT_ROOT, OUT / "manifest.json"), {
        "schema": "r18-p43-piao-owner-claim-manifest/1",
        "phase": "PREREGISTERED_UNREAD_FOR_EXPOSURE",
        "created_at_utc": search.utc_now(),
        "runtime": guard.capture(source_paths=tracked),
        "p3_bank_sha256": digest(P3_BANK),
        "p3_result_sha256": digest(P3_RESULT),
        "p3_generator_sha256": digest(Path(p3.__file__)),
        "parent_sha256": digest(PARENT),
        "contract_sha256": digest(CONTRACT),
        "source_count": SOURCE_COUNT,
        "case_index_offset": CASE_INDEX_OFFSET,
        "roles": list(p3.ROLES),
        "role_assignment": "每连续四个来源覆盖四座，角色每四个来源交替",
        "source_exclusion": "排除P3冻结题库全部hand13；新形状之间也不得重复",
        "trajectory": "新P3谓词可达前缀+强制一次discard:白，随后当前P37父代",
        "target": (
            "首飘后、圈主下一次摸牌前，圈主首次同时可pass与chi/peng/"
            "gang:exposed的正式响应请求"
        ),
        "statistical_unit": "一个新shape_witness/完整物理世界；同源多窗口只取首次",
        "minimum_states": MIN_STATES,
        "minimum_per_role": MIN_PER_ROLE,
        "required_focal_seats": [0, 1, 2, 3],
        "development_states": DEVELOPMENT_STATES,
        "maximum_hidden_states": MAX_HIDDEN_STATES,
        "split_rule": "固定salt+request_sha256排序；前16开发、后至多16隐藏、其余保留",
        "stop_rule": "256个来源用尽即停止；不得看到结果后追加来源或降低门槛",
        "outcome_blind": True,
        "directed_reachable_not_natural": True,
        "natural_confirmation_required_after_candidate": True,
        "model_calls": 0,
        "selection_eligible": False,
        "release_eligible": False,
    })
    print(json.dumps({"status": "PREREGISTERED", "sources": SOURCE_COUNT}, ensure_ascii=False))


def _existing_p3_hands() -> set[tuple[str, ...]]:
    rows = json.loads(P3_BANK.read_text(encoding="utf-8"))["cases"]
    return {tuple(row["shape_witness"]["hand13"]) for row in rows}


def _new_shapes() -> tuple[list[dict[str, Any]], dict[str, int]]:
    """确定性生成来源，并剔除已冻结 P3 题库的 32 个形状。"""

    existing = _existing_p3_hands()
    generated, work = p3.generate_shapes(SOURCE_COUNT + len(existing) + 32)
    selected = []
    seen = set(existing)
    for shape in generated:
        hand = tuple(shape["reachability_witness"]["hand13"])
        if hand in seen:
            continue
        seen.add(hand)
        selected.append(shape)
        if len(selected) == SOURCE_COUNT:
            break
    if len(selected) != SOURCE_COUNT:
        raise RuntimeError("新P3谓词形状不足256个")
    return selected, work


async def _prepare_one(index: int, shape: dict[str, Any]) -> dict[str, Any]:
    role = p3.ROLES[((index - 1) // 4) % len(p3.ROLES)]
    case_index = CASE_INDEX_OFFSET + index
    world, focal_seat, prefix_specs = p3._world_row(  # noqa: SLF001
        shape, case_index=case_index, role=role,
    )
    request, prefix_events, runtime = await p3._capture_target(  # noqa: SLF001
        world, focal_seat, prefix_specs, shape,
    )
    request_json = decision_request_to_json(request)
    return {
        "schema": "r18-p43-piao-owner-claim-source/1",
        "source_id": "r18-p43-source-{0:03d}".format(index),
        "base_scenario_id": "r18-p43-shape-{0:03d}".format(index),
        "role": role,
        "focal_seat": focal_seat,
        "case_index": case_index,
        "shape_witness": shape["reachability_witness"],
        "shape_sha256": value_digest(shape["reachability_witness"]),
        "opening_request": request_json,
        "opening_request_sha256": value_digest(request_json),
        "full_world": world,
        "prefix_events": prefix_events,
        "generation_runtime": runtime,
    }


def prepare_sources() -> None:
    """生成并冻结 256 个不与 P3 重叠的新可达首飘来源。"""

    manifest = verify_preregistered()
    authorization = json.loads((_project_file(_PROJECT_ROOT, OUT / "authorization.json")).read_text(encoding="utf-8"))
    natural.require_authorization(authorization)
    shapes, work = _new_shapes()
    ledger = search.ActionValueLedger.load(
        _project_file(_PROJECT_ROOT, OUT / "ledger.json"),
        authorized_budgets=search.av_ledger_budgets_from_authorization(authorization),
    )
    pending = [
        (index, shape) for index, shape in enumerate(shapes, 1)
        if not source_path("r18-p43-source-{0:03d}".format(index)).exists()
    ]
    reservation = ledger.reserve(
        step_id="r18:p43-source-generation", account="tables_full",
        amount=len(pending), note="256个新形状的合法前缀与首飘目标捕获",
    )
    completed = 0
    failures = []
    try:
        for index, shape in pending:
            try:
                row = asyncio.run(_prepare_one(index, shape))
                write_json(source_path(row["source_id"]), row)
                completed += 1
            except Exception as exc:  # noqa: BLE001
                failures.append({
                    "index": index,
                    "error": type(exc).__name__ + ": " + str(exc),
                })
    finally:
        ledger.settle(reservation, actual=completed, note="按完成的可达前缀计")
    rows = []
    for index in range(1, SOURCE_COUNT + 1):
        path = source_path("r18-p43-source-{0:03d}".format(index))
        if path.exists():
            rows.append(json.loads(path.read_text(encoding="utf-8")))
    source_index = [{
        "source_id": row["source_id"],
        "role": row["role"],
        "focal_seat": row["focal_seat"],
        "shape_sha256": row["shape_sha256"],
        "opening_request_sha256": row["opening_request_sha256"],
    } for row in rows]
    write_json(_project_file(_PROJECT_ROOT, OUT / "source-index.json"), {
        "schema": "r18-p43-source-index/1", "sources": source_index,
    })
    write_json(_project_file(_PROJECT_ROOT, OUT / "source-result.json"), {
        "schema": "r18-p43-source-result/1",
        "planned": manifest["source_count"],
        "completed": len(rows),
        "newly_completed": completed,
        "failures": failures,
        "source_index_sha256": digest(_project_file(_PROJECT_ROOT, OUT / "source-index.json")),
        "generation_work": work,
        "spent": ledger.account_summary(),
    })
    if failures or len(rows) != manifest["source_count"]:
        raise RuntimeError("P43来源生成不完整")
    print(json.dumps({"status": "SOURCES_FROZEN", "sources": len(rows)}, ensure_ascii=False))


def verify_sources() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    manifest = verify_preregistered()
    source_result = json.loads((_project_file(_PROJECT_ROOT, OUT / "source-result.json")).read_text(encoding="utf-8"))
    if source_result["completed"] != manifest["source_count"] or source_result["failures"]:
        raise ValueError("P43来源没有完整冻结")
    if source_result["source_index_sha256"] != digest(_project_file(_PROJECT_ROOT, OUT / "source-index.json")):
        raise ValueError("P43来源索引漂移")
    frozen = json.loads((_project_file(_PROJECT_ROOT, OUT / "source-index.json")).read_text(encoding="utf-8"))["sources"]
    if len(frozen) != manifest["source_count"]:
        raise ValueError("P43来源数量漂移")
    for item in frozen:
        row = json.loads(source_path(item["source_id"]).read_text(encoding="utf-8"))
        if row["shape_sha256"] != item["shape_sha256"]:
            raise ValueError(item["source_id"] + " 形状漂移")
        if value_digest(row["opening_request"]) != item["opening_request_sha256"]:
            raise ValueError(item["source_id"] + " 首飘请求漂移")
    return manifest, frozen


async def expose_source(item: Mapping[str, Any]) -> dict[str, Any]:
    """执行首飘并冻结圈主下次摸牌前的首次响应机会。"""

    row = json.loads(source_path(str(item["source_id"])).read_text(encoding="utf-8"))
    world_row = row["full_world"]
    engine = SimulationEngine(p3.pilot.RULES, rules_hash=str(world_row["rules_hash"]))
    world = engine.from_replay(world_row)
    policies: list[Any] = [
        ComparableHeuristicPolicyV2(monotonic=lambda: 800.0) for _ in range(4)
    ]
    focal = int(row["focal_seat"])
    policies[focal] = ActionValuePolicy(ActionValueScorer(
        "r18-p43-parent-" + str(row["source_id"]),
        PARENT.read_text(encoding="utf-8"),
    ))
    wrappers: list[ForceFirstActionPolicy] = []
    for event in row["prefix_events"]:
        seat = int(event["seat"])
        wrapper = ForceFirstActionPolicy(
            policies[seat], target_window=window_key_from_json(event["window_key"]),
            forced_action_key=event["action_key"],
            policy_id="r18-p43-prefix-" + event["label"],
        )
        policies[seat] = wrapper
        wrappers.append(wrapper)
    opening_request = decision_request_from_json(row["opening_request"])
    opening = ForceFirstActionPolicy(
        policies[focal], target_window=opening_request.window_key,
        forced_action_key="discard:白", policy_id="r18-p43-proven-first-piao",
    )
    policies[focal] = opening
    wrappers.append(opening)
    prefix = []
    active_counts: Counter[str] = Counter()
    for _ in range(100_000):
        frame = engine.frame(world)
        if frame.final_scores is not None or frame.blocked_reason is not None:
            return {
                "schema": "r18-p43-piao-owner-claim-exposure/1",
                "source": dict(item),
                "status": "hand_complete_before_owner_claim",
                "opening_force_count": opening.force_count,
                "all_prefix_forces_once": all(value.force_count == 1 for value in wrappers),
                "active_window_counts": dict(sorted(active_counts.items())),
                "target": None,
            }
        prepared: dict[Any, tuple[Any, Any]] = {}
        for decision in frame.decisions:
            analysis = p3.pilot.RULES.analyze(decision.observation, value_limits=LIMITS)
            request = opportunities.real_window_request(
                decision=decision,
                analysis=analysis,
                match_id=str(world_row["initial"]["world_payload"]["match_id"]),
                config=p3.pilot.driver_config(), now_monotonic=lambda: 800.0,
            )
            prepared[decision.window_key] = (analysis, request)
            if opening.force_count != 1:
                continue
            context = analyze_catch_play(request.observation)
            if not context.active:
                continue
            owner = context.owner_seat == request.observation.seat and context.issue is None
            active_counts[request.observation.phase + (":owner" if owner else ":nonowner")] += 1
            if request.observation.seat != focal or not owner:
                continue
            if request.observation.phase == "draw":
                return {
                    "schema": "r18-p43-piao-owner-claim-exposure/1",
                    "source": dict(item),
                    "status": "owner_next_draw_before_claim",
                    "opening_force_count": opening.force_count,
                    "all_prefix_forces_once": all(value.force_count == 1 for value in wrappers),
                    "active_window_counts": dict(sorted(active_counts.items())),
                    "target": None,
                }
            legal = [candidate.action_key for candidate in request.rules.legal_candidates]
            claims = [key for key in legal if key.startswith((
                "chi:", "peng:", "gang:exposed:",
            ))]
            if "pass" not in legal or not claims:
                continue
            plan = await policies[focal].choose(
                request,
                p3.pilot.driver_config().budget_policy.build(800.0, decision.timeout_seconds),
            )
            if not plan.candidates:
                raise RuntimeError("P37在圈主响应目标没有动作")
            request_json = decision_request_to_json(request)
            return {
                "schema": "r18-p43-piao-owner-claim-exposure/1",
                "source": dict(item),
                "status": "hit",
                "opening_force_count": opening.force_count,
                "all_prefix_forces_once": all(value.force_count == 1 for value in wrappers),
                "active_window_counts": dict(sorted(active_counts.items())),
                "target": {
                    "request": request_json,
                    "request_sha256": value_digest(request_json),
                    "prefix": prefix,
                    "reference_action": plan.candidates[0].action_key,
                    "claim_action_keys": claims,
                    "legal_action_keys": legal,
                    "phase": request.observation.phase,
                    "round_no": request.observation.round_no,
                    "snapshot_seq": request.observation.snapshot_seq,
                    "remaining_tile_count": request.observation.remaining_tile_count,
                    "catch_play_owner_seat": context.owner_seat,
                    "chain_piao": request.observation.chain_piao,
                    "chain_count": request.observation.rule_state.chain_count,
                },
            }
        choices = []
        for decision in frame.decisions:
            analysis, request = prepared[decision.window_key]
            plan = await policies[int(decision.window_key.seat)].choose(
                request,
                p3.pilot.driver_config().budget_policy.build(800.0, decision.timeout_seconds),
            )
            if not plan.candidates:
                raise RuntimeError("P43前缀策略没有动作")
            action = plan.candidates[0].action
            key = action_key(action)
            if not any(candidate.action_key == key for candidate in analysis.legal_candidates):
                raise RuntimeError("P43前缀策略返回非法动作：" + key)
            choices.append(SimulationChoice(decision.window_key, action))
        world = engine.advance(world, frame.revision, tuple(choices))
        prefix.extend({
            "window_key": window_key_to_json(choice.window_key),
            "action_key": action_key(choice.action),
        } for choice in choices)
    raise RuntimeError("P43轨迹超过步数上限")


def run_exposure() -> None:
    manifest, frozen = verify_sources()
    authorization = json.loads((_project_file(_PROJECT_ROOT, OUT / "authorization.json")).read_text(encoding="utf-8"))
    natural.require_authorization(authorization)
    ledger = search.ActionValueLedger.load(
        _project_file(_PROJECT_ROOT, OUT / "ledger.json"),
        authorized_budgets=search.av_ledger_budgets_from_authorization(authorization),
    )
    pending = [item for item in frozen if not exposure_path(item["source_id"]).exists()]
    reservation = ledger.reserve(
        step_id="r18:p43-owner-claim-exposure", account="tables_full",
        amount=len(pending), note="256个首飘后圈主响应机会暴露",
    )
    completed = 0
    failures = []
    try:
        for item in pending:
            try:
                result = asyncio.run(expose_source(item))
                if result["opening_force_count"] != 1 or not result["all_prefix_forces_once"]:
                    raise RuntimeError("P43前缀或首次飘白未恰好强制一次")
                write_json(exposure_path(str(item["source_id"])), result)
                completed += 1
            except Exception as exc:  # noqa: BLE001
                failures.append({
                    "source_id": item["source_id"],
                    "error": type(exc).__name__ + ": " + str(exc),
                })
    finally:
        ledger.settle(reservation, actual=completed, note="按完成的首飘后轨迹计")
    write_json(_project_file(_PROJECT_ROOT, OUT / "run-summary.json"), {
        "schema": "r18-p43-run-summary/1",
        "planned": manifest["source_count"],
        "completed": completed,
        "failures": failures,
        "spent": ledger.account_summary(),
    })
    if failures or completed != len(frozen):
        raise RuntimeError("P43圈主响应暴露执行不完整")
    print(json.dumps({"status": "EXPOSURE_COMPLETE", "sources": completed}, ensure_ascii=False))


def analyze() -> None:
    manifest, frozen = verify_sources()
    summary = json.loads((_project_file(_PROJECT_ROOT, OUT / "run-summary.json")).read_text(encoding="utf-8"))
    if summary["failures"] or summary["completed"] != manifest["source_count"]:
        raise ValueError("P43执行不完整")
    hits = []
    status_counts: Counter[str] = Counter()
    for item in frozen:
        row = json.loads(exposure_path(str(item["source_id"])).read_text(encoding="utf-8"))
        status_counts[row["status"]] += 1
        if row["target"] is not None:
            hits.append({"source": row["source"], **row["target"]})
    ordered = sorted(
        hits,
        key=lambda row: hashlib.sha256(
            (SELECTION_SALT + "|" + row["request_sha256"]).encode("utf-8")
        ).hexdigest(),
    )
    development = ordered[:DEVELOPMENT_STATES]
    hidden = ordered[DEVELOPMENT_STATES:DEVELOPMENT_STATES + MAX_HIDDEN_STATES]
    reserve = ordered[DEVELOPMENT_STATES + MAX_HIDDEN_STATES:]
    role_counts = Counter(row["source"]["role"] for row in hits)
    seats = sorted({int(row["source"]["focal_seat"]) for row in hits})
    gate = (
        len(hits) >= MIN_STATES
        and all(role_counts[role] >= MIN_PER_ROLE for role in p3.ROLES)
        and seats == manifest["required_focal_seats"]
        and len(development) == DEVELOPMENT_STATES
        and len(hidden) >= MIN_STATES - DEVELOPMENT_STATES
    )
    write_json(_project_file(_PROJECT_ROOT, OUT / "targets.json"), {
        "schema": "r18-p43-piao-owner-claim-targets/1",
        "selection_salt": SELECTION_SALT,
        "development": development,
        "hidden": hidden,
        "reserve": reserve,
        "hidden_labels_opened": False,
    })
    result = {
        "schema": "r18-p43-piao-owner-claim-result/1",
        "status": "OPEN_P44_DEVELOPMENT_TEACHER" if gate else "CLOSE_OWNER_CLAIM_INSUFFICIENT_SUPPORT",
        "sources": len(frozen),
        "status_counts": dict(sorted(status_counts.items())),
        "eligible_states": len(hits),
        "independent_sources": len({row["source"]["source_id"] for row in hits}),
        "role_counts": dict(sorted(role_counts.items())),
        "focal_seats": seats,
        "phase_counts": dict(sorted(Counter(row["phase"] for row in hits).items())),
        "claim_family_counts": dict(sorted(Counter(
            key.split(":", 1)[0]
            for row in hits for key in row["claim_action_keys"]
        ).items())),
        "reference_action_counts": dict(sorted(Counter(
            row["reference_action"] for row in hits
        ).items())),
        "passes_exposure_gate": gate,
        "development_states": len(development),
        "hidden_states": len(hidden),
        "reserve_states": len(reserve),
        "directed_reachable_not_natural": True,
        "outcome_labels_generated": False,
        "hidden_labels_opened": False,
        "next": (
            "冻结P44多臂共同隐藏世界教师；先比较pass与每个合法claim，开发有稳定信号才调用作者模型"
            if gate else
            "关闭首飘后圈主claim主动路线；不得追加来源、降低门槛或用同源变体补数"
        ),
        "selection_eligible": False,
        "release_eligible": False,
    }
    write_json(_project_file(_PROJECT_ROOT, OUT / "result.json"), result)
    print(json.dumps(result, ensure_ascii=False, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("preregister", "prepare", "run", "analyze"))
    command = parser.parse_args().command
    if command == "preregister":
        preregister()
    elif command == "prepare":
        prepare_sources()
    elif command == "run":
        run_exposure()
    else:
        analyze()


if __name__ == "__main__":
    main()
