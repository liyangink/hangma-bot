"""第三结构批次机械归一化 v2：用白名单列表记录替代字典下标写入。"""
from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

import ast
import json
import sys
from pathlib import Path


HERE = Path(__file__).resolve().parent
ROUTE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15')
for path in (_project_file(_PROJECT_ROOT, ROUTE / "tools"), HERE):
    sys.path.insert(0, str(path))

import sitin_generate as gen  # noqa: E402
import structural_author_batch as first  # noqa: E402
import structural_author_batch_3 as batch3  # noqa: E402
import structural_normalize_3 as v1  # noqa: E402


BATCH = batch3.BATCH


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def replace_once(source: str, old: str, new: str, label: str, records: list[dict]) -> str:
    count = source.count(old)
    if count != 1:
        raise ValueError(f"{label}匹配数应为1，实际{count}")
    records.append({"label": label, "before_sha256": first.sha256_text(old),
                    "after_sha256": first.sha256_text(new)})
    return source.replace(old, new)


def normalize_space(source: str, records: list[dict]) -> str:
    first_line, rest = source.split("\n", 1)
    line, detail = v1.normalized_space(first_line)
    records.append({"label": "parameters_list_to_mapping_comment_only", "detail": detail})
    return line + "\n" + rest


def c1(source: str) -> tuple[str, list[dict]]:
    records: list[dict] = []
    source = normalize_space(source, records)
    source = replace_once(
        source,
        '    cmp_chi = None\n',
        '    cmp_chi = None\n    cmp_records = []\n',
        "initialize_comparison_records",
        records,
    )
    source = replace_once(
        source,
        '''            cmp_chi["cmp_adjust"] = chi_adj
            cmp_chi["cmp_detail"] = {"trigger": True, "window": "response_chi_same_shanten", "margin_support_minus_10": margin, "params": params_note, "own_branch_count": chi_count, "own_open_routes": chi_open, "adjust": chi_adj}
            cmp_pass["cmp_adjust"] = pass_adj
            cmp_pass["cmp_detail"] = {"trigger": True, "window": "response_chi_same_shanten", "margin_support_minus_10": margin, "params": params_note, "own_branch_count": pass_count, "own_open_routes": pass_open, "adjust": pass_adj}
''',
        '''            cmp_records.append({"item": cmp_chi, "adjust": chi_adj, "detail": {"trigger": True, "window": "response_chi_same_shanten", "margin_support_minus_10": margin, "params": params_note, "own_branch_count": chi_count, "own_open_routes": chi_open, "adjust": chi_adj}})
            cmp_records.append({"item": cmp_pass, "adjust": pass_adj, "detail": {"trigger": True, "window": "response_chi_same_shanten", "margin_support_minus_10": margin, "params": params_note, "own_branch_count": pass_count, "own_open_routes": pass_open, "adjust": pass_adj}})
''',
        "replace_item_mutation_with_identity_records",
        records,
    )
    source = replace_once(
        source,
        '''        unknown = base is None
        total = base_floor - 1.0 if unknown else base
''',
        '''        unknown = base is None
        adjust = None
        cmp_detail = None
        for cmp_record in cmp_records:
            if cmp_record.get("item") is item:
                adjust = cmp_record.get("adjust")
                cmp_detail = cmp_record.get("detail")
        total = base_floor - 1.0 if unknown else base
''',
        "lookup_comparison_record_by_identity",
        records,
    )
    source = replace_once(
        source,
        '            adjust = item.get("cmp_adjust")\n',
        '',
        "remove_mutated_field_lookup",
        records,
    )
    source = replace_once(
        source,
        '"chi_pass_compare": item.get("cmp_detail")',
        '"chi_pass_compare": cmp_detail',
        "trace_uses_record_detail",
        records,
    )
    return source, records


def c2(source: str) -> tuple[str, list[dict]]:
    records: list[dict] = []
    source = normalize_space(source, records)
    source = replace_once(
        source,
        '    gate_deltas = {}\n    gate_notes = {}\n',
        '    gate_deltas = []\n    gate_notes = []\n',
        "replace_dynamic_maps_with_record_lists",
        records,
    )
    source = replace_once(
        source,
        '''                    note = {"gate": "response_chi_ordinal", "params": [TIE_BAND, CONT_BONUS, FAMILY_BREAK], "margin": round(margin, 6), "triggered": False, "delta": 0.0}
                    if chi_shanten is not None and chi_shanten == pass_shanten and abs(margin) <= TIE_BAND:
                        note["triggered"] = True
                        note["shanten_level"] = "tenpain" if chi_shanten == 0 else "noten"
                        chi_branch_list = chi_action.get("followup_branches")
                        chi_branch_count = 0
                        if chi_branch_list is not None:
                            chi_branch_count = len(chi_branch_list)
                        capped = chi_branch_count
                        if capped > 4:
                            capped = 4
                        branch_gain = 0.0
                        if chi_branch_count > pass_branch_count:
                            branch_gain = CONT_BONUS * capped
                        chi_family_list = chi_action.get("family_progress_entries")
                        chi_closed = 0
                        chi_sp_route = "absent"
                        if chi_family_list is not None:
                            for family in chi_family_list:
                                if family.get("route_status") == "closed_proven":
                                    chi_closed += 1
                                if family.get("family") == "seven_pairs":
                                    chi_sp_route = family.get("route_status")
                        family_gain = 0.0
                        if chi_closed > pass_closed:
                            family_gain = float(FAMILY_BREAK)
                        note["chi_branch_count"] = chi_branch_count; note["pass_branch_count"] = pass_branch_count
                        note["chi_closed_routes"] = chi_closed; note["pass_closed_routes"] = pass_closed
                        note["seven_pairs_route_chi"] = chi_sp_route
                        note["branch_gain"] = branch_gain; note["family_gain"] = family_gain
                        note["delta"] = branch_gain + family_gain
                    gate_notes[chi_action.get("action_key")] = note
                    if note.get("delta") != 0.0:
                        gate_deltas[chi_action.get("action_key")] = note.get("delta")
''',
        '''                    triggered = False
                    shanten_level = None
                    chi_branch_count = 0
                    chi_closed = 0
                    chi_sp_route = "absent"
                    branch_gain = 0.0
                    family_gain = 0.0
                    if chi_shanten is not None and chi_shanten == pass_shanten and abs(margin) <= TIE_BAND:
                        triggered = True
                        shanten_level = "tenpain" if chi_shanten == 0 else "noten"
                        chi_branch_list = chi_action.get("followup_branches")
                        if chi_branch_list is not None:
                            chi_branch_count = len(chi_branch_list)
                        capped = chi_branch_count
                        if capped > 4:
                            capped = 4
                        if chi_branch_count > pass_branch_count:
                            branch_gain = CONT_BONUS * capped
                        chi_family_list = chi_action.get("family_progress_entries")
                        if chi_family_list is not None:
                            for family in chi_family_list:
                                if family.get("route_status") == "closed_proven":
                                    chi_closed += 1
                                if family.get("family") == "seven_pairs":
                                    chi_sp_route = family.get("route_status")
                        if chi_closed > pass_closed:
                            family_gain = float(FAMILY_BREAK)
                    note = {"gate": "response_chi_ordinal", "params": [TIE_BAND, CONT_BONUS, FAMILY_BREAK], "margin": round(margin, 6), "triggered": triggered, "delta": branch_gain + family_gain}
                    if triggered:
                        note = {"gate": "response_chi_ordinal", "params": [TIE_BAND, CONT_BONUS, FAMILY_BREAK], "margin": round(margin, 6), "triggered": True, "delta": branch_gain + family_gain, "shanten_level": shanten_level, "chi_branch_count": chi_branch_count, "pass_branch_count": pass_branch_count, "chi_closed_routes": chi_closed, "pass_closed_routes": pass_closed, "seven_pairs_route_chi": chi_sp_route, "branch_gain": branch_gain, "family_gain": family_gain}
                    gate_notes.append({"action_key": chi_action.get("action_key"), "note": note})
                    if note.get("delta") != 0.0:
                        gate_deltas.append({"action_key": chi_action.get("action_key"), "delta": note.get("delta")})
''',
        "build_note_once_and_append_records",
        records,
    )
    source = replace_once(
        source,
        '''            gate_delta = gate_deltas.get(key)
            if gate_delta is not None:
''',
        '''            gate_delta = None
            for gate_record in gate_deltas:
                if gate_record.get("action_key") == key:
                    gate_delta = gate_record.get("delta")
            if gate_delta is not None:
''',
        "lookup_gate_delta_from_records",
        records,
    )
    source = replace_once(
        source,
        '''        trace = {"basis": item.get("basis"), "base_score": base, "shanten_after": item.get("shanten"), "best_shanten_non_pass": best_shanten, "wealth_part": wealth_part, "wealth_discard_part": wealth_discard_part, "river_part": river_part, "risk_units": risk_units, "style_part": style_part, "unknown": unknown, "unknown_policy": "known_final_floor_minus_1" if unknown else None, "hu_sorting_layer": kind == "hu", "scope": "direct_v2_or_produced_outside_v2"}
        gate_note = gate_notes.get(key)
        if gate_note is not None:
            trace["chi_ordinal_gate"] = gate_note
''',
        '''        gate_note = None
        for note_record in gate_notes:
            if note_record.get("action_key") == key:
                gate_note = note_record.get("note")
        if gate_note is None:
            trace = {"basis": item.get("basis"), "base_score": base, "shanten_after": item.get("shanten"), "best_shanten_non_pass": best_shanten, "wealth_part": wealth_part, "wealth_discard_part": wealth_discard_part, "river_part": river_part, "risk_units": risk_units, "style_part": style_part, "unknown": unknown, "unknown_policy": "known_final_floor_minus_1" if unknown else None, "hu_sorting_layer": kind == "hu", "scope": "direct_v2_or_produced_outside_v2"}
        else:
            trace = {"basis": item.get("basis"), "base_score": base, "shanten_after": item.get("shanten"), "best_shanten_non_pass": best_shanten, "wealth_part": wealth_part, "wealth_discard_part": wealth_discard_part, "river_part": river_part, "risk_units": risk_units, "style_part": style_part, "unknown": unknown, "unknown_policy": "known_final_floor_minus_1" if unknown else None, "hu_sorting_layer": kind == "hu", "scope": "direct_v2_or_produced_outside_v2", "chi_ordinal_gate": gate_note}
''',
        "construct_trace_with_optional_gate_note",
        records,
    )
    return source, records


def subscript_assignments(source: str) -> int:
    count = 0
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Assign):
            count += sum(isinstance(target, ast.Subscript) for target in node.targets)
    return count


def main() -> None:
    rows = []
    for task_id, transform in (("C1", c1), ("C2", c2)):
        source_path = BATCH / f"generations/{task_id}/repair/candidate.py"
        target = BATCH / f"generations/{task_id}/repair/normalized-v2"
        if target.exists():
            raise SystemExit(f"normalized-v2已存在：{task_id}")
        source = source_path.read_text(encoding="utf-8")
        normalized, records = transform(source)
        if subscript_assignments(normalized) != 0:
            raise ValueError(f"{task_id}仍有下标赋值")
        precheck = gen.precheck_action_value_candidate(normalized)
        space = first.validate_space(normalized)
        target.mkdir(parents=True)
        (target / "candidate.py").write_text(normalized, encoding="utf-8")
        write_json(target / "normalization.json", {
            "schema": "r10-structural-normalization/3-v2",
            "task": task_id,
            "source_sha256": first.sha256_text(source),
            "normalized_sha256": first.sha256_text(normalized),
            "transformations": records,
            "semantic_claim": (
                "参数域只改注释表示；原字典原位字段写入改为局部记录列表和等值查找。"
                "评分、条件、参数、动作集合和trace字段取值保持；后续以冻结真实观察做运行验收。"
            ),
            "precheck": precheck,
            "structure_space": space,
        })
        rows.append({
            "task": task_id,
            "source_sha256": first.sha256_text(source),
            "normalized_sha256": first.sha256_text(normalized),
            "static_precheck": precheck.get("ok"),
            "structure_space": space.get("ok"),
            "accepted": precheck.get("ok") is True and space.get("ok") is True,
            "problems": list(precheck.get("problems") or []) + list(space.get("problems") or []),
        })
    write_json(BATCH / "normalization-v2-summary.json", {
        "schema": "r10-structural-normalization-summary/3-v2",
        "supersedes": "normalization-summary.json（v1误用非白名单dict.update）",
        "tasks": rows,
        "accepted": [row["task"] for row in rows if row["accepted"]],
        "closed": [row["task"] for row in rows if not row["accepted"]],
        "model_calls": 0,
        "effect_evaluation_started": False,
    })
    print(json.dumps({"status": "NORMALIZED_V2", "tasks": rows}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
