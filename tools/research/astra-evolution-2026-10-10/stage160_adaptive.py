"""在已声明的CPU调度下完整评估，先一槽，再在证实释放后扩为十槽。

算法、牌山和原预算均不随结果调整。复用冻结经过时钟worker，不覆盖
旧驱动；两个资源阶段自然join后才交接，不因观察超时重启或补种子。
"""
from __future__ import annotations

import argparse
import concurrent.futures
import json
import multiprocessing
from pathlib import Path
import time

import stage160_budgeted as budgeted

stage = budgeted.stage


def verify_schedule(declaration):
    """一槽和十槽是事前资源计划，workers字段表示已冻结上限。"""
    schedule = declaration['worker_schedule']
    if (declaration['workers'] != 10 or schedule['initial_workers'] != 1
            or schedule['released_workers'] != 10
            or declaration['cpu_cores'] * 80 // 100 < 11):
        raise ValueError('资源计划须先1后10，整机重计算上限至少11')
    if schedule['source_exec_session_id'] != 35427:
        raise ValueError('释放依据不是当前原确认handle')
    return schedule


def expansion_evidence(schedule):
    """只认主agent核验handle后的释放，或原确认负门且两个池自然闭合。

原门通过时保留一槽，给旧候选十槽验证/自由赛优先。状态和脚本来源
必须共同匹配；原进程观察超时不是释放证据。
"""
    release = Path(schedule['release_file'])
    if release.exists():
        record = json.loads(release.read_text())
        if (record.get('schema') != 'astra-stage160-cpu-release/1'
                or record.get('source_exec_session_id') != schedule['source_exec_session_id']
                or record.get('source_pipeline_sha256') != schedule['source_pipeline_sha256']
                or type(record.get('source_terminal_exit_code')) is not int
                or record['source_terminal_exit_code'] != 0
                or type(record.get('heavy_slots_released')) is not int
                or record['heavy_slots_released'] != 10):
            raise ValueError('CPU释放记录不匹配；不能扩池')
        return {'kind': 'root_verified_release', 'record_sha256': stage.file_sha(release)}
    source = Path(schedule['source_pipeline_path'])
    if stage.file_sha(source) != schedule['source_pipeline_sha256']:
        raise ValueError('原确认流水线来源漂移')
    state_path = Path(schedule['source_state_path'])
    state = json.loads(state_path.read_text())
    if (state.get('pipeline_sha256') != schedule['source_pipeline_sha256']
            or state.get('candidate_id') != schedule['source_candidate_id']
            or state.get('gates_sha256') != schedule['source_gates_sha256']):
        raise ValueError('原确认状态身份漂移')
    if (state.get('status') == 'confirmation_closed_reliability_review_pending'
            and state.get('confirmation_stage_gate_pass') is False
            and state.get('commands')
            and all(c.get('status') == 'complete' and c.get('exit_code') == 0
                    for c in state['commands'])):
        # 固定原脚本只有subprocess.run（含池join）及全部报告返回后才写该终态。
        return {'kind': 'original_confirmation_negative_natural_join',
                'state_sha256': stage.file_sha(state_path),
                'pipeline_sha256': schedule['source_pipeline_sha256']}
    return None


def main():
    """完整新目录，不续跑旧输出；失败保留原任务并停止追加。"""
    parser = argparse.ArgumentParser()
    parser.add_argument('--declaration', required=True)
    parser.add_argument('--out', required=True)
    parser.add_argument('--plan-only', action='store_true')
    args = parser.parse_args()
    declaration = json.loads(Path(args.declaration).read_text())
    stage.verify_declaration(declaration)
    schedule = verify_schedule(declaration)
    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=False)
    tasks = stage.build_tasks(declaration, out)
    stage.save(out / 'PLAN.json', {'declaration': declaration,
        'declaration_sha256': stage.file_sha(args.declaration), 'driver_sha256': stage.file_sha(__file__),
        'tasks': tasks, 'worker_schedule': schedule, 'logical_budget_not_live_admission': True})
    if args.plan_only:
        return
    results, phases = [], []
    offset, stopped = 0, False
    workers = schedule['released_workers'] if expansion_evidence(schedule) else schedule['initial_workers']
    while offset < len(tasks) and not stopped:
        phase = {'workers': workers, 'started_at_unix_seconds': time.time(),
                 'first_task_index': offset, 'natural_join_complete': False}
        phases.append(phase)
        stage.save(out / 'RESOURCES.json', {'phases': phases, 'active_workers': workers,
            'all_pools_naturally_joined': False})
        with concurrent.futures.ProcessPoolExecutor(max_workers=workers,
                mp_context=multiprocessing.get_context('spawn')) as pool:
            pending = {}
            for _ in range(workers):
                if offset == len(tasks): break
                task = tasks[offset]; offset += 1
                pending[pool.submit(budgeted.worker, task)] = task
            promote = False
            while pending:
                done, _ = concurrent.futures.wait(pending, timeout=30,
                    return_when=concurrent.futures.FIRST_COMPLETED)
                if not done:
                    print(json.dumps({'heartbeat': True, 'workers': workers,
                        'closed': len(results), 'planned': len(tasks)}), flush=True)
                    continue
                for future in done:
                    pending.pop(future)
                    row = future.result(); results.append(row)
                    stopped |= row['status'] != 'complete'
                    stage.save(out / 'PROGRESS.json', {'closed': len(results), 'planned': len(tasks),
                        'results': results, 'resource_phases': phases})
                    print(json.dumps({'closed': len(results), 'planned': len(tasks), 'workers': workers,
                        'stage': row['task']['stage_root'], 'arm': row['task']['arm'],
                        'status': row['status'], 'changed': row.get('actual_changed_windows'),
                        'error': row.get('error')}), flush=True)
                if workers == 1 and not stopped:
                    evidence = expansion_evidence(schedule)
                    promote = evidence is not None
                    if promote: phase['release_evidence'] = evidence
                if not stopped and not promote:
                    for _ in done:
                        if offset == len(tasks): break
                        task = tasks[offset]; offset += 1
                        pending[pool.submit(budgeted.worker, task)] = task
        phase.update(natural_join_complete=True, ended_at_unix_seconds=time.time(),
                     closed_total=len(results))
        stage.save(out / 'RESOURCES.json', {'phases': phases, 'active_workers': 0,
            'completed_pools_naturally_joined': True, 'tasks_remaining': len(tasks) - offset})
        workers = schedule['released_workers']
    complete = len(results) == len(tasks) and not stopped
    stage.save(out / 'RUN-CLOSED.json', {'complete': complete, 'closed': len(results),
        'planned': len(tasks), 'results': results, 'resource_phases': phases})
    stage.save(out / 'RESOURCES.json', {'phases': phases, 'active_workers': 0,
        'all_pools_naturally_joined': True, 'stage_complete': complete})
    if not complete:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
