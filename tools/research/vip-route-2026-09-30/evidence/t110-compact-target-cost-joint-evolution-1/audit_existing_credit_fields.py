"""纯读旧开发DTO及冻结源码，核已有爆头字段和候选显式消费范围。

不调用生产规则、候选评分、世界、续打或模型，不读取T112确认结果。
字面字段缺席只证明没有显式读取，不能证明支付里不含爆头贡献。
"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t110-compact-target-cost-joint-evolution-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
import ast
from collections import Counter
import gzip
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCE = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t110-compact-target-cost-joint-evolution-1/S02-model-output/candidate.py')
VIEWS = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t110-compact-target-cost-joint-evolution-1/S01-PUBLIC-FIRST-CASE-VIEWS.jsonl.gz')
CASES = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t110-compact-target-cost-joint-evolution-1/S01-PUBLIC-FIRST-CASES.json')


def sha(path):
    """摘要绑定本次只读输入，不修改或重建原件。"""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    """核九份已有完整输入和显式字段名，输出带适用边界的静态诊断。"""
    generation = json.loads((_project_file(_PROJECT_ROOT, SOURCE.parent / 'generation.json')).read_text())
    assert sha(SOURCE) == generation['identity']['source_sha256']
    tree = ast.parse(SOURCE.read_text())
    literals = Counter(n.value for n in ast.walk(tree)
        if isinstance(n, ast.Constant) and isinstance(n.value, str))
    cases = json.loads(CASES.read_text())['cases']
    expected = {c['arms']['P']['view_sha256'] for c in cases}
    by_digest = {}
    waits = baotou_true = 0
    values = Counter()
    with gzip.open(VIEWS, 'rt') as stream:
        for line in stream:
            row = json.loads(line)
            digest = row['view_sha256']
            raw = json.dumps(row['view'], ensure_ascii=False, sort_keys=True,
                separators=(',', ':'), allow_nan=False).encode()
            assert hashlib.sha256(raw).hexdigest() == digest
            assert len(raw) == row['json_bytes'] and digest not in by_digest
            by_digest[digest] = row['view']
            for node in row['view']['nodes']:
                waiting = node['waiting']
                if waiting is None:
                    continue
                waits += 1
                assert type(waiting['baotou']) is bool
                assert type(waiting['chain_count']) is int
                baotou_true += int(waiting['baotou'])
                values[waiting['chain_count']] += 1
                for payment in waiting['normal_draw_hu_payments'] or ():
                    assert type(payment['baotou_after_draw']) is bool
    assert set(by_digest) == expected and len(by_digest) == 9
    fields = ('baotou', 'chain_count', 'baotou_after_draw',
              'normal_draw_hu_payments', 'score_delta', 'retained_whites')
    result = {
        'scope': 'nine previously exposed S01 first-case DTOs and unchanged S02 source only',
        'input_sha256': {str(p): sha(p) for p in (SOURCE, VIEWS, CASES)},
        'candidate_id': generation['identity']['candidate_id'],
        'full_DTOs': 9, 'waiting_nodes': waits, 'baotou_true_nodes': baotou_true,
        'chain_count_node_distribution': dict(values),
        'source_string_literal_occurrences': {f: literals[f] for f in fields},
        'finding': 'existing condition baotou and chain_count facts are already serialized; S02 has no explicit literal read of these lifecycle fields',
        'important_limit': 'S02 consumes authoritative score_delta, so earned baotou/chain score can be reflected implicitly; unused flags do not prove double credit, a wrong wait, or a rule bug',
        'next_action_if_needed': 'first test formulas using existing lifecycle facts; expand only a separately evidenced additional-white action chain, not current-state fields',
        'current_confirmation_outcomes_read': False, 'formula_or_runtime_changed': False,
        'new_rules_scores_models_worlds_tables': 0, 'admitted': False, 'published': False,
    }
    with (_project_file(_PROJECT_ROOT, HERE / 'S02-EXISTING-CREDIT-FIELD-AUDIT.json')).open('x') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')
    print({k: result[k] for k in ('full_DTOs', 'waiting_nodes', 'baotou_true_nodes',
        'source_string_literal_occurrences', 'new_rules_scores_models_worlds_tables')}, flush=True)


if __name__ == '__main__':
    main()
