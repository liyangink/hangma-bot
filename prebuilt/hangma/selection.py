"""规则预编译制品的匹配与判定（**安装期与检查期共用的唯一定义**）。

**为什么单独成模块**：这段匹配逻辑原先只存在于 `hatch_build.py` 内，而该文件在
模块顶层导入 `hatchling`——只有构建隔离环境里能导入。于是"运行时到底装了哪个后端"
这个检查**没有便宜的复用路径**，只能靠人记得。抽出来之后，构建钩子与
`scripts/check_native_backend.py` 用的是**同一份**匹配规则。

**边界**：本模块只做只读的路径/摘要判定，不加载二进制、不访问网络、不编译、不写盘；
它不导入 `hangma_bot`（运行时事实由调用方传入 `evaluate_backend`）。
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import platform
import sys
import sysconfig

MANIFEST_SCHEMA_VERSION = 1


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
        if manifest["schema_version"] != MANIFEST_SCHEMA_VERSION:
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


def evaluate_backend(runtime: dict, prebuilt: tuple[Path, str] | None) -> dict:
    """把"运行时实际后端"与"本机是否有可用预编译件"合成为一个判定（纯函数）。

    三类结论，**关键是区分后两类**：

    - `native`：运行时已加载原生内核 ⇒ ok。
    - `fallback_with_usable_prebuilt`：**本机存在完全匹配的预编译件，却在跑纯 Python 回退**
      ⇒ 这是"漏装"（安装时没跑原生发布那一步），不是正常退路；必须报错并给出修复命令。
    - `fallback_without_prebuilt`：本机确实没有匹配制品（平台/解释器不符，或源码已改而
      制品未更新）⇒ 属正常退路，只提示原因。
    """
    implementation = (runtime or {}).get("implementation")
    native = implementation not in (None, "unavailable") and implementation != "python"
    if native:
        return {"verdict": "native", "ok": True, "fix": None,
            "detail": "已加载原生规则内核（implementation=%s）" % implementation}
    if prebuilt is None:
        return {"verdict": "fallback_without_prebuilt", "ok": True, "fix": None,
            "detail": "本机没有匹配的预编译制品，纯 Python 回退属正常（平台/解释器不符或源码已改而制品未更新）"}
    artifact, _tag = prebuilt
    fix = "HANGMA_NATIVE=prebuilt uv pip install --python .venv/bin/python --no-deps -e ."
    return {"verdict": "fallback_with_usable_prebuilt", "ok": False, "fix": fix,
        "detail": "存在完全匹配的预编译件却在跑纯 Python 回退（implementation=%s，artifact=%s）；"
                  "这属安装漏装而非正常退路" % (implementation, artifact.name)}
