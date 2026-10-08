"""R18 P20：稳定 P5 全新完整桌中的杠/非杠成对自然暴露审计。

本阶段只读取依法可见的 ``DecisionRequest`` 与冻结 P5 的动作评分，在运行前
冻结 512 张表和六个互斥分层。每个来源根、每个分层最多保留一个状态，避免
同一牌山的四个换座来源冒充独立样本。P5 已证明的补杠严格支配窗口只作正控，
不进入后续非支配规律发现；本阶段不读取候选效果，也不调用作者模型。
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
from collections import Counter, defaultdict
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
import r18_p9_midgame_hidden_world_teacher as p9  # noqa: E402
import sitin_natural_panel as natural  # noqa: E402
import sitin_search as search  # noqa: E402
import strong_seed_batch as batch  # noqa: E402
from hangma_bot.application.audit_codec import decision_request_to_json  # noqa: E402
from hangma_bot.hangma.interface import ValueAnalysisLimits  # noqa: E402
from hangma_bot.policy.action_value_policy import build_scoring_view  # noqa: E402
from hangma_bot.policy.action_value_seeds import ActionValueScorer  # noqa: E402


OUT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p20-gang-pair-natural-exposure-01-20260922')
CONTRACT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/contracts/group-dev-v1.json')
AV_CONTRACT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/contracts/action-value-v1.json')
PUBLIC_INTERFACE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/contracts/action-value-public-interface-v1.json')
PARENT = p9.P5
PANEL_SEED = 2026102203
MIXES = ("H", "M")
ROOTS = tuple(range(1, 33))
SEATS = (0, 1, 2, 3)
TABLES_PER_SOURCE = 2
PLANNED_TABLES = len(MIXES) * len(ROOTS) * len(SEATS) * TABLES_PER_SOURCE
WORKERS = 8
LIMITS = ValueAnalysisLimits(max_expansions=20_000, max_routes_per_candidate=256)
FAMILIES = tuple(
    f"{kind}.{direction}"
    for kind in ("concealed", "exposed", "added")
    for direction in ("gang_to_nongang", "nongang_to_gang")
)
MIN_STATES = 24
MIN_SOURCE_ROOTS = 4


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def value_digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")).hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def sources() -> list[dict[str, Any]]:
    return [
        {
            "mix": mix,
            "root_index": root,
            "focal_seat": seat,
            "source_root_id": f"{mix}:r{root:02d}",
            "source_id": f"{mix}:r{root:02d}:s{seat}",
        }
        for mix in MIXES for root in ROOTS for seat in SEATS
    ]


def source_path(row: Mapping[str, Any]) -> Path:
    return _project_file(_PROJECT_ROOT, OUT / "sources" / (str(row["source_id"]).replace(":", "-") + ".json"))


def _gang_kind(key: str) -> str:
    """从正式动作键读取杠类型；未知键立即失败，不把它归入其他层。"""

    pieces = key.split(":")
    if len(pieces) != 3 or pieces[0] != "gang" or pieces[1] not in {
        "concealed", "exposed", "added",
    }:
        raise ValueError("未知杠动作键：" + key)
    return pieces[1]


def _strict_dominance_triggered(trace: Mapping[str, Any]) -> bool:
    """识别 P5 已冻结的补杠严格支配覆盖，供正控与发现样本分流。"""

    overlay = trace.get("r18_gang_dominance_overlay")
    return isinstance(overlay, Mapping) and overlay.get("triggered") is True


def _candidate_row(
    request: Any,
    source: Mapping[str, Any],
    scorer: ActionValueScorer,
) -> tuple[dict[str, Any] | None, str | None]:
    observation = request.observation
    legal_keys = tuple(item.action_key for item in request.rules.legal_candidates)
    gang_keys = tuple(key for key in legal_keys if key.startswith("gang:"))
    nongang_keys = tuple(key for key in legal_keys if not key.startswith("gang:"))
    if not gang_keys or not nongang_keys:
        return None, None

    batch_result = scorer.score(build_scoring_view(request))
    if batch_result.status != "SCORED":
        return None, "P5_" + batch_result.status + ":" + str(batch_result.reason)
    entries = sorted(batch_result.entries, key=lambda item: (-item.score, item.action_key))
    if not entries:
        return None, "P5_EMPTY_ENTRIES"
    gang_entries = [entry for entry in entries if entry.action_key.startswith("gang:")]
    nongang_entries = [entry for entry in entries if not entry.action_key.startswith("gang:")]
    if not gang_entries or not nongang_entries:
        return None, "P5_SCORE_ACTION_PARTITION_MISMATCH"
    parent = entries[0]
    if parent.action_key.startswith("gang:"):
        paired = nongang_entries[0]
        direction = "gang_to_nongang"
        gang_key = parent.action_key
    else:
        paired = gang_entries[0]
        direction = "nongang_to_gang"
        gang_key = paired.action_key
    family = _gang_kind(gang_key) + "." + direction
    if family not in FAMILIES:
        return None, "UNKNOWN_FAMILY:" + family
    request_json = decision_request_to_json(request)
    wealth = observation.rule_state.wealth_god.code
    hand = [tile.code for tile in observation.my_hand]
    if observation.drawn_tile is not None and len(hand) != observation.hand_counts[observation.seat]:
        hand.append(observation.drawn_tile.code)
    positive_control = _strict_dominance_triggered(parent.trace)
    return {
        "schema": "r18-p20-gang-pair-natural-row/1",
        "family": family,
        "source": dict(source),
        "request_sha256": value_digest(request_json),
        "request": request_json,
        "game_id": observation.game_id,
        "round_no": observation.round_no,
        "snapshot_seq": observation.snapshot_seq,
        "phase": observation.phase,
        "seat": observation.seat,
        "dealer_seat": observation.dealer_seat,
        "remaining_tile_count": observation.remaining_tile_count,
        "wealth_count": hand.count(wealth),
        "baotou": observation.rule_state.baotou,
        "chain_count": observation.rule_state.chain_count,
        "chain_piao": observation.chain_piao,
        "legal_action_keys": list(legal_keys),
        "gang_action_keys": list(gang_keys),
        "nongang_action_keys": list(nongang_keys),
        "reference_action_key": parent.action_key,
        "reference_score": parent.score,
        "intervention_action_key": paired.action_key,
        "intervention_score": paired.score,
        "p5_score_margin": parent.score - paired.score,
        "gang_kind": _gang_kind(gang_key),
        "strict_dominance_positive_control": positive_control,
        "sample_role": "positive_control" if positive_control else "discovery",
        "reference_trace": parent.trace,
        "intervention_trace": paired.trace,
        "p5_status": "SCORED",
    }, None


def audit_requests(
    requests: list[Any], source: Mapping[str, Any], parent_source: str,
) -> dict[str, Any]:
    scorer = ActionValueScorer("r18-p20-p5-" + str(source["source_id"]), parent_source)
    counts: Counter[str] = Counter()
    rows_by_family: dict[str, list[dict[str, Any]]] = defaultdict(list)
    problems = []
    for request in requests:
        counts["focal_requests"] += 1
        row, problem = _candidate_row(request, source, scorer)
        if problem is not None:
            problems.append(problem)
        if row is not None:
            counts[row["family"]] += 1
            counts["strict_dominance_positive_controls"] += int(
                row["strict_dominance_positive_control"]
            )
            rows_by_family[row["family"]].append(row)
    rows = []
    for family in FAMILIES:
        for role in ("discovery", "positive_control"):
            options = sorted(
                (
                    item for item in rows_by_family[family]
                    if item["sample_role"] == role
                ),
                key=lambda item: (
                    int(item["round_no"]), int(item["snapshot_seq"]),
                    str(item["request_sha256"]),
                ),
            )
            if options:
                rows.append(options[0])
    return {"counts": dict(sorted(counts.items())), "eligible_rows": rows,
            "problems": problems}


def execute_source(source_row: Mapping[str, Any]) -> dict[str, Any]:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    parent_source = PARENT.read_text(encoding="utf-8")
    plans = natural.build_seat_stage_plans(
        contract=contract,
        opponent=str(source_row["mix"]),
        root_index=int(source_row["root_index"]),
        focal_seat=int(source_row["focal_seat"]),
        panel_seed=PANEL_SEED,
    )
    requests: list[Any] = []
    stage = natural.run_arm_stage(
        arm="p20-p5-gang-pair-natural",
        plans=plans,
        candidate_scorer=ActionValueScorer(
            "r18-p20-trajectory-" + str(source_row["source_id"]), parent_source,
        ),
        opponent_policies=contract["panel"]["opponent_scenarios"][
            str(source_row["mix"])
        ]["opponent_policies"],
        versions_block=natural.stage.contract_versions_block(contract),
        step_limit=int(contract["stop"]["step_limit"]),
        value_limits=LIMITS,
        decision_observer=requests.append,
    )
    return {
        "source": dict(source_row),
        "status": stage.get("status"),
        "error": stage.get("error"),
        "tables": len(stage.get("tables") or []),
        "audit": audit_requests(requests, source_row, parent_source),
    }


def prepare() -> None:
    """在查看杠窗口前冻结来源、分层、独立单位、阈值和最大表数。"""

    if OUT.exists():
        raise SystemExit("P20 目录已存在；拒绝覆盖")
    OUT.mkdir(parents=True)
    authorization = batch.unified_document(
        batch_label=OUT.name,
        authorization_id="r18-p20-gang-pair-natural-exposure-01",
        accounts={"tables_full": PLANNED_TABLES},
        issued_by="lead",
        issued_at_utc=search.utc_now(),
        legacy_alias=False,
    )
    authorization.update({
        "issuance_basis": "机会优先新目标；在当前P5轨迹上冻结非支配杠/非杠配对",
        "scope": "全新H/M各32根、四焦点座、每来源2桌；稳定P5结果盲采集；来源根独立",
        "max_model_calls": 0,
        "confirmation_roots": 0,
    })
    write_json(_project_file(_PROJECT_ROOT, OUT / "authorization.json"), authorization)
    frozen_sources = sources()
    write_json(_project_file(_PROJECT_ROOT, OUT / "sources.json"), {
        "schema": "r18-p20-gang-pair-sources/1", "sources": frozen_sources,
    })
    tracked = [
        Path(__file__), CONTRACT, AV_CONTRACT, PUBLIC_INTERFACE, PARENT,
        Path(natural.__file__), _project_file(_PROJECT_ROOT, OUT / "authorization.json"), _project_file(_PROJECT_ROOT, OUT / "sources.json"),
    ]
    write_json(_project_file(_PROJECT_ROOT, OUT / "manifest.json"), {
        "schema": "r18-p20-gang-pair-natural-manifest/1",
        "created_at_utc": search.utc_now(),
        "runtime": guard.capture(source_paths=tracked),
        "contract_sha256": digest(CONTRACT),
        "action_value_contract_sha256": digest(AV_CONTRACT),
        "public_interface_sha256": digest(PUBLIC_INTERFACE),
        "parent_sha256": digest(PARENT),
        "scoring_view_schema": "sitin-scoring-view/4",
        "panel_seed": PANEL_SEED,
        "mixes": list(MIXES),
        "root_indices": list(ROOTS),
        "focal_seats": list(SEATS),
        "sources": len(frozen_sources),
        "tables_per_source": TABLES_PER_SOURCE,
        "planned_tables": PLANNED_TABLES,
        "workers": WORKERS,
        "families": list(FAMILIES),
        "minimum_states_per_family": MIN_STATES,
        "minimum_source_roots_per_family": MIN_SOURCE_ROOTS,
        "freeze_rule": "每来源单元先取每层第一条；每来源根四个焦点座再按(round_no,snapshot_seq,request_sha256)取一条；全局请求摘要去重",
        "trajectory_policy": "frozen P5",
        "paired_action_rule": "P5选杠则配P5最高分非杠；P5不选杠则配P5最高分杠",
        "strict_dominance_policy": "P5补杠严格支配窗口只作正控，不进入非支配教师自然暴露门",
        "independent_unit": "source_root_id（同牌山四个换座来源只计一个）",
        "outcome_blind": True,
        "model_calls": 0,
        "selection_eligible": False,
        "release_eligible": False,
    })
    print(json.dumps({"status": "PREPARED", "tables": PLANNED_TABLES}, ensure_ascii=False))


def verify_manifest() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    manifest = json.loads((_project_file(_PROJECT_ROOT, OUT / "manifest.json")).read_text(encoding="utf-8"))
    if manifest["contract_sha256"] != digest(CONTRACT):
        raise ValueError("P20 桌赛合同漂移")
    if manifest["action_value_contract_sha256"] != digest(AV_CONTRACT):
        raise ValueError("P20 评分合同漂移")
    if manifest["public_interface_sha256"] != digest(PUBLIC_INTERFACE):
        raise ValueError("P20 公开接口漂移")
    if manifest["parent_sha256"] != digest(PARENT):
        raise ValueError("P20 P5 父代漂移")
    guard.verify(manifest["runtime"])
    frozen = json.loads((_project_file(_PROJECT_ROOT, OUT / "sources.json")).read_text(encoding="utf-8"))["sources"]
    return manifest, frozen


def run() -> None:
    manifest, frozen = verify_manifest()
    authorization = json.loads((_project_file(_PROJECT_ROOT, OUT / "authorization.json")).read_text(encoding="utf-8"))
    natural.require_authorization(authorization)
    ledger = search.ActionValueLedger.load(
        _project_file(_PROJECT_ROOT, OUT / "ledger.json"),
        authorized_budgets=search.av_ledger_budgets_from_authorization(authorization),
    )
    pending = []
    completed_tables = 0
    for row in frozen:
        path = source_path(row)
        if path.exists():
            saved = json.loads(path.read_text(encoding="utf-8"))
            if saved.get("status") != "complete" or saved.get("tables") != TABLES_PER_SOURCE:
                raise ValueError("既有来源不完整：" + str(path))
            completed_tables += TABLES_PER_SOURCE
        else:
            pending.append(row)
    reservation = ledger.reserve(
        step_id="r18:p20-gang-pair-natural-exposure",
        account="tables_full",
        amount=PLANNED_TABLES - completed_tables,
        note="稳定P5杠/非杠成对结果盲自然暴露",
    )
    failures = []
    executed = 0
    usage_unknown = False
    try:
        with concurrent.futures.ProcessPoolExecutor(max_workers=manifest["workers"]) as pool:
            futures = {pool.submit(execute_source, row): row for row in pending}
            for future in concurrent.futures.as_completed(futures):
                row = futures[future]
                result = None
                try:
                    result = future.result()
                    if result["status"] != "complete" or result["tables"] != TABLES_PER_SOURCE:
                        raise RuntimeError(result.get("error") or "来源未跑满")
                    if result["audit"]["problems"]:
                        raise RuntimeError("P5 杠配对复算失败：" + ";".join(result["audit"]["problems"][:3]))
                    write_json(source_path(row), result)
                    executed += TABLES_PER_SOURCE
                    completed_tables += TABLES_PER_SOURCE
                    if completed_tables % 64 == 0 or completed_tables == PLANNED_TABLES:
                        print(json.dumps({
                            "completed_tables": completed_tables,
                            "planned_tables": PLANNED_TABLES,
                        }, ensure_ascii=False), flush=True)
                except Exception as exc:  # noqa: BLE001
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
        "schema": "r18-p20-gang-pair-natural-run/1",
        "source_files": len(files),
        "actual_tables": actual,
        "failures": failures,
        "spent": ledger.account_summary(),
    })
    if failures or actual != PLANNED_TABLES or len(files) != len(frozen):
        raise RuntimeError("P20 杠配对自然暴露执行不完整")
    print(json.dumps({"status": "RUN_COMPLETE", "tables": actual}, ensure_ascii=False))


def analyze() -> None:
    manifest, frozen = verify_manifest()
    summary = json.loads((_project_file(_PROJECT_ROOT, OUT / "run-summary.json")).read_text(encoding="utf-8"))
    if summary["failures"] or summary["actual_tables"] != PLANNED_TABLES:
        raise ValueError("P20 执行不完整")
    raw_counts: Counter[str] = Counter()
    rows_by_root_family_role: dict[
        tuple[str, str, str], list[dict[str, Any]]
    ] = defaultdict(list)
    total_requests = 0
    for source in frozen:
        document = json.loads(source_path(source).read_text(encoding="utf-8"))
        raw_counts.update(document["audit"]["counts"])
        total_requests += int(document["audit"]["counts"].get("focal_requests", 0))
        for row in document["audit"]["eligible_rows"]:
            rows_by_root_family_role[(
                source["source_root_id"], row["family"], row["sample_role"],
            )].append(row)

    frozen_rows = []
    seen_requests = set()
    duplicate_skips = 0
    source_roots = sorted({source["source_root_id"] for source in frozen})
    for source_root in source_roots:
        for family in FAMILIES:
            for role in ("discovery", "positive_control"):
                options = sorted(
                    rows_by_root_family_role.get((source_root, family, role), ()),
                    key=lambda row: (
                        int(row["round_no"]), int(row["snapshot_seq"]),
                        int(row["seat"]), str(row["request_sha256"]),
                    ),
                )
                previously_seen = set(seen_requests)
                selected = next(
                    (row for row in options if row["request_sha256"] not in previously_seen),
                    None,
                )
                duplicate_skips += sum(
                    row["request_sha256"] in previously_seen for row in options
                )
                if selected is not None:
                    seen_requests.add(selected["request_sha256"])
                    frozen_rows.append(selected)

    by_family = {}
    for family in FAMILIES:
        items = [
            row for row in frozen_rows
            if row["family"] == family and row["sample_role"] == "discovery"
        ]
        controls = [
            row for row in frozen_rows
            if row["family"] == family and row["sample_role"] == "positive_control"
        ]
        source_roots = sorted({row["source"]["source_root_id"] for row in items})
        by_family[family] = {
            "eligible_windows": int(raw_counts[family]),
            "frozen_discovery_states": len(items),
            "frozen_positive_control_states": len(controls),
            "source_roots": source_roots,
            "source_root_count": len(source_roots),
            "passes_natural_exposure_gate": (
                len(items) >= MIN_STATES and len(source_roots) >= MIN_SOURCE_ROOTS
            ),
            "reference_action_frequencies": dict(sorted(Counter(
                row["reference_action_key"] for row in items
            ).items())),
            "intervention_action_frequencies": dict(sorted(Counter(
                row["intervention_action_key"] for row in items
            ).items())),
            "score_margin": {
                "min": min((row["p5_score_margin"] for row in items), default=None),
                "max": max((row["p5_score_margin"] for row in items), default=None),
                "mean": (
                    sum(row["p5_score_margin"] for row in items) / len(items)
                    if items else None
                ),
            },
        }
    dataset = {
        "schema": "r18-p20-gang-pair-natural-dataset/1",
        "outcome_blind": True,
        "independent_unit": "source_root_id",
        "rows": frozen_rows,
    }
    result = {
        "schema": "r18-p20-gang-pair-natural-result/1",
        "status": "COMPLETE_P20_GANG_PAIR_NATURAL_EXPOSURE",
        "tables": PLANNED_TABLES,
        "source_units": len(frozen),
        "focal_requests": total_requests,
        "raw_counts": dict(sorted(raw_counts.items())),
        "frozen_states_all_roles": len(frozen_rows),
        "frozen_discovery_states": sum(
            row["sample_role"] == "discovery" for row in frozen_rows
        ),
        "frozen_positive_control_states": sum(
            row["sample_role"] == "positive_control" for row in frozen_rows
        ),
        "request_hashes_unique": len(seen_requests) == len(frozen_rows),
        "duplicate_skips": duplicate_skips,
        "by_family": by_family,
        "families_open_for_p21": [
            family for family in FAMILIES
            if by_family[family]["passes_natural_exposure_gate"]
        ],
        "families_closed_for_low_exposure": [
            family for family in FAMILIES
            if not by_family[family]["passes_natural_exposure_gate"]
        ],
        "next": "仅对通过24状态/4来源根门的非支配发现层运行共同隐藏世界成对教师；严格支配样本只验证正控，其余层不靠合成题补数",
        "selection_eligible": False,
        "release_eligible": False,
    }
    write_json(_project_file(_PROJECT_ROOT, OUT / "dataset.json"), dataset)
    write_json(_project_file(_PROJECT_ROOT, OUT / "result.json"), result)
    print(json.dumps(result, ensure_ascii=False, indent=2))


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
