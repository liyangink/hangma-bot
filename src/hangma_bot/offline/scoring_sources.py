"""评分实现的可核验来源清单：**依赖闭包 + 字节指纹**。

## 为什么需要它（REVIEW-8 S8-1）

初版候选身份只对**入口文件**取指纹。但候选之间会互相 import——
`meld_waiting_conditional` 用 `meld_opportunity_cost.natural_draw_value`，
公共评分器还要经过 `evaluation_v2`。只改被依赖的那个文件、入口文件不变时，
`bound_identity` / `candidate_identity` / `scoring_source` **三者全都不变**，
于是"在某份代码上过了门禁"这条结论可以被另一份代码沿用。实测：把
`natural_draw_value` 的返回值整体加 42，同一输入的首选从 `peng:1w` 变成 `pass`，
而三个身份一个都没变。

## 做什么

从**显式声明的根**出发，按**静态 import 图**求**一级方（`hangma_bot.*`）传递闭包**，
对闭包里的每个文件取 sha256。同一份清单同时用于四处，避免"四份清单各写一遍"：

1. 准入身份（门禁 `bound_identity`）；
2. 调度身份（调度器 `_candidate_identity`，与门禁**共用同一个函数**）；
3. 实验清单的 `scoring_source`；
4. 未提交代码时的 `code_snapshot/` 归档。

## 为什么静态解析，而不是 import 之后读 `sys.modules`

后者取决于进程里**还**导入过什么：同一份候选从门禁入口与从评估入口跑会得到不同清单，
身份随之漂移。静态解析同输入同输出，且不执行任何候选代码。

## 边界

- 只跟随 `hangma_bot.*`；标准库与三方库不进清单（它们由环境记录负责，不是本仓可控源码）。
- 动态 import（`importlib`）**不**被跟随。本仓的候选装载是**静态字面量注册表**
  （`policy/heuristics/__init__.py` 明确禁止动态导入），因此静态解析是完备的；
  一旦将来引入动态导入，本清单会**漏**依赖，必须同步改这里。
- 闭包包含规则包时（例如 `chain_path_value` 依赖链转移函数），**规则源码变化**会让
  该候选的准入记录失效——这是有意的：规则转移函数直接决定评分项取值。
"""
from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

#: 仓库根（本文件位于 <root>/src/hangma_bot/offline/scoring_sources.py）。
REPO_ROOT = Path(__file__).resolve().parents[3]
SRC_ROOT = REPO_ROOT / "src"

#: 与候选**无关**、但参与每次评分的公共实现。候选身份与评分源码清单都以它们为根。
COMMON_SCORING_ROOTS: Tuple[str, ...] = (
    "hangma_bot.policy.evaluation_v1",
    "hangma_bot.policy.evaluation_v2",
    "hangma_bot.policy.heuristic_v1",
    "hangma_bot.policy.heuristic_v2",
    "hangma_bot.policy.weights_v1",
    "hangma_bot.policy.heuristic_adapter",
)

#: 仅在**归档与实验清单**里追加的根（装修饰器与旧版评分）。
#: 它们不进候选身份：候选身份只应随"决定这次评分的那份代码"变化，
#: 把用不到的实现也算进去会让记录无谓失效。
ARCHIVE_ONLY_ROOTS: Tuple[str, ...] = (
    "hangma_bot.policy.white_discard_guard",
    "hangma_bot.policy.legacy_pass",
    "hangma_bot.policy.weights",
    "hangma_bot.policy.weighted_heuristic",
    "hangma_bot.policy.safe_fallback",
)


def resolve_module(dotted: str) -> Optional[Path]:
    """把点分模块名解析成**本仓源码文件**；不在本仓时返回 None（不猜）。"""

    relative = Path(*dotted.split("."))
    for candidate in (SRC_ROOT / relative.with_suffix(".py"),
                      SRC_ROOT / relative / "__init__.py"):
        if candidate.is_file():
            return candidate
    return None


def _package_of(path: Path) -> List[str]:
    """文件所属的包路径（用于解析相对 import）。"""

    return list(path.relative_to(SRC_ROOT).parts[:-1])


def module_imports(path: Path) -> Tuple[str, ...]:
    """一个文件静态 import 的点分模块名（含"从包里取子模块"的形态）。"""

    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return ()
    package = _package_of(path)
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                found.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                # level=1 指当前包；level=n 向上 n-1 层。
                base = package[:len(package) - (node.level - 1)] if node.level > 1 else package
                module = ".".join(base + ([node.module] if node.module else []))
            else:
                module = node.module or ""
            if not module:
                continue
            found.add(module)
            # `from pkg import sub` 里 sub 可能是子模块——两个都登记，
            # 解析不到的（函数/常量名）会被 resolve_module 丢掉。
            for alias in node.names:
                found.add(module + "." + alias.name)
    return tuple(sorted(found))


def dependency_closure(roots: Sequence[str]) -> Tuple[str, ...]:
    """从根出发的一级方 import 传递闭包（稳定排序，同输入同输出）。"""

    seen: set = set()
    stack: List[str] = list(roots)
    while stack:
        name = stack.pop()
        if name in seen:
            continue
        path = resolve_module(name)
        if path is None:
            continue
        seen.add(name)
        for dependency in module_imports(path):
            if dependency.startswith("hangma_bot") and dependency not in seen:
                stack.append(dependency)
    return tuple(sorted(seen))


def candidate_module_name(candidate_name: str) -> str:
    """已注册候选的点分模块名；命名约定与注册表一致。"""

    return "hangma_bot.policy.heuristics." + candidate_name


def identity_roots(candidate_name: str) -> Tuple[str, ...]:
    """构成**候选身份**的根：该候选模块 + 与候选无关的公共评分实现。"""

    return (candidate_module_name(candidate_name),) + COMMON_SCORING_ROOTS


def digest_of_file(path: Path) -> Dict[str, Any]:
    """一个文件的字节指纹。"""

    data = path.read_bytes()
    return {"sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}


def source_manifest(roots: Sequence[str]) -> Dict[str, Dict[str, Any]]:
    """根闭包 → {相对路径: 字节指纹}；路径相对仓库根，稳定排序。"""

    manifest: Dict[str, Dict[str, Any]] = {}
    for name in dependency_closure(roots):
        path = resolve_module(name)
        if path is None:
            continue
        manifest[str(path.relative_to(REPO_ROOT))] = digest_of_file(path)
    return dict(sorted(manifest.items()))


def digest_of_manifest(manifest: Mapping[str, Mapping[str, Any]]) -> str:
    """清单 → 单个摘要（16 位十六进制）。

    **必须由"路径 + 内容哈希"共同决定**：只对内容求和会让"两份文件互换内容"
    得到同一个摘要，而那是两份不同的实现。
    """

    payload = "\n".join(
        "{0}:{1}".format(path, entry.get("sha256")) for path, entry in sorted(manifest.items()))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def candidate_identity_digest(candidate_name: str) -> str:
    """候选身份里的源码摘要——**覆盖完整执行依赖**，不是入口文件。"""

    return digest_of_manifest(source_manifest(identity_roots(candidate_name)))


def scoring_source_snapshot(candidate_names: Iterable[str]) -> Dict[str, Dict[str, Any]]:
    """实验清单的 scoring_source：公共评分实现 + 本次用到的候选，取依赖闭包。"""

    roots: List[str] = list(COMMON_SCORING_ROOTS) + list(ARCHIVE_ONLY_ROOTS)
    for name in sorted(set(candidate_names)):
        roots.append(candidate_module_name(name))
    return source_manifest(roots)


def write_code_snapshot(out_dir: Path, manifest: Mapping[str, Mapping[str, Any]]) -> Optional[str]:
    """把清单里的实际源码写入 out_dir/code_snapshot/；返回子目录名。

    "可验证指纹"用于**核对**，"实际代码快照"用于**在没有该提交的环境里重建**，
    两者用途不同。代价有界：清单是依赖闭包（十几到几十个小文件），不是整仓快照。
    """

    if not manifest:
        return None
    target = out_dir / "code_snapshot"
    for relative_path in sorted(manifest):
        source = REPO_ROOT / relative_path
        if not source.is_file():
            continue
        destination = target / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(source.read_bytes())
    return target.name


def manifest_to_json(manifest: Mapping[str, Mapping[str, Any]]) -> str:
    """清单的稳定 JSON 文本（用于落盘与比对）。"""

    return json.dumps(dict(manifest), ensure_ascii=False, sort_keys=True, indent=2)


__all__ = [
    "ARCHIVE_ONLY_ROOTS",
    "COMMON_SCORING_ROOTS",
    "REPO_ROOT",
    "SRC_ROOT",
    "candidate_identity_digest",
    "candidate_module_name",
    "dependency_closure",
    "digest_of_file",
    "digest_of_manifest",
    "identity_roots",
    "manifest_to_json",
    "module_imports",
    "resolve_module",
    "scoring_source_snapshot",
    "source_manifest",
    "write_code_snapshot",
]
