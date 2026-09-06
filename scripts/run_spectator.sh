#!/usr/bin/env bash
# 启动独立的本机观战器。它只读仓库 runs/ 中已经落盘的审计记录。
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

# 未传 --watch-dir 时，服务端默认读取此处的 ./runs。其余参数（例如 --port、
# --once 或显式 --watch-dir）原样交给观战器，且不会影响赛事 Bot。
exec python3 spectator/server.py "$@"
