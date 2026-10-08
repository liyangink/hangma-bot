#!/usr/bin/env python3
"""G283 量具小样本：仅用 G258/G61 与本地来源的动作前缀、生产规则。

按 G258 原行序，腾蛇和玄武各取前三个不同物理房的逐码等支持窗，
两强手交替排列。官方赛后事件只核已执行弃牌身份；不读取后续事件、
终局分或隐藏牌墙来生成特征。输出文件必须尚不存在。
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
from collections import Counter
from dataclasses import asdict
import glob
import hashlib
import json
from pathlib import Path
import sys
from time import perf_counter

HERE = Path(__file__).resolve().parent
ROOT = _PROJECT_ROOT
sys.path[:0] = [str(_project_file(_PROJECT_ROOT, ROOT / "src")), str(HERE), str(_project_file(_PROJECT_ROOT, ROOT / "review/baotou-anatomy-20260925"))]

import c31_action_layer_gap as c31  # noqa: E402
import g05_strong_draw_reconstruction as g05  # noqa: E402
from hangma_bot.hangma.engine import HangmaRules  # noqa: E402
from hangma_bot.kernel.config import RuleConfig  # noqa: E402
from hangma_bot.kernel.serialization import observation_from_json  # noqa: E402
from hangma_bot.policy.action_value_seeds import ActionValueScorer  # noqa: E402

G258 = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g258-postclaim-action-pairs-20260929')
G61 = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g61-strong-draw-action-atlas-20260927')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g283-postclaim-route-pilot-20260929/result.json')
PEERS = ("tengshe_0638", "xuanwu_2346")


def digest(path: Path) -> str:
    """给本地冻结输入记 SHA-256；不修改原件。"""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path: Path) -> dict:
    """只读取白名单内的本地 JSON。"""
    return json.loads(path.read_text(encoding="utf-8"))


def select_rows() -> tuple[list[dict], dict]:
    """按预定机械顺序选样，并核 G258 的 222/144 分母。"""
    result = read_json(_project_file(_PROJECT_ROOT, G258 / "result.json"))
    source = _project_file(_PROJECT_ROOT, G258 / "target_pairs.jsonl")
    if (result["evidence_sha256"][source.name] != digest(source)
            or result["source_sha256"]["g61"] != digest(_project_file(_PROJECT_ROOT, G61 / "result.json"))
            or result["result_blind"] is not True):
        raise ValueError("G258 结果盲源摘要漂移")
    rows = [json.loads(line) for line in source.open(encoding="utf-8")]
    support = [row for row in rows if row["action_pair"]["ordinary_parent_by_tile"]
               == row["action_pair"]["ordinary_alternate_by_tile"]]
    no_old = sum(all(top != row["strong_action"] for top in row["old_tops"].values())
                 for row in support)
    if (len(rows), len(support), no_old) != (1083, 222, 144):
        raise ValueError("G258 1083/222/144 分母漂移")
    by_peer = {peer: [] for peer in PEERS}
    seen_rooms: set[str] = set()
    for row in support:
        if row["room"] not in seen_rooms and len(by_peer[row["peer"]]) < 3:
            by_peer[row["peer"]].append(row)
            seen_rooms.add(row["room"])
    if any(len(rows) != 3 for rows in by_peer.values()) or len(seen_rooms) != 6:
        raise ValueError("固定六房样本不完整")
    chosen = [by_peer[peer][index] for index in range(3) for peer in PEERS]
    return chosen, {"targets": len(rows), "equal_support": len(support),
                    "no_old_top_hit": no_old, "by_peer": dict(Counter(r["peer"] for r in support))}


def manifests(rooms: set[str]) -> dict[str, tuple[Path, dict]]:
    """从 G61 来源房的本地审计清单取实际规则配置。"""
    found = {}
    for raw in glob.glob(str(_project_file(_PROJECT_ROOT, ROOT / "artifacts/sessions/*/audit/runs/*/manifest.json"))):
        path = Path(raw)
        doc = read_json(path)
        room = (doc.get("context") or {}).get("tournament_id")
        if room in rooms:
            if room in found:
                raise ValueError("样本房存在多个运行清单：" + room)
            found[room] = (path, doc)
    if set(found) != rooms:
        raise ValueError("样本房缺实际配置：" + repr(sorted(rooms - set(found))))
    return found


def archives(games: set[str]) -> dict[str, tuple[Path, dict]]:
    """只按本地下载源清单索引目标场，不扫描其他场事件内容。"""
    found = {}
    pattern = str(_project_file(_PROJECT_ROOT, ROOT / "artifacts/sessions/*/official/**/dl-*/source.json"))
    for raw in glob.glob(pattern, recursive=True):
        source = Path(raw)
        meta = read_json(source)
        game_id = meta.get("game_id")
        if game_id not in games:
            continue
        path = source.with_name("events.json")
        if not path.is_file():
            continue
        old = found.get(game_id)
        if old is None or path.stat().st_mtime_ns > old[0].stat().st_mtime_ns:
            found[game_id] = (path, meta)
    if set(found) != games:
        raise ValueError("样本场缺本地原始牌谱：" + repr(sorted(games - set(found))))
    return found


def prefix_observation(frozen: dict, events_path: Path, source_meta: dict):
    """只推进目标摸牌及之前事件，重建 G61 当时可见观察。"""
    doc = read_json(events_path)
    if (doc["room_id"] != frozen["room_id"] or doc["game_id"] != frozen["game_id"]
            or source_meta["game_id"] != frozen["game_id"]):
        raise ValueError("官方牌谱房/场身份不等")
    target_seq = frozen["draw_seq"]
    # 当前桌分只由本次动作前已经结束的单局积分累加；不触碰目标局
    # 的结算，也不把既往积分当未来路线结果。
    scores = [0, 0, 0, 0]
    past_settlements = 0
    for block in doc["blocks"]:
        if block["round_no"] >= frozen["round_no"]:
            continue
        for event in block.get("events", ()):
            if event["seq"] >= target_seq or event["type"] != "round_ended":
                continue
            delta = (event.get("data") or {}).get("scores")
            if not isinstance(delta, list) or len(delta) != 4:
                raise ValueError("已结束单局缺可见积分向量")
            scores = [old + int(change) for old, change in zip(scores, delta)]
            past_settlements += 1
    if past_settlements != frozen["round_no"] - 1 or scores != frozen["observation"]["scores"]:
        raise ValueError("行动前已知桌分与 G61 观察不等")
    blocks = [block for block in doc["blocks"] if block["round_no"] == frozen["round_no"]]
    starts = [block["start_hands"] for block in blocks
              if block.get("start_hands") and all(
                  isinstance(hand, list) for hand in block["start_hands"])]
    if len(starts) != 1:
        raise ValueError("目标单局起手牌缺失或重复")
    events = sorted((event for block in blocks for event in block.get("events", ())
                     if event["seq"] <= target_seq), key=lambda event: event["seq"])
    draw = next((event for event in events if event["seq"] == target_seq), None)
    if draw is None or draw["type"] != "tile_drawn" or draw["seat"] != frozen["seat"]:
        raise ValueError("目标触发摸牌事件漂移")
    snapshots = c31.reconstruct(events, starts[0], scores,
                                frozen["dealer_seat"])
    previous = max((seq for seq in snapshots if seq < target_seq), default=None)
    if previous is None:
        raise ValueError("目标摸牌之前没有公开弃牌快照")
    before = snapshots[previous]
    intervening = [event["type"] for event in events
                   if previous < event["seq"] < target_seq
                   and event["type"] not in ("pass", "timeout")]
    if (intervening or not before["rivers"][frozen["seat"]]
            or before["rivers"][frozen["seat"]][-1] == c31.WEALTH):
        raise ValueError("G05 非白弃牌后无实质事件的链=0 前提不成立")
    prior_own_discard = before["rivers"][frozen["seat"]][-1]
    if c31.progression.chain_after_discard(9, 4, True, c31.Tile(prior_own_discard)) != (0, 0):
        raise ValueError("生产动作链不能推出普通摸牌窗清零")
    rebuilt = g05.public_observation(
        before, draw, game_id=frozen["game_id"], round_no=frozen["round_no"],
        dealer=frozen["dealer_seat"], scores=scores,
    )
    original = observation_from_json(frozen["observation"])
    if rebuilt != original:
        raise ValueError("G61 行动前玩家可见观察与修正链前缀重建不等")
    return rebuilt, {"prior_discard_seq": previous, "prior_own_discard": prior_own_discard,
                     "prefix_event_count": len(events), "chain_count": original.rule_state.chain_count,
                     "chain_piao": original.chain_piao,
                     "past_settlements_for_current_scores": past_settlements}


def main() -> None:
    """按前缀、配置、规则、父代顺序对拍，再试生产公开后继。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUT)
    args = parser.parse_args()
    output = args.output
    if output.exists():
        raise FileExistsError("G283 pilot 证据已存在，拒绝覆盖")
    chosen, denominator = select_rows()
    g61 = read_json(_project_file(_PROJECT_ROOT, G61 / "result.json"))
    if g61["outcome_labels_opened"] is not False:
        raise ValueError("G61 来源不是结果盲")
    manifest_map = manifests({row["room"] for row in chosen})
    archive_map = archives({row["game_id"] for row in chosen})
    scorer = ActionValueScorer("g283-pilot-parent", c31.R18_INTEGRATED_POSITIVE_V2_SOURCE)
    evidence = []
    for row in chosen:
        peer, room = row["peer"], row["room"]
        unit = peer + "/" + room
        path = _project_file(_PROJECT_ROOT, G61 / "rooms" / f"{peer}--{room}" / "windows.json")
        if digest(path) != g61["units"][unit]["windows_sha256"]:
            raise ValueError("G61 逐房观察源摘要漂移")
        windows = read_json(path)["windows"]
        matches = [w for w in windows if (w["game_id"], w["round_no"], w["draw_seq"], w["seat"])
                   == (row["game_id"], row["round_no"], row["draw_seq"], row["seat"])]
        if len(matches) != 1:
            raise ValueError("G258 目标没有唯一 G61 观察")
        frozen = matches[0]
        if (frozen["actual_action"], frozen["parent_top_action"]) != (
                row["strong_action"], row["parent_action"]):
            raise ValueError("G258/G61 动作身份漂移")
        run_path, run = manifest_map[room]
        payload = run["payload"]
        config = RuleConfig(ruleset_version=payload["ruleset_version"],
                            base_score=payload["base_score"],
                            you_cai_bi_kao=payload["you_cai_bi_kao"])
        if (config.ruleset_version, config.base_score, config.you_cai_bi_kao) != (
                c31.RULE_CONFIG.ruleset_version, c31.RULE_CONFIG.base_score, False):
            raise ValueError("真实房配置与 G61 冻结规则环境不一致")
        archive_path, source_meta = archive_map[row["game_id"]]
        observation, chain_check = prefix_observation(frozen, archive_path, source_meta)
        replayed = g05.analysis_row(observation, {"tile": row["strong_action"].split(":", 1)[1]}, scorer)
        if (replayed["legal_action_keys"] != frozen["legal_action_keys"]
                or replayed["parent_top_action"] != frozen["parent_top_action"]
                or replayed["actual_action"] != frozen["actual_action"]):
            raise ValueError("修正链观察的生产合法候选或父代动作漂移")
        started = perf_counter()
        analysis = HangmaRules(config).analyze_public_self_draw_successors(observation)
        elapsed_ms = (perf_counter() - started) * 1000
        root_map = {root.action_key: root for root in analysis.roots}
        roots = {}
        for action in (row["parent_action"], row["strong_action"]):
            root = root_map.get(action)
            roots[action] = None if root is None else {
                "coverage": root.coverage.value,
                "conditional_draw_edges": len(root.edges),
                "edge_capacity_total": root.edge_capacity_total,
                "unrestricted_hu_edges": sum(e.unrestricted.hu_available for e in root.edges),
                "restricted_hu_edges": sum(e.restricted.hu_available for e in root.edges),
                "issues": [asdict(issue) for issue in root.issues],
            }
        evidence.append({
            "peer": peer, "room": room, "game_id": row["game_id"],
            "round_no": row["round_no"], "draw_seq": row["draw_seq"], "seat": row["seat"],
            "parent_action": row["parent_action"], "strong_action": row["strong_action"],
            "g61_observation_sha256": hashlib.sha256(json.dumps(
                frozen["observation"], ensure_ascii=False, sort_keys=True).encode()).hexdigest(),
            "prefix_reconstruction": chain_check,
            "actual_room_config": {"ruleset_version": config.ruleset_version,
                                   "base_score": config.base_score,
                                   "you_cai_bi_kao": config.you_cai_bi_kao},
            "public_successor": {"coverage": analysis.coverage.value,
                                  "elapsed_ms": round(elapsed_ms, 3),
                                  "root_count": len(analysis.roots),
                                  "roots": roots,
                                  "issues": [asdict(issue) for issue in analysis.issues]},
            "ordinary_one_fan_qualification_known": False,
            "ordinary_baotou_entry_known": False,
            "unknown_reason": "public_successor_only_exposes_hu_available_without_fan_or_baotou_qualification",
            "source_sha256": {"g61_windows": digest(path), "run_manifest": digest(run_path),
                              "source_json": digest(archive_path.with_name("source.json")),
                              "events_json": digest(archive_path)},
        })
    result = {
        "schema": "g283-postclaim-route-pilot/1", "result_blind": True,
        "selection": "G258 原行序，各强手首三个不同物理房的逐码等支持窗，腾蛇/玄武交替",
        "denominator": denominator, "sample_size": len(evidence), "rows": evidence,
        "source_sha256": {"g258_result": digest(_project_file(_PROJECT_ROOT, G258 / "result.json")),
                          "g258_pairs": digest(_project_file(_PROJECT_ROOT, G258 / "target_pairs.jsonl")),
                          "g61_result": digest(_project_file(_PROJECT_ROOT, G61 / "result.json")),
                          "c31": digest(Path(c31.__file__)),
                          "g05": digest(Path(g05.__file__)),
                          "public_successor": digest(_project_file(_PROJECT_ROOT, ROOT / "src/hangma_bot/hangma/public_successor.py")),
                          "script": digest(Path(__file__))},
        "conclusion": "The public successor API may return structural hu_available, but it does not expose ordinary one-fan qualification or ordinary baotou entry; no continuation score is computed.",
        "unknown": ["opponent_preemption", "future_wall_order", "future_catch_play_state",
                    "future_hu_fan_and_baotou_qualification_not_exposed", "counterfactual_result"],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as handle:
        json.dump(result, handle, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
        handle.write("\n")
    print(json.dumps({"sample_size": len(evidence),
                      "coverage": [r["public_successor"]["coverage"] for r in evidence],
                      "elapsed_ms": [r["public_successor"]["elapsed_ms"] for r in evidence]},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
