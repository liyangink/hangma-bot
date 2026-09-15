"""安装期构建可选规则扩展；线上导入和动作窗口永远不启动编译器。

HANGMA_NATIVE=auto（默认）先复用兼容预编译制品，缺失时尝试构建，
最终允许 Python 退路；required 要求原生成功，prebuilt 禁止源码编译，
off 用于纯 Python 安装及退路验收。所有检查只发生在安装期。
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


# 预编译制品的匹配逻辑**只有一处定义**（prebuilt/hangma/selection.py）：构建钩子与
# scripts/check_native_backend.py 共用同一份，避免"检查"与"安装"两套判据漂移。
# 此处按路径加载，不为本模块再引入安装期包依赖。
def _load_prebuilt_selection():
    import importlib.util

    path = Path(__file__).resolve().parent / "prebuilt" / "hangma" / "selection.py"
    spec = importlib.util.spec_from_file_location("hangma_prebuilt_selection", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


select_prebuilt = _load_prebuilt_selection().select_prebuilt


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
    """沿用 Hatch 后端，为普通与可编辑安装复用或构建 CPython 扩展。"""

    def initialize(self, version: str, build_data: dict) -> None:
        """校验或编译成功才纳入 wheel；失败时清除同 ABI 的旧开发制品。"""
        if self.target_name != "wheel":
            return
        mode = os.environ.get("HANGMA_NATIVE", "auto")
        if mode not in {"auto", "required", "off", "prebuilt"}:
            raise ValueError("HANGMA_NATIVE 只能是 auto、required、prebuilt 或 off")
        package = Path(self.root) / "src/hangma_bot/hangma"
        suffix = sysconfig.get_config_var("EXT_SUFFIX")
        source = package / "_grouped_native.c"
        destination = package / ("_grouped_native" + (suffix or ".so"))
        if mode == "off":
            if version == "editable":
                destination.unlink(missing_ok=True)
            return
        self._temporary: tempfile.TemporaryDirectory[str] | None = None
        native_tag: str | None = None
        try:
            # 显式编译选项必须生效；prebuilt 则明确要求只复用已有制品。
            custom_build = any(os.environ.get(key) for key in (
                "CC", "CFLAGS", "LDFLAGS", "ARCHFLAGS", "MACOSX_DEPLOYMENT_TARGET", "_PYTHON_HOST_PLATFORM"))
            prebuilt = select_prebuilt(Path(self.root)) if mode == "prebuilt" or not custom_build else None
            if prebuilt is not None:
                output, native_tag = prebuilt
                self.app.display_info("复用已校验的规则预编译制品：" + output.name)
            else:
                if mode == "prebuilt":
                    raise RuntimeError("没有与当前平台、Python 和源码匹配的预编译规则制品；未启动编译器")
                if sys.implementation.name != "cpython" or sys.platform == "win32" or not suffix:
                    raise RuntimeError("原生构建当前支持带 GCC/Clang 的 macOS/Linux CPython")
                include = sysconfig.get_paths()["include"]
                if not (Path(include) / "Python.h").is_file():
                    raise RuntimeError("缺少当前 Python 的开发头文件 Python.h")
                self._temporary = tempfile.TemporaryDirectory(prefix="hangma-native-build-")
                output = Path(self._temporary.name) / destination.name
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
            if self._temporary is not None:
                self._temporary.cleanup()
            if version == "editable":
                destination.unlink(missing_ok=True)
            details = exc.stderr.strip() if isinstance(exc, subprocess.CalledProcessError) else str(exc)
            message = "规则 C 扩展构建失败：" + details
            if mode in {"required", "prebuilt"}:
                raise RuntimeError(message) from exc
            self.app.display_warning(message + "；安装同语义 Python 分组实现。")
            return
        if version != "editable":
            build_data["force_include"][str(output)] = "hangma_bot/hangma/" + output.name
        build_data["pure_python"] = False
        if native_tag is not None:
            build_data["tag"] = native_tag
            build_data["infer_tag"] = False
        else:
            build_data["infer_tag"] = True

    def finalize(self, version: str, build_data: dict, artifact_path: str) -> None:
        """wheel 已封装后清除临时编译目录，可编辑安装制品继续供本地导入。"""
        temporary = getattr(self, "_temporary", None)
        if temporary is not None:
            temporary.cleanup()
