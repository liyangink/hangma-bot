"""准备精确来源清单与独立S03续赛入口；不修改主线，不联网或停止玩家。"""
from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t191-four-day-execution-1/successor-wiring-1'

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
ROOT = _PROJECT_ROOT
WORK = _project_file(_PROJECT_ROOT, '.private/t191-successor-wiring/workspace')


def pin(path):
    """文件完整字节身份；不读取凭证。"""
    raw = path.read_bytes()
    return {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def save(path, value):
    """独占保存准备证据，禁止覆盖既有尝试。"""
    with path.open("x") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def main():
    """先核所有实际门，再准备唯一自然交接；本工具零评分、零HTTP。"""
    load = lambda p: json.loads(p.read_text())
    prepared = load(_project_file(_PROJECT_ROOT, HERE / "ASSEMBLY-PREPARED.json"))
    packages = load(_project_file(_PROJECT_ROOT, HERE / "PACKAGES-CLOSED.json"))
    validation = load(_project_file(_PROJECT_ROOT, HERE / "ASSEMBLY-VALIDATION-CLOSED.json"))
    deadline = load(_project_file(_PROJECT_ROOT, HERE / "original-deadline-probe/CLOSED.json"))
    assert all(d["complete"] for d in (prepared, packages, validation, deadline))
    assert validation["source_stable"] and validation["actual_functional_score_calls"] == 10
    assert len(validation["actual_checks"]) == 80
    assert deadline["source_stable"] and deadline["actual_service_choose"] == 59
    assert load(_project_file(_PROJECT_ROOT, HERE / "DEADLINE-ACTUAL-RECEIPT.json"))["actual_exit_code"] == 0
    assert len(packages["source_manifest"]) == 183
    paths = set(prepared["changed_source_files"])
    for row in packages["rows"]:
        paths.update((row["package_path"], row["config_path"]))
    native = _project_file(_PROJECT_ROOT, WORK / "prebuilt/vip-s03-compiled-formula-v1")
    paths.update(p.relative_to(WORK).as_posix() for p in native.iterdir() if p.is_file())
    assert len(paths) == 27
    changes = []
    for relative in sorted(paths):
        destination, source = _project_file(_PROJECT_ROOT, ROOT / relative), _project_file(_PROJECT_ROOT, WORK / relative)
        after = pin(source)
        expected = prepared["changed_source_files"].get(relative)
        before = pin(destination) if destination.exists() else None
        if expected:
            assert before == expected["before"] and after == expected["after"]
        else:
            assert before is None, "新制品路径已存在，禁止覆盖: " + relative
        changes.append({"path": relative, "before": before, "after": after})
    for relative, digest in packages["source_manifest"].items():
        assert pin(_project_file(_PROJECT_ROOT, WORK / relative))["sha256"] == digest
        if relative not in prepared["changed_source_files"]:
            assert pin(_project_file(_PROJECT_ROOT, ROOT / relative))["sha256"] == digest
    save(_project_file(_PROJECT_ROOT, HERE / "CHANGESET.json"), {"complete": True, "files": changes,
        "production_source_files_changed": 3, "runtime_source_manifest": packages["source_manifest"],
        "main_application_requires_predecessor_natural_finish": True,
        "mandatory_gates": {name: pin(_project_file(_PROJECT_ROOT, HERE / name)) for name in
            ("ASSEMBLY-PREPARED.json", "PACKAGES-CLOSED.json", "ASSEMBLY-VALIDATION-CLOSED.json",
             "original-deadline-probe/CLOSED.json", "DEADLINE-ACTUAL-RECEIPT.json")}})

    original_path = _project_file(_PROJECT_ROOT, HERE.parent / "free_watchdog.py")
    original = original_path.read_text()
    replacements = [
        ("T191 独立自由赛守护", "T191 S03独立自由赛守护"),
        ("ROOT = HERE.parents[3]", "ROOT = HERE.parents[4]"),
        ("OLD = HERE.parent / 't165-live-watchdog-1'", "OLD = HERE.parent.parent / 't165-live-watchdog-1'"),
        (".private/t191-free-watchdog", ".private/t191-s03-free-watchdog"),
        ("b.VIP_S02_FREE_SUCCESSOR_STRATEGY", "b.VIP_S03_FREE_STRATEGY"),
        ("('vip_s02_bounded_d1_free_v6', 'vip_s02_bounded_d1_free_v7')",
         "('vip_s02_bounded_d1_free_v6', 'vip_s02_bounded_d1_free_v7', 'vip_s03_bounded_d1_free_v1')"),
        ("t191-live-%s-free", "t191-s03-live-%s-free"),
        ("T191专属计算版持续自由赛", "T191 S03专属计算版持续自由赛"),
        ("'t170-free-only-watchdog-1': '.private/t170-free-watchdog'",
         "'t170-free-only-watchdog-1': '.private/t170-free-watchdog',\n"
         "                't191-four-day-execution-1': '.private/t191-free-watchdog'"),
        ("h.write(directory / 'PLAN.json', plan, exclusive=True)",
         "# 审计脱敏会截断长源码映射；另存完整公共包，不读取Token。\n"
         "    import hangma_bot.bootstrap as b\n"
         "    release = b._load_vip_manifest(frozen['free_strategy'], frozen['package_ids']['free'])\n"
         "    h.write(directory / 'RELEASE-SNAPSHOT.json', release, exclusive=True)\n"
         "    h.write(directory / 'PLAN.json', plan, exclusive=True)"),
    ]
    body = original
    for old, new in replacements:
        expected_count = 2 if old == "b.VIP_S02_FREE_SUCCESSOR_STRATEGY" else 1
        assert body.count(old) == expected_count, old
        body = body.replace(old, new)
    compile(body, str(_project_file(_PROJECT_ROOT, HERE / "free_watchdog.py")), "exec")
    with (_project_file(_PROJECT_ROOT, HERE / "free_watchdog.py")).open("x") as stream:
        stream.write(body)
    save(_project_file(_PROJECT_ROOT, HERE / "WATCHDOG-PREPARATION.json"), {"complete": True,
        "original_driver": {"path": str(original_path.relative_to(ROOT)), **pin(original_path)},
        "successor_driver": {"path": str((_project_file(_PROJECT_ROOT, HERE / "free_watchdog.py")).relative_to(ROOT)), **pin(_project_file(_PROJECT_ROOT, HERE / "free_watchdog.py"))},
        "explicit_replacements": [{"before": old, "after": new} for old, new in replacements],
        "same_global_token_owner_lock_and_postprocess_lock": True,
        "new_driver_started": False, "main_source_modified": False,
        "new_score_worker_world_table_HTTP_model_calls": 0})
    print({"prepared_exact_files": len(changes), "source_files_changed": 3, "new_owner_started": False})


if __name__ == "__main__":
    main()
