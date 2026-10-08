#!/usr/bin/env python3
"""G53 结果盲复核：自然缺口下降的路线差距，以及同层宽面入口覆盖。"""

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
G48 = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g48-cross-layer-natural-gap-reach-20260927/result.json')
G14 = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g14-white-reserve-frontier-20260927')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g53-route-competition-reach-20260927/result.json')


def sha(path: Path) -> str:
    """返回已冻结研究输入或程序的内容摘要。"""

    return hashlib.sha256(path.read_bytes()).hexdigest()


def scope(rows: list[dict]) -> dict[str, int]:
    """窗口与触达完整桌分开计数，避免把同桌多窗当独立样本。"""

    return {"windows": len(rows), "tables": len({row["game_id"] for row in rows}),
            "rooms": len({row["room_id"] for row in rows})}


def safely_close(row: dict) -> bool:
    """仅作入口计数；七对/综合向听不退、当前综合容量不减且父代分差≤10。"""

    return any(
        item["delta_seven_pairs_shanten"] is not None and
        item["delta_seven_pairs_shanten"] <= 0 and
        item["delta_combined_shanten"] <= 0 and
        item["delta_combined_useful_count"] is not None and
        item["delta_combined_useful_count"] >= 0 and
        item["parent_score_gap"] is not None and
        0 <= item["parent_score_gap"] <= 10
        for item in row["alternatives"]
    )


def main() -> None:
    """重用 G48/G14 冻结生产事实，不读后续事件或桌分。"""

    if OUT.exists():
        raise SystemExit("G53 结果已存在，拒绝覆盖")
    g48 = json.loads(G48.read_text(encoding="utf-8"))
    g14_result_path = _project_file(_PROJECT_ROOT, G14 / "result.json")
    g14_rows_path = _project_file(_PROJECT_ROOT, G14 / "rows.jsonl.gz")
    g14 = json.loads(g14_result_path.read_text(encoding="utf-8"))
    if (g48.get("outcome_blind") is not True or len(g48.get("rows") or []) != 318 or
            g14.get("outcome_blind") is not True or g14.get("rows") != 2134 or
            g14.get("rows_sha256") != sha(g14_rows_path) or
            g48.get("parent_source_sha256") != g14.get("parent_source_sha256")):
        raise ValueError("G48/G14 结果盲来源或逐窗摘要漂移")
    by_gap = {}
    for gap in sorted({row["parent_standard_shanten"] - row["parent_seven_pairs_shanten"]
                       for row in g48["rows"]}):
        subset = [row for row in g48["rows"] if row["parent_standard_shanten"] -
                  row["parent_seven_pairs_shanten"] == gap]
        by_gap[str(gap)] = {"all": scope(subset),
                            "seven_tenpai": scope([row for row in subset
                                                    if row["parent_seven_pairs_shanten"] == 0]),
                            "not_seven_tenpai": scope([row for row in subset
                                                        if row["parent_seven_pairs_shanten"] >= 1]),
                            "not_tenpai_safely_close": scope([row for row in subset
                                                                if row["parent_seven_pairs_shanten"] >= 1
                                                                and safely_close(row)])}
    with gzip.open(g14_rows_path, "rt", encoding="utf-8") as stream:
        rows = [json.loads(line) for line in stream]
    if len(rows) != 2134 or len({(row["game_id"], row["round_no"], row["trigger_seq"])
                                 for row in rows}) != len(rows):
        raise ValueError("G14 同层白板自然前沿逐窗重复或缺失")
    categories = {
        "ordinary_leads": [row for row in rows if row["parent_shape"]["seven_shanten"] is not None
                           and row["parent_shape"]["standard_shanten"] <
                           row["parent_shape"]["seven_shanten"]],
        "ordinary_ties_seven": [row for row in rows if row["parent_shape"]["seven_shanten"] is not None
                                and row["parent_shape"]["standard_shanten"] ==
                                row["parent_shape"]["seven_shanten"]],
        "seven_leads": [row for row in rows if row["parent_shape"]["seven_shanten"] is not None
                        and row["parent_shape"]["standard_shanten"] >
                        row["parent_shape"]["seven_shanten"]],
        "seven_unavailable": [row for row in rows if row["parent_shape"]["seven_shanten"] is None],
    }
    if sum(len(value) for value in categories.values()) != len(rows):
        raise ValueError("G14 目标路线分层未穷尽")
    static = {}
    for label, subset in categories.items():
        novel = [row for row in subset
                 if row["natural_wider_without_conventional_type_gain_count"] > 0]
        static[label] = {"all": scope(subset),
                         "width_without_conventional_type_gain": scope(novel),
                         "chosen_same_g10": sum(row["same_action_g10"] for row in subset),
                         "chosen_same_g11": sum(row["same_action_g11"] for row in subset)}
    output = {"schema": "g53-route-competition-reach/1", "outcome_blind": True,
              "g48_sha256": sha(G48), "g14_result_sha256": sha(g14_result_path),
              "g14_rows_sha256": sha(g14_rows_path),
              "script_sha256": sha(Path(__file__)),
              "lower_natural_need_by_parent_standard_minus_seven": by_gap,
              "same_stratum_natural_width_by_route": static,
              "boundary": "仅冻结父代动作前合法弃牌与生产牌形事实；旧静态机会非候选已执行行为，分差≤10 为描述带，未读未来或桌分。"}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(output, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                   encoding="utf-8")
    print(json.dumps({"lower_need": by_gap, "same_stratum": static},
                     ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
