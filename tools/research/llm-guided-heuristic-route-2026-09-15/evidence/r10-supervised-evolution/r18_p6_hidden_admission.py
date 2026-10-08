"""R18 P6 七对门清候选的一次性新来源隐藏准入。"""

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
import r18_p6_development_preflight as development  # noqa: E402
import r18_seven_pairs_natural_probe as probe  # noqa: E402
import sitin_natural_panel as natural  # noqa: E402
import sitin_search as search  # noqa: E402
import strong_seed_batch as batch  # noqa: E402
from hangma_bot.kernel.serialization import window_key_to_json  # noqa: E402
from hangma_bot.policy.action_value_policy import build_scoring_view  # noqa: E402
from hangma_bot.policy.action_value_seeds import ActionValueScorer  # noqa: E402


OUT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p6-hidden-admission-01-20260922')
CANDIDATE = development.CANDIDATE
PARENT = development.PARENT
PREFLIGHT = development.OUT / "result.json"
CONTRACT = probe.CONTRACT
PANEL_SEED = 2026100929
MIXES = probe.MIXES
ROOTS = probe.ROOTS
SEATS = probe.SEATS
TABLES_PER_SOURCE = probe.TABLES_PER_SOURCE
PLANNED_TABLES = len(MIXES) * len(ROOTS) * len(SEATS) * TABLES_PER_SOURCE
LIMITS = probe.LIMITS


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
    """列出候选冻结后的全新自然来源。"""

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


def prepare() -> None:
    """在生成隐藏轨迹前冻结候选、判据、来源和门槛。"""

    if OUT.exists():
        raise SystemExit("P6 隐藏准入目录已存在；拒绝覆盖")
    preflight = json.loads(PREFLIGHT.read_text(encoding="utf-8"))
    if preflight.get("status") != "PASS_P6_DEVELOPMENT":
        raise ValueError("P6 开发预检未通过")
    OUT.mkdir(parents=True)
    authorization = batch.unified_document(
        batch_label=OUT.name,
        authorization_id="r18-p6-hidden-admission-01",
        accounts={"tables_full": PLANNED_TABLES},
        issued_by="lead",
        issued_at_utc=search.utc_now(),
        legacy_alias=False,
    )
    authorization.update({
        "issuance_basis": "P6开发预检通过；源码冻结后用全新自然来源一次性验收",
        "scope": "全新H/M各32根、四焦点座、每来源2桌；严格命中改良与非命中P5逐点保持",
        "max_model_calls": 0,
        "confirmation_roots": len(MIXES) * len(ROOTS),
    })
    write_json(_project_file(_PROJECT_ROOT, OUT / "authorization.json"), authorization)
    write_json(_project_file(_PROJECT_ROOT, OUT / "manifest.json"), {
        "schema": "r18-p6-hidden-admission-manifest/1",
        "created_at_utc": search.utc_now(),
        "runtime": guard.capture(source_paths=[
            Path(__file__), Path(probe.__file__), Path(development.__file__),
            CANDIDATE, PARENT, PREFLIGHT, CONTRACT, _project_file(_PROJECT_ROOT, OUT / "authorization.json"),
            Path(natural.__file__),
        ]),
        "candidate_sha256": digest(CANDIDATE),
        "parent_sha256": digest(PARENT),
        "preflight_sha256": digest(PREFLIGHT),
        "predicate_source_sha256": digest(Path(probe.__file__)),
        "contract_sha256": digest(CONTRACT),
        "development_panel_seed_excluded": probe.PANEL_SEED,
        "panel_seed": PANEL_SEED,
        "mixes": list(MIXES),
        "root_indices": list(ROOTS),
        "focal_seats": list(SEATS),
        "sources": len(sources()),
        "tables_per_source": TABLES_PER_SOURCE,
        "planned_tables": PLANNED_TABLES,
        "workers": 8,
        "trajectory_policy": "stable weighted_heuristic_v2",
        "admission_gate": {
            "strict_windows_min": 16,
            "strict_distinct_tables_min": 16,
            "strict_distinct_source_roots_min": 8,
            "strict_required_mixes": list(MIXES),
            "strict_selection_failures": 0,
            "nonstrict_score_or_choice_mismatches": 0,
            "candidate_failures": 0,
        },
        "hidden_semantics": "候选源码与门槛先冻结；未命中窗口必须逐点评分保持P5",
        "selection_eligible": False,
        "release_eligible": False,
    })
    print(json.dumps({
        "status": "PREPARED",
        "candidate_sha256": digest(CANDIDATE),
        "panel_seed": PANEL_SEED,
        "tables": PLANNED_TABLES,
    }, ensure_ascii=False))


def verify_manifest() -> dict[str, Any]:
    """拒绝候选、父代、预检、判据、合同或执行代码漂移。"""

    manifest = json.loads((_project_file(_PROJECT_ROOT, OUT / "manifest.json")).read_text(encoding="utf-8"))
    checks = {
        "candidate": (manifest["candidate_sha256"], digest(CANDIDATE)),
        "parent": (manifest["parent_sha256"], digest(PARENT)),
        "preflight": (manifest["preflight_sha256"], digest(PREFLIGHT)),
        "predicate": (manifest["predicate_source_sha256"], digest(Path(probe.__file__))),
        "contract": (manifest["contract_sha256"], digest(CONTRACT)),
    }
    for label, (expected, actual) in checks.items():
        if expected != actual:
            raise ValueError(label + " 漂移")
    if manifest["panel_seed"] == manifest["development_panel_seed_excluded"]:
        raise ValueError("隐藏准入错误复用开发 panel_seed")
    guard.verify(manifest["runtime"])
    return manifest


def _top_key(batch_result: Any) -> str:
    """按合同排序规则读取首选动作。"""

    return sorted(batch_result.entries, key=lambda item: (-item.score, item.action_key))[0].action_key


def _score_map(batch_result: Any) -> dict[str, float]:
    """返回完整动作评分。"""

    return {item.action_key: item.score for item in batch_result.entries}


def _independent_expected(request: Any, parent_batch: Any) -> tuple[str | None, dict[str, Any] | None]:
    """用规则对象和冻结探针判据独立计算应触发动作。"""

    observation = request.observation
    legal = list(request.rules.legal_candidates)
    if (
        len(legal) < 2
        or len(observation.melds[observation.seat]) != 0
        or any(not item.action_key.startswith("discard:") for item in legal)
    ):
        return None, None
    rows = [probe._complete_discard(item) for item in legal]
    if any(row is None for row in rows):
        return None, None
    valid = [row for row in rows if row is not None]
    by_key = {row["action_key"]: row for row in valid}
    scores = _score_map(parent_batch)
    parent_top = _top_key(parent_batch)
    if parent_top not in by_key:
        return None, None
    reference = by_key[parent_top]
    dominators = [
        row for row in valid
        if scores.get(row["action_key"]) == scores.get(parent_top)
        and row["standard_shanten"] == reference["standard_shanten"]
        and row["standard_useful"] == reference["standard_useful"]
        and probe._seven_dominates(row, reference)
    ]
    if not dominators:
        return None, None
    chosen = sorted(
        dominators,
        key=lambda row: (
            row["seven_pairs_shanten"],
            -sum(value for _, value in row["seven_pairs_useful"]),
            row["action_key"],
        ),
    )[0]
    return str(chosen["action_key"]), {
        "parent_action": parent_top,
        "parent": reference,
        "dominant": chosen,
    }


def audit_requests(requests: list[Any], source: Mapping[str, Any]) -> dict[str, Any]:
    """独立判定严格窗口并比较冻结 P6 与 P5 的完整评分。"""

    parent = ActionValueScorer("r18-p6-hidden-parent", PARENT.read_text(encoding="utf-8"))
    candidate = ActionValueScorer("r18-p6-hidden-candidate", CANDIDATE.read_text(encoding="utf-8"))
    counts: Counter[str] = Counter()
    windows = []
    problems = []
    max_operations = 0
    for request in requests:
        counts["focal_requests"] += 1
        view = build_scoring_view(request)
        try:
            parent_batch = parent.score(view)
            candidate_batch = candidate.score(view)
        except Exception as exc:  # noqa: BLE001 - 候选失败必须进入证据
            counts["candidate_failures"] += 1
            problems.append(type(exc).__name__ + ": " + str(exc)[:240])
            continue
        max_operations = max(max_operations, candidate.last_operation_count)
        parent_top = _top_key(parent_batch)
        candidate_top = _top_key(candidate_batch)
        triggers = [
            item.action_key for item in candidate_batch.entries
            if isinstance(item.trace.get("r18_seven_pairs_overlay"), dict)
            and item.trace["r18_seven_pairs_overlay"].get("triggered") is True
        ]
        expected_key, evidence = _independent_expected(request, parent_batch)
        if expected_key is None:
            counts["nonstrict_windows"] += 1
            if triggers:
                counts["unexpected_trigger_windows"] += 1
            if _score_map(candidate_batch) != _score_map(parent_batch):
                counts["nonstrict_score_mismatches"] += 1
            if candidate_top != parent_top:
                counts["nonstrict_choice_mismatches"] += 1
            continue
        counts["strict_windows"] += 1
        if candidate_top != expected_key:
            counts["strict_selection_failures"] += 1
        if triggers != [expected_key]:
            counts["strict_trace_failures"] += 1
        entry = next(item for item in candidate_batch.entries if item.action_key == expected_key)
        trace = entry.trace.get("r18_seven_pairs_overlay")
        if not isinstance(trace, dict) or trace.get("parent_action") != parent_top:
            counts["strict_trace_content_failures"] += 1
        parent_score = _score_map(parent_batch)[parent_top]
        if entry.score != parent_score + 0.25:
            counts["strict_score_failures"] += 1
        windows.append({
            "source": dict(source),
            "game_id": request.observation.game_id,
            "round_no": request.observation.round_no,
            "seat": request.observation.seat,
            "window_key": window_key_to_json(request.window_key),
            "parent_action": parent_top,
            "candidate_action": candidate_top,
            "expected_action": expected_key,
            "parent_facts": evidence["parent"],
            "dominant_facts": evidence["dominant"],
            "candidate_operations": candidate.last_operation_count,
        })
    return {
        "counts": dict(sorted(counts.items())),
        "windows": windows,
        "problems": problems,
        "max_candidate_operations": max_operations,
    }


def execute_source(source: Mapping[str, Any]) -> dict[str, Any]:
    """跑一个隐藏来源的两桌稳定 V2 阶段并审计焦点请求。"""

    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    plans = natural.build_seat_stage_plans(
        contract=contract,
        opponent=str(source["mix"]),
        root_index=int(source["root_index"]),
        focal_seat=int(source["focal_seat"]),
        panel_seed=PANEL_SEED,
    )
    requests: list[Any] = []
    stage = natural.run_arm_stage(
        arm="baseline",
        plans=plans,
        candidate_scorer=ActionValueScorer("r18-p6-hidden-unused", PARENT.read_text(encoding="utf-8")),
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
    """并行执行隐藏来源，按来源断点续跑。"""

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
        step_id="r18:p6-hidden-admission",
        account="tables_full",
        amount=PLANNED_TABLES - completed_tables,
        note="P6冻结后全新自然来源隐藏准入",
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
                        raise RuntimeError("隐藏来源出现候选执行问题")
                    write_json(source_path(row), result)
                    executed += TABLES_PER_SOURCE
                    completed_tables += TABLES_PER_SOURCE
                    if completed_tables % 64 == 0 or completed_tables == PLANNED_TABLES:
                        print(json.dumps({
                            "completed_tables": completed_tables,
                            "planned_tables": PLANNED_TABLES,
                        }, ensure_ascii=False), flush=True)
                except Exception as exc:  # noqa: BLE001 - 失败必须保守记账
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
        "schema": "r18-p6-hidden-admission-run/1",
        "source_files": len(files),
        "actual_tables": actual,
        "failures": failures,
        "spent": ledger.account_summary(),
    })
    if failures or actual != PLANNED_TABLES or len(files) != len(sources()):
        raise RuntimeError("P6 隐藏准入执行不完整")
    print(json.dumps({"status": "RUN_COMPLETE", "tables": actual}, ensure_ascii=False))


def analyze() -> None:
    """聚合隐藏证据并严格套用预冻结通过门。"""

    manifest = verify_manifest()
    run_summary = json.loads((_project_file(_PROJECT_ROOT, OUT / "run-summary.json")).read_text(encoding="utf-8"))
    if run_summary["failures"] or run_summary["actual_tables"] != PLANNED_TABLES:
        raise ValueError("P6 隐藏准入运行不完整")
    counts: Counter[str] = Counter()
    runtime: Counter[str] = Counter()
    windows = []
    completed_hands = 0
    max_operations = 0
    for source in sources():
        document = json.loads(source_path(source).read_text(encoding="utf-8"))
        completed_hands += int(document["completed_hands"])
        counts.update(document["audit"]["counts"])
        runtime.update(document["runtime_counts"])
        windows.extend(document["audit"]["windows"])
        max_operations = max(max_operations, int(document["audit"]["max_candidate_operations"]))
    tables = {row["game_id"] for row in windows}
    roots = {row["source"]["source_root_id"] for row in windows}
    mixes = {row["source"]["mix"] for row in windows}
    gate = manifest["admission_gate"]
    nonstrict_mismatches = (
        counts["unexpected_trigger_windows"]
        + counts["nonstrict_score_mismatches"]
        + counts["nonstrict_choice_mismatches"]
    )
    strict_failures = (
        counts["strict_selection_failures"]
        + counts["strict_trace_failures"]
        + counts["strict_trace_content_failures"]
        + counts["strict_score_failures"]
    )
    gate_checks = {
        "strict_windows_min": len(windows) >= int(gate["strict_windows_min"]),
        "strict_distinct_tables_min": len(tables) >= int(gate["strict_distinct_tables_min"]),
        "strict_distinct_source_roots_min": len(roots) >= int(gate["strict_distinct_source_roots_min"]),
        "strict_required_mixes": mixes == set(gate["strict_required_mixes"]),
        "strict_selection_failures_zero": strict_failures == int(gate["strict_selection_failures"]),
        "nonstrict_mismatches_zero": nonstrict_mismatches == int(gate["nonstrict_score_or_choice_mismatches"]),
        "candidate_failures_zero": counts["candidate_failures"] == int(gate["candidate_failures"]),
        "operations_within_default_limit": max_operations <= 100_000,
    }
    result = {
        "schema": "r18-p6-hidden-admission-result/1",
        "status": "PASS_P6_HIDDEN" if all(gate_checks.values()) else "FAIL_P6_HIDDEN",
        "tables": PLANNED_TABLES,
        "completed_hands": completed_hands,
        "candidate_sha256": manifest["candidate_sha256"],
        "counts": dict(sorted(counts.items())),
        "strict_evidence": {
            "windows": len(windows),
            "distinct_tables": len(tables),
            "distinct_source_roots": len(roots),
            "mixes": sorted(mixes),
            "lower_shanten_windows": sum(
                1 for row in windows
                if row["dominant_facts"]["seven_pairs_shanten"]
                < row["parent_facts"]["seven_pairs_shanten"]
            ),
        },
        "max_candidate_operations": max_operations,
        "gate_checks": gate_checks,
        "runtime_counts": dict(sorted(runtime.items())),
        "windows": windows,
        "interpretation": "冻结P6在全新自然来源准确实现七对无损支配并对其余公开请求逐点评分保持P5；尚未通过完整桌赛安全门。",
        "selection_eligible": all(gate_checks.values()),
        "release_eligible": False,
    }
    write_json(_project_file(_PROJECT_ROOT, OUT / "result.json"), result)
    print(json.dumps({
        "status": result["status"],
        "tables": result["tables"],
        "completed_hands": result["completed_hands"],
        "strict_evidence": result["strict_evidence"],
        "max_candidate_operations": max_operations,
        "gate_checks": gate_checks,
    }, ensure_ascii=False, indent=2))
    if not all(gate_checks.values()):
        raise RuntimeError("P6 隐藏准入未通过")


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
