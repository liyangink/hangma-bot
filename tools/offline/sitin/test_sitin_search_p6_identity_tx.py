# -*- coding: utf-8 -*-
"""P6 专属测试（R7 修复批次）：S2 恢复身份强制核验 + S3 副作用事务检查点。

复审条目：R6-IMPLEMENTATION-REVIEW-2026-09-17 §3 S2（P1）/ §3 S3（P1）。
本文件只覆盖 P6 工作包；不改既有测试文件，也不改其他模块。

S2 覆盖（每个推进/恢复入口自行重算冻结清单，调用方 identity 只作额外期望）：
  - 开轮冻结可重算清单（十面：规则/投影/执行器/模拟器/统计器/基线/对手/
    分析配置/面板/根用途），传递依赖含 hand_analysis / _standard；
  - 逐面注入依赖改动（方法体 / 数学后端 / 分析上限 / 面板 / 目标合同）→
    新费用与新结果写入之前拒绝恢复；
  - 三种绕过形态（空 identity、只给 run_id、旧摘要配 {}）全部被拒；
  - 相同身份则复用已提交结果（不重跑、不重复计费）。

S3 覆盖（实例任务标识 + 恢复先对账 + 单推进者 + 账本互斥原子落盘）：
  ① H 完成 / M 未完时中断后恢复；② 结果写入与费用结算之间中断（两个方向）；
  ③ 账本写入中断（不产生半截账本）；④ 两个恢复者竞争同一运行目录；
  ⑤ 模型回复已存在但生成状态未提交。

全部离线（mock 生成 + 替身桌赛），不调真实 LLM、不跑真实桌赛、不消耗授权账目。
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
import hashlib
import json
import subprocess
import sys
import textwrap
import uuid
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))

import sitin_search as search  # noqa: E402
import sitin_natural_panel as natural  # noqa: E402

#: 批次 7 授权令牌 + 账户额度（替身 runtime：0 真实桌赛，账面照记）。
TOKEN = {"authorized": True, "batch": 7,
         "budgets": {"tokens_input": 100000, "tokens_output": 200000,
                     "tables_full": 256, "tables_partial": 64,
                     "prefix_generation": 64}}


class FakeDrive:
    """替身桌赛驱动（0 真实桌赛）；fail_on_call 在指定调用序号上抛错模拟中断。"""

    def __init__(self, fail_on_call=None):
        self.calls = []
        self.fail_on_call = fail_on_call

    def __call__(self, *, plan, policies_by_seat, versions_block, step_limit,
                 value_limits):
        self.calls.append(plan.table_id)
        if self.fail_on_call is not None and len(self.calls) >= self.fail_on_call:
            raise RuntimeError("P6 注入：桌赛中途中止（第 {0} 次桌执行）".format(
                len(self.calls)))
        seats = list(plan.seats())
        focal_idx = seats.index("focal") if "focal" in seats \
            else seats.index("natural:focal")
        is_candidate = str(getattr(policies_by_seat[focal_idx], "policy_id",
                                   "")).startswith("action_value")
        offset = plan.seed % 7 - 3
        scores = []
        for seat in range(4):
            if seat == focal_idx:
                scores.append(12 + offset if is_candidate else -10 + offset)
            else:
                scores.append(2 - seat + (offset if seat % 2 else -offset))
        return {"table_id": plan.table_id, "seed": int(plan.seed),
                "match_status": "complete", "wall_ms": 1.0,
                "scores_by_seat": scores, "result": {}}


@pytest.fixture
def fake_runtime(monkeypatch):
    monkeypatch.setattr(natural, "execute_natural_table", FakeDrive(), raising=True)


# ----------------------------------------------------------------- 工具


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _run(tmp_path, tag, **kwargs):
    out = Path(tmp_path) / ("p6-" + tag + "-" + uuid.uuid4().hex[:6])
    return out, search.run_av_evolution(out, **kwargs)


def _freeze(tmp_path, tag, stop_after, **kwargs):
    out, result = _run(tmp_path, tag, generation_mode="mock",
                       authorization=TOKEN, stop_after=stop_after, **kwargs)
    assert result.get("stopped_after") == stop_after, result
    return out, search.av_state_load(search.av_latest_state_path(out))


def _state_of(run_root):
    state_path = search.av_latest_state_path(Path(run_root))
    assert state_path is not None
    return state_path, search.av_state_load(state_path)


def _ledger_of(run_root):
    return search.ActionValueLedger.load(Path(run_root) / "av-ledger.json")


def _fault(*points):
    """构造故障注入钩子：**只在指定注入点**抛异常（模拟进程在检查点之间崩溃）。"""

    def hook(point, **_fields):
        if point in points:
            raise RuntimeError("P6 注入故障：{0}".format(point))

    return hook


# ============================================================ S2 · 冻结清单


def test_s2_start_freezes_recomputable_manifest(tmp_path, fake_runtime):
    """开轮即冻结可重算清单（十面齐全）且传递依赖覆盖规则来源。"""

    out, state = _freeze(tmp_path, "s2-manifest", "RESERVED")
    identity = state["identity"]
    manifest = identity["frozen_manifest"]
    assert manifest["schema"] == search.AV_FROZEN_MANIFEST_SCHEMA
    for surface in search.AV_FROZEN_MANIFEST_SURFACES:
        assert surface in manifest["surfaces"], surface
    assert identity["frozen_manifest_digest"] == search.av_frozen_manifest_digest(
        manifest)
    rules = manifest["surfaces"]["rules"]["modules"]
    assert "hangma_bot.hangma.hand_analysis" in rules
    assert "hangma_bot.hangma._standard" in rules
    # 入口自算：调用方给空期望不改变结论（身份核验不依赖调用方材料）。
    ok, reason, recomputed = search.av_verify_run_identity(state, expected={})
    assert ok and not reason, reason
    assert recomputed["surfaces"]["rules"]["digest"] == \
        manifest["surfaces"]["rules"]["digest"]


def _patch_dependency_change(monkeypatch, spec):
    """按面注入依赖改动：文件内容（后缀匹配）或分析配置值。"""

    if spec.get("analysis_limits"):
        real = search.av_analysis_config

        def bumped():
            config = dict(real())
            limits = dict(config["value_analysis_limits"])
            limits["max_expansions"] = int(limits["max_expansions"]) + 1
            config["value_analysis_limits"] = limits
            return config

        monkeypatch.setattr(search, "av_analysis_config", bumped, raising=True)
        return
    suffix = spec["file_suffix"]
    real_reader = search.av_dependency_file_reader

    def reader(path):
        data = real_reader(path)
        if str(path).endswith(suffix):
            return data + b"\n# P6 injected dependency change\n"
        return data

    monkeypatch.setattr(search, "av_dependency_file_reader", reader, raising=True)


#: (用例名, 注入方式, 应命中的面)
S2_CHANGE_CASES = (
    ("method_body", {"file_suffix": "policy/action_value_policy.py"}, "projection"),
    ("math_backend", {"file_suffix": "hangma/hand_analysis.py"}, "rules"),
    ("math_backend_standard", {"file_suffix": "hangma/_standard.py"}, "rules"),
    ("analysis_cap", {"analysis_limits": True}, "analysis_config"),
    ("panel", {"file_suffix": "sitin_natural_panel.py"}, "panel"),
    ("target_contract", {"file_suffix": "contracts/group-dev-v1.json"}, "opponent"),
)


@pytest.mark.parametrize("label,spec,surface", S2_CHANGE_CASES,
                         ids=[case[0] for case in S2_CHANGE_CASES])
def test_s2_identity_change_refused_before_new_cost(tmp_path, monkeypatch,
                                                    fake_runtime, label, spec,
                                                    surface):
    """只改一个面即拒绝恢复，且拒绝发生在新费用与新结果写入之前。"""

    out, state = _freeze(tmp_path, "s2-" + label, "CONDITIONAL_EVALUATED")
    before = _ledger_of(out).account_summary()
    iter_dir = Path(state["iter_dir"])
    _patch_dependency_change(monkeypatch, spec)
    refused = search.run_av_machine_resume(out, run_id=state["run_id"],
                                           authorization=TOKEN)
    assert refused.get("refused"), "身份已变更但仍被放行恢复"
    assert surface in refused["refused"], refused["refused"]
    assert _ledger_of(out).account_summary() == before, "拒绝前已产生新费用"
    assert not list(iter_dir.glob("natural-*")), "拒绝前已写入新结果"
    _, after_state = _state_of(out)
    assert after_state["status"] == "CONDITIONAL_EVALUATED"


def test_s2_bypass_forms_all_refused(tmp_path, monkeypatch, fake_runtime):
    """空 identity / 只给 run_id / 旧摘要配 {} 三种绕过形态全部被拒。"""

    out, state = _freeze(tmp_path, "s2-bypass", "CONDITIONAL_EVALUATED")
    old_identity = dict(state["identity"])
    _patch_dependency_change(monkeypatch,
                             {"file_suffix": "policy/action_value_policy.py"})
    before = _ledger_of(out).account_summary()
    forms = {
        "空 identity": {},
        "只给 run_id": None,
        "旧摘要配 {}": {"deps_digest": old_identity.get("deps_digest")},
        "旧清单摘要": {"frozen_manifest_digest":
                       old_identity["frozen_manifest_digest"]},
    }
    for label, identity in forms.items():
        kwargs = {} if identity is None else {"identity": identity}
        refused = search.run_av_machine_resume(out, run_id=state["run_id"],
                                               authorization=TOKEN, **kwargs)
        assert refused.get("refused"), "绕过形态未被拒：{0}".format(label)
        assert "身份" in refused["refused"], refused["refused"]
    assert _ledger_of(out).account_summary() == before
    assert not list(Path(state["iter_dir"]).glob("natural-*"))


def test_s2_same_identity_reuses_committed_results(tmp_path, fake_runtime):
    """相同身份：复用已提交结果，不重跑、不重复计费。"""

    out, state = _freeze(tmp_path, "s2-reuse", "CONDITIONAL_EVALUATED")
    eval_path = Path(state["conditional"]["evaluation_path"])
    eval_sha = _sha(eval_path)
    ok, reason, _manifest = search.av_verify_run_identity(state)
    assert ok and not reason
    resumed = search.run_av_machine_resume(out, run_id=state["run_id"],
                                           authorization=TOKEN)
    assert resumed.get("terminal") == "ITERATION_COMPLETE"
    assert _sha(eval_path) == eval_sha, "条件结果被重跑覆盖"
    ledger = _ledger_of(out)
    assert ledger.spent("prefix_generation") == 1.0, "条件前缀被重复计费"
    assert ledger.spent("tables_full") == 8.0  # 1 根 × 1 座 × 2 臂 × 2 桌 × H/M


# ============================================================ S3 · 实例台账


def test_s3_instance_registry_keyed_by_root_seat_arm_schedule(tmp_path,
                                                             fake_runtime):
    """实例任务标识 = **完整评价身份**（候选 × 情景 × 种子 × 根 × 座位 × 臂 × 赛程）。

    R8/S1：键从「根 × 座位 × 臂 × 赛程」扩展为完整评价身份（复审 A3）——缺候选与
    情景/种子的旧键会让两个真实实例共用一条记录。逐实例记开始/完成/费用/摘要。
    """

    out, result = _run(tmp_path, "s3-reg", generation_mode="mock",
                       authorization=TOKEN)
    assert result.get("terminal") == "ITERATION_COMPLETE"
    registry = search.av_instances_load(out)
    assert registry["schema"] == search.AV_INSTANCE_SCHEMA
    rows = registry["instances"]
    assert len(rows) == 4, sorted(rows)  # 1 根 × 1 座 × 2 臂 × H/M
    mixes, arms = set(), set()
    for key, row in rows.items():
        assert key == search.av_instance_identity_key(
            candidate_id=row["candidate_id"], opponent_mix=row["opponent_mix"],
            panel_seed=row["panel_seed"], source_root_id=row["source_root_id"],
            root_index=row.get("root_index"), root_seed=row.get("root_seed"),
            seat=row["seat"], arm=row["arm"], schedule=row["schedule"])
        # 身份维度逐项在案（键可复算，不被别的候选/情景顶掉）。
        state = search.av_state_load(search.av_latest_state_path(out))
        assert row["candidate_id"] == state["identity"]["candidate_id"]
        assert row["cache_key"] == (
            key if row["arm"] == "candidate" else row["cache_key"])
        assert row["evaluation_scope"] == (
            "shared_baseline_cache" if row["arm"] == "baseline"
            else "candidate_evaluation")
        assert row["status"] == "completed"
        assert row["cost"]["tables"] == 2
        assert row["result_digest"] and len(row["result_digest"]) == 64
        assert row["started_at_utc"] and row["completed_at_utc"]
        mixes.add(row["opponent_mix"])
        arms.add(row["arm"])
    assert mixes == {"H", "M"} and arms == {"baseline", "candidate"}
    # 账本不留卡住的预留。
    ledger = _ledger_of(out)
    assert all(item["status"] == "settled" for item in ledger.reservations)


# ---------------------------------------------------------- ① H 完成 / M 未完


def test_s3_interrupt_after_h_before_m_resume_no_rerun(tmp_path, monkeypatch):
    """①：H 已完成、M 中断（在途预留未结算）→ 恢复复用 H、只补 M。"""

    # 硬中断注入点：H 已完整跑完并落检查点；M 刚预留（在途）就崩。
    monkeypatch.setattr(search, "av_fault_point",
                        _fault("natural:M:after_reserve"), raising=True)
    out = Path(tmp_path) / ("p6-s3-int1-" + uuid.uuid4().hex[:6])
    with pytest.raises(RuntimeError):
        search.run_av_evolution(out, generation_mode="mock", authorization=TOKEN)
    _state_path, state = _state_of(out)
    assert state["status"] == "CONDITIONAL_EVALUATED", state["status"]
    iter_dir = Path(state["iter_dir"])
    h_panel = iter_dir / "natural-H" / "panel.json"
    assert h_panel.is_file()
    h_sha = _sha(h_panel)
    mid = _ledger_of(out)
    m_rows = [item for item in mid.reservations if ":M:" in item["step_id"]]
    assert m_rows and m_rows[-1]["status"] == "reserved", "中断态不是在途预留"
    # 恢复（解除注入）：H 复用、M 补跑。
    monkeypatch.setattr(search, "av_fault_point", lambda *a, **k: None, raising=True)
    resumed = search.run_av_machine_resume(out, run_id=state["run_id"],
                                           authorization=TOKEN)
    assert resumed.get("terminal") == "ITERATION_COMPLETE", resumed.get("refused")
    assert _sha(h_panel) == h_sha, "H 面板被重跑（结果被覆盖）"
    ledger = _ledger_of(out)
    h_rows = [item for item in ledger.reservations if ":H:" in item["step_id"]]
    assert len(h_rows) == 1, "H 被重复预留/结算"
    assert all(item["status"] == "settled" for item in ledger.reservations), \
        "账本仍有卡住的在途预留"
    m_after = [item for item in ledger.reservations if ":M:" in item["step_id"]]
    assert len(m_after) == 2, "中断尝试的成本未保留或未产生新尝试"
    assert all(item["status"] == "settled" for item in m_after)
    # 每个实例恰好一条完成记录：H 与 M 各 2 个实例，无重复桌赛实例。
    registry = search.av_instances_load(out)["instances"]
    assert len(registry) == 4
    assert all(row["status"] == "completed" for row in registry.values())
    assert {row["opponent_mix"] for row in registry.values()} == {"H", "M"}
    assert sum(row["cost"]["tables"] for row in registry.values()) == 8
    # 统计只吃一次：样本数 = 根 × 座位 × 情景，不因重试翻倍。
    _, final = _state_of(out)
    assert final["summary"]["n_samples"] == 2


# ------------------------------------------------- ② 结果写入与费用结算之间


def test_s3_result_written_before_settle_reconciled(tmp_path, monkeypatch,
                                                    fake_runtime):
    """②（结果已写、费用未结算）：恢复按结果里的执行数结算并复用结果。"""

    out, state = _freeze(tmp_path, "s3-r1", "CONDITIONAL_EVALUATED")
    monkeypatch.setattr(search, "av_fault_point",
                        _fault("natural:H:after_result_before_settle"),
                        raising=True)
    with pytest.raises(RuntimeError):
        search.run_av_machine_resume(out, run_id=state["run_id"],
                                     authorization=TOKEN)
    monkeypatch.setattr(search, "av_fault_point", lambda *a, **k: None,
                        raising=True)
    iter_dir = Path(state["iter_dir"])
    h_panel = iter_dir / "natural-H" / "panel.json"
    assert h_panel.is_file(), "故障点未落在结果落盘之后"
    h_sha = _sha(h_panel)
    h_table_ids = [row["table_ids"] for row in
                   json.loads(h_panel.read_text(encoding="utf-8"))["samples"]]
    mid = _ledger_of(out)
    h_rows = [item for item in mid.reservations if ":H:" in item["step_id"]]
    assert h_rows and h_rows[-1]["status"] == "reserved", "费用已结算，无法覆盖本窗口"
    # 恢复：按结果记录的执行数结算 H（不重跑），再补 M。
    resumed = search.run_av_machine_resume(out, run_id=state["run_id"],
                                           authorization=TOKEN)
    assert resumed.get("terminal") == "ITERATION_COMPLETE", resumed.get("refused")
    assert _sha(h_panel) == h_sha, "H 面板被重跑"
    assert json.loads(h_panel.read_text(encoding="utf-8"))["samples"][0][
        "table_ids"] == h_table_ids[0]
    ledger = _ledger_of(out)
    h_after = [item for item in ledger.reservations if ":H:" in item["step_id"]]
    assert len(h_after) == 1 and h_after[0]["status"] == "settled"
    assert h_after[0]["charged"] == 4.0, "未按结果记录的执行数结算"
    assert all(item["status"] == "settled" for item in ledger.reservations)


def test_s3_cost_settled_but_result_missing_retried(tmp_path, monkeypatch,
                                                    fake_runtime):
    """②（费用已结算、结果未落盘）：失败成本保留，新尝试补齐结果，不丢结果。"""

    out, state = _freeze(tmp_path, "s3-r2", "CONDITIONAL_EVALUATED")
    monkeypatch.setattr(search, "av_fault_point",
                        _fault("natural:H:after_settle_before_completion"),
                        raising=True)
    with pytest.raises(RuntimeError):
        search.run_av_machine_resume(out, run_id=state["run_id"],
                                     authorization=TOKEN)
    monkeypatch.setattr(search, "av_fault_point", lambda *a, **k: None,
                        raising=True)
    iter_dir = Path(state["iter_dir"])
    h_panel = iter_dir / "natural-H" / "panel.json"
    h_summary = json.loads(h_panel.read_text(encoding="utf-8"))
    h_panel.unlink()  # 模拟"费用已结算、结果文件未落盘"的另一半窗口
    mid = _ledger_of(out)
    h_rows = [item for item in mid.reservations if ":H:" in item["step_id"]]
    assert h_rows and h_rows[-1]["status"] == "settled"
    charged_before = mid.spent("tables_full")
    resumed = search.run_av_machine_resume(out, run_id=state["run_id"],
                                           authorization=TOKEN)
    assert resumed.get("terminal") == "ITERATION_COMPLETE", resumed.get("refused")
    ledger = _ledger_of(out)
    h_after = [item for item in ledger.reservations if ":H:" in item["step_id"]]
    assert len(h_after) == 2, "失败成本未保留或未产生新尝试"
    assert all(item["status"] == "settled" for item in h_after)
    assert ledger.spent("tables_full") == charged_before + 8.0
    assert h_panel.is_file(), "结果丢失未补齐"
    registry = search.av_instances_load(out)["instances"]
    assert len(registry) == 4
    assert all(row["status"] == "completed" for row in registry.values())
    assert h_summary["identity"]["panel_seed"] == json.loads(
        h_panel.read_text(encoding="utf-8"))["identity"]["panel_seed"]


# ------------------------------------------------------------- ③ 账本写入中断


def test_s3_ledger_write_interrupted_no_half_ledger(tmp_path, monkeypatch):
    """③：账本写入中断不产生半截账本；主文件仍是最后一份完整账。"""

    path = tmp_path / "av-ledger.json"
    ledger = search.ActionValueLedger(path,
                                      authorized_budgets={"tables_full": 10.0})
    ledger.reserve(step_id="first", account="tables_full", amount=2.0)
    good_bytes = path.read_bytes()
    real_replace = search.os.replace

    def failing_replace(src, dst, *args, **kwargs):
        if str(dst) == str(path):
            raise OSError("P6 注入：账本落盘中断")
        return real_replace(src, dst, *args, **kwargs)

    monkeypatch.setattr(search.os, "replace", failing_replace)
    with pytest.raises(OSError):
        ledger.reserve(step_id="second", account="tables_full", amount=3.0)
    assert path.read_bytes() == good_bytes, "主账本被写坏/写半截"
    reloaded = search.ActionValueLedger.load(path)
    assert [item["step_id"] for item in reloaded.reservations] == ["first"]
    assert reloaded.spent("tables_full") == 2.0
    # 解除故障：同一笔预留可重做且只计一次。
    monkeypatch.setattr(search.os, "replace", real_replace)
    ledger.reserve(step_id="second", account="tables_full", amount=3.0)
    final = search.ActionValueLedger.load(path)
    assert final.spent("tables_full") == 5.0
    assert len([item for item in final.reservations
                if item["step_id"] == "second"]) == 1


def test_s3_ledger_read_modify_write_mutex_across_processes(tmp_path):
    """③/④：多进程并发记账——读改写互斥 + 原子落盘，无丢失更新。"""

    path = tmp_path / "av-ledger.json"
    template = textwrap.dedent("""
        import sys
        sys.path.insert(0, {tools!r})
        import sitin_search as search
        ledger = search.ActionValueLedger({path!r}, authorized_budgets={{"tokens_input": 100000.0}})
        for index in range(5):
            ledger.reserve(step_id="p{proc}-{{}}".format(index),
                           account="tokens_input", amount=1.0)
        """)
    procs = [subprocess.Popen(
        [sys.executable, "-c", template.format(tools=str(_HERE), path=str(path),
                                               proc=no)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        for no in range(4)]
    for proc in procs:
        _out, err = proc.communicate(timeout=120)
        assert proc.returncode == 0, err.decode("utf-8", "replace")[-800:]
    ledger = search.ActionValueLedger.load(path)
    assert len(ledger.reservations) == 20, "并发记账丢失更新（读改写未互斥）"
    assert ledger.spent("tokens_input") == 20.0


def test_s3_settled_task_cannot_be_reserved_again(tmp_path):
    """③：已结算任务不得原地再次预留；恢复须走 supersede 显式让位。"""

    path = tmp_path / "av.json"
    ledger = search.ActionValueLedger(path,
                                      authorized_budgets={"tables_full": 20.0})
    reservation = ledger.reserve(step_id="natural:abc:H:1",
                                 account="tables_full", amount=4.0)
    ledger.settle(reservation, actual=4.0)
    with pytest.raises(search.TaskAlreadySettled):
        ledger.reserve(step_id="natural:abc:H:1", account="tables_full", amount=4.0)
    assert ledger.spent("tables_full") == 4.0
    superseded = ledger.supersede(step_id="natural:abc:H:1", account="tables_full",
                                  reason="恢复对账：结果缺失，让位给新尝试")
    assert superseded["superseded"] is True
    assert ledger.spent("tables_full") == 4.0  # 失败成本保留
    again = ledger.reserve(step_id="natural:abc:H:1", account="tables_full", amount=4.0)
    ledger.settle(again, actual=4.0)
    reloaded = search.ActionValueLedger.load(path)
    assert reloaded.spent("tables_full") == 8.0
    assert len(reloaded.reservations) == 2


def test_s3_confirm_second_call_refused_not_traceback(tmp_path):
    """③：确认入口重复调用不得双计——返回可读拒绝而不是崩栈。"""

    archive_mod = search.av_archive()
    roots = [{"root_id": "np-H-x-r01", "opponent_mix": "H"},
             {"root_id": "np-M-x-r01", "opponent_mix": "M"}]
    epoch = archive_mod.build_channel_epoch("normal", roots)
    archive_path = tmp_path / "archive.json"
    archive_path.write_text(json.dumps(
        {"schema": "sitin-archive/1", "entries": {}, "slots": {}},
        ensure_ascii=False), encoding="utf-8")
    epoch_path = tmp_path / "epoch.json"
    epoch_path.write_text(json.dumps(epoch, ensure_ascii=False), encoding="utf-8")
    out = tmp_path / "confirm-out"
    authorization = {"authorized": True, "confirm_budget": 8.0}
    first = search.run_av_confirm(out, archive_path, epoch_path,
                                  confirm_authorization=authorization)
    assert first["ok"] is True
    second = search.run_av_confirm(out, archive_path, epoch_path,
                                   confirm_authorization=authorization)
    assert second["ok"] is False and "已结算" in second["refused"]
    ledger = search.ActionValueLedger.load(out / "av-ledger.json")
    confirm_rows = [item for item in ledger.reservations
                    if item["account"] == "confirm_reserved"]
    assert len(confirm_rows) == 1, "确认账被重复预留"


# ------------------------------------------------------- ④ 单推进者（竞争）


_HOLD_LOCK = textwrap.dedent("""
    import fcntl, pathlib, sys, time
    lock = pathlib.Path(sys.argv[1])
    lock.parent.mkdir(parents=True, exist_ok=True)
    handle = lock.open("a+")
    fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
    pathlib.Path(str(lock) + ".held").write_text("1")
    time.sleep(30)
    """)


def test_s3_two_advancers_single_owner(tmp_path, fake_runtime):
    """④：两个恢复者竞争同一运行目录 → 只有一个推进者，另一个被拒。"""

    out, state = _freeze(tmp_path, "s3-race", "GENERATED")
    lock_path = Path(out) / "advance.lock"
    holder = subprocess.Popen([sys.executable, "-c", _HOLD_LOCK, str(lock_path)],
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        held = Path(str(lock_path) + ".held")
        for _ in range(200):
            if held.exists():
                break
            holder.poll()
            assert holder.returncode is None, holder.stderr.read().decode()[-400:]
            import time
            time.sleep(0.05)
        assert held.exists(), "外部推进者未取得运行目录锁"
        before = _ledger_of(out).account_summary()
        refused = search.run_av_machine_resume(out, run_id=state["run_id"],
                                               authorization=TOKEN)
        assert refused.get("refused"), "第二个推进者被放行"
        assert "推进者" in refused["refused"], refused["refused"]
        assert _ledger_of(out).account_summary() == before, "被拒者仍产生费用"
        _, mid = _state_of(out)
        assert mid["status"] == "GENERATED"
    finally:
        holder.kill()
        holder.wait(timeout=30)
    done = search.run_av_machine_resume(out, run_id=state["run_id"],
                                        authorization=TOKEN)
    assert done.get("terminal") == "ITERATION_COMPLETE", done.get("refused")


# ------------------------------------------- ⑤ 回复已存在但生成状态未提交


def test_s3_reply_present_generation_not_committed(tmp_path, monkeypatch,
                                                   fake_runtime):
    """⑤：回复已摄入、状态未提交 → 恢复只摄入一次、不重复计费、不重发提示词。"""

    out, first = _run(tmp_path, "s3-gen", generation_mode="delegate",
                      authorization=TOKEN)
    assert first.get("waiting_for_reply") is True
    _state_path, state = _state_of(out)
    envelope = Path(state["iter_dir"]) / "reply-envelope.json"
    from hangma_bot.policy.action_value_seeds import SEEDS
    import sitin_generate as generate

    seed = SEEDS["efficiency_seed"]
    fence = chr(96) * 3
    reply = ("{efficiency_seed 机制（P6 测试）}\n\n" + fence + "json\n"
             + json.dumps({key: seed.mechanism[key]
                           for key in generate.AV_MECHANISM_FIELDS},
                          ensure_ascii=False) + "\n" + fence + "\n\n"
             + fence + "python\n" + seed.source + fence + "\n")
    envelope.write_text(json.dumps({
        "schema": "sitin-generation-reply/1", "origin": "delegated_model_reply",
        "prompt_sha256": state["generation"]["prompt_sha256"],
        "reply": reply, "provider": "p6-test", "model": "fake-model",
        "captured_at_utc": "2026-09-17T00:00:00Z", "delegator": "p6-tests",
        "usage": {"input_tokens": 111, "output_tokens": 222}},
        ensure_ascii=False), encoding="utf-8")
    pending = Path(state["generation"]["pending_dir"]) / "prompt.txt"
    prompt_sha = _sha(pending)
    monkeypatch.setattr(search, "av_fault_point",
                        _fault("generate:after_ingest_before_state_save"),
                        raising=True)
    with pytest.raises(RuntimeError):
        search.run_av_machine_resume(out, run_id=state["run_id"],
                                     authorization=TOKEN)
    monkeypatch.setattr(search, "av_fault_point", lambda *a, **k: None,
                        raising=True)
    _, mid = _state_of(out)
    assert mid["status"] == "RESERVED"
    ledger_mid = _ledger_of(out)
    assert ledger_mid.spent("tokens_input") == 111.0
    candidate_py = Path(mid["iter_dir"]) / "generation" / "candidate.py"
    assert candidate_py.is_file(), "恢复前生成产物未落盘"
    candidate_sha = _sha(candidate_py)
    done = search.run_av_machine_resume(out, run_id=state["run_id"],
                                        authorization=TOKEN)
    assert done.get("terminal") == "ITERATION_COMPLETE", done.get("refused")
    assert _sha(pending) == prompt_sha, "恢复重发了提示词"
    assert _sha(candidate_py) == candidate_sha, "候选产物被重写"
    ledger = _ledger_of(out)
    assert ledger.spent("tokens_input") == 111.0, "生成 token 被重复计费"
    assert ledger.spent("tokens_output") == 222.0
    _, final = _state_of(out)
    statuses = [item["status"] for item in final["step_history"]]
    assert statuses.count("GENERATED") == 1, "生成步被记了两遍"
    assert final["generation"]["phase"] == "ingested"
    assert all(item["status"] == "settled" for item in ledger.reservations)
