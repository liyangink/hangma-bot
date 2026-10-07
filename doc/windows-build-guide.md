# Windows 编译指南

截至 2026-10-07，当前 P0 正式策略包仅支持 Apple Silicon Mac 和 CPython 3.11.x（不限定补丁版本）。Windows 原生编译尚未支持；Windows 上使用 WSL2（Windows 的 Linux 子系统）可以准备 Linux 构建环境并编译规则模块，但仍需完整的 Linux 正式策略发布包才能参赛。

Mac 的参赛入口会自动准备兼容 Python 和依赖。`participate.sh` 尚不提供 Windows／Linux 正式运行支持；以下步骤用于编译准备。

## 1. 安装 WSL2

要求 Windows 11，或 Windows 10 2004／内部版本 19041 及以上，并允许安装 WSL2。

以管理员身份打开 PowerShell，执行：

```powershell
wsl --install -d Ubuntu
```

重启电脑，打开 Ubuntu，按提示创建用户名和密码。在 PowerShell 中确认 `VERSION` 为 `2`：

```powershell
wsl --list --verbose
```

若已有 Ubuntu 显示为 `1`，执行：

```powershell
wsl --set-version Ubuntu 2
```

## 2. 准备编译环境

以下命令均在 Ubuntu 终端执行：

```bash
sudo apt-get update
sudo apt-get install -y build-essential git curl
curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"
uv python install 3.11
git clone https://github.com/liyangink/hangma-bot.git
cd hangma-bot
uv venv --python 3.11 .venv
source .venv/bin/activate
```

## 3. 编译并检查规则模块

安装命令会自动编译规则模块，编译失败会停止安装：

```bash
HANGMA_NATIVE=required uv pip install -e .
```

检查命令：

```bash
python scripts/check_native_backend.py --json
```

确认输出中的 `runtime.implementation` 为 `c_grouped`。此检查只验证规则模块，不代表正式策略包已可运行。

## 4. 正式参赛前仍需完成

当前安装命令不会编译正式策略。仓库中的四个共享策略模块和 P0 策略模块均为 Mac 预编译文件，正式发布包还校验这些文件及规则模块的摘要。

完整 Windows／Linux 支持仍需：

1. 在目标平台编译全部策略模块；原生 Windows 还需适配规则模块与构建入口。
2. 生成并审核目标平台的正式发布包及配套配置。
3. 在目标电脑验证规则一致性、配置作用域、赛事生命周期、多进程运行及 1 秒／3 秒动作时限。

以上 WSL2 步骤已按现有构建入口核对，尚未在 Windows 电脑实测。当前没有可保证直接启动 P0 正式赛的 Windows／WSL2 命令；只允许原生 Windows 的电脑需要先完成平台移植。
