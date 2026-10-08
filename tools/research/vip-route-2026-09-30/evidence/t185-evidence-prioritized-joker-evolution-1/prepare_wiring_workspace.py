"""在私有目录准备当前线上源码的隔离副本；不切换版本、不运行任何牌局。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t185-evidence-prioritized-joker-evolution-1'

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
import os
from pathlib import Path
import shutil
import subprocess
import sys

from common import HERE, ROOT, pin, save
import t185_close_development as dev

WORK = _project_file(_PROJECT_ROOT, ROOT / ".private/t185-wiring/workspace")


def main():
    """按当前S02冻结清单复制公开代码及制品，独立解释器核两个旧包；不复制凭证。"""
    from hangma_bot import bootstrap as b
    free = b._load_vip_free_manifest()
    test = b._load_vip_testroom_manifest()
    dev.require(free["source_manifest"] == test["source_manifest"] == b._vip_runtime_sources(),
        "当前线上源码与两旧包不一致，不准备漂移副本")
    dev.require(not WORK.exists(), "隔离副本已存在，保留原工作，不覆盖或重置")
    files = set(free["source_manifest"])
    files.update(free["evidence_sha256"])
    files.update(test["evidence_sha256"])
    files.update((b.VIP_S02_FREE_MANIFEST, b.VIP_S02_TESTROOM_MANIFEST,
        "configs/vip-s02-bounded-d1-v6.free-match.example.json",
        "configs/vip-s02-bounded-d1-v8.test-room.example.json", "AGENTS.md", "README.md",
        "UBIQUITOUS_LANGUAGE.md", "pyproject.toml"))
    files.update(p.relative_to(ROOT).as_posix() for p in
        (_project_file(_PROJECT_ROOT, ROOT / b.VIP_S02_COMPILED_DIRECTORY)).iterdir() if p.is_file())
    files.update(p.relative_to(ROOT).as_posix() for p in (_project_file(_PROJECT_ROOT, ROOT / "src/hangma_bot/hangma")).glob("*.so"))
    dev.require(any(n.endswith(".so") and n.startswith("src/hangma_bot/hangma/") for n in files),
        "规则数学本地原件缺失，不在副本中临时编译")
    source_files = {}
    for name in sorted(files):
        p = Path(name)
        dev.require(not p.is_absolute() and ".." not in p.parts and p.parts[0] != ".private" and
            (_project_file(_PROJECT_ROOT, ROOT / p)).resolve().is_relative_to(ROOT), "副本不接收私有凭证或仓库外路径")
        source_files[name] = pin(_project_file(_PROJECT_ROOT, ROOT / p))
    out = _project_file(_PROJECT_ROOT, HERE / "wiring-preparation")
    out.mkdir(exist_ok=False)
    WORK.mkdir(parents=True, mode=0o700)
    save(out / "START.json", {"workspace": str(WORK), "files": source_files,
        "old_free_package_id": free["release_package_id"], "old_testroom_package_id": test["release_package_id"],
        "new_candidate_package_created": False, "online_source_or_watchdog_modified": False,
        "HTTP_scores_worlds_tables_workers_started": 0})
    failure, answer = None, None
    try:
        for name, expected in source_files.items():
            target = WORK / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(_project_file(_PROJECT_ROOT, ROOT / name), target)
            dev.require(pin(target) == expected, "隔离副本实际字节不同:" + name)
        code = ('import json; from pathlib import Path; from hangma_bot import bootstrap as b; '
            'assert Path(b.__file__).resolve().is_relative_to(Path.cwd()); '
            'print(json.dumps({"bootstrap_file":b.__file__,"free":b._load_vip_free_manifest()["release_package_id"],'
            '"testroom":b._load_vip_testroom_manifest()["release_package_id"],'
            '"source_count":len(b._vip_runtime_sources())}))')
        env = {**os.environ, "PYTHONPATH": str(WORK / "src") + os.pathsep + str(WORK),
            "PYTHONDONTWRITEBYTECODE": "1"}
        proc = subprocess.run([sys.executable, "-c", code], cwd=WORK, env=env, capture_output=True)
        save(out / "PREFLIGHT-RECEIPT.json", {"actual_exit_code": proc.returncode,
            "stdout_sha256": hashlib.sha256(proc.stdout).hexdigest(),
            "stderr_sha256": hashlib.sha256(proc.stderr).hexdigest(), "HTTP_scores_worlds_tables_workers_started": 0})
        dev.require(proc.returncode == 0, "旧包隔离预检失败；保留副本，禁止自动重做:" + proc.stderr.decode()[-1000:])
        answer = json.loads(proc.stdout)
        dev.require(answer["free"] == free["release_package_id"] and answer["testroom"] == test["release_package_id"] and
            answer["source_count"] == len(free["source_manifest"]), "隔离副本旧包或源码数量不同")
    except BaseException as error:
        failure = {"type": type(error).__name__, "message": str(error)}
    finally:
        stable = all(pin(_project_file(_PROJECT_ROOT, ROOT / name)) == expected for name, expected in source_files.items())
        complete = failure is None and stable and answer is not None
        save(out / "CLOSED.json", {"complete": complete, "failure": failure, "source_stable": stable,
            "workspace": str(WORK), "files": source_files, "preflight": answer,
            "new_candidate_package_created": False, "new_candidate_equivalence_strength_or_deadline_admitted": False,
            "online_source_or_watchdog_modified": False, "HTTP_scores_worlds_tables_workers_started": 0})
    dev.require(complete, "隔离副本准备未通过；原副本和失败均保留")
    print({"complete": True, "source_count": answer["source_count"], "copied_files": len(source_files),
        "new_candidate_admission": False}, flush=True)


if __name__ == "__main__":
    main()
