#!/usr/bin/env python3
"""G33：仅盘点 GLM 答卷与合同，不把文本有效误认为算法有效。"""

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

from collections import Counter
import hashlib
import json
from pathlib import Path

import g33_glm_breadth_pilot as pilot


OUT = pilot.OUT / "inventory.json"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    """要求所有预登记卡均有终态，输出可审的人工作业清单。"""

    if OUT.exists():
        raise SystemExit("G33 答卷盘点已存在，拒绝覆盖")
    counts = Counter()
    rows = []
    for key in pilot.CARDS:
        call = pilot.OUT / f"{key}.call.json"
        answer = pilot.OUT / f"{key}.answer.txt"
        if not call.exists() or not answer.exists():
            raise ValueError("G33 未完成的任务卡：" + key)
        record = json.loads(call.read_text(encoding="utf-8"))
        if record["answer_sha256"] != sha(answer):
            raise ValueError("G33 答卷摘要漂移：" + key)
        answer_text = answer.read_text(encoding="utf-8")
        try:
            parsed_text = json.loads(answer_text.strip())
            text_json_complete = True
        except json.JSONDecodeError:
            parsed_text = None
            text_json_complete = False
        counts["calls"] += 1
        counts["call_success"] += int(record["exit_code"] == 0)
        counts["contract_valid"] += int(record["valid_json_contract"] is True)
        counts["nonempty_failed_answer"] += int(record["exit_code"] != 0 and bool(answer_text.strip()))
        row = {"key": key, "exit_code": record["exit_code"],
               "failure_kind": record["failure_kind"],
               "valid_json_contract": record["valid_json_contract"],
               "answer_sha256": sha(answer), "answer_chars": len(answer_text),
               "text_json_complete": text_json_complete,
               "elapsed_seconds": record["elapsed_seconds"],
               "diagnostic_bytes": record["diagnostic_bytes"], "hypotheses": []}
        if record["valid_json_contract"] is True:
            value = parsed_text
            for index, item in enumerate(value["hypotheses"], 1):
                counts["hypotheses"] += 1
                row["hypotheses"].append({"index": index,
                                          "name": item["name"],
                                          "mechanism_chars": len(str(item["mechanism"])),
                                          "pseudocode_chars": len(str(item["bounded_pseudocode"])),
                                          "falsification_chars": len(str(item["falsification_gate"]))})
        rows.append(row)
    result = {"schema": "g33-author-inventory/1", "counts": dict(counts),
              "manifest_sha256": sha(pilot.OUT / "manifest.json"),
              "source_sha256": sha(Path(__file__)), "rows": rows,
              "boundary": "只数文本与机器合同；未核规则、数学、可编码、独有行为或收益。"}
    OUT.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                   encoding="utf-8")
    print(json.dumps(result["counts"], ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
