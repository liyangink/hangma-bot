"""交叉核对 G103/G104 父代实战的高番入口覆盖，不估计候选收益。"""

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

import gzip
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path


BASE = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence')
G103 = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g103-official-route-horizon-20260928')
G104 = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g104-post-root-claim-route-20260928')
OUTPUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g105-route-state-cross-audit-20260928/result.json')


def sha256(path: Path) -> str:
    """返回原始证据文件摘要，避免跨批次误拼。"""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_rows(path: Path) -> list[dict]:
    """读取压缩 JSONL；每行保持原始官方单局或行动键。"""
    with gzip.open(path, "rt", encoding="utf-8") as source:
        return [json.loads(line) for line in source]


def main() -> None:
    """以单局首冲突为单位核对三类合法行动入口。"""
    root_path = _project_file(_PROJECT_ROOT, G103 / "rows.jsonl.gz")
    claim_path = _project_file(_PROJECT_ROOT, G104 / "rows.jsonl.gz")
    claim_result_path = _project_file(_PROJECT_ROOT, G104 / "result.json")
    roots = read_rows(root_path)
    claims = read_rows(claim_path)
    claim_result = json.loads(claim_result_path.read_text(encoding="utf-8"))

    by_key: dict[tuple[str, int, int], dict] = {}
    for root in roots:
        key = (root["key"][1], root["key"][2], root["seat"])
        if key in by_key:
            raise ValueError(f"重复单局首冲突：{key}")
        by_key[key] = root
    claim_by_key: dict[tuple[str, int, int], list[dict]] = defaultdict(list)
    for claim in claims:
        key = (claim["game_id"], claim["round_no"], claim["seat"])
        if key not in by_key:
            raise ValueError(f"鸣牌超出固定根：{key}")
        claim_by_key[key].append(claim)

    gang_direct: set[tuple[str, int, int]] = set()
    for item in claim_result["previously_missing_high_wins"]:
        if not item["gang_immediate_win"]:
            continue
        matching = [root for root in roots if root["key"] == item["key"]]
        if len(matching) != 1:
            raise ValueError(f"杠开根不唯一：{item['key']}")
        root = matching[0]
        gang_direct.add((root["key"][1], root["key"][2], root["seat"]))

    total = Counter()
    by_white: dict[str, Counter] = defaultdict(Counter)
    by_shanten: dict[str, Counter] = defaultdict(Counter)
    by_outcome: dict[str, Counter] = defaultdict(Counter)

    for key, root in by_key.items():
        normal = root["first_entry_ordinal"]["high"] is not None
        claim = any(
            event.get("entry") is not None
            and event["entry"]["high_capacity"] > 0
            for event in claim_by_key[key]
        )
        gang = key in gang_direct
        route = normal or claim or gang
        high_win = root["outcome"] == "self_win" and (root["terminal_fan"] or 0) >= 2
        if high_win and not route:
            raise ValueError(f"高番实胡没有可核对入口：{key}")
        white = "0" if root["white_before"] == 0 else "1" if root["white_before"] == 1 else "2+"
        for counts in (total, by_white[white], by_shanten[str(root["shanten"])], by_outcome[root["outcome"]]):
            counts["hands"] += 1
            counts["normal_high_entry"] += normal
            counts["post_claim_high_entry"] += claim
            counts["gang_replenish_direct_high_win"] += gang
            counts["any_high_route"] += route
            counts["self_high_win"] += high_win
            counts["normal_and_claim_overlap"] += normal and claim

    if total["hands"] != 170 or len(claims) != 60 or total["self_high_win"] != 10:
        raise ValueError("G103/G104 冻结样本规模变化，需重新审计")
    result = {
        "schema": "g105-route-state-cross-audit/1",
        "boundary": "G103 170 个首冲突单局的父代实战；非备选动作收益或独立确认",
        "inputs_sha256": {
            "g103_rows": sha256(root_path),
            "g104_rows": sha256(claim_path),
            "g104_result": sha256(claim_result_path),
        },
        "claim_events": len(claims),
        "total": dict(total),
        "by_root_white_count": {key: dict(value) for key, value in sorted(by_white.items())},
        "by_root_standard_shanten": {key: dict(value) for key, value in sorted(by_shanten.items())},
        "by_terminal_outcome": {key: dict(value) for key, value in sorted(by_outcome.items())},
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result["total"], ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
