"""坐隐 2.4 调度器自测：台账、根级统计、**到预算即停**。

重点守两件容易写错的事：
  1. 独立单位是**根组**——不得用"配对×双臂"推标准误（初版 §1.2 犯过的错）；
  2. 预算台账**独立于日志**，且**先记账后执行**——不足时显式停止，不静默扩容
     （MEoH 把计数器挂在可选 profiler 里，不挂就永不停止，见 vendor/LLM4AD meoh.py:158-163）。
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

import contextlib
import importlib.util
import io
import json
import math
import sys
import time
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
_REPO = _PROJECT_ROOT
sys.path.insert(0, str(_HERE))

spec = importlib.util.spec_from_file_location("sitin_scheduler", _project_file(_PROJECT_ROOT, _HERE / "sitin_scheduler.py"))
sched = importlib.util.module_from_spec(spec)
sys.modules["sitin_scheduler"] = sched
assert spec.loader is not None
spec.loader.exec_module(sched)


# --- 根级统计：独立单位必须是根，不是配对 -----------------------------------

def test_root_statistics_uses_roots_as_the_unit_not_pairs():
    """16 根、每根 2 个换座 ⇒ 独立单位是 **16**，SE = sd/4，不是 sd/sqrt(32)。"""

    deltas = [-40.0, -60.0, -20.0, -80.0, -50.0, -30.0, -70.0, -45.0,
              -55.0, -35.0, -65.0, -25.0, -75.0, -42.0, -58.0, -48.0]
    stats = sched.root_statistics(deltas)
    assert stats["n_roots"] == 16
    assert stats["se_root"] == pytest.approx(stats["sd_root"] / math.sqrt(16), rel=1e-9)
    pair_based = stats["sd_root"] / math.sqrt(32)
    assert stats["se_root"] > pair_based, "用配对数会假性变窄——这正是要防的错误"


def test_root_statistics_withholds_on_a_single_root():
    stats = sched.root_statistics([1.0])
    assert stats["sd_root"] is None and stats["mde"] is None


def test_mean_by_root_averages_within_a_root():
    pairs = [{"scenario_id": "a", "delta": 10.0}, {"scenario_id": "a", "delta": 20.0},
             {"scenario_id": "b", "delta": -5.0}]
    assert sched.mean_by_root(pairs) == [15.0, -5.0]


# --- 台账：独立、先记账、不足即停 -------------------------------------------

def test_ledger_reserves_before_running_and_persists(tmp_path):
    ledger = sched.BudgetLedger(table_budget=200, path=tmp_path / "ledger.json")
    tables = ledger.reserve("第一轮", ["c1", "c2"], roots=16, seats=1,
                            root_keys=["scale-0", "scale-1"])
    # 16 根 × 1 换座 × 2 臂 × 2 候选 = 64 桌
    assert tables == 64
    assert ledger.spent_tables == 64
    assert ledger.remaining_tables == 136
    on_disk = json.loads((tmp_path / "ledger.json").read_text(encoding="utf-8"))
    assert on_disk["spent_tables"] == 64, "台账必须**落盘**，与日志无关"


def test_ledger_refuses_to_exceed_budget_instead_of_expanding(tmp_path):
    ledger = sched.BudgetLedger(table_budget=10, path=tmp_path / "ledger.json")
    with pytest.raises(sched.BudgetExceeded) as info:
        ledger.reserve("第一轮", ["c1"], roots=16, seats=1, root_keys=["scale-0"])
    assert "不静默扩容" in str(info.value)
    assert ledger.spent_tables == 0, "被拒绝时不得留下已花费的记账"


def test_ledger_round_trip(tmp_path):
    path = tmp_path / "ledger.json"
    first = sched.BudgetLedger(table_budget=100, path=path)
    first.reserve("第一轮", ["c1"], roots=4, seats=1, root_keys=["scale-0", "scale-1"])
    second = sched.BudgetLedger.load(path)
    assert second.table_budget == 100
    assert second.spent_tables == first.spent_tables
    assert second.consumed_root_keys == first.consumed_root_keys


# --- 到预算即停 -------------------------------------------------------------

def test_plan_round_stops_when_budget_is_insufficient():
    ledger = sched.BudgetLedger(table_budget=100)
    decision = sched.plan_round(ledger, ["c1", "c2"], sched.ROUND_SPECS[1],
                                ["r{0}".format(i) for i in range(64)])
    assert decision["decision"] == "stop"
    assert "预算不足" in decision["reason"]


def test_plan_round_stops_when_there_are_not_enough_roots():
    ledger = sched.BudgetLedger(table_budget=10 ** 6)
    decision = sched.plan_round(ledger, ["c1"], sched.ROUND_SPECS[1], ["only-one"])
    assert decision["decision"] == "stop"
    assert "根组不足" in decision["reason"]


def test_find_stop_reports_the_first_unaffordable_round():
    """第二轮要 64 根 × 4 换座 × 2 臂 × 存活数，预算只够第一轮 ⇒ 停在第二轮。"""

    ledger = sched.BudgetLedger(table_budget=200)
    stop = sched.find_stop(ledger, ["c1", "c2"], sched.ROUND_SPECS,
                           ["r{0}".format(i) for i in range(64)])
    assert stop["decision"] == "stop"
    assert stop["round"] == "第二轮" or "预算不足" in stop["reason"]


def test_find_stop_runs_when_the_budget_covers_every_round():
    ledger = sched.BudgetLedger(table_budget=10 ** 6)
    stop = sched.find_stop(ledger, ["c1"], sched.ROUND_SPECS,
                           ["r{0}".format(i) for i in range(64)])
    assert stop["decision"] == "run"


# --- 淘汰只作预算分配，且必须守住"保留数"的语义 -----------------------------

def test_select_survivors_keeps_ceiling_of_half():
    # 注意：能进排序的候选必须显式带 rankable=True（R7-2 之后的新契约）。
    results = {"c1": {"mean": 5.0, "rankable": True},
               "c2": {"mean": 3.0, "rankable": True},
               "c3": {"mean": 1.0, "rankable": True}}
    assert sched.select_survivors(results, 0.5) == ["c1", "c2"]
    assert sched.select_survivors(results, 1.0) == ["c1", "c2", "c3"]


def test_select_survivors_never_returns_empty_when_a_candidate_is_rankable():
    assert sched.select_survivors({"c1": {"mean": 0.0, "rankable": True}}, 0.25) == ["c1"]


# --- 配对读取 ---------------------------------------------------------------

def test_read_pairs_takes_the_tested_seat_not_a_fixed_index(tmp_path):
    """被测座位随换座变化，必须按 policy_ids_by_seat 反查而不是写死座位 0。"""

    rows = [
        {"status": "complete", "scenario_id": "s0", "pair_id": "s0:1230",
         "result_id": "r:s0:1230:base", "policy_ids_by_seat": ["opp", "base", "opp", "opp"],
         "scores_after": [0, -10, 0, 0]},
        {"status": "complete", "scenario_id": "s0", "pair_id": "s0:1230",
         "result_id": "r:s0:1230:cand", "policy_ids_by_seat": ["opp", "cand", "opp", "opp"],
         "scores_after": [0, 30, 0, 0]},
    ]
    path = tmp_path / "results.jsonl"
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    pairs = sched.read_pairs(path, "base", "cand")
    assert pairs == [{"scenario_id": "s0", "pair_id": "s0:1230", "delta": 40.0}]


def test_read_pairs_ignores_incomplete_rows(tmp_path):
    rows = [
        {"status": "error", "scenario_id": "s0", "pair_id": "s0:1230",
         "result_id": "r:s0:1230:base", "policy_ids_by_seat": ["opp", "base", "opp", "opp"],
         "scores_after": [0, -10, 0, 0]},
        {"status": "complete", "scenario_id": "s0", "pair_id": "s0:1230",
         "result_id": "r:s0:1230:cand", "policy_ids_by_seat": ["opp", "cand", "opp", "opp"],
         "scores_after": [0, 30, 0, 0]},
    ]
    path = tmp_path / "results.jsonl"
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    assert sched.read_pairs(path, "base", "cand") == []

# --- REVIEW-7 反例回归：不可排序、非法配置、累计预算 ------------------------

def test_zero_root_candidate_is_not_rankable(tmp_path):
    """R7-2：零有效根组必须标为**不可排序**，而不是均值 0。"""

    stats = sched.root_statistics([])
    assert stats["rankable"] is False
    assert "零有效根组" in stats["rankable_reason"]
    assert sched.root_statistics([1.0])["rankable"] is False
    assert sched.root_statistics([1.0, 2.0])["rankable"] is True


def test_zero_root_failure_does_not_beat_a_valid_negative_candidate():
    """R7-2 的核心反例：初版 `mean or 0.0` 让失败候选（None→0）胜过有效均值 −1 的候选。"""

    results = {
        "failed_candidate": {"rankable": False, "mean": None, "n_roots": 0},
        "valid_candidate": {"rankable": True, "mean": -1.0, "n_roots": 4},
    }
    survivors = sched.select_survivors(results, 0.5)
    assert survivors == ["valid_candidate"]


def test_select_survivors_returns_empty_when_nothing_is_rankable():
    assert sched.select_survivors({"a": {"rankable": False, "mean": None}}, 0.5) == []


def test_ledger_rejects_illegal_roots_and_seats(tmp_path):
    """R7-6：非法配置会**增加**剩余预算（记 −8 桌）而切片仍生成 3 次换座。"""

    ledger = sched.BudgetLedger(table_budget=20, path=tmp_path / "l.json")
    with pytest.raises(ValueError):
        ledger.reserve("r", ["c"], roots=4, seats=-1, root_keys=["a"])
    with pytest.raises(ValueError):
        ledger.reserve("r", ["c"], roots=0, seats=1, root_keys=["a"])
    with pytest.raises(ValueError):
        ledger.reserve("r", ["c"], roots=4, seats=5, root_keys=["a"])
    assert ledger.spent_tables == 0, "被拒的配置不得改动预算"


def test_find_stop_accumulates_cost_across_rounds():
    """R7-7：初版每轮都对同一初始余额判断，600 预算下的 128+512=640 会被报成可完成。"""

    ledger = sched.BudgetLedger(table_budget=600)
    stop = sched.find_stop(ledger, ["c1", "c2"], sched.ROUND_SPECS,
                           ["r{0}".format(i) for i in range(64)])
    assert stop["decision"] == "stop"
    assert "累计" in stop["reason"], stop


def test_candidate_identity_separates_parameter_variants():
    """R7-5：同模块不同参数必须有不同的身份，否则产物互相覆盖。"""

    repo = _HERE.parents[2]
    a = sched._candidate_identity("meld_opportunity_cost", {"adj.beta": 2.0}, repo)
    b = sched._candidate_identity("meld_opportunity_cost", {"adj.beta": 20.0}, repo)
    assert a != b
    assert "beta=2.0" in a and "beta=20.0" in b
    assert "src" in a

# --- REVIEW-7 R7-1：门禁必须**绑定身份**并被调度器强制核验 -------------------

def _admission_corpus(tmp_path, content='{"a": 1}\n', name="corpus.jsonl"):
    """造一份准入语料，返回 (路径, 字节哈希)。"""

    import hashlib

    path = tmp_path / name
    path.write_text(content, encoding="utf-8")
    return path, hashlib.sha256(path.read_bytes()).hexdigest()


def _write_gate_record(directory, identity, *, corpus_sha=None, admitted=True,
                       evidence_kind="admission", name="rec.json", extra=None):
    """写一条门禁记录；`corpus_sha=None` 表示**旧格式**（没有语料指纹）。"""

    import json as _json

    payload = {"bound_identity": identity, "admitted": admitted}
    if evidence_kind is not None:
        payload["evidence_kind"] = evidence_kind
    if corpus_sha is not None:
        payload["corpus"] = {"path": "corpus.jsonl", "rows": 1, "sha256": corpus_sha}
    if extra:
        payload.update(extra)
    (directory / name).write_text(_json.dumps(payload), encoding="utf-8")


def _gate_record_dir(tmp_path, weights):
    """造一个绑定身份正确、并带**语料指纹**的门禁通过记录。"""

    directory = tmp_path / "gate-records"
    directory.mkdir(exist_ok=True)
    corpus, corpus_sha = _admission_corpus(tmp_path)
    identity = sched._candidate_identity("meld_opportunity_cost", weights, _REPO)
    _write_gate_record(directory, identity, corpus_sha=corpus_sha, name="rec.json")
    return directory, identity, corpus


def test_scheduler_refuses_without_a_gate_record_directory(tmp_path):
    """R7-1 反例：初版从不检查门禁，直接 reserve → run_round。"""

    corpus, _ = _admission_corpus(tmp_path)
    admitted, detail = sched._gate_admits(
        "meld_opportunity_cost", {"adj.beta": 20.0}, None, _REPO,
        admission_corpus=corpus)
    assert admitted is False
    assert "不允许在无通过记录时扣预算" in detail


def test_scheduler_refuses_without_a_declared_corpus(tmp_path):
    """★ R7-1 剩余项：**不声明语料就不准入**。

    身份里不含语料，因此"在某份语料上过了 G-2"这条结论可以被任意换语料后的
    运行沿用。拒绝声明即拒绝执行——不是靠调用方自觉。
    """

    directory, identity, _ = _gate_record_dir(tmp_path, {"adj.beta": 20.0})
    admitted, detail = sched._gate_admits(
        "meld_opportunity_cost", {"adj.beta": 20.0}, directory, _REPO)
    assert admitted is False
    assert "未声明准入语料" in detail


def test_scheduler_refuses_when_no_record_matches_the_identity(tmp_path):
    directory = tmp_path / "gate-records"
    directory.mkdir()
    corpus, _ = _admission_corpus(tmp_path)
    admitted, detail = sched._gate_admits(
        "meld_opportunity_cost", {"adj.beta": 20.0}, directory, _REPO,
        admission_corpus=corpus)
    assert admitted is False
    assert "绑定身份一致" in detail


def test_changing_parameters_invalidates_an_existing_record(tmp_path):
    """★ 这条是 R7-1 的核心：参数一改，原通过记录**必须自动失效**。"""

    directory, _, corpus = _gate_record_dir(tmp_path, {"adj.beta": 20.0})
    admitted_ok, _ = sched._gate_admits(
        "meld_opportunity_cost", {"adj.beta": 20.0}, directory, _REPO,
        admission_corpus=corpus)
    admitted_changed, detail = sched._gate_admits(
        "meld_opportunity_cost", {"adj.beta": 99.0}, directory, _REPO,
        admission_corpus=corpus)
    assert admitted_ok is True
    assert admitted_changed is False, detail


def test_a_record_that_did_not_pass_does_not_admit(tmp_path):
    directory, identity, corpus = _gate_record_dir(tmp_path, {"adj.beta": 20.0})
    _, corpus_sha = _admission_corpus(tmp_path)
    _write_gate_record(directory, identity, corpus_sha=corpus_sha,
                       admitted=False, name="rec.json",
                       extra={"failed": ["G-2 退化检测"]})
    admitted, detail = sched._gate_admits(
        "meld_opportunity_cost", {"adj.beta": 20.0}, directory, _REPO,
        admission_corpus=corpus)
    assert admitted is False
    assert "门禁未通过" in detail


def test_a_different_corpus_invalidates_the_admission(tmp_path):
    """★ R7-1 剩余项核心：**换语料 ⇒ 原准入记录失效**。

    初版记录里写了 `corpus`，但核验时一个字段都没读：同一绑定身份下
    "在语料 A 上通过"的记录会直接放行"在语料 B 上运行"的候选——
    而触发面与改选率都随语料变（价值族② 实测就是一份没有链状态窗口的语料）。
    """

    directory, _, corpus_a = _gate_record_dir(tmp_path, {"adj.beta": 20.0})
    corpus_b, _ = _admission_corpus(tmp_path, '{"b": 2}\n', name="other.jsonl")
    admitted, detail = sched._gate_admits(
        "meld_opportunity_cost", {"adj.beta": 20.0}, directory, _REPO,
        admission_corpus=corpus_b)
    assert admitted is False
    assert "准入语料不一致" in detail
    # 用原语料仍然可以准入——拒绝的是"换语料"，不是"有语料"
    ok, _ = sched._gate_admits(
        "meld_opportunity_cost", {"adj.beta": 20.0}, directory, _REPO,
        admission_corpus=corpus_a)
    assert ok is True


def test_gate_record_without_a_corpus_fingerprint_is_rejected(tmp_path):
    """★ 旧格式记录（没有 `corpus.sha256`）必须**拒绝并给出可区分理由**。"""

    directory = tmp_path / "gate-records"
    directory.mkdir()
    corpus, _ = _admission_corpus(tmp_path)
    identity = sched._candidate_identity(
        "meld_opportunity_cost", {"adj.beta": 20.0}, _REPO)
    _write_gate_record(directory, identity, corpus_sha=None, name="legacy.json")
    admitted, detail = sched._gate_admits(
        "meld_opportunity_cost", {"adj.beta": 20.0}, directory, _REPO,
        admission_corpus=corpus)
    assert admitted is False
    assert "没有语料指纹" in detail


def test_gate_binding_records_the_admission_source(tmp_path):
    """候选产物要写明"依据的是哪条记录、那份语料"。"""

    directory, _, corpus = _gate_record_dir(tmp_path, {"adj.beta": 20.0})
    binding = sched.gate_binding("meld_opportunity_cost", {"adj.beta": 20.0},
                                 directory, _REPO, corpus)
    assert binding is not None
    assert binding["record"] == "rec.json"
    assert len(binding["record_sha256"]) == 64
    assert binding["evidence_kind"] == "admission"
    # 换语料 ⇒ 没有可写的依据
    other, _ = _admission_corpus(tmp_path, '{"b": 2}\n', name="other.jsonl")
    assert sched.gate_binding("meld_opportunity_cost", {"adj.beta": 20.0},
                              directory, _REPO, other) is None


def test_trigger_set_records_never_admit(tmp_path):
    """★ 2026-09-15 事故回归：构造触发集的记录**即使门禁级通过也不得准入**。

    事故形态：价值族② 在真实语料上 G-2 FAIL、在构造触发集上 G-2 PASS，
    两条记录放在同一目录，调度器扫目录时**先读到触发集那条**，
    于是"触发集 PASS"被当成了准入依据。这不是假想——已实际复现。

    屏障要经得住"记录里就写着 admitted=true"：触发集记录现在恒为 false，
    但这里仍用 true 来测，确保过滤靠的是 kind 而不是那个布尔值。
    """

    directory = tmp_path / "gate-records"
    directory.mkdir()
    corpus, corpus_sha = _admission_corpus(tmp_path)
    identity = sched._candidate_identity("meld_opportunity_cost", {"adj.beta": 20.0}, _REPO)
    _write_gate_record(directory, identity, corpus_sha=corpus_sha,
                       evidence_kind="trigger", name="trigger.json")

    admitted, detail = sched._gate_admits(
        "meld_opportunity_cost", {"adj.beta": 20.0}, directory, _REPO,
        admission_corpus=corpus)
    assert admitted is False, detail
    assert "绑定身份一致" in detail     # 被当作"没有可用记录"，而不是"通过"


def test_admission_record_wins_over_a_trigger_record(tmp_path):
    """真实语料记录与触发集记录同目录时，仍然按真实语料判定。"""

    directory = tmp_path / "gate-records"
    directory.mkdir()
    corpus, corpus_sha = _admission_corpus(tmp_path)
    identity = sched._candidate_identity("meld_opportunity_cost", {"adj.beta": 20.0}, _REPO)
    # 触发集那条按字母序更靠前（"a-" < "b-"），因此这条测试确实在测"过滤"而非"顺序"。
    _write_gate_record(directory, identity, corpus_sha=corpus_sha,
                       evidence_kind="trigger", name="a-trigger.json")
    _write_gate_record(directory, identity, corpus_sha=corpus_sha, admitted=False,
                       name="b-admission.json", extra={"failed": ["G-2 退化检测"]})

    admitted, detail = sched._gate_admits(
        "meld_opportunity_cost", {"adj.beta": 20.0}, directory, _REPO,
        admission_corpus=corpus)
    assert admitted is False
    assert "门禁未通过" in detail


def test_records_without_evidence_kind_are_rejected_fail_closed(tmp_path):
    """★ 独立复核撞出的 fail-open：缺 evidence_kind 的记录**不得**作为准入依据。

    初版按 admission 处理（理由写的是"向后兼容"），而本次事故的形态恰恰就是
"没有证据种类字段的记录"。改为 fail-closed，并给出**可区分**的理由，
否则排查时看不出是记录格式问题还是根本没有记录。
    """

    directory = tmp_path / "gate-records"
    directory.mkdir()
    corpus, corpus_sha = _admission_corpus(tmp_path)
    identity = sched._candidate_identity(
        "meld_opportunity_cost", {"adj.beta": 20.0}, _REPO)
    _write_gate_record(directory, identity, corpus_sha=corpus_sha,
                       evidence_kind=None, name="legacy.json")
    admitted, detail = sched._gate_admits(
        "meld_opportunity_cost", {"adj.beta": 20.0}, directory, _REPO,
        admission_corpus=corpus)
    assert admitted is False
    assert "缺 evidence_kind" in detail          # 与"没有匹配记录"可区分


def test_conflicting_admission_records_are_rejected(tmp_path):
    """★ 独立复核撞出的顺序依赖：同一身份存在 PASS 与 FAIL 两条记录时必须拒绝。

    初版按文件名字典序取**首个**匹配即返回，而绑定身份里**不含语料**，
    换语料重跑不会让旧记录失效 ⇒ 旧 PASS 可能压过新 FAIL。
    """

    directory = tmp_path / "gate-records"
    directory.mkdir()
    corpus, corpus_sha = _admission_corpus(tmp_path)
    identity = sched._candidate_identity(
        "meld_opportunity_cost", {"adj.beta": 20.0}, _REPO)
    _write_gate_record(directory, identity, corpus_sha=corpus_sha,
                       name="a-old-pass.json")
    _write_gate_record(directory, identity, corpus_sha=corpus_sha, admitted=False,
                       name="b-new-fail.json", extra={"failed": ["G-2 退化检测"]})

    admitted, detail = sched._gate_admits(
        "meld_opportunity_cost", {"adj.beta": 20.0}, directory, _REPO,
        admission_corpus=corpus)
    assert admitted is False
    assert "结论不一致" in detail



# --- REVIEW-7 R7-3 / R7-4 / S7-2：分级执行、根组防重、产物身份 --------------

def test_reserve_rejects_replay_of_the_same_root_set(tmp_path):
    """★ R7-4：同一（轮次, 根组集合）再次预留属于**重演**，默认拒绝。"""

    ledger = sched.BudgetLedger(table_budget=100, path=tmp_path / "ledger.json")
    keys = ["a", "b"]
    ledger.reserve("第一级", ["cand"], 2, 1, keys)
    with pytest.raises(ValueError) as excinfo:
        ledger.reserve("第一级", ["cand"], 2, 1, keys)
    assert "重演" in str(excinfo.value)


def test_allowed_rerun_is_charged_and_marked(tmp_path):
    """重演**照常计费**，但在台账里标记 rerun，不计入新增独立根组。"""

    ledger = sched.BudgetLedger(table_budget=100, path=tmp_path / "ledger.json")
    keys = ["a", "b"]
    first = ledger.reserve("第一级", ["cand"], 2, 1, keys)
    ledger.reserve("第一级", ["cand"], 2, 1, keys, allow_rerun=True)
    assert ledger.spent_tables == first * 2
    assert ledger.root_sets[0]["rerun"] is False
    assert ledger.root_sets[-1]["rerun"] is True
    # 不同的轮次用同一批根组**不算重演**（分级配方里各级本就不同）
    ledger.reserve("第二级", ["cand"], 2, 1, keys)
    assert ledger.spent_tables == first * 3


def test_run_state_round_trip(tmp_path):
    path = tmp_path / "run_state.json"
    state = sched.RunState(path=path, levels=[{"round": "第一级", "survivors": []}],
                           cursor_level=1, stop_reason=None)
    state.save()
    back = sched.RunState.load(path)
    assert back.levels == state.levels
    assert back.cursor_level == 1
    assert sched.RunState.load(tmp_path / "missing.json").cursor_level == 0


def _fake_pairs(bias):
    return [{"scenario_id": "s{0}".format(i), "delta": bias + i} for i in range(2)]


def _main_argv(tmp_path, budget):
    levels = json.dumps([{"name": "第一级", "roots": 2, "seats": 1, "keep_fraction": 0.5},
                         {"name": "第二级", "roots": 2, "seats": 1, "keep_fraction": 1.0}])
    corpus = tmp_path / "corpus.jsonl"
    if not corpus.exists():
        corpus.write_text('{"a": 1}\n', encoding="utf-8")
    return ["--candidate", "meld_opportunity_cost", "--weights", '{"adj.beta": 20.0}',
            "--candidate", "seven_pairs_path_value",
            "--weights", '{"adj.path_log2": 1.0, "adj.closer_bonus": 1.0}',
            "--levels", levels, "--budget-tables", str(budget),
            "--ledger", str(tmp_path / "ledger.json"), "--out", str(tmp_path / "run"),
            "--gate-records", str(tmp_path / "gates"),
            "--admission-corpus", str(corpus)]


def _patch_main_gates(monkeypatch):
    """把受监管装载、门禁核验与产物绑定替换成测试替身。

    签名必须接受 `admission_corpus` 与 `identity` 关键字——它们正是
    「先受监管装载、再按同一身份核验」这条链路的两个接口。
    """

    monkeypatch.setattr(sched, "_gate_admits",
                        lambda name, w, gd, repo, **kw: (True, "test"))
    monkeypatch.setattr(sched, "gate_binding",
                        lambda name, w, gd, repo, corpus, **kw: None)
    monkeypatch.setattr(sched.sibling("sitin_gates"), "supervised_prepare", _fake_prepare)


def _fake_prepare(name, weights, **_kwargs):
    """受监管装载的测试替身：只给**真实身份**，不跑子进程。

    真实实现会起隔离子进程导入注册表并构造候选（REVIEW-9）；单测不需要那个代价，
    但身份必须是真的——恢复对账、产物身份与门禁绑定都靠它。
    """

    identity = sched._candidate_identity(name, weights, _REPO)
    return {"ok": True, "schema": "sitin-prepare/1", "candidate": name,
            "weights": dict(weights), "params": {}, "base": {},
            "scope": ["chi", "peng"], "bound_identity": identity,
            "adjustment_identity": "test-identity",
            "adjustment_spec": {"name": "测试", "version": "test-v1", "trigger": "测试",
                                "thought": "测试", "scope": ["chi", "peng"], "bound": 1.0},
            "source_sha256": "0" * 64, "dependency_digest": "0" * 16,
            "execution": {"timed_out": False}}


def _patch(monkeypatch, pairs_by_prefix, fail_on=None):
    def fake_run(name, weights, roots, seats, out_dir, repo, **kwargs):
        if fail_on is not None and name == fail_on:
            raise RuntimeError("模拟中断")
        return pairs_by_prefix(name)

    monkeypatch.setattr(sched, "run_round", fake_run)
    _patch_main_gates(monkeypatch)


def test_main_really_advances_to_the_next_level(tmp_path, monkeypatch):
    """★ R7-3 的核心：初版**永远只跑第一轮**，然后用临时根标签"规划"第二轮就退出。

    本测试要求：配方有两级就真的跑两级，且第二级只跑**晋级的那一个**候选。
    """

    seen = []

    def fake_run(name, weights, roots, seats, out_dir, repo, **kwargs):
        seen.append(name)
        return _fake_pairs(10.0 if "seven" in name else 0.0)

    monkeypatch.setattr(sched, "run_round", fake_run)
    _patch_main_gates(monkeypatch)

    # 每级 2 根 × 1 换座 × 2 臂 × 候选数：第一级 8 桌、第二级 4 桌 ⇒ 12
    assert sched.main(_main_argv(tmp_path, 12)) == 0
    state = json.loads((tmp_path / "run" / "run_state.json").read_text(encoding="utf-8"))
    assert state["cursor_level"] == 2
    assert [level["round"] for level in state["levels"]] == ["第一级", "第二级"]
    # 第一级：两个候选都跑；第二级：只跑晋级的 seven_pairs_path_value
    assert seen == ["meld_opportunity_cost", "seven_pairs_path_value",
                    "seven_pairs_path_value"]
    assert state["levels"][1]["spec"]["roots"] == 2
    # 两级用**不同的**根组集合（新增样本，不是重演）
    assert state["levels"][0]["root_set_id"] != state["levels"][1]["root_set_id"]


def test_main_stops_on_budget_before_reserving(tmp_path, monkeypatch):
    """预算只够第一级 ⇒ 停在第二级，且**不得**预留那笔预算。"""

    _patch(monkeypatch, lambda name: _fake_pairs(1.0))
    assert sched.main(_main_argv(tmp_path, 8)) == 1
    state = json.loads((tmp_path / "run" / "run_state.json").read_text(encoding="utf-8"))
    assert state["cursor_level"] == 1
    assert "预算不足" in (state["stop_reason"] or "")
    ledger = json.loads((tmp_path / "ledger.json").read_text(encoding="utf-8"))
    assert ledger["spent_tables"] == 8          # 只为第一级扣款
    assert len(ledger["root_sets"]) == 1


def test_interrupted_run_resumes_without_charging_again(tmp_path, monkeypatch):
    """★ R7-3 的恢复入口：中断后重跑必须**从断点继续**，且不重复扣预算。"""

    argv = _main_argv(tmp_path, 12)
    calls = {"n": 0}

    def crashing_run(name, weights, roots, seats, out_dir, repo, **kwargs):
        calls["n"] += 1
        if calls["n"] >= 3:                      # 第 3 次 = 第二级的第一个候选
            raise RuntimeError("模拟中断")
        return _fake_pairs(10.0 if "seven" in name else 0.0)

    monkeypatch.setattr(sched, "run_round", crashing_run)
    _patch_main_gates(monkeypatch)
    with pytest.raises(RuntimeError):
        sched.main(argv)

    mid = json.loads((tmp_path / "run" / "run_state.json").read_text(encoding="utf-8"))
    assert mid["cursor_level"] == 1                       # 第一级已完成
    assert mid["levels"][1]["done"] == []                 # 第二级一个都没完成
    spent_after_crash = json.loads(
        (tmp_path / "ledger.json").read_text(encoding="utf-8"))["spent_tables"]
    assert spent_after_crash == 12                        # 两级都已预留

    seen = []

    def working_run(name, weights, roots, seats, out_dir, repo, **kwargs):
        seen.append(name)
        return _fake_pairs(10.0 if "seven" in name else 0.0)

    monkeypatch.setattr(sched, "run_round", working_run)
    assert sched.main(argv) == 0
    assert seen == ["seven_pairs_path_value"]             # 只补跑第二级
    final = json.loads((tmp_path / "ledger.json").read_text(encoding="utf-8"))
    assert final["spent_tables"] == spent_after_crash      # **不重复扣款**
    assert len(final["root_sets"]) == 2                    # 也没有重复预留


def test_candidate_manifest_records_identity_and_effective_weights(tmp_path):
    """★ S7-2：产物必须带**完整候选身份**与**有效权重**。

    初版 runs/sitin-2.4/.../manifest.json 里 effective_weights=null、没有候选身份、
    没有源码指纹——指纹存在于对象中和落进产物是两件事。
    """

    ledger = sched.BudgetLedger(table_budget=10, path=tmp_path / "ledger.json")
    roots = [{"seed": 1, "scenario_id": "r0"}, {"seed": 2, "scenario_id": "r1"}]
    manifest = sched.candidate_manifest(
        "chain_path_value", {"adj.scale": 40.0, "shanten_step": 100.0},
        _REPO, roots, {"name": "第一级", "roots": 2, "seats": 1}, ledger)
    assert manifest["candidate"] == "chain_path_value"
    assert manifest["bound_identity"].startswith("chain_path_value|adj(scale=40.0")
    assert "chain-path-value-v1" in manifest["adjustment_identity"]
    assert manifest["effective_adjustment_params"] == {"scale": 40.0}
    assert manifest["effective_base_weights"]["shanten_step"] == 100.0   # 覆盖生效
    assert manifest["effective_base_weights"]["win_now"] == 1000.0       # 默认被补齐
    assert len(manifest["source_sha256"]) == 64
    assert manifest["root_set_id"].startswith("roots-")
    assert manifest["adjustment_spec"]["scope"]                      # 作用面进产物
    assert manifest["cell_dir"] == sched.cell_dir_name(manifest["bound_identity"])
    assert manifest["gate_binding"] is None                          # 未传就不编造


def test_candidate_manifest_carries_the_gate_binding(tmp_path):
    """产物要写明**这次执行依据的是哪条准入记录**（R7-1）。"""

    ledger = sched.BudgetLedger(table_budget=10, path=tmp_path / "ledger.json")
    roots = [{"seed": 1, "scenario_id": "r0"}]
    binding = {"record": "gates-x.json", "record_sha256": "a" * 64,
               "corpus_sha256": "b" * 64, "corpus_path": "c.jsonl",
               "evidence_kind": "admission"}
    manifest = sched.candidate_manifest(
        "chain_path_value", {}, _REPO, roots,
        {"name": "第一级", "roots": 1, "seats": 1}, ledger, gate_binding=binding)
    assert manifest["gate_binding"] == binding


# --- REVIEW-7 2.5：跑一轮必须**可终止**，失败必须被隔离成不可排序 -----------

def test_cell_dir_name_is_filesystem_safe():
    """★ 次要清理：候选身份含 | ( ) = , ，不能直接当路径名（本仓已积累 48 条）。"""

    identity = "meld_opportunity_cost|adj(beta=20.0)|base(default)|src37be910e3f467d67"
    name = sched.cell_dir_name(identity)
    assert not set(name) & set("|()=, ")
    assert "meld_opportunity_cost" in name                    # 人眼仍看得出是哪个候选
    # 不同身份必须得到不同目录名（单射由尾部哈希保证，不靠易碰撞的 slug）
    assert name != sched.cell_dir_name(identity.replace("20.0", "20-0"))


def test_run_cli_kills_a_hanging_command(tmp_path):
    """★ 2.5 反例：初版 `subprocess.run` 没有超时，死循环候选会把调度器挂死。"""

    import sys as _sys
    import time as _time

    started = _time.monotonic()
    result = sched._run_cli(
        [_sys.executable, "-c", "import time; time.sleep(30)"], tmp_path, 0.5)
    elapsed = _time.monotonic() - started
    assert result.timed_out is True
    assert result.group_still_alive is False
    assert elapsed < 20, "超时后必须真的结束，而不是等子进程自然退出"


def test_run_cli_delegates_to_the_shared_supervised_entry(tmp_path):
    """★ S8-2：调度器与门禁必须**共用**受监管入口，不能各写一份终止逻辑。

    初版这里是自己的一段 `if process.poll() is None` 逻辑——它只看**组长**是否还活着，
    于是后代忽略 TERM 时既不发 KILL、又用无超时的 `communicate()` 继续等（实测 8.041 秒）。
    """

    calls = {}
    real = sched.sibling("sitin_process").run_supervised

    def spy(command, **kwargs):
        calls["command"] = list(command)
        calls["kwargs"] = kwargs
        return real(command, **kwargs)

    monkeypatch_target = sched.sibling("sitin_process")
    original = monkeypatch_target.run_supervised
    monkeypatch_target.run_supervised = spy
    try:
        result = sched._run_cli([sys.executable, "-c", "print('ok')"], tmp_path, 30)
    finally:
        monkeypatch_target.run_supervised = original
    assert calls["command"][-1] == "print('ok')"
    assert calls["kwargs"]["grace_sec"] == sched._TERMINATE_GRACE_SEC
    assert result.returncode == 0 and result.timed_out is False


def test_hanging_candidate_is_recorded_as_unrankable(tmp_path, monkeypatch):
    """★ 2.5 + R7-2 的合流：超时**不得**静默，也不得补零参与排序。

    初版 `subprocess.run(check=True)` 要么抛异常终止整个调度器，
    要么（若被吞掉）留下零行结果被当成"均值 0"。两者都不对：
    失败候选应落盘失败证据、记为不可排序，其余候选照常推进。
    """

    def hanging_run(name, weights, roots, seats, out_dir, repo, **kwargs):
        if "seven" in name:
            raise sched.RoundFailed("运行超时：360.0 秒内未结束（已终止进程组）",
                                    returncode=None, stderr="boom", timeout_sec=360.0)
        return _fake_pairs(1.0)

    monkeypatch.setattr(sched, "run_round", hanging_run)
    _patch_main_gates(monkeypatch)
    # 第一级 2 候选 × 2 根 × 1 换座 × 2 臂 = 8 桌；第二级 4 桌 ⇒ 12 够跑完。
    # 退出码 0 = **配方跑完了**；候选失败是记录下来的结果，不是停止原因。
    assert sched.main(_main_argv(tmp_path, 12)) == 0
    state = json.loads((tmp_path / "run" / "run_state.json").read_text(encoding="utf-8"))
    first = state["levels"][0]
    failed = [item for item in first["results"].values()
              if item.get("status") == "failed"]
    assert len(failed) == 1
    assert failed[0]["rankable"] is False
    assert failed[0]["mean"] is None                 # **不得补零**
    assert "运行超时" in failed[0]["rankable_reason"]
    # 失败证据落盘（含输出尾部），否则事后无法判断是超时还是崩了
    identity = sched._candidate_identity(
        "seven_pairs_path_value",
        {"adj.path_log2": 1.0, "adj.closer_bonus": 1.0}, _REPO)
    cell = tmp_path / "run" / "第一级" / sched.cell_dir_name(identity)
    assert (cell / "failure.json").is_file()
    evidence = json.loads((cell / "failure.json").read_text(encoding="utf-8"))
    assert evidence["schema"] == "sitin-round-failure/1"
    assert evidence["stderr_tail"] == "boom"
    # 失败候选**不晋级**，幸存的候选照常进入第二级
    assert [entry["candidate"] for entry in first["survivors"]] == ["meld_opportunity_cost"]
    assert state["cursor_level"] == 2


# --- 对抗性复核撞出的四类反例（本轮修复的回归） ---------------------------

def test_root_set_id_is_keyed_on_seed_not_label():
    """★ 判重键必须取 **seed**（发牌身份），不能取 scenario_id（只是标签）。

    初版按标签取哈希，方向完全相反：换 --root-prefix（标签变、牌山没变）判"新增样本"
    照常计费；只换 --seed-base（**真换了牌山**）反被判"重演"直接拒绝。
    """

    same_seed_other_label = [{"seed": 100, "scenario_id": "A-0"},
                             {"seed": 101, "scenario_id": "A-1"}]
    other_seed_same_label = [{"seed": 200, "scenario_id": "A-0"},
                             {"seed": 201, "scenario_id": "A-1"}]
    assert (sched.root_set_id_of(same_seed_other_label)
            == sched.root_set_id_of([{"seed": 100, "scenario_id": "B-9"},
                                     {"seed": 101, "scenario_id": "B-8"}]))
    assert (sched.root_set_id_of(same_seed_other_label)
            != sched.root_set_id_of(other_seed_same_label))


def test_resume_refuses_a_different_recipe(tmp_path, monkeypatch):
    """★ 恢复必须与记录对账：换换座数恢复会被**拒绝**，而不是静默实跑别的配方。

    对账发生在**已记录但未完成**的等级上（已完成的等级在游标之外，直接跳过）。
    所以先制造一次「第二级已预留、候选未跑完」的中断，再改 seats 恢复。
    """

    argv = _main_argv(tmp_path, 12)
    calls = {'n': 0}

    def crashing(name, weights, roots, seats, out_dir, repo, **kw):
        calls['n'] += 1
        if calls['n'] >= 3:
            raise RuntimeError('模拟中断')
        return _fake_pairs(1.0)

    monkeypatch.setattr(sched, 'run_round', crashing)
    _patch_main_gates(monkeypatch)
    with pytest.raises(RuntimeError):
        sched.main(argv)
    mid = json.loads((tmp_path / 'run' / 'run_state.json').read_text(encoding='utf-8'))
    assert mid['cursor_level'] == 1 and len(mid['levels']) == 2

    bad = list(argv)
    idx = bad.index('--levels')
    bad[idx + 1] = json.dumps([{'name': '第一级', 'roots': 2, 'seats': 1, 'keep_fraction': 0.5},
                               {'name': '第二级', 'roots': 2, 'seats': 2,
                                'keep_fraction': 1.0}])
    with pytest.raises(ValueError) as excinfo:
        sched.main(bad)
    assert '恢复被拒绝' in str(excinfo.value)
    assert 'seats' in str(excinfo.value)

def test_rerun_clears_a_stale_stop_reason(tmp_path, monkeypatch):
    """★ 停止原因必须**每次运行重算**。

    初版从不清除：**预算不足停止后追加预算重跑**（工程期望；现行文档未写成规范句）时
    （两级跑完、cursor=2、已扣 24 桌、退出码 0），run_state/elimination.json/md 里
    仍写着上一次的"预算不足停止"——报告说停止、实际已执行。
    """

    out = tmp_path / "run"
    out.mkdir(parents=True)
    (out / "run_state.json").write_text(json.dumps(
        {"schema": "sitin-run-state/1", "levels": [], "cursor_level": 0,
         "stop_reason": "第二级：预算不足：本轮需 8 桌，剩余 4 桌"}), encoding="utf-8")

    _patch(monkeypatch, lambda name: _fake_pairs(1.0))
    assert sched.main(_main_argv(tmp_path, 12)) == 0
    state = json.loads((out / "run_state.json").read_text(encoding="utf-8"))
    assert state["stop_reason"] is None
    elimination = json.loads((out / "elimination.json").read_text(encoding="utf-8"))
    assert elimination["report"].get("stop_reason") is None
    assert "预算不足" not in (out / "elimination.md").read_text(encoding="utf-8")


def test_ledger_reserved_but_state_missing_is_reconciled(tmp_path, monkeypatch):
    """★ reserve 落盘而 run_state 未落盘的窗口：按台账**重建**该级，不重复扣款。

    初版在这种情况下重跑会被判"重演"直接抛错；加 --allow-rerun 则重复扣款。
    """

    argv = _main_argv(tmp_path, 12)
    _patch(monkeypatch, lambda name: _fake_pairs(1.0))
    assert sched.main(argv) == 0
    spent = json.loads((tmp_path / "ledger.json").read_text(encoding="utf-8"))["spent_tables"]

    # 模拟"台账已落盘、状态丢失"
    (tmp_path / "run" / "run_state.json").unlink()
    seen = []
    monkeypatch.setattr(sched, "run_round",
                        lambda name, weights, roots, seats, out_dir, repo, **kw:
                        (seen.append(name) or _fake_pairs(1.0)))
    assert sched.main(argv) == 0
    final = json.loads((tmp_path / "ledger.json").read_text(encoding="utf-8"))
    assert final["spent_tables"] == spent          # **没有重复扣款**
    assert len(seen) == 3                          # 但确实把两级重跑了一遍


# --- REVIEW-8 R8-3：恢复前必须核对**完整任务身份**与当前准入 -----------------

def _single_candidate_argv(tmp_path, budget, beta):
    levels = json.dumps([{"name": "L1", "roots": 2, "seats": 1, "keep_fraction": 1.0}])
    corpus = tmp_path / "corpus.jsonl"
    if not corpus.exists():
        corpus.write_text('{"a": 1}\n', encoding="utf-8")
    return ["--candidate", "meld_opportunity_cost",
            "--weights", json.dumps({"adj.beta": beta}),
            "--levels", levels, "--budget-tables", str(budget),
            "--ledger", str(tmp_path / "ledger.json"), "--out", str(tmp_path / "run"),
            "--gate-records", str(tmp_path / "gates"),
            "--admission-corpus", str(corpus)]


def test_resume_refuses_a_candidate_whose_admission_was_revoked(tmp_path, monkeypatch):
    """★ R8-3 的核心反例：命令行上通过准入的候选与**实际被执行的**候选可以不同。

    复核探针：先以 β=20 预留后中断；把该候选的准入改为拒绝，再以**已通过准入**的
    β=40 恢复——初版**实际执行并晋级的仍是 β=20**，退出码还是 0。
    修法：恢复前逐候选重核身份与准入，不一致**拒绝恢复**。
    """

    argv_old = _single_candidate_argv(tmp_path, 4, 20.0)
    monkeypatch.setattr(sched, "run_round",
                        lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("模拟中断")))
    _patch_main_gates(monkeypatch)
    with pytest.raises(RuntimeError):
        sched.main(argv_old)
    state = json.loads((tmp_path / "run" / "run_state.json").read_text(encoding="utf-8"))
    assert state["levels"][0]["candidates"][0]["weights"] == {"adj.beta": 20.0}
    assert state["levels"][0]["done"] == []

    # 第二个入口：β=40 通过准入，β=20 **不再**通过
    argv_new = _single_candidate_argv(tmp_path, 4, 40.0)

    def admits(name, weights, gate_dir, repo, **kw):
        if float(weights.get("adj.beta", 0)) == 20.0:
            return False, "门禁记录已失效（复核注入）"
        return True, "test"

    monkeypatch.setattr(sched, "_gate_admits", admits)
    monkeypatch.setattr(sched, "gate_binding", lambda *a, **kw: None)
    with pytest.raises(ValueError) as excinfo:
        sched.main(argv_new)
    assert "恢复被拒绝" in str(excinfo.value)
    assert "门禁记录已失效" in str(excinfo.value)


def test_resume_refuses_a_different_candidate_set(tmp_path, monkeypatch):
    """候选集合本身变了 ⇒ 这是**另一个任务**，不得在旧状态上继续跑。"""

    argv_old = _single_candidate_argv(tmp_path, 4, 20.0)
    monkeypatch.setattr(sched, "run_round",
                        lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("模拟中断")))
    _patch_main_gates(monkeypatch)
    with pytest.raises(RuntimeError):
        sched.main(argv_old)

    argv_new = _single_candidate_argv(tmp_path, 4, 20.0)
    argv_new[1] = "seven_pairs_path_value"          # 换成另一个候选
    monkeypatch.setattr(sched, "_gate_admits",
                        lambda name, w, gd, repo, **kw: (True, "test"))
    with pytest.raises(ValueError) as excinfo:
        sched.main(argv_new)
    assert "身份与本次命令行不一致" in str(excinfo.value)


def test_resume_still_works_when_everything_matches(tmp_path, monkeypatch):
    """对账通过时必须**照常恢复**——拒绝是给不一致用的，不是给正常恢复用的。"""

    argv = _single_candidate_argv(tmp_path, 4, 20.0)
    calls = {"n": 0}

    def interrupt_once(name, weights, roots, seats, out_dir, repo, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("模拟中断")
        return _fake_pairs(1.0)

    monkeypatch.setattr(sched, "run_round", interrupt_once)
    _patch_main_gates(monkeypatch)
    with pytest.raises(RuntimeError):
        sched.main(argv)
    assert sched.main(argv) == 0
    ledger = json.loads((tmp_path / "ledger.json").read_text(encoding="utf-8"))
    assert ledger["spent_tables"] == 4          # 不重复扣款


# --- REVIEW-8 R8-4：核对计划矩阵，部分失败不得参与排名 -----------------------

def _plan_rows(roots, seats, *, break_pair=None, break_kind="error"):
    """按计划造结果行；可指定破坏某一对（换状态或删一臂）。"""

    rows = []
    for root in roots:
        for index in range(seats):
            permutation = list(sched.PLANNED_PERMUTATIONS[index])
            pair_id = "{0}:{1}".format(root["scenario_id"],
                                       "".join(str(item) for item in permutation))
            for arm in ("weighted_heuristic_v2", "cand_x"):
                seats_ids = ["weighted_heuristic_v2", "opp-0", "opp-1", "opp-2"]
                seats_ids[0] = arm
                row = {"scenario_id": root["scenario_id"], "pair_id": pair_id,
                       "seat_permutation": permutation,
                       "policy_ids_by_seat": seats_ids, "scores_after": [0, 0, 0, 0],
                       "status": "complete"}
                if break_pair == pair_id:
                    if break_kind == "drop":
                        break
                    row["status"] = "error"
                rows.append(row)
    return rows


def _write_rows(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
                    encoding="utf-8")


def test_verify_round_plan_accepts_a_complete_matrix(tmp_path):
    roots = [{"seed": 1, "scenario_id": "r0"}, {"seed": 2, "scenario_id": "r1"}]
    path = tmp_path / "results.jsonl"
    _write_rows(path, _plan_rows(roots, 1))
    verdict = sched.verify_round_plan(path, roots, 1, "weighted_heuristic_v2", "cand_x")
    assert verdict["ok"] is True
    assert verdict["rows"] == 4 and verdict["expected_tables"] == 4


def test_verify_round_plan_rejects_a_partial_failure(tmp_path):
    """★ R8-4 反例：每根都有一条候选臂 error，remaining 成功行**不得**参与排名。"""

    roots = [{"seed": 1, "scenario_id": "r0"}, {"seed": 2, "scenario_id": "r1"}]
    rows = _plan_rows(roots, 1)
    rows[1]["status"] = "error"                  # 一根的候选臂失败
    path = tmp_path / "results.jsonl"
    _write_rows(path, rows)
    verdict = sched.verify_round_plan(path, roots, 1, "weighted_heuristic_v2", "cand_x")
    assert verdict["ok"] is False
    assert any("非 complete" in p for p in verdict["problems"])


def test_verify_round_plan_rejects_a_missing_pair(tmp_path):
    roots = [{"seed": 1, "scenario_id": "r0"}, {"seed": 2, "scenario_id": "r1"}]
    rows = [row for row in _plan_rows(roots, 1) if row["scenario_id"] != "r1"]
    path = tmp_path / "results.jsonl"
    _write_rows(path, rows)
    verdict = sched.verify_round_plan(path, roots, 1, "weighted_heuristic_v2", "cand_x")
    assert verdict["ok"] is False
    assert any("结果行数" in p or "没有任何结果" in p for p in verdict["problems"])


def test_verify_round_plan_rejects_a_pair_without_the_challenger_arm(tmp_path):
    roots = [{"seed": 1, "scenario_id": "r0"}]
    rows = [row for row in _plan_rows(roots, 1) if row["policy_ids_by_seat"][0] != "cand_x"]
    path = tmp_path / "results.jsonl"
    _write_rows(path, rows)
    verdict = sched.verify_round_plan(path, roots, 1, "weighted_heuristic_v2", "cand_x")
    assert verdict["ok"] is False
    assert any("基线一臂 + 候选一臂" in p for p in verdict["problems"])


def test_run_round_fails_the_round_when_the_matrix_is_partial(tmp_path, monkeypatch):
    """★ R8-4 端到端：`run_round` 必须对照计划核验，不足即判本轮失败。"""

    roots = [{"seed": 1, "scenario_id": "r0"}, {"seed": 2, "scenario_id": "r1"}]
    cell = tmp_path / "cell"

    class _FakeResult:
        returncode = 0
        timed_out = False
        stdout = ""
        stderr = ""
        signals_sent: tuple = ()

        def to_json(self):
            return {"returncode": 0, "timed_out": False}

    rows = _plan_rows(roots, 1)
    rows[0]["status"] = "error"

    def fake_cli(command, cwd, limit):
        del command, cwd, limit
        _write_rows(cell / "out" / "results.jsonl", rows)
        return _FakeResult()

    monkeypatch.setattr(sched, "_run_cli", fake_cli)
    with pytest.raises(sched.RoundFailed) as excinfo:
        sched.run_round("meld_opportunity_cost", {"adj.beta": 20.0}, roots, 1, cell,
                        repo=_REPO)
    assert "结果矩阵与计划不符" in str(excinfo.value)
    assert excinfo.value.problems
    assert excinfo.value.to_json()["problems"]


# --- REVIEW-8 R8-5：产物的根组身份必须与台账/状态同一口径 -------------------

def test_candidate_manifest_uses_the_seed_based_root_identity(tmp_path):
    """★ R8-5：初版把 scenario_id 标签列表喂给 root_set_id_of，于是
    产物里的根组身份与 run_state **永远对不上**（实测 8/8 份都不一致）。"""

    ledger = sched.BudgetLedger(table_budget=10, path=tmp_path / "ledger.json")
    roots = [{"seed": 111, "scenario_id": "label-A"}, {"seed": 222, "scenario_id": "label-B"}]
    manifest = sched.candidate_manifest(
        "chain_path_value", {}, _REPO, roots, {"name": "L1", "roots": 2, "seats": 1}, ledger)
    assert manifest["root_set_id"] == sched.root_set_id_of(roots)
    assert manifest["root_set_id_source"] == "computed_from_seeds"
    # 标签换了、seed 没换 ⇒ 身份不变（判重键按 seed，这是既有结论）
    relabelled = [{"seed": 111, "scenario_id": "other"}, {"seed": 222, "scenario_id": "x"}]
    assert manifest["root_set_id"] == sched.root_set_id_of(relabelled)
    # 与旧的"按标签算"必须不同，否则这条测试没有区分力
    assert manifest["root_set_id"] != sched.root_set_id_of(
        [root["scenario_id"] for root in roots])


def test_manifest_and_run_state_agree_on_the_root_identity(tmp_path, monkeypatch):
    """跨产物相等断言：每个 candidate-manifest 的根组身份 == 对应 run_state 的。"""

    _patch(monkeypatch, lambda name: _fake_pairs(1.0))
    assert sched.main(_main_argv(tmp_path, 12)) == 0
    state = json.loads((tmp_path / "run" / "run_state.json").read_text(encoding="utf-8"))
    checked = 0
    for level in state["levels"]:
        for entry in level["candidates"]:
            cell = (tmp_path / "run" / level["round"]
                    / sched.cell_dir_name(entry["identity"]))
            manifest = json.loads(
                (cell / "candidate-manifest.json").read_text(encoding="utf-8"))
            assert manifest["root_set_id"] == level["root_set_id"], (
                level["round"], entry["candidate"])
            assert manifest["root_set_id_source"] == "verified"
            checked += 1
    assert checked >= 3          # 第一级两个 + 第二级一个


# --- 3.P 编排验证发现的预算口径问题：命令行只能**追加**预算 -------------------

def test_budget_can_be_raised_from_the_command_line_but_never_shrunk(tmp_path):
    """★ 3.P：台账已存在时，命令行预算**只能加不能减**（【工程建议】口径）。

    初版完全忽略命令行值：**现行文档没有这条规范句**，所以这是**意外行为**
    （静默忽略参数），不是"违反要求"。修复后的口径是本用例断言的四条行为
    （追加生效 / 不缩减 / 缺省保留 / 来源必须可见）。
    """

    path = tmp_path / "ledger.json"
    ledger = sched.BudgetLedger(table_budget=20, path=path)
    ledger.reserve("第一级", ["cand"], 4, 1, ["r0", "r1", "r2", "r3"],
                   root_set_id_value="roots-demo")
    assert ledger.spent_tables == 8
    assert sched.BudgetLedger.load(path, table_budget=30).table_budget == 30   # 追加生效
    assert sched.BudgetLedger.load(path, table_budget=10).table_budget == 20   # 不缩减
    assert sched.BudgetLedger.load(path).table_budget == 20                    # 不改就是不改


def test_resume_after_a_budget_stop_completes_with_the_raised_budget(tmp_path, monkeypatch):
    """★ 3.P：预算不足停止 → 追加预算续跑，必须跑到第二级且**不重复预留第一级**。"""

    _patch(monkeypatch, lambda name: _fake_pairs(1.0))
    assert sched.main(_main_argv(tmp_path, 10)) == 1          # 第二级差预算，停下
    before = json.loads((tmp_path / "ledger.json").read_text(encoding="utf-8"))
    assert before["spent_tables"] == 8 and len(before["root_sets"]) == 1

    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        assert sched.main(_main_argv(tmp_path, 12)) == 0      # 追加到 12 后跑完两级
    after = json.loads((tmp_path / "ledger.json").read_text(encoding="utf-8"))
    assert after["spent_tables"] == 12
    assert after["table_budget"] == 12
    assert len(after["root_sets"]) == 2                       # 第一级没有重复预留
    state = json.loads((tmp_path / "run" / "run_state.json").read_text(encoding="utf-8"))
    assert state["cursor_level"] == 2 and state["stop_reason"] is None
    assert "本次生效" in output.getvalue()                    # 预算来源必须可见

# --- 3.P 核验发现的残留路径：恢复与产物不得在父进程重算身份 -------------------
#
# verify_persisted_level 与 candidate_manifest 原先都用 _candidate_identity 重算身份，
# 而它会在**父进程**导入候选注册表（= 执行每一个已注册候选的模块体）。
# 3.P 的核验探针（evidence/3.P-verification/verify_parent_side_execution.py）行为上抓到了它。


def _exploding_identity(name, weights, repo):
    raise AssertionError("父进程不得重算身份：_candidate_identity 会导入候选注册表")


def test_resume_path_never_recomputes_identity_in_the_parent(tmp_path, monkeypatch):
    """★ 3.P：恢复路径重核身份必须走**受监管装载**，在父进程重算就算缺陷。"""

    weights = {"adj.beta": 20.0}
    identity = sched._candidate_identity("meld_opportunity_cost", weights, _REPO)

    def fake_prepare(name, weights, **kwargs):
        return {"ok": True, "schema": "sitin-prepare/1", "candidate": name,
                "weights": dict(weights), "params": {}, "base": {},
                "scope": ["chi", "peng"], "bound_identity": identity,
                "adjustment_identity": "test-identity",
                "adjustment_spec": {"name": "测试", "version": "test-v1",
                                    "trigger": "测试", "thought": "测试",
                                    "scope": ["chi", "peng"], "bound": 1.0},
                "source_sha256": "0" * 64, "dependency_digest": "0" * 16,
                "execution": {"timed_out": False}}

    calls = {"n": 0}

    def interrupt_once(name, weights, roots, seats, out_dir, repo, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("模拟中断")
        return _fake_pairs(1.0)

    monkeypatch.setattr(sched, "run_round", interrupt_once)
    monkeypatch.setattr(sched.sibling("sitin_gates"), "supervised_prepare", fake_prepare)
    monkeypatch.setattr(sched, "_gate_admits", lambda name, w, gd, repo, **kw: (True, "test"))
    monkeypatch.setattr(sched, "gate_binding", lambda *a, **kw: None)
    # 关键：把父进程现算身份这条路**打断**——它一旦被走到，用例就会失败。
    monkeypatch.setattr(sched, "_candidate_identity", _exploding_identity)

    argv = _single_candidate_argv(tmp_path, 4, 20.0)
    with pytest.raises(RuntimeError):
        sched.main(argv)                       # 首跑：中断
    assert sched.main(argv) == 0               # 恢复：全程不碰父进程现算
    cell = tmp_path / "run" / "L1" / sched.cell_dir_name(identity)
    manifest = json.loads((cell / "candidate-manifest.json").read_text(encoding="utf-8"))
    assert manifest["cell_dir"] == sched.cell_dir_name(identity)


def test_candidate_manifest_reuses_the_prepared_identity(tmp_path, monkeypatch):
    """★ 3.P：产物目录名用**已经算出来的那份身份**，不在父进程重算。"""

    monkeypatch.setattr(sched, "_candidate_identity", _exploding_identity)
    prepared = sched.sibling("sitin_gates").supervised_prepare(
        "meld_opportunity_cost", {"adj.beta": 20.0})
    ledger = sched.BudgetLedger(table_budget=10)
    manifest = sched.candidate_manifest(
        "meld_opportunity_cost", {"adj.beta": 20.0}, _REPO,
        [{"seed": 1, "scenario_id": "r0"}], {"name": "L1", "roots": 1, "seats": 1},
        ledger, prepared=prepared)
    assert manifest["bound_identity"] == prepared["bound_identity"]
    assert manifest["cell_dir"] == sched.cell_dir_name(prepared["bound_identity"])

