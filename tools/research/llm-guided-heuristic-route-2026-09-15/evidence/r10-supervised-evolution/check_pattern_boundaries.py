"""检查作者前冻结的不变量；新增公式还需单独手算，不用候选输出定义答案。"""

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
import math
import strong_seed_batch as b
import pattern_option_batch as batch
import pattern_option_boundary_inputs as frozen
from hangma_bot.policy.action_value_seeds import ActionValueScorer


def main():
    """14个合成输入检查缺失退化、胡优先和未知底分；保存失败而非吞掉。"""
    sub = batch.OUT / batch.NAME
    state = b.search.av_state_load(b.search.av_latest_state_path(sub/'run'))
    source = b.Path(state['iter_dir'])/'generation/candidate.py'
    data = b.read(frozen.PATH)
    baseline = b.read(batch.OUT/'boundary-parent-baseline.json')
    assert baseline['input_sha256'] == b.digest(frozen.PATH.read_bytes())
    assert data['runner_sha256'] == b.digest(b.Path(frozen.__file__).read_bytes())
    scorer = ActionValueScorer('candidate-boundaries', source.read_text())
    rows = []
    for (name, sample, invariant), saved, before in zip(frozen.cases(), data['rows'], baseline['rows'], strict=True):
        assert name == saved['name'] == before['name']
        assert b.behavior.digest(sample.candidate_view()) == b.behavior.digest(saved['view'])
        got = scorer.score(sample)
        scores = {e.action_key:e.score for e in got.entries}
        order = sorted(scores,key=lambda key:(-scores[key],key))
        errors = []
        if got.status != ('ABSTAIN' if invariant == 'abstain' else 'SCORED'):
            errors.append('status')
        if any(not math.isfinite(v) for v in scores.values()):
            errors.append('finite_score')
        if got.status == 'SCORED' and set(scores) != {a.action_key for a in sample.actions}:
            errors.append('action_coverage')
        if invariant in ('per_action_parent_fallback','parent_identical') and scores != before['scores']:
            errors.append('parent_fallback')
        if invariant == 'hu_first' and order[:1] != ['hu']:
            errors.append('hu_priority')
        if invariant == 'known_floor_minus_1' and scores.get('pass') != min(v for k,v in scores.items() if k!='pass')-1:
            errors.append('unknown_floor')
        rows.append({'name':name,'invariant':invariant,'errors':errors,'status':got.status,
            'scores':scores,'order':order,'trace':{e.action_key:dict(e.trace) for e in got.entries}})
    report = {'status':'PASS' if all(not r['errors'] for r in rows) else 'FAIL', 'cases':len(rows),
        'rows':rows,'source_sha256':b.digest(source.read_bytes()), 'input_sha256':baseline['input_sha256'],
        'scope':'固定合成边界不变量；不替代独立算术、合法触发或强度评测', 'release_eligible':False}
    output=sub/'boundary-check.json'
    assert not output.exists()
    b.write(output,report)
    print(report['status'],[(r['name'],r['errors']) for r in rows if r['errors']],flush=True)
    assert report['status']=='PASS'


if __name__=='__main__':
    main()
