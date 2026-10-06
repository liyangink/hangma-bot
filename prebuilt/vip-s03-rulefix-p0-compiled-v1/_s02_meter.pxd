cdef class Meter:
    cdef public object used, limit
    cpdef charge(self, count=*)
    cdef void charge_one(self) except *
