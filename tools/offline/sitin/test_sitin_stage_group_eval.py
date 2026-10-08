"""group_advance_v1 目标合同接入 sitin_stage 的确定性测试（T14 / T15 / 合同校验 / 端到端）。

对应 SEARCH-SPACE-REDESIGN-2026-09-16.md §14 的两条验收：

- **T14**：前二 U、正积分、联合事件与旧阶段代理分 stage_advance_score 在构造样例上
  给出**不同**结果——四个指标混为一谈即是偏移。
- **T15**：同分缺 god_count 时保留**识别区间**三态（[1,1] / [0,0] / [0,1]），
  不删根、不补零、不按 participant_id 任意排位；自比较配对差恒 0。

本文件独立于 test_sitin_stage.py / test_sitin_search.py（在途修复互不干扰），
不跑任何真实桌赛或模型，全部为纯计算与命令级断言。
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

import pytest

_HERE = Path(__file__).resolve().parent
_REPO = _PROJECT_ROOT
sys.path.insert(0, str(_project_file(_PROJECT_ROOT, _REPO / "src")))
sys.path.insert(0, str(_HERE))

CONTRACT_PATH = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/contracts/group-dev-v1.json')


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, _project_file(_PROJECT_ROOT, _HERE / "sitin_stage.py"))
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


stage = _load("sitin_stage_group_eval_under_test")


def row(pid: str, total: int, points: int = 0, god=None):
    """构造一行阶段账（god_count 默认 None：离线不可复现，不补零）。"""

    return stage.LedgerRow(participant_id=pid, total_score=total, place_points=points,
                           god_count=god)


def ledger_file(tmp_path: Path, rows) -> Path:
    """把构造账本写成 JSON 文件（LedgerRow 形状：god_count 可空）。"""

    payload = [{"participant_id": r.participant_id, "total_score": r.total_score,
                "place_points": r.place_points, "tables_played": r.tables_played,
                "byes": r.byes, "god_count": r.god_count} for r in rows]
    path = tmp_path / "ledger.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def run_group_eval(tmp_path: Path, rows, focal: str, capsys):
    ledger = ledger_file(tmp_path, rows)
    code = stage.main(["group-eval", "--contract-file", str(CONTRACT_PATH),
                       "--ledger", str(ledger), "--focal", focal])
    payload = json.loads(capsys.readouterr().out)
    return code, payload


# ---------------------------------------------------------------------------
# T14：四个指标必须可区分
# ---------------------------------------------------------------------------


def test_t14_top_two_and_positive_net_score():
    """焦点严格第 1 且净分为正：U=[1,1]、positive_net=1、联合事件=1。"""

    rows = [row("f1", 30), row("a", 10), row("b", 0), row("c", -10)]
    utility = stage.group_advance_utility(rows, focal_id="f1")
    assert (utility["u_low"], utility["u_high"], utility["unresolved"]) == (1, 1, False)
    auxiliary = stage.auxiliary_stage_reports(rows)
    assert auxiliary["positive_net_score"]["f1"] is True


def test_t14_top_two_but_negative_net_score():
    """焦点第 1 但净分为负：U=[1,1] 而 positive_net=0——U 与正积分不是同一个目标。"""

    rows = [row("f1", -5), row("a", -10), row("b", -20), row("c", -30)]
    utility = stage.group_advance_utility(rows, focal_id="f1")
    assert (utility["u_low"], utility["u_high"]) == (1, 1)
    auxiliary = stage.auxiliary_stage_reports(rows)
    assert auxiliary["positive_net_score"]["f1"] is False


def test_t14_third_place_but_positive_net_score():
    """焦点严格第 3 但净分为正：U=[0,0] 而 positive_net=1——两目标可以反向。"""

    rows = [row("a", 40), row("b", 30), row("f1", 20), row("c", 10)]
    utility = stage.group_advance_utility(rows, focal_id="f1")
    assert (utility["u_low"], utility["u_high"], utility["unresolved"]) == (0, 0, False)
    auxiliary = stage.auxiliary_stage_reports(rows)
    assert auxiliary["positive_net_score"]["f1"] is True


def test_t14_joint_event_via_command(tmp_path, capsys):
    """联合事件（前二且正积分）单独报告：三个样例分别得 1 / 0 / 0，不与 U 相加。"""

    ledgers = (
        ([row("f1", 30), row("a", 10), row("b", 0), row("c", -10)], (1, 1)),
        ([row("f1", -5), row("a", -10), row("b", -20), row("c", -30)], (0, 0)),
        ([row("a", 40), row("b", 30), row("f1", 20), row("c", 10)], (0, 0)),
    )
    for rows, expected in ledgers:
        code, payload = run_group_eval(tmp_path, rows, "f1", capsys)
        assert code == 0 and payload["ok"] is True
        joint = payload["focal_advance_and_positive"]
        assert (joint["low"], joint["high"]) == expected


def test_t14_legacy_proxy_score_differs_from_u():
    """旧 stage_advance_score 依赖 participant_id 字典序兜底，U 不依赖：同分样例上二者不同。"""

    # 同一组 (total_score, place_points)：top=(50,3)、并列二三人=(20,1)、末位=(0,-1)。
    # 只改并列两人的身份名，旧代理分随之翻转（11 vs −1），U 区间始终 [0,1] 未解决。
    # 变体 A：焦点 f1 字典序领先并列者 zz；变体 B：焦点 f1 字典序落后并列者 aa。
    variant_a = [row("top", 50, 3), row("f1", 20, 1), row("zz", 20, 1), row("low", 0, -1)]
    variant_b = [row("top", 50, 3), row("aa", 20, 1), row("f1", 20, 1), row("low", 0, -1)]
    legacy_a = stage.auxiliary_stage_reports(variant_a)["stage_advance_score_reference"]
    legacy_b = stage.auxiliary_stage_reports(variant_b)["stage_advance_score_reference"]
    assert legacy_a["note"] == "legacy_proxy_only_not_goal"
    assert legacy_a["values"]["f1"] == 11          # 字典序兜底把 f1 排进前二：10+1
    assert legacy_b["values"]["f1"] == -1          # 同分但身份靠后被排到第 3：0+(−1)
    utility_a = stage.group_advance_utility(variant_a, focal_id="f1")
    utility_b = stage.group_advance_utility(variant_b, focal_id="f1")
    assert (utility_a["u_low"], utility_a["u_high"], utility_a["unresolved"]) == (0, 1, True)
    assert (utility_b["u_low"], utility_b["u_high"], utility_b["unresolved"]) == (0, 1, True)
    # 旧代理把未解决并列写成确定标量；U 的输出里没有任何旧代理字段。
    assert set(utility_a) == {"focal_id", "u_low", "u_high", "unresolved",
                              "a", "b", "tie_block", "policy"}


# ---------------------------------------------------------------------------
# T15：识别区间三态与红线
# ---------------------------------------------------------------------------


def test_t15_no_ties_first_and_third():
    """无并列：焦点第 1 → [1,1]；焦点第 3 → [0,0]（名次分也构成严格序）。"""

    first = [row("f1", 30, 3), row("a", 30, 1), row("b", 10), row("c", 0)]
    utility = stage.group_advance_utility(first, focal_id="f1")
    assert (utility["u_low"], utility["u_high"], utility["unresolved"], utility["a"],
            utility["b"]) == (1, 1, False, 1, 1)
    third = [row("a", 40), row("b", 30), row("f1", 20), row("c", 10)]
    utility = stage.group_advance_utility(third, focal_id="f1")
    assert (utility["u_low"], utility["u_high"], utility["unresolved"], utility["a"],
            utility["b"]) == (0, 0, False, 3, 3)


def test_t15_tie_block_wholly_above_boundary():
    """并列块整体在前二（两人并列第 1-2），焦点严格第 3：焦点不在块内，按严格比较即 [0,0]。"""

    rows = [row("x1", 30), row("x2", 30), row("f1", 10), row("low", 0)]
    utility = stage.group_advance_utility(rows, focal_id="f1")
    assert (utility["u_low"], utility["u_high"], utility["unresolved"], utility["a"],
            utility["b"]) == (0, 0, False, 3, 3)


def test_t15_focal_tied_at_ranks_1_2():
    """焦点与一人并列第 1-2（b=2 ≤ 2）：块内最好最差都进前二 → [1,1]。"""

    rows = [row("f1", 30), row("a", 30), row("b", 10), row("c", 0)]
    utility = stage.group_advance_utility(rows, focal_id="f1")
    assert (utility["u_low"], utility["u_high"], utility["unresolved"], utility["a"],
            utility["b"]) == (1, 1, False, 1, 2)
    assert utility["tie_block"] == ["a", "f1"]


def test_t15_focal_tied_at_ranks_2_3():
    """焦点与一人并列第 2-3（a=2, b=3）：跨界 → [0,1] 且 unresolved=true。"""

    rows = [row("top", 50), row("f1", 20), row("a", 20), row("low", 0)]
    utility = stage.group_advance_utility(rows, focal_id="f1")
    assert (utility["u_low"], utility["u_high"], utility["unresolved"], utility["a"],
            utility["b"]) == (0, 1, True, 2, 3)


def test_t15_focal_tied_at_ranks_2_4():
    """焦点与两人并列第 2-4（a=2, b=4）：仍是跨界三态 [0,1]。"""

    rows = [row("top", 50), row("f1", 20), row("a", 20), row("b", 20)]
    utility = stage.group_advance_utility(rows, focal_id="f1")
    assert (utility["u_low"], utility["u_high"], utility["unresolved"], utility["a"],
            utility["b"]) == (0, 1, True, 2, 4)
    assert utility["tie_block"] == ["a", "b", "f1"]


def test_t15_tie_block_with_best_rank_3():
    """并列块 a=3（焦点最好也是第 3）：a > 2 → [0,0]，不需要身份序参与判定。"""

    rows = [row("top", 50), row("second", 40), row("f1", 20), row("a", 20)]
    utility = stage.group_advance_utility(rows, focal_id="f1")
    assert (utility["u_low"], utility["u_high"], utility["unresolved"], utility["a"],
            utility["b"]) == (0, 0, False, 3, 4)


def test_t15_interval_path_never_reads_identity_order_or_fills_god():
    """红线：区间与 U 不读 participant_id 排序；god_count=None 不触发补零；块成员完整。"""

    base = [row("aa", 50, 3), row("bb", 20, 1), row("cc", 20, 1), row("dd", 0, -1)]

    def by_id(rows):
        return {item["participant_id"]: (item["a"], item["b"], tuple(item["tie_block"]))
                for item in stage.group_advance_intervals(rows)}

    # 输入行序不影响结果（区间按身份键控比较，不依赖输入顺序）。
    assert by_id(list(reversed(base))) == by_id(base)
    # 改名（并列成员字典序相对关系翻转）不改变各自区间：a/b 只由两键决定。
    renamed = [row("z9", 50, 3), row("z2", 20, 1), row("a1", 20, 1), row("dd", 0, -1)]
    renamed_map = by_id(renamed)
    # 区间 (a,b) 不变；tie_block 内容随改名更新为新的并列成员集合。
    assert renamed_map["z2"][:2] == by_id(base)["bb"][:2] == (2, 3)
    assert renamed_map["a1"][:2] == by_id(base)["cc"][:2] == (2, 3)
    assert renamed_map["z2"][2] == renamed_map["a1"][2] == ("a1", "z2")
    # god_count 任意取值都不改变区间；区间输出里也没有任何补零的 god_count 字段。
    filled = [row("aa", 50, 3, god=9), row("bb", 20, 1, god=0),
              row("cc", 20, 1, god=7), row("dd", 0, -1, god=1)]
    assert by_id(filled) == by_id(base)
    for item in stage.group_advance_intervals(base):
        assert "god_count" not in item
    # 纯函数不改动输入：god_count 仍为 None（没有被补成 0）。
    assert [r.god_count for r in base] == [None, None, None, None]
    # 并列块成员完整：块内每人的 tie_block 恰是全部同签名参赛者。
    blocks = by_id(base)
    assert blocks["bb"][2] == ("bb", "cc") and blocks["cc"][2] == ("bb", "cc")
    assert blocks["aa"][2] == ("aa",) and blocks["dd"][2] == ("dd",)


def test_t15_self_comparison_paired_difference_is_zero():
    """自比较：同一账本两次求值（含打乱输入行序）配对差恒 0，不会变成 [-1,1]。"""

    rows = [row("aa", 50, 3), row("bb", 20, 1), row("cc", 20, 1), row("dd", 0, -1)]
    first = stage.group_advance_utility(rows, focal_id="bb")
    second = stage.group_advance_utility(rows, focal_id="bb")
    shuffled = stage.group_advance_utility(list(reversed(rows)), focal_id="bb")
    for other in (second, shuffled):
        assert first["u_low"] - other["u_low"] == 0
        assert first["u_high"] - other["u_high"] == 0
        assert first["unresolved"] == other["unresolved"] is True


# ---------------------------------------------------------------------------
# 合同校验：group-dev-v1 通过；破坏 mode / objective / ladder / 引文被拒
# ---------------------------------------------------------------------------


def load_contract():
    return json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))


def test_group_dev_contract_passes_validation():
    """group-dev-v1.json 整体通过 validate_contract（含引文逐条对快照核对）。"""

    assert stage.validate_contract(load_contract()) == []


def test_contract_mode_removed_is_rejected():
    """去掉 mode=group_only：退回官方档位纪律（最后阶段必须是决赛 + 内建引文集）。"""

    contract = load_contract()
    del contract["mode"]
    problems = stage.validate_contract(contract)
    assert problems != []
    assert any("最后阶段必须是决赛" in item for item in problems)


def test_contract_objective_variants_are_rejected():
    """objective 三个关键字段被破坏时逐条报问题。"""

    for field, bad in (("target_id", "joint_target_v1"), ("advance_count", 3),
                       ("missing_key_policy", "zero_fill")):
        contract = load_contract()
        contract["objective"][field] = bad
        problems = stage.validate_contract(contract)
        assert any(field in item for item in problems), (field, problems)


def test_contract_ladder_variants_are_rejected():
    """ladder 结构偏离 group_only 声明（档数/阶段数/groups/group_size/group_advance）被拒。"""

    def problems_after(mutate):
        contract = load_contract()
        mutate(contract)
        return stage.validate_contract(contract)

    assert any("恰一档" in item for item in
               problems_after(lambda c: c["ladder"].append(dict(c["ladder"][0]))))
    assert any("恰一个阶段" in item for item in problems_after(
        lambda c: c["ladder"][0]["stages"].append(dict(c["ladder"][0]["stages"][0]))))
    assert any("groups" in item for item in
               problems_after(lambda c: c["ladder"][0]["stages"][0].update(groups=2)))
    assert any("group_size" in item for item in
               problems_after(lambda c: c["ladder"][0]["stages"][0].update(group_size=8)))
    assert any("group_advance" in item for item in
               problems_after(lambda c: c["ladder"][0]["stages"][0].update(group_advance=3)))


def test_contract_citation_excerpt_mismatch_is_rejected():
    """引文 excerpt 被篡改时，逐条快照比对必须失败（fail-closed）。"""

    contract = load_contract()
    contract["rule_citations"][0]["excerpt"] = "这段原文不存在于快照里"
    problems = stage.validate_contract(contract)
    assert any("引文" in item and "第 377 行" in item for item in problems)


# ---------------------------------------------------------------------------
# 端到端：cmd_group_eval 与 cmd_check
# ---------------------------------------------------------------------------


def test_group_eval_end_to_end_ok(tmp_path, capsys):
    """命令级求值：严格 JSON 输出（合同 sha、焦点 U、全员区间表、辅助指标）。"""

    rows = [row("f1", 30), row("a", 10), row("b", 0), row("c", -10)]
    code, payload = run_group_eval(tmp_path, rows, "f1", capsys)
    assert code == 0
    assert payload["ok"] is True
    assert payload["schema"] == "sitin-group-eval/1"
    assert payload["target_id"] == "group_advance_v1"
    assert payload["advance_count"] == 2
    # 合同摘要与 contract_text 口径一致（可复算）。
    assert payload["contract_sha256"] == stage.sha256_text(
        stage.contract_text(load_contract()))
    assert len(payload["contract_sha256"]) == 64
    utility = payload["focal_utility"]
    assert (utility["u_low"], utility["u_high"], utility["policy"]) == (
        1, 1, "recognition_interval")
    assert {item["participant_id"] for item in payload["intervals"]} == {"f1", "a", "b", "c"}
    auxiliary = payload["auxiliary"]
    assert auxiliary["positive_net_score"] == {"f1": True, "a": True, "b": False, "c": False}
    assert auxiliary["stage_advance_score_reference"]["note"] == "legacy_proxy_only_not_goal"


def test_group_eval_focal_missing_exits_2(tmp_path, capsys):
    """焦点不在账本：{"ok": false, "problems": [...]} + 退出码 2。"""

    rows = [row("a", 30), row("b", 10), row("c", 0), row("d", -10)]
    code, payload = run_group_eval(tmp_path, rows, "nope", capsys)
    assert code == 2
    assert payload["ok"] is False
    assert any("不在账本" in item for item in payload["problems"])


def test_group_eval_without_objective_exits_2(tmp_path, capsys):
    """合同无 objective 键：{"ok": false} + 退出码 2（objective 是求值的必需输入）。"""

    contract = load_contract()
    del contract["objective"]
    del contract["provenance"]["objective"]     # 同步摘除 dangling 出处，隔离变量
    contract_path = tmp_path / "no-objective.json"
    contract_path.write_text(json.dumps(contract, ensure_ascii=False), encoding="utf-8")
    ledger = ledger_file(tmp_path, [row("f1", 30), row("a", 10), row("b", 0), row("c", -10)])
    code = stage.main(["group-eval", "--contract-file", str(contract_path),
                       "--ledger", str(ledger), "--focal", "f1"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 2
    assert payload["ok"] is False
    assert any("objective" in item for item in payload["problems"])


def test_cmd_check_group_dev_contract_ok(capsys):
    """check 子命令端到端：group-dev-v1.json 引文比对通过，ok:true、退出码 0。"""

    code = stage.main(["check", "--contract-file", str(CONTRACT_PATH)])
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload == {"ok": True, "problems": []}


# ---------------------------------------------------------------------------
# 接线：_stage_record 在 group_advance_v1 合同下附加区间与 U（standings 原样）
# ---------------------------------------------------------------------------


def _table(records, scores):
    ids = [item["participant_id"] for item in records]
    plan = stage.build_table_plan(
        stage_no=1, stage_name="开发组", stage_role="qualify", stage_kind="group_round",
        table_id="s1-t1", participants=records, permutation=stage.IDENTITY_PERMUTATION,
        seed=20260916, tables_in_stage=1, group_index=0, batch_index=0)
    outcome = stage.TableOutcome(table_id="s1-t1", status="complete",
                                 participant_ids_by_seat=plan.seats(),
                                 scores_by_seat=tuple(scores), seed=20260916)
    return plan, outcome


def test_stage_record_attaches_intervals_and_utilities():
    """group_advance_v1 + group_round：记录附加全员区间与 U；无 objective 的合同不附加。"""

    records = [{"participant_id": pid, "policy_name": "weighted_heuristic_v2"}
               for pid in ("f1", "a", "b", "c")]
    plan, outcome = _table(records, (30, 20, 20, 0))
    contract = load_contract()
    orchestrator = stage.StageOrchestrator(
        contract=contract, participants=records,
        run_tables=lambda planned: [outcome])
    record = orchestrator._stage_record(
        stage_no=1, spec=dict(contract["ladder"][0]["stages"][0]),
        participants=[item["participant_id"] for item in records], plan=[plan],
        outcomes={outcome.table_id: outcome}, byes={})
    assert record["kind"] == "group_round"
    # standings 保持旧形状（rank/tie_unresolved 仍由 rank_ledger 生成，不被改写）。
    assert {key in record["standings"][0] for key in ("rank", "tie_unresolved")} == {True}
    intervals = {item["participant_id"]: (item["a"], item["b"])
                 for item in record["advance_intervals"]}
    assert intervals == {"f1": (1, 1), "a": (2, 3), "b": (2, 3), "c": (4, 4)}
    utilities = {item["focal_id"]: (item["u_low"], item["u_high"], item["unresolved"])
                 for item in record["advance_utilities"]}
    assert utilities == {"f1": (1, 1, False), "a": (0, 1, True), "b": (0, 1, True),
                         "c": (0, 0, False)}
    # 对照：默认（非 group_only、无 objective）合同不触发附加字段。
    default = stage.default_contract(ruleset_version="test-ruleset", base_score=1,
                                     you_cai_bi_kao=False, rounds_per_game=2,
                                     frozen_at="2026-09-16")
    plain = stage.StageOrchestrator(
        contract=default, participants=records, run_tables=lambda planned: [outcome])
    plain_record = plain._stage_record(
        stage_no=1, spec=dict(default["ladder"][-1]["stages"][0]),
        participants=[item["participant_id"] for item in records], plan=[plan],
        outcomes={outcome.table_id: outcome}, byes={})
    assert "advance_intervals" not in plain_record
    assert "advance_utilities" not in plain_record
