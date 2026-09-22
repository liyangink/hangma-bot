"""action_value_v1 独立策略评分接缝的单元测试（T01/T05/T06 + 静态负例 + 计费）。

权威行为来自 SEARCH-SPACE-REDESIGN-2026-09-16.md §14 验收矩阵：
- T01 同事实两个完整种子产生不同合法排序；移除 V2 模块依赖不影响装载。
- T05 合法 Hu 与继续均可进入排序；hu_first_reference 让胡恒第一；旧策略零改动。
- T06 抛错/超量死循环/NaN/缺动作/非法键/trace 超限触发整批失败或
  WorkloadExceeded，绝不部分补零；ABSTAIN 路径带 reason。
"""

from __future__ import annotations

import subprocess
import sys
from typing import Any, Callable, Dict, Mapping

import pytest

from hangma_bot.hangma.interface import Settlement
from hangma_bot.kernel.actions import Discard, Hu, Pass, Peng, Tile

from hangma_bot.policy.action_value import (
    SCORING_VIEW_SCHEMA_VERSION,
    ActionScore,
    ActionView,
    AnalysisProfileView,
    CompetitionView,
    ScoreBatch,
    ScoringView,
    batch_to_ranked_candidates,
    run_scoring_skeleton,
)
from hangma_bot.policy.action_value_executor import (
    MAX_COUNTED_OPERATIONS,
    StaticCheckError,
    WorkloadExceeded,
    ActionValueExecutor,
    compute_candidate_identity,
    compute_deps_digest,
)
from hangma_bot.policy.action_value_seeds import (
    SEED_NAMES,
    build_action_value_policy,
    build_sample_view,
    self_check,
)


# ---------------------------------------------------------------------------
# 视图构造助手
# ---------------------------------------------------------------------------


def _make_view(actions: tuple, *, competition: CompetitionView | None = None) -> ScoringView:
    """按 action_key 升序构造测试视图（调用方保证升序）。"""
    return ScoringView(
        schema_version=SCORING_VIEW_SCHEMA_VERSION,
        visible_state=build_sample_view().visible_state,
        actions=actions,
        analysis_profile=AnalysisProfileView(
            semantics_version="value-analysis-sample/1",
            max_expansions=2048,
            max_routes_per_candidate=128,
            truncation_note="测试视图",
            ruleset_version="sample",
        ),
        competition=competition,
    )


def _conflict_view() -> ScoringView:
    """T01 取舍样例：短距牌效（弃牌）与路线进展（碰）冲突。

    - discard:2w：向听 1、有效牌 10 → 牌效 2.0；family_progress=SAME。
    - peng:5t：向听 3、有效牌 4 → 牌效 -7.0；但 ADVANCE +2、立即结算
      fan 8/self_delta 32、条件路线 conditional_settlement fan 16（R2/S2
      修正：种子从真实 ValueRoute 字段读取，不再读不存在的 branch.fan）
      → 路线分 11.0。
    - pass：无任何分支事实 → 两种子均显式未知处理垫底。
    """
    actions = (
        ActionView(
            action_key="discard:2w",
            action=Discard(tile=Tile("2w")),
            action_type="discard",
            is_legal=True,
            followup_branches=(
                {"followup_key": "discard:2w", "combined_shanten": 1, "support_remaining": 10},
            ),
            family_progress="SAME",
        ),
        ActionView(
            action_key="pass",
            action=Pass(),
            action_type="pass",
            is_legal=True,
            family_progress="SAME",
        ),
        ActionView(
            action_key="peng:5t",
            action=Peng(tile=Tile("5t")),
            action_type="peng",
            is_legal=True,
            followup_branches=(
                {
                    "followup_key": "peng:5t",
                    "combined_shanten": 3,
                    "support_remaining": 4,
                },
            ),
            routes=(
                {
                    "followup_discard": None,
                    "shanten": 0,
                    "useful_tiles": ({"code": "5t", "remaining_estimate": 2},),
                    "conditional_settlement": {
                        "fan": 16, "score_delta": (16, -6, -6, -4),
                        "self_delta": 16, "details": ("conflict-route",),
                    },
                    "conditions": {
                        "draw_kind": "normal", "pre_draw_hand": ("5t", "5t"),
                        "meld_count": 0, "chain_count": 0, "chain_piao": 0,
                        "baotou": False,
                    },
                    "support": "conditional_witness",
                },
            ),
            immediate_settlement=Settlement(
                score_delta=(32, -11, -11, -10), fan=8, details=("conflict-sample",)
            ),
            family_progress="ADVANCE",
        ),
    )
    return _make_view(actions)


def _hu_continue_view() -> ScoringView:
    """T05 样例：合法 Hu 与继续（弃牌）并存且弃牌牌效更高。"""
    actions = (
        ActionView(
            action_key="discard:3t",
            action=Discard(tile=Tile("3t")),
            action_type="discard",
            is_legal=True,
            followup_branches=(
                {"followup_key": "discard:3t", "combined_shanten": 0, "support_remaining": 12},
            ),
            family_progress="ADVANCE",
        ),
        ActionView(
            action_key="hu",
            action=Hu(),
            action_type="hu",
            is_legal=True,
            immediate_settlement=Settlement(
                score_delta=(4, -2, -1, -1), fan=1, details=("hu-sample",)
            ),
            family_progress="CLOSE",
        ),
    )
    return _make_view(actions)


def _scores_by_key(batch: ScoreBatch) -> Dict[str, float]:
    return {entry.action_key: entry.score for entry in batch.entries}


def _plain_candidate(result: Mapping[str, Any]) -> Callable[[Mapping[str, Any]], Mapping[str, Any]]:
    def candidate(_view: Mapping[str, Any]) -> Mapping[str, Any]:
        return result

    return candidate


# ---------------------------------------------------------------------------
# T01：同事实两个完整种子产生不同合法排序
# ---------------------------------------------------------------------------


class TestT01TwoSeedsDifferentRankings:
    def test_both_seeds_score_complete_and_legal(self) -> None:
        view = _conflict_view()
        for name in ("efficiency_seed", "route_value_seed"):
            batch = build_action_value_policy(name).score(view)
            assert batch.status == "SCORED"
            assert set(_scores_by_key(batch)) == set(view.expected_action_keys())

    def test_efficiency_prefers_short_distance_discard(self) -> None:
        batch = build_action_value_policy("efficiency_seed").score(_conflict_view())
        scores = _scores_by_key(batch)
        assert scores["discard:2w"] > scores["peng:5t"]
        assert scores["discard:2w"] == pytest.approx(2.0)
        assert scores["peng:5t"] == pytest.approx(-7.0)

    def test_route_value_prefers_advancing_route(self) -> None:
        batch = build_action_value_policy("route_value_seed").score(_conflict_view())
        scores = _scores_by_key(batch)
        assert scores["peng:5t"] > scores["discard:2w"]
        assert scores["peng:5t"] == pytest.approx(11.0)
        assert scores["discard:2w"] == pytest.approx(2.0)

    def test_orderings_genuinely_differ(self) -> None:
        view = _conflict_view()
        first_eff = batch_to_ranked_candidates(
            build_action_value_policy("efficiency_seed").score(view), view.actions
        )[0].action_key
        first_route = batch_to_ranked_candidates(
            build_action_value_policy("route_value_seed").score(view), view.actions
        )[0].action_key
        assert first_eff == "discard:2w"
        assert first_route == "peng:5t"

    def test_unknown_not_ranked_above_known_negative(self) -> None:
        """未知的 pass 不得排在已知负分（peng:5t=-7.0）之前。"""
        batch = build_action_value_policy("efficiency_seed").score(_conflict_view())
        scores = _scores_by_key(batch)
        assert scores["pass"] < scores["peng:5t"] < 0.0
        entry = next(e for e in batch.entries if e.action_key == "pass")
        assert entry.trace["basis"] == "unknown_field_basis"
        assert entry.trace["field"] == "combined_shanten"
        assert entry.trace["anchor"] == pytest.approx(scores["peng:5t"] - 1.0)

    def test_deterministic_across_fresh_loads(self) -> None:
        view = _conflict_view()
        first = build_action_value_policy("efficiency_seed").score(view)
        second = build_action_value_policy("efficiency_seed").score(view)
        assert first == second

    def test_route_value_trace_disclaims_expected_points(self) -> None:
        batch = build_action_value_policy("route_value_seed").score(_conflict_view())
        for entry in batch.entries:
            assert "非期望积分" in entry.trace["note"]

    def test_removing_heuristic_v2_does_not_affect_loading(self) -> None:
        """T01 import 隔离：屏蔽 heuristic_v2 后新接缝仍可装载并自测。"""
        script = (
            "import sys\n"
            "import hangma_bot.policy  # 包初始化（此时 v2 正常加载）\n"
            "for name in [n for n in sys.modules if n.startswith('hangma_bot.policy.action_value')]:\n"
            "    del sys.modules[name]\n"
            "sys.modules['hangma_bot.policy.heuristic_v2'] = None  # 再次 import 立即失败\n"
            "try:\n"
            "    import hangma_bot.policy.heuristic_v2\n"
            "    raise AssertionError('v2 屏蔽失败')\n"
            "except ImportError:\n"
            "    pass\n"
            "from hangma_bot.policy.action_value_seeds import build_action_value_policy, self_check\n"
            "scorer = build_action_value_policy('efficiency_seed')\n"
            "assert scorer.name == 'efficiency_seed'\n"
            "assert self_check() == {'efficiency_seed': 'ok', 'route_value_seed': 'ok', 'hu_first_reference': 'ok'}\n"
            "print('ISOLATION_OK')\n"
        )
        result = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True,
            text=True,
            env={"PYTHONDONTWRITEBYTECODE": "1", "PATH": "/usr/bin:/bin"},
        )
        assert result.returncode == 0, result.stderr
        assert "ISOLATION_OK" in result.stdout

    def test_seed_sources_do_not_reference_v2(self) -> None:
        """绑定级隔离：三个新模块的名字绑定不来自 weighted_heuristic/heuristic_v2。"""
        import types

        from hangma_bot.policy import action_value, action_value_executor, action_value_seeds

        banned = {
            "hangma_bot.policy.heuristic_v2",
            "hangma_bot.policy.weighted_heuristic",
        }
        for module in (action_value, action_value_executor, action_value_seeds):
            for name, value in vars(module).items():
                if isinstance(value, types.ModuleType):
                    assert value.__name__ not in banned, name
                owner = getattr(value, "__module__", None)
                assert owner not in banned, "{0}.{1}".format(module.__name__, name)


# ---------------------------------------------------------------------------
# T05：胡与继续均可进入排序；旧策略零改动
# ---------------------------------------------------------------------------


class TestT05HuAndContinueCompared:
    def test_hu_and_continue_both_enter_ranking(self) -> None:
        view = _hu_continue_view()
        batch = build_action_value_policy("efficiency_seed").score(view)
        assert set(_scores_by_key(batch)) == {"discard:3t", "hu"}

    def test_efficiency_can_rank_continue_above_hu(self) -> None:
        """compare_legal：立即胡不强制第一（这不是规则定理）。"""
        view = _hu_continue_view()
        ranked = batch_to_ranked_candidates(
            build_action_value_policy("efficiency_seed").score(view), view.actions
        )
        assert ranked[0].action_key == "discard:3t"
        assert ranked[1].action_key == "hu"

    def test_hu_first_reference_keeps_hu_always_first(self) -> None:
        view = _hu_continue_view()
        batch = build_action_value_policy("hu_first_reference").score(view)
        ranked = batch_to_ranked_candidates(batch, view.actions)
        assert ranked[0].action_key == "hu"
        hu_score = _scores_by_key(batch)["hu"]
        assert hu_score == 1_000_000.0
        assert all(hu_score > entry.score for entry in batch.entries if entry.action_key != "hu")

    def test_hu_first_matches_efficiency_below_hu(self) -> None:
        view = _hu_continue_view()
        eff = batch_to_ranked_candidates(
            build_action_value_policy("efficiency_seed").score(view), view.actions
        )
        ref = batch_to_ranked_candidates(
            build_action_value_policy("hu_first_reference").score(view), view.actions
        )
        assert [c.action_key for c in ref if c.action_key != "hu"] == [
            c.action_key for c in eff if c.action_key != "hu"
        ]

    def test_frozen_old_policy_files_unchanged(self) -> None:
        """旧策略文件零改动：git 状态只允许出现本任务新增/修改文件。"""
        import subprocess as sp

        policy_dir = "src/hangma_bot/policy"
        diff = sp.run(
            ["git", "diff", "--name-only", "HEAD", "--", policy_dir],
            capture_output=True,
            text=True,
        )
        if diff.returncode != 0:
            pytest.skip("git 不可用，跳过工作区断言")
        modified = {line.strip() for line in diff.stdout.splitlines() if line.strip()}
        # R2 返工（S2/S5）获准修改 action_value 接缝文件族与受控接口
        # （score_trace）；executor.py 由 R1（S1 计费修复）并行修改；
        # AGENTS.md 是模块文档（完成度评审更新）。旧策略文件
        # （heuristic*/safe_fallback 等）仍零改动。
        allowed = {
            "src/hangma_bot/policy/__init__.py",
            "src/hangma_bot/policy/AGENTS.md",
            "src/hangma_bot/policy/interface.py",
            "src/hangma_bot/policy/action_value.py",
            "src/hangma_bot/policy/action_value_executor.py",
            "src/hangma_bot/policy/action_value_policy.py",
            "src/hangma_bot/policy/action_value_seeds.py",
            # 2026-09-22：R18 P37 新增冻结活动研究父代注册表；只供离线组合根。
            "src/hangma_bot/policy/research_candidates.py",
            # 2026-09-21：R17 在冻结公开后继/叶执行合同之上新增薄策略包装器；
            # 只重排既有合法弃牌位置，任一缺口原样回退 V2。
            "src/hangma_bot/policy/public_successor_policy.py",
            # 2026-09-18：`weights_v1.py` 末尾新增 modul 级常量 V2_PARAM_BATCH_WEIGHTS
            # （`v2_hu_upgrade_v2` 的载体）。纯新增、未被任何既有策略引用，
            # DEFAULT_WEIGHTS_V1 取值逐字不变；字节冻结契约已同步更新哈希并追加
            # behavior_neutral_evidence（tests/offline/evidence/v1-acceptance-2026-09-06/freeze.json）。
            "src/hangma_bot/policy/weights_v1.py",
        }
        unexpected = modified - allowed
        assert not unexpected, "旧策略文件被意外修改：{0}".format(sorted(unexpected))
        status = sp.run(
            ["git", "status", "--porcelain", "--", policy_dir],
            capture_output=True,
            text=True,
        )
        new_files = {
            line[3:].strip()
            for line in status.stdout.splitlines()
            if line.startswith("??")
        }
        # 新模块须在执行本回归前纳入提交集合，避免未跟踪源码绕过上方白名单。
        expected_new: set[str] = set()
        assert new_files == expected_new


# ---------------------------------------------------------------------------
# T06：失败合同——绝不部分补零
# ---------------------------------------------------------------------------


ABSTAIN_RESULT: Mapping[str, Any] = {"status": "ABSTAIN", "reason": "缺必需字段 combined_shanten"}


class TestT06BatchFailureContract:
    def test_raising_candidate_fails_whole_batch(self) -> None:
        def boom(_view: Mapping[str, Any]) -> Mapping[str, Any]:
            raise RuntimeError("候选崩溃")

        with pytest.raises(ValueError, match="候选执行失败"):
            run_scoring_skeleton(build_sample_view(), boom)

    def test_executor_candidate_runtime_error_becomes_value_error(self) -> None:
        source = (
            "def score_actions(view):\n"
            "    return view['missing_key']\n"
        )
        executor = ActionValueExecutor(source, name="raise-sample")
        with pytest.raises(ValueError, match="候选执行失败"):
            executor.score(build_sample_view())

    def test_division_by_zero_fails_batch(self) -> None:
        source = (
            "def score_actions(view):\n"
            "    ratio = 1 / 0\n"
            "    return {'status': 'ABSTAIN', 'reason': 'unreachable'}\n"
        )
        executor = ActionValueExecutor(source, name="div-zero")
        with pytest.raises(ValueError, match="ZeroDivisionError"):
            executor.score(build_sample_view())

    def test_overlong_for_loop_raises_workload_exceeded(self) -> None:
        """受限子集禁 while；用超长 for 构造 100k+ 操作也必须立即终止。"""
        source = (
            "def score_actions(view):\n"
            "    for i in range(200000):\n"
            "        pass\n"
            "    return {'status': 'ABSTAIN', 'reason': 'dead-loop'}\n"
        )
        executor = ActionValueExecutor(source, name="dead-loop")
        with pytest.raises(WorkloadExceeded, match="计数操作超限"):
            executor.score(build_sample_view())
        # S1：range(200000) 在构造期即按长度计满 200000，循环根本未开始。
        assert executor.last_operation_count == 200000

    def test_workload_exceeded_is_uncatchable_by_exception(self) -> None:
        assert not issubclass(WorkloadExceeded, Exception)
        assert issubclass(WorkloadExceeded, BaseException)
        with pytest.raises(WorkloadExceeded):
            try:
                raise WorkloadExceeded("test")
            except Exception:  # noqa: BLE001 - 验证候选侧 except Exception 捕不到
                pytest.fail("except Exception 不应捕获 WorkloadExceeded")

    def test_bare_except_rejected_statically(self) -> None:
        source = (
            "def score_actions(view):\n"
            "    try:\n"
            "        return view\n"
            "    except:\n"
            "        return {'status': 'ABSTAIN', 'reason': 'never'}\n"
        )
        with pytest.raises(StaticCheckError, match="try/except"):
            ActionValueExecutor(source, name="bare-except")

    def test_nan_score_fails_whole_batch(self) -> None:
        view = build_sample_view()
        result = {
            "status": "SCORED",
            "entries": [
                {"action_key": key, "score": float("nan"), "trace": {}}
                for key in view.expected_action_keys()
            ],
            "reason": None,
        }
        with pytest.raises(ValueError, match="有限"):
            run_scoring_skeleton(view, _plain_candidate(result))

    def test_infinite_score_fails_whole_batch(self) -> None:
        view = build_sample_view()
        result = {
            "status": "SCORED",
            "entries": [
                {"action_key": key, "score": float("inf"), "trace": {}}
                for key in view.expected_action_keys()
            ],
            "reason": None,
        }
        with pytest.raises(ValueError, match="有限"):
            run_scoring_skeleton(view, _plain_candidate(result))

    def test_bool_score_rejected(self) -> None:
        view = build_sample_view()
        result = {
            "status": "SCORED",
            "entries": [
                {"action_key": key, "score": True, "trace": {}}
                for key in view.expected_action_keys()
            ],
            "reason": None,
        }
        with pytest.raises(ValueError, match="布尔"):
            run_scoring_skeleton(view, _plain_candidate(result))

    def test_missing_action_fails_no_zero_fill(self) -> None:
        view = build_sample_view()
        keys = list(view.expected_action_keys())
        result = {
            "status": "SCORED",
            "entries": [
                {"action_key": key, "score": 1.0, "trace": {}} for key in keys[:-1]
            ],
            "reason": None,
        }
        with pytest.raises(ValueError, match="遗漏"):
            run_scoring_skeleton(view, _plain_candidate(result))

    def test_duplicate_action_fails(self) -> None:
        view = build_sample_view()
        keys = list(view.expected_action_keys())
        entries = [{"action_key": key, "score": 1.0, "trace": {}} for key in keys]
        entries.append({"action_key": keys[0], "score": 2.0, "trace": {}})
        with pytest.raises(ValueError, match="重复"):
            run_scoring_skeleton(view, _plain_candidate({"status": "SCORED", "entries": entries}))

    def test_unknown_action_key_fails(self) -> None:
        view = build_sample_view()
        entries = [
            {"action_key": key, "score": 1.0, "trace": {}}
            for key in view.expected_action_keys()
        ]
        entries.append({"action_key": "bogus:action", "score": 9.0, "trace": {}})
        with pytest.raises(ValueError, match="越界"):
            run_scoring_skeleton(view, _plain_candidate({"status": "SCORED", "entries": entries}))

    def test_single_oversize_trace_string_fails(self) -> None:
        view = build_sample_view()
        entries = [
            {"action_key": key, "score": 1.0, "trace": {"blob": "x" * 5000}}
            for key in view.expected_action_keys()
        ]
        with pytest.raises(ValueError, match="字符串"):
            run_scoring_skeleton(view, _plain_candidate({"status": "SCORED", "entries": entries}))

    def test_trace_batch_bytes_over_limit_fails(self) -> None:
        view = build_sample_view()
        entries = [
            {
                "action_key": key,
                "score": 1.0,
                "trace": {"k{0}".format(i): "v" * 1000 for i in range(40)},
            }
            for key in view.expected_action_keys()
        ]
        with pytest.raises(ValueError, match="32"):
            run_scoring_skeleton(view, _plain_candidate({"status": "SCORED", "entries": entries}))

    def test_abstain_path_carries_reason(self) -> None:
        batch = run_scoring_skeleton(build_sample_view(), _plain_candidate(ABSTAIN_RESULT))
        assert batch.status == "ABSTAIN"
        assert batch.entries == ()
        assert batch.reason == "缺必需字段 combined_shanten"
        assert batch_to_ranked_candidates(batch, build_sample_view().actions) == ()

    def test_abstain_without_reason_fails(self) -> None:
        with pytest.raises(ValueError, match="reason"):
            run_scoring_skeleton(
                build_sample_view(), _plain_candidate({"status": "ABSTAIN", "reason": ""})
            )

    def test_abstain_with_entries_fails(self) -> None:
        result = {
            "status": "ABSTAIN",
            "reason": "x",
            "entries": [{"action_key": "hu", "score": 1.0, "trace": {}}],
        }
        with pytest.raises(ValueError, match="不得携带"):
            run_scoring_skeleton(build_sample_view(), _plain_candidate(result))

    def test_non_dict_return_fails(self) -> None:
        with pytest.raises(ValueError, match="映射"):
            run_scoring_skeleton(build_sample_view(), lambda _v: "SCORED")

    def test_unknown_status_fails(self) -> None:
        with pytest.raises(ValueError, match="status"):
            run_scoring_skeleton(
                build_sample_view(), _plain_candidate({"status": "PARTIAL", "reason": "x"})
            )

    def test_entry_missing_fields_fails(self) -> None:
        view = build_sample_view()
        entries = [{"action_key": key, "score": 1.0} for key in view.expected_action_keys()]
        with pytest.raises(ValueError, match="action_key/score/trace"):
            run_scoring_skeleton(view, _plain_candidate({"status": "SCORED", "entries": entries}))

    def test_int_score_is_accepted_as_float(self) -> None:
        view = build_sample_view()
        entries = [
            {"action_key": key, "score": 2, "trace": {}}
            for key in view.expected_action_keys()
        ]
        batch = run_scoring_skeleton(view, _plain_candidate({"status": "SCORED", "entries": entries}))
        assert all(entry.score == 2.0 and isinstance(entry.score, float) for entry in batch.entries)

    def test_empty_action_table_rejected_before_candidate(self) -> None:
        view = _make_view(())
        with pytest.raises(ValueError, match="动作表为空"):
            run_scoring_skeleton(view, _plain_candidate(ABSTAIN_RESULT))


# ---------------------------------------------------------------------------
# 静态子集检查负例：每条禁令至少一个拒绝样例
# ---------------------------------------------------------------------------

_STATIC_NEGATIVES: Dict[str, str] = {
    "while": """def score_actions(view):
    while True:
        pass
    return {}
""",
    "import": """import math

def score_actions(view):
    return {}
""",
    "import-from": """from math import log

def score_actions(view):
    return {}
""",
    "self-recursion": """def score_actions(view):
    return score_actions(view)
""",
    "mutual-recursion": """def helper_a(view):
    return helper_b(view)

def helper_b(view):
    return helper_a(view)

def score_actions(view):
    return helper_a(view)
""",
    "getattr": """def score_actions(view):
    return getattr(view, 'keys')
""",
    "setattr-attribute-store": """def score_actions(view):
    view.get = 1
    return {}
""",
    "dunder-attribute": """def score_actions(view):
    return view.__class__
""",
    "forbidden-method": """def score_actions(view):
    return '{0}'.format(1)
""",
    "eval-name": """def score_actions(view):
    return eval('1')
""",
    "exec-name": """def score_actions(view):
    return exec('x = 1')
""",
    "compile-name": """def score_actions(view):
    return compile('1', 'x', 'eval')
""",
    "import-dunder": """def score_actions(view):
    return __import__('math')
""",
    "open-name": """def score_actions(view):
    return open('/etc/passwd')
""",
    "big-int-constant": """def score_actions(view):
    x = 123456789012345678901234567890
    return {}
""",
    "infinite-float-constant": """def score_actions(view):
    x = 1e400
    return {}
""",
    "pow-exponent-too-large": """def score_actions(view):
    x = 2 ** 64
    return {}
""",
    "pow-variable-exponent": """def score_actions(view):
    p = 2
    x = 3 ** p
    return {}
""",
    "yield": """def score_actions(view):
    yield 1
""",
    "generator-expression": """def score_actions(view):
    x = (i for i in [1])
    return {}
""",
    "global-stmt": """def score_actions(view):
    global x
    return {}
""",
    "nonlocal-stmt": """def score_actions(view):
    def inner():
        nonlocal view
        return view
    return inner()
""",
    "bare-except": """def score_actions(view):
    try:
        x = 1
    except:
        x = 2
    return {}
""",
    "except-exception": """def score_actions(view):
    try:
        x = 1
    except Exception:
        x = 2
    return {}
""",
    "except-base-exception": """def score_actions(view):
    try:
        x = 1
    except BaseException:
        x = 2
    return {}
""",
    "try-finally": """def score_actions(view):
    try:
        x = 1
    finally:
        x = 2
    return {}
""",
    "del-stmt": """def score_actions(view):
    x = 1
    del x
    return {}
""",
    "with-stmt": """def score_actions(view):
    with open('x') as f:
        x = f
    return {}
""",
    "raise-stmt": """def score_actions(view):
    raise ValueError(1)
""",
    "assert-stmt": """def score_actions(view):
    assert True
    return {}
""",
    "class-def": """class Helper:
    pass

def score_actions(view):
    return {}
""",
    "subscript-store": """def score_actions(view):
    view['a'] = 1
    return {}
""",
    "starred-arg": """def score_actions(view):
    x = [*[1]]
    return {}
""",
    "dict-double-star": """def score_actions(view):
    d = {**view}
    return d
""",
    "walrus": """def score_actions(view):
    y = 1 if (x := 2) else 3
    return {}
""",
    "lambda-default": """def score_actions(view):
    g = lambda x=1: x
    return {}
""",
    "underscore-name": """def score_actions(view):
    return _av_pass
""",
    "async-function": """async def score_actions(view):
    return {}
""",
    "annotation": """def score_actions(view):
    x: int = 1
    return {}
""",
    "function-annotation": """def score_actions(view) -> dict:
    return {}
""",
    "default-arg": """def score_actions(view, extra=1):
    return {}
""",
    "wrong-signature": """def score_actions(v):
    return {}
""",
    "missing-score-actions": """def helper(view):
    return {}
""",
    "module-level-call": """X = len('abc')

def score_actions(view):
    return {}
""",
    "module-level-list": """CACHE = []

def score_actions(view):
    return {}
""",
    "module-level-dict": """TABLE = {"a": 1}

def score_actions(view):
    return {}
""",
    "module-level-set": """SEEN = {1, 2}

def score_actions(view):
    return {}
""",
    "module-level-non-constant": """X = [1, 2] + [3]

def score_actions(view):
    return {}
""",
    "decorator": """def wrap(fn):
    return fn

@wrap
def score_actions(view):
    return {}
""",
    "await": """def score_actions(view):
    x = await view
    return {}
""",
    "bytes-constant": """def score_actions(view):
    b = b'x'
    return {}
""",
}


@pytest.mark.parametrize("case", sorted(_STATIC_NEGATIVES), ids=sorted(_STATIC_NEGATIVES))
def test_static_check_rejects_forbidden_construct(case: str) -> None:
    with pytest.raises(StaticCheckError):
        ActionValueExecutor(_STATIC_NEGATIVES[case], name="negative-" + case)


def test_static_check_allows_lambda_and_helpers() -> None:
    """白名单内的 lambda 与无递归辅助函数必须可用（种子依赖）。"""
    source = """LIMIT = 10

def double(x):
    return x * 2

def score_actions(view):
    values = map(double, [1, 2, 3])
    picked = sorted(values, key=lambda v: 0 - v)
    total = sum(picked)
    return {'status': 'ABSTAIN', 'reason': 'allowed'}
"""
    executor = ActionValueExecutor(source, name="positive-lambda")
    assert executor.score(build_sample_view()).status == "ABSTAIN"


# ---------------------------------------------------------------------------
# 计费正确性
# ---------------------------------------------------------------------------


class TestMetering:
    def test_loop_and_arithmetic_metered_exactly(self) -> None:
        source = (
            "def score_actions(view):\n"
            "    total = 0\n"
            "    for i in range(50):\n"
            "        total = total + i\n"
            "    return {'status': 'ABSTAIN', 'reason': 'meter'}\n"
        )
        executor = ActionValueExecutor(source, name="meter-loop")
        executor.score(build_sample_view())
        # range：调用点 1 + 按长度计费 50（S1：range 本身按长度计费）；
        # 迭代 50×1；加法 50×1；返回字典字面量 2；
        # R9/S1b：候选返回值本身按结构单元计费 5（dict 1 + 'status'/值 2 +
        # 'reason'/值 2）——该通道此前免费，现与其它结构遍历同口径。
        assert executor.last_operation_count == 1 + 50 + 50 + 50 + 2 + 5

    def test_sum_and_sorted_charged_by_input_length(self) -> None:
        source = (
            "def score_actions(view):\n"
            "    data = [1, 2, 3, 4, 5]\n"
            "    s = sum(data)\n"
            "    ordered = sorted(data)\n"
            "    return {'status': 'ABSTAIN', 'reason': 'meter'}\n"
        )
        executor = ActionValueExecutor(source, name="meter-builtin")
        executor.score(build_sample_view())
        # 列表字面量 5；sum 调用点 1 + 长度 5；sorted 调用点 1 + 长度 5；字典 2；
        # R9/S1b：候选返回值结构单元 5。
        assert executor.last_operation_count == 5 + 6 + 6 + 2 + 5

    def test_len_charged_one_per_call(self) -> None:
        source = (
            "def score_actions(view):\n"
            "    n = len(view['actions'])\n"
            "    return {'status': 'ABSTAIN', 'reason': 'len'}\n"
        )
        executor = ActionValueExecutor(source, name="meter-len")
        executor.score(build_sample_view())
        # len 调用点 1 + 内建 1 + 字典 2 + 返回值结构单元 5（R9/S1b）。
        assert executor.last_operation_count == 4 + 5

    def test_collection_size_cap(self) -> None:
        source = (
            "def score_actions(view):\n"
            "    big = list(range(5000))\n"
            "    return {'status': 'ABSTAIN', 'reason': 'cap'}\n"
        )
        executor = ActionValueExecutor(source, name="meter-cap")
        with pytest.raises(WorkloadExceeded, match="4096"):
            executor.score(build_sample_view())

    def test_append_growth_capped(self) -> None:
        source = (
            "def score_actions(view):\n"
            "    rows = []\n"
            "    for i in range(5000):\n"
            "        rows.append(i)\n"
            "    return {'status': 'ABSTAIN', 'reason': 'append'}\n"
        )
        executor = ActionValueExecutor(source, name="meter-append")
        with pytest.raises(WorkloadExceeded):
            executor.score(build_sample_view())

    def test_runtime_big_int_rejected(self) -> None:
        source = (
            "def score_actions(view):\n"
            "    big = 9223372036854775807\n"
            "    huge = big + big\n"
            "    return {'status': 'ABSTAIN', 'reason': 'bigint'}\n"
        )
        executor = ActionValueExecutor(source, name="bigint-runtime")
        with pytest.raises(WorkloadExceeded, match="63 位"):
            executor.score(build_sample_view())

    def test_infinite_float_conversion_rejected(self) -> None:
        source = (
            "def score_actions(view):\n"
            "    f = float('inf')\n"
            "    return {'status': 'ABSTAIN', 'reason': 'inf'}\n"
        )
        executor = ActionValueExecutor(source, name="float-inf")
        with pytest.raises(WorkloadExceeded, match="非有限"):
            executor.score(build_sample_view())

    def test_string_repeat_overflow_rejected(self) -> None:
        source = (
            "def score_actions(view):\n"
            "    s = 'x' * 70000\n"
            "    return {'status': 'ABSTAIN', 'reason': 'str'}\n"
        )
        executor = ActionValueExecutor(source, name="str-overflow")
        with pytest.raises(WorkloadExceeded, match="重复"):
            executor.score(build_sample_view())

    def test_meter_resets_between_scores(self) -> None:
        view = build_sample_view()
        executor = build_action_value_policy("efficiency_seed")._executor
        executor.score(view)
        first = executor.last_operation_count
        executor.score(view)
        second = executor.last_operation_count
        assert first is not None
        assert first == second  # 同视图两次执行计数一致（计数器已复位）


# ---------------------------------------------------------------------------
# RankedCandidate 适配与身份
# ---------------------------------------------------------------------------


class TestAdaptationAndIdentity:
    def test_rank_invariants(self) -> None:
        view = _conflict_view()
        batch = build_action_value_policy("route_value_seed").score(view)
        ranked = batch_to_ranked_candidates(batch, view.actions)
        assert [c.rank for c in ranked] == list(range(1, len(ranked) + 1))
        keys = [c.action_key for c in ranked]
        scores = [_scores_by_key(batch)[k] for k in keys]
        assert scores == sorted(scores, reverse=True)
        for candidate in ranked:
            assert candidate.total_score == pytest.approx(
                sum(part.value for part in candidate.score_parts)
            )
            assert len(candidate.score_parts) == 1
            assert candidate.score_parts[0].name == "action_value_v1"
            assert candidate.reasons

    def test_tie_broken_by_action_key_ascending(self) -> None:
        view = build_sample_view()
        result = {
            "status": "SCORED",
            "entries": [
                {"action_key": key, "score": 5.0, "trace": {}}
                for key in view.expected_action_keys()
            ],
            "reason": None,
        }
        batch = run_scoring_skeleton(view, _plain_candidate(result))
        ranked = batch_to_ranked_candidates(batch, view.actions)
        assert [c.action_key for c in ranked] == sorted(view.expected_action_keys())

    def test_identity_deterministic_and_sensitive(self) -> None:
        base = dict(
            source="def score_actions(view):\n    return {}\n",
            contract_sha256="a" * 64,
            params={"weights": [1, 2]},
            executor_version="action-value-executor/1",
            deps_digest=compute_deps_digest(),
        )
        identity = compute_candidate_identity(**base)
        assert identity == compute_candidate_identity(**base)
        assert len(identity) == 64
        changed = {
            "source": "def score_actions(view):\n    return 1\n",
            "params": {"weights": [1, 3]},
            "contract_sha256": "b" * 64,
            "executor_version": "action-value-executor/2",
            "deps_digest": "0" * 64,
        }
        for field, value in changed.items():
            variant = dict(base)
            variant[field] = value
            assert compute_candidate_identity(**variant) != identity, field

    def test_deps_digest_deterministic(self) -> None:
        assert compute_deps_digest() == compute_deps_digest()

    def test_scorer_candidate_identity(self) -> None:
        scorer = build_action_value_policy("efficiency_seed")
        first = scorer.candidate_identity("c" * 64)
        second = scorer.candidate_identity("c" * 64)
        assert first == second
        other = build_action_value_policy("route_value_seed").candidate_identity("c" * 64)
        assert first != other

    def test_unknown_seed_name_rejected(self) -> None:
        with pytest.raises(ValueError, match="未知 action_value 种子名"):
            build_action_value_policy("no_such_seed")

    def test_self_check_passes_for_all_seeds(self) -> None:
        assert self_check() == {name: "ok" for name in SEED_NAMES}


# ---------------------------------------------------------------------------
# 类型与只读投影
# ---------------------------------------------------------------------------


class TestScoringViewContract:
    def test_actions_must_be_sorted_strictly(self) -> None:
        actions = tuple(reversed(build_sample_view().actions))
        with pytest.raises(ValueError, match="严格升序"):
            ScoringView(
                schema_version=SCORING_VIEW_SCHEMA_VERSION,
                visible_state=build_sample_view().visible_state,
                actions=actions,
                analysis_profile=build_sample_view().analysis_profile,
            )

    def test_wrong_schema_version_rejected(self) -> None:
        # 旧结构版本（P11b 前的 /1）在新常量下必须被拒；反例值随版本升位而更新。
        with pytest.raises(ValueError, match="schema_version"):
            ScoringView(
                schema_version="sitin-scoring-view/1",
                visible_state=build_sample_view().visible_state,
                actions=build_sample_view().actions,
                analysis_profile=build_sample_view().analysis_profile,
            )

    def test_action_key_consistency_enforced(self) -> None:
        good = build_sample_view().actions[0]
        with pytest.raises(ValueError, match="不一致"):
            ActionView(
                action_key="discard:9w",
                action=good.action,
                action_type="discard",
                is_legal=True,
            )

    def test_read_only_accessors(self) -> None:
        view = build_sample_view()
        assert view.hand_codes()[0] == "1w"
        assert view.seat_index() == 0
        assert view.wall_remaining() == 60
        assert view.table_scores() == (0, 0, 0, 0)
        assert view.phase() == "draw"

    def test_competition_view_optional_defaults(self) -> None:
        assert CompetitionView().stage_scores is None
        assert CompetitionView().table_scores is None
        assert CompetitionView().freshness_masks is None
        with pytest.raises(ValueError):
            CompetitionView(stage_scores=(1, 2, 3))

    def test_candidate_view_branch_object_passthrough(self) -> None:
        """B1 未合入前，followup_branches 支持任意对象透传（别名键映射）。"""

        class FakeFollowup:
            followup_key = "discard:1w"
            combined_shanten = 2
            support_remaining = 3

        actions = (
            ActionView(
                action_key="pass",
                action=Pass(),
                action_type="pass",
                is_legal=True,
                followup_branches=(FakeFollowup(),),
            ),
        )
        view = _make_view(actions)
        mapping = view.candidate_view()
        branch = mapping["actions"][0]["followup_branches"][0]
        assert branch["followup_key"] == "discard:1w"
        assert branch["combined_shanten"] == 2
        assert branch["support_remaining"] == 3

    def test_batch_equality_and_immutability(self) -> None:
        batch = ScoreBatch(
            status="SCORED",
            entries=(ActionScore(action_key="hu", score=1.0, trace={"a": 1}),),
        )
        with pytest.raises(Exception):
            batch.status = "ABSTAIN"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# R1（2026-09-17）：S1 计费绕过/跨调用状态、S3 赛事配置越界、S4 内容身份
# ---------------------------------------------------------------------------


MIN_RANGE_SOURCE = (
    "def score_actions(view):\n"
    "    x = min(range(1000000))\n"
    "    return {'status': 'ABSTAIN', 'reason': 'probe'}\n"
)


class TestR1S1BillingBypassClosed:
    """评审 S1 反例改造为正式回归：两个反例必须被拒绝或有界终止。"""

    def test_min_over_million_range_rejected_under_tiny_budget(self) -> None:
        executor = ActionValueExecutor(MIN_RANGE_SOURCE, max_operations=100)
        with pytest.raises(WorkloadExceeded, match="计数操作超限"):
            executor.score(build_sample_view())
        # range 构造期即按长度计满——真实遍历从未发生。
        assert executor.last_operation_count == 1_000_000

    def test_max_and_sum_over_large_range_rejected(self) -> None:
        for expr in ("max(range(500000))", "sum(range(500000))", "all(range(500000))"):
            source = (
                "def score_actions(view):\n"
                "    x = {0}\n"
                "    return {{'status': 'ABSTAIN', 'reason': 'probe'}}\n".format(expr)
            )
            executor = ActionValueExecutor(source, max_operations=1000)
            with pytest.raises(WorkloadExceeded):
                executor.score(build_sample_view())

    def test_module_level_cache_list_rejected(self) -> None:
        source = (
            "CACHE = []\n"
            "\n"
            "def score_actions(view):\n"
            "    CACHE.append(1)\n"
            "    return {'status': 'ABSTAIN', 'reason': 'cache'}\n"
        )
        with pytest.raises(StaticCheckError, match="跨调用可变状态"):
            ActionValueExecutor(source)

    def test_repeat_calls_stay_stateless(self) -> None:
        source = (
            "LIMITS = (3, 5)\n"
            "\n"
            "def score_actions(view):\n"
            "    total = 0\n"
            "    for cap in LIMITS:\n"
            "        total = total + cap\n"
            "    entries = []\n"
            "    for action in view['actions']:\n"
            "        entries.append({'action_key': action['action_key'], 'score': total * 1.0, 'trace': {}})\n"
            "    return {'status': 'SCORED', 'entries': entries}\n"
        )
        executor = ActionValueExecutor(source)
        view = build_sample_view()
        first = executor.score(view)
        second = executor.score(view)
        assert first == second

    def test_module_mutation_detected_across_calls(self) -> None:
        """防御性验证：装载后命名空间若被外部篡改，执行后复核必须拒绝。"""
        source = (
            "T = (1, 2)\n"
            "\n"
            "def score_actions(view):\n"
            "    return {'status': 'ABSTAIN', 'reason': 'x'}\n"
        )
        executor = ActionValueExecutor(source)
        executor.score(build_sample_view())
        executor._namespace["T"] = (9, 9)  # 模拟跨调用状态注入
        with pytest.raises(WorkloadExceeded, match="跨调用状态"):
            executor.score(build_sample_view())

    def test_count_index_billed_by_length(self) -> None:
        source = (
            "def score_actions(view):\n"
            "    s = 'x' * 5000\n"
            "    n = s.count('x')\n"
            "    return {'status': 'ABSTAIN', 'reason': 'count'}\n"
        )
        executor = ActionValueExecutor(source, max_operations=100)
        with pytest.raises(WorkloadExceeded):
            executor.score(build_sample_view())

    def test_enumerate_map_zip_inputs_bounded(self) -> None:
        source = (
            "def score_actions(view):\n"
            "    pairs = list(enumerate(range(5000)))\n"
            "    return {'status': 'ABSTAIN', 'reason': 'enumerate'}\n"
        )
        executor = ActionValueExecutor(source)
        with pytest.raises(WorkloadExceeded, match="4096"):
            executor.score(build_sample_view())

    def test_min_max_multi_argument_form_still_allowed(self) -> None:
        source = (
            "def score_actions(view):\n"
            "    m = min(3, 1, 2)\n"
            "    m2 = max(1, 4, 2)\n"
            "    return {'status': 'ABSTAIN', 'reason': 'multi'}\n"
        )
        executor = ActionValueExecutor(source)
        assert executor.score(build_sample_view()).status == "ABSTAIN"

    def test_slice_results_keep_collection_cap(self) -> None:
        source = (
            "def score_actions(view):\n"
            "    base = list(range(10))\n"
            "    grown = base[0:1]\n"
            "    for i in range(4100):\n"
            "        grown.append(i)\n"
            "    return {'status': 'ABSTAIN', 'reason': 'slice'}\n"
        )
        executor = ActionValueExecutor(source)
        with pytest.raises(WorkloadExceeded):
            executor.score(build_sample_view())


class TestR1S1TimingAndFallback:
    """超量不阻塞原动作窗口；失败后紧急保底仍可用；最大输入有界完成。"""

    def test_overwork_rejected_fast_and_emergency_still_available(self) -> None:
        from time import perf_counter

        from hangma_bot.hangma.engine import HangmaRules
        from hangma_bot.kernel.config import RuleConfig

        executor = ActionValueExecutor(MIN_RANGE_SOURCE)  # 默认 100k 预算
        started = perf_counter()
        with pytest.raises(WorkloadExceeded):
            executor.score(build_sample_view())
        elapsed_ms = (perf_counter() - started) * 1000.0
        assert elapsed_ms < 2000.0, "超量拒绝必须立即完成，不得阻塞动作窗口"
        # 原动作窗口保底：候选整批失效后紧急动作路径独立可用。
        rules = HangmaRules(RuleConfig("v26", 1, False))
        observation = build_sample_view().visible_state
        assert rules.emergency_action(observation) is not None

    def test_max_input_view_scores_bounded(self) -> None:
        from time import perf_counter

        from hangma_bot.kernel.actions import (
            CANONICAL_TILE_ORDER,
            Chi,
            Discard,
            Hu,
            Pass,
            Peng,
            Tile,
        )

        def branches_for(prefix: str) -> tuple:
            return tuple(
                {
                    "followup_key": "{0}-b{1}".format(prefix, branch),
                    "combined_shanten": branch % 4,
                    "support_remaining": branch % 9,
                    "fan": branch % 33,
                }
                for branch in range(128)
            )

        actions = [
            ActionView(
                action_key="discard:{0}".format(code),
                action=Discard(tile=Tile(code)),
                action_type="discard",
                is_legal=True,
                followup_branches=branches_for(code),
                family_progress="ADVANCE",
            )
            for code in CANONICAL_TILE_ORDER
        ]
        actions.append(
            ActionView(action_key="hu", action=Hu(), action_type="hu", is_legal=True,
                       followup_branches=branches_for("hu"), family_progress="CLOSE"))
        actions.append(
            ActionView(action_key="pass", action=Pass(), action_type="pass",
                       is_legal=True, followup_branches=branches_for("pass"),
                       family_progress="SAME"))
        for code in ("1w", "3w", "5w"):
            actions.append(
                ActionView(
                    action_key="peng:{0}".format(code),
                    action=Peng(tile=Tile(code)),
                    action_type="peng",
                    is_legal=True,
                    followup_branches=branches_for("peng" + code),
                    family_progress="ADVANCE",
                )
            )
        for start in ("1w", "4w", "7w"):
            index = CANONICAL_TILE_ORDER.index(start)
            tiles = (
                Tile(CANONICAL_TILE_ORDER[index]),
                Tile(CANONICAL_TILE_ORDER[index + 1]),
                Tile(CANONICAL_TILE_ORDER[index + 2]),
            )
            actions.append(
                ActionView(
                    action_key="chi:{0}".format(",".join(t.code for t in tiles)),
                    action=Chi(tiles=tiles),
                    action_type="chi",
                    is_legal=True,
                    followup_branches=branches_for("chi" + start),
                    family_progress="ADVANCE",
                )
            )
        base = build_sample_view()
        view = ScoringView(
            schema_version=SCORING_VIEW_SCHEMA_VERSION,
            visible_state=base.visible_state,
            actions=tuple(sorted(actions, key=lambda item: item.action_key)),
            analysis_profile=base.analysis_profile,
        )
        assert len(view.actions) >= 40
        started = perf_counter()
        batch = build_action_value_policy("route_value_seed").score(view)
        elapsed_ms = (perf_counter() - started) * 1000.0
        assert batch.status == "SCORED"
        assert len(batch.entries) == len(view.actions)
        assert elapsed_ms < 2000.0, "最大输入（40+ 动作 × 128 分支）必须有界快速完成"


class TestR1S3ResearchTournamentBoundary:
    """研究策略与真实网络入口分离：三入口 + 测试房间一律拒绝。"""

    @pytest.mark.parametrize(
        "mode_name",
        ["OFFICIAL_TOURNAMENT", "TEST_TOURNAMENT", "AUTO_MATCH", "TEST_ROOM"],
    )
    def test_network_modes_reject_research_strategy(self, mode_name: str) -> None:
        from pathlib import Path

        from hangma_bot.bootstrap import RuntimeConfig, RuntimeMode, TokenKind

        mode = RuntimeMode[mode_name]
        token_kind = (
            TokenKind.OFFICIAL
            if mode in (RuntimeMode.OFFICIAL_TOURNAMENT, RuntimeMode.AUTO_MATCH)
            else TokenKind.TEST
        )
        with pytest.raises(ValueError, match="研究候选"):
            RuntimeConfig(
                mode=mode,
                base_url="https://example.invalid",
                expected_tournament_id="x",
                known_guide_version=29,
                token="not-a-real-token",
                token_kind=token_kind,
                audit_root=Path("/tmp/never"),
                strategy="action_value:efficiency_seed",
            )

    def test_research_names_not_in_available_strategies(self) -> None:
        from hangma_bot.bootstrap import AVAILABLE_STRATEGIES, RESEARCH_STRATEGY_NAMES

        assert not any(name.startswith("action_value:") for name in AVAILABLE_STRATEGIES)
        assert set(RESEARCH_STRATEGY_NAMES) == {
            "action_value:efficiency_seed",
            "action_value:route_value_seed",
            "action_value:hu_first_reference",
            "action_value:r18_two_wealth_baotou_v1",
        }

    def test_stable_strategies_still_configurable(self) -> None:
        from pathlib import Path

        from hangma_bot.bootstrap import (
            DEFAULT_STRATEGY,
            RuntimeConfig,
            RuntimeMode,
            TokenKind,
        )

        config = RuntimeConfig(
            mode=RuntimeMode.OFFICIAL_TOURNAMENT,
            base_url="https://example.invalid",
            expected_tournament_id="x",
            known_guide_version=29,
            token="not-a-real-token",
            token_kind=TokenKind.OFFICIAL,
            audit_root=Path("/tmp/never"),
            strategy=DEFAULT_STRATEGY,
        )
        assert config.strategy == DEFAULT_STRATEGY

    def test_research_entry_offline_only(self) -> None:
        from hangma_bot.bootstrap import build_research_policy
        from hangma_bot.policy.action_value_policy import ActionValuePolicy

        for name in (
            "action_value:efficiency_seed",
            "action_value:route_value_seed",
            "action_value:hu_first_reference",
            "action_value:r18_two_wealth_baotou_v1",
        ):
            policy = build_research_policy(name)
            assert isinstance(policy, ActionValuePolicy)
        with pytest.raises(ValueError, match="未知研究策略名"):
            build_research_policy("action_value:unknown")


class TestR1S4ContentBoundIdentity:
    """身份绑定实际第一方实现：只改方法体也必须改变 candidate_id。"""

    def test_first_party_modules_all_importable(self) -> None:
        import importlib

        from hangma_bot.policy.action_value_executor import FIRST_PARTY_DIGEST_MODULES

        assert len(FIRST_PARTY_DIGEST_MODULES) >= 5
        for dotted in FIRST_PARTY_DIGEST_MODULES:
            assert importlib.import_module(dotted) is not None

    def test_deps_digest_binds_actual_file_contents(self) -> None:
        import importlib.util
        from pathlib import Path

        from hangma_bot.policy.action_value_executor import (
            compute_deps_digest,
            compute_first_party_digest,
        )

        structural = compute_deps_digest()
        contents = {}
        for dotted in ("hangma_bot.policy.action_value", "hangma_bot.policy.action_value_executor"):
            spec = importlib.util.find_spec(dotted)
            contents[dotted] = Path(spec.origin).read_text(encoding="utf-8")
        bound = compute_deps_digest(contents)
        assert structural != bound
        # 只改一个文件的一个字符（等价于只改方法体）即失效。
        tweaked = dict(contents)
        first_key = next(iter(tweaked))
        tweaked[first_key] = tweaked[first_key] + "# body-only tweak\n"
        assert compute_deps_digest(tweaked) != bound
        assert compute_first_party_digest(tweaked) != compute_first_party_digest(contents)

    def test_executor_version_bumped_for_billing_change(self) -> None:
        from hangma_bot.policy.action_value_executor import EXECUTOR_VERSION

        # /2：R1 迭代入口与 range 按长度计费；
        # /3：R6/S1 方法别名、比较与成员查询、递归结构遍历纳入计费，
        #     新增嵌套深度/结构单元上限，格式宽度与精度改为分配前校验，
        #     集合迭代确定化——计费语义再变，旧 candidate_id 与准入失效。
        # /4：R8/N1—N3 原生哈希前置守卫（字典/集合字面量与推导式、set/
        #     frozenset/dict 构造、.add、深键查询）、序列起始值求和拒绝、
        #     字面量与推导式改确定元素流、链式比较临时名隔离——计费与语义
        #     第三次变更，旧 candidate_id 与准入记录再次失效。
        # /5（R9/S1）：结构遍历改为每个展开节点（含标量叶）各计 1 个单元、
        #     容器与标量叶同口径限额、共享引用按出现次数累积——宽而浅的共享
        #     结构不再只算容器数（原反例 (1,)*1024 复用 256 次由放行改为哈希
        #     前拒绝），计费与语义第四次变更，旧 candidate_id、旧准入记录与
        #     旧面板身份随之失效。理由与连带影响见
        #     evidence/v4-impl/r9-fixes/P1-exec/FIX-REPORT.md §版本判定。
        # /6（R9/S1b，独立对抗性验证收口）：集合式字典视图（dict_keys/
        #     dict_items/dict_values）纳入结构遍历、未知类型保守兜底（不再
        #     「未知 ⇒ 0」）、候选返回值（含 trace）按结构单元计费、字符串产出
        #     按 64 字符一段计费——第三形状反例（视图）与 trace 通道、字符串
        #     通道同时收口，计费与语义第五次变更，旧 candidate_id、旧准入记录
        #     与旧面板身份失效。证据见 evidence/v4-impl/r9-fixes/P1-exec/
        #     FIX-REPORT.md 与 P1-exec-verify/VERIFY-REPORT.md。
        assert EXECUTOR_VERSION == "action-value-executor/6"
