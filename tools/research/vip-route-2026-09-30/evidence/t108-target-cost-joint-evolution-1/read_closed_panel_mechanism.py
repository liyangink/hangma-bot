"""只读已闭合公开面板，核对改公式后是否真正改变动作排序。

不装载或调用候选，不重新评分，不读取运行中的自然桌成绩。窗口、换座和
解释条目不是独立牌山；本工具只诊断开发行为，不授强度或上线资格。
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
import ast
import hashlib
import json
from collections import Counter
from pathlib import Path


HERE = Path(__file__).resolve().parent


def digest(path):
    """对只读输入绑定文件摘要，不把摘要视为运行结果证明。"""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    """汇总已实际评分的分值与解释变化；收益变换仅作代数检查。"""
    rows_path = _project_file(_PROJECT_ROOT, HERE / "S02-public-probe/ROWS.jsonl")
    closure_path = _project_file(_PROJECT_ROOT, HERE / "S02-public-probe/ROOT-READBACK.json")
    source_path = _project_file(_PROJECT_ROOT, HERE / "S02-model-output/candidate.py")
    closure = json.loads(closure_path.read_text())
    if closure["complete"] is not True:
        raise ValueError("公开面板尚未完成，禁止机制读回")
    rows = [json.loads(line) for line in rows_path.read_text().splitlines()]
    counts, groups, changed_first = Counter(), {}, []
    tolerance = 1e-12  # 排序点绝对差容差；不代表积分或概率精度。
    for row in rows:
        old = {e["action_key"]: e for e in row["parent_scores"]}
        new = {e["action_key"]: e for e in row["child_scores"]["entries"]}
        if set(old) != set(new):
            raise ValueError("父子合法动作集合不一致")
        score_changes, trace_changes = [], []
        actual = not row["child_score_reused"]
        counts["actual_child_calls"] += actual
        for key, entry in new.items():
            score_changed = abs(entry["score"] - old[key]["score"]) > tolerance
            trace_changed = entry["trace"] != old[key]["trace"]
            if score_changed:
                score_changes.append(key)
            if trace_changed:
                trace_changes.append(key)
            if actual:
                counts["actual_action_outputs"] += 1
                counts["changed_score_outputs"] += score_changed
                counts["changed_trace_outputs"] += trace_changed
                counts["trace_changed_but_score_unchanged_outputs"] += trace_changed and not score_changed
                for tag, item in (("parent", old[key]), ("child", entry)):
                    trace = item["trace"]
                    offer = trace.get("net_offer")
                    if offer:
                        # 只数实际返回解释的聚合分支；不代表全部内部目标。
                        counts[tag + ":reported_net_offer:" + str(offer[1])] += 1
                        counts[tag + ":reported_offer_with_remote_option"] += trace.get("option") is not None
        group = row["label"].split(":")[1] if row["label"].startswith("old:") else "new"
        summary = groups.setdefault(group, Counter())
        summary["windows"] += 1
        summary["score_changed_windows"] += bool(score_changes)
        summary["first_changed_windows"] += row["behavior_changed"]
        summary["trace_only_changed_windows"] += bool(trace_changes) and not score_changes
        counts["windows_with_any_score_change"] += bool(score_changes)
        counts["windows_with_trace_only_changes"] += bool(trace_changes) and not score_changes
        if row["behavior_changed"]:
            changed_first.append({"label": row["label"], "parent_first": row["parent_first"],
                                  "child_first": row["child_first"], "score_changed_actions": score_changes})
    if counts["actual_child_calls"] != closure["actual_child_score_calls"]:
        raise ValueError("真实评分次数与闭合读回不符")
    if counts["actual_action_outputs"] != closure["finite_legal_outputs_actual_calls"]:
        raise ValueError("实际动作输出数与闭合读回不符")
    constants = {}
    for node in ast.parse(source_path.read_text()).body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            constants[node.targets[0].id] = ast.literal_eval(node.value)
    cap, reference = constants["PAYCAP"], constants["PAYREF"]
    algebra = []
    for normalized_amount in (6, 12, 24, 48, 96, 192, 384, 768):
        point = cap * normalized_amount / (reference + abs(normalized_amount))
        doubled = cap * (2 * normalized_amount) / (reference + abs(2 * normalized_amount))
        algebra.append({"normalized_amount": normalized_amount, "rank_point": point,
                        "doubling_rank_point_ratio": doubled / point})
    result = {
        "scope": "closed_adaptive_public_panel_mechanism_diagnosis_not_fitness",
        "input_sha256": {str(p.relative_to(HERE)): digest(p) for p in (rows_path, closure_path, source_path)},
        "reader_sha256": digest(Path(__file__)), "score_difference_tolerance_rank_points": tolerance,
        "window_count": len(rows), "counts": dict(counts),
        "label_groups_not_independent_sources": {k: dict(v) for k, v in groups.items()},
        "changed_first": changed_first,
        "payment_transform_algebra_not_policy_calls": {
            "normalized_amount_unit": "focal_net_score_divided_by_configured_base_score",
            "formula": "PAYCAP * amount / (PAYREF + abs(amount))", "PAYCAP": cap, "PAYREF": reference,
            "rows": algebra, "not_exact_expected_score_or_probability": True},
        "new_business": {"model_calls": 0, "score_calls": 0, "rules_calls": 0,
                         "worlds": 0, "tables": 0, "confirmation_reads": 0},
        "boundaries": ["已曝光面板仅诊断排序行为", "解释变化不能授收入或强度",
                       "有界收益压缩是待验证机制假设，不是数学或规则错误", "未读取运行中桌赛成绩"],
    }
    output = _project_file(_PROJECT_ROOT, HERE / "S02-CLOSED-PANEL-MECHANISM-DIAGNOSIS.json")
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    print(json.dumps({"output": str(output), "counts": dict(counts), "changed_first": changed_first}, ensure_ascii=False))


if __name__ == "__main__":
    main()
