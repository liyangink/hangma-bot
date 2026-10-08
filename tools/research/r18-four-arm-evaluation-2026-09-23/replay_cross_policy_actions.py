"""在两臂实网玩家观察上互相重放冻结策略，定位动作差异而不推断收益。"""

from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/r18-four-arm-evaluation-2026-09-23'

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
import json
from pathlib import Path
import sys
import time


ROOT = _PROJECT_ROOT
sys.path.insert(0, str(_project_file(_PROJECT_ROOT, ROOT / "src")))

from hangma_bot.application.audit_codec import decision_request_from_json  # noqa: E402
from hangma_bot.bootstrap import RISK_CELLS, RISK_VERSION, SAFETY_MARGIN  # noqa: E402
from hangma_bot.policy.interface import DecisionBudget  # noqa: E402
from hangma_bot.policy.r18_integrated_positive_v2_release import (  # noqa: E402
    R18IntegratedPositiveV2ReleasePolicy,
    R18_INTEGRATED_POSITIVE_V2_RELEASE_PACKAGE_ID,
    R18_INTEGRATED_POSITIVE_V2_RULES_SOURCE_HASH,
    R18_INTEGRATED_POSITIVE_V2_VALUE_ANALYSIS_SHA256,
)
from hangma_bot.policy.v2_hu_upgrade import V2HuUpgradePolicy  # noqa: E402


def _load_pairs(path: Path) -> list[tuple[dict, dict]]:
    """按决策身份与修订号连接真实输入和计划，拒绝丢失或重复。"""

    inputs = {}
    plans = {}
    for line in path.open(encoding="utf-8"):
        row = json.loads(line)
        payload = row.get("payload") or {}
        if row.get("kind") == "decision_input":
            request = payload.get("request") or {}
            key = (request.get("decision_id"), len(request.get("rejected_attempts") or []) + 1)
            if key in inputs:
                raise ValueError("重复输入: " + str(key))
            inputs[key] = request
        elif row.get("kind") == "decision_planned":
            plan = payload.get("returned_plan") or {}
            if not plan.get("candidates"):
                continue
            key = (plan.get("decision_id"), plan.get("revision"))
            if key in plans:
                raise ValueError("重复计划: " + str(key))
            plans[key] = plan
    if set(inputs) != set(plans):
        raise ValueError("决策输入与计划未完全对齐: inputs=%d plans=%d"
                         % (len(inputs), len(plans)))
    return [(inputs[key], plans[key]) for key in sorted(inputs)]


async def analyze(audit_roots: list[Path]) -> dict:
    """先复算实网策略自证，再让另一策略在同一输入上重排；只统计改选。"""

    r18 = R18IntegratedPositiveV2ReleasePolicy(
        rules_source_hash=R18_INTEGRATED_POSITIVE_V2_RULES_SOURCE_HASH,
        value_analysis_sha256=R18_INTEGRATED_POSITIVE_V2_VALUE_ANALYSIS_SHA256,
    )
    huup = V2HuUpgradePolicy(risk_cells=RISK_CELLS, risk_version=RISK_VERSION,
                             safety_margin=SAFETY_MARGIN)
    result = []
    for audit_root in audit_roots:
        participants = sorted(audit_root.glob("slot-*/runs/*/participants/u_*/decisions.jsonl"))
        participants.extend(sorted(audit_root.glob("runs/*/participants/u_*/decisions.jsonl")))
        manifests = {}
        for path in participants:
            run_dir = path.parents[2]
            if run_dir not in manifests:
                payload = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))["payload"]
                if payload.get("policy_version") == "r18_integrated_positive_v2":
                    release = payload.get("policy_release") or {}
                    if release.get("release_package_id") != R18_INTEGRATED_POSITIVE_V2_RELEASE_PACKAGE_ID:
                        raise ValueError("R18 发布包摘要与当前重放策略不符: " + str(run_dir))
                manifests[run_dir] = payload.get("policy_version")
        arm_results = {}
        for observed_arm in ("r18_integrated_positive_v2", "v2_hu_upgrade_v1"):
            counts = Counter()
            differences = []
            for path in participants:
                if manifests[path.parents[2]] != observed_arm:
                    continue
                for source, recorded in _load_pairs(path):
                    request = decision_request_from_json(source)
                    phase = request.window_key.phase.value
                    now = time.monotonic()
                    budget = DecisionBudget(now + 15, now + 16, now + 17)
                    r18_plan = await r18.choose(request, budget)
                    huup_plan = await huup.choose(request, budget)
                    actual_top = recorded["candidates"][0]["action_key"]
                    replayed = r18_plan if observed_arm == "r18_integrated_positive_v2" else huup_plan
                    if replayed.candidates[0].action_key != actual_top:
                        raise ValueError("实网策略重放首选不符: " + request.decision_id)
                    counts["windows"] += 1
                    counts["phase_" + phase] += 1
                    if len(replayed.candidates) >= 2:
                        counts["comparable_windows"] += 1
                    if any(candidate.action_key == "hu" for candidate in replayed.candidates):
                        counts["legal_hu_windows"] += 1
                    other_top = (huup_plan if observed_arm == "r18_integrated_positive_v2"
                                 else r18_plan).candidates[0].action_key
                    if actual_top == other_top:
                        continue
                    counts["different_top"] += 1
                    counts["different_phase_" + phase] += 1
                    counts["different_" + actual_top.split(":", 1)[0]
                           + "_vs_" + other_top.split(":", 1)[0]] += 1
                    if len(differences) < 24:
                        window = request.window_key
                        differences.append({"game_id": window.game_id, "round_no": window.round_no,
                                            "trigger_seq": window.trigger_seq, "phase": phase,
                                            "r18_top": r18_plan.candidates[0].action_key,
                                            "huup_top": huup_plan.candidates[0].action_key,
                                            "r18_score": r18_plan.candidates[0].total_score,
                                            "huup_score": huup_plan.candidates[0].total_score})
            arm_results[observed_arm] = {"counts": dict(counts),
                                         "difference_examples": differences}
        result.append({"audit_root": str(audit_root.relative_to(ROOT)),
                       "observed_arms": arm_results})
    return {"schema": "r18-vs-huup-same-observation/2", "rooms": result,
            "interpretation": "只定位同一玩家观察的动作差异；改选率不是积分因果效应。"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit-root", type=Path, action="append", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    body = asyncio.run(analyze([path.resolve() for path in args.audit_root]))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(body, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                        encoding="utf-8")
    print(args.out)


if __name__ == "__main__":
    main()
