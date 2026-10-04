"""一次同步公开计数作用域的有限缓存；不解析规则，不缓存未见容量。

只接受深模块提供的冻结值白名单。无文件、时钟、网络、第二套规则或
跨模块函数替换；每个结果仍由唯一公开计数原体产生。
"""

from collections import OrderedDict
from dataclasses import fields
from types import SimpleNamespace

_UNSAFE = object()
_VALUE_FIELDS = {'Tile': ('code',), 'PublicMeld': ('seat', 'kind', 'tiles', 'from_seat'), 'PublicEvent': ('seq', 'kind', 'seat', 'tiles', 'occurred_at_unix_sec', 'detail_kind', 'catch_play', 'gang_replenish', 'response_window', 'result_draw', 'result_fan', 'result_details', 'result_scores', 'final_scores', 'claimed_tile'), 'PublicClaimEvidence': ('seat', 'meld_index', 'feeder_seat', 'claimed_tile', 'provenance', 'retained_in_river')}


def _registry_valid(values):
    try:
        return all(tuple(field.name for field in fields(getattr(values, name))) == names
                   for name, names in _VALUE_FIELDS.items())
    except (AttributeError, TypeError):
        return False


class _Identity:
    """强持有完整不可变原件，以对象身份而非不完整字段相等比较。"""

    __slots__ = ("value",)

    def __init__(self, value):
        self.value = value

    def __hash__(self):
        return id(self.value)

    def __eq__(self, other):
        return type(other) is _Identity and self.value is other.value


class _Bounded:
    """局部有限 LRU；身份键持有原件，避免对象编号复用。"""

    def __init__(self, capacity, stats, name):
        self.capacity, self.stats, self.name = capacity, stats, name
        self.rows = OrderedDict()

    def get(self, key):
        value = self.rows.get(key, _UNSAFE)
        if value is not _UNSAFE:
            self.rows.move_to_end(key)
        return value

    def put(self, key, value):
        if key in self.rows:
            self.rows.move_to_end(key)
        elif len(self.rows) >= self.capacity:
            self.rows.popitem(last=False)
            self.stats[self.name + "_evictions"] += 1
        self.rows[key] = value
        self.stats[self.name + "_peak_entries"] = max(
            self.stats[self.name + "_peak_entries"], len(self.rows))

    def clear(self):
        self.rows.clear()


class _PublicCountScope:
    """一次同步构图的纯公开事实缓存；资格和暗牌不进入结果缓存。"""

    def __init__(self, namespace, public_capacity, dependencies_current):
        self.pc = SimpleNamespace(**{name: namespace[name] for name in (
            "Tile", "PublicMeld", "PublicEvent", "PublicClaimEvidence", "PublicTileView")})
        self.dependencies_current = dependencies_current
        self.closed = False
        self.registry_valid = _registry_valid(self.pc)
        self.stats = {
            "public_calls": 0, "public_hits": 0, "public_misses": 0,
            "public_bypasses": 0, "public_failed_calls": 0,
            "river_key_calls": 0, "river_key_hits": 0,
            "river_key_scans": 0, "river_key_derivations": 0,
            "river_append_notices": 0,
            "immutable_container_checks": 0, "immutable_container_hits": 0,
            "immutable_container_bypasses": 0, "oversized_container_bypasses": 0,
            "cleared": False, "restored": False, "closed": False,
            "dependency_bypasses": 0, "registry_bypasses": 0,
        }
        for name in ("public", "river", "container"):
            self.stats[name + "_evictions"] = 0
            self.stats[name + "_peak_entries"] = 0
        self.public = _Bounded(public_capacity, self.stats, "public")
        self.rivers = _Bounded(2048, self.stats, "river")
        self.containers = _Bounded(256, self.stats, "container")
        # 每个字段均遍历，包含 dataclass 的 compare=False 字段；只允许
        # 已注册冻结值类型，不接受任意 dataclass 或带可变相等语义的子类。
        self.allowed_fields = ({
            cls: tuple(field.name for field in fields(cls))
            for cls in (self.pc.Tile, self.pc.PublicMeld, self.pc.PublicEvent,
                        self.pc.PublicClaimEvidence)
        } if self.registry_valid else {})

    def _immutable(self, value):
        stack = [(value, 0)]
        visited = 0
        while stack:
            item, depth = stack.pop()
            visited += 1
            if visited > 131072 or depth > 12:
                return False
            kind = type(item)
            # float 是不可变叶；仅包含在强持有的原件身份中，绝不拿
            # NaN 的数值相等/散列去合并不同历史，也不修改原规则读取。
            if item is None or kind in (bool, int, float, str):
                continue
            if kind is tuple:
                if len(item) > 4096:
                    return False
                stack.extend((part, depth + 1) for part in item)
                continue
            names = self.allowed_fields.get(kind)
            if names is None:
                return False
            try:
                stack.extend((getattr(item, name), depth + 1) for name in names)
            except AttributeError:
                return False
        return True

    def _container_key(self, value):
        if type(value) is not tuple:
            return _UNSAFE
        if len(value) > 4096:
            # tuple 长度固定，先 O(1) 判断，既不扫描也不负缓存可变内容。
            self.stats["oversized_container_bypasses"] += 1
            return _UNSAFE
        identity = _Identity(value)
        known = self.containers.get(identity)
        if known is not _UNSAFE:
            self.stats["immutable_container_hits"] += 1
            return known
        self.stats["immutable_container_checks"] += 1
        if not self._immutable(value):
            self.stats["immutable_container_bypasses"] += 1
            return _UNSAFE
        self.containers.put(identity, identity)
        return identity

    def _river_key(self, river):
        self.stats["river_key_calls"] += 1
        if type(river) is not tuple or len(river) > 4096:
            return _UNSAFE
        identity = _Identity(river)
        known = self.rivers.get(identity)
        if known is not _UNSAFE:
            self.stats["river_key_hits"] += 1
            return known
        self.stats["river_key_scans"] += 1
        if any(type(tile) is not self.pc.Tile or type(tile.code) is not str
               for tile in river):
            return _UNSAFE
        # 保留牌河顺序及重复牌，不以 Counter 或 set 折叠完整原事实。
        encoded = tuple(tile.code for tile in river)
        self.rivers.put(identity, encoded)
        return encoded

    @staticmethod
    def _scalar(value):
        # bool 与 int 分开，None 与0分开；非规范值走原规则，不增新拒绝。
        return ((type(value), value)
                if value is None or type(value) in (int, bool) else _UNSAFE)

    def key(self, view, legacy):
        if type(view) is not self.pc.PublicTileView or type(legacy) is not bool:
            return _UNSAFE
        if (type(view.discards) is not tuple or len(view.discards) != 4
                or type(view.melds) is not tuple or len(view.melds) != 4
                or type(view.hand_counts) is not tuple or len(view.hand_counts) != 4):
            return _UNSAFE
        rivers = tuple(self._river_key(row) for row in view.discards)
        melds = self._container_key(view.melds)
        history = self._container_key(view.public_history)
        claims = self._container_key(view.claim_evidence)
        hands = tuple(self._scalar(value) for value in view.hand_counts)
        wall = self._scalar(view.remaining_tile_count)
        snapshot, consumed = self._scalar(view.snapshot_seq), self._scalar(view.consumed_seq)
        if any(value is _UNSAFE for value in
               (*rivers, melds, history, claims, *hands, wall, snapshot, consumed)):
            return _UNSAFE
        # 字段顺序与 _VIEW_FIELDS 同步；历史、副露、证据身份持有其全字段。
        # 此处不放本人暗牌/抓打资格：它们不参与 PublicTileCounts；原 unseen
        # 函数仍逐次读取 concealed/drawn_tile/seat/chain_piao 并执行全部守卫。
        return (rivers, melds, hands, wall, history, snapshot, consumed, claims, legacy)

    def count(self, original, view, legacy):
        if self.closed:
            return original(view, legacy_four_meld=legacy)
        self.stats["public_calls"] += 1
        if not self.registry_valid or not self.dependencies_current():
            reason = "registry_bypasses" if not self.registry_valid else "dependency_bypasses"
            self.stats[reason] += 1
            self.stats["public_bypasses"] += 1
            self.clear()
            try:
                return original(view, legacy_four_meld=legacy)
            except BaseException:
                self.stats["public_failed_calls"] += 1
                raise
        try:
            key = self.key(view, legacy)
        except (AttributeError, TypeError, RecursionError):
            # 不完整/非规范原件不增加新的拒绝，交回原函数给出原有异常。
            key = _UNSAFE
        if key is _UNSAFE:
            self.stats["public_bypasses"] += 1
        else:
            cached = self.public.get(key)
            if cached is not _UNSAFE:
                self.stats["public_hits"] += 1
                return cached
            self.stats["public_misses"] += 1
        try:
            result = original(view, legacy_four_meld=legacy)
        except BaseException:
            self.stats["public_failed_calls"] += 1
            raise
        if key is not _UNSAFE:
            self.public.put(key, result)
        return result

    def note_river_append(self, old, new, tile):
        """仅给实际old+(tile,)构造元组登记键；不读取或推导库存。"""
        self.stats["river_append_notices"] += 1
        if (self.closed or not self.registry_valid or not self.dependencies_current()
                or type(tile) is not self.pc.Tile or type(tile.code) is not str
                or type(new) is not tuple or len(new) > 4096):
            return
        old_key = self._river_key(old)
        if old_key is _UNSAFE:
            return
        self.rivers.put(_Identity(new), old_key + (tile.code,))
        self.stats["river_key_derivations"] += 1

    def clear(self):
        self.public.clear()
        self.rivers.clear()
        self.containers.clear()
        self.stats["cleared"] = True

