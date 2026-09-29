#!/usr/bin/env bash
# 自由赛连续巡检入口。macOS 上防止空闲系统休眠跨过官方 finished 短暂可见期。
# 每次调用的结算、锁和止损语义仍由 auto_match_watch.sh / watchdog 独占。
set -u

watch_repo_root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$watch_repo_root"
mkdir -p runs/auto-match-watchdog

if [ "$(uname -s)" = "Darwin" ] && [ "${1:-}" != "--inside-caffeinate" ]; then
    if ! command -v caffeinate >/dev/null 2>&1; then
        printf 'macOS 缺少 caffeinate；拒绝在无防休眠保护下连续巡检\n' >&2
        exit 3
    fi
    exec caffeinate -is bash "$0" --inside-caffeinate
fi

printf '%s\n' "$$" > runs/auto-match-watchdog/watch-loop.pid
while true; do
    bash scripts/auto_match_watch.sh
    watch_status=$?
    if [ "$watch_status" -ne 0 ]; then
        printf '自由赛连续巡检已停：watchdog 退出码 %s\n' "$watch_status" >&2
        exit "$watch_status"
    fi
    sleep 60
done
