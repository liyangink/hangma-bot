#!/usr/bin/env python3
"""G126：结果盲采集全正常摸打窗口的严格宽面冲突。"""

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
import json
import math
import os
from pathlib import Path
from types import SimpleNamespace

import g87_post_claim_score_trace as g87
import g95_wider_discard_same_hand_preflight as g95
import g108_fresh_hm_route_exposure as g108
from hangma_bot.kernel.serialization import observation_to_json, window_key_to_json


HERE = Path(__file__).resolve().parent
PREREG = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/G126-ALL-DRAW-NATURAL-WIDTH-EXPOSURE-PREREG-2026-09-28.md')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g126-all-draw-natural-width-exposure-20260928')
PANEL_SEED = 2026111501
ROOTS = tuple(range(1, 33))


class CaptureEveryHandAllDrawPolicy(g95.CaptureWiderPolicy):
    """保留 G95 判据，去掉已吃碰限制；每单局仍只取首次命中。"""

    def __init__(self, inner, capture_engine):
        super().__init__(inner, capture_engine)
        self.records = {}

    async def choose(self, request, budget):
        """先由冻结父代决策，再只读当前合法弃牌与依法可见普通型事实。"""
        round_no = request.window_key.round_no
        if round_no not in self.records and self.world is not None:
            self.world = None
            self.request = None
            self.parent_key = None
            self.alternate_key = None
            self.facts = {}
        plan = await self.inner.choose(request, budget)
        if self.world is not None or request.window_key.phase is not g95.g93.WindowPhase.DRAW:
            return plan
        if not plan.candidates:
            return plan
        parent = plan.candidates[0].action_key
        if not parent.startswith("discard:") or parent == "discard:白":
            return plan
        entries = {candidate.action_key: candidate.facts
                   for candidate in request.rules.legal_candidates}
        parent_facts = entries.get(parent)
        if parent_facts is None or type(parent_facts.standard_shanten_after) is not int:
            return plan

        def width(action_key: str) -> tuple[int, int]:
            """规则有效码与公开未见物理容量，不是牌墙概率。"""
            useful = entries[action_key].standard_useful_tiles or ()
            return len(useful), sum(tile.remaining_estimate for tile in useful)

        parent_width = width(parent)
        eligible = []
        for ranked in plan.candidates[1:]:
            key = ranked.action_key
            facts = entries.get(key)
            if (not key.startswith("discard:") or key == "discard:白"
                    or facts is None
                    or facts.standard_shanten_after != parent_facts.standard_shanten_after):
                continue
            codes, capacity = width(key)
            if codes > parent_width[0] and capacity > parent_width[1]:
                eligible.append(key)
        if not eligible:
            return plan
        alternate = min(eligible, key=lambda key: (-width(key)[0], -width(key)[1], key))
        if self.capture_engine.latest_world is None:
            raise ValueError("G126 当前决策缺模拟器世界引用")
        self.world = self.capture_engine.latest_world
        self.request = request
        self.parent_key = parent
        self.alternate_key = alternate
        self.facts = {
            key: {"standard_shanten_after": entries[key].standard_shanten_after,
                  "ordinary_codes": width(key)[0],
                  "public_unseen_capacity": width(key)[1]}
            for key in (parent, alternate)
        }
        self.records[round_no] = SimpleNamespace(
            world=self.world, request=self.request, parent_key=parent,
            alternate_key=alternate, facts=self.facts)
        return plan


def plans(contract: dict) -> list[tuple[str, int, int, object]]:
    """固定新根、H/M 交错与四座换位的父代表清单。"""
    result = []
    for root_index in ROOTS:
        for mix in ("H", "M"):
            for seat in range(4):
                plan = g95.g93.natural.build_seat_stage_plans(
                    contract=contract, opponent=mix, root_index=root_index,
                    focal_seat=seat, panel_seed=PANEL_SEED)[0]
                result.append((mix, root_index, seat, plan))
    return result


def scored_target(record, scorer) -> dict:
    """只保存动作前观察、生产牌效和冻结父代评分分量。"""
    request = record.request
    observation = request.observation
    parent, alternate = record.parent_key, record.alternate_key
    view = g87.g05.build_scoring_view(
        request, value_limits=g87.c31.VALUE_LIMITS).candidate_view()
    scored = scorer(view)
    if scored["status"] != "SCORED":
        raise ValueError("G126 父代未产生完整评分")
    entries = {entry["action_key"]: entry for entry in scored["entries"]}
    scores = {key: float(entry["score"]) for key, entry in entries.items()}
    if (g87.argmax(scores) != parent or parent not in entries
            or alternate not in entries):
        raise ValueError("G126 父代评分与完整桌执行动作不一致")
    gap = scores[parent] - scores[alternate]
    if not math.isfinite(gap) or gap < -1e-8:
        raise ValueError("G126 父代评分差非法")
    components = {name: g87.component(entries[parent]["trace"], name)
                  - g87.component(entries[alternate]["trace"], name)
                  for name in g87.COMPONENTS}
    if abs(sum(components.values()) - gap) > 1e-8:
        raise ValueError("G126 评分分量不守恒")
    own_claims = sum(meld.kind in ("chi", "peng")
                     for meld in observation.melds[observation.seat])
    white = (sum(tile.code == "白" for tile in observation.my_hand)
             + int(observation.drawn_tile is not None
                   and observation.drawn_tile.code == "白"))
    return {
        "round_no": request.window_key.round_no,
        "window_key": window_key_to_json(request.window_key),
        "observation_sha256": g108.canonical_sha(observation_to_json(observation)),
        "parent_action": parent, "alternate_action": alternate,
        "visible_action_facts": record.facts,
        "score_facts": {
            "parent_score_gap": gap,
            "component_parent_minus_alternate": components,
            "ordinary_codes_delta": record.facts[alternate]["ordinary_codes"]
                                     - record.facts[parent]["ordinary_codes"],
            "public_unseen_capacity_delta":
                record.facts[alternate]["public_unseen_capacity"]
                - record.facts[parent]["public_unseen_capacity"],
            "standard_shanten_after": record.facts[parent]["standard_shanten_after"],
            "own_chi_peng_count": own_claims,
            "white_before": white,
            "remaining_tile_count": observation.remaining_tile_count,
        },
    }


def run_table(mix: str, root_index: int, seat: int, plan,
              contract: dict, versions: dict, scorer) -> dict:
    """完整父代桌只作目标窗来源，不用单局得分挑选窗口。"""
    original = g95.CaptureWiderPolicy
    g95.CaptureWiderPolicy = CaptureEveryHandAllDrawPolicy
    try:
        captured, _, _, _, hands, _ = g95.run_full(plan, contract, versions, mix)
    finally:
        g95.CaptureWiderPolicy = original
    if (not isinstance(captured, CaptureEveryHandAllDrawPolicy)
            or len(hands) != int(versions["rounds_per_game"])):
        raise ValueError("G126 冻结父代表未完整完成")
    targets = [scored_target(captured.records[number], scorer)
               for number in sorted(captured.records)]
    return {"mix": mix, "root_index": root_index, "focal_seat": seat,
            "table_id": plan.table_id, "seed": plan.seed,
            "status": "complete", "hands": len(hands), "target_windows": targets}


def manifest(contract_path: Path) -> dict:
    """以摘要冻结新面板、规则/评分代码和采集器。"""
    paths = {"prereg": PREREG, "script": Path(__file__),
             "contract": contract_path, "g95": Path(g95.__file__),
             "g87": Path(g87.__file__), "g93": Path(g95.g93.__file__)}
    return {"schema": "g126-all-draw-natural-width-manifest/1",
            "panel_seed": PANEL_SEED, "roots": list(ROOTS),
            "tables_planned": len(ROOTS) * 2 * 4,
            "parent_scorer_sha256": g87.c31.R18_INTEGRATED_POSITIVE_V2_SHA256,
            "input_sha256": {name: g95.sha(path) for name, path in paths.items()},
            "boundary": "只保存父代真实轨迹的行动前事实；未来与结算不得用于选样。"}


def summary(rows: list[dict], planned: int) -> dict:
    """以桌和目标窗分账，不把同一牌山上的窗口视为独立收益样本。"""
    by_mix = {}
    for mix in ("H", "M"):
        group = [row for row in rows if row["mix"] == mix]
        targets = [target for row in group for target in row["target_windows"]]
        by_mix[mix] = {
            "tables": len(group), "roots": len({row["root_index"] for row in group}),
            "target_windows": len(targets),
            "by_claim_count": {
                str(count): sum(target["score_facts"]["own_chi_peng_count"] == count
                                for target in targets)
                for count in (0, 1, 2, 3, 4)},
            "by_shanten": {
                str(count): sum(target["score_facts"]["standard_shanten_after"] == count
                                for target in targets)
                for count in (0, 1, 2, 3, 4)},
            "one_shanten_by_claim": {
                str(count): sum(target["score_facts"]["standard_shanten_after"] == 1
                                and target["score_facts"]["own_chi_peng_count"] == count
                                for target in targets)
                for count in (0, 1, 2, 3, 4)},
        }
    return {"schema": "g126-all-draw-natural-width-summary/1",
            "status": "complete" if len(rows) == planned else "in_progress",
            "tables_completed": len(rows), "tables_planned": planned,
            "by_mix": by_mix,
            "boundary": "行动前真实暴露；无备选续打、无因果增益或候选证明。"}


def main() -> None:
    """逐桌落盘，可从同一清单的精确前缀续跑。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run-first", action="store_true")
    parser.add_argument("--max-new", type=int, default=0)
    args = parser.parse_args()
    contract_path = g95.g93.paired.CONTRACT
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    versions = g95.g93.natural.stage.contract_versions_block(contract)
    all_plans = plans(contract)
    expected = manifest(contract_path)
    if len(all_plans) != expected["tables_planned"]:
        raise ValueError("G126 面板张数不守恒")
    scorer = g87.c31.load_parent()
    if args.dry_run_first:
        mix, root_index, seat, plan = all_plans[0]
        row = run_table(mix, root_index, seat, plan, contract, versions, scorer)
        print(json.dumps({"mix": mix, "root": root_index, "seat": seat,
                          "targets": len(row["target_windows"])}, ensure_ascii=False))
        return
    OUT.mkdir(parents=True, exist_ok=True)
    manifest_path = _project_file(_PROJECT_ROOT, OUT / "manifest.json")
    if manifest_path.exists():
        if json.loads(manifest_path.read_text(encoding="utf-8")) != expected:
            raise ValueError("G126 现有清单漂移，拒绝混写")
    else:
        manifest_path.write_text(json.dumps(expected, ensure_ascii=False,
                                            sort_keys=True, indent=2) + "\n", encoding="utf-8")
    rows_path = _project_file(_PROJECT_ROOT, OUT / "rows.jsonl")
    rows = ([json.loads(line) for line in rows_path.read_text(encoding="utf-8").splitlines()]
            if rows_path.exists() else [])
    for old, (mix, root_index, seat, plan) in zip(rows, all_plans):
        if (old["mix"], old["root_index"], old["focal_seat"], old["table_id"]) != (
                mix, root_index, seat, plan.table_id):
            raise ValueError("G126 已有桌不是冻结计划前缀")
    added = 0
    with rows_path.open("a", encoding="utf-8") as stream:
        for mix, root_index, seat, plan in all_plans[len(rows):]:
            row = run_table(mix, root_index, seat, plan, contract, versions, scorer)
            stream.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
            rows.append(row)
            added += 1
            if added % 8 == 0:
                print(json.dumps({"tables": len(rows), "by_mix": summary(rows, len(all_plans))["by_mix"]},
                                 ensure_ascii=False, sort_keys=True), flush=True)
            if args.max_new > 0 and added >= args.max_new:
                break
    result = summary(rows, len(all_plans))
    (_project_file(_PROJECT_ROOT, OUT / "result.json")).write_text(json.dumps(result, ensure_ascii=False,
                                          sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
