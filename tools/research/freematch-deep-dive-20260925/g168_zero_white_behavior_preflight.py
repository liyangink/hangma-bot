#!/usr/bin/env python3
"""G168：复原 G166 当前窗口，审查窄候选的合法改选与旧线重合。"""

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
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import c32_cards as c32
import g166_fresh_root_two_arm_teacher as teacher
import g168_zero_white_first_width_policy as candidate


HERE = Path(__file__).resolve().parent
PREREG = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/G168-ZEROWHITE-FIRST-WIDTH-BEHAVIOR-PREREG-2026-09-28.md')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g168-zero-white-behavior-20260928/result.json')
OLD = {
    "g11": _project_file(_PROJECT_ROOT, HERE / "candidates/G11-SHAPE-RISK-PARETO-V1.py"),
    "g30": _project_file(_PROJECT_ROOT, HERE / "candidates/G30-EDGE-TIE-ONEWHITE-V1.py"),
    "g88": _project_file(_PROJECT_ROOT, HERE / "candidates/G88-POST-CLAIM-FAMILIAR-BIAS-V1.py"),
}


def sha(path: Path) -> str:
    """保存来源、候选及旧线的原始字节摘要。"""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def old_tops(request, scorers: dict) -> dict[str, str]:
    """同一依法可见规则输入下，比较旧评分器动作指纹。"""
    capture = teacher.source.g160.source
    view = capture.g87.g05.build_scoring_view(
        request, value_limits=capture.g87.c31.VALUE_LIMITS).candidate_view()
    legal = {entry["action_key"] for entry in view["actions"]
             if entry["is_legal"] is True}
    results = {}
    for name, scorer in scorers.items():
        scored = scorer(view)
        if scored["status"] != "SCORED":
            raise ValueError("G168 旧评分器无法评分：" + name)
        entries = scored["entries"]
        scores = {entry["action_key"]: float(entry["score"]) for entry in entries}
        if set(scores) != legal:
            raise ValueError("G168 旧评分器动作集改变：" + name)
        results[name] = capture.g87.argmax(scores)
    return results


def main() -> None:
    """候选仅作 G166 观察上的结果盲行为审查，不读取双臂收益。"""
    if OUT.exists():
        raise FileExistsError("G168 行为结果已存在，拒绝覆盖")
    items = teacher.selected()
    targets = teacher.index()
    g95 = teacher.source.g160.source.g95
    contract = json.loads(g95.g93.paired.CONTRACT.read_text(encoding="utf-8"))
    versions = g95.g93.natural.stage.contract_versions_block(contract)
    scorer = teacher.source.g160.source.g87.c31.load_parent()
    plans = {(mix, root, seat): plan for mix, root, seat, plan in
             teacher.source.plans(contract)}
    old = {name: c32.load_scorer(path.name)[0] for name, path in OLD.items()}
    if any(value is None for value in old.values()):
        raise ValueError("G168 旧评分器缺失")
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
                or teacher.source.g160.source.scored_target(record, scorer) != target
                or item["observation_sha256"] != target["observation_sha256"]):
            raise ValueError("G168 父代观察或评分与固定 G166 来源不符")
        legal = [action.action_key for action in record.request.rules.legal_candidates]
        if record.parent_key not in legal or len(set(legal)) != len(legal):
            raise ValueError("G168 生产合法动作集异常")
        ordered = [record.parent_key] + [action for action in legal
                                         if action != record.parent_key]
        plan = SimpleNamespace(candidates=tuple(
            SimpleNamespace(action_key=action) for action in ordered))
        selected, evidence, consumed = candidate.select(record.request, plan)
        if selected is not None and selected not in legal:
            raise ValueError("G168 候选选择非法动作")
        if item["white_before"] == 1 and (selected is not None or consumed):
            raise ValueError("G168 一白非目标窗发生改选或状态消耗")
        older = old_tops(record.request, old) if selected is not None else {}
        rows.append({"mix": item["mix"], "root_index": item["root_index"],
                     "focal_seat": item["focal_seat"], "round_no": item["round_no"],
                     "white_before": item["white_before"],
                     "observation_sha256": item["observation_sha256"],
                     "parent_action": record.parent_key,
                     "expected_alternate": record.alternate_key,
                     "selected_action": selected,
                     "consumed_hand": consumed,
                     "reason": evidence["reason"],
                     "old_top_actions": older})
    counts = Counter((row["mix"], row["white_before"], row["reason"])
                     for row in rows)
    adopted = [row for row in rows if row["selected_action"] is not None]
    zero = [row for row in rows if row["white_before"] == 0]
    guard = [row for row in zero if row["reason"] == "combined_shanten_regression"]
    if (len(rows) != 64 or len(zero) != 32 or len(adopted) != 31
            or len(guard) != 1 or any(row["selected_action"] !=
                                      row["expected_alternate"] for row in adopted)
            or any(row["white_before"] != 0 for row in adopted)):
        raise ValueError("G168 31/31 精确改选与一处综合保护行为门失败")
    overlap = {name: sum(row["old_top_actions"][name] == row["selected_action"]
                         for row in adopted) for name in OLD}
    unique = [row for row in adopted if all(
        action != row["selected_action"] for action in row["old_top_actions"].values())]
    by_mix_unique = {mix: len({row["root_index"] for row in unique
                               if row["mix"] == mix}) for mix in ("H", "M")}
    passed = bool(unique) and all(by_mix_unique.values())
    result = {
        "schema": "g168-zero-white-behavior/1",
        "input_sha256": {
            "prereg": sha(PREREG), "candidate": sha(_project_file(_PROJECT_ROOT, HERE / "g168_zero_white_first_width_policy.py")),
            "script": sha(Path(__file__)),
            "g166_selection": sha(teacher.source.OUT / "selection.json"),
            "g166_parent_rows": sha(teacher.source.OUT / "rows.jsonl"),
            **{name: sha(path) for name, path in OLD.items()},
        },
        "summary": {
            "fixed_windows": len(rows),
            "adopted": len(adopted),
            "combined_guarded": len(guard),
            "old_action_overlap": overlap,
            "not_matched_by_any_checked_old_scorer": len(unique),
            "unique_roots_by_mix": by_mix_unique,
            "by_pool_white_reason": {
                "/".join(map(str, key)): value for key, value in sorted(counts.items())},
        },
        "behavior_gate_pass": passed,
        "rows": rows,
        "boundary": "已看 G166 观察的合法行为与旧线去重；不是全桌积分或线上时限验收。",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False,
                             sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result["summary"] | {"behavior_gate_pass": passed},
                     ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
