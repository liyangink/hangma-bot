# -*- coding: utf-8 -*-
"""P7 专属测试（R7 修复批次）：A2 档案挑战刷新原子性（补根成功才换席）。

复审条目：R6-IMPLEMENTATION-REVIEW-2026-09-17 §4 A2（P1 级，违反 v4 §9.2）。
本文件只覆盖 P7 工作包（A2）；A3/A4 见 test_sitin_search_p8_behavior_schedule.py。

缺陷复述（复审纯数据反例，本文件以数据夹具逐字复现）：
  旧席 [ff4580, b59963] 加入挑战者 251268 后预重排为 [251268, ff4580]；
  刷新因"只有零个新根而非四根"失败，调用方**仍会保存新席**；
  换 --out 时只继承档案、未继承原正常通道 epoch，进一步绕过挑战。

覆盖（复审 §4 A2 验收四情形 + 成功提交 + 同根证据）：
  ① 刷新空集（校验异常）：保持原席与原 epoch；
  ② 部分完成（原席者缺新刷新根）：保持原席与原 epoch，结果暂存 pending；
  ③ 预算不足：保持原席与原 epoch，挑战者留在探索候选队列；
  ④ 新目录续接（换 --out）：epoch 与根台账随运行链继承，原席仍保持，
     早期有效候选不因迁移目录无声消失；
  ⑤ 全部参与者同根证据齐备 → 原子提交新 epoch，统一重排；
  ⑥ 挑战者缺旧根（阶段 1 未完成）→ 原席保持。

预算红线：全部为纯数据夹具（不含 mock 生成、不含桌赛、不调真实 LLM、
不消耗授权账目）。
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

import json
import sys
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))

import sitin_search as search  # noqa: E402
import sitin_archive as sa  # noqa: E402

# —— R6 实测身份（复审 §4 A2 反例原值，便于与试跑证据逐字对照）——
OLD_A = "ff45809206e103f3ff2dbd455700a16a49a111bdb8c2472560a1eb5d5a421b73"
OLD_B = "b59963f4dce4769631cc4ab800a1891d2417602cdd141dfce4d2660191fecbf9"
CHALLENGER = "251268662a6dd4ac5c083029ef2fb0de287754510892f037861f0d936814e5b1"

#: 通道核心根（epoch 1）与声明的新刷新批（4 根、H/M 各 2；§9.2）。
CORE_ROOTS = (("np-H-20260916-root01", "H"), ("np-H-20260916-root02", "H"),
              ("np-M-20260916-root01", "M"), ("np-M-20260916-root02", "M"))
REFRESH_ROOTS = (("np-H-20260917-root01", "H"), ("np-H-20260917-root02", "H"),
                 ("np-M-20260917-root01", "M"), ("np-M-20260917-root02", "M"))


def _sample(root, mix, cid, d):
    """一条双臂正常面板样本（点值 U）：候选 U=d、基线 U=0 → d_low=d。"""

    return {"source_root_id": root, "scenario": "normal", "opponent_mix": mix,
            "candidate_id": cid, "root_role": "core", "invalid": False,
            "cost": 1.0,
            "arms": {"baseline": {"candidate_id": search.AV_BASELINE_ID, "u": 0.0},
                     "candidate": {"candidate_id": cid, "u": float(d)}}}


def _samples(cid, roots, d):
    return [_sample(root, mix, cid, d) for root, mix in roots]


def _entry(cid, roots, d):
    """按样本构建档案条目（sort_value = 声明混合差值下界均值 = d）。"""

    return sa.build_archive_entry(cid, _samples(cid, roots, d), safety="PASS",
                                  min_roots=1)


def _epoch(channel, roots, epoch_no=1):
    return sa.build_channel_epoch(channel, [{"root_id": rid, "opponent_mix": mix}
                                            for rid, mix in roots],
                                  epoch_no=epoch_no)


def _write_json(path, payload):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                          encoding="utf-8")


def _read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _seed_archive_dir(archive_dir, *, archive, epoch):
    _write_json(Path(archive_dir) / "av-archive.json", archive)
    _write_json(Path(archive_dir) / "normal-epoch.json", epoch)
    _write_json(Path(archive_dir) / "normal-roots.json",
                {"schema": "sitin-av-normal-roots/1",
                 "roots": [{"root_id": rid, "opponent_mix": mix}
                           for rid, mix in CORE_ROOTS]})


def _state(run_root, *, cid=CHALLENGER, roots=CORE_ROOTS, d=-0.25,
           archive_in_path=None, iteration_no=2):
    """挑战者迭代状态（纯数据）：只有自然面板样本与身份，不含真实执行。"""

    iter_dir = Path(run_root) / "iterations" / "iter-{0:02d}".format(iteration_no)
    iter_dir.mkdir(parents=True, exist_ok=True)
    return {
        "schema": search.AV_ITERATION_STATE_SCHEMA,
        "run_id": "run-" + cid[:8],
        "iteration_no": iteration_no,
        "created_at_utc": "2026-09-17T00:00:00Z",
        "status": "SUMMARIZED",
        "step_history": [],
        "identity": {"candidate_id": cid, "run_id": "run-" + cid[:8]},
        "plan": {"operator": "i1", "predicate": "branch_open", "opponent": "H",
                 "prefix_source": "scripted_fixture", "natural_roots": 2,
                 "natural_seats": 1, "natural_opponents": ["H", "M"],
                 "panel_seed": 20260916,
                 "archive_in": {"source": "local" if archive_in_path is None
                                else "chain_committed",
                                "path": (str(archive_in_path)
                                         if archive_in_path is not None else None)}},
        "iter_dir": str(iter_dir),
        "conditional_result": {"samples": []},
        "natural_result": {"samples": _samples(cid, roots, d)},
    }


def _case(tmp_path, *, challenger_roots=CORE_ROOTS, d=-0.25,
          incumbent_extra_roots=(), chain=False):
    """搭一个"原席 + 挑战者"的档案目录；返回 (run_root, archive_dir, state)。"""

    archive = sa.update_archive([_entry(OLD_A, CORE_ROOTS + tuple(incumbent_extra_roots), -0.5),
                                 _entry(OLD_B, CORE_ROOTS + tuple(incumbent_extra_roots), -0.6)])
    assert archive["slots"]["overall"] == [OLD_A, OLD_B], archive["slots"]
    epoch = _epoch("normal", CORE_ROOTS, 1)
    if chain:
        # 换 --out：档案与 epoch 在前序运行目录里（新目录本地没有）。
        prev_root = Path(tmp_path) / "chain" / "iter-01"
        _seed_archive_dir(prev_root / "archive", archive=archive, epoch=epoch)
        run_root = Path(tmp_path) / "chain" / "iter-02"
        run_root.mkdir(parents=True, exist_ok=True)
        state = _state(run_root, roots=challenger_roots, d=d,
                       archive_in_path=prev_root / "archive" / "av-archive.json")
        return run_root, prev_root / "archive", state
    run_root = Path(tmp_path) / "run"
    archive_dir = run_root / "archive"
    _seed_archive_dir(archive_dir, archive=archive, epoch=epoch)
    state = _state(run_root, roots=challenger_roots, d=d)
    return run_root, archive_dir, state


def _seats_of(archive_dir):
    return _read_json(Path(archive_dir) / "av-archive.json")["slots"]


def _epoch_of(archive_dir):
    return _read_json(Path(archive_dir) / "normal-epoch.json")


# ---------------------------------------------------------------------------
# ① 刷新空集（校验异常）：保持原席与原 epoch
# ---------------------------------------------------------------------------


def test_a2_empty_refresh_batch_keeps_original_seats_and_epoch(tmp_path):
    """复审纯数据反例：挑战者缺"新刷新批"（0 根 ≠ 4 根）→ 校验异常 →
    原席 [OLD_A, OLD_B] 与原 epoch 1 必须保持，挑战者只进候选池/队列。"""

    run_root, archive_dir, state = _case(tmp_path)
    assert state["identity"]["candidate_id"] == CHALLENGER
    reranked = sa.update_archive(
        [_entry(OLD_A, CORE_ROOTS, -0.5), _entry(OLD_B, CORE_ROOTS, -0.6),
         _entry(CHALLENGER, CORE_ROOTS, -0.25)])
    # 判别力对照：不做事务保护时，纯重排会把挑战者直接顶到第一席。
    assert reranked["slots"]["overall"] == [CHALLENGER, OLD_A]

    outcome = search._av_commit_archive(state, run_root, attempt_refresh=True)

    assert _seats_of(archive_dir)["overall"] == [OLD_A, OLD_B]
    epoch = _epoch_of(archive_dir)
    assert epoch["epoch"] == 1
    assert [row["root_id"] for row in epoch["roots"]] == [r for r, _ in CORE_ROOTS]
    archive = _read_json(Path(archive_dir) / "av-archive.json")
    assert CHALLENGER in archive["entries"]  # 新候选只留在候选池
    assert CHALLENGER in archive["exploration_queue"]
    assert outcome["status"] in ("ARCHIVE_COMMITTED", "REFRESH_PENDING")
    assert (outcome.get("refresh") or {}).get("status") != "committed"


# ---------------------------------------------------------------------------
# ② 部分完成：保持原席与原 epoch，结果暂存 pending
# ---------------------------------------------------------------------------


def test_a2_partial_completion_keeps_original_seats_and_epoch(tmp_path):
    """挑战者补齐旧根且有望入席，但原席者缺声明的新刷新根 → pending_partial：
    原席、原 epoch 保持，新根证据只暂存 pending，不混新旧均值。"""

    challenger_roots = CORE_ROOTS + REFRESH_ROOTS
    run_root, archive_dir, state = _case(tmp_path, challenger_roots=challenger_roots)
    outcome = search._av_commit_archive(state, run_root, attempt_refresh=True)

    assert outcome["status"] == "REFRESH_PENDING"
    assert (outcome.get("refresh") or {}).get("status") == "pending_partial"
    assert _seats_of(archive_dir)["overall"] == [OLD_A, OLD_B]
    epoch = _epoch_of(archive_dir)
    assert epoch["epoch"] == 1
    assert [row["root_id"] for row in epoch["roots"]] == [r for r, _ in CORE_ROOTS]
    missing = (outcome["refresh"].get("missing") or {})
    assert set(missing) == {OLD_A, OLD_B}
    assert all(set(REFRESH_ROOTS_ROWS) <= set(rows) for rows in missing.values())


REFRESH_ROOTS_ROWS = [r for r, _ in REFRESH_ROOTS]


# ---------------------------------------------------------------------------
# ③ 预算不足：保持原席与原 epoch，挑战者留探索候选队列
# ---------------------------------------------------------------------------


def test_a2_budget_insufficient_keeps_original_seats_and_epoch(tmp_path):
    """补根预算为 0（不足）→ 原席与原 epoch 保持，挑战者留探索候选队列。"""

    challenger_roots = CORE_ROOTS + REFRESH_ROOTS
    run_root, archive_dir, state = _case(tmp_path, challenger_roots=challenger_roots)
    outcome = search._av_commit_archive(state, run_root, attempt_refresh=True,
                                        refresh_budget=0)

    assert (outcome.get("refresh") or {}).get("status") == "budget_insufficient"
    assert _seats_of(archive_dir)["overall"] == [OLD_A, OLD_B]
    epoch = _epoch_of(archive_dir)
    assert epoch["epoch"] == 1
    assert [row["root_id"] for row in epoch["roots"]] == [r for r, _ in CORE_ROOTS]
    archive = _read_json(Path(archive_dir) / "av-archive.json")
    assert CHALLENGER in archive["exploration_queue"]
    assert CHALLENGER in archive["entries"]


# ---------------------------------------------------------------------------
# ④ 新目录续接：epoch / 根台账随运行链继承，原席仍保持
# ---------------------------------------------------------------------------


def test_a2_new_out_dir_inherits_epoch_and_keeps_original_seats(tmp_path):
    """换 --out（新运行目录本地无档案/epoch）：epoch 与根台账按运行链继承，
    挑战者不得因此绕过挑战；早期有效候选仍在档案与候选池中。"""

    run_root, prev_archive_dir, state = _case(tmp_path, chain=True)
    assert not (run_root / "archive" / "normal-epoch.json").is_file()

    outcome = search._av_commit_archive(state, run_root, attempt_refresh=True)

    local = run_root / "archive"
    epoch = _epoch_of(local)                      # 继承并就地落盘（内容=原 epoch）
    assert epoch["epoch"] == 1
    assert [row["root_id"] for row in epoch["roots"]] == [r for r, _ in CORE_ROOTS]
    # 根台账同样继承（换目录不重置）。
    roots_ledger = _read_json(local / "normal-roots.json")
    assert {row["root_id"] for row in roots_ledger["roots"]} >= {r for r, _ in CORE_ROOTS}
    # 原席保持：挑战者虽在纯重排中第一，仍不得占席。
    assert _seats_of(local)["overall"] == [OLD_A, OLD_B]
    archive = _read_json(local / "av-archive.json")
    assert {OLD_A, OLD_B, CHALLENGER} <= set(archive["entries"])
    assert (outcome.get("refresh") or {}).get("status") != "committed"


# ---------------------------------------------------------------------------
# ⑤ 成功提交：同根证据齐备 → 新 epoch 统一重排
# ---------------------------------------------------------------------------


def test_a2_success_requires_all_participants_same_roots(tmp_path):
    """全部参与者（含原席者）在旧根＋新刷新根上齐备 → 原子提交新 epoch，
    统一重排；提交摘要里每个参与者 roots_missing 为空（同根证据）。"""

    roots = CORE_ROOTS + REFRESH_ROOTS
    run_root, archive_dir, state = _case(tmp_path, challenger_roots=roots,
                                         incumbent_extra_roots=REFRESH_ROOTS)
    outcome = search._av_commit_archive(state, run_root, attempt_refresh=True)

    assert (outcome.get("refresh") or {}).get("status") == "committed", outcome
    epoch = _epoch_of(archive_dir)
    assert epoch["epoch"] == 2
    assert [row["root_id"] for row in epoch["roots"]] == [r for r, _ in roots]
    summary = _read_json(Path(archive_dir) / "commit-summary.json")
    assert set(summary["participants"]) == {OLD_A, OLD_B, CHALLENGER}
    for cid, row in summary["participants"].items():
        assert row["roots_missing"] == [], (cid, row)
    archive = _read_json(Path(archive_dir) / "av-archive.json")
    assert archive["slots"]["overall"][0] == CHALLENGER
    # 提交后重排只由新根集统一产生（不是旧重排结果的残留）。
    assert set(archive["slots"]["overall"]) <= {OLD_A, OLD_B, CHALLENGER}


# ---------------------------------------------------------------------------
# ⑥ 挑战者缺旧根（阶段 1 未完成）→ 原席保持
# ---------------------------------------------------------------------------


def test_a2_challenger_missing_core_roots_keeps_original_seats(tmp_path):
    """挑战者只补了部分旧根（阶段 1 未完成）→ 不比较、不重排，原席原 epoch 保持。"""

    partial = CORE_ROOTS[:2]
    run_root, archive_dir, state = _case(tmp_path, challenger_roots=partial)
    outcome = search._av_commit_archive(state, run_root, attempt_refresh=True)

    assert outcome["status"] == "REFRESH_PENDING"
    assert (outcome.get("refresh") or {}).get("phase") == "phase1"
    assert _seats_of(archive_dir)["overall"] == [OLD_A, OLD_B]
    assert _epoch_of(archive_dir)["epoch"] == 1


# ---------------------------------------------------------------------------
# ⑦ 事务件：刷新结果可事后核对
# ---------------------------------------------------------------------------


def test_a2_channel_refresh_tx_records_baseline_and_outcome(tmp_path):
    """刷新事务件必须留下原 epoch、失败原因与基准席位，事后可核对。"""

    run_root, archive_dir, state = _case(tmp_path)
    outcome = search._av_commit_archive(state, run_root, attempt_refresh=True)
    tx_path = (Path(state["iter_dir"]) / "transactions"
               / search.AV_TX_FILES["channel_refresh"])
    tx = _read_json(tx_path)
    assert tx["old_epoch"]["epoch_no"] == 1
    assert [row for row in tx["old_epoch"]["roots"]] == [r for r, _ in CORE_ROOTS]
    assert tx["outcome"] == (outcome.get("refresh") or {}).get("status")
    assert tx["seats_before"] == [OLD_A, OLD_B]
    assert tx["seats_after"] == [OLD_A, OLD_B]


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
