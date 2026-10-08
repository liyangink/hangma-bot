"""用官方完整牌谱独立寻找未送入策略的基础碰/吃机会。

本工具按起手牌和官方事件还原各座位暗牌，不读取机器人当时的观察。
结果是“牌形与阶段允许”的保守候选：财神、抓打圈及更细规则仍须
用正式规则引擎复核；不能把原始牌形候选直接叫作合法漏窗。

用法：PYTHONPATH=src python audit_claim_opportunities.py AUDIT_ROOT OFFICIAL_EVENTS_ROOT
"""

from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/r18-four-arm-evaluation-2026-09-23'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

import argparse
import gzip
import json
from collections import Counter, defaultdict
from pathlib import Path

from hangma_bot.adapters.official.dto import parse_snapshot
from hangma_bot.adapters.official.projector import observation
from hangma_bot.hangma import HangmaRules
from hangma_bot.kernel.config import RuleConfig


def rows(path: Path):
    """完整读取 JSONL；赛后证据损坏时中止，不把缺行误算为零漏窗。

    自由赛入口按 `audit_raw_gzip` 落 `.jsonl.gz`，测试房落 `.jsonl`；
    两种都要读，否则自由赛会被误报成"缺原始审计"。
    """

    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8") as stream:
        for line in stream:
            yield json.loads(line)


def decision_inputs(audit_root: Path) -> dict[tuple[str, str, str], set[int]]:
    """按场次、用户、响应阶段收集真实进入策略的触发序号。"""

    inputs = defaultdict(set)
    # 两种审计布局：四席测试房是 slot-*/runs/...，单 Token 自由赛没有 slot 层。
    # 只增加路径来源，不改变任何判据或统计口径。
    paths: list[Path] = []
    seen: set[Path] = set()
    for pattern in ("slot-*/runs/*/participants/*/decisions.jsonl",
                    "runs/*/participants/*/decisions.jsonl"):
        for path in sorted(audit_root.glob(pattern)):
            if path not in seen:
                seen.add(path)
                paths.append(path)
    for path in paths:
        participant_id = path.parent.name
        for row in rows(path):
            if row.get("kind") != "decision_input":
                continue
            request = (row.get("payload") or {}).get("request") or {}
            window = request.get("window_key") or {}
            phase = window.get("phase")
            if phase not in ("response_peng", "response_chi"):
                continue
            # 碰窗观察中的 last_discard.seq 是原弃牌；吃窗 trigger_seq
            # 可能是三条碰超时中的末条，须稍后映射回同一物理弃牌周期。
            observation = request.get("observation") or {}
            discard = observation.get("last_discard") or {}
            seq = discard.get("seq") if phase == "response_peng" else window.get("trigger_seq")
            if isinstance(seq, int):
                inputs[(window["game_id"], participant_id, phase)].add(seq)
    return inputs


# 官方事件流的 seq 与我方快照 last_discard.seq 之间存在固定偏移：
# 同一张弃牌，官方记在 seq=N，而我们消费到的快照把它记在 N+1 或 N+2。
# 2026-09-25 实测（a_ee0fd34a23e2_r1_b5_t0）：117→119、886→887、1081→1082、
# 1143→1144、1170→1171，牌张逐一对上。旧版按**精确相等**判定「是否进入策略」，
# 于是把一个已经决策过的窗口误报成漏窗——这是假阳性类别，不是真实漏发。
# 现在改为在该弃牌之后的一个小窗口内查找，并保留 SEQ_SLACK 便于做敏感性检查。
SEQ_SLACK = 4


def _seen_response(inputs, game_id, user_id, phase, seq) -> bool:
    """该物理弃牌周期是否有任一决策输入进入策略（容许已知 seq 偏移）。"""

    recorded = inputs[(game_id, user_id, phase)]
    return any(seq <= item <= seq + SEQ_SLACK for item in recorded)


def chi_shapes(hand: Counter[str], tile: str) -> bool:
    """仅判断数字牌相邻两张的原始牌形，不替代正式吃牌规则。"""

    if len(tile) != 2 or tile[1] not in "wtb" or tile[0] not in "123456789":
        return False
    number, suit = int(tile[0]), tile[1]
    for left, right in ((number - 2, number - 1), (number - 1, number + 1),
                        (number + 1, number + 2)):
        if 1 <= left <= 9 and 1 <= right <= 9:
            if hand[f"{left}{suit}"] > 0 and hand[f"{right}{suit}"] > 0:
                return True
    return False


def confirm_with_rules(audit_root: Path, official_root: Path, missing: list[dict]) -> tuple[list[dict], list[dict]]:
    """用实际获取的官方快照与正式规则引擎复核缺失窗口。

    只取原弃牌及其碰/吃阶段内的快照，并保持原手牌、座位、规则配置；
    将快照阶段设为待核的响应阶段。若没有这样的快照，单独报告为未证实。
    该复核验证动作合法性，不估计请求是否赶上官方毫秒截止。
    """

    participants = {}
    # 两种审计布局：四席测试房 slot-*/runs/...，单 Token 自由赛 runs/...。
    # 一个审计根可以包含多个 run（同一战役的每一房各一个 run-*）。
    # 旧版按参与者名 setdefault 只留第一个目录，导致后续房的场次被拿去
    # 第一个房的 raw 目录里找，报「缺该场原始审计」。这里改为收集全部目录，
    # 取用时再挑出真正含该场 raw 的那个。
    participants = defaultdict(list)
    for pattern in ("slot-*/runs/*/participants/*", "runs/*/participants/*"):
        for slot in audit_root.glob(pattern):
            participants[slot.name].append(slot)
    rules_by_participant = {}
    confirmed, unverified, other_seat = [], [], []
    official = {}
    for path in official_root.rglob("events.json"):
        document = json.loads(path.read_text(encoding="utf-8"))
        official[document["game_id"]] = document
    for item in missing:
        game_id, seat, seq = item["game_id"], item["seat"], item["seq"]
        user_id = official[game_id]["seats"][seat]["user_id"]
        participant = participants.get(user_id)
        if participant is None:
            # 真实自由赛只持有本方身份的审计，他家座位无法核对（我们没有他们的
            # 决策输入）。单列成"非本方座位"，既不计入漏发也不计入未证实。
            # 四席测试房四家全是本方，因此该分支不触发，原有结论口径不变。
            other_seat.append({**item, "user_id": user_id, "reason": "not_our_seat"})
            continue
        # 从候选目录里挑出真正包含该场 raw 的那一个。
        raw_files = []
        chosen = None
        for candidate_dir in participant:
            found = sorted((candidate_dir / "raw").glob(f"{game_id}*.jsonl*"))
            if found:
                raw_files = found
                chosen = candidate_dir
                break
        if not raw_files:
            raise ValueError(f"缺该场原始审计: {game_id}")
        participant = chosen
        if user_id not in rules_by_participant:
            manifest = json.loads((participant.parents[1] / "manifest.json").read_text(encoding="utf-8"))["payload"]
            rules_by_participant[user_id] = HangmaRules(RuleConfig(
                manifest["ruleset_version"], manifest["base_score"],
                bool(manifest["you_cai_bi_kao"])))
        candidates = []
        raw_rows = []
        for raw_file in raw_files:
            raw_rows.extend(rows(raw_file))
        for row in raw_rows:
            payload = row.get("payload") or {}
            if payload.get("source") != "state_response":
                continue
            document = json.loads(payload.get("raw") or "{}")
            snapshot = document.get("snapshot")
            current_seq = document.get("seq")
            latest = seq + (3 if item["kind"] == "peng_pair" else 4)
            if (not isinstance(snapshot, dict) or not isinstance(current_seq, int)
                    or not seq <= current_seq <= latest
                    or snapshot.get("last_discard") != item["tile"]
                    or snapshot.get("round_no") != item["round_no"]):
                continue
            candidates.append((current_seq, snapshot))
        if not candidates:
            unverified.append({**item, "reason": "no_same_discard_snapshot"})
            continue
        current_seq, snapshot = min(candidates, key=lambda pair: pair[0])
        phase = "response_peng" if item["kind"] == "peng_pair" else "response_chi"
        targeted = {**snapshot, "phase": phase, "responding_seats": [seat]}
        analysis = rules_by_participant[user_id].analyze(
            observation(parse_snapshot(targeted, current_seq), (), game_id))
        action_prefix = "peng:" if item["kind"] == "peng_pair" else "chi:"
        actions = [candidate.action_key for candidate in analysis.legal_candidates
                   if candidate.action_key.startswith(action_prefix)]
        result = {**item, "snapshot_seq": current_seq, "legal_actions": actions,
                  "rule_issues": [issue.message for issue in analysis.issues]}
        if actions and not analysis.issues:
            confirmed.append(result)
        else:
            unverified.append({**result, "reason": "rules_not_cleanly_confirmed"})
    return confirmed, unverified, other_seat


def analyze(audit_root: Path, official_root: Path) -> dict:
    """返回原始牌形候选和缺失策略输入的场次、局号、事件序号。"""

    inputs = decision_inputs(audit_root)
    counts = Counter()
    missing = []
    hand_errors = []
    official_files = sorted(official_root.rglob("events.json"))
    if not official_files:
        raise ValueError("找不到官方 events.json")
    for path in official_files:
        document = json.loads(path.read_text(encoding="utf-8"))
        game_id = document["game_id"]
        by_seq = {event["seq"]: event for block in document["blocks"]
                  for event in block["events"]}
        users = [item["user_id"] for item in document["seats"]]
        hands = None
        round_no = None
        for block in document["blocks"]:
            initial = block.get("start_hands")
            if initial and all(isinstance(hand, list) for hand in initial):
                hands = [Counter(hand) for hand in initial]
                round_no = block["round_no"]
            if hands is None:
                raise ValueError(f"缺起手牌: {game_id} round={block['round_no']}")
            for event in block["events"]:
                kind, seat, tile = event["type"], event.get("seat"), event.get("tile")
                data = event.get("data") or {}
                if kind == "tile_discarded":
                    if tile != "白" and data.get("catch_play") is False:
                        for other in range(4):
                            if other != seat and hands[other][tile] >= 2:
                                counts["peng_pair"] += 1
                                if not _seen_response(inputs, game_id, users[other],
                                                     "response_peng", event["seq"]):
                                    missing.append({"game_id": game_id, "round_no": round_no,
                                                    "seq": event["seq"], "seat": other,
                                                    "tile": tile, "kind": "peng_pair"})
                        next_seat = (seat + 1) % 4
                        # 有人提前碰/明杠时吃窗不会开启；只有三条碰窗走满标记
                        # 连续出现，才把牌形上的吃机会列入核对集合。
                        peng_exhausted = all(
                            by_seq.get(event["seq"] + offset, {}).get("type") == "timeout"
                            and (by_seq[event["seq"] + offset].get("data") or {}).get("window") == "peng"
                            for offset in (1, 2, 3)
                        )
                        if peng_exhausted and chi_shapes(hands[next_seat], tile):
                            counts["chi_shape"] += 1
                            next_discard = min((seq for seq, item in by_seq.items()
                                                if seq > event["seq"] and item["type"] in
                                                ("tile_discarded", "round_ended")),
                                               default=event["seq"] + 8)
                            received = any(event["seq"] <= seq < next_discard for seq in
                                           inputs[(game_id, users[next_seat], "response_chi")])
                            if not received:
                                missing.append({"game_id": game_id, "round_no": round_no,
                                                "seq": event["seq"], "seat": next_seat,
                                                "tile": tile, "kind": "chi_shape"})
                    hands[seat][tile] -= 1
                elif kind == "tile_drawn":
                    hands[seat][tile] += 1
                elif kind == "peng":
                    hands[seat][tile] -= 2
                elif kind == "chi":
                    consumed = list(data["tiles"])
                    consumed.remove(tile)  # 第三张来自他家弃牌，不在本人暗牌
                    for own_tile in consumed:
                        hands[seat][own_tile] -= 1
                elif kind == "gang":
                    consumed = {"ming": 3, "an": 4, "bu": 1}.get(data.get("kind"))
                    if consumed is None:
                        raise ValueError(f"未知杠类别: {game_id} seq={event['seq']}")
                    hands[seat][tile] -= consumed
                if kind in ("tile_discarded", "peng", "chi", "gang"):
                    for owner, hand in enumerate(hands):
                        if any(count < 0 for count in hand.values()):
                            hand_errors.append({"game_id": game_id, "round_no": round_no,
                                                "seq": event["seq"], "seat": owner})
    confirmed, unverified, other_seat = confirm_with_rules(audit_root, official_root, missing)
    return {"official_games": len(official_files), "opportunities": dict(counts),
            "missing_inputs": missing, "confirmed_legal_missing_inputs": confirmed,
            "unverified_missing_inputs": unverified,
            "other_seat_candidates": other_seat,
            "hand_reconstruction_errors": hand_errors,
            "interpretation": "先以官方手牌与事件找牌形候选，再用同周期快照及正式规则引擎复核；未证实项单列"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("audit_root", type=Path)
    parser.add_argument("official_events_root", type=Path)
    args = parser.parse_args()
    print(json.dumps(analyze(args.audit_root, args.official_events_root),
                     ensure_ascii=False, indent=2))
