#!/usr/bin/env python3
"""G198：同一合法后继弃牌的普通缺口保护与自然七对选择权。"""

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
from hashlib import sha256
import json
from pathlib import Path
import time

import c31_action_layer_gap as c31
import g52_shared_horizon as g52
import g95_wider_discard_same_hand_preflight as g95
import g181_two_draw_settlement_value as g181
import g196_three_draw_competing_route_pilot as g196
from hangma_bot.application.audit_codec import candidate_value_facts_to_json
from hangma_bot.hangma import value_analysis
from hangma_bot.policy.r18_integrated_positive_v2_rules_20260929_release import (
    R18IntegratedPositiveV2Rules20260929ReleasePolicy,
    R18_V2_RULES_20260929_SOURCE_HASH,
)


HERE = Path(__file__).resolve().parent
PLAN = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/G198-COMMON-HORIZON-SEVEN-OPTION-PREREG-2026-09-29.md')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g198-common-horizon-seven-option-20260929/result.json')
MODES = ("restricted", "unrestricted")


def digest(path: Path) -> str:
    """绑定预登记、生产与冻结来源字节。"""

    return sha256(path.read_bytes()).hexdigest()


def _choice(leaves: list[dict], white_floor: int, ordinary_limit: int) -> dict | None:
    """在同一合法后继叶里先守普通缺口上限，再选最佳自然七对。"""

    permitted = [leaf for leaf in leaves
                 if leaf["whites_held"] >= white_floor
                 and type(leaf["ordinary_natural_need"]) is int
                 and leaf["ordinary_natural_need"] <= ordinary_limit
                 and type(leaf["seven_natural_need"]) is int
                 and type(leaf["seven_natural_progress_capacity"]) is int]
    if not permitted:
        return None
    winner = min(permitted, key=lambda leaf: (
        leaf["seven_natural_need"], -leaf["seven_natural_progress_capacity"],
        leaf["ordinary_natural_need"], -leaf["ordinary_natural_progress_capacity"],
        leaf["discard"],
    ))
    return {key: winner[key] for key in (
        "discard", "ordinary_natural_need", "ordinary_natural_progress_capacity",
        "seven_natural_need", "seven_natural_progress_capacity", "whites_held",
    )}


def compare(parent: dict, alternate: dict) -> dict:
    """两臂共享第一摸码和容量；只以同叶普通保护后的七对路线比较。"""

    p_edges = parent["edges"]
    a_edges = alternate["edges"]
    if (parent["first_draw_public_capacity"] != alternate["first_draw_public_capacity"]
            or [(edge["draw"], edge["capacity"]) for edge in p_edges]
            != [(edge["draw"], edge["capacity"]) for edge in a_edges]):
        raise ValueError("G198 双臂首次条件摸牌身份或公开容量不一致")
    counts = {mode: Counter() for mode in MODES}
    rows = []
    for p, a in zip(p_edges, a_edges, strict=True):
        if p["draw"] != a["draw"] or p["capacity"] != a["capacity"]:
            raise ValueError("G198 第一摸码或容量错位")
        edge = {"draw": p["draw"], "capacity": p["capacity"], "modes": {}}
        for mode in MODES:
            data = []
            for tree, one in ((parent, p), (alternate, a)):
                item = one["best_second"][mode]
                leaves = item.get("legal_leaves")
                if not isinstance(leaves, list) or len(leaves) != item["legal_discard_count"]:
                    raise ValueError("G198 完整合法后继弃牌叶缺失")
                white_floor = tree["root_whites_held"] + int(p["draw"] == "白")
                retained = [leaf for leaf in leaves
                            if leaf["whites_held"] >= white_floor]
                if not retained:
                    data.append((None, leaves, white_floor))
                    continue
                if any(type(leaf["ordinary_natural_need"]) is not int
                       or type(leaf["seven_natural_need"]) is not int
                       or type(leaf["seven_natural_progress_capacity"]) is not int
                       for leaf in retained):
                    raise ValueError("G198 普通/七对自然事实未知")
                data.append((min(leaf["ordinary_natural_need"] for leaf in retained),
                             leaves, white_floor))
            (pbest, pleaves, pwhite), (abest, aleaves, awhite) = data
            if pbest is None or abest is None:
                status = "no_shared_white_retaining_leaf"
                details = {"ordinary_best": [pbest, abest], "joint_choices": None}
            else:
                limit = max(pbest, abest)
                pc = _choice(pleaves, pwhite, limit)
                ac = _choice(aleaves, awhite, limit)
                if pc is None or ac is None:
                    raise ValueError("G198 普通上限未保留原最佳合法叶")
                pseven = (pc["seven_natural_need"],
                          -pc["seven_natural_progress_capacity"])
                aseven = (ac["seven_natural_need"],
                          -ac["seven_natural_progress_capacity"])
                seven = ("alternate_better" if aseven < pseven else
                         "parent_better" if pseven < aseven else "equal")
                ordinary = ("alternate_better" if abest < pbest else
                            "parent_better" if pbest < abest else "equal")
                status = ordinary + "/" + seven
                details = {"ordinary_best": [pbest, abest],
                           "joint_choices": {"parent": pc, "alternate": ac},
                           "ordinary_limit": limit}
            counts[mode][status] += p["capacity"]
            edge["modes"][mode] = {"status": status, **details}
        rows.append(edge)
    for mode in MODES:
        if sum(counts[mode].values()) != parent["first_draw_public_capacity"]:
            raise ValueError("G198 第一摸容量分区不守恒")
    return {"first_capacity": parent["first_draw_public_capacity"],
            "by_mode_capacity": {mode: dict(sorted(count.items()))
                                 for mode, count in counts.items()},
            "edges": rows}


def _selected() -> list[dict]:
    """沿用 G196 冻结选样，仅取 H/M 各两个一白开发根。"""

    selected = [row for row in g196._selected() if row["white_before"] == 1]
    if len(selected) != 4 or Counter(row["mix"] for row in selected) != {"H": 2, "M": 2}:
        raise ValueError("G198 一白四窗冻结选样不成立")
    return selected


def main() -> None:
    """从当前规则绑定父代准确重放目标窗，再计算同叶结构。"""

    if OUT.exists():
        raise FileExistsError("G198 结果已存在；拒绝覆盖")
    selected = _selected()
    targets = g181._table_targets(selected)
    contract = json.loads(g95.g93.paired.CONTRACT.read_text(encoding="utf-8"))
    versions = g95.g93.natural.stage.contract_versions_block(contract)
    plans = {(mix, root, seat): plan for mix, root, seat, plan
             in g196.source.plans(contract)}
    scorer = g196.capture.g87.c31.load_parent()
    grouped = defaultdict(list)
    for row in selected:
        grouped[(row["mix"], row["root_index"], row["focal_seat"])].append(row)
    rows = []
    for table_key, members in sorted(grouped.items()):
        mix, root, seat = table_key
        old_capture = g95.CaptureWiderPolicy
        old_factory = g95.g93.paired.policy_factory

        def current_factory(arm: str):
            """仅对父代使用 G194 当前规则包；评分源码保持冻结。"""

            if arm != "r18_v2":
                return old_factory(arm)

            def build(monotonic):
                del monotonic
                return R18IntegratedPositiveV2Rules20260929ReleasePolicy(
                    rules_source_hash=R18_V2_RULES_20260929_SOURCE_HASH,
                    value_analysis_sha256=digest(Path(value_analysis.__file__)),
                )
            return build

        g95.CaptureWiderPolicy = g196.capture.CaptureEveryHandAllDrawPolicy
        g95.g93.paired.policy_factory = current_factory
        try:
            captured, *_ = g95.run_full(plans[table_key], contract, versions, mix)
        finally:
            g95.CaptureWiderPolicy = old_capture
            g95.g93.paired.policy_factory = old_factory
        for item in members:
            key = (mix, root, seat, item["round_no"])
            record = captured.records.get(item["round_no"])
            if (record is None or g196.capture.scored_target(record, scorer) != targets[key]
                    or item["observation_sha256"] != targets[key]["observation_sha256"]
                    or item["parent_action"] != record.parent_key
                    or item["alternate_action"] != record.alternate_key):
                raise ValueError("G198 冻结来源观察或双臂身份漂移")
            legal = {action.action_key: action for action in record.request.rules.legal_candidates}
            trees = {}
            started = time.perf_counter()
            for name, action_key in (("parent", record.parent_key),
                                     ("alternate", record.alternate_key)):
                action = legal.get(action_key)
                if action is None or action.value_facts is None:
                    raise ValueError("G198 合法动作或生产价值事实缺失")
                trees[name] = g52.evaluate_root(
                    record.request.observation,
                    {"action_key": action_key,
                     "value_facts": candidate_value_facts_to_json(action.value_facts)},
                    c31.RULE_CONFIG, include_all_leaves=True,
                )
            result = compare(trees["parent"], trees["alternate"])
            rows.append({"mix": mix, "root_index": root, "focal_seat": seat,
                         "round_no": item["round_no"], "white_before": 1,
                         "observation_sha256": item["observation_sha256"],
                         "parent_action": record.parent_key,
                         "alternate_action": record.alternate_key,
                         "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
                         "comparison": result})
            print(json.dumps({"windows_complete": len(rows), "last": key},
                             ensure_ascii=False), flush=True)
    payload = {"schema": "g198-common-horizon-seven-option/1",
               "source_sha256": {"plan": digest(PLAN), "script": digest(Path(__file__)),
                                 "g160_selection": digest(g196.source.OUT / "selection.json"),
                                 "g160_rows": digest(g196.source.OUT / "rows.jsonl"),
                                 "g52_script": digest(Path(g52.__file__)),
                                 "g196_script": digest(Path(g196.__file__))},
               "rows": rows,
               "boundary": "同一未来条件摸牌与生产合法弃牌叶的结构选择权；公开容量非真实牌墙概率，不含他家先胡或收益标签。"}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True,
                              indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
