"""R18 P45：合并 P8 起手七对与 P37 双财神活动父代。

P8 与 P37 都从同一个 P5 分叉。P8 已验证的庄家起手七对覆盖没有进入后续
P37 谱系。本程序只做可审计的三方补丁合并：把 P8 相对 P5 的完整覆盖块
插入 P37，并证明 P8 开发/历史隐藏能力、P8 中后段边界和 P37 全部现有行为
同时保留。完整桌安全门由下一阶段独立执行。
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
import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Iterable


HERE = Path(__file__).resolve().parent
ROUTE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15')
ROOT = _PROJECT_ROOT
for path in (_project_file(_PROJECT_ROOT, ROOT / "src"), _project_file(_PROJECT_ROOT, ROUTE / "tools"), HERE):
    sys.path.insert(0, str(path))

import r18_p8_boundary_admission as p8  # noqa: E402
import r18_p37_two_wealth_active_parent as p37  # noqa: E402
import sitin_search as search  # noqa: E402
from hangma_bot.application.audit_codec import decision_request_from_json  # noqa: E402
from hangma_bot.policy.action_value_policy import build_scoring_view  # noqa: E402
from hangma_bot.policy.action_value_seeds import ActionValueScorer  # noqa: E402


OUT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p45-integrated-positive-parent-01-20260922')
P5 = p8.PARENT
P8 = p8.CANDIDATE
P37 = p37.OUT / "candidate.py"
P8_DEVELOPMENT_RESULT = p8.DEVELOPMENT_OUT / "result.json"
P8_HIDDEN_RESULT = p8.HIDDEN_OUT / "result.json"
P8_BOUNDARY_RESULT = p8.BOUNDARY_OUT
P37_ACTIVE = p37.OUT / "active-parent.json"

P8_BLOCK_START = "    seven_value_best_key = None\n"
P8_BLOCK_END = "    reason = \"胡以动态排序层优先；未知动作严格锚定在已知最终分最低值以下\"\n"
P37_INSERT_MARKER = "    # 双财神保包tou飘反事实覆盖：父代最终 entries 之上最小新增。\n"
P8_REASON = (
    "    if seven_value_triggered:\n"
    "        reason = reason + \"；已验证庄家起手域内完整一次自摸条件期望严格胜出时选择七对路线弃牌\"\n"
)
P37_REASON_MARKER = (
    "    if piao2_triggered:\n"
    "        reason = reason + \"；双财神保包头飘反事实触发，目标财神弃牌提到父代hu最终分上方1.0\"\n"
)


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def text_digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def integrated_source() -> tuple[str, dict[str, Any]]:
    """从 P8/P5 精确差异提取覆盖块，并插入 P37 的父代最终分之后。"""

    p5_source = P5.read_text(encoding="utf-8")
    p8_source = P8.read_text(encoding="utf-8")
    p37_source = P37.read_text(encoding="utf-8")
    if p5_source.count(P8_BLOCK_START) != 0 or p37_source.count(P8_BLOCK_START) != 0:
        raise ValueError("P5/P37 已含 P8 覆盖，拒绝重复合并")
    if p8_source.count(P8_BLOCK_START) != 1 or p8_source.count(P8_BLOCK_END) != 1:
        raise ValueError("P8 覆盖块边界不唯一")
    start = p8_source.index(P8_BLOCK_START)
    end = p8_source.index(P8_BLOCK_END, start)
    overlay = p8_source[start:end]
    if p37_source.count(P37_INSERT_MARKER) != 1:
        raise ValueError("P37 双财神插入点不唯一")
    if p37_source.count(P37_REASON_MARKER) != 1:
        raise ValueError("P37 reason 插入点不唯一")
    merged = p37_source.replace(P37_INSERT_MARKER, overlay + P37_INSERT_MARKER, 1)
    merged = merged.replace(P37_REASON_MARKER, P8_REASON + P37_REASON_MARKER, 1)
    old_doc = (
        '"""R18 多财神飘覆盖 + 补杠严格支配覆盖 + '
        '双财神保包头飘反事实覆盖；稳定 V2 是完整回退。"""'
    )
    new_doc = (
        '"""R18 多财神飘、补杠支配、庄家起手七对与双财神保包头覆盖；'
        '稳定 V2 是完整回退。"""'
    )
    if merged.count(old_doc) != 1:
        raise ValueError("P37 模块说明漂移")
    merged = merged.replace(old_doc, new_doc, 1)
    return merged, {
        "p5_sha256": text_digest(p5_source),
        "p8_sha256": text_digest(p8_source),
        "p37_sha256": text_digest(p37_source),
        "p8_overlay_sha256": text_digest(overlay),
        "p8_overlay_lines": len(overlay.splitlines()),
        "merge_rule": (
            "从P8中提取seven_value_best_key至reason前的唯一新增块，插入P37双财神块前；"
            "只在seven_value_triggered时追加P8 reason"
        ),
    }


def score_map(batch: Any) -> dict[str, float]:
    return {item.action_key: item.score for item in batch.entries}


def top_key(batch: Any) -> str:
    return sorted(batch.entries, key=lambda item: (-item.score, item.action_key))[0].action_key


def triggered(batch: Any, key: str) -> list[str]:
    return [
        item.action_key for item in batch.entries
        if isinstance(item.trace.get(key), dict)
        and item.trace[key].get("triggered") is True
    ]


def p8_views() -> Iterable[tuple[str, str, Any]]:
    for split in ("development", "hidden"):
        cases, metadata = p8.load_split(split)
        for case, meta in zip(cases, metadata):
            yield split + ":" + case.case_id, str(meta["decision_type"]), build_scoring_view(case.request)


def boundary_views() -> Iterable[tuple[str, Any]]:
    document = json.loads(p8.BORDER_DATASET.read_text(encoding="utf-8"))
    if document.get("status") != "COMPLETE" or len(document.get("rows") or []) != 29:
        raise ValueError("P8自然边界数据集不完整")
    for index, row in enumerate(document["rows"], 1):
        request = decision_request_from_json(row["request"])
        yield "boundary:{0:02d}".format(index), build_scoring_view(request)


def require_prior_evidence() -> None:
    checks = (
        (P8_DEVELOPMENT_RESULT, "PASS_P8_DEVELOPMENT"),
        (P8_HIDDEN_RESULT, "PASS_P8_HISTORICAL_HIDDEN_REGRESSION"),
        (P8_BOUNDARY_RESULT, "PASS_P8_NATURAL_BOUNDARY"),
    )
    for path, status in checks:
        row = json.loads(path.read_text(encoding="utf-8"))
        if row.get("status") != status:
            raise ValueError(path.name + " 未通过：" + str(row.get("status")))
    active = json.loads(P37_ACTIVE.read_text(encoding="utf-8"))
    if active.get("active_research_parent") is not True or active.get("candidate_sha256") != digest(P37):
        raise ValueError("P37 当前身份不是活动研究父代")


def run() -> None:
    """生成合并候选并执行三条谱系能力不回归门。"""

    if OUT.exists():
        raise SystemExit("P45目录已存在；拒绝覆盖")
    require_prior_evidence()
    merged, merge_identity = integrated_source()
    OUT.mkdir(parents=True)
    candidate = _project_file(_PROJECT_ROOT, OUT / "candidate.py")
    candidate.write_text(merged.rstrip("\n") + "\n", encoding="utf-8")
    precheck = p37.p33.gen.precheck_action_value_candidate(merged)
    if precheck.get("ok") is not True:
        raise ValueError("P45合并候选未通过受限语法：" + repr(precheck))

    integrated = ActionValueScorer("r18-p45-integrated", merged)
    p8_scorer = ActionValueScorer("r18-p45-p8", P8.read_text(encoding="utf-8"))
    p37_scorer = ActionValueScorer("r18-p45-p37", P37.read_text(encoding="utf-8"))
    problems = []
    rows = []
    max_operations = 0

    for label, dtype, view in p8_views():
        combined = integrated.score(view)
        operations = integrated.last_operation_count
        reference = p8_scorer.score(view)
        max_operations = max(max_operations, operations)
        same_scores = score_map(combined) == score_map(reference)
        same_top = top_key(combined) == top_key(reference)
        seven = triggered(combined, "r18_seven_pairs_value_overlay")
        two = triggered(combined, "two_wealth_piao_keeps_baotou_cf")
        expected_seven = dtype == "seven_pairs_tradeoff"
        if not same_scores or not same_top:
            problems.append(label + ":p8_behavior_regression")
        if bool(seven) != expected_seven:
            problems.append(label + ":p8_trigger_mismatch")
        if two:
            problems.append(label + ":orthogonal_overlap_with_two_wealth")
        rows.append({
            "label": label, "group": "p8_" + dtype,
            "same_scores_as_p8": same_scores, "same_top_as_p8": same_top,
            "seven_trigger_keys": seven, "two_wealth_trigger_keys": two,
            "operations": operations,
        })

    for label, view in boundary_views():
        combined = integrated.score(view)
        operations = integrated.last_operation_count
        reference = p37_scorer.score(view)
        max_operations = max(max_operations, operations)
        same_scores = score_map(combined) == score_map(reference)
        same_top = top_key(combined) == top_key(reference)
        seven = triggered(combined, "r18_seven_pairs_value_overlay")
        if not same_scores or not same_top or seven:
            problems.append(label + ":p8_boundary_regression")
        rows.append({
            "label": label, "group": "p8_natural_boundary",
            "same_scores_as_p37": same_scores, "same_top_as_p37": same_top,
            "seven_trigger_keys": seven, "operations": operations,
        })

    for label, view in p37.views():
        combined = integrated.score(view)
        operations = integrated.last_operation_count
        reference = p37_scorer.score(view)
        max_operations = max(max_operations, operations)
        exact = combined == reference
        seven = triggered(combined, "r18_seven_pairs_value_overlay")
        if not exact or seven:
            problems.append("p37:" + label + ":behavior_regression")
        rows.append({
            "label": "p37:" + label, "group": "p37_current_views",
            "exact_batch_equal": exact, "seven_trigger_keys": seven,
            "operations": operations,
        })

    groups = dict(sorted(Counter(row["group"] for row in rows).items()))
    checks = {
        "prior_p8_and_p37_evidence_passed": True,
        "static_precheck_passed": precheck.get("ok") is True,
        "p8_development_and_hidden_score_behavior_preserved": not any(
            "p8_behavior_regression" in item for item in problems
        ),
        "p8_trigger_scope_preserved": not any(
            "p8_trigger_mismatch" in item for item in problems
        ),
        "p8_natural_boundary_falls_back_to_p37": not any(
            "p8_boundary_regression" in item for item in problems
        ),
        "p37_current_behavior_exactly_preserved": not any(
            "behavior_regression" in item and item.startswith("p37:") for item in problems
        ),
        "p8_and_two_wealth_overlays_do_not_overlap": not any(
            "orthogonal_overlap" in item for item in problems
        ),
        "operation_limit_respected": max_operations <= 100_000,
        "problems_zero": not problems,
    }
    result = {
        "schema": "r18-p45-integrated-positive-parent-preflight/1",
        "status": "PASS_P45_INTEGRATED_PREFLIGHT" if all(checks.values()) else "FAIL_P45_INTEGRATED_PREFLIGHT",
        "created_at_utc": search.utc_now(),
        "candidate_sha256": digest(candidate),
        "merge_identity": merge_identity,
        "source_evidence": {
            "p8_development_result_sha256": digest(P8_DEVELOPMENT_RESULT),
            "p8_hidden_result_sha256": digest(P8_HIDDEN_RESULT),
            "p8_boundary_result_sha256": digest(P8_BOUNDARY_RESULT),
            "p37_active_parent_sha256": digest(P37_ACTIVE),
        },
        "dynamic_views": len(rows),
        "dynamic_groups": groups,
        "maximum_operations": max_operations,
        "operation_limit": integrated.max_operations,
        "checks": checks,
        "problems": problems,
        "rows": rows,
        "decision": "OPEN_P46_FRESH_TABLE_SAFETY" if all(checks.values()) else "REJECT_P45_MERGE",
        "selection_eligible": False,
        "active_research_parent": False,
        "release_eligible": False,
    }
    write_json(_project_file(_PROJECT_ROOT, OUT / "precheck.json"), precheck)
    write_json(_project_file(_PROJECT_ROOT, OUT / "result.json"), result)
    write_json(_project_file(_PROJECT_ROOT, OUT / "manifest.json"), {
        "schema": "r18-p45-integrated-positive-parent-manifest/1",
        "candidate_sha256": digest(candidate),
        "p5_sha256": digest(P5), "p8_sha256": digest(P8), "p37_sha256": digest(P37),
        "result_sha256": digest(_project_file(_PROJECT_ROOT, OUT / "result.json")),
        "merge_identity": merge_identity,
        "next_required": "全新完整桌相对P37非劣，并审计P8与P37各自自然触发",
        "release_eligible": False,
    })
    print(json.dumps({
        "status": result["status"], "candidate_sha256": result["candidate_sha256"],
        "dynamic_views": result["dynamic_views"], "dynamic_groups": groups,
        "maximum_operations": max_operations, "checks": checks,
        "problems": problems, "decision": result["decision"],
    }, ensure_ascii=False, indent=2))
    if result["status"] != "PASS_P45_INTEGRATED_PREFLIGHT":
        raise RuntimeError("P45谱系合并预检失败")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("run",))
    globals()[parser.parse_args().operation]()
