"""统一推进并发等待的确定性单调时钟。"""
import asyncio
from _official_testkit import FakeClock

class VirtualClock(FakeClock):
    """所有协程共用一个单调时钟；不会把并发sleep的时长累加。"""
    def __init__(self):
        super().__init__(start=0)
        self.waiting = []

    async def sleep(self, seconds):
        future = asyncio.get_running_loop().create_future()
        self.waiting.append((self.monotonic() + max(seconds, .000001), future))
        await future

    async def run(self, awaitable):
        task = asyncio.create_task(awaitable)
        for _ in range(10000):
            for _ in range(12):
                await asyncio.sleep(0)
            if task.done():
                return task.result()
            self.waiting = [(when, f) for when, f in self.waiting if not f.done()]
            assert self.waiting, "探针脚本死锁，而非目标失败"
            nearest = min(when for when, f in self.waiting)
            self.advance(max(0, nearest - self.monotonic()))
            for when, future in self.waiting:
                if when <= self.monotonic() + 1e-10 and not future.done():
                    future.set_result(None)
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        raise AssertionError("虚拟时钟未收敛")
