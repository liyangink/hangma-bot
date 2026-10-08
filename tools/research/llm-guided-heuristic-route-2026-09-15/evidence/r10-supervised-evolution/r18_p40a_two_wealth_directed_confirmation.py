"""R18 P40a：双财神候选的全新自然根定向独立确认。"""

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
import r18_p29_multiwhite_baotou_natural_exposure as p29  # noqa: E402
import r18_p34_two_wealth_candidate_preflight as p34  # noqa: E402
import sitin_natural_panel as natural  # noqa: E402
import sitin_search as search  # noqa: E402
import strong_seed_batch as batch  # noqa: E402
from hangma_bot.policy.action_value_policy import build_scoring_view  # noqa: E402
from hangma_bot.policy.action_value_seeds import ActionValueScorer  # noqa: E402


OUT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p40a-two-wealth-directed-confirmation-01-20260922')
P39 = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p39-two-wealth-confirmation-candidate-01-20260922')
PACKAGE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p39-two-wealth-confirmation-candidate-01-20260922/candidate-package.json')
CONFIRMATION_CONTRACT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p39-two-wealth-confirmation-candidate-01-20260922/confirmation-contract.json')
CANDIDATE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p39-two-wealth-confirmation-candidate-01-20260922/candidate.py')
PARENT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p5-gang-dominance-01-20260922/generation/candidate.py')
CONTRACT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/contracts/group-dev-v1.json')
PANEL_SEED = 2026102212
MIXES = ("H", "M")
ROOTS = tuple(range(1, 161))
SEATS = (0, 1, 2, 3)
TABLES_PER_SOURCE = 2
WORKERS = 8
SOURCE_UNITS = len(MIXES) * len(ROOTS) * len(SEATS)
NATURAL_TABLES = SOURCE_UNITS * TABLES_PER_SOURCE
TARGETS_PER_MIX = 4
ROLLOUTS_PER_TARGET = 32
HIDDEN_TABLES = len(MIXES) * TARGETS_PER_MIX * ROLLOUTS_PER_TARGET * 2
SELECTION_SALT = "r18-p40a-two-wealth-independent-confirmation/v1"
BOOTSTRAP_REPLICATES = 20_000


def digest(path: Path) -> str:
    """返回文件字节 SHA-256。"""

    return hashlib.sha256(path.read_bytes()).hexdigest()


def value_digest(value: Any) -> str:
    """返回稳定 JSON 值 SHA-256。"""

    return hashlib.sha256(json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")).hexdigest()


def write_json(path: Path, value: Any) -> None:
    """稳定写入 UTF-8 JSON；只在离线证据目录产生副作用。"""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def sources() -> list[dict[str, Any]]:
    """冻结 H/M 各 160 个独立牌山根的四座位来源。"""

    return [
        {
            "batch": "P40a",
            "mix": mix,
            "root_index": root,
            "focal_seat": seat,
            "panel_seed": PANEL_SEED,
            "source_root_id": f"{mix}:p40a:r{root:03d}",
            "source_id": f"{mix}:p40a:r{root:03d}:s{seat}",
        }
        for mix in MIXES for root in ROOTS for seat in SEATS
    ]


def source_path(source: Mapping[str, Any]) -> Path:
    """返回单个自然来源结果路径。"""

    return _project_file(_PROJECT_ROOT, OUT / "sources" / (str(source["source_id"]).replace(":", "-") + ".json"))


def snapshot_path(target: Mapping[str, Any]) -> Path:
    """返回目标合法前缀快照路径。"""

    return _project_file(_PROJECT_ROOT, OUT / "snapshots" / (str(target["target_id"]) + ".json"))


def rollout_path(target: Mapping[str, Any], index: int) -> Path:
    """返回单个共同隐藏世界配对结果路径。"""

    return _project_file(_PROJECT_ROOT, OUT / "rollouts" / "{0}-world-{1:02d}.json".format(
        target["target_id"], index
    ))


def execute_source(source: Mapping[str, Any]) -> dict[str, Any]:
    """用全新 seed 运行 P5 自然轨迹并应用既有冻结公开谓词。"""

    p29.PANEL_SEED = PANEL_SEED
    p29.PARENT = PARENT
    return p29.execute_source(source)


def prepare() -> None:
    """在任何确认桌执行前冻结来源、公开谓词、选择规则与通过门。"""

    if OUT.exists():
        raise SystemExit("P40a 目录已存在；拒绝覆盖")
    package = json.loads(PACKAGE.read_text(encoding="utf-8"))
    contract = json.loads(CONFIRMATION_CONTRACT.read_text(encoding="utf-8"))
    if package.get("status") != "FROZEN_FOR_INDEPENDENT_CONFIRMATION":
        raise ValueError("P39 候选未冻结为独立确认身份")
    if digest(CANDIDATE) != package.get("candidate_sha256"):
        raise ValueError("P39 候选源码漂移")
    directed = contract["directed_natural_confirmation"]
    if (
        directed["minimum_independent_roots"] != 8
        or directed["minimum_roots_by_mix"] != {"H": 4, "M": 4}
        or directed["hidden_worlds_per_root"] != ROLLOUTS_PER_TARGET
    ):
        raise ValueError("P39 定向确认门与 P40a 实现不一致")
    OUT.mkdir(parents=True)
    for name in ("sources", "snapshots", "rollouts"):
        (_project_file(_PROJECT_ROOT, OUT / name)).mkdir()
    authorization = batch.unified_document(
        batch_label=OUT.name,
        authorization_id="r18-p40a-two-wealth-directed-confirmation-01",
        accounts={
            "tables_full": NATURAL_TABLES + HIDDEN_TABLES,
            "prefix_generation": len(MIXES) * TARGETS_PER_MIX,
            "confirm_reserved": len(MIXES) * TARGETS_PER_MIX,
        },
        issued_by="lead",
        issued_at_utc=search.utc_now(),
        legacy_alias=False,
    )
    authorization.update({
        "issuance_basis": "P39候选源码、身份和一次性确认合同已经冻结",
        "scope": (
            "全新P5自然轨迹搜索8个确认根；每根32个公开状态一致共同隐藏世界；"
            "立即胡对双财神保爆头飘"
        ),
        "max_model_calls": 0,
        "confirmation_roots": len(MIXES) * TARGETS_PER_MIX,
    })
    frozen_sources = sources()
    write_json(_project_file(_PROJECT_ROOT, OUT / "authorization.json"), authorization)
    write_json(_project_file(_PROJECT_ROOT, OUT / "sources.json"), {
        "schema": "r18-p40a-natural-confirmation-sources/1",
        "sources": frozen_sources,
    })
    tracked = [
        Path(__file__), Path(p29.__file__), Path(p13.__file__), Path(p34.__file__),
        PACKAGE, CONFIRMATION_CONTRACT, CANDIDATE, PARENT, CONTRACT,
        _project_file(_PROJECT_ROOT, OUT / "authorization.json"), _project_file(_PROJECT_ROOT, OUT / "sources.json"),
    ]
    write_json(_project_file(_PROJECT_ROOT, OUT / "manifest.json"), {
        "schema": "r18-p40a-two-wealth-directed-confirmation-manifest/1",
        "created_at_utc": search.utc_now(),
        "runtime": guard.capture(source_paths=tracked),
        "candidate_id": package["candidate_id"],
        "candidate_sha256": digest(CANDIDATE),
        "parent_sha256": digest(PARENT),
        "package_sha256": digest(PACKAGE),
        "confirmation_contract_sha256": digest(CONFIRMATION_CONTRACT),
        "contract_sha256": digest(CONTRACT),
        "panel_seed": PANEL_SEED,
        "mixes": list(MIXES),
        "root_indices": list(ROOTS),
        "focal_seats": list(SEATS),
        "source_units": SOURCE_UNITS,
        "tables_per_source": TABLES_PER_SOURCE,
        "natural_tables": NATURAL_TABLES,
        "workers": WORKERS,
        "frozen_predicate": (
            "draw and exactly_two_wealth and hu_legal and discard_white_legal and "
            "discard_white.baotou_after_is_true and p5_top_is_hu"
        ),
        "selection": {
            "unit": "mix + source_root_id；四座位与两桌不增加 n",
            "salt": SELECTION_SALT,
            "targets_per_mix": TARGETS_PER_MIX,
            "uses_outcome": False,
        },
        "hidden_confirmation": {
            "targets": len(MIXES) * TARGETS_PER_MIX,
            "sample_keys": [
                "r18-p40a-confirmation-world-{0:02d}".format(index)
                for index in range(1, ROLLOUTS_PER_TARGET + 1)
            ],
            "rollouts_per_target": ROLLOUTS_PER_TARGET,
            "planned_tables": HIDDEN_TABLES,
            "primary_metric": "piao_minus_immediate_hu_current_round_settlement",
            "gate": {
                "mechanical_success": "all",
                "candidate_action_matches": "all",
                "bootstrap_95_lower": ">0",
                "positive_roots": ">=7/8",
                "minimum_leave_one_root_out_mean": ">0",
            },
        },
        "outcome_blind_until_targets_frozen": True,
        "one_shot": True,
        "release_eligible": False,
    })
    print(json.dumps({
        "status": "P40A_PREPARED",
        "source_units": SOURCE_UNITS,
        "natural_tables": NATURAL_TABLES,
        "hidden_tables_if_reachable": HIDDEN_TABLES,
    }, ensure_ascii=False, indent=2))


def verify() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """核对候选、确认合同、脚本和自然来源没有漂移。"""

    manifest = json.loads((_project_file(_PROJECT_ROOT, OUT / "manifest.json")).read_text(encoding="utf-8"))
    checks = {
        "candidate": (manifest["candidate_sha256"], digest(CANDIDATE)),
        "parent": (manifest["parent_sha256"], digest(PARENT)),
        "package": (manifest["package_sha256"], digest(PACKAGE)),
        "confirmation_contract": (
            manifest["confirmation_contract_sha256"], digest(CONFIRMATION_CONTRACT)
        ),
        "table_contract": (manifest["contract_sha256"], digest(CONTRACT)),
    }
    for label, (expected, actual) in checks.items():
        if expected != actual:
            raise ValueError("P40a " + label + " 漂移")
    guard.verify(manifest["runtime"])
    frozen = json.loads((_project_file(_PROJECT_ROOT, OUT / "sources.json")).read_text(encoding="utf-8"))["sources"]
    if frozen != sources():
        raise ValueError("P40a 自然来源清单漂移")
    return manifest, frozen


def run_natural() -> None:
    """并行运行结果盲自然来源，支持断点续跑。"""

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
            row = json.loads(path.read_text(encoding="utf-8"))
            if row.get("status") != "complete" or row.get("tables") != TABLES_PER_SOURCE:
                raise ValueError("既有 P40a 自然来源不完整：" + str(path))
            completed_tables += TABLES_PER_SOURCE
        else:
            pending.append(source)
    reservation = ledger.reserve(
        step_id="r18:p40a:natural-exposure",
        account="tables_full",
        amount=NATURAL_TABLES - completed_tables,
        note="独立确认候选冻结后的全新P5自然轨迹目标机会搜索",
    )
    failures = []
    executed = 0
    usage_unknown = False
    try:
        with concurrent.futures.ProcessPoolExecutor(max_workers=manifest["workers"]) as pool:
            futures = {pool.submit(execute_source, source): source for source in pending}
            for future in concurrent.futures.as_completed(futures):
                source = futures[future]
                row = None
                try:
                    row = future.result()
                    if row["status"] != "complete" or row["tables"] != TABLES_PER_SOURCE:
                        raise RuntimeError(row.get("error") or "来源未跑满")
                    if row["audit"]["problems"]:
                        raise RuntimeError("P5 重评分失败：" + ";".join(
                            row["audit"]["problems"][:3]
                        ))
                    write_json(source_path(source), row)
                    executed += TABLES_PER_SOURCE
                    completed_tables += TABLES_PER_SOURCE
                    if completed_tables % 128 == 0 or completed_tables == NATURAL_TABLES:
                        print(json.dumps({
                            "completed_tables": completed_tables,
                            "planned_tables": NATURAL_TABLES,
                        }, ensure_ascii=False), flush=True)
                except Exception as exc:  # noqa: BLE001
                    if row is None:
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
    write_json(_project_file(_PROJECT_ROOT, OUT / "natural-run-summary.json"), {
        "schema": "r18-p40a-natural-run-summary/1",
        "source_files": len(files),
        "actual_tables": actual,
        "failures": failures,
        "spent": ledger.account_summary(),
    })
    if failures or actual != NATURAL_TABLES or len(files) != len(frozen):
        raise RuntimeError("P40a 自然确认来源执行不完整")


def _hash_order(row: Mapping[str, Any]) -> str:
    """按冻结盐、来源根和请求摘要产生结果盲选择顺序。"""

    return hashlib.sha256("|".join((
        SELECTION_SALT,
        str(row["source"]["source_root_id"]),
        str(row["request_sha256"]),
    )).encode("utf-8")).hexdigest()


def freeze_targets() -> None:
    """按来源根去重并冻结 H/M 各四个目标；不读取任何续打结果。"""

    manifest, frozen = verify()
    summary = json.loads((_project_file(_PROJECT_ROOT, OUT / "natural-run-summary.json")).read_text(encoding="utf-8"))
    if summary["failures"] or summary["actual_tables"] != NATURAL_TABLES:
        raise ValueError("P40a 自然来源尚未完整")
    counts: Counter[str] = Counter()
    rows_by_root: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for source in frozen:
        document = json.loads(source_path(source).read_text(encoding="utf-8"))
        counts.update(document["audit"]["counts"])
        for row in document["audit"]["eligible_rows"]:
            rows_by_root[str(source["source_root_id"])].append(row)
    independent = [
        min(options, key=_hash_order)
        for _root, options in sorted(rows_by_root.items())
    ]
    pools = {
        mix: sorted(
            (row for row in independent if row["source"]["mix"] == mix),
            key=_hash_order,
        )
        for mix in MIXES
    }
    enough = all(len(pools[mix]) >= TARGETS_PER_MIX for mix in MIXES)
    selected: list[dict[str, Any]] = []
    if enough:
        for mix in MIXES:
            for index, row in enumerate(pools[mix][:TARGETS_PER_MIX], 1):
                target = dict(row)
                target["source"] = dict(target["source"])
                target["source"]["table_no"] = int(target["table_no"])
                target["source"]["table_id"] = str(target["table_id"])
                target["target_id"] = "r18-p40a-{0}-{1:02d}".format(mix.lower(), index)
                target["family"] = "two_wealth.piao_keeps_baotou"
                target["split"] = "independent_confirmation"
                selected.append(target)
    selected.sort(key=lambda row: row.get("target_id", ""))
    write_json(_project_file(_PROJECT_ROOT, OUT / "targets.json"), {
        "schema": "r18-p40a-directed-confirmation-targets/1",
        "candidate_id": manifest["candidate_id"],
        "selection_salt": SELECTION_SALT,
        "outcome_blind": True,
        "targets": selected,
    })
    result = {
        "schema": "r18-p40a-natural-target-freeze-result/1",
        "status": "TARGETS_FROZEN" if enough else "INSUFFICIENT_NEW_NATURAL_ROOTS",
        "natural_tables": NATURAL_TABLES,
        "independent_roots": len(independent),
        "by_mix": {mix: len(pools[mix]) for mix in MIXES},
        "seat_coverage": sorted({row["focal_physical_seat"] for row in independent}),
        "raw_counts": dict(sorted(counts.items())),
        "selected_targets": len(selected),
        "targets_sha256": digest(_project_file(_PROJECT_ROOT, OUT / "targets.json")),
        "hidden_labels_opened": False,
        "confirmation_eligible": enough,
        "release_eligible": False,
    }
    write_json(_project_file(_PROJECT_ROOT, OUT / "target-freeze-result.json"), result)
    print(json.dumps(result, ensure_ascii=False, indent=2))


def targets() -> list[dict[str, Any]]:
    """读取已经结果盲冻结的八个独立确认目标。"""

    document = json.loads((_project_file(_PROJECT_ROOT, OUT / "targets.json")).read_text(encoding="utf-8"))
    rows = list(document["targets"])
    if len(rows) != len(MIXES) * TARGETS_PER_MIX:
        raise ValueError("P40a 没有冻结恰好八个确认目标")
    if Counter(row["source"]["mix"] for row in rows) != {"H": 4, "M": 4}:
        raise ValueError("P40a 确认目标 H/M 配比漂移")
    return rows


def correct_target_shape() -> None:
    """在零捕获、零隐藏桌后补齐重建器所需的 source 表身份字段。"""

    if any((_project_file(_PROJECT_ROOT, OUT / "snapshots")).glob("*.json")):
        raise RuntimeError("已有确认快照，不得修订目标结构")
    if any((_project_file(_PROJECT_ROOT, OUT / "rollouts")).glob("*.json")):
        raise RuntimeError("已有隐藏配对结果，不得修订目标结构")
    failure_path = _project_file(_PROJECT_ROOT, OUT / "capture-summary.json")
    failure = json.loads(failure_path.read_text(encoding="utf-8"))
    if failure.get("captured") != 0 or len(failure.get("failures") or []) != 8:
        raise RuntimeError("首次捕获不是八根零成功的 table_no 结构失败")
    if any(row.get("error") != "KeyError: 'table_no'" for row in failure["failures"]):
        raise RuntimeError("首次捕获还包含非 table_no 结构失败")

    manifest_path = _project_file(_PROJECT_ROOT, OUT / "manifest.json")
    targets_path = _project_file(_PROJECT_ROOT, OUT / "targets.json")
    freeze_result_path = _project_file(_PROJECT_ROOT, OUT / "target-freeze-result.json")
    old_manifest_sha256 = digest(manifest_path)
    old_targets_sha256 = digest(targets_path)
    attempt_path = _project_file(_PROJECT_ROOT, OUT / "capture-attempt-01-failure.json")
    write_json(attempt_path, failure)
    document = json.loads(targets_path.read_text(encoding="utf-8"))
    for target in document["targets"]:
        source = dict(target["source"])
        if "table_no" in source or "table_id" in source:
            raise RuntimeError("目标 source 已含表身份，拒绝重复修订")
        source["table_no"] = int(target["table_no"])
        source["table_id"] = str(target["table_id"])
        target["source"] = source
    write_json(targets_path, document)
    freeze_result = json.loads(freeze_result_path.read_text(encoding="utf-8"))
    freeze_result["targets_sha256"] = digest(targets_path)
    freeze_result["target_shape_correction"] = (
        "只把顶层 table_no/table_id 复制到 source 块，供既有合法前缀重建器读取"
    )
    write_json(freeze_result_path, freeze_result)
    correction_path = _project_file(_PROJECT_ROOT, OUT / "target-shape-correction.json")
    write_json(correction_path, {
        "schema": "r18-p40a-target-shape-correction/1",
        "first_attempt_status": "REFUSED_BEFORE_SNAPSHOT_OR_HIDDEN_TABLE",
        "first_attempt_error": "KeyError: 'table_no'",
        "old_targets_sha256": old_targets_sha256,
        "new_targets_sha256": digest(targets_path),
        "old_manifest_sha256": old_manifest_sha256,
        "snapshots_before_correction": 0,
        "hidden_rollouts_before_correction": 0,
        "candidate_changed": False,
        "selected_roots_changed": False,
        "gate_changed": False,
        "corrected_fields": ["source.table_no", "source.table_id"],
        "capture_attempt_sha256": digest(attempt_path),
    })
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    tracked = [
        Path(__file__), Path(p29.__file__), Path(p13.__file__), Path(p34.__file__),
        PACKAGE, CONFIRMATION_CONTRACT, CANDIDATE, PARENT, CONTRACT,
        _project_file(_PROJECT_ROOT, OUT / "authorization.json"), _project_file(_PROJECT_ROOT, OUT / "sources.json"), targets_path,
        freeze_result_path, attempt_path, correction_path,
    ]
    manifest["runtime"] = guard.capture(source_paths=tracked)
    manifest["target_shape_correction_sha256"] = digest(correction_path)
    manifest["targets_sha256"] = digest(targets_path)
    write_json(manifest_path, manifest)
    print(json.dumps({
        "status": "P40A_TARGET_SHAPE_CORRECTED",
        "targets": len(document["targets"]),
        "snapshots": 0,
        "hidden_rollouts": 0,
        "candidate_changed": False,
        "gate_changed": False,
    }, ensure_ascii=False, indent=2))


def capture() -> None:
    """重建八个合法前缀，并验证冻结候选选择目标飘财神动作。"""

    manifest, _frozen = verify()
    frozen_targets = targets()
    freeze_result = json.loads(
        (_project_file(_PROJECT_ROOT, OUT / "target-freeze-result.json")).read_text(encoding="utf-8")
    )
    if freeze_result.get("hidden_labels_opened") is not False:
        raise ValueError("P40a 捕获前隐藏标签状态不为 false")
    if freeze_result["targets_sha256"] != digest(_project_file(_PROJECT_ROOT, OUT / "targets.json")):
        raise ValueError("P40a 冻结目标漂移")
    authorization = json.loads((_project_file(_PROJECT_ROOT, OUT / "authorization.json")).read_text(encoding="utf-8"))
    natural.require_authorization(authorization)
    ledger = search.ActionValueLedger.load(
        _project_file(_PROJECT_ROOT, OUT / "ledger.json"),
        authorized_budgets=search.av_ledger_budgets_from_authorization(authorization),
    )
    pending = [row for row in frozen_targets if not snapshot_path(row).exists()]
    capture_step_id = (
        "r18:p40a:capture-after-target-shape-correction"
        if (_project_file(_PROJECT_ROOT, OUT / "target-shape-correction.json")).exists()
        else "r18:p40a:capture"
    )
    reservation = ledger.reserve(
        step_id=capture_step_id,
        account="prefix_generation",
        amount=len(pending),
        note="八个全新独立确认自然根的P5精确合法前缀捕获",
    )
    table_contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    parent = ActionValueScorer("r18-p40a-capture-parent", PARENT.read_text(encoding="utf-8"))
    candidate = ActionValueScorer(
        "r18-p40a-capture-candidate", CANDIDATE.read_text(encoding="utf-8")
    )
    completed = 0
    failures = []
    checks = []
    try:
        for target in pending:
            try:
                p13.PARENT = PARENT
                snapshot = p13.capture_one(target, table_contract)
                snapshot["capture"]["consumer"] = "R18 P40a independent confirmation"
                request = p34.request_from_snapshot(target, snapshot)
                checked = p34.check_view(
                    label=target["target_id"],
                    view=build_scoring_view(request),
                    parent=parent,
                    candidate=candidate,
                )
                if (
                    checked["expected_target"] != target["intervention_action"]
                    or checked["candidate_top"] != target["intervention_action"]
                ):
                    raise ValueError("确认候选未选择冻结飘财神动作")
                write_json(snapshot_path(target), snapshot)
                checks.append(checked)
                completed += 1
                print(json.dumps({
                    "captured": sum(snapshot_path(row).exists() for row in frozen_targets),
                    "planned": len(frozen_targets),
                }, ensure_ascii=False), flush=True)
            except Exception as exc:  # noqa: BLE001
                failures.append({
                    "target_id": target["target_id"],
                    "error": type(exc).__name__ + ": " + str(exc),
                })
    finally:
        ledger.settle(reservation, actual=completed, note="按成功捕获并核验候选动作的根计")
    write_json(_project_file(_PROJECT_ROOT, OUT / "capture-summary.json"), {
        "schema": "r18-p40a-capture-summary/1",
        "captured": sum(snapshot_path(row).exists() for row in frozen_targets),
        "planned": len(frozen_targets),
        "candidate_action_checks": checks,
        "failures": failures,
        "spent": ledger.account_summary(),
    })
    if failures or not all(snapshot_path(row).exists() for row in frozen_targets):
        raise RuntimeError("P40a 确认根捕获不完整")


def rebind_after_capture_step_fix() -> None:
    """在第二次捕获仍为零执行时，为修正后的新 step_id 重绑运行清单。"""

    if any((_project_file(_PROJECT_ROOT, OUT / "snapshots")).glob("*.json")):
        raise RuntimeError("已有确认快照，不得重绑捕获步骤")
    if any((_project_file(_PROJECT_ROOT, OUT / "rollouts")).glob("*.json")):
        raise RuntimeError("已有隐藏配对结果，不得重绑捕获步骤")
    ledger = json.loads((_project_file(_PROJECT_ROOT, OUT / "ledger.json")).read_text(encoding="utf-8"))
    capture_rows = [
        row for row in ledger.get("reservations", [])
        if row.get("step_id") == "r18:p40a:capture"
    ]
    if len(capture_rows) != 1 or capture_rows[0].get("charged") != 0:
        raise RuntimeError("原捕获步骤不是唯一零成本结算")
    attempt_path = _project_file(_PROJECT_ROOT, OUT / "capture-attempt-02-failure.json")
    write_json(attempt_path, {
        "schema": "r18-p40a-capture-attempt-failure/1",
        "status": "REFUSED_BEFORE_RESERVATION_OR_SNAPSHOT",
        "error": (
            "TaskAlreadySettled: r18:p40a:capture 已以 actual=0 结算；"
            "结构修正后的重试必须使用新 step_id"
        ),
        "snapshots": 0,
        "hidden_rollouts": 0,
        "candidate_changed": False,
        "targets_changed": False,
        "gate_changed": False,
    })
    correction_path = _project_file(_PROJECT_ROOT, OUT / "capture-step-id-correction.json")
    write_json(correction_path, {
        "schema": "r18-p40a-capture-step-id-correction/1",
        "old_step_id": "r18:p40a:capture",
        "old_step_actual": 0,
        "new_step_id": "r18:p40a:capture-after-target-shape-correction",
        "reason": "已结算任务名不可复用；保留首次失败成本并使用独立重试身份",
        "candidate_changed": False,
        "targets_changed": False,
        "gate_changed": False,
        "attempt_sha256": digest(attempt_path),
    })
    manifest_path = _project_file(_PROJECT_ROOT, OUT / "manifest.json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    tracked = [
        Path(__file__), Path(p29.__file__), Path(p13.__file__), Path(p34.__file__),
        PACKAGE, CONFIRMATION_CONTRACT, CANDIDATE, PARENT, CONTRACT,
        _project_file(_PROJECT_ROOT, OUT / "authorization.json"), _project_file(_PROJECT_ROOT, OUT / "sources.json"), _project_file(_PROJECT_ROOT, OUT / "targets.json"),
        _project_file(_PROJECT_ROOT, OUT / "target-freeze-result.json"), _project_file(_PROJECT_ROOT, OUT / "capture-attempt-01-failure.json"),
        _project_file(_PROJECT_ROOT, OUT / "target-shape-correction.json"), attempt_path, correction_path,
    ]
    manifest["runtime"] = guard.capture(source_paths=tracked)
    manifest["capture_step_id_correction_sha256"] = digest(correction_path)
    write_json(manifest_path, manifest)
    print(json.dumps({
        "status": "P40A_CAPTURE_STEP_ID_REBOUND",
        "old_step_actual": 0,
        "snapshots": 0,
        "hidden_rollouts": 0,
        "candidate_changed": False,
        "targets_changed": False,
        "gate_changed": False,
    }, ensure_ascii=False, indent=2))


def execute_rollout(
    target: Mapping[str, Any], index: int, sample_key: str,
) -> dict[str, Any]:
    """在共同隐藏世界中比较 P5 立即胡与确认候选的飘财神首动作。"""

    p13.OUT = OUT
    p13.PARENT = PARENT
    row = p13.execute_rollout(target, index, sample_key)
    row["schema"] = "r18-p40a-directed-confirmation-rollout/1"
    row["family"] = target["family"]
    row["split"] = "independent_confirmation"
    return row


def run_hidden() -> None:
    """执行八根、每根 32 个共同隐藏世界的双臂一次性确认。"""

    manifest, _frozen = verify()
    frozen_targets = targets()
    capture_summary = json.loads(
        (_project_file(_PROJECT_ROOT, OUT / "capture-summary.json")).read_text(encoding="utf-8")
    )
    if capture_summary["failures"] or capture_summary["captured"] != len(frozen_targets):
        raise ValueError("P40a 确认根未完整捕获")
    authorization = json.loads((_project_file(_PROJECT_ROOT, OUT / "authorization.json")).read_text(encoding="utf-8"))
    natural.require_authorization(authorization)
    ledger = search.ActionValueLedger.load(
        _project_file(_PROJECT_ROOT, OUT / "ledger.json"),
        authorized_budgets=search.av_ledger_budgets_from_authorization(authorization),
    )
    sample_keys = manifest["hidden_confirmation"]["sample_keys"]
    pending = []
    completed_tables = 0
    for target in frozen_targets:
        for index, key in enumerate(sample_keys, 1):
            path = rollout_path(target, index)
            if path.exists():
                row = json.loads(path.read_text(encoding="utf-8"))
                if not row.get("mechanical_ok"):
                    raise ValueError("既有 P40a 配对机械条件失败：" + str(path))
                completed_tables += 2
            else:
                pending.append((target, index, key))
    reservation = ledger.reserve(
        step_id="r18:p40a:hidden-confirmation",
        account="tables_full",
        amount=HIDDEN_TABLES - completed_tables,
        note="八个独立确认根×32共同隐藏世界×立即胡/飘财神",
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
                        raise RuntimeError("P40a 配对机械条件失败")
                    write_json(rollout_path(target, index), row)
                    executed += 2
                    completed_tables += 2
                    if completed_tables % 64 == 0 or completed_tables == HIDDEN_TABLES:
                        print(json.dumps({
                            "completed_tables": completed_tables,
                            "planned_tables": HIDDEN_TABLES,
                        }, ensure_ascii=False), flush=True)
                except Exception as exc:  # noqa: BLE001
                    if row is None:
                        usage_unknown = True
                    failures.append({
                        "target_id": target["target_id"],
                        "rollout_index": index,
                        "error": type(exc).__name__ + ": " + str(exc),
                    })
    finally:
        if usage_unknown:
            ledger.settle(reservation, usage_unknown=True, note="子进程未返回；保守结算")
        else:
            ledger.settle(reservation, actual=executed, note="按成功两臂桌数结算")
    files = list((_project_file(_PROJECT_ROOT, OUT / "rollouts")).glob("*.json"))
    write_json(_project_file(_PROJECT_ROOT, OUT / "hidden-run-summary.json"), {
        "schema": "r18-p40a-hidden-run-summary/1",
        "rollout_files": len(files),
        "actual_tables": len(files) * 2,
        "failures": failures,
        "spent": ledger.account_summary(),
    })
    if failures or len(files) * 2 != HIDDEN_TABLES:
        raise RuntimeError("P40a 隐藏确认执行不完整")


def bootstrap_interval(values: list[float]) -> tuple[float, float]:
    """以独立自然来源根为单位做冻结随机种子的 bootstrap 95% 区间。"""

    rng = random.Random(PANEL_SEED + 40)
    means = []
    for _ in range(BOOTSTRAP_REPLICATES):
        means.append(statistics.fmean(rng.choice(values) for _ in values))
    means.sort()
    return (
        means[int(0.025 * len(means))],
        means[int(0.975 * len(means)) - 1],
    )


def analyze() -> None:
    """按八个新自然来源根等权裁定定向独立确认。"""

    manifest, _frozen = verify()
    frozen_targets = targets()
    capture_summary = json.loads(
        (_project_file(_PROJECT_ROOT, OUT / "capture-summary.json")).read_text(encoding="utf-8")
    )
    run_summary = json.loads(
        (_project_file(_PROJECT_ROOT, OUT / "hidden-run-summary.json")).read_text(encoding="utf-8")
    )
    if run_summary["failures"] or run_summary["actual_tables"] != HIDDEN_TABLES:
        raise ValueError("P40a 隐藏确认执行不完整")
    states = []
    for target in frozen_targets:
        rows = [
            json.loads(rollout_path(target, index).read_text(encoding="utf-8"))
            for index in range(1, ROLLOUTS_PER_TARGET + 1)
        ]
        primary = [row["focal_current_round_settlement_delta"] for row in rows]
        full_table = [row["focal_remaining_table_score"]["delta"] for row in rows]
        states.append({
            "target_id": target["target_id"],
            "source": target["source"],
            "features": target["features"],
            "reference_action": target["reference_action"],
            "intervention_action": target["intervention_action"],
            "mechanical_ok": all(row["mechanical_ok"] for row in rows),
            "mean_current_round_settlement_delta": statistics.fmean(primary),
            "mean_remaining_table_score_delta": statistics.fmean(full_table),
            "primary_values": primary,
            "terminal_transitions": dict(sorted(Counter(
                row["reference"]["terminal"] + "->" + row["intervention"]["terminal"]
                for row in rows
            ).items())),
        })
    values = [row["mean_current_round_settlement_delta"] for row in states]
    low, high = bootstrap_interval(values)
    leave_one_out = {
        row["source"]["source_root_id"]: statistics.fmean(
            values[:index] + values[index + 1:]
        )
        for index, row in enumerate(states)
    }
    action_checks = capture_summary["candidate_action_checks"]
    candidate_actions_ok = bool(
        len(action_checks) == len(states)
        and all(
            row["expected_trigger"] is True
            and row["candidate_top"] == row["expected_target"]
            for row in action_checks
        )
    )
    aggregate = {
        "mean_current_round_settlement_delta": statistics.fmean(values),
        "bootstrap_95": [low, high],
        "positive_roots": sum(value > 0 for value in values),
        "zero_roots": sum(value == 0 for value in values),
        "negative_roots": sum(value < 0 for value in values),
        "minimum_required_positive_roots": 7,
        "leave_one_root_out_mean": leave_one_out,
        "minimum_leave_one_root_out_mean": min(leave_one_out.values()),
        "mean_remaining_table_score_delta_secondary": statistics.fmean(
            row["mean_remaining_table_score_delta"] for row in states
        ),
    }
    gate_passed = bool(
        all(row["mechanical_ok"] for row in states)
        and candidate_actions_ok
        and low > 0
        and aggregate["positive_roots"] >= 7
        and aggregate["minimum_leave_one_root_out_mean"] > 0
    )
    result = {
        "schema": "r18-p40a-two-wealth-directed-confirmation-result/1",
        "status": "PASS_P40A_DIRECTED_CONFIRMATION" if gate_passed else "FAIL_P40A_DIRECTED_CONFIRMATION",
        "candidate_id": manifest["candidate_id"],
        "candidate_sha256": manifest["candidate_sha256"],
        "natural_tables": NATURAL_TABLES,
        "independent_confirmation_roots": len(states),
        "rollouts": len(states) * ROLLOUTS_PER_TARGET,
        "hidden_tables": HIDDEN_TABLES,
        "candidate_actions_ok": candidate_actions_ok,
        "mechanical_ok": all(row["mechanical_ok"] for row in states),
        "states": states,
        "aggregate": aggregate,
        "gate_passed": gate_passed,
        "confirmation_eligible": gate_passed,
        "release_eligible": False,
        "next": (
            "执行P40b全新完整桌非劣确认"
            if gate_passed else
            "关闭当前候选发布推进；保持活动研究父代，不得复用本确认集改阈值"
        ),
    }
    write_json(_project_file(_PROJECT_ROOT, OUT / "result.json"), result)
    print(json.dumps({
        "status": result["status"],
        "aggregate": aggregate,
        "candidate_actions_ok": candidate_actions_ok,
        "mechanical_ok": result["mechanical_ok"],
        "gate_passed": gate_passed,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=(
        "prepare", "run_natural", "freeze_targets", "correct_target_shape", "capture",
        "rebind_after_capture_step_fix", "run_hidden", "analyze",
    ))
    globals()[parser.parse_args().operation]()
