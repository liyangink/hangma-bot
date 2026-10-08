"""仅本研究的请求增强器；沿用既有凭据/响应/错误通道，不改生产闭包。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t182-step12-diagnosis-and-joint-evolution-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
import hashlib
import json
import os
from pathlib import Path

from hangma_bot.offline.vip_eoh_generate import legacy_generation_tools


class ReasoningRequestOpener:
    """转发前显式加入已核GLM推理字段，仅记录不含认证或正文的请求收据。"""
    def __init__(self, inner, receipt):
        self.inner, self.receipt = inner, Path(receipt)

    def open(self, request, timeout):
        """输入是原API请求；输出与既有opener一致；网络错误原样传播，绝不重发。"""
        body = json.loads(request.data)
        assert body["model"] == "glm-5.3"
        assert "thinking" not in body and "reasoning_effort" not in body
        body["thinking"] = {"type": "enabled"}
        body["reasoning_effort"] = "max"
        request.data = json.dumps(body, ensure_ascii=False).encode()
        receipt = {"model": body["model"], "thinking": body["thinking"],
                   "reasoning_effort": body["reasoning_effort"],
                   "max_tokens": body.get("max_tokens"),
                   "temperature": body.get("temperature"), "top_p": body.get("top_p"),
                   "seed": body.get("seed"), "prompt_request_utf8_bytes": len(request.data),
                   "request_body_sha256": hashlib.sha256(request.data).hexdigest(),
                   "source": "actual_request_body_immediately_before_one_open",
                   "provider_applied_reasoning_effort": "unknown; request is explicit",
                   "credentials_or_prompt_recorded": False}
        with self.receipt.open("x") as stream:
            json.dump(receipt, stream, ensure_ascii=False, allow_nan=False)
            stream.flush()
            os.fsync(stream.fileno())
        return self.inner.open(request, timeout=timeout)


def make_factory(receipt):
    """生成EoH API工厂；凭据仍只在原预留落盘后的build_backend读取。"""
    def factory(kind, **kwargs):
        assert kind == "api"
        transport = legacy_generation_tools().build_backend(kind, **kwargs)
        original = transport._opener
        transport._opener = lambda: ReasoningRequestOpener(original(), receipt)
        return transport
    return factory
