"""perclass 包的**语料选择**脚本：先冻结规则，再运行（用户 2026-09-16 裁定）。

用户裁定：语料基线换新（旧 auto-match-2026-09-06 3343 行、public_history 全空、
无 chain_piao，降级为历史对照样本）。新基线 = artifacts/sessions/*/postgame/*/derived/*/decisions.jsonl 家族。

**选择规则（本脚本写死，运行时不得按候选表现调整）**：

1. 根：artifacts/sessions/*/postgame/*/derived/*/decisions.jsonl（全家族枚举）；
2. 只保留**会话目录名以 auto-match- 开头**者：真实自动对战分布；
   排除 test-room-*（测试房间）与 adapter-*（协议验收）会话；
3. 只取 **postgame 时间戳以 20260910T 开头**者（09-10 批 = 最新一天）；
4. 按**路径字符串升序**排序（确定性；会话 id 是哈希，与内容无关 ⇒ 等价于按会话随机取，
   不是按候选表现挑）；
5. 从上往下取**整份文件**，直到"再取一份就会使累计行数超过 ROW_CAP=20000"为止
   （**不拆文件**：每份 = 一局完整记录，避免半局）；
6. 落盘清单：逐文件 路径 / 字节 / 行数 / sha256 / 累计行数，外加**被排除清单与理由**，
   以及全家族的按天/按前缀分布（供复核"新基线不是手挑的"）。

输出：
  evidence/3.6b-perclass/corpus-manifest.json   —— 机读清单（工具直接吃它）
  evidence/3.6b-perclass/CORPUS-SELECTION.md    —— 人读选择说明（含全家族分布）
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
import subprocess
import sys
from pathlib import Path

ROW_CAP = 20000
SCHEMA = "sitin-corpus-manifest/1"
ROOT = _PROJECT_ROOT          # 仓库根
HERE = Path(__file__).resolve().parent
FAMILY_GLOB = "*/postgame/*/derived/*/decisions.jsonl"
DAY_PREFIX = "20260910T"
SESSION_PREFIX = "auto-match-"


def family_files() -> list:
    return sorted((_project_file(_PROJECT_ROOT, ROOT / "artifacts/sessions")).glob(FAMILY_GLOB))


def row_counts(paths: list) -> dict:
    """用 wc -l 一次数完（JSONL 一行 = 一条决策记录）；只看行数，不解析内容。

    **必须丢掉 wc 的汇总行**（返工修复，Challenger risk ②）：多文件调用时 wc -l 会追加一行
    "<总量> total"，把它当成第 N+1 个"文件"会让家族总行数**精确放大 2 倍**
    （实测 732,074 = 2 × 366,037）。修法：只接受能对上真实文件名的行，且**逐文件回填**校验
    （缺任何一份就报错，绝不静默当 0）。
    """

    if not paths:
        return {}
    out = subprocess.run(["wc", "-l", *[str(p) for p in paths]],
                         capture_output=True, text=True, check=True)
    known = {str(p) for p in paths}
    counts: dict = {}
    for line in out.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        count, _, name = line.rpartition(" ")
        name = name.strip()
        if name not in known:                     # 汇总行（total）或任何非文件名的行：丢弃
            continue
        counts[name] = int(count)
    missing = sorted(item for item in known if item not in counts)
    if missing:
        raise RuntimeError("wc -l 未回填这些文件：{0}".format(missing[:5]))
    return counts


def main() -> int:
    files = family_files()
    counts = row_counts(files)
    by_day: dict = {}
    by_prefix: dict = {}
    for path in files:
        by_day.setdefault(path.parts[-4][:8], []).append(str(path.relative_to(ROOT)))
        by_prefix.setdefault(path.parts[-6].split("-")[0], []).append(
            str(path.relative_to(ROOT)))

    candidates = [p for p in files
                  if p.parts[-6].startswith(SESSION_PREFIX) and p.parts[-4].startswith(DAY_PREFIX)]
    selected: list = []
    cumulative = 0
    stopped_at = None
    for path in candidates:
        rows = counts.get(str(path), 0)
        if selected and cumulative + rows > ROW_CAP:
            stopped_at = str(path.relative_to(ROOT))
            break
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        cumulative += rows
        selected.append({
            "path": str(path.relative_to(ROOT)),
            "bytes": path.stat().st_size,
            "rows": rows,
            "sha256": digest,
            "cumulative_rows": cumulative,
        })
        if cumulative >= ROW_CAP:
            break

    chosen = {item["path"] for item in selected}
    excluded = []
    for path in files:
        rel = str(path.relative_to(ROOT))
        if not path.parts[-6].startswith(SESSION_PREFIX):
            reason = "非 auto-match 会话（测试房间 / 协议验收）"
        elif not path.parts[-4].startswith(DAY_PREFIX):
            reason = "不在 09-10 批（本包只取最新一天，规则先于运行冻结）"
        elif rel not in chosen:
            reason = "排序在截断点之后（累计行数已达/将超上限 {0}）".format(ROW_CAP)
        else:
            continue
        excluded.append({"path": rel, "rows": counts.get(str(path), 0), "reason": reason})

    manifest = {
        "schema": SCHEMA,
        # **诊断子集**（F7 裁定，2026-09-16）：只用于逐类账与工具自检；
        # 不得作为 scorer/condition/overall 的分母或效果口径，也不得与 canonical 面板混用。
        "panel_id": "subset-perclass-frozen",
        "panel_role": "diagnostic-subset",
        "record_layer": "raw",
        "canonical_panel": {
            "panel_id": "panel-canonical-20260910",
            "manifest": "corpus-manifest-canonical.json",
            "rows": 359262,
            "record_layer_filled": True,
            "note": ("唯一 canonical 面板（记录层归一化）。本子集的数字**不得**与它相加或混用；"
                     "引用时必须各自写明面板 id 与是否归一化。"),
        },
        "generator": ('tools/research/llm-guided-heuristic-route-2026-09-15/evidence/3.6b-perclass/select_corpus.py'),
        "frozen_before_run": True,
        "selection_rule": (
            "会话目录名以 auto-match- 开头 ∧ postgame 时间戳以 20260910T 开头；"
            "按路径字符串升序；整份文件取到累计行数 <= row_cap 为止（不拆文件）。"
            "规则写死在 select_corpus.py 里，运行前冻结，不按候选表现挑语料。"),
        "row_cap": ROW_CAP,
        "day": DAY_PREFIX,
        "session_prefix": SESSION_PREFIX,
        "rows": cumulative,
        "files": selected,
        "excluded": excluded,
        "family": {
            "files": len(files),
            "rows": sum(counts.values()),
            "by_day": {day: len(items) for day, items in sorted(by_day.items())},
            "by_session_prefix": {key: len(items) for key, items in sorted(by_prefix.items())},
        },
        "note": ("本清单只选语料，不选候选：选择规则与候选表现无关。"
                 "工具通过 sitin_gates.corpus_manifest() 读它，身份 = 清单文件哈希。"),
    }
    target = _project_file(_PROJECT_ROOT, HERE / "corpus-manifest.json")
    target.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")

    lines = [
        "# perclass 包的语料选择（先冻结规则、后运行）",
        "",
        "> 由 [select_corpus.py](./select_corpus.py) 生成；工具侧读取口径见",
        "> [tools/sitin_gates.py](../../tools/sitin_gates.py) 的 CORPUS_MANIFEST_SCHEMA。",
        "",
        "## 0. 面板身份与 canonical 的关系（Lead 裁定 F7，2026-09-16）",
        "",
        "| 项 | 值 |",
        "| --- | --- |",
        "| 本清单 panel_id | **subset-perclass-frozen**（角色：诊断子集） |",
        "| 本清单指纹（文件 sha256） | 见 [corpus-manifest.json](./corpus-manifest.json) 的清单哈希 |",
        "| 本清单行数 | {0} |".format(cumulative),
        "| 本清单 record_layer | **raw**（记录原样；不作为效果口径） |",
        "| 唯一 canonical 面板 | **panel-canonical-20260910**（105 份 / 359,262 行，record_layer_filled=true） |",
        "| canonical 清单 | [corpus-manifest-canonical.json](./corpus-manifest-canonical.json) |",
        "",
        "**边界**：本子集只用于**逐类账与工具自检**；不得作为 scorer / condition / overall 的分母或效果口径，",
        "也不得与 canonical 面板的数字相加或混用。任何引用必须写明「面板 id + 是否归一化」。",
        "",
        "### 0.1 记录层前后的四个量（命名与 corpus 3.6d 对齐；canonical 面板口径）",
        "",
        "| 量 | 值 | 判据 |",
        "| --- | --- | --- |",
        "| `newly_attributable` | 21 | 行侧：`raw chain_piao is None ∧ filled is not None` |",
        "| `newly_scored` | **14** | 分母侧：修前被规则层降级排除 ∧ 修后进入计分（**由引擎判据得出的唯一分母口径**） |",
        "| `still_unknown` | 5 | 修后仍不可归因且 `chain_count>0`（逐行列明，不并入分母） |",
        "| `net_usable_window_delta` | +16 | 链族可用窗口差（= 已知数净差；**不得**当作新可判窗口数或新计分窗口数） |",
        "",
        "派生：`attributable_but_still_excluded = 21 − 14 = 7`（已可归因但仍被其他规则排除）。",
        "历史注记：corpus 侧初版把该净差命名为 `newly_decidable_windows=16`（已于提交 cb3a3c38 删除，其值实为净差而非新可判窗口数）；引用一律用 `net_usable_window_delta`。",
        "机读与逐行样本见 [raw/51-newly-decidable.json](./raw/51-newly-decidable.json) 的 `reconciliation` 块；",
        "**本包一律以 14（分母口径）为准**，引用 16 时必须写明它是净差。",
        "",
        "### 0.2 排除账（整文件行数，扫到底）",
        "",
        "| 项 | 值 |",
        "| --- | --- |",
        "| canonical 纳入 | 105 份 / 359,262 行 |",
        "| canonical 排除 | 7 份 / **6,775 行（1.85%）**（四份旧形态 199/982/2,361/3,233 行 + 三份空文件） |",
        "| 家族合计 | 112 份 / 366,037 行（= 纳入 + 排除） |",
        "| 来源 | 本包**本地重算**，与 3.6d 的 `corpus_family.excluded_rows=6,775` 对拍一致 |",
        "",
        "## 1. 规则（写死在脚本里，运行前冻结）",
        "",
        "1. 根：artifacts/sessions/*/postgame/*/derived/*/decisions.jsonl；",
        "2. 会话目录名以 auto-match- 开头（排除 test-room-* / adapter-*）；",
        "3. postgame 时间戳以 {0} 开头（09-10 批 = 最新一天）；".format(DAY_PREFIX),
        "4. 按路径字符串**升序**（会话 id 是哈希 ⇒ 等价于按会话随机取）；",
        "5. 整份文件取到累计行数 <= row_cap={0} 为止（**不拆文件**）；".format(ROW_CAP),
        "6. 清单与被排除清单一起落盘。",
        "",
        "## 2. 全家族分布（复核「新基线不是手挑的」）",
        "",
        "| 项 | 值 |",
        "| --- | --- |",
        "| 家族文件数 | {0} |".format(len(files)),
        "| 家族总行数 | {0} |".format(sum(counts.values())),
        "| 按天（文件数） | {0} |".format(
            ", ".join("{0}: {1}".format(day, len(items))
                      for day, items in sorted(by_day.items()))),
        "| 按会话前缀（文件数） | {0} |".format(
            ", ".join("{0}: {1}".format(k, len(v)) for k, v in sorted(by_prefix.items()))),
        "",
        "## 3. 选中子集",
        "",
        "| # | 文件 | 行数 | 累计 | 字节 | sha256（前 12） |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for index, item in enumerate(selected, 1):
        lines.append("| {0} | {1} | {2} | {3} | {4} | {5}… |".format(
            index, item["path"], item["rows"], item["cumulative_rows"], item["bytes"],
            item["sha256"][:12]))
    lines += [
        "",
        "**选中 {0} 份 / {1} 行**（上限 {2}）。".format(len(selected), cumulative, ROW_CAP),
        "",
        "## 4. 被排除的文件",
        "",
        "| 文件 | 行数 | 理由 |",
        "| --- | --- | --- |",
    ]
    for item in excluded:
        lines.append("| {0} | {1} | {2} |".format(item["path"], item["rows"], item["reason"]))
    lines += [
        "",
        "## 5. 边界（必须与结论一起引用）",
        "",
        "1. 本清单**与候选表现无关**：规则先冻结、后运行；换一天或换上限都必须重新落盘。",
        "2. 选中子集是**批内按路径顺序的整份文件**，不是全家族的无偏抽样；",
        "   结论只对该子集成立，不得外推整体发生率。",
        "3. 旧语料 datasets/derived/auto-match-2026-09-06/decisions.jsonl **降级为历史对照样本**，",
        "   只用于 before/after 与回归，不再作为基线。",
    ]
    (_project_file(_PROJECT_ROOT, HERE / "CORPUS-SELECTION.md")).write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("家族: {0} 份 / {1} 行".format(len(files), sum(counts.values())))
    print("候选（auto-match- ∧ 09-10）: {0} 份".format(len(candidates)))
    print("选中: {0} 份 / {1} 行（row_cap={2}）".format(len(selected), cumulative, ROW_CAP))
    print("截断点: {0}".format(stopped_at))
    print("清单: {0}".format(target))
    return 0


if __name__ == "__main__":
    sys.exit(main())
