"""T200 phase4真实开发面板拼接；仅prepare，0新规则/评分/World/API。

来源顺序冻结为frontier001五点、frontier002最多六点、B15-01领导碰
控制；若不足12，按预声明旧panel002标签补齐。完整图SHA去重，不强凑。
复用现机械面板schema与检查接口；阶段208评分上限由根另行冻结批准。
"""
from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t200-eoh-fast-evolution-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

import argparse
import copy
import json
import math
from pathlib import Path
import sys

import mechanical_probe as helper

STAGE = helper.STAGE
OLD_FRONTIER = STAGE / "frontier-feedback-001"
NEW_FRONTIER = STAGE / "frontier-feedback-002"
BEHAVIOR = STAGE / "behavior-feedback"
OLD_PANEL = helper.TOOLS / "panel-002/PANEL.json"
OUTPUT = helper.TOOLS / "search-panel-004"
FALLBACKS = ("O01", "C02", "validation-088:fresh:008:07", "C03", "C04", "G04")


def add_closed(folder, parent, files, *, count_limit):
    """核已闭片段、当前P0及原来源指纹；不评分，也不读候选成绩选输入。"""
    closed_path, binding_path = folder / "CLOSED.json", folder / "CURRENT-P0-BINDING.json"
    closed, binding = helper.read(closed_path), helper.read(binding_path)
    if closed.get("complete") is not True or binding["candidate_identity"] != parent["identity"]:
        raise ValueError("片段未闭或P0完整身份不同:" + str(folder))
    pins = closed["case_pins"]
    if not 0 <= len(pins) <= count_limit:
        raise ValueError("片段题数超声明上限")
    files.update({str(closed_path): helper.pin(closed_path), str(binding_path): helper.pin(binding_path)})
    files.update(closed.get("source_pins", {}))
    for relative, expected in pins.items():
        path = (folder / relative).resolve()
        if not path.is_relative_to(folder.resolve()) or helper.pin(path) != expected:
            raise ValueError("片段case路径或指纹不同")
        files[str(path)] = expected
    helper.verify(files)
    return closed, pins


def normalized(case, path, parent, fragment):
    """仅改封套字段名，完整图、精确父分和解释原值不改。"""
    summary = case.get("summary", {})
    label = case.get("case_id", case.get("label", summary.get("case_id")))
    dto = case.get("public_view", case.get("public_graph"))
    sha = case.get("view_sha256", summary.get("view_sha256"))
    legal = sorted(case["legal_action_keys"])
    entries = sorted(({"action_key": row["action_key"], "score": row["score"],
                        "trace": row["trace"].get("detail", row["trace"])}
                       for row in case["parent_entries"]), key=lambda row: (-row["score"], row["action_key"]))
    first = case.get("parent_first", summary.get("parent_first"))
    if (not label or not dto or helper.digest(dto) != sha or
        sorted(action["action_key"] for action in dto["actions"]) != legal or
        sorted(entry["action_key"] for entry in entries) != legal or
        len(legal) != len(set(legal)) or entries[0]["action_key"] != first or
        any(type(entry["score"]) not in (int, float) or not math.isfinite(entry["score"]) for entry in entries) or
        any(node["gap_kind"] is not None for node in dto["nodes"])):
        raise ValueError("完整图/父全向量不闭:" + str(label))
    identity = parent["identity"]
    if (dto["schema_version"] != identity["view_schema_version"] or
        dto["graph_schema_version"] != identity["graph_schema_version"] or
        dto["limits"] != identity["params"]["projection_limits"] or
        any(dto["binding"][key] != value for key, value in identity["params"]["rule_config"].items())):
        raise ValueError("图合同/投影/实际规则与当前P0不同")
    from hangma_bot.kernel.serialization import observation_from_json, window_key_from_json
    observation_from_json(case["observation"])
    window_key_from_json(case["window_key"])
    return {"label": label, "kind": "captured_current_P0", "purpose": "phase4已封真实机制搜索输入",
        "observation": case["observation"], "window_key": case["window_key"], "legal_action_keys": legal,
        "captured_view": dto, "captured_view_sha256": sha, "parent_entries": entries,
        "parent_first": first, "root_white_count": helper.root_white_count(dto),
        "source_case_id": label, "origin_audit_file": str(path), "source_fragment": fragment,
        "source_kind": case.get("kind", summary.get("kind")),
        "source_mother": case.get("mother", summary.get("mother"))}


def prepare(output):
    """等全部片段ready后一次创建新12窗面板；只保留首个完整SHA来源。"""
    _, parent = helper.current_parent()
    files = helper.producer_files()
    for path in (Path(__file__), Path(helper.__file__), helper.BATCH,
                 helper.PARENT / "generation.json", helper.PARENT / "candidate.py"):
        files[str(path.resolve())] = helper.pin(path)
    old_closed, old_pins = add_closed(OLD_FRONTIER, parent, files, count_limit=5)
    new_closed, new_pins = add_closed(NEW_FRONTIER, parent, files, count_limit=6)
    if len(old_pins) != 5:
        raise ValueError("旧frontier必须完整五点")
    windows, seen, skipped = [], set(), []
    def accept(window):
        sha = window["captured_view_sha256"]
        if sha in seen:
            skipped.append({"label": window["label"], "view_sha256": sha, "reason": "full_graph_duplicate_keep_first_source"})
            return
        if any(item["label"] == window["label"] for item in windows):
            raise ValueError("不同完整图冒用同输入标签")
        seen.add(sha)
        windows.append(window)
    for folder, pins in ((OLD_FRONTIER, old_pins), (NEW_FRONTIER, new_pins)):
        for relative in sorted(pins):
            path = folder / relative
            accept(normalized(helper.read(path), path, parent, folder.name))
    behavior_closed = helper.read(BEHAVIOR / "CLOSED.json")
    publication_path = BEHAVIOR / "PUBLICATION-CLOSED.json"
    publication = helper.read(publication_path)
    if behavior_closed.get("complete") is not True or publication.get("complete") is not True or publication["closed_pin"] != helper.pin(BEHAVIOR / "CLOSED.json"):
        raise ValueError("B15缓存提取/发布未闭")
    files.update(behavior_closed["source_pins"])
    files.update({str(BEHAVIOR / "CLOSED.json"): helper.pin(BEHAVIOR / "CLOSED.json"),
                  str(publication_path): helper.pin(publication_path)})
    control_path = BEHAVIOR / "cases/T200-cache-01.json"
    expected = behavior_closed["case_files"].get(str(control_path), behavior_closed["case_files"].get("cases/T200-cache-01.json"))
    if expected != helper.pin(control_path):
        raise ValueError("B15-01控制case指纹不同")
    files[str(control_path)] = expected
    accept(normalized(helper.read(control_path), control_path, parent, "B15-01_real_leading_peng_control"))
    if len(windows) < 12:
        old_panel, _, old_parent = helper.checked_panel(OLD_PANEL)
        if old_parent["identity"] != parent["identity"]:
            raise ValueError("回填面板P0身份不同")
        files.update(old_panel["files"])
        files[str(OLD_PANEL)] = helper.pin(OLD_PANEL)
        for label in FALLBACKS:
            if len(windows) >= 12:
                break
            window = copy.deepcopy(next(item for item in old_panel["windows"] if item["label"] == label))
            window["source_fragment"] = "declared_panel002_fallback"
            accept(window)
    if len(windows) != 12 or len(seen) != 12:
        raise ValueError("真实完整SHA不足/超出12，不强凑或扩量")
    helper.verify(files)
    panel = {"schema": "t200-finite-mechanical-panel/1", "parent_identity": parent["identity"],
        "windows": windows, "window_count": 12, "selected_case_ids": [item["label"] for item in windows],
        "selection_scope": "frontier001→frontier002→B15-01→预声明panel002回填；完整图SHA首来源去重，未看候选或终分选题",
        "repeats": 2, "max_candidates": 4, "score_budget": 240, "planned_maximum_scores": 120,
        "score_budget_field_scope": "既有generic schema结构额度240；不代表本phase获批，根另冻结208上限",
        "phase4_proposed_cost_split": {"search12_P0_plus_up_to4_candidates_two_repeats": 120,
                                       "new_E2_old_controls_maximum": 88, "maximum_combined": 208},
        "phase4_execution_budget_approved": False, "files": files, "duplicate_graphs_skipped": skipped,
        "prepare_rule_score_World_tables_API_calls": 0,
        "claims": {"development_only": True, "strength": False, "deadline": False, "release": False}}
    out = helper.new_directory(output)
    helper.save(out / "PANEL.json", panel)
    helper.checked_panel(out / "PANEL.json")
    helper.save(out / "PREPARED.json", {"complete": True, "entry_pin": helper.pin(Path(__file__)),
        "panel_pin": helper.pin(out / "PANEL.json"), "windows": 12,
        "source_order": ["frontier-feedback-001", "frontier-feedback-002", "B15-01", *FALLBACKS],
        "actual_scores_rules_World_tables_API": 0, "candidate_binding_or_execution_started": False,
        "maximum_future_search_scores": 120, "phase4_root_budget_pending": True})
    return {"complete": True, "panel": str(out / "PANEL.json"), "panel_pin": helper.pin(out / "PANEL.json"),
            "windows": 12, "scores_rules_World_tables_API": 0}


def main():
    """片段未ready时0输出创建；仅一次新面板prepare，没有评分/绑定执行分支。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=OUTPUT)
    args = parser.parse_args()
    sys.addaudithook(helper.deny_external)
    if not all((NEW_FRONTIER / name).is_file() for name in ("CLOSED.json", "CURRENT-P0-BINDING.json")):
        print(json.dumps({"complete": False, "status": "new_fragment_pending", "scores_rules_World_tables_API": 0,
                          "output_created": False}, ensure_ascii=False))
        return 2
    print(json.dumps(prepare(args.out), ensure_ascii=False, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
