"""canonical 面板配额**元数据刷新**（秒级；不重跑窗口级扫描）。

为什么需要它：canonical 覆盖账的窗口级数字（行 359,262 / 计分 338,018 / 四态 19-1-8-0）
由一次 ~17 分钟的扫描产出；而本轮只改了清单的**排除账元数据**（整文件行数 6,775）。
按 Lead 作业纪律（2026-09-16）：口径/命名对齐**不得**触发全量重算 ⇒ 这里只把清单台账
（排除行数 / 比例 / 清单哈希）刷进已有产物，并**断言面板内容指纹未变**（否则拒绝刷新，
要求重跑全量）。

安全阀：内容指纹（105 份文件的 sha256 组合）与行数**任一变化**即 exit 2，不做任何写入。
"""
from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/llm-guided-heuristic-route-2026-09-15/evidence/3.6b-perclass'

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
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PANEL = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/3.6b-perclass/corpus-manifest-canonical.json')
TARGET = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/3.6b-perclass/canonical/coverage.json')


def main() -> int:
    manifest = json.loads(PANEL.read_text(encoding="utf-8"))
    coverage = json.loads(TARGET.read_text(encoding="utf-8"))
    before = dict(coverage["input"].get("panel_identity") or {})
    # 安全阀：面板内容（指纹 + 行数）必须与产物里记录的一致
    if before.get("fingerprint") != manifest.get("fingerprint") or \
            before.get("rows") != manifest.get("rows"):
        print("拒绝刷新：面板内容指纹或行数与产物不一致（需要重跑全量）")
        print("  产物:", before.get("fingerprint"), before.get("rows"))
        print("  清单:", manifest.get("fingerprint"), manifest.get("rows"))
        return 2
    after = dict(before)
    after.update({
        "fingerprint_basis": "清单内 105 份文件的 sha256 组合（内容口径，不含清单元数据）",
        "manifest_sha256": hashlib.sha256(PANEL.read_bytes()).hexdigest(),
        "excluded_rows": manifest.get("excluded_rows"),
        "excluded_ratio": manifest.get("excluded_ratio"),
        "family_rows": manifest.get("family_rows"),
        "family_files": manifest.get("family_files"),
    })
    coverage["input"]["panel_identity"] = after
    coverage["input"]["manifest"] = {
        key: manifest.get(key) for key in (
            "schema", "panel_id", "panel_role", "record_layer", "record_layer_filled",
            "record_layer_source", "fingerprint", "row_cap", "rows", "excluded_rows",
            "excluded_ratio", "family_rows", "family_files", "selection_rule",
            "frozen_before_run", "generator", "cross_package", "note")}
    TARGET.write_text(json.dumps(coverage, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    changed = sorted(key for key in set(before) | set(after) if before.get(key) != after.get(key))
    print("已刷新（秒级，未重跑扫描）：", TARGET.relative_to(HERE.parents[0]) if False else TARGET)
    print("变更字段：", changed)
    print("面板内容指纹（未变）：", after["fingerprint"])
    print("排除账：", after["excluded_rows"], "行 /", after["excluded_ratio"])
    print("窗口级数字（未动）：行", coverage["panel"]["rows_total"],
          "/ 计分", coverage["panel"]["scored"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
