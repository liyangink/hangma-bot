#!/usr/bin/env python3
"""决策数据集导出：把影子审计转成可训练/可复核的逐窗口样本。

设计要点（对齐方案"数据集保留未选择动作与选择理由，避免学生只能模仿其盲区"）：

- **一行一个决策窗口**：含观察摘要、全部合法候选及其规则事实、实际选择与理由、该单局结局；
- **不丢候选**：未选择动作与其路线/价值事实一并保留，供模仿学习之外的排序/偏好学习使用；
- **结局来自同一牌局**：按 (game_id, round_no) 连接 hands 行，含四家分差与赢家番型；
- **血缘**：manifest 记录源批次、freeze 哈希、样本数与特征覆盖统计。

来源：
- `--source shadow`：`run_shadow.py` 产出的 `changes.jsonl.gz`（含路线签名窗口）；
- `--source audit`：真实会话审计 `decisions.jsonl`（全窗口，但无七对向听字段）。

用法：`export_decision_dataset.py shadow --batch <批次目录> --output <dataset.jsonl.gz>`
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
import gzip
import hashlib
import json
import sys
from pathlib import Path

WORK = _project_file(_PROJECT_ROOT, 'review/heuristic-balanced-2026-09-10')
sys.path.insert(0, str(_project_file(_PROJECT_ROOT, WORK.parent / 'big-hand-paths-2026-09-09')))

from hangma_bot.application.audit_codec import candidate_value_facts_to_json
from hangma_bot.hangma import HangmaRules
from hangma_bot.hangma.interface import ValueAnalysisLimits
from hangma_bot.kernel.config import RuleConfig
from hangma_bot.kernel.serialization import observation_from_json

MAX_USEFUL_TILES = 12  # 每个候选保留的有效牌上限，控制体积；其余在计数里体现


def load_hands(batch: Path) -> dict:
    rows = {}
    path = batch / 'hands.jsonl.gz'
    if not path.is_file():
        return rows
    with gzip.open(path, 'rt', encoding='utf-8') as handle:
        for line in handle:
            if not line.strip():
                continue
            hand = json.loads(line)
            rows[(hand.get('game_id'), hand.get('round_no'))] = hand
    return rows


def summarise_facts(facts: dict) -> dict:
    useful = facts.get('useful_tiles') or []
    return dict(
        shanten_after=facts.get('shanten_after'),
        standard_shanten_after=facts.get('standard_shanten_after'),
        seven_pairs_shanten_after=facts.get('seven_pairs_shanten_after'),
        useful_tile_count=len(useful),
        useful_unseen_total=sum(tile.get('remaining_estimate', 0) for tile in useful),
        useful_tiles=[dict(code=tile.get('code'), unseen=tile.get('remaining_estimate'))
                      for tile in useful[:MAX_USEFUL_TILES]],
        best_followup_discard=facts.get('best_followup_discard'),
        completeness=facts.get('completeness'),
        replacement_draw_unknown=facts.get('replacement_draw_unknown'),
    )


def summarise_value_facts(value_facts: dict | None) -> dict | None:
    if not value_facts:
        return None
    routes = []
    for route in (value_facts.get('routes') or [])[:6]:
        settlement = route.get('conditional_settlement') or {}
        conditions = route.get('conditions') or {}
        tiles = route.get('useful_tiles') or []
        routes.append(dict(
            fan=settlement.get('fan'),
            score_delta=settlement.get('score_delta'),
            details=settlement.get('details'),
            unseen_total=sum(tile.get('remaining_estimate', 0) for tile in tiles),
            baotou=conditions.get('baotou'),
            draw_kind=conditions.get('draw_kind'),
            chain_count=conditions.get('chain_count'),
            followup_discard=route.get('followup_discard'),
        ))
    return dict(coverage=value_facts.get('coverage'),
                immediate_settlement=value_facts.get('immediate_settlement'),
                route_count=len(value_facts.get('routes') or []),
                routes=routes)


def enrich(change: dict) -> dict:
    """用规则模块离线重算一摸价值事实（教师侧事实，不进入线上闭环）。

    审计批次按需启用价值分析，覆盖率低；训练数据集需要每个候选的价值目标，
    因此导出时按记录的观察重算：同一规则模块、同一 ValueAnalysisLimits 预算，
    只读观察，不读取牌墙或他家暗牌。
    """

    request = change.get('request') or {}
    observation = request.get('observation')
    rules_doc = request.get('rules') or {}
    if not isinstance(observation, dict):
        return change
    ruleset = rules_doc.get('ruleset_version') or 'hangma-mvp-v10-public-counts'
    rules = HangmaRules(RuleConfig(ruleset, 1, False))
    try:
        analysis = rules.analyze(observation_from_json(observation), value_limits=ValueAnalysisLimits())
    except Exception:
        return change
    by_key = {}
    for candidate in analysis.legal_candidates:
        if candidate.value_facts is None:
            continue
        try:
            by_key[candidate.action_key] = candidate_value_facts_to_json(candidate.value_facts)
        except Exception:
            continue
    for candidate in (request.get('rules') or {}).get('legal_candidates') or []:
        facts = by_key.get(candidate.get('action_key'))
        if facts is not None:
            candidate['value_facts'] = facts
    return change


def window_row(change: dict, hands: dict, source: str) -> dict | None:
    request = change.get('request')
    if not isinstance(request, dict):
        return None
    observation = request.get('observation') or {}
    rules = request.get('rules') or {}
    window = request.get('window_key') or {}
    game_id = window.get('game_id')
    round_no = window.get('round_no')
    hand = hands.get((game_id, round_no)) or {}
    candidates = []
    for candidate in rules.get('legal_candidates') or []:
        action = candidate.get('action') or {}
        entry = dict(action_key=candidate.get('action_key'), kind=action.get('kind'))
        if isinstance(candidate.get('facts'), dict):
            entry['facts'] = summarise_facts(candidate['facts'])
        value = summarise_value_facts(candidate.get('value_facts'))
        if value:
            entry['value_facts'] = value
        candidates.append(entry)
    return dict(
        source=source, game_id=game_id, round_no=round_no,
        trigger_seq=window.get('trigger_seq'), phase=window.get('phase'), seat=window.get('seat'),
        observation=dict(
            hand=[tile for tile in (observation.get('my_hand') or [])],
            drawn_tile=observation.get('drawn_tile'),
            meld_counts=[len(melds) for melds in (observation.get('melds') or [])],
            remaining_tile_count=observation.get('remaining_tile_count'),
            hand_counts=observation.get('hand_counts'),
            rule_state=observation.get('rule_state'),
        ),
        candidates=candidates,
        selected=change.get('selected') or change.get('baseline_action_key'),
        selected_reasons=list(change.get('reasons') or ([change.get('reason')] if change.get('reason') else [])),
        outcome=None if not hand else dict(
            winner_seat=hand.get('winner'), fan=hand.get('fan'), details=hand.get('details'),
            score_delta=hand.get('score_delta'),
            # 单局行不直接带 is_draw：流局由无赢家或零番推导（牌谱行口径见 hands.jsonl.gz 字段）。
            is_draw=bool(hand['is_draw']) if 'is_draw' in hand
            else (hand.get('winner') is None or not hand.get('fan')))
    )


def shadow(batch: Path, output: Path, enrich_value: bool = False) -> dict:
    hands = load_hands(batch)
    changes_path = batch / 'changes.jsonl.gz'
    rows = []
    with gzip.open(changes_path, 'rt', encoding='utf-8') as handle:
        for line in handle:
            if not line.strip():
                continue
            change = json.loads(line)
            if enrich_value:
                change = enrich(change)
            row = window_row(change, hands, 'shadow')
            if row is not None:
                rows.append(row)
    with gzip.open(output, 'wt', encoding='utf-8') as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False) + chr(10))
    with_outcome = sum(1 for row in rows if row['outcome'])
    with_routes = sum(1 for row in rows if any('facts' in c and c['facts'].get('seven_pairs_shanten_after') is not None
                                              for c in row['candidates']))
    with_value = sum(1 for row in rows if any('value_facts' in c for c in row['candidates']))
    # provenance：只记数据文件哈希是不够的——训练样本必须能自证"由哪套规则产生"
    # （AGENTS §7：记录规则、特征、动作、续打策略、对手池、采样器、校准与随机种子版本）。
    # 批次的 freeze.json 里正好钉扎了这些（source_sha256 覆盖全部规则源码），这里原样带出，
    # 使数据集脱离批次目录单独传阅时仍可追溯。
    provenance = None
    freeze_path = batch / "freeze.json"
    if freeze_path.is_file():
        freeze = json.loads(freeze_path.read_text(encoding="utf-8"))
        provenance = {
            "batch_freeze_sha256": hashlib.sha256(freeze_path.read_bytes()).hexdigest(),
            "ruleset": freeze.get("ruleset"),
            "baseline": freeze.get("baseline"),
            "candidate": freeze.get("candidate"),
            "opponents": freeze.get("opponents"),
            "roots": freeze.get("roots"),
            "seed_range": freeze.get("seed_range"),
            "hands_per_table": freeze.get("hands_per_table"),
            "you_cai_bi_kao": freeze.get("you_cai_bi_kao"),
            "rule_source_sha256": freeze.get("source_sha256"),
        }
    return dict(source="shadow", batch=str(batch), windows=len(rows), hands=len(hands),
                enriched=enrich_value, provenance=provenance,
                with_outcome=with_outcome, with_route_facts=with_routes, with_value_facts=with_value,
                mean_candidates=round(sum(len(row["candidates"]) for row in rows) / max(1, len(rows)), 2),
                output=str(output),
                source_sha256={name: hashlib.sha256((batch / name).read_bytes()).hexdigest()
                               for name in ("changes.jsonl.gz", "hands.jsonl.gz")
                               if (batch / name).is_file()})


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest='command', required=True)
    shadow_parser = sub.add_parser('shadow')
    shadow_parser.add_argument('--batch', type=Path, required=True)
    shadow_parser.add_argument('--output', type=Path, required=True)
    shadow_parser.add_argument('--enrich-value', action='store_true',
                               help='导出时用规则模块重算一摸价值事实（教师侧离线事实）')
    args = parser.parse_args()
    report = shadow(args.batch, args.output, enrich_value=args.enrich_value)
    manifest = args.output.with_suffix('.manifest.json')
    manifest.write_text(json.dumps(report, ensure_ascii=False, indent=2) + chr(10), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
