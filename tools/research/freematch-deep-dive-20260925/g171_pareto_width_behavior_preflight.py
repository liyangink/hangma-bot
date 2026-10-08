#!/usr/bin/env python3
"""G171：固定 G166 父代观察上的合法性、多目标保护与旧线去重。"""

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
import json
from pathlib import Path
from types import SimpleNamespace

import c32_cards as c32
import g166_fresh_root_two_arm_teacher as teacher
import g168_zero_white_behavior_preflight as g168_behavior
import g171_pareto_width_policy as candidate


HERE = Path(__file__).resolve().parent
PREREG = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/G171-PARETO-WIDTH-BEHAVIOR-PREREG-2026-09-28.md')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g171-pareto-width-behavior-20260928/result.json')


def _plan(request, parent_scorer, parent_key):
    """使用冻结 R18 全动作原分与轨迹构造只读候选序列。"""
    source = teacher.source.g160.source
    view = source.g87.g05.build_scoring_view(
        request, value_limits=source.g87.c31.VALUE_LIMITS).candidate_view()
    scored = parent_scorer(view)
    if scored["status"] != "SCORED":
        raise ValueError("G171 R18 原评分未覆盖该窗口")
    entries = {item["action_key"]: item for item in scored["entries"]}
    legal = {item.action_key for item in request.rules.legal_candidates}
    if set(entries) != legal:
        raise ValueError("G171 评分与生产合法动作集不一致")
    scores = {key: float(item["score"]) for key, item in entries.items()}
    if source.g87.argmax(scores) != parent_key:
        raise ValueError("G171 父代首选与固定评分不一致")
    order = [parent_key] + sorted(legal - {parent_key})
    return SimpleNamespace(candidates=tuple(SimpleNamespace(
        action_key=key,
        score_trace={"trace_schema": "sitin-action-score-trace/1",
                     "detail": entries[key]["trace"]}) for key in order))


def main() -> None:
    """行为层不读取 G166/G168 收益，仅核可见性、规则与旧线差异。"""
    if OUT.exists():
        raise FileExistsError("G171 行为结果已存在，拒绝覆盖")
    items = teacher.selected()
    targets = teacher.index()
    g95 = teacher.source.g160.source.g95
    contract = json.loads(g95.g93.paired.CONTRACT.read_text(encoding="utf-8"))
    versions = g95.g93.natural.stage.contract_versions_block(contract)
    parent_scorer = teacher.source.g160.source.g87.c31.load_parent()
    plans = {(mix, root, seat): plan for mix, root, seat, plan in
             teacher.source.plans(contract)}
    old = {name: c32.load_scorer(path.name)[0]
           for name, path in g168_behavior.OLD.items()}
    if any(value is None for value in old.values()):
        raise ValueError("G171 旧评分器缺失")
    rows = []
    for item in items:
        key = (item["mix"], item["root_index"], item["focal_seat"],
               item["round_no"])
        table, target = targets[key]
        original = g95.CaptureWiderPolicy
        g95.CaptureWiderPolicy = teacher.source.g160.source.CaptureEveryHandAllDrawPolicy
        try:
            captured, _runtime, _rules, _situation, _hands, _ = g95.run_full(
                plans[key[:3]], contract, versions, table["mix"])
        finally:
            g95.CaptureWiderPolicy = original
        record = captured.records.get(item["round_no"])
        if (record is None
                or teacher.source.g160.source.scored_target(record, parent_scorer)
                != target
                or item["observation_sha256"] != target["observation_sha256"]):
            raise ValueError("G171 父代观察或评分与 G166 固定来源不符")
        plan = _plan(record.request, parent_scorer, record.parent_key)
        selected, evidence, consumed = candidate.select(record.request, plan)
        legal = {action.action_key for action in record.request.rules.legal_candidates}
        if selected is not None and selected not in legal:
            raise ValueError("G171 选择非法动作")
        if item["white_before"] == 1 and (selected is not None or consumed):
            raise ValueError("G171 一白非目标窗越位或消耗机会")
        if selected is not None:
            if not (evidence["alternate_standard_width"][0]
                    > evidence["parent_standard_width"][0]
                    and evidence["alternate_standard_width"][1]
                    > evidence["parent_standard_width"][1]
                    and evidence["alternate_combined_shanten"]
                    <= evidence["parent_combined_shanten"]
                    and evidence["alternate_combined_capacity"]
                    >= evidence["parent_combined_capacity"]
                    and evidence["alternate_seven_pairs_shanten"]
                    <= evidence["parent_seven_pairs_shanten"]
                    and evidence["alternate_risk_units"]
                    <= evidence["parent_risk_units"]):
                raise ValueError("G171 已选择动作违反冻结联合保护")
        older = g168_behavior.old_tops(record.request, old) if selected else {}
        rows.append({"mix": item["mix"], "root_index": item["root_index"],
                     "focal_seat": item["focal_seat"], "round_no": item["round_no"],
                     "white_before": item["white_before"],
                     "observation_sha256": item["observation_sha256"],
                     "parent_action": record.parent_key,
                     "selected_action": selected, "consumed_hand": consumed,
                     "reason": evidence["reason"], "evidence": evidence,
                     "old_top_actions": older})
    adopted = [row for row in rows if row["selected_action"] is not None]
    unique = [row for row in adopted if all(
        action != row["selected_action"]
        for action in row["old_top_actions"].values())]
    unique_roots = {mix: len({row["root_index"] for row in unique
                              if row["mix"] == mix}) for mix in ("H", "M")}
    if len(rows) != 64 or sum(row["white_before"] == 0 for row in rows) != 32:
        raise ValueError("G171 G166 固定 64 窗或零白层覆盖异常")
    summary = {
        "fixed_windows": len(rows),
        "adopted": len(adopted),
        "guarded": sum(row["consumed_hand"] and row["selected_action"] is None
                       for row in rows),
        "unique_vs_g11_g30_g88": len(unique),
        "unique_roots_by_mix": unique_roots,
        "by_pool_white_reason": {
            "/".join(map(str, key)): value for key, value in sorted(Counter(
                (row["mix"], row["white_before"], row["reason"])
                for row in rows).items())},
    }
    passed = bool(unique) and all(unique_roots.values())
    payload = {
        "schema": "g171-pareto-width-behavior/1",
        "input_sha256": {
            "prereg": g168_behavior.sha(PREREG),
            "candidate": g168_behavior.sha(_project_file(_PROJECT_ROOT, HERE / "g171_pareto_width_policy.py")),
            "script": g168_behavior.sha(Path(__file__)),
            "g166_selection": g168_behavior.sha(teacher.source.OUT / "selection.json"),
            "g166_parent_rows": g168_behavior.sha(teacher.source.OUT / "rows.jsonl"),
            **{name: g168_behavior.sha(path)
               for name, path in g168_behavior.OLD.items()},
        },
        "summary": summary,
        "behavior_gate_pass": passed,
        "rows": rows,
        "boundary": "已看 G166 观察的合法行为门；不读收益，不作发布确认。",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False,
                              sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary | {"behavior_gate_pass": passed},
                     ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
