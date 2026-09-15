#!/usr/bin/env bash
# 启动评估库查看器并自动打开浏览器。
#
# 用法：
#   bash scripts/run_datamart.sh                 # 127.0.0.1:8787，自动开浏览器
#   bash scripts/run_datamart.sh --port 9000
#   bash scripts/run_datamart.sh --no-open       # 只起服务，不开浏览器
#   bash scripts/run_datamart.sh --rebuild       # 先从仓库内数据池重建库再启动
#
# 默认只绑定本机回环地址；对外开放需显式传 --host，并会打印安全警告。
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

# 选一个可用的解释器：优先仓库 .venv，其次 python3。
PY=""
for candidate in "$repo_root/.venv/bin/python" "$(command -v python3 || true)"; do
  if [[ -n "$candidate" && -x "$candidate" ]] && "$candidate" -c 'import sqlite3' >/dev/null 2>&1; then
    PY="$candidate"; break
  fi
done
if [[ -z "$PY" ]]; then
  echo "找不到可用的 Python（需要标准库 sqlite3）；请先安装 Python 3.9+" >&2
  exit 1
fi

if [[ ! -f "$repo_root/datamart/hangma-eval.db" ]]; then
  echo "评估库不存在，正在从仓库内数据池重建…"
  "$PY" datamart/build.py
fi

exec "$PY" datamart/serve.py "$@"
