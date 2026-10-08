"""作者初答之前冻结牌型选择的合成边界；不指定最优动作或冒充历史牌局。"""

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
from dataclasses import replace
import strong_seed_batch as b
import pattern_option_batch as batch
from check_discard_arithmetic import action, view
from hangma_bot.hangma.interface import UsefulTileFact

PATH = batch.OUT / 'boundary-inputs.json'


def shaped(code, normal, seven, support=12):
    """牌型向听来自合成合同事实；两牌型支持重合，不得无依据累加。"""
    a = action(code, support, min(normal, seven))
    return replace(a, standard_shanten_after=normal, seven_pairs_shanten_after=seven,
        standard_useful_tiles=a.useful_tiles, seven_pairs_useful_tiles=a.useful_tiles)


def cases():
    """只预登记缺证据退化和不相关动作不变；具体新增分数待独立手算。"""
    a, z = shaped('1w', 2, 4), shaped('2w', 2, 3)
    result = [('secondary_distance', view((a, z), familiar=()), None),
        ('equal_patterns', view((shaped('1w', 2, 2), shaped('2w', 2, 2)), familiar=()), None),
        ('seven_best', view((shaped('1w', 3, 2), shaped('2w', 4, 2)), familiar=()), None),
        ('ordinary_far_ahead', view((shaped('1w', 1, 5), shaped('2w', 1, 4)), familiar=()), None)]
    for field in ('standard_shanten_after', 'seven_pairs_shanten_after', 'standard_useful_tiles', 'seven_pairs_useful_tiles'):
        result.append(('missing_'+field, view(tuple(replace(x, **{field: None}) for x in (a,z)), familiar=()), 'per_action_parent_fallback'))
    result += [
        ('known_empty_support', view(tuple(replace(x, seven_pairs_useful_tiles=()) for x in (a,z)), familiar=()), None),
        ('unequal_support', view((shaped('1w', 2, 3, 12), shaped('2w', 2, 2, 8)), familiar=()), None),
        ('hu_priority', view((a, z, action('', kind='hu')), familiar=()), 'hu_first'),
        ('unknown_floor', view((a, z, action('', kind='pass')), familiar=()), 'known_floor_minus_1'),
        ('non_discard', view((action('1w', 12, kind='peng'), action('', 12, kind='pass')), familiar=()), 'parent_identical'),
        ('all_unknown', view((action('1w'), action('2w')), familiar=()), 'abstain'),
    ]
    return result


def freeze():
    """一次落盘，保留输入摘要与先验不变量；不会根据候选表现删例。"""
    assert not PATH.exists()
    b.write(PATH, {'created_at_utc': b.search.utc_now(), 'runner_sha256': b.digest(b.Path(__file__).read_bytes()),
        'rows': [{'name': name, 'view': sample.candidate_view(), 'invariant': invariant}
                 for name, sample, invariant in cases()],
        'scope': '14个合成合同输入，不证明合法历史可达，不计强度样本', 'release_eligible': False})
    print('frozen',len(cases()))


if __name__ == '__main__':
    freeze()
