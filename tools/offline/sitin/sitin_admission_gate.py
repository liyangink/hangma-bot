"""模型准入的**唯一正式出口**（评审 C3；P25 包 C 收口 S1–S3）。

为什么要它：底层 grade/summarize 只用**报告自述**的身份做对账，不重验真实提示词、
不消费卫生判词、目标模型直接取当前 manifest。更早的出口还留下三处"看得见却绑不住"的缺口
（P25 复审 S1–S3）：预期题面取计划自述、答卷按整批摘要集合匹配、会话结束与模型身份混用。
本工具把这些来源全部**从冻结材料重算**，任一不符即具名阻断、不产生准入资格。

P25 包 C 的三条收口口径：
  1. **S1 题面绑定**：首答预期输入**只能从冻结包重建**（sealed_dispatch.sealed_prompt）；
     修复轮预期输入**只能从冻结构造器 + 首答 + 诊断产物重建**（本轮判分报告的 problems 经
     p25-headless/repair_prompt.build_repair_prompt）。计划里的 prompt_sha256 降级为
     **待核数据**：与冻结重建不一致即整批阻断（计划问题）。
  2. **S2 逐项绑定**：复用判分器**同一个**答卷定位函数（sitin_model_admission.find_reply）
     建立 (批次, 题目, first/repair) 唯一记录；答卷字节必须等于该会话**终止回合内**的答卷
     摘要；.md 与 .txt 同等对待；存在修复文件就必须存在**唯一**修复会话与**前驱首答**。
  3. **S3 单请求协议**：每个会话恰好一次 request/header、一次 turn/end、终止后无工作事件，
     请求配置必须与冻结 provider/model/effort/maxTokens 一致；题面之外的额外上下文块/
     未登记 user 消息一律阻断。

绑定清单（缺一不可）：
  1. 题面**文件字节** == 任务 JSON 自述的 prompt_sha256；
  2. **实际投递的提示词** == 冻结重建值（首答=冻结包；修复=冻结构造器+首答+诊断产物）；
  3. **卫生判词**：本轮 audit/veto 必须 CLEAN，且被判分的每一题都在 accepted 里；
  4. **逐项来源绑定**：每个被判分的答复文件，必须对应该 (题目, 类型) 的唯一 CLEAN 会话；
  5. **真实模型身份**：从会话 request/header 读 provider/model/reasoningEffort/maxTokens，
     必须唯一且与 manifest 的 target_model + 通道身份一致；
  6. **两轮独立**：run_id 集合不相交、轮次摘要不同；
  7. **判分器/门槛身份**：与当前冻结版本一致。

诊断产物（grade 的报告、summarize 的 verdict）**永远**不构成准入资格；
只有本工具产出的 envelope 且 formal_admission=true 才是。
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

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

HERE = Path(__file__).resolve().parent
ROUTE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15')
ADMISSION_DIR = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/v4-impl/r9-admission')
REPAIR_DIR = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/v4-impl/r9-admission/p25-headless')
for path in (HERE, ADMISSION_DIR, REPAIR_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import sitin_model_admission as adm                     # noqa: E402
import sealed_dispatch as sd                            # noqa: E402

try:                                                    # 冻结构造器（修复题面重建）
    import repair_prompt as rp                          # noqa: E402
    REPAIR_IMPORT_ERROR = None
except Exception as exc:                                # noqa: BLE001
    rp = None
    REPAIR_IMPORT_ERROR = "{0}: {1}".format(type(exc).__name__, exc)

#: 出口 schema（/2 = P25 包 C：冻结题面权威 + 逐项来源绑定 + 单请求协议）。
ENVELOPE_SCHEMA = "sitin-model-admission-envelope/2"


def repair_constructor_identity() -> Dict[str, Any]:
    """冻结构造器身份（文件字节摘要 + 诊断 schema）：修复题面的重建必须可复现。

    为什么修复侧要单独记身份：修复提示词的正文由**构造器**决定，构造器一改（例如 C2 把
    文本 problems 换成结构化诊断），同一轮归档就再也重建不出原题面——那是"身份变了"，
    必须被看见，而不是让出口悄悄接受旧题面。
    """
    if rp is None:
        return {"available": False, "error": REPAIR_IMPORT_ERROR}
    path = Path(getattr(rp, "__file__", "") or "")
    return {"available": True, "path": str(path),
            "sha256": (sha256_file(path) if path.is_file() else None),
            "diagnostic_schema": getattr(rp, "DIAGNOSTIC_SCHEMA", None),
            "import_error": None}


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _parse_round(spec: str) -> Dict[str, str]:
    parts = spec.split(":")
    if len(parts) != 3:
        raise SystemExit("--round 需要 LABEL:REPLIES_DIR:PLAN_JSON，得到 {0!r}".format(spec))
    label, replies, plan = parts
    return {"label": label, "replies": replies, "plan": plan}


def _reply_targets(replies_dir: Path, task_ids: Sequence[str]) -> Dict[Tuple[str, str], Path]:
    """**复用判分器的答卷定位函数**：{(题目, 类型): 答卷文件}（.txt/.md 同等对待）。

    为什么必须复用：判分器与出口若各自枚举文件，就会出现"判分器消费了 .md、出口只检查
    .txt"的漏检（P25 复审 S2 反例③）。这里逐题调用 find_reply，两者的产物清单同源。
    """
    targets: Dict[Tuple[str, str], Path] = {}
    for task_id in task_ids:
        first = adm.find_reply(replies_dir, task_id)
        if first is not None:
            targets[(task_id, "first")] = first
        repair = adm.find_reply(replies_dir, task_id, repair=True)
        if repair is not None:
            targets[(task_id, "repair")] = repair
    return targets


def _grade_round(package_dir: Path, replies_dir: Path, label: str,
                 out_path: Path) -> Tuple[Optional[Dict[str, Any]], str]:
    """走**冻结判分器**判分（诊断产物：供修复题面重建与 summarize 消费，不构成准入资格）。"""
    cmd = [sys.executable, str(_project_file(_PROJECT_ROOT, HERE / "sitin_model_admission.py")), "grade",
           "--package-dir", str(package_dir), "--replies", str(replies_dir),
           "--round-label", label, "--out", str(out_path)]
    proc = subprocess.run(cmd, cwd=str(ROUTE), capture_output=True, text=True)
    if proc.returncode != 0 or not out_path.is_file():
        return None, proc.stderr[-400:]
    return json.loads(out_path.read_text(encoding="utf-8")), ""


def _expected_prompts(package_dir: Path, tasks: Dict[str, Dict[str, Any]],
                      replies_dir: Path, report: Optional[Dict[str, Any]],
                      label: str, blockers: List[Dict[str, Any]]
                      ) -> Tuple[Dict[Tuple[str, str], str], List[Dict[str, Any]]]:
    """S1：题面预期值**只从冻结材料重建**；重建不出来即具名阻断（不回退计划自述）。

    - 首答：冻结包（sealed_prompt）逐字重建；
    - 修复：冻结构造器 + **首答正文** + **诊断产物**（本轮判分报告的 problems）逐字重建。
    """
    expected: Dict[Tuple[str, str], str] = {}
    rows: List[Dict[str, Any]] = []
    for task_id in sorted(tasks):
        try:
            expected[(task_id, "first")] = sd.frozen_prompt_sha256(task_id, package_dir)
        except OSError as exc:
            blockers.append({"code": "PROMPT_UNDERIVABLE", "round": label, "task": task_id,
                             "kind": "first",
                             "detail": "冻结包题面读不到：{0}".format(exc)})
    report_rows = {str(row.get("task_id")): row
                   for row in ((report or {}).get("tasks") or [])}
    for (task_id, kind), path in sorted(_reply_targets(replies_dir, sorted(tasks)).items()):
        if kind != "repair":
            continue
        first_path = adm.find_reply(replies_dir, task_id)
        if first_path is None:
            blockers.append({"code": "REPAIR_WITHOUT_FIRST_REPLY", "round": label,
                             "task": task_id,
                             "detail": "存在修复文件但缺前驱首答：无法按冻结构造器重建"})
            continue
        if rp is None:
            blockers.append({"code": "REPAIR_REBUILD_UNAVAILABLE", "round": label,
                             "task": task_id, "detail": REPAIR_IMPORT_ERROR})
            continue
        row = report_rows.get(task_id) or {}
        # 诊断产物：优先**结构化诊断**（C2 口径：tasks[].diagnostics），退回文本 problems
        # （旧口径报告）。两者都不在时按空表重建，仍要求与投递题面逐字一致——不一致即阻断。
        source = "diagnostics" if row.get("diagnostics") else "problems"
        diagnostics = row.get("diagnostics") or row.get("problems") or []
        try:
            built = rp.build_repair_prompt(
                tasks[task_id], sd.sealed_prompt(task_id, package_dir),
                first_path.read_text(encoding="utf-8"), diagnostics)
        except Exception as exc:                            # noqa: BLE001 失败关闭
            blockers.append({"code": "REPAIR_REBUILD_FAILED", "round": label,
                             "task": task_id,
                             "detail": "{0}: {1}".format(type(exc).__name__, exc)[:300]})
            continue
        expected[(task_id, "repair")] = sha256_text(built["text"])
        rows.append({"task_id": task_id, "file": path.name,
                     "first_reply_file": first_path.name,
                     "diagnostic_source": source,
                     "diagnostics_sha256": row.get("diagnostics_sha256"),
                     "source_report_problems": len(row.get("problems") or []),
                     "expected_prompt_sha256": expected[(task_id, "repair")],
                     "derivation": ("冻结包题面 + 首答正文 + 本轮诊断产物，"
                                    "经 p25-headless/repair_prompt.build_repair_prompt 逐字重建")})
    return expected, rows


def admit(args) -> Tuple[Dict[str, Any], int]:
    package_dir = Path(args.package_dir)
    rounds = [_parse_round(spec) for spec in args.round]
    sessions_root = Path(args.sessions_root).expanduser()
    blockers: List[Dict[str, Any]] = []
    index_path = (Path(args.index) if args.index
                  else _project_file(_PROJECT_ROOT, ADMISSION_DIR / "sealed-dispatch" / "dispatch" / "index.json"))

    manifest = json.loads((package_dir / "manifest.json").read_text(encoding="utf-8"))
    tasks = {}
    for path in sorted((package_dir / "tasks").glob("T*.json")):
        task = json.loads(path.read_text(encoding="utf-8"))
        tasks[task["task_id"]] = task
    # 冻结请求身份：provider/model 取题包 manifest，effort/maxTokens 取通道常量（S3）。
    expected_config = sd.expected_request_config(manifest.get("target_model"))

    # ---- 1) 题面文件字节 vs 任务 JSON 自述 ----
    prompt_rows, drift = [], []
    for task_id, task in sorted(tasks.items()):
        body_path = package_dir / task.get("prompt_file", "prompts/{0}.txt".format(task_id))
        actual = sha256_file(body_path) if body_path.is_file() else None
        declared = task.get("prompt_sha256")
        try:
            sealed = sd.frozen_prompt_sha256(task_id, package_dir)
        except OSError:
            sealed = None
        prompt_rows.append({"task_id": task_id, "file": str(body_path),
                            "actual_body_sha256": actual, "declared_body_sha256": declared,
                            "sealed_prompt_sha256": sealed})
        if declared and actual != declared:
            drift.append(task_id)
    if drift:
        blockers.append({"code": "PROMPT_FILE_DRIFT",
                         "detail": "题面文件字节与任务 JSON 自述不一致", "tasks": drift})
    bindings: Dict[str, Any] = {"prompts": {"tasks": len(prompt_rows), "rows": prompt_rows}}

    # ---- 2~5) 逐轮：判分 → 冻结题面重建 → 卫生审计 → 逐项来源绑定 → 模型身份 ----
    round_rows, report_paths = [], []
    with tempfile.TemporaryDirectory() as tmp:
        for spec in rounds:
            label = spec["label"]
            replies_dir, plan_path = Path(spec["replies"]), Path(spec["plan"])
            plan = json.loads(plan_path.read_text(encoding="utf-8"))
            report_path = Path(tmp) / ("report-{0}.json".format(label))
            report, grade_error = _grade_round(package_dir, replies_dir, label, report_path)
            if report is None:
                blockers.append({"code": "GRADE_FAILED", "round": label,
                                 "stderr": grade_error})
                round_rows.append({"round_label": label, "replies_dir": str(replies_dir),
                                   "plan": str(plan_path), "veto_status": None,
                                   "run_ids": sorted({item["run_id"] for item in plan}),
                                   "answers": [], "note": "判分失败，未进入绑定"})
                continue
            expected_prompts, repair_rows = _expected_prompts(
                package_dir, tasks, replies_dir, report, label, blockers)
            audit = sd.do_audit(plan, sessions_root, index_path=index_path,
                                expected_prompts=expected_prompts,
                                expected_request_config=expected_config)
            veto = sd.do_veto(audit)
            targets = _reply_targets(replies_dir, sorted(tasks))
            row: Dict[str, Any] = {
                "round_label": label, "replies_dir": str(replies_dir),
                "plan": str(plan_path),
                "veto_status": veto["status"], "accepted": sorted(audit["accepted"]),
                "blocking_kinds": veto["blocking_kinds"],
                "graded_tasks": sorted(t for (t, k) in targets if k == "first"),
                "repair_tasks": sorted(t for (t, k) in targets if k == "repair"),
                "run_ids": sorted({item["run_id"] for item in plan}),
                "plan_problems": audit["plan_problems"],
                "prompt_authority": audit.get("prompt_authority"),
                "expected_request_config": audit.get("expected_request_config"),
                "repair_prompt_rebuilds": repair_rows,
            }
            if veto["status"] != "CLEAN":
                blockers.append({"code": "HYGIENE_NOT_CLEAN", "round": label,
                                 "detail": veto["status"], "kinds": veto["blocking_kinds"],
                                 "blocked_tasks": veto["blocked_tasks"],
                                 "contaminated_tasks": veto["contaminated_tasks"],
                                 "plan_problems": audit["plan_problems"]})
            # ---- S2：逐项（题目 × 类型）来源绑定，答卷/会话/题面/前驱首答逐项一致 ----
            accepted_rows: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}
            for arow in audit["rows"]:
                if arow["status"] in sd.ADMISSION_STATUSES:
                    key = (str(arow["task_id"]), str(arow.get("kind") or "first"))
                    accepted_rows.setdefault(key, []).append(arow)
            duplicates = sorted("{0}/{1}".format(*key) for key, rows_
                                in accepted_rows.items() if len(rows_) > 1)
            if duplicates:
                blockers.append({"code": "DUPLICATE_ACCEPTED_SESSION", "round": label,
                                 "attempts": duplicates,
                                 "detail": "同一 (题目, 类型) 有多条 CLEAN 会话：来源不唯一"})
            answer_rows = []
            for key in sorted(targets):
                path = targets[key]
                digest = sha256_file(path)
                rows_ = accepted_rows.get(key) or []
                entry: Dict[str, Any] = {"task_id": key[0], "kind": key[1],
                                         "file": path.name, "sha256": digest,
                                         "session_count": len(rows_)}
                if len(rows_) != 1:
                    entry.update({"bound": False,
                                  "reason": "该 (题目, 类型) 没有唯一 CLEAN 会话"})
                    blockers.append({"code": "ANSWER_NOT_BOUND_TO_SESSION", "round": label,
                                     "task": key[0], "kind": key[1], "file": path.name,
                                     "sessions": len(rows_)})
                    answer_rows.append(entry)
                    continue
                arow = rows_[0]
                entry.update({"run_id": arow["run_id"],
                              "prompt_authority": arow.get("prompt_authority"),
                              "session_prompt_sha256": arow.get("prompt_sha256"),
                              "expected_prompt_sha256": arow.get("expected_prompt_sha256"),
                              "plan_prompt_sha256": arow.get("plan_prompt_sha256"),
                              "session_answer_sha256": arow.get("terminated_answer_sha256"),
                              "answer_is_terminated": arow.get("answer_is_terminated")})
                if not arow.get("answer_is_terminated"):
                    entry.update({"bound": False, "reason": "答卷不在终止回合内"})
                    blockers.append({"code": "ANSWER_NOT_TERMINATED", "round": label,
                                     "task": key[0], "kind": key[1], "run_id": arow["run_id"]})
                elif digest != arow.get("terminated_answer_sha256"):
                    entry.update({"bound": False,
                                  "reason": "答卷字节 ≠ 该会话终止回合内交付的答卷"})
                    blockers.append({"code": "ANSWER_SESSION_MISMATCH", "round": label,
                                     "task": key[0], "kind": key[1], "file": path.name,
                                     "run_id": arow["run_id"]})
                elif arow.get("prompt_sha256") != arow.get("expected_prompt_sha256"):
                    entry.update({"bound": False, "reason": "题面 ≠ 冻结重建值"})
                    blockers.append({"code": "PROMPT_NOT_FROZEN", "round": label,
                                     "task": key[0], "kind": key[1],
                                     "run_id": arow["run_id"]})
                else:
                    entry["bound"] = True
                answer_rows.append(entry)
            row["answers"] = answer_rows
            # ---- 修复 ↔ 前驱首答 ↔ 唯一修复调用 ----
            repair_files = {t for (t, k) in targets if k == "repair"}
            first_files = {t for (t, k) in targets if k == "first"}
            repair_sessions = {t for (t, k) in accepted_rows if k == "repair"}
            missing_repair_session = sorted(repair_files - repair_sessions)
            if missing_repair_session:
                blockers.append({"code": "REPAIR_FILE_WITHOUT_SESSION", "round": label,
                                 "tasks": missing_repair_session,
                                 "detail": "存在修复文件但没有对应的修复调用（修复会话）"})
            orphan_repairs = sorted(repair_files - first_files)
            if orphan_repairs:
                blockers.append({"code": "REPAIR_WITHOUT_FIRST_REPLY", "round": label,
                                 "tasks": orphan_repairs,
                                 "detail": "存在修复文件但没有前驱首答：来源链断裂"})
            dangling = sorted(repair_sessions - repair_files)
            if dangling:
                blockers.append({"code": "REPAIR_SESSION_WITHOUT_REPLY", "round": label,
                                 "tasks": dangling,
                                 "detail": "存在修复调用但没有交付修复文件：判分材料与调用不一致"})
            # ---- S3：模型身份取 accepted 会话的单请求协议配置 ----
            identities: Dict[str, int] = {}
            by_session = []
            for key in sorted(accepted_rows):
                for arow in accepted_rows[key]:
                    config = (arow.get("protocol") or {}).get("request_config")
                    if not isinstance(config, dict):
                        blockers.append({"code": "MODEL_IDENTITY_UNREADABLE", "round": label,
                                         "task": key[0], "run_id": arow.get("run_id")})
                        continue
                    digest = json.dumps(config, sort_keys=True, ensure_ascii=False)
                    identities[digest] = identities.get(digest, 0) + 1
                    by_session.append({"task_id": key[0], "kind": key[1],
                                       "run_id": arow.get("run_id"), "config": config})
            row["model_identities"] = by_session
            row["distinct_model_identities"] = sorted(identities)
            if len(identities) != 1:
                blockers.append({"code": "MODEL_IDENTITY_NOT_UNIQUE", "round": label,
                                 "distinct": sorted(identities)})
            else:
                actual = json.loads(next(iter(identities)))
                declared_model = (manifest.get("target_model") or {}).get("model")
                declared_provider = (manifest.get("target_model") or {}).get("provider")
                if (actual.get("model") != declared_model
                        or actual.get("provider") != declared_provider):
                    blockers.append({"code": "MODEL_IDENTITY_MISMATCH", "round": label,
                                     "declared": {"provider": declared_provider,
                                                  "model": declared_model},
                                     "actual": actual})
                if args.expect_model and actual.get("model") != args.expect_model:
                    blockers.append({"code": "MODEL_EXPECTATION_MISMATCH", "round": label,
                                     "expected": args.expect_model, "actual": actual.get("model")})
            round_rows.append(row)
            report_paths.append(str(report_path))

        # ---- 6) 两轮独立 ----
        if len(round_rows) >= 2:
            for i in range(len(round_rows)):
                for j in range(i + 1, len(round_rows)):
                    left, right = round_rows[i], round_rows[j]
                    shared = sorted(set(left["run_ids"]) & set(right["run_ids"]))
                    if shared:
                        blockers.append({"code": "ROUNDS_NOT_INDEPENDENT",
                                         "detail": "两轮共用会话（不是独立调用）",
                                         "rounds": [left["round_label"], right["round_label"]],
                                         "shared_run_ids": shared})
        # ---- 7) 汇总（走冻结判分器；复用本轮判分报告，不重复判分）----
        verdict = None
        if len(report_paths) == len(round_rows) and report_paths:
            verdict_out = Path(tmp) / "verdict.json"
            cmd = [sys.executable, str(_project_file(_PROJECT_ROOT, HERE / "sitin_model_admission.py")), "summarize"]
            for path in report_paths:
                cmd += ["--report", path]
            # **必须显式传 --manifest**：summarize 不带该参数时用的是模块内默认包
            # （不是刚判分的那个包），身份对账会在错误的材料上做。
            cmd += ["--manifest", str(package_dir / "manifest.json")]
            cmd += ["--out", str(verdict_out)]
            proc = subprocess.run(cmd, cwd=str(ROUTE), capture_output=True, text=True)
            if proc.returncode == 0 and verdict_out.is_file():
                verdict = json.loads(verdict_out.read_text(encoding="utf-8"))

    current_grader = adm.grader_sha256()
    if verdict is None:
        blockers.append({"code": "SUMMARIZE_FAILED"})
    else:
        if verdict.get("grader_sha256") != current_grader:
            blockers.append({"code": "GRADER_IDENTITY_MISMATCH",
                             "verdict": verdict.get("grader_sha256"),
                             "current": current_grader})
        declared_model = (manifest.get("target_model") or {})
        if verdict.get("target_model") != declared_model:
            blockers.append({"code": "TARGET_MODEL_MISMATCH"})

    bindings_ok = not blockers
    admitted = bool(bindings_ok and verdict
                    and verdict.get("status") == "ADMISSION_PASS"
                    and verdict.get("admission_pass") is True)
    if bindings_ok and not admitted:
        blockers.append({"code": "VERDICT_NOT_ADMISSION_PASS",
                         "status": (verdict or {}).get("status"),
                         "reasons": (verdict or {}).get("blocking_reasons")})
    envelope = {
        "schema": ENVELOPE_SCHEMA,
        "bindings_ok": bindings_ok,
        "formal_admission": admitted,
        "diagnostic_only": False,
        "blockers": blockers,
        "package_dir": str(package_dir),
        "manifest_identity": {k: manifest.get(k) for k in
                              ("schema", "identity", "thresholds", "target_model")},
        "expected_request_config": expected_config,
        "bindings": {"rounds": round_rows, "prompts": bindings["prompts"],
                     "grader_sha256": current_grader,
                     "prompt_authority": ("首答=冻结包重建；修复=冻结构造器+首答+诊断产物重建；"
                                          "计划自述只作待核数据"),
                     "answer_locator": "sitin_model_admission.find_reply（与判分器同源）",
                     "repair_constructor": repair_constructor_identity()},
        "verdict": verdict,
        "note": ("这是模型准入的**唯一正式出口**。formal_admission=false 时，"
                 "任何判分器报告或 summarize 输出都只是诊断读数，不构成准入资格；"
                 "诊断产物永不产生正式准入。"),
    }
    return envelope, (0 if envelope["formal_admission"] else 2)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("admit", help="唯一正式准入出口")
    p.add_argument("--package-dir", required=True)
    p.add_argument("--round", action="append", required=True,
                   help="LABEL:REPLIES_DIR:PLAN_JSON（可重复，至少两条）")
    p.add_argument("--sessions-root", default=str(Path.home() / ".dsh" / "sessions"))
    p.add_argument("--expect-model", default=None)
    p.add_argument("--index", default=None,
                   help="派发清单（默认用 r9-admission 的 sealed-dispatch/dispatch/index.json）")
    p.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    envelope, code = admit(args)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(envelope, ensure_ascii=False, indent=1),
                              encoding="utf-8")
    print(json.dumps({"bindings_ok": envelope["bindings_ok"],
                      "formal_admission": envelope["formal_admission"],
                      "verdict": (envelope.get("verdict") or {}).get("status"),
                      "blockers": [b["code"] for b in envelope["blockers"]],
                      "out": args.out}, ensure_ascii=False))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
