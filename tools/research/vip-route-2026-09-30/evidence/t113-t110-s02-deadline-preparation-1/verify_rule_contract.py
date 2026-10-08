"""最小复现真实测量器的合法集合检查；不调用规则分析或候选评分。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t113-t110-s02-deadline-preparation-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
import argparse
import ast
from pathlib import Path
import sys

RUNTIME = Path('/Users/liyang/.codex/worktrees/t54-public-count-cache/hangma-bot')


def main():
    """从真实调用点抽取表达式，在真实 RuleAnalysis 上验证字段契约。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runner', type=Path, required=True)
    args = parser.parse_args()
    sys.path[:0] = [str(RUNTIME), str(_project_file(_PROJECT_ROOT, RUNTIME / 'src'))]
    from hangma_bot.hangma.interface import RuleAnalysis, RuleCompleteness
    # 空合法集只用于复现属性访问；不声称这是完整的可行动牌局。
    rules = RuleAnalysis((), None, RuleCompleteness.COMPLETE, 'measurement-contract-fixture', ())
    tree = ast.parse(args.runner.read_text())
    selected = []
    for node in ast.walk(tree):
        if isinstance(node, ast.SetComp):
            for part in ast.walk(node):
                if isinstance(part, ast.Attribute) and isinstance(part.value, ast.Name) and part.value.id == 'rules':
                    selected.append(node)
                    break
    if len(selected) != 1:
        raise ValueError('无法唯一定位真实合法候选集合检查')
    expression = ast.fix_missing_locations(ast.Expression(selected[0]))
    try:
        actual = eval(compile(expression, str(args.runner), 'eval'), {'rules': rules})
        assert actual == set()
    except AttributeError as exc:
        print({'rule_contract_valid': False, 'error': str(exc), 'new_rules_scores_choose_worlds_tables': 0})
        return 1
    print({'rule_contract_valid': True, 'real_type': type(rules).__name__,
           'new_rules_scores_choose_worlds_tables': 0})
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
