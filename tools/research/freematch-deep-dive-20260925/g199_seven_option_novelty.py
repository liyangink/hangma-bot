#!/usr/bin/env python3
"""G199：在全部一白板开发窗审计后继七对选择权的独有性。"""

from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/freematch-deep-dive-20260925'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

from collections import Counter, defaultdict
import json
from pathlib import Path
import time

import g198_common_horizon_seven_option as g198
from hangma_bot.application.audit_codec import candidate_value_facts_to_json
from hangma_bot.hangma import value_analysis
from hangma_bot.policy.r18_integrated_positive_v2_rules_20260929_release import (
    R18IntegratedPositiveV2Rules20260929ReleasePolicy,
    R18_V2_RULES_20260929_SOURCE_HASH,
)


HERE = Path(__file__).resolve().parent
PLAN = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/G199-SEVEN-OPTION-NOVELTY-PREREG-2026-09-29.md')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g199-seven-option-novelty-20260929/result.json')


def current_seven(facts) -> dict:
    """读取动作当下规则事实；未知与空推进集合有不同语义。"""

    if (facts is None or facts.seven_pairs_shanten_after is None
            or facts.seven_pairs_useful_tiles is None):
        raise ValueError("G199 当前七对向听或推进事实未知")
    seen = set()
    capacity = 0
    for tile in facts.seven_pairs_useful_tiles:
        if tile.code in seen or type(tile.remaining_estimate) is not int:
            raise ValueError("G199 当前七对逐牌容量重复或未知")
        seen.add(tile.code)
        capacity += max(tile.remaining_estimate, 0)
    return {"shanten": facts.seven_pairs_shanten_after, "capacity": capacity}


def current_relation(parent: dict, alternate: dict) -> str:
    """先单列当前七对缺口不同，再比较同缺口的公开有效容量。"""

    if parent["shanten"] != alternate["shanten"]:
        return "shanten_different"
    if parent["capacity"] > alternate["capacity"]:
        return "parent_more"
    if parent["capacity"] < alternate["capacity"]:
        return "alternate_more"
    return "equal"


def _selected() -> list[dict]:
    """G160 冻结选样的全部 25 个一白板开发窗，不借结算选样。"""

    selected = [row for row in g198.g181._selected()
                if row["split"] == "development" and row["white_before"] == 1]
    if len(selected) != 25 or Counter(row["mix"] for row in selected) != {"H": 11, "M": 14}:
        raise ValueError("G199 一白板开发窗冻结选样数量漂移")
    return selected


def main() -> None:
    """准确重放当前生产规则绑定父代，并保存全部第一摸结构。"""

    if OUT.exists():
        raise FileExistsError("G199 结果已存在；拒绝覆盖")
    selected = _selected()
    targets = g198.g181._table_targets(selected)
    contract = json.loads(g198.g95.g93.paired.CONTRACT.read_text(encoding="utf-8"))
    versions = g198.g95.g93.natural.stage.contract_versions_block(contract)
    plans = {(mix, root, seat): plan for mix, root, seat, plan
             in g198.g196.source.plans(contract)}
    scorer = g198.g196.capture.g87.c31.load_parent()
    grouped = defaultdict(list)
    for row in selected:
        grouped[(row["mix"], row["root_index"], row["focal_seat"])].append(row)
    rows = []
    for table_key, members in sorted(grouped.items()):
        mix, root, seat = table_key
        old_capture = g198.g95.CaptureWiderPolicy
        old_factory = g198.g95.g93.paired.policy_factory

        def current_factory(arm: str):
            """只替换父代规则绑定；原评分源码与冻结牌山保持不变。"""

            if arm != "r18_v2":
                return old_factory(arm)

            def build(monotonic):
                del monotonic
                return R18IntegratedPositiveV2Rules20260929ReleasePolicy(
                    rules_source_hash=R18_V2_RULES_20260929_SOURCE_HASH,
                    value_analysis_sha256=g198.digest(Path(value_analysis.__file__)),
                )
            return build

        g198.g95.CaptureWiderPolicy = g198.g196.capture.CaptureEveryHandAllDrawPolicy
        g198.g95.g93.paired.policy_factory = current_factory
        try:
            captured, *_ = g198.g95.run_full(plans[table_key], contract, versions, mix)
        finally:
            g198.g95.CaptureWiderPolicy = old_capture
            g198.g95.g93.paired.policy_factory = old_factory
        for item in members:
            key = (mix, root, seat, item["round_no"])
            record = captured.records.get(item["round_no"])
            if (record is None
                    or g198.g196.capture.scored_target(record, scorer) != targets[key]
                    or item["observation_sha256"] != targets[key]["observation_sha256"]
                    or item["parent_action"] != record.parent_key
                    or item["alternate_action"] != record.alternate_key):
                raise ValueError("G199 冻结来源观察或双臂身份漂移")
            legal = {action.action_key: action
                     for action in record.request.rules.legal_candidates}
            trees = {}
            current = {}
            started = time.perf_counter()
            for name, action_key in (("parent", record.parent_key),
                                     ("alternate", record.alternate_key)):
                action = legal.get(action_key)
                if action is None or action.value_facts is None:
                    raise ValueError("G199 合法动作或生产价值事实缺失")
                current[name] = current_seven(action.facts)
                trees[name] = g198.g52.evaluate_root(
                    record.request.observation,
                    {"action_key": action_key,
                     "value_facts": candidate_value_facts_to_json(action.value_facts)},
                    g198.c31.RULE_CONFIG, include_all_leaves=True,
                )
            rows.append({"mix": mix, "root_index": root, "focal_seat": seat,
                         "round_no": item["round_no"], "white_before": 1,
                         "observation_sha256": item["observation_sha256"],
                         "parent_action": record.parent_key,
                         "alternate_action": record.alternate_key,
                         "current_seven": current,
                         "current_relation": current_relation(
                             current["parent"], current["alternate"]),
                         "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
                         "comparison": g198.compare(trees["parent"], trees["alternate"])})
            print(json.dumps({"windows_complete": len(rows), "last": key},
                             ensure_ascii=False), flush=True)
    payload = {"schema": "g199-seven-option-novelty/1",
               "source_sha256": {"plan": g198.digest(PLAN),
                                 "script": g198.digest(Path(__file__)),
                                 "g160_selection": g198.digest(g198.g196.source.OUT / "selection.json"),
                                 "g160_rows": g198.digest(g198.g196.source.OUT / "rows.jsonl"),
                                 "g198_script": g198.digest(Path(g198.__file__)),
                                 "g52_script": g198.digest(Path(g198.g52.__file__))},
               "rows": rows,
               "boundary": "结果盲结构审计；公开物理容量非牌墙概率，不含对手先胡或收益。"}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True,
                              indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
