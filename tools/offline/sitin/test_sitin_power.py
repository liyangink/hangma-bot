"""坐隐 1.1 工具的自测：锁定验收判据。

不依赖网络、不写文件、不跑桌赛；全部在既有产物上做纯计算。
运行：.venv/bin/python3 -m pytest review/llm-guided-heuristic-route-2026-09-15/tools/test_sitin_power.py -q
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
import math
import sys
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
_REPO = _PROJECT_ROOT


def _load_module():
    """按路径加载工具模块（不放进包，避免污染生产命名空间）。"""

    spec = importlib.util.spec_from_file_location("sitin_power", _project_file(_PROJECT_ROOT, _HERE / "sitin_power.py"))
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules["sitin_power"] = module
    spec.loader.exec_module(module)
    return module


sitin = _load_module()

PROBE_RESULTS = _project_file(_PROJECT_ROOT, _REPO / "runs/probe-scale-20260915/out/results.jsonl")
PROBE_EXPERIMENT = _project_file(_PROJECT_ROOT, _REPO / "runs/probe-scale-20260915/experiment.json")
FIXED_RULE = _project_file(_PROJECT_ROOT, 'review/heuristic-balanced-2026-09-10')


def test_roots_required_matches_reviewer_power_table():
    """功效公式必须复现第四轮复核给出的五行（审查 R2-2 已独立复算）。"""

    sd = 59.45250204995581
    expected = {1.0: 27743, 2.0: 6936, 3.0: 3083, 5.0: 1110, 15.0: 124}
    for effect, want in expected.items():
        assert sitin.roots_required(effect, sd) == want


def test_minimum_detectable_effect_is_inverse_of_roots_required():
    """MDE 与"所需根组"必须互为反函数。"""

    sd = 59.45250204995581
    for effect in (1.0, 2.0, 5.0):
        need = sitin.roots_required(effect, sd)
        assert sitin.minimum_detectable_effect(sd, need) <= effect


@pytest.mark.skipif(not PROBE_RESULTS.exists(), reason="缺少 probe 产物")
def test_probe_reproduces_root_level_figures():
    """probe-scale 的根级口径：16 根、64 配对、sd≈59.4525、换座完全重复。"""

    seeds = sitin.load_seed_map(PROBE_EXPERIMENT)["seeds"]
    pairs, exclusions = sitin.collect_root_pairs(
        sitin._load_rows(PROBE_RESULTS),
        baseline_policy_id="weighted_heuristic_v1",
        challenger_policy_id="weighted_heuristic_v2",
        seed_map=seeds,
    )
    assert exclusions == [], "probe 产物不应有排除项：" + repr(exclusions)
    roots = sitin.aggregate_by_root(pairs)
    assert len(roots) == 16
    assert sum(r.n_pairs for r in roots) == 64
    # 该 probe 中四次换座给出完全相同的差值——这正是初版把它当独立样本的原因
    assert all(r.distinct_deltas == 1 for r in roots)
    report = sitin.build_report(roots)
    assert report["roots"]["sd_root"] == pytest.approx(59.452502, abs=1e-6)
    assert report["roots"]["mean_delta"] == pytest.approx(2.75, abs=1e-9)


@pytest.mark.skipif(not PROBE_RESULTS.exists(), reason="缺少 probe 产物")
def test_power_table_tables_equal_roots_times_two_arms_times_four_rotations():
    """桌数口径：根组 × 2 臂 × 4 换座；不得只算根组或配对。"""

    seeds = sitin.load_seed_map(PROBE_EXPERIMENT)["seeds"]
    pairs, _ = sitin.collect_root_pairs(
        sitin._load_rows(PROBE_RESULTS),
        baseline_policy_id="weighted_heuristic_v1",
        challenger_policy_id="weighted_heuristic_v2",
        seed_map=seeds,
    )
    report = sitin.build_report(sitin.aggregate_by_root(pairs))
    for row in report["power_table"]:
        assert row["tables_required"] == row["roots_required"] * 2 * 4


@pytest.mark.skipif(not FIXED_RULE.exists(), reason="缺少历史战役产物")
def test_fixed_rule_batch_keeps_arms_separate_from_opponents():
    """历史批次里三个对手与基线同名；不得把它们误当成被测臂。

    该批每批为 32 根 × 双臂 × 1 换座 = 64 桌，即 32 个配对。
    """

    path = _project_file(_PROJECT_ROOT, FIXED_RULE / "fixed-rule-1340000/results.jsonl")
    if not path.exists():
        pytest.skip("缺少 fixed-rule-1340000 产物")
    # 必须显式声明方向：字典序会把符号反过来（weighted_heuristic_v2 排在
    # v2_hu_upgrade_v1 之后，缺省推断会得到 −6.3125 而不是 +6.3125）
    pairs, exclusions = sitin.collect_root_pairs(
        sitin._load_rows(path),
        baseline_policy_id="weighted_heuristic_v2",
        challenger_policy_id="v2_hu_upgrade_v1",
    )
    assert exclusions == [], "同名的三个对手不应导致排除：" + repr(exclusions[:3])
    roots = sitin.aggregate_by_root(pairs)
    assert len(roots) == 32
    report = sitin.build_report(roots)
    assert report["roots"]["pairs_total"] == 32
    # 单换座 ⇒ 每根只有一个配对值
    assert all(r.n_pairs == 1 for r in roots)
    assert report["roots"]["mean_delta"] == pytest.approx(6.3125, abs=1e-9)


@pytest.mark.skipif(not PROBE_RESULTS.exists(), reason="缺少 probe 产物")
def test_missing_seed_map_marks_roots_as_unknown():
    """没有 experiment 时不得声称根组身份已知（跨运行合并的前置条件）。"""

    pairs, _ = sitin.collect_root_pairs(sitin._load_rows(PROBE_RESULTS))
    report = sitin.build_report(sitin.aggregate_by_root(pairs))
    assert report["roots"]["seeds_known"] is False
    assert all(item["seed"] is None for item in report["per_root"])


@pytest.mark.skipif(not FIXED_RULE.exists(), reason="缺少历史战役产物")
def test_default_orientation_is_flagged_as_unverified():
    """不显式声明方向时必须出排除项——符号不可信。"""

    path = _project_file(_PROJECT_ROOT, FIXED_RULE / "fixed-rule-1340000/results.jsonl")
    if not path.exists():
        pytest.skip("缺少 fixed-rule-1340000 产物")
    _, exclusions = sitin.collect_root_pairs(sitin._load_rows(path))
    assert any("符号方向未经验证" in item for item in exclusions)


def test_incomplete_status_rows_are_excluded_not_silently_dropped():
    """非 complete 行必须进排除清单，不静默丢弃。"""

    rows = [
        {
            "status": "error",
            "scenario_id": "s0",
            "pair_id": "s0:0123",
            "policy_ids_by_seat": ["a", "b", "c", "d"],
            "scores_after": [0, 0, 0, 0],
        }
    ]
    pairs, exclusions = sitin.collect_root_pairs(rows)
    assert pairs == []
    assert len(exclusions) == 1 and "status=error" in exclusions[0]


def test_mismatched_opponents_are_rejected():
    """两臂对手阵容不同时不得当成复式配对。"""

    def row(label, scores, policy_ids):
        return {
            "status": "complete",
            "scenario_id": "s0",
            "pair_id": "s0:0123",
            "policy_ids_by_seat": policy_ids,
            "scores_after": scores,
            "expected_hands": 8,
            "completed_hands": 8,
            "invalid_reasons": [],
            "source_kind": "simulation",
            "seat_permutation": [0, 1, 2, 3],
            "game_key": {"game_id": "t:s0:0123:" + label},
        }

    rows = [
        row("base", [10, 0, 0, 0], ["base", "o1", "o2", "o3"]),
        row("chal", [12, 0, 0, 0], ["chal", "o1", "o2", "oX"]),
    ]
    pairs, exclusions = sitin.collect_root_pairs(rows)
    assert pairs == []
    assert any("对手阵容不一致" in item for item in exclusions)

# ---------------------------------------------------------------------------
# 第五轮复核（REVIEW-5-PHASE1）新增：输入完整性、重复行、方向参数、零方差
# ---------------------------------------------------------------------------

def _row(label, scores, *, source_kind="simulation", completed=8, expected=8,
         invalid=(), permutation=(0, 1, 2, 3), scenario="s0"):
    return {
        "status": "complete",
        "scenario_id": scenario,
        "pair_id": scenario + ":0123",
        "policy_ids_by_seat": [label, "o1", "o2", "o3"],
        "scores_after": scores,
        "expected_hands": expected,
        "completed_hands": completed,
        "invalid_reasons": list(invalid),
        "source_kind": source_kind,
        "seat_permutation": list(permutation),
        "game_key": {"game_id": "t:%s:0123:%s" % (scenario, label)},
    }


def test_incomplete_or_non_strength_rows_are_excluded():
    """status=complete 不足以进入强度统计：来源、单局数、失效原因都要查。

    这四项是仓库既有语义（check_complete_consistency 与
    STRENGTH_SOURCE_KINDS）；初版只查了 status。
    """

    good = [_row("base", [10, 0, 0, 0]), _row("chal", [12, 0, 0, 0])]
    pairs, exc = sitin.collect_root_pairs(
        good, baseline_policy_id="base", challenger_policy_id="chal")
    assert len(pairs) == 1 and exc == []

    # 候选臂**独立构造**，避免"同臂两行"被当成重复而掩盖真正的失败原因
    cases = {
        "mock 来源": _row("chal", [12, 0, 0, 0], source_kind="mock"),
        "单局数不足": _row("chal", [12, 0, 0, 0], completed=1),
        "有失效原因": _row("chal", [12, 0, 0, 0], invalid=["blocked"]),
    }
    for name, bad in cases.items():
        pairs, exc = sitin.collect_root_pairs(
            [_row("base", [10, 0, 0, 0]), bad],
            baseline_policy_id="base", challenger_policy_id="chal")
        assert pairs == [], name
        assert exc, name


def test_mismatched_seat_permutation_is_rejected():
    """换座配置必须逐座一致（复用 _pair_consistency 语义）。"""

    rows = [_row("base", [10, 0, 0, 0]), _row("chal", [12, 0, 0, 0], permutation=(3, 2, 1, 0))]
    pairs, exc = sitin.collect_root_pairs(
        rows, baseline_policy_id="base", challenger_policy_id="chal")
    assert pairs == []
    assert any("seat_permutation" in item for item in exc)


def test_conflicting_duplicate_arm_is_rejected_regardless_of_order():
    """同一配对臂出现冲突重复时，结果**不得取决于文件顺序**。"""

    base = _row("base", [10, 0, 0, 0])
    chal = _row("chal", [12, 0, 0, 0])
    dup = _row("chal", [9999, 0, 0, 0])   # 同臂、不同分数
    for rows in ([base, chal, dup], [dup, base, chal]):
        pairs, exc = sitin.collect_root_pairs(
            rows, baseline_policy_id="base", challenger_policy_id="chal")
        assert pairs == []
        assert any("多行且取值不同" in item for item in exc)


def test_identical_duplicate_is_deduplicated_with_a_note():
    """完全相同的重复行可去重，但必须留下说明。"""

    base = _row("base", [10, 0, 0, 0])
    chal = _row("chal", [12, 0, 0, 0])
    pairs, exc = sitin.collect_root_pairs(
        [base, chal, dict(chal)], baseline_policy_id="base", challenger_policy_id="chal")
    assert len(pairs) == 1
    assert any("重复行，已去重" in item for item in exc)


def test_single_sided_direction_parameter_raises():
    """只给一侧身份必须报错——单侧会静默反转差值符号。"""

    rows = [_row("base", [10, 0, 0, 0]), _row("chal", [12, 0, 0, 0])]
    for kwargs in ({"baseline_policy_id": "base"}, {"challenger_policy_id": "chal"}):
        with pytest.raises(ValueError):
            sitin.collect_root_pairs(rows, **kwargs)


def test_zero_variance_reports_instead_of_crashing():
    """自身/等价对照的零方差是**期望结果**，报告必须能表示它。"""

    # 需要**多个根组**才能定义根级标准差；单根组的 sd 为 None，无法检验零方差
    rows = []
    for i in range(4):
        rows += [_row("base", [10, 0, 0, 0], scenario="z%d" % i),
                 _row("chal", [10, 0, 0, 0], scenario="z%d" % i)]
    pairs, _ = sitin.collect_root_pairs(
        rows, baseline_policy_id="base", challenger_policy_id="chal")
    report = sitin.build_report(sitin.aggregate_by_root(pairs))
    assert report["roots"]["sd_root"] == 0
    assert report["power_table"] == []
    assert "零方差" in (report["planning_note"] or "")


def test_budget_uses_explicit_rotations_and_reports_actual_tables():
    """预算的换座数必须显式；同时报告**实际双臂桌数**。"""

    rows = []
    for i in range(4):
        rows.append(_row("base", [10, 0, 0, 0], scenario="s%d" % i))
        rows.append(_row("chal", [12, 0, 0, 0], scenario="s%d" % i))
    pairs, _ = sitin.collect_root_pairs(
        rows, baseline_policy_id="base", challenger_policy_id="chal")
    roots = sitin.aggregate_by_root(pairs)
    one = sitin.build_report(roots)
    four = sitin.build_report(roots, rotations_for_budget=4)
    assert one["roots"]["observed_rotations_max"] == 1
    assert one["roots"]["tables_total"] == 4 * 2         # 4 配对 × 2 臂
    assert one["roots"]["count"] == 4
    # 基线/候选同分 ⇒ sd=0，功效表为空；换座数仍需在报告中显式
    assert "每根换座数 = 4" in " ".join(four["notes"])
    assert "每根换座数 = 1" in " ".join(one["notes"])
