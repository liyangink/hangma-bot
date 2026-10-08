"""为 T200 natural 候选补12个可恢复的普通摸打开发输入；只准备缓存材料。

固定母1至6、换座0，每母按原全座决策行顺序取最先两个合格窗口。
条件只读公开观察、完整合法根与已封规则图，不按候选评分或终分选题。
复用 mechanical_probe 的核验/绑定接口；不评分、不恢复世界、不跑桌/API。
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
import gzip
import importlib.util
import json
from pathlib import Path
import sys

ROOT = _PROJECT_ROOT
STAGE = _project_file(_PROJECT_ROOT, '.private/t200-eoh-fast-evolution')
HERE = Path(__file__).resolve().parent
ORIGIN_MANIFEST = _project_file(_PROJECT_ROOT, '.private/t199-four-step-execution/p0-impact-32-attempt-004/COMPOSITE-ORIGINS.json')
ORIGIN_HELPER = _project_file(_PROJECT_ROOT, '.private/t199-four-step-execution/joint-continuation/common.py')
NATURAL_ID = "e4496b5f1511e323250b591e6f071afd35c9625ac5bf585827fb2361c6c3ba12"


def load_file(path, name):
    """装载明确指定的现有薄工具，避免改动其源码或全局绑定。"""
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def tools():
    """复用原机械入口的规范JSON、当前父核验和文件指纹。"""
    return load_file(_project_file(_PROJECT_ROOT, HERE / "mechanical_probe.py"), "_t200_immutable_mechanical_probe")


def eligible(row, view, prefix_seats, prefix_count, core):
    """纯公开事实筛选：0/1白、无胡杠/特殊链，所有弃后根均非听牌。"""
    observation = row["observation"]
    if (observation["phase"] != "draw" or observation["gang_draw"] is not False or
        observation["chain_piao"] != 0 or observation["rule_state"]["chain_count"] != 0 or
        observation["rule_state"]["baotou"] is not False or
        observation["rule_state"]["catch_play"] is not False or
        observation["remaining_tile_count"] is None or observation["remaining_tile_count"] <= 20 or
        {key.split(":", 1)[0] for key in row["legal_action_keys"]} != {"discard"} or
        prefix_count < 8 or prefix_seats != {0, 1, 2, 3}):
        return False
    if core.root_white_count(view) not in (0, 1):
        return False
    if any(node["gap_kind"] is not None for node in view["nodes"]):
        return False
    nodes = {node["node_key"]: node for node in view["nodes"]}
    for action in view["actions"]:
        waiting = nodes[action["node_key"]]["waiting"]
        if waiting is None:
            return False
        structure = waiting["structure"]
        if (structure["standard_shanten"] <= 0 or
            structure["seven_pairs_shanten"] is not None and structure["seven_pairs_shanten"] <= 0):
            return False
    return True


def prepare(output):
    """从指定成功32复合来源取六母12窗；复制完整图、精确父向量与恢复定位。"""
    core = tools()
    batch, parent = core.current_parent()
    origins_tool = load_file(ORIGIN_HELPER, "_t200_specified_P0_origins")
    manifest = core.read(ORIGIN_MANIFEST)
    source, origins, frozen, _ = origins_tool.composite_origins(manifest["reference_plan_path"], ORIGIN_MANIFEST)
    if source["candidate_identity"] != parent["identity"]:
        raise ValueError("成功32桌不是当前P0精确身份")
    windows, selected_sha, scanned = [], set(), []
    for mother in range(1, 7):
        matches = [origin for origin in origins.values()
                   if origin["task"]["root"] == mother and origin["task"]["rotation"] == 0]
        if len(matches) != 1:
            raise ValueError("事前母/换座来源不唯一")
        origin = matches[0]
        task = origin["task"]
        views = {}
        with gzip.open(origin["raw_paths"]["views.jsonl.gz"], "rt") as stream:
            for line in stream:
                capture = json.loads(line)
                if core.digest(capture["view"]) != capture["view_sha256"]:
                    raise ValueError("完整原图摘要不同")
                views[capture["view_sha256"]] = capture["view"]
        prefix, prefix_seats, picked = [], set(), 0
        with gzip.open(origin["raw_paths"]["decisions.jsonl.gz"], "rt") as stream:
            for row_no, line in enumerate(stream):
                row = json.loads(line)
                if row["status"] != "chosen" or row["selected_action_key"] not in row["legal_action_keys"]:
                    raise ValueError("原全座前缀含未选择/非法动作")
                if row["seat"] == task["focal_physical_seat"]:
                    if not row["c_self_scored"] or len(row["scoring_calls"]) != 1:
                        raise ValueError("成功P0焦点原评分缺失")
                    call = row["scoring_calls"][0]
                    if not (call["status"] == "SCORED" and call["full_legal_keys"] and
                            call["score_completed"] and call["input_capture"]["saved_before_score"]):
                        raise ValueError("原父完整合法评分与捕获未闭")
                    sha = call["input_capture"]["view_sha256"]
                    view = views[sha]
                    if sha not in selected_sha and eligible(row, view, prefix_seats, len(prefix), core):
                        keys = sorted(row["legal_action_keys"])
                        if keys != sorted(action["action_key"] for action in view["actions"]):
                            raise ValueError("缓存图/原完整合法根不同")
                        # 选点已由上面的公开事实固定，随后才复制原父评分，绝不据分值改选点。
                        entries = sorted(({"action_key": entry["action_key"], "score": entry["score"],
                                           "trace": entry["trace"].get("detail", entry["trace"])}
                                          for entry in row["candidates"]), key=lambda entry: (-entry["score"], entry["action_key"]))
                        label = f"cache:m{mother:02d}:seat0:row{row_no:05d}"
                        windows.append({"label": label, "kind": "captured_current_P0",
                            "purpose": "普通摸打0/1白，无Hu/Gang/特殊链；所有弃后根非听牌，跨母机制补题",
                            "observation": row["observation"], "window_key": row["window_key"],
                            "legal_action_keys": keys, "captured_view": view, "captured_view_sha256": sha,
                            "parent_entries": entries, "root_white_count": core.root_white_count(view),
                            "source_case_id": row["decision_id"], "origin_audit_file": origin["raw_paths"]["decisions.jsonl.gz"],
                            "source_mother": mother, "rotation": 0, "target_row": row_no,
                            "source_origin": origin,
                            "all_seat_prefix": {"row_count": len(prefix), "seats": sorted(prefix_seats),
                                "all_chosen_legal": True, "prefix_sha256": core.digest(prefix), "rows": list(prefix),
                                "scope": "离线恢复定位与实际选择证据，不进入候选score_actions输入"},
                            "selection_score_or_outcome_accessed": False})
                        selected_sha.add(sha)
                        picked += 1
                        if picked == 2:
                            scanned.append({"mother": mother, "rotation": 0, "table_no": task["table_no"],
                                "last_read_decision_row": row_no, "selected": picked})
                            break
                prefix.append({"row_no": row_no, "decision_id": row["decision_id"], "seat": row["seat"],
                    "window_key": row["window_key"], "legal_action_keys": row["legal_action_keys"],
                    "selected_action_key": row["selected_action_key"]})
                prefix_seats.add(row["seat"])
        if picked != 2:
            raise ValueError("指定母来源没有两份合格输入；不自动改母或调条件")
    frozen.update(core.producer_files())
    frozen.update({str(path): core.pin(path) for path in (Path(__file__).resolve(), _project_file(_PROJECT_ROOT, HERE / "mechanical_probe.py"),
        ORIGIN_HELPER, core.BATCH, core.PARENT / "candidate.py", core.PARENT / "generation.json")})
    core.verify(frozen)
    panel = {"schema": "t200-finite-mechanical-panel/1", "parent_identity": parent["identity"],
        "selected_case_ids": [window["label"] for window in windows],
        "selection_scope": "事前母1..6/换座0；原行顺序最先两个公开条件合格窗口；非候选评分或终分选择",
        "windows": windows, "window_count": 12, "repeats": 2, "max_candidates": 1,
        "score_budget": 240, "planned_maximum_scores": 48, "files": frozen,
        "prepare_rule_score_World_tables_API_calls": 0,
        "claims": {"development_only": True, "strength": False, "deadline": False, "release": False},
        "natural_candidate_id": NATURAL_ID, "origin_manifest": str(ORIGIN_MANIFEST),
        "read_scope": "只解析预定六母换座0的公开图与首个两合格点之前的全座决策；32来源其余文件只验摘要",
        "source_scans": scanned}
    out = core.new_directory(output)
    core.save(out / "PANEL.json", panel)
    checked, _, _ = core.checked_panel(out / "PANEL.json")
    validate_windows(checked, core)
    core.save(out / "PREPARED.json", {"complete": True, "panel_pin": core.pin(out / "PANEL.json"),
        "entry_pin": core.pin(Path(__file__)), "original_mechanical_entry_pin": core.pin(_project_file(_PROJECT_ROOT, HERE / "mechanical_probe.py")),
        "source_mothers": [1, 2, 3, 4, 5, 6], "windows": 12, "all_seat_prefixes_legal": True,
        "full_current_P0_identity": parent["identity"]["candidate_id"], "source_scans": scanned,
        "scores_rules_World_tables_API": 0, "planned_maximum_scores": 48,
        "candidate_execution_started": False})
    return {"complete": True, "panel": str(out / "PANEL.json"), "panel_pin": core.pin(out / "PANEL.json"),
            "mothers": 6, "windows": 12, "planned_scores": 48, "actual_scores_rules_World_tables_API": 0}


def validate_windows(panel, core):
    """只复核全部12窗口、公开条件、精确图摘要和合法全座前缀，不重建规则。"""
    from hangma_bot.kernel.serialization import observation_from_json, window_key_from_json
    if panel["window_count"] != 12 or panel["natural_candidate_id"] != NATURAL_ID:
        raise ValueError("不是本natural专属12题")
    for window in panel["windows"]:
        prefix = window["all_seat_prefix"]
        observation_from_json(window["observation"])
        window_key_from_json(window["window_key"])
        if (core.digest(window["captured_view"]) != window["captured_view_sha256"] or
            prefix["row_count"] != len(prefix["rows"]) or core.digest(prefix["rows"]) != prefix["prefix_sha256"] or
            any(row["selected_action_key"] not in row["legal_action_keys"] for row in prefix["rows"]) or
            not eligible(window, window["captured_view"], set(prefix["seats"]), prefix["row_count"], core)):
            raise ValueError("补题/原图/前缀事实不一致")
    if len({window["source_mother"] for window in panel["windows"]}) != 6:
        raise ValueError("没有覆盖固定六母")


def main():
    """prepare/validate均0评分；bind只接受该natural候选，复用原入口新绑定。"""
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    prep = commands.add_parser("prepare")
    prep.add_argument("--out", type=Path, default=_project_file(_PROJECT_ROOT, STAGE / "mechanical-tools/cache-panel-001"))
    check = commands.add_parser("validate")
    check.add_argument("--panel", type=Path, required=True)
    binding = commands.add_parser("bind")
    binding.add_argument("--panel", type=Path, required=True)
    binding.add_argument("--candidate", type=Path, required=True)
    binding.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    core = tools()
    sys.addaudithook(core.deny_external)
    if args.command == "prepare":
        result = prepare(args.out)
    else:
        panel, batch, _ = core.checked_panel(args.panel)
        validate_windows(panel, core)
        if args.command == "validate":
            result = {"complete": True, "windows": 12, "mothers": 6, "panel_pin": core.pin(args.panel),
                      "actual_scores_rules_World_tables_API": 0}
        else:
            from hangma_bot.offline.vip_eoh_generate import load_vip_parents
            candidate = load_vip_parents([args.candidate], batch)[0]
            if candidate["identity"]["candidate_id"] != NATURAL_ID:
                raise ValueError("本补题只绑定已指定natural，不扩候选费用")
            result = core.bind(args.panel, [args.candidate], args.out)
            if result["planned_score_calls"] != 48:
                raise ValueError("natural专属补题超48评分")
    print(json.dumps(result, ensure_ascii=False, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
