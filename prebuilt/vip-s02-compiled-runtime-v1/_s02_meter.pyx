from hangma_bot.policy.action_value_executor import WorkloadExceeded
cdef class Meter:
    def __init__(self, limit):
        self.used = 0
        self.limit = limit
    cpdef charge(self, count=1):
        self.used += count
        if self.used > self.limit:
            raise WorkloadExceeded("计数操作超限：已用 {0}，上限 {1}".format(self.used, self.limit))
    cdef void charge_one(self) except *:
        self.used += 1
        if self.used > self.limit:
            raise WorkloadExceeded("计数操作超限：已用 {0}，上限 {1}".format(self.used, self.limit))
