"""装配第二代路线置信映射，并在冻结真实观察上完成行为预检。"""
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

import argparse
import datetime as dt
import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path


HERE = Path(__file__).resolve().parent
ROUTE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15')
for path in (_project_file(_PROJECT_ROOT, ROUTE / "tools"), HERE, _project_file(_PROJECT_ROOT, ROUTE / "evidence/v4-impl/r9-gate2/run")):
    sys.path.insert(0, str(path))

import route_microfunction_checks_1 as checks  # noqa: E402
import structural_behavior_preflight as preflight  # noqa: E402
from hangma_bot.policy.action_value import batch_to_ranked_candidates  # noqa: E402
from hangma_bot.policy.action_value_executor import ActionValueExecutor, static_check  # noqa: E402


AUTHOR = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/route-microfunction-generation-02-20260921')
BATCH = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/route-confidence-recombination-02-20260921')
PARENT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/route-microfunction-contrastive-01-20260921/behavior-preflight-v2/configurations/r2-cfg-02/candidate.py')
V2 = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/v2-parent-revalidation-20260920/parent/generation/candidate.py')
SOURCE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/route-confidence-recombination-02-20260921/generations/C/candidate.py')
CONFIGS = [
    # 稳定 V2 零效应。
    {"RC_RAW_FLOOR": -0.10, "RC_RAW_WIDTH": 0.35, "RC_MARGIN_REF": 0.22,
     "RC_DISCARD_CAP": 0.0, "RC_CLAIM_FACTOR": 0.5, "RC_FIXED_BLEND": 0.0},
    # GLM C1 原提案。
    {"RC_RAW_FLOOR": -0.10, "RC_RAW_WIDTH": 0.35, "RC_MARGIN_REF": 0.22,
     "RC_DISCARD_CAP": 8.0, "RC_CLAIM_FACTOR": 0.5, "RC_FIXED_BLEND": 0.0},
    # GLM C2 原提案。
    {"RC_RAW_FLOOR": -0.15, "RC_RAW_WIDTH": 0.45, "RC_MARGIN_REF": 0.12,
     "RC_DISCARD_CAP": 7.5, "RC_CLAIM_FACTOR": 0.25, "RC_FIXED_BLEND": 0.0},
    # C1 的副露反事实：禁副露奖励。
    {"RC_RAW_FLOOR": -0.10, "RC_RAW_WIDTH": 0.35, "RC_MARGIN_REF": 0.22,
     "RC_DISCARD_CAP": 8.0, "RC_CLAIM_FACTOR": 0.0, "RC_FIXED_BLEND": 0.0},
    # C1 的副露反事实：四分之一上限。
    {"RC_RAW_FLOOR": -0.10, "RC_RAW_WIDTH": 0.35, "RC_MARGIN_REF": 0.22,
     "RC_DISCARD_CAP": 8.0, "RC_CLAIM_FACTOR": 0.25, "RC_FIXED_BLEND": 0.0},
    # 对 route_margin 收紧，提高领先幅度区分率。
    {"RC_RAW_FLOOR": -0.10, "RC_RAW_WIDTH": 0.35, "RC_MARGIN_REF": 0.12,
     "RC_DISCARD_CAP": 8.0, "RC_CLAIM_FACTOR": 0.5, "RC_FIXED_BLEND": 0.0},
    # 放宽绝对原值起点，检查触发稀疏性。
    {"RC_RAW_FLOOR": -0.15, "RC_RAW_WIDTH": 0.35, "RC_MARGIN_REF": 0.22,
     "RC_DISCARD_CAP": 8.0, "RC_CLAIM_FACTOR": 0.5, "RC_FIXED_BLEND": 0.0},
    # 固定满额父代形状控制；仅 discard/chi/peng，pass 不加分。
    {"RC_RAW_FLOOR": -0.10, "RC_RAW_WIDTH": 0.35, "RC_MARGIN_REF": 0.22,
     "RC_DISCARD_CAP": 8.0, "RC_CLAIM_FACTOR": 1.0, "RC_FIXED_BLEND": 1.0},
]
DEFAULT_INDEX = 1


def digest_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_proposals() -> dict[str, dict]:
    summary = json.loads((_project_file(_PROJECT_ROOT, AUTHOR / "ingest-summary.json")).read_text(encoding="utf-8"))
    if summary.get("accepted") != ["C1", "C2"]:
        raise ValueError("第二代作者提案未全部通过合同")
    return {
        task: json.loads((_project_file(_PROJECT_ROOT, AUTHOR / "generations" / task / "proposal.json")).read_text(encoding="utf-8"))
        for task in ("C1", "C2")
    }


def structure_space() -> dict:
    names = tuple(CONFIGS[0])
    return {
        "parameters": {name: sorted({row[name] for row in CONFIGS}) for name in names},
        "zero_effect": CONFIGS[0],
        "configs": CONFIGS,
    }


def build_source() -> str:
    source = PARENT.read_text(encoding="utf-8")
    first_line, rest = source.split("\n", 1)
    if not first_line.startswith("# STRUCTURE_SPACE_JSON: "):
        raise ValueError("父代参数空间头缺失")
    if rest.startswith("# ACTIVE_CONFIG_JSON: "):
        _, rest = rest.split("\n", 1)
    source = (
        "# STRUCTURE_SPACE_JSON: "
        + json.dumps(structure_space(), ensure_ascii=False, separators=(",", ":"))
        + "\n" + rest
    )
    constants = """RC_RAW_FLOOR = -0.1
RC_RAW_WIDTH = 0.35
RC_MARGIN_REF = 0.22
RC_DISCARD_CAP = 8.0
RC_CLAIM_FACTOR = 0.5
RC_FIXED_BLEND = 0.0
"""
    source, count = re.subn(
        r"RMF_SCALE = .*?\nRMF_SHAPE = .*?\nRMF_CAP = .*?\nRMF_MODE = .*?\n",
        constants, source, count=1,
    )
    if count != 1:
        raise ValueError("父代常数锚点漂移")
    route_call = "route_micro_value(direct_support, self_delta, fan, wall, RMF_SHAPE)"
    if source.count(route_call) != 1:
        raise ValueError("路线微值调用锚点漂移")
    source = source.replace(
        route_call,
        "route_micro_value(direct_support, self_delta, fan, wall, 64.0)",
    )
    old_summary = '''    route_low = None
    route_high = None
    route_mean = None
    if len(route_raw_values) >= 2:
        route_low = min(route_raw_values)
        route_high = max(route_raw_values)
        if route_high > route_low:
            route_mean = sum(route_raw_values) / float(len(route_raw_values))
'''
    new_summary = '''    route_low = None
    route_high = None
    route_second = None
    route_mean = None
    if len(route_raw_values) >= 2:
        for route_value in route_raw_values:
            if route_high is None or route_value > route_high:
                route_second = route_high
                route_high = route_value
            elif route_second is None or route_value > route_second:
                route_second = route_value
            if route_low is None or route_value < route_low:
                route_low = route_value
        route_mean = sum(route_raw_values) / float(len(route_raw_values))
'''
    if source.count(old_summary) != 1:
        raise ValueError("路线窗口汇总锚点漂移")
    source = source.replace(old_summary, new_summary)
    old_delta = '''        route_raw = item.get("route_raw")
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
'''
    new_delta = '''        route_raw = item.get("route_raw")
        route_margin = None
        route_confidence = 0.0
        route_delta = 0.0
        family_factor = 0.0
        if kind == "discard":
            family_factor = 1.0
        elif kind == "chi" or kind == "peng":
            family_factor = RC_CLAIM_FACTOR
        if (RC_DISCARD_CAP != 0.0 and family_factor != 0.0
                and route_raw is not None and route_high is not None
                and route_second is not None and route_raw == route_high):
            route_margin = route_high - route_second
            raw_confidence = (route_raw - RC_RAW_FLOOR) / RC_RAW_WIDTH
            if raw_confidence < 0.0:
                raw_confidence = 0.0
            if raw_confidence > 1.0:
                raw_confidence = 1.0
            margin_confidence = route_margin / RC_MARGIN_REF
            if margin_confidence < 0.0:
                margin_confidence = 0.0
            if margin_confidence > 1.0:
                margin_confidence = 1.0
            route_confidence = RC_FIXED_BLEND + (1.0 - RC_FIXED_BLEND) * (
                raw_confidence * margin_confidence)
            route_delta = RC_DISCARD_CAP * family_factor * route_confidence
        route_confidence = round(route_confidence, 9)
        route_delta = round(route_delta, 6)
'''
    if source.count(old_delta) != 1:
        raise ValueError("路线增量锚点漂移")
    source = source.replace(old_delta, new_delta)
    old_trace = (
        '"route_delta": route_delta, "route_raw": route_raw, "route_low": route_low, '
        '"route_high": route_high, "route_mean": route_mean, "rmf_mode": RMF_MODE, '
        '"route_delta_basis": item.get("route_delta_basis"), "route_valid_count": item.get("route_valid_count"), '
        '"rmf_scale": RMF_SCALE, "rmf_shape": RMF_SHAPE, "rmf_cap": RMF_CAP,'
    )
    new_trace = (
        '"route_delta": route_delta, "route_confidence": route_confidence, '
        '"route_raw": route_raw, "route_low": route_low, "route_high": route_high, '
        '"route_second": route_second, "route_margin": route_margin, "route_mean": route_mean, '
        '"route_delta_basis": item.get("route_delta_basis"), '
        '"route_valid_count": item.get("route_valid_count"), '
        '"rc_raw_floor": RC_RAW_FLOOR, "rc_raw_width": RC_RAW_WIDTH, '
        '"rc_margin_ref": RC_MARGIN_REF, "rc_discard_cap": RC_DISCARD_CAP, '
        '"rc_claim_factor": RC_CLAIM_FACTOR, "rc_fixed_blend": RC_FIXED_BLEND,'
    )
    if source.count(old_trace) != 1:
        raise ValueError("路线trace锚点漂移")
    source = source.replace(old_trace, new_trace)
    static_check(source)
    return source


def prepare() -> None:
    if BATCH.exists():
        raise SystemExit("第二代路线重组目录已存在；拒绝覆盖")
    proposals = load_proposals()
    if proposals["C1"]["family"] != "hybrid" or proposals["C2"]["family"] != "hybrid":
        raise ValueError("本装配器只接受本批两提案共同选择的 hybrid 家族")
    expected = [
        (-0.10, 0.35, 0.22, 8.0, "half"),
        (-0.15, 0.45, 0.12, 7.5, "quarter"),
    ]
    observed = [
        (proposals[key]["raw_floor"], proposals[key]["raw_width"],
         proposals[key]["margin_ref"], proposals[key]["discard_cap"],
         proposals[key]["claim_policy"])
        for key in ("C1", "C2")
    ]
    if observed != expected:
        raise ValueError("模型提案与机械配置锚点不一致")
    source = build_source()
    target = SOURCE.parent
    target.mkdir(parents=True)
    SOURCE.write_text(source, encoding="utf-8")
    write_json(target / "record.json", {
        "schema": "r10-route-confidence-recombination/1",
        "source_sha256": digest_text(source),
        "parents": {
            "fixed_full_bonus": {"path": str(PARENT), "sha256": hashlib.sha256(PARENT.read_bytes()).hexdigest()},
            "C1": proposals["C1"],
            "C2": proposals["C2"],
        },
        "mechanical_counterfactuals": [
            "C1 claim_factor 0/0.25/0.5",
            "C1 margin_ref 0.12/0.22",
            "C1 raw_floor -0.15/-0.10",
            "fixed_full_bonus shape control",
        ],
        "configs": CONFIGS,
        "default_index": DEFAULT_INDEX,
        "effect_tables": 0,
    })
    write_json(_project_file(_PROJECT_ROOT, BATCH / "manifest.json"), {
        "schema": "r10-route-confidence-recombination-batch/1",
        "created_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "author_batch": str(AUTHOR),
        "source": str(SOURCE),
        "source_sha256": digest_text(source),
        "v2": {"path": str(V2), "sha256": hashlib.sha256(V2.read_bytes()).hexdigest()},
        "configurations": len(CONFIGS),
        "selection_eligible": False,
        "effect_tables": 0,
        "confirmation_reserved": 0,
    })
    (_project_file(_PROJECT_ROOT, BATCH / ".gitignore")).write_text("behavior-preflight-v2/configurations/\n", encoding="utf-8")
    print(json.dumps({"status": "PREPARED", "source_sha256": digest_text(source),
                      "configurations": len(CONFIGS)}, ensure_ascii=False, indent=2))


def enrich_preflight() -> None:
    summary_path = _project_file(_PROJECT_ROOT, BATCH / "behavior-preflight-v2/summary.json")
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    views, corpus = preflight.load_real_views()
    config_rows = summary["tasks"][0]["configurations"]
    enrich = []
    invariance = []
    for row in config_rows:
        path = _project_file(_PROJECT_ROOT, BATCH / "behavior-preflight-v2/configurations" / row["config_id"] / "candidate.py")
        executor = ActionValueExecutor(path.read_text(encoding="utf-8"), name=row["config_id"])
        bonuses = []
        confidences = []
        preferred_bonus = []
        family_bonus = Counter()
        for view in views:
            scored = executor.score(view)
            ranked = batch_to_ranked_candidates(scored, view.actions)
            preferred = ranked[0].action_key if ranked else None
            for entry in scored.entries:
                trace = entry.trace
                bonus = float(trace.get("route_delta") or 0.0)
                confidence = float(trace.get("route_confidence") or 0.0)
                if bonus > 0.0:
                    bonuses.append(bonus)
                    family_bonus[entry.action_key.split(":", 1)[0]] += 1
                if confidence > 0.0:
                    confidences.append(confidence)
                if entry.action_key == preferred and bonus > 0.0:
                    preferred_bonus.append(bonus)
        partition = checks.partition_check(path, views)
        invariance.append({
            "config_id": row["config_id"], "cases": partition["cases"],
            "passed": partition["invariant"],
        })
        enrich.append({
            "config_id": row["config_id"],
            "positive_bonus_entries": len(bonuses),
            "positive_confidence_entries": len(confidences),
            "preferred_with_positive_bonus": len(preferred_bonus),
            "bonus_min": min(bonuses) if bonuses else None,
            "bonus_max": max(bonuses) if bonuses else None,
            "distinct_bonus_rounded": len({round(value, 6) for value in bonuses}),
            "confidence_min": min(confidences) if confidences else None,
            "confidence_max": max(confidences) if confidences else None,
            "distinct_confidence_rounded": len({round(value, 6) for value in confidences}),
            "family_bonus_entries": dict(family_bonus),
        })
    if any(row["cases"] != 12 or row["passed"] != 12 for row in invariance):
        raise ValueError("第二代路线拆分/重排不变性失败")
    zero = enrich[0]
    if zero["positive_bonus_entries"] != 0 or config_rows[0]["changed_scores_vs_base"] != 0:
        raise ValueError("第二代零效应未精确退化稳定V2")
    nonzero = enrich[1:]
    if any(row["positive_bonus_entries"] and row["distinct_bonus_rounded"] <= 1
           for row in nonzero[:-1]):
        raise ValueError("幅度恢复配置仍退化为固定奖励")
    summary["schema"] = "r10-route-confidence-behavior-preflight/1"
    summary["confidence_behavior"] = enrich
    summary["route_partition_and_order"] = {
        "current_core_real_views": corpus["unique_real_views"],
        "configurations": invariance,
        "cases": sum(row["cases"] for row in invariance),
        "passed": sum(row["passed"] for row in invariance),
    }
    summary["scope_note"] = (
        "冻结真实观察只检验接线、精确退化、奖励幅度和路线变形；不提供动作标签或效果。"
    )
    write_json(summary_path, summary)


def run_preflight() -> None:
    if not SOURCE.exists():
        raise SystemExit("请先 prepare")
    preflight.BATCH = BATCH
    preflight.SOURCES = {"C": SOURCE}
    preflight.BASES = {"C": V2}
    preflight.main()
    enrich_preflight()
    summary = json.loads((_project_file(_PROJECT_ROOT, BATCH / "behavior-preflight-v2/summary.json")).read_text(encoding="utf-8"))
    print(json.dumps({
        "status": "COMPLETE_ROUTE_CONFIDENCE_PREFLIGHT",
        "passed_tasks": summary["passed_tasks"],
        "failed_tasks": summary["failed_tasks"],
        "configurations": summary["configurations_materialized"],
        "partition_cases": summary["route_partition_and_order"]["cases"],
        "behavior": summary["confidence_behavior"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("prepare", "preflight"))
    args = parser.parse_args()
    {"prepare": prepare, "preflight": run_preflight}[args.operation]()
