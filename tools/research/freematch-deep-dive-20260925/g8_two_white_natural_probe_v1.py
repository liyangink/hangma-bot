#!/usr/bin/env python3
"""在新 H/M 牌山根上结果盲冻结双白下一摸爆头的可执行入口。

本脚本只测自然触发、冻结目标窗和父代执行身份；完整桌模拟虽必须执行，
但本阶段不保存或分析比分。此前 P24 的广义盲弃胡负结果仍生效。
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

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import sys


HERE = Path(__file__).resolve().parent
ROOT = _PROJECT_ROOT
EV = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution')
for path in (_project_file(_PROJECT_ROOT, ROOT / "src"), EV, _project_file(_PROJECT_ROOT, ROOT / "review/llm-guided-heuristic-route-2026-09-15/tools"), HERE):
    sys.path.insert(0, str(path))

import g8_two_white_next_draw_census as census  # noqa: E402
import r18_p85_hu_deferral_natural_exposure as p85  # noqa: E402
from hangma_bot.application.audit_codec import decision_request_to_json  # noqa: E402
from hangma_bot.policy.action_value_policy import build_scoring_view  # noqa: E402
from hangma_bot.policy.action_value_seeds import ActionValueScorer  # noqa: E402


OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g8-two-white-next-draw-20260927/natural-probe')
PANEL_SEED = 2026102709
MIXES = ("H", "M")
ROOTS = tuple(range(1, 9))
SEATS = (0, 1, 2, 3)
TABLES_PER_SOURCE = 2
PREDICATE = "draw and legal_hu and parent_top_hu and hu_fan_1 and exactly_two_white and no_immediate_baotou_discard and wall_gt_24 and publicly_possible_nonwhite_next_draw_then_nonwhite_discard_baotou"


def _write(path: Path, value: dict) -> None:
    """保存无比赛结局的稳定 JSON。"""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sources() -> list[dict]:
    """两池各八个新独立牌山根，每根四座位、两张完整桌。"""

    return [{"mix": mix, "root_index": root, "focal_seat": seat,
             "source_root_id": f"{mix}:g8p76:{PANEL_SEED}:r{root:03d}",
             "source_id": f"{mix}:g8p76:{PANEL_SEED}:r{root:03d}:s{seat}"}
            for mix in MIXES for root in ROOTS for seat in SEATS]


def _source_path(source: dict) -> Path:
    return _project_file(_PROJECT_ROOT, OUT / "sources" / (source["source_id"].replace(":", "-") + ".json"))


def _candidate(request, source: dict, scorer: ActionValueScorer) -> tuple[dict | None, str]:
    """只从当前可见请求、规则事实和父代排序识别预先指定的窄入口。"""

    observation = request.observation
    if observation.phase != "draw":
        return None, "not_draw"
    if not any(item.action_key == "hu" for item in request.rules.legal_candidates):
        return None, "no_legal_hu"
    if sum(tile.code == "白" for tile in observation.my_hand) != 2:
        return None, "not_two_white"
    if observation.remaining_tile_count <= 24:
        return None, "no_next_draw_wall_budget"
    scored = scorer.score(build_scoring_view(request))
    if scored.status != "SCORED":
        raise ValueError("父代评分失败：" + str(scored.reason))
    entries = sorted(scored.entries, key=lambda item: (-item.score, item.action_key))
    if not entries or entries[0].action_key != "hu":
        return None, "parent_not_hu"
    request_json = decision_request_to_json(request)
    facts = census._static_witnesses(request_json)
    if facts["hu_fan"] != 1:
        return None, "hu_fan_not_one"
    if facts["immediate_baotou_discards"]:
        return None, "immediate_target_present"
    if not facts["witnesses"]:
        return None, "no_public_next_draw_route"
    by_first: dict[str, set[str]] = defaultdict(set)
    for witness in facts["witnesses"]:
        by_first[witness["first"]].add(witness["draw"])
    scores = {item.action_key: item.score for item in entries}
    ranked = sorted(by_first, key=lambda first: (
        -sum(facts["public_support_by_draw"][draw] for draw in by_first[first]),
        -scores["discard:" + first], first))
    first = ranked[0]
    table_id = str(observation.game_id).removeprefix("sitin-stage:")
    row = {"schema": "g8-two-white-natural-row/1", "source": source,
           "request": request_json, "request_sha256": p85.value_digest(request_json),
           "table_id": table_id, "table_no": int(table_id.rsplit("-t", 1)[1]),
           "window_key": request_json["window_key"], "focal_physical_seat": observation.seat,
           "reference_action": "hu", "intervention_action": "discard:" + first,
           "features": {"hu_fan": 1, "white_count": 2, "remaining_tile_count": facts["wall"],
                        "own_meld_count": facts["meld_count"],
                        "all_route_public_support_upper": facts["public_support_upper"],
                        "chosen_first_route_public_support_upper": sum(
                            facts["public_support_by_draw"][draw] for draw in by_first[first]),
                        "chosen_first_next_draws": sorted(by_first[first]),
                        "parent_hu_score": scores["hu"],
                        "parent_discard_score": scores["discard:" + first]}}
    return row, "eligible"


def _execute(source: dict, contract: dict) -> dict:
    """父代真正完成两桌，逐桌验证策略身份，然后只保存结果盲请求。"""

    frozen_source = p85.parent_source()
    plans = p85.natural.build_seat_stage_plans(
        contract=contract, opponent=source["mix"], root_index=source["root_index"],
        focal_seat=source["focal_seat"], panel_seed=PANEL_SEED)
    requests = []
    stage = p85.natural.run_arm_stage(
        arm="candidate", plans=plans,
        candidate_scorer=ActionValueScorer("g8p76-trajectory-" + source["source_id"], frozen_source),
        opponent_policies=contract["panel"]["opponent_scenarios"][source["mix"]]["opponent_policies"],
        versions_block=p85.natural.stage.contract_versions_block(contract),
        step_limit=int(contract["stop"]["step_limit"]), value_limits=p85.LIMITS,
        decision_observer=requests.append)
    if stage.get("status") != "complete" or len(stage.get("tables") or []) != TABLES_PER_SOURCE:
        raise RuntimeError("自然桌赛未完整完成：" + str(stage.get("error")))
    for plan, table in zip(plans, stage["tables"]):
        focal_seat = plan.seats().index(p85.natural.FOCAL_PARTICIPANT)
        policy_ids = (table.get("policy_execution") or {}).get("policy_ids_by_seat") or []
        if len(policy_ids) != 4 or not str(policy_ids[focal_seat]).startswith("action_value_v1:g8p76-trajectory-"):
            raise RuntimeError("焦点座位不是冻结 R18 v2")
    scorer = ActionValueScorer("g8p76-rescore-" + source["source_id"], frozen_source)
    counts = Counter()
    rows = []
    for request in requests:
        counts["focal_requests"] += 1
        row, status = _candidate(request, source, scorer)
        counts[status] += 1
        if row is not None:
            rows.append(row)
    rows.sort(key=lambda item: (item["request"]["observation"]["round_no"],
                                item["window_key"]["trigger_seq"], item["request_sha256"]))
    return {"schema": "g8-two-white-natural-source/1", "source": source,
            "status": "complete", "tables": TABLES_PER_SOURCE,
            "counts": dict(counts), "eligible_before_source_dedup": len(rows),
            "first_eligible": rows[0] if rows else None}


def prepare() -> None:
    """在运行任何新牌山前冻结源码、合同、父代和结果盲谓词。"""

    if OUT.exists():
        raise FileExistsError("自然探针目录已存在，拒绝覆盖")
    p85.parent_source()
    frozen = {"schema": "g8-two-white-natural-manifest/1", "outcome_blind": True,
              "parent_source_sha256": census.PARENT_SHA256,
              "parent_file_sha256": _hash(_project_file(_PROJECT_ROOT, ROOT / "src/hangma_bot/policy/r18_integrated_positive_v2.py")),
              "contract_sha256": _hash(p85.CONTRACT),
              "screen_script_sha256": _hash(_project_file(_PROJECT_ROOT, HERE / "g8_two_white_next_draw_census.py")),
              "probe_script_sha256": _hash(Path(__file__)), "panel_seed": PANEL_SEED,
              "predicate": PREDICATE, "source_units": len(sources()),
              "planned_full_tables": len(sources()) * TABLES_PER_SOURCE,
              "independence_unit": "H/M×牌山根；四座位与两桌不增加独立样本数",
              "prior_boundary": "P24广义盲弃胡开发失败；本窄入口未获收益豁免"}
    _write(_project_file(_PROJECT_ROOT, OUT / "manifest.json"), frozen)
    _write(_project_file(_PROJECT_ROOT, OUT / "sources.json"), {"schema": "g8-two-white-natural-sources/1", "sources": sources()})


def run() -> None:
    """按来源断点续跑；只计完成桌，失败停止并保留可复核记录。"""

    manifest = json.loads((_project_file(_PROJECT_ROOT, OUT / "manifest.json")).read_text(encoding="utf-8"))
    if _hash(Path(__file__)) != manifest["probe_script_sha256"]:
        raise ValueError("探针源码在冻结后漂移")
    if _hash(_project_file(_PROJECT_ROOT, HERE / "g8_two_white_next_draw_census.py")) != manifest["screen_script_sha256"]:
        raise ValueError("规则筛查源码在冻结后漂移")
    if _hash(p85.CONTRACT) != manifest["contract_sha256"]:
        raise ValueError("自然对手合同漂移")
    p85.parent_source()
    contract = json.loads(p85.CONTRACT.read_text(encoding="utf-8"))
    frozen = json.loads((_project_file(_PROJECT_ROOT, OUT / "sources.json")).read_text(encoding="utf-8"))["sources"]
    if frozen != sources():
        raise ValueError("自然来源清单漂移")
    for index, source in enumerate(frozen, 1):
        path = _source_path(source)
        if path.exists():
            continue
        row = _execute(source, contract)
        _write(path, row)
        if index % 8 == 0:
            print(json.dumps({"completed_sources": index, "planned_sources": len(frozen)}, ensure_ascii=False), flush=True)


def analyze() -> None:
    """只报告自然暴露；依根去重，不读取任何桌赛分数。"""

    frozen = json.loads((_project_file(_PROJECT_ROOT, OUT / "sources.json")).read_text(encoding="utf-8"))["sources"]
    by_root = defaultdict(list)
    counts = Counter()
    for source in frozen:
        row = json.loads(_source_path(source).read_text(encoding="utf-8"))
        if row["status"] != "complete" or row["tables"] != TABLES_PER_SOURCE:
            raise ValueError("自然来源未完成")
        counts.update(row["counts"])
        if row["first_eligible"]:
            by_root[source["source_root_id"]].append(row["first_eligible"])
    selected = [min(rows, key=lambda row: hashlib.sha256((row["source"]["source_root_id"] + row["request_sha256"]).encode()).hexdigest())
                for _, rows in sorted(by_root.items())]
    by_mix = Counter(row["source"]["mix"] for row in selected)
    _write(_project_file(_PROJECT_ROOT, OUT / "dataset.json"), {"schema": "g8-two-white-natural-dataset/1",
                                  "outcome_blind": True, "rows": selected})
    result = {"schema": "g8-two-white-natural-result/1", "outcome_blind": True,
              "source_units": len(frozen), "full_tables": len(frozen) * TABLES_PER_SOURCE,
              "raw_counts": dict(counts), "independent_roots": len(selected),
              "independent_roots_by_mix": dict(by_mix),
              "seat_coverage": sorted({row["focal_physical_seat"] for row in selected}),
              "decision": ("OPEN_FOCUSED_CAUSAL_DEVELOPMENT" if all(by_mix[mix] >= 6 for mix in MIXES)
                           else "INSUFFICIENT_NATURAL_EXPOSURE"),
              "release_eligible": False}
    _write(_project_file(_PROJECT_ROOT, OUT / "result.json"), result)
    print(json.dumps(result, ensure_ascii=False, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("prepare", "run", "analyze"))
    command = parser.parse_args().command
    if command == "prepare":
        prepare()
    elif command == "run":
        run()
    else:
        analyze()


if __name__ == "__main__":
    main()
