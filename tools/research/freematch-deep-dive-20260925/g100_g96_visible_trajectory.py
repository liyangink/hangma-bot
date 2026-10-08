#!/usr/bin/env python3
"""G100：逐分支记录焦点座位依法可见行动链，并与 G96 结算恒等对账。"""

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
import gzip
import hashlib
import json
from pathlib import Path
from typing import Any

import g95_wider_discard_same_hand_preflight as g95
from hangma_bot.application.audit_codec import candidate_value_facts_to_json
from hangma_bot.hangma.engine import _build_context


HERE = Path(__file__).resolve().parent
SOURCE = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g96-wider-discard-branch-expansion-20260928/result.json')
PREREG = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/G100-G96-PAIRED-VISIBLE-TRAJECTORY-PREREG-2026-09-28.md')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g100-g96-paired-visible-trajectory-20260928/result.json.gz')


def sha(path: Path) -> str:
    """记录冻结输入和量具的 SHA-256。"""
    return hashlib.sha256(path.read_bytes()).hexdigest()


class TracePolicy:
    """透明记录焦点策略真实收到的观察与实际首选动作，不读取模拟世界。"""

    def __init__(self, inner: Any) -> None:
        self.inner = inner
        self.policy_id = getattr(inner, "policy_id", None)
        self.records: list[dict] = []

    async def choose(self, request: Any, budget: Any) -> Any:
        """只在策略返回后记录生产合法事实；不修改候选与动作。"""
        plan = await self.inner.choose(request, budget)
        if not plan.candidates:
            raise ValueError("G100 焦点策略未返回任何候选")
        key = plan.candidates[0].action_key
        legal = {candidate.action_key: candidate
                 for candidate in request.rules.legal_candidates}
        chosen = legal.get(key)
        if chosen is None:
            raise ValueError("G100 焦点首选不在生产合法动作表")
        observation = request.observation
        full = _build_context(observation).full_hand()
        facts = chosen.facts
        value = (candidate_value_facts_to_json(chosen.value_facts)
                 if chosen.value_facts is not None else None)
        routes = None
        highfan_routes = None
        if value is not None and value["coverage"] == "complete":
            normal = [route for route in value["routes"]
                      if route["followup_discard"] is None and
                      route["conditions"]["draw_kind"] == "normal"]
            routes = len(normal)
            highfan_routes = sum(
                (route["conditional_settlement"] or {}).get("fan", 0) >= 2
                for route in normal)
        useful = None
        if facts is not None and facts.standard_useful_tiles is not None:
            useful = [
                {"code": item.code, "public_unseen_capacity": item.remaining_estimate}
                for item in facts.standard_useful_tiles
            ]
        before = sum(tile.code == "白" for tile in full)
        after = before - int(key == "discard:白") if key.startswith("discard:") else None
        self.records.append({
            "window": g95.g93.window_key_to_json(request.window_key),
            "action_key": key,
            "hand_codes": [tile.code for tile in full],
            "white_before": before,
            "white_after_discard": after,
            "wall_remaining": observation.remaining_tile_count,
            "catch_play": observation.rule_state.catch_play,
            "catch_play_owner_seat": observation.rule_state.catch_play_owner_seat,
            "chain_count": observation.rule_state.chain_count,
            "chain_piao": observation.chain_piao,
            "meld_count": len(observation.melds[observation.seat]),
            "legal_immediate_hu": any(action.startswith("hu") for action in legal),
            "standard_shanten_after": (
                None if facts is None else facts.standard_shanten_after),
            "seven_pairs_shanten_after": (
                None if facts is None else facts.seven_pairs_shanten_after),
            "standard_useful_tiles": useful,
            "baotou_after": None if facts is None else facts.baotou_after,
            "one_draw_value_coverage": None if value is None else value["coverage"],
            "one_draw_win_routes": routes,
            "one_draw_highfan_routes": highfan_routes,
        })
        return plan


def run_branch(*, world: Any, captured: Any, plan: Any, contract: dict,
               versions: dict, runtime: dict, rules: Any, situation: Any,
               mix: str, forced_key: str | None) -> dict:
    """同 G95 单局续打，外层只读记录焦点座位每次实际策略调用。"""
    g93 = g95.g93
    target = captured.request.window_key
    single = g95.SettlementOnlyHandEngine(runtime["engine"], target.round_no)
    clock = g93.ManualClock(start_monotonic=800.0, wait_scale=1.0)
    policies = list(g95.policies_for(plan, contract, clock, mix))
    force = None
    if forced_key is not None:
        force = g93.ForceOncePolicy(policies[target.seat], target, forced_key)
        policies[target.seat] = force
    traced = TracePolicy(policies[target.seat])
    policies[target.seat] = traced
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
        raise ValueError("G100 轨迹分支未正常结算")
    if force is not None and force.used != 1:
        raise ValueError("G100 备选动作未恰好强制一次")
    counts = asdict(outcome.runtime_counts)
    if any(counts.get(key, 0) for key in ("fallbacks", "illegal_choices", "timeouts")):
        raise ValueError("G100 分支有降级、非法或超时")
    expected = captured.parent_key if forced_key is None else forced_key
    if not outcome.decisions or outcome.decisions[0].action_key != expected:
        raise ValueError("G100 分支首动作漂移")
    focal = [decision for decision in outcome.decisions if decision.seat == target.seat]
    if len(focal) != len(traced.records):
        raise ValueError("G100 焦点策略调用与已执行决策数不一致")
    for decision, record in zip(focal, traced.records):
        if (decision.action_key != record["action_key"] or
                dict(decision.window_key) != record["window"]):
            raise ValueError("G100 焦点轨迹行动或窗口与驱动审计不一致")
    return {"settlement": single.settlement,
            "decision_count": len(outcome.decisions),
            "first_decision_action": outcome.decisions[0].action_key,
            "forced_once": 0 if force is None else force.used,
            "runtime_counts": counts,
            "focal_trajectory": traced.records}


def main() -> None:
    """重建 G96 全部双臂九世界；逐分支恒等后冻结压缩轨迹。"""
    if OUT.exists():
        raise FileExistsError("G100 已有轨迹证据，拒绝覆盖")
    source = json.loads(SOURCE.read_text(encoding="utf-8"))
    if source["schema"] != "g96-wider-discard-branch-expansion/1":
        raise ValueError("G100 输入 schema 漂移")
    g93 = g95.g93
    contract = json.loads(g93.paired.CONTRACT.read_text(encoding="utf-8"))
    versions = g93.natural.stage.contract_versions_block(contract)
    rows = []
    for old in source["rows"]:
        mix, root, seat = old["mix"], old["root_index"], old["focal_seat"]
        plan = g93.natural.build_seat_stage_plans(
            contract=contract, opponent=mix, root_index=root,
            focal_seat=seat, panel_seed=source["panel_seed"])[0]
        captured, runtime, rules, situation, _, outcome = g95.run_full(
            plan, contract, versions, mix)
        if (plan.table_id != old["table_id"] or
                list(outcome.final_scores or ()) != old["full_parent_final_scores"]):
            raise ValueError("G100 父代表身份或终分漂移")
        if old["status"] == "no_window":
            if captured.world is not None:
                raise ValueError("G100 原无命中桌意外命中")
            continue
        if (old["status"] != "paired" or captured.world is None or
                g93.window_key_to_json(captured.request.window_key) != old["target_window"]
                or captured.parent_key != old["parent_action"] or
                captured.alternate_key != old["alternate_action"] or
                captured.facts != old["visible_action_facts"]):
            raise ValueError("G100 目标窗口或规则事实漂移")
        reference = runtime["engine"].frame(captured.world).decisions[0].observation
        pairs = []
        for original in old["world_pairs"]:
            sample_key = original["sample_key"]
            world = (captured.world if sample_key == "historical" else
                     runtime["engine"].resample_public_consistent_hidden_world(
                         captured.world, focal_seat=seat, sample_key=sample_key))
            if runtime["engine"].frame(world).decisions[0].observation != reference:
                raise ValueError("G100 重采样改变焦点玩家可见观察")
            pair = {arm: run_branch(
                world=world, captured=captured, plan=plan, contract=contract,
                versions=versions, runtime=runtime, rules=rules,
                situation=situation, mix=mix,
                forced_key=(None if arm == "parent" else captured.alternate_key))
                for arm in ("parent", "alternate")}
            for arm in ("parent", "alternate"):
                for field in ("settlement", "decision_count", "first_decision_action",
                              "forced_once", "runtime_counts"):
                    if pair[arm][field] != original[arm][field]:
                        raise ValueError("G100 分支与 G96 原证据漂移：" + field)
            pairs.append({"sample_key": sample_key, **pair})
        rows.append({"mix": mix, "root_index": root, "focal_seat": seat,
                     "table_id": plan.table_id,
                     "target_window": old["target_window"],
                     "parent_action": captured.parent_key,
                     "alternate_action": captured.alternate_key,
                     "white_before": old["white_before"],
                     "pairs": pairs})
        print(json.dumps({"mix": mix, "root": root, "seat": seat,
                          "world_pairs": len(pairs)}, ensure_ascii=False), flush=True)
    if len(rows) != sum(old["status"] == "paired" for old in source["rows"]):
        raise ValueError("G100 完成窗口数不符")
    result = {"schema": "g100-g96-paired-visible-trajectory/1",
              "exploratory": True,
              "input_sha256": {"g96": sha(SOURCE), "prereg": sha(PREREG),
                               "script": sha(Path(__file__)),
                               "g95_branch": sha(_project_file(_PROJECT_ROOT, HERE / "g95_wider_discard_same_hand_preflight.py"))},
              "rows": rows,
              "boundary": "逐次记录只来自焦点玩家可见 DecisionRequest；隐藏世界仅推进离线分支，"
                          "九世界同窗相关且非历史后验；不能把结果回填为在线事实或训练标签。"}
    body = (json.dumps(result, ensure_ascii=False, sort_keys=True,
                       separators=(",", ":")) + "\n").encode("utf-8")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_bytes(gzip.compress(body, compresslevel=9, mtime=0))
    print(json.dumps({"windows": len(rows),
                      "world_pairs": sum(len(row["pairs"]) for row in rows),
                      "bytes_gzip": OUT.stat().st_size}, ensure_ascii=False))


if __name__ == "__main__":
    main()
