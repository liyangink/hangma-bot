"""R18 P21：P20 非支配杠/非杠前沿的开发集共同隐藏世界教师。

P20 的三个开放层各冻结 32 个独立牌山根，结果盲地分成 16 个开发状态和
16 个复验状态。本程序只捕获、运行并分析开发状态；复验状态的公开请求虽
已冻结，但在候选规则冻结前不生成任何结果标签。每个状态在 32 个公开状态
一致的隐藏世界中比较 P5 原杠与 P5 最高分非杠，之后两臂都恢复 P5。
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
import r18_p20_gang_pair_natural_exposure as p20  # noqa: E402
import sitin_natural_panel as natural  # noqa: E402
import sitin_search as search  # noqa: E402
import strong_seed_batch as batch  # noqa: E402


OUT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p21-gang-pair-development-teacher-01-20260922')
DATASET = p20.OUT / "dataset.json"
EXPOSURE_RESULT = p20.OUT / "result.json"
CONTRACT = p20.CONTRACT
PARENT = p20.PARENT
OPEN_FAMILIES = (
    "concealed.gang_to_nongang",
    "exposed.gang_to_nongang",
    "added.gang_to_nongang",
)
STATES_PER_FAMILY = 32
DEVELOPMENT_PER_FAMILY = 16
ROLLOUTS_PER_STATE = 32
WORKERS = 8
SELECTION_SALT = "r18-p21-gang-pair-selection/v1"
SPLIT_SALT = "r18-p21-gang-pair-split/v1"


def write_json(path: Path, value: Any) -> None:
    """写入稳定 UTF-8 JSON。"""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def digest(path: Path) -> str:
    """返回文件 SHA-256。"""

    return hashlib.sha256(path.read_bytes()).hexdigest()


def value_digest(value: Any) -> str:
    """返回规范 JSON 值摘要。"""

    return hashlib.sha256(json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")).hexdigest()


def state_projection(request_json: Mapping[str, Any]) -> dict[str, Any]:
    """提取证明同一合法决策状态所需的公开请求字段。"""

    return {
        "observation": request_json["observation"],
        "rules": request_json["rules"],
        "trigger_seq": request_json["trigger_seq"],
        "window_key": request_json["window_key"],
    }


def _hash_order(row: Mapping[str, Any], salt: str) -> str:
    payload = "|".join((
        salt, str(row["family"]), str(row["source"]["source_root_id"]),
        str(row["request_sha256"]),
    ))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def selected_rows() -> list[dict[str, Any]]:
    """按家族和 H/M 来源结果盲取样，再冻结开发/复验各 16 个状态。"""

    result = json.loads(EXPOSURE_RESULT.read_text(encoding="utf-8"))
    if tuple(result.get("families_open_for_p21") or ()) != OPEN_FAMILIES:
        raise ValueError("P20 开放家族与 P21 冻结假设不一致")
    rows = [
        row for row in json.loads(DATASET.read_text(encoding="utf-8"))["rows"]
        if row["family"] in OPEN_FAMILIES and row["sample_role"] == "discovery"
    ]
    selected: list[dict[str, Any]] = []
    for family in OPEN_FAMILIES:
        pools = {
            mix: sorted(
                (row for row in rows if row["family"] == family and row["source"]["mix"] == mix),
                key=lambda row: _hash_order(row, SELECTION_SALT),
            )
            for mix in ("H", "M")
        }
        quotas = {mix: min(16, len(pool)) for mix, pool in pools.items()}
        deficit = STATES_PER_FAMILY - sum(quotas.values())
        for mix in sorted(pools, key=lambda item: (-len(pools[item]), item)):
            room = len(pools[mix]) - quotas[mix]
            take = min(deficit, room)
            quotas[mix] += take
            deficit -= take
        if deficit:
            raise ValueError(family + " 没有足够的独立牌山根")

        development_quotas = {mix: quotas[mix] // 2 for mix in pools}
        development_deficit = DEVELOPMENT_PER_FAMILY - sum(development_quotas.values())
        for mix in sorted(pools):
            if development_deficit <= 0:
                break
            if development_quotas[mix] < quotas[mix]:
                development_quotas[mix] += 1
                development_deficit -= 1

        for mix in ("H", "M"):
            chosen = sorted(
                pools[mix][:quotas[mix]], key=lambda row: _hash_order(row, SPLIT_SALT),
            )
            for index, row in enumerate(chosen):
                item = dict(row)
                item["split"] = (
                    "development" if index < development_quotas[mix] else "replication"
                )
                selected.append(item)
    return sorted(selected, key=lambda row: (
        row["family"], row["split"], row["source"]["mix"],
        row["source"]["source_root_id"], row["request_sha256"],
    ))


def targets() -> list[dict[str, Any]]:
    """把 P20 冻结行转换为 P13 可机械复用的精确中局目标。"""

    counters: Counter[tuple[str, str]] = Counter()
    short = {
        "concealed.gang_to_nongang": "concealed",
        "exposed.gang_to_nongang": "exposed",
        "added.gang_to_nongang": "added",
    }
    result = []
    for row in selected_rows():
        key = (row["family"], row["split"])
        counters[key] += 1
        request = row["request"]
        observation = request["observation"]
        table_id = str(observation["game_id"]).removeprefix("sitin-stage:")
        result.append({
            "target_id": "r18-p21-{0}-{1}-{2:02d}".format(
                short[row["family"]], row["split"], counters[key],
            ),
            "split": row["split"],
            "family": row["family"],
            "source": {
                "panel_seed": p20.PANEL_SEED,
                "source_id": row["source"]["source_id"],
                "source_root_id": row["source"]["source_root_id"],
                "mix": row["source"]["mix"],
                "root_index": row["source"]["root_index"],
                "focal_seat": row["source"]["focal_seat"],
                "table_no": int(table_id.rsplit("-t", 1)[1]),
                "table_id": table_id,
            },
            "window_key": request["window_key"],
            "focal_physical_seat": int(observation["seat"]),
            "request_sha256": row["request_sha256"],
            "state_projection_sha256": value_digest(state_projection(request)),
            "reference_action": row["reference_action_key"],
            "intervention_action": row["intervention_action_key"],
            "features": {
                "round_no": row["round_no"],
                "phase": row["phase"],
                "dealer_seat": row["dealer_seat"],
                "remaining_tile_count": row["remaining_tile_count"],
                "wealth_count": row["wealth_count"],
                "baotou": row["baotou"],
                "chain_count": row["chain_count"],
                "chain_piao": row["chain_piao"],
                "p5_score_margin": row["p5_score_margin"],
                "reference_trace": row["reference_trace"],
                "intervention_trace": row["intervention_trace"],
            },
        })
    expected = {
        (family, split): 16
        for family in OPEN_FAMILIES for split in ("development", "replication")
    }
    if dict(counters) != expected:
        raise ValueError("P21 家族/切分计数错误：" + repr(dict(counters)))
    roots = [row["source"]["source_root_id"] for row in result]
    if len(roots) != len(set((row["family"], root) for row, root in zip(result, roots))):
        raise ValueError("P21 同家族重复使用来源根")
    return result


def snapshot_path(target: Mapping[str, Any]) -> Path:
    return _project_file(_PROJECT_ROOT, OUT / "snapshots" / (str(target["target_id"]) + ".json"))


def rollout_path(target: Mapping[str, Any], index: int) -> Path:
    return _project_file(_PROJECT_ROOT, OUT / "rollouts" / "{0}-hidden-{1:02d}.json".format(target["target_id"], index))


def source_paths() -> list[Path]:
    return [
        Path(__file__), DATASET, EXPOSURE_RESULT, CONTRACT, PARENT,
        Path(p13.__file__), Path(p20.__file__), Path(natural.__file__),
    ]


def prepare() -> None:
    """冻结 48 个开发目标、48 个盲态复验目标与开发执行预算。"""

    if OUT.exists():
        raise SystemExit("P21 目录已存在；拒绝覆盖")
    if digest(PARENT) != digest(p13.PARENT):
        raise ValueError("P21 与复用教师的 P5 父代不一致")
    frozen = targets()
    development = [row for row in frozen if row["split"] == "development"]
    sample_keys = [
        "r18-p21-gang-pair-hidden-world-{0:02d}".format(index)
        for index in range(1, ROLLOUTS_PER_STATE + 1)
    ]
    planned_tables = len(development) * len(sample_keys) * 2
    OUT.mkdir(parents=True)
    (_project_file(_PROJECT_ROOT, OUT / "snapshots")).mkdir()
    (_project_file(_PROJECT_ROOT, OUT / "rollouts")).mkdir()
    authorization = batch.unified_document(
        batch_label=OUT.name,
        authorization_id="r18-p21-gang-pair-development-teacher-01",
        accounts={"prefix_generation": len(development), "tables_full": planned_tables},
        issued_by="lead", issued_at_utc=search.utc_now(), legacy_alias=False,
    )
    authorization.update({
        "issuance_basis": "P20 三个非支配杠层自然暴露过门；只打开结果盲开发切分",
        "scope": "3家族×16开发状态×32共同隐藏世界×P5原杠/最高分非杠；48复验状态不运行",
        "max_model_calls": 0,
        "confirmation_roots": 0,
    })
    write_json(_project_file(_PROJECT_ROOT, OUT / "authorization.json"), authorization)
    write_json(_project_file(_PROJECT_ROOT, OUT / "targets.json"), {
        "schema": "r18-p21-gang-pair-targets/1", "targets": frozen,
    })
    write_json(_project_file(_PROJECT_ROOT, OUT / "manifest.json"), {
        "schema": "r18-p21-gang-pair-development-manifest/1",
        "created_at_utc": search.utc_now(),
        "runtime": guard.capture(source_paths=source_paths() + [
            _project_file(_PROJECT_ROOT, OUT / "authorization.json"), _project_file(_PROJECT_ROOT, OUT / "targets.json"),
        ]),
        "dataset_sha256": digest(DATASET),
        "exposure_result_sha256": digest(EXPOSURE_RESULT),
        "targets_sha256": digest(_project_file(_PROJECT_ROOT, OUT / "targets.json")),
        "parent_sha256": digest(PARENT),
        "contract_sha256": digest(CONTRACT),
        "open_families": list(OPEN_FAMILIES),
        "states_per_family": STATES_PER_FAMILY,
        "development_per_family": DEVELOPMENT_PER_FAMILY,
        "development_states": len(development),
        "replication_states_kept_blind": len(frozen) - len(development),
        "rollouts_per_state": ROLLOUTS_PER_STATE,
        "sample_keys": sample_keys,
        "planned_tables": planned_tables,
        "workers": WORKERS,
        "primary_label": "intervention_non_gang_minus_reference_gang_current_round_settlement",
        "selection_unit": "自然牌山根，家族内不重复；共同隐藏世界不增加独立样本数",
        "replication_labels_opened": False,
        "release_eligible": False,
    })
    print(json.dumps({
        "status": "PREPARED", "development_states": len(development),
        "replication_states_kept_blind": len(frozen) - len(development),
        "planned_tables": planned_tables,
    }, ensure_ascii=False))


def verify() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """核对 P20 输入、目标、父代、合同和执行实现均未漂移。"""

    manifest = json.loads((_project_file(_PROJECT_ROOT, OUT / "manifest.json")).read_text(encoding="utf-8"))
    checks = {
        "P20数据": (manifest["dataset_sha256"], digest(DATASET)),
        "P20结果": (manifest["exposure_result_sha256"], digest(EXPOSURE_RESULT)),
        "P21目标": (manifest["targets_sha256"], digest(_project_file(_PROJECT_ROOT, OUT / "targets.json"))),
        "P5父代": (manifest["parent_sha256"], digest(PARENT)),
        "合同": (manifest["contract_sha256"], digest(CONTRACT)),
    }
    for label, (expected, actual) in checks.items():
        if expected != actual:
            raise ValueError(label + "漂移")
    guard.verify(manifest["runtime"])
    frozen = json.loads((_project_file(_PROJECT_ROOT, OUT / "targets.json")).read_text(encoding="utf-8"))["targets"]
    if frozen != targets():
        raise ValueError("P21 目标不能从 P20 结果盲重建")
    return manifest, frozen


def capture() -> None:
    """只捕获开发状态的 P5 合法前缀；复验状态保持未运行。"""

    manifest, frozen = verify()
    development = [row for row in frozen if row["split"] == "development"]
    authorization = json.loads((_project_file(_PROJECT_ROOT, OUT / "authorization.json")).read_text(encoding="utf-8"))
    natural.require_authorization(authorization)
    ledger = search.ActionValueLedger.load(
        _project_file(_PROJECT_ROOT, OUT / "ledger.json"),
        authorized_budgets=search.av_ledger_budgets_from_authorization(authorization),
    )
    pending = [row for row in development if not snapshot_path(row).exists()]
    reservation = ledger.reserve(
        step_id="r18:p21-gang-pair:capture", account="prefix_generation",
        amount=len(pending), note="48个开发状态的P5精确合法前缀捕获",
    )
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    completed = 0
    failures = []
    try:
        for target in pending:
            try:
                snapshot = p13.capture_one(target, contract)
                snapshot["capture"]["consumer"] = "R18 P21 gang-pair development teacher"
                write_json(snapshot_path(target), snapshot)
                completed += 1
                print(json.dumps({
                    "captured": sum(snapshot_path(row).exists() for row in development),
                    "planned": len(development),
                }, ensure_ascii=False), flush=True)
            except Exception as exc:  # noqa: BLE001
                failures.append({
                    "target_id": target["target_id"],
                    "error": type(exc).__name__ + ": " + str(exc),
                })
    finally:
        ledger.settle(reservation, actual=completed, note="按成功捕获的合法前缀计")
    write_json(_project_file(_PROJECT_ROOT, OUT / "capture-summary.json"), {
        "schema": "r18-p21-gang-pair-capture-summary/1",
        "captured": sum(snapshot_path(row).exists() for row in development),
        "planned": manifest["development_states"], "failures": failures,
        "replication_snapshots": sum(
            snapshot_path(row).exists() for row in frozen if row["split"] == "replication"
        ),
        "spent": ledger.account_summary(),
    })
    if failures or not all(snapshot_path(row).exists() for row in development):
        raise RuntimeError("P21 开发状态捕获不完整")


def execute_rollout(target: Mapping[str, Any], index: int, sample_key: str) -> dict[str, Any]:
    """复用已验证的 P13 双臂机械执行，并把证据身份改为 P21。"""

    p13.OUT = OUT
    row = p13.execute_rollout(target, index, sample_key)
    row["schema"] = "r18-p21-gang-pair-development-rollout/1"
    row["family"] = target["family"]
    row["split"] = target["split"]
    return row


def run() -> None:
    """并行执行 48×32 个开发集共同隐藏世界配对。"""

    manifest, frozen = verify()
    development = [row for row in frozen if row["split"] == "development"]
    summary = json.loads((_project_file(_PROJECT_ROOT, OUT / "capture-summary.json")).read_text(encoding="utf-8"))
    if summary["failures"] or summary["captured"] != manifest["development_states"]:
        raise ValueError("P21 开发状态尚未全部捕获")
    if summary["replication_snapshots"] != 0:
        raise ValueError("P21 复验状态被提前捕获")
    authorization = json.loads((_project_file(_PROJECT_ROOT, OUT / "authorization.json")).read_text(encoding="utf-8"))
    natural.require_authorization(authorization)
    ledger = search.ActionValueLedger.load(
        _project_file(_PROJECT_ROOT, OUT / "ledger.json"),
        authorized_budgets=search.av_ledger_budgets_from_authorization(authorization),
    )
    pending = []
    completed_tables = 0
    for target in development:
        for index, key in enumerate(manifest["sample_keys"], 1):
            path = rollout_path(target, index)
            if path.exists():
                row = json.loads(path.read_text(encoding="utf-8"))
                if not row.get("mechanical_ok"):
                    raise ValueError("既有 P21 配对机械条件失败：" + str(path))
                completed_tables += 2
            else:
                pending.append((target, index, key))
    reservation = ledger.reserve(
        step_id="r18:p21-gang-pair:run", account="tables_full",
        amount=manifest["planned_tables"] - completed_tables,
        note="48开发状态×32共同隐藏世界×P5原杠/最高分非杠",
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
                        raise RuntimeError("P21 共同隐藏世界配对机械条件失败")
                    write_json(rollout_path(target, index), row)
                    executed += 2
                    completed_tables += 2
                    if completed_tables % 128 == 0:
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
        "schema": "r18-p21-gang-pair-run-summary/1",
        "rollout_files": len(files), "actual_tables": len(files) * 2,
        "failures": failures, "spent": ledger.account_summary(),
    })
    if failures or len(files) * 2 != manifest["planned_tables"]:
        raise RuntimeError("P21 杠配对开发教师执行不完整")


def bootstrap_interval(values: list[float], salt: int) -> tuple[float, float]:
    """对独立基础状态均值做确定性百分位 bootstrap 95% 区间。"""

    rng = random.Random(2026092200 + salt)
    means = []
    for _ in range(20_000):
        means.append(statistics.fmean(rng.choice(values) for _ in values))
    means.sort()
    return means[int(0.025 * len(means))], means[int(0.975 * len(means)) - 1]


def analyze() -> None:
    """按基础状态等权汇总开发标签；正值表示非杠优于 P5 原杠。"""

    manifest, frozen = verify()
    development = [row for row in frozen if row["split"] == "development"]
    summary = json.loads((_project_file(_PROJECT_ROOT, OUT / "run-summary.json")).read_text(encoding="utf-8"))
    if summary["failures"] or summary["actual_tables"] != manifest["planned_tables"]:
        raise ValueError("P21 开发教师执行不完整")
    states = []
    all_mechanical = True
    for target in development:
        rows = [
            json.loads(rollout_path(target, index).read_text(encoding="utf-8"))
            for index in range(1, ROLLOUTS_PER_STATE + 1)
        ]
        mechanical = all(row["mechanical_ok"] for row in rows)
        all_mechanical = all_mechanical and mechanical
        direct = [row["focal_current_round_settlement_delta"] for row in rows]
        full = [row["focal_remaining_table_score"]["delta"] for row in rows]
        transitions = Counter(
            row["reference"]["terminal"] + "->" + row["intervention"]["terminal"]
            for row in rows
        )
        states.append({
            "target_id": target["target_id"], "family": target["family"],
            "source": target["source"], "features": target["features"],
            "reference_action": target["reference_action"],
            "intervention_action": target["intervention_action"],
            "hidden_world_rollouts": len(rows), "mechanical_ok": mechanical,
            "mean_current_round_settlement_delta": statistics.fmean(direct),
            "mean_remaining_table_score_delta": statistics.fmean(full),
            "positive_hidden_worlds": sum(value > 0 for value in direct),
            "zero_hidden_worlds": sum(value == 0 for value in direct),
            "negative_hidden_worlds": sum(value < 0 for value in direct),
            "terminal_transitions": dict(sorted(transitions.items())),
            "current_round_settlement_values": direct,
        })
    by_family = {}
    for salt, family in enumerate(OPEN_FAMILIES, 1):
        items = [row for row in states if row["family"] == family]
        values = [row["mean_current_round_settlement_delta"] for row in items]
        low, high = bootstrap_interval(values, salt)
        mean = statistics.fmean(values)
        positive = sum(value > 0 for value in values)
        by_family[family] = {
            "independent_states": len(items),
            "mean_non_gang_minus_gang_current_round_settlement": mean,
            "bootstrap_95_interval": [low, high],
            "positive_state_means": positive,
            "zero_state_means": sum(value == 0 for value in values),
            "negative_state_means": sum(value < 0 for value in values),
            "open_for_rule_authoring": bool(
                all_mechanical and len(items) == DEVELOPMENT_PER_FAMILY
                and mean > 0 and low > 0 and positive >= 10
            ),
        }
    result = {
        "schema": "r18-p21-gang-pair-development-result/1",
        "status": "COMPLETE_P21_GANG_PAIR_DEVELOPMENT_TEACHER",
        "mechanical_ok": all_mechanical,
        "development_states": len(states),
        "rollouts": len(states) * ROLLOUTS_PER_STATE,
        "tables": len(states) * ROLLOUTS_PER_STATE * 2,
        "states": states,
        "by_family": by_family,
        "families_open_for_rule_authoring": [
            family for family in OPEN_FAMILIES
            if by_family[family]["open_for_rule_authoring"]
        ],
        "families_closed_by_development_teacher": [
            family for family in OPEN_FAMILIES
            if not by_family[family]["open_for_rule_authoring"]
        ],
        "replication_states": manifest["replication_states_kept_blind"],
        "replication_labels_opened": False,
        "interpretation": "正值表示最高分非杠优于P5原杠；统计单位是自然牌山根，32个隐藏分配只降低单状态标签方差",
        "next": "只对通过开发门的家族拟合公开可见且杭麻规则可解释的窄规则；候选源码和判据冻结后才可打开48个复验状态",
        "selection_eligible": True,
        "release_eligible": False,
    }
    write_json(_project_file(_PROJECT_ROOT, OUT / "result.json"), result)
    print(json.dumps({
        "status": result["status"], "mechanical_ok": all_mechanical,
        "development_states": len(states), "by_family": by_family,
        "families_open_for_rule_authoring": result["families_open_for_rule_authoring"],
        "replication_labels_opened": False,
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
