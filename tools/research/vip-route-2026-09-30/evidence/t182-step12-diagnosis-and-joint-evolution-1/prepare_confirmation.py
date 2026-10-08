"""T182 唯一候选的独立确认准备；开发未完整闭合/未选中时不生成计划。"""
from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t182-step12-diagnosis-and-joint-evolution-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

import ast
import ctypes
import fcntl
import json
import os
import sys
from contextlib import contextmanager
from pathlib import Path

import close_development as dev
import close_development_readout_repair as repair
import confirmation_resources as resources

HERE = Path(__file__).resolve().parent
ROOT = _PROJECT_ROOT
PLAN = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t182-step12-diagnosis-and-joint-evolution-1/CONFIRMATION-PLAN.json')
CONTRACT = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t182-step12-diagnosis-and-joint-evolution-1/CONFIRMATION-READOUT-CONTRACT.md')
DEVELOPMENT = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t182-step12-diagnosis-and-joint-evolution-1/DEVELOPMENT-CLOSED.json')
REPAIR_INPUTS = ("close_development_readout_repair.py", "DEVELOPMENT-READOUT-REPAIR-CONTRACT.md",
                 "DEVELOPMENT-FIRST-INPUT-CHECK-FAILED.json", "DEVELOPMENT-READOUT-REPAIR-VALIDATION.json")


def repair_validation():
    """确认必须绑定实际修复验证当前字节；不因同名成功文件而继承旧验收。"""
    validation, validation_pin = dev.read(_project_file(_PROJECT_ROOT, HERE / REPAIR_INPUTS[-1]))
    dev.require(validation.get("schema") == "t182-development-readout-repair-validation/1" and
                all(validation.get(k) is True for k in ("success", "source_stable", "all_required_negative_checks_passed",
                    "original_statistical_function_identity_unchanged", "selection_ast_unchanged")) and
                validation.get("actual_focal_score_receipts_checked") == 1686 and
                validation.get("actual_complete_tables_receipt_checked") == 4 and
                validation.get("actual_completed_tables_metadata_checked") == 14 and
                validation.get("scores_extracted") is False, "评分收据修正版未实际验收通过")
    files = validation.get("files")
    required = {str(_project_file(_PROJECT_ROOT, HERE / name)) for name in (*REPAIR_INPUTS[:-1], "close_development.py", "run_development.py")}
    dev.require(type(files) is dict and required <= set(files), "修复验证未绑定当前实现／合同／原失败")
    # 每桌只核必要实现小文件；实际验证的大收据按依赖集合在统一IO阶段核一次。
    for path in required:
        expected = files[path]
        dev.require(dev.pin(Path(path)) == expected, "修复验证原字节漂移:" + path)
    return validation_pin, files


def background_priority():
    """后台研究只降CPU/IO优先级；导入时不设置资源或获取锁。"""
    dev.require(sys.platform == "darwin", "本批须使用macOS后台IO环境")
    priority = os.getpriority(os.PRIO_PROCESS, 0)
    if priority < 15:
        os.nice(15 - priority)
    dev.require(os.getpriority(os.PRIO_PROCESS, 0) >= 15, "研究CPU优先级未降至nice15")
    io = ctypes.CDLL(None, use_errno=True).setiopolicy_np
    io.argtypes, io.restype = [ctypes.c_int, ctypes.c_int, ctypes.c_int], ctypes.c_int
    dev.require(io(0, 0, 3) == 0, "研究未获得macOS后台IO")


@contextmanager
def postprocess_lock(label):
    """独占共用赛后锁，异常也释放；不停止或操作自由赛进程。"""
    with (_project_file(_PROJECT_ROOT, ROOT / ".private/t165-live-watchdog/postprocess.lock")).open("a+") as lock:
        print(json.dumps({"state": "waiting_postprocess_lock", "operation": label,
                          "scores_extracted": False}, ensure_ascii=False), flush=True)
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            yield
        finally:
            primary = sys.exc_info()[1]
            try:
                fcntl.flock(lock, fcntl.LOCK_UN)
            except BaseException as secondary:
                if primary is None:
                    raise
                primary.add_note("释放赛后锁再次失败:" + type(secondary).__name__ + ": " + str(secondary))


def new_json(path, value):
    """仅排他新建计划/闭合证据；不覆盖既有支出或结果。"""
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n"
    with Path(path).open("x", encoding="utf-8") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())


def research_imports():
    """递归冻结所有静态import的同目录研究实现，包括函数内import；不执行脚本。"""
    queue = [_project_file(_PROJECT_ROOT, HERE / n) for n in ("prepare_confirmation.py", "run_confirmation.py", "close_confirmation.py")]
    seen, edges = {}, {}
    while queue:
        path = queue.pop().resolve()
        if str(path) in seen:
            continue
        tree = ast.parse(path.read_bytes(), filename=str(path))
        children = set()
        for node in ast.walk(tree):
            modules = ([a.name for a in node.names] if isinstance(node, ast.Import)
                       else [node.module] if isinstance(node, ast.ImportFrom) and node.module else [])
            for module in modules:
                local = _project_file(_PROJECT_ROOT, HERE / (module.split(".")[0] + ".py"))
                if local.is_file():
                    children.add(local.resolve())
        seen[str(path)] = dev.pin(path)
        edges[str(path)] = sorted(str(c) for c in children)
        queue.extend(children)
    return seen, edges


def selected_from_development(closure, development_plan):
    """重核开发事前规则：32来源四座差和>0、至少2净增来源，最高均值后按ID排序。"""
    dev.require(closure.get("schema") == "t182-natural-development-closed/1" and
                closure.get("complete") is True and closure.get("source_stable") is True and
                closure.get("status") == "development_complete_not_confirmed" and
                closure.get("source_kind") == "simulation" and
                closure.get("readout_schema_repair") == "production_opponent_diagnostics_and_object_ids_only_v1",
                "开发未完整闭合／未使用实际验收的评分收据修正版，确认不可准备")
    dev.require(all(closure.get(k) is False for k in
                    ("confirmation_admission", "strength_admission", "deadline_admission", "release_admission")),
                "开发准入边界不符")
    dev.require(closure.get("parent_identity") == development_plan["parent"]["identity"] and
                closure.get("planned_table_instances") == closure.get("actual_table_instances") ==
                development_plan["planned_table_instances"] and
                closure.get("completed_hand_instances") == development_plan["planned_table_instances"] * 8 and
                closure.get("independent_mother_sources") == 32, "开发原分母或父代身份不符")
    entries = closure.get("candidates")
    dev.require(type(entries) is list and len(entries) == len(development_plan["candidates"]), "开发候选分母不符")
    by_id = {a["identity"]["candidate_id"]: a for a in development_plan["candidates"]}
    dev.require(len({r["candidate_id"] for r in entries}) == len(entries) and
                {r["candidate_id"] for r in entries} == set(by_id), "开发候选身份重复或缺失")
    eligible = []
    for row in entries:
        candidate_id = row["candidate_id"]
        dev.require(row["identity"] == by_id[candidate_id]["identity"], "开发候选完整身份不符")
        sources = row.get("sources")
        dev.require(type(sources) is list and len(sources) == 32, "开发来源不足32")
        totals, positive = [], []
        for source, root in zip(sources, development_plan["roots"]):
            dev.require(source.get("root_id") == root["root_id"] and source.get("seed") == root["seed"],
                        "开发来源顺序或身份不符")
            pairs = source.get("paired_tables")
            dev.require(type(pairs) is list and [p.get("rotation") for p in pairs] == [0, 1, 2, 3],
                        "开发每来源四座不足")
            value = dev.integer(source["four_seat_delta_sums"]["net"], "开发来源净分差")
            dev.require(value == sum(dev.integer(p["delta"]["net"], "开发配对差") for p in pairs),
                        "开发来源净分差与四桌不一致")
            totals.append(value)
            if value > 0:
                positive.append(root["root_id"])
        total = sum(totals)
        dev.require(row["mean_delta"]["net"] == total / 128 and
                    row.get("net_delta_sum_128_tables") == total and row.get("positive_sources") == positive and
                    row.get("development_selection_eligible") is (total > 0 and len(positive) >= 2),
                    "开发选择算术不符")
        if total > 0 and len(positive) >= 2:
            eligible.append((total, candidate_id))
    eligible.sort(key=lambda item: (-item[0], item[1]))
    selected = None if not eligible else eligible[0][1]
    dev.require(closure.get("selected_candidate_id_for_confirmation_preparation") == selected,
                "开发选择不等于冻结事前规则")
    dev.require(selected is not None, "开发没有选出候选，确认不得启动")
    return by_id[selected]


def validate_confirmation_plan(plan):
    """核1024完整桌与独立128来源；只验证计划和源码，不生成世界或读取运行成绩。"""
    dev.require(plan.get("schema") == "t182-natural-confirmation/2" and plan.get("rotations") == [0, 1, 2, 3] and
                plan.get("rounds") == 8 and plan.get("initial_dealer_physical") == 0 and
                dev.seat_vector(plan.get("initial_scores_0_1_2_3"), "确认初分") == [0, 0, 0, 0], "确认计划版本/赛制不符")
    roots, candidates = plan.get("roots"), plan.get("candidates")
    dev.require(type(roots) is list and len(roots) == 128 and type(candidates) is list and len(candidates) == 1,
                "确认须128来源和唯一候选")
    dev.require(len({r["root_id"] for r in roots}) == len({r["seed"] for r in roots}) == 128, "确认来源或seed重复")
    for root in roots:
        dev.integer(root["seed"], "确认seed", 0)
        opponents = root.get("opponent_types_logical_1_2_3")
        dev.require(type(opponents) is list and len(opponents) == 3 and
                    all(t in ("automatic_like", "normal_v0", "r18") for t in opponents), "确认对手组成不符")
    dev.require(plan.get("planned_table_instances") == plan.get("maximum_new_complete_table_instances") == 1024 and
                plan.get("planned_hand_instances") == 8192 and
                plan.get("no_early_score_peeking_or_additional_roots") is True and
                plan.get("normal_fallbacks_allowed") is False, "确认预算/查看/回退边界不符")
    dev.require(plan.get("bootstrap") == {"seed": 20261004, "replicates": 20000, "sources": 128,
                                           "interval": "percentile_linear_0.025_0.975"}, "确认区间方法漂移")
    dev.require(plan.get("wall_seconds_per_table") == 600 and plan.get("workers") == [0, 1] and
                plan.get("max_cpu_workers") == 2 and plan.get("partition") == "worker=ordinal%2" and
                plan.get("resource_tasks") == resources.tasks(plan) and plan.get("nice_at_least") == 15 and
                plan.get("macos_background_io") is True and
                plan.get("common_postprocess_lock_held_during_simulation") is False,
                "确认资源分区／优先级／原600秒保护不符")
    parent, child = plan["parent"], candidates[0]
    dev.require(parent["identity"]["source_sha256"] == dev.PARENT_SHA and
                parent["identity"]["params"] == child["identity"]["params"] and
                parent["identity"]["params"]["max_operations"] == 4800000 and
                parent["identity"]["params"]["projection_limits"]["max_replacement_depth"] == 1 and
                parent["identity"]["candidate_id"] != child["identity"]["candidate_id"], "确认父代/限额不符")
    for arm in (parent, child):
        dev.require(dev.pin(Path(arm["source_file"]))["sha256"] == arm["identity"]["source_sha256"], "确认公式原源码漂移")
    for name in ("prepare_confirmation.py", "run_confirmation.py", "close_confirmation.py", "CONFIRMATION-READOUT-CONTRACT.md",
                 "DEVELOPMENT-CLOSED.json", "DEVELOPMENT-PLAN.json", "COMPOSITIONS.json", "FRESH-ROOTS-BEFORE-AUTHOR.json",
                 "confirmation_resources.py", "RESOURCE-SCHEDULING-CLOSED.json", "RESOURCE-SCHEDULING-PLAN.json",
                 *REPAIR_INPUTS):
        dev.require(str(_project_file(_PROJECT_ROOT, HERE / name)) in plan["files"], "确认未冻结关键输入:" + name)
    dev.require(plan.get("selected_candidate_id") == child["identity"]["candidate_id"], "确认选择身份不符")
    validation_pin, repair_files = repair_validation()
    dev.require(plan.get("readout_repair_validation_pin") == validation_pin and
                plan.get("readout_repair_evidence_files") == repair_files and
                plan["files"].get(str(_project_file(_PROJECT_ROOT, HERE / REPAIR_INPUTS[-1]))) == plan["readout_repair_validation_pin"],
                "确认未绑定当前实际评分收据修复验证")
    compositions, _ = dev.read(_project_file(_PROJECT_ROOT, HERE / "COMPOSITIONS.json"))
    dev.require(roots == compositions["pools"]["confirmation"], "确认未使用事前冻结的全部128来源")
    seeds = {r["seed"] for r in roots}
    for pool in ("development", "diagnostic"):
        dev.require(not seeds & {r["seed"] for r in compositions["pools"][pool]}, "确认与开发/诊断来源交叉")
    research_files, edges = research_imports()
    dev.require(plan.get("research_imports") == edges and
                all(plan["files"].get(path) == value for path, value in research_files.items()), "研究import闭包未完整绑定")


def read_confirmation_plan(*, verify_development_evidence=False):
    """读取唯一确认计划；原开发大文件仅在调用方持锁的启动/闭合时统一验一次。"""
    plan, plan_pin = dev.read(PLAN)
    validate_confirmation_plan(plan)
    dev.frozen(plan)
    development, development_pin = dev.read(DEVELOPMENT)
    development_plan, development_plan_pin = dev.read(_project_file(_PROJECT_ROOT, HERE / "DEVELOPMENT-PLAN.json"))
    resource_closed, resource_pin = resources.development_resource_evidence(development_pin, development_plan_pin)
    dev.require(resource_pin == plan.get("development_resource_closed_pin") and
                resource_closed["files"] == plan.get("development_resource_evidence_files"),
                "确认未绑定完整开发资源闭合原件")
    dev.require(all(resource_closed["files"].get(str(_project_file(_PROJECT_ROOT, HERE / name))) == plan["files"].get(str(_project_file(_PROJECT_ROOT, HERE / name)))
                    for name in REPAIR_INPUTS), "确认评分修复原件与开发资源冻结不同")
    selected = selected_from_development(development, development_plan)
    dev.require(selected == plan["candidates"][0] and plan["parent"] == development_plan["parent"] and
                development.get("files") == plan.get("development_evidence_files"), "确认身份未绑定开发原选择及原证据")
    if verify_development_evidence:
        dependencies = dict(plan["development_resource_evidence_files"])
        for collection in (plan["development_evidence_files"], plan["readout_repair_evidence_files"]):
            for path, expected in collection.items():
                dev.require(dependencies.get(path, expected) == expected, "开发／资源／修复原件pin矛盾:" + path)
                dependencies[path] = expected
        for path, expected in dependencies.items():
            dev.require(dev.pin(Path(path)) == expected, "开发原证据漂移:" + path)
    return plan, plan_pin


def main():
    """全验开发原终态、源码和选择后，仅新建确认计划；实际世界/评分/桌数仍为0。"""
    dev.require(not PLAN.exists(), "确认计划已存在，拒绝覆盖")
    background_priority()
    with postprocess_lock("prepare_confirmation"):
        development, development_pin = dev.read(DEVELOPMENT)
        development_plan, development_plan_pin = dev.read(_project_file(_PROJECT_ROOT, HERE / "DEVELOPMENT-PLAN.json"))
        dev.validate_plan(development_plan)
        dev.frozen(development_plan)
        selected = selected_from_development(development, development_plan)
        validation_pin, repair_files = repair_validation()
        resource_closed, resource_pin = resources.development_resource_evidence(development_pin, development_plan_pin)
        dependencies = dict(resource_closed["files"])
        for collection in (development["files"], repair_files):
            for path, expected in collection.items():
                dev.require(dependencies.get(path, expected) == expected, "开发／资源／修复原件pin矛盾:" + path)
                dependencies[path] = expected
        for path, expected in dependencies.items():
            dev.require(dev.pin(Path(path)) == expected, "开发原证据漂移:" + path)
        dev.require(development["files"].get(str(_project_file(_PROJECT_ROOT, HERE / "DEVELOPMENT-PLAN.json"))) == development_plan_pin,
                    "开发闭合未绑定原开发计划")
        compositions, _ = dev.read(_project_file(_PROJECT_ROOT, HERE / "COMPOSITIONS.json"))
        fresh, _ = dev.read(_project_file(_PROJECT_ROOT, HERE / "FRESH-ROOTS-BEFORE-AUTHOR.json"))
        roots = compositions["pools"]["confirmation"]
        dev.require(fresh.get("author_may_read_confirmation") is False and fresh.get("confirmation_labels_read") == 0 and
                    fresh["confirmation"] == [{"root_id": r["root_id"], "seed": r["seed"]} for r in roots],
                    "确认池不是事前未读标签的冻结来源")
        # 准备阶段重新核真实装载身份，但不执行候选评分或生成世界。
        from hangma_bot.offline.vip_eoh_generate import VipEohBatch, load_vip_parents
        from hangma_bot.offline.scoring_sources import source_manifest
        batch = VipEohBatch.read(_project_file(_PROJECT_ROOT, HERE / "AUTHOR-BATCH.json"))
        loaded = load_vip_parents([Path(selected["package"])], batch)[0]
        dev.require(loaded["identity"] == selected["identity"] and
                    batch.identity(Path(development_plan["parent"]["source_file"]).read_text()) == development_plan["parent"]["identity"],
                    "确认准备实际装载身份不同于开发原身份")
        manifest = source_manifest(("hangma_bot.offline.qualifier_opponents", "hangma_bot.offline.vip_eoh_generate",
                                    "hangma_bot.offline.scoring_input_capture", "hangma_bot.offline.evaluate"))
        for path, value in development_plan["source_manifest"].items():
            dev.require(manifest.get(path, value) == value and dev.pin(_project_file(_PROJECT_ROOT, ROOT / path)) == value, "开发生产源码已漂移:" + path)
            manifest[path] = value
        research_files, edges = research_imports()
        files = dict(development_plan["files"])
        files.update(research_files)
        files[str(CONTRACT)] = dev.pin(CONTRACT)
        files[str(DEVELOPMENT)] = development_pin
        files[str(_project_file(_PROJECT_ROOT, HERE / "DEVELOPMENT-PLAN.json"))] = development_plan_pin
        files[str(resources.RESOURCE_CLOSED)] = resource_pin
        files[str(resources.RESOURCE_PLAN)] = resource_closed["schedule_plan_pin"]
        for name in REPAIR_INPUTS:
            files[str(_project_file(_PROJECT_ROOT, HERE / name))] = dev.pin(_project_file(_PROJECT_ROOT, HERE / name))
            dev.require(resource_closed["files"].get(str(_project_file(_PROJECT_ROOT, HERE / name))) == files[str(_project_file(_PROJECT_ROOT, HERE / name))],
                        "资源闭合未冻结同份评分收据修复原件:" + name)
        plan = {"schema": "t182-natural-confirmation/2", "roots": roots,
            "parent": development_plan["parent"], "candidates": [selected],
            "selected_candidate_id": selected["identity"]["candidate_id"], "files": files,
            "source_manifest": manifest, "research_imports": edges, "development_evidence_files": development["files"],
            "development_resource_closed_pin": resource_pin, "development_resource_evidence_files": resource_closed["files"],
            "readout_repair_validation_pin": validation_pin,
            "readout_repair_evidence_files": repair_files,
            "rotations": [0, 1, 2, 3], "rounds": 8, "initial_dealer_physical": 0,
            "initial_scores_0_1_2_3": [0, 0, 0, 0], "planned_table_instances": 1024,
            "maximum_new_complete_table_instances": 1024, "planned_hand_instances": 8192,
            "step_limit": development_plan["step_limit"], "wall_seconds_per_table": development_plan["wall_seconds_per_table"],
            "minimum_free_bytes": development_plan["minimum_free_bytes"], "capture_limits": development_plan["capture_limits"],
            "bootstrap": {"seed": 20261004, "replicates": 20000, "sources": 128,
                          "interval": "percentile_linear_0.025_0.975"},
            "net_signal_gate": "128母来源95%净积分配对区间下端严格>0",
            "opportunity_evidence_gate": "至少2母来源大牌(>=4番)实际收入配对四座均值>0；仅证据门",
            "no_early_score_peeking_or_additional_roots": True, "normal_fallbacks_allowed": False,
            "max_confirmed_candidates": 1, "new_models_scores_worlds_tables_in_preparation": 0,
            "workers": [0, 1], "max_cpu_workers": 2, "partition": "worker=ordinal%2",
            "nice_at_least": 15, "macos_background_io": True,
            "common_postprocess_lock_held_during_simulation": False,
            "deadline_admission": False, "runtime_reliability_admission": False, "release_admission": False}
        plan["resource_tasks"] = resources.tasks(plan)
        validate_confirmation_plan(plan)
        dev.frozen(plan)
        for path, expected in dependencies.items():
            dev.require(dev.pin(Path(path)) == expected, "准备期间开发原证据漂移:" + path)
        new_json(PLAN, plan)
    print(json.dumps({"prepared": True, "plan": str(PLAN), "planned_tables": 1024,
                      "new_models_scores_worlds_tables": 0, "release_admission": False}, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, TypeError, IndexError, AttributeError) as error:
        print(json.dumps({"prepared": False, "status": "unknown_or_invalid_no_plan", "error_type": type(error).__name__,
                          "reason": str(error), "original_evidence_retained": True}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(1)
