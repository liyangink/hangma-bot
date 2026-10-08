"""纯标准库冻结八个多白物理母源；不分析胡牌、不指定未来进张。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t32-new-multiwhite-source-preparation-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
from pathlib import Path
from collections import Counter
import ast
import hashlib
import json
import random

HERE = Path(__file__).resolve().parent
REPO = _PROJECT_ROOT
TEACHER = ['1w','2w','3w','1b','2b','3b','4t','5t','6t','东','东','7w','8w']
# 胡牌资格只是先验设计假设；START 后必须由 hangma 模块核验。
POSES = (
    ('three_white_broad_nonhu', ['白']*3+['2w','3w','5w','6w','2b','3b','5b','6b','东','南'], '北', False),
    ('three_white_compact_current_hu', ['白']*3+['2w','3w','4w','6w','7w','3b','4b','6t','7t','中'], '8t', True),
    ('four_white_broad_nonhu', ['白']*4+['1w','2w','4w','5w','1b','2b','4b','5b','东'], '南', False),
    ('four_white_natural_meld_current_hu', ['白']*4+['2w','3w','4w','1b','2b','3b','4t','5t','6t'], '5w', True),
)


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def main():
    """136 张守恒；只洗一次余牌，8 源原样冻结，无失败替换或结果挑选。"""
    module = ast.parse((_project_file(_PROJECT_ROOT, REPO/'src/hangma_bot/kernel/actions.py')).read_text())
    codes = next(ast.literal_eval(n.value) for n in module.body if isinstance(n, ast.AnnAssign)
        and isinstance(n.target, ast.Name) and n.target.id == 'CANONICAL_TILE_ORDER')
    assert len(codes) == len(set(codes)) == 34
    proposals = []
    for shape, focal, drawn, hu in POSES:
        for teacher in (False, True):
            seed = 2026103001+len(proposals)
            others = {'1': TEACHER} if teacher else {}
            assert len(focal) == 13 and all(len(h) == 13 for h in others.values())
            reserved = Counter(focal+[drawn]+[t for h in others.values() for t in h])
            assert set(reserved) <= set(codes) and max(reserved.values()) <= 4
            residual = [c for c in codes for _ in range(4-reserved[c])]
            random.Random(seed).shuffle(residual)
            hands, cursor = [list(focal), [], [], []], 0
            for seat in range(1, 4):
                if str(seat) in others:
                    hands[seat] = list(others[str(seat)])
                else:
                    hands[seat] = residual[cursor:cursor+13]
                    cursor += 13
            wall = residual[cursor:]
            deck = [t for block in range(3) for seat in range(4) for t in hands[seat][block*4:block*4+4]]
            deck += [h[12] for h in hands]+[drawn]+wall
            assert len(wall) == 83 and len(deck) == 136 and Counter(deck) == Counter({c: 4 for c in codes})
            proposals.append({'root_id': 'vip-t32-new-multiwhite-'+str(seed), 'seed': seed,
                'shape': shape, 'profile': 'opponent_near_completion' if teacher else shape,
                'opponent_condition': 'fixed_concealed_near_ready_pending_rule_check' if teacher else 'unconditioned_residual_shuffle',
                'focal_hand13': focal, 'dealer_drawn_tile': drawn, 'fixed_other_hands': others,
                'hands13_by_seat': hands, 'wall': wall, 'full_physical_deck': deck,
                'deck_sha256': hashlib.sha256(canonical(deck)).hexdigest(),
                'qualification': {'focal_seat': 0, 'phase': 'draw', 'visible_white_count': focal.count('白')+int(drawn == '白'),
                    'current_legal_hu': hu},
                'teacher_data_never_candidate_input': True, 'qualification_not_executed': True})
    frame = {'schema': 't32-new-multiwhite-physical-source-preparation/1', 'status': 'pure_preparation_no_START',
        'proposals': proposals, 'planned_mother_roots': 8, 'planned_worlds': 16, 'continuation_instances_upper': 80,
        'candidates_unchanged': ['T24', 'T25'], 'parent_candidate_id': 'edda117c2593f75e1098e280546187084655f35f540642fc081842cf484e43a1',
        'child_candidate_id': 'efe05edd6c93b58c24526313ea1ca0fc5e60970bb100ab18734fbab053264164',
        'hidden_sample_namespace': 'vip-t32-new-multiwhite-abc-v1', 'wall_clock_seconds_upper': 3600,
        'ordinary_and_highfan_and_competition_censoring_reported_separately': True,
        'business_calls': 0, 'new_authors': 0, 'new_independent_reviews': 0,
        'source_kind': 'manual_physical_condition_not_natural_prevalence', 'late_wall_coverage': False,
        'not_confirmation_or_release': True, 'no_future_draw_or_winner_filter': True,
        'builder_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    with (_project_file(_PROJECT_ROOT, HERE/'SOURCE-CONDITIONS.json')).open('x') as stream:
        json.dump(frame, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')
    print(json.dumps({'status': frame['status'], 'physical_roots': len(proposals), 'business_calls': 0}))


if __name__ == '__main__':
    main()
