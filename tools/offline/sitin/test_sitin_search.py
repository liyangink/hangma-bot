"""坐隐 3.4/3.5 搜索驱动自测：**预算与停止规则必须能被证明生效**。

只测“跑通了”是没有意义的。本文件的重心是四件容易写错的事：

  1. **先预留后执行**：不足时抛错并落盘，不静默扩容；失败与重试同样计费；
     释放预留必须给理由（否则预算去向无法核对）。
  2. **两账分开**：确认账在本轮结构性不可动用——搜索不足不得挪确认预算。
  3. **同面板才可比**：跨面板比较被拒绝；实跑根组与计划不一致要能被发现。
  4. **三种完成状态分开报**：工具完成 ≠ 发现候选 ≠ 通过发布门禁；
     “未分辨”如实标出，生成产物停在待注册状态并进缺口清单。

阶段工具当前正被同波次的另一包扩展（候选槽），因此阶段相关的断言只要求
“探针不抛异常、结论落在三态里、缺口不花预算”，不把对方还没落地的接口写死。
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
from typing import Any, Dict, List, Optional

import pytest

_HERE = Path(__file__).resolve().parent
_REPO = _PROJECT_ROOT
sys.path.insert(0, str(_project_file(_PROJECT_ROOT, _REPO / "src")))
sys.path.insert(0, str(_HERE))

spec = importlib.util.spec_from_file_location("sitin_search", _project_file(_PROJECT_ROOT, _HERE / "sitin_search.py"))
search = importlib.util.module_from_spec(spec)
sys.modules["sitin_search"] = search
assert spec.loader is not None
spec.loader.exec_module(search)

CORPUS = _project_file(_PROJECT_ROOT, _REPO / "datasets/derived/auto-match-2026-09-06/decisions.jsonl")
GATE_DIR = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/2.3-gates')


# --- 夹具 -------------------------------------------------------------------

def freeze_payload() -> Dict[str, Any]:
    return {
        "schema": search.FREEZE_SCHEMA,
        "frozen_at": "2026-09-15",
        "accounts": {
            "search": {"calls": 8, "output_tokens": 1000000, "tables": 384,
                       "wall_clock_sec": 21600},
            "confirm": {"calls": 0, "output_tokens": 100000000, "tables": 0,
                        "wall_clock_sec": 0},
        },
        "panel": {"roots": 16, "seats": 2, "baseline_id": "weighted_heuristic_v2",
                  "ruleset": "hangma-mvp-v10-public-counts", "seed_base": 2026092000,
                  "root_prefix": "searchA-"},
        "upgrade": {"slots": 2, "roots": 8, "seats": 2, "seed_base": 2026093000,
                    "root_prefix": "searchA-up-"},
        "stage": {"pairs": 4, "tables_per_run": 9, "arms": 2, "participants": 9},
        # 墙钟基准**必须声明**（fail-closed）：夹具给一个实测口径的值；
        # "缺声明"的情形由专门的回归覆盖（见 test_wall_basis_*）。
        "wall_estimate_sec_per_table": 8.0,
        "retry_reserve_tables": 24,
        "stop_rules": {
            "keep_fraction": 0.5,
            "exploration_slots": 1,
            "upgrade_slots": 2,
            "consecutive_failures": 3,
            "unresolved_rule": "|均值| <= 本面板 MDE 或 有效根组 < 2 时标未分辨",
            "on_budget_exhausted": "保存状态并停止，报告缺口；不静默扩容",
            "on_panel_mismatch": "拒绝跨面板比较",
            "rerun": "同一身份+同一面板已执行过即复用；重演须显式 --allow-rerun 并照常计费",
            "unknown_token_call_limit": 3,
        },
    }


@pytest.fixture()
def freeze(tmp_path: Path) -> "search.Freeze":
    path = tmp_path / "freeze.json"
    path.write_text(json.dumps(freeze_payload(), ensure_ascii=False, indent=2), encoding="utf-8")
    return search.Freeze.load(path)


@pytest.fixture()
def ctx(tmp_path: Path, freeze) -> "search.SearchContext":
    out = tmp_path / "run"
    out.mkdir()
    return search.SearchContext(
        out=out, freeze=freeze,
        ledger=search.SearchLedger.load(out / "ledger.json", freeze),
        archive=search.Archive.load(out / "archive.json", freeze),
        state=search.RunState.load(out / "state.json"),
        steps_path=out / "steps.jsonl")


def stats(*, mean: float, mde: float = 2.9, n_roots: int = 16, sd_root: float = 4.0,
          rankable: bool = True, status: Optional[str] = None) -> Dict[str, Any]:
    payload = {"n_roots": n_roots, "mean": mean, "sd_root": sd_root,
               "se_root": 1.0, "mde": mde, "rankable": rankable,
               "rankable_reason": None}
    if status:
        payload["status"] = status
    return payload


class FakeScheduler:
    """调度器替身：只写“调度器本该写出的产物”，不真跑桌赛。"""

    def __init__(self, *, spent_tables: int, results: Dict[str, Dict[str, Any]],
                 root_keys: Optional[List[str]] = None, returncode: int = 0,
                 write_elimination: bool = True) -> None:
        self.spent_tables = spent_tables
        self.results = results
        self.root_keys = root_keys
        self.returncode = returncode
        self.write_elimination = write_elimination
        self.commands: List[List[str]] = []

    def __call__(self, name: str, command, *, cwd, timeout_sec, dry_run: bool = False):
        rendered = [str(item) for item in command]
        self.commands.append(rendered)
        level_dir = Path(rendered[rendered.index("--out") + 1])
        level_dir.mkdir(parents=True, exist_ok=True)
        level = json.loads(rendered[rendered.index("--levels") + 1])[0]["name"]
        if self.write_elimination:
            (level_dir / "elimination.json").write_text(json.dumps({
                "ledger": {"spent_tables": self.spent_tables},
                "report": {"levels": [{"round": level, "results": self.results}]},
                "run_state": {}}, ensure_ascii=False), encoding="utf-8")
            roots = self.root_keys
            if roots is None:
                prefix = rendered[rendered.index("--root-prefix") + 1]
                roots = ["{0}L1-{1}".format(prefix, index) for index in range(16)]
            (level_dir / "run_state.json").write_text(json.dumps({
                "schema": "sitin-run-state/1",
                "levels": [{"round": level, "root_keys": roots}]}, ensure_ascii=False),
                encoding="utf-8")
        return search.ToolRun(name=name, command=tuple(rendered),
                              returncode=self.returncode, timed_out=False,
                              elapsed_sec=3.0, signals_sent=(), stdout="{}", stderr="")


def entry(key: str, identity: str) -> Dict[str, Any]:
    return {"key": key, "candidate": key, "weights": {}, "identity": identity,
            "admission": {"status": "admitted"}, "hypothesis": ""}


def panel_of(freeze, level: str = "L1") -> Dict[str, Any]:
    data = freeze.panel
    panel = search.plan_level(level=level, roots=int(data["roots"]), seats=int(data["seats"]),
                              seed_base=int(data["seed_base"]),
                              root_prefix=str(data["root_prefix"]))
    panel["panel_id"] = search.panel_identity(panel, baseline_id=str(data["baseline_id"]),
                                              ruleset=str(data["ruleset"]))
    panel["root_set_id"] = search._sibling("sitin_scheduler").root_set_id_of(panel["root_specs"])
    return panel


# --- 冻结预算：四维 + 停止规则必须齐全 ---------------------------------------

def test_freeze_requires_four_axes_and_stop_rules(tmp_path: Path):
    path = tmp_path / "freeze.json"
    payload = freeze_payload()
    del payload["accounts"]["search"]["wall_clock_sec"]
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ValueError, match="缺少维度"):
        search.Freeze.load(path)

    payload = freeze_payload()
    del payload["stop_rules"]["consecutive_failures"]
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ValueError, match="stop_rules"):
        search.Freeze.load(path)


# --- 台账：先记账后执行、失败同样计费、释放要理由 ----------------------------

def test_ledger_reserves_before_running_and_persists(tmp_path: Path, freeze):
    ledger = search.SearchLedger.load(tmp_path / "ledger.json", freeze)
    reservation = ledger.reserve(step_id="screen:L1", account=search.ACCOUNT_SEARCH,
                                 amounts={"tables": 192, "wall_clock_sec": 900},
                                 note="初筛")
    assert ledger.remaining("search")["tables"] == 384 - 192
    on_disk = json.loads((tmp_path / "ledger.json").read_text(encoding="utf-8"))
    assert on_disk["accounts"]["search"]["reserved"]["tables"] == 192, "预留必须落盘"
    ledger.settle(reservation, status="ok", actual={"tables": 128, "wall_clock_sec": 300})
    assert ledger.remaining("search")["tables"] == 384 - 128, "按实测结算，未用部分退回"


def test_ledger_stops_when_budget_short_and_saves_state(tmp_path: Path, freeze):
    ledger = search.SearchLedger.load(tmp_path / "ledger.json", freeze)
    with pytest.raises(search.BudgetExhausted, match="不静默扩容"):
        ledger.reserve(step_id="screen:L1", account="search", amounts={"tables": 900},
                       note="超过总额")
    assert (tmp_path / "ledger.json").is_file(), "预算不足时必须已保存状态"
    assert ledger.step_ids() == [], "不足时不得留下半条预留"


def test_failed_step_is_charged_in_full(tmp_path: Path, freeze):
    """失败与重试同样计费：没有实测值时按**预留额**全额计费。"""

    ledger = search.SearchLedger.load(tmp_path / "ledger.json", freeze)
    reservation = ledger.reserve(step_id="generate:t1", account="search",
                                 amounts={"calls": 1, "output_tokens": 32768},
                                 note="一次生成")
    ledger.settle(reservation, status="failed", note="调用失败")
    assert ledger.spent("search")["calls"] == 1
    assert ledger.spent("search")["output_tokens"] == 32768


def test_release_requires_reason_and_returns_budget(tmp_path: Path, freeze):
    ledger = search.SearchLedger.load(tmp_path / "ledger.json", freeze)
    reservation = ledger.reserve(step_id="stage:compare", account="search",
                                 amounts={"tables": 72}, note="阶段比较")
    with pytest.raises(ValueError, match="理由"):
        ledger.release(reservation, reason="  ")
    ledger.release(reservation, reason="探针判定阶段面板不可用：未执行")
    assert ledger.remaining("search")["tables"] == 384
    assert ledger.reservations[0]["release_reason"], "释放理由必须留在台账里"


def test_confirm_account_is_structurally_unavailable(tmp_path: Path, freeze):
    """不进入第四阶段独立确认：确认账**任何**预留都被拒绝。"""

    ledger = search.SearchLedger.load(tmp_path / "ledger.json", freeze)
    with pytest.raises(search.ConfirmAccountFrozen, match="确认账不可动用"):
        ledger.reserve(step_id="screen:L1", account="confirm", amounts={"tables": 1},
                       note="试图挪用确认预算")
    assert ledger.reserved("confirm")["tables"] == 0


def test_ledger_refuses_changed_freeze(tmp_path: Path, freeze):
    ledger = search.SearchLedger.load(tmp_path / "ledger.json", freeze)
    ledger.save()
    other = freeze_payload()
    other["accounts"]["search"]["tables"] = 768
    path = tmp_path / "other-freeze.json"
    path.write_text(json.dumps(other, ensure_ascii=False), encoding="utf-8")
    changed = search.Freeze.load(path)
    with pytest.raises(ValueError, match="冻结摘要与台账不一致"):
        search.SearchLedger.load(tmp_path / "ledger.json", changed)


def test_ledger_refuses_duplicate_step(tmp_path: Path, freeze):
    ledger = search.SearchLedger.load(tmp_path / "ledger.json", freeze)
    ledger.reserve(step_id="screen:L1", account="search", amounts={"tables": 1}, note="a")
    with pytest.raises(ValueError, match="已有预留记录"):
        ledger.reserve(step_id="screen:L1", account="search", amounts={"tables": 1}, note="b")


# --- 计划核算：先扣预留，再算能跑几个候选 ------------------------------------

def test_compute_plan_subtracts_reserves_before_sizing(freeze):
    plan = search.compute_plan(freeze, available=99)
    arithmetic = plan["arithmetic"]
    assert arithmetic["per_candidate_tables"] == 64          # 16 根 × 2 换座 × 2 臂
    assert arithmetic["upgrade_tables"] == 2 * 8 * 2 * 2     # 2 名额
    assert arithmetic["stage_tables"] == 4 * 9 * 2           # 4 对 × 9 桌 × 2 臂
    fixed = (arithmetic["upgrade_tables"] + arithmetic["stage_tables"]
             + arithmetic["retry_reserve_tables"])
    assert arithmetic["fixed_reserve_tables"] == fixed
    assert arithmetic["c_max_by_budget"] == (384 - fixed) // 64
    assert arithmetic["candidates_planned"] == arithmetic["c_max_by_budget"]


def test_compute_plan_never_exceeds_budget(freeze):
    plan = search.compute_plan(freeze, available=99)
    assert plan["arithmetic"]["total_planned_tables"] <= 384


# --- 面板与统计口径 ---------------------------------------------------------

def test_panel_identity_depends_on_boards_and_seats(freeze):
    base = panel_of(freeze)
    same = panel_of(freeze)
    assert base["panel_id"] == same["panel_id"], "同参数必须同面板身份"
    other = search.plan_level(level="L1", roots=16, seats=1, seed_base=int(freeze.panel["seed_base"]),
                              root_prefix=str(freeze.panel["root_prefix"]))
    assert search.panel_identity(other, baseline_id="weighted_heuristic_v2",
                                 ruleset="r") != base["panel_id"], "换座数不同即不同面板"


def test_check_panel_alignment_rejects_cross_panel():
    problems = search.check_panel_alignment(
        [{"panel_id": "panel-a"}, {"panel_id": "panel-b"}], level="L1")
    assert problems and "面板不一致" in problems[0]
    assert search.check_panel_alignment([{"panel_id": "panel-a"}], level="L1") == []
    assert search.check_panel_alignment([{"panel_id": None}], level="L1")


def test_plan_level_matches_scheduler_root_formula():
    panel = search.plan_level(level="L1", roots=3, seats=2, seed_base=100, root_prefix="x-")
    assert [item["seed"] for item in panel["root_specs"]] == [100, 101, 102]
    assert [item["scenario_id"] for item in panel["root_specs"]] == ["x-L1-0", "x-L1-1", "x-L1-2"]


def test_describe_statistics_labels_unresolved_and_unrankable():
    assert search.describe_statistics(stats(mean=0.5))["state"] == "unresolved"
    assert search.describe_statistics(stats(mean=-9.0))["state"] == "resolved_negative"
    assert search.describe_statistics(stats(mean=9.0))["state"] == "resolved_positive"
    assert search.describe_statistics(stats(mean=None, rankable=False,
                                            n_roots=0))["state"] == "unrankable"
    single = search.describe_statistics(stats(mean=50.0, n_roots=1))
    assert single["state"] == "unrankable", "单根不构成点估计"


# --- 准入核验：可区分的失败理由 ---------------------------------------------

@pytest.mark.skipif(not CORPUS.is_file(), reason="准入语料不可用")
def test_admission_check_distinguishes_reasons(ctx):
    entries = [{"candidate": "meld_opportunity_cost", "weights": {"adj.beta": 20.0}},
               {"candidate": "chain_path_value", "weights": {"adj.scale": 40.0}},
               {"candidate": "not_a_registered_candidate", "weights": {}}]
    results = {item["candidate"]: item for item in search.step_admission(
        ctx, entries, gate_dir=GATE_DIR, admission_corpus=CORPUS)}
    assert results["meld_opportunity_cost"]["status"] == "admitted"
    assert results["meld_opportunity_cost"]["corpus_sha256"]
    assert results["chain_path_value"]["status"] == "not_admitted"
    assert results["not_a_registered_candidate"]["status"] == "load_failed"
    assert results["not_a_registered_candidate"]["registration"] == "unregistered"


# --- 评估步：按调度器实扣结算、根组不符要能发现 ------------------------------

def test_screen_step_settles_with_scheduler_actual_tables(ctx, freeze, monkeypatch):
    panel = panel_of(freeze)
    entries = [entry("a", "id-a"), entry("b", "id-b")]
    fake = FakeScheduler(spent_tables=64,
                         results={"id-a": stats(mean=6.0), "id-b": stats(mean=1.0)})
    monkeypatch.setattr(search, "run_tool", fake)
    outcome = search.step_screen(ctx, level="L1", entries=entries, panel=panel,
                                 spec={"name": "L1", "roots": 16, "seats": 2,
                                       "keep_fraction": 0.5},
                                 gate_dir=GATE_DIR, admission_corpus=CORPUS,
                                 timeout_sec=60.0)
    assert outcome["planned_tables"] == 128          # 2 候选 × 16 根 × 2 换座 × 2 臂
    assert outcome["actual_tables"] == 64            # 调度器只扣了 64（部分候选被拒）
    assert outcome["problems"] == []
    assert ctx.ledger.spent("search")["tables"] == 64, "按实扣结算，差额退回"
    record = ctx.archive.records["a"]
    assert record.levels["L1"]["classification"]["state"] == "resolved_positive"
    assert record.levels["L1"]["statistics"]["mean"] == 6.0


def test_screen_step_flags_root_mismatch(ctx, freeze, monkeypatch):
    panel = panel_of(freeze)
    entries = [entry("a", "id-a")]
    fake = FakeScheduler(spent_tables=64, results={"id-a": stats(mean=6.0)},
                         root_keys=["somebody-elses-board-0"])
    monkeypatch.setattr(search, "run_tool", fake)
    outcome = search.step_screen(ctx, level="L1", entries=entries, panel=panel,
                                 spec={"name": "L1", "roots": 16, "seats": 2,
                                       "keep_fraction": 0.5},
                                 gate_dir=GATE_DIR, admission_corpus=CORPUS,
                                 timeout_sec=60.0)
    assert outcome["status"] == "failed"
    assert any("根组" in problem for problem in outcome["problems"])


def test_screen_step_never_charges_more_than_reserved(ctx, freeze, monkeypatch):
    panel = panel_of(freeze)
    entries = [entry("a", "id-a")]
    fake = FakeScheduler(spent_tables=999, results={"id-a": stats(mean=6.0)})
    monkeypatch.setattr(search, "run_tool", fake)
    outcome = search.step_screen(ctx, level="L1", entries=entries, panel=panel,
                                 spec={"name": "L1", "roots": 16, "seats": 2,
                                       "keep_fraction": 0.5},
                                 gate_dir=GATE_DIR, admission_corpus=CORPUS,
                                 timeout_sec=60.0)
    assert outcome["status"] == "failed"
    assert any("预算超支" in problem for problem in outcome["problems"])
    assert ctx.ledger.reservations[0]["overrun"] is True, "超支必须留痕"


# --- token 口径：以生成端产物为准；读不到显式标 unknown 并单独计数 -------------

def test_unknown_token_usage_is_charged_conservatively_and_counted(tmp_path: Path, freeze):
    """读不到用量时按**预留额**保守计费并单独计数——绝不静默按 0 记账。"""

    ledger = search.SearchLedger.load(tmp_path / "ledger.json", freeze)
    reservation = ledger.reserve(step_id="generate:t1", account="search",
                                 amounts={"calls": 1, "output_tokens": 32768},
                                 note="一次生成")
    ledger.settle(reservation, status="ok", actual={"calls": 1, "output_tokens": 32768},
                  note="用量未知", tokens_unknown=True)
    assert ledger.unknown_token_calls("search") == 1
    assert ledger.unknown_token_charged("search") == 32768
    payload = ledger.to_json()["accounts"]["search"]
    assert payload["unknown_token_calls"] == 1 and payload["unknown_token_charged"] == 32768
    assert payload["spent"]["output_tokens"] == 32768, "未知量保守计入已消耗"
    assert ledger.unknown_token_calls("confirm") == 0


def test_read_token_usage_prefers_generator_ledger_then_record(tmp_path: Path):
    gen_out = tmp_path / "gen"
    gen_out.mkdir()
    # ① 生成端台账有增量 ⇒ 直接用它的口径
    (gen_out / "budget.json").write_text(json.dumps({"spent_tokens": 500}), encoding="utf-8")
    usage = search.read_token_usage(gen_out=gen_out, attempt_dir=None, before=100.0, after=500.0)
    assert usage["known"] and usage["output_tokens"] == 400
    # ② 台账无增量（delegate/replay 摄入路径）⇒ 退到尝试记录的 usage
    attempt = tmp_path / "attempt"
    attempt.mkdir()
    (attempt / "record.json").write_text(json.dumps(
        {"reply": {"usage": {"output_tokens": 321}}}), encoding="utf-8")
    usage = search.read_token_usage(gen_out=gen_out, attempt_dir=str(attempt),
                                    before=500.0, after=500.0)
    assert usage["known"] and usage["output_tokens"] == 321
    # ③ 两处都没有 ⇒ 显式 unknown（不是 0）
    empty = tmp_path / "empty"
    empty.mkdir()
    usage = search.read_token_usage(gen_out=empty, attempt_dir=None, before=None, after=None)
    assert usage["known"] is False and usage["output_tokens"] is None and usage["reason"]


def test_generate_step_marks_unknown_and_stop_rule_caps_unknowns(ctx, monkeypatch):
    """用量读不到时：按预留额计费 + 单独计数；达到冻结上限即停止。"""

    monkeypatch.setattr(search, "run_tool", lambda *a, **k: search.ToolRun(
        name="sitin_generate.i1", command=("gen",), returncode=0, timed_out=False,
        elapsed_sec=1.0, signals_sent=(), stdout=json.dumps(
            {"attempt_identity": "gen|i1|x", "attempt_dir": None, "parse_status": "ok",
             "load_ok": True, "admission": "pending_admission"}), stderr=""))
    request = {"request_id": "g1", "operator": "i1", "backend": "replay"}
    outcome = search.step_generate(ctx, request, timeout_sec=10.0, token_reserve=8192)
    assert outcome["token_usage"]["known"] is False
    assert ctx.ledger.unknown_token_calls("search") == 1
    assert ctx.ledger.spent("search")["output_tokens"] == 8192, "未知量按预留额保守计费"
    assert ctx.archive.records["gen|i1|x"].registration == "pending_registration"


def test_generate_step_uses_generator_reported_usage(ctx, monkeypatch):
    def fake(name, command, *, cwd, timeout_sec, dry_run=False):
        out = Path([str(item) for item in command][
            [str(item) for item in command].index("--out") + 1])
        out.mkdir(parents=True, exist_ok=True)
        # 生成端是**先预留后调用**：调用前台账就存在（0），调用后累加。
        (out / "budget.json").write_text(json.dumps({"spent_tokens": 4096}), encoding="utf-8")
        return search.ToolRun(name=name, command=tuple(str(i) for i in command),
                              returncode=0, timed_out=False, elapsed_sec=2.0,
                              signals_sent=(), stdout=json.dumps(
                                  {"attempt_identity": "gen|i1|y", "attempt_dir": None}),
                              stderr="")

    monkeypatch.setattr(search, "run_tool", fake)
    # 调用前生成端台账已存在（先预留后调用），因此"增量"口径成立。
    gen_out = ctx.out / "generate" / "g2"
    gen_out.mkdir(parents=True, exist_ok=True)
    (gen_out / "budget.json").write_text(json.dumps({"spent_tokens": 0}), encoding="utf-8")
    outcome = search.step_generate(ctx, {"request_id": "g2", "operator": "i1",
                                         "backend": "replay"},
                                   timeout_sec=10.0, token_reserve=8192)
    assert outcome["token_usage"]["known"] is True
    assert ctx.ledger.spent("search")["output_tokens"] == 4096, "以生成端产物的用量为准"
    assert ctx.ledger.unknown_token_calls("search") == 0


# --- 阶段证据取代关系（回合 4） ---------------------------------------------

def test_handoff_records_stage_evidence_supersession(tmp_path: Path, freeze):
    """外部运行可取代结论，但必须标来源、标 superseded、按开发期消耗登记（不追认）。"""

    archive = search.Archive.load(tmp_path / "a.json", freeze)
    ctx = _ctx_with("r", freeze, archive, "l.json", tmp_path)
    evidence = {
        "decision": {"path": "优先省钱路径", "reason": "同面板同 seed_base，自跑买不到新信息"},
        "superseded": {"out": "run-stage", "pairs": "7/10", "tables_spent": 174,
                       "status": "unrankable"},
        "superseding": {"source": "…/validation-10scen/…/stage-compare.json",
                        "executor_version": "ver 3", "pairs": "10/10",
                        "tables": {"spent": 183, "planned": 240},
                        "metrics": {"delta": 2.5, "sd_root": 9.2286, "se_root": 2.9183,
                                    "mde": 8.176, "n_scenarios": 10},
                        "extra_tables": {"records": 2, "tables": 3,
                                         "detail": [{"arm": "candidate", "scenario_index": 2}]}},
        "conclusion": {"state": "未分辨（配对正确、分辨力不足）",
                       "why": "|Δ| < MDE",
                       "what_changed": "变化来自配对修正，措辞不得改口成「更优」"},
        "accounting": {"recognized_in_search_ledger": False,
                       "reason": "外部运行不进我的 spent"},
    }
    handoff = search.build_handoff(ctx, pool={"candidates": []}, stage_evidence=evidence)
    kinds = {gap["kind"] for gap in handoff["gaps"]}
    assert "stage_evidence_superseded" in kinds
    gap = [g for g in handoff["gaps"] if g["kind"] == "stage_evidence_superseded"][0]
    assert gap["tables_spent"] == 174 and "superseded_by" in gap
    text = search.render_handoff_md(handoff)
    assert "阶段比较证据（取代关系）" in text
    assert "未分辨（配对正确、分辨力不足）" in text and "更优" in text
    assert "外部运行不进我的 spent" in text


def test_supersession_patches_machine_fields_not_just_narrative(tmp_path: Path, freeze):
    """F3：被取代的旧指标必须从 `candidates[].stage` 里清掉，并留指针 + 外部指标标注。"""

    archive = search.Archive.load(tmp_path / "a2.json", freeze)
    record = archive.upsert("meld_opportunity_cost", candidate="meld_opportunity_cost",
                            identity="id-1", registration="registered",
                            gate={"status": "admitted"})
    record.stage = {"status": "unrankable", "tables_spent": 174,
                    "metrics": {"delta": 0.571429, "mde": 7.408695}}
    ctx = _ctx_with("r2", freeze, archive, "l2.json", tmp_path)
    evidence = {
        "superseded": {"record_key": "meld_opportunity_cost", "out": "run-stage",
                       "verdict": "配对键选错造成误废"},
        "superseding": {"source": "…/validation-10scen/…/stage-compare.json",
                        "executor_version": "ver 3", "pairs": "10/10",
                        "tables": {"spent": 183, "planned": 240},
                        "metrics": {"delta": 2.5, "mde": 8.175958},
                        "secondary": {"reached_final": {"mean": 0.2}}},
    }
    handoff = search.build_handoff(ctx, pool={"candidates": []}, stage_evidence=evidence)
    item = [c for c in handoff["candidates"] if c["key"] == "meld_opportunity_cost"][0]
    stage = item["stage"]
    assert stage["metrics"] is None, "旧 Δ=0.571/MDE=7.409 不得留在机器字段里"
    assert stage["metrics_status"] == "superseded"
    assert stage["superseded_by"].endswith("stage-compare.json")
    assert stage["tables_spent"] == 174, "被取代的是结论，消耗记录照留"
    assert stage["superseding"]["metrics"]["delta"] == 2.5
    assert stage["superseding"]["recognized_in_search_ledger"] is False
    assert "未追认" in stage["superseding"]["label"]


# --- 触发面接线验证（裁定一：先改判别力，不加根数） ------------------------

def _g2(*, fired: int, changed: int, matrix: Optional[Dict[str, Any]] = None,
        applicable: int = 3249) -> Dict[str, Any]:
    return {"applicable_windows": applicable, "fired_windows": fired,
            "applicable_changed": changed, "change_matrix": matrix or {},
            "window_classes": {"other": applicable - fired, "response": fired}}


def test_compare_wiring_reports_reached_and_parameter_effect():
    """零值对照让可观测项变化 ⇒ 参数数值确实改变了行为（接线证据）。"""

    result = search.compare_wiring({
        "declared": _g2(fired=100, changed=2, matrix={"peng->pass": 2}),
        "injected": _g2(fired=120, changed=3, matrix={"peng->pass": 3}),
        "zero": _g2(fired=40, changed=0)})
    assert result["branch_reached"] is True
    assert result["parameters_change_observable_behaviour"] is True
    assert "declared vs zero" in result["differences"]
    assert result["differences"]["declared vs zero"]["fired_windows"] == {"declared": 100, "zero": 40}
    assert "接线证据" in result["boundary"] and "不回答" in result["boundary"]


def test_compare_wiring_flags_an_uncovered_surface():
    """触发面未到达候选（fired=0）⇒ 结论是"换语料而不是加根数"，不是"参数无效"。"""

    result = search.compare_wiring({"declared": _g2(fired=0, changed=0, applicable=48),
                                    "injected": _g2(fired=0, changed=0, applicable=48),
                                    "zero": _g2(fired=0, changed=0, applicable=48)})
    assert result["branch_reached"] is False
    assert result["parameters_change_observable_behaviour"] is False
    assert "未到达" in result["verdict"] and "换语料" in result["verdict"]


def test_compare_wiring_marks_magnitude_only_differences_unresolved():
    """三套参数可观测项相同 ⇒ 幅度层面不可区分，标 unresolved，不得写成"参数已生效"。"""

    same = _g2(fired=100, changed=2, matrix={"peng->pass": 2})
    result = search.compare_wiring({"declared": dict(same), "injected": dict(same),
                                    "zero": dict(same)})
    assert result["branch_reached"] is True
    assert result["parameters_change_observable_behaviour"] is False
    assert "不可区分" in result["verdict"] and "unresolved" in result["verdict"]
    assert "候选是否更强" in result["boundary"], "边界必须写明不得据此写效果结论"


def test_g2_evidence_extracts_detail_from_a_gate_report(tmp_path: Path):
    path = tmp_path / "g2.json"
    path.write_text(json.dumps({
        "evidence_kind": "trigger", "admitted": False,
        "gates": [{"gate": "G-0 x", "status": "PASS"},
                  {"gate": "G-2 退化检测", "status": "INSUFFICIENT",
                   "detail": {"fired_windows": 100, "applicable_changed": 2}}]}),
        encoding="utf-8")
    detail = search._g2_evidence(path)
    assert detail["fired_windows"] == 100 and detail["_gate_status"] == "INSUFFICIENT"
    assert detail["_admitted"] is False, "trigger 口径必须留下 admitted=False 的痕迹"
    assert search._g2_evidence(tmp_path / "missing.json") is None


# --- 回合 2 返工项：零差异观测 / 更正 / 超限即停 / 冻结绑定 -------------------

def test_describe_statistics_marks_zero_difference_observations():
    """逐根差值为 0 且 sd=0 ⇒ no_observed_difference；理由不得写成"分辨不出方向"。"""

    zero = search.describe_statistics(stats(mean=0.0, mde=0.0, n_roots=8, sd_root=0.0))
    assert zero["state"] == "no_observed_difference"
    assert "零差异观测" in zero["reason"] and "分辨不出方向" not in zero["reason"]
    # 均值 0 但根间有波动（sd≠0）仍是"未分辨"，不得混为一谈
    varied = search.describe_statistics(stats(mean=0.0, mde=3.0, n_roots=8))
    assert varied["state"] == "unresolved"


def test_ledger_correct_rewrites_a_known_wrong_value_with_a_trail(tmp_path: Path, freeze):
    """更正已结算的错值：改 charged、留下 before/after 与理由，不新增预留。"""

    ledger = search.SearchLedger.load(tmp_path / "l.json", freeze)
    reservation = ledger.reserve(step_id="stage:compare", account="search",
                                 amounts={"tables": 180, "wall_clock_sec": 853.875}, note="阶段")
    ledger.settle(reservation, status="ok", actual={"tables": 174, "wall_clock_sec": 0.0})
    assert ledger.reservations[0]["overrun"] is False
    ledger.correct(reservation, actual={"wall_clock_sec": 1250.621},
                   note="恢复路径没拿到执行件 elapsed，按执行件台账更正")
    entry = ledger.reservations[0]
    assert entry["charged"]["wall_clock_sec"] == 1250.621
    assert entry["overrun"] is True, "更正后必须重算超限"
    assert entry["corrections"][0]["before"]["wall_clock_sec"] == 0.0
    assert len(ledger.reservations) == 1, "更正不得新增预留（否则一笔开销两条记录）"
    with pytest.raises(ValueError, match="理由"):
        ledger.correct(reservation, actual={"wall_clock_sec": 1.0}, note="  ")


def test_overrun_of_reports_any_axis_including_wall_clock(ctx):
    """**超限即停**：四维一视同仁——墙钟超了也要给出停止理由。"""

    reservation = ctx.ledger.reserve(step_id="screen:L1", account="search",
                                     amounts={"tables": 10, "wall_clock_sec": 100}, note="x")
    ctx.ledger.settle(reservation, status="ok", actual={"tables": 10, "wall_clock_sec": 250})
    reason = ctx.overrun_of("screen:L1")
    assert reason and "wall_clock_sec" in reason
    assert ctx.ledger.overrun_steps("search") == ["screen:L1"]
    assert ctx.overrun_of("screen:L2") is None


def test_freeze_binding_flags_an_in_place_rewrite(tmp_path: Path, freeze):
    """冻结件被原地改写 ⇒ 交接件必须报"绑定断裂"，不得只报当前文件 sha。"""

    archive = search.Archive.load(tmp_path / "a.json", freeze)
    ctx = _ctx_with("r", freeze, archive, "l.json", tmp_path, freeze_sha="deadbeef" * 8)
    rows = search.freeze_binding([ctx])
    assert rows[0]["bound"] is False
    assert rows[0]["ledger_recorded_sha256"] != rows[0]["file_current_sha256"]
    handoff = search.build_handoff(ctx, pool={"candidates": []})
    assert any(gap["kind"] == "freeze_binding_broken" for gap in handoff["gaps"])


def test_handoff_renders_development_spend_as_registered_not_recognised(tmp_path: Path, freeze):
    """开发期消耗只登记：渲染出来，并写明不进搜索账的 spent / 上限分母。"""

    archive = search.Archive.load(tmp_path / "a.json", freeze)
    ctx = _ctx_with("r", freeze, archive, "l.json", tmp_path)
    dev = {"items": [{"label": "执行件阶段桌赛", "value": 252, "unit": "桌",
                      "source": "3.4-stage-candidate/README.md", "reproducible": "部分"}],
           "totals": {"tables": 730, "output_tokens": 57853},
           "notes": ["36 桌落在 /tmp：不可复跑"]}
    handoff = search.build_handoff(ctx, pool={"candidates": []}, development_spend=dev)
    text = search.render_handoff_md(handoff)
    assert "开发期消耗（登记，不追认）" in text and "不进搜索账的 spent" in text
    assert "730 桌 / 57853 token" in text and "不可复跑" in text


# --- 晋级：冻结名额 + 探索名额需要机制假设 ----------------------------------

def test_promote_needs_hypothesis_for_exploration_slot(ctx):
    # a/b 点估计靠前（留存 0.5 ⇒ 4 个可排序候选保留 2 个）；c/e 落在后半且**本面板未分辨**。
    for key, mean in (("a", 8.0), ("b", 7.0), ("c", 0.4), ("e", -0.2)):
        record = ctx.archive.upsert(key, identity="id-" + key, registration="registered")
        record.levels["L1"] = {"statistics": stats(mean=mean),
                               "classification": search.describe_statistics(stats(mean=mean))}
    failed = ctx.archive.upsert("d", identity="id-d", registration="registered")
    failed.levels["L1"] = {"statistics": stats(mean=None, rankable=False, n_roots=0,
                                              status="failed"),
                           "classification": search.describe_statistics(
                               stats(mean=None, rankable=False, n_roots=0, status="failed"))}
    entries = [entry(key, "id-" + key) for key in ("a", "b", "c", "d", "e")]
    no_hypothesis = search.step_promote(ctx, level="L1", entries=entries, hypotheses={})
    assert no_hypothesis["promoted"] == ["a", "b"], "留存比例 0.5 → 4 个可排序候选里保留 2 个"
    assert no_hypothesis["exploration"] == [], "没有机制假设就不占探索名额"
    assert any(item["key"] == "d" for item in no_hypothesis["eliminated"])
    assert ctx.archive.records["c"].verdict == "unresolved", "未分辨就标未分辨"

    with_hypothesis = search.step_promote(ctx, level="L1", entries=entries,
                                          hypotheses={"c": "等待有效牌估计偏高时应更少鸣牌"})
    assert [item["key"] for item in with_hypothesis["exploration"]] == ["c"]
    assert ctx.archive.records["c"].verdict == "promoted_exploration"
    assert "机制假设" in ctx.archive.records["c"].verdict_reason


def test_near_miss_hint_points_at_literal_formatting():
    """身份是**字面量敏感**的：JSON 写 20 与 20.0 会得到两个身份。

    不静默规范化（那会让"门禁通过的那份配置"与"实际跑的配置"对不上），但必须
    给出可定位的线索，否则操作者只会看到"没有记录"。
    """

    scanned = [("gates-a.json", {"bound_identity":
                                 "meld_opportunity_cost|adj(beta=20.0)|base(default)|src8463a0a5891a1cb6"})]
    hint = search._near_miss_hint(
        scanned, "meld_opportunity_cost|adj(beta=20)|base(default)|src8463a0a5891a1cb6")
    assert "近失配" in hint and "beta=20.0" in hint
    assert search._near_miss_hint(scanned, "other|adj(beta=20)|base(default)|srcdeadbeef") == ""


def test_resolve_path_uses_repo_root_for_relative_paths(tmp_path: Path):
    assert search.resolve_path("review/x.json") == _project_file(_PROJECT_ROOT, _REPO / "review/x.json")
    absolute = tmp_path / "a.json"
    assert search.resolve_path(absolute) == absolute


# --- 阶段：探针不花预算、结论落在三态 ---------------------------------------

class FakeStageModule:
    PANEL_POLICY_NAMES = ("weighted_heuristic_v2", "safe_fallback")


def test_stage_probe_rejects_candidate_policy(ctx, monkeypatch):
    monkeypatch.setattr(search, "_sibling", lambda name: FakeStageModule())
    monkeypatch.setattr(search, "run_tool", lambda *a, **k: search.ToolRun(
        name="probe", command=("stage", "check"), returncode=2, timed_out=False,
        elapsed_sec=0.1, signals_sent=(),
        stdout="", stderr="error: argument --panel-policy: invalid choice: 'x'"))
    probe = search.stage_seating_probe(ctx, candidate_policy="meld_opportunity_cost")
    assert probe["verdict"] == "unsupported"
    assert search.stage_seating_probe(ctx, candidate_policy="weighted_heuristic_v2")["verdict"] \
        == "supported"


def test_stage_probe_detects_frozen_executor_capability(ctx, monkeypatch):
    """冻结模板后按**执行件能力**探测（compare --help 是否接受候选与准入记录）。"""

    payload = freeze_payload()
    payload["stage"]["command_template"] = ["{python}", "compare", "--candidate", "{candidate}"]
    path = ctx.out.parent / "freeze-cap.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    ctx = search.SearchContext(out=ctx.out, freeze=search.Freeze.load(path), ledger=ctx.ledger,
                               archive=ctx.archive, state=ctx.state, steps_path=ctx.steps_path)
    monkeypatch.setattr(search, "_sibling", lambda name: FakeStageModule())
    monkeypatch.setattr(search, "run_tool", lambda *a, **k: search.ToolRun(
        name="probe", command=("compare", "--help"), returncode=0, timed_out=False,
        elapsed_sec=0.1, signals_sent=(),
        stdout="usage: compare --candidate CANDIDATE --gate-record GATE_RECORD", stderr=""))
    probe = search.stage_seating_probe(ctx, candidate_policy="meld_opportunity_cost")
    assert probe["capability_mode"] is True and probe["verdict"] == "supported"


def test_stage_probe_survives_a_broken_stage_tool(ctx, monkeypatch):
    """阶段工具正在被编辑也不能让探针抛异常：那是“能力不可用”，不是整轮崩掉。"""

    def boom(name):
        raise SyntaxError("'(' was never closed (sitin_stage.py)")

    monkeypatch.setattr(search, "_sibling", boom)
    monkeypatch.setattr(search, "run_tool", lambda *a, **k: search.ToolRun(
        name="probe", command=("stage",), returncode=1, timed_out=False, elapsed_sec=0.1,
        signals_sent=(), stdout="", stderr="SyntaxError: '(' was never closed"))
    probe = search.stage_seating_probe(ctx, candidate_policy="meld_opportunity_cost")
    assert probe["verdict"] == "unknown"
    assert probe["stage_module_error"]


def test_stage_step_records_gap_without_spending(ctx, monkeypatch):
    monkeypatch.setattr(search, "_sibling", lambda name: FakeStageModule())
    monkeypatch.setattr(search, "run_tool", lambda *a, **k: search.ToolRun(
        name="probe", command=("stage", "check"), returncode=2, timed_out=False,
        elapsed_sec=0.1, signals_sent=(), stdout="", stderr="invalid choice"))
    outcome = search.step_stage(ctx, entries=[entry("a", "id-a")],
                                stage_plan={"candidate_policy": "a", "pairs": 4,
                                            "tables_per_run": 9, "arms": 2,
                                            "participants": 9})
    assert outcome["status"] == "gap"
    assert ctx.ledger.spent("search")["tables"] == 0, "不支持时一分钱都不花"
    assert ctx.ledger.reservations == [], "连预留都不该发生"
    assert ctx.archive.records["a"].stage["status"] == "gap"


def test_select_upgrade_queue_reserves_a_slot_for_exploration():
    """容量 >= 2 时探索候选**先占一个名额**；其余按评分序，不按名字典序。"""

    ranked = [{"key": "zeta"}, {"key": "alpha"}]
    exploration = [{"key": "mid"}]
    assert [item["key"] for item in search.select_upgrade_queue(ranked, exploration, 2)] == \
        ["mid", "zeta"], "探索名额先占，其余按评分序"
    assert [item["key"] for item in search.select_upgrade_queue(ranked, exploration, 1)] == ["zeta"]
    assert [item["key"] for item in search.select_upgrade_queue(ranked, exploration, 0)] == []
    assert [item["key"] for item in search.select_upgrade_queue([], exploration, 2)] == ["mid"]


# --- F1 溯源字段的消费端（回合 6 残余项） -----------------------------------

def compliant_report() -> Dict[str, Any]:
    """一份**合规**的执行件报告骨架（契约 §3.5 的五个溯源字段齐备）。"""

    return {
        "schema": search.STAGE_COMPARE_SCHEMA, "status": "complete",
        "versions": {"tool_sha256": "bf8eda7867c26b7e14f4d5c6dbbb1f1078d1b653004379fdc57151cdab0b8f7e"},
        "source_digest_at_start": "bf8eda7867c26b7e",
        "source_digest_at_end": "bf8eda7867c26b7e",
        "tool_source_changed_during_run": False,
        "budget": {"precheck": "passed", "required_tables": 18},
    }


def test_stage_provenance_is_machine_decidable():
    """缺字段 / 运行中源码被改，都必须在机器字段里可判（不靠人读 prose）。"""

    ok = search.stage_provenance(compliant_report())
    assert ok["compliant"] is True and ok["missing_fields"] == []
    assert ok["source_changed_during_run"] is False and ok["precheck"] == "passed"

    legacy = compliant_report()
    for field in ("source_digest_at_start", "source_digest_at_end",
                  "tool_source_changed_during_run"):
        legacy.pop(field)
    legacy.pop("versions")
    legacy["budget"] = {"note": "B1 之前的产物"}
    partial = search.stage_provenance(legacy)
    assert partial["compliant"] is False
    assert set(partial["missing_fields"]) == {
        "versions.tool_sha256", "source_digest_at_start", "source_digest_at_end",
        "tool_source_changed_during_run", "budget.precheck"}
    assert "非合规报告" in partial["note"]

    changed = search.stage_provenance(
        dict(compliant_report(), tool_source_changed_during_run=True))
    assert changed["source_changed_during_run"] is True


def test_stage_step_flags_source_changed_report_and_keeps_tables(ctx, monkeypatch):
    """tool_source_changed_during_run=true ⇒ 报告不作结论依据，但桌数照实结算。"""

    frozen_template = freeze_payload()
    frozen_template["stage"]["command_template"] = ["{python}", "compare", "--out", "{out}"]
    path = ctx.out.parent / "freeze-prov.json"
    path.write_text(json.dumps(frozen_template, ensure_ascii=False), encoding="utf-8")
    ctx = search.SearchContext(out=ctx.out, freeze=search.Freeze.load(path),
                               ledger=ctx.ledger, archive=ctx.archive, state=ctx.state,
                               steps_path=ctx.steps_path)

    def fake(name, command, *, cwd, timeout_sec, dry_run=False):
        rendered = [str(item) for item in command]
        if name == "sitin_stage.probe":
            return search.ToolRun(name=name, command=tuple(rendered), returncode=0,
                                  timed_out=False, elapsed_sec=0.1, signals_sent=(),
                                  stdout="--candidate --gate-record", stderr="")
        arm_dir = Path(rendered[rendered.index("--out") + 1])
        arm_dir.mkdir(parents=True, exist_ok=True)
        report = dict(compliant_report(), tables={"planned": 36, "spent": 36},
                      metrics={"delta": 9.9}, tool_source_changed_during_run=True,
                      source_digest_at_end="deadbeefcafe0000")
        (arm_dir / search.STAGE_COMPARE_REPORT).write_text(
            json.dumps(report, ensure_ascii=False), encoding="utf-8")
        return search.ToolRun(name=name, command=tuple(rendered), returncode=0,
                              timed_out=False, elapsed_sec=1.0, signals_sent=(),
                              stdout="", stderr="")

    monkeypatch.setattr(search, "run_tool", fake)
    outcome = search.step_stage(ctx, entries=[entry("a", "id-a")],
                                stage_plan={"candidate_policy": "a", "pairs": 2,
                                            "tables_per_run": 9, "arms": 2,
                                            "participants": 9, "candidate": "a"})
    assert outcome["status"] == "failed", "源码变动必须让本步失败，不得静默成功"
    assert any("运行中源码被改" in p for p in outcome["problems"])
    assert ctx.ledger.spent("search")["tables"] == 36, "桌是真的跑过了，照实结算"
    stage = ctx.archive.records["a"].stage
    assert stage["status"] == "untrusted_source"
    assert stage["provenance"]["source_changed_during_run"] is True


def test_stage_step_marks_a_legacy_report_as_noncompliant(ctx, monkeypatch):
    """字段落地之前的旧报告：桌数照算，但**机器字段**标出缺了什么。"""

    frozen_template = freeze_payload()
    frozen_template["stage"]["command_template"] = ["{python}", "compare", "--out", "{out}"]
    path = ctx.out.parent / "freeze-legacy.json"
    path.write_text(json.dumps(frozen_template, ensure_ascii=False), encoding="utf-8")
    ctx = search.SearchContext(out=ctx.out, freeze=search.Freeze.load(path),
                               ledger=ctx.ledger, archive=ctx.archive, state=ctx.state,
                               steps_path=ctx.steps_path)

    def fake(name, command, *, cwd, timeout_sec, dry_run=False):
        rendered = [str(item) for item in command]
        if name == "sitin_stage.probe":
            return search.ToolRun(name=name, command=tuple(rendered), returncode=0,
                                  timed_out=False, elapsed_sec=0.1, signals_sent=(),
                                  stdout="--candidate --gate-record", stderr="")
        arm_dir = Path(rendered[rendered.index("--out") + 1])
        arm_dir.mkdir(parents=True, exist_ok=True)
        legacy = {"schema": search.STAGE_COMPARE_SCHEMA, "status": "complete",
                  "tables": {"planned": 240, "spent": 183},
                  "metrics": {"delta": 2.5}, "verification": {"extra_tables": []},
                  "budget": {"budget_tables": 240}}
        (arm_dir / search.STAGE_COMPARE_REPORT).write_text(
            json.dumps(legacy, ensure_ascii=False), encoding="utf-8")
        return search.ToolRun(name=name, command=tuple(rendered), returncode=0,
                              timed_out=False, elapsed_sec=1.0, signals_sent=(),
                              stdout="", stderr="")

    monkeypatch.setattr(search, "run_tool", fake)
    outcome = search.step_stage(ctx, entries=[entry("a", "id-a")],
                                stage_plan={"candidate_policy": "a", "pairs": 2,
                                            "tables_per_run": 9, "arms": 2,
                                            "participants": 9, "candidate": "a"})
    assert any("非合规报告" in p for p in outcome["problems"])
    assert ctx.ledger.spent("search")["tables"] == 183, "按 spent 实报，不按 planned 保守计费"
    compliance = ctx.archive.records["a"].stage["contract_compliance"]
    assert compliance["compliant"] is False
    assert "budget.precheck" in compliance["missing_fields"]
    assert ctx.archive.records["a"].stage["status"] == "complete+noncompliant"


def test_stage_step_reconciles_with_executor_report(ctx, freeze, monkeypatch):
    """冻结模板后：按执行件报告的 tables.spent 结算，并把阶段指标写进档案。"""

    frozen_template = freeze_payload()
    frozen_template["stage"]["command_template"] = [
        "{python}", "{tools_dir}/sitin_stage.py", "compare", "--candidate", "{candidate}",
        "--weights", "{weights}", "--gate-record", "{gate_record}",
        "--budget-tables", "{budget_tables}", "--out", "{out}"]
    path = ctx.out.parent / "freeze-stage.json"
    path.write_text(json.dumps(frozen_template, ensure_ascii=False), encoding="utf-8")
    ctx = search.SearchContext(out=ctx.out, freeze=search.Freeze.load(path),
                               ledger=ctx.ledger, archive=ctx.archive, state=ctx.state,
                               steps_path=ctx.steps_path)

    def fake(name, command, *, cwd, timeout_sec, dry_run=False):
        rendered = [str(item) for item in command]
        if name == "sitin_stage.probe":
            return search.ToolRun(name=name, command=tuple(rendered), returncode=0,
                                  timed_out=False, elapsed_sec=0.1, signals_sent=(),
                                  stdout="usage: ... --candidate CANDIDATE --gate-record GATE",
                                  stderr="")
        arm_dir = Path(rendered[rendered.index("--out") + 1])
        arm_dir.mkdir(parents=True, exist_ok=True)
        (arm_dir / search.STAGE_COMPARE_REPORT).write_text(json.dumps(
            dict(compliant_report(), tables={"planned": 18, "spent": 18},
                 metrics={"primary": "advance_rate", "delta": 0.05}), ensure_ascii=False),
            encoding="utf-8")
        return search.ToolRun(name=name, command=tuple(rendered), returncode=0,
                              timed_out=False, elapsed_sec=9.0, signals_sent=(),
                              stdout="", stderr="")

    monkeypatch.setattr(search, "run_tool", fake)
    outcome = search.step_stage(ctx, entries=[entry("a", "id-a")],
                                stage_plan={"candidate_policy": "a", "pairs": 2,
                                            "tables_per_run": 9, "arms": 2,
                                            "participants": 9, "candidate": "a",
                                            "gate_record": "g.json",
                                            "admission_corpus": "c.jsonl"})
    assert outcome["status"] == "ran" and outcome["actual_tables"] == 18
    assert ctx.ledger.spent("search")["tables"] == 18, "按执行件实报结算"
    assert ctx.archive.records["a"].stage["metrics"]["delta"] == 0.05
    # **溯源被消费**：合规报告的五字段进档案（回合 6 残余项的落点）
    provenance = ctx.archive.records["a"].stage["provenance"]
    assert provenance["compliant"] is True and provenance["precheck"] == "passed"
    assert ctx.archive.records["a"].stage["contract_compliance"]["compliant"] is True


def test_stage_step_charges_reservation_when_report_is_missing(ctx, monkeypatch):
    """报告缺失 ⇒ 按预留额保守计费，并记成 gap/问题，不免费重演。"""

    frozen_template = freeze_payload()
    frozen_template["stage"]["command_template"] = ["{python}", "compare", "--out", "{out}"]
    path = ctx.out.parent / "freeze-stage2.json"
    path.write_text(json.dumps(frozen_template, ensure_ascii=False), encoding="utf-8")
    ctx = search.SearchContext(out=ctx.out, freeze=search.Freeze.load(path),
                               ledger=ctx.ledger, archive=ctx.archive, state=ctx.state,
                               steps_path=ctx.steps_path)
    monkeypatch.setattr(search, "run_tool", lambda name, command, **k: search.ToolRun(
        name=name, command=tuple(str(i) for i in command), returncode=0, timed_out=False,
        elapsed_sec=5.0, signals_sent=(),
        stdout="--candidate --gate-record" if name.endswith("probe") else "", stderr=""))
    outcome = search.step_stage(ctx, entries=[entry("a", "id-a")],
                                stage_plan={"candidate_policy": "a", "pairs": 2,
                                            "tables_per_run": 9, "arms": 2,
                                            "participants": 9, "candidate": "a"})
    assert outcome["status"] == "failed"
    assert outcome["actual_tables"] == 36, "缺报告时按预留额（2 对 × 9 桌 × 2 臂）计费"
    assert any("缺少" in problem for problem in outcome["problems"])


def test_cmd_run_dry_run_plans_without_spending(tmp_path, monkeypatch):
    """dry-run 走完编排（预留→渲染命令→释放），**一分预算都不花**，也不标记完成。"""

    payload = freeze_payload()
    payload["accounts"]["search"]["tables"] = 40
    payload["panel"] = {"roots": 2, "seats": 1, "baseline_id": "weighted_heuristic_v2",
                        "ruleset": "hangma-mvp-v10-public-counts", "seed_base": 1,
                        "root_prefix": "dry-"}
    payload["upgrade"] = {"slots": 0, "roots": 2, "seats": 1, "seed_base": 1, "root_prefix": "u-"}
    payload["stage"] = {"pairs": 0, "tables_per_run": 9, "arms": 2, "participants": 9}
    payload["retry_reserve_tables"] = 0
    freeze_path = tmp_path / "freeze.json"
    freeze_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    pool_path = tmp_path / "pool.json"
    pool_path.write_text(json.dumps({
        "schema": search.POOL_SCHEMA,
        "candidates": [{"candidate": "a", "weights": {}},
                       {"candidate": "b", "weights": {}}]}), encoding="utf-8")
    monkeypatch.setattr(search, "step_admission", lambda ctx, entries, **kwargs: [
        {"candidate": item["candidate"], "weights": item.get("weights") or {},
         "status": "admitted", "identity": "id-" + item["candidate"],
         "registration": "registered"} for item in entries])
    out = tmp_path / "out"
    rc = search.main(["run", "--freeze", str(freeze_path), "--out", str(out),
                      "--pool", str(pool_path), "--gate-records", str(tmp_path),
                      "--admission-corpus", str(tmp_path / "corpus.jsonl"), "--dry-run"])
    assert rc == 0
    ledger = json.loads((out / "ledger.json").read_text(encoding="utf-8"))
    assert ledger["accounts"]["search"]["spent"]["tables"] == 0, "dry-run 不得消耗桌数"
    assert {item["status"] for item in ledger["reservations"]} == {"released"}
    assert all("dry-run" in item["release_reason"] for item in ledger["reservations"])
    assert json.loads((out / "state.json").read_text(encoding="utf-8"))["completed"] == [], \
        "dry-run 不标记完成，重跑才会真的执行"


# --- 阶段单跑与多账交接 -----------------------------------------------------

def test_seed_entries_from_archive_binds_identity_and_gate(tmp_path: Path):
    """阶段单跑从**既有档案**播种身份：不重新拼参数（20 与 20.0 是两个身份，实测过）。"""

    archive = {
        "schema": search.ARCHIVE_SCHEMA, "freeze_sha256": "x",
        "records": {"meld_opportunity_cost": {
            "key": "meld_opportunity_cost", "candidate": "meld_opportunity_cost",
            "identity": "meld_opportunity_cost|adj(beta=20.0)|base(default)|src8463a0a5891a1cb6",
            "weights": {"adj.beta": 20.0},
            "gate": {"status": "admitted", "record_path": "/tmp/gates-x.json"}}},
    }
    path = tmp_path / "archive.json"
    path.write_text(json.dumps(archive, ensure_ascii=False), encoding="utf-8")
    entries = search.seed_entries_from_archive(path, ["meld_opportunity_cost"])
    assert entries[0]["identity"].endswith("src8463a0a5891a1cb6")
    assert entries[0]["weights"] == {"adj.beta": 20.0}
    assert entries[0]["gate_record"] == "/tmp/gates-x.json"
    with pytest.raises(ValueError, match="档案里没有候选"):
        search.seed_entries_from_archive(path, ["nope"])


def _ctx_with(out_name: str, freeze, archive, ledger_name: str, tmp_path: Path,
               freeze_sha: Optional[str] = None) -> "search.SearchContext":
    ledger = search.SearchLedger.load(tmp_path / ledger_name, freeze)
    if freeze_sha is not None:
        ledger.freeze_sha256 = freeze_sha      # 模拟"另一份冻结"的上下文（只读汇总用）
    return search.SearchContext(out=tmp_path / out_name, freeze=freeze, ledger=ledger,
                                archive=archive,
                                state=search.RunState.load(tmp_path / (out_name + "-s.json")),
                                steps_path=tmp_path / (out_name + "-st.jsonl"))


def test_merge_records_merges_same_panel_levels_across_rounds(tmp_path: Path, freeze):
    """同一面板的同名等级照常合并（跨面板才拒绝）。"""

    first = search.Archive.load(tmp_path / "a1.json", freeze)
    first.upsert("c1", identity="id-1", registration="registered",
                 levels={"L1": {"panel_id": "panel-A", "statistics": stats(mean=1.0)}},
                 verdict="promoted", verdict_reason="主账结论")
    second = search.Archive.load(tmp_path / "a2.json", freeze)
    second.upsert("c1", identity="id-1", registration="registered",
                  levels={"L2": {"panel_id": "panel-B", "statistics": stats(mean=-2.0)}},
                  stage={"status": "complete", "tables_spent": 180})
    merged, conflicts = search.merge_records(
        [_ctx_with("r1", freeze, first, "l1.json", tmp_path),
         _ctx_with("r2", freeze, second, "l2.json", tmp_path)])
    assert conflicts == []
    assert len(merged) == 1
    assert set(merged[0]["levels"]) == {"L1", "L2"}
    assert merged[0]["stage"]["tables_spent"] == 180


def test_merge_records_refuses_to_overwrite_across_panels_and_keeps_primary_verdict(tmp_path: Path, freeze):
    """**跨面板回归**（组合评审 P1）：冒烟的 L1 不得顶掉主账的 L1，verdict 也不得被顶掉。"""

    main = search.Archive.load(tmp_path / "m.json", freeze)
    main.upsert("c1", identity="id-1", registration="registered",
                levels={"L1": {"panel_id": "panel-main16", "statistics": stats(mean=2.0, n_roots=16)}},
                verdict="promoted_exploration",
                verdict_reason="探索名额：机制假设已登记——七对路径")
    smoke = search.Archive.load(tmp_path / "s.json", freeze)
    smoke.upsert("c1", identity="id-1", registration="registered",
                 levels={"L1": {"panel_id": "panel-smoke2", "statistics": stats(mean=-10.0, n_roots=2)}},
                 verdict="promoted", verdict_reason="开发面板点估计靠前（冻结留存比例 1.0）")
    primary = _ctx_with("main", freeze, main, "lm.json", tmp_path, freeze_sha="sha-main")
    other = _ctx_with("smoke", freeze, smoke, "ls.json", tmp_path, freeze_sha="sha-smoke")
    merged, conflicts = search.merge_records([primary, other], primary_sha="sha-main")
    record = merged[0]
    assert record["levels"]["L1"]["panel_id"] == "panel-main16", "主账面板必须留在主视图"
    assert record["levels"]["L1"]["statistics"]["n_roots"] == 16
    assert record["levels_other_panels"][0]["panel_id"] == "panel-smoke2", "另一块面板并列留档"
    assert record["verdict"] == "promoted_exploration", "verdict 只接受主冻结上下文的结论"
    assert "机制假设" in record["verdict_reason"]
    assert conflicts and conflicts[0]["kind"] == "cross_panel_level_conflict"
    assert "panel-smoke2" in conflicts[0]["panels"]


def test_step_resumes_pending_reservation_instead_of_charging_twice(ctx):
    """崩溃后重跑：续用未结算的预留，不重复扣款、也不报"重复预留"。"""

    reservation = ctx.ledger.reserve(step_id="screen:L1", account="search",
                                     amounts={"tables": 10}, note="首次")
    plan = ctx.step("screen:L1", account="search", amounts={"tables": 10}, note="重跑")
    assert plan["status"] == "resumed"
    assert plan["reservation"]["reservation_id"] == reservation["reservation_id"]
    assert len(ctx.ledger.reservations) == 1, "不得再记一笔"


def test_stage_step_recovers_an_existing_arm_report(ctx, monkeypatch):
    """执行件报告已在盘上 ⇒ 只对账不重跑（恢复不花第二遍桌数）。"""

    frozen_template = freeze_payload()
    frozen_template["stage"]["command_template"] = ["{python}", "compare", "--out", "{out}"]
    path = ctx.out.parent / "freeze-rec.json"
    path.write_text(json.dumps(frozen_template, ensure_ascii=False), encoding="utf-8")
    ctx = search.SearchContext(out=ctx.out, freeze=search.Freeze.load(path),
                               ledger=ctx.ledger, archive=ctx.archive, state=ctx.state,
                               steps_path=ctx.steps_path)
    calls: List[str] = []

    def fake(name, command, *, cwd, timeout_sec, dry_run=False):
        rendered = [str(item) for item in command]
        calls.append(name)
        if name == "sitin_stage.probe":
            return search.ToolRun(name=name, command=tuple(rendered), returncode=0,
                                  timed_out=False, elapsed_sec=0.1, signals_sent=(),
                                  stdout="--candidate --gate-record", stderr="")
        arm_dir = Path(rendered[rendered.index("--out") + 1])
        arm_dir.mkdir(parents=True, exist_ok=True)
        return search.ToolRun(name=name, command=tuple(rendered), returncode=0,
                              timed_out=False, elapsed_sec=1.0, signals_sent=(),
                              stdout="", stderr="")

    monkeypatch.setattr(search, "run_tool", fake)
    # 先放一份"上一次跑完但没结算"的报告
    arm_dir = ctx.out / "stage" / search._sibling("sitin_scheduler").cell_dir_name("a")
    arm_dir.mkdir(parents=True, exist_ok=True)
    (arm_dir / search.STAGE_COMPARE_REPORT).write_text(json.dumps({
        "schema": search.STAGE_COMPARE_SCHEMA, "status": "complete",
        "tables": {"planned": 18, "spent": 17},
        "metrics": {"primary": "advance_rate", "delta": 0.02}}, ensure_ascii=False),
        encoding="utf-8")
    outcome = search.step_stage(ctx, entries=[entry("a", "id-a")],
                                stage_plan={"candidate_policy": "a", "pairs": 2,
                                            "tables_per_run": 9, "arms": 2,
                                            "participants": 9, "candidate": "a"})
    assert outcome["actual_tables"] == 17, "按已有报告对账"
    assert "sitin_stage.compare" not in calls, "已有报告时不得重跑执行件"
    assert ctx.archive.records["a"].stage["recovered"] is True


def test_freeze_also_lists_each_ledger_separately(tmp_path: Path):
    """交接报告把多本账**并列 + 求和**，不合并台账（一本账一个冻结摘要）。"""

    paths = []
    for index, tables in ((1, 384), (2, 180)):
        payload = freeze_payload()
        payload["accounts"]["search"]["tables"] = tables
        path = tmp_path / "freeze{0}.json".format(index)
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        paths.append(path)
    out1, out2 = tmp_path / "run1", tmp_path / "run2"
    for out, path, spend in ((out1, paths[0], 288), (out2, paths[1], 180)):
        out.mkdir()
        (out / "freeze-path.txt").write_text(str(path) + "\n", encoding="utf-8")
        fr = search.Freeze.load(path)
        ledger = search.SearchLedger.load(out / "ledger.json", fr)
        reservation = ledger.reserve(step_id="s", account="search",
                                     amounts={"tables": spend}, note="t")
        ledger.settle(reservation, status="ok")
        search.Archive.load(out / "archive.json", fr).save()
        search.RunState.load(out / "state.json").save()
    rc = search.main(["freeze", "--freeze", str(paths[0]), "--out", str(out1),
                      "--also", str(out2)])
    assert rc == 0
    handoff = json.loads((out1 / "handoff.json").read_text(encoding="utf-8"))
    assert len(handoff["budget"]["ledgers"]) == 2
    assert handoff["budget"]["totals"]["search_spent_tables"] == 468
    assert handoff["budget"]["confirm_touched"] is False


# --- 交接：三种完成状态分开报、缺口单列 -------------------------------------

def test_handoff_separates_completion_states_and_gaps(ctx):
    record = ctx.archive.upsert("a", candidate="a", identity="id-a", registration="registered",
                                gate={"status": "admitted"})
    record.levels["L1"] = {"statistics": stats(mean=6.0),
                           "classification": search.describe_statistics(stats(mean=6.0))}
    record.verdict = "promoted"
    record.stage = {"status": "gap", "reason": "面板不能坐候选"}
    ctx.archive.upsert("gen-attempt-1", registration="pending_registration",
                       source={"kind": "generated_attempt"})
    handoff = search.build_handoff(ctx, pool={"candidates": [{"candidate": "a"}]})
    states = handoff["completion_states"]
    assert states[search.COMPLETION_TOOL]["status"] == "完成"
    assert states[search.COMPLETION_CANDIDATES]["promoted"] == ["a"]
    assert "未通过" in states[search.COMPLETION_RELEASE_GATE]["status"]
    kinds = {gap["kind"] for gap in handoff["gaps"]}
    assert "pending_registration" in kinds and "candidate_without_stage_budget" in kinds
    assert handoff["budget"]["confirm_touched"] is False, "确认账必须未被动用"
    assert "gen-attempt-1" in handoff["generated_pending_registration"]
    text = search.render_handoff_md(handoff)
    assert "三种完成状态" in text and "缺口" in text


# --- 反馈三段 + 边界守卫 ----------------------------------------------------

def test_feedback_separates_facts_from_hypothesis(ctx):
    record = ctx.archive.upsert("a", identity="id-a", gate={"status": "admitted"})
    record.levels["L1"] = {"statistics": stats(mean=6.0),
                           "classification": search.describe_statistics(stats(mean=6.0))}
    text = search.build_feedback(record.to_json())
    assert "## 事实" in text and "## 相关表现" in text and "## 机制假设" in text
    assert "不由工具臆造机制假设" in text, "未填写时必须明说未填写"
    filled = search.build_feedback(record.to_json(), hypothesis="鸣牌成本被低估")
    assert "鸣牌成本被低估" in filled


def test_guard_out_dir_refuses_controlled_source_surface(tmp_path: Path):
    with pytest.raises(ValueError, match="受控源码面"):
        search.guard_out_dir(_project_file(_PROJECT_ROOT, _REPO / "src" / "hangma_bot" / "policy"))
    with pytest.raises(ValueError, match="仓库根"):
        search.guard_out_dir(_REPO)
    assert search.guard_out_dir(tmp_path / "ok") == (tmp_path / "ok").resolve()


def test_run_tool_dry_run_does_not_execute(tmp_path: Path):
    run = search.run_tool("noop", ["definitely-not-a-real-binary"], cwd=tmp_path,
                          timeout_sec=5.0, dry_run=True)
    assert run.returncode is None and "(dry-run)" in run.stderr




# --- 残余证据收口：缺口定位字段、生成产物的取证强度与源码指纹 -------------------
#
# 这一节盯的是**验收时才暴露**的三类静默缺陷：机器字段不进人读件、夹具被当成候选、
# 相对路径解析错基准导致指纹为空。三者都不影响"跑通"，但都会让交接件说谎。

def _write_generation_records(gen_dir: Path, *, attempt_dir: str, identity: str,
                              is_model_output: Optional[bool],
                              evidence_kind: str) -> None:
    """造一个最小的生成产物目录：尝试台账 records.jsonl + 尝试目录里的 candidate.py。"""

    attempt = gen_dir / attempt_dir
    attempt.mkdir(parents=True, exist_ok=True)
    (attempt / "candidate.py").write_text("VALUE = 1\n", encoding="utf-8")
    (gen_dir / "records.jsonl").write_text(json.dumps({
        "schema": "sitin-generation-record/1",
        "attempt_identity": identity,
        "attempt_dir": attempt_dir,
        "evidence_kind": evidence_kind,
        "is_model_output": is_model_output,
        "admission_eligible": is_model_output,
    }, ensure_ascii=False) + "\n", encoding="utf-8")


def test_generation_evidence_strength_is_fail_closed_without_a_ledger(tmp_path: Path):
    """读不到台账 = unknown，**不是** drill：查不到就把产物从待注册清单里放走是最危险的错。"""

    missing = search.generation_evidence_strength(tmp_path / "nope", "any-identity")
    assert missing["strength"] == "unknown"
    assert missing["is_model_output"] is None


def test_code_sha_resolves_relative_attempt_dirs_against_the_generator_out(tmp_path: Path):
    """相对 attempt_dir 的基准是生成端的 --out；按工作目录解析会静默得到 None。"""

    gen = tmp_path / "gen"
    _write_generation_records(gen, attempt_dir="attempts/a", identity="i", is_model_output=True,
                              evidence_kind="headless_model_reply")
    assert search._code_sha_of("attempts/a") is None, "不传基准就是解析不到（旧行为）"
    resolved = search._code_sha_of("attempts/a", base=gen)
    assert resolved is not None and len(resolved) == 64


def test_handoff_backfills_the_generation_fingerprint_and_says_so(ctx):
    """空指纹必须就地重算**并登记补过**，不能悄悄改数、也不能留在交接件里当证据。"""

    _write_generation_records(ctx.out / "generate" / "g1", attempt_dir="attempts/model",
                              identity="genloop|model", is_model_output=True,
                              evidence_kind="headless_model_reply")
    ctx.archive.upsert("genloop|model", registration="pending_registration",
                       source={"kind": "generated_attempt", "request_id": "g1",
                               "attempt_dir": "attempts/model", "code_sha256": None})
    handoff = search.build_handoff(ctx, pool={"candidates": []})
    assert len(handoff["generated_evidence_backfill"]) == 1
    entry = handoff["generated_evidence_backfill"][0]
    assert entry["key"] == "genloop|model"
    assert entry["code_sha256"] and len(entry["code_sha256"]) == 64
    assert entry["evidence_strength"] == "model"


def test_handoff_splits_drill_artifacts_from_real_model_outputs(ctx):
    """演练夹具与真实模型产出**分开报**：前者按合同不得注册，处置建议完全相反。"""

    _write_generation_records(ctx.out / "generate" / "g1", attempt_dir="attempts/drill",
                              identity="genloop|drill", is_model_output=False,
                              evidence_kind="format_fixture")
    _write_generation_records(ctx.out / "generate" / "g2", attempt_dir="attempts/model",
                              identity="genloop|model", is_model_output=True,
                              evidence_kind="headless_model_reply")
    for key, request_id, attempt_dir in (("genloop|drill", "g1", "attempts/drill"),
                                         ("genloop|model", "g2", "attempts/model")):
        ctx.archive.upsert(key, registration="pending_registration",
                           source={"kind": "generated_attempt", "request_id": request_id,
                                   "attempt_dir": attempt_dir})
    handoff = search.build_handoff(ctx, pool={"candidates": []})
    kinds = {gap["kind"] for gap in handoff["gaps"]}
    assert {"pending_registration", "drill_not_registrable"} <= kinds
    pending = next(gap for gap in handoff["gaps"] if gap["kind"] == "pending_registration")
    drill = next(gap for gap in handoff["gaps"] if gap["kind"] == "drill_not_registrable")
    assert pending["items"] == ["genloop|model"], "待注册只放模型产出"
    assert drill["items"] == ["genloop|drill"]
    assert handoff["generated_pending_registration"] == ["genloop|model"]
    assert handoff["generated_not_registrable"] == ["genloop|drill"]
    assert "不得" in drill["impact"] and "无需注册" in drill["action"]


def test_handoff_markdown_shows_which_candidate_and_panel_a_gap_belongs_to(ctx):
    """缺口的定位字段必须进人读件：否则不同候选的同类缺口在交接件里长得一模一样。"""

    gap = {"kind": "cross_panel_level_conflict", "candidate": "meld_waiting_conditional",
           "level": "L2", "panels": ["panel-aaaa", "panel-bbbb"],
           "sources": ["/x/run", "/x/smoke"], "count": 2,
           "impact": "跨面板数字不得当同一批证据使用", "action": "先对齐面板"}
    handoff = search.build_handoff(ctx, pool={"candidates": []}, extra_gaps=[gap])
    text = search.render_handoff_md(handoff)
    assert "候选：meld_waiting_conditional" in text
    assert "等级：L2" in text
    assert "面板：panel-aaaa、panel-bbbb" in text



# --- 同一本账里再加候选：两个等级名都要能声明（步 id 唯一，撞名即"复用"） --------

def test_run_names_both_levels_so_a_second_candidate_gets_its_own_steps(tmp_path, monkeypatch):
    """台账按步 id 唯一：升级级不能写死 L2，否则第二级会撞上已完成的 screen:L2 而拿不到样本。"""

    payload = freeze_payload()
    payload["upgrade"] = {"slots": 2, "roots": 16, "seats": 2, "seed_base": 2026093000,
                          "root_prefix": "searchA-up-"}
    freeze_path = tmp_path / "freeze.json"
    freeze_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    pool_path = tmp_path / "pool.json"
    pool_path.write_text(json.dumps({"schema": search.POOL_SCHEMA,
                                     "candidates": [{"candidate": "a", "weights": {}}]}),
                         encoding="utf-8")
    monkeypatch.setattr(search, "step_admission", lambda ctx, entries, **kwargs: [
        {"candidate": item["candidate"], "weights": item.get("weights") or {},
         "status": "admitted", "identity": "id-" + item["candidate"],
         "registration": "registered"} for item in entries])
    fake = FakeScheduler(spent_tables=64, results={"id-a": stats(mean=6.0)})
    monkeypatch.setattr(search, "run_tool", fake)
    out = tmp_path / "out"
    rc = search.main(["run", "--freeze", str(freeze_path), "--out", str(out),
                      "--pool", str(pool_path), "--gate-records", str(GATE_DIR),
                      "--admission-corpus", str(CORPUS),
                      "--level-name", "L1b", "--upgrade-level-name", "L2b"])
    assert rc == 0
    ledger = json.loads((out / "ledger.json").read_text(encoding="utf-8"))
    steps = [item["step_id"] for item in ledger["reservations"]]
    assert steps == ["screen:L1b", "screen:L2b"], "两级都按声明命名，不与旧步撞 id"
    assert "screen:L1" not in steps and "screen:L2" not in steps
    assert ledger["accounts"]["search"]["spent"]["tables"] == 128


# --- 三条账目口径：各自有名字、互不相加（Lead 裁定） --------------------------

def test_handoff_names_three_accounting_calibres_and_never_merges_them(ctx):
    """预算执行 / 开发期消耗 / 机时总消耗是**三件不同的东西**：人读件必须分清名字与限定语。"""

    reservation = ctx.ledger.reserve(step_id="screen:L1", account="search",
                                     amounts={"tables": 64}, note="t")
    ctx.ledger.settle(reservation, status="ok", actual={"tables": 64})
    develop = {"schema": "sitin-development-spend/1",
               "totals": {"tables": 498, "output_tokens": 57853},
               "totals_label": "开发期消耗合计（登记不追认）", "items": []}
    handoff = search.build_handoff(ctx, pool={"candidates": []}, development_spend=develop)
    calibres = handoff["accounting_calibres"]
    assert calibres["budget_execution"]["spent_tables"] == 64
    assert calibres["budget_execution"]["limit_tables"] == 384
    assert calibres["development_spend"]["tables"] == 498
    assert calibres["machine_time_total"]["tables"] == 562, "机时总量 = 预算执行 + 开发期消耗"
    assert "非预算口径" in calibres["machine_time_total"]["definition"]
    assert "不进任何上限分母" in calibres["machine_time_total"]["definition"]
    assert "不可用作预算执行复算" in calibres["machine_time_total"]["definition"]
    text = search.render_handoff_md(handoff)
    assert "三条账目口径" in text
    assert "**开发期消耗合计（登记不追认）**" in text, "不得再叫\"任务级合计\""
    assert "**562** 桌 = 64（预算执行口径）+ 498（开发期消耗口径）" in text


def test_handoff_without_development_spend_has_no_machine_time_total(ctx):
    """没有开发期消耗登记时，机时总量**留空**而不是当成 0——0 与"没有这个量"是两件事。"""

    handoff = search.build_handoff(ctx, pool={"candidates": []})
    assert handoff["accounting_calibres"]["development_spend"]["tables"] is None
    assert handoff["accounting_calibres"]["machine_time_total"]["tables"] is None


# --- 「越过已报告超限」：逐条点名 + 留痕，且不动任何已结算数字 ------------------

def _overrun_step(ctx, *, step_id: str = "screen:L1b", reserved: float = 100.0,
                  charged: float = 472.8):
    reservation = ctx.ledger.reserve(step_id=step_id, account="search",
                                     amounts={"tables": 64, "wall_clock_sec": reserved},
                                     note="t")
    ctx.ledger.settle(reservation, status="ok",
                      actual={"tables": 64, "wall_clock_sec": charged})
    return reservation


def _reservation_row(ctx, step_id: str):
    ledger = json.loads((ctx.out / "ledger.json").read_text(encoding="utf-8"))
    return next(row for row in ledger["reservations"] if row["step_id"] == step_id)


def test_overrun_gate_stops_unless_that_exact_step_is_named(ctx):
    """未点名 ⇒ 照旧停；点名 ⇒ 仅该步可继续；**charged 与 overrun 标记均不变**。"""

    _overrun_step(ctx)
    before = _reservation_row(ctx, "screen:L1b")
    assert before["overrun"] is True
    assert search._overrun_gate(ctx, "screen:L1b", ()) is not None, "未点名必须照旧停止"
    assert search._overrun_gate(ctx, "screen:L2b", ("screen:L1b",)) is None, \
        "点名别的步不得影响本步（也不得凭空放行）"
    assert search._overrun_gate(ctx, "screen:L1b", ("screen:L1b",)) is None, "点名后放行"
    after = _reservation_row(ctx, "screen:L1b")
    assert after["charged"] == before["charged"], "charged 一个数都不能被改"
    assert after["overrun"] is True, "overrun 标记不得被清（停止已经生效过，事实要留着）"
    assert after["status"] == "settled", "不得重结"


def test_overrun_acknowledgement_is_never_a_wildcard_and_reaches_the_handoff(ctx):
    """点名必须是**逐条 step_id**：通配、空串、默认开启都不算数；记录必须进交接件。"""

    _overrun_step(ctx, charged=472.8)
    for fake in ("*", "screen:*", "screen:", "", "SCREEN:L1B"):
        assert search._overrun_gate(ctx, "screen:L1b", (fake,)) is not None, \
            "只有逐字相同的 step_id 才算点名：{0!r}".format(fake)
    assert search._load_overrun_acknowledgements(ctx.out) == [], "放行前不得留下任何记录"
    assert search._overrun_gate(ctx, "screen:L1b", ("screen:L1b",)) is None
    rows = search._load_overrun_acknowledgements(ctx.out)
    assert len(rows) == 1 and rows[0]["step_id"] == "screen:L1b"
    assert search._overrun_gate(ctx, "screen:L1b", ("screen:L1b",)) is None, "重复点名仍放行"
    assert len(search._load_overrun_acknowledgements(ctx.out)) == 1, \
        "同一步同一数值只留一条，重复运行不刷屏"
    assert rows[0]["axes"]["wall_clock_sec"] == {"预留": 100.0, "实结": 472.8}, \
        "例外记录必须含超限数值与触发维度"
    assert rows[0]["unchanged"] == {"charged": True, "overrun_flag": True, "resettlement": False}
    gap = search._overrun_acknowledgement_gap(rows[0])
    assert gap["kind"] == "overrun_acknowledged_exception"
    assert "472.8" in gap["impact"] and "wall_clock_sec" in gap["impact"]
    text = search.render_handoff_md(search.build_handoff(
        ctx, pool={"candidates": []}, extra_gaps=[gap]))
    assert "已披露例外" in text and "超限维度：wall_clock_sec" in text
    assert "实结：472.8" in text


# --- 门禁记录分散在多处：一次读多处、逐字段比对、不一致即冲突 --------------------

MELD_WEIGHTS = {"adj.beta": 20.0}


def _copy_gate_record(source: Path, target_dir: Path, **overrides) -> Path:
    """把一份真实门禁记录复制到另一个目录（可选改几个字段），用于构造多目录场景。"""

    payload = json.loads(source.read_text(encoding="utf-8"))
    payload.update(overrides)
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / source.name
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


@pytest.mark.skipif(not CORPUS.is_file(), reason="准入语料不可用")
def test_admission_reads_the_same_candidate_from_several_directories(ctx, tmp_path: Path):
    """记录由各包落在自己的目录里：消费侧必须能**同时读多处**，否则会把已准入读成"没有记录"。"""

    record = _copy_gate_record(_project_file(_PROJECT_ROOT, GATE_DIR / "gates-meld_opportunity_cost.json"), tmp_path / "a")
    empty = tmp_path / "b"
    empty.mkdir()
    results = search.step_admission(ctx, [{"candidate": "meld_opportunity_cost",
                                           "weights": MELD_WEIGHTS}],
                                    gate_dirs=[tmp_path / "a", empty],
                                    admission_corpus=CORPUS)
    item = results[0]
    assert item["status"] == "admitted"
    assert item["record_path"] == str(record), "必须给出**真实记录路径**"
    assert item["record_paths"] == [str(record)]
    assert item["gate_dirs"] == [str(tmp_path / "a"), str(empty)]


@pytest.mark.skipif(not CORPUS.is_file(), reason="准入语料不可用")
def test_admission_flags_field_level_conflicts_across_directories(ctx, tmp_path: Path):
    """两处都有同一身份同一语料的记录、字段却不同 ⇒ **记冲突**，不按目录顺序任选其一。"""

    source = _project_file(_PROJECT_ROOT, GATE_DIR / "gates-meld_opportunity_cost.json")
    _copy_gate_record(source, tmp_path / "a")
    _copy_gate_record(source, tmp_path / "b", failed=["合成冲突：两处记录不一致"])
    item = search.step_admission(ctx, [{"candidate": "meld_opportunity_cost",
                                        "weights": MELD_WEIGHTS}],
                                 gate_dirs=[tmp_path / "a", tmp_path / "b"],
                                 admission_corpus=CORPUS)[0]
    assert item["status"] == "conflicting_gate_records", "fail-closed：不任选其一"
    assert any("failed" in problem for problem in item["differences"])
    assert len(item["record_paths"]) == 2


@pytest.mark.skipif(not CORPUS.is_file(), reason="准入语料不可用")
def test_freeze_rescan_corrects_a_stale_gate_status_and_says_so(ctx, tmp_path: Path):
    """报告侧重扫把陈旧的 gate 字段改成真实值 + 记录路径，并逐条披露改了谁。"""

    record = _copy_gate_record(_project_file(_PROJECT_ROOT, GATE_DIR / "gates-meld_opportunity_cost.json"), tmp_path / "later")
    ctx.archive.upsert("meld_opportunity_cost", candidate="meld_opportunity_cost",
                       weights=MELD_WEIGHTS, registration="registered",
                       gate={"status": "no_admission_record"},
                       levels={"L1": {"statistics": stats(mean=6.0),
                                      "classification": search.describe_statistics(stats(mean=6.0))}})
    handoff = search.build_handoff(ctx, pool={"candidates": []},
                                   gate_dirs=[tmp_path / "later"], admission_corpus=CORPUS)
    candidate = next(item for item in handoff["candidates"]
                     if item["candidate"] == "meld_opportunity_cost")
    assert candidate["gate"]["status"] == "admitted", "机器字段不得继续写假话"
    assert candidate["gate"]["record_path"] == str(record)
    assert "rescanned_by" in candidate["gate"], "重扫来源必须可辨"
    assert handoff["gate_rescan"]["changed"] == [{"candidate": "meld_opportunity_cost",
                                                  "before": "no_admission_record",
                                                  "after": "admitted",
                                                  "record_paths": [str(record)]}]
    text = search.render_handoff_md(handoff)
    assert "准入重扫" in text and "no_admission_record → admitted" in text
    # 档案（历史事实）不被改写：重扫只动报告。
    assert ctx.archive.records["meld_opportunity_cost"].gate["status"] == "no_admission_record"


# --- 吞吐诊断账：臂由冻结件声明、按实结算、CPU 与墙钟分开读 ----------------------

class FakeMatches:
    """完整桌赛替身：只写"评估工具本该写出的" results.jsonl，不真跑。"""

    def __init__(self, *, rows_per_arm: int, seconds: float = 20.0) -> None:
        self.rows_per_arm = rows_per_arm
        self.seconds = seconds
        self.commands: List[List[str]] = []

    def __call__(self, name: str, command, *, cwd, timeout_sec, dry_run: bool = False):
        rendered = [str(item) for item in command]
        self.commands.append(rendered)
        arm_dir = Path(rendered[rendered.index("--out") + 1])
        arm_dir.mkdir(parents=True, exist_ok=True)
        (arm_dir / "results.jsonl").write_text(
            "".join("{{\"row\": {0}}}\n".format(index) for index in range(self.rows_per_arm)),
            encoding="utf-8")
        return search.ToolRun(name=name, command=tuple(rendered), returncode=0, timed_out=False,
                              elapsed_sec=self.seconds, signals_sent=(), stdout="{}", stderr="")


def _throughput_freeze_payload(tmp_path: Path, *, tables: int = 8) -> Dict[str, Any]:
    payload = freeze_payload()
    payload["accounts"]["search"]["tables"] = tables
    payload["wall_estimate_sec_per_table"] = 8.0
    experiment = tmp_path / "experiment.json"
    experiment.write_text(json.dumps({"tournament_config": {"rules": {"ruleset_version": "old"}}}),
                          encoding="utf-8")
    payload["throughput_probe"] = {
        "purpose": "throughput_diagnosis",
        "base_experiment": str(experiment),
        "tables_per_arm": 4,
        "arms": {"historical-config": {},
                 "current-ruleset": {"tournament_config.rules.ruleset_version": "new"}},
        "archived_reference": {"cpu_seconds_per_table": 1.468},
    }
    return payload


def test_throughput_probe_settles_actual_tables_and_reports_cpu_separately(tmp_path, monkeypatch):
    """诊断账按**实跑桌数**结算，并把 CPU 秒/桌与墙钟秒/桌分开报（历史口径是 CPU 秒）。"""

    payload = _throughput_freeze_payload(tmp_path)
    freeze_path = tmp_path / "freeze.json"
    freeze_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(search, "run_tool", FakeMatches(rows_per_arm=4, seconds=20.0))
    ticks = iter([100.0, 112.0, 112.0, 126.0])
    monkeypatch.setattr(search, "children_cpu_seconds", lambda: next(ticks))
    out = tmp_path / "throughput"
    rc = search.main(["throughput-probe", "--freeze", str(freeze_path), "--out", str(out)])
    assert rc == 0
    report = json.loads((out / "throughput-probe.json").read_text(encoding="utf-8"))
    first, second = report["measurements"]
    assert (first["tables"], first["cpu_seconds_per_table"]) == (4, 3.0)
    assert (second["tables"], second["cpu_seconds_per_table"]) == (4, 3.5)
    assert first["wall_seconds_per_table"] == 5.0
    assert report["comparison"]["reference_cpu_seconds_per_table"] == 1.468
    assert report["comparison"]["arms"][0]["ratio_vs_reference"] == round(3.0 / 1.468, 4)
    assert report["purpose"] == "throughput_diagnosis"
    ledger = json.loads((out / "ledger.json").read_text(encoding="utf-8"))
    assert ledger["accounts"]["search"]["spent"]["tables"] == 8, "两臂 4+4 桌按实结算"
    assert ledger["accounts"]["search"]["remaining"]["tables"] == 0


def test_throughput_probe_refuses_to_run_without_a_frozen_plan(tmp_path):
    """臂与基准必须**先冻结**：冻结件没有 throughput_probe 段时直接拒绝，不猜着跑。"""

    freeze_path = tmp_path / "freeze.json"
    freeze_path.write_text(json.dumps(freeze_payload(), ensure_ascii=False), encoding="utf-8")
    with pytest.raises(SystemExit, match="throughput_probe"):
        search.main(["throughput-probe", "--freeze", str(freeze_path),
                     "--out", str(tmp_path / "out")])
def test_dry_run_release_does_not_lock_the_step_for_the_real_run(tmp_path: Path, freeze):
    """released 的定义是"确实没执行、预算已退回"⇒ 它不该把该步**永久锁死**。"""

    out = tmp_path / "run"
    out.mkdir()
    ledger = search.SearchLedger.load(out / "ledger.json", freeze)
    rehearsal = ledger.reserve(step_id="probe:throughput", account="search",
                               amounts={"tables": 8}, note="dry-run 预演")
    ledger.release(rehearsal, reason="dry-run：只做计划，不执行")
    assert ledger.remaining("search")["tables"] == 384, "释放后预算必须回到原值"
    real = ledger.reserve(step_id="probe:throughput", account="search",
                          amounts={"tables": 8}, note="真实执行")
    assert real["reservation_id"].endswith("#2")
    ledger.settle(real, status="ok", actual={"tables": 8})
    assert ledger.spent("search")["tables"] == 8, "只有真实那次计费"
    with pytest.raises(ValueError, match="已有预留记录"):
        ledger.reserve(step_id="probe:throughput", account="search",
                       amounts={"tables": 8}, note="第三次：已结算的步不得重复预留")


def test_zero_charge_settlement_does_not_lock_the_step(tmp_path: Path, freeze):
    """结算后四维全 0 = "跑是跑了、什么也没产出"（如启动即崩）⇒ 不得锁死该步、也不得按满额计费。"""

    out = tmp_path / "run"
    out.mkdir()
    ledger = search.SearchLedger.load(out / "ledger.json", freeze)
    crashed = ledger.reserve(step_id="probe:throughput", account="search",
                             amounts={"tables": 12}, note="第一次：臂进程启动即崩")
    ledger.settle(crashed, status="failed",
                  actual={"tables": 0, "wall_clock_sec": 0.05}, note="0 桌产出")
    assert ledger.spent("search")["tables"] == 0, "崩了不等于花了 12 桌"
    retry = ledger.reserve(step_id="probe:throughput", account="search",
                           amounts={"tables": 8}, note="重试")
    ledger.settle(retry, status="ok", actual={"tables": 8})
    assert ledger.spent("search")["tables"] == 8, "只有真正跑出桌数那次计费"




# --- F2：墙钟基准 fail-closed（缺声明即报错；旧件走显式一次性处置） -----------------

def _freeze_without_wall_basis(tmp_path: Path) -> Path:
    payload = freeze_payload()
    payload.pop("wall_estimate_sec_per_table", None)
    path = tmp_path / "legacy-freeze.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def test_wall_basis_is_fail_closed_without_a_declared_measured_value(tmp_path: Path):
    """缺 wall_estimate_sec_per_table ⇒ **报错**，绝不静默回落到已作废的历史常数。"""

    freeze = search.Freeze.load(_freeze_without_wall_basis(tmp_path))
    with pytest.raises(search.WallBasisMissing, match="不得静默回落"):
        freeze.wall_basis()
    basis = freeze.wall_basis("该件产生于 fail-closed 规则之前（复现历史运行）")
    assert basis["source"] == "legacy-declared"
    assert basis["seconds_per_table"] == search.LEGACY_SECONDS_PER_TABLE
    assert "非实测" in basis["value_note"]
    declared = search.Freeze.load(Path(tmp_path / "ok.json")) if False else None
    assert declared is None


def test_declared_wall_basis_wins_and_is_not_flagged_as_legacy(tmp_path: Path):
    """冻结件声明了实测值 ⇒ 用声明值，且**不算**遗留例外。"""

    payload = freeze_payload()
    payload["wall_estimate_sec_per_table"] = 9.5
    path = tmp_path / "freeze.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    basis = search.Freeze.load(path).wall_basis()
    assert basis["source"] == "declared" and basis["seconds_per_table"] == 9.5


def test_legacy_wall_basis_needs_an_explicit_declaration_and_lands_in_the_handoff(tmp_path: Path):
    """旧冻结件只有被**显式点名**才能继续，且必须作为已披露例外进交接件。"""

    path = _freeze_without_wall_basis(tmp_path)
    out = tmp_path / "run"
    out.mkdir()
    (out / "freeze-path.txt").write_text(str(path) + "\n", encoding="utf-8")
    freeze = search.Freeze.load(path)
    search.Archive.load(out / "archive.json", freeze).save()
    search.RunState.load(out / "state.json").save()
    with pytest.raises(SystemExit, match="不得静默回落"):
        search.main(["freeze", "--freeze", str(path), "--out", str(out)])
    rc = search.main(["freeze", "--freeze", str(path), "--out", str(out),
                      "--legacy-wall-basis", "该件产生于 fail-closed 规则之前"])
    assert rc == 0
    handoff = json.loads((out / "handoff.json").read_text(encoding="utf-8"))
    kinds = {gap["kind"] for gap in handoff["gaps"]}
    assert "wall_basis_legacy_exception" in kinds
    row = handoff["wall_basis"][0]
    assert row["source"] == "legacy-declared" and row["reason"]
    text = search.render_handoff_md(handoff)
    assert "墙钟基准" in text and "一次性的历史口径声明" in text


# --- F1：准入重扫必须同步重算 verdict，旧理由降级为快照 ---------------------------

@pytest.mark.skipif(not CORPUS.is_file(), reason="准入语料不可用")
def test_gate_rescan_recomputes_verdict_and_keeps_the_old_reason_as_a_snapshot(ctx, tmp_path: Path):
    """gate 改成 admitted 后，verdict_reason 不得继续说"准入未通过"（同一对象两件相反的话）。"""

    record = _copy_gate_record(_project_file(_PROJECT_ROOT, GATE_DIR / "gates-meld_opportunity_cost.json"), tmp_path / "later")
    ctx.archive.upsert("meld_opportunity_cost", candidate="meld_opportunity_cost",
                       weights=MELD_WEIGHTS, registration="registered",
                       gate={"status": "no_admission_record"},
                       verdict="blocked", verdict_reason="准入未通过：no_admission_record")
    handoff = search.build_handoff(ctx, pool={"candidates": []},
                                   gate_dirs=[tmp_path / "later"], admission_corpus=CORPUS)
    item = next(row for row in handoff["candidates"]
                if row["candidate"] == "meld_opportunity_cost")
    assert item["gate"]["status"] == "admitted"
    assert item["gate"]["record_path"] == str(record)
    assert item["verdict"] == "pending", "已准入不再是 blocked"
    assert "准入未通过" not in item["verdict_reason"], "不得再对下游说两件相反的事"
    assert "准入已通过" in item["verdict_reason"]
    assert "与准入结论无关" in item["verdict_reason"]
    assert "准入未通过：no_admission_record" in item["verdict_reason_superseded"]
    assert "运行当时快照" in item["verdict_reason_superseded"]
    pointer = item["gate_rescan_pointer"]
    assert pointer["changed"] is True
    assert pointer["previous_gate_status"] == "no_admission_record"
    assert pointer["record_paths"] == [str(record)], "R2：机器指针要指回真实记录"
    text = search.render_handoff_md(handoff)
    assert "旧理由已被准入重扫更正" in text


# --- F3：候选计数与吞吐由数据渲染，不写死 -----------------------------------------

def test_stage_policy_and_throughput_are_rendered_from_data(ctx):
    """写死的"三个候选/7.9 秒/桌"必须改成从档案与账本渲染（否则同行 4 个 promoted 自相矛盾）。"""

    for index, mean in enumerate((1.0, -0.5, -9.0)):
        record = ctx.archive.upsert("cand-{0}".format(index), candidate="cand-{0}".format(index),
                                    identity="id-{0}".format(index), registration="registered",
                                    gate={"status": "admitted"})
        record.levels["L1"] = {"statistics": stats(mean=mean),
                               "classification": search.describe_statistics(stats(mean=mean))}
    reservation = ctx.ledger.reserve(step_id="screen:L1", account="search",
                                     amounts={"tables": 64, "wall_clock_sec": 600.0}, note="t")
    ctx.ledger.settle(reservation, status="ok",
                      actual={"tables": 64, "wall_clock_sec": 512.0})
    handoff = search.build_handoff(ctx, pool={"candidates": []})
    current = handoff["stage_policy"]["current"]
    # F10：resolved_negative（-9.0 > MDE 2.9）是**方向可分辨**的，绝不能从结论句里消失。
    assert handoff["stage_policy"]["resolved_negative_at_level"] == ["cand-2@L1"], \
        "负向可分辨必须单列，不得并入「未分辨」"
    assert "cand-2@L1=resolved_negative" in current
    assert "不构成追加依据" in current
    assert "resolved_positive" in handoff["stage_policy"]["rule"]
    assert "三个候选" not in current
    assert handoff["stage_policy"]["throughput_measured_seconds_per_table"] == 8.0
    note = handoff["stage_policy"]["throughput_note"]
    assert "8.00 秒/桌" in note and "7.9" not in note
    assert "已作废" in note


# --- F11/F12/F13：留痕、复用先于取基准、纯读预检 -------------------------------

def test_reused_step_never_resolves_the_wall_basis(tmp_path: Path, freeze):
    """F12：已完成的步**不消费**墙钟基准——否则历史账连"什么都不做"的复跑都会报错。"""

    legacy = search.Freeze.load(_freeze_without_wall_basis(tmp_path))
    out = tmp_path / "run"
    out.mkdir()
    ctx = search.SearchContext(out=out, freeze=legacy,
                               ledger=search.SearchLedger.load(out / "ledger.json", legacy),
                               archive=search.Archive.load(out / "archive.json", legacy),
                               state=search.RunState.load(out / "state.json"),
                               steps_path=out / "steps.jsonl")  # 注意：没有 legacy_wall_basis
    ctx.state.mark("screen:L1")
    outcome = search.step_screen(ctx, level="L1", entries=[entry("a", "id-a")],
                                 panel=panel_of(freeze),
                                 spec={"name": "L1", "roots": 16, "seats": 2,
                                       "keep_fraction": 0.5},
                                 gate_dir=GATE_DIR, admission_corpus=CORPUS, timeout_sec=60.0)
    assert outcome["status"] == "reused", "该步已完成 ⇒ 复用，不需要墙钟基准"
    assert ctx.ledger.spent("search")["tables"] == 0


def test_legacy_wall_basis_is_recorded_on_the_freeze_path_too(tmp_path: Path):
    """F11：freeze 路径也要写文件级留痕（此前只有交接件缺口 + 人读件，全仓 0 命中记录文件）。"""

    path = _freeze_without_wall_basis(tmp_path)
    out = tmp_path / "run"
    out.mkdir()
    (out / "freeze-path.txt").write_text(str(path) + "\n", encoding="utf-8")
    freeze = search.Freeze.load(path)
    search.Archive.load(out / "archive.json", freeze).save()
    search.RunState.load(out / "state.json").save()
    rc = search.main(["freeze", "--freeze", str(path), "--out", str(out),
                      "--legacy-wall-basis", "该件产生于 fail-closed 规则之前"])
    assert rc == 0
    rows = search._read_jsonl(out / search.WALL_BASIS_FILE)
    assert len(rows) == 1, "文件级留痕必须存在"
    assert rows[0]["source"] == "legacy-declared" and rows[0]["reason"]
    assert rows[0]["freeze_sha256"] == freeze.sha256
    steps = (out / "steps.jsonl").read_text(encoding="utf-8")
    assert "legacy-declared" in steps, "steps.jsonl 也要有这一条"
    assert "不得用于新报价" in rows[0]["boundary"]


def test_run_prechecks_the_wall_basis_before_any_side_effect(tmp_path: Path, monkeypatch):
    """F13：缺声明且未显式处置 ⇒ **在建产物之前**就报错（不写 freeze-path、不动档案、不花钱）。"""

    path = _freeze_without_wall_basis(tmp_path)
    out = tmp_path / "out"
    pool_path = tmp_path / "pool.json"
    pool_path.write_text(json.dumps({"schema": search.POOL_SCHEMA,
                                     "candidates": [{"candidate": "a", "weights": {}}]}),
                         encoding="utf-8")
    monkeypatch.setattr(search, "step_admission", lambda ctx, entries, **kwargs: [
        {"candidate": item["candidate"], "weights": item.get("weights") or {},
         "status": "admitted", "identity": "id-" + item["candidate"],
         "registration": "registered"} for item in entries])
    with pytest.raises(search.WallBasisMissing, match="不得静默回落"):
        search.main(["run", "--freeze", str(path), "--out", str(out),
                     "--pool", str(pool_path), "--gate-records", str(tmp_path),
                     "--admission-corpus", str(tmp_path / "corpus.jsonl")])
    assert not (out / "freeze-path.txt").exists(), "预检必须先于任何产物写入"
    assert not (out / "archive.json").exists()


# --- wv12：入口级回归（此前 80 项覆盖不到"命令入口"这一层） ---------------------

@pytest.mark.skipif(not CORPUS.is_file(), reason="准入语料不可用")
def test_verify_wiring_entry_runs_in_dry_run(tmp_path: Path, monkeypatch):
    """⑤a 入口必须能跑：曾经把 legacy_wall_basis 塞进 bool() ⇒ 照抄命令即 TypeError。"""

    payload = freeze_payload()
    payload["verify"] = {
        "candidate": "meld_opportunity_cost",
        "weights_base": {"adj.beta": 20.0},
        "weights_injected": {"adj.beta": 8.0},
        "wiring": {"corpus": str(CORPUS),
                   "registrations": str(_project_file(_PROJECT_ROOT, GATE_DIR / "candidate-registrations.json")),
                   "weights_zero": {"adj.beta": 0.0}, "wall_clock_sec": 60},
    }
    freeze_path = tmp_path / "freeze.json"
    freeze_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    calls: List[List[str]] = []

    def fake_run(name, command, *, cwd, timeout_sec, dry_run=False):
        rendered = [str(item) for item in command]
        calls.append(rendered)
        return search.ToolRun(name=name, command=tuple(rendered), returncode=0, timed_out=False,
                              elapsed_sec=0.5, signals_sent=(), stdout="{}", stderr="")

    monkeypatch.setattr(search, "run_tool", fake_run)
    rc = search.main(["verify-wiring", "--freeze", str(freeze_path),
                      "--out", str(tmp_path / "wiring"), "--dry-run"])
    assert rc == 0, "入口必须跑得动（旧实现会 TypeError: bool() takes no keyword arguments）"
    assert calls, "dry-run 也要把三条臂的计划渲染出来"


@pytest.mark.skipif(not CORPUS.is_file(), reason="准入语料不可用")
def test_verify_injection_entry_runs_in_dry_run(tmp_path: Path, monkeypatch):
    """⑤b 入口同样必须能跑（同一处 bool() 缺陷的另一半）。"""

    payload = freeze_payload()
    payload["verify"] = {"candidate": "meld_opportunity_cost",
                         "weights_base": {"adj.beta": 20.0},
                         "weights_injected": {"adj.beta": 8.0},
                         "roots": 2, "seats": 1, "seed_base": 1, "root_prefix": "v-"}
    freeze_path = tmp_path / "freeze.json"
    freeze_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(search, "run_tool", lambda *a, **k: search.ToolRun(
        name="x", command=(), returncode=0, timed_out=False, elapsed_sec=0.1,
        signals_sent=(), stdout="{}", stderr=""))
    rc = search.main(["verify-injection", "--freeze", str(freeze_path),
                      "--out", str(tmp_path / "verify"), "--dry-run"])
    assert rc == 0


def test_reused_steps_do_not_trip_the_overrun_gate(tmp_path: Path, monkeypatch):
    """wv12 ③：本账五步全 overrun，靠"reused 跳过超限门"才复跑得动 ⇒ 必须有回归钉住。"""

    payload = freeze_payload()
    payload["upgrade"] = {"slots": 0, "roots": 8, "seats": 2, "seed_base": 1, "root_prefix": "u-"}
    freeze_path = tmp_path / "freeze.json"
    freeze_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    freeze = search.Freeze.load(freeze_path)
    out = tmp_path / "out"
    out.mkdir()
    ledger = search.SearchLedger.load(out / "ledger.json", freeze)
    reservation = ledger.reserve(step_id="screen:L1", account="search",
                                 amounts={"tables": 64, "wall_clock_sec": 10.0}, note="t")
    ledger.settle(reservation, status="ok", actual={"tables": 64, "wall_clock_sec": 99.0})
    assert ledger.reservations[0]["overrun"] is True
    state = search.RunState.load(out / "state.json")
    state.mark("screen:L1")
    state.save()
    pool_path = tmp_path / "pool.json"
    pool_path.write_text(json.dumps({"schema": search.POOL_SCHEMA,
                                     "candidates": [{"candidate": "a", "weights": {}}]}),
                         encoding="utf-8")
    monkeypatch.setattr(search, "step_admission", lambda ctx, entries, **kwargs: [
        {"candidate": item["candidate"], "weights": item.get("weights") or {},
         "status": "admitted", "identity": "id-" + item["candidate"],
         "registration": "registered"} for item in entries])
    monkeypatch.setattr(search, "step_promote", lambda ctx, **kwargs: {
        "step_id": "promote:L1", "level": kwargs["level"], "promoted": [], "exploration": [],
        "survivors": [], "unresolved": [], "eliminated": []})
    rc = search.main(["run", "--freeze", str(freeze_path), "--out", str(out),
                      "--pool", str(pool_path), "--gate-records", str(GATE_DIR),
                      "--admission-corpus", str(CORPUS)])
    assert rc == 0, "已完成的步复用 ⇒ 不该被历史超限挡住"
    assert json.loads((out / "state.json").read_text(encoding="utf-8"))["stop_reason"] is None


def test_freeze_writes_back_recomputed_classifications(tmp_path: Path):
    """wv12 ③：档案与交接件对同一等级不得给出不同标签——重算结果写回，旧值留快照。"""

    freeze_path = tmp_path / "freeze.json"
    freeze_path.write_text(json.dumps(freeze_payload(), ensure_ascii=False), encoding="utf-8")
    freeze = search.Freeze.load(freeze_path)
    out = tmp_path / "run"
    out.mkdir()
    (out / "freeze-path.txt").write_text(str(freeze_path) + "\n", encoding="utf-8")
    archive = search.Archive.load(out / "archive.json", freeze)
    record = archive.upsert("cand", candidate="cand", identity="id-cand",
                            registration="registered", gate={"status": "admitted"})
    zero = stats(mean=0.0, mde=0.0, sd_root=0.0)
    # 模拟"旧函数写下的陈旧标签"：零差异观测被记成 unresolved。
    record.levels["L2x"] = {"statistics": zero,
                            "classification": {"state": "unresolved", "reason": "陈旧标签"}}
    archive.save()
    search.RunState.load(out / "state.json").save()
    rc = search.main(["freeze", "--freeze", str(freeze_path), "--out", str(out)])
    assert rc == 0
    written = json.loads((out / "archive.json").read_text(encoding="utf-8"))
    level = written["records"]["cand"]["levels"]["L2x"]
    assert level["classification"]["state"] == "no_observed_difference", "写回到档案"
    assert level["classification_superseded"]["state"] == "unresolved", "旧值留快照"
    handoff = json.loads((out / "handoff.json").read_text(encoding="utf-8"))
    assert handoff["classification_sync"], "写回动作要进交接件披露"
    assert handoff["classification_sync"][0]["before"] == "unresolved"


# --- wv16：机时口径环境（R8）、消费契约（R2）、单臂等价判定 ---------------------

def _probe_report(path: Path, *, implementation: str, arm: str = "a", result_ids=("r1", "r2")) -> Path:
    """造一份最小的 throughput-probe 报告（含后端信息），供交接件与环境块使用。"""

    native = {"native_loaded": implementation != "python",
              "backend": {"implementation": implementation, "semantics_version": "v1",
                          "fallback_reason": None, "native_path": "…/_grouped_native.so"}}
    path.write_text(json.dumps({
        "schema": "sitin-throughput-probe/1", "generated_at_utc": "2026-09-16T00:00:00Z",
        "measurements": [{"arm": arm, "tables": len(result_ids),
                          "wall_seconds_per_table": 2.0, "cpu_seconds_per_table": 1.5,
                          "instructions_per_table": 28277811636, "native": native}]},
        ensure_ascii=False), encoding="utf-8")
    return path


def test_handoff_splits_throughput_environment_by_backend(ctx, tmp_path: Path):
    """R8：交接件必须把"启用内核后"与"启用前"的秒/桌**分开渲染**，并给出报价规则。"""

    post = _probe_report(tmp_path / "post.json", implementation="c_grouped", arm="post")
    pre = _probe_report(tmp_path / "pre.json", implementation="python", arm="pre")
    handoff = search.build_handoff(ctx, pool={"candidates": []}, throughput_env=[post, pre])
    env = handoff["throughput_environment"]
    assert env["status"] == "measured"
    assert [row["arm"] for row in env["post_kernel_measurements"]] == ["post"]
    assert [row["arm"] for row in env["pre_kernel_measurements"]] == ["pre"]
    assert "不得与新值混用" in env["quote_rule"]
    text = search.render_handoff_md(handoff)
    assert "机时口径环境" in text and "启用内核后" in text and "启用内核前" in text
    assert "报价规则" in text


def test_handoff_without_throughput_env_says_unmeasured(ctx):
    """没挂机时产物 ⇒ 明确写 unmeasured 并给出指令，**不假装有数**。"""

    handoff = search.build_handoff(ctx, pool={"candidates": []})
    env = handoff["throughput_environment"]
    assert env["status"] == "unmeasured" and env["instruction"]
    assert "consumption_contract" in handoff
    assert "handoff.json" in handoff["consumption_contract"]["authoritative"]


def test_single_arm_equivalence_run_is_judged_identical(tmp_path: Path, monkeypatch, freeze):
    """单臂也要能判"逐字节相同"：旧逻辑要求两臂互比，会把只有一臂的运行判成"存在不一致"。"""

    payload = freeze_payload()
    payload["throughput_probe"] = {
        "purpose": "x", "base_experiment": str(tmp_path / "exp.json"), "tables_per_arm": 2,
        "arms": {"only": {}},
        "archived_reference": {"cpu_seconds_per_table": 1.468},
    }
    (tmp_path / "exp.json").write_text("{}", encoding="utf-8")
    freeze_path = tmp_path / "freeze.json"
    freeze_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    recorded = tmp_path / "recorded.jsonl"
    recorded.write_text('{"result_id": "r1"}\n{"result_id": "r2"}\n', encoding="utf-8")
    plan = {"purpose": "x", "base_experiment": str(tmp_path / "exp.json"), "tables_per_arm": 2,
            "arms": {"only": {}}, "compare": {"against": str(recorded), "key": "result_id"}}
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")

    class FakeOne:
        def __call__(self, name, command, *, cwd, timeout_sec, dry_run=False):
            rendered = [str(item) for item in command]
            arm_dir = Path(rendered[rendered.index("--out") + 1])
            arm_dir.mkdir(parents=True, exist_ok=True)
            (arm_dir / "results.jsonl").write_text('{"result_id": "r1"}\n{"result_id": "r2"}\n',
                                                   encoding="utf-8")
            return search.ToolRun(name=name, command=tuple(rendered), returncode=0,
                                  timed_out=False, elapsed_sec=1.0, signals_sent=(),
                                  stdout="{}", stderr="")

    monkeypatch.setattr(search, "run_tool", FakeOne())
    out = tmp_path / "out"
    rc = search.main(["throughput-probe", "--freeze", str(freeze_path), "--out", str(out),
                      "--plan", str(plan_path), "--step", "s1"])
    assert rc == 0
    report = json.loads((out / "throughput-probe.json").read_text(encoding="utf-8"))
    assert report["equivalence"]["verdict"] == "全部逐字节相同"
    assert report["equivalence"]["cross_arm_comparison"] is False


def test_probe_reports_are_named_per_step_so_a_later_step_cannot_overwrite(tmp_path: Path, monkeypatch):
    """wv16：同一本账跑两步时，旧实现两步都写 throughput-probe.json ⇒ 前一步的实测被静默覆盖。"""

    payload = freeze_payload()
    payload["throughput_probe"] = {"purpose": "x", "base_experiment": str(tmp_path / "exp.json"),
                                   "tables_per_arm": 1, "arms": {"a": {}}}
    (tmp_path / "exp.json").write_text("{}", encoding="utf-8")
    freeze_path = tmp_path / "freeze.json"
    freeze_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    class Fake:
        def __call__(self, name, command, *, cwd, timeout_sec, dry_run=False):
            rendered = [str(item) for item in command]
            arm_dir = Path(rendered[rendered.index("--out") + 1])
            arm_dir.mkdir(parents=True, exist_ok=True)
            (arm_dir / "results.jsonl").write_text('{"result_id": "r1"}\n', encoding="utf-8")
            return search.ToolRun(name=name, command=tuple(rendered), returncode=0,
                                  timed_out=False, elapsed_sec=1.0, signals_sent=(),
                                  stdout="{}", stderr="")

    monkeypatch.setattr(search, "run_tool", Fake())
    out = tmp_path / "out"
    for step in ("first", "second"):
        rc = search.main(["throughput-probe", "--freeze", str(freeze_path), "--out", str(out),
                          "--step", step])
        assert rc == 0
    assert (out / "throughput-probe-first.json").is_file(), "第一步的报告必须留档"
    assert (out / "throughput-probe-second.json").is_file()
    assert (out / "throughput-probe.json").is_file(), "latest 仍然写，供最后一步的读者使用"


# --- wv18：更正件的安全边界、三态后端、口径指针、指针字段说真话 -----------------

def test_corrections_refuse_a_foreign_target_and_a_stale_before(tmp_path: Path):
    """F1：更正件只能改它声明的文件，且只在 before 仍然匹配时改——绝不覆盖未来写入的正确值。"""

    corrections = tmp_path / 'REPORT-CORRECTIONS.json'
    declared = tmp_path / 'declared.json'
    declared.write_text(json.dumps({'value': False}), encoding='utf-8')
    sha = search.sha256_text(declared.read_text(encoding='utf-8'))

    def write_corrections(**fields):
        payload = {'schema': 'sitin-report-corrections/1', 'target': 'declared.json',
                   'corrections': [{'path': ['value'], 'before': False, 'after': True,
                                    'reason': 'x'}]}
        payload.update(fields)
        corrections.write_text(json.dumps(payload, ensure_ascii=False), encoding='utf-8')

    # ① 外来制品：target 不符 ⇒ 一个字段都不许动
    other = tmp_path / 'other.json'
    other.write_text(json.dumps({'value': False}), encoding='utf-8')
    write_corrections(target_sha256=sha)
    foreign = search._apply_report_corrections(other)
    assert foreign['applied'] == 0
    assert 'target 不匹配' in (foreign['error'] or '')
    assert foreign['data']['value'] is False, '同目录的其它产物一个字段都不许动'
    # ② 缺 target_sha256（钉不住制品）⇒ 拒改：分不清'旧写法记错'与'内核真回退'
    write_corrections()
    unpinned = search._apply_report_corrections(declared)
    assert unpinned['applied'] == 0 and 'target_sha256' in (unpinned['error'] or '')
    assert unpinned['data']['value'] is False
    # ③ 哈希不符 ⇒ 目标不是被更正的那一份
    write_corrections(target_sha256='0' * 64)
    wrong = search._apply_report_corrections(declared)
    assert wrong['applied'] == 0 and '不符' in (wrong['error'] or '')
    assert wrong['data']['value'] is False
    # ④ 哈希与 before 都相符 ⇒ 应用（确实还是那个错值）
    write_corrections(target_sha256=sha)
    applied = search._apply_report_corrections(declared)
    assert applied['applied'] == 1 and applied['data']['value'] is True
    # ⑤ 制品已如实写 True（新报告写对了）⇒ before 不匹配，跳过并登记
    declared.write_text(json.dumps({'value': True}), encoding='utf-8')
    write_corrections(target_sha256=search.sha256_text(declared.read_text(encoding='utf-8')))
    again = search._apply_report_corrections(declared)
    assert again['applied'] == 0
    assert again['data']['value'] is True, 'before 不匹配必须跳过'
    assert again['skipped'], '跳过要登记，不许静默'


def test_missing_backend_evidence_is_unknown_not_pre_kernel(ctx, tmp_path: Path):
    """F2：没有后端块的测量是**证据缺失**，不能翻成"启用前口径"。"""

    report = tmp_path / "r.json"
    report.write_text(json.dumps({"schema": "sitin-throughput-probe/1", "measurements": [
        {"arm": "no-backend", "tables": 4, "wall_seconds_per_table": 2.0, "native": {}}]},
        ensure_ascii=False), encoding="utf-8")
    env = search.throughput_environment([report])
    assert env["pre_kernel_measurements"] == [], "缺证据不得进 pre"
    assert [row["arm"] for row in env["unknown_backend_measurements"]] == ["no-backend"]
    assert env["counts"]["unknown"] == 1 and env["counts"]["post"] == 0
    assert "不得报价" in env["quote_rule"]
    assert "证据缺失" in env["quote_rule"]


def test_pre_kernel_references_are_pointers_not_copies(tmp_path: Path):
    """F3：pre=[] 不等于"没有旧值"——必须给出旧口径的**指针**（文件 + 字段名）。"""

    legacy = tmp_path / "legacy-freeze.json"
    legacy.write_text(json.dumps({"wall_estimate_sec_per_table": 1.58125}), encoding="utf-8")
    refs = search._pre_kernel_references([legacy])
    assert refs[0]["field"] == "wall_estimate_sec_per_table"
    assert refs[0]["value"] == 1.58125
    assert "作废" in refs[0]["note"]
    env = search.throughput_environment([], pre_kernel_refs=refs)
    assert env["pre_kernel_references"] == refs
    assert env["status"] == "unmeasured" and "不得报价" in env["quote_rule"]


def test_gate_rescan_pointer_says_whether_the_status_actually_changed(ctx, tmp_path: Path):
    """F5：6 条里只有 1 条真被取代 ⇒ 字段必须带 changed，不能一律叫 superseded。"""

    ctx.archive.upsert("untouched", candidate="untouched", weights={}, identity="id-u",
                       registration="registered", gate={"status": "no_gate_records"})
    handoff = search.build_handoff(ctx, pool={"candidates": []},
                                   gate_dirs=[tmp_path / "empty"],
                                   admission_corpus=None)
    item = next(row for row in handoff["candidates"] if row["candidate"] == "untouched")
    pointer = item.get("gate_rescan_pointer")
    if pointer is not None:
        assert "previous_gate_status" in pointer and "changed" in pointer
        assert pointer["changed"] == (pointer["previous_gate_status"] != item["gate"]["status"])  # 如实反映前后是否不同


# --- wv22：更正件不得崩、后端块类型守卫、第三态进人读面、活体端到端 --------------

def test_backend_classification_only_accepts_string_implementations(ctx, tmp_path: Path):
    """F2-a/b：非字符串 implementation 与非映射 native/backend 一律 unknown（不 str() 兜底、不 AttributeError）。"""

    cases = [
        ({"implementation": 123}, "unknown"),
        ({"implementation": True}, "unknown"),
        ({"implementation": "Python"}, "pre"),
        ({"implementation": "C_GROUPED"}, "post"),
    ]
    for backend, expected in cases:
        report = tmp_path / "r.json"
        report.write_text(json.dumps({"schema": "sitin-throughput-probe/1", "measurements": [
            {"arm": "a", "tables": 1, "native": {"backend": backend}}]}, ensure_ascii=False),
            encoding="utf-8")
        env = search.throughput_environment([report])
        got = ("post" if env["counts"]["post"] else ("pre" if env["counts"]["pre"] else "unknown"))
        assert got == expected, "{0} ⇒ {1}（应为 {2}）".format(backend, got, expected)
    for shape in ({"native": "c_grouped"}, {"native": {"backend": ["c_grouped"]}}):
        report = tmp_path / "r2.json"
        report.write_text(json.dumps({"schema": "sitin-throughput-probe/1", "measurements": [
            {"arm": "b", "tables": 1, "native": shape["native"]}]}, ensure_ascii=False),
            encoding="utf-8")
        env = search.throughput_environment([report])
        assert env["counts"]["unknown"] == 1, "非映射形状不得抛异常、也不得判 post/pre"


def test_native_loaded_is_kept_as_non_classifying_evidence(ctx, tmp_path: Path):
    """F2-c：native_loaded=true 是可靠正证据，保留下来但**不参与**口径判定。"""

    report = tmp_path / "r.json"
    report.write_text(json.dumps({"schema": "sitin-throughput-probe/1", "measurements": [
        {"arm": "kernel-arm", "tables": 1, "native": {"native_loaded": True}}]}, ensure_ascii=False),
        encoding="utf-8")
    env = search.throughput_environment([report])
    assert env["counts"] == {"post": 0, "pre": 0, "unknown": 1}, "不得用 native_loaded 提升口径"
    row = env["unknown_backend_measurements"][0]
    assert row["native_loaded_observed"] is True, "正证据不得静默丢弃"
    assert "不参与口径判定" in row["native_loaded_note"]


def test_unknown_state_is_rendered_in_the_human_readable_handoff(ctx, tmp_path: Path):
    """L1：有 unknown 行时，人读件必须出现第三张表与计数，否则读者看不出"证据缺失"。"""

    report = tmp_path / "r.json"
    report.write_text(json.dumps({"schema": "sitin-throughput-probe/1", "measurements": [
        {"arm": "no-backend", "tables": 1, "native": {}}]}, ensure_ascii=False), encoding="utf-8")
    handoff = search.build_handoff(ctx, pool={"candidates": []}, throughput_env=[report])
    text = search.render_handoff_md(handoff)
    assert "unknown=1" in text
    assert "证据缺失" in text and "不得当作启用前" in text


def test_corrections_never_crash_and_handle_missing_leaf_keys(tmp_path: Path):
    """F1-a：leaf 缺失（before=null 的补记语义）、下标越界、类型不符都不得抛异常。"""

    report = tmp_path / "probe.json"
    report.write_text(json.dumps({"measurements": [{"native": {"native_loaded": False}}]}),
                      encoding="utf-8")
    corrections = tmp_path / "REPORT-CORRECTIONS.json"
    corrections.write_text(json.dumps({
        "schema": "sitin-report-corrections/1", "target": "probe.json",
        "target_sha256": search.sha256_text(report.read_text(encoding="utf-8")),
        "corrections": [
            {"path": ["measurements", 0, "native", "backend"], "before": None, "after": {"implementation": "c_grouped"}, "reason": "补记"},
            {"path": ["measurements", 9, "native"], "before": None, "after": 1, "reason": "越界"},
            {"path": ["measurements", "x"], "before": None, "after": 1, "reason": "类型不符"},
        ]}, ensure_ascii=False), encoding="utf-8")
    outcome = search._apply_report_corrections(report)
    assert outcome["applied"] == 1, "缺失 leaf 按 None 比较 ⇒ 命中 before=null 的补记语义"
    assert outcome["data"]["measurements"][0]["native"]["backend"] == {"implementation": "c_grouped"}
    assert len(outcome["skipped"]) == 2, "越界与类型不符记 skipped，不抛异常"
# --- wv24：更正件写坏形状不得崩、空串实现名归 unknown、来源账目与补记留痕 --------------

def test_corrections_refuse_broken_shapes_instead_of_crashing(tmp_path: Path):
    """F1-a′：更正件顶层/条目清单/条目本身写坏形状时一律 error 或 skipped，绝不抛异常穿出。"""

    report = tmp_path / "probe.json"
    report.write_text(json.dumps({"measurements": [{"native": {}}]}), encoding="utf-8")
    sha = search.sha256_text(report.read_text(encoding="utf-8"))

    def write_corrections(payload):
        (tmp_path / "REPORT-CORRECTIONS.json").write_text(
            json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    base = {"schema": "sitin-report-corrections/1", "target": "probe.json",
            "target_sha256": sha}
    # ① 顶层不是对象：数组 / 字符串 / 数字 —— 旧代码在 payload.get 上抛 AttributeError
    for shape in ([], "oops", 42):
        write_corrections(shape)
        outcome = search._apply_report_corrections(report)      # 必须不抛
        assert outcome["applied"] == 0, shape
        assert "顶层不是对象" in (outcome["error"] or ""), shape
        assert outcome["data"]["measurements"][0]["native"] == {}, "形状不符时一个字段都不许动"
    # ② corrections 不是数组：对象（旧代码会迭代出字符串键 ⇒ AttributeError）、字符串（迭代出单字符）
    for shape in ({"a": 1}, "oops"):
        write_corrections(dict(base, corrections=shape))
        outcome = search._apply_report_corrections(report)
        assert outcome["applied"] == 0 and "不是数组" in (outcome["error"] or ""), shape
    # ③ 条目不是对象：字符串 / 数字 / null ⇒ 记 skipped，不抛、也不升级成 error
    write_corrections(dict(base, corrections=["oops", 42, None]))
    outcome = search._apply_report_corrections(report)
    assert outcome["error"] is None, "条目写坏是条目级问题，不该升级成整件 error"
    assert outcome["applied"] == 0
    assert len(outcome["skipped"]) == 3, "三条坏条目都要登记，不许静默丢"
    assert all("不是对象" in item["why"] for item in outcome["skipped"])


def test_corrections_never_silently_drop_entries_without_a_path(tmp_path: Path):
    """F1-a′：缺 path / 空 path / path 不是键数组都必须留痕（applied=0 且 skipped 有记录）。"""

    report = tmp_path / "probe.json"
    report.write_text(json.dumps({"measurements": [{"native": {}}]}), encoding="utf-8")
    (tmp_path / "REPORT-CORRECTIONS.json").write_text(json.dumps({
        "schema": "sitin-report-corrections/1", "target": "probe.json",
        "target_sha256": search.sha256_text(report.read_text(encoding="utf-8")),
        "corrections": [
            {"before": None, "after": 1, "reason": "缺 path"},
            {"path": [], "before": None, "after": 1, "reason": "空 path"},
            {"path": "measurements.0.native", "before": None, "after": 1, "reason": "path 是字符串"},
        ]}, ensure_ascii=False), encoding="utf-8")
    outcome = search._apply_report_corrections(report)
    assert outcome["applied"] == 0 and outcome["error"] is None
    assert len(outcome["skipped"]) == 3, "三条都不得静默丢弃（旧写法 applied=0、skipped=[]、error=None）"
    assert outcome["data"]["measurements"][0]["native"] == {}, "字符串 path 不得被逐字符当成键来改"


def test_blank_implementation_is_unknown_not_post(ctx, tmp_path: Path):
    """F2-a′：空串/纯空白 implementation 一律 unknown，且该行 implementation 不得自相矛盾。"""

    def env_for(raw):
        report = tmp_path / "r.json"
        report.write_text(json.dumps({"schema": "sitin-throughput-probe/1", "measurements": [
            {"arm": "a", "tables": 1, "native": {"backend": {"implementation": raw}}}]},
            ensure_ascii=False), encoding="utf-8")
        return search.throughput_environment([report])

    for raw in ("", " ", "\t", "\n  "):
        env = env_for(raw)
        assert env["counts"] == {"post": 0, "pre": 0, "unknown": 1}, repr(raw)
        row = env["unknown_backend_measurements"][0]
        assert row["implementation"] is None, "空串不得当作实现名：post 臂 implementation=null 是自相矛盾行"
    # 空白包裹的真实实现名：去空白只用于判定，实现名照原样留着
    assert env_for(" python ")["counts"]["pre"] == 1
    assert env_for("  C_GROUPED  ")["counts"]["post"] == 1
    assert env_for("  C_GROUPED  ")["post_kernel_measurements"][0]["implementation"] == "  C_GROUPED  "
    # 明说"没有原生后端"的字面量同样是证据缺失，不得当成已启用内核
    for raw in ("none", "NULL", "Unknown"):
        assert env_for(raw)["counts"] == {"post": 0, "pre": 0, "unknown": 1}, raw


def test_environment_rows_carry_account_and_run_label(tmp_path: Path):
    """低项①：行内带来源账目/运行目录——多目录并挂时读者能分辨这条臂算在哪本账上。"""

    run_dir = tmp_path / "run-throughput-post-kernel-v2"
    run_dir.mkdir()
    (run_dir / "ledger.json").write_text(json.dumps({
        "accounts": {"search": {}, "confirm": {}},
        "reservations": [{"account": "search", "step_id": "probe:timing"}]}),
        encoding="utf-8")
    report = run_dir / "throughput-probe-timing.json"
    report.write_text(json.dumps({"schema": "sitin-throughput-probe/1", "measurements": [
        {"arm": "a", "tables": 4, "native": {"backend": {"implementation": "c_grouped"}}}]},
        ensure_ascii=False), encoding="utf-8")
    row = search.throughput_environment([report])["post_kernel_measurements"][0]
    assert row["account"] == "search", "账目取实际被记账的账户，不是台账开着的账户清单"
    assert row["run_label"] == "run-throughput-post-kernel-v2"
    # 台账里没有 reservations（旧账本）时**不许**把"开着的账户"写成被记账账户（wv26 低项①）
    (run_dir / "ledger.json").write_text(
        json.dumps({"accounts": {"search": {}, "confirm": {}}}), encoding="utf-8")
    fallback = search.throughput_environment([report])["post_kernel_measurements"][0]
    assert fallback["account"] is None and fallback["account_basis"] == "opened"
    assert fallback["opened_accounts"] == ["confirm", "search"]
    # 没有台账目录时留 None（缺标签不等于缺测量），目录名仍然记下来
    loose = tmp_path / "loose" / "throughput-probe.json"
    loose.parent.mkdir()
    loose.write_text(json.dumps({"schema": "sitin-throughput-probe/1", "measurements": [
        {"arm": "b", "tables": 1, "native": {"backend": {"implementation": "c_grouped"}}}]},
        ensure_ascii=False), encoding="utf-8")
    row2 = search.throughput_environment([loose])["post_kernel_measurements"][0]
    assert row2["account"] is None and row2["run_label"] == "loose"


def test_corrections_trace_names_paths_and_marks_backfilled_fields(ctx, tmp_path: Path):
    """低项②：applied_paths 给出被改字段与"补记/更正"之分，并在人读件里点明。"""

    report = tmp_path / "throughput-probe.json"
    report.write_text(json.dumps({"measurements": [{"native": {"native_loaded": False}}]}),
                      encoding="utf-8")
    (tmp_path / "REPORT-CORRECTIONS.json").write_text(json.dumps({
        "schema": "sitin-report-corrections/1", "target": "throughput-probe.json",
        "target_sha256": search.sha256_text(report.read_text(encoding="utf-8")),
        "corrections": [
            {"path": ["measurements", 0, "native", "native_loaded"],
             "before": False, "after": True, "reason": "更正"},
            {"path": ["measurements", 0, "native", "backend"],
             "before": None, "after": {"implementation": "c_grouped"}, "reason": "补记"},
        ]}, ensure_ascii=False), encoding="utf-8")
    env = search.throughput_environment([report])
    seen = env["corrections_applied"][0]
    assert seen["applied"] == 2
    kinds = {item["path"]: item["kind"] for item in seen["applied_paths"]}
    assert kinds == {"measurements.0.native.native_loaded": "更正",
                     "measurements.0.native.backend": "补记"}, "键不存在 ⇒ 补记；键存在 ⇒ 更正"
    assert env["post_kernel_measurements"][0]["implementation"] == "c_grouped"
    handoff = search.build_handoff(ctx, pool={"candidates": []}, throughput_env=[report])
    text = search.render_handoff_md(handoff)
    assert "更正留痕" in text and "**补记**" in text, "人读件必须点明哪些字段是补记出来的"
    assert "measurements.0.native.backend" in text


# --- wv26：真实回退名 python_grouped、整体回退、更正取值渲染、账目依据 ------------------

def test_python_grouped_fallback_is_pre_not_post(ctx, tmp_path: Path):
    """F2-新：python_grouped 是 _standard.py 里**真实的回退实现名**，必须判 pre 而不是 post。"""

    def env_for(raw, fallback_reason=None):
        report = tmp_path / "r.json"
        backend = {"implementation": raw, "fallback_reason": fallback_reason}
        report.write_text(json.dumps({"schema": "sitin-throughput-probe/1", "measurements": [
            {"arm": "fallback-arm", "tables": 4, "native": {"native_loaded": False,
                                                            "backend": backend}}]},
            ensure_ascii=False), encoding="utf-8")
        return search.throughput_environment([report])

    for raw in ("python_grouped", "Python_Grouped", "  python_grouped  ", "python",
                "Python", "PYTHON_REFERENCE"):
        env = env_for(raw, "ImportError: no native")
        assert env["counts"] == {"post": 0, "pre": 1, "unknown": 0}, repr(raw)
        assert env["pre_kernel_measurements"][0]["implementation"] == raw, "实现名照原样留着"
        assert env["post_kernel_measurements"] == [], "回退臂绝不许进报价面"
    # 原生名仍然是 post（别把整支判反）
    assert env_for("c_grouped")["counts"]["post"] == 1


def test_writer_records_a_real_fallback_as_native_loaded_false():
    """F2-新（写者侧）：native 块由同一三态判据推出，回退时不得写 native_loaded=true。"""

    fallback = search._native_block_from_backend_info(
        {"implementation": "python_grouped", "semantics_version": "v1",
         "fallback_reason": "ImportError: no native"}, {"native_path": None})
    assert fallback["native_loaded"] is False, "回退写 true 会与同一行的 fallback_reason 自相矛盾"
    assert fallback["native_path"] is None, "既有字段要保留"
    assert search._native_block_from_backend_info(
        {"implementation": "c_grouped"})["native_loaded"] is True
    for unknown in ({"implementation": None}, {"implementation": ""}, {}):
        assert search._native_block_from_backend_info(unknown)["native_loaded"] is None, unknown


def test_corrections_roll_back_a_partial_application(ctx, tmp_path: Path):
    """F1-a″：好条目已改、坏条目随后异常 ⇒ 必须整体回退，不许留"半更正"的权威面。"""

    report = tmp_path / "throughput-probe.json"
    report.write_text(json.dumps({"measurements": [
        {"arm": "a", "native": {"native_loaded": False}}]}), encoding="utf-8")
    (tmp_path / "REPORT-CORRECTIONS.json").write_text(json.dumps({
        "schema": "sitin-report-corrections/1", "target": "throughput-probe.json",
        "target_sha256": search.sha256_text(report.read_text(encoding="utf-8")),
        "corrections": [
            {"path": ["measurements", 0, "native", "native_loaded"],
             "before": False, "after": True, "reason": "好条目"},
            # 不可哈希的键 ⇒ 遍历时抛 TypeError（旧写法此时已把上一条改进了 data）
            {"path": [{"unhashable": True}], "before": None, "after": 1, "reason": "坏条目"},
        ]}, ensure_ascii=False), encoding="utf-8")
    outcome = search._apply_report_corrections(report)
    assert outcome["error"], "坏条目必须记 error"
    assert outcome["rolled_back"] is True
    assert outcome["applied"] == 0, "整体回退后不许再报 applied"
    assert outcome["data"]["measurements"][0]["native"]["native_loaded"] is False, "产物必须是原始内容"
    assert [item["path"] for item in outcome["discarded_applied_paths"]] == [
        "measurements.0.native.native_loaded"], "被回退的改动员不许静默丢"
    # 调用方（throughput_environment）读到的也必须是原始数据
    env = search.throughput_environment([report])
    assert env["counts"] == {"post": 0, "pre": 0, "unknown": 1}
    assert env["corrections_applied"][0]["rolled_back"] is True


def test_correction_entries_render_booleans_as_json(ctx, tmp_path: Path):
    """F3-新：更正条目的 before/after 用 JSON 渲染——旧写法把 false/true 渲染成"原本没有该字段"。"""

    report = tmp_path / "throughput-probe.json"
    report.write_text(json.dumps({"measurements": [
        {"native": {"native_loaded": False}}]}), encoding="utf-8")
    (tmp_path / "REPORT-CORRECTIONS.json").write_text(json.dumps({
        "schema": "sitin-report-corrections/1", "target": "throughput-probe.json",
        "target_sha256": search.sha256_text(report.read_text(encoding="utf-8")),
        "corrections": [
            {"path": ["measurements", 0, "native", "native_loaded"],
             "before": False, "after": True, "reason": "更正"},
            {"path": ["measurements", 0, "native", "semantics_version"],
             "before": None, "after": "v1", "reason": "补记"},
        ]}, ensure_ascii=False), encoding="utf-8")
    text = search.render_handoff_md(
        search.build_handoff(ctx, pool={"candidates": []}, throughput_env=[report]))
    assert "false → true" in text, 'bool 必须按 JSON 渲染，否则会把更正说成补记'
    assert '（原本没有该字段） → "v1"' in text, '只有补记行才用"原本没有该字段"'
    assert "**更正**" in text and "**补记**" in text


def test_account_fallback_is_not_reported_as_a_charged_account(tmp_path: Path):
    """低项①：台账没有记账记录时，account 必须留空并给出 account_basis=opened。"""

    run_dir = tmp_path / "run-legacy"
    run_dir.mkdir()
    (run_dir / "ledger.json").write_text(
        json.dumps({"accounts": {"search": {}, "confirm": {}}}), encoding="utf-8")
    report = run_dir / "throughput-probe.json"
    report.write_text(json.dumps({"schema": "sitin-throughput-probe/1", "measurements": [
        {"arm": "a", "tables": 1, "native": {"backend": {"implementation": "c_grouped"}}}]},
        ensure_ascii=False), encoding="utf-8")
    row = search.throughput_environment([report])["post_kernel_measurements"][0]
    assert row["account"] is None, '开着的账户不等于"这笔机时记在谁头上"'
    assert row["account_basis"] == "opened" and row["opened_accounts"] == ["confirm", "search"]


def test_format_command_only_replaces_named_placeholders():
    rendered = search.format_command(
        ["{python}", "{tools_dir}/sitin_stage.py", "run", "--out", "{out}"],
        {"python": "py", "tools_dir": "/t", "out": "/o"})
    assert rendered == ["py", "/t/sitin_stage.py", "run", "--out", "/o"]

