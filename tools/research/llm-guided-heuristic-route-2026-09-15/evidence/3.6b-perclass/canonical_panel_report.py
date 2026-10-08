"""canonical 面板（panel-canonical-20260910）单命令报告：**一次扫描**产出 3.6a 逐类账 + 6 份 G-2C。

为什么用脚本而不是 CLI：CLI 的 --coverage 一次只跑一批候选，而逐类**判定**（G-2C）
需要"每个候选一份记录"。本脚本用 evaluate_panel 的**多候选单次扫描**同时得到两者——
判定逻辑仍只有一份实现（`sitin_gates.perclass_records` 纯函数），扫描次数只是工程选择。

口径（F7）：panel_id=panel-canonical-20260910；record_layer=filled（记录层归一化）；
指纹与行数取自 corpus-manifest-canonical.json。诊断子集 subset-perclass-frozen 的数字
**不得**与本文件的数字相加或混用。

只读：不跑桌赛、不写语料、不改候选或线上配置。
"""
from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/llm-guided-heuristic-route-2026-09-15/evidence/3.6b-perclass'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

import hashlib
import importlib.util
import json
import sys
import time
from pathlib import Path

ROOT = _PROJECT_ROOT
HERE = Path(__file__).resolve().parent
TOOLS = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/tools')
sys.path.insert(0, str(_project_file(_PROJECT_ROOT, ROOT / "src")))
sys.path.insert(0, str(TOOLS))

spec = importlib.util.spec_from_file_location("sitin_scenario_classes",
                                              _project_file(_PROJECT_ROOT, TOOLS / "sitin_scenario_classes.py"))
sc = importlib.util.module_from_spec(spec)
sys.modules["sitin_scenario_classes"] = sc
assert spec.loader is not None
spec.loader.exec_module(sc)
gates = sc._tool("sitin_gates")

PANEL = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/3.6b-perclass/corpus-manifest-canonical.json')
OUT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/3.6b-perclass/canonical')
RULESET = "hangma-mvp-v10-public-counts"
CANDIDATES = ("chain_path_value", "four_component_path_value", "meld_opportunity_cost",
              "meld_waiting_conditional", "multiplier_path_potential",
              "seven_pairs_path_value")
WEIGHTS = {
    "chain_path_value": {"adj.scale": 40.0},
    "four_component_path_value": {},
    "meld_opportunity_cost": {"adj.beta": 20.0},
    "meld_waiting_conditional": {"adj.gain": 60.0, "adj.reference": 21.0},
    "multiplier_path_potential": {
        "adj.scale_points_per_log2_fan": 12.0, "adj.w_chain_step_log2fan": 1.0,
        "adj.w_chain_progress_log2fan": 0.5, "adj.w_baotou_progress_log2fan": 0.5,
        "adj.w_branch_quality_log2fan": 0.5, "adj.w_four_white_ratio_log2fan": 0.5},
    "seven_pairs_path_value": {"adj.path_log2": 1.0, "adj.closer_bonus": 1.0},
}


def main() -> int:
    manifest = sc.manifest_info(PANEL) or {}
    # 面板身份（F7）：**内容指纹**（105 份文件的 sha256 组合）才是面板身份——它不随清单的
    # 元数据（排除账、注释、格式）变化；清单文件自身的哈希另存 manifest_sha256 供审计。
    fingerprint = manifest.get("fingerprint") or hashlib.sha256(PANEL.read_bytes()).hexdigest()
    input_info = {
        "path": str(PANEL),
        "sha256": fingerprint,
        "rows": manifest.get("rows"),
        "constructed": False,
        "evidence_kind": "admission",
        "record_layer": manifest.get("record_layer"),
        "manifest": manifest,
        "panel_identity": {
            "panel_id": manifest.get("panel_id"),
            "fingerprint": fingerprint,
            "fingerprint_basis": "清单内 105 份文件的 sha256 组合（内容口径，不含清单元数据）",
            "manifest_sha256": hashlib.sha256(PANEL.read_bytes()).hexdigest(),
            "rows": manifest.get("rows"),
            "record_layer_filled": bool(manifest.get("record_layer_filled")),
            "record_layer": manifest.get("record_layer"),
            "excluded_rows": manifest.get("excluded_rows"),
            "excluded_ratio": manifest.get("excluded_ratio"),
        },
    }
    started = time.time()
    evaluation = sc.evaluate_panel(
        sc.iter_rows(PANEL), CANDIDATES, ruleset=RULESET,
        weights_by_candidate=WEIGHTS, record_layer="filled", diagnostics=True)
    elapsed = time.time() - started
    panel = evaluation["panel"]
    input_info["rows"] = panel["rows_total"]
    input_info["panel_identity"]["rows"] = panel["rows_total"]
    input_info["raw_coverage"] = panel["raw_coverage"]

    OUT.mkdir(parents=True, exist_ok=True)
    coverage = sc.coverage_ledger(input_info, evaluation, CANDIDATES)
    coverage["boundaries"] = list(sc.BOUNDARIES)
    (_project_file(_PROJECT_ROOT, OUT / "coverage.json")).write_text(
        json.dumps(coverage, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (_project_file(_PROJECT_ROOT, OUT / "COVERAGE.md")).write_text(sc.render_coverage_markdown(coverage), encoding="utf-8")
    matrix = sc.class_matrix(coverage)
    (_project_file(_PROJECT_ROOT, OUT / "matrix.json")).write_text(
        json.dumps(matrix, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (_project_file(_PROJECT_ROOT, OUT / "MATRIX.md")).write_text(sc.render_matrix_markdown(matrix), encoding="utf-8")
    effect = sc.effect_layer(input_info, evaluation, CANDIDATES)
    (_project_file(_PROJECT_ROOT, OUT / "effect-layer.json")).write_text(
        json.dumps(effect, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (_project_file(_PROJECT_ROOT, OUT / "EFFECT-LAYER.md")).write_text(sc.render_effect_layer_markdown(effect),
                                         encoding="utf-8")
    for name in CANDIDATES:
        record = gates.perclass_records(evaluation, name, weights=WEIGHTS[name],
                                        ruleset=RULESET, raw_diagnostics=True)
        (_project_file(_PROJECT_ROOT, OUT / "g2c-{0}.json".format(name))).write_text(
            json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    verdicts = coverage["summary"]["verdict_counts"]
    print("panel_id:", manifest.get("panel_id"), "record_layer:", panel.get("record_layer"))
    print("扫描 {0:.1f}s；行 {1} / 计分 {2} / 排除降级 {3}".format(
        elapsed, panel["rows_total"], panel["scored"], panel["excluded_degraded"]))
    print("四态：", json.dumps(verdicts, ensure_ascii=False))
    print("raw 层：chain_piao 已知 {0} / 不可判定 {1} / chain_count>0 {2}".format(
        panel["raw_coverage"]["raw_chain_piao_known"],
        panel["raw_coverage"]["raw_chain_piao_undecidable"],
        panel["raw_coverage"]["raw_chain_count_nonzero"]))
    for name in CANDIDATES:
        record = json.loads((_project_file(_PROJECT_ROOT, OUT / "g2c-{0}.json".format(name))).read_text(encoding="utf-8"))
        roll = record["detail"]["rollup"]
        print("G-2C {0:28s} {1:13s} declared={2:3d} reliable={3:2d} insuff={4:2d} notver={5:2d} viol={6}".format(
            name, record["status"], roll["declared_count"], roll["reliable_count"],
            roll["counts"]["insufficient"], roll["counts"]["not_verified"],
            record["detail"]["out_of_class_increment"]["violation_total"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
