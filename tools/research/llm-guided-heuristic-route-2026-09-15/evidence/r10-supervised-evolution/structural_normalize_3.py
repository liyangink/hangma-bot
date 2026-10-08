"""机械归一化第三结构批次候选，不改变算法、参数值或可执行语义。"""
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

import ast
import json
import re
import sys
from pathlib import Path


HERE = Path(__file__).resolve().parent
ROUTE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15')
for path in (_project_file(_PROJECT_ROOT, ROUTE / "tools"), HERE):
    sys.path.insert(0, str(path))

import sitin_generate as gen  # noqa: E402
import structural_author_batch as first  # noqa: E402
import structural_author_batch_3 as batch3  # noqa: E402


BATCH = batch3.BATCH
TASKS = ("C1", "C2")
SPACE_PREFIX = "# STRUCTURE_SPACE_JSON: "
ASSIGNMENT = re.compile(r"^(?P<indent>\s*)(?P<name>[A-Za-z_]\w*)\[(?P<key>.+)\]\s*=\s*(?P<value>.+)$")


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def normalized_space(line: str) -> tuple[str, dict]:
    if not line.startswith(SPACE_PREFIX):
        raise ValueError("首行不是STRUCTURE_SPACE_JSON")
    space = json.loads(line[len(SPACE_PREFIX):])
    raw_parameters = space.get("parameters")
    if not isinstance(raw_parameters, list) or not 1 <= len(raw_parameters) <= 4:
        raise ValueError("只允许把模型误交的1—4项parameters列表归一化")
    parameters = {}
    for item in raw_parameters:
        if not isinstance(item, dict) or set(item) - {"name", "grid", "zero"}:
            raise ValueError("parameters列表项结构超出机械归一化范围")
        name = item.get("name")
        grid = item.get("grid")
        if not isinstance(name, str) or not isinstance(grid, list) or name in parameters:
            raise ValueError("parameters列表项不可唯一映射")
        parameters[name] = grid
        if "zero" in item and float(item["zero"]) != float(space["zero_effect"][name]):
            raise ValueError("parameters.zero与zero_effect冲突")
    changed = dict(space)
    changed["parameters"] = parameters
    return SPACE_PREFIX + json.dumps(
        changed, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ), {"before": raw_parameters, "after": parameters}


def normalize_assignment(fragment: str) -> tuple[str, dict | None]:
    match = ASSIGNMENT.match(fragment)
    if match is None:
        return fragment, None
    name = match.group("name")
    key = match.group("key")
    value = match.group("value")
    replacement = f"{match.group('indent')}{name}.update({{{key}: {value}}})"
    return replacement, {
        "target": name,
        "key_source": key,
        "value_source": value,
        "equivalence": "dict下标赋值改为单键dict.update；目标在源码中均由字典字面量创建",
    }


def normalize(code: str) -> tuple[str, list[dict], dict]:
    lines = code.splitlines()
    lines[0], space_change = normalized_space(lines[0])
    changes = []
    output = [lines[0]]
    for line_no, line in enumerate(lines[1:], start=2):
        # 模型把两条简单字典赋值放在同一行；先按分号拆开，再逐条等价改写。
        fragments = line.split("; ")
        if len(fragments) > 1:
            indent = line[:len(line) - len(line.lstrip())]
            fragments = [fragments[0]] + [indent + item.lstrip() for item in fragments[1:]]
        converted = []
        for fragment in fragments:
            replacement, detail = normalize_assignment(fragment)
            converted.append(replacement)
            if detail is not None:
                changes.append({"line": line_no, **detail})
        output.extend(converted)
    result = "\n".join(output).rstrip("\n") + "\n"
    return result, changes, space_change


def subscript_assignment_count(code: str) -> int:
    tree = ast.parse(code)
    count = 0
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Subscript):
                count += 1
    return count


def main() -> None:
    rows = []
    for task_id in TASKS:
        source_path = BATCH / f"generations/{task_id}/repair/candidate.py"
        target = BATCH / f"generations/{task_id}/repair/normalized"
        if target.exists():
            raise SystemExit(f"归一化目录已存在：{task_id}")
        source = source_path.read_text(encoding="utf-8")
        before_count = subscript_assignment_count(source)
        normalized, changes, space_change = normalize(source)
        after_count = subscript_assignment_count(normalized)
        if before_count != len(changes) or after_count != 0:
            raise ValueError(
                f"{task_id}下标赋值归一化不闭合：before={before_count}, changes={len(changes)}, after={after_count}"
            )
        precheck = gen.precheck_action_value_candidate(normalized)
        space = first.validate_space(normalized)
        target.mkdir(parents=True)
        (target / "candidate.py").write_text(normalized, encoding="utf-8")
        write_json(target / "normalization.json", {
            "schema": "r10-structural-normalization/3",
            "task": task_id,
            "source": str(source_path),
            "source_sha256": first.sha256_text(source),
            "normalized_sha256": first.sha256_text(normalized),
            "structure_space_change": space_change,
            "executable_rewrites": changes,
            "rewrite_count": len(changes),
            "semantic_scope": "只改字典赋值语法；参数域只改注释中的等价JSON表示",
            "precheck": precheck,
            "structure_space": space,
        })
        rows.append({
            "task": task_id,
            "source_sha256": first.sha256_text(source),
            "normalized_sha256": first.sha256_text(normalized),
            "rewrite_count": len(changes),
            "static_precheck": precheck.get("ok"),
            "structure_space": space.get("ok"),
            "accepted": precheck.get("ok") is True and space.get("ok") is True,
            "problems": list(precheck.get("problems") or []) + list(space.get("problems") or []),
        })
    write_json(BATCH / "normalization-summary.json", {
        "schema": "r10-structural-normalization-summary/3",
        "tasks": rows,
        "accepted": [row["task"] for row in rows if row["accepted"]],
        "closed": [row["task"] for row in rows if not row["accepted"]],
        "model_calls": 0,
        "effect_evaluation_started": False,
    })
    print(json.dumps({"status": "NORMALIZED", "tasks": rows}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
