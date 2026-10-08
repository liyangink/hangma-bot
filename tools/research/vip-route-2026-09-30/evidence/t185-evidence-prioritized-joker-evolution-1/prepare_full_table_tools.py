"""为T185生成独立完整桌工具；复用已核配对与统计，不运行任何桌。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t185-evidence-prioritized-joker-evolution-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
import ast
import json
from pathlib import Path

from common import HERE, OLD, pin, save


def replace_once(text, old, new):
    """固定源片段必须唯一，避免模板漂移后静默替换错误位置。"""
    assert text.count(old) == 1, old
    return text.replace(old, new, 1)


def extract(text, name):
    """只抽取命名纯函数的完整源码；不执行旧批main或修改模块全局。"""
    tree = ast.parse(text)
    return ast.get_source_segment(text, next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name))


def write(name, text):
    """语法核对后排他新建研究工具；不覆写源模板。"""
    ast.parse(text)
    with (_project_file(_PROJECT_ROOT, HERE / name)).open("x") as stream:
        stream.write(text)


def main():
    """新增字段只用于闭合后分层，不进入候选输入或开发选优公式。"""
    old_runner = (OLD / "run_development.py").read_text()
    runner = old_runner.replace('from prepare_diagnostics import pin, save', 'from common import pin, save')
    runner = runner.replace('from run_diagnostic_sources import canonical', 'from common import canonical')
    runner = runner.replace('t182-development', 't185-development')
    runner = replace_once(runner, 'def __init__(self, engine, *, settlement_sink):',
                          'def __init__(self, engine, *, settlement_sink, focal_seat):')
    runner = replace_once(runner, 'self.pairing_proofs = []', 'self.pairing_proofs = []\n        self.focal_seat = focal_seat')
    runner = replace_once(runner, '"export_matches_frozen_sampler": True, "teacher_only_not_policy_input": True}',
        '"focal_initial_white_count": initial["hands"][self.focal_seat].count("白"),\n                "export_matches_frozen_sampler": True, "teacher_only_not_policy_input": True}')
    runner = replace_once(runner, 'PairingAuditEngine(runtime.engine, settlement_sink=settlements.append)',
                          'PairingAuditEngine(runtime.engine, settlement_sink=settlements.append, focal_seat=rotation)')
    write("t185_run_development.py", runner)

    original = (OLD / "close_development.py").read_text()
    repair = (OLD / "close_development_readout_repair.py").read_text()
    reader = original.replace('t182-natural-development', 't185-natural-development').replace('t182-development:', 't185-development:')
    reader = replace_once(reader, 'BOOTSTRAP_SEED = 20261004', 'BOOTSTRAP_SEED = 20261005')
    reader = replace_once(reader, 'import sys\n', 'import sys\nfrom collections import Counter\nfrom hangma_bot.policy.action_value import CANDIDATE_KIND\nfrom hangma_bot.policy.r18_integrated_positive_v2 import R18_INTEGRATED_POSITIVE_V2_NAME\n')
    reader = reader.replace('HERE / "run_development.py"', 'HERE / "t185_run_development.py"')
    reader = reader.replace('HERE / "COMPOSITIONS.json"', 'HERE / "FROZEN-OPPONENT-COMPOSITIONS.json"')
    reader = replace_once(reader, 'for name in ("diagnostic", "confirmation"):', 'for name in ("diagnostic_fresh", "confirmation"):')
    constants = '''LEGACY_INFORMATION = "评分兼容视图[legacy-pass-neutral-v1]：可信过牌恢复旧中性基线；原始规则事实不改写"
CATCH_INFORMATION = "抓打圈生效：排序仅在规则允许的硬约束候选内进行"
NORMAL_INFORMATION = frozenset((LEGACY_INFORMATION, CATCH_INFORMATION))
R18_DYNAMIC_ID = CANDIDATE_KIND + ":" + R18_INTEGRATED_POSITIVE_V2_NAME
KNOWN_TYPES = ("automatic_like", "normal_v0", "r18")
'''
    old_score = extract(reader, "score_receipts")
    new_score = extract(repair, "score_receipts")
    extra = '''            ranked = row.get("candidates")
            require(type(ranked) is list and len(ranked) == len(legal), "完整排名条数不符")
            require({e.get("action_key") for e in ranked} == set(legal) and
                    [e.get("rank") for e in ranked] == list(range(1, len(legal) + 1)), "完整排名键/序号不符")
            require(all(type(e.get("score")) in (int, float) and math.isfinite(e["score"]) for e in ranked), "排名含非有限或非数字评分")
            require(ranked[0]["action_key"] == row["selected_action_key"], "实际动作不是排名第一")
'''
    new_score = replace_once(new_score, '            receipt = call["input_capture"]\n', extra + '            receipt = call["input_capture"]\n')
    helpers = "\n\n".join(extract(repair, n) for n in ("decision_metadata", "input_receipt_fields", "aggregate_audits"))
    reader = replace_once(reader, old_score, constants + "\n\n" + helpers + "\n\n" + new_score)
    reader = replace_once(reader, '"tables": list(tables.values()), "candidates": candidates,',
        '"tables": list(tables.values()), "candidates": candidates,\n        "opponent_compatibility_audit": aggregate_audits([t["audit"] for t in tables.values()]),')
    write("t185_close_development.py", reader)
    # 统计函数仅允许更改本批match名称；所有分账和配对选优保持原算法。
    before, after = ast.parse(original), ast.parse(reader)
    identical = {}
    for name in ("account", "bootstrap_interval", "comparisons"):
        old = extract(original, name).replace("t182-development:", "t185-development:")
        identical[name] = ast.dump(ast.parse(old), include_attributes=False) == ast.dump(ast.parse(extract(reader, name)), include_attributes=False)
    assert all(identical.values())
    files = [Path(__file__), _project_file(_PROJECT_ROOT, HERE / "common.py"), OLD / "run_development.py", OLD / "close_development.py", OLD / "close_development_readout_repair.py",
             _project_file(_PROJECT_ROOT, HERE / "t185_run_development.py"), _project_file(_PROJECT_ROOT, HERE / "t185_close_development.py")]
    save(_project_file(_PROJECT_ROOT, HERE / "FULL-TABLE-TOOLS-PREPARED.json"), {"schema": "t185-full-table-tools/1", "complete": True,
        "files": {str(p): pin(p) for p in files}, "statistical_function_AST_unchanged_except_match_namespace": identical,
        "bootstrap_seed_for_this_batch": 20261005, "extra_readout_checks": "全合法排名与有限分值，真实对手类型兼容信息单列",
        "extra_initial_white_scalar_teacher_only_not_policy_input": True,
        "old_original_modules_mutated": False, "new_worlds_tables_model_calls": 0})
    print({"prepared": True, "stats_identity": identical, "new_worlds_tables": 0}, flush=True)


if __name__ == "__main__":
    main()
