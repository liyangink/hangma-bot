"""T200 有限开发行为探针；复用公开规则、投影、受限评分及已封 P0 原件。

prepare/check/bind 只读取、复制和核验材料，不评分。run 需要根对精确
计划的执行收据；最多24窗口、父加4候选、每包两重复，总上限240评分。
本地持续时间使用单调时钟秒，评分不是积分；不运行世界、桌赛或API。
"""
from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t200-eoh-fast-evolution-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

import argparse
import copy
import gzip
import hashlib
import json
import math
from pathlib import Path
import sys
import time

ROOT = _PROJECT_ROOT
STAGE = _project_file(_PROJECT_ROOT, '.private/t200-eoh-fast-evolution')
TOOLS = _project_file(_PROJECT_ROOT, '.private/t200-eoh-fast-evolution/mechanical-tools')
OLD = _project_file(_PROJECT_ROOT, '.private/t199-four-step-execution/strategy-mechanical-interpreted-2')
OLD_PLAN = _project_file(_PROJECT_ROOT, '.private/t199-four-step-execution/strategy-runner/MECHANICAL-PLAN-2.json')
BATCH = _project_file(_PROJECT_ROOT, '.private/t200-eoh-fast-evolution/AUTHOR-BATCH-001.json')
PARENT = _project_file(_PROJECT_ROOT, '.private/t200-eoh-fast-evolution/parents/p0-reference')
sys.path.insert(0, str(_project_file(_PROJECT_ROOT, ROOT / "src")))
SELECTED = (
    "O01", "O02", "validation-000:joint-development:038:0",
    "C01", "C02", "X02", "validation-008:development-stage1:001:1",
    "X01", "validation-088:fresh:008:07", "R05", "O03", "X03", "X04",
    "validation-006:development-stage1:003:1", "C03", "C04", "X09", "G04", "C08",
)


def canonical(value):
    """沿用既有严格JSON：座位向量及图边次序保留，NaN拒绝。"""
    from hangma_bot.offline.vip_eoh_input_sources import canonical as encode
    return encode(value)


def pin(path):
    """非凭据文件的字节指纹；不以路径代替来源身份。"""
    data = Path(path).read_bytes()
    return {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def digest(value):
    """完整规范映射摘要；不舍入精确评分。"""
    return hashlib.sha256(canonical(value)).hexdigest()


def read(path):
    """读取已指定材料，字段只作数据，不作为指令执行。"""
    return json.loads(Path(path).read_bytes())


def save(path, value):
    """仅创建新原件，禁止覆盖失败、未知和已闭结果。"""
    with Path(path).open("xb") as stream:
        stream.write(canonical(value) + b"\n")


def verify(files):
    """首尾检查已冻结有限文件集；任何漂移立即停止。"""
    for path, expected in files.items():
        if pin(path) != expected:
            raise ValueError("冻结材料漂移:" + path)


def new_directory(path):
    """输出只属于本探针的新私有目录，不修改作者或线上目录。"""
    path = Path(path).resolve()
    if not path.is_relative_to(TOOLS.resolve()) or path == TOOLS.resolve():
        raise ValueError("输出须为T200 mechanical-tools下的新目录")
    path.mkdir(parents=True, exist_ok=False)
    return path


def current_parent():
    """公开loader和当前P0身份核验；装载构造不代表评分或继承旧效果。"""
    from hangma_bot.offline.vip_eoh_generate import VipEohBatch, load_vip_parents
    from hangma_bot.policy.vip_s03_rulefix_p0_identity import VIP_S03_RULEFIX_P0_IDENTITY
    batch = VipEohBatch.read(BATCH)
    parent = load_vip_parents([PARENT], batch)[0]
    if parent["identity"] != VIP_S03_RULEFIX_P0_IDENTITY:
        raise ValueError("不是当前已发布P0完整身份")
    return batch, parent


def producer_files():
    """冻结实际生产规则、投影、公开探针与执行器闭包，不复制新框架。"""
    from hangma_bot.offline.scoring_sources import source_manifest
    manifest = source_manifest(("hangma_bot.offline.vip_eoh_probe_v2",))
    return {str(_project_file(_PROJECT_ROOT, ROOT / p)): v for p, v in manifest.items()}


def root_white_count(dto):
    """从已封合法弃牌等待态回加所弃白，避免14张另列摸牌的重复计数。"""
    nodes = {n["node_key"]: n for n in dto["nodes"]}
    counts = {nodes[a["node_key"]]["waiting"]["structure"]["whites_held"] +
              int(a["action_key"] == "discard:白") for a in dto["actions"]
              if a["action_type"] == "discard" and nodes[a["node_key"]]["waiting"] is not None}
    if len(counts) > 1:
        raise ValueError("同根弃牌事实的实体白库存不一致")
    return next(iter(counts)) if counts else None


def prepare(output):
    """按预先固定开发案例复制19个已封图及父向量，再声明3个未知观察控制。"""
    batch, parent = current_parent()
    closed = read(_project_file(_PROJECT_ROOT, OLD / "FILE-CLOSED.json"))
    old_plan = read(OLD_PLAN)
    if closed["complete"] is not True or closed["binding_id"] != old_plan["binding_id"]:
        raise ValueError("原33图没有独立封闭")
    files = {str(_project_file(_PROJECT_ROOT, OLD / name)): expected for name, expected in closed["original_files"].items()}
    files.update({str(p): pin(p) for p in (_project_file(_PROJECT_ROOT, OLD / "FILE-CLOSED.json"), OLD_PLAN, BATCH,
                  _project_file(_PROJECT_ROOT, PARENT / "generation.json"), _project_file(_PROJECT_ROOT, PARENT / "candidate.py"), Path(__file__))})
    if old_plan["params"] != parent["identity"]["params"]:
        raise ValueError("原图参数与当前P0父不一致")
    if pin(old_plan["sources"]["parent"]["path"]) != pin(_project_file(_PROJECT_ROOT, PARENT / "candidate.py")):
        raise ValueError("原父公式字节不一致")
    verify(files)
    audits = read(_project_file(_PROJECT_ROOT, OLD / "AUDIT-ROWS.json"))
    cases = {c["case_id"]: c for c in old_plan["cases"]}
    views = {}
    with gzip.open(_project_file(_PROJECT_ROOT, OLD / "views.jsonl.gz"), "rt") as stream:
        for line in stream:
            row = json.loads(line)
            if digest(row["view"]) != row["view_sha256"]:
                raise ValueError("原完整图摘要不一致")
            views[row["view_sha256"]] = row["view"]
    windows = []
    for label in SELECTED:
        records = [r for r in audits if r["case_id"] == label and r["variant"] == "parent"]
        if len(records) != 2:
            raise ValueError("原父没有两次完整重复:" + label)
        row = records[0]
        if any(r["status"] != "chosen" or not r["c_self_scored"] or len(r["scoring_calls"]) != 1
               or not r["scoring_calls"][0]["full_legal_keys"] for r in records):
            raise ValueError("原父完整评分未闭")
        scores = lambda r: sorted(({"action_key": e["action_key"], "score": e["score"],
                                   "trace": e["trace"].get("detail", e["trace"])}
                                  for e in r["candidates"]), key=lambda e: (-e["score"], e["action_key"]))
        if canonical(scores(records[0])) != canonical(scores(records[1])):
            raise ValueError("原父重复不一致")
        sha = row["scoring_calls"][0]["input_capture"]["view_sha256"]
        dto = views[sha]
        keys = sorted(row["legal_action_keys"])
        if sorted(a["action_key"] for a in dto["actions"]) != keys:
            raise ValueError("原图合法根不全")
        windows.append({"label": label, "kind": "captured_current_P0", "purpose": cases[label]["purpose"],
            "observation": row["observation"], "window_key": row["window_key"], "legal_action_keys": keys,
            "captured_view_sha256": sha, "captured_view": dto, "parent_entries": scores(row),
            "root_white_count": root_white_count(dto), "source_case_id": label,
            "origin_audit_file": str(_project_file(_PROJECT_ROOT, OLD / "AUDIT-ROWS.json"))})
    for field in ("remaining_tile_count", "gang_draw", "chain_piao"):
        control = copy.deepcopy(windows[0])
        control.update(label="unknown:" + field, kind="synthetic_unknown_observation_control",
                       purpose="未知字段守卫，仅机械控制，不授自然覆盖或效果", captured_view=None,
                       captured_view_sha256=None, parent_entries=None, root_white_count=0)
        control["observation"][field] = None
        windows.append(control)
    if not {0, 1, 2} <= {w["root_white_count"] for w in windows}:
        raise ValueError("缺0/1/2白开发输入")
    if len({digest({k: w[k] for k in ("observation", "window_key")}) for w in windows}) != len(windows):
        raise ValueError("输入重复")
    files.update(producer_files())
    panel = {"schema": "t200-finite-mechanical-panel/1", "parent_identity": parent["identity"],
        "selected_case_ids": list(SELECTED), "selection_scope": "固定历史开发机制题，未按候选评分/确认成绩选题",
        "windows": windows, "window_count": len(windows), "repeats": 2, "max_candidates": 4,
        "score_budget": 240, "planned_maximum_scores": len(windows) * 5 * 2,
        "files": files, "prepare_rule_score_World_tables_API_calls": 0,
        "claims": {"development_only": True, "strength": False, "deadline": False, "release": False}}
    verify(files)
    out = new_directory(output)
    save(out / "PANEL.json", panel)
    save(out / "PREPARED.json", {"complete": True, "panel_pin": pin(out / "PANEL.json"),
         "windows": len(windows), "real_current_P0": len(SELECTED), "synthetic_unknown_controls": 3,
         "scores_rules_World_tables_API": 0, "parent_loader_entries": 1,
         "planned_maximum_scores": panel["planned_maximum_scores"], "execution_started": False})
    return {"complete": True, "windows": len(windows), "scores": 0, "panel": str(out / "PANEL.json")}


def checked_panel(path):
    """核冻结面板、当前父与全部来源，不分析规则或评分。"""
    path = Path(path).resolve()
    panel = read(path)
    if panel["schema"] != "t200-finite-mechanical-panel/1" or not 12 <= panel["window_count"] <= 24:
        raise ValueError("不是有限开发面板")
    if panel["window_count"] != len(panel["windows"]) or panel["repeats"] != 2 or panel["score_budget"] != 240:
        raise ValueError("窗口或预算漂移")
    verify(panel["files"])
    batch, parent = current_parent()
    if panel["parent_identity"] != parent["identity"]:
        raise ValueError("当前父身份漂移")
    return panel, batch, parent


def bind(panel_path, candidates, output):
    """根选择已返回候选后冻结精确执行分母；不运行评分。"""
    from hangma_bot.offline.vip_eoh_generate import load_vip_parents
    panel, batch, parent = checked_panel(panel_path)
    if not 1 <= len(candidates) <= 4:
        raise ValueError("本有限轮只接受1到4候选")
    paths = [Path(p).resolve() for p in candidates]
    if len(set(paths)) != len(paths) or PARENT.resolve() in paths:
        raise ValueError("候选重复或冒用父")
    materials = load_vip_parents(paths, batch)
    if len({m["identity"]["candidate_id"] for m in materials}) != len(materials):
        raise ValueError("同字节候选不得重复消费机械预算")
    packages = [parent, *materials]
    files = {**panel["files"], str(Path(panel_path).resolve()): pin(panel_path)}
    for path in [PARENT.resolve(), *paths]:
        for name in ("generation.json", "candidate.py"):
            files[str(path / name)] = pin(path / name)
    plan = {"schema": "t200-finite-mechanical-run-plan/1", "panel_path": str(Path(panel_path).resolve()),
        "panel_pin": pin(panel_path), "packages": [{"path": m["path"], "identity": m["identity"],
             "record_sha256": m["record_sha256"], "source_sha256": m["source_sha256"],
             "role": "parent" if i == 0 else "candidate"} for i, m in enumerate(packages)],
        "files": files, "repeats": 2, "planned_score_calls": len(packages) * panel["window_count"] * 2,
        "maximum_score_calls": 240, "wall_clock_seconds": 300, "execution_enabled": False,
        "World_tables_API": 0, "effects_auto_dispatch": False}
    out = new_directory(output)
    save(out / "RUN-PLAN.json", plan)
    return {"complete": True, "score_calls": 0, "planned_score_calls": plan["planned_score_calls"],
            "plan": str(out / "RUN-PLAN.json"), "plan_pin": pin(out / "RUN-PLAN.json")}


def equivalent_honor_swap(dto, old_key, new_key, old_scores, new_scores):
    """只有严格同分且完整等待态能按孤字换名逐字段同构时，才标等价字序。"""
    honors = ("东", "南", "西", "北", "中", "发")
    if old_key == new_key or old_key[:8] != "discard:" or new_key[:8] != "discard:":
        return False
    a, b = old_key[8:], new_key[8:]
    if a not in honors or b not in honors or old_scores[a_key := old_key] != old_scores[new_key] or new_scores[a_key] != new_scores[new_key]:
        return False
    nodes = {n["node_key"]: n for n in dto["nodes"]}
    actions = {x["action_key"]: x for x in dto["actions"]}
    wa, wb = (nodes[actions[k]["node_key"]]["waiting"] for k in (old_key, new_key))
    if wa is None or wb is None:
        return False
    indexes = {code: i for i, code in enumerate(dto["tile_order"])}
    if wa["structure"]["natural_counts33"][indexes[a]] != 0 or wb["structure"]["natural_counts33"][indexes[b]] != 0:
        return False
    def swapped(value, field=""):
        if isinstance(value, dict):
            return {k: swapped(v, k) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            result = [swapped(v) for v in value]
            if field.endswith("counts33") or field in ("unseen_capacities", "unseen_evidence"):
                result[indexes[a]], result[indexes[b]] = result[indexes[b]], result[indexes[a]]
            return result
        return b if value == a else a if value == b else value
    return canonical(swapped(wa)) == canonical(wb)


def run(plan_path, approval_path, output):
    """按精确批准计划真实重建typed输入并评分；失败保留分母，不重试或买桌。"""
    from hangma_bot.hangma.engine import HangmaRules
    from hangma_bot.kernel.observation import CompetitionContext
    from hangma_bot.kernel.serialization import observation_from_json, window_key_from_json
    from hangma_bot.policy.interface import DecisionRequest
    from hangma_bot.policy.route_vip_heuristic import build_vip_route_scoring_view
    from hangma_bot.policy.action_value_executor import ActionValueExecutor, WorkloadExceeded
    from hangma_bot.offline.vip_eoh_generate import load_vip_parents
    from hangma_bot.offline.vip_eoh_probe_v2 import validate_trace
    plan, approval = read(plan_path), read(approval_path)
    if (plan["schema"] != "t200-finite-mechanical-run-plan/1" or
        approval.get("approved_for_t200_mechanical") is not True or
        approval.get("plan_pin") != pin(plan_path) or
        approval.get("maximum_score_calls") != plan["planned_score_calls"] or
        not 1 <= plan["planned_score_calls"] <= 240):
        raise ValueError("缺根对精确有限计划的评分批准")
    verify(plan["files"])
    panel, batch, parent = checked_panel(plan["panel_path"])
    materials = load_vip_parents([Path(p["path"]) for p in plan["packages"]], batch)
    for material, meta in zip(materials, plan["packages"]):
        if any(material[k] != meta[k] for k in ("identity", "record_sha256", "source_sha256")):
            raise ValueError("执行候选原件漂移")
    executors = [ActionValueExecutor(m["source"], max_operations=batch.max_operations,
                  max_local_collection_size=batch.projection_limits.max_nodes) for m in materials]
    out = new_directory(output)
    costs = {"rule_calls": 0, "projection_calls": 0, "score_calls": 0,
             "model_calls": 0, "World_advances": 0, "table_instances": 0,
             "public_package_load_entries": len(materials), "explicit_executor_constructors": len(executors)}
    save(out / "START.json", {"plan_pin": pin(plan_path), "approval_pin": pin(approval_path),
        "planned_score_calls": plan["planned_score_calls"], "packages": plan["packages"],
        "elapsed_clock": "time.monotonic_seconds", "official_deadline_claim": False})
    began = time.monotonic()
    failures, results, differences = [], [], []
    seen_score_views = set()  # 同完整图只允许每包两次；未知字段可能投影成原同图。
    rules = HangmaRules(batch.rule_config)
    try:
        with (out / "RESULTS.jsonl").open("xb") as stream, gzip.open(out / "ACTUAL-VIEWS.jsonl.gz", "xb") as captures:
            for item in panel["windows"]:
                window_results, window_error, dto, sha = [], None, None, None
                control = item["kind"] == "synthetic_unknown_observation_control"
                try:
                    if time.monotonic() - began >= plan["wall_clock_seconds"]:
                        raise ValueError("本轮单调秒预算耗尽")
                    obs = observation_from_json(item["observation"])
                    key = window_key_from_json(item["window_key"])
                    costs["rule_calls"] += 1
                    analysis = rules.analyze(obs, route_limits=batch.route_limits)
                    if analysis.completeness.value != "complete":
                        raise ValueError("规则分析不完整")
                    legal = sorted(c.action_key for c in analysis.legal_candidates)
                    if not control and legal != item["legal_action_keys"]:
                        raise ValueError("重建合法根与原父不一致")
                    request = DecisionRequest(obs, CompetitionContext("t200-mechanical", None, None, None,
                        None, (), 0), analysis, item["label"], key.trigger_seq, key, ())
                    costs["projection_calls"] += 1
                    view = build_vip_route_scoring_view(request, batch.rule_config, limits=batch.projection_limits)
                    dto = json.loads(canonical(view.candidate_view()))
                    sha = digest(dto)
                    captures.write(canonical({"label": item["label"], "view_sha256": sha, "view": dto}) + b"\n")
                    captures.flush()
                    if not control and (sha != item["captured_view_sha256"] or dto != item["captured_view"]):
                        raise ValueError("typed投影与原完整JSON图不一致")
                    if any(n.gap_kind is not None for n in view.nodes):
                        raise ValueError("公开图有机械/事实/工作量缺口")
                    if sha in seen_score_views:
                        raise ValueError("同完整图已有两重复；本控制不追加评分")
                    seen_score_views.add(sha)
                except (Exception, WorkloadExceeded) as error:
                    window_error = {"type": type(error).__name__, "reason": str(error)}
                    if not control:
                        failures.append({"label": item["label"], "stage": "input", **window_error})
                for index, executor in enumerate(executors):
                    repetitions = []
                    for repeat in range(2):
                        row = {"label": item["label"], "kind": item["kind"], "package_index": index,
                            "candidate_id": materials[index]["identity"]["candidate_id"], "repeat": repeat,
                            "view_sha256": sha, "status": "not_scored", "score_calls": 0,
                            "entries": [], "typed_JSON_exact_input": window_error is None and not control}
                        if window_error is not None:
                            row.update(status="control_unscored" if control else "unfinished", error=window_error)
                        else:
                            tick = time.monotonic()
                            try:
                                if costs["score_calls"] >= plan["planned_score_calls"] or time.monotonic() - began >= plan["wall_clock_seconds"]:
                                    raise ValueError("精确评分或单调秒预算耗尽")
                                row["score_calls"] = 1
                                costs["score_calls"] += 1
                                scored = executor.score_vip_route(view)
                                if scored.status != "SCORED":
                                    raise ValueError("候选未完整SCORED")
                                entries = sorted(({"action_key": e.action_key, "score": e.score,
                                      "trace": json.loads(canonical(dict(e.trace)))} for e in scored.entries),
                                      key=lambda e: (-e["score"], e["action_key"]))
                                if sorted(e["action_key"] for e in entries) != legal or any(not math.isfinite(e["score"]) for e in entries):
                                    raise ValueError("全合法根/有限分合同失败")
                                for entry in entries:
                                    validate_trace(entry["trace"])
                                if digest(view.candidate_view()) != sha:
                                    raise ValueError("评分改变typed输入")
                                if index == 0 and not control:
                                    original = {e["action_key"]: e["score"] for e in item["parent_entries"]}
                                    if {e["action_key"]: e["score"] for e in entries} != original:
                                        raise ValueError("当前父精确评分与历史同图父向量不同")
                                row.update(status="scored", entries=entries, first=entries[0]["action_key"])
                            except (Exception, WorkloadExceeded) as error:
                                row.update(status="unfinished", error={"type": type(error).__name__, "reason": str(error)})
                                failures.append({"label": item["label"], "package_index": index, "repeat": repeat, **row["error"]})
                            finally:
                                row.update(counted_operations=executor.last_operation_count,
                                           score_monotonic_seconds=time.monotonic() - tick)
                        repetitions.append(row)
                        results.append(row)
                        stream.write(canonical(row) + b"\n")
                        stream.flush()
                    exact_repeat = all(r["status"] == "scored" for r in repetitions) and repetitions[0]["entries"] == repetitions[1]["entries"]
                    if all(r["status"] == "scored" for r in repetitions) and not exact_repeat:
                        failures.append({"label": item["label"], "package_index": index, "stage": "determinism"})
                    window_results.append({"package_index": index, "repeated_complete_exact": exact_repeat,
                                           "first_row": repetitions[0]})
                if window_results[0]["repeated_complete_exact"]:
                    base = window_results[0]["first_row"]
                    for candidate in window_results[1:]:
                        if not candidate["repeated_complete_exact"]:
                            continue
                        row = candidate["first_row"]
                        changed = row["first"] != base["first"]
                        old_scores = {e["action_key"]: e["score"] for e in base["entries"]}
                        new_scores = {e["action_key"]: e["score"] for e in row["entries"]}
                        honor = changed and equivalent_honor_swap(dto, base["first"], row["first"], old_scores, new_scores)
                        differences.append({"label": item["label"], "kind": item["kind"],
                            "candidate_id": row["candidate_id"], "parent_first": base["first"], "candidate_first": row["first"],
                            "first_changed": changed, "equivalent_honor_permutation_only": honor,
                            "meaningful_development_change": changed and not honor and not control,
                            "synthetic_control_not_effect_evidence": control})
        verify(plan["files"])
    except (Exception, WorkloadExceeded) as error:
        failures.append({"stage": "run", "type": type(error).__name__, "reason": str(error)})
    summary = {"schema": "t200-finite-mechanical-result/1", "complete": not failures,
        "plan_pin": pin(plan_path), "approval_pin": pin(approval_path), "costs": costs,
        "failures": failures, "differences": differences,
        "elapsed_monotonic_seconds": time.monotonic() - began,
        "planned_package_windows": len(materials) * panel["window_count"],
        "observed_call_rows": len(results), "planned_call_rows": plan["planned_score_calls"],
        "candidate_dispositions": [{"candidate_id": m["identity"]["candidate_id"],
             "meaningful_first_changes": sum(d["meaningful_development_change"] for d in differences if d["candidate_id"] == m["identity"]["candidate_id"]),
             "no_change_or_only_equivalent_honors_stop_effect_budget": not any(d["meaningful_development_change"] for d in differences if d["candidate_id"] == m["identity"]["candidate_id"])}
             for m in materials[1:]],
        "strength_deadline_release_admission": False, "effect_budget_approved": False,
        "effects_auto_dispatch": False, "typed_JSON_scope": "生产typed view的完整canonical映射等于同窗原P0捕获JSON；未绕过执行器直接执行作者JSON函数"}
    if len(results) != plan["planned_score_calls"]:
        summary["complete"] = False
    save(out / "CLOSED.json", summary)
    return {"complete": summary["complete"], "costs": costs, "failures": len(failures),
            "dispositions": summary["candidate_dispositions"]}


def deny_external(event, args):
    """探针拒绝网络、子进程、Token和确认结果；不改运行进程或生产全局。"""
    if event in ("socket.connect", "socket.getaddrinfo", "subprocess.Popen", "os.system"):
        raise ValueError("有限机械探针禁止外部副作用")
    if event == "open" and args and isinstance(args[0], str):
        path = Path(args[0])
        if "token" in path.parts or path.name in (".env", "vip-zai-api.json", "confirmation-seeds.json", "OUTCOME.json"):
            raise ValueError("有限机械探针禁止凭据或确认/桌结果")


def main():
    """prepare/check/bind均0评分；run须显式根批准，输出只写新探针目录。"""
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    prep = commands.add_parser("prepare")
    prep.add_argument("--out", type=Path, default=_project_file(_PROJECT_ROOT, TOOLS / "panel-001"))
    check = commands.add_parser("check")
    check.add_argument("--panel", type=Path, required=True)
    binding = commands.add_parser("bind")
    binding.add_argument("--panel", type=Path, required=True)
    binding.add_argument("--candidate", type=Path, action="append", required=True)
    binding.add_argument("--out", type=Path, required=True)
    execute = commands.add_parser("run")
    execute.add_argument("--plan", type=Path, required=True)
    execute.add_argument("--approval", type=Path, required=True)
    execute.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    sys.addaudithook(deny_external)
    if args.command == "prepare":
        result = prepare(args.out)
    elif args.command == "check":
        panel, _, _ = checked_panel(args.panel)
        result = {"complete": True, "windows": panel["window_count"], "scores": 0,
                  "planned_maximum_scores": panel["planned_maximum_scores"]}
    elif args.command == "bind":
        result = bind(args.panel, args.candidate, args.out)
    else:
        result = run(args.plan, args.approval, args.out)
    print(json.dumps(result, ensure_ascii=False, allow_nan=False))
    return 0 if result["complete"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
