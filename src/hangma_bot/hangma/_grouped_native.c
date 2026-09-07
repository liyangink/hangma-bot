/*
 * 杭麻普通型缺牌数的可选 CPython 分组内核。
 *
 * 数学语义：自然牌虚牌配额为 4-原计数，递归中完整保留零配额；枚举
 * 财神在每个块缺位上的分配，保留舍牌分支。四组通过面子、将和财神
 * 资源合成。依据为本模块 RULES_EVIDENCE.md 的牌系统与胡牌结构；
 * 算法验证来自 grouped-dp-performance-2026-09-07 的独立模板对拍。
 *
 * 输入只有 33 种自然牌计数和三个资源参数，没有其他玩家手牌或牌墙。
 * 计算与清缓存始终持有解释器锁，不访问网络、文件或系统时间。
 * 仅 CPython 的模块定义头由解释器维护；数学缓存与计数全部归模块
 * 状态所有，随模块实例分配、释放，不依赖解释器间共享的可变全局。
 */
#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include <stdint.h>
#include <string.h>

#ifndef __SIZEOF_INT128__
#error "The optional grouped backend requires compiler support for 128-bit integers."
#endif

#define SEMANTICS_VERSION "hangma-standard-grouped-v1"

typedef __uint128_t U128;
#define LOCAL_N 65536u
#define TABLE_N 8192u
#define WHOLE_N 32768u
#define INF 99
#define UNKNOWN 255
#define ALL_TYPES UINT64_C(0x1ffffffff)
#define SUIT_TYPES UINT64_C(0x1ff)
#define HONOR_TYPES (UINT64_C(0x3f) << 27)
#define TABLE_INDEX(m,p,w) (((m)*2+(p))*5+(w))

typedef struct {
    U128 counts, quota;
    uint64_t domain;
    uint8_t whites, sets, pair, value, valid;
} ScalarEntry;
typedef struct {
    U128 counts, quota;
    uint64_t domain;
    uint8_t costs[50], valid;
} TableEntry;

/* CPython 为每个模块实例分配并最终释放 m_size 字节；这里不保存
 * PyObject 引用，也不使用进程全局缓存，多个解释器之间不共享可变数据。 */
typedef struct {
    ScalarEntry local_cache[LOCAL_N], whole_cache[WHOLE_N];
    TableEntry table_cache[TABLE_N];
    uint64_t local_hits, local_misses, local_occupied;
    uint64_t table_hits, table_misses, table_occupied;
    uint64_t table_value_hits, table_value_misses;
    uint64_t whole_hits, whole_misses, whole_occupied;
} ModuleState;

_Static_assert(sizeof(ScalarEntry) == 48, "scalar cache layout must use 48 bytes");
_Static_assert(sizeof(TableEntry) == 96, "table cache layout must use 96 bytes");

static inline int minimum(int a,int b) { return a < b ? a : b; }
static inline int at(U128 value,int index) { return (value >> (3*index)) & 7; }
static inline U128 unit(int index) { return (U128)1 << (3*index); }
static inline uint64_t mix64(uint64_t value) {
    value ^= value >> 30; value *= UINT64_C(0xbf58476d1ce4e5b9);
    value ^= value >> 27; value *= UINT64_C(0x94d049bb133111eb);
    return value ^ (value >> 31);
}
static inline uint64_t key_hash(U128 counts,U128 quota,uint64_t domain) {
    return mix64((uint64_t)counts) ^ mix64((uint64_t)(counts>>64)+17)
        ^ mix64((uint64_t)quota+131) ^ mix64((uint64_t)(quota>>64)+65537) ^ mix64(domain);
}
static inline int scalar(ModuleState *state,U128,int,int,int,U128,uint64_t,int);

/* 当前块的自然牌尽量使用；同值自然牌与其他块白/虚牌可交换，因此
 * 不影响可行性与虚牌总数。缺口的白/虚分配必须全部枚举。 */
static int same_tile_block(ModuleState *state,U128 counts,int whites,int sets,int pair,U128 quota,
                           uint64_t domain,int total,int index,int width,int is_pair,int best,int bound) {
    int natural=minimum(at(counts,index),width);
    int missing=width-natural;
    U128 remaining=counts-natural*unit(index);
    for (int use_white=minimum(missing,whites);use_white>=0;--use_white) {
        int phantom=missing-use_white;
        if (phantom >= best || at(quota,index) < phantom) continue;
        int value=phantom+scalar(state,remaining,whites-use_white,sets-(!is_pair),pair-is_pair,
                                quota-phantom*unit(index),domain,total-natural);
        if (value < best) best=value;
        if (best == bound) break;
    }
    return best;
}

static int run_block(ModuleState *state,U128 counts,int whites,int sets,int pair,U128 quota,
                     uint64_t domain,int total,int start,int best,int bound) {
    U128 remaining=counts;
    int missing[3], missing_count=0, natural=0;
    for (int pos=start;pos<start+3;++pos) {
        if (at(counts,pos)) { remaining-=unit(pos); ++natural; }
        else missing[missing_count++]=pos;
    }
    /* 位为1表示该缺位使用白板；所有分配包含少用白板的选择。 */
    for (int mask=(1<<missing_count)-1;mask>=0;--mask) {
        int use_white=__builtin_popcount((unsigned)mask);
        int phantoms=missing_count-use_white;
        if (use_white>whites || phantoms>=best) continue;
        U128 left_quota=quota;
        int feasible=1;
        for (int j=0;j<missing_count;++j) {
            if (mask & (1<<j)) continue;
            int pos=missing[j];
            if (!at(left_quota,pos)) { feasible=0; break; }
            left_quota-=unit(pos);
        }
        if (!feasible) continue;
        int value=phantoms+scalar(state,remaining,whites-use_white,sets-1,pair,left_quota,domain,total-natural);
        if (value < best) best=value;
        if (best == bound) break;
    }
    return best;
}

static int solve(ModuleState *state,U128 counts,int whites,int sets,int pair,U128 quota,uint64_t domain,int total) {
    if (!sets && !pair) return 0;
    int bound=3*sets+2*pair-total-whites;
    if (bound<0) bound=0;
    int best=INF;
    if (!counts) {
        /* 纯白/虚块可交换到所有自然牌使用之后。此处按具体牌种扣除
         * 剩余库存，slots-white 仅是下界，不能作为无条件答案。 */
        uint64_t kinds=domain;
        while (kinds) {
            int index=__builtin_ctzll(kinds);
            kinds &= kinds-1;
            best=same_tile_block(state,counts,whites,sets,pair,quota,domain,total,index,pair?2:3,pair,best,bound);
            if (best == bound) return best;
        }
        if (!pair && sets) {
            for (int suit=0;suit<3;++suit) for (int start=9*suit;start<=9*suit+6;++start) {
                uint64_t window=UINT64_C(7)<<start;
                if ((domain & window) != window) continue;
                best=run_block(state,counts,whites,sets,pair,quota,domain,total,start,best,bound);
                if (best == bound) return best;
            }
        }
        return best;
    }
    uint64_t lo=(uint64_t)counts;
    int first_bit=lo ? __builtin_ctzll(lo) : 64+__builtin_ctzll((uint64_t)(counts>>64));
    int index=first_bit/3;
    if (pair) {
        best=same_tile_block(state,counts,whites,sets,pair,quota,domain,total,index,2,1,best,bound);
        if (best == bound) return best;
    }
    if (sets) {
        best=same_tile_block(state,counts,whites,sets,pair,quota,domain,total,index,3,0,best,bound);
        if (best == bound) return best;
        if (index<27) {
            int suit_start=(index/9)*9;
            int first=index-2>suit_start ? index-2 : suit_start;
            int last=minimum(index,suit_start+6);
            for (int start=first;start<=last;++start) {
                uint64_t window=UINT64_C(7)<<start;
                if ((domain & window) != window) continue;
                best=run_block(state,counts,whites,sets,pair,quota,domain,total,start,best,bound);
                if (best == bound) return best;
            }
        }
    }
    int discarded=scalar(state,counts-unit(index),whites,sets,pair,quota,domain,total-1);
    return minimum(best,discarded);
}

static inline int scalar(ModuleState *state,U128 counts,int whites,int sets,int pair,U128 quota,uint64_t domain,int total) {
    uint64_t hash=key_hash(counts,quota,domain)^mix64(whites+17*sets+127*pair);
    ScalarEntry *entry=&state->local_cache[hash & (LOCAL_N-1)];
    if (entry->valid && entry->counts==counts && entry->quota==quota && entry->domain==domain
        && entry->whites==whites && entry->sets==sets && entry->pair==pair) {
        ++state->local_hits; return entry->value;
    }
    ++state->local_misses;
    int value=solve(state,counts,whites,sets,pair,quota,domain,total);
    if (!entry->valid) ++state->local_occupied;
    *entry=(ScalarEntry){counts,quota,domain,whites,sets,pair,value,1};
    return value;
}

static TableEntry *get_table(ModuleState *state,U128 counts,U128 quota,uint64_t domain) {
    TableEntry *entry=&state->table_cache[key_hash(counts,quota,domain)&(TABLE_N-1)];
    if (entry->valid && entry->counts==counts && entry->quota==quota && entry->domain==domain) {
        ++state->table_hits; return entry;
    }
    ++state->table_misses;
    if (!entry->valid) ++state->table_occupied;
    entry->counts=counts; entry->quota=quota; entry->domain=domain; entry->valid=1;
    memset(entry->costs,UNKNOWN,sizeof(entry->costs));
    return entry;
}

static int table_value(ModuleState *state,TableEntry *table,int whites,int sets,int pair,int total) {
    int offset=TABLE_INDEX(sets,pair,whites);
    if (table->costs[offset] != UNKNOWN) { ++state->table_value_hits; return table->costs[offset]; }
    ++state->table_value_misses;
    int value=scalar(state,table->counts,whites,sets,pair,table->quota,table->domain,total);
    table->costs[offset]=value;
    return value;
}

static int merge_groups(ModuleState *state,U128 counts,int whites,int sets,int pair,U128 quota) {
    uint8_t previous[50],next[50];
    memset(previous,INF,sizeof(previous));
    previous[TABLE_INDEX(0,0,0)]=0;
    for (int group=0;group<4;++group) {
        U128 local_counts=0,local_quota=0;
        int total=0;
        int first=group<3 ? 9*group : 27;
        int last=group<3 ? first+9 : 33;
        for (int i=first;i<last;++i) {
            int target=group<3 ? i-first : i;
            local_counts |= (U128)at(counts,i)<<(3*target);
            local_quota |= (U128)at(quota,i)<<(3*target);
            total+=at(counts,i);
        }
        TableEntry *table=get_table(state,local_counts,local_quota,group<3 ? SUIT_TYPES : HONOR_TYPES);
        if (group==3) {
            int best=INF;
            for (int m=0;m<=sets;++m) for (int p=0;p<=pair;++p) for (int w=0;w<=whites;++w) {
                int before=previous[TABLE_INDEX(m,p,w)];
                if (before>=best) continue;
                int value=before+table_value(state,table,whites-w,sets-m,pair-p,total);
                if (value<best) best=value;
            }
            return best;
        }
        memset(next,INF,sizeof(next));
        for (int m=0;m<=sets;++m) for (int p=0;p<=pair;++p) for (int w=0;w<=whites;++w) {
            int before=previous[TABLE_INDEX(m,p,w)];
            if (before>=INF) continue;
            for (int dm=0;dm<=sets-m;++dm) for (int dp=0;dp<=pair-p;++dp) for (int dw=0;dw<=whites-w;++dw) {
                int slot=TABLE_INDEX(m+dm,p+dp,w+dw);
                if (before>=next[slot]) continue;
                int value=before+table_value(state,table,dw,dm,dp,total);
                if (value<next[slot]) next[slot]=value;
            }
        }
        memcpy(previous,next,sizeof(previous));
    }
    return INF;
}


/* 全手缓存仅保存分组合成结果，不调用另一套整手搜索。 */
static int grouped_need(ModuleState *state, U128 counts, int whites, int sets,
                        int pair, U128 quota) {
    uint64_t hash = key_hash(counts, quota, ALL_TYPES)
        ^ mix64(whites + 17 * sets + 127 * pair);
    ScalarEntry *entry = &state->whole_cache[hash & (WHOLE_N - 1)];
    if (entry->valid && entry->counts == counts && entry->quota == quota
        && entry->domain == ALL_TYPES && entry->whites == whites
        && entry->sets == sets && entry->pair == pair) {
        ++state->whole_hits;
        return entry->value;
    }
    ++state->whole_misses;
    int answer = merge_groups(state, counts, whites, sets, pair, quota);
    if (!entry->valid) ++state->whole_occupied;
    *entry = (ScalarEntry){counts, quota, ALL_TYPES, whites, sets, pair, answer, 1};
    return answer;
}

/* 本扩展的每个可调用方法都以所属模块作为 self；状态寿命由 CPython
 * 保证。没有 PyObject 字段，所以无需额外的 GC 遍历或重复手工释放。 */
static ModuleState *module_state(PyObject *module) {
    ModuleState *state = (ModuleState *)PyModule_GetState(module);
    if (state == NULL && !PyErr_Occurred()) {
        PyErr_SetString(PyExc_RuntimeError, "分组内核的模块状态尚未初始化");
    }
    return state;
}

/* bool 是 Python int 的子类，此处要求精确 int，避免 True 被当作一张牌。
 * 超出 C long 的 Python 大整数仍统一作为范围错误处理，不发生截断。 */
static int bounded_int(PyObject *value, const char *name, int *output) {
    if (!PyLong_CheckExact(value)) {
        PyErr_Format(PyExc_TypeError, "%s 必须为整数，不能使用 bool 或整数子类", name);
        return 0;
    }
    int overflow = 0;
    long number = PyLong_AsLongAndOverflow(value, &overflow);
    if (PyErr_Occurred()) return 0;
    if (overflow || number < 0 || number > 4) {
        PyErr_Format(PyExc_ValueError, "%s 必须在 0–4 范围内", name);
        return 0;
    }
    *output = (int)number;
    return 1;
}

PyDoc_STRVAR(need_doc,
    "need($module, counts33, whites, sets_left, pair_needed)\n"
    "--\n\n"
    "计算普通型最少自然虚牌数。自然牌计数必须是长度33的精确tuple，元素、白板数和面子数均受0–4约束；"
    "将标志必须为bool。非法类型或范围抛出异常，只修改本模块的有界缓存。");

static PyObject *module_need(PyObject *module, PyObject *args, PyObject *kwargs) {
    static const char *const keywords[] = {
        "counts33", "whites", "sets_left", "pair_needed", NULL
    };
    PyObject *counts_arg, *whites_arg, *sets_arg, *pair_arg;
    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "OOOO:need", (char **)keywords,
                                    &counts_arg, &whites_arg, &sets_arg, &pair_arg)) {
        return NULL;
    }
    int whites, sets;
    if (!bounded_int(whites_arg, "whites", &whites)
        || !bounded_int(sets_arg, "sets_left", &sets)) return NULL;
    if (!PyBool_Check(pair_arg)) {
        PyErr_SetString(PyExc_TypeError, "pair_needed 必须为 bool");
        return NULL;
    }
    if (!PyTuple_CheckExact(counts_arg)) {
        PyErr_SetString(PyExc_TypeError, "counts33 必须为精确 tuple，不能使用其他序列或 tuple 子类");
        return NULL;
    }
    if (PyTuple_GET_SIZE(counts_arg) != 33) {
        PyErr_SetString(PyExc_ValueError, "counts33 必须恰好包含33种自然牌计数");
        return NULL;
    }
    U128 counts = 0, quota = 0;
    for (int i = 0; i < 33; ++i) {
        int number;
        if (!bounded_int(PyTuple_GET_ITEM(counts_arg, i), "counts33 元素", &number)) {
            return NULL;
        }
        counts |= (U128)number << (3 * i);
        quota |= (U128)(4 - number) << (3 * i);
    }
    ModuleState *state = module_state(module);
    if (state == NULL) return NULL;
    int answer = grouped_need(state, counts, whites, sets, pair_arg == Py_True, quota);
    return PyLong_FromLong(answer);
}

PyDoc_STRVAR(clear_doc,
    "cache_clear($module, /)\n"
    "--\n\n"
    "清空本模块实例的全部有界缓存和计数，不影响其他模块或解释器。");

static PyObject *module_cache_clear(PyObject *module, PyObject *Py_UNUSED(ignored)) {
    ModuleState *state = module_state(module);
    if (state == NULL) return NULL;
    memset(state, 0, sizeof(*state));
    Py_RETURN_NONE;
}

static PyObject *scalar_cache_info(uint64_t capacity, uint64_t bytes,
                                   uint64_t hits, uint64_t misses, uint64_t occupied) {
    return Py_BuildValue("{s:K,s:K,s:K,s:K,s:K}",
        "capacity", (unsigned long long)capacity,
        "bytes", (unsigned long long)bytes,
        "hits", (unsigned long long)hits,
        "misses", (unsigned long long)misses,
        "occupied", (unsigned long long)occupied);
}

PyDoc_STRVAR(info_doc,
    "cache_info($module, /)\n"
    "--\n\n"
    "分别返回三类缓存的容量、字节数、占用和命中计数；字节数不含Python运行时。");

static PyObject *module_cache_info(PyObject *module, PyObject *Py_UNUSED(ignored)) {
    ModuleState *state = module_state(module);
    if (state == NULL) return NULL;
    PyObject *local = scalar_cache_info(
        LOCAL_N, sizeof(state->local_cache), state->local_hits,
        state->local_misses, state->local_occupied);
    if (local == NULL) return NULL;
    PyObject *table = Py_BuildValue("{s:K,s:K,s:K,s:K,s:K,s:K,s:K}",
        "capacity", (unsigned long long)TABLE_N,
        "bytes", (unsigned long long)sizeof(state->table_cache),
        "hits", (unsigned long long)state->table_hits,
        "misses", (unsigned long long)state->table_misses,
        "occupied", (unsigned long long)state->table_occupied,
        "value_hits", (unsigned long long)state->table_value_hits,
        "value_misses", (unsigned long long)state->table_value_misses);
    if (table == NULL) {
        Py_DECREF(local);
        return NULL;
    }
    PyObject *whole = scalar_cache_info(
        WHOLE_N, sizeof(state->whole_cache), state->whole_hits,
        state->whole_misses, state->whole_occupied);
    if (whole == NULL) {
        Py_DECREF(local);
        Py_DECREF(table);
        return NULL;
    }
    PyObject *result = Py_BuildValue("{s:O,s:O,s:O,s:K,s:s,s:s}",
        "local_cache", local, "local_table", table, "whole_cache", whole,
        "cache_bytes_total", (unsigned long long)(
            sizeof(state->local_cache) + sizeof(state->table_cache) + sizeof(state->whole_cache)),
        "backend", "native", "semantics_version", SEMANTICS_VERSION);
    Py_DECREF(local);
    Py_DECREF(table);
    Py_DECREF(whole);
    return result;
}

static int module_exec(PyObject *module) {
    if (module_state(module) == NULL) return -1;
    return PyModule_AddStringConstant(module, "SEMANTICS_VERSION", SEMANTICS_VERSION);
}

/* 方法表、槽位表都是只读元数据；C API 的字段未声明 const，因此在
 * 装配处显式转换。运行时唯一静态可变对象是 CPython 要求的模块定义头。 */
static const PyMethodDef grouped_methods[] = {
    {"need", (PyCFunction)(void (*)(void))module_need, METH_VARARGS | METH_KEYWORDS, need_doc},
    {"cache_clear", module_cache_clear, METH_NOARGS, clear_doc},
    {"cache_info", module_cache_info, METH_NOARGS, info_doc},
    {NULL, NULL, 0, NULL}
};

static const PyModuleDef_Slot grouped_slots[] = {
    {Py_mod_exec, module_exec},
#ifdef Py_mod_multiple_interpreters
    {Py_mod_multiple_interpreters, Py_MOD_PER_INTERPRETER_GIL_SUPPORTED},
#endif
#ifdef Py_mod_gil
    {Py_mod_gil, Py_MOD_GIL_USED},
#endif
    {0, NULL}
};

static struct PyModuleDef grouped_definition = {
    PyModuleDef_HEAD_INIT,
    .m_name = "hangma_bot.hangma._grouped_native",
    .m_doc = "杭麻普通型分组动态规划；每模块独立有界缓存，保持解释器锁。",
    .m_size = sizeof(ModuleState),
    .m_methods = (PyMethodDef *)grouped_methods,
    .m_slots = (PyModuleDef_Slot *)grouped_slots,
    .m_traverse = NULL,
    .m_clear = NULL,
    .m_free = NULL
};

PyMODINIT_FUNC PyInit__grouped_native(void) {
    return PyModuleDef_Init(&grouped_definition);
}
