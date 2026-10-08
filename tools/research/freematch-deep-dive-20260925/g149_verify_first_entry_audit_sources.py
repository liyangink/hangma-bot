#!/usr/bin/env python3
"""G149：核对 G146/G147 逐房来源与 G61/G69 冻结清单完全相同。"""

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

import hashlib
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
G61 = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g61-strong-draw-action-atlas-20260927/result.json')
G69 = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g69-same-room-route-chain-20260928/batch_result.json')
G146 = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g146-first-baotou-wait-capacity-20260928/result.json')
G147 = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g147-one-white-first-ready-wait-20260928/result.json')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g149-first-entry-source-verification-20260928/result.json')


def sha(path: Path) -> str:
    """计算审计器与冻结输入文件的原始字节摘要。"""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    """要求逐房每个实际读取的窗口文件均匹配旧冻结源摘要。"""
    if OUT.exists():
        raise FileExistsError("G149 已有验证结果，拒绝覆盖")
    g61 = json.loads(G61.read_text(encoding="utf-8"))
    g69 = json.loads(G69.read_text(encoding="utf-8"))
    outputs = {"g146": json.loads(G146.read_text(encoding="utf-8")),
               "g147": json.loads(G147.read_text(encoding="utf-8"))}
    checks = {}
    for name, result in outputs.items():
        sources = result["window_source_sha256"]
        if len(sources) < 31 * 2:
            raise ValueError(name + " 逐房来源覆盖不足")
        for identity, observed in sources.items():
            peer, room, actor = identity.split("/")
            if actor == "peer":
                expected = g61["units"][peer + "/" + room]["windows_sha256"]
            elif actor == "us":
                expected = g69["rooms"][room]["windows_sha256"]
            else:
                raise ValueError("未知座位身份：" + identity)
            if observed != expected:
                raise ValueError(name + " 来源摘要漂移：" + identity)
        script = _project_file(_PROJECT_ROOT, HERE / ("g146_first_baotou_wait_capacity_audit.py" if name == "g146"
                         else "g147_one_white_first_ready_wait_audit.py"))
        if result["inputs_sha256"]["script"] != sha(script):
            raise ValueError(name + " 运行脚本摘要与现文件不一致")
        checks[name] = {"source_files": len(sources),
                        "distinct_rooms": len({identity.split("/")[1]
                                               for identity in sources}),
                        "script_sha256": sha(script)}
    result = {"schema": "g149-first-entry-source-verification/1",
              "inputs_sha256": {"g61": sha(G61), "g69": sha(G69),
                                "g146": sha(G146), "g147": sha(G147),
                                "script": sha(Path(__file__))},
              "checks": checks,
              "boundary": "只验证已归档逐房窗口来源与脚本身份；不新增独立房或候选收益。"}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                   encoding="utf-8")
    print(json.dumps(checks, ensure_ascii=False, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
