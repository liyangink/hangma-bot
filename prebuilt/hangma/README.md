# 预编译规则制品

本目录将小型规则扩展随源码一起提交，使兼容的 Apple Silicon Mac 安装时无需编译。当前文件为 **52,552 字节**，没有第三方动态库依赖，只依赖 macOS 系统库和运行中的 Python 解释器。

## 使用范围

兼容范围由二进制与解释器共同决定，不要求 M 系列芯片型号完全相同。

| 项目 | 当前制品 |
| --- | --- |
| CPU 架构 | arm64；Python 进程也须以 arm64 运行 |
| Python | CPython 3.11.x 常规构建；不是跨 Python 次版本通用扩展 |
| macOS | 二进制最低系统标记为 11.0；只在 macOS 26.6.2 当前机器实测 |
| wheel 标签 | cp311-cp311-macosx_11_0_arm64 |
| 数学语义 | hangma-standard-grouped-v1 |
| 原生文件 SHA-256 | c475cfd69a86317a2b42bde8085e9e14aa2a0c456a8dae656935c6ba45a18dd6 |

相同 CPython 次版本内的二进制接口（Application Binary Interface，ABI，决定解释器能否加载扩展）通常兼容，3.11 与 3.12 需分别构建；macOS 标签表示最低系统和架构。依据 [Python 官方 ABI 说明](https://docs.python.org/3/c-api/stable.html)与[平台标记规范](https://packaging.python.org/en/latest/specifications/platform-compatibility-tags/)，查阅日期 2026-09-07。

## 安装与确认

新机器仍需正常安装项目及 Python 依赖。开发安装会把匹配库复制到当前源码包；仅 git clone 不会把本目录变成 Python 导入路径。

```sh
python3.11 -m venv .venv
HANGMA_NATIVE=prebuilt .venv/bin/python -m pip install -e '.[dev]'
python scripts/check_native_backend.py
```

检查输出的 implementation 为 c_grouped。测试房、自由赛、正式赛、模拟与规则重算评估都复用此规则模块；保留历史规则结果的决策评估不重新计算。已经运行的进程需要重启。

**安装后必须跑一次 `scripts/check_native_backend.py`（换机器、改建 venv、以及开跑长篇离线评估之前同样要跑）**。它把"本机存在完全匹配的预编译件、却在跑纯 Python 回退"判为失败并给出修复命令；"本机确实没有匹配制品"则只提示原因、不算问题。判据与安装期**共用同一份**匹配模块（`selection.py`），不会各判一套。

**为什么要有这道检查**：原生构建钩子在 `auto` 模式下不匹配或未执行时**只警告、不报错**，回落是静默的。2026-09-16 实测到一次真实漏装：venv 比本目录的 C 内核早两天建立、之后从未重装，环境长期跑纯 Python，每桌 CPU 9.01 秒 vs 启用内核 1.84 秒（**4.9 倍**）。该差异只在跑几千桌时才显形，日常看不出，**项目的历史吞吐常数因此被误判作废**（其实它描述的是带内核的环境）。

默认 auto 与 required 先尝试预编译库；required 要求最终获得原生扩展。prebuilt 明确禁止源码编译，不兼容就报错。off 使用 Python。指定 CC/CFLAGS/LDFLAGS 等编译配置时，auto/required 进入源码构建，以尊重显式配置；prebuilt 始终只复用。

## 校验与更新

[manifest.json](manifest.json)记录平台、Python 版本、扩展后缀、最低 macOS、二进制摘要及对应的 C/Python 数学源码摘要。path 相对本目录；sources 的键相对仓库根目录；provenance 记录源码对应提交、捕获日期和既有校验证据。未匹配的制品不进入安装包，损坏或缺少来源信息时也不复用。

改变数学源码后，旧制品会因摘要不匹配而失效。维护者应使用常规源码编译（例如显式设置 CC），重新验证二进制、系统下限、动态依赖和数学输出，再更新本目录及清单。不能仅修改清单摘要来掩盖源码与制品不一致，也不能将普通构建的 wheel 仅改名来扩大兼容范围。

此制品原样复用[规则集成中已通过数学校验的库](../../review/grouped-dp-integration-2026-09-07/validation-native/validation.json)，没有重新编译或改变算法。本次分发验收见[免编译安装记录](../../review/native-prebuilt-2026-09-07/README.md)。
