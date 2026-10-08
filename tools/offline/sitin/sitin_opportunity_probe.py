"""机会位点探针（能力尺 · 第一阶段 v2）：只读语料 + 规则谓词 + 下一窗口权威状态。

v1 的三处错误已修：
  1. 白板弃牌键是 "discard:白"，v1 用 endswith("white") 判错 ⇒ 飘从未被识别；
  2. v1 把 pass 归入"弃牌后未知" ⇒ 爆头桶被污染（pass 不改变任何状态）；
  3. 吃/碰对链的语义 v1 靠猜 ⇒ 改为读**记录里同局下一窗口的权威 rule_state**。

判定原则（按可靠性排序）：
  - 弃牌/杠对链：用 hangma.special_rules / progression 的规则谓词（规则确定）；
  - 其余动作对链、以及对爆头/圈的持续：读同 (game_id, round_no) 下一窗口的
    observation.rule_state（平台权威）；没有下一窗口记 state_unavailable；
  - 一切不确定都记 unknown，绝不猜成"毁掉"。

这不是强度证据：不跑桌赛、不做概率假设、不给候选排名。
"""
from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/llm-guided-heuristic-route-2026-09-15/tools'

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
import json
import os
import sys
from collections import Counter, defaultdict

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))

from hangma_bot.bootstrap import build_decision_codec  # noqa: E402
from hangma_bot.hangma import hand_analysis  # noqa: E402
from hangma_bot.hangma.internal_types import is_wealth_code  # noqa: E402

WHITE = "白"
WHITE_SUFFIX = ":" + WHITE
CODE = build_decision_codec()
DECODE = CODE["decode_request"]


def _whites_in_hand(obs) -> int:
    """手留财神张数：处理 my_hand 含/不含刚摸牌两种形态。"""
    hand = list(obs.my_hand or ())
    meld_count = len(list(getattr(obs, "melds", ()) or ()))
    whites = sum(1 for t in hand if str(t) == WHITE)
    drawn = getattr(obs, "drawn_tile", None)
    if drawn is not None and str(drawn) == WHITE and len(hand) == 13 - 3 * meld_count:
        whites += 1
    return whites


def _seven_pairs_shanten(obs) -> "int | None":
    meld_count = len(list(getattr(obs, "melds", ()) or ()))
    if meld_count > 0:
        return None  # 官方：七对禁吃碰明杠暗杠
    tiles = list(obs.my_hand or ())
    drawn = getattr(obs, "drawn_tile", None)
    if drawn is not None and len(tiles) == 13:
        tiles.append(drawn)
    try:
        return hand_analysis.analyse_hand(tuple(tiles), 0).chiitoi_shanten
    except Exception:
        return None


def _load_groups(path):
    """按 (game_id, round_no) 分组并按 trigger_seq 排序，供读下一窗口状态。"""
    groups = defaultdict(list)
    bad = 0
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            try:
                row = json.loads(line)
                wk = row["request"]["window_key"]
                key = (wk["game_id"], wk["round_no"])
                groups[key].append((int(wk["trigger_seq"]), row))
            except Exception:
                bad += 1
    for key in groups:
        groups[key].sort(key=lambda item: item[0])
    return groups, bad


def _analyze(rows, limit, counters, verdict, examples, hist):
    for pos, (_seq, row) in enumerate(rows):
        if counters["rows"] >= limit:
            return
        counters["rows"] += 1
        try:
            req = DECODE(row["request"])
        except Exception:
            counters["decode_failed"] += 1
            continue
        obs = req.observation
        rs = obs.rule_state
        baotou = bool(getattr(rs, "baotou", False))
        chain = int(getattr(rs, "chain_count", 0) or 0)
        catch = bool(getattr(rs, "catch_play", False))
        owner = getattr(rs, "catch_play_owner_seat", None)
        seat = int(getattr(obs, "seat", -1))
        whites = _whites_in_hand(obs)

        after = rows[pos + 1][1] if pos + 1 < len(rows) else None
        after_rs = None
        if after is not None:
            try:
                after_rs = DECODE(after["request"]).observation.rule_state
            except Exception:
                after_rs = None

        plan = row.get("returned_plan") or {}
        cands = plan.get("candidates") or []
        if not cands:
            counters["no_plan"] += 1
            continue
        chosen = min(cands, key=lambda c: c.get("rank", 99))
        ckey = str(chosen.get("action_key", ""))
        ckind = str((chosen.get("action") or {}).get("kind", ""))
        hist[ckind] += 1

        legal = list(getattr(req.rules, "legal_candidates", ()) or ())
        kinds = {str(getattr(c.action, "kind", "")) for c in legal}
        has_hu = "hu" in kinds
        has_gang = "gang" in kinds
        discards_white = ckind == "discard" and ckey.endswith(WHITE_SUFFIX)
        # 飘 = 爆头态打出财神（special_rules.is_piao_discard 同据；此处用规则模块的字符串谓词）
        is_piao = (ckind == "discard" and baotou
                   and is_wealth_code(ckey.split(":", 1)[-1]))

        def note(name, tag, reason):
            verdict[name][tag] += 1
            if len(examples[name]) < 5:
                examples[name].append({
                    "chosen": ckey, "kind": ckind, "tag": tag, "reason": reason,
                    "chain_before": chain, "baotou_before": baotou,
                    "whites": whites, "has_hu": has_hu,
                    "chain_after": None if after_rs is None else getattr(after_rs, "chain_count", None),
                    "baotou_after": None if after_rs is None else getattr(after_rs, "baotou", None),
                })

        # ---------- O1 爆头态 ----------
        if baotou:
            counters["opp_baotou"] += 1
            if ckind == "hu":
                note("baotou", "traded_for_win", "legal_hu_taken")
            elif ckind == "pass":
                note("baotou", "preserved", "pass_no_state_change")
            elif is_piao:
                note("baotou", "preserved", "piao_keeps_baotou")
            elif ckind == "discard":
                if after_rs is None:
                    note("baotou", "state_unavailable", "no_next_window")
                elif bool(getattr(after_rs, "baotou", False)):
                    note("baotou", "preserved_next_window", "authoritative_after_state")
                else:
                    note("baotou", "lost_next_window", "authoritative_after_state")
            else:
                note("baotou", "unknown_action", ckind)

        # ---------- O2 链已开 ----------
        if chain > 0:
            counters["opp_chain"] += 1
            can_extend = (baotou and whites > 0) or has_gang
            if ckind == "hu":
                note("chain_open", "traded_for_win", "legal_hu_taken")
            elif ckind == "gang":
                note("chain_open", "extended_rule", "gang_plus_one")
            elif is_piao:
                note("chain_open", "extended_rule", "piao_plus_one")
            elif ckind == "pass":
                note("chain_open", "preserved_no_change", "pass")
            elif ckind == "discard":
                note("chain_open",
                     "broken_with_alternative" if can_extend else "broken_no_alternative",
                     "chain_breaks_on_non_piao_discard")
            elif ckind in ("chi", "peng"):
                if after_rs is None:
                    note("chain_open", "state_unavailable", "no_next_window")
                else:
                    after_chain = int(getattr(after_rs, "chain_count", 0) or 0)
                    note("chain_open",
                         "extended_next_window" if after_chain > chain else "broken_next_window",
                         "authoritative_after_state")
            else:
                note("chain_open", "unknown_action", ckind)

        # ---------- O3 圈主是我 ----------
        if catch and owner is not None and int(owner) == seat:
            counters["opp_catch_owner"] += 1
            if ckind == "hu":
                note("catch_owner", "traded_for_win", "legal_hu_taken")
            elif ckind == "pass":
                note("catch_owner", "preserved", "pass_no_state_change")
            elif ckind == "discard" and not discards_white:
                note("catch_owner",
                     "closed_with_alternative" if whites > 0 else "closed_no_alternative",
                     "owner_discards_non_white")
            else:
                note("catch_owner", "preserved_other", ckind)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", help="decisions.jsonl 路径或 glob")
    ap.add_argument("--manifest", help="canonical 面板清单 JSON（取 files[].path）")
    ap.add_argument("--limit", type=int, default=2000000)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    paths = []
    if args.manifest:
        with open(args.manifest, encoding="utf-8") as fh:
            paths = [entry["path"] for entry in json.load(fh).get("files", ())]
    if args.corpus:
        paths = sorted(set(paths) | set(glob.glob(args.corpus)))
    paths = sorted(paths)
    if not paths:
        print("no corpus matched")
        return 2

    counters = Counter()
    verdict = defaultdict(Counter)
    examples = defaultdict(list)
    hist = Counter()
    for path in paths:
        groups, bad = _load_groups(path)
        counters["bad_rows"] += bad
        for rows in groups.values():
            _analyze(rows, args.limit, counters, verdict, examples, hist)
            if counters["rows"] >= args.limit:
                break
        if counters["rows"] >= args.limit:
            break

    os.makedirs(args.out, exist_ok=True)
    report = {
        "schema": "sitin-opportunity-probe/2",
        "scope": {"paths": len(paths), "rows": counters["rows"],
                  "manifest": args.manifest, "corpus": args.corpus},
        "opportunity_counts": {k: counters[k] for k in sorted(counters) if k.startswith("opp_")},
        "verdicts": {k: dict(v) for k, v in verdict.items()},
        "examples": {k: v for k, v in examples.items()},
        "chosen_kind_hist": dict(hist),
        "counters": dict(counters),
    }
    with open(os.path.join(args.out, "probe.json"), "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=1)

    print("rows", counters["rows"], "files", len(paths))
    print("opportunities", report["opportunity_counts"])
    for name in sorted(verdict):
        total = sum(verdict[name].values())
        parts = ", ".join("%s=%d" % (k, v) for k, v in verdict[name].most_common())
        print("  %-14s n=%-6d %s" % (name, total, parts))
    print("chosen_kinds", dict(hist))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
