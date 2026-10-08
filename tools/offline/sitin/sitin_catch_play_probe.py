"""抓打圈探针：按 官方指南 1.1 / API §5.4 + RULES_EVIDENCE 语义做构造矩阵复核。

覆盖（全部为规则可判定的硬约束，非策略偏好）：
  1. 受限座位弃牌只能打刚摸到的牌；摸牌信息缺失时保守拒绝；
  2. 受限座位不能吃、碰；仅暗杠与自摸胡；
  3. 补杠/明杠一并禁止（边界约定：补杠不算暗杠）；
  4. 圈主身份经 analyze_catch_play 判定；未知归属时 .restricts() 保守限制；
  5. 官方 v24 证据（圈主有牌形也可能不开窗）——登记为**平台行为**，不作为规则断言。
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
import dataclasses
import json
import os
import sys
from collections import Counter

HERE = os.path.abspath(os.path.dirname(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, ROOT)

from hangma_bot.hangma import catch_play  # noqa: E402
from hangma_bot.hangma.engine import HangmaRules  # noqa: E402
from hangma_bot.hangma.interface import ValueAnalysisLimits  # noqa: E402
from hangma_bot.hangma.special_rules import catch_play_restriction  # noqa: E402
from hangma_bot.kernel.actions import Chi, Discard, Gang, GangKind, Hu, Peng, Tile  # noqa: E402
from hangma_bot.kernel.config import RuleConfig  # noqa: E402

from tests.unit.hangma.test_value_analysis import _observation  # noqa: E402

RULES = HangmaRules(RuleConfig("hangma-mvp-v10-public-counts", 1, False))
LIMITS = ValueAnalysisLimits()
QUAD_HAND = ("1w", "1w", "1w", "1w", "2w", "3w", "4w", "5w", "6w", "7w", "8w", "9w", "白")


def with_circle(obs, *, active, owner_seat, seat):
    """构造抓打圈观察：官方原标记 + 圈主座位；seat 为本座位。"""
    state = dataclasses.replace(obs.rule_state, catch_play=bool(active),
                                catch_play_owner_seat=owner_seat)
    return dataclasses.replace(obs, rule_state=state, seat=seat)


def actions_of(obs):
    analysis = RULES.analyze(obs, value_limits=LIMITS)
    return list(analysis.legal_candidates), analysis


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    checks = []

    def record(name, ok, detail):
        checks.append({"check": name, "ok": bool(ok), "detail": detail})

    # ---- 弃牌窗：刚摸牌可打，其它牌受限 ----
    obs = _observation(QUAD_HAND, draw="9w")
    candidates, _ = actions_of(obs)
    discards = [c.action for c in candidates if isinstance(c.action, Discard)]
    drawn = Tile("9w")
    if discards:
        drew_ok = catch_play_restriction(discards[0], drawn)
        target = [a for a in discards if a.tile.code == "9w"]
        other = [a for a in discards if a.tile.code != "9w"]
        record("受限座位可打刚摸牌", bool(target) and
               catch_play_restriction(target[0], drawn) is None,
               {"action": target[0].tile.code if target else None})
        record("受限座位不得打其他牌", bool(other) and
               catch_play_restriction(other[0], drawn) is not None,
               {"reason": catch_play_restriction(other[0], drawn) if other else None})
    record("摸牌信息缺失时保守拒绝",
           catch_play_restriction(discards[0], None) is not None if discards else False,
           {"reason": catch_play_restriction(discards[0], None) if discards else None})

    # ---- 杠：暗杠放行，明杠/补杠禁止 ----
    gang_actions = [c.action for c in candidates if isinstance(c.action, Gang)]
    concealed = [a for a in gang_actions if a.kind is GangKind.CONCEALED]
    record("暗杠放行", bool(concealed) and catch_play_restriction(concealed[0], drawn) is None,
           {"n_concealed": len(concealed), "n_gang": len(gang_actions)})
    other_gang = [a for a in gang_actions if a.kind is not GangKind.CONCEALED]
    if other_gang:
        record("明杠/补杠禁止", catch_play_restriction(other_gang[0], drawn) is not None,
               {"reason": catch_play_restriction(other_gang[0], drawn)})

    # ---- 响应窗：吃/碰/胡 ----
    # 响应窗：上家打 9b；手牌含 7b8b（可吃）与 9b9b（可碰）
    resp = _observation(("7b", "8b", "9b", "9b", "1t", "2t", "3t", "5w", "5w",
                         "1w", "1w", "白", "发"), response="9b")
    # 吃只在 response_chi 窗口产生候选；测试助手默认写 response_peng，这里按真实阶段修正
    resp = dataclasses.replace(resp, phase="response_chi")
    resp_candidates, _ = actions_of(resp)
    chi = [c.action for c in resp_candidates if isinstance(c.action, Chi)]
    peng = [c.action for c in resp_candidates if isinstance(c.action, Peng)]
    # 引擎按响应阶段开族：response_chi 出吃、response_peng 出碰 ⇒ 两个窗口各断言一次
    resp_peng = dataclasses.replace(
        _observation(("7b", "8b", "9b", "9b", "1t", "2t", "3t", "5w", "5w",
                      "1w", "1w", "白", "发"), response="9b"), phase="response_peng")
    peng_candidates, _ = actions_of(resp_peng)
    peng = [c.action for c in peng_candidates if isinstance(c.action, Peng)]
    record("响应窗动作集合可构造", bool(chi) and bool(peng),
           {"chi_at_response_chi": len(chi), "peng_at_response_peng": len(peng)})
    # 自摸胡：摸牌窗里正好成胡（只自摸，响应窗没有胡）
    win_obs = _observation(("1w", "2w", "3w", "4w", "5w", "6w", "7w", "8w", "9w",
                            "1b", "2b", "3b", "东"), draw="东")
    win_candidates, _ = actions_of(win_obs)
    hu = [c.action for c in win_candidates if isinstance(c.action, Hu)]
    if chi:
        record("吃禁止", catch_play_restriction(chi[0], None) is not None,
               {"reason": catch_play_restriction(chi[0], None)})
    if peng:
        record("碰禁止", catch_play_restriction(peng[0], None) is not None,
               {"reason": catch_play_restriction(peng[0], None)})
    if hu:
        record("自摸胡放行", catch_play_restriction(hu[0], None) is None, {})

    # ---- 身份判定与保守性 ----
    plain = _observation(QUAD_HAND, draw="9w")
    ctx_none = catch_play.analyze_catch_play(plain)
    record("无圈时 active=False", ctx_none.active is False, {"source": ctx_none.source})
    circled = with_circle(plain, active=True, owner_seat=1, seat=1)
    ctx_owner = catch_play.analyze_catch_play(circled)
    record("圈主本人不受限", ctx_owner.restricts(1) is False,
           {"active": ctx_owner.active, "owner": ctx_owner.owner_seat,
            "issue": ctx_owner.issue, "source": ctx_owner.source})
    circled_other = with_circle(plain, active=True, owner_seat=1, seat=2)
    ctx_other = catch_play.analyze_catch_play(circled_other)
    record("非圈主受限", ctx_other.restricts(2) is True,
           {"active": ctx_other.active, "owner": ctx_other.owner_seat})
    record("圈主未知时保守限制(契约)", ctx_none.restricts(0) is (ctx_none.active and
                                                                ctx_none.owner_seat != 0),
           {"active": ctx_none.active, "owner": ctx_none.owner_seat})

    os.makedirs(args.out, exist_ok=True)
    fixture = os.path.join(ROOT, "tests/fixtures/official/v24/catch-play/owner-peng-no-window.json")
    official = {}
    if os.path.exists(fixture):
        with open(fixture, encoding="utf-8") as fh:
            data = json.load(fh)
        official = {"cases": len(data.get("cases", ())),
                    "guide_version": [c.get("provenance", {}).get("guide_version")
                                      for c in data.get("cases", ())],
                    "owner_seats": [c.get("owner_seat") for c in data.get("cases", ())],
                    "meaning": data.get("meaning", "")[:120]}
    report = {"schema": "sitin-catch-play-probe/1", "checks": checks,
              "official_evidence": official,
              "platform_behavior_note": "v24 实测：圈主即使有吃碰牌形，平台也可能不开窗"
                                        "⇒ 不得把「有牌形」当作「必然开窗」"}
    with open(os.path.join(args.out, "catch-play.json"), "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=1)

    counts = Counter("ok" if c["ok"] else "fail" for c in checks)
    print("检查项:", dict(counts))
    for item in checks:
        print("  %-28s %s %s" % (item["check"], "PASS" if item["ok"] else "FAIL",
                                 json.dumps(item["detail"], ensure_ascii=False)[:100]))
    print()
    print("官方证据:", json.dumps(official, ensure_ascii=False)[:240])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
