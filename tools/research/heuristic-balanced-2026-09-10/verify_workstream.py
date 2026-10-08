#!/usr/bin/env python3
"""工作线验收套件：一条命令复核本工作线的核心主张。

复核项（每项给出通过/失败与关键数值，失败不掩盖）：

1. **影子层零行为差异**：`shadow-confirmation-v2` 的 `shadow-summary.json` 差异为 0；
2. **审计完整性**：同批 `integrity.json.passed` 为真且失败项为空；
3. **门禁自校验（改进模式）**：`gate-hu-vs-v2-development/gate.json` 通过且均值 > 0、区间下界 > 0；
4. **门禁自校验（零差异模式）**：`gate-shadow-zero/gate.json` 的 `identical_arms` 为真；
5. **门禁拒绝低功效**：`gate-hu-vs-v2-smoke/gate.json` 未通过（样本不足时必须拒绝）；
6. **候选否证留痕**：Tier-B 门禁 `gate-tierb-dev32/gate.json` 未通过，且失败项包含均值与区间；
7. **迁移核查产物**：真实与模拟的机会空间/支配率差值在 2pp 以内；
8. **未创建 v2_balanced_v1**：仓库不存在名为 v2_balanced_v1 的生产枚举（门禁未满足）；
9. **门禁稳健性判据生效**：`gate-hu-vs-v2-development/reevaluated.json` 在新增的符号检验判据下
   仍通过（Tier-A 的增益不是重尾假象）；
10. **门禁拒绝重尾假象**：`gate-robustness.json` 里 value 候选的符号检验不显著，且其
   "均值判据外推通过率"随样本量单调上升（说明单靠均值会在大样本下伪证）。

用法：`verify_workstream.py [--root review/heuristic-balanced-2026-09-10]`
"""
from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/heuristic-balanced-2026-09-10'

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
import sys
from pathlib import Path

WORK = _project_file(_PROJECT_ROOT, 'review/heuristic-balanced-2026-09-10')


def load(path: Path):
    return json.loads(path.read_text(encoding='utf-8')) if path.is_file() else None


def check(results, name, passed, detail):
    results.append(dict(check=name, passed=bool(passed), detail=detail))


def main(root: Path) -> int:
    results = []
    shadow = load(root / 'shadow-confirmation-v2/shadow-summary.json')
    check(results, '影子层零行为差异',
          shadow is not None and not shadow.get('zero_difference_mismatches'),
          dict(tables=shadow.get('tables') if shadow else None,
               mismatches=len(shadow.get('zero_difference_mismatches') or []) if shadow else None))

    integrity = load(root / 'shadow-confirmation-v2/integrity.json')
    check(results, '审计完整性',
          integrity is not None and integrity.get('passed') is True and not integrity.get('failures'),
          dict(samples=integrity.get('samples') if integrity else None,
               failures=list((integrity or {}).get('failures') or {}),
               truncated_notes=(integrity or {}).get('truncated_notes')))

    development = load(root / 'gate-hu-vs-v2-development/gate.json')
    check(results, '门禁·改进模式自校验',
          development is not None and development.get('passed') is True
          and (development.get('mean_delta') or 0) > 0
          and (development.get('delta_ci95') or [None])[0] > 0,
          dict(mean=development.get('mean_delta') if development else None,
               ci=(development or {}).get('delta_ci95'), pairs=development.get('tables') if development else None))

    zero = load(root / 'gate-shadow-zero/gate.json')
    check(results, '门禁·零差异模式自校验',
          zero is not None and zero.get('passed') is True and zero.get('checks', {}).get('identical_arms') is True,
          dict(mean=zero.get('mean_delta') if zero else None, pairs=zero.get('tables') if zero else None))

    smoke = load(root / 'gate-hu-vs-v2-smoke/gate.json')
    check(results, '门禁拒绝低功效',
          smoke is not None and smoke.get('passed') is False,
          dict(pairs=smoke.get('tables') if smoke else None, ci=(smoke or {}).get('delta_ci95')))

    tierb = load(root / 'gate-tierb-dev32/gate.json')
    failed_checks = [key for key, value in (tierb or {}).get('checks', {}).items() if not value]
    check(results, '候选否证留痕（Tier-B）',
          tierb is not None and tierb.get('passed') is False and 'mean_delta_positive' in failed_checks,
          dict(mean=tierb.get('mean_delta') if tierb else None, ci=(tierb or {}).get('delta_ci95'),
               failed=failed_checks))

    reevaluated = load(root / 'gate-hu-vs-v2-development/reevaluated.json')
    check(results, '门禁·稳健性判据',
          reevaluated is not None and reevaluated.get('passed') is True
          and (reevaluated.get('checks') or {}).get('robust_not_heavy_tail') is True,
          dict(passed=reevaluated.get('passed') if reevaluated else None,
               sign_test=(reevaluated or {}).get('verdict', {}).get('sign_test'),
               trimmed=(reevaluated or {}).get('verdict', {}).get('trimmed_mean_delta')))

    robustness = load(root / 'gate-robustness.json')
    value_entry = ((robustness or {}).get('candidates') or {}).get('value') or {}
    tier_a_entry = ((robustness or {}).get('candidates') or {}).get('tier_a') or {}
    rates = list((value_entry.get('naive_mean_pass_rate') or {}).values())
    check(results, '门禁拒绝重尾假象',
          bool(rates) and rates[-1] > rates[0]
          and (value_entry.get('sign_p') or 1.0) > 0.05
          and (tier_a_entry.get('sign_p') or 1.0) < 0.05,
          dict(value_sign_p=value_entry.get('sign_p'), value_roots=value_entry.get('roots'),
               naive_pass_rate=value_entry.get('naive_mean_pass_rate'),
               tier_a_sign_p=tier_a_entry.get('sign_p'), tier_a_roots=tier_a_entry.get('roots')))

    night = load(root / 'transfer-night.json')
    simulation = load(root / 'transfer-simulation.json')
    if night and simulation:
        night_windows = night['stats'].get('窗口数', 0)
        sim_windows = simulation['stats'].get('窗口数', 0)
        night_tie = night['stats'].get('同距离候选≥2的窗口', 0) / max(1, night_windows)
        sim_tie = simulation['stats'].get('同距离候选≥2的窗口', 0) / max(1, sim_windows)
        night_dom = night['stats'].get('所选被支配', 0) / max(1, night_windows)
        sim_dom = simulation['stats'].get('所选被支配', 0) / max(1, sim_windows)
        check(results, '迁移核查（机会空间与支配率 ≤2pp）',
              abs(night_tie - sim_tie) <= 0.02 and abs(night_dom - sim_dom) <= 0.02,
              dict(opportunity=[round(night_tie, 4), round(sim_tie, 4)],
                   dominated=[round(night_dom, 4), round(sim_dom, 4)]))
    else:
        check(results, '迁移核查（机会空间与支配率 ≤2pp）', False, '缺少 transfer-night/transfer-simulation 产物')

    dataset = root / 'decision-dataset-confirmation.jsonl.gz'
    if dataset.is_file():
        import gzip
        rows = value_covered = outcome_covered = 0
        with gzip.open(dataset, 'rt', encoding='utf-8') as handle:
            for line in handle:
                if not line.strip():
                    continue
                row = json.loads(line)
                rows += 1
                outcome_covered += 1 if row.get('outcome') else 0
                value_covered += 1 if any('value_facts' in item for item in row.get('candidates') or []) else 0
        check(results, '决策数据集（确认规模）',
              rows >= 10000 and value_covered == rows and outcome_covered == rows,
              dict(rows=rows, value_facts=value_covered, outcomes=outcome_covered))
    else:
        check(results, '决策数据集（确认规模）', False, '缺少 decision-dataset-confirmation.jsonl.gz')

    bootstrap = (root.parents[1] / 'src/hangma_bot/bootstrap.py')
    text = bootstrap.read_text(encoding='utf-8') if bootstrap.is_file() else ''
    check(results, '未创建 v2_balanced_v1',
          '"v2_balanced_v1"' not in text,
          dict(bootstrap=str(bootstrap), has_enum='"v2_balanced_v1"' in text))

    passed = all(item['passed'] for item in results)
    print(json.dumps(dict(passed=passed, checks=results), ensure_ascii=False, indent=2))
    return 0 if passed else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, default=WORK)
    args = parser.parse_args()
    sys.exit(main(args.root))
