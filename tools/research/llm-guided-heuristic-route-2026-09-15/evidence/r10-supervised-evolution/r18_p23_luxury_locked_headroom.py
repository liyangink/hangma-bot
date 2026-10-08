"""R18 P23：已锁自然四张的暗杠/保留取舍首尺。

本批复用 P16 已冻结且结果盲采集的 P5 自然请求，只选择本人门清、暗牌中
存在一组非财神自然四张、P5 首选把该组暗杠、同时存在保留该四张的合法弃牌
的窗口。每个自然牌山根最多保留一个状态，随后在 32 个公开状态一致的隐藏
世界中比较“P5 原暗杠”与“P5 评分最高的保留弃牌”，两臂之后都恢复 P5。

本批只判断该机制是否值得在全新来源确认，不生成候选，不打开任何旧隐藏集，
也不调用作者模型。共同隐藏世界只降低单状态标签方差，不增加独立样本数。
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
import r18_p16_catch_play_natural_exposure as p16  # noqa: E402
import sitin_natural_panel as natural  # noqa: E402
import sitin_search as search  # noqa: E402
import strong_seed_batch as batch  # noqa: E402
from hangma_bot.application.audit_codec import decision_request_from_json  # noqa: E402
from hangma_bot.policy.action_value_policy import build_scoring_view  # noqa: E402
from hangma_bot.policy.action_value_seeds import ActionValueScorer  # noqa: E402


OUT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p23-luxury-locked-headroom-01-20260922')
P16_SOURCES = p16.OUT / "sources"
P16_MANIFEST = p16.OUT / "manifest.json"
P16_RESULT = p16.OUT / "result.json"
CONTRACT = p16.CONTRACT
PARENT = p16.PARENT
SELECTION_SALT = "r18-p23-luxury-locked-headroom-state/v1"
EXPECTED_SOURCE_FILES = 256
EXPECTED_INDEPENDENT_STATES = 12
ROLLOUTS_PER_STATE = 32
WORKERS = 8


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


def combined_hand(observation: Mapping[str, Any]) -> list[str]:
    """按正式观察快照语义取得包含当前摸牌的本人暗牌。"""

    hand = list(observation["my_hand"])
    drawn = observation.get("drawn_tile")
    seat = int(observation["seat"])
    if drawn is not None and len(hand) != int(observation["hand_counts"][seat]):
        hand.append(str(drawn))
    return hand


def exposure_rows() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """从 P16 原始自然请求中重筛门清锁定豪华组，不读取任何结算结果。"""

    paths = sorted(P16_SOURCES.glob("*.json"))
    if len(paths) != EXPECTED_SOURCE_FILES:
        raise ValueError("P16 原始来源必须恰有 256 个文件")
    parent_source = PARENT.read_text(encoding="utf-8")
    scorer = ActionValueScorer("r18-p23-p5-rescore", parent_source)
    counts: Counter[str] = Counter()
    rows_by_root: dict[str, list[dict[str, Any]]] = defaultdict(list)
    seen_requests: set[str] = set()
    relevant_file_hashes: dict[str, str] = {}

    for path in paths:
        document = json.loads(path.read_text(encoding="utf-8"))
        for row in document["audit"]["eligible_rows"]:
            counts["p16_catch_open_rows"] += 1
            request_json = row["request"]
            observation = request_json["observation"]
            if observation["phase"] != "draw":
                continue
            seat = int(observation["seat"])
            hand = combined_hand(observation)
            hand_counts = Counter(hand)
            wealth_code = str(observation["rule_state"]["wealth_god"])
            locked_codes = sorted(
                code for code, count in hand_counts.items()
                if count == 4 and code != wealth_code
            )
            if not locked_codes:
                continue
            counts["natural_four_rows"] += 1
            if observation["melds"][seat]:
                counts["excluded_existing_meld"] += 1
                continue
            counts["closed_luxury_rows"] += 1
            if len(locked_codes) != 1:
                counts["excluded_multiple_locked_groups"] += 1
                continue
            request_sha = str(row["request_sha256"])
            if request_sha in seen_requests:
                counts["duplicate_request_rows"] += 1
                continue
            seen_requests.add(request_sha)

            request = decision_request_from_json(request_json)
            scored = scorer.score(build_scoring_view(request))
            if scored.status != "SCORED":
                raise ValueError("P5 重评分失败：" + str(scored.reason))
            entries = sorted(scored.entries, key=lambda item: (-item.score, item.action_key))
            if not entries:
                raise ValueError("P5 重评分无动作")
            locked = locked_codes[0]
            reference = entries[0]
            expected_gang = "gang:concealed:" + locked
            preserve = [
                entry for entry in entries
                if entry.action_key.startswith("discard:")
                and entry.action_key.split(":", 1)[1] != locked
            ]
            category = (
                "locked_concealed_gang" if reference.action_key == expected_gang
                else "other_parent_action"
            )
            counts[category] += 1
            if category != "locked_concealed_gang" or not preserve:
                continue
            intervention = preserve[0]
            source = dict(row["source"])
            table_id = str(observation["game_id"]).removeprefix("sitin-stage:")
            relative_path = str(path.relative_to(ROOT))
            relevant_file_hashes[relative_path] = digest(path)
            rows_by_root[str(source["source_root_id"])].append({
                "schema": "r18-p23-luxury-locked-exposure-row/1",
                "source": {
                    "panel_seed": p16.PANEL_SEED,
                    "source_id": source["source_id"],
                    "source_root_id": source["source_root_id"],
                    "mix": source["mix"],
                    "root_index": source["root_index"],
                    "focal_seat": source["focal_seat"],
                    "table_no": int(table_id.rsplit("-t", 1)[1]),
                    "table_id": table_id,
                    "p16_source_path": relative_path,
                    "p16_source_sha256": relevant_file_hashes[relative_path],
                },
                "window_key": request_json["window_key"],
                "focal_physical_seat": seat,
                "request_sha256": request_sha,
                "state_projection_sha256": value_digest(state_projection(request_json)),
                "reference_action": reference.action_key,
                "intervention_action": intervention.action_key,
                "features": {
                    "round_no": int(observation["round_no"]),
                    "phase": str(observation["phase"]),
                    "dealer_seat": int(observation["dealer_seat"]),
                    "remaining_tile_count": observation["remaining_tile_count"],
                    "wealth_count": hand_counts[wealth_code],
                    "locked_natural_code": locked,
                    "locked_groups": len(locked_codes),
                    "chain_count": int(observation["rule_state"]["chain_count"]),
                    "chain_piao": observation.get("chain_piao"),
                    "baotou": bool(observation["rule_state"]["baotou"]),
                    "reference_score": reference.score,
                    "intervention_score": intervention.score,
                    "p5_score_margin": reference.score - intervention.score,
                    "reference_trace": reference.trace,
                    "intervention_trace": intervention.trace,
                },
            })

    selected = []
    for source_root_id, options in sorted(rows_by_root.items()):
        choice = min(options, key=lambda item: hashlib.sha256(
            (SELECTION_SALT + "|" + item["request_sha256"]).encode("utf-8")
        ).hexdigest())
        selected.append(choice)
    selected.sort(key=lambda item: (
        item["source"]["source_root_id"], item["request_sha256"],
    ))
    audit = {
        "schema": "r18-p23-luxury-locked-exposure-audit/1",
        "outcome_blind": True,
        "source_files": len(paths),
        "counts": dict(sorted(counts.items())),
        "eligible_rows_before_root_dedup": sum(len(items) for items in rows_by_root.values()),
        "independent_source_roots": len(rows_by_root),
        "selected_independent_states": len(selected),
        "selection_salt": SELECTION_SALT,
        "selection_rule": "每个自然牌山根按 salted request_sha256 取一条；不读取结算与桌分",
        "relevant_source_file_hashes": dict(sorted(relevant_file_hashes.items())),
    }
    return selected, audit


def targets_from_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """为精确前缀捕获分配稳定目标编号。"""

    result = []
    for index, row in enumerate(rows, 1):
        item = dict(row)
        item["target_id"] = "r18-p23-luxury-{0:02d}".format(index)
        result.append(item)
    return result


def snapshot_path(target: Mapping[str, Any]) -> Path:
    return _project_file(_PROJECT_ROOT, OUT / "snapshots" / (str(target["target_id"]) + ".json"))


def rollout_path(target: Mapping[str, Any], index: int) -> Path:
    return _project_file(_PROJECT_ROOT, OUT / "rollouts" / "{0}-hidden-{1:02d}.json".format(
        target["target_id"], index,
    ))


def prepare() -> None:
    """冻结自然来源、12 个独立状态、双臂动作和首尺门。"""

    if OUT.exists():
        raise SystemExit("P23 目录已存在；拒绝覆盖")
    rows, audit = exposure_rows()
    if len(rows) != EXPECTED_INDEPENDENT_STATES:
        raise ValueError("P23 独立自然状态数漂移：" + str(len(rows)))
    targets = targets_from_rows(rows)
    planned_tables = len(targets) * ROLLOUTS_PER_STATE * 2
    OUT.mkdir(parents=True)
    (_project_file(_PROJECT_ROOT, OUT / "snapshots")).mkdir()
    (_project_file(_PROJECT_ROOT, OUT / "rollouts")).mkdir()
    authorization = batch.unified_document(
        batch_label=OUT.name,
        authorization_id="r18-p23-luxury-locked-headroom-01",
        accounts={"prefix_generation": len(targets), "tables_full": planned_tables},
        issued_by="lead", issued_at_utc=search.utc_now(), legacy_alias=False,
    )
    authorization.update({
        "issuance_basis": "P22关闭赛事处境轴；P16结果盲自然请求暴露门清锁定豪华组",
        "scope": "12独立牌山根×32共同隐藏世界×P5原暗杠/最高分保留弃牌",
        "max_model_calls": 0,
        "confirmation_roots": 0,
    })
    write_json(_project_file(_PROJECT_ROOT, OUT / "authorization.json"), authorization)
    write_json(_project_file(_PROJECT_ROOT, OUT / "source-audit.json"), audit)
    write_json(_project_file(_PROJECT_ROOT, OUT / "targets.json"), {
        "schema": "r18-p23-luxury-locked-targets/1", "targets": targets,
    })
    sample_keys = [
        "r18-p23-luxury-hidden-world-{0:02d}".format(index)
        for index in range(1, ROLLOUTS_PER_STATE + 1)
    ]
    tracked = [
        Path(__file__), P16_MANIFEST, P16_RESULT, Path(p16.__file__),
        Path(p13.__file__), Path(natural.__file__), CONTRACT, PARENT,
        _project_file(_PROJECT_ROOT, OUT / "authorization.json"), _project_file(_PROJECT_ROOT, OUT / "source-audit.json"), _project_file(_PROJECT_ROOT, OUT / "targets.json"),
    ]
    write_json(_project_file(_PROJECT_ROOT, OUT / "manifest.json"), {
        "schema": "r18-p23-luxury-locked-headroom-manifest/1",
        "created_at_utc": search.utc_now(),
        "runtime": guard.capture(source_paths=tracked),
        "p16_manifest_sha256": digest(P16_MANIFEST),
        "p16_result_sha256": digest(P16_RESULT),
        "contract_sha256": digest(CONTRACT),
        "parent_sha256": digest(PARENT),
        "targets_sha256": digest(_project_file(_PROJECT_ROOT, OUT / "targets.json")),
        "source_audit_sha256": digest(_project_file(_PROJECT_ROOT, OUT / "source-audit.json")),
        "independent_states": len(targets),
        "rollouts_per_state": ROLLOUTS_PER_STATE,
        "sample_keys": sample_keys,
        "planned_tables": planned_tables,
        "workers": WORKERS,
        "primary_label": "preserve_discard_minus_concealed_gang_current_round_settlement",
        "headroom_gate": {
            "mean_strictly_positive": True,
            "bootstrap_95_lower_strictly_positive": True,
            "positive_state_means_at_least": 8,
            "all_mechanical": True,
        },
        "interpretation": "通过只授权在全新自然来源确认；不授权候选、模型调用或发布",
        "model_calls": 0,
        "selection_eligible": False,
        "release_eligible": False,
    })
    print(json.dumps({
        "status": "PREPARED", "independent_states": len(targets),
        "planned_tables": planned_tables,
    }, ensure_ascii=False))


def verify() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """核对冻结来源、目标、父代、合同与执行实现未漂移。"""

    manifest = json.loads((_project_file(_PROJECT_ROOT, OUT / "manifest.json")).read_text(encoding="utf-8"))
    checks = {
        "P16清单": (manifest["p16_manifest_sha256"], digest(P16_MANIFEST)),
        "P16结果": (manifest["p16_result_sha256"], digest(P16_RESULT)),
        "合同": (manifest["contract_sha256"], digest(CONTRACT)),
        "P5父代": (manifest["parent_sha256"], digest(PARENT)),
        "P23目标": (manifest["targets_sha256"], digest(_project_file(_PROJECT_ROOT, OUT / "targets.json"))),
        "来源审计": (manifest["source_audit_sha256"], digest(_project_file(_PROJECT_ROOT, OUT / "source-audit.json"))),
    }
    for label, (expected, actual) in checks.items():
        if expected != actual:
            raise ValueError(label + "漂移")
    guard.verify(manifest["runtime"])
    targets = json.loads((_project_file(_PROJECT_ROOT, OUT / "targets.json")).read_text(encoding="utf-8"))["targets"]
    if len(targets) != manifest["independent_states"]:
        raise ValueError("P23 目标数漂移")
    return manifest, targets


def capture() -> None:
    """按 P16 原自然桌计划重建 12 个精确合法前缀。"""

    manifest, targets = verify()
    authorization = json.loads((_project_file(_PROJECT_ROOT, OUT / "authorization.json")).read_text(encoding="utf-8"))
    natural.require_authorization(authorization)
    ledger = search.ActionValueLedger.load(
        _project_file(_PROJECT_ROOT, OUT / "ledger.json"),
        authorized_budgets=search.av_ledger_budgets_from_authorization(authorization),
    )
    pending = [target for target in targets if not snapshot_path(target).exists()]
    reservation = ledger.reserve(
        step_id="r18:p23-luxury-locked:capture", account="prefix_generation",
        amount=len(pending), note="12个锁定豪华组自然状态的P5精确前缀捕获",
    )
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    completed = 0
    failures = []
    try:
        for target in pending:
            try:
                snapshot = p13.capture_one(target, contract)
                snapshot["capture"]["consumer"] = "R18 P23 luxury-locked headroom"
                write_json(snapshot_path(target), snapshot)
                completed += 1
                print(json.dumps({
                    "captured": sum(snapshot_path(row).exists() for row in targets),
                    "planned": len(targets),
                }, ensure_ascii=False), flush=True)
            except Exception as exc:  # noqa: BLE001
                failures.append({
                    "target_id": target["target_id"],
                    "error": type(exc).__name__ + ": " + str(exc),
                })
    finally:
        ledger.settle(reservation, actual=completed, note="按成功捕获的合法前缀计")
    write_json(_project_file(_PROJECT_ROOT, OUT / "capture-summary.json"), {
        "schema": "r18-p23-luxury-locked-capture-summary/1",
        "captured": sum(snapshot_path(row).exists() for row in targets),
        "planned": manifest["independent_states"], "failures": failures,
        "spent": ledger.account_summary(),
    })
    if failures or not all(snapshot_path(row).exists() for row in targets):
        raise RuntimeError("P23 自然状态捕获不完整")


def execute_rollout(target: Mapping[str, Any], index: int, sample_key: str) -> dict[str, Any]:
    """复用已验证的双臂执行器，并把证据身份改为 P23。"""

    p13.OUT = OUT
    row = p13.execute_rollout(target, index, sample_key)
    row["schema"] = "r18-p23-luxury-locked-headroom-rollout/1"
    return row


def run() -> None:
    """并行执行 12×32 个共同隐藏世界配对。"""

    manifest, targets = verify()
    summary = json.loads((_project_file(_PROJECT_ROOT, OUT / "capture-summary.json")).read_text(encoding="utf-8"))
    if summary["failures"] or summary["captured"] != manifest["independent_states"]:
        raise ValueError("P23 状态尚未全部捕获")
    authorization = json.loads((_project_file(_PROJECT_ROOT, OUT / "authorization.json")).read_text(encoding="utf-8"))
    natural.require_authorization(authorization)
    ledger = search.ActionValueLedger.load(
        _project_file(_PROJECT_ROOT, OUT / "ledger.json"),
        authorized_budgets=search.av_ledger_budgets_from_authorization(authorization),
    )
    pending = []
    completed_tables = 0
    for target in targets:
        for index, key in enumerate(manifest["sample_keys"], 1):
            path = rollout_path(target, index)
            if path.exists():
                row = json.loads(path.read_text(encoding="utf-8"))
                if not row.get("mechanical_ok"):
                    raise ValueError("既有 P23 配对机械条件失败：" + str(path))
                completed_tables += 2
            else:
                pending.append((target, index, key))
    reservation = ledger.reserve(
        step_id="r18:p23-luxury-locked:run", account="tables_full",
        amount=manifest["planned_tables"] - completed_tables,
        note="12状态×32共同隐藏世界×原暗杠/保留豪华组弃牌",
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
                        raise RuntimeError("P23 共同隐藏世界配对机械条件失败")
                    write_json(rollout_path(target, index), row)
                    executed += 2
                    completed_tables += 2
                    if completed_tables % 128 == 0 or completed_tables == manifest["planned_tables"]:
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
        "schema": "r18-p23-luxury-locked-run-summary/1",
        "rollout_files": len(files), "actual_tables": len(files) * 2,
        "failures": failures, "spent": ledger.account_summary(),
    })
    if failures or len(files) * 2 != manifest["planned_tables"]:
        raise RuntimeError("P23 豪华组首尺执行不完整")


def bootstrap_interval(values: list[float]) -> tuple[float, float]:
    """对独立自然牌山根均值做确定性百分位 bootstrap 95% 区间。"""

    rng = random.Random(2026092223)
    means = []
    for _ in range(20_000):
        means.append(statistics.fmean(rng.choice(values) for _ in values))
    means.sort()
    return means[int(0.025 * len(means))], means[int(0.975 * len(means)) - 1]


def analyze() -> None:
    """按自然牌山根等权汇总；正值表示保留豪华组优于 P5 原暗杠。"""

    manifest, targets = verify()
    summary = json.loads((_project_file(_PROJECT_ROOT, OUT / "run-summary.json")).read_text(encoding="utf-8"))
    if summary["failures"] or summary["actual_tables"] != manifest["planned_tables"]:
        raise ValueError("P23 执行不完整")
    states = []
    for target in targets:
        rows = [
            json.loads(rollout_path(target, index).read_text(encoding="utf-8"))
            for index in range(1, ROLLOUTS_PER_STATE + 1)
        ]
        direct = [row["focal_current_round_settlement_delta"] for row in rows]
        full = [row["focal_remaining_table_score"]["delta"] for row in rows]
        states.append({
            "target_id": target["target_id"], "source": target["source"],
            "features": target["features"],
            "reference_action": target["reference_action"],
            "intervention_action": target["intervention_action"],
            "hidden_world_rollouts": len(rows),
            "mechanical_ok": all(row["mechanical_ok"] for row in rows),
            "mean_current_round_settlement_delta": statistics.fmean(direct),
            "mean_remaining_table_score_delta": statistics.fmean(full),
            "positive_hidden_worlds": sum(value > 0 for value in direct),
            "zero_hidden_worlds": sum(value == 0 for value in direct),
            "negative_hidden_worlds": sum(value < 0 for value in direct),
            "terminal_transitions": dict(sorted(Counter(
                row["reference"]["terminal"] + "->" + row["intervention"]["terminal"]
                for row in rows
            ).items())),
            "current_round_settlement_values": direct,
        })
    values = [row["mean_current_round_settlement_delta"] for row in states]
    low, high = bootstrap_interval(values)
    mean = statistics.fmean(values)
    positive = sum(value > 0 for value in values)
    mechanical = all(row["mechanical_ok"] for row in states)
    passes = bool(mechanical and mean > 0 and low > 0 and positive >= 8)
    result = {
        "schema": "r18-p23-luxury-locked-headroom-result/1",
        "status": (
            "OPEN_NEW_SOURCE_CONFIRMATION" if passes
            else "CLOSE_LUXURY_LOCKED_GANG_AXIS"
        ),
        "mechanical_ok": mechanical,
        "independent_states": len(states),
        "rollouts": len(states) * ROLLOUTS_PER_STATE,
        "tables": len(states) * ROLLOUTS_PER_STATE * 2,
        "mean_preserve_minus_gang_current_round_settlement": mean,
        "bootstrap_95_interval": [low, high],
        "positive_state_means": positive,
        "zero_state_means": sum(value == 0 for value in values),
        "negative_state_means": sum(value < 0 for value in values),
        "passes_headroom_gate": passes,
        "states": states,
        "model_calls": 0,
        "selection_eligible": False,
        "release_eligible": False,
        "next": (
            "用全新自然牌山取得至少24个独立根，预先拆分开发/复验并确认后再决定作者调用"
            if passes else
            "关闭锁定豪华组的无条件保留轴，转向另一杭麻机会家族"
        ),
    }
    write_json(_project_file(_PROJECT_ROOT, OUT / "result.json"), result)
    print(json.dumps({
        key: result[key] for key in (
            "status", "mechanical_ok", "independent_states", "tables",
            "mean_preserve_minus_gang_current_round_settlement",
            "bootstrap_95_interval", "positive_state_means",
            "zero_state_means", "negative_state_means",
            "passes_headroom_gate", "next",
        )
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
