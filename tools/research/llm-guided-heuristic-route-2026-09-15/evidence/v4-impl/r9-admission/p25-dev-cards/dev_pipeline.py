"""P25 小规模新调用诊断 · 开发卡的**派发/审计/记录**驱动（零模型）。

职责边界（复审 §3、S1/S3/S4）：
  * emit   —— 由**卡构造器**重建密封题面（sd.sealed_prompt，唯一权威），写 dispatch/<TID>/prompt.txt
              与 index.json；**不**读派发后的文件当权威（那是同一份来源，但审计侧会独立重建）。
  * audit  —— 卫生审计（sealed_dispatch.do_audit + do_veto）。题面权威一律走 **frozen_rebuilt**：
              首答由卡片构造器重建；修复轮由**冻结构造器** repair_prompt.build_repair_prompt
              （首答 + 结构化诊断）重建。计划自述的 prompt_sha256 只作待核数据。
              本脚本**不放宽**任何审计项：不传 allow_declared_authority、不降低协议断言。
  * record —— 把判据产物、审计/veto、真实用量汇总成逐卡记录（JSON + Markdown）。
"""
from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/llm-guided-heuristic-route-2026-09-15/evidence/v4-impl/r9-admission/p25-dev-cards'

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
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ADMISSION = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/v4-impl/r9-admission')
ROUTE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15')
REPO = _PROJECT_ROOT
sys.path.insert(0, str(ADMISSION))
sys.path.insert(0, str(_project_file(_PROJECT_ROOT, ADMISSION / "p25-headless")))
sys.path.insert(0, str(_project_file(_PROJECT_ROOT, ROUTE / "tools")))

import sealed_dispatch as sd                                     # noqa: E402
import repair_prompt as rp                                       # noqa: E402

PACKAGE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/v4-impl/r9-admission/p25-dev-cards/package')
DISPATCH = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/v4-impl/r9-admission/p25-dev-cards/dispatch')
SESSIONS = _project_file(_PROJECT_ROOT, REPO / ".dsh-headless" / "sessions")


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def card_ids() -> list:
    return sorted(path.stem for path in (_project_file(_PROJECT_ROOT, PACKAGE / "prompts")).glob("TD*.txt"))


def cmd_emit(args) -> int:
    tasks = args.tasks.split(",") if args.tasks else card_ids()
    rows = []
    for task_id in tasks:
        text = sd.sealed_prompt(task_id, PACKAGE)
        target = _project_file(_PROJECT_ROOT, DISPATCH / task_id)
        target.mkdir(parents=True, exist_ok=True)
        (target / "prompt.txt").write_text(text, encoding="utf-8")
        rows.append({"task_id": task_id, "prompt_sha256": sha256_text(text),
                     "prompt_chars": len(text), "seal_clause": sd.SEAL_CLAUSE in text})
    # 键名必须是 tasks：sealed_dispatch.do_audit 的派发清单核对读 index["tasks"]
    # （与 do_emit 的 schema 同形），否则审计在读取清单时 KeyError。
    index = {"schema": "sitin-sealed-dispatch-index/1", "seal_clause": sd.SEAL_CLAUSE,
             "dispatch_rule": "每卡密封题面由 sd.sealed_prompt 现场重建（唯一权威）",
             "cards": rows, "tasks": rows}
    (_project_file(_PROJECT_ROOT, DISPATCH / "index.json")).write_text(json.dumps(index, ensure_ascii=False, indent=1),
                                         encoding="utf-8")
    print(json.dumps({"tasks": len(rows), "out": str(DISPATCH)}, ensure_ascii=False))
    return 0


def expected_prompts(plan: list, first_replies: Path, report: Path = None,
                    repair_prompt_dir: Path = None) -> tuple:
    """冻结构造器重建的预期题面摘要：(expected, rows)。

    首答：sd.sealed_prompt(task_id, PACKAGE)（卡构造器路径）；
    修复：repair_prompt.build_repair_prompt(任务, 首答密封题面, 首答原文, 结构化诊断)。
    重建值同时与派发目录里的 prompt.txt 逐字节比对（不一致即 fail-closed）。
    """
    report_data = json.loads(Path(report).read_text(encoding="utf-8")) if report else {}
    by_task = {str(row.get("task_id")): row for row in (report_data.get("tasks") or [])}
    expected, rows = {}, []
    for item in plan:
        task_id, kind = str(item["task"]), str(item.get("kind") or "first")
        task = json.loads((_project_file(_PROJECT_ROOT, PACKAGE / "tasks" / (task_id + ".json"))).read_text(encoding="utf-8"))
        sealed = sd.sealed_prompt(task_id, PACKAGE)
        if kind == "first":
            text, source = sealed, "card_builder:sd.sealed_prompt"
        else:
            first_reply = (Path(first_replies) / (task_id + ".txt")).read_text(encoding="utf-8")
            built = rp.build_repair_prompt(task, sealed, first_reply,
                                           (by_task.get(task_id) or {}).get("diagnostics") or [])
            text = built["text"]
            source = "frozen_constructor:repair_prompt.build_repair_prompt"
        digest = sha256_text(text)
        # 逐字节比对的对象随轮次不同：首答对 dispatch/<tid>/prompt.txt（卡构造器产物），
        # 修复轮对 repair-prompts/<tid>/prompt.txt（冻结构造器产物）。
        if kind == "first":
            dispatched_path = _project_file(_PROJECT_ROOT, DISPATCH / task_id / "prompt.txt")
        else:
            dispatched_path = Path(repair_prompt_dir or (_project_file(_PROJECT_ROOT, HERE / "repair-prompts")))                 / task_id / "prompt.txt"
        dispatched = dispatched_path.read_text(encoding="utf-8")
        rows.append({"task": task_id, "kind": kind, "source": source,
                     "rebuilt_sha256": digest,
                     "dispatched_sha256": sha256_text(dispatched),
                     "identical": digest == sha256_text(dispatched),
                     "rebuilt_chars": len(text)})
        expected[(task_id, kind)] = digest
    return expected, rows


def cmd_audit(args) -> int:
    plan = json.loads(Path(args.plan).read_text(encoding="utf-8"))
    manifest = json.loads((_project_file(_PROJECT_ROOT, PACKAGE / "manifest.json")).read_text(encoding="utf-8"))
    config = sd.expected_request_config(manifest.get("target_model"))
    expected, rows = expected_prompts(plan, Path(args.first_replies), args.report,
                                      repair_prompt_dir=Path(args.repair_prompts))
    if not all(row["identical"] for row in rows):
        raise SystemExit("重建题面与派发题面不一致（fail-closed）：{0}".format(
            json.dumps([r for r in rows if not r["identical"]], ensure_ascii=False)))
    # 派发清单按**本轮实际派发的题**重建：do_audit 用清单核对"清单里的题是否都被计划覆盖"，
    # 修复轮只派 2 题，拿 6 题的清单去核对会把整批判 INVALID（那是清单用错，不是证据问题）。
    rounds = sorted({str(item.get("kind") or "first") for item in plan})
    index = json.loads((_project_file(_PROJECT_ROOT, DISPATCH / "index.json")).read_text(encoding="utf-8"))
    planned = {str(item["task"]) for item in plan}
    index = dict(index, tasks=[row for row in index["tasks"] if row["task_id"] in planned],
                 cards=[row for row in index.get("cards", []) if row["task_id"] in planned],
                 rounds=rounds,
                 note="按本轮计划重建的派发清单（只含本轮派发的题）")
    index_path = _project_file(_PROJECT_ROOT, DISPATCH / ("index-{0}.json".format("-".join(rounds))))
    index_path.write_text(json.dumps(index, ensure_ascii=False, indent=1), encoding="utf-8")
    audit = sd.do_audit(plan, Path(args.sessions_root),
                        index_path=index_path,
                        expected_prompts=expected, expected_request_config=config)
    veto = sd.do_veto(audit)
    payload = {
        "schema": "sitin-p25-dev-cards-audit/1",
        "audit": audit, "veto": veto,
        "expected_prompts": rows,
        "expected_request_config": config,
        "index_path": str(index_path),
        "index_tasks": sorted(row["task_id"] for row in index["tasks"]),
        "prompt_authority": audit.get("prompt_authority"),
        "note": ("题面权威 = frozen_rebuilt（首答=卡构造器；修复=冻结构造器+首答+诊断）；"
                 "计划自述只作待核数据；未放宽任何审计项。"),
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({"status": veto["status"], "clean": audit["clean"],
                      "accepted": audit["accepted"],
                      "blocked": [{"task": r["task_id"], "status": r["status"]}
                                  for r in audit["blocked"]],
                      "contaminated": [r["task_id"] for r in audit["contaminated"]],
                      "plan_problems": audit["plan_problems"],
                      "authority": audit.get("prompt_authority"),
                      "out": str(out)}, ensure_ascii=False))
    return 0 if veto["admission_eligible"] else 2


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("emit")
    p.add_argument("--tasks", default=None)
    p.set_defaults(func=cmd_emit)
    p = sub.add_parser("audit")
    p.add_argument("--plan", required=True)
    p.add_argument("--first-replies", required=True)
    p.add_argument("--report", default=None, help="修复轮的判分报告（取结构化诊断）")
    p.add_argument("--repair-prompts", default=str(_project_file(_PROJECT_ROOT, HERE / "repair-prompts")),
                   help="冻结构造器产出的修复提示词目录（逐字节比对对象）")
    p.add_argument("--sessions-root", default=str(SESSIONS))
    p.add_argument("--out", required=True)
    p.set_defaults(func=cmd_audit)
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
