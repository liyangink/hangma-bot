"""P85：在全新 R18 v2 自然轨迹上冻结“立即胡或继续追爆头”窗口。

只用动作前的玩家观察、合法候选与冻结父代评分确定窗口；不读取结果，
不在本步骤估计弃胡收益。每个对手组合×牌山根最多选一个统计单位。
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
from hangma_bot.policy.r18_integrated_positive_v2 import (  # noqa: E402
    R18_INTEGRATED_POSITIVE_V2_SHA256,
    R18_INTEGRATED_POSITIVE_V2_SOURCE,
)


OUT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p85-hu-deferral-natural-exposure-01-20260925')
CONTRACT = p16.CONTRACT
PARENT = _project_file(_PROJECT_ROOT, ROOT / "src/hangma_bot/policy/r18_integrated_positive_v2.py")
P84_RESULT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p84-high-wealth-near-seven-development-teacher-01-20260925/result.json')
PANEL_SEED = 2026102503
MIXES = ("H", "M")
ROOTS = tuple(range(1, 33))
SEATS = (0, 1, 2, 3)
TABLES_PER_SOURCE = 2
PLANNED_TABLES = len(MIXES) * len(ROOTS) * len(SEATS) * TABLES_PER_SOURCE
LIMITS = p16.LIMITS
MIN_TOTAL_ROOTS = 24
MIN_ROOTS_PER_MIX = 8
MAX_SELECTED_ROOTS_PER_MIX = 16
SELECTION_SALT = "r18-p85-hu-deferral-selection/v1"
SPLIT_SALT = "r18-p85-hu-deferral-split/v1"


def write_json(path: Path, value: Any) -> None:
    """写入稳定 UTF-8 JSON。"""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                    encoding="utf-8")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def value_digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode("utf-8")).hexdigest()


def parent_source() -> str:
    """核对发布包中冻结的 R18 v2 评分源码。"""

    source = R18_INTEGRATED_POSITIVE_V2_SOURCE
    if hashlib.sha256(source.encode("utf-8")).hexdigest() != R18_INTEGRATED_POSITIVE_V2_SHA256:
        raise ValueError("R18 v2 评分源码摘要漂移")
    return source


def sources() -> list[dict[str, Any]]:
    """冻结 H/M 各 32 根、四座位的全新自然牌山来源。"""

    return [{
        "mix": mix, "root_index": root, "focal_seat": seat,
        "source_root_id": f"{mix}:p85:{PANEL_SEED}:r{root:03d}",
        "source_id": f"{mix}:p85:{PANEL_SEED}:r{root:03d}:s{seat}",
    } for mix in MIXES for root in ROOTS for seat in SEATS]


def source_path(source: Mapping[str, Any]) -> Path:
    return _project_file(_PROJECT_ROOT, OUT / "sources" / (str(source["source_id"]).replace(":", "-") + ".json"))


def candidate_row(request: Any, source: Mapping[str, Any],
                  scorer: ActionValueScorer) -> tuple[dict[str, Any] | None, str | None, tuple[str, ...]]:
    """只以动作前事实识别父代确实放弃合法胡、转弃非财神的窗口。"""

    ob = request.observation
    reached: list[str] = []
    if ob.phase != "draw":
        return None, None, tuple(reached)
    reached.append("draw_window")
    if not any(candidate.action_key == "hu" for candidate in request.rules.legal_candidates):
        return None, None, tuple(reached)
    reached.append("legal_immediate_hu")
    view = build_scoring_view(request)
    scored = scorer.score(view)
    if scored.status != "SCORED":
        return None, "R18_V2_" + scored.status + ":" + str(scored.reason), tuple(reached)
    entries = sorted(scored.entries, key=lambda entry: (-entry.score, entry.action_key))
    if not entries:
        return None, "R18_V2_EMPTY_ENTRIES", tuple(reached)
    top = entries[0]
    hu = next((entry for entry in entries if entry.action_key == "hu"), None)
    if hu is None:
        return None, "R18_V2_LEGAL_HU_NOT_SCORED", tuple(reached)
    if not top.action_key.startswith("discard:"):
        return None, None, tuple(reached)
    reached.append("r18_v2_top_discards_instead_of_hu")
    if top.action_key == "discard:" + ob.rule_state.wealth_god.code:
        return None, None, tuple(reached)
    reached.append("top_discards_nonwealth")
    cover = top.trace.get("hu_vs_nonwealth_baotou_cf")
    if not isinstance(cover, dict) or cover.get("triggered") is not True:
        return None, None, tuple(reached)
    reached.append("nonwealth_baotou_cover_triggered")
    if not any(candidate.action_key == top.action_key
               for candidate in request.rules.legal_candidates):
        return None, "R18_V2_TOP_NOT_LEGAL", tuple(reached)

    request_json = decision_request_to_json(request)
    table_id = str(ob.game_id).removeprefix("sitin-stage:")
    return {
        "schema": "r18-p85-hu-deferral-natural-row/1",
        "source": dict(source), "request": request_json,
        "request_sha256": value_digest(request_json),
        "state_projection_sha256": value_digest({
            "observation": request_json["observation"], "rules": request_json["rules"],
            "trigger_seq": request_json["trigger_seq"],
            "window_key": request_json["window_key"],
        }),
        "window_key": request_json["window_key"],
        "focal_physical_seat": ob.seat,
        "table_no": int(table_id.rsplit("-t", 1)[1]),
        "table_id": table_id,
        "reference_action": top.action_key, "intervention_action": "hu",
        "features": {
            "round_no": ob.round_no, "phase": ob.phase,
            "dealer_seat": ob.dealer_seat,
            "remaining_tile_count": ob.remaining_tile_count,
            "own_meld_count": len(ob.melds[ob.seat]),
            "other_meld_counts": [len(ob.melds[seat]) for seat in SEATS if seat != ob.seat],
            "wealth_count_in_hand": sum(tile.code == ob.rule_state.wealth_god.code
                                        for tile in ob.my_hand),
            "baotou": ob.rule_state.baotou,
            "chain_count": ob.rule_state.chain_count,
            "reference_score": top.score, "hu_score": hu.score,
            "reference_trace": top.trace, "hu_trace": hu.trace,
        },
    }, None, tuple(reached + ["eligible_hu_deferral"])


def audit_requests(requests: list[Any], source: Mapping[str, Any],
                   frozen_source: str) -> dict[str, Any]:
    """保存每来源第一条合格状态，并记录完整结果盲暴露漏斗。"""

    scorer = ActionValueScorer("r18-p85-rescore-" + str(source["source_id"]), frozen_source)
    counts: Counter[str] = Counter()
    problems: list[str] = []
    rows = []
    for request in requests:
        counts["focal_requests"] += 1
        row, problem, reached = candidate_row(request, source, scorer)
        if problem is not None:
            problems.append(problem)
        for step in reached:
            counts[step] += 1
        if row is not None:
            rows.append(row)
    rows.sort(key=lambda row: (row["features"]["round_no"],
                               row["window_key"]["trigger_seq"], row["request_sha256"]))
    return {"counts": dict(sorted(counts.items())), "eligible_rows": rows[:1],
            "eligible_rows_before_source_dedup": len(rows), "problems": problems}


def execute_source(source: Mapping[str, Any]) -> dict[str, Any]:
    """让真正 R18 v2 打完该来源的两桌，逐桌核对焦点策略身份。"""

    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    frozen_source = parent_source()
    plans = natural.build_seat_stage_plans(
        contract=contract, opponent=str(source["mix"]),
        root_index=int(source["root_index"]), focal_seat=int(source["focal_seat"]),
        panel_seed=PANEL_SEED,
    )
    requests: list[Any] = []
    stage = natural.run_arm_stage(
        arm="candidate", plans=plans,
        candidate_scorer=ActionValueScorer(
            "r18-p85-trajectory-" + str(source["source_id"]), frozen_source),
        opponent_policies=contract["panel"]["opponent_scenarios"][str(source["mix"])][
            "opponent_policies"],
        versions_block=natural.stage.contract_versions_block(contract),
        step_limit=int(contract["stop"]["step_limit"]), value_limits=LIMITS,
        decision_observer=requests.append,
    )
    focal_policy_ids = []
    if stage.get("status") == "complete":
        for plan, table in zip(plans, stage.get("tables") or []):
            focal_seat = plan.seats().index(natural.FOCAL_PARTICIPANT)
            policy_ids = (table.get("policy_execution") or {}).get("policy_ids_by_seat") or []
            if len(policy_ids) != 4 or not str(policy_ids[focal_seat]).startswith(
                "action_value_v1:r18-p85-trajectory-"):
                raise RuntimeError("P85 焦点座位未运行指定 R18 v2 候选策略")
            focal_policy_ids.append(str(policy_ids[focal_seat]))
        if len(focal_policy_ids) != TABLES_PER_SOURCE:
            raise RuntimeError("P85 逐桌焦点策略身份不完整")
    return {"source": dict(source), "status": stage.get("status"),
            "error": stage.get("error"), "tables": len(stage.get("tables") or []),
            "focal_policy_ids": focal_policy_ids,
            "audit": audit_requests(requests, source, frozen_source)}


def prepare() -> None:
    """在任何新牌山或收益执行前冻结来源、谓词、门和哈希。"""

    if OUT.exists():
        raise SystemExit("P85 目录已存在；拒绝覆盖")
    parent_source()
    previous = json.loads(P84_RESULT.read_text(encoding="utf-8"))
    if previous.get("decision") != "CLOSE_HIGH_WEALTH_NEAR_SEVEN_CLAIM_AXIS":
        raise ValueError("P84 关闭裁定与预期不符")
    OUT.mkdir(parents=True)
    (_project_file(_PROJECT_ROOT, OUT / "sources")).mkdir()
    authorization = batch.unified_document(
        batch_label=OUT.name,
        authorization_id="r18-p85-hu-deferral-natural-exposure-01",
        accounts={"tables_full": PLANNED_TABLES},
        issued_by="lead", issued_at_utc=search.utc_now(), legacy_alias=False,
    )
    authorization.update({
        "issuance_basis": "P84关闭高财神过牌；实网R18 v2七次真正弃胡分歧有四次本人胡、三次他家抢先胡",
        "scope": "全新H/M各32根、四焦点座、每来源两桌；只测R18 v2真实弃胡暴露",
        "max_model_calls": 0, "confirmation_roots": 0,
    })
    write_json(_project_file(_PROJECT_ROOT, OUT / "authorization.json"), authorization)
    write_json(_project_file(_PROJECT_ROOT, OUT / "sources.json"), {"schema": "r18-p85-hu-deferral-sources/1",
                                      "sources": sources()})
    tracked = [Path(__file__), Path(p16.__file__), Path(natural.__file__),
               CONTRACT, PARENT, P84_RESULT, _project_file(_PROJECT_ROOT, OUT / "authorization.json"),
               _project_file(_PROJECT_ROOT, OUT / "sources.json")]
    write_json(_project_file(_PROJECT_ROOT, OUT / "manifest.json"), {
        "schema": "r18-p85-hu-deferral-manifest/1",
        "created_at_utc": search.utc_now(),
        "runtime": guard.capture(source_paths=tracked),
        "contract_sha256": digest(CONTRACT), "parent_sha256": digest(PARENT),
        "parent_score_source_sha256": R18_INTEGRATED_POSITIVE_V2_SHA256,
        "p84_result_sha256": digest(P84_RESULT), "panel_seed": PANEL_SEED,
        "mixes": list(MIXES), "root_indices": list(ROOTS),
        "focal_seats": list(SEATS), "source_units": len(sources()),
        "tables_per_source": TABLES_PER_SOURCE, "planned_tables": PLANNED_TABLES,
        "focal_arm": "candidate",
        "frozen_predicate": (
            "phase_draw and legal_hu and r18_v2_top_is_nonwealth_discard and "
            "top.hu_vs_nonwealth_baotou_cf.triggered_is_true"
        ),
        "predicate_inputs": "依法可见DecisionRequest、合法候选和冻结R18 v2评分；无结果",
        "reference_action": "R18 v2实际首选弃牌", "intervention_action": "hu",
        "independence_unit": "H/M×自然牌山根；四座位与两桌不增加n",
        "minimum_total_roots": MIN_TOTAL_ROOTS,
        "minimum_roots_per_mix": MIN_ROOTS_PER_MIX,
        "maximum_selected_roots_per_mix": MAX_SELECTED_ROOTS_PER_MIX,
        "seat_coverage_required": list(SEATS),
        "selection_salt": SELECTION_SALT, "split_salt": SPLIT_SALT,
        "split_rule": "H/M各最多16个偶数根，哈希盲分开发/复验；不足暴露门则关闭",
        "outcome_blind": True, "replication_labels_opened": False,
        "model_calls": 0, "selection_eligible": False, "release_eligible": False,
    })
    print(json.dumps({"status": "PREPARED", "source_units": len(sources()),
                      "planned_tables": PLANNED_TABLES}, ensure_ascii=False))


def verify() -> list[dict[str, Any]]:
    """确认运行代码、规则合同、父代和自然来源未漂移。"""

    manifest = json.loads((_project_file(_PROJECT_ROOT, OUT / "manifest.json")).read_text(encoding="utf-8"))
    for key, path in (("contract_sha256", CONTRACT), ("parent_sha256", PARENT),
                      ("p84_result_sha256", P84_RESULT)):
        if manifest[key] != digest(path):
            raise ValueError("P85 冻结依赖漂移：" + key)
    if manifest["parent_score_source_sha256"] != R18_INTEGRATED_POSITIVE_V2_SHA256:
        raise ValueError("P85 父代评分身份漂移")
    parent_source()
    guard.verify(manifest["runtime"])
    frozen = json.loads((_project_file(_PROJECT_ROOT, OUT / "sources.json")).read_text(encoding="utf-8"))["sources"]
    if frozen != sources():
        raise ValueError("P85 自然来源清单漂移")
    return frozen


def run() -> None:
    """逐来源运行并按完整桌保守记账；失败即停，允许断点续跑。"""

    frozen = verify()
    authorization = json.loads((_project_file(_PROJECT_ROOT, OUT / "authorization.json")).read_text(encoding="utf-8"))
    natural.require_authorization(authorization)
    ledger = search.ActionValueLedger.load(
        _project_file(_PROJECT_ROOT, OUT / "ledger.json"),
        authorized_budgets=search.av_ledger_budgets_from_authorization(authorization),
    )
    completed = 0
    pending = []
    for source in frozen:
        path = source_path(source)
        if path.exists():
            saved = json.loads(path.read_text(encoding="utf-8"))
            if saved.get("status") != "complete" or saved.get("tables") != TABLES_PER_SOURCE:
                raise ValueError("P85 既有来源不完整：" + str(path))
            completed += TABLES_PER_SOURCE
        else:
            pending.append(source)
    failures = []
    for source in pending:
        reservation = ledger.reserve(
            step_id="r18:p85:natural:" + str(source["source_id"]),
            account="tables_full", amount=TABLES_PER_SOURCE,
            note="R18 v2候选身份核验后的结果盲自然暴露",
        )
        try:
            result = execute_source(source)
            if result["status"] != "complete" or result["tables"] != TABLES_PER_SOURCE:
                raise RuntimeError(result.get("error") or "来源未跑满")
            if result["audit"]["problems"]:
                raise RuntimeError("R18 v2评分失败：" + ";".join(result["audit"]["problems"][:3]))
            write_json(source_path(source), result)
            ledger.settle(reservation, actual=TABLES_PER_SOURCE,
                          note="两桌完成，且焦点策略身份审计通过")
            completed += TABLES_PER_SOURCE
            if completed % 32 == 0 or completed == PLANNED_TABLES:
                print(json.dumps({"completed_tables": completed,
                                  "planned_tables": PLANNED_TABLES},
                                 ensure_ascii=False), flush=True)
        except Exception as exc:  # noqa: BLE001
            ledger.settle(reservation, usage_unknown=True,
                          note="来源执行失败，按两桌保守结算")
            failures.append({"source_id": source["source_id"],
                             "error": type(exc).__name__ + ": " + str(exc)})
            break
    files = list((_project_file(_PROJECT_ROOT, OUT / "sources")).glob("*.json"))
    actual = sum(json.loads(path.read_text(encoding="utf-8"))["tables"] for path in files)
    write_json(_project_file(_PROJECT_ROOT, OUT / "run-summary.json"), {
        "schema": "r18-p85-hu-deferral-run-summary/1",
        "source_files": len(files), "actual_tables": actual,
        "failures": failures, "spent": ledger.account_summary(),
    })
    if failures or actual != PLANNED_TABLES or len(files) != len(frozen):
        raise RuntimeError("P85 自然暴露执行不完整")


def _hash_order(row: Mapping[str, Any], salt: str) -> str:
    return hashlib.sha256("|".join((salt, row["source"]["source_root_id"],
                                     row["request_sha256"])).encode("utf-8")).hexdigest()


def analyze() -> None:
    """根级去重并盲分开发/复验，不读取任一状态的实际结果。"""

    frozen = verify()
    summary = json.loads((_project_file(_PROJECT_ROOT, OUT / "run-summary.json")).read_text(encoding="utf-8"))
    if summary["failures"] or summary["actual_tables"] != PLANNED_TABLES:
        raise ValueError("P85 执行不完整")
    counts: Counter[str] = Counter()
    by_root: dict[str, list[dict[str, Any]]] = defaultdict(list)
    raw_eligible = 0
    for source in frozen:
        document = json.loads(source_path(source).read_text(encoding="utf-8"))
        counts.update(document["audit"]["counts"])
        raw_eligible += document["audit"]["eligible_rows_before_source_dedup"]
        for row in document["audit"]["eligible_rows"]:
            by_root[source["source_root_id"]].append(row)
    independent = [min(options, key=lambda row: _hash_order(row, SELECTION_SALT))
                   for _, options in sorted(by_root.items())]
    pools = {mix: sorted((row for row in independent if row["source"]["mix"] == mix),
                         key=lambda row: _hash_order(row, SPLIT_SALT)) for mix in MIXES}
    selected_counts = {mix: min(MAX_SELECTED_ROOTS_PER_MIX, len(pools[mix])) for mix in MIXES}
    selected_counts = {mix: n - n % 2 for mix, n in selected_counts.items()}
    seat_coverage = sorted({row["focal_physical_seat"] for row in independent})
    passes = (sum(selected_counts.values()) >= MIN_TOTAL_ROOTS
              and all(selected_counts[mix] >= MIN_ROOTS_PER_MIX for mix in MIXES)
              and seat_coverage == list(SEATS))
    selected = []
    if passes:
        for mix in MIXES:
            for index, row in enumerate(pools[mix][:selected_counts[mix]]):
                selected.append({**row, "split": (
                    "development" if index < selected_counts[mix] // 2 else "replication")})
    selected.sort(key=lambda row: (row.get("split", ""), row["source"]["mix"],
                                   row["source"]["source_root_id"], row["request_sha256"]))
    write_json(_project_file(_PROJECT_ROOT, OUT / "dataset.json"), {
        "schema": "r18-p85-hu-deferral-dataset/1",
        "outcome_blind": True, "replication_labels_opened": False, "rows": selected,
    })
    result = {
        "schema": "r18-p85-hu-deferral-result/1",
        "status": "OPEN_DEVELOPMENT_CONFIRMATION" if passes else "INSUFFICIENT_NATURAL_EXPOSURE",
        "tables": PLANNED_TABLES, "source_units": len(frozen),
        "focal_requests": counts["focal_requests"],
        "raw_counts": dict(sorted(counts.items())),
        "raw_eligible_windows": raw_eligible,
        "independent_roots": len(independent),
        "independent_focal_seat_coverage": seat_coverage,
        "by_mix": {mix: {"independent_roots": len(pools[mix]),
                         "selected_roots": selected_counts[mix] if passes else 0,
                         "development_roots": selected_counts[mix] // 2 if passes else 0,
                         "replication_roots": selected_counts[mix] // 2 if passes else 0}
                   for mix in MIXES},
        "selected_states": len(selected),
        "development_states": sum(row["split"] == "development" for row in selected),
        "replication_states": sum(row["split"] == "replication" for row in selected),
        "passes_natural_exposure_gate": passes,
        "replication_labels_opened": False, "model_calls": 0,
        "next": ("仅开发状态可做立即胡/继续的共同隐藏世界教师；复验状态封存"
                 if passes else "按预登记暴露门关闭这一窄作用域，不以构造题补自然根"),
        "selection_eligible": False, "release_eligible": False,
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
