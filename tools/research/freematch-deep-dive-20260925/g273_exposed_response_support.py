#!/usr/bin/env python3
"""G273：从 G76 冻结的行动前行复核已有副露的独有鸣牌支持域。"""

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

import argparse
from collections import Counter
import gzip
import hashlib
import json
import math
from pathlib import Path


HERE = Path(__file__).resolve().parent
SOURCE = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g76-confirmed-response-atlas-20260928/rows.jsonl.gz')
DEFAULT_OUTPUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g273-exposed-response-support-20260929/result.json')
EXPECTED_SOURCE_SHA256 = "2a26d239e79ce863311b4be2681a86a9d7d94b50648ab4f4a5355f6d3cd08fc6"
PEERS = ("xuanwu_2346", "tengshe_0638")
ROW_FIELDS = frozenset({
    "accepted_key", "actor", "actual", "claim_shanten", "claim_width", "dealer",
    "discard_seq", "game_id", "own_meld_count", "parent_key", "parent_margin",
    "pass_shanten", "pass_width", "peer", "phase", "r6_key", "room", "round_no",
    "seat", "wall_remaining", "white_count",
})
KEY_FIELDS = ("peer", "actor", "game_id", "round_no", "discard_seq", "seat", "phase")


def digest(path: Path) -> str:
    """返回原文件的 SHA-256；不解读文件以外的牌谱或结算。"""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def key(row: dict) -> tuple:
    """以强手单位、座位和官方弃牌序号固定一个已确认响应阶段。"""
    return tuple(row[field] for field in KEY_FIELDS)


def stable_key_digest(rows: list[dict]) -> str:
    """给筛出的窗口键生成可复核摘要，不读取后续事件。"""
    payload = json.dumps(sorted(key(row) for row in rows), ensure_ascii=False,
                         separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def read_rows(path: Path) -> list[dict]:
    """只接受 G76 冻结的行动前字段；新字段先审查，避免误读赛后资料。"""
    actual_digest = digest(path)
    if actual_digest != EXPECTED_SOURCE_SHA256:
        raise ValueError(f"G76 压缩行动前行摘要漂移：{actual_digest}")
    rows = []
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        for number, line in enumerate(stream, start=1):
            row = json.loads(line)
            if not isinstance(row, dict) or set(row) != ROW_FIELDS:
                raise ValueError(f"第 {number} 行字段集合变化；先审查信息权限")
            if row["peer"] not in PEERS or row["actor"] not in ("peer", "us"):
                raise ValueError(f"第 {number} 行强手或座位类别变化")
            if row["actual"] not in ("claim", "pass", "timeout"):
                raise ValueError(f"第 {number} 行官方响应类别变化")
            if row["phase"] not in ("response_peng", "response_chi"):
                raise ValueError(f"第 {number} 行响应阶段变化")
            if type(row["own_meld_count"]) is not int or row["own_meld_count"] < 0:
                raise ValueError(f"第 {number} 行本人既有副露组数无效")
            rows.append(row)
    if len(rows) != 10_366 or len({key(row) for row in rows}) != len(rows):
        raise ValueError("G76 行数或响应阶段唯一性漂移")
    return rows


def relation(claim_width: object, pass_width: object) -> str:
    """公开有效张容量只作宽度指纹；缺失与非有限值保留未知。"""
    if (type(claim_width) not in (int, float) or
            type(pass_width) not in (int, float) or
            not math.isfinite(claim_width) or not math.isfinite(pass_width)):
        return "unknown"
    if claim_width > pass_width:
        return "greater"
    if claim_width < pass_width:
        return "smaller"
    return "equal"


def by_peer(rows: list[dict]) -> dict:
    """汇总每位强手的跨房支持，不把窗口数当独立桌赛样本。"""
    result = {}
    for peer in PEERS:
        selected = [row for row in rows if row["peer"] == peer]
        result[peer] = {
            "windows": len(selected),
            "rooms": len({row["room"] for row in selected}),
            "games": len({row["game_id"] for row in selected}),
            "by_phase": dict(sorted(Counter(row["phase"] for row in selected).items())),
            "by_prior_meld_count": dict(sorted((str(k), v) for k, v in
                Counter(row["own_meld_count"] for row in selected).items())),
            "by_claim_type": dict(sorted(Counter(
                row["accepted_key"].split(":", 1)[0] for row in selected).items())),
            "parent_best_claim_width_vs_pass": dict(sorted(Counter(relation(
                row["claim_width"], row["pass_width"]) for row in selected).items())),
            "parent_best_claim_same_combined_shanten": sum(
                type(row["claim_shanten"]) is int and
                row["claim_shanten"] == row["pass_shanten"] for row in selected),
            "window_keys_sha256": stable_key_digest(selected),
        }
    return result


def main() -> None:
    """输出只含 G76 行内选择计数和窗口键，不产生候选或收益判断。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=SOURCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    rows = read_rows(args.source)
    unique = [row for row in rows if row["actor"] == "peer" and
              row["actual"] == "claim" and row["parent_key"] == "pass" and
              row["r6_key"] == "pass"]
    support = [row for row in unique if row["own_meld_count"] > 0]
    controls = [row for row in rows if row["actor"] == "peer" and
                row["peer"] == "xuanwu_2346" and row["actual"] == "pass" and
                row["own_meld_count"] > 0]
    strict_controls = [row for row in controls if row["parent_key"] == "pass" and
                       row["r6_key"] == "pass"]
    peer_exposed = [row for row in rows if row["actor"] == "peer" and
                    row["own_meld_count"] > 0]
    if (len(unique) != 88 or Counter(row["peer"] for row in unique) !=
            {"xuanwu_2346": 49, "tengshe_0638": 39} or
            len(support) != 52 or Counter(row["peer"] for row in support) !=
            {"xuanwu_2346": 27, "tengshe_0638": 25} or
            len(controls) != 406 or len(strict_controls) != 366):
        raise ValueError("G76 独有鸣牌或玄武明确过牌支持域漂移")
    if any(row["accepted_key"].split(":", 1)[0] not in ("chi", "peng") or
           row["phase"] != "response_" + row["accepted_key"].split(":", 1)[0]
           for row in unique):
        raise ValueError("独有动作与吃碰阶段不一致")

    timeout = [row for row in peer_exposed if row["peer"] == "tengshe_0638" and
               row["actual"] == "timeout"]
    tengshe_pass = [row for row in peer_exposed if row["peer"] == "tengshe_0638" and
                    row["actual"] == "pass"]
    if tengshe_pass:
        raise ValueError("腾蛇出现主动过牌；旧负控边界需重审")
    result = {
        "schema": "g273-exposed-response-support/1",
        "source": "G76 已确认开启且生产规则合法的行动前响应阶段行",
        "source_gzip_sha256": digest(args.source),
        "script_sha256": digest(Path(__file__)),
        "selection": {
            "unique_claim": "actor=peer, actual=claim, parent_key=pass, r6_key=pass",
            "exposed_support": "unique_claim 且 own_meld_count>0",
            "negative_control": "peer=xuanwu_2346, actor=peer, actual=pass, own_meld_count>0",
        },
        "source_rows": len(rows),
        "unique_claim": {"windows": len(unique), "by_peer": by_peer(unique)},
        "exposed_support": {
            "windows": len(support),
            "physical_rooms": len({row["room"] for row in support}),
            "peer_room_units": len({(row["peer"], row["room"]) for row in support}),
            "by_peer": by_peer(support),
            "window_keys": [dict(zip(KEY_FIELDS, key(row))) for row in
                            sorted(support, key=key)],
        },
        "negative_control": {
            "xuanwu_explicit_pass_exposed": len(controls),
            "xuanwu_explicit_pass_rooms": len({row["room"] for row in controls}),
            "xuanwu_parent_pass": sum(row["parent_key"] == "pass" for row in controls),
            "xuanwu_r6_pass": sum(row["r6_key"] == "pass" for row in controls),
            "xuanwu_strict_parent_r6_pass": len(strict_controls),
            "xuanwu_strict_window_keys_sha256": stable_key_digest(strict_controls),
            "xuanwu_by_phase": dict(sorted(Counter(
                row["phase"] for row in controls).items())),
            "xuanwu_window_keys_sha256": stable_key_digest(controls),
            "tengshe_explicit_pass_exposed": len(tengshe_pass),
            "tengshe_timeout_exposed": len(timeout),
            "tengshe_timeout_is_negative_label": False,
        },
        "boundary": (
            "本脚本只读 G76 的行动前行；own_meld_count>0 包括规则计数中的吃、碰、杠固定面子，"
            "压缩行不含面子种类，不能再细分。G76 已核合法性在此继承而非重跑；"
            "claim_shanten/claim_width 属于父代评分最高的合法鸣牌而非必然是强手 accepted_key，"
            "仅作旧指纹，强手实际动作事实必须逐窗重新计算；"
            "未读取赛后积分、未来牌墙或他家暗牌，窗口计数不是因果收益。"
        ),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"output": str(args.output), "unique_claim": len(unique),
                      "exposed_support": len(support), "xuanwu_pass_control": len(controls)},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
