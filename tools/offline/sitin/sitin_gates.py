"""坐隐 2.3：候选三道门禁（G-1 时间与纯度 / G-2 退化检测 / G-3 评估记账）。

**门禁只做准入，不做排序**（README §6.1、DESIGN §4.3）。G-2 的改选率与矩阵
**绝不允许**当适应度或淘汰依据——本项目已两次证伪决策级代理信号。

三道的判据（README §6.1）：

- **G-1 时间与纯度**：候选确定性、无 IO、只读既有事实、毫秒级。
- **G-2 退化检测**：报告改选率、改选矩阵、是否"永远改选/永不改选"；异常样本人工复核。
- **G-3 评估记账**：候选须给出**触发条件、改变的动作、预期方向与反例**；
  缺少触发条件说明的候选**不进队列**（不以"自报预期增分数"作准入）。

**设计纪律**：门禁必须能**失败**。因此本模块配负例测试（`test_sitin_gates.py`），
用故意写坏的候选（抛异常、返回 NaN、无界、不确定、缺触发条件）验证每道门都会拦。
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

import argparse
import asyncio
import hashlib
import importlib.util
import json
import os
import statistics
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

REPO = _PROJECT_ROOT
sys.path.insert(0, str(_project_file(_PROJECT_ROOT, REPO / "src")))
_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))

from hangma_bot.application.deadline import ManualClock  # noqa: E402
from hangma_bot.bootstrap import build_decision_codec  # noqa: E402
from hangma_bot.hangma.engine import HangmaRules  # noqa: E402
from hangma_bot.hangma.interface import RuleCompleteness  # noqa: E402
from hangma_bot.kernel.config import RuleConfig  # noqa: E402
from hangma_bot.offline.evaluate import translate_budget  # noqa: E402
from hangma_bot.offline.scoring_sources import candidate_identity_digest  # noqa: E402
import sitin_execution_profile as execution_profiles  # noqa: E402
# 候选注册表**惰性导入**（REVIEW-9「装载有界」）：见 heuristics_registry()。
_HEURISTICS: Optional[Any] = None


def heuristics_registry():
    """惰性导入候选注册表。

    **为什么必须惰性**：`policy.heuristics.__init__` 会 import **全部**已注册候选模块，
    于是一个在**模块体里**挂住的候选，会让每一个 import 本工具的进程一起挂住——
    包括只想"先核验身份、再决定要不要碰候选"的调度器父进程。
    把导入推迟到真正需要它的函数里之后，父进程可以先跑受监管的
    `supervised_prepare`（子进程里完成导入与构造），失败就拒绝，
    **根本不会在自己进程里执行候选代码**。
    """

    global _HEURISTICS
    if _HEURISTICS is None:
        from hangma_bot.policy import heuristics as module
        _HEURISTICS = module
    return _HEURISTICS


class _LazyRegistry:
    """惰性注册表**代理**：第一次属性访问才真正导入。

    保留 `heuristics.xxx` 的既有调用写法，同时把导入推迟到调用点——
    "import 本工具"因此不再等于"import 全部候选模块"。
    """

    def __getattr__(self, name: str) -> Any:
        return getattr(heuristics_registry(), name)


#: 与既有的 `from hangma_bot.policy import heuristics` 同名的**惰性代理**。
heuristics = _LazyRegistry()

from hangma_bot.policy.heuristic_v2 import ComparableHeuristicPolicyV2  # noqa: E402
from hangma_bot.policy.interface import DecisionRequest  # noqa: E402


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, _project_file(_PROJECT_ROOT, _HERE / (name + ".py")))
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


recompute = _load("sitin_m4_recompute")
process_guard = _load("sitin_process")

# G-1 静态禁止痕迹：候选模块必须是纯计算。
G1_FORBIDDEN_TOKENS: Tuple[str, ...] = (
    "import socket", "import urllib", "import httpx", "import requests",
    "import aiohttp", "import subprocess", "import shutil", "import tempfile",
    "import os", "import random", "import time", "open(", "os.remove",
    "Path(", ".write_text", ".read_text",
)

# G-1 时间上界（**每个被触发窗口**，毫秒）。
# S7-1：分位数会掩盖单次超时，因此除了 p99 还必须有**硬上限**。
# 1 秒窗口下留足余量：50ms 已是极宽松的门槛，目的只是拦住"循环/搜索/阻塞"。
G1_MAX_SINGLE_WINDOW_MS = 50.0
G1_MAX_OVERHEAD_MS = 20.0

# G-2 判据（2026-09-15 修正两处**假失败**；价值族②暴露，记入 route 证据）：
#
# D1 「适用面」被硬编码成响应窗口。初版把"响应窗口"当成唯一适用面，
#    于是对声明 scope=全部动作类别的价值族候选，任何发生在弃牌/杠窗口的改选
#    都被报成"范围外溢"（假失败）。适用面必须由**候选声明的 scope** 决定。
# D2 零改选只有一种解释。初版把"零改选"一律读成"等价基线"。实测语料
#    `auto-match-2026-09-06` 的 chain_count 在 3249/3249 个窗口里都是 0，
#    链路径候选的核心触发面**根本没有样例**；此时"零改选"是**证据不足**，
#    不是退化。判据改为：作用面内零**触发** ⇒ INSUFFICIENT；
#    触发到了却零**改选** ⇒ FAIL（这才是真正的等价基线）。
G2_MIN_APPLICABLE_WINDOWS = 20   # 适用窗口太少时不给结论
# **触发面**也要有下限（2026-09-15 独立复核撞出）：初版把分母换成 `fired_n` 后，
# `fired_n=1` 且改选 1 次 ⇒ 改选率 1.0 ⇒ 被判"全部改选"；`fired_n=4` 改选 4 次同样
# 被判退化。1~4 个窗口就下硬结论，与"适用窗口 <20 归 INSUFFICIENT"自相矛盾。
G2_MIN_FIRED_WINDOWS = 8
# 兼容旧名（既有证据文件与报告引用过它）。
G2_MIN_RESPONSE_WINDOWS = G2_MIN_APPLICABLE_WINDOWS
# **行为诊断**阈值（2026-09-15 第二次修订，REVIEW-9 / PLAN-REVISION §3.0）：
# 两个极值**不再产生 FAIL**，只做行为诊断与资源筛选（见 g2_triage）：
#   - 1.0：针对性修正型候选会在**每个**实际触发点都改选，那不是退化；
#   - 0.0：只说明"本面板与配置下未改变选择"，不构成"机制无效"的结论，
#          按资源筛选**暂缓升级**。
# 这是对上面 D2 后一句的部分撤回，**不是**重新引入 R7-8：
# R7-8 的病是"没测到 ⇒ 报通过"；这里极值是**明确的观测**，只是它不是"退化"。
# 覆盖不足仍走 INSUFFICIENT，执行故障与范围外溢仍走 FAIL。
G2_ALWAYS_CHANGE_RATE = 1.0       # 行为诊断：全部改选
G2_NEVER_CHANGE_RATE = 0.0        # 行为诊断：触发面上完全不改选


def candidate_identity(candidate_name: str, weights: Mapping[str, float]) -> str:
    """候选的**绑定身份**：模块 + 有效参数 + **执行依赖指纹**。

    R7-1 要求"门禁通过记录"与"随后被调度执行的候选"是**同一份配置**；
    参数或代码一改，原记录即失效。因此身份必须包含三样：
      ① 模块名；② **拆分后的有效参数**（`adj.*` 去前缀后的实际值）；
      ③ **源码指纹**（在门禁侧计算——门禁持有 IO 权限，policy 包不持有）。

    **REVIEW-8 S8-1**：③ 初版只对**入口文件**取指纹。候选之间会互相 import
    （`meld_waiting_conditional` 用 `meld_opportunity_cost.natural_draw_value`），
    公共评分器还要经过 `evaluation_v2`——只改被依赖的文件、入口不变时，
    `bound_identity` / `candidate_identity` / `scoring_source` 三者**全都不变**。
    现在指纹取自 **import 依赖闭包**（见 `offline/scoring_sources.py`），
    闭包内任一文件变化都会让身份变化。
    """

    params, base = heuristics.split_declaration_params(dict(weights))
    sorted_params = ",".join("{0}={1}".format(k, params[k]) for k in sorted(params))
    digest = candidate_identity_digest(candidate_name)
    base_key = ",".join("{0}={1}".format(k, base[k]) for k in sorted(base))
    return "{0}|adj({1})|base({2})|src{3}".format(
        candidate_name, sorted_params or "default", base_key or "default", digest)


def _real_budget(now: float, enhancement: float = 1.0):
    """按**真实**单调时钟造一份 1 秒增强预算。

    S7-1：初版让策略跑在 `lambda: 0.0` 的假时钟上，策略内部的截止检查永不推进，
    于是"运行中"超时根本无法被测出。G-1 要测的恰恰是**真实 1 秒窗口里会不会超时**，
    因此这里用真时钟 + 真实时限重建预算。
    """

    from hangma_bot.policy.interface import DecisionBudget

    return DecisionBudget(now + enhancement, now + enhancement + 1.0,
                          now + enhancement + 2.0)


def gate_g1(candidate_name: str, weights: Mapping[str, float],
            requests: Sequence[Any], budgets: Sequence[Any]) -> Dict[str, Any]:
    """G-1：静态纯度 + 确定性 + 有界 + 毫秒级增量。"""

    problems: List[str] = []
    module = heuristics.candidate_module(candidate_name)
    source = Path(module.__file__).read_text(encoding="utf-8")
    hits = [token for token in G1_FORBIDDEN_TOKENS if token in source]
    if hits:
        problems.append("候选模块含禁止痕迹：{0}".format(hits))

    policy = heuristics.build_candidate(candidate_name, weights=weights,
                                        monotonic=lambda: 0.0)
    baseline = ComparableHeuristicPolicyV2(monotonic=lambda: 0.0)

    # 确定性：同输入两次逐字节相同
    mismatches = 0
    for request, budget in zip(requests, budgets):
        first = asyncio.run(policy.choose(request, budget))
        second = asyncio.run(policy.choose(request, budget))
        if first != second:
            mismatches += 1
    if mismatches:
        problems.append("非确定输出：{0} 个窗口两次结果不同".format(mismatches))

    # 有界：候选声明的 bound 必须覆盖实际分项
    bound = policy.adjustment.spec.bound
    over = 0
    for request, budget in zip(requests, budgets):
        plan = asyncio.run(policy.choose(request, budget))
        for candidate in plan.candidates:
            for part in candidate.score_parts:
                if part.name == policy.adjustment.spec.name and abs(part.value) > bound + 1e-9:
                    over += 1
    if over:
        problems.append("分项越界：{0} 处超过声明 bound={1}".format(over, bound))
    if policy.adjustment.clamped_count:
        problems.append("运行期发生钳制 {0} 次（候选幅度与声明不符）".format(
            policy.adjustment.clamped_count))

    # 毫秒级（REVIEW-7 S7-1 重写）：
    # 初版用"40 个窗口的增量 p99"，而其中往往只有 2 个窗口真正触发候选——
    # 于是 p99 取排序后下标 38，**把唯一最慢的窗口排除在外**，
    # 实测有候选单次响应约 1934ms 仍报 PASS。修法三条：
    #   ① 只在**真正触发**的窗口上计时（按候选 scope 过滤）；
    #   ② 对**每个被触发窗口**设硬上限（不是分位数）；
    #   ③ 用**真实单调时钟**驱动策略的截止检查——初版注入 lambda:0.0，
    #      策略内部检查永不推进，"运行中"超时根本测不出来。
    triggered: List[float] = []
    for request, budget in zip(requests, budgets):
        keys = [c.action_key for c in request.rules.legal_candidates]
        if not any(policy.adjustment.applies_to(key) for key in keys):
            continue
        real_clock = time.monotonic
        timed_policy = heuristics.build_candidate(
            candidate_name, weights=weights, monotonic=real_clock)
        timed_budget = _real_budget(real_clock())
        start = time.perf_counter()
        asyncio.run(timed_policy.choose(request, timed_budget))
        triggered.append((time.perf_counter() - start) * 1000.0)
    overheads = triggered
    p50 = statistics.median(overheads) if overheads else 0.0
    p99 = (sorted(overheads)[min(int(0.99 * (len(overheads) - 1)), len(overheads) - 1)]
           if overheads else 0.0)
    slowest = max(overheads) if overheads else 0.0
    if not overheads:
        problems.append("没有任何**触发**窗口被计时：时间门禁无法判定")
    if slowest > G1_MAX_SINGLE_WINDOW_MS:
        # 硬上限：一次超时就是失败，不允许用分位数掩盖。
        problems.append("单次触发窗口耗时 {0:.3f}ms 超过硬上限 {1}ms".format(
            slowest, G1_MAX_SINGLE_WINDOW_MS))
    if p99 > G1_MAX_OVERHEAD_MS:
        problems.append("触发窗口增量 p99={0:.3f}ms 超过 {1}ms".format(p99, G1_MAX_OVERHEAD_MS))

    # 零窗口等于"没测过任何东西"：报 PASS 会把未测量伪装成通过（R7-8）。
    # 显式区分"测出问题"(FAIL) 与"没测"(INSUFFICIENT)；前者优先。
    measured = bool(requests)
    if not measured:
        problems.append("没有任何窗口被测量：证据不足，不等于通过")
    return {"gate": "G-1 时间与纯度",
            "status": ("FAIL" if problems and measured
                       else ("INSUFFICIENT" if not measured else "PASS")),
            "problems": problems,
            "detail": {"forbidden_hits": hits, "nondeterministic_windows": mismatches,
                       "bound": bound, "over_bound_parts": over,
                       "overhead_ms_p50": round(p50, 4), "overhead_ms_p99": round(p99, 4),
                       "windows_measured": len(requests),
                       "triggered_windows_timed": len(overheads),
                       "slowest_triggered_ms": round(slowest, 4)}}


def g2_verdict(applicable_n: int, applicable_changed: int, out_of_scope_changed: int,
               total_windows: Optional[int] = None, *,
               fired_n: Optional[int] = None,
               candidate_failures: Sequence[Mapping[str, Any]] = (),
               baseline_failures: Sequence[Mapping[str, Any]] = (),
               candidate_failure_total: Optional[int] = None,
               baseline_failure_total: Optional[int] = None
               ) -> Tuple[str, List[str], List[str], Optional[float]]:
    """G-2 的判定（纯函数，便于精确测试门禁**能否失败**）。

    参数（2026-09-15 按 D1/D2 更正措辞；这些量都按**候选声明的 scope** 统计）：
      applicable_n           至少存在一个**声明 scope 内**合法候选的动作窗口数；
      applicable_changed     其中首选动作发生变化的窗口数；
      out_of_scope_changed   **声明 scope 之外**的窗口中首选发生变化的窗口数；
      total_windows          本次语料解出的窗口总数；0 表示输入为空；
      fired_n                适用窗口中**候选真的给出过非零调整**的窗口数。
                             缺省 None 表示调用方未测量，退回旧判据（分母取适用面）。
      candidate_failures     **候选执行抛异常**的窗口**样本**（窗口标识 + 异常文本），
                             最多 `_MAX_FAILURE_DETAIL` 条；
      baseline_failures      同上，**基线执行抛异常**的窗口样本；
      candidate_failure_total 候选执行失败的**真实窗口数**（不受明细上限影响）。
                              缺省 None 表示调用方只给了样本，按 `len(candidate_failures)` 计。
      baseline_failure_total  基线执行失败的真实窗口数；口径同上。

    **上限只作用于明细，不作用于计数**（轮次 3 更正）：初版把"计数"写成 `len(明细)`，
    于是一份有 91 个失败窗口的语料在报告里显示成 20——**叙述与证据对不上**。
    现在计数由调用方单独传入（`*_failure_total`），这样既保住有界内存，
    又让"总窗口数 = 排除 + 适用 + 失败"这条账能对上。

    返回 (status, problems, notes, rate)。状态**三态**：
      PASS           有足够证据且无退化；
      FAIL           观测到退化、范围外溢，**或候选执行出错**；
      **INSUFFICIENT** 证据不足——**不等于通过**。

    **REVIEW-8 R8-1**：初版把"解码失败""规则事实不可用""策略执行异常"塞进同一个
    `except Exception`，只把 `excluded` 加一。于是**已经执行出错**的候选照样
    三门 PASS、`admitted=true`——那不是"尚未测到错误"，而是把错误算成了排除。
    现在三者分开计数，且**执行失败优先于一切样本量判断**（先判失败，再判证据够不够）。

    **REVIEW-7 R7-8 的教训**：初版在样本不足时返回 problems=[]，上层按
    "无 problems ⇒ PASS" 聚合，于是**空语料也拿到 all_pass=true**——与"不足时不给结论"
    的承诺直接冲突。这正是 P4 那类"通过条件等于没检查"的病，因此状态必须显式三态。

    **顺序也修了**：范围外溢的检查**先于**样本量判断——初版提前返回会漏掉
    已经观测到的外溢（1 个响应窗口 + 100 个范围外改选也会被放过）。

    **D1/D2（2026-09-15，由价值族②暴露）**：
      D1 适用面必须由**候选声明的 scope** 决定，不能硬编码成响应窗口；
      D2 零改选有两种成因——"语料没有触发面"（证据不足）与
         "触发到了却不改选"（真退化）。前者归 INSUFFICIENT，只有后者才是 FAIL。
    判据的**分母**优先取 fired_n（真正触发过的窗口）：一个只在 4 个窗口触发过的
    候选，用 3249 当分母算"改选率"没有意义；用 4 当分母才回答得了
    "触发到了之后它到底改没改"。
    """

    problems: List[str] = []
    notes: List[str] = []
    # **计数取真实值**（轮次 3 更正）：样本可能被上限截断，判定与叙述都必须用真值。
    candidate_total = (len(candidate_failures) if candidate_failure_total is None
                       else int(candidate_failure_total))
    baseline_total = (len(baseline_failures) if baseline_failure_total is None
                      else int(baseline_failure_total))
    # **执行失败最先判**（R8-1）：它不是"证据不足"，是"已经出错"。
    if candidate_total or candidate_failures:
        problems.append(
            "候选执行失败：{0} 个窗口抛异常（明细保留前 {1} 条）；示例 {2}".format(
                candidate_total, len(candidate_failures),
                "; ".join("{0} -> {1}".format(item.get("window"), item.get("error"))
                          for item in list(candidate_failures)[:3])))
        return "FAIL", problems, notes, None
    if baseline_total or baseline_failures:
        notes.append(
            "基线（冻结 V2）在 {0} 个窗口抛异常（明细保留前 {1} 条），本次无法完成比较；"
            "示例 {2}。**这不是证据不足之外的通过条件**".format(
                baseline_total, len(baseline_failures),
                "; ".join("{0} -> {1}".format(item.get("window"), item.get("error"))
                          for item in list(baseline_failures)[:3])))
        return "INSUFFICIENT", problems, notes, None
    if total_windows is not None and total_windows == 0:
        return "INSUFFICIENT", ["输入为空：没有任何窗口可判定"], notes, None
    # 外溢先判：它与样本量无关，且一旦观测到就是确定的坏事。
    if out_of_scope_changed:
        problems.append("范围外溢：{0} 个**声明 scope 之外**的窗口发生改选".format(
            out_of_scope_changed))
        rate = round(applicable_changed / applicable_n, 4) if applicable_n else None
        return "FAIL", problems, notes, rate
    if applicable_n < G2_MIN_APPLICABLE_WINDOWS:
        notes.append("适用窗口仅 {0} 个，不足 {1}：**证据不足，不等于通过**".format(
            applicable_n, G2_MIN_APPLICABLE_WINDOWS))
        return "INSUFFICIENT", problems, notes, None
    if fired_n == 0:
        # D2：作用面里有窗口，但候选一次非零调整都没给。这在观测上分不清两件事——
        # 语料没有触发面（证据不足）与候选恒为 0（真缺陷）。两者**都不得准入**，
        # 但前者不能写成"等价基线"：那是把证据不足伪装成结论。
        notes.append(
            "适用窗口 {0} 个，但候选**一次非零调整都没有给出**：无法区分"
            "『本语料没有触发面』与『候选恒为 0』。两者都不得准入——"
            "须补触发样例（按规则可枚举生成）或修候选，**本条不是通过**".format(
                applicable_n))
        return "INSUFFICIENT", problems, notes, None
    if fired_n is not None and 0 < fired_n < G2_MIN_FIRED_WINDOWS:
        # 触发面太小 ⇒ 不给结论。**不等于通过**（上层 admitted 仍要求无 INSUFFICIENT）。
        notes.append(
            "候选只在 {0} 个窗口触发（不足 {1}）：触发面本身太小，**证据不足，不等于通过**".format(
                fired_n, G2_MIN_FIRED_WINDOWS))
        rate = round(applicable_changed / fired_n, 4) if fired_n else None
        return "INSUFFICIENT", problems, notes, rate
    basis = fired_n if fired_n is not None else applicable_n
    rate = round(applicable_changed / basis, 4) if basis else None
    if fired_n is not None and fired_n < applicable_n:
        notes.append("候选只在 {0}/{1} 个适用窗口触发；判据分母取**触发面**".format(
            fired_n, applicable_n))
    # **改选率极值不再判 FAIL**（REVIEW-9 / PLAN-REVISION §3.0，2026-09-15 修订）：
    #   100%：一个专门修正某类选择的候选，可以在**每个**实际触发点都改选；
    #    0%：只说明**当前面板与配置未改变选择**，据此否定整个机制是错的。
#
    # 两者都改记**行为诊断**，由 g2_triage 给出"要不要花预算升级"的资源筛选结论。
    #
    # **这是对上一条 D2 判据的部分撤回，不是重新引入 R7-8**：
    #   R7-8 的病是"没测到 ⇒ 报通过"；这里"测到了且极值"仍然是一条**明确的观测**，
    #   只是它不构成"退化"的结论。覆盖不足仍走 INSUFFICIENT，执行故障仍走 FAIL。
    if rate is not None and rate >= G2_ALWAYS_CHANGE_RATE:
        notes.append(
            "行为诊断：触发窗口改选率 1.0（**每个触发点都改选**）。"
            "这本身不证明退化——针对性修正型候选本可以如此；请人工看改选矩阵与动作族分布")
    elif rate is not None and rate <= G2_NEVER_CHANGE_RATE:
        notes.append(
            "行为诊断：在 {0} 个**实际触发**窗口上改选率为 0.0，"
            "即**本面板与配置下未改变任何选择**。这不等于机制无效，"
            "按资源筛选**暂缓升级**（见 triage），不得据此否定整个机制".format(basis))
    return ("FAIL" if problems else "PASS"), problems, notes, rate


#: 资源筛选结论（REVIEW-9 / PLAN-REVISION §3.0）：只回答"要不要花预算升级"。
TRIAGE_UPGRADE = "upgrade"
TRIAGE_BLOCKED = "blocked"
TRIAGE_HOLD_COVERAGE = "hold_coverage"
TRIAGE_HOLD_NO_CHANGE = "hold_no_change"
TRIAGE_WATCH_ALL_CHANGE = "watch_all_change"


def g2_triage(status: str, *, applicable_n: int, fired_n: Optional[int],
              basis: int, rate: Optional[float]) -> Dict[str, Any]:
    """把门禁结论翻译成**预算决策**用的资源筛选状态。

    **它只回答"要不要把预算花在这个候选的下一级评估上"，不回答"机制好不好"。**
    四类分开（REVIEW-9 要求）：执行故障与范围外溢是**确定的问题**（`blocked`）；
    覆盖不足是**证据问题**（`hold_coverage`）；行为极值是**诊断**
    （`hold_no_change` / `watch_all_change`），据此否定整个机制是错的。
    """

    if status == "FAIL":
        return {"decision": TRIAGE_BLOCKED,
                "reason": "执行故障或声明范围外溢：不得升级",
                "is_a_verdict_on_the_mechanism": False}
    if status == "INSUFFICIENT":
        return {"decision": TRIAGE_HOLD_COVERAGE,
                "reason": "证据不足（适用窗口 {0}、触发窗口 {1}）：先补覆盖，不是候选缺陷".format(
                    applicable_n, fired_n),
                "is_a_verdict_on_the_mechanism": False}
    if rate is not None and rate <= G2_NEVER_CHANGE_RATE:
        return {"decision": TRIAGE_HOLD_NO_CHANGE,
                "reason": ("在 {0} 个实际触发窗口上未改变任何选择："
                           "**本面板与配置下**无行为差异，暂缓升级；"
                           "这不等于机制无效，换面板或换配置可能不同").format(basis),
                "is_a_verdict_on_the_mechanism": False}
    if rate is not None and rate >= G2_ALWAYS_CHANGE_RATE:
        return {"decision": TRIAGE_WATCH_ALL_CHANGE,
                "reason": ("在 {0} 个实际触发窗口上全部改选：可能是针对性修正，"
                           "也可能是无差别覆盖；须人工看改选矩阵后再决定升级").format(basis),
                "is_a_verdict_on_the_mechanism": False}
    return {"decision": TRIAGE_UPGRADE,
            "reason": "无执行故障、覆盖足够、行为有分化：可进入下一级评估",
            "is_a_verdict_on_the_mechanism": False}


#: 失败明细最多保留多少条（防止一份坏语料把报告撑爆；计数不受影响）。
_MAX_FAILURE_DETAIL = 20


def _remember_failure(sink: List[Dict[str, Any]], window_key: str, exc: BaseException) -> None:
    """记录一次**执行失败**（窗口标识 + 异常类型与文本）；计数不受明细上限影响。"""

    if len(sink) >= _MAX_FAILURE_DETAIL:
        return
    sink.append({"window": window_key,
                 "error": "{0}: {1}".format(type(exc).__name__, exc)[:300]})


def gate_g2(candidate_name: str, weights: Mapping[str, float],
            rows: Sequence[Mapping[str, Any]], ruleset: str = "v26") -> Dict[str, Any]:
    """G-2：在同一批记录观察上比较基线与候选的首选，报改选率、矩阵与退化。

    **只作门禁**：本函数的任何输出都不得用于排序或淘汰。
    """

    codec = build_decision_codec()
    decode_request, decode_budget = codec["decode_request"], codec["decode_budget"]
    rules = HangmaRules(RuleConfig(ruleset_version=ruleset, base_score=1,
                                   you_cai_bi_kao=False))
    clock = ManualClock(start_monotonic=100.0)
    baseline = ComparableHeuristicPolicyV2(monotonic=clock.now)
    policy = heuristics.build_candidate(candidate_name, weights=weights,
                                        monotonic=clock.now)

    class_counts: Counter = Counter()
    changed_by_class: Counter = Counter()
    matrix: Counter = Counter()
    first_kind_counts: Counter = Counter()
    excluded = 0              # 解码失败 + 规则事实不可用（**不含**策略执行失败）
    excluded_decode = 0       # 其中：行解不出请求/预算/规则分析
    excluded_degraded = 0     # 其中：规则分析降级或没有合法候选
    # **执行失败单独记**（R8-1）：它是"已经出错"，不是"样本被排除"。
    # 明细有上限（防止坏语料撑爆报告），**计数没有上限**（轮次 3 更正）：
    # 两者分开，计数才敢用来对账"总窗口 = 排除 + 适用 + 失败"。
    candidate_failures: List[Dict[str, Any]] = []
    baseline_failures: List[Dict[str, Any]] = []
    candidate_failure_total = 0
    baseline_failure_total = 0
    applicable_n = 0          # 声明 scope 内存在合法候选的窗口
    applicable_changed = 0    # 其中首选被改选的窗口
    out_of_scope_n = 0        # 声明 scope 外的窗口
    out_of_scope_changed = 0  # 其中首选被改选的窗口（真外溢）
    fired_windows = 0         # 候选给出过非零调整的窗口（全部）
    fired_in_scope = 0        # 其中落在声明 scope 内的
    for row in rows:
        payload = row.get("request")
        if not isinstance(payload, Mapping):
            excluded += 1
            excluded_decode += 1
            continue
        try:
            recorded = decode_request(payload)
            budget = translate_budget(
                decode_budget(row.get("budget"), row.get("budget_origin_monotonic", 0.0)),
                row.get("budget_origin_monotonic", 0.0), 100.0)
            analysis = rules.analyze(recorded.observation)
        except Exception:
            excluded += 1
            excluded_decode += 1
            continue
        if analysis.completeness is RuleCompleteness.DEGRADED or not analysis.legal_candidates:
            excluded += 1
            excluded_degraded += 1
            continue
        request = DecisionRequest(
            observation=recorded.observation, competition=recorded.competition,
            rules=analysis, decision_id=recorded.decision_id,
            trigger_seq=recorded.trigger_seq, window_key=recorded.window_key,
            rejected_attempts=())
        keys = [c.action_key for c in analysis.legal_candidates]
        # D1：适用面由**候选声明的 scope**决定，不硬编码成响应窗口。
        in_scope = any(policy.adjustment.applies_to(key) for key in keys)
        fired_before = policy.adjustment.fired_count
        window_key = str(recorded.decision_id)
        # **基线与候选分开 try**（R8-1）：合成一个 except 会把"候选抛错"
        # 混进"基线抛错/输入不可用"，而两者的处置不同。
        try:
            base_plan = asyncio.run(baseline.choose(request, budget))
        except Exception as exc:
            _remember_failure(baseline_failures, window_key, exc)
            baseline_failure_total += 1
            continue
        try:
            cand_plan = asyncio.run(policy.choose(request, budget))
        except Exception as exc:
            _remember_failure(candidate_failures, window_key, exc)
            candidate_failure_total += 1
            continue
        klass = recompute.window_class(keys)
        class_counts[klass] += 1
        # 触发面：本窗口里候选是否真的给出过非零调整（诊断量，不参与评分）。
        if policy.adjustment.fired_count > fired_before:
            fired_windows += 1
            if in_scope:
                fired_in_scope += 1
        base_first = recompute._first_key(base_plan)
        cand_first = recompute._first_key(cand_plan)
        first_kind_counts[recompute._kind(base_first)] += 1
        if in_scope:
            applicable_n += 1
        else:
            out_of_scope_n += 1
        if cand_first != base_first:
            changed_by_class[klass] += 1
            matrix["{0}->{1}".format(recompute._kind(base_first),
                                     recompute._kind(cand_first))] += 1
            if in_scope:
                applicable_changed += 1
            else:
                out_of_scope_changed += 1

    # 旧口径的响应窗口统计保留，便于与既有证据文件对照（不作判定依据）。
    response_n = class_counts.get("response", 0)
    response_changed = changed_by_class.get("response", 0)
    others_n = sum(v for k, v in class_counts.items() if k != "response")
    # 判定逻辑抽成纯函数：门禁"能否失败"必须能被精确测试（见 test_sitin_gates.py）。
    total_windows = sum(class_counts.values())
    status_g2, problems, notes, rate = g2_verdict(
        applicable_n, applicable_changed, out_of_scope_changed, total_windows,
        fired_n=fired_in_scope,
        candidate_failures=candidate_failures, baseline_failures=baseline_failures,
        candidate_failure_total=candidate_failure_total,
        baseline_failure_total=baseline_failure_total)
    problems = list(problems)
    directions = [key for key in matrix if "->" in key]
    both_directions = any(not key.startswith(key.split("->")[0]) for key in directions)
    # 判据分母与 g2_verdict 同口径：优先取**触发面**，没有触发才退回适用面。
    basis = fired_in_scope if fired_in_scope else applicable_n
    # 行为诊断：**描述面板行为**，不参与判定（REVIEW-9）。
    diagnosis = {
        "applicable_windows": applicable_n,
        "fired_windows_in_scope": fired_in_scope,
        "changed_in_scope": applicable_changed,
        "basis": basis,
        "change_rate": rate,
        "change_matrix": dict(matrix),
        "out_of_scope_changed": out_of_scope_changed,
        # **真实计数**（不是明细长度）：轮次 3 更正——初版这里写 len(明细)，
        # 于是一份 91 个失败窗口的语料在诊断里显示成 20。
        "candidate_execution_failure_count": candidate_failure_total,
        "baseline_execution_failure_count": baseline_failure_total,
        "note": "行为诊断只描述面板行为，不判定策略好坏（REVIEW-9）",
    }
    triage = g2_triage(status_g2, applicable_n=applicable_n, fired_n=fired_in_scope,
                       basis=basis, rate=rate)
    return {
        # status 直接取纯函数的**三态**结果：证据不足不再被翻译成 PASS（R7-8）。
        "gate": "G-2 退化检测", "status": status_g2,
        "problems": problems, "notes": notes,
        "diagnosis": diagnosis,
        "triage": triage,
        "detail": {
            "window_classes": dict(class_counts), "excluded": excluded,
            # R8-1：排除与**执行失败**分开计数——前者是"没测到"，后者是"已经出错"。
            "excluded_decode": excluded_decode,
            "excluded_degraded": excluded_degraded,
            # 明细是**有上限的样本**；计数与对账用下面的真实值（轮次 3 更正）。
            "candidate_execution_failures": list(candidate_failures),
            "baseline_execution_failures": list(baseline_failures),
            "candidate_execution_failure_samples": len(candidate_failures),
            "baseline_execution_failure_samples": len(baseline_failures),
            "failed_windows": {"candidate": candidate_failure_total,
                               "baseline": baseline_failure_total},
            # **对账**：本函数把每一行恰好归入一个桶，因此这五个数必须等于行数。
            # 有它，"报告里的数"与"语料里的行"才不是两套说法。
            "accounting": {
                "rows": len(rows),
                "excluded": excluded,
                "baseline_failed": baseline_failure_total,
                "candidate_failed": candidate_failure_total,
                "applicable": applicable_n,
                "out_of_scope": out_of_scope_n,
                "sum": (excluded + baseline_failure_total + candidate_failure_total
                        + applicable_n + out_of_scope_n),
                "reconciles": (excluded + baseline_failure_total + candidate_failure_total
                               + applicable_n + out_of_scope_n) == len(rows),
            },
            # 判定口径（D1）：适用面按**声明 scope** 统计。
            "declared_scope": list(policy.adjustment.spec.scope),
            "applicable_windows": applicable_n,
            "applicable_changed": applicable_changed,
            "applicable_change_rate": rate,
            "fired_windows": fired_windows,
            "fired_windows_in_scope": fired_in_scope,
            "out_of_scope_windows": out_of_scope_n,
            "out_of_scope_changed": out_of_scope_changed,
            # 旧口径，保留以便与既有证据文件对照；**不作判定依据**。
            "response_windows": response_n, "response_changed": response_changed,
            "offscope_changed": out_of_scope_changed,
            "offscope_windows": out_of_scope_n,
            "change_matrix": dict(matrix),
            "baseline_first_kinds": dict(first_kind_counts),
            "has_offscope_spill": bool(out_of_scope_changed),
            # 供报告使用，**不作排序依据**
            "note": "本项只作门禁与诊断，禁止用于适应度排序（README §4.2/DESIGN §4.3）",
        },
        "directions_present": sorted({k.split("->")[1] for k in directions}),
    }


# ---------------------------------------------------------------------------
# 3.6b 逐类判定（perclass）：把「分量 ↔ 规则可枚举场景类」从覆盖账推进到**门禁可判**
#
# 3.6a 交付了逐类覆盖账（`sitin_scenario_classes.py`），但它**不进任何门禁**：
# 门禁的结论是**面板级计数**，于是「19 个声明类里只有 2 个有证据」与
# 「2 个声明类全有证据」在记录里**同形**——一类的证据不足被别类的 PASS 掩盖。
#
# 本节补三件事（README §17 3.6b 的判据）：
#   ① **逐类报告**：每个 (候选 × 场景类) 给三态 `reliable / insufficient / not_verified`；
#      汇总只取**最弱环节**——类间不可互相掩盖，一个类的 reliable 也不构成整体结论；
#   ② **类外零增量判定**：改选必须落在**已声明类**内；归属未知单列，**不填零**；
#   ③ **受控研究执行入口**：把「全局准入」与「有范围的研究执行」拆开；研究记录绑定
#      候选 / 面板 / 采样器身份与声明范围，**先实现拒绝路径**，且**永不产出准入**。
#
# **本段不参与 `admitted`**（PHASE3-RULE-AWARE §4.4：覆盖 INSUFFICIENT 不等于不安全，
# 也不等于低价值）。它只回答一句话：候选**自己声明的那些类**里，有哪些在本面板上被验证过。
# ---------------------------------------------------------------------------

#: 场景类清单工具的模块名。**类的唯一来源是 `sitin_scenario_classes.py`**：
#: 本文件不复制类清单、不复制谓词——复制一份就等于多一处会漂移的真相。
SCENARIO_TOOL = "sitin_scenario_classes"
#: 逐类判定段的 schema（落在门禁记录的 `perclass` 段里）。
PERCLASS_SCHEMA = "sitin-gates-perclass/1"
#: 研究请求 / 研究记录的 schema。**有版本**是研究入口的拒绝条件之一。
RESEARCH_REQUEST_SCHEMA = "sitin-gates-research-request/1"
RESEARCH_SCHEMA = "sitin-gates-research/1"
#: 研究入口自身的版本（调用方必须显式声明同一个版本，否则拒绝）。
RESEARCH_ENTRY_VERSION = "perclass-research/1"
#: 逐类判定的门禁名：与 G-1/G-2/G-3 **并列展示**，但**不进 `gates` 列表**——
#: 进了列表就会改 `all_pass`/`admitted` 的含义，而"旧 admitted 含义不变"是硬要求。
G2C_GATE_LABEL = "G-2C 逐类覆盖"

#: 记录层视图的取值（与 sitin_scenario_classes.RECORD_LAYER_MODES **同值同义**；
#: 这里写常量而不是 import，是为了让父进程不必为了读一个字符串而加载场景类工具）。
SCENARIO_RECORD_LAYER_RAW = "raw"
SCENARIO_RECORD_LAYER_FILLED = "filled"

#: 逐类三态（README §17.3.6 设计口径 2 的原文用词）。
CLASS_RELIABLE = "reliable"
CLASS_INSUFFICIENT = "insufficient"
CLASS_NOT_VERIFIED = "not_verified"
#: 候选没有声明覆盖该类：这是**声明**的陈述，不是对该类的判定，因此单列。
CLASS_UNDECLARED = "undeclared"
CLASS_VERDICTS: Tuple[str, ...] = (CLASS_RELIABLE, CLASS_INSUFFICIENT, CLASS_NOT_VERIFIED)

#: 判定理由（机读）：测试与报告都按理由断言，不靠读自然语言猜。
REASON_NOT_DECLARED = "not_declared"
REASON_NO_POSITION = "no_position_on_panel"
REASON_FACTS_MISSING = "facts_missing_on_panel"
REASON_BELOW_WINDOW_FLOOR = "below_window_floor"
REASON_BELOW_FIRED_FLOOR = "fired_below_floor"
REASON_FIRED_NO_CHANGE = "fired_no_change"
REASON_OK = "ok"

#: 三态与理由的固定读法（**必须与数字一起引用**，否则"未验证"会被读成"无影响"）。
CLASS_VERDICT_NOTES: Mapping[str, str] = {
    CLASS_RELIABLE: ("本面板上该类位点与触发面均达下限、且观察到改选：**只说明该类被验证过**，"
                     "不是效果结论，也不构成整候选结论。"),
    CLASS_INSUFFICIENT: ("已声明但证据不足（位点或触发面不到下限，或触发到了没改选）："
                         "**不等于通过**，也不等于机制无效（REVIEW-9：极值只作行为诊断）。"),
    CLASS_NOT_VERIFIED: ("已声明但本面板上无法验证（无位点，或所需事实在该类上不可判定）："
                         "**不得填零**，也不得读成「无影响」。"),
    CLASS_UNDECLARED: "候选没有声明覆盖该类：这是**声明**的陈述，不是对该类的判定。",
}

REASON_NOTES: Mapping[str, str] = {
    REASON_NOT_DECLARED: "候选静态声明里没有该类（记号级**弱**声明，见 boundaries 第 1 条）。",
    REASON_NO_POSITION: "本面板上该类一个可判定窗口都没有 ⇒ **未验证**（不是「无影响」，也不得填零）。",
    REASON_FACTS_MISSING: "本面板上该类有窗口但**全部不可判定**（所需事实不在评分上下文）⇒ 未验证。",
    REASON_BELOW_WINDOW_FLOOR: "类内可判定窗口数低于下限 ⇒ 证据不足。",
    REASON_BELOW_FIRED_FLOOR: "类内候选触发窗口数低于下限 ⇒ 触发面太小，证据不足。",
    REASON_FIRED_NO_CHANGE: ("触发过但没有改变首选：本面板与本配置下该类**没有被验证**；"
                             "按 REVIEW-9，这**不是**退化判定。"),
    REASON_OK: "位点与触发面均达下限，且观察到改选。",
}


def class_reliability(declared: bool, windows_in_class: int, windows_undecided: int,
                      fired: int, changed: int, *,
                      window_floor: int = G2_MIN_FIRED_WINDOWS,
                      fired_floor: int = G2_MIN_FIRED_WINDOWS) -> Tuple[str, str]:
    """一个 (候选 × 场景类) 的证据三态（纯函数，便于精确测试门禁**能否失败**）。

    与 3.6a 的覆盖四态**同源、不同问**：3.6a 问「面板上这类有多少可判定窗口」，
    本函数问「候选**自己声明**的这类，在本面板上**被验证了吗**」。两者共用同一份
    `evaluate_panel` 记录；`window_floor` 缺省等于 3.6a 的 `MIN_CLASS_WINDOWS`
    （同一份证据下限口径；场景类工具的 `--check` 会现读本模块常量核对，防两处漂移）。

    三态（**没有第四态，也没有分数**）：
      reliable       位点够（>= window_floor）、触发够（>= fired_floor）、且观察到改选；
      insufficient   已声明但证据不足：位点不够、触发面不够，或**触发到了没改选**；
      not_verified   已声明但本面板**无法验证**：类内 0 个可判定窗口——
                     `windows_undecided > 0` 表示事实缺失 ⇒ **不得填零**。

    未声明的类返回 `undeclared`：它描述**声明**，不是对该类的判定。
    """

    if not declared:
        return CLASS_UNDECLARED, REASON_NOT_DECLARED
    if windows_in_class <= 0:
        if windows_undecided > 0:
            return CLASS_NOT_VERIFIED, REASON_FACTS_MISSING
        return CLASS_NOT_VERIFIED, REASON_NO_POSITION
    if windows_in_class < int(window_floor):
        return CLASS_INSUFFICIENT, REASON_BELOW_WINDOW_FLOOR
    if fired < int(fired_floor):
        return CLASS_INSUFFICIENT, REASON_BELOW_FIRED_FLOOR
    if changed <= 0:
        return CLASS_INSUFFICIENT, REASON_FIRED_NO_CHANGE
    return CLASS_RELIABLE, REASON_OK


def class_verdict_note(verdict: str, reason: str) -> str:
    """三态 + 理由的读法（**单一来源**，报告与测试都从这里取文字）。"""

    head = CLASS_VERDICT_NOTES.get(verdict, "未知状态：不得据此下任何结论")
    tail = REASON_NOTES.get(reason, "未知理由：不得据此下任何结论")
    return "{0} 判据：{1}".format(head, tail)


def perclass_rollup(classes: Sequence[Mapping[str, Any]], *,
                    violations: Sequence[Mapping[str, Any]] = (),
                    undecided_changes: Sequence[Mapping[str, Any]] = (),
                    execution_failures: int = 0) -> Dict[str, Any]:
    """把逐类三态汇总成**最弱环节**结论（纯函数）。

    **为什么是"最弱环节"而不是平均**（README §17.3.6 设计口径 2）："任何一类的证据不足
    不得被别类的 PASS 掩盖"。因此：

      FAIL         观察到**确定的问题**：类外改选（声明与实际不符）或候选/基线执行失败。
                   这两件事与样本量无关，一旦出现就是确定的坏事。
      INSUFFICIENT 没有确定问题，但**存在未达 reliable 的已声明类**、或存在**归属未知**的
                   改选（类外零增量无法核对）、或候选**一个类都没声明**（无法逐类判定）。
      PASS         **全部已声明类**都 reliable。

    **它反向不成立**：PASS 只说明"候选自己声明的那些类在本面板上都被验证过"，
    既不是效果结论，也不是准入结论（准入是 `admitted`，研究执行是另一个入口）。
    """

    problems: List[str] = []
    notes: List[str] = []
    declared = [entry for entry in classes if entry.get("declared")]
    blocking = [{"class_id": entry["id"], "verdict": entry["verdict"], "reason": entry["reason"]}
                for entry in declared if entry["verdict"] != CLASS_RELIABLE]
    reliable = [entry["id"] for entry in declared if entry["verdict"] == CLASS_RELIABLE]
    counts: Dict[str, int] = {verdict: 0 for verdict in CLASS_VERDICTS}
    counts[CLASS_UNDECLARED] = 0
    for entry in classes:
        counts[entry["verdict"]] = counts.get(entry["verdict"], 0) + 1

    if execution_failures:
        problems.append(
            "候选/基线执行失败 {0} 个窗口：它既不是「未验证」也不是「证据不足」，"
            "**已明确出错**（明细见 panel）".format(execution_failures))
    if violations:
        problems.append(
            "类外改选 {0} 个窗口：改选既不在候选已声明的类内、也不落在已声明类的"
            "**不可判定**窗口上 ⇒ 声明与实际不符（窗口样本见 out_of_class_increment）".format(
                len(violations)))

    if problems:
        status = "FAIL"
    elif not declared:
        status = "INSUFFICIENT"
        notes.append("候选**没有声明任何场景类**：逐类判定无从谈起，"
                     "**这是证据不足，不是通过**")
    elif blocking or undecided_changes:
        status = "INSUFFICIENT"
    else:
        status = "PASS"

    notes.append(
        "汇总只取**最弱环节**：已声明 {0} 类，其中 reliable {1} 类；"
        "**类间不可互相掩盖**（任一已声明类未达 reliable 即汇总不给通过），"
        "反之**一个类的 reliable 也不构成整候选结论**".format(len(declared), len(reliable)))
    if undecided_changes and not problems:
        notes.append(
            "另有 {0} 个改选窗口的**归属未知**（改选落在已声明类的不可判定窗口上）："
            "既不能算类外溢出、也不能算合规 ⇒ 类外零增量**无法核对**，不得填零".format(
                len(undecided_changes)))

    return {
        "status": status,
        "problems": problems,
        "notes": notes,
        "counts": counts,
        "declared_classes": [entry["id"] for entry in declared],
        "reliable_classes": reliable,
        "blocking_classes": blocking,
        "reliable_count": len(reliable),
        "declared_count": len(declared),
        # 三个显式"不是什么"：防止汇总被下游读成准入/效果/排序依据。
        "not_admission_basis": True,
        "is_a_verdict_on_strength": False,
        "is_a_verdict_on_safety": False,
        "note": ("本汇总是**覆盖**结论：不得当准入、不得当效果、不得用于排序或适应度。"
                 "覆盖 INSUFFICIENT **不等于**不安全，也不等于低价值"
                 "（PHASE3-RULE-AWARE §4.4）。"),
    }


_SCENARIO: Optional[Any] = None


def scenario_classes():
    """惰性导入场景类清单工具（类清单与谓词的**唯一来源**）。

    **为什么惰性**：该模块在导入时会 import `policy.heuristics.four_component_path_value`
    （取 `four_white_state` / `known_piao` 等事实函数）。"父进程不执行候选侧代码"
    是本项目的既有纪律（REVIEW-9 的装载有界），因此只在真正需要逐类判定时
    （即受监管子进程内）导入，`import sitin_gates` 本身仍然不碰任何候选模块。
    """

    global _SCENARIO
    if _SCENARIO is None:
        _SCENARIO = _load(SCENARIO_TOOL)
    return _SCENARIO


def gate_g2c(candidate_name: str, weights: Mapping[str, float],
             rows: Sequence[Mapping[str, Any]], ruleset: str = "v26", *,
             raw_diagnostics: bool = True,
             record_layer: str = SCENARIO_RECORD_LAYER_RAW) -> Dict[str, Any]:
    """G-2C：逐类覆盖判定（**在受监管子进程里运行**，与 G-1/G-2 共用同一套隔离）。

    与 `gate_g2` 的关系：G-2 回答"这份候选在**整个面板**上是否退化/是否越界"，
    G-2C 回答"它**自己声明的每个场景类**，在本面板上被验证到了什么程度"。两者不互相替代。

    口径（与 3.6a 的覆盖账同源，避免两套账）：
      · 面板记录由 `sitin_scenario_classes.evaluate_panel` 产出（同一份解码、规则分析、
        分类与首选动作口径；首选取 `sitin_m4_recompute._first_key`）；
      · 类清单与谓词来自该工具，**本文件不复制**；
      · 下限 `window_floor` 取该工具的 `MIN_CLASS_WINDOWS`（`--check` 已把它与
        本模块的 `G2_MIN_FIRED_WINDOWS` 钉在一起）；
      · **候选参数随身份传入**（`weights`）：逐类判定必须针对与门禁记录同一个
        `bound_identity` 的候选；3.6a 的覆盖账用注册表默认参数，那是它的口径，
        不是门禁的口径。

    **它是只读的计算**：不跑桌赛、不写语料、不改任何候选或配置。
    """

    scenario = scenario_classes()
    # rows 可以是任意可迭代（惰性）：记录层视图与 raw 诊断都由 evaluate_panel 单次遍历完成。
    evaluation = scenario.evaluate_panel(
        rows, [candidate_name], ruleset=ruleset,
        weights_by_candidate={candidate_name: dict(weights)},
        record_layer=record_layer, diagnostics=True)
    return perclass_records(evaluation, candidate_name, weights=weights,
                            ruleset=ruleset, raw_diagnostics=raw_diagnostics)


def perclass_records(evaluation: Mapping[str, Any], candidate_name: str, *,
                     weights: Optional[Mapping[str, float]] = None,
                     ruleset: str = "v26", raw_diagnostics: bool = True) -> Dict[str, Any]:
    """从**已有的** evaluate_panel 输出构造一份 G-2C 门禁记录（纯函数：无 IO、不跑候选）。

    **为什么要有这个纯函数**：canonical 面板 359,262 行上，"6 个候选各跑一遍"要 6 遍扫描，
    而 evaluate_panel 本来就支持**一次扫描多个候选**。把判定逻辑抽出来后，两种入口
    （gate_g2c 单候选 / 共享扫描的多候选）产出**逐字相同**的记录形状——
    判定只有一份实现，扫描次数只是工程选择。
    """

    scenario = scenario_classes()
    floor = int(getattr(scenario, "MIN_CLASS_WINDOWS", G2_MIN_FIRED_WINDOWS))
    weights = dict(weights or {})
    records = evaluation["records"]
    aggregate = scenario.aggregate_records(records, [candidate_name])
    declarations = scenario.candidate_declarations(candidate_name)
    declared = list(scenario.declared_from_table(declarations["classes"]))
    scoped = scenario.class_scope_violations(records, candidate_name, declared)

    classes_out: List[Dict[str, Any]] = []
    for item in scenario.CLASSES:
        cid = item["id"]
        bucket = aggregate["classes"][cid]
        counts = bucket["candidates"][candidate_name]
        decl = declarations["classes"][cid]
        verdict, reason = class_reliability(
            bool(decl["declared"]), bucket["windows_in_class"], bucket["windows_undecided"],
            counts["fired"], counts["changed"], window_floor=floor)
        classes_out.append({
            "id": cid,
            "name": item["name"],
            "kind": item["kind"],
            "level": item["level"],
            "declared": bool(decl["declared"]),
            "scope_hit": decl["scope_hit"],
            "token_hit": decl["token_hit"],
            "windows_in_class": bucket["windows_in_class"],
            "windows_undecided": bucket["windows_undecided"],
            "windows_out_of_class": bucket["windows_out_of_class"],
            "fired_windows": counts["fired"],
            "changed_windows": counts["changed"],
            "verdict": verdict,
            "reason": reason,
            "verdict_note": class_verdict_note(verdict, reason),
        })

    panel = dict(evaluation["panel"])
    execution_failures = int(panel.get("candidate_failed", 0)) + int(panel.get("baseline_failed", 0))
    rollup = perclass_rollup(
        classes_out, violations=scoped["violations"],
        undecided_changes=scoped["undecided_changes"], execution_failures=execution_failures)

    return {
        "gate": G2C_GATE_LABEL,
        "status": rollup["status"],
        "problems": rollup["problems"],
        "notes": rollup["notes"],
        "detail": {
            "schema": PERCLASS_SCHEMA,
            "candidate": candidate_name,
            "weights": dict(weights),
            "weights_applied": True,
            "declared_classes": declared,
            "ruleset_version": ruleset,
            "record_layer": evaluation["panel"].get("record_layer"),
            "declaration_note": declarations.get("note"),
            "classes": classes_out,
            "rollup": rollup,
            "out_of_class_increment": {
                "declared_classes": declared,
                "changed_windows": sum(
                    1 for record in records if record["per_candidate"][candidate_name]["changed"]),
                "violations": list(scoped["violations"][:_MAX_FAILURE_DETAIL]),
                "violation_total": len(scoped["violations"]),
                "undecided_changes": list(scoped["undecided_changes"][:_MAX_FAILURE_DETAIL]),
                "undecided_change_total": len(scoped["undecided_changes"]),
                "note": ("类外零增量：改选必须落在已声明类内。"
                         "violations 是**确定的外溢**；undecided_changes 是**归属未知**，"
                         "两者分开、都不填零。"),
            },
            "panel": panel,
            "panel_facts": dict(evaluation["panel_facts"]),
            # raw 层诊断由 evaluate_panel 的单次遍历产出（3.6b 返工：不再二次读入面板）。
            "panel_raw": (panel.get("raw_coverage") if raw_diagnostics else None),
            "window_floor": floor,
            "fired_floor": G2_MIN_FIRED_WINDOWS,
            "units": {
                "windows_in_class": "计数：本面板上该类**判定为成立**的窗口数",
                "windows_undecided": "计数：该类**不可判定**的窗口数（事实缺失，不得填零）",
                "fired_windows": "计数：类内候选给出过非零调整的窗口数",
                "changed_windows": "计数：类内首选动作被改选的窗口数",
                "note": ("本段**只含计数**：没有番、没有积分、没有评分点、没有权重，"
                         "也不产出排序或适应度。"),
            },
            "not_in_admitted": ("本段**不参与** `admitted`/`all_pass`：覆盖不足不等于不安全"
                                "（PHASE3-RULE-AWARE §4.4）。研究执行资格见研究入口。"),
            "boundaries": [
                "触发集是构造集：只证明接线与提供可触发作用面；不得用于效应估计、排序、淘汰或晋级声明。",
                "unknown/not_verified 不得填零，也不得读成「无影响」。",
                "逐类三态不得合并成单一总分；汇总只取最弱环节，且不是准入或效果结论。",
                "记录缺口 ≠ 机制稀有：面板无位点不构成机制稀缺性判断，也不得据此做预算规划。",
            ],
        },
    }


def _gate_failures(gate_record: Mapping[str, Any]) -> List[Dict[str, Any]]:
    """从门禁记录里取 **FAIL** 的门（研究执行的前置之一：执行安全）。"""

    failures: List[Dict[str, Any]] = []
    for gate in gate_record.get("gates", ()) or ():
        if isinstance(gate, Mapping) and gate.get("status") == "FAIL":
            failures.append({"gate": gate.get("gate"), "problems": list(gate.get("problems", ()))})
    return failures


def research_execution_entry(request: Mapping[str, Any], *,
                             gate_record: Mapping[str, Any]) -> Dict[str, Any]:
    """受控研究执行入口：**先把拒绝路径走完**，再谈能不能执行（PHASE3-RULE-AWARE §4.4/§4.5）。

    合同（三条，都是"缺一即拒绝"）：

      ① **与全局准入分开**：本函数产出的记录 `admitted` 恒为 `False`、`evidence_kind`
         恒为 `research`；研究记录**不接受**任何"准入 / 效果 / 晋级"的声明范围
         （出现即拒绝），避免"触发集 PASS 被旧扫描器误当成全局准入"。
      ② **身份与范围绑定**：候选身份（`bound_identity`）、面板身份（sha256 + 行数 +
         是否构造集）、采样器身份（id + 版本 + **先冻结后运行** + 种子）与声明范围
         四处齐备且互相一致，否则拒绝。
      ③ **结论范围只能落在已被验证的类上**：`claim_classes` 必须是逐类三态为
         `reliable` 的类；`research_classes`（要采样的类）**可以**包含尚未验证的类——
         那正是研究的目的——但记录会把它们标成"证据待补"。

    返回的记录始终带 `refusals`（**全部拒绝理由**，不是第一条）与
    `permitted = not refusals`；`admitted` 恒为 False。
    """

    refusals: List[Dict[str, Any]] = []

    def refuse(code: str, reason: str, **extra: Any) -> None:
        entry: Dict[str, Any] = {"code": code, "reason": reason}
        entry.update(extra)
        refusals.append(entry)

    if not isinstance(request, Mapping):
        refuse("request_missing", "没有研究请求：受控研究执行必须先有一次显式请求（JSON）")
        request = {}
    if not isinstance(gate_record, Mapping):
        refuse("gate_record_missing", "没有门禁记录：研究执行的前置是同一候选的门禁记录")

    # ① 版本与形态（"有版本"是范围绑定的前提：没有版本就无法判断范围属于哪一版）
    if request.get("schema") != RESEARCH_REQUEST_SCHEMA:
        refuse("request_schema", "研究请求 schema 必须是 {0}，得到 {1!r}".format(
            RESEARCH_REQUEST_SCHEMA, request.get("schema")))
    if request.get("entry_version") != RESEARCH_ENTRY_VERSION:
        refuse("entry_version", "研究入口版本必须是 {0}，得到 {1!r}".format(
            RESEARCH_ENTRY_VERSION, request.get("entry_version")))

    perclass = gate_record.get("perclass") if isinstance(gate_record, Mapping) else None
    perclass_ok = isinstance(perclass, Mapping) and perclass.get("detail", {}).get("schema") == PERCLASS_SCHEMA
    if not perclass_ok:
        refuse("perclass_missing",
               "门禁记录里没有逐类判定段（G-2C）：结论范围无法核对 ⇒ 拒绝（先跑 --perclass）")
    detail = perclass.get("detail", {}) if perclass_ok else {}
    verdicts = {entry["id"]: entry["verdict"] for entry in detail.get("classes", ())}

    # ② 候选身份
    candidate = request.get("candidate")
    record_candidate = gate_record.get("candidate") if isinstance(gate_record, Mapping) else None
    if not candidate or not record_candidate:
        refuse("candidate_identity_unbound", "候选名缺失：研究记录必须绑定到具体候选")
    elif candidate != record_candidate:
        refuse("candidate_identity_mismatch",
               "研究请求的候选 {0!r} 与门禁记录的候选 {1!r} 不一致".format(candidate, record_candidate))
    bound_identity = request.get("bound_identity")
    record_bound = gate_record.get("bound_identity") if isinstance(gate_record, Mapping) else None
    if not bound_identity or not record_bound:
        refuse("candidate_identity_unbound",
               "bound_identity 缺失（请求或门禁记录）：没有它，研究结果无法绑回具体候选身份")
    elif bound_identity != record_bound:
        refuse("candidate_identity_mismatch",
               "研究请求的 bound_identity 与门禁记录不一致（参数或代码已变）")

    # ③ 面板身份
    panel = request.get("panel")
    record_panel = gate_record.get("corpus") if isinstance(gate_record, Mapping) else None
    if not isinstance(panel, Mapping) or not isinstance(record_panel, Mapping):
        refuse("panel_identity_unbound", "面板身份缺失：研究记录必须绑定到具体面板（sha256 + 行数）")
    else:
        for key in ("sha256", "rows"):
            if not panel.get(key) or panel.get(key) != record_panel.get(key):
                refuse("panel_identity_mismatch",
                       "面板 {0} 与门禁记录不一致：请求 {1!r} / 记录 {2!r}".format(
                           key, panel.get(key), record_panel.get(key)))
        if bool(panel.get("constructed_trigger_set")) != bool(record_panel.get("constructed_trigger_set")):
            refuse("panel_identity_mismatch", "constructed_trigger_set 与门禁记录不一致")

    # ④ 采样器身份（先冻结后运行；种子必须显式）
    sampler = request.get("sampler")
    if not isinstance(sampler, Mapping):
        refuse("sampler_identity_unbound", "采样器身份缺失：没有采样器身份就没有可复核的抽样律")
        sampler = {}
    for key in ("id", "version"):
        if not str(sampler.get(key) or "").strip():
            refuse("sampler_identity_unbound", "采样器缺少 {0}".format(key))
    if sampler.get("frozen_before_run") is not True:
        refuse("sampler_not_frozen", "采样器必须**先冻结后运行**（frozen_before_run=true）")
    seeds = sampler.get("seeds")
    if not isinstance(seeds, (list, tuple)) or not seeds:
        refuse("sampler_seeds_missing", "采样器必须显式列出种子（seeds 非空）")

    scope = request.get("scope") if isinstance(request.get("scope"), Mapping) else {}
    research_classes = list(scope.get("research_classes") or ())
    claim_classes = list(scope.get("claim_classes") or ())
    claim_kinds = list(scope.get("claim_kinds") or ())
    declared_classes = list(detail.get("declared_classes") or ())

    # ⑤ 研究范围必须显式（否则"研究"没有边界，事后无法判断结论覆盖了谁）
    if not research_classes:
        refuse("research_scope_unbounded", "研究范围为空：必须显式列出要采样/研究的场景类")

    # ⑥ 结论范围只能落在已声明的类上，且只能是已被验证（reliable）的类
    for cid in list(research_classes) + list(claim_classes):
        if declared_classes and cid not in declared_classes:
            refuse("scope_not_declared", "类 {0} 不在候选的已声明类里（{1}）".format(
                cid, len(declared_classes)))
    for cid in claim_classes:
        if verdicts and verdicts.get(cid) != CLASS_RELIABLE:
            refuse("claim_without_evidence",
                   "结论类 {0} 的逐类判定是 {1!r}，不是 {2!r}：结论不得落在未验证的类上".format(
                       cid, verdicts.get(cid), CLASS_RELIABLE))

    # ⑦ 研究记录永不携带准入/效果/晋级结论
    admission_kinds = ("admission", "effect", "promotion")
    if request.get("admission") or request.get("gate_level_admitted"):
        refuse("admission_claim", "研究请求试图携带准入结论：研究执行资格**不是**发布准入")
    for kind in claim_kinds:
        if str(kind) in admission_kinds:
            refuse("admission_claim", "声明范围里出现了 {0!r}：研究记录不得承载准入/效果/晋级结论".format(kind))
    known_kinds = ("behavior", "conditional_effect")
    for kind in claim_kinds:
        if str(kind) not in known_kinds and str(kind) not in admission_kinds:
            refuse("claim_kind_unknown", "未知的声明种类 {0!r}（允许：{1}）".format(kind, list(known_kinds)))

    # ⑧ 执行安全是研究执行的前置（有 FAIL 门 ⇒ 先修执行，再谈研究）
    failures = _gate_failures(gate_record)
    if failures:
        refuse("unsafe_gates", "门禁存在 FAIL：{0} ⇒ 研究执行前必须先修复执行侧问题".format(
            [item["gate"] for item in failures]))

    # ⑨ 构造触发集上可以研究**行为**，但不得据此声明条件效果/整体效果
    requested_panel = request.get("panel") if isinstance(request.get("panel"), Mapping) else {}
    constructed = bool(requested_panel.get("constructed_trigger_set"))
    if constructed and "conditional_effect" in [str(k) for k in claim_kinds]:
        refuse("constructed_panel_effect_claim",
               "面板是**构造触发集**：不得在其上声明条件效果或任何效应结论")

    permitted = not refusals
    return {
        "schema": RESEARCH_SCHEMA,
        "entry_version": RESEARCH_ENTRY_VERSION,
        "permitted": permitted,
        "refusals": refusals,
        # **恒为 False**：研究记录不得被任何扫描器读成准入。
        "evidence_kind": "research",
        "admitted": False,
        "gate_level_admitted": False,
        "candidate": candidate,
        "identities": {
            "candidate_bound_identity": bound_identity,
            "panel": dict(panel) if isinstance(panel, Mapping) else None,
            "sampler": dict(sampler) if isinstance(sampler, Mapping) else None,
        },
        "research_scope": {
            "classes": research_classes,
            "evidence_pending": [cid for cid in research_classes
                                 if verdicts.get(cid) != CLASS_RELIABLE],
            "note": ("研究范围内的类**允许**尚未验证（这正是研究的目的）；"
                     "它们不得被写成已有结论。"),
        },
        "claim_scope": {
            "classes": claim_classes,
            "kinds": claim_kinds,
            "class_verdicts": {cid: verdicts.get(cid) for cid in claim_classes},
            "note": "结论范围只允许落在逐类判定为 reliable 的类上，且种类限于 behavior / conditional_effect。",
        },
        "perclass_status": perclass.get("status") if perclass_ok else None,
        "gate_failures": failures,
        "not_admission_basis": True,
        "boundaries": [
            "研究执行资格**不是**发布准入，也不是效果结论（PHASE3-RULE-AWARE §4.4）。",
            "条件结果只落条件效应，不外推整体积分或实际赛事发生率。",
            "构造触发集上只能研究行为，不得声明条件效果或准入。",
            "研究记录必须与候选/面板/采样器身份一起引用；身份不符即作废。",
        ],
        "note": ("拒绝路径**先于**执行：refusals 非空即 permitted=False，"
                 "且本记录永不带准入结论。"),
    }


def verify_research_record(record: Mapping[str, Any]) -> List[str]:
    """校验一份研究记录**不得**被读成准入（下游扫描器与负例测试共用）。

    判据是"读到它的人会不会误判"，因此逐条检查：
      · schema/版本必须是研究记录；
      · `admitted` 与 `gate_level_admitted` 必须是 `False`（**不是缺省、不是 None**）；
      · `evidence_kind` 不得是 `admission`；
      · `permitted` 必须与 `refusals` 一致（拒绝过就不许说能执行）；
      · 许可执行时，结论范围里的每个类必须带着 `reliable` 的逐类判定；
      · 身份与范围齐备。
    返回问题列表；空列表 = 可以按"研究执行"读，且**不能**按准入读。
    """

    problems: List[str] = []
    if not isinstance(record, Mapping):
        return ["研究记录不是映射：不可读作任何结论"]
    if record.get("schema") != RESEARCH_SCHEMA:
        problems.append("schema 不是 {0}".format(RESEARCH_SCHEMA))
    if record.get("entry_version") != RESEARCH_ENTRY_VERSION:
        problems.append("entry_version 不是 {0}".format(RESEARCH_ENTRY_VERSION))
    if record.get("admitted") is not False:
        problems.append("admitted 必须是 False（研究记录不得携带准入结论）")
    if record.get("gate_level_admitted") is not False:
        problems.append("gate_level_admitted 必须是 False")
    if record.get("evidence_kind") != "research":
        problems.append("evidence_kind 必须是 research，得到 {0!r}".format(record.get("evidence_kind")))
    refusals = list(record.get("refusals") or ())
    if bool(record.get("permitted")) is bool(refusals):
        problems.append("permitted 与 refusals 不一致：有拒绝理由就不许说能执行")
    identities = record.get("identities")
    if not isinstance(identities, Mapping):
        problems.append("缺少 identities（候选/面板/采样器身份）")
    else:
        if not identities.get("candidate_bound_identity"):
            problems.append("缺少候选绑定身份")
        for key in ("panel", "sampler"):
            if not isinstance(identities.get(key), Mapping):
                problems.append("缺少 {0} 身份".format(key))
    claim = record.get("claim_scope")
    if not isinstance(claim, Mapping):
        problems.append("缺少 claim_scope（结论范围）")
    elif record.get("permitted"):
        for cid, verdict in (claim.get("class_verdicts") or {}).items():
            if verdict != CLASS_RELIABLE:
                problems.append("结论类 {0} 的判定是 {1!r}，不是 reliable".format(cid, verdict))
    if not isinstance(record.get("research_scope"), Mapping):
        problems.append("缺少 research_scope（研究范围）")
    return problems


G3_REQUIRED_FIELDS: Tuple[str, ...] = (
    "candidate", "trigger", "changed_actions", "expected_direction", "counterexample",
)


def gate_g3(candidate_name: str, registration: Optional[Mapping[str, Any]], *,
            prepared: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
    """G-3：候选的机制说明与记账必须齐备；缺触发条件不得进队列。"""

    problems: List[str] = []
    if registration is None:
        problems.append("候选 {0} 没有登记记录".format(candidate_name))
        return {"gate": "G-3 评估记账", "status": "FAIL", "problems": problems,
                "detail": {}}
    # R7-9：初版用 `str(value).strip()`，于是 JSON 的 `null`/`[]`/`{}`/`false`
    # 都被当成"非空文字"通过。必须校验**类型与实际内容**。
    missing = []
    for field in G3_REQUIRED_FIELDS:
        value = registration.get(field, None)
        if isinstance(value, str):
            ok = bool(value.strip())
        elif isinstance(value, (list, tuple)):
            ok = len(value) > 0 and all(isinstance(x, str) and x.strip() for x in value)
        elif isinstance(value, Mapping):
            ok = len(value) > 0
        else:
            # None / bool / 数值都不是合法的机制说明。
            ok = False
        if not ok:
            missing.append(field)
    if missing:
        problems.append("登记记录字段缺失、为空或类型非法：{0}".format(missing))
    if str(registration.get("candidate")) != candidate_name:
        problems.append("登记记录的候选名与请求不一致")
    # 候选自身声明的触发条件也必须存在（双重保险：代码与登记可能漂移）。
    # **构造已在 G-0 的隔离进程里做过**（REVIEW-9）：这里只读它的结果，
    # 不再在父进程导入注册表、也不再次执行候选代码。
    if prepared is not None:
        spec = prepared.get("adjustment_spec") or {}
        if not str(spec.get("trigger") or "").strip():
            problems.append("候选 spec.trigger 为空")
    else:
        try:
            policy = heuristics.build_candidate(candidate_name)
            if not policy.adjustment.spec.trigger.strip():
                problems.append("候选 spec.trigger 为空")
        except Exception as exc:
            problems.append("无法构造候选：{0}".format(exc))
    return {"gate": "G-3 评估记账", "status": "PASS" if not problems else "FAIL",
            "problems": problems, "detail": dict(registration)}


def _registration_for(registrations: Mapping[str, Any],
                     candidate_name: str) -> Optional[Mapping[str, Any]]:
    """取候选的 G-3 登记记录；接受两种文件形状。

    - 直接映射：`{"候选名": {...}}`
    - 带封装：`{"schema": ..., "candidates": {"候选名": {...}}}`
    """

    if not isinstance(registrations, Mapping):
        return None
    nested = registrations.get("candidates")
    if isinstance(nested, Mapping):
        return nested.get(candidate_name)
    entry = registrations.get(candidate_name)
    return entry if isinstance(entry, Mapping) else None


def corpus_identity(path: Path, rows: int, *, constructed: bool) -> Dict[str, Any]:
    """语料的**身份**：内容哈希 + 行数 + 是否构造集。

    R7-1 的剩余缺口就在这里：初版记录里写了 `corpus`（路径 + 行数），
    但调度器核验准入时**一个字段都没读**——于是换一份语料重跑，
    旧记录照样放行；身份里也没有任何东西会因为语料变化而失效。
    路径字符串不能当身份（同一路径可以换成另一份内容），必须按**字节**取哈希。
    """

    import hashlib

    from_path = Path(path)
    data = from_path.read_bytes()
    identity = {
        "path": str(path),
        "rows": int(rows),
        "sha256": hashlib.sha256(data).hexdigest(),
        "bytes": len(data),
        "constructed_trigger_set": bool(constructed),
    }
    # 语料清单：身份 = 清单自身的哈希（清单里逐文件带 sha256）＋ 选择规则摘要。
    manifest = corpus_manifest(from_path)
    if manifest is not None:
        identity["manifest"] = {
            "schema": manifest.get("schema"),
            "files": len(manifest.get("files", ())),
            "rows": manifest.get("rows"),
            "row_cap": manifest.get("row_cap"),
            "selection_rule": manifest.get("selection_rule"),
            "frozen_before_run": manifest.get("frozen_before_run"),
        }
    return identity


#: **语料清单**（多文件面板）的 schema。它把"选中的语料"变成可复核的清单，
#: 而不是一个路径字符串：清单逐文件给出 路径 + 行数 + sha256 + 累计行数，
#: 任何一份文件换掉都会改清单内容，从而改 `corpus_identity`。
#: **为什么不用"拼成一个大文件"**：新语料家族 36 万行 / 7.9 GB，拼文件既吃内存又不进 git。
CORPUS_MANIFEST_SCHEMA = "sitin-corpus-manifest/1"


def corpus_manifest(path: Path) -> Optional[Dict[str, Any]]:
    """输入路径是语料清单（JSON）时返回清单内容，否则返回 None。"""

    candidate = Path(path)
    if candidate.suffix != ".json" or not candidate.is_file():
        return None
    try:
        data = json.loads(candidate.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(data, Mapping) or data.get("schema") != CORPUS_MANIFEST_SCHEMA:
        return None
    return dict(data)


def manifest_files(manifest: Mapping[str, Any]) -> List[Path]:
    """清单里的文件（相对路径按仓库根解析；**顺序即读取顺序**）。"""

    out: List[Path] = []
    for entry in manifest.get("files", ()):
        item = entry.get("path") if isinstance(entry, Mapping) else entry
        resolved = Path(str(item))
        out.append(resolved if resolved.is_absolute() else (_project_file(_PROJECT_ROOT, REPO / resolved)))
    return out


def resolve_record_layer(path: Path, requested: Optional[str] = None) -> str:
    """解析记录层视图：显式参数优先 → 语料清单声明的视图 → raw。

    canonical 面板在清单里声明 `record_layer: filled`（记录层归一化后），因此调用方
    **不必**记着加参数也不会读错视图；显式传入不同视图仍然允许（前后对比正是这么用的）。
    """

    manifest = corpus_manifest(path)
    declared = manifest.get("record_layer") if isinstance(manifest, Mapping) else None
    if requested in (SCENARIO_RECORD_LAYER_RAW, SCENARIO_RECORD_LAYER_FILLED):
        return str(requested)
    if declared in (SCENARIO_RECORD_LAYER_RAW, SCENARIO_RECORD_LAYER_FILLED):
        return str(declared)
    return SCENARIO_RECORD_LAYER_RAW


def iter_corpus(path: Path, limit: Optional[int] = None):
    """**惰性**遍历语料（每次只持有一行）；清单输入按其文件顺序展开。

    与 load_corpus 同一份读取口径（同一清单语义），区别只是**不物化**：
    canonical 面板 359,262 行全物化约 28 GB（实测 82 KB/行），逐类判定因此走本入口。
    """

    manifest = corpus_manifest(path)
    files = manifest_files(manifest) if manifest is not None else [Path(path)]
    seen = 0
    for item in files:
        with Path(item).open(encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                yield json.loads(line)
                seen += 1
                if limit is not None and seen >= limit:
                    return


def load_corpus(path: Path, limit: Optional[int] = None) -> List[dict]:
    """读取 JSONL 语料；输入也可以是**语料清单**（见 CORPUS_MANIFEST_SCHEMA）。

    `limit` 是**计分窗口总数的上限**，跨文件累计（清单里每个文件都是完整一局，
    中途截断只发生在调用方显式要求 limit 时；本工具的清单选择规则按"整份文件"取，
    因此正常情况下 limit=None，不截断任何一局）。
    """

    manifest = corpus_manifest(path)
    files = manifest_files(manifest) if manifest is not None else [Path(path)]
    rows: List[dict] = []
    for item in files:
        with Path(item).open(encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                rows.append(json.loads(line))
                if limit is not None and len(rows) >= limit:
                    return rows
    return rows


def build_g1_windows(rows: Sequence[Mapping[str, Any]], ruleset: str = "v26",
                     limit: int = 40, require_kinds: Sequence[str] = (),
                     scan_cap: int = 20000) -> Tuple[List[Any], List[Any]]:
    """从语料里挑出可用于 G-1 的窗口（重算后完整、有合法候选）。

    `require_kinds` 非空时**只收候选真正会触发的窗口**（S7-1）：
    初版把前 40 个窗口一股脑拿去计时，而其中往往只有 2 个含吃碰候选，
    于是 p99 量的是噪声、唯一最慢的窗口被排序下标排除。筛选后
    `limit` 表示"要收集多少个**已触发**窗口"，`scan_cap` 限制扫描深度。
    """

    wanted = set(require_kinds)

    codec = build_decision_codec()
    decode_request, decode_budget = codec["decode_request"], codec["decode_budget"]
    rules = HangmaRules(RuleConfig(ruleset_version=ruleset, base_score=1,
                                   you_cai_bi_kao=False))
    requests: List[Any] = []
    budgets: List[Any] = []
    scanned = 0
    for row in rows:
        payload = row.get("request")
        if not isinstance(payload, Mapping):
            continue
        try:
            recorded = decode_request(payload)
            budget = translate_budget(
                decode_budget(row.get("budget"), row.get("budget_origin_monotonic", 0.0)),
                row.get("budget_origin_monotonic", 0.0), 100.0)
            analysis = rules.analyze(recorded.observation)
        except Exception:
            continue
        if analysis.completeness is RuleCompleteness.DEGRADED or not analysis.legal_candidates:
            continue
        if wanted and not any(recompute._kind(c.action_key) in wanted
                              for c in analysis.legal_candidates):
            scanned += 1
            if scanned >= scan_cap:
                break
            continue
        requests.append(DecisionRequest(
            observation=recorded.observation, competition=recorded.competition,
            rules=analysis, decision_id=recorded.decision_id,
            trigger_seq=recorded.trigger_seq, window_key=recorded.window_key,
            rejected_attempts=()))
        budgets.append(budget)
        if len(requests) >= limit:
            break
        scanned += 1
        if scanned >= scan_cap:
            break
    return requests, budgets


def looks_like_trigger_set(rows: Sequence[Mapping[str, Any]]) -> bool:
    """语料是否由 `sitin_trigger_windows.py` 生成（构造集）。

    判据是行里带 `trigger_grid` 标记，**由生成器写入**，不是靠文件名猜。
    用途：防止"在构造集上跑出的 PASS"被当成准入证据落盘。
    """

    # **必须全量扫描**（2026-09-15 独立复核撞出）：初版只看 `rows[:50]`，
    # 于是"标记只出现在第 51 行之后"或"删掉前 50 行的标记"就能绕过屏障 1。
    # 行数在本工具的量级（数千）下全扫的成本可以忽略。
    return any(isinstance(row.get("trigger_grid"), Mapping) for row in rows)


#: 受监管执行的墙钟上限（REVIEW-8 S8-2）。口径是"拦住不会自己结束的运行"，
#: 而不是性能门禁：实测整条门禁命令约 5 秒，这里给到约 60 倍余量，
#: 且可由 `--gate-timeout-sec` 覆盖。
GATE_G1_TIMEOUT_SEC = 300.0
GATE_G2_TIMEOUT_SEC = 600.0
#: G-2C 逐类覆盖：与 G-2 同量级（同一份面板上多一遍分类与逐候选统计）。
GATE_G2C_TIMEOUT_SEC = 600.0
#: SIGTERM 之后的无条件 SIGKILL 宽限。
GATE_TERM_GRACE_SEC = 5.0

#: 隔离执行的 check 名 → 对外门禁名（**单一来源**：受监管入口与内部入口共用）。
_GATE_LABELS: Mapping[str, str] = {
    "g1": "G-1 时间与纯度",
    "g2": "G-2 退化检测",
    "g2c": G2C_GATE_LABEL,
}


def _report_without_gates(candidate_name: str, weights: Mapping[str, float],
                          corpus: Path, rows: int, constructed: bool,
                          evidence_kind: str, gate0: Dict[str, Any]) -> Dict[str, Any]:
    """装载/构造失败时的记录：**只有 G-0，且它 FAIL**。

    后面三道门没有运行——"没跑"绝不能写成"通过"（R7-8 的同一条纪律）。
    `bound_identity` 留空而不是现算：现算要导入注册表，而导入正是刚刚失败的那一步。
    """

    return {
        "schema": "sitin-gates/1",
        "evidence_kind": evidence_kind,
        "gate_level_admitted": False,
        "constructed_trigger_set": constructed,
        "candidate": candidate_name,
        "weights": dict(weights),
        "candidate_identity": None,
        "bound_identity": None,
        "weights_effective": dict(weights),
        "gates": [gate0],
        "all_pass": False,
        "admitted": False,
        "failed": [gate0["gate"]],
        "insufficient": [],
        "corpus": corpus_identity(corpus, rows, constructed=constructed),
        "note": ("装载/构造未完成，其余门禁**没有运行**；"
                 "本条记录不构成任何准入依据"),
    }


def _isolated_failure(label: str, reason: str, result: Any = None) -> Dict[str, Any]:
    """隔离执行失败时的门禁结果：**FAIL**，不是"证据不足"，也不是静默排除。

    候选执行不会自己结束时，"没测到"与"测到它不停"是两件事：后者是**确定的坏事**。
    """

    detail: Dict[str, Any] = {"supervised": True, "reason": reason}
    if result is not None:
        detail["execution"] = result.to_json()
    return {"gate": label, "status": "FAIL", "problems": [reason], "notes": [],
            "detail": detail}


#: 装载与构造的墙钟上限（REVIEW-9「装载/构造也有界执行」）。
#: 口径同样是"拦住不会自己结束的运行"：正常候选的导入加构造在毫秒级。
GATE_PREPARE_TIMEOUT_SEC = 60.0


def supervised_prepare(candidate_name: str, weights: Mapping[str, float], *,
                       timeout_sec: Optional[float] = None) -> Dict[str, Any]:
    """在**隔离进程**里完成候选的**装载与构造**，返回身份与作用面。

    **为什么连装载也要隔离**：`policy.heuristics.__init__` 会 import 全部已注册候选模块，
    候选的**模块体**与**构造参数**都是候选作者写的代码。初版这些都在调用方进程里跑，
    一个在模块体里挂住的候选会让整个调度器/门禁**在被拒绝之前就挂死**。

    返回始终带 `ok`：
      - 成功：`bound_identity` / `adjustment_identity` / `adjustment_spec` /
        `params` / `base` / `scope` / `source_sha256` / `dependency_digest` + `execution`；
      - 失败：`ok=False` 与 `reason`，另附 `execution`（受监管结局）。
    调用方据此**在扣预算之前**拒绝，而不是把候选代码放进自己进程再祈祷它不挂。
    """

    import tempfile

    # `is not None` 而不是真值判断：0 是合法的"立刻到期"，测试用它走终止路径。
    limit = float(timeout_sec) if timeout_sec is not None else GATE_PREPARE_TIMEOUT_SEC
    workdir = Path(tempfile.mkdtemp(prefix="sitin-prepare-"))
    out_path = workdir / "prepare.json"
    command = [sys.executable, str(Path(__file__).resolve()),
               "--internal-prepare",
               "--candidate", candidate_name,
               "--weights", json.dumps(dict(weights)),
               "--out", str(out_path)]
    result = process_guard.run_supervised(command, cwd=REPO, timeout_sec=limit,
                                          grace_sec=GATE_TERM_GRACE_SEC)
    if result.timed_out:
        return {"ok": False,
                "reason": "装载/构造超时：{0} 秒内未结束，已终止进程组（信号 {1}）".format(
                    limit, "+".join(result.signals_sent) or "无"),
                "execution": result.to_json()}
    if result.returncode != 0 or not out_path.is_file():
        tail = result.stderr.strip().splitlines()[-1][:200] if result.stderr.strip() else ""
        return {"ok": False,
                "reason": "装载/构造未产出结果：returncode={0}{1}".format(
                    result.returncode, "；stderr 尾部：" + tail if tail else ""),
                "execution": result.to_json()}
    try:
        payload = json.loads(out_path.read_text(encoding="utf-8"))
    except Exception as exc:                       # noqa: BLE001 —— 解析失败同样是失败
        return {"ok": False, "reason": "装载/构造结果不可解析：{0}".format(exc),
                "execution": result.to_json()}
    payload["ok"] = True
    payload["execution"] = result.to_json()
    return payload


def supervised_gate(check: str, candidate_name: str, weights: Mapping[str, float],
                    corpus: Path, *, timeout_sec: Optional[float] = None,
                    corpus_limit: Optional[int] = None,
                    g1_limit: Optional[int] = None,
                    record_layer: str = SCENARIO_RECORD_LAYER_RAW) -> Dict[str, Any]:
    """在**隔离进程**里跑一道门禁，父进程强制执行墙钟上限与进程组终止。

    **为什么门禁必须隔离（REVIEW-8 S8-2）**：门禁跑的是"离线生成的任意候选代码"。
    初版在当前进程直接执行：注入一个纯计算 `while True` 后，G-1 **无法返回**，
    审查探针是靠**额外**加的外部两秒监管才把它清掉的；同步计算卡住时，
    后面的真实时钟检查根本没有执行机会。G-2 同样直接执行，一并纳入本入口。
    """

    import tempfile

    if check not in _GATE_LABELS:
        raise ValueError("未知的门禁 check：{0!r}（允许：{1}）".format(
            check, sorted(_GATE_LABELS)))
    label = _GATE_LABELS[check]
    default_limit = {"g1": GATE_G1_TIMEOUT_SEC, "g2": GATE_G2_TIMEOUT_SEC,
                     "g2c": GATE_G2C_TIMEOUT_SEC}[check]
    # `is not None` 而不是真值判断：0 是**合法**的"立刻到期"，测试用它走终止路径。
    limit = float(timeout_sec) if timeout_sec is not None else default_limit
    workdir = Path(tempfile.mkdtemp(prefix="sitin-gate-{0}-".format(check)))
    out_path = workdir / "gate.json"
    command = [sys.executable, str(Path(__file__).resolve()),
               "--internal-gate", check,
               "--candidate", candidate_name,
               "--weights", json.dumps(dict(weights)),
               "--corpus", str(corpus),
               "--out", str(out_path)]
    if corpus_limit is not None:
        command += ["--corpus-limit", str(int(corpus_limit))]
    if g1_limit is not None:
        command += ["--g1-limit", str(int(g1_limit))]
    # 记录层视图**必须在父进程解析成具体取值**（None = 交给清单声明/退回 raw）：
    # 直接把 None 传给子进程会让 argparse 以 invalid choice 退出（本轮实测踩到过一次）。
    command += ["--record-layer", resolve_record_layer(corpus, record_layer)]
    result = process_guard.run_supervised(command, cwd=REPO, timeout_sec=limit,
                                          grace_sec=GATE_TERM_GRACE_SEC)
    if result.timed_out:
        return _isolated_failure(
            label,
            "隔离执行超时：{0} 秒内未结束，已终止进程组（信号 {1}）".format(
                limit, "+".join(result.signals_sent) or "无"), result)
    if result.returncode != 0 or not out_path.is_file():
        tail = result.stderr.strip().splitlines()[-1][:200] if result.stderr.strip() else ""
        return _isolated_failure(
            label, "隔离执行未产出结果：returncode={0}{1}".format(
                result.returncode, "；stderr 尾部：" + tail if tail else ""), result)
    try:
        report = json.loads(out_path.read_text(encoding="utf-8"))
    except Exception as exc:                       # noqa: BLE001 —— 解析失败同样是 FAIL
        return _isolated_failure(label, "隔离执行结果不可解析：{0}".format(exc), result)
    detail = report.setdefault("detail", {})
    detail["supervised"] = True
    detail["supervision"] = result.to_json()
    return report


def run_all(candidate_name: str, weights: Mapping[str, float], corpus: Path,
            registrations: Mapping[str, Any], *, corpus_limit: Optional[int] = None,
            g1_limit: int = 40, evidence_kind: str = "admission",
            g1_timeout_sec: Optional[float] = None,
            g2_timeout_sec: Optional[float] = None,
            prepare_timeout_sec: Optional[float] = None,
            perclass: bool = False,
            g2c_timeout_sec: Optional[float] = None,
            record_layer: str = SCENARIO_RECORD_LAYER_RAW) -> Dict[str, Any]:
    """跑三道门禁并产出记录。

    `evidence_kind`（2026-09-15 新增）：`admission` = 真实语料，可作准入依据；
    `trigger` = 构造触发集，**只证明接线与可触发面，永不产生准入资格**。

    **两道独立屏障**（缺一不可，二者都由"触发集 PASS 被误当准入"这次事故驱动）：
      ① 语料自带 `trigger_grid` 标记而 `evidence_kind` 仍是 `admission` ⇒ **拒绝出记录**；
      ② 即使写了 `trigger` 记录，`admitted` 也恒为 `False`（门禁级结论另存
         `gate_level_admitted`）。
    """

    if evidence_kind not in ("admission", "trigger"):
        raise ValueError("evidence_kind 必须是 admission 或 trigger，得到 {0!r}".format(
            evidence_kind))
    rows = load_corpus(corpus, corpus_limit)
    constructed = looks_like_trigger_set(rows)
    if constructed and evidence_kind == "admission":
        raise ValueError(
            "该语料是**构造触发集**（行内带 trigger_grid 标记），不能作为准入证据；"
            "请用 --evidence-kind trigger，或换真实语料。")
    # **G-0 装载与构造（受监管）**（REVIEW-9）：注册表导入、候选模块体与按参数构造
    # 都是候选作者写的代码。初版把它们放在调用方进程里，于是"在模块体里挂住"的候选
    # 会让门禁/调度器**在被拒绝之前就挂死**。现在父进程不执行任何候选代码。
    prepared = supervised_prepare(candidate_name, weights, timeout_sec=prepare_timeout_sec)
    if not prepared["ok"]:
        g0 = {"gate": "G-0 装载与构造", "status": "FAIL",
              "problems": [prepared["reason"]], "notes": [],
              "detail": {"supervised": True, "execution": prepared.get("execution")}}
    else:
        g0 = {"gate": "G-0 装载与构造", "status": "PASS", "problems": [], "notes": [],
              "detail": {"supervised": True,
                         "bound_identity": prepared.get("bound_identity"),
                         "scope": prepared.get("scope"),
                         "dependency_digest": prepared.get("dependency_digest"),
                         "execution": prepared.get("execution")}}
    if not prepared["ok"]:
        # 装载都过不了：后面三道门**没有跑**，不能假装它们通过。
        return _report_without_gates(
            candidate_name, weights, corpus, len(rows), constructed, evidence_kind, g0)
    # 绑定身份来自**受监管的装载**（与调度器核验的是同一个值，R7-1/S8-1）。
    bound_identity = prepared["bound_identity"]
    # **G-1/G-2 跑在受监管的隔离进程里**（REVIEW-8 S8-2）：候选是"离线生成的
    # 任意代码"，在当前进程直接执行时，一个纯计算死循环会把门禁本身挂住——
    # 连它自己的"真实时钟检查"都没有执行机会。合成一个隔离入口后，
    # 墙钟上限与进程组终止由父进程强制执行，且与桌赛执行**共用同一个实现**。
    g1 = supervised_gate("g1", candidate_name, weights, corpus, timeout_sec=g1_timeout_sec,
                         corpus_limit=corpus_limit, g1_limit=g1_limit)
    g2 = supervised_gate("g2", candidate_name, weights, corpus, timeout_sec=g2_timeout_sec,
                         corpus_limit=corpus_limit)
    g3 = gate_g3(candidate_name, _registration_for(registrations, candidate_name),
                 prepared=prepared)
    # 3.6b 逐类覆盖（G-2C）：**独立段，不进 gates**。
    # 理由：进了 gates 就会改 all_pass/admitted 的含义，而"旧 admitted 含义不变"是硬要求；
    # 且覆盖 INSUFFICIENT **不等于**不安全（PHASE3-RULE-AWARE §4.4）。
    g2c = None
    if perclass:
        g2c = supervised_gate("g2c", candidate_name, weights, corpus,
                              timeout_sec=g2c_timeout_sec, corpus_limit=corpus_limit,
                              record_layer=record_layer)
    gates = [g0, g1, g2, g3]
    # 只有 PASS 才算通过；INSUFFICIENT（证据不足）**不等于通过**（R7-8）。
    failed = [g["gate"] for g in gates if g["status"] == "FAIL"]
    insufficient = [g["gate"] for g in gates if g["status"] == "INSUFFICIENT"]
    gate_level_admitted = not failed and not insufficient
    # 构造触发集**永不给准入资格**：门禁级结论另存，`admitted` 才是执行前置条件。
    admitted = gate_level_admitted and evidence_kind == "admission"
    return {
        "schema": "sitin-gates/1",
        "evidence_kind": evidence_kind,
        "gate_level_admitted": gate_level_admitted,
        "constructed_trigger_set": constructed,
        "candidate": candidate_name,
        "weights": dict(weights),
        # 身份同样取**受监管装载**的结果（3.P 核验发现的残留路径）：这里再构造一次候选，
        # 等于把"候选构造"重新放回父进程——一个在构造或模块体里挂住的候选会让门禁
        # 在拿到 G-0 PASS 之后**卡死在父进程**，正是 G-0 要消灭的那件事。
        # adjustment_identity 与父进程现算的值同源同式（同一个 build_candidate + identity），
        # 因此产物字段一字不变，变的只是"在哪个进程里算"。
        "candidate_identity": prepared["adjustment_identity"],
        "bound_identity": bound_identity,   # 调度器核验用的绑定键
        "weights_effective": dict(weights),
        "gates": gates,
        # 两个布尔值必须分开，否则"三门都 PASS"与"可以执行"会被混成一个（Spec ②）：
        #   all_pass —— 门禁级结论：三态里不存在 FAIL 且不存在 INSUFFICIENT；
        #   admitted —— **可执行**：all_pass **且** 证据种类是真实语料。
        # 触发集上三门全 PASS 时 all_pass=True 而 admitted=False，这是**有意**的。
        "all_pass": gate_level_admitted,
        "admitted": admitted,
        "failed": failed,
        "insufficient": insufficient,
        # 3.6b：逐类覆盖判定（G-2C）。**独立段**：不参与 all_pass / admitted。
        # 未开启时显式写 None 并注明"没跑不等于通过"（R7-8 的同一条纪律）。
        "perclass": g2c,
        "perclass_note": ("G-2C 逐类覆盖：只回答「候选自己声明的每个场景类在本面板上被验证到什么"
                          "程度」，不参与 admitted/all_pass。未开启时本段为 null —— "
                          "**没跑不等于通过**。"),
        # 语料身份进记录**并被调度器核验**（R7-1 剩余项）：换语料 ⇒ 记录失效。
        "corpus": corpus_identity(corpus, len(rows), constructed=constructed),
        "note": "门禁只做准入，不作排序；G-2 输出禁止用于适应度（README §4.2）",
    }


# ============================================================
# 5. action_value_v1 门禁（SEARCH-SPACE-REDESIGN-2026-09-16 §6.2，v4）
#
# 旧 G-0/G-1/G-2/G-2C/G-3 与 research 记录**语义原义不动**；本节是新候选
# 种类 action_value_v1 的独立门禁，写独立 schema sitin-action-value-admission/1
# （独立记录文件），不重解释旧 admitted。静态检查/插桩/计费与 B2 进程内
# 执行器共用同一实现（import 自 action_value_executor，单一来源不复制）；
# 候选装载与执行一律经 sitin_process.run_supervised 在工作子进程完成
# （静态检查通过不免除隔离；工作进程不注入凭据、到期终止进程组）。
# ============================================================

#: 新门禁记录 schema（合同 admission_record_schema）。
AV_ADMISSION_SCHEMA = "sitin-action-value-admission/1"
#: 新候选种类（合同 candidate_kind）。
AV_CANDIDATE_KIND = "action_value_v1"
#: 机器合同路径：白名单/限额/禁令/输出合同的唯一来源（与生成端同源）。
AV_CONTRACT_PATH = (_project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/contracts/action-value-v1.json'))
#: 全机工作进程上限（§11 起始 12；调度层检查，第 13 个并发请求拒绝）。
AV_MAX_WORKERS = 12
#: 整链计时检查保留的固定网络余量（毫秒；§6.2）。
AV_NETWORK_MARGIN_MS = 120.0
#: 单次受监管执行缺省墙钟上限（秒）。
AV_EXEC_TIMEOUT_SEC = 60.0
#: 整链计时缺省重复次数（p50/p95/p99/max 的样本量）。
AV_TIMING_REPEATS = 12

AV_ADMISSION_NOTE = ("执行安全/覆盖/受控研究资格三种检查分开报告；本记录不等于发布准入，"
                     "效果层由 evaluate-action-value 的真实双臂结果评价，发布层需独立确认与人工审核")

_AV_MODULES: Dict[str, Any] = {}
_AV_CONTRACT_CACHE: Dict[str, Tuple[Dict[str, Any], str]] = {}


def _av_module(dotted: str) -> Any:
    """惰性导入 B2 模块（与 heuristics_registry 同一条纪律：导入推迟到调用点）。"""

    if dotted not in _AV_MODULES:
        import importlib
        _AV_MODULES[dotted] = importlib.import_module(dotted)
    return _AV_MODULES[dotted]


def av_contract(path: Optional[Path] = None) -> Tuple[Dict[str, Any], str]:
    """读机器合同 action-value-v1.json；返回 (合同字典, 文件 sha256)。

    白名单/限额/禁令/输出合同全部从这里读——本模块与生成端
    sitin_generate.render_action_value_task_contract 同源，不手抄第二套。
    """

    target = Path(path) if path is not None else AV_CONTRACT_PATH
    key = str(target)
    if key not in _AV_CONTRACT_CACHE:
        raw = target.read_bytes()
        _AV_CONTRACT_CACHE[key] = (json.loads(raw.decode("utf-8")),
                                   hashlib.sha256(raw).hexdigest())
    return _AV_CONTRACT_CACHE[key]


def av_first_party_contents() -> Dict[str, str]:
    """读取实际第一方文件内容（S4 修复：身份绑定实际实现，不是字段摘要）。

    清单单一来源是 executor.FIRST_PARTY_DIGEST_MODULES（类型/投影/策略
    接线/种子/规则事实接口），另含机器合同 JSON 全文。任何文件的方法体
    改动都会改变内容，从而使 candidate_id 与旧准入记录失效（T07）。
    读文件只发生在离线装配层；纯策略层（action_value_executor）无文件副作用。
    """
    import importlib.util

    executor = _av_module("hangma_bot.policy.action_value_executor")
    contents: Dict[str, str] = {}
    for dotted in executor.FIRST_PARTY_DIGEST_MODULES:
        spec = importlib.util.find_spec(dotted)
        if spec is None or not spec.origin:
            raise RuntimeError("第一方依赖模块不可导入：{0}".format(dotted))
        contents[dotted] = Path(spec.origin).read_text(encoding="utf-8")
    contents["contract:action-value-v1.json"] = AV_CONTRACT_PATH.read_text(
        encoding="utf-8")
    return contents


def av_deps_digest(contents: Optional[Mapping[str, str]] = None) -> str:
    """deps_digest 单一计算入口：默认注入实际第一方文件内容摘要（S4）。"""
    executor = _av_module("hangma_bot.policy.action_value_executor")
    material = contents if contents is not None else av_first_party_contents()
    return executor.compute_deps_digest(material)


def av_default_identity_params() -> Dict[str, Any]:
    """身份缺省参数：绑定实际分析配置（S4：身份另含实际 ValueAnalysisLimits）。"""
    interface = _av_module("hangma_bot.hangma.interface")
    limits = interface.ValueAnalysisLimits()
    return {"value_analysis_limits": {
        "max_expansions": limits.max_expansions,
        "max_routes_per_candidate": limits.max_routes_per_candidate}}


def av_candidate_identity(candidate_source: str, *,
                          contract_sha256: Optional[str] = None,
                          executor_version: Optional[str] = None,
                          params: Optional[Mapping[str, Any]] = None,
                          execution_profile: Any = None) -> str:
    """按合同 identity.candidate_id_inputs 计算 candidate_id（B2 单一实现）。

    executor_version/contract_sha256 可显式覆盖（T07：依赖改动使身份失效的
    对账测试用）；生产路径缺省取当前执行器、当前合同、实际第一方文件
    内容摘要（S4）与实际分析配置。
    """

    executor = _av_module("hangma_bot.policy.action_value_executor")
    _, digest = av_contract()
    return executor.compute_candidate_identity(
        candidate_source,
        contract_sha256 if contract_sha256 is not None else digest,
        execution_profiles.identity_params(
            params if params is not None else av_default_identity_params(), execution_profile),
        executor_version or executor.EXECUTOR_VERSION,
        av_deps_digest())


def av_identity_binding(candidate_source: str, *,
                        contract_sha256: Optional[str] = None,
                        executor_version: Optional[str] = None,
                        params: Optional[Mapping[str, Any]] = None,
                        execution_profile: Any = None) -> Dict[str, Any]:
    """候选与全部身份输入的绑定块（进入门禁记录，供恢复/续写逐项核验）。"""

    executor = _av_module("hangma_bot.policy.action_value_executor")
    _, digest = av_contract()
    return {
        "candidate_kind": AV_CANDIDATE_KIND,
        "candidate_source_sha256": hashlib.sha256(
            candidate_source.encode("utf-8")).hexdigest(),
        "candidate_id": av_candidate_identity(
            candidate_source, contract_sha256=contract_sha256,
            executor_version=executor_version, params=params, execution_profile=execution_profile),
        "contract_sha256": contract_sha256 if contract_sha256 is not None else digest,
        "executor_version": (executor_version or executor.EXECUTOR_VERSION),
        "deps_digest": av_deps_digest(),
        "deps_digest_basis": "first_party_file_contents(S4)",
        "params": execution_profiles.identity_params(
            params if params is not None else av_default_identity_params(), execution_profile),
        "candidate_id_inputs": (av_contract()[0].get("identity", {})
                                .get("candidate_id_inputs", [])),
    }


def av_record_identity_matches(record: Mapping[str, Any],
                               candidate_source: str, *, execution_profile: Any = None) -> Tuple[bool, str]:
    """核验一份门禁记录是否放行**这份**候选源码；任何不符拒绝（T07）。

    - 只认 schema == sitin-action-value-admission/1：旧 delta 的
      sitin-gates/1（含 admitted=true）显式拒绝，不冒充新准入；
    - candidate_id / contract_sha256 / executor_version / deps_digest /
      candidate_source_sha256 逐项重算比对；依赖改动使身份失效。
    """

    if not isinstance(record, Mapping):
        return False, "记录不是映射"
    schema = record.get("schema")
    if schema != AV_ADMISSION_SCHEMA:
        return False, ("旧 schema {0!r} 不能放行 action_value_v1 候选"
                       "（需 {1}）".format(schema, AV_ADMISSION_SCHEMA))
    binding = record.get("identity") or {}
    if not isinstance(binding, Mapping):
        return False, "记录缺 identity 绑定块"
    try:
        execution_profiles.require_same(record.get("execution_profile"), execution_profile)
        expect = av_identity_binding(candidate_source, execution_profile=execution_profile)
    except ValueError as error:
        return False, str(error)
    for key in ("candidate_id", "contract_sha256", "executor_version",
                "deps_digest", "candidate_source_sha256"):
        if binding.get(key) != expect[key]:
            return False, ("身份字段 {0} 不符（记录 {1}，当前 {2}）："
                           "工具/依赖改动使旧记录失效，拒绝续写".format(
                               key, str(binding.get(key))[:16],
                               str(expect[key])[:16]))
    layers = record.get("layers") or {}
    safety = (layers.get("execution_safety") or {}).get("status")
    if safety != "PASS":
        return False, "记录执行安全层非 PASS（{0}），不放行".format(safety)
    return True, ""


class WorkerCapExceeded(RuntimeError):
    """超出全机工作进程上限（§11：12）的调度请求被拒绝。"""


class AVWorkerSlots:
    """调度层工作进程上限检查（进程内注册表；全机口径由搜索账本另核）。

    上限 AV_MAX_WORKERS=12：请求第 13 个在册槽位即抛 WorkerCapExceeded，
    不静默排队、不扩容。进程内注册表覆盖单调度器并发；跨进程全机口径
    在 sitin_search 的账本里做同一检查（两处同一常量）。
    """

    _active: Dict[str, str] = {}

    def __init__(self, cap: int = AV_MAX_WORKERS) -> None:
        self.cap = int(cap)

    def acquire(self, slot_id: str, note: str = "") -> None:
        if slot_id in AVWorkerSlots._active:
            return
        if len(AVWorkerSlots._active) >= self.cap:
            raise WorkerCapExceeded(
                "工作进程请求被拒绝：在册 {0} 已达全机上限 {1}".format(
                    len(AVWorkerSlots._active), self.cap))
        AVWorkerSlots._active[slot_id] = note or slot_id

    def release(self, slot_id: str) -> None:
        AVWorkerSlots._active.pop(slot_id, None)

    @classmethod
    def active_count(cls) -> int:
        return len(cls._active)

    @classmethod
    def reset_for_test(cls) -> None:
        cls._active.clear()


#: 子进程环境白名单：只透传运行必需变量，**不注入任何凭据**
#: （API key/LLM 配置/DSH 变量一律不进工作子进程）。
_AV_CHILD_ENV_KEYS: Tuple[str, ...] = (
    "PATH", "HOME", "LANG", "LC_CTYPE", "LC_ALL", "TMPDIR", "TMP", "TEMP",
    "PYTHONIOENCODING", "SYSTEMROOT", "SYSTEMDRIVE", "COMSPEC",
)


def av_child_env() -> Dict[str, str]:
    """构造不含凭据的子进程环境（密钥类变量按模式显式剔除）。"""

    import re as _re
    env: Dict[str, str] = {}
    for name in _AV_CHILD_ENV_KEYS:
        value = os.environ.get(name)
        if value is not None:
            env[name] = value
    secret_like = _re.compile(r"(KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL|SITIN_LLM|DSH_)", _re.I)
    return {key: value for key, value in env.items() if not secret_like.search(key)}


# ---------------------------------------------------------------------------
# 5.1 视图夹具（子进程内构造；类型与 B2 build_sample_view 同源）
# ---------------------------------------------------------------------------


def _av_observation():
    seeds = _av_module("hangma_bot.policy.action_value_seeds")
    return seeds.make_sample_observation()


def _av_profile():
    seeds = _av_module("hangma_bot.policy.action_value_seeds")
    return seeds.build_sample_view().analysis_profile


def _av_action_view(action, *, branches=None, progress: str = "UNKNOWN",
                    settlement=None):
    av_mod = _av_module("hangma_bot.policy.action_value")
    actions_mod = _av_module("hangma_bot.kernel.actions")
    types = ((actions_mod.Discard, "discard"), (actions_mod.Chi, "chi"),
             (actions_mod.Peng, "peng"), (actions_mod.Gang, "gang"),
             (actions_mod.Hu, "hu"), (actions_mod.Pass, "pass"))
    action_type = next(name for cls, name in types if isinstance(action, cls))
    return av_mod.ActionView(
        action_key=actions_mod.action_key(action), action=action,
        action_type=action_type, is_legal=True, followup_branches=branches,
        immediate_settlement=settlement, family_progress=progress)


def _av_view(actions, *, reference_features=()):
    av_mod = _av_module("hangma_bot.policy.action_value")
    ordered = tuple(sorted(actions, key=lambda item: item.action_key))
    return av_mod.ScoringView(
        schema_version=av_mod.SCORING_VIEW_SCHEMA_VERSION,
        visible_state=_av_observation(), actions=ordered,
        analysis_profile=_av_profile(),
        reference_features=tuple(reference_features))


def av_view_sample():
    """样例视图（弃牌/胡/过三类；与 seeds.build_sample_view 同一构造）。"""

    seeds = _av_module("hangma_bot.policy.action_value_seeds")
    return seeds.build_sample_view()


def _av_family_views() -> Dict[str, Any]:
    """动作族视图工厂（返回**工厂函数**，与 AV_VIEW_FIXTURES 其余条目同形）。"""

    actions_mod = _av_module("hangma_bot.kernel.actions")

    def fam_discard():
        return _av_view([_av_action_view(actions_mod.Discard(actions_mod.Tile("1w")),
                                        progress="ADVANCE")])

    def fam_chi():
        return _av_view([_av_action_view(
            actions_mod.Chi((actions_mod.Tile("1w"), actions_mod.Tile("2w"),
                             actions_mod.Tile("3w"))), progress="SAME")])

    def fam_peng():
        return _av_view([_av_action_view(actions_mod.Peng(actions_mod.Tile("2w")),
                                        progress="SAME")])

    def fam_gang():
        return _av_view([_av_action_view(
            actions_mod.Gang(actions_mod.Tile("5w"), actions_mod.GangKind.EXPOSED),
            progress="ADVANCE")])

    def fam_hu():
        interface = _av_module("hangma_bot.hangma.interface")
        return _av_view([_av_action_view(
            actions_mod.Hu(), progress="CLOSE",
            settlement=interface.Settlement(
                score_delta=(8, -3, -3, -2), fan=4, details=("fixture",)))])

    def fam_pass():
        return _av_view([_av_action_view(actions_mod.Pass(), progress="SAME")])

    return {
        "fam_discard": fam_discard,
        "fam_chi": fam_chi,
        "fam_peng": fam_peng,
        "fam_gang": fam_gang,
        "fam_hu": fam_hu,
        "fam_pass": fam_pass,
    }


def av_view_route_combo():
    """路线组合视图：WITNESSED/UNANALYZED 两分支并存（覆盖层组合项）。"""

    actions_mod = _av_module("hangma_bot.kernel.actions")
    tile = actions_mod.Tile
    witnessed = ({"followup_key": "discard:1w", "combined_shanten": 1,
                  "support_remaining": 4, "route_status": "WITNESSED"},)
    unanalyzed = ({"followup_key": "discard:2b", "combined_shanten": 2,
                   "support_remaining": None, "route_status": "UNANALYZED"},)
    return _av_view([
        _av_action_view(actions_mod.Discard(tile("1w")), branches=witnessed,
                        progress="ADVANCE"),
        _av_action_view(actions_mod.Discard(tile("2b")), branches=unanalyzed,
                        progress="UNKNOWN"),
    ])


def av_view_unknown_missing():
    """未知与缺史视图：无分支事实 + 缺失参考代理（missing_reason 非空）。"""

    actions_mod = _av_module("hangma_bot.kernel.actions")
    av_mod = _av_module("hangma_bot.policy.action_value")
    tile = actions_mod.Tile
    missing_ref = av_mod.ReferenceFeature(
        name="opp_win_share", value=0.0, version="ref/1", unit="近似比例",
        missing_reason="缺史：无校准数据，不冒充概率")
    return _av_view([
        _av_action_view(actions_mod.Discard(tile("3b")), branches=None,
                        progress="UNKNOWN"),
        _av_action_view(actions_mod.Pass(), progress="UNKNOWN"),
    ], reference_features=(missing_ref,))


def av_view_max_input():
    """最大输入视图：19 个动作（14 弃牌+吃碰杠胡过）各带分支事实。"""

    actions_mod = _av_module("hangma_bot.kernel.actions")
    tile = actions_mod.Tile
    actions = []
    for code in ("1w", "2w", "3w", "4w", "5w", "6w", "7w", "8w", "9w",
                 "1b", "2b", "3b", "4b", "5b"):
        branches = ({"followup_key": "discard:" + code, "combined_shanten": 1,
                     "support_remaining": 3, "route_status": "OPEN_UNCERTAIN"},)
        actions.append(_av_action_view(actions_mod.Discard(tile(code)),
                                       branches=branches, progress="SAME"))
    actions.append(_av_action_view(
        actions_mod.Chi((tile("1w"), tile("2w"), tile("3w"))), progress="SAME"))
    actions.append(_av_action_view(actions_mod.Peng(tile("2w")), progress="SAME"))
    actions.append(_av_action_view(actions_mod.Gang(tile("5w"),
                                                    actions_mod.GangKind.ADDED),
                                   progress="ADVANCE"))
    actions.append(_av_action_view(actions_mod.Hu(), progress="CLOSE"))
    actions.append(_av_action_view(actions_mod.Pass(), progress="SAME"))
    return _av_view(actions)


#: 视图夹具注册表：view_factory 按名解析（子进程同表）。
AV_VIEW_FIXTURES: Dict[str, Any] = {
    "sample": av_view_sample,
    "route_combo": av_view_route_combo,
    "unknown_missing": av_view_unknown_missing,
    "max_input": av_view_max_input,
}
AV_VIEW_FIXTURES.update(_av_family_views())

#: 覆盖层逐类清单（§6.2 覆盖行：动作族逐类 + 路线组合 + 未知与缺史）。
AV_COVERAGE_VIEWS: Tuple[str, ...] = (
    "fam_hu", "fam_pass", "fam_chi", "fam_peng", "fam_gang", "fam_discard",
    "route_combo", "unknown_missing",
)


def av_view_names(view_factory: Any) -> List[str]:
    """把 view_factory 规范成夹具名列表：str / {fixture: name} / JSON 路径。"""

    if isinstance(view_factory, str):
        names = [view_factory]
    elif isinstance(view_factory, Mapping):
        names = [str(view_factory["fixture"])]
    elif isinstance(view_factory, (list, tuple)):
        names = [str(item) for item in view_factory]
    else:
        spec = json.loads(Path(view_factory).read_text(encoding="utf-8"))
        names = [str(spec["fixture"])] if isinstance(spec, Mapping) else [
            str(item["fixture"]) for item in spec]
    unknown = [name for name in names if name not in AV_VIEW_FIXTURES]
    if unknown:
        raise ValueError("未知视图夹具 {0}（可用：{1}）".format(
            unknown, sorted(AV_VIEW_FIXTURES)))
    return names


# ---------------------------------------------------------------------------
# 5.2 探针候选（门禁自有的行为夹具；非模型输出、非候选注册表成员）
# ---------------------------------------------------------------------------

AV_PROBE_OK = '''def score_actions(view):
    entries = []
    for item in view["actions"]:
        entries.append({"action_key": item["action_key"], "score": 1.0, "trace": {}})
    return {"status": "SCORED", "entries": entries}
'''

#: 运行期故障探针：静态可过、执行必炸（除零）——验证隔离故障整批降级。
AV_PROBE_RAISE = '''def score_actions(view):
    total = 0.0
    for item in view["actions"]:
        total = total + 1.0 / 0.0
    return {"status": "SCORED", "entries": []}
'''

#: 超量探针：固定大循环触发计数限额（受限子集无 while，超量即等价死循环）。
AV_PROBE_OVERWORK = '''def score_actions(view):
    total = 0
    for i in range(10000000):
        total = total + i
    return {"status": "SCORED", "entries": []}
'''

#: 非有限数探针：1e308*10 运行期溢出为 Inf ——验证 NaN/Inf 整批失效。
AV_PROBE_NONFINITE = '''BASE = 1e308

def score_actions(view):
    big = BASE * 10.0
    entries = []
    for item in view["actions"]:
        entries.append({"action_key": item["action_key"], "score": big, "trace": {}})
    return {"status": "SCORED", "entries": entries}
'''

#: 缺动作探针：SCORED 少报一个动作——验证完整性拒绝。
AV_PROBE_MISSING = '''def score_actions(view):
    entries = []
    for item in view["actions"]:
        entries.append({"action_key": item["action_key"], "score": 1.0, "trace": {}})
    if len(entries) > 1:
        entries = entries[:-1]
    return {"status": "SCORED", "entries": entries}
'''

#: 非法键探针：多报一个越界动作键——验证越界拒绝。
AV_PROBE_ILLEGAL = '''def score_actions(view):
    entries = []
    for item in view["actions"]:
        entries.append({"action_key": item["action_key"], "score": 1.0, "trace": {}})
    entries.append({"action_key": "bogus:not_in_view", "score": 2.0, "trace": {}})
    return {"status": "SCORED", "entries": entries}
'''

#: 布尔冒充数探针：score=True ——验证布尔冒充数值整批失败。
AV_PROBE_BOOL = '''def score_actions(view):
    entries = []
    for item in view["actions"]:
        entries.append({"action_key": item["action_key"], "score": True, "trace": {}})
    return {"status": "SCORED", "entries": entries}
'''

#: 探针 → 允许的失败种类（kind 必须落在集合内且 ok=False 才算 PASS）。
AV_PROBE_EXPECTATIONS: Dict[str, Dict[str, Any]] = {
    "raise_error": {"source": AV_PROBE_RAISE,
                    "kinds": ("batch_invalid", "workload_exceeded")},
    "over_workload": {"source": AV_PROBE_OVERWORK, "kinds": ("workload_exceeded",)},
    "non_finite": {"source": AV_PROBE_NONFINITE, "kinds": ("workload_exceeded",
                                                           "batch_invalid")},
    "missing_action": {"source": AV_PROBE_MISSING, "kinds": ("batch_invalid",)},
    "illegal_key": {"source": AV_PROBE_ILLEGAL, "kinds": ("batch_invalid",)},
    "bool_score": {"source": AV_PROBE_BOOL, "kinds": ("batch_invalid",)},
}


# ---------------------------------------------------------------------------
# 5.3 受监管装载与执行（父进程静态检查 → 子进程装载执行）
# ---------------------------------------------------------------------------


def _av_exec_child(code_path: Path, view_names: Sequence[str], *,
                   timeout_sec: Optional[float], max_operations: Optional[int],
                   slot_id: str) -> Dict[str, Any]:
    """起一个受监管子进程装载执行给定源码；返回子进程报告（不抛错）。"""

    import tempfile

    slots = AVWorkerSlots()
    slots.acquire(slot_id, note="av-exec")
    try:
        workdir = Path(tempfile.mkdtemp(prefix="sitin-av-exec-"))
        out_path = workdir / "exec.json"
        source_path = workdir / "candidate.py"
        source_path.write_text(Path(code_path).read_text(encoding="utf-8"),
                               encoding="utf-8")
        command = [sys.executable, str(Path(__file__).resolve()),
                   "--internal-av-exec",
                   "--code", str(source_path),
                   "--views", ",".join(view_names),
                   "--out", str(out_path)]
        if max_operations is not None:
            command += ["--max-operations", str(int(max_operations))]
        result = process_guard.run_supervised(
            command, cwd=REPO, timeout_sec=(float(timeout_sec)
                                            if timeout_sec is not None
                                            else AV_EXEC_TIMEOUT_SEC),
            env=av_child_env())
        if result.timed_out:
            return {"ok": False, "failure_kind": "timeout",
                    "message": "受监管执行超时，进程组已终止（信号 {0}）".format(
                        "+".join(result.signals_sent) or "无"),
                    "execution": result.to_json()}
        if result.returncode != 0 or not out_path.is_file():
            tail = (result.stderr.strip().splitlines()[-1][:200]
                    if result.stderr.strip() else "")
            return {"ok": False, "failure_kind": "child_error",
                    "message": "子进程未产出结果：returncode={0}{1}".format(
                        result.returncode, "；stderr 尾部：" + tail if tail else ""),
                    "execution": result.to_json()}
        try:
            payload = json.loads(out_path.read_text(encoding="utf-8"))
        except Exception as exc:                    # noqa: BLE001 —— 解析失败同样是失败
            return {"ok": False, "failure_kind": "unparsable",
                    "message": "子进程结果不可解析：{0}".format(exc),
                    "execution": result.to_json()}
        payload["execution"] = result.to_json()
        return payload
    finally:
        slots.release(slot_id)


def _internal_av_exec(args: Any) -> int:
    """内部入口：在**工作子进程**里装载执行受限候选并逐视图评分。

    装载 = ActionValueExecutor 构造（静态检查+插桩编译+exec 全在本进程）；
    WorkloadExceeded 是 BaseException，显式接住转为结构化报告（候选不能
    捕获它继续执行——静态检查已拒绝 try/except，这里是执行器外围）。
    """

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    source = Path(args.code).read_text(encoding="utf-8")
    executor_mod = _av_module("hangma_bot.policy.action_value_executor")
    names = [name for name in args.views.split(",") if name]
    results: Dict[str, Any] = {}
    payload: Dict[str, Any] = {"schema": "sitin-av-exec/1",
                               "executor_version": executor_mod.EXECUTOR_VERSION}
    try:
        executor = executor_mod.ActionValueExecutor(
            source, name="<av-admission>",
            **({"max_operations": int(args.max_operations)}
               if args.max_operations is not None else {}))
    except executor_mod.WorkloadExceeded as exc:
        payload.update({"ok": False, "results": {}, "load": {
            "ok": False, "failure_kind": "workload_exceeded",
            "message": "装载期工作量超限：{0}".format(exc)}})
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                       encoding="utf-8")
        return 0
    except ValueError as exc:
        payload.update({"ok": False, "results": {}, "load": {
            "ok": False, "failure_kind": "static_or_load",
            "message": "{0}: {1}".format(type(exc).__name__, exc)}})
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                       encoding="utf-8")
        return 0
    payload["load"] = {"ok": True}
    for name in names:
        view = AV_VIEW_FIXTURES[name]()
        record: Dict[str, Any] = {"ok": False}
        started = time.perf_counter()
        try:
            batch = executor.score(view)
            record.update({"ok": True, "status": batch.status,
                           "entries": len(batch.entries),
                           "operations": executor.last_operation_count})
        except executor_mod.WorkloadExceeded as exc:
            record.update({"ok": False, "failure_kind": "workload_exceeded",
                           "message": str(exc)})
        except ValueError as exc:
            record.update({"ok": False, "failure_kind": "batch_invalid",
                           "message": str(exc)[:400]})
        except Exception as exc:                    # noqa: BLE001 —— 任何异常都整批失效
            record.update({"ok": False, "failure_kind": "batch_invalid",
                           "message": "{0}: {1}".format(type(exc).__name__, exc)[:400]})
        record["elapsed_ms"] = round((time.perf_counter() - started) * 1000.0, 3)
        results[name] = record
    payload["results"] = results
    payload["ok"] = all(item.get("ok") for item in results.values())
    # 保底可用性：整链失败后紧急计划仍可取得（§6.2 执行安全层的保底测试）。
    emergency = _av_emergency_probe()
    payload["emergency"] = emergency
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                   encoding="utf-8")
    return 0


def _av_emergency_probe() -> Dict[str, Any]:
    """在子进程内验证紧急动作路径独立可用（HangmaRules.emergency_action）。"""

    engine = _av_module("hangma_bot.hangma.engine")
    config_mod = _av_module("hangma_bot.kernel.config")
    rules = engine.HangmaRules(config_mod.RuleConfig(
        ruleset_version="v26", base_score=1, you_cai_bi_kao=False))
    started = time.perf_counter()
    candidate = rules.emergency_action(_av_observation())
    return {"available": candidate is not None,
            "action_key": getattr(candidate, "action_key", None),
            "elapsed_ms": round((time.perf_counter() - started) * 1000.0, 3)}


def load_candidate_supervised(candidate_source: str,
                              view_factory: Any = "sample", *,
                              timeout_sec: Optional[float] = None,
                              max_operations: Optional[int] = None) -> Dict[str, Any]:
    """**装载前监管 + 工作子进程装载执行**（§6.1；B2 留给 D 的装载函数）。

    父进程只做静态子集检查（AST 层，不执行候选代码）；静态失败**不进
    子进程**（T07 装载前监管）。通过后再经 sitin_process.run_supervised
    在工作子进程完成装载（插桩编译+exec）与逐视图评分；子进程环境不含
    凭据，到期终止整个进程组。静态检查与计费实现与 B2 执行器同源。
    """

    executor_mod = _av_module("hangma_bot.policy.action_value_executor")
    try:
        executor_mod.static_check(candidate_source)
    except ValueError as exc:
        return {"ok": False, "stage": "static",
                "failure_kind": "static",
                "message": "静态子集检查未通过（未进入子进程装载）：{0}".format(exc),
                "supervised": False}
    import tempfile

    workdir = Path(tempfile.mkdtemp(prefix="sitin-av-load-"))
    code_path = workdir / "candidate.py"
    code_path.write_text(candidate_source, encoding="utf-8")
    report = _av_exec_child(code_path, av_view_names(view_factory),
                            timeout_sec=timeout_sec,
                            max_operations=max_operations,
                            slot_id="av-load:{0}".format(hash(code_path) & 0xFFFFFF))
    report["stage"] = "supervised"
    report["supervised"] = True
    return report


def _internal_av_timing(args: Any) -> int:
    """内部入口：整链计时（紧急/规则分析/事实构建/评分/计划输出 + 预算夹具）。"""

    from types import SimpleNamespace

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    source = Path(args.code).read_text(encoding="utf-8")
    repeats = max(1, int(args.repeats))
    executor_mod = _av_module("hangma_bot.policy.action_value_executor")
    seeds = _av_module("hangma_bot.policy.action_value_seeds")
    policy_mod = _av_module("hangma_bot.policy.action_value_policy")
    interface_mod = _av_module("hangma_bot.hangma.interface")
    engine = _av_module("hangma_bot.hangma.engine")
    config_mod = _av_module("hangma_bot.kernel.config")
    actions_mod = _av_module("hangma_bot.kernel.actions")
    observation_mod = _av_module("hangma_bot.kernel.observation")

    base = seeds.make_sample_observation()
    hand = base.my_hand + (actions_mod.Tile("6b"),)
    obs = observation_mod.PlayerObservation(
        game_id=base.game_id, seat=base.seat, round_no=base.round_no,
        snapshot_seq=base.snapshot_seq, phase="draw", dealer_seat=base.dealer_seat,
        turn_seat=base.turn_seat, responding_seats=base.responding_seats,
        my_hand=hand, drawn_tile=actions_mod.Tile("6b"), discards=base.discards,
        melds=base.melds, hand_counts=(14, 13, 13, 13),
        last_discard=base.last_discard,
        remaining_tile_count=base.remaining_tile_count, scores=base.scores,
        rule_state=base.rule_state, public_history=base.public_history)
    rules = engine.HangmaRules(config_mod.RuleConfig(
        ruleset_version="v26", base_score=1, you_cai_bi_kao=False))
    limits = interface_mod.ValueAnalysisLimits()
    competition = observation_mod.CompetitionContext(
        tournament_id="timing-fixture", stage_no=None, stage_role=None,
        stage_total=None, participant_rank=None, ranking=(), observed_at_unix_ms=0)
    executor = executor_mod.ActionValueExecutor(source, name="<av-timing>",
        **({"max_operations": args.max_operations} if args.max_operations is not None else {}))
    segments: Dict[str, List[float]] = {name: [] for name in (
        "emergency", "rule_analysis", "fact_build", "scoring", "plan_output")}
    full_chain: List[float] = []
    failure = None
    for _ in range(repeats):
        try:
            started = time.perf_counter()
            rules.emergency_action(obs)
            t1 = time.perf_counter()
            analysis = rules.analyze(obs, value_limits=limits)
            t2 = time.perf_counter()
            request = SimpleNamespace(observation=obs, rules=analysis,
                                      competition=competition)
            view = policy_mod.build_scoring_view(request)
            t3 = time.perf_counter()
            batch = executor.score(view)
            t4 = time.perf_counter()
            policy_mod.batch_to_ranked_candidates(batch, view.actions)
            t5 = time.perf_counter()
        except (Exception, executor_mod.WorkloadExceeded) as exc:  # 计数异常也须留下计时失败记录
            failure = "{0}: {1}".format(type(exc).__name__, exc)
            break
        segments["emergency"].append((t1 - started) * 1000.0)
        segments["rule_analysis"].append((t2 - t1) * 1000.0)
        segments["fact_build"].append((t3 - t2) * 1000.0)
        segments["scoring"].append((t4 - t3) * 1000.0)
        segments["plan_output"].append((t5 - t4) * 1000.0)
        full_chain.append((t5 - started) * 1000.0)
    # DecisionBudget 剩余额度夹具：增强截止已过 → 必须拒绝进入增强评分。
    budget_mod = _av_module("hangma_bot.policy.interface")
    now = 1000.0
    over = budget_mod.DecisionBudget(
        enhancement_deadline_monotonic=now - 1.0,
        fallback_deadline_monotonic=now + 1.0,
        latest_send_at_monotonic=now + 2.0)
    under = budget_mod.DecisionBudget(
        enhancement_deadline_monotonic=now + 0.5,
        fallback_deadline_monotonic=now + 1.0,
        latest_send_at_monotonic=now + 2.0)
    over_ok, over_reason = av_budget_headroom(now, over)
    under_ok, _under_reason = av_budget_headroom(now, under)
    over_refused = not over_ok
    payload = {
        "schema": "sitin-av-timing/1",
        "n_repeats": repeats,
        "failure": failure,
        "segments_ms": {name: av_percentiles(values)
                        for name, values in segments.items()},
        "full_chain_ms": av_percentiles(full_chain),
        "network_margin_ms": AV_NETWORK_MARGIN_MS,
        "budget_fixture": {
            "over_budget_refused": over_refused,
            "over_budget_reason": over_reason,
            "headroom_budget_accepted": under_ok,
            "note": "预算夹具：增强截止已过的 DecisionBudget 拒绝进入增强评分；"
                    "整链耗时另按剩余额度检查，网络余量固定扣除",
        },
        "executor_version": executor_mod.EXECUTOR_VERSION,
        "max_operations": args.max_operations or executor_mod.MAX_COUNTED_OPERATIONS,
    }
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                   encoding="utf-8")
    return 0


def av_percentiles(values_ms: Sequence[float]) -> Dict[str, float]:
    """分段耗时的 p50/p95/p99/max（毫秒；空序列全 0 并标记空）。"""

    if not values_ms:
        return {"p50": 0.0, "p95": 0.0, "p99": 0.0, "max": 0.0, "n": 0}
    ordered = sorted(values_ms)

    def pct(fraction: float) -> float:
        index = min(int(fraction * (len(ordered) - 1)), len(ordered) - 1)
        return ordered[index]

    return {"p50": round(pct(0.50), 3), "p95": round(pct(0.95), 3),
            "p99": round(pct(0.99), 3), "max": round(ordered[-1], 3),
            "n": len(ordered)}


def av_budget_headroom(now_monotonic: float, budget: Any, *,
                       margin_ms: float = AV_NETWORK_MARGIN_MS
                       ) -> Tuple[bool, str]:
    """按实际 DecisionBudget 剩余额度检查是否允许进入增强评分。

    增强截止已过（或剩余量不足以覆盖固定网络余量）→ 拒绝：骨架必须
    在进入增强前就退回已备好的合法紧急计划（§4.1/§6.2）。
    """

    remaining_ms = (budget.enhancement_deadline_monotonic - now_monotonic) * 1000.0
    if remaining_ms <= 0.0:
        return False, "增强截止已过（剩余 {0:.1f}ms）：不进入增强评分，退回紧急计划".format(
            remaining_ms)
    if remaining_ms < margin_ms:
        return False, ("剩余 {0:.1f}ms 低于固定网络余量 {1:.1f}ms："
                       "不进入增强评分".format(remaining_ms, margin_ms))
    return True, ""


# ---------------------------------------------------------------------------
# 5.4 admit_action_value：五层门禁主入口（§6.2 表逐行）
# ---------------------------------------------------------------------------


def _av_probe_item(probe_name: str, *, views: Sequence[str] = ("sample",),
                   timeout_sec: Optional[float] = None,
                   max_operations: Optional[int] = None) -> Dict[str, Any]:
    """跑一个探针候选并按期望失败种类判定 PASS/FAIL。"""

    expectation = AV_PROBE_EXPECTATIONS[probe_name]
    import tempfile

    workdir = Path(tempfile.mkdtemp(prefix="sitin-av-probe-"))
    code_path = workdir / "probe.py"
    code_path.write_text(expectation["source"], encoding="utf-8")
    report = _av_exec_child(code_path, list(views), timeout_sec=timeout_sec,
                            max_operations=max_operations,
                            slot_id="av-probe:{0}".format(probe_name))
    item: Dict[str, Any] = {"probe": probe_name}
    if report.get("failure_kind"):
        item.update({"status": "FAIL", "reason": report.get("message"),
                     "failure_kind": report.get("failure_kind")})
        return item
    results = report.get("results") or {}
    per_view = {}
    ok = True
    for name, outcome in results.items():
        kinds = expectation["kinds"]
        passed = (not outcome.get("ok")) and outcome.get("failure_kind") in kinds
        per_view[name] = {"rejected": not outcome.get("ok"),
                          "failure_kind": outcome.get("failure_kind"),
                          "pass": passed}
        ok = ok and passed
    item["per_view"] = per_view
    item["status"] = "PASS" if ok and per_view else "FAIL"
    if not ok:
        item["reason"] = "存在未被正确拒绝的探针视图（期望整批失败种类 {0}）".format(
            list(expectation["kinds"]))
    item["execution_tail"] = (report.get("execution") or {})
    return item


def admit_action_value(candidate_source: str, *, executor_config: Optional[Mapping[str, Any]] = None,
                       facts_panel: Optional[Mapping[str, Any]] = None,
                       timing_config: Optional[Mapping[str, Any]] = None,
                       execution_profile: Any = None) -> Dict[str, Any]:
    """action_value_v1 五层门禁（§6.2）；返回 sitin-action-value-admission/1 记录。

    层与 PASS 条件（逐项记录，未知关键安全性质不放行）：
      1 执行安全：静态子集 / 限额全链 / 输出合同 / 隔离故障 / 保底 / 审计；
      2 覆盖：胡/过/吃/碰/杠/弃牌逐类 + 路线组合 + 未知缺史（样本不足标
        INSUFFICIENT，不汇总抹平）；
      3 受控研究资格：执行安全 PASS + 场景生成器合法 + 候选身份绑定 +
        资源余量（工作进程上限）——资格不等于发布；
      4/5 效果与发布资格：本入口不评价（记录里显式 NOT_EVALUATED）。
    整链计时独立成块：五段耗时 p50/p95/p99/max + 预算夹具 + 网络余量。
    """

    started = time.monotonic()
    executor_config = dict(executor_config or {})
    profile = execution_profiles.resolve(execution_profile)
    operation_limit = profile["max_operations"]
    if "max_operations" in executor_config:
        declared = executor_config["max_operations"]
        if type(declared) is not int or declared != operation_limit:
            raise ValueError("executor_config额度与显式执行配置不符；不能只记录未生效的额度")
    executor_config["max_operations"] = operation_limit
    timing_config = dict(timing_config or {})
    timing_config.setdefault("repeats", AV_TIMING_REPEATS)
    record: Dict[str, Any] = {
        "schema": AV_ADMISSION_SCHEMA,
        "candidate_kind": AV_CANDIDATE_KIND,
        "created_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "identity": av_identity_binding(candidate_source, execution_profile=profile),
        "execution_profile": profile,
        "executor_config": executor_config,
        "facts_panel": {key: (str(value) if isinstance(value, Path) else value)
                        for key, value in (facts_panel or {}).items()},
        "note": AV_ADMISSION_NOTE,
        "legacy_gates_unchanged": True,
    }

    # —— 层 1：执行安全（六项，任何一项未知/失败即不放行）——
    items: Dict[str, Any] = {}
    executor_mod = _av_module("hangma_bot.policy.action_value_executor")
    static_problems: List[str] = []
    try:
        executor_mod.static_check(candidate_source)
    except ValueError as exc:
        static_problems.append(str(exc))
    items["static_subset"] = {
        "status": "PASS" if not static_problems else "FAIL",
        "problems": static_problems,
        "source_bytes": len(candidate_source.encode("utf-8")),
        "max_source_bytes": executor_mod.MAX_SOURCE_BYTES,
    }
    load_report: Optional[Dict[str, Any]] = None
    if not static_problems:
        load_report = load_candidate_supervised(
            candidate_source, ["sample", "max_input"],
            timeout_sec=executor_config.get("timeout_sec"), max_operations=operation_limit)
        sample_ok = bool((load_report.get("results") or {}).get("sample", {}).get("ok"))
        max_ok = bool((load_report.get("results") or {}).get("max_input", {}).get("ok"))
        items["supervised_load"] = {
            "status": "PASS" if (sample_ok and max_ok and load_report.get("load", {}).get("ok"))
            else "FAIL",
            "reason": None if sample_ok and max_ok else (
                (load_report.get("message") if load_report.get("failure_kind") else None)
                or "受监管装载或最大输入评分未通过（详见 load_report）"),
            "views": {name: {"ok": bool(outcome.get("ok")),
                             "failure_kind": outcome.get("failure_kind"),
                             "operations": outcome.get("operations")}
                      for name, outcome in (load_report.get("results") or {}).items()},
            "group_still_alive": bool(
                (load_report.get("execution") or {}).get("group_still_alive")),
        }
    else:
        items["supervised_load"] = {"status": "FAIL",
                                    "reason": "静态检查未通过，未进入子进程装载"}
    items["limits_full_chain"] = _av_probe_item(
        "over_workload", views=("sample", "max_input"),
        timeout_sec=executor_config.get("timeout_sec"), max_operations=operation_limit)
    output_items = {name: _av_probe_item(name, max_operations=operation_limit) for name in
                    ("non_finite", "missing_action", "illegal_key", "bool_score")}
    items["output_contract"] = {
        "status": ("PASS" if all(item["status"] == "PASS"
                                 for item in output_items.values()) else "FAIL"),
        "probes": output_items,
    }
    items["isolation_fault"] = _av_probe_item(
        "raise_error", timeout_sec=executor_config.get("timeout_sec"), max_operations=operation_limit)
    raise_execution = items["isolation_fault"].get("execution_tail") or {}
    emergency = {}
    if isinstance(load_report, Mapping):
        emergency = load_report.get("emergency") or {}
    isolation_ok = (items["isolation_fault"]["status"] == "PASS"
                    and not raise_execution.get("group_still_alive"))
    fallback_ok = isolation_ok and emergency.get("available") is True
    items["fallback"] = {
        "status": "PASS" if fallback_ok else "FAIL",
        "emergency_after_failure": emergency,
        "reason": None if fallback_ok else
        "候选故障被隔离后紧急计划不可用，或进程组未正确终止",
    }
    safety_pass = all(
        item.get("status") == "PASS"
        for key, item in items.items()
        if key in ("static_subset", "supervised_load", "limits_full_chain",
                   "output_contract", "isolation_fault", "fallback"))
    # 审计测试：先写占位记录证明可落盘，末尾用完整记录复写再验一次。
    audit_dir = None
    if isinstance(facts_panel, Mapping) and facts_panel.get("record_dir"):
        audit_dir = Path(str(facts_panel["record_dir"]))
    import tempfile

    audit_workdir = Path(tempfile.mkdtemp(prefix="sitin-av-audit-"))
    audit_path = (audit_dir / "admission.json") if audit_dir else (
        audit_workdir / "admission.json")
    audit_ok = True
    audit_problems: List[str] = []
    try:
        audit_path.parent.mkdir(parents=True, exist_ok=True)
        audit_path.write_text(json.dumps({"schema": AV_ADMISSION_SCHEMA},
                                         ensure_ascii=False), encoding="utf-8")
        json.loads(audit_path.read_text(encoding="utf-8"))
    except Exception as exc:                        # noqa: BLE001 —— 审计失败也是失败
        audit_ok = False
        audit_problems.append(str(exc))
    items["audit"] = {"status": "PASS" if audit_ok else "FAIL",
                      "record_path": str(audit_path),
                      "problems": audit_problems}
    safety_pass = safety_pass and audit_ok
    execution_safety = {
        "status": "PASS" if safety_pass else "FAIL",
        "items": items,
        "policy": "FAIL 禁止效果执行；未知关键安全性质不放行（六项必须齐备且全 PASS）",
    }
    if load_report is not None:
        execution_safety["load_report"] = {
            key: value for key, value in load_report.items()
            if key != "execution"}
        execution_safety["supervision"] = load_report.get("execution")

    # —— 层 2：覆盖（候选逐类真实评分；样本不足标 INSUFFICIENT）——
    coverage: Dict[str, Any] = {"views": {}, "status": None}
    if static_problems:
        coverage["status"] = "FAIL"
        coverage["reason"] = "静态检查未通过，覆盖层未运行（没跑不等于通过）"
    else:
        cov_report = load_candidate_supervised(
            candidate_source, list(AV_COVERAGE_VIEWS),
            timeout_sec=executor_config.get("timeout_sec"), max_operations=operation_limit)
        per_view = cov_report.get("results") or {}
        statuses = []
        for name in AV_COVERAGE_VIEWS:
            outcome = per_view.get(name)
            if outcome is None:
                coverage["views"][name] = {"status": "INSUFFICIENT",
                                           "reason": "该类视图未取得样本（不汇总抹平）"}
                statuses.append("INSUFFICIENT")
            elif outcome.get("ok"):
                coverage["views"][name] = {"status": "PASS",
                                           "entries": outcome.get("entries"),
                                           "operations": outcome.get("operations")}
                statuses.append("PASS")
            elif outcome.get("failure_kind") in ("batch_invalid", "workload_exceeded"):
                coverage["views"][name] = {
                    "status": "FAIL", "reason": outcome.get("message"),
                    "failure_kind": outcome.get("failure_kind")}
                statuses.append("FAIL")
            else:
                coverage["views"][name] = {
                    "status": "INSUFFICIENT",
                    "reason": "执行报告缺失（{0}）".format(
                        cov_report.get("message") or outcome.get("failure_kind"))}
                statuses.append("INSUFFICIENT")
        coverage["status"] = ("FAIL" if "FAIL" in statuses else
                              ("INSUFFICIENT" if "INSUFFICIENT" in statuses
                               else "PASS"))
    record["layers"] = {
        "execution_safety": execution_safety,
        "coverage": coverage,
    }

    # —— 层 3：受控研究资格（不等于发布）——
    reasons: List[str] = []
    if not safety_pass:
        reasons.append("执行安全层未通过")
    panel = facts_panel or {}
    generator = panel.get("generator") or panel.get("prefix_source")
    if not generator:
        reasons.append("未声明事实面板/场景生成器身份")
    elif panel.get("legal") is False:
        reasons.append("事实面板声明生成器不合法")
    resource_ok = True
    try:
        slots = AVWorkerSlots()
        slots.acquire("av-admission:{0}".format(record["identity"]["candidate_id"][:12]))
        slots.release("av-admission:{0}".format(record["identity"]["candidate_id"][:12]))
    except WorkerCapExceeded as exc:
        resource_ok = False
        reasons.append(str(exc))
    record["layers"]["controlled_research"] = {
        "status": "ELIGIBLE" if not reasons else "NOT_ELIGIBLE",
        "reasons": reasons,
        "generator": generator,
        "worker_slots_available": resource_ok,
        "note": "受控研究资格可在声明条件/自然面板取证；不等于发布准入",
    }

    # —— 整链计时（§6.2：分段 + 全链分位数 + 预算夹具 + 网络余量）——
    timing_block: Dict[str, Any] = {"status": "SKIP", "reason": "静态检查未通过"}
    if not static_problems:
        import tempfile

        timing_dir = Path(tempfile.mkdtemp(prefix="sitin-av-timing-"))
        code_path = timing_dir / "candidate.py"
        code_path.write_text(candidate_source, encoding="utf-8")
        slots = AVWorkerSlots()
        slot_id = "av-timing:{0}".format(record["identity"]["candidate_id"][:12])
        slots.acquire(slot_id)
        try:
            out_path = timing_dir / "timing.json"
            command = [sys.executable, str(Path(__file__).resolve()),
                       "--internal-av-timing",
                       "--code", str(code_path),
                       "--repeats", str(int(timing_config["repeats"])),
                       "--max-operations", str(operation_limit),
                       "--out", str(out_path)]
            result = process_guard.run_supervised(
                command, cwd=REPO,
                timeout_sec=float(timing_config.get("timeout_sec", 300.0)),
                env=av_child_env())
            if result.timed_out or not out_path.is_file():
                timing_block = {"status": "FAIL",
                                "reason": "计时链执行超时或未产出（信号 {0}）".format(
                                    "+".join(result.signals_sent) or "无")}
            else:
                timing_block = json.loads(out_path.read_text(encoding="utf-8"))
                timing_block["status"] = (
                    "PASS" if timing_block.get("failure") is None
                    and timing_block.get("budget_fixture", {}).get("over_budget_refused")
                    else "FAIL")
        finally:
            slots.release(slot_id)
    record["timing"] = timing_block

    record["execution_safety_pass"] = safety_pass
    record["controlled_research_eligible"] = (
        record["layers"]["controlled_research"]["status"] == "ELIGIBLE")
    record["effect"] = {"status": "NOT_EVALUATED",
                        "note": "效果层由 evaluate-action-value 双臂与统计评价；不补零"}
    record["release"] = {"status": "NOT_EVALUATED",
                         "note": "发布层需独立确认、规则一致性、实际时限/恢复与人工审核"}
    record["elapsed_sec"] = round(time.monotonic() - started, 3)
    # 审计层第二跳：完整记录可落盘可回读。
    try:
        audit_path.write_text(
            json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        json.loads(audit_path.read_text(encoding="utf-8"))
        record["audit_record_path"] = str(audit_path)
    except Exception as exc:                        # noqa: BLE001 —— 审计失败翻转安全层
        record["layers"]["execution_safety"]["items"]["audit"] = {
            "status": "FAIL", "problems": [str(exc)]}
        record["layers"]["execution_safety"]["status"] = "FAIL"
        record["execution_safety_pass"] = False
    return record


def _internal_prepare(args: Any) -> int:
    """内部入口：在**隔离进程**里装载候选注册表并构造候选，把身份与作用面写成 JSON。

    **父进程不执行任何候选代码**：注册表导入、模块体、构造参数都发生在这里。
    """

    heuristics = heuristics_registry()
    candidate = args.candidate
    weights = json.loads(args.weights)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    params, base = heuristics.split_declaration_params(dict(weights))
    built = heuristics.build_candidate(candidate, weights=weights)
    spec = built.adjustment.spec
    module = heuristics.candidate_module(candidate)
    source = module.__file__
    payload = {
        "schema": "sitin-prepare/1",
        "candidate": candidate,
        "weights": dict(weights),
        "params": params,
        "base": base,
        "scope": list(spec.scope),
        "bound_identity": candidate_identity(candidate, weights),
        "adjustment_identity": built.identity(),
        "adjustment_spec": {
            "name": spec.name, "version": spec.version, "trigger": spec.trigger,
            "thought": spec.thought, "scope": list(spec.scope), "bound": spec.bound,
        },
        "source_sha256": hashlib.sha256(Path(source).read_bytes()).hexdigest(),
        "source_path": str(Path(source)),
        "dependency_digest": candidate_identity_digest(candidate),
    }
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    return 0


def _internal_gate(args: Any) -> int:
    """内部入口：在**隔离进程**里只跑一道门禁，把结果写成 JSON。

    与 `run_all` 分开是为了让"受监管执行"这件事只有一个实现：
    父进程负责墙钟上限与进程组终止，子进程只负责算。
    """

    candidate = args.candidate
    weights = json.loads(args.weights)
    corpus = Path(args.corpus)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    if args.internal_gate == "g2c":
        # 逐类判定走**惰性**读取：canonical 面板 359,262 行全物化约 28 GB。
        rows: Any = iter_corpus(corpus, args.corpus_limit)
    else:
        rows = load_corpus(corpus, args.corpus_limit)
    if args.internal_gate == "g1":
        scope = heuristics.build_candidate(
            candidate, weights=weights).adjustment.spec.scope
        requests, budgets = build_g1_windows(rows, limit=args.g1_limit,
                                             require_kinds=scope)
        report = gate_g1(candidate, weights, requests, budgets)
    elif args.internal_gate == "g2c":
        # 3.6b：逐类覆盖判定。**在子进程里跑**，因为它要 import 场景类工具
        # （该模块会 import 候选侧事实函数），父进程不执行候选侧代码。
        record_layer = resolve_record_layer(corpus, getattr(args, "record_layer", None))
        report = gate_g2c(candidate, weights, rows, record_layer=record_layer)
    else:
        report = gate_g2(candidate, weights, rows)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    return 0


def _verify_research_cli(path: Path) -> int:
    """校验一份研究记录**不得**被读成准入；有问题退出码 2。

    这是"禁止让触发集 PASS 被旧扫描器误当成全局准入"那条要求的可执行形态：
    下游拿到的任何研究记录都必须先过这里。
    """

    record = json.loads(Path(path).read_text(encoding="utf-8"))
    problems = verify_research_record(record)
    for problem in problems:
        print("      ! {0}".format(problem))
    if problems:
        print("研究记录校验失败：{0} 项问题".format(len(problems)))
        return 2
    print("研究记录校验通过：{0}；permitted={1}（**不是**准入结论）".format(
        record.get("schema"), record.get("permitted")))
    return 0


def _research_entry_cli(args: Any) -> int:
    """受控研究执行入口（CLI）：**拒绝路径优先**；permitted=False 时退出码 2。

    记录总会落盘（含全部拒绝理由），这样"被拒"本身也是可复核的证据，
    而不是一句无法追查的失败。
    """

    if not args.gate_record:
        raise SystemExit("--research-entry 需要 --gate-record（含 perclass 段的门禁记录）")
    gate_record = json.loads(Path(args.gate_record).read_text(encoding="utf-8"))
    request: Any = {}
    if args.research_request:
        request = json.loads(Path(args.research_request).read_text(encoding="utf-8"))
    record = research_execution_entry(request, gate_record=gate_record)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for refusal in record["refusals"]:
        print("      ! 拒绝[{0}] {1}".format(refusal["code"], refusal["reason"]))
    if record["permitted"]:
        print("研究执行许可（**非准入**）：候选 {0}；研究范围 {1} 类；结论范围 {2} 类".format(
            record["candidate"], len(record["research_scope"]["classes"]),
            len(record["claim_scope"]["classes"])))
        return 0
    print("拒绝研究执行：{0} 条理由（记录已落盘，admitted 恒为 false）".format(
        len(record["refusals"])))
    return 2


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="坐隐 2.3 候选门禁（G-0/G-1/G-2/G-3 + 3.6b G-2C 逐类覆盖与研究入口）")
    # `--candidate` 不再在 argparse 层强制：研究入口/校验入口不需要它。
    # 需要它的路径在下面显式校验，错误信息与旧行为一致。
    ap.add_argument("--candidate", default=None)
    ap.add_argument("--weights", default="{}", help="JSON；候选参数用 adj. 前缀")
    ap.add_argument("--corpus", default=None,
                    help="语料路径；--internal-prepare 模式下不需要")
    ap.add_argument("--registrations", default=None,
                    help="G-3 登记文件；--internal-gate 模式下不需要")
    # --out 不在 argparse 层强制：校验与研究入口不需要它；需要它的路径在下面显式校验。
    ap.add_argument("--out", default=None)
    ap.add_argument("--corpus-limit", type=int, default=None)
    ap.add_argument("--g1-limit", type=int, default=40)
    ap.add_argument("--evidence-kind", choices=("admission", "trigger"),
                    default="admission",
                    help="admission=真实语料（准入依据）；trigger=构造触发集（非准入）")
    ap.add_argument("--gate-timeout-sec", type=float, default=None,
                    help="隔离执行的墙钟上限（秒）；缺省 G-1 300 秒、G-2 600 秒")
    ap.add_argument("--internal-gate", choices=("g1", "g2", "g2c"), default=None,
                    help="内部入口：只跑一道门禁并把结果写到 --out（由父进程受监管调用）")
    ap.add_argument("--internal-prepare", action="store_true",
                    help="内部入口：在隔离进程里装载并构造候选，把身份与作用面写到 --out")
    ap.add_argument("--internal-av-exec", action="store_true",
                    help="内部入口：工作子进程装载执行 action_value 候选（--code 源码，--views 夹具 CSV）")
    ap.add_argument("--internal-av-timing", action="store_true",
                    help="内部入口：整链计时（紧急/规则分析/事实构建/评分/计划输出）")
    ap.add_argument("--code", default=None, help="--internal-av-* 用：候选源码文件")
    ap.add_argument("--views", default="sample", help="--internal-av-exec 用：视图夹具 CSV")
    ap.add_argument("--max-operations", type=int, default=None,
                    help="--internal-av-exec 用：覆盖计数操作上限（测试收紧用）")
    ap.add_argument("--repeats", type=int, default=12,
                    help="--internal-av-timing 用：计时重复次数")
    ap.add_argument("--perclass", action="store_true",
                    help="追加 G-2C 逐类覆盖判定（受监管子进程；**不改变** admitted 语义）")
    ap.add_argument("--research-entry", dest="research_entry", action="store_true",
                    help="受控研究执行入口：先走拒绝路径；permitted=False 时退出码 2")
    ap.add_argument("--gate-record", default=None,
                    help="--research-entry 用：含 perclass 段的门禁记录")
    ap.add_argument("--research-request", default=None,
                    help="--research-entry 用：研究请求 JSON（候选/面板/采样器身份 + 范围 + 种子）")
    ap.add_argument("--verify-research", default=None,
                    help="校验一份研究记录不得被读成准入；有问题退出码 2")
    ap.add_argument("--record-layer", dest="record_layer",
                    choices=(SCENARIO_RECORD_LAYER_RAW, SCENARIO_RECORD_LAYER_FILLED),
                    default=None,
                    help="记录层视图：缺省 = 语料清单声明的视图（canonical 面板声明 filled），再退回 raw")
    args = ap.parse_args(argv)

    if args.internal_prepare:
        return _internal_prepare(args)
    if getattr(args, "internal_av_exec", None):
        return _internal_av_exec(args)
    if getattr(args, "internal_av_timing", False):
        return _internal_av_timing(args)
    if args.internal_gate:
        return _internal_gate(args)
    if args.verify_research:
        return _verify_research_cli(Path(args.verify_research))
    if args.research_entry:
        return _research_entry_cli(args)

    if not args.out:
        raise SystemExit("--out 为必填（--verify-research 除外）")
    if not args.candidate:
        raise SystemExit("--candidate 为必填（除非使用 --internal-*/--research-entry/--verify-research）")
    if not args.corpus:
        raise SystemExit("--corpus 为必填（除非使用 --internal-prepare）")
    if not args.registrations:
        raise SystemExit("--registrations 为必填（除非使用 --internal-gate/--internal-prepare）")
    registrations = json.loads(Path(args.registrations).read_text(encoding="utf-8"))
    timeout = args.gate_timeout_sec
    report = run_all(args.candidate, json.loads(args.weights), Path(args.corpus),
                     registrations, corpus_limit=args.corpus_limit,
                     g1_limit=args.g1_limit,
                     evidence_kind=args.evidence_kind,
                     g1_timeout_sec=timeout, g2_timeout_sec=timeout,
                     perclass=args.perclass, g2c_timeout_sec=timeout,
                     record_layer=args.record_layer)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    for gate in report["gates"]:
        print("[{0}] {1}".format(gate["status"], gate["gate"]))
        for problem in gate.get("problems", ()):
            print("      ! {0}".format(problem))
    if report.get("perclass"):
        # 逐类段**不参与准入**，因此单独一行打印，措辞也点明这一点。
        rollup = (report["perclass"].get("detail") or {}).get("rollup")
        if rollup:
            print("[{0}] {1}（逐类覆盖，**不参与 admitted**；最弱环节 {2}/{3} 类 reliable）".format(
                report["perclass"]["status"], report["perclass"]["gate"],
                rollup["reliable_count"], rollup["declared_count"]))
        else:
            # 隔离执行失败时没有 rollup：**照实说"没算成"**，不许把它读成"通过"。
            print("[{0}] {1}（逐类覆盖，**不参与 admitted**；本段未产出 rollup）".format(
                report["perclass"]["status"], report["perclass"]["gate"]))
    if report["evidence_kind"] != "admission":
        # 构造触发集的结论**不是**准入结论；措辞必须与用途一致，避免被下游误读。
        print("结论（触发集，**非准入证据**）：门禁级结论 {0}；失败 {1}；证据不足 {2}".format(
            "通过" if report["gate_level_admitted"] else "不通过",
            report["failed"], report["insufficient"]))
    elif report["admitted"]:
        print("结论：全部门禁通过（可准入）")
    elif report["insufficient"] and not report["failed"]:
        print("结论：**证据不足，不予准入**：{0}".format(report["insufficient"]))
    else:
        print("结论：未通过：失败 {0}；证据不足 {1}".format(
            report["failed"], report["insufficient"]))
    return 0 if report["admitted"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
