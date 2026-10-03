"""自由赛显式冻结身份、无副作用拒绝与计算预热/关闭；不授强度。"""
import asyncio
from dataclasses import replace
from types import SimpleNamespace
import pytest
import hangma_bot.bootstrap as b
from hangma_bot.application.auto_match_runtime import AutoMatchSettings


def configuration(tmp_path, **changes):
    package=b._load_vip_free_manifest()
    data=dict(mode='auto_match',token_kind='official',token='fake-test-only',
        base_url='https://platform.invalid',expected_tournament_id='',known_guide_version=package['known_guide_version'],
        audit_root=str(tmp_path),strategy=b.VIP_S02_FREE_STRATEGY,sse_enabled=True,
        expected_policy_release_id=package['release_package_id'])
    data.update(changes)
    return b.runtime_config_from_mapping(data)


@pytest.mark.parametrize('mode,kind', [('test_room','test'),('test_tournament','test'),('official_tournament','official')])
def test_free_package_rejects_all_other_modes(tmp_path,mode,kind):
    with pytest.raises(ValueError,match='不授其他运行模式'):
        configuration(tmp_path,mode=mode,token_kind=kind,expected_tournament_id='t-local')


@pytest.mark.parametrize('changes',[{'sse_enabled':False},{'expected_policy_release_id':None},{'expected_policy_release_id':'0'*64}])
def test_free_requires_exact_binding_and_sse(tmp_path,changes):
    with pytest.raises(ValueError):configuration(tmp_path,**changes)


def test_free_rechecks_drift_before_http_or_audit(tmp_path,monkeypatch):
    config=configuration(tmp_path);created=[]
    monkeypatch.setattr(b,'_vip_runtime_sources',lambda:{'changed':'0'*64})
    monkeypatch.setattr(b,'JsonlAuditSink',lambda *a,**k:created.append('audit'))
    with pytest.raises(RuntimeError,match='源码摘要漂移'):
        b.build_auto_match_runtime(config,AutoMatchSettings('test-only'),session_factory=lambda:created.append('http'))
    assert not created


def test_free_does_not_enter_participant_assembly(tmp_path):
    config=configuration(tmp_path)
    with pytest.raises(ValueError,match='必须使用build_auto_match_runtime'):b.build_runtime(config)


@pytest.mark.parametrize('failure',['start','cancel-start','runtime',None])
async def test_free_warms_before_match_and_closes_on_every_exit(failure):
    events=[]
    class Compute:
        async def start(self):
            events.append('warm')
            if failure=='start':raise RuntimeError('test-start')
            if failure=='cancel-start':raise asyncio.CancelledError()
        async def close(self):events.append('compute-close')
    class Runtime:
        async def run(self):
            events.append('match')
            try:
                if failure=='runtime':raise RuntimeError('test-runtime')
                return 'finished'
            finally:events.extend(['http-close','audit-close'])
    class Session:
        async def aclose(self):events.append('http-close')
    class Sink:
        async def aclose(self,timeout_seconds):events.append('audit-close')
    unit=b.AssembledAutoMatchRuntime(SimpleNamespace(),AutoMatchSettings('test-only'),'fake',Sink(),Session(),Compute(),Runtime(),Compute())
    if failure:
        with pytest.raises(asyncio.CancelledError if failure=='cancel-start' else RuntimeError):await unit.run()
    else:assert await unit.run()=='finished'
    assert events==(['warm','compute-close','http-close','audit-close'] if failure in ('start','cancel-start') else ['warm','match','http-close','audit-close','compute-close'])


@pytest.mark.parametrize("base_url", ["https://platform.invalid:abc", "https://platform.invalid:65536", "https:///empty-host"])
def test_url_constructor_fault_rejected_before_assembly(tmp_path,base_url,monkeypatch):
    created=[]
    monkeypatch.setattr(b,"JsonlAuditSink",lambda *a,**k:created.append("audit"))
    with pytest.raises(ValueError):configuration(tmp_path,base_url=base_url)
    assert not created
