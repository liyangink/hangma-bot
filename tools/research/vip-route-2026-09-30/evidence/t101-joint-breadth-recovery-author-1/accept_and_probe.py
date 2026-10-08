"""签收第二作者原答，用既定公开输入验实际评分；不重跑父评分或世界。

61旧控制和32新开发分歧共93窗口。相同完整DTO的新候选评分仅执行一次，
各窗口明确记录复用；父分值仅来自已验证的真实旧记录，不伪装新调用。
"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t101-joint-breadth-recovery-author-1'

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
import gzip
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import time

from hangma_bot.hangma.engine import HangmaRules
from hangma_bot.kernel.observation import CompetitionContext
from hangma_bot.kernel.serialization import observation_from_json, window_key_from_json
from hangma_bot.offline.scoring_input_capture import ScoringInputCapture, ScoringInputCaptureLimits
from hangma_bot.offline.scoring_sources import REPO_ROOT
from hangma_bot.offline.vip_eoh_generate import (
    VipEohBatch, build_vip_eoh_prompt, load_vip_parents, parse_vip_eoh_reply, run_vip_eoh_generate,
)
from hangma_bot.policy.action_value_executor import ActionValueExecutor
from hangma_bot.policy.interface import DecisionRequest
from hangma_bot.policy.route_vip_heuristic import build_vip_route_scoring_view

HERE = Path(__file__).resolve().parent
OLD = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t97-natural-preparation-joint-root-1')
DIAGNOSTIC = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t100-joint-pilot-divergence-1')


def canonical(value):
    """规范有限JSON；排序分不当积分，解释与版本不删除。"""
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False).encode()


def pin(path):
    """冻结字节及大小；原答和父身份都必须首尾稳定。"""
    raw = Path(path).read_bytes()
    return {'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)}


def save(name, value):
    """只创建新收据，失败及半批不得覆盖。"""
    with (_project_file(_PROJECT_ROOT, HERE / name)).open('xb') as f:
        f.write(canonical(value) + b'\n')


def cases():
    """复用已核公开控制读取器，保留全部32跨源分歧，未选赢家子集。"""
    spec = importlib.util.spec_from_file_location('t97_public_cases_reader', _project_file(_PROJECT_ROOT, OLD / 'accept_and_probe.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    old, inputs = module.public_cases()
    closure = json.loads((_project_file(_PROJECT_ROOT, OLD / 'PUBLIC-PROBE-COMBINED-CLOSURE.json')).read_text())
    assert closure['complete'] and closure['source_stable']
    by_label = {r['label']: r for r in closure['rows']}
    result = []
    for row in old:
        actual = by_label[row['label']]
        assert actual['status'] == 'complete'
        result.append({'label': row['label'], 'observation': row['observation'],
                       'window_key': row['window_key'], 'view_sha256': actual['view_sha256'],
                       'parent_scores': actual['scores']['candidate']['entries'],
                       'parent_first': actual['scores']['candidate']['first'],
                       'scope': row['scope']})
    with gzip.open(_project_file(_PROJECT_ROOT, DIAGNOSTIC / 'PUBLIC-FIRST-DIVERGENCES.json.gz'), 'rt') as f:
        fresh = json.load(f)['rows']
    pairs = {r['label']: r for r in json.loads((_project_file(_PROJECT_ROOT, DIAGNOSTIC / 'PAIR-READBACK.json')).read_text())['pairs']}
    for row in fresh:
        observation = dict(row['public_observation'], game_id=pairs[row['label']]['new_match_id'])
        window = dict(row['window'], game_id=observation['game_id'])
        result.append({'label': 'T100:' + row['label'], 'observation': observation,
                       'window_key': window, 'view_sha256': row['complete_view_sha256'],
                       'parent_scores': row['T97_actual_scores'], 'parent_first': row['T97_action'],
                       'scope': 'known new-pilot development first divergence, not independent confirmation'})
    assert len(result) == 93 and len({r['label'] for r in result}) == 93
    return result, [_project_file(_PROJECT_ROOT, OLD / 'accept_and_probe.py'), *inputs, _project_file(_PROJECT_ROOT, OLD / 'PUBLIC-PROBE-COMBINED-CLOSURE.json'),
                     _project_file(_PROJECT_ROOT, DIAGNOSTIC / 'PUBLIC-FIRST-DIVERGENCES.json.gz'), _project_file(_PROJECT_ROOT, DIAGNOSTIC / 'PAIR-READBACK.json')]


def main():
    """模型交付首封、真实m1装载、93窗口完整合法评分；工程故障即止新评分。"""
    prep = json.loads((_project_file(_PROJECT_ROOT, HERE / 'AUTHOR-PREPARATION-CLOSED.json')).read_text())
    assert all(pin(n) == h for n, h in prep['frozen_files'].items())
    delivered = {n: pin(_project_file(_PROJECT_ROOT, HERE / n)) for n in ('RAW-REPLY.txt', 'candidate.py', 'STATIC-CHECKS.json', 'AUTHOR-NOTE.md')}
    save('ROOT-AUTHOR-REPLY-FIRST-SEAL.json', {'schema': 't101-real-second-author-first-seal/1',
        'files': delivered, 'operator': 'm1', 'formal_parents': prep['formal_parents'],
        'requested_model': 'gpt-6.1-sol', 'requested_effort': 'max',
        'actual_author_delegations': 1, 'underlying_api_calls_and_tokens': None,
        'created_at_utc': datetime.now(timezone.utc).isoformat(), 'admitted': False})
    batch_file = _project_file(_PROJECT_ROOT, HERE / 'S02-generation.batch.json')
    batch = VipEohBatch.read(batch_file)
    parent_path = _project_file(_PROJECT_ROOT, OLD / 'S01-model-output')
    parent = load_vip_parents([parent_path], batch)[0]
    parsed = parse_vip_eoh_reply((_project_file(_PROJECT_ROOT, HERE / 'RAW-REPLY.txt')).read_text(), 'm1', [parent])
    assert parsed['source_raw'].encode() == (_project_file(_PROJECT_ROOT, HERE / 'candidate.py')).read_bytes()
    ActionValueExecutor(parsed['source'], max_operations=batch.max_operations,
                        max_local_collection_size=batch.projection_limits.max_nodes)
    feedback = (_project_file(_PROJECT_ROOT, HERE / 'FROZEN-FEEDBACK.txt')).read_text()
    packet, _ = build_vip_eoh_prompt(batch, 'm1', [parent], feedback)
    assert packet.sha256 == prep['prompt_sha256'] == pin(_project_file(_PROJECT_ROOT, HERE / 'S02-prompt-emission/prompt.txt'))['sha256']
    save('REPLAY-ENVELOPE.json', {'schema': 'sitin-generation-reply/1',
        'captured_at_utc': datetime.now(timezone.utc).isoformat(), 'origin': 'delegated_model_reply',
        'provider': 'codex-collaboration', 'model': 'unknown', 'finish_reason': 'stop',
        'prompt_sha256': packet.sha256, 'reply': (_project_file(_PROJECT_ROOT, HERE / 'RAW-REPLY.txt')).read_text(),
        'delegator': '/root via /root/t101_sol_max_joint_breadth_author',
        'note': 'actual second delegation; replay is zero new model calls; underlying usage unknown'})
    generated = run_vip_eoh_generate(batch_file=batch_file, out_dir=_project_file(_PROJECT_ROOT, HERE / 'S02-model-output'),
        operator='m1', parent_paths=(parent_path,), backend='replay', feedback=feedback,
        reply_file=_project_file(_PROJECT_ROOT, HERE / 'REPLAY-ENVELOPE.json'))
    assert generated['status'] == 'loaded_not_admitted', generated.get('error')
    candidate = load_vip_parents([_project_file(_PROJECT_ROOT, HERE / 'S02-model-output')], batch)[0]
    panel, inputs = cases()
    frozen = {str(p): pin(p) for p in [Path(__file__), *inputs, batch_file,
              _project_file(_PROJECT_ROOT, HERE / 'S02-model-output/generation.json'), _project_file(_PROJECT_ROOT, HERE / 'S02-model-output/candidate.py')]}
    source_manifest = generated['framework']['generation_source_manifest']
    save('PUBLIC-PROBE-START.json', {'requested_windows': 93, 'maximum_actual_child_scores': 93,
        'parent_scores': 'cached verified actual T97 on exact full input; not repeated',
        'same_child_input_reuse': 'full DTO SHA equality only; actual calls reported separately',
        'frozen_files': frozen, 'source_manifest': source_manifest,
        'candidate_identity': candidate['identity'], 'scope': 'development only, no world or admission'})
    executor = ActionValueExecutor(candidate['source'], max_operations=batch.max_operations,
                                    max_local_collection_size=batch.projection_limits.max_nodes)
    rows, cache, counts = [], {}, {'rule_attempts': 0, 'view_attempts': 0, 'actual_child_score_calls': 0}
    begun, failure, cleanup, costs = time.monotonic(), None, [], None
    raw = (_project_file(_PROJECT_ROOT, HERE / 'PUBLIC-PROBE-VIEWS.jsonl.gz')).open('x+b')
    capture = ScoringInputCapture(raw, limits=ScoringInputCaptureLimits(67108864, 2147483648, 128))
    output = (_project_file(_PROJECT_ROOT, HERE / 'PUBLIC-PROBE-ROWS.jsonl')).open('x')
    try:
        for case in panel:
            row = {'label': case['label'], 'status': 'not_started', 'parent_first': case['parent_first']}
            if failure is None:
                try:
                    assert time.monotonic() - begun < 1200
                    obs, key = observation_from_json(case['observation']), window_key_from_json(case['window_key'])
                    counts['rule_attempts'] += 1
                    analysis = HangmaRules(batch.rule_config).analyze(obs, route_limits=batch.route_limits)
                    assert analysis.completeness.value == 'complete'
                    request = DecisionRequest(obs, CompetitionContext('T101-public-probe', None, None, None, None, (), 0),
                                                analysis, case['label'], key.trigger_seq, key, ())
                    counts['view_attempts'] += 1
                    view = build_vip_route_scoring_view(request, batch.rule_config, limits=batch.projection_limits)
                    dto = view.candidate_view()
                    digest = hashlib.sha256(canonical(dto)).hexdigest()
                    row['view_sha256'] = digest
                    assert digest == case['view_sha256'], 'full public input changed'
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
                    row['child_score_reused'] = cache[digest]['actual_score_origin'] != case['label']
                    assert hashlib.sha256(canonical(view.candidate_view())).hexdigest() == digest
                    row['child_scores'] = cache[digest]
                    first = sorted(cache[digest]['entries'], key=lambda e: (-e['score'], e['action_key']))[0]['action_key']
                    row.update(status='complete', child_first=first,
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
                  and all(pin(_project_file(_PROJECT_ROOT, HERE / n)) == h for n, h in delivered.items())
                  and all(pin(_project_file(_PROJECT_ROOT, REPO_ROOT / n)) == h for n, h in source_manifest.items())
                  and batch.identity(candidate['source']) == candidate['identity'])
        complete = (failure is None and not cleanup and stable and len(rows) == 93
                    and all(r['status'] == 'complete' for r in rows)
                    and costs is not None and costs['terminal']['terminal_valid'])
        save('PUBLIC-PROBE-CLOSURE.json', {'complete': complete, 'source_stable': stable, 'rows': rows,
            'counts': counts, 'unique_scored_views': len(cache), 'input_capture': costs,
            'primary_failure': failure, 'cleanup_errors': cleanup,
            'parent_score_calls': 0, 'new_models_worlds_tables': 0,
            'candidate_identity': candidate['identity'], 'elapsed_monotonic_seconds': time.monotonic()-begun,
            'scope': 'development behavior; no single-action causality, strength or admission'})
        if not complete:
            raise SystemExit(1)


if __name__ == '__main__':
    main()
