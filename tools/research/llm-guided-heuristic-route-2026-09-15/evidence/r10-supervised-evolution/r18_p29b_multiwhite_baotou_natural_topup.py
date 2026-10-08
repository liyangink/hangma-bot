"""R18 P29b：两张财神、飘后仍保持爆头的结果盲自然暴露追加批。

P28 并轨的构造材料提出一个直接受杭麻规则支持的新假设：当前可胡且持有两张
财神时，打出一张财神后若仍为爆头，继续路线可能优于立即收胡。P3 已覆盖三、
四财神的窄边界，本批只观察恰好两张财神，避免重复评价既有专长。

P29 首批 512 桌只得到 4 个独立牌山根。本追加批保持完全相同的公开谓词，
只更换 panel seed 并追加 2,560 桌，使两批合计达到预登记上限 3,072 桌。
本程序不独立拆分开发/复验；最终由 P29c 对两批来源根合并后统一裁定。
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
import r18_p16_catch_play_natural_exposure as p16  # noqa: E402
import sitin_natural_panel as natural  # noqa: E402
import sitin_search as search  # noqa: E402
import strong_seed_batch as batch  # noqa: E402
from hangma_bot.application.audit_codec import decision_request_to_json  # noqa: E402
from hangma_bot.policy.action_value_policy import build_scoring_view  # noqa: E402
from hangma_bot.policy.action_value_seeds import ActionValueScorer  # noqa: E402


OUT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p29b-multiwhite-baotou-natural-topup-01-20260922')
CONTRACT = p16.CONTRACT
PARENT = p16.PARENT
PANEL_SEED = 2026102206
MIXES = ("H", "M")
ROOTS = tuple(range(1, 161))
SEATS = (0, 1, 2, 3)
TABLES_PER_SOURCE = 2
PLANNED_TABLES = len(MIXES) * len(ROOTS) * len(SEATS) * TABLES_PER_SOURCE
WORKERS = 8
LIMITS = p16.LIMITS
MIN_TOTAL_ROOTS = 24
MIN_ROOTS_PER_MIX = 8
MAX_SELECTED_ROOTS_PER_MIX = 16
SELECTION_SALT = "r18-p29b-multiwhite-baotou-selection/v1"
SPLIT_SALT = "r18-p29b-multiwhite-baotou-split/v1"


def write_json(path: Path, value: Any) -> None:
    """写入稳定 UTF-8 JSON。"""

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


def sources() -> list[dict[str, Any]]:
    """冻结 320 个追加牌山根的四座位自然来源。"""

    return [
        {
            "mix": mix,
            "root_index": root,
            "focal_seat": seat,
            "source_root_id": f"{mix}:b2:r{root:03d}",
            "source_id": f"{mix}:b2:r{root:03d}:s{seat}",
        }
        for mix in MIXES for root in ROOTS for seat in SEATS
    ]


def source_path(row: Mapping[str, Any]) -> Path:
    return _project_file(_PROJECT_ROOT, OUT / "sources" / (str(row["source_id"]).replace(":", "-") + ".json"))


def combined_hand(observation: Any) -> list[str]:
    """按观察快照语义取得包含当前摸牌的本人暗牌。"""

    hand = [tile.code for tile in observation.my_hand]
    if (
        observation.drawn_tile is not None
        and len(hand) != observation.hand_counts[observation.seat]
    ):
        hand.append(observation.drawn_tile.code)
    return hand


def _candidate_row(
    request: Any,
    source: Mapping[str, Any],
    scorer: ActionValueScorer,
) -> tuple[dict[str, Any] | None, str | None, str | None]:
    """应用冻结公开谓词；返回行、问题和最细命中阶段。"""

    observation = request.observation
    if observation.phase != "draw":
        return None, None, None
    stage = "draw_window"
    hand = combined_hand(observation)
    counts = Counter(hand)
    wealth = observation.rule_state.wealth_god.code
    if wealth != "白":
        return None, "UNEXPECTED_WEALTH_CODE:" + str(wealth), None
    wealth_count = counts[wealth]
    if wealth_count != 2:
        return None, None, stage
    stage = "exactly_two_wealth"

    view = build_scoring_view(request)
    facts_by_key = {item.action_key: item for item in view.actions}
    if not {"hu", "discard:白"} <= set(facts_by_key):
        return None, None, stage
    stage = "hu_and_piao_legal"
    piao_facts = facts_by_key["discard:白"]
    if piao_facts.baotou_after is not True:
        return None, None, stage
    stage = "piao_baotou_after_true"

    scored = scorer.score(view)
    if scored.status != "SCORED":
        return None, "P5_" + scored.status + ":" + str(scored.reason), None
    entries = sorted(scored.entries, key=lambda item: (-item.score, item.action_key))
    if not entries:
        return None, "P5_EMPTY_ENTRIES", None
    reference = entries[0]
    if reference.action_key != "hu":
        return None, None, "p5_not_immediate_hu"
    piao_entry = next(
        (entry for entry in entries if entry.action_key == "discard:白"), None
    )
    if piao_entry is None:
        return None, "P5_SCORE_ACTION_FACT_MISMATCH", None

    request_json = decision_request_to_json(request)
    table_id = str(observation.game_id).removeprefix("sitin-stage:")
    return {
        "schema": "r18-p29b-multiwhite-baotou-natural-row/1",
        "source": dict(source),
        "request_sha256": value_digest(request_json),
        "state_projection_sha256": value_digest({
            "observation": request_json["observation"],
            "rules": request_json["rules"],
            "trigger_seq": request_json["trigger_seq"],
            "window_key": request_json["window_key"],
        }),
        "window_key": request_json["window_key"],
        "focal_physical_seat": observation.seat,
        "table_no": int(table_id.rsplit("-t", 1)[1]),
        "table_id": table_id,
        "reference_action": "hu",
        "intervention_action": "discard:白",
        "features": {
            "round_no": observation.round_no,
            "phase": observation.phase,
            "dealer_seat": observation.dealer_seat,
            "remaining_tile_count": observation.remaining_tile_count,
            "wealth_count_before": wealth_count,
            "wealth_count_after_piao": wealth_count - 1,
            "own_meld_count": len(observation.melds[observation.seat]),
            "chain_count": observation.rule_state.chain_count,
            "chain_piao": observation.chain_piao,
            "baotou": observation.rule_state.baotou,
            "piao_baotou_after": piao_facts.baotou_after,
            "piao_standard_shanten_after": piao_facts.standard_shanten_after,
            "piao_seven_pairs_shanten_after": piao_facts.seven_pairs_shanten_after,
            "reference_score": reference.score,
            "intervention_score": piao_entry.score,
            "p5_score_margin": reference.score - piao_entry.score,
            "reference_trace": reference.trace,
            "intervention_trace": piao_entry.trace,
        },
    }, None, "eligible_exactly_two_wealth_piao_keeps_baotou"


def audit_requests(
    requests: list[Any], source: Mapping[str, Any], parent_source: str,
) -> dict[str, Any]:
    """每来源只保存第一条符合固定谓词的状态，避免运行产物膨胀。"""

    scorer = ActionValueScorer("r18-p29b-p5-" + str(source["source_id"]), parent_source)
    counts: Counter[str] = Counter()
    problems = []
    rows = []
    for request in requests:
        counts["focal_requests"] += 1
        row, problem, stage = _candidate_row(request, source, scorer)
        if problem is not None:
            problems.append(problem)
        if stage is not None:
            counts[stage] += 1
        if row is not None:
            rows.append(row)
    rows.sort(key=lambda item: (
        int(item["features"]["round_no"]),
        int(item["window_key"]["trigger_seq"]),
        str(item["request_sha256"]),
    ))
    return {
        "counts": dict(sorted(counts.items())),
        "eligible_rows": rows[:1],
        "eligible_rows_before_source_dedup": len(rows),
        "problems": problems,
    }


def execute_source(source: Mapping[str, Any]) -> dict[str, Any]:
    """运行一个来源单元的两桌 P5 阶段并应用公开谓词。"""

    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    parent_source = PARENT.read_text(encoding="utf-8")
    plans = natural.build_seat_stage_plans(
        contract=contract, opponent=str(source["mix"]),
        root_index=int(source["root_index"]), focal_seat=int(source["focal_seat"]),
        panel_seed=PANEL_SEED,
    )
    requests: list[Any] = []
    stage = natural.run_arm_stage(
        arm="p29b-p5-multiwhite-baotou-natural", plans=plans,
        candidate_scorer=ActionValueScorer(
            "r18-p29b-trajectory-" + str(source["source_id"]), parent_source,
        ),
        opponent_policies=contract["panel"]["opponent_scenarios"][str(source["mix"])][
            "opponent_policies"
        ],
        versions_block=natural.stage.contract_versions_block(contract),
        step_limit=int(contract["stop"]["step_limit"]), value_limits=LIMITS,
        decision_observer=requests.append,
    )
    return {
        "source": dict(source), "status": stage.get("status"),
        "error": stage.get("error"), "tables": len(stage.get("tables") or []),
        "audit": audit_requests(requests, source, parent_source),
    }


def prepare() -> None:
    """在运行全新自然桌前冻结谓词、来源、暴露门和开发/复验规则。"""

    if OUT.exists():
        raise SystemExit("P29b 目录已存在；拒绝覆盖")
    OUT.mkdir(parents=True)
    (_project_file(_PROJECT_ROOT, OUT / "sources")).mkdir()
    authorization = batch.unified_document(
        batch_label=OUT.name,
        authorization_id="r18-p29b-multiwhite-baotou-natural-topup-01",
        accounts={"tables_full": PLANNED_TABLES},
        issued_by="lead", issued_at_utc=search.utc_now(), legacy_alias=False,
    )
    authorization.update({
        "issuance_basis": "P29首批4根未过门；按预登记3,072桌上限追加且不改谓词",
        "scope": "全新seed，H/M各160根、四焦点座、每来源两桌；P5结果盲追加暴露",
        "max_model_calls": 0,
        "confirmation_roots": 0,
    })
    frozen_sources = sources()
    write_json(_project_file(_PROJECT_ROOT, OUT / "authorization.json"), authorization)
    write_json(_project_file(_PROJECT_ROOT, OUT / "sources.json"), {
        "schema": "r18-p29b-multiwhite-baotou-sources/1",
        "sources": frozen_sources,
    })
    tracked = [
        Path(__file__), Path(p16.__file__), Path(natural.__file__),
        CONTRACT, PARENT, _project_file(_PROJECT_ROOT, OUT / "authorization.json"), _project_file(_PROJECT_ROOT, OUT / "sources.json"),
    ]
    write_json(_project_file(_PROJECT_ROOT, OUT / "manifest.json"), {
        "schema": "r18-p29b-multiwhite-baotou-natural-manifest/1",
        "created_at_utc": search.utc_now(),
        "runtime": guard.capture(source_paths=tracked),
        "contract_sha256": digest(CONTRACT),
        "parent_sha256": digest(PARENT),
        "panel_seed": PANEL_SEED,
        "mixes": list(MIXES), "root_indices": list(ROOTS),
        "focal_seats": list(SEATS), "sources": len(frozen_sources),
        "tables_per_source": TABLES_PER_SOURCE,
        "planned_tables": PLANNED_TABLES, "workers": WORKERS,
        "frozen_predicate": (
            "draw and exactly_two_wealth and hu_legal and discard_white_legal and "
            "discard_white.baotou_after_is_true and p5_top_is_hu"
        ),
        "predicate_inputs": (
            "依法可见DecisionRequest、合法动作、hangma同源CandidateFacts.baotou_after、"
            "冻结P5评分；不读取局或阶段结果"
        ),
        "independence_unit": "source_root_id（H/M+自然根）；四座位与两桌不增加n",
        "minimum_total_roots": MIN_TOTAL_ROOTS,
        "minimum_roots_per_mix": MIN_ROOTS_PER_MIX,
        "maximum_selected_roots_per_mix": MAX_SELECTED_ROOTS_PER_MIX,
        "seat_coverage_required": list(SEATS),
        "selection_salt": SELECTION_SALT,
        "split_salt": SPLIT_SALT,
        "split_rule": "本批不独立拆分；P29c 合并 P29/P29b 后统一结果盲拆分",
        "outcome_blind": True,
        "replication_labels_opened": False,
        "model_calls": 0, "selection_eligible": False, "release_eligible": False,
    })
    print(json.dumps({
        "status": "PREPARED", "source_units": len(frozen_sources),
        "planned_tables": PLANNED_TABLES,
    }, ensure_ascii=False))


def verify() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """核对冻结脚本、合同、父代和来源清单未漂移。"""

    manifest = json.loads((_project_file(_PROJECT_ROOT, OUT / "manifest.json")).read_text(encoding="utf-8"))
    if manifest["contract_sha256"] != digest(CONTRACT):
        raise ValueError("P29b 合同漂移")
    if manifest["parent_sha256"] != digest(PARENT):
        raise ValueError("P29b P5父代漂移")
    guard.verify(manifest["runtime"])
    frozen = json.loads((_project_file(_PROJECT_ROOT, OUT / "sources.json")).read_text(encoding="utf-8"))["sources"]
    if frozen != sources():
        raise ValueError("P29b 全新自然来源清单漂移")
    return manifest, frozen


def run() -> None:
    """并行执行 2,560 张追加自然桌，支持断点续跑。"""

    manifest, frozen = verify()
    authorization = json.loads((_project_file(_PROJECT_ROOT, OUT / "authorization.json")).read_text(encoding="utf-8"))
    natural.require_authorization(authorization)
    ledger = search.ActionValueLedger.load(
        _project_file(_PROJECT_ROOT, OUT / "ledger.json"),
        authorized_budgets=search.av_ledger_budgets_from_authorization(authorization),
    )
    pending = []
    completed_tables = 0
    for source in frozen:
        path = source_path(source)
        if path.exists():
            saved = json.loads(path.read_text(encoding="utf-8"))
            if saved.get("status") != "complete" or saved.get("tables") != TABLES_PER_SOURCE:
                raise ValueError("既有 P29b 来源不完整：" + str(path))
            completed_tables += TABLES_PER_SOURCE
        else:
            pending.append(source)
    reservation = ledger.reserve(
        step_id="r18:p29b-multiwhite-baotou:natural-topup", account="tables_full",
        amount=PLANNED_TABLES - completed_tables,
        note="全新P5自然桌搜索恰好两财神且飘后仍保持爆头的机会",
    )
    failures = []
    executed = 0
    usage_unknown = False
    try:
        with concurrent.futures.ProcessPoolExecutor(max_workers=manifest["workers"]) as pool:
            futures = {pool.submit(execute_source, source): source for source in pending}
            for future in concurrent.futures.as_completed(futures):
                source = futures[future]
                result = None
                try:
                    result = future.result()
                    if result["status"] != "complete" or result["tables"] != TABLES_PER_SOURCE:
                        raise RuntimeError(result.get("error") or "来源未跑满")
                    if result["audit"]["problems"]:
                        raise RuntimeError("P5 重评分失败：" + ";".join(result["audit"]["problems"][:3]))
                    write_json(source_path(source), result)
                    executed += TABLES_PER_SOURCE
                    completed_tables += TABLES_PER_SOURCE
                    if completed_tables % 128 == 0 or completed_tables == PLANNED_TABLES:
                        print(json.dumps({
                            "completed_tables": completed_tables,
                            "planned_tables": PLANNED_TABLES,
                        }, ensure_ascii=False), flush=True)
                except Exception as exc:  # noqa: BLE001
                    if result is None:
                        usage_unknown = True
                    failures.append({
                        "source_id": source["source_id"],
                        "error": type(exc).__name__ + ": " + str(exc),
                    })
    finally:
        if usage_unknown:
            ledger.settle(reservation, usage_unknown=True, note="子进程未返回；保守结算")
        else:
            ledger.settle(reservation, actual=executed, note="按完整返回桌数结算")
    files = list((_project_file(_PROJECT_ROOT, OUT / "sources")).glob("*.json"))
    actual = sum(json.loads(path.read_text(encoding="utf-8"))["tables"] for path in files)
    write_json(_project_file(_PROJECT_ROOT, OUT / "run-summary.json"), {
        "schema": "r18-p29b-multiwhite-baotou-run-summary/1",
        "source_files": len(files), "actual_tables": actual,
        "failures": failures, "spent": ledger.account_summary(),
    })
    if failures or actual != PLANNED_TABLES or len(files) != len(frozen):
        raise RuntimeError("P29b 追加自然暴露执行不完整")


def _hash_order(row: Mapping[str, Any], salt: str) -> str:
    payload = "|".join((
        salt, str(row["source"]["source_root_id"]), str(row["request_sha256"]),
    ))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def analyze() -> None:
    """按自然牌山根去重并冻结等量 H/M 开发与复验状态，不生成标签。"""

    manifest, frozen = verify()
    summary = json.loads((_project_file(_PROJECT_ROOT, OUT / "run-summary.json")).read_text(encoding="utf-8"))
    if summary["failures"] or summary["actual_tables"] != PLANNED_TABLES:
        raise ValueError("P29b 执行不完整")
    raw_counts: Counter[str] = Counter()
    rows_by_root: dict[str, list[dict[str, Any]]] = defaultdict(list)
    raw_eligible = 0
    for source in frozen:
        document = json.loads(source_path(source).read_text(encoding="utf-8"))
        raw_counts.update(document["audit"]["counts"])
        raw_eligible += int(document["audit"]["eligible_rows_before_source_dedup"])
        for row in document["audit"]["eligible_rows"]:
            rows_by_root[str(source["source_root_id"])].append(row)

    independent = []
    for source_root_id, options in sorted(rows_by_root.items()):
        independent.append(min(options, key=lambda row: _hash_order(row, SELECTION_SALT)))
    pools = {
        mix: sorted(
            (row for row in independent if row["source"]["mix"] == mix),
            key=lambda row: _hash_order(row, SPLIT_SALT),
        )
        for mix in MIXES
    }
    seat_coverage = sorted({int(row["focal_physical_seat"]) for row in independent})
    independent.sort(key=lambda row: (
        row["source"]["mix"], row["source"]["source_root_id"],
        row["request_sha256"],
    ))
    dataset = {
        "schema": "r18-p29b-multiwhite-baotou-dataset/1",
        "outcome_blind": True, "replication_labels_opened": False,
        "rows": independent,
    }
    by_mix = {
        mix: {
            "independent_roots": len(pools[mix]),
            "selected_roots": 0,
            "development_roots": 0,
            "replication_roots": 0,
        }
        for mix in MIXES
    }
    result = {
        "schema": "r18-p29b-multiwhite-baotou-natural-result/1",
        "status": "COMPLETE_TOPUP_AWAITING_P29C_CONSOLIDATION",
        "tables": PLANNED_TABLES,
        "source_units": len(frozen),
        "focal_requests": int(raw_counts["focal_requests"]),
        "raw_counts": dict(sorted(raw_counts.items())),
        "raw_eligible_windows": raw_eligible,
        "independent_roots": len(independent),
        "independent_focal_seat_coverage": seat_coverage,
        "by_mix": by_mix,
        "selected_states": 0,
        "development_states": 0,
        "replication_states": 0,
        "passes_natural_exposure_gate": None,
        "replication_labels_opened": False,
        "model_calls": 0,
        "next": "由P29c合并P29首批与本追加批，再统一裁定和结果盲拆分",
        "selection_eligible": False, "release_eligible": False,
    }
    write_json(_project_file(_PROJECT_ROOT, OUT / "dataset.json"), dataset)
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
