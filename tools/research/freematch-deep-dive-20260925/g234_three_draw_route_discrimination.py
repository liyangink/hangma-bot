#!/usr/bin/env python3
"""G234：核三摸规则路线能否区分 G233 的高番取舍压力题。"""

from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/freematch-deep-dive-20260925'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

from hashlib import sha256
import json
from pathlib import Path
import time

import c31_action_layer_gap as c31
import g196_three_draw_competing_route_pilot as g196
import g219_two_draw_settlement_route as g219
import g223_visible_multi_action_route as g223
import g224_g223_vector_replay as g224
import g232_base_width_inversion as g232
import g233_inversion_same_world_branch as g233
import g87_post_claim_score_trace as g87
from hangma_bot.kernel.serialization import observation_from_json


HERE = Path(__file__).resolve().parent
PLAN = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/G234-THREE-DRAW-ROUTE-DISCRIMINATION-PREREG-2026-09-29.md')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g234-three-draw-route-discrimination-20260929')
MODES = ("restricted", "unrestricted")


def digest(path: Path) -> str:
    """绑定来源、脚本及结果字节。"""

    return sha256(path.read_bytes()).hexdigest()


def write_new(path: Path, value: dict) -> None:
    """原子落盘且不覆盖已有不同结果。"""

    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    if path.exists():
        if path.read_text(encoding="utf-8") != encoded:
            raise FileExistsError(path)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(encoded, encoding="utf-8")
    temp.replace(path)


def run_one(target: dict) -> dict:
    """从 G224 行动前观察逐合法根独立重建两种抓打资格包络。"""

    _, archived = g233.archived_root(target)
    observation = observation_from_json(archived["observation"])
    request = g87.request_for(observation)
    if (request.window_key.round_no != target["round_no"]
            or request.trigger_seq != target["snapshot_seq"]
            or request.observation.seat != target["seat"]
            or archived["root_action"] != target["parent_action"]):
        raise ValueError("G234 G224 行动前观察身份漂移")
    legal = {item.action_key: item for item in request.rules.legal_candidates}
    root_actions = (target["parent_action"],
                    target["representative_inversion"]["action"])
    for key in root_actions:
        if key not in legal or legal[key].facts is None:
            raise ValueError("G234 固定根动作不在生产合法集合")
    source_options = {item["action"]: item for item in archived["same_layer_options"]}
    for key in root_actions:
        fact = legal[key].facts
        saved = source_options[key]
        if (fact.standard_shanten_after != target["standard_shanten_after"]
                or saved["standard_width"] != [
                    sum(item.remaining_estimate > 0
                        for item in fact.standard_useful_tiles),
                    sum(item.remaining_estimate
                        for item in fact.standard_useful_tiles)]):
            raise ValueError("G234 普通型向听或逐码容量漂移")
    if (archived["root_shape"]["white_after"] != target["white_after"]
            or tuple(target["representative_inversion"]["width_gain"])
            != tuple(source_options[root_actions[1]]["standard_width"][i]
                     - source_options[root_actions[0]]["standard_width"][i]
                     for i in (0, 1))):
        raise ValueError("G234 白板数或宽度差漂移")
    output = {"schema": "g234-three-draw-route-window/1",
              "identity": {name: target[name] for name in (
                  "mix", "root_index", "start_seat", "table_id", "round_no",
                  "snapshot_seq", "seat", "white_after", "standard_shanten_after",
                  "parent_action")},
              "alternate_action": root_actions[1],
              "source_sha256": {
                  "g223_stage": digest(g223.stage_path(target["mix"],
                                                          target["root_index"],
                                                          target["start_seat"])),
                  "g224_stage": digest(g224.stage_path(target["mix"],
                                                          target["root_index"],
                                                          target["start_seat"])),
              },
              "modes": {}, "status": "complete"}
    try:
        for mode in MODES:
            arms = {}
            for key in root_actions:
                started = time.perf_counter()
                search = g196.RouteSearch(observation, c31.RULE_CONFIG, key)
                g219.first_hu_parity(search, legal[key], observation.seat)
                value = search.evaluate(restricted=(mode == "restricted"))
                arms[key] = {
                    "value": value.json(),
                    "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
                    "legal_leaf_count": search.legal_leaf_count,
                    "win_split_count": search.win_split_count,
                    "third_ready_count": search.third_ready_count,
                }
            base = arms[root_actions[0]]["value"]
            alternative = arms[root_actions[1]]["value"]
            delta = {name: round(alternative[name] - base[name], 9)
                     for name in ("plain", "special", "depth1", "depth2",
                                  "depth3", "total")}
            if abs(delta["plain"] + delta["special"] - delta["total"]) > 1e-8:
                raise ValueError("G234 三摸普通／高番分量不守恒")
            output["modes"][mode] = {"arms": arms, "alternate_minus_parent": delta}
    except (g196.RouteLimitExceeded, ValueError) as error:
        output["status"] = "abstained"
        output["reason"] = type(error).__name__ + ": " + str(error)
        output.pop("modes")
    return output


def summarize(rows: list[dict]) -> dict:
    """只报告结构判别与覆盖，不拿已看 G233 世界训练权重。"""

    by_mix = {}
    for mix in ("H", "M"):
        group = [row for row in rows if row["identity"]["mix"] == mix]
        complete = [row for row in group if row["status"] == "complete"]
        by_mix[mix] = {
            "windows": len(group), "complete": len(complete),
            "abstained": len(group) - len(complete),
            "special_delta_negative_both_modes": sum(all(
                row["modes"][mode]["alternate_minus_parent"]["special"] < -1e-9
                for mode in MODES) for row in complete),
            "plain_delta_positive_both_modes": sum(all(
                row["modes"][mode]["alternate_minus_parent"]["plain"] > 1e-9
                for mode in MODES) for row in complete),
        }
    return by_mix


def main() -> None:
    """固定九窗全部完成后才写汇总；逐窗结果允许断点恢复。"""

    targets = g233.selected()
    if len(targets) != 9:
        raise ValueError("G233 冻结九窗来源漂移")
    manifest = {
        "schema": "g234-three-draw-route-manifest/1",
        "selection": [{name: target[name] for name in (
            "mix", "root_index", "start_seat", "table_id", "round_no",
            "snapshot_seq", "seat", "white_after", "standard_shanten_after",
            "parent_action")} | {
                "alternate_action": target["representative_inversion"]["action"]}
            for target in targets],
        "modes": list(MODES),
        "source_sha256": {
            "prereg": digest(PLAN), "script": digest(Path(__file__)),
            "g232_result": digest(g232.OUT),
            "g233_manifest": digest(g233.OUT / "manifest.json"),
            "g196_search": digest(Path(g196.__file__)),
            "g219_parity": digest(Path(g219.__file__)),
            "g224_result": digest(g224.OUT / "result.json"),
            "production_rules": digest(_project_file(_PROJECT_ROOT, HERE.parents[1] /
                                       "src/hangma_bot/hangma/engine.py")),
        },
        "boundary": "九个已看行动前压力窗的三摸公开容量条件结构值；非赛事概率、候选或收益确认。",
    }
    write_new(_project_file(_PROJECT_ROOT, OUT / "manifest.json"), manifest)
    for index, target in enumerate(targets, 1):
        path = _project_file(_PROJECT_ROOT, OUT / "windows" / f"window-{index:02d}.json")
        if path.exists():
            row = json.loads(path.read_text(encoding="utf-8"))
            if (row["identity"]["mix"], row["identity"]["root_index"],
                    row["alternate_action"]) != (
                    target["mix"], target["root_index"],
                    target["representative_inversion"]["action"]):
                raise ValueError("G234 已有窗口身份漂移")
            continue
        row = run_one(target)
        write_new(path, row)
        print(json.dumps({"completed_windows": index, "mix": target["mix"],
                          "root": target["root_index"], "status": row["status"]},
                         ensure_ascii=False), flush=True)
    if (_project_file(_PROJECT_ROOT, OUT / "result.json")).exists():
        raise FileExistsError("G234 汇总已存在，拒绝覆盖")
    paths = [_project_file(_PROJECT_ROOT, OUT / "windows" / f"window-{index:02d}.json")
             for index in range(1, len(targets) + 1)]
    rows = [json.loads(path.read_text(encoding="utf-8")) for path in paths]
    result = {"schema": "g234-three-draw-route-result/1",
              "manifest_sha256": digest(_project_file(_PROJECT_ROOT, OUT / "manifest.json")),
              "window_sha256": {path.name: digest(path) for path in paths},
              "by_mix": summarize(rows), "windows": len(rows),
              "boundary": manifest["boundary"]}
    write_new(_project_file(_PROJECT_ROOT, OUT / "result.json"), result)
    print(json.dumps({"status": "complete", "by_mix": result["by_mix"]},
                     ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
