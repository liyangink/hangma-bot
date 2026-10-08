"""将已闭小批读回与成本诊断原件压缩归档；不删除或改写冻结原件。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t186-incremental-opportunity-repair-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
import gzip
import io
import json
import sys
import tarfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
PRIOR = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t185-evidence-prioritized-joker-evolution-1')
sys.path.insert(0, str(PRIOR))
from common import pin, save


def archive(name, paths):
    """仅收普通文件，逐字节读回核验；恢复前须核目标，禁止覆盖不同原件。"""
    target = _project_file(_PROJECT_ROOT, HERE / name)
    assert not target.exists()
    unique = sorted(set(paths))
    originals = {str(p.relative_to(HERE)): pin(p) for p in unique}
    with tarfile.open(target, "x:gz") as output:
        for p in unique:
            assert p.is_file() and not p.is_symlink()
            raw = p.read_bytes()
            item = tarfile.TarInfo(str(p.relative_to(HERE)))
            item.size, item.mode, item.mtime = len(raw), 0o644, 0
            output.addfile(item, io.BytesIO(raw))
    with tarfile.open(target, "r:gz") as stored:
        assert sorted(stored.getnames()) == sorted(originals)
        for member_name, expected in originals.items():
            raw = stored.extractfile(member_name).read()
            import hashlib
            assert {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()} == expected
    assert all(pin(_project_file(_PROJECT_ROOT, HERE / p)) == h for p, h in originals.items())
    return {"archive": target.name, "archive_pin": pin(target), "originals": originals,
        "uncompressed_bytes": sum(p["bytes"] for p in originals.values()),
        "original_files_retained_unchanged": True, "verified_exact_bytes": True}


def main():
    """闭合检查后归档静态结果；正在运行阶段仅封存已冻结计划，不封存伪终态。"""
    dispatch = _project_file(_PROJECT_ROOT, HERE / "natural-stage-001-dispatch")
    assert json.loads((dispatch / "CLOSED.json").read_text())["complete"]
    assert json.loads((dispatch / "READOUT-CLOSED.json").read_text())["complete"]
    assert json.loads((_project_file(_PROJECT_ROOT, HERE / "natural-stage-001-followup/CLOSED.json")).read_text())["complete"]
    assert json.loads((_project_file(_PROJECT_ROOT, HERE / "natural-stage-001-paths/CLOSED.json")).read_text())["complete"]
    paths = list(dispatch.rglob("*.json"))
    paths += [p for p in (_project_file(_PROJECT_ROOT, HERE / "natural-stage-001-followup")).iterdir() if p.is_file()]
    paths += [p for p in (_project_file(_PROJECT_ROOT, HERE / "natural-stage-001-paths")).iterdir() if p.is_file()]
    records = [archive("STAGE-001-CLOSED-EVIDENCE.tar.gz", paths)]
    cost_paths = []
    for directory in ("closed-choice-cost-plain", "closed-choice-cost-v2-plain", "closed-choice-cost-v2-profile"):
        cost_paths.extend(p for p in (_project_file(_PROJECT_ROOT, HERE / directory)).iterdir() if p.is_file())
    records.append(archive("CLOSED-COST-EVIDENCE.tar.gz", cost_paths))
    plan = _project_file(_PROJECT_ROOT, HERE / "NATURAL-STAGE-002-PLAN.json")
    compressed = _project_file(_PROJECT_ROOT, HERE / "NATURAL-STAGE-002-PLAN.json.gz")
    assert not compressed.exists()
    raw = plan.read_bytes()
    compressed.write_bytes(gzip.compress(raw, mtime=0))
    assert gzip.decompress(compressed.read_bytes()) == raw
    manifest = _project_file(_PROJECT_ROOT, HERE / "STAGE-001-EVIDENCE-ARCHIVE.json")
    assert not manifest.exists()
    save(manifest, {"archives": records, "frozen_stage2_plan": {
        "original": plan.name, "original_pin": pin(plan), "gzip": compressed.name, "gzip_pin": pin(compressed),
        "verified_exact_bytes": True}, "restore": "先核归档摘要及每个成员的原摘要。若目标存在且摘要不同，停止，不覆盖；否则恢复到本目录相对路径并再核摘要。",
        "raw_complete_table_streams_not_in_this_archive": True,
        "new_scores_worlds_tables_models_HTTP": 0, "original_files_removed_or_modified": False})
    print(json.dumps({"complete": True, "archives": [
        {k:r[k] for k in ("archive", "archive_pin", "uncompressed_bytes")} for r in records]}))


if __name__ == "__main__":
    main()
