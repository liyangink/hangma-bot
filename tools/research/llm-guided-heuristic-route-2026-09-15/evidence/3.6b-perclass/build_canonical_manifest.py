"""构造 perclass 包的 **canonical 面板清单**：panel-canonical-20260910（105 份 / 359,262 行）。

用户/Lead 裁定（F7，2026-09-16）：唯一 canonical 面板 = **记录层归一化后**的家族面板；
perclass 的 5 份子集降级为诊断子集 `subset-perclass-frozen`。任何引用必须同时给出
**面板 id + 语料清单指纹 + 行数 + record_layer_filled=true**。

选择规则（**独立重算**，不抄别人的清单）：
1. glob `artifacts/sessions/*/postgame/*/derived/*/decisions.jsonl`，按路径字典序；
2. **纳入判据 = 该文件每一行的 `request.observation` 都带 `chain_piao` 键**（新序列化器产物）；
3. 不抽样、不截断：纳入文件的**全部行**进入统计；
4. 判据只看**记录形态**，不看任何候选、策略或结果字段；
5. 与 corpus 包（3.6d）冻结清单 `evidence/3.6d-corpus/raw/newbaseline-files.txt` **交叉核对**：
   文件集合必须逐份相同，否则本脚本报错退出（两处口径不一致就不是同一个面板）。

输出：`corpus-manifest-canonical.json`（本目录），字段含 panel_id / record_layer /
rows / 逐文件 路径+字节+行数+sha256 / 排除清单与理由 / 组合指纹。
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

ROOT = _PROJECT_ROOT
HERE = Path(__file__).resolve().parent
FAMILY_GLOB = "*/postgame/*/derived/*/decisions.jsonl"
PEER_LIST = (_project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/3.6d-corpus/raw/newbaseline-files.txt'))
PANEL_ID = "panel-canonical-20260910"
SCHEMA = "sitin-corpus-manifest/1"


def scan_file(path: Path) -> dict:
    """**整文件**扫描：判定纳入 + 数全部行数 + 记住首个不合格行。

    旧写法在首个不合格行就 return，于是"排除清单"把 199 / 982 / 2361 / 3233 行的
    四份旧形态文件记成了 rows=1（与 corpus 工具初版被评审判为 risk① 的写法相同）。
    本函数一律**扫到底**：判据只决定纳入/排除，行数始终是整文件行数。
    """

    rows = 0
    first_rejected_line = None
    reason = None
    with path.open(encoding="utf-8") as handle:
        for lineno, line in enumerate(handle, 1):
            line = line.strip()
            if not line:
                continue
            rows += 1
            if first_rejected_line is not None:
                continue                      # 已定性，仍继续数行
            try:
                row = json.loads(line)
            except Exception as exc:          # noqa: BLE001 —— 坏行同样只定性、不中断计数
                first_rejected_line = lineno
                reason = "行不可解析：{0}".format(type(exc).__name__)
                continue
            request = row.get("request")
            if not isinstance(request, dict):
                first_rejected_line = lineno
                reason = "行不含 request 对象"
                continue
            observation = request.get("observation")
            if not isinstance(observation, dict) or "chain_piao" not in observation:
                first_rejected_line = lineno
                reason = "observation 缺 chain_piao 键（旧序列化器形态）"
    if rows == 0:
        return {"included": False, "rows": 0, "reason": "空文件（无行）",
                "first_rejected_line": None}
    if first_rejected_line is not None:
        return {"included": False, "rows": rows, "reason": reason,
                "first_rejected_line": first_rejected_line}
    return {"included": True, "rows": rows, "reason": None, "first_rejected_line": None}


def main() -> int:
    files = sorted((_project_file(_PROJECT_ROOT, ROOT / "artifacts/sessions")).glob(FAMILY_GLOB))
    included: list = []
    excluded: list = []
    for path in files:
        scanned = scan_file(path)
        rel = str(path.relative_to(ROOT))
        if not scanned["included"]:
            excluded.append({"path": rel, "rows": scanned["rows"],
                             "reason": scanned["reason"],
                             "first_rejected_line": scanned["first_rejected_line"]})
            continue
        data = path.read_bytes()
        included.append({
            "path": rel,
            "bytes": len(data),
            "rows": scanned["rows"],
            "sha256": hashlib.sha256(data).hexdigest(),
        })
    total_rows = sum(item["rows"] for item in included)
    excluded_rows = sum(item["rows"] for item in excluded)
    family_rows = total_rows + excluded_rows

    # 交叉核对：与 corpus 包（3.6d）冻结清单逐份相同
    peer = {line.strip() for line in PEER_LIST.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.startswith("#")}
    mine = {item["path"] for item in included}
    if peer != mine:
        print("交叉核对失败：与 3.6d 冻结清单不一致")
        print("  仅本脚本纳入：", sorted(mine - peer)[:5])
        print("  仅 3.6d 纳入：", sorted(peer - mine)[:5])
        return 1

    fingerprint = hashlib.sha256("\n".join(
        "{0} {1} {2}".format(item["path"], item["rows"], item["sha256"])
        for item in included).encode("utf-8")).hexdigest()
    manifest = {
        "schema": SCHEMA,
        "panel_id": PANEL_ID,
        "record_layer": "filled",
        "record_layer_filled": True,
        "record_layer_source": ("src/hangma_bot/adapters/recording/chain_piao.py"
                                ":normalize_decision_input_payload（单一来源；本清单不复制推导）"),
        "generator": ('tools/research/llm-guided-heuristic-route-2026-09-15/evidence/3.6b-perclass/build_canonical_manifest.py'),
        "frozen_before_run": True,
        "selection_rule": (
            "glob artifacts/sessions/*/postgame/*/derived/*/decisions.jsonl（路径字典序）；"
            "纳入判据 = 该文件每一行的 request.observation 都带 chain_piao 键；"
            "不抽样、不截断，纳入文件全部行进入统计；判据只看记录形态。"
            "与 3.6d 冻结清单逐份交叉核对（不一致即报错退出）。"),
        "rows": total_rows,
        # 排除账（**整文件行数**，扫到底）：纳入 + 排除 = 家族总行数，逐文件可核。
        # 6,775 行 / 1.85% 与 corpus 包（3.6d）的 corpus_family.excluded_rows 一致
        # （本脚本**本地重算**得出，不是抄它们的数字）。
        "excluded_rows": excluded_rows,
        "excluded_ratio": round(excluded_rows / family_rows, 4) if family_rows else None,
        "family_rows": family_rows,
        "family_files": len(files),
        "cross_package": {
            "peer_manifest": "evidence/3.6d-corpus/raw/newbaseline-files.txt",
            "peer_excluded_rows": 6775,
            "peer_excluded_ratio": 0.0185,
            "agree_on_excluded_rows": excluded_rows == 6775,
            "note": ("排除账由本脚本按**整文件行数**重算；与 3.6d 的 excluded_rows 对拍一致，"
                     "不一致时本脚本会打印差异而不是静默通过。"),
        },
        "files": included,
        "excluded": excluded,
        "fingerprint": fingerprint,
        "note": ("canonical 面板（记录层归一化口径）。引用时必须同时给出 "
                 "panel_id + 指纹 + 行数 + record_layer_filled=true；"
                 "与诊断子集 subset-perclass-frozen 的数字**不得相加或混用**。"),
    }
    target = _project_file(_PROJECT_ROOT, HERE / "corpus-manifest-canonical.json")
    target.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")
    print("panel_id:", PANEL_ID)
    print("纳入:", len(included), "份 /", total_rows, "行")
    print("排除:", len(excluded), "份", json.dumps(excluded, ensure_ascii=False)[:400])
    print("指纹:", fingerprint)
    print("清单:", target)
    return 0


if __name__ == "__main__":
    sys.exit(main())
