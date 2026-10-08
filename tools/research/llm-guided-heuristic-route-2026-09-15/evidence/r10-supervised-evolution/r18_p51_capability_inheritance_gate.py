"""R18 P51：对所有后继候选强制执行累计能力继承门。"""

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

import r18_p45_integrated_positive_parent as p45  # noqa: E402
import r18_p47_integrated_parent_registration as p47  # noqa: E402
from hangma_bot.policy.action_value_seeds import ActionValueScorer  # noqa: E402


OUT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p51-capability-inheritance-gate-01-20260922')
ARCHIVE5 = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-opportunity-archive-05-20260922')
CONTRACT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-opportunity-archive-05-20260922/inheritance-contract.json')
ACTIVE_PARENT = p45.OUT / "candidate.py"
MISSING_SEVEN_CONTROL = p45.P37
MISSING_TWO_WEALTH_CONTROL = p45.P8
OPERATION_LIMIT = 100_000


def digest(path: Path) -> str:
    """返回文件 SHA-256。"""

    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: Any) -> None:
    """写入稳定 JSON。"""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def top_key(batch: Any) -> str:
    """按合同排序读取首选动作。"""

    return sorted(batch.entries, key=lambda item: (-item.score, item.action_key))[0].action_key


def locked_views() -> Iterable[tuple[str, str, Any]]:
    """枚举已准入能力、反例边界和既有父代行为的冻结视图。"""

    for label, decision_type, view in p45.p8_views():
        yield "p8_" + decision_type, label, view
    for label, view in p45.boundary_views():
        yield "p8_natural_boundary", label, view
    for label, view in p45.p37.views():
        yield "p37_current_views", "p37:" + label, view


def evaluate_candidate(path: Path) -> dict[str, Any]:
    """相对活动父代逐视图核对完整批次、首选和工作量。"""

    source = path.read_text(encoding="utf-8")
    precheck = p45.p37.p33.gen.precheck_action_value_candidate(source)
    parent_source = ACTIVE_PARENT.read_text(encoding="utf-8")
    parent = ActionValueScorer("r18-p51-parent", parent_source)
    candidate = ActionValueScorer("r18-p51-candidate", source)
    rows = []
    failed_groups = Counter()
    maximum_operations = 0
    for group, label, view in locked_views():
        expected = parent.score(view)
        actual = candidate.score(view)
        operations = candidate.last_operation_count
        maximum_operations = max(maximum_operations, operations)
        exact = actual == expected
        same_top = top_key(actual) == top_key(expected)
        if not exact:
            failed_groups[group] += 1
        rows.append({
            "group": group,
            "label": label,
            "exact_batch_equal": exact,
            "same_top_action": same_top,
            "candidate_operations": operations,
        })
    exact_count = sum(row["exact_batch_equal"] for row in rows)
    top_count = sum(row["same_top_action"] for row in rows)
    return {
        "candidate_path": str(path),
        "candidate_sha256": digest(path),
        "active_parent_sha256": digest(ACTIVE_PARENT),
        "views": len(rows),
        "exact_batch_equal_views": exact_count,
        "same_top_action_views": top_count,
        "failed_views": len(rows) - exact_count,
        "failed_groups": dict(sorted(failed_groups.items())),
        "maximum_operations": maximum_operations,
        "operation_limit": OPERATION_LIMIT,
        "static_precheck_passed": precheck.get("ok") is True,
        "gate_passed": (
            precheck.get("ok") is True
            and exact_count == len(rows)
            and top_count == len(rows)
            and maximum_operations <= OPERATION_LIMIT
        ),
        "rows": rows,
    }


def validate() -> None:
    """验证活动父代通过，并证明两个历史缺能力父代会被拒绝。"""

    if OUT.exists():
        raise SystemExit("P51 目录已存在；拒绝覆盖")
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    if contract.get("active_parent_sha256") != digest(ACTIVE_PARENT):
        raise ValueError("第五版继承合同与活动父代漂移")
    expected_views = int(
        contract["required_suites"]["capability_and_boundary_views"]["views"]
    )
    active = evaluate_candidate(ACTIVE_PARENT)
    missing_seven = evaluate_candidate(MISSING_SEVEN_CONTROL)
    missing_two = evaluate_candidate(MISSING_TWO_WEALTH_CONTROL)
    checks = {
        "expected_locked_view_count": active["views"] == expected_views == 380,
        "active_parent_passes": active["gate_passed"] is True,
        "missing_seven_control_rejected": (
            missing_seven["gate_passed"] is False
            and missing_seven["failed_groups"].get("p8_seven_pairs_tradeoff", 0) > 0
        ),
        "missing_two_wealth_control_rejected": (
            missing_two["gate_passed"] is False
            and missing_two["failed_groups"].get("p37_current_views", 0) > 0
        ),
        "all_candidates_statically_valid": all(
            row["static_precheck_passed"] for row in (active, missing_seven, missing_two)
        ),
    }
    passed = all(checks.values())
    OUT.mkdir(parents=True)
    for name, row in (
        ("active-parent", active),
        ("missing-seven-control", missing_seven),
        ("missing-two-wealth-control", missing_two),
    ):
        write_json(_project_file(_PROJECT_ROOT, OUT / (name + ".json")), row)
    result = {
        "schema": "r18-p51-capability-inheritance-gate-result/1",
        "status": "PASS_P51_INHERITANCE_GATE" if passed else "FAIL_P51_INHERITANCE_GATE",
        "contract_sha256": digest(CONTRACT),
        "active_parent": {
            key: value for key, value in active.items() if key != "rows"
        },
        "negative_controls": {
            "missing_seven": {
                key: value for key, value in missing_seven.items() if key != "rows"
            },
            "missing_two_wealth": {
                key: value for key, value in missing_two.items() if key != "rows"
            },
        },
        "checks": checks,
        "successor_policy": contract["default_successor_rule"],
        "next": (
            "所有新候选在开发题评分前先调用本门；默认零豁免"
            if passed else "停止新作者调用并修复继承视图、活动父代或负控判别"
        ),
        "release_eligible": False,
    }
    write_json(_project_file(_PROJECT_ROOT, OUT / "result.json"), result)
    write_json(_project_file(_PROJECT_ROOT, OUT / "manifest.json"), {
        "schema": "r18-p51-capability-inheritance-gate-manifest/1",
        "script_sha256": digest(Path(__file__)),
        "contract_sha256": digest(CONTRACT),
        "active_parent_sha256": digest(ACTIVE_PARENT),
        "missing_seven_control_sha256": digest(MISSING_SEVEN_CONTROL),
        "missing_two_wealth_control_sha256": digest(MISSING_TWO_WEALTH_CONTROL),
        "result_sha256": digest(_project_file(_PROJECT_ROOT, OUT / "result.json")),
        "release_eligible": False,
    })
    print(json.dumps({
        "status": result["status"],
        "active_parent": result["active_parent"],
        "negative_controls": result["negative_controls"],
        "checks": checks,
        "next": result["next"],
    }, ensure_ascii=False, indent=2))
    if not passed:
        raise RuntimeError("P51 强制能力继承门未通过")


def check(candidate: Path) -> None:
    """供后续作者批次在打开新目标标签前检查一个候选。"""

    result = evaluate_candidate(candidate.resolve())
    print(json.dumps({key: value for key, value in result.items() if key != "rows"}, ensure_ascii=False, indent=2))
    if not result["gate_passed"]:
        raise RuntimeError("候选未完整继承活动父代锁定能力")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("validate", "check"))
    parser.add_argument("--candidate", type=Path)
    args = parser.parse_args()
    if args.operation == "check":
        if args.candidate is None:
            parser.error("check 需要 --candidate")
        check(args.candidate)
    else:
        validate()
