"""T199隔离解释器导入探针：实际读取旧driver锁字段和所有动态helper路径。

不调用watch、worker、load_config，不读取Token。子进程禁止网络与再spawn；
原样搬根的锁路径仍由旧ROOT派生，探针如实标记不兼容，不替它偷偷改字段。
"""
from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t199-four-step-execution-1/runtime'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

import argparse
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from release_gate import FREE_DRIVER, GateError, LEGACY_TOOLS, save_exclusive


def child_probe(root: Path, shared_dir: Path) -> dict:
    """实际导入冻结root；审计钩子阻止网络、凭据读取及导入期间外部副作用。"""
    root = root.resolve()
    def no_side_effects(event, arguments):
        if event in ("socket.connect", "socket.getaddrinfo", "subprocess.Popen", "os.system"):
            raise GateError("导入探针禁止外部副作用：" + event)
        if event == "open" and arguments and isinstance(arguments[0], (str, bytes)):
            path = os.fsdecode(arguments[0])
            if "token" in Path(path).parts or Path(path).name == ".env":
                raise GateError("导入探针禁止凭据读取")
    sys.addaudithook(no_side_effects)
    sys.path[:0] = [str(root / "src"), str(root)]
    driver_path = root / FREE_DRIVER
    spec = importlib.util.spec_from_file_location("t199_frozen_legacy_probe", driver_path)
    driver = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(driver)
    import hangma_bot.bootstrap as bootstrap
    import scripts.run_auto_match as launch
    modules = {"driver": driver, "nonblocking": driver.n, "helper": driver.h,
               "analysis": driver.a, "bootstrap": bootstrap, "player_entry": launch}
    paths = {name: str(Path(module.__file__).resolve()) for name, module in modules.items()}
    helper = Path(driver.a.HELPER).resolve()
    helper_spec = importlib.util.spec_from_file_location("t199_actual_analysis_helper", helper)
    helper_module = importlib.util.module_from_spec(helper_spec)
    helper_spec.loader.exec_module(helper_module)
    paths["analysis_dynamic_helper"] = str(Path(helper_module.__file__).resolve())
    if any(not Path(path).is_relative_to(root) for path in paths.values()):
        raise GateError("实际导入泄漏到冻结根外")
    locks = {"OWNER_LOCK": str(driver.OWNER_LOCK.resolve()),
             "POSTPROCESS_LOCK": str(driver.POSTPROCESS_LOCK.resolve()),
             "WORKER_SINGLETON": str((driver.PRIVATE / "worker.lock").resolve()),
             "helper_PRIVATE": str(driver.h.PRIVATE.resolve())}
    expected = {"OWNER_LOCK": str((shared_dir / "controller.lock").resolve()),
                "POSTPROCESS_LOCK": str((shared_dir / "postprocess.lock").resolve())}
    packages = {}
    for strategy in (bootstrap.VIP_S03_TESTROOM_STRATEGY, bootstrap.VIP_S03_FREE_STRATEGY,
                     bootstrap.VIP_S03_TEST_TOURNAMENT_STRATEGY, bootstrap.VIP_S03_OFFICIAL_TOURNAMENT_STRATEGY):
        package = bootstrap._load_vip_manifest(strategy, None)
        packages[strategy] = {"allowed_modes": package["allowed_modes"],
                              "release_package_id": package["release_package_id"]}
    return {"complete": True, "actual_module_paths": paths,
            "actual_free_identity": driver.identity(),
            "actual_roots": {"driver": str(driver.ROOT), "helper": str(driver.h.ROOT),
                             "bootstrap": str(bootstrap._REPO_ROOT)},
            "legacy_lock_paths": locks, "expected_shared_lock_paths": expected,
            "legacy_owner_lock_ready": locks["OWNER_LOCK"] == expected["OWNER_LOCK"],
            "legacy_postprocess_lock_ready": locks["POSTPROCESS_LOCK"] == expected["POSTPROCESS_LOCK"],
            "other_players_function_source": str(Path(driver.h.other_players.__code__.co_filename).resolve()),
            "all_legacy_tools_present": all((root / path).is_file() for path in LEGACY_TOOLS),
            "actual_four_package_assembly": packages,
            "python_runtime": {"executable": sys.executable, "version": sys.version,
                               "cache_tag": sys.implementation.cache_tag, "platform": sys.platform},
            "network_calls": 0, "token_reads": 0, "watch_called": False,
            "runtime_launch_implemented": False,
            "note": "旧watch还会写HERE并从DRIVER新spawn，不能仅改两个锁字段后当新控制器使用"}


def main() -> None:
    """父进程只启动此导入探针；真实玩家启动不在本工具能力范围。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--shared-lock-dir", required=True, type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--child", action="store_true")
    args = parser.parse_args()
    if args.child:
        print(json.dumps(child_probe(args.root, args.shared_lock_dir), ensure_ascii=False))
        return
    # -I排除调用方PYTHONPATH；探针和冻结root的导入入口由代码显式添加。
    process = subprocess.run([sys.executable, "-I", "-B", str(Path(__file__).resolve()),
        "--child", "--root", str(args.root.resolve()), "--shared-lock-dir", str(args.shared_lock_dir.resolve())],
        cwd=args.root, capture_output=True, text=True, timeout=30)
    if process.returncode:
        value = {"complete": False, "actual_exit_code": process.returncode,
                 "error": process.stderr[-2000:], "network_calls": 0,
                 "runtime_launch_implemented": False}
    else:
        value = json.loads(process.stdout)
        value["probe_subprocess_actual_exit_code"] = process.returncode
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        save_exclusive(args.out, value)
    print(json.dumps(value, ensure_ascii=False, indent=2))
    if not value["complete"]:
        raise SystemExit(2)


if __name__ == "__main__":
    # -I不自动把工具目录加入sys.path，仍只允许这一个显式工具目录。
    main()
