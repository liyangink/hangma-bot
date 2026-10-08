"""核对真实分支字段与财神守恒；只用可见请求，不推进或改写规则。"""

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
import dataclasses
from collections import Counter

import strong_seed_batch as b
from hangma_bot.hangma.interface import FollowupBranchFacts
from hangma_bot.kernel.actions import Chi, Peng
from hangma_bot.policy.action_value_policy import build_scoring_view


def audit():
    """枚举冻结开发窗，核验吃碰耗牌不含财神，逐合法弃牌计算手留变化。"""
    panel = b.HERE / 'batch03-known-root-diagnostic/panel.json'
    panel_digest, windows = b.behavior.load_panel(panel)
    keys = Counter()
    rows = []
    for window_id, request in windows:
        view = build_scoring_view(request)
        projected = {a['action_key']: a for a in view.candidate_view()['actions']}
        for action in view.actions:
            if not isinstance(action.action, (Chi, Peng)):
                continue
            observation = request.observation
            # 合法响应没有本人摸牌；避免把两种摸牌编码差异混入守恒探针。
            assert observation.drawn_tile is None
            hand = [tile.code for tile in observation.my_hand]
            claim = action.action
            consumed = ([tile.code for tile in claim.tiles] if isinstance(claim, Chi)
                        else [claim.tile.code] * 3)
            assert '白' not in consumed
            # 被吃/碰的牌来自他家，只删除另两张本人手牌。
            claimed = observation.last_discard.tile.code
            consumed.remove(claimed)
            after_call = hand.copy()
            for tile in consumed:
                after_call.remove(tile)
            assert after_call.count('白') == hand.count('白')
            for branch in projected[action.action_key].get('followup_branches') or ():
                keys.update(branch.keys())
                discarded = branch['followup_discard']
                after_discard = after_call.copy()
                after_discard.remove(discarded)
                delta = after_discard.count('白') - hand.count('白')
                assert delta == (-1 if discarded == '白' else 0)
                rows.append({'window': window_id, 'action': action.action_key,
                             'followup_discard': discarded, 'wealth_delta': delta})
    assert all(type(value) is int and 0 < value <= len(rows) for value in keys.values())
    paths = [b.ROUTE.parents[1] / name for name in (
        'src/hangma_bot/hangma/interface.py',
        'src/hangma_bot/hangma/candidate_facts.py',
        'src/hangma_bot/policy/action_value.py',
        'src/hangma_bot/hangma/action_families.py',
        'doc/references/official-guide-v34-content.txt')]
    return {'scope': '生产字段核查与可见手牌计数；不是强度、完整规则或官方赛事验证',
            'panel_digest': panel_digest,
            'runner_sha256': b.digest(b.Path(__file__).read_bytes()),
            'execution_deps_digest': b.search.av_gates().av_deps_digest(),
            'source_files': {str(p): b.digest(p.read_bytes()) for p in paths},
            'producer_fields': [f.name for f in dataclasses.fields(FollowupBranchFacts)],
            'observed_key_counts': dict(keys),
            'unproduced_optional_aliases': ['hand_codes', 'progress', 'route_state'],
            'branches': len(rows),
            'wealth_discard_branches': sum(r['wealth_delta'] == -1 for r in rows),
            'rows': rows, 'release_eligible': False}


if __name__ == '__main__':
    output = b.HERE / 'branch-refinement-20260920/production-capability-audit.json'
    if output.exists():
        raise SystemExit('保留已有证据，不覆盖')
    result = audit()
    b.write(output, result)
    print({key: result[key] for key in ('branches', 'wealth_discard_branches',
                                       'observed_key_counts')})
