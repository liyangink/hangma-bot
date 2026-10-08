"""确认执行身份的持久原件、模拟依赖与自洽旧赛程漂移反例。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
import copy
import pytest
import confirmation_execution_identity as identity


@pytest.fixture
def fake_manifest(monkeypatch):
    state={'simulator':'v1','baseline':'v1','statistics':'v1'}
    monkeypatch.setattr(identity.batch.search,'av_frozen_manifest',lambda:copy.deepcopy(state))
    monkeypatch.setattr(identity.batch.search,'av_frozen_manifest_digest',identity.pairing.draft.digest)
    return state


def test_snapshot_roundtrip_and_source_change(tmp_path,fake_manifest):
    source=tmp_path/'candidate.py';source.write_text('old')
    frozen=identity.capture(source_paths=[source])
    assert identity.verify(copy.deepcopy(frozen))==frozen['production_digest']
    source.write_text('new')
    with pytest.raises(ValueError,match='漂移'):identity.verify(frozen)


@pytest.mark.parametrize('surface',['simulator','baseline','statistics'])
def test_dependency_changes_refuse(surface,tmp_path,fake_manifest):
    frozen=identity.capture(source_paths=[])
    fake_manifest[surface]='v2'
    with pytest.raises(ValueError,match='漂移'):identity.verify(frozen)


def test_corrupted_frozen_manifest_refuses(fake_manifest):
    frozen=identity.capture(source_paths=[])
    frozen['production_manifest']['simulator']='forged'
    with pytest.raises(ValueError,match='漂移'):identity.verify(frozen)


def test_self_consistent_old_root_runtime_refuses():
    contract=identity.batch.read(identity.batch.ROUTE/'contracts/group-dev-v1.json')
    root=identity.pairing.build_root_plan(contract=contract,registration_seed=91237,opponent='H',root_index=1)
    identity.verify_root_runtime(root)
    root['runtime_identity']['source_sha256']['shuffle']='0'*64
    body=dict(root);body.pop('root_content_digest')
    root['root_content_digest']=identity.pairing.draft.digest(body)
    with pytest.raises(ValueError,match='运行身份'):identity.verify_root_runtime(root)
