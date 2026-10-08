"""R18 P12：从全新 P5 自然牌局采集七对/普通型竞争前沿。"""

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

import argparse
import concurrent.futures
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Mapping


HERE = Path(__file__).resolve().parent
ROUTE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15')
ROOT = _PROJECT_ROOT
for path in (_project_file(_PROJECT_ROOT, ROOT / "src"), _project_file(_PROJECT_ROOT, ROUTE / "tools"), HERE):
    sys.path.insert(0, str(path))

import confirmation_execution_identity as guard  # noqa: E402
import r18_p9_midgame_hidden_world_teacher as p9  # noqa: E402
import sitin_natural_panel as natural  # noqa: E402
from hangma_bot.application.audit_codec import decision_request_to_json  # noqa: E402
from hangma_bot.hangma.interface import ValueAnalysisLimits  # noqa: E402
from hangma_bot.policy.action_value_policy import build_scoring_view  # noqa: E402
from hangma_bot.policy.action_value_seeds import ActionValueScorer  # noqa: E402


OUT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p12-natural-seven-pairs-frontier-01-20260922')
CONTRACT = p9.CONTRACT
PARENT = p9.P5
PANEL_SEED = 2026102201
MIXES = ("H", "M")
DEVELOPMENT_ROOTS = (1, 2, 3, 4)
HIDDEN_ROOTS = (5, 6, 7, 8)
SEATS = (0, 1, 2, 3)
LIMITS = ValueAnalysisLimits(max_expansions=20_000, max_routes_per_candidate=256)


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                    encoding="utf-8")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def value_digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")).hexdigest()


def sources() -> list[dict[str, Any]]:
    rows = []
    for split, roots in (("development", DEVELOPMENT_ROOTS), ("hidden", HIDDEN_ROOTS)):
        for mix in MIXES:
            for root in roots:
                for seat in SEATS:
                    rows.append({
                        "split": split, "mix": mix, "root_index": root,
                        "focal_seat": seat,
                        "source_id": "{0}:{1}:r{2:02d}:s{3}".format(split, mix, root, seat),
                    })
    return rows


def support(items: Any) -> int:
    return sum(int(item.remaining_estimate) for item in items)


def action_json(action: Any) -> dict[str, Any]:
    return {
        "action_key": action.action_key,
        "standard_shanten_after": action.standard_shanten_after,
        "standard_support_remaining": support(action.standard_useful_tiles),
        "seven_pairs_shanten_after": action.seven_pairs_shanten_after,
        "seven_pairs_support_remaining": support(action.seven_pairs_useful_tiles),
        "combined_shanten_after": action.shanten_after,
    }


def route_compare(left: Mapping[str, Any], right: Mapping[str, Any], prefix: str) -> int:
    """按向听优先、公开未见支持数次之比较；左优返回 1。"""

    left_shanten = int(left[prefix + "_shanten_after"])
    right_shanten = int(right[prefix + "_shanten_after"])
    if left_shanten != right_shanten:
        return 1 if left_shanten < right_shanten else -1
    left_support = int(left[prefix + "_support_remaining"])
    right_support = int(right[prefix + "_support_remaining"])
    if left_support != right_support:
        return 1 if left_support > right_support else -1
    return 0


def top(batch: Any) -> Any:
    return sorted(batch.entries, key=lambda item: (-item.score, item.action_key))[0]


def frontier_row(request: Any, scorer: Any, source: Mapping[str, Any]) -> dict[str, Any] | None:
    observation = request.observation
    if request.window_key.phase.value != "draw":
        return None
    if len(observation.melds[observation.seat]) != 0:
        return None
    view = build_scoring_view(request)
    parent_top = top(scorer.score(view))
    if not parent_top.action_key.startswith("discard:"):
        return None
    actions = []
    for action in view.actions:
        if not action.action_key.startswith("discard:"):
            continue
        if (
            action.standard_shanten_after is None
            or action.seven_pairs_shanten_after is None
            or action.standard_useful_tiles is None
            or action.seven_pairs_useful_tiles is None
        ):
            continue
        actions.append(action_json(action))
    parent = next((row for row in actions if row["action_key"] == parent_top.action_key), None)
    if parent is None:
        return None
    alternatives = [
        row for row in actions
        if row["action_key"] != parent["action_key"]
        and int(row["seven_pairs_shanten_after"]) <= 2
        and route_compare(row, parent, "seven_pairs") > 0
    ]
    if not alternatives:
        return None
    alternatives.sort(key=lambda row: (
        int(row["seven_pairs_shanten_after"]),
        -int(row["seven_pairs_support_remaining"]),
        int(row["standard_shanten_after"]),
        -int(row["standard_support_remaining"]),
        str(row["action_key"]),
    ))
    best = alternatives[0]
    standard_cmp = route_compare(best, parent, "standard")
    request_json = decision_request_to_json(request)
    hand = [tile.code for tile in observation.my_hand]
    if observation.drawn_tile is not None:
        hand.append(observation.drawn_tile.code)
    counts = Counter(hand)
    return {
        "schema": "r18-p12-natural-seven-pairs-frontier-row/1",
        **dict(source),
        "request_sha256": value_digest(request_json),
        "request": request_json,
        "window_key": {
            "phase": request.window_key.phase.value,
            "seat": request.window_key.seat,
            "trigger_seq": request.window_key.trigger_seq,
        },
        "round_no": observation.round_no,
        "dealer": observation.seat == observation.dealer_seat,
        "remaining_tile_count": observation.remaining_tile_count,
        "wealth_count": counts[observation.rule_state.wealth_god.code],
        "pair_kinds": sum(value >= 2 for value in counts.values()),
        "triplet_kinds": sum(value >= 3 for value in counts.values()),
        "parent": parent,
        "seven_pairs_frontier": best,
        "standard_effect": ("better" if standard_cmp > 0 else
                            "worse" if standard_cmp < 0 else "same"),
        "eligible_alternatives": alternatives,
    }


def collect_source(source: Mapping[str, Any]) -> dict[str, Any]:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    parent_source = PARENT.read_text(encoding="utf-8")
    requests: list[Any] = []
    plans = natural.build_seat_stage_plans(
        contract=contract, opponent=str(source["mix"]),
        root_index=int(source["root_index"]), focal_seat=int(source["focal_seat"]),
        panel_seed=PANEL_SEED,
    )
    stage = natural.run_arm_stage(
        arm="p12-p5-natural-collector", plans=plans,
        candidate_scorer=ActionValueScorer(
            "r18-p12-p5-" + str(source["source_id"]), parent_source,
        ),
        opponent_policies=contract["panel"]["opponent_scenarios"][str(source["mix"])][
            "opponent_policies"
        ],
        versions_block=natural.stage.contract_versions_block(contract),
        step_limit=int(contract["stop"]["step_limit"]), value_limits=LIMITS,
        decision_observer=requests.append,
    )
    scorer = ActionValueScorer("r18-p12-frontier-" + str(source["source_id"]), parent_source)
    rows = [row for row in (
        frontier_row(request, scorer, source) for request in requests
    ) if row is not None]
    return {
        "source": dict(source), "status": stage["status"],
        "tables": len(stage.get("tables") or []), "observed_requests": len(requests),
        "frontier_rows": rows,
    }


def prepare() -> None:
    if OUT.exists():
        raise SystemExit("P12 目录已存在；拒绝覆盖")
    OUT.mkdir(parents=True)
    (_project_file(_PROJECT_ROOT, OUT / "sources")).mkdir()
    frozen = sources()
    write_json(_project_file(_PROJECT_ROOT, OUT / "sources.json"), {"schema": "r18-p12-sources/1", "sources": frozen})
    write_json(_project_file(_PROJECT_ROOT, OUT / "manifest.json"), {
        "schema": "r18-p12-manifest/1",
        "runtime": guard.capture(source_paths=[
            Path(__file__), Path(natural.__file__), PARENT, CONTRACT, _project_file(_PROJECT_ROOT, OUT / "sources.json"),
        ]),
        "parent_sha256": digest(PARENT), "contract_sha256": digest(CONTRACT),
        "panel_seed": PANEL_SEED,
        "development_roots": list(DEVELOPMENT_ROOTS), "hidden_roots": list(HIDDEN_ROOTS),
        "mixes": list(MIXES), "seats": list(SEATS), "source_units": len(frozen),
        "planned_tables": len(frozen) * 2, "workers": 8,
        "selection_contract": "门清摸牌弃牌窗口；存在七对向听/支持严格优于P5首选且七对向听<=2的动作",
        "split_contract": "先按root_index冻结development/hidden；同一来源根及后续隐藏分配不得跨组",
        "outcome_blind": True, "development_only": True,
        "selection_eligible": False, "release_eligible": False,
    })
    print(json.dumps({"status": "PREPARED", "sources": len(frozen),
                      "tables": len(frozen) * 2}, ensure_ascii=False))


def verify() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    manifest = json.loads((_project_file(_PROJECT_ROOT, OUT / "manifest.json")).read_text())
    guard.verify(manifest["runtime"])
    frozen = json.loads((_project_file(_PROJECT_ROOT, OUT / "sources.json")).read_text())["sources"]
    return manifest, frozen


def run() -> None:
    manifest, frozen = verify()
    failures = []
    with concurrent.futures.ProcessPoolExecutor(max_workers=manifest["workers"]) as pool:
        futures = {pool.submit(collect_source, source): source for source in frozen}
        for completed, future in enumerate(concurrent.futures.as_completed(futures), 1):
            source = futures[future]
            try:
                row = future.result()
                if row["status"] != "complete" or row["tables"] != 2:
                    raise RuntimeError("自然来源未完整执行")
                write_json(_project_file(_PROJECT_ROOT, OUT / "sources" / (str(source["source_id"]).replace(":", "-") + ".json")), row)
            except Exception as exc:  # noqa: BLE001
                failures.append({"source_id": source["source_id"],
                                 "error": type(exc).__name__ + ": " + str(exc)})
            if completed % 8 == 0:
                print(json.dumps({"completed_sources": completed,
                                  "planned_sources": len(frozen)}, ensure_ascii=False), flush=True)
    write_json(_project_file(_PROJECT_ROOT, OUT / "run-summary.json"), {"completed": len(frozen) - len(failures),
                                           "planned": len(frozen), "failures": failures})
    if failures:
        raise RuntimeError("P12 自然采集存在失败")


def analyze() -> None:
    manifest, frozen = verify()
    source_rows = [json.loads(path.read_text()) for path in sorted((_project_file(_PROJECT_ROOT, OUT / "sources")).glob("*.json"))]
    if len(source_rows) != len(frozen):
        raise ValueError("P12 来源不完整")
    rows = [row for source in source_rows for row in source["frontier_rows"]]
    hashes = [row["request_sha256"] for row in rows]
    if len(hashes) != len(set(hashes)):
        raise ValueError("自然竞争窗口 request_sha256 重复")
    by_split = {
        split: [row for row in rows if row["split"] == split]
        for split in ("development", "hidden")
    }
    write_json(_project_file(_PROJECT_ROOT, OUT / "dataset.json"), {"schema": "r18-p12-dataset/1", "rows": rows})
    write_json(_project_file(_PROJECT_ROOT, OUT / "result.json"), {
        "schema": "r18-p12-result/1", "status": "COMPLETE_P12_NATURAL_FRONTIER",
        "mechanical_ok": True, "sources": len(source_rows),
        "tables": sum(source["tables"] for source in source_rows),
        "observed_requests": sum(source["observed_requests"] for source in source_rows),
        "frontier_windows": len(rows),
        "by_split": {split: len(items) for split, items in by_split.items()},
        "by_standard_effect": dict(Counter(row["standard_effect"] for row in rows)),
        "source_roots_disjoint": not (
            {row["root_index"] for row in by_split["development"]}
            & {row["root_index"] for row in by_split["hidden"]}
        ),
        "request_hashes_unique": len(hashes) == len(set(hashes)),
        "next_gate": "按split分别冻结基础状态并做共同隐藏世界多臂当前局教师；hidden标签在候选冻结前不得用于选择",
        "development_only": True, "selection_eligible": False, "release_eligible": False,
    })
    print(json.dumps(json.loads((_project_file(_PROJECT_ROOT, OUT / "result.json")).read_text()), ensure_ascii=False, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("prepare", "run", "analyze"))
    command = parser.parse_args().command
    if command == "prepare": prepare()
    elif command == "run": run()
    else: analyze()


if __name__ == "__main__":
    main()
