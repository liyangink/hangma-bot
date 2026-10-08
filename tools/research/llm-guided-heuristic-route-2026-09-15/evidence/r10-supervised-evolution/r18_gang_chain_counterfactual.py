"""R18 自然杠链直接分歧的配对完整桌续打。

从冻结杠链自然探针中只取“一次补牌代理与 V2 在是否杠上直接相反”的
窗口。同一两桌阶段分别强制 V2 原动作和 oracle 首个最优动作，之后恢复
稳定 V2。结果只决定下一版定向题库的分层，不直接开放作者任务。
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
import r18_natural_opportunity_counterfactual as shared  # noqa: E402
import sitin_natural_panel as natural  # noqa: E402
import sitin_search as search  # noqa: E402
import strong_seed_batch as batch  # noqa: E402


OUT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-gang-chain-counterfactual-01-20260922')
PROBE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-gang-chain-natural-probe-02-20260922')
CONTRACT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/contracts/group-dev-v1.json')
CANDIDATE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p3-author-01-20260922/generation/candidate.py')


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def target_path(target: Mapping[str, Any]) -> Path:
    return _project_file(_PROJECT_ROOT, OUT / "pairs" / (str(target["target_id"]) + ".json"))


def prepare() -> None:
    """冻结全部直接杠/不杠分歧；排除两边都不杠的普通弃牌分歧。"""

    if OUT.exists():
        raise SystemExit("杠链反事实目录已存在；拒绝覆盖")
    probe = json.loads((_project_file(_PROJECT_ROOT, PROBE / "result.json")).read_text(encoding="utf-8"))
    probe_manifest = json.loads((_project_file(_PROJECT_ROOT, PROBE / "manifest.json")).read_text(encoding="utf-8"))
    if probe.get("status") != "COMPLETE_GANG_CHAIN_PROBE":
        raise ValueError("杠链自然探针尚未完成")
    targets = []
    for row in probe["windows"]:
        v2 = str(row["v2_action"])
        if v2 in row["oracle_optimal"]:
            continue
        oracle = str(sorted(row["oracle_optimal"])[0])
        v2_gang = v2.startswith("gang:")
        oracle_gang = oracle.startswith("gang:")
        if v2_gang == oracle_gang:
            continue
        source = shared._parse_source(row)
        stratum = "proxy_promotes_gang" if oracle_gang else "proxy_rejects_gang"
        targets.append({
            "target_id": "gang-cf-{0:02d}".format(len(targets) + 1),
            "stratum": stratum,
            "source": source,
            "window_key": row["window_key"],
            "focal_physical_seat": row["seat"],
            "dealer_seat": row["dealer_seat"],
            "round_no": row["round_no"],
            "remaining_tile_count": row["remaining_tile_count"],
            "gang_kinds": row["gang_kinds"],
            "gang_action_keys": row["gang_action_keys"],
            "reference_action": v2,
            "intervention_action": oracle,
            "oracle_optimal": row["oracle_optimal"],
        })
    strata = {}
    for name in ("proxy_promotes_gang", "proxy_rejects_gang"):
        strata[name] = sum(target["stratum"] == name for target in targets)
    if strata != {"proxy_promotes_gang": 4, "proxy_rejects_gang": 3}:
        raise ValueError("直接杠分歧数量漂移：" + repr(strata))
    planned_tables = len(targets) * 4
    OUT.mkdir(parents=True)
    authorization = batch.unified_document(
        batch_label=OUT.name,
        authorization_id="r18-gang-chain-counterfactual-01",
        accounts={"tables_full": planned_tables},
        issued_by="lead",
        issued_at_utc=search.utc_now(),
        legacy_alias=False,
    )
    authorization.update({
        "issuance_basis": "512桌自然杠链探针发现7个V2与一次补牌代理直接杠/不杠分歧",
        "scope": "7目标×V2动作/oracle动作×每阶段2桌；精确WindowKey干预一次",
        "max_model_calls": 0,
        "confirmation_roots": 0,
    })
    write_json(_project_file(_PROJECT_ROOT, OUT / "authorization.json"), authorization)
    write_json(_project_file(_PROJECT_ROOT, OUT / "targets.json"), {
        "schema": "r18-gang-chain-counterfactual-targets/1",
        "targets": targets,
    })
    write_json(_project_file(_PROJECT_ROOT, OUT / "manifest.json"), {
        "schema": "r18-gang-chain-counterfactual-manifest/1",
        "created_at_utc": search.utc_now(),
        "runtime": guard.capture(source_paths=[
            Path(__file__), Path(shared.__file__), _project_file(_PROJECT_ROOT, PROBE / "manifest.json"),
            _project_file(_PROJECT_ROOT, PROBE / "result.json"), CONTRACT, CANDIDATE,
            _project_file(_PROJECT_ROOT, OUT / "authorization.json"), _project_file(_PROJECT_ROOT, OUT / "targets.json"),
        ]),
        "probe_result_sha256": digest(_project_file(_PROJECT_ROOT, PROBE / "result.json")),
        "probe_panel_seed": probe_manifest["panel_seed"],
        "candidate_sha256": digest(CANDIDATE),
        "contract_sha256": digest(CONTRACT),
        "targets": len(targets),
        "strata": strata,
        "planned_tables": planned_tables,
        "workers": 7,
        "target_rule": "V2不在oracle最优且V2动作/oracle首动作只有一边是gang",
        "decision_rule": "本批只校准方向；任一分层非全同向即同时建立应杠/不应杠正负控，不发作者任务",
        "selection_eligible": False,
        "release_eligible": False,
    })
    print(json.dumps({
        "status": "PREPARED", "targets": len(targets),
        "strata": strata, "planned_tables": planned_tables,
    }, ensure_ascii=False))


def verify_manifest() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    manifest = json.loads((_project_file(_PROJECT_ROOT, OUT / "manifest.json")).read_text(encoding="utf-8"))
    targets = json.loads((_project_file(_PROJECT_ROOT, OUT / "targets.json")).read_text(encoding="utf-8"))["targets"]
    if manifest["probe_result_sha256"] != digest(_project_file(_PROJECT_ROOT, PROBE / "result.json")):
        raise ValueError("杠链自然探针结果漂移")
    if manifest["candidate_sha256"] != digest(CANDIDATE):
        raise ValueError("P3 身份漂移")
    if manifest["contract_sha256"] != digest(CONTRACT):
        raise ValueError("合同漂移")
    guard.verify(manifest["runtime"])
    return manifest, targets


def execute_pair(target: Mapping[str, Any]) -> dict[str, Any]:
    return shared.execute_pair(target)


def run() -> None:
    manifest, targets = verify_manifest()
    authorization = json.loads((_project_file(_PROJECT_ROOT, OUT / "authorization.json")).read_text(encoding="utf-8"))
    natural.require_authorization(authorization)
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
                raise ValueError("既有配对不完整：" + str(path))
            completed_tables += 4
        else:
            pending.append(target)
    reservation = ledger.reserve(
        step_id="r18:gang-chain-counterfactual",
        account="tables_full",
        amount=manifest["planned_tables"] - completed_tables,
        note="自然杠链直接分歧配对续打",
    )
    failures = []
    executed = 0
    usage_unknown = False
    try:
        with concurrent.futures.ProcessPoolExecutor(max_workers=manifest["workers"]) as pool:
            futures = {pool.submit(execute_pair, target): target for target in pending}
            for future in concurrent.futures.as_completed(futures):
                target = futures[future]
                result = None
                try:
                    result = future.result()
                    if not result["mechanical_ok"]:
                        raise RuntimeError("配对机械条件失败")
                    write_json(target_path(target), result)
                    executed += 4
                    completed_tables += 4
                    print(json.dumps({
                        "completed_targets": completed_tables // 4,
                        "planned_targets": len(targets),
                    }, ensure_ascii=False), flush=True)
                except Exception as exc:  # noqa: BLE001
                    if result is None:
                        usage_unknown = True
                    failures.append({
                        "target_id": target["target_id"],
                        "error": type(exc).__name__ + ": " + str(exc),
                    })
    finally:
        if usage_unknown:
            ledger.settle(reservation, usage_unknown=True, note="子进程未返回；保守结算")
        else:
            ledger.settle(reservation, actual=executed, note="按完整配对桌数结算")
    files = list((_project_file(_PROJECT_ROOT, OUT / "pairs")).glob("*.json")) if (_project_file(_PROJECT_ROOT, OUT / "pairs")).exists() else []
    actual = len(files) * 4
    write_json(_project_file(_PROJECT_ROOT, OUT / "run-summary.json"), {
        "schema": "r18-gang-chain-counterfactual-run/1",
        "pair_files": len(files), "actual_tables": actual,
        "failures": failures, "spent": ledger.account_summary(),
    })
    if failures or actual != manifest["planned_tables"] or len(files) != len(targets):
        raise RuntimeError("杠链反事实执行不完整")
    print(json.dumps({"status": "RUN_COMPLETE", "tables": actual}, ensure_ascii=False))


def analyze() -> None:
    manifest, targets = verify_manifest()
    summary = json.loads((_project_file(_PROJECT_ROOT, OUT / "run-summary.json")).read_text(encoding="utf-8"))
    if summary["failures"] or summary["actual_tables"] != manifest["planned_tables"]:
        raise ValueError("杠链反事实执行不完整")
    rows = [json.loads(target_path(target).read_text(encoding="utf-8")) for target in targets]
    strata = {}
    for name in ("proxy_promotes_gang", "proxy_rejects_gang"):
        selected = [row for row in rows if row["target"]["stratum"] == name]
        values = [float(row["intervention_minus_hu_target_table_score"])
                  for row in selected]
        # 共享执行器的字段名沿用“minus_hu”，这里参考动作实际是 V2；重新命名解释。
        strata[name] = {
            "pairs": len(values),
            "oracle_action_minus_v2_mean": statistics.fmean(values),
            "oracle_action_minus_v2_median": statistics.median(values),
            "positive": sum(value > 0 for value in values),
            "zero": sum(value == 0 for value in values),
            "negative": sum(value < 0 for value in values),
            "values": values,
        }
    all_same_direction = all(
        data["positive"] == data["pairs"] for data in strata.values()
    )
    write_json(_project_file(_PROJECT_ROOT, OUT / "result.json"), {
        "schema": "r18-gang-chain-counterfactual-result/1",
        "status": "COMPLETE_GANG_CHAIN_COUNTERFACTUAL",
        "pairs": len(rows),
        "mechanical_ok_pairs": sum(row["mechanical_ok"] for row in rows),
        "strata": strata,
        "proxy_all_direct_disagreements_supported": all_same_direction,
        "decision": (
            "BUILD_DIRECTIONAL_GANG_BANK"
            if all_same_direction else "BUILD_GANG_POSITIVE_AND_NEGATIVE_CONTROLS"
        ),
        "author_task_open": False,
        "interpretation": "一次自然未来牌序的方向校准；下一步仍需跨状态与未来墙重复",
        "selection_eligible": False,
        "release_eligible": False,
    })
    print(json.dumps(json.loads((_project_file(_PROJECT_ROOT, OUT / "result.json")).read_text(encoding="utf-8")), ensure_ascii=False, indent=2))


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
