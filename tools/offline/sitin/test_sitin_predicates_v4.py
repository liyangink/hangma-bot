# -*- coding: utf-8 -*-
"""sitin_predicates_v4 的完整测试（v4 合同 §7.3 八个机器谓词）。

覆盖合同测试行要求的阈值 8/9、15/16、gap 1/2、未见数 0/1、缺 chain_piao、
合法弃白保持四白、分牌型 UNKNOWN 与胡/继续窗口，另加结构校验、三值语义与
确定性用例。全部为纯函数级 pytest 用例，不依赖仓库内其他模块。
"""

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

import copy
import json

import pytest

from sitin_predicates_v4 import (
    FAMILIES,
    FAMILY_PREDICATES,
    PREDICATE_IDS,
    evaluate_predicate,
    evaluate_predicates,
)


def make_branch(action_key, combined_shanten=1, progress=None, route_status="WITNESSED", support=None):
    """构造单个分支投影；progress/support 是对四个家族默认值的覆盖。"""
    base_progress = {family: "SAME" for family in FAMILIES}
    if progress:
        base_progress.update(progress)
    base_support = {family: 4 for family in FAMILIES}
    if support:
        base_support.update(support)
    return {
        "action_key": action_key,
        "combined_shanten": combined_shanten,
        "family_progress": base_progress,
        "route_status": route_status,
        "support_remaining": base_support,
    }


def make_facts(branches, wall_left=20):
    """构造规则事实投影；wall_left=None 表示墙余量未知。"""
    return {"wall_left": wall_left, "branches": branches}


def advancing_pair(
    family,
    wall_left=20,
    b_shanten=1,
    c_shanten=2,
    b_support=4,
    c_support=4,
    b_route_status="WITNESSED",
    c_route_status="WITNESSED",
):
    """构造“b 对 family 推进、c 原地”的最小可比分支对。

    P9c：取舍代价量 = Δsupp = b_support − c_support；b_shanten 是**决策相关性**门槛
    （PAIR_SHANTEN_MAX）的输入。
    """
    b = make_branch(
        "advance_route",
        combined_shanten=b_shanten,
        progress={family: "ADVANCE"},
        route_status=b_route_status,
        support={family: b_support},
    )
    c = make_branch(
        "plain_discard",
        combined_shanten=c_shanten,
        progress={family: "SAME"},
        route_status=c_route_status,
        support={family: c_support},
    )
    return make_facts([b, c], wall_left)


# ---------------------------------------------------------------------------
# 冻结常量与映射
# ---------------------------------------------------------------------------


def test_predicate_ids_and_mapping_frozen():
    """八个谓词 ID 与家族映射必须与 §7.3 冻结合同逐字一致。"""
    assert PREDICATE_IDS == (
        "branch_open",
        "branch_cost",
        "chain_open",
        "chain_cost",
        "four_white_open",
        "four_white_cost",
        "baotou_open",
        "baotou_cost",
    )
    assert set(FAMILY_PREDICATES) == set(FAMILIES)
    for family in FAMILIES:
        open_id, cost_id = FAMILY_PREDICATES[family]
        assert open_id == family + "_open"
        assert cost_id == family + "_cost"


def test_result_contains_exactly_eight_predicates():
    """主入口一次返回八个谓词，键集合与顺序同 PREDICATE_IDS。"""
    results = evaluate_predicates(advancing_pair("branch"))
    assert tuple(results) == PREDICATE_IDS


# ---------------------------------------------------------------------------
# 阈值边界：wall 15/16、7/8/9、gap 1/2、未见数 0/1
# ---------------------------------------------------------------------------


def test_open_true_at_wall_16():
    """wall_left=16 恰好满足 open 的墙余量阈值（>=16）。"""
    results = evaluate_predicates(advancing_pair("branch", wall_left=16))
    assert results["branch_open"]["value"] == "TRUE"
    assert results["branch_open"]["witness"] == {"b": "advance_route", "c": "plain_discard"}


def test_open_false_at_wall_15():
    """wall_left=15 差一枚不满足 open（15<16），且无缺失值，判 FALSE 而非 UNKNOWN。"""
    results = evaluate_predicates(advancing_pair("branch", wall_left=15))
    assert results["branch_open"]["value"] == "FALSE"
    assert results["branch_open"]["witness"] is None
    assert results["branch_open"]["missing"] is None


def test_cost_true_at_wall_15():
    """P9c 边界：wall_left=15 恰好满足 cost 的墙余量析取项（≤15，与 open 的 ≥16 互补）。"""
    results = evaluate_predicates(advancing_pair("branch", wall_left=15))
    assert results["branch_cost"]["value"] == "TRUE"
    assert results["branch_cost"]["witness"] == {"b": "advance_route", "c": "plain_discard"}


def test_cost_true_at_wall_2():
    """wall_left=2（实测下界附近）同样满足 cost 的墙余量析取项。"""
    results = evaluate_predicates(advancing_pair("branch", wall_left=2))
    assert results["branch_cost"]["value"] == "TRUE"


def test_cost_not_wall_derived_at_wall_16():
    """wall_left=16 不因墙满足 cost（16>15）；Δsupp=0 也不满足 Δ 析取项 ⇒ FALSE。

    合同测试行（§7.3）原写明墙阈值边界 8/9；P9c 起边界为 **15/16**（两侧互补），
    open 在 16 判 TRUE、cost 在 16 不因墙判 TRUE。旧值 8/9 作为历史留在文档修正块。
    """
    results = evaluate_predicates(advancing_pair("branch", wall_left=16))
    assert results["branch_cost"]["value"] == "FALSE"
    assert results["branch_cost"]["missing"] is None
    assert results["branch_open"]["value"] == "TRUE"


def test_support_delta_open_true_cost_false():
    """P9c 边界（上侧）：Δsupp = −16 恰好满足 open（≥−16），不满足 cost（>−17）。"""
    results = evaluate_predicates(
        advancing_pair("chain", b_support=4, c_support=20)
    )
    assert results["chain_open"]["value"] == "TRUE"
    assert results["chain_open"]["witness"] == {"b": "advance_route",
                                                "c": "plain_discard"}
    assert results["chain_cost"]["value"] == "FALSE"
    assert results["chain_cost"]["missing"] is None


def test_support_delta_cost_true_open_false():
    """P9c 边界（下侧）：Δsupp = −17 不满足 open（<−16），恰好满足 cost（≤−17）。"""
    results = evaluate_predicates(
        advancing_pair("chain", b_support=4, c_support=21)
    )
    assert results["chain_open"]["value"] == "FALSE"
    assert results["chain_open"]["missing"] is None
    assert results["chain_cost"]["value"] == "TRUE"
    assert results["chain_cost"]["witness"] == {"b": "advance_route",
                                                "c": "plain_discard"}


def test_support_delta_far_below_also_cost():
    """Δsupp 远低于下侧同样判 cost（下侧不设第二个边界）。"""
    results = evaluate_predicates(
        advancing_pair("chain", b_support=1, c_support=40)
    )
    assert results["chain_cost"]["value"] == "TRUE"
    assert results["chain_open"]["value"] == "FALSE"


def test_decision_relevance_gate_blocks_both_sides():
    """决策相关性门槛（P9c）：b 的动作后向听 > PAIR_SHANTEN_MAX(1) ⇒ 两侧都不成立。

    "关键进张耗尽/距离明显增大"这类取舍只在距成牌一步之内才有决策意义；实测这也正是
    两侧位置选择性的来源（开局首帧不可能满足）。
    """
    from sitin_predicates_v4 import PAIR_SHANTEN_MAX

    assert PAIR_SHANTEN_MAX == 1
    for shanten in (2, 3, 4):
        facts = advancing_pair("branch", b_shanten=shanten, b_support=1, c_support=40)
        results = evaluate_predicates(facts)
        assert results["branch_open"]["value"] == "FALSE", shanten
        assert results["branch_cost"]["value"] == "FALSE", shanten
        assert results["branch_cost"]["missing"] is None, shanten
    # 门槛内（≤1）同一批数值即成立 ⇒ 门槛是唯一的差别。
    ok = evaluate_predicates(advancing_pair("branch", b_shanten=1, b_support=1,
                                            c_support=40))
    assert ok["branch_cost"]["value"] == "TRUE"


def test_support_level_no_longer_a_threshold():
    """P9c：支持计数**水平**不再是阈值（旧 support>0 / ==0 在真实对上恒真/恒假）。

    b 的支持计数取 0 还是 1，只要 Δsupp 相同，两侧判定就相同——水平本身不再决定判定；
    水平差（Δsupp）才决定（这是"换量"的核心断言）。
    """
    for level in (0, 1, 4, 9):
        results = evaluate_predicates(
            advancing_pair("baotou", b_support=level, c_support=level))
        assert results["baotou_open"]["value"] == "TRUE", level
        assert results["baotou_cost"]["value"] == "FALSE", level
    # Δsupp 到 −17 时同一水平组合翻转成 cost ⇒ 决定判定的是**差**，不是水平。
    starved = evaluate_predicates(advancing_pair("baotou", b_support=0, c_support=17))
    assert starved["baotou_cost"]["value"] == "TRUE"
    assert starved["baotou_open"]["value"] == "FALSE"


# ---------------------------------------------------------------------------
# 结构条件：b SAME/c RETREAT、c CLOSE、route_status 门槛、action_key 约束
# ---------------------------------------------------------------------------


def test_b_same_with_c_retreat_forms_pair():
    """b=SAME 且 c=RETREAT 也构成满足对（合同判定第 1 条的第二种组合）。"""
    b = make_branch("keep_route", progress={"branch": "SAME"}, combined_shanten=1)
    c = make_branch("risky_gang", progress={"branch": "RETREAT"}, combined_shanten=2)
    results = evaluate_predicates(make_facts([b, c], wall_left=20))
    assert results["branch_open"]["value"] == "TRUE"
    assert results["branch_open"]["witness"] == {"b": "keep_route", "c": "risky_gang"}


def test_b_advance_with_c_close_forms_pair():
    """b=ADVANCE 且 c=CLOSE（开门使七对关闭一类）构成满足对。"""
    b = make_branch("open_route", progress={"branch": "ADVANCE"}, combined_shanten=1)
    c = make_branch("pair_close", progress={"branch": "CLOSE"}, combined_shanten=2)
    results = evaluate_predicates(make_facts([b, c], wall_left=20))
    assert results["branch_open"]["value"] == "TRUE"


def test_b_retreat_cannot_form_pair():
    """b=RETREAT/CLOSE 不能充当推进侧：两个非推进分支之间凑不成任何满足对。

    注意 SAME 反向可与 RETREAT 凑对（b=SAME、c=RETREAT 是合同允许的组合，
    见 test_b_same_with_c_retreat_forms_pair），故此处用 RETREAT+CLOSE 双非推进。
    """
    b = make_branch("worse_route", progress={"branch": "RETREAT"}, combined_shanten=1)
    c = make_branch("closed_route", progress={"branch": "CLOSE"}, combined_shanten=2)
    results = evaluate_predicates(make_facts([b, c], wall_left=20))
    assert results["branch_open"]["value"] == "FALSE"
    assert results["branch_cost"]["value"] == "FALSE"


def test_closed_proven_b_unusable():
    """route_status=CLOSED_PROVEN 的 b 被硬门槛排除：无满足对，FALSE 且无缺失。"""
    facts = advancing_pair("branch", b_route_status="CLOSED_PROVEN")
    results = evaluate_predicates(facts)
    assert results["branch_open"]["value"] == "FALSE"
    assert results["branch_open"]["missing"] is None
    assert results["branch_cost"]["value"] == "FALSE"


def test_unanalyzed_b_unusable():
    """route_status=UNANALYZED 的 b 同样不可用（合同只允许 WITNESSED/OPEN_UNCERTAIN）。"""
    facts = advancing_pair("branch", b_route_status="UNANALYZED")
    results = evaluate_predicates(facts)
    assert results["branch_open"]["value"] == "FALSE"
    assert results["branch_open"]["missing"] is None


def test_route_status_gate_positive_control_witnessed():
    """对照：同一局面把 b 换成 WITNESSED 即恢复 TRUE，证明翻转来自 route_status。"""
    facts = advancing_pair("branch", b_route_status="WITNESSED")
    assert evaluate_predicates(facts)["branch_open"]["value"] == "TRUE"


def test_same_action_key_pair_rejected():
    """两个分支 action_key 相同不能组成对：即使进展标签匹配也判 FALSE。"""
    x = make_branch("discard_5m", progress={"branch": "ADVANCE"}, combined_shanten=1)
    y = make_branch("discard_5m", progress={"branch": "SAME"}, combined_shanten=2)
    results = evaluate_predicates(make_facts([x, y], wall_left=20))
    assert results["branch_open"]["value"] == "FALSE"
    assert results["branch_open"]["missing"] is None
    assert results["branch_cost"]["value"] == "FALSE"


def test_distinct_action_key_pair_accepted():
    """加入不同 action_key 的第三分支后可配对，见证键使用互不相同的 action_key。"""
    x = make_branch("discard_5m", progress={"branch": "ADVANCE"}, combined_shanten=1)
    y = make_branch("discard_5m", progress={"branch": "SAME"}, combined_shanten=2)
    z = make_branch("pass", progress={"branch": "RETREAT"}, combined_shanten=2)
    results = evaluate_predicates(make_facts([x, y, z], wall_left=20))
    assert results["branch_open"]["value"] == "TRUE"
    assert results["branch_open"]["witness"] == {"b": "discard_5m", "c": "pass"}


def test_c_route_status_not_gated():
    """合同只约束 b 的 route_status；c 为 CLOSED_PROVEN 仍可作参照侧。"""
    facts = advancing_pair("branch", c_route_status="CLOSED_PROVEN")
    results = evaluate_predicates(facts)
    assert results["branch_open"]["value"] == "TRUE"
    assert results["branch_open"]["witness"] == {"b": "advance_route", "c": "plain_discard"}


# ---------------------------------------------------------------------------
# family_progress UNKNOWN（缺 chain_piao 类）与四白专场景
# ---------------------------------------------------------------------------


def test_unknown_progress_branch_not_used_as_b():
    """UNKNOWN 进展分支不能充当 b：存在完整满足对时结果仍 TRUE 且见证不含它。"""
    b = make_branch("chi_w", progress={"chain": "ADVANCE"}, combined_shanten=1)
    unknown = make_branch(
        "piao_chain", progress={"chain": "UNKNOWN"}, combined_shanten=0,
        support={"chain": 9},
    )
    c = make_branch("plain_discard", progress={"chain": "SAME"}, combined_shanten=2)
    results = evaluate_predicates(make_facts([b, unknown, c], wall_left=20))
    assert results["chain_open"]["value"] == "TRUE"
    assert results["chain_open"]["witness"] == {"b": "chi_w", "c": "plain_discard"}


def test_unknown_progress_may_flip_open_but_not_closed_cost():
    """UNKNOWN 进展可能改变 open 判定则 UNKNOWN；cost 数值已定死则照常 FALSE。

    缺 chain_piao 归因的分支（chain=UNKNOWN）若实为 ADVANCE，open 有可能为 TRUE，
    故 open 为 UNKNOWN 并单列原因。

    cost 侧（P9c：Δsupp 边界 −16/−17）：本例两分支的支持计数相等（Δsupp=0），
    且 wall=20>15 ⇒ 墙析取项与 Δsupp 析取项**在任何进展补全下**都不成立，
    cost 判 FALSE（判据未放宽）。

    对照（同一帧只把参照分支的支持计数抬高到 Δsupp=−17）：cost 变成 **UNKNOWN**
    而不是 TRUE/FALSE——因为"推进分支的进张比参照少 17 张"这一条能否成立，取决于那条
    UNKNOWN 进展的分支最终补全成什么（补成 RETREAT 则该对成立）⇒ 存在性分析判 UNKNOWN
    是**正确**的，这正是新量阈值落在观测域内部带来的可分辨性。
    """
    unknown = make_branch(
        "piao_chain", progress={"chain": "UNKNOWN"}, combined_shanten=1,
        support={"chain": 4},
    )
    c = make_branch("plain_discard", progress={"chain": "SAME"}, combined_shanten=1,
                    support={"chain": 4})
    results = evaluate_predicates(make_facts([unknown, c], wall_left=20))
    assert results["chain_open"]["value"] == "UNKNOWN"
    assert results["chain_open"]["witness"] is None
    missing = results["chain_open"]["missing"]
    assert missing and len(missing) == 1
    assert "piao_chain" in missing[0]
    assert "UNKNOWN" in missing[0]
    assert results["chain_cost"]["value"] == "FALSE"
    assert results["chain_cost"]["missing"] is None
    starved = make_branch(
        "piao_chain", progress={"chain": "UNKNOWN"}, combined_shanten=1,
        support={"chain": 4},
    )
    c_rich = make_branch("plain_discard", progress={"chain": "SAME"},
                         combined_shanten=1, support={"chain": 21})
    results_starved = evaluate_predicates(make_facts([starved, c_rich], wall_left=20))
    assert results_starved["chain_cost"]["value"] == "UNKNOWN"
    assert results_starved["chain_cost"]["missing"]


def test_four_white_advance_witness_with_open_uncertain_route():
    """合法弃白保持四白：弃白分支 four_white=ADVANCE，route_status=OPEN_UNCERTAIN。

    合同明确“不因单纯弃白就写 CLOSE”；OPEN_UNCERTAIN 的 b 不被证明关闭，可作见证。
    """
    discard_w = make_branch(
        "discard_w",
        progress={"four_white": "ADVANCE"},
        route_status="OPEN_UNCERTAIN",
        combined_shanten=1,
        support={"four_white": 3},
    )
    keep_w = make_branch(
        "keep_w", progress={"four_white": "RETREAT"}, combined_shanten=2
    )
    results = evaluate_predicates(make_facts([discard_w, keep_w], wall_left=18))
    assert results["four_white_open"]["value"] == "TRUE"
    assert results["four_white_open"]["witness"] == {"b": "discard_w", "c": "keep_w"}


# ---------------------------------------------------------------------------
# combined_shanten 为 null（分牌型不可比较）
# ---------------------------------------------------------------------------


def test_null_shanten_cannot_form_true_pair():
    """b 的动作后向听未知（shanten_state=unknown）时不能凑对判 TRUE，只能 UNKNOWN。

    P9c：向听仍是**决策相关性**门槛的输入（必须 ≤ PAIR_SHANTEN_MAX），因此"未知"
    依然进缺失分析；而 shanten_state=not_applicable（无等待态，如胡牌）是**确定不可比较**，
    不进缺失分析（P9 修复）。
    """
    b = make_branch(
        "tenhon_route", progress={"branch": "ADVANCE"}, combined_shanten=None
    )
    c = make_branch("safe_discard", progress={"branch": "SAME"}, combined_shanten=2)
    results = evaluate_predicates(make_facts([b, c], wall_left=20))
    assert results["branch_open"]["value"] == "UNKNOWN"
    assert results["branch_open"]["witness"] is None
    missing = results["branch_open"]["missing"]
    assert any("tenhon_route" in reason and "向听" in reason for reason in missing)
    # cost 侧：墙 20>15、Δsupp=0（两分支支持都为 4）⇒ 即便 b 的向听补全成 ≤1 也不成立，
    # 因此是**确定 FALSE**（存在性分析逐项检查结果，不是"未知就一律 UNKNOWN"）。
    assert results["branch_cost"]["value"] == "FALSE"
    assert results["branch_cost"]["missing"] is None
    # 对照：把 Δsupp 压到 −17 后，同一未知向听就能翻转 cost ⇒ UNKNOWN（且单列原因）。
    starved_b = make_branch("tenhon_route", progress={"branch": "ADVANCE"},
                            combined_shanten=None, support={"branch": 4})
    rich_c = make_branch("safe_discard", progress={"branch": "SAME"},
                         combined_shanten=2, support={"branch": 21})
    starved = evaluate_predicates(make_facts([starved_b, rich_c], wall_left=20))
    assert starved["branch_cost"]["value"] == "UNKNOWN"
    assert starved["branch_cost"]["missing"]


def test_null_shanten_branch_ignored_when_full_pair_exists():
    """另一分支对数据完整时照常 TRUE，null 向听分支只被跳过、不进见证。"""
    null_b = make_branch(
        "tenhon_route", progress={"branch": "ADVANCE"}, combined_shanten=None
    )
    good_b = make_branch("normal_route", progress={"branch": "ADVANCE"}, combined_shanten=1)
    c = make_branch("safe_discard", progress={"branch": "SAME"}, combined_shanten=2)
    results = evaluate_predicates(make_facts([good_b, null_b, c], wall_left=20))
    assert results["branch_open"]["value"] == "TRUE"
    assert results["branch_open"]["witness"] == {"b": "normal_route", "c": "safe_discard"}


def test_null_shanten_irrelevant_when_condition_already_decided():
    """缺失 gap 不可能改变判定时不触发 UNKNOWN：open 已因 wall=10 定死为 FALSE。

    cost 侧不同：gap 补全后仍可能 >=2，故 cost 保持 UNKNOWN——两方向独立判定。
    """
    b = make_branch(
        "tenhon_route", progress={"branch": "ADVANCE"}, combined_shanten=None
    )
    c = make_branch("safe_discard", progress={"branch": "SAME"}, combined_shanten=2)
    results = evaluate_predicates(make_facts([b, c], wall_left=10))
    assert results["branch_open"]["value"] == "FALSE"
    assert results["branch_open"]["missing"] is None
    assert results["branch_cost"]["value"] == "UNKNOWN"


# ---------------------------------------------------------------------------
# 缺失值与 UNKNOWN（wall_left 缺失、support 未知等）
# ---------------------------------------------------------------------------


def test_wall_missing_all_eight_unknown():
    """wall_left 缺失且存在可翻转的满足对时，八个谓词全部 UNKNOWN 并单列原因。"""
    b = make_branch(
        "advance_all",
        progress={family: "ADVANCE" for family in FAMILIES},
        combined_shanten=1,
    )
    c = make_branch(
        "plain_discard",
        progress={family: "SAME" for family in FAMILIES},
        combined_shanten=2,
    )
    facts = make_facts([b, c], wall_left=None)
    results = evaluate_predicates(facts)
    assert tuple(results) == PREDICATE_IDS
    for predicate_id in PREDICATE_IDS:
        assert results[predicate_id]["value"] == "UNKNOWN", predicate_id
        assert results[predicate_id]["witness"] is None
        assert "wall_left 缺失" in results[predicate_id]["missing"]


def test_wall_missing_without_any_pair_is_false():
    """无任何可配对分支时，wall 缺失也不可能改变判定，仍为 FALSE。"""
    only = make_branch("sole_action", progress={family: "ADVANCE" for family in FAMILIES})
    results = evaluate_predicates(make_facts([only], wall_left=None))
    for predicate_id in PREDICATE_IDS:
        assert results[predicate_id]["value"] == "FALSE"


def test_support_unknown_gives_unknown_with_reason():
    """b 的 support_remaining 未知时 open/cost 无法判定，UNKNOWN 并说明分支与家族。"""
    b = make_branch(
        "advance_route",
        progress={"chain": "ADVANCE"},
        support={"chain": None},
    )
    c = make_branch("plain_discard", progress={"chain": "SAME"}, combined_shanten=2)
    results = evaluate_predicates(make_facts([b, c], wall_left=20))
    assert results["chain_open"]["value"] == "UNKNOWN"
    assert results["chain_cost"]["value"] == "UNKNOWN"
    missing = results["chain_open"]["missing"]
    assert any("advance_route" in reason and "support_remaining" in reason for reason in missing)


# ---------------------------------------------------------------------------
# FALSE：全部已知但无满足对；TRUE 见证键
# ---------------------------------------------------------------------------


def test_all_known_no_satisfying_pair_false():
    """数据完整但两侧条件都不满足：wall=16（不因墙判 cost）且 Δsupp=0（不到下侧）。"""
    results = evaluate_predicates(advancing_pair("four_white", wall_left=16))
    assert results["four_white_open"]["value"] == "TRUE"          # 机会侧成立
    assert results["four_white_open"]["witness"] is not None
    assert results["four_white_cost"]["value"] == "FALSE"
    assert results["four_white_cost"]["missing"] is None
    # 反例：同一帧把 Δsupp 压到 −17 ⇒ 机会侧转 FALSE、代价侧转 TRUE（互补、不留空隙）。
    starved = evaluate_predicates(advancing_pair("four_white", wall_left=16,
                                                 b_support=4, c_support=21))
    assert starved["four_white_open"]["value"] == "FALSE"
    assert starved["four_white_cost"]["value"] == "TRUE"


def test_true_result_carries_witness_keys():
    """TRUE 结果附事实见证键，且 witness 恰含 b/c 两个键。"""
    results = evaluate_predicates(advancing_pair("baotou"))
    witness = results["baotou_open"]["witness"]
    assert set(witness) == {"b", "c"}
    assert witness["b"] == "advance_route"
    assert witness["c"] == "plain_discard"
    assert results["baotou_open"]["missing"] is None


# ---------------------------------------------------------------------------
# 胡窗口/继续窗口：无分支对可言
# ---------------------------------------------------------------------------


def test_single_action_all_false():
    """胡/继续窗口只有一个动作：无分支对可言，也没有缺失值，八谓词全 FALSE。"""
    only = make_branch(
        "sole_hu",
        progress={family: "ADVANCE" for family in FAMILIES},
        combined_shanten=1,
    )
    results = evaluate_predicates(make_facts([only], wall_left=20))
    for predicate_id in PREDICATE_IDS:
        assert results[predicate_id]["value"] == "FALSE"
        assert results[predicate_id]["witness"] is None
        assert results[predicate_id]["missing"] is None


def test_empty_branches_all_false():
    """分支列表为空：同属无分支对可言，八谓词全 FALSE。"""
    results = evaluate_predicates(make_facts([], wall_left=20))
    for predicate_id in PREDICATE_IDS:
        assert results[predicate_id]["value"] == "FALSE"


# ---------------------------------------------------------------------------
# 确定性与纯度
# ---------------------------------------------------------------------------


def test_deterministic_results_and_witness_order():
    """同输入两次调用结果全等（含键序与 missing 排序）；多候选时见证取稳定序首个。"""
    b1 = make_branch("b_one", progress={"branch": "ADVANCE"}, combined_shanten=1)
    b2 = make_branch("b_two", progress={"branch": "ADVANCE"}, combined_shanten=0)
    c = make_branch("c_zero", progress={"branch": "SAME"}, combined_shanten=2)
    facts = make_facts([c, b2, b1], wall_left=20)  # 乱序输入验证按 action_key 稳定排序
    first = evaluate_predicates(facts)
    second = evaluate_predicates(facts)
    assert first == second
    assert json.dumps(first, ensure_ascii=False) == json.dumps(second, ensure_ascii=False)
    assert first["branch_open"]["witness"] == {"b": "b_one", "c": "c_zero"}


def test_input_not_mutated():
    """纯函数：调用后 facts 深度不变。"""
    facts = advancing_pair("chain")
    snapshot = copy.deepcopy(facts)
    evaluate_predicates(facts)
    assert facts == snapshot


def test_extra_top_level_keys_ignored():
    """facts 顶层的其他投影字段一律忽略，不影响判定。"""
    facts = advancing_pair("branch")
    facts["source_root_id"] = "root-42"
    facts["legal"] = True
    assert evaluate_predicates(facts)["branch_open"]["value"] == "TRUE"


# ---------------------------------------------------------------------------
# 家族映射与单谓词入口
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("family", list(FAMILIES))
def test_all_families_open_true(family):
    """四个家族各自产出 family_open/family_cost 的正确映射与独立判定。"""
    facts = advancing_pair(family)
    results = evaluate_predicates(facts)
    assert results[family + "_open"]["value"] == "TRUE"
    assert results[family + "_cost"]["value"] == "FALSE"
    prefix = family + "_"
    other_ids = [pid for pid in PREDICATE_IDS if not pid.startswith(prefix)]
    for predicate_id in other_ids:
        assert results[predicate_id]["value"] == "FALSE", predicate_id


@pytest.mark.parametrize("predicate_id", list(PREDICATE_IDS))
def test_evaluate_predicate_matches_bulk(predicate_id):
    """单谓词入口与批量入口逐字段一致。"""
    b = make_branch(
        "advance_all",
        progress={family: "ADVANCE" for family in FAMILIES},
        combined_shanten=1,
    )
    c = make_branch(
        "plain_discard",
        progress={family: "SAME" for family in FAMILIES},
        combined_shanten=2,
    )
    facts = make_facts([b, c], wall_left=None)
    assert evaluate_predicate(facts, predicate_id) == evaluate_predicates(facts)[predicate_id]


def test_evaluate_predicate_rejects_unknown_id():
    """未知谓词 ID 抛 ValueError。"""
    facts = advancing_pair("branch")
    with pytest.raises(ValueError, match="predicate_id"):
        evaluate_predicate(facts, "branch_openness")


# ---------------------------------------------------------------------------
# 输入结构非法与字段缺省语义
# ---------------------------------------------------------------------------


def _valid_branch_dict():
    return make_branch("advance_route", progress={"branch": "ADVANCE"})


def test_valueerror_facts_not_dict():
    """facts 不是 dict，ValueError 指明 facts。"""
    with pytest.raises(ValueError, match="facts"):
        evaluate_predicates(["not", "a", "dict"])


def test_valueerror_missing_branches():
    """缺 branches 字段，ValueError。"""
    with pytest.raises(ValueError, match="branches"):
        evaluate_predicates({"wall_left": 20})


def test_valueerror_branches_not_list():
    """branches 不是 list，ValueError。"""
    with pytest.raises(ValueError, match="branches"):
        evaluate_predicates({"wall_left": 20, "branches": "x"})


def test_valueerror_branch_not_dict():
    """分支项不是 dict，ValueError 指明下标。"""
    with pytest.raises(ValueError, match=r"branches\[0\]"):
        evaluate_predicates({"wall_left": 20, "branches": ["x"]})


def test_valueerror_action_key_invalid():
    """action_key 缺失或非 str，ValueError。"""
    branch = _valid_branch_dict()
    del branch["action_key"]
    with pytest.raises(ValueError, match="action_key"):
        evaluate_predicates({"wall_left": 20, "branches": [branch]})
    bad = _valid_branch_dict()
    bad["action_key"] = 123
    with pytest.raises(ValueError, match="action_key"):
        evaluate_predicates({"wall_left": 20, "branches": [bad]})


@pytest.mark.parametrize(
    "label",
    ["BETTER", "advance", "", 3, None],
)
def test_valueerror_progress_bad_label(label):
    """family_progress 出现五个冻结标签之外的值，ValueError。"""
    branch = _valid_branch_dict()
    branch["family_progress"]["chain"] = label
    with pytest.raises(ValueError, match="family_progress"):
        evaluate_predicates({"wall_left": 20, "branches": [branch]})


def test_valueerror_progress_missing_family_key():
    """family_progress 缺某个家族键，ValueError。"""
    branch = _valid_branch_dict()
    del branch["family_progress"]["baotou"]
    with pytest.raises(ValueError, match="family_progress"):
        evaluate_predicates({"wall_left": 20, "branches": [branch]})


def test_valueerror_progress_extra_family_key():
    """family_progress 含封闭键集之外的键（如拼错的家族名），ValueError。"""
    branch = _valid_branch_dict()
    branch["family_progress"]["chain_piao"] = "ADVANCE"
    with pytest.raises(ValueError, match="family_progress"):
        evaluate_predicates({"wall_left": 20, "branches": [branch]})


def test_valueerror_progress_not_dict():
    """family_progress 不是 dict，ValueError。"""
    branch = _valid_branch_dict()
    branch["family_progress"] = ["ADVANCE"]
    with pytest.raises(ValueError, match="family_progress"):
        evaluate_predicates({"wall_left": 20, "branches": [branch]})


@pytest.mark.parametrize("bad_value", ["many", 2.5, True])
def test_valueerror_support_bad_type(bad_value):
    """support_remaining 值非 int（或为 bool/浮点/字符串），ValueError。"""
    branch = _valid_branch_dict()
    branch["support_remaining"]["four_white"] = bad_value
    with pytest.raises(ValueError, match="support_remaining"):
        evaluate_predicates({"wall_left": 20, "branches": [branch]})


def test_valueerror_support_negative():
    """support_remaining 为负枚数，ValueError。"""
    branch = _valid_branch_dict()
    branch["support_remaining"]["four_white"] = -1
    with pytest.raises(ValueError, match="support_remaining"):
        evaluate_predicates({"wall_left": 20, "branches": [branch]})


def test_valueerror_support_missing_family_key():
    """support_remaining 缺某个家族键，ValueError。"""
    branch = _valid_branch_dict()
    del branch["support_remaining"]["chain"]
    with pytest.raises(ValueError, match="support_remaining"):
        evaluate_predicates({"wall_left": 20, "branches": [branch]})


def test_valueerror_route_status_invalid():
    """route_status 非四个枚举之一，ValueError。"""
    branch = _valid_branch_dict()
    branch["route_status"] = "MAYBE"
    with pytest.raises(ValueError, match="route_status"):
        evaluate_predicates({"wall_left": 20, "branches": [branch]})


@pytest.mark.parametrize("bad_wall", ["20", True, -1])
def test_valueerror_wall_left_invalid(bad_wall):
    """wall_left 类型非法（str/bool/负数），ValueError。"""
    with pytest.raises(ValueError, match="wall_left"):
        evaluate_predicates({"wall_left": bad_wall, "branches": [_valid_branch_dict()]})


@pytest.mark.parametrize("bad_shanten", ["1", True])
def test_valueerror_combined_shanten_invalid(bad_shanten):
    """combined_shanten 非 int 且非 null，ValueError。"""
    branch = _valid_branch_dict()
    branch["combined_shanten"] = bad_shanten
    with pytest.raises(ValueError, match="combined_shanten"):
        evaluate_predicates({"wall_left": 20, "branches": [branch]})


def test_wall_left_absent_treated_as_missing():
    """wall_left 键缺省与 null 同义（未知），不抛 ValueError。"""
    facts = advancing_pair("branch")
    del facts["wall_left"]
    results = evaluate_predicates(facts)
    assert results["branch_open"]["value"] == "UNKNOWN"
    assert "wall_left 缺失" in results["branch_open"]["missing"]


def test_combined_shanten_absent_treated_as_null():
    """分支缺 combined_shanten 键与 null 同义（不可比较）。"""
    b = make_branch("tenhon_route", progress={"branch": "ADVANCE"})
    del b["combined_shanten"]
    c = make_branch("safe_discard", progress={"branch": "SAME"}, combined_shanten=2)
    results = evaluate_predicates(make_facts([b, c], wall_left=20))
    assert results["branch_open"]["value"] == "UNKNOWN"


def test_negative_shanten_accepted():
    """向听距离约定可为负（-1 表成胡一类），属合法输入，不抛 ValueError。"""
    b = make_branch(
        "won_route", progress={"branch": "ADVANCE"}, combined_shanten=-1
    )
    c = make_branch("plain_discard", progress={"branch": "SAME"}, combined_shanten=2)
    results = evaluate_predicates(make_facts([b, c], wall_left=20))
    assert results["branch_open"]["value"] == "TRUE"
