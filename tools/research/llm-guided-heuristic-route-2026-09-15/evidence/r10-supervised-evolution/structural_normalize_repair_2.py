"""归一化第二结构批次修复回复中的可机械确认格式问题。"""
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

import hashlib
import json
import sys
from pathlib import Path


HERE = Path(__file__).resolve().parent
ROUTE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15')
ADMISSION = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/v4-impl/r9-admission')
for path in (_project_file(_PROJECT_ROOT, ROUTE / "tools"), _project_file(_PROJECT_ROOT, ADMISSION / "p25-dev-cards"), HERE):
    sys.path.insert(0, str(path))

import sitin_generate as gen  # noqa: E402
import structural_author_batch as first  # noqa: E402


BATCH = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/structural-search-02-20260921')
TASKS = ("T1", "T2", "T4")
MECHANISMS = {
    "T1": {
        "trigger": "单个合法动作具有至少两个可用的后续分支见证；不足时精确保留S3父代分数。",
        "changed_branches": "只在同一动作内部比较followup_branches的相对向听、跨度、离散度和有界余量；不要求同窗存在多个可比分支动作。",
        "expected_direction": "在保留S3父代FBV种子的基础上，给分支相对质量更高且见证充分的动作增加有界边际。",
        "counterexample": "后续分支不足、字段未知或证据不满足门槛时，RFM必须为零且结果逐分回到S3父代。",
    },
    "T2": {
        "trigger": "动作存在可用followup_branches；是否已有直接牌效事实决定收缩或补充分支。",
        "changed_branches": "直接牌效可比时有界收缩S3父代后续项；直接牌效缺失时按有界support_remaining补充，S3父代常数保持不动。",
        "expected_direction": "减少直接牌效与后续价值重复计分，并使缺少直接牌效但有可靠后续见证的动作获得有限补偿。",
        "counterexample": "参数全零时收缩与补充都必须为零，逐分等价于S3父代；缺少有效分支事实时不得虚构价值。",
    },
    "T4": {
        "trigger": "动作存在可用followup_branches并能确定最佳combined_shanten。",
        "changed_branches": "固定恢复层逐分重建S3父代FBV；非零配置仅增加由最佳分支序数决定的亚单位破平层。",
        "expected_direction": "保持S3父代主排序，只在主分接近时偏向后续分支序数更优的动作。",
        "counterexample": "FB_TIE_STEP为零或没有有效分支时破平层必须为零；不得跨越一分以上的主排序差。",
    },
}


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def normalize_code(task: str, source: str) -> tuple[str, str]:
    """只删除T1回复末尾可机械识别的孤立右花括号。"""
    if task != "T1":
        return source, "可执行源码逐字节保持不变"
    lines = source.splitlines()
    if not lines or lines[-1] != "}":
        raise ValueError("T1末尾不再是预期的孤立右花括号；拒绝猜测修复")
    normalized = "\n".join(lines[:-1]).rstrip("\n") + "\n"
    return normalized, "仅删除源码末尾一个孤立的`}`行"


def main() -> None:
    rows = []
    for task in TASKS:
        repair = _project_file(_PROJECT_ROOT, BATCH / "generations" / task / "repair")
        target = repair / "normalized"
        if target.exists():
            raise SystemExit(f"归一化产物已存在，拒绝覆盖：{task}")
        source_path = repair / "candidate.py"
        source = source_path.read_text(encoding="utf-8")
        code, change = normalize_code(task, source)
        target.mkdir(parents=True)
        (target / "candidate.py").write_text(code, encoding="utf-8")
        write_json(target / "mechanism.json", MECHANISMS[task])

        precheck = gen.precheck_action_value_candidate(code)
        try:
            space = first.validate_space(code)
        except (SyntaxError, ValueError) as exc:
            space = {"ok": False, "problems": [f"参数空间异常：{type(exc).__name__}: {exc}"]}
        write_json(target / "precheck.json", precheck)
        write_json(target / "structure-space.json", space)
        source_sha = sha256_text(source)
        output_sha = sha256_text(code)
        executable_changed = source_sha != output_sha
        record = {
            "schema": "r10-structural-repair-normalization/1",
            "task": task,
            "source": str(source_path.relative_to(BATCH)),
            "source_sha256": source_sha,
            "candidate_sha256": output_sha,
            "executable_changed": executable_changed,
            "executable_change": change,
            "mechanism_normalization": (
                "把修复回复thought、源码docstring与trace中已有的机制说明映射为标准四字段；"
                "不据此改写任何可执行表达式或参数。"
            ),
            "static_precheck": precheck.get("ok") is True,
            "structure_space": space.get("ok") is True,
            "accepted_for_behavior_preflight": (
                precheck.get("ok") is True and space.get("ok") is True
            ),
            "problems": list(precheck.get("problems") or [])
                        + list(space.get("problems") or []),
        }
        if task != "T1" and executable_changed:
            raise AssertionError(f"{task}不应发生可执行源码变化")
        write_json(target / "normalization.json", record)
        rows.append(record)

    summary = {
        "schema": "r10-structural-repair-normalization-summary/1",
        "policy": "只纠正可机械确认的输出格式；不进行第二次算法修复或效果调参",
        "tasks": rows,
        "accepted": [row["task"] for row in rows
                     if row["accepted_for_behavior_preflight"]],
        "closed": [row["task"] for row in rows
                   if not row["accepted_for_behavior_preflight"]],
    }
    write_json(_project_file(_PROJECT_ROOT, BATCH / "repair-normalization-summary.json"), summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
