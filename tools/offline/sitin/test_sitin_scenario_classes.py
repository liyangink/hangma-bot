"""坐隐 3.0 场景类清单自测：**清单必须与指南/源码一致，四态判定必须能失败**。

三条纪律：

1. **清单不是散文**：每条官方依据都指向指南行号与标记、每个谓词字段都指向源码符号与字段；
   `--check` 与下面的测试共用同一实现，依据漂移或字段改名必须让测试红。
2. **四态判定必须能失败**：`unknown` 不得填零、`not_applicable` 不得当成"机制稀有"、
   逐类账不得合并；用构造面板把每种情形都钉成回归。
3. **类外零增量核对必须能失败**：用**故意违反声明**的构造记录证明它拦得住，
   再用真实触发集证明当前候选没有越界改选。

触发集是**构造集**：本测试只证明接线、判定与账目口径，不构成任何效果证据。
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

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

_HERE = Path(__file__).resolve().parent
_REPO = _PROJECT_ROOT
sys.path.insert(0, str(_project_file(_PROJECT_ROOT, _REPO / "src")))
sys.path.insert(0, str(_HERE))

from hangma_bot.hangma.interface import (  # noqa: E402
    CandidateFactKind,
    CandidateFacts,
    RuleCandidate,
    RuleCompleteness,
)
from hangma_bot.kernel.actions import (  # noqa: E402
    Discard,
    Gang,
    GangKind,
    Hu,
    Pass,
    Tile,
    action_key,
)
from hangma_bot.policy.evaluation_v1 import EvaluationContext  # noqa: E402
from hangma_bot.policy.heuristics.four_component_path_value import (  # noqa: E402
    meld_count_of,
)

_spec = importlib.util.spec_from_file_location(
    "sitin_scenario_classes", _project_file(_PROJECT_ROOT, _HERE / "sitin_scenario_classes.py"))
sc = importlib.util.module_from_spec(_spec)
sys.modules["sitin_scenario_classes"] = sc
assert _spec.loader is not None
_spec.loader.exec_module(sc)

WEALTH = "白"
#: 13 张自然暗牌（无副露形态）：meld_count_of 判定为 0 副露。
HAND13 = ("1w", "2w", "3w", "5w", "6w", "7w", "2t", "3t", "4t", "8b", "8b", "9b", "9b")
#: 10 张暗牌（一副露形态）。
HAND10 = ("1w", "2w", "3w", "5w", "6w", "7w", "2t", "3t", "4t", "8b")

#: **冻结口径**：类 id 列表改名即失败（id 冻结后为他包引用口径）。
FROZEN_CLASS_IDS = (
    "branch.chiitoi_live", "branch.luxury_locked", "branch.closer_seven_pairs",
    "chain.open", "chain.gang_step", "chain.gang_draw_open", "chain.piao_discard",
    "chain.break_discard", "chain.claim_repiao_circle",
    "four_white.at_four", "four_white.derivable_held4", "four_white.unknown_piao",
    "baotou.active", "baotou.discard_recheck", "baotou.meld_inherit",
    "baotou.decline_win_for_piao",
    "overlay.four_white_baotou", "overlay.chiitoi_baotou", "overlay.gang_piao_mix",
    "overlay.plain_branch_max", "overlay.global_max",
    "payrole.self_dealer", "payrole.self_nondealer",
    "meld.claim_window", "meld.waiting_facts_available",
    "gate.you_cai_bi_kao", "gate.wall_end_gang_ban", "gate.catch_play_owner",
)

TRIGGER_GRID = (_project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/2.3-gates/trigger/trigger-grid.jsonl'))


def _ctx(**overrides) -> EvaluationContext:
    """构造评分上下文；默认值 = 无副露 / 链 0 / 非爆头 / 手留 0 张财神 / 飘出未知。"""

    base = dict(
        combined_codes=tuple(HAND13), wealth_code=WEALTH, safe_codes=frozenset(),
        my_seat=0, next_seat=1, next_seat_meld_codes=(), dealer_seat=0,
        dealer_meld_codes=(), table_rank=1, catch_play=False,
        chain_count=0, baotou=False, wealth_count=0, chain_piao=None)
    base.update(overrides)
    return EvaluationContext(**base)


def _facts(**overrides):
    """构造候选事实（默认：完整、行牌、普通型向听 1、七对向听 2）。"""

    base = dict(fact_kind=CandidateFactKind.HAND_PROGRESS,
                completeness=RuleCompleteness.COMPLETE,
                shanten_after=1, useful_tiles=(),
                standard_shanten_after=1, seven_pairs_shanten_after=2,
                standard_useful_tiles=(), seven_pairs_useful_tiles=(),
                replacement_draw_unknown=False)
    base.update(overrides)
    return CandidateFacts(**base)


def _cand(action, facts=None, key=None):
    """真实 @@RuleCandidate@@（谓词会调用生产函数，必须是可消费的事实对象）。"""

    return RuleCandidate(action=action, action_key=key or action_key(action),
                         evidence=(), facts=facts)


def _record(window, in_class, undecided, candidates):
    """构造逐窗口记录（与 evaluate_panel 的记录同形）。"""

    return {"window": window, "in_class": list(in_class), "undecided": list(undecided),
            "per_candidate": candidates}


def _panel(*records):
    return {"records": list(records),
            "panel": {"rows_total": len(records), "scored": len(records),
                      "reconciles": True},
            "panel_facts": {}}


def _per_candidate(changed_windows, candidates=("alpha", "beta")):
    """构造 per_candidate 字典：changed_windows 里的窗口标记为改选。"""

    return {name: {"fired": name in changed_windows, "changed": name in changed_windows}
            for name in candidates}


def _declarations(names, declared_ids=()):
    """构造声明表（合成候选名不在注册表里，必须显式注入）。"""

    declared = set(declared_ids)
    return {name: {"candidate": name, "declared_scope": [], "classes": {
        cid: {"declared": cid in declared, "scope_hit": [], "token_hit": []}
        for cid in sc.CLASS_IDS}} for name in names}


# --- 1. 清单与源码 / 指南一致 -------------------------------------------------

def test_static_check_passes():
    """★ 全部静态核对（指南行 + 源码符号 + 关系 + 结算现算）必须零失败。"""

    assert sc.check() == []


def test_class_ids_are_frozen():
    """类 id 是**引用口径**：改名必须让测试红。"""

    assert tuple(sc.CLASS_IDS) == FROZEN_CLASS_IDS
    assert len(set(sc.CLASS_IDS)) == len(FROZEN_CLASS_IDS)


def test_official_basis_points_at_guide_lines():
    """每条官方依据都必须落在指南真实行上，且该行含声明的标记。"""

    guide = _project_file(_PROJECT_ROOT, _REPO / sc.GUIDE)
    lines = guide.read_text(encoding="utf-8").splitlines()
    checked = 0
    for item in sc.CLASSES:
        for basis in item["official"]:
            assert basis["file"] == sc.GUIDE
            assert 1 <= basis["line"] <= len(lines), (item["id"], basis["line"])
            assert basis["marker"] in lines[basis["line"] - 1], (item["id"], basis)
            checked += 1
    assert checked >= 30


def test_predicate_fields_exist_on_source_symbols():
    """每个可判定谓词字段都必须真实存在（字段改名即失败）。"""

    import dataclasses

    checked = 0
    for item in sc.CLASSES:
        for entry in item["fields"]:
            symbol = sc.resolve(entry["symbol"])
            assert dataclasses.is_dataclass(symbol), entry
            names = {field.name for field in dataclasses.fields(symbol)}
            assert entry["field"] in names, (item["id"], entry)
            checked += 1
    assert checked >= 20


def test_every_class_has_predicate_and_relations_are_consistent():
    """每个类都有谓词；关系目标存在、mutex 对称、implies 无环。"""

    assert sc.check_class_structure() == []
    assert sc.check_relations() == []


#: 门控事实的接线状态（**跨包依赖**：由 3.6d 把三个字段接进 EvaluationContext）。
GATE_WIRING = sc.gate_wiring_status()
GATE_FACTS_WIRED = GATE_WIRING["all_wired"]


def _with_gate_facts(ctx: EvaluationContext, **extra) -> EvaluationContext:
    """按当前接线状态补上门控字段（未接线的字段不传，避免自造不存在的字段）。"""

    import dataclasses

    known = {field.name for field in dataclasses.fields(EvaluationContext)}
    return dataclasses.replace(ctx, **{k: v for k, v in extra.items() if k in known})


def test_gate_classes_are_wired_and_decidable():
    """★ 3.6b 修订：三个门控类不再标不可判定；接线契约、谓词字段与强制点齐备。"""

    for class_id, wired in sc.GATE_FACT_WIRING.items():
        item = next(entry for entry in sc.CLASSES if entry["id"] == class_id)
        assert item.get("undecidable") is None, class_id
        declared = {(entry["symbol"], entry["field"]) for entry in item["fields"]}
        assert (wired["symbol"], wired["field"]) in declared, class_id
        assert item.get("rule_enforcement"), class_id
        for entry in item["rule_enforcement"]:
            assert sc.resolve(entry["symbol"]) is not None
    # 契约表与运行时读取点必须同源：字段在 ⇒ 可判定；不在 ⇒ 不可判定（不填零）。
    for entry in GATE_WIRING["classes"]:
        assert entry["wired_to_context"] is (entry["field"] in sc.context_field_names())


def test_gate_wiring_check_has_the_inverted_polarity():
    """★ --check 极性反转：接线未落地 ⇒ gate_wiring_missing；落地 ⇒ 该条消失。

    未接线时这条**预期红**（跨包时序依赖）：红的是"事实还没接进上下文"这件事本身，
    不是清单写错；也**不得**为了变绿把三个类改回不可判定。
    """

    failures = sc.check_gate_wiring()
    missing = {item["class_id"] for item in failures if item["kind"] == "gate_wiring_missing"}
    if GATE_FACTS_WIRED:
        assert missing == set(), failures
    else:
        assert missing == set(sc.GATE_FACT_WIRING), (
            "接线未落地时必须以 gate_wiring_missing 逐类报出（预期红，见交付报告 unresolved）")
    assert not [item for item in failures if item["kind"] == "gate_still_undecidable"]
    assert not [item for item in failures if item["kind"] == "gate_rule_enforcement_missing"]


@pytest.mark.skipif(not GATE_FACTS_WIRED,
                    reason="跨包时序依赖：3.6d 尚未把三个门控事实接进 EvaluationContext"
                           "（本清单已按目标态实现；接线落地后本用例自动转绿）")
def test_gate_facts_are_really_in_the_scoring_context():
    """目标态断言：三个门控字段必须**真的**在评分上下文里（不是文档承诺）。"""

    for entry in GATE_WIRING["classes"]:
        assert entry["field"] in sc.context_field_names(), entry


def test_pay_role_coefficients_are_recomputed_from_settlement():
    """支付角色系数必须由 settlement **现算**得到（不抄数字）。"""

    from hangma_bot.hangma.settlement import settle_scores

    seen = set()
    for row in sc.PAY_ROLE_COMBOS:
        seen.add((row["self_role"], row["winner_role"]))
        self_seat = 0
        dealer_seat = 0 if row["self_role"] == "dealer" else 1
        winner = {"self": self_seat, "dealer": dealer_seat}.get(row["winner_role"])
        if winner is None:
            winner = next(seat for seat in range(4)
                          if seat != self_seat and seat != dealer_seat)
        fan, base = 6, 3
        vector = settle_scores(fan, base, winner, dealer_seat)
        assert vector[self_seat] / float(base * fan) == row["coefficient"]
    assert seen == {(role, winner)
                    for role in ("dealer", "nondealer")
                    for winner in ("self", "dealer", "other_nondealer")}


def test_weight_policy_has_no_per_class_weights():
    """**不得按场景类拍权重**：清单里不存在任何权重类字段。"""

    assert sc.check_weight_fields() == []
    assert sc.WEIGHT_POLICY["verdict"].startswith("不得按场景类拍权重")
    for forbidden in ("weight", "weights", "score"):
        for item in sc.CLASSES:
            assert forbidden not in item


def test_known_gaps_are_cited_with_file_and_line():
    """已知缺口（庄闲缺席 / 风险不缩放）必须有据可查：文件 + 行 + 标记。"""

    gaps = {item["id"]: item for item in sc.KNOWN_GAPS}
    assert set(gaps) == {"gap.payrole_absent_in_scoring_layer",
                         "gap.risk_not_scaled_by_fan_or_pay_multiplier"}
    for item in sc.KNOWN_GAPS:
        assert item["citations"]
        for citation in item["citations"]:
            text = sc._source_line(citation["file"], citation["line"])
            assert text is not None
            assert citation["marker"] in text
    payrole_gap = gaps["gap.payrole_absent_in_scoring_layer"]
    assert "兑现概率层" in payrole_gap["precondition"]
    # 「顺序反了是空操作」这条判据必须写在缺口条目里（可逐字复核）
    joined = " ".join(str(payrole_gap.get(key, "")) for key in
                      ("precondition", "current_state", "why_not_a_parameter_problem"))
    assert "空操作" in joined
    assert payrole_gap["measured_facts"]["samples"] == 27824


def test_frozen_risk_cells_are_dealer_agnostic():
    """冻结风险表仍为庄闲通用价（与缺口清单的陈述一致）。"""

    assert sc.check_risk_cells() == []


def test_min_windows_matches_gate_threshold():
    """类覆盖下限与门禁触发面下限同值（同一份证据下限口径）。"""

    assert sc.MIN_CLASS_WINDOWS == sc._tool("sitin_gates").G2_MIN_FIRED_WINDOWS


# --- 2. 四态判定（含 unknown 不填零） -----------------------------------------

def test_verdict_thresholds():
    """四态阈值与优先级。"""

    assert sc.class_verdict(8, 0) == "sufficient"
    assert sc.class_verdict(20, 3) == "sufficient"
    assert sc.class_verdict(7, 0) == "insufficient"
    assert sc.class_verdict(1, 5) == "insufficient"      # 有窗口优先于不可判定
    assert sc.class_verdict(0, 3) == "unknown"
    assert sc.class_verdict(0, 0) == "not_applicable"


def test_unknown_is_not_zero_and_not_not_applicable():
    """★ unknown 不得填零、不得并入 not_applicable；其读法必须写明。"""

    records = [_record("w1", [], ["four_white.at_four"], _per_candidate(())),
               _record("w2", [], ["four_white.at_four"], _per_candidate(())),
               _record("w3", [], ["four_white.at_four"], _per_candidate(()))]
    aggregate = sc.aggregate_records(records, ["alpha"])
    bucket = aggregate["classes"]["four_white.at_four"]
    assert bucket["windows_in_class"] == 0
    assert bucket["windows_undecided"] == 3
    assert bucket["windows_out_of_class"] == 0
    assert sc.class_verdict(bucket["windows_in_class"],
                            bucket["windows_undecided"]) == "unknown"
    assert "不得填零" in sc.verdict_note("unknown")


def test_undecidable_predicate_returns_none_not_false():
    """链内飘出未知时，四白等值条件必须判为 None（不是 False）。"""

    ctx = _ctx(chain_count=1, chain_piao=None, wealth_count=1)
    classes = sc.classify_window(ctx, [])
    assert classes["four_white.at_four"] is None
    assert classes["four_white.unknown_piao"] is True
    assert classes["four_white.derivable_held4"] is False


def test_derivable_held_four_makes_four_white_decidable():
    """手留 4 张时飘出必为 0 ⇒ 四白条件可判定（不是 unknown）。"""

    ctx = _ctx(chain_count=1, chain_piao=None, wealth_count=4)
    classes = sc.classify_window(ctx, [])
    assert classes["four_white.derivable_held4"] is True
    assert classes["four_white.unknown_piao"] is False
    assert classes["four_white.at_four"] is True


def test_classify_window_supports_multi_membership():
    """一个位点可以同时属于多个类（官方明文叠加），逐类各记一笔。"""

    ctx = _ctx(baotou=True, chain_count=3, chain_piao=3, wealth_count=1)
    discard = _cand(Discard(Tile(WEALTH)))
    hu = _cand(Hu())
    classes = sc.classify_window(ctx, [discard, hu])
    assert classes["chain.piao_discard"] is True
    assert classes["baotou.active"] is True
    assert classes["baotou.decline_win_for_piao"] is True
    assert classes["chain.claim_repiao_circle"] is False     # 不在抓打圈
    assert sum(1 for value in classes.values() if value) >= 5


def test_gate_predicates_follow_the_wiring_state():
    """门控谓词三态：未接线的字段 ⇒ None（不填零）；接线后 ⇒ 按事实给出 True/False。"""

    ctx = _with_gate_facts(_ctx(), you_cai_bi_kao=True, remaining_tile_count=0,
                           catch_play_owner_seat=0)
    classes = sc.classify_window(ctx, [])
    if GATE_FACTS_WIRED:
        assert classes["gate.you_cai_bi_kao"] is True          # 开关打开
        assert classes["gate.wall_end_gang_ban"] is True       # 0 <= WALL_RESERVE_TILES
        assert classes["gate.catch_play_owner"] is False       # 不在圈内 ⇒ 可判定为不成立
    else:
        assert classes["gate.you_cai_bi_kao"] is None
        assert classes["gate.wall_end_gang_ban"] is None
        assert classes["gate.catch_play_owner"] is False, (
            "不在圈内是可判定的规则事实：接线未落地也不该是 None")
    # 边界值：0 张与"未知(None)"必须分开（未知不填零）。
    unknown_wall = sc.classify_window(_with_gate_facts(_ctx(), remaining_tile_count=None), [])
    assert unknown_wall["gate.wall_end_gang_ban"] is None
    # 圈内但圈主身份未知 ⇒ None；圈主是本人 ⇒ True。
    owner_unknown = sc.classify_window(
        _with_gate_facts(_ctx(catch_play=True), catch_play_owner_seat=None), [])
    assert owner_unknown["gate.catch_play_owner"] is None
    owner_self = sc.classify_window(
        _with_gate_facts(_ctx(catch_play=True, my_seat=2), catch_play_owner_seat=2), [])
    assert owner_self["gate.catch_play_owner"] is (True if GATE_FACTS_WIRED else False or None)


def test_closer_seven_pairs_needs_reference_candidate():
    """纯弃牌窗口没有手牌不变的参考候选 ⇒ 本类不可判定（不猜）。"""

    discard = _cand(Discard(Tile("9b")), _facts())
    assert sc.classify_window(_ctx(), [discard])["branch.closer_seven_pairs"] is None
    reference = _cand(Pass(), _facts(standard_shanten_after=2, seven_pairs_shanten_after=1))
    assert sc.classify_window(_ctx(), [discard, reference])["branch.closer_seven_pairs"] is True


def test_chiitoi_path_closed_by_meld_count():
    """副露数由暗牌张数反推：10 张 ⇒ 1 副露 ⇒ 七对路径已关闭。"""

    assert meld_count_of(tuple(HAND13)) == 0
    assert meld_count_of(tuple(HAND10)) == 1
    classes = sc.classify_window(_ctx(combined_codes=tuple(HAND10)), [])
    assert classes["branch.chiitoi_live"] is False


def test_gang_draw_open_requires_complete_facts():
    """有杠候选但事实不完整 ⇒ 不可判定（不得当成杠前没听）。"""

    gang = _cand(Gang(Tile("1w"), GangKind.CONCEALED), _facts(shanten_after=0))
    assert sc.classify_window(_ctx(), [gang])["chain.gang_draw_open"] is True
    degraded = _cand(Gang(Tile("1w"), GangKind.CONCEALED),
                     _facts(completeness=RuleCompleteness.DEGRADED, shanten_after=None))
    assert sc.classify_window(_ctx(), [degraded])["chain.gang_draw_open"] is None
    assert sc.classify_window(_ctx(), [])["chain.gang_draw_open"] is False


def test_candidate_class_status_vocabulary():
    """候选 × 类的证据状态取值固定；无声明一律 undeclared。"""

    assert sc.candidate_class_status(False, 12, 5, 3) == "undeclared"
    assert sc.candidate_class_status(True, 0, 0, 0) == "no_window"
    assert sc.candidate_class_status(True, 12, 0, 0) == "no_fire"
    assert sc.candidate_class_status(True, 12, 4, 0) == "fired_no_change"
    assert sc.candidate_class_status(True, 12, 4, 2) == "changed"


# --- 3. 逐类不可合并 ---------------------------------------------------------

def test_ledger_does_not_merge_classes_into_a_single_total():
    """★ 逐类账不得合并成单一总分：汇总只有计数，并标注不得作为准入依据。"""

    records = [
        _record("w1", ["chain.open"], [], _per_candidate(())),
        _record("w2", ["chain.open"], [], _per_candidate(())),
        _record("w3", [], ["four_white.at_four"], _per_candidate(())),
        _record("w4", ["baotou.active"], [], _per_candidate(())),
    ]
    evaluation = _panel(*records)
    data = sc.coverage_ledger({"path": "synthetic"}, evaluation, ["alpha"],
                              _declarations(["alpha"], ["chain.open"]))
    summary = data["summary"]
    assert summary["not_admission_basis"] is True
    assert "不得作为准入依据" in summary["note"]
    assert sum(summary["verdict_counts"].values()) == len(sc.CLASS_IDS)
    for key in summary:
        assert key not in ("score", "total", "aggregate", "rank", "weighted")
        assert not key.endswith("_score")
    verdicts = {entry["id"]: entry["verdict"] for entry in data["classes"]}
    assert verdicts["chain.open"] == "insufficient"      # 2 个窗口 < 下限
    assert verdicts["four_white.at_four"] == "unknown"   # 一个都判不出且有不可判定
    assert verdicts["baotou.active"] == "insufficient"
    assert verdicts["payrole.self_dealer"] == "not_applicable"
    assert len(set(verdicts.values())) >= 3


def test_aggregate_counts_undecided_separately_from_out_of_class():
    """不可判定窗口必须单列，不得混进类外计数。"""

    records = [_record("w1", ["chain.open"], ["branch.luxury_locked"], _per_candidate(())),
               _record("w2", [], [], _per_candidate(()))]
    aggregate = sc.aggregate_records(records, ["alpha"])
    luxury = aggregate["classes"]["branch.luxury_locked"]
    assert luxury["windows_undecided"] == 1
    assert luxury["windows_out_of_class"] == 1
    assert luxury["windows_in_class"] == 0


# --- 4. 类外零增量判定（含负例） ----------------------------------------------

def test_class_scope_violation_detects_out_of_class_change():
    """★ 负例：改选落在**已声明类之外** ⇒ 必须报违规（这条检查能失败）。"""

    records = [_record("w1", ["chain.open"], [], _per_candidate(("alpha",))),
               _record("w2", [], ["chain.open"], _per_candidate(("alpha",)))]
    result = sc.class_scope_violations(records, "alpha", ["baotou.active"])
    assert len(result["violations"]) == 2
    assert result["undecided_changes"] == []
    assert result["violations"][0]["window"] == "w1"


def test_class_scope_violation_passes_when_change_is_in_class():
    """正例：改选落在已声明类内 ⇒ 零违规。"""

    records = [_record("w1", ["chain.open"], [], _per_candidate(("alpha",)))]
    result = sc.class_scope_violations(records, "alpha", ["chain.open"])
    assert result["violations"] == []
    assert result["undecided_changes"] == []


def test_class_scope_violation_separates_undecided_from_violation():
    """已声明类不可判定时的改选归入归属未知，不能算违规也不能算合规。"""

    records = [_record("w1", [], ["chain.open"], _per_candidate(("alpha",)))]
    result = sc.class_scope_violations(records, "alpha", ["chain.open"])
    assert result["violations"] == []
    assert len(result["undecided_changes"]) == 1


def test_delta_outside_declared_classes_is_zero_on_trigger_set():
    """真实触发集上：六个静态注册候选的改选必须落在各自已声明类内。"""

    if not TRIGGER_GRID.is_file():
        pytest.skip("触发集缺失：{0}".format(TRIGGER_GRID))
    rows = sc.load_rows(TRIGGER_GRID)
    names = sc._registry().candidate_names()
    evaluation = sc.evaluate_panel(rows, names)
    assert evaluation["panel"]["reconciles"] is True
    for name in names:
        declared = sc.declared_class_ids(name)
        result = sc.class_scope_violations(evaluation["records"], name, declared)
        assert result["violations"] == [], (name, result["violations"][:2])


def test_trigger_set_coverage_end_to_end():
    """端到端：触发集上逐类出账必须可复算；门控类**已接线 ⇒ 可判定**（不再是 unknown）。"""

    if not TRIGGER_GRID.is_file():
        pytest.skip("触发集缺失")
    rows = sc.load_rows(TRIGGER_GRID)
    names = sc._registry().candidate_names()
    evaluation = sc.evaluate_panel(rows, names)
    data = sc.coverage_ledger({"path": str(TRIGGER_GRID)}, evaluation, names)
    verdicts = {entry["id"]: entry["verdict"] for entry in data["classes"]}
    assert data["gate_wiring"]["all_wired"] is True, "3.6b 目标态：三个门控事实已接线"
    classes = {entry["id"]: entry for entry in data["classes"]}
    for cid in ("gate.you_cai_bi_kao", "gate.wall_end_gang_ban", "gate.catch_play_owner"):
        # 3.6b 修订：接线后这三类不再因"事实缺失"落 unknown；四态由面板上的窗口数决定。
        assert verdicts[cid] in ("sufficient", "insufficient", "not_applicable"), verdicts[cid]
        assert classes[cid]["windows_undecided"] == 0, cid
    assert verdicts["chain.open"] == "sufficient"
    assert data["panel"]["scored"] == len(rows)
    chain = next(entry for entry in data["classes"] if entry["id"] == "chain.open")
    expected = sum(1 for record in evaluation["records"] if "chain.open" in record["in_class"])
    assert chain["windows_in_class"] == expected


def test_emit_catalog_is_json_serialisable_and_complete():
    """机读产物必须可序列化、含全部类与支付组合、且带边界声明。"""

    data = sc.catalog()
    text = json.dumps(data, ensure_ascii=False)
    assert json.loads(text)["schema"] == sc.SCHEMA
    assert len(data["classes"]) == len(FROZEN_CLASS_IDS)
    assert len(data["pay_role_combos"]) == 6
    assert data["counts"]["citations"] >= 30
    assert any("构造集" in item for item in data["boundaries"])
    assert data["weight_policy"]["verdict"]
    for item in data["classes"]:
        assert item["official"] or item["level"] != sc.LEVEL_OFFICIAL


def test_markdown_renderers_are_stable():
    """人读渲染与 JSON 同源：类 id、边界与权重纪律都必须出现。"""

    catalog_md = sc.render_catalog_markdown(sc.catalog())
    for cid in ("chain.claim_repiao_circle", "payrole.self_dealer", "gate.catch_play_owner"):
        assert cid in catalog_md
    assert "不得按场景类拍权重" in catalog_md
    coverage_md = sc.render_coverage_markdown({
        "input": {"path": "x", "constructed": True, "evidence_kind": "trigger"},
        "panel": {"rows_total": 1, "scored": 1, "reconciles": True},
        "panel_facts": {}, "min_class_windows": 8,
        "classes": [{"id": "chain.open", "verdict": "insufficient", "windows_in_class": 1,
                     "windows_undecided": 0, "windows_out_of_class": 0,
                     "candidates": {"alpha": {"fired_windows": 1, "changed_windows": 0,
                                              "status": "fired_no_change"}}}],
        "out_of_class_increment": {"alpha": {"declared_classes": [], "changed_windows": 0,
                                             "violation_total": 0,
                                             "undecided_change_total": 0}},
        "gaps": [], "boundaries": list(sc.BOUNDARIES),
        "summary": {"verdict_counts": {"insufficient": 1}},
    })
    assert "逐类覆盖" in coverage_md
    assert "不得作为准入依据" in coverage_md


def test_conflicting_evidence_kind_is_rejected():
    """构造集不得标为 admission 证据（拒绝而不是静默降级）。"""

    if not TRIGGER_GRID.is_file():
        pytest.skip("触发集缺失")
    code = sc.main(["--coverage", "--input", str(TRIGGER_GRID),
                    "--evidence-kind", "admission", "--limit", "1"])
    assert code == 2

# --- 5. 效果层 / 预算层（**不得与覆盖判定互相污染**） --------------------------

def _effect_panel():
    """构造效果层面板：两类有窗口（一类零改选、一类有改选）+ 一类不可判定。"""

    records = [
        _record("w1", ["branch.chiitoi_live", "chain.open"], [],
                _per_candidate(())),
        _record("w2", ["branch.chiitoi_live", "chain.open"], [],
                _per_candidate(("alpha",))),
        _record("w3", ["branch.chiitoi_live"], [], _per_candidate(())),
        _record("w4", ["branch.chiitoi_live", "baotou.active"], [],
                _per_candidate(())),
        _record("w5", [], ["four_white.at_four"], _per_candidate(())),
    ]
    return _panel(*records)


def test_effect_layer_cannot_feed_coverage():
    """★ 代码层保证：覆盖账**不接受**效果层数据作参数（分列、分标题、互不污染）。"""

    import inspect

    parameters = set(inspect.signature(sc.coverage_ledger).parameters)
    assert not any("effect" in name for name in parameters)
    data = sc.coverage_ledger({"path": "synthetic"}, _effect_panel(), ["alpha"],
                              _declarations(["alpha"], ["chain.open"]))
    for key in data:
        assert "effect" not in key
    assert "出现率" not in json.dumps(data["summary"], ensure_ascii=False)
    assert "不得回改" in sc.EFFECT_LAYER_PURPOSE
    assert "覆盖判定" in sc.EFFECT_LAYER_PURPOSE


def test_effect_layer_appearance_rate_arithmetic():
    """出现率的分子分母必须与逐窗口记录一致（可复算）。"""

    evaluation = _effect_panel()
    data = sc.effect_layer({"path": "synthetic"}, evaluation, ["alpha"])
    total = len(evaluation["records"])
    assert data["panel"]["scored"] == total
    by_id = {entry["class_id"]: entry for entry in data["per_class"]}
    chain = by_id["chain.open"]
    assert chain["numerator"] == 2
    assert chain["denominator"] == total
    assert chain["rate"] == 2 / float(total)
    unknown = by_id["four_white.at_four"]
    assert unknown["numerator"] == 0
    assert unknown["undecided"] == 1
    assert unknown["rate"] == 0.0


def test_effect_layer_information_prejudgement_is_recomputable():
    """信息量预判必须来自实际改选数：零改选的类是无差别类，有改选的类才可分辨。"""

    data = sc.effect_layer({"path": "synthetic"}, _effect_panel(), ["alpha"])
    info = data["information_prejudgement"]
    assert "chain.open" in info["discriminating_classes"]
    assert "baotou.active" in info["indifferent_classes"]
    assert "chain.open" not in info["indifferent_classes"]
    assert "改选数是否全为 0" in info["basis"]


def test_effect_layer_plain_games_and_conclusion():
    """普通局统计与用途结论必须齐全，且写明"不得当作机制稀有"。"""

    data = sc.effect_layer({"path": "synthetic"}, _effect_panel(), ["alpha"])
    patterns = {tuple(row["active_components"]): row for row in data["active_component_patterns"]}
    assert patterns[("branch",)]["windows"] == 1      # 只有分支活跃的普通局（w3）
    assert patterns[("branch", "chain")]["windows"] == 2
    assert patterns[("branch", "baotou")]["windows"] == 1
    assert data["plain_games"]["windows"] == 1
    assert data["plain_games"]["share"] == 1 / 5.0
    assert data["plain_games"]["denominator"] == 5
    conclusion = data["conclusion"]
    assert "普通局可以评强度" in conclusion["plain_vs_special"]
    assert len(conclusion["conditional_evaluation"]) == 4
    assert "机制稀有" in conclusion["not_rareness"]
    assert "不得回改" in data["hard_constraint"]


def test_effect_layer_rejects_constructed_panel():
    """构造触发集不得用来算出现率（它不是分布抽样）。"""

    if not TRIGGER_GRID.is_file():
        pytest.skip("触发集缺失")
    code = sc.main(["--effect-layer", "--input", str(TRIGGER_GRID), "--limit", "2"])
    assert code == 2


def test_effect_layer_markdown_marks_purpose():
    """人读效果层报告必须在标题里写明用途，避免被当成覆盖判定。"""

    text = sc.render_effect_layer_markdown(
        sc.effect_layer({"path": "synthetic"}, _effect_panel(), ["alpha"]))
    assert "效果层 / 预算层" in text
    assert "不是**覆盖判定" in text or "不是" in text
    assert "普通局" in text
    assert "条件化评估" in text


def test_class_matrix_reports_undeclared_explicitly():
    """矩阵必须显式标 undeclared，且单元格与覆盖账同源。"""

    data = sc.coverage_ledger({"path": "synthetic"}, _effect_panel(), ["alpha"],
                              _declarations(["alpha"], ["chain.open"]))
    matrix = sc.class_matrix(data)
    assert matrix["class_ids"] == list(sc.CLASS_IDS)
    row = matrix["candidates"][0]
    assert row["candidate"] == "alpha"
    assert row["cells"]["chain.open"]["declared"] is True
    assert row["cells"]["chain.open"]["status"] in (
        "no_fire", "fired_no_change", "changed", "no_window")
    assert row["cells"]["baotou.active"]["declared"] is False
    assert row["undeclared_classes"] == len(sc.CLASS_IDS) - 1
    text = sc.render_matrix_markdown(matrix)
    assert "undeclared" in text
    assert "分量—场景类矩阵" in text
    assert "只描述现状与缺口" in text


def test_panel_diagnostics_reports_raw_layer_without_filtering():
    """原始覆盖诊断只读观察：链状态 / 飘出可判定性 / 抓打圈都必须原样计数。"""

    if not TRIGGER_GRID.is_file():
        pytest.skip("触发集缺失")
    rows = sc.load_rows(TRIGGER_GRID)
    diag = sc.panel_diagnostics(rows)
    assert diag["raw_windows"] == len(rows)
    assert diag["undecodable"] == 0
    # 触发集的 8 个规则状态里有 6 个 chain_count >= 1（3 骨架 × 2 位点 × 6 状态）
    assert diag["raw_chain_count_nonzero"] == 36
    assert diag["raw_chain_piao_known"] + diag["raw_chain_piao_undecidable"] <= len(rows)
    # 触发集骨架全部取自非抓打圈窗口
    assert diag["raw_catch_play_true"] == 0
    assert "只统计原始观察" in diag["note"]


# --- 6. 核对本身必须能失败（负例） --------------------------------------------

def test_check_detects_citation_drift():
    """负例：依据漂移（标记对不上 / 行号越界）必须被核对拦下。"""

    basis = dict(sc.CLASSES[0]["official"][0])
    drifted = dict(basis, marker="这一行绝对不存在这个标记")
    failures = sc.check_citations([drifted], "synthetic")
    assert failures and failures[0]["kind"] == "citation"
    assert not sc.check_citations([basis], "synthetic")
    out_of_range = dict(basis, line=10 ** 6)
    assert sc.check_citations([out_of_range], "synthetic")


def test_check_detects_field_rename(monkeypatch):
    """负例：谓词字段改名必须让符号核对失败。"""

    broken = {"id": "synthetic", "fields": [
        {"symbol": sc.SYM_CONTEXT, "field": "no_such_field", "note": ""}]}
    monkeypatch.setattr(sc, "CLASSES", (broken,))
    failures = sc.check_predicate_symbols()
    assert any(item["kind"] == "field" for item in failures)
    missing_symbol = {"id": "synthetic", "fields": [
        {"symbol": "no.such.module:Thing", "field": "x", "note": ""}]}
    monkeypatch.setattr(sc, "CLASSES", (missing_symbol,))
    assert any(item["kind"] == "symbol" for item in sc.check_predicate_symbols())


def test_check_detects_relation_drift(monkeypatch):
    """负例：关系目标不存在 / mutex 不对称必须失败。"""

    broken = {"id": "a", "relations": [{"target": "nope", "kind": "mutex", "note": ""}]}
    monkeypatch.setattr(sc, "CLASSES", (broken,))
    assert any(item["kind"] == "relation_target" for item in sc.check_relations())
    asymmetric = {"id": "a", "relations": [{"target": "b", "kind": "mutex", "note": ""}]}
    other = {"id": "b", "relations": []}
    monkeypatch.setattr(sc, "CLASSES", (asymmetric, other))
    assert any(item["kind"] == "mutex_asymmetry" for item in sc.check_relations())


def test_main_exits_nonzero_when_check_fails(monkeypatch):
    """`--check` 失败必须返回非零（本包把它当准入门槛用）。"""

    basis = dict(sc.CLASSES[0]["official"][0], marker="这一行绝对不存在这个标记")
    broken = dict(sc.CLASSES[0], official=(basis,))
    monkeypatch.setattr(sc, "CLASSES", (broken,) + tuple(sc.CLASSES[1:]))
    assert sc.main(["--check"]) == 2

