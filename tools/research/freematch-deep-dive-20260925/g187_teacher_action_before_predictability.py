#!/usr/bin/env python3
"""G187：G186 全桌教师的结果分解与留根行动前可预测性检验。"""

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

from collections import defaultdict
import hashlib
import json
from pathlib import Path

import numpy as np

import g186_multi_action_full_table_teacher as teacher


HERE = Path(__file__).resolve().parent
PLAN = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/G187-TEACHER-ACTION-BEFORE-PREDICTABILITY-PREREG-2026-09-28.md')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g187-teacher-action-before-predictability-20260928/result.json')
LABEL_FIELDS = ("plain_self_win_delta", "special_self_win_delta",
                "other_win_delta", "draw_delta")
FEATURE_NAMES = (
    "r18_score_delta", "standard_code_delta", "standard_capacity_delta",
    "seven_shanten_improvement", "seven_capacity_delta", "seven_missing",
    "combined_shanten_improvement", "combined_capacity_delta", "combined_missing",
    "white_before", "wall_remaining", "mix_m", "white_x_seven_capacity",
)


def sha(path: Path) -> str:
    """结果绑定事前模型、教师和来源。"""

    return hashlib.sha256(path.read_bytes()).hexdigest()


def capacity(items: dict | None) -> int | None:
    """公开未见物理容量不是未来牌墙概率。"""

    return None if items is None else sum(items.values())


def features(row: dict, action: str) -> list[float]:
    """只由行动前规则事实构造备选相对父代的固定特征。"""

    identity = row["window_identity"]
    base = row["action_before_facts"][identity["parent_action"]]
    alt = row["action_before_facts"][action]
    def delta(name: str) -> tuple[float, float]:
        old, new = capacity(base[name]), capacity(alt[name])
        return (0.0, 1.0) if old is None or new is None else (float(new - old), 0.0)
    seven_cap, seven_missing = delta("seven_pairs_useful")
    combined_cap, combined_missing = delta("combined_useful")
    standard_old = base["standard_useful"]
    standard_new = alt["standard_useful"]
    if standard_old is None or standard_new is None:
        raise ValueError("G187 目标动作缺普通型进张事实")
    def improvement(name: str) -> float:
        old, new = base[name], alt[name]
        return 0.0 if old is None or new is None else float(old - new)
    white = row["score_facts"]["white_before"]
    wall = row["score_facts"]["remaining_tile_count"]
    return [
        float(alt["r18_score"] - base["r18_score"]),
        float(len(standard_new) - len(standard_old)),
        float(sum(standard_new.values()) - sum(standard_old.values())),
        improvement("seven_pairs_shanten"), seven_cap, seven_missing,
        improvement("combined_shanten"), combined_cap, combined_missing,
        float(white), float(wall), float(identity["mix"] == "M"),
        float(white) * seven_cap,
    ]


def ridge_predict(train_x: np.ndarray, train_y: np.ndarray,
                  test_x: np.ndarray) -> np.ndarray:
    """仅训练根标准化；截距不惩罚，其余特征固定 L2=20。"""

    means = train_x.mean(axis=0)
    scales = train_x.std(axis=0)
    scales[scales < 1e-12] = 1.0
    x = (train_x - means) / scales
    test = (test_x - means) / scales
    design = np.column_stack((np.ones(len(x)), x))
    penalty = np.diag([0.0] + [20.0] * x.shape[1])
    coefficients = np.linalg.solve(design.T @ design + penalty,
                                   design.T @ train_y)
    return np.column_stack((np.ones(len(test)), test)) @ coefficients


def main() -> None:
    """只在 80 窗完成后读教师，留根预测后保存不可覆盖结果。"""

    if OUT.exists():
        raise FileExistsError("G187 结果已存在，拒绝覆盖")
    source_dir = teacher.OUT
    manifest_path = source_dir / "manifest.json"
    rows_path = source_dir / "rows.jsonl"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if (manifest.get("schema") != "g186-multi-action-full-table-teacher-manifest/1"
            or manifest.get("development_windows") != 80
            or manifest.get("samples") != list(teacher.SAMPLES)
            or manifest["source_sha256"]["script"] != sha(Path(teacher.__file__))
            or manifest["source_sha256"]["prereg"] != sha(teacher.PLAN)):
        raise ValueError("G187 教师清单、脚本或事前方案漂移")
    rows = [json.loads(line) for line in rows_path.read_text(encoding="utf-8").splitlines()]
    if len(rows) != 80:
        raise ValueError("G187 不能在 G186 开发窗未完成时读结果")
    selection = json.loads((teacher.source.OUT / "selection.json").read_text(encoding="utf-8"))
    items = [item for item in selection["selected"] if item["split"] == "development"]
    examples = []
    by_window = defaultdict(list)
    for index, (row, item) in enumerate(zip(rows, items, strict=True)):
        identity = {key: item[key] for key in
                    ("mix", "root_index", "focal_seat", "round_no",
                     "observation_sha256", "parent_action")}
        if row["window_identity"] != identity:
            raise ValueError("G187 教师行不等于 G183 开发来源准确前缀")
        worlds = row["paired_worlds"]
        if [world["sample_key"] for world in worlds] != list(teacher.SAMPLES):
            raise ValueError("G187 教师同世界样本缺失或顺序漂移")
        actions = [identity["parent_action"], *row["alternate_actions"]]
        if not (2 <= len(actions) <= 4) or len(actions) != len(set(actions)):
            raise ValueError("G187 教师合法动作数量或去重不符")
        for world in worlds:
            if set(world["outcomes"]) != set(actions):
                raise ValueError("G187 同世界动作臂不齐")
            if world["focal_table_delta_by_action"][identity["parent_action"]] != 0:
                raise ValueError("G187 父代相对分非零")
            for action in actions:
                outcome = world["outcomes"][action]
                if len(outcome["hands"]) != 8:
                    raise ValueError("G187 续打不是完整八局桌")
                accounting = outcome["account"]
                if sum(accounting[name] for name in LABEL_FIELDS) != accounting["focal_table_delta"]:
                    raise ValueError("G187 互斥收支分量不守恒")
                if (accounting["focal_table_delta"] -
                    world["outcomes"][identity["parent_action"]]["account"]["focal_table_delta"]
                        != world["focal_table_delta_by_action"][action]):
                    raise ValueError("G187 同世界配对净分不守恒")
        for action in row["alternate_actions"]:
            label = float(np.mean([world["focal_table_delta_by_action"][action]
                                   for world in worlds]))
            components = {name: float(np.mean([
                world["outcomes"][action]["account"][name] -
                world["outcomes"][identity["parent_action"]]["account"][name]
                for world in worlds])) for name in LABEL_FIELDS}
            if abs(sum(components.values()) - label) > 1e-8:
                raise ValueError("G187 教师窗口分量均值不守恒")
            example = {"window_index": index, "identity": identity, "action": action,
                       "features": features(row, action), "mean_delta": label,
                       "components": components,
                       "world_deltas": [world["focal_table_delta_by_action"][action]
                                        for world in worlds]}
            examples.append(example)
            by_window[index].append(example)
    roots = sorted({example["identity"]["root_index"] for example in examples})
    predictions = {}
    for root in roots:
        train = [example for example in examples
                 if example["identity"]["root_index"] != root]
        test = [example for example in examples
                if example["identity"]["root_index"] == root]
        pred = ridge_predict(np.array([entry["features"] for entry in train], dtype=float),
                             np.array([entry["mean_delta"] for entry in train], dtype=float),
                             np.array([entry["features"] for entry in test], dtype=float))
        predictions.update({(entry["window_index"], entry["action"]): float(value)
                            for entry, value in zip(test, pred, strict=True)})
    selected = []
    for index, row in enumerate(rows):
        ranked = sorted(by_window[index],
                        key=lambda entry: (-predictions[(index, entry["action"])],
                                           entry["action"]))
        winner = ranked[0]
        choose = winner if predictions[(index, winner["action"])] > 0 else None
        selected.append({"window_index": index,
                         "identity": row["window_identity"],
                         "chosen_action": choose["action"] if choose else row["window_identity"]["parent_action"],
                         "predicted_delta": predictions[(index, winner["action"])],
                         "observed_mean_delta": choose["mean_delta"] if choose else 0.0,
                         "observed_components": choose["components"] if choose else
                         {name: 0.0 for name in LABEL_FIELDS},
                         "oracle_best_mean_delta": max(0.0, *(entry["mean_delta"]
                                                               for entry in by_window[index])),
                         "alternate_count": len(by_window[index])})
    summary = {}
    for mix in ("H", "M", "all"):
        group = [row for row in selected if mix == "all" or row["identity"]["mix"] == mix]
        by_root = defaultdict(list)
        for row in group:
            by_root[row["identity"]["root_index"]].append(row["observed_mean_delta"])
        values = np.array([np.mean(by_root[root]) for root in sorted(by_root)], dtype=float)
        rng = np.random.default_rng(20260928187 + {"H": 0, "M": 1, "all": 2}[mix])
        boot = np.mean(rng.choice(values, size=(4000, len(values)), replace=True), axis=1)
        summary[mix] = {
            "windows": len(group), "roots": len(values),
            "chosen_alternates": sum(row["chosen_action"] != row["identity"]["parent_action"]
                                     for row in group),
            "window_mean_delta": float(np.mean([row["observed_mean_delta"] for row in group])),
            "root_equal_mean_delta": float(values.mean()),
            "root_bootstrap_95_descriptive": [float(np.quantile(boot, 0.025)),
                                               float(np.quantile(boot, 0.975))],
            "oracle_best_mean_delta": float(np.mean([
                row["oracle_best_mean_delta"] for row in group])),
            "components": {name: float(np.mean([
                row["observed_components"][name] for row in group]))
                           for name in LABEL_FIELDS},
        }
    result = {"schema": "g187-teacher-action-before-predictability/1",
              "source_sha256": {"plan": sha(PLAN), "script": sha(Path(__file__)),
                                "g186_manifest": sha(manifest_path),
                                "g186_rows": sha(rows_path),
                                "g183_selection": sha(teacher.source.OUT / "selection.json")},
              "feature_names": list(FEATURE_NAMES), "ridge_alpha": 20.0,
              "leave_root_out": True, "related_worlds_per_window": len(teacher.SAMPLES),
              "development_windows": len(rows), "alternative_action_examples": len(examples),
              "summary": summary, "selected": selected, "examples": examples,
              "boundary": "开发来源同世界单窗强制动作的留根诊断，非候选全桌政策收益；锁定窗未开。"}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                   encoding="utf-8")
    print(json.dumps({"windows": len(rows), "examples": len(examples),
                      "summary": summary}, ensure_ascii=False, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
