"""核对共享仓库的跟踪范围，阻止本机大数据重新进入 Git。"""

from __future__ import annotations

import subprocess
from pathlib import PurePosixPath

LOCAL_ROOTS = {"review", "local-data", "datasets", "game-records", "datamart",
               "artifacts", ".private", "runs", "bundles", "derived", "exports"}


def main() -> int:
    """只读当前提交的路径和对象长度；失败打印路径，不读取文件正文。"""
    output = subprocess.check_output(["git", "ls-tree", "-rlz", "HEAD"])
    failures = []
    total = 0
    for record in output.split(b"\0"):
        if not record:
            continue
        metadata, name = record.split(b"\t", 1)
        fields = metadata.split()
        if fields[1] != b"blob":
            continue
        path = name.decode("utf-8")
        size = int(fields[3])
        total += size
        if PurePosixPath(path).parts[0] in LOCAL_ROOTS:
            failures.append("本机数据仍在跟踪：" + path)
        if size > 5 * 1024 * 1024:
            failures.append("共享单文件超过 5 MiB，请核定必要性：" + path)
    for failure in failures:
        print(failure)
    print(f"当前共享文件合计 {total / 1024**2:.2f} MiB；范围违规 {len(failures)} 项")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
