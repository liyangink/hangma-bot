"""量化两房动作计算、动作提交与进入策略时剩余安全窗口。"""
from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/r18-four-arm-evaluation-2026-09-23'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
import argparse
import json
import math
from collections import defaultdict
from pathlib import Path


def dist(values: list[float]) -> dict:
    """按最近秩给出毫秒分位数和截止尾部计数。"""
    ordered = sorted(values)
    def q(p: float) -> float | None:
        return round(ordered[min(len(ordered) - 1, max(0, math.ceil(len(ordered) * p) - 1))], 1) if ordered else None
    return {'count': len(ordered), 'p50_ms': q(.5), 'p95_ms': q(.95),
            'p99_ms': q(.99), 'max_ms': q(1),
            'under_100ms': sum(value < 100 for value in ordered),
            'under_200ms': sum(value < 200 for value in ordered)}


def analyze(root: Path) -> dict:
    """只读四席最后一次审计运行；动作网络耗时仅成功的 HTTP 200。"""
    values = defaultdict(list)
    for slot in sorted(root.glob('slot-*')):
        runs = sorted((slot / 'runs').glob('run-*'), key=lambda path: path.stat().st_mtime)
        if not runs:
            raise ValueError(f'{slot}: no audit run')
        for path in (runs[-1] / 'participants').glob('*/decisions.jsonl'):
            with path.open(encoding='utf-8') as handle:
                for line in handle:
                    row = json.loads(line)
                    payload = row.get('payload') or {}
                    phase = (payload.get('window') or {}).get('phase')
                    response = phase in ('response_peng', 'response_chi')
                    if row.get('kind') == 'decision_input':
                        elapsed = payload.get('rule_elapsed_ms')
                        if isinstance(elapsed, (int, float)):
                            values['rule_all_ms'].append(elapsed)
                            if response:
                                values['rule_response_ms'].append(elapsed)
                        if response:
                            origin = payload.get('budget_origin_monotonic')
                            latest = (payload.get('budget') or {}).get('latest_send_at_monotonic')
                            if origin is not None and latest is not None:
                                values['response_latest_send_slack_ms'].append((latest - origin) * 1000)
                    elif row.get('kind') == 'decision_planned':
                        elapsed = payload.get('policy_elapsed_ms')
                        if isinstance(elapsed, (int, float)):
                            values['policy_all_ms'].append(elapsed)
                            if response:
                                values['policy_response_ms'].append(elapsed)
        for path in (runs[-1] / 'participants').glob('*/raw/t_*.jsonl'):
            with path.open(encoding='utf-8') as handle:
                for line in handle:
                    payload = json.loads(line).get('payload') or {}
                    if payload.get('http_status') != 200 or not str(payload.get('endpoint', '')).endswith('/action'):
                        continue
                    timing = payload.get('request_timing') or {}
                    started = timing.get('transport_started_at_monotonic')
                    completed = timing.get('completed_at_monotonic')
                    if started is not None and completed is not None:
                        values['successful_post_network_ms'].append((completed - started) * 1000)
    return {'room': root.parent.name, 'source': 'decision_input/decision_planned and successful action POST raw request timing',
            'measurements': {key: dist(value) for key, value in sorted(values.items())}}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('audit_roots', nargs='+', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    result = {root.parent.name: analyze(root) for root in args.audit_roots}
    document = json.dumps(result, ensure_ascii=False, indent=2) + '\n'
    if args.output:
        args.output.write_text(document, encoding='utf-8')
    else:
        print(document, end='')

if __name__ == '__main__':
    main()
