"""路线吃碰专长新来源失败诊断：拆分改选方向、对手池与阶段结果关联。"""
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
import json
import math
from collections import Counter, defaultdict
from pathlib import Path


HERE = Path(__file__).resolve().parent
BATCH = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/cross-specialist-01-20260921')
NEW_SOURCE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/cross-specialist-01-20260921/new-source')
DEVELOPMENT_C = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/cross-specialist-01-20260921/effect-c')
OUT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/cross-specialist-01-20260921/new-source/diagnosis.json')


def read(path: Path):
    """读取 UTF-8 JSON。"""
    return json.loads(path.read_text(encoding="utf-8"))


def action_family(action_key: str | None) -> str:
    """把稳定动作键压缩为动作族，不解析规则语义。"""
    if action_key is None:
        return "none"
    return action_key.split(":", 1)[0]


def table_audits(root: Path, prefix: str, mixes: tuple[str, ...], roots: range):
    """遍历候选阶段产物，返回逐阶段改选审计。"""
    for mix in mixes:
        for root_index in roots:
            for seat in range(4):
                label = f"{prefix}-{mix}-r{root_index:02d}-s{seat}"
                raw = read(root / label / "result.json")["raw"]
                audit = [row for table in raw["tables"] for row in table["prototype_audit"]]
                yield mix, root_index, seat, audit


def audit_distribution(root: Path, prefix: str, roots: range) -> dict:
    """汇总一个来源的改选方向和阶段覆盖。"""
    decisions = Counter()
    changes = Counter()
    changed_stages = Counter()
    stage_change_histogram = Counter()
    per_root = defaultdict(Counter)
    for mix, root_index, _seat, rows in table_audits(root, prefix, ("H", "M"), roots):
        local = 0
        for row in rows:
            decisions[mix] += 1
            if not row["changed"]:
                continue
            local += 1
            source = action_family(row["base_first"])
            target = action_family(row["selected_first"])
            changes[(mix, source, target)] += 1
            per_root[(mix, root_index)][source + "->" + target] += 1
        changed_stages[mix] += int(local > 0)
        stage_change_histogram[(mix, local)] += 1
    return {
        "decisions": dict(decisions),
        "changes": {
            mix: [
                {"from": source, "to": target, "count": count}
                for (row_mix, source, target), count in sorted(changes.items())
                if row_mix == mix
            ]
            for mix in ("H", "M")
        },
        "changed_stages": dict(changed_stages),
        "stage_change_histogram": {
            mix: {str(local): count for (row_mix, local), count in sorted(stage_change_histogram.items())
                  if row_mix == mix}
            for mix in ("H", "M")
        },
        "per_root": {
            mix: {
                str(root_index): dict(per_root[(mix, root_index)])
                for root_index in roots
            }
            for mix in ("H", "M")
        },
    }


def pearson(xs: list[float], ys: list[float]) -> float | None:
    """计算描述性 Pearson 相关；零方差时返回 None。"""
    if len(xs) != len(ys) or not xs:
        return None
    mx = sum(xs) / len(xs)
    my = sum(ys) / len(ys)
    dx = [value - mx for value in xs]
    dy = [value - my for value in ys]
    denom = math.sqrt(sum(value * value for value in dx) * sum(value * value for value in dy))
    if denom == 0:
        return None
    return sum(a * b for a, b in zip(dx, dy, strict=True)) / denom


def effect_by_change_count(distribution: dict) -> dict:
    """按候选轨迹的改选数描述阶段效用差；不把相关性冒充因果。"""
    samples = read(_project_file(_PROJECT_ROOT, NEW_SOURCE / "samples.json"))
    by_mix = {}
    for mix in ("H", "M"):
        stage_counts = defaultdict(int)
        for root_index, counts in distribution["per_root"][mix].items():
            stage_counts[int(root_index)] = sum(counts.values())
        grouped = defaultdict(list)
        root_deltas = defaultdict(list)
        for sample in samples:
            if sample["opponent_mix"] != mix:
                continue
            delta = (
                float(sample["arms"]["candidate"]["u_low"])
                - float(sample["arms"]["baseline"]["u_low"])
            )
            root_deltas[int(sample["root_index"])].append(delta)
        xs, ys = [], []
        for root_index in range(1, 65):
            count = stage_counts[root_index]
            delta = sum(root_deltas[root_index]) / len(root_deltas[root_index])
            grouped[count].append(delta)
            xs.append(float(count))
            ys.append(delta)
        by_mix[mix] = {
            "by_root_change_count": {
                str(count): {
                    "roots": len(values),
                    "mean_root_delta": sum(values) / len(values),
                }
                for count, values in sorted(grouped.items())
            },
            "pearson_change_count_vs_root_delta": pearson(xs, ys),
            "note": "候选改选会改变后续轨迹；这里只是描述关联，不是单步动作因果估计。",
        }
    return by_mix


def run() -> None:
    """生成开发与全新来源的可复算行为分布对照。"""
    if OUT.exists():
        raise SystemExit("路线吃碰新来源诊断已存在；拒绝覆盖")
    new_distribution = audit_distribution(
        _project_file(_PROJECT_ROOT, NEW_SOURCE / "candidate"), "ns-candidate", range(1, 65)
    )
    development_distribution = audit_distribution(
        _project_file(_PROJECT_ROOT, DEVELOPMENT_C / "candidates/route_claim_only"),
        "c-route_claim_only",
        range(13, 29),
    )
    result = {
        "schema": "r10-route-claim-new-source-diagnosis/1",
        "scope": "只读行为和阶段结果诊断；不重评候选，不改变关闭裁定",
        "new_source": new_distribution,
        "development_c_new_roots": development_distribution,
        "new_source_effect_by_change_count": effect_by_change_count(new_distribution),
        "interpretation_limits": [
            "prototype_audit 的 base_first 是候选轨迹同状态下的 V2 反事实排序。",
            "首次改选后候选与基线轨迹可分叉，后续审计行不能与基线轨迹逐动作配对。",
            "根级改选数与阶段效用差相关只用于提出下一假设，不能证明某个动作正确或错误。",
        ],
    }
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("run",))
    parser.parse_args()
    run()
