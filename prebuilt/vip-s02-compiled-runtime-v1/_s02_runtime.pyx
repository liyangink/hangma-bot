from __future__ import annotations
from _s02_meter cimport Meter
from hangma_bot.policy.action_value_executor import (
    ALLOWED_BUILTINS,
    ALLOWED_METHODS,
    ActionScore,
    ActionValueCompiledRuntime,
    ActionValueExecutor,
    ActionView,
    AnalysisProfileView,
    Any,
    CANDIDATE_KIND,
    Callable,
    CompetitionView,
    Dict,
    EXECUTOR_VERSION,
    FIRST_PARTY_DIGEST_MODULES,
    FrozenSet,
    ItemsView,
    KeysView,
    List,
    MAX_COUNTED_OPERATIONS,
    MAX_DATA_CELLS,
    MAX_DATA_DEPTH,
    MAX_INT_MAGNITUDE,
    MAX_LOCAL_COLLECTION_SIZE,
    MAX_POWER_EXPONENT,
    MAX_SHIFT_BITS,
    MAX_SOURCE_BYTES,
    MAX_STRING_CHARS,
    MAX_SUPPORTED_LOCAL_COLLECTION_SIZE,
    MAX_TRACE_BYTES,
    Mapping,
    Optional,
    ReferenceFeature,
    SCORING_VIEW_SCHEMA_VERSION,
    STATUS_VALUES,
    ScoreBatch,
    ScoringView,
    Set,
    StaticCheckError,
    Tuple,
    UNSIZEED_INPUT_COST,
    ValuesView,
    WorkloadExceeded,
    _AV_BIN,
    _AV_CMP,
    _AV_DICT_LIT,
    _AV_FVALUE,
    _AV_ITER,
    _AV_KEY,
    _AV_METHOD,
    _AV_PASS,
    _AV_SET_LIT,
    _AV_SUB,
    _AV_UN,
    _AV_WRAP_DICT,
    _AV_WRAP_LIST,
    _AvDict,
    _AvFrozenSet,
    _AvList,
    _AvSet,
    _BIN_OPS,
    _CMP_NAMES,
    _CMP_OPS,
    _INSTRUMENT_NAMES,
    _Instrumentor,
    _Meter,
    _PERCENT_SPEC,
    _RT_OPS,
    _SCALAR_COST_TYPES,
    _STRING_COST_CHUNK,
    _UNARY_OPS,
    _canonical_params,
    _check_comprehension,
    _check_constant,
    _check_constant_expr,
    _check_expr,
    _check_function,
    _check_recursion,
    _check_score_actions_signature,
    _check_stmts,
    _check_target,
    _is_docstring,
    _reject,
    _resolves,
    _types_digest_material,
    _valid_name,
    annotations,
    ast,
    compute_candidate_identity,
    compute_deps_digest,
    compute_first_party_digest,
    dataclass,
    dataclass_fields,
    hashlib,
    json,
    math,
    operator,
    parse_format_spec,
    re,
    run_scoring_skeleton,
    static_check,
)

def _structure_exceeded(what: str) -> WorkloadExceeded:
    """结构单元超限的统一拒绝信号（R9/S1）。"""
    return WorkloadExceeded(
        "{0} 结构超过 {1} 单元上限：拒绝递归数据遍历".format(what, MAX_DATA_CELLS)
    )


def _structure_children(node: Any) -> Optional[List[Any]]:
    """结构节点的子节点列表；返回 None 表示该节点是 O(1) 叶子。

    R9/S1b：分派不再默认放行——dict_keys/dict_items/dict_values 这类**集合式
    字典视图**必须展开为底层键/键值对：CPython 的 dict_items 相等比较走逐项
    查找并逐值比较（dictview_richcompare），视图本身不是 dict/tuple/list/set/
    frozenset 实例，白名单分派会把它们当成 O(1) 标量（实测量：视图计 0 单元，
    而原生比较每轮访问 524,288 个元素节点）。
    """
    if isinstance(node, dict):
        return [child for pair in node.items() for child in pair]
    if isinstance(node, (tuple, list, set, frozenset)):
        return list(node)
    if isinstance(node, ItemsView):
        # 每项是 (键, 值) 二元组：两项都参与原生比较/序列化。
        return [child for pair in node for child in pair]
    if isinstance(node, KeysView):
        return list(node)
    if isinstance(node, ValuesView):
        return list(node)
    return None


def _unknown_structure_units(node: Any) -> int:
    """未知类型的保守单元数（R9/S1b：不再默认 0）。

    兜底顺序（保守方向 = 宁可多计也不放行）：
    1. 有 len() 的对象（range、视图类、自定义 Sized）：按 max(1, len) 计费
       且**不展开**——元素级遍历由迭代/构造/切片等各自通道计费；
    2. 可调用对象（函数、绑定方法、白名单内建）：身份哈希与比较 O(1)，计 1；
    3. 其余未知类型（分派外的对象）：按 MAX_DATA_CELLS + 1 计费。这个数字
       必然让计费通道触顶——所有调用点都会把结构代价计到计数器上（默认
       预算 100,000 < 131,073）或按单元上限直接拒绝，因此**默认口径下等价于
       拒绝**，同时 structure_cost 保持全函数（不抛异常），直接度量与
       读数仍可观察。
    """
    if node is None or isinstance(node, (bool, int, float, complex)):
        # 标量基类（含 int/float 的子类，如计数叶子这类外部包装）：O(1) 哈希
        # 与比较，计 1——不展开、不按未知形状拒绝。
        return 1
    try:
        length = len(node)
    except TypeError:
        length = None
    if isinstance(length, int) and length >= 0:
        return max(1, length)
    if callable(node):
        return 1
    return MAX_DATA_CELLS + 1  # 未知形状：按上限+1 计费 → 计费通道必然拒绝


def _walk_structure(
    value: Any, what: str, sink: Optional[Callable[[int], None]]
) -> int:
    """同一套有界结构遍历：返回单元数；sink 逐节点计费（None = 只测量）。

    口径（structure_cost 与候选返回值计费共用，避免两份实现分叉）：
    - 每个展开节点各计 1 个单元（容器、视图、标量叶同口径；字符串按 64
      字符一段、至少 1 段）；
    - 共享引用按出现次数累积，不做 id 记忆化；
    - 容器/视图出栈前先按「每个子节点至少 1 单元」预判 MAX_DATA_CELLS，
      超限立即拒绝，因此入栈量与遍历量都有界；
    - 未知类型走保守兜底（见 _unknown_structure_units）。
    """
    kind = type(value)
    if kind is str:
        return len(value) // _STRING_COST_CHUNK
    if kind in _SCALAR_COST_TYPES:
        return 0
    children = _structure_children(value)
    if children is None:
        return _unknown_structure_units(value)
    total = 0
    stack: List[Tuple[Any, int]] = [(value, 0)]
    while stack:
        node, depth = stack.pop()
        node_type = type(node)
        if isinstance(node, str):
            units = max(1, len(node) // _STRING_COST_CHUNK)
        elif node is None or isinstance(node, (bool, int, float, complex)):
            units = 1  # 标量叶：与容器节点同口径各计 1 个单元
        else:
            node_children = _structure_children(node)
            if node_children is None:
                units = _unknown_structure_units(node)
            else:
                if depth + 1 > MAX_DATA_DEPTH:
                    raise WorkloadExceeded(
                        "{0} 嵌套深度超过 {1} 层上限：拒绝递归数据遍历".format(
                            what, MAX_DATA_DEPTH
                        )
                    )
                if total + 1 + len(node_children) > MAX_DATA_CELLS:
                    raise _structure_exceeded(what)
                units = 1
                for child in node_children:
                    stack.append((child, depth + 1))
        if sink is not None:
            sink(units)
        total += units
        if total > MAX_DATA_CELLS:
            raise _structure_exceeded(what)
    return total


def structure_cost(value: Any, what: str) -> int:
    """结构代价（R6/S1；R9/S1 扩到标量叶）：每个展开节点各计 1 个单元。

    计费口径（与复审同口径）：
    - **每个被展开的节点各计 1 个单元**：容器节点与标量叶（int/float/bool/
      None 及其它非容器对象）同口径；字符串按 64 字符一段、至少 1 段
      （CPython 的字符串比较是 memcmp 级、哈希在对象内缓存，短键的额外
      增量本就接近 0，但仍逐项访问一次）；
    - **共享引用按出现次数累积**：同一对象被容器引用 n 次就遍历 n 次。
      CPython 的元组哈希不缓存子对象哈希、容器比较也不去重，所以这里
      **不做 id 记忆化**——去重会让宽而共享的结构少算真实遍历成本；
    - 顶层标量与短字符串走常数快路径（不建栈、不遍历），普通标量比较与
      短键哈希的计费量级与既有实现一致。

    比较/成员查询/格式化/排序，以及 R8/N1 新增的**原生哈希**（字典键、
    集合元素、下标查询）都会递归遍历数据，而 CPython 的比较、repr 与哈希
    在 C 层执行、不受候选语句计费约束。本函数在**真正遍历数据之前**用
    显式栈做有界测量：

    - 容器深度超过 MAX_DATA_DEPTH 即拒绝——(a, a) 重复嵌套会形成深度 d、
      叶数 2^d 的结构，指数比较不再可能跑满时间或 C 栈；
    - 单元数超过 MAX_DATA_CELLS 即拒绝——容器节点与标量叶同口径计入，
      宽而浅（含共享引用）的结构同样有界；
    - 守卫自身有界：容器出栈时先按“每个子节点至少 1 单元”预判上限，
      超限立即拒绝，因此入栈量与遍历量都不超过 MAX_DATA_CELLS。

    修复前（R8/N1—N3）只给容器节点与长字符串计费、标量叶出栈不计数：
    row=(1,)*1024、key=(row,)*256、{key: 1} 的 262144 个展开叶只算 257，
    原生元组哈希仍逐项访问这些叶。

    R9/S1b：分派不再默认放行。dict_keys/dict_items/dict_values 这类集合式
    视图按底层键/键值对展开（同一单元上限）；其余未知类型按
    _unknown_structure_units 的保守兜底处理（有 len 按长度计、可调用计 1、
    其余拒绝），不再有「未知 ⇒ 0」。
    """
    return _walk_structure(value, what, None)


def charge_structure(value: Any, meter: "_Meter", what: str) -> int:
    """把结构单元逐节点计费到执行器计数器（R9/S1b：候选返回值通道）。

    候选执行期间的一切批量工作都按结构单元计费；候选**返回后**的返回值
    （含 trace）此前完全在计费之外：24 operations 就能让执行器序列化
    201 MB。这里在返回骨架做任何递归校验/序列化之前按出现次数逐节点计费，
    超出计数预算即 WorkloadExceeded（整批失效，不进入序列化）。
    """
    return _walk_structure(value, what, meter.charge)


def _digits_to_int(digits: str) -> Optional[int]:
    """把数字串转成整数；超过 12 位直接给一个超限值，避免自身大整数膨胀。"""
    if not digits:
        return None
    if len(digits) > 12:
        return MAX_STRING_CHARS + 1
    return int(digits)


def percent_format_guard(pattern: str, what: str) -> None:
    """按 % 格式化规范在**分配前**检查宽度、精度与最小结果长度。

    修复前百分号格式化先分配 100 MB 结果，再在 av_bin 事后检查长度。
    """
    minimum = 0
    for match in _PERCENT_SPEC.finditer(pattern):
        width_text = match.group(3)
        precision_text = match.group(4)
        conversion = match.group(5)
        if conversion == "%":
            minimum += 1
            continue
        if (width_text and "*" in width_text) or (
            precision_text and "*" in precision_text
        ):
            # '%%*d' % (n, x)：宽度/精度取自实参，分配前无法界定上限。
            raise WorkloadExceeded(
                "{0} 使用 * 宽度/精度：无法在分配前界定长度上限，请改用固定宽度".format(what)
            )
        width = _digits_to_int(width_text)
        if width is not None:
            if width > MAX_STRING_CHARS:
                raise WorkloadExceeded(
                    "{0} 宽度 {1} 超过 {2} 字符上限：在分配前拒绝".format(
                        what, width, MAX_STRING_CHARS
                    )
                )
            minimum += width
        else:
            minimum += 1
        precision = _digits_to_int(precision_text)
        if precision is not None:
            if precision > MAX_STRING_CHARS:
                raise WorkloadExceeded(
                    "{0} 精度 {1} 超过 {2} 字符上限：在分配前拒绝".format(
                        what, precision, MAX_STRING_CHARS
                    )
                )
            minimum += precision
    if minimum > MAX_STRING_CHARS:
        raise WorkloadExceeded(
            "{0} 结果最小长度 {1} 超过 {2} 字符上限：在分配前拒绝".format(
                what, minimum, MAX_STRING_CHARS
            )
        )


def _deterministic_key(value: Any) -> Tuple[int, str]:
    """外部普通集合元素的兜底排序键（与 hash 种子无关）。

    候选只能构造受限集合（插入顺序固定），本函数只服务“非受限集合混入”的
    防御性路径：按类型分层 + repr 排序，repr 深度受结构检查约束。
    """
    if isinstance(value, bool):
        return (0, "1" if value else "0")
    if value is None:
        return (0, "")
    if isinstance(value, (int, float)):
        return (1, repr(value))
    if isinstance(value, str):
        return (2, value)
    try:
        return (3, repr(value))
    except RecursionError:  # pragma: no cover - 结构检查已限制深度
        return (4, type(value).__name__)


def _deterministic_order(value: Any) -> List[Any]:
    """集合迭代顺序：受限集合用插入顺序；其余按确定性键排序兜底。"""
    order = getattr(value, "_order", None)
    if order is not None:
        return list(order)
    try:
        return sorted(value, key=_deterministic_key)
    except TypeError:  # pragma: no cover - 防御性兜底
        return list(value)


def _unique_in_order(items: Any) -> List[Any]:
    """按首次出现顺序去重（受限冻结集合用它固定迭代顺序）。"""
    seen: Set[Any] = set()
    ordered: List[Any] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            ordered.append(item)
    return ordered


def _make_runtime(Meter meter, collection_cap = MAX_LOCAL_COLLECTION_SIZE):
    """构造受限运行时：插桩助手 + 白名单内建的计费包装。

    计费规范（合同 limits.metering_rules）：每个调用点计 1（_av_pass），
    白名单内建按各自规范再计——len/min/max/abs/round/int/float/bool/range
    计 1；sum/sorted/all/any/map/filter/enumerate/reversed/zip 与容器构造
    按输入长度保守计费；禁止不计费的批量计算。
    """
    cap = collection_cap

    def seq_len(value: Any) -> Optional[int]:
        try:
            return len(value)
        except TypeError:
            return None

    def input_cost(value: Any) -> int:
        length = seq_len(value)
        return length if length is not None else UNSIZEED_INPUT_COST

    def collection_exceed() -> None:
        raise WorkloadExceeded("局部集合超过 {0} 项上限".format(cap))

    def items_structure_cost(items: Any, what: str) -> int:
        """元素级结构代价：排序/极值的 C 层比较也按元素结构计费。"""
        total = 0
        for item in items:
            total += structure_cost(item, what)
            if total > MAX_DATA_CELLS:
                raise WorkloadExceeded(
                    "{0} 结构超过 {1} 单元上限：拒绝递归数据遍历".format(
                        what, MAX_DATA_CELLS
                    )
                )
        return total

    def scan_cost(value: Any, what: str) -> int:
        """线性扫描计费（in / .count / .index）：按长度 + 元素结构代价。"""
        length = seq_len(value)
        if length is None:
            return UNSIZEED_INPUT_COST
        limit = MAX_STRING_CHARS if isinstance(value, str) else cap
        if length > limit:
            raise WorkloadExceeded(
                "{0} 输入长度 {1} 超过 {2} 上限".format(what, length, limit)
            )
        total = max(1, length)
        if isinstance(value, str) or isinstance(value, dict):
            # 字符串逐字符扫描、字典按哈希查找：不再展开（字典值不参与查找）。
            return total
        for item in value:
            total += structure_cost(item, what)
            if total > MAX_DATA_CELLS:
                raise WorkloadExceeded(
                    "{0} 结构超过 {1} 单元上限：拒绝递归数据遍历".format(
                        what, MAX_DATA_CELLS
                    )
                )
        return total

    def guard_format_spec(spec: str, what: str) -> None:
        """格式规范宽度/精度在**分配前**校验（R6/S1）。"""
        width, precision = parse_format_spec(spec)
        if width is not None and width > MAX_STRING_CHARS:
            raise WorkloadExceeded(
                "{0} 宽度 {1} 超过 {2} 字符上限：在分配前拒绝".format(
                    what, width, MAX_STRING_CHARS
                )
            )
        if precision is not None and precision > MAX_STRING_CHARS:
            raise WorkloadExceeded(
                "{0} 精度 {1} 超过 {2} 字符上限：在分配前拒绝".format(
                    what, precision, MAX_STRING_CHARS
                )
            )

    def metered_key(key: Any, what: str) -> Any:
        """给 sorted/min/max 的 key 包装：键结果的结构代价进入计费。

        key 结果的比较发生在 C 层（PyObject_RichCompare），不在 _av_cmp 的
        计费路径上；按每个键结果的结构规模计费即把这条通道关掉。
        """
        if key is None or not callable(key):
            return key

        def key_call(item: Any) -> Any:
            result = key(item)
            meter.charge(structure_cost(result, what))
            return result

        return key_call

    def ordered_input(value: Any) -> Any:
        """R8/N3：原生集合输入的迭代顺序确定化（受限集合已按插入序迭代）。

        候选能构造的集合都已是受限集合（插入序）；这里只处理“混入的普通
        set/frozenset”（例如视图数据或旧对象），按确定键排序后再消费，
        保证跨 PYTHONHASHSEED 的计费与结果一致。
        """
        if isinstance(value, (set, frozenset)) and not isinstance(
            value, (_AvSet, _AvFrozenSet)
        ):
            return _deterministic_order(value)
        return value

    def bounded_items(value: Any, what: str) -> List[Any]:
        """S1 修复：消费可迭代对象的内建统一“先限长（≤cap）再按元素计费”。

        有长度输入：len > cap 即拒绝（最大输入边界），否则按长度计费并
        物化；无长度输入：逐项计费物化（受 cap 约束）。真实遍历只发生在
        本函数内，候选无法再拿到“只计 1 次调用费却遍历百万项”的通道。
        """
        value = ordered_input(value)
        length = seq_len(value)
        if length is None:
            return materialize(value)
        if length > cap:
            raise WorkloadExceeded(
                "{0} 输入长度 {1} 超过 {2} 项上限".format(what, length, cap)
            )
        meter.charge(max(1, length))
        return list(value)

    def num_guard(value: Any) -> Any:
        if isinstance(value, bool):
            return value
        if isinstance(value, int):
            if value > MAX_INT_MAGNITUDE or value < -MAX_INT_MAGNITUDE:
                raise WorkloadExceeded(
                    "整数结果超过 63 位界限：{0}".format(value)
                )
            return value
        if isinstance(value, float):
            if not math.isfinite(value):
                raise WorkloadExceeded("非有限浮点结果（NaN/Inf）使整批失效")
            return value
        return value

    def materialize(iterable: Any) -> List[Any]:
        out: List[Any] = []
        for item in iterable:
            meter.charge(1)
            if len(out) >= cap:
                collection_exceed()
            out.append(item)
        return out

    def av_pass(value: Any) -> Any:
        meter.charge(1)
        if type(value) is str and len(value) > MAX_STRING_CHARS:
            raise WorkloadExceeded(
                "字符串超过 {0} 字符上限".format(MAX_STRING_CHARS)
            )
        return value

    def repeat_guard(seq: Any, times: int) -> None:
        limit = MAX_STRING_CHARS if isinstance(seq, str) else cap
        if times > 0 and len(seq) * times > limit:
            raise WorkloadExceeded(
                "序列重复将超过 {0} 上限".format(limit)
            )

    def av_bin(a: Any, op_name: str, b: Any) -> Any:
        meter.charge(1)
        if op_name == "**":
            if isinstance(b, bool) or not isinstance(b, int) or b < 0 or b > MAX_POWER_EXPONENT:
                raise WorkloadExceeded("** 只允许 0—{0} 的整数指数".format(MAX_POWER_EXPONENT))
        if op_name in ("<<", ">>"):
            if isinstance(b, bool) or not isinstance(b, int) or b < 0 or b > MAX_SHIFT_BITS:
                raise WorkloadExceeded("移位量超过 {0} 位上限".format(MAX_SHIFT_BITS))
        if op_name == "*":
            if isinstance(a, (list, tuple, str)) and isinstance(b, int) and not isinstance(b, bool):
                repeat_guard(a, b)
            elif isinstance(b, (list, tuple, str)) and isinstance(a, int) and not isinstance(a, bool):
                repeat_guard(b, a)
        if op_name == "%" and isinstance(a, str):
            # R6/S1：宽度/精度在分配前校验（修复前先分配 100 MB 再事后检查）。
            percent_format_guard(a, "% 格式化")
            meter.charge(structure_cost(b, "% 格式化右操作数"))
        if op_name in ("|", "-", "&", "^"):
            set_result = combined_set(a, b, op_name)
            if set_result is not None:
                return set_result
            if op_name == "|" and isinstance(a, dict) and isinstance(b, dict):
                return combined_dict(a, b)
        result = _RT_OPS[op_name](a, b)
        if isinstance(result, str) and len(result) > MAX_STRING_CHARS:
            raise WorkloadExceeded("字符串超过 {0} 字符上限".format(MAX_STRING_CHARS))
        if isinstance(result, str):
            # R9/S1b：**字符串产出**按 64 字符一段计费（与字符串哈希/比较同口径）。
            # 修复前拼接与重复只计 1 次运算：`"x"*32768 + "y"*32768` 每次拷贝
            # 64 KiB 却只花 1 个单元，15,000 轮（90,005 ops）能搬 983 MB；
            # 现在的上界是 64 字节/单元（短字符串结果 < 64 字符仍为 0，热路径不变）。
            meter.charge(len(result) // _STRING_COST_CHUNK)
        if isinstance(result, (list, tuple)):
            if len(result) > cap:
                collection_exceed()
            if isinstance(result, list):
                return _AvList(result, cap)
            return result
        if isinstance(result, (set, frozenset)):
            # R6/S1：集合运算结果同样受集合上限约束，并按插入顺序确定化
            # （修复前返回普通 set：长度不受限且迭代顺序随 hash 种子变化）。
            if len(result) > cap:
                collection_exceed()
            meter.charge(max(1, len(result)))
            return _AvSet(_deterministic_order(result), cap, meter)
        return num_guard(result)

    def combined_set(a: Any, b: Any, op_name: str) -> Any:
        """集合运算的确定化重建：顺序 = 左操作数顺序 + 右操作数新增项。"""
        if not isinstance(a, (set, frozenset)) or not isinstance(b, (set, frozenset)):
            return None
        meter.charge(max(1, len(a) + len(b)))
        base = _RT_OPS[op_name](set(a), set(b))
        if len(base) > cap:
            collection_exceed()
        if op_name == "|":
            order = [item for item in _deterministic_order(a)]
            order += [item for item in _deterministic_order(b) if item not in a]
        elif op_name == "&":
            order = [item for item in _deterministic_order(a) if item in b]
        elif op_name == "-":
            order = [item for item in _deterministic_order(a) if item not in b]
        else:  # ^
            order = [item for item in _deterministic_order(a) if item not in b]
            order += [item for item in _deterministic_order(b) if item not in a]
        return _AvSet(order, cap, meter)

    def combined_dict(a: Any, b: Any) -> Any:
        """dict | dict：逐键守卫重建（顺序与 Python 一致：左后右）。

        R8/N1：dict(a)/update(b) 在 C 层哈希全部键，改为经 _AvDict.__setitem__
        重建，键的结构检查与计费与字面量构造走同一通道。
        """
        meter.charge(max(1, len(a) + len(b)))
        merged = _AvDict(cap=cap, meter=meter)
        for key, value in a.items():
            merged[key] = value
        for key, value in b.items():
            merged[key] = value
        return merged

    def av_un(op_name: str, value: Any) -> Any:
        meter.charge(1)
        if op_name == "not":
            return not value
        if op_name == "-":
            return num_guard(-value)
        if op_name == "+":
            return num_guard(+value)
        return num_guard(~value)

    def av_iter(iterable: Any) -> Any:
        for item in iterable:
            meter.charge(1)
            yield item

    def av_cmp(a: Any, op_name: str, b: Any) -> Any:
        """R6/S1：比较与成员查询统一计费，并按操作数结构规模计费。

        - 相等/排序比较：按两侧结构代价计费（标量 0，故标量比较量级不变）；
        - is / is not：身份比较 O(1)，只计 1；
        - in / not in：按被查序列长度（scan_cost）加被查元素结构计费。

        结构代价由 structure_cost 做**有界**遍历并在超深/超宽时提前拒绝，
        所以 CPython 的递归比较不会在指数结构上跑满时间或 C 栈。
        """
        meter.charge(1)
        if op_name in ("is", "is not"):
            return _CMP_OPS[op_name](a, b)
        if op_name in ("in", "not in"):
            meter.charge(scan_cost(b, "成员查询容器") + structure_cost(a, "成员查询元素"))
            return _CMP_OPS[op_name](a, b)
        cost = structure_cost(a, "比较左操作数") + structure_cost(b, "比较右操作数")
        if cost:
            meter.charge(cost)
        return _CMP_OPS[op_name](a, b)

    def av_fvalue(value: Any, spec: Any, conversion: int) -> str:
        """R6/S1：f-string 单值格式化——宽度/精度在分配前校验。

        修复前 f-string 在整段拼接后才检查长度：宽度 2×10^8 的结果先被分配
        （实测峰值 200 MB）才抛超限。这里先按运行时的格式规范解析宽度与精度
        并拒绝超限值，再做 repr/str/ascii 转换与 format()；容器值先做有界结构
        检查，避免 repr 在指数结构上递归展开。
        """
        meter.charge(1)
        meter.charge(structure_cost(value, "f-string 值"))
        if conversion == 114:  # !r
            value = repr(value)
        elif conversion == 115:  # !s
            value = str(value)
        elif conversion == 97:  # !a
            value = ascii(value)
        if spec is None:
            result = format(value, "")
        else:
            if not isinstance(spec, str):
                raise WorkloadExceeded("f-string 格式规范必须是字符串")
            guard_format_spec(spec, "f-string 格式规范")
            result = format(value, spec)
        if type(result) is str and len(result) > MAX_STRING_CHARS:
            raise WorkloadExceeded("字符串超过 {0} 字符上限".format(MAX_STRING_CHARS))
        if type(result) is str:
            # R9/S1b：格式化产出同样按 64 字符一段计费（宽度 65536 的填充
            # 此前 2 个操作就能产出 128 KiB；短结果仍为 0，热路径不变）。
            meter.charge(len(result) // _STRING_COST_CHUNK)
        return result

    def av_sub(value: Any, index: Any) -> Any:
        """R6/S1：切片是批量拷贝——按结果长度计费；下标取值 O(1) 不计。

        R8/N1：`table[深键]` 的字典查找会在 C 层哈希并比较键，深键的
        指数级代价必须先做有界结构检查并计费。
        """
        if isinstance(value, dict):
            meter.charge(structure_cost(index, "下标键"))
        result = value[index]
        if isinstance(index, slice) and isinstance(result, (str, list, tuple)):
            meter.charge(len(result))
        elif isinstance(result, (set, frozenset, dict)) and len(result) > cap:
            collection_exceed()
        return result

    def av_method(obj: Any, name: str) -> Any:
        """R6/S1：方法取值统一包装为计费可调用对象。

        修复前只包装 .count/.index 的直接调用：`count = values.count` 之后再
        调用就完全绕过计费（4096 项列表扫 40 趟只计 8,357）。现在取方法本身
        计 1，返回的可调用对象在每次调用时按方法规范计费：

        - .count/.index：按被查序列长度 + 参数结构计费（真实线性扫描）；
        - .append/.add：先查集合上限再改（任何底层容器都受上限约束）；
        - .get/.items/.keys/.values：只由调用点计 1（键的哈希成本按结构代价
          计入 .get），因此常见只读方法调用的计费量级与修复前一致。

        取值本身（绑定方法）不计费：绑定是 O(1)，真实工作发生在调用时；
        调用点已经有 _av_pass 计 1。
        """
        bound = getattr(obj, name)  # 无该方法时与原生语义一致：立即 AttributeError

        if name in ("count", "index"):

            def scan(*args: Any, **kwargs: Any) -> Any:
                cost = scan_cost(obj, ".{0} 输入".format(name))
                for arg in args:
                    cost += structure_cost(arg, ".{0} 参数".format(name))
                meter.charge(cost)
                return bound(*args, **kwargs)

            return scan

        if name in ("append", "add"):

            def grow(*args: Any, **kwargs: Any) -> Any:
                if len(obj) >= cap:
                    collection_exceed()
                if name == "add" and not isinstance(obj, _AvSet):
                    # R8/N1：受限集合的 add 自带结构守卫与计费；普通 set
                    # （混入对象）在这里补上，别名调用与直接调用走同一通道。
                    for arg in args:
                        meter.charge(structure_cost(arg, ".add 元素"))
                return bound(*args, **kwargs)

            return grow

        def call(*args: Any, **kwargs: Any) -> Any:
            if name == "get" and args:
                # 键的哈希/比较成本：长键或深键按结构代价计费（短键为 0）。
                meter.charge(structure_cost(args[0], ".get 键"))
            return bound(*args, **kwargs)

        return call

    def wrap_list(value: Any) -> Any:
        value = ordered_input(value)
        length = seq_len(value)
        if length is None:
            items = materialize(value)
        else:
            if length > cap:
                collection_exceed()
            items = list(value)
        meter.charge(max(1, len(items)))
        return _AvList(items, cap)

    def wrap_set(value: Any) -> Any:
        """集合构造（字面量 / 推导式 / set()）：按源序插入并逐元素守卫。

        R8/N1+N3：元素在进入原生哈希之前做结构检查并按结构计费；原生
        集合输入先确定化排序，避免迭代顺序随哈希种子漂移。
        """
        value = ordered_input(value)
        length = seq_len(value)
        if length is None:
            items = materialize(value)
        else:
            if length > cap:
                collection_exceed()
            items = list(value)
        meter.charge(max(1, len(items)))
        return _AvSet(items, cap, meter)

    def wrap_dict(value: Any) -> Any:
        """字典构造（字面量 / 推导式 / dict()）：逐键守卫（原生哈希前）。

        R8/N1：修复前 dict(mapping) 先在 C 层哈希全部键，深键的指数级
        哈希/比较完全在保护之外；现在键经 _AvDict.__setitem__ 检查与计费。
        """
        if isinstance(value, dict):
            if len(value) > cap:
                collection_exceed()
            pairs = value.items()
        else:
            length = seq_len(value)
            if length is None:
                pairs = materialize(value)
            else:
                if length > cap:
                    collection_exceed()
                pairs = value
        result = _AvDict(pairs, cap, meter)
        meter.charge(max(1, len(result)))
        return result

    def av_key(value: Any) -> Any:
        """R8/N1：推导式键在进入原生哈希前的守卫与计费（标量代价为 0）。"""
        meter.charge(structure_cost(value, "推导式键"))
        return value

    # —— 白名单内建的计费包装 ——

    def b_len(obj: Any) -> int:
        meter.charge(1)
        return len(obj)

    def b_min(*args: Any, **kwargs: Any) -> Any:
        # S1：单参数形式先限长再按元素计费（min(range(N)) 不再免费遍历 N 项）；
        # 多参数形式比较参数本身，按参数个数计费。
        # R6/S1：极值比较发生在 C 层，按元素结构与 key 结果结构计费并限深。
        if len(args) == 1:
            items = bounded_items(args[0], "min()")
            meter.charge(items_structure_cost(items, "min() 元素"))
            if "key" in kwargs:
                kwargs["key"] = metered_key(kwargs["key"], "min() 键")
            return num_guard(min(items, **kwargs))
        meter.charge(max(1, len(args)))
        meter.charge(items_structure_cost(list(args), "min() 参数"))
        if "key" in kwargs:
            kwargs["key"] = metered_key(kwargs["key"], "min() 键")
        return num_guard(min(*args, **kwargs))

    def b_max(*args: Any, **kwargs: Any) -> Any:
        if len(args) == 1:
            items = bounded_items(args[0], "max()")
            meter.charge(items_structure_cost(items, "max() 元素"))
            if "key" in kwargs:
                kwargs["key"] = metered_key(kwargs["key"], "max() 键")
            return num_guard(max(items, **kwargs))
        meter.charge(max(1, len(args)))
        meter.charge(items_structure_cost(list(args), "max() 参数"))
        if "key" in kwargs:
            kwargs["key"] = metered_key(kwargs["key"], "max() 键")
        return num_guard(max(*args, **kwargs))

    def b_abs(value: Any) -> Any:
        meter.charge(1)
        return num_guard(abs(value))

    def b_round(*args: Any, **kwargs: Any) -> Any:
        meter.charge(1)
        return num_guard(round(*args, **kwargs))

    def b_int(*args: Any, **kwargs: Any) -> Any:
        meter.charge(1)
        return num_guard(int(*args, **kwargs))

    def b_float(value: Any) -> float:
        meter.charge(1)
        result = float(value)
        if not math.isfinite(result):
            raise WorkloadExceeded("float() 转换结果非有限，整批失效")
        return result

    def b_bool(*args: Any, **kwargs: Any) -> bool:
        meter.charge(1)
        return bool(*args, **kwargs)

    def b_range(*args: Any) -> range:
        # S1：range 本身按长度计费并禁止超大构造——len(range(...)) 即元素数，
        # 构造 range(1000000) 立即计满预算并抛 WorkloadExceeded，后续任何
        # 内建/循环都不可能再从超大 range 获得不计费遍历。
        for item in args:
            if isinstance(item, bool) or not isinstance(item, int):
                raise WorkloadExceeded("range 参数必须是 int")
        result = range(*args)
        meter.charge(max(1, len(result)))
        return result

    def b_sum(iterable: Any, *start: Any) -> Any:
        items = bounded_items(iterable, "sum()")
        # R6/S1：序列求和（sum(pairs, ())）按元素结构计费——拼接是批量拷贝。
        meter.charge(items_structure_cost(items, "sum() 元素"))
        # R8/N1：序列起始值会做 len(rows) 次拷贝，最终规模 = len(start) +
        # Σlen(item)，不受单集合上限约束（复审反例 [(1,)*128]*64 + () 得到
        # 8192 项、仅计 138）。评分的求和只需要数值用途，因此**在拷贝之前**
        # 拒绝序列起始值；数值起始值（int/float/bool）仍然允许。
        if start and isinstance(start[0], (list, tuple, str, dict, set, frozenset)):
            raise WorkloadExceeded(
                "sum() 不允许序列起始值（如 sum(rows, ())）：重复拷贝的次数与"
                "最终规模不受单集合上限约束；数值求和请用 sum(rows)"
            )
        return num_guard(sum(items, *start))

    def b_sorted(iterable: Any, **kwargs: Any) -> Any:
        items = bounded_items(iterable, "sorted()")
        # R6/S1：排序比较在 C 层执行，按元素结构与 key 结果结构计费并限深。
        meter.charge(items_structure_cost(items, "sorted() 元素"))
        if "key" in kwargs:
            kwargs["key"] = metered_key(kwargs["key"], "sorted() 键")
        return _AvList(sorted(items, **kwargs), cap)

    def b_all(iterable: Any) -> bool:
        return all(bounded_items(iterable, "all()"))

    def b_any(iterable: Any) -> bool:
        return any(bounded_items(iterable, "any()"))

    def b_enumerate(iterable: Any, *start: Any) -> Any:
        # S1：物化为受限列表（不再返回惰性 enumerate），长度受限、按元素计费。
        items = bounded_items(iterable, "enumerate()")
        return _AvList(list(enumerate(items, *start)), cap)

    def b_reversed(seq: Any) -> Any:
        items = bounded_items(seq, "reversed()")
        return _AvList(items[::-1], cap)

    def b_zip(*seqs: Any) -> Any:
        materialized = [bounded_items(seq, "zip()") for seq in seqs]
        items = list(zip(*materialized))
        if len(items) > cap:
            collection_exceed()
        return _AvList(items, cap)

    def b_map(fn: Any, *seqs: Any) -> Any:
        materialized = [bounded_items(seq, "map()") for seq in seqs]
        items = list(map(fn, *materialized))
        if len(items) > cap:
            collection_exceed()
        return _AvList(items, cap)

    def b_filter(fn: Any, seq: Any) -> Any:
        items = bounded_items(seq, "filter()")
        picked = list(filter(fn, items))
        if len(picked) > cap:
            collection_exceed()
        return _AvList(picked, cap)

    def b_tuple(iterable: Any = ()) -> tuple:
        iterable = ordered_input(iterable)
        length = seq_len(iterable)
        if length is None:
            items = materialize(iterable)
        else:
            if length > cap:
                collection_exceed()
            items = list(iterable)
        meter.charge(max(1, len(items)))
        return tuple(items)

    def b_list(iterable: Any = ()) -> Any:
        return wrap_list(iterable)

    def b_dict(*args: Any, **kwargs: Any) -> Any:
        """dict(...)：与字面量/推导式同一条逐键守卫通道（R8/N1）。"""
        pairs: List[Any] = []
        if args:
            source = args[0]
            if isinstance(source, dict):
                if len(source) > cap:
                    collection_exceed()
                pairs.extend(source.items())
            else:
                pairs.extend(bounded_items(source, "dict()"))
        pairs.extend(kwargs.items())
        if len(pairs) > cap:
            collection_exceed()
        result = _AvDict(pairs, cap, meter)
        meter.charge(max(1, len(result)))
        return result

    def b_set(iterable: Any = ()) -> Any:
        return wrap_set(iterable)

    def b_frozenset(iterable: Any = ()) -> frozenset:
        iterable = ordered_input(iterable)
        length = seq_len(iterable)
        if length is None:
            items = materialize(iterable)
        else:
            if length > cap:
                collection_exceed()
            items = list(iterable)
        meter.charge(max(1, len(items)))
        # R8/N1：冻结集合的构造同样在 C 层哈希元素——逐项结构守卫并计费。
        for item in items:
            meter.charge(structure_cost(item, "frozenset 元素"))
        # R6/S1：冻结集合也按首次出现顺序迭代（跨 hash 种子一致）。
        return _AvFrozenSet(_unique_in_order(items))

    runtime: Dict[str, Any] = {
        _AV_PASS: av_pass,
        _AV_BIN: av_bin,
        _AV_UN: av_un,
        _AV_ITER: av_iter,
        _AV_CMP: av_cmp,
        _AV_METHOD: av_method,
        _AV_FVALUE: av_fvalue,
        _AV_SUB: av_sub,
        _AV_WRAP_LIST: wrap_list,
        _AV_WRAP_DICT: wrap_dict,
        _AV_SET_LIT: wrap_set,
        _AV_DICT_LIT: wrap_dict,
        _AV_KEY: av_key,
        "len": b_len,
        "min": b_min,
        "max": b_max,
        "abs": b_abs,
        "sum": b_sum,
        "sorted": b_sorted,
        "reversed": b_reversed,
        "enumerate": b_enumerate,
        "zip": b_zip,
        "range": b_range,
        "round": b_round,
        "int": b_int,
        "float": b_float,
        "bool": b_bool,
        "all": b_all,
        "any": b_any,
        "tuple": b_tuple,
        "list": b_list,
        "dict": b_dict,
        "set": b_set,
        "frozenset": b_frozenset,
        "map": b_map,
        "filter": b_filter,
    }
    return runtime

