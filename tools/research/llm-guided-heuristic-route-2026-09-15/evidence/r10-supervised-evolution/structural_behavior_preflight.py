"""R10 第一结构批次：在既有真实观察上装配六配置并做零成本行为预检。"""
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
import re
import sys
from collections import Counter
from pathlib import Path


HERE = Path(__file__).resolve().parent
ROUTE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15')
BATCH = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/structural-search-01-20260921')
for path in (_project_file(_PROJECT_ROOT, ROUTE / "tools"), HERE, _project_file(_PROJECT_ROOT, ROUTE / "evidence/v4-impl/r9-gate2/run")):
    sys.path.insert(0, str(path))

import sitin_real_behavior as behavior  # noqa: E402
import wealth_branch_probe as helper  # noqa: E402
from hangma_bot.policy.action_value import batch_to_ranked_candidates  # noqa: E402
from hangma_bot.policy.action_value_executor import ActionValueExecutor  # noqa: E402


SOURCES = {
    "S1": _project_file(_PROJECT_ROOT, BATCH / "generations/S1/normalized/candidate.py"),
    "S2": _project_file(_PROJECT_ROOT, BATCH / "generations/S2/normalized/candidate.py"),
    "S3": _project_file(_PROJECT_ROOT, BATCH / "generations/S3/normalized/candidate.py"),
    "S4": _project_file(_PROJECT_ROOT, BATCH / "generations/S4/candidate.py"),
}
BASES = {
    "S1": _project_file(_PROJECT_ROOT, HERE / (
        "comparable-shape-20260920/comparable-shape-terra-max/run/iterations/"
        "iter-01/generation/candidate.py"
    )),
    "S2": _project_file(_PROJECT_ROOT, HERE / "v2-parent-revalidation-20260920/parent/generation/candidate.py"),
    "S3": _project_file(_PROJECT_ROOT, HERE / "v2-parent-revalidation-20260920/parent/generation/candidate.py"),
    "S4": _project_file(_PROJECT_ROOT, HERE / "v2-parent-revalidation-20260920/parent/generation/candidate.py"),
}
SPACE_RE = re.compile(r"^# STRUCTURE_SPACE_JSON: (\{.*\})\s*$", re.MULTILINE)
NUMBER_RE = r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?"


def digest(value: object) -> str:
    data = json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_space(source: str) -> dict:
    match = SPACE_RE.search(source)
    if match is None:
        raise ValueError("缺 STRUCTURE_SPACE_JSON")
    return json.loads(match.group(1))


def materialize(source: str, config: dict, config_id: str) -> str:
    """只替换已声明模块数值常数，并以注释绑定活动配置身份。"""
    result = source
    for name, value in config.items():
        pattern = re.compile(rf"^{re.escape(name)}\s*=\s*{NUMBER_RE}\s*$", re.MULTILINE)
        result, count = pattern.subn(f"{name} = {json.dumps(value)}", result)
        if count != 1:
            raise ValueError(f"{name} 模块赋值匹配数={count}")
    active = "# ACTIVE_CONFIG_JSON: " + json.dumps(
        {"config_id": config_id, "values": config}, ensure_ascii=False,
        sort_keys=True, separators=(",", ":"))
    first, rest = result.split("\n", 1)
    return first + "\n" + active + "\n" + rest


def load_real_views() -> tuple[list, dict]:
    """读取所有冻结真实窗口，按 candidate_view 摘要去重并重建 ScoringView。"""
    records = sorted(HERE.glob("**/windows/*.json"))
    unique = {}
    provenance = Counter()
    for path in records:
        if BATCH in path.parents:
            continue
        raw = json.loads(path.read_text(encoding="utf-8"))
        if set(raw) != {"schema", "request", "request_sha256", "projection",
                        "candidate_view_sha256"}:
            continue
        if behavior.digest(raw["request"]) != raw["request_sha256"]:
            raise ValueError(f"请求摘要不一致：{path}")
        request = helper.decision_request_from_json(raw["request"])
        view = helper.build_scoring_view(request)
        key = behavior.digest(view.candidate_view())
        if key != raw["candidate_view_sha256"]:
            raise ValueError(f"投影摘要不一致：{path}")
        unique.setdefault(key, view)
        provenance[path.parent.parent.name] += 1
    return [unique[key] for key in sorted(unique)], {
        "record_files": len(records),
        "unique_real_views": len(unique),
        "source_directories": dict(sorted(provenance.items())),
    }


def reading(executor: ActionValueExecutor, view) -> dict:
    batch = executor.score(view)
    ranked = batch_to_ranked_candidates(batch, view.actions)
    return {
        "status": batch.status,
        "reason": batch.reason,
        "preferred": ranked[0].action_key if ranked else None,
        "scores": {entry.action_key: entry.score for entry in batch.entries},
        "operations": executor.last_operation_count,
    }


def same_scores(left: dict, right: dict) -> bool:
    """零效应数学等价只比较状态和动作分；reason 是允许变化的诊断文案。"""
    return left["status"] == right["status"] and left["scores"] == right["scores"]


def main() -> None:
    out = _project_file(_PROJECT_ROOT, BATCH / "behavior-preflight-v2")
    if out.exists():
        raise SystemExit("行为预检目录已存在；不得覆盖")
    out.mkdir(parents=True)
    write_json(_project_file(_PROJECT_ROOT, BATCH / "behavior-preflight/closure-v1.json"), {
        "schema": "r10-structural-behavior-preflight-closure/1",
        "status": "SUPERSEDED_MEASUREMENT_BUG",
        "problem": "v1 的 same_scores 把允许变化的 ScoreBatch.reason 诊断文案纳入逐分等价，"
                   "导致 S2/S4 即使动作分完全相同也被记 changed_scores。",
        "correction": "v2 只比较 status 与每动作 score；reason 变化单独报告。",
        "effect_tables": 0,
    })
    views, corpus = load_real_views()
    if len(views) < 100:
        raise SystemExit("真实观察不足 100，拒绝行为预检")
    write_json(out / "corpus.json", corpus | {
        "selection_eligible": False,
        "effect_tables": 0,
        "purpose": "既有真实观察的生成端行为与退化检查；不作效果样本",
    })
    task_rows = []
    config_manifest = []
    for task_id in sorted(SOURCES):
        source = SOURCES[task_id].read_text(encoding="utf-8")
        base_source = BASES[task_id].read_text(encoding="utf-8")
        space = load_space(source)
        base_executor = ActionValueExecutor(base_source, name=task_id + "-base")
        base_readings = [reading(base_executor, view) for view in views]
        zero = space["zero_effect"]
        rows = []
        preference_signatures = Counter()
        score_signatures = Counter()
        any_preference_change = False
        default_index = None
        zero_index = None
        for index, config in enumerate(space["configs"]):
            config_id = f"{task_id.lower()}-cfg-{index:02d}"
            candidate = materialize(source, config, config_id)
            target = out / "configurations" / config_id
            target.mkdir(parents=True)
            (target / "candidate.py").write_text(candidate.rstrip("\n") + "\n", encoding="utf-8")
            executor = ActionValueExecutor(candidate, name=config_id)
            failures = []
            current = []
            for view_index, view in enumerate(views):
                try:
                    current.append(reading(executor, view))
                except BaseException as exc:  # WorkloadExceeded 继承 BaseException
                    failures.append({"view_index": view_index, "type": type(exc).__name__,
                                     "message": str(exc)})
                    current.append({"status": "FAILED", "reason": type(exc).__name__,
                                    "preferred": None, "scores": {}, "operations": None})
            preference = [item["status"] + ":" + str(item["preferred"]) for item in current]
            scores = [{"status": item["status"], "reason": item["reason"],
                       "scores": item["scores"]} for item in current]
            preference_sha = digest(preference)
            scores_sha = digest(scores)
            preference_signatures[preference_sha] += 1
            score_signatures[scores_sha] += 1
            changed_preferred = sum(
                item["preferred"] != base["preferred"] or item["status"] != base["status"]
                for item, base in zip(current, base_readings))
            changed_scores = sum(not same_scores(item, base)
                                 for item, base in zip(current, base_readings))
            changed_reasons = sum(item["reason"] != base["reason"]
                                  for item, base in zip(current, base_readings))
            any_preference_change = any_preference_change or changed_preferred > 0
            is_zero = all(float(config[name]) == float(zero[name]) for name in zero)
            if is_zero:
                zero_index = index
            defaults = {
                name: value for name, value in helper_constants(source).items()
                if name in space["parameters"]
            }
            is_default = all(float(config[name]) == float(defaults[name]) for name in defaults)
            if is_default:
                default_index = index
            row = {
                "config_id": config_id,
                "index": index,
                "values": config,
                "source_sha256": hashlib.sha256(candidate.encode("utf-8")).hexdigest(),
                "is_zero_effect": is_zero,
                "is_author_default": is_default,
                "views": len(views),
                "failures": failures,
                "changed_preferred_vs_base": changed_preferred,
                "changed_scores_vs_base": changed_scores,
                "changed_reasons_vs_base": changed_reasons,
                "preference_signature": preference_sha,
                "score_signature": scores_sha,
                "max_operations": max((item["operations"] or 0) for item in current),
            }
            write_json(target / "behavior.json", row)
            rows.append(row)
            config_manifest.append({"task": task_id, **{key: row[key] for key in
                ("config_id", "index", "values", "source_sha256", "is_zero_effect",
                 "is_author_default", "changed_preferred_vs_base", "changed_scores_vs_base",
                 "preference_signature", "score_signature")}})
        if zero_index is None or default_index is None:
            raise ValueError(f"{task_id} 未唯一绑定 zero/default 配置")
        zero_row = rows[zero_index]
        all_clean = all(not row["failures"] for row in rows)
        zero_exact = zero_row["changed_scores_vs_base"] == 0
        passed = all_clean and zero_exact and any_preference_change
        task_rows.append({
            "task": task_id,
            "source": str(SOURCES[task_id]),
            "source_sha256": hashlib.sha256(source.encode("utf-8")).hexdigest(),
            "zero_reference": str(BASES[task_id]),
            "zero_reference_sha256": hashlib.sha256(base_source.encode("utf-8")).hexdigest(),
            "views": len(views),
            "all_configurations_clean": all_clean,
            "zero_config_index": zero_index,
            "zero_exact_score_equivalence": zero_exact,
            "zero_changed_score_views": zero_row["changed_scores_vs_base"],
            "author_default_index": default_index,
            "default_changed_preferred_views": rows[default_index]["changed_preferred_vs_base"],
            "default_changed_score_views": rows[default_index]["changed_scores_vs_base"],
            "any_configuration_changes_preferred": any_preference_change,
            "unique_preference_signatures": len(preference_signatures),
            "unique_score_signatures": len(score_signatures),
            "duplicate_preference_groups": [count for count in preference_signatures.values() if count > 1],
            "duplicate_score_groups": [count for count in score_signatures.values() if count > 1],
            "behavior_preflight_pass": passed,
            "failure_reason": (None if passed else
                "运行失败" if not all_clean else
                "零效应未回到预登记基线" if not zero_exact else
                "234个真实观察均未产生首选变化"),
            "configurations": rows,
        })
    write_json(out / "configuration-manifest.json", {
        "schema": "r10-structural-configuration-manifest/1",
        "configurations": config_manifest,
        "count": len(config_manifest),
    })
    summary = {
        "schema": "r10-structural-behavior-preflight/1",
        "corpus": corpus,
        "tasks": task_rows,
        "passed_tasks": [row["task"] for row in task_rows if row["behavior_preflight_pass"]],
        "failed_tasks": [row["task"] for row in task_rows if not row["behavior_preflight_pass"]],
        "configurations_materialized": len(config_manifest),
        "effect_tables": 0,
        "selection_eligible": False,
    }
    write_json(out / "summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


def helper_constants(source: str) -> dict:
    """读取参数空间声明涉及的模块数值常数；仅用于绑定作者默认配置。"""
    space = load_space(source)
    result = {}
    for name in space["parameters"]:
        match = re.search(rf"^{re.escape(name)}\s*=\s*({NUMBER_RE})\s*$", source, re.MULTILINE)
        if match is None:
            raise ValueError(f"未找到模块常数 {name}")
        result[name] = float(match.group(1))
    return result


if __name__ == "__main__":
    main()
