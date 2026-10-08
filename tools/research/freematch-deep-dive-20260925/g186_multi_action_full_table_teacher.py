#!/usr/bin/env python3
"""G186：G183 新根开发窗的多弃牌同世界完整桌教师。"""

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

import argparse
import hashlib
import json
import os
from pathlib import Path

import g182_full_table_branch_preflight as branch
import g183_new_root_teacher_source as source


HERE = Path(__file__).resolve().parent
PLAN = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/G186-MULTI-ACTION-FULL-TABLE-TEACHER-PREREG-2026-09-28.md')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g186-multi-action-full-table-teacher-20260928')
SAMPLES = ("historical",) + tuple(f"g186-{index:02d}" for index in range(1, 8))


def sha(path: Path) -> str:
    """把方案、来源及实现绑定到清单。"""

    return hashlib.sha256(path.read_bytes()).hexdigest()


def action_facts(facts) -> dict:
    """只序列化生产规则给出的动作前牌效与公开未见容量。"""

    def useful(items) -> dict | None:
        if items is None:
            return None
        return {item.code: item.remaining_estimate for item in items}

    return {
        "combined_shanten": facts.shanten_after,
        "standard_shanten": facts.standard_shanten_after,
        "seven_pairs_shanten": facts.seven_pairs_shanten_after,
        "standard_useful": useful(facts.standard_useful_tiles),
        "seven_pairs_useful": useful(facts.seven_pairs_useful_tiles),
        "combined_useful": useful(facts.useful_tiles),
        "baotou_after": facts.baotou_after,
    }


def selected_actions(record, scorer) -> tuple[list[str], dict]:
    """只按行动前合法事实和冻结原分选至多三个严格宽面备选。"""

    request = record.request
    legal = {item.action_key: item.facts for item in request.rules.legal_candidates}
    parent = record.parent_key
    widest = record.alternate_key
    if parent not in legal or widest not in legal:
        raise ValueError("G186 父代或 G183 最宽备选不在合法集合")
    parent_fact = legal[parent]
    if parent_fact.standard_useful_tiles is None:
        raise ValueError("G186 父代普通型进张未分析")

    def width(facts) -> tuple[int, int]:
        tiles = facts.standard_useful_tiles
        if tiles is None:
            raise ValueError("G186 合法弃牌普通型进张未分析")
        return len(tiles), sum(tile.remaining_estimate for tile in tiles)

    parent_width = width(parent_fact)
    eligible = []
    for key, facts in legal.items():
        if (not key.startswith("discard:") or key == "discard:白"
                or key == parent
                or facts.standard_shanten_after != parent_fact.standard_shanten_after):
            continue
        codes, capacity = width(facts)
        if codes > parent_width[0] and capacity > parent_width[1]:
            eligible.append(key)
    if widest not in eligible:
        raise ValueError("G186 G183 最宽备选不再满足严格宽面规则")
    if min(eligible, key=lambda key: (-width(legal[key])[0],
                                      -width(legal[key])[1], key)) != widest:
        raise ValueError("G186 G183 最宽备选动作身份漂移")

    view = source.g160.source.g87.g05.build_scoring_view(
        request, value_limits=source.g160.source.g87.c31.VALUE_LIMITS).candidate_view()
    scored = scorer(view)
    if scored.get("status") != "SCORED":
        raise ValueError("G186 冻结 R18 未完整评分")
    scores = {item["action_key"]: float(item["score"])
              for item in scored["entries"]}
    if source.g160.source.g87.argmax(scores) != parent:
        raise ValueError("G186 冻结评分首选不等于父代动作")
    actions = [parent, widest]
    rest = [key for key in eligible if key not in actions]
    if rest:
        best_score = min(rest, key=lambda key: (-scores[key], key))
        actions.append(best_score)
        rest.remove(best_score)
    if rest:
        max_capacity = min(rest, key=lambda key: (-width(legal[key])[1],
                                                  -width(legal[key])[0], key))
        actions.append(max_capacity)
    return actions, {key: {"r18_score": scores[key],
                           **action_facts(legal[key])} for key in actions}


def compact(outcome: dict) -> dict:
    """保留八局结算与互斥积分分量，不落盘内部世界或其他暗手。"""

    return {key: value for key, value in outcome.items() if key != "decisions"}


def main() -> None:
    """准确前缀跑完整开发来源，锁定窗无任何备选调用。"""

    parser = argparse.ArgumentParser()
    parser.add_argument("--max-new", type=int, default=0)
    args = parser.parse_args()
    g95 = source.g160.source.g95
    g93 = g95.g93
    selection_path = source.OUT / "selection.json"
    selection = json.loads(selection_path.read_text(encoding="utf-8"))
    source_result = json.loads((source.OUT / "result.json").read_text(encoding="utf-8"))
    if (not selection.get("result_blind") or not source_result.get("source_coverage_gate_pass")
            or selection["rows_sha256"] != sha(source.OUT / "rows.jsonl")
            or selection["manifest_sha256"] != sha(source.OUT / "manifest.json")):
        raise ValueError("G186 G183 冻结来源未通过摘要或覆盖门")
    items = [item for item in selection["selected"] if item["split"] == "development"]
    if len(items) != 80 or len(selection["selected"]) != 120:
        raise ValueError("G186 来源窗数量不符，锁定窗不得误入")
    contract_path = g93.paired.CONTRACT
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    versions = g93.natural.stage.contract_versions_block(contract)
    schedule = {(mix, root, seat): plan for mix, root, seat, plan in source.plans(contract)}
    target_rows = {}
    for line in (source.OUT / "rows.jsonl").read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        for target in row["target_windows"]:
            target_rows[(row["mix"], row["root_index"], row["focal_seat"],
                         target["round_no"])] = target
    manifest = {
        "schema": "g186-multi-action-full-table-teacher-manifest/1",
        "development_windows": len(items), "samples": list(SAMPLES),
        "source_sha256": {name: sha(path) for name, path in {
            "prereg": PLAN, "script": Path(__file__),
            "selection": selection_path, "g183_rows": source.OUT / "rows.jsonl",
            "g183_manifest": source.OUT / "manifest.json",
            "contract": contract_path, "g182_resume": Path(branch.__file__),
            "g95_runtime": Path(g95.__file__),
            "parent_source": _project_file(_PROJECT_ROOT, HERE.parents[1] / "src/hangma_bot/policy/r18_integrated_positive_v2.py"),
        }.items()},
        "boundary": "只开 G183 的 80 个开发窗；八个同观察相关世界，锁定窗继续封存。",
    }
    OUT.mkdir(parents=True, exist_ok=True)
    manifest_path = _project_file(_PROJECT_ROOT, OUT / "manifest.json")
    if manifest_path.exists():
        if json.loads(manifest_path.read_text(encoding="utf-8")) != manifest:
            raise ValueError("G186 既有清单与当前输入漂移，拒绝混写")
    else:
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False,
                                            sort_keys=True, indent=2) + "\n", encoding="utf-8")
    rows_path = _project_file(_PROJECT_ROOT, OUT / "rows.jsonl")
    previous = ([json.loads(line) for line in rows_path.read_text(encoding="utf-8").splitlines()]
                if rows_path.exists() else [])
    if len(previous) > len(items):
        raise ValueError("G186 既有续打行多于事前开发窗")
    for old, item in zip(previous, items):
        if old["window_identity"] != {key: item[key] for key in
                                      ("mix", "root_index", "focal_seat", "round_no",
                                       "observation_sha256", "parent_action")}:
            raise ValueError("G186 既有结果不是事前开发窗准确前缀")
    scorer = source.g160.source.g87.c31.load_parent()
    added = 0
    with rows_path.open("a", encoding="utf-8") as stream:
        for item in items[len(previous):]:
            mix, root, seat, round_no = (item[key] for key in
                                         ("mix", "root_index", "focal_seat", "round_no"))
            plan = schedule[(mix, root, seat)]
            original = g95.CaptureWiderPolicy
            g95.CaptureWiderPolicy = source.g160.source.CaptureEveryHandAllDrawPolicy
            try:
                captured, runtime, rules, situation, full_hands, full_outcome = g95.run_full(
                    plan, contract, versions, mix)
            finally:
                g95.CaptureWiderPolicy = original
            record = captured.records.get(round_no)
            expected = target_rows[(mix, root, seat, round_no)]
            if (record is None or source.g160.source.scored_target(record, scorer) != expected
                    or expected["observation_sha256"] != item["observation_sha256"]
                    or record.parent_key != item["parent_action"]
                    or record.alternate_key != item["alternate_action"]):
                raise ValueError("G186 父代来源观察或评分事实漂移")
            actions, facts = selected_actions(record, scorer)
            initial = runtime["engine"].frame(record.world).decisions[0].observation
            before = full_hands[:round_no - 1]
            pair_rows = []
            for sample in SAMPLES:
                world = (record.world if sample == "historical" else
                         runtime["engine"].resample_public_consistent_hidden_world(
                             record.world, focal_seat=seat, sample_key=sample))
                if runtime["engine"].frame(world).decisions[0].observation != initial:
                    raise ValueError("G186 重采样改变行动前 PlayerObservation")
                outcomes = {}
                for key in actions:
                    result = branch.run_branch(
                        world=world, record=record, plan=plan, contract=contract,
                        versions=versions, runtime=runtime, rules=rules,
                        situation=situation, mix=mix,
                        forced_key=None if key == item["parent_action"] else key,
                        prefix_hands=before)
                    outcomes[key] = result
                    if sample == "historical" and key == item["parent_action"]:
                        if (len(result["hands"]) != len(full_hands)
                                or any({name: old[name] for name in branch.SETTLEMENT_FIELDS}
                                       != {name: new[name] for name in branch.SETTLEMENT_FIELDS}
                                       for old, new in zip(full_hands, result["hands"], strict=True))
                                or result["final_scores"] != list(full_outcome.final_scores or ())
                                or result["decisions"] !=
                                branch._decisions(full_outcome, record.request.window_key)):
                            raise ValueError("G186 历史父代行动、逐局或终分不恒等")
                starts = {tuple(result["hands"][0]["scores_before"])
                          for result in outcomes.values()}
                if len(starts) != 1:
                    raise ValueError("G186 同世界动作臂积分起点不同")
                parent_score = outcomes[item["parent_action"]]["final_scores"][seat]
                pair_rows.append({
                    "sample_key": sample,
                    "focal_table_delta_by_action": {
                        key: result["final_scores"][seat] - parent_score
                        for key, result in outcomes.items()},
                    "outcomes": {key: compact(result) for key, result in outcomes.items()},
                })
            row = {
                "window_identity": {key: item[key] for key in
                                    ("mix", "root_index", "focal_seat", "round_no",
                                     "observation_sha256", "parent_action")},
                "alternate_actions": actions[1:],
                "action_before_facts": facts,
                "score_facts": item["score_facts"],
                "paired_worlds": pair_rows,
            }
            stream.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
            added += 1
            print(json.dumps({"completed_windows": len(previous) + added,
                              "mix": mix, "root": root, "white": item["white_before"],
                              "actions": len(actions)}, ensure_ascii=False), flush=True)
            if args.max_new > 0 and added >= args.max_new:
                break
    print(json.dumps({"complete": len(previous) + added == len(items),
                      "windows": len(previous) + added}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
