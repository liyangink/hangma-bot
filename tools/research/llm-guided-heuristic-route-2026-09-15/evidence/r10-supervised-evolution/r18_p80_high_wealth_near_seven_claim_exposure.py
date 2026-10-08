"""R18 P80：高财神、近听七对时鸣牌与过牌的结果盲自然暴露。

P31 已否定宽泛的“过牌保七对”规则，且其 32 个冻结状态都不满足
“至少两财神且过牌后七对向听≤1”。本批只研究这个未覆盖的窄条件：
R18 v2 实际选择吃/碰，普通型向听不变或改善，但吃/碰会关闭七对路线。

本程序在运行新牌山前冻结公开谓词；只保存自然可达状态，不生成收益标签、
不调用模型。每个自然牌山根最多贡献一个统计单位，达到暴露门后才拆分开发与
复验并进入共同隐藏世界教师。
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
from hangma_bot.policy.r18_integrated_positive_v2 import (  # noqa: E402
    R18_INTEGRATED_POSITIVE_V2_SHA256,
    R18_INTEGRATED_POSITIVE_V2_SOURCE,
)


OUT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p80-high-wealth-near-seven-claim-exposure-01-20260925')
CONTRACT = p16.CONTRACT
PARENT = _project_file(_PROJECT_ROOT, ROOT / "src/hangma_bot/policy/r18_integrated_positive_v2.py")
PRIOR_DATASET = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p30-closed-route-claim-natural-exposure-01-20260922/dataset.json')
PRIOR_TEACHER = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p31-closed-route-claim-development-teacher-01-20260922/result.json')
PANEL_SEED = 2026102501
MIXES = ("H", "M")
ROOTS = tuple(range(1, 33))
SEATS = (0, 1, 2, 3)
TABLES_PER_SOURCE = 2
PLANNED_TABLES = len(MIXES) * len(ROOTS) * len(SEATS) * TABLES_PER_SOURCE
WORKERS = 8
LIMITS = p16.LIMITS
MIN_TOTAL_ROOTS = 24
MIN_ROOTS_PER_MIX = 8
MAX_SELECTED_ROOTS_PER_MIX = 16
SELECTION_SALT = "r18-p80-high-wealth-near-seven-selection/v1"
SPLIT_SALT = "r18-p80-high-wealth-near-seven-split/v1"


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


def parent_source() -> str:
    """取得冻结 R18 v2 评分源码，并校验发布候选的内容摘要。"""

    source = R18_INTEGRATED_POSITIVE_V2_SOURCE
    if hashlib.sha256(source.encode("utf-8")).hexdigest() != R18_INTEGRATED_POSITIVE_V2_SHA256:
        raise ValueError("R18 v2 父代源码摘要漂移")
    return source


def wealth_count(observation: Any) -> int:
    """按观察中本人暗牌与可选摸牌字段计数，不把同一张财神重复计算。"""

    wealth = observation.rule_state.wealth_god.code
    count = sum(tile.code == wealth for tile in observation.my_hand)
    if (observation.drawn_tile is not None
            and len(observation.my_hand) != observation.hand_counts[observation.seat]
            and observation.drawn_tile.code == wealth):
        count += 1
    if not 0 <= count <= 4:
        raise ValueError("玩家可见财神数超出规则上限")
    return count


def verify_prior_boundary() -> None:
    """确认旧宽泛教师失败，且其冻结状态没有覆盖本批窄条件。"""

    dataset = json.loads(PRIOR_DATASET.read_text(encoding="utf-8"))
    rows = dataset.get("rows")
    if not dataset.get("outcome_blind") or len(rows or []) != 32:
        raise ValueError("P30 结果盲冻结状态不完整")
    for row in rows:
        observation = row["request"]["observation"]
        wealth = observation["rule_state"]["wealth_god"]
        count = observation["my_hand"].count(wealth)
        if count >= 2 and row["features"]["pass_seven_pairs_shanten_after"] <= 1:
            raise ValueError("P30 已覆盖 P80 高财神近七对窄条件")
    teacher = json.loads(PRIOR_TEACHER.read_text(encoding="utf-8"))
    if teacher.get("development_states") != 16 or teacher.get("gate_passed") is not False:
        raise ValueError("P31 关闭结论与已冻结证据不符")


def sources() -> list[dict[str, Any]]:
    """冻结 64 个独立牌山根的四座位自然来源。"""

    return [
        {
            "mix": mix,
            "root_index": root,
            "focal_seat": seat,
            "source_root_id": f"{mix}:p80:{PANEL_SEED}:r{root:03d}",
            "source_id": f"{mix}:p80:{PANEL_SEED}:r{root:03d}:s{seat}",
        }
        for mix in MIXES for root in ROOTS for seat in SEATS
    ]


def source_path(row: Mapping[str, Any]) -> Path:
    return _project_file(_PROJECT_ROOT, OUT / "sources" / (str(row["source_id"]).replace(":", "-") + ".json"))


def _candidate_row(
    request: Any,
    source: Mapping[str, Any],
    scorer: ActionValueScorer,
) -> tuple[dict[str, Any] | None, str | None, tuple[str, ...]]:
    """应用冻结公开谓词；第三个返回值是已通过的累计漏斗阶段。"""

    observation = request.observation
    reached: list[str] = []
    if observation.phase not in ("response_peng", "response_chi"):
        return None, None, tuple(reached)
    reached.append("claim_response_window")
    if len(observation.melds[observation.seat]) != 0:
        return None, None, tuple(reached)
    reached.append("closed_claim_response_window")
    count = wealth_count(observation)
    if count < 2:
        return None, None, tuple(reached)
    reached.append("two_plus_wealth")

    view = build_scoring_view(request)
    facts_by_key = {item.action_key: item for item in view.actions}
    pass_facts = facts_by_key.get("pass")
    claim_facts = [
        item for item in view.actions if item.action_type in ("chi", "peng")
    ]
    if pass_facts is None or not claim_facts:
        return None, None, tuple(reached)
    reached.append("pass_and_claim_legal")
    if (
        pass_facts.standard_shanten_after is None
        or pass_facts.seven_pairs_shanten_after is None
        or pass_facts.seven_pairs_shanten_after > 1
    ):
        return None, None, tuple(reached)
    reached.append("pass_retains_seven_pairs_within_one_shanten")

    nonworsening_claims = [
        item for item in claim_facts
        if item.standard_shanten_after is not None
        and item.standard_shanten_after <= pass_facts.standard_shanten_after
        and item.seven_pairs_shanten_after is None
        and item.best_followup_discard is not None
    ]
    if not nonworsening_claims:
        return None, None, tuple(reached)
    reached.append("claim_nonworsening_standard_and_closes_seven_pairs")

    scored = scorer.score(view)
    if scored.status != "SCORED":
        return None, "R18_V2_" + scored.status + ":" + str(scored.reason), tuple(reached)
    entries = sorted(scored.entries, key=lambda item: (-item.score, item.action_key))
    if not entries:
        return None, "R18_V2_EMPTY_ENTRIES", tuple(reached)
    reference = entries[0]
    nonworsening_by_key = {item.action_key: item for item in nonworsening_claims}
    if reference.action_key not in nonworsening_by_key:
        return None, None, tuple(reached)
    reached.append("r18_v2_top_is_nonworsening_claim")
    pass_entry = next((entry for entry in entries if entry.action_key == "pass"), None)
    if pass_entry is None:
        return None, "R18_V2_SCORE_ACTION_FACT_MISMATCH", tuple(reached)
    reference_facts = nonworsening_by_key[reference.action_key]

    request_json = decision_request_to_json(request)
    table_id = str(observation.game_id).removeprefix("sitin-stage:")
    return {
        "schema": "r18-p80-high-wealth-near-seven-natural-row/1",
        "source": dict(source),
        "request": request_json,
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
        "family": reference_facts.action_type,
        "reference_action": reference.action_key,
        "intervention_action": "pass",
        "features": {
            "round_no": observation.round_no,
            "phase": observation.phase,
            "dealer_seat": observation.dealer_seat,
            "remaining_tile_count": observation.remaining_tile_count,
            "own_meld_count_before": len(observation.melds[observation.seat]),
            "wealth_count": count,
            "chain_count": observation.rule_state.chain_count,
            "chain_piao": observation.chain_piao,
            "baotou": observation.rule_state.baotou,
            "pass_standard_shanten_after": pass_facts.standard_shanten_after,
            "pass_seven_pairs_shanten_after": pass_facts.seven_pairs_shanten_after,
            "claim_standard_shanten_after": reference_facts.standard_shanten_after,
            "claim_standard_speed_gain": (
                pass_facts.standard_shanten_after - reference_facts.standard_shanten_after
            ),
            "claim_seven_pairs_shanten_after": reference_facts.seven_pairs_shanten_after,
            "claim_best_followup_discard": reference_facts.best_followup_discard,
            "reference_score": reference.score,
            "intervention_score": pass_entry.score,
            "r18_v2_score_margin": reference.score - pass_entry.score,
            "reference_trace": reference.trace,
            "intervention_trace": pass_entry.trace,
        },
    }, None, tuple(reached + ["eligible_high_wealth_near_seven_claim"])


def audit_requests(
    requests: list[Any], source: Mapping[str, Any], parent_source: str,
) -> dict[str, Any]:
    """每来源只保存第一条符合固定谓词的状态，避免运行产物膨胀。"""

    scorer = ActionValueScorer("r18-p80-r18-v2-" + str(source["source_id"]), parent_source)
    counts: Counter[str] = Counter()
    problems = []
    rows = []
    for request in requests:
        counts["focal_requests"] += 1
        row, problem, reached = _candidate_row(request, source, scorer)
        if problem is not None:
            problems.append(problem)
        for stage in reached:
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
    """运行一个来源单元的两桌 R18 v2 阶段并应用公开谓词。"""

    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    source_text = parent_source()
    plans = natural.build_seat_stage_plans(
        contract=contract, opponent=str(source["mix"]),
        root_index=int(source["root_index"]), focal_seat=int(source["focal_seat"]),
        panel_seed=PANEL_SEED,
    )
    requests: list[Any] = []
    stage = natural.run_arm_stage(
        arm="p80-r18-v2-high-wealth-near-seven-natural", plans=plans,
        candidate_scorer=ActionValueScorer(
            "r18-p80-trajectory-" + str(source["source_id"]), source_text,
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
        "audit": audit_requests(requests, source, source_text),
    }


def prepare() -> None:
    """在运行全新自然桌前冻结谓词、来源、暴露门和开发/复验规则。"""

    if OUT.exists():
        raise SystemExit("P80 目录已存在；拒绝覆盖")
    parent_source()
    verify_prior_boundary()
    OUT.mkdir(parents=True)
    (_project_file(_PROJECT_ROOT, OUT / "sources")).mkdir()
    authorization = batch.unified_document(
        batch_label=OUT.name,
        authorization_id="r18-p80-high-wealth-near-seven-claim-exposure-01",
        accounts={"tables_full": PLANNED_TABLES},
        issued_by="lead", issued_at_utc=search.utc_now(), legacy_alias=False,
    )
    authorization.update({
        "issuance_basis": "P31宽泛过牌规则失败；只检验其未覆盖的高财神近七对窄条件自然暴露",
        "scope": "H/M各32根、四焦点座、每来源两桌；R18 v2结果盲自然暴露",
        "max_model_calls": 0,
        "confirmation_roots": 0,
    })
    frozen_sources = sources()
    write_json(_project_file(_PROJECT_ROOT, OUT / "authorization.json"), authorization)
    write_json(_project_file(_PROJECT_ROOT, OUT / "sources.json"), {
        "schema": "r18-p80-high-wealth-near-seven-sources/1",
        "sources": frozen_sources,
    })
    tracked = [
        Path(__file__), Path(p16.__file__), Path(natural.__file__),
        CONTRACT, PARENT, PRIOR_DATASET, PRIOR_TEACHER,
        _project_file(_PROJECT_ROOT, OUT / "authorization.json"), _project_file(_PROJECT_ROOT, OUT / "sources.json"),
    ]
    write_json(_project_file(_PROJECT_ROOT, OUT / "manifest.json"), {
        "schema": "r18-p80-high-wealth-near-seven-manifest/1",
        "created_at_utc": search.utc_now(),
        "runtime": guard.capture(source_paths=tracked),
        "contract_sha256": digest(CONTRACT),
        "parent_sha256": digest(PARENT),
        "parent_score_source_sha256": R18_INTEGRATED_POSITIVE_V2_SHA256,
        "prior_p30_dataset_sha256": digest(PRIOR_DATASET),
        "prior_p31_result_sha256": digest(PRIOR_TEACHER),
        "panel_seed": PANEL_SEED,
        "mixes": list(MIXES), "root_indices": list(ROOTS),
        "focal_seats": list(SEATS), "sources": len(frozen_sources),
        "tables_per_source": TABLES_PER_SOURCE,
        "planned_tables": PLANNED_TABLES, "workers": WORKERS,
        "frozen_predicate": (
            "phase_in(response_peng,response_chi) and own_meld_count_is_zero and "
            "visible_wealth_count>=2 and pass_and_chi_or_peng_legal and "
            "pass.seven_pairs_shanten_after<=1 and "
            "claim.standard_shanten_after<=pass.standard_shanten_after and "
            "claim.seven_pairs_shanten_after_is_none and "
            "claim.best_followup_discard_is_not_none and r18_v2_top_is_that_claim"
        ),
        "predicate_inputs": (
            "依法可见DecisionRequest、合法动作、hangma同源普通型/七对向听及"
            "最佳后续弃牌、冻结R18 v2评分；不读取局或阶段结果"
        ),
        "family_strata": ["chi", "peng"],
        "minimum_visible_wealth_count": 2,
        "seven_pairs_max_shanten": 1,
        "independence_unit": "source_root_id（H/M+自然根）；四座位与两桌不增加n",
        "minimum_total_roots": MIN_TOTAL_ROOTS,
        "minimum_roots_per_mix": MIN_ROOTS_PER_MIX,
        "maximum_selected_roots_per_mix": MAX_SELECTED_ROOTS_PER_MIX,
        "seat_coverage_required": list(SEATS),
        "selection_salt": SELECTION_SALT,
        "split_salt": SPLIT_SALT,
        "split_rule": (
            "H/M各自最多取偶数个根且不超过16，合计至少24且每mix至少8；"
            "各mix内部按冻结哈希结果盲半分development/replication"
        ),
        "count_semantics": "raw_counts除focal_requests外均为累计通过漏斗计数",
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
        raise ValueError("P80 合同漂移")
    if manifest["parent_sha256"] != digest(PARENT):
        raise ValueError("P80 R18 v2父代文件漂移")
    if manifest["parent_score_source_sha256"] != R18_INTEGRATED_POSITIVE_V2_SHA256:
        raise ValueError("P80 R18 v2评分源码身份漂移")
    parent_source()
    verify_prior_boundary()
    if manifest["prior_p30_dataset_sha256"] != digest(PRIOR_DATASET):
        raise ValueError("P80 P30 冻结数据漂移")
    if manifest["prior_p31_result_sha256"] != digest(PRIOR_TEACHER):
        raise ValueError("P80 P31 教师结论漂移")
    guard.verify(manifest["runtime"])
    frozen = json.loads((_project_file(_PROJECT_ROOT, OUT / "sources.json")).read_text(encoding="utf-8"))["sources"]
    if frozen != sources():
        raise ValueError("P80 全新自然来源清单漂移")
    return manifest, frozen


def run() -> None:
    """并行执行 512 张新自然桌，支持断点续跑。"""

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
                raise ValueError("既有 P80 来源不完整：" + str(path))
            completed_tables += TABLES_PER_SOURCE
        else:
            pending.append(source)
    reservation = ledger.reserve(
        step_id="r18:p80-high-wealth-near-seven:natural", account="tables_full",
        amount=PLANNED_TABLES - completed_tables,
        note="全新R18 v2自然桌测量高财神近七对鸣牌/过牌窄条件的可达性",
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
                        raise RuntimeError("R18 v2 重评分失败：" + ";".join(result["audit"]["problems"][:3]))
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
        "schema": "r18-p80-high-wealth-near-seven-run-summary/1",
        "source_files": len(files), "actual_tables": actual,
        "failures": failures, "spent": ledger.account_summary(),
    })
    if failures or actual != PLANNED_TABLES or len(files) != len(frozen):
        raise RuntimeError("P80 全新自然暴露执行不完整")


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
        raise ValueError("P80 执行不完整")
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
    selected_counts = {
        mix: min(MAX_SELECTED_ROOTS_PER_MIX, len(pools[mix])) for mix in MIXES
    }
    selected_counts = {
        mix: count - count % 2 for mix, count in selected_counts.items()
    }
    seat_coverage = sorted({int(row["focal_physical_seat"]) for row in independent})
    passes_exposure = (
        sum(selected_counts.values()) >= MIN_TOTAL_ROOTS
        and all(selected_counts[mix] >= MIN_ROOTS_PER_MIX for mix in MIXES)
        and seat_coverage == list(SEATS)
    )
    selected = []
    if passes_exposure:
        for mix in MIXES:
            chosen = pools[mix][: selected_counts[mix]]
            for index, row in enumerate(chosen):
                item = dict(row)
                item["split"] = (
                    "development"
                    if index < selected_counts[mix] // 2
                    else "replication"
                )
                selected.append(item)
    selected.sort(key=lambda row: (
        row.get("split", ""), row["source"]["mix"],
        row["source"]["source_root_id"], row["request_sha256"],
    ))
    dataset = {
        "schema": "r18-p80-high-wealth-near-seven-dataset/1",
        "outcome_blind": True, "replication_labels_opened": False,
        "rows": selected,
    }
    by_mix = {
        mix: {
            "independent_roots": len(pools[mix]),
            "selected_roots": sum(row["source"]["mix"] == mix for row in selected),
            "development_roots": sum(
                row["source"]["mix"] == mix and row.get("split") == "development"
                for row in selected
            ),
            "replication_roots": sum(
                row["source"]["mix"] == mix and row.get("split") == "replication"
                for row in selected
            ),
        }
        for mix in MIXES
    }
    by_family = {
        family: {
            "independent_roots": sum(row["family"] == family for row in independent),
            "selected_roots": sum(row["family"] == family for row in selected),
            "development_roots": sum(
                row["family"] == family and row.get("split") == "development"
                for row in selected
            ),
            "replication_roots": sum(
                row["family"] == family and row.get("split") == "replication"
                for row in selected
            ),
        }
        for family in ("chi", "peng")
    }
    result = {
        "schema": "r18-p80-high-wealth-near-seven-result/1",
        "status": (
            "OPEN_DEVELOPMENT_CONFIRMATION" if passes_exposure
            else "INSUFFICIENT_NATURAL_EXPOSURE"
        ),
        "tables": PLANNED_TABLES,
        "source_units": len(frozen),
        "focal_requests": int(raw_counts["focal_requests"]),
        "raw_counts": dict(sorted(raw_counts.items())),
        "raw_eligible_windows": raw_eligible,
        "independent_roots": len(independent),
        "independent_focal_seat_coverage": seat_coverage,
        "by_mix": by_mix,
        "by_family": by_family,
        "selected_states": len(selected),
        "development_states": sum(row.get("split") == "development" for row in selected),
        "replication_states": sum(row.get("split") == "replication" for row in selected),
        "passes_natural_exposure_gate": passes_exposure,
        "replication_labels_opened": False,
        "model_calls": 0,
        "next": (
            "只对development状态运行32共同隐藏世界确认；复验状态保持封存"
            if passes_exposure else
            "按预登记自然暴露门关闭该窄假设，不用构造题补数"
        ),
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
