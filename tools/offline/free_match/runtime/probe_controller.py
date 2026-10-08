"""T199新控制器实际-I导入／共享锁FD探针，只调用inspect，不启动watch。"""
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
import release_gate as gate


def main() -> None:
    """owner-fd只核已有继承描述符；从不打开、取得或释放活跃owner锁。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", required=True, type=Path)
    parser.add_argument("--owner-fd", type=int)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--child", action="store_true")
    args = parser.parse_args()
    if args.child:
        def deny(event, values):
            if event in ("socket.connect", "socket.getaddrinfo", "subprocess.Popen", "os.system"):
                raise gate.GateError("预检禁止网络或二次spawn")
            if event == "open" and values and isinstance(values[0], (str, bytes)):
                path = Path(os.fsdecode(values[0]))
                if "token" in path.parts or path.name == ".env":
                    raise gate.GateError("预检禁止凭据读取")
        sys.addaudithook(deny)
        spec = gate.read_json(args.spec)
        root = Path(spec["release_root"])
        entry = root / 'tools/offline/free_match/runtime/controller.py'
        frozen_gate_spec = importlib.util.spec_from_file_location("release_gate", entry.parent / "release_gate.py")
        frozen_gate = importlib.util.module_from_spec(frozen_gate_spec)
        sys.modules["release_gate"] = frozen_gate
        frozen_gate_spec.loader.exec_module(frozen_gate)
        module_spec = importlib.util.spec_from_file_location("t199_actual_controller", entry)
        module = importlib.util.module_from_spec(module_spec)
        module_spec.loader.exec_module(module)
        controller = module.Controller(args.spec)
        value = controller.inspect()
        if spec.get("preparation_only") is True:
            try:
                controller.check_admission()
            except ValueError as error:
                value["draft_start_refused"] = True
                value["draft_refusal_reason"] = str(error)
            else:
                raise gate.GateError("草稿竟通过真实启动资格，拒绝预检放行")
        value["actual_controller_file"] = str(Path(module.__file__).resolve())
        value["actual_gate_file"] = str(Path(module.gate.__file__).resolve())
        value["network_calls"] = 0
        if args.owner_fd is not None:
            value["inherited_fd_probe"] = gate.verify_owner_fd(args.owner_fd, Path(spec["shared"]["owner_lock"]))
        print(json.dumps(value, ensure_ascii=False))
        return
    command = [sys.executable, "-I", "-B", str(Path(__file__).resolve()), "--child", "--spec", str(args.spec.resolve())]
    descriptors = ()
    if args.owner_fd is not None:
        command.extend(("--owner-fd", str(args.owner_fd)))
        descriptors = (args.owner_fd,)
    process = subprocess.run(command, cwd=Path(gate.read_json(args.spec)["release_root"]),
                             capture_output=True, text=True, timeout=30, pass_fds=descriptors)
    if process.returncode:
        value = {"complete": False, "actual_exit_code": process.returncode,
                 "error": process.stderr[-2000:], "network_calls": 0}
    else:
        value = json.loads(process.stdout)
        value["probe_subprocess_actual_exit_code"] = 0
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        gate.save_exclusive(args.out, value)
    print(json.dumps(value, ensure_ascii=False, indent=2))
    if not value["complete"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
