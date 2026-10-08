"""R18 自然三财神机会：立即胡与 oracle 动作的配对完整桌续打。

目标窗口来自冻结的 512 桌稳定 V2 自然暴露率面板。每个目标分别重放
相同两桌阶段，只在目标 ``WindowKey`` 把焦点 V2 的首选强制为 ``hu`` 或
冻结 oracle 动作，之后继续使用稳定 V2。该批用于判断自然“保财”缺口是否
值得扩展 horizon；不直接准入候选或形成发布结论。
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
import math
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
import sitin_natural_panel as natural  # noqa: E402
import sitin_search as search  # noqa: E402
import strong_seed_batch as batch  # noqa: E402
from hangma_bot.hangma.interface import ValueAnalysisLimits  # noqa: E402
from hangma_bot.kernel.serialization import window_key_from_json  # noqa: E402
from hangma_bot.offline.forced_action import ForceFirstActionPolicy  # noqa: E402
from hangma_bot.policy.action_value_seeds import ActionValueScorer  # noqa: E402
from hangma_bot.policy.heuristic_v2 import ComparableHeuristicPolicyV2  # noqa: E402


OUT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-natural-opportunity-counterfactual-01-20260922')
EXPOSURE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p3-natural-exposure-01-20260922')
CONTRACT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/contracts/group-dev-v1.json')
CANDIDATE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p3-author-01-20260922/generation/candidate.py')
LIMITS = ValueAnalysisLimits(max_expansions=20_000, max_routes_per_candidate=256)
BOOTSTRAP_REPLICATES = 20_000


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


def source_paths() -> list[Path]:
    return [
        Path(__file__),
        _project_file(_PROJECT_ROOT, EXPOSURE / "manifest.json"),
        _project_file(_PROJECT_ROOT, EXPOSURE / "result.json"),
        CONTRACT,
        CANDIDATE,
        Path(natural.__file__),
    ]


def _parse_source(record: Mapping[str, Any]) -> dict[str, Any]:
    """从冻结桌身份恢复自然面板来源；格式不符立即拒绝。"""

    game_id = str(record["game_id"])
    marker = "sitin-stage:np-"
    if not game_id.startswith(marker):
        raise ValueError("未知自然桌 game_id: " + game_id)
    body = game_id[len(marker):]
    pieces = body.split("-")
    # {mix}-{panel_seed}-rNN-sN-tN；mix 当前是单段 H/M。
    if len(pieces) != 5:
        raise ValueError("自然桌 game_id 分段不符: " + game_id)
    mix, panel_text, root_text, seat_text, table_text = pieces
    if not root_text.startswith("r") or not seat_text.startswith("s") or not table_text.startswith("t"):
        raise ValueError("自然桌 game_id 身份段不符: " + game_id)
    return {
        "mix": mix,
        "panel_seed": int(panel_text),
        "root_index": int(root_text[1:]),
        "focal_seat": int(seat_text[1:]),
        "table_no": int(table_text[1:]),
        "table_id": game_id[len("sitin-stage:"):],
    }


def prepare() -> None:
    """冻结全部 11 个自然目标、动作与方向裁定，不看续打结果。"""

    if OUT.exists():
        raise SystemExit("自然机会反事实目录已存在；拒绝覆盖")
    exposure = json.loads((_project_file(_PROJECT_ROOT, EXPOSURE / "result.json")).read_text(encoding="utf-8"))
    manifest = json.loads((_project_file(_PROJECT_ROOT, EXPOSURE / "manifest.json")).read_text(encoding="utf-8"))
    if exposure.get("status") != "COMPLETE_EXPOSURE_ESTIMATE":
        raise ValueError("自然暴露率面板尚未完成")
    if exposure.get("tables") != manifest.get("planned_tables"):
        raise ValueError("自然暴露率桌数与冻结清单不一致")
    targets = []
    counts: Counter[str] = Counter()
    for index, record in enumerate(exposure["opportunity_records"], 1):
        optimal = list(record["oracle_optimal"])
        if "discard:白" in optimal:
            stratum = "natural_piao_positive_control"
            action = "discard:白"
        else:
            discards = sorted(key for key in optimal if key.startswith("discard:"))
            if not discards:
                raise ValueError("自然机会 oracle 没有可干预弃牌")
            stratum = "natural_keep_wealth_probe"
            action = discards[0]
        source = _parse_source(record)
        target = {
            "target_id": "natural-{0:02d}".format(index),
            "stratum": stratum,
            "source": source,
            "window_key": record["window_key"],
            "window_identity_sha256": record["window_identity_sha256"],
            "focal_physical_seat": record["seat"],
            "dealer_seat": record["dealer_seat"],
            "round_no": record["round_no"],
            "remaining_tile_count": record["remaining_tile_count"],
            "meld_counts": record["meld_counts"],
            "river_lengths": record["river_lengths"],
            "oracle_optimal": optimal,
            "intervention_action": action,
            "reference_action": "hu",
        }
        targets.append(target)
        counts[stratum] += 1
    if counts != Counter({
        "natural_keep_wealth_probe": 9,
        "natural_piao_positive_control": 2,
    }):
        raise ValueError("自然机会分层数量漂移：" + repr(counts))

    planned_tables = len(targets) * 2 * 2  # 每目标两臂，每臂两桌阶段
    OUT.mkdir(parents=True)
    authorization = batch.unified_document(
        batch_label=OUT.name,
        authorization_id="r18-natural-opportunity-counterfactual-01",
        accounts={"tables_full": planned_tables},
        issued_by="lead",
        issued_at_utc=search.utc_now(),
        legacy_alias=False,
    )
    authorization.update({
        "issuance_basis": "冻结512桌自然暴露率发现11个真实机会窗口；先校准方向再决定是否开放保财作者任务",
        "scope": "11目标×胡/冻结oracle动作×每阶段2桌；只在精确WindowKey干预一次",
        "max_model_calls": 0,
        "confirmation_roots": 0,
    })
    write_json(_project_file(_PROJECT_ROOT, OUT / "authorization.json"), authorization)
    write_json(_project_file(_PROJECT_ROOT, OUT / "targets.json"), {
        "schema": "r18-natural-opportunity-counterfactual-targets/1",
        "targets": targets,
    })
    write_json(_project_file(_PROJECT_ROOT, OUT / "manifest.json"), {
        "schema": "r18-natural-opportunity-counterfactual-manifest/1",
        "created_at_utc": search.utc_now(),
        "runtime": guard.capture(source_paths=source_paths() + [
            _project_file(_PROJECT_ROOT, OUT / "authorization.json"), _project_file(_PROJECT_ROOT, OUT / "targets.json")
        ]),
        "exposure_result_sha256": digest(_project_file(_PROJECT_ROOT, EXPOSURE / "result.json")),
        "candidate_sha256": digest(CANDIDATE),
        "contract_sha256": digest(CONTRACT),
        "targets": len(targets),
        "strata": dict(sorted(counts.items())),
        "planned_tables": planned_tables,
        "workers": 8,
        "frozen_intervention_rule": "oracle最优含discard:白则强制白；否则按action_key排序取首个非白弃牌",
        "decision_rule": {
            "piao_positive_control": "2/2目标桌差>0，否则反事实重放或代理口径失败",
            "reopen_keep_horizon_research": "保财9题至少8题目标桌差>0、均值>0且配对均值bootstrap 95%下界>0",
            "otherwise": "KEEP_WEALTH_DIRECTION_PAUSED",
        },
        "selection_eligible": False,
        "release_eligible": False,
    })
    print(json.dumps({
        "status": "PREPARED",
        "targets": len(targets),
        "planned_tables": planned_tables,
        "strata": dict(counts),
    }, ensure_ascii=False))


def verify_manifest() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    manifest = json.loads((_project_file(_PROJECT_ROOT, OUT / "manifest.json")).read_text(encoding="utf-8"))
    targets = json.loads((_project_file(_PROJECT_ROOT, OUT / "targets.json")).read_text(encoding="utf-8"))["targets"]
    if manifest["exposure_result_sha256"] != digest(_project_file(_PROJECT_ROOT, EXPOSURE / "result.json")):
        raise ValueError("自然暴露率结果漂移")
    if manifest["candidate_sha256"] != digest(CANDIDATE):
        raise ValueError("P3 身份漂移")
    if manifest["contract_sha256"] != digest(CONTRACT):
        raise ValueError("桌赛合同漂移")
    guard.verify(manifest["runtime"])
    return manifest, targets


def execute_arm(target: Mapping[str, Any], action_key: str) -> dict[str, Any]:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    source = target["source"]
    plans = natural.build_seat_stage_plans(
        contract=contract,
        opponent=str(source["mix"]),
        root_index=int(source["root_index"]),
        focal_seat=int(source["focal_seat"]),
        panel_seed=int(source["panel_seed"]),
    )
    target_window = window_key_from_json(target["window_key"])
    wrappers: list[ForceFirstActionPolicy] = []

    def policy_factory(monotonic: Any) -> Any:
        wrapper = ForceFirstActionPolicy(
            ComparableHeuristicPolicyV2(monotonic=monotonic),
            target_window=target_window,
            forced_action_key=action_key,
            policy_id="r18-natural-cf-" + action_key,
        )
        wrappers.append(wrapper)
        return wrapper

    candidate_source = CANDIDATE.read_text(encoding="utf-8")
    stage = natural.run_arm_stage(
        arm="candidate",
        plans=plans,
        candidate_scorer=ActionValueScorer("r18-natural-cf-unused", candidate_source),
        opponent_policies=contract["panel"]["opponent_scenarios"][
            str(source["mix"])
        ]["opponent_policies"],
        versions_block=natural.stage.contract_versions_block(contract),
        step_limit=int(contract["stop"]["step_limit"]),
        value_limits=LIMITS,
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
    reference = execute_arm(target, str(target["reference_action"]))
    intervention = execute_arm(target, str(target["intervention_action"]))
    table_delta = None
    stage_delta = None
    if reference["target_table_focal_score"] is not None and intervention["target_table_focal_score"] is not None:
        table_delta = intervention["target_table_focal_score"] - reference["target_table_focal_score"]
    if reference["focal_stage_score"] is not None and intervention["focal_stage_score"] is not None:
        stage_delta = intervention["focal_stage_score"] - reference["focal_stage_score"]
    mechanical_ok = all(
        arm["status"] == "complete"
        and arm["tables"] == 2
        and arm["force_count"] == 1
        and arm["target_table_found"]
        and all(value == 0 for value in arm["runtime_counts"].values())
        for arm in (reference, intervention)
    )
    return {
        "target": dict(target),
        "reference": reference,
        "intervention": intervention,
        "intervention_minus_hu_target_table_score": table_delta,
        "intervention_minus_hu_stage_score": stage_delta,
        "mechanical_ok": mechanical_ok,
    }


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
                raise ValueError("既有目标对不完整：" + str(path))
            completed_tables += 4
        else:
            pending.append(target)
    reservation = ledger.reserve(
        step_id="r18:natural-opportunity-counterfactual",
        account="tables_full",
        amount=manifest["planned_tables"] - completed_tables,
        note="自然机会胡/冻结oracle动作配对续打",
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
                except Exception as exc:  # noqa: BLE001 - 保留失败目标
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
        "schema": "r18-natural-opportunity-counterfactual-run/1",
        "pair_files": len(files),
        "actual_tables": actual,
        "failures": failures,
        "spent": ledger.account_summary(),
    })
    if failures or actual != manifest["planned_tables"] or len(files) != len(targets):
        raise RuntimeError("自然机会配对续打不完整")
    print(json.dumps({"status": "RUN_COMPLETE", "tables": actual}, ensure_ascii=False))


def bootstrap_interval(values: list[float], salt: int) -> tuple[float, float]:
    rng = random.Random(202609220900 + salt)
    means = []
    for _ in range(BOOTSTRAP_REPLICATES):
        means.append(sum(values[rng.randrange(len(values))] for _ in values) / len(values))
    means.sort()
    return (
        means[math.floor(0.025 * (len(means) - 1))],
        means[math.ceil(0.975 * (len(means) - 1))],
    )


def analyze() -> None:
    manifest, targets = verify_manifest()
    run_summary = json.loads((_project_file(_PROJECT_ROOT, OUT / "run-summary.json")).read_text(encoding="utf-8"))
    if run_summary["failures"] or run_summary["actual_tables"] != manifest["planned_tables"]:
        raise ValueError("自然机会配对续打不完整")
    rows = [json.loads(target_path(target).read_text(encoding="utf-8")) for target in targets]
    strata = {}
    for salt, stratum in enumerate((
        "natural_piao_positive_control", "natural_keep_wealth_probe"
    ), 1):
        selected = [row for row in rows if row["target"]["stratum"] == stratum]
        values = [float(row["intervention_minus_hu_target_table_score"]) for row in selected]
        lo, hi = bootstrap_interval(values, salt)
        strata[stratum] = {
            "pairs": len(values),
            "mean_target_table_delta": statistics.fmean(values),
            "median_target_table_delta": statistics.median(values),
            "positive": sum(value > 0 for value in values),
            "zero": sum(value == 0 for value in values),
            "negative": sum(value < 0 for value in values),
            "bootstrap_95_mean": [lo, hi],
            "values": values,
        }
    piao_ok = strata["natural_piao_positive_control"]["positive"] == 2
    keep = strata["natural_keep_wealth_probe"]
    reopen = (
        keep["positive"] >= 8
        and keep["mean_target_table_delta"] > 0
        and keep["bootstrap_95_mean"][0] > 0
    )
    decision = (
        "REOPEN_KEEP_HORIZON_RESEARCH"
        if piao_ok and reopen
        else "KEEP_WEALTH_DIRECTION_PAUSED"
    )
    write_json(_project_file(_PROJECT_ROOT, OUT / "result.json"), {
        "schema": "r18-natural-opportunity-counterfactual-result/1",
        "status": "COMPLETE_NATURAL_COUNTERFACTUAL",
        "mechanical_ok_pairs": sum(row["mechanical_ok"] for row in rows),
        "pairs": len(rows),
        "strata": strata,
        "checks": {
            "all_pairs_mechanical_ok": all(row["mechanical_ok"] for row in rows),
            "piao_positive_control_2_of_2": piao_ok,
            "keep_positive_at_least_8_of_9": keep["positive"] >= 8,
            "keep_mean_positive": keep["mean_target_table_delta"] > 0,
            "keep_bootstrap_lower_positive": keep["bootstrap_95_mean"][0] > 0,
        },
        "decision": decision,
        "interpretation": "一次冻结自然未来牌序的探索校准；若重开也只重开horizon/生存模型研究，不直接发作者任务",
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
