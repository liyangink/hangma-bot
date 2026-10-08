"""R10 条件路线微函数：把绝对微值机械重组为窗内相对优势结构。

第一批两个模型表达式都合法，但十个非零配置只形成同一稀疏首选签名。本工具不再
调用模型，也不接触终局效果；它依照 EoH/ReEvo 的父代重组与行为多样性原则，把
两个已验收表达式分别装入 midrange 与 best_only 两种预登记相对映射。
"""
from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

import datetime as dt
import json
import re
import sys
from pathlib import Path


HERE = Path(__file__).resolve().parent
ROUTE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15')
for path in (_project_file(_PROJECT_ROOT, ROUTE / "tools"), HERE):
    sys.path.insert(0, str(path))

import route_microfunction_batch_1 as first  # noqa: E402
from hangma_bot.policy.action_value_executor import static_check  # noqa: E402


SOURCE_BATCH = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/route-microfunction-01-20260921')
BATCH = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/route-microfunction-contrastive-01-20260921')
TASKS = {
    "R1": {
        "parent": "M1",
        "mode": "midrange",
        "configs": [
            {"RMF_SCALE": 0.0, "RMF_SHAPE": 24.0, "RMF_CAP": 8.0},
            {"RMF_SCALE": 4.0, "RMF_SHAPE": 24.0, "RMF_CAP": 4.0},
            {"RMF_SCALE": 8.0, "RMF_SHAPE": 24.0, "RMF_CAP": 8.0},
            {"RMF_SCALE": 12.0, "RMF_SHAPE": 24.0, "RMF_CAP": 12.0},
            {"RMF_SCALE": 8.0, "RMF_SHAPE": 12.0, "RMF_CAP": 8.0},
            {"RMF_SCALE": 8.0, "RMF_SHAPE": 48.0, "RMF_CAP": 8.0},
        ],
        "default_index": 2,
        "hypothesis": (
            "把同窗有效路线原值按(min+max)/2居中并以跨度归一，可同时奖励相对强路线、"
            "惩罚相对弱路线，避免T3和M1对所有路线动作同向加分。"
        ),
    },
    "R2": {
        "parent": "M2",
        "mode": "best_only",
        "configs": [
            {"RMF_SCALE": 0.0, "RMF_SHAPE": 64.0, "RMF_CAP": 8.0},
            {"RMF_SCALE": 4.0, "RMF_SHAPE": 64.0, "RMF_CAP": 4.0},
            {"RMF_SCALE": 8.0, "RMF_SHAPE": 64.0, "RMF_CAP": 8.0},
            {"RMF_SCALE": 12.0, "RMF_SHAPE": 64.0, "RMF_CAP": 12.0},
            {"RMF_SCALE": 8.0, "RMF_SHAPE": 32.0, "RMF_CAP": 8.0},
            {"RMF_SCALE": 8.0, "RMF_SHAPE": 96.0, "RMF_CAP": 8.0},
        ],
        "default_index": 2,
        "hypothesis": (
            "只奖励同窗原值最高的路线动作，弱路线精确保持V2，避免在条件价值代理尚未校准时"
            "对较弱路线施加负分；它与R1形成保守/对称两种结构档案。"
        ),
    },
}


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _space(configs: list[dict]) -> dict:
    return {
        "parameters": {
            name: sorted({row[name] for row in configs})
            for name in ("RMF_SCALE", "RMF_SHAPE", "RMF_CAP")
        },
        "zero_effect": next(row for row in configs if row["RMF_SCALE"] == 0.0),
        "configs": configs,
    }


def _route_raw_function() -> str:
    return '''def route_raw_value(action, visible, seat):
    """返回动作内最强已校验路线的无量纲原值；未知保持None。"""
    if action.get("value_coverage") != "complete":
        return (None, "coverage_not_complete", 0)
    issues = action.get("value_issues")
    if issues is None or len(issues) != 0:
        return (None, "value_issues", 0)
    wall = finite_number(visible.get("remaining_tile_count"))
    direct_support = support_total(action.get("useful_tiles"))
    if wall is None or wall <= 0.0 or direct_support is None or direct_support <= 0.0:
        return (None, "public_support_unavailable", 0)
    best = None
    valid_routes = 0
    routes = action.get("routes")
    if routes is None:
        return (None, "routes_unknown", 0)
    for route in routes:
        if route.get("shanten") != 0:
            continue
        route_support = support_total(route.get("useful_tiles"))
        if route_support is None or route_support <= 0.0:
            continue
        conditions = route.get("conditions")
        if conditions is None or conditions.get("draw_kind") not in ("normal", "replacement"):
            continue
        settlement = route.get("conditional_settlement")
        if settlement is None:
            continue
        self_delta = finite_number(settlement.get("self_delta"))
        fan = finite_number(settlement.get("fan"))
        deltas = settlement.get("score_delta")
        if (self_delta is None or self_delta <= 0.0 or fan is None or fan <= 0.0
                or deltas is None or len(deltas) != 4):
            continue
        seat_delta = finite_number(deltas[seat])
        if seat_delta is None or seat_delta != self_delta:
            continue
        raw = route_micro_value(direct_support, self_delta, fan, wall, RMF_SHAPE)
        if raw is None:
            continue
        valid_routes += 1
        if best is None or raw > best:
            best = raw
    if best is None:
        return (None, "no_valid_route", valid_routes)
    return (round(best, 12), "complete_route_raw_max", valid_routes)


'''


def build_source(proposal: dict, spec: dict) -> str:
    source = first._candidate_source(proposal)
    space = _space(spec["configs"])
    lines = source.splitlines()
    lines[0] = "# STRUCTURE_SPACE_JSON: " + json.dumps(
        space, ensure_ascii=False, separators=(",", ":"))
    source = "\n".join(lines) + "\n"
    default = spec["configs"][spec["default_index"]]
    for name in ("RMF_SCALE", "RMF_SHAPE", "RMF_CAP"):
        source, count = re.subn(
            rf"^{name}\s*=\s*[-+0-9.eE]+\s*$", f"{name} = {default[name]}",
            source, count=1, flags=re.MULTILINE,
        )
        if count != 1:
            raise ValueError("默认参数锚点漂移：" + name)
    source = source.replace(
        "RMF_CAP = {0}\n".format(default["RMF_CAP"]),
        "RMF_CAP = {0}\nRMF_MODE = {1}\n".format(
            default["RMF_CAP"], json.dumps(spec["mode"])),
        1,
    )
    start = source.index("def route_adjustment(action, visible, seat):\n")
    end = source.index("def score_actions(view):\n", start)
    source = source[:start] + _route_raw_function() + source[end:]
    source = source.replace(
        "route_delta, route_delta_basis, route_valid_count = route_adjustment(\n"
        "            action, visible, seat)",
        "route_raw, route_delta_basis, route_valid_count = route_raw_value(\n"
        "            action, visible, seat)",
    )
    source = source.replace(
        '"shanten": shanten, "route_delta": route_delta, '
        '"route_delta_basis": route_delta_basis',
        '"shanten": shanten, "route_raw": route_raw, '
        '"route_delta_basis": route_delta_basis',
    )
    source = source.replace(
        '"shanten": None, "route_delta": route_delta, '
        '"route_delta_basis": route_delta_basis',
        '"shanten": None, "route_raw": route_raw, '
        '"route_delta_basis": route_delta_basis',
    )
    source = source.replace(
        '"route_delta": 0.0, "route_delta_basis": "unknown_action"',
        '"route_raw": None, "route_delta_basis": "unknown_action"',
    )
    before_entries = '''    base_floor = min(known)
    entries = []
'''
    route_summary = '''    base_floor = min(known)
    route_raw_values = []
    for pending_item in pending:
        pending_raw = pending_item.get("route_raw")
        if pending_raw is not None:
            route_raw_values.append(pending_raw)
    route_low = None
    route_high = None
    route_mean = None
    if len(route_raw_values) >= 2:
        route_low = min(route_raw_values)
        route_high = max(route_raw_values)
        if route_high > route_low:
            route_mean = sum(route_raw_values) / float(len(route_raw_values))
    entries = []
'''
    if source.count(before_entries) != 1:
        raise ValueError("route summary锚点漂移")
    source = source.replace(before_entries, route_summary)
    old_delta = '''        route_delta = item.get("route_delta")
        total = round(total + route_delta, 6)
'''
    new_delta = '''        route_raw = item.get("route_raw")
        route_delta = 0.0
        if (RMF_SCALE != 0.0 and route_raw is not None and route_low is not None
                and route_high is not None and route_high > route_low):
            span = route_high - route_low
            if RMF_MODE == "midrange":
                route_delta = RMF_SCALE * (
                    route_raw - (route_low + route_high) / 2.0) / span
            elif RMF_MODE == "best_only" and route_raw == route_high:
                route_delta = RMF_SCALE * (route_raw - route_low) / span
            if route_delta > RMF_CAP:
                route_delta = RMF_CAP
            if route_delta < -RMF_CAP:
                route_delta = -RMF_CAP
        route_delta = round(route_delta, 6)
        total = round(total + route_delta, 6)
'''
    if source.count(old_delta) != 1:
        raise ValueError("route delta锚点漂移")
    source = source.replace(old_delta, new_delta)
    source = source.replace(
        '"route_delta": route_delta, "route_delta_basis": item.get("route_delta_basis"),',
        '"route_delta": route_delta, "route_raw": route_raw, "route_low": route_low, '
        '"route_high": route_high, "route_mean": route_mean, "rmf_mode": RMF_MODE, '
        '"route_delta_basis": item.get("route_delta_basis"),',
    )
    static_check(source)
    return source


def prepare() -> None:
    if BATCH.exists():
        raise SystemExit("对比微函数批次已存在；拒绝覆盖")
    source_summary = json.loads(
        (_project_file(_PROJECT_ROOT, SOURCE_BATCH / "behavior-preflight-v2/summary.json")).read_text(encoding="utf-8")
    )
    if set(source_summary.get("passed_tasks") or []) != {"M1", "M2"}:
        raise ValueError("第一批微函数未通过行为预检")
    BATCH.mkdir(parents=True)
    rows = []
    for task_id, spec in TASKS.items():
        proposal = json.loads(
            (_project_file(_PROJECT_ROOT, SOURCE_BATCH / "generations" / spec["parent"] / "proposal.json")).read_text(
                encoding="utf-8")
        )
        source = build_source(proposal, spec)
        target = _project_file(_PROJECT_ROOT, BATCH / "generations" / task_id)
        target.mkdir(parents=True)
        (target / "candidate.py").write_text(source, encoding="utf-8")
        row = {
            "task": task_id,
            "parent": spec["parent"],
            "mode": spec["mode"],
            "hypothesis": spec["hypothesis"],
            "candidate_sha256": first.sha256_text(source),
            "proposal_sha256": first.sha256_text(json.dumps(proposal, ensure_ascii=False, sort_keys=True)),
            "configs": spec["configs"],
            "default_index": spec["default_index"],
            "effect_tables": 0,
        }
        write_json(target / "record.json", row)
        rows.append(row)
    write_json(_project_file(_PROJECT_ROOT, BATCH / "manifest.json"), {
        "schema": "r10-route-microfunction-contrastive/1",
        "created_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "parents": rows,
        "v2_sha256": first.EXPECTED_V2_SHA256,
        "derivation": (
            "第一批10个非零配置在226冻结真实视图上只形成一个新首选签名、均只改2窗；"
            "无终局标签近似重放提示窗内相对映射可能扩大覆盖，最终覆盖必须以装配后的"
            "候选行为预检和完整阶段效果为准。"
        ),
        "literature_basis": [
            "EoH: 复用高层启发式并变异关键函数",
            "ReEvo: 根据比较反馈反思并重组父代",
            "MEoH/Lexicase: 以行为差异保持结构档案而不是只保留文本不同",
        ],
        "effect_evaluation_started": False,
        "confirmation_reserved": 0,
        "model_calls": 0,
    })
    write_json(_project_file(_PROJECT_ROOT, BATCH / "preflight-plan.json"), {
        "schema": "r10-route-microfunction-contrastive-preflight-plan/1",
        "checks": [
            "六配置含唯一scale=0且逐分等价稳定V2",
            "冻结226真实ScoringView无运行失败并形成不止一个非零首选签名",
            "12个当前核心条件路线输入的拆分与重排逐分不变",
            "只有通过上述检查的行为独特配置才可冻结完整阶段评价预算",
        ],
        "selection_eligible": False,
        "effect_tables": 0,
    })
    (_project_file(_PROJECT_ROOT, BATCH / ".gitignore")).write_text(
        "behavior-preflight-v2/configurations/\neffect-*/baseline/\n"
        "effect-*/candidates/\neffect-*/*.lock\n",
        encoding="utf-8",
    )
    print(json.dumps({"status": "PREPARED", "tasks": rows}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    prepare()
