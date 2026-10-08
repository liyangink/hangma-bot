#!/usr/bin/env python3
"""G248：G233 已看正反例的双臂合法行动与自然牌形时间线。"""

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

from hashlib import sha256
import json
from pathlib import Path

import g178_natural_vs_standard_support as natural
import g182_full_table_branch_preflight as branch
import g223_visible_multi_action_route as g223
import g233_inversion_same_world_branch as g233
import g95_wider_discard_same_hand_preflight as g95
from hangma_bot.hangma.engine import _build_context
from hangma_bot.hangma.public_tile_counts import count_unseen_tiles


HERE = Path(__file__).resolve().parent
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g248-paired-route-timelines-20260929/result.json')
CASES = (("H", 3, "g233-08"), ("H", 6, "g233-14"),
         ("M", 1, "g233-03"))


def digest(path: Path) -> str:
    """结果绑定冻结同世界窗口和本程序字节。"""

    return sha256(path.read_bytes()).hexdigest()


class TracePolicy:
    """只保存本人请求引用；牌形在桌结束后复算，避免占用动作预算。"""

    def __init__(self, inner, sink: list[tuple], target_round: int) -> None:
        self.inner = inner
        self.sink = sink
        self.target_round = target_round
        self.policy_id = getattr(inner, "policy_id", None)
        self.max_operations = getattr(inner, "max_operations", None)

    async def choose(self, request, budget):
        """仅保存目标单局的玩家可见事实和生产合法首选。"""

        plan = await self.inner.choose(request, budget)
        if request.window_key.round_no != self.target_round:
            return plan
        self.sink.append((request, plan))
        return plan


def expand_trace(records: list[tuple], forced_key: str | None) -> list[dict]:
    """离开动作窗口后，仅凭保存的 PlayerObservation 复算自然牌形。"""

    output = []
    for index, (request, plan) in enumerate(records):
        if not plan.candidates:
            raise ValueError("G248 目标单局父代计划为空")
        key = forced_key if index == 0 and forced_key is not None else plan.candidates[0].action_key
        legal = {item.action_key: item for item in request.rules.legal_candidates}
        if key not in legal or len(legal) != len(request.rules.legal_candidates):
            raise ValueError("G248 父代首选不在生产合法动作集合")
        observation = request.observation
        full = _build_context(observation).full_hand()
        entry = {
            "trigger_seq": request.trigger_seq,
            "phase": request.window_key.phase.value,
            "drawn_tile": None if observation.drawn_tile is None
                          else observation.drawn_tile.code,
            "action_key": key,
            "white_before": sum(tile.code == "白" for tile in full),
            "chain_before": observation.rule_state.chain_count,
            "chain_piao_before": observation.chain_piao,
            "baotou_before": observation.rule_state.baotou,
        }
        if key.startswith("discard:"):
            facts = legal[key].facts
            root = natural._drop(full, key.split(":", 1)[1])
            entry["white_after"] = sum(tile.code == "白" for tile in root)
            try:
                unseen = count_unseen_tiles(observation)
                need, support = natural.natural(
                    root, unseen, len(observation.melds[observation.seat]))
            except ValueError as error:
                if index == 0:
                    raise
                entry["natural_status"] = type(error).__name__ + ": " + str(error)
            else:
                entry.update({
                    "natural_status": "complete",
                    "natural_need_after": need,
                    "natural_support_types": len(support),
                    "natural_support_public_capacity": sum(support.values()),
                })
            if (facts is None or type(facts.standard_shanten_after) is not int
                    or type(facts.seven_pairs_shanten_after) is not int):
                if index == 0:
                    raise ValueError("G248 目标根弃牌规则事实未知")
                entry["rule_fact_status"] = "unknown"
            else:
                entry.update({
                    "rule_fact_status": "complete",
                    "standard_shanten_after": facts.standard_shanten_after,
                    "seven_pairs_shanten_after": facts.seven_pairs_shanten_after,
                    "baotou_after": facts.baotou_after,
                })
        output.append(entry)
    return output


def one(mix: str, root: int, sample_key: str, contract: dict,
        versions: dict) -> dict:
    """同一不可变世界的两臂续桌与 G233 保存结果逐项恒等。"""

    selected = [(index, item) for index, item in enumerate(g233.selected(), 1)
                if (item["mix"], item["root_index"]) == (mix, root)]
    if len(selected) != 1:
        raise ValueError("G248 指定窗口身份不唯一")
    index, target = selected[0]
    source_path = g233.OUT / "windows" / f"window-{index:02d}.json"
    frozen = json.loads((g233.OUT / "result.json").read_text(encoding="utf-8"))
    if (frozen.get("schema") != "g233-inversion-same-world-result/1"
            or frozen["window_sha256"].get(source_path.name) != digest(source_path)):
        raise ValueError("G248 G233 逐窗摘要与冻结汇总不一致")
    source = json.loads(source_path.read_text(encoding="utf-8"))
    source_hashes = {
        "g223_stage": digest(g223.stage_path(
            mix, root, target["start_seat"])),
        "g224_stage": digest(g233.g224.stage_path(
            mix, root, target["start_seat"])),
    }
    if source["source_sha256"] != source_hashes:
        raise ValueError("G248 G223/G224 行动前来源摘要漂移")
    pairs = [item for item in source["paired_worlds"]
             if item["sample_key"] == sample_key]
    if len(pairs) != 1:
        raise ValueError("G248 指定相关世界缺失")
    expected = pairs[0]
    plan = g223.panel.natural.build_seat_stage_plans(
        contract=contract, opponent=mix, root_index=root,
        focal_seat=target["start_seat"], panel_seed=g223.SEED)[0]
    old_capture, old_policies = g95.CaptureWiderPolicy, g95.policies_for
    try:
        g95.CaptureWiderPolicy = lambda inner, engine: g233.CaptureExactPolicy(
            inner, engine, target)
        g95.policies_for = g233.parent_policies
        captured, runtime, rules, situation, hands, _ = g95.run_full(
            plan, contract, versions, mix)
        if captured.world is None or captured.request is None:
            raise ValueError("G248 原父代没有到达固定目标窗")
        world = runtime["engine"].resample_public_consistent_hidden_world(
            captured.world, focal_seat=target["seat"], sample_key=sample_key)
        if (runtime["engine"].frame(world).decisions[0].observation
                != captured.request.observation):
            raise ValueError("G248 同世界采样改变本人行动前观察")
        arms = {}
        for name, forced_key in (("parent", None),
                                 ("alternate", captured.alternate_key)):
            records: list[tuple] = []

            def traced_policies(plan, contract, clock, mix):
                policies = list(g233.parent_policies(plan, contract, clock, mix))
                policies[target["seat"]] = TracePolicy(
                    policies[target["seat"]], records, target["round_no"])
                return tuple(policies)

            g95.policies_for = traced_policies
            result = branch.run_branch(
                world=world, record=captured, plan=plan, contract=contract,
                versions=versions, runtime=runtime, rules=rules,
                situation=situation, mix=mix, forced_key=forced_key,
                prefix_hands=hands[:target["round_no"] - 1])
            trace = expand_trace(records, forced_key)
            original = expected[name]
            target_hand = {field: result["hands"][target["round_no"] - 1][field]
                           for field in branch.SETTLEMENT_FIELDS}
            if (target_hand != original["target_hand"]
                    or result["final_scores"] != original["final_scores"]
                    or result["account"] != original["account"]):
                raise ValueError("G248 带只读追踪的双臂结算与 G233 不恒等")
            chosen = [
                {"trigger_seq": window["trigger_seq"], "phase": window["phase"],
                 "action_key": key}
                for window, key in result["decisions"]
                if window["round_no"] == target["round_no"]
                and window["seat"] == target["seat"]
            ]
            if ([{key: row[key] for key in ("trigger_seq", "phase", "action_key")}
                 for row in trace] != chosen):
                raise ValueError("G248 只读追踪与实际本人动作序列不一致")
            arms[name] = {
                "target_class": original["target_class"],
                "target_focal_score_delta": target_hand["score_delta"][target["seat"]],
                "complete_table_focal_delta": result["account"]["focal_table_delta"],
                "own_draw_windows": sum(row["phase"] == "draw"
                                        and row["drawn_tile"] is not None
                                        for row in trace),
                "own_no_draw_followups": sum(row["phase"] == "draw"
                                             and row["drawn_tile"] is None
                                             for row in trace),
                "own_nonpass_claims": sum(row["phase"] != "draw"
                                          and row["action_key"] != "pass"
                                          for row in trace),
                "focal_timeline": trace,
            }
        return {
            "mix": mix, "root_index": root, "sample_key": sample_key,
            "target": {name: target[name] for name in (
                "table_id", "round_no", "snapshot_seq", "seat", "parent_action")},
            "alternate_action": target["representative_inversion"]["action"],
            "focal_complete_table_delta_alt_minus_parent": expected[
                "focal_complete_table_delta"],
            "arms": arms, "g233_window_sha256": digest(source_path),
        }
    finally:
        g95.CaptureWiderPolicy, g95.policies_for = old_capture, old_policies


def main() -> None:
    """已知反例只作路径测量，不把后验时点当线上触发条件。"""

    if OUT.exists():
        raise FileExistsError("G248 结果已存在，不覆盖")
    contract = json.loads(g95.g93.paired.CONTRACT.read_text(encoding="utf-8"))
    versions = g95.g93.natural.stage.contract_versions_block(contract)
    rows = [one(mix, root, sample, contract, versions)
            for mix, root, sample in CASES]
    payload = {
        "schema": "g248-paired-route-timeline-audit/1",
        "source_sha256": {
            "script": digest(Path(__file__)),
            "g233_result": digest(g233.OUT / "result.json"),
            "g233_manifest": digest(g233.OUT / "manifest.json"),
            "g178_natural_math": digest(Path(natural.__file__)),
            "g182_branch": digest(Path(branch.__file__)),
        },
        "rows": rows,
        "boundary": "事后选取 G233 两负一正相关世界；仅解释合法路线、形状与到达时点，不是独立条件概率或候选收益。",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True,
                              indent=2) + "\n", encoding="utf-8")
    print(json.dumps([{
        "mix": row["mix"], "root": row["root_index"],
        "delta": row["focal_complete_table_delta_alt_minus_parent"],
        "draws": {arm: value["own_draw_windows"]
                  for arm, value in row["arms"].items()},
    } for row in rows], ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
