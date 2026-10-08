#!/usr/bin/env python3
"""G192：结果盲父代表中三向听自然宽面冲突的覆盖与评分来源。"""

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

from collections import Counter, defaultdict
from hashlib import sha256
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
SOURCE = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g126-all-draw-natural-width-exposure-20260928')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g192-three-shanten-exposure-20260929/result.json')
HONORS = frozenset("东南西北中发")


def digest(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def aggregate(rows: list[dict]) -> dict:
    """窗口不是独立样本；单列不同父代表桌与池×牌山根。"""
    components = ("base_score", "river_part", "risk_part", "style_part",
                  "wealth_part", "wealth_discard_part", "hu_baotou_overlay")
    return {
        "windows": len(rows),
        "tables": len({(row["mix"], row["root_index"], row["focal_seat"])
                       for row in rows}),
        "pool_roots": len({(row["mix"], row["root_index"]) for row in rows}),
        "white_counts": dict(sorted(Counter(row["white_before"]
                                            for row in rows).items())),
        "mean_public_width_delta": (
            sum(row["width_delta"] for row in rows) / len(rows) if rows else None),
        "mean_public_capacity_delta": (
            sum(row["capacity_delta"] for row in rows) / len(rows) if rows else None),
        "score_gap_le_1": sum(row["score_gap"] <= 1 for row in rows),
        "component_parent_favors": {
            name: sum(row["components"].get(name, 0) > 0 for row in rows)
            for name in components},
        "component_alternate_favors": {
            name: sum(row["components"].get(name, 0) < 0 for row in rows)
            for name in components},
    }


def main() -> None:
    """只读 G126 行动前窗口；不打开备选续打或结算。"""
    if OUT.exists():
        raise FileExistsError("G192 结果已存在；拒绝覆盖")
    source_result = json.loads((_project_file(_PROJECT_ROOT, SOURCE / "result.json")).read_text(encoding="utf-8"))
    if (source_result.get("status") != "complete"
            or source_result.get("tables_completed") != 256
            or source_result.get("tables_planned") != 256):
        raise ValueError("G192 G126 父代完整桌不齐")
    rows = []
    table_count = 0
    target_count = 0
    for line in (_project_file(_PROJECT_ROOT, SOURCE / "rows.jsonl")).read_text(encoding="utf-8").splitlines():
        table = json.loads(line)
        if table["status"] != "complete" or table["hands"] != 8:
            raise ValueError("G192 来源桌未完成八个单局")
        table_count += 1
        for target in table["target_windows"]:
            target_count += 1
            facts = target["score_facts"]
            if not (facts["standard_shanten_after"] == 3
                    and facts["own_chi_peng_count"] == 0):
                continue
            parent, alternate = target["parent_action"], target["alternate_action"]
            if not (parent.startswith("discard:") and alternate.startswith("discard:")
                    and parent != "discard:白" and alternate != "discard:白"):
                raise ValueError("G192 三向听目标动作身份非法")
            components = facts["component_parent_minus_alternate"]
            score_gap = facts["parent_score_gap"]
            if abs(sum(components.values()) - score_gap) > 1e-8:
                raise ValueError("G192 父代评分分量不守恒")
            width, capacity = (facts["ordinary_codes_delta"],
                               facts["public_unseen_capacity_delta"])
            if width <= 0 or capacity <= 0:
                raise ValueError("G192 来源不是严格宽面备选")
            parent_code, alternate_code = parent[8:], alternate[8:]
            rows.append({
                "mix": table["mix"], "root_index": table["root_index"],
                "focal_seat": table["focal_seat"], "round_no": target["round_no"],
                "parent_action": parent, "alternate_action": alternate,
                "white_before": facts["white_before"],
                "wall_remaining": facts["remaining_tile_count"],
                "width_delta": width, "capacity_delta": capacity,
                "score_gap": score_gap, "components": components,
                "honor_for_number": (alternate_code in HONORS
                                     and parent_code not in HONORS),
            })
    if table_count != 256 or target_count != 847 or len(rows) != 169:
        raise ValueError("G192 G126 母体桌、目标窗或三向听窗数量漂移")
    layers = {}
    for mix in ("H", "M"):
        all_rows = [row for row in rows if row["mix"] == mix]
        one_white = [row for row in all_rows if row["white_before"] == 1]
        honor = [row for row in one_white if row["honor_for_number"]]
        rank16_like = [row for row in honor if row["score_gap"] <= 1
                       and row["width_delta"] >= 2
                       and row["capacity_delta"] >= 6]
        for name, selected in (("all", all_rows), ("one_white", one_white),
                               ("one_white_honor_for_number", honor),
                               ("rank16_like", rank16_like)):
            layers[f"{mix}/{name}"] = aggregate(selected)
    payload = {
        "schema": "g192-three-shanten-exposure/1",
        "source_sha256": {"g126_manifest": digest(_project_file(_PROJECT_ROOT, SOURCE / "manifest.json")),
                          "g126_result": digest(_project_file(_PROJECT_ROOT, SOURCE / "result.json")),
                          "g126_rows": digest(_project_file(_PROJECT_ROOT, SOURCE / "rows.jsonl")),
                          "script": digest(Path(__file__))},
        "source_tables": table_count, "source_target_windows": target_count,
        "three_shanten_windows": len(rows), "layers": layers,
        "rows": rows,
        "boundary": ("仅 G126 每单局首次严格宽面冲突；父代行动前事实，"
                     "备选未续打。宽度与公开容量不是牌墙概率，赢家大牌案例未入选。"),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True,
                              indent=2) + "\n", encoding="utf-8")
    print(json.dumps(layers, ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
