"""R18 P34：双财神留爆头候选的开发、回退与父代覆盖保持预检。"""

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
from dataclasses import replace
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

import r18_opportunity_behavior_preflight as real_behavior  # noqa: E402
import r18_p13_development_seven_pairs_teacher as p13  # noqa: E402
import r18_p32_two_wealth_baotou_rare_teacher as p32  # noqa: E402
import r18_p5_development_preflight as p5  # noqa: E402
import sitin_opportunities as opportunities  # noqa: E402
import sitin_search as search  # noqa: E402
from hangma_bot.hangma.engine import HangmaRules  # noqa: E402
from hangma_bot.application.audit_codec import decision_request_from_json  # noqa: E402
from hangma_bot.kernel.serialization import window_key_from_json  # noqa: E402
from hangma_bot.policy.action_value_policy import build_scoring_view  # noqa: E402
from hangma_bot.policy.action_value_seeds import ActionValueScorer  # noqa: E402


OUT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p34-two-wealth-candidate-preflight-01-20260922')
AUTHOR = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p33-two-wealth-author-01-20260922')
CANDIDATE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p33-two-wealth-author-01-20260922/generation-repair01/candidate.py')
PARENT = p32.PARENT
P32_RESULT = p32.OUT / "result.json"
P32_TARGETS = p32.OUT / "targets.json"
CONTRACT = p32.CONTRACT


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def request_from_snapshot(target: Mapping[str, Any], snapshot: Mapping[str, Any]) -> Any:
    """从已冻结开发快照重建目标窗口的正式决策请求。"""

    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    rules = HangmaRules(p13.core.rule_config_from_contract(contract))
    runtime = opportunities.build_real_runtime(
        rules_config=rules.config,
        rounds_per_game=int(snapshot["match_spec"]["rounds_per_game"]),
        seed=int(snapshot["match_spec"]["seed"]),
        scenario_id=str(snapshot["match_spec"]["scenario_id"]),
    )
    engine, world = opportunities.rebuild_world(
        rules=rules, snapshot=snapshot, value_limits=p13.LIMITS, runtime=runtime,
    )
    expected = window_key_from_json(target["window_key"])
    for decision in engine.frame(world).decisions:
        if decision.window_key != expected:
            continue
        analysis = rules.analyze(decision.observation, value_limits=p13.LIMITS)
        return opportunities.real_window_request(
            decision=decision, analysis=analysis,
            match_id=str(snapshot["match_spec"]["match_id"]),
            config=opportunities._driver_config(), now_monotonic=lambda: 800.0,
        )
    raise ValueError("快照重建后未找到冻结窗口：" + str(target["target_id"]))


def load_legacy_real_windows() -> tuple[list[tuple[str, Any, list[str]]], int]:
    """核验旧面板的文件与请求摘要；允许已记录的投影版本发生代码漂移。"""

    by_name: dict[str, tuple[Any, list[str]]] = {}
    drifted = 0
    for panel in real_behavior.PANELS:
        manifest = json.loads(panel.read_text(encoding="utf-8"))
        if (
            manifest.get("schema") != "sitin-real-behavior-panel/1"
            or manifest.get("purpose") != "development_behavior"
            or manifest.get("selection_eligible") is not False
        ):
            raise ValueError("旧控制集不是开发行为面板：" + str(panel))
        for entry in manifest.get("windows") or []:
            target = (panel.parent / entry["file"]).resolve()
            if not target.is_relative_to(panel.parent.resolve()):
                raise ValueError("旧控制窗口路径越界：" + str(target))
            data = json.loads(target.read_text(encoding="utf-8"))
            if real_behavior.behavior.digest(data) != entry["record_sha256"]:
                raise ValueError("旧控制窗口记录摘要漂移：" + str(target))
            if real_behavior.behavior.digest(data["request"]) != data["request_sha256"]:
                raise ValueError("旧控制请求摘要漂移：" + str(target))
            request = decision_request_from_json(data["request"])
            current = real_behavior.behavior.digest(
                build_scoring_view(request).candidate_view()
            )
            if current != entry["candidate_view_sha256"]:
                drifted += 1
            name = str(entry["candidate_view_sha256"])
            if name not in by_name:
                by_name[name] = (request, [])
            by_name[name][1].append(str(panel))
    return [
        (name, request, origins)
        for name, (request, origins) in sorted(by_name.items())
    ], drifted


def top_entry(batch: Any) -> Any:
    """按线上确定性排序返回首选条目。"""

    return min(batch.entries, key=lambda item: (-item.score, item.action_key))


def expected_target(view: Any, parent_batch: Any) -> str | None:
    """独立复刻 P33 冻结谓词，不读取候选 trace。"""

    parent_top = top_entry(parent_batch)
    fact_by_key = {item.action_key: item for item in view.actions}
    if fact_by_key[parent_top.action_key].action_type != "hu":
        return None
    visible = view.visible_state
    wealth = visible.rule_state.wealth_god.code
    own_meld_count = len(visible.melds[visible.seat])
    hand = [tile.code for tile in visible.my_hand]
    wealth_count = hand.count(wealth)
    if (
        visible.drawn_tile is not None
        and len(hand) != 14 - 3 * own_meld_count
        and visible.drawn_tile.code == wealth
    ):
        wealth_count += 1
    if wealth_count != 2:
        return None
    legal_hu = [
        item for item in view.actions
        if item.is_legal is True and item.action_type == "hu"
    ]
    legal_wealth_discards = [
        item for item in view.actions
        if item.is_legal is True
        and item.action_type == "discard"
        and item.action_key[8:] == wealth
    ]
    if len(legal_hu) != 1 or len(legal_wealth_discards) != 1:
        return None
    target = legal_wealth_discards[0]
    return target.action_key if target.baotou_after is True else None


def check_view(
    *, label: str, view: Any, parent: ActionValueScorer,
    candidate: ActionValueScorer,
) -> dict[str, Any]:
    """验证唯一允许的分数变化、选择结果、轨迹和工作量。"""

    parent_batch = parent.score(view)
    parent_operations = parent.last_operation_count
    candidate_batch = candidate.score(view)
    candidate_operations = candidate.last_operation_count
    if parent_batch.status != "SCORED" or candidate_batch.status != "SCORED":
        raise ValueError(label + " 未同时返回 SCORED")
    parent_entries = {item.action_key: item for item in parent_batch.entries}
    candidate_entries = {item.action_key: item for item in candidate_batch.entries}
    if parent_entries.keys() != candidate_entries.keys():
        raise ValueError(label + " 合法动作全集漂移")
    target = expected_target(view, parent_batch)
    changed = sorted(
        key for key in parent_entries if parent_entries[key] != candidate_entries[key]
    )
    if target is None:
        if changed:
            raise ValueError(label + " 非触发窗口未逐条保持 P5：" + repr(changed))
    else:
        if changed != [target]:
            raise ValueError(label + " 触发窗口只允许目标弃牌改变：" + repr(changed))
        parent_top = top_entry(parent_batch)
        candidate_target = candidate_entries[target]
        if candidate_target.score != parent_top.score + 1.0:
            raise ValueError(label + " 目标分数不是父代胡最终分+1.0")
        if top_entry(candidate_batch).action_key != target:
            raise ValueError(label + " 触发后未选择目标财神弃牌")
        trace = candidate_target.trace.get("two_wealth_piao_keeps_baotou_cf")
        if not isinstance(trace, Mapping) or trace.get("triggered") is not True:
            raise ValueError(label + " 缺少双财神触发轨迹")
        if trace.get("version") != "two_wealth_piao_keeps_baotou_cf/v1":
            raise ValueError(label + " 双财神轨迹版本漂移")
        for key, value in parent_entries[target].trace.items():
            if candidate_target.trace.get(key) != value:
                raise ValueError(label + " 目标动作父代轨迹字段被改写：" + key)
    return {
        "label": label,
        "expected_trigger": target is not None,
        "expected_target": target,
        "parent_top": top_entry(parent_batch).action_key,
        "candidate_top": top_entry(candidate_batch).action_key,
        "changed_action_keys": changed,
        "parent_operations": parent_operations,
        "candidate_operations": candidate_operations,
    }


def prepare() -> None:
    """在任何隐藏快照生成前冻结候选摘要与预检判据。"""

    if OUT.exists():
        raise SystemExit("P34 预检目录已存在；拒绝覆盖")
    result = json.loads(P32_RESULT.read_text(encoding="utf-8"))
    if result.get("decision") != "OPEN_P33_LIMITED_AUTHOR":
        raise ValueError("P32 没有开放受限候选作者")
    if result.get("hidden_labels_opened") is not False:
        raise ValueError("P32 隐藏标签必须保持封存")
    targets_document = json.loads(P32_TARGETS.read_text(encoding="utf-8"))
    hidden_ids = [
        row["target_id"] for row in targets_document["targets"]
        if row["split"] == "hidden"
    ]
    hidden_snapshots = [
        target_id for target_id in hidden_ids
        if (p32.OUT / "snapshots" / (target_id + ".json")).exists()
    ]
    if hidden_snapshots:
        raise ValueError("P34 冻结前已存在隐藏快照：" + repr(hidden_snapshots))
    OUT.mkdir(parents=True)
    write_json(_project_file(_PROJECT_ROOT, OUT / "manifest.json"), {
        "schema": "r18-p34-two-wealth-candidate-preflight-manifest/1",
        "created_at_utc": search.utc_now(),
        "candidate_sha256": digest(CANDIDATE),
        "parent_sha256": digest(PARENT),
        "p32_result_sha256": digest(P32_RESULT),
        "p32_targets_sha256": digest(P32_TARGETS),
        "contract_sha256": digest(CONTRACT),
        "candidate_static_precheck_sha256": digest(
            _project_file(_PROJECT_ROOT, AUTHOR / "generation-repair01/precheck.json")
        ),
        "gate": {
            "all_10_development_roots_must_trigger_exact_target": True,
            "only_exact_target_entry_may_change": True,
            "target_score_equals_parent_hu_final_score_plus": 1.0,
            "all_p5_discovery_and_existing_real_controls_follow_independent_predicate": True,
            "fail_closed_baotou_mutations_exact_parent": True,
            "candidate_operation_limit_must_hold": True,
        },
        "hidden_snapshots_before_freeze": 0,
        "hidden_labels_opened": False,
        "release_eligible": False,
    })
    print(json.dumps({
        "status": "P34_PREPARED", "development_states": 10,
        "hidden_states_kept_blind": len(hidden_ids),
    }, ensure_ascii=False))


def verify() -> dict[str, Any]:
    manifest = json.loads((_project_file(_PROJECT_ROOT, OUT / "manifest.json")).read_text(encoding="utf-8"))
    checks = {
        "candidate": (manifest["candidate_sha256"], digest(CANDIDATE)),
        "parent": (manifest["parent_sha256"], digest(PARENT)),
        "p32_result": (manifest["p32_result_sha256"], digest(P32_RESULT)),
        "p32_targets": (manifest["p32_targets_sha256"], digest(P32_TARGETS)),
        "contract": (manifest["contract_sha256"], digest(CONTRACT)),
    }
    for label, (expected, actual) in checks.items():
        if expected != actual:
            raise ValueError("P34 冻结输入漂移：" + label)
    return manifest


def run() -> None:
    """执行开发正例、父代既有覆盖、真实窗口与合成退化负控。"""

    manifest = verify()
    parent = ActionValueScorer("r18-p34-parent", PARENT.read_text(encoding="utf-8"))
    candidate = ActionValueScorer(
        "r18-p34-candidate", CANDIDATE.read_text(encoding="utf-8")
    )
    document = json.loads(P32_TARGETS.read_text(encoding="utf-8"))
    development = [row for row in document["targets"] if row["split"] == "development"]
    development_rows = []
    development_views = []
    for target in development:
        snapshot = json.loads(p32.snapshot_path(target).read_text(encoding="utf-8"))
        request = request_from_snapshot(target, snapshot)
        view = build_scoring_view(request)
        development_views.append((target, view))
        development_rows.append(check_view(
            label=target["target_id"], view=view,
            parent=parent, candidate=candidate,
        ))

    p5_rows = []
    for target in p5.prior.targets():
        request = p5.exact_request(target)
        p5_rows.append(check_view(
            label="p5:" + target["target_id"], view=build_scoring_view(request),
            parent=parent, candidate=candidate,
        ))

    real_rows = []
    real_windows, drifted_real_records = load_legacy_real_windows()
    for name, request, _origins in real_windows:
        real_rows.append(check_view(
            label="real:" + name, view=build_scoring_view(request),
            parent=parent, candidate=candidate,
        ))

    first_target, first_view = development_views[0]
    wealth_key = str(first_target["intervention_action"])
    fail_closed_rows = []
    for name, value in (("baotou_false", False), ("baotou_unknown", None)):
        mutated_actions = tuple(
            replace(item, baotou_after=value) if item.action_key == wealth_key else item
            for item in first_view.actions
        )
        fail_closed_rows.append(check_view(
            label="mutation:" + name,
            view=replace(first_view, actions=mutated_actions),
            parent=parent, candidate=candidate,
        ))
    wealth_tile = first_view.visible_state.rule_state.wealth_god
    three_wealth_visible = replace(
        first_view.visible_state,
        my_hand=tuple(first_view.visible_state.my_hand) + (wealth_tile,),
    )
    fail_closed_rows.append(check_view(
        label="mutation:three_wealth",
        view=replace(first_view, visible_state=three_wealth_visible),
        parent=parent, candidate=candidate,
    ))

    all_rows = development_rows + p5_rows + real_rows + fail_closed_rows
    checks = {
        "ten_development_roots_trigger_exact_target": (
            len(development_rows) == 10
            and all(row["expected_trigger"] for row in development_rows)
            and all(row["candidate_top"] == row["expected_target"] for row in development_rows)
        ),
        "only_expected_entry_changes": all(
            row["changed_action_keys"]
            == ([row["expected_target"]] if row["expected_trigger"] else [])
            for row in all_rows
        ),
        "p5_discovery_controls_preserved": len(p5_rows) == 7,
        "existing_real_controls_follow_predicate": bool(real_rows),
        "three_fail_closed_mutations_exact_parent": (
            len(fail_closed_rows) == 3
            and all(not row["expected_trigger"] and not row["changed_action_keys"]
                    for row in fail_closed_rows)
        ),
        "operation_limit_holds": max(
            row["candidate_operations"] for row in all_rows
        ) <= candidate.max_operations,
        "hidden_snapshots_remain_zero": not any(
            p32.snapshot_path(row).exists()
            for row in document["targets"] if row["split"] == "hidden"
        ),
    }
    passed = all(checks.values())
    result = {
        "schema": "r18-p34-two-wealth-candidate-preflight-result/1",
        "status": "PASS_P34_DEVELOPMENT" if passed else "FAIL_P34_DEVELOPMENT",
        "checks": checks,
        "candidate_sha256": manifest["candidate_sha256"],
        "development_rows": development_rows,
        "p5_discovery_rows": p5_rows,
        "existing_real_windows": {
            "windows": len(real_rows),
            "triggers": sum(row["expected_trigger"] for row in real_rows),
            "legacy_projection_drifted_records": drifted_real_records,
            "interpretation": (
                "旧面板仍逐文件核验记录与请求摘要；只放宽历史 candidate_view "
                "摘要与当前投影代码相等的要求，父代与候选始终消费同一当前重建视图"
            ),
            "rows": real_rows,
        },
        "fail_closed_mutations": fail_closed_rows,
        "maximum_candidate_operations": max(
            row["candidate_operations"] for row in all_rows
        ),
        "operation_limit": candidate.max_operations,
        "source_quality_note": (
            "作者源码含一个随即被正确常量覆盖的冗余 canonical_codes 赋值；"
            "不影响本次行为门，正式策略接缝前应做等价规范化并复跑此预检"
        ),
        "hidden_labels_opened": False,
        "decision": (
            "OPEN_P35_HIDDEN_ADMISSION" if passed
            else "CLOSE_P33_CANDIDATE_AND_DIAGNOSE"
        ),
        "selection_eligible": passed,
        "release_eligible": False,
    }
    write_json(_project_file(_PROJECT_ROOT, OUT / "result.json"), result)
    print(json.dumps({
        "status": result["status"], "checks": checks,
        "development_triggers": sum(row["expected_trigger"] for row in development_rows),
        "p5_discovery_windows": len(p5_rows),
        "existing_real_windows": len(real_rows),
        "existing_real_triggers": sum(row["expected_trigger"] for row in real_rows),
        "maximum_candidate_operations": result["maximum_candidate_operations"],
        "operation_limit": result["operation_limit"],
        "decision": result["decision"],
    }, ensure_ascii=False, indent=2))
    if not passed:
        raise RuntimeError("P34 开发预检失败")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("prepare", "run"))
    globals()[parser.parse_args().operation]()


if __name__ == "__main__":
    main()
