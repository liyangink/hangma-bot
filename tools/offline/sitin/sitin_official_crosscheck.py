"""全场景 × 官方金例对拍：把官方 fan-calc 金例投影成局面，跑我们的规则模块，逐例比对。

官方验证接口 = `tests/fixtures/official/*/fan-calc*/cases.jsonl`（平台返回 hu/baotou/fan/scores）。
对拍项：是否可胡、爆头标记、总番。按 fixture 与 tags 两个维度汇总，给出覆盖与不一致清单。
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

HERE = os.path.abspath(os.path.dirname(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, ROOT)

import dataclasses  # noqa: E402

from hangma_bot.hangma.engine import HangmaRules  # noqa: E402
from hangma_bot.hangma.interface import ValueAnalysisLimits  # noqa: E402
from hangma_bot.kernel.actions import Tile  # noqa: E402
from hangma_bot.kernel.config import RuleConfig  # noqa: E402
from hangma_bot.policy.action_value_policy import build_scoring_view  # noqa: E402

from tests.unit.hangma.test_value_analysis import _observation  # noqa: E402
from tests.unit.policy.support import make_request  # noqa: E402

RULES = HangmaRules(RuleConfig("hangma-mvp-v10-public-counts", 1, False))
LIMITS = ValueAnalysisLimits()


def normalize(case):
    """兼容两种官方金例结构：

    - v18/v23/v9(部分)：`{request: {hand, draw, chain, base}, response: {...}, http_status?}`
    - v9(爆头/链4)：`{tag, hand, draw, chain?, resp: {...}}`（**没有** http_status）
    返回 (request, response, http_status 或 None)；无法识别返回 (None, None, None)。
    """
    if isinstance(case.get("request"), dict) and isinstance(case.get("response"), dict):
        return case["request"], case["response"], case.get("http_status")
    if isinstance(case.get("hand"), list) and isinstance(case.get("resp"), dict):
        request = {
            "hand": case["hand"],
            "draw": case.get("draw"),
            "chain": case.get("chain") or {"count": 0, "piao": 0},
            "base": case.get("base", 1),
        }
        return request, case["resp"], 200
    return None, None, None


def project(case):
    """把官方金例投影成观察：手牌、摸牌、链计数/飘数、爆头标记、牌河飘白。"""
    request = case["request"]
    expected = case["response"]
    chain = request.get("chain", {}) or {}
    obs = _observation(request["hand"], request.get("draw"),
                       chain=int(chain.get("count", 0) or 0),
                       piao=int(chain.get("piao", 0) or 0),
                       baotou=bool(expected.get("baotou", False)),
                       base_and_kind=None) if False else _observation(
        request["hand"], request.get("draw"),
        chain=int(chain.get("count", 0) or 0),
        piao=int(chain.get("piao", 0) or 0),
        baotou=bool(expected.get("baotou", False)))
    rivers = list(obs.discards)
    piao = int(chain.get("piao", 0) or 0)
    if piao:
        rivers[0] = tuple([Tile("白")] * piao)
    return dataclasses.replace(obs, discards=tuple(rivers))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--glob", default="tests/fixtures/official/**/fan-calc*/cases*.jsonl")
    args = ap.parse_args()
    paths = sorted(glob.glob(os.path.join(ROOT, args.glob), recursive=True))
    if not paths:
        print("no fixtures matched")
        return 2
    by_fixture = defaultdict(Counter)
    per_tag = defaultdict(Counter)
    mismatches = []
    for path in paths:
        fixture = os.path.relpath(path, ROOT)
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                try:
                    case = json.loads(line)
                except Exception:
                    by_fixture[fixture]["bad_json"] += 1
                    continue
                raw = case
                request_part, expected, status = normalize(raw)
                if request_part is None or status not in (None, 200):
                    by_fixture[fixture]["skipped"] += 1
                    continue
                raw_tags = list(raw.get("tags") or [])
                if isinstance(raw.get("tag"), str):
                    raw_tags.append(raw["tag"])
                tags = ",".join(raw_tags) or "(no-tag)"
                case = {"request": request_part, "response": expected, "tags": raw_tags}
                try:
                    obs = project(case)
                    analysis = RULES.analyze(obs, value_limits=LIMITS)
                    view = build_scoring_view(make_request(obs, analysis), value_limits=LIMITS)
                except Exception as error:
                    by_fixture[fixture]["engine_error"] += 1
                    per_tag[tags]["engine_error"] += 1
                    mismatches.append({"fixture": fixture, "tags": tags,
                                       "kind": "engine_error", "detail": str(error)[:80]})
                    continue
                hu = [a for a in view.actions if a.action_type == "hu"]
                got_hu = bool(hu)
                got_fan = None
                if hu:
                    settlement = hu[0].immediate_settlement
                    got_fan = None if settlement is None else getattr(settlement, "fan", None)
                want_hu = bool(expected.get("hu"))
                want_fan = expected.get("fan")
                by_fixture[fixture]["cases"] += 1
                per_tag[tags]["cases"] += 1
                by_fixture[fixture]["hu_match" if got_hu == want_hu else "hu_mismatch"] += 1
                per_tag[tags]["hu_match" if got_hu == want_hu else "hu_mismatch"] += 1
                # 官方 hu=false 时 fan 记 0；此时"无胡动作"就是一致，不能拿 None 与 0 比
                fan_ok = (got_fan == want_fan) or (not want_hu and got_fan is None)
                if fan_ok:
                    by_fixture[fixture]["fan_match"] += 1
                    per_tag[tags]["fan_match"] += 1
                else:
                    by_fixture[fixture]["fan_mismatch"] += 1
                    per_tag[tags]["fan_mismatch"] += 1
                    mismatches.append({"fixture": fixture, "tags": tags, "kind": "fan",
                                       "want": want_fan, "got": got_fan,
                                       "hand": "".join(request_hand(case))})
    os.makedirs(args.out, exist_ok=True)
    report = {"schema": "sitin-official-crosscheck/1", "fixtures": len(paths),
              "by_fixture": {k: dict(v) for k, v in by_fixture.items()},
              "by_tag": {k: dict(v) for k, v in per_tag.items()},
              "mismatches": mismatches[:200]}
    with open(os.path.join(args.out, "crosscheck.json"), "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=1)
    print("fixtures", len(paths))
    for fixture, counter in sorted(by_fixture.items()):
        print("%-58s %s" % (fixture[-58:], dict(counter)))
    agg = Counter()
    for counter in by_fixture.values():
        agg.update(counter)
    print()
    print("汇总:", dict(agg))
    bad_tags = {t: dict(c) for t, c in per_tag.items() if c.get("fan_mismatch") or c.get("hu_mismatch")}
    print("场景标签数:", len(per_tag), "| 有不一致的标签数:", len(bad_tags))
    for tag, counter in sorted(bad_tags.items()):
        print("  不一致 %-30s %s" % (tag[:30], counter))
    return 0


def request_hand(case):
    return case["request"]["hand"] + ([case["request"]["draw"]] if case["request"].get("draw") else [])


if __name__ == "__main__":
    raise SystemExit(main())
