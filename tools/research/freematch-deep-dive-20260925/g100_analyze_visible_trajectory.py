#!/usr/bin/env python3
"""G100：从已恒等的可见轨迹按窗口/对手池计算路线入口与终局交叉。"""

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
import gzip
import hashlib
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
SOURCE = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g96-wider-discard-branch-expansion-20260928/result.json')
TRAJECTORY = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g100-g96-paired-visible-trajectory-20260928/result.json.gz')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g100-g96-paired-visible-trajectory-20260928/analysis.json')


def sha(path: Path) -> str:
    """记录本分析绑定的原始证据身份。"""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def draw_discards(branch: dict) -> list[dict]:
    """只数真正的本人摸牌后弃牌，避免响应窗连续 `pass` 重复计入口。"""
    return [row for row in branch["focal_trajectory"]
            if row["window"]["phase"] == "draw" and
            row["action_key"].startswith("discard:")]


def first_entry(branch: dict, field: str) -> int | None:
    """返回根弃牌记为 0 的本人正常摸打序号；未到达保持 None。"""
    return next((index for index, row in enumerate(draw_discards(branch))
                 if row[field] is not None and row[field] > 0), None)


def entry_counts(counter: Counter, label: str, parent: int | None,
                 alternate: int | None) -> None:
    """同一隐藏世界配对内做入口差，不把多次 pass 算成多次机会。"""
    if parent is None and alternate is None:
        counter[label + "_neither"] += 1
    elif parent is None:
        counter[label + "_alternate_only"] += 1
    elif alternate is None:
        counter[label + "_parent_only"] += 1
    else:
        counter[label + "_both"] += 1
        if alternate < parent:
            counter[label + "_alternate_earlier"] += 1
        elif parent < alternate:
            counter[label + "_parent_earlier"] += 1
        else:
            counter[label + "_same_index"] += 1


def main() -> None:
    """独立加载 G96/G100，聚合九世界相关样本并写不可覆盖摘要。"""
    if OUT.exists():
        raise FileExistsError("G100 分析已存在，拒绝覆盖")
    g96 = json.loads(SOURCE.read_text(encoding="utf-8"))
    traced = json.loads(gzip.decompress(TRAJECTORY.read_bytes()))
    if (g96["schema"] != "g96-wider-discard-branch-expansion/1" or
            traced["schema"] != "g100-g96-paired-visible-trajectory/1" or
            traced["input_sha256"]["g96"] != sha(SOURCE)):
        raise ValueError("G100 轨迹与 G96 来源身份不符")
    old = {(row["mix"], row["root_index"], row["focal_seat"]): row
           for row in g96["rows"] if row["status"] == "paired"}
    if len(old) != len(traced["rows"]):
        raise ValueError("G100 命中窗口数不符")
    pool = {mix: Counter() for mix in ("H", "M")}
    windows = []
    all_actions = Counter()
    for row in traced["rows"]:
        key = (row["mix"], row["root_index"], row["focal_seat"])
        source = old.get(key)
        if (source is None or row["table_id"] != source["table_id"] or
                row["target_window"] != source["target_window"] or
                len(row["pairs"]) != len(source["world_pairs"])):
            raise ValueError("G100 轨迹窗口或九世界身份不符")
        c = Counter()
        for traced_pair, original in zip(row["pairs"], source["world_pairs"]):
            if traced_pair["sample_key"] != original["sample_key"]:
                raise ValueError("G100 隐藏样本键漂移")
            for arm in ("parent", "alternate"):
                branch = traced_pair[arm]
                for record in branch["focal_trajectory"]:
                    all_actions["focal_decisions"] += 1
                    all_actions["white_discards"] += record["action_key"] == "discard:白"
                    if (record["one_draw_value_coverage"] not in (None, "complete")):
                        all_actions["incomplete_value_facts"] += 1
            if traced_pair["sample_key"] == "historical":
                continue
            c["resampled_pairs"] += 1
            delta = original["focal_delta_alt_minus_parent"]
            c["focal_delta_sum"] += delta
            c["positive_pairs"] += delta > 0
            c["negative_pairs"] += delta < 0
            c["zero_pairs"] += delta == 0
            for name, field in (("ordinary", "one_draw_win_routes"),
                                ("highfan", "one_draw_highfan_routes")):
                parent = first_entry(traced_pair["parent"], field)
                alternate = first_entry(traced_pair["alternate"], field)
                entry_counts(c, name, parent, alternate)
                c[name + "_parent_reached"] += parent is not None
                c[name + "_alternate_reached"] += alternate is not None
            c["parent_draw_discards"] += len(draw_discards(traced_pair["parent"]))
            c["alternate_draw_discards"] += len(draw_discards(traced_pair["alternate"]))
            c["special_self_to_plain"] += (
                original["parent_class"] == "special_self_win" and
                original["alternate_class"] == "plain_self_win")
            c["special_self_to_other"] += (
                original["parent_class"] == "special_self_win" and
                original["alternate_class"] == "other_win")
        if c["resampled_pairs"] != 8:
            raise ValueError("G100 每窗重采样世界数不等于八")
        pool[row["mix"]].update(c)
        windows.append({"mix": row["mix"], "root_index": row["root_index"],
                        "focal_seat": row["focal_seat"],
                        "white_before": row["white_before"],
                        "counts": dict(sorted(c.items()))})
    result = {"schema": "g100-visible-trajectory-analysis/1",
              "input_sha256": {"g96": sha(SOURCE), "trajectory": sha(TRAJECTORY),
                               "script": sha(Path(__file__))},
              "windows": windows,
              "pool_counts": {mix: dict(sorted(counts.items()))
                              for mix, counts in pool.items()},
              "all_actions": dict(sorted(all_actions.items())),
              "boundary": "入口只计本人正常摸牌后实际弃牌的生产一步胡路线；"
                          "已看 G96 结果，八世界同窗相关，不能用作候选拟合/晋级。"}
    OUT.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                   encoding="utf-8")
    print(json.dumps({"windows": len(windows),
                      "pool_counts": result["pool_counts"],
                      "all_actions": result["all_actions"]},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
