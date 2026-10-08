#!/usr/bin/env python3
"""G10 分路线弃牌：冻结目标后，复用 P84 精确前缀与同墙完整桌双臂教师。"""

from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/freematch-deep-dive-20260925'

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
import hashlib
import json
from pathlib import Path
import statistics
import sys


HERE = Path(__file__).resolve().parent
ROOT = _PROJECT_ROOT
sys.path.insert(0, str(HERE))
import g10_route_option_natural_exposure as exposure  # noqa: E402
from hangma_bot.application.audit_codec import decision_request_to_json  # noqa: E402
from hangma_bot.policy.action_value_policy import build_scoring_view  # noqa: E402
from hangma_bot.policy.action_value_seeds import ActionValueScorer  # noqa: E402

R10 = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution')
sys.path.insert(0, str(R10))
import r18_p84_high_wealth_near_seven_current_table_teacher as p84  # noqa: E402


OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g10-route-option-paired-teacher-20260927')
EXPOSURE_RESULT = exposure.OUT / "result.json"
EXPOSURE_MANIFEST = exposure.OUT / "manifest.json"
SAMPLES = tuple(f"g10-route-future-{index:02d}" for index in range(1, 9))
p84.OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g10-route-option-paired-teacher-20260927')  # 借用已经审计的精确前缀与双臂实现；不修改 P84 原始证据。


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                    encoding="utf-8")


def _selected_rows() -> tuple[dict, list[dict]]:
    """只纳入事前每池至少十二个独立根的路线，不根据桌分补选。"""

    exposure._verify()
    document = _read(EXPOSURE_RESULT)
    if (document.get("outcome_labels_opened") is not False
            or document.get("completed_tables") != 384
            or document.get("parent_source_sha256") != exposure.g1.p83.R18_INTEGRATED_POSITIVE_V2_SHA256):
        raise ValueError("G10 自然暴露完整性、父代或结果盲状态不符")
    opened = {kind for kind, passed in document["teacher_entry_open"].items() if passed is True}
    if not opened:
        raise ValueError("G10 无路线通过 H/M 独立根暴露门")
    rows = [row for row in document["selected"] if row["route_kind"] in opened]
    for kind in opened:
        for mix in exposure.MIXES:
            roots = {row["source"]["source_root_id"] for row in rows
                     if row["route_kind"] == kind and row["source"]["mix"] == mix}
            if len(roots) != document["independent_roots_by_route"][mix][kind] or len(roots) < 12:
                raise ValueError("G10 路线独立根计数漂移")
    rows.sort(key=lambda row: (row["route_kind"], row["source"]["mix"],
                               row["source"]["root_index"]))
    return document, rows


def _rebuild_target(row: dict, index: int) -> dict:
    """重建自然来源请求，核对公开事实、父代首选和冻结 B，不读终局。"""

    source = row["source"]
    contract = _read(exposure.g1.CONTRACT)
    parent = exposure.g1.p83.parent_source()
    plans = exposure.g1.p83.natural.build_seat_stage_plans(
        contract=contract, opponent=source["mix"], root_index=source["root_index"],
        focal_seat=source["focal_seat"], panel_seed=exposure.PANEL_SEED)
    requests = []
    label = "g10-teacher-rebuild-" + source["source_id"]
    stage = exposure.g1.p83.natural.run_arm_stage(
        arm="candidate", plans=plans,
        candidate_scorer=ActionValueScorer(label, parent),
        opponent_policies=contract["panel"]["opponent_scenarios"][source["mix"]]["opponent_policies"],
        versions_block=exposure.g1.p83.natural.stage.contract_versions_block(contract),
        step_limit=int(contract["stop"]["step_limit"]),
        value_limits=exposure.g1.p83.LIMITS, decision_observer=requests.append)
    if stage.get("status") != "complete" or len(stage.get("tables") or []) != 2:
        raise ValueError("G10 来源请求重建未跑满")
    for plan, table in zip(plans, stage["tables"]):
        seat = plan.seats().index(exposure.g1.p83.natural.FOCAL_PARTICIPANT)
        identities = (table.get("policy_execution") or {}).get("policy_ids_by_seat") or []
        if len(identities) != 4 or identities[seat] != "action_value_v1:" + label:
            raise ValueError("G10 来源请求重建焦点策略身份漂移")
    matches = [request for request in requests
               if (request.observation.game_id, request.observation.round_no, request.trigger_seq)
               == (row["game_id"], row["round_no"], row["trigger_seq"])]
    if len(matches) != 1:
        raise ValueError("G10 冻结动作窗重建不唯一")
    request = matches[0]
    raw = decision_request_to_json(request)
    if exposure._digest(raw) != row["request_sha256"]:
        raise ValueError("G10 玩家可见请求摘要漂移")
    check, reason = exposure._eligible(request, ActionValueScorer("g10-teacher-audit", parent))
    if reason != "eligible" or check is None:
        raise ValueError("G10 冻结路线机会重建失败：" + reason)
    for key in ("parent_action", "alternate_action", "parent_route_shanten",
                "alternate_route_shanten", "parent_support", "alternate_support",
                "white_count", "wall_remaining", "route_improvements"):
        if check[key] != row[key]:
            raise ValueError("G10 路线动作前事实漂移：" + key)
    view = build_scoring_view(request)
    scored = ActionValueScorer("g10-teacher-parent-check", parent).score(view)
    ranked = sorted(scored.entries, key=lambda item: (-item.score, item.action_key))
    if scored.status != "SCORED" or ranked[0].action_key != row["parent_action"]:
        raise ValueError("G10 冻结父代首选漂移")
    if row["alternate_action"] not in {item.action_key for item in view.actions}:
        raise ValueError("G10 B 不再合法")
    table_id = str(raw["observation"]["game_id"]).removeprefix("sitin-stage:")
    if table_id != plans[row["table_no"] - 1].table_id:
        raise ValueError("G10 自然桌身份漂移")
    return {
        "target_id": f"g10-route-{index:03d}", "split": "development", "family": "discard",
        "route_kind": row["route_kind"],
        "source": dict(source, panel_seed=exposure.PANEL_SEED,
                       table_no=row["table_no"], table_id=table_id),
        "window_key": raw["window_key"], "competition": raw["competition"],
        "focal_physical_seat": raw["observation"]["seat"],
        "request_sha256": p84.value_digest(raw),
        "state_projection_sha256": p84.value_digest(p84.p13.state_projection(raw)),
        "reference_action": row["parent_action"],
        "intervention_action": row["alternate_action"],
        "features": {"round_no": row["round_no"], "route_kind": row["route_kind"],
                     "white_count": row["white_count"], "wall_remaining": row["wall_remaining"],
                     "parent_route_shanten": row["parent_route_shanten"],
                     "alternate_route_shanten": row["alternate_route_shanten"]},
    }


def prepare() -> None:
    """在生成任何双臂积分之前，冻结目标、未来墙键、依赖和预算。"""

    if OUT.exists():
        raise SystemExit("G10 教师目录已存在，拒绝覆盖")
    _document, rows = _selected_rows()
    targets = [_rebuild_target(row, index) for index, row in enumerate(rows, 1)]
    if len({(item["route_kind"], item["source"]["source_root_id"]) for item in targets}) != len(targets):
        raise ValueError("G10 同一路线内独立根重复")
    OUT.mkdir(parents=True)
    (_project_file(_PROJECT_ROOT, OUT / "snapshots")).mkdir()
    (_project_file(_PROJECT_ROOT, OUT / "rollouts")).mkdir()
    authorization = exposure.g1.p83.batch.unified_document(
        batch_label=OUT.name, authorization_id="g10-route-option-paired-teacher-20260927",
        accounts={"prefix_generation": len(targets),
                  "tables_full": len(targets) * len(SAMPLES) * 2},
        issued_by="lead", issued_at_utc=exposure.g1.p83.search.utc_now(), legacy_alias=False)
    authorization.update({"scope": "G10 两类路线 H/M 独立根，同墙八次、双臂当前完整桌",
                          "max_model_calls": 0, "confirmation_roots": 0})
    _write(_project_file(_PROJECT_ROOT, OUT / "authorization.json"), authorization)
    _write(_project_file(_PROJECT_ROOT, OUT / "targets.json"), {"schema": "g10-route-option-teacher-targets/1",
                                   "targets": targets, "outcome_labels_opened": False})
    closure = [Path(__file__), exposure.PREREG, EXPOSURE_RESULT, EXPOSURE_MANIFEST,
               Path(exposure.__file__), _project_file(_PROJECT_ROOT, OUT / "targets.json"), _project_file(_PROJECT_ROOT, OUT / "authorization.json"),
               *p84.source_paths()]
    _write(_project_file(_PROJECT_ROOT, OUT / "manifest.json"), {
        "schema": "g10-route-option-teacher-manifest/1",
        "created_at_utc": exposure.g1.p83.search.utc_now(),
        "runtime": exposure.g1.p83.guard.capture(source_paths=closure),
        "exposure_result_sha256": _sha(EXPOSURE_RESULT),
        "exposure_manifest_sha256": _sha(EXPOSURE_MANIFEST),
        "targets_sha256": _sha(_project_file(_PROJECT_ROOT, OUT / "targets.json")),
        "parent_source_sha256": exposure.g1.p83.R18_INTEGRATED_POSITIVE_V2_SHA256,
        "target_count": len(targets), "future_walls": len(SAMPLES),
        "planned_tables": len(targets) * len(SAMPLES) * 2,
        "sample_keys": SAMPLES, "outcome_labels_opened": False,
        "release_eligible": False,
    })
    print(json.dumps({"targets": len(targets),
                      "planned_tables": len(targets) * len(SAMPLES) * 2}))


def _verify() -> tuple[dict, list[dict]]:
    manifest = _read(_project_file(_PROJECT_ROOT, OUT / "manifest.json"))
    if (_sha(EXPOSURE_RESULT) != manifest["exposure_result_sha256"]
            or _sha(EXPOSURE_MANIFEST) != manifest["exposure_manifest_sha256"]
            or _sha(_project_file(_PROJECT_ROOT, OUT / "targets.json")) != manifest["targets_sha256"]
            or manifest["parent_source_sha256"] != exposure.g1.p83.R18_INTEGRATED_POSITIVE_V2_SHA256):
        raise ValueError("G10 教师冻结输入漂移")
    exposure.g1.p83.guard.verify(manifest["runtime"])
    targets = _read(_project_file(_PROJECT_ROOT, OUT / "targets.json"))
    if targets.get("outcome_labels_opened") is not False or len(targets["targets"]) != manifest["target_count"]:
        raise ValueError("G10 教师目标或结果盲状态漂移")
    return manifest, targets["targets"]


def _ledger():
    auth = _read(_project_file(_PROJECT_ROOT, OUT / "authorization.json"))
    exposure.g1.p83.natural.require_authorization(auth)
    return exposure.g1.p83.search.ActionValueLedger.load(
        _project_file(_PROJECT_ROOT, OUT / "ledger.json"),
        authorized_budgets=exposure.g1.p83.search.av_ledger_budgets_from_authorization(auth))


def capture() -> None:
    manifest, targets = _verify()
    book = _ledger()
    contract = _read(exposure.g1.CONTRACT)
    complete = 0
    for target in targets:
        path = p84.snapshot_path(target)
        if path.exists():
            complete += 1
            continue
        reservation = book.reserve(
            step_id="g10:teacher:capture:" + target["target_id"],
            account="prefix_generation", amount=1, note="冻结 R18 v2 精确合法前缀")
        try:
            snapshot = p84.capture_one(target, contract)
            snapshot["capture"]["consumer"] = "G10 route-option paired teacher"
            _write(path, snapshot)
            book.settle(reservation, actual=1, note="精确前缀捕获成功")
            complete += 1
        except BaseException:
            book.settle(reservation, usage_unknown=True, note="前缀异常，保守计费")
            raise
        if complete % 8 == 0 or complete == manifest["target_count"]:
            print(json.dumps({"captured": complete, "planned": manifest["target_count"]}), flush=True)
    _write(_project_file(_PROJECT_ROOT, OUT / "capture-summary.json"), {"captured": complete,
                                          "planned": manifest["target_count"],
                                          "spent": book.account_summary()})


def run() -> None:
    manifest, targets = _verify()
    if _read(_project_file(_PROJECT_ROOT, OUT / "capture-summary.json"))["captured"] != manifest["target_count"]:
        raise ValueError("G10 教师前缀未捕获完整")
    book = _ledger()
    completed = 0
    for target in targets:
        for index, sample_key in enumerate(SAMPLES, 1):
            path = p84.rollout_path(target, index)
            if path.exists():
                if _read(path).get("mechanical_ok") is not True:
                    raise ValueError("G10 已存双臂机械门失败")
                completed += 2
                continue
            reservation = book.reserve(
                step_id=f"g10:teacher:run:{target['target_id']}:{index:02d}",
                account="tables_full", amount=2, note="同隐藏前缀与共同未来墙当前完整桌")
            try:
                result = p84.execute_rollout(target, index, sample_key)
                if result.get("mechanical_ok") is not True:
                    raise ValueError("G10 双臂机械门失败")
                result["schema"] = "g10-route-option-teacher-rollout/1"
                result["route_kind"] = target["route_kind"]
                _write(path, result)
                book.settle(reservation, actual=2, note="两臂完整且机械门通过")
                completed += 2
            except BaseException:
                book.settle(reservation, usage_unknown=True, note="续打异常，保守计费")
                raise
        if completed % 128 == 0 or completed == manifest["planned_tables"]:
            print(json.dumps({"completed_tables": completed,
                              "planned_tables": manifest["planned_tables"]}), flush=True)
    _write(_project_file(_PROJECT_ROOT, OUT / "run-summary.json"), {"completed_tables": completed,
                                      "planned_tables": manifest["planned_tables"],
                                      "spent": book.account_summary()})


def analyze() -> None:
    """先在根内平均八份未来墙，再按 H/M 与路线独立根汇总。"""

    manifest, targets = _verify()
    if (_project_file(_PROJECT_ROOT, OUT / "result.json")).exists():
        raise SystemExit("G10 教师结果已存在，拒绝覆盖")
    if _read(_project_file(_PROJECT_ROOT, OUT / "run-summary.json"))["completed_tables"] != manifest["planned_tables"]:
        raise ValueError("G10 教师双臂完整桌未跑满")
    roots = []
    for target in targets:
        rows = [_read(p84.rollout_path(target, index)) for index in range(1, len(SAMPLES) + 1)]
        if any(row.get("mechanical_ok") is not True for row in rows):
            raise ValueError("G10 教师有机械门失败")
        deltas = [row["focal_current_table_score"]["delta"] for row in rows]
        round_deltas = [row["focal_current_round_settlement_delta"] for row in rows]
        wins = {arm: Counter() for arm in ("reference", "intervention")}
        transitions = Counter()
        for row in rows:
            transitions[row["reference"]["terminal"] + "->" + row["intervention"]["terminal"]] += 1
            for arm in wins:
                record = row[arm]
                if record["terminal"] == "focal_hu":
                    details = record["details"]
                    plain_only = details == ["平胡"]
                    has_special = any(item != "平胡" for item in details)
                    wins[arm]["focal_hu"] += 1
                    wins[arm]["plain_only_hu"] += int(plain_only)
                    wins[arm]["special_hu"] += int(has_special)
                    wins[arm]["focal_hu_settlement"] += record["focal_settlement"]
                    wins[arm]["plain_only_hu_settlement"] += (
                        record["focal_settlement"] if plain_only else 0)
                    wins[arm]["special_hu_settlement"] += (
                        record["focal_settlement"] if has_special else 0)
        roots.append({
            "target_id": target["target_id"], "route_kind": target["route_kind"],
            "source_root_id": target["source"]["source_root_id"],
            "mix": target["source"]["mix"],
            "reference_action": target["reference_action"],
            "intervention_action": target["intervention_action"],
            "table_delta_mean": statistics.mean(deltas),
            "target_round_delta_mean": statistics.mean(round_deltas),
            "table_deltas": deltas,
            "terminal_transitions": dict(sorted(transitions.items())),
            "focal_hu": {arm: dict(wins[arm]) for arm in wins},
        })
    by_route = {}
    for kind in ("standard", "seven_pairs"):
        selected = [row for row in roots if row["route_kind"] == kind]
        if not selected:
            continue
        by_mix = {}
        for mix in exposure.MIXES:
            pool = [row for row in selected if row["mix"] == mix]
            values = [row["table_delta_mean"] for row in pool]
            hu = {arm: dict(sum((Counter(row["focal_hu"][arm]) for row in pool), Counter()))
                  for arm in ("reference", "intervention")}
            terminal_transitions = sum(
                (Counter(row["terminal_transitions"]) for row in pool), Counter())
            leave_one_out = [statistics.mean(value for index, value in enumerate(values)
                                             if index != excluded)
                             for excluded in range(len(values))]
            by_mix[mix] = {"roots": len(values), "mean_delta": statistics.mean(values),
                           "positive": sum(value > 0 for value in values),
                           "zero": sum(value == 0 for value in values),
                           "negative": sum(value < 0 for value in values),
                           "min_root_delta": min(values), "max_root_delta": max(values),
                           "leave_one_root_out_mean_range": [min(leave_one_out), max(leave_one_out)],
                           "target_round_delta_mean": statistics.mean(
                               row["target_round_delta_mean"] for row in pool),
                           "terminal_transitions": dict(sorted(terminal_transitions.items())),
                           "focal_hu_counts_and_income": hu,
                           "plain_only_hu_count_delta": (
                               hu["intervention"].get("plain_only_hu", 0)
                               - hu["reference"].get("plain_only_hu", 0)),
                           "plain_only_hu_income_delta": (
                               hu["intervention"].get("plain_only_hu_settlement", 0)
                               - hu["reference"].get("plain_only_hu_settlement", 0))}
        overall = statistics.mean(row["table_delta_mean"] for row in selected)
        by_route[kind] = {"by_mix": by_mix, "overall_mean_delta": overall,
                          "score_only_gate": bool(
                              by_mix["H"]["mean_delta"] > 0
                              and by_mix["M"]["mean_delta"] > 0
                              and overall >= 2)}
    _write(_project_file(_PROJECT_ROOT, OUT / "result.json"), {
        "schema": "g10-route-option-teacher-result/1", "roots": roots,
        "by_route": by_route, "completed_tables": manifest["planned_tables"],
        "independence_unit": "route_kind × source_root_id",
        "outcome_labels_opened": True, "release_eligible": False,
        "note": "八张未来墙只减小根内噪声；分数门不代替普通胡机会人工审核，亦非发布门",
    })
    print(json.dumps({kind: value["by_mix"] | {
        "overall_mean_delta": value["overall_mean_delta"],
        "score_only_gate": value["score_only_gate"]}
        for kind, value in by_route.items()}, ensure_ascii=False))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("prepare", "capture", "run", "analyze"))
    args = parser.parse_args()
    {"prepare": prepare, "capture": capture, "run": run, "analyze": analyze}[args.command]()


if __name__ == "__main__":
    main()
