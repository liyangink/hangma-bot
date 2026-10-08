#!/usr/bin/env python3
"""被压制局/连庄局的反事实候选解剖（只读审计日志，无网络，不跑模拟）。

数据来源
--------
- 我方逐决策审计：artifacts/sessions/<标签>/audit/runs/<run>/participants/
  u_13495c3d79c8/decisions.jsonl（NDJSON，流式扫描）。
  用到的记录种类：
  - decision_planned：payload.candidates 是规则模块给出的合法候选排序，
    每条带 reasons（base_score / basis / best_shanten_non_pass /
    risk_units / river_part / hu_sorting_layer）与 observation_snapshot
    （my_hand / drawn_tile / my_melds / scores / remaining_tile_count /
    rule_state）。这就是「当时有哪些法律允许的不同选择」。
  - candidate_validated：最终通过合法性复核的那一条 action_key。
  - submission_intent / submission_outcome：实际提交与结果。
- 官方牌谱：artifacts/sessions/<标签>/official/dl-*/events.json，
  用于判定「我方这次弃牌是否被对手吃/碰/明杠领走」（喂牌）。

为什么口径是「喂牌」而不是「放铳」
--------------------------------
RULES_EVIDENCE.md §2 明确「只能自摸，不允许点炮；禁止抢杠胡」，
因此平台不存在放铳；我方弃牌不会直接导致失分。唯一由我方弃牌影响的
失分通道是被对手吃/碰/明杠（推进对手向听、给杠加番与摸牌）。
本脚本据此度量喂牌，而不是套用日麻的「危险牌」概念。

用法：
    .venv/bin/python review/freematch-deep-dive-20260925/suppressed_counterfactuals.py
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
import collections
import glob
import json
import math
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from suppressed_rounds import (ME, load_official, round_events,  # noqa: E402
                               parse_game, dealer_runs, dealer_streak_at, contiguous,
                               _ctx_of, rate, mean_se)

AUDIT_ROOTS = ("r18-auto-match-campaign-20260923", "r18-v2-sse-freematch-20260925-pm",
               "r18-v2-sse-freematch-20260925-pm2", "r18-v2-sse-freematch-20260925-pm3",
               "r18-integrated-positive-v1-auto-match")


def claim_index(payload):
    """{(round_no, feeder_seat, tile): [(claimer_seat, kind)]}：被鸣牌的我方弃牌。"""
    out = collections.defaultdict(list)
    for rn, evs in round_events(payload).items():
        last_discard = None
        for ev in evs:
            t = ev.get("type")
            if t == "tile_discarded":
                last_discard = (ev.get("seat"), ev.get("tile"))
            elif t in ("chi", "peng", "gang"):
                data = ev.get("data") or {}
                if t == "gang" and data.get("kind") == "an":
                    continue
                if last_discard and ev.get("tile") == last_discard[1]:
                    out[(rn, last_discard[0], last_discard[1])].append(
                        (ev.get("seat"), data.get("kind") or t))
            elif t in ("pass", "timeout"):
                data = ev.get("data") or {}
                if t == "pass" or data.get("kind") == "response":
                    last_discard = None
    return out


def parse_reasons(reasons):
    """把 reasons 的 "key=value" 列表解析成字典；值尽量转数值。"""
    d = {}
    for item in reasons or []:
        if "=" not in item:
            continue
        k, v = item.split("=", 1)
        try:
            d[k] = float(v)
        except ValueError:
            d[k] = v
    return d


def scan_audit(game_ids, roots=AUDIT_ROOTS, limit_games=None):
    """流式扫描审计日志，返回 [(decision_planned_record, chosen_action_key)] 精简列表。"""
    planned, validated = {}, {}
    files = []
    for tag in roots:
        files.extend(glob.glob(os.path.join(
            "artifacts/sessions", tag, "audit", "runs", "*", "participants",
            ME, "decisions.jsonl")))
    print("[扫描] 审计文件 {0} 个".format(len(files)), file=sys.stderr)
    for path in files:
        with open(path) as fh:
            for line in fh:
                head = line[:140]
                want_p = '"decision_planned"' in head
                want_v = '"candidate_validated"' in head
                if not (want_p or want_v):
                    continue
                i = line.find('"game_id": "')
                if i < 0:
                    continue
                start = i + len('"game_id": "')
                gid = line[start:line.find('"', start)]
                if gid not in game_ids:
                    continue
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                ctx = rec.get("context") or {}
                key = (ctx.get("game_id"), ctx.get("round_no"), ctx.get("trigger_seq"),
                       ctx.get("decision_id"))
                pl = rec.get("payload") or {}
                if want_p:
                    cands = []
                    for c in pl.get("candidates") or []:
                        cands.append({
                            "action_key": c.get("action_key"),
                            "rank": c.get("rank"),
                            "kind": (c.get("action") or {}).get("kind"),
                            "tile": (c.get("action") or {}).get("tile"),
                            "emergency": bool(c.get("is_emergency")),
                            "r": parse_reasons(c.get("reasons")),
                        })
                    obs = pl.get("observation_snapshot") or {}
                    planned[key] = {
                        "game_id": ctx.get("game_id"), "round_no": ctx.get("round_no"),
                        "trigger_seq": ctx.get("trigger_seq"),
                        "decision_id": ctx.get("decision_id"),
                        "phase": (pl.get("window") or {}).get("phase"),
                        "seat": (pl.get("window") or {}).get("seat"),
                        "candidates": cands,
                        "hand": obs.get("my_hand"), "drawn": obs.get("drawn_tile"),
                        "melds": obs.get("my_melds"), "scores": obs.get("scores"),
                        "remaining": obs.get("remaining_tile_count"),
                        "rule_state": obs.get("rule_state"),
                    }
                else:
                    validated[key] = pl.get("action_key")
    out = []
    for key, rec in planned.items():
        rec["chosen"] = validated.get(key)
        out.append(rec)
    out.sort(key=lambda r: (r["game_id"] or "", r["round_no"] or 0, r["trigger_seq"] or 0))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--scores", default="review/freematch-deep-dive-20260925/room-scores.json")
    ap.add_argument("--out", default="review/freematch-deep-dive-20260925/suppressed-rounds-cf.json")
    ap.add_argument("--md-samples", type=int, default=8)
    args = ap.parse_args(argv)

    official = load_official()
    games = {}
    for g0 in json.load(open(args.scores))["games"]:
        got = official.get(g0["game_id"])
        if not got:
            continue
        g = parse_game(g0["game_id"], got[1], got[2])
        if g:
            games[g["game_id"]] = g
    print("[装载] 场 {0}".format(len(games)), file=sys.stderr)

    # 每局的局面标签 + 我方位次统计
    ctx_of = {}
    claim_of = {}
    for gid, g in games.items():
        rs, my = g["rounds"], g["my_seat"]
        for i, r in enumerate(rs):
            ctx_of[(gid, r["round_no"])] = _ctx_of(rs, i, my)
        claim_of[gid] = claim_index(got_payload := official[gid][2])

    decisions = scan_audit(set(games))
    print("[扫描] 命中决策 {0}".format(len(decisions)), file=sys.stderr)

    # ---- 1) 措辞与打分构成面 ------------------------------------------
    fields = collections.Counter()
    field_nonzero = collections.Counter()
    cand_counts = collections.Counter()
    reason_keys = collections.Counter()
    for d in decisions:
        cand_counts[len(d["candidates"])] += 1
        for c in d["candidates"]:
            for k, v in c["r"].items():
                reason_keys[k] += 1
                fields[k] += 1
                if isinstance(v, (int, float)) and v != 0:
                    field_nonzero[k] += 1
    field_stats = {k: {"seen": fields[k], "nonzero": field_nonzero.get(k, 0),
                       "nonzero_share": field_nonzero.get(k, 0) / fields[k]}
                   for k in sorted(fields)}

    # ---- 2) 弃牌决策的候选面与喂牌 ------------------------------------
    disc_rows = []
    for d in decisions:
        if d["phase"] != "draw" or not d["candidates"]:
            continue
        top = d["candidates"][0]
        if top["kind"] != "discard":
            continue
        chosen = d["chosen"] or top["action_key"]
        by_key = {c["action_key"]: c for c in d["candidates"]}
        ch = by_key.get(chosen)
        if ch is None:
            continue
        disc = [c for c in d["candidates"] if c["kind"] == "discard"]
        if not isinstance(ch["r"].get("base_score"), (int, float)):
            continue
        # 无差别集：与所选在 base_score 与 best_shanten_non_pass 上完全相同的
        # 其他合法候选。规则模块与打分面都不区分它们，选哪张只由 tie-break 决定。
        tied = [c for c in disc
                if c["r"].get("base_score") == ch["r"].get("base_score")
                and c["r"].get("best_shanten_non_pass") == ch["r"].get("best_shanten_non_pass")]
        claims = claim_of.get(d["game_id"], {})
        def fed(tile):
            for (rn, feeder, t), lst in claims.items():
                if rn == d["round_no"] and feeder == d["seat"] and t == tile:
                    return lst
            return None
        ch_feed = fed(ch["tile"])
        alt_feed = [(c["tile"], fed(c["tile"])) for c in tied if c["action_key"] != ch["action_key"]]
        ctx = ctx_of.get((d["game_id"], d["round_no"]), "未知")
        # 同牌效（向听不退化）且未被鸣的备选是否存在
        safe_alt = [c for c in tied
                    if c["action_key"] != ch["action_key"]
                    and not fed(c["tile"])
                    and c["r"].get("best_shanten_non_pass") == ch["r"].get("best_shanten_non_pass")]
        disc_rows.append({
            "game_id": d["game_id"], "round_no": d["round_no"],
            "trigger_seq": d["trigger_seq"], "ctx": ctx,
            "chosen": chosen, "chosen_tile": ch["tile"],
            "n_candidates": len(d["candidates"]), "n_tied_best": len(tied),
            "fed": (ch_feed is not None),
            "fed_by": ([{"seat": s, "kind": k} for s, k in (ch_feed or [])] or None),
            "safe_alt_same_score_same_shanten": [c["action_key"] for c in safe_alt],
            "alt_tiles_tied": [c["tile"] for c in tied if c["action_key"] != ch["action_key"]],
            "risk_units": ch["r"].get("risk_units"),
            "river_part": ch["r"].get("river_part"),
            "base_score": ch["r"].get("base_score"),
            "best_shanten_non_pass": ch["r"].get("best_shanten_non_pass"),
            "remaining": d["remaining"],
            "n_hand": len(d["hand"] or []),
            "n_melds": len(d["melds"] or []),
            "drawn": d["drawn"],
            "hand": d["hand"],
            "top3": [{"action_key": c["action_key"], "base_score": c["r"].get("base_score"),
                      "shanten": c["r"].get("best_shanten_non_pass"),
                      "risk_units": c["r"].get("risk_units")} for c in disc[:3]],
        })

    # ---- 3) 牌值级被鸣率模型：并列时「换一张」的期望收益 ----------------
    tile_stat = collections.defaultdict(lambda: {"n": 0, "claimed": 0})
    for r in disc_rows:
        s = tile_stat[r["chosen_tile"]]
        s["n"] += 1
        s["claimed"] += 1 if r["fed"] else 0
    tile_rate = {t: (v["claimed"] / v["n"] if v["n"] else None)
                 for t, v in tile_stat.items()}
    global_rate = (sum(1 for r in disc_rows if r["fed"]) / len(disc_rows)) if disc_rows else 0.0

    tie_decisions = [r for r in disc_rows
                     if r["n_tied_best"] > 1 and r["alt_tiles_tied"]]
    tie_fed = [r for r in tie_decisions if r["fed"]]
    regret_rows = []
    for r in tie_decisions:
        ch = tile_rate.get(r["chosen_tile"])
        alts = [tile_rate.get(t) for t in r["alt_tiles_tied"]]
        alts = [a for a in alts if a is not None]
        if ch is None or not alts:
            continue
        regret_rows.append({
            "room_id": r["game_id"], "chosen_rate": ch,
            "best_alt_rate": min(alts), "mean_alt_rate": sum(alts) / len(alts),
            "fed": r["fed"]})

    def boot_mean(rows, key, iters=4000, seed=11):
        by_room = collections.defaultdict(list)
        for x in rows:
            by_room[x["room_id"]].append(x[key])
        rooms = sorted(by_room)
        if not rooms:
            return None
        rng = random.Random(seed)
        vals = []
        for _ in range(iters):
            acc = []
            for _ in range(len(rooms)):
                acc.extend(by_room[rooms[rng.randrange(len(rooms))]])
            vals.append(sum(acc) / len(acc))
        vals.sort()
        obs = sum(v for vs in by_room.values() for v in vs) / sum(
            len(v) for v in by_room.values())
        return {"n": sum(len(v) for v in by_room.values()), "mean": obs,
                "ci": [vals[int(0.025 * len(vals))], vals[min(len(vals) - 1,
                                                             int(0.975 * len(vals)))]],
                "n_rooms": len(rooms)}

    tie_regret = {
        "tie_discard_decisions": len(tie_decisions),
        "tie_decisions_where_fed": len(tie_fed),
        "chosen_tile_claim_rate_mean": boot_mean(regret_rows, "chosen_rate"),
        "mean_of_tied_alternatives_claim_rate": boot_mean(regret_rows, "mean_alt_rate"),
        "min_of_tied_alternatives_claim_rate": boot_mean(regret_rows, "best_alt_rate"),
        "expected_feed_rate_reduction_if_tiebreak_min_claim_rate": (
            (boot_mean(regret_rows, "chosen_rate")["mean"]
             - boot_mean(regret_rows, "best_alt_rate")["mean"]) if regret_rows else None),
    }

    # ---- 4) 喂牌的后果（关联，不是因果）------------------------------
    win_by_claimer = collections.defaultdict(list)
    for gid, g in games.items():
        for r in g["rounds"]:
            for k in range(4):
                if k == g["my_seat"]:
                    continue
                fed = (r["all"][k].get("fed", 0) > 0)
                win_by_claimer[fed].append((gid, r["winner"] == k))
    feed_consequence = {
        "claimer_won_given_claimed": rate(win_by_claimer[True]),
        "claimer_won_given_no_claim": rate(win_by_claimer[False]),
    }

    # ---- 5) 连庄局里给庄家喂牌 --------------------------------------
    fed_dealer = collections.Counter()
    for gid, g in games.items():
        rs, my = g["rounds"], g["my_seat"]
        for i, r in enumerate(rs):
            d = r["dealer"]
            if d is None or d == my:
                continue
            on_streak = dealer_streak_at(rs, i, my)
            edges = r.get("claim_edges") or []
            by_me = [e for e in edges if e[0] == my]
            to_dealer = [e for e in by_me if e[1] == d]
            fed_dealer["rounds_opp_dealer"] += 1
            fed_dealer["my_claims_fed"] += len(by_me)
            if to_dealer:
                fed_dealer["rounds_i_fed_dealer"] += 1
            if on_streak:
                fed_dealer["rounds_streak"] += 1
                if to_dealer:
                    fed_dealer["rounds_streak_i_fed_dealer"] += 1

    total = len(disc_rows)
    feeds = sum(1 for r in disc_rows if r["fed"])
    tie_rows = [r for r in disc_rows if r["n_tied_best"] > 1]
    tie_feed = sum(1 for r in tie_rows if r["fed"])
    tie_safe = sum(1 for r in tie_rows
                   if r["safe_alt_same_score_same_shanten"] and not r["fed"])

    def pack(rows):
        if not rows:
            return {"n": 0}
        return {
            "n": len(rows),
            "feed_rate": rate([(r["game_id"], r["fed"]) for r in rows]),
            "mean_remaining": mean_se([r["remaining"] for r in rows]),
            "mean_candidates": mean_se([r["n_candidates"] for r in rows]),
            "melded_share": rate([(r["game_id"], (r["n_melds"] or 0) > 0) for r in rows]),
        }
    by_ctx = {k: pack([r for r in disc_rows if r["ctx"] == k])
              for k in sorted(set(r["ctx"] for r in disc_rows))}

    # 决策点分数状态：是否处于「我们被压制」的局内状态
    cf = {
        "meta": {"decisions_scanned": len(decisions), "discard_decisions": total,
                 "audit_roots": list(AUDIT_ROOTS)},
        "reason_field_stats": field_stats,
        "candidate_count_distribution": dict(sorted(cand_counts.items())),
        "discard_feed_overall": {"n": total, "feeds": feeds,
                                 "feed_rate": rate([(r["game_id"], r["fed"]) for r in disc_rows])},
        "discard_feed_by_context": by_ctx,
        "tile_claim_rate": {t: {"n": v["n"], "claimed": v["claimed"],
                                "rate": tile_rate[t]} for t, v in sorted(tile_stat.items())},
        "tie_regret_model": tie_regret,
        "feed_consequence_observational": feed_consequence,
        "fed_dealer": dict(fed_dealer),
        "tie_analysis": {
            "discard_decisions": total,
            "with_tie_at_best_score": len(tie_rows),
            "tie_share": (len(tie_rows) / total if total else None),
            "tie_feed_rate": rate([(r["game_id"], r["fed"]) for r in tie_rows]),
            "tie_with_safe_equal_alternative_and_not_fed": tie_safe,
            "tie_with_safe_equal_alternative_and_not_fed_share_of_ties": (
                tie_safe / len(tie_rows) if tie_rows else None),
        },
    }

    # 样例：压制/连庄情境下「并列最高分但选了会被鸣的那张」的具体窗口
    samples = [r for r in disc_rows
               if r["ctx"] in ("CTX_对手连庄中", "CTX_我方连失2局")
               and r["fed"] and r["safe_alt_same_score_same_shanten"]]
    samples = samples[:args.md_samples]
    cf["samples_fed_with_safe_equal_alternative"] = samples
    cf["_disc_rows"] = disc_rows

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w") as fh:
        json.dump({k: v for k, v in cf.items() if not k.startswith("_")},
                  fh, ensure_ascii=False, indent=1)

    print("[打分面] 候选数分布 " + json.dumps(dict(sorted(cand_counts.items()))))
    print("[打分面] risk_units 非零比例 {0} / river_part 非零比例 {1}".format(
        round(field_stats.get("risk_units", {}).get("nonzero_share", -1), 6),
        round(field_stats.get("river_part", {}).get("nonzero_share", -1), 6)))
    print("[喂牌] 弃牌决策 {0}，被鸣 {1} = {2}".format(
        total, feeds, round(feeds / total, 4) if total else None))
    print("[喂牌] 按情境 " + json.dumps(
        {k: {"n": v["n"], "feed": round(v["feed_rate"]["rate"], 4)} for k, v in by_ctx.items()},
        ensure_ascii=False))
    print("[并列] 最高分并列决策 {0}/{1} = {2}；其中并列内有「同分同向听且未被鸣」备选且我们没被鸣的 {3}".format(
        len(tie_rows), total, round(len(tie_rows) / total, 4) if total else None, tie_safe))
    common = [(t, tile_rate[t], tile_stat[t]["n"]) for t in tile_rate
              if tile_rate[t] is not None and tile_stat[t]["n"] >= 100]
    print("[牌值] 被鸣率最高 5 种 " + json.dumps(
        [(t, round(r, 4), n) for t, r, n in sorted(common, key=lambda x: -x[1])[:5]],
        ensure_ascii=False))
    print("[牌值] 被鸣率最低 5 种 " + json.dumps(
        [(t, round(r, 4), n) for t, r, n in sorted(common, key=lambda x: x[1])[:5]],
        ensure_ascii=False))
    print("[并列代价] " + json.dumps(
        {k: (round(v["mean"], 5) if isinstance(v, dict) and "mean" in v else v)
         for k, v in tie_regret.items()}, ensure_ascii=False))
    print("[喂庄] " + json.dumps(fed_dealer, ensure_ascii=False))
    print("[后果] 被鸣后鸣牌者本局胡率 {0} / 未被鸣时 {1}".format(
        round(feed_consequence["claimer_won_given_claimed"]["rate"], 4),
        round(feed_consequence["claimer_won_given_no_claim"]["rate"], 4)))
    print("[样例] 可避免喂牌样例 {0} 条".format(len(samples)))
    print("[写出] {0}".format(args.out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
