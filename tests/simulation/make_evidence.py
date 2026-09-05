#!/usr/bin/env python3
"""样例产物生成器（可追溯证据）：单局模拟导出 → tests/simulation/evidence/。

用法：.venv/bin/python tests/simulation/make_evidence.py
输出：tests/simulation/evidence/sample-hand-20260905.json 与终端 SHA-256。
固定 seed=20260905、scenario=sample-scenario、match=sample-match、1 局；
产物含 round_ended（增量 scores）+ game_ended（累计 final_scores，seat=-1）。
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[2] / "src"
_TESTS = Path(__file__).resolve().parents[1]
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))
if str(_TESTS) not in sys.path:
    sys.path.insert(0, str(_TESTS))

from hangma_bot.simulation import SimulationEngine, compute_rules_hash
from simulation._helpers import make_rules, make_spec, simple_chooser, drive


def main() -> None:
    rules = make_rules()
    engine = SimulationEngine(rules, rules_hash=compute_rules_hash(_SRC.parent))
    spec = make_spec(
        rules, rounds=1, seed=20260905,
        scenario_id="sample-scenario", match_id="sample-match",
    )
    world = drive(engine, engine.start(spec), simple_chooser(rules))
    row = engine.export_hand(world, 1)
    # 摘要必须对实际落盘的字节计算（曾出现 sort_keys 变体算摘要、未排序变体写盘的证据链缺陷）
    payload = json.dumps(row, ensure_ascii=False, indent=1).encode("utf-8")
    digest = hashlib.sha256(payload).hexdigest()
    out_dir = _TESTS / "simulation" / "evidence"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "sample-hand-20260905.json"
    out_path.write_bytes(payload)
    # 读回自校验：落盘字节与声明摘要必须一致，否则本脚本立即失败
    assert hashlib.sha256(out_path.read_bytes()).hexdigest() == digest, "证据哈希与落盘字节不一致"
    print("written:", out_path)
    print("sha256 :", digest)
    print("events :", len(row["events"]), "is_draw:", row["is_draw"],
          "last_event:", row["events"][-1]["type"] if row["events"] else None)


if __name__ == "__main__":
    main()
