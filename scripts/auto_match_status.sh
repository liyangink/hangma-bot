#!/usr/bin/env bash
# 自由赛战况细查（只读固定指令）：每场比分/完赛数/小计/账本累计。
#   bash /Users/liyang/Projects/Opensource/hangma-bot/scripts/auto_match_status.sh
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
exec .venv/bin/python3 scripts/auto_match_status.py "$@"
