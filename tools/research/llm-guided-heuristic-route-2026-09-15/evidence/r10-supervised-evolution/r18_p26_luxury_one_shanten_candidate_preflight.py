"""R18 P26：锁定豪华组一向听候选的冻结与逐点回退预检。"""

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

from collections import Counter
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

import r18_p13_development_seven_pairs_teacher as p13  # noqa: E402
import r18_p23_luxury_locked_headroom as p23  # noqa: E402
import r18_p25_luxury_one_shanten_development_teacher as p25  # noqa: E402
import sitin_opportunities as opportunities  # noqa: E402
import sitin_search as search  # noqa: E402
from hangma_bot.application.audit_codec import decision_request_from_json  # noqa: E402
from hangma_bot.hangma.engine import HangmaRules  # noqa: E402
from hangma_bot.kernel.serialization import window_key_from_json  # noqa: E402
from hangma_bot.policy.action_value_policy import build_scoring_view  # noqa: E402
from hangma_bot.policy.action_value_seeds import ActionValueScorer  # noqa: E402


OUT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p26-luxury-one-shanten-candidate-01-20260922')
CANDIDATE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p26-luxury-one-shanten-candidate-01-20260922/generation/candidate.py')
PARENT = p25.PARENT
P25_RESULT = p25.OUT / "result.json"
P25_TARGETS = p25.OUT / "targets.json"
P23_TARGETS = p23.OUT / "targets.json"
CONTRACT = p25.CONTRACT


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def request_from_snapshot(target: Mapping[str, Any], snapshot: Mapping[str, Any]) -> Any:
    """从已冻结开发快照重建目标窗口的正式 ``DecisionRequest``。"""

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
            decision=decision, analysis=analysis, match_id=str(snapshot["match_spec"]["match_id"]),
            config=opportunities._driver_config(), now_monotonic=lambda: 800.0,
        )
    raise ValueError("快照重建后未找到冻结目标窗口：" + str(target["target_id"]))


def p23_request(target: Mapping[str, Any]) -> Any:
    """只读取 P23 已绑定的 P16 文件并按摘要找回正式请求。"""

    path = _project_file(_PROJECT_ROOT, ROOT / str(target["source"]["p16_source_path"]))
    if digest(path) != target["source"]["p16_source_sha256"]:
        raise ValueError("P23 绑定的 P16 来源漂移：" + str(path))
    document = json.loads(path.read_text(encoding="utf-8"))
    hits = [
        row["request"] for row in document["audit"]["eligible_rows"]
        if row["request_sha256"] == target["request_sha256"]
    ]
    if len(hits) != 1:
        raise ValueError("P23 请求摘要未唯一命中：" + str(target["target_id"]))
    return decision_request_from_json(hits[0])


def expected_intervention(view: Any, parent_batch: Any) -> str | None:
    """独立复刻 P24 冻结谓词，返回应提升的 P5 保留四张弃牌。"""

    observation = view.visible_state
    if observation.phase != "draw" or observation.melds[observation.seat]:
        return None
    hand = [tile.code for tile in observation.my_hand]
    if observation.drawn_tile is not None and len(hand) != observation.hand_counts[observation.seat]:
        hand.append(observation.drawn_tile.code)
    counts = Counter(hand)
    wealth = observation.rule_state.wealth_god.code
    locked = sorted(code for code, count in counts.items() if count == 4 and code != wealth)
    if len(locked) != 1:
        return None
    entries = sorted(parent_batch.entries, key=lambda item: (-item.score, item.action_key))
    reference = "gang:concealed:" + locked[0]
    if not entries or entries[0].action_key != reference:
        return None
    preserve = [
        item for item in entries
        if item.action_key.startswith("discard:")
        and item.action_key.split(":", 1)[1] != locked[0]
    ]
    if not preserve:
        return None
    facts = {item.action_key: item for item in view.actions}
    if (
        facts[reference].standard_shanten_after != 1
        or facts[preserve[0].action_key].standard_shanten_after != 1
    ):
        return None
    return preserve[0].action_key


def check_one(
    *, label: str, request: Any,
    parent: ActionValueScorer, candidate: ActionValueScorer,
) -> dict[str, Any]:
    """核对触发窗口只改变目标动作，非触发窗口逐点等于 P5。"""

    view = build_scoring_view(request)
    parent_batch = parent.score(view)
    parent_operations = parent.last_operation_count
    candidate_batch = candidate.score(view)
    candidate_operations = candidate.last_operation_count
    if parent_batch.status != "SCORED" or candidate_batch.status != "SCORED":
        raise ValueError(label + " 评分未返回 SCORED")
    target = expected_intervention(view, parent_batch)
    parent_entries = {item.action_key: item for item in parent_batch.entries}
    candidate_entries = {item.action_key: item for item in candidate_batch.entries}
    if parent_entries.keys() != candidate_entries.keys():
        raise ValueError(label + " 动作全集漂移")
    changed = sorted(
        key for key in parent_entries
        if parent_entries[key] != candidate_entries[key]
    )
    parent_top = min(parent_batch.entries, key=lambda item: (-item.score, item.action_key))
    candidate_top = min(candidate_batch.entries, key=lambda item: (-item.score, item.action_key))
    if target is None:
        if changed or parent_batch != candidate_batch:
            raise ValueError(label + " 非触发窗口未逐点回退 P5")
    else:
        if changed != [target]:
            raise ValueError(label + " 触发窗口改动动作不是唯一目标弃牌：" + repr(changed))
        if candidate_top.action_key != target:
            raise ValueError(label + " 触发后未选择冻结目标弃牌")
        trace = candidate_entries[target].trace.get("r18_luxury_one_shanten_overlay")
        if not isinstance(trace, Mapping) or trace.get("triggered") is not True:
            raise ValueError(label + " 缺少可审计触发轨迹")
        if trace.get("reference_gang") != parent_top.action_key:
            raise ValueError(label + " 轨迹中的参考暗杠漂移")
    return {
        "label": label,
        "expected_trigger": target is not None,
        "expected_intervention": target,
        "parent_top": parent_top.action_key,
        "candidate_top": candidate_top.action_key,
        "changed_action_keys": changed,
        "parent_operations": parent_operations,
        "candidate_operations": candidate_operations,
    }


def main() -> None:
    p25_result = json.loads(P25_RESULT.read_text(encoding="utf-8"))
    if p25_result.get("status") != "OPEN_NARROW_CANDIDATE_AUTHORING":
        raise ValueError("P25 未开放窄候选编写")
    if p25_result.get("replication_labels_opened") is not False:
        raise ValueError("P25 复验标签必须仍未打开")
    manifest_path = _project_file(_PROJECT_ROOT, OUT / "manifest.json")
    if manifest_path.exists():
        raise SystemExit("P26 manifest 已存在；拒绝覆盖冻结候选")
    source = CANDIDATE.read_text(encoding="utf-8")
    parent_source = PARENT.read_text(encoding="utf-8")
    manifest = {
        "schema": "r18-p26-luxury-one-shanten-candidate-manifest/1",
        "created_at_utc": search.utc_now(),
        "candidate_sha256": digest(CANDIDATE),
        "parent_sha256": digest(PARENT),
        "p25_result_sha256": digest(P25_RESULT),
        "p25_targets_sha256": digest(P25_TARGETS),
        "p23_targets_sha256": digest(P23_TARGETS),
        "contract_sha256": digest(CONTRACT),
        "frozen_scope": (
            "draw；本人门清；恰一组非财神自然四张；P5首选对应暗杠；"
            "P5最高分且不拆该四张的弃牌存在；两动作standard_shanten_after均为1"
        ),
        "mutation": "仅把该保留弃牌提升到P5原首选分+0.5；其余动作及所有非触发窗口逐点保持P5",
        "development_labels_used": True,
        "replication_labels_opened": False,
        "model_calls": 0,
        "release_eligible": False,
    }
    write_json(manifest_path, manifest)
    parent = ActionValueScorer("r18-p26-preflight-parent", parent_source)
    candidate = ActionValueScorer("r18-p26-preflight-candidate", source)
    p25_targets = json.loads(P25_TARGETS.read_text(encoding="utf-8"))["targets"]
    rows = []
    for target in p25_targets:
        if target["split"] != "development":
            continue
        snapshot = json.loads(p25.snapshot_path(target).read_text(encoding="utf-8"))
        rows.append(check_one(
            label=target["target_id"],
            request=request_from_snapshot(target, snapshot),
            parent=parent, candidate=candidate,
        ))
    p23_targets = json.loads(P23_TARGETS.read_text(encoding="utf-8"))["targets"]
    for target in p23_targets:
        rows.append(check_one(
            label=target["target_id"], request=p23_request(target),
            parent=parent, candidate=candidate,
        ))
    development = [row for row in rows if row["label"].startswith("r18-p25-")]
    historical = [row for row in rows if row["label"].startswith("r18-p23-")]
    result = {
        "schema": "r18-p26-luxury-one-shanten-candidate-preflight/1",
        "status": "OPEN_BLIND_REPLICATION",
        "mechanical_ok": True,
        "candidate_sha256": manifest["candidate_sha256"],
        "development_windows": len(development),
        "development_triggers": sum(row["expected_trigger"] for row in development),
        "historical_control_windows": len(historical),
        "historical_control_triggers": sum(row["expected_trigger"] for row in historical),
        "historical_control_fallbacks": sum(not row["expected_trigger"] for row in historical),
        "maximum_candidate_operations": max(row["candidate_operations"] for row in rows),
        "operation_limit": candidate.max_operations,
        "replication_labels_opened": False,
        "rows": rows,
        "next": "保持候选源码与作用域冻结，打开P24预留12个replication自然根",
        "selection_eligible": True,
        "release_eligible": False,
    }
    if result["development_triggers"] != 12:
        raise ValueError("P25 12 个开发窗口未全部触发候选")
    if result["historical_control_triggers"] != 4 or result["historical_control_fallbacks"] != 8:
        raise ValueError("P23 事后诊断的4个同一向听/8个非同一向听控制未复现")
    write_json(_project_file(_PROJECT_ROOT, OUT / "preflight.json"), result)
    print(json.dumps({key: result[key] for key in (
        "status", "mechanical_ok", "development_windows", "development_triggers",
        "historical_control_windows", "historical_control_triggers",
        "historical_control_fallbacks", "maximum_candidate_operations",
        "operation_limit", "replication_labels_opened", "next",
    )}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
