"""R18 P37：规范化双财神候选并登记为活动研究父代。"""

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
from typing import Any


HERE = Path(__file__).resolve().parent
ROUTE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15')
ROOT = _PROJECT_ROOT
for path in (_project_file(_PROJECT_ROOT, ROOT / "src"), _project_file(_PROJECT_ROOT, ROUTE / "tools"), HERE):
    sys.path.insert(0, str(path))

import r18_p32_two_wealth_baotou_rare_teacher as p32  # noqa: E402
import r18_p33_two_wealth_author as p33  # noqa: E402
import r18_p34_two_wealth_candidate_preflight as p34  # noqa: E402
import r18_p35_two_wealth_hidden_admission as p35  # noqa: E402
import r18_p5_development_preflight as p5  # noqa: E402
import sitin_search as search  # noqa: E402
from hangma_bot.policy.action_value_policy import build_scoring_view  # noqa: E402
from hangma_bot.policy.action_value_seeds import ActionValueScorer  # noqa: E402


OUT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p37-two-wealth-active-parent-01-20260922')
SOURCE = p34.CANDIDATE
P34_RESULT = p34.OUT / "result.json"
P35_RESULT = p35.OUT / "result.json"
P36_RESULT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p36-two-wealth-table-safety-01-20260922/result.json')

DEAD_ASSIGNMENT = '''    canonical_codes = (
        "1w", "2w", "3w", "3w", "4w", "5w", "6w", "7w", "8w", "9w",
        "1b", "2b", "3b", "4b", "5b", "6b", "7b", "8b", "9b",
        "1t", "2t", "3t", "4t", "5t", "6t", "7t", "8t", "9t",
        "东", "南", "西", "北", "中", "发", "白",
    )
'''


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def text_digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def normalized_source() -> tuple[str, str]:
    """删除一次无条件重绑前的死赋值；不改变任何可观察评分语义。"""

    source = SOURCE.read_text(encoding="utf-8")
    if source.count(DEAD_ASSIGNMENT) != 1:
        raise ValueError("待删除 canonical_codes 死赋值不是唯一一次")
    marker = DEAD_ASSIGNMENT + "    canonical_codes = (\n"
    if source.count(marker) != 1:
        raise ValueError("死赋值后不是紧邻的无条件 canonical_codes 重绑定")
    return source, source.replace(DEAD_ASSIGNMENT, "", 1)


def views() -> list[tuple[str, Any]]:
    """汇集开发、隐藏、父代覆盖、真实控制与退化负控的当前评分视图。"""

    result: list[tuple[str, Any]] = []
    document = json.loads(p32.OUT.joinpath("targets.json").read_text(encoding="utf-8"))
    development_views = []
    for target in document["targets"]:
        if target["split"] != "development":
            continue
        snapshot = json.loads(p32.snapshot_path(target).read_text(encoding="utf-8"))
        view = build_scoring_view(p34.request_from_snapshot(target, snapshot))
        development_views.append((target, view))
        result.append(("development:" + target["target_id"], view))
    hidden_document = json.loads(p35.OUT.joinpath("targets.json").read_text(encoding="utf-8"))
    for target in hidden_document["targets"]:
        snapshot = json.loads(p35.snapshot_path(target).read_text(encoding="utf-8"))
        result.append((
            "hidden:" + target["target_id"],
            build_scoring_view(p34.request_from_snapshot(target, snapshot)),
        ))
    for target in p5.prior.targets():
        result.append((
            "p5:" + target["target_id"],
            build_scoring_view(p5.exact_request(target)),
        ))
    real_windows, _ = p34.load_legacy_real_windows()
    for name, request, _origins in real_windows:
        result.append(("real:" + name, build_scoring_view(request)))
    first_target, first_view = development_views[0]
    target_key = str(first_target["intervention_action"])
    for name, value in (("baotou_false", False), ("baotou_unknown", None)):
        actions = tuple(
            replace(item, baotou_after=value) if item.action_key == target_key else item
            for item in first_view.actions
        )
        result.append(("mutation:" + name, replace(first_view, actions=actions)))
    wealth_tile = first_view.visible_state.rule_state.wealth_god
    visible = replace(
        first_view.visible_state,
        my_hand=tuple(first_view.visible_state.my_hand) + (wealth_tile,),
    )
    result.append(("mutation:three_wealth", replace(first_view, visible_state=visible)))
    return result


def run() -> None:
    """生成规范化源码，证明等价并冻结活动父代登记。"""

    if OUT.exists():
        raise SystemExit("P37 活动父代目录已存在；拒绝覆盖")
    p34_result = json.loads(P34_RESULT.read_text(encoding="utf-8"))
    p35_result = json.loads(P35_RESULT.read_text(encoding="utf-8"))
    p36_result = json.loads(P36_RESULT.read_text(encoding="utf-8"))
    if p34_result.get("decision") != "OPEN_P35_HIDDEN_ADMISSION":
        raise ValueError("P34 开发预检没有通过")
    if p35_result.get("gate_passed") is not True:
        raise ValueError("P35 隐藏机会门没有通过")
    if p36_result.get("status") != "PASS_R18_P36_RESEARCH_SAFETY":
        raise ValueError("P36 完整桌安全门没有通过")
    source, normalized = normalized_source()
    OUT.mkdir(parents=True)
    candidate_path = _project_file(_PROJECT_ROOT, OUT / "candidate.py")
    candidate_path.write_text(normalized.rstrip("\n") + "\n", encoding="utf-8")
    precheck = p33.gen.precheck_action_value_candidate(normalized)
    if precheck.get("ok") is not True:
        raise ValueError("P37 规范化源码未通过受限语法：" + repr(precheck))
    source_scorer = ActionValueScorer("r18-p37-source", source)
    normalized_scorer = ActionValueScorer("r18-p37-normalized", normalized)
    rows = []
    max_source_operations = 0
    max_normalized_operations = 0
    for label, view in views():
        source_batch = source_scorer.score(view)
        source_operations = source_scorer.last_operation_count
        normalized_batch = normalized_scorer.score(view)
        normalized_operations = normalized_scorer.last_operation_count
        equal = source_batch == normalized_batch
        if not equal:
            raise ValueError("P37 规范化行为不等价：" + label)
        if normalized_operations > source_operations:
            raise ValueError("P37 规范化增加受限操作数：" + label)
        max_source_operations = max(max_source_operations, source_operations)
        max_normalized_operations = max(max_normalized_operations, normalized_operations)
        rows.append({
            "label": label, "exact_batch_equal": equal,
            "source_operations": source_operations,
            "normalized_operations": normalized_operations,
        })
    groups = {
        prefix: sum(row["label"].startswith(prefix + ":") for row in rows)
        for prefix in ("development", "hidden", "p5", "real", "mutation")
    }
    evidence = {
        "schema": "r18-p37-two-wealth-normalization-equivalence/1",
        "source_sha256": text_digest(source),
        "normalized_sha256": text_digest(normalized),
        "normalization": (
            "删除一个 canonical_codes 赋值；下一条语句在任何读取或分支前"
            "无条件重绑同名变量，因此删除项为不可观察死赋值"
        ),
        "removed_occurrences": 1,
        "mechanism_changed": False,
        "static_precheck": precheck,
        "dynamic_views": len(rows),
        "dynamic_groups": groups,
        "all_exact_batch_equal": all(row["exact_batch_equal"] for row in rows),
        "maximum_source_operations": max_source_operations,
        "maximum_normalized_operations": max_normalized_operations,
        "operation_limit": normalized_scorer.max_operations,
        "rows": rows,
    }
    write_json(_project_file(_PROJECT_ROOT, OUT / "precheck.json"), precheck)
    write_json(_project_file(_PROJECT_ROOT, OUT / "equivalence.json"), evidence)
    registry = {
        "schema": "r18-active-research-parent/1",
        "created_at_utc": search.utc_now(),
        "parent_id": "r18-p37-two-wealth-baotou-active-parent/v1",
        "role": "overall_research_leader_and_two_wealth_specialist",
        "candidate_path": str(candidate_path),
        "candidate_sha256": digest(candidate_path),
        "evidence_identity_bridge": {
            "evaluated_candidate_sha256": p36_result["candidate_sha256"],
            "normalization_equivalence_sha256": digest(_project_file(_PROJECT_ROOT, OUT / "equivalence.json")),
            "scope": "仅删除紧邻无条件重绑前的死赋值；255个当前评分视图完整批次逐项相等",
        },
        "opportunity_capability": {
            "family": "two_wealth.piao_keeps_baotou",
            "hidden_natural_roots": p35_result["hidden_states"],
            "hidden_positive_roots": p35_result["aggregate"]["positive_states"],
            "mean_current_round_settlement_delta": p35_result["aggregate"][
                "mean_piao_minus_hu_current_round_settlement"
            ],
            "bootstrap_95": p35_result["aggregate"]["bootstrap_95"],
        },
        "table_safety": {
            "tables": p36_result["tables"],
            "natural_triggered_requests": p36_result["request_audit_counts"][
                "two_wealth_triggered"
            ],
            "stage_score_delta_mean": p36_result["overall"]["stage_score_delta_mean"],
            "bootstrap_mean_95_interval": p36_result["overall"][
                "bootstrap_mean_95_interval"
            ],
            "negative_paired_units": p36_result["overall"]["negative_units"],
        },
        "stable_control": {
            "name": "P5",
            "candidate_path": str(p32.PARENT),
            "candidate_sha256": digest(p32.PARENT),
        },
        "selection_eligible": True,
        "active_research_parent": True,
        "release_eligible": False,
        "next_required": (
            "把规范化父代接入可配置离线策略工厂，复跑正式契约/时限/发布门；"
            "同时以该父代继续生成下一个杭麻特殊机会家族"
        ),
    }
    write_json(_project_file(_PROJECT_ROOT, OUT / "active-parent.json"), registry)
    write_json(_project_file(_PROJECT_ROOT, OUT / "manifest.json"), {
        "schema": "r18-p37-two-wealth-active-parent-manifest/1",
        "source_sha256": digest(SOURCE),
        "candidate_sha256": digest(candidate_path),
        "p34_result_sha256": digest(P34_RESULT),
        "p35_result_sha256": digest(P35_RESULT),
        "p36_result_sha256": digest(P36_RESULT),
        "equivalence_sha256": digest(_project_file(_PROJECT_ROOT, OUT / "equivalence.json")),
        "active_parent_sha256": digest(_project_file(_PROJECT_ROOT, OUT / "active-parent.json")),
        "release_eligible": False,
    })
    print(json.dumps({
        "status": "P37_ACTIVE_RESEARCH_PARENT_REGISTERED",
        "candidate_sha256": registry["candidate_sha256"],
        "dynamic_views": evidence["dynamic_views"],
        "dynamic_groups": groups,
        "all_exact_batch_equal": evidence["all_exact_batch_equal"],
        "maximum_source_operations": max_source_operations,
        "maximum_normalized_operations": max_normalized_operations,
        "active_research_parent": True,
        "release_eligible": False,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("run",))
    globals()[parser.parse_args().operation]()
