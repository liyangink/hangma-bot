# -*- coding: utf-8 -*-
"""S3 专属测试（R8 修复轮）：A4 探索席仍被全部冻结（复审 §4 A4，P2 级）。

复审依据：R7-REPAIR-REREVIEW-2026-09-17 §4 A4（固定复审版本 bb954580）。
缺陷原文：「_kept 保席逻辑把**全部 slots 换回原席位**——包含探索席；成功挑战只更新
目标正常通道或家族通道」。纯数据反例：update_archive 已选出探索候选 C，但提交结果仍
为 []。后果：从**初始空探索席**开始，真正有新行为的候选也可能永远进不了探索父代
通道（next_generation_plan 的通道循环遇到空探索席会跳过它，M1 父代永远只来自整体席）。

修复要求（复审 §4 A4）：**只冻结需要同根挑战的通道**（正常通道与家族通道按各自事务
语义保原席）；**探索席按公共行为面板独立更新**，并与档案事务**一致提交**（同一份
av-archive.json 原子写，不另开旁路）。

**R9 计划 §13 A 项收紧（本文件同步改口径）**：探索席必须相对**提交后的在案席位**重算
——排除在案 overall 与四个家族席持有者，并用**这些持有者的行为签名摘要**做同行为去重
参考（实现唯一来源 sa.select_exploration_seat），再与冻结席位一次原子提交。旧口径
「探索席 == update_archive(entries) 的探索席」把"冻结的在案席位"与"候选池面板视角的
探索席"拼接提交：池内整体席与在案整体席不一致时，在案整体席持有者或其**同行为孪生**
会落进探索池并占探索席（父代与在案整体席行为相同）。因此本文件所有此类期望改为
`_assert_exploration_rebased_on_committed`（逐元素 + 排除集 + 去重参考集合的精确断言），
判据**未放宽**：不同签名可占探索席、同签名不可重复占、保席不冻结探索更新三条全部保留。

验收覆盖（本文件逐条实测）：
  ① 连续 ≥3 个**不同动作签名**的候选 → 探索席与探索父代可达（给出签名差异与父代来源）；
  ② 正常挑战失败时**原正常席位仍保持**（探索席更新不得破坏保席语义）；
  ③ 家族通道不受影响（家族席按同根挑战语义保原席；探索席独立更新）；
  ④ 同口径：行为签名沿用 P8 既有实现（_av_behavior_signature → 门禁
     sitin_model_admission.behavior_signature），本文件不另写一份签名；
  ⑤ 探索席的入选资格不被放开（无行为证据者仍不占探索席——"解冻"不等于"放宽门槛"）。

预算红线：纯数据夹具 + mock 生成 + 替身桌赛驱动/替身家族条件评价执行器（0 真实桌赛、
0 模型调用、0 真实授权消耗；账面照记便于核对）。
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

import itertools
import json
import re
import sys
import uuid
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))

import sitin_search as search  # noqa: E402
import sitin_archive as sa  # noqa: E402
import sitin_natural_panel as natural  # noqa: E402
from hangma_bot.policy import action_value_seeds as seeds  # noqa: E402
from hangma_bot.policy.action_value_seeds import EFFICIENCY_SEED  # noqa: E402

#: 批次 7 授权令牌 + 账户额度（替身执行：0 真实桌赛，账面照记）。
TOKEN = {"authorized": True, "batch": 7,
         "budgets": {"tokens_input": 100000, "tokens_output": 200000,
                     "tables_full": 256, "tables_partial": 64,
                     "prefix_generation": 64}}

#: 正常通道 epoch 的两个根（H/M 各一）：纯数据反例里挑战者必须已持有这两个根。
H_ROOT = ("np-H-11-root01", "H")
M_ROOT = ("np-M-11-root01", "M")
EPOCH_ROOTS = [{"root_id": H_ROOT[0], "opponent_mix": "H",
                "usage": "development_core"},
               {"root_id": M_ROOT[0], "opponent_mix": "M",
                "usage": "development_core"}]

_UNKNOWN_LINE = ('results.append({"action_key": action["action_key"], '
                 '"score": 0.0, "trace": trace})')
_PASS_WHEN_UNKNOWN_LINE = (
    'results.append({"action_key": action["action_key"], '
    '"score": (1.0 if action["action_key"] == "pass" else 0.0), "trace": trace})')
_SHANTEN_NEG = ("SHANTEN_WEIGHT = 3.0", "SHANTEN_WEIGHT = -3.0")

#: **行为不同**的候选源码变体（公共行为面板上的首选动作确实不同，见 §1 实测：
#: 八个冻结窗口里只有 route_combo / unknown_missing 有多动作，故差异落在这两窗）：
#:   base                     → route_combo=discard:1w、unknown_missing=discard:3b
#:   shanten_neg              → route_combo=discard:2b（该窗评分权重取反）
#:   pass_when_unknown        → unknown_missing=pass（无事实窗的缺省偏好改变）
#:   shanten_neg_pass_unknown → route_combo=discard:2b 且 unknown_missing=pass（两处合并）
BEHAVIOR_EDITS = {
    "base": (),
    "shanten_neg": (_SHANTEN_NEG,),
    "pass_when_unknown": ((_UNKNOWN_LINE, _PASS_WHEN_UNKNOWN_LINE),),
    "shanten_neg_pass_unknown": (_SHANTEN_NEG,
                                 (_UNKNOWN_LINE, _PASS_WHEN_UNKNOWN_LINE)),
}
BEHAVIOR_KINDS = tuple(BEHAVIOR_EDITS)


# ---------------------------------------------------------------------------
# 夹具助手（形状与 P8/test_sitin_search_p8_behavior_schedule.py 同源）
# ---------------------------------------------------------------------------


def _sig(*actions, missing=()):
    """行为签名（P8 落档形状）：冻结窗口上的首选动作 + 未知掩码。"""

    return {"windows": [
        {"window_id": "w{0}".format(i),
         "action_key": (None if i in missing else action),
         "missing": i in missing}
        for i, action in enumerate(actions)]}


def _sig_actions(signature):
    return {row["window_id"]: row["action_key"]
            for row in (signature or {}).get("windows") or ()}


def _sig_diff(left, right):
    """两份签名的逐窗差异：{窗口: (左首选, 右首选)}（只列不同的窗口）。"""

    a, b = _sig_actions(left), _sig_actions(right)
    return {key: (a.get(key), b.get(key)) for key in sorted(set(a) | set(b))
            if a.get(key) != b.get(key)}


def _sample(root, mix, cid, d, *, scenario="normal", cost=1.0):
    """一条双臂样本（点值 U）：候选 U=d、基线 U=0。"""

    return {"source_root_id": root, "scenario": scenario, "opponent_mix": mix,
            "candidate_id": cid, "root_role": "core", "invalid": False,
            "cost": cost,
            "arms": {"baseline": {"candidate_id": search.AV_BASELINE_ID, "u": 0.0},
                     "candidate": {"candidate_id": cid, "u": float(d)}}}


def _normal(cid, roots, d=0.5):
    """正常面板样本：roots = [(root_id, mix)]。"""

    return [_sample(root, mix, cid, d) for root, mix in roots]


def _entry(cid, d, signature, *, roots=(H_ROOT, M_ROOT)):
    return sa.build_archive_entry(cid, _normal(cid, roots, d), safety="PASS",
                                  min_roots=1, behavior_signature=signature)


def _committed_exclusion_set(archive):
    """提交后在案席位的**排除集**（overall + 四家族席；探索席自身不算）。"""

    return sorted({cid for channel in ("overall",) + tuple(sa.FAMILIES)
                   for cid in (archive["slots"].get(channel) or [])})


def _assert_exploration_rebased_on_committed(archive, *, expect=None):
    """探索席口径的**精确集合断言**（R9 计划 §13 A 项；不是"非空"或"数量大于零"）。

    逐元素对拍四件事：
      ① 探索席 == sa.select_exploration_seat(entries, 在案席位)["slots"]——输入是
         **提交后的在案席位**，不是候选池面板重排出的席位（后者只是池内视角）；
      ② 探索席 ∩ 在案席位（overall + 四家族席）= ∅：一个候选不得兼任整体/家族席；
      ③ 探索席成员的**行为签名摘要** ∉ 在案席持有者摘要集合：同签名不重复占名额；
      ④ selection_report.exploration 的排除集 / 去重参考集合 / 同签名被排除者与
         复算一致（报告与席位同源，不留下"报告说 A、席位是 B"的错账）。
    """

    entries = archive["entries"]
    expected = sa.select_exploration_seat(list(entries.values()), archive["slots"])
    seat = list(archive["slots"]["exploration"])
    assert seat == expected["slots"], (seat, expected["slots"])
    if expect is not None:
        assert seat == list(expect), (seat, expect)
    seated = _committed_exclusion_set(archive)
    assert not (set(seat) & set(seated)), (seat, seated)
    holder_digests = {sa.behavior_signature_digest(entries[cid]["behavior_signature"])
                      for cid in seated}
    member_digests = {sa.behavior_signature_digest(entries[cid]["behavior_signature"])
                      for cid in seat}
    assert not (member_digests & holder_digests), (member_digests, holder_digests)
    report = (archive.get("selection_report") or {}).get("exploration") or {}
    assert sorted(report.get("excluded_seated") or []) == seated, report
    assert (report.get("reference_digests") or {}) == (
        expected["report"]["reference_digests"]), report
    assert (report.get("excluded_behavior_duplicates") or {}) == (
        expected["report"]["excluded_behavior_duplicates"]), report
    assert list(report.get("pool") or []) == list(expected["report"]["pool"]), report
    return expected


def _write_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + chr(10),
                    encoding="utf-8")


def _read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _run_root(tmp_path):
    root = Path(tmp_path) / ("s3-" + uuid.uuid4().hex[:6]) / "run"
    root.mkdir(parents=True, exist_ok=True)
    return root


# ---------------------------------------------------------------------------
# ① 复审纯数据反例：面板选出探索候选，提交却写回空探索席
# ---------------------------------------------------------------------------


def test_a4_review_counterexample_exploration_seat_is_not_frozen(tmp_path):
    """复审 A4 纯数据反例原样复现（真实实现 + 真实落盘，非替身）。

    预置状态：run 目录里只有**在案正常席 [A] 与候选池 {A,B}**（B 是上一轮评价过、
    未占席的候选——与真实迭代链的产物形状一致，见本文件 §E2E 用例实测）、
    正常通道 epoch（H/M 各一根）、本轮挑战者 C（比 A、B 更弱，且挑战批无新根 →
    刷新批校验失败 → 非提交结局）。**不预置探索席**：初始探索席为空。

    反例（修复前）：公共行为面板（update_archive 真实选择器）已选出探索候选，
    提交结果 slots.exploration 仍为 []。
    修复后：探索席 == 面板选择；正常通道仍是原席（挑战未提交 → 保原席）。
    """

    run_root = _run_root(tmp_path)
    iter_dir = run_root / "iterations" / "iter-03"
    iter_dir.mkdir(parents=True, exist_ok=True)
    sig_a = _sig("hu", "pass", "discard:1w")
    sig_b = _sig("hu", "pass", "discard:2b")
    sig_c = _sig("pass", "hu", "discard:3b")
    assert not _sig_diff(sig_a, sig_b) == {} and not _sig_diff(sig_b, sig_c) == {}

    entry_a = _entry("cand-A", 1.0, sig_a)
    entry_b = _entry("cand-B", 0.5, sig_b)
    entry_c = _entry("cand-C", -0.2, sig_c)
    # 无行为证据的候选 D：即便探索席解冻，也不得占席（"解冻" != "放宽资格"）。
    entry_d = _entry("cand-D", 0.4, None)
    assert entry_d["behavior_signature"] is None

    baseline = sa.update_archive([entry_a])
    assert baseline["slots"]["overall"] == ["cand-A"]
    assert baseline["slots"]["exploration"] == []
    baseline["entries"] = {"cand-A": entry_a, "cand-B": entry_b,
                           "cand-D": entry_d}
    _write_json(run_root / "archive" / "av-archive.json", baseline)
    _write_json(run_root / "archive" / "normal-epoch.json",
                {"schema": sa.CHANNEL_EPOCH_SCHEMA, "channel": "normal",
                 "epoch": 1, "roots": EPOCH_ROOTS, "pending": None})

    state = {"run_id": "s3-a4-pure", "iteration_no": 3,
             "iter_dir": str(iter_dir), "identity": {"candidate_id": "cand-C"},
             "behavior": {"behavior_signature": sig_c},
             "conditional_result": {"samples": _normal("cand-C", (H_ROOT, M_ROOT))},
             "natural_result": {"samples": _normal("cand-C", (H_ROOT, M_ROOT))},
             "plan": {}}
    outcome = search._av_commit_archive(state, run_root, True)
    archive = _read_json(run_root / "archive" / "av-archive.json")
    # 结局确实是"挑战未提交、保原席"（与复审观察到的 refresh_rejected 同形）。
    assert outcome["refresh"]["status"] == "refresh_rejected", outcome["refresh"]
    assert archive["challenge"]["seats_kept"] is True, archive["challenge"]

    # —— 候选池视角（对照，**不作在案席位**）：面板重排出的整体席是 [A, B] ——
    pool = sa.update_archive(list(archive["entries"].values()))
    assert pool["slots"]["overall"] == ["cand-A", "cand-B"], pool["slots"]
    assert pool["slots"]["exploration"] == ["cand-C"], pool["selection_report"]["exploration"]

    # —— 复审反例：提交结果必须非空且 == **相对提交后在案席位**重算的探索席 ——
    # （修复前恒为 []；旧口径"== 面板视角选择"在池内整体席与在案整体席不一致时
    #   会把在案整体席持有者的同行为孪生放进探索席——R9 计划 §13 A）
    expected = _assert_exploration_rebased_on_committed(
        archive, expect=["cand-C", "cand-B"])
    assert archive["slots"]["exploration"] == ["cand-C", "cand-B"], (
        "探索席未按提交后在案席位重算：{0}".format(archive["slots"]["exploration"]))
    # 在案整体席只有 A：B 未被在案席位占用、签名与 A 不同 → 可占探索席（§9.1 不兼任
    # 只针对**在案席位**，不是针对池内排序名次）。
    assert expected["seated"] == ["cand-A"], expected["seated"]
    # —— 正常通道仍然保原席（面板整体席是 [A,B]，在案仍是原席 [A]）——
    assert archive["slots"]["overall"] == ["cand-A"], archive["slots"]
    # —— 资格未放宽：无行为证据的 D 不进探索席，也不进探索池 ——
    assert "cand-D" not in archive["slots"]["exploration"], archive["slots"]
    assert "cand-D" not in expected["report"]["pool"], expected["report"]
    # —— 与档案事务一致提交：事务件同时记下被挑战通道的原席与探索席 ——
    assert outcome["refresh"]["exploration_after"] == ["cand-C", "cand-B"], outcome["refresh"]
    tx = _read_json(iter_dir / "transactions" / "tx-channel-refresh.json")
    assert tx["seats_after"] == ["cand-A"], tx
    assert tx["exploration_after"] == ["cand-C", "cand-B"], tx
    # 选席口径身份串随席位一起落盘（R9 §13：排序键与探索席重算口径已升版）。
    assert archive["slot_selection_version"] == sa.SLOT_SELECTION_VERSION, archive.get(
        "slot_selection_version")


def test_a4_freeze_scope_only_challenge_channels(tmp_path):
    """冻结范围：需要同根挑战的通道保原席，探索席不在冻结面内。

    反向断言：把"只冻结挑战通道"写成"冻结全部通道"（当前缺陷）会让本用例在
    探索席断言处转红；把"探索席独占冻结解除"写成"连整体席一起解冻"会在整体席
    断言处转红——两条断言各自独立。
    """

    run_root = _run_root(tmp_path)
    iter_dir = run_root / "iterations" / "iter-01"
    iter_dir.mkdir(parents=True, exist_ok=True)
    sig = [_sig("hu", "pass", "discard:1w"), _sig("hu", "pass", "discard:2b"),
           _sig("pass", "hu", "discard:3b")]
    entries = [_entry("cand-A", 1.0, sig[0]), _entry("cand-B", 0.5, sig[1]),
               _entry("cand-C", -0.2, sig[2])]
    baseline = sa.update_archive([entries[0]])
    baseline["entries"] = {"cand-A": entries[0], "cand-B": entries[1]}
    _write_json(run_root / "archive" / "av-archive.json", baseline)
    _write_json(run_root / "archive" / "normal-epoch.json",
                {"schema": sa.CHANNEL_EPOCH_SCHEMA, "channel": "normal",
                 "epoch": 1, "roots": EPOCH_ROOTS, "pending": None})
    state = {"run_id": "s3-a4-scope", "iteration_no": 2, "iter_dir": str(iter_dir),
             "identity": {"candidate_id": "cand-C"},
             "behavior": {"behavior_signature": sig[2]},
             "natural_result": {"samples": _normal("cand-C", (H_ROOT, M_ROOT))},
             "plan": {}}
    search._av_commit_archive(state, run_root, False)      # 未请求刷新：直接走保席分支
    archive = _read_json(run_root / "archive" / "av-archive.json")
    assert archive["challenge"]["status"] == "no_refresh_requested", archive["challenge"]
    # 挑战通道（整体席）：保原席。
    assert archive["slots"]["overall"] == ["cand-A"], archive["slots"]
    # 探索席：按公共行为面板独立更新（不在冻结面内），且**相对提交后在案席位**重算。
    _assert_exploration_rebased_on_committed(archive, expect=["cand-C", "cand-B"])
    pool = sa.update_archive(list(archive["entries"].values()))
    # 池内视角（对照）：面板整体席是 [A, B]，故池内探索席只剩 C——与在案口径不同源，
    # 这正是旧实现"拼接两份视角"的缺陷来源（R9 计划 §13 A）。
    assert pool["slots"]["overall"] == ["cand-A", "cand-B"], pool["slots"]
    assert pool["slots"]["exploration"] == ["cand-C"], pool["slots"]


# ---------------------------------------------------------------------------
# ①b 挑战**成功提交**的路径同样不得把探索席换回原席
# ---------------------------------------------------------------------------


def test_a4_same_signature_cannot_take_exploration_seat(tmp_path):
    """同签名不重复占探索名额（§9.2 规则 4）在**提交后在案席位**上成立。

    预置：在案整体席 A（签名 s0，安全 PASS）；候选池里 B 与 A **行为完全相同**
    （源码身份不同 → candidate_id 不同），C 的签名与 A 不同。提交（未请求刷新 →
    保原席）后必须：C 占探索席；B **不占**探索席，且被显式登记为"与在案席者同签名"
    的排除项（不静默丢）——同签名不因代码改名/排版增加探索名额。

    反向断言：把行为签名去重退化成 candidate_id 去重，B 会落进探索席 → 本用例转红。
    """

    run_root = _run_root(tmp_path)
    iter_dir = run_root / "iterations" / "iter-02"
    iter_dir.mkdir(parents=True, exist_ok=True)
    sig_a = _sig("hu", "pass", "discard:1w")
    sig_c = _sig("pass", "hu", "discard:3b")
    entry_a = _entry("cand-A", 1.0, sig_a)
    entry_b = _entry("cand-B", 0.4, sig_a)      # 同签名、不同候选身份
    entry_c = _entry("cand-C", -0.2, sig_c)
    assert sa.behavior_signature_digest(entry_a["behavior_signature"]) == \
        sa.behavior_signature_digest(entry_b["behavior_signature"])
    assert _sig_diff(sig_a, sig_c) != {}
    baseline = sa.update_archive([entry_a])
    baseline["entries"] = {"cand-A": entry_a, "cand-B": entry_b}
    _write_json(run_root / "archive" / "av-archive.json", baseline)
    _write_json(run_root / "archive" / "normal-epoch.json",
                {"schema": sa.CHANNEL_EPOCH_SCHEMA, "channel": "normal",
                 "epoch": 1, "roots": EPOCH_ROOTS, "pending": None})
    state = {"run_id": "p6-a4-same-signature", "iteration_no": 2,
             "iter_dir": str(iter_dir), "identity": {"candidate_id": "cand-C"},
             "behavior": {"behavior_signature": sig_c},
             "natural_result": {"samples": _normal("cand-C", (H_ROOT, M_ROOT))},
             "plan": {}}
    search._av_commit_archive(state, run_root, False)
    archive = _read_json(run_root / "archive" / "av-archive.json")
    assert archive["slots"]["overall"] == ["cand-A"], archive["slots"]
    expected = _assert_exploration_rebased_on_committed(archive, expect=["cand-C"])
    # 同签名被排除者**显式登记**（规则 4"不静默丢"）：B → 与在案席者 A 同签名。
    assert expected["report"]["excluded_behavior_duplicates"] == {
        "cand-B": ["cand-A"]}, expected["report"]
    assert "cand-B" not in expected["report"]["pool"], expected["report"]
    assert archive["slots"]["exploration"] == ["cand-C"], archive["slots"]


def test_a4_normal_challenge_commit_carries_panel_exploration(tmp_path):
    """提交分支（apply_challenge committed）也必须带上公共行为面板的探索席。

    复审 §4 A4 指出"成功挑战只更新目标正常通道或家族通道"：若挑战基准档案的席位
    整份取自原席，那么**成功提交**时 `new_slots = dict(archive["slots"])` 也会把
    探索席写回原位（含初始空席）。本用例让正常通道真的提交（刷新批 = 4 根、H/M 各 2、
    全员补齐）→ 换席必须只发生在整体席，探索席按面板落位。
    """

    run_root = _run_root(tmp_path)
    iter_dir = run_root / "iterations" / "iter-04"
    iter_dir.mkdir(parents=True, exist_ok=True)
    refresh_roots = (("np-H-11-root02", "H"), ("np-H-11-root03", "H"),
                     ("np-M-11-root02", "M"), ("np-M-11-root03", "M"))
    all_roots = (H_ROOT, M_ROOT) + refresh_roots
    sig_a = _sig("hu", "pass", "discard:1w")
    sig_b = _sig("hu", "pass", "discard:2b")
    sig_c = _sig("pass", "hu", "discard:3b")
    # 在案：原席 A（比挑战者弱）、候选池里的 B（更弱，且不占任何席）。
    entry_a = _entry("cand-A", 0.5, sig_a, roots=all_roots)
    entry_b = _entry("cand-B", -0.2, sig_b, roots=all_roots)
    baseline = sa.update_archive([entry_a])
    baseline["entries"] = {"cand-A": entry_a, "cand-B": entry_b}
    _write_json(run_root / "archive" / "av-archive.json", baseline)
    _write_json(run_root / "archive" / "normal-epoch.json",
                {"schema": sa.CHANNEL_EPOCH_SCHEMA, "channel": "normal",
                 "epoch": 1, "roots": EPOCH_ROOTS, "pending": None})
    state = {"run_id": "s3-a4-commit", "iteration_no": 4, "iter_dir": str(iter_dir),
             "identity": {"candidate_id": "cand-C"},
             "behavior": {"behavior_signature": sig_c},
             # 挑战者比原席强 → 有望入席；新根恰为 4 根（H/M 各 2）→ 刷新批合法。
             "conditional_result": {"samples": _normal("cand-C", all_roots, 1.0)},
             "natural_result": {"samples": _normal("cand-C", refresh_roots, 1.0)},
             "plan": {}}
    state["conditional_result"]["samples"] += _normal("cand-C", refresh_roots, 1.0)
    outcome = search._av_commit_archive(state, run_root, True)
    archive = _read_json(run_root / "archive" / "av-archive.json")
    assert outcome["status"] == "ARCHIVE_COMMITTED", outcome
    assert archive["challenge"]["status"] == "committed", archive["challenge"]
    assert archive["challenge"]["seats_kept"] is False, archive["challenge"]
    # 整体席按新根集统一重排：挑战者 C 上位、原席 A 仍在前二。
    assert archive["slots"]["overall"] == ["cand-C", "cand-A"], archive["slots"]
    # 探索席：随提交一起落位，且**相对提交后的在案席位**重算（R9 §13 A 口径）。
    # 提交后排除集 = {cand-C, cand-A}（本通道新席）→ 剩余安全候选只有 B。
    expected = _assert_exploration_rebased_on_committed(archive, expect=["cand-B"])
    assert expected["seated"] == ["cand-A", "cand-C"], expected["seated"]
    # 池内视角（对照）：本夹具里面板重排的整体席与提交后在案席位**恰好一致**
    # （B 在两个视角下都没有占整体席），所以本用例单独**不能**区分新旧口径——
    # 能区分的证据在"反例"与"冻结范围"两个用例里（池内整体席是 [A,B]、在案只有 [A]）。
    pool = sa.update_archive(list(archive["entries"].values()))
    assert pool["slots"]["overall"] == ["cand-C", "cand-A"], pool["slots"]
    assert pool["slots"]["exploration"] == ["cand-B"], pool["slots"]
    assert outcome["refresh"]["exploration_after"] == ["cand-B"], outcome["refresh"]
    tx = _read_json(iter_dir / "transactions" / "tx-channel-refresh.json")
    assert tx["seats_after"] == ["cand-C", "cand-A"], tx
    assert tx["exploration_after"] == ["cand-B"], tx


# ---------------------------------------------------------------------------
# ② 端到端：连续 ≥3 个不同动作签名 → 探索席与探索父代可达
# ---------------------------------------------------------------------------


class _FakeDrive:
    """替身桌赛驱动（0 真实桌赛）：焦点臂给确定性分数，语义与 P8/P6 测试同源。

    焦点座位候选臂 +12、基线臂 -10（按 seed 微扰）→ 候选臂 U=1、基线臂 U=0，
    保证组内晋级目标可算（否则样本 uncomputable，档案无根）。
    """

    def __call__(self, *, plan, policies_by_seat, versions_block, step_limit,
                 value_limits):
        seats = list(plan.seats())
        focal_idx = seats.index("natural:focal") if "natural:focal" in seats \
            else seats.index("focal")
        focal_policy = policies_by_seat[focal_idx]
        is_candidate = str(getattr(focal_policy, "policy_id", "")).startswith(
            "action_value")
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


def _behavior_source(kind, tag):
    """按 kind 生成**行为不同**的候选源码（+ 唯一常量使源码身份不同）。

    行为差异只来自评分逻辑本身；tag 只改源码身份（不改行为）——与 P8 的变体
    手法互补：P8 用纯 tag 证明"同行为不重复占席"，本文件用真行为差证明
    "有新行为者必须能进探索席"。
    """

    if kind not in BEHAVIOR_EDITS:
        raise AssertionError("未知的行为变体 {0!r}".format(kind))
    text = EFFICIENCY_SEED.source
    for old, new in BEHAVIOR_EDITS[kind]:
        assert old in text, ("变体 {0} 的编辑点不在种子里：{1!r}".format(kind, old))
        text = text.replace(old, new)
    return text + "\nS3_VARIANT_TAG = {0!r}\n".format(tag)


def _patch_behavior_seed(monkeypatch, kind, tag):
    spec = seeds.SeedSpec(name="efficiency_seed",
                          source=_behavior_source(kind, tag),
                          mechanism=dict(seeds.EFFICIENCY_SEED_MECHANISM))
    monkeypatch.setitem(seeds.SEEDS, "efficiency_seed", spec)


def test_a4_three_distinct_signatures_reach_exploration_seat_and_parent(
        tmp_path, monkeypatch):
    """① 端到端（公开入口 run_av_evolution）：连续三个不同动作签名的候选 →
    探索席非空且**探索父代被真实调度**（planned_channel=exploration、父代来自探索席）。

    每一步的真实/替身与预置状态见 FIX-REPORT §4 路径表。关键断言：
      - 三个候选的**逐窗首选动作**确实不同（签名差异逐窗列出）；
      - 正常通道挑战未提交 → 原正常席保持（保席语义未被探索席更新破坏）；
      - 探索席 == 公共行为面板（update_archive）选择；
      - 通道循环走到探索位时，planned_channel 必须是 exploration 且父代 ∈ 探索席
        （修复前探索席为空 → next_generation_plan 跳过探索、父代永远只来自整体席）。
    """

    monkeypatch.setattr(natural, "execute_natural_table", _FakeDrive(), raising=True)
    run_root = Path(tmp_path) / "chain" / "iter-01"
    signatures = []
    candidates = []
    exploration_hit = None
    observed_channels = []
    for index in range(7):
        before = (_read_json(run_root / "archive" / "av-archive.json")
                  if (run_root / "archive" / "av-archive.json").is_file() else {})
        _patch_behavior_seed(monkeypatch, BEHAVIOR_KINDS[index % len(BEHAVIOR_KINDS)],
                             "k{0}".format(index))
        result = search.run_av_evolution(
            run_root, generation_mode="mock", seed_name="efficiency_seed",
            authorization=TOKEN, natural_roots=1, natural_seats=1)
        assert result.get("terminal") == "ITERATION_COMPLETE", result
        state = search.av_state_load(search.av_latest_state_path(run_root))
        signature = (state.get("behavior") or {}).get("behavior_signature")
        signatures.append(signature)
        candidates.append(state["identity"]["candidate_id"])
        plan_in = state["plan"]["archive_in"]
        observed_channels.append(plan_in.get("planned_channel"))
        if plan_in.get("planned_channel") == "exploration":
            exploration_hit = {"iteration": index + 1, "plan": plan_in,
                               "archive": before, "state": state}
            break

    # —— 前置：前三个候选确实是三个不同动作签名（逐窗差异可核）——
    first_three = signatures[:3]
    assert len(first_three) == 3 and all(first_three), signatures
    digests = [row["digest"] for row in first_three]
    assert len(set(digests)) == 3, digests
    diffs = {"0-1": _sig_diff(first_three[0], first_three[1]),
             "1-2": _sig_diff(first_three[1], first_three[2]),
             "0-2": _sig_diff(first_three[0], first_three[2])}
    for key, diff in diffs.items():
        assert diff, ("候选 {0} 的签名没有逐窗差异".format(key), diffs)
    assert all(row["view_set"] == list(search.AV_BEHAVIOR_VIEWS)
               for row in first_three), first_three

    # —— 探索父代可达：通道循环走到探索位时必须真的排到探索席 ——
    assert exploration_hit is not None, (
        "通道循环未走到探索通道（观测到的 planned_channel 序列：{0}）".format(
            observed_channels))
    archive = exploration_hit["archive"]
    seat = archive["slots"]["exploration"]
    assert seat, ("探索席为空：真正有新行为的候选进不了探索父代通道（复审 A4）",
                  archive["slots"])
    assert exploration_hit["plan"]["planned_operator"] == "M1", exploration_hit["plan"]
    assert exploration_hit["plan"]["planned_parent_candidate_id"] in seat, (
        exploration_hit["plan"], seat)
    assert exploration_hit["plan"]["applied_parent_dir"], exploration_hit["plan"]

    # —— 探索父代持有的是与在案整体席**行为不同**的候选 ——
    overall_seat = archive["slots"]["overall"]
    assert overall_seat, archive["slots"]
    entries = archive["entries"]
    parent = exploration_hit["plan"]["planned_parent_candidate_id"]
    parent_sig = entries[parent]["behavior_signature"]
    assert all(_sig_diff(parent_sig, entries[cid]["behavior_signature"])
               for cid in overall_seat), (parent, overall_seat)

    # —— 正常通道挑战失败：原正常席保持（首个候选），挑战者留在候选池 ——
    assert archive["challenge"]["seats_kept"] is True, archive["challenge"]
    assert archive["challenge"]["status"] == "refresh_rejected", archive["challenge"]
    assert overall_seat == [candidates[0]], (overall_seat, candidates)
    # 前三个候选（即本用例输入的三份不同签名）都已在候选池里（不丢证据）。
    assert set(candidates[:3]) <= set(entries), (candidates[:3], sorted(entries))

    # —— 探索席 == **相对提交后在案席位**重算的选择（R9 计划 §13 A 口径）——
    # 修复前这里写的是"== 候选池面板视角的探索席"，而两者在池内整体席与在案整体席
    # 不一致时会分叉（在案整体席持有者的同行为孪生落进探索席）。现在改为：以**提交后
    # 的在案席位**为排除集与去重参考，逐元素对拍（口径见 _assert_exploration_rebased...
    # 的 docstring；不是"非空"断言）。
    expected = _assert_exploration_rebased_on_committed(archive)
    assert expected["seated"] == overall_seat, (expected["seated"], overall_seat)
    assert archive["slot_selection_version"] == sa.SLOT_SELECTION_VERSION, archive.get(
        "slot_selection_version")
    # 池内视角（对照）：面板重排出的整体席与在案整体席**可以不同**——旧实现把这两份
    # 视角拼在一起提交，才会让在案整体席者的同行为候选占探索席。
    pool = sa.update_archive(list(entries.values()))
    assert pool["slots"]["overall"], pool["slots"]


# ---------------------------------------------------------------------------
# ③ 家族通道：家族席按同根挑战语义保原席，探索席独立更新
# ---------------------------------------------------------------------------

CHANNEL = "branch"
SUB_OPEN = "branch_open"
SUB_COST = "branch_cost"
SEED_A, SEED_B = 11, 12
MAP_1 = {("H", SEED_A): 3, ("M", SEED_A): 4, ("H", SEED_B): 5, ("M", SEED_B): 6}
MAP_2 = {("H", SEED_A): 13, ("M", SEED_A): 14, ("H", SEED_B): 15, ("M", SEED_B): 16}
MAP_3 = {("H", SEED_A): 23, ("M", SEED_A): 24, ("H", SEED_B): 25, ("M", SEED_B): 26}
MAP_4 = {("H", SEED_A): 33, ("M", SEED_A): 34, ("H", SEED_B): 35, ("M", SEED_B): 36}


def _family_declarations(index_map):
    """开轮声明的家族刷新批：两侧 × H/M（每侧 4 条显式根声明）。"""

    return [{"channel": CHANNEL, "sub_scenario": sub, "opponent_mix": mix,
             "panel_seed": seed, "root_index": index_map[(mix, seed)]}
            for sub in (SUB_OPEN, SUB_COST)
            for mix, seed in (("H", SEED_A), ("M", SEED_A),
                              ("H", SEED_B), ("M", SEED_B))]


def _strength_of(source):
    match = re.search(r"S3_STRENGTH\s*=\s*(-?[0-9]+)", source or "")
    return int(match.group(1)) if match else None


def _strength_source(strength, kind):
    """带强度标记 + 行为变体的候选源码（强度只进替身驱动，不进评分逻辑）。"""

    text = _behavior_source(kind, "s{0}-{1}".format(strength, kind))
    lines = text.splitlines()
    return "\n".join(lines[:2] + ["S3_STRENGTH = {0}".format(int(strength))]
                     + lines[2:])


class StrengthDrive:
    """替身桌赛驱动：焦点臂分数由候选源码的强度标记决定（0 真实桌赛）。"""

    def __call__(self, *, plan, policies_by_seat, versions_block, step_limit,
                 value_limits):
        seats = list(plan.seats())
        focal_idx = seats.index("natural:focal") if "natural:focal" in seats \
            else seats.index("focal")
        policy = policies_by_seat[focal_idx]
        is_candidate = str(getattr(policy, "policy_id", "")).startswith(
            "action_value")
        strength = (_strength_of(getattr(getattr(policy, "_scorer", None),
                                         "source", ""))
                    if is_candidate else None)
        focal = float(strength) if strength is not None else -10.0
        others = iter((5.0, 3.0, 1.0))
        scores = [focal if seat == focal_idx else next(others) for seat in range(4)]
        return {"table_id": plan.table_id, "seed": int(plan.seed),
                "match_status": "complete", "wall_ms": 1.0,
                "scores_by_seat": scores, "result": {}}


class FamilyEvalStub:
    """替身家族条件评价执行器（0 真实桌赛）：复现工作项点名的根 + 根摘要标记。"""

    def __init__(self, strength):
        self.strength = int(strength)

    def __call__(self, *, state, run_root, ledger, authorization, item, source,
                 test_runtime_factory=None):
        sub = str(item["sub_scenario"])
        mix = str(item["opponent_mix"])
        seed = int(item["panel_seed"])
        index = int((item.get("root_indexes") or [0])[0])
        roots = [str(value) for value in item["root_ids"]]
        step_id = "{0}:tables-full".format(search._av_family_step_prefix(
            str(item["candidate_id"]), sub, str(item["token"])))
        reservation = ledger.reserve(step_id=step_id, account="tables_full",
                                     amount=4.0, note="替身家族条件评价（先预留）")
        ledger.settle(reservation, actual=4.0, note="替身：0 真实桌赛")
        strength = _strength_of(source.get("source")) or self.strength
        requirement = search.av_family_root_requirement_digest(
            prefix_source=str(item.get("prefix_source") or "scripted_fixture"),
            predicate=sub, opponent_mix=mix, panel_seed=seed, root_index=index)
        samples = [{"source_root_id": root, "scenario": sub,
                    "opponent_mix": mix, "candidate_id": item["candidate_id"],
                    "root_role": "core", "invalid": False,
                    "completeness": "complete", "invalid_reasons": [],
                    "cost": 1.0, "root_requirement_digest": requirement,
                    "root_content_digest": requirement + ":stub",
                    "arms": {"baseline": {"candidate_id": search.AV_BASELINE_ID,
                                          "u": 0.0},
                             "candidate": {"candidate_id": item["candidate_id"],
                                           "u": strength / 16.0}}}
                   for root in roots]
        return {"ok": True, "tables_executed": 4,
                "evaluation": {
                    "ok": True,
                    "identity": {"candidate_id": item["candidate_id"],
                                 "opponent_mix": mix},
                    "panel": {"predicate": sub, "panel_seed": seed,
                              "tables_full_executed": 4},
                    "root_selection": {"selector": "conditional_root",
                                       "indexes": [index], "root_ids": list(roots)},
                    "samples": samples, "execution_kind": "real_runtime",
                    "real_table_instances": 4, "result_admission": {"ok": True}},
                "reason": ""}


def _family_evolve(run_root, monkeypatch, *, strength, kind, index_map):
    source = _strength_source(strength, kind)
    monkeypatch.setitem(seeds.SEEDS, "efficiency_seed", seeds.SeedSpec(
        name="efficiency_seed", source=source,
        mechanism=dict(seeds.EFFICIENCY_SEED_MECHANISM)))
    monkeypatch.setattr(natural, "execute_natural_table", StrengthDrive(),
                        raising=True)
    monkeypatch.setattr(search, "_av_family_execute_evaluation",
                        FamilyEvalStub(strength), raising=True)
    result = search.run_av_evolution(
        run_root, generation_mode="mock", seed_name="efficiency_seed",
        predicate=SUB_OPEN, opponent="H", panel_seed=SEED_A,
        natural_roots=2, natural_seats=1, authorization=TOKEN,
        family_channel=CHANNEL, family_refresh=_family_declarations(index_map))
    assert result.get("terminal") == "ITERATION_COMPLETE", result
    return search.av_state_load(search.av_latest_state_path(run_root))


def test_a4_family_channel_keeps_seats_and_exploration_updates(tmp_path, monkeypatch):
    """③ 家族通道实测：家族席按同根挑战语义保原席；探索席独立更新；整体席仍保原席。

    四次迭代（同一 run_root 的真实续跑，无预塞档案）：
      1. 首次初始化 → 建立家族 epoch 1 + 首个家族席（S2 已交付能力）；
      2. 更弱挑战者（行为与首席不同）→ 家族挑战未提交 → 家族席保持；
      3. 更弱挑战者（第三种行为）→ 家族挑战仍未提交 → 家族席仍保持；
      4. 更弱挑战者（第四种行为）→ 家族席仍保持；候选池已有 4 个可留身份，
         公共行为面板因此选出**未被任何整体/家族席占用**的候选作探索席 →
         探索席必须与档案事务一起落位（修复前被 `_kept_write` 冻结为空）。
    """

    run_root = _run_root(tmp_path)
    first_state = _family_evolve(run_root, monkeypatch, strength=8, kind="base",
                                 index_map=MAP_1)
    first = first_state["identity"]["candidate_id"]
    archive_1 = _read_json(run_root / "archive" / "av-archive.json")
    assert archive_1["slots"][CHANNEL] == [first], archive_1["slots"]

    second_state = _family_evolve(run_root, monkeypatch, strength=4,
                                  kind="shanten_neg", index_map=MAP_2)
    second = second_state["identity"]["candidate_id"]
    archive_2 = _read_json(run_root / "archive" / "av-archive.json")
    # 家族席保持（弱挑战者不入席）；整体席也保持（正常通道同样未提交换席）。
    assert archive_2["slots"][CHANNEL] == [first], archive_2["slots"]
    assert archive_2["slots"]["overall"] == [first], archive_2["slots"]
    assert archive_2["family_challenge"]["seats_kept"] is True, \
        archive_2["family_challenge"]
    assert second in archive_2["entries"], sorted(archive_2["entries"])

    third_state = _family_evolve(run_root, monkeypatch, strength=4,
                                 kind="pass_when_unknown", index_map=MAP_3)
    third = third_state["identity"]["candidate_id"]
    archive_3 = _read_json(run_root / "archive" / "av-archive.json")
    # 家族通道语义不变：家族挑战未提交 → 家族席仍是首席。
    assert archive_3["slots"][CHANNEL] == [first], archive_3["slots"]
    assert archive_3["family_challenge"]["seats_kept"] is True, archive_3["family_challenge"]

    fourth_state = _family_evolve(run_root, monkeypatch, strength=4,
                                  kind="shanten_neg_pass_unknown", index_map=MAP_4)
    fourth = fourth_state["identity"]["candidate_id"]
    archive_4 = _read_json(run_root / "archive" / "av-archive.json")
    # 家族席仍保持（第四次仍是"未提交 → 保原席"），整体席也仍保持。
    assert archive_4["slots"][CHANNEL] == [first], archive_4["slots"]
    assert archive_4["slots"]["overall"] == [first], archive_4["slots"]
    assert archive_4["family_challenge"]["seats_kept"] is True, archive_4["family_challenge"]
    # 探索席：相对**提交后在案席位**重算（修复前被保席逻辑冻结为空）。
    # 排除集 = 在案整体席 + 四家族席（本夹具里都是 first）；去重参考 = first 的签名。
    expected_4 = _assert_exploration_rebased_on_committed(archive_4)
    assert len(archive_4["slots"]["exploration"]) == 2, archive_4["slots"]
    assert expected_4["seated"] == [first], expected_4["seated"]
    assert set(archive_4["slots"]["exploration"]) <= {second, third, fourth}, (
        archive_4["slots"], [second, third, fourth])
    # 四个候选行为互不相同（逐窗差异可核），探索席持有的是**未占挑战通道**的那个。
    entries = archive_4["entries"]
    sigs = [entries[cid]["behavior_signature"]
            for cid in (first, second, third, fourth)]
    assert len({row["digest"] for row in sigs}) == 4, sigs
    for left in range(4):
        for right in range(left + 1, 4):
            assert _sig_diff(sigs[left], sigs[right]), (left, right)
    assert first not in archive_4["slots"]["exploration"], archive_4["slots"]
    assert not (set(archive_4["slots"]["exploration"])
                & set(archive_4["slots"][CHANNEL])), archive_4["slots"]
    # 事务件（同一份档案事务）如实记下被保原家族席与本次的探索席。
    tx = _read_json(Path(fourth_state["iter_dir"]) / "transactions"
                    / "tx-family-refresh.json")
    assert tx["seats_after"] == [first], tx
    assert tx["exploration_after"] == archive_4["slots"]["exploration"], tx


def test_a4_family_challenge_commit_carries_panel_exploration(tmp_path, monkeypatch):
    """③b 家族挑战**成功提交**时：家族席按同根集换席，探索席随面板一起提交。

    与 ③ 互补：③ 覆盖"家族挑战未提交 → 保原家族席"的非提交写点（_kept_write），
    本用例覆盖提交写点（challenge_base → apply_challenge committed）：换席只能发生在
    被挑战的家族通道上，探索席仍由公共行为面板决定（修复前整份基准取自原席 → 探索席
    被写回空表）。
    """

    run_root = _run_root(tmp_path)
    first = _family_evolve(run_root, monkeypatch, strength=12, kind="base",
                           index_map=MAP_1)["identity"]["candidate_id"]
    # 第二个候选的强度标记**低于基线（-10）**：整体/家族排序值都是负的 → 它永远进不了
    # 挑战通道席位，因而**必然**留在探索池（探索席断言因此与总成本并列时的字典序无关，
    # 不随运行目录漂移而时红时绿）。它本身仍是一个合法的行为不同候选。
    weak = _family_evolve(run_root, monkeypatch, strength=-20, kind="shanten_neg",
                          index_map=MAP_2)["identity"]["candidate_id"]
    third_state = _family_evolve(run_root, monkeypatch, strength=20,
                                 kind="pass_when_unknown", index_map=MAP_3)
    third = third_state["identity"]["candidate_id"]
    archive = _read_json(run_root / "archive" / "av-archive.json")
    assert archive["family_challenge"]["status"] == "committed", archive["family_challenge"]
    assert archive["slots"][CHANNEL] == [third], archive["slots"]
    assert third != first and weak not in (first, third)
    # 正常通道本轮未提交 → 原正常席保持（换席不外溢到其它通道）。
    assert archive["slots"]["overall"] == [first], archive["slots"]
    # 探索席：相对**提交后在案席位**重算的结果必须随提交一起落位（弱候选未被任何
    # 挑战通道占用）。修复前整份基准取自原席 → 探索席被写回空表。
    expected = _assert_exploration_rebased_on_committed(archive, expect=[weak])
    # 排除集 = 在案整体席 first + 本通道家族席 third（换席只发生在本通道）。
    assert expected["seated"] == sorted([first, third]), expected["seated"]
    assert not (set(archive["slots"]["exploration"])
                & set(archive["slots"][CHANNEL])), archive["slots"]
    assert archive["slot_selection_version"] == sa.SLOT_SELECTION_VERSION, archive.get(
        "slot_selection_version")


# ---------------------------------------------------------------------------
# ①c P7：epoch is None 首次提交分支统一到同一提交口径（R9 §15 P6 未闭合项 2）
# ---------------------------------------------------------------------------


def test_a4_normal_first_commit_uses_the_same_rebase_call(tmp_path, monkeypatch):
    """P7：首次建立正常通道 epoch 的分支与其它提交点**同一调用口径**。

    P6 遗留（R9 §15 未闭合项 2）：`_av_commit_archive` 的 `epoch is None` 分支没有显式
    调 `rebase_exploration_seat`，只靠"该分支的在案席位就是 `update_archive` 的席位"
    这一步**旁证**（结论当时确实相同）。旁证不是保证：一旦该分支改成"先写席、探索席
    另算"、或池内视角与提交席位分叉，就会静默回到 §13 A 的旧缺陷形态（探索父代与在案
    整体席同行为）。本用例把该分支钉在同一口径上，逐项判据：

      ① 口径：该分支**显式**调用 `_av_commit_slots`（入参 = 冻结面席位：探索席置空，
         由提交点相对在案席位重算）；
      ② 结果：落盘的探索席 == `sa.select_exploration_seat(entries, 在案席位)` 的独立
         复算（精确集合 + 排除集/去重参考逐项一致，不是"非空"）；
      ③ 等价对照：本夹具的**池内视角**与提交后在案席位本就一致（`update_archive` 的
         整体席 == 提交席位），因此池内视角选出的探索席与重算结论相同——这正是 P6
         当时能给出等价性论证的原因；口径统一不改变任何产物（跨变体逐字节对照见
         `evidence/v4-impl/r9-fixes/P7-famid/probes/probe_equivalence_seat_commit.py`）。

    反向断言：把该分支的 `_av_commit_slots` 摘掉（回到 P6 写法）→ ① 转红；把它换成
    "只写冻结面席位、不重算"→ 探索席变成 []（冻结面把探索席置空）→ ② 转红。
    """

    run_root = _run_root(tmp_path)
    iter_dir = run_root / "iterations" / "iter-00"
    iter_dir.mkdir(parents=True, exist_ok=True)
    sig_a = _sig("hu", "pass", "discard:1w")
    sig_b = _sig("hu", "pass", "discard:2b")
    sig_c = _sig("pass", "hu", "discard:3b")
    entry_a = _entry("cand-A", 1.0, sig_a)
    entry_b = _entry("cand-B", 0.5, sig_b)
    entry_c = _entry("cand-C", -0.2, sig_c)
    # 在案档案（含候选池条目）但**没有** normal-epoch.json：首次提交分支。
    baseline = sa.update_archive([entry_a])
    baseline["entries"] = {"cand-A": entry_a, "cand-B": entry_b, "cand-C": entry_c}
    _write_json(run_root / "archive" / "av-archive.json", baseline)
    assert not (run_root / "archive" / "normal-epoch.json").is_file()
    state = {"run_id": "p7-a4-first-commit", "iteration_no": 1,
             "iter_dir": str(iter_dir), "identity": {"candidate_id": "cand-C"},
             "behavior": {"behavior_signature": sig_c},
             "natural_result": {"samples": _normal("cand-C", (H_ROOT, M_ROOT), 0.7)},
             "plan": {}}

    calls = []
    real_commit = search._av_commit_slots

    def spy(archive, seats):
        calls.append({"seats": {key: list(value) for key, value in seats.items()},
                      "exploration_in_seats": list(seats.get("exploration") or [])})
        return real_commit(archive, seats)

    monkeypatch.setattr(search, "_av_commit_slots", spy, raising=True)
    outcome = search._av_commit_archive(state, run_root, False)
    archive = _read_json(run_root / "archive" / "av-archive.json")
    assert outcome["status"] == "ARCHIVE_COMMITTED", outcome
    assert archive["challenge"]["status"] == "epoch_established", archive["challenge"]
    assert archive["challenge"]["seats_kept"] is False, archive["challenge"]

    # ① 口径：该分支确实走了统一入口，且入参是"冻结面席位"（探索席置空后重算）。
    assert len(calls) == 1, calls
    assert calls[0]["exploration_in_seats"] == [], calls
    assert sorted(calls[0]["seats"]) == sorted(sa.SLOT_CAPACITY), calls
    assert calls[0]["seats"]["overall"] == ["cand-A", "cand-B"], calls

    # ② 结果：落盘探索席 == 相对在案席位重算（精确集合 + 排除集/去重参考逐项一致）。
    expected = _assert_exploration_rebased_on_committed(archive, expect=["cand-C"])
    assert expected["seated"] == ["cand-A", "cand-B"], expected["seated"]
    assert archive["slots"]["exploration"] == ["cand-C"], archive["slots"]

    # ③ 等价对照：本夹具里池内视角 == 提交席位，故两种口径结论相同（P6 旁证成立）。
    pool = sa.update_archive(list(archive["entries"].values()))
    assert pool["slots"]["overall"] == archive["slots"]["overall"], pool["slots"]
    assert pool["slots"]["exploration"] == archive["slots"]["exploration"], pool["slots"]
    # 事务件与口径串随同一份提交落盘。
    tx = _read_json(iter_dir / "transactions" / "tx-channel-refresh.json")
    assert tx["seats_after"] == ["cand-A", "cand-B"], tx
    assert tx["exploration_after"] == ["cand-C"], tx
    assert archive["slot_selection_version"] == sa.SLOT_SELECTION_VERSION, archive.get(
        "slot_selection_version")


# ---------------------------------------------------------------------------
# ④ P13 / 复审 A4r：两个探索席**彼此**同行为去重（P2 残留）
# ---------------------------------------------------------------------------


def _a4r_fixture():
    """A（action1，占 overall）+ B/C（同为 action2）+ D（action3）；等证据数。"""

    sig_a = _sig("discard:1w")
    sig_bc = _sig("discard:2b")
    sig_d = _sig("discard:3b")
    entries = {"A": _entry("cand-A", 1.0, sig_a),
               "B": _entry("cand-B", 0.5, sig_bc),
               "C": _entry("cand-C", 0.4, sig_bc),
               "D": _entry("cand-D", 0.3, sig_d)}
    digest = {entries[key]["candidate_id"]: entries[key]["behavior_digest"]
              for key in entries}
    assert digest["cand-B"] == digest["cand-C"], digest   # B/C 同行为（源码身份不同）
    assert len({digest["cand-A"], digest["cand-B"], digest["cand-D"]}) == 3, digest
    return entries, digest


def _a4r_select(entries, seats=("cand-A",)):
    """公开选择器纯数据直调；返回 (slots, report)。"""

    result = sa.select_exploration_seat(list(entries), {"overall": list(seats)})
    return result["slots"], result["report"]


def test_a4r_two_exploration_seats_cannot_share_behavior_signature():
    """① 复审最小反例：正常席 A 选 action1、B/C 都选 action2 → 两个探索席只留一个。

    修复前：B、C 都进探索池，第二轮最小距离 0.0 仍被选中（两个探索名额代表同一种
    行为）。修复后：C 被 B 排除并登记来源；**没有第二种行为就不填满第二席**。

    反向断言：把"选入后排除同行为候选"删掉 → slots 变 ["cand-B", "cand-C"] 转红。
    """

    entries, digest = _a4r_fixture()
    pool = [entries["A"], entries["B"], entries["C"]]
    slots, report = _a4r_select(pool)
    # ① B/C 只留一个（同行为不给第二个探索名额）。
    assert slots == ["cand-B"], (slots, report)
    # 池内两个同行为候选都可参加打分（排除发生在选入之后，不是静默筛掉）。
    assert report["pool"] == ["cand-B", "cand-C"], report["pool"]
    # 只有一种行为 → 第二轮不发生（第二席留空，不用同行为补满）。
    assert len(report["steps"]) == 1, report["steps"]
    assert report["steps"][0]["chosen"] == "cand-B", report["steps"]
    # 排除来源逐条可核：谁被谁排除、依据哪条签名摘要。
    assert report["steps"][0]["excluded_same_behavior"] == {
        "cand-C": digest["cand-B"]}, report["steps"]
    assert report["excluded_behavior_duplicates"] == {"cand-C": ["cand-B"]}, report
    assert report["excluded_behavior_duplicate_sources"] == {
        "cand-C": {"basis": sa.EXPLORATION_DUPLICATE_BASIS,
                   "digest": digest["cand-B"], "owners": ["cand-B"]}}, report
    # 被排除者与提出排除者行为摘要相同（排除依据就是它）。
    assert digest["cand-C"] == report["excluded_behavior_duplicate_sources"][
        "cand-C"]["digest"], report


def test_a4r_distinct_behavior_d_takes_the_second_exploration_seat():
    """② 加入选 action3 的 D → 两个探索席为 B、D（不同签名仍可占探索席）。

    反向断言：把分组键从行为摘要换成 candidate_id（等于不去重）→ 修复前形态；把去重
    写成"整池只留一个候选"→ D 进不了第二席，本用例转红。
    """

    entries, digest = _a4r_fixture()
    slots, report = _a4r_select([entries[k] for k in ("A", "B", "C", "D")])
    assert slots == ["cand-B", "cand-D"], (slots, report)
    # 两个探索席的行为摘要互不相同（这正是"探索多样性"的可核判据）。
    member_digests = [digest[cid] for cid in slots]
    assert len(set(member_digests)) == len(member_digests), member_digests
    assert digest["cand-D"] in member_digests and digest["cand-B"] in member_digests
    # 同行为的 C 仍被排除并登记（第二席由**不同行为**的 D 占，不是被 C 填）。
    assert report["excluded_behavior_duplicates"] == {"cand-C": ["cand-B"]}, report
    assert "cand-C" not in slots, slots


def test_a4r_input_order_does_not_change_exploration_result():
    """③ 输入顺序不影响结果：4 个候选的全部 24 种排列给出同一席位与同一登记。

    反向断言：排除/登记若依赖 dict 插入序（例如先 `for cid in remaining` 再记录），
    排列间会出现不同 slots 或不同 owners 顺序 → 本用例转红。
    """

    entries, digest = _a4r_fixture()
    keys = ("A", "B", "C", "D")
    outcomes = {}
    for order in itertools.permutations(keys):
        slots, report = _a4r_select([entries[k] for k in order])
        outcomes["".join(order)] = (tuple(slots), json.dumps({
            "excluded_behavior_duplicates": report["excluded_behavior_duplicates"],
            "excluded_behavior_duplicate_sources": report[
                "excluded_behavior_duplicate_sources"]}, sort_keys=True))
    assert len(outcomes) == 24, sorted(outcomes)
    distinct = sorted(set(outcomes.values()))
    assert len(distinct) == 1, distinct
    slots, _ = _a4r_select([entries[k] for k in keys])
    assert list(slots) == ["cand-B", "cand-D"], slots


def test_a4r_archive_keeps_duplicate_lineage_and_records_source():
    """④ 档案级（update_archive）：席位去重不丢缓存/血缘，重复来源照记。

    同行为候选只退出**选席**：它仍在 entries（结果缓存与血缘保留），并在
    behavior_duplicates / selection_report.exploration 里显式登记"被谁排除"。
    """

    entries, digest = _a4r_fixture()
    archive = sa.update_archive([entries[k] for k in ("A", "B", "C", "D")])
    seat = archive["slots"]["exploration"]
    assert seat == ["cand-D"], (seat, archive["slots"])
    # 缓存/血缘保留：被排除者未从档案条目里消失。
    assert sorted(archive["entries"]) == ["cand-A", "cand-B", "cand-C", "cand-D"], \
        sorted(archive["entries"])
    assert archive["entries"]["cand-C"]["behavior_digest"] == digest["cand-C"]
    # 排除来源照记：C 与整体席者 B 同行为（在案席持有者来源）。
    assert archive["behavior_duplicates"] == {"cand-C": ["cand-B"]}, \
        archive["behavior_duplicates"]
    sources = archive["selection_report"]["exploration"][
        "excluded_behavior_duplicate_sources"]
    assert sources == {"cand-C": {"basis": sa.SEATED_DUPLICATE_BASIS,
                                  "digest": digest["cand-B"],
                                  "owners": ["cand-B"]}}, sources
    assert archive["slot_selection_version"] == sa.SLOT_SELECTION_VERSION


def test_a4r_no_second_behavior_leaves_second_seat_empty(tmp_path, monkeypatch):
    """⑤ 只有一种行为：第二席**留空**（不得强行填充），提交路径同样如此。

    预置在案整体席 A（action1）；候选池只有 B/C（同为 action2）。提交（未请求刷新 →
    保原席）后探索席必须是 [B]：第二个名额空着，而不是用同行为的 C 填满。
    """

    run_root = _run_root(tmp_path)
    iter_dir = run_root / "iterations" / "iter-05"
    iter_dir.mkdir(parents=True, exist_ok=True)
    sig_a = _sig("discard:1w")
    sig_bc = _sig("discard:2b")
    entry_a = _entry("cand-A", 1.0, sig_a)
    entry_b = _entry("cand-B", 0.5, sig_bc)
    entry_c = _entry("cand-C", 0.4, sig_bc)
    baseline = sa.update_archive([entry_a])
    baseline["entries"] = {"cand-A": entry_a, "cand-B": entry_b, "cand-C": entry_c}
    _write_json(run_root / "archive" / "av-archive.json", baseline)
    _write_json(run_root / "archive" / "normal-epoch.json",
                {"schema": sa.CHANNEL_EPOCH_SCHEMA, "channel": "normal",
                 "epoch": 1, "roots": EPOCH_ROOTS, "pending": None})
    state = {"run_id": "p13-a4r-single-behavior", "iteration_no": 5,
             "iter_dir": str(iter_dir), "identity": {"candidate_id": "cand-C"},
             "behavior": {"behavior_signature": sig_bc},
             "natural_result": {"samples": _normal("cand-C", (H_ROOT, M_ROOT))},
             "plan": {}}
    search._av_commit_archive(state, run_root, False)
    archive = _read_json(run_root / "archive" / "av-archive.json")
    assert archive["slots"]["overall"] == ["cand-A"], archive["slots"]
    expected = _assert_exploration_rebased_on_committed(archive, expect=["cand-B"])
    assert archive["slots"]["exploration"] == ["cand-B"], (
        "同行为候选填满了第二个探索名额：{0}".format(archive["slots"]))
    assert expected["report"]["excluded_behavior_duplicates"] == {
        "cand-C": ["cand-B"]}, expected["report"]
    assert expected["report"]["excluded_behavior_duplicate_sources"]["cand-C"][
        "basis"] == sa.EXPLORATION_DUPLICATE_BASIS, expected["report"]
    tx = _read_json(iter_dir / "transactions" / "tx-channel-refresh.json")
    assert tx["exploration_after"] == ["cand-B"], tx


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
