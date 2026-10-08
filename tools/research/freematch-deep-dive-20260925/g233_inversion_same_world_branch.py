#!/usr/bin/env python3
"""G233：宽进张评分反转窗的同世界单次改弃完整桌续打。"""

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
from hashlib import sha256
import json
from pathlib import Path

import g182_full_table_branch_preflight as branch
import g210_post_claim_guarded_familiar_policy as g210
import g223_visible_multi_action_route as g223
import g224_g223_vector_replay as g224
import g232_base_width_inversion as g232
import g95_wider_discard_same_hand_preflight as g95
from hangma_bot.kernel.serialization import observation_from_json


HERE = Path(__file__).resolve().parent
PLAN = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/G233-INVERSION-SAME-WORLD-BRANCH-PREREG-2026-09-29.md')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g233-inversion-same-world-branch-20260929')
SAMPLES = ("historical",) + tuple(f"g233-{index:02d}" for index in range(1, 17))
FIELDS = branch.SETTLEMENT_FIELDS


def digest(path: Path) -> str:
    """给所有固定来源和逐窗分支保存 SHA-256。"""

    return sha256(path.read_bytes()).hexdigest()


def write_new(path: Path, value: dict) -> None:
    """原子落盘；已有不同证据不得被续跑覆盖。"""

    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    if path.exists():
        if path.read_text(encoding="utf-8") != encoded:
            raise FileExistsError(path)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(encoded, encoding="utf-8")
    temp.replace(path)


def selected() -> list[dict]:
    """只读 G232 行动前代表动作，每个 H/M×根取 t1 的首窗。"""

    source = json.loads(g232.OUT.read_text(encoding="utf-8"))
    if (source.get("schema") != "g232-base-width-inversion/1"
            or source.get("root_windows") != 2191
            or source.get("counts", {}).get("base_width_inversion_windows") != 32):
        raise ValueError("G232 行动前来源漂移")
    eligible = [row for row in source["rows"]
                if row["representative_inversion"] is not None
                and row["table_id"].endswith("-t1")]
    first = {}
    for row in sorted(eligible, key=lambda value: (
            value["mix"], value["root_index"], value["start_seat"],
            value["round_no"], value["snapshot_seq"])):
        first.setdefault((row["mix"], row["root_index"]), row)
    rows = [first[key] for key in sorted(first)]
    if (len(rows) != 9 or Counter(row["mix"] for row in rows)
            != Counter({"H": 5, "M": 4})):
        raise ValueError("G233 每根第一张桌首反转窗口数量漂移")
    return rows


def parent_policies(plan, contract, clock, mix):
    """与 G223 相同，按当前规则直接装配冻结 R18 评分源码。"""

    natural = g95.g93.natural
    logical = natural.arm_logical_policies(
        arm="candidate", candidate_scorer=None,
        logical_participants=plan.logical_participants,
        opponent_policies=contract["panel"]["opponent_scenarios"][mix]["opponent_policies"],
        monotonic=clock.now, candidate_policy_factory=g210.parent_factory)
    return natural.seat_policies_from(
        logical, plan.permutation, plan.logical_participants)


class CaptureExactPolicy:
    """只捕获固定行动前窗口的世界，不改变原父代动作。"""

    def __init__(self, inner, capture_engine, target: dict) -> None:
        self.inner = inner
        self.capture_engine = capture_engine
        self.target = target
        self.policy_id = getattr(inner, "policy_id", None)
        self.world = None
        self.request = None
        self.parent_key = None
        self.alternate_key = None

    async def choose(self, request, budget):
        """依单局、序号和座位核目标；父代计划逐字返回。"""

        plan = await self.inner.choose(request, budget)
        if (request.window_key.round_no != self.target["round_no"]
                or request.trigger_seq != self.target["snapshot_seq"]
                or request.observation.seat != self.target["seat"]):
            return plan
        if self.world is not None or not plan.candidates:
            raise ValueError("G233 目标窗口重复或父代无合法保底")
        parent = plan.candidates[0].action_key
        alternate = self.target["representative_inversion"]["action"]
        if (parent != self.target["parent_action"]
                or alternate not in {item.action_key for item in plan.candidates}
                or alternate not in {item.action_key
                                     for item in request.rules.legal_candidates}
                or self.capture_engine.latest_world is None):
            raise ValueError("G233 目标父代、备选或同帧世界漂移")
        self.world = self.capture_engine.latest_world
        self.request = request
        self.parent_key = parent
        self.alternate_key = alternate
        return plan


def archived_root(target: dict) -> tuple[dict, dict]:
    """读取 G223 原父代表及 G224 同窗玩家可见观察。"""

    unit = (target["mix"], target["root_index"], target["start_seat"])
    old = json.loads(g223.stage_path(*unit).read_text(encoding="utf-8"))
    new = json.loads(g224.stage_path(*unit).read_text(encoding="utf-8"))
    original = old["stage"]["tables"][0]
    matches = [root for root in new["roots"]
               if root["table_id"] == target["table_id"]
               and root["round_no"] == target["round_no"]
               and root["root_action"] == target["parent_action"]
               and root["observation"]["snapshot_seq"] == target["snapshot_seq"]]
    if (original["table_id"] != target["table_id"] or len(matches) != 1):
        raise ValueError("G223/G224 同窗来源缺失或不唯一")
    return original, matches[0]


def _settlement(hand: dict) -> dict:
    """只比较生产结算定义的八项字段。"""

    return {name: hand[name] for name in FIELDS}


def hand_class(hand: dict, seat: int) -> str:
    """目标单局只进入一个结算终点类别。"""

    if hand["is_draw"]:
        return "draw"
    if hand["winner_seat"] != seat:
        return "other_win"
    return "plain_self_win" if hand["details"] == ["平胡"] else "special_self_win"


def compact(outcome: dict, round_no: int, seat: int) -> dict:
    """只保存目标局与八局积分分解，避免复制内部世界。"""

    return {
        "target_hand": _settlement(outcome["hands"][round_no - 1]),
        "target_class": hand_class(outcome["hands"][round_no - 1], seat),
        "final_scores": outcome["final_scores"],
        "account": outcome["account"],
        "decision_count": outcome["decision_count"],
        "forced_once": outcome["forced_once"],
        "runtime_counts": outcome["runtime_counts"],
        "elapsed_ms": outcome["elapsed_ms"],
    }


def run_one(target: dict, contract: dict, versions: dict) -> dict:
    """完整复跑原父代，再对十七同世界各做双臂完整桌续打。"""

    mix, root, start_seat = (target[name] for name in
                             ("mix", "root_index", "start_seat"))
    plan = g223.panel.natural.build_seat_stage_plans(
        contract=contract, opponent=mix, root_index=root,
        focal_seat=start_seat, panel_seed=g223.SEED)[0]
    archived, root_visible = archived_root(target)
    old_capture, old_policies = g95.CaptureWiderPolicy, g95.policies_for
    g95.CaptureWiderPolicy = lambda inner, engine: CaptureExactPolicy(inner, engine, target)
    g95.policies_for = parent_policies
    try:
        captured, runtime, rules, situation, hands, original = g95.run_full(
            plan, contract, versions, mix)
        if captured.world is None or captured.request is None:
            raise ValueError("G233 原父代表未到达冻结目标窗口")
        if captured.request.observation != observation_from_json(root_visible["observation"]):
            raise ValueError("G233 捕获观察与 G224 保存观察不恒等")
        if (list(original.final_scores or ()) != archived["scores_by_seat"]
                or len(hands) != len(archived["hand_records"])
                or [_settlement(hand) for hand in hands]
                != [_settlement(hand) for hand in archived["hand_records"]]):
            raise ValueError("G233 原父代八局结算或终分与 G223 不恒等")
        focal_records = [item for item in original.decisions
                         if item.seat == captured.request.observation.seat]
        observed = [(item.window_key["round_no"], item.window_key["trigger_seq"],
                     item.action_key) for item in focal_records]
        expected = [(item["round_no"], item["trigger_seq"], item["chosen_action"])
                    for item in json.loads(g223.stage_path(mix, root, start_seat)
                                           .read_text(encoding="utf-8"))["captured_decisions"]
                    if item["game_id"] == plan.match_id]
        if observed != expected:
            raise ValueError("G233 原父代本人逐动作与 G223 不恒等")
        initial_observation = runtime["engine"].frame(
            captured.world).decisions[0].observation
        before = hands[:target["round_no"] - 1]
        pairs = []
        for sample in SAMPLES:
            world = (captured.world if sample == "historical" else
                     runtime["engine"].resample_public_consistent_hidden_world(
                         captured.world, focal_seat=target["seat"],
                         sample_key=sample))
            if runtime["engine"].frame(world).decisions[0].observation != initial_observation:
                raise ValueError("G233 隐藏世界重采样改变本人可见观察")
            parent = branch.run_branch(
                world=world, record=captured, plan=plan, contract=contract,
                versions=versions, runtime=runtime, rules=rules,
                situation=situation, mix=mix, forced_key=None,
                prefix_hands=before)
            alternate = branch.run_branch(
                world=world, record=captured, plan=plan, contract=contract,
                versions=versions, runtime=runtime, rules=rules,
                situation=situation, mix=mix, forced_key=captured.alternate_key,
                prefix_hands=before)
            if (parent["hands"][0]["scores_before"]
                    != alternate["hands"][0]["scores_before"]):
                raise ValueError("G233 双臂起点积分不同")
            if sample == "historical":
                if ([_settlement(hand) for hand in parent["hands"]]
                        != [_settlement(hand) for hand in hands]
                        or parent["final_scores"] != list(original.final_scores or ())
                        or parent["decisions"] != branch._decisions(
                            original, captured.request.window_key)):
                    raise ValueError("G233 历史世界父代分支不恒等")
            p = compact(parent, target["round_no"], target["seat"])
            a = compact(alternate, target["round_no"], target["seat"])
            pairs.append({
                "sample_key": sample,
                "focal_target_hand_delta": a["target_hand"]["score_delta"][target["seat"]]
                - p["target_hand"]["score_delta"][target["seat"]],
                "focal_complete_table_delta": a["final_scores"][target["seat"]]
                - p["final_scores"][target["seat"]],
                "parent": p, "alternate": a,
            })
        return {
            "schema": "g233-inversion-same-world-window/1",
            "identity": {name: target[name] for name in (
                "mix", "root_index", "start_seat", "table_id", "round_no",
                "snapshot_seq", "seat", "white_after", "standard_shanten_after",
                "parent_action")},
            "alternate_action": captured.alternate_key,
            "action_before_inversion": target["representative_inversion"],
            "source_sha256": {
                "g223_stage": digest(g223.stage_path(mix, root, start_seat)),
                "g224_stage": digest(g224.stage_path(mix, root, start_seat)),
            },
            "paired_worlds": pairs,
        }
    finally:
        g95.CaptureWiderPolicy, g95.policies_for = old_capture, old_policies


def summarize(rows: list[dict]) -> dict:
    """根等权拆前后半与目标单局互斥结局，不拟合候选权重。"""

    result = {}
    for mix in ("H", "M"):
        group = [row for row in rows if row["identity"]["mix"] == mix]
        roots = []
        transitions = Counter()
        for row in group:
            worlds = row["paired_worlds"]
            if [item["sample_key"] for item in worlds] != list(SAMPLES):
                raise ValueError("G233 分支样本键缺失或顺序漂移")
            for item in worlds:
                transitions[(item["parent"]["target_class"],
                             item["alternate"]["target_class"])] += 1
            sample = worlds[1:]
            root = {
                "root_index": row["identity"]["root_index"],
                "historical_table_delta": worlds[0]["focal_complete_table_delta"],
                "first_half_table_delta": sum(item["focal_complete_table_delta"]
                                              for item in sample[:8]) / 8,
                "second_half_table_delta": sum(item["focal_complete_table_delta"]
                                               for item in sample[8:]) / 8,
                "resampled_table_delta": sum(item["focal_complete_table_delta"]
                                             for item in sample) / 16,
                "resampled_target_hand_delta": sum(item["focal_target_hand_delta"]
                                                   for item in sample) / 16,
            }
            for name in ("plain_self_win_delta", "special_self_win_delta",
                         "other_win_delta", "draw_delta"):
                root["resampled_" + name] = sum(
                    item["alternate"]["account"][name]
                    - item["parent"]["account"][name]
                    for item in sample) / 16
            roots.append(root)
        def mean(name: str) -> float:
            return sum(row[name] for row in roots) / len(roots)
        result[mix] = {
            "independent_roots": len(roots),
            "root_equal_mean": {name: mean(name) for name in roots[0]
                                if name != "root_index"},
            "roots_positive_both_halves": sum(
                row["first_half_table_delta"] > 0
                and row["second_half_table_delta"] > 0 for row in roots),
            "target_class_transitions": {
                f"{old}->{new}": count
                for (old, new), count in sorted(transitions.items())},
            "per_root": roots,
        }
    return result


def main() -> None:
    """断点可续跑；未完成时不签发汇总。"""

    parser = argparse.ArgumentParser()
    parser.add_argument("--max-new", type=int, default=0)
    args = parser.parse_args()
    targets = selected()
    contract = json.loads(g95.g93.paired.CONTRACT.read_text(encoding="utf-8"))
    versions = g95.g93.natural.stage.contract_versions_block(contract)
    manifest = {
        "schema": "g233-inversion-same-world-manifest/1",
        "selected_windows": len(targets), "samples": list(SAMPLES),
        "source_sha256": {
            "prereg": digest(PLAN), "script": digest(Path(__file__)),
            "g232_result": digest(g232.OUT), "g224_result": digest(g224.OUT / "result.json"),
            "g223_result": digest(g223.OUT / "result.json"),
            "contract": digest(g95.g93.paired.CONTRACT),
            "g182_branch": digest(Path(branch.__file__)),
            "g95_runtime": digest(Path(g95.__file__)),
        },
        "selection": [{name: row[name] for name in (
            "mix", "root_index", "start_seat", "table_id", "round_no",
            "snapshot_seq", "seat", "white_after", "standard_shanten_after",
            "parent_action")} | {"alternate_action": row["representative_inversion"]["action"]}
                      for row in targets],
        "boundary": "九个已看行动前根、每窗十七相关隐藏世界的机制预检；不是独立策略收益。",
    }
    write_new(_project_file(_PROJECT_ROOT, OUT / "manifest.json"), manifest)
    added = 0
    for index, target in enumerate(targets, 1):
        path = _project_file(_PROJECT_ROOT, OUT / "windows" / f"window-{index:02d}.json")
        if path.exists():
            row = json.loads(path.read_text(encoding="utf-8"))
            if (row["identity"]["mix"], row["identity"]["root_index"],
                    row["alternate_action"]) != (
                    target["mix"], target["root_index"],
                    target["representative_inversion"]["action"]):
                raise ValueError("G233 既有窗口身份不符")
            continue
        row = run_one(target, contract, versions)
        write_new(path, row)
        added += 1
        print(json.dumps({"completed_windows": index,
                          "mix": target["mix"], "root": target["root_index"],
                          "mean_resampled_table_delta": sum(
                              item["focal_complete_table_delta"]
                              for item in row["paired_worlds"][1:]) / 16},
                         ensure_ascii=False), flush=True)
        if args.max_new > 0 and added >= args.max_new:
            break
    paths = [_project_file(_PROJECT_ROOT, OUT / "windows" / f"window-{index:02d}.json")
             for index in range(1, len(targets) + 1)]
    if not all(path.exists() for path in paths):
        print(json.dumps({"status": "in_progress",
                          "completed": sum(path.exists() for path in paths),
                          "planned": len(paths)}), flush=True)
        return
    if (_project_file(_PROJECT_ROOT, OUT / "result.json")).exists():
        raise FileExistsError("G233 汇总已存在，拒绝覆盖")
    rows = [json.loads(path.read_text(encoding="utf-8")) for path in paths]
    result = {
        "schema": "g233-inversion-same-world-result/1",
        "manifest_sha256": digest(_project_file(_PROJECT_ROOT, OUT / "manifest.json")),
        "window_sha256": {path.name: digest(path) for path in paths},
        "windows": len(rows), "paired_worlds": len(rows) * len(SAMPLES),
        "by_mix": summarize(rows),
        "boundary": manifest["boundary"],
    }
    write_new(_project_file(_PROJECT_ROOT, OUT / "result.json"), result)
    print(json.dumps({"status": "complete", "windows": len(rows),
                      "paired_worlds": result["paired_worlds"]},
                     ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
