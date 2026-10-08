#!/usr/bin/env python3
"""G98：复用生产规则与 G52 两摸条件树，核对 G96 宽面动作对。"""

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

import g52_shared_horizon as g52
import g62_strong_shared_horizon as g62
import g95_wider_discard_same_hand_preflight as g95
from hangma_bot.application.audit_codec import candidate_value_facts_to_json
from hangma_bot.hangma.candidate_facts import FactsAnalysisError


HERE = Path(__file__).resolve().parent
SOURCE = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g96-wider-discard-branch-expansion-20260928/result.json')
PREREG = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/G98-G96-TWO-DRAW-ROUTE-CHECK-PREREG-2026-09-28.md')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g98-g96-two-draw-route-check-20260928/result.json')


def sha(path: Path) -> str:
    """记录冻结证据与量具字节身份。"""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    """重建 G96 全部身份，并对 27 个冻结动作对计算同一两摸时域摘要。"""
    if OUT.exists():
        raise FileExistsError("G98 已有证据，拒绝覆盖")
    source = json.loads(SOURCE.read_text(encoding="utf-8"))
    if source["schema"] != "g96-wider-discard-branch-expansion/1":
        raise ValueError("G96 输入 schema 漂移")
    contract = json.loads(g95.g93.paired.CONTRACT.read_text(encoding="utf-8"))
    versions = g95.g93.natural.stage.contract_versions_block(contract)
    rows = []
    for old in source["rows"]:
        mix, root, seat = old["mix"], old["root_index"], old["focal_seat"]
        plan = g95.g93.natural.build_seat_stage_plans(
            contract=contract, opponent=mix, root_index=root,
            focal_seat=seat, panel_seed=source["panel_seed"])[0]
        captured, runtime, rules, situation, hands, outcome = g95.run_full(
            plan, contract, versions, mix)
        if (plan.table_id != old["table_id"]
                or list(outcome.final_scores or ()) != old["full_parent_final_scores"]):
            raise ValueError("G98 原父代表身份或终分漂移")
        if old["status"] == "no_window":
            if captured.world is not None:
                raise ValueError("G98 原无命中桌意外命中")
            continue
        if (old["status"] != "paired" or captured.world is None
                or g95.g93.window_key_to_json(captured.request.window_key)
                != old["target_window"]
                or captured.parent_key != old["parent_action"]
                or captured.alternate_key != old["alternate_action"]
                or captured.facts != old["visible_action_facts"]):
            raise ValueError("G98 原动作窗口身份、动作或规则宽度漂移")
        row = {"mix": mix, "root_index": root, "focal_seat": seat,
               "table_id": plan.table_id, "target_window": old["target_window"],
               "parent_action": captured.parent_key,
               "alternate_action": captured.alternate_key,
               "white_before": old["white_before"],
               "shanten": captured.facts[captured.parent_key]["standard_shanten_after"],
               "resampled_delta_sum": sum(pair["focal_delta_alt_minus_parent"]
                                            for pair in old["world_pairs"][1:]),
               "resampled_signs": dict(Counter(
                   "positive" if pair["focal_delta_alt_minus_parent"] > 0
                   else "negative" if pair["focal_delta_alt_minus_parent"] < 0
                   else "zero" for pair in old["world_pairs"][1:])),
               "historical_delta": old["world_pairs"][0]["focal_delta_alt_minus_parent"]}
        legal = {candidate.action_key: candidate
                 for candidate in captured.request.rules.legal_candidates}
        try:
            pair = {}
            for label, key in (("parent", captured.parent_key),
                               ("alternate", captured.alternate_key)):
                candidate = legal.get(key)
                if candidate is None or candidate.value_facts is None:
                    raise ValueError("生产规则分值事实缺失")
                root_tree = g52.evaluate_root(
                    captured.request.observation,
                    {"action_key": key,
                     "value_facts": candidate_value_facts_to_json(candidate.value_facts)},
                    rules.config)
                pair[label] = g62.summarize(root_tree)
            row["status"] = "complete"
            row["pair"] = pair
            row["delta_alt_minus_parent"] = g62.delta(pair["parent"], pair["alternate"])
        except (ValueError, FactsAnalysisError) as exc:
            row["status"] = "unavailable"
            row["reason"] = type(exc).__name__ + ": " + str(exc)[:250]
        rows.append(row)
    if len(rows) != sum(old["status"] == "paired" for old in source["rows"]):
        raise ValueError("G98 冻结动作窗口数不符")
    result = {"schema": "g98-g96-two-draw-route-check/1",
              "exploratory": True,
              "input_sha256": {"g96": sha(SOURCE), "prereg": sha(PREREG),
                               "script": sha(Path(__file__)),
                               "g52_tree": sha(_project_file(_PROJECT_ROOT, HERE / "g52_shared_horizon.py")),
                               "g62_summary": sha(_project_file(_PROJECT_ROOT, HERE / "g62_strong_shared_horizon.py"))},
              "rows": rows,
              "boundary": "两摸条件树无对手行动、实际墙后验和真实续打策略；"
                          "本批已看结算，不能从方向对应拟合候选阈值。"}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                   encoding="utf-8")
    print(json.dumps({"windows": len(rows),
                      "complete": sum(row["status"] == "complete" for row in rows),
                      "unavailable": sum(row["status"] == "unavailable" for row in rows)},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
