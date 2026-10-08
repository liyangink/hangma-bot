"""P28 前置事实探针：三条前置必须成立，否则整批不该跑。

1. PublicSuccessorSearchPolicy 不在任何策略表里，也没有接线进 R18；
2. R18 v2 源码不使用后继分析（静态 AST + 运行期调用计数两条独立证据）；
3. R17 A/B 叶程序源码逐字节等于零桌门记录里的摘要。

只读既有文件；产物只写进 P28 新目录。
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

import ast
import hashlib
import json
import sys
from pathlib import Path


HERE = Path(__file__).resolve().parent
ROUTE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15')
ROOT = _PROJECT_ROOT

import r17_vs_r18v2_evaluation as p28  # noqa: E402


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def strategy_table_scan() -> dict:
    from hangma_bot import bootstrap

    names = set()
    for table_name in ("_STRATEGY_FACTORIES", "_RESEARCH_STRATEGY_FACTORIES",
                       "_SEQUENCE_MODEL_STRATEGIES"):
        table = getattr(bootstrap, table_name, {}) or {}
        for key, value in table.items():
            names.add(str(key))
            source = getattr(value, "__code__", None)
            names.add(str(getattr(value, "__qualname__", "")))
    hits = sorted(name for name in names if "successor" in name.lower())
    source = Path(bootstrap.__file__).read_text(encoding="utf-8")
    return {
        "registered_names_with_successor": hits,
        "bootstrap_source_mentions_public_successor": (
            "public_successor" in source or "PublicSuccessor" in source
        ),
        "available_strategies_with_successor": sorted(
            name for name in bootstrap.AVAILABLE_STRATEGIES
            if "successor" in name.lower()
        ),
        "research_strategies_with_successor": sorted(
            name for name in bootstrap.RESEARCH_STRATEGY_NAMES
            if "successor" in name.lower()
        ),
        "r18v2_registered_where": {
            "in_available_strategies": (
                p28.BASELINE_STRATEGY in bootstrap.AVAILABLE_STRATEGIES
            ),
            "in_research_strategies": (
                p28.BASELINE_STRATEGY in bootstrap.RESEARCH_STRATEGY_NAMES
            ),
        },
    }


def successor_reference_scan() -> dict:
    package = _project_file(_PROJECT_ROOT, ROOT / "src/hangma_bot")
    referencing = []
    for path in sorted(package.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        if "public_successor" in text or "PublicSuccessor" in text:
            referencing.append(str(path.relative_to(ROOT)))
    r18_files = [
        package / "policy/r18_integrated_positive_v2.py",
        package / "policy/r18_integrated_positive_v2_release.py",
        package / "policy/research_candidates.py",
        package / "bootstrap.py",
    ]
    return {
        "package_files_referencing_successor": referencing,
        "r18v2_chain_files": {
            str(path.relative_to(ROOT)): {
                "references_successor": (
                    "successor" in path.read_text(encoding="utf-8").lower()
                ),
                "sha256": digest(path),
                "lines": len(path.read_text(encoding="utf-8").splitlines()),
            }
            for path in r18_files
        },
    }


def runtime_call_count(arm: str, source_row: dict) -> dict:
    """运行一臂一个来源，统计规则侧后继分析的真实调用次数。"""

    from hangma_bot.hangma.engine import HangmaRules

    counter = {"calls": 0}
    original = HangmaRules.analyze_public_self_draw_successors

    def counting(self, observation):
        counter["calls"] += 1
        return original(self, observation)

    HangmaRules.analyze_public_self_draw_successors = counting
    try:
        row = p28.execute_stage(arm, source_row, p28.passing_candidates())
    finally:
        HangmaRules.analyze_public_self_draw_successors = original
    return {
        "arm": arm,
        "source": source_row["source_id"],
        "status": row["stage"]["status"],
        "successor_analysis_calls": counter["calls"],
        "focal_policy_ids": [
            item["policy_id"] for item in row["stage"]["focal_policy_ids_by_table"]
        ],
    }


def main() -> None:
    out_path = p28.OUT / "prerequisite-probe.json"
    if not p28.OUT.exists():
        raise SystemExit("请先跑 prepare；本探针把产物写进 P28 新目录")
    candidates = p28.passing_candidates()
    source_row = {"mix": "M", "root_index": 3, "focal_seat": 2,
                  "source_id": "M:r03:s2"}
    report = {
        "schema": "p28-prerequisite-probe/1",
        "strategy_tables": strategy_table_scan(),
        "successor_references": successor_reference_scan(),
        "r17_candidate_identity": {
            candidate_id: {
                "path": item["path"],
                "sha256": item["sha256"],
                "gate_recorded_sha256": json.loads(
                    Path(item["gate_result"]).read_text(encoding="utf-8")
                ).get("candidate_source_sha256"),
                "byte_identical": digest(Path(item["path"])) == item["sha256"],
                "candidate_identity": item["identity"],
            }
            for candidate_id, item in candidates.items()
        },
        "runtime_successor_calls": {
            "r18v2_baseline": runtime_call_count("baseline", source_row),
            "r17_candidate_A_positive_control": runtime_call_count(
                "candidate:A", source_row
            ),
        },
        "verdict": {},
    }
    tables = report["strategy_tables"]
    calls = report["runtime_successor_calls"]
    report["verdict"] = {
        "P1_public_successor_not_registered": (
            not tables["registered_names_with_successor"]
            and not tables["bootstrap_source_mentions_public_successor"]
            and not tables["available_strategies_with_successor"]
            and not tables["research_strategies_with_successor"]
        ),
        "P2_r18v2_has_no_successor_use": (
            all(
                not item["references_successor"]
                for item in report["successor_references"]["r18v2_chain_files"].values()
            )
            and calls["r18v2_baseline"]["successor_analysis_calls"] == 0
            and calls["r17_candidate_A_positive_control"]["successor_analysis_calls"] > 0
        ),
        "P3_r17_sources_byte_identical": all(
            item["byte_identical"]
            and item["sha256"] == item["gate_recorded_sha256"]
            for item in report["r17_candidate_identity"].values()
        ),
    }
    report["verdict"]["all_three_hold"] = all(report["verdict"].values())
    p28.write_json(out_path, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
