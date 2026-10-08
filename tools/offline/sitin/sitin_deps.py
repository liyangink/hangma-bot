# -*- coding: utf-8 -*-
"""P3 RUNID · 运行身份依赖登记表：动态 sibling 装载与真实装配入口的**唯一登记处**。

为什么必须单独有这一层（R8 复审 §3 S2，P1）：
  冻结清单此前只从「执行器/规则/模拟器」几个第一方根走 `hangma_bot.*` 传递闭包，
  编排侧工具文件（`sitin_natural_panel.py` 等）只哈希**自身字节**。于是真实装配入口
  实际执行到的 `hangma_bot.offline.evaluate.drive_match`（桌赛驱动）、
  `hangma_bot.bootstrap.build_evaluation_runtime`（组合根）及其传递依赖不在任何摘要
  面内——纯内存改一个方法体（只编译、从不执行）、冻结摘要不变、身份核验照样通过。
  同时 `_sibling` 这类**动态装载**按名字从同目录 exec 模块：装载进来的实现既没有
  登记、也不会进清单，漏项因此是静默的。

本模块只做三件事，都是**登记**（不含任何业务逻辑，也不 import 任何工具/业务模块——
它是登记表本身，同时是 `_sibling` 缺项拒绝的判据来源，反向依赖会成环）：

  1. `SIBLING_MODULES`：动态 sibling 装载的显式登记表（名字 → 角色）。装载检查
     `require_sibling` 在**登记不到时直接失败**（`UnregisteredSiblingLoad`），
     不静默跳过、不退回“没装载过”。
  2. `ENTRY_FILES`：真实装配入口（编排状态机 + 桌赛执行件 + 全部登记 sibling +
     本登记表自身）。入口清单由 `SIBLING_MODULES` 派生，二者不可能漂移。
  3. `entry_call_graph`：**入口调用图**枚举——从入口文件出发，沿 import 关系走
     `hangma_bot.*` 模块与同目录工具模块的传递闭包，逐节点给出所在文件与实际摘要。
     清单覆盖由这张图决定，而不是由人工维护的模块名列表决定。

**缺项即失败关闭**（`ManifestCoverageGap`）：入口文件里出现「指向同目录工具的
动态装载，但该名字未登记」或「第一方 `hangma_bot.*` 模块解析不到文件」时，
清单计算直接失败——宁可拒绝所有保存/恢复，也不产生一份看起来完整的清单。

证据边界：本模块只做静态解析与文件摘要，不产生 import 副作用、不联网、
不执行候选代码。
"""
from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/llm-guided-heuristic-route-2026-09-15/tools'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

import ast
import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import (Any, Callable, Dict, Iterable, List, Mapping, Optional,
                    Sequence, Tuple)

#: 仓库根（本文件位于 <repo>/review/llm-guided-heuristic-route-2026-09-15/tools/）。
REPO_ROOT = _PROJECT_ROOT
#: 同目录工具目录。
TOOLS_DIR = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/tools')
#: 第一方业务源码根。
SRC_ROOT = _project_file(_PROJECT_ROOT, REPO_ROOT / "src")


class UnregisteredSiblingLoad(RuntimeError):
    """动态 sibling 装载请求了**未登记**的名字：失败关闭（缺项拒绝，不静默跳过）。"""


class ManifestCoverageGap(RuntimeError):
    """冻结清单覆盖缺口（未登记的动态装载 / 解析不到的第一方模块）：拒绝出清单。"""


class ManifestReadError(ManifestCoverageGap):
    """清单文件**读不了**（不存在 / 不是普通文件 / 权限不足）：清单身份无法计算。

    与 ManifestParseError 同族、同一处置口径（P14-FU1 收残留）：读不到字节的文件，
    它的**内容摘要**与 **import 事实**两样都拿不到，于是清单会"看起来完整"地漏掉它
    （以及它带进来的依赖子树）。旧实现在 `module_imports` 与两个扫描器里
    `except OSError: continue/return []`——读失败与"这个文件没有依赖"再次被混为一谈。

    判据不是"能不能读到"这一条：**条目由调用方点名的文件**都必须给出事实；
    点名了却读不到 ⇒ 具名拒绝，而不是少一条记录继续出清单。
    """

    def __init__(self, path: Path, *, dotted: str, reason: str) -> None:
        self.path = Path(path)
        self.dotted = str(dotted)
        self.reason = str(reason)
        super().__init__(
            "清单文件读不了：{0}（模块 {1}）——{2}。该文件的内容摘要与 import 事实"
            "都拿不到，冻结清单的**清单身份无法计算**（依赖闭包会漏掉它所在的子树），"
            "因此这**不是运行结果问题**而是身份问题；按缺项失败关闭拒绝出清单"
            "（R8 §3 S2）。这不是「没有依赖」，而是「没看到这个文件」——**不静默跳过**。"
            .format(_relpath(self.path), self.dotted, self.reason))


class ManifestParseError(ManifestCoverageGap):
    """清单文件**解析失败**（语法/编码错误）：清单身份无法计算，拒绝出清单。

    为什么必须具名失败、不许静默跳过（P14；并发写入/半截文件是真实触发形态）：
    解析不到 import 事实的文件，其真实依赖不会进闭包——旧实现里
    `_refs_from_tree` 返回空列表、两个扫描器 `continue`，于是清单**看起来完整**
    地漏掉整棵依赖子树，旧结果可以跨实现复用（R8 §3 S2 的身份洞）。另外一处消费点
    没有判空，直接崩成 `TypeError: 'NoneType' object is not iterable`——崩溃能看见，
    静默漏项看不见，后者才是身份洞。

    异常原文写清三件事：**哪个文件**、**原因（语法错误原文）**、**这是清单身份
    无法计算，不是运行结果问题**（所以处置方式是让写入完成/修好源码后重算清单，
    而不是"跳过这个文件继续出清单"）。

    判据只针对 **Python 源码**（`.py`/`.pyi`，见 `is_python_source`）：原生扩展
    （`_grouped_native.cpython-311-*.so` 这类）**本来就没有** Python import 事实，
    解析不了不是缺陷，其身份由字节摘要面（`av_dependency_file_reader`）覆盖——
    把两者混为一谈会让清单在机器上直接出不来（P14 实测：29 条既有无辜回归）。
    """

    def __init__(self, path: Path, *, dotted: str, reason: str) -> None:
        self.path = Path(path)
        self.dotted = str(dotted)
        self.reason = str(reason)
        super().__init__(
            "清单文件解析失败：{0}（模块 {1}）——{2}。该文件的 import 事实无法提取，"
            "冻结清单的**清单身份无法计算**：依赖闭包会漏掉这棵子树，因此这**不是"
            "运行结果问题**而是身份问题；按缺项失败关闭拒绝出清单（R8 §3 S2：宁可"
            "拒绝所有保存/恢复，也不产生一份看起来完整的清单）。并发写入/半截文件"
            "请等写入完成、语法错误请修好源码后重算清单——**不静默跳过该文件**。"
            .format(_relpath(self.path), self.dotted, self.reason))


@dataclass(frozen=True)
class SiblingSpec:
    """一个动态 sibling 模块的登记项。

    - name：`sys.modules` 里的模块名（也就是同目录文件名去掉 .py）；
    - role：它在装配链里承担什么（进报告，供人核对“为什么这个模块必须在清单里”）；
    - in_manifest：是否作为**真实装配入口**进冻结清单。当前全部为 True：任何被
      动态装载进来的 sibling 都参与本次运行的实际执行，没有理由豁免。
    """

    name: str
    role: str
    in_manifest: bool = True


#: 动态 sibling 装载的**显式登记表**（R9 P3 覆盖缺口修复项 2）。
#: 取值来源：对 tools/*.py 做 AST 扫描，收集「以同目录工具文件名为字面量的动态装载
#: 调用」（`_sibling` / `sibling` / `_load` / `_load_sibling` /
#: `spec_from_file_location` / 其它以工具名为参数的装载器）；扫描器保留在本模块
#: （`scan_dynamic_sibling_loads`），由测试对**全目录**复核，避免本表随新工具漂移。
SIBLING_MODULES: Mapping[str, SiblingSpec] = {
    "sitin_archive": SiblingSpec(
        "sitin_archive", "C2 统计/档案/提名/选席（配对统计与行为签名摘要的消费端）"),
    "sitin_config": SiblingSpec(
        "sitin_config", "运行账本/配额配置（桌赛预算口径）"),
    # 登记表自身：由 `sitin_search._deps()` 自举装载（唯一不经登记检查的装载点，
    # 否则登记检查的判据来源要自己登记自己，成环）。它照样是入口文件、照样进摘要。
    "sitin_deps": SiblingSpec(
        "sitin_deps", "依赖登记表自身（_deps 自举装载的唯一例外；入口调用图的根源）"),
    "sitin_feedback": SiblingSpec(
        "sitin_feedback", "三段反馈投影（事实/关联结果的唯一程序化来源）"),
    "sitin_gates": SiblingSpec(
        "sitin_gates", "门禁与身份（契约摘要、候选身份、覆盖层、受监管装载）"),
    "sitin_generate": SiblingSpec(
        "sitin_generate", "候选生成与受监管子进程装载（TaskContract 渲染）"),
    "sitin_m4_policy": SiblingSpec(
        "sitin_m4_policy", "M4 策略实现（重算/机制率工具的装载目标）"),
    "sitin_m4_recompute": SiblingSpec(
        "sitin_m4_recompute", "M4 重算（机制率与门禁侧重算）"),
    "sitin_model_admission": SiblingSpec(
        "sitin_model_admission", "模型准入判分器（能力分数与行为偏好签名）"),
    "sitin_natural_panel": SiblingSpec(
        "sitin_natural_panel",
        "自然开局面板：**真实桌赛驱动**（offline.evaluate.drive_match）"),
    "sitin_opportunities": SiblingSpec(
        "sitin_opportunities", "C1 条件面板：真实桌赛驱动与双臂费用账"),
    "sitin_power": SiblingSpec(
        "sitin_power", "统计功效计算（S0 工具的装载目标）"),
    "sitin_process": SiblingSpec(
        "sitin_process", "受监管子进程执行（超时/资源上限）"),
    "sitin_real_behavior": SiblingSpec(
        "sitin_real_behavior", "真实开发观察的生产计划重放与冻结面板身份"),
    "sitin_execution_audit": SiblingSpec(
        "sitin_execution_audit", "自然桌评分执行诊断、持久化一致性与未知计数核验"),
    "sitin_execution_profile": SiblingSpec(
        "sitin_execution_profile", "有界离线执行配置、身份参数与研究资格分离"),
    "sitin_scenario_classes": SiblingSpec(
        "sitin_scenario_classes", "场景分类（面板缓存侧装载）"),
    "sitin_scheduler": SiblingSpec(
        "sitin_scheduler", "同面板调度与场次计划（轮换/种子派生）"),
    "sitin_stage": SiblingSpec(
        "sitin_stage", "阶段桌赛执行：**真实桌赛驱动**（offline.evaluate.drive_match）"),
}

#: 清单侧入口模块：编排状态机 + 登记表自身 + 全部登记 sibling。
#: 由 SIBLING_MODULES 派生（不是人工维护的第二份名单）。
#: 去重且顺序稳定（sitin_deps 已在登记表内，不重复列）。
ENTRY_MODULES: Tuple[str, ...] = tuple(dict.fromkeys(
    ("sitin_search",) + tuple(
        sorted(name for name, spec in SIBLING_MODULES.items() if spec.in_manifest))))
#: 入口文件（tools/ 下文件名）。
ENTRY_FILES: Tuple[str, ...] = tuple(name + ".py" for name in ENTRY_MODULES)


def sibling_specs() -> Tuple[SiblingSpec, ...]:
    """登记项（按名字排序，输出稳定）。"""

    return tuple(SIBLING_MODULES[name] for name in sorted(SIBLING_MODULES))


def require_sibling(name: str, *, loader: str = "_sibling") -> SiblingSpec:
    """动态装载前的**登记检查**：登记不到即失败关闭。

    为什么不是「查不到就照旧装载」：静默跳过正是 S2 的漏项形态——被装载进来的
    实现既不在清单里、也不在任何报告里，旧结果可以跨实现复用。这里选择让调用点
    直接失败，缺口在第一次装载时暴露，而不是在若干轮之后的身份核验里。
    """

    spec = SIBLING_MODULES.get(str(name))
    if spec is None:
        raise UnregisteredSiblingLoad(
            "动态 sibling 装载被拒绝：{0!r} 未登记（loader={1}）。"
            "新工具模块必须在 tools/sitin_deps.py 的 SIBLING_MODULES 里显式登记"
            "（含 role），否则它的实现不进冻结清单，旧结果可跨实现复用（R8 §3 S2）"
            .format(name, loader))
    return spec


def _digest_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _relpath(path: Path) -> str:
    """仓库内相对路径（清单可读、跨检出稳定；不在仓库内则原样）。

    先按**字面路径**算，再按解析后的路径算：隔离验证树里 `src/` 是软链，字面路径
    在树内、解析后的路径在真实仓库里——只按解析路径算会退化成绝对路径，
    报告里的"入口 → 登记项"对照表就不可读了（身份摘要不依赖本函数，见
    `av_manifest_identity_payload`）。
    """

    candidate = Path(path)
    for base, item in ((REPO_ROOT, candidate),
                       (REPO_ROOT.resolve(), candidate.resolve())):
        try:
            return item.relative_to(base).as_posix()
        except ValueError:
            continue
    return candidate.as_posix()


def _base_package(dotted: str, path: Path) -> str:
    """相对导入的基准包名。

    包（`__init__.py`）里 `from .x import y` 的基准是**包自身**，普通模块里是它的
    父包。两处旧实现都按父包算，于是 `hangma_bot/offline/__init__.py` 的
    `from .evaluate import ...` 被解析成 `hangma_bot.evaluate`（不存在），真实依赖
    `hangma_bot.offline.evaluate` 反而没进闭包——这正是 S2 漏项形态之一。
    """

    if Path(path).name == "__init__.py":
        return dotted
    return dotted.rsplit(".", 1)[0] if "." in dotted else dotted


def _strip_package(dotted: str, levels: int) -> str:
    """按相对层级向上走 levels 层包（levels 为 `ast.ImportFrom.level - 1`）。"""

    base = dotted
    for _ in range(max(0, int(levels))):
        base = base.rsplit(".", 1)[0] if "." in base else base
    return base


@dataclass(frozen=True)
class ImportRef:
    """一条 import 事实。

    - name：被引用的（可能是）模块名；
    - required：True = `import a.b` / `from a.b import ...` 里的模块名，**必须**能
      解析到文件；False = `from a.b import c` 里的 `c`（可能是子模块，也可能只是
      属性），解析不到不算缺口。
    """

    name: str
    required: bool


#: 解析缓存：键为（文件路径，内容摘要）。进程内重复计算清单时省掉重复 parse；
#: 键含内容摘要，因此**注入的改动**（reader 返回不同字节）一定命中不同键，不会
#: 把旧图当成新图——这是"缓存不得掩盖身份变化"的最低要求。上限兜底防无界增长。
_PARSE_CACHE: Dict[Tuple[str, str], Optional[ast.Module]] = {}
#: 解析失败的原因原文（键与 _PARSE_CACHE 同构）：具名拒绝时逐字带出，
#: 不需要重新 parse 一次就能说清"是哪个语法错误"。
_PARSE_ERRORS: Dict[Tuple[str, str], str] = {}
_PARSE_CACHE_LIMIT = 4096


def _cache_key(path: Path, data: bytes) -> Tuple[str, str]:
    return (str(path), _digest_bytes(data))


def _parse_error_text(error: BaseException) -> str:
    """错误原文：异常类型 + 原文（SyntaxError 另带出错行文本，便于现场定位）。"""

    text = "{0}: {1}".format(type(error).__name__, error)
    line = getattr(error, "text", None)
    if isinstance(line, str) and line.strip():
        text += "（出错行：{0}）".format(line.strip())
    return text


def _parse_cached(path: Path, data: bytes) -> Optional[ast.Module]:
    """按（路径，内容摘要）缓存 AST；解析失败记 None 并记下原因（不伪造）。

    注意：`None` **只在缓存内部**表示"这个字节序列解析不了"。消费侧不允许把 None
    当成"没有 import"——那是静默漏项，见 `_parse_source_required` /
    `_parse_any_optional` 与 ManifestParseError。
    """

    key = _cache_key(path, data)
    if key in _PARSE_CACHE:
        return _PARSE_CACHE[key]
    try:
        tree: Optional[ast.Module] = ast.parse(data.decode("utf-8"))
    except (SyntaxError, UnicodeDecodeError, ValueError) as error:
        tree = None
        _PARSE_ERRORS[key] = _parse_error_text(error)
    if len(_PARSE_CACHE) >= _PARSE_CACHE_LIMIT:
        _PARSE_CACHE.clear()
        _PARSE_ERRORS.clear()
    _PARSE_CACHE[key] = tree
    return tree


#: Python 源码后缀：只有这些文件才谈得上"解析失败 = 清单身份不可计算"。
SOURCE_SUFFIXES: Tuple[str, ...] = (".py", ".pyi")


def is_python_source(path: Path) -> bool:
    """是否 Python 源码（清单侧判据的唯一入口，按后缀判定，不看内容猜）。"""

    return Path(path).suffix.lower() in SOURCE_SUFFIXES


def _parse_source_required(path: Path, data: bytes, *, dotted: str) -> ast.Module:
    """解析 **Python 源码**；失败即**具名拒绝**（不返回 None、不静默跳过）。

    这是"解析失败"与"解析出零条 import"之间唯一的区分点：拿到源码的调用方一定拿到
    语法树，于是「这个文件没有依赖」只能是事实，不可能来自一次失败的解析。
    """

    tree = _parse_cached(Path(path), data)
    if tree is None:
        raise ManifestParseError(
            Path(path), dotted=dotted,
            reason=_PARSE_ERRORS.get(_cache_key(Path(path), data), "解析失败（原因未记录）"))
    return tree


def _parse_any_optional(path: Path, data: bytes, *, dotted: str,
                        ) -> Optional[ast.Module]:
    """解析**可能不是源码**的文件（原生扩展等）：源码失败即具名拒绝，非源码返回 None。

    为什么非源码不算缺口：`.so`/`.pyd` 里不可能有 Python import 事实，**没有东西可漏**；
    它们的身份由字节摘要面覆盖（`av_dependency_file_reader` → sha256）。把"解析不了
    二进制"当成身份洞，只会让清单在这台机器上整体出不来。
    """

    if not is_python_source(path):
        return None
    return _parse_source_required(path, data, dotted=dotted)


def _refs_from_tree(tree: Optional[ast.Module], dotted: str, path: Path,
                    ) -> List[ImportRef]:
    """从语法树提取 import 事实（含函数内导入与相对导入）。

    `tree is None` 的含义被收窄为**一种**：这个文件不是 Python 源码（无 import 事实）。
    Python 源码解析失败不会走到这里——`_parse_any_optional` 已经具名拒绝了。
    """

    if tree is None:
        return []
    package = _base_package(dotted, path)
    found: List[ImportRef] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.extend(ImportRef(alias.name, True) for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            level = int(node.level or 0)
            base = _strip_package(package, level - 1) if level else ""
            if node.module:
                dotted_module = (base + "." + node.module) if level else node.module
                found.append(ImportRef(dotted_module, True))
                found.extend(ImportRef(dotted_module + "." + alias.name, False)
                             for alias in node.names)
            else:
                found.extend(ImportRef(base + "." + alias.name, True)
                             for alias in node.names)
    return found


def module_imports(path: Path, dotted: str) -> List[ImportRef]:
    """解析一个模块文件的 import（含函数内导入与相对导入）。

    直接读文件字节（不注入 reader）：这是给调用方按路径解析用的公开入口；
    清单侧走 `entry_call_graph`，那里的字节来自注入的 reader，二者不混用。
    """

    try:
        data = Path(path).read_bytes()
    except OSError as error:
        # P14-FU1：读不到字节 = 内容摘要与 import 事实两样都没有 ⇒ 具名失败关闭
        # （旧实现返回空列表，与"这个文件没有 import"无法区分）。
        raise ManifestReadError(Path(path), dotted=dotted,
                                reason="{0}: {1}".format(type(error).__name__, error))
    return _refs_from_tree(_parse_any_optional(Path(path), data, dotted=dotted),
                           dotted, Path(path))


def module_imports_of(data: bytes, dotted: str, path: Path) -> List[ImportRef]:
    """按**给定字节**解析 import（清单侧：字节来自注入的 reader）。

    Python 源码解析失败即抛 `ManifestParseError`（具名、失败关闭）：入口调用图宁可
    拒绝出清单，也不把"解析不了"当成"没有依赖"（S2 身份洞）。
    """

    return _refs_from_tree(_parse_any_optional(Path(path), data, dotted=dotted),
                           dotted, Path(path))


def resolve_tool(name: str, *, tools_dir: Optional[Path] = None) -> Optional[Path]:
    """同目录工具模块名 → 文件（不是工具模块返回 None）。"""

    root = Path(tools_dir or TOOLS_DIR)
    if "." in name:
        return None
    path = root / (name + ".py")
    return path if path.is_file() else None


def resolve_module(dotted: str, *, src_root: Optional[Path] = None) -> Optional[Path]:
    """第一方模块名 → 文件（只在仓库 src/ 下解析，不伪造、不猜）。"""

    import importlib.util

    if not (dotted == "hangma_bot" or dotted.startswith("hangma_bot.")):
        return None
    try:
        spec = importlib.util.find_spec(dotted)
    except (ImportError, ModuleNotFoundError, ValueError, AttributeError):
        return None
    origin = getattr(spec, "origin", None)
    if not origin:
        return None
    path = Path(origin)
    if not path.is_file():
        return None
    root = Path(src_root or SRC_ROOT)
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return None
    return path


def scan_dynamic_sibling_loads(*, tools_dir: Optional[Path] = None,
                               files: Optional[Iterable[str]] = None,
                               ) -> Dict[str, Tuple[str, ...]]:
    """静态扫描动态 sibling 装载调用：工具模块名 → 装载点（文件:函数）列表。

    判据刻意保守：调用实参里出现**同目录已有工具文件的名字字面量**，即认为该模块
    会被动态装载（`_sibling("sitin_process")`、`sibling("sitin_gates")`、
    `spec_from_file_location("sitin_power", ...)` 都命中）。因此本表可以机械复核，
    不依赖“谁知道谁装载了谁”。
    """

    root = Path(tools_dir or TOOLS_DIR)
    stems = {path.stem for path in root.glob("*.py")}
    found: Dict[str, set] = {}
    names = list(files) if files is not None else sorted(
        path.name for path in root.glob("*.py"))
    for filename in names:
        path = root / filename
        # P14-FU1：点名了却读不到 ⇒ 具名拒绝（旧实现两处 continue 都静默）。
        if not path.is_file():
            raise ManifestReadError(path, dotted=Path(filename).stem,
                                    reason="文件不存在或不是普通文件")
        if not is_python_source(path):
            # 非 Python 源码（误传 .so/.json 等）里不可能有 sibling 装载调用：
            # 不是"漏项"，直接不看（源码文件的解析失败仍走下面的具名拒绝）。
            continue
        try:
            data = path.read_bytes()
        except OSError as error:
            raise ManifestReadError(path, dotted=Path(filename).stem,
                                    reason="{0}: {1}".format(type(error).__name__, error))
        # P14：解析失败即**具名拒绝**（旧实现在这里 ast.walk(None) 崩成
        # AttributeError/TypeError；崩掉还能看见，静默漏项看不见，故统一失败关闭）。
        tree = _parse_source_required(path, data, dotted=Path(filename).stem)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            callee = node.func
            if isinstance(callee, ast.Name):
                caller = callee.id
            elif isinstance(callee, ast.Attribute):
                caller = callee.attr
            else:
                continue
            arguments = list(node.args) + [keyword.value for keyword in node.keywords]
            for argument in arguments:
                if isinstance(argument, ast.Constant) \
                        and isinstance(argument.value, str) \
                        and argument.value in stems \
                        and argument.value != Path(filename).stem:
                    found.setdefault(argument.value, set()).add(
                        "{0}:{1}".format(filename, caller))
    return {name: tuple(sorted(sites)) for name, sites in found.items()}


#: 第一方模块的**按名装载**调用（反射装载；与 sibling 装载同属"动态装载"）。
MODULE_LOADER_NAMES: Tuple[str, ...] = ("_av_module", "import_module", "__import__")


def scan_literal_module_loads(*, tools_dir: Optional[Path] = None,
                              files: Optional[Iterable[str]] = None,
                              ) -> Dict[str, Tuple[str, ...]]:
    """扫描**字面量**的第一方模块装载调用：模块名 → 装载点（文件:调用名）列表。

    为什么单列一类：`sitin_gates._av_module("hangma_bot.x")` 之类的调用按名字
    import 模块，静态 import 图看不到它。当前入口链里 10 处都在清单内（实测），
    但"新增一处没进清单的按名装载"与 S2 的 sibling 漏项是同一形态，
    因此纳入覆盖缺口的判据（见 coverage_gaps）。
    """

    root = Path(tools_dir or TOOLS_DIR)
    found: Dict[str, set] = {}
    names = list(files) if files is not None else sorted(
        path.name for path in root.glob("*.py"))
    for filename in names:
        path = root / filename
        if not path.is_file():
            raise ManifestReadError(path, dotted=Path(filename).stem,
                                    reason="文件不存在或不是普通文件")
        if not is_python_source(path):
            continue                     # 同上：非源码不含按名装载调用
        try:
            data = path.read_bytes()
        except OSError as error:
            raise ManifestReadError(path, dotted=Path(filename).stem,
                                    reason="{0}: {1}".format(type(error).__name__, error))
        # P14：旧实现 `if tree is None: continue` 会**静默跳过**解析不了的文件——
        # 该文件的按名装载全部漏出判据，"清单看起来完整"。改为具名拒绝。
        tree = _parse_source_required(path, data, dotted=Path(filename).stem)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not node.args:
                continue
            callee = node.func
            if isinstance(callee, ast.Name):
                caller = callee.id
            elif isinstance(callee, ast.Attribute):
                caller = callee.attr
            else:
                continue
            if caller not in MODULE_LOADER_NAMES:
                continue
            first = node.args[0]
            if isinstance(first, ast.Constant) and isinstance(first.value, str) \
                    and (first.value == "hangma_bot"
                         or first.value.startswith("hangma_bot.")):
                found.setdefault(first.value, set()).add(
                    "{0}:{1}".format(filename, caller))
    return {name: tuple(sorted(sites)) for name, sites in found.items()}


def unregistered_dynamic_loads(*, tools_dir: Optional[Path] = None,
                               files: Optional[Iterable[str]] = None,
                               ) -> List[Dict[str, Any]]:
    """未登记的动态装载（登记不到即失败关闭的判据；空列表=无缺口）。"""

    scanned = scan_dynamic_sibling_loads(tools_dir=tools_dir, files=files)
    return [{"module": name, "sites": list(sites)}
            for name, sites in sorted(scanned.items())
            if name not in SIBLING_MODULES]


def entry_call_graph(*, reader: Callable[[Path], bytes],
                     tools_dir: Optional[Path] = None,
                     src_root: Optional[Path] = None,
                     entries: Optional[Sequence[str]] = None,
                     ) -> Dict[str, Any]:
    """入口调用图：入口工具文件 → 第一方模块与同目录工具模块的传递闭包。

    节点键形如 `tool:sitin_stage`（同目录工具模块）与
    `module:hangma_bot.offline.evaluate`（第一方模块）；每个节点带仓库相对路径与
    内容摘要（经调用方注入的 reader，与清单其余文件面同一读取入口）。

    返回：
      - `nodes`：{节点键: {"kind", "name", "path", "sha256"}}；
      - `edges`：{节点键: [被引用节点键, ...]}（排序、去重；用于「入口调用图 →
        登记项」对照表）；
      - `missing`：必须解析却解析不到的第一方模块（**非空即缺口**）；
      - `foreign`：非第一方 import（标准库/第三方），不进清单（报告里逐项给出理由）。
    """

    root = Path(tools_dir or TOOLS_DIR)
    source_root = Path(src_root or SRC_ROOT)
    entry_names = tuple(entries or ENTRY_FILES)
    nodes: Dict[str, Dict[str, Any]] = {}
    edges: Dict[str, List[str]] = {}
    node_bytes: Dict[str, bytes] = {}
    files_by_key: Dict[str, Path] = {}
    missing: List[str] = []
    foreign: set = set()
    queue: List[Tuple[str, Path, str]] = []

    def _key_for_tool(name: str) -> str:
        return "tool:" + name

    def _key_for_module(dotted: str) -> str:
        return "module:" + dotted

    for filename in entry_names:
        path = root / filename
        if not path.is_file():
            raise ManifestCoverageGap(
                "登记入口文件不存在：{0}（清单覆盖无从谈起，拒绝出清单）".format(
                    _relpath(path)))
        dotted = Path(filename).stem
        key = _key_for_tool(dotted)
        nodes[key] = {"kind": "tool", "name": dotted,
                      "path": _relpath(path),
                      "sha256": _digest_bytes(reader(path))}
        edges.setdefault(key, [])
        queue.append((key, path, dotted))
        files_by_key[key] = path

    seen: set = set()
    while queue:
        key, path, dotted = queue.pop(0)
        if key in seen:
            continue
        seen.add(key)
        targets: set = set()
        data = node_bytes.get(key)
        if data is None:
            data = reader(path)
            node_bytes[key] = data
        for ref in module_imports_of(data, dotted, path):
            tool_path = resolve_tool(ref.name, tools_dir=root) if "." not in ref.name \
                else None
            if tool_path is not None:
                target_key = _key_for_tool(ref.name)
                if target_key not in nodes:
                    payload = reader(tool_path)
                    node_bytes[target_key] = payload
                    nodes[target_key] = {
                        "kind": "tool", "name": ref.name,
                        "path": _relpath(tool_path),
                        "sha256": _digest_bytes(payload)}
                    edges.setdefault(target_key, [])
                    queue.append((target_key, tool_path, ref.name))
                targets.add(target_key)
                continue
            if ref.name == "hangma_bot" or ref.name.startswith("hangma_bot."):
                module_path = resolve_module(ref.name, src_root=source_root)
                if module_path is None:
                    if ref.required and ref.name not in missing:
                        missing.append(ref.name)
                    continue
                target_key = _key_for_module(ref.name)
                if target_key not in nodes:
                    payload = reader(module_path)
                    node_bytes[target_key] = payload
                    nodes[target_key] = {
                        "kind": "module", "name": ref.name,
                        "path": _relpath(module_path),
                        "sha256": _digest_bytes(payload)}
                    edges.setdefault(target_key, [])
                    queue.append((target_key, module_path, ref.name))
                targets.add(target_key)
                continue
            foreign.add(ref.name)
        edges[key] = sorted(targets)

    return {"entries": sorted(_key_for_tool(Path(name).stem)
                              for name in entry_names),
            "nodes": {key: nodes[key] for key in sorted(nodes)},
            "edges": {key: edges.get(key, []) for key in sorted(edges)},
            "missing": sorted(missing), "foreign": sorted(foreign)}


def coverage_gaps(*, reader: Callable[[Path], bytes],
                  tools_dir: Optional[Path] = None,
                  src_root: Optional[Path] = None,
                  graph: Optional[Mapping[str, Any]] = None,
                  covered: Optional[Iterable[str]] = None,
                  ) -> List[Dict[str, Any]]:
    """清单覆盖缺口（空列表=可出清单）：未登记的动态装载 + 解析不到的第一方模块。

    两类缺口都**失败关闭**：未登记的动态装载意味着某个被装载的实现不进清单；
    解析不到的第一方模块意味着闭包断了（真实依赖被静默丢掉）。

    `graph` 可传入已算好的入口调用图（清单侧先算图再判缺口，避免重复计算）。
    """

    root = Path(tools_dir or TOOLS_DIR)
    gaps: List[Dict[str, Any]] = []
    for item in unregistered_dynamic_loads(tools_dir=root, files=ENTRY_FILES):
        gaps.append({"kind": "unregistered_dynamic_load",
                     "module": item["module"], "sites": item["sites"]})
    graph = graph if graph is not None else entry_call_graph(
        reader=reader, tools_dir=root, src_root=src_root)
    for name in graph.get("missing") or ():
        gaps.append({"kind": "unresolved_first_party_module", "module": name,
                     "sites": []})
    if covered is not None:
        known = {str(item) for item in covered}
        for name, sites in sorted(scan_literal_module_loads(
                tools_dir=root, files=ENTRY_FILES).items()):
            if name not in known:
                gaps.append({"kind": "uncovered_module_load", "module": name,
                             "sites": list(sites)})
    return gaps
