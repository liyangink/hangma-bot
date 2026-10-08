#!/usr/bin/env python3
"""G97：重新构造 G96 冻结窗口，逐项对账父代弃牌评分。"""

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

import g87_post_claim_score_trace as g87
import g95_wider_discard_same_hand_preflight as g95


HERE = Path(__file__).resolve().parent
SOURCE = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g96-wider-discard-branch-expansion-20260928/result.json')
PREREG = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/G97-G96-VISIBLE-SCORE-TRACE-PREREG-2026-09-28.md')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g97-g96-visible-score-trace-20260928/result.json')


def sha(path: Path) -> str:
    """绑定输入证据和固定评分源码。"""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    """仅重算已冻结的玩家可见评分分量，严格核对旧窗口身份。"""
    if OUT.exists():
        raise FileExistsError("G97 已有证据，拒绝覆盖")
    source = json.loads(SOURCE.read_text(encoding="utf-8"))
    if source["schema"] != "g96-wider-discard-branch-expansion/1":
        raise ValueError("G96 输入 schema 错误")
    contract = json.loads(g95.g93.paired.CONTRACT.read_text(encoding="utf-8"))
    versions = g95.g93.natural.stage.contract_versions_block(contract)
    scorer = g87.c31.load_parent()
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
            raise ValueError("G97 完整父代表身份或终分漂移")
        if old["status"] == "no_window":
            if captured.world is not None:
                raise ValueError("G97 原缺测桌意外命中")
            continue
        if captured.world is None or old["status"] != "paired":
            raise ValueError("G97 已配对桌目标缺失")
        request = captured.request
        observation = request.observation
        if (g95.g93.window_key_to_json(request.window_key) != old["target_window"]
                or captured.parent_key != old["parent_action"]
                or captured.alternate_key != old["alternate_action"]
                or captured.facts != old["visible_action_facts"]):
            raise ValueError("G97 窗口键、动作或规则宽度事实漂移")
        white_before = (sum(tile.code == "白" for tile in observation.my_hand)
                        + int(observation.drawn_tile is not None
                              and observation.drawn_tile.code == "白"))
        if white_before != old["white_before"]:
            raise ValueError("G97 当前白板数漂移")
        view = g87.g05.build_scoring_view(
            request, value_limits=g87.c31.VALUE_LIMITS).candidate_view()
        scored = scorer(view)
        if scored["status"] != "SCORED":
            raise ValueError("G97 冻结父代评分失败")
        entries = {entry["action_key"]: entry for entry in scored["entries"]}
        scores = {key: float(entry["score"]) for key, entry in entries.items()}
        parent, alternate = captured.parent_key, captured.alternate_key
        if (g87.argmax(scores) != parent or parent not in entries
                or alternate not in entries):
            raise ValueError("G97 冻结父代动作排序漂移")
        gap = scores[parent] - scores[alternate]
        delta = {name: g87.component(entries[parent]["trace"], name)
                 - g87.component(entries[alternate]["trace"], name)
                 for name in g87.COMPONENTS}
        if abs(sum(delta.values()) - gap) > 1e-8:
            raise ValueError("G97 父代评分分量无法对账")
        values = [pair["focal_delta_alt_minus_parent"] for pair in old["world_pairs"][1:]]
        signs = Counter("positive" if value > 0 else "negative" if value < 0 else "zero"
                        for value in values)
        rows.append({
            "mix": mix, "root_index": root, "focal_seat": seat,
            "table_id": plan.table_id,
            "target_window": old["target_window"],
            "parent_action": parent, "alternate_action": alternate,
            "white_before": white_before,
            "standard_shanten_after": captured.facts[parent]["standard_shanten_after"],
            "ordinary_codes_delta": captured.facts[alternate]["ordinary_codes"]
            - captured.facts[parent]["ordinary_codes"],
            "public_unseen_capacity_delta":
                captured.facts[alternate]["public_unseen_capacity"]
                - captured.facts[parent]["public_unseen_capacity"],
            "parent_score_gap": gap,
            "component_parent_minus_alternate": delta,
            "remaining_tile_count": observation.remaining_tile_count,
            "dealer_seat": observation.dealer_seat,
            "scores_by_seat": list(observation.scores),
            "own_chi_peng_count": sum(meld.kind in ("chi", "peng")
                                      for meld in observation.melds[seat]),
            "opponent_meld_count": sum(len(observation.melds[index])
                                        for index in range(4) if index != seat),
            "public_discard_count": sum(len(discard) for discard in observation.discards),
            "resampled_signs": dict(signs),
            "resampled_delta_sum": sum(values),
            "historical_delta": old["world_pairs"][0]["focal_delta_alt_minus_parent"],
        })
    if len(rows) != sum(row["status"] == "paired" for row in source["rows"]):
        raise ValueError("G97 已配对窗口数对账失败")
    result = {
        "schema": "g97-g96-visible-score-trace/1", "exploratory": True,
        "input_sha256": {"g96": sha(SOURCE), "prereg": sha(PREREG),
                         "script": sha(Path(__file__)),
                         "parent_scorer":
                         g87.c31.R18_INTEGRATED_POSITIVE_V2_SHA256},
        "rows": rows,
        "boundary": "评分分量解释父代排序；八世界结算只作事后解释标签，"
                    "不得在本批拟合阈值或声称官方收益。",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                   encoding="utf-8")
    print(json.dumps({"reconstructed_windows": len(rows),
                      "mix_counts": dict(Counter(row["mix"] for row in rows))},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
