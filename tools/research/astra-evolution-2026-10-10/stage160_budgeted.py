"""完整160单局评估：世界沿用逻辑时钟，候选增强计入真实经过时间。

不修改已冻结旧驱动。800是模拟预算的单调秒原点；每次choose独立重置，
父策略及辅助计算耗时均推进候选时钟，三段原截止原样传递。规则分析在
choose前完成，网络与应用排队未计入；本模式仍不能代替线上时限准入。
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import time

import stage160 as stage
from stage160_metrics import MetricsAudit


class RequestElapsedClock:
    """一次公开策略请求内的相对单调时钟，单位秒；空闲时禁止读取。"""
    def __init__(self, monotonic=time.monotonic, origin=800.0):
        self.monotonic = monotonic
        self.origin = origin
        self.started = None

    def begin(self):
        """在choose入口记录真实时刻；同一策略不允许请求重叠。"""
        if self.started is not None:
            raise RuntimeError('同一候选请求重叠')
        self.started = self.monotonic()

    def __call__(self):
        if self.started is None:
            raise RuntimeError('候选时钟只在choose内有效')
        return self.origin + self.monotonic() - self.started

    def end(self):
        """正常完成或异常均清理请求时基，不把上一窗耗时带入下一窗。"""
        self.started = None


class ElapsedPolicy:
    """透传公开策略接口和审计属性，仅为本次choose启用候选经过时钟。"""
    def __init__(self, inner, clock):
        self.inner = inner
        self.clock = clock

    def __getattr__(self, name):
        return getattr(self.inner, name)

    async def choose(self, request, budget):
        """不重建、不延长原预算；异常继续交给严格评估驱动处理。"""
        self.clock.begin()
        try:
            return await self.inner.choose(request, budget)
        finally:
            self.clock.end()


def candidate_policy(parent, candidate):
    """验签工厂和辅助源码，注入真实经过时钟并核对交付候选身份。"""
    if candidate['kind'] == 'P0_identity':
        return parent
    path = Path(candidate['factory_path'])
    if stage.file_sha(path) != candidate['factory_sha256']:
        raise RuntimeError('候选源码漂移')
    for auxiliary, digest in candidate.get('auxiliary_files', {}).items():
        if stage.file_sha(auxiliary) != digest:
            raise RuntimeError('候选辅助来源漂移: ' + auxiliary)
    name = '_astra_elapsed_candidate_' + candidate['factory_sha256'][:16]
    if name not in sys.modules:
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        sys.modules[name] = module
    clock = RequestElapsedClock()
    inner = sys.modules[name].build_policy(parent, clock=clock, params=candidate.get('params'))
    if inner.candidate_id != candidate['expected_candidate_id']:
        raise RuntimeError('候选身份与事前声明不符')
    return ElapsedPolicy(inner, clock)


_base_worker = stage.worker


def worker(task):
    """spawn进程中接入经过时钟和只读牌效审计；生产核心保持冻结。"""
    stage.candidate_policy = candidate_policy
    stage.FocalAudit = MetricsAudit
    return _base_worker(task)


def main():
    stage.worker = worker
    stage.main()


if __name__ == '__main__':
    main()
