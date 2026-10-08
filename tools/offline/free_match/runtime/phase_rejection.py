"""为已合法且及时发送的吃／碰／唯一过牌相位冲突取证；原NoRefresh不改写。"""
from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t199-four-step-execution-1/runtime'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

import hashlib
import json
import math
import re
import time


def window(value):
    """原窗口五元键；schema包装不参与等价比较。"""
    if not isinstance(value, dict): return None
    return tuple(value.get(key) for key in ('game_id', 'round_no', 'trigger_seq', 'phase', 'seat'))


def key(context):
    return tuple(context.get(name) for name in ('game_id', 'decision_id', 'attempt_no'))


def rejection_family(payload):
    """只识别三条已核实官方原文；动作、合法集及时序还须完整证明。"""
    try:
        body = json.loads(payload['raw']); error = body.get('error')
        code = body.get('code') or (error.get('code') if isinstance(error, dict) else None)
        message = body.get('message') or (error.get('message') if isinstance(error, dict) else None)
        if payload.get('http_status') != 409 or code != 'INVALID_ACTION': return None
        if message == 'peng only in peng window': return 'peng'
        if message == 'cannot pass in phase 1': return 'only_pass'
        if message == 'chi only in chi window': return 'chi'
    except (KeyError, TypeError, ValueError): pass
    return None


def exact_message(payload):
    """候选证据入口，不表示已经豁免；NOT_QUALIFIED及其它原文保持硬门。"""
    return rejection_family(payload) is not None


def compact(row):
    """只保留原规则合法键/验证/预算/意图/拒绝；不重算牌型或评分。"""
    kind, payload = row.get('kind'), row.get('payload', {})
    if kind == 'decision_input':
        req = payload.get('request', {}); rules = req.get('rules', {}); obs = req.get('observation', {})
        payload = {'window': req.get('window_key'), 'rule_completeness': rules.get('completeness'),
            'legal_keys': [item.get('action_key') for item in rules.get('legal_candidates', [])],
            'budget': payload.get('budget'), 'snapshot_seq': obs.get('snapshot_seq'), 'consumed_seq': obs.get('consumed_seq'),
            'rejected_attempts': req.get('rejected_attempts')}
    elif kind not in ('candidate_validated', 'submission_intent', 'submission_outcome', 'decision_ended'): return None
    return {'kind': kind, 'context': row.get('context', {}), 'payload': payload, 'monotonic_ns': row.get('monotonic_ns')}


def collect(run, decisions, *, max_bytes, max_seconds, max_record_bytes=8388608, recovery_windows=()):
    """仅精确相位拒绝才扫描decisions；有界保留SHA、全窗意图数及适配器尝试关联。"""
    if not decisions: return {}, {'bytes': 0, 'seconds': 0., 'complete': True, 'triggered': False}, {}, {}
    started = time.monotonic(); size = 0; result = {did: [] for did in decisions}; needles = [did.encode() for did in decisions]
    adapter_counts, adapter_attempts = {}, {}
    recovery_contexts = {item[:3] for item in recovery_windows}
    paths = sorted(run.glob('participants/*/decisions.jsonl'))
    complete = bool(paths); unknown = None
    for path in paths:
        with path.open('rb') as stream:
            for line_no, line in enumerate(stream, 1):
                size += len(line)
                if size > max_bytes or time.monotonic() - started > max_seconds:
                    complete = False; unknown = 'compact_index_limit'; break
                prefix = line[:2048]
                kind_match = re.search(br'"kind"\s*:\s*"([^"]+)"', prefix)
                context_match = re.search(br'"context"\s*:\s*(\{[^{}]*\})', prefix)
                # 仅支持已冻结录制器的完整前缀；位置变更或截断必须未知，不能漏计另DID的意图。
                if kind_match is None or context_match is None:
                    complete = False; unknown = 'compact_prefix_contract_missing'; break
                header_context = json.loads(context_match.group(1))
                target = header_context.get('decision_id') in result
                if (kind_match.group(1) == b'decision_input' and
                        (header_context.get('game_id'), header_context.get('round_no'),
                         header_context.get('trigger_seq')) in recovery_contexts):
                    next_did = header_context.get('decision_id')
                    if not isinstance(next_did, str) or not next_did:
                        complete = False; unknown = 'compact_recovery_identity_missing'; break
                    result.setdefault(next_did, [])
                    target = True
                # 不限decision_id核所有adapter body意图；另DID的失败/模糊POST不能因无raw响应漏掉。
                adapter_intent = kind_match.group(1) == b'submission_intent'
                if not target and not adapter_intent: continue
                if len(line) > max_record_bytes:
                    complete = False; unknown = 'compact_target_record_limit'; break
                row = json.loads(line); did = row.get('context', {}).get('decision_id')
                payload = row.get('payload', {})
                if row.get('kind') == 'submission_intent' and 'body' in payload:
                    original_window = window(payload.get('window'))
                    if original_window is None or any(value is None for value in original_window):
                        complete = False; unknown = 'adapter_intent_window_missing'; break
                    adapter_counts[original_window] = adapter_counts.get(original_window, 0) + 1
                    # 全部DID的body意图都保留；没有响应的失败/模糊POST也不能从同窗重复保护中消失。
                    wire_context = row.get('context', {})
                    gid, did, attempt = key(wire_context)
                    if (not isinstance(gid, str) or not gid or not isinstance(did, str) or not did
                            or type(attempt) is not int or attempt < 1):
                        complete = False; unknown = 'adapter_intent_identity_missing_or_invalid'; break
                    adapter_attempts.setdefault((gid, did, attempt), []).append({
                        'context': wire_context, 'payload': payload,
                        'monotonic_ns': row.get('monotonic_ns')})
                elif row.get('kind') == 'submission_intent' and 'latest_send_at_monotonic' not in payload:
                    complete = False; unknown = 'adapter_intent_body_missing'; break
                if did not in result: continue
                selected = compact(row)
                if selected is not None:
                    selected.update(source=str(path), line=line_no, original_line_sha256=hashlib.sha256(line).hexdigest())
                    result[did].append(selected)
        if not complete: break
    return result, {'bytes': size, 'seconds': time.monotonic() - started, 'complete': complete,
        'triggered': True, 'unknown': unknown, 'max_bytes': max_bytes, 'max_seconds': max_seconds,
        'max_target_record_bytes': max_record_bytes, 'target_decisions': len(decisions)}, adapter_counts, adapter_attempts


def associate_posts(posts, adapter_attempts):
    """按可信body意图把原HTTP响应关联五元窗口，再跨DID计数；缺项或冲突不做豁免。"""
    counts = {}
    info = {'complete': True, 'unknown': None, 'raw_post_records': len(posts), 'mapped_post_records': 0}

    def fail(reason):
        info.update(complete=False, unknown=reason)
        return counts, info

    for row in posts:
        context, payload = row.get('context', {}), row.get('payload', {})
        if not isinstance(context, dict) or not isinstance(payload, dict):
            return fail('phase_post_identity_missing_or_conflicting')
        gid, did, attempt = key(context)
        if (not isinstance(gid, str) or not gid or not isinstance(did, str) or not did
                or type(attempt) is not int or attempt < 1
                or payload.get('decision_id') != did or type(payload.get('attempt_no')) is not int
                or payload['attempt_no'] != attempt):
            return fail('phase_post_identity_missing_or_conflicting')
        matches = adapter_attempts.get((gid, did, attempt), [])
        if len(matches) != 1:
            return fail('phase_post_adapter_mapping_missing' if not matches else 'phase_post_adapter_mapping_conflicting')
        wire = matches[0]; sent = wire['payload']; wire_context = wire['context']
        original_window = window(sent.get('window'))
        if (original_window is None or not isinstance(original_window[0], str) or not original_window[0]
                or type(original_window[1]) is not int or original_window[1] < 1
                or type(original_window[2]) is not int or original_window[2] < 0
                or not isinstance(original_window[3], str) or not original_window[3]
                or type(original_window[4]) is not int or not 0 <= original_window[4] < 4
                or (context.get('game_id'), context.get('round_no'), context.get('trigger_seq')) != original_window[:3]
                or (wire_context.get('game_id'), wire_context.get('round_no'), wire_context.get('trigger_seq')) != original_window[:3]
                or type(context.get('round_no')) is not int or type(context.get('trigger_seq')) is not int
                or type(wire_context.get('round_no')) is not int or type(wire_context.get('trigger_seq')) is not int
                or type(wire_context.get('attempt_no')) is not int
                or sent.get('decision_id') != did or type(sent.get('attempt_no')) is not int
                or sent['attempt_no'] != attempt or not isinstance(sent.get('body'), dict)):
            return fail('phase_post_adapter_mapping_invalid')
        timing = payload.get('request_timing')
        start = timing.get('transport_started_at_monotonic') if isinstance(timing, dict) else None
        if (type(start) not in (int, float) or not math.isfinite(start)
                or type(wire.get('monotonic_ns')) is not int
                or wire['monotonic_ns'] > int(start * 1e9)
                or type(row.get('monotonic_ns')) is not int or row['monotonic_ns'] < int(start * 1e9)):
            return fail('phase_post_adapter_mapping_timing_unknown')
        # 身份只用于关联，不是计数键；同五元窗多个不同DID的POST仍累计并拒绝重分类。
        counts[original_window] = counts.get(original_window, 0) + 1
        info['mapped_post_records'] += 1
    return counts, info


def closed_pass_recovery(records, following, old_window, old_did, post_counts, adapter_counts):
    """只证即时已应用的本人摸牌及独立新弃牌成功；不读取赛后事件或断言关闭原因。"""
    body, snap = following['body'], following['body']['snapshot']
    seq, seat = body['seq'], old_window[4]
    if (snap.get('game_id') != old_window[0] or snap.get('round_no') != old_window[1]
            or snap.get('phase') != 'draw' or snap.get('seat') != seat or snap.get('turn') != seat
            or any(type(snap.get(k)) is not int for k in ('round_no', 'seat', 'turn'))):
        return None
    new_window = (old_window[0], old_window[1], seq, 'draw', seat)
    inputs = [r for r in records if r['kind'] == 'decision_input'
        and (r['context'].get('game_id'), r['context'].get('round_no'),
             r['context'].get('trigger_seq')) == new_window[:3]]
    if len(inputs) != 1: return None
    source = inputs[0]; inp = source['payload']; did = source['context'].get('decision_id')
    applied = following.get('applied_at_monotonic_ns')
    recorded_window = window(inp.get('window'))
    if recorded_window != new_window or any(type(recorded_window[i]) is not int for i in (1, 2, 4)): return None
    if (not isinstance(did, str) or not did or did == old_did
            or window(inp.get('window')) != new_window or inp.get('rule_completeness') != 'complete'
            or inp.get('rejected_attempts') != [] or inp.get('snapshot_seq') != seq or inp.get('consumed_seq') != seq
            or any(type(inp.get(k)) is not int for k in ('snapshot_seq', 'consumed_seq'))
            or type(applied) is not int or applied < following['stamp']
            or type(source.get('monotonic_ns')) is not int or source['monotonic_ns'] <= applied):
        return None
    selected = [r for r in records if r['context'].get('game_id') == new_window[0]
        and r['context'].get('decision_id') == did]
    if any((r['context'].get('round_no'), r['context'].get('trigger_seq')) != new_window[1:3]
           or any(type(r['context'].get(k)) is not int for k in ('round_no', 'trigger_seq'))
           for r in selected): return None
    intents = [r for r in selected if r['kind'] == 'submission_intent'
        and 'latest_send_at_monotonic' in r['payload']]
    wires = [r for r in selected if r['kind'] == 'submission_intent' and 'body' in r['payload']]
    outcomes = [r for r in selected if r['kind'] == 'submission_outcome' and 'outcome_type' in r['payload']]
    ends = [r for r in selected if r['kind'] == 'decision_ended']
    if len(intents) != 1 or len(wires) != 1 or len(outcomes) != 1 or len(ends) != 1: return None
    intent, wire, outcome, end = intents[0], wires[0], outcomes[0], ends[0]
    action = intent['payload'].get('action_key')
    # 本次只纳入实际已见的独立摸牌后弃牌成功，未为其它动作预建宽泛豁免。
    if not isinstance(action, str) or not action.startswith('discard:') or not action[8:]: return None
    legal = inp.get('legal_keys')
    if not isinstance(legal, list) or any(not isinstance(key, str) for key in legal) or action not in legal: return None
    matches = [r for r in selected if r['kind'] == 'candidate_validated'
        and r['payload'].get('action_key') == action and r['payload'].get('legal') is True]
    if len(matches) != 1: return None
    validation = matches[0]
    if (validation['payload'].get('action') != {'kind': 'discard', 'tile': action[8:], 'schema_version': 1}
            or wire['payload'].get('body') != {'action': 'discard', 'tile': action[8:]}): return None
    for record in (intent, wire, outcome):
        if type(record['context'].get('attempt_no')) is not int or record['context']['attempt_no'] != 1: return None
    for record in (validation, intent, wire, end):
        recorded_window = window(record['payload'].get('window'))
        if recorded_window != new_window or any(type(recorded_window[i]) is not int for i in (1, 2, 4)): return None
    for record in (intent, wire):
        if record['payload'].get('based_on_authoritative_seq') != seq: return None
    for record in (wire, outcome):
        if (record['payload'].get('decision_id') != did or type(record['payload'].get('attempt_no')) is not int
                or record['payload']['attempt_no'] != 1 or record['payload'].get('action_key') != action): return None
    if outcome['payload'].get('outcome_type') != 'SubmitAccepted': return None
    if any(type(end['payload'].get(k)) is not int or end['payload'][k] != 1
           for k in ('sent_attempts', 'attempt_count')): return None
    if any(type(counts.get(new_window)) is not int or counts[new_window] != 1
           for counts in (post_counts, adapter_counts)): return None
    ordered = (source, validation, intent, wire, outcome, end)
    stamps = [r.get('monotonic_ns') for r in ordered]
    if any(type(stamp) is not int for stamp in stamps) or stamps != sorted(stamps): return None
    return {'recovery_decision_id': did, 'recovery_window': list(new_window),
        'recovery_actual_outcome': 'SubmitAccepted', 'recovery_sent_attempts': 1,
        'recovery_compact_original_line_sha256': [r['original_line_sha256'] for r in ordered],
        'clock_unknown': True, 'closure_reason_unknown': True,
        'postgame_timeout_used': False}


def prove(rejection, records, snapshots, post_counts, adapter_counts):
    """每项均须原件证据；缺项仍按原非法/未知门阻下一房，绝不宽免其他INVALID_ACTION。"""
    row = rejection; ctx = row.get('context', {}); payload = row.get('payload', {})
    family = rejection_family(payload)
    if family is None: return None
    gid, did, attempt = key(ctx); timing = payload.get('request_timing', {})
    selected = [record for record in records if record['context'].get('game_id') == gid
        and record['context'].get('decision_id') == did]
    inputs = [record for record in selected if record['kind'] == 'decision_input']
    validated = [record for record in selected if record['kind'] == 'candidate_validated']
    intents = [record for record in selected if record['kind'] == 'submission_intent'
        and record['context'].get('attempt_no') == attempt and 'latest_send_at_monotonic' in record['payload']]
    outcomes = [record for record in selected if record['kind'] == 'submission_outcome'
        and record['context'].get('attempt_no') == attempt and 'outcome_type' in record['payload']]
    ended = [record for record in selected if record['kind'] == 'decision_ended']
    bodies = [record for record in selected if record['kind'] == 'submission_intent'
        and record['context'].get('attempt_no') == attempt and 'body' in record['payload']]
    if len(inputs) != 1 or len(intents) != 1 or len(outcomes) != 1 or len(ended) != 1 or len(bodies) != 1: return None
    source, intent, outcome = inputs[0], intents[0], outcomes[0]; inp, sent, returned = source['payload'], intent['payload'], outcome['payload']
    action = sent.get('action_key'); old_window = window(inp.get('window'))
    if old_window is None or not isinstance(action, str): return None
    server_closed_pass = False
    server_closed_only_pass = False
    if family == 'peng':
        if not action.startswith('peng:') or old_window[3] != 'response_peng': return None
    elif family == 'chi':
        if not action.startswith('chi:') or old_window[3] != 'response_chi': return None
        chi_tiles = action[4:].split(',')
        # 这里只核录制牌组与编码一致，不重算规则；合法性仍必须有完整原规则及复核记录。
        if (len(chi_tiles) != 3 or any(len(tile) != 2 or tile[0] not in '123456789'
                or tile[1] not in 'wbt' for tile in chi_tiles)
                or len({tile[1] for tile in chi_tiles}) != 1
                or any(int(tile[0]) != int(chi_tiles[0][0]) + index for index, tile in enumerate(chi_tiles))):
            return None
    else:
        if action != 'pass' or old_window[3] != 'response_chi': return None
        legal = inp.get('legal_keys')
        if legal != ['pass']:
            # 新类只接受完整Chi+Pass集合；旧唯一Pass及吃/碰类别的时序门不放宽。
            if (not isinstance(legal, list) or len(legal) < 2 or any(not isinstance(k, str) for k in legal)
                    or len(set(legal)) != len(legal) or legal.count('pass') != 1
                    or any(not k.startswith('chi:') for k in legal if k != 'pass')): return None
            server_closed_pass = True
    if inp.get('rule_completeness') != 'complete' or action not in inp.get('legal_keys', []): return None
    if old_window[:3] != (gid, ctx.get('round_no'), ctx.get('trigger_seq')): return None
    if window(sent.get('window')) != old_window or sent.get('based_on_authoritative_seq') != inp.get('snapshot_seq'): return None
    matches = [record for record in validated if record['payload'].get('action_key') == action
        and record['payload'].get('legal') is True and window(record['payload'].get('window')) == old_window]
    if len(matches) != 1: return None
    code = action.split(':', 1)[1] if family == 'peng' else None
    expected_action = {'kind': 'peng', 'tile': code, 'schema_version': 1} if family == 'peng' else {'kind': 'pass', 'schema_version': 1}
    if family == 'chi': expected_action = {'kind': 'chi', 'tiles': chi_tiles, 'schema_version': 1}
    if matches[0]['payload'].get('action') != expected_action: return None
    # 本版官方适配器为 pass 明确发送空 tile；不接受别的 tile 或额外字段。
    expected_body = {'action': 'peng', 'tile': code} if family == 'peng' else {'action': 'pass', 'tile': ''}
    if family == 'chi':
        body = bodies[0]['payload'].get('body')
        if not isinstance(body, dict) or body.get('tile') not in chi_tiles: return None
        chi_discard = body['tile']
        chi_owned = [tile for tile in chi_tiles if tile != chi_discard]
        expected_body = {'action': 'chi', 'tile': chi_discard, 'tiles': chi_owned}
    if bodies[0]['payload'].get('body') != expected_body: return None
    wire = bodies[0]; wire_payload = wire['payload']; wire_context = wire['context']
    if window(wire_payload.get('window')) != old_window: return None
    if (wire_payload.get('action_key') != action or wire_payload.get('based_on_authoritative_seq') != inp.get('snapshot_seq')
            or wire_payload.get('decision_id') != did or wire_payload.get('attempt_no') != attempt): return None
    if (wire_context.get('round_no'), wire_context.get('trigger_seq')) != old_window[1:3]: return None
    budget = inp.get('budget') or {}; latest = budget.get('latest_send_at_monotonic'); sent_latest = sent.get('latest_send_at_monotonic')
    start, finish = timing.get('transport_started_at_monotonic'), timing.get('completed_at_monotonic')
    if any(type(value) not in (int, float) or not math.isfinite(value) for value in (latest, sent_latest, start, finish)): return None
    if latest != sent_latest: return None
    if family == 'only_pass' and inp.get('legal_keys') == ['pass'] and start < finish < latest:
        # batch013的原唯一Pass在本地latest前已收到相位拒绝，不能伪称跨本地截止。
        # 仅走下方既有全套服务器关闭＋独立本人DRAW成功证明；未观测服务器收包钟。
        if inp.get('rejected_attempts') != []: return None
        server_closed_pass = True
        server_closed_only_pass = True
    if server_closed_pass:
        # 本地latest不是已校准服务器时间；新类只用HTTP及已应用快照证明相位关闭。
        if not start < finish: return None
    elif not start < latest < finish: return None
    if any(type(record.get('monotonic_ns')) is not int or record['monotonic_ns'] > int(start * 1e9)
           for record in (source, matches[0], intent, wire)): return None
    if type(row.get('monotonic_ns')) is not int or type(outcome.get('monotonic_ns')) is not int:
        return None
    if outcome['monotonic_ns'] < row['monotonic_ns']: return None
    if post_counts.get(old_window, 0) != 1: return None
    if adapter_counts.get(old_window, 0) != 1: return None
    end = ended[0]['payload']
    if window(end.get('window')) != old_window: return None
    if type(end.get('sent_attempts')) is not int or end['sent_attempts'] != 1:
        return None
    if type(end.get('attempt_count')) is not int or end['attempt_count'] != 1:
        return None
    if returned.get('outcome_type') != 'SubmitRejectedNoRefresh' or returned.get('reason') != 'conflict_refresh_unavailable': return None
    if returned.get('official_code') != 'INVALID_ACTION' or returned.get('rejected_action_key') != action: return None
    before = [item for item in snapshots if item['gid'] == gid and item['stamp'] < int(start * 1e9)
        and item['seq_requested'] == 0 and item['body'].get('gap') is False and item['body'].get('seq') == inp.get('snapshot_seq')]
    if not before: return None
    prior = max(before, key=lambda item: item['stamp']); pre = prior['body'].get('snapshot') or {}
    if prior.get('applied') is not True: return None
    if pre.get('phase') != old_window[3] or pre.get('round_no') != old_window[1] or pre.get('seat') != old_window[4]: return None
    if family == 'peng' and pre.get('last_discard') != code: return None
    if family == 'only_pass' and not isinstance(pre.get('last_discard'), str): return None
    if server_closed_pass:
        # 旧五元窗计数为1不足以证明旧DID无跨窗重试；不能忽略被attempt过滤掉的额外意图/结果。
        if type(attempt) is not int or attempt != 1: return None
        for record in (source, matches[0], ended[0]):
            context = record['context']
            if (any(type(context.get(k)) is not int for k in ('round_no', 'trigger_seq'))
                    or (context['round_no'], context['trigger_seq']) != old_window[1:3]): return None
        for record in selected:
            if record['kind'] not in ('submission_intent', 'submission_outcome'): continue
            context, detail = record['context'], record['payload']
            if (type(context.get('attempt_no')) is not int or context['attempt_no'] != attempt
                    or any(type(context.get(k)) is not int for k in ('round_no', 'trigger_seq'))
                    or (context['round_no'], context['trigger_seq']) != old_window[1:3]): return None
            if 'attempt_no' in detail and (type(detail['attempt_no']) is not int or detail['attempt_no'] != attempt): return None
            if record['kind'] == 'submission_intent' or 'window' in detail:
                recorded_window = window(detail.get('window'))
                if recorded_window != old_window or any(type(recorded_window[i]) is not int for i in (1, 2, 4)): return None
        if (any(type(old_window[i]) is not int for i in (1, 2, 4)) or not 0 <= old_window[4] < 4
                or any(type(inp.get(k)) is not int for k in ('snapshot_seq', 'consumed_seq'))
                or inp.get('consumed_seq') != inp['snapshot_seq'] or inp['snapshot_seq'] < old_window[2]
                or pre.get('game_id') != gid or type(pre.get('turn')) is not int
                or any(type(pre.get(k)) is not int for k in ('round_no', 'seat'))
                or not 0 <= pre['turn'] < 4 or old_window[4] != (pre['turn'] + 1) % 4
                or pre.get('responding_seats') != [old_window[4]] or not isinstance(pre.get('my_hand'), list)
                or type(prior.get('applied_at_monotonic_ns')) is not int
                or not prior['stamp'] <= prior['applied_at_monotonic_ns'] < source['monotonic_ns']): return None
        for candidate in inp['legal_keys']:
            if candidate == 'pass': continue
            tiles = candidate[4:].split(',')
            if (len(tiles) != 3 or any(len(tile) != 2 or tile[0] not in '123456789' or tile[1] not in 'wbt' for tile in tiles)
                    or len({tile[1] for tile in tiles}) != 1
                    or any(int(tile[0]) != int(tiles[0][0]) + i for i, tile in enumerate(tiles))
                    or pre['last_discard'] not in tiles
                    or any(pre['my_hand'].count(tile) < 1 for tile in tiles if tile != pre['last_discard'])): return None
        if any(type(counts.get(old_window)) is not int or counts[old_window] != 1
               for counts in (post_counts, adapter_counts)): return None
        for record in (source, matches[0], intent, wire, ended[0]):
            recorded_window = window(record['payload'].get('window'))
            if recorded_window != old_window or any(type(recorded_window[i]) is not int for i in (1, 2, 4)): return None
    if family == 'chi':
        seat, turn, hand = old_window[4], pre.get('turn'), pre.get('my_hand')
        deadline, wall_start = pre.get('window_deadline_ms'), timing.get('started_wall_unix_ms')
        # 官方已公布的唯一吃位、弃牌来源与本人两张牌均须在原权威快照中对应；不宽免错牌或错方向。
        if (type(seat) is not int or type(turn) is not int or not 0 <= turn < 4
                or seat != (turn + 1) % 4 or pre.get('responding_seats') != [seat]
                or pre.get('last_discard') != chi_discard or not isinstance(hand, list)
                or any(hand.count(tile) < 1 for tile in chi_owned)):
            return None
        if inp.get('consumed_seq') != inp.get('snapshot_seq'): return None
        # 新吃窗还保留实际Unix毫秒启动相对官方截止的严格门；服务器收包时刻依旧未知。
        if type(deadline) is not int or type(wall_start) is not int or not 0 <= wall_start < deadline: return None
    after = [item for item in snapshots if item['gid'] == gid and item['stamp'] > row['monotonic_ns']
        and item['seq_requested'] == 0 and item['body'].get('gap') is False and type(item['body'].get('seq')) is int
        and item['body']['seq'] > inp.get('snapshot_seq', -1) and isinstance(item['body'].get('snapshot'), dict)]
    for following in sorted(after, key=lambda item: item['stamp']):
        if following.get('applied') is not True: continue
        snap = following['body']['snapshot']
        if snap.get('seat') != old_window[4]: continue
        if server_closed_pass:
            recovery = closed_pass_recovery(records, following, old_window, did, post_counts, adapter_counts)
            if recovery is None: continue
            return {'classification': 'recovered_server_closed_only_pass' if server_closed_only_pass else 'recovered_server_closed_response_pass', 'decision_id': did,
                'attempt_no': attempt, 'game_id': gid, 'window': list(old_window), 'action_key': action,
                'actual_outcome': 'SubmitRejectedNoRefresh', 'authoritative_recovery_seq': following['body']['seq'],
                'all_window_adapter_body_intents': 1, 'decision_sent_attempts': 1,
                'rejected_raw_sha256': hashlib.sha256(json.dumps(row, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest(),
                'compact_original_line_sha256': [record['original_line_sha256'] for record in (source, matches[0], intent, wire, outcome)],
                'timely_send_margin_ms': None, 'observed_local_send_margin_ms': (latest - start) * 1000,
                'transport_response_ms': (finish - start) * 1000,
                'warning': ('no_evidence_of_lost_claim_opportunity; clock_unknown; closure_reason_unknown; server_receive_time_not_observed'
                    if server_closed_only_pass else 'possible_lost_chi; clock_unknown; closure_reason_unknown; server_receive_time_not_observed'),
                **recovery}
        if any(snap.get(field) != pre.get(field) for field in ('round_no', 'phase', 'turn', 'last_discard')):
            classification = 'recovered_expired_peng_window' if family == 'peng' else 'recovered_expired_only_pass_window'
            warning = 'lost_response_opportunity_and_transport_latency; server_receive_time_not_observed' if family == 'peng' else 'only_pass_window_advanced_and_transport_latency; no_evidence_of_lost_claim_opportunity; server_receive_time_not_observed'
            if family == 'chi':
                classification = 'recovered_expired_chi_window'
                warning = 'lost_response_opportunity_and_transport_latency; server_receive_time_not_observed'
            return {'classification': classification, 'decision_id': did, 'attempt_no': attempt,
                'game_id': gid, 'window': list(old_window), 'action_key': action,
                'actual_outcome': 'SubmitRejectedNoRefresh', 'authoritative_recovery_seq': following['body']['seq'],
                'all_window_adapter_body_intents': 1, 'decision_sent_attempts': 1,
                'rejected_raw_sha256': hashlib.sha256(json.dumps(row, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest(),
                'compact_original_line_sha256': [record['original_line_sha256'] for record in (source, matches[0], intent, wire, outcome)],
                'timely_send_margin_ms': (latest - start) * 1000, 'transport_response_ms': (finish - start) * 1000,
                'warning': warning}
    return None
