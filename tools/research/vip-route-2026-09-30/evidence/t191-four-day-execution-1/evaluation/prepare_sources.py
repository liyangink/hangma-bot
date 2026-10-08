"""按公开事实补至多10个T191开发窗口；只读旧公开流，零评分、零新世界。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t191-four-day-execution-1/evaluation'

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
import json
import time
from pathlib import Path

from abc_support import *

BUCKETS = ("current_hu_no_immediate_upgrade", "current_hu_immediate_upgrade",
    "white0_same_speed_dealer_early", "white0_same_speed_nondealer_early",
    "white1_same_speed_dealer_early", "white1_same_speed_nondealer_early",
    "white0_same_speed_dealer_late", "white0_same_speed_nondealer_late",
    "white1_same_speed_dealer_late", "white1_same_speed_nondealer_late")


def public_tags(row, view):
    """仅以本家公开形、合法胡支付和下一正常摸支付标记，不推断更远升级或胜负。"""
    obs = row["observation"]
    white = obs["my_hand"].count("白") + int(obs["drawn_tile"] == "白")
    wall, seat = obs["remaining_tile_count"], obs["seat"]
    position = "dealer" if seat == obs["dealer_seat"] else "nondealer"
    period = "early" if type(wall) is int and wall >= 60 else "late" if type(wall) is int and wall <= 30 else "middle"
    nodes = {n["node_key"]: n for n in view["nodes"]}
    direct = [nodes[a["node_key"]] for a in view["actions"]]
    proofs, waits = [], [n["waiting"] for n in direct if n["kind"] == "wait" and n["waiting"] is not None]
    for wait in waits:
        s = wait["structure"]
        if s["seven_pairs_shanten"] is None or s["standard_shanten"] != s["seven_pairs_shanten"]:
            continue
        # 相同物理码去重；精确零容量牌码不成为标签证据。
        allowed = {code for code, cap in zip(view["tile_order"], wait["unseen_capacities"]) if cap is not None and cap > 0}
        standard, seven = set(wait["standard_useful_codes"]) & allowed, set(wait["seven_pairs_useful_codes"]) & allowed
        if len(standard | seven) > max(len(standard), len(seven)):
            proofs.append({"minimum_shanten": s["standard_shanten"], "standard_codes": sorted(standard),
                "seven_pairs_codes": sorted(seven), "union_codes": sorted(standard | seven)})
    tags = set()
    if white in (0, 1) and proofs and period in ("early", "late"):
        tags.add(f"white{white}_same_speed_{position}_{period}")
    current = [n["settlement"]["score_delta"][seat] for n in direct if n["kind"] == "hu"]
    increments = []
    if current:
        anchor = max(current)
        increments = [p["settlement"]["score_delta"][seat] - anchor for w in waits for p in w["normal_draw_hu_payments"]]
        if increments and max(increments) <= 0:
            tags.add("current_hu_no_immediate_upgrade")
        if increments and max(increments) > 0:
            tags.add("current_hu_immediate_upgrade")
    return tags, {"white_count": white, "dealer_relation": position, "wall_remaining_tiles": wall,
        "wall_period": period, "equal_speed_union_proofs": proofs,
        "current_hu_score_delta": current, "next_normal_draw_payment_increments": increments,
        "future_upgrade_status": "unknown_beyond_local_given_normal_draw_hu"}


def main(args):
    """固定母源升序扫描arm0/座位0，每类每母取首窗；按类别优先选不同母源。"""
    background_priority()
    base = EVIDENCE / "t186-incremental-opportunity-repair-1"
    prior_path = EVIDENCE / "t188-joint-score-mechanism-1/CONDITION-PLAN.json"
    prior = read(prior_path)
    excluded = {t["composition"]["root_id"] for t in prior["targets"]}
    files, roots = {str(prior_path): pin(prior_path), str(Path(__file__)): pin(Path(__file__)),
        str(_project_file(_PROJECT_ROOT, HERE / "abc_support.py")): pin(_project_file(_PROJECT_ROOT, HERE / "abc_support.py"))}, {}
    for name in ("NATURAL-STAGE-001-PLAN.json", "NATURAL-STAGE-002-PLAN.json", "NATURAL-STAGE-003-PLAN.json", "JOINT-NATURAL-STAGE-001-PLAN.json"):
        path = base / name
        plan = read(path)
        files[str(path)] = pin(path)
        for index in plan["root_indices"]:
            composition = plan["roots"][index - 1]
            roots[composition["root_id"]] = (index, composition)
    candidates, scanned, missing, view_bytes = [], [], [], 0
    started = time.monotonic()
    for root_id, (index, composition) in sorted(roots.items()):
        if root_id in excluded:
            continue
        if len(scanned) >= args.maximum_tables:
            break
        directory = base / "natural-development" / f"root-{index:03d}" / "seat-0-arm-0"
        closure_path = directory / "CLOSURE.json"
        closure = read(closure_path)
        require(closure["complete"] and closure["root"] == composition and closure["rotation"] == 0, "旧恢复来源未闭合或不符")
        # 只使用闭合性及恢复元数据；不复制旧后继结算给候选作者。
        decision_path, views_path = directory / "focal-decisions.jsonl.gz", directory / "views.jsonl.gz"
        for path in (closure_path, decision_path, views_path):
            files[str(path)] = pin(path)
        wanted, row_count = {}, 0
        with gzip.open(decision_path, "rt") as stream:
            for line in stream:
                row = json.loads(line)
                row_count += 1
                obs = row["observation"]
                wall = obs["remaining_tile_count"]
                white = obs["my_hand"].count("白") + int(obs["drawn_tile"] == "白")
                maybe = row["current_opportunity"]["legal_hu"] or (row["phase"] == "draw" and white in (0, 1)
                    and type(wall) is int and (wall >= 60 or wall <= 30))
                if maybe:
                    call = row["scoring_calls"][0]
                    require(call["input_capture"]["saved_before_score"], "原公开图缺捕获")
                    wanted[call["input_capture"]["view_sha256"]] = row
        first = {}
        with gzip.open(views_path, "rb") as stream:
            for line in stream:
                view_bytes += len(line)
                require(view_bytes <= args.maximum_uncompressed_view_bytes, "公开流读取字节上限耗尽，禁止重选题")
                saved = json.loads(line)
                digest = saved["view_sha256"]
                if digest not in wanted:
                    continue
                row, view = wanted.pop(digest), saved["view"]
                require(sha(view) == digest and sorted(a["action_key"] for a in view["actions"]) == sorted(row["legal_action_keys"]), "旧缓存读回摘要或合法根不同")
                tags, facts = public_tags(row, view)
                for tag in tags:
                    key = (row["window_key"]["round_no"], row["window_key"]["trigger_seq"])
                    if tag not in first or key < first[tag]["key"]:
                        first[tag] = {"key": key, "row": row, "sha": digest, "facts": facts}
        scanned.append({"root_id": root_id, "table_index": index, "public_rows_read": row_count,
            "public_tags_present": sorted(first), "closed_metadata_only": True})
        for tag in BUCKETS:
            if tag not in first:
                continue
            found, row = first[tag], first[tag]["row"]
            case = {"label": f"t191-public:{root_id}:{tag}", "root_id": root_id,
                "window_key": row["window_key"], "observation": row["observation"],
                "legal_action_keys": sorted(row["legal_action_keys"]), "view_sha256": found["sha"], "classes": [tag]}
            candidates.append({"case": case, "focal_seat": 0, "composition": composition,
                "source_closure": str(closure_path), "selection": "原S02座位0/arm0，母源升序、该公共类别首次窗口；不读后继积分或候选评分",
                "selection_public_facts": found["facts"], "source_public_rows": str(decision_path),
                "source_public_views": str(views_path)})
        # 先取得10不同母来源候选再完成固定类别选择；少数未覆盖类别作为缺口保留。
        if len({t["composition"]["root_id"] for t in candidates}) >= 10:
            break
    selected, used = [], set()
    for bucket in BUCKETS:
        options = [t for t in candidates if t["case"]["classes"] == [bucket] and t["composition"]["root_id"] not in used]
        if options:
            selected.append(options[0])
            used.add(options[0]["composition"]["root_id"])
    for target in candidates:
        if len(selected) >= 10:
            break
        if target["composition"]["root_id"] not in used:
            selected.append(target)
            used.add(target["composition"]["root_id"])
    present = {tag for t in selected for tag in t["case"]["classes"]}
    missing = [tag for tag in BUCKETS if tag not in present]
    require(all(pin(Path(p)) == expected for p, expected in files.items()), "来源冻结期间漂移")
    result = {"schema": "t191-public-source-supplement/1", "targets": selected, "files": files,
        "selection_uses_outcomes_or_candidate_scores": False, "candidate_successor_scores_read": False,
        "selection_input": "T186既有已闭S02座位0 arm0完整公开focal-decisions和捕获图；closure仅complete/root/rotation",
        "excluded_mother_sources": sorted(excluded), "table_order": "root_id升序、仅物理座位0 arm0",
        "window_order": "单局号和trigger_seq升序，每母每类首次",
        "bucket_order": list(BUCKETS), "public_tag_rules": {
            "same_speed": "直接wait根普通/七对向听相同，正公开容量码并集严格多于任一单路，按物理码去重",
            "early": "公开remaining_tile_count>=60", "late": "公开remaining_tile_count<=30",
            "no_immediate_upgrade": "可合法Hu且至少一个正常下一摸支付见证，全部支付不高于当前Hu；更远升级未知",
            "immediate_upgrade": "可合法Hu且正常下一摸至少一条支付严格更高；不是自然实现概率"},
        "maximum_tables": args.maximum_tables, "maximum_uncompressed_view_bytes": args.maximum_uncompressed_view_bytes,
        "actual_uncompressed_view_bytes": view_bytes, "scanned_tables": scanned,
        "actual_supplement_sources": len(selected), "missing_to_requested_10": 10 - len(selected),
        "uncovered_public_buckets": missing, "old_confirmed_sources_are_new_independent_confirmation": False,
        "new_scores_worlds_single_hands_complete_tables_model_calls_HTTP": 0,
        "elapsed_monotonic_seconds": time.monotonic() - started,
        "strength_deadline_or_release_admission": False}
    save(Path(args.output).resolve(), result)
    print(json.dumps({"sources": len(selected), "missing": 10 - len(selected), "uncovered_public_buckets": missing,
        "tables_read": len(scanned), "uncompressed_view_bytes": view_bytes, "actual_new_business_calls": 0}))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", required=True)
    p.add_argument("--maximum-tables", type=int, default=26)
    p.add_argument("--maximum-uncompressed-view-bytes", type=int, default=1073741824)
    main(p.parse_args())
