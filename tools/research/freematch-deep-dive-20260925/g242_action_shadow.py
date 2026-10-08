#!/usr/bin/env python3
"""G242 事后只读：把冻结预测器投到 G224 合法备选及 G233 压力题。"""

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

from collections import Counter
from hashlib import sha256
import json
from pathlib import Path

import numpy as np

import g233_inversion_same_world_branch as pressure
import g242_competing_risk_calibration as model


HERE = Path(__file__).resolve().parent
G224 = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g224-g223-vector-replay-20260929')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g242-competing-risk-calibration-20260929/action-shadow.json')


def digest(path: Path) -> str:
    """锁旧观察、诊断权重与脚本原文字节。"""
    return sha256(path.read_bytes()).hexdigest()


def probability(option: dict, observation: dict, weights: np.ndarray) -> list[float]:
    """只用玩家可见观察和该生产合法备选事实计算固定类别概率。"""
    key = option["action"]
    row = {
        "remaining_tile_count": observation["remaining_tile_count"],
        "standard_shanten_after": option["standard_shanten_after"],
        "seven_pairs_shanten_after": option["seven_pairs_shanten_after"],
        "white_before": option["white_after"] + int(key == "discard:白"),
        "meld_count": len(observation["melds"][observation["seat"]]),
        "standard_useful_type_count": option["standard_width"][0],
        "standard_useful_public_capacity": option["standard_width"][1],
        "chosen_action": key,
    }
    return model.probabilities(np.asarray([model.features(row, full=True)]),
                               weights)[0].tolist()


def main() -> None:
    """逐阶段验 G224 摘要，保存全部固定压力题及宽面覆盖计数。"""
    if OUT.exists():
        raise FileExistsError(OUT)
    model_result = json.loads(model.OUT.read_text(encoding="utf-8"))
    weights = np.asarray(model_result["full_coefficients"], dtype=np.float64)
    source = json.loads((_project_file(_PROJECT_ROOT, G224 / "result.json")).read_text(encoding="utf-8"))
    targets = {(row["table_id"], row["round_no"], row["snapshot_seq"]): row
               for row in pressure.selected()}
    if len(targets) != 9:
        raise ValueError("G242 历史压力题身份不唯一")
    counts = {mix: Counter() for mix in ("H", "M")}
    cases = []
    for filename, expected_hash in sorted(source["stage_sha256"].items()):
        path = _project_file(_PROJECT_ROOT, G224 / "stages" / filename)
        if digest(path) != expected_hash:
            raise ValueError("G242 G224 来源阶段摘要不符")
        stage = json.loads(path.read_text(encoding="utf-8"))
        mix = stage["mix"]
        for root in stage["roots"]:
            options = {option["action"]: option for option in root["same_layer_options"]}
            parent = options[root["root_action"]]
            parent_p = probability(parent, root["observation"], weights)
            for alternate in options.values():
                code = alternate["action"].split(":", 1)[1]
                if (alternate is parent or len(code) != 2
                        or code[0] not in "123456789" or code[1] not in "wbt"
                        or alternate["standard_width"][0] <= parent["standard_width"][0]
                        or alternate["standard_width"][1] <= parent["standard_width"][1]):
                    continue
                counts[mix]["strict_wider_numeric_pairs"] += 1
                delta = probability(alternate, root["observation"], weights)[1] - parent_p[1]
                if delta > 0:
                    counts[mix]["positive_ownwin_pairs"] += 1
                if delta > 0.001:
                    counts[mix]["positive_ownwin_over_0p001"] += 1
                if delta > 0.005:
                    counts[mix]["positive_ownwin_over_0p005"] += 1
            observation = root["observation"]
            target = targets.get((root["table_id"], root["round_no"],
                                  observation["snapshot_seq"]))
            if target is None:
                continue
            alternate = options[target["representative_inversion"]["action"]]
            alternate_p = probability(alternate, observation, weights)
            cases.append({"mix": mix, "root_index": target["root_index"],
                          "table_id": target["table_id"],
                          "round_no": target["round_no"],
                          "parent_action": target["parent_action"],
                          "alternate_action": alternate["action"],
                          "parent_probability": parent_p,
                          "alternate_probability": alternate_p,
                          "alternate_minus_parent_ownwin_before_third": (
                              alternate_p[1] - parent_p[1])})
    if len(cases) != len(targets):
        raise ValueError("G242 旧压力题未完整命中")
    value = {
        "schema": "g242-action-shadow/1",
        "model_result_sha256": digest(model.OUT),
        "g224_result_sha256": digest(_project_file(_PROJECT_ROOT, G224 / "result.json")),
        "script_sha256": digest(Path(__file__)),
        "class_order": model_result["class_order"],
        "strict_wider_numeric_by_mix": {mix: dict(counts[mix]) for mix in counts},
        "known_pressure_cases": sorted(cases, key=lambda row: (
            row["mix"], row["root_index"])),
        "boundary": "已看 G224/G233 的事后机制投影；非改弃因果标签、不可调阈值。",
    }
    OUT.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2)
                   + "\n", encoding="utf-8")
    print(json.dumps(value["strict_wider_numeric_by_mix"],
                     ensure_ascii=False, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
