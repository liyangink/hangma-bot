"""隔离 P7 的 29 个自然触发，做同墙同策略的单窗口配对续打。"""

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
import statistics
import sys
from typing import Any, Mapping


HERE = Path(__file__).resolve().parent
ROUTE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15')
ROOT = _PROJECT_ROOT
for path in (_project_file(_PROJECT_ROOT, ROOT / "src"), _project_file(_PROJECT_ROOT, ROUTE / "tools"), HERE):
    sys.path.insert(0, str(path))

import confirmation_execution_identity as guard  # noqa: E402
import r18_p7_table_safety_topup as topup  # noqa: E402
import sitin_search as search  # noqa: E402
import strong_seed_batch as batch  # noqa: E402
from hangma_bot.kernel.serialization import window_key_from_json  # noqa: E402
from hangma_bot.offline.forced_action import ForceFirstActionPolicy  # noqa: E402
from hangma_bot.policy.action_value_policy import ActionValuePolicy  # noqa: E402
from hangma_bot.policy.action_value_seeds import ActionValueScorer  # noqa: E402


DATASET = topup.OUT / "natural-trigger-outcome-dataset.json"
OUT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p7-natural-trigger-counterfactual-01-20260922')


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


def parse_source(row: Mapping[str, Any]) -> dict[str, Any]:
    """从数据集行恢复自然面板来源与目标桌身份。"""

    mix, root_text, seat_text = str(row["source_id"]).split(":")
    game_id = str(row["request"]["observation"]["game_id"])
    if not game_id.startswith("sitin-stage:"):
        raise ValueError("未知自然桌 game_id")
    return {
        "mix": mix,
        "root_index": int(root_text[1:]),
        "focal_seat": int(seat_text[1:]),
        "source_id": row["source_id"],
        "table_id": game_id[len("sitin-stage:"):],
    }


def target_path(target: Mapping[str, Any]) -> Path:
    """返回单窗口配对证据路径。"""

    return _project_file(_PROJECT_ROOT, OUT / "pairs" / (str(target["target_id"]) + ".json"))


def source_paths() -> list[Path]:
    """列出冻结解释依赖。"""

    import hangma_bot.offline.forced_action as forced_action

    return [
        Path(__file__), DATASET, topup.CONTRACT, topup.CANDIDATE, topup.PARENT,
        Path(topup.natural.__file__), Path(forced_action.__file__),
    ]


def prepare() -> None:
    """冻结 29 个窗口和两臂动作；不看隔离续打结果。"""

    if OUT.exists():
        raise SystemExit("P7 自然触发隔离反事实目录已存在；拒绝覆盖")
    dataset = json.loads(DATASET.read_text(encoding="utf-8"))
    if dataset.get("status") != "COMPLETE" or len(dataset.get("rows") or []) != 29:
        raise ValueError("P7 自然触发数据集不完整")
    targets = []
    for index, row in enumerate(dataset["rows"], 1):
        targets.append({
            "target_id": "p7-natural-{0:02d}".format(index),
            "request_sha256": row["request_sha256"],
            "source": parse_source(row),
            "window_key": row["request"]["window_key"],
            "focal_physical_seat": int(row["request"]["observation"]["seat"]),
            "candidate_action": row["observable_features"]["candidate"]["action_key"],
            "parent_action": row["observable_features"]["parent"]["action_key"],
            "observable_features": row["observable_features"],
        })
    if len({row["request_sha256"] for row in targets}) != 29:
        raise ValueError("P7 自然触发窗口不唯一")
    planned_tables = len(targets) * 2 * 2
    OUT.mkdir(parents=True)
    authorization = batch.unified_document(
        batch_label=OUT.name,
        authorization_id="r18-p7-natural-trigger-counterfactual-01",
        accounts={"tables_full": planned_tables},
        issued_by="lead",
        issued_at_utc=search.utc_now(),
        legacy_alias=False,
    )
    authorization.update({
        "issuance_basis": "P7低频安全扩样的29个自然触发需要隔离单窗口效果，避免同来源多触发互相混淆",
        "scope": "29目标×P7/P5首动作×每阶段2桌；目标前后均使用冻结P7，只有精确WindowKey强制动作不同",
        "max_model_calls": 0,
        "confirmation_roots": 0,
    })
    write_json(_project_file(_PROJECT_ROOT, OUT / "authorization.json"), authorization)
    write_json(_project_file(_PROJECT_ROOT, OUT / "targets.json"), {
        "schema": "r18-p7-natural-trigger-counterfactual-targets/1",
        "targets": targets,
    })
    write_json(_project_file(_PROJECT_ROOT, OUT / "manifest.json"), {
        "schema": "r18-p7-natural-trigger-counterfactual-manifest/1",
        "created_at_utc": search.utc_now(),
        "runtime": guard.capture(source_paths=source_paths() + [
            _project_file(_PROJECT_ROOT, OUT / "authorization.json"), _project_file(_PROJECT_ROOT, OUT / "targets.json"),
        ]),
        "dataset_sha256": digest(DATASET),
        "candidate_sha256": digest(topup.CANDIDATE),
        "parent_sha256": digest(topup.PARENT),
        "contract_sha256": digest(topup.CONTRACT),
        "targets": len(targets),
        "planned_tables": planned_tables,
        "workers": 8,
        "intervention": "两臂从同一来源重放；仅目标WindowKey强制P7或P5首选动作一次；其余焦点窗口均由冻结P7决定",
        "interpretation": "每目标只有一个已发生未来牌序；用于隔离与诊断，不能单独训练阈值或授予准入",
        "selection_eligible": False,
        "release_eligible": False,
    })
    print(json.dumps({
        "status": "PREPARED", "targets": len(targets),
        "planned_tables": planned_tables,
    }, ensure_ascii=False))


def verify_manifest() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """核对冻结身份和目标。"""

    manifest = json.loads((_project_file(_PROJECT_ROOT, OUT / "manifest.json")).read_text(encoding="utf-8"))
    targets = json.loads((_project_file(_PROJECT_ROOT, OUT / "targets.json")).read_text(encoding="utf-8"))["targets"]
    checks = {
        "dataset": (manifest["dataset_sha256"], digest(DATASET)),
        "candidate": (manifest["candidate_sha256"], digest(topup.CANDIDATE)),
        "parent": (manifest["parent_sha256"], digest(topup.PARENT)),
        "contract": (manifest["contract_sha256"], digest(topup.CONTRACT)),
    }
    for label, (expected, actual) in checks.items():
        if expected != actual:
            raise ValueError(label + " 漂移")
    guard.verify(manifest["runtime"])
    return manifest, targets


def execute_arm(target: Mapping[str, Any], action_key: str) -> dict[str, Any]:
    """重放两桌阶段，在精确目标窗口强制一次动作。"""

    contract = json.loads(topup.CONTRACT.read_text(encoding="utf-8"))
    source = target["source"]
    plans = topup.natural.build_seat_stage_plans(
        contract=contract,
        opponent=str(source["mix"]),
        root_index=int(source["root_index"]),
        focal_seat=int(source["focal_seat"]),
        panel_seed=topup.PANEL_SEED,
    )
    target_window = window_key_from_json(target["window_key"])
    wrappers: list[ForceFirstActionPolicy] = []
    candidate_source = topup.CANDIDATE.read_text(encoding="utf-8")

    def policy_factory(monotonic: Any) -> Any:
        delegate = ActionValuePolicy(ActionValueScorer(
            "r18-P7-isolated-delegate-" + str(target["target_id"]),
            candidate_source,
        ))
        wrapper = ForceFirstActionPolicy(
            delegate,
            target_window=target_window,
            forced_action_key=action_key,
            policy_id="r18-P7-isolated-" + action_key,
        )
        wrappers.append(wrapper)
        return wrapper

    stage = topup.natural.run_arm_stage(
        arm="candidate",
        plans=plans,
        candidate_scorer=ActionValueScorer("r18-P7-isolated-unused", candidate_source),
        opponent_policies=contract["panel"]["opponent_scenarios"][
            str(source["mix"])
        ]["opponent_policies"],
        versions_block=topup.natural.stage.contract_versions_block(contract),
        step_limit=int(contract["stop"]["step_limit"]),
        value_limits=topup.LIMITS,
        candidate_policy_factory=policy_factory,
    )
    target_table = next(
        (table for table in stage.get("tables") or []
         if table["table_id"] == source["table_id"]),
        None,
    )
    runtime: Counter[str] = Counter()
    for table in stage.get("tables") or []:
        runtime.update(table.get("result", {}).get("runtime_counts") or {})
    scores = None if target_table is None else target_table.get("scores_by_seat")
    return {
        "action_key": action_key,
        "status": stage.get("status"),
        "error": stage.get("error"),
        "tables": len(stage.get("tables") or []),
        "force_count": sum(item.force_count for item in wrappers),
        "target_table_found": target_table is not None,
        "target_table_scores_by_seat": scores,
        "target_table_focal_score": (
            None if scores is None else scores[int(target["focal_physical_seat"])]
        ),
        "focal_stage_score": stage.get("focal_stage_score"),
        "runtime_counts": dict(sorted(runtime.items())),
    }


def execute_pair(target: Mapping[str, Any]) -> dict[str, Any]:
    """执行同目标的 P7/P5 首动作两臂。"""

    candidate = execute_arm(target, str(target["candidate_action"]))
    parent = execute_arm(target, str(target["parent_action"]))
    table_delta = None
    stage_delta = None
    if candidate["target_table_focal_score"] is not None and parent["target_table_focal_score"] is not None:
        table_delta = candidate["target_table_focal_score"] - parent["target_table_focal_score"]
    if candidate["focal_stage_score"] is not None and parent["focal_stage_score"] is not None:
        stage_delta = candidate["focal_stage_score"] - parent["focal_stage_score"]
    mechanical_ok = all(
        arm["status"] == "complete"
        and arm["tables"] == 2
        and arm["force_count"] == 1
        and arm["target_table_found"]
        and all(value == 0 for value in arm["runtime_counts"].values())
        for arm in (candidate, parent)
    )
    return {
        "target": dict(target),
        "candidate": candidate,
        "parent": parent,
        "candidate_minus_parent_target_table_score": table_delta,
        "candidate_minus_parent_stage_score": stage_delta,
        "mechanical_ok": mechanical_ok,
    }


def run() -> None:
    """并行完成 29 个单窗口配对。"""

    manifest, targets = verify_manifest()
    authorization = json.loads((_project_file(_PROJECT_ROOT, OUT / "authorization.json")).read_text(encoding="utf-8"))
    topup.natural.require_authorization(authorization)
    ledger = search.ActionValueLedger.load(
        _project_file(_PROJECT_ROOT, OUT / "ledger.json"),
        authorized_budgets=search.av_ledger_budgets_from_authorization(authorization),
    )
    pending = []
    completed_tables = 0
    for target in targets:
        path = target_path(target)
        if path.exists():
            row = json.loads(path.read_text(encoding="utf-8"))
            if not row.get("mechanical_ok"):
                raise ValueError("既有隔离配对不完整")
            completed_tables += 4
        else:
            pending.append(target)
    reservation = ledger.reserve(
        step_id="r18-p7:natural-trigger-counterfactual",
        account="tables_full",
        amount=manifest["planned_tables"] - completed_tables,
        note="P7自然七对触发的单窗口P7/P5动作隔离续打",
    )
    failures = []
    executed = 0
    usage_unknown = False
    try:
        with concurrent.futures.ProcessPoolExecutor(max_workers=manifest["workers"]) as pool:
            futures = {pool.submit(execute_pair, target): target for target in pending}
            for future in concurrent.futures.as_completed(futures):
                target = futures[future]
                pair = None
                try:
                    pair = future.result()
                    if not pair["mechanical_ok"]:
                        raise RuntimeError("单窗口隔离机械条件失败")
                    write_json(target_path(target), pair)
                    executed += 4
                    completed_tables += 4
                    print(json.dumps({
                        "completed_targets": completed_tables // 4,
                        "planned_targets": len(targets),
                    }, ensure_ascii=False), flush=True)
                except Exception as exc:  # noqa: BLE001
                    if pair is None:
                        usage_unknown = True
                    failures.append({
                        "target_id": target["target_id"],
                        "error": type(exc).__name__ + ": " + str(exc),
                    })
    finally:
        if usage_unknown:
            ledger.settle(reservation, usage_unknown=True, note="子进程未返回；保守结算")
        else:
            ledger.settle(reservation, actual=executed, note="按完整隔离配对桌数结算")
    files = list((_project_file(_PROJECT_ROOT, OUT / "pairs")).glob("*.json")) if (_project_file(_PROJECT_ROOT, OUT / "pairs")).exists() else []
    actual = len(files) * 4
    write_json(_project_file(_PROJECT_ROOT, OUT / "run-summary.json"), {
        "schema": "r18-p7-natural-trigger-counterfactual-run/1",
        "pair_files": len(files),
        "actual_tables": actual,
        "failures": failures,
        "spent": ledger.account_summary(),
    })
    if failures or actual != manifest["planned_tables"] or len(files) != len(targets):
        raise RuntimeError("P7 自然触发隔离续打不完整")
    print(json.dumps({"status": "RUN_COMPLETE", "tables": actual}, ensure_ascii=False))


def analyze() -> None:
    """汇总单未来隔离效果，只形成诊断证据。"""

    manifest, targets = verify_manifest()
    run_summary = json.loads((_project_file(_PROJECT_ROOT, OUT / "run-summary.json")).read_text(encoding="utf-8"))
    if run_summary["failures"] or run_summary["actual_tables"] != manifest["planned_tables"]:
        raise ValueError("P7 自然触发隔离续打不完整")
    rows = [json.loads(target_path(target).read_text(encoding="utf-8")) for target in targets]
    values = [float(row["candidate_minus_parent_target_table_score"]) for row in rows]
    by_source: dict[str, list[float]] = {}
    for row, value in zip(rows, values):
        by_source.setdefault(str(row["target"]["source"]["source_id"]), []).append(value)
    result = {
        "schema": "r18-p7-natural-trigger-counterfactual-result/1",
        "status": "COMPLETE_P7_NATURAL_TRIGGER_COUNTERFACTUAL",
        "mechanical_ok_pairs": sum(row["mechanical_ok"] for row in rows),
        "pairs": len(rows),
        "summary": {
            "mean_target_table_delta": statistics.fmean(values),
            "median_target_table_delta": statistics.median(values),
            "positive": sum(value > 0 for value in values),
            "zero": sum(value == 0 for value in values),
            "negative": sum(value < 0 for value in values),
            "values": values,
            "sources_with_multiple_targets": sum(len(items) > 1 for items in by_source.values()),
        },
        "rows": rows,
        "interpretation": "同一已发生未来牌序下的单窗口隔离；可定位反例，不能把单未来结果直接拟合成线上阈值",
        "selection_eligible": False,
        "release_eligible": False,
    }
    write_json(_project_file(_PROJECT_ROOT, OUT / "result.json"), result)
    print(json.dumps({
        "status": result["status"], **result["summary"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("prepare", "run", "analyze"))
    args = parser.parse_args()
    globals()[args.operation]()
