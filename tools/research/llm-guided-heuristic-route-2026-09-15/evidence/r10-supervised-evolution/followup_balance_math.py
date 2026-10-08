"""用有理数及真实输入独立核算本次有界信用公式；不拟合权重或评测效果。"""

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
from fractions import Fraction
from itertools import product
import json

import followup_balance_checks as checks

b = checks.b
OUT = checks.OUT


def expected_order(rows, context):
    """按归一化信用独立计算，避免复用作者的乘权重整数公式。"""
    w, n = context["nonprogress_weight"], context["direct_support"]
    values = []
    for index, row in enumerate(rows):
        value = Fraction(str(row["v2_total"]))
        credit = min(Fraction(row["improvement_weighted_sum"], w), n) if w else Fraction(0)
        values.append((value + credit, value, -index, row["action_key"]))
    return [r[3] for r in sorted(values, reverse=True)]


def main():
    """核对归一化、上限、零权重、稳定平分、允许跨分及真实正负输入。"""
    ranker, digest = checks.load_ranker()
    cases = [
        ("已见负例保留V2", [-72, -79], [129, 326], 21, 95, 0),
        ("已见正例保留结构改良", [-275, -275, -275], [0, 1356, 1356], 25, 93, 1),
        ("信用足够允许跨分", [0, -5], [0, 80], 10, 10, 1),
        ("截断阻止巨大Q覆盖", [0, -3], [0, 100], 2, 10, 0),
        ("零权重退回V2", [0, -1], [0, 999], 10, 0, 0),
        ("组合相同保留V2高分", [0, -2], [0, 20], 10, 10, 0),
        ("全相同保留原序", [0, 0], [10, 10], 10, 10, 0),
        ("双饱和保留V2", [-1, 0], [999, 888], 1, 10, 1),
    ]
    reports = []
    for name, values, qualities, n, w, first in cases:
        rows = [{"action_key": str(i), "v2_total": v, "improvement_weighted_sum": q, "score_parts": {}}
            for i, (v, q) in enumerate(zip(values, qualities, strict=True))]
        context = {"direct_shanten": 1, "direct_support": n, "nonprogress_weight": w}
        before = json.dumps([rows, context], sort_keys=True)
        actual = ranker(rows, context)
        assert actual == expected_order(rows, context) and actual[0] == str(first), name
        assert before == json.dumps([rows, context], sort_keys=True)
        reports.append({"name": name, "order": actual})
    count = 0
    for w, n, difference, qa, qb in product((0, 1, 17, 136), (1, 21, 136), (-7, 0, 7), (0, 28, 1356), (0, 44, 18496)):
        rows = [{"action_key": "a", "v2_total": -100, "improvement_weighted_sum": qa},
                {"action_key": "b", "v2_total": -100 + difference, "improvement_weighted_sum": qb}]
        context = {"direct_support": n, "nonprogress_weight": w}
        assert ranker(rows, context) == expected_order(rows, context)
        count += 1
    reports_from_real_inputs = 0
    behavior = OUT / "behavior-results.json"
    if behavior.exists():
        for row in b.read(behavior):
            if row["status"] == "EVALUATED":
                assert row["ranking_order"] == expected_order(row["ranking_rows"], row["ranking_context"])
                reports_from_real_inputs += 1
    result = {"status": "PASS_EXACT_RATIONAL_CHECK", "source_sha256": digest,
        "arithmetic_source_sha256": b.digest(b.Path(__file__).read_bytes()), "boundary_cases": reports,
        "grid_cases": count, "real_evaluated_requests": reports_from_real_inputs,
        "effect_claim": False, "release_eligible": False}
    b.write(OUT / "math-checks.json", result)
    print(result, flush=True)


if __name__ == "__main__":
    main()
