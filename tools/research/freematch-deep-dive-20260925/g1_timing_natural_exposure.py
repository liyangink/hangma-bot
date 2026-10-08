#!/usr/bin/env python3
"""G1：新牌山根上结果盲冻结双听牌鸣/过自然窗口。

本程序只保存玩家观察、合法候选、父代排序与轨迹身份；阶段分仅由
`run_arm_stage` 为推进世界内部计算，不读取或写入筛选产物。
"""

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
import asyncio
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Mapping

ROOT = _PROJECT_ROOT
ROUTE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15')
R10 = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution')
for path in (_project_file(_PROJECT_ROOT, ROOT / "src"), _project_file(_PROJECT_ROOT, ROUTE / "tools"), R10):
    sys.path.insert(0, str(path))

import r18_p83_high_wealth_near_seven_claim_exposure as p83  # noqa: E402
from hangma_bot.application.audit_codec import (  # noqa: E402
    decision_request_from_json, decision_request_to_json,
)
from hangma_bot.kernel.actions import action_key  # noqa: E402
from hangma_bot.policy.action_value_policy import (  # noqa: E402
    ActionValuePolicy, build_scoring_view,
)
from hangma_bot.policy.action_value_seeds import ActionValueScorer  # noqa: E402

OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g1-timing-natural-01')
PREREG = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/G1-SELF-DRAW-TIMING-NATURAL-PREREG-2026-09-26.md')
CONTRACT = p83.CONTRACT
PARENT = p83.PARENT
PANEL_SEED = 2026102701
MIXES = ("H", "M")
ROOTS = tuple(range(1, 33))
SEATS = (0, 1, 2, 3)
TABLES_PER_SOURCE = 2
PLANNED_TABLES = len(MIXES) * len(ROOTS) * len(SEATS) * TABLES_PER_SOURCE
MAX_PER_CATEGORY_MIX = 12
MIN_PER_CATEGORY_MIX = 8
SELECTION_SALT = "g1-timing-natural-selection/v1"
SPLIT_SALT = "g1-timing-natural-split/v1"


def write_json(path: Path, value: Any) -> None:
    """稳定写入 UTF-8 研究产物；冻结清单的重写由调用方禁止。"""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                    encoding="utf-8")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def value_digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")).hexdigest()


def sources() -> list[dict[str, Any]]:
    """64 个独立牌山根各取四焦点座位，两桌阶段。"""

    return [{
        "mix": mix, "root_index": root, "focal_seat": seat,
        "source_root_id": f"{mix}:g1:{PANEL_SEED}:r{root:03d}",
        "source_id": f"{mix}:g1:{PANEL_SEED}:r{root:03d}:s{seat}",
    } for mix in MIXES for root in ROOTS for seat in SEATS]


def source_path(source: Mapping[str, Any]) -> Path:
    return _project_file(_PROJECT_ROOT, OUT / "sources" / (str(source["source_id"]).replace(":", "-") + ".json"))


def _support(action: Any) -> int:
    """求规则估计的有效张数；这不是牌墙概率。"""

    return sum(int(item.remaining_estimate) for item in action.useful_tiles)


def candidate_row(
    request: Any, source: Mapping[str, Any], scorer: ActionValueScorer,
) -> tuple[dict[str, Any] | None, str | None, tuple[str, ...]]:
    """只用当前合法观察筛双听牌自然分歧，并排除 P84 冻结家族。"""

    observation = request.observation
    reached = []
    if observation.phase not in ("response_peng", "response_chi"):
        return None, None, ()
    reached.append("response")
    view = build_scoring_view(request)
    phase_kind = "chi" if observation.phase == "response_chi" else "peng"
    pass_action = next((item for item in view.actions if item.action_type == "pass"), None)
    claims = [item for item in view.actions if item.action_type == phase_kind
              and item.is_legal and item.fact_kind == "hand_progress"
              and item.shanten_after == 0 and item.best_followup_discard is not None]
    if (pass_action is None or pass_action.fact_kind != "hand_progress"
            or pass_action.shanten_after != 0 or not claims):
        return None, None, tuple(reached)
    reached.append("both_tenpai")
    scored = scorer.score(view)
    if scored.status != "SCORED":
        return None, "R18_V2_" + scored.status + ":" + str(scored.reason), tuple(reached)
    entries = sorted(scored.entries, key=lambda item: (-item.score, item.action_key))
    if not entries:
        return None, "R18_V2_EMPTY_ENTRIES", tuple(reached)
    by_key = {item.action_key: item for item in view.actions}
    claim_by_key = {item.action_key: item for item in claims}
    reference = entries[0]
    pass_entry = next((item for item in entries if item.action_key == "pass"), None)
    if pass_entry is None:
        return None, "R18_V2_MISSING_PASS_SCORE", tuple(reached)
    scored_claims = [item for item in entries if item.action_key in claim_by_key]
    if not scored_claims:
        return None, "R18_V2_MISSING_CLAIM_SCORE", tuple(reached)
    if reference.action_key in claim_by_key:
        category = "parent_claim"
        claim_entry = reference
        intervention = "pass"
    elif reference.action_key == "pass":
        category = "parent_pass"
        claim_entry = scored_claims[0]
        intervention = claim_entry.action_key
    else:
        return None, None, tuple(reached)
    claim = claim_by_key[claim_entry.action_key]
    reached.append(category)
    wealth_count = p83.wealth_count(observation)
    if (category == "parent_claim" and wealth_count >= 2
            and pass_action.seven_pairs_shanten_after is not None
            and pass_action.seven_pairs_shanten_after <= 1
            and claim.seven_pairs_shanten_after is None
            and pass_action.standard_shanten_after is not None
            and claim.standard_shanten_after is not None
            and claim.standard_shanten_after <= pass_action.standard_shanten_after):
        return None, None, tuple(reached + ["excluded_p84_exact_family"])
    reached.append("p84_excluded")
    if observation.last_discard is None:
        return None, "RESPONSE_WITHOUT_DISCARD", tuple(reached)
    distance = (observation.seat - observation.last_discard.seat) % 4
    if distance not in (1, 2, 3) or (phase_kind == "chi" and distance != 1):
        return None, "INVALID_RELATIVE_SEAT", tuple(reached)
    request_json = decision_request_to_json(request)
    game_id = str(observation.game_id).removeprefix("sitin-stage:")
    table_suffix = game_id.rsplit("-t", 1)[-1] if "-t" in game_id else game_id.rsplit("_t", 1)[-1]
    if not table_suffix.isdigit():
        return None, "UNKNOWN_TABLE_ID_FORMAT", tuple(reached)
    return {
        "schema": "g1-timing-natural-row/1",
        "source": dict(source), "category": category, "family": phase_kind,
        "request": request_json, "request_sha256": value_digest(request_json),
        "state_projection_sha256": value_digest({
            "observation": request_json["observation"],
            "rules": request_json["rules"],
            "trigger_seq": request_json["trigger_seq"],
            "window_key": request_json["window_key"],
        }),
        "window_key": request_json["window_key"],
        "table_id": game_id, "table_no": int(table_suffix),
        "focal_physical_seat": observation.seat,
        "reference_action": reference.action_key,
        "intervention_action": intervention,
        "features": {
            "round_no": observation.round_no,
            "phase": observation.phase,
            "relative_seat": distance,
            "dealer_seat": observation.dealer_seat,
            "remaining_tile_count": observation.remaining_tile_count,
            "own_meld_count": len(observation.melds[observation.seat]),
            "visible_wealth_count": wealth_count,
            "pass_shanten": pass_action.shanten_after,
            "claim_shanten": claim.shanten_after,
            "pass_support_remaining": _support(pass_action),
            "claim_support_remaining": _support(claim),
            "pass_standard_shanten": pass_action.standard_shanten_after,
            "pass_seven_pairs_shanten": pass_action.seven_pairs_shanten_after,
            "claim_standard_shanten": claim.standard_shanten_after,
            "claim_seven_pairs_shanten": claim.seven_pairs_shanten_after,
            "claim_best_followup_discard": claim.best_followup_discard,
            "parent_score_margin_claim_minus_pass": claim_entry.score - pass_entry.score,
        },
    }, None, tuple(reached + ["eligible"])


def audit_requests(requests: list[Any], source: Mapping[str, Any], parent: str) -> dict:
    """每座位来源、每动作类别最多留一个最早自然状态。"""

    scorer = ActionValueScorer("g1-timing-" + str(source["source_id"]), parent)
    counts = Counter()
    rows_by_category: dict[str, list[dict]] = defaultdict(list)
    problems = []
    for request in requests:
        counts["focal_requests"] += 1
        row, problem, reached = candidate_row(request, source, scorer)
        counts.update(reached)
        if problem:
            problems.append(problem)
        if row is not None:
            rows_by_category[row["category"]].append(row)
    selected = []
    for category in ("parent_claim", "parent_pass"):
        options = rows_by_category[category]
        options.sort(key=lambda row: (
            int(row["features"]["round_no"]), int(row["window_key"]["trigger_seq"]),
            str(row["request_sha256"]),
        ))
        selected.extend(options[:1])
    return {
        "counts": dict(sorted(counts.items())),
        "eligible_rows": selected,
        "eligible_rows_before_source_dedup": sum(map(len, rows_by_category.values())),
        "problems": problems,
    }


def execute_source(source: Mapping[str, Any]) -> dict:
    """两桌自然阶段；只保存状态、策略身份和结果盲窗口。"""

    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    parent = p83.parent_source()
    plans = p83.natural.build_seat_stage_plans(
        contract=contract, opponent=str(source["mix"]),
        root_index=int(source["root_index"]), focal_seat=int(source["focal_seat"]),
        panel_seed=PANEL_SEED,
    )
    requests: list[Any] = []
    stage = p83.natural.run_arm_stage(
        arm="candidate", plans=plans,
        candidate_scorer=ActionValueScorer("g1-trajectory-" + str(source["source_id"]), parent),
        opponent_policies=contract["panel"]["opponent_scenarios"][str(source["mix"])][
            "opponent_policies"],
        versions_block=p83.natural.stage.contract_versions_block(contract),
        step_limit=int(contract["stop"]["step_limit"]),
        value_limits=p83.LIMITS, decision_observer=requests.append,
    )
    policy_ids = []
    if stage.get("status") == "complete":
        for plan, table in zip(plans, stage.get("tables") or []):
            seat = plan.seats().index(p83.natural.FOCAL_PARTICIPANT)
            ids = (table.get("policy_execution") or {}).get("policy_ids_by_seat") or []
            expected = "action_value_v1:g1-trajectory-" + str(source["source_id"])
            if len(ids) != 4 or str(ids[seat]) != expected:
                raise RuntimeError("焦点座位未执行 R18 v2 候选策略")
            policy_ids.append(str(ids[seat]))
        if len(policy_ids) != TABLES_PER_SOURCE:
            raise RuntimeError("自然阶段未完成焦点策略身份核验")
    return {
        "source": dict(source), "status": stage.get("status"),
        "error": stage.get("error"), "tables": len(stage.get("tables") or []),
        "focal_policy_ids": policy_ids,
        "audit": audit_requests(requests, source, parent),
    }


def prepare() -> None:
    """先冻结全部新来源、谓词、选择盐与运行预算。"""

    if OUT.exists():
        raise SystemExit("结果盲自然暴露目录已存在；拒绝覆盖")
    p83.parent_source()
    OUT.mkdir(parents=True)
    (_project_file(_PROJECT_ROOT, OUT / "sources")).mkdir()
    frozen = sources()
    authorization = p83.batch.unified_document(
        batch_label=OUT.name, authorization_id="g1-timing-natural-exposure-01",
        accounts={"tables_full": PLANNED_TABLES}, issued_by="lead",
        issued_at_utc=p83.search.utc_now(), legacy_alias=False,
    )
    authorization.update({
        "issuance_basis": "固定十房鸣/过时序核验；新牌山根双听牌结果盲暴露",
        "scope": "H/M 各32根×四座×两桌；仅 R18 v2 自然轨迹，不读收益",
        "max_model_calls": 0, "confirmation_roots": 0,
    })
    write_json(_project_file(_PROJECT_ROOT, OUT / "authorization.json"), authorization)
    write_json(_project_file(_PROJECT_ROOT, OUT / "sources.json"), {"schema": "g1-timing-sources/1", "sources": frozen})
    tracked = [Path(__file__), Path(p83.__file__), Path(p83.natural.__file__),
               CONTRACT, PARENT, PREREG,
               _project_file(_PROJECT_ROOT, OUT / "authorization.json"), _project_file(_PROJECT_ROOT, OUT / "sources.json")]
    write_json(_project_file(_PROJECT_ROOT, OUT / "manifest.json"), {
        "schema": "g1-timing-natural-manifest/1",
        "created_at_utc": p83.search.utc_now(),
        "runtime": p83.guard.capture(source_paths=tracked),
        "contract_sha256": digest(CONTRACT), "parent_sha256": digest(PARENT),
        "prereg_sha256": digest(PREREG),
        "parent_score_source_sha256": p83.R18_INTEGRATED_POSITIVE_V2_SHA256,
        "panel_seed": PANEL_SEED, "mixes": list(MIXES), "root_indices": list(ROOTS),
        "focal_seats": list(SEATS), "source_units": len(frozen),
        "tables_per_source": TABLES_PER_SOURCE, "planned_tables": PLANNED_TABLES,
        "categories": ["parent_claim", "parent_pass"],
        "frozen_predicate": (
            "response_chi|peng and pass.shanten==0 and legal_claim.shanten==0 "
            "and parent_top==pass|that_claim and complete_followup; exclude exact P84 family"
        ),
        "maximum_per_category_mix": MAX_PER_CATEGORY_MIX,
        "minimum_per_category_mix": MIN_PER_CATEGORY_MIX,
        "selection_salt": SELECTION_SALT, "split_salt": SPLIT_SALT,
        "independence_unit": "source_root_id; four seats and two tables do not increase n",
        "outcome_blind": True, "replication_labels_opened": False,
        "model_calls": 0, "release_eligible": False,
    })
    print(json.dumps({"status": "PREPARED", "source_units": len(frozen),
                      "planned_tables": PLANNED_TABLES}, ensure_ascii=False))


def verify() -> list[dict[str, Any]]:
    """拒绝源码、父代、合同或冻结来源漂移。"""

    manifest = json.loads((_project_file(_PROJECT_ROOT, OUT / "manifest.json")).read_text(encoding="utf-8"))
    if manifest["contract_sha256"] != digest(CONTRACT):
        raise ValueError("合同漂移")
    if manifest["parent_sha256"] != digest(PARENT):
        raise ValueError("父代文件漂移")
    if manifest["prereg_sha256"] != digest(PREREG):
        raise ValueError("预登记漂移")
    if manifest["parent_score_source_sha256"] != p83.R18_INTEGRATED_POSITIVE_V2_SHA256:
        raise ValueError("父代评分源码漂移")
    p83.parent_source()
    p83.guard.verify(manifest["runtime"])
    frozen = json.loads((_project_file(_PROJECT_ROOT, OUT / "sources.json")).read_text(encoding="utf-8"))["sources"]
    if frozen != sources():
        raise ValueError("自然来源清单漂移")
    return frozen


def run() -> None:
    """逐来源断点续跑；失败立即停并保守记账。"""

    frozen = verify()
    authorization = json.loads((_project_file(_PROJECT_ROOT, OUT / "authorization.json")).read_text(encoding="utf-8"))
    p83.natural.require_authorization(authorization)
    ledger = p83.search.ActionValueLedger.load(
        _project_file(_PROJECT_ROOT, OUT / "ledger.json"),
        authorized_budgets=p83.search.av_ledger_budgets_from_authorization(authorization),
    )
    completed_tables = 0
    failure = None
    for source in frozen:
        path = source_path(source)
        if path.exists():
            saved = json.loads(path.read_text(encoding="utf-8"))
            if saved.get("status") != "complete" or saved.get("tables") != TABLES_PER_SOURCE:
                raise ValueError("已存来源不完整：" + str(path))
            completed_tables += TABLES_PER_SOURCE
            continue
        reservation = ledger.reserve(
            step_id="g1:timing:natural:" + str(source["source_id"]),
            account="tables_full", amount=TABLES_PER_SOURCE,
            note="两桌 R18 v2 策略身份核验后的结果盲自然暴露",
        )
        try:
            result = execute_source(source)
            if result["status"] != "complete" or result["tables"] != TABLES_PER_SOURCE:
                raise RuntimeError(result.get("error") or "来源未跑满")
            if result["audit"]["problems"]:
                raise RuntimeError("父代重评分失败：" + ";".join(result["audit"]["problems"][:3]))
            write_json(path, result)
            ledger.settle(reservation, actual=TABLES_PER_SOURCE, note="两桌完成，身份核验通过")
            completed_tables += TABLES_PER_SOURCE
            if completed_tables % 32 == 0 or completed_tables == PLANNED_TABLES:
                print(json.dumps({"completed_tables": completed_tables,
                                  "planned_tables": PLANNED_TABLES}, ensure_ascii=False), flush=True)
        except Exception as exc:  # noqa: BLE001
            ledger.settle(reservation, usage_unknown=True, note="来源失败，按两桌保守结算")
            failure = {"source_id": source["source_id"],
                       "error": type(exc).__name__ + ": " + str(exc)}
            break
    write_json(_project_file(_PROJECT_ROOT, OUT / "run-summary.json"), {
        "schema": "g1-timing-natural-run-summary/1",
        "source_files": len(list((_project_file(_PROJECT_ROOT, OUT / "sources")).glob("*.json"))),
        "actual_tables": completed_tables,
        "failure": failure, "spent": ledger.account_summary(),
    })
    if failure or completed_tables != PLANNED_TABLES:
        raise RuntimeError("自然暴露未完整结束：" + str(failure))


def _hash_row(row: Mapping[str, Any], salt: str) -> str:
    return hashlib.sha256("|".join((
        salt, str(row["source"]["source_root_id"]), str(row["request_sha256"]),
    )).encode("utf-8")).hexdigest()


def analyze() -> None:
    """根级去重、H/M×父代鸣/过分层，并结果盲冻结开发与复验。"""

    if (_project_file(_PROJECT_ROOT, OUT / "dataset.json")).exists() or (_project_file(_PROJECT_ROOT, OUT / "result.json")).exists():
        raise SystemExit("结果盲切分已经冻结；拒绝覆盖")
    frozen = verify()
    summary = json.loads((_project_file(_PROJECT_ROOT, OUT / "run-summary.json")).read_text(encoding="utf-8"))
    if summary.get("failure") or summary.get("actual_tables") != PLANNED_TABLES:
        raise ValueError("512 桌来源未完整")
    counts = Counter()
    options: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for source in frozen:
        document = json.loads(source_path(source).read_text(encoding="utf-8"))
        counts.update(document["audit"]["counts"])
        for row in document["audit"]["eligible_rows"]:
            options[(row["source"]["mix"], row["category"])].append(row)
    selected = []
    strata = {}
    for mix in MIXES:
        candidates = {category: sorted(options[(mix, category)],
                                       key=lambda row: _hash_row(row, SELECTION_SALT))
                      for category in ("parent_claim", "parent_pass")}
        used_roots = set()
        chosen = {category: [] for category in candidates}
        for _ in range(MAX_PER_CATEGORY_MIX):
            for category in ("parent_claim", "parent_pass"):
                row = next((item for item in candidates[category]
                            if item["source"]["source_root_id"] not in used_roots), None)
                if row is None:
                    continue
                chosen[category].append(row)
                used_roots.add(row["source"]["source_root_id"])
        for category, rows in chosen.items():
            if len(rows) % 2:
                rows.pop()
            strata[f"{mix}:{category}"] = {
                "raw_source_rows": len(candidates[category]),
                "independent_available_roots": len({row["source"]["source_root_id"]
                                                    for row in candidates[category]}),
                "selected_roots": len(rows),
            }
            rows.sort(key=lambda row: _hash_row(row, SPLIT_SALT))
            for index, row in enumerate(rows):
                item = dict(row)
                item["split"] = "development" if index < len(rows) // 2 else "replication"
                selected.append(item)
    gate = all(value["selected_roots"] >= MIN_PER_CATEGORY_MIX
               for value in strata.values())
    if not gate:
        selected = []
    selected.sort(key=lambda row: (
        row.get("split", ""), row["source"]["mix"], row["category"],
        row["source"]["source_root_id"], row["request_sha256"],
    ))
    roots = [row["source"]["source_root_id"] for row in selected]
    if len(roots) != len(set(roots)):
        raise ValueError("同一牌山根被重复计入")
    write_json(_project_file(_PROJECT_ROOT, OUT / "dataset.json"), {
        "schema": "g1-timing-natural-dataset/1",
        "outcome_blind": True, "replication_labels_opened": False,
        "rows": selected,
    })
    write_json(_project_file(_PROJECT_ROOT, OUT / "result.json"), {
        "schema": "g1-timing-natural-result/1",
        "status": "OPEN_DEVELOPMENT_TEACHER" if gate else "INSUFFICIENT_NATURAL_EXPOSURE",
        "tables": PLANNED_TABLES, "source_units": len(frozen),
        "independent_selected_roots": len(roots),
        "strata": strata, "funnel": dict(sorted(counts.items())),
        "development_roots": sum(row["split"] == "development" for row in selected),
        "replication_roots": sum(row["split"] == "replication" for row in selected),
        "outcome_blind": True, "model_calls": 0,
    })
    print(json.dumps({"status": "OPEN_DEVELOPMENT_TEACHER" if gate else
                      "INSUFFICIENT_NATURAL_EXPOSURE", "strata": strata,
                      "selected_roots": len(roots)}, ensure_ascii=False, sort_keys=True))


def review_identity() -> None:
    """独立复算选中窗口首选，核验所有桌的实际策略身份。"""

    if (_project_file(_PROJECT_ROOT, OUT / "policy-identity-review.json")).exists():
        raise SystemExit("身份复核产物已存在；拒绝覆盖")
    frozen = verify()
    result = json.loads((_project_file(_PROJECT_ROOT, OUT / "result.json")).read_text(encoding="utf-8"))
    dataset = json.loads((_project_file(_PROJECT_ROOT, OUT / "dataset.json")).read_text(encoding="utf-8"))
    if result["tables"] != PLANNED_TABLES or len(frozen) != len(sources()):
        raise ValueError("自然来源不完整")
    rows = dataset["rows"]
    policy = ActionValuePolicy(ActionValueScorer(
        "g1-independent-policy-review", p83.parent_source(),
    ))
    for row in rows:
        request = decision_request_from_json(row["request"])
        plan = asyncio.run(policy.choose(request, None))
        actual = None if not plan.candidates else action_key(plan.candidates[0].action)
        if actual != row["reference_action"]:
            raise ValueError("冻结窗口父代首选与策略执行不符：" + row["source"]["source_id"])
    identity_tables = 0
    for source in frozen:
        saved = json.loads(source_path(source).read_text(encoding="utf-8"))
        expected = "action_value_v1:g1-trajectory-" + str(source["source_id"])
        if saved["status"] != "complete" or saved["focal_policy_ids"] != [
                expected, expected]:
            raise ValueError("逐桌焦点策略身份错误：" + str(source["source_id"]))
        identity_tables += len(saved["focal_policy_ids"])
    summary = {
        "schema": "g1-timing-policy-identity-review/1",
        "actual_tables": identity_tables,
        "selected_window_policy_top_checked": len(rows),
        "selected_window_policy_top_mismatches": 0,
        "outcome_labels_opened": False,
        "review_passed": identity_tables == PLANNED_TABLES,
    }
    write_json(_project_file(_PROJECT_ROOT, OUT / "policy-identity-review.json"), summary)
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "run", "analyze", "review-identity"))
    args = parser.parse_args()
    {"prepare": prepare, "run": run, "analyze": analyze,
     "review-identity": review_identity}[args.command]()


if __name__ == "__main__":
    main()
