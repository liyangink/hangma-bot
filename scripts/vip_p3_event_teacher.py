"""按预冻结观察根生成全合法动作的互斥首次事件和完整单局教师账。

仅离线教师访问 WorldState。拟合、诊断和确认池按原始牌山种子隔离；
确认池必须先给出逐根预冻结预测清单。教师结局不可用作当下策略特征。
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
from collections import Counter
from pathlib import Path

from hangma_bot.hangma.engine import HangmaRules
from hangma_bot.hangma.interface import RuleCompleteness, ValueAnalysisLimits
from hangma_bot.kernel.config import RuleConfig, TimingConfig, TournamentConfig
from hangma_bot.kernel.serialization import observation_from_json
from hangma_bot.offline.vip_reference import choose_reference_action
from hangma_bot.simulation import MatchSpec, SimulationChoice, SimulationEngine

from scripts.vip_p3_first_event_preflight import _event_key, _finish_hand, _first_event


_WORLD_COUNT = {"fit": 4, "diagnostic": 8, "confirmation": 16}
_REFERENCES = ("shape", "r18_frozen")
_LIMITS = ValueAnalysisLimits(max_expansions=8192)


def _check_confirmation(predictions: dict | None, *, selection_sha256: str,
                        roots: list[dict]) -> None:
    """确认池教师不得先于完整动作预测冻结而打开。"""

    if predictions is None or (predictions.get("scope") !=
                               "vip_p3_event_confirmation_predictions_locked"
                               or predictions.get("selection_sha256") != selection_sha256):
        raise ValueError("确认池缺事前冻结的模型动作预测")
    by_id = {row["root_id"]: row for row in predictions.get("roots", ())}
    if len(by_id) != len(roots) or set(by_id) != {row["root_id"] for row in roots}:
        raise ValueError("确认池预测根数或身份不守恒")
    for root in roots:
        row = by_id[root["root_id"]]
        scores = row.get("scores_by_action")
        if (not isinstance(scores, dict)
                or set(scores) != set(root["legal_action_keys"])
                or any(type(value) not in (int, float) or not math.isfinite(value)
                       for value in scores.values())
                or row.get("chosen_action_key") not in scores):
            raise ValueError("确认池全部合法动作分数未事前冻结")


def teach(selection: dict, *, selection_sha256: str, split: str,
          predictions: dict | None = None) -> dict:
    """复走参考路径并对每个预选根强制全部合法首动作。"""

    if (selection.get("scope") !=
            "vip_p3_pre_outcome_event_root_selection_no_teacher_results"
            or selection.get("rule_config") != {"BaseScore": 1, "YouCaiBiKao": False}
            or selection.get("selection_reference") != "r18_frozen"
            or selection.get("scenario_prefix") != "vip-p3-event-frame"
            or selection.get("initial_dealer_rule") != "seed_mod_4"
            or selection.get("selected_root_count") != len(selection.get("selected_roots", ()))
            or split not in _WORLD_COUNT):
        raise ValueError("事件教师冻结选根配置、数量或池不符")
    roots = [row for row in selection["selected_roots"] if row["split"] == split]
    if not roots or len(roots) != selection["selected_split_counts"].get(split):
        raise ValueError("事件教师当前池根数与冻结计划不符")
    if split == "confirmation":
        _check_confirmation(predictions, selection_sha256=selection_sha256,
                            roots=roots)
    elif predictions is not None:
        raise ValueError("拟合/诊断池不消费确认预测包")
    by_seed = {}
    for row in roots:
        seed, revision = row["seed"], row["frame_revision"]
        if revision in by_seed.setdefault(seed, {}):
            raise ValueError("事件教师同一帧选中重复本座窗口")
        by_seed[seed][revision] = row
    rules = HangmaRules(RuleConfig("hangma-mvp-v10-public-counts", 1, False))
    engine = SimulationEngine(rules)
    rows = []
    event_counts = {ref: Counter() for ref in _REFERENCES}
    for seed in sorted(by_seed):
        spec = MatchSpec(
            match_id=f"{selection['scenario_prefix']}-{seed}",
            scenario_id=f"{selection['scenario_prefix']}-{seed}",
            config=TournamentConfig(1, 1, rules.config, TimingConfig(1.0, 1.0, 3.0)),
            seed=seed, initial_dealer=seed % 4,
            initial_scores=(0, 0, 0, 0),
        )
        world = engine.start(spec)
        reached = set()
        for _ in range(500):
            frame = engine.frame(world)
            if frame.blocked_reason is not None:
                raise ValueError("事件教师参考路径被模拟器阻塞: " + frame.blocked_reason)
            if frame.final_scores is not None:
                break
            target = by_seed[seed].get(frame.revision)
            if target is not None:
                mine = [item for item in frame.decisions
                        if item.window_key.seat == 0]
                if len(mine) != 1:
                    raise ValueError("预冻结事件根没有唯一本人动作窗口")
                decision = mine[0]
                observation = observation_from_json(target["observation"])
                if (decision.observation != observation
                        or target["root_id"] != hashlib.sha256(
                            repr(observation).encode()).hexdigest()
                        or target["initial_dealer"] != seed % 4
                        or observation.dealer_seat != seed % 4
                        or target["phase"] != observation.phase):
                    raise ValueError("事件教师观察与结果盲冻结根不符")
                analysis = rules.analyze(observation, route_limits=_LIMITS)
                candidates = analysis.legal_candidates
                keys = [item.action_key for item in candidates]
                if (analysis.completeness is not RuleCompleteness.COMPLETE
                        or analysis.conditional_roots is None
                        or len(analysis.conditional_roots) != len(candidates)
                        or any(root.gap_kind is not None
                               for root in analysis.conditional_roots)
                        or keys != target["legal_action_keys"]):
                    raise ValueError("冻结根全合法动作或 P2 条件根不完整")
                outcomes = {key: {ref: [] for ref in _REFERENCES} for key in keys}
                for sample in range(_WORLD_COUNT[split]):
                    hidden = engine.resample_public_consistent_hidden_world(
                        world, focal_seat=0,
                        sample_key=(f"vip-p3-event:{seed}:{frame.revision}:"
                                    f"{sample}"),
                    )
                    sampled_frame = engine.frame(hidden)
                    focal = [item for item in sampled_frame.decisions
                             if item.window_key == decision.window_key]
                    if len(focal) != 1 or focal[0].observation != observation:
                        raise ValueError("同根相关隐藏世界改变玩家观察")
                    for candidate in candidates:
                        after = engine.advance(hidden, sampled_frame.revision, tuple(
                            SimulationChoice(
                                item.window_key,
                                candidate.action if item.window_key == decision.window_key
                                else choose_reference_action(
                                    rules, item, mode=selection["selection_reference"]),
                            ) for item in sampled_frame.decisions
                        ))
                        for ref in _REFERENCES:
                            event = _first_event(
                                engine, rules, after, seat=observation.seat,
                                reference=ref, include_next_observation=True,
                            )
                            terminal = _finish_hand(engine, rules, after,
                                                    reference=ref)
                            if event["kind"] in ("self_win", "other_win", "draw") and (
                                event["score_delta"] != terminal["score_delta"]
                            ):
                                raise ValueError("首次终局与完整单局结算不一致")
                            event_counts[ref][event["kind"]] += 1
                            outcomes[candidate.action_key][ref].append({
                                "sample": sample,
                                "first_event_key": _event_key(event),
                                "first_event": event,
                                "terminal": terminal,
                            })
                rows.append({
                    "seed": seed, "frame_revision": frame.revision,
                    "root_id": target["root_id"], "phase": observation.phase,
                    "tags": target["tags"], "inclusion_probability": target[
                        "inclusion_probability"],
                    "sample_count": _WORLD_COUNT[split],
                    "observation": target["observation"],
                    "legal_action_keys": keys,
                    "outcomes_by_action_and_reference": outcomes,
                })
                reached.add(frame.revision)
            world = engine.advance(world, frame.revision, tuple(
                SimulationChoice(item.window_key,
                                 choose_reference_action(
                                     rules, item, mode=selection["selection_reference"]))
                for item in frame.decisions
            ))
        else:
            raise ValueError("事件教师参考路径超过 500 帧")
        if reached != set(by_seed[seed]):
            raise ValueError("冻结事件根未全部在同一参考路径到达")
    expected_worlds = sum(len(row["legal_action_keys"]) * row["sample_count"]
                          for row in rows)
    if (len(rows) != len(roots)
            or any(sum(counter.values()) != expected_worlds
                   for counter in event_counts.values())):
        raise ValueError("事件教师根、动作或互斥事件质量不守恒")
    return {
        "scope": "vip_p3_event_all_action_teacher_not_candidate_strength",
        "selection_sha256": selection_sha256,
        "rule_config": selection["rule_config"],
        "split": split, "continuation_references": list(_REFERENCES),
        "root_count": len(rows), "natural_seed_count": len(by_seed),
        "worlds_per_root": _WORLD_COUNT[split],
        "action_worlds_per_reference": expected_worlds,
        "event_counts_by_reference": {ref: dict(sorted(count.items()))
                                      for ref, count in event_counts.items()},
        "rows": rows,
    }


def _load_json(path: Path) -> dict:
    """读取纯 JSON 或 gzip JSON，路径只由调用者传入。"""

    raw = path.read_bytes()
    return json.loads(gzip.decompress(raw) if path.suffix == ".gz" else raw)


def _write_json(path: Path, payload: dict) -> None:
    """以确定性 gzip 头写证据文件，保证复算摘要稳定。"""

    data = (json.dumps(payload, ensure_ascii=False, sort_keys=True,
                       separators=(",", ":")) + "\n").encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix == ".gz":
        with path.open("wb") as raw:
            with gzip.GzipFile(fileobj=raw, mode="wb", filename="", mtime=0,
                               compresslevel=9) as stream:
                stream.write(data)
    else:
        path.write_bytes(data)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selection", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--split", choices=tuple(_WORLD_COUNT), required=True)
    parser.add_argument("--prediction-freeze", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    manifest = _load_json(args.manifest)
    if manifest.get("scope") != "vip_p3_event_pre_outcome_source_identity":
        raise ValueError("事件教师缺结果盲源码摘要清单")
    for item in manifest["files"]:
        if hashlib.sha256(Path(item["path"]).read_bytes()).hexdigest() != item["sha256"]:
            raise ValueError("事件教师冻结源码或抽样框摘要漂移: " + item["path"])
    raw = args.selection.read_bytes()
    selection = json.loads(gzip.decompress(raw) if args.selection.suffix == ".gz" else raw)
    predictions = (_load_json(args.prediction_freeze)
                   if args.prediction_freeze is not None else None)
    _write_json(args.output, teach(
        selection, selection_sha256=hashlib.sha256(raw).hexdigest(),
        split=args.split, predictions=predictions,
    ))


if __name__ == "__main__":
    main()
