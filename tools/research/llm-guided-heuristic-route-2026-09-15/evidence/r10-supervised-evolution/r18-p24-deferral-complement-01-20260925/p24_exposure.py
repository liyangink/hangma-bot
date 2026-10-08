"""P24 暴露：在全新 R18 v2 自然轨迹上冻结「1 番平价胡 vs 盲弃胡」窗口。

谓词（结果盲：只看动作前的玩家观察、RuleAnalysis 合法候选与冻结 R18 v2 评分）：

    phase == draw
    and hu 在 legal_candidates 里
    and 冻结 R18 v2 首选动作就是 hu            （父代实际收胡）
    and hu 候选 immediate_settlement.fan == 1   （平价胡）
    and 不存在任何合法非财神弃牌使 facts.baotou_after is True（无爆头靶）

臂 A = 立即 hu；臂 B = 冻结 R18 v2 自评最优的非财神弃牌（盲弃胡，不保证进爆头）。
每（对手混合 × 自然牌山根）最多冻结一个状态；独立单元 = mix × root_index。
本步骤不读取任何结算、积分或结果，因此是结果盲的。
"""

from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p24-deferral-complement-01-20260925'

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
EV = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution')
ROUTE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15')
ROOT = _PROJECT_ROOT
for path in (_project_file(_PROJECT_ROOT, ROOT / "src"), _project_file(_PROJECT_ROOT, ROUTE / "tools"), EV):
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

OUT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p24-deferral-complement-01-20260925/exposure')
CONTRACT = p16.CONTRACT
PARENT = _project_file(_PROJECT_ROOT, ROOT / "src/hangma_bot/policy/r18_integrated_positive_v2.py")
PANEL_SEED = 2026102607
MIXES = ("H", "M")
ROOTS = tuple(range(1, 13))
SEATS = (0, 1, 2, 3)
TABLES_PER_SOURCE = 2
SOURCES_PER_MIX = len(ROOTS) * len(SEATS)
PLANNED_TABLES = len(MIXES) * SOURCES_PER_MIX * TABLES_PER_SOURCE
LIMITS = p16.LIMITS
SELECTED_ROOTS_PER_MIX = 8
MINIMUM_ROOTS_PER_MIX = 8
SELECTION_SALT = "r18-p24-deferral-complement-selection/v1"
SPLIT_SALT = "r18-p24-deferral-complement-split/v1"
PREDICATE = (
    "phase_draw and legal_hu and r18_v2_top_is_hu and hu_fan_eq_1 and "
    "no_legal_nonwealth_discard_with_baotou_after_true"
)


def write_json(path: Path, value: Any) -> None:
    """写入稳定 UTF-8 JSON。"""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + chr(10),
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
    """冻结 H/M 各 12 根、四座位的全新自然牌山来源（新 panel_seed）。"""

    return [{
        "mix": mix, "root_index": root, "focal_seat": seat,
        "source_root_id": "np-{0}-{1}-root{2:02d}".format(mix, PANEL_SEED, root),
        "source_id": "{0}:p24:{1}:r{2:03d}:s{3}".format(mix, PANEL_SEED, root, seat),
    } for mix in MIXES for root in ROOTS for seat in SEATS]


def source_path(source: Mapping[str, Any]) -> Path:
    return _project_file(_PROJECT_ROOT, OUT / "sources" / (str(source["source_id"]).replace(":", "-") + ".json"))


def tile_of(key: str) -> str | None:
    return key.split(":", 1)[1] if ":" in key else None


def candidate_row(request: Any, source: Mapping[str, Any], scorer: ActionValueScorer
                  ) -> tuple[dict[str, Any] | None, str | None, tuple[str, ...]]:
    """只以动作前事实识别「1 番平价胡、且无爆头靶」的自然窗口。"""

    ob = request.observation
    reached: list[str] = []
    if ob.phase != "draw":
        return None, None, tuple(reached)
    reached.append("draw_window")
    legal = list(request.rules.legal_candidates)
    if not any(item.action_key == "hu" for item in legal):
        return None, None, tuple(reached)
    reached.append("legal_immediate_hu")
    view = build_scoring_view(request)
    scored = scorer.score(view)
    if scored.status != "SCORED":
        return None, "R18_V2_" + str(scored.status) + ":" + str(scored.reason), tuple(reached)
    entries = sorted(scored.entries, key=lambda entry: (-entry.score, entry.action_key))
    if not entries:
        return None, "R18_V2_EMPTY_ENTRIES", tuple(reached)
    top = entries[0]
    if top.action_key != "hu":
        return None, None, tuple(reached + ["r18_v2_top_is_not_hu"])
    reached.append("r18_v2_top_is_hu")

    hu_item = next(item for item in legal if item.action_key == "hu")
    settlement = getattr(hu_item.value_facts, "immediate_settlement", None)
    hu_fan = None if settlement is None else settlement.fan
    if hu_fan != 1:
        return None, None, tuple(reached + ["hu_fan_is_" + repr(hu_fan)])
    reached.append("hu_fan_eq_1")

    wealth = ob.rule_state.wealth_god.code
    nonwealth_discards = []
    baotou_targets = []
    for item in legal:
        if not str(item.action_key).startswith("discard:"):
            continue
        if tile_of(item.action_key) == wealth:
            continue
        nonwealth_discards.append(item)
        facts = item.facts
        if facts is not None and facts.baotou_after is True:
            baotou_targets.append(item.action_key)
    if not nonwealth_discards:
        return None, "NO_LEGAL_NONWEALTH_DISCARD", tuple(reached)
    if baotou_targets:
        return None, None, tuple(reached + ["has_nonwealth_baotou_target"])
    reached.append("no_nonwealth_baotou_target")

    choices = [entry for entry in entries
               if str(entry.action_key).startswith("discard:")
               and tile_of(entry.action_key) != wealth]
    if not choices:
        return None, "R18_V2_NO_SCORED_NONWEALTH_DISCARD", tuple(reached)
    intervention = choices[0]
    legal_keys = {item.action_key for item in legal}
    if intervention.action_key not in legal_keys:
        return None, "R18_V2_INTERVENTION_NOT_LEGAL", tuple(reached)
    intervention_item = next(item for item in legal
                             if item.action_key == intervention.action_key)

    request_json = decision_request_to_json(request)
    table_id = str(ob.game_id).removeprefix("sitin-stage:")
    useful = getattr(intervention_item.facts, "useful_tiles", ()) or ()
    return {
        "schema": "r18-p24-deferral-complement-natural-row/1",
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
        "reference_action": "hu",
        "intervention_action": intervention.action_key,
        "features": {
            "round_no": ob.round_no, "phase": ob.phase,
            "dealer_seat": ob.dealer_seat,
            "remaining_tile_count": ob.remaining_tile_count,
            "own_meld_count": len(ob.melds[ob.seat]),
            "other_meld_counts": [len(ob.melds[seat]) for seat in SEATS if seat != ob.seat],
            "wealth_count_in_hand": sum(tile.code == wealth for tile in ob.my_hand),
            "baotou": ob.rule_state.baotou,
            "chain_count": ob.rule_state.chain_count,
            "hu_fan": hu_fan,
            "hu_score": top.score,
            "hu_settlement": {
                "fan": settlement.fan,
                "score_delta": list(settlement.score_delta),
                "details": list(settlement.details),
            },
            "intervention_score": intervention.score,
            "intervention_shanten_after": getattr(intervention_item.facts, "shanten_after", None),
            "intervention_useful_kinds": len(useful),
            "intervention_useful_tiles": [tile.code for tile in useful],
            "intervention_baotou_after": getattr(intervention_item.facts, "baotou_after", None),
            "nonwealth_discard_count": len(nonwealth_discards),
            "hand_after_draw": [tile.code for tile in ob.my_hand],
            "drawn_tile": (None if ob.drawn_tile is None else ob.drawn_tile.code),
            "hu_trace": dict(top.trace),
        },
    }, None, tuple(reached + ["eligible_fan1_hu_no_baotou_target"])


def audit_requests(requests: list[Any], source: Mapping[str, Any],
                   frozen_source: str) -> dict[str, Any]:
    """保存每来源第一条合格状态，并记录完整结果盲暴露漏斗。"""

    scorer = ActionValueScorer("r18-p24-rescore-" + str(source["source_id"]), frozen_source)
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
    rows.sort(key=lambda item: (item["features"]["round_no"],
                                item["window_key"]["trigger_seq"], item["request_sha256"]))
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
            "r18-p24-trajectory-" + str(source["source_id"]), frozen_source),
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
                    "action_value_v1:r18-p24-trajectory-"):
                raise RuntimeError("P24 焦点座位未运行指定 R18 v2 候选策略")
            focal_policy_ids.append(str(policy_ids[focal_seat]))
        if len(focal_policy_ids) != TABLES_PER_SOURCE:
            raise RuntimeError("P24 逐桌焦点策略身份不完整")
    return {"source": dict(source), "status": stage.get("status"),
            "error": stage.get("error"), "tables": len(stage.get("tables") or []),
            "focal_policy_ids": focal_policy_ids,
            "audit": audit_requests(requests, source, frozen_source)}


def prepare() -> None:
    """在任何新牌山执行前冻结来源、谓词、门和哈希。"""

    if OUT.exists():
        raise SystemExit("P24 暴露目录已存在；拒绝覆盖")
    parent_source()
    OUT.mkdir(parents=True)
    (_project_file(_PROJECT_ROOT, OUT / "sources")).mkdir()
    authorization = batch.unified_document(
        batch_label=OUT.parent.name,
        authorization_id="r18-p24-deferral-complement-natural-exposure-01",
        accounts={"tables_full": PLANNED_TABLES},
        issued_by="lead", issued_at_utc=search.utc_now(), legacy_alias=False,
    )
    authorization.update({
        "issuance_basis": "P24 前置普查：全量 3,920 局上收紧池 742 窗，远超 16 根量级",
        "scope": "全新 H/M 各 12 根、四焦点座、每来源两桌；只测 R18 v2 自然暴露",
        "max_model_calls": 0, "confirmation_roots": 0,
    })
    write_json(_project_file(_PROJECT_ROOT, OUT / "authorization.json"), authorization)
    write_json(_project_file(_PROJECT_ROOT, OUT / "sources.json"), {"schema": "r18-p24-deferral-complement-sources/1",
                                      "sources": sources()})
    tracked = [Path(__file__), Path(p16.__file__), Path(natural.__file__),
               CONTRACT, PARENT, _project_file(_PROJECT_ROOT, OUT / "authorization.json"), _project_file(_PROJECT_ROOT, OUT / "sources.json")]
    write_json(_project_file(_PROJECT_ROOT, OUT / "manifest.json"), {
        "schema": "r18-p24-deferral-complement-manifest/1",
        "created_at_utc": search.utc_now(),
        "runtime": guard.capture(source_paths=tracked),
        "contract_sha256": digest(CONTRACT), "parent_sha256": digest(PARENT),
        "parent_score_source_sha256": R18_INTEGRATED_POSITIVE_V2_SHA256,
        "panel_seed": PANEL_SEED, "mixes": list(MIXES), "root_indices": list(ROOTS),
        "focal_seats": list(SEATS), "source_units": len(sources()),
        "tables_per_source": TABLES_PER_SOURCE, "planned_tables": PLANNED_TABLES,
        "focal_arm": "candidate", "frozen_predicate": PREDICATE,
        "predicate_inputs": "依法可见 DecisionRequest、RuleAnalysis 合法候选与冻结 R18 v2 评分；无结果",
        "reference_action": "hu",
        "intervention_action": "冻结 R18 v2 自评最优的非财神弃牌（盲弃胡）",
        "independence_unit": "mix × 自然牌山根；四座位与两桌不增加 n",
        "selected_roots_per_mix": SELECTED_ROOTS_PER_MIX,
        "minimum_roots_per_mix": MINIMUM_ROOTS_PER_MIX,
        "selection_salt": SELECTION_SALT, "split_salt": SPLIT_SALT,
        "selection_rule": "每 source_root 按选择盐取一条；H/M 各自按切分盐排序后取前 8 根为开发根",
        "outcome_blind": True, "replication_labels_opened": False,
        "model_calls": 0, "selection_eligible": False, "release_eligible": False,
    })
    print(json.dumps({"status": "PREPARED", "source_units": len(sources()),
                      "planned_tables": PLANNED_TABLES}, ensure_ascii=False))


def verify() -> list[dict[str, Any]]:
    """确认运行代码、规则合同、父代和自然来源未漂移。"""

    manifest = json.loads((_project_file(_PROJECT_ROOT, OUT / "manifest.json")).read_text(encoding="utf-8"))
    for key, path in (("contract_sha256", CONTRACT), ("parent_sha256", PARENT)):
        if manifest[key] != digest(path):
            raise ValueError("P24 冻结依赖漂移：" + key)
    if manifest["parent_score_source_sha256"] != R18_INTEGRATED_POSITIVE_V2_SHA256:
        raise ValueError("P24 父代评分身份漂移")
    parent_source()
    guard.verify(manifest["runtime"])
    frozen = json.loads((_project_file(_PROJECT_ROOT, OUT / "sources.json")).read_text(encoding="utf-8"))["sources"]
    if frozen != sources():
        raise ValueError("P24 自然来源清单漂移")
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
                raise ValueError("P24 既有来源不完整：" + str(path))
            completed += TABLES_PER_SOURCE
        else:
            pending.append(source)
    failures = []
    for source in pending:
        reservation = ledger.reserve(
            step_id="r18:p24:natural:" + str(source["source_id"]),
            account="tables_full", amount=TABLES_PER_SOURCE,
            note="P24 结果盲自然暴露（收紧池：1 番平价胡且无爆头靶）",
        )
        try:
            result = execute_source(source)
            if result["status"] != "complete" or result["tables"] != TABLES_PER_SOURCE:
                raise RuntimeError(result.get("error") or "来源未跑满")
            if result["audit"]["problems"]:
                raise RuntimeError("R18 v2 评分失败：" + ";".join(result["audit"]["problems"][:3]))
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
        "schema": "r18-p24-deferral-complement-run-summary/1",
        "source_files": len(files), "actual_tables": actual,
        "failures": failures, "spent": ledger.account_summary(),
    })
    if failures or actual != PLANNED_TABLES or len(files) != len(frozen):
        raise RuntimeError("P24 自然暴露执行不完整")


def _hash_order(row: Mapping[str, Any], salt: str) -> str:
    return hashlib.sha256("|".join((salt, row["source"]["source_root_id"],
                                     row["request_sha256"])).encode("utf-8")).hexdigest()


def analyze() -> None:
    """根级去重并盲分，不读取任一状态的实际结果。"""

    frozen = verify()
    summary = json.loads((_project_file(_PROJECT_ROOT, OUT / "run-summary.json")).read_text(encoding="utf-8"))
    if summary["failures"] or summary["actual_tables"] != PLANNED_TABLES:
        raise ValueError("P24 暴露执行不完整")
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
    selected = []
    for mix in MIXES:
        for row in pools[mix][:SELECTED_ROOTS_PER_MIX]:
            selected.append({**row, "mix_rank": _hash_order(row, SPLIT_SALT)})
    selected.sort(key=lambda row: (row["source"]["mix"], row["mix_rank"]))
    passes = all(len(pools[mix]) >= MINIMUM_ROOTS_PER_MIX for mix in MIXES)
    seat_coverage = sorted({row["focal_physical_seat"] for row in independent})
    write_json(_project_file(_PROJECT_ROOT, OUT / "dataset.json"), {
        "schema": "r18-p24-deferral-complement-dataset/1",
        "outcome_blind": True, "rows": selected,
    })
    result = {
        "schema": "r18-p24-deferral-complement-result/1",
        "status": "OPEN_DEVELOPMENT_TEACHER" if passes else "INSUFFICIENT_NATURAL_EXPOSURE",
        "tables": PLANNED_TABLES, "source_units": len(frozen),
        "focal_requests": counts["focal_requests"],
        "raw_counts": dict(sorted(counts.items())),
        "raw_eligible_windows": raw_eligible,
        "independent_roots": len(independent),
        "independent_focal_seat_coverage": seat_coverage,
        "by_mix": {mix: {"independent_roots": len(pools[mix]),
                         "selected_roots": min(SELECTED_ROOTS_PER_MIX, len(pools[mix])),
                         "independent_seat_coverage": sorted({row["focal_physical_seat"]
                                                              for row in pools[mix]})}
                   for mix in MIXES},
        "selected_states": len(selected),
        "passes_natural_exposure_gate": passes,
        "next": ("按预登记 §三 四道门跑配对续打"
                 if passes else "按预登记暴露门关闭，不以构造题补自然根"),
        "selection_eligible": False, "release_eligible": False,
        "outcome_blind": True, "model_calls": 0,
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
