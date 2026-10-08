"""定位共享工具与本机研究原件，保留历史记录中的逻辑路径和字节身份。"""

from __future__ import annotations

from functools import lru_cache
import json
import os
from pathlib import Path


@lru_cache(maxsize=32)
def _shared_paths(root: Path) -> dict[str, str]:
    """读取检出内的迁移索引；冻结运行根可只包含实际使用的共享文件。"""
    path = root / "doc/research/storage-map.json"
    if not path.is_file():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return dict(payload["shared_paths"])


def project_file(root: Path, source: str | Path) -> Path:
    """返回文件实际位置，不读取原件、不改写记录，也不下载缺失数据。

    ``root`` 是源码或冻结运行根。``source`` 可以是历史相对路径或绝对路径。
    共享代码和必要合同优先取迁移索引；研究数据由本机数据根定位。
    ``HANGMA_OFFLINE_DATA_ROOT`` 指定包含 review/datasets 等子目录的数据根，
    默认使用检出内的 local-data。根外的显式输入保持调用者提供的位置。
    """
    root = Path(root).absolute()
    source = Path(source)
    data_root = Path(os.environ.get("HANGMA_OFFLINE_DATA_ROOT", root / "local-data"))
    if not data_root.is_absolute():
        data_root = root / data_root
    if source.is_absolute():
        if source.is_relative_to(data_root):
            source = source.relative_to(data_root)
        else:
            try:
                source = source.relative_to(root)
            except ValueError:
                return source
    relative = source
    if ".." in relative.parts:
        raise ValueError("项目文件路径不能包含父目录跳转")
    mapped = _shared_paths(root).get(relative.as_posix())
    if mapped is not None:
        target = Path(mapped)
        if target.is_absolute() or ".." in target.parts:
            raise ValueError("共享文件迁移索引必须指向检出内的相对路径")
        if target.parts[:2] == ("tests", "fixtures"):
            # 历史数据在本机时读原件；共享夹具仅供明确的测试运行使用。
            original = root / relative
            migrated = data_root / relative
            if original.exists():
                return original
            if migrated.exists():
                return migrated
            if os.environ.get("HANGMA_OFFLINE_TEST_FIXTURES") != "1":
                return migrated
        return root / target
    if relative.parts and relative.parts[0] in {
        "review", "datasets", "game-records", "datamart"
    }:
        migrated = data_root / relative
        if migrated.exists() or not (root / relative).exists():
            return migrated
    return root / relative
