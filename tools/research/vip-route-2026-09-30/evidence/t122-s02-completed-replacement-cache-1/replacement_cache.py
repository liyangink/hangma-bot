"""同一投影复用已完整生成的杠补子图；不复用旧条件状态或删合法根。

此前完成选择缓存在给定补牌与规则分析之后才命中。本原型额外对完整
待补牌事实建键，只有相同根身份、全公开证据与规范不可变状态才复用
完成节点引用，省掉同一杠补子图的重复给定补牌和规则分析。
"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t122-s02-completed-replacement-cache-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
from dataclasses import fields
from hangma_bot.hangma import progression, public_tile_counts as public
from hangma_bot.hangma.route_transition import ConditionalIdentity, ConditionalPhase, ConditionalRouteState
from hangma_bot.kernel.actions import CANONICAL_TILE_ORDER, Tile
from hangma_bot.kernel.observation import PublicDiscard


class OwnedIdentity:
    """强持有历史原件；比较对象身份，不让释放后编号复用成为命中。"""
    def __init__(self,value): self.value=value
    def __hash__(self): return id(self.value)
    def __eq__(self,other): return type(other) is OwnedIdentity and self.value is other.value


def immutable(value):
    """只接受已知不可变状态原件及原始类型；自定义对象交回原路径。"""
    kind=type(value)
    if value is None or kind in (bool,int,str) or kind is ConditionalPhase:
        return True
    if kind is tuple:
        return all(immutable(item) for item in value)
    if kind in (Tile,PublicDiscard,progression.CatchPlayState):
        return all(immutable(getattr(value,field.name)) for field in fields(value))
    return False


def tagged(value):
    """保留所有原始值的精确类型，避免bool/int或枚举/字符串相等碰撞。"""
    kind=type(value)
    if kind is tuple:
        return (kind,tuple(tagged(item) for item in value))
    if kind in (Tile,PublicDiscard,progression.CatchPlayState):
        return (kind,tuple((field.name,tagged(getattr(value,field.name)))
                         for field in fields(value)))
    return (kind,value)


def make_projection(base):
    class CompletedReplacementProjection(base):
        """仅缓存完成后的根节点，所有关键条件保留在键中。"""
        def __init__(self,*args,**kwargs):
            super().__init__(*args,**kwargs)
            self.completed_replacements={}
            self.replacement_calls=self.replacement_hits=self.replacement_misses=self.replacement_bypasses=0

        def replacement_key(self,state):
            if (type(state) is not ConditionalRouteState
                    or state.phase is not ConditionalPhase.REPLACEMENT_DRAW
                    or state.structural_only is not False or state.drawn_tile is not None
                    or state.terminal_result is not None
                    or type(state.seat) is not int or state.seat not in range(4)
                    or type(state.dealer_seat) is not int or state.dealer_seat not in range(4)
                    or type(state.meld_count) is not int or state.meld_count not in range(5)
                    or type(state.wall_remaining) is not int or state.wall_remaining<=20
                    or type(state.concealed) is not tuple
                    or len(state.concealed)!=13-3*state.meld_count
                    or any(type(tile) is not Tile or type(tile.code) is not str
                           or tile.code not in CANONICAL_TILE_ORDER for tile in state.concealed)):
                return None
            identity=state.identity
            if (type(identity) is not ConditionalIdentity or type(identity.game_id) is not str
                    or type(identity.round_no) is not int or type(identity.root_action_key) is not str
                    or type(identity.ruleset_version) is not str
                    or type(identity.path) is not tuple
                    or any(type(item) is not str for item in identity.path)):
                return None
            view,root=state.public_view,state.root_public_view
            if (type(view) is not public.PublicTileView or type(root) is not public.PublicTileView
                    or not self.input_guard.valid(root,public.PublicTileView)
                    or not self.input_guard.valid(view,public.PublicTileView)):
                return None
            # 保留副露顺序和全部领取证据；此原型不新增暗杠排列规范化。
            view_key=tuple((field.name,OwnedIdentity(getattr(view,field.name))
                           if field.name=='public_history' else getattr(view,field.name))
                          for field in fields(view))
            values=[]
            for field in fields(state):
                value=getattr(state,field.name)
                if field.name=='identity':
                    value=(identity.game_id,identity.round_no,identity.root_action_key,identity.ruleset_version)
                elif field.name=='concealed':
                    value=tuple(sorted(tile.code for tile in value))
                elif field.name=='root_public_view':
                    value=OwnedIdentity(value)
                elif field.name=='public_view':
                    value=view_key
                elif not immutable(value):
                    return None
                else:
                    value=tagged(value)
                values.append((field.name,value))
            signature=tuple(values)
            try: hash(signature)
            except TypeError: return None
            return signature

        def replacement(self,state,key):
            self.replacement_calls+=1
            signature=self.replacement_key(state)
            if signature is None:
                self.replacement_bypasses+=1
                return super().replacement(state,key)
            previous=self.completed_replacements.get(signature)
            if previous is not None:
                self.replacement_hits+=1
                return previous
            self.replacement_misses+=1
            result=super().replacement(state,key)
            if len(self.completed_replacements)<self.limits.max_nodes:
                self.completed_replacements[signature]=result
            return result
    return CompletedReplacementProjection
