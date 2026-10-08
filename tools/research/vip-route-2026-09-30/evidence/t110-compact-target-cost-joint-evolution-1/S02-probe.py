"""验收本批实际API候选的103个公开窗口；不重复已核父评分或生成世界。"""

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
from dataclasses import asdict
from datetime import datetime, timezone
import argparse
import hashlib
import json
import math
from pathlib import Path
import time

from hangma_bot.hangma.engine import HangmaRules
from hangma_bot.kernel.observation import CompetitionContext
from hangma_bot.kernel.serialization import observation_from_json, window_key_from_json
from hangma_bot.offline.scoring_input_capture import ScoringInputCapture, ScoringInputCaptureLimits
from hangma_bot.offline.scoring_sources import REPO_ROOT
from hangma_bot.offline.vip_eoh_generate import VipEohBatch, load_vip_parents
from hangma_bot.policy.action_value_executor import ActionValueExecutor
from hangma_bot.policy.interface import DecisionRequest
from hangma_bot.policy.route_vip_heuristic import build_vip_route_scoring_view

HERE = Path(__file__).resolve().parent


def canonical(value):
    """有限JSON精确序列化，用于复用输入和绑定来源。"""
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False).encode()


def pin(path):
    """核验实际源码与输入字节；不解析私有配置。"""
    raw = Path(path).read_bytes()
    return {'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)}


def save(path, value):
    """收据只创建；失败分母和费用原样留存。"""
    with path.open('xb') as stream:
        stream.write(canonical(value) + b'\n')


def main(slot):
    """机械合法性是硬门；已曝光案例首选只作行为反馈，不指定正确答案。"""
    prep = json.loads((_project_file(_PROJECT_ROOT, HERE / 'S02-AUTHOR-PREPARATION-CLOSED.json')).read_text())
    assert all(pin(n) == h for n, h in prep['frozen_files'].items())
    batch = VipEohBatch.read(_project_file(_PROJECT_ROOT, HERE / 'AUTHOR-BATCH.json'))
    package = _project_file(_PROJECT_ROOT, HERE / (slot + '-model-output'))
    generation = json.loads((package / 'generation.json').read_text())
    assert generation['status'] == 'loaded_not_admitted' and generation['identity_stable']
    candidate = load_vip_parents([package], batch)[0]
    parent = json.loads((_project_file(_PROJECT_ROOT, HERE / 'PARENT-IDENTITY.json')).read_text())['formal_parent']
    assert candidate['identity'] != parent
    cases = json.loads((_project_file(_PROJECT_ROOT, HERE / 'PUBLIC-PANEL.json')).read_text())['cases']
    assert len(cases) == 103
    out = _project_file(_PROJECT_ROOT, HERE / (slot + '-public-probe'))
    out.mkdir(exist_ok=False)
    frozen = {str(p): pin(p) for p in [Path(__file__), _project_file(_PROJECT_ROOT, HERE / 'PUBLIC-PANEL.json'),
              _project_file(_PROJECT_ROOT, HERE / 'AUTHOR-BATCH.json'), package / 'generation.json', package / 'candidate.py']}
    manifest = candidate['identity']['source_manifest']
    assert all(pin(_project_file(_PROJECT_ROOT, REPO_ROOT / n)) == h for n, h in manifest.items())
    save(out / 'START.json', {'schema': 't110-real-child-public-probe/1',
         'slot': slot, 'candidate_identity': candidate['identity'], 'formal_parent': parent,
         'frozen_files': frozen, 'source_manifest': manifest, 'max_actual_child_scores': 103,
         'actual_parent_scores': 0, 'parent_reference': 'verified actual T101 exact full input',
         'case_action_gold_labels': False, 'created_at_utc': datetime.now(timezone.utc).isoformat(),
         'worlds_models_tables': 0, 'wall_seconds': 1200, 'normal_R18_fallback_allowed': False})
    executor = ActionValueExecutor(candidate['source'], max_operations=batch.max_operations,
                                  max_local_collection_size=batch.projection_limits.max_nodes)
    rows, cache, failure, cleanup = [], {}, None, []
    counts = {'rules_analyze_attempts': 0, 'view_build_attempts': 0, 'actual_child_score_calls': 0}
    begun, costs = time.monotonic(), None
    raw = (out / 'VIEWS.jsonl.gz').open('x+b')
    capture = ScoringInputCapture(raw, limits=ScoringInputCaptureLimits(67108864, 2147483648, 128))
    output = (out / 'ROWS.jsonl').open('x')
    try:
        for case in cases:
            row = {'label': case['label'], 'status': 'not_started', 'parent_first': case['parent_first']}
            if failure is None:
                try:
                    assert time.monotonic() - begun < 1200
                    obs, key = observation_from_json(case['observation']), window_key_from_json(case['window_key'])
                    counts['rules_analyze_attempts'] += 1
                    analysis = HangmaRules(batch.rule_config).analyze(obs, route_limits=batch.route_limits)
                    assert analysis.completeness.value == 'complete'
                    request = DecisionRequest(obs, CompetitionContext('T101-public-probe', None, None, None, None, (), 0),
                                              analysis, case['label'], key.trigger_seq, key, ())
                    counts['view_build_attempts'] += 1
                    view = build_vip_route_scoring_view(request, batch.rule_config, limits=batch.projection_limits)
                    dto = view.candidate_view()
                    digest = hashlib.sha256(canonical(dto)).hexdigest()
                    row['view_sha256'] = digest
                    assert digest == case['view_sha256'], '完整输入与真实父记录不同'
                    legal = {a.action_key for a in view.actions}
                    assert legal == {e['action_key'] for e in case['parent_scores']}
                    if digest not in cache:
                        receipt = capture.store(dto)
                        assert receipt.saved_before_score and receipt.error is None
                        counts['actual_child_score_calls'] += 1
                        scored = executor.score_vip_route(view)
                        entries = [{'action_key': e.action_key, 'score': e.score, 'trace': e.trace} for e in scored.entries]
                        assert scored.status == 'SCORED' and len(entries) == len(legal)
                        assert {e['action_key'] for e in entries} == legal
                        assert all(type(e['score']) in (int, float) and math.isfinite(e['score']) for e in entries)
                        cache[digest] = {'entries': entries, 'operations': executor.last_operation_count,
                             'capture_receipt': asdict(receipt), 'actual_score_origin': case['label']}
                    assert hashlib.sha256(canonical(view.candidate_view())).hexdigest() == digest
                    first = sorted(cache[digest]['entries'], key=lambda e: (-e['score'], e['action_key']))[0]['action_key']
                    row.update(status='complete', child_first=first, child_scores=cache[digest],
                         child_score_reused=cache[digest]['actual_score_origin'] != case['label'],
                         behavior_changed=first != case['parent_first'], parent_scores=case['parent_scores'])
                except BaseException as exc:
                    failure = {'type': type(exc).__name__, 'reason': str(exc), 'label': case['label']}
                    row.update(status='failed', error=failure)
            rows.append(row)
            output.write(canonical(row).decode() + '\n'); output.flush()
            print({k: row.get(k) for k in ('label', 'status', 'parent_first', 'child_first', 'behavior_changed')}, flush=True)
    finally:
        output.close()
        try:
            costs = capture.finish()
        except BaseException as exc:
            cleanup.append(type(exc).__name__ + ': ' + str(exc))
        finally:
            raw.close()
        stable = (all(pin(n) == h for n, h in frozen.items())
                  and all(pin(n) == h for n, h in prep['frozen_files'].items())
                  and all(pin(_project_file(_PROJECT_ROOT, REPO_ROOT / n)) == h for n, h in manifest.items())
                  and batch.identity(candidate['source']) == candidate['identity'])
        complete = (failure is None and not cleanup and stable and len(rows) == 103
                    and all(r['status'] == 'complete' for r in rows)
                    and costs is not None and costs['terminal']['terminal_valid'])
        save(out / 'CLOSURE.json', {'complete': complete, 'source_stable': stable, 'counts': counts,
             'candidate_identity': candidate['identity'], 'rows': rows, 'primary_failure': failure,
             'cleanup_errors': cleanup, 'unique_scored_views': len(cache), 'input_capture': costs,
             'actual_parent_score_calls': 0, 'actual_new_models_worlds_tables': 0,
             'normal_R18_fallbacks': 0, 'elapsed_monotonic_seconds': time.monotonic() - begun,
             'scope': 'development mechanical and behavior evidence; no optimality/strength/deadline/admission'})
        if not complete:
            raise SystemExit(1)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--slot', choices=('S01', 'S02'), required=True)
    main(parser.parse_args().slot)
