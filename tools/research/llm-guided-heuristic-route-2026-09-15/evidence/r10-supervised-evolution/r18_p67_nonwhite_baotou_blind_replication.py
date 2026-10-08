"""R18 P67：非财神建爆头候选的隐藏复验。

P64B 已在不打开复验根的前提下证明因果信号可在当前 P47 续打下复现，
P66B 已冻结候选源码并通过 377 点回归与 16 个开发目标的零桌预检。本程序
首次打开 P63 预留的 16 个复验根，先确认冻结候选在不看收益的公开状态上
选中预登记动作，再在 32 个全新共同隐藏世界中与立即胡配对复验。
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
import random
import statistics
import sys
from typing import Any, Mapping


HERE = Path(__file__).resolve().parent
ROUTE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15')
ROOT = _PROJECT_ROOT
for path in (_project_file(_PROJECT_ROOT, ROOT / "src"), _project_file(_PROJECT_ROOT, ROUTE / "tools"), HERE):
    sys.path.insert(0, str(path))

import confirmation_execution_identity as guard  # noqa: E402
import r18_p13_development_seven_pairs_teacher as p13  # noqa: E402
import r18_p63_nonwhite_baotou_natural_exposure as p63  # noqa: E402
import r18_p66b_nonwhite_baotou_candidate_preflight as p66b  # noqa: E402
import claim_counterfactual_pilot as core  # noqa: E402
import sitin_opportunities as opportunities  # noqa: E402
import sitin_natural_panel as natural  # noqa: E402
import sitin_search as search  # noqa: E402
import strong_seed_batch as batch  # noqa: E402
from hangma_bot.hangma.engine import HangmaRules  # noqa: E402
from hangma_bot.kernel.serialization import window_key_from_json  # noqa: E402
from hangma_bot.policy.action_value_policy import build_scoring_view  # noqa: E402
from hangma_bot.policy.action_value_seeds import ActionValueScorer  # noqa: E402


OUT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p67-nonwhite-baotou-blind-replication-01-20260923')
CONTRACT = p63.CONTRACT
PARENT = p63.PARENT
CANDIDATE = p66b.CANDIDATE
TRACE_KEY = p66b.TRACE_KEY
ROLLOUTS_PER_STATE = 32
WORKERS = 8
BOOTSTRAP_REPLICATES = 20_000
MIN_POSITIVE_STATES = 12
P63_RESULT = p63.OUT / "result.json"
P63_DATASET = p63.OUT / "dataset.json"
P66B_RESULT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p66b-nonwhite-baotou-candidate-preflight-01-20260923/result.json')
P66B_MANIFEST = p66b.OUT / "manifest.json"
P64B_RESULT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p64b-nonwhite-baotou-p47-continuation-audit-01-20260923/result.json')
P64B_MANIFEST = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p64b-nonwhite-baotou-p47-continuation-audit-01-20260923/manifest.json')
P64B_SCRIPT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18_p64b_nonwhite_baotou_p47_continuation_audit.py')


def write_json(path: Path, value: Any) -> None:
    """写入稳定、可复算的 UTF-8 JSON。"""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def natural_rows() -> list[dict[str, Any]]:
    """读取 P63 在收益揭示前冻结的 16 开发根与 16 复验根。"""

    result = json.loads(P63_RESULT.read_text(encoding="utf-8"))
    document = json.loads(P63_DATASET.read_text(encoding="utf-8"))
    rows = list(document["rows"])
    if not (
        result.get("status") == "OPEN_DEVELOPMENT_CONFIRMATION"
        and result.get("passes_natural_exposure_gate") is True
        and result.get("replication_labels_opened") is False
        and document.get("outcome_blind") is True
        and document.get("replication_labels_opened") is False
    ):
        raise ValueError("P67 只能消费预先保持复验盲态的 P63 自然数据集")
    if Counter(row["split"] for row in rows) != {
        "development": 16, "replication": 16,
    }:
        raise ValueError("P67 必须绑定 P63 冻结的 16 开发根与 16 复验根")
    if Counter(row["source"]["mix"] for row in rows) != {"H": 16, "M": 16}:
        raise ValueError("P67 H/M 自然根计数漂移")
    roots = [str(row["source"]["source_root_id"]) for row in rows]
    if len(roots) != len(set(roots)):
        raise ValueError("P67 来源根必须独立")
    if sorted({int(row["focal_physical_seat"]) for row in rows}) != [0, 1, 2, 3]:
        raise ValueError("P67 焦点座位覆盖漂移")
    return rows


def targets() -> list[dict[str, Any]]:
    """把 P63 的结果盲切分投影为可捕获目标，不重新选择样本。"""

    rows = natural_rows()
    counters: Counter[str] = Counter()
    result = []
    for row in rows:
        split = str(row["split"])
        counters[split] += 1
        source = row["source"]
        result.append({
            "target_id": "r18-p67-{0}-{1:02d}".format(
                split, counters[split],
            ),
            "split": split,
            "family": "hu_vs_nonwealth_baotou",
            "source": {
                "panel_seed": p63.PANEL_SEED,
                "source_id": source["source_id"],
                "source_root_id": source["source_root_id"],
                "mix": source["mix"],
                "root_index": source["root_index"],
                "focal_seat": source["focal_seat"],
                "table_no": row["table_no"],
                "table_id": row["table_id"],
            },
            "window_key": row["window_key"],
            "focal_physical_seat": row["focal_physical_seat"],
            "request_sha256": row["request_sha256"],
            "state_projection_sha256": row["state_projection_sha256"],
            "reference_action": row["reference_action"],
            "intervention_action": row["intervention_action"],
            "features": dict(row["features"]),
        })
    result.sort(key=lambda row: (
        row["split"], row["source"]["mix"],
        row["source"]["source_root_id"], row["request_sha256"],
    ))
    if Counter(row["split"] for row in result) != {
        "development": 16, "replication": 16,
    }:
        raise ValueError("P67 开发/复验切分计数错误")
    roots = [row["source"]["source_root_id"] for row in result]
    if len(roots) != len(set(roots)):
        raise ValueError("P67 来源根不独立")
    return result


def snapshot_path(target: Mapping[str, Any]) -> Path:
    return _project_file(_PROJECT_ROOT, OUT / "snapshots" / (str(target["target_id"]) + ".json"))


def rollout_path(target: Mapping[str, Any], index: int) -> Path:
    return _project_file(_PROJECT_ROOT, OUT / "rollouts" / "{0}-hidden-{1:02d}.json".format(
        target["target_id"], index,
    ))


def source_paths() -> list[Path]:
    """列出会改变目标、重放或标签语义的实现与冻结输入。"""

    return [
        Path(__file__), Path(p13.__file__), Path(p63.__file__), Path(p66b.__file__),
        CONTRACT, PARENT, CANDIDATE,
        p63.OUT / "manifest.json", P63_RESULT, P63_DATASET,
        P64B_SCRIPT, P64B_RESULT, P64B_MANIFEST, P66B_RESULT, P66B_MANIFEST,
    ]


def prepare() -> None:
    """在打开复验状态和生成收益标签前冻结候选、样本和通过门。"""

    if OUT.exists():
        raise SystemExit("P67 目录已存在；拒绝覆盖")
    p64b_result = json.loads(P64B_RESULT.read_text(encoding="utf-8"))
    p66b_result = json.loads(P66B_RESULT.read_text(encoding="utf-8"))
    if not (
        p64b_result.get("status") == "COMPLETE_P64B_NONWEALTH_BAOTOU_P47_CONTINUATION_AUDIT"
        and p64b_result.get("gate_passed") is True
        and p64b_result.get("decision") == "CONFIRM_P64_UNDER_P47_AND_OPEN_P67_REPLICATION"
        and p64b_result.get("replication_labels_opened") is False
    ):
        raise ValueError("P64B 未证明 P47 续打下的开发信号或复验盲态已破坏")
    if not (
        p66b_result.get("status") == "PASS_P66B_NONWEALTH_BAOTOU_CANDIDATE_PREFLIGHT"
        and p66b_result.get("decision") == "OPEN_P67_REPLICATION"
    ):
        raise ValueError("P66B 候选预检未通过")
    frozen = targets()
    replication = [row for row in frozen if row["split"] == "replication"]
    sample_keys = [
        "r18-p67-nonwhite-baotou-p47-blind-hidden-world-{0:02d}".format(index)
        for index in range(1, ROLLOUTS_PER_STATE + 1)
    ]
    planned_tables = len(replication) * len(sample_keys) * 2
    OUT.mkdir(parents=True)
    (_project_file(_PROJECT_ROOT, OUT / "snapshots")).mkdir()
    (_project_file(_PROJECT_ROOT, OUT / "rollouts")).mkdir()
    authorization = batch.unified_document(
        batch_label=OUT.name,
        authorization_id="r18-p67-nonwhite-baotou-blind-replication-01",
        accounts={
            "prefix_generation": len(replication),
            "tables_full": planned_tables,
        },
        issued_by="lead", issued_at_utc=search.utc_now(), legacy_alias=False,
    )
    authorization.update({
        "issuance_basis": "P64B在P47续打下通过开发复核；P66B冻结候选并通过零桌预检；P63的16个复验根至今未生成收益标签",
        "scope": "16复验根×32全新共同隐藏世界×立即胡/非财神建爆头；双臂续打显式绑定P47",
        "max_model_calls": 0,
        "confirmation_roots": 0,
    })
    write_json(_project_file(_PROJECT_ROOT, OUT / "authorization.json"), authorization)
    write_json(_project_file(_PROJECT_ROOT, OUT / "targets.json"), {
        "schema": "r18-p67-nonwhite-baotou-targets/1",
        "p63_dataset_sha256": digest(P63_DATASET),
        "targets": frozen,
        "replication_labels_opened_at_prepare": False,
    })
    write_json(_project_file(_PROJECT_ROOT, OUT / "manifest.json"), {
        "schema": "r18-p67-nonwhite-baotou-blind-replication-manifest/1",
        "created_at_utc": search.utc_now(),
        "runtime": guard.capture(source_paths=source_paths() + [
            _project_file(_PROJECT_ROOT, OUT / "authorization.json"), _project_file(_PROJECT_ROOT, OUT / "targets.json"),
        ]),
        "targets_sha256": digest(_project_file(_PROJECT_ROOT, OUT / "targets.json")),
        "parent_sha256": digest(PARENT),
        "candidate_sha256": digest(CANDIDATE),
        "contract_sha256": digest(CONTRACT),
        "natural_roots": len(frozen),
        "replication_states": len(replication),
        "rollouts_per_state": ROLLOUTS_PER_STATE,
        "sample_keys": sample_keys,
        "planned_tables": planned_tables,
        "workers": WORKERS,
        "sampling_unit": "自然来源根；共同隐藏世界不增加独立样本数",
        "sampling_scope": "依法可见公开状态一致的对手暗手与未消耗牌墙；不是历史后验",
        "continuation_parent": "P47；捕获前与每个工作子进程内都显式设置p13.PARENT",
        "primary_label": "nonwealth_baotou_minus_immediate_hu_current_round_settlement",
        "replication_gate": {
            "state_mean_bootstrap_95_lower_strictly_greater_than": 0.0,
            "minimum_positive_states": MIN_POSITIVE_STATES,
            "minimum_leave_one_root_out_mean_strictly_greater_than": 0.0,
            "each_mix_mean_strictly_greater_than": 0.0,
            "mechanical_success_required": True,
            "candidate_selects_registered_action_in_all_states": True,
        },
        "replication_labels_opened_at_prepare": False,
        "model_calls": 0,
        "release_eligible": False,
    })
    print(json.dumps({
        "status": "PREPARED", "natural_roots": len(frozen),
        "replication_states": len(replication),
        "planned_tables": planned_tables,
    }, ensure_ascii=False))


def verify() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """核对冻结切分、父代、合同和运行实现未漂移。"""

    manifest = json.loads((_project_file(_PROJECT_ROOT, OUT / "manifest.json")).read_text(encoding="utf-8"))
    checks = {
        "P67目标": (manifest["targets_sha256"], digest(_project_file(_PROJECT_ROOT, OUT / "targets.json"))),
        "P47父代": (manifest["parent_sha256"], digest(PARENT)),
        "P65候选": (manifest["candidate_sha256"], digest(CANDIDATE)),
        "合同": (manifest["contract_sha256"], digest(CONTRACT)),
    }
    for label, (expected, actual) in checks.items():
        if expected != actual:
            raise ValueError(label + "漂移")
    guard.verify(manifest["runtime"])
    document = json.loads((_project_file(_PROJECT_ROOT, OUT / "targets.json")).read_text(encoding="utf-8"))
    if document.get("replication_labels_opened_at_prepare") is not False:
        raise ValueError("P67 准备时复验标签必须保持封存")
    frozen = list(document["targets"])
    if frozen != targets():
        raise ValueError("P67 目标不能从 P63 结果盲数据集重建")
    return manifest, frozen


def trace_without_new_mapping(trace: Mapping[str, Any]) -> dict[str, Any]:
    """移除 P65 唯一新增解释键，以核对 P47 解释逐点等价。"""

    return {key: value for key, value in trace.items() if key != TRACE_KEY}


def exact_request(target: Mapping[str, Any]) -> Any:
    """从新捕获的复验快照重建精确公开请求，不读取收益。"""

    snapshot = json.loads(snapshot_path(target).read_text(encoding="utf-8"))
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    rules = HangmaRules(core.rule_config_from_contract(contract))
    runtime = opportunities.build_real_runtime(
        rules_config=rules.config,
        rounds_per_game=int(snapshot["match_spec"]["rounds_per_game"]),
        seed=int(snapshot["match_spec"]["seed"]),
        scenario_id=str(snapshot["match_spec"]["scenario_id"]),
    )
    engine, world = opportunities.rebuild_world(
        rules=rules, snapshot=snapshot, value_limits=p13.LIMITS, runtime=runtime,
    )
    wanted = window_key_from_json(target["window_key"])
    decision = next(
        item for item in engine.frame(world).decisions if item.window_key == wanted
    )
    analysis = rules.analyze(decision.observation, value_limits=p13.LIMITS)
    request = opportunities.real_window_request(
        decision=decision, analysis=analysis,
        match_id=str(snapshot["match_spec"]["match_id"]),
        config=opportunities._driver_config(), now_monotonic=lambda: 800.0,
    )
    capture = p13.ExactStateCapture(target)
    if capture(request) is None or capture.hits != 1:
        raise ValueError("P67 复验请求未精确命中冻结状态")
    return request


def score_rows(scorer: ActionValueScorer, request: Any) -> list[Any]:
    """经正式评分视图运行受限源码并返回稳定排序。"""

    scored = scorer.score(build_scoring_view(request, value_limits=p13.LIMITS))
    if scored.status != "SCORED":
        raise ValueError("候选 ABSTAIN：" + str(scored.reason))
    return sorted(scored.entries, key=lambda entry: (-entry.score, entry.action_key))


def check_candidate_selection(target: Mapping[str, Any]) -> dict[str, Any]:
    """在不看收益时核对候选仅提升预登记动作并将其置顶。"""

    request = exact_request(target)
    parent = ActionValueScorer("r18-p67-parent", PARENT.read_text(encoding="utf-8"))
    candidate = ActionValueScorer(
        "r18-p67-candidate", CANDIDATE.read_text(encoding="utf-8")
    )
    before = score_rows(parent, request)
    after = score_rows(candidate, request)
    before_by_key = {entry.action_key: entry for entry in before}
    after_by_key = {entry.action_key: entry for entry in after}
    target_key = str(target["intervention_action"])
    changed = sorted(
        key for key in before_by_key
        if after_by_key[key].score != before_by_key[key].score
    )
    mappings = [entry.trace.get(TRACE_KEY) for entry in after]
    mapping_complete = all(isinstance(item, Mapping) for item in mappings)
    trigger_all = mapping_complete and all(
        item.get("triggered") is True for item in mappings
    )
    target_mapping = after_by_key[target_key].trace.get(TRACE_KEY) or {}
    trace_parent_exact = all(
        trace_without_new_mapping(entry.trace)
        == before_by_key[entry.action_key].trace
        for entry in after
    )
    mechanism_exact = bool(
        before[0].action_key == "hu"
        and after[0].action_key == target_key
        and changed == [target_key]
        and after_by_key[target_key].score == before_by_key["hu"].score + 1.0
        and trigger_all
        and target_mapping.get("target_action") == target_key
        and target_mapping.get("score_capacity")
        == target["features"]["baotou_score_capacity"]
        and target_mapping.get("support_remaining")
        == target["features"]["baotou_support_remaining"]
        and target_mapping.get("min_route_fan")
        == target["features"]["baotou_min_fan"]
        and trace_parent_exact
    )
    return {
        "target_id": target["target_id"],
        "parent_top": before[0].action_key,
        "candidate_top": after[0].action_key,
        "expected_target": target_key,
        "changed_scores": changed,
        "trace_parent_exact": trace_parent_exact,
        "mechanism_exact": mechanism_exact,
    }


def capture() -> None:
    """捕获 16 个复验根，并在运行收益标签前核对候选选择。"""

    manifest, frozen = verify()
    replication = [row for row in frozen if row["split"] == "replication"]
    authorization = json.loads((_project_file(_PROJECT_ROOT, OUT / "authorization.json")).read_text(encoding="utf-8"))
    natural.require_authorization(authorization)
    ledger = search.ActionValueLedger.load(
        _project_file(_PROJECT_ROOT, OUT / "ledger.json"),
        authorized_budgets=search.av_ledger_budgets_from_authorization(authorization),
    )
    pending = [row for row in replication if not snapshot_path(row).exists()]
    reservation = ledger.reserve(
        step_id="r18:p67-nonwealth-baotou-replication:capture",
        account="prefix_generation", amount=len(pending),
        note="16个非财神建爆头复验根的P47精确合法前缀捕获",
    )
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    p13.PARENT = PARENT
    completed = 0
    failures = []
    try:
        for target in pending:
            try:
                snapshot = p13.capture_one(target, contract)
                snapshot["capture"]["consumer"] = "R18 P67 nonwealth baotou blind replication"
                write_json(snapshot_path(target), snapshot)
                completed += 1
                print(json.dumps({
                    "captured": sum(snapshot_path(row).exists() for row in replication),
                    "planned": len(replication),
                }, ensure_ascii=False), flush=True)
            except Exception as exc:  # noqa: BLE001
                failures.append({
                    "target_id": target["target_id"],
                    "error": type(exc).__name__ + ": " + str(exc),
                })
    finally:
        ledger.settle(reservation, actual=completed, note="按成功捕获的合法前缀计")
    selection_rows = []
    if not failures and all(snapshot_path(row).exists() for row in replication):
        for target in replication:
            try:
                selection_rows.append(check_candidate_selection(target))
            except Exception as exc:  # noqa: BLE001
                failures.append({
                    "target_id": target["target_id"],
                    "selection_error": type(exc).__name__ + ": " + str(exc),
                })
    selection_ok = bool(
        len(selection_rows) == len(replication)
        and all(row["mechanism_exact"] for row in selection_rows)
    )
    write_json(_project_file(_PROJECT_ROOT, OUT / "candidate-selection.json"), {
        "schema": "r18-p67-nonwhite-baotou-candidate-selection/1",
        "candidate_sha256": digest(CANDIDATE),
        "selection_ok": selection_ok,
        "rows": selection_rows,
        "outcome_labels_opened": False,
    })
    write_json(_project_file(_PROJECT_ROOT, OUT / "capture-summary.json"), {
        "schema": "r18-p67-nonwhite-baotou-capture-summary/1",
        "captured": sum(snapshot_path(row).exists() for row in replication),
        "planned": manifest["replication_states"], "failures": failures,
        "candidate_selection_ok": selection_ok,
        "spent": ledger.account_summary(),
    })
    if failures or not all(snapshot_path(row).exists() for row in replication):
        raise RuntimeError("P67 复验状态捕获或候选选择核对不完整")
    if not selection_ok:
        raise RuntimeError("P67 冻结候选未在全部复验状态精确选择预登记动作")


def execute_rollout(
    target: Mapping[str, Any], index: int, sample_key: str,
) -> dict[str, Any]:
    """复用已验证的 P13 公开状态一致双臂执行。"""

    p13.OUT = OUT
    p13.PARENT = PARENT
    row = p13.execute_rollout(target, index, sample_key)
    row["schema"] = "r18-p67-nonwhite-baotou-replication-rollout/1"
    row["family"] = target["family"]
    row["split"] = target["split"]
    return row


def run() -> None:
    """并行执行 16×32 个复验根的共同隐藏世界配对。"""

    manifest, frozen = verify()
    replication = [row for row in frozen if row["split"] == "replication"]
    summary = json.loads((_project_file(_PROJECT_ROOT, OUT / "capture-summary.json")).read_text(encoding="utf-8"))
    if (
        summary["failures"]
        or summary["captured"] != manifest["replication_states"]
        or summary["candidate_selection_ok"] is not True
    ):
        raise ValueError("P67 复验前缀未完整捕获或候选选择未通过")
    authorization = json.loads((_project_file(_PROJECT_ROOT, OUT / "authorization.json")).read_text(encoding="utf-8"))
    natural.require_authorization(authorization)
    ledger = search.ActionValueLedger.load(
        _project_file(_PROJECT_ROOT, OUT / "ledger.json"),
        authorized_budgets=search.av_ledger_budgets_from_authorization(authorization),
    )
    pending = []
    completed_tables = 0
    for target in replication:
        for index, key in enumerate(manifest["sample_keys"], 1):
            path = rollout_path(target, index)
            if path.exists():
                row = json.loads(path.read_text(encoding="utf-8"))
                if not row.get("mechanical_ok"):
                    raise ValueError("既有 P67 配对机械条件失败：" + str(path))
                completed_tables += 2
            else:
                pending.append((target, index, key))
    reservation = ledger.reserve(
        step_id="r18:p67-nonwealth-baotou-replication:run", account="tables_full",
        amount=manifest["planned_tables"] - completed_tables,
        note="16复验根×32共同隐藏世界×立即胡/非财神建爆头",
    )
    failures = []
    executed = 0
    usage_unknown = False
    try:
        with concurrent.futures.ProcessPoolExecutor(max_workers=manifest["workers"]) as pool:
            futures = {
                pool.submit(execute_rollout, target, index, key): (target, index)
                for target, index, key in pending
            }
            for future in concurrent.futures.as_completed(futures):
                target, index = futures[future]
                row = None
                try:
                    row = future.result()
                    if not row["mechanical_ok"]:
                        raise RuntimeError("P67 配对机械条件失败")
                    write_json(rollout_path(target, index), row)
                    executed += 2
                    completed_tables += 2
                    if completed_tables % 64 == 0:
                        print(json.dumps({
                            "completed_tables": completed_tables,
                            "planned_tables": manifest["planned_tables"],
                        }, ensure_ascii=False), flush=True)
                except Exception as exc:  # noqa: BLE001
                    if row is None:
                        usage_unknown = True
                    failures.append({
                        "target_id": target["target_id"], "rollout_index": index,
                        "error": type(exc).__name__ + ": " + str(exc),
                    })
    finally:
        if usage_unknown:
            ledger.settle(reservation, usage_unknown=True, note="子进程未返回；保守结算")
        else:
            ledger.settle(reservation, actual=executed, note="按成功两臂桌数结算")
    files = list((_project_file(_PROJECT_ROOT, OUT / "rollouts")).glob("*.json"))
    write_json(_project_file(_PROJECT_ROOT, OUT / "run-summary.json"), {
        "schema": "r18-p67-nonwhite-baotou-run-summary/1",
        "rollout_files": len(files), "actual_tables": len(files) * 2,
        "failures": failures, "spent": ledger.account_summary(),
    })
    if failures or len(files) * 2 != manifest["planned_tables"]:
        raise RuntimeError("P67 非财神建爆头复验执行不完整")


def bootstrap_interval(values: list[float]) -> tuple[float, float]:
    """对自然基础状态均值做确定性 bootstrap 95% 区间。"""

    rng = random.Random(2026092367)
    means = []
    for _ in range(BOOTSTRAP_REPLICATES):
        means.append(statistics.fmean(rng.choice(values) for _ in values))
    means.sort()
    return (
        means[int(0.025 * len(means))],
        means[int(0.975 * len(means)) - 1],
    )


def analyze() -> None:
    """按 16 个预留自然根等权裁定；正值表示非财神建爆头优于立即胡。"""

    manifest, frozen = verify()
    replication = [row for row in frozen if row["split"] == "replication"]
    summary = json.loads((_project_file(_PROJECT_ROOT, OUT / "run-summary.json")).read_text(encoding="utf-8"))
    if summary["failures"] or summary["actual_tables"] != manifest["planned_tables"]:
        raise ValueError("P67 复验执行不完整")
    selection = json.loads((_project_file(_PROJECT_ROOT, OUT / "candidate-selection.json")).read_text(encoding="utf-8"))
    if selection.get("selection_ok") is not True:
        raise ValueError("P67 候选选择未通过")
    states = []
    all_mechanical = True
    for target in replication:
        rows = [
            json.loads(rollout_path(target, index).read_text(encoding="utf-8"))
            for index in range(1, ROLLOUTS_PER_STATE + 1)
        ]
        mechanical = all(row["mechanical_ok"] for row in rows)
        all_mechanical = all_mechanical and mechanical
        direct = [
            row["focal_current_round_settlement_delta"]
            for row in rows
        ]
        full = [
            row["focal_remaining_table_score"]["delta"]
            for row in rows
        ]
        states.append({
            "target_id": target["target_id"], "source": target["source"],
            "features": target["features"],
            "reference_action": target["reference_action"],
            "intervention_action": target["intervention_action"],
            "mechanical_ok": mechanical,
            "mean_baotou_minus_hu_current_round_settlement": statistics.fmean(direct),
            "mean_remaining_table_score_delta": statistics.fmean(full),
            "positive_hidden_worlds": sum(value > 0 for value in direct),
            "zero_hidden_worlds": sum(value == 0 for value in direct),
            "negative_hidden_worlds": sum(value < 0 for value in direct),
            "current_round_settlement_values": direct,
            "terminal_transitions": dict(sorted(Counter(
                row["reference"]["terminal"] + "->" + row["intervention"]["terminal"]
                for row in rows
            ).items())),
        })
    values = [
        row["mean_baotou_minus_hu_current_round_settlement"] for row in states
    ]
    low, high = bootstrap_interval(values)
    leave_one_out = {}
    for row in states:
        root = str(row["source"]["source_root_id"])
        remaining = [
            value for item, value in zip(states, values)
            if str(item["source"]["source_root_id"]) != root
        ]
        leave_one_out[root] = statistics.fmean(remaining)
    positive = sum(value > 0 for value in values)
    mix_means = {
        mix: statistics.fmean(
            value for row, value in zip(states, values)
            if row["source"]["mix"] == mix
        )
        for mix in ("H", "M")
    }
    gate_passed = bool(
        all_mechanical
        and selection.get("selection_ok") is True
        and statistics.fmean(values) > 0 and low > 0
        and positive >= MIN_POSITIVE_STATES
        and min(leave_one_out.values()) > 0
        and min(mix_means.values()) > 0
    )
    aggregate = {
        "mean_baotou_minus_hu_current_round_settlement": statistics.fmean(values),
        "bootstrap_95": [low, high],
        "positive_states": positive,
        "zero_states": sum(value == 0 for value in values),
        "negative_states": sum(value < 0 for value in values),
        "minimum_required_positive_states": MIN_POSITIVE_STATES,
        "leave_one_source_root_out_mean": leave_one_out,
        "minimum_leave_one_source_root_out_mean": min(leave_one_out.values()),
        "mean_by_mix": mix_means,
    }
    result = {
        "schema": "r18-p67-nonwhite-baotou-blind-replication-result/1",
        "status": (
            "PASS_P67_NONWEALTH_BAOTOU_BLIND_REPLICATION"
            if gate_passed else "FAIL_P67_NONWEALTH_BAOTOU_BLIND_REPLICATION"
        ),
        "mechanical_ok": all_mechanical,
        "natural_roots": manifest["natural_roots"],
        "replication_states": len(states),
        "rollouts": len(states) * ROLLOUTS_PER_STATE,
        "tables": len(states) * ROLLOUTS_PER_STATE * 2,
        "states": states, "aggregate": aggregate,
        "passes_replication_gate": gate_passed,
        "candidate_sha256": digest(CANDIDATE),
        "decision": (
            "OPEN_P68_TABLE_SAFETY" if gate_passed
            else "REJECT_P65_AFTER_BLIND_REPLICATION"
        ),
        "replication_labels_opened": True,
        "next": (
            "进入候选对P47的全桌配对非劣安全屏；不因强机会局部收益直接注册父代"
            if gate_passed else
            "保持P47并拒绝P65；不得根据已打开的复验标签追加阈值"
        ),
        "selection_eligible": gate_passed,
        "release_eligible": False,
    }
    write_json(_project_file(_PROJECT_ROOT, OUT / "result.json"), result)
    print(json.dumps({
        "status": result["status"], "mechanical_ok": all_mechanical,
        "aggregate": aggregate, "gate_passed": gate_passed,
        "decision": result["decision"], "replication_labels_opened": True,
    }, ensure_ascii=False, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("prepare", "capture", "run", "analyze"))
    command = parser.parse_args().command
    if command == "prepare":
        prepare()
    elif command == "capture":
        capture()
    elif command == "run":
        run()
    else:
        analyze()


if __name__ == "__main__":
    main()
