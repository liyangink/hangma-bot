#!/usr/bin/env python3
"""G33：精确重放 G32 阶段，定位两臂首个可见动作分歧。"""

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

import argparse
import hashlib
import json
from pathlib import Path

import g14_accounted_paired_panel as panel


HERE = Path(__file__).resolve().parent
G32 = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g32-edge-paired-expansion-20260927')
BASELINE = "r18_v2"
CANDIDATE = "candidate@review/freematch-deep-dive-20260925/candidates/G30-EDGE-TIE-ONEWHITE-V1.py"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class TracedPolicy:
    """仅在离线诊断层记录本人可见输入及原策略计划，不改变动作选择。"""

    def __init__(self, policy: object, decisions: list[dict]) -> None:
        self.policy = policy
        self.decisions = decisions
        self.policy_id = getattr(policy, "policy_id", type(policy).__name__)
        self.max_operations = getattr(policy, "max_operations", None)

    async def choose(self, request: object, budget: object) -> object:
        """输入为合法决策请求；输出原策略计划；唯一副作用是内存诊断记录。"""

        result = await self.policy.choose(request, budget)
        observation = request.observation
        selected = result.candidates[0] if result.candidates else None
        self.decisions.append({
            "game_id": observation.game_id,
            "round_no": observation.round_no,
            "trigger_seq": request.trigger_seq,
            "phase": observation.phase,
            "seat": observation.seat,
            "my_hand": [tile.code for tile in observation.my_hand],
            "drawn_tile": None if observation.drawn_tile is None else observation.drawn_tile.code,
            "wealth_god": observation.rule_state.wealth_god.code,
            "remaining_tile_count": observation.remaining_tile_count,
            "scores": list(observation.scores),
            "river_sizes": [len(river) for river in observation.discards],
            "selected_action_key": None if selected is None else selected.action_key,
            "selected_score": None if selected is None else selected.total_score,
            "selected_parts": [] if selected is None else [
                {"name": part.name, "value": part.value} for part in selected.score_parts],
            "ranked_top5": [{"action_key": item.action_key,
                             "score": item.total_score} for item in result.candidates[:5]],
            "legal_progress": {
                item.action_key: {
                    "shanten_after": None if item.facts is None else item.facts.shanten_after,
                    "standard_shanten_after": None if item.facts is None else item.facts.standard_shanten_after,
                    "seven_pairs_shanten_after": None if item.facts is None else item.facts.seven_pairs_shanten_after,
                    "standard_useful_tiles": [] if item.facts is None else [
                        {"code": fact.code, "remaining_estimate": fact.remaining_estimate}
                        for fact in (item.facts.standard_useful_tiles or ())],
                } for item in request.rules.legal_candidates
                if item.action_key.startswith("discard:")},
            "degraded_reasons": list(result.degraded_reasons),
        })
        return result


def trace_unit(mix: str, root: int, seat: int, arm: str, panel_seed: int) -> dict:
    """同一冻结计划重放一阶段，并与 G32 分数及牌山身份对账。"""

    contract = json.loads(panel.paired.CONTRACT.read_text(encoding="utf-8"))
    plans = panel.natural.build_seat_stage_plans(
        contract=contract, opponent=mix, root_index=root,
        focal_seat=seat, panel_seed=panel_seed)
    decisions: list[dict] = []
    factory = panel.paired.policy_factory(arm)

    def traced_factory(monotonic):
        return TracedPolicy(factory(monotonic), decisions)

    stage = panel.accounted.run_accounted_stage(
        plans=plans, candidate_policy_factory=traced_factory,
        opponent_policies=contract["panel"]["opponent_scenarios"][mix]["opponent_policies"],
        versions_block=panel.natural.stage.contract_versions_block(contract),
        step_limit=int(contract["stop"]["step_limit"]),
        value_limits=panel.paired.LIMITS)
    source = json.loads(panel.paired.unit_path(G32, (mix, root, seat, arm, panel_seed)).read_text())
    original = source["stage"]
    if (stage["status"] != "complete" or stage["focal_stage_score"] != original["focal_stage_score"]
            or [table["seed"] for table in stage["tables"]]
            != [table["seed"] for table in original["tables"]]):
        raise ValueError("诊断重放与 G32 阶段结算或牌山身份不一致")
    return {"score": stage["focal_stage_score"], "decisions": decisions}


def first_divergence(baseline: list[dict], candidate: list[dict]) -> dict:
    """仅共同前缀的同一观察可归因于策略；分叉后不逐窗比较。"""

    for index, (left, right) in enumerate(zip(baseline, candidate)):
        identity = ("game_id", "round_no", "trigger_seq", "phase", "seat",
                    "my_hand", "drawn_tile", "wealth_god", "remaining_tile_count",
                    "scores", "river_sizes")
        if any(left[key] != right[key] for key in identity):
            return {"kind": "observation_diverged_before_action", "decision_index": index,
                    "baseline": left, "candidate": right}
        if left["selected_action_key"] != right["selected_action_key"]:
            return {"kind": "same_observation_different_action", "decision_index": index,
                    "baseline": left, "candidate": right}
    return {"kind": "no_difference_in_common_prefix", "common_decisions":
            min(len(baseline), len(candidate)), "baseline_decisions": len(baseline),
            "candidate_decisions": len(candidate)}


def main() -> None:
    """写冻结诊断产物；目标单元可重复指定，不覆盖已有输出。"""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", action="append", required=True,
                        help="池:根:座位，如 H:8:3")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        parser.error("输出已存在，拒绝覆盖")
    manifest_path = _project_file(_PROJECT_ROOT, G32 / "manifest.json")
    manifest = json.loads(manifest_path.read_text())
    if manifest["arms"] != [BASELINE, CANDIDATE]:
        raise ValueError("G32 两臂身份已漂移")
    rows = []
    for target in args.target:
        mix, root_text, seat_text = target.split(":")
        root, seat = int(root_text), int(seat_text)
        if mix not in ("H", "M") or not 1 <= root <= 12 or seat not in range(4):
            parser.error("目标必须属于 G32 的 H/M、根 1–12、座位 0–3")
        base = trace_unit(mix, root, seat, BASELINE, manifest["panel_seed"])
        cand = trace_unit(mix, root, seat, CANDIDATE, manifest["panel_seed"])
        rows.append({"target": target, "baseline_stage_score": base["score"],
                     "candidate_stage_score": cand["score"],
                     "first_divergence": first_divergence(base["decisions"], cand["decisions"])})
    payload = {"schema": "g33-first-divergence/1", "g32_manifest_sha256": sha(manifest_path),
               "candidate_source_sha256": manifest["candidate_sources"][CANDIDATE],
               "rows": rows, "scope": "开发根离线诊断；只比较分叉前同一本人观察，不作净收益因果归因"}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                        encoding="utf-8")
    print(json.dumps({"targets": len(rows), "kinds":
                      [row["first_divergence"]["kind"] for row in rows]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
