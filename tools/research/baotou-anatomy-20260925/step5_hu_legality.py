#!/usr/bin/env python3
"""第 5 步：质询复核 —— 「14 张已胡的弃牌窗口」到底是什么，以及 hu 当时合不合法。

主审质询（2026-09-25）：若摸牌后 14 张暗牌已成胡，自摸胡就合法，父代一定会胡，
这个窗口就不该以「弃牌」形式存在。要求逐例回答四件事。

本脚本用**真实审计窗口**回答，不靠推理：
1. 数据源：\`.team-work/p6-baotou-route/cache/*.jsonl.gz\`，每个窗口带平台权威
   观察（my_hand / drawn_tile / melds / rule_state）与 **hangma 产出的真实
   legal_candidates**（\`request.rules.legal_candidates\`，经 p6_lib.build_view 复原）。
2. 对每个窗口归一出 14-3m 张暗牌，用 hangma 的 win_split 判是否已胡，
   再查 \`hu\` 是否在真实合法候选里。
3. 按「来路」（drawn_tile 是否存在）分层，并对我方 0 副露的窗口出逐例清单。
4. 读各房 manifest 的 \`you_cai_bi_kao\` 开关，确认规则前提。

用法：.venv/bin/python step5_hu_legality.py [--out hu-legality.json]
"""

from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/baotou-anatomy-20260925'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

import argparse
import glob
import gzip
import json
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = _PROJECT_ROOT
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(_project_file(_PROJECT_ROOT, ROOT / "src")))

from anatomy_lib import TILE_ORDER  # noqa: E402
from hangma_bot.hangma import hand_analysis  # noqa: E402
from hangma_bot.kernel.actions import Tile  # noqa: E402

P6_CACHE = _project_file(_PROJECT_ROOT, ROOT / ".team-work" / "p6-baotou-route" / "cache")
WEALTH = "白"


def iter_cached():
    for path in sorted(glob.glob(str(_project_file(_PROJECT_ROOT, P6_CACHE / "*.jsonl.gz")))):
        room = os.path.basename(path)[: -len(".jsonl.gz")]
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            for line in handle:
                row = json.loads(line)
                row["room"] = room
                yield row


def normalize(view):
    """把窗口观察归一成 (14-3m 张暗牌, 副露数, 来路, 刚摸牌)。

    两种官方形态都要处理：my_hand 已含刚摸牌（14-3m），或 my_hand 为
    13-3m 而刚摸牌在 drawn_tile。**刚摸牌为空（drawn_tile is None）时，
    按 action_families.hu_candidates 的「刚摸牌」门禁，本窗口规则性无胡候选。**
    """

    visible = view["visible_state"]
    hand = list(visible["my_hand"])
    drawn = visible["drawn_tile"]
    melds = len(visible["melds"][visible["seat"]])
    if len(hand) == 14 - 3 * melds:
        # 14-3m 张暗牌有两种来路，**必须靠 drawn_tile 区分**：
        # - drawn 非空 = 摸牌后（my_hand 已含刚摸牌）；
        # - drawn 为空 = 碰/吃/杠后（官方在该窗口仍给 draw 阶段，但规则性无胡候选，
        #   见 action_families.hu_candidates 的「刚摸牌」门禁）。
        return tuple(hand), melds, ("draw" if drawn is not None else "meld"), drawn
    if len(hand) == 13 - 3 * melds:
        # 契约形态：my_hand 为摸前暗牌，刚摸牌另存。
        return tuple(hand + [drawn]), melds, "draw", drawn
    return None, melds, None, None


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="hu-legality.json")
    args = parser.parse_args(argv)

    crosstab = Counter()
    normal_failed = 0
    examples = defaultdict(list)
    hu_legal_and_discarded = []
    per_room = defaultdict(Counter)
    indexed = {}

    for row in iter_cached():
        view = row["view"]
        visible = view["visible_state"]
        if visible["seat"] is None:
            continue
        hand, melds, origin, drawn = normalize(view)
        actions = [a["action_key"] for a in view["actions"]]
        hu_legal = "hu" in actions
        if hand is None:
            normal_failed += 1
            continue
        if any(code not in TILE_ORDER for code in hand):
            normal_failed += 1
            continue
        is_win = hand_analysis.win_split(tuple(Tile(c) for c in hand), melds) is not None
        whites = sum(1 for c in hand if c == WEALTH)
        phase = visible["phase"]
        chose_hu = row["plan_rank1"] == "hu"
        key = (phase, origin, is_win, hu_legal, chose_hu)
        crosstab[key] += 1
        per_room[row["room"]][(origin, is_win, hu_legal)] += 1
        per_room[row["room"]][("all", is_win, hu_legal)] += 1
        indexed[(row["game_id"], row["round_no"], row["trigger_seq"])] = {
            "phase": phase, "origin": origin, "hand": list(hand), "melds": melds,
            "whites": whites, "baotou": visible["rule_state"]["baotou"],
            "hu_legal": hu_legal, "actions": actions,
            "plan_rank1": row["plan_rank1"], "room": row["room"],
            "chain_count": visible["rule_state"]["chain_count"],
        }
        if is_win and not hu_legal and len(examples[origin]) < 6:
            examples[origin].append({
                "room": row["room"], "game_id": row["game_id"], "round_no": row["round_no"],
                "seq": row["trigger_seq"], "hand": list(hand), "melds": melds,
                "whites": whites, "baotou": visible["rule_state"]["baotou"],
                "hu_legal": hu_legal, "plan_rank1": row["plan_rank1"],
                "actions_head": actions[:8],
            })
        if is_win and hu_legal and not chose_hu:
            hu_legal_and_discarded.append({
                "room": row["room"], "game_id": row["game_id"], "round_no": row["round_no"],
                "seq": row["trigger_seq"], "origin": origin, "phase": phase,
                "hand": list(hand), "melds": melds, "whites": whites,
                "baotou": visible["rule_state"]["baotou"],
                "plan_rank1": row["plan_rank1"], "actions": actions,
            })

    print("## 1. 真实审计窗口上的交叉表（32,374 个窗口）")
    print()
    print("| 阶段 | 来路 | 14 张已胡 | hu 在合法候选里 | 父代选择 | 窗口数 |")
    print("| --- | --- | --- | --- | --- | --- |")
    order = [("draw", "draw"), ("draw", "meld"), ("response_peng", None), ("response_chi", None)]
    total = 0
    for phase, origin in [("draw", "draw"), ("draw", "meld"), ("response_peng", None),
                          ("response_chi", None)]:
        for is_win in (True, False):
            for hu_legal in (True, False):
                for chose_hu in (True, False):
                    count = 0
                    for key, value in crosstab.items():
                        if key[0] != phase or key[2] != is_win or key[3] != hu_legal:
                            continue
                        if key[4] != chose_hu:
                            continue
                        if origin is not None and key[1] != origin:
                            continue
                        count += value
                    if not count:
                        continue
                    total += count
                    print("| %s | %s | %s | %s | %s | %d |" % (
                        phase, origin or "（响应窗）", "是" if is_win else "否",
                        "是" if hu_legal else "否", "hu" if chose_hu else "非 hu", count))
    print()
    print("合计计入 %d（归一失败 %d）" % (total, normal_failed))
    print()
    print("**审计窗口里「14 张已胡 且 hu 合法」的窗口：%d；其中父代选 hu 的 %d，未选 hu 的 %d**" % (
        sum(v for k, v in crosstab.items() if k[2] and k[3]),
        sum(v for k, v in crosstab.items() if k[2] and k[3] and k[4]),
        sum(v for k, v in crosstab.items() if k[2] and k[3] and not k[4])))
    for item in hu_legal_and_discarded[:10]:
        print("   ", json.dumps(item, ensure_ascii=False))

    # 逐房
    print()
    print("## 2. 分房：摸牌后已胡 / 鸣牌后已胡 的窗口数（真实审计）")
    print()
    print("| 房 | 摸牌后窗口 | 摸牌后已胡 | 鸣牌后窗口 | 鸣牌后已胡 | 其中 hu 合法 |")
    print("| --- | --- | --- | --- | --- | --- |")
    for room in sorted(per_room):
        c = per_room[room]
        dw = sum(v for k, v in c.items() if k[0] == "draw")
        dh = sum(v for k, v in c.items() if k[0] == "draw" and k[1])
        mw = sum(v for k, v in c.items() if k[0] == "meld")
        mh = sum(v for k, v in c.items() if k[0] == "meld" and k[1])
        legal = sum(v for k, v in c.items() if k[1] and k[2])
        print("| %s | %d | %d | %d | %d | %d |" % (room, dw, dh, mw, mh, legal))

    # 我方 0 副露窗口逐例
    print()
    # 可比局限定：只取审计样本覆盖到的 (game_id, round_no)
    audit_rounds = {(row["game_id"], row["round_no"]) for row in []} 
    print("## 3. 我方「0 副露 + 已胡」弃牌窗口逐例（来自本库重建，含审计候选）")
    print()
    rounds = []
    with open(_project_file(_PROJECT_ROOT, HERE / "rounds.jsonl"), encoding="utf-8") as handle:
        for line in handle:
            rounds.append(json.loads(line))
    zero_meld = []
    meld_pos = []
    for row in rounds:
        me = next((s for s in row["seats"] if s["is_me"]), None)
        if me is None:
            continue
        for w in me["reach_windows"]:
            item = {
                "game_id": row["game_id"], "round_no": row["round_no"], "seq": w[0],
                "turn": w[1], "n_targets": w[2], "chosen_target": w[3],
                "whites": w[5], "melds": w[6], "chosen": w[7], "origin": w[8],
                "winner": row["winner_seat"], "me_is_winner": row["winner_seat"] == me["seat"],
                "detail": row["detail"],
            }
            # 官方事件 seq 与我方快照 trigger_seq 有已知固定偏移（见
            # audit_claim_opportunities.py 的 SEQ_SLACK=4 注释）：同一张弃牌
            # 官方记在 seq=N，快照记在 N+1/N+2。按该容忍窗口对齐。
            audit = None
            for offset in (0, 1, 2, 3, 4, -1, -2, -3, -4):
                audit = indexed.get((row["game_id"], row["round_no"], w[0] + offset))
                if audit is not None:
                    break
            item["audit"] = audit
            (zero_meld if w[6] == 0 else meld_pos).append(item)
    print("我方 0 副露的已胡窗口共 %d 个；副露>0 的共 %d 个。" % (len(zero_meld), len(meld_pos)))
    in_audit = sum(1 for item in zero_meld if item["audit"])
    print("其中能在审计窗口里找到（可读到真实合法候选）的：%d / %d。" % (in_audit, len(zero_meld)))
    meld_in_audit = sum(1 for item in meld_pos if item["audit"])
    print("副露>0 的已胡窗口中能在审计里找到的：%d / %d。" % (meld_in_audit, len(meld_pos)))
    # 我方全部已胡窗口（两种来路）在审计里的 hu 合法性
    both = [item for item in (zero_meld + meld_pos) if item["audit"]]
    hu_legal_count = sum(1 for item in both if item["audit"]["hu_legal"])
    chosen_hu = sum(1 for item in both if item["audit"]["plan_rank1"] == "hu")
    print()
    print("**我方全部 %d 个已胡弃牌窗口中，进入审计样本的 %d 个：hu 合法的 %d 个，父代选 hu 的 %d 个。**"
          % (len(zero_meld) + len(meld_pos), len(both), hu_legal_count, chosen_hu))
    for item in both:
        if item["audit"]["hu_legal"]:
            print("   hu 合法例：", json.dumps({
                "game_id": item["game_id"], "round_no": item["round_no"], "seq": item["seq"],
                "原路": item["origin"], "audit": item["audit"]}, ensure_ascii=False))
    print()
    print("| # | game_id | 局 | seq | 巡 | 手留白 | 手牌 | 审计 hu 合法 | 审计 rank1 | 候选数 | 本局结果 |")
    print("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for index, item in enumerate(zero_meld, 1):
        audit = item["audit"]
        print("| %d | %s | %d | %d | %d | %d | %s | %s | %s | %s | %s%s |" % (
            index, item["game_id"], item["round_no"], item["seq"], item["turn"], item["whites"],
            " ".join(audit["hand"]) if audit else "（不在审计样本内）",
            ("是" if audit["hu_legal"] else "否") if audit else "—",
            audit["plan_rank1"] if audit else "—",
            len(audit["actions"]) if audit else "—",
            "我方胡 " if item["me_is_winner"] else "",
            ",".join(item["detail"] or [])))

    # 副露>0 的示例
    print()
    print("## 4. 我方「副露>0 + 已胡」窗口示例（前 12 条）")
    print()
    print("| # | game_id | 局 | seq | 巡 | 副露 | 手留白 | 审计 hu 合法 | 审计 rank1 | 本局结果 |")
    print("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for index, item in enumerate(meld_pos[:12], 1):
        audit = item["audit"]
        print("| %d | %s | %d | %d | %d | %d | %d | %s | %s | %s%s |" % (
            index, item["game_id"], item["round_no"], item["seq"], item["turn"],
            item["melds"], item["whites"],
            ("是" if audit["hu_legal"] else "否") if audit else "—",
            audit["plan_rank1"] if audit else "—",
            "我方胡 " if item["me_is_winner"] else "", ",".join(item["detail"] or [])))

    # you_cai_bi_kao 开关
    print()
    print("## 5. 各房 you_cai_bi_kao 开关（读 manifest，只读）")
    print()
    print("| 房 | you_cai_bi_kao | runs（读到的 manifest 数） |")
    print("| --- | --- | --- |")
    switches = {}
    for room in sorted({row["room"] for row in []} | set(per_room)):
        values = Counter()
        for manifest in glob.glob(str(_project_file(_PROJECT_ROOT, ROOT / "artifacts" / "sessions" / room / "audit" / "runs" / "*" / "manifest.json"))):
            try:
                payload = json.loads(Path(manifest).read_text(encoding="utf-8")).get("payload") or {}
            except (OSError, ValueError):
                continue
            values[bool(payload.get("you_cai_bi_kao"))] += 1
        switches[room] = dict(values)
        print("| %s | %s | %d |" % (
            room, ", ".join("%s:%d" % (k, v) for k, v in sorted(values.items())) or "无 manifest",
            sum(values.values())))

    payload = {
        "crosstab": {"%s|%s|%s|%s|%s" % k: v for k, v in crosstab.items()},
        "normalize_failed": normal_failed,
        "hu_legal_while_win_hand": len(hu_legal_and_discarded),
        "hu_legal_examples": hu_legal_and_discarded[:20],
        "per_room": {k: {str(kk): vv for kk, vv in v.items()} for k, v in per_room.items()},
        "switch_you_cai_bi_kao": switches,
        "zero_meld_windows": [
            {k: v for k, v in item.items() if k != "audit"} for item in zero_meld],
        "zero_meld_in_audit": in_audit,
        "meld_pos_in_audit": meld_in_audit,
        "my_win_hand_windows_in_audit": len(both),
        "my_win_hand_hu_legal": hu_legal_count,
        "my_win_hand_chosen_hu": chosen_hu,
        "meld_pos_windows": len(meld_pos),
    }
    (_project_file(_PROJECT_ROOT, HERE / args.out)).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print()
    print("已写出 %s" % (_project_file(_PROJECT_ROOT, HERE / args.out)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
