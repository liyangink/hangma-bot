#!/usr/bin/env python3
"""G95：结果盲取宽面弃牌，在相同隐藏样本内续打两条单局分支。"""

from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/freematch-deep-dive-20260925'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

import asyncio
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
from typing import Any

import g93_same_hand_branch_preflight as g93


HERE = Path(__file__).resolve().parent
PREREG = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/G95-WIDER-DISCARD-SAME-HAND-PREFLIGHT-PREREG-2026-09-28.md')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g95-wider-discard-same-hand-preflight-20260928/result.json')
PANEL_SEED = 2026110901
SAMPLES = tuple(f"g95-{index:02d}" for index in range(1, 9))


def sha(path: Path) -> str:
    """把面板合同、事前计划及程序身份写入结果。"""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def policies_for(plan: Any, contract: dict, clock: Any, mix: str) -> tuple[Any, ...]:
    """按物理座位装配冻结 R18 v2 与 H/M 工程对手。"""
    natural = g93.natural
    logical = natural.arm_logical_policies(
        arm="candidate", candidate_scorer=None,
        logical_participants=plan.logical_participants,
        opponent_policies=contract["panel"]["opponent_scenarios"][mix]["opponent_policies"],
        monotonic=clock.now,
        candidate_policy_factory=g93.paired.policy_factory("r18_v2"))
    return natural.seat_policies_from(
        logical, plan.permutation, plan.logical_participants)


class CaptureWiderPolicy:
    """只取首个同普通型向听、两项公开进张都更宽的合法非白弃牌。"""

    def __init__(self, inner: Any, capture_engine: g93.CaptureEngine) -> None:
        self.inner = inner
        self.capture_engine = capture_engine
        self.policy_id = getattr(inner, "policy_id", None)
        self.world: Any = None
        self.request: Any = None
        self.parent_key: str | None = None
        self.alternate_key: str | None = None
        self.facts: dict[str, dict] = {}

    async def choose(self, request: Any, budget: Any) -> Any:
        """先取父代完整计划，命中时只保存窗口与不透明世界，不改当前动作。"""
        plan = await self.inner.choose(request, budget)
        if self.world is not None or request.window_key.phase is not g93.WindowPhase.DRAW:
            return plan
        observation = request.observation
        if not any(meld.kind in ("chi", "peng")
                   for meld in observation.melds[observation.seat]):
            return plan
        if not plan.candidates:
            return plan
        parent = plan.candidates[0].action_key
        if not parent.startswith("discard:") or parent == "discard:白":
            return plan
        entries = {candidate.action_key: candidate.facts
                   for candidate in request.rules.legal_candidates}
        parent_facts = entries.get(parent)
        if parent_facts is None or type(parent_facts.standard_shanten_after) is not int:
            return plan

        def width(action_key: str) -> tuple[int, int]:
            """有效牌码数与公开未见容量是玩家可见事实，不是实墙张数。"""
            useful = entries[action_key].standard_useful_tiles or ()
            return len(useful), sum(tile.remaining_estimate for tile in useful)

        parent_width = width(parent)
        eligible = []
        for ranked in plan.candidates[1:]:
            action_key = ranked.action_key
            facts = entries.get(action_key)
            if (not action_key.startswith("discard:") or action_key == "discard:白"
                    or facts is None
                    or facts.standard_shanten_after != parent_facts.standard_shanten_after):
                continue
            candidate_width = width(action_key)
            if (candidate_width[0] > parent_width[0]
                    and candidate_width[1] > parent_width[1]):
                eligible.append(action_key)
        if not eligible:
            return plan
        alternate = min(eligible, key=lambda key: (-width(key)[0], -width(key)[1], key))
        if self.capture_engine.latest_world is None:
            raise ValueError("G95 未取得本次决策的模拟器世界引用")
        self.world = self.capture_engine.latest_world
        self.request = request
        self.parent_key = parent
        self.alternate_key = alternate
        self.facts = {key: {
            "standard_shanten_after": entries[key].standard_shanten_after,
            "ordinary_codes": width(key)[0],
            "public_unseen_capacity": width(key)[1],
        } for key in (parent, alternate)}
        return plan


class SettlementOnlyHandEngine:
    """单局结算后截停驱动；只使用 simulation 的公开最小结算出口。"""

    def __init__(self, inner: Any, target_round: int) -> None:
        self.inner = inner
        self.target_round = target_round
        self.settlement: dict | None = None

    def frame(self, world: Any) -> Any:
        base = self.inner.frame(world)
        if base.completed_hands < self.target_round:
            return base
        if self.settlement is None:
            self.settlement = self.inner.export_hand_settlement(world, self.target_round)
        return g93.SimulationFrame(
            revision=base.revision, decisions=(), completed_hands=base.completed_hands,
            final_scores=tuple(self.settlement["scores_after"]), blocked_reason=None)

    def advance(self, world: Any, revision: int, choices: Any) -> Any:
        return self.inner.advance(world, revision, choices)


def run_full(plan: Any, contract: dict, versions: dict, mix: str) -> tuple:
    """完成一张冻结父代表，保存首个合格世界与正式单局结算对照。"""
    runtime, spec, rules = g93.runtime_for(plan, versions)
    inner = g93.HandAccountingEngine(runtime["engine"])
    capture_engine = g93.CaptureEngine(inner)
    clock = g93.ManualClock(start_monotonic=800.0, wait_scale=1.0)
    policies = list(policies_for(plan, contract, clock, mix))
    focal_seat = plan.seats().index(g93.natural.FOCAL_PARTICIPANT)
    captured = CaptureWiderPolicy(policies[focal_seat], capture_engine)
    policies[focal_seat] = captured
    situation = g93.natural.build_stage_situation(
        plan=plan, table_no=1, tables_completed=0, totals={}, place_totals={},
        rounds_per_game=int(versions["rounds_per_game"]))
    config = g93.MatchDriverConfig(
        clock_mode=str(versions["clock_mode"]),
        step_limit=int(contract["stop"]["step_limit"]),
        budget_policy=g93.BudgetPolicy(), competition_tournament_id=plan.scenario_id)
    outcome = asyncio.run(g93.drive_match(
        engine=capture_engine, spec=spec, policies_by_seat=tuple(policies),
        rules=rules, choice_factory=runtime["choice_factory"],
        config=config, now_monotonic=clock.now, wall_clock=None,
        value_limits=g93.paired.LIMITS, stage_situation=situation))
    if outcome.status != "complete" or len(inner.hands) != int(versions["rounds_per_game"]):
        raise ValueError("G95 原父代表未完成全部单局")
    counts = asdict(outcome.runtime_counts)
    if any(counts.get(key, 0) for key in ("fallbacks", "illegal_choices", "timeouts")):
        raise ValueError("G95 原父代表发生降级、非法或超时")
    return captured, runtime, rules, situation, inner.hands, outcome


def run_branch(*, world: Any, captured: CaptureWiderPolicy, plan: Any,
               contract: dict, versions: dict, runtime: dict, rules: Any,
               situation: Any, mix: str, forced_key: str | None) -> dict:
    """从给定同一世界各运行一支，目标窗口外均用冻结父代。"""
    target = captured.request.window_key
    single = SettlementOnlyHandEngine(runtime["engine"], target.round_no)
    clock = g93.ManualClock(start_monotonic=800.0, wait_scale=1.0)
    policies = list(policies_for(plan, contract, clock, mix))
    force = None
    if forced_key is not None:
        force = g93.ForceOncePolicy(policies[target.seat], target, forced_key)
        policies[target.seat] = force
    snapshot = {
        "observation_summary": g93.frame_observation_summary(runtime["engine"].frame(world)),
        "match_spec": {"match_id": plan.match_id},
    }
    config = g93.MatchDriverConfig(
        clock_mode=str(versions["clock_mode"]),
        step_limit=int(contract["stop"]["step_limit"]),
        budget_policy=g93.BudgetPolicy(), competition_tournament_id=plan.scenario_id)
    outcome = asyncio.run(g93.resume_match(
        engine=single, world=world, policies_by_seat=tuple(policies),
        rules=rules, choice_factory=runtime["choice_factory"],
        config=config, now_monotonic=clock.now, wall_clock=None,
        stage_snapshot=snapshot,
        remaining_schedule={"declared_endpoint": "target_round_settlement"},
        value_limits=g93.paired.LIMITS, stage_situation=situation))
    if outcome.status != "complete" or single.settlement is None:
        raise ValueError("G95 同局续打未完整结算")
    if force is not None and force.used != 1:
        raise ValueError("G95 备选弃牌未恰好执行一次")
    counts = asdict(outcome.runtime_counts)
    if any(counts.get(key, 0) for key in ("fallbacks", "illegal_choices", "timeouts")):
        raise ValueError("G95 同局续打发生降级、非法或超时")
    expected = captured.parent_key if forced_key is None else forced_key
    if not outcome.decisions or outcome.decisions[0].action_key != expected:
        raise ValueError("G95 续打首动作与预登记动作不一致")
    return {"settlement": single.settlement,
            "decision_count": len(outcome.decisions),
            "first_decision_action": outcome.decisions[0].action_key,
            "forced_once": 0 if force is None else force.used,
            "runtime_counts": counts}


def classify(settlement: dict, focal_seat: int) -> str:
    """按实际结算而非未来预测给本人单局收入分类。"""
    if settlement["is_draw"]:
        return "draw"
    if settlement["winner_seat"] != focal_seat:
        return "other_win"
    return "plain_self_win" if settlement["details"] == ["平胡"] else "special_self_win"


def main() -> None:
    """H/M 四座结果盲找窗，逐窗九个世界配对，保存最小结算及审计。"""
    if OUT.exists():
        raise FileExistsError("G95 证据已存在，拒绝覆盖")
    contract = json.loads(g93.paired.CONTRACT.read_text(encoding="utf-8"))
    versions = g93.natural.stage.contract_versions_block(contract)
    rows = []
    for mix in ("H", "M"):
        for seat in range(4):
            plan = g93.natural.build_seat_stage_plans(
                contract=contract, opponent=mix, root_index=1,
                focal_seat=seat, panel_seed=PANEL_SEED)[0]
            captured, runtime, rules, situation, hands, outcome = run_full(
                plan, contract, versions, mix)
            row = {"mix": mix, "root_index": 1, "focal_seat": seat,
                   "table_id": plan.table_id, "seed": plan.seed,
                   "full_parent_final_scores": list(outcome.final_scores or ())}
            if captured.world is None:
                row["status"] = "no_window"
                rows.append(row)
                continue
            target = captured.request.window_key
            focal_observation = runtime["engine"].frame(captured.world).decisions[0].observation
            row.update({"status": "paired", "target_window": g93.window_key_to_json(target),
                        "parent_action": captured.parent_key,
                        "alternate_action": captured.alternate_key,
                        "visible_action_facts": captured.facts,
                        "white_before": sum(tile.code == "白" for tile in
                                            captured.request.observation.my_hand)
                        + int(captured.request.observation.drawn_tile is not None
                              and captured.request.observation.drawn_tile.code == "白")})
            worlds = [("historical", captured.world)]
            for sample_key in SAMPLES:
                sampled = runtime["engine"].resample_public_consistent_hidden_world(
                    captured.world, focal_seat=target.seat, sample_key=sample_key)
                if runtime["engine"].frame(sampled).decisions[0].observation != focal_observation:
                    raise ValueError("G95 隐藏重采样改变焦点玩家可见观察")
                worlds.append((sample_key, sampled))
            paired_worlds = []
            for sample_key, world in worlds:
                parent = run_branch(
                    world=world, captured=captured, plan=plan, contract=contract,
                    versions=versions, runtime=runtime, rules=rules,
                    situation=situation, mix=mix, forced_key=None)
                alternate = run_branch(
                    world=world, captured=captured, plan=plan, contract=contract,
                    versions=versions, runtime=runtime, rules=rules,
                    situation=situation, mix=mix, forced_key=captured.alternate_key)
                p = parent["settlement"]
                a = alternate["settlement"]
                if p["scores_before"] != a["scores_before"]:
                    raise ValueError("G95 配对分支单局起点积分不一致")
                if sample_key == "historical":
                    old = hands[target.round_no - 1]
                    for field in ("round_no", "scores_before", "scores_after", "score_delta",
                                  "winner_seat", "is_draw", "fan", "details"):
                        if p[field] != old[field]:
                            raise ValueError("G95 历史世界父代单局恒等失败：" + field)
                paired_worlds.append({
                    "sample_key": sample_key,
                    "parent": parent,
                    "alternate": alternate,
                    "focal_delta_alt_minus_parent":
                        a["score_delta"][target.seat] - p["score_delta"][target.seat],
                    "parent_class": classify(p, target.seat),
                    "alternate_class": classify(a, target.seat),
                })
            row["world_pairs"] = paired_worlds
            rows.append(row)
            print(json.dumps({"mix": mix, "seat": seat, "status": "paired",
                              "target_round": target.round_no,
                              "sample_deltas": [w["focal_delta_alt_minus_parent"]
                                                for w in paired_worlds]}, ensure_ascii=False),
                  flush=True)
    result = {
        "schema": "g95-wider-discard-same-hand-preflight/1",
        "panel_seed": PANEL_SEED, "sample_keys": list(SAMPLES),
        "input_sha256": {"prereg": sha(PREREG), "script": sha(Path(__file__)),
                         "g93_script": sha(Path(g93.__file__)),
                         "contract": sha(g93.paired.CONTRACT)},
        "rows": rows,
        "boundary": "各配对样本仅比较同一单局；公开一致重采样不是历史后验，"
                    "重复窗口/世界不是独立完整桌赛；本结果不签发候选准入。",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                   encoding="utf-8")
    print(json.dumps({"tables": len(rows),
                      "paired": sum(row["status"] == "paired" for row in rows)},
                     ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
