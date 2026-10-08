#!/usr/bin/env python3
"""G215：同牌山复跑已见 G211 首分叉局，采集本座可见请求和真实合法后继。"""

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

from hashlib import sha256
import json
from pathlib import Path
from typing import Any

import g14_accounted_paired_panel as panel
import g210_post_claim_guarded_familiar_policy as candidate
from hangma_bot.application.audit_codec import (
    decision_request_from_json,
    decision_request_to_json,
)


HERE = Path(__file__).resolve().parent
ROOT = _PROJECT_ROOT
SOURCE = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g211-g210-hm-development-20260929')
FIRST = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g213-first-changed-hand-20260929/result.json')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g215-first-divergence-visible-trace-20260929/result.json')
SEED = 20261229210


def digest(path: Path) -> str:
    """绑定原始完整桌和首触局证据。"""
    return sha256(path.read_bytes()).hexdigest()


def compact_request(request: Any) -> dict:
    """仅保留策略当时可见事实；不读取模拟完整世界或未来牌墙。"""
    observation = request.observation
    return {
        "decision_id": request.decision_id,
        "game_id": observation.game_id,
        "round_no": observation.round_no,
        "trigger_seq": request.trigger_seq,
        "phase": request.window_key.phase.value,
        "seat": observation.seat,
        "hand": [tile.code for tile in observation.my_hand],
        "drawn_tile": None if observation.drawn_tile is None
                      else observation.drawn_tile.code,
        "wealth_god": observation.rule_state.wealth_god.code,
        "chain_count": observation.rule_state.chain_count,
        "chain_piao": observation.chain_piao,
        "baotou": observation.rule_state.baotou,
        "remaining_tile_count": observation.remaining_tile_count,
        "scores_by_seat": list(observation.scores),
        "legal_actions": [item.action_key for item in request.rules.legal_candidates],
    }


class RecordingPolicy:
    """只读记录最终策略计划；原样返回，不修改动作、预算或时钟。"""

    def __init__(self, parent: Any, records: dict[str, dict], target: dict) -> None:
        self.parent = parent
        self.records = records
        self.target = target
        self.policy_id = getattr(parent, "policy_id", type(parent).__name__)
        self.max_operations = getattr(parent, "max_operations", None)

    async def choose(self, request: Any, budget: Any) -> Any:
        """在研究桌记录动作；所有选择权保留给原策略。"""
        plan = await self.parent.choose(request, budget)
        if (self.target["table_id"] in request.decision_id
                and request.observation.round_no == self.target["round_no"]):
            record = self.records[request.decision_id]
            record["chosen_action"] = (None if not plan.candidates
                                       else plan.candidates[0].action_key)
            record["plan_revision"] = plan.revision
        return plan


def run_one(target: dict, arm: str, contract: dict) -> dict:
    """按 G211 同根同座完整阶段复跑；观察器只记目标单局。"""
    mix = target["mix"]
    root = target["root_index"]
    seat = target["stage_start_seat"]
    plans = panel.natural.build_seat_stage_plans(
        contract=contract, opponent=mix, root_index=root,
        focal_seat=seat, panel_seed=SEED)
    rows: dict[str, dict] = {}
    metrics: list[dict] = []

    def observe(request: Any) -> None:
        if (target["table_id"] not in request.decision_id
                or request.observation.round_no != target["round_no"]):
            return
        if request.decision_id in rows:
            raise ValueError("同一决策标识重复进入观察器")
        record = compact_request(request)
        if request.trigger_seq == target["first_seq"]:
            complete = decision_request_to_json(request)
            if decision_request_to_json(decision_request_from_json(complete)) != complete:
                raise ValueError("首分叉完整可见请求不能无损往返")
            record["complete_request"] = complete
        rows[request.decision_id] = record

    def factory(monotonic: Any) -> RecordingPolicy:
        original = (candidate.parent_factory(monotonic) if arm == "r18_v2"
                    else candidate.policy_factory(metrics)(monotonic))
        return RecordingPolicy(original, rows, target)

    stage = panel.natural.run_arm_stage(
        arm="candidate", plans=plans, candidate_scorer=None,
        candidate_policy_factory=factory,
        decision_observer=observe,
        opponent_policies=contract["panel"]["opponent_scenarios"][mix]["opponent_policies"],
        versions_block=panel.natural.stage.contract_versions_block(contract),
        step_limit=int(contract["stop"]["step_limit"]),
        value_limits=panel.paired.LIMITS)
    archived_path = _project_file(_PROJECT_ROOT, SOURCE / "stages" / f"{mix}-r{root:04d}-s{seat}-{arm}.json")
    archived = json.loads(archived_path.read_text(encoding="utf-8"))["stage"]
    if stage["status"] != "complete" or archived["status"] != "complete":
        raise ValueError("复跑或归档阶段未完成")
    if (stage["focal_stage_score"] != archived["focal_stage_score"]
            or len(stage["tables"]) != len(archived["tables"])):
        raise ValueError("复跑阶段分或桌数与归档不同")
    checks = []
    for now, before in zip(stage["tables"], archived["tables"]):
        equal = {
            "table_id": now["table_id"],
            "same_seed": now["seed"] == before["seed"],
            "same_scores": now["scores_by_seat"] == before["scores_by_seat"],
            "same_runtime_counts": now["result"]["runtime_counts"]
                                   == before["result"]["runtime_counts"],
            "same_policy_execution": now["policy_execution"]
                                     == before["policy_execution"],
        }
        if not all(value for key, value in equal.items() if key != "table_id"):
            raise ValueError("复跑桌与归档发生非观测性偏移：" + repr(equal))
        checks.append(equal)
    timeline = sorted(rows.values(), key=lambda row: row["trigger_seq"])
    if not timeline or any("chosen_action" not in row for row in timeline):
        raise ValueError("目标单局观察与实际动作不完整")
    first = [row for row in timeline if row["trigger_seq"] == target["first_seq"]]
    if len(first) != 1:
        raise ValueError("目标首分叉窗口未唯一复现")
    expected = (target["first_parent_action"] if arm == "r18_v2"
                else target["first_alternate_action"])
    if first[0]["chosen_action"] != expected:
        raise ValueError("首分叉动作与冻结 G213 不同")
    target_table = next(row for row in stage["tables"]
                        if row["table_id"] == target["table_id"])
    return {
        "arm": arm,
        "archived_stage_sha256": digest(archived_path),
        "stage_score": stage["focal_stage_score"],
        "table_parity": checks,
        "target_table_scores_by_seat": target_table["scores_by_seat"],
        "target_hand_trace": timeline,
        "g210_adoptions_in_stage": sum(row["status"] == "adopted" for row in metrics),
    }


def main() -> None:
    """既有开发根只做确定性记录核验；不充当新候选确认集。"""
    if OUT.exists():
        raise FileExistsError("G215 证据已存在，拒绝覆盖")
    first = json.loads(FIRST.read_text(encoding="utf-8"))
    manifest = json.loads((_project_file(_PROJECT_ROOT, SOURCE / "manifest.json")).read_text(encoding="utf-8"))
    if manifest["panel_seed"] != SEED or first["schema"] != "g213-first-changed-hand-audit/1":
        raise ValueError("已见开发输入身份不符")
    contract = json.loads(panel.paired.CONTRACT.read_text(encoding="utf-8"))
    targets = [next(row for row in first["rows"] if row["mix"] == mix
                    and row["root_index"] == 1 and row["stage_start_seat"] == 0)
               for mix in ("H", "M")]
    result = {
        "schema": "g215-first-divergence-visible-trace/1",
        "source_sha256": {"g213": digest(FIRST),
                          "g211_manifest": digest(_project_file(_PROJECT_ROOT, SOURCE / "manifest.json")),
                          "contract": digest(panel.paired.CONTRACT)},
        "targets": [],
        "boundary": "已看 G211 根的可见请求和同世界实际行动链诊断；不含对手暗手或未来墙，不是新根收益证据。",
    }
    for target in targets:
        arms = {arm: run_one(target, arm, contract)
                for arm in ("r18_v2", "g210_postclaim_guarded_familiar_v1")}
        before = next(row for row in arms["r18_v2"]["target_hand_trace"]
                      if row["trigger_seq"] == target["first_seq"])
        after = next(row for row in arms["g210_postclaim_guarded_familiar_v1"]["target_hand_trace"]
                     if row["trigger_seq"] == target["first_seq"])
        if before["complete_request"] != after["complete_request"]:
            raise ValueError("首分叉两臂行动前可见状态或合法动作不一致")
        result["targets"].append({
            "identity": {key: target[key] for key in
                         ("mix", "root_index", "stage_start_seat", "table_id",
                          "actual_focal_seat", "round_no", "first_seq",
                          "first_parent_action", "first_alternate_action")},
            "first_request_equal": True,
            "first_request_sha256": sha256(json.dumps(
                before["complete_request"], ensure_ascii=False,
                sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest(),
            "arms": arms,
        })
        print(json.dumps({"mix": target["mix"], "table": target["table_id"],
                          "parent_decisions": len(arms["r18_v2"]["target_hand_trace"]),
                          "candidate_decisions": len(arms["g210_postclaim_guarded_familiar_v1"]["target_hand_trace"])},
                         ensure_ascii=False), flush=True)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                   encoding="utf-8")


if __name__ == "__main__":
    main()
