"""安装期构建可选规则扩展；线上导入和动作窗口永远不启动编译器。

HANGMA_NATIVE=auto（默认）先复用兼容预编译制品，缺失时尝试构建，
最终允许 Python 退路；required 要求原生成功，prebuilt 禁止源码编译，
off 用于纯 Python 安装及退路验收。所有检查只发生在安装期。
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import platform
import shlex
import shutil
import subprocess
import sys
import sysconfig
import tempfile

from hatchling.builders.hooks.plugin.interface import BuildHookInterface


def select_prebuilt(root: Path) -> tuple[Path, str] | None:
    """按运行平台、解释器、系统下限及源码/制品摘要选择已入库扩展。

    当前只提供 macOS arm64 CPython 制品；不匹配、损坏或清单异常均
    返回 None，安装调用方决定编译或报错。不访问网络、不加载二进制。
    """
    if sys.platform != "darwin" or sys.implementation.name != "cpython":
        return None
    if sysconfig.get_config_var("Py_DEBUG") or sysconfig.get_config_var("Py_GIL_DISABLED"):
        return None
    directory = root / "prebuilt/hangma"
    try:
        manifest = json.loads((directory / "manifest.json").read_text())
        if manifest["schema_version"] != 1:
            return None
        host_macos = tuple(int(value) for value in platform.mac_ver()[0].split(".")[:2])
        for item in manifest["artifacts"]:
            if (item["platform"] != sys.platform
                or item["architecture"] != platform.machine()
                or item["python_implementation"] != sys.implementation.name
                or item["python_version"] != list(sys.version_info[:2])
                or item["soabi"] != sysconfig.get_config_var("SOABI")
                or item["extension_suffix"] != sysconfig.get_config_var("EXT_SUFFIX")):
                continue
            minimum = tuple(item["minimum_macos"])
            if (len(minimum) != 2 or any(type(n) is not int for n in minimum)
                or minimum[0] < 11 or minimum[1] != 0 or len(host_macos) != 2
                or host_macos < minimum):
                continue
            artifact = (directory / item["path"]).resolve()
            if not artifact.is_relative_to(directory.resolve()):
                continue
            if artifact.name != "_grouped_native" + item["extension_suffix"]:
                continue
            if hashlib.sha256(artifact.read_bytes()).hexdigest() != item["binary_sha256"]:
                continue
            sources = item["sources"]
            required_sources = {"src/hangma_bot/hangma/_grouped_native.c",
                "src/hangma_bot/hangma/_standard_python.py"}
            if not required_sources.issubset(sources):
                continue
            for name, expected in sources.items():
                source = (root / name).resolve()
                if (not source.is_relative_to(root.resolve())
                    or hashlib.sha256(source.read_bytes()).hexdigest() != expected):
                    break
            else:
                python_tag = "cp" + "".join(map(str, sys.version_info[:2]))
                tag = f"{python_tag}-{python_tag}-macosx_{minimum[0]}_0_{item['architecture']}"
                return artifact, tag
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return None
    return None


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
