"""安装期构建可选规则扩展；线上导入和动作窗口永远不启动编译器。

HANGMA_NATIVE=auto（默认）允许无编译器时安装 Python 路径，required
用于要求原生制品的部署，off 用于纯 Python 安装及退路验收。
"""
from __future__ import annotations

import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import sysconfig
import tempfile

from hatchling.builders.hooks.plugin.interface import BuildHookInterface


def publish_extension(source: Path, destination: Path) -> None:
    """先复制到目标目录的临时文件再原子替换，允许系统临时目录跨文件系统。"""
    with tempfile.NamedTemporaryFile(prefix=".hangma-native-", dir=destination.parent, delete=False) as handle:
        staged = Path(handle.name)
    try:
        shutil.copyfile(source, staged)
        os.replace(staged, destination)
    finally:
        staged.unlink(missing_ok=True)


class CustomBuildHook(BuildHookInterface):
    """沿用 Hatch 构建后端，为普通与可编辑安装生成本平台 CPython 扩展。"""

    def initialize(self, version: str, build_data: dict) -> None:
        """编译成功才纳入 wheel；可选构建失败时清除同 ABI 的旧开发制品。"""
        if self.target_name != "wheel":
            return
        mode = os.environ.get("HANGMA_NATIVE", "auto")
        if mode not in {"auto", "required", "off"}:
            raise ValueError("HANGMA_NATIVE 只能是 auto、required 或 off")
        package = Path(self.root) / "src/hangma_bot/hangma"
        suffix = sysconfig.get_config_var("EXT_SUFFIX")
        source = package / "_grouped_native.c"
        destination = package / ("_grouped_native" + (suffix or ".so"))
        if mode == "off":
            if version == "editable":
                destination.unlink(missing_ok=True)
            return
        self._temporary = tempfile.TemporaryDirectory(prefix="hangma-native-build-")
        output = Path(self._temporary.name) / destination.name
        try:
            if sys.implementation.name != "cpython" or sys.platform == "win32" or not suffix:
                raise RuntimeError("原生构建当前支持带 GCC/Clang 的 macOS/Linux CPython")
            include = sysconfig.get_paths()["include"]
            if not (Path(include) / "Python.h").is_file():
                raise RuntimeError("缺少当前 Python 的开发头文件 Python.h")
            linker = shlex.split(sysconfig.get_config_var("LDSHARED") or "cc -shared")
            if os.environ.get("CC"):
                linker = shlex.split(os.environ["CC"]) + linker[1:]
            # 保留解释器的架构/系统部署目标；不加入 -march=native，避免绑定本机指令。
            flags = shlex.split(sysconfig.get_config_var("CFLAGS") or "")
            flags += shlex.split(os.environ.get("CFLAGS", ""))
            command = linker + flags + ["-O3", "-std=c11", "-fPIC", "-I" + include,
                str(source), "-o", str(output)] + shlex.split(os.environ.get("LDFLAGS", ""))
            subprocess.run(command, check=True, capture_output=True, text=True)
            if version == "editable":
                publish_extension(output, destination)
        except (OSError, RuntimeError, subprocess.CalledProcessError) as exc:
            self._temporary.cleanup()
            if version == "editable":
                destination.unlink(missing_ok=True)
            details = exc.stderr.strip() if isinstance(exc, subprocess.CalledProcessError) else str(exc)
            message = "规则 C 扩展构建失败：" + details
            if mode == "required":
                raise RuntimeError(message) from exc
            self.app.display_warning(message + "；安装同语义 Python 分组实现。")
            return
        if version != "editable":
            build_data["force_include"][str(output)] = "hangma_bot/hangma/" + output.name
        build_data["pure_python"] = False
        build_data["infer_tag"] = True

    def finalize(self, version: str, build_data: dict, artifact_path: str) -> None:
        """wheel 已封装后清除临时编译目录，可编辑安装制品继续供本地导入。"""
        temporary = getattr(self, "_temporary", None)
        if temporary is not None:
            temporary.cleanup()
