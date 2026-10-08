# -*- coding: utf-8 -*-
"""P2 工作包专属测试：自然面板阶段账注入（复审 §5 M1；FIX-PLAN 波次 1 P2）。

复审缺陷（红）：
    drive_match 调用未传 stage_situation；阶段循环只在桌赛结束后累计积分与
    名次分 → 第二桌的策略请求里只有桌内事实（stage_no/stage_total/
    ranking 全空），读不到首桌形成的阶段积分与名次分，门线/追分逻辑可能
    退回桌内积分。

本包验收（绿）：
    每桌开始前按「参赛者身份 → 物理座位」注入已完成桌阶段账（阶段账 =
    已完成各桌之和，不含当前桌；桌内结果仍由 PlayerObservation.scores
    单独维护）；四种换座下身份与座位一一对应；固定同一第二桌观察时，
    注入领先/落后首桌账会让公开策略输入与策略选择发生对应变化。

证据分层：测试 1—3 与 5 用记录型替身（0 真实桌赛）核对编排与映射；
测试 4、6 用**本地模拟器**（组合根 SimulationEngine，rounds_per_game=1 的
缩小赛程）核对真实驱动链上的注入与选择差异。全程 0 授权桌赛、0 LLM 调用、
不写 review/.../evidence 既有产物。
"""
from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/llm-guided-heuristic-route-2026-09-15/tools'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

import dataclasses
import inspect
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import pytest  # noqa: E402

import sitin_natural_panel as natural  # noqa: E402
import sitin_stage as stage  # noqa: E402
from hangma_bot.hangma.interface import ValueAnalysisLimits  # noqa: E402
from hangma_bot.policy.action_value import SCORING_VIEW_SCHEMA_VERSION  # noqa: E402
from hangma_bot.policy.action_value_executor import EXECUTOR_VERSION  # noqa: E402
from hangma_bot.policy.action_value_seeds import SEEDS  # noqa: E402

CONTRACT_PATH = natural.REPO / natural.DEFAULT_CONTRACT
OPPONENT_POLICIES = ("weighted_heuristic_v2",) * (stage.SEAT_COUNT - 1)
#: 缩小赛程（夹具：每桌 1 局）：本包验的是策略输入与选择，不是强度结论。
FIXTURE_ROUNDS = 1


def _contract() -> Mapping[str, Any]:
    return json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))


def _versions(contract: Mapping[str, Any], *, rounds: int = FIXTURE_ROUNDS) -> Dict[str, Any]:
    versions = dict(stage.contract_versions_block(contract))
    versions["rounds_per_game"] = int(rounds)
    return versions


def _plans(*, focal_seat: int = 0, contract: Optional[Mapping[str, Any]] = None) -> List[Any]:
    return natural.build_seat_stage_plans(
        contract=contract or _contract(), opponent="H", root_index=1,
        focal_seat=int(focal_seat), panel_seed=natural.DEFAULT_PANEL_SEED)


def _step_limit(contract: Mapping[str, Any]) -> int:
    return int(contract["stop"]["step_limit"])


class _ScriptedDrive:
    """记录型桌执行替身：记录每桌收到的阶段投影，按脚本返回终局积分（0 真实桌赛）。"""

    def __init__(self, scores_by_table: Mapping[int, Sequence[int]]) -> None:
        self.scores_by_table = {int(key): tuple(int(value) for value in values)
                                for key, values in scores_by_table.items()}
        self.calls: List[Dict[str, Any]] = []

    def __call__(self, *, plan: Any, policies_by_seat: Sequence[Any],
                 versions_block: Mapping[str, Any], step_limit: int,
                 value_limits: Any, stage_situation: Any = None) -> Dict[str, Any]:
        table_no = len(self.calls) + 1
        self.calls.append({
            "table_no": table_no, "table_id": plan.table_id,
            "seats": tuple(plan.seats()), "permutation": tuple(plan.permutation),
            "situation": stage_situation,
        })
        scores = self.scores_by_table.get(table_no, (0, 0, 0, 0))
        return {"table_id": plan.table_id, "seed": int(plan.seed),
                "match_status": "complete", "wall_ms": 1.0,
                "scores_by_seat": list(scores), "result": {}}


class _LegacySignatureDrive(_ScriptedDrive):
    """旧签名替身（与既有 0 桌结构测试同形）：不含 stage_situation 参数。"""

    def __call__(self, *, plan: Any, policies_by_seat: Sequence[Any],
                 versions_block: Mapping[str, Any], step_limit: int,
                 value_limits: Any) -> Dict[str, Any]:  # type: ignore[override]
        return super().__call__(plan=plan, policies_by_seat=policies_by_seat,
                                versions_block=versions_block, step_limit=step_limit,
                                value_limits=value_limits)


def _run_arm(monkeypatch: Any, drive: Any, *, plans: Optional[Sequence[Any]] = None,
             contract: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
    """跑一臂（基线臂；阶段账注入与臂无关），桌执行由 drive 承担。"""

    contract = contract or _contract()
    plans = list(plans) if plans is not None else _plans(contract=contract)
    monkeypatch.setattr(natural, "execute_natural_table", drive, raising=True)
    return natural.run_arm_stage(
        arm="baseline", plans=plans, candidate_scorer=None,
        opponent_policies=list(OPPONENT_POLICIES), versions_block=_versions(contract),
        step_limit=_step_limit(contract), value_limits=ValueAnalysisLimits())


class _StageAccountProbe:
    """探测策略：读公开策略输入里的阶段账决定候选顺序（探针口径，不主张策略优劣）。

    规则：本座位在阶段账中落后（participant_rank > 1）→ 取加权启发式计划的
    **末位**候选；领先/并列第一 → 取**首位**候选（原口径）。每个窗口记录
    观察签名、公开输入（CompetitionContext 投影）与最终所选动作键。
    """

    def __init__(self, *, policy_id: str, monotonic: Any = lambda: 800.0) -> None:
        self.policy_id = policy_id
        self._inner = stage.build_panel_policy("weighted_heuristic_v2", monotonic)
        self.windows: List[Dict[str, Any]] = []

    async def choose(self, request: Any, budget: Any) -> Any:
        plan = await self._inner.choose(request, budget)
        competition = request.competition
        behind = int(competition.participant_rank or 1) > 1
        order = list(plan.candidates)
        chosen = order[-1] if behind else order[0]
        reordered = [chosen] + [item for item in order if item is not chosen]
        self.windows.append({
            "seat": int(request.observation.seat),
            "window_key": (str(request.window_key.game_id), int(request.window_key.round_no),
                           int(request.window_key.trigger_seq),
                           request.window_key.phase.value),
            "hand": tuple(tile.code for tile in request.observation.my_hand),
            "scores": tuple(int(value) for value in request.observation.scores),
            "stage_no": competition.stage_no,
            "stage_total": competition.stage_total,
            "participant_rank": competition.participant_rank,
            "ranking_ids": tuple(str(entry.participant_id) for entry in competition.ranking),
            "ranking_total_scores": tuple(int(entry.total_score)
                                          for entry in competition.ranking),
            "ranking_place_points": tuple(int(entry.place_points)
                                          for entry in competition.ranking),
            "n_candidates": len(order),
            "inner_first": order[0].action_key,
            "chosen": chosen.action_key,
        })
        return dataclasses.replace(plan, candidates=tuple(
            dataclasses.replace(item, rank=index + 1)
            for index, item in enumerate(reordered)))


def _observation_signature(window: Mapping[str, Any]) -> Tuple[Any, ...]:
    """同一观察的比对签名：窗口键 + 手牌 + 桌内积分（不含阶段账）。"""

    return (window["window_key"], window["hand"], window["scores"])


def _focal_policies(seats: Sequence[str], *, probe: _StageAccountProbe) -> List[Any]:
    """焦点座位放探测策略，其余座位保持合同白名单装配（两臂一致口径）。"""

    policies: List[Any] = []
    for participant in seats:
        if participant == natural.FOCAL_PARTICIPANT:
            policies.append(probe)
        else:
            policies.append(stage.build_panel_policy("weighted_heuristic_v2",
                                                     lambda: 800.0))
    return policies


# ============================================================ 1. 第二桌注入首桌账（红→绿）


def test_second_table_policy_input_carries_first_table_stage_account(monkeypatch):
    """红→绿：第 2 桌执行前注入首桌形成的阶段积分与名次分（复审 §5 M1）。"""

    fake = _ScriptedDrive({1: (10, -4, 2, 6)})
    record = _run_arm(monkeypatch, fake)
    assert record["status"] == "complete", record["error"]
    first, second = fake.calls

    # 第 1 桌：阶段账为空（stage_no=1、已完成 0 桌、剩余 1 桌可推）
    assert first["situation"] is not None, "第 1 桌也应收到阶段投影（表头为 0 账）"
    assert first["situation"].stage_scores_by_seat == (0, 0, 0, 0)
    assert first["situation"].place_points_by_seat == (0, 0, 0, 0)
    assert first["situation"].stage_table_no == 1
    assert first["situation"].tables_completed == 0
    assert first["situation"].tables_in_stage == 2

    # 第 2 桌换座：逻辑焦点位坐到物理座位 1（合同 rotate_permutation(1)）
    assert second["permutation"] == (1, 2, 3, 0)
    assert second["seats"] == ("opp-3", "focal", "opp-1", "opp-2")
    situation = second["situation"]
    assert situation is not None, "第二桌策略输入缺少阶段账（M1 缺陷复现）"
    assert situation.stage_table_no == 2
    assert situation.tables_in_stage == 2
    assert situation.tables_completed == 1
    assert situation.rounds_per_game == FIXTURE_ROUNDS

    # 身份→物理座位映射：首桌 (10,-4,2,6) 按座位 (focal,opp-1,opp-2,opp-3)
    # → 身份账 focal 10 / opp-1 -4 / opp-2 2 / opp-3 6；名次分 (3,-3,-1,1)。
    # 第 2 桌座位顺序 (opp-3, focal, opp-1, opp-2) → 投影向量随座位重排：
    assert situation.participant_ids_by_seat == second["seats"]
    assert situation.stage_scores_by_seat == (6, 10, -4, 2)
    assert situation.place_points_by_seat == (1, 3, -3, -1)

    # 公开策略输入（CompetitionContext）：座位 1（focal）可见自己的阶段名次与四座账
    context = situation.competition_context(second["table_id"], 1)
    assert context.stage_no == 2 and context.stage_total == 2
    assert context.participant_rank == 1
    assert [entry.participant_id for entry in context.ranking] == list(second["seats"])
    assert [int(entry.total_score) for entry in context.ranking] == [6, 10, -4, 2]
    assert [int(entry.place_points) for entry in context.ranking] == [1, 3, -3, -1]
    assert [int(entry.games_played) for entry in context.ranking] == [
        FIXTURE_ROUNDS] * stage.SEAT_COUNT
    print("[T1] 第 2 桌注入账 scores={0} places={1} rank(focal)={2}".format(
        situation.stage_scores_by_seat, situation.place_points_by_seat,
        context.participant_rank))


# ============================================================ 2. 不含当前桌、不重复累计


def test_stage_account_excludes_current_table(monkeypatch):
    """阶段账 = 已完成各桌之和，不含当前桌；桌内结果单独维护，不重复累计。"""

    fake = _ScriptedDrive({1: (10, -4, 2, 6), 2: (7, -3, 5, -5)})
    record = _run_arm(monkeypatch, fake)
    assert record["status"] == "complete", record["error"]
    second = fake.calls[1]

    # 第 2 桌注入的仍只有首桌：不含本桌 (7,-3,5,-5)，也没有翻倍
    assert second["situation"].stage_scores_by_seat == (6, 10, -4, 2)
    assert second["situation"].tables_completed == 1

    # 阶段终点账 = 各桌之和（逐身份）：focal 10-3=7 / opp-1 -4+5=1 /
    # opp-2 2-5=-3 / opp-3 6+7=13；名次分 3-1=2 / -3+1=-2 / -1-3=-4 / 1+3=4
    assert record["stage_totals_by_participant"] == {
        "focal": 7, "opp-1": 1, "opp-2": -3, "opp-3": 13}
    assert record["stage_place_points_by_participant"] == {
        "focal": 2, "opp-1": -2, "opp-2": -4, "opp-3": 4}
    print("[T2] 阶段终点账={0} 注入账(第2桌)={1}".format(
        record["stage_totals_by_participant"],
        second["situation"].stage_scores_by_seat))


# ============================================================ 3. 四换座映射一致


def test_four_rotations_map_participant_identity_to_physical_seat(monkeypatch):
    """四换座（rotate 0—3）：身份→座位映射一致、不串位（夹具为 4 桌阶段）。"""

    contract = _contract()
    base = _plans(focal_seat=0, contract=contract)
    logical = [{"participant_id": participant, "policy_name": name}
               for participant, name in zip(base[0].logical_participants,
                                            base[0].policy_names)]
    scripted = {1: (12, -1, 4, -6), 2: (-2, 7, 3, -8), 3: (5, 5, -4, -6), 4: (1, -9, 8, 0)}
    plans = [stage.build_table_plan(
        stage_no=1, stage_name="开发组", stage_role="qualify", stage_kind="group_round",
        table_id="np-rot-{0}".format(index + 1), participants=logical,
        permutation=stage.rotate_permutation(index), seed=1000 + index,
        tables_in_stage=len(scripted), group_index=1) for index in range(len(scripted))]

    fake = _ScriptedDrive(scripted)
    record = _run_arm(monkeypatch, fake, plans=plans, contract=contract)
    assert record["status"] == "complete", record["error"]

    permutations = [call["permutation"] for call in fake.calls]
    assert permutations == [stage.rotate_permutation(index)
                            for index in range(len(scripted))]
    assert len(set(permutations)) == stage.SEAT_COUNT  # 四种换座都覆盖

    expected_scores: Dict[str, int] = {}
    expected_places: Dict[str, int] = {}
    for index, call in enumerate(fake.calls):
        situation = call["situation"]
        assert situation is not None
        assert situation.participant_ids_by_seat == call["seats"]
        assert situation.stage_table_no == index + 1
        assert situation.tables_completed == index
        # 期望值由「身份累计」独立算得，再按本桌物理座位展开
        want_scores = tuple(expected_scores.get(pid, 0) for pid in call["seats"])
        want_places = tuple(expected_places.get(pid, 0) for pid in call["seats"])
        assert situation.stage_scores_by_seat == want_scores, call["table_id"]
        assert situation.place_points_by_seat == want_places, call["table_id"]
        row_scores = fake.scores_by_table[index + 1]
        points = stage.place_points_for_table(row_scores)
        for seat, participant in enumerate(call["seats"]):
            expected_scores[participant] = (expected_scores.get(participant, 0)
                                            + int(row_scores[seat]))
            expected_places[participant] = (expected_places.get(participant, 0)
                                            + int(points[seat]))
    print("[T3] 四换座投影（身份→座位）逐桌一致：permutations={0}".format(permutations))


# ============================================================ 4. 同一观察：领先/落后（本地模拟器）


def test_same_second_table_observation_leading_vs_trailing_changes_input_and_choice():
    """固定同一第 2 桌观察，注入领先/落后首桌账 → 公开输入与选择对应变化。"""

    contract = _contract()
    plans = _plans(focal_seat=0, contract=contract)
    table_two = plans[1]
    seats = tuple(table_two.seats())
    focal_seat = seats.index(natural.FOCAL_PARTICIPANT)
    versions = _versions(contract)

    # 首桌账两版（同一第 2 桌计划、同一牌山）：焦点参赛者领先 vs 落后
    leading_totals = {"focal": 90, "opp-1": -20, "opp-2": 10, "opp-3": 40}
    leading_places = {"focal": 3, "opp-1": -3, "opp-2": -1, "opp-3": 1}
    trailing_totals = {"focal": -20, "opp-1": 90, "opp-2": 10, "opp-3": 40}
    trailing_places = {"focal": -3, "opp-1": 3, "opp-2": -1, "opp-3": 1}

    def run(totals: Mapping[str, int], places: Mapping[str, int]) -> Tuple[Any, Any]:
        situation = natural.build_stage_situation(
            plan=table_two, table_no=2, tables_completed=1, totals=totals,
            place_totals=places, rounds_per_game=FIXTURE_ROUNDS)
        probe = _StageAccountProbe(policy_id="probe:stage-account")
        row = natural.execute_natural_table(
            plan=table_two, policies_by_seat=_focal_policies(seats, probe=probe),
            versions_block=versions, step_limit=_step_limit(contract),
            value_limits=ValueAnalysisLimits(), stage_situation=situation)
        return row, probe

    row_lead, probe_lead = run(leading_totals, leading_places)
    row_trail, probe_trail = run(trailing_totals, trailing_places)
    assert row_lead["match_status"] == "complete", row_lead
    assert row_trail["match_status"] == "complete", row_trail
    assert probe_lead.windows and probe_trail.windows

    first_lead, first_trail = probe_lead.windows[0], probe_trail.windows[0]
    assert _observation_signature(first_lead) == _observation_signature(first_trail), \
        "两版注入必须观察同一局面（同一计划/同一牌山）"
    assert first_lead["stage_no"] == first_trail["stage_no"] == 2
    assert first_lead["stage_total"] == first_trail["stage_total"] == 2
    assert first_lead["participant_rank"] == 1
    assert first_trail["participant_rank"] == stage.SEAT_COUNT
    assert first_lead["ranking_total_scores"] == tuple(
        leading_totals[pid] for pid in seats)
    assert first_trail["ranking_total_scores"] == tuple(
        trailing_totals[pid] for pid in seats)

    # 首个选择发生分歧的窗口：观察仍完全相同（分歧前的轨迹一致）
    diverge = next(index for index, (lead, trail) in enumerate(
        zip(probe_lead.windows, probe_trail.windows)) if lead["chosen"] != trail["chosen"])
    lead_window, trail_window = (probe_lead.windows[diverge],
                                 probe_trail.windows[diverge])
    assert _observation_signature(lead_window) == _observation_signature(trail_window)
    assert lead_window["n_candidates"] > 1
    assert lead_window["inner_first"] == trail_window["inner_first"]
    print("[T4] 分歧窗口={0} 观察相同；领先→{1}（rank={2}），落后→{3}（rank={4}）；"
          "终局积分 领先={5} 落后={6}".format(
              diverge, lead_window["chosen"], lead_window["participant_rank"],
              trail_window["chosen"], trail_window["participant_rank"],
              row_lead["scores_by_seat"], row_trail["scores_by_seat"]))
    assert row_lead["scores_by_seat"] != row_trail["scores_by_seat"]


# ============================================================ 5. 装配守卫（旧替身兼容）


def test_real_entry_declares_stage_account_and_legacy_double_stays_compatible(monkeypatch):
    """真实执行入口声明阶段账参数；旧签名替身不被新参数打断（既有测试兼容）。"""

    assert "stage_situation" in inspect.signature(
        natural.execute_natural_table).parameters, \
        "execute_natural_table 必须显式接收 stage_situation（M1 注入通道）"

    legacy = _LegacySignatureDrive({1: (10, -4, 2, 6)})
    record = _run_arm(monkeypatch, legacy)
    assert record["status"] == "complete", record["error"]
    assert len(legacy.calls) == 2
    assert all(call["situation"] is None for call in legacy.calls)  # 旧替身无该参数

    real = _ScriptedDrive({1: (10, -4, 2, 6)})
    record = _run_arm(monkeypatch, real)
    assert record["status"] == "complete", record["error"]
    assert real.calls[1]["situation"] is not None


def test_candidate_policy_factory_replaces_only_focal_candidate_arm():
    """显式研究策略工厂只替换候选臂焦点位，基线与三家对手保持冻结装配。"""

    class ProbePolicy:
        policy_id = "probe:r17"

    calls = []

    def factory(monotonic):
        calls.append(monotonic)
        return ProbePolicy()

    participants = (natural.FOCAL_PARTICIPANT, "opp-1", "opp-2", "opp-3")
    candidate = natural.arm_logical_policies(
        arm="candidate",
        candidate_scorer=None,
        logical_participants=participants,
        opponent_policies=OPPONENT_POLICIES,
        monotonic=lambda: 800.0,
        candidate_policy_factory=factory,
    )
    assert isinstance(candidate[natural.FOCAL_PARTICIPANT], ProbePolicy)
    assert len(calls) == 1

    baseline = natural.arm_logical_policies(
        arm="baseline",
        candidate_scorer=None,
        logical_participants=participants,
        opponent_policies=OPPONENT_POLICIES,
        monotonic=lambda: 800.0,
        candidate_policy_factory=factory,
    )
    assert not isinstance(baseline[natural.FOCAL_PARTICIPANT], ProbePolicy)
    assert len(calls) == 1
    assert tuple(type(candidate[item]) for item in participants[1:]) == tuple(
        type(baseline[item]) for item in participants[1:]
    )


def test_unknown_arm_rejected_before_natural_table_execution():
    """描述性 arm 名不能静默切到稳定 V2，避免重现 P80 的轨迹身份错误。"""

    with pytest.raises(ValueError, match="arm 只能为 baseline 或 candidate"):
        natural.arm_logical_policies(
            arm="p80-r18-v2-natural", candidate_scorer=None,
            logical_participants=(natural.FOCAL_PARTICIPANT, "opp-1", "opp-2", "opp-3"),
            opponent_policies=OPPONENT_POLICIES, monotonic=lambda: 800.0,
        )
    with pytest.raises(ValueError, match="arm 只能为 baseline 或 candidate"):
        natural.run_arm_stage(
            arm="p80-r18-v2-natural", plans=(), candidate_scorer=None,
            opponent_policies=OPPONENT_POLICIES,
            versions_block={"rounds_per_game": FIXTURE_ROUNDS},
            step_limit=1, value_limits=ValueAnalysisLimits(),
        )


# ============================================================ 6. 真实模拟器整臂核对


def test_real_arm_second_table_policy_input_carries_real_first_table_result(monkeypatch):
    """本地模拟器整臂：第 2 桌策略输入 = 第 1 桌真实结果的按身份累计。"""

    contract = _contract()
    plans = _plans(focal_seat=0, contract=contract)
    versions = _versions(contract)
    original = natural.arm_logical_policies
    probes: List[_StageAccountProbe] = []

    def with_probe(**kwargs: Any) -> Dict[str, Any]:
        policies = original(**kwargs)
        probe = _StageAccountProbe(policy_id="probe:arm-stage-account")
        policies[natural.FOCAL_PARTICIPANT] = probe
        probes.append(probe)
        return policies

    monkeypatch.setattr(natural, "arm_logical_policies", with_probe, raising=True)
    record = natural.run_arm_stage(
        arm="baseline", plans=plans, candidate_scorer=None,
        opponent_policies=list(OPPONENT_POLICIES), versions_block=versions,
        step_limit=_step_limit(contract), value_limits=ValueAnalysisLimits())
    assert record["status"] == "complete", record["error"]
    assert len(probes) == 2 and all(probe.windows for probe in probes)

    # 完整真实桌赛结果必须经过阶段编排留存，且JSON落盘往返不丢字段。
    persisted = json.loads(json.dumps(record))
    for table, plan in zip(persisted["tables"], plans):
        result = table["result"]
        assert result["expected_hands"] == result["completed_hands"] == FIXTURE_ROUNDS
        assert result["status"] == "complete" and result["invalid_reasons"] == []
        assert result["scores_after"] == table["scores_by_seat"]
        assert result["scores_before"] == [0, 0, 0, 0]
        assert result["policy_ids_by_seat"] == list(plan.seats())
        assert result["seat_permutation"] == list(plan.permutation)
        assert result["runtime_counts"] is not None
        assert result["versions"]["rules_hash"]

    first_table_seats = tuple(plans[0].seats())
    second_table_seats = tuple(plans[1].seats())
    first_row = record["tables"][0]
    assert first_row["match_status"] == "complete"
    expected_by_participant = {
        first_table_seats[seat]: int(first_row["scores_by_seat"][seat])
        for seat in range(stage.SEAT_COUNT)}
    expected_vector = tuple(expected_by_participant[pid] for pid in second_table_seats)

    probe_one, probe_two = probes
    # 第 1 桌：阶段账全空、阶段序号 1、剩余 1 桌；四家同分 ⇒ 名次为并列区间
    # (1..4) 的平均名次 2.5 取整 2（StageSituationProjection 声明的并列共享口径，
    # 不是缺陷：第 1 桌本就没有已完成桌事实）。
    for window in probe_one.windows:
        assert window["stage_no"] == 1 and window["stage_total"] == 2
        assert window["ranking_total_scores"] == (0, 0, 0, 0)
        assert window["ranking_place_points"] == (0, 0, 0, 0)
        assert window["participant_rank"] == 2
        assert window["scores"] == (0, 0, 0, 0)  # 桌内积分单独维护
    # 第 2 桌：策略输入 = 第 1 桌实跑结果按身份搬到本桌座位；桌内积分仍为 0
    for window in probe_two.windows:
        assert window["stage_no"] == 2 and window["stage_total"] == 2
        assert window["ranking_ids"] == second_table_seats
        assert window["ranking_total_scores"] == expected_vector
        assert window["scores"] == (0, 0, 0, 0)
    print("[T6] 第 1 桌实跑座位分={0}；第 2 桌（座位 {1}）策略输入阶段账={2}".format(
        first_row["scores_by_seat"], second_table_seats, expected_vector))


# ============================================================ 7. P2b 按根索引/根种子显式选取
#
# 缺陷（P7b 实测约束）：run_natural_panel 只接受「根数 N」→ 只能复现某
# (mix, panel_seed) 的 root01..rootN **前缀**；档案挑战补根时无法只评「参与者
# 缺失的那些根」，只能整前缀重跑（重复评价同一实例/重复计费）或放弃新鲜独立根。
#
# 本节验收：显式根选取（索引或种子）只评被选根；根身份（root_id / root_seed /
# table_id / table_seed / root_content_digest）与「按根数取前缀」逐字节一致；
# 同一根重复请求既不产生第二个实例（P6 实例台账）也不第二次计费（统一账本）；
# 越界/重复/空列表一律拒绝，且拒绝早于任何桌赛执行与任何费用。

#: P2b 金例的**身份上下文**：视图结构版本、执行器版本、候选身份与两份合同摘要。
#: 它们进入 panel 身份（candidate_id / contract_sha256 / av_contract_sha256），因此
#: **任何无关的结构版本升位都会改变产物的字节**（E3：sitin-scoring-view /2→/3 使
#: panel.json 摘要从 2fe03eca… 变为 927beddb…；R9 波次 1 的 P1 把执行器升到 /6、
#: P2/P4/P6 改动合同与身份口径，又使摘要变为本次重录值）——这与「按根选取」能力无关。
#: 当前版本与本常量不一致时，产物摘要断言**显式 skip**（给出逐项差异与归因证据路径），
#: 既不静默改数也不放宽（与 T10 案同一口径）。
#:
#: **R9/P3 重录**（2026-09-17，R9-FIX-PLAN §11.1）：P1（EXECUTOR_VERSION /6）、
#: P2（根描述符身份）、P4（准入身份新增 materials_sha256/executor_version/thresholds）、
#: P6（sitin-archive/2、sitin-slot-selection/2）之后，候选身份与 av 合同摘要变化，
#: 金例按设计 skip（18 passed / 1 skipped）。重录走**本文件自己的夹具**
#: （_freeze_clock + _run_panel + _SeededDrive），重录脚本与产物见
#: evidence/v4-impl/r9-fixes/P3-runid/probes/probe_golden_rerecord.py 与
#: .../green/golden-rerecord.json（连跑两次逐字节一致）。
GOLDEN_IDENTITY_CONTEXT: Dict[str, str] = {
    # 旧字节金例尚未记录评分执行审计，新增字段不追认历史内容。
    "policy_execution_schema": "unrecorded",
    # 视图结构版本（src/hangma_bot/policy/action_value.py）。
    "scoring_view_schema": "sitin-scoring-view/3",
    # 受限执行器版本（src/hangma_bot/policy/action_value_executor.py）；R9 P1 由 /4 升 /6。
    "executor_version": "action-value-executor/6",
    # 候选身份（由候选源码 + av 合同摘要 + 执行器/视图结构摘要派生）。
    "candidate_id": "cc937de6978ebd5a1b712871774fca4b5ca84387a28a98637f5f3ce3939e369e",
    # 目标合同与 action_value 合同的内容摘要（进 panel 身份）。
    "contract_sha256": "98c1e0a387550799b0985695a3846aeb1862ad85a4cfb71f22dbb433e63d7f6e",
    "av_contract_sha256": "3c0b4d3a2fdd1f438e2e5d295e4269f578485032aeddad0eb558fdcce981d4a9",
}
#: 归因/重录证据（金例漂移时写进 skip 理由，供复核）。
GOLDEN_DRIFT_EVIDENCE = (
    "review/llm-guided-heuristic-route-2026-09-15/evidence/v4-impl/r9-fixes/"
    "P3-runid/green/golden-rerecord.json（R9/P3 重录：身份上下文逐项取值 + 逐字节"
    "产物摘要 + 8 次替身桌赛的桌身份/牌山；漂移归因见同目录 FIX-REPORT.md）")
#: 上述身份上下文下记录的产物摘要（2026-09-17 R9/P3 重录；时钟打桩 + 确定性替身桌赛）。
GOLDEN_LEGACY_ROOTS2_PANEL_SHA256 = (
    "0d7ac63cf9caf1658e03dfa9fb7f589b66c427eeae2a98cad97727401f80cd7e")
GOLDEN_LEGACY_ROOTS2_SAMPLES_SHA256 = (
    "d421b8cb4a1d514bc246c15bb8642944906736b61bde5ef65167ba337bab2c69")
#: P2b 金例：根身份（root_id、root_seed、table_id、table_seed）逐根固定值。
#: **与身份上下文无关**：只由 (对手, panel_seed, 根序号) 派生——E3 升版前后逐字相同
#: （归因证据见 GOLDEN_DRIFT_EVIDENCE：467 个字段未变，其中含下列全部根身份字段）。
GOLDEN_ROOT_IDENTITY: Dict[int, Tuple[str, int, Tuple[str, ...], Tuple[int, ...]]] = {
    1: ("np-H-20260916-root01", 109887957447187,
        ("np-H-20260916-r01-s0-t1", "np-H-20260916-r01-s0-t2"),
        (50316934399476, 4328248873106)),
    2: ("np-H-20260916-root02", 2624154998715,
        ("np-H-20260916-r02-s0-t1", "np-H-20260916-r02-s0-t2"),
        (102729955129120, 238113619500132)),
    3: ("np-H-20260916-root03", 202823643509449,
        ("np-H-20260916-r03-s0-t1", "np-H-20260916-r03-s0-t2"),
        (150248150547707, 257357438608793)),
    4: ("np-H-20260916-root04", 133609000058923,
        ("np-H-20260916-r04-s0-t1", "np-H-20260916-r04-s0-t2"),
        (170570164487387, 224958380317842)),
}
#: P2b 金例：根内容摘要（root_content_digest）逐根固定值。它由 panel 口径常量
#: （generator/stage_projection/基线臂名）+ (对手, panel_seed, 根序号, 根种子, 赛程) 派生，
#: **不含候选身份、不含视图结构版本**——E3 升版前后逐字相同（见 GOLDEN_DRIFT_EVIDENCE）。
#: 该值变化属**真实**面板身份变更（根身份/口径变了，P6 台账与 P7b 同根复现会受影响），
#: 需按 Q7 换批次并附「根身份四元组是否同时变化」的核对后再重录；不是结构版本漂移的假红。
GOLDEN_ROOT_CONTENT_DIGESTS: Dict[int, str] = {
    1: "062111d9c818479960a303794fd5ce8e18385018dd6876f002735942481ba154",
    2: "691767ed789643f64d04d7cc4d857546d9e48e87beac59d375041a99ea4449ef",
}


def _root_content_digests(panel: Mapping[str, Any]) -> Dict[int, str]:
    """产物里的逐根内容摘要（根序号 → root_content_digest）。"""

    return {int(sample["root_index"]): str(sample["root_content_digest"])
            for sample in panel["samples"]}


def _identity_context(panel: Mapping[str, Any]) -> Dict[str, str]:
    """当前运行的「身份上下文」：视图结构版本 + 执行器版本 + 产物里的身份三项。"""

    identity = panel.get("identity") or {}
    return {
        "scoring_view_schema": str(SCORING_VIEW_SCHEMA_VERSION),
        "policy_execution_schema": str(identity.get("policy_execution_schema", "unrecorded")),
        "executor_version": str(EXECUTOR_VERSION),
        "candidate_id": str(identity.get("candidate_id")),
        "contract_sha256": str(identity.get("contract_sha256")),
        "av_contract_sha256": str(identity.get("av_contract_sha256")),
    }


def _golden_context_mismatch(panel: Mapping[str, Any]) -> List[str]:
    """金例绑定的身份上下文与当前不一致的项（空列表=可比对）。"""

    current = _identity_context(panel)
    return ["{0}: 金例 {1} ≠ 当前 {2}".format(key, GOLDEN_IDENTITY_CONTEXT[key],
                                             current.get(key))
            for key in sorted(GOLDEN_IDENTITY_CONTEXT)
            if current.get(key) != GOLDEN_IDENTITY_CONTEXT[key]]


#: P2b 夹具：确定性候选源码（与 sitin_search_v4 同源种子；不调 LLM）。
GOOD_SOURCE = SEEDS["route_value_seed"].source
#: 批次 7 预算授权令牌（替身桌赛仍走真实授权门，0 真实执行）。
#:
#: P14：授权门已统一到 Q6 的**受信校验入口**（sitin_search.av_authorization_allows，
#: operation=natural_panel，required={"tables_full": 1.0}）——legacy 形态照样接受
#: （authorized=true 且 batch==7 且无 sitin-authorization/1 字段），但"本次操作所需账户
#: 必须已声明额度"这一项与状态机**同判据**，故令牌必须带 budgets（旧式门不看额度）。
BATCH7_TOKEN = {"authorized": True, "batch": 7,
                "budgets": {"tables_full": 64.0}}
LEDGER_BUDGETS = {"tables_full": 64.0}


class _SeededDrive:
    """确定性替身桌赛：座位分只由 (plan.seed, 焦点臂) 决定（与根序无关）。

    因此「同一根在两版调用形式下」的产物可逐字节对拍；同时记录每次编排调用
    收到的阶段账投影（P2b 不改注入口径，显式选取下仍须逐桌注入）。
    """

    def __init__(self) -> None:
        self.calls: List[Dict[str, Any]] = []

    def __call__(self, *, plan: Any, policies_by_seat: Sequence[Any],
                 versions_block: Mapping[str, Any], step_limit: int,
                 value_limits: Any, stage_situation: Any = None) -> Dict[str, Any]:
        seats = list(plan.seats())
        focal_idx = seats.index("focal") if "focal" in seats \
            else seats.index("natural:focal")
        is_candidate = str(getattr(policies_by_seat[focal_idx], "policy_id", "")
                           ).startswith("action_value")
        self.calls.append({"table_id": plan.table_id, "seed": int(plan.seed),
                           "focal_idx": focal_idx, "is_candidate": is_candidate,
                           "situation": stage_situation})
        offset = int(plan.seed) % 7 - 3
        scores = []
        for seat in range(stage.SEAT_COUNT):
            if seat == focal_idx:
                scores.append(12 + offset if is_candidate else -10 + offset)
            else:
                scores.append(2 - seat + (offset if seat % 2 else -offset))
        return {"table_id": plan.table_id, "seed": int(plan.seed),
                "match_status": "complete", "wall_ms": 1.0,
                "scores_by_seat": scores, "result": {}}


def _freeze_clock(monkeypatch: Any) -> None:
    """打桩墙钟/CPU 钟：产物里的计时字段归零 → 产物可逐字节对拍。"""

    monkeypatch.setattr(natural.time, "monotonic", lambda: 1000.0)
    monkeypatch.setattr(natural.time, "process_time", lambda: 500.0)


def _run_panel(tmp_path: Path, monkeypatch: Any, *, out_name: str,
               drive: Optional[_SeededDrive] = None,
               **kwargs: Any) -> Tuple[Dict[str, Any], _SeededDrive]:
    """跑一次面板（真实执行入口由确定性替身替换：0 真实桌赛、0 LLM 调用）。"""

    contract = kwargs.pop("contract", None) or _contract()
    drive = drive if drive is not None else _SeededDrive()
    monkeypatch.setattr(natural, "execute_natural_table", drive, raising=True)
    panel = natural.run_natural_panel(
        candidate_source=kwargs.pop("candidate_source", GOOD_SOURCE),
        opponent=kwargs.pop("opponent", "H"),
        seats_per_root=kwargs.pop("seats_per_root", 1), contract=contract,
        out_dir=tmp_path / out_name, authorization=BATCH7_TOKEN, **kwargs)
    return panel, drive


def _artifacts(out_dir: Path) -> Dict[str, bytes]:
    """产物目录的逐文件字节快照（文件集合 + 内容；等价于 diff -r 判据）。"""

    return {path.name: path.read_bytes()
            for path in sorted(Path(out_dir).iterdir()) if path.is_file()}


def _sha256(data: bytes) -> str:
    import hashlib
    return hashlib.sha256(data).hexdigest()


def _root_identity(panel: Mapping[str, Any]
                   ) -> Dict[int, Tuple[str, int, Tuple[str, ...], Tuple[int, ...]]]:
    """从产物样本里抽出「根身份」四元组（root_id/root_seed/桌身份表/桌种子表）。"""

    return {int(sample["root_index"]): (
        str(sample["source_root_id"]), int(sample["root_seed"]),
        tuple(str(item) for item in sample["table_ids"]),
        tuple(int(item) for item in sample["table_seeds"]))
        for sample in panel["samples"]}


# ------------------------------------------- 7.1 只评被选根（前缀外的新鲜独立根）


def test_root_indices_evaluates_only_requested_roots(tmp_path, monkeypatch):
    """root_indices=[3,4] 只评 root03/root04；root01/root02 未被评价。

    证明面（期望/实际）：产物样本的 root_index/source_root_id 只有 3/4；替身桌赛
    的编排调用里不出现 root01/root02 的 table_id（即未启动过它们的任何桌）；根身份
    与金例逐字一致（同一 (mix, panel_seed, root_index) 恒等）。
    """

    _freeze_clock(monkeypatch)
    panel, drive = _run_panel(tmp_path, monkeypatch, out_name="idx-3-4",
                             root_indices=[3, 4])

    # 期望：只有被选根的两个样本；实际：逐个核对
    assert [sample["root_index"] for sample in panel["samples"]] == [3, 4]
    assert [sample["source_root_id"] for sample in panel["samples"]] == [
        "np-H-20260916-root03", "np-H-20260916-root04"]
    assert _root_identity(panel) == {3: GOLDEN_ROOT_IDENTITY[3],
                                     4: GOLDEN_ROOT_IDENTITY[4]}
    # 未被选根**一个桌都没跑**：编排调用里没有 r01/r02 的桌
    called = [call["table_id"] for call in drive.calls]
    assert called and all("-r03-" in item or "-r04-" in item for item in called), called
    assert not any("-r01-" in item or "-r02-" in item for item in called)
    assert len(called) == 2 * 2 * 2  # 根 × 臂 × 桌（座位 1）
    # 费用与配置口径：根数按选择集长度计，费用只按被选根计
    assert panel["config"]["roots"] == 2
    assert panel["config"]["min_roots"] == 2
    assert panel["cost"]["tables_full_planned"] == 8
    assert panel["cost"]["tables_full_executed"] == 8
    # 阶段账注入口径不变（P2b 只改根选取，不改投影）：每桌仍收到投影
    assert all(call["situation"] is not None for call in drive.calls)
    assert {call["situation"].tables_in_stage for call in drive.calls} == {2}
    print("[T7] 选择 root_indices=[3,4] → 样本根={0}，编排调用={1} 桌，"
          "根01/02 调用数=0".format(
              [sample["source_root_id"] for sample in panel["samples"]], len(called)))


def test_selected_root_seats_rotate_all_focal_seats(tmp_path, monkeypatch):
    """显式选取下座位轮换不受影响：root03 × 4 焦点座位 → 4 样本、桌身份含 s0..s3。"""

    panel, _ = _run_panel(tmp_path, monkeypatch, out_name="idx-3-seats4",
                          root_indices=[3], seats_per_root=stage.SEAT_COUNT)
    assert {sample["focal_anchor_seat"] for sample in panel["samples"]} == set(
        range(stage.SEAT_COUNT))
    assert {int(sample["root_index"]) for sample in panel["samples"]} == {3}
    assert panel["cost"]["tables_full_planned"] == 1 * stage.SEAT_COUNT * 2 * 2
    seat_one = next(sample for sample in panel["samples"]
                    if sample["focal_anchor_seat"] == 1)
    assert all("-r03-s1-" in table_id for table_id in seat_one["table_ids"])


# ------------------------------------------- 7.2 前缀选择与旧接口逐字节一致


def test_root_indices_prefix_is_byte_identical_to_legacy_roots(tmp_path, monkeypatch):
    """真不变量（与结构版本无关，永不放宽）：root_indices=[1,2] ≡ roots=2。

    三层判据：①两版产物目录逐文件字节相同；②根身份四元组与**与身份上下文无关**的
    内容摘要金例一致（E3 升版前后逐字相同）；③编排调用序列（桌身份/牌山）逐项相同。
    产物**字节级**金例（会随视图结构/合同版本漂移）另见
    test_legacy_roots2_artifact_golden_is_bound_to_identity_context。
    """

    _freeze_clock(monkeypatch)
    legacy, legacy_drive = _run_panel(tmp_path, monkeypatch, out_name="legacy-roots2",
                                     roots=2)
    indexed, indexed_drive = _run_panel(tmp_path, monkeypatch, out_name="idx-1-2",
                                        root_indices=[1, 2])

    legacy_files = _artifacts(tmp_path / "legacy-roots2")
    indexed_files = _artifacts(tmp_path / "idx-1-2")
    assert set(legacy_files) == set(indexed_files) == {"panel.json", "samples.jsonl"}
    assert legacy_files == indexed_files, "两版调用形式的产物必须逐字节一致"
    # 逐根身份与根内容摘要相同，且与「与版本无关的金例」一致（同根 ⇒ 同一实例）
    assert _root_identity(indexed) == _root_identity(legacy) == {
        1: GOLDEN_ROOT_IDENTITY[1], 2: GOLDEN_ROOT_IDENTITY[2]}
    assert _root_content_digests(indexed) == _root_content_digests(legacy) == {
        1: GOLDEN_ROOT_CONTENT_DIGESTS[1], 2: GOLDEN_ROOT_CONTENT_DIGESTS[2]}
    # 编排调用序列（桌身份/牌山）完全相同 → 同根同牌山
    assert [(call["table_id"], call["seed"], call["is_candidate"])
            for call in indexed_drive.calls] == \
        [(call["table_id"], call["seed"], call["is_candidate"])
         for call in legacy_drive.calls]
    print("[T8] 不变量：两版产物逐字节一致（panel.json sha256={0}）；根身份与内容摘要"
          "与版本无关金例一致".format(_sha256(legacy_files["panel.json"])[:16]))


def test_root_content_digest_is_independent_of_candidate_identity(tmp_path, monkeypatch):
    """同一根的根身份与内容摘要与**候选身份**无关（P6「同根=同一实例」的判据）。

    两个不同候选源码（不同 candidate_id）在同一 (mix, panel_seed, 根选择) 下必须给出
    相同的 root_id/root_seed/table_id/table_seed/root_content_digest：P7b 的同根跨身份
    补根与 P6 实例台账都依赖这条；这也是 E3 归因的机器化对照——那些摘要不随身份上下文
    （视图结构版本/合同摘要/candidate_id）漂移，只有 candidate_id 与合同摘要会变。
    """

    _freeze_clock(monkeypatch)
    other_source = SEEDS["efficiency_seed"].source
    assert other_source != GOOD_SOURCE, "两个夹具候选源码必须不同"
    first, _ = _run_panel(tmp_path, monkeypatch, out_name="identity-a",
                          root_indices=[3, 4])
    second, _ = _run_panel(tmp_path, monkeypatch, out_name="identity-b",
                           root_indices=[3, 4], candidate_source=other_source)

    assert first["identity"]["candidate_id"] != second["identity"]["candidate_id"]
    assert _root_identity(first) == _root_identity(second) == {
        3: GOLDEN_ROOT_IDENTITY[3], 4: GOLDEN_ROOT_IDENTITY[4]}
    assert _root_content_digests(first) == _root_content_digests(second)
    assert {sample["table_seeds"][0] for sample in first["samples"]} == \
        {sample["table_seeds"][0] for sample in second["samples"]}
    print("[T8b] 跨候选身份同根：candidate_id {0}… ≠ {1}…，根身份与内容摘要逐字相同"
          "（同根 ⇒ 同一实例）".format(first["identity"]["candidate_id"][:12],
                                      second["identity"]["candidate_id"][:12]))


def test_legacy_roots2_artifact_golden_is_bound_to_identity_context(tmp_path, monkeypatch):
    """产物**字节级**金例：与身份上下文绑定（E3 升版后果收口）。

    candidate_id 与合同摘要进入 panel 身份，故任何**无关的**结构版本升位都会改变产物
    字节（E3：sitin-scoring-view /2→/3 → 2fe03eca… 变为 927beddb…）。金例只在
    GOLDEN_IDENTITY_CONTEXT 记录的上下文下可比：当前上下文不一致时**显式 skip**，
    理由里给出逐项差异与归因证据路径——不静默改数、不放宽（同 T10 案口径）。
    语义不变量由 test_root_indices_prefix_is_byte_identical_to_legacy_roots 与
    test_root_content_digest_is_independent_of_candidate_identity 无条件断言（不受 skip 影响）。
    """

    _freeze_clock(monkeypatch)
    panel, _ = _run_panel(tmp_path, monkeypatch, out_name="golden-roots2", roots=2)
    files = _artifacts(tmp_path / "golden-roots2")
    mismatch = _golden_context_mismatch(panel)
    if mismatch:
        pytest.skip("产物字节级金例绑定的身份上下文与当前不一致（漂移来自结构/合同版本，"
                    "与按根选取能力无关）→ 不比对：{0}；归因证据 {1}；重录口径见 "
                    "FIX-REPORT §8".format("；".join(mismatch), GOLDEN_DRIFT_EVIDENCE))
    assert _sha256(files["panel.json"]) == GOLDEN_LEGACY_ROOTS2_PANEL_SHA256
    assert _sha256(files["samples.jsonl"]) == GOLDEN_LEGACY_ROOTS2_SAMPLES_SHA256
    print("[T8c] 金例（上下文 {0}）：panel.json sha256={1}、samples.jsonl sha256={2}".format(
        GOLDEN_IDENTITY_CONTEXT["scoring_view_schema"],
        _sha256(files["panel.json"])[:16], _sha256(files["samples.jsonl"])[:16]))


def test_golden_context_binding_reports_the_drifting_field(tmp_path):
    """绑定机制自检：上下文某项不一致时**逐项报出**（skip 理由可用、不吞差异）。

    不依赖真实升版：只断言「改动某一项 → 多出一条指名该项的差异」，因此本用例
    自身不会随版本漂移变红（升版时由金例用例 skip 并给出同一套差异文本）。
    """

    shape = {"identity": {"candidate_id": "c" * 64, "contract_sha256": "k" * 64,
                          "av_contract_sha256": "a" * 64}}
    baseline = _golden_context_mismatch(shape)
    drifted = dict(shape)
    drifted["identity"] = dict(shape["identity"], av_contract_sha256="0" * 64)
    added = [item for item in _golden_context_mismatch(drifted) if item not in baseline]
    assert len(added) == 1 and "av_contract_sha256" in added[0], added
    assert "0" * 64 in added[0] and GOLDEN_IDENTITY_CONTEXT["av_contract_sha256"] in added[0]


def test_root_indices_order_is_canonical(tmp_path, monkeypatch):
    """选择集语义=集合：[4,3] 与 [3,4] 产物逐字节一致（顺序不承载证据）。"""

    _freeze_clock(monkeypatch)
    _run_panel(tmp_path, monkeypatch, out_name="idx-3-4", root_indices=[3, 4])
    _run_panel(tmp_path, monkeypatch, out_name="idx-4-3", root_indices=[4, 3])
    assert _artifacts(tmp_path / "idx-3-4") == _artifacts(tmp_path / "idx-4-3")


def test_root_seeds_select_the_same_roots_as_indices(tmp_path, monkeypatch):
    """显式根种子：种子唯一回落到其根序号 → 与按索引选取的产物逐字节一致。"""

    _freeze_clock(monkeypatch)
    seeds = [GOLDEN_ROOT_IDENTITY[3][1], GOLDEN_ROOT_IDENTITY[4][1]]
    by_seed, _ = _run_panel(tmp_path, monkeypatch, out_name="seeds-3-4",
                            root_seeds=seeds)
    assert _root_identity(by_seed) == {3: GOLDEN_ROOT_IDENTITY[3],
                                       4: GOLDEN_ROOT_IDENTITY[4]}
    assert [sample["root_seed"] for sample in by_seed["samples"]] == seeds
    _run_panel(tmp_path, monkeypatch, out_name="idx-3-4", root_indices=[3, 4])
    assert _artifacts(tmp_path / "seeds-3-4") == _artifacts(tmp_path / "idx-3-4")


# ------------------------------------------- 7.3 边界：拒绝先于执行与费用


def test_root_selection_boundaries_rejected_before_any_table(tmp_path, monkeypatch):
    """越界/重复/空列表/多形式并用/未给选择：ValueError 且**早于**任何桌赛与费用。"""

    ledger_path = tmp_path / "boundary-ledger.json"
    cases = (
        ("空索引列表", {"root_indices": []}),
        ("重复索引", {"root_indices": [3, 3]}),
        ("索引下界越界", {"root_indices": [0]}),
        ("索引上界越界", {"root_indices": [natural.MAX_ROOT_INDEX + 1]}),
        ("负数索引", {"root_indices": [-1]}),
        ("非整数索引", {"root_indices": ["3"]}),
        ("布尔索引", {"root_indices": [True]}),
        ("空种子列表", {"root_seeds": []}),
        ("未知种子", {"root_seeds": [1]}),
        ("种子重复指向同根", {"root_seeds": [GOLDEN_ROOT_IDENTITY[3][1],
                                            GOLDEN_ROOT_IDENTITY[3][1]]}),
        ("索引与根数并用", {"roots": 2, "root_indices": [1, 2]}),
        ("根数与种子并用", {"roots": 2, "root_seeds": [GOLDEN_ROOT_IDENTITY[1][1]]}),
        ("索引与种子并用", {"root_indices": [3],
                            "root_seeds": [GOLDEN_ROOT_IDENTITY[3][1]]}),
        ("未给任何选择", {}),
        ("负数根数", {"roots": -1}),
        ("非整数根数", {"roots": 2.0}),
    )
    for label, selection in cases:
        drive = _SeededDrive()
        monkeypatch.setattr(natural, "execute_natural_table", drive, raising=True)
        with pytest.raises(ValueError) as failure:
            natural.run_natural_panel(
                candidate_source=GOOD_SOURCE, opponent="H", seats_per_root=1,
                contract=_contract(), out_dir=tmp_path / ("bad-" + label),
                authorization=BATCH7_TOKEN, ledger_path=ledger_path,
                ledger_authorized_budgets=LEDGER_BUDGETS, **selection)
        assert drive.calls == [], "{0}：拒绝前已启动桌赛".format(label)
        assert "根" in str(failure.value), label  # 报错信息说清是根选择问题
        assert not ledger_path.is_file(), "{0}：拒绝前已产生费用".format(label)
        assert not (tmp_path / ("bad-" + label)).is_dir(), \
            "{0}：拒绝前已建立产物目录".format(label)
    print("[T11] {0} 种非法根选择全部在启动任何桌赛之前被拒（0 桌赛、0 费用、"
          "0 产物）".format(len(cases)))


def test_legacy_zero_roots_keeps_defined_empty_prefix(tmp_path, monkeypatch):
    """旧接口 roots=0 明确定义为空前缀（不新增拒绝）：0 样本、0 桌、产物仍在。"""

    panel, drive = _run_panel(tmp_path, monkeypatch, out_name="legacy-roots0",
                              roots=0)
    assert panel["samples"] == [] and drive.calls == []
    assert panel["config"]["roots"] == 0
    assert panel["cost"]["tables_full_planned"] == 0
    assert (tmp_path / "legacy-roots0" / "panel.json").is_file()


def test_selection_step_identity_keeps_legacy_token(tmp_path):
    """步标识记号：前缀选择沿用旧记号（2），非前缀选择单列（idx3-4）。"""

    assert natural.natural_selection_token((1, 2)) == "2"
    assert natural.natural_selection_token((1, 2, 3, 4)) == "4"
    assert natural.natural_selection_token(()) == "0"
    assert natural.natural_selection_token((3, 4)) == "idx3-4"
    assert natural.natural_selection_token((3,)) == "idx3"
    assert natural.natural_selection_token((2, 3, 4, 5)) == "idx2-3-4-5"


# ------------------------------------------- 7.4 幂等：同根不产生第二实例/第二次计费


def _step_ids(ledger: Any) -> List[str]:
    """账本已登记步标识（ActionValueLedger 的公开视图是 reservations）。"""

    return [str(item["step_id"]) for item in ledger.reservations]


def _instance_rows(panel: Mapping[str, Any],
                   contract: Mapping[str, Any]) -> List[Dict[str, Any]]:
    """按 P6 口径把面板产物折成实例行（来源根 × 座位 × 臂 × 赛程）。"""

    import sitin_search as search
    tables = int(contract["group"]["tables_per_group"])
    schedule = "stage_complete:{0}_tables".format(tables)
    rows: List[Dict[str, Any]] = []
    for sample in panel["samples"]:
        for arm in ("baseline", "candidate"):
            arm_record = (sample.get("raw_arms") or {}).get(arm) or {}
            rows.append({
                "instance_key": search.av_instance_key(
                    source_root_id=sample["source_root_id"],
                    seat=int(sample["focal_anchor_seat"]), arm=arm,
                    schedule=schedule),
                "source_root_id": sample["source_root_id"],
                "seat": int(sample["focal_anchor_seat"]), "arm": arm,
                "schedule": schedule, "opponent_mix": str(sample["opponent_mix"]),
                "planned_tables": tables, "status": "completed",
                "tables": len(arm_record.get("tables") or []),
                "result_digest": _sha256(json.dumps(
                    sample["arms"][arm], ensure_ascii=False,
                    sort_keys=True).encode("utf-8")),
            })
    return rows


def test_repeated_same_root_request_yields_one_instance(tmp_path, monkeypatch):
    """同一根重复请求 → 同一实例键：台账只有一份实例、费用不翻倍（P6 口径）。

    两段证明：①时钟打桩（确定性环境）下两次请求的实例键与结果摘要完全相同，
    台账合并为一组实例、无冲突、单实例费用不翻倍；②同一实例被重复评价且结果
    内容不同（同键、不同不可变摘要）时，实例**数量**仍为 2（不产生第二个实例、
    不覆盖已有结果），差异被 P6 台账记为 conflicts（重复评价是显式告警）。
    """

    import sitin_search as search
    contract = _contract()

    # ① 确定性环境：同一根的两次请求完全同形 → 台账幂等
    _freeze_clock(monkeypatch)
    first, _ = _run_panel(tmp_path, monkeypatch, out_name="repeat-a",
                          root_indices=[3])
    second, _ = _run_panel(tmp_path, monkeypatch, out_name="repeat-b",
                           root_indices=[3])
    rows_a = _instance_rows(first, contract)
    rows_b = _instance_rows(second, contract)
    assert len(rows_a) == 2 and len(rows_b) == 2  # 座位 1 × 2 臂
    assert {row["instance_key"] for row in rows_a} == \
        {row["instance_key"] for row in rows_b}, "同一根必须产生同一实例键"
    assert all(row["instance_key"].startswith("np-H-20260916-root03|seat0|")
               for row in rows_a)
    assert {row["result_digest"] for row in rows_a} == \
        {row["result_digest"] for row in rows_b}
    run_root = tmp_path / "instance-run"
    run_root.mkdir()
    first_report = search.av_instances_apply(run_root, updates=rows_a, attempt_no=1,
                                            iteration_no=1, run_id="run-a")
    assert first_report["n_instances"] == 2 and first_report["conflicts"] == []
    second_report = search.av_instances_apply(run_root, updates=rows_b, attempt_no=2,
                                             iteration_no=2, run_id="run-b")
    assert second_report["n_instances"] == 2, "重复请求产生了第二个实例"
    assert second_report["conflicts"] == []
    registry = search.av_instances_load(run_root)["instances"]
    assert len(registry) == 2
    assert sorted(row["cost"]["tables"] for row in registry.values()) == [2, 2]
    assert all(len(row["attempts"]) == 2 for row in registry.values())

    # ② 同一实例的重复评价结果内容不同（同键不同摘要）：实例数仍为 2，
    #    既有结果不被覆盖，差异被台账记为 conflicts（显式告警而非静默覆盖）
    rows_c = [dict(row, result_digest="0" * 64) for row in rows_a]
    assert {row["instance_key"] for row in rows_c} == \
        {row["instance_key"] for row in rows_a}
    third_report = search.av_instances_apply(run_root, updates=rows_c, attempt_no=3,
                                            iteration_no=3, run_id="run-c")
    assert third_report["n_instances"] == 2, "重复请求产生了第二个实例"
    assert len(third_report["conflicts"]) == 2, "同一实例被重复评价未被告警"
    registry = search.av_instances_load(run_root)["instances"]
    assert len(registry) == 2
    assert {row["result_digest"] for row in registry.values()} == \
        {row["result_digest"] for row in rows_a}, "冲突不得覆盖既有不可变摘要"
    assert sorted(row["cost"]["tables"] for row in registry.values()) == [2, 2]
    print("[T12] root03 重复请求：实例键={0} 三次登记后实例数={1}、单实例费用=2 桌、"
          "同键异摘要告警={2}".format(sorted(registry), len(registry),
                                      len(third_report["conflicts"])))


def test_repeated_identical_selection_is_not_recharged(tmp_path, monkeypatch):
    """同选择集不第二次计费：第二步在预留阶段即被拒（TaskAlreadySettled）。

    同时核对补根不被前缀账行挡住：非前缀选择集有**独立**步标识（idx3-4），
    可以在新预算内正常记账。
    """

    import sitin_search as search
    ledger_path = tmp_path / "av-ledger.json"
    first, _ = _run_panel(tmp_path, monkeypatch, out_name="ledger-legacy",
                          roots=2, ledger_path=ledger_path,
                          ledger_authorized_budgets=LEDGER_BUDGETS)
    ledger = search.ActionValueLedger.load(ledger_path)
    legacy_step = "natural:{0}:H:2".format(first["identity"]["candidate_id"][:12])
    assert legacy_step in _step_ids(ledger), _step_ids(ledger)
    assert ledger.spent("tables_full") == 8.0

    with pytest.raises(search.TaskAlreadySettled):
        _run_panel(tmp_path, monkeypatch, out_name="ledger-again",
                   root_indices=[1, 2], ledger_path=ledger_path,
                   ledger_authorized_budgets=LEDGER_BUDGETS)
    assert search.ActionValueLedger.load(ledger_path).spent("tables_full") == 8.0, \
        "同一选择集被重复计费"

    extra, _ = _run_panel(tmp_path, monkeypatch, out_name="ledger-extra",
                          root_indices=[3, 4], ledger_path=ledger_path,
                          ledger_authorized_budgets=LEDGER_BUDGETS)
    ledger = search.ActionValueLedger.load(ledger_path)
    extra_step = "natural:{0}:H:idx3-4".format(extra["identity"]["candidate_id"][:12])
    assert extra_step in _step_ids(ledger), _step_ids(ledger)
    assert ledger.spent("tables_full") == 16.0
    print("[T13] 同前缀选择集重复请求被拒（步 {0}，费用仍 8.0）；补根选择集独立记账"
          "（步 {1}，累计 16.0）".format(legacy_step, extra_step))
