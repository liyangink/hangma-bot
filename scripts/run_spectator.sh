#!/usr/bin/env bash
# 启动独立的本机观战器。它只读仓库内已经落盘的审计记录，不影响赛事 Bot。
#
# 不带 --watch-dir 启动时进入跟随模式：服务端在运行时按“runs/ 子树最近仍有写入”
# 自动发现活跃批次，自由赛换批后无需重启即可继续观战。找不到 artifacts/sessions/
# 时回退到服务端默认 ./runs。显式传 --watch-dir 时完全按传参固定目录。
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

has_watch_dir=0
for arg in "$@"; do
  case "$arg" in
    --watch-dir|--watch-dir=*) has_watch_dir=1 ;;
  esac
done

if [ "$has_watch_dir" -eq 0 ] && [ -d "$repo_root/artifacts/sessions" ]; then
  # 跟随模式：目录发现与换批切换都在 Python 侧完成，这里只给父目录。
  exec python3 spectator/server.py --follow-live-sessions "$repo_root/artifacts/sessions" "$@"
fi

if [ "$has_watch_dir" -eq 0 ]; then
  echo '未发现 artifacts/sessions/，回退到服务端默认 ./runs。' >&2
fi

# 其余参数（例如 --port、--once 或显式 --watch-dir）原样交给观战器。
exec python3 spectator/server.py "$@"
