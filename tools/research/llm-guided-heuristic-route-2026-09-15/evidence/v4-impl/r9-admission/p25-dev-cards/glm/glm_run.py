"""P25 瘦卡重跑 · 派发/审计/判分/修复/记录驱动（零模型）。

与长卡轮的流程**完全一致**，只把卡包换成 slim/package：
  * emit   —— sd.sealed_prompt 从**瘦卡包**重建密封题面；index.json 同时写 tasks/cards 两键
              （sealed_dispatch.do_audit 读 index["tasks"]）；
  * audit  —— 复用 sealed_dispatch.do_audit + do_veto；题面权威 frozen_rebuilt：
              首答 = 瘦卡构造器重建；修复 = **冻结构造器**（repair_prompt 的结构化诊断渲染）
              + **卡面入口**（build_action_value_repair_card_prompt，逐卡 focus）重建；
              重建值与派发目录逐字节比对；不放宽任何审计项；
  * grade  —— 直接调用长卡轮的 criterion.py（判据一行不改），只把 PACKAGE 指向瘦卡包；
  * repair —— 瘦修复提示词（材料逐字 + focus 前置）；
  * record —— 复用 record_dev_cards.py，PACKAGE 指向瘦卡包。

用法（仓库根，Python 用 .venv/bin/python）：
    glm_run.py emit
    glm_run.py audit  --plan P --first-replies R [--report J] --out O
    glm_run.py grade  --replies R --out O --dispatch-ledger L ...
    glm_run.py repair --report J --replies R --out D
    glm_run.py record --criterion C --audit A ... --out-json J --out-md M
"""
from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/llm-guided-heuristic-route-2026-09-15/evidence/v4-impl/r9-admission/p25-dev-cards/glm'

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
BASE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/v4-impl/r9-admission/p25-dev-cards')
ADMISSION = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/v4-impl/r9-admission')
ROUTE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15')
REPO = _PROJECT_ROOT
sys.path.insert(0, str(BASE))
sys.path.insert(0, str(ADMISSION))
sys.path.insert(0, str(_project_file(_PROJECT_ROOT, ADMISSION / "p25-headless")))
sys.path.insert(0, str(_project_file(_PROJECT_ROOT, ROUTE / "tools")))

import sealed_dispatch as sd                                     # noqa: E402
import repair_prompt as rp                                       # noqa: E402
import sitin_generate as gen                                     # noqa: E402
import criterion as criterion_mod                                # noqa: E402
import record_dev_cards as record_mod                            # noqa: E402

PKG = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/v4-impl/r9-admission/p25-dev-cards/glm/package')
DISPATCH = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/v4-impl/r9-admission/p25-dev-cards/glm/dispatch')
SESSIONS = _project_file(_PROJECT_ROOT, REPO / ".dsh-headless" / "sessions")


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def card_ids() -> list:
    return sorted(path.stem for path in (_project_file(_PROJECT_ROOT, PKG / "prompts")).glob("TD*.txt"))


def focus_of(task_id: str) -> dict:
    task = json.loads((_project_file(_PROJECT_ROOT, PKG / "tasks" / (task_id + ".json"))).read_text(encoding="utf-8"))
    return (task.get("slim") or {}).get("focus") or {}


def cmd_emit(args) -> int:
    tasks = args.tasks.split(",") if args.tasks else card_ids()
    rows = []
    for task_id in tasks:
        text = sd.sealed_prompt(task_id, PKG)
        target = _project_file(_PROJECT_ROOT, DISPATCH / task_id)
        target.mkdir(parents=True, exist_ok=True)
        (target / "prompt.txt").write_text(text, encoding="utf-8")
        rows.append({"task_id": task_id, "prompt_sha256": sha256_text(text),
                     "prompt_chars": len(text), "seal_clause": sd.SEAL_CLAUSE in text})
    index = {"schema": "sitin-sealed-dispatch-index/1", "seal_clause": sd.SEAL_CLAUSE,
             "dispatch_rule": "瘦卡密封题面由 sd.sealed_prompt 从 slim/package 重建（唯一权威）",
             "cards": rows, "tasks": rows}
    (_project_file(_PROJECT_ROOT, DISPATCH / "index.json")).write_text(json.dumps(index, ensure_ascii=False, indent=1),
                                         encoding="utf-8")
    print(json.dumps({"tasks": len(rows), "out": str(DISPATCH)}, ensure_ascii=False))
    return 0


def build_slim_repair(task: dict, first_reply: str, diagnostics) -> dict:
    """瘦修复提示词：冻结诊断渲染（repair_prompt）+ 卡面入口（build_action_value_repair_card_prompt）。

    决策卡（keyword）没有代码卡面入口：用同一 focus 的极简前置头 + 材料 + 要求。
    """
    card_id = str(task["task_id"])
    focus = focus_of(card_id)
    lines, stats = rp.render_diagnostics(task, diagnostics)
    added = "\n".join([rp.PROBLEM_HEADER, *lines, "", rp.requirement_text(rp.grader_kind(task))])
    tokens = rp.vocabulary_tokens(task)
    for _ in range(3):
        leaks = rp.leak_check(task, added)
        if not leaks:
            break
        added, extra = rp.redact(added, leaks)
        stats["redactions"].extend(extra)
    leaks = rp.leak_check(task, added)
    materials = "\n".join([rp.REPAIR_HEADER, first_reply.rstrip(), "", added])
    if str(task["validation"]["kind"]) == "keyword":
        head = "\n".join([
            "【本次目标与修改点（先读这一节）】",
            "  - 本次目标：" + str(focus.get("objective") or ""),
            "  - 本次修改点：" + str(focus.get("change_point") or ""),
            "  - 交付形态：与上一轮相同（中文短答；先结论后依据）。"])
        text = "\n".join([head, "", materials])
        identity = "keyword_head"
    else:
        # 按判分器 kind 决定输出条款：kind=code 的卡必须要求「一句话 + json 四字段 + python 围栏」，
        # 否则修复轮会被判 MECHANISM_FIELDS_MISSING（测量侧制造的失败）。
        text = gen.build_action_value_repair_card_prompt(
            materials, focus,
            grader_kind=(task.get("validation") or {}).get("kind") or "repair").text
        identity = "build_action_value_repair_card_prompt"
    if materials.rstrip("\n") not in text:
        raise AssertionError("瘦修复卡改写了材料正文：{0}".format(card_id))
    # **密封条款必须在**（评审 §2/卫生审计）：长卡轮的修复提示词继承自 sd.sealed_prompt，
    # 本路径自己拼卡面，必须显式补回 SEAL_CLAUSE 与 DELIVERY_CLAUSE，否则审计判 MISSING_SEAL
    # 并整批拒收（实测：本目录 invalid-repair-MISSING_SEAL/ 就是这样被 fail-closed 拦下的）。
    text = "\n".join([sd.SEAL_CLAUSE, "", text, "", sd.DELIVERY_CLAUSE])
    if sd.SEAL_MARKER not in text:
        raise AssertionError("瘦修复卡缺少密封条款：{0}".format(card_id))
    if sd.DELIVERY_CLAUSE not in text:
        raise AssertionError("瘦修复卡缺少交付方式条款：{0}".format(card_id))
    return {"text": text, "added": added, "stats": stats, "leaks": leaks,
            "materials_chars": len(materials), "identity": identity,
            "diagnostics_available": bool(stats.get("diagnostics_available")),
            "diagnostic_source": str(stats.get("source") or "structured")}


def cmd_repair(args) -> int:
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    report = json.loads(Path(args.report).read_text(encoding="utf-8"))
    only = set(args.tasks.split(",")) if args.tasks else None
    rows = []
    for row in report.get("tasks") or ():
        card_id = str(row.get("task_id"))
        if row.get("pass") or (only and card_id not in only):
            continue
        task = json.loads((_project_file(_PROJECT_ROOT, PKG / "tasks" / (card_id + ".json"))).read_text(encoding="utf-8"))
        reply = (Path(args.replies) / (card_id + ".txt")).read_text(encoding="utf-8")
        built = build_slim_repair(task, reply, row.get("diagnostics") or [])
        target = out_dir / card_id
        target.mkdir(parents=True, exist_ok=True)
        (target / "prompt.txt").write_text(built["text"], encoding="utf-8")
        rows.append({"task_id": card_id, "chars": len(built["text"]),
                     "materials_chars": built["materials_chars"],
                     "identity": built["identity"],
                     "diagnostics_available": built["diagnostics_available"],
                     "diagnostic_source": built["diagnostic_source"],
                     "diagnostic_stats": built["stats"], "leak_tokens": built["leaks"]})
    manifest = {"schema": "sitin-headless-repair-prompts/2",
                "generated_from": "冻结诊断渲染 + 卡面入口（逐卡 focus）",
                "diagnostics_available_tasks": sorted(r["task_id"] for r in rows
                                                      if r["diagnostics_available"]),
                "source_report": str(args.report), "replies": str(args.replies),
                "out": str(out_dir), "tasks": rows}
    (_project_file(_PROJECT_ROOT, HERE / "repair-prompts.json")).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({"tasks": len(rows),
                      "leaks": sum(len(r["leak_tokens"]) for r in rows),
                      "chars": {r["task_id"]: r["chars"] for r in rows},
                      "out": str(out_dir)}, ensure_ascii=False))
    return 0


def expected_prompts(plan, first_replies, report_path=None, repair_dir=None):
    report = (json.loads(Path(report_path).read_text(encoding="utf-8"))
              if report_path else {})
    by_task = {str(row.get("task_id")): row for row in (report.get("tasks") or [])}
    expected, rows = {}, []
    for item in plan:
        task_id, kind = str(item["task"]), str(item.get("kind") or "first")
        task = json.loads((_project_file(_PROJECT_ROOT, PKG / "tasks" / (task_id + ".json"))).read_text(encoding="utf-8"))
        if kind == "first":
            text = sd.sealed_prompt(task_id, PKG)
            source = "slim_card_builder:sd.sealed_prompt"
            dispatched_path = _project_file(_PROJECT_ROOT, DISPATCH / task_id / "prompt.txt")
        else:
            first_reply = (Path(first_replies) / (task_id + ".txt")).read_text(encoding="utf-8")
            built = build_slim_repair(task, first_reply,
                                      (by_task.get(task_id) or {}).get("diagnostics") or [])
            text = built["text"]
            source = "frozen_diagnostics+card_focus_repair"
            dispatched_path = Path(repair_dir or (_project_file(_PROJECT_ROOT, HERE / "repair-prompts"))) / task_id / "prompt.txt"
        digest = sha256_text(text)
        dispatched = dispatched_path.read_text(encoding="utf-8")
        rows.append({"task": task_id, "kind": kind, "source": source,
                     "rebuilt_sha256": digest, "dispatched_sha256": sha256_text(dispatched),
                     "identical": digest == sha256_text(dispatched),
                     "rebuilt_chars": len(text)})
        expected[(task_id, kind)] = digest
    return expected, rows


def session_request_config(run_id: str) -> dict:
    """从**会话痕迹**读该次请求实际生效的配置（身份的唯一权威来源）。"""
    for path in Path(SESSIONS).glob("*/" + run_id + "/session.jsonl.zstd"):
        info = sd.read_session_strict(path)
        for rec in info["records"]:
            if rec.get("type") != "request/header":
                continue
            header = (rec.get("data") or {}).get("header") or {}
            cfg = header.get("config")
            if isinstance(cfg, dict):
                return dict(cfg)
    return {}


def declared_identity(manifest: dict) -> dict:
    """**诊断身份**：manifest.diagnostic_route.declared_request_config（显式登记）。

    为什么需要它：无权限通道的冻结配置断言把 reasoningEffort/maxTokens 钉成**deepseek 通道
    常量**（CHANNEL_REASONING_EFFORT="max"、CHANNEL_MAX_TOKENS=256000）。换成 pi-ai 的
    glm 路由后，request/header 里没有 maxTokens 这一项（pi-ai 的 route 不写它），于是
    sd.expected_request_config() 造出的期望值与实测值不等 ⇒ PROTOCOL_REQUEST_CONFIG_MISMATCH。
    处理办法**不是放宽检查**，而是按 Lead 的口径：把**实测到的**配置登记成诊断专用身份
    （manifest + declared-identity.json），让检查有权威可对——检查照跑，任何一项不符仍然
    fail-closed（见 verify_identity_against_sessions）。
    """
    route = manifest.get("diagnostic_route") or {}
    config = route.get("declared_request_config")
    if not isinstance(config, dict) or not config:
        raise SystemExit("manifest 未登记诊断身份 declared_request_config（fail-closed）")
    return dict(config)


def verify_identity_against_sessions(plan, expected_config) -> dict:
    """逐会话核对：**每一次**请求的实测配置都必须等于登记的诊断身份（不符即 fail-closed）。"""
    rows, bad = [], []
    for item in plan:
        run_id = item.get("run_id")
        observed = session_request_config(run_id)
        same = observed == dict(expected_config)
        rows.append({"task": item.get("task"), "kind": item.get("kind"), "run_id": run_id,
                     "observed": observed, "declared": dict(expected_config), "match": same})
        if not same:
            bad.append(rows[-1])
    if bad:
        raise SystemExit("实测请求配置与登记的诊断身份不符（fail-closed）：{0}".format(
            json.dumps(bad, ensure_ascii=False)))
    return {"rows": rows, "all_match": True, "declared": dict(expected_config)}


def cmd_declare(args) -> int:
    """把**实测**配置登记成诊断身份，并由账本生成计划（plan）。"""
    ledger = json.loads(Path(args.ledger).read_text(encoding="utf-8"))
    calls = [c for c in (ledger.get("calls") or []) if c.get("exit_code") == 0 and c.get("run_id")]
    if not calls:
        raise SystemExit("账本里没有成功调用，无法登记诊断身份")
    configs = {json.dumps(c.get("request_config"), sort_keys=True, ensure_ascii=False)
               for c in calls}
    if len(configs) != 1:
        raise SystemExit("同一轮出现不一致的请求配置（fail-closed）：{0}".format(configs))
    declared = json.loads(next(iter(configs)))
    # 逐会话复核：账本自述不算数，以会话痕迹为准
    observations = {c["task"]: session_request_config(c["run_id"]) for c in calls}
    mismatched = {k: v for k, v in observations.items() if v != declared}
    if mismatched:
        raise SystemExit("会话实测配置与账本自述不一致（fail-closed）：{0}".format(
            json.dumps(mismatched, ensure_ascii=False)))
    manifest = json.loads((_project_file(_PROJECT_ROOT, PKG / "manifest.json")).read_text(encoding="utf-8"))
    manifest.setdefault("diagnostic_route", {})
    manifest["diagnostic_route"].update({
        "declared_request_config": declared,
        "declared_identity_source": "会话痕迹 request/header（逐条核对；账本自述不作数）",
        "declared_identity_note": ("**诊断身份，不是准入身份**：无权限通道的冻结配置断言钉的是"
                                   "deepseek 通道常量（effort=max / maxTokens=256000）；"
                                   "pi-ai 的 glm 路由不写 maxTokens，故按 Lead 口径把**实测**配置"
                                   "登记为诊断身份，让检查有权威可对；检查照跑，任何一项不符仍 fail-closed。"),
        "observed_tasks": sorted(observations),
    })
    (_project_file(_PROJECT_ROOT, PKG / "manifest.json")).write_text(json.dumps(manifest, ensure_ascii=False, indent=1),
                                       encoding="utf-8")
    plan = [{"task": c["task"], "kind": args.kind, "run_id": c["run_id"]} for c in calls]
    plan_path = Path(args.plan)
    plan_path.parent.mkdir(parents=True, exist_ok=True)
    plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=1), encoding="utf-8")
    out = {"schema": "sitin-p25-dev-cards-declared-identity/1",
           "declared_request_config": declared,
           "observed": observations,
           "ledger": str(args.ledger), "plan": str(plan_path),
           "note": "诊断身份（非准入身份）；来源 = 会话痕迹 request/header。"}
    Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({"declared": declared, "tasks": sorted(observations),
                      "plan": str(plan_path)}, ensure_ascii=False))
    return 0


def cmd_audit(args) -> int:
    plan = json.loads(Path(args.plan).read_text(encoding="utf-8"))
    manifest = json.loads((_project_file(_PROJECT_ROOT, PKG / "manifest.json")).read_text(encoding="utf-8"))
    # 诊断身份（实测登记）取代通道常量身份；检查本身不放宽：仍需逐项相等。
    config = args.expected_config_json and json.loads(args.expected_config_json) \
        or declared_identity(manifest)
    identity_check = verify_identity_against_sessions(plan, config)
    expected, rows = expected_prompts(plan, Path(args.first_replies), args.report,
                                      args.repair_prompts)
    if not all(row["identical"] for row in rows):
        raise SystemExit("重建题面与派发题面不一致（fail-closed）：{0}".format(
            json.dumps([r for r in rows if not r["identical"]], ensure_ascii=False)))
    rounds = sorted({str(item.get("kind") or "first") for item in plan})
    index = json.loads((_project_file(_PROJECT_ROOT, DISPATCH / "index.json")).read_text(encoding="utf-8"))
    planned = {str(item["task"]) for item in plan}
    index = dict(index, tasks=[r for r in index["tasks"] if r["task_id"] in planned],
                 rounds=rounds, note="按本轮计划重建的派发清单（只含本轮派发的题）")
    index_path = _project_file(_PROJECT_ROOT, DISPATCH / ("index-{0}.json".format("-".join(rounds))))
    index_path.write_text(json.dumps(index, ensure_ascii=False, indent=1), encoding="utf-8")
    audit = sd.do_audit(plan, Path(args.sessions_root), index_path=index_path,
                        expected_prompts=expected, expected_request_config=config)
    veto = sd.do_veto(audit)
    payload = {"schema": "sitin-p25-dev-cards-audit/1", "audit": audit, "veto": veto,
               "expected_prompts": rows, "expected_request_config": config,
               "identity_check": identity_check,
               "index_path": str(index_path),
               "prompt_authority": audit.get("prompt_authority"),
               "note": ("题面权威 = frozen_rebuilt（首答=瘦卡构造器；修复=冻结诊断+卡面入口）；"
                        "请求配置的权威 = **诊断身份**（manifest.diagnostic_route."
                        "declared_request_config，来源为会话 request/header 实测）；"
                        "检查逐项相等、任何不符 fail-closed —— 未放宽任何审计项。")}
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({"status": veto["status"], "clean": audit["clean"],
                      "accepted": audit["accepted"],
                      "blocked": [{"task": r["task_id"], "status": r["status"]}
                                  for r in audit["blocked"]],
                      "contaminated": [r["task_id"] for r in audit["contaminated"]],
                      "plan_problems": audit["plan_problems"],
                      "authority": audit.get("prompt_authority"), "out": str(out)},
                     ensure_ascii=False))
    return 0 if veto["admission_eligible"] else 2


def cmd_grade(args) -> int:
    criterion_mod.PACKAGE = PKG
    argv = ["criterion.py", "--replies", args.replies, "--out", args.out,
            "--round-label", args.round_label]
    for ledger in args.dispatch_ledger or []:
        argv += ["--dispatch-ledger", ledger]
    for ledger in args.ledger or []:
        argv += ["--ledger", ledger]
    saved = sys.argv
    try:
        sys.argv = argv
        return criterion_mod.main()
    finally:
        sys.argv = saved


def cmd_record(args) -> int:
    record_mod.PACKAGE = PKG
    argv = ["record_dev_cards.py", "--criterion", args.criterion,
            "--out-json", args.out_json, "--out-md", args.out_md]
    for path in args.audit or []:
        argv += ["--audit", path]
    for path in args.dispatch_ledger or []:
        argv += ["--dispatch-ledger", path]
    argv += ["--repair-prompts", str(_project_file(_PROJECT_ROOT, HERE / "repair-prompts.json"))]
    if args.verdict_json:
        argv += ["--verdict-json", args.verdict_json]
    saved = sys.argv
    try:
        sys.argv = argv
        return record_mod.main()
    finally:
        sys.argv = saved


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("emit")
    p.add_argument("--tasks", default=None)
    p.set_defaults(func=cmd_emit)
    p = sub.add_parser("declare")
    p.add_argument("--ledger", required=True, help="无权限通道派发账本（取实测 request_config）")
    p.add_argument("--plan", required=True, help="按账本生成的计划 JSON")
    p.add_argument("--kind", default="first")
    p.add_argument("--out", required=True, help="诊断身份登记产物")
    p.set_defaults(func=cmd_declare)
    p = sub.add_parser("audit")
    p.add_argument("--plan", required=True)
    p.add_argument("--first-replies", required=True)
    p.add_argument("--report", default=None)
    p.add_argument("--repair-prompts", default=str(_project_file(_PROJECT_ROOT, HERE / "repair-prompts")))
    p.add_argument("--sessions-root", default=str(SESSIONS))
    p.add_argument("--expected-config-json", default=None,
                   help="覆盖登记的诊断身份（缺省读 manifest.diagnostic_route）")
    p.add_argument("--out", required=True)
    p.set_defaults(func=cmd_audit)
    p = sub.add_parser("repair")
    p.add_argument("--report", required=True)
    p.add_argument("--replies", required=True)
    p.add_argument("--tasks", default=None)
    p.add_argument("--out", required=True)
    p.set_defaults(func=cmd_repair)
    p = sub.add_parser("grade")
    p.add_argument("--replies", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--round-label", default="slim-r1")
    p.add_argument("--dispatch-ledger", action="append", default=None)
    p.add_argument("--ledger", action="append", default=None)
    p.set_defaults(func=cmd_grade)
    p = sub.add_parser("record")
    p.add_argument("--criterion", required=True)
    p.add_argument("--audit", action="append", default=None)
    p.add_argument("--dispatch-ledger", action="append", default=None)
    p.add_argument("--out-json", required=True)
    p.add_argument("--out-md", required=True)
    p.add_argument("--verdict-json", default=None)
    p.set_defaults(func=cmd_record)
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
