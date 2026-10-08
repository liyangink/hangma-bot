"""R18 P35：双财神留爆头候选的九个自然隐藏根准入。"""

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
import r18_p32_two_wealth_baotou_rare_teacher as p32  # noqa: E402
import r18_p34_two_wealth_candidate_preflight as p34  # noqa: E402
import sitin_natural_panel as natural  # noqa: E402
import sitin_search as search  # noqa: E402
import strong_seed_batch as batch  # noqa: E402
from hangma_bot.policy.action_value_policy import build_scoring_view  # noqa: E402
from hangma_bot.policy.action_value_seeds import ActionValueScorer  # noqa: E402


OUT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p35-two-wealth-hidden-admission-01-20260922')
CONTRACT = p32.CONTRACT
PARENT = p32.PARENT
CANDIDATE = p34.CANDIDATE
P32_MANIFEST = p32.OUT / "manifest.json"
P32_TARGETS = p32.OUT / "targets.json"
P32_RESULT = p32.OUT / "result.json"
P34_MANIFEST = p34.OUT / "manifest.json"
P34_RESULT = p34.OUT / "result.json"
ROLLOUTS_PER_STATE = 32
WORKERS = 8
BOOTSTRAP_REPLICATES = 20_000
MIN_POSITIVE_STATES = 7


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def targets() -> list[dict[str, Any]]:
    """只返回 P32 预留且在候选冻结后才允许使用的九个隐藏根。"""

    document = json.loads(P32_TARGETS.read_text(encoding="utf-8"))
    rows = [dict(row) for row in document["targets"] if row["split"] == "hidden"]
    if len(rows) != 9:
        raise ValueError("P35 必须恰有九个 P32 隐藏根")
    mixes = Counter(row["source"]["mix"] for row in rows)
    if mixes != {"H": 5, "M": 4}:
        raise ValueError("P35 隐藏根 H/M 配比漂移")
    roots = [(row["source"]["batch"], row["source"]["source_root_id"]) for row in rows]
    if len(roots) != len(set(roots)):
        raise ValueError("P35 隐藏来源根不独立")
    return sorted(rows, key=lambda row: row["target_id"])


def snapshot_path(target: Mapping[str, Any]) -> Path:
    return _project_file(_PROJECT_ROOT, OUT / "snapshots" / (str(target["target_id"]) + ".json"))


def rollout_path(target: Mapping[str, Any], index: int) -> Path:
    return _project_file(_PROJECT_ROOT, OUT / "rollouts" / "{0}-hidden-world-{1:02d}.json".format(
        target["target_id"], index,
    ))


def source_paths() -> list[Path]:
    return [
        Path(__file__), Path(p13.__file__), Path(p32.__file__), Path(p34.__file__),
        CONTRACT, PARENT, CANDIDATE,
        P32_MANIFEST, P32_TARGETS, P32_RESULT, P34_MANIFEST, P34_RESULT,
    ]


def prepare() -> None:
    """在捕获或生成任何隐藏收益前冻结九根、隐藏世界和统计门。"""

    if OUT.exists():
        raise SystemExit("P35 目录已存在；拒绝覆盖")
    p34_result = json.loads(P34_RESULT.read_text(encoding="utf-8"))
    if p34_result.get("decision") != "OPEN_P35_HIDDEN_ADMISSION":
        raise ValueError("P34 未开放隐藏验收")
    if p34_result.get("hidden_labels_opened") is not False:
        raise ValueError("P34 已错误打开隐藏标签")
    frozen = targets()
    sample_keys = [
        "r18-p35-two-wealth-hidden-world-{0:02d}".format(index)
        for index in range(1, ROLLOUTS_PER_STATE + 1)
    ]
    planned_tables = len(frozen) * len(sample_keys) * 2
    OUT.mkdir(parents=True)
    (_project_file(_PROJECT_ROOT, OUT / "snapshots")).mkdir()
    (_project_file(_PROJECT_ROOT, OUT / "rollouts")).mkdir()
    authorization = batch.unified_document(
        batch_label=OUT.name,
        authorization_id="r18-p35-two-wealth-hidden-admission-01",
        accounts={"prefix_generation": len(frozen), "tables_full": planned_tables},
        issued_by="lead", issued_at_utc=search.utc_now(), legacy_alias=False,
    )
    authorization.update({
        "issuance_basis": "P34候选已冻结并通过开发、回退和父代覆盖保持预检",
        "scope": "九个预留自然根×32个公开状态一致共同隐藏世界×立即胡/飘白",
        "max_model_calls": 0,
        "confirmation_roots": len(frozen),
    })
    write_json(_project_file(_PROJECT_ROOT, OUT / "authorization.json"), authorization)
    write_json(_project_file(_PROJECT_ROOT, OUT / "targets.json"), {
        "schema": "r18-p35-two-wealth-hidden-targets/1",
        "source_targets_sha256": digest(P32_TARGETS),
        "targets": frozen,
        "labels_opened_after_candidate_freeze": True,
    })
    write_json(_project_file(_PROJECT_ROOT, OUT / "manifest.json"), {
        "schema": "r18-p35-two-wealth-hidden-admission-manifest/1",
        "created_at_utc": search.utc_now(),
        "runtime": guard.capture(source_paths=source_paths() + [
            _project_file(_PROJECT_ROOT, OUT / "authorization.json"), _project_file(_PROJECT_ROOT, OUT / "targets.json"),
        ]),
        "targets_sha256": digest(_project_file(_PROJECT_ROOT, OUT / "targets.json")),
        "candidate_sha256": digest(CANDIDATE),
        "parent_sha256": digest(PARENT),
        "p34_result_sha256": digest(P34_RESULT),
        "hidden_states": len(frozen),
        "rollouts_per_state": ROLLOUTS_PER_STATE,
        "sample_keys": sample_keys,
        "planned_tables": planned_tables,
        "workers": WORKERS,
        "sampling_unit": "P32预留的独立自然来源根；共同隐藏世界不增加独立样本数",
        "primary_label": "piao_minus_immediate_hu_current_round_settlement",
        "gate": {
            "all_candidate_actions_must_equal_frozen_intervention": True,
            "state_mean_bootstrap_95_lower_strictly_greater_than": 0.0,
            "minimum_positive_states": MIN_POSITIVE_STATES,
            "minimum_leave_one_root_out_mean_strictly_greater_than": 0.0,
            "mechanical_success_required": True,
        },
        "model_calls": 0,
        "release_eligible": False,
    })
    print(json.dumps({
        "status": "P35_PREPARED", "hidden_states": len(frozen),
        "planned_tables": planned_tables,
    }, ensure_ascii=False))


def correct_authorization() -> None:
    """在零执行前提下把误写的签发者修为统一授权器认可的 ``lead``。"""

    if any((_project_file(_PROJECT_ROOT, OUT / "snapshots")).glob("*.json")) or any((_project_file(_PROJECT_ROOT, OUT / "rollouts")).glob("*.json")):
        raise RuntimeError("已有隐藏快照或配对结果，不得修订授权元数据")
    if (_project_file(_PROJECT_ROOT, OUT / "ledger.json")).exists() or (_project_file(_PROJECT_ROOT, OUT / "capture-summary.json")).exists():
        raise RuntimeError("已有预算账本或捕获摘要，不得修订授权元数据")
    authorization_path = _project_file(_PROJECT_ROOT, OUT / "authorization.json")
    manifest_path = _project_file(_PROJECT_ROOT, OUT / "manifest.json")
    old_authorization_sha256 = digest(authorization_path)
    old_manifest_sha256 = digest(manifest_path)
    authorization = json.loads(authorization_path.read_text(encoding="utf-8"))
    if authorization.get("issued_by") != "root":
        raise RuntimeError("P35 授权签发者不是待修复的 root")
    authorization["issued_by"] = "lead"
    authorization["correction"] = (
        "首次捕获在创建账本或桌赛前因 issuer_untrusted fail-closed；"
        "只把签发者改为仓库统一受信角色 lead"
    )
    write_json(authorization_path, authorization)
    correction_path = _project_file(_PROJECT_ROOT, OUT / "authorization-correction.json")
    write_json(correction_path, {
        "schema": "r18-p35-authorization-correction/1",
        "old_authorization_sha256": old_authorization_sha256,
        "new_authorization_sha256": digest(authorization_path),
        "old_manifest_sha256": old_manifest_sha256,
        "first_attempt_status": "REFUSED_BEFORE_LEDGER_OR_TABLE_START",
        "first_attempt_error": "issuer_untrusted: root not in trusted issuers ['lead']",
        "snapshots_before_correction": 0,
        "rollouts_before_correction": 0,
        "candidate_changed": False,
        "targets_changed": False,
        "gate_changed": False,
    })
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["runtime"] = guard.capture(source_paths=source_paths() + [
        authorization_path, _project_file(_PROJECT_ROOT, OUT / "targets.json"), correction_path,
    ])
    manifest["authorization_correction_sha256"] = digest(correction_path)
    write_json(manifest_path, manifest)
    print(json.dumps({
        "status": "P35_AUTHORIZATION_CORRECTED",
        "issued_by": authorization["issued_by"],
        "snapshots": 0, "rollouts": 0,
    }, ensure_ascii=False))


def verify() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """核对候选、目标、判据与运行实现没有漂移。"""

    manifest = json.loads((_project_file(_PROJECT_ROOT, OUT / "manifest.json")).read_text(encoding="utf-8"))
    checks = {
        "P35目标": (manifest["targets_sha256"], digest(_project_file(_PROJECT_ROOT, OUT / "targets.json"))),
        "P33候选": (manifest["candidate_sha256"], digest(CANDIDATE)),
        "P5父代": (manifest["parent_sha256"], digest(PARENT)),
        "P34结果": (manifest["p34_result_sha256"], digest(P34_RESULT)),
    }
    for label, (expected, actual) in checks.items():
        if expected != actual:
            raise ValueError(label + "漂移")
    guard.verify(manifest["runtime"])
    document = json.loads((_project_file(_PROJECT_ROOT, OUT / "targets.json")).read_text(encoding="utf-8"))
    if document["targets"] != targets():
        raise ValueError("P35 隐藏目标不能从 P32 冻结切分重建")
    return manifest, list(document["targets"])


def capture() -> None:
    """捕获九个隐藏自然根并验证冻结候选确实选择飘财神。"""

    manifest, frozen = verify()
    authorization = json.loads((_project_file(_PROJECT_ROOT, OUT / "authorization.json")).read_text(encoding="utf-8"))
    natural.require_authorization(authorization)
    ledger = search.ActionValueLedger.load(
        _project_file(_PROJECT_ROOT, OUT / "ledger.json"),
        authorized_budgets=search.av_ledger_budgets_from_authorization(authorization),
    )
    pending = [row for row in frozen if not snapshot_path(row).exists()]
    reservation = ledger.reserve(
        step_id="r18:p35-two-wealth:capture", account="prefix_generation",
        amount=len(pending), note="九个预留隐藏根的P5精确合法前缀捕获",
    )
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    parent = ActionValueScorer("r18-p35-capture-parent", PARENT.read_text(encoding="utf-8"))
    candidate = ActionValueScorer(
        "r18-p35-capture-candidate", CANDIDATE.read_text(encoding="utf-8")
    )
    completed = 0
    failures = []
    action_checks = []
    try:
        for target in pending:
            try:
                snapshot = p13.capture_one(target, contract)
                snapshot["capture"]["consumer"] = "R18 P35 two-wealth hidden admission"
                request = p34.request_from_snapshot(target, snapshot)
                checked = p34.check_view(
                    label=target["target_id"], view=build_scoring_view(request),
                    parent=parent, candidate=candidate,
                )
                if (
                    checked["expected_target"] != target["intervention_action"]
                    or checked["candidate_top"] != target["intervention_action"]
                ):
                    raise ValueError("候选未选择冻结飘财神动作")
                write_json(snapshot_path(target), snapshot)
                action_checks.append(checked)
                completed += 1
                print(json.dumps({
                    "captured": sum(snapshot_path(row).exists() for row in frozen),
                    "planned": len(frozen),
                }, ensure_ascii=False), flush=True)
            except Exception as exc:  # noqa: BLE001
                failures.append({
                    "target_id": target["target_id"],
                    "error": type(exc).__name__ + ": " + str(exc),
                })
    finally:
        ledger.settle(reservation, actual=completed, note="按成功捕获并通过候选动作核验的根计")
    write_json(_project_file(_PROJECT_ROOT, OUT / "capture-summary.json"), {
        "schema": "r18-p35-two-wealth-hidden-capture-summary/1",
        "captured": sum(snapshot_path(row).exists() for row in frozen),
        "planned": manifest["hidden_states"],
        "candidate_action_checks": action_checks,
        "failures": failures,
        "spent": ledger.account_summary(),
    })
    if failures or not all(snapshot_path(row).exists() for row in frozen):
        raise RuntimeError("P35 隐藏根捕获或候选动作核验不完整")


def execute_rollout(
    target: Mapping[str, Any], index: int, sample_key: str,
) -> dict[str, Any]:
    """在共同隐藏世界中比较冻结候选动作与 P5 的立即胡。"""

    p13.OUT = OUT
    row = p13.execute_rollout(target, index, sample_key)
    row["schema"] = "r18-p35-two-wealth-hidden-rollout/1"
    row["family"] = target["family"]
    row["split"] = "hidden_confirmation"
    return row


def run() -> None:
    """并行执行九根、每根三十二个共同隐藏世界的双臂配对。"""

    manifest, frozen = verify()
    capture_summary = json.loads((_project_file(_PROJECT_ROOT, OUT / "capture-summary.json")).read_text(encoding="utf-8"))
    if (
        capture_summary["failures"]
        or capture_summary["captured"] != manifest["hidden_states"]
        or len(capture_summary["candidate_action_checks"]) != manifest["hidden_states"]
    ):
        raise ValueError("P35 隐藏根未完整捕获或候选动作未全部核验")
    authorization = json.loads((_project_file(_PROJECT_ROOT, OUT / "authorization.json")).read_text(encoding="utf-8"))
    natural.require_authorization(authorization)
    ledger = search.ActionValueLedger.load(
        _project_file(_PROJECT_ROOT, OUT / "ledger.json"),
        authorized_budgets=search.av_ledger_budgets_from_authorization(authorization),
    )
    pending = []
    completed_tables = 0
    for target in frozen:
        for index, key in enumerate(manifest["sample_keys"], 1):
            path = rollout_path(target, index)
            if path.exists():
                row = json.loads(path.read_text(encoding="utf-8"))
                if not row.get("mechanical_ok"):
                    raise ValueError("既有 P35 配对机械条件失败：" + str(path))
                completed_tables += 2
            else:
                pending.append((target, index, key))
    reservation = ledger.reserve(
        step_id="r18:p35-two-wealth:run", account="tables_full",
        amount=manifest["planned_tables"] - completed_tables,
        note="九隐藏根×32共同隐藏世界×立即胡/飘财神",
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
                        raise RuntimeError("P35 配对机械条件失败")
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
        "schema": "r18-p35-two-wealth-hidden-run-summary/1",
        "rollout_files": len(files), "actual_tables": len(files) * 2,
        "failures": failures, "spent": ledger.account_summary(),
    })
    if failures or len(files) * 2 != manifest["planned_tables"]:
        raise RuntimeError("P35 隐藏验收执行不完整")


def bootstrap_interval(values: list[float]) -> tuple[float, float]:
    """以自然来源根为单位做确定性 bootstrap 95% 区间。"""

    rng = random.Random(2026092235)
    means = []
    for _ in range(BOOTSTRAP_REPLICATES):
        means.append(statistics.fmean(rng.choice(values) for _ in values))
    means.sort()
    return (
        means[int(0.025 * len(means))],
        means[int(0.975 * len(means)) - 1],
    )


def analyze() -> None:
    """按九个自然来源根等权裁定隐藏机会能力。"""

    manifest, frozen = verify()
    capture_summary = json.loads((_project_file(_PROJECT_ROOT, OUT / "capture-summary.json")).read_text(encoding="utf-8"))
    run_summary = json.loads((_project_file(_PROJECT_ROOT, OUT / "run-summary.json")).read_text(encoding="utf-8"))
    if run_summary["failures"] or run_summary["actual_tables"] != manifest["planned_tables"]:
        raise ValueError("P35 隐藏配对执行不完整")
    states = []
    all_mechanical = True
    for target in frozen:
        rows = [
            json.loads(rollout_path(target, index).read_text(encoding="utf-8"))
            for index in range(1, ROLLOUTS_PER_STATE + 1)
        ]
        mechanical = all(row["mechanical_ok"] for row in rows)
        all_mechanical = all_mechanical and mechanical
        primary = [row["focal_current_round_settlement_delta"] for row in rows]
        full_table = [row["focal_remaining_table_score"]["delta"] for row in rows]
        states.append({
            "target_id": target["target_id"], "source": target["source"],
            "features": target["features"],
            "reference_action": target["reference_action"],
            "intervention_action": target["intervention_action"],
            "mechanical_ok": mechanical,
            "mean_piao_minus_hu_current_round_settlement": statistics.fmean(primary),
            "mean_remaining_table_score_delta": statistics.fmean(full_table),
            "primary_values": primary,
            "terminal_transitions": dict(sorted(Counter(
                row["reference"]["terminal"] + "->" + row["intervention"]["terminal"]
                for row in rows
            ).items())),
        })
    values = [row["mean_piao_minus_hu_current_round_settlement"] for row in states]
    low, high = bootstrap_interval(values)
    leave_one_out = {}
    for index, row in enumerate(states):
        remaining = values[:index] + values[index + 1:]
        leave_one_out[
            row["source"]["batch"] + "|" + row["source"]["source_root_id"]
        ] = statistics.fmean(remaining)
    positive = sum(value > 0 for value in values)
    candidate_actions_ok = bool(
        len(capture_summary["candidate_action_checks"]) == len(states)
        and all(
            row["expected_trigger"] is True
            and row["candidate_top"] == row["expected_target"]
            for row in capture_summary["candidate_action_checks"]
        )
    )
    aggregate = {
        "mean_piao_minus_hu_current_round_settlement": statistics.fmean(values),
        "bootstrap_95": [low, high],
        "positive_states": positive,
        "zero_states": sum(value == 0 for value in values),
        "negative_states": sum(value < 0 for value in values),
        "minimum_required_positive_states": MIN_POSITIVE_STATES,
        "leave_one_source_root_out_mean": leave_one_out,
        "minimum_leave_one_source_root_out_mean": min(leave_one_out.values()),
        "mean_remaining_table_score_delta_secondary": statistics.fmean(
            row["mean_remaining_table_score_delta"] for row in states
        ),
    }
    gate_passed = bool(
        all_mechanical and candidate_actions_ok
        and aggregate["mean_piao_minus_hu_current_round_settlement"] > 0
        and low > 0
        and positive >= MIN_POSITIVE_STATES
        and aggregate["minimum_leave_one_source_root_out_mean"] > 0
    )
    result = {
        "schema": "r18-p35-two-wealth-hidden-admission-result/1",
        "status": "COMPLETE_P35_TWO_WEALTH_HIDDEN_ADMISSION",
        "candidate_sha256": manifest["candidate_sha256"],
        "mechanical_ok": all_mechanical,
        "candidate_actions_ok": candidate_actions_ok,
        "hidden_states": len(states),
        "rollouts": len(states) * ROLLOUTS_PER_STATE,
        "tables": len(states) * ROLLOUTS_PER_STATE * 2,
        "states": states,
        "aggregate": aggregate,
        "gate_passed": gate_passed,
        "decision": (
            "OPEN_P36_FRESH_TABLE_SAFETY" if gate_passed
            else "CLOSE_P33_CANDIDATE_KEEP_P5"
        ),
        "labels_opened_after_candidate_freeze": True,
        "selection_eligible": gate_passed,
        "release_eligible": False,
        "next": (
            "候选源码保持冻结；用新seed同牌山换座位完整桌检验相对P5非劣"
            if gate_passed else
            "保持P5；记录隐藏失败，不得看结果后修改双财神阈值并重用本隐藏集"
        ),
    }
    write_json(_project_file(_PROJECT_ROOT, OUT / "result.json"), result)
    print(json.dumps({
        "status": result["status"], "mechanical_ok": all_mechanical,
        "candidate_actions_ok": candidate_actions_ok,
        "aggregate": aggregate, "gate_passed": gate_passed,
        "decision": result["decision"],
    }, ensure_ascii=False, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=(
        "prepare", "correct_authorization", "capture", "run", "analyze",
    ))
    globals()[parser.parse_args().operation]()


if __name__ == "__main__":
    main()
