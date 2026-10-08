"""作者交付前定义名次风格边界输入；使用合成合同形状，不声称历史可达。"""

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
import stage_style_batch as experiment
from check_discard_arithmetic import action, view
from hangma_bot.policy.action_value import CompetitionView

PATH = experiment.OUT / 'boundary-inputs.json'


def cases():
    """固定0号座位，四座积分顺序0—3；所有实际例的阶段积分和为零。"""
    vectors = (
        ('strict_first', (30, -10, -10, -10)),
        ('strict_second', (10, 30, -20, -20)),
        ('strict_third', (-10, 30, 0, -20)),
        ('strict_last', (-30, 10, 10, 10)),
        ('tie_first_two', (10, 10, -10, -10)),
        ('tie_second_third', (0, 10, 0, -10)),
        ('tie_first_three', (10, 10, 10, -30)),
        ('tie_all', (0, 0, 0, 0)),
        ('tie_last_two', (-10, 10, 10, -10)),
    )
    base = view((action('4b', 15), action('8t', 10)))
    base = replace(base, competition=None)
    rows = []
    for name, scores in vectors:
        competition = CompetitionView(stage_scores=scores, table_scores=(0, 0, 0, 0),
            current_stage_scores=scores, freshness_masks=('stage_account:complete', 'table_account:live'))
        sample = replace(base, competition=competition)
        rows.append((name, sample))
        # 相同阶段合计、不同已完成账/本桌账拆分，隔离重复相加错误。
        live = (-3, 1, 1, 1)
        completed = tuple(scores[i] - live[i] for i in range(4))
        rows.append((name + '_split', replace(sample,
            visible_state=replace(sample.visible_state, scores=live),
            competition=replace(competition, stage_scores=completed, table_scores=live))))
    rows.append(('no_competition', base))
    for mask in ('stage_account:absent', 'stage_account:unmappable'):
        rows.append((mask, replace(base, competition=CompetitionView(
            table_scores=(0, 0, 0, 0), freshness_masks=(mask, 'table_account:live')))))
    rows.append(('no_discard', replace(rows[0][1], actions=(action('', 10, kind='pass'),))))
    rows.append(('hu_present', replace(rows[0][1], actions=tuple(sorted(
        base.actions + (action('', kind='hu'),), key=lambda a: a.action_key)))))
    rows.append(('unknown_floor', replace(rows[0][1], actions=tuple(sorted(
        base.actions + (action('', kind='pass'),), key=lambda a: a.action_key)))))
    return rows


def freeze():
    """只冻结输入；期望分数须在独立审阅作者声明后手算，不能复制候选输出。"""
    assert not PATH.exists()
    rows = [{'name': name, 'view': sample.candidate_view()} for name, sample in cases()]
    b.write(PATH, {'created_at_utc': b.search.utc_now(), 'rows': rows,
        'runner_sha256': b.digest(b.Path(__file__).read_bytes()),
        'scope': '24个合成输入；无效果样本，拆分不变性只约束阶段风格机制',
        'selection_eligible': False})
    print('frozen', len(rows), flush=True)


if __name__ == '__main__':
    freeze()
