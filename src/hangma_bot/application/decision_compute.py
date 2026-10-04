"""有界计算进程：只搬运玩家可见请求和计划，不拥有 HTTP 或规则裁决。"""
from __future__ import annotations

import asyncio
import pickle
import hashlib
import json
import multiprocessing
import socket
import struct
from dataclasses import dataclass, field
from concurrent.futures import Future, ThreadPoolExecutor
import threading
from math import isfinite
from typing import Callable

from hangma_bot.application.audit_codec import (
    decision_plan_from_json, decision_plan_to_json,
)
from hangma_bot.application.deadline import RuntimeClock
from hangma_bot.policy.interface import BotPolicy, DecisionBudget, DecisionPlan, DecisionRequest


class DecisionComputeError(RuntimeError):
    """计算服务拒绝或失败；应用层据此使用预先准备的合法紧急动作。"""


@dataclass(frozen=True)
class PreparedDecisionPolicy:
    """子进程组合结果；身份须由工厂根据实际源码/依赖核实，不能仅回显配置。"""
    policy: BotPolicy
    execution_id: str  # 实际装载的完整执行身份，不含 Token 或隐藏牌局信息


@dataclass(frozen=True)
class DecisionComputeSettings:
    """每身份固定资源上限；所有持续时间单位为真实秒。"""
    workers: int = 2
    max_pending: int = 8
    max_message_bytes: int = 16 * 1024 * 1024
    startup_seconds: float = 5.0
    max_job_seconds: float = 3.0  # 即使调用方给出很远截止，卡死计算仍有硬上限
    abandon_grace_seconds: float = 0.1  # 取消/过期后仍未退出则终止对应计算进程
    resource_reap_seconds: float = 1.0  # 单次资源回收等待上限；失败仍保留迟到清理所有权
    max_restarts: int = 2  # 每槽整个服务生命周期的重启上限，不随请求重置

    def __post_init__(self):
        for name in ('workers', 'max_message_bytes'):
            if type(getattr(self, name)) is not int or getattr(self, name) <= 0:
                raise ValueError(name)
        for name in ('max_pending', 'max_restarts'):
            if type(getattr(self, name)) is not int or getattr(self, name) < 0:
                raise ValueError(name)
        for name in ('startup_seconds', 'max_job_seconds', 'abandon_grace_seconds', 'resource_reap_seconds'):
            value = getattr(self, name)
            if type(value) not in (int, float) or not isfinite(value) or value <= 0:
                raise ValueError(name)


def _encode(payload, limit):
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True,
                     separators=(',', ':'), allow_nan=False).encode()
    if len(raw) > limit:
        raise DecisionComputeError('MESSAGE_LIMIT')
    return raw


def _pack_job(number, request, budget, limit):
    """在服务独占的有限传输线程中编码；可信pickle不再经base64和整包JSON重复编码。"""
    body = pickle.dumps((number, request, budget), protocol=5)
    if len(body) > limit:
        raise DecisionComputeError('MESSAGE_LIMIT')
    digest = hashlib.sha256(body).hexdigest()
    header = _encode(dict(job_id=number, digest=digest), 4096)
    wire = struct.pack('!I', len(header)) + header + body
    if len(wire) > limit:
        raise DecisionComputeError('MESSAGE_LIMIT')
    return wire, digest


def _decode_message(raw):
    """传输线程恢复JSON及计划值对象，父事件循环仅做有界身份/候选检查。"""
    message = json.loads(raw)
    if 'plan' in message:
        message['plan'] = decision_plan_from_json(message['plan'])
    return message


def _read_sync(sock, size):
    chunks = bytearray()
    while len(chunks) < size:
        block = sock.recv(size - len(chunks))
        if not block:
            raise EOFError()
        chunks.extend(block)
    return bytes(chunks)


def _worker_entry(sock, factory, expected_id, limit):
    """spawn 子进程入口；具体策略由组合根传入的可序列化工厂创建。"""
    def send(payload):
        raw = _encode(payload, limit)
        sock.sendall(struct.pack('!I', len(raw)) + raw)
    try:
        prepared = factory()
        if prepared.execution_id != expected_id:
            raise DecisionComputeError('EXECUTION_ID_MISMATCH')
        send({'kind': 'ready', 'execution_id': prepared.execution_id})
        while True:
            size = struct.unpack('!I', _read_sync(sock, 4))[0]
            if size > limit:
                raise DecisionComputeError('MESSAGE_LIMIT')
            frame = _read_sync(sock, size)
            header_size = struct.unpack('!I', frame[:4])[0]
            if header_size > 4096 or header_size + 4 > len(frame):
                raise DecisionComputeError('MESSAGE_HEADER_LIMIT')
            header = json.loads(frame[4:4 + header_size])
            body = frame[4 + header_size:]
            if hashlib.sha256(body).hexdigest() != header['digest']:
                raise DecisionComputeError('INPUT_DIGEST_MISMATCH')
            envelope = dict(kind='result', execution_id=prepared.execution_id,
                            job_id=header['job_id'], digest=header['digest'])
            try:
                # 只解码私有父进程由可信规则核心构造的完整值对象；无外部入口。
                number, request, budget = pickle.loads(body)
                if (number != header['job_id'] or not isinstance(request, DecisionRequest)
                        or not isinstance(budget, DecisionBudget)):
                    raise DecisionComputeError('REQUEST_TYPE_MISMATCH')
                plan = asyncio.run(prepared.policy.choose(request, budget))
                envelope['plan'] = decision_plan_to_json(plan)
                send(envelope)
            except Exception as exc:
                # 不传任意异常文本，避免意外导出候选/基础设施敏感内容。
                envelope['error'] = type(exc).__name__
                send(envelope)
    except (EOFError, BrokenPipeError, ConnectionResetError):
        pass
    except Exception:
        try:
            send({'kind': 'failed'})
        except Exception:
            pass
    finally:
        sock.close()


@dataclass
class _Job:
    number: int
    request: DecisionRequest
    budget: DecisionBudget
    future: asyncio.Future
    digest: str | None = None
    wire_started: bool = False  # 已开始向子进程写入；仅父侧编码不能视为子进程工作。
    reply_received: bool = False  # 完整响应已读入父侧；解码仍归原槽，但子进程已结束本次计算。
    deadline: asyncio.TimerHandle | None = None
    reap: asyncio.TimerHandle | None = None


@dataclass
class _Slot:
    wake: asyncio.Event = field(default_factory=asyncio.Event)
    task: asyncio.Task | None = None
    process: object = None
    writer: asyncio.StreamWriter | None = None
    ready: bool = False
    active: _Job | None = None
    restarts: int = 0
    start_future: object = None  # 实际spawn线程future，取消async等待不能丢弃所有权
    parent_socket: object = None
    child_socket: object = None
    late_reap_future: object = None  # 回收期限之后的自动清理；不依赖调用方再close
    late_reap_thread: object = None  # 每槽最多一个独占迟到清理线程，只在退出退化时启用


class BoundedDecisionCompute:
    """实现 choose 接缝的应用计算服务；start/close 由组合根显式拥有。

    截止为注入 RuntimeClock 的原本机单调时钟秒值，排队不重建预算。
    工厂只能携带可信策略装配配置，禁止 Token/WorldState；结果仍须经过
    原应用层规则复核和官方 ActionGate。服务不保存已完成请求历史。
    """
    def __init__(self, factory: Callable[[], PreparedDecisionPolicy], *, execution_id: str,
                 clock: RuntimeClock, settings: DecisionComputeSettings):
        if not execution_id or not isinstance(execution_id, str):
            raise ValueError('execution_id')
        self.factory, self.execution_id = factory, execution_id
        self.clock, self.settings = clock, settings
        self._slots = [_Slot() for _ in range(settings.workers)]
        self._jobs = {}
        self._pending = []
        self._current = {}
        self._number = 0
        self._transport_futures = set()  # 至多workers份未结束传输；不借用全局默认线程池
        self._transport_threads = set()  # 每服务最多workers个固定线程，退出时逐个确认结束
        self._thread_lock = threading.Lock()
        self._transport = ThreadPoolExecutor(max_workers=settings.workers,
            thread_name_prefix='hangma-decision-transport', initializer=self._register_transport_thread)
        self._started = self._closed = False
        self._close_task = None  # 并发退出共享同一个资源回收所有者
        self._counts = dict(submitted=0, dispatched=0, completed=0, discarded=0,
                            rejected=0, faults=0, policy_failures=0, process_starts=0, restarts=0,
                            peak_owned=0, peak_pending=0, peak_transport=0)

    def snapshot(self):
        """固定大小诊断计数及当前资源量；不暴露请求内容或无限增长的历史列表。"""
        with self._thread_lock:
            self._transport_futures = {f for f in self._transport_futures if not f.done()}
            transport_inflight = len(self._transport_futures)
            threads_alive = sum(t.is_alive() for t in self._transport_threads)
        return dict(self._counts, transport_inflight=transport_inflight,
                    late_reap_inflight=sum(s.late_reap_future is not None and not s.late_reap_future.done()
                                          for s in self._slots),
                    late_reap_threads_alive=sum(s.late_reap_thread is not None and s.late_reap_thread.is_alive()
                                               for s in self._slots),
                    transport_threads_alive=threads_alive,
                    owned=len(self._jobs), pending=len(self._pending),
                    active=sum(s.active is not None for s in self._slots),
                    ready=sum(s.ready for s in self._slots),
                    live_processes=sum(self._process_live(s) for s in self._slots), current=len(self._current),
                    closed=self._closed)

    @staticmethod
    def _process_live(slot):
        process = slot.process
        try:
            return process is not None and process.is_alive()
        except ValueError:
            # 迟到回收线程只在join已确认退出后close进程句柄。
            return False

    def _transport_done(self, future):
        with self._thread_lock:
            self._transport_futures.discard(future)

    def _register_transport_thread(self):
        with self._thread_lock:
            self._transport_threads.add(threading.current_thread())

    async def _offload(self, function, *args, slot=None):
        """只接受至多workers份传输任务；取消等待后仍保留实际线程future直到终态。"""
        with self._thread_lock:
            self._transport_futures = {f for f in self._transport_futures if not f.done()}
            if self._closed or len(self._transport_futures) >= self.settings.workers:
                raise DecisionComputeError('TRANSPORT_NOT_AVAILABLE')
            future = self._transport.submit(function, *args)
            self._transport_futures.add(future)
            self._counts['peak_transport'] = max(self._counts['peak_transport'], len(self._transport_futures))
        future.add_done_callback(self._transport_done)
        if slot is not None:
            slot.start_future = future
        wrapped = asyncio.wrap_future(future)
        # shield取消只放弃本等待；迟到异常仍须认领，底层future保存在有限集合。
        wrapped.add_done_callback(lambda done: None if done.cancelled() else done.exception())
        return await asyncio.shield(wrapped)

    async def start(self):
        """窗口开始前预热固定计算槽；工厂错误或超时明确失败并关闭全部资源。"""
        if self._closed:
            raise DecisionComputeError('CLOSED')
        if self._started:
            return
        self._started = True
        ready = [asyncio.get_running_loop().create_future() for _ in self._slots]
        for slot, future in zip(self._slots, ready):
            slot.task = asyncio.create_task(self._serve(slot, future))
        try:
            await asyncio.gather(*ready)
        except BaseException:
            await self.close()
            raise

    async def choose(self, request: DecisionRequest, budget: DecisionBudget) -> DecisionPlan:
        """返回同输入计划；过期、拥堵、故障抛异常，调用方取消保持资源回收所有权。"""
        if self._closed or not self._started or not any(s.ready for s in self._slots):
            raise DecisionComputeError('NOT_READY')
        if not all(isfinite(v) for v in (budget.enhancement_deadline_monotonic,
                    budget.fallback_deadline_monotonic, budget.latest_send_at_monotonic)):
            raise DecisionComputeError('INVALID_DEADLINE')
        if self.clock.now() >= budget.fallback_deadline_monotonic:
            raise DecisionComputeError('DEADLINE')
        game = request.window_key.game_id
        old = self._current.get(game)
        if old is not None:
            self._abandon(old, 'SUPERSEDED')
        idle = next((s for s in self._slots if s.ready and s.active is None), None)
        if idle is None and len(self._pending) >= self.settings.max_pending:
            self._counts['rejected'] += 1
            raise DecisionComputeError('QUEUE_FULL')
        # 先占有限槽/队列，只有真正派发时才编码；拒绝及排队过期不编码大载荷。
        self._number += 1
        job = _Job(self._number, request, budget,
                   asyncio.get_running_loop().create_future())
        self._jobs[job.number] = job
        self._current[game] = job
        self._counts['submitted'] += 1
        job.deadline = asyncio.get_running_loop().call_later(
            self.clock.budget_wait_seconds(budget.fallback_deadline_monotonic),
            self._abandon, job, 'DEADLINE')
        if idle is None:
            self._pending.append(job)
            self._pending.sort(key=lambda j: (j.budget.fallback_deadline_monotonic, j.number))
        else:
            self._assign(idle, job)
        self._counts['peak_owned'] = max(self._counts['peak_owned'], len(self._jobs))
        self._counts['peak_pending'] = max(self._counts['peak_pending'], len(self._pending))
        try:
            return await job.future
        except asyncio.CancelledError:
            self._abandon(job, 'CANCELLED')
            raise

    def _assign(self, slot, job):
        slot.active = job
        slot.wake.set()

    def _forget(self, job):
        self._jobs.pop(job.number, None)
        if self._current.get(job.request.window_key.game_id) is job:
            self._current.pop(job.request.window_key.game_id)
        for timer in (job.deadline, job.reap):
            if timer is not None:
                timer.cancel()

    def _abandon(self, job, reason):
        if job.number not in self._jobs:
            return
        if not job.future.done():
            job.future.set_exception(DecisionComputeError(reason))
        if self._current.get(job.request.window_key.game_id) is job:
            self._current.pop(job.request.window_key.game_id)
        if job in self._pending:
            self._pending.remove(job)
            self._forget(job)
        elif job.reap is None and job.wire_started and not job.reply_received:
            # 只有已发送的活跃任务可能占住子进程。父侧编码到期后会在
            # _exchange 的发送前检查退出，不得因此误杀等待输入的健康进程。
            # 已发送任务仍归原槽；不把取消误当作进程已经空闲。
            slot = next(s for s in self._slots if s.active is job)
            job.reap = asyncio.get_running_loop().call_later(
                self.settings.abandon_grace_seconds, self._kill_stale, slot, job)

    def _kill_stale(self, slot, job):
        if (slot.active is job and job.wire_started and not job.reply_received
                and slot.process is not None and slot.process.is_alive()):
            slot.process.terminate()

    async def _read(self, reader, job=None):
        size = struct.unpack('!I', await reader.readexactly(4))[0]
        if size > self.settings.max_message_bytes:
            raise DecisionComputeError('MESSAGE_LIMIT')
        raw = await reader.readexactly(size)
        if job is not None:
            # 收齐报文不等于接受结果：后续仍解码、核身份及原截止。
            # 这里只证明子进程已完成发送；父侧解码迟到不能误杀空闲进程。
            # 槽和线程所有权保留到解码/丢弃结束，防止下一请求交叉读写。
            job.reply_received = True
        return await self._offload(_decode_message, raw)

    async def _exchange(self, slot, reader, job):
        wire, job.digest = await self._offload(_pack_job, job.number, job.request,
                                             job.budget, self.settings.max_message_bytes)
        if job.future.done() or self.clock.now() >= job.budget.fallback_deadline_monotonic:
            self._abandon(job, 'DEADLINE')
            return None
        # write 可能已送出部分字节后抛错，必须在调用前标记通信已开始。
        job.wire_started = True
        slot.writer.write(struct.pack('!I', len(wire)) + wire)
        await slot.writer.drain()
        return await self._read(reader, job)

    def _deliver(self, slot, job, message):
        if message is None:
            return
        if (message.get('kind') != 'result' or message.get('job_id') != job.number
                or message.get('digest') != job.digest
                or message.get('execution_id') != self.execution_id):
            raise DecisionComputeError('RESULT_IDENTITY_MISMATCH')
        if (job.future.done() or self._current.get(job.request.window_key.game_id) is not job
                or self.clock.now() >= job.budget.fallback_deadline_monotonic):
            self._counts['discarded'] += 1
            self._abandon(job, 'DEADLINE')
            return
        if 'error' in message:
            # 子进程已捕获本次策略拒绝并继续服务。它不是进程/协议故障，
            # 不能耗尽重启额度，令随后所有正常窗口永久进入紧急保底。
            # 只有身份与错误信封都合法时才走此通道；不接受伪造成功计划。
            if type(message['error']) is not str or 'plan' in message:
                raise DecisionComputeError('RESULT_ERROR_ENVELOPE_INVALID')
            self._counts['policy_failures'] += 1
            job.future.set_exception(DecisionComputeError('POLICY_FAILED'))
            return
        plan = message['plan']
        request = job.request
        allowed = {c.action_key for c in request.rules.legal_candidates}
        rejected = {r.action_key for r in request.rejected_attempts}
        if (plan.decision_id != request.decision_id or plan.window_key != request.window_key
                or plan.based_on_authoritative_seq != request.observation.snapshot_seq
                or not plan.candidates
                or any(c.action_key not in allowed or c.action_key in rejected for c in plan.candidates)):
            raise DecisionComputeError('PLAN_REQUEST_MISMATCH')
        # 解码/复核本身也消耗原预算，不能用解码前的检查授及时结果。
        if self.clock.now() >= job.budget.fallback_deadline_monotonic:
            self._abandon(job, 'DEADLINE')
            self._counts['discarded'] += 1
        else:
            job.future.set_result(plan)
            self._counts['completed'] += 1

    async def _start_slot(self, slot):
        """原启动期限同时覆盖spawn和ready；实际start线程future属于当前槽。"""
        slot.parent_socket, slot.child_socket = socket.socketpair()
        slot.process = multiprocessing.get_context('spawn').Process(target=_worker_entry,
            args=(slot.child_socket, self.factory, self.execution_id, self.settings.max_message_bytes),
            daemon=True)
        await self._offload(slot.process.start, slot=slot)
        self._counts['process_starts'] += 1
        slot.child_socket.close()
        slot.child_socket = None
        reader, slot.writer = await asyncio.open_connection(sock=slot.parent_socket)
        slot.parent_socket = None  # 所有权已交给异步writer
        return reader

    async def _serve(self, slot, ready):
        while not self._closed:
            try:
                async def startup():
                    reader = await self._start_slot(slot)
                    message = await self._read(reader)
                    return reader, message
                reader, message = await asyncio.wait_for(startup(), self.settings.startup_seconds)
                if message != dict(kind='ready', execution_id=self.execution_id):
                    raise DecisionComputeError('WORKER_START_FAILED')
                slot.ready = True
                if not ready.done():
                    ready.set_result(None)
                while not self._closed:
                    if slot.active is None and self._pending:
                        self._assign(slot, self._pending.pop(0))
                    if slot.active is None:
                        slot.wake.clear()
                        await slot.wake.wait()
                        continue
                    job = slot.active
                    try:
                        if self.clock.now() >= job.budget.fallback_deadline_monotonic:
                            self._abandon(job, 'DEADLINE')
                            continue
                        self._counts['dispatched'] += 1
                        message = await asyncio.wait_for(self._exchange(slot, reader, job),
                                                         self.settings.max_job_seconds)
                        self._deliver(slot, job, message)
                    except Exception:
                        if not job.future.done():
                            job.future.set_exception(DecisionComputeError('WORKER_FAILED'))
                        raise
                    finally:
                        self._forget(job)
                        slot.active = None
            except asyncio.CancelledError:
                if not ready.done():
                    ready.set_exception(DecisionComputeError('CLOSED'))
                if slot.active is not None and not slot.active.future.done():
                    slot.active.future.set_exception(DecisionComputeError('CLOSED'))
                raise
            except Exception:
                self._counts['faults'] += 1
                if slot.active is not None:
                    if not slot.active.future.done():
                        slot.active.future.set_exception(DecisionComputeError('WORKER_FAILED'))
                    self._forget(slot.active)
                    slot.active = None
                if not ready.done():
                    ready.set_exception(DecisionComputeError('WORKER_START_FAILED'))
                    return
            finally:
                slot.ready = False
                await self._stop(slot)
            if slot.restarts >= self.settings.max_restarts:
                return
            slot.restarts += 1
            self._counts['restarts'] += 1
            await asyncio.sleep(0.01)

    def _schedule_late_reap(self, slot):
        """退出超时后的唯一所有者；即使事件循环退出，迟到spawn也会被同步终止。"""
        if slot.late_reap_future is not None:
            return
        finished = slot.late_reap_future = Future()
        start_future = slot.start_future
        process, parent, child = slot.process, slot.parent_socket, slot.child_socket
        def reap():
            try:
                try:
                    start_future.result()  # 有限一个迟到所有者，不能在start结束前关fd
                except Exception:
                    pass
                for sock in (parent, child):
                    if sock is not None:
                        sock.close()
                if process.pid is not None:
                    if process.is_alive():
                        process.terminate()
                    process.join(timeout=self.settings.resource_reap_seconds)
                    if process.is_alive():
                        process.kill()
                        process.join(timeout=self.settings.resource_reap_seconds)
                    if process.is_alive():
                        raise DecisionComputeError('LATE_PROCESS_REAP_FAILED')
                process.close()
                slot.process = slot.parent_socket = slot.child_socket = slot.start_future = None
                finished.set_result(None)
            except BaseException as exc:
                finished.set_exception(exc)  # 未回收句柄继续在slot，不冒称清理成功
        slot.late_reap_thread = threading.Thread(target=reap, name='hangma-late-spawn-reap', daemon=True)
        slot.late_reap_thread.start()

    async def _stop(self, slot):
        if slot.late_reap_future is not None:
            wrapped = asyncio.wrap_future(slot.late_reap_future)
            wrapped.add_done_callback(lambda done: None if done.cancelled() else done.exception())
            done, _ = await asyncio.wait({wrapped}, timeout=self.settings.resource_reap_seconds)
            if not done:
                raise DecisionComputeError('SPAWN_REAP_FAILED')
            wrapped.result()
            return
        # start等待被取消不表示Process.start已经结束，不能提前关它正在使用的socket。
        if slot.start_future is not None and not slot.start_future.done():
            wrapped = asyncio.wrap_future(slot.start_future)
            wrapped.add_done_callback(lambda done: None if done.cancelled() else done.exception())
            done, _ = await asyncio.wait({wrapped}, timeout=self.settings.resource_reap_seconds)
            if not done:
                self._schedule_late_reap(slot)
                raise DecisionComputeError('SPAWN_REAP_FAILED')
        for name in ('child_socket', 'parent_socket'):
            sock = getattr(slot, name)
            if sock is not None:
                sock.close()
                setattr(slot, name, None)
        slot.start_future = None
        if slot.writer is not None:
            slot.writer.close()
            try:
                await asyncio.wait_for(slot.writer.wait_closed(), 0.2)
            except Exception:
                pass
            slot.writer = None
        process = slot.process
        if process is not None:
            if process.pid is None:
                process.close()
                slot.process = None
                return
            if process.is_alive():
                process.terminate()
            for attempt in range(100):
                process.join(timeout=0)
                if not process.is_alive():
                    process.close()
                    slot.process = None
                    return
                if attempt == 20:
                    process.kill()
                await asyncio.sleep(0.01)
            raise DecisionComputeError('PROCESS_REAP_FAILED')

    async def close(self):
        """并发退出共享一个回收任务；调用方取消等待不能取消底层回收所有权。"""
        if (self._close_task is None or (self._close_task.done()
                and not self._close_task.cancelled() and self._close_task.exception() is not None)):
            self._close_task = asyncio.create_task(self._close_resources())
        return await asyncio.shield(self._close_task)

    async def _close_resources(self):
        self._closed = True
        for job in list(self._jobs.values()):
            self._abandon(job, 'CLOSED')
        tasks = [s.task for s in self._slots if s.task is not None]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        # 每个失败也继续回收其他槽，并始终关闭线程池入队口。
        errors = [r for r in await asyncio.gather(*(self._stop(s) for s in self._slots),
                                                  return_exceptions=True) if isinstance(r, BaseException)]
        with self._thread_lock:
            active = [f for f in self._transport_futures if not f.done()]
        if active:
            wrapped = [asyncio.wrap_future(f) for f in active]
            for future in wrapped:
                future.add_done_callback(lambda done: None if done.cancelled() else done.exception())
            _done, pending = await asyncio.wait(wrapped, timeout=self.settings.resource_reap_seconds)
            if pending:
                errors.append(DecisionComputeError('TRANSPORT_REAP_FAILED'))
        # wait=False不能等价于线程已退出：未结束raw futures继续拥有，done回调自动移除。
        self._transport.shutdown(wait=False, cancel_futures=True)
        for _ in range(max(1, int(self.settings.resource_reap_seconds / .01))):
            with self._thread_lock:
                alive = any(t.is_alive() for t in self._transport_threads)
            alive = alive or any(s.late_reap_thread is not None and s.late_reap_thread.is_alive()
                                 for s in self._slots)
            if not alive:
                break
            await asyncio.sleep(.01)
        else:
            errors.append(DecisionComputeError('TRANSPORT_THREAD_REAP_FAILED'))
        for job in list(self._jobs.values()):
            self._forget(job)
        for slot in self._slots:
            slot.active = None
        if errors:
            raise errors[0]
