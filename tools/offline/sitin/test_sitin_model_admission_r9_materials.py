"""P4 ADMIT · R9 修复专属测试（复审 R8-REPAIR-REREVIEW §5 M1 / §5 M2）。

覆盖两件事：
1. **M1 材料兼容性**：区分「候选未违规」与「有完整能力证据」——材料不兼容时整包
   INCOMPLETE，不得计入通过数/兑换信用/准入，也不得缩小冻结分母；父代等**所有实际
   评价材料字节**进入准入身份，汇总时从当前字节重验，材料一变旧报告即失效；
2. **M2 行为签名同口径**：偏好签名**直接复用生产排序**（先确定动作、后序列化），
   舍入只用于展示。

红→绿：修复前本文件相关用例必须失败（合成包 24/24、评分器 6/6、admission_pass=True；
极小分差下准入首选与生产首选分叉）。运行：
    .venv/bin/python -m pytest review/llm-guided-heuristic-route-2026-09-15/tools/test_sitin_model_admission_r9_materials.py -q

**证据边界**：全部为进程内合成回复 / 冻结任务包**副本**（临时目录）；0 真实模型、
0 真实桌赛、0 网络；不写仓库内既有 evidence。
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
import io
import json
import shutil
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import sitin_model_admission as adm  # noqa: E402
import sitin_model_admission_probes as probes  # noqa: E402

PKG = adm.PACKAGE_DIR
MATERIAL_TASKS = ("T06", "T07", "T08")
PARENT_REF = "materials/T06-parent-triax-v1.py"

TINY_SCORER = """def score_actions(view):
    \"\"\"合成评分器：分数 = 序号 × 1e-10（复审 §5 M2 反例）。\"\"\"
    entries = []
    for index, action in enumerate(view["actions"]):
        entries.append({"action_key": action["action_key"],
                        "score": index * 0.0000000001, "trace": {}})
    return {"status": "SCORED", "entries": entries}
"""

#: 保序/等行为变换包装：复用父代评分，只改分数的数值表示。
WRAPPER_TEMPLATE = """


def score_actions(view):
    \"\"\"变换包装：决策含义不变，只改分数表示。\"\"\"
    batch = parent_score(view)
    if batch["status"] != "SCORED":
        return batch
    entries = []
    for entry in batch["entries"]:
        entries.append({"action_key": entry["action_key"],
                        "score": TRANSFORM(entry["score"]),
                        "trace": entry["trace"]})
    return {"status": "SCORED", "entries": entries}
"""


def _wrapped(parent_code: str, expression: str) -> str:
    """父代入口改名 + 变换包装（只改分数表示，不改决策含义）。"""
    return probes._rename_entry(parent_code) + WRAPPER_TEMPLATE.replace(
        "TRANSFORM", "(lambda VALUE: " + expression + ")")


# ---------------------------------------------------------------------------
# 夹具：任务包副本 + 合成回复（不触碰仓库里的冻结任务包）
# ---------------------------------------------------------------------------

def _package_copy(tmp_path: Path, name: str) -> Path:
    dest = Path(tmp_path) / name
    shutil.copytree(PKG, dest, dirs_exist_ok=True)
    return dest


def _synthetic_replies(package_dir: Path, replies_dir: Path, marker: str) -> Path:
    """复审 §5 M1 的合成回复：标准答案 + 一行**不同文本**的标记。"""
    replies_dir.mkdir(parents=True, exist_ok=True)
    for path in sorted((package_dir / "selftest" / "standard").glob("T*.txt")):
        (replies_dir / path.name).write_text(
            path.read_text(encoding="utf-8") + chr(10) + "审查夹具记录：" + marker + chr(10),
            encoding="utf-8")
    return replies_dir


def _run(argv) -> int:
    with contextlib.redirect_stdout(io.StringIO()):
        return adm.main(list(argv))


def _grade(package_dir: Path, replies_dir: Path, out: Path, label: str):
    assert _run(["grade", "--package-dir", str(package_dir),
                 "--replies", str(replies_dir), "--out", str(out),
                 "--round-label", label]) == 0
    return json.loads(Path(out).read_text(encoding="utf-8"))


def _summarize(package_dir: Path, reports, out: Path):
    argv = ["summarize", "--manifest", str(package_dir / "manifest.json"),
            "--out", str(out)]
    for report in reports:
        argv += ["--report", str(report)]
    assert _run(argv) == 0
    return json.loads(Path(out).read_text(encoding="utf-8"))


def _row(report: dict, task_id: str) -> dict:
    return next(row for row in report["tasks"] if row["task_id"] == task_id)


def _parent_code(package_dir: Path, task_id: str = "T06") -> str:
    reply = (package_dir / "selftest" / "standard" / (task_id + ".txt")).read_text(
        encoding="utf-8")
    return adm.gen.normalized_code(adm.gen.parse_action_value_reply(reply)["code"])


def _production_first(code: str, view_name: str):
    """生产口径的首选动作（调用线上同一函数）。"""
    from hangma_bot.policy import action_value_executor as av_exec
    from hangma_bot.policy.action_value import batch_to_ranked_candidates
    view = adm.gates.AV_VIEW_FIXTURES[view_name]()
    batch = av_exec.ActionValueExecutor(code, name="<test-production>").score(view)
    ranked = batch_to_ranked_candidates(batch, view.actions)
    return ranked[0].action_key if ranked else None


def _t06_views():
    return list(json.loads((PKG / "tasks" / "T06.json").read_text(
        encoding="utf-8"))["validation"]["views"])

# ---------------------------------------------------------------------------
# 1. M1：材料不兼容的合成包不得准入（复审原样反例）
# ---------------------------------------------------------------------------

def test_synthetic_replies_with_incompatible_parent_material_are_not_admitted(tmp_path):
    """复审 §5 M1 反例：合成回复 24/24、评分器 6/6、admission_pass=True → 必须消失。

    冻结父代材料 materials/T06-parent-triax-v1.py 在当前视图结构版本下全部弃权：
    T06/T07/T08 的第 ④ 条无法判定，因此只有 21 项、3 个评分器任务有完整证据。
    它们**不判候选挂**（不是模型的错），但不得计入通过数、不得兑换信用、整包必须是
    INCOMPLETE；冻结分母仍是 24 项 / 6 个评分器任务（不得缩小分母绕过门槛）。
    """
    pkg = _package_copy(tmp_path, "pkg")
    reports = []
    first_report = None
    for index in (1, 2):
        replies = _synthetic_replies(pkg, Path(tmp_path) / ("replies-" + str(index)),
                                     str(index))
        report_path = Path(tmp_path) / ("grade-" + str(index) + ".json")
        reports.append(report_path)
        report = _grade(pkg, replies, report_path, "synthetic-" + str(index))
        first_report = first_report or report
    report = first_report
    # 冻结分母不得缩小：仍是全部 24 项 / 6 个评分器任务。
    assert report["summary"]["tasks"] == 24
    assert report["summary"]["scorer_total"] == 6
    assert report["summary"]["pass"] == 21, report["summary"]
    assert report["summary"]["scorer_pass"] == 3, report["summary"]
    assert report["summary"]["material_incomplete_task_ids"] == list(MATERIAL_TASKS)
    assert report["summary"]["status"] == adm.PACKAGE_INCOMPLETE
    for task_id in MATERIAL_TASKS:
        row = _row(report, task_id)
        # 「候选未违规」与「有完整能力证据」分开记：
        assert row["pass"] is False, (task_id, row.get("problems"))
        assert row["decidable_pass"] is True, (task_id, row)
        assert row["violation"] is False, (task_id, row)
        assert row["evidence_status"] == adm.EVIDENCE_MATERIAL_INCOMPLETE, row
        assert row["credit_blocked"] is True, row
        assert row["warnings"], task_id
    verdict = _summarize(pkg, reports, Path(tmp_path) / "verdict.json")
    assert verdict["unique_rounds"] == 2, verdict["duplicate_rounds"]
    assert verdict["admission_pass"] is False
    assert verdict["status"] == adm.PACKAGE_INCOMPLETE
    assert verdict["material_compatibility"]["incompatible_task_ids"] == (
        list(MATERIAL_TASKS))
    assert verdict["blocking_reasons"], "阻断准入却没有给出理由"


def test_material_bytes_enter_identity_and_old_report_is_rejected(tmp_path):
    """**只替换父代材料**即拒绝旧报告：材料字节进入任务摘要与材料身份。

    修复前：材料换成可评分父代后任务摘要不变，旧报告继续 identity_ok=True /
    admission_pass=True（复审 §5 M1 第二条反例）。
    """
    pkg = _package_copy(tmp_path, "pkg")
    replies = _synthetic_replies(pkg, Path(tmp_path) / "replies", "1")
    report_path = Path(tmp_path) / "grade.json"
    report = _grade(pkg, replies, report_path, "synthetic-1")
    before = report["identity"]
    assert before["materials_sha256"] == adm.materials_sha256(pkg, adm.load_tasks(pkg))
    # 只改父代材料（任务 JSON 一个字不改）。
    (pkg / PARENT_REF).write_text(_parent_code(pkg), encoding="utf-8")
    after_tasks = adm.load_tasks(pkg)
    assert adm.tasks_sha256(after_tasks, pkg) != before["tasks_sha256"]
    assert adm.materials_sha256(pkg, after_tasks) != before["materials_sha256"]
    verdict = _summarize(pkg, [report_path], Path(tmp_path) / "verdict.json")
    assert verdict["admission_pass"] is False
    row = verdict["rounds"][0]
    assert row["identity_ok"] is False
    assert row["material_consistent"] is False
    joined = " ".join(row["identity_problems"] + row["material_problems"])
    assert "评价材料字节不一致" in joined, joined
    assert "材料兼容性重验不一致" in joined, joined


def test_material_fix_then_regrade_reestablishes_credit(tmp_path):
    """正对照：材料修好并**重新判分**后成绩可以重建（门不是恒挂）。

    新父代 = T06 标准答案（可评分）；候选 = 在父代基础上**真的改变首选动作**的修订
    （复用 E2 等行为探针的正对照包装），第 ④ 条必须重新给出 REVISION_OBSERVED。
    """
    pkg = _package_copy(tmp_path, "pkg")
    (pkg / PARENT_REF).write_text(_parent_code(pkg), encoding="utf-8")
    parent = _parent_code(pkg)
    child = probes._rename_entry(parent) + probes.REAL_CHANGE_WRAPPER
    replies = _synthetic_replies(pkg, Path(tmp_path) / "replies", "1")
    (replies / "T06.txt").write_text(
        "{材料修好后的重判正对照。}" + chr(10) + chr(10) + "```json" + chr(10)
        + json.dumps(probes.REAL_CHANGE_MECHANISM, ensure_ascii=False)
        + chr(10) + "```" + chr(10) + chr(10) + "```python" + chr(10) + child
        + chr(10) + "```" + chr(10), encoding="utf-8")
    report = _grade(pkg, replies, Path(tmp_path) / "grade.json", "regraded")
    row = _row(report, "T06")
    assert row["evidence_status"] == adm.EVIDENCE_COMPLETE
    assert row["pass"] is True, row.get("problems")
    revision = row["detail"]["capability"]["revision_behavior"]
    assert revision["verdict"] == adm.REVISION_OBSERVED, revision
    assert revision["credited"] is True
    assert report["material_compatibility"]["status"] == adm.PACKAGE_COMPLETE
    assert report["summary"]["material_incomplete_task_ids"] == []


def test_verify_materials_recomputes_from_current_bytes(tmp_path):
    """材料兼容性从**当前字节**重算：冻结父代不兼容、换成可评分父代即兼容。"""
    pkg = _package_copy(tmp_path, "pkg")
    frozen = adm.verify_materials(pkg, adm.load_tasks(pkg))
    assert frozen["status"] == adm.PACKAGE_INCOMPLETE
    assert frozen["incompatible_task_ids"] == list(MATERIAL_TASKS)
    for row in frozen["checked"]:
        assert row["observable_views"] == [], row
        assert row["status"] == "INCOMPATIBLE", row
    (pkg / PARENT_REF).write_text(_parent_code(pkg), encoding="utf-8")
    fixed = adm.verify_materials(pkg, adm.load_tasks(pkg))
    assert fixed["status"] == adm.PACKAGE_COMPLETE
    assert fixed["incompatible_task_ids"] == []
    assert all(row["observable_views"] for row in fixed["checked"]), fixed


def test_summarize_rejects_report_claiming_compatible_materials(tmp_path):
    """汇总**重验**材料：报告自称「材料全兼容」但当前材料不兼容 → 拒绝（不信自述）。

    伪造时把材料记录、摘要计数与包级状态**一起**改成一致（假装兼容），身份哈希保持
    与当前材料一致——唯一能识破的就是汇总端从当前字节独立重算的那一步。
    """
    pkg = _package_copy(tmp_path, "pkg")  # 父代仍是冻结的不兼容材料
    replies = _synthetic_replies(pkg, Path(tmp_path) / "replies", "1")
    report_path = Path(tmp_path) / "grade.json"
    report = _grade(pkg, replies, report_path, "forged")
    forged = json.loads(json.dumps(report))
    forged["material_compatibility"]["status"] = adm.PACKAGE_COMPLETE
    forged["material_compatibility"]["incompatible_task_ids"] = []
    forged["summary"]["status"] = adm.PACKAGE_COMPLETE
    forged["summary"]["material_incomplete"] = 0
    forged["summary"]["material_incomplete_task_ids"] = []
    forged_path = Path(tmp_path) / "forged.json"
    forged_path.write_text(json.dumps(forged, ensure_ascii=False), encoding="utf-8")
    verdict = _summarize(pkg, [forged_path], Path(tmp_path) / "verdict.json")
    assert verdict["admission_pass"] is False
    assert verdict["status"] == adm.PACKAGE_INCOMPLETE
    row = verdict["rounds"][0]
    assert row["identity_ok"] is True, row["identity_problems"]  # 哈希确实对得上
    assert row["material_consistent"] is False, row
    assert any("材料兼容性重验不一致" in problem for problem in row["material_problems"]), \
        row["material_problems"]


def test_evidence_credit_requires_complete_evidence():
    """信用口径：判分通过 + 证据完整；材料不完整的一律不兑换（复审 §5 M1）。"""
    assert adm.evidence_credit({"pass": True,
                                "evidence_status": adm.EVIDENCE_COMPLETE}) is True
    assert adm.evidence_credit({"pass": True,
                                "evidence_status":
                                adm.EVIDENCE_MATERIAL_INCOMPLETE}) is False
    assert adm.evidence_credit({"pass": False,
                                "evidence_status": adm.EVIDENCE_COMPLETE}) is False
    assert adm.evidence_credit({}) is False

# ---------------------------------------------------------------------------
# 2. M2：行为签名与生产排序同口径（先定动作，后序列化；舍入只用于展示）
# ---------------------------------------------------------------------------

def test_preference_signature_matches_production_on_tiny_score_gaps():
    """复审 §5 M2 反例：分数 [0, 1e-10, 2e-10] 与正倍 1000 缩放。

    修复前：准入先 round(score, 9) → 三档塌成 0 → 首选退化成 action_key 升序
    （discard:1w），生产两次都选第三动作（pass）；×1000 的修订因此被当成
    REVISION_OBSERVED 并发放信用。
    """
    small = TINY_SCORER
    large = small.replace("0.0000000001", "0.0000001")
    for code in (small, large):
        assert (adm.preference_signature(code, ["sample"])["sample"]["action_key"]
                == _production_first(code, "sample") == "pass")
    # 舍入只出现在展示字段：原始分数保留 1e-10 的分档。
    block = adm.behavior_signature(small, ["sample"])["sample"]
    assert block["scores"] == {"discard:1w": 0.0, "hu": 1e-10, "pass": 2e-10}
    assert block["scores_display"] == {"discard:1w": 0.0, "hu": 0.0, "pass": 0.0}
    delta = adm.revision_behavior_delta(large, small, ["sample"])
    assert delta["verdict"] == adm.REVISION_EQUIVALENT, delta
    assert delta["credited"] is False
    assert delta["decision_changed_views"] == []


def test_window_table_production_admission_archive_agree():
    """逐窗对照表：小分差 / 真实平分 / 正比例缩放 / 整体平移下三方首选一致。

    三方口径：production（生产排序）、admission（preference_signature）、archive
    （P8 档案 sitin_search._av_behavior_signature，经同一份 behavior_signature）。
    """
    import sitin_search as search  # noqa: E402 —— P8 档案签名侧
    parent = _parent_code(PKG)
    views = _t06_views()
    transforms = {
        "tiny_gap": "VALUE * 0.00000000001",
        "ties": "0.0",
        "scale_1000": "VALUE * 1000.0",
        "translate_100": "VALUE + 100.0",
    }
    for name, expression in transforms.items():
        child = _wrapped(parent, expression)
        signature = adm.preference_signature(child, views)
        archive = {row["window_id"]: row["action_key"]
                   for row in search._av_behavior_signature(child)["windows"]}
        for view_name in views:
            chosen = _production_first(child, view_name)
            assert signature[view_name]["action_key"] == chosen, (
                name, view_name, signature[view_name], chosen)
            if view_name in archive:
                assert archive[view_name] == chosen, (name, view_name, archive)


def test_ordering_preserving_transforms_never_earn_revision_credit():
    """保序变换（1e-11 / 1e-8 / ×1000 / 整体平移）一律 EQUIVALENT、不发信用。"""
    parent = _parent_code(PKG)
    views = _t06_views()
    for factor in ("0.00000000001", "0.00000001", "1000.0"):
        child = _wrapped(parent, "VALUE * " + factor)
        delta = adm.revision_behavior_delta(child, parent, views)
        assert delta["verdict"] == adm.REVISION_EQUIVALENT, (factor, delta)
        assert delta["credited"] is False, (factor, delta)
        assert delta["decision_changed_views"] == [], (factor, delta)
    shifted = _wrapped(parent, "VALUE + 100.0")
    delta = adm.revision_behavior_delta(shifted, parent, views)
    assert delta["verdict"] == adm.REVISION_EQUIVALENT
    assert delta["credited"] is False


def test_preference_signature_reuses_production_function():
    """接线断言：准入的偏好排序就是生产函数的**同一对象**，不是第二份实现。"""
    from hangma_bot.policy import action_value as av
    assert adm.batch_to_ranked_candidates is av.batch_to_ranked_candidates
    assert "batch_to_ranked_candidates" in adm.PREFERENCE_ORDER_SOURCE
    records = adm.behavior_signature(TINY_SCORER, ["sample"])["sample"]
    assert records["order_source"] == adm.PREFERENCE_ORDER_SOURCE

# ---------------------------------------------------------------------------
# 3. 档案侧（P8）锁定：只消费已确定的首选动作，不重排、不舍入
# ---------------------------------------------------------------------------

def test_archive_signature_agrees_with_production_on_tiny_scores():
    """极小分差下 P8 档案签名也必须与生产首选一致（复审 §5 M2 反例的档案侧）。"""
    import sitin_search as search  # noqa: E402
    signature = search._av_behavior_signature(TINY_SCORER)
    assert signature["windows"], signature
    for row in signature["windows"]:
        assert row["action_key"] == _production_first(TINY_SCORER, row["window_id"]), \
            row


def test_archive_digest_does_not_rederive_from_scores():
    """档案摘要只读 window_id/action_key/missing：misleading scores 不得改变摘要。"""
    import sitin_archive as archive  # noqa: E402
    base = {"windows": [{"window_id": "sample", "action_key": "pass", "missing": False}]}
    same_action_other_scores = {"windows": [
        {"window_id": "sample", "action_key": "pass", "missing": False,
         "scores": {"pass": 0.0, "discard:1w": 999.0}}]}
    other_action = {"windows": [{"window_id": "sample", "action_key": "discard:1w",
                                 "missing": False}]}
    assert archive.behavior_signature_digest(base) == \
        archive.behavior_signature_digest(same_action_other_scores)
    assert archive.behavior_signature_digest(base) != \
        archive.behavior_signature_digest(other_action)
    assert "batch_to_ranked_candidates" in archive.BEHAVIOR_SIGNATURE_ORDER_SOURCE

def test_material_gate_cannot_be_bypassed_by_lowering_thresholds(tmp_path):
    """材料门与阈值无关：把门槛改小也不能让材料不兼容的包准入（不缩小分母的旁证）。

    「不得缩小冻结分母绕过门槛」的反向检验：即使有人改小 `manifest.thresholds`，
    材料不兼容仍必须阻断准入（status=INCOMPLETE）——门槛不属于本包的放行路径。
    """
    pkg = _package_copy(tmp_path, "pkg")
    manifest_path = pkg / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["thresholds"]["min_pass_per_round"] = 1
    manifest["thresholds"]["scorer_min_pass_per_round"] = 1
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    reports = []
    for index in (1, 2):
        replies = _synthetic_replies(pkg, Path(tmp_path) / ("replies-" + str(index)),
                                     str(index))
        report_path = Path(tmp_path) / ("grade-" + str(index) + ".json")
        reports.append(report_path)
        _grade(pkg, replies, report_path, "lowered-" + str(index))
    verdict = _summarize(pkg, reports, Path(tmp_path) / "verdict.json")
    assert verdict["thresholds"]["min_pass_per_round"] == 1
    assert all(row["pass_ok"] for row in verdict["rounds"])
    assert verdict["admission_pass"] is False, "门槛被改小后材料不兼容的包仍准入"
    assert verdict["status"] == adm.PACKAGE_INCOMPLETE

# ---------------------------------------------------------------------------
# 4. 评判语义版本串与门槛进入准入身份（Lead 2026-09-17 追加要求 1 / 2）
# ---------------------------------------------------------------------------

def test_executor_version_is_part_of_admission_identity(tmp_path, monkeypatch):
    """执行器版本属于评判语义：仅改版本串 → 旧报告 identity_ok 变 false；复原即恢复。

    为什么必须这样（Lead 追加要求 1）：父代材料兼容性与修订信用都是在**具体执行器
    语义**下得出的，执行器版本变化（例如 /4→/5 收紧结构拒绝对象）会改变同一候选的
    评分与首选动作，旧报告不能继续有效。这里用 monkeypatch 只改 `EXECUTOR_VERSION`
    常量（等价于一次真实升版，且不触碰 P1 的执行器文件），随后再复原做反向对照：
    身份内容不变时汇总必须**照常可用**，不得变成永久失效。
    """
    pkg = _package_copy(tmp_path, "pkg")
    replies = _synthetic_replies(pkg, Path(tmp_path) / "replies", "1")
    report_path = Path(tmp_path) / "grade.json"
    report = _grade(pkg, replies, report_path, "exec-v")
    assert report["identity"]["executor_version"] == adm.executor_version()
    assert report["identity"]["executor_version"] == str(adm.av_exec.EXECUTOR_VERSION)
    monkeypatch.setattr(adm.av_exec, "EXECUTOR_VERSION",
                        "action-value-executor/999-synthetic")
    bumped = _summarize(pkg, [report_path], Path(tmp_path) / "v-bumped.json")
    row = bumped["rounds"][0]
    assert row["identity_ok"] is False, row["identity_problems"]
    assert any("评分执行器版本不一致" in problem for problem in row["identity_problems"]), \
        row["identity_problems"]
    assert bumped["rounds"][0]["round_ok"] is False
    assert bumped["admission_pass"] is False
    assert bumped["executor_version"] == "action-value-executor/999-synthetic"
    monkeypatch.undo()
    recovered = _summarize(pkg, [report_path], Path(tmp_path) / "v-recovered.json")
    assert recovered["rounds"][0]["identity_ok"] is True, \
        recovered["rounds"][0]["identity_problems"]
    assert recovered["executor_version"] == adm.executor_version()


def test_threshold_change_is_part_of_admission_identity(tmp_path):
    """门槛属于评判语义：改门槛后旧报告不得复用（结论必须由重判重新得出）。

    判定（Lead 追加要求 2）：阈值改动会改变**同一份材料/回复**的通过结论（22/24 + 5/6
    与 21/24 + 3/6 可以给出相反结论），因此阈值必须进身份。做法：判分报告记录
    **产出时实际使用的门槛**（取自 manifest），汇总端要求它与当前 manifest 逐值一致；
    反向对照：在新门槛下重判后，汇总照常可用（不是永久失效）。
    """
    pkg = _package_copy(tmp_path, "pkg")
    replies = _synthetic_replies(pkg, Path(tmp_path) / "replies", "1")
    report_path = Path(tmp_path) / "grade-old.json"
    report = _grade(pkg, replies, report_path, "old-thresholds")
    assert report["summary"]["thresholds_source"] == "manifest"
    assert report["summary"]["thresholds"]["min_pass_per_round"] == 22
    manifest_path = pkg / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["thresholds"]["min_pass_per_round"] = 21
    manifest["thresholds"]["scorer_min_pass_per_round"] = 3
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    stale = _summarize(pkg, [report_path], Path(tmp_path) / "v-stale.json")
    row = stale["rounds"][0]
    assert row["identity_ok"] is False, row["identity_problems"]
    assert any("门槛集合不一致" in problem for problem in row["identity_problems"]), \
        row["identity_problems"]
    assert stale["admission_pass"] is False
    # 反向对照：在新门槛下重判 → 身份自洽，汇总恢复可用（材料门仍然独立生效）。
    fresh = Path(tmp_path) / "grade-new.json"
    regraded = _grade(pkg, replies, fresh, "new-thresholds")
    assert regraded["summary"]["thresholds"]["min_pass_per_round"] == 21
    recovered = _summarize(pkg, [fresh], Path(tmp_path) / "v-recovered.json")
    assert recovered["rounds"][0]["identity_ok"] is True, \
        recovered["rounds"][0]["identity_problems"]
    assert recovered["thresholds"]["min_pass_per_round"] == 21
    assert recovered["thresholds_sha256"] == regraded["summary"]["thresholds_sha256"]
    # 门槛放宽也**不能**绕过材料门：整包仍是 INCOMPLETE，不得准入。
    assert recovered["admission_pass"] is False
    assert recovered["status"] == adm.PACKAGE_INCOMPLETE
