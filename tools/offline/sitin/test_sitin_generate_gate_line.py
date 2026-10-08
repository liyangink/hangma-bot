# -*- coding: utf-8 -*-
"""P10 · M4：门线 / 位次势差口径的手算金例（纯计算；不调用模型、不跑桌赛）。

复审 §5 M4 的实例：候选 docstring 写「本人可见积分到晋级门线（第 3 名分数线）的距离」，
公式却是升序 ``sorted(scores)[2]``——升序下标 2 是**第 2 名**。对四座积分
``(100, 80, 20, 0)``、焦点座位 2，该代码给出 −60，而所称「第 3 名距离」应为 0。

本文件把该实例连同领先 / 临界 / 落后 / 同分 / 四换座 / 结算后门线变动写成**手算金例**：
每条期望值都在注释里给出推导算式（升序下标 ↔ 名次映射是唯一依据）。

口径的唯一来源是 ``tools/sitin_generate.py`` 的门线小节：作者提示词从那里渲染，
本测试对**同一批函数**逐值核对——因此提示词、参考实现与金例不会各自漂移。

运行：

    .venv/bin/python -m pytest review/llm-guided-heuristic-route-2026-09-15/tools/test_sitin_generate_gate_line.py -q
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
import inspect
import itertools
import json
import sys
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))

import sitin_generate as gen  # noqa: E402

#: 复审实例用的四座积分（座位 0—3）。
S = (100.0, 80.0, 20.0, 0.0)

#: 冻结目标合同：晋级区大小与名次键链的唯一来源（只读，不修改）。
GROUP_CONTRACT = (gen.REPO / "review/llm-guided-heuristic-route-2026-09-15"
                  / "contracts" / "group-dev-v1.json")

#: 冻结候选（复审实例，只读；用于复现缺陷出处）。
FROZEN_CANDIDATE = (gen.REPO / "review/llm-guided-heuristic-route-2026-09-15"
                    / "evidence" / "v4-impl" / "r6-trial-runs" / "rep1" / "iter-01"
                    / "iterations" / "iter-01" / "generation" / "candidate.py")


def _gaps(scores, seat):
    """取两条门线势差；未知时断言失败（金例只有已知局面）。"""

    got = gen.gate_line_potentials(scores, seat)
    assert got is not None, (scores, seat)
    return got


def _permuted(values, perm):
    """按置换 perm 搬座位：结果[perm[i]] = values[i]（四换座用）。"""

    moved = [0.0, 0.0, 0.0, 0.0]
    for index in range(4):
        moved[perm[index]] = values[index]
    return tuple(moved)


# ============================================================ 1. 名次映射与合同同源


def test_order_statistic_mapping_comes_from_frozen_objective_contract():
    """升序下标 ↔ 名次必须与冻结目标合同一致：第 k 名分数 = 升序下标 (4−k)。

    目标合同 objective.advance_count = 2（晋级区 = 前 2），因此：
      晋级区末位 = 第 2 名 = 升序下标 2；区外头名 = 第 3 名 = 升序下标 1。
    复审缺陷正是把「第 3 名」贴到了下标 2 上（差一位）。
    """

    contract = json.loads(GROUP_CONTRACT.read_text(encoding="utf-8"))
    advance = contract["objective"]["advance_count"]
    assert advance == 2, "冻结合同变更则本文件的名次映射必须重算"

    indices = gen.gate_line_indices(advance)
    # 推导：升序排序后 a[0] 最小 = 第 4 名 …… a[3] 最大 = 第 1 名；
    #       第 k 名 → 下标 4−k → 第 2 名下 2、第 3 名下 1。
    assert indices == {"inside_line_index": 2, "outside_line_index": 1}

    # 判别力对照：升序下标 2 的数值就是第 2 名分数，绝不是第 3 名。
    ordered = sorted(S)
    assert ordered[2] == 80.0, "升序下标 2 = 第 2 名分数"
    assert ordered[1] == 20.0, "升序下标 1 = 第 3 名分数"


def test_review_instance_off_by_one_is_reproduced_on_frozen_candidate():
    """复审实例可复现：冻结候选把「第 3 名」贴到下标 2，真实第 3 名距离为 0。"""

    if not FROZEN_CANDIDATE.is_file():
        pytest.skip("冻结候选不存在（证据目录被移动）")
    spec = importlib.util.spec_from_file_location("frozen_rep1_01", FROZEN_CANDIDATE)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    # 手算：旧 cutline_of = s[seat] − sorted(s)[2] = 20 − 80 = −60（第 2 名距离）。
    assert module.cutline_of(S, 2)[0] == -60.0
    # 手算：所称「第 3 名」距离 = s[seat] − sorted(s)[1] = 20 − 20 = 0。
    assert S[2] - sorted(S)[1] == 0.0
    # 口径修正后：两条尺子分别给出 −60（追第 2 名）与 0（领先第 3 名），名实一致。
    gaps = _gaps(S, 2)
    assert gaps["inside_gap"] == -60.0 and gaps["outside_gap"] == 0.0
    assert gaps["inside_line"] == 80.0 and gaps["outside_line"] == 20.0


# ============================================================ 2. 六类手算金例


def test_leading_case():
    """领先：s=(100,80,20,0)，焦点座位 0（第 1 名）。

    升序 a=[0,20,80,100]：第 2 名 = a[2] = 80，第 3 名 = a[1] = 20。
    inside_gap  = s[0] − 80 = 100 − 80 = +20
    outside_gap = s[0] − 20 = 100 − 20 = +80
    """

    gaps = _gaps(S, 0)
    assert gaps["inside_line"] == 80.0 and gaps["outside_line"] == 20.0
    assert gaps["inside_gap"] == 20.0
    assert gaps["outside_gap"] == 80.0


def test_critical_tie_case():
    """临界（并列第 2）：s=(100,80,80,0)，焦点座位 1。

    升序 a=[0,80,80,100]：第 2 名 = a[2] = 80，第 3 名 = a[1] = 80（两个 80 并列）。
    inside_gap  = 80 − 80 = 0（临界：正好压在晋级区末位线上）
    outside_gap = 80 − 80 = 0
    名次区间：严格更高者 1 人（100）→ low=2；同块 2 人 → high=3；
    high=3 > advance_count=2 且 low=2 ≤ 2 → UNRESOLVED（座位 1 与座位 2 谁进前二未解决）。
    """

    gaps = _gaps((100.0, 80.0, 80.0, 0.0), 1)
    assert gaps["inside_gap"] == 0.0
    assert gaps["outside_gap"] == 0.0

    status = gen.gate_zone_status((100.0, 80.0, 80.0, 0.0), 1, 2)
    assert status == {"low": 2, "high": 3, "zone": "UNRESOLVED"}

    # 次级键（名次分）齐备时同一局面可以判定：座位 1 名次分 3 > 座位 2 名次分 1
    # → 座位 1 严格第 2（low=high=2 → IN），座位 2 严格第 3（low=high=3 > 2 → OUT）。
    keys = ((100.0, 3), (80.0, 3), (80.0, 1), (0.0, -3))
    assert gen.gate_zone_status(keys, 1, 2) == {"low": 2, "high": 2, "zone": "IN"}
    assert gen.gate_zone_status(keys, 2, 2) == {"low": 3, "high": 3, "zone": "OUT"}

    # 差一分未压线：s=(100,79,80,0)，焦点座位 1 → inside_gap = 79 − 80 = −1；
    # outside_gap = 79 − 79 = 0（升序 a=[0,79,80,100]，第 3 名 = 79 = 本人）。
    near = _gaps((100.0, 79.0, 80.0, 0.0), 1)
    assert near["inside_gap"] == -1.0
    assert near["outside_gap"] == 0.0


def test_behind_case():
    """落后：s=(100,80,20,0)，焦点座位 2 与座位 3（复审实例的两个落后座位）。

    座位 2：inside_gap = 20 − 80 = −60；outside_gap = 20 − 20 = 0
    座位 3：inside_gap =  0 − 80 = −80；outside_gap =  0 − 20 = −20
    名次区间：座位 2 严格更高者 2 人 → low=high=3 > 2 → OUT；
              座位 3 严格更高者 3 人 → low=high=4 > 2 → OUT。
    """

    seat2 = _gaps(S, 2)
    assert seat2["inside_gap"] == -60.0
    assert seat2["outside_gap"] == 0.0
    assert gen.gate_zone_status(S, 2, 2) == {"low": 3, "high": 3, "zone": "OUT"}

    seat3 = _gaps(S, 3)
    assert seat3["inside_gap"] == -80.0
    assert seat3["outside_gap"] == -20.0
    assert gen.gate_zone_status(S, 3, 2) == {"low": 4, "high": 4, "zone": "OUT"}


def test_tie_case_keeps_interval_and_never_fabricates_zero_or_rank():
    """同分：门线数值良定义，但「是否在区内」必须给区间，不得塌缩成确定名次。

    E1 s=(50,50,10,0)，焦点座位 0：升序 a=[0,10,50,50] → 第 2 名 = 50、第 3 名 = 10；
       inside_gap = 50 − 50 = 0；outside_gap = 50 − 10 = +40；
       区间：严格更高者 0 → low=1；同块 2 人 → high=2；high=2 ≤ 2 → IN。
    E2 s=(50,50,50,0)，焦点座位 0：严格更高者 0 → low=1；同块 3 人 → high=3；
       high=3 > 2 且 low=1 ≤ 2 → UNRESOLVED（三人在争两个席位）。
    E3 s=(100,90,80,80)，焦点座位 3：升序 a=[80,80,90,100] → 第 2 名 = 90、第 3 名 = 80；
       inside_gap = 80 − 90 = −10；outside_gap = 80 − 80 = 0；
       区间：严格更高者 2 → low=3；同块 2 人 → high=4；low=3 > 2 → OUT。
    """

    e1 = _gaps((50.0, 50.0, 10.0, 0.0), 0)
    assert (e1["inside_gap"], e1["outside_gap"]) == (0.0, 40.0)
    assert gen.gate_zone_status((50.0, 50.0, 10.0, 0.0), 0, 2) == {
        "low": 1, "high": 2, "zone": "IN"}

    assert gen.gate_zone_status((50.0, 50.0, 50.0, 0.0), 0, 2) == {
        "low": 1, "high": 3, "zone": "UNRESOLVED"}

    e3 = _gaps((100.0, 90.0, 80.0, 80.0), 3)
    assert (e3["inside_gap"], e3["outside_gap"]) == (-10.0, 0.0)
    assert gen.gate_zone_status((100.0, 90.0, 80.0, 80.0), 3, 2) == {
        "low": 3, "high": 4, "zone": "OUT"}

    # 0 只表示「已算出的相等」，与「未知」是两件事（未知一律 None，见下一节）。
    assert e1["inside_gap"] == 0.0


def test_seat_rotation_invariance():
    """四换座：置换只改座位标签，不改积分多重集合 → 两条门线势差不变。

    推导：sorted() 只依赖多重集合；置换 p 下 s'[p(i)] = s[i] 且焦点座位随迁
    → 门线数值 a[2]、a[1] 不变，本人分数 s[seat] 不变 → inside/outside gap 不变。
    """

    base = (100.0, 80.0, 20.0, 0.0)
    for seat in range(4):
        want = _gaps(base, seat)
        for perm in itertools.permutations(range(4)):
            assert _gaps(_permuted(base, perm), perm[seat]) == want, (perm, seat)

    # 同分局面同样随迁（并列块整体移动）。
    tie = (50.0, 50.0, 10.0, 0.0)
    want_tie = {"inside_line": 50.0, "outside_line": 10.0,
                "inside_gap": 0.0, "outside_gap": 40.0}
    for perm in itertools.permutations(range(4)):
        assert _gaps(_permuted(tie, perm), perm[0]) == want_tie, perm


# ============================================================ 3. 动作后门线势差


def test_post_settlement_line_movement_recompute_vs_approximation():
    """结算后门线变动：完整四座结算向量重算 ≠ 只加本人增量。

    G1 本人越过门线：s=(100,80,20,0)，座位 2，四座增量 (0,0,+70,0)
       → s' = (100,80,90,0)；升序 a'=[0,80,90,100] → 第 2 名' = 90；
       inside_gap' = 90 − 90 = 0；inside_gap = 20 − 80 = −60
       → Δinside_gap = 0 − (−60) = +60 ≠ 本人增量 +70（门线从 80 移到 90）。
       outside_gap' = 90 − 80 = +10；outside_gap = 20 − 20 = 0 → Δoutside_gap = +10。
    G2 只他家结算：四座增量 (0,−30,0,0) → s' = (100,50,20,0)；a'=[0,20,50,100]
       → 第 2 名' = 50 → inside_gap' = 20 − 50 = −30 → Δinside_gap = −30 − (−60) = +30；
       本人增量 = 0，但 Δinside_gap = +30 → 「只加本人增量」的近似看不到这一变化。
    G3 近似启发式对照：同一局面、本人增量 +70、门线固定在动作前取值 80
       → Δinside_gap = Δoutside_gap = +70（恒等于本人增量），门线未移动。
    """

    g1 = gen.gate_line_delta_recomputed(S, 2, (0.0, 0.0, 70.0, 0.0))
    assert g1 is not None
    assert g1["delta_inside"] == 60.0
    assert g1["delta_outside"] == 10.0
    assert g1["inside_line_moved"] is True and g1["outside_line_moved"] is True
    assert g1["delta_inside"] != 70.0, "重算下 ΔΦ ≠ 本人增量"

    g2 = gen.gate_line_delta_recomputed(S, 2, (0.0, -30.0, 0.0, 0.0))
    assert g2 is not None
    assert g2["delta_inside"] == 30.0
    assert g2["delta_outside"] == 0.0
    assert g2["inside_line_moved"] is True

    g3 = gen.gate_line_delta_frozen_line(S, 2, 70.0)
    assert g3 is not None
    assert g3["delta_inside"] == 70.0 and g3["delta_outside"] == 70.0
    assert g3["inside_line_moved"] is False and g3["outside_line_moved"] is False
    assert g3["delta_inside"] != g1["delta_inside"], "两种模式数值不同，不得混称"

    # 模式名与常量、提示词名表三处必须同源（不得各写一套字符串）。
    assert g1["mode"] == gen.GATE_LINE_MODE_RECOMPUTE
    assert g3["mode"] == gen.GATE_LINE_MODE_FROZEN
    names = gen.gate_line_semantics_block()["mode_names"]
    assert set(names) == {gen.GATE_LINE_MODE_RECOMPUTE, gen.GATE_LINE_MODE_FROZEN}
    assert names[gen.GATE_LINE_MODE_FROZEN].startswith("近似启发式")


def test_translation_invariance():
    """平移不变性：四座同加常数 c 不改变门线势差（对 c 的取值也一样）。

    推导：s + c·1⁴ 的升序向量就是 a + c·1⁴（次序不变）→ 门线数值各加 c，
    本人分数也加 c → 两个**差**不变。故「绝对积分水平」不是门线势差。
    注意：门线数值本身随 c 平移（−1000 时 inside_line = −920），这是对的；
    不变的必须是势差。
    """

    cases = [(S, 0), (S, 2), (S, 3), ((100.0, 80.0, 80.0, 0.0), 1),
             ((50.0, 50.0, 10.0, 0.0), 0)]
    for scores, seat in cases:
        want = _gaps(scores, seat)
        for shift in (-1000.0, -7.0, 0.0, 5.0, 1000.0):
            moved = tuple(value + shift for value in scores)
            got = _gaps(moved, seat)
            assert got["inside_gap"] == want["inside_gap"], (scores, seat, shift)
            assert got["outside_gap"] == want["outside_gap"], (scores, seat, shift)


# ============================================================ 4. 未知与适用域


def test_unknown_is_never_masqueraded_as_zero():
    """未知不得伪装成 0：缺失、长度错、布尔冒充、非有限、越界一律 None。

    对照：已知的相等返回 0.0（dict），未知返回 None——两者必须可区分，
    否则「不知道」会被当成「正好压线」送进下游势能。
    """

    for bad in (None, (100.0, 80.0, 20.0), (100.0, 80.0, 20.0, 0.0, 5.0),
                (100.0, 80.0, None, 0.0), (100.0, 80.0, True, 0.0),
                (100.0, 80.0, False, 0.0), (100.0, 80.0, float("nan"), 0.0),
                (100.0, 80.0, float("inf"), 0.0)):
        assert gen.gate_line_potentials(bad, 0) is None, bad
    for bad_seat in (None, True, False, -1, 4):
        assert gen.gate_line_potentials(S, bad_seat) is None, bad_seat
    # 已知的相等是 0.0，不是 None。
    assert _gaps((100.0, 80.0, 80.0, 0.0), 1)["inside_gap"] == 0.0

    # 结算向量重算：任一座增量未知 → 未知（不得当 0、不得当门线不变）。
    for bad_deltas in (None, (0.0, None, 70.0, 0.0), (0.0, 0.0, 70.0),
                       (0.0, 0.0, 70.0, 0.0, 1.0), (0.0, True, 70.0, 0.0),
                       (0.0, 0.0, float("nan"), 0.0)):
        assert gen.gate_line_delta_recomputed(S, 2, bad_deltas) is None, bad_deltas
    assert gen.gate_line_delta_frozen_line(S, 2, None) is None
    assert gen.gate_line_delta_frozen_line(S, 2, True) is None

    # 名次区间：基准未知 / 晋级区大小未知 → 未知，不猜名次。
    for bad_keys in (None, (100.0, 80.0, 20.0), (100.0, None, 20.0, 0.0)):
        assert gen.gate_zone_status(bad_keys, 0, 2) is None, bad_keys
    for bad_advance in (None, 0, 4, True):
        assert gen.gate_zone_status(S, 0, bad_advance) is None, bad_advance


def test_monotonicity_holds_only_inside_the_declared_domain():
    """单调性只在声明的适用域内成立，不得断言「向听更低就更好」。

    门线分项的声明域（门线数值固定）：inside_gap 关于本人积分单调不减。
    手算 s=(100,80,x,0)：
      第 2 名分数 = max(min(x,100), 80) → x≤80 时 80；80≤x≤100 时 x；x≥100 时 100
      ⇒ inside_gap = x−80 (x≤80) / 0 (80≤x≤100) / x−100 (x≥100)
      x = 0,20,79,80,81,100,120 → −80,−60,−1,0,0,0,20（非降）。
    本测试**不**对「向听更低就更好」下全局断言：大牌路线可能牺牲向听换番；
    该限定只在提示词里以受限形式声明（见下一条断言）。
    """

    xs = (0.0, 20.0, 79.0, 80.0, 81.0, 100.0, 120.0)
    want = (-80.0, -60.0, -1.0, 0.0, 0.0, 0.0, 20.0)
    got = tuple(_gaps((100.0, 80.0, x, 0.0), 2)["inside_gap"] for x in xs)
    assert got == want
    for before, after in zip(got, got[1:]):
        assert after >= before, "声明域内必须单调不减"

    # 近似模式：ΔΦ 恒等于本人增量（对 δ 单调），且不声称门线会移动。
    deltas = (-5.0, 0.0, 13.0, 70.0)
    frozen = tuple(gen.gate_line_delta_frozen_line(S, 2, d)["delta_inside"]
                   for d in deltas)
    assert frozen == deltas


# ============================================================ 5. 提示词口径同源


def _rendered_contract_text():
    payload = gen.render_action_value_task_contract(
        objective_summary="测试目标", panel_boundary="测试面板", prompt_role="I1")
    return payload, gen.render_action_value_contract_text(payload)


def test_prompt_declares_the_only_allowed_names_formulas_and_domain():
    """提示词必须写明唯一允许的定义、公式、命名与适用域（名实一致）。"""

    payload, text = _rendered_contract_text()
    # 1) 口径进合同身份（新语义即新提示词，不能悄悄沿用旧提示词哈希）。
    assert "gate_line_semantics" in payload

    # 2) 唯一映射与两个名字 + 公式都在。
    assert "升序下标" in text and "第 2 名" in text and "第 3 名" in text
    for name in ("inside_line", "outside_line", "recompute", "frozen_line"):
        assert name in text, name
    assert "近似启发式" in text and "完整结算向量重算" in text

    # 3) 禁止的命名必须显式写出来（不得留下名实不符表述）。
    for clause in gen.GATE_LINE_FORBIDDEN_NAMINGS:
        assert clause in text, clause
    # 名实不符的旧表述只允许出现在**禁止条款**（引用即禁止）里；
    # 任何陈述性位置出现都算名实不符，必须红。
    for stale in ("第 3 名门线", "第 3 名分数线", "第三名分数线"):
        for line in text.splitlines():
            if stale in line:
                assert "不得" in line, "名实不符表述出现在陈述位置：{0}".format(line)

    # 4) 参考实现与公式同源：提示词里出现的必须是同一份源码。
    assert inspect.getsource(gen.gate_line_potentials).strip() in text
    assert 'lines["second"]' in text and 'lines["third"]' in text

    # 5) 单调性只在声明域内：域限制必须写在提示词里（含「同一动作族」限定）。
    assert "同一动作族" in text
    assert "不得写成任何局面" in text

    # 6) 未知口径与识别区间必须在提示词里（不得伪装零）。
    assert "未知" in text and "识别区间" in text

    # 7) 真实生成路径（build_action_value_prompt 的 I1 与 M1）都必须带该口径块：
    #    只改 render_* 而没进 build_action_value_prompt 等于没改。
    parent = {"identity": "genloop|test", "candidate_id": "cand-test",
              "thought": "父代机制说明", "code": "def score_actions(view):\n    pass",
              "code_sha256": "0" * 64}
    for operator, extra in ((gen.OPERATOR_I1, {}), (gen.OPERATOR_M1, {"parent": parent})):
        packet = gen.build_action_value_prompt(operator, gen.render_action_value_task_contract(
            objective_summary="测试目标", panel_boundary="测试面板",
            prompt_role=operator, **extra))
        assert "门线" in packet.text, operator
        assert "inside_gap=-60" in packet.text, operator
        assert "gate_line_semantics" in json.dumps(packet.to_json(), ensure_ascii=False) \
            or packet.contract_identity, operator


def test_prompt_renders_hand_computed_golden_numbers():
    """提示词里的金例数字必须等于本文件手算的期望值（防提示词与算式漂移）。"""

    _, text = _rendered_contract_text()
    lines = text.splitlines()

    def row(*needles):
        for line in lines:
            if all(needle in line for needle in needles):
                return line
        raise AssertionError("未找到金例行：{0}".format(needles))

    leading = row("焦点座位=0", "(100, 80, 20, 0)")
    assert "inside_gap=20" in leading and "outside_gap=80" in leading

    critical = row("焦点座位=1", "(100, 80, 80, 0)")
    assert "inside_gap=0" in critical and "outside_gap=0" in critical
    assert "UNRESOLVED" in critical

    behind = row("焦点座位=2", "(100, 80, 20, 0)")
    assert "inside_gap=-60" in behind and "outside_gap=0" in behind

    last = row("焦点座位=3", "(100, 80, 20, 0)")
    assert "inside_gap=-80" in last and "outside_gap=-20" in last

    # 结算后门线变动两行：重算与近似必须给出**不同**数字。
    recompute = row("四座增量", "(0, 0, 70, 0)")
    assert "Δinside_gap=+60" in recompute and "本人增量 +70" in recompute
    # 门线自身随四座向量移动：s'=(100,80,90,0) → 第 2 名 80→90、第 3 名 20→80。
    assert "inside_line 80→90" in recompute, recompute
    assert "outside_line 20→80" in recompute, recompute

    # 只他家结算：s'=(100,50,20,0) → 第 2 名 80→50（本人一分未动，Δinside_gap 仍为 +30）。
    only_others = row("四座增量", "(0, -30, 0, 0)")
    assert "Δinside_gap=+30" in only_others and "本人增量 +0" in only_others
    assert "inside_line 80→50" in only_others, only_others

    frozen = row("近似启发式", "本人增量 +70")
    assert "Δinside_gap=+70" in frozen and "移动=False" in frozen


def test_unreadable_objective_contract_falls_back_with_explicit_note(monkeypatch):
    """目标合同读不到时：用缺省晋级区并在口径块里写明，不编造合同事实。"""

    monkeypatch.setattr(gen, "AV_GROUP_CONTRACT_RELPATH",
                        Path("review/llm-guided-heuristic-route-2026-09-15"
                             "/contracts/__p10_absent__.json"))
    assert gen.gate_advance_count() == (gen.GATE_ADVANCE_FALLBACK, False)
    assert gen.gate_line_indices(gen.GATE_ADVANCE_FALLBACK) == {
        "inside_line_index": 2, "outside_line_index": 1}
    block = gen.gate_line_semantics_block()
    assert "不可读" in block["advance_count_source"]
    assert block["advance_count"] == gen.GATE_ADVANCE_FALLBACK


def test_reference_implementation_passes_restricted_subset_check():
    """参考实现必须能被逐字复制进候选：过同一份受限子集静态检查。"""

    executor = pytest.importorskip("hangma_bot.policy.action_value_executor")
    source = "\n\n".join(
        inspect.getsource(fn) for fn in (
            gen.gate_line_values, gen.gate_line_potentials,
            gen.gate_line_delta_recomputed, gen.gate_line_delta_frozen_line,
            gen.gate_zone_status,
        ))
    candidate = ('"""金例：门线辅助函数可在候选内逐字复用。"""' + "\n\n"
                 + source
                 + "\n\n\n" + "def score_actions(view):" + "\n"
                 + '    """最小骨架：只用同一套辅助函数。"""' + "\n"
                 + "    if view is None:" + "\n"
                 + '        return {"status": "ABSTAIN", "reason": "金例骨架"}' + "\n"
                 + '    return {"status": "ABSTAIN", "reason": "金例骨架"}' + "\n")
    executor.static_check(candidate)
    # 判别力对照：带默认参数的版本必须被拒（否则上面的检查无意义）。
    broken = candidate.replace("def gate_line_values(scores):",
                               "def gate_line_values(scores, fallback=None):")
    assert broken != candidate
    with pytest.raises(executor.StaticCheckError):
        executor.static_check(broken)

# ============================================================ 6. 作者守卫条款（未知 / 批次失败 / 修订行为差异）
#
# 背景（P4 实测，Lead 裁决维持严格口径）：按修正后的准入门禁重判 R6 冻结批次，
# r1 21/24、r2 20/24、admission_pass=false；两条根因都属作者侧可预防：
#   ① 未分析动作给 0.0，排在已知负分动作之前（实测 0.0 vs −17.8941 / −17.1687 /
#      −1.3883 / −17.5296）；② T07 的修订作答只改说明，签名与父代逐项相同。


def _guard_entries(unknown_score, known_score):
    """构造两动作窗口：一个未分析（discard:2b）、一个已知负分（discard:1w）。"""

    return ({"action_key": "discard:2b", "score": unknown_score, "unknown": True},
            {"action_key": "discard:1w", "score": known_score, "unknown": False})


def test_unknown_never_may_outrank_known_negative():
    """未知越位判据与 R6 实测形态：0.0 排在已知负分之前必须被判违规。

    判据（合同 batch_failure_policy + 准入判分器同口径）：
      未分析分数 > 已知负分分数 + 容差 1e-12 ⇒ 违规。
    实测：r1/T07 0.0 vs −17.8941；r1/T08 0.0 vs −17.1687；
          r2/T05 0.0 vs −1.3883；r2/T08 0.0 vs −17.5296 ⇒ 各 1 对违规。
    对照（内置种子）：−5.5 vs −4.5 ⇒ 违规 0 对（−5.5 ≤ −4.5）。
    """

    for unknown_score, known_score in ((0.0, -17.8941), (0.0, -17.1687),
                                       (0.0, -1.3883), (0.0, -17.5296)):
        found = gen.unknown_above_known_violations(
            _guard_entries(unknown_score, known_score), gen.AUTHOR_UNKNOWN_TOLERANCE)
        assert len(found) == 1, (unknown_score, known_score)
        assert found[0]["unknown"] == "discard:2b"
        assert found[0]["known"] == "discard:1w"
        assert found[0]["unknown_score"] == unknown_score
        assert found[0]["known_score"] == known_score

    # 对照：内置种子的写法满足合同（未知低于已知负分）。
    assert gen.unknown_above_known_violations(
        _guard_entries(-5.5, -4.5), gen.AUTHOR_UNKNOWN_TOLERANCE) == []

    # 判据是「不高于」（容差内相等合规），但推荐写法取严格更低——见下一项测试。
    assert gen.unknown_above_known_violations(
        _guard_entries(-17.8941, -17.8941), gen.AUTHOR_UNKNOWN_TOLERANCE) == []
    # 容差内（+1e-13）仍合规；越出容差（+1e-6）即违规。
    assert gen.unknown_above_known_violations(
        _guard_entries(-17.8941 + 1e-13, -17.8941), gen.AUTHOR_UNKNOWN_TOLERANCE) == []
    assert len(gen.unknown_above_known_violations(
        _guard_entries(-17.8941 + 1e-6, -17.8941), gen.AUTHOR_UNKNOWN_TOLERANCE)) == 1

    # 已知**非负**动作不受本判据约束（合同原文只禁止越过已知负分）。
    assert gen.unknown_above_known_violations(
        _guard_entries(0.0, 12.0), gen.AUTHOR_UNKNOWN_TOLERANCE) == []

    # 容差非法 → None：调用方必须按未知处理，不得当成「无违规」。
    for bad in (None, True, False, -1e-12, float("nan"), float("inf")):
        assert gen.unknown_above_known_violations(
            _guard_entries(0.0, -17.8941), bad) is None, bad


def test_guarded_unknown_score_is_strictly_below_every_known_score():
    """推荐写法：未分析动作取「已知最低分 − margin」（严格低于全部已知评分）。

    手算：已知 [−17.8941, −3.2, 12.0]，最低分 −17.8941；margin 1.0
      ⇒ 未分析取值 −17.8941 − 1.0 = −18.8941（< −17.8941 ✓ 违规 0 对）。
    margin 必须 > 0：取 0 时等于已知最低分，次序由 action_key 决定，
    未知仍可能排在已知负分之前 ⇒ 返回 None；负数、布尔、NaN 同样 None。
    没有已知评分（None/空）⇒ None：窗口内没有可比较事实，只能整批 ABSTAIN。
    """

    known = [-17.8941, -3.2, 12.0]
    value = gen.guarded_unknown_score(known, gen.AUTHOR_UNKNOWN_MARGIN)
    assert value == -18.8941
    assert value < min(known)
    assert gen.unknown_above_known_violations(
        _guard_entries(value, -17.8941), gen.AUTHOR_UNKNOWN_TOLERANCE) == []

    assert gen.unknown_score_floor(known) == -17.8941
    # 布尔与 NaN 不得混进最低分；已知全为空 → 无下限。
    assert gen.unknown_score_floor([True, False, float("nan")]) is None
    assert gen.unknown_score_floor([-4.0, None, float("nan"), True, -7.5]) == -7.5

    for bad_margin in (0.0, -1.0, None, True, float("nan")):
        assert gen.guarded_unknown_score(known, bad_margin) is None, bad_margin
    assert gen.guarded_unknown_score(None, 1.0) is None
    assert gen.guarded_unknown_score([], 1.0) is None


def test_action_has_produced_facts_defines_unknown():
    """未分析（缺证）的唯一口径：任何已生产事实都没有，才是未知。

    事实口径同合同 scoring_view.fields.actions；fact_kind=analysis_failed
    且无其他事实视为缺证；空元组分支/路线等于未分析，useful_tiles=() 是
    「已知为空」的事实（不是缺失）。
    """

    assert gen.action_has_produced_facts(None) is False
    assert gen.action_has_produced_facts({}) is False
    assert gen.action_has_produced_facts({"fact_kind": "analysis_failed"}) is False
    assert gen.action_has_produced_facts({"followup_branches": ()}) is False
    assert gen.action_has_produced_facts({"routes": ()}) is False
    assert gen.action_has_produced_facts({"family_progress_entries": ()}) is False

    assert gen.action_has_produced_facts({"fact_kind": "hand_progress"}) is True
    assert gen.action_has_produced_facts({"shanten_after": 2}) is True
    assert gen.action_has_produced_facts({"standard_shanten_after": 3}) is True
    assert gen.action_has_produced_facts({"seven_pairs_shanten_after": 4}) is True
    assert gen.action_has_produced_facts({"useful_tiles": ()}) is True
    assert gen.action_has_produced_facts({"immediate_settlement": {"fan": 2}}) is True
    assert gen.action_has_produced_facts({"followup_branches": ({"k": 1},)}) is True
    # analysis_failed 但另有事实 → 有可用读数。
    assert gen.action_has_produced_facts(
        {"fact_kind": "analysis_failed", "shanten_after": 1}) is True


def test_m1_behavior_difference_selfcheck():
    """修订自查（与生产排序、准入判分同一口径）：只有**首选动作改变**才算行为差异。

    手算：父 [(discard:1w, 5), (discard:2b, −3)]（首选 discard:1w）
      · 子相同 ⇒ changed=False（R6 T07 实测形态：只改说明/注释）
      · 子 [(1w, 5), (2b, −4)] ⇒ 值差 1 项但**次序与首选都没变** ⇒ changed=False
        （复审 C1：只改分值不改次序不是行为差异）
      · 子 [(1w, −3), (2b, 5)] ⇒ 首选 1w → 2b ⇒ changed=True、次序反转 1 对
      · 键集合变化（父 2 键、子 3 键）但首选仍是 1w ⇒ changed=False、added_keys=1
    并列被打破：父 [(a,5),(b,5)] 首选 a（同分按 action_key 升序）；
      子 [(a,5),(b,4)] 首选仍是 a ⇒ 无差异、反转 0 对；
      子 [(a,5),(b,6)] 首选变 b ⇒ 有差异（平分破除按生产排序）。
    """

    parent = (("discard:1w", 5.0), ("discard:2b", -3.0))
    same = gen.behavior_change_report(parent, parent)
    assert same["changed"] is False
    assert same["verdict"] == gen.BEHAVIOR_VERDICT_EQUIVALENT
    assert same["value_diff_count"] == 0
    assert same["order_changed"] is False and same["top_changed"] is False
    assert same["removed_keys"] == 0 and same["added_keys"] == 0
    assert same["parent_top"] == "discard:1w" and same["child_top"] == "discard:1w"
    assert gen.order_reversal_pairs(parent, parent) == ()

    value_only = gen.behavior_change_report(
        parent, (("discard:1w", 5.0), ("discard:2b", -4.0)))
    assert value_only["changed"] is False and value_only["value_diff_count"] == 1
    assert value_only["top_changed"] is False
    assert "保序" in value_only["equivalence_reason"]
    assert gen.order_reversal_pairs(parent, (("discard:1w", 5.0),
                                             ("discard:2b", -4.0))) == ()

    reordered = gen.order_reversal_pairs(
        parent, (("discard:1w", -3.0), ("discard:2b", 5.0)))
    assert reordered == (("discard:1w", "discard:2b"),)
    reversal = gen.behavior_change_report(
        parent, (("discard:1w", -3.0), ("discard:2b", 5.0)))
    assert reversal["value_diff_count"] == 2
    assert reversal["changed"] is True
    assert reversal["verdict"] == gen.BEHAVIOR_VERDICT_OBSERVED
    assert reversal["parent_top"] == "discard:1w"
    assert reversal["child_top"] == "discard:2b"

    added = gen.behavior_change_report(
        parent, (("discard:1w", 5.0), ("discard:2b", -3.0), ("pass", 0.0)))
    assert added["changed"] is False and added["added_keys"] == 1
    assert added["value_diff_count"] == 0 and added["top_changed"] is False

    # 并列被打破：首选未变不算差异；首选改选才算（生产排序同分按 action_key 升序）。
    tie_kept = gen.behavior_change_report(
        (("a", 5.0), ("b", 5.0)), (("a", 5.0), ("b", 4.0)))
    assert tie_kept["changed"] is False and gen.order_reversal_pairs(
        (("a", 5.0), ("b", 5.0)), (("a", 5.0), ("b", 4.0))) == ()
    tie_broken = gen.behavior_change_report(
        (("a", 5.0), ("b", 5.0)), (("a", 5.0), ("b", 6.0)))
    assert tie_broken["changed"] is True
    assert (tie_broken["parent_top"], tie_broken["child_top"]) == ("a", "b")


def test_guard_clauses_are_in_the_prompt_and_enter_contract_identity():
    """条款必须真的进提示词，且随合同身份变化（fail-closed：旧 attempt 不复用）。"""

    payload, text = _rendered_contract_text()
    assert "author_guard_semantics" in payload
    guard = payload["author_guard_semantics"]

    # 1) 条款逐条在提示词里（唯一来源：author_guard_clauses）。
    for clause in gen.author_guard_clauses():
        assert clause in text, clause[:40]
    assert guard["clauses"] == list(gen.author_guard_clauses())

    # 2) 关键约束不缺失（逐条点名检查）。
    for token in ("未知 ≠ 0", "未知不得越位", "batch_failure_policy",
                  "整批 ABSTAIN", "整窗口失效", "不得悄悄拼 V2 分数",
                  "缺证不得冒充已评分", "unknown_facts",
                  "M1 修订必须产生行为差异", "changed_branches",
                  "次序反转", "不得夸大差异"):
        assert token in text, token

    # 3) 反例的具体形态（−17.8941 vs 0.0）必须写进提示词。
    assert "未分析 discard:2b=0 vs 已知负分 discard:1w=-17.8941 ⇒ 违规 1 对" in text
    assert "未分析 discard:2b=0 vs 已知负分 discard:1w=-1.3883 ⇒ 违规 1 对" in text
    assert "未分析 discard:2b=-5.5 vs 已知负分 discard:1w=-4.5 ⇒ 违规 0 对" in text
    assert "未分析动作取 -18.8941" in text
    # C1 金例（值由 behavior_change_report 现算）：只改说明 / 保序平移 / 真实首选改变。
    assert ("修订自查（只改说明（R6 T07 实测形态））：有行为差异=False；判定=EQUIVALENT；"
            "①分值差异 0 项；②排序变化=False；③首选 discard:1w→discard:1w") in text
    assert ("修订自查（保序平移（全体 +100，只改分值不改次序））：有行为差异=False；"
            "判定=EQUIVALENT；①分值差异 2 项；②排序变化=False；"
            "③首选 discard:1w→discard:1w") in text
    assert ("修订自查（真实首选改变（次序反转））：有行为差异=True；判定=REVISION_OBSERVED；"
            "①分值差异 2 项；②排序变化=True；③首选 discard:1w→discard:2b") in text
    assert "有行为差异=True；分值差异 1 项；次序反转 0 对" not in text

    # 4) 自查参考实现与条款同源，且不引用模块常量（可复制进候选）。
    source = guard["reference_implementation"]
    assert inspect.getsource(gen.guarded_unknown_score).strip() in source
    assert inspect.getsource(gen.unknown_above_known_violations).strip() in source
    assert "AUTHOR_UNKNOWN_TOLERANCE" not in source
    assert source.strip() in text

    # 5) 进合同身份：去掉该键 → 身份哈希必须变（fail-closed）。
    trimmed = {key: value for key, value in payload.items()
               if key != "author_guard_semantics"}
    assert gen.action_value_contract_identity(trimmed) != \
        gen.action_value_contract_identity(payload)

    # 6) I1 与 M1 的真实提示词都带该段（只改 render_* 等于没改）。
    parent = {"identity": "genloop|test", "candidate_id": "cand-test",
              "thought": "父代机制说明", "code": "def score_actions(view):\n    pass",
              "code_sha256": "0" * 64}
    for operator, extra in ((gen.OPERATOR_I1, {}), (gen.OPERATOR_M1, {"parent": parent})):
        packet = gen.build_action_value_prompt(operator, gen.render_action_value_task_contract(
            objective_summary="测试目标", panel_boundary="测试面板",
            prompt_role=operator, **extra))
        assert "作者守卫条款" in packet.text, operator
        assert "未知不得越位" in packet.text, operator
        assert "M1 自查指令" in packet.text, operator


def test_guard_reference_passes_restricted_subset_check():
    """自查参考实现必须能被逐字复制进候选（过同一份受限子集静态检查）。"""

    executor = pytest.importorskip("hangma_bot.policy.action_value_executor")
    source = "\n\n".join(
        inspect.getsource(fn) for fn in (
            gen.unknown_score_floor, gen.guarded_unknown_score,
            gen.unknown_above_known_violations,
        ))
    candidate = ('"""金例：守卫辅助函数可在候选内逐字复用。"""' + "\n\n"
                 + source
                 + "\n\n\n" + "def score_actions(view):" + "\n"
                 + '    """最小骨架：只用同一套辅助函数。"""' + "\n"
                 + "    if view is None:" + "\n"
                 + '        return {"status": "ABSTAIN", "reason": "金例骨架"}' + "\n"
                 + '    return {"status": "ABSTAIN", "reason": "金例骨架"}' + "\n")
    executor.static_check(candidate)
    # 判别力对照：去掉容差参数改为外部常量引用仍能通过静态检查（名字在白名单内
    # 才会通过），但**带默认参数**必须被拒——复制时不得加默认值。
    broken = candidate.replace("def guarded_unknown_score(known_scores, margin):",
                               "def guarded_unknown_score(known_scores, margin=1.0):")
    assert broken != candidate
    with pytest.raises(executor.StaticCheckError):
        executor.static_check(broken)
# ============================================================ 7. 可用赛事基准（competition_bases，P10c）
#
# 背景（P11 实测）：候选评分器现在能读到 ScoringView.competition 的阶段账，
# 但提示词渲染器只渲染 scoring_view.fields —— 合同新增的 competition_bases
# 不会进提示词，作者因此不知道字段存在，M1 的最终价值（用上阶段账）落空。


def _contract_bases():
    contract, _ = gen.load_action_value_contract()
    return contract["scoring_view"]["competition_bases"]


def test_prompt_renders_every_competition_basis_key():
    """competition_bases 的每个键都必须进提示词（缺一个就是作者读不到）。"""

    _, text = _rendered_contract_text()
    bases = _contract_bases()
    assert bases, "合同必须声明 competition_bases"
    for key in bases:
        assert key in text, key
    # 关键语义逐条在提示词里（座位序、掩码位置序与闭集、身份锚点、缺账口径）。
    assert "物理座位 0—3" in text
    assert "freshness_masks 的位置序固定为 [stage_scores, table_scores]" in text
    assert "freshness_masks.order：stage_scores、table_scores" in text
    for value in ("stage_account:complete", "stage_account:absent",
                  "stage_account:unmappable", "table_account:live"):
        assert value in text, value
    assert "participant_rank" in text
    assert "ranking 恰 4 条" in text
    assert "不含当前桌进行中积分" in text
    assert "本桌进行中积分" in text
    # 缺键时的 fail-closed 分支说明不在（因为合同有该键）。
    assert "合同未声明 competition_bases" not in text


def test_competition_bases_are_carried_into_payload_and_identity():
    """基准语义进 payload（单源复制，不手抄）并随合同身份变化（fail-closed）。"""

    payload, _ = _rendered_contract_text()
    bases = _contract_bases()
    assert payload["scoring_view"]["competition_bases"] == bases
    trimmed = dict(payload)
    trimmed["scoring_view"] = {key: value for key, value in payload["scoring_view"].items()
                              if key != "competition_bases"}
    assert gen.action_value_contract_identity(trimmed) != \
        gen.action_value_contract_identity(payload)


def test_new_contract_key_is_rendered_automatically(tmp_path, monkeypatch):
    """反 P11 缺陷类：合同新增键即使没被具名渲染，也必须自动进提示词。

    构造：把合同复制一份、在 competition_bases 里加一个未具名键，
    指向该副本渲染 → 键名与取值都必须出现在提示词里（不得静默丢弃）。
    """

    contract, _ = gen.load_action_value_contract()
    mutated = json.loads(json.dumps(contract, ensure_ascii=False))
    mutated["scoring_view"]["competition_bases"]["seat_swap_note"] = "换座后身份随座位搬移"
    path = tmp_path / "action-value-v1-with-extra-key.json"
    path.write_text(json.dumps(mutated, ensure_ascii=False), encoding="utf-8")

    monkeypatch.setattr(gen, "AV_CONTRACT_RELPATH", path)
    gen._AV_CONTRACT_CACHE.clear()
    try:
        text = gen.render_action_value_contract_text(
            gen.render_action_value_task_contract(
                objective_summary="x", panel_boundary="y", prompt_role="i1"))
    finally:
        gen._AV_CONTRACT_CACHE.clear()
    assert "seat_swap_note" in text
    assert "换座后身份随座位搬移" in text
    assert "合同新增键，自动渲染" in text


def test_missing_competition_bases_fails_closed(tmp_path, monkeypatch):
    """合同没有 competition_bases 时不得静默省略：显式写明「不得臆造基准语义」。"""

    contract, _ = gen.load_action_value_contract()
    mutated = json.loads(json.dumps(contract, ensure_ascii=False))
    del mutated["scoring_view"]["competition_bases"]
    path = tmp_path / "action-value-v1-without-bases.json"
    path.write_text(json.dumps(mutated, ensure_ascii=False), encoding="utf-8")

    monkeypatch.setattr(gen, "AV_CONTRACT_RELPATH", path)
    gen._AV_CONTRACT_CACHE.clear()
    try:
        payload = gen.render_action_value_task_contract(
            objective_summary="x", panel_boundary="y", prompt_role="i1")
        text = gen.render_action_value_contract_text(payload)
    finally:
        gen._AV_CONTRACT_CACHE.clear()
    assert payload["scoring_view"]["competition_bases"] is None
    assert "合同未声明 competition_bases" in text
    assert "不得臆造基准语义" in text


def test_stage_scores_absent_is_not_zero_shares_the_unknown_invariant():
    """「stage_scores 缺账不得当 0」并入缺账口径条款，不新造第二套说法。

    E3/M1 把旧「基准唯一（三类不得混算或相加）」拆成两条：账的三个概念
    （已完成账 / 当前桌账 / 当前阶段合计）与缺账口径（未知 ≠ 0）。本用例跟到
    缺账口径那一条上，断言逐项不变。
    """

    clauses = gen.gate_line_clauses()
    basis_clause = [c for c in clauses if c.startswith("缺账口径")][0]
    assert "stage_scores 缺账" in basis_clause
    assert "stage_account:absent" in basis_clause and "stage_account:unmappable" in basis_clause
    assert "不得当 0" in basis_clause
    assert "不得当「四家同分」" in basis_clause
    assert "不得用 table_scores 或 visible_state.scores 顶替" in basis_clause
    # 与作者守卫条款同一条不变量（不是第二套说法）。
    assert "未知 ≠ 0" in basis_clause
    assert "同一条不变量" in basis_clause
    # 已知的零仍可用（四座全 0 账）——不得把「已知零」也当未知。
    assert "已知的零" in basis_clause and "stage_account:complete" in basis_clause

    # 条款与基准块都要真的进提示词，且 I1/M1 真实路径都带。
    _, text = _rendered_contract_text()
    assert basis_clause in text
    parent = {"identity": "genloop|test", "candidate_id": "cand-test",
              "thought": "父代机制说明", "code": "def score_actions(view):\n    pass",
              "code_sha256": "0" * 64}
    for operator, extra in ((gen.OPERATOR_I1, {}), (gen.OPERATOR_M1, {"parent": parent})):
        packet = gen.build_action_value_prompt(operator, gen.render_action_value_task_contract(
            objective_summary="测试目标", panel_boundary="测试面板",
            prompt_role=operator, **extra))
        assert "competition_bases" in packet.text, operator
        assert "participant_rank" in packet.text, operator
        assert "stage_scores 缺账" in packet.text, operator

# ============================================================ 8. E3 · M1 阶段合计语义 + M2 门线数学条款
#
# 复审 §5（R8 包 E3）两处条文缺陷：
#   M1（P1）：投影与机器合同说 stage_scores 只含已完成桌、table_scores 是本桌进行中，
#     同座位序、同单位、互不重叠；作者条款却要求「一次门线只选一个基准」并禁止相加。
#     这不再是防重复累计，而是禁止重建完整当前阶段分数。本节固定三概念、零合金例，
#     并把禁令收窄为「同一份本桌积分的两个基准名不得相加」。
#   M2（P2）：① frozen_line 下「δ 是公共平移、不改变本窗口排序」不成立（同一窗口内
#     不同动作的结算增量可分别为 5 与 15）；② recompute 下门线是顺序统计量，
#     Φ(s)=s[seat]−门线分数 连续且分段线性，跨名次门线改变斜率而非势值不连续，
#     且部分区域 ΔΦ 可以等于本人增量。数值金例：本人增量 59.999999 / 60 / 60.000001
#     → inside 势差 59.999999 / 60 / 60（连续拐点）。


def _e3_clause(needle):
    """取唯一一条含标识的条款；0 条或多条都算失败（防条款被删或写重）。"""

    found = [clause for clause in gen.gate_line_clauses() if needle in clause]
    assert len(found) == 1, (needle, len(found))
    return found[0]


def _e3_row(needle):
    """取第一条含标识的金例行（金例值全部由参考实现算出，测试不复算常量）。"""

    rows = [row for row in gen.gate_line_golden_rows() if needle in row]
    assert rows, needle
    return rows[0]


def _e3_prompt_text():
    return _rendered_contract_text()[1]


# ---------------------------------------------------------------- M1 阶段合计


def test_stage_composition_clause_names_three_concepts():
    """提示词必须分清「已完成账 / 当前桌账 / 当前阶段合计」，并给出合成路径。"""

    clause = _e3_clause("先分辨再算")   # 只命中三概念条款本身（「平移不变」条款会引用它的名字）
    for token in ("已完成账", "当前桌账", "当前阶段合计",
                  "competition.stage_scores", "competition.table_scores",
                  "competition.current_stage_scores",
                  "stage_scores[i] + table_scores[i]",
                  "互不重叠", "同单位", "同座位序",
                  "唯一禁止的重复累计", "visible_state.table_scores",
                  "同一事实的两个基准名", "重建完整当前阶段分数"):
        assert token in clause, token

    # 老条款的绝对禁令必须消失（它正是禁止重建完整阶段分数的那一句）：
    # 条款层与整份提示词（含合同 rendered 字段）都不许再出现。
    joined = "\n".join(gen.gate_line_clauses())
    assert "三类不得混算或相加" not in joined
    assert "一次门线计算只用一个基准" not in joined
    assert "三类不得混算或相加" not in _e3_prompt_text()

    # 「已完成账 + 当前桌账」是要求用的路径；唯一禁止的是同一事实重复累计。
    assert "必须用当前阶段合计" in clause
    assert "算两次" in clause


def test_stage_composition_golden_rows_reproduce_the_review_numbers():
    """零合金例：已完成账 −60 / 当前桌账 +100 / 合计 **+40**（焦点座位 2）。"""

    completed = (60.0, 40.0, -20.0, -80.0)
    table = (-100.0, 0.0, 100.0, 0.0)
    composite = tuple(a + b for a, b in zip(completed, table))
    assert composite == (-40.0, 40.0, 80.0, -80.0)

    # 参考实现复算（提示词里的数字必须与它一致）。
    assert gen.gate_line_potentials(completed, 2)["inside_gap"] == -60.0
    assert gen.gate_line_potentials(table, 2)["inside_gap"] == 100.0
    assert gen.gate_line_potentials(composite, 2)["inside_gap"] == 40.0
    assert gen.gate_zone_status(completed, 2, 2)["zone"] == "OUT"
    assert gen.gate_zone_status(composite, 2, 2)["zone"] == "IN"

    for needle, gap in (("阶段账金例·已完成账", "inside_gap=-60"),
                        ("阶段账金例·当前桌账", "inside_gap=100"),
                        ("阶段账金例·当前阶段合计", "inside_gap=40")):
        row = _e3_row(needle)
        assert gap in row, row
        assert "焦点座位=2" in row, row
    composite_row = _e3_row("阶段账金例·当前阶段合计")
    assert "(-40, 40, 80, -80)" in composite_row, composite_row
    assert "IN" in composite_row, composite_row
    # 结论行必须点明「只看已完成账会把当前领先者当落后者」。
    conclusion = _e3_row("阶段账金例结论")
    assert "把当前领先者当落后者" in conclusion, conclusion
    assert "+40" in conclusion, conclusion


def test_stage_composition_clause_is_in_the_author_prompt_both_operators():
    """真实生成路径（I1 与 M1）都必须带三概念条款与零合金例。"""

    _, text = _rendered_contract_text()
    assert _e3_clause("先分辨再算") in text
    assert _e3_row("阶段账金例·当前阶段合计") in text

    parent = {"identity": "genloop|test", "candidate_id": "cand-test",
              "thought": "父代机制说明", "code": "def score_actions(view):\n    pass",
              "code_sha256": "0" * 64}
    for operator, extra in ((gen.OPERATOR_I1, {}), (gen.OPERATOR_M1, {"parent": parent})):
        packet = gen.build_action_value_prompt(operator, gen.render_action_value_task_contract(
            objective_summary="测试目标", panel_boundary="测试面板",
            prompt_role=operator, **extra))
        assert "当前阶段合计" in packet.text, operator
        assert "current_stage_scores" in packet.text, operator
        assert "inside_gap=40" in packet.text, operator


# ---------------------------------------------------------------- M2 数学条款


def test_frozen_line_clause_drops_the_false_common_shift_claim():
    """「δ 是公共平移、不改变本窗口排序」必须消失（只允许出现在禁止条款里）。"""

    clause = _e3_clause("动作后门线势差只有两种模式")
    assert "ΔΦ = δ 对本座位" in clause and "逐动作恒成立" in clause
    # 不同动作的结算增量可以不同 —— 数值反例必须写出来。
    assert "+5" in clause and "+15" in clause, clause
    assert "全部动作共享同一个常数平移" in clause, clause
    # 正文里不得出现把 δ 当成公共平移的陈述（引用即禁止的写法才行）。
    for line in _e3_prompt_text().splitlines():
        if "公共平移" in line:
            assert "不得" in line, "δ=公共平移 的错述出现在陈述位置：{0}".format(line)

    # 参考实现同源：逐动作取增量，δ 不同则势差不同（不是公共平移）。
    first = gen.gate_line_delta_frozen_line(S, 2, 5.0)
    second = gen.gate_line_delta_frozen_line(S, 2, 15.0)
    assert first["delta_inside"] == 5.0 and second["delta_inside"] == 15.0
    assert first["delta_inside"] != second["delta_inside"]
    # 对照：真正共享同一常数平移时排序才不变（四座同加 c）。
    assert gen.gate_line_potentials(S, 2)["inside_gap"] == \
        gen.gate_line_potentials(tuple(item + 7.0 for item in S), 2)["inside_gap"]


def test_recompute_clause_states_continuity_and_conditional_equality():
    """ΔΦ 可以等于本人增量；跨名次门线是斜率变化，不是势值不连续。"""

    clause = _e3_clause("两种模式的差别")
    for token in ("连续", "分段线性", "斜率", "有时成立", "总是成立",
                  "一般不等于", "恰等于本人增量"):
        assert token in clause, token
    # 绝对式「ΔΦ ≠ 本人增量」不得无保留地陈述：同一行必须带纠正标记
    # （「不得…」的禁止条款，或「不是恒真」的更正说明）。
    for line in _e3_prompt_text().splitlines():
        if "ΔΦ ≠ 本人增量" in line or "ΔΦ 不等于本人增量" in line:
            assert ("不得" in line or "不是恒真" in line), "绝对不等式无保留地出现在陈述位置：{0}".format(line)
        if "跨越处不连续" in line:
            assert "只属于" in line, "不连续错述出现在陈述位置：{0}".format(line)

    # 数值复算：本人增量恰等于势差的那一行（金例 +60）。
    gold = (100.0, 80.0, 20.0, 0.0)
    equal_row = gen.gate_line_delta_recomputed(gold, 2, (0.0, 0.0, 60.0, 0.0))
    assert equal_row["delta_inside"] == 60.0, "门线未移动时 ΔΦ 恰等于本人增量"
    assert equal_row["inside_line_moved"] is False


def test_continuity_golden_rows_match_the_reference_implementation():
    """连续拐点金例：59.999999 / 60 / 60.000001 → inside 势差 59.999999 / 60 / 60。"""

    gold = (100.0, 80.0, 20.0, 0.0)
    deltas = (59.999999, 60.0, 60.000001)
    measured = tuple(
        gen.gate_line_delta_recomputed(gold, 2, (0.0, 0.0, delta, 0.0))["delta_inside"]
        for delta in deltas)
    assert measured == (59.999999, 60.0, 60.0), measured
    # 连续性：相邻采样点的跳变不超过增量步长（无跳变）。
    for before, after in zip(measured, measured[1:]):
        assert 0.0 <= after - before <= 1e-6 + 1e-12, (before, after)

    rows = [row for row in gen.gate_line_golden_rows() if "连续拐点金例" in row]
    assert len(rows) == 3, rows
    for row, delta, gap in zip(rows, deltas, measured):
        assert "焦点座位=2" in row, row
        # 分隔符 "；" 让 +60 不会误命中 +60.000001 那一行。
        assert "本人增量 {0}；".format(gen._gate_exact_signed(delta)) in row, row
        assert "Δinside_gap={0}".format(gen._gate_exact_signed(gap)) in row, row
    # 60.000001 必须精确呈现（%g 会把它吞成 60，金例就失去判别力）。
    assert "60.000001" in "\n".join(rows)
    summary = _e3_row("连续拐点序列")
    assert "59.999999" in summary and "60.000001" in summary, summary
    assert "恰等于本人增量" in summary, summary


def test_piecewise_linear_slope_changes_at_the_rank_line():
    """分段线性：门线未越过时 ΔΦ 随本人增量斜率 1；越过后斜率 0（连续拐点）。"""

    gold = (100.0, 80.0, 20.0, 0.0)

    def delta(own):
        return gen.gate_line_delta_recomputed(gold, 2, (0.0, 0.0, own, 0.0))["delta_inside"]

    below = tuple(delta(own) for own in (50.0, 55.0, 59.0, 60.0))
    assert below == (50.0, 55.0, 59.0, 60.0), below          # 斜率 1
    above = tuple(delta(own) for own in (60.0, 61.0, 70.0))
    assert above == (60.0, 60.0, 60.0), above                # 斜率 0
    # 拐点在本人增量 60（越过第 2 名分数线 80），两侧都连续。
    assert delta(59.999999) < delta(60.0) == delta(60.000001)


def test_forbidden_claims_are_rendered_and_enter_the_semantics_block():
    """被禁止的错述必须逐条出现在提示词的禁止清单里（可被作者读到）。"""

    claims = gen.GATE_LINE_FORBIDDEN_CLAIMS
    assert claims, "M2 的两处错述必须显式列为禁止陈述"
    text = _e3_prompt_text()
    for claim in claims:
        assert claim in text, claim
    block = gen.gate_line_semantics_block()
    assert block["forbidden_claims"] == list(claims)


# ---------------------------------------------------------------- 剩余赛程缺口


def test_remaining_schedule_gap_is_clause_and_contract_registered():
    """剩余赛程未投影：提示词必须写明不可见，合同必须登记为剩余缺口。"""

    clause = _e3_clause("可见赛程")
    for token in ("未投影", "residual_gaps", "剩余桌数", "阶段总桌数",
                  "逐字不变", "最后机会追分", "仍有多桌可保守",
                  "不得", "不可见"):
        assert token in clause, token

    contract, _ = gen.load_action_value_contract()
    bases = contract["scoring_view"]["competition_bases"]
    gaps = bases["residual_gaps"]
    assert gaps, "合同必须显式登记剩余缺口"
    gap = [item for item in gaps if "剩余" in item][0]
    for token in ("stage_no", "stage_total", "单位", "不得当 0", "剩余桌数"):
        assert token in gap, token
    # 缺口登记进提示词（作者看得到「哪些事实不可见」）。
    _, text = _rendered_contract_text()
    assert "residual_gaps" in text
    assert gap in text


