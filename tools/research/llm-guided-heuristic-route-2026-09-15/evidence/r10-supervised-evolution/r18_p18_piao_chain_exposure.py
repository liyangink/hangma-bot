"""R18 P18：从已证实应飘的可达中局冻结圈内续飘机会。

输入是 P3 的 32 个新形状可达中局。每条轨迹先重放已冻结合法前缀，再强制
一次已由配对反事实证明为正的 ``discard:白``。之后由当前 P5 续打；只读取
焦点依法可见请求，冻结首次“圈主摸牌且 hu/续飘/关圈同时可选”的状态。

本阶段只审计可达性和动作支持，不读取目标状态之后的结算，不调用模型。
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
from dataclasses import asdict
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


OUT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p18-piao-chain-exposure-01-20260922')
P3_BANK = p3.OUT / "bank.json"
P3_RESULT = p3.OUT / "result.json"
PARENT = p16.PARENT
CONTRACT = p16.CONTRACT
LIMITS = p16.LIMITS
MIN_STATES = 24
MIN_SOURCE_CASES = 24
DEVELOPMENT_STATES = 20
SELECTION_SALT = "r18-p18-piao-chain-split-v1"


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


def source_path(case_id: str) -> Path:
    return _project_file(_PROJECT_ROOT, OUT / "sources" / (case_id + ".json"))


def source_rows() -> list[dict[str, Any]]:
    result = json.loads(P3_RESULT.read_text(encoding="utf-8"))
    checks = result.get("checks") or {}
    if not checks or not all(checks.values()):
        raise ValueError("P3 可达中局必须已通过全部冻结检查")
    rows = json.loads(P3_BANK.read_text(encoding="utf-8"))["cases"]
    if len(rows) != 32:
        raise ValueError("P3 可达中局必须恰有32个来源状态")
    return rows


def prepare() -> None:
    """在运行圈内轨迹前冻结来源、阈值和最大桌数。"""

    if OUT.exists():
        raise SystemExit("P18目录已存在；拒绝覆盖")
    sources = [
        {"case_id": row["case_id"], "role": row["role"], "focal_seat": row["focal_seat"]}
        for row in source_rows()
    ]
    OUT.mkdir(parents=True)
    (_project_file(_PROJECT_ROOT, OUT / "sources")).mkdir()
    authorization = batch.unified_document(
        batch_label=OUT.name,
        authorization_id="r18-p18-piao-chain-exposure-01",
        accounts={"tables_full": len(sources)},
        issued_by="lead", issued_at_utc=search.utc_now(), legacy_alias=False,
    )
    authorization.update({
        "issuance_basis": "P17关闭无条件开圈；转向P3已证实为正的飘白后续圈内决策",
        "scope": "32个P3可达中局各重放一条完整手牌；首次圈主摸牌结果盲冻结",
        "max_model_calls": 0,
        "confirmation_roots": 0,
    })
    write_json(_project_file(_PROJECT_ROOT, OUT / "authorization.json"), authorization)
    write_json(_project_file(_PROJECT_ROOT, OUT / "sources.json"), {
        "schema": "r18-p18-piao-chain-sources/1", "sources": sources,
    })
    tracked = [
        Path(__file__), P3_BANK, P3_RESULT, PARENT, CONTRACT,
        Path(p3.__file__), Path(p16.__file__), Path(opportunities.__file__),
        _project_file(_PROJECT_ROOT, OUT / "authorization.json"), _project_file(_PROJECT_ROOT, OUT / "sources.json"),
    ]
    write_json(_project_file(_PROJECT_ROOT, OUT / "manifest.json"), {
        "schema": "r18-p18-piao-chain-manifest/1",
        "created_at_utc": search.utc_now(),
        "runtime": guard.capture(source_paths=tracked),
        "p3_bank_sha256": digest(P3_BANK),
        "p3_result_sha256": digest(P3_RESULT),
        "parent_sha256": digest(PARENT),
        "contract_sha256": digest(CONTRACT),
        "sources": len(sources),
        "planned_tables": len(sources),
        "minimum_states": MIN_STATES,
        "minimum_source_cases": MIN_SOURCE_CASES,
        "development_states_if_open": DEVELOPMENT_STATES,
        "split_rule": "按固定salt+request_sha256排序；前20开发、其余隐藏",
        "target": "首次catch_play活动、焦点为圈主的摸牌窗；hu、discard:白、非白弃牌并存",
        "trajectory": "P3冻结前缀+强制一次已证实应飘的discard:白，随后P5",
        "outcome_blind": True,
        "model_calls": 0,
        "selection_eligible": False,
        "release_eligible": False,
    })
    print(json.dumps({"status": "PREPARED", "sources": len(sources)}, ensure_ascii=False))


def verify() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    manifest = json.loads((_project_file(_PROJECT_ROOT, OUT / "manifest.json")).read_text(encoding="utf-8"))
    checks = {
        "P3题库": (manifest["p3_bank_sha256"], digest(P3_BANK)),
        "P3结果": (manifest["p3_result_sha256"], digest(P3_RESULT)),
        "P5父代": (manifest["parent_sha256"], digest(PARENT)),
        "合同": (manifest["contract_sha256"], digest(CONTRACT)),
    }
    for label, (expected, actual) in checks.items():
        if expected != actual:
            raise ValueError(label + "漂移")
    guard.verify(manifest["runtime"])
    frozen = json.loads((_project_file(_PROJECT_ROOT, OUT / "sources.json")).read_text(encoding="utf-8"))["sources"]
    current = [
        {"case_id": row["case_id"], "role": row["role"], "focal_seat": row["focal_seat"]}
        for row in source_rows()
    ]
    if frozen != current:
        raise ValueError("P18来源不可由P3重建")
    return manifest, frozen


async def execute_source(row: Mapping[str, Any]) -> dict[str, Any]:
    """重放一个 P3 世界，截取首次圈主摸牌多臂机会。"""

    case = next(item for item in source_rows() if item["case_id"] == row["case_id"])
    world_row = case["full_world"]
    engine = SimulationEngine(p3.pilot.RULES, rules_hash=str(world_row["rules_hash"]))
    world = engine.from_replay(world_row)
    policies: list[Any] = [
        ComparableHeuristicPolicyV2(monotonic=lambda: 800.0) for _ in range(4)
    ]
    focal = int(case["focal_seat"])
    policies[focal] = ActionValuePolicy(ActionValueScorer(
        "r18-p18-p5-" + str(case["case_id"]), PARENT.read_text(encoding="utf-8"),
    ))
    wrappers: list[ForceFirstActionPolicy] = []
    for event in case["prefix_events"]:
        seat = int(event["seat"])
        wrapper = ForceFirstActionPolicy(
            policies[seat], target_window=window_key_from_json(event["window_key"]),
            forced_action_key=event["action_key"],
            policy_id="r18-p18-prefix-" + event["label"],
        )
        policies[seat] = wrapper
        wrappers.append(wrapper)
    initial_target = decision_request_from_json(case["request"])
    opening = ForceFirstActionPolicy(
        policies[focal], target_window=initial_target.window_key,
        forced_action_key="discard:白", policy_id="r18-p18-proven-opening",
    )
    policies[focal] = opening
    wrappers.append(opening)
    prefix = []
    active_windows = Counter()
    claim_rows = []
    for _ in range(100_000):
        frame = engine.frame(world)
        if frame.final_scores is not None or frame.blocked_reason is not None:
            return {
                "schema": "r18-p18-piao-chain-source/1",
                "source": dict(row), "status": "complete_without_target",
                "opening_force_count": opening.force_count,
                "all_prefix_forces_once": all(item.force_count == 1 for item in wrappers),
                "active_window_counts": dict(sorted(active_windows.items())),
                "claim_opportunities": claim_rows,
                "target": None,
            }
        prepared: dict[Any, tuple[Any, Any]] = {}
        for decision in frame.decisions:
            analysis = p3.pilot.RULES.analyze(decision.observation, value_limits=LIMITS)
            request = opportunities.real_window_request(
                decision=decision, analysis=analysis,
                match_id=str(world_row["initial"]["world_payload"]["match_id"]),
                config=p3.pilot.driver_config(), now_monotonic=lambda: 800.0,
            )
            prepared[decision.window_key] = (analysis, request)
            context = analyze_catch_play(request.observation)
            if opening.force_count == 1 and context.active:
                owner = context.owner_seat == request.observation.seat and context.issue is None
                active_windows[request.observation.phase + (":owner" if owner else ":nonowner")] += 1
                legal = [item.action_key for item in request.rules.legal_candidates]
                claims = [key for key in legal if key.startswith((
                    "chi:", "peng:", "gang:exposed:", "gang:added:",
                ))]
                if owner and claims and "pass" in legal:
                    claim_rows.append({
                        "window_key": window_key_to_json(request.window_key),
                        "phase": request.observation.phase,
                        "claim_action_keys": claims,
                    })
                white = [key for key in legal if key == "discard:白"]
                nonwhite = [
                    key for key in legal
                    if key.startswith("discard:") and key != "discard:白"
                ]
                if (
                    owner and request.observation.phase == "draw"
                    and "hu" in legal and white and nonwhite
                ):
                    plan = await policies[focal].choose(
                        request, p3.pilot.driver_config().budget_policy.build(
                            800.0, decision.timeout_seconds,
                        ),
                    )
                    if not plan.candidates:
                        raise RuntimeError("P5在圈主目标窗口没有动作")
                    return {
                        "schema": "r18-p18-piao-chain-source/1",
                        "source": dict(row), "status": "hit",
                        "opening_force_count": opening.force_count,
                        "all_prefix_forces_once": all(item.force_count == 1 for item in wrappers),
                        "active_window_counts": dict(sorted(active_windows.items())),
                        "claim_opportunities": claim_rows,
                        "target": {
                            "request": decision_request_to_json(request),
                            "request_sha256": value_digest(decision_request_to_json(request)),
                            "prefix": prefix,
                            "reference_action": plan.candidates[0].action_key,
                            "renew_action": "discard:白",
                            "close_action_candidates": nonwhite,
                            "legal_action_keys": legal,
                            "round_no": request.observation.round_no,
                            "snapshot_seq": request.observation.snapshot_seq,
                            "remaining_tile_count": request.observation.remaining_tile_count,
                            "wealth_count": sum(
                                tile.code == request.observation.rule_state.wealth_god.code
                                for tile in request.observation.my_hand
                            ) + int(
                                request.observation.drawn_tile is not None
                                and request.observation.drawn_tile.code
                                == request.observation.rule_state.wealth_god.code
                            ),
                            "baotou": request.observation.rule_state.baotou,
                            "chain_count": request.observation.rule_state.chain_count,
                            "chain_piao": request.observation.chain_piao,
                            "catch_play_owner_seat": context.owner_seat,
                        },
                    }
        choices = []
        for decision in frame.decisions:
            analysis, request = prepared[decision.window_key]
            plan = await policies[int(decision.window_key.seat)].choose(
                request, p3.pilot.driver_config().budget_policy.build(
                    800.0, decision.timeout_seconds,
                ),
            )
            if not plan.candidates:
                raise RuntimeError("P18前缀策略没有动作")
            action = plan.candidates[0].action
            key = action_key(action)
            if not any(item.action_key == key for item in analysis.legal_candidates):
                raise RuntimeError("P18前缀策略返回非法动作：" + key)
            choices.append(SimulationChoice(decision.window_key, action))
        world = engine.advance(world, frame.revision, tuple(choices))
        prefix.extend({
            "window_key": window_key_to_json(choice.window_key),
            "action_key": action_key(choice.action),
        } for choice in choices)
    raise RuntimeError("P18轨迹超过步数上限")


def run() -> None:
    manifest, frozen = verify()
    authorization = json.loads((_project_file(_PROJECT_ROOT, OUT / "authorization.json")).read_text(encoding="utf-8"))
    natural.require_authorization(authorization)
    ledger = search.ActionValueLedger.load(
        _project_file(_PROJECT_ROOT, OUT / "ledger.json"),
        authorized_budgets=search.av_ledger_budgets_from_authorization(authorization),
    )
    pending = [row for row in frozen if not source_path(str(row["case_id"])).exists()]
    reservation = ledger.reserve(
        step_id="r18:p18-piao-chain-exposure", account="tables_full",
        amount=len(pending), note="32个已证实应飘可达中局的圈内机会暴露",
    )
    completed = 0
    failures = []
    try:
        for row in pending:
            try:
                result = asyncio.run(execute_source(row))
                if result["opening_force_count"] != 1 or not result["all_prefix_forces_once"]:
                    raise RuntimeError("P3前缀或已证实飘白未恰好强制一次")
                write_json(source_path(str(row["case_id"])), result)
                completed += 1
            except Exception as exc:  # noqa: BLE001
                failures.append({
                    "case_id": row["case_id"],
                    "error": type(exc).__name__ + ": " + str(exc),
                })
    finally:
        ledger.settle(reservation, actual=completed, note="按完成的完整手牌轨迹计")
    write_json(_project_file(_PROJECT_ROOT, OUT / "run-summary.json"), {
        "schema": "r18-p18-run-summary/1", "completed": completed,
        "planned": manifest["planned_tables"], "failures": failures,
        "spent": ledger.account_summary(),
    })
    if failures or completed != manifest["planned_tables"]:
        raise RuntimeError("P18圈内暴露执行不完整")
    print(json.dumps({"status": "RUN_COMPLETE", "sources": completed}, ensure_ascii=False))


def analyze() -> None:
    manifest, frozen = verify()
    summary = json.loads((_project_file(_PROJECT_ROOT, OUT / "run-summary.json")).read_text(encoding="utf-8"))
    if summary["failures"] or summary["completed"] != manifest["planned_tables"]:
        raise ValueError("P18执行不完整")
    hits = []
    status_counts = Counter()
    claims = []
    for source in frozen:
        document = json.loads(source_path(str(source["case_id"])).read_text(encoding="utf-8"))
        status_counts[document["status"]] += 1
        claims.extend({"case_id": source["case_id"], **row} for row in document["claim_opportunities"])
        if document["target"] is not None:
            hits.append({"source": document["source"], **document["target"]})
    ordered = sorted(
        hits,
        key=lambda row: hashlib.sha256(
            (SELECTION_SALT + "|" + row["request_sha256"]).encode("utf-8")
        ).hexdigest(),
    )
    development = ordered[:DEVELOPMENT_STATES]
    hidden = ordered[DEVELOPMENT_STATES:]
    opened = len(hits) >= MIN_STATES and len({row["source"]["case_id"] for row in hits}) >= MIN_SOURCE_CASES
    write_json(_project_file(_PROJECT_ROOT, OUT / "targets.json"), {
        "schema": "r18-p18-piao-chain-targets/1",
        "selection_salt": SELECTION_SALT,
        "development": development,
        "hidden": hidden,
        "hidden_labels_opened": False,
    })
    result = {
        "schema": "r18-p18-piao-chain-result/1",
        "status": "COMPLETE_P18_PIAO_CHAIN_EXPOSURE",
        "sources": len(frozen),
        "status_counts": dict(sorted(status_counts.items())),
        "eligible_owner_draw_states": len(hits),
        "independent_source_cases": len({row["source"]["case_id"] for row in hits}),
        "reference_action_frequencies": dict(sorted(Counter(
            row["reference_action"] for row in hits
        ).items())),
        "wealth_count_frequencies": dict(sorted(Counter(
            str(row["wealth_count"]) for row in hits
        ).items())),
        "chain_piao_frequencies": dict(sorted(Counter(
            str(row["chain_piao"]) for row in hits
        ).items())),
        "owner_claim_opportunities": len(claims),
        "owner_claim_rows": claims,
        "passes_exposure_gate": opened,
        "development_states": len(development),
        "hidden_states": len(hidden),
        "next": (
            "对开发状态运行hu/P5参考动作与discard:白续飘的共同隐藏世界教师；隐藏标签继续封存"
            if opened else "关闭续飘作者路线；不得用合成状态补足自然可达门"
        ),
        "hidden_labels_opened": False,
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
