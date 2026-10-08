"""R18 ``seven_pairs_closed`` 首尺：自然桌中的七对无损支配机会。

轨迹由稳定 V2 产生，冻结 P5 仅在赛后复算相同公开请求。本探针只识别一个
窄判据：纯弃牌窗口中，两个动作的 P5 分数、普通型向听和普通型有效牌完全
相同，而其中一个动作的七对向听更低，或同向听下七对有效牌逐项不差且至少
一项更好。该判据只证明“现有牌效目标不退化且七对一步事实更优”，不把它
冒充完整牌局期望或发布强度。
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
from collections import Counter
import concurrent.futures
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
import sitin_natural_panel as natural  # noqa: E402
import sitin_search as search  # noqa: E402
import strong_seed_batch as batch  # noqa: E402
from hangma_bot.hangma.interface import (  # noqa: E402
    CandidateFactKind,
    RuleCompleteness,
    ValueAnalysisLimits,
)
from hangma_bot.kernel.serialization import window_key_to_json  # noqa: E402
from hangma_bot.policy.action_value_policy import build_scoring_view  # noqa: E402
from hangma_bot.policy.action_value_seeds import ActionValueScorer  # noqa: E402


OUT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-seven-pairs-natural-probe-01-20260922')
CONTRACT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/contracts/group-dev-v1.json')
PARENT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p5-gang-dominance-01-20260922/generation/candidate.py')
PANEL_SEED = 2026100823
MIXES = ("H", "M")
ROOTS = tuple(range(1, 33))
SEATS = (0, 1, 2, 3)
TABLES_PER_SOURCE = 2
PLANNED_TABLES = len(MIXES) * len(ROOTS) * len(SEATS) * TABLES_PER_SOURCE
LIMITS = ValueAnalysisLimits(max_expansions=20_000, max_routes_per_candidate=256)


def digest(path: Path) -> str:
    """返回文件 SHA-256。"""

    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: Any) -> None:
    """写入稳定 JSON。"""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def sources() -> list[dict[str, Any]]:
    """列出全新自然来源。"""

    return [
        {
            "panel_seed": PANEL_SEED,
            "mix": mix,
            "root_index": root,
            "focal_seat": seat,
            "source_id": f"s{PANEL_SEED}:{mix}:r{root:02d}:s{seat}",
            "source_root_id": natural.natural_root_id(mix, PANEL_SEED, root),
        }
        for mix in MIXES for root in ROOTS for seat in SEATS
    ]


def source_path(row: Mapping[str, Any]) -> Path:
    """返回一个来源的断点文件。"""

    return _project_file(_PROJECT_ROOT, OUT / "sources" / (str(row["source_id"]).replace(":", "-") + ".json"))


def source_paths() -> list[Path]:
    """列出会改变执行或判据语义的输入。"""

    return [Path(__file__), CONTRACT, PARENT, Path(natural.__file__)]


def prepare() -> None:
    """在观察结果前冻结样本、判据和后续分流门槛。"""

    if OUT.exists():
        raise SystemExit("七对自然探针目录已存在；拒绝覆盖")
    OUT.mkdir(parents=True)
    authorization = batch.unified_document(
        batch_label=OUT.name,
        authorization_id="r18-seven-pairs-natural-probe-01",
        accounts={"tables_full": PLANNED_TABLES},
        issued_by="lead",
        issued_at_utc=search.utc_now(),
        legacy_alias=False,
    )
    authorization.update({
        "issuance_basis": "P5补杠后继通过；转入seven_pairs_closed并先测自然无损支配机会",
        "scope": "全新H/M各32根、四焦点座、每来源2桌；稳定V2轨迹，P5仅赛后复算",
        "max_model_calls": 0,
        "confirmation_roots": 0,
    })
    write_json(_project_file(_PROJECT_ROOT, OUT / "authorization.json"), authorization)
    write_json(_project_file(_PROJECT_ROOT, OUT / "manifest.json"), {
        "schema": "r18-seven-pairs-natural-probe-manifest/1",
        "created_at_utc": search.utc_now(),
        "runtime": guard.capture(source_paths=source_paths() + [_project_file(_PROJECT_ROOT, OUT / "authorization.json")]),
        "contract_sha256": digest(CONTRACT),
        "parent_sha256": digest(PARENT),
        "panel_seed": PANEL_SEED,
        "mixes": list(MIXES),
        "root_indices": list(ROOTS),
        "focal_seats": list(SEATS),
        "sources": len(sources()),
        "tables_per_source": TABLES_PER_SOURCE,
        "planned_tables": PLANNED_TABLES,
        "workers": 8,
        "trajectory_policy": "stable weighted_heuristic_v2",
        "candidate_use": "frozen P5 postgame request replay only",
        "frozen_public_predicate": {
            "window": "all legal actions are discard; own meld count is zero",
            "facts": "complete hand_progress; standard and seven-pairs shanten/useful tiles all known",
            "parent_parity": "P5 action scores exactly equal",
            "standard_parity": "standard shanten and per-code remaining estimates exactly equal",
            "seven_pairs_dominance": (
                "lower seven-pairs shanten, or equal shanten with per-code remaining "
                "estimates weakly greater and at least one strictly greater"
            ),
            "unknown_or_missing": "exclude from strict predicate and count separately",
        },
        "decision_gate": {
            "open_mechanical_candidate_min_distinct_roots": 8,
            "open_mechanical_candidate_required_mixes": list(MIXES),
            "otherwise": "build reachable paired counterfactual before authoring",
        },
        "oracle_warning": "只证明P5与普通型一步事实不退化；不等于完整牌局Q值",
        "selection_eligible": False,
        "release_eligible": False,
    })
    print(json.dumps({"status": "PREPARED", "tables": PLANNED_TABLES}, ensure_ascii=False))


def verify_manifest() -> dict[str, Any]:
    """拒绝合同、父代、判据或执行环境漂移。"""

    manifest = json.loads((_project_file(_PROJECT_ROOT, OUT / "manifest.json")).read_text(encoding="utf-8"))
    if manifest["contract_sha256"] != digest(CONTRACT):
        raise ValueError("合同漂移")
    if manifest["parent_sha256"] != digest(PARENT):
        raise ValueError("P5 身份漂移")
    guard.verify(manifest["runtime"])
    return manifest


def _useful_map(value: Any) -> tuple[tuple[str, int], ...] | None:
    """把规则有效牌事实变成稳定映射；未知返回空值。"""

    if value is None:
        return None
    return tuple(sorted((item.code, int(item.remaining_estimate)) for item in value))


def _complete_discard(candidate: Any) -> dict[str, Any] | None:
    """返回可参与严格比较的弃牌事实。"""

    facts = candidate.facts
    if not candidate.action_key.startswith("discard:") or facts is None:
        return None
    if (
        facts.fact_kind is not CandidateFactKind.HAND_PROGRESS
        or facts.completeness is not RuleCompleteness.COMPLETE
        or facts.standard_shanten_after is None
        or facts.seven_pairs_shanten_after is None
        or facts.standard_useful_tiles is None
        or facts.seven_pairs_useful_tiles is None
        or facts.pattern_progress_note is not None
    ):
        return None
    return {
        "action_key": candidate.action_key,
        "standard_shanten": int(facts.standard_shanten_after),
        "seven_pairs_shanten": int(facts.seven_pairs_shanten_after),
        "standard_useful": _useful_map(facts.standard_useful_tiles),
        "seven_pairs_useful": _useful_map(facts.seven_pairs_useful_tiles),
    }


def _map_dominates(left: tuple[tuple[str, int], ...], right: tuple[tuple[str, int], ...]) -> bool:
    """左侧逐牌公开容量不差且至少一项更好。"""

    left_map = dict(left)
    right_map = dict(right)
    codes = set(left_map) | set(right_map)
    return all(left_map.get(code, 0) >= right_map.get(code, 0) for code in codes) and any(
        left_map.get(code, 0) > right_map.get(code, 0) for code in codes
    )


def _seven_dominates(left: Mapping[str, Any], right: Mapping[str, Any]) -> bool:
    """按冻结判据判断左动作的七对一步事实是否严格支配右动作。"""

    if left["seven_pairs_shanten"] < right["seven_pairs_shanten"]:
        return True
    if left["seven_pairs_shanten"] != right["seven_pairs_shanten"]:
        return False
    return _map_dominates(left["seven_pairs_useful"], right["seven_pairs_useful"])


def _top_key(batch_result: Any) -> str:
    """按合同排序规则返回 P5 首选动作。"""

    return sorted(batch_result.entries, key=lambda item: (-item.score, item.action_key))[0].action_key


def audit_requests(requests: list[Any], source: Mapping[str, Any]) -> dict[str, Any]:
    """测量七对自然暴露、P5选择和严格无损支配机会。"""

    scorer = ActionValueScorer("r18-seven-pairs-probe-p5", PARENT.read_text(encoding="utf-8"))
    counts: Counter[str] = Counter()
    windows = []
    problems = []
    for request in requests:
        counts["focal_requests"] += 1
        observation = request.observation
        legal = list(request.rules.legal_candidates)
        if any(item.action_key.startswith("discard:") for item in legal):
            counts["windows_with_discard"] += 1
        if len(observation.melds[observation.seat]) > 0:
            closed_values = [
                item.facts.seven_pairs_shanten_after
                for item in legal
                if item.action_key.startswith("discard:") and item.facts is not None
            ]
            if closed_values:
                counts["exposed_discard_windows"] += 1
                if all(value is None for value in closed_values):
                    counts["exposed_path_closed_windows"] += 1
            continue
        if len(legal) < 2 or any(not item.action_key.startswith("discard:") for item in legal):
            continue
        counts["closed_discard_only_windows"] += 1
        facts = [_complete_discard(item) for item in legal]
        if any(item is None for item in facts):
            counts["closed_incomplete_windows"] += 1
            continue
        rows = [item for item in facts if item is not None]
        counts["closed_complete_windows"] += 1
        try:
            batch_result = scorer.score(build_scoring_view(request))
        except Exception as exc:  # noqa: BLE001 - 失败必须留下证据
            counts["parent_scoring_failures"] += 1
            problems.append(type(exc).__name__ + ": " + str(exc)[:240])
            continue
        scores = {item.action_key: float(item.score) for item in batch_result.entries}
        parent_top = _top_key(batch_result)
        by_key = {item["action_key"]: item for item in rows}
        if parent_top not in by_key:
            counts["parent_non_discard_top"] += 1
            continue
        dominators = []
        for left in rows:
            right = by_key[parent_top]
            same_parent = scores.get(left["action_key"]) == scores.get(parent_top)
            same_standard = (
                left["standard_shanten"] == right["standard_shanten"]
                and left["standard_useful"] == right["standard_useful"]
            )
            if same_parent and same_standard and _seven_dominates(left, right):
                dominators.append(left)
        seven_best = min(item["seven_pairs_shanten"] for item in rows)
        standard_best = min(item["standard_shanten"] for item in rows)
        if by_key[parent_top]["seven_pairs_shanten"] == seven_best:
            counts["parent_min_seven_shanten"] += 1
        if by_key[parent_top]["standard_shanten"] == standard_best:
            counts["parent_min_standard_shanten"] += 1
        if any(item["seven_pairs_shanten"] < item["standard_shanten"] for item in rows):
            counts["seven_route_closer_windows"] += 1
        if any(item["standard_shanten"] < item["seven_pairs_shanten"] for item in rows):
            counts["standard_route_closer_windows"] += 1
        if not dominators:
            continue
        chosen = sorted(
            dominators,
            key=lambda item: (
                item["seven_pairs_shanten"],
                -sum(value for _, value in item["seven_pairs_useful"]),
                item["action_key"],
            ),
        )[0]
        counts["strict_dominance_windows"] += 1
        if chosen["seven_pairs_shanten"] < by_key[parent_top]["seven_pairs_shanten"]:
            counts["strict_lower_shanten_windows"] += 1
        else:
            counts["strict_useful_dominance_windows"] += 1
        windows.append({
            "source": dict(source),
            "game_id": observation.game_id,
            "round_no": observation.round_no,
            "seat": observation.seat,
            "snapshot_seq": observation.snapshot_seq,
            "window_key": window_key_to_json(request.window_key),
            "remaining_tile_count": observation.remaining_tile_count,
            "wealth_god": observation.rule_state.wealth_god.code,
            "wealth_count": sum(
                1 for tile in observation.my_hand
                if tile.code == observation.rule_state.wealth_god.code
            ),
            "parent_action": parent_top,
            "dominant_action": chosen["action_key"],
            "parent_score": scores[parent_top],
            "dominant_score": scores[chosen["action_key"]],
            "parent_facts": by_key[parent_top],
            "dominant_facts": chosen,
        })
    return {
        "counts": dict(sorted(counts.items())),
        "windows": windows,
        "problems": problems,
        "max_parent_operations": scorer.last_operation_count,
    }


def execute_source(source: Mapping[str, Any]) -> dict[str, Any]:
    """跑一个来源的两桌稳定 V2 阶段并审计焦点请求。"""

    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    plans = natural.build_seat_stage_plans(
        contract=contract,
        opponent=str(source["mix"]),
        root_index=int(source["root_index"]),
        focal_seat=int(source["focal_seat"]),
        panel_seed=PANEL_SEED,
    )
    requests: list[Any] = []
    scorer = ActionValueScorer("r18-seven-pairs-probe-unused", PARENT.read_text(encoding="utf-8"))
    stage = natural.run_arm_stage(
        arm="baseline",
        plans=plans,
        candidate_scorer=scorer,
        opponent_policies=contract["panel"]["opponent_scenarios"][str(source["mix"])]["opponent_policies"],
        versions_block=natural.stage.contract_versions_block(contract),
        step_limit=int(contract["stop"]["step_limit"]),
        value_limits=LIMITS,
        decision_observer=requests.append,
    )
    completed_hands = sum(
        int(table.get("result", {}).get("completed_hands") or 0)
        for table in stage.get("tables") or []
    )
    runtime: Counter[str] = Counter()
    for table in stage.get("tables") or []:
        runtime.update(table.get("result", {}).get("runtime_counts") or {})
    return {
        "source": dict(source),
        "status": stage.get("status"),
        "error": stage.get("error"),
        "tables": len(stage.get("tables") or []),
        "completed_hands": completed_hands,
        "runtime_counts": dict(sorted(runtime.items())),
        "audit": audit_requests(requests, source),
    }


def run() -> None:
    """并行执行冻结来源，按来源断点续跑。"""

    manifest = verify_manifest()
    authorization = json.loads((_project_file(_PROJECT_ROOT, OUT / "authorization.json")).read_text(encoding="utf-8"))
    natural.require_authorization(authorization)
    ledger = search.ActionValueLedger.load(
        _project_file(_PROJECT_ROOT, OUT / "ledger.json"),
        authorized_budgets=search.av_ledger_budgets_from_authorization(authorization),
    )
    pending = []
    completed_tables = 0
    for row in sources():
        path = source_path(row)
        if path.exists():
            saved = json.loads(path.read_text(encoding="utf-8"))
            if saved.get("status") != "complete" or saved.get("tables") != TABLES_PER_SOURCE:
                raise ValueError("既有来源不完整：" + str(path))
            completed_tables += TABLES_PER_SOURCE
        else:
            pending.append(row)
    reservation = ledger.reserve(
        step_id="r18:seven-pairs-natural-probe",
        account="tables_full",
        amount=PLANNED_TABLES - completed_tables,
        note="稳定V2自然七对无损支配探针",
    )
    failures = []
    executed = 0
    usage_unknown = False
    try:
        with concurrent.futures.ProcessPoolExecutor(max_workers=int(manifest["workers"])) as pool:
            futures = {pool.submit(execute_source, row): row for row in pending}
            for future in concurrent.futures.as_completed(futures):
                row = futures[future]
                result = None
                try:
                    result = future.result()
                    if result["status"] != "complete" or result["tables"] != TABLES_PER_SOURCE:
                        raise RuntimeError(result.get("error") or "来源未跑满")
                    if result["audit"]["problems"]:
                        raise RuntimeError("七对窗口审计出现问题")
                    write_json(source_path(row), result)
                    executed += TABLES_PER_SOURCE
                    completed_tables += TABLES_PER_SOURCE
                    if completed_tables % 64 == 0 or completed_tables == PLANNED_TABLES:
                        print(json.dumps({
                            "completed_tables": completed_tables,
                            "planned_tables": PLANNED_TABLES,
                        }, ensure_ascii=False), flush=True)
                except Exception as exc:  # noqa: BLE001 - 保守保留失败来源
                    if result is None:
                        usage_unknown = True
                    failures.append({
                        "source_id": row["source_id"],
                        "error": type(exc).__name__ + ": " + str(exc),
                    })
    finally:
        if usage_unknown:
            ledger.settle(reservation, usage_unknown=True, note="子进程未返回；保守结算")
        else:
            ledger.settle(reservation, actual=executed, note="按完整返回桌数结算")
    files = list((_project_file(_PROJECT_ROOT, OUT / "sources")).glob("*.json")) if (_project_file(_PROJECT_ROOT, OUT / "sources")).exists() else []
    actual = sum(json.loads(path.read_text(encoding="utf-8"))["tables"] for path in files)
    write_json(_project_file(_PROJECT_ROOT, OUT / "run-summary.json"), {
        "schema": "r18-seven-pairs-natural-probe-run/1",
        "source_files": len(files),
        "actual_tables": actual,
        "failures": failures,
        "spent": ledger.account_summary(),
    })
    if failures or actual != PLANNED_TABLES or len(files) != len(sources()):
        raise RuntimeError("七对自然探针执行不完整")
    print(json.dumps({"status": "RUN_COMPLETE", "tables": actual}, ensure_ascii=False))


def analyze() -> None:
    """聚合自然暴露并按预冻结门槛决定下一步。"""

    manifest = verify_manifest()
    run_summary = json.loads((_project_file(_PROJECT_ROOT, OUT / "run-summary.json")).read_text(encoding="utf-8"))
    if run_summary["failures"] or run_summary["actual_tables"] != PLANNED_TABLES:
        raise ValueError("七对自然探针运行不完整")
    counts: Counter[str] = Counter()
    runtime: Counter[str] = Counter()
    windows = []
    completed_hands = 0
    for source in sources():
        document = json.loads(source_path(source).read_text(encoding="utf-8"))
        completed_hands += int(document["completed_hands"])
        counts.update(document["audit"]["counts"])
        runtime.update(document["runtime_counts"])
        windows.extend(document["audit"]["windows"])
    roots = {row["source"]["source_root_id"] for row in windows}
    mixes = {row["source"]["mix"] for row in windows}
    gate = manifest["decision_gate"]
    gate_checks = {
        "distinct_roots_min": len(roots) >= int(gate["open_mechanical_candidate_min_distinct_roots"]),
        "required_mixes": mixes == set(gate["open_mechanical_candidate_required_mixes"]),
        "execution_failures_zero": not run_summary["failures"],
    }
    decision = (
        "OPEN_MECHANICAL_SEVEN_PAIRS_CANDIDATE"
        if all(gate_checks.values())
        else "BUILD_REACHABLE_PAIRED_COUNTERFACTUAL_BEFORE_AUTHORING"
    )
    result = {
        "schema": "r18-seven-pairs-natural-probe-result/1",
        "status": "COMPLETE_SEVEN_PAIRS_NATURAL_PROBE",
        "tables": PLANNED_TABLES,
        "completed_hands": completed_hands,
        "counts": dict(sorted(counts.items())),
        "strict_evidence": {
            "windows": len(windows),
            "distinct_tables": len({row["game_id"] for row in windows}),
            "distinct_source_roots": len(roots),
            "mixes": sorted(mixes),
        },
        "gate_checks": gate_checks,
        "decision": decision,
        "runtime_counts": dict(sorted(runtime.items())),
        "windows": windows,
        "interpretation": (
            "严格窗口只证明P5评分与普通型一步事实持平时七对一步事实可改善；"
            "尚未证明完整牌局收益、完整桌赛非劣或发布资格。"
        ),
        "selection_eligible": False,
        "release_eligible": False,
    }
    write_json(_project_file(_PROJECT_ROOT, OUT / "result.json"), result)
    print(json.dumps({
        "status": result["status"],
        "tables": result["tables"],
        "completed_hands": result["completed_hands"],
        "counts": result["counts"],
        "strict_evidence": result["strict_evidence"],
        "gate_checks": result["gate_checks"],
        "decision": result["decision"],
    }, ensure_ascii=False, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("prepare", "run", "analyze"))
    args = parser.parse_args()
    if args.command == "prepare":
        prepare()
    elif args.command == "run":
        run()
    else:
        analyze()


if __name__ == "__main__":
    main()
