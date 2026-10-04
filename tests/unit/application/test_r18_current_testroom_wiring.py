"""新实验R18不能冒充正式包；混合房四个身份各自携带精确摘要。"""
import importlib.util
import json
from pathlib import Path

import pytest
import hangma_bot.bootstrap as b


def config(tmp_path, **changes):
    """假Token只验证组合根入口，绝不创建官方连接。"""
    p = b._load_r18_current_testroom_manifest()
    data = dict(mode='test_room', token_kind='test', token='fake-local-only',
        base_url='https://platform.invalid', expected_tournament_id='t-local',
        known_guide_version=p['known_guide_version'], audit_root=str(tmp_path),
        strategy=b.R18_CURRENT_TESTROOM_STRATEGY, sse_enabled=True,
        expected_policy_release_id=p['release_package_id'])
    data.update(changes)
    return b.runtime_config_from_mapping(data)


def test_new_r18_is_bound_testroom_control_and_default_is_unchanged(tmp_path):
    c = config(tmp_path)
    assert c.strategy == b.R18_CURRENT_TESTROOM_STRATEGY
    assert b.DEFAULT_STRATEGY == 'weighted_heuristic'
    p = b._load_r18_current_testroom_manifest(c.expected_policy_release_id)
    assert p['allowed_modes'] == ['test_room']
    assert p['strength_admission'] is False and p['production_default'] is False
    assert p['params']['value_limits'] == {'max_expansions': 2048, 'max_routes_per_candidate': 128}


@pytest.mark.parametrize('mode,kind', [('auto_match','official'),
    ('test_tournament','test'), ('official_tournament','official')])
def test_experimental_r18_does_not_inherit_formal_or_free_permission(tmp_path, mode, kind):
    with pytest.raises(ValueError, match='仅允许测试房'):
        config(tmp_path, mode=mode, token_kind=kind)


@pytest.mark.parametrize('changes', [{'sse_enabled':False},
    {'expected_policy_release_id':None}, {'expected_policy_release_id':'0'*64},
    {'known_guide_version':34}])
def test_explicit_current_identity_sse_and_guide_are_required(tmp_path, changes):
    with pytest.raises(ValueError):
        config(tmp_path, **changes)


def test_r18_runtime_rechecks_source_before_resource_ownership(tmp_path, monkeypatch):
    c = config(tmp_path)
    monkeypatch.setattr(b, '_vip_runtime_sources', lambda: {'drift':'0'*64})
    created = []
    monkeypatch.setattr(b, 'JsonlAuditSink', lambda *a, **k: created.append('audit'))
    with pytest.raises(RuntimeError, match='源码摘要漂移'):
        b.build_runtime(c, session_factory=lambda: created.append('http'))
    assert created == []


@pytest.mark.parametrize('field,value', [('allowed_modes',['official_tournament']),
    ('strength_admission',True), ('production_default',True)])
def test_even_rehashed_manifest_cannot_expand_r18_permissions(tmp_path, monkeypatch, field, value):
    p = b._load_r18_current_testroom_manifest()
    p[field] = value
    p['release_package_id'] = b._vip_package_id(p)
    path = tmp_path / 'bad.json'
    path.write_text(json.dumps(p))
    monkeypatch.setattr(b, 'R18_CURRENT_TESTROOM_MANIFEST', str(path))
    with pytest.raises(RuntimeError, match='范围、参数'):
        b._load_r18_current_testroom_manifest()


def test_mixed_room_keeps_two_distinct_package_bindings_per_seat(tmp_path):
    """通过公开脚本配置接口检查真实子进程映射，不读取私有状态。"""
    path = Path(__file__).resolve().parents[3] / 'scripts/run_test_room.py'
    spec = importlib.util.spec_from_file_location('mixed_room_contract', path)
    room = importlib.util.module_from_spec(spec)
    import sys
    sys.modules[spec.name] = room
    spec.loader.exec_module(room)
    r18 = b._load_r18_current_testroom_manifest()
    vip = b._load_vip_testroom_manifest()
    names = [b.VIP_S02_TESTROOM_STRATEGY, b.R18_CURRENT_TESTROOM_STRATEGY] * 2
    ids = [vip['release_package_id'], r18['release_package_id']] * 2
    data = dict(mode='test_room', base_url='https://platform.invalid', expected_tournament_id='t-local',
        known_guide_version=35, audit_root=str(tmp_path/'room'), sse_enabled=True,
        discard_pacing_enabled=False, strategy=b.VIP_S02_TESTROOM_STRATEGY,
        identities=[dict(slot=slot, token='fake-'+slot, strategy=name,
                         expected_policy_release_id=identity)
                    for slot, name, identity in zip(['A','B','C','D'], names, ids)])
    file = tmp_path / 'room.json'
    file.write_text(json.dumps(data))
    parsed = room.load_room_config(file, environ={})
    for seat, name, identity in zip(parsed.identities, names, ids):
        child = room.child_config_mapping(parsed, seat)
        assert child['strategy'] == name and child['expected_policy_release_id'] == identity
        child.update(token='fake-child')
        child.pop('token_env')
        assert b.runtime_config_from_mapping(child).strategy == name
