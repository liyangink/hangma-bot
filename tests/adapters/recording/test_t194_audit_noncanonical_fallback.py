"""T194公共红例回归：探测非原生容器不能提前消费旧路径的输入。"""
import json
from hangma_bot.adapters.recording import JsonlAuditSink
from hangma_bot.application.contracts import AuditKind
from recording._helpers import make_record


async def test_noncanonical_dict_consumed_only_by_legacy_encoding(tmp_path):
    """真正E1落盘value=1；错误探测会先消费一次再fallback，误写value=2。"""
    class StatefulDict(dict):
        def __init__(self):
            super().__init__(value='seed')
            self.calls=0
        def items(self):
            self.calls+=1
            return [('value',self.calls)]
    sink=JsonlAuditSink(tmp_path,'run-1')
    receipt=sink.emit(make_record(AuditKind.LIFECYCLE_CHANGED,
        {'status':'running','data':StatefulDict()}))
    assert receipt.queued and not receipt.audit_degraded
    summary=await sink.aclose(timeout_seconds=2)
    assert summary.written==1 and summary.serialization_failures==0
    document=json.loads((tmp_path/'runs/run-1/lifecycle.jsonl').read_text())
    assert document['payload']=={'status':'running','data':{'value':1}}
