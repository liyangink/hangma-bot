#!/usr/bin/env python3
"""G90：逐阶段对拍 G89 并按牌山根汇总已关闭候选的逐局收入差。"""

from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/freematch-deep-dive-20260925'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

from collections import Counter
import hashlib
import json
from pathlib import Path
import random

import g14_accounted_paired_panel as g14
from g13_hand_accounting import summarize_hands


HERE = Path(__file__).resolve().parent
G89 = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g89-g88-hm-development-20260928')
G90 = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g90-g89-hand-accounting-20260928')
PREREG = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/G90-G89-HAND-ACCOUNTING-PREREG-2026-09-28.md')
CANDIDATE = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/candidates/G88-POST-CLAIM-FAMILIAR-BIAS-V1.py')
ARM = "candidate@review/freematch-deep-dive-20260925/candidates/G88-POST-CLAIM-FAMILIAR-BIAS-V1.py"
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g90-g89-hand-accounting-20260928/verification.json')
COMPONENTS = g14.COMPONENTS
COUNTS = ("plain_self_wins", "special_self_wins", "other_wins", "draws")
SEED = 2026110803
BOOTSTRAPS = 20_000


def sha(path: Path) -> str:
    """绑定冻结输入及复算程序内容。"""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def ci(values: list[float], rng: random.Random) -> list[float]:
    """以独立牌山根为单位重采样，不把单局误作独立样本。"""
    n = len(values)
    draws = sorted(sum(values[rng.randrange(n)] for _ in range(n)) / n
                   for _ in range(BOOTSTRAPS))
    return [draws[int(0.025 * BOOTSTRAPS)], draws[int(0.975 * BOOTSTRAPS) - 1]]


def main() -> None:
    """先逐桌身份和积分对账，再开放四项收益分量。"""
    if OUT.exists():
        raise FileExistsError("G90 复核已存在，拒绝覆盖")
    old_manifest = json.loads((_project_file(_PROJECT_ROOT, G89 / "manifest.json")).read_text(encoding="utf-8"))
    new_manifest = json.loads((_project_file(_PROJECT_ROOT, G90 / "manifest.json")).read_text(encoding="utf-8"))
    old_result = json.loads((_project_file(_PROJECT_ROOT, G89 / "result.json")).read_text(encoding="utf-8"))
    new_result = json.loads((_project_file(_PROJECT_ROOT, G90 / "result.json")).read_text(encoding="utf-8"))
    if (old_manifest["panel_seed"] != 2026110801 or
            new_manifest["panel_seed"] != 2026110801 or
            old_manifest["arms"] != new_manifest["arms"] != ["r18_v2", ARM] or
            old_manifest["roots_per_mix"] != new_manifest["roots_per_mix"] != 24 or
            old_manifest["root_start"] != new_manifest["root_start"] != 1 or
            old_manifest["candidate_sources"][ARM] != sha(CANDIDATE) or
            new_manifest["candidate_sources"][ARM] != sha(CANDIDATE) or
            old_result["complete_tables"] != new_result["complete_tables"] != 768):
        raise ValueError("G89/G90 实验身份或桌数漂移")
    policy_ids = old_manifest["arms"]
    totals: dict[tuple[str, int, str, str], list[int]] = {}
    counts: dict[tuple[str, int, str, str], list[int]] = {}
    table_count = 0
    hand_count = 0
    stage_count = 0
    for mix in ("H", "M"):
        for root in range(1, 25):
            for seat in range(4):
                for arm in policy_ids:
                    unit = (mix, root, seat, arm, 2026110801)
                    old = json.loads(g14.paired.unit_path(G89, unit).read_text(encoding="utf-8"))
                    new = json.loads(g14.paired.unit_path(G90, unit).read_text(encoding="utf-8"))
                    g14.verify_unit(new, unit=unit, tables_per_stage=2)
                    if (old["mix"], old["root_index"], old["focal_seat"], old["arm"]) != (
                            new["mix"], new["root_index"], new["focal_seat"], new["arm"]):
                        raise ValueError("G89/G90 阶段身份不符")
                    a, b = old["stage"], new["stage"]
                    for name in ("status", "focal_stage_score", "execution_review",
                                 "stage_totals_by_participant", "u_interval"):
                        if a[name] != b[name]:
                            raise ValueError("G89/G90 阶段结果不一致：" + name)
                    if len(a["tables"]) != len(b["tables"]) != 2:
                        raise ValueError("G89/G90 完整桌数不一致")
                    stage_count += 1
                    for before, after in zip(a["tables"], b["tables"]):
                        for name in ("table_id", "seed", "scores_by_seat", "policy_execution"):
                            if before[name] != after[name]:
                                raise ValueError("G89/G90 桌级身份、终分或执行不一致：" + name)
                        for name in ("game_key", "runtime_counts", "completed_hands", "expected_hands"):
                            if before["result"][name] != after["result"][name]:
                                raise ValueError("G89/G90 结果字段不一致：" + name)
                        account = after["hand_account"]
                        independently = summarize_hands(
                            after["hand_records"], focal_seat=account["focal_seat"],
                            initial_scores=(0, 0, 0, 0),
                            final_scores=after["scores_by_seat"], expected_hands=8)
                        if account != independently:
                            raise ValueError("G90 逐局拆账不能独立复算")
                        table_count += 1
                        hand_count += len(after["hand_records"])
                        for name in COMPONENTS:
                            totals.setdefault((mix, root, arm, name), []).append(account[name])
                        for name in COUNTS:
                            counts.setdefault((mix, root, arm, name), []).append(account[name])
    if stage_count != 384 or table_count != 768 or hand_count != 6144:
        raise ValueError("G90 阶段/桌/单局数不足")
    old_roots = {(row["mix"], row["root_index"]): row for row in old_result["root_clusters"]}
    new_roots = {(row["mix"], row["root_index"]): row for row in new_result["root_clusters"]}
    if set(old_roots) != set(new_roots) or len(old_roots) != 48:
        raise ValueError("G89/G90 根身份不符")
    data: dict[str, dict[str, list[float]]] = {
        mix: {name: [] for name in (*COMPONENTS, *COUNTS, "net")}
        for mix in ("H", "M")}
    for mix, root in sorted(old_roots):
        before = old_roots[(mix, root)]
        after = new_roots[(mix, root)]
        old_net = float(before["delta_vs_baseline_per_table"][ARM])
        new_net = float(after["delta_vs_baseline_per_table"][ARM])
        if abs(old_net - new_net) > 1e-9:
            raise ValueError("G89/G90 根级净分不一致")
        component_sum = 0.0
        for name in COMPONENTS:
            value = (sum(totals[(mix, root, ARM, name)]) -
                     sum(totals[(mix, root, "r18_v2", name)])) / 8.0
            if abs(value - after["component_delta_vs_baseline_per_table"][ARM][name]) > 1e-9:
                raise ValueError("G90 根级收益分量不一致")
            data[mix][name].append(value)
            component_sum += value
        if abs(component_sum - old_net) > 1e-9:
            raise ValueError("G90 根级收益分量之和不等于旧净分")
        for name in COUNTS:
            data[mix][name].append((sum(counts[(mix, root, ARM, name)]) -
                                    sum(counts[(mix, root, "r18_v2", name)])) / 8.0)
        data[mix]["net"].append(old_net)
    rng = random.Random(SEED)
    means = {mix: {name: sum(values) / len(values) for name, values in rows.items()}
             for mix, rows in data.items()}
    intervals = {mix: {name: ci(values, rng) for name, values in rows.items()}
                 for mix, rows in data.items()}
    combined = {name: (means["H"][name] + means["M"][name]) / 2
                for name in data["H"]}
    result = {
        "schema": "g90-g89-hand-accounting-verification/1",
        "input_sha256": {"g89_manifest": sha(_project_file(_PROJECT_ROOT, G89 / "manifest.json")),
                         "g89_result": sha(_project_file(_PROJECT_ROOT, G89 / "result.json")),
                         "g90_manifest": sha(_project_file(_PROJECT_ROOT, G90 / "manifest.json")),
                         "g90_result": sha(_project_file(_PROJECT_ROOT, G90 / "result.json")),
                         "candidate": sha(CANDIDATE), "prereg": sha(PREREG),
                         "script": sha(Path(__file__))},
        "same_stage_table_score_execution": True,
        "stages": stage_count, "complete_tables": table_count,
        "complete_hands": hand_count, "roots": 48,
        "mean_delta_per_complete_table": {**means, "combined_equal_mix": combined},
        "root_bootstrap_95_percentile": intervals,
        "root_signs_net": {mix: dict(Counter(
            "positive" if x > 0 else "negative" if x < 0 else "zero"
            for x in data[mix]["net"])) for mix in ("H", "M")},
        "bootstrap_seed": SEED, "bootstrap_replicates": BOOTSTRAPS,
        "boundary": "重跑 G89 旧开发根只作事后收益归因，不是独立候选确认或新根效果证据。",
    }
    OUT.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                   encoding="utf-8")
    print(json.dumps({"counts": (stage_count, table_count, hand_count),
                      "means": result["mean_delta_per_complete_table"]},
                     ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
