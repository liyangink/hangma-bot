"""G58 A 原答 JSON 前缀中抽出的纯函数；原答严格合同失败，仅供离线研究。"""

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

def choose(ctx, options):
    if ctx is None or options is None:
        return None
    if len(options) < 2:
        return None
    white_count = ctx['white_count']
    own_melds = ctx['own_melds']
    wall_remaining = ctx['wall_remaining']
    dealer = ctx['dealer']
    table_rank = ctx['table_rank']
    opponent_melds = ctx['opponent_melds']
    drawn_tile = ctx['drawn_tile']
    if white_count is None or own_melds is None or wall_remaining is None:
        return None
    if dealer is None or table_rank is None or drawn_tile is None:
        return None
    if white_count is True or white_count is False:
        return None
    if own_melds is True or own_melds is False:
        return None
    if wall_remaining is True or wall_remaining is False:
        return None
    if table_rank is True or table_rank is False:
        return None
    if dealer is not True and dealer is not False:
        return None
    if opponent_melds is None or len(opponent_melds) != 3:
        return None
    m0 = opponent_melds[0]
    m1 = opponent_melds[1]
    m2 = opponent_melds[2]
    if m0 is None or m0 is True or m0 is False:
        return None
    if m1 is None or m1 is True or m1 is False:
        return None
    if m2 is None or m2 is True or m2 is False:
        return None
    if (m0 + m1 + m2) != 0:
        return None
    if wall_remaining < 40:
        return None
    if own_melds >= 2:
        return None
    if dealer is False and table_rank < 3:
        return None
    parent = None
    for o in options:
        if o['is_parent'] is True:
            parent = o
    if parent is None:
        return None
    p_key = parent['key']
    if len(p_key) < 8 or p_key[:8] != 'discard:':
        return None
    p_c = parent['combined']
    if p_c is None or p_c is True or p_c is False:
        return None
    p_score = parent['score']
    if p_score is None or p_score is True or p_score is False:
        return None
    p_ordinary = parent['ordinary']
    if p_ordinary is True or p_ordinary is False:
        return None
    p_seven = parent['seven']
    if p_seven is True or p_seven is False:
        return None
    p_white = parent['white_after']
    if p_white is None or p_white is True or p_white is False:
        return None
    p_bao = parent['baotou_after']
    p_sup = parent['support']
    if p_sup is None:
        return None
    cap_p = 0
    for e in p_sup:
        r = e['remaining']
        if r is None or r is True or r is False:
            return None
        cap_p = cap_p + r
    best_key = None
    best_cap = -1
    best_white = -1
    best_score = 0.0
    for o in options:
        if o['is_parent'] is True:
            continue
        c = o['combined']
        if c is None or c is True or c is False or c != p_c:
            continue
        sc = o['score']
        if sc is None or sc is True or sc is False:
            continue
        sup = o['support']
        if sup is None:
            continue
        cap = 0
        bad = False
        for e in sup:
            r = e['remaining']
            if r is None or r is True or r is False:
                bad = True
                break
            cap = cap + r
        if bad:
            continue
        w_a = o['white_after']
        if w_a is None or w_a is True or w_a is False:
            continue
        if w_a < p_white:
            continue
        bao = o['baotou_after']
        if p_bao is True and bao is not True:
            continue
        ordn = o['ordinary']
        if ordn is not None and (ordn is True or ordn is False):
            continue
        if p_ordinary is not None and ordn is None:
            continue
        if ordn is not None and p_ordinary is not None and ordn > p_ordinary:
            continue
        sevn = o['seven']
        if sevn is not None and (sevn is True or sevn is False):
            continue
        if p_seven is not None and sevn is None:
            continue
        if sevn is not None and p_seven is not None and sevn > p_seven:
            continue
        k = o['key']
        if len(k) < 8 or k[:8] != 'discard:':
            continue
        replace = False
        if cap > best_cap:
            replace = True
        elif cap == best_cap and w_a > best_white:
            replace = True
        elif cap == best_cap and w_a == best_white and sc > best_score:
            replace = True
        if replace:
            best_key = k
            best_cap = cap
            best_white = w_a
            best_score = sc
    if best_key is None:
        return None
    margin = best_cap - cap_p
    if margin < 2:
        return None
    score_margin = p_score - best_score
    if score_margin < 0:
        score_margin = 0.0
    if score_margin > 2.0 * margin:
        return None
    return best_key
