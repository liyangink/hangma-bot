"""用唯一规则公开入口核对既有三对弃牌的条件后继；不模拟他家或改动策略。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution'

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
from dataclasses import asdict, replace
from time import perf_counter

import nonprogress_quality_probe as previous
import confirmation_execution_identity as guard
import sitin_natural_panel as natural
from hangma_bot.hangma.engine import HangmaRules
from hangma_bot.hangma.public_tile_counts import count_public_tiles
from hangma_bot.kernel.actions import CANONICAL_TILE_ORDER, Discard, Tile
from hangma_bot.kernel.config import RuleConfig
from hangma_bot.kernel.observation import PublicDiscard

b = previous.b
OUT = b.HERE / "followup-rule-probe-20260920"


def prepare():
    """冻结全部已计算条件分支；零模型、零新牌山、零策略效果预算。"""
    assert not OUT.exists(), "禁止覆盖旧探查"
    old = b.read(previous.OUT / "manifest.json")
    guard.verify(old["runtime"])
    assert b.read(previous.OUT / "summary.json")["status"] == "COMPLETE_MATH_DIAGNOSTIC_ONLY"
    versions = natural.stage.contract_versions_block(b.read(b.ROUTE / "contracts/group-dev-v1.json"))
    dependencies = [previous.OUT / name for name in ("manifest.json", "summary.json", "case-1.json", "case-2.json", "case-3.json")]
    dependencies.append(b.ROUTE / "contracts/group-dev-v1.json")
    OUT.mkdir()
    b.write(OUT / "manifest.json", {
        "schema": "followup-public-rule-probe/1", "created_at_utc": b.search.utc_now(),
        "cases": old["cases"], "input_digests": {str(p): b.digest(p.read_bytes()) for p in dependencies},
        "rule_config": {k: versions[k] for k in ("ruleset_version", "base_score", "you_cai_bi_kao")},
        "runtime": guard.capture(source_paths=[b.Path(__file__), b.Path(previous.__file__), b.Path(previous.previous.__file__)]),
        "max_rule_calls": 204, "max_process_seconds": 120,
        "model_calls": 0, "effect_tables": 0, "confirmation_roots": 0, "release_eligible": False,
        "scope": "沿用三对弃牌全部正未见枚数牌种，调用HangmaRules.analyze；只比较合法弃牌集合、向听及未见有效枚数，记录其他动作而不评价它们",
        "hypothesis": "首次普通弃牌后本人再次普通摸牌，暂时冻结其他公开牌与副露；自身牌河加首次弃牌，牌墙减一，链零且非抓打圈。不是完整可达的轮转轨迹，未声称他家没有行动或未来就如此发生",
        "synthetic_fields": "新快照水位为旧消费水位+2，只作条件夹具锚点；旧历史保留但history_complete=False，不伪造官方事件或调用confirmed_action恢复入口",
        "units": "支持为公开未见有效枚数；perf_counter单调时钟耗时单位秒，不代表赛事最大并发时延",
    })
    print("frozen: same 3 pairs, all prior hypothetical draws, public rule qualification only", flush=True)


def hypothetical_observation(request, full, first, draw):
    """构造明确标记为局部假设的条件观察；只允许本批无财神、无链、非抓打圈输入。"""
    obs = request.observation
    assert obs.phase == "draw" and obs.turn_seat == obs.seat and obs.drawn_tile is not None
    assert not obs.rule_state.catch_play and obs.rule_state.chain_count == 0 and not obs.rule_state.baotou
    assert all(t != obs.rule_state.wealth_god for t in full)
    assert obs.remaining_tile_count is not None and obs.remaining_tile_count > 21
    assert obs.hand_counts[obs.seat] == len(full)
    waiting = list(full)
    waiting.remove(Tile(first))
    rivers = list(obs.discards)
    rivers[obs.seat] = rivers[obs.seat] + (Tile(first),)
    seq = max(obs.snapshot_seq, obs.consumed_seq or 0)
    return replace(obs, my_hand=tuple(waiting), drawn_tile=Tile(draw), discards=tuple(rivers),
                   last_discard=PublicDiscard(obs.seat, Tile(first), seq + 1),
                   remaining_tile_count=obs.remaining_tile_count - 1, snapshot_seq=seq + 2,
                   consumed_seq=seq + 2, responding_seats=(), history_complete=False,
                   chain_piao=0, gang_draw=False)


def run():
    """逐分支保留差异，不因不一致删掉输入；全部完成后判定本次有限资格核验。"""
    plan = b.read(OUT / "manifest.json")
    guard.verify(plan["runtime"])
    for path, digest in plan["input_digests"].items():
        assert b.digest(b.Path(path).read_bytes()) == digest
    assert not (OUT / "started.json").exists(), "不得隐式重跑"
    b.write(OUT / "started.json", {"at_utc": b.search.utc_now()})
    rules = HangmaRules(RuleConfig(**plan["rule_config"]))
    started = perf_counter()
    reports = []
    calls = 0
    for index, case in enumerate(plan["cases"]):
        path = b.Path(case["input"])
        assert b.digest(path.read_bytes()) == case["record_sha256"]
        request, full, melds, unseen = previous.previous.material(b.read(path))
        old = b.read(previous.OUT / ("case-" + str(index + 1) + ".json"))
        results = []
        for variant in old["variants"]:
            first = variant["action"].split(":", 1)[1]
            for branch in variant["branches"]:
                calls += 1
                assert calls <= plan["max_rule_calls"]
                draw = branch["draw"]
                obs = hypothetical_observation(request, full, first, draw)
                expected_unseen = dict(unseen)
                expected_unseen[draw] -= 1
                known = Counter(t.code for t in obs.my_hand + (obs.drawn_tile,))
                public = count_public_tiles(obs)
                actual_unseen = {code: None if public[i] is None else max(0, 4 - known[code] - public[i])
                                 for i, code in enumerate(CANONICAL_TILE_ORDER)}
                before = perf_counter()
                analysis = rules.analyze(obs)
                elapsed = perf_counter() - before
                legal = [c for c in analysis.legal_candidates if isinstance(c.action, Discard)]
                actual = {c.action.tile.code: {
                    "shanten": c.facts.shanten_after if c.facts is not None else None,
                    "support": sum(t.remaining_estimate for t in c.facts.useful_tiles) if c.facts is not None else None,
                    "completeness": c.facts.completeness.value if c.facts is not None else None,
                } for c in legal}
                math = {c["discard"]: c for c in branch["all_math_discards"]}
                differences = [{"discard": code, "math": math[code], "rule": actual[code]}
                               for code in sorted(set(math) & set(actual))
                               if any(math[code][k] != actual[code][k] for k in ("shanten", "support"))]
                missing = sorted(set(math) - set(actual))
                extra = sorted(set(actual) - set(math))
                issues = [asdict(x) for x in analysis.issues]
                accepted = (actual_unseen == expected_unseen and not differences and not missing and not extra
                            and analysis.completeness.value == "complete" and not issues
                            and all(c["completeness"] == "complete" for c in actual.values()))
                results.append({"first_discard": first, "hypothetical_draw": draw, "unseen_copies": branch["unseen_copies"],
                    "conditional_only": True, "public_counts_match": actual_unseen == expected_unseen,
                    "actual_unseen": actual_unseen, "legal_discards": actual,
                    "math_discards_not_legal": missing, "legal_discards_not_in_math": extra,
                    "fact_differences": differences, "completeness": analysis.completeness.value, "issues": issues,
                    "other_legal_actions": [c.action_key for c in analysis.legal_candidates if not isinstance(c.action, Discard)],
                    "passed": accepted, "rule_elapsed_seconds": elapsed})
        report = {"index": index, "source": case["input"], "conditioned_windows": len(results),
                  "passed": sum(r["passed"] for r in results), "branches": results}
        b.write(OUT / ("case-" + str(index + 1) + ".json"), report)
        reports.append(report)
        print("case", index + 1, "passed", report["passed"], "/", len(results), flush=True)
    guard.verify(plan["runtime"])
    rows = [r for report in reports for r in report["branches"]]
    b.write(OUT / "summary.json", {
        "status": "PASS_CONDITIONAL_RULE_DIAGNOSTIC_ONLY" if all(r["passed"] for r in rows) else "MISMATCHES_REQUIRE_REVIEW",
        "conditioned_windows": calls, "passed": sum(r["passed"] for r in rows),
        "legal_discard_facts_compared": sum(len(r["legal_discards"]) for r in rows),
        "unseen_count_mismatches": sum(not r["public_counts_match"] for r in rows),
        "math_discards_not_legal": sum(len(r["math_discards_not_legal"]) for r in rows),
        "fact_differences": sum(len(r["fact_differences"]) for r in rows),
        "other_action_windows": sum(bool(r["other_legal_actions"]) for r in rows),
        "max_rule_elapsed_seconds": max(r["rule_elapsed_seconds"] for r in rows),
        "sum_rule_elapsed_seconds": sum(r["rule_elapsed_seconds"] for r in rows),
        "elapsed_seconds": perf_counter() - started,
        "model_calls": 0, "effect_tables": 0, "confirmation_roots": 0, "release_eligible": False,
        "limits": ["只核验冻结局部条件下的弃牌集合及牌效，不证明完整未来轨迹可达",
                   "未模拟他家介入、未来公开变化、牌墙概率或保留20张后的机会数量",
                   "其他合法动作只记录不排序，未声称弃牌续接是最佳未来策略",
                   "三对已见诊断输入，不是泛化、完整阶段效果或发布时延证据"],
    })


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("prepare", "run"))
    args = parser.parse_args()
    prepare() if args.operation == "prepare" else run()
