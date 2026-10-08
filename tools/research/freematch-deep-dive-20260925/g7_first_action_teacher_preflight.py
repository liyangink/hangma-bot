#!/usr/bin/env python3
"""G7 小批同隐藏世界首动作配对：只用于三摸代理价值工程核验。"""

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
import g1_timing_natural_exposure as g1  # noqa: E402
import g7_g6_overlap as overlap  # noqa: E402
import g7_natural_three_draw_exposure as g7  # noqa: E402
import g7_new_root_exposure_pilot as pilot  # noqa: E402
from hangma_bot.application.audit_codec import decision_request_to_json  # noqa: E402
from hangma_bot.policy.action_value_seeds import ActionValueScorer  # noqa: E402

R10 = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution')
sys.path.insert(0, str(R10))
import r18_p84_high_wealth_near_seven_current_table_teacher as p84  # noqa: E402

OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g7-first-action-teacher-preflight-20260927')
PREREG = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/G7-FIRST-ACTION-TEACHER-PREFLIGHT-PREREG-2026-09-27.md')
PILOT_RESULT = pilot.OUT / "result.json"
PILOT_MANIFEST = pilot.OUT / "manifest.json"
SAMPLES = tuple(f"g7-pair-future-{index:02d}" for index in range(1, 9))
p84.OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g7-first-action-teacher-preflight-20260927')  # 只重定向既有 P84 快照/续打路径，规则与双臂执行代码不复制。


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                    encoding="utf-8")


def _selected_pilot_rows():
    doc = _read(PILOT_RESULT)
    if (doc.get("outcome_labels_opened") is not False or doc.get("planned_tables") != 64
            or doc.get("parent_source_sha256") != g1.p83.R18_INTEGRATED_POSITIVE_V2_SHA256):
        raise ValueError("G7 新根试跑身份或结果盲状态不符")
    by_root = {}
    for row in doc["rows"]:
        if row["delta_2"] != 0 or row["delta_3"] <= 0:
            continue
        root = row["source"]["source_root_id"]
        if root not in by_root or row["hash"] < by_root[root]["hash"]:
            by_root[root] = row
    selected = sorted(by_root.values(), key=lambda row: (row["group"], row["hash"]))
    counts = Counter(row["group"] for row in selected)
    if counts != Counter({"H": 3, "M": 4}):
        raise ValueError("预登记的 H3/M4 独立正差根数漂移")
    return selected


def _rebuild_target(row, index):
    source = row["source"]
    contract = _read(g1.CONTRACT)
    parent = g1.p83.parent_source()
    plans = g1.p83.natural.build_seat_stage_plans(
        contract=contract, opponent=source["mix"], root_index=source["root_index"],
        focal_seat=source["focal_seat"], panel_seed=pilot.PANEL_SEED,
    )
    requests = []
    name = "g7-teacher-target-" + source["source_id"]
    stage = g1.p83.natural.run_arm_stage(
        arm="candidate", plans=plans,
        candidate_scorer=ActionValueScorer(name, parent),
        opponent_policies=contract["panel"]["opponent_scenarios"][source["mix"]][
            "opponent_policies"],
        versions_block=g1.p83.natural.stage.contract_versions_block(contract),
        step_limit=int(contract["stop"]["step_limit"]),
        value_limits=g1.p83.LIMITS, decision_observer=requests.append,
    )
    if stage.get("status") != "complete" or len(stage.get("tables") or []) != 2:
        raise ValueError("重建来源未跑满")
    expected_ids = ["action_value_v1:" + name] * 2
    actual_ids = []
    for plan, table in zip(plans, stage["tables"]):
        seat = plan.seats().index(g1.p83.natural.FOCAL_PARTICIPANT)
        ids = (table.get("policy_execution") or {}).get("policy_ids_by_seat") or []
        actual_ids.append(ids[seat] if len(ids) == 4 else None)
    if actual_ids != expected_ids:
        raise ValueError("重建来源焦点策略身份不符")
    matches = [request for request in requests
               if (request.observation.game_id, request.observation.round_no,
                   request.trigger_seq) ==
               (row["game_id"], row["round_no"], row["trigger_seq"])]
    if len(matches) != 1:
        raise ValueError("冻结窗口重建次数不是一：" + row["game_id"])
    request = matches[0]
    raw = decision_request_to_json(request)
    view = g1.build_scoring_view(request)
    scored = ActionValueScorer("g7-teacher-parent-check", parent).score(view)
    ranked = sorted(scored.entries, key=lambda item: (-item.score, item.action_key))
    if scored.status != "SCORED" or ranked[0].action_key != row["a"]:
        raise ValueError("目标窗口冻结父代首选漂移")
    legal = {item.action_key for item in view.actions}
    if row["b"] not in legal:
        raise ValueError("目标替代动作不合法")
    if overlap._useful_distribution(raw, row["a"]) != overlap._useful_distribution(raw, row["b"]):
        raise ValueError("完整一步有效牌分布漂移")
    if overlap._useful_distribution(raw, row["a"]) is None:
        raise ValueError("完整一步有效牌分布缺失")
    recomputed = g7._evaluate({"group": row["group"], "room": row["room"],
                               "game_id": row["game_id"], "round_no": row["round_no"],
                               "trigger_seq": row["trigger_seq"], "hash": row["hash"],
                               "a": row["a"], "b": row["b"],
                               "shanten": row["shanten"], "whites": row["whites"],
                               "request": raw})
    if any(recomputed[field] != row[field] for field in
           ("delta_2", "delta_3", "capacity", "unknown_pool")):
        raise ValueError("目标窗口两摸/三摸规则容量漂移")
    table_id = str(raw["observation"]["game_id"]).removeprefix("sitin-stage:")
    if "-t" not in table_id or not table_id.rsplit("-t", 1)[1].isdigit():
        raise ValueError("自然桌 ID 缺少桌号")
    table_no = int(table_id.rsplit("-t", 1)[1])
    target = {
        "target_id": f"g7-teacher-{index:02d}", "split": "development",
        "family": "discard",
        "source": dict(source, panel_seed=pilot.PANEL_SEED,
                       table_no=table_no, table_id=table_id),
        "window_key": raw["window_key"], "competition": raw["competition"],
        "focal_physical_seat": raw["observation"]["seat"],
        "request_sha256": p84.value_digest(raw),
        "state_projection_sha256": p84.value_digest(p84.p13.state_projection(raw)),
        "reference_action": row["a"], "intervention_action": row["b"],
        "features": {"round_no": row["round_no"], "shanten": row["shanten"],
                     "whites": row["whites"], "delta_2": row["delta_2"],
                     "delta_3": row["delta_3"]},
        "request": raw,
    }
    return target


def prepare() -> None:
    if OUT.exists():
        raise SystemExit("教师目录已存在，拒绝覆盖")
    selected = _selected_pilot_rows()
    targets = [_rebuild_target(row, index) for index, row in enumerate(selected, 1)]
    roots = [target["source"]["source_root_id"] for target in targets]
    if len(roots) != len(set(roots)):
        raise ValueError("独立牌山根重复")
    OUT.mkdir(parents=True)
    (_project_file(_PROJECT_ROOT, OUT / "snapshots")).mkdir()
    (_project_file(_PROJECT_ROOT, OUT / "rollouts")).mkdir()
    auth = g1.p83.batch.unified_document(
        batch_label=OUT.name, authorization_id="g7-first-action-teacher-preflight-20260927",
        accounts={"prefix_generation": len(targets),
                  "tables_full": len(targets) * len(SAMPLES) * 2},
        issued_by="lead", issued_at_utc=g1.p83.search.utc_now(), legacy_alias=False,
    )
    auth.update({"scope": "7 根×8 共同未来墙×双臂当前完整桌工程教师",
                 "max_model_calls": 0, "confirmation_roots": 0})
    _write(_project_file(_PROJECT_ROOT, OUT / "authorization.json"), auth)
    _write(_project_file(_PROJECT_ROOT, OUT / "targets.json"), {"schema": "g7-teacher-targets/1",
                                   "targets": targets, "outcome_labels_opened": False})
    import hangma_bot.offline.forced_action as forced_action
    import hangma_bot.offline.evaluate as evaluate
    import hangma_bot.simulation.engine as simulation_engine
    import hangma_bot.simulation.shuffle as simulation_shuffle
    closure = [Path(__file__), PREREG, PILOT_RESULT, PILOT_MANIFEST,
               Path(pilot.__file__), Path(g1.__file__), Path(overlap.__file__),
               Path(g7.__file__), _project_file(_PROJECT_ROOT, OUT / "targets.json"), _project_file(_PROJECT_ROOT, OUT / "authorization.json"),
               *p84.source_paths()]
    _write(_project_file(_PROJECT_ROOT, OUT / "manifest.json"), {
        "schema": "g7-teacher-manifest/1", "created_at_utc": g1.p83.search.utc_now(),
        "runtime": g1.p83.guard.capture(source_paths=closure),
        "pilot_result_sha256": _sha(PILOT_RESULT),
        "pilot_manifest_sha256": _sha(PILOT_MANIFEST),
        "parent_sha256": g1.p83.R18_INTEGRATED_POSITIVE_V2_SHA256,
        "targets_sha256": _sha(_project_file(_PROJECT_ROOT, OUT / "targets.json")),
        "roots": len(targets), "future_walls": len(SAMPLES),
        "planned_tables": len(targets) * len(SAMPLES) * 2,
        "sample_keys": SAMPLES, "outcome_labels_opened": False,
        "release_eligible": False,
    })
    print(json.dumps({"prepared_roots": len(targets), "planned_tables": 112}))


def _verify():
    manifest = _read(_project_file(_PROJECT_ROOT, OUT / "manifest.json"))
    if (_sha(PILOT_RESULT) != manifest["pilot_result_sha256"]
            or _sha(PILOT_MANIFEST) != manifest["pilot_manifest_sha256"]
            or manifest["parent_sha256"] != g1.p83.R18_INTEGRATED_POSITIVE_V2_SHA256
            or _sha(_project_file(_PROJECT_ROOT, OUT / "targets.json")) != manifest["targets_sha256"]):
        raise ValueError("冻结来源或目标摘要漂移")
    g1.p83.guard.verify(manifest["runtime"])
    targets_doc = _read(_project_file(_PROJECT_ROOT, OUT / "targets.json"))
    if targets_doc.get("outcome_labels_opened") is not False:
        raise ValueError("目标结果盲状态漂移")
    targets = targets_doc["targets"]
    if len(targets) != manifest["roots"]:
        raise ValueError("目标根数漂移")
    return manifest, targets


def _ledger():
    auth = _read(_project_file(_PROJECT_ROOT, OUT / "authorization.json"))
    g1.p83.natural.require_authorization(auth)
    return g1.p83.search.ActionValueLedger.load(
        _project_file(_PROJECT_ROOT, OUT / "ledger.json"),
        authorized_budgets=g1.p83.search.av_ledger_budgets_from_authorization(auth),
    )


def capture() -> None:
    manifest, targets = _verify()
    book = _ledger()
    contract = _read(g1.CONTRACT)
    complete = 0
    for target in targets:
        path = p84.snapshot_path(target)
        if path.exists():
            complete += 1
            continue
        reservation = book.reserve(
            step_id="g7:teacher:capture:" + target["target_id"],
            account="prefix_generation", amount=1,
            note="冻结 R18 v2 精确合法前缀",
        )
        try:
            snapshot = p84.capture_one(target, contract)
            snapshot["capture"]["consumer"] = "G7 first-action teacher preflight"
            _write(path, snapshot)
            book.settle(reservation, actual=1, note="精确前缀捕获成功")
            complete += 1
        except BaseException:
            book.settle(reservation, usage_unknown=True, note="前缀异常，保守计费")
            raise
        print(json.dumps({"captured": complete, "planned": manifest["roots"]}), flush=True)
    _write(_project_file(_PROJECT_ROOT, OUT / "capture-summary.json"), {"captured": complete,
                                          "planned": manifest["roots"],
                                          "spent": book.account_summary()})


def run() -> None:
    manifest, targets = _verify()
    if _read(_project_file(_PROJECT_ROOT, OUT / "capture-summary.json"))["captured"] != manifest["roots"]:
        raise ValueError("精确前缀未捕获完整")
    book = _ledger()
    completed = 0
    for target in targets:
        for index, sample_key in enumerate(SAMPLES, 1):
            path = p84.rollout_path(target, index)
            if path.exists():
                if _read(path).get("mechanical_ok") is not True:
                    raise ValueError("已有双臂结果机械门失败")
                completed += 2
                continue
            reservation = book.reserve(
                step_id=f"g7:teacher:run:{target['target_id']}:{index:02d}",
                account="tables_full", amount=2,
                note="同隐藏世界首动作 A/B 当前完整桌",
            )
            try:
                result = p84.execute_rollout(target, index, sample_key)
                if result.get("mechanical_ok") is not True:
                    raise ValueError("首动作双臂机械门失败")
                result["schema"] = "g7-first-action-teacher-rollout/1"
                _write(path, result)
                book.settle(reservation, actual=2, note="两臂完整且机械门通过")
                completed += 2
            except BaseException:
                book.settle(reservation, usage_unknown=True, note="续打异常，保守计费")
                raise
        print(json.dumps({"completed_tables": completed,
                          "planned_tables": manifest["planned_tables"]}), flush=True)
    _write(_project_file(_PROJECT_ROOT, OUT / "run-summary.json"), {"completed_tables": completed,
                                      "planned_tables": manifest["planned_tables"],
                                      "spent": book.account_summary()})


def analyze() -> None:
    manifest, targets = _verify()
    if (_project_file(_PROJECT_ROOT, OUT / "result.json")).exists():
        raise SystemExit("教师结果已存在，拒绝覆盖")
    if _read(_project_file(_PROJECT_ROOT, OUT / "run-summary.json"))["completed_tables"] != manifest["planned_tables"]:
        raise ValueError("双臂完整桌未跑满")
    roots = []
    for target in targets:
        deltas = []
        rounds = []
        transitions = Counter()
        focal_win_fans = {"reference": [], "intervention": []}
        focal_win_details = {"reference": [], "intervention": []}
        for index in range(1, len(SAMPLES)+1):
            result = _read(p84.rollout_path(target, index))
            if result.get("mechanical_ok") is not True:
                raise ValueError("双臂机械门失败")
            deltas.append(result["focal_current_table_score"]["delta"])
            rounds.append(result["focal_current_round_settlement_delta"])
            transitions[result["reference"]["terminal"] + "->" +
                        result["intervention"]["terminal"]] += 1
            for arm, key in (("reference", "reference"),
                             ("intervention", "intervention")):
                record = result[key]
                if record["terminal"] == "focal_hu":
                    focal_win_fans[arm].append(record["fan"])
                    focal_win_details[arm].append(record["details"])
        roots.append({"target_id": target["target_id"],
                      "source_root_id": target["source"]["source_root_id"],
                      "mix": target["source"]["mix"],
                      "reference_action": target["reference_action"],
                      "intervention_action": target["intervention_action"],
                      "whites": target["features"]["whites"],
                      "delta_3": target["features"]["delta_3"],
                      "table_delta_mean": statistics.mean(deltas),
                      "target_round_delta_mean": statistics.mean(rounds),
                      "table_deltas": deltas,
                      "terminal_transitions": dict(sorted(transitions.items())),
                      "focal_win_fans": focal_win_fans,
                      "focal_win_details": focal_win_details})
    by_mix = {mix: [row["table_delta_mean"] for row in roots if row["mix"] == mix]
              for mix in ("H", "M")}
    summary = {mix: {"roots": len(values),
                     "mean_delta": statistics.mean(values) if values else None,
                     "positive": sum(value > 0 for value in values),
                     "zero": sum(value == 0 for value in values),
                     "negative": sum(value < 0 for value in values)}
               for mix, values in by_mix.items()}
    all_values = [row["table_delta_mean"] for row in roots]
    overall_transitions = Counter()
    for row in roots:
        overall_transitions.update(row["terminal_transitions"])
    output = {"schema": "g7-first-action-teacher-preflight-result/1",
              "roots": roots, "by_mix": summary,
              "overall_mean_delta": statistics.mean(all_values),
              "terminal_transitions": dict(sorted(overall_transitions.items())),
              "completed_tables": manifest["planned_tables"],
              "independence_unit": "source_root_id",
              "release_eligible": False,
              "note": "7 根开发工程教师，根内八未来墙不能当独立样本"}
    _write(_project_file(_PROJECT_ROOT, OUT / "result.json"), output)
    print(json.dumps({"by_mix": summary,
                      "overall_mean_delta": output["overall_mean_delta"]},
                     ensure_ascii=False))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("prepare", "capture", "run", "analyze"))
    args = parser.parse_args()
    {"prepare": prepare, "capture": capture, "run": run,
     "analyze": analyze}[args.command]()


if __name__ == "__main__":
    main()
