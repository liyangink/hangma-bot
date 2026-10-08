#!/usr/bin/env python3
"""G7 正差/零差负控新根暴露；复用已验证的 64 桌可见窗口筛查。"""

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
import hashlib
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import g7_new_root_exposure_pilot as pilot  # noqa: E402

PANEL_SEED = 2026102902
ROOTS = tuple(range(201, 213))
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g7-new-root-negative-control-20260927')
PREREG = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/G7-NEW-ROOT-NEGATIVE-CONTROL-PREREG-2026-09-27.md')

# pilot 的筛查与审计实现保持原样；仅在本进程设定新来源和独立输出目录。
pilot.PANEL_SEED = PANEL_SEED
pilot.ROOTS = ROOTS
pilot.OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g7-new-root-negative-control-20260927')
pilot.PREREG = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/G7-NEW-ROOT-NEGATIVE-CONTROL-PREREG-2026-09-27.md')


def prepare() -> None:
    """冻结全新 H/M 根、四座和结果盲自然桌执行预算。"""

    if OUT.exists():
        raise SystemExit("G7 新根负控目录已存在，拒绝覆盖")
    parent = pilot.g1.p83.parent_source()
    expected_sha = pilot.g1.p83.R18_INTEGRATED_POSITIVE_V2_SHA256
    if hashlib.sha256(parent.encode()).hexdigest() != expected_sha:
        raise ValueError("冻结 R18 v2 父代摘要不符")
    sources = pilot.sources()
    if len(sources) != 96 or len({item["source_root_id"] for item in sources}) != 24:
        raise ValueError("H/M 根或四座来源数不符")
    OUT.mkdir(parents=True)
    (_project_file(_PROJECT_ROOT, OUT / "sources")).mkdir()
    auth = pilot.g1.p83.batch.unified_document(
        batch_label=OUT.name, authorization_id="g7-new-root-negative-control-20260927",
        accounts={"tables_full": len(sources) * pilot.TABLES_PER_SOURCE},
        issued_by="lead", issued_at_utc=pilot.g1.p83.search.utc_now(),
        legacy_alias=False,
    )
    auth.update({"scope": "新根正差及零差负控 192 桌结果盲暴露",
                 "max_model_calls": 0, "confirmation_roots": 0})
    pilot._write(_project_file(_PROJECT_ROOT, OUT / "authorization.json"), auth)
    pilot._write(_project_file(_PROJECT_ROOT, OUT / "sources.json"), {"schema": "g7-new-root-sources/1",
                                        "sources": sources})
    closure = [Path(__file__), Path(pilot.__file__), PREREG,
               pilot.g1.CONTRACT, pilot.g1.PARENT,
               Path(pilot.g7.__file__), Path(pilot.overlap.__file__),
               Path(pilot.g1.p83.natural.__file__),
               _project_file(_PROJECT_ROOT, OUT / "authorization.json"), _project_file(_PROJECT_ROOT, OUT / "sources.json")]
    pilot._write(_project_file(_PROJECT_ROOT, OUT / "manifest.json"), {
        "schema": "g7-new-root-pilot-manifest/1",
        "created_at_utc": pilot.g1.p83.search.utc_now(),
        "runtime": pilot.g1.p83.guard.capture(source_paths=closure),
        "contract_sha256": pilot._sha(pilot.g1.CONTRACT),
        "prereg_sha256": pilot._sha(PREREG),
        "parent_source_sha256": expected_sha,
        "panel_seed": PANEL_SEED,
        "source_units": len(sources),
        "planned_tables": len(sources) * pilot.TABLES_PER_SOURCE,
        "sample_per_source": 2, "outcome_blind": True,
        "release_eligible": False,
    })
    print(json.dumps({"prepared_sources": len(sources),
                      "independent_roots": 24,
                      "planned_tables": 192}))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("prepare", "run", "analyze"))
    args = parser.parse_args()
    {"prepare": prepare, "run": pilot.run,
     "analyze": pilot.analyze}[args.command]()


if __name__ == "__main__":
    main()
