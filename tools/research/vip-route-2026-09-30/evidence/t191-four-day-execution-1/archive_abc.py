"""封存已自然闭合的186单局原件，逐成员校验并实际临时恢复；不改原件。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t191-four-day-execution-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
import gzip
import hashlib
import json
import tarfile
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = _PROJECT_ROOT
import sys
sys.path.insert(0, str(_project_file(_PROJECT_ROOT, HERE / "evaluation")))
from abc_support import background_priority, pin, read, require, save


def main():
    """仅封存已验签固定批；分块按未压缩16MiB，不读认证或启动研究。"""
    background_priority()
    closed_path = _project_file(_PROJECT_ROOT, HERE / "evaluation/SPEED-ABC-CLOSED.json")
    closed = read(closed_path)
    require(closed["complete"] and closed["source_stable"] and closed["resources_released"], "条件批未闭合")
    base = _project_file(_PROJECT_ROOT, HERE / "evaluation/speed-abc")
    paths = sorted(path for path in base.rglob("*") if path.is_file() and path.suffix != ".lock")
    paths.append(closed_path)
    require(all(path.is_relative_to(HERE) for path in paths), "归档越过本阶段")
    for path, expected in closed["files"].items():
        require(pin(Path(path)) == expected, "闭合原件漂移")
    refs = {str(path.relative_to(ROOT)): pin(path) for path in paths}
    groups, current, total = [], [], 0
    for path in paths:
        size = path.stat().st_size
        if current and total + size > 16 * 1024 * 1024:
            groups.append(current)
            current, total = [], 0
        current.append(path)
        total += size
    if current:
        groups.append(current)
    destination = _project_file(_PROJECT_ROOT, HERE / "abc-archive")
    destination.mkdir(exist_ok=False)
    archives, restored = [], set()
    with tempfile.TemporaryDirectory(prefix="t191-abc-restore-") as temporary:
        temp = Path(temporary)
        for index, group in enumerate(groups, 1):
            target = destination / f"part-{index:03d}.tar.gz"
            with target.open("xb") as raw:
                with gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as compressed:
                    with tarfile.open(fileobj=compressed, mode="w|") as archive:
                        for path in group:
                            name = str(path.relative_to(ROOT))
                            require(pin(path) == refs[name], "归档读取时原件漂移")
                            info = tarfile.TarInfo(name)
                            info.size, info.mode, info.mtime = path.stat().st_size, 0o644, 0
                            with path.open("rb") as source:
                                archive.addfile(info, source)
            with tarfile.open(target, "r:gz") as archive:
                for member in archive:
                    require(member.isfile() and member.name in refs and member.name not in restored,
                        "未知、非文件或重复归档成员")
                    relative = Path(member.name)
                    require(not relative.is_absolute() and ".." not in relative.parts, "归档路径越界")
                    restored_path = temp / relative
                    restored_path.parent.mkdir(parents=True, exist_ok=True)
                    digest, size = hashlib.sha256(), 0
                    with archive.extractfile(member) as source, restored_path.open("xb") as output:
                        while block := source.read(1024 * 1024):
                            output.write(block)
                            digest.update(block)
                            size += len(block)
                    require({"bytes": size, "sha256": digest.hexdigest()} == refs[member.name]
                        and pin(restored_path) == refs[member.name], "实际恢复原字节不一致")
                    restored.add(member.name)
            archives.append({"path": str(target.relative_to(HERE)), **pin(target), "members": len(group)})
    require(restored == set(refs) and all(pin(_project_file(_PROJECT_ROOT, ROOT / name)) == expected for name, expected in refs.items()),
        "成员不齐或封存后原件漂移")
    save(destination / "VERIFIED.json", {"complete": True, "source_closed_pin": pin(closed_path),
        "archives": archives, "members": refs, "all_members_actually_restored_and_exact": True,
        "original_files_preserved": True, "script_pin": pin(Path(__file__)),
        "new_scores_worlds_tables_models_HTTP": 0})
    print(json.dumps({"complete": True, "members": len(restored), "parts": len(archives),
        "compressed_bytes": sum(row["bytes"] for row in archives), "actual_restore_verified": True}))


if __name__ == "__main__":
    main()
