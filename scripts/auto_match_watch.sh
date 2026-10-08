#!/usr/bin/env bash
# 自由赛单次巡检入口（重复执行安全/幂等）；连续巡检由 auto_match_watch_loop.sh 调用。
# 从仓库根目录执行：
#   bash scripts/auto_match_watch.sh  （从仓库根目录运行）
# 行为：无会话→引导开第一房；存活→报进度；退出→下载牌谱/结算/记账/止损判断/续开。
# 详细语义与退出码见 scripts/auto_match_watchdog.py 文档字符串。
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
mkdir -p runs/auto-match-watchdog
exec "${WATCHDOG_PYTHON:-.venv/bin/python3}" scripts/auto_match_watchdog.py "$@"
