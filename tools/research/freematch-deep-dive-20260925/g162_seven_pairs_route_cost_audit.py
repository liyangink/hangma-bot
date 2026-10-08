#!/usr/bin/env python3
"""G162：在 G161 开发窗复核行动前七对/普通型逐牌机会成本。"""

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

import hashlib
import json
from pathlib import Path

import g126_all_draw_natural_width_exposure as capture
import g160_multi_action_value_source as source
import g161_multi_action_development_teacher as teacher


HERE = Path(__file__).resolve().parent
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g162-seven-pairs-route-cost-20260928/result.json')


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def vector(items) -> dict[str, int] | None:
    """None 保持为未知，空字典保持已知但无推进牌。"""
    if items is None:
        return None
    result = {tile.code: tile.remaining_estimate for tile in items}
    if len(result) != len(items):
        raise ValueError("生产逐牌推进事实重复")
    return result


def one_fact(facts) -> dict:
    """只读取当前合法动作的生产规则事实。"""
    standard = vector(facts.standard_useful_tiles)
    seven = vector(facts.seven_pairs_useful_tiles)
    combined = vector(facts.useful_tiles)
    return {"standard_shanten_after": facts.standard_shanten_after,
            "seven_pairs_shanten_after": facts.seven_pairs_shanten_after,
            "combined_shanten_after": facts.shanten_after,
            "standard_useful_by_code": standard,
            "seven_pairs_useful_by_code": seven,
            "combined_useful_by_code": combined,
            "standard_types": len(standard) if standard is not None else None,
            "standard_capacity": sum(standard.values()) if standard is not None else None,
            "seven_pairs_types": len(seven) if seven is not None else None,
            "seven_pairs_capacity": sum(seven.values()) if seven is not None else None,
            "combined_types": len(combined) if combined is not None else None,
            "combined_capacity": sum(combined.values()) if combined is not None else None,
            "baotou_after": facts.baotou_after,
            "pattern_progress_note": facts.pattern_progress_note}


def main() -> None:
    """逐桌重建相同观察，不读取隐藏世界反事实结果文件。"""
    if OUT.exists():
        raise FileExistsError("G162 行动前事实已有结果，不覆盖")
    items = teacher.selected()
    targets = teacher.index()
    g95 = source.source.g95
    contract = json.loads(g95.g93.paired.CONTRACT.read_text(encoding="utf-8"))
    versions = g95.g93.natural.stage.contract_versions_block(contract)
    scorer = capture.g87.c31.load_parent()
    plans = {(mix, root, seat): plan for mix, root, seat, plan in source.plans(contract)}
    grouped = {}
    for item in items:
        grouped.setdefault((item["mix"], item["root_index"],
                            item["focal_seat"]), []).append(item)
    by_identity = {}
    for key, group in grouped.items():
        original = g95.CaptureWiderPolicy
        g95.CaptureWiderPolicy = capture.CaptureEveryHandAllDrawPolicy
        try:
            captured, _runtime, _rules, _situation, hands, _ = g95.run_full(
                plans[key], contract, versions, key[0])
        finally:
            g95.CaptureWiderPolicy = original
        if len(hands) != 8:
            raise ValueError("G162 父代表不完整")
        for item in group:
            identity = key + (item["round_no"],)
            _table, target = targets[identity]
            record = captured.records.get(item["round_no"])
            if record is None or capture.scored_target(record, scorer) != target:
                raise ValueError("G162 行动前观察、父代评分或动作漂移")
            legal = {candidate.action_key: candidate.facts
                     for candidate in record.request.rules.legal_candidates}
            parent = one_fact(legal[item["parent_action"]])
            alternate = one_fact(legal[item["alternate_action"]])
            if (parent["standard_shanten_after"] != 2
                    or alternate["standard_shanten_after"] != 2
                    or parent["standard_types"] !=
                       target["visible_action_facts"][item["parent_action"]]["ordinary_codes"]
                    or alternate["standard_types"] !=
                       target["visible_action_facts"][item["alternate_action"]]["ordinary_codes"]):
                raise ValueError("G162 普通型规则事实与来源不守恒")
            by_identity[identity] = {
                "mix": item["mix"], "root_index": item["root_index"],
                "focal_seat": item["focal_seat"], "round_no": item["round_no"],
                "white_before": item["white_before"],
                "observation_sha256": item["observation_sha256"],
                "parent_action": item["parent_action"],
                "alternate_action": item["alternate_action"],
                "parent": parent, "alternate": alternate,
            }
    rows = [by_identity[(item["mix"], item["root_index"], item["focal_seat"],
                         item["round_no"])] for item in items]
    if len(rows) != 49:
        raise ValueError("G162 49 个开发窗不完整")
    payload = {"schema": "g162-seven-pairs-route-cost/1",
               "development_only": True,
               "selection_sha256": sha(source.OUT / "selection.json"),
               "source_rows_sha256": sha(source.OUT / "rows.jsonl"),
               "script_sha256": sha(Path(__file__)),
               "rows": rows,
               "boundary": "开发结果已看后的行动前事实审计；不得当独立确认或直接调新阈值。"}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False,
                              sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"rows": len(rows), "output": str(OUT)},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
