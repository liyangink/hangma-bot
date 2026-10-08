"""R18 P29c：合并两批结果盲自然暴露并统一拆分开发/复验。

P29 首批 512 桌与 P29b 追加 2,560 桌使用相同公开谓词、不同 panel seed。
本程序在追加批运行前冻结合并门、去重和拆分规则；只读取机会窗口身份与公开
事实，不读取任何动作收益标签。
"""

from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Mapping


HERE = Path(__file__).resolve().parent
ROUTE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15')
ROOT = _PROJECT_ROOT
for path in (_project_file(_PROJECT_ROOT, ROOT / "src"), _project_file(_PROJECT_ROOT, ROUTE / "tools"), HERE):
    sys.path.insert(0, str(path))

import confirmation_execution_identity as guard  # noqa: E402
import r18_p29_multiwhite_baotou_natural_exposure as p29  # noqa: E402
import r18_p29b_multiwhite_baotou_natural_topup as p29b  # noqa: E402
import sitin_search as search  # noqa: E402


OUT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p29c-multiwhite-baotou-exposure-consolidation-01-20260922')
MIXES = ("H", "M")
SEATS = (0, 1, 2, 3)
EXPECTED_TABLES = p29.PLANNED_TABLES + p29b.PLANNED_TABLES
MIN_TOTAL_ROOTS = 24
MIN_ROOTS_PER_MIX = 8
MAX_SELECTED_ROOTS_PER_MIX = 16
SELECTION_SALT = "r18-p29c-multiwhite-baotou-selection/v1"
SPLIT_SALT = "r18-p29c-multiwhite-baotou-split/v1"


def write_json(path: Path, value: Any) -> None:
    """写入稳定 UTF-8 JSON。"""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _hash_order(row: Mapping[str, Any], salt: str) -> str:
    payload = "|".join((
        salt, str(row["source"]["source_root_id"]), str(row["request_sha256"]),
    ))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def prepare() -> None:
    """在 P29b 运行前冻结合并门、两批身份和拆分规则。"""

    if OUT.exists():
        raise SystemExit("P29c 目录已存在；拒绝覆盖")
    if not (p29.OUT / "result.json").is_file():
        raise ValueError("P29 首批结果不存在")
    if not (p29b.OUT / "manifest.json").is_file():
        raise ValueError("P29b 必须先 prepare，再冻结 P29c")
    OUT.mkdir(parents=True)
    tracked = [
        Path(__file__), Path(p29.__file__), Path(p29b.__file__),
        p29.OUT / "manifest.json", p29.OUT / "result.json",
        p29.OUT / "run-summary.json", p29b.OUT / "manifest.json",
        p29.CONTRACT, p29.PARENT,
    ]
    write_json(_project_file(_PROJECT_ROOT, OUT / "manifest.json"), {
        "schema": "r18-p29c-multiwhite-baotou-consolidation-manifest/1",
        "created_at_utc": search.utc_now(),
        "runtime": guard.capture(source_paths=tracked),
        "batches": [
            {
                "name": "P29", "panel_seed": p29.PANEL_SEED,
                "planned_tables": p29.PLANNED_TABLES,
                "manifest_sha256": digest(p29.OUT / "manifest.json"),
            },
            {
                "name": "P29b", "panel_seed": p29b.PANEL_SEED,
                "planned_tables": p29b.PLANNED_TABLES,
                "manifest_sha256": digest(p29b.OUT / "manifest.json"),
            },
        ],
        "expected_tables": EXPECTED_TABLES,
        "frozen_predicate": (
            "draw and exactly_two_wealth and hu_legal and discard_white_legal and "
            "discard_white.baotou_after_is_true and p5_top_is_hu"
        ),
        "independence_unit": "batch+source_root_id；座位与同根两桌不增加n",
        "gate": {
            "minimum_total_roots": MIN_TOTAL_ROOTS,
            "minimum_roots_per_mix": MIN_ROOTS_PER_MIX,
            "required_focal_seats": list(SEATS),
        },
        "maximum_selected_roots_per_mix": MAX_SELECTED_ROOTS_PER_MIX,
        "selection_salt": SELECTION_SALT,
        "split_salt": SPLIT_SALT,
        "split_rule": (
            "每mix按冻结哈希最多选16个偶数根；每mix内部前半development、"
            "后半replication；收益标签均未生成"
        ),
        "outcome_blind": True,
        "replication_labels_opened": False,
        "model_calls": 0,
        "selection_eligible": False,
        "release_eligible": False,
    })
    print(json.dumps({
        "status": "PREPARED", "expected_tables": EXPECTED_TABLES,
        "gate": {"total": MIN_TOTAL_ROOTS, "per_mix": MIN_ROOTS_PER_MIX},
    }, ensure_ascii=False))


def verify() -> dict[str, Any]:
    """核对合并程序、两批冻结清单、合同与 P5 父代未漂移。"""

    manifest = json.loads((_project_file(_PROJECT_ROOT, OUT / "manifest.json")).read_text(encoding="utf-8"))
    guard.verify(manifest["runtime"])
    expected = {
        "P29": digest(p29.OUT / "manifest.json"),
        "P29b": digest(p29b.OUT / "manifest.json"),
    }
    for batch in manifest["batches"]:
        if batch["manifest_sha256"] != expected[batch["name"]]:
            raise ValueError(batch["name"] + " manifest 漂移")
    return manifest


def _load_batch(module: Any, batch_name: str) -> tuple[Counter[str], list[dict[str, Any]]]:
    summary = json.loads((module.OUT / "run-summary.json").read_text(encoding="utf-8"))
    if summary["failures"] or int(summary["actual_tables"]) != module.PLANNED_TABLES:
        raise ValueError(batch_name + " 执行不完整")
    counts: Counter[str] = Counter()
    rows = []
    for source in module.sources():
        document = json.loads(module.source_path(source).read_text(encoding="utf-8"))
        counts.update(document["audit"]["counts"])
        for row in document["audit"]["eligible_rows"]:
            item = dict(row)
            item["exposure_batch"] = batch_name
            rows.append(item)
    return counts, rows


def analyze() -> None:
    """合并、按来源根去重、过门并结果盲拆分。"""

    verify()
    total_counts: Counter[str] = Counter()
    rows_by_root: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    batch_summary = {}
    raw_eligible = 0
    for module, name in ((p29, "P29"), (p29b, "P29b")):
        counts, rows = _load_batch(module, name)
        total_counts.update(counts)
        raw_eligible += int(counts["eligible_exactly_two_wealth_piao_keeps_baotou"])
        for row in rows:
            identity = name + ":" + str(row["source"]["source_root_id"])
            rows_by_root[identity].append(row)
        batch_summary[name] = {
            "tables": module.PLANNED_TABLES,
            "focal_requests": int(counts["focal_requests"]),
            "raw_eligible_windows": int(
                counts["eligible_exactly_two_wealth_piao_keeps_baotou"]
            ),
            "independent_roots": len({
                str(row["source"]["source_root_id"]) for row in rows
            }),
        }

    independent = [
        min(options, key=lambda row: _hash_order(row, SELECTION_SALT))
        for _, options in sorted(rows_by_root.items())
    ]
    pools = {
        mix: sorted(
            (row for row in independent if row["source"]["mix"] == mix),
            key=lambda row: _hash_order(row, SPLIT_SALT),
        )
        for mix in MIXES
    }
    selected_counts = {
        mix: min(MAX_SELECTED_ROOTS_PER_MIX, len(pools[mix])) for mix in MIXES
    }
    selected_counts = {
        mix: count - count % 2 for mix, count in selected_counts.items()
    }
    seat_coverage = sorted({int(row["focal_physical_seat"]) for row in independent})
    passes = (
        sum(selected_counts.values()) >= MIN_TOTAL_ROOTS
        and all(selected_counts[mix] >= MIN_ROOTS_PER_MIX for mix in MIXES)
        and seat_coverage == list(SEATS)
    )
    selected = []
    if passes:
        for mix in MIXES:
            chosen = pools[mix][: selected_counts[mix]]
            for index, row in enumerate(chosen):
                item = dict(row)
                item["split"] = (
                    "development"
                    if index < selected_counts[mix] // 2
                    else "replication"
                )
                selected.append(item)
    selected.sort(key=lambda row: (
        row.get("split", ""), row["source"]["mix"],
        row["exposure_batch"], row["source"]["source_root_id"],
    ))
    dataset = {
        "schema": "r18-p29c-multiwhite-baotou-dataset/1",
        "outcome_blind": True,
        "replication_labels_opened": False,
        "rows": selected,
    }
    result = {
        "schema": "r18-p29c-multiwhite-baotou-consolidation-result/1",
        "status": (
            "OPEN_DEVELOPMENT_CONFIRMATION"
            if passes else "INSUFFICIENT_NATURAL_EXPOSURE_AT_MAX_BUDGET"
        ),
        "tables": EXPECTED_TABLES,
        "batch_summary": batch_summary,
        "focal_requests": int(total_counts["focal_requests"]),
        "raw_counts": dict(sorted(total_counts.items())),
        "raw_eligible_windows": raw_eligible,
        "independent_roots": len(independent),
        "independent_roots_by_mix": {mix: len(pools[mix]) for mix in MIXES},
        "independent_focal_seat_coverage": seat_coverage,
        "selected_states": len(selected),
        "development_states": sum(row.get("split") == "development" for row in selected),
        "replication_states": sum(row.get("split") == "replication" for row in selected),
        "selected_by_mix": selected_counts if passes else {mix: 0 for mix in MIXES},
        "passes_natural_exposure_gate": passes,
        "replication_labels_opened": False,
        "model_calls": 0,
        "next": (
            "只对development状态运行32共同隐藏世界hu/discard:白配对；replication保持封存"
            if passes else
            "达到3,072桌预登记上限仍不足；关闭自然轴，不用构造题或阈值补救"
        ),
        "selection_eligible": False,
        "release_eligible": False,
    }
    write_json(_project_file(_PROJECT_ROOT, OUT / "dataset.json"), dataset)
    write_json(_project_file(_PROJECT_ROOT, OUT / "result.json"), result)
    print(json.dumps(result, ensure_ascii=False, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("prepare", "analyze"))
    command = parser.parse_args().command
    if command == "prepare":
        prepare()
    else:
        analyze()


if __name__ == "__main__":
    main()
