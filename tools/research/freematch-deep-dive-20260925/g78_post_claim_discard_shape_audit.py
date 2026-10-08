#!/usr/bin/env python3
"""G78：结果盲复核强手正常摸打分歧与此前本人吃碰的交互。"""

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
import hashlib
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
SOURCE = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g61-strong-draw-action-atlas-20260927')
OUTPUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g78-post-claim-discard-shape-20260928/result.json')
PEERS = ("xuanwu_2346", "tengshe_0638")


def sha(path: Path) -> str:
    """返回输入的 SHA-256，记录冻结资料版本。"""

    return hashlib.sha256(path.read_bytes()).hexdigest()


def stratum(row: dict) -> str:
    """只用本人摸牌时公开副露区分已吃碰、全暗牌和仅杠牌。"""

    melds = row["observation"]["melds"][row["seat"]]
    if any(meld["kind"] in ("chi", "peng") for meld in melds):
        return "prior_chi_peng"
    return "gang_only" if melds else "closed"


def direction(value: int | float) -> str:
    """强手实际弃牌减冻结父代首选弃牌的方向。"""

    return "more" if value > 0 else "less" if value < 0 else "same"


def main() -> None:
    """连接 G61 结果盲动作窗与生产规则事实；不读终局或未来牌墙。"""

    if OUTPUT.exists():
        raise SystemExit("G78 结果已存在，拒绝覆盖")
    manifest_path = _project_file(_PROJECT_ROOT, SOURCE / "result.json")
    shape_path = _project_file(_PROJECT_ROOT, SOURCE / "shape_profile.json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    shape = json.loads(shape_path.read_text(encoding="utf-8"))
    if len(manifest["units"]) != 32 or manifest["outcome_labels_opened"] is not False:
        raise ValueError("G61 冻结房或结果盲边界漂移")
    if shape["batch_sha256"] != sha(manifest_path) or shape["outcome_labels_opened"] is not False:
        raise ValueError("G61 生产规则事实与冻结房不匹配")
    strict = {
        (row["peer"], row["room"], row["game_id"], row["round_no"], row["draw_seq"]): row
        for row in shape["strict_discard_rows"]
    }
    if len(strict) != len(shape["strict_discard_rows"]):
        raise ValueError("G61 严格弃牌窗键重复")

    counts: dict[tuple[str, str, str], Counter] = defaultdict(Counter)
    inputs = {}
    matched = set()
    for unit in sorted(manifest["units"]):
        peer, room = unit.split("/", 1)
        if peer not in PEERS:
            raise ValueError("G61 强手身份漂移")
        path = _project_file(_PROJECT_ROOT, SOURCE / "rooms" / (peer + "--" + room) / "windows.json")
        if sha(path) != manifest["units"][unit]["windows_sha256"]:
            raise ValueError("G61 原始动作窗摘要漂移")
        inputs[unit] = sha(path)
        windows = json.loads(path.read_text(encoding="utf-8"))["windows"]
        for window in windows:
            group = stratum(window)
            stats = counts[(peer, room, group)]
            stats["legal_normal_draw_windows"] += 1
            key = (peer, room, window["game_id"], window["round_no"], window["draw_seq"])
            record = strict.get(key)
            if record is None:
                continue
            matched.add(key)
            if window["actual_action"] != record["strong_action"] or window["parent_top_action"] != record["parent_action"]:
                raise ValueError("G61 动作事实连接不一致")
            stats["strict_discard_pair"] += 1
            delta = record["delta"]
            if delta["ordinary_delta"] != 0:
                continue
            stats["same_ordinary_shanten"] += 1
            for name in ("capacity", "codes"):
                value = delta[f"ordinary_support_{name}_delta_same_layer"]
                if value is None:
                    raise ValueError("同普通型向听但有效牌事实缺失")
                stats[f"ordinary_{name}_{direction(value)}"] += 1
    if matched != set(strict):
        raise ValueError("G61 严格弃牌窗未全量连接")
    if sum(row["legal_normal_draw_windows"] for row in counts.values()) != 17_938:
        raise ValueError("G61 正常摸打总窗口漂移")

    summaries = {}
    for peer in PEERS:
        summaries[peer] = {}
        for group in ("closed", "prior_chi_peng", "gang_only"):
            room_rows = {room: dict(stats) for (name, room, state), stats in counts.items()
                         if name == peer and state == group}
            totals = Counter()
            for room_stats in room_rows.values():
                totals.update(room_stats)
            signs = {}
            for name in ("codes", "capacity"):
                signs[name] = dict(Counter(direction(
                    room_stats.get(f"ordinary_{name}_more", 0)
                    - room_stats.get(f"ordinary_{name}_less", 0)
                ) for room_stats in room_rows.values()))
            summaries[peer][group] = {
                "rooms_with_windows": len(room_rows), "totals": dict(sorted(totals.items())),
                "room_direction_more_minus_less": signs,
            }
    OUTPUT.parent.mkdir(parents=True)
    result = {
        "schema": "g78-post-claim-discard-shape/1", "exploratory": True,
        "outcome_labels_opened": False,
        "source_sha256": {"g61_batch": sha(manifest_path), "g61_shape": sha(shape_path),
                          "g61_windows": inputs, "script": sha(Path(__file__))},
        "strict_rows_matched": len(matched), "summaries": summaries,
        "boundary": "吃碰前后是实际策略产生的状态，观察性分层不能推断吃碰或更宽弃牌有因果收益；"
                    "强手动作不是金标签，公开未见张数不是墙中摸牌概率。",
    }
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                      encoding="utf-8")
    print(json.dumps({"strict_rows_matched": len(matched), "summaries": summaries},
                     ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
