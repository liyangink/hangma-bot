#!/usr/bin/env python3
"""G247：在 G233 同世界反例中复算行动前无白自然进张。"""

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

from hashlib import sha256
import json
from pathlib import Path

import g178_natural_vs_standard_support as natural
import g233_inversion_same_world_branch as branch
import g87_post_claim_score_trace as g87
from hangma_bot.hangma.engine import _build_context
from hangma_bot.hangma.public_tile_counts import count_unseen_tiles
from hangma_bot.kernel.serialization import observation_from_json


HERE = Path(__file__).resolve().parent
SOURCE = branch.OUT / "result.json"
MANIFEST = branch.OUT / "manifest.json"
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g247-natural-route-counterexample-20260929/result.json')


def digest(path: Path) -> str:
    """绑定程序与冻结来源的原文字节。"""

    return sha256(path.read_bytes()).hexdigest()


def positive_support(tiles) -> dict[str, int]:
    """生产规则逐码公开容量；零容量与白板另记，不冒充墙内概率。"""

    if tiles is None:
        raise ValueError("G247 规则有效牌未知")
    support = {}
    for item in tiles:
        if (item.code in support or type(item.remaining_estimate) is not int
                or not 0 <= item.remaining_estimate <= 4):
            raise ValueError("G247 规则有效牌码或容量非法")
        if item.remaining_estimate:
            support[item.code] = item.remaining_estimate
    return support


def action_state(key: str, legal: dict, full, unseen, meld_count: int) -> dict:
    """两臂只读同一个 PlayerObservation 和生产合法动作事实。"""

    if key not in legal or not key.startswith("discard:"):
        raise ValueError("G247 目标不是生产合法弃牌")
    facts = legal[key].facts
    if (facts is None or type(facts.standard_shanten_after) is not int
            or type(facts.seven_pairs_shanten_after) is not int
            or type(facts.baotou_after) is not bool):
        raise ValueError("G247 生产路线事实未知")
    root = natural._drop(full, key.split(":", 1)[1])
    need, support = natural.natural(root, unseen, meld_count)
    standard = positive_support(facts.standard_useful_tiles)
    seven = positive_support(facts.seven_pairs_useful_tiles)
    return {
        "natural_need": need,
        "natural_support": support,
        "natural_types": len(support),
        "natural_public_capacity": sum(support.values()),
        "standard_shanten": facts.standard_shanten_after,
        "standard_support": standard,
        "standard_types": len(standard),
        "standard_public_capacity": sum(standard.values()),
        "seven_pairs_shanten": facts.seven_pairs_shanten_after,
        "seven_pairs_support": seven,
        "seven_pairs_public_capacity": sum(seven.values()),
        "baotou_after": facts.baotou_after,
        "white_retained": sum(tile.code == "白" for tile in root),
    }


def compare(target: dict, outcome: dict) -> dict:
    """按已冻结窗口身份对齐两臂；结算只作事后反例标签。"""

    mix, root = target["mix"], target["root_index"]
    source_hashes = {
        "g223_stage": digest(branch.g223.stage_path(
            mix, root, target["start_seat"])),
        "g224_stage": digest(branch.g224.stage_path(
            mix, root, target["start_seat"])),
    }
    if source_hashes != outcome["source_sha256"]:
        raise ValueError("G247 G223/G224 行动前观察来源摘要漂移")
    _, archived = branch.archived_root(target)
    observation = observation_from_json(archived["observation"])
    request = g87.request_for(observation)
    parent = target["parent_action"]
    alternate = target["representative_inversion"]["action"]
    if (outcome["identity"]["mix"] != mix
            or outcome["identity"]["root_index"] != root
            or outcome["identity"]["parent_action"] != parent
            or outcome["alternate_action"] != alternate
            or outcome["identity"]["snapshot_seq"] != target["snapshot_seq"]
            or outcome["identity"]["table_id"] != target["table_id"]):
        raise ValueError("G247 同世界结算与行动前窗口身份漂移")
    legal = {item.action_key: item for item in request.rules.legal_candidates}
    if len(legal) != len(request.rules.legal_candidates):
        raise ValueError("G247 生产合法动作键重复")
    full = _build_context(observation).full_hand()
    unseen = count_unseen_tiles(observation)
    meld_count = len(observation.melds[observation.seat])
    states = {key: action_state(key, legal, full, unseen, meld_count)
              for key in (parent, alternate)}
    old, new = states[parent], states[alternate]
    samples = outcome["paired_worlds"]
    if [sample["sample_key"] for sample in samples] != list(branch.SAMPLES):
        raise ValueError("G247 同世界样本键或顺序漂移")
    table_delta = sum(sample["focal_complete_table_delta"]
                      for sample in samples[1:]) / 16
    return {
        "mix": mix, "root_index": root,
        "white_before": sum(tile.code == "白" for tile in full),
        "parent_action": parent, "alternate_action": alternate,
        "visible_source_sha256": source_hashes,
        "states": states,
        "alternate_minus_parent": {
            name: new[name] - old[name]
            for name in ("natural_need", "natural_types",
                         "natural_public_capacity", "standard_shanten",
                         "standard_types", "standard_public_capacity",
                         "seven_pairs_shanten", "seven_pairs_public_capacity",
                         "white_retained")},
        "same_world_16_resamples_table_delta": table_delta,
    }


def main() -> None:
    """只读既有九窗后验反例；结果不得用于在同批拟合发布阈值。"""

    if OUT.exists():
        raise FileExistsError("G247 结果已存在，不覆盖")
    frozen = json.loads(SOURCE.read_text(encoding="utf-8"))
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    targets = branch.selected()
    if (frozen.get("schema") != "g233-inversion-same-world-result/1"
            or manifest.get("selected_windows") != 9
            or frozen.get("windows") != 9
            or len(targets) != 9
            or frozen.get("manifest_sha256") != digest(MANIFEST)):
        raise ValueError("G247 G233 冻结来源不完整")
    rows = []
    sources = {}
    for index, target in enumerate(targets, 1):
        path = branch.OUT / "windows" / f"window-{index:02d}.json"
        if digest(path) != frozen["window_sha256"][path.name]:
            raise ValueError("G247 G233 逐窗结算 SHA 不一致")
        sources[path.name] = digest(path)
        rows.append(compare(target, json.loads(path.read_text(encoding="utf-8"))))
    natural_up = [row for row in rows if row["alternate_minus_parent"]["natural_types"] > 0
                  and row["alternate_minus_parent"]["natural_public_capacity"] > 0]
    if len(natural_up) != 9:
        raise ValueError("G247 已看反例并非九窗均严格自然宽面")
    summary = {
        "windows": len(rows),
        "strict_natural_width_gain": len(natural_up),
        "natural_need_equal": sum(row["alternate_minus_parent"]["natural_need"] == 0
                                  for row in rows),
        "strict_width_negative_positive_zero_resampled_table": [
            sum(row["same_world_16_resamples_table_delta"] < 0 for row in natural_up),
            sum(row["same_world_16_resamples_table_delta"] > 0 for row in natural_up),
            sum(row["same_world_16_resamples_table_delta"] == 0 for row in natural_up),
        ],
    }
    payload = {
        "schema": "g247-natural-route-counterexample-audit/1",
        "source_sha256": {
            "script": digest(Path(__file__)), "g233_result": digest(SOURCE),
            "g233_manifest": digest(MANIFEST),
            "g233_windows": sources,
            "g178_natural_math": digest(Path(natural.__file__)),
        },
        "summary": summary, "rows": rows,
        "boundary": "G233 已看九窗的事后行动前规则事实与相关隐藏世界结算对账；不是九个独立策略收益样本，也不能用后验分差调发布阈值。",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True,
                              indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
