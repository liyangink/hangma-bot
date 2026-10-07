#!/usr/bin/env bash
# 在参赛前准备独立环境；运行与信号处理仍由原参赛入口负责。
set -euo pipefail

case "${1:-}" in
    check|start) ;;
    -h|--help)
        echo '检查赛事：bash participate.sh check'
        echo '启动比赛：bash participate.sh start'
        echo '测试赛事：在上述命令末尾加 --test'
        exit 0 ;;
    *) echo '用法：bash participate.sh check|start [--test] [--token-file 文件]' >&2; exit 2 ;;
esac

if [[ "$(uname -s)" != Darwin || "$(uname -m)" != arm64 ]]; then
    echo '当前正式策略包只支持 Apple Silicon Mac；Windows／Linux 尚需对应平台发布包。' >&2
    exit 2
fi

task_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$task_root"
umask 077
task_runtime="$task_root/.private/participant-runtime"
task_python="$task_runtime/venv/bin/python"
mkdir -p "$task_runtime"

# 指纹只用于判断是否需要安装；正式包、源码和二进制仍由组合根校验。
task_fingerprint="$(
    printf '%s\n' "$task_root"
    shasum -a 256 pyproject.toml hatch_build.py prebuilt/hangma/manifest.json \
        prebuilt/hangma/cp311-macosx_11_0_arm64/_grouped_native.cpython-311-darwin.so \
        src/hangma_bot/hangma/_grouped_native.c src/hangma_bot/hangma/_standard_python.py
)"
task_installed="$(cat "$task_runtime/install.sha256" 2>/dev/null || true)"
if [[ "$task_installed" != "$task_fingerprint" ]] || ! "$task_python" -c \
    'import sys, httpx; assert sys.implementation.name == "cpython" and sys.version_info[:2] == (3, 11)' \
    >/dev/null 2>&1; then
    echo '正在自动准备参赛环境（首次需要联网）...'
    task_uv="$(command -v uv || true)"
    if [[ -z "$task_uv" ]]; then
        task_uv="$task_runtime/tools/uv"
        if [[ ! -x "$task_uv" ]]; then
            curl --fail --silent --show-error --location --proto '=https' --tlsv1.2 \
                https://astral.sh/uv/0.11.1/install.sh -o "$task_runtime/uv-install.sh"
            UV_UNMANAGED_INSTALL="$task_runtime/tools" sh "$task_runtime/uv-install.sh"
            rm -f "$task_runtime/uv-install.sh"
        fi
    fi
    export UV_CACHE_DIR="$task_runtime/cache"
    export UV_PYTHON_INSTALL_DIR="$task_runtime/python"
    if [[ ! -x "$task_python" ]]; then
        "$task_uv" venv --python 3.11 "$task_runtime/venv"
    fi
    "$task_python" -c 'import sys; assert sys.implementation.name == "cpython" and sys.version_info[:2] == (3, 11)' \
        || { echo '专用参赛环境不是 CPython 3.11，请移走 .private/participant-runtime 后重试。' >&2; exit 2; }
    HANGMA_NATIVE=prebuilt "$task_uv" pip install --python "$task_python" -e .
    printf '%s\n' "$task_fingerprint" > "$task_runtime/install.sha256"
fi

exec "$task_python" scripts/participate.py "$@"
