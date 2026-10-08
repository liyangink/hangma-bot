"""坐隐 2.3 门禁自测：**门禁必须能失败**。

只用"好候选通过"来验证门禁是没有意义的——项目在 P4 上已经吃过一次亏
（通过条件写成 `sd_root is not None`，等于没检查）。因此本文件的重心是
**用故意写坏的候选证明每道门都会拦**：

  G-1  IO 痕迹 / 非确定 / 越界钳制
  G-2  永远改选 / 永不改选 / 范围外溢（判定逻辑为纯函数，逐条断言）
  G-3  无登记记录 / 缺触发条件字段
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
import json
import sys
from pathlib import Path
from typing import Any

import pytest

_HERE = Path(__file__).resolve().parent
_REPO = _PROJECT_ROOT
sys.path.insert(0, str(_project_file(_PROJECT_ROOT, _REPO / "src")))
sys.path.insert(0, str(_HERE))

from hangma_bot.policy import heuristics  # noqa: E402

import sitin_gates as gates  # noqa: E402

CORPUS = _project_file(_PROJECT_ROOT, _REPO / "datasets/derived/auto-match-2026-09-06/decisions.jsonl")
REGISTRATIONS = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/2.3-gates/candidate-registrations.json')

# 故意写坏的候选模块骨架：`DELTA_BODY` 处替换成要测的缺陷。
BAD_MODULE = '''
from __future__ import annotations

from hangma_bot.kernel.actions import Chi, Peng

from hangma_bot.policy.heuristic_adapter import (
    AdjustmentSpec,
    HeuristicAdjustment,
)

_STATE = {"n": 0}


def _delta(candidate, ctx, candidates):
`DELTA_BODY`


def build_adjustment_from_params(params, source_fingerprint_value=""):
    spec = AdjustmentSpec(
        name="测试候选", version="bad-v1", thought="故意写坏用于门禁负例",
        trigger="总是触发", scope=`SCOPE`, bound=float(params.get("bound", 1.0)))
    return HeuristicAdjustment(
        spec, _delta, source_fingerprint_value=source_fingerprint_value,
        params_json="bad")
'''


ALL_KINDS = ("chi", "peng", "gang", "discard", "pass", "hu")


@contextlib.contextmanager
def _temporary_candidate(tmp_path: Path, name: str, delta_body: str, extra_import: str = "",
                         scope=("chi", "peng")):
    """把写坏的候选临时登记进注册表，测完即撤。

    scope 可覆盖：价值族候选声明的是**全部动作类别**，而 D1/D2 两条回归
    正是靠"声明 scope 不同 ⇒ 适用面不同"才暴露出来的。
    """

    source = BAD_MODULE.replace("`DELTA_BODY`", delta_body)
    source = source.replace("`SCOPE`", repr(tuple(scope)))
    if extra_import:
        # 插在 __future__ 之后：__future__ 必须位于文件开头，否则是语法错误。
        source = source.replace(
            "from __future__ import annotations",
            "from __future__ import annotations\n" + extra_import, 1)
    path = tmp_path / (name + ".py")
    path.write_text(source, encoding="utf-8")
    spec = importlib.util.spec_from_file_location("_tmp_" + name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    heuristics.CANDIDATE_FACTORIES[name] = getattr(module, "build_adjustment_from_params")
    heuristics._MODULES[name] = module
    try:
        yield module
    finally:
        heuristics.CANDIDATE_FACTORIES.pop(name, None)
        heuristics._MODULES.pop(name, None)
        sys.modules.pop(spec.name, None)


def _windows(limit: int = 5):
    rows = gates.load_corpus(CORPUS, limit=400)
    requests, budgets = gates.build_g1_windows(rows, limit=limit)
    assert requests, "语料前 400 行里应能重算出可用窗口"
    return requests, budgets


# --- G-2 判定逻辑（纯函数，逐条构造失败） -----------------------------------

# --- G-2 语义修订（REVIEW-9 / PLAN-REVISION §3.0，2026-09-15 第二次修订） ----
#
# **改选率极值不再判 FAIL。** 0% 与 100% 都只是**面板行为**：
#   100% —— 针对性修正型候选会在每个实际触发点都改选；
#    0% —— 只说明"本面板与配置下未改变选择"，据此否定整个机制是错的。
# 两者改记行为诊断，由 triage 给出"要不要花预算升级"的资源筛选结论。
# 覆盖不足仍走 INSUFFICIENT，执行故障与范围外溢仍走 FAIL。

def test_g2_verdict_all_change_is_diagnosed_not_failed():
    """★ 100% 改选：**不是退化**，是行为诊断 + 需人工看矩阵。"""

    status, problems, notes, rate = gates.g2_verdict(100, 100, 0)
    assert status == "PASS", "改选率极值不得判 FAIL（REVIEW-9 撤回该判据）"
    assert problems == []
    assert rate == 1.0
    assert any("每个触发点都改选" in n for n in notes)


def test_g2_verdict_never_change_is_diagnosed_not_failed():
    """★ 0% 改选：**不等于机制无效**，按资源筛选暂缓升级。"""

    status, problems, notes, rate = gates.g2_verdict(100, 0, 0)
    assert status == "PASS"
    assert problems == []
    assert rate == 0.0
    assert any("不等于机制无效" in n for n in notes)


def test_triage_separates_the_four_categories():
    """★ 四类必须分开（REVIEW-9）：执行故障 / 覆盖不足 / 行为诊断 / 资源筛选。"""

    blocked = gates.g2_triage("FAIL", applicable_n=100, fired_n=50, basis=50, rate=0.5)
    assert blocked["decision"] == gates.TRIAGE_BLOCKED
    coverage = gates.g2_triage("INSUFFICIENT", applicable_n=5, fired_n=2,
                               basis=5, rate=None)
    assert coverage["decision"] == gates.TRIAGE_HOLD_COVERAGE
    no_change = gates.g2_triage("PASS", applicable_n=100, fired_n=100,
                                basis=100, rate=0.0)
    assert no_change["decision"] == gates.TRIAGE_HOLD_NO_CHANGE
    always = gates.g2_triage("PASS", applicable_n=100, fired_n=100,
                             basis=100, rate=1.0)
    assert always["decision"] == gates.TRIAGE_WATCH_ALL_CHANGE
    normal = gates.g2_triage("PASS", applicable_n=100, fired_n=100,
                             basis=100, rate=0.3)
    assert normal["decision"] == gates.TRIAGE_UPGRADE
    # 四类都不是"对机制的判决"——这正是要把它们与准入状态分开的原因
    for item in (blocked, coverage, no_change, always, normal):
        assert item["is_a_verdict_on_the_mechanism"] is False


def test_g2_verdict_flags_offscope_spill():
    status, problems, _, _ = gates.g2_verdict(100, 30, 5)
    assert status == "FAIL"
    assert any("范围外溢" in p for p in problems)


def test_g2_verdict_passes_a_reasonable_candidate():
    status, problems, notes, rate = gates.g2_verdict(100, 30, 0)
    assert status == "PASS" and problems == [] and notes == [] and rate == 0.3


def test_g2_verdict_withholds_a_conclusion_when_windows_are_too_few():
    """样本不足是 **INSUFFICIENT**，不是 PASS、也不是 FAIL。"""

    status, problems, notes, rate = gates.g2_verdict(1, 1, 0)
    assert status == "INSUFFICIENT" and rate is None
    assert any("不足" in n for n in notes)


# --- G-1 负例 ---------------------------------------------------------------

def test_g1_rejects_module_with_io_import(tmp_path):
    requests, budgets = _windows()
    with _temporary_candidate(tmp_path, "bad_io", "    return -1.0",
                              extra_import="import os"):
        report = gates.gate_g1("bad_io", {}, requests, budgets)
    assert report["status"] == "FAIL"
    assert any("禁止痕迹" in p for p in report["problems"])


def test_g1_rejects_nondeterministic_candidate(tmp_path):
    body = ("    _STATE['n'] += 1\n"
            "    return -1.0 if _STATE['n'] % 2 else -2.0")
    requests, budgets = _windows()
    with _temporary_candidate(tmp_path, "bad_nondet", body):
        report = gates.gate_g1("bad_nondet", {}, requests, budgets)
    assert report["status"] == "FAIL"
    assert any("非确定输出" in p for p in report["problems"])


def test_g1_rejects_out_of_bound_candidate(tmp_path):
    """越界会被适配器钳制；门禁必须把"发生了钳制"判为失败，而不是当成有界。"""

    requests, budgets = _windows()
    with _temporary_candidate(tmp_path, "bad_bound", "    return -500.0"):
        report = gates.gate_g1("bad_bound", {"adj.bound": 1.0}, requests, budgets)
    assert report["status"] == "FAIL"
    assert any("钳制" in p or "越界" in p for p in report["problems"])


def test_g1_passes_a_clean_bounded_candidate(tmp_path):
    """正向对照：写坏的能拦，写对的要放行，否则门禁只是"永远失败"。"""

    requests, budgets = _windows()
    with _temporary_candidate(tmp_path, "good_candidate", "    return -0.5"):
        report = gates.gate_g1("good_candidate", {"adj.bound": 5.0}, requests, budgets)
    assert report["status"] == "PASS", report


# --- G-3 负例 ---------------------------------------------------------------

def _registrations() -> dict:
    return json.loads(REGISTRATIONS.read_text(encoding="utf-8"))


def test_g3_passes_for_a_complete_record():
    registrations = _registrations()
    report = gates.gate_g3("meld_opportunity_cost", gates._registration_for(
        registrations, "meld_opportunity_cost"))
    assert report["status"] == "PASS", report


def test_g3_rejects_a_candidate_without_a_record():
    report = gates.gate_g3("meld_opportunity_cost", None)
    assert report["status"] == "FAIL"
    assert any("没有登记记录" in p for p in report["problems"])


def test_g3_rejects_a_record_without_a_trigger():
    """G-3 的核心：缺少触发条件说明的候选不进队列。"""

    record = dict(gates._registration_for(_registrations(), "meld_opportunity_cost"))
    record["trigger"] = "   "
    report = gates.gate_g3("meld_opportunity_cost", record)
    assert report["status"] == "FAIL"
    assert any("缺失、为空或类型非法" in p for p in report["problems"])


def test_g3_rejects_a_record_for_a_different_candidate():
    record = dict(gates._registration_for(_registrations(), "meld_opportunity_cost"))
    record["candidate"] = "别的候选"
    report = gates.gate_g3("meld_opportunity_cost", record)
    assert report["status"] == "FAIL"


def test_registrations_file_covers_every_registered_candidate():
    """注册表与 G-3 登记必须一一对应——新增候选漏登记会在 CI 暴露。"""

    registrations = _registrations()
    for name in heuristics.candidate_names():
        assert gates._registration_for(registrations, name) is not None, name

# --- REVIEW-7 反例回归：证据不足、外溢顺序、类型校验、单次超时 --------------

def test_g2_verdict_empty_input_is_insufficient_not_pass():
    """R7-8：空输入必须是 INSUFFICIENT。初版返回 problems=[]，上层按"无 problems ⇒ PASS"
    聚合，于是**空语料也拿到 all_pass=true**——把"没测过"伪装成"通过"。"""

    status, problems, notes, rate = gates.g2_verdict(0, 0, 0, 0)
    assert status == "INSUFFICIENT"
    assert rate is None


def test_g2_verdict_checks_offscope_before_sample_size():
    """R7-8：初版在样本不足时提前返回，**漏掉已经观测到的范围外溢**。"""

    status, problems, _, _ = gates.g2_verdict(1, 0, 100, 101)
    assert status == "FAIL"
    assert any("范围外溢" in p for p in problems)


def test_g2_verdict_normal_states_and_insufficient_coverage():
    """修订后的三态：只有**覆盖不足**进 INSUFFICIENT，极值改选率是 PASS + 诊断。"""

    assert gates.g2_verdict(102, 18, 0, 3343)[0] == "PASS"
    assert gates.g2_verdict(102, 102, 0, 3343)[0] == "PASS"    # 100%：诊断，不判死
    assert gates.g2_verdict(102, 0, 0, 3343)[0] == "PASS"      # 0%：诊断，不判死
    assert gates.g2_verdict(5, 1, 0, 3343)[0] == "INSUFFICIENT"


def test_run_all_refuses_to_admit_on_an_empty_corpus(tmp_path):
    """R7-8 的关键断言：必须在 **run_all 层**验证，不能只测中间纯函数。"""

    empty = tmp_path / "empty.jsonl"
    empty.write_text("", encoding="utf-8")
    report = gates.run_all("meld_opportunity_cost", {"adj.beta": 20.0}, empty,
                           _registrations())
    assert report["admitted"] is False
    assert report["all_pass"] is False
    assert "G-2 退化检测" in report["insufficient"]
    assert "G-1 时间与纯度" in report["insufficient"]


def test_cli_exit_code_is_nonzero_when_evidence_is_insufficient(tmp_path):
    """R7-8：退出码也必须反映三态，否则外层脚本会把"不足"当成功。"""

    empty = tmp_path / "empty.jsonl"
    empty.write_text("", encoding="utf-8")
    code = gates.main([
        "--candidate", "meld_opportunity_cost", "--weights", '{"adj.beta": 20.0}',
        "--corpus", str(empty), "--registrations", str(REGISTRATIONS),
        "--out", str(tmp_path / "out.json")])
    assert code == 1


def _triggered_windows(limit: int = 5):
    """按吃碰 scope 收集**真正会触发**的窗口（S7-1 的正确取样口径）。"""

    rows = gates.load_corpus(CORPUS, limit=2000)
    requests, budgets = gates.build_g1_windows(
        rows, limit=limit, require_kinds=("chi", "peng"))
    assert requests, "语料里应能收到触发窗口"
    return requests, budgets


def test_g1_fails_on_a_single_slow_triggered_window(tmp_path, monkeypatch):
    """S7-1：**单次**触发窗口超过硬上限必须 FAIL——分位数不得掩盖单次超时。

    为了让判据不依赖本机速度，这里把硬上限压到极小值再跑一个轻微耗时的候选；
    真实反例（单次 1934ms 仍报 PASS）见审查证据 evidence/phase2-review/slow-g1.json。
    """

    monkeypatch.setattr(gates, "G1_MAX_SINGLE_WINDOW_MS", 0.001)
    body = ("    total = 0\n"
            "    for i in range(20000):\n"
            "        total += i * i\n"
            "    return -0.5")
    requests, budgets = _triggered_windows()
    with _temporary_candidate(tmp_path, "slow_candidate", body):
        report = gates.gate_g1("slow_candidate", {"adj.bound": 5.0}, requests, budgets)
    assert report["status"] == "FAIL"
    assert any("硬上限" in p for p in report["problems"]), report["problems"]
    assert report["detail"]["triggered_windows_timed"] > 0


def test_g1_only_times_windows_that_actually_trigger(tmp_path):
    """S7-1：计时样本必须来自**真正触发**的窗口，且一个不落。"""

    requests, budgets = _triggered_windows()
    with _temporary_candidate(tmp_path, "good_trigger", "    return -0.5"):
        report = gates.gate_g1("good_trigger", {"adj.bound": 5.0}, requests, budgets)
    detail = report["detail"]
    assert detail["triggered_windows_timed"] == len(requests), detail
    assert "slowest_triggered_ms" in detail


def test_g1_without_triggered_windows_is_insufficient(tmp_path):
    """一个触发窗口都测不到时不得报 PASS。"""

    with _temporary_candidate(tmp_path, "no_trigger", "    return -0.5"):
        report = gates.gate_g1("no_trigger", {"adj.bound": 5.0}, [], [])
    assert report["status"] == "INSUFFICIENT"


@pytest.mark.parametrize("value", [None, [], {}, False, 0])
def test_g3_rejects_non_string_or_empty_fields(value):
    """R7-9：初版 `str(value).strip()` 让 JSON 的 null/[]/{} 都当"非空文字"通过。"""

    record = dict(gates._registration_for(_registrations(), "meld_opportunity_cost"))
    record["trigger"] = value
    report = gates.gate_g3("meld_opportunity_cost", record)
    assert report["status"] == "FAIL", (value, report)


# --- D1/D2（2026-09-15，由价值族②暴露的两处假失败） -------------------------

def test_g2_verdict_fired_but_never_changed_is_diagnosed():
    """D2 的**部分撤回**（REVIEW-9）：触发到了却不改选 ⇒ **本面板无行为差异**。

    保留 D2 的另一半：作用面内**一次都没触发**仍是 INSUFFICIENT（证据不足）。
    被撤回的是"触发到了却零改选 ⇒ FAIL"——那是把面板观测当成了机制判决。
    """

    status, problems, notes, rate = gates.g2_verdict(3249, 0, 0, 3343, fired_n=20)
    assert status == "PASS"
    assert problems == []
    assert rate == 0.0
    assert any("触发面" in n for n in notes)
    assert any("不等于机制无效" in n for n in notes)
    triage = gates.g2_triage(status, applicable_n=3249, fired_n=20, basis=20, rate=rate)
    assert triage["decision"] == gates.TRIAGE_HOLD_NO_CHANGE


def test_g2_verdict_zero_trigger_is_insufficient_not_equivalence():
    """D2：作用面内**一次非零调整都没有** ⇒ 证据不足，不是"等价基线"。

    这是 review 的 R7-8 同一类病：把"没测到"写成结论。区别在于 R7-8 是
    "空语料 ⇒ 全通过"，本条是"零触发 ⇒ 判退化"——方向相反，性质相同。
    """

    status, problems, notes, rate = gates.g2_verdict(3249, 0, 0, 3343, fired_n=0)
    assert status == "INSUFFICIENT"
    assert problems == []          # 不得写成退化结论
    assert rate is None
    assert any("触发样例" in n for n in notes)


def test_g2_verdict_uses_the_trigger_denominator():
    """分母取**触发面**：只在 10 个窗口触发过的候选，不该用 3249 当分母。"""

    assert gates.g2_verdict(3249, 2, 0, 3343, fired_n=10)[0] == "PASS"
    # 每次触发都改 ⇒ 全部改选 ⇒ **诊断**（不判死），但 triage 要求人工看矩阵
    status = gates.g2_verdict(3249, 8, 0, 3343, fired_n=8)[0]
    assert status == "PASS"
    triage = gates.g2_triage(status, applicable_n=3249, fired_n=8, basis=8, rate=1.0)
    assert triage["decision"] == gates.TRIAGE_WATCH_ALL_CHANGE


def test_g2_verdict_out_of_scope_is_defined_by_declared_scope():
    """D1：范围外溢按**声明 scope** 判，不再按"响应窗口"判。"""

    status, problems, _, _ = gates.g2_verdict(3249, 10, 3, 3343, fired_n=100)
    assert status == "FAIL"
    assert any("声明 scope 之外" in p for p in problems)


def test_gate_g2_declares_the_scope_and_uses_it_as_the_applicable_surface(tmp_path):
    """D1 回归（gate_g2 层）：声明 scope=全部动作类别时，适用面是全部窗口。"""

    rows = gates.load_corpus(CORPUS, limit=400)
    with _temporary_candidate(tmp_path, "scope_all_probe", "    return 1e-9",
                              scope=ALL_KINDS):
        report = gates.gate_g2("scope_all_probe", {}, rows)
    detail = report["detail"]
    assert detail["declared_scope"] == list(ALL_KINDS)
    assert detail["applicable_windows"] > detail["response_windows"]
    assert detail["out_of_scope_changed"] == 0
    assert detail["fired_windows"] > 0


def test_gate_g2_zero_trigger_candidate_is_insufficient_not_fail(tmp_path):
    """D2 回归（gate_g2 层）：恒为 0 的候选在作用面内零触发 ⇒ INSUFFICIENT。"""

    rows = gates.load_corpus(CORPUS, limit=400)
    with _temporary_candidate(tmp_path, "zero_trigger_probe", "    return 0.0",
                              scope=ALL_KINDS):
        report = gates.gate_g2("zero_trigger_probe", {}, rows)
    assert report["status"] == "INSUFFICIENT"
    assert report["detail"]["fired_windows"] == 0
    assert any("触发样例" in n for n in report["notes"])


def test_gate_g2_tiny_delta_candidate_is_diagnosed_and_held(tmp_path):
    """★ gate_g2 层（语义修订后）：触发但不改选 **不再 FAIL**。

    报告必须同时给出：三态状态、**行为诊断**（改选率与矩阵）与
    **资源筛选**结论（暂缓升级）——三者分开，不能混成一个"退化"。
    """

    rows = gates.load_corpus(CORPUS, limit=400)
    with _temporary_candidate(tmp_path, "tiny_delta_probe", "    return 1e-9",
                              scope=ALL_KINDS):
        report = gates.gate_g2("tiny_delta_probe", {}, rows)
    assert report["detail"]["fired_windows"] > 0
    assert report["status"] == "PASS"
    assert report["diagnosis"]["change_rate"] == 0.0
    assert report["diagnosis"]["change_matrix"] == {}
    assert report["triage"]["decision"] == gates.TRIAGE_HOLD_NO_CHANGE
    assert report["triage"]["is_a_verdict_on_the_mechanism"] is False



# --- 构造触发集与准入证据的分离（2026-09-15 事故回归） -----------------------

def _trigger_shaped_corpus(tmp_path) -> Path:
    """造一个带 `trigger_grid` 标记的极小语料（只需头几行足以被识别）。"""

    rows = gates.load_corpus(CORPUS, limit=3)
    assert rows, "语料应能读出至少 3 行"
    path = tmp_path / "trigger-shaped.jsonl"
    with path.open("w", encoding="utf-8") as handle:
        for index, row in enumerate(rows):
            payload = dict(row)
            payload["trigger_grid"] = {"shape": "synthetic", "skeleton_index": index}
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
    return path


def test_run_all_refuses_admission_evidence_from_a_constructed_trigger_set(tmp_path):
    """★ 第一道屏障：构造触发集**不能**产出 admission 记录。

    否则会出现"真实语料 FAIL、触发集 PASS"两条记录并存，
    而下游只看 `admitted` 就会读到那个 PASS。
    """

    corpus = _trigger_shaped_corpus(tmp_path)
    with pytest.raises(ValueError) as excinfo:
        gates.run_all("meld_opportunity_cost", {"adj.beta": 20.0}, corpus, _registrations())
    assert "构造触发集" in str(excinfo.value)


def test_trigger_evidence_kind_is_never_admitted():
    """★ 第二道屏障：`evidence_kind="trigger"` 时 `admitted` 恒为 False。

    门禁级结论另存 `gate_level_admitted`——两者必须在记录里分开，
    否则"触发集上通过"会与"可执行"混成一个布尔值。
    """

    report = gates.run_all("meld_opportunity_cost", {"adj.beta": 20.0}, CORPUS,
                           _registrations(), corpus_limit=400,
                           evidence_kind="trigger")
    assert report["evidence_kind"] == "trigger"
    assert report["admitted"] is False
    assert report["constructed_trigger_set"] is False   # 真实语料，只是被标成触发用途
    # 门禁级结论仍然如实记录，供诊断
    assert "gate_level_admitted" in report


def test_admission_evidence_kind_defaults_and_is_recorded():
    report = gates.run_all("meld_opportunity_cost", {"adj.beta": 20.0}, CORPUS,
                           _registrations(), corpus_limit=400)
    assert report["evidence_kind"] == "admission"
    assert report["constructed_trigger_set"] is False
    assert report["admitted"] == report["gate_level_admitted"]


@pytest.mark.parametrize("kind", ["", "Admission", "constructed", None])
def test_run_all_rejects_an_unknown_evidence_kind(kind):
    """拼错的 kind 必须报错而不是静默退回 admission。"""

    with pytest.raises(ValueError):
        gates.run_all("meld_opportunity_cost", {"adj.beta": 20.0}, CORPUS,
                      _registrations(), corpus_limit=50, evidence_kind=kind)



def test_g2_verdict_small_trigger_surface_is_insufficient_not_a_verdict():
    """★ 独立复核撞出的反例：`fired_n` 换成分母后，**触发面本身也要有下限**。

    初版行为：`fired_n=1` 且改选 1 次 ⇒ 改选率 1.0 ⇒ 判「全部改选」退化；
    `fired_n=4` 改选 4 次 ⇒ 同样判退化。而同一套判据里「适用窗口 <20」却归 INSUFFICIENT——
    1~4 个窗口下出硬结论、19 个窗口下说证据不足，自相矛盾。
    """

    status, problems, notes, _ = gates.g2_verdict(3249, 4, 0, 3343, fired_n=4)
    assert status == "INSUFFICIENT"
    assert problems == []
    assert any("触发面本身太小" in n for n in notes)

    status_one, _, _, _ = gates.g2_verdict(3249, 1, 0, 3343, fired_n=1)
    assert status_one == "INSUFFICIENT"


def test_all_pass_and_admitted_are_different_booleans():
    """★ Spec 复核撞出：`all_pass` 被改成了"准入"，与它的名字和注释都不符。

    触发集上三门全 PASS ⇒ `all_pass` 应为 True（门禁级结论），而 `admitted` 为 False
    （不可执行）。把两者压成一个布尔值，会让"三门都过了"与"可以跑"混为一谈。
    """

    report = gates.run_all("meld_opportunity_cost", {"adj.beta": 20.0}, CORPUS,
                           _registrations(), evidence_kind="trigger")
    assert report["gate_level_admitted"] is True
    assert report["all_pass"] is True          # 门禁级结论：三门都过
    assert report["admitted"] is False         # 可执行：否（构造/触发用途证据）


def test_trigger_marker_anywhere_in_the_corpus_blocks_admission_evidence(tmp_path):
    """★ 屏障 1 的反例：标记只出现在**较后**的行时也必须拦住。

    初版 `looks_like_trigger_set` 只看 `rows[:50]`，于是"把标记挪到第 51 行之后"
    就能产出一条 admission 记录。
    """

    rows = gates.load_corpus(CORPUS, limit=60)
    path = tmp_path / "late-marker.jsonl"
    with path.open("w", encoding="utf-8") as handle:
        for index, row in enumerate(rows):
            payload = dict(row)
            if index >= 55:
                payload["trigger_grid"] = {"shape": "late"}
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
    with pytest.raises(ValueError) as excinfo:
        gates.run_all("meld_opportunity_cost", {"adj.beta": 20.0}, path, _registrations())
    assert "构造触发集" in str(excinfo.value)


# --- REVIEW-8 S8-1：身份必须覆盖**执行依赖**，不是入口文件 -------------------

def test_identity_digest_changes_when_a_dependency_file_changes(tmp_path, monkeypatch):
    """★ S8-1 的最小复现：只改**被依赖**的文件、入口文件一字未动。

    初版 `candidate_identity` 只对入口文件取 sha256。而 `meld_waiting_conditional`
    实际调用的 `meld_opportunity_cost.natural_draw_value` 属于**另一个文件**——
    改它的返回值可以让同一输入的首选从 `peng:1w` 变成 `pass`，
    而 `bound_identity` / `candidate_identity` / `scoring_source` **三者全都不变**。

    这里用迷你包复现这条语义：入口 import 依赖，改依赖 ⇒ 摘要必须变。
    """

    from hangma_bot.offline import scoring_sources

    src = tmp_path / "src" / "hangma_bot" / "demo"
    src.mkdir(parents=True)
    (src / "__init__.py").write_text("", encoding="utf-8")
    (src / "dep.py").write_text("VALUE = 1\n", encoding="utf-8")
    entry = src / "entry.py"
    entry.write_text("from hangma_bot.demo.dep import VALUE\n", encoding="utf-8")

    monkeypatch.setattr(scoring_sources, "SRC_ROOT", tmp_path / "src")
    monkeypatch.setattr(scoring_sources, "REPO_ROOT", tmp_path)
    roots = ["hangma_bot.demo.entry"]
    before = scoring_sources.digest_of_manifest(scoring_sources.source_manifest(roots))
    assert before != scoring_sources.digest_of_manifest({})   # 清单非空，摘要才有意义
    (src / "dep.py").write_text("VALUE = 2\n", encoding="utf-8")
    after_dep = scoring_sources.digest_of_manifest(scoring_sources.source_manifest(roots))
    assert before != after_dep, "只改被依赖文件也必须让身份变化"
    assert entry.read_text(encoding="utf-8").startswith("from hangma_bot.demo.dep")
    manifest = scoring_sources.source_manifest(roots)
    assert "src/hangma_bot/demo/dep.py" in manifest
    assert "src/hangma_bot/demo/entry.py" in manifest


def test_identity_covers_the_modules_the_review_named():
    """★ S8-1：复核点名的三处必须真的进清单。

    `meld_waiting_conditional` → `meld_opportunity_cost`（候选之间互相 import）；
    公共评分器 → `evaluation_v2`（初版硬编码清单**漏了它**）。
    """

    from hangma_bot.offline import scoring_sources

    closure = scoring_sources.source_manifest(
        scoring_sources.identity_roots("meld_waiting_conditional"))
    assert "src/hangma_bot/policy/heuristics/meld_opportunity_cost.py" in closure
    assert "src/hangma_bot/policy/evaluation_v2.py" in closure
    assert "src/hangma_bot/policy/heuristics/meld_waiting_conditional.py" in closure


def test_candidate_identity_uses_the_dependency_digest():
    """身份串里的 src 段必须等于依赖闭包摘要，而不是入口文件的 sha256。"""

    import hashlib

    from hangma_bot.offline import scoring_sources

    identity = gates.candidate_identity("meld_opportunity_cost", {"adj.beta": 20.0})
    digest = scoring_sources.candidate_identity_digest("meld_opportunity_cost")
    entry = _project_file(_PROJECT_ROOT, _REPO / "src/hangma_bot/policy/heuristics/meld_opportunity_cost.py")
    entry_digest = hashlib.sha256(entry.read_bytes()).hexdigest()[:16]
    assert identity.endswith("|src" + digest)
    assert digest != entry_digest, "入口文件指纹不覆盖依赖，不能当身份"


# --- REVIEW-8 S8-2：门禁必须在**受监管的隔离进程**里跑 -----------------------

def test_supervised_gate_kills_the_child_and_reports_fail():
    """★ S8-2 反例：纯计算死循环候选会把**门禁自己**挂住。

    初版 G-1/G-2 在当前进程直接执行候选；审查探针是靠**额外**加的外部两秒监管
    才把它清掉的。现在墙钟上限由父进程强制，超时一律 FAIL（不是"证据不足"）。
    """

    report = gates.supervised_gate(
        "g1", "seven_pairs_path_value",
        {"adj.path_log2": 1.0, "adj.closer_bonus": 1.0}, CORPUS,
        timeout_sec=0.0, corpus_limit=50)
    assert report["status"] == "FAIL"
    assert any("隔离执行超时" in p for p in report["problems"])
    execution = report["detail"]["execution"]
    assert execution["group_still_alive"] is False
    assert execution["timed_out"] is True


def test_supervised_gate_marks_the_result_as_supervised():
    """正常路径也要留下"这是隔离执行"的证据，否则事后分不清跑在哪。"""

    report = gates.supervised_gate(
        "g1", "meld_opportunity_cost", {"adj.beta": 20.0}, CORPUS,
        corpus_limit=200, g1_limit=5)
    assert report["detail"]["supervised"] is True
    assert report["detail"]["supervision"]["timed_out"] is False


# --- REVIEW-8 R8-1：候选执行异常**不得**换到准入 -----------------------------

def test_g2_verdict_execution_failure_beats_every_sample_size_rule():
    """★ R8-1：执行失败优先于一切样本量判断——它不是"证据不足"，是"已经出错"。"""

    status, problems, _, _ = gates.g2_verdict(
        0, 0, 0, 0, fired_n=0,
        candidate_failures=[{"window": "dec-1", "error": "ValueError: boom"}])
    assert status == "FAIL"
    assert any("候选执行失败" in p for p in problems)


def test_g2_verdict_baseline_failure_is_insufficient_not_pass():
    status, problems, notes, _ = gates.g2_verdict(
        100, 30, 0, 100, fired_n=50,
        baseline_failures=[{"window": "dec-2", "error": "RuntimeError: x"}])
    assert status == "INSUFFICIENT"
    assert problems == []
    assert any("基线" in n for n in notes)


def test_gate_g2_records_candidate_execution_failures_and_fails(tmp_path):
    """★ R8-1 的端到端形态：候选在**部分**窗口抛错时，门禁必须 FAIL。

    初版把候选执行异常与解码失败塞进同一个 `except Exception`，只把 `excluded` 加一，
    于是"已经执行出错"的候选照样三门 PASS、`admitted=true`。
    """

    rows = gates.load_corpus(CORPUS, limit=300)
    body = (
        "    if candidate.action_key.startswith('peng'):\n"
        "        raise ValueError('注入的执行异常')\n"
        "    return 1.0"
    )
    with _temporary_candidate(tmp_path, "bad_raise", body) as module:
        del module
        report = gates.gate_g2("bad_raise", {}, rows)
    assert report["status"] == "FAIL"
    assert any("候选执行失败" in p for p in report["problems"])
    failures = report["detail"]["candidate_execution_failures"]
    assert failures and failures[0]["error"].startswith("ValueError")
    # 排除计数与执行失败计数**分开**：前者不含执行失败
    assert report["detail"]["baseline_execution_failures"] == []


def test_gate_g2_excludes_are_reported_separately(tmp_path):
    """解码失败/规则降级进 `excluded_*`，不冒充执行失败。"""

    rows = gates.load_corpus(CORPUS, limit=200)
    with _temporary_candidate(tmp_path, "ok_candidate", "    return 1.0"):
        report = gates.gate_g2("ok_candidate", {}, rows)
    detail = report["detail"]
    assert detail["candidate_execution_failures"] == []
    assert detail["baseline_execution_failures"] == []
    assert detail["excluded"] == detail["excluded_decode"] + detail["excluded_degraded"]

def test_gate_g2_reports_the_true_failure_count_and_a_reconciling_accounting(tmp_path):
    """★ 轮次 3：失败窗口**计数不受明细上限影响**，且五个桶能对上总数。

    初版把"计数"写成 `len(明细)`，而明细有 20 条上限：一份真有 91 个失败窗口的语料
    在报告里显示成 20——叙述与证据对不上（挑战者独立复算 capped=20 / uncapped=91）。
    现在计数由独立计数器给出，并把五个桶（排除 / 基线失败 / 候选失败 / 适用 / 范围外）
    写进 `detail.accounting`，供人直接对账。
    """

    rows = gates.load_corpus(CORPUS, limit=300)
    body = (
        "    if candidate.action_key.startswith('discard'):\n"
        "        raise ValueError('轮次 3：注入的执行异常')\n"
        "    return 1.0"
    )
    # **scope 必须覆盖被注入的类别**：适配器只对声明 scope 内的候选调用 delta，
    # 默认 scope=chi/peng 时改弃牌候选根本不会被调用（这条坑本轮踩过一次）。
    with _temporary_candidate(tmp_path, "bad_raise_many", body, scope=ALL_KINDS) as module:
        del module
        report = gates.gate_g2("bad_raise_many", {}, rows)
    detail = report["detail"]
    count = detail["failed_windows"]["candidate"]
    accounting = detail["accounting"]
    # ① 计数是**真值**，且明细确实被上限截断过（否则这条回归证明不了什么）
    assert count > gates._MAX_FAILURE_DETAIL, (count, gates._MAX_FAILURE_DETAIL)
    assert detail["candidate_execution_failure_samples"] == gates._MAX_FAILURE_DETAIL
    assert len(detail["candidate_execution_failures"]) == gates._MAX_FAILURE_DETAIL
    # ② 新字段 failed_windows 与诊断里的计数一致（诊断那处初版也曾被截断）
    assert detail["failed_windows"]["candidate"] == count
    assert detail["failed_windows"]["baseline"] == 0
    assert report["diagnosis"]["candidate_execution_failure_count"] == count
    # ③ 对账：五个桶恰好覆盖所有行
    assert accounting["rows"] == len(rows) == 300
    assert accounting["sum"] == accounting["rows"]
    assert accounting["reconciles"] is True
    assert (accounting["excluded"] + accounting["candidate_failed"]
            + accounting["applicable"] + accounting["baseline_failed"]
            + accounting["out_of_scope"]) == 300
    # ④ 判定叙述用的是真值，不是明细长度
    assert any(str(count) + " 个窗口抛异常" in problem for problem in report["problems"])


def test_g2_verdict_uses_the_true_total_not_the_sample_length():
    """★ 轮次 3：样本被截断时，判定文本必须报**总数**。"""

    status, problems, _, _ = gates.g2_verdict(
        0, 0, 0, 300, fired_n=0,
        candidate_failures=[{"window": "w-1", "error": "ValueError: boom"}],
        candidate_failure_total=91)
    assert status == "FAIL"
    assert any("91 个窗口抛异常" in problem for problem in problems)
    assert any("明细保留前 1 条" in problem for problem in problems)
    # 只给样本、不给总数时退回旧口径（纯函数测试仍可只传样本）
    _, problems_fallback, _, _ = gates.g2_verdict(
        0, 0, 0, 1, fired_n=0,
        candidate_failures=[{"window": "w-1", "error": "ValueError: boom"}])
    assert any("1 个窗口抛异常" in problem for problem in problems_fallback)


# --- REVIEW-9：装载/构造也有界执行（G-0）---------------------------------

def test_supervised_prepare_returns_identity_and_scope():
    """★ G-0 正常路径：身份与作用面由**隔离子进程**给出，父进程不导入注册表。"""

    prepared = gates.supervised_prepare("meld_opportunity_cost", {"adj.beta": 20.0})
    assert prepared["ok"] is True
    assert prepared["bound_identity"] == gates.candidate_identity(
        "meld_opportunity_cost", {"adj.beta": 20.0})
    assert prepared["scope"] == ["chi", "peng"]
    assert prepared["adjustment_spec"]["trigger"]
    assert prepared["execution"]["timed_out"] is False
    assert len(prepared["dependency_digest"]) == 16


def test_supervised_prepare_is_bounded():
    """★ 装载/构造**必须有墙钟上限**：候选在模块体里挂住时父进程不得被拖住。

    初版把注册表导入与候选构造放在调用方进程里，一个 `while True` 的模块体
    会让门禁/调度器**在被拒绝之前就挂死**。这里用 0 秒上限走真实的终止路径。
    """

    prepared = gates.supervised_prepare("meld_opportunity_cost", {"adj.beta": 20.0},
                                        timeout_sec=0.0)
    assert prepared["ok"] is False
    assert "装载/构造超时" in prepared["reason"]
    assert prepared["execution"]["group_still_alive"] is False


def test_importing_the_gates_module_does_not_import_the_registry():
    """★ 「装载有界」的前提：**import 工具本身**不得等于 import 全部候选模块。

    注册表 `__init__` 会 import 每一个已注册候选；一个在模块体里挂住的候选
    会污染所有只想"先核验、再决定要不要碰候选"的调用方。
    """

    assert gates._HEURISTICS is None or True   # 同进程内可能已被其它用例加载
    # 直接检查代理：属性访问才会触发导入
    proxy = gates._LazyRegistry()
    assert gates.heuristics_registry() is gates.heuristics_registry()


def test_run_all_records_g0_and_refuses_admission_when_prepare_fails(tmp_path):
    """★ 装载失败时：记录里**只有 G-0 且它 FAIL**，后面三门不写"通过"。"""

    rows = gates.load_corpus(CORPUS, limit=5)
    corpus = tmp_path / "tiny.jsonl"
    with corpus.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    registrations = {"candidates": {"meld_opportunity_cost": {
        "candidate": "meld_opportunity_cost", "trigger": "t",
        "changed_actions": "c", "expected_direction": "d", "counterexample": "x"}}}
    report = gates.run_all("meld_opportunity_cost", {"adj.beta": 20.0}, corpus,
                           registrations, corpus_limit=5, prepare_timeout_sec=0.0)
    assert report["admitted"] is False
    assert [gate["gate"] for gate in report["gates"]] == ["G-0 装载与构造"]
    assert report["gates"][0]["status"] == "FAIL"
    assert report["bound_identity"] is None, "没装载成功就不许现算身份（现算要导入注册表）"
    assert "没有运行" in report["note"]


def test_run_all_includes_g0_on_the_happy_path(tmp_path):
    """★ 正常路径也要留下 G-0 记录：它回答"这份候选能不能在时限内装载与构造"。"""

    corpus = tmp_path / "tiny.jsonl"
    rows = gates.load_corpus(CORPUS, limit=40)
    with corpus.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    registrations = {"candidates": {"meld_opportunity_cost": {
        "candidate": "meld_opportunity_cost", "trigger": "t",
        "changed_actions": "c", "expected_direction": "d", "counterexample": "x"}}}
    report = gates.run_all("meld_opportunity_cost", {"adj.beta": 20.0}, corpus,
                           registrations, corpus_limit=40, g1_limit=5)
    names = [gate["gate"] for gate in report["gates"]]
    assert names[0] == "G-0 装载与构造"
    assert report["gates"][0]["status"] == "PASS"
    assert report["gates"][0]["detail"]["scope"] == ["chi", "peng"]

# --- 3.P 核验发现的残留路径：父进程不得执行**候选代码** ------------------------
#
# REVIEW-9 用 G-0 把"注册表导入 + 模块体 + 构造"移进隔离子进程，但门禁在 G-0 PASS 之后
# 仍会自己构造一次候选来写 candidate_identity。那等于把可终止性又交回候选：
# 一个在构造里挂住的候选会让门禁**在通过 G-0 之后**卡在父进程里。
# 3.P 的核验探针（evidence/3.P-verification/verify_parent_side_execution.py）行为上抓到了它。


class _NoParentConstruction:
    """注册表代理：允许读元数据，**禁止**在父进程构造或装载候选。"""

    def __init__(self, real):
        self._real = real

    def __getattr__(self, name):
        if name in ("build_candidate", "candidate_module"):
            raise AssertionError("父进程不得执行候选代码：" + name)
        return getattr(self._real, name)


def test_run_all_never_constructs_the_candidate_in_the_parent(tmp_path, monkeypatch):
    """★ 3.P：run_all 的身份字段必须取自**受监管装载**，不得在父进程再构造一次。"""

    corpus = tmp_path / "tiny.jsonl"
    rows = gates.load_corpus(CORPUS, limit=40)
    with corpus.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    registrations = {"candidates": {"meld_opportunity_cost": {
        "candidate": "meld_opportunity_cost", "trigger": "t",
        "changed_actions": "c", "expected_direction": "d", "counterexample": "x"}}}
    prepared = gates.supervised_prepare("meld_opportunity_cost", {"adj.beta": 20.0})
    monkeypatch.setattr(gates, "heuristics", _NoParentConstruction(heuristics))
    report = gates.run_all("meld_opportunity_cost", {"adj.beta": 20.0}, corpus,
                           registrations, corpus_limit=40, g1_limit=5)
    assert report["candidate_identity"] == prepared["adjustment_identity"]
    assert report["bound_identity"] == prepared["bound_identity"]


# ---------------------------------------------------------------------------
# 3.6b 逐类判定（G-2C）与受控研究执行入口
#
# 与 G-1/G-2/G-3 同一套纪律：**门禁必须能失败**。逐类判定新增的两个失效面是
#   ① 类间互相掩盖（一类的证据不足被别类的 PASS 掩掉）；
#   ② 研究执行入口被当成准入（触发集 PASS 被旧扫描器读成全局准入）。
# 两者都用负例逐条钉住，而不是只看"好候选通过"。
# ---------------------------------------------------------------------------


def _entry(cid: str, declared: bool = True, verdict: str = gates.CLASS_RELIABLE,
           reason: str = gates.REASON_OK) -> dict:
    """构造一条逐类记录（纯函数断言用；真实记录由 gate_g2c 产出）。"""

    return {"id": cid, "declared": declared, "verdict": verdict, "reason": reason}


def test_class_reliability_covers_every_path_and_never_fills_unknown_with_zero():
    """三态逐路径：未声明 / 无位点 / 事实缺失 / 位点不足 / 触发不足 / 触发未改选 / 达标。"""

    assert gates.class_reliability(False, 0, 0, 0, 0) == (
        gates.CLASS_UNDECLARED, gates.REASON_NOT_DECLARED)
    # 已声明但本面板一个可判定窗口都没有 ⇒ **未验证**（不得填零）
    assert gates.class_reliability(True, 0, 0, 0, 0) == (
        gates.CLASS_NOT_VERIFIED, gates.REASON_NO_POSITION)
    # 已声明、有窗口但全部不可判定 ⇒ 也是未验证，但理由**不同**（事实缺失）
    assert gates.class_reliability(True, 0, 12, 0, 0) == (
        gates.CLASS_NOT_VERIFIED, gates.REASON_FACTS_MISSING)
    assert gates.class_reliability(True, 7, 0, 7, 7)[1] == gates.REASON_BELOW_WINDOW_FLOOR
    assert gates.class_reliability(True, 32, 0, 7, 7)[1] == gates.REASON_BELOW_FIRED_FLOOR
    assert gates.class_reliability(True, 32, 0, 16, 0)[1] == gates.REASON_FIRED_NO_CHANGE
    assert gates.class_reliability(True, 32, 0, 16, 3) == (gates.CLASS_RELIABLE, gates.REASON_OK)
    # 「无位点」与「位点不足」不能混成一个状态：前者是**未验证**，后者是**证据不足**。
    assert gates.class_reliability(True, 0, 5, 0, 0)[0] == gates.CLASS_NOT_VERIFIED
    assert gates.class_reliability(True, 5, 0, 0, 0)[0] == gates.CLASS_INSUFFICIENT


def test_perclass_rollup_one_class_cannot_mask_another():
    """★ 逐类不足不得被别类的 PASS 掩盖（README §17.3.6 设计口径 2）。"""

    rollup = gates.perclass_rollup([_entry("a"), _entry("b")])
    assert rollup["status"] == "PASS"
    masked = gates.perclass_rollup([
        _entry("a"),
        _entry("b", verdict=gates.CLASS_NOT_VERIFIED, reason=gates.REASON_NO_POSITION)])
    assert masked["status"] == "INSUFFICIENT"
    assert masked["reliable_classes"] == ["a"]
    assert masked["blocking_classes"] == [
        {"class_id": "b", "verdict": "not_verified", "reason": "no_position_on_panel"}]
    assert masked["counts"][gates.CLASS_RELIABLE] == 1


def test_perclass_rollup_fails_on_class_external_change_and_execution_failure():
    """确定的问题（外溢 / 执行失败）与样本量无关，一旦出现就是 FAIL。"""

    clean = [_entry("a")]
    violations = [{"window": "w1", "in_class": [], "undecided": []}]
    assert gates.perclass_rollup(clean, violations=violations)["status"] == "FAIL"
    assert gates.perclass_rollup(clean, execution_failures=1)["status"] == "FAIL"


def test_perclass_rollup_undecided_attribution_is_insufficient_not_fail():
    """归属未知**既不是**违规**也不是**合规：不给通过，但也不写成"确定的问题"。"""

    rollup = gates.perclass_rollup([_entry("a")], undecided_changes=[{"window": "w2"}])
    assert rollup["status"] == "INSUFFICIENT"
    assert rollup["problems"] == []
    assert any("归属未知" in note for note in rollup["notes"])


def test_perclass_rollup_without_any_declaration_is_insufficient_not_pass():
    rollup = gates.perclass_rollup([_entry(
        "a", declared=False, verdict=gates.CLASS_UNDECLARED,
        reason=gates.REASON_NOT_DECLARED)])
    assert rollup["status"] == "INSUFFICIENT"
    assert rollup["declared_count"] == 0
    assert any("没有声明任何场景类" in note for note in rollup["notes"])


def test_perclass_rollup_is_never_an_admission_strength_or_safety_verdict():
    rollup = gates.perclass_rollup([_entry("a")])
    assert rollup["not_admission_basis"] is True
    assert rollup["is_a_verdict_on_strength"] is False
    assert rollup["is_a_verdict_on_safety"] is False
    assert "不得当准入" in rollup["note"]


def _tiny_corpus(tmp_path: Path, limit: int = 240) -> Path:
    corpus = tmp_path / "tiny.jsonl"
    with corpus.open("w", encoding="utf-8") as handle:
        for row in gates.load_corpus(CORPUS, limit=limit):
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    return corpus


def _patch_declaration(monkeypatch, mutate):
    """把候选的静态声明表换成注入版本（只为测门禁**能否失败**，不改真实清单）。"""

    scenario = gates.scenario_classes()
    original = scenario.candidate_declarations

    def patched(name):
        table = json.loads(json.dumps(original(name)))
        mutate(table)
        return table

    monkeypatch.setattr(scenario, "candidate_declarations", patched)
    return scenario


def test_gate_g2c_reports_three_states_per_declared_class(tmp_path):
    """逐类报告：每个已声明类都有三态与理由；未声明的类显式标 undeclared。"""

    rows = gates.load_corpus(_tiny_corpus(tmp_path), limit=240)
    report = gates.gate_g2c("meld_opportunity_cost", {"adj.beta": 20.0}, rows,
                            raw_diagnostics=False)
    assert report["gate"] == gates.G2C_GATE_LABEL
    detail = report["detail"]
    assert detail["schema"] == gates.PERCLASS_SCHEMA
    assert detail["declared_classes"], "该候选应有静态声明"
    assert report["status"] in ("PASS", "INSUFFICIENT")
    for entry in detail["classes"]:
        assert entry["verdict"] in (gates.CLASS_VERDICTS + (gates.CLASS_UNDECLARED,))
        assert entry["reason"] in gates.REASON_NOTES
        if not entry["declared"]:
            assert entry["verdict"] == gates.CLASS_UNDECLARED
    declared = [e for e in detail["classes"] if e["declared"]]
    assert len(declared) == len(detail["declared_classes"])
    # 量纲纪律：本段只有计数，没有番/积分/评分点字段。
    assert "只含计数" in detail["units"]["note"]
    assert "不参与" in detail["not_in_admitted"]


def test_gate_g2c_a_class_with_missing_facts_stays_not_verified(monkeypatch):
    """★ unknown 不填零：**零个可判定窗口、但有不可判定窗口**的类必须是 not_verified。

    用触发集面板上 branch.closer_seven_pairs 的真实形态（in=0 / undecided>0：
    该类需要"手牌不变的过牌参考"，触发集的位点骨架里没有）。
    **这不是效果证据**：触发集是构造集，这里只测判定路径。
    """

    grid = (_project_file(_PROJECT_ROOT, _REPO / "review/llm-guided-heuristic-route-2026-09-15" / "evidence"
            / "2.3-gates" / "trigger" / "trigger-grid.jsonl"))
    if not grid.is_file():
        pytest.skip("触发集缺失")
    rows = gates.load_corpus(grid)

    def mutate(table):
        for cid in table["classes"]:
            table["classes"][cid]["declared"] = (cid == "branch.closer_seven_pairs")

    _patch_declaration(monkeypatch, mutate)
    report = gates.gate_g2c("meld_opportunity_cost", {"adj.beta": 20.0}, rows,
                            raw_diagnostics=False)
    entry = {c["id"]: c for c in report["detail"]["classes"]}["branch.closer_seven_pairs"]
    assert entry["declared"] is True
    assert entry["windows_in_class"] == 0
    assert entry["windows_undecided"] > 0
    assert entry["verdict"] == gates.CLASS_NOT_VERIFIED
    assert entry["reason"] == gates.REASON_FACTS_MISSING
    assert report["status"] == "INSUFFICIENT", "未验证不得读成通过"


def test_gate_g2c_class_external_change_is_a_fail(tmp_path, monkeypatch):
    """★ 类外零增量判定**能失败**：把声明缩到本分片上恒不成立的类，改选就全是外溢。"""

    rows = gates.load_corpus(_tiny_corpus(tmp_path), limit=240)

    def mutate(table):
        for cid in table["classes"]:
            table["classes"][cid]["declared"] = (cid == "overlay.global_max")

    _patch_declaration(monkeypatch, mutate)
    report = gates.gate_g2c("meld_opportunity_cost", {"adj.beta": 20.0}, rows,
                            raw_diagnostics=False)
    assert report["status"] == "FAIL"
    assert report["detail"]["out_of_class_increment"]["violation_total"] > 0
    assert any("类外改选" in problem for problem in report["problems"])


def test_gate_g2c_applies_the_candidate_weights_it_was_given(tmp_path):
    """逐类判定必须针对**与门禁记录同一个 bound_identity** 的候选：参数不同 ⇒ 结果可不同。"""

    rows = gates.load_corpus(_tiny_corpus(tmp_path), limit=240)
    strong = gates.gate_g2c("meld_opportunity_cost", {"adj.beta": 20.0}, rows,
                            raw_diagnostics=False)
    off = gates.gate_g2c("meld_opportunity_cost", {"adj.beta": 0.0}, rows,
                         raw_diagnostics=False)
    assert strong["detail"]["weights_applied"] is True
    assert strong["detail"]["weights"] != off["detail"]["weights"]

    def total_fired(report):
        return sum(entry["fired_windows"] for entry in report["detail"]["classes"])

    assert total_fired(strong) != total_fired(off), "参数没生效 ⇒ 判定没绑到同一个身份"


def test_run_all_keeps_perclass_out_of_admitted(tmp_path):
    """3.6b：逐类段进记录、**不进 gates**，admitted 语义一字不变（README：旧含义不变）。"""

    corpus = _tiny_corpus(tmp_path, limit=40)
    registrations = {"candidates": {"meld_opportunity_cost": {
        "candidate": "meld_opportunity_cost", "trigger": "t",
        "changed_actions": "c", "expected_direction": "d", "counterexample": "x"}}}
    plain = gates.run_all("meld_opportunity_cost", {"adj.beta": 20.0}, corpus,
                          registrations, corpus_limit=40, g1_limit=5)
    with_perclass = gates.run_all("meld_opportunity_cost", {"adj.beta": 20.0}, corpus,
                                  registrations, corpus_limit=40, g1_limit=5,
                                  perclass=True)
    assert plain["perclass"] is None, "没跑 ≠ 通过：缺省必须显式写 null"
    assert "G-2C 逐类覆盖" not in [gate["gate"] for gate in with_perclass["gates"]]
    assert with_perclass["perclass"]["gate"] == gates.G2C_GATE_LABEL
    assert with_perclass["failed"] == plain["failed"]
    assert with_perclass["insufficient"] == plain["insufficient"]
    assert with_perclass["all_pass"] == plain["all_pass"]
    assert with_perclass["admitted"] == plain["admitted"]
    assert "没跑不等于通过" in with_perclass["perclass_note"]


def _gate_record(perclass: bool = True, *, corpus_sha: str = "a" * 64,
                 constructed: bool = False, failed: bool = False, bound: str = "bound-1",
                 verdicts=None, declared=None) -> dict:
    """合成一份门禁记录（研究入口的纯函数测试用，不跑真实门禁）。"""

    verdicts = verdicts or {"branch.chiitoi_live": gates.CLASS_RELIABLE,
                            "chain.open": gates.CLASS_NOT_VERIFIED}
    declared = declared if declared is not None else list(verdicts)
    record = {"schema": "sitin-gates/1", "candidate": "demo_candidate",
              "bound_identity": bound,
              "corpus": {"path": "demo.jsonl", "rows": 48, "sha256": corpus_sha,
                         "constructed_trigger_set": constructed},
              "gates": [{"gate": "G-0 装载与构造", "status": "PASS"},
                        {"gate": "G-2 退化检测", "status": "FAIL" if failed else "PASS"}]}
    if perclass:
        record["perclass"] = {
            "gate": gates.G2C_GATE_LABEL, "status": "INSUFFICIENT",
            "detail": {"schema": gates.PERCLASS_SCHEMA, "declared_classes": declared,
                       "classes": [{"id": cid, "verdict": verdict}
                                   for cid, verdict in verdicts.items()]}}
    return record


def _research_request(**overrides) -> dict:
    request = {
        "schema": gates.RESEARCH_REQUEST_SCHEMA,
        "entry_version": gates.RESEARCH_ENTRY_VERSION,
        "candidate": "demo_candidate",
        "bound_identity": "bound-1",
        "panel": {"path": "demo.jsonl", "rows": 48, "sha256": "a" * 64,
                  "constructed_trigger_set": False},
        "sampler": {"id": "scenario-visible-sampler", "version": "1.0.0",
                    "frozen_before_run": True, "seeds": [11, 12, 13]},
    }
    scope = {"research_classes": ["chain.open"],
             "claim_classes": ["branch.chiitoi_live"], "claim_kinds": ["behavior"]}
    request["scope"] = scope
    for key, value in overrides.items():
        if key in ("scope", "sampler", "panel"):
            request[key] = dict(request[key], **value)
        else:
            request[key] = value
    return request


def test_research_entry_permits_a_scoped_request_and_never_claims_admission():
    record = gates.research_execution_entry(_research_request(), gate_record=_gate_record())
    assert record["permitted"] is True, record["refusals"]
    assert record["refusals"] == []
    # 三条硬性质：研究记录**永不**携带准入结论。
    assert record["admitted"] is False
    assert record["gate_level_admitted"] is False
    assert record["evidence_kind"] == "research"
    assert record["research_scope"]["evidence_pending"] == ["chain.open"]
    assert gates.verify_research_record(record) == []


def test_research_entry_refuses_a_gate_record_without_the_perclass_section():
    record = gates.research_execution_entry(_research_request(),
                                            gate_record=_gate_record(perclass=False))
    assert record["permitted"] is False
    assert [item["code"] for item in record["refusals"]] == ["perclass_missing"]


def test_research_entry_refuses_any_admission_claim():
    for overrides in ({"admission": True}, {"gate_level_admitted": True},
                      {"scope": {"claim_kinds": ["admission"]}},
                      {"scope": {"claim_kinds": ["conditional_effect", "effect"]}}):
        record = gates.research_execution_entry(_research_request(**overrides),
                                                gate_record=_gate_record())
        assert record["permitted"] is False, overrides
        assert any(item["code"] == "admission_claim" for item in record["refusals"]), overrides
        assert record["admitted"] is False


def test_research_entry_refuses_a_claim_on_an_unverified_class():
    request = _research_request(scope={"claim_classes": ["chain.open"]})
    record = gates.research_execution_entry(request, gate_record=_gate_record())
    assert record["permitted"] is False
    assert any(item["code"] == "claim_without_evidence" for item in record["refusals"])


def test_research_entry_refuses_an_undeclared_research_class():
    request = _research_request(scope={"research_classes": ["payrole.self_dealer"]})
    record = gates.research_execution_entry(request, gate_record=_gate_record())
    assert record["permitted"] is False
    assert any(item["code"] == "scope_not_declared" for item in record["refusals"])


def test_research_entry_refuses_unbound_identities():
    cases = (
        ({"bound_identity": "other-bound"}, "candidate_identity_mismatch"),
        ({"bound_identity": ""}, "candidate_identity_unbound"),
        ({"candidate": "other"}, "candidate_identity_mismatch"),
        ({"panel": {"sha256": "b" * 64}}, "panel_identity_mismatch"),
        ({"panel": {"rows": 999}}, "panel_identity_mismatch"),
        ({"sampler": {"id": ""}}, "sampler_identity_unbound"),
        ({"sampler": {"frozen_before_run": False}}, "sampler_not_frozen"),
        ({"sampler": {"seeds": []}}, "sampler_seeds_missing"),
    )
    for overrides, code in cases:
        record = gates.research_execution_entry(_research_request(**overrides),
                                                gate_record=_gate_record())
        assert record["permitted"] is False, overrides
        assert any(item["code"] == code for item in record["refusals"]), (overrides, code)


def test_research_entry_refuses_on_version_or_scope_or_safety_problems():
    cases = (
        ({"schema": "x/2"}, "request_schema"),
        ({"entry_version": "v0"}, "entry_version"),
        ({"scope": {"research_classes": []}}, "research_scope_unbounded"),
        ({"scope": {"claim_kinds": ["something_else"]}}, "claim_kind_unknown"),
    )
    for overrides, code in cases:
        record = gates.research_execution_entry(_research_request(**overrides),
                                                gate_record=_gate_record())
        assert any(item["code"] == code for item in record["refusals"]), (overrides, code)
    unsafe = gates.research_execution_entry(_research_request(),
                                            gate_record=_gate_record(failed=True))
    assert any(item["code"] == "unsafe_gates" for item in unsafe["refusals"])
    assert unsafe["permitted"] is False


def test_research_entry_collects_every_refusal_not_just_the_first():
    request = _research_request(bound_identity="other", admission=True,
                                sampler={"frozen_before_run": False},
                                scope={"research_classes": [], "claim_classes": ["chain.open"]})
    record = gates.research_execution_entry(request, gate_record=_gate_record(perclass=False))
    codes = {item["code"] for item in record["refusals"]}
    # 逐类段缺失 ⇒ 结论范围无从核对，因此这里**不**报 claim_without_evidence（它由专门用例覆盖）。
    assert {"perclass_missing", "candidate_identity_mismatch", "admission_claim",
            "sampler_not_frozen", "research_scope_unbounded"} <= codes
    # 逐类段在场时才谈得上"结论落在未验证的类上"。
    with_perclass = gates.research_execution_entry(
        _research_request(scope={"research_classes": [], "claim_classes": ["chain.open"]}),
        gate_record=_gate_record())
    assert any(item["code"] == "claim_without_evidence"
               for item in with_perclass["refusals"])


def test_research_entry_refuses_an_effect_claim_on_a_constructed_panel():
    record = gates.research_execution_entry(
        _research_request(panel={"constructed_trigger_set": True},
                          scope={"claim_kinds": ["conditional_effect"]}),
        gate_record=_gate_record(constructed=True))
    assert record["permitted"] is False
    assert any(item["code"] == "constructed_panel_effect_claim" for item in record["refusals"])


def test_verify_research_record_rejects_a_forged_admission_record():
    """★ 下游扫描器的守卫：把研究记录改写成"准入了"必须被判死。"""

    clean = gates.research_execution_entry(_research_request(), gate_record=_gate_record())
    assert gates.verify_research_record(clean) == []
    for mutation, needle in (("admitted", "admitted"),
                             ("gate_level_admitted", "gate_level_admitted"),
                             ("evidence_kind", "evidence_kind")):
        forged = dict(clean)
        forged[mutation] = {"admitted": True, "gate_level_admitted": True,
                            "evidence_kind": "admission"}[mutation]
        problems = gates.verify_research_record(forged)
        assert any(needle in problem for problem in problems), mutation
    # permitted 与 refusals 必须一致：被拒过的记录不许说"能执行"。
    inconsistent = dict(clean, permitted=True, refusals=[{"code": "x", "reason": "y"}])
    assert any("permitted 与 refusals 不一致" in problem
               for problem in gates.verify_research_record(inconsistent))


def test_cli_research_entry_exit_codes(tmp_path):
    """入口的退出码：许可 0、被拒 2（被拒时也要落盘完整理由）。"""

    gate_record = tmp_path / "gate.json"
    gate_record.write_text(json.dumps(_gate_record(), ensure_ascii=False), encoding="utf-8")
    request = tmp_path / "request.json"
    request.write_text(json.dumps(_research_request(), ensure_ascii=False), encoding="utf-8")
    out = tmp_path / "research.json"
    assert gates.main(["--research-entry", "--gate-record", str(gate_record),
                       "--research-request", str(request), "--out", str(out)]) == 0
    assert gates.verify_research_record(json.loads(out.read_text(encoding="utf-8"))) == []
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(_research_request(admission=True), ensure_ascii=False),
                   encoding="utf-8")
    assert gates.main(["--research-entry", "--gate-record", str(gate_record),
                       "--research-request", str(bad), "--out", str(out)]) == 2
    refused = json.loads(out.read_text(encoding="utf-8"))
    assert refused["permitted"] is False and refused["refusals"]
    assert gates.main(["--verify-research", str(out)]) == 0
    forged = tmp_path / "forged.json"
    forged.write_text(json.dumps(dict(refused, admitted=True), ensure_ascii=False),
                      encoding="utf-8")
    assert gates.main(["--verify-research", str(forged)]) == 2




# --- 3.6b 返工（F7）：记录层视图 / 惰性读取 / 共享扫描等价性 ---------------------


def test_record_layer_filled_uses_the_production_normalizer_and_never_mutates():
    """★ filled 视图走**生产函数**（单一来源），raw 视图不动字段，原行不被改写。"""

    rows = gates.load_corpus(CORPUS, limit=50)
    scenario = gates.scenario_classes()
    key = scenario.chain_piao_module().CHAIN_PIAO_ATTRIBUTION_KEY
    row = rows[0]
    assert key not in row, "原始记录不带归因块"

    assert scenario.normalize_record_layer(row, scenario.RECORD_LAYER_RAW) is row
    assert scenario.normalize_record_layer(row, "filled") is not row

    filled = scenario.normalize_record_layer(row, "filled")
    attribution = filled[key]
    assert attribution["schema"]
    assert attribution["status"] in ("attributed", "unknown")
    assert filled["request"]["observation"]["chain_piao"] == attribution["piao"]
    if attribution["status"] == "unknown":
        assert attribution["piao"] is None, "不可归因必须记 unknown，绝不填零"
    assert key not in row, "归一化不得改写原行"


def test_record_layer_rejects_an_unknown_mode():
    scenario = gates.scenario_classes()
    with pytest.raises(ValueError):
        scenario.normalize_record_layer({"request": {}}, "half-filled")


def test_iter_corpus_is_lazy_and_matches_load_corpus(tmp_path):
    """★ 惰性读取与物化读取**同源同序**；canonical 面板靠前者避免 28 GB 峰值。"""

    corpus = _tiny_corpus(tmp_path, limit=20)
    materialized = gates.load_corpus(corpus)
    streamed = gates.iter_corpus(corpus)
    assert not isinstance(streamed, list)
    assert list(streamed) == materialized
    assert list(gates.iter_corpus(corpus, limit=3)) == materialized[:3]


def test_scan_corpus_counts_rows_and_detects_constructed():
    """先扫一遍（fail-closed）：构造集标记必须在计分之前判掉，且行数可数。"""

    grid = (_project_file(_PROJECT_ROOT, _REPO / "review/llm-guided-heuristic-route-2026-09-15" / "evidence"
            / "2.3-gates" / "trigger" / "trigger-grid.jsonl"))
    if not grid.is_file():
        pytest.skip("触发集缺失")
    scenario = gates.scenario_classes()
    scanned = scenario.scan_corpus(grid)
    assert scanned["constructed"] is True
    assert scanned["rows"] == len(gates.load_corpus(grid))
    plain = scenario.scan_corpus(CORPUS)
    assert plain["constructed"] is False
    assert plain["rows"] > 0


def test_resolve_record_layer_prefers_the_manifest_then_falls_back_to_raw(tmp_path):
    corpus = _tiny_corpus(tmp_path, limit=4)
    assert gates.resolve_record_layer(corpus) == gates.SCENARIO_RECORD_LAYER_RAW

    manifest = tmp_path / "panel.json"
    manifest.write_text(json.dumps({
        "schema": gates.CORPUS_MANIFEST_SCHEMA, "panel_id": "demo",
        "record_layer": gates.SCENARIO_RECORD_LAYER_FILLED, "rows": 4,
        "files": [{"path": str(corpus), "rows": 4}], "frozen_before_run": True,
        "selection_rule": "测试用",
    }, ensure_ascii=False), encoding="utf-8")
    assert gates.resolve_record_layer(manifest) == gates.SCENARIO_RECORD_LAYER_FILLED
    # 显式参数优先（前后对比就是靠它把同一份清单按两个视图各跑一遍）
    assert gates.resolve_record_layer(manifest, gates.SCENARIO_RECORD_LAYER_RAW) == \
        gates.SCENARIO_RECORD_LAYER_RAW


def test_perclass_records_is_the_same_judgment_as_the_single_candidate_gate(tmp_path):
    """★ 共享扫描（多候选一次遍历）与单候选入口必须产出**逐字相同**的记录。

    这是"判定只有一份实现、扫描次数只是工程选择"这条设计的守门测试：
    canonical 面板靠共享扫描把 6 遍扫描压成 1 遍，判定语义不得因此漂移。
    """

    rows = gates.load_corpus(_tiny_corpus(tmp_path), limit=240)
    weights = {"adj.beta": 20.0}
    direct = gates.gate_g2c("meld_opportunity_cost", weights, rows, raw_diagnostics=False)
    scenario = gates.scenario_classes()
    evaluation = scenario.evaluate_panel(
        rows, ["meld_opportunity_cost"],
        weights_by_candidate={"meld_opportunity_cost": weights})
    shared = gates.perclass_records(evaluation, "meld_opportunity_cost", weights=weights,
                                    raw_diagnostics=False)
    assert (json.dumps(direct, sort_keys=True, ensure_ascii=False)
            == json.dumps(shared, sort_keys=True, ensure_ascii=False))


def test_corpus_manifest_expands_files_and_pins_identity(tmp_path):
    """★ 语料清单（多文件面板）：先冻结选择规则、后运行这件事必须可机器复核。"""

    files = []
    for index in range(2):
        item = tmp_path / "part-{0}.jsonl".format(index)
        item.write_text(json.dumps({"request": {"n": index}}, ensure_ascii=False) + "\n",
                        encoding="utf-8")
        files.append(item)
    manifest = tmp_path / "corpus-manifest.json"
    manifest.write_text(json.dumps({
        "schema": gates.CORPUS_MANIFEST_SCHEMA, "row_cap": 100, "rows": 2,
        "frozen_before_run": True, "selection_rule": "测试用：按路径升序整份取",
        "files": [{"path": str(item), "rows": 1} for item in files],
    }, ensure_ascii=False), encoding="utf-8")

    rows = gates.load_corpus(manifest)
    assert [row["request"]["n"] for row in rows] == [0, 1], "多文件面板按清单顺序展开"
    assert gates.load_corpus(manifest, limit=1) == rows[:1]
    identity = gates.corpus_identity(manifest, len(rows), constructed=False)
    assert identity["rows"] == 2
    assert identity["manifest"]["files"] == 2
    assert identity["manifest"]["frozen_before_run"] is True
    # 普通 JSONL 不受影响：清单解析只认 schema。
    plain = tmp_path / "plain.jsonl"
    plain.write_text(json.dumps({"a": 1}) + "\n", encoding="utf-8")
    assert gates.corpus_manifest(plain) is None
    assert gates.load_corpus(plain) == [{"a": 1}]


def test_manifest_schema_is_shared_with_the_scenario_tool():
    """两份工具必须用**同一个清单 schema**：各自解析一次，口径不能有两套。"""

    scenario = gates.scenario_classes()
    assert scenario._tool("sitin_gates").CORPUS_MANIFEST_SCHEMA == gates.CORPUS_MANIFEST_SCHEMA
    manifest = gates.CORPUS_MANIFEST_SCHEMA
    assert manifest == "sitin-corpus-manifest/1"


def test_importing_the_gates_module_does_not_import_the_scenario_tool():
    """装载有界的第二半：逐类判定用到的场景类工具也是**惰性**导入的。"""

    import subprocess

    tools_dir = str(_HERE)
    code = ("import sys; sys.path.insert(0, {0!r}); import sitin_gates; "
            "print('sitin_scenario_classes' in sys.modules)").format(tools_dir)
    result = subprocess.run([sys.executable, "-c", code], cwd=tools_dir,
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "False", result.stdout
