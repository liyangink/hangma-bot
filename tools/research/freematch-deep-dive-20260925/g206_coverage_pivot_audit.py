#!/usr/bin/env python3
"""G206：对已冻结的多白量具与强手宽面发现集作覆盖算账。

本程序只读取已有机读证据，不重判动作、不读取未来牌墙，也不把条件
胡分或强手选择解释为候选净收益。不同来源母体分别报告，不合并率。
"""

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


HERE = Path(__file__).resolve().parent
EVIDENCE = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence')
SOURCES = {
    "g203": _project_file(_PROJECT_ROOT, EVIDENCE / "g203-future-catch-play-reach-20260929/result.json"),
    "g204": _project_file(_PROJECT_ROOT, EVIDENCE / "g204-multiwhite-two-action-claim-20260929/result.json"),
    "g87": _project_file(_PROJECT_ROOT, EVIDENCE / "g87-post-claim-score-trace-20260928/result.json"),
    "g94": _project_file(_PROJECT_ROOT, EVIDENCE / "g94-cumulative-free-reaudit-20260928/result.json"),
    "g193": _project_file(_PROJECT_ROOT, EVIDENCE / "g193-early-shape-development-20260929/analysis.json"),
}
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g206-coverage-pivot-20260929/result.json')
FULL_TABLES_91_ROOMS = 909  # G203 源自冻结的 91 房完整桌审计。
STRONG_ROOMS_TABLES = 310  # G61/G94 的 31 个去重强手房，每房十张完整桌。
TARGET_GAIN_PER_TABLE = 2.0  # 已冻结的全桌开发/确认目标，仅用于覆盖算术。


def distinct(rows: list[dict]) -> dict[str, int]:
    """对窗口按官方房、完整桌和单局去重，避免同局重复计数。"""

    return {
        "windows": len(rows),
        "rooms": len({row["room_id"] for row in rows}),
        "tables": len({row["game_id"] for row in rows}),
        "hands": len({(row["game_id"], row["round_no"]) for row in rows}),
    }


def main() -> None:
    """输出来源绑定的描述性覆盖，不执行策略或发布判决。"""

    if OUT.exists():
        raise FileExistsError("G206 已冻结结果存在，拒绝覆盖")
    source_sha = {key: sha256(path.read_bytes()).hexdigest()
                  for key, path in SOURCES.items()}
    source = {key: json.loads(path.read_text(encoding="utf-8"))
              for key, path in SOURCES.items()}
    g203, g204, g87, g94, g193 = (source[key]
                                   for key in ("g203", "g204", "g87", "g94", "g193"))
    rows = g204["rows"]
    if (len(g203["source_rooms"]) != 91
            or g203["main_summary"]["complete"] != 29
            or g204["draw_complete"] != 29
            or g204["claim_complete"] != 29
            or len(rows) != 29
            or g193["complete_tables"] != 1024):
        raise ValueError("冻结父代/量具/开发桌身份发生漂移")
    if len({(row["game_id"], row["round_no"], row["trigger_seq"])
            for row in rows}) != len(rows):
        raise ValueError("G204 窗口身份重复")

    robust = []
    for row in rows:
        deltas = row["alternate_minus_parent"]
        if set(deltas) != {"0.5", "1.0"}:
            raise ValueError("两种再摸权重不完整")
        if all(deltas[weight]["total"] > 1e-8
               and deltas[weight]["special"] >= -1e-8
               for weight in ("0.5", "1.0")):
            robust.append(row)

    # 阈值为事后敏感性描述，不是候选触发规则或统计显著性判据。
    by_delta = {}
    for label, threshold in (("positive", 0.0), ("gt_0_1", 0.1),
                             ("gt_0_25", 0.25), ("gt_0_5", 0.5),
                             ("gt_1", 1.0)):
        selected = [row for row in robust
                    if min(row["alternate_minus_parent"][weight]["total"]
                           for weight in ("0.5", "1.0")) > threshold]
        counts = distinct(selected)
        touched = counts["tables"]
        by_delta[label] = {
            **counts,
            "fraction_of_909_parent_tables": touched / FULL_TABLES_91_ROOMS,
            "conditional_gain_required_if_effect_only_on_these_tables":
                None if touched == 0 else
                TARGET_GAIN_PER_TABLE * FULL_TABLES_91_ROOMS / touched,
        }

    wide = [row for row in g87["rows"]
            if row["strong_ordinary_codes_delta"] > 0
            and row["strong_ordinary_capacity_delta"] > 0]
    if (len(wide) != g94["wide_windows"]["windows"]
            or len({row["room"] for row in wide}) != 31
            or len({(row["game_id"], row["round_no"]) for row in wide})
            != g94["wide_windows"]["distinct_hands"]):
        raise ValueError("G87/G94 强手宽面发现集不一致")
    strong_tables = len({row["game_id"] for row in wide})

    result = {
        "schema": "g206-coverage-pivot-audit/1",
        "source_sha256": source_sha,
        "script_sha256": sha256(Path(__file__).read_bytes()).hexdigest(),
        "parent_multiwhite": {
            "source_rooms": 91,
            "source_complete_tables": FULL_TABLES_91_ROOMS,
            "all_conflict": distinct(rows),
            "robust_positive_no_highfan_decline": by_delta,
        },
        "strong_ordinary_width_discovery": {
            "source_rooms": 31,
            "source_complete_tables": STRONG_ROOMS_TABLES,
            "windows": len(wide),
            "hands": len({(row["game_id"], row["round_no"]) for row in wide}),
            "tables": strong_tables,
            "table_fraction": strong_tables / STRONG_ROOMS_TABLES,
            "white_zero_windows": sum(row["white_before"] == 0 for row in wide),
        },
        "g193_development": {
            "complete_tables_both_arms": g193["complete_tables"],
            "development_gate_pass": g193["development_gate_pass"],
            "means_delta_per_complete_table": g193["means_delta_per_complete_table"],
        },
        "boundary": (
            "G204 为官方父代近听多白窗口的条件价值，不是上线候选收益；"
            "阈值是事后覆盖敏感性而非新门槛。若仅这些桌受影响，所需条件"
            "增益是算术恒等式而非可达到的上界。G87/G94 是强手选动作的"
            "不同母体，不能把其桌覆盖当成我方候选触发率或净收益。"
        ),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True,
                              indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"g204": by_delta,
                      "strong_tables": strong_tables},
                     ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
