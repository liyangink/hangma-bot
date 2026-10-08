"""只读已闭合评分DTO，重建第二公式的准备代价分量。

不装载候选、不运行规则或完整评分。重建的是启发式effort代数，不是
新动作分、摸牌时间、成功概率或结算预测；节点数量不是独立样本数。
"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t108-target-cost-joint-evolution-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
import gzip
import hashlib
import json
from collections import Counter
from pathlib import Path


HERE = Path(__file__).resolve().parent


def main():
    """核对保白目标自身缺张是否被统一替换成全自然准备缺张。"""
    capture_path = _project_file(_PROJECT_ROOT, HERE / "S02-public-probe/VIEWS.jsonl.gz")
    readback_path = _project_file(_PROJECT_ROOT, HERE / "S02-public-probe/ROOT-READBACK.json")
    source_path = _project_file(_PROJECT_ROOT, HERE / "S02-model-output/candidate.py")
    readback = json.loads(readback_path.read_text())
    assert readback["complete"] is True
    counts, samples = Counter(), []
    identities = set()
    with gzip.open(capture_path, "rt") as stream:
        for line in stream:
            record = json.loads(line)
            if record["view_sha256"] in identities:
                raise ValueError("真实完整输入重复，不能扩充计数")
            identities.add(record["view_sha256"])
            for node in record["view"]["nodes"]:
                waiting = node["waiting"]
                if waiting is None:
                    continue
                counts["waiting_nodes"] += 1
                structure, prep = waiting["structure"], waiting["natural_preparation"]
                whites = structure["whites_held"]
                ordinary_length = max(0, structure["standard_shanten"]) + 1
                prep_need, prep_drop = prep["natural_draw_lower_bound"], prep["natural_discard_lower_bound"]
                counts["preparation_count_conservation_failures"] += prep_drop != prep_need + 1 - whites
                targets = []
                for target in structure["targets"]:
                    if target["family"] != "standard" or target["target_stage"] != "waiting_predecessor":
                        continue
                    retained, need = target["retained_whites"], target["natural_need"]
                    drop, white_drop = target["target_natural_discard_lower_bound"], target["target_white_discard_lower_bound"]
                    counts["standard_predecessor_targets"] += 1
                    counts["target_count_conservation_failures"] += drop != need + 1 - retained or white_drop != retained - 1
                    counts["need_difference_outside_white_used_range"] += not (0 <= prep_need - need <= whites - retained)
                    scale = max(ordinary_length, need + int(target["requires_terminal_draw"]), drop + white_drop)
                    residual_draw = max(0, prep_need - need)
                    residual_drop = max(0, prep_drop - drop)
                    base_effort = max(0, scale - 1)
                    effort = base_effort + residual_draw + residual_drop
                    counts["positive_residual_discard_targets"] += residual_drop > 0
                    counts["base_effort_equals_target_need"] += base_effort == need
                    counts["final_effort_equals_all_natural_preparation_need"] += effort == prep_need
                    targets.append({"retained_whites": retained, "white_used": target["white_used"],
                                    "target_natural_need": need, "target_natural_discard": drop,
                                    "base_effort": base_effort, "residual_draw": residual_draw,
                                    "residual_discard": residual_drop, "final_effort": effort})
                if len({t["target_natural_need"] for t in targets}) > 1:
                    counts["nodes_with_different_target_needs"] += 1
                    equal = len({t["final_effort"] for t in targets}) == 1
                    counts["different_target_needs_collapsed_to_equal_effort_nodes"] += equal
                    if equal and len(samples) < 6:
                        samples.append({"view_sha256": record["view_sha256"], "node_key": node["node_key"],
                                        "whites_held": whites, "prep_need": prep_need, "prep_discard": prep_drop,
                                        "ordinary_length": ordinary_length, "targets": targets})
    assert len(identities) == readback["unique_full_inputs"]
    result = {
        "scope": "closed_public_DTO_component_algebra_not_full_policy_scoring",
        "actual_closed_unique_inputs": len(identities), "counts": dict(counts), "examples_not_action_gold": samples,
        "input_sha256": {str(p.relative_to(HERE)): hashlib.sha256(p.read_bytes()).hexdigest()
                         for p in (capture_path, readback_path, source_path)},
        "reader_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "new_business": {"candidate_invocations": 0, "rules_invocations": 0, "model_calls": 0,
                         "worlds": 0, "tables": 0, "unclosed_natural_outcome_reads": 0},
        "component_arithmetic_reconstructions": counts["standard_predecessor_targets"],
        "not_independent_source_counts": True, "not_fitness_or_rule_error_proof": True,
    }
    output = _project_file(_PROJECT_ROOT, HERE / "S02-CLOSED-TARGET-COST-ALGEBRA.json")
    with output.open("x") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"actual_closed_unique_inputs": len(identities), "counts": dict(counts),
                      "first_example": samples[:1]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
