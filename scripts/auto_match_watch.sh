#!/usr/bin/env bash
# 自由赛盯盘唯一入口（固定指令，重复执行安全/幂等）。
# 盯盘 agent 只需要也只应该执行这一条命令（绝对路径，免疫工作目录错误）：
#   bash /Users/liyang/Projects/Opensource/hangma-bot/scripts/auto_match_watch.sh
# 行为：无会话→引导开第一房；存活→报进度；退出→下载牌谱/结算/记账/止损判断/续开。
# 详细语义与退出码见 scripts/auto_match_watchdog.py 文档字符串。
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
mkdir -p runs/auto-match-watchdog
exec .venv/bin/python3 scripts/auto_match_watchdog.py "$@"
