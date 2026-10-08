"""坐隐 3.0 阶段编排自测：**结论必须是可执行的断言**。

三条纪律（对齐 tools/test_sitin_phase3_facts.py 的写法）：

1. **官方规则必须逐条可执行**：名次分的并列平均、三键/单键排序、阶段清零、轮空、
   组内排名与组间隔离、决赛加赛——每条结论都用构造输入跑一遍，而不是写在散文里。
2. **计划核验必须先于排名**（REVIEW-8 R8-4）：缺行、非 complete、座位不符，
   都必须判**不可排序**；测试要证明"部分失败不会变成部分排名"。
3. **身份按 seed 与结构取哈希，不按标签**（REVIEW-8 R8-5）：改名不改身份、
   换种子必改身份，且与调度器的 root_set_id_of 同口径。

**构造集只证明编排语义与接线**，不构成任何效果证据；本文件不跑真实桌赛。
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
import math
import random
import shlex
import subprocess
import sys
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
_REPO = _PROJECT_ROOT
sys.path.insert(0, str(_project_file(_PROJECT_ROOT, _REPO / "src")))
sys.path.insert(0, str(_HERE))

stage = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/tools/sitin_stage.py')


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, _project_file(_PROJECT_ROOT, _HERE / (name + ".py")))
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


stage = _load("sitin_stage")
scheduler = _load("sitin_scheduler")

IDS9 = ["p0{0}".format(index) for index in range(1, 10)]


# ---------------------------------------------------------------------------
# 夹具构造
# ---------------------------------------------------------------------------


#: 合同冻结日期：测试里固定写死，证明合同与「生成当天」无关（复审 #16）。
FROZEN_AT = "2026-09-15"


def contract(**overrides):
    kwargs = {
        "ruleset_version": "test-ruleset",
        "base_score": 1,
        "you_cai_bi_kao": False,
        "rounds_per_game": 2,
        "frozen_at": FROZEN_AT,
    }
    kwargs.update(overrides)
    return stage.default_contract(**kwargs)


def synthetic_match_row(*, table_id, scores, seat_participants, scenario_id="s1t1-1"):
    """造一条契约 §7 的 MatchResult 行，用于重演对账的构造输入（不是真实桌赛）。"""

    from hangma_bot.kernel.config import RuleConfig, TimingConfig, TournamentConfig
    from hangma_bot.offline.evaluation_results import MatchResult

    return MatchResult(
        evaluation_schema_version=1, result_id="r-" + table_id, source_kind="simulation",
        scenario_id=scenario_id, pair_id=scenario_id + ":0123", game_key=None,
        config=TournamentConfig(max_games=1, rounds_per_game=2,
                                rules=RuleConfig(ruleset_version="test-ruleset", base_score=1,
                                                 you_cai_bi_kao=False),
                                timing=TimingConfig(peng_timeout_sec=1.0, chi_timeout_sec=1.0,
                                                    discard_timeout_sec=3.0)),
        policy_ids_by_seat=tuple(seat_participants), seat_permutation=(0, 1, 2, 3),
        expected_hands=2, completed_hands=2, scores_before=(0, 0, 0, 0),
        scores_after=tuple(scores), official_ranks=None, status="complete",
        invalid_reasons=(), runtime_counts=None,
        versions=(("ruleset_version", "test-ruleset"),), source_refs=())


def recorded_run_runner(recorded):
    """把**一份运行记录里的场次结果**当重演输入（负例回归用：复算源与被比对象同源可得）。"""

    def run_tables(plan):
        by_id = {str(table["plan"]["table_id"]): table for table in recorded["tables"]}
        outcomes = []
        for table in plan:
            entry = by_id.get(table.table_id)
            if entry is None:
                raise stage.StageFailed("缺少场次 " + table.table_id)
            outcome = entry["outcome"]
            outcomes.append(stage.TableOutcome(
                table_id=table.table_id, status=str(outcome["status"]),
                participant_ids_by_seat=tuple(outcome["participant_ids_by_seat"]),
                scores_by_seat=tuple(int(item) for item in outcome["scores_by_seat"]),
                source_kind=str(outcome.get("source_kind") or "fixture")))
        return outcomes

    return run_tables


def write_replay_inputs(tmp_path, *, scores_by_stage, broken=None):
    """造一对「run.json + tables.jsonl」，用于重演对账测试。

    返回 (run_path, tables_path, run)。tables.jsonl 由 run 的计划与**脚本分数**生成，
    因此两侧本来一致；测试通过分别篡改任一侧来验证对账是双向的。
    """

    run = run_orchestration(scores_by_stage=scores_by_stage)
    lines = []
    for table in run["tables"]:
        plan = table["plan"]
        outcome = table["outcome"]
        if broken and plan["table_id"] in broken:
            outcome = dict(outcome, scores_by_seat=[int(x) + 1 for x in outcome["scores_by_seat"]])
        row = synthetic_match_row(table_id=plan["table_id"],
                                  scores=outcome["scores_by_seat"],
                                  seat_participants=plan["seat_participants"],
                                  scenario_id=plan["scenario_id"])
        payload = dict(row.to_json())
        # 信封必须与生产写入器（_write_tables_jsonl）同形：少字段会被重演的 fail-closed 判出来。
        payload[stage.ROW_ENVELOPE_KEY] = {"schema": stage.RUN_SCHEMA,
                                           "table_id": plan["table_id"],
                                           "stage_no": plan["stage_no"],
                                           "group_index": plan.get("group_index"),
                                           "seed": plan["seed"],
                                           "scenario_id": plan["scenario_id"],
                                           "seat_participants": plan["seat_participants"],
                                           "wall_ms": 1.0}
        lines.append(json.dumps(payload, ensure_ascii=False))
    run_path = tmp_path / "run.json"
    run_path.write_text(json.dumps(run, ensure_ascii=False), encoding="utf-8")
    tables_path = tmp_path / "tables.jsonl"
    tables_path.write_text(chr(10).join(lines) + chr(10), encoding="utf-8")
    return run_path, tables_path, run


def participants(count: int):
    return stage.participants_for(count, "weighted_heuristic_v2")


def scripted_runner(scores_by_stage, *, overtime_delta=None, broken_tables=(), seat_bonus=None):
    """按 (阶段号 → {参赛者: 分数}) 出分；可注入坏场次（验证不可排序）。"""

    def run_tables(plan):
        outcomes = []
        bonus = list(seat_bonus or [0, 0, 0, 0])
        for table in plan:
            seats = table.seats()
            if table.table_id in broken_tables:
                outcomes.append(stage.TableOutcome(
                    table_id=table.table_id, status="error",
                    participant_ids_by_seat=seats, failure="注入的执行失败"))
                continue
            base = scores_by_stage.get(table.stage_no, {})
            scores = []
            for seat, participant in enumerate(seats):
                value = int(base[participant]) + int(bonus[seat])
                if table.stage_kind == "overtime":
                    value += int((overtime_delta or {}).get(participant, 0))
                scores.append(value)
            outcomes.append(stage.TableOutcome(
                table_id=table.table_id, status="complete", participant_ids_by_seat=seats,
                scores_by_seat=tuple(scores), source_kind="fixture"))
        return outcomes

    return run_tables


def run_orchestration(*, scores_by_stage, count=9, **contract_overrides):
    options = {"max_overtime": 3}
    options.update(contract_overrides)
    return stage.build_run(
        contract=contract(**options),
        participants=participants(count),
        runner=scripted_runner(scores_by_stage), mode="test")


# --- 1. 合同 -----------------------------------------------------------------


def test_default_contract_passes_validation():
    """★ 默认合同必须自洽：每个语义块有出处、unresolved 非空、档位表覆盖到位人数。"""

    assert stage.validate_contract(contract()) == []


def test_contract_requires_evidence_level_and_real_path():
    """provenance 必须指向真实存在的合同路径，且级别只能是四级之一。"""

    bad = contract()
    bad["provenance"]["batch.not_a_field"] = {"level": stage.LEVEL_OFFICIAL, "source": "x"}
    bad["provenance"]["panel"] = {"level": "看起来很确定", "source": "x"}
    problems = stage.validate_contract(bad)
    assert any("不存在" in item for item in problems), problems
    assert any("合法证据级别" in item for item in problems), problems


def test_contract_requires_unresolved_items():
    """★ 官方确实还有未确认项（正式赛事参数、god_count 不可复现）；写空等于掩盖。"""

    bad = contract()
    bad["unresolved"] = []
    assert any("unresolved" in item for item in stage.validate_contract(bad))


def test_contract_rejects_candidate_policy_names():
    """★ 面板策略必须来自冻结白名单：本包不允许通过合同引入候选。"""

    bad = contract()
    bad["panel"]["policy_pool"] = ["seven_pairs_path_value"]
    assert any("白名单" in item for item in stage.validate_contract(bad))
    with pytest.raises(ValueError):
        stage.participants_for(2, "seven_pairs_path_value")


def test_ladder_matches_the_official_bracket_table():
    """★ 档位表按到位人数定档（官方 §2），边界人数必须落在正确的档上。"""

    frozen = contract()
    assert [(item["min_participants"]) for item in frozen["ladder"]] == [17, 9, 5, 4]

    def names(count):
        return [spec["name"] for spec in stage.ladder_stages(frozen, count)]

    assert names(20) == ["海选", "16强", "8强", "决赛"]
    assert names(17) == ["海选", "16强", "8强", "决赛"]
    assert names(16) == ["海选", "8强", "决赛"]
    assert names(9) == ["海选", "8强", "决赛"]
    assert names(8) == ["海选资格轮", "决赛"]
    assert names(5) == ["海选资格轮", "决赛"]
    assert names(4) == ["决赛"]
    with pytest.raises(stage.StageVoid):
        stage.ladder_stages(frozen, 3)


def test_qualifying_target_follows_the_bracket():
    """海选取前 G 随档位变化（16 / 8 / 4），不是写死的 16。"""

    frozen = contract()
    for count, expected in ((20, 16), (16, 8), (5, 4)):
        first = stage.ladder_stages(frozen, count)[0]
        assert (first["kind"], first["target"]) == ("qualifying_global", expected)


# --- 2. 名次分 ---------------------------------------------------------------


def test_place_points_are_the_official_four_values():
    """不同分数时名次分是 +3 / +1 / −1 / −3（官方 §5.1）。"""

    assert stage.place_points_for_table([10, 5, 0, -5]) == (3, 1, -1, -3)


def test_tied_first_and_second_share_the_average():
    """★ 官方例子：第 1、2 名并列时各得 +2；第 3、4 名仍是 −1 / −3。"""

    assert stage.place_points_for_table([10, 10, 5, 0]) == (2, 2, -1, -3)


def test_tied_middle_pair_scores_zero_each():
    """第 2、3 名并列 ⇒ (+1 −1) / 2 = 0。"""

    assert stage.place_points_for_table([10, 5, 5, 0]) == (3, 0, 0, -3)


def test_tied_bottom_triple_shares_the_average():
    """第 2—4 名并列 ⇒ (+1 −1 −3) / 3 = −1。"""

    assert stage.place_points_for_table([10, 2, 2, 2]) == (3, -1, -1, -1)


def test_four_way_tie_scores_zero():
    """四人同分 ⇒ (3+1−1−3)/4 = 0 每人。"""

    assert stage.place_points_for_table([7, 7, 7, 7]) == (0, 0, 0, 0)


def test_place_points_reject_non_four_seat_vectors():
    """不是 4 个座位直接报错：**不四舍五入、不猜**。"""

    with pytest.raises(ValueError):
        stage.place_points_for_table([1, 2, 3])


# --- 3. 名次与排序键 ---------------------------------------------------------


def test_rank_uses_only_offline_reproducible_keys():
    """★ god_count 离线不可复现（官方 §5.2）⇒ 不参与排序，但必须显式记录差异。"""

    rows = [stage.LedgerRow("p01", total_score=10, place_points=0),
            stage.LedgerRow("p02", total_score=5, place_points=3)]
    standing = stage.rank_ledger(rows, keys=["total_score", "place_points", "god_count"])
    assert standing[0]["participant_id"] == "p01"
    assert standing[0]["keys_declared"] == ["total_score", "place_points", "god_count"]
    assert standing[0]["keys_used"] == ["total_score", "place_points"]
    assert all(row["god_count"] is None for row in standing)


def test_ties_are_marked_unresolved_with_declared_fallback():
    """★ 两键相同时名次未解决：并列同名次 + 显式标记 + 声明的身份字典序兜底。"""

    rows = [stage.LedgerRow("p02", total_score=10, place_points=1),
            stage.LedgerRow("p01", total_score=10, place_points=1)]
    standing = stage.rank_ledger(rows, keys=["total_score", "place_points", "god_count"])
    assert [row["participant_id"] for row in standing] == ["p01", "p02"]
    assert [row["rank"] for row in standing] == [1, 1]
    assert all(row["tie_unresolved"] for row in standing)


def test_final_ranking_ignores_place_points():
    """★ 决赛只看 total_score（官方 §5.2）：名次分不同也不改变并列判定。"""

    rows = [stage.LedgerRow("p01", total_score=10, place_points=3),
            stage.LedgerRow("p02", total_score=10, place_points=-3)]
    standing = stage.rank_ledger(rows, keys=["total_score"])
    assert [row["rank"] for row in standing] == [1, 1]
    assert standing[0]["keys_used"] == ["total_score"]


# --- 4. 蛇形分组 -------------------------------------------------------------


def test_snake_seeding_matches_the_official_pattern():
    """★ 16 人 4 组的标准蛇形：{1,8,9,16} / {2,7,10,15} / {3,6,11,14} / {4,5,12,13}。"""

    ordered = ["r{0:02d}".format(index) for index in range(1, 17)]
    groups, _ = stage.snake_groups(ordered, groups=4, group_size=4)
    assert groups == [["r01", "r08", "r09", "r16"], ["r02", "r07", "r10", "r15"],
                      ["r03", "r06", "r11", "r14"], ["r04", "r05", "r12", "r13"]]


def test_avoidance_reduces_repeat_pairs():
    """上一阶段同组再相遇时，确定性贪心交换必须减少（且不得增加）重逢对数。"""

    ordered = ["r{0:02d}".format(index) for index in range(1, 17)]
    baseline, _ = stage.snake_groups(ordered, groups=4, group_size=4)
    _, diagnostics = stage.snake_groups(ordered, groups=4, group_size=4,
                                        previous_groups=baseline)
    assert diagnostics["repeat_pairs_before_swaps"] > 0
    assert diagnostics["repeat_pairs"] <= diagnostics["repeat_pairs_before_swaps"]


def test_group_size_mismatch_is_rejected():
    with pytest.raises(ValueError):
        stage.snake_groups(["a", "b", "c"], groups=2, group_size=4)


# --- 5. 计划核验（R8-4） -----------------------------------------------------


def build_plan_and_outcomes(**contract_overrides):
    frozen = contract(**contract_overrides)
    members = [{"participant_id": pid, "policy_name": "weighted_heuristic_v2"} for pid in IDS9]
    plan, _ = stage.plan_qualifying_tables(
        contract=frozen, participants=members, stage_no=1, stage_name="海选",
        stage_role="qualify", panel_seed=int(frozen["seeds"]["panel_seed"]))
    outcomes = []
    for table in plan:
        seats = table.seats()
        outcomes.append(stage.TableOutcome(
            table_id=table.table_id, status="complete", participant_ids_by_seat=seats,
            scores_by_seat=tuple(range(stage.SEAT_COUNT)), source_kind="fixture"))
    return plan, outcomes


def test_complete_matrix_passes():
    plan, outcomes = build_plan_and_outcomes()
    verdict = stage.verify_stage_tables(plan, outcomes)
    assert verdict["ok"] and verdict["problems"] == []


def test_partial_failure_makes_the_stage_unrankable():
    """★ 一条 error 就不可排序：不允许把剩下的成功行拿去排名（R8-4）。"""

    plan, outcomes = build_plan_and_outcomes()
    broken = stage.TableOutcome(
        table_id=outcomes[0].table_id, status="error",
        participant_ids_by_seat=outcomes[0].participant_ids_by_seat,
        failure="注入失败")
    verdict = stage.verify_stage_tables(plan, [broken] + outcomes[1:])
    assert not verdict["ok"]
    assert any("状态 error" in item for item in verdict["problems"])


def test_missing_and_extra_tables_are_reported():
    plan, outcomes = build_plan_and_outcomes()
    missing = stage.verify_stage_tables(plan, outcomes[1:])
    assert any("没有结果" in item for item in missing["problems"])
    extra_outcome = stage.TableOutcome(
        table_id="not-planned", status="complete",
        participant_ids_by_seat=outcomes[0].participant_ids_by_seat,
        scores_by_seat=(0, 0, 0, 0), source_kind="fixture")
    extra = stage.verify_stage_tables(plan, outcomes + [extra_outcome])
    assert any("不属于本阶段计划" in item for item in extra["problems"])


def test_seat_identity_mismatch_is_reported():
    """座位身份与计划不符也必须拦下：否则分数会被记到别人头上。"""

    plan, outcomes = build_plan_and_outcomes()
    seats = list(outcomes[0].participant_ids_by_seat)
    seats[0], seats[1] = seats[1], seats[0]
    tampered = stage.TableOutcome(
        table_id=outcomes[0].table_id, status="complete",
        participant_ids_by_seat=tuple(seats), scores_by_seat=outcomes[0].scores_by_seat,
        source_kind="fixture")
    verdict = stage.verify_stage_tables(plan, [tampered] + outcomes[1:])
    assert any("座位身份与计划不符" in item for item in verdict["problems"])


def test_failed_table_aborts_the_whole_run():
    """★ 执行失败必须让整轮编排停下并抛 StageFailed，不产出任何名次。"""

    scores = {1: {pid: 10 for pid in IDS9}, 2: {pid: 10 for pid in IDS9},
              3: {pid: 10 for pid in IDS9}}
    frozen = contract()
    orchestrator = stage.StageOrchestrator(
        contract=frozen, participants=participants(9),
        run_tables=scripted_runner(scores, broken_tables=("s1-b1-t1",)))
    with pytest.raises(stage.StageFailed):
        orchestrator.run()


# --- 6. 编排语义（构造输入） -------------------------------------------------


def test_stage_scores_reset_each_stage():
    """★ 官方：每个阶段独立计分，不带入下一阶段。"""

    scores = {1: {pid: 10 for pid in IDS9}, 2: {pid: 40 for pid in IDS9},
              3: {pid: 7 for pid in IDS9}}
    run = run_orchestration(scores_by_stage=scores)
    stage_two = run["stages"][1]
    assert all(row["total_score"] == 80 for group in stage_two["groups"]
               for row in group["standings"])          # 40 × 2 场，不含阶段 1 的 20
    assert all(stage["score_reset"] for stage in run["stages"])


def test_byes_score_zero_and_are_recorded():
    """★ 官方：某批不足一桌者该批轮空，0 分且不计名次分。"""

    scores = {1: {pid: 10 for pid in IDS9}, 2: {pid: 40 for pid in IDS9},
              3: {pid: 7 for pid in IDS9}}
    run = run_orchestration(scores_by_stage=scores)
    first = run["stages"][0]
    byes = first["byes"]
    assert sorted(byes.values()) == [0] * 7 + [1, 1]        # 9 人 4 桌 ⇒ 恰好 1 人轮空 / 批
    byed = [pid for pid, count in byes.items() if count]
    for row in first["standings"]:
        if row["participant_id"] in byed:
            assert row["total_score"] == 10 and row["tables_played"] == 1
        else:
            assert row["total_score"] == 20 and row["tables_played"] == 2


def test_boundary_tie_is_reported_as_unresolved():
    """★ 晋级边界两键相同时：标未解决，并用声明的身份字典序兜底。"""

    scores = {1: {pid: 10 for pid in IDS9}, 2: {pid: 40 for pid in IDS9},
              3: {pid: 7 for pid in IDS9}}
    run = run_orchestration(scores_by_stage=scores)
    first = run["stages"][0]
    assert first["advance"]["boundary_unresolved"] is True
    assert any(item["kind"] == "advancement_boundary" for item in run["boundaries"])
    assert len(first["advance"]["advanced"]) == 8


def test_cross_group_scores_are_not_compared():
    """★ 官方 §3.2：组与组之间的分数不互相比较——高分的组内第 3 名照样淘汰。"""

    # 阶段 1：前 8 名按身份字典序晋级（同分），蛇形分成 2 组。
    stage_one = {pid: 10 for pid in IDS9}
    flat = {pid: 10 for pid in IDS9}
    probe = run_orchestration(scores_by_stage={1: stage_one, 2: flat, 3: flat})
    members = [group["members"] for group in probe["stages"][1]["groups"]]
    # 构造：A 组第 2 名分数低于 B 组第 3 名。
    values = {}
    for index, member in enumerate(members[0]):
        values[member] = 100 - index * 40          # 100 / 60 / 20 ...
    for index, member in enumerate(members[1]):
        values[member] = 90 - index * 10           # 90 / 80 / 70 ...
    run = run_orchestration(scores_by_stage={1: stage_one, 2: values, 3: flat})
    groups = run["stages"][1]["groups"]
    loser = groups[1]["standings"][2]
    winner = groups[0]["standings"][1]
    assert loser["total_score"] > winner["total_score"]
    assert loser["participant_id"] not in groups[1]["advanced"]
    assert winner["participant_id"] in groups[0]["advanced"]


def test_group_stage_standings_follow_the_declared_cross_group_order():
    """★ 组内赛的阶段名次表按合同声明的「组内名次优先、组序号次序」排列。

    官方没有公开跨组种子算法（见合同 unresolved），因此这条**声明**必须由测试钉住：
    先各组第 1 名（按组序号），再各组第 2 名……而不是把所有组按分数全局排序。
    """

    flat = {pid: 10 for pid in IDS9}
    run = run_orchestration(scores_by_stage={1: flat, 2: flat, 3: flat})
    stage_two = run["stages"][1]
    groups = stage_two["groups"]
    expected = []
    for rank_index in range(len(groups[0]["standings"])):
        for group in groups:
            expected.append(group["standings"][rank_index]["participant_id"])
    assert [row["participant_id"] for row in stage_two["standings"]] == expected
    assert stage_two["standings_order_basis"] == contract()["group"]["next_stage_seed_order"]


def test_final_runs_overtime_until_the_order_is_unique():
    """★ 官方 §3.3：同分自动加赛并把得分并入决赛总账，直到 1—4 名两两不同。"""

    scores = {1: {pid: 10 for pid in IDS9}, 2: {pid: 10 for pid in IDS9},
              3: {pid: 10 for pid in IDS9}}
    runner = scripted_runner(scores, overtime_delta={"p01": 4, "p02": 3, "p03": 2, "p04": 1})
    run = stage.build_run(contract=contract(), participants=participants(9), runner=runner,
                          mode="test")
    final = run["stages"][2]
    assert final["overtime"] == {"rounds": 1, "unique_after": True, "cap_reached": False}
    assert len({row["total_score"] for row in final["standings"]}) == 4
    assert all(row["keys_used"] == ["total_score"] for row in final["standings"])
    assert len(final["tables"]) == 2                 # 决赛一场 + 加赛一场


def test_overtime_cap_is_reported_as_unresolved():
    """★ 工程上限触及后必须标未解决，不宣称名次已唯一（官方加赛本无上限）。"""

    scores = {1: {pid: 10 for pid in IDS9}, 2: {pid: 10 for pid in IDS9},
              3: {pid: 10 for pid in IDS9}}
    run = run_orchestration(scores_by_stage=scores, max_overtime=1)
    final = run["stages"][2]
    assert final["overtime"]["cap_reached"] is True
    assert final["overtime"]["unique_after"] is False
    assert any(item["kind"] == "overtime_cap" for item in run["boundaries"])


def test_ladder_short_circuits_to_final_for_four_participants():
    """4 人直接决赛（官方 §2），没有海选阶段。"""

    scores = {1: {pid: 10 for pid in IDS9[:4]}}
    run = run_orchestration(scores_by_stage=scores, count=4)
    assert [item["name"] for item in run["stages"]] == ["决赛"]
    assert run["stages"][0]["role"] == "final"


# --- 7. 身份与产物 -----------------------------------------------------------


def test_root_set_id_matches_the_scheduler():
    """★ 与调度器同口径：两边对同一组 seed 必须给出同一个根组身份（R7-4 的约定）。"""

    seeds = [{"seed": 11, "scenario_id": "a"}, {"seed": 22, "scenario_id": "b"}]
    assert stage.root_set_id_of(seeds) == scheduler.root_set_id_of(seeds)


def test_panel_identity_follows_structure_and_seeds_not_labels():
    """★ 身份按**结构与 seed** 取哈希（R8-5）：只改标签不改身份，改 seed 必改身份。"""

    frozen = contract()
    members = [{"participant_id": pid, "policy_name": "weighted_heuristic_v2"} for pid in IDS9]
    plan, _ = stage.plan_qualifying_tables(
        contract=frozen, participants=members, stage_no=1, stage_name="海选",
        stage_role="qualify", panel_seed=int(frozen["seeds"]["panel_seed"]))
    renamed = [stage.replace_table_labels(table) for table in plan]
    base = stage.panel_identity(contract_sha256="x", participants=members, plan=plan)
    assert stage.panel_identity(contract_sha256="x", participants=members,
                                plan=renamed) == base
    reseeded = [stage.replace(table, seed=table.seed + 1) for table in plan]
    assert stage.panel_identity(contract_sha256="x", participants=members,
                                plan=reseeded) != base
    moved = [stage.replace(table, permutation=(1, 2, 3, 0)) for table in plan]
    assert stage.panel_identity(contract_sha256="x", participants=members, plan=moved) != base


def test_tables_jsonl_rows_are_contract_match_results(tmp_path):
    """★ 逐场次产物必须是契约 §7 的 MatchResult：生产读取器要能直接读回。"""

    from hangma_bot.kernel.config import RuleConfig, TimingConfig, TournamentConfig
    from hangma_bot.offline.evaluation_results import MatchResult, read_results_jsonl

    row = MatchResult(
        evaluation_schema_version=1, result_id="r-test", source_kind="simulation",
        scenario_id="s1t1-1", pair_id="s1t1-1:0123", game_key=None,
        config=TournamentConfig(max_games=1, rounds_per_game=2,
                                rules=RuleConfig(ruleset_version="test", base_score=1,
                                                 you_cai_bi_kao=False),
                                timing=TimingConfig(peng_timeout_sec=1.0, chi_timeout_sec=1.0,
                                                    discard_timeout_sec=3.0)),
        policy_ids_by_seat=("p01", "p02", "p03", "p04"), seat_permutation=(0, 1, 2, 3),
        expected_hands=2, completed_hands=2, scores_before=(0, 0, 0, 0),
        scores_after=(9, -3, 0, -6), official_ranks=None, status="complete",
        invalid_reasons=(), runtime_counts=None, versions=(("ruleset_version", "test"),),
        source_refs=())
    payload = dict(row.to_json())
    payload[stage.ROW_ENVELOPE_KEY] = {"schema": stage.RUN_SCHEMA, "table_id": "s1-b1-t1",
                                       "stage_no": 1, "seed": 1, "wall_ms": 12.5}
    path = tmp_path / "tables.jsonl"
    path.write_text(json.dumps(payload, ensure_ascii=False) + chr(10), encoding="utf-8")
    parsed = read_results_jsonl(path)
    assert len(parsed) == 1
    assert parsed[0].scores_after == (9, -3, 0, -6)
    rows = stage.read_tables_jsonl(path)
    assert rows["s1-b1-t1"].scores_by_seat == (9, -3, 0, -6)
    assert rows["s1-b1-t1"].participant_ids_by_seat == ("p01", "p02", "p03", "p04")


def test_tables_jsonl_is_written_from_the_persisted_cells(tmp_path):
    """★ 回归：逐场次产物不能是空文件。

    初版把 MatchResult 行只留在内存里，落盘时被静默跳过，产出 0 字节的
    tables.jsonl（**看上去有产物、其实没有内容**）。这条测试把
    「单元格文件 → tables.jsonl」这条链路钉住。
    """

    from hangma_bot.kernel.config import RuleConfig, TimingConfig, TournamentConfig
    from hangma_bot.offline.evaluation_results import MatchResult, read_results_jsonl

    row = MatchResult(
        evaluation_schema_version=1, result_id="r-s1-b1-t1", source_kind="simulation",
        scenario_id="s1t1-1", pair_id="s1t1-1:0123", game_key=None,
        config=TournamentConfig(max_games=1, rounds_per_game=2,
                                rules=RuleConfig(ruleset_version="test", base_score=1,
                                                 you_cai_bi_kao=False),
                                timing=TimingConfig(peng_timeout_sec=1.0, chi_timeout_sec=1.0,
                                                    discard_timeout_sec=3.0)),
        policy_ids_by_seat=("p01", "p02", "p03", "p04"), seat_permutation=(0, 1, 2, 3),
        expected_hands=2, completed_hands=2, scores_before=(0, 0, 0, 0),
        scores_after=(9, -3, 0, -6), official_ranks=None, status="complete",
        invalid_reasons=(), runtime_counts=None, versions=(("ruleset_version", "test"),),
        source_refs=())
    cell = tmp_path / "tables" / stage.slug("s1-b1-t1")
    cell.mkdir(parents=True)
    (cell / "table.json").write_text(json.dumps(
        {"schema": stage.RUN_SCHEMA, "table_id": "s1-b1-t1", "wall_ms": 12.5,
         "result": row.to_json()}, ensure_ascii=False), encoding="utf-8")
    run = {"tables": [{"plan": {"table_id": "s1-b1-t1", "stage_no": 1, "group_index": None,
                                "seed": 7, "scenario_id": "s1t1-7",
                                "seat_participants": ["p01", "p02", "p03", "p04"]},
                       "outcome": {"supervision": {"returncode": 0}}}]}
    stage._write_tables_jsonl(tmp_path / "tables.jsonl", tmp_path, run)
    text = (tmp_path / "tables.jsonl").read_text(encoding="utf-8").strip()
    assert text, "tables.jsonl 不能为空"
    parsed = read_results_jsonl(tmp_path / "tables.jsonl")
    assert len(parsed) == 1 and parsed[0].scores_after == (9, -3, 0, -6)
    rows = stage.read_tables_jsonl(tmp_path / "tables.jsonl")
    assert rows["s1-b1-t1"].wall_ms == 12.5


def test_config_snapshot_is_reused_from_step_1_3():
    """配置指纹必须复用 1.3 的快照工具（一处定义），不重造第二份语义。"""

    snapshot = stage.config_snapshot(contract=contract())
    assert snapshot["schema"] == "sitin-config/1"
    assert snapshot["config_fingerprint"]
    other = stage.config_snapshot(contract=contract(clock_mode="real"))
    assert other["config_fingerprint"] != snapshot["config_fingerprint"]


# --- 8. 构造夹具与重演 -------------------------------------------------------


def test_fixture_runner_rejects_undeclared_participants():
    """夹具缺声明必须显式失败：**不能把未知填成 0**。"""

    frozen = contract()
    members = [{"participant_id": pid, "policy_name": "weighted_heuristic_v2"} for pid in IDS9]
    plan, _ = stage.plan_qualifying_tables(
        contract=frozen, participants=members, stage_no=1, stage_name="海选",
        stage_role="qualify", panel_seed=int(frozen["seeds"]["panel_seed"]))
    runner = stage.fixture_runner({"schema": stage.FIXTURE_SCHEMA,
                                   "base_scores": {"p01": 1}})
    with pytest.raises(stage.StageFailed):
        runner(plan)


def test_recorded_runner_reports_missing_tables():
    """重演缺场次即失败：重演不得凭标签或空值补全。"""

    frozen = contract()
    members = [{"participant_id": pid, "policy_name": "weighted_heuristic_v2"} for pid in IDS9]
    plan, _ = stage.plan_qualifying_tables(
        contract=frozen, participants=members, stage_no=1, stage_name="海选",
        stage_role="qualify", panel_seed=int(frozen["seeds"]["panel_seed"]))
    with pytest.raises(stage.StageFailed):
        stage.recorded_runner({})(plan)

# --- 9. 复审整改回归（#15 加赛名次分 / #16 真冻结 / #17 组内边界 / #18 重演对账 / #19 轮空记账）


def test_rule_citations_resolve_to_the_official_snapshot():
    """★ 规则引文必须真的能在官方快照里逐条核到（复审 #15 的出处要求）。

    "我当时读到过"不是出处：引文带行号与原文片段，校验器打开快照比对；
    引文改错必须失败。
    """

    assert stage.verify_rule_citations() == []
    assert "final.overtime_no_place_points" in {item["key"] for item in stage.RULES_VERIFIED}
    citations = contract()["rule_citations"]
    assert citations and {item["file"] for item in citations} == {stage.GUIDE_REF}
    assert all(int(item["line"]) > 1 for item in citations)


def test_rule_citation_mismatch_is_rejected(monkeypatch):
    """引文与快照不符必须失败（否则引文会悄悄过期）。"""

    wrong = tuple(dict(item, excerpt="这段原文不存在于快照里") for item in stage.RULES_VERIFIED)
    monkeypatch.setattr(stage, "RULES_VERIFIED", wrong)
    assert stage.verify_rule_citations()


def test_overtime_tables_do_not_produce_place_points():
    """★ 官方 v34 第 377 行：加赛场不产生名次分/白板数（复审 #15）。

    初版对加赛桌照常按本场位次发 +3/+1/−1/−3：决赛名次不受影响，但**被记录的分项是错的**。
    """

    flat = {pid: 10 for pid in IDS9}
    run = run_orchestration(scores_by_stage={1: flat, 2: flat, 3: flat})
    final = run["stages"][2]
    assert final["overtime"]["rounds"] >= 1, "本例必须真的触发加赛"
    overtime_rows = [row for row in final["seat_accounting"] if row["stage_kind"] == "overtime"]
    assert overtime_rows
    for row in overtime_rows:
        assert set(row["place_points_by_seat"]) == {0}
        assert row["place_points_rule"] == "overtime_no_place_points"
    regular_rows = [row for row in final["seat_accounting"] if row["stage_kind"] == "final"]
    assert regular_rows and all(row["place_points_rule"] == "table_rank" for row in regular_rows)


def test_final_standings_record_place_points_but_rank_by_total_score():
    """加赛名次分归零不改决赛判据：决赛仍只看总得分（官方「决赛轮纯总得分」）。

    常规决赛桌仍按本场位次记录名次分（官方「名次分每场 …」），加赛桌贡献固定 0；
    排序键始终只有 total_score。
    """

    flat = {pid: 10 for pid in IDS9}
    runner = scripted_runner({1: flat, 2: flat, 3: flat},
                             overtime_delta={"p01": 4, "p02": 3, "p03": 2, "p04": 1})
    run = stage.build_run(contract=contract(), participants=participants(9), runner=runner,
                          mode="test")
    final = run["stages"][2]
    assert final["overtime"]["rounds"] == 1
    assert all(row["keys_used"] == ["total_score"] for row in final["standings"])
    totals = [row["total_score"] for row in final["standings"]]
    assert len(set(totals)) == len(totals), "加赛后名次必须两两不同"
    # 记录到的名次分必须**只来自常规决赛桌**：加赛桌贡献 0（官方 v34 第 377 行）。
    # 本例四人同分 ⇒ 常规桌按并列区间平均也是 0；用逐座位复算把这条对齐钉住。
    regular = [row for row in final["seat_accounting"] if row["stage_kind"] == "final"]
    assert len(regular) == 1
    expected_points = {}
    for row in regular:
        for seat, participant in enumerate(row["participants_by_seat"]):
            expected_points[participant] = row["place_points_by_seat"][seat]
    assert all(row["place_points"] == expected_points[row["participant_id"]]
               for row in final["standings"])
    overtime_points = [row for row in final["seat_accounting"] if row["stage_kind"] == "overtime"]
    assert overtime_points and all(set(row["place_points_by_seat"]) == {0}
                                   for row in overtime_points)


def test_contract_must_be_frozen_explicitly():
    """★ 合同冻结日期必须显式给出：不得默认取当天 UTC（复审 #16）。"""

    with pytest.raises(TypeError):
        stage.default_contract(ruleset_version="r", base_score=1, you_cai_bi_kao=False,
                               rounds_per_game=2)
    for bad in ("", "2026/09/15", "today"):
        with pytest.raises(ValueError):
            contract(frozen_at=bad)
    assert contract()["frozen_at"] == FROZEN_AT
    broken = dict(contract(), frozen_at="x")
    assert any("frozen_at" in item for item in stage.validate_contract(broken))


def test_contract_text_is_independent_of_the_wall_clock(monkeypatch):
    """★ 同一条复跑命令在任何一天都必须产出同一个 sha（复审 #16）。

    做法不是"比两次结果"（那证明不了什么），而是**让任何日期读取直接报错**：
    合同一旦偷偷读当天日期，本测试立刻失败。
    """

    baseline = stage.contract_text(contract())
    assert stage.sha256_text(baseline) == stage.sha256_text(stage.contract_text(contract()))

    def _forbidden(*args, **kwargs):
        raise AssertionError("阶段合同不得读取当天日期（frozen_at 必须显式给出）")

    monkeypatch.setattr(stage.time, "gmtime", _forbidden)
    monkeypatch.setattr(stage.time, "strftime", _forbidden)
    assert stage.contract_text(contract()) == baseline


def test_group_stage_boundary_tie_is_reported():
    """★ 组内第 2/3 名两键相同时同样是**未解决边界**（复审 #17：初版硬编码 False）。"""

    flat = {pid: 10 for pid in IDS9}
    probe = run_orchestration(scores_by_stage={1: flat, 2: flat, 3: flat})
    members = [group["members"] for group in probe["stages"][1]["groups"]]
    values = {}
    for index, member in enumerate(members[0]):
        values[member] = (100, 50, 50, 0)[index]        # 第 2、3 名两场同分 ⇒ 两键相同
    for index, member in enumerate(members[1]):
        values[member] = 100 - index * 30
    run = run_orchestration(scores_by_stage={1: flat, 2: values, 3: flat})
    stage_two = run["stages"][1]
    tied_group = [group for group in stage_two["groups"] if group["boundary_unresolved"]]
    assert len(tied_group) == 1, "第一组必须出现组内晋级线并列"
    assert tied_group[0]["index"] if False else tied_group[0]["group_index"] == 1
    assert stage_two["advance"]["boundary_unresolved"] is True
    entries = [item for item in run["boundaries"] if item.get("group_index") == 1]
    assert entries and entries[0]["kind"] == "advancement_boundary"


@pytest.mark.parametrize("count", [5, 6, 7])
def test_small_fields_record_byes_instead_of_silent_zero(count):
    """★ 5/6/7 人档：凑不满一桌的余数必须记**轮空**（复审 #19）。

    初版按每批上限切 4 人块、遇不足一桌就 break，余数既不上桌也不记轮空，
    被静默算成"打了 0 场、0 分"。
    """

    flat = {pid: 10 for pid in IDS9[:count]}
    run = run_orchestration(scores_by_stage={1: flat, 2: flat, 3: flat}, count=count)
    first = run["stages"][0]
    remainder = count % 4
    batches = int(contract()["batch"]["batches"])
    assert sum(first["byes"].values()) == batches * remainder
    for row in first["standings"]:
        assert row["tables_played"] + row["byes"] == batches
    for batch in first["batch_plan"]:
        assert batch["tables"] == count // 4
        assert len(batch["seated"]) == 4 * (count // 4)
        assert len(batch["byes"]) == remainder


def test_bye_accounting_still_matches_the_nine_person_case():
    """9 人档行为不变：2 批各 2 桌、每批 1 人轮空（#19 的修复不得改动原语义）。"""

    flat = {pid: 10 for pid in IDS9}
    first = run_orchestration(scores_by_stage={1: flat, 2: flat, 3: flat})["stages"][0]
    assert sorted(first["byes"].values()) == [0] * 7 + [1, 1]


def test_recorded_runner_and_comparison_agree(tmp_path):
    """重演对账的正例：输入与记录一致时两侧都不报问题。"""

    flat = {pid: 10 for pid in IDS9}
    run_path, tables_path, run = write_replay_inputs(
        tmp_path, scores_by_stage={1: flat, 2: flat, 3: flat})
    assert run_path.exists() and tables_path.exists()
    rows = stage.read_tables_jsonl(tables_path)
    assert stage.compare_expected_tables(rows, run) == []
    recomputed = stage.build_run(contract=contract(), participants=participants(9),
                                 runner=stage.recorded_runner(rows), mode="replay")
    assert stage.compare_runs(run, recomputed) == []


def test_replay_comparison_detects_tampering_on_either_side(tmp_path):
    """★ 重演必须**两侧都核**（复审 #18）：只改 tables.jsonl 或只改 run.json 都要报问题。"""

    flat = {pid: 10 for pid in IDS9}
    _, tables_path, run = write_replay_inputs(
        tmp_path, scores_by_stage={1: flat, 2: flat, 3: flat})
    rows = stage.read_tables_jsonl(tables_path)
    assert stage.compare_expected_tables(rows, run) == []

    target = sorted(rows)[0]
    tampered_rows = dict(rows)
    tampered_rows[target] = stage.replace(rows[target], scores_by_seat=(99, 98, 97, 96))
    assert stage.compare_expected_tables(tampered_rows, run), "改输入侧必须被发现"

    tampered_run = json.loads(json.dumps(run))
    tampered_run["tables"][0]["outcome"]["scores_by_seat"] = [1, 2, 3, 4]
    assert stage.compare_expected_tables(rows, tampered_run), "改记录侧必须被发现"

    tampered_seat = json.loads(json.dumps(run))
    tampered_seat["tables"][0]["plan"]["seat_participants"] = ["p09", "p08", "p07", "p06"]
    assert stage.compare_expected_tables(rows, tampered_seat), "座位身份被改必须被发现"

    tampered_seed = json.loads(json.dumps(run))
    tampered_seed["tables"][0]["plan"]["seed"] = int(tampered_seed["tables"][0]["plan"]["seed"]) + 1
    assert stage.compare_expected_tables(rows, tampered_seed), "换牌山（seed）必须被发现"


def test_replay_comparison_detects_tampered_results(tmp_path):
    """★ 记录侧的名次表、身份、边界被改也必须在重算对账里报出来。"""

    flat = {pid: 10 for pid in IDS9}
    _, tables_path, run = write_replay_inputs(
        tmp_path, scores_by_stage={1: flat, 2: flat, 3: flat})
    rows = stage.read_tables_jsonl(tables_path)
    recomputed = stage.build_run(contract=contract(), participants=participants(9),
                                 runner=stage.recorded_runner(rows), mode="replay")
    assert stage.compare_runs(run, recomputed) == []

    standings_tampered = json.loads(json.dumps(run))
    standings_tampered["stages"][0]["standings"][0]["total_score"] += 1
    assert stage.compare_runs(standings_tampered, recomputed), "名次表被改必须被发现"

    identity_tampered = json.loads(json.dumps(run))
    identity_tampered["panel_id"] = "panel-deadbeef"
    assert stage.compare_runs(identity_tampered, recomputed), "面板身份被改必须被发现"

    advance_tampered = json.loads(json.dumps(run))
    advance_tampered["stages"][0]["advance"]["advanced"] = ["p01"]
    assert stage.compare_runs(advance_tampered, recomputed), "晋级名单被改必须被发现"

    boundary_tampered = json.loads(json.dumps(run))
    boundary_tampered["boundaries"] = [{"kind": "假的边界"}]
    assert stage.compare_runs(boundary_tampered, recomputed), "边界记录被改必须被发现"


# --- 10. CLI 子命令覆盖（contract / check / fixture / run(void) / replay）


REPLAY_CLI_ARGS = ("--ruleset-version", "test-ruleset", "--rounds-per-game", "2")


def test_cli_contract_and_check(tmp_path):
    """★ CLI 覆盖：contract 产合同、check 校验；缺 --frozen-at 必须直接失败。"""

    out_dir = tmp_path / "contract"
    assert stage.main(["contract", "--frozen-at", FROZEN_AT, "--out", str(out_dir)]) == 0
    assert (out_dir / "stage-contract.json").exists()
    assert (out_dir / "STAGE-CONTRACT.md").exists()
    assert stage.main(["check", "--contract-file", str(out_dir / "stage-contract.json")]) == 0
    # check 以数据形式报问题：缺 --frozen-at 返回 2（不是抛 SystemExit）
    assert stage.main(["check"]) == 2
    with pytest.raises(SystemExit):
        stage.main(["contract", "--out", str(tmp_path / "nope")])


def test_cli_fixture_end_to_end(tmp_path):
    """★ CLI 覆盖：fixture 端到端产出运行记录与报告（构造集，不是效果证据）。"""

    flat = {pid: 10 for pid in IDS9}
    fixture_path = tmp_path / "fixture.json"
    fixture_path.write_text(json.dumps({
        "schema": stage.FIXTURE_SCHEMA, "base_scores": flat, "seat_bonus": [0, 0, 0, 0],
        "stage_base_scores": {"2": flat, "3": flat},
        "overtime_delta": {pid: index for index, pid in enumerate(IDS9)},
    }, ensure_ascii=False), encoding="utf-8")
    out_dir = tmp_path / "fixture-run"
    assert stage.main(["fixture", "--fixture", str(fixture_path), "--out", str(out_dir),
                       "--participants", "9", "--frozen-at", FROZEN_AT]) == 0
    run = json.loads((out_dir / "run.json").read_text(encoding="utf-8"))
    assert run["mode"] == "fixture" and len(run["tables"]) >= 9
    assert run["status"]["candidates_found"] == "not_applicable"
    assert (out_dir / "REPORT.md").exists()


def test_cli_run_void_path(tmp_path):
    """★ CLI 覆盖：少于 4 人时整场作废，落 void.json 且不产生名次。"""

    out_dir = tmp_path / "void"
    assert stage.main(["run", "--out", str(out_dir), "--participants", "3",
                       "--frozen-at", FROZEN_AT]) == 0
    void = json.loads((out_dir / "void.json").read_text(encoding="utf-8"))
    assert void["schema"] == stage.VOID_SCHEMA
    assert "作废" in void["reason"]
    assert not (out_dir / "run.json").exists()


def test_cli_replay_accepts_a_consistent_pair_and_rejects_tampering(tmp_path):
    """★ CLI 覆盖：重演对账——一致返回 0；改输入或改记录返回 2 并列出 problems。"""

    flat = {pid: 10 for pid in IDS9}
    run_path, tables_path, _ = write_replay_inputs(
        tmp_path, scores_by_stage={1: flat, 2: flat, 3: flat})
    out_dir = tmp_path / "replay"
    args = ["replay", "--tables", str(tables_path), "--expect-run", str(run_path),
            "--out", str(out_dir), "--frozen-at", FROZEN_AT, *REPLAY_CLI_ARGS]
    assert stage.main(list(args)) == 0
    verdict = json.loads((out_dir / "replay.json").read_text(encoding="utf-8"))["verdict"]
    assert verdict["ok"] and verdict["problems"] == []
    assert verdict["replayed_tables"] > 0

    lines = tables_path.read_text(encoding="utf-8").splitlines()
    payload = json.loads(lines[0])
    payload["scores_after"] = [7, 7, 7, 7]
    lines[0] = json.dumps(payload, ensure_ascii=False)
    tables_path.write_text(chr(10).join(lines) + chr(10), encoding="utf-8")
    assert stage.main(list(args)) == 2
    verdict = json.loads((out_dir / "replay.json").read_text(encoding="utf-8"))["verdict"]
    assert any("不一致" in item for item in verdict["problems"])


def test_panel_assembly_never_imports_the_candidate_registry():
    """★ 「面板跑不到未准入候选」必须是**可执行的构造检查**，不是散文承诺。

    复审指出别的包用「静态扫描 import 白名单」会被 from 父包 import 绕过；
    这里改成在子进程里真的加载本模块、装配面板策略、并连组合根一起 import，
    再看候选注册表有没有进 sys.modules（二进制层面的证据，不是文本扫描）。
    """

    import subprocess

    program = (
        "import importlib.util, sys, pathlib;"
        "path = pathlib.Path({path!r});"
        "spec = importlib.util.spec_from_file_location('sitin_stage', path);"
        "module = importlib.util.module_from_spec(spec); sys.modules['sitin_stage'] = module;"
        "spec.loader.exec_module(module);"
        "module.build_panel_policy('weighted_heuristic_v2', lambda: 0.0);"
        "import hangma_bot.bootstrap;"
        "print('LEAK' if 'hangma_bot.policy.heuristics' in sys.modules else 'CLEAN')"
    ).format(path=str(stage.__file__))
    completed = subprocess.run([sys.executable, "-c", program], capture_output=True, text=True,
                               cwd=str(_REPO))
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip().endswith("CLEAN"), completed.stdout
    with pytest.raises(ValueError):
        stage.build_panel_policy("seven_pairs_path_value", lambda: 0.0)

# --- 11. 第三轮整改：对账覆盖面（#11）/ fail-closed（#12）/ 合同命令可跑（#10）/ 日期真解析（#13）


def test_frozen_at_rejects_impossible_calendar_dates():
    """★ 日期必须**真解析**（复审 #13）：2026-13-45 形状合法但不是日期。"""

    for bad in ("2026-13-45", "2026-02-30", "20260915", "2026-9-15", "today", "", None):
        with pytest.raises(ValueError):
            contract(frozen_at=bad)
    assert stage.parse_frozen_at("2026-09-15") == "2026-09-15"
    broken = dict(contract(), frozen_at="2026-13-45")
    assert any("frozen_at" in item for item in stage.validate_contract(broken))


def test_contract_repro_command_reproduces_the_same_contract(tmp_path):
    """★ 合同自带的复跑命令必须**真的能跑通并复现同一 sha**（复审 #10）。

    做法：取合同渲染出的 contract 命令，把解释器换成当前解释器、--out 指到临时目录，
    真的执行它，再比对产出的合同 JSON 与合同本身的 sha。命令漏参数（例如漏 --frozen-at
    或漏非默认参数）会当场失败。
    """

    frozen = contract(rounds_per_game=4, max_overtime=2)     # 故意用非默认参数
    commands = stage.contract_repro_commands(frozen)
    assert len(commands) >= 5
    line = next(item for item in commands if " contract " in item)
    argv = shlex.split(line)
    argv[0] = sys.executable
    out_index = argv.index("--out")
    argv[out_index + 1] = str(tmp_path)
    completed = subprocess.run(argv, cwd=str(_REPO), capture_output=True, text=True)
    assert completed.returncode == 0, completed.stderr
    produced = json.loads((tmp_path / "stage-contract.json").read_text(encoding="utf-8"))
    assert stage.contract_text(produced) == stage.contract_text(frozen)
    assert "--frozen-at" in line and FROZEN_AT in line


def test_rendered_contract_lists_the_runnable_commands():
    """人读版合同里的复跑命令与 contract_repro_commands 同源（一处定义）。"""

    frozen = contract()
    text = stage.render_contract_md(frozen, contract_sha256="deadbeef")
    for command in stage.contract_repro_commands(frozen):
        assert command in text
    assert "--frozen-at" in text


def test_replay_fails_closed_when_seed_is_missing(tmp_path):
    """★ 重演输入缺 seed 是 **problem**，不是"跳过比对"（复审 #12）。"""

    flat = {pid: 10 for pid in IDS9}
    _, tables_path, run = write_replay_inputs(
        tmp_path, scores_by_stage={1: flat, 2: flat, 3: flat})
    rows = stage.read_tables_jsonl(tables_path)
    assert stage.compare_expected_tables(rows, run) == []

    target = sorted(rows)[0]
    without_seed = dict(rows)
    without_seed[target] = stage.replace(rows[target], seed=None)
    problems = stage.compare_expected_tables(without_seed, run)
    assert any("seed" in item and "fail-closed" in item for item in problems), problems

    # 输入侧整体去掉 seed 字段也一样（从文件读回即为 None）
    lines = tables_path.read_text(encoding="utf-8").splitlines()
    payload = json.loads(lines[0])
    payload[stage.ROW_ENVELOPE_KEY].pop("seed")
    lines[0] = json.dumps(payload, ensure_ascii=False)
    tables_path.write_text(chr(10).join(lines) + chr(10), encoding="utf-8")
    stripped = stage.read_tables_jsonl(tables_path)
    assert any("seed" in item for item in stage.compare_expected_tables(stripped, run))


def test_replay_detects_tampered_round_three_fix_fields(tmp_path):
    """★ 对账必须覆盖**承载本轮整改的字段**（复审 #11）：改回旧 bug 值必须报 problem。

    四类字段各一条负例：加赛名次分（#15）、逐批轮空名单（#19）、
    组内晋级边界标记（#17）、计划核验结果（R8-4）。
    """

    flat = {pid: 10 for pid in IDS9}
    runner = scripted_runner({1: flat, 2: flat, 3: flat},
                             overtime_delta={"p01": 4, "p02": 3, "p03": 2, "p04": 1})
    recorded = stage.build_run(contract=contract(), participants=participants(9),
                               runner=runner, mode="test")
    # 复算源 = 这条运行记录自己的场次结果（与"重演"同构），再逐项篡改记录侧。
    recomputed = stage.build_run(contract=contract(), participants=participants(9),
                                 runner=recorded_run_runner(recorded), mode="test")
    assert stage.compare_runs(recorded, recomputed) == []

    # ① 加赛桌名次分改回旧 bug 值（照常按本场位次计分）
    overtime_tampered = json.loads(json.dumps(recorded))
    final_rows = overtime_tampered["stages"][2]["seat_accounting"]
    overtime_rows = [row for row in final_rows if row["stage_kind"] == "overtime"]
    assert overtime_rows, "本例必须真的触发加赛"
    overtime_rows[0]["place_points_by_seat"] = [3, 1, -1, -3]
    overtime_rows[0]["place_points_rule"] = "table_rank"
    problems = stage.compare_runs(overtime_tampered, recomputed)
    assert any("逐场次记账" in item for item in problems), problems

    # ② 逐批轮空名单改回旧行为（不记余数）
    batch_tampered = json.loads(json.dumps(recorded))
    for stage_record in batch_tampered["stages"]:
        for batch in stage_record.get("batch_plan") or []:
            batch["byes"] = []
    assert any("逐批记账" in item for item in stage.compare_runs(batch_tampered, recomputed))

    # ③ 组内晋级边界标记改回硬编码 False
    boundary_tampered = json.loads(json.dumps(recorded))
    for group in boundary_tampered["stages"][1]["groups"]:
        group["boundary_unresolved"] = False
    assert any("边界标记" in item or "名次表" in item
               for item in stage.compare_runs(boundary_tampered, recomputed))

    # ④ 计划核验结果被改
    plan_tampered = json.loads(json.dumps(recorded))
    plan_tampered["plan_verification"][0]["ok"] = False
    plan_tampered["plan_verification"][0]["status_counts"] = {"error": 4}
    assert any("计划核验" in item for item in stage.compare_runs(plan_tampered, recomputed))


def test_replay_detects_recurrence_of_the_overtime_place_point_bug():
    """★ 判据：把**旧 bug 的实现**改回去，重演必须报 problem（复审 #11 / Lead 裁定）。

    这不是手工篡改产物，而是真的把规则接缝换回旧写法再复算一遍。
    """

    flat = {pid: 10 for pid in IDS9}
    runner = scripted_runner({1: flat, 2: flat, 3: flat},
                             overtime_delta={"p01": 4, "p02": 3, "p03": 2, "p04": 1})
    recorded = stage.build_run(contract=contract(), participants=participants(9),
                               runner=runner, mode="test")
    with pytest.MonkeyPatch.context() as patch:
        # 旧实现：加赛桌也按本场位次发 +3/+1/−1/−3
        patch.setattr(stage, "place_points_for_stage_table",
                      lambda table, scores: (stage.place_points_for_table(scores), "table_rank"))
        buggy = stage.build_run(contract=contract(), participants=participants(9),
                                runner=runner, mode="test")
    problems = stage.compare_runs(recorded, buggy)
    assert any("逐场次记账" in item for item in problems), problems


def test_replay_detects_recurrence_of_the_bye_accounting_bug():
    """★ 5/6/7 人轮空记账洞复发必须被发现：把旧 planner 换回去再复算。"""

    def buggy_planner(*, contract, participants, stage_no, stage_name, stage_role, panel_seed):
        """旧实现：按每批上限切 4 人块、不足一桌 break，余数既不记轮空也不上桌。"""

        batch_count = int(contract["batch"]["batches"])
        per_batch = int(contract["batch"]["tables_per_batch"])
        byes = {str(item["participant_id"]): 0 for item in participants}
        order = sorted(participants, key=lambda item: str(item["participant_id"]))
        tables = []
        index = 0
        for batch_index in range(batch_count):
            rng = random.Random(stage.derive_seed(panel_seed, "batch", str(stage_no),
                                                  str(batch_index)))
            shuffled = list(order)
            rng.shuffle(shuffled)
            seated = shuffled[: per_batch * stage.SEAT_COUNT]
            for item in shuffled[per_batch * stage.SEAT_COUNT:]:
                byes[str(item["participant_id"])] += 1
            for slot in range(per_batch):
                quad = seated[slot * stage.SEAT_COUNT:(slot + 1) * stage.SEAT_COUNT]
                if len(quad) < stage.SEAT_COUNT:
                    break
                table_id = "s{0}-b{1}-t{2}".format(stage_no, batch_index + 1, slot + 1)
                seed = stage.derive_seed(panel_seed, "table", str(stage_no), table_id)
                tables.append(stage.build_table_plan(
                    stage_no=stage_no, stage_name=stage_name, stage_role=stage_role,
                    stage_kind="qualifying_global", table_id=table_id, participants=quad,
                    permutation=stage.rotate_permutation(index), seed=seed,
                    tables_in_stage=0, batch_index=batch_index + 1))
                index += 1
        return [stage.replace(table, tables_in_stage=len(tables)) for table in tables], byes

    flat = {pid: 10 for pid in IDS9[:6]}
    scores = {1: flat, 2: flat, 3: flat}
    recorded = run_orchestration(scores_by_stage=scores, count=6)
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(stage, "plan_qualifying_tables", buggy_planner)
        buggy = run_orchestration(scores_by_stage=scores, count=6)
    problems = stage.compare_runs(recorded, buggy)
    assert any("逐批记账" in item or "名次表" in item for item in problems), problems


def test_replay_detects_recurrence_of_the_group_boundary_bug():
    """★ 组内边界标记硬编码 False 的复发必须被发现。"""

    flat = {pid: 10 for pid in IDS9}
    probe = run_orchestration(scores_by_stage={1: flat, 2: flat, 3: flat})
    members = [group["members"] for group in probe["stages"][1]["groups"]]
    values = {}
    for index, member in enumerate(members[0]):
        values[member] = (100, 50, 50, 0)[index]
    for index, member in enumerate(members[1]):
        values[member] = 100 - index * 30
    scores = {1: flat, 2: values, 3: flat}
    recorded = run_orchestration(scores_by_stage=scores)
    assert recorded["stages"][1]["advance"]["boundary_unresolved"] is True
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(stage.StageOrchestrator, "_boundary_tie",
                      lambda self, standings, cut: None)
        buggy = run_orchestration(scores_by_stage=scores)
    problems = stage.compare_runs(recorded, buggy)
    assert any("边界标记" in item or "边界" in item for item in problems), problems


def test_cli_replay_rejects_a_missing_seed(tmp_path):
    """CLI 层同样 fail-closed：去掉一条记录的 seed，重演必须返回 2。"""

    flat = {pid: 10 for pid in IDS9}
    run_path, tables_path, _ = write_replay_inputs(
        tmp_path, scores_by_stage={1: flat, 2: flat, 3: flat})
    lines = tables_path.read_text(encoding="utf-8").splitlines()
    payload = json.loads(lines[0])
    payload[stage.ROW_ENVELOPE_KEY].pop("seed")
    lines[0] = json.dumps(payload, ensure_ascii=False)
    tables_path.write_text(chr(10).join(lines) + chr(10), encoding="utf-8")
    out_dir = tmp_path / "replay"
    code = stage.main(["replay", "--tables", str(tables_path), "--expect-run", str(run_path),
                       "--out", str(out_dir), "--frozen-at", FROZEN_AT, *REPLAY_CLI_ARGS])
    assert code == 2
    verdict = json.loads((out_dir / "replay.json").read_text(encoding="utf-8"))["verdict"]
    assert any("seed" in item for item in verdict["problems"])

# --- 12. 第四轮整改：引文 fail-closed（check --contract-file）/ 计划字段全比对 / 降档登记


def test_check_rejects_a_tampered_contract_citation(tmp_path):
    """★ 交付合同里的引文被篡改必须判不 ok（复审：6 条引文被改仍判 ok 的 fail-open）。

    四类篡改各一条：改行号、改原文、换文件、删一条。
    """

    frozen = contract()
    record_path = tmp_path / "stage-contract.json"
    record_path.write_text(json.dumps(frozen, ensure_ascii=False), encoding="utf-8")
    assert stage.main(["check", "--contract-file", str(record_path)]) == 0

    def tamper_line(payload):
        payload["rule_citations"][0]["line"] = int(payload["rule_citations"][0]["line"]) + 1

    def tamper_excerpt(payload):
        payload["rule_citations"][1]["excerpt"] = "这段原文不存在于快照里"

    def tamper_file(payload):
        payload["rule_citations"][2]["file"] = "doc/references/official-guide-v27-content.txt"

    def tamper_drop(payload):
        payload["rule_citations"].pop()

    for tamper, label in ((tamper_line, "改行号"), (tamper_excerpt, "改原文"),
                          (tamper_file, "换文件"), (tamper_drop, "删一条")):
        payload = json.loads(json.dumps(frozen))
        tamper(payload)
        problems = stage.validate_contract(payload)
        assert problems, "篡改（{0}）必须被判出问题".format(label)
        record_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        assert stage.main(["check", "--contract-file", str(record_path)]) == 2, label
        record_path.write_text(json.dumps(frozen, ensure_ascii=False), encoding="utf-8")


def test_check_rejects_a_contract_that_drops_a_builtin_citation(tmp_path):
    """内建清单里的引文必须在合同里登记；漏登记同样判不 ok（两边都被钉住）。"""

    payload = dict(contract())
    payload["rule_citations"] = [item for item in payload["rule_citations"]
                                 if item["key"] != "ladder_downgrade.dynamic"]
    problems = stage.validate_contract(payload)
    assert any("未登记进合同" in item for item in problems), problems


def _alternative_value(value):
    """给一个必然与原值不同的替换值（用于逐字段篡改回归）。"""

    if isinstance(value, bool):
        return not value
    if isinstance(value, int):
        return value + 1
    if value is None:
        return 0
    if isinstance(value, str):
        return value + "-tampered"
    if isinstance(value, list):
        return list(value) + ["tampered"]
    if isinstance(value, dict):
        return dict(value, _tampered=True)
    return "tampered"


def test_replay_compares_every_plan_field():
    """★ 逐场次计划的**每个字段**都在对账范围内（复审：31 处篡改盲）。

    做法不是"列举几个字段试一下"，而是**遍历运行记录里出现过的全部计划字段**，
    逐个改成不同值再复算：每个字段都必须被报出来。字段以后增减，这条测试自动跟着走。
    """

    flat = {pid: 10 for pid in IDS9}
    runner = scripted_runner({1: flat, 2: flat, 3: flat},
                             overtime_delta={"p01": 4, "p02": 3, "p03": 2, "p04": 1})
    recorded = stage.build_run(contract=contract(), participants=participants(9),
                               runner=runner, mode="test")
    recomputed = stage.build_run(contract=contract(), participants=participants(9),
                                 runner=recorded_run_runner(recorded), mode="test")
    assert stage.compare_runs(recorded, recomputed) == []

    fields = stage.plan_field_inventory(recorded)
    assert {"permutation", "initial_dealer", "batch_index", "match_id", "pair_id",
            "tables_in_stage"} <= set(fields), "本轮点名过的字段必须在清单里"
    for field in fields:
        tampered = json.loads(json.dumps(recorded))
        plan = tampered["tables"][0]["plan"]
        plan[field] = _alternative_value(plan[field])
        problems = stage.compare_runs(tampered, recomputed)
        assert problems, "计划字段 {0} 被篡改却没人报".format(field)


def test_replay_compares_envelope_stage_and_group(tmp_path):
    """★ 输入信封的阶段定位也要比，且缺字段 fail-closed。"""

    flat = {pid: 10 for pid in IDS9}
    run_path, tables_path, run = write_replay_inputs(
        tmp_path, scores_by_stage={1: flat, 2: flat, 3: flat})
    rows = stage.read_tables_jsonl(tables_path)
    assert stage.compare_expected_tables(rows, run) == []

    def rewrite(mutate):
        lines = tables_path.read_text(encoding="utf-8").splitlines()
        payload = json.loads(lines[0])
        mutate(payload[stage.ROW_ENVELOPE_KEY])
        lines[0] = json.dumps(payload, ensure_ascii=False)
        tables_path.write_text(chr(10).join(lines) + chr(10), encoding="utf-8")
        return stage.read_tables_jsonl(tables_path)

    moved = rewrite(lambda envelope: envelope.__setitem__("stage_no", 99))
    assert any("stage_no" in item for item in stage.compare_expected_tables(moved, run))

    regrouped = rewrite(lambda envelope: envelope.__setitem__("group_index", 7))
    assert any("group_index" in item for item in stage.compare_expected_tables(regrouped, run))

    stripped = rewrite(lambda envelope: envelope.pop("group_index"))
    assert any("fail-closed" in item and "group_index" in item
               for item in stage.compare_expected_tables(stripped, run))


def test_replay_verdict_declares_coverage_and_blind_spots(tmp_path):
    """★ 产物要自证覆盖面：列出比对了哪些字段，以及**没有比对什么、为什么**。"""

    flat = {pid: 10 for pid in IDS9}
    run_path, tables_path, run = write_replay_inputs(
        tmp_path, scores_by_stage={1: flat, 2: flat, 3: flat})
    out_dir = tmp_path / "replay"
    assert stage.main(["replay", "--tables", str(tables_path), "--expect-run", str(run_path),
                       "--out", str(out_dir), "--frozen-at", FROZEN_AT, *REPLAY_CLI_ARGS]) == 0
    verdict = json.loads((out_dir / "replay.json").read_text(encoding="utf-8"))["verdict"]
    assert set(stage.plan_field_inventory(run)) <= set(verdict["compared_table_plan_fields"])
    assert {"seed", "scenario_id", "stage_no", "group_index", "seat_participants"} <= set(
        verdict["compared_table_envelope_fields"])
    assert verdict["not_compared_fields"], "没比对的字段必须写明（不能留成空白）"
    assert all(reason for reason in verdict["not_compared_fields"].values())


def test_contract_registers_the_official_stage_downgrade():
    """★ 官方「阶段间降档/翻转」必须登记（复审：此前未登记）。"""

    frozen = contract()
    downgrade = frozen.get("ladder_downgrade")
    assert downgrade, "合同必须登记阶段间降档/翻转"
    assert len(downgrade["rules"]) == 4
    assert any("降为 8 强规模" in rule["behaviour"] for rule in downgrade["rules"])
    assert "降档" in downgrade["stage_total"] and "翻转" in downgrade["stage_total"]
    assert downgrade["offline_handling"].startswith("offline_modeled=false")
    provenance = frozen["provenance"]
    for key in ("ladder_downgrade.rules", "ladder_downgrade.stage_total",
                "ladder_downgrade.offline_handling"):
        assert key in provenance, key
    assert provenance["ladder_downgrade.rules"]["level"] == stage.LEVEL_OFFICIAL
    assert provenance["ladder_downgrade.offline_handling"]["level"] == stage.LEVEL_ENGINEERING
    assert any(item["key"] == "ladder_downgrade.dynamic" for item in frozen["rule_citations"])
    assert any("降档" in str(item.get("item")) for item in frozen["unresolved"])
    assert stage.validate_contract(frozen) == []
    text = stage.render_contract_md(frozen, contract_sha256="deadbeef")
    assert "阶段间降档/翻转" in text and "降为 8 强规模" in text





# ---------------------------------------------------------------------------
# 12. 3.4 候选槽与阶段比较（stagecand 包 · 执行件）
#
# 这一段测试的纪律与前文一致：**结论必须可执行**。特别地，
# 「候选只能从静态注册表注入」「缺准入就不跑阶段比较」「先预留后执行」
# 「单侧失败即不可排序」四条都各有一个负例，不允许只靠散文承诺。
#
# **边界**：本文件不测搜索闭环与 3.5 冻结件——它们不属于本包
# （编排者是 tools/sitin_search.py，见 sitin_stage.py §10 的边界说明）。
# ---------------------------------------------------------------------------


def admission_record(*, candidate="seven_pairs_path_value", weights=None, admitted=True,
                     evidence_kind="admission", corpus_sha="deadbeef"):
    return {"schema": "sitin-gates/1", "evidence_kind": evidence_kind, "candidate": candidate,
            "weights": dict(weights or {"adj.path_log2": 1.0}), "admitted": admitted,
            "failed": [] if admitted else ["G-2 退化检测"], "insufficient": [],
            "bound_identity": "{0}|adj()|base(default)|src0".format(candidate),
            "corpus": {"path": "x", "rows": 1, "sha256": corpus_sha}}


def ledger_for(tmp_path, *, tables=200, wall_sec=100000):
    """**执行台账**（不是预算账本）：只记本执行件跑了多少桌、花了多少墙钟。"""

    return stage.StageExecutionLedger(tmp_path / "execution-ledger.json",
                                      {"tables": tables, "wall_sec": wall_sec})


def overtime_runner_factory():
    """候选臂的决赛打平 ⇒ 触发官方加赛（多一张 s3-final-ot1-t1）；基线不触发。"""

    def factory(arm_dir, candidates):
        name = Path(arm_dir).name

        def run_tables(plan):
            scores = compare_scores()
            delta = None
            if name == "candidate":
                scores[3] = {participant: 0 for participant in scores[3]}
                delta = {"p02": 10}
            return scripted_runner(scores, overtime_delta=delta)(plan)

        return run_tables

    return factory


def _compare_args(**overrides):
    """构造 cmd_compare 需要的 namespace：**走真实解析器**，避免手写字段与 CLI 漂移。"""

    argv = ["compare", "--candidate", "seven_pairs_path_value",
            "--weights", '{"adj.path_log2": 1.0}', "--gate-record", "gates.json",
            "--admission-corpus", "corpus.jsonl", "--contract-file", "contract.json",
            "--scenarios", "2", "--seed-base", "2026102000", "--participants", "9",
            "--focal", "p01", "--budget-tables", "40", "--out", "out"]
    args = stage.build_arg_parser().parse_args(argv)
    for key, value in overrides.items():
        setattr(args, key, value)
    return args


def compare_scores():
    """夹具出分脚本：焦点 p01 基线里垫底（-100），其余参赛者名次互不相同。

    焦点垫底是有意的：这样"候选臂把 p01 抬起来"才会改变**名次**，
    而阶段主指标只看名次与晋级，不看原始分。
    """

    base = {"p01": -100, "p02": 5, "p03": -5, "p04": -10, "p05": 0, "p06": 1, "p07": 2,
            "p08": 3, "p09": 4}
    return {1: dict(base), 2: dict(base), 3: dict(base)}


def compare_runner_factory(*, fail_arms=(), focus_gain=0):
    """按臂名构造 runner：可注入「单侧失败」与「候选臂抬高焦点参赛者」。"""

    def factory(arm_dir, candidates):
        name = Path(arm_dir).name

        def run_tables(plan):
            if name in fail_arms:
                raise stage.StageFailed("注入的会话失败：{0}".format(name))
            scores = compare_scores()
            if name == "candidate" and focus_gain:
                for stage_no in scores:
                    scores[stage_no]["p01"] += int(focus_gain)
            return scripted_runner(scores)(plan)

        return run_tables

    return factory


def run_compare(tmp_path, *, arms=("baseline", "candidate"), fail_arms=(), focus_gain=0,
                scenarios=2, tables=200, digest_reader=None):
    """跑一次**夹具**阶段比较（不跑真实桌赛）：验证配对语义与账目。"""

    out_dir = tmp_path / "compare"
    ledger = ledger_for(tmp_path, tables=tables)
    payload = stage.run_stage_comparison(
        contract=contract(max_overtime=1), arm={"id": "a1",
                                                "candidate": "seven_pairs_path_value",
                                                "weights": {"adj.path_log2": 1.0},
                                                "family": "测试族"},
        participants=participants(9), scenarios=scenarios, seed_base=2026102000,
        out_dir=out_dir, ledger=ledger,
        admission={"record": "x", "record_sha256": "0" * 64, "corpus_sha256": "0" * 64,
                   "bound_identity": "t", "candidate": "seven_pairs_path_value",
                   "weights": {"adj.path_log2": 1.0}, "evidence_kind": "admission"},
        focal="p01", table_timeout_sec=1.0, digest_reader=digest_reader,
        runner_factory=compare_runner_factory(fail_arms=fail_arms, focus_gain=focus_gain))
    return payload, ledger, out_dir


def test_stage_session_bound_keeps_overtime_headroom():
    """★ 先预留要按**上界**：决赛加赛是官方规则允许的额外场次。"""

    bound = stage.stage_session_table_bound(contract=contract(), participants=9)
    assert bound["qualifying"] == 4 and bound["groups"] == 4 and bound["final"] == 1
    assert bound["expected"] == 9
    assert bound["bound"] == 9 + 3 * 1


def test_execution_ledger_reserves_before_executing_and_releases_on_settle(tmp_path):
    """★ 预留**立即计入已用**；结算时多退少补。"""

    ledger = ledger_for(tmp_path, tables=10)
    reservation = ledger.add({"tables": 8}, step="table-match", note="x")
    assert ledger.remaining()["tables"] == 2
    ledger.settle(reservation, {"tables": 5}, note="actual")
    assert ledger.remaining()["tables"] == 5
    reloaded = stage.StageExecutionLedger.load(tmp_path / "execution-ledger.json",
                                               {"tables": 10, "wall_sec": 0})
    assert reloaded.spent["tables"] == 5
    assert reloaded.to_json()["schema"] == "sitin-stage-ledger/1"


def test_execution_ledger_refuses_a_reservation_that_does_not_fit(tmp_path):
    """★ 预留不下就抛，不静默扩容。"""

    ledger = ledger_for(tmp_path, tables=3)
    with pytest.raises(stage.StageBudgetExceeded) as error:
        ledger.add({"tables": 4}, step="table-match", note="x")
    assert "预留不下" in str(error.value)
    assert ledger.spent["tables"] == 0


def test_execution_ledger_stops_after_an_overrun(tmp_path):
    """★ 实际 > 预留 ⇒ 记超额，并且**不再放行**任何新预留（fail-closed）。"""

    ledger = ledger_for(tmp_path, tables=100)
    reservation = ledger.add({"tables": 2}, step="table-match", note="x")
    ledger.settle(reservation, {"tables": 5}, note="超了")
    assert ledger.overruns and ledger.overruns[0]["delta"]["tables"] == 3
    with pytest.raises(stage.StageBudgetExceeded):
        ledger.add({"tables": 1}, step="table-match", note="再来一次")


def test_execution_ledger_counts_unsettled_reservations_as_spent(tmp_path):
    """★ 崩溃后未结算的预留**一律算已花**：不把「没写 done」解释成「没花」。"""

    ledger = ledger_for(tmp_path, tables=10)
    ledger.add({"tables": 6}, step="table-match", note="中断")
    reloaded = stage.StageExecutionLedger.load(tmp_path / "execution-ledger.json",
                                               {"tables": 10, "wall_sec": 0})
    assert reloaded.spent["tables"] == 6
    assert reloaded.stale and len(reloaded.stale) == 1
    assert reloaded.remaining()["tables"] == 4
# --- 12.2 候选装配与准入绑定（闸②） ------------------------------------------


def test_candidate_slot_is_not_a_panel_policy():
    """★ 候选槽名不得混进冻结白名单：白名单路径必须继续拒绝候选名。"""

    assert stage.CANDIDATE_SLOT not in stage.PANEL_POLICY_NAMES
    with pytest.raises(ValueError):
        stage.build_panel_policy(stage.CANDIDATE_SLOT, lambda: 0.0)


def test_build_candidate_policy_rejects_unregistered_names():
    """★ 未注册的候选直接失败（不静默回退到白名单）。"""

    with pytest.raises(KeyError):
        stage.build_candidate_policy("not_a_registered_candidate", {}, lambda: 0.0)


def test_seat_dispatch_injects_the_candidate_only_through_the_registry():
    """★ 闸①可执行：槽名 → 注册表候选；白名单名 → 白名单策略；两者分派在一处。"""

    from hangma_bot.policy.heuristic_adapter import HeuristicAdjustmentPolicy
    from hangma_bot.policy.heuristic_v2 import ComparableHeuristicPolicyV2

    policies = stage.resolve_seat_policies(
        [stage.CANDIDATE_SLOT, "weighted_heuristic_v2"], ["p01", "p02"],
        {stage.CANDIDATE_SLOT: {"candidate": "seven_pairs_path_value",
                                "weights": {"adj.path_log2": 1.0}}},
        lambda: 0.0)
    assert isinstance(policies[0], HeuristicAdjustmentPolicy)
    assert isinstance(policies[1], ComparableHeuristicPolicyV2)
    # 参赛者身份绑定在策略上（只作诊断，不进评分）。
    assert [item.policy_id for item in policies] == ["p01", "p02"]
    # 未注册的名字走候选槽同样失败——闸①不会因为「在槽里」而被绕过。
    with pytest.raises(KeyError):
        stage.resolve_seat_policies(
            [stage.CANDIDATE_SLOT], ["p01"],
            {stage.CANDIDATE_SLOT: {"candidate": "not_registered", "weights": {}}},
            lambda: 0.0)


def test_versions_only_record_the_candidate_slots_that_actually_sat_down():
    """★ 版本块里的候选槽痕迹 = 「这一桌**真的**跑了候选代码」，不是「本会话声明过」。"""

    slots = {stage.CANDIDATE_SLOT: {"candidate": "seven_pairs_path_value",
                                    "weights": {"adj.path_log2": 1.0}}}
    seated = stage.used_candidate_slots([stage.CANDIDATE_SLOT, "weighted_heuristic_v2"], slots)
    assert seated == slots
    assert stage.used_candidate_slots(["weighted_heuristic_v2"] * 4, slots) == {}


def test_stage_ledger_schema_is_not_the_orchestrator_budget_schema():
    """★ 同名不同义会让下游按 schema 解析时静默取错字段：两个 schema **必须不同名**。"""

    ledger = stage.StageExecutionLedger(Path("/tmp/unused-execution-ledger.json"),
                                        {"tables": 4})
    payload = ledger.to_json()
    assert payload["schema"] == "sitin-stage-ledger/1"
    assert payload["schema"] != "sitin-search-ledger/1"
    # 本执行件不调用模型：台账里没有调用次数／输出 token 这两列。
    assert set(payload["spent"]) == {"tables", "wall_sec"}
    assert not (Path("/tmp") / "unused-execution-ledger.json").exists()


def test_admission_binding_is_fail_closed(tmp_path):
    """★ 闸②：证据种类／候选／参数／admitted／语料，五条逐条打掉。"""

    corpus = tmp_path / "corpus.jsonl"
    corpus.write_text("{}\n", encoding="utf-8")
    sha = stage.sha256_file(corpus)
    good = tmp_path / "good.json"
    good.write_text(json.dumps(admission_record(corpus_sha=sha), ensure_ascii=False),
                    encoding="utf-8")
    binding = stage.load_admission_binding(good, corpus, candidate="seven_pairs_path_value",
                                           weights={"adj.path_log2": 1.0})
    assert binding["evidence_kind"] == "admission" and binding["corpus_sha256"] == sha

    cases = {
        "trigger": admission_record(evidence_kind="trigger", corpus_sha=sha),
        "other-candidate": admission_record(candidate="chain_path_value", corpus_sha=sha),
        "other-weights": admission_record(weights={"adj.path_log2": 2.0}, corpus_sha=sha),
        "not-admitted": admission_record(admitted=False, corpus_sha=sha),
        "other-corpus": admission_record(corpus_sha="0" * 64),
    }
    for name, payload in cases.items():
        path = tmp_path / (name + ".json")
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        with pytest.raises(stage.StepFailed):
            stage.load_admission_binding(path, corpus, candidate="seven_pairs_path_value",
                                         weights={"adj.path_log2": 1.0})


# --- 12.3 阶段指标与统计口径 -------------------------------------------------


def test_admission_binding_says_which_kind_of_unusable_record_it_hit(tmp_path):
    """★ 取证式诊断（Challenger 2026-09-16 的可定位意见）：三种"不可用"必须**分开说**，
    且当场把可核事实（可见性／大小／内容 sha256）写进消息——否则下次发生时无法自证是哪一种。"""

    corpus = tmp_path / "corpus.jsonl"
    corpus.write_text("{}\n", encoding="utf-8")
    kwargs = {"candidate": "seven_pairs_path_value", "weights": {"adj.path_log2": 1.0}}

    missing = tmp_path / "not-there.json"
    with pytest.raises(stage.StepFailed) as absent:
        stage.load_admission_binding(missing, corpus, **kwargs)
    message = str(absent.value)
    assert "路径当时不可见或不是普通文件" in message and "取证" in message
    assert '"is_file": false' in message and "not-there.json" in message

    wrong_type = tmp_path / "array.json"
    wrong_type.write_text("[1, 2, 3]\n", encoding="utf-8")
    with pytest.raises(stage.StepFailed) as typed:
        stage.load_admission_binding(wrong_type, corpus, **kwargs)
    message = str(typed.value)
    assert "JSON 顶层不是对象" in message
    assert '"size": 10' in message and '"sha256"' in message     # 内容确实在，且被取证

    broken = tmp_path / "broken.json"
    broken.write_text("{not json", encoding="utf-8")
    with pytest.raises(stage.StepFailed) as malformed:
        stage.load_admission_binding(broken, corpus, **kwargs)
    assert "不是合法 JSON" in str(malformed.value)


def test_stage_metrics_follow_seat_accounting_and_place_points():
    """★ 阶段主指标的口径：晋级深度 × 10 + 决赛名次分；名次分只来自逐场账。"""

    def stage_record(stage_no, kind, role, order, advanced, points):
        rows = []
        for index, participant in enumerate(order):
            rows.append({"participants_by_seat": list(order),
                         "place_points_by_seat": list(points),
                         "scores_by_seat": [0, 0, 0, 0]})
            break
        return {"stage_no": stage_no, "kind": kind, "role": role,
                "seat_accounting": rows,
                "standings": [{"participant_id": item} for item in order],
                "advance": {"advanced": list(advanced)}}

    run = {"stages": [
        stage_record(1, "qualifying_global", "qualify", ["p01", "p02", "p03", "p04"],
                     ["p01", "p02"], [3, 1, -1, -3]),
        stage_record(2, "group_round", "qualify", ["p01", "p02", "p05", "p06"],
                     ["p01"], [3, 1, -1, -3]),
        stage_record(3, "final", "final", ["p02", "p01", "p03", "p04"], [], [3, 1, -1, -3]),
    ]}
    metrics = stage.stage_metrics(run, "p01")
    assert metrics["advanced_qualify_stages"] == 2
    assert metrics["reached_final"] is True and metrics["final_rank"] == 2
    assert metrics["stage_advance_score"] == 20 + (4 - 2 + 1)
    assert metrics["place_points_total"] == 3 + 3 + 1
    assert metrics["tables_played"] == 3


def test_stage_metrics_of_an_eliminated_participant():
    """★ 海选即淘汰 ⇒ 主指标 0（不给「未进决赛」编造名次）。"""

    run = {"stages": [{"stage_no": 1, "kind": "qualifying_global", "role": "qualify",
                       "seat_accounting": [{"participants_by_seat": ["p09", "p02", "p03", "p04"],
                                            "place_points_by_seat": [-3, 1, 3, -1],
                                            "scores_by_seat": [0, 0, 0, 0]}],
                       "standings": [{"participant_id": "p02"}, {"participant_id": "p09"}],
                       "advance": {"advanced": ["p02"]}}]}
    metrics = stage.stage_metrics(run, "p09")
    assert metrics["advanced_qualify_stages"] == 0
    assert metrics["reached_final"] is False and metrics["final_rank"] is None
    assert metrics["stage_advance_score"] == 0 and metrics["place_points_total"] == -3


def test_root_level_statistics_matches_the_scheduler():
    """★ 口径一致性用**断言**而不是「看起来一样」：本包不 import 调度器。"""

    values = [3.0, -1.0, 0.0, 5.0, 2.0]
    ours = stage.root_level_statistics(values)
    theirs = scheduler.root_statistics(values)
    for key in ("n_roots", "mean", "sd_root", "se_root", "mde", "rankable"):
        assert ours[key] == theirs[key], key
    assert stage.root_level_statistics([1.0])["rankable"] is False


# --- 12.4 配对阶段比较 -------------------------------------------------------


def test_compare_pairs_the_two_arms_on_identical_seeds(tmp_path):
    """★ 配对成立的前提：两臂**牌山集合逐字相同**，差别只在焦点参赛者的策略。"""

    payload, ledger, out_dir = run_compare(tmp_path, scenarios=2)
    assert payload["schema"] == stage.COMPARE_SCHEMA
    rows = payload["scenarios"]
    assert len(rows) == 2 and all(row["paired"] for row in rows)
    for row in rows:
        baseline = json.loads((out_dir / "scenarios" /
                               "scenario-{0:02d}".format(row["scenario_index"])
                               / "baseline" / "run.json").read_text(encoding="utf-8"))
        candidate = json.loads((out_dir / "scenarios" /
                                "scenario-{0:02d}".format(row["scenario_index"])
                                / "candidate" / "run.json").read_text(encoding="utf-8"))
        assert baseline["root_set_id"] == candidate["root_set_id"]
        assert [item["plan"]["seed"] for item in baseline["tables"]] == \
            [item["plan"]["seed"] for item in candidate["tables"]]
    assert payload["verdict"]["rankable"] is True
    assert payload["summary"][stage.PRIMARY_STAGE_METRIC]["n_roots"] == 2
    # 账目：每会话按实际桌数结算（9 桌／会话 × 2 臂 × 2 场景）。
    assert ledger.spent["tables"] == 36
    # 执行量按**自己的 schema** 交给编排者透传（不得与预算账同名）。
    execution = payload["execution"]
    assert execution["schema"] == "sitin-stage-ledger/1"
    assert execution["tables_spent"] == 36
    assert "sitin-search-ledger" not in json.dumps(execution)
    assert ledger.overruns == []


def test_compare_records_a_focus_improvement_as_a_positive_delta(tmp_path):
    """★ 焦点参赛者从垫底变第一 ⇒ 逐场景 Δ 与根级均值同为正（构造性正例）。"""

    payload, _ledger, _out = run_compare(tmp_path, focus_gain=200, scenarios=3)
    deltas = payload["summary"][stage.PRIMARY_STAGE_METRIC]["per_scenario"]
    assert deltas and all(item > 0 for item in deltas)
    assert payload["summary"][stage.PRIMARY_STAGE_METRIC]["mean"] > 0
    assert payload["scenarios"][0]["candidate"]["reached_final"] is True
    assert payload["scenarios"][0]["baseline"]["reached_final"] is False


def test_compare_is_not_rankable_when_one_arm_fails(tmp_path):
    """★ 单侧失败 ⇒ 整次比较不可排序（fail-closed），不得只拿成功的那一侧排名。"""

    payload, _ledger, _out = run_compare(tmp_path, fail_arms=("candidate",), scenarios=2)
    assert payload["verdict"]["rankable"] is False
    assert all(row["failure_kind"] == "one_sided_failure" for row in payload["scenarios"])
    assert payload["verdict"]["n_paired_scenarios"] == 0


def test_compare_records_symmetric_failure_as_void_without_dropping_samples(tmp_path):
    """★ 两臂同时失败 = 对称情形：记 void 并保留在产物里，不是「静默删样本」。"""

    payload, _ledger, _out = run_compare(tmp_path, fail_arms=("baseline", "candidate"),
                                         scenarios=2)
    assert payload["verdict"]["rankable"] is False
    assert all(row["failure_kind"] == "void_pair" for row in payload["scenarios"])
    assert all(row["failures"] for row in payload["scenarios"])


def test_whole_round_precheck_blocks_before_any_scenario_runs(tmp_path):
    """★ 整轮可行性预检：需要「场景数 × 每会话上界 × 臂数」，不足就**一个场景都不跑**。

    契约 §4.1 的「开跑前预检」按 Lead 裁定实现为**整轮**口径——让 9 桌花在不可能配对的
    场景上尤其贵（实测吞吐比历史慢约 5 倍），也免得半跑场景的记账规则被临时解释。
    但**报告必须落盘**（编排者按预留额保守计费要有据）。
    """

    payload, ledger, out_dir = run_compare(tmp_path, scenarios=2, tables=20)
    assert payload["status"] == "unrankable"
    assert payload["budget"]["precheck"] == "failed"
    assert payload["budget"]["required_tables"] == 40        # 2 场景 × 上界 10 桌 × 2 臂
    assert payload["budget"]["budget_tables"] == 20
    assert "整轮可行性预检未通过" in payload["budget"]["stop_reason"]
    assert all(row["failure_kind"] == "budget_precheck_failed" for row in payload["scenarios"])
    assert payload["tables"]["spent"] == 0                   # 一桌都没花
    assert ledger.spent["tables"] == 0 and ledger.reservations == []
    # 一个场景目录都没有，但报告仍然存在。
    assert not (out_dir / "scenarios").exists()
    assert (out_dir / stage.STAGE_COMPARE_REPORT).is_file()


def test_whole_round_precheck_passes_when_the_budget_covers_the_upper_bound(tmp_path):
    """★ 预检的上界口径：budget ≥ 场景数 × 上界 × 臂数 才放行（恰好相等也算通过）。"""

    payload, ledger, _out = run_compare(tmp_path, scenarios=2, tables=40)
    assert payload["budget"]["precheck"] == "passed"
    assert payload["budget"]["required_tables"] == 40
    assert payload["status"] == "complete"
    assert ledger.spent["tables"] == 36                      # 预检按上界，结算按实际


def test_stage_compare_report_matches_the_frozen_cross_package_contract(tmp_path):
    """★ 报告字段是**跨包约定**（STAGE-COMPARE-CONTRACT.md §3）：缺一即不可对账。"""

    payload, _ledger, out_dir = run_compare(tmp_path, scenarios=2)
    assert stage.STAGE_COMPARE_REPORT == "stage-compare.json"
    assert (out_dir / stage.STAGE_COMPARE_REPORT).is_file()
    for field in ("schema", "status", "arm", "baseline", "panel", "tables", "pairs",
                  "metrics", "verification", "wall_sec", "command", "versions"):
        assert field in payload, field
    assert payload["schema"] == "sitin-stage-compare/1"
    assert payload["status"] == "complete"
    for field in ("id", "candidate", "weights", "identity", "gate_record_sha256",
                  "admission_corpus_sha256"):
        assert field in payload["arm"], field
    for field in ("policy", "contract_sha256"):
        assert field in payload["baseline"], field
    for field in ("scenarios", "seeds", "seed_base", "participants", "focal", "panel_id"):
        assert field in payload["panel"], field
    assert len(payload["panel"]["seeds"]) == 2 and payload["panel"]["panel_id"].startswith(
        "stagecmp-")
    # 预留口径统一按**上界**（Lead 裁定）：planned = 场景 × 每会话上界 × 臂；
    # 结算只看 spent（实际）。expected 只作参考。
    assert payload["tables"]["spent"] == 36
    assert payload["tables"]["planned"] == 2 * 2 * 10          # max_overtime=1 ⇒ 上界 10 桌/会话
    assert payload["tables"]["expected"] == 36
    assert payload["verification"]["extra_tables"] == []
    assert payload["pairs"] == 2
    for field in ("primary", "unit", "baseline_value", "candidate_value", "delta",
                  "per_scenario"):
        assert field in payload["metrics"], field
    assert [item["seed"] for item in payload["metrics"]["per_scenario"]] == \
        payload["panel"]["seeds"]
    assert payload["verification"]["plan_ok"] is True
    assert payload["wall_sec"] >= 0
    assert payload["versions"]["tool"].endswith("sitin_stage.py")
    assert len(payload["versions"]["tool_sha256"]) == 64
    assert payload["execution"]["tables_spent"] == 36
    assert payload["execution"]["schema"] == "sitin-stage-ledger/1"


def test_declared_base_schedule_is_identical_for_both_arms():
    """★ 根因回归：**派生式里不得含臂标识** —— 基础赛程的场次号与 seed 对两臂逐字相同。

    这条守的是本项目硬要求「候选与基线用同一批牌山」。两臂的差别只有焦点那一位
    用的是候选槽名还是白名单名，**不得**影响场次号与 seed。
    """

    board = participants(9)
    candidate_members, slots = stage.build_scenario_participants(
        board, candidate_arm={"candidate": "seven_pairs_path_value",
                              "weights": {"adj.path_log2": 1.0}}, focal="p01")
    assert slots and candidate_members[0]["policy_name"] == stage.CANDIDATE_SLOT
    baseline_members, empty = stage.build_scenario_participants(
        board, candidate_arm=None, focal="p01")
    assert empty == {}
    for panel_seed in (2026102000, derive_like(123456)):
        left = stage.table_seed_map(stage.declared_base_plans(
            contract=contract(max_overtime=1), participants=baseline_members,
            panel_seed=panel_seed))
        right = stage.table_seed_map(stage.declared_base_plans(
            contract=contract(max_overtime=1), participants=candidate_members,
            panel_seed=panel_seed))
        assert left == right, "两臂的基础赛程必须逐字相同"
        assert len(left) == 9
    # 换场景种子必须换牌山（否则「场景」这个独立单位是假的）。
    other = stage.table_seed_map(stage.declared_base_plans(
        contract=contract(max_overtime=1), participants=baseline_members,
        panel_seed=2026102001))
    assert other != stage.table_seed_map(stage.declared_base_plans(
        contract=contract(max_overtime=1), participants=baseline_members,
        panel_seed=2026102000))


def derive_like(value):
    """测试用的另一个场景种子（走真实的派生式，避免手写魔数）。"""
    return stage.derive_scenario_seed(2026102000, value)


def test_execution_accounting_separates_missing_drift_and_official_overtime():
    """★ 三种对账结果必须**分开**：缺项/漂移 ⇒ 不可排序；多出来的（加赛）只记录。"""

    base = {"s1-b1-t1": 111, "s3-final-t1": 222}
    clean = stage.execution_accounting(base_seeds=base,
                                       executed_seeds={**base, "s3-final-ot1-t1": 333})
    assert clean["extra_tables"] == ["s3-final-ot1-t1"]
    assert clean["missing_base_tables"] == [] and clean["drifted_seeds"] == []
    missing = stage.execution_accounting(base_seeds=base, executed_seeds={"s1-b1-t1": 111})
    assert missing["missing_base_tables"] == ["s3-final-t1"]
    drifted = stage.execution_accounting(base_seeds=base,
                                         executed_seeds={"s1-b1-t1": 111, "s3-final-t1": 999})
    assert drifted["drifted_seeds"] == ["s3-final-t1"]


def test_overtime_in_one_arm_does_not_void_the_pair(tmp_path):
    """★ 官方加赛（得分决定 ⇒ 与策略有关）**不得**被当成配对失败——旧实现正是这样误废场景的。"""

    out_dir = tmp_path / "compare"
    ledger = ledger_for(tmp_path)
    payload = stage.run_stage_comparison(
        contract=contract(max_overtime=1),
        arm={"id": "a1", "candidate": "seven_pairs_path_value",
             "weights": {"adj.path_log2": 1.0}, "family": "测试族"},
        participants=participants(9), scenarios=1, seed_base=2026102000, out_dir=out_dir,
        ledger=ledger,
        admission={"record": "x", "record_sha256": "0" * 64, "corpus_sha256": "0" * 64,
                   "bound_identity": "t", "candidate": "seven_pairs_path_value",
                   "weights": {"adj.path_log2": 1.0}, "evidence_kind": "admission"},
        focal="p01", table_timeout_sec=1.0,
        runner_factory=overtime_runner_factory())
    row = payload["scenarios"][0]
    assert row["paired"] is True
    assert row["declared_base_tables"] == 9
    assert row["extra_tables_by_arm"]["baseline"] == []
    assert row["extra_tables_by_arm"]["candidate"] == ["s3-final-ot1-t1"]
    assert payload["verdict"]["rankable"] is True
    assert payload["verification"]["extra_tables"] == [
        {"scenario_index": 0, "arm": "candidate", "table_ids": ["s3-final-ot1-t1"]}]
    # 主指标照常算（加赛场次并入决赛总账是官方规则）。
    assert payload["metrics"]["per_scenario"][0]["delta"] is not None


def test_source_digest_is_captured_at_start_and_flagged_when_source_changes(tmp_path):
    """★ 指纹纪律的**时序漏洞**（Lead 裁定 F1）：跑完才读盘，会把"运行期间被改过的源码"
    标成它**从未执行过**的版本。这里注入一个"第二次调用返回不同指纹"的读取器来复现，
    要求：① 两次指纹都记下来；② 标志位为真；③ `versions.tool_sha256` 记的是**开跑前**那份。"""

    seen = []

    def reader():
        seen.append(1)
        return "a" * 64 if len(seen) == 1 else "b" * 64

    payload, _ledger, _out = run_compare(tmp_path, scenarios=1, digest_reader=reader)
    assert payload["source_digest_at_start"] == "a" * 64
    assert payload["source_digest_at_end"] == "b" * 64
    assert payload["tool_source_changed_during_run"] is True
    assert payload["versions"]["tool_sha256"] == "a" * 64      # 真正跑过的那份
    assert payload["versions"]["tool_sha256"] != payload["source_digest_at_end"]
    assert "开跑前捕获" in payload["versions"]["tool_sha256_rule"]


def test_source_digest_flag_is_false_with_timestamps_for_a_normal_run(tmp_path):
    """★ 常驻字段（不是特批）：正常运行的标志位为假，且起止时间与双指纹都在产物里。"""

    payload, _ledger, _out = run_compare(tmp_path, scenarios=1)
    assert payload["tool_source_changed_during_run"] is False
    assert payload["source_digest_at_start"] == payload["source_digest_at_end"]
    assert len(payload["source_digest_at_start"]) == 64
    assert payload["versions"]["tool_sha256"] == payload["source_digest_at_start"]
    for field in ("started_at", "finished_at"):
        assert payload[field].endswith("Z") and "T" in payload[field]
    assert payload["started_at"] <= payload["finished_at"]


def test_panel_id_is_recomputable_from_the_declaration_alone(tmp_path):
    """★ panel_id 必须只由**声明**复算（编排者要对账），不掺运行期偶然量。"""

    payload, _ledger, _out = run_compare(tmp_path, scenarios=2)
    recomputed = stage.panel_declaration_id(
        contract_sha256=payload["contract_sha256"],
        participants=participants(9), focal="p01", seed_base=2026102000,
        seeds=payload["panel"]["seeds"])
    assert recomputed == payload["panel"]["panel_id"]


def test_compare_command_line_records_a_rerunnable_argv():
    """★ 报告里的 command 要能原样复跑（编排者对账靠它，不靠记忆）。"""

    args = _compare_args()
    command = stage.compare_command_line(args)
    assert command[2] == "compare"
    for flag in ("--candidate", "--weights", "--gate-record", "--admission-corpus",
                 "--contract-file", "--scenarios", "--seed-base", "--participants",
                 "--budget-tables", "--out"):
        assert flag in command, flag
    parsed = stage.build_arg_parser().parse_args(command[2:])
    assert parsed.candidate == args.candidate and parsed.scenarios == args.scenarios


# ---------------------------------------------------------------------------
# 正式阶段执行器的阶段账注入（P13：复审 §5 M1 的第三处同类缺口）
#
# 缺陷：table-worker 子命令里的正式阶段执行器 execute_table 调 drive_match 时未传
# stage_situation，且父进程 run_tables_supervised 从不构造阶段账 → 3.0 run 与
# 3.4 compare 两条**正式评估路径**上，第 2 桌起的策略请求读不到已完成桌的阶段积分/
# 名次分（与自然面板 P2、AIVAT P12 同病；本处是第三例）。
#
# 契约（与自然面板逐字同约，单一实现 natp.build_stage_situation）：
#   * 第 1 桌 = 空账表头（stage_table_no=1、tables_completed=0、四席全 0）；
#   * 第 k 桌 = 前 k−1 桌累计，按「参赛者身份 → 物理座位」映射（plan.seats()），
#     **不含本桌**；换座后身份与座位一一对应，不串位；
#   * 无键 = 旧行为（None）：非阶段赛程的调用方零变化。
# ---------------------------------------------------------------------------


def versions_block(**contract_overrides):
    return stage.contract_versions_block(contract(**contract_overrides))


def rotating_plans(*, rounds=3, stage_no=1):
    """单组 4 人、每桌换座（rotate_permutation）的确定性赛程：用于四换座身份↔座位核对。"""

    members = [{"participant_id": "p0{0}".format(index + 1),
                "policy_name": "weighted_heuristic_v2"} for index in range(4)]
    return [
        stage.build_table_plan(
            stage_no=stage_no, stage_name="组内赛", stage_role="qualify",
            stage_kind="group_round", table_id="s{0}-g1-t{1}".format(stage_no, index + 1),
            participants=members, permutation=stage.rotate_permutation(index),
            seed=900 + index, tables_in_stage=rounds, group_index=1)
        for index in range(rounds)]


def cell_plan(out_dir, plan):
    """读回某场次**实际落盘**的 plan.json（子进程收到的就是这一份）。"""

    cell = Path(out_dir) / "tables" / stage.slug(plan.table_id) / "plan.json"
    return json.loads(cell.read_text(encoding="utf-8"))


class _SupervisedProcess:
    """受监管子进程的替身返回值（只提供 run_tables_supervised 会读的字段）。"""

    timed_out = False
    returncode = 0
    stdout = ""
    stderr = ""

    def to_json(self):
        return {"command": "替身", "returncode": 0, "timed_out": False,
                "stdout_bytes": 0, "stderr_bytes": 0}


class _ScriptedSupervisor:
    """受监管子进程替身：读回每桌落盘的计划载荷（含注入的阶段账），按脚本写回结果行。

    **不启动子进程、不跑真实桌赛**：只验注入编排与「身份 → 物理座位」映射。
    """

    def __init__(self, scores_by_table):
        self.scores_by_table = {int(key): tuple(int(value) for value in values)
                                for key, values in scores_by_table.items()}
        self.calls = []

    def run_supervised(self, command, cwd=None, timeout_sec=None):
        plan_path = Path(command[command.index("--plan") + 1])
        row_path = Path(command[command.index("--out") + 1])
        payload = json.loads(Path(plan_path).read_text(encoding="utf-8"))
        table_no = len(self.calls) + 1
        self.calls.append({"table_no": table_no, "table_id": payload["table_id"],
                           "plan_path": plan_path,
                           "stage_situation": payload.get("stage_situation")})
        scores = self.scores_by_table.get(table_no, (0, 0, 0, 0))
        row_path.write_text(json.dumps({
            "schema": stage.RUN_SCHEMA, "table_id": payload["table_id"],
            "stage_no": payload["stage_no"], "group_index": payload.get("group_index"),
            "wall_ms": 1.0, "match_status": "complete", "completed_hands": 2,
            "result": {"status": "complete", "scores_after": list(scores),
                       "policy_ids_by_seat": list(payload["participants_by_seat"]),
                       "invalid_reasons": []},
        }, ensure_ascii=False), encoding="utf-8")
        return _SupervisedProcess()


def test_run_tables_supervised_injects_the_completed_table_stage_account(monkeypatch, tmp_path):
    """★ P13 红→绿：逐桌注入已完成桌阶段账（第 1 桌空账、第 2 桌起累计、四换座不串位）。"""

    plans = rotating_plans(rounds=3)
    scripted = {1: (10, -4, 2, 6), 2: (5, 5, 5, 5), 3: (7, -1, 3, -9)}
    supervisor = _ScriptedSupervisor(scripted)
    monkeypatch.setattr(stage, "sibling", lambda name: supervisor)
    out_dir = tmp_path / "run"
    outcomes = stage.run_tables_supervised(
        out_dir=out_dir, timeout_sec=1.0, plan=plans, versions_block=versions_block(),
        timing=stage.DEFAULT_TIMING, step_limit=1)
    assert [item.status for item in outcomes] == ["complete"] * 3
    assert len(supervisor.calls) == 3

    injected = [cell_plan(out_dir, plan).get("stage_situation") for plan in plans]
    # 第 1 桌：**空账表头**（既不是缺键，也不是空字典）。
    first = injected[0]
    assert first is not None, "第 1 桌场次计划缺少阶段账注入（M1 同类缺陷复现）"
    assert first["stage_table_no"] == 1 and first["tables_completed"] == 0
    assert first["tables_in_stage"] == 3
    assert first["stage_scores_by_seat"] == [0, 0, 0, 0]
    assert first["place_points_by_seat"] == [0, 0, 0, 0]
    assert first["participant_ids_by_seat"] == list(plans[0].seats())

    # 逐桌核对：账 = **已完成桌**累计（测试内独立累计，不读实现内部状态）。
    totals, places = {}, {}
    for index, plan in enumerate(plans):
        situation = injected[index]
        assert situation is not None, "第 {0} 桌计划缺少阶段账注入".format(index + 1)
        assert situation["participant_ids_by_seat"] == list(plan.seats())
        assert situation["stage_table_no"] == index + 1
        assert situation["tables_completed"] == index
        assert situation["tables_in_stage"] == 3
        assert situation["stage_scores_by_seat"] == [totals.get(pid, 0) for pid in plan.seats()]
        assert situation["place_points_by_seat"] == [places.get(pid, 0) for pid in plan.seats()]
        scores = scripted[index + 1]
        points = stage.place_points_for_table(list(scores))
        for seat, participant in enumerate(plan.seats()):
            totals[participant] = totals.get(participant, 0) + int(scores[seat])
            places[participant] = places.get(participant, 0) + int(points[seat])

    # 四换座：物理座位序逐桌不同 ⇒ 若不按身份映射，下面几条必然对不上。
    assert list(plans[1].seats()) != list(plans[0].seats())
    assert list(plans[2].seats()) != list(plans[0].seats())
    # 第 2 桌 = 首桌账按**本桌物理座位**展开（p04/p01/p02/p03）。
    assert injected[1]["stage_scores_by_seat"] == [6, 10, -4, 2]
    assert injected[1]["place_points_by_seat"] == [1, 3, -3, -1]
    # 第 3 桌 = 前两桌累计（p03/p04/p01/p02）；并列桌四席名次分为 0。
    assert injected[2]["stage_scores_by_seat"] == [7, 11, 15, 1]
    assert injected[2]["place_points_by_seat"] == [-1, 1, 3, -3]
    # **不含本桌**：第 2/3 桌的账不得等于本桌自己的分数向量。
    assert injected[1]["stage_scores_by_seat"] != list(scripted[2])
    assert injected[2]["stage_scores_by_seat"] != list(scripted[3])


def test_run_tables_supervised_counts_only_completed_tables_in_one_stage(monkeypatch, tmp_path):
    """★ 账按阶段隔离：换阶段（stage_no 变化）重新从空账表头起算，不跨阶段累计。"""

    plans = rotating_plans(rounds=2, stage_no=1) + rotating_plans(rounds=2, stage_no=2)
    scripted = {1: (10, -4, 2, 6), 2: (5, 5, 5, 5), 3: (9, 9, 9, 9), 4: (1, 1, 1, 1)}
    supervisor = _ScriptedSupervisor(scripted)
    monkeypatch.setattr(stage, "sibling", lambda name: supervisor)
    out_dir = tmp_path / "run"
    stage.run_tables_supervised(out_dir=out_dir, timeout_sec=1.0, plan=plans,
                                versions_block=versions_block(),
                                timing=stage.DEFAULT_TIMING, step_limit=1)
    injected = [cell_plan(out_dir, plan).get("stage_situation") for plan in plans]
    assert [item["stage_table_no"] for item in injected] == [1, 2, 1, 2]
    assert [item["tables_completed"] for item in injected] == [0, 1, 0, 1]
    # 第二阶段首桌四席全 0：阶段清零，上一阶段账不得渗入。
    assert injected[2]["stage_scores_by_seat"] == [0, 0, 0, 0]
    assert injected[2]["place_points_by_seat"] == [0, 0, 0, 0]
    # 第二阶段第 2 桌只含本阶段首桌（9 分并列 ⇒ 四席名次分 0），不含第一阶段任何账。
    assert injected[3]["stage_scores_by_seat"] == [9, 9, 9, 9]
    assert injected[3]["place_points_by_seat"] == [0, 0, 0, 0]


def test_execute_table_forwards_stage_situation_to_drive_match(monkeypatch):
    """★ 通道：计划载荷里的阶段账逐字转交 drive_match；缺键 = 旧行为（None）。"""

    from hangma_bot.offline import evaluate as evaluate_module
    from hangma_bot.offline.evaluate import StageSituationProjection

    plan = rotating_plans(rounds=1)[0]
    situation = StageSituationProjection(
        stage_table_no=2, tables_in_stage=3, stage_role="qualify", tables_completed=1,
        rounds_per_game=2, stage_scores_by_seat=(6, 10, -4, 2),
        place_points_by_seat=(1, 3, -3, -1), participant_ids_by_seat=tuple(plan.seats()))
    payload = dict(plan.to_json())
    payload["versions"] = versions_block()
    payload["timing"] = dict(stage.DEFAULT_TIMING)
    payload["step_limit"] = 1
    payload["participants_by_seat"] = list(plan.seats())
    payload["policy_names_by_seat"] = list(plan.policy_names_by_seat())

    seen = []

    class _StopRun(Exception):
        pass

    async def fake_drive_match(**kwargs):
        seen.append(kwargs)
        raise _StopRun("记下驱动入参即可，不跑真实桌赛")

    monkeypatch.setattr(evaluate_module, "drive_match", fake_drive_match)

    with pytest.raises(_StopRun):
        stage.execute_table(dict(payload, stage_situation=situation.to_json()))
    assert len(seen) == 1
    forwarded = seen[0].get("stage_situation")
    assert isinstance(forwarded, StageSituationProjection), (
        "execute_table 未把阶段账转交 drive_match（M1 同类缺陷复现）")
    assert forwarded == situation
    assert forwarded.participant_ids_by_seat == tuple(plan.seats())

    with pytest.raises(_StopRun):
        stage.execute_table(dict(payload))          # 无键：既有调用零变化
    assert len(seen) == 2 and seen[1].get("stage_situation") is None


def test_stage_situation_from_json_round_trips_and_absent_key_is_none():
    """★ 载荷 → 投影的还原：逐字段等值；缺键/空值一律 None（不伪造空账）。"""

    from hangma_bot.offline.evaluate import StageSituationProjection

    payload = {
        "stage_table_no": 2, "tables_in_stage": 3, "stage_role": "qualify",
        "tables_completed": 1, "rounds_per_game": 2,
        "stage_scores_by_seat": [6, 10, -4, 2], "place_points_by_seat": [1, 3, -3, -1],
        "participant_ids_by_seat": ["p04", "p01", "p02", "p03"],
        "tables_remaining_after_current": 1,
        "god_count_modeling": "offline_unavailable_modeled_zero_not_used_for_u",
    }
    restored = stage.stage_situation_from_json(payload)
    assert isinstance(restored, StageSituationProjection)
    assert restored.stage_table_no == 2 and restored.tables_completed == 1
    assert restored.tables_in_stage == 3 and restored.rounds_per_game == 2
    assert restored.stage_scores_by_seat == (6, 10, -4, 2)
    assert restored.place_points_by_seat == (1, 3, -3, -1)
    assert restored.participant_ids_by_seat == ("p04", "p01", "p02", "p03")
    assert stage.stage_situation_from_json(None) is None
    assert stage.stage_situation_from_json({}) is None


def test_stage_account_mode_is_the_natural_panel_single_implementation():
    """★ 口径单一：口径名取自自然面板（P2 的单一实现），不复制语义、不另立名字。"""

    natural = _load("sitin_natural_panel")
    assert stage.stage_account_mode() == natural.STAGE_ACCOUNT_MODE
    assert isinstance(stage.stage_account_mode(), str) and stage.stage_account_mode()


#: 逐桌驱动入口名：**桌执行入口**就是把策略送上桌的那一层（阶段账必须在这里进通道）。
DRIVER_ENTRY_NAMES = ("drive_match", "resume_match", "run_match_experiment")

#: 明确判定「不适用阶段账」的驱动入口（依据见 P13 FIX-REPORT §1 全类扫描表）：
#: run_match_experiment 是**同牌山复式对照**（seed × 换座 × 双臂），每次 run 都是互相
#: 独立的单桌复制，不是阶段赛程；给它注入「已完成桌账」等于伪造阶段推进。
DRIVER_ENTRIES_NOT_APPLICABLE = {"run_match_experiment"}


def driver_calls(path):
    """AST 取驱动**调用**（docstring/注释里的同名文字不算调用），含所在函数名。"""

    import ast  # 只在本用例内用到：按 AST 精确取调用点，不用文本扫描

    tree = ast.parse(Path(path).read_text(encoding="utf-8"))
    functions = [(node.lineno, node.end_lineno or node.lineno, node.name)
                 for node in ast.walk(tree)
                 if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))]
    calls = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
        if name not in DRIVER_ENTRY_NAMES:
            continue
        enclosing = ""
        for start, end, function_name in functions:
            if start <= node.lineno <= end and (not enclosing
                                                or start > enclosing[0]):
                enclosing = (start, function_name)
        calls.append((name, enclosing[1] if enclosing else "<module>", node))
    return calls


def test_every_table_driver_call_site_forwards_the_stage_account():
    """★ 关闭**这一类**缺陷：tools/ 与 src/ 里每个逐桌驱动调用点都必须注入阶段账。

    新接入一个桌执行入口而不传 stage_situation ⇒ 本用例红（P2 自然面板 / P12 AIVAT /
    P13 正式阶段执行器 三处同类缺口的共同护栏）。判定「不适用」的驱动入口必须在
    DRIVER_ENTRIES_NOT_APPLICABLE 里显式列出并写明依据，不允许静默放过。
    """

    import ast

    review_root = _project_file(_PROJECT_ROOT, _REPO / "review" / "llm-guided-heuristic-route-2026-09-15")
    targets = sorted(path for path in _HERE.glob("*.py")
                     if not path.name.startswith("test_"))
    targets += sorted(path for path in (_project_file(_PROJECT_ROOT, _REPO / "src")).rglob("*.py")
                      if "__pycache__" not in path.parts)
    checked, offenders, seen_entries = 0, [], set()
    for path in targets:
        for name, enclosing, node in driver_calls(path):
            checked += 1
            seen_entries.add(name)
            # 调用方侧（谁调它）与实现侧（它内部调 drive_match）都按同一张不适用表放行。
            if name in DRIVER_ENTRIES_NOT_APPLICABLE \
                    or enclosing in DRIVER_ENTRIES_NOT_APPLICABLE:
                continue
            forwarded = next((keyword for keyword in node.keywords
                              if keyword.arg == "stage_situation"), None)
            if forwarded is not None and not (isinstance(forwarded.value, ast.Constant)
                                              and forwarded.value.value is None):
                continue                      # 通道在（且不是硬关掉的 None）
            relative = (str(path.relative_to(review_root)) if str(path).startswith(str(_HERE))
                        else str(path.relative_to(_REPO)))
            offenders.append("{0}:{1} {2}() 内 {3}(...) 未传 stage_situation".format(
                relative, node.lineno, enclosing, name))
    assert checked >= 5, "扫描面过窄（应覆盖 tools/ 与 src/ 的全部驱动调用点）"
    assert seen_entries >= {"drive_match", "resume_match"}, "扫描面漏了驱动入口"
    assert not offenders, ("桌执行入口未注入阶段账（M1 同类缺口）：" + chr(10)
                           + chr(10).join(offenders))
