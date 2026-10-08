"""R18 P22：赛事处境是否改变三财神“立即胡/首飘”偏好的首尺。

本批只回答是否存在可编码的赛事处境增益，不生成候选。输入由两类既有
冻结事实组成：P3 的可达三财神中局，以及 P5 正式两桌阶段第一桌的真实积分
分布。每个 P3 世界保持目标局物理事实不变，并由正式 ``SimulationEngine``
继续生成第 2—8 局；同一基础世界在 12 个阶段处境下分别强制 ``hu`` 与
``discard:白``，用官方组内阶段前二目标 ``group_advance_v1`` 计算效用。

12 个处境不增加独立样本数；统计根始终是 16 个基础世界。当前 P5 虽不读取
赛事账，仍逐处境实际执行，以验证 ``StageSituationProjection`` 到正式
``BotPolicy.choose`` 的投影链，并为后续候选留下可复算请求证据。
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
import concurrent.futures
from dataclasses import asdict, replace
import hashlib
import json
from pathlib import Path
import statistics
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
import sitin_natural_panel as natural  # noqa: E402
import sitin_opportunities as opportunities  # noqa: E402
import sitin_search as search  # noqa: E402
import sitin_stage as stage  # noqa: E402
import strong_seed_batch as batch  # noqa: E402
from hangma_bot.application.audit_codec import (  # noqa: E402
    decision_request_to_json,
)
from hangma_bot.kernel.actions import action_key  # noqa: E402
from hangma_bot.kernel.serialization import window_key_from_json  # noqa: E402
from hangma_bot.offline.evaluate import (  # noqa: E402
    StageSituationProjection,
    frame_observation_summary,
    resume_match,
)
from hangma_bot.offline.forced_action import ForceFirstActionPolicy  # noqa: E402
from hangma_bot.policy.action_value_policy import (  # noqa: E402
    ActionValuePolicy,
    build_scoring_view,
)
from hangma_bot.policy.action_value_seeds import ActionValueScorer  # noqa: E402
from hangma_bot.policy.heuristic_v2 import ComparableHeuristicPolicyV2  # noqa: E402
from hangma_bot.simulation import SimulationChoice, SimulationEngine  # noqa: E402


OUT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p22-competition-situation-headroom-01-20260922')
P3_BANK = p3.OUT / "bank.json"
P3_RESULT = p3.OUT / "result.json"
P5_STAGE_DIR = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p5-table-safety-01-20260922/stages')
PARENT = p16.PARENT
CONTRACT = p16.CONTRACT
LIMITS = p16.LIMITS
ROLE_DEVELOPMENT = 8
CONTEXTS_PER_RANK = 3
TABLE_ROUNDS = 8
WORKERS = 8
SOURCE_SALT = "r18-p22-source-split-v1"
PLANNED_ROOTS = ROLE_DEVELOPMENT * 2
PLANNED_CONTEXTS = CONTEXTS_PER_RANK * 4
PLANNED_TABLES = PLANNED_ROOTS * PLANNED_CONTEXTS * 2


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


def p3_cases() -> list[dict[str, Any]]:
    result = json.loads(P3_RESULT.read_text(encoding="utf-8"))
    if not result.get("checks") or not all(result["checks"].values()):
        raise ValueError("P3 可达中局未通过冻结检查")
    rows = json.loads(P3_BANK.read_text(encoding="utf-8"))["cases"]
    if len(rows) != 32:
        raise ValueError("P3 来源必须恰有 32 个基础世界")
    return rows


def split_sources() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """每个角色结果盲选择 8 个开发根，其余只登记身份、不运行标签。"""

    development: list[dict[str, Any]] = []
    replication: list[dict[str, Any]] = []
    roles = sorted({str(row["role"]) for row in p3_cases()})
    for role in roles:
        rows = [row for row in p3_cases() if row["role"] == role]
        ordered = sorted(rows, key=lambda row: hashlib.sha256(
            (SOURCE_SALT + "|" + str(row["request_sha256"])).encode("utf-8")
        ).hexdigest())
        for split, selected in (
            ("development", ordered[:ROLE_DEVELOPMENT]),
            ("replication", ordered[ROLE_DEVELOPMENT:]),
        ):
            target = development if split == "development" else replication
            target.extend({
                "case_id": row["case_id"],
                "role": row["role"],
                "focal_seat": row["focal_seat"],
                "request_sha256": row["request_sha256"],
                "split": split,
            } for row in selected)
    if len(development) != PLANNED_ROOTS or len(replication) != PLANNED_ROOTS:
        raise ValueError("P22 来源拆分必须为 16 开发 + 16 复验")
    return development, replication


def stage_evidence_paths() -> list[Path]:
    paths = sorted(P5_STAGE_DIR.glob("parent-*.json"))
    if len(paths) != 32:
        raise ValueError("P5 正式父代阶段证据必须恰有 32 个来源单元")
    return paths


def empirical_context_pool() -> list[dict[str, Any]]:
    """从 P5 正式两桌阶段的第一桌抽取可复算、无并列的真实阶段账。"""

    pool = []
    for path in stage_evidence_paths():
        document = json.loads(path.read_text(encoding="utf-8"))
        table = document["stage"]["tables"][0]
        ids = list(table["stage_situation"]["participant_ids_by_seat"])
        scores = [int(value) for value in table["scores_by_seat"]]
        points = list(stage.place_points_for_table(scores))
        score_by_id = {ids[index]: scores[index] for index in range(4)}
        point_by_id = {ids[index]: points[index] for index in range(4)}
        if "focal" not in score_by_id:
            raise ValueError("P5 阶段证据缺焦点参赛者：" + str(path))
        opponents = sorted(pid for pid in ids if pid != "focal")
        canonical_ids = ["focal"] + opponents
        canonical_scores = [score_by_id[pid] for pid in canonical_ids]
        canonical_points = [point_by_id[pid] for pid in canonical_ids]
        rows = [
            stage.LedgerRow(
                participant_id=canonical_ids[index],
                total_score=canonical_scores[index],
                place_points=canonical_points[index],
            )
            for index in range(4)
        ]
        interval = next(
            item for item in stage.group_advance_intervals(rows)
            if item["participant_id"] == "focal"
        )
        if interval["a"] != interval["b"]:
            continue
        focal_rank = int(interval["a"])
        ordered_scores = sorted(canonical_scores, reverse=True)
        second_score = ordered_scores[1]
        third_score = ordered_scores[2]
        boundary_margin = (
            canonical_scores[0] - third_score
            if focal_rank <= 2 else canonical_scores[0] - second_score
        )
        pool.append({
            "source_id": document["source"]["source_id"],
            "source_path": str(path.relative_to(ROOT)),
            "source_sha256": digest(path),
            "focal_rank_after_first_table": focal_rank,
            "boundary_margin": int(boundary_margin),
            "scores_canonical": canonical_scores,
            "place_points_canonical": canonical_points,
            "canonical_participants": canonical_ids,
        })
    return pool


def select_contexts() -> list[dict[str, Any]]:
    """每个真实名次层取边界距离最小、中位、最大三个分位点。"""

    selected = []
    for rank in range(1, 5):
        rows = sorted(
            (row for row in empirical_context_pool()
             if row["focal_rank_after_first_table"] == rank),
            key=lambda row: (abs(row["boundary_margin"]), row["source_id"]),
        )
        if len(rows) < CONTEXTS_PER_RANK:
            raise ValueError("真实阶段积分的名次层 {0} 不足 3 个".format(rank))
        indices = (0, len(rows) // 2, len(rows) - 1)
        for quantile, index in zip(("boundary", "middle", "extreme"), indices):
            row = dict(rows[index])
            row["context_id"] = "rank{0}-{1}".format(rank, quantile)
            row["quantile"] = quantile
            selected.append(row)
    if len({row["source_id"] for row in selected}) != PLANNED_CONTEXTS:
        raise ValueError("P22 真实阶段处境选择不得重复来源")
    return selected


def source_case(case_id: str) -> dict[str, Any]:
    return next(row for row in p3_cases() if row["case_id"] == case_id)


def rollout_path(source: Mapping[str, Any], context: Mapping[str, Any]) -> Path:
    return _project_file(_PROJECT_ROOT, OUT / "rollouts" / "{0}-{1}.json".format(
        source["case_id"], context["context_id"],
    ))


def prepare() -> None:
    """在读取新续打结果前冻结基础根、真实阶段处境、预算和通过判据。"""

    if OUT.exists():
        raise SystemExit("P22 目录已存在；拒绝覆盖")
    development, replication = split_sources()
    contexts = select_contexts()
    OUT.mkdir(parents=True)
    (_project_file(_PROJECT_ROOT, OUT / "rollouts")).mkdir()
    authorization = batch.unified_document(
        batch_label=OUT.name,
        authorization_id="r18-p22-competition-situation-headroom-01",
        accounts={"tables_full": PLANNED_TABLES},
        issued_by="lead", issued_at_utc=search.utc_now(), legacy_alias=False,
    )
    authorization.update({
        "issuance_basis": "P20/P21关闭非支配杠取舍；按计划转向赛事处境下已证实三财神首飘",
        "scope": "16开发根×12个真实首桌处境×立即胡/首飘；16复验根标签封存",
        "max_model_calls": 0,
        "confirmation_roots": 0,
    })
    write_json(_project_file(_PROJECT_ROOT, OUT / "authorization.json"), authorization)
    write_json(_project_file(_PROJECT_ROOT, OUT / "sources.json"), {
        "schema": "r18-p22-sources/1",
        "selection_salt": SOURCE_SALT,
        "development": development,
        "replication": replication,
        "replication_labels_opened": False,
    })
    write_json(_project_file(_PROJECT_ROOT, OUT / "contexts.json"), {
        "schema": "r18-p22-empirical-stage-contexts/1",
        "population": "P5 正式桌赛安全门父代臂的 32 个第一桌结果；排除已知键并列",
        "selection": "按焦点第一桌后名次分层；边界距离排序取最小/中位/最大",
        "contexts": contexts,
    })
    tracked = [
        Path(__file__), P3_BANK, P3_RESULT, PARENT, CONTRACT,
        Path(p3.__file__), Path(p16.__file__), Path(opportunities.__file__),
        *stage_evidence_paths(), _project_file(_PROJECT_ROOT, OUT / "authorization.json"),
        _project_file(_PROJECT_ROOT, OUT / "sources.json"), _project_file(_PROJECT_ROOT, OUT / "contexts.json"),
    ]
    write_json(_project_file(_PROJECT_ROOT, OUT / "manifest.json"), {
        "schema": "r18-p22-competition-situation-headroom-manifest/1",
        "created_at_utc": search.utc_now(),
        "runtime": guard.capture(source_paths=tracked),
        "p3_bank_sha256": digest(P3_BANK),
        "p3_result_sha256": digest(P3_RESULT),
        "parent_sha256": digest(PARENT),
        "contract_sha256": digest(CONTRACT),
        "sources_sha256": digest(_project_file(_PROJECT_ROOT, OUT / "sources.json")),
        "contexts_sha256": digest(_project_file(_PROJECT_ROOT, OUT / "contexts.json")),
        "development_roots": len(development),
        "replication_roots": len(replication),
        "contexts": len(contexts),
        "planned_tables": PLANNED_TABLES,
        "workers": WORKERS,
        "table_rounds": TABLE_ROUNDS,
        "world_lift": (
            "P3 full_world 的目标局保持不变；from_replay 后仅把 rounds_per_game "
            "从单局证据的 1 提升为正式 8，后续局由同一 SimulationEngine/seed 生成"
        ),
        "request_schema_upgrade": (
            "P3 冻结后评分视图升至 /4；身份核对只归一新增且由 hangma 生产的 "
            "CandidateFacts.baotou_after，其他观察/规则字段必须逐值相同"
        ),
        "sampling_unit": "16 个 P3 基础世界；12 个赛事处境是同根反事实，不增加 n",
        "primary_outcome": "group_advance_v1 的保守识别区间严格支配",
        "headroom_gate": {
            "all_tables_complete": True,
            "zero_runtime_failures": True,
            "context_projection_exact": True,
            "strict_preference_flip_roots_at_least": 6,
            "roots_with_piao_strictly_better_at_least": 3,
            "roots_with_hu_strictly_better_at_least": 3,
        },
        "interpretation": (
            "通过只授权扩展赛事处境表示并生成小候选；不等于隐藏准入、桌赛非劣或发布"
        ),
        "replication_labels_opened": False,
        "model_calls": 0,
        "selection_eligible": False,
        "release_eligible": False,
    })
    print(json.dumps({
        "status": "PREPARED", "development_roots": len(development),
        "contexts": len(contexts), "planned_tables": PLANNED_TABLES,
    }, ensure_ascii=False))


def verify() -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    manifest = json.loads((_project_file(_PROJECT_ROOT, OUT / "manifest.json")).read_text(encoding="utf-8"))
    checks = {
        "P3题库": (manifest["p3_bank_sha256"], digest(P3_BANK)),
        "P3结果": (manifest["p3_result_sha256"], digest(P3_RESULT)),
        "P5父代": (manifest["parent_sha256"], digest(PARENT)),
        "合同": (manifest["contract_sha256"], digest(CONTRACT)),
        "来源": (manifest["sources_sha256"], digest(_project_file(_PROJECT_ROOT, OUT / "sources.json"))),
        "处境": (manifest["contexts_sha256"], digest(_project_file(_PROJECT_ROOT, OUT / "contexts.json"))),
    }
    for label, (expected, actual) in checks.items():
        if expected != actual:
            raise ValueError(label + "漂移")
    guard.verify(manifest["runtime"])
    frozen_sources = json.loads((_project_file(_PROJECT_ROOT, OUT / "sources.json")).read_text(encoding="utf-8"))
    development, replication = split_sources()
    if frozen_sources["development"] != development or frozen_sources["replication"] != replication:
        raise ValueError("P22 来源不能按冻结 salt 重建")
    contexts = json.loads((_project_file(_PROJECT_ROOT, OUT / "contexts.json")).read_text(encoding="utf-8"))["contexts"]
    if contexts != select_contexts():
        raise ValueError("P22 赛事处境不能从 P5 阶段分布重建")
    return manifest, development, contexts


class CaptureTargetPolicy:
    """在正式策略接缝中记录目标请求；记录后原样委托。"""

    def __init__(self, inner: Any, target_window: Any) -> None:
        self.inner = inner
        self.target_window = target_window
        self.policy_id = getattr(inner, "policy_id", "r18-p22-capture")
        self.max_operations = getattr(inner, "max_operations", None)
        self.requests: list[Any] = []

    async def choose(self, request: Any, budget: Any) -> Any:
        if request.window_key == self.target_window:
            self.requests.append(request)
        return await self.inner.choose(request, budget)


def physical_context(
    context: Mapping[str, Any], focal_seat: int,
) -> tuple[StageSituationProjection, tuple[str, str, str, str]]:
    participants = opportunities.participant_ids_by_seat(focal_seat)
    opponent_ids = sorted(pid for pid in participants if pid != opportunities.FOCAL_PARTICIPANT)
    canonical_ids = [opportunities.FOCAL_PARTICIPANT] + opponent_ids
    scores_by_id = {
        canonical_ids[index]: int(context["scores_canonical"][index])
        for index in range(4)
    }
    points_by_id = {
        canonical_ids[index]: int(context["place_points_canonical"][index])
        for index in range(4)
    }
    scores = tuple(scores_by_id[pid] for pid in participants)
    points = tuple(points_by_id[pid] for pid in participants)
    projection = StageSituationProjection(
        stage_table_no=2,
        tables_in_stage=2,
        tables_completed=1,
        rounds_per_game=TABLE_ROUNDS,
        stage_scores_by_seat=scores,  # type: ignore[arg-type]
        place_points_by_seat=points,  # type: ignore[arg-type]
        participant_ids_by_seat=participants,
    )
    return projection, participants


def policies_for_arm(
    row: Mapping[str, Any], action: str, label: str,
) -> tuple[list[Any], list[ForceFirstActionPolicy], CaptureTargetPolicy]:
    policies: list[Any] = [
        ComparableHeuristicPolicyV2(monotonic=lambda: 800.0) for _ in range(4)
    ]
    focal = int(row["focal_seat"])
    policies[focal] = ActionValuePolicy(ActionValueScorer(
        "r18-p22-p5-" + label, PARENT.read_text(encoding="utf-8"),
    ))
    wrappers: list[ForceFirstActionPolicy] = []
    for event in row["prefix_events"]:
        seat = int(event["seat"])
        wrapper = ForceFirstActionPolicy(
            policies[seat],
            target_window=window_key_from_json(event["window_key"]),
            forced_action_key=str(event["action_key"]),
            policy_id="r18-p22-prefix-" + str(event["label"]),
        )
        policies[seat] = wrapper
        wrappers.append(wrapper)
    target_window = window_key_from_json(row["request"]["window_key"])
    target = ForceFirstActionPolicy(
        policies[focal], target_window=target_window,
        forced_action_key=action, policy_id="r18-p22-target-" + label,
    )
    wrappers.append(target)
    capture = CaptureTargetPolicy(target, target_window)
    policies[focal] = capture
    return policies, wrappers, capture


def request_identity_without_competition(request_json: Mapping[str, Any]) -> dict[str, Any]:
    """赛事投影允许变化；动作窗口、观察与规则事实必须与 P3 冻结请求一致。"""

    rules = json.loads(json.dumps(request_json["rules"], ensure_ascii=False))
    for candidate in rules.get("legal_candidates") or []:
        facts = candidate.get("facts")
        if isinstance(facts, dict):
            facts.pop("baotou_after", None)
    return {
        "window_key": request_json["window_key"],
        "observation": request_json["observation"],
        "rules": rules,
        "trigger_seq": request_json["trigger_seq"],
    }


async def run_arm(
    row: Mapping[str, Any], context: Mapping[str, Any], action: str, label: str,
) -> dict[str, Any]:
    world_row = row["full_world"]
    engine = SimulationEngine(p3.pilot.RULES, rules_hash=str(world_row["rules_hash"]))
    imported = engine.from_replay(world_row)
    first_summary = frame_observation_summary(engine.frame(imported))
    world = replace(imported, rounds_per_game=TABLE_ROUNDS, history_consistent=False)
    if frame_observation_summary(engine.frame(world)) != first_summary:
        raise ValueError("提升桌局数改变了 P3 首帧公开观察")
    projection, participants = physical_context(context, int(row["focal_seat"]))
    policies, wrappers, capture = policies_for_arm(row, action, label)
    outcome = await resume_match(
        engine=engine, world=world, policies_by_seat=tuple(policies),
        rules=p3.pilot.RULES, choice_factory=SimulationChoice,
        config=p3.pilot.driver_config(), now_monotonic=lambda: 800.0,
        wall_clock=None,
        remaining_schedule={
            "declared_endpoint": "current_table_end",
            "stage_table_no": 2,
            "tables_in_stage": 2,
            "remaining_tables_after_current": 0,
        },
        stage_snapshot={
            "observation_summary": first_summary,
            "match_spec": {"match_id": world_row["initial"]["world_payload"]["match_id"]},
        },
        value_limits=LIMITS,
        stage_situation=projection,
    )
    if len(capture.requests) != 1:
        raise RuntimeError("目标窗口请求必须恰好捕获一次，实际 {0}".format(len(capture.requests)))
    captured_json = decision_request_to_json(capture.requests[0])
    captured_identity = request_identity_without_competition(captured_json)
    frozen_identity = request_identity_without_competition(row["request"])
    if captured_identity != frozen_identity:
        mismatches = {
            key: (value_digest(frozen_identity[key]), value_digest(captured_identity[key]))
            for key in frozen_identity if frozen_identity[key] != captured_identity[key]
        }
        raise ValueError(
            "P22 目标请求除赛事处境外与 P3 冻结请求不一致：" + repr(mismatches)
        )
    view = build_scoring_view(capture.requests[0], value_limits=LIMITS).candidate_view()
    expected_scores = list(projection.stage_scores_by_seat)
    competition = view.get("competition") or {}
    projection_exact = bool(
        list(competition.get("stage_scores") or ()) == expected_scores
        and list(competition.get("current_stage_scores") or ()) == expected_scores
        and list(competition.get("table_scores") or ()) == [0, 0, 0, 0]
        and list(competition.get("freshness_masks") or ())
        == ["stage_account:complete", "table_account:live"]
    )
    final_scores = None if outcome.final_scores is None else [int(x) for x in outcome.final_scores]
    all_forces_once = all(wrapper.force_count == 1 for wrapper in wrappers)
    mechanical = bool(
        outcome.status == "complete"
        and outcome.completed_hands == TABLE_ROUNDS
        and final_scores is not None
        and all_forces_once
        and projection_exact
        and all(value == 0 for value in asdict(outcome.runtime_counts).values())
    )
    return {
        "status": outcome.status,
        "completed_hands": outcome.completed_hands,
        "final_scores_by_seat": final_scores,
        "place_points_by_seat": (
            None if final_scores is None else list(stage.place_points_for_table(final_scores))
        ),
        "participants_by_seat": list(participants),
        "force_counts": [wrapper.force_count for wrapper in wrappers],
        "all_forces_once": all_forces_once,
        "runtime_counts": asdict(outcome.runtime_counts),
        "captured_competition": competition,
        "projection_exact": projection_exact,
        "decisions": len(outcome.decisions),
        "error_reason": outcome.error_reason,
        "mechanical_ok": mechanical,
    }


def utility(
    context: Mapping[str, Any], arm: Mapping[str, Any], focal_seat: int,
) -> dict[str, Any]:
    projection, participants = physical_context(context, focal_seat)
    scores = list(arm["final_scores_by_seat"])
    points = list(arm["place_points_by_seat"])
    rows = []
    for seat, participant in enumerate(participants):
        rows.append(stage.LedgerRow(
            participant_id=participant,
            total_score=int(projection.stage_scores_by_seat[seat]) + int(scores[seat]),
            place_points=int(projection.place_points_by_seat[seat]) + int(points[seat]),
        ))
    result = stage.group_advance_utility(
        rows, focal_id=opportunities.FOCAL_PARTICIPANT,
    )
    result["totals_by_participant"] = {
        row.participant_id: row.total_score for row in rows
    }
    result["place_points_by_participant"] = {
        row.participant_id: row.place_points for row in rows
    }
    return result


def execute_pair(source: Mapping[str, Any], context: Mapping[str, Any]) -> dict[str, Any]:
    row = source_case(str(source["case_id"]))
    prefix = str(source["case_id"]) + "-" + str(context["context_id"])
    hu = asyncio.run(run_arm(row, context, "hu", prefix + "-hu"))
    piao = asyncio.run(run_arm(row, context, "discard:白", prefix + "-piao"))
    focal = int(source["focal_seat"])
    hu_u = utility(context, hu, focal) if hu["mechanical_ok"] else None
    piao_u = utility(context, piao, focal) if piao["mechanical_ok"] else None
    mechanical = hu["mechanical_ok"] and piao["mechanical_ok"]
    return {
        "schema": "r18-p22-competition-situation-rollout/1",
        "case_id": source["case_id"],
        "role": source["role"],
        "focal_seat": focal,
        "context_id": context["context_id"],
        "context_source_id": context["source_id"],
        "context_rank": context["focal_rank_after_first_table"],
        "context_scores_canonical": context["scores_canonical"],
        "context_place_points_canonical": context["place_points_canonical"],
        "hu": hu,
        "piao": piao,
        "hu_utility": hu_u,
        "piao_utility": piao_u,
        "mechanical_ok": mechanical,
    }


def run() -> None:
    manifest, sources, contexts = verify()
    authorization = json.loads((_project_file(_PROJECT_ROOT, OUT / "authorization.json")).read_text(encoding="utf-8"))
    natural.require_authorization(authorization)
    ledger = search.ActionValueLedger.load(
        _project_file(_PROJECT_ROOT, OUT / "ledger.json"),
        authorized_budgets=search.av_ledger_budgets_from_authorization(authorization),
    )
    pending = []
    completed_tables = 0
    for source in sources:
        for context in contexts:
            path = rollout_path(source, context)
            if path.exists():
                row = json.loads(path.read_text(encoding="utf-8"))
                if not row.get("mechanical_ok"):
                    raise ValueError("既有 P22 配对机械条件失败：" + str(path))
                completed_tables += 2
            else:
                pending.append((source, context))
    reservation = ledger.reserve(
        step_id="r18:p22-competition-situation:run", account="tables_full",
        amount=manifest["planned_tables"] - completed_tables,
        note="16开发根×12真实第一桌处境×立即胡/首飘的8局当前桌",
    )
    failures = []
    executed = 0
    usage_unknown = False
    try:
        with concurrent.futures.ProcessPoolExecutor(max_workers=manifest["workers"]) as pool:
            futures = {
                pool.submit(execute_pair, source, context): (source, context)
                for source, context in pending
            }
            for future in concurrent.futures.as_completed(futures):
                source, context = futures[future]
                row = None
                try:
                    row = future.result()
                    if not row["mechanical_ok"]:
                        raise RuntimeError("P22 双臂机械条件失败")
                    write_json(rollout_path(source, context), row)
                    completed_tables += 2
                    executed += 2
                    if completed_tables % 32 == 0:
                        print(json.dumps({
                            "completed_tables": completed_tables,
                            "planned_tables": manifest["planned_tables"],
                        }, ensure_ascii=False), flush=True)
                except Exception as exc:  # noqa: BLE001
                    if row is None:
                        usage_unknown = True
                    failures.append({
                        "case_id": source["case_id"],
                        "context_id": context["context_id"],
                        "error": type(exc).__name__ + ": " + str(exc),
                    })
    finally:
        if usage_unknown:
            ledger.settle(reservation, usage_unknown=True, note="子进程未返回；保守结算")
        else:
            ledger.settle(reservation, actual=executed, note="按成功两臂桌数结算")
    files = list((_project_file(_PROJECT_ROOT, OUT / "rollouts")).glob("*.json"))
    write_json(_project_file(_PROJECT_ROOT, OUT / "run-summary.json"), {
        "schema": "r18-p22-run-summary/1",
        "rollout_files": len(files),
        "actual_tables": len(files) * 2,
        "failures": failures,
        "spent": ledger.account_summary(),
    })
    if failures or len(files) * 2 != manifest["planned_tables"]:
        raise RuntimeError("P22 赛事处境首尺执行不完整")


def strict_preference(row: Mapping[str, Any]) -> str:
    hu = row["hu_utility"]
    piao = row["piao_utility"]
    if float(piao["u_low"]) > float(hu["u_high"]):
        return "piao"
    if float(hu["u_low"]) > float(piao["u_high"]):
        return "hu"
    return "tie_or_unresolved"


def analyze() -> None:
    manifest, sources, contexts = verify()
    summary = json.loads((_project_file(_PROJECT_ROOT, OUT / "run-summary.json")).read_text(encoding="utf-8"))
    if summary["failures"] or summary["actual_tables"] != manifest["planned_tables"]:
        raise ValueError("P22 执行不完整")
    rows = [
        json.loads(rollout_path(source, context).read_text(encoding="utf-8"))
        for source in sources for context in contexts
    ]
    if not all(row["mechanical_ok"] for row in rows):
        raise ValueError("P22 存在机械失败配对")
    root_results = []
    for source in sources:
        own = [row for row in rows if row["case_id"] == source["case_id"]]
        preferences = [strict_preference(row) for row in own]
        counts = Counter(preferences)
        hu_terminals = {tuple(row["hu"]["final_scores_by_seat"]) for row in own}
        piao_terminals = {tuple(row["piao"]["final_scores_by_seat"]) for row in own}
        root_results.append({
            "case_id": source["case_id"],
            "role": source["role"],
            "contexts": len(own),
            "preference_counts": dict(sorted(counts.items())),
            "strict_flip": counts["piao"] > 0 and counts["hu"] > 0,
            "has_piao_strict": counts["piao"] > 0,
            "has_hu_strict": counts["hu"] > 0,
            "context_invariant_terminal_scores": (
                len(hu_terminals) == 1 and len(piao_terminals) == 1
            ),
            "hu_final_scores_by_seat": list(next(iter(hu_terminals))),
            "piao_final_scores_by_seat": list(next(iter(piao_terminals))),
        })
    context_results = []
    for context in contexts:
        own = [row for row in rows if row["context_id"] == context["context_id"]]
        counts = Counter(strict_preference(row) for row in own)
        u_deltas = []
        for row in own:
            hu = row["hu_utility"]
            piao = row["piao_utility"]
            if not hu["unresolved"] and not piao["unresolved"]:
                u_deltas.append(float(piao["u_low"]) - float(hu["u_low"]))
        context_results.append({
            "context_id": context["context_id"],
            "prior_rank": context["focal_rank_after_first_table"],
            "boundary_margin": context["boundary_margin"],
            "preference_counts": dict(sorted(counts.items())),
            "resolved_u_delta_mean": (
                None if not u_deltas else statistics.fmean(u_deltas)
            ),
            "resolved_roots": len(u_deltas),
        })
    flip_roots = sum(row["strict_flip"] for row in root_results)
    piao_roots = sum(row["has_piao_strict"] for row in root_results)
    hu_roots = sum(row["has_hu_strict"] for row in root_results)
    context_exact = all(
        row["hu"]["projection_exact"] and row["piao"]["projection_exact"]
        for row in rows
    )
    context_invariant = all(
        row["context_invariant_terminal_scores"] for row in root_results
    )
    gate = manifest["headroom_gate"]
    passes = bool(
        context_exact
        and context_invariant
        and flip_roots >= int(gate["strict_preference_flip_roots_at_least"])
        and piao_roots >= int(gate["roots_with_piao_strictly_better_at_least"])
        and hu_roots >= int(gate["roots_with_hu_strictly_better_at_least"])
    )
    result = {
        "schema": "r18-p22-competition-situation-headroom-result/1",
        "status": (
            "OPEN_COMPETITION_SITUATION_AUTHOR_AXIS" if passes
            else "CLOSE_COMPETITION_SITUATION_AUTHOR_AXIS"
        ),
        "development_roots": len(sources),
        "contexts_per_root": len(contexts),
        "actual_tables": summary["actual_tables"],
        "mechanical_ok": True,
        "context_projection_exact": context_exact,
        "context_invariant_terminal_scores": context_invariant,
        "strict_preference_flip_roots": flip_roots,
        "roots_with_piao_strictly_better": piao_roots,
        "roots_with_hu_strictly_better": hu_roots,
        "passes_headroom_gate": passes,
        "root_results": root_results,
        "context_results": context_results,
        "replication_roots_opened": False,
        "model_calls": 0,
        "next": (
            "扩展评分视图以显式投影 stage_table_no/tables_in_stage；只向作者开放开发根和赛事处境差分"
            if passes else
            "关闭三财神首飘的赛事处境作者轴；不扩 schema、不调用模型，转向其他杭麻机会家族"
        ),
        "selection_eligible": False,
        "release_eligible": False,
    }
    write_json(_project_file(_PROJECT_ROOT, OUT / "result.json"), result)
    print(json.dumps(result, ensure_ascii=False, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("prepare", "run", "analyze"))
    command = parser.parse_args().command
    if command == "prepare":
        prepare()
    elif command == "run":
        run()
    else:
        analyze()


if __name__ == "__main__":
    main()
