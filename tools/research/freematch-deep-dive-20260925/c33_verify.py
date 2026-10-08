#!/usr/bin/env python3
"""C33 四合一验证：官方金例 + 全量重建一致性 + 性能 + 可达性（可复跑）。

口径冻结在 review/freematch-deep-dive-20260925/C33-PREREG-FACT-EXPOSURE.md。
本脚本**必须从 worktree**（.team-work/c33-fact-exposure）运行，且 src 必须解析到
worktree 的规则源码（脚本会把 worktree/src 抢回 sys.path[0] 并断言）。

用法：
    cd /Users/liyang/hangma-bot/.team-work/c33-fact-exposure
    PYTHONPATH=$PWD/src UV_CACHE_DIR=/tmp/uv-cache \
        /Users/liyang/hangma-bot/.venv/bin/python \
        review/freematch-deep-dive-20260925/c33_verify.py            # 全量（约 10—20 分钟）
    ... c33_verify.py --phase snapshot                                # 只建性能快照
    ... c33_verify.py --phase timing --src /Users/liyang/hangma-bot/src   # 旧代码配对计时
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
import gzip
import json
import os
import pickle
import shutil
import statistics
import subprocess
import sys
import time
from pathlib import Path

MAIN_TREE = _PROJECT_ROOT
ROOT = _PROJECT_ROOT
HERE = Path(__file__).resolve().parent
if ROOT == MAIN_TREE:
    sys.stderr.write(
        "警告：本脚本在主工作树里运行；主树的规则源码**没有** C33 新事实，"
        "读数无意义。请从 worktree .team-work/c33-fact-exposure 运行。\n"
    )

# c31 在 import 时会把「它自己所在树的 src」插到 sys.path[0]；worktree 的副本
# 指向 worktree，正是我们要的规则源码。先插一次以保证顺序确定。
sys.path.insert(0, str(_project_file(_PROJECT_ROOT, ROOT / "src")))
sys.path.insert(0, str(_project_file(_PROJECT_ROOT, ROOT / "review" / "baotou-anatomy-20260925")))
sys.path.insert(0, str(HERE))

import anatomy_lib as AL  # noqa: E402
import c31_action_layer_gap as C31  # noqa: E402

from hangma_bot.hangma import hand_analysis, progression  # noqa: E402
from hangma_bot.hangma.internal_types import counts_from_tiles  # noqa: E402
from hangma_bot.hangma.public_tile_counts import count_public_tiles  # noqa: E402
from hangma_bot.kernel.actions import CANONICAL_TILE_INDEX, Tile  # noqa: E402

RULES = C31.RULES
"""规则模块（C31 口径，同一 RuleConfig）：生产侧与一致性对拍的唯一合法性来源。"""

OUT = _project_file(_PROJECT_ROOT, ROOT / ".team-work" / "c33-fact-exposure")
CACHE_DIR = _project_file(_PROJECT_ROOT, ROOT / ".team-work" / "p6-baotou-route" / "cache")
CLAIM_TYPES = ("chi", "peng")
UNKNOWN = 1 << 30
SNAPSHOT_CLAIM_LIMIT = 3000
SNAPSHOT_OTHER_STRIDE = 50
SNAPSHOT_OTHER_LIMIT = 1000


# ---------------------------------------------------------------------------
# 0. 通用
# ---------------------------------------------------------------------------


def assert_worktree_rules() -> str:
    """断言当前进程加载的规则模块来自 worktree 的 src。"""

    path = Path(progression.__file__).resolve()
    assert str(path).startswith(str(_project_file(_PROJECT_ROOT, ROOT / "src"))), "规则模块不在 worktree: %s" % path
    return str(path)


def c33_key(branch):
    """C33 预登记 §2 的择优键（爆头优先 → 向听最小 → 支持最大 → 规范牌序）。"""

    shanten = branch.get("shanten")
    support = branch.get("support")
    return (
        0 if branch.get("baotou") is True else 1,
        shanten if type(shanten) is int else UNKNOWN,
        -(support if type(support) is int else -1),
        CANONICAL_TILE_INDEX[branch["code"]],
    )


def drop_one(tiles, code):
    """去掉首个同码实例；没有该牌返回 None（不猜）。"""

    kept = list(tiles)
    for index, item in enumerate(kept):
        if item == code:
            del kept[index]
            return tuple(kept)
    return None


def percentiles(samples):
    if not samples:
        return None
    ordered = sorted(samples)
    return {
        "n": len(ordered),
        "p50_ms": 1000.0 * statistics.median(ordered),
        "p99_ms": 1000.0 * ordered[min(len(ordered) - 1, int(0.99 * len(ordered)))],
        "max_ms": 1000.0 * ordered[-1],
        "mean_ms": 1000.0 * statistics.fmean(ordered),
    }


# ---------------------------------------------------------------------------
# 1. 语料：C31 口径的 18 382 窗
# ---------------------------------------------------------------------------


def load_cache():
    """生产视图缓存：只保留响应窗口（逐字沿用 c31_rebuild_validate.load_cache）。"""

    index = collections.defaultdict(list)
    for path in sorted(CACHE_DIR.glob("*.jsonl.gz")):
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            for line in handle:
                row = json.loads(line)
                if row.get("phase") not in ("response_peng", "response_chi"):
                    continue
                index[(row.get("game_id"), row.get("round_no"), row.get("trigger_seq"))].append(row)
    return index


def iter_windows(cache, games, limit=None):
    """按 C31 口径重建并逐窗产出 (key, phase, seat, observation, production 行)。"""

    wanted = {key[0] for key in cache}
    produced = 0
    for game_id in sorted(wanted & set(games)):
        document = games[game_id]["doc"]
        block_meta = C31.round_metadata(document)
        table = [0, 0, 0, 0]
        for round_no, events, start_hands in AL.round_blocks(document):
            if not start_hands or not all(isinstance(hand, list) for hand in start_hands):
                continue
            ended_dealer, ended_scores = C31.round_end_facts(events)
            dealer = (block_meta.get(round_no) or {}).get("dealer")
            if dealer is None:
                dealer = ended_dealer
            if dealer is None:
                dealer = next((index for index, hand in enumerate(start_hands)
                               if len(hand) == 14), None)
            if dealer is None:
                continue
            snaps = C31.reconstruct(events, start_hands, table, dealer)
            for key in [item for item in cache
                        if item[0] == game_id and item[1] == round_no]:
                snap = snaps.get(key[2])
                if snap is None:
                    continue
                for production in cache[key]:
                    seat = production["view"]["visible_state"]["seat"]
                    phase = production["phase"]
                    observation = C31.build_observation(
                        snap, seat, phase, game_id, round_no)
                    produced += 1
                    yield key, phase, seat, observation, production
                    if limit is not None and produced >= limit:
                        return
            if ended_scores is not None:
                table = [a + b for a, b in zip(table, ended_scores)]


# ---------------------------------------------------------------------------
# 2. 分析侧独立计算（不复用生产侧任何中间对象）
# ---------------------------------------------------------------------------


def analysis_side(observation, action, action_key):
    """从鸣牌后观察独立重建「最优跟打」的四个读数。

    独立之处：手牌由 C31.post_claim_observation 的机械搬运得到（不是生产侧的
    WindowContext 基座）；跟打全集自己从 post.my_hand 去重枚举；向听与有效牌只
    调 hand_analysis；张数按文档口径 4 − 弃后手牌 − 去重公开牌 − 本动作新公开
    自己折算；爆头**无条件**调 progression.baotou_after_discard（生产侧对非听牌
    分支走了「向听 > 0 ⇒ 必非爆头」的等价短路）——因此 100% 一致率同时就是该
    短路的等价性对照：任一分支短路取值与全量规则调用不符，一致率立刻不为 100%。
    """

    post = C31.post_claim_observation(observation, action)
    if post is None:
        return None
    seat = observation.seat
    melds_after = len(post.melds[seat])
    hand = tuple(tile.code for tile in post.my_hand)
    if not hand:
        return None
    public = count_public_tiles(observation)
    before = collections.Counter(tile.code for tile in observation.my_hand)
    after_claim = collections.Counter(hand)
    newly_base = {code: amount for code, amount in (before - after_claim).items()
                  if amount > 0}
    branches = []
    for code in sorted(set(hand), key=lambda item: CANONICAL_TILE_INDEX[item]):
        remaining_hand = drop_one(hand, code)
        if remaining_hand is None:
            continue
        summary = hand_analysis.analyse_hand(
            tuple(Tile(item) for item in remaining_hand), melds_after)
        newly = dict(newly_base)
        newly[code] = newly.get(code, 0) + 1
        counts = counts_from_tiles(tuple(Tile(item) for item in remaining_hand))
        total = 0
        known = True
        for useful in summary.useful_tiles:
            index = CANONICAL_TILE_INDEX[useful.code]
            public_count = public[index]
            if public_count is None:
                known = False
                break
            total += max(0, 4 - counts[index] - public_count - newly.get(useful.code, 0))
        try:
            baotou = bool(progression.baotou_after_discard(
                tuple(Tile(item) for item in remaining_hand), melds_after))
        except (ValueError, KeyError):
            baotou = None
        branches.append({"code": code, "shanten": summary.shanten,
                         "support": total if known else None, "baotou": baotou})
    if not branches:
        return None
    best = min(branches, key=c33_key)
    return {
        "branches": tuple((b["code"], b["shanten"], b["support"], b["baotou"])
                          for b in branches),
        "best": best,
        "best_key": "{0}#{1}".format(action_key, best["code"]),
    }


def production_side(facts):
    """生产侧的四个新字段 + 逐分支三元组。"""

    return {
        "branches": tuple((b.followup_discard, b.combined_shanten,
                           b.support_remaining, b.baotou_after)
                          for b in facts.followup_branches),
        "baotou": facts.followup_baotou,
        "support": facts.followup_support,
        "shanten": facts.followup_shanten,
        "key": facts.followup_best_key,
    }


# ---------------------------------------------------------------------------
# 3. 一致性（C31 口径 18 382 窗）
# ---------------------------------------------------------------------------


def consistency(limit=None, snapshot_path=None):
    cache = load_cache()
    games = {game["game_id"]: game for game in AL.load_games()}
    print("生产响应窗口缓存：%d 个 (game,round,seq) 键 / %d 条窗口"
          % (len(cache), sum(len(v) for v in cache.values())))
    counts = collections.Counter()
    per_field = collections.Counter()
    mismatch_examples = []
    fidelity_examples = []
    snapshot = []
    claim_windows = 0
    anchor = collections.Counter()
    started = time.time()
    for index, (key, phase, seat, observation, production) in enumerate(
            iter_windows(cache, games, limit=limit)):
        counts["windows"] += 1
        analysis = RULES.analyze(observation)
        by_key = {}
        for candidate in analysis.legal_candidates:
            facts = candidate.facts
            by_key[candidate.action_key] = candidate
            if candidate.action_key.startswith(("chi:", "peng:")):
                counts["claims"] += 1
                if facts is None or facts.followup_branches is None:
                    counts["claims_without_branches"] += 1
                    continue
                counts["claims_with_branches"] += 1
        recorded = {}
        recorded_action = {}
        for action in production["view"]["actions"]:
            recorded_action[action["action_key"]] = action
            if action["action_type"] in CLAIM_TYPES and action.get("followup_branches"):
                recorded[action["action_key"]] = action["followup_branches"]
        has_claim = False
        window_new_baotou = False
        window_c32_baotou = False
        window_action_baotou = False
        window_new_increment = False
        window_c32_increment = False
        for action_key, candidate in sorted(by_key.items()):
            if not action_key.startswith(("chi:", "peng:")):
                continue
            facts = candidate.facts
            if facts is None or facts.followup_branches is None:
                continue
            has_claim = True
            prod = production_side(facts)
            side = analysis_side(observation, candidate.action, action_key)
            if side is None:
                counts["side_none"] += 1
            else:
                if prod["branches"] != side["branches"]:
                    per_field["branches"] += 1
                    if len(mismatch_examples) < 20:
                        mismatch_examples.append({
                            "kind": "branches", "key": list(key), "seat": seat,
                            "action_key": action_key,
                            "production": list(prod["branches"]),
                            "analysis": list(side["branches"])})
                expected_map = {
                    "baotou": side["best"]["baotou"],
                    "support": side["best"]["support"],
                    "shanten": side["best"]["shanten"],
                    "key": side["best_key"],
                }
                for field, expected in expected_map.items():
                    if prod[field] != expected:
                        per_field[field] += 1
                        if len(mismatch_examples) < 20:
                            mismatch_examples.append({
                                "kind": field, "key": list(key), "seat": seat,
                                "action_key": action_key,
                                "production": prod[field], "analysis": expected})
                counts["compared"] += 1
            if action_key in recorded:
                counts["recorded_pairs"] += 1
                recorded_triples = tuple(
                    (item.get("followup_discard"), item.get("combined_shanten"),
                     item.get("support_remaining")) for item in recorded[action_key])
                mine = tuple((code, shanten, support)
                             for code, shanten, support, _ in prod["branches"])
                if recorded_triples == mine:
                    counts["recorded_match"] += 1
                else:
                    counts["recorded_mismatch"] += 1
                    if len(fidelity_examples) < 10:
                        fidelity_examples.append({
                            "key": list(key), "seat": seat, "action_key": action_key,
                            "recorded": list(recorded_triples), "rebuilt": list(mine)})
            # 动作层爆头取**生产记录**（线上跑过 value 分析，动作层 baotou_after 才有值；
            # 本脚本按 C31 口径只跑 RULES.analyze(观察)，不重跑昂贵分值分析）。
            action_baotou = (
                (recorded_action.get(action_key) or {}).get("baotou_after") is True)
            c32_branch = next((item for item in facts.followup_branches
                               if item.followup_discard == facts.best_followup_discard),
                              None)
            c32_baotou = None if c32_branch is None else c32_branch.baotou_after is True
            if facts.followup_baotou is True:
                window_new_baotou = True
            if c32_baotou:
                window_c32_baotou = True
            if action_baotou:
                window_action_baotou = True
            if c32_baotou and not action_baotou:
                window_c32_increment = True
            if facts.followup_baotou is True and not action_baotou:
                window_new_increment = True
        if has_claim:
            claim_windows += 1
            for name, flag in (("new_baotou", window_new_baotou),
                               ("c32_baotou", window_c32_baotou),
                               ("action_baotou", window_action_baotou),
                               ("new_increment", window_new_increment),
                               ("c32_increment", window_c32_increment)):
                if flag:
                    anchor[name] += 1
        if snapshot_path is not None:
            claim_taken = sum(1 for item in snapshot if item[1])
            other_taken = sum(1 for item in snapshot if not item[1])
            if has_claim and claim_taken < SNAPSHOT_CLAIM_LIMIT:
                snapshot.append((observation, True))
            elif (not has_claim) and index % SNAPSHOT_OTHER_STRIDE == 0 and \
                    other_taken < SNAPSHOT_OTHER_LIMIT:
                snapshot.append((observation, False))
        if counts["windows"] % 2000 == 0:
            print("  … %d 窗 / %.1f 秒" % (counts["windows"], time.time() - started))

    payload = {
        "windows": counts["windows"],
        "claims": counts["claims"],
        "claims_with_branches": counts["claims_with_branches"],
        "claims_without_branches": counts["claims_without_branches"],
        "compared_claims": counts["compared"],
        "side_none": counts["side_none"],
        "field_mismatches": dict(per_field),
        "mismatch_examples": mismatch_examples,
        "fidelity": {
            "recorded_pairs": counts["recorded_pairs"],
            "match": counts["recorded_match"],
            "mismatch": counts["recorded_mismatch"],
            "rate": (counts["recorded_match"] / counts["recorded_pairs"]
                     if counts["recorded_pairs"] else None),
            "examples": fidelity_examples,
        },
        "anchors_on_corpus": {
            "windows_with_claim": claim_windows,
            "window_new_baotou": anchor["new_baotou"],
            "window_c32_width_best_baotou": anchor["c32_baotou"],
            "window_action_layer_baotou": anchor["action_baotou"],
            "window_new_increment": anchor["new_increment"],
            "window_c32_increment": anchor["c32_increment"],
        },
        "elapsed_sec": time.time() - started,
    }
    consistent = not any(per_field.values())
    payload["consistent"] = consistent
    (_project_file(_PROJECT_ROOT, OUT / "consistency.json")).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print()
    print("== 全量重建一致性（C31 口径窗）")
    print("受检窗口 %d；吃/碰候选 %d（可枚举跟打 %d，未产出事实 %d）；对拍候选 %d"
          % (payload["windows"], payload["claims"], payload["claims_with_branches"],
             payload["claims_without_branches"], payload["compared_claims"]))
    if consistent:
        print("逐位一致率：**100.00%**（分支集合 + 逐分支三元组 + 4 个新字段，全部相等）")
    else:
        print("**不一致**：%s（清单见 consistency.json 的 mismatch_examples）"
              % json.dumps(dict(per_field), ensure_ascii=False))
    fidelity = payload["fidelity"]
    print("保真度锚点（重建生产侧 vs 缓存记录）：%d/%d = %.2f%%"
          % (fidelity["match"], fidelity["recorded_pairs"],
             100.0 * (fidelity["rate"] or 0.0)))
    print("锚点（本语料，窗）：有鸣牌候选 %d；新口径爆头可达 %d；C32 口径（牌效最优跟打）爆头 %d；"
          "动作层爆头 %d；新口径增量（动作层看不见）%d；C32 口径增量 %d"
          % (claim_windows, anchor["new_baotou"], anchor["c32_baotou"],
             anchor["action_baotou"], anchor["new_increment"], anchor["c32_increment"]))
    if snapshot_path is not None:
        with open(snapshot_path, "wb") as handle:
            pickle.dump(snapshot, handle)
        print("性能快照：%d 个观察（含鸣牌候选 %d）写入 %s"
              % (len(snapshot), sum(1 for item in snapshot if item[1]), snapshot_path))
    return payload


# ---------------------------------------------------------------------------
# 4. 官方金例对拍（沿用既有命令，不新造口径）
# ---------------------------------------------------------------------------


def gold_cases():
    out = _project_file(_PROJECT_ROOT, OUT / "gold")
    out.mkdir(parents=True, exist_ok=True)
    tool = (_project_file(_PROJECT_ROOT, ROOT / "review" / "llm-guided-heuristic-route-2026-09-15" / "tools"
            / "sitin_official_crosscheck.py"))
    env = dict(os.environ, PYTHONPATH=str(_project_file(_PROJECT_ROOT, ROOT / "src")), UV_CACHE_DIR="/tmp/uv-cache")
    started = time.time()
    done = subprocess.run([sys.executable, str(tool), "--out", str(out)],
                          cwd=str(ROOT), env=env, capture_output=True, text=True)
    report = json.loads((out / "crosscheck.json").read_text(encoding="utf-8"))
    summary = collections.Counter()
    for counter in report["by_fixture"].values():
        summary.update(counter)
    payload = {
        "fixtures": report["fixtures"],
        "cases": summary.get("cases", 0),
        "hu_match": summary.get("hu_match", 0),
        "fan_match": summary.get("fan_match", 0),
        "skipped": summary.get("skipped", 0),
        "mismatched_tags": len([tag for tag, counter in report["by_tag"].items()
                                if counter.get("fan_mismatch") or counter.get("hu_mismatch")]),
        "engine_error": summary.get("engine_error", 0),
        "mismatches": report["mismatches"][:20],
        "returncode": done.returncode,
        "stdout_tail": done.stdout.strip().splitlines()[-6:],
        "elapsed_sec": time.time() - started,
    }
    payload["passed"] = (
        payload["hu_match"] == payload["cases"]
        and payload["fan_match"] == payload["cases"]
        and payload["mismatched_tags"] == 0
        and payload["engine_error"] == 0
    )
    (_project_file(_PROJECT_ROOT, OUT / "gold.json")).write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                                   encoding="utf-8")
    print()
    print("== 官方金例对拍（%d 夹具）" % payload["fixtures"])
    print("用例 %d：hu 一致 %d / fan 一致 %d / 不一致标签 %d / 引擎异常 %d ⇒ %s"
          % (payload["cases"], payload["hu_match"], payload["fan_match"],
             payload["mismatched_tags"], payload["engine_error"],
             "通过" if payload["passed"] else "**未通过**"))
    return payload


# ---------------------------------------------------------------------------
# 5. 性能（配对计时：旧代码 vs 新代码，同一批重建观察）
# ---------------------------------------------------------------------------


def run_timing(src, snapshot_path, tag):
    """在子进程里用指定 src 计时（保证规则模块只来自一个树）。"""

    code = (
        "import json, pickle, sys, time\n"
        "sys.path.insert(0, %r)\n"
        "from hangma_bot.hangma import progression\n"
        "from hangma_bot.hangma.engine import HangmaRules\n"
        "from hangma_bot.kernel.config import RuleConfig\n"
        "assert progression.__file__.startswith(%r), progression.__file__\n"
        "rules = HangmaRules(RuleConfig(ruleset_version='hangma-mvp-v10-public-counts',"
        " base_score=1, you_cai_bi_kao=False))\n"
        "with open(%r, 'rb') as handle:\n"
        "    rows = pickle.load(handle)\n"
        "sample = []\n"
        "for observation, has_claim in rows:\n"
        "    mark = time.perf_counter()\n"
        "    rules.analyze(observation)\n"
        "    sample.append((time.perf_counter() - mark, has_claim))\n"
        "from hangma_bot.hangma.hand_analysis import math_backend_info\n"
        "print(json.dumps({'src': %r, 'backend': math_backend_info(), 'samples': sample}))\n"
    ) % (str(src), str(src), str(snapshot_path), tag)
    env = dict(os.environ, PYTHONPATH=str(src), UV_CACHE_DIR="/tmp/uv-cache")
    done = subprocess.run([sys.executable, "-c", code], cwd=str(ROOT), env=env,
                          capture_output=True, text=True)
    if done.returncode != 0:
        raise RuntimeError("计时子进程失败（%s）：%s" % (tag, done.stderr[-2000:]))
    return json.loads(done.stdout.strip().splitlines()[-1])


def pure_python_src(source_root, tag):
    """同一份代码的**纯 Python 回退**口径：复制 src 并去掉原生 .so。

    为什么必须做：原生分组数学（_grouped_native，构建产物、不进 git）在 worktree 里
    不存在；若直接比较「主树（有原生）vs worktree（无原生）」，测到的 20—30 倍差是
    **后端差**而不是新事实差。这里把两个后端都跑齐，才谈得上「新事实带来的开销」。
    """

    dst = _project_file(_PROJECT_ROOT, OUT / ("pure-src-" + tag))
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(source_root / "src", dst / "src",
                    ignore=shutil.ignore_patterns("__pycache__", "*.so"))
    return dst / "src"


def timing(snapshot_path):
    if not snapshot_path.exists():
        print("缺性能快照 %s：先跑 --phase snapshot" % snapshot_path)
        return None
    main_native = run_timing(_project_file(_PROJECT_ROOT, MAIN_TREE / "src"), snapshot_path, "main")
    new_native = run_timing(_project_file(_PROJECT_ROOT, ROOT / "src"), snapshot_path, "worktree")
    main_pure = run_timing(pure_python_src(MAIN_TREE, "main"), snapshot_path, "main-pure")
    new_pure = run_timing(pure_python_src(ROOT, "worktree"), snapshot_path, "worktree-pure")
    old_samples = [item[0] for item in main_native["samples"]]
    new_samples = [item[0] for item in new_native["samples"]]
    flags = [item[1] for item in new_native["samples"]]
    assert len(old_samples) == len(new_samples), "两侧观察数不一致"
    deltas = [n - o for n, o in zip(new_samples, old_samples)]
    claim_deltas = [d for d, flag in zip(deltas, flags) if flag]
    claim_new = [s for s, flag in zip(new_samples, flags) if flag]
    delta_box = percentiles(deltas)
    payload = {
        "observations": len(new_samples),
        "claim_observations": sum(1 for flag in flags if flag),
        "old_all": percentiles(old_samples),
        "new_all": percentiles(new_samples),
        "delta_all": delta_box,
        "new_claims": percentiles(claim_new),
        "delta_claims": percentiles(claim_deltas),
        "delta_max_ms": 1000.0 * max(deltas),
        "delta_p99_share_of_1s": delta_box["p99_ms"] / 1000.0,
        "delta_max_share_of_1s": (1000.0 * max(deltas)) / 1000.0,
    }
    pure_old = [item[0] for item in main_pure["samples"]]
    pure_new = [item[0] for item in new_pure["samples"]]
    pure_deltas = [n - o for n, o in zip(pure_new, pure_old)]
    pure_delta_box = percentiles(pure_deltas)
    payload.update({
        "backends": {"main": main_native.get("backend"), "worktree": new_native.get("backend"),
                     "main_pure": main_pure.get("backend"), "worktree_pure": new_pure.get("backend")},
        "pure_old_all": percentiles(pure_old),
        "pure_new_all": percentiles(pure_new),
        "pure_delta_all": pure_delta_box,
        "pure_delta_max_ms": 1000.0 * max(pure_deltas),
        "pure_old_claims": percentiles([s for s, flag in zip(pure_old, flags) if flag]),
        "pure_new_claims": percentiles([s for s, flag in zip(pure_new, flags) if flag]),
    })
    payload["ceiling_ok"] = (
        delta_box["p99_ms"] <= 10.0 and payload["delta_max_ms"] <= 100.0)
    payload["ceiling_ok_pure_python"] = (
        pure_delta_box["p99_ms"] <= 10.0 and payload["pure_delta_max_ms"] <= 100.0)
    (_project_file(_PROJECT_ROOT, OUT / "timing.json")).write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                                     encoding="utf-8")
    print()
    print("== 性能（同一批重建观察 %d 个；配对计时，旧代码 = 主树 src）" % payload["observations"])
    print("| 口径 | p50 (ms) | p99 (ms) | max (ms) | 均值 (ms) |")
    print("| --- | ---: | ---: | ---: | ---: |")
    for label, box in (("旧代码（无新事实）", payload["old_all"]),
                       ("新代码（含新事实）", payload["new_all"]),
                       ("增量（全部窗）", payload["delta_all"]),
                       ("新代码（含鸣牌候选窗 n=%d）" % payload["claim_observations"],
                        payload["new_claims"]),
                       ("增量（含鸣牌候选窗）", payload["delta_claims"])):
        print("| %s | %.3f | %.3f | %.3f | %.3f |"
              % (label, box["p50_ms"], box["p99_ms"], box["max_ms"], box["mean_ms"]))
    print("后端实现：主树 %s / worktree %s（原生）；纯 Python 回退 %s / %s"
          % (payload["backends"]["main"]["implementation"],
             payload["backends"]["worktree"]["implementation"],
             payload["backends"]["main_pure"]["implementation"],
             payload["backends"]["worktree_pure"]["implementation"]))
    print()
    print("| 后端 | 旧代码 p50/p99/max (ms) | 新代码 p50/p99/max (ms) | 增量 p50/p99/max (ms) |")
    print("| --- | --- | --- | --- |")
    for label, old_box, new_box, box in (
            ("原生（线上路径）", payload["old_all"], payload["new_all"], delta_box),
            ("纯 Python 回退", payload["pure_old_all"], payload["pure_new_all"],
             pure_delta_box)):
        print("| %s | %.3f / %.3f / %.3f | %.3f / %.3f / %.3f | %.3f / %.3f / %.3f |"
              % (label, old_box["p50_ms"], old_box["p99_ms"], old_box["max_ms"],
                 new_box["p50_ms"], new_box["p99_ms"], new_box["max_ms"],
                 box["p50_ms"], box["p99_ms"], box["max_ms"]))
    print("含鸣牌候选窗 n=%d：新代码原生 p50/p99/max %.3f/%.3f/%.3f ms；回退 %.3f/%.3f/%.3f ms"
          % (payload["claim_observations"], payload["new_claims"]["p50_ms"],
             payload["new_claims"]["p99_ms"], payload["new_claims"]["max_ms"],
             payload["pure_new_claims"]["p50_ms"], payload["pure_new_claims"]["p99_ms"],
             payload["pure_new_claims"]["max_ms"]))
    print("预登记上限（增量 p99 <= 10.0 ms 且 max <= 100.0 ms）："
          "原生增量 p99 %.3f ms（%.3f%% 的 1 s）/ max %.3f ms ⇒ %s；"
          "回退增量 p99 %.3f ms（%.3f%% 的 1 s）/ max %.3f ms ⇒ %s"
          % (delta_box["p99_ms"], 100.0 * payload["delta_p99_share_of_1s"],
             payload["delta_max_ms"], "通过" if payload["ceiling_ok"] else "**超出上限**",
             pure_delta_box["p99_ms"], pure_delta_box["p99_ms"] / 10.0,
             payload["pure_delta_max_ms"],
             "通过" if payload["ceiling_ok_pure_python"] else "**超出上限**"))
    return payload


# ---------------------------------------------------------------------------
# 6. 可达性（仓库既有 l1_reach.py；视图只补新字段）
# ---------------------------------------------------------------------------


def reach():
    # 候选源码按任务书放在**主工作树**的 candidates 目录（它不改 hangma，不需要
    # worktree）；l1_reach.py 仍是 worktree 的既有副本、未改一字。
    cand_dir = _project_file(_PROJECT_ROOT, MAIN_TREE / "review" / "freematch-deep-dive-20260925" / "candidates")
    arm = cand_dir / "OPTY-R18-C33-FOLLOWUP-BAOTOU.py"
    control = cand_dir / "OPTY-R18-C33-NEGCTRL-MISSINGKEY.py"
    audit = cand_dir / "OPTY-R18-C33-AUDIT-ACTIONLAYER.py"
    script = _project_file(_PROJECT_ROOT, HERE / "l1_reach.py")
    env = dict(os.environ, PYTHONPATH=str(_project_file(_PROJECT_ROOT, ROOT / "src")), UV_CACHE_DIR="/tmp/uv-cache")
    started = time.time()
    done = subprocess.run([sys.executable, str(script), str(arm), str(control), str(audit)],
                          cwd=str(ROOT), env=env, capture_output=True, text=True)
    print()
    print("== 可达性（l1_reach.py，未改一字；p6 生产真实视图只补 C33 新字段）")
    print(done.stdout.strip())
    if done.returncode != 0:
        print("l1_reach 退出码 %d：%s" % (done.returncode, done.stderr[-1500:]))
    payload = {"command": " ".join([str(script), arm.name, control.name, audit.name]),
               "returncode": done.returncode, "stdout": done.stdout,
               "stderr_tail": done.stderr[-1500:], "elapsed_sec": time.time() - started}
    (_project_file(_PROJECT_ROOT, OUT / "reach.json")).write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                                    encoding="utf-8")
    return payload


def reach_denominators():
    """p6 窗全集、含鸣牌候选的窗、以及候选面可读性的正/负控读数。"""

    sys.path.insert(0, str(_project_file(_PROJECT_ROOT, ROOT / ".team-work" / "p6-baotou-route")))
    import p6_lib  # noqa: E402  —— worktree 内的桥（只加键）

    counts = collections.Counter()
    for row in p6_lib.iter_rooms(p6_lib.ROOMS_PRIMARY + p6_lib.ROOMS_EXTRA):
        counts["windows"] += 1
        for action in row["view"]["actions"]:
            if action["action_type"] == "gang":
                counts["gangs"] += 1
                if action.get("followup_best_key") is not None:
                    counts["gang_with_key"] += 1
        claims = [item for item in row["view"]["actions"]
                  if item["action_type"] in CLAIM_TYPES]
        if not claims:
            continue
        counts["windows_with_claims"] += 1
        counts["claims"] += len(claims)
        readable = [item for item in claims if item.get("followup_best_key") is not None]
        counts["claims_readable"] += len(readable)
        if any(item.get("followup_baotou") is True for item in readable):
            counts["windows_new_baotou"] += 1
        if any(item.get("followup_baotou") is True and item.get("baotou_after") is not True
               for item in readable):
            counts["windows_new_baotou_increment"] += 1
        if any(item.get("baotou_after") is True for item in readable):
            counts["windows_action_baotou"] += 1
    stats = dict(counts)
    stats["p6_enrichment"] = p6_lib.enrichment_stats()
    stats["coverage_claims"] = (counts["claims_readable"] / counts["claims"]
                                if counts["claims"] else None)
    (_project_file(_PROJECT_ROOT, OUT / "reach-denominators.json")).write_text(
        json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
    print()
    print("== 可达性分母与可读性（p6 生产真实视图）")
    print("窗 %d；含吃/碰候选的窗 %d；吃/碰候选 %d（可读新字段 %d，覆盖率 %.4f%%）；"
          "明杠候选 %d（预登记适用口径 = 0，实测非空 %d）"
          % (stats["windows"], stats["windows_with_claims"], stats["claims"],
             stats["claims_readable"], 100.0 * (stats["coverage_claims"] or 0.0),
             stats["gangs"], stats.get("gang_with_key", 0)))
    print("含「新口径跟打后爆头可达」的窗 %d（其中动作层看不见的增量 %d；动作层爆头窗 %d）"
          % (stats["windows_new_baotou"], stats["windows_new_baotou_increment"],
             stats.get("windows_action_baotou", 0)))
    return stats


# ---------------------------------------------------------------------------
# 7. 摘要影响
# ---------------------------------------------------------------------------


def rules_hash(src_root):
    from hangma_bot.simulation.artifacts import compute_rules_hash
    return compute_rules_hash(str(src_root))


def summary_impact():
    old = rules_hash(MAIN_TREE)
    new = rules_hash(ROOT)
    from hangma_bot.policy.r18_integrated_positive_v2_release import (
        R18_INTEGRATED_POSITIVE_V2_RULES_SOURCE_HASH as BOUND)
    payload = {
        "old_hash_main_tree": old,
        "new_hash_worktree": new,
        "changed": old != new,
        "frozen_release_bound_hash": BOUND,
        "frozen_release_matches_new": BOUND == new,
        "note": ("沿用本改动必须构造新的发布包（人审）；本轮不构造，"
                 "冻结发布包与线上配置一字未动。"),
    }
    (_project_file(_PROJECT_ROOT, OUT / "rules-hash.json")).write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                                         encoding="utf-8")
    print()
    print("== 上游摘要影响（rules_source_hash，范围 src/hangma_bot/hangma 全部 .py/.c/.h）")
    print("主树（改动前 / 未改）：%s" % old)
    print("worktree（含 C33 新事实）：%s" % new)
    print("冻结发布包绑定 %s；与新值是否一致：%s"
          % (BOUND, "是" if BOUND == new else "**否**"))
    print("结论：**沿用本改动必须构造新发布包（人审）；本轮不构造**。")
    return payload


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", default="full",
                        choices=("full", "snapshot", "timing", "consistency"))
    parser.add_argument("--src", default=None)
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    snapshot_path = _project_file(_PROJECT_ROOT, OUT / "timing-snapshot.pkl")
    print("规则模块：%s" % assert_worktree_rules())

    if args.phase == "timing":
        source = Path(args.src) if args.src else _project_file(_PROJECT_ROOT, MAIN_TREE / "src")
        result = run_timing(source, snapshot_path, str(source))
        print(json.dumps({"src": str(source),
                          "all": percentiles([item[0] for item in result["samples"]]),
                          "claims": percentiles([item[0] for item in result["samples"]
                                                 if item[1]])},
                         ensure_ascii=False, indent=2))
        return 0

    if args.phase in ("snapshot", "consistency"):
        consistency(limit=args.limit, snapshot_path=snapshot_path)
        return 0

    started = time.time()
    gold = gold_cases()
    consistency_payload = consistency(snapshot_path=snapshot_path)
    timing_payload = timing(snapshot_path)
    reach_payload = reach()
    denominators = reach_denominators()
    impact = summary_impact()
    payload = {
        "gold": gold,
        "consistency": {key: value for key, value in consistency_payload.items()
                        if key != "mismatch_examples"},
        "timing": timing_payload,
        "reach": {"returncode": reach_payload["returncode"],
                  "elapsed_sec": reach_payload["elapsed_sec"]},
        "denominators": denominators,
        "rules_hash": impact,
        "elapsed_sec": time.time() - started,
    }
    (_project_file(_PROJECT_ROOT, OUT / "summary.json")).write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                                      encoding="utf-8")
    print()
    print("总用时 %.1f 秒；产物写入 %s" % (time.time() - started, OUT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
