"""把 R18 截断/缺陷作者交付规范化为冻结机会算法的最小 V2 改写。

原始 GLM 源码保留作作者证据，但不直接执行：它们包含字段层级、未知池分母和
受限子集错误。本工具从稳定 V2 重新生成同一预登记机制，避免逐项手改后失去血缘。
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

import hashlib
import json
from pathlib import Path
import sys


HERE = Path(__file__).resolve().parent
ROUTE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15')
ADMISSION = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/v4-impl/r9-admission')
for path in (_project_file(_PROJECT_ROOT, ROUTE / "tools"), _project_file(_PROJECT_ROOT, ADMISSION / "p25-dev-cards"), HERE):
    sys.path.insert(0, str(path))

import sitin_generate as gen  # noqa: E402
from hangma_bot.policy.action_value_seeds import ActionValueScorer  # noqa: E402


AUTHOR = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-opportunity-author-01-20260922')
V2 = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/v2-parent-revalidation-20260920/parent/generation/candidate.py')


TAIL = '''    final_entries = []
    for entry in entries:
        score = entry.get("score")
        if entry.get("action_type") == "hu" and hu_level is not None:
            score = hu_level + 1.0
        if entry.get("trace").get("unknown") is True:
            score = known_floor - 1.0
        final_entries.append({"action_key": entry.get("action_key"), "score": score, "trace": entry.get("trace")})
    return {"status": "SCORED", "entries": final_entries, "reason": "胡以动态排序层优先；未知动作严格锚定在已知最终分最低值以下"}
'''


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def target_condition(task: str) -> str:
    if task == "K3":
        return '''                target_shape = tile_code != wealth
                family_ok = False
                families = action.get("family_progress_entries")
                if families is not None:
                    for family in families:
                        if family.get("family") == "baotou" and family.get("route_status") == "witnessed" and family.get("progress") in ("same", "advance"):
                            family_ok = True'''
    return '''                target_shape = tile_code == wealth
                family_ok = False
                families = action.get("family_progress_entries")
                if families is not None:
                    for family in families:
                        if family.get("family") == "chain" and family.get("route_status") == "witnessed" and family.get("progress") == "advance":
                            family_ok = True'''


def overlay(task: str) -> str:
    if task == "K3":
        name = "three_wealth_keep_proxy_boundary/v1"
        wealth_required = 3
        ratio = 1.25
    else:
        name = "four_wealth_piao_proxy_boundary/v1"
        wealth_required = 4
        ratio = 1.50
    return f'''    overlay_name = "{name}"
    overlay_required_ratio = {ratio:.2f}
    overlay_best_key = None
    overlay_best_proxy = None
    overlay_immediate_hu = None
    overlay_actual_ratio = None
    overlay_triggered = False
    overlay_degrade_reason = "目标机会窗口不成立"
    overlay_unknown_pool = None
    if rule_state.get("baotou") is True and wealth_count == {wealth_required} and hu_level is not None:
        overlay_degrade_reason = "立即胡结算事实不完整"
        for action in actions:
            if action.get("is_legal") is True and action.get("action_type") == "hu":
                settlement = action.get("immediate_settlement")
                if settlement is not None:
                    delta = settlement.get("score_delta")
                    if delta is not None and len(delta) == 4:
                        amount = delta[seat]
                        if amount is not None and amount is not True and amount is not False:
                            value = float(amount)
                            if value - value == 0 and value > 0.0:
                                overlay_immediate_hu = value
        remaining_count = visible.get("remaining_tile_count")
        hand_counts = visible.get("hand_counts")
        if remaining_count is not None and remaining_count is not True and remaining_count is not False and hand_counts is not None and len(hand_counts) == 4:
            pool = float(remaining_count)
            pool_ok = pool - pool == 0 and pool >= 0.0
            for other_seat in range(4):
                if other_seat != seat:
                    count = hand_counts[other_seat]
                    if count is None or count is True or count is False:
                        pool_ok = False
                    else:
                        count_value = float(count)
                        if count_value - count_value != 0 or count_value < 0.0:
                            pool_ok = False
                        else:
                            pool += count_value
            if pool_ok and pool > 0.0:
                overlay_unknown_pool = pool
        if overlay_immediate_hu is not None and overlay_unknown_pool is not None:
            overlay_degrade_reason = "没有完整且满足家族转移的目标弃牌"
            for action in actions:
                key = action.get("action_key")
                kind = action.get("action_type")
                if kind != "discard" or key is None:
                    continue
                tile_code = key[8:]
{target_condition(task)}
                facts_ok = target_shape and family_ok
                if action.get("value_coverage") != "complete":
                    facts_ok = False
                issues = action.get("value_issues")
                if issues is None or len(issues) != 0:
                    facts_ok = False
                routes = action.get("routes")
                if routes is None or len(routes) == 0:
                    facts_ok = False
                numerator = 0.0
                seen_codes = []
                if facts_ok:
                    for route in routes:
                        route_ok = route.get("followup_discard") is None
                        route_shanten = route.get("shanten")
                        if route_shanten is None or route_shanten is True or route_shanten is False or route_shanten != 0:
                            route_ok = False
                        if route.get("support") != "conditional_witness":
                            route_ok = False
                        conditional = route.get("conditional_settlement")
                        route_value = None
                        if conditional is not None:
                            route_delta = conditional.get("score_delta")
                            if route_delta is not None and len(route_delta) == 4:
                                route_amount = route_delta[seat]
                                if route_amount is not None and route_amount is not True and route_amount is not False:
                                    converted = float(route_amount)
                                    if converted - converted == 0 and converted >= 0.0:
                                        route_value = converted
                        if route_value is None:
                            route_ok = False
                        useful_tiles = route.get("useful_tiles")
                        if useful_tiles is None or len(useful_tiles) == 0:
                            route_ok = False
                        if route_ok:
                            for useful in useful_tiles:
                                code = useful.get("code")
                                estimate = useful.get("remaining_estimate")
                                if code is None or code in seen_codes or estimate is None or estimate is True or estimate is False:
                                    route_ok = False
                                else:
                                    estimate_value = float(estimate)
                                    if estimate_value - estimate_value != 0 or estimate_value < 0.0 or estimate_value > 4.0:
                                        route_ok = False
                                    else:
                                        seen_codes.append(code)
                                        numerator += route_value * estimate_value
                        if not route_ok:
                            facts_ok = False
                            break
                if facts_ok:
                    proxy = numerator / overlay_unknown_pool
                    if overlay_best_proxy is None or proxy > overlay_best_proxy or (proxy == overlay_best_proxy and key < overlay_best_key):
                        overlay_best_proxy = proxy
                        overlay_best_key = key
            if overlay_best_proxy is not None:
                overlay_actual_ratio = overlay_best_proxy / overlay_immediate_hu
                overlay_degrade_reason = "条件代理优势未达到预登记风险缓冲"
                if overlay_actual_ratio >= overlay_required_ratio:
                    overlay_triggered = True
                    overlay_degrade_reason = "触发"
    final_entries = []
    for entry in entries:
        score = entry.get("score")
        if entry.get("action_type") == "hu" and hu_level is not None:
            score = hu_level + 1.0
        if entry.get("trace").get("unknown") is True:
            score = known_floor - 1.0
        v2_score = score
        if overlay_triggered and entry.get("action_key") == overlay_best_key:
            score = hu_level + 2.0
        trace = entry.get("trace")
        if overlay_best_key is not None and entry.get("action_key") == overlay_best_key:
            trace = {{"basis": trace.get("basis"), "base_score": trace.get("base_score"), "shanten_after": trace.get("shanten_after"), "best_shanten_non_pass": trace.get("best_shanten_non_pass"), "wealth_part": trace.get("wealth_part"), "wealth_discard_part": trace.get("wealth_discard_part"), "river_part": trace.get("river_part"), "risk_units": trace.get("risk_units"), "style_part": trace.get("style_part"), "unknown": trace.get("unknown"), "unknown_policy": trace.get("unknown_policy"), "hu_sorting_layer": trace.get("hu_sorting_layer"), "scope": trace.get("scope"), "r18_opportunity_overlay": {{"structure": overlay_name, "triggered": overlay_triggered, "wealth_count": wealth_count, "immediate_hu_value": overlay_immediate_hu, "continue_proxy": overlay_best_proxy, "proxy_unknown_pool": overlay_unknown_pool, "required_ratio": overlay_required_ratio, "actual_ratio": overlay_actual_ratio, "score_delta": score - v2_score, "degrade_reason": overlay_degrade_reason, "limitation": "仅下一次本人自摸立即胡的条件代理，不是完整牌局期望；未建模他家先胡、鸣牌和轮转生存"}}}}
        final_entries.append({{"action_key": entry.get("action_key"), "score": score, "trace": trace}})
    reason = "胡以动态排序层优先；未知动作严格锚定在已知最终分最低值以下"
    if overlay_triggered:
        reason = reason + "；R18机会边界触发，目标弃牌以胡层上方1分排序"
    return {{"status": "SCORED", "entries": final_entries, "reason": reason}}
'''


def build(task: str) -> str:
    parent = V2.read_text(encoding="utf-8")
    if parent.count(TAIL) != 1:
        raise RuntimeError("稳定 V2 尾部锚点不唯一")
    title = (
        '"""R18 三财保财条件代理边界；稳定 V2 是完整回退。"""'
        if task == "K3"
        else '"""R18 四财飘条件代理边界；稳定 V2 是完整回退。"""'
    )
    first, rest = parent.split("\n", 1)
    if not first.startswith('"""'):
        raise RuntimeError("稳定 V2 缺模块说明")
    return title + "\n" + rest.replace(TAIL, overlay(task))


def main() -> None:
    parent = V2.read_text(encoding="utf-8")
    summary = []
    for task in ("K3", "P4"):
        raw = _project_file(_PROJECT_ROOT, AUTHOR / "generations" / task / "candidate.py")
        code = build(task)
        target = _project_file(_PROJECT_ROOT, AUTHOR / "generations" / task / "normalized-v2")
        if target.exists():
            raise SystemExit(task + " 规范化目录已存在；拒绝覆盖")
        target.mkdir(parents=True)
        (target / "candidate.py").write_text(code, encoding="utf-8")
        precheck = gen.precheck_action_value_candidate(code)
        load_error = None
        if precheck.get("ok") is True:
            try:
                ActionValueScorer("r18-normalized-" + task, code)
            except Exception as exc:  # noqa: BLE001 - 规范化证据需记录装载错误
                load_error = type(exc).__name__ + ": " + str(exc)
        record = {
            "schema": "r18-opportunity-normalization/1",
            "task": task,
            "parent_path": str(V2),
            "parent_sha256": sha256_text(parent),
            "raw_author_path": str(raw),
            "raw_author_sha256": sha256_text(raw.read_text(encoding="utf-8")),
            "normalized_sha256": sha256_text(code),
            "fixed_design_sha256": sha256_text(
                __import__("r18_opportunity_author")._repair_design(task)
            ),
            "effect_feedback_used": False,
            "hidden_input_used": False,
            "semantic_corrections": [
                "conditional_settlement 从 routes[] 读取，不从动作层读取",
                "进张牌码读取 useful_tiles[].code，不读取不存在的 tile",
                "未知池只计剩余牌墙和其他三家暗手，不重复加入本家手牌",
                "每条路线使用自己的 score_delta，不能复用单个动作级值",
                "value_issues 缺失视为未知并回退，不能当空集合",
                "候选返回值不做字典下标写入，保持受限子集纯返回",
                "目标形状与家族门控保留在逐动作循环内，不能退缩为只检查最后动作",
            ],
            "static_precheck": precheck,
            "load_error": load_error,
            "accepted_for_development_preflight": (
                precheck.get("ok") is True and load_error is None
            ),
        }
        write_json(target / "normalization-record.json", record)
        summary.append(record)
    write_json(_project_file(_PROJECT_ROOT, AUTHOR / "normalized-v2-ingest-summary.json"), {
        "schema": "r18-opportunity-normalized-ingest/1",
        "rows": summary,
        "accepted_for_development_preflight": [
            row["task"] for row in summary
            if row["accepted_for_development_preflight"]
        ],
        "hidden_evaluation_started": False,
    })
    print(json.dumps({
        "accepted": [
            row["task"] for row in summary
            if row["accepted_for_development_preflight"]
        ],
        "problems": {
            row["task"]: list(row["static_precheck"].get("problems") or [])
            + ([row["load_error"]] if row["load_error"] else [])
            for row in summary
            if not row["accepted_for_development_preflight"]
        },
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
