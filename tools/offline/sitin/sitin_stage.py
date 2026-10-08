"""坐隐 3.0／3.4／3.5：阶段合同、编排验证、搜索闭环与冻结交接。

对齐 [PLAN-REVISION §3.0／§3.4／§3.5](../../PLAN-REVISION-2026-09-15.md)
与 §2「阶段晋级进入选择流程」，以及 [README §17](../README.md) 第三步。

## 本包做三件事

1. **3.0 把阶段合同冻成可核验的产物**：官方资料版本/抓取日期、目标阶段、实际 Rounds/场次数、
   分组换座、阶段清零、排名键与同分规则、晋级定义、对手情景、规则/策略版本、种子与停止条件。
   每一条都带**证据级别**（根 AGENTS.md §3：官方已确认 / 当前观察 / 工程建议 / 待确认假设）
   与出处；没有依据的项写进 unresolved，**不猜**。
2. **3.0 用小规模真实桌赛验证编排语义**：按官方档位表组阶段（海选 → 组内 → 决赛），
   真实跑完整桌赛，再用官方排序 / 晋级 / 阶段清零 / 决赛加赛规则算名次。
3. **3.4 受准入约束的候选槽与配套阶段比较**（`compare`）：把候选注入阶段面板，
   跑**候选 vs 基线**、按场景种子配对的完整阶段比较，并按根级（场景）统计报点估计、
   根级 sd、SE 与 MDE；两臂牌山必须逐字相同，单侧失败即不可排序。见本文 §10。

   **搜索闭环（生成 → 门禁 → L1/L2 → 阶段比较 → 留存淘汰 → 反馈）与 3.5 冻结件
   不由本文件实现**：编排者是 tools/sitin_search.py（searchdrv 包），它按冻结文件里的
   command_template 调用本文件的 `compare`，并从 compare.json 的 execution 段读实际桌数。
   本文件**只有执行台账**（`sitin-stage-ledger/1`，记桌数与墙钟），**不是预算账本**。

## 不是本包的东西（避免越界）

- 四分量完整价值结构基线（baseline 包）、3.1 最小生成闭环（genloop 包）、
  3.P 的 REVIEW-8 修复核验与门禁语义证据（fixverify 包）。本包只**编排**它们，不重写它们。
- **3.0 的三条命令（`run` / `fixture` / `replay`）不装载候选、不 import 候选注册表**：
  它们只用**冻结的稳定策略白名单**（见 PANEL_POLICY_NAMES 的说明），因此不产生任何准入结论，
  也不得被读成「候选可用」的依据。这条线由
  `test_panel_assembly_never_imports_the_candidate_registry` 在**二进制层面**守着
  （子进程里真的装配面板再看 sys.modules）。
- **3.4 的 `compare` 路径会装载候选**，这是有意为之的**边界扩张**，
  并且带三道闸：① 候选必须来自**静态注册表**（`is_candidate` 判定，未注册直接失败）；
  ② 必须给出门禁**准入记录**（admitted=true 且语料指纹一致），否则拒绝跑阶段比较；
  ③ 候选代码只在**受监管隔离子进程**里执行（`sitin_process.run_supervised`）。
  即便如此，本包跑出的任何阶段结果仍是**开发期证据**，不是发布门禁结论。
- 本包**不做发布结论**：三种完成状态在产物里分开写（工具完成 / 发现候选 / 通过发布门禁）。

## 为什么不直接复用 offline.evaluate.run_match_experiment

它把一次实验固定成「1 个被测座位 + 3 个对手座位」的**两臂**结构，无法表达
「任意 4 个参赛者同桌」；阶段编排要多批、多桌、任意 4 元组。因此这里直接调用
**同一个生产桌赛驱动** offline.evaluate.drive_match（引擎、MatchSpec、
换座与结果行构造全部复用），只由本包自己排座位——不写第二套规则，也不改
src/ 任何一行。

## 可终止：复用受监管入口

每个场次都在 sitin_process.run_supervised 的**隔离子进程**里跑，有墙钟上限与
**进程组**终止（REVIEW-8 S8-2 的共用入口）。本包只跑仓内冻结策略、不装载任意
候选代码，但仍沿用同一条纪律：卡住的场次不能挂住整个编排，也不能被静默当成
「这桌不存在」。

## 结果核验：R8-4 口径

每个阶段执行后先核对**完整计划矩阵**：计划里的每个场次都要有结果、都要
complete、座位上的人要与计划逐席相同。任何不符即**本轮不可排序并停止**
（StageFailed），绝不把「恰好在某些桌上成功」的行拿去算名次，也不补零。

## 用法

**复跑命令以合同里的为准**：`contract` 会把它们（含 `--frozen-at`）渲染进
`STAGE-CONTRACT.md` §5，并由自测**真的执行**一条来核对 sha。等价的手写形式：

    .venv/bin/python review/llm-guided-heuristic-route-2026-09-15/tools/sitin_stage.py contract --frozen-at 2026-09-15 --out review/llm-guided-heuristic-route-2026-09-15/evidence/3.0-stage
    .venv/bin/python review/llm-guided-heuristic-route-2026-09-15/tools/sitin_stage.py run --frozen-at 2026-09-15 --out review/llm-guided-heuristic-route-2026-09-15/evidence/3.0-stage/run --participants 9
    .venv/bin/python review/llm-guided-heuristic-route-2026-09-15/tools/sitin_stage.py replay --frozen-at 2026-09-15 --tables review/llm-guided-heuristic-route-2026-09-15/evidence/3.0-stage/run/tables.jsonl --expect-run review/llm-guided-heuristic-route-2026-09-15/evidence/3.0-stage/run/run.json --out review/llm-guided-heuristic-route-2026-09-15/evidence/3.0-stage/replay

3.4 的阶段比较（**执行件**：候选 vs 基线、配对场景、缺准入记录直接拒绝）：

    .venv/bin/python review/llm-guided-heuristic-route-2026-09-15/tools/sitin_stage.py compare \
        --contract-file review/llm-guided-heuristic-route-2026-09-15/evidence/3.0-stage/stage-contract.json \
        --candidate seven_pairs_path_value --weights '{"adj.path_log2": 1.0, "adj.closer_bonus": 1.0}' \
        --gate-record review/llm-guided-heuristic-route-2026-09-15/evidence/2.3-gates/gates-seven_pairs_path_value.json \
        --admission-corpus datasets/derived/auto-match-2026-09-06/decisions.jsonl \
        --scenarios 2 --seed-base 2026102000 --budget-tables 40 --table-timeout-sec 180 \
        --out review/llm-guided-heuristic-route-2026-09-15/evidence/3.4-stage-candidate/validation/seven-pairs

    # 编排（生成 → 门禁 → 初筛升级 → 阶段比较 → 冻结）**不在本文件**：
    # tools/sitin_search.py（searchdrv 包）按 command_template 调用上面的 compare。

`--frozen-at` 是必填：合同一旦退回「当天 UTC」，同一条命令换天就换 sha，
「冻结」名不副实；日期还会用 `date.fromisoformat` 真解析（`2026-13-45` 会被拒）。
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
import math
import random
import statistics
import sys
import time
from dataclasses import dataclass, field, replace
import re
from datetime import date as _date
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

#: 合同冻结日期的**规范写法**：显式、零填充的 YYYY-MM-DD（不允许"当天 UTC"这种隐式值）。
FROZEN_AT_PATTERN = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")


def parse_frozen_at(value: Any) -> str:
    """解析并规范化合同冻结日期；非法日期必须失败（复审：不能只看形状）。

    只用正则挡形状是不够的：2026-13-45 形状完全合法。这里用 date.fromisoformat 做**真解析**，
    并要求规范化结果与输入逐字节相同——这样 20260915（Python 也接受的基本格式）
    与 2026-9-15 都会被拒。
    """

    text = str(value or "").strip()
    try:
        parsed = _date.fromisoformat(text)
    except ValueError as error:
        raise ValueError("frozen_at 必须是合法的 YYYY-MM-DD（收到 {0!r}：{1}）".format(value, error))
    if parsed.isoformat() != text:
        raise ValueError("frozen_at 必须写成规范的零填充 YYYY-MM-DD（收到 {0!r}）".format(value))
    return text

REPO = _PROJECT_ROOT
_HERE = Path(__file__).resolve().parent
for _entry in (str(_project_file(_PROJECT_ROOT, REPO / "src")), str(_HERE)):
    if _entry not in sys.path:
        sys.path.insert(0, _entry)

#: 阶段合同 schema（新产物；待汇总包登记进受控文档 §4.9）。
CONTRACT_SCHEMA = "sitin-stage-contract/1"
#: 阶段编排运行记录 schema。
RUN_SCHEMA = "sitin-stage-run/1"
#: 构造夹具 schema（只验证编排语义，不是效果证据）。
FIXTURE_SCHEMA = "sitin-stage-fixture/1"
#: 场次失败记录 schema（阶段不可排序时的落盘理由）。
FAILURE_SCHEMA = "sitin-stage-failure/1"
#: 整场作废记录 schema（官方规则下人数不足，不产生名次）。
VOID_SCHEMA = "sitin-stage-void/1"
#: tables.jsonl 每行 = 契约 §7 的 MatchResult JSON + 本键下的阶段编排信封。
ROW_ENVELOPE_KEY = "sitin_stage"

NEWLINE = chr(10)

SEAT_COUNT = 4
#: 本场总得分名次分（官方《赛事流程》§5.1：+3 / +1 / −1 / −3，同分共享并列区间的平均）。
PLACE_POINTS: Tuple[int, ...] = (3, 1, -1, -3)
#: 逻辑身份到实际座位的基准排列；换座按 rotate_permutation 轮换。
IDENTITY_PERMUTATION: Tuple[int, int, int, int] = (0, 1, 2, 3)

# 证据级别（根 AGENTS.md §3）。合同里每个语义路径都必须带其中一个。
LEVEL_OFFICIAL = "官方已确认"
LEVEL_OBSERVED = "当前观察"
LEVEL_ENGINEERING = "工程建议"
LEVEL_ASSUMED = "待确认假设"
LEVELS = (LEVEL_OFFICIAL, LEVEL_OBSERVED, LEVEL_ENGINEERING, LEVEL_ASSUMED)

#: 官方指南快照（v34）：规则引文必须指向**具体行**，由 verify_rule_citations 逐条核对。
GUIDE_REF = "doc/references/official-guide-v34-content.txt"
GUIDE_VERSION = "v34（2026-09-15 入库快照）"
#: 赛事流程（多阶段晋级结构）的本地整理件；结构类规则引自它，逐条给出小节号。
FLOW_REF = "doc/official-tournament-flow-2026-09-03.md"

#: 本包实现的官方规则 → 快照**行号 + 原文片段**。
#:
#: 纪律：引文只写在合同里而不校验，等于没有出处（本项目反复吃过「当时读到过」的亏）。
#: 因此每条都带行号与原文片段，verify_rule_citations 会真的打开快照逐条比对；
#: 快照换版本或行号漂移时 --check 必须失败，而不是静默沿用旧引文。
RULES_VERIFIED: Tuple[Dict[str, Any], ...] = (
    {"key": "final.overtime_until_unique", "line": 375,
     "excerpt": "决赛轮常规场次打完若 1-4 名总得分有并列 → running 态自动加赛并账循环（无上限）",
     "rule": "决赛同分自动加赛，且场次无上限"},
    {"key": "final.overtime_no_place_points", "line": 377,
     "excerpt": "决赛轮纯总得分、任何同分加赛至 1-4 名两两不同，加赛场不产生名次分/白板数",
     "rule": "加赛场不产生名次分与白板数"},
    {"key": "ranking.tie_break_chain", "line": 377,
     "excerpt": "键序 total_score → place_points → god_count → user_id（字典序兜底），三键独立永不相加",
     "rule": "晋级轮三键独立、末位 user_id 字典序兜底"},
    {"key": "ranking.place_points_values", "line": 377,
     "excerpt": "名次分每场 1 位 +3 / 2 位 +1 / 3 位 −1 / 4 位 −3",
     "rule": "名次分按本场位次取 +3 / +1 / −1 / −3"},
    {"key": "ranking.place_points_tie_rule", "line": 377,
     "excerpt": "本场同分共享并列区间平均、不进总得分",
     "rule": "本场同分共享并列区间平均，且名次分不进总得分"},
    {"key": "ranking.god_count_offline", "line": 377,
     "excerpt": "不可经事件流复算，轮空积 0",
     "rule": "白板获取数不可经事件流复算；轮空积 0"},
    {"key": "ladder_downgrade.dynamic", "line": 369,
     "excerpt": "stage.total 随降档/翻转动态收缩，不可按创建时规划轮次",
     "rule": "阶段总数随降档/翻转动态收缩；不可按创建时规划预判轮次"},
)


def verify_rule_citations(*, repo: Path = REPO,
                          citations: Optional[Sequence[Mapping[str, Any]]] = None) -> List[str]:
    """逐条核对规则引文：打开官方快照，确认**被引用的那一行**真的含有该原文片段。

    citations 省略时核对模块内建的 RULES_VERIFIED；传入合同的 rule_citations 时，
    核对的是**交付合同文件里的那几条**。初版只核内建表，于是「交付合同被篡改引文」
    仍然判 ok —— 那等于"逐条可核"只对自己那张表有效（复审指出的 fail-open）。
    """

    items = list(citations) if citations is not None else list(RULES_VERIFIED)
    if not items:
        return ["没有可核对的规则引文：rule_citations 为空"]
    problems: List[str] = []
    cache: Dict[str, List[str]] = {}
    for item in items:
        relative = str(item.get("file") or GUIDE_REF)
        if relative not in cache:
            path = Path(repo) / relative
            cache[relative] = (path.read_text(encoding="utf-8").splitlines()
                               if path.exists() else [])
            if not cache[relative]:
                problems.append("规则 {0} 引用的快照不存在或为空：{1}".format(
                    item.get("key"), relative))
                continue
        lines = cache[relative]
        try:
            index = int(item["line"]) - 1
        except (KeyError, TypeError, ValueError):
            problems.append("规则 {0} 的 line 不是整数：{1!r}".format(
                item.get("key"), item.get("line")))
            continue
        if index < 0 or index >= len(lines):
            problems.append("规则 {0} 引用的第 {1} 行超出快照范围（共 {2} 行）".format(
                item.get("key"), item.get("line"), len(lines)))
            continue
        if str(item.get("excerpt") or "") not in lines[index]:
            problems.append("规则 {0} 的引文与 {1} 第 {2} 行不符".format(
                item.get("key"), relative, item.get("line")))
    return problems


def verify_contract_citations(contract: Mapping[str, Any], *, repo: Path = REPO) -> List[str]:
    """核对**合同文件自带**的引文，并与内建清单逐字段比对（两边都被钉住）。

    只核内建表会漏掉「交付合同被改」；只核合同又允许悄悄改内建表。
    因此两边都比：① 合同里每条引文能在官方快照对应行找到原文；
    ② 合同引文与内建清单在键集合与键、文件、行号、原文、规则文字上逐一相等。
    """

    citations = list(contract.get("rule_citations") or [])
    problems = verify_rule_citations(repo=repo, citations=citations)
    builtin = {str(item["key"]): item for item in RULES_VERIFIED}
    seen = set()
    for item in citations:
        key = str(item.get("key"))
        if key in seen:
            problems.append("合同引文里出现重复键：{0}".format(key))
        seen.add(key)
        raw = builtin.get(key)
        if raw is None:
            problems.append("合同引文 {0} 不在内建清单里".format(key))
            continue
        # 内建清单里 file 是隐含的（统一指官方快照），补默认值后再逐字段比。
        expected = dict(raw)
        expected.setdefault("file", GUIDE_REF)
        for field in ("file", "line", "excerpt", "rule"):
            if item.get(field) != expected[field]:
                problems.append("合同引文 {0} 的 {1} 与内建清单不一致：合同 {2!r}，内建 {3!r}".format(
                    key, field, item.get(field), expected[field]))
    for key in sorted(set(builtin) - seen):
        problems.append("内建清单里的引文 {0} 未登记进合同".format(key))
    return problems
FLOW_SOURCE = "官方门户 flow-stage；流程基线 2026-09-03 抓取，指南 v27（2026-09-09 同步）"
OBSERVED_EVENT = ("t_dee58824c308「9月4日杭麻竞技一测」观察：M=10 / Rounds=16 / BaseScore=1 / "
                  "YouCaiBiKao=false（2026-09-05 抓取）")
API_TIE_SOURCE = ("官方 event-api 变更说明（v7）：三键全同以 user_id 字典序兜底；"
                  "客户端应采用平台返回的 rank，不自行覆盖")
GOD_COUNT_SOURCE = ("官方《赛事流程》§5.2：白板获取数含平台内部配牌时点，参赛方无法只靠实时事件"
                    "准确复算，平台排名值为权威")

#: 允许进面板的**冻结稳定策略**白名单。
#:
#: 为什么不用 scripts/evaluate.py 的 build_policy：该脚本模块级 import 候选注册表
#: （hangma_bot.policy.heuristics），会装载**全部已注册候选模块**（REVIEW-9「装载有界」
#: 已就此提醒）。阶段编排面板只允许稳定策略，因此这里显式白名单 + 本地装配：
#: 既避免在检查之前装载候选，也让「本包不可能跑到未准入候选」成为**构造保证**。
PANEL_POLICY_NAMES: Tuple[str, ...] = (
    "weighted_heuristic_v2",
    "weighted_heuristic_v1",
    "weighted_heuristic_v2_white_guard",
    "safe_fallback",
)

#: 与 scripts/evaluate.py / sitin_scheduler 同口径的动作窗口配置（秒）。
DEFAULT_TIMING: Dict[str, float] = {"peng_timeout_sec": 1.0, "chi_timeout_sec": 1.0,
                                    "discard_timeout_sec": 3.0}

#: 官方档位表（《赛事流程》§2）。min_participants 取该档下界；档位按人数降序匹配。
LADDER: Tuple[Dict[str, Any], ...] = (
    {
        "min_participants": 17,
        "stages": (
            {"name": "海选", "role": "qualify", "kind": "qualifying_global", "target": 16},
            {"name": "16强", "role": "qualify", "kind": "group_round", "groups": 4,
             "group_size": 4, "group_advance": 2},
            {"name": "8强", "role": "qualify", "kind": "group_round", "groups": 2,
             "group_size": 4, "group_advance": 2},
            {"name": "决赛", "role": "final", "kind": "final", "group_size": 4},
        ),
    },
    {
        "min_participants": 9,
        "stages": (
            {"name": "海选", "role": "qualify", "kind": "qualifying_global", "target": 8},
            {"name": "8强", "role": "qualify", "kind": "group_round", "groups": 2,
             "group_size": 4, "group_advance": 2},
            {"name": "决赛", "role": "final", "kind": "final", "group_size": 4},
        ),
    },
    {
        "min_participants": 5,
        "stages": (
            {"name": "海选资格轮", "role": "qualify", "kind": "qualifying_global", "target": 4},
            {"name": "决赛", "role": "final", "kind": "final", "group_size": 4},
        ),
    },
    {
        "min_participants": 4,
        "stages": (
            {"name": "决赛", "role": "final", "kind": "final", "group_size": 4},
        ),
    },
)
#: 少于该人数整场赛事作废、不产生名次（官方 §2）。
VOID_BELOW = 4


# ---------------------------------------------------------------------------
# 1. 通用小工具
# ---------------------------------------------------------------------------


def sibling(name: str):
    """按文件路径加载同目录工具模块（与 sitin_l1_driver / sitin_scheduler 同法）。"""

    spec = importlib.util.spec_from_file_location(name, _project_file(_PROJECT_ROOT, _HERE / (name + ".py")))
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def derive_seed(base: int, *tags: str) -> int:
    """从基准种子与标签派生**确定性**种子。

    发牌只由 seed 决定，标签只是注释（sitin_scheduler.root_set_id_of 的第一条教训）；
    因此派生必须进 seed、并且可复算，否则「重跑同一面板」会悄悄换牌山。
    """

    blob = "|".join([str(int(base))] + [str(tag) for tag in tags])
    return int(hashlib.sha256(blob.encode("utf-8")).hexdigest()[:12], 16)


# ---------------------------------------------------------------------------
# 1b. 根描述符（R9/A3）：**唯一**根身份与执行种子（普通条件生成 ↔ 指定根入口共用）
# ---------------------------------------------------------------------------
#
# 缺陷（R8 复审 A3 · P1）：普通条件生成用 derive_seed(panel_seed,"prefix",根身份)
# 得到实际执行的牌山种子，家族登记与补根却用 derive_seed(…,"family",子场景,情景,…)
# **另算一个**种子；两边"同名根"其实不是同一座牌山，第二候选补同根无法逐字复现。
# 同一条缺陷的 A2 侧面：旧根身份 av-eval-{谓词}:{谓词}:rootNNN 不含对手情景与实际
# 种子，H/M 与跨种子实例在根名去重处互相吞并（8 个评价项只剩 4 个 H 根）。
#
# 本节的修法：把"根"表示成**唯一描述符**（生成器版本 × 子场景 × 对手情景 × 实际
# 种子 × 根索引），身份字符串与执行种子都由同五个维度派生——普通生成、登记、补根
# 三处只可能给出同一个值。候选身份**不进**描述符（候选属于评价实例，见
# sitin_search.av_instance_identity_key 的 candidate 维）。

#: 完整根身份 schema（v2）：字符串本身携带全部身份维度，去重不依赖调用方自觉。
ROOT_IDENTITY_SCHEMA = "sitin-root-identity/2"
#: 旧根身份 schema 记号（只用于**显式**识别历史数据；不做静默迁移）。
ROOT_IDENTITY_LEGACY_SCHEMA = "sitin-root-identity/1"
#: 根描述符 schema（身份 + 执行种子 + 复现参数）。
ROOT_DESCRIPTOR_SCHEMA = "sitin-root-descriptor/2"
#: 共享派生记号：五个身份维度 → 执行种子（两处入口同一条式子）。
ROOT_SEED_DERIVATION_SHARED = "shared-root-v2"
#: 历史普通生成器派生记号：derive_seed(panel_seed, "prefix", 旧根身份)。
#: 历史根的种子只有按**原生成器**式子还原才算"逐字沿用"，不得静默赋新种子。
ROOT_SEED_DERIVATION_LEGACY_PREFIX = "prefix-v1"
#: 旧根身份形状：{标签}:{谓词}:rootNNN（标签通常是 av-eval-{谓词}）。
_ROOT_IDENTITY_LEGACY_RE = re.compile(
    r"^(?P<label>[^:]+):(?P<predicate>[^:]+):root(?P<index>\d+)$")
#: v2 根身份形状：av-eval-{谓词}:{生成器}:{情景}:s{种子}:rootNNN。
_ROOT_IDENTITY_V2_RE = re.compile(
    r"^(?P<label>[^:]+):(?P<predicate>[^:]+):(?P<generator>[^:]+):"
    r"(?P<mix>[^:]+):s(?P<seed>\d+):root(?P<index>\d+)$")


def root_identity(*, generator: Any, sub_scenario: Any, opponent_mix: Any,
                  panel_seed: Any, root_index: Any) -> str:
    """完整根身份：av-eval-{子场景}:{生成器}:{情景}:s{实际种子}:root{NNN}。

    五个维度缺一即身份漂移：少了情景 → H/M 同名互吞（A2）；少了种子 → 跨种子同索引
    被当成同一个根（A2）；少了生成器版本 → 夹具根与真实根、两代生成器的产物同 ID
    （无法判断"这条证据是谁跑的"）。
    """

    index = int(root_index)
    if index < 0:
        raise ValueError("根序号必须 ≥ 0，得到 {0}（不静默取绝对值）".format(index))
    return "av-eval-{0}:{0}:{1}:{2}:s{3}:root{4:03d}".format(
        str(sub_scenario), str(generator), str(opponent_mix), int(panel_seed), index)


def root_seed(*, generator: Any, sub_scenario: Any, opponent_mix: Any,
              panel_seed: Any, root_index: Any) -> int:
    """根执行种子：只由**完整根身份**的五个维度派生（普通生成与补根共用）。

    同身份 ⇒ 同种子 ⇒ 同牌山；这是"补根跑的是同一个根"的必要条件（A3）。
    """

    return int(derive_seed(int(panel_seed), "root", str(generator),
                           str(sub_scenario), str(opponent_mix), "root",
                           str(int(root_index))))


def root_descriptor(*, generator: Any, sub_scenario: Any, opponent_mix: Any,
                    panel_seed: Any, root_index: Any) -> Dict[str, Any]:
    """根描述符：身份 + 执行种子 + 复现参数（登记/补根/内容摘要的唯一输入）。"""

    index = int(root_index)
    return {
        "schema": ROOT_DESCRIPTOR_SCHEMA,
        "generator": str(generator),
        "sub_scenario": str(sub_scenario),
        "opponent_mix": str(opponent_mix),
        "panel_seed": int(panel_seed),
        "root_index": index,
        "root_id": root_identity(generator=generator, sub_scenario=sub_scenario,
                                 opponent_mix=opponent_mix, panel_seed=panel_seed,
                                 root_index=index),
        "root_seed": root_seed(generator=generator, sub_scenario=sub_scenario,
                               opponent_mix=opponent_mix, panel_seed=panel_seed,
                               root_index=index),
        "seed_derivation": ROOT_SEED_DERIVATION_SHARED,
        "root_identity_schema": ROOT_IDENTITY_SCHEMA,
    }


def parse_root_identity(root_id: Any) -> Optional[Dict[str, Any]]:
    """解析 v2 根身份 → 五个维度；不是 v2 形状返回 None（**不猜**旧格式）。"""

    match = _ROOT_IDENTITY_V2_RE.match(str(root_id or ""))
    if match is None:
        return None
    return {"root_identity_schema": ROOT_IDENTITY_SCHEMA,
            "root_id": str(root_id),
            "generator": match.group("generator"),
            "sub_scenario": match.group("predicate"),
            "opponent_mix": match.group("mix"),
            "panel_seed": int(match.group("seed")),
            "root_index": int(match.group("index")),
            "seed_derivation": ROOT_SEED_DERIVATION_SHARED}


def parse_legacy_root_identity(root_id: Any) -> Optional[Dict[str, Any]]:
    """解析**旧**根身份（v1）→ {label, predicate, root_index}；不是旧形状返回 None。

    只用于显式识别历史数据（拒绝继承 / 按原生成器还原种子）；调用方不得据此静默
    把历史根当成当前根：v1 不含情景与实际种子，无法与 v2 身份等价。
    """

    match = _ROOT_IDENTITY_LEGACY_RE.match(str(root_id or ""))
    if match is None:
        return None
    return {"root_identity_schema": ROOT_IDENTITY_LEGACY_SCHEMA,
            "root_id": str(root_id),
            "root_label": match.group("label"),
            "sub_scenario": match.group("predicate"),
            "root_index": int(match.group("index")),
            "seed_derivation": ROOT_SEED_DERIVATION_LEGACY_PREFIX}


def legacy_prefix_root_seed(panel_seed: Any, legacy_root_id: Any) -> int:
    """历史普通生成器的执行种子：derive_seed(panel_seed, "prefix", 旧根身份)。

    与普通生成器旧实现逐字同式——"历史普通根按原生成器恢复"只有这一条路，
    另算一个种子等于换了一座牌山。
    """

    return int(derive_seed(int(panel_seed), "prefix", str(legacy_root_id)))


def root_index_of(root_id: Any) -> Optional[int]:
    """根身份末尾的 rootNNN 序号；不可解析返回 None（不猜）。"""

    match = re.search(r"root(\d+)$", str(root_id or ""))
    return int(match.group(1)) if match else None


def root_set_id_of(roots: Sequence[Any]) -> str:
    """根组集合身份：**按 seed** 取哈希。

    与 sitin_scheduler.root_set_id_of 同口径（同一构造：换行连接 seeds 后取 sha256 前 12 位）。
    本包不 import 调度器（避免把候选注册表拖进来），因此**用测试断言两者相等**，
    而不是靠「看起来一样」。
    """

    items = [str(root["seed"]) if isinstance(root, Mapping) else str(root) for root in roots]
    return "roots-" + hashlib.sha256(NEWLINE.join(items).encode("utf-8")).hexdigest()[:12]


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def slug(text: str) -> str:
    """安全目录名：身份里带冒号/括号等字符时不能直接当路径（本项目已有一次教训）。"""

    safe = "".join(ch if (ch.isalnum() or ch in "-_") else "-" for ch in str(text))
    return safe[:60] + "-" + sha256_text(str(text))[:8]


def rotate_permutation(index: int) -> Tuple[int, int, int, int]:
    """第 index 桌的换座排列：permutation[逻辑身份] = (index + 逻辑身份) % 4。

    **工程建议**：官方未规定离线实验的座位分配，这是本包声明的确定性轮换
    （同一参赛者在不同场次轮换座位，降低「只赢在某个座位」的假象）。
    """

    shift = int(index) % SEAT_COUNT
    return tuple((shift + logical) % SEAT_COUNT for logical in range(SEAT_COUNT))  # type: ignore[return-value]


def _lookup_path(data: Mapping[str, Any], dotted: str) -> Any:
    current: Any = data
    for part in dotted.split("."):
        if not isinstance(current, Mapping) or part not in current:
            raise KeyError(dotted)
        current = current[part]
    return current


# ---------------------------------------------------------------------------
# 2. 阶段合同
# ---------------------------------------------------------------------------


def default_contract(
    *,
    ruleset_version: str,
    base_score: int,
    you_cai_bi_kao: bool,
    rounds_per_game: int,
    clock_mode: str = "logical",
    panel_seed: int = 20260915,
    panel_policy: str = "weighted_heuristic_v2",
    tables_per_batch: int = 2,
    batches: int = 2,
    tables_per_group: int = 2,
    tables_in_final: int = 1,
    max_overtime: int = 3,
    table_timeout_sec: float = 300.0,
    step_limit: int = 100000,
    frozen_at: str,
) -> Dict[str, Any]:
    """组装阶段合同；所有字段显式给出，不做默认推断。

    Rounds（rounds_per_game）与规则版本必须由调用方给出（与 sitin_config 同一纪律：
    配置语义的权威来源是显式声明，不是本工具的推断）。
    **frozen_at 同样是必填且无默认值**：合同一旦取「当天 UTC」，同一条复跑命令
    在不同日期就会产出不同 sha，「冻结」名不副实（复审 #16）。
    """

    if panel_policy not in PANEL_POLICY_NAMES:
        raise ValueError("面板策略 {0!r} 不在冻结白名单 {1} 内".format(panel_policy, PANEL_POLICY_NAMES))
    resolved_frozen_at = parse_frozen_at(frozen_at)   # 非法日期在这里就失败
    contract: Dict[str, Any] = {
        "schema": CONTRACT_SCHEMA,
        "frozen_at": resolved_frozen_at,
        "target": {
            "goal": "官方阶段格式下晋级（海选全场排名 / 四人晋级组 / 决赛各自成立，不互相替代）",
            "verification_ladder": "9 人档：海选 → 8强（2 组 × 4 人，每组前 2）→ 决赛",
            "why_this_ladder": (
                "最小可覆盖：轮空、全场排名、组内排名与组间隔离、阶段清零、决赛加赛；"
                "档位表本身按到场人数自动定档，本验证只是其中一档"),
            "actual_event_parameters": "待赛事方确认（见 unresolved）",
        },
        "ladder": [
            {"min_participants": row["min_participants"],
             "stages": [dict(stage) for stage in row["stages"]]}
            for row in LADDER
        ],
        "void_below": VOID_BELOW,
        # 官方：阶段结构**不是**开赛时定档一次就固定——阶段间会按"已确认到位人数"再次降档，
        # 阶段总数（stage.total）随之收缩。本包离线编排**不模拟重新确认与降档**（见 unresolved）。
        "ladder_downgrade": {
            "when": "下一阶段开赛前，按已确认到位的晋级者/候补人数再次定档",
            "rules": [
                {"confirmed": "少于 4 人", "behaviour": "整场赛事作废，无最终名次"},
                {"confirmed": "4—8 人", "behaviour": "直接降为 4 人决赛；多余人员按上一阶段名次取前 4"},
                {"confirmed": "9—16 人", "behaviour": "降为 8 强规模"},
                {"confirmed": "满足原计划", "behaviour": "按原阶段继续"},
            ],
            "stage_total": "stage.total 随降档/翻转动态收缩，不可按创建时规划轮次（官方原文）",
            "client_rule": "阶段数可能因后续确认人数不足而收缩；客户端必须以当前返回的 status 与 stage 为准",
            "offline_handling": "offline_modeled=false：本包的面板假设晋级者全部按时确认，阶段结构按首次定档执行",
        },
        "batch": {
            "table_size": SEAT_COUNT,
            "bye_score": 0,
            "tables_per_batch": int(tables_per_batch),
            "batches": int(batches),
            "games_per_participant_per_batch": 1,
            "tables_per_batch_rule": "实际整桌数 = min(tables_per_batch, 本批人数 // 4)；余下不足一桌者该批轮空",
            "pairing": "每批按阶段种子做确定性洗牌后每 4 人一桌；不足一桌者该批轮空",
            "bye_bookkeeping": "轮空计 0 分，且不计名次分与白板数",
        },
        "group": {
            "group_size": SEAT_COUNT,
            "group_advance": 2,
            "seeding": "上一阶段名次蛇形分组",
            "avoid_previous_groupmates": "尽力避免上一阶段同组者过早重逢（本包用确定性贪心交换实现）",
            "cross_group_comparison": False,
            "next_stage_seed_order": "组内名次优先、组序号次序（不跨组比较分数）",
            "tables_per_group": int(tables_per_group),
        },
        "final": {
            "keys": ["total_score"],
            "overtime_until_unique": True,
            "overtime_rule": "任意两人总得分相同则四人加赛，得分并入决赛总账后重排，直到 1—4 名两两不同",
            "overtime_no_place_points": True,
            "tables_in_final": int(tables_in_final),
            "max_overtime": int(max_overtime),
        },
        "ranking": {
            "qualify_keys": ["total_score", "place_points", "god_count"],
            "final_keys": ["total_score"],
            "place_points_values": list(PLACE_POINTS),
            "place_points_tie_rule": "本场同分者共享并列名次区间的平均名次分",
            "place_points_excluded_from_total": True,
            "tie_fallback": "平台内部顺序（指南 v34：user_id 字典序兜底）",
            "score_reset_per_stage": True,
            "god_count_offline": "offline_unavailable",
        },
        "advance": {
            "primary": "上一阶段第 1..G 名晋级",
            "backup": "第 G+1..2G 名进入候补池；人数不足 2G 时其余未晋级者全部列为候补",
            "reconfirm_each_stage": "晋级者与候补每个新阶段前都要重新确认到位（本包离线不模拟确认）",
        },
        "panel": {
            "policy_pool": [panel_policy],
            "homogeneous": True,
            "table_runner": "offline.evaluate.drive_match（生产模拟驱动）",
            "supervision": "sitin_process.run_supervised（进程组终止 + 墙钟上限）",
            "note": "工程情景面板：不含候选、不含未准入权重；不构成效果证据，也不代表官方对手分布",
        },
        "versions": {
            "ruleset_version": ruleset_version,
            "base_score": int(base_score),
            "you_cai_bi_kao": bool(you_cai_bi_kao),
            "rounds_per_game": int(rounds_per_game),
            "clock_mode": clock_mode,
            "config_fingerprint": "运行时由 sitin_config 计算并写入 run.json",
        },
        "seeds": {
            "panel_seed": int(panel_seed),
            "derivation": "seed = sha256(panel_seed | 阶段标签 | 场次标签) 前 12 位十六进制",
            "scenario_id": "s{阶段}t{序号}-{seed}",
        },
        "stop": {
            "max_overtime": int(max_overtime),
            "table_timeout_sec": float(table_timeout_sec),
            "step_limit": int(step_limit),
            "on_table_failure": "该阶段不可排序并停止：不补零、不静默删行、不继续推进",
            "on_void": "到位人数少于 {0} 人时整场作废，不产生名次".format(VOID_BELOW),
        },
        "rule_citations": [
            {"key": item["key"], "rule": item["rule"], "file": GUIDE_REF,
             "version": GUIDE_VERSION, "line": int(item["line"]), "excerpt": item["excerpt"]}
            for item in RULES_VERIFIED
        ],
        "provenance": {
            "rule_citations": {
                "level": LEVEL_OFFICIAL,
                "source": "每条引文带 {0} 的行号与原文片段；--check 会打开快照逐条比对"
                          "（verify_rule_citations）".format(GUIDE_REF)},
            "target": {"level": LEVEL_ENGINEERING, "source": "PLAN-REVISION §2；本包选定的验证档位"},
            "ladder": {"level": LEVEL_OFFICIAL, "source": "{0} §2（{1}）".format(FLOW_REF, FLOW_SOURCE)},
            "void_below": {"level": LEVEL_OFFICIAL, "source": "{0} §2".format(FLOW_REF)},
            "batch.table_size": {"level": LEVEL_OFFICIAL, "source": "{0} §3.1".format(FLOW_REF)},
            "batch.bye_score": {"level": LEVEL_OFFICIAL,
                                "source": "{0} §3.1「该批 0 分」；{1} 第 377 行「轮空积 0」；"
                                          "两条由 verify_rule_citations 逐条核对原文".format(
                                              FLOW_REF, GUIDE_REF)},
            "batch.tables_per_batch_rule": {
                "level": LEVEL_OFFICIAL,
                "source": "{0} §3.1「每桌 4 人」「不足一桌的少数参赛者该批轮空」——"
                          "整桌数只能是 ⌊人数/4⌋；本包取 min(上限, ⌊人数/4⌋)".format(FLOW_REF)},
            "batch.pairing": {"level": LEVEL_OFFICIAL,
                              "source": "{0} §3.1「同桌组合随机、不同批可能再次相遇」；"
                                        "确定性洗牌是本包对该随机的可复算实现".format(FLOW_REF)},
            "batch.tables_per_batch": {"level": LEVEL_ENGINEERING,
                                       "source": "官方 M 由组委会配置；本包面板规模是工程选择"},
            "batch.games_per_participant_per_batch": {
                "level": LEVEL_ENGINEERING, "source": "本包面板：每批每位参赛者最多 1 个场次"},
            "group.group_size": {"level": LEVEL_OFFICIAL, "source": "{0} §3.2".format(FLOW_REF)},
            "group.group_advance": {"level": LEVEL_OFFICIAL, "source": "{0} §3.2".format(FLOW_REF)},
            "group.seeding": {"level": LEVEL_OFFICIAL, "source": "{0} §3.2".format(FLOW_REF)},
            "group.avoid_previous_groupmates": {
                "level": LEVEL_ASSUMED,
                "source": "{0} §3.2 只说「尽量避免」；平台算法未公开，本包用声明的贪心近似".format(FLOW_REF)},
            "group.cross_group_comparison": {"level": LEVEL_OFFICIAL,
                                             "source": "{0} §3.2「组与组之间的分数不互相比较」".format(FLOW_REF)},
            "group.next_stage_seed_order": {
                "level": LEVEL_ASSUMED,
                "source": "官方只说组间分数不互相比较，未公开下一阶段种子怎么在组间排序；"
                          "本包声明为「组内名次优先、组序号次序」，两种读法见 unresolved"},
            "group.tables_per_group": {"level": LEVEL_ENGINEERING,
                                       "source": "官方「组内循环」未公布场次数；本包声明每组场次数"},
            "final.keys": {"level": LEVEL_OFFICIAL, "source": "{0} §5.2".format(FLOW_REF)},
            "final.overtime_until_unique": {
                "level": LEVEL_OFFICIAL,
                "source": "{0} §3.3；{1} 第 375 行「决赛轮常规场次打完若 1-4 名总得分有并列 → "
                          "running 态自动加赛并账循环（无上限）」（引文可核）".format(FLOW_REF, GUIDE_REF)},
            "final.overtime_rule": {
                "level": LEVEL_OFFICIAL,
                "source": "{0} 第 375 行（加赛并账、无上限）与第 377 行"
                          "「决赛轮纯总得分、任何同分加赛至 1-4 名两两不同，"
                          "加赛场不产生名次分/白板数」（引文可核）".format(GUIDE_REF)},
            "final.overtime_no_place_points": {
                "level": LEVEL_OFFICIAL,
                "source": "{0} 第 377 行「加赛场不产生名次分/白板数」（引文可核）".format(GUIDE_REF)},
            "final.max_overtime": {"level": LEVEL_ENGINEERING,
                                   "source": "官方加赛没有上限；本包的上限是工程保护，不是官方规则"},
            "ranking.qualify_keys": {
                "level": LEVEL_OFFICIAL,
                "source": "{0} §5.1；{1} 第 377 行「键序 total_score → place_points → god_count → "
                          "user_id（字典序兜底），三键独立永不相加」（引文可核）".format(FLOW_REF, GUIDE_REF)},
            "ranking.final_keys": {"level": LEVEL_OFFICIAL, "source": "{0} §5.2".format(FLOW_REF)},
            "ranking.place_points_values": {
                "level": LEVEL_OFFICIAL,
                "source": "{1} 第 377 行「名次分每场 1 位 +3 / 2 位 +1 / 3 位 −1 / 4 位 −3」"
                          "（引文可核）；{0} §5.1".format(FLOW_REF, GUIDE_REF)},
            "ranking.place_points_tie_rule": {
                "level": LEVEL_OFFICIAL,
                "source": "{1} 第 377 行「本场同分共享并列区间平均、不进总得分」（引文可核）；"
                          "{0} §5.1".format(FLOW_REF, GUIDE_REF)},
            "ranking.place_points_excluded_from_total": {
                "level": LEVEL_OFFICIAL,
                "source": "{0} 第 377 行「不进总得分」（引文可核）".format(GUIDE_REF)},
            "ranking.tie_fallback": {"level": LEVEL_OFFICIAL, "source": API_TIE_SOURCE},
            "ranking.score_reset_per_stage": {"level": LEVEL_OFFICIAL, "source": "{0} §5.1".format(FLOW_REF)},
            "ranking.god_count_offline": {
                "level": LEVEL_OFFICIAL,
                "source": "{0} 第 377 行「白板获取数口径 = 配牌扫全手（庄家含第 14 张直抽）+ "
                          "每次墙摸到白板（含杠上摸），不可经事件流复算」（引文可核）；"
                          "{1}".format(GUIDE_REF, GOD_COUNT_SOURCE)},
            "ladder_downgrade.when": {
                "level": LEVEL_OFFICIAL,
                "source": "{0} §2「可能在阶段间自动降档」、§4 异常人数处理表".format(FLOW_REF)},
            "ladder_downgrade.rules": {
                "level": LEVEL_OFFICIAL, "source": "{0} §4 异常人数处理表".format(FLOW_REF)},
            "ladder_downgrade.stage_total": {
                "level": LEVEL_OFFICIAL,
                "source": "{1} 第 369 行「stage.total 随降档/翻转动态收缩，不可按创建时规划轮次」"
                          "（引文可核）；{0} §2、§6.2".format(FLOW_REF, GUIDE_REF)},
            "ladder_downgrade.client_rule": {
                "level": LEVEL_OFFICIAL, "source": "{0} §2".format(FLOW_REF)},
            "ladder_downgrade.offline_handling": {
                "level": LEVEL_ENGINEERING,
                "source": "本包声明：面板不模拟阶段间重新确认与降档（缺口写进 unresolved）"},
            "advance.primary": {"level": LEVEL_OFFICIAL, "source": "{0} §4".format(FLOW_REF)},
            "advance.backup": {"level": LEVEL_OFFICIAL, "source": "{0} §4".format(FLOW_REF)},
            "advance.reconfirm_each_stage": {"level": LEVEL_OFFICIAL, "source": "{0} §4".format(FLOW_REF)},
            "panel": {"level": LEVEL_ENGINEERING,
                      "source": "PLAN-REVISION §2「不给未知对手分布编造权重」；本包声明的工程面板"},
            "versions": {"level": LEVEL_OBSERVED,
                         "source": "evidence/1.3-config/config.json 的指纹口径；" + OBSERVED_EVENT},
            "seeds": {"level": LEVEL_ENGINEERING, "source": "本包：面板种子与派生规则（可复跑）"},
            "stop": {"level": LEVEL_ENGINEERING,
                     "source": "本包：墙钟上限与失败处理；官方未规定离线编排的停止条件"},
        },
        "unresolved": [
            {"item": "正式赛事的到位人数、M、Rounds、底分与各阶段开赛时间",
             "status": "待确认假设",
             "basis": "{0} §9「仍待赛事方或实际赛程确认」".format(FLOW_REF),
             "observation": OBSERVED_EVENT,
             "impact": "本包的 Rounds/场次数是面板参数，不能当作正式赛事参数；"
                       "正式阶段比较前必须用运行时 config 重新冻结"},
            {"item": "离线无法复现 god_count（白板获取数）",
             "status": "待确认假设",
             "basis": GOD_COUNT_SOURCE,
             "observation": "offline 的 MatchResult 不记录配牌与牌墙白板数",
             "impact": "离线阶段排序只有两键；同两键时的名次是未解决边界，"
                       "平台 rank 才是权威。本包对未解决边界显式标注，不假装三键排序"},
            {"item": "平台「尽量避免上一阶段同组者重逢」的具体算法",
             "status": "待确认假设",
             "basis": "{0} §3.2 只有「尽量避免」的表述".format(FLOW_REF),
             "observation": "无公开算法",
             "impact": "本包用声明的确定性贪心交换近似，并报告交换前后的重逢对数"},
            {"item": "平台海选同桌随机组合的抽样方式",
             "status": "待确认假设",
             "basis": "{0} §3.1「同桌组合随机」".format(FLOW_REF),
             "observation": "无公开算法",
             "impact": "本包用声明的确定性洗牌实现该随机；换种子即换面板，必须重新冻结"},
            {"item": "官方加赛无场次上限",
             "status": "待确认假设",
             "basis": "{0} §3.3".format(FLOW_REF),
             "observation": "本包 max_overtime 是工程保护",
             "impact": "触及上限时该次运行标注未解决，不宣称名次已唯一"},
            {"item": "组内赛之后、下一阶段的种子序怎么在组间排序",
             "status": "待确认假设",
             "basis": "{0} §3.2「组与组之间的分数不互相比较」；但 §5.1 又把 16 强/8 强"
                      "列入三键排序阶段".format(FLOW_REF),
             "observation": "两种读法都说得通：① 只在组内排名（本包采用，声明为组内名次优先、"
                            "组序号次序）；② 平台仍给出跨组三键名次用于种子",
             "impact": "读法不同会改变蛇形分组与「尽量避免重逢」的结果；本包的声明写在合同里，"
                       "换读法必须改合同并重新冻结"},
            {"item": "阶段间重新确认与降档/翻转没有被离线编排模拟",
             "status": "待确认假设",
             "basis": "{0} §2「阶段数可能因后续确认人数不足而收缩」、§4 异常人数处理表；"
                      "{1} 第 369 行「stage.total 随降档/翻转动态收缩」".format(FLOW_REF, GUIDE_REF),
             "observation": "本包面板假设晋级者全部按时确认，阶段结构按首次定档执行"
                            "（合同 ladder_downgrade.offline_handling = offline_modeled=false）",
             "impact": "真实赛事的阶段结构可能在阶段间收缩；离线阶段比较的结论必须限定在"
                       "「不降档」这一情景下，不得外推为官方晋级概率。"
                       "要模拟降档需要引入确认到位模型（属新工作，本轮不做）"},
            {"item": "官方对手分布与自由赛池构成",
             "status": "待确认假设",
             "basis": "PLAN-REVISION §2、§7 第 3 条",
             "observation": "本包面板是同质稳定策略",
             "impact": "面板结果只描述该面板；不得外推为官方晋级概率或对手强弱"},
        ],
    }
    return contract


def validate_contract(contract: Mapping[str, Any]) -> List[str]:
    """核验阶段合同；返回问题清单（空列表 = 通过）。

    纪律：**每个语义块都必须有出处**、每条 provenance 路径必须真实存在、
    unresolved 不能为空（官方确实还有未确认项，写空就是掩盖）。
    """

    problems: List[str] = []
    if contract.get("schema") != CONTRACT_SCHEMA:
        problems.append("schema 必须是 {0}".format(CONTRACT_SCHEMA))
    try:
        # 合同必须真冻结：日期写死在产物里，而不是每次生成时取当天；且必须是**真实存在**的日期。
        parse_frozen_at(contract.get("frozen_at"))
    except ValueError as error:
        problems.append(str(error))
    # 引文两边都核：内建清单 → 快照；**合同文件自带的那几条** → 快照 + 与内建逐字段一致。
    # group_only 目标合同例外：它显式不实现完整官方档位，只引用自己实际依赖的官方
    # 规则（排名键链、加赛不产生名次分），因此逐条对快照核对原文，但不要求镜像
    # 内建七条（那七条描述的是完整多阶段官方档位的引文纪律）。
    problems.extend(verify_rule_citations())
    if contract.get("mode") == "group_only":
        problems.extend(verify_rule_citations(
            citations=list(contract.get("rule_citations") or [])))
    else:
        problems.extend(verify_contract_citations(contract))
    citations = contract.get("rule_citations")
    if not isinstance(citations, list) or not citations:
        problems.append("rule_citations 不能为空：官方规则必须逐条给出快照行号与原文片段")
    else:
        for index, item in enumerate(citations):
            for field in ("key", "rule", "file", "line", "excerpt"):
                if not str((item or {}).get(field) or "").strip():
                    problems.append("rule_citations[{0}].{1} 为空".format(index, field))
    provenance = contract.get("provenance")
    if not isinstance(provenance, Mapping):
        problems.append("缺少 provenance 映射")
        return problems
    blocks = ("target", "ladder", "batch", "group", "final", "ranking", "advance",
              "panel", "versions", "seeds", "stop")
    for key in blocks:
        if key not in contract:
            problems.append("缺少语义块 {0}".format(key))
    for dotted, entry in sorted(provenance.items()):
        if not isinstance(entry, Mapping):
            problems.append("provenance[{0}] 必须是映射".format(dotted))
            continue
        if entry.get("level") not in LEVELS:
            problems.append("provenance[{0}].level 不是合法证据级别：{1!r}".format(
                dotted, entry.get("level")))
        if not str(entry.get("source") or "").strip():
            problems.append("provenance[{0}].source 为空".format(dotted))
        try:
            _lookup_path(contract, dotted)
        except KeyError:
            problems.append("provenance[{0}] 指向的合同路径不存在".format(dotted))
    for block in blocks:
        if not any(dotted == block or dotted.startswith(block + ".") for dotted in provenance):
            problems.append("语义块 {0} 没有任何 provenance 条目".format(block))
    ladder = contract.get("ladder")
    if not isinstance(ladder, list) or not ladder:
        problems.append("ladder 必须是非空列表")
    else:
        floors = [int(row.get("min_participants", -1)) for row in ladder]
        if floors != sorted(floors, reverse=True):
            problems.append("ladder 必须按 min_participants 降序排列")
        if floors and min(floors) != int(contract.get("void_below", VOID_BELOW)):
            problems.append("ladder 最低档下界必须等于 void_below")
        for row in ladder:
            stages = row.get("stages")
            if not isinstance(stages, list) or not stages:
                problems.append("ladder 档位 {0} 没有阶段".format(row.get("min_participants")))
                continue
            if stages[-1].get("kind") != "final" and contract.get("mode") != "group_only":
                problems.append("档位 {0} 的最后阶段必须是决赛".format(row.get("min_participants")))
            for stage in stages:
                if stage.get("kind") not in ("qualifying_global", "group_round", "final"):
                    problems.append("未知阶段类型 {0!r}".format(stage.get("kind")))
    if contract.get("mode") == "group_only":
        # group_advance_v1 的 group-only 目标合同（v4 §2）：单档、单组内赛、4 人取前 2，
        # 不进决赛——「最后阶段必须是决赛」的官方档位检查在上面被显式豁免。
        ladder_rows = ladder if isinstance(ladder, list) else []
        if len(ladder_rows) != 1:
            problems.append("group_only 合同 ladder 必须恰一档")
        else:
            group_stages = ladder_rows[0].get("stages") or []
            if len(group_stages) != 1:
                problems.append("group_only 合同 ladder 档位必须恰一个阶段")
            else:
                stage_spec = group_stages[0]
                if stage_spec.get("kind") != "group_round":
                    problems.append("group_only 合同唯一阶段 kind 必须是 group_round")
                for field, expected in (("groups", 1), ("group_size", 4), ("group_advance", 2)):
                    if stage_spec.get(field) != expected:
                        problems.append(
                            "group_only 合同阶段 {0} 必须是 {1!r}（收到 {2!r}）".format(
                                field, expected, stage_spec.get(field)))
        objective = contract.get("objective")
        if objective is not None:
            if not isinstance(objective, Mapping):
                problems.append("objective 必须是映射")
            else:
                if objective.get("target_id") != "group_advance_v1":
                    problems.append(
                        "group_only 合同 objective.target_id 必须是 'group_advance_v1'")
                if objective.get("advance_count") != 2:
                    problems.append("group_only 合同 objective.advance_count 必须是 2")
                if objective.get("missing_key_policy") != "recognition_interval":
                    problems.append(
                        "group_only 合同 objective.missing_key_policy "
                        "必须是 'recognition_interval'")
    ranking = contract.get("ranking", {})
    if list(ranking.get("qualify_keys", [])) != ["total_score", "place_points", "god_count"]:
        problems.append("qualify_keys 必须与官方三键一致")
    if list(ranking.get("final_keys", [])) != ["total_score"]:
        problems.append("final_keys 必须只有 total_score")
    if list(ranking.get("place_points_values", [])) != list(PLACE_POINTS):
        problems.append("place_points_values 与官方 +3/+1/−1/−3 不一致")
    if not bool(ranking.get("score_reset_per_stage")):
        problems.append("官方规则要求每个阶段独立计分（score_reset_per_stage）")
    unresolved = contract.get("unresolved")
    if not isinstance(unresolved, list) or not unresolved:
        problems.append("unresolved 不能为空：官方仍有未确认项，写空等于掩盖")
    else:
        for index, item in enumerate(unresolved):
            for field in ("item", "status", "basis", "impact"):
                if not str((item or {}).get(field) or "").strip():
                    problems.append("unresolved[{0}].{1} 为空：未解决项必须写清依据与影响".format(
                        index, field))
    panel = contract.get("panel", {})
    pool = list(panel.get("policy_pool", []))
    if not pool or any(name not in PANEL_POLICY_NAMES for name in pool):
        problems.append("panel.policy_pool 只能包含冻结白名单策略：{0}".format(PANEL_POLICY_NAMES))
    final = contract.get("final", {})
    if int(final.get("max_overtime", 0)) <= 0:
        problems.append("final.max_overtime 必须是正数（工程保护上限）")
    if not bool(final.get("overtime_no_place_points")):
        problems.append("官方 v34 第 377 行：加赛场不产生名次分/白板数（overtime_no_place_points 必须为真）")
    if not bool(ranking.get("place_points_excluded_from_total")):
        problems.append("官方 v34 第 377 行：名次分不进总得分（place_points_excluded_from_total 必须为真）")
    if not str(contract.get("batch", {}).get("tables_per_batch_rule") or "").strip():
        problems.append("必须声明每批实际整桌数规则（不足一桌者轮空）")
    return problems


class StageVoid(RuntimeError):
    """整场作废（官方规则）：不是异常，但也不产生名次。"""


class StageFailed(RuntimeError):
    """阶段结果与计划不符：**不可排序**，停止推进（不补零、不静默删行）。"""


def ladder_stages(contract: Mapping[str, Any], participants: int) -> List[Dict[str, Any]]:
    """按到位人数取档位；少于 void_below 抛 StageVoid。"""

    if participants < int(contract.get("void_below", VOID_BELOW)):
        raise StageVoid("到位人数 {0} 少于 {1}：官方规则下整场赛事作废，不产生名次".format(
            participants, contract.get("void_below", VOID_BELOW)))
    for row in contract["ladder"]:
        if participants >= int(row["min_participants"]):
            return [dict(stage) for stage in row["stages"]]
    raise StageVoid("没有匹配的档位：人数 {0}".format(participants))


# ---------------------------------------------------------------------------
# 3. 纯编排语义（无副作用，可单测）
# ---------------------------------------------------------------------------


def place_points_for_table(scores: Sequence[int]) -> Tuple[int, ...]:
    """本场名次分：按本场总得分排名，同分共享**并列名次区间的平均**名次分。

    官方 §5.1：名次分依次为 +3 / +1 / −1 / −3；本场同分时共享并列名次区间的平均
    （例：第 1、2 名并列时各得 +2）。四桌位时所有区间的平均都是整数；
    不是整数说明输入不是 4 个座位——**显式报错**，不四舍五入。
    """

    if len(scores) != SEAT_COUNT:
        raise ValueError("本场必须是 {0} 个座位，得到 {1}".format(SEAT_COUNT, len(scores)))
    order = sorted(range(SEAT_COUNT), key=lambda seat: (-int(scores[seat]), seat))
    points = [0] * SEAT_COUNT
    index = 0
    while index < SEAT_COUNT:
        end = index
        while end + 1 < SEAT_COUNT and int(scores[order[end + 1]]) == int(scores[order[index]]):
            end += 1
        block = PLACE_POINTS[index:end + 1]
        total = sum(block)
        if total % len(block) != 0:
            raise ValueError("并列区间 {0} 的平均名次分不是整数：{1}".format(
                list(range(index + 1, end + 2)), total / len(block)))
        share = total // len(block)
        for position in range(index, end + 1):
            points[order[position]] = share
        index = end + 1
    return tuple(points)


@dataclass
class LedgerRow:
    """一个阶段内的累计账（**每个阶段从零开始**：官方 §5.1 阶段独立计分）。"""

    participant_id: str
    total_score: int = 0
    place_points: int = 0
    tables_played: int = 0
    byes: int = 0
    god_count: Optional[int] = None      # 离线不可复现 ⇒ 恒 None，不填 0


def rank_ledger(rows: Sequence[LedgerRow], *, keys: Sequence[str]) -> List[Dict[str, Any]]:
    """按声明排序键出阶段名次；离线只有两键，第三键缺失时标**未解决边界**。

    - god_count 离线不可复现（官方 §5.2 说明），因此**不参与排序**，
      但会记进 keys_declared 与 keys_used 的差异里；
    - 同两键时的名次是未解决边界：用**声明的**参赛者身份字典序兜底
      （与官方 user_id 字典序兜底同形），并置 tie_unresolved=true，
      使下游不能把它当官方名次使用。
    """

    usable = [key for key in keys if key in ("total_score", "place_points")]
    if not usable:
        raise ValueError("至少需要一个可离线复现的排序键")
    ordered = sorted(rows, key=lambda row: row.participant_id)
    ordered.sort(key=lambda row: tuple(-int(getattr(row, key)) for key in usable))
    out: List[Dict[str, Any]] = []
    for index, row in enumerate(ordered):
        signature = tuple(int(getattr(row, key)) for key in usable)
        previous = (tuple(int(getattr(ordered[index - 1], key)) for key in usable)
                    if index > 0 else None)
        following = (tuple(int(getattr(ordered[index + 1], key)) for key in usable)
                     if index + 1 < len(ordered) else None)
        rank = out[-1]["rank"] if (previous is not None and previous == signature) else index + 1
        out.append({
            "participant_id": row.participant_id,
            "rank": rank,
            "total_score": int(row.total_score),
            "place_points": int(row.place_points),
            "god_count": row.god_count,
            "tables_played": int(row.tables_played),
            "byes": int(row.byes),
            "keys_declared": list(keys),
            "keys_used": list(usable),
            "tie_unresolved": bool((previous is not None and previous == signature)
                                   or (following is not None and following == signature)),
        })
    return out


def group_advance_intervals(rows: Sequence[LedgerRow], *,
                            keys: Sequence[str] = ("total_score", "place_points")
                            ) -> List[Dict[str, Any]]:
    """group_advance_v1 的**识别区间**：按已知排序键给每个参赛者的可能名次区间 [a, b]。

    合同 objective.interval_algorithm：按已知 (total_score, place_points) 降序排序，
    同分并列成块；每个参赛者 a = 严格更高者数 + 1、b = 严格更高者数 + 同块人数。
    这是**识别区间**——缺 god_count 这一事实造成的未知，不是抽样置信区间，二者
    不得混同（SEARCH-SPACE-REDESIGN v4 §2）。纪律：全程不读 participant_id 排序，
    同块只用成员集合表达，不用身份序提前打破并列（T15 红线）；god_count 为 None
    不补零、不参与任何计算。
    """

    usable = [key for key in keys if key in ("total_score", "place_points")]
    if not usable:
        raise ValueError("至少需要一个可离线复现的排序键")
    ordered = sorted(rows, key=lambda row: tuple(-int(getattr(row, key)) for key in usable))
    out: List[Dict[str, Any]] = []
    index = 0
    while index < len(ordered):
        signature = tuple(int(getattr(ordered[index], key)) for key in usable)
        end = index
        while (end + 1 < len(ordered)
               and tuple(int(getattr(ordered[end + 1], key)) for key in usable) == signature):
            end += 1
        # tie_block 仅按身份排序**展示成员集合**，不参与名次判定：a/b 与身份序无关。
        block_ids = sorted(row.participant_id for row in ordered[index:end + 1])
        for row in ordered[index:end + 1]:
            out.append({
                "participant_id": row.participant_id,
                "a": index + 1,
                "b": end + 1,
                "tie_block": list(block_ids),
            })
        index = end + 1
    return out


def group_advance_utility(rows: Sequence[LedgerRow], *, focal_id: str,
                          advance: int = 2) -> Dict[str, Any]:
    """焦点参赛者的 U 识别区间（group_advance_v1：U = 1{本阶段完整排名 ≤ advance}）。

    三态规则（合同 objective.interval_algorithm）：b ≤ advance ⇒ U=[1,1]；
    a > advance ⇒ U=[0,0]；其余 [0,1] 且 unresolved=true。**禁止**用 participant_id
    字典序提前打破未知 god_count 造成的并列——区间是答案的一部分，不是待消除的
    噪声（T15 红线）。焦点不在账本里时抛 KeyError，由调用方转成失败输出。
    """

    by_id = {item["participant_id"]: item for item in group_advance_intervals(rows)}
    if focal_id not in by_id:
        raise KeyError("焦点参赛者 {0!r} 不在账本里".format(focal_id))
    item = by_id[focal_id]
    low, high = int(item["a"]), int(item["b"])
    if high <= advance:
        u_low = u_high = 1
        unresolved = False
    elif low > advance:
        u_low = u_high = 0
        unresolved = False
    else:
        u_low, u_high = 0, 1
        unresolved = True
    return {
        "focal_id": focal_id,
        "u_low": u_low,
        "u_high": u_high,
        "unresolved": unresolved,
        "a": low,
        "b": high,
        "tie_block": list(item["tie_block"]),
        "policy": "recognition_interval",
    }


def auxiliary_stage_reports(rows: Sequence[LedgerRow]) -> Dict[str, Any]:
    """辅助报告：正积分表与旧代理分参照；联合事件由调用方组合，不与 U 相加。

    - positive_net_score 只报告、不作为晋级条件（合同 objective.auxiliary_reports）；
      「前二且正积分」联合事件由调用方拿 U 区间与本表组合，本函数不掺入 U。
    - stage_advance_score_reference 按旧开发代理公式「10×晋级资格阶段数＋决赛名次分」
      对样例输入计算：单组四人样例里晋级资格阶段数取「按 participant_id 字典序兜底
      的名次进入前 2」，决赛名次分按 PLACE_POINTS 位次取值。标记
      legacy_proxy_only_not_goal：仅供 T14 证明四者不同，任何新主指标路径不得读取。
    """

    positives = {row.participant_id: int(row.total_score) > 0 for row in rows}
    ordered = sorted(rows, key=lambda row: row.participant_id)
    ordered.sort(key=lambda row: (-int(row.total_score), -int(row.place_points)))
    legacy: Dict[str, int] = {}
    for position, row in enumerate(ordered, start=1):
        # 旧代理的取整规则就是字典序兜底名次——这正是它不能当目标的原因（T14）。
        final_points = int(PLACE_POINTS[position - 1]) if position <= len(PLACE_POINTS) else 0
        legacy[row.participant_id] = 10 * (1 if position <= 2 else 0) + final_points
    return {
        "positive_net_score": positives,
        "stage_advance_score_reference": {
            "values": legacy,
            "formula": "10×晋级资格阶段数＋决赛名次分（旧开发代理；同分按 participant_id 字典序兜底）",
            "note": "legacy_proxy_only_not_goal",
        },
    }


def snake_groups(ordered_ids: Sequence[str], *, groups: int, group_size: int,
                 previous_groups: Optional[Sequence[Sequence[str]]] = None
                 ) -> Tuple[List[List[str]], Dict[str, Any]]:
    """按名次**蛇形分组**，并用确定性贪心交换尽量避免上一阶段同组者重逢。

    返回 (分组, 诊断)；诊断里写明交换前后的重逢对数与交换轮数，
    因为「尽量避免」是**官方软约束**（§3.2），平台算法未公开。
    """

    expected = groups * group_size
    if len(ordered_ids) != expected:
        raise ValueError("蛇形分组要求人数恰好 {0}，得到 {1}".format(expected, len(ordered_ids)))
    original = [_snake_bucket(ordered_ids, groups, index) for index in range(groups)]
    buckets = [list(bucket) for bucket in original]
    previous_pairs = _pair_set(previous_groups or ())
    repeats_before_swaps = _count_repeats(original, previous_pairs)
    repeats = repeats_before_swaps
    swaps = 0
    if previous_pairs:
        improved = True
        while improved:
            improved = False
            for left in range(groups):
                for right in range(left + 1, groups):
                    for item_left in range(len(buckets[left])):
                        for item_right in range(len(buckets[right])):
                            buckets[left][item_left], buckets[right][item_right] = (
                                buckets[right][item_right], buckets[left][item_left])
                            after = _count_repeats(buckets, previous_pairs)
                            if after < repeats:
                                repeats = after
                                swaps += 1
                                improved = True
                            else:
                                buckets[left][item_left], buckets[right][item_right] = (
                                    buckets[right][item_right], buckets[left][item_left])
    return buckets, {
        "seeding": "snake",
        "swaps_to_avoid_repeats": swaps,
        "repeat_pairs": repeats,
        "repeat_pairs_before_swaps": repeats_before_swaps,
        "previous_groups_supplied": bool(previous_groups),
        "note": "「尽量避免重逢」是官方软约束；本实现是声明的确定性近似",
    }


def _snake_bucket(ordered_ids: Sequence[str], groups: int, bucket: int) -> List[str]:
    members = []
    for index, participant in enumerate(ordered_ids):
        row, column = divmod(index, groups)
        if (column if row % 2 == 0 else groups - 1 - column) == bucket:
            members.append(participant)
    return members


def _pair_set(groups: Sequence[Sequence[str]]) -> set:
    pairs = set()
    for group in groups:
        members = sorted(str(item) for item in group)
        for first in range(len(members)):
            for second in range(first + 1, len(members)):
                pairs.add((members[first], members[second]))
    return pairs


def _count_repeats(buckets: Sequence[Sequence[str]], previous_pairs: set) -> int:
    return len(_pair_set(buckets) & previous_pairs)


# ---------------------------------------------------------------------------
# 4. 场次计划与执行契约
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TablePlan:
    """一个场次（一桌 4 人）的完整计划；permutation[逻辑身份] = 实际座位。"""

    table_id: str
    stage_no: int
    stage_name: str
    stage_role: str            # qualify / final
    stage_kind: str            # qualifying_global / group_round / final / overtime
    group_index: Optional[int]
    batch_index: Optional[int]
    tables_in_stage: int
    logical_participants: Tuple[str, str, str, str]
    policy_names: Tuple[str, str, str, str]
    permutation: Tuple[int, int, int, int]
    seed: int
    scenario_id: str
    match_id: str
    pair_id: str
    initial_dealer: int

    def seats(self) -> Tuple[str, str, str, str]:
        """按**实际座位**排列的参赛者身份（与 MatchResult.policy_ids_by_seat 同口径）。"""

        by_seat: List[str] = [""] * SEAT_COUNT
        for logical, seat in enumerate(self.permutation):
            by_seat[seat] = self.logical_participants[logical]
        return tuple(by_seat)  # type: ignore[return-value]

    def policy_names_by_seat(self) -> Tuple[str, str, str, str]:
        """按实际座位排列的策略名（与 seats() 同序）。"""

        by_seat: List[str] = [""] * SEAT_COUNT
        for logical, seat in enumerate(self.permutation):
            by_seat[seat] = self.policy_names[logical]
        return tuple(by_seat)  # type: ignore[return-value]

    def to_json(self) -> Dict[str, Any]:
        return {
            "table_id": self.table_id,
            "stage_no": self.stage_no,
            "stage_name": self.stage_name,
            "stage_role": self.stage_role,
            "stage_kind": self.stage_kind,
            "group_index": self.group_index,
            "batch_index": self.batch_index,
            "tables_in_stage": self.tables_in_stage,
            "logical_participants": list(self.logical_participants),
            "policy_names": list(self.policy_names),
            "permutation": list(self.permutation),
            "seat_participants": list(self.seats()),
            "seed": self.seed,
            "scenario_id": self.scenario_id,
            "match_id": self.match_id,
            "pair_id": self.pair_id,
            "initial_dealer": self.initial_dealer,
        }

    @classmethod
    def from_json(cls, data: Mapping[str, Any]) -> "TablePlan":
        return cls(
            table_id=str(data["table_id"]),
            stage_no=int(data["stage_no"]),
            stage_name=str(data["stage_name"]),
            stage_role=str(data["stage_role"]),
            stage_kind=str(data["stage_kind"]),
            group_index=(None if data.get("group_index") is None else int(data["group_index"])),
            batch_index=(None if data.get("batch_index") is None else int(data["batch_index"])),
            tables_in_stage=int(data.get("tables_in_stage", 1)),
            logical_participants=tuple(data["logical_participants"]),  # type: ignore[arg-type]
            policy_names=tuple(data["policy_names"]),                  # type: ignore[arg-type]
            permutation=tuple(int(item) for item in data["permutation"]),  # type: ignore[arg-type]
            seed=int(data["seed"]),
            scenario_id=str(data["scenario_id"]),
            match_id=str(data["match_id"]),
            pair_id=str(data["pair_id"]),
            initial_dealer=int(data.get("initial_dealer", 0)),
        )


@dataclass(frozen=True)
class TableOutcome:
    """一个场次的执行结局；失败时 failure 有值、scores_by_seat 为空。"""

    table_id: str
    status: str
    participant_ids_by_seat: Tuple[str, ...]
    scores_by_seat: Optional[Tuple[int, ...]] = None
    invalid_reasons: Tuple[str, ...] = ()
    wall_ms: Optional[float] = None
    result: Optional[Mapping[str, Any]] = None
    supervision: Optional[Mapping[str, Any]] = None
    failure: Optional[str] = None
    source_kind: str = "simulation"
    seed: Optional[int] = None          # 牌山种子：发牌身份，重演对账必须逐场次比对
    scenario_id: Optional[str] = None   # 牌山标签（只作注释，不参与身份）

    def to_json(self) -> Dict[str, Any]:
        return {
            "table_id": self.table_id,
            "status": self.status,
            "seed": self.seed,
            "scenario_id": self.scenario_id,
            "participant_ids_by_seat": list(self.participant_ids_by_seat),
            "scores_by_seat": (None if self.scores_by_seat is None
                               else [int(item) for item in self.scores_by_seat]),
            "invalid_reasons": list(self.invalid_reasons),
            "wall_ms": (None if self.wall_ms is None else round(float(self.wall_ms), 3)),
            "supervision": (None if self.supervision is None else dict(self.supervision)),
            "failure": self.failure,
            "source_kind": self.source_kind,
        }


def build_table_plan(*, stage_no: int, stage_name: str, stage_role: str, stage_kind: str,
                     table_id: str, participants: Sequence[Mapping[str, Any]],
                     permutation: Tuple[int, int, int, int], seed: int,
                     tables_in_stage: int, group_index: Optional[int] = None,
                     batch_index: Optional[int] = None,
                     initial_dealer: int = 0) -> TablePlan:
    """由「逻辑身份顺序的参赛者列表」构造场次计划；座位由 permutation 决定。"""

    if len(participants) != SEAT_COUNT:
        raise ValueError("一个场次必须是 {0} 人，得到 {1}".format(SEAT_COUNT, len(participants)))
    ids = tuple(str(item["participant_id"]) for item in participants)
    names = tuple(str(item["policy_name"]) for item in participants)
    scenario_id = "s{0}t{1}-{2}".format(stage_no, table_id.rsplit("-", 1)[-1], seed)
    return TablePlan(
        table_id=table_id, stage_no=stage_no, stage_name=stage_name, stage_role=stage_role,
        stage_kind=stage_kind, group_index=group_index, batch_index=batch_index,
        tables_in_stage=int(tables_in_stage), logical_participants=ids, policy_names=names,
        permutation=permutation, seed=int(seed), scenario_id=scenario_id,
        match_id="sitin-stage:{0}".format(table_id),
        pair_id="{0}:{1}".format(scenario_id, "".join(str(item) for item in permutation)),
        initial_dealer=int(initial_dealer),
    )


def plan_qualifying_tables(*, contract: Mapping[str, Any], participants: Sequence[Mapping[str, Any]],
                           stage_no: int, stage_name: str, stage_role: str,
                           panel_seed: int) -> Tuple[List[TablePlan], Dict[str, int]]:
    """海选：按批推进，每批确定性洗牌后每 4 人一桌，不足一桌者该批轮空。"""

    batch_count = int(contract["batch"]["batches"])
    per_batch = int(contract["batch"]["tables_per_batch"])
    byes = {str(item["participant_id"]): 0 for item in participants}
    order = sorted(participants, key=lambda item: str(item["participant_id"]))
    tables: List[TablePlan] = []
    table_index = 0
    for batch_index in range(batch_count):
        rng = random.Random(derive_seed(panel_seed, "batch", str(stage_no), str(batch_index)))
        shuffled = list(order)
        rng.shuffle(shuffled)
        # **整桌数 = min(每批上限, ⌊本批人数/4⌋)**：官方「每桌 4 人」「不足一桌的少数
        # 参赛者该批轮空（0 分，不计名次分与白板数）」。初版按每批上限直接切 4 人块、
        # 遇到不足一桌就 break，于是 5/6/7 人档的余数**既不上桌也不记轮空**，
        # 被静默算成「打了 0 场、0 分」（复审 #19）。
        full_tables = min(per_batch, len(shuffled) // SEAT_COUNT)
        seated = shuffled[: full_tables * SEAT_COUNT]
        for item in shuffled[full_tables * SEAT_COUNT:]:
            byes[str(item["participant_id"])] += 1
        for slot in range(full_tables):
            quad = seated[slot * SEAT_COUNT:(slot + 1) * SEAT_COUNT]
            table_id = "s{0}-b{1}-t{2}".format(stage_no, batch_index + 1, slot + 1)
            seed = derive_seed(panel_seed, "table", str(stage_no), table_id)
            tables.append(build_table_plan(
                stage_no=stage_no, stage_name=stage_name, stage_role=stage_role,
                stage_kind="qualifying_global", table_id=table_id, participants=quad,
                permutation=rotate_permutation(table_index), seed=seed,
                tables_in_stage=0, batch_index=batch_index + 1))
            table_index += 1
    return [replace(table, tables_in_stage=len(tables)) for table in tables], byes


def plan_group_tables(*, contract: Mapping[str, Any], groups: Sequence[Sequence[str]],
                      policies: Mapping[str, str], stage_no: int, stage_name: str,
                      panel_seed: int) -> List[TablePlan]:
    """组内赛：每组固定 4 人、组内循环若干场次；**组与组之间不比较**（官方 §3.2）。"""

    rounds = int(contract["group"]["tables_per_group"])
    tables: List[TablePlan] = []
    index = 0
    for group_index, members in enumerate(groups, start=1):
        if len(members) != SEAT_COUNT:
            raise ValueError("每组必须是 {0} 人，得到 {1}".format(SEAT_COUNT, len(members)))
        for round_index in range(rounds):
            table_id = "s{0}-g{1}-t{2}".format(stage_no, group_index, round_index + 1)
            seed = derive_seed(panel_seed, "table", str(stage_no), table_id)
            tables.append(build_table_plan(
                stage_no=stage_no, stage_name=stage_name, stage_role="qualify",
                stage_kind="group_round", table_id=table_id,
                participants=[{"participant_id": member, "policy_name": policies[member]}
                              for member in members],
                permutation=rotate_permutation(index), seed=seed,
                tables_in_stage=len(groups) * rounds, group_index=group_index))
            index += 1
    return tables


def plan_final_tables(*, contract: Mapping[str, Any], finalists: Sequence[str],
                      policies: Mapping[str, str], stage_no: int, stage_name: str,
                      panel_seed: int, overtime_index: int) -> List[TablePlan]:
    """决赛（及加赛）：固定 4 人，只累计总得分；加赛场次并入决赛总账。"""

    if len(finalists) != SEAT_COUNT:
        raise ValueError("决赛必须是 {0} 人，得到 {1}".format(SEAT_COUNT, len(finalists)))
    rounds = int(contract["final"]["tables_in_final"])
    tables: List[TablePlan] = []
    for round_index in range(rounds):
        suffix = "" if overtime_index == 0 else "-ot{0}".format(overtime_index)
        table_id = "s{0}-final{1}-t{2}".format(stage_no, suffix, round_index + 1)
        seed = derive_seed(panel_seed, "table", str(stage_no), table_id)
        tables.append(build_table_plan(
            stage_no=stage_no, stage_name=stage_name, stage_role="final",
            stage_kind=("final" if overtime_index == 0 else "overtime"),
            table_id=table_id,
            participants=[{"participant_id": member, "policy_name": policies[member]}
                          for member in finalists],
            permutation=rotate_permutation(overtime_index + round_index), seed=seed,
            tables_in_stage=rounds + overtime_index))
    return tables


def verify_stage_tables(plan: Sequence[TablePlan], outcomes: Sequence[TableOutcome]) -> Dict[str, Any]:
    """对照**计划**核验一个阶段的全部场次结果（REVIEW-8 R8-4 口径）。

    逐项核对：计划里的每个场次都要有结果、都必须是 complete、
    座位上的参赛者身份要与计划**逐席相同**、分数向量长度正确。
    任何不符都进 problems，由调用方判**不可排序**——不允许「删掉失败行再排名」。
    """

    problems: List[str] = []
    planned_ids = [table.table_id for table in plan]
    if len(set(planned_ids)) != len(planned_ids):
        problems.append("计划里出现重复场次号")
    by_id: Dict[str, TableOutcome] = {}
    for outcome in outcomes:
        if outcome.table_id in by_id:
            problems.append("场次 {0} 出现了多条结果".format(outcome.table_id))
        by_id[outcome.table_id] = outcome
    missing = sorted(set(planned_ids) - set(by_id))
    if missing:
        problems.append("{0} 个计划的场次没有结果；示例 {1}".format(len(missing), missing[:3]))
    extra = sorted(set(by_id) - set(planned_ids))
    if extra:
        problems.append("{0} 条结果不属于本阶段计划；示例 {1}".format(len(extra), extra[:3]))
    for table in plan:
        outcome = by_id.get(table.table_id)
        if outcome is None:
            continue
        if outcome.status != "complete":
            problems.append("场次 {0} 状态 {1}：{2}".format(
                table.table_id, outcome.status,
                "；".join(outcome.invalid_reasons) or outcome.failure or "无理由"))
        expected_seats = table.seats()
        if tuple(outcome.participant_ids_by_seat) != expected_seats:
            problems.append("场次 {0} 座位身份与计划不符：计划 {1}，实际 {2}".format(
                table.table_id, list(expected_seats), list(outcome.participant_ids_by_seat)))
        if outcome.scores_by_seat is None or len(outcome.scores_by_seat) != SEAT_COUNT:
            problems.append("场次 {0} 缺少 {1} 个座位的分数".format(table.table_id, SEAT_COUNT))
    return {
        "ok": not problems,
        "problems": problems,
        "planned_tables": len(plan),
        "observed_tables": len(outcomes),
        "status_counts": _status_counts(outcomes),
    }


def _group_stage_standings(group_records: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    """组内赛的阶段名次表：**组内名次优先、组序号次序**，不跨组比较分数。

    官方 §3.2 只说「组与组之间的分数不互相比较」，没有公开下一阶段种子在组间怎么排；
    本包声明的读法是：先取各组第 1 名（按组序号），再取各组第 2 名，依次类推。
    换读法必须改合同（group.next_stage_seed_order）并重新冻结——那张 unresolved 里
    写明了另一种可能读法（§5.1 的跨组三键名次）。
    """

    depth = max((len(record["standings"]) for record in group_records), default=0)
    ordered: List[Dict[str, Any]] = []
    for rank_index in range(depth):
        for record in group_records:
            if rank_index < len(record["standings"]):
                ordered.append(dict(record["standings"][rank_index]))
    return ordered


def _status_counts(outcomes: Sequence[TableOutcome]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for outcome in outcomes:
        counts[outcome.status] = counts.get(outcome.status, 0) + 1
    return counts


def place_points_for_stage_table(table: TablePlan,
                                 scores: Sequence[int]) -> Tuple[Tuple[int, ...], str]:
    """本场**计入阶段账**的名次分与规则名。

    - 加赛桌：恒 0，规则名 `overtime_no_place_points`（官方指南 v34 第 377 行）；
    - 其余场次：按本场位次与并列区间平均，规则名 `table_rank`。

    把这条规则抽成**一个可替换的接缝**，是为了让「把规则改回旧写法」能在测试里
    真的跑一遍（见 test_replay_detects_recurrence_of_the_overtime_place_point_bug）：
    只靠散文声称"重演能发现它复发"是不够的。
    """

    if table.stage_kind == "overtime":
        return (0,) * SEAT_COUNT, "overtime_no_place_points"
    return place_points_for_table(scores), "table_rank"


def accumulate_stage(*, plan: Sequence[TablePlan], outcomes: Mapping[str, TableOutcome],
                     participants: Sequence[str], byes: Mapping[str, int],
                     seat_bonus_rows: List[Dict[str, Any]]) -> List[LedgerRow]:
    """把本阶段所有场次累加进**本阶段独立**的账（官方：阶段分数不带入下一阶段）。

    **加赛场不产生名次分**（官方指南 v34 第 377 行：「决赛轮纯总得分、任何同分加赛至
    1-4 名两两不同，**加赛场不产生名次分/白板数**」）。初版对加赛桌照常按本场名次发
    +3/+1/−1/−3，被记录的名次分是错的（复审 #15）——决赛名次只看总得分不受影响，
    但产物里的分项必须是 0。
    """

    ledger = {pid: LedgerRow(participant_id=pid) for pid in participants}
    for table in plan:
        outcome = outcomes[table.table_id]
        if outcome.scores_by_seat is None:
            raise StageFailed("场次 {0} 没有分数，不能累计".format(table.table_id))
        scores = tuple(int(item) for item in outcome.scores_by_seat)
        points, rule = place_points_for_stage_table(table, scores)
        seats = table.seats()
        seat_bonus_rows.append({
            "table_id": table.table_id,
            "stage_kind": table.stage_kind,
            "scores_by_seat": list(scores),
            "place_points_by_seat": list(points),
            "place_points_rule": rule,
            "participants_by_seat": list(seats),
        })
        for seat, participant in enumerate(seats):
            row = ledger[participant]
            row.total_score += scores[seat]
            row.place_points += points[seat]
            row.tables_played += 1
    for participant, count in byes.items():
        if participant in ledger:
            ledger[participant].byes = int(count)
    return [ledger[pid] for pid in sorted(ledger)]


# ---------------------------------------------------------------------------
# 5. 编排器
# ---------------------------------------------------------------------------


class StageOrchestrator:
    """按合同档位推进阶段；桌赛执行通过注入的 run_tables 完成。"""

    def __init__(self, *, contract: Mapping[str, Any], participants: Sequence[Mapping[str, Any]],
                 run_tables: Callable[[Sequence[TablePlan]], List[TableOutcome]],
                 mode: str = "simulation"):
        self.contract = contract
        self.participants = [{"participant_id": str(item["participant_id"]),
                              "policy_name": str(item["policy_name"])} for item in participants]
        if len({item["participant_id"] for item in self.participants}) != len(self.participants):
            raise ValueError("参赛者身份必须唯一")
        self.run_tables = run_tables
        self.mode = mode
        self.panel_seed = int(contract["seeds"]["panel_seed"])
        self.tables: List[Dict[str, Any]] = []
        self.verifications: List[Dict[str, Any]] = []
        self.boundaries: List[Dict[str, Any]] = []
        self.policies = {item["participant_id"]: item["policy_name"] for item in self.participants}
        self.outcomes: Dict[str, TableOutcome] = {}

    # -- 执行与记账 ---------------------------------------------------------

    def _execute(self, plan: Sequence[TablePlan], stage_no: int) -> Dict[str, TableOutcome]:
        """执行一个阶段的全部场次并**对照计划**核验；不符即不可排序。"""

        outcomes = list(self.run_tables(plan))
        verdict = verify_stage_tables(plan, outcomes)
        verdict["stage_no"] = stage_no
        self.verifications.append(verdict)
        for outcome in outcomes:
            self.outcomes[outcome.table_id] = outcome
        if not verdict["ok"]:
            raise StageFailed("阶段 {0} 结果与计划不符（不可排序）：{1}".format(
                stage_no, "；".join(verdict["problems"])))
        for table in plan:
            outcome = self.outcomes[table.table_id]
            self.tables.append({
                "plan": table.to_json(),
                "outcome": outcome.to_json(),
                "source_kind": outcome.source_kind,
            })
        return {table.table_id: self.outcomes[table.table_id] for table in plan}

    def _stage_record(self, *, stage_no: int, spec: Mapping[str, Any], participants: Sequence[str],
                      plan: Sequence[TablePlan], outcomes: Mapping[str, TableOutcome],
                      byes: Mapping[str, int]) -> Dict[str, Any]:
        seat_rows: List[Dict[str, Any]] = []
        ledger = accumulate_stage(plan=plan, outcomes=outcomes, participants=participants,
                                  byes=byes, seat_bonus_rows=seat_rows)
        keys = (self.contract["ranking"]["final_keys"] if spec["kind"] == "final"
                else self.contract["ranking"]["qualify_keys"])
        standings = rank_ledger(ledger, keys=keys)
        for row in standings:
            row["stage_no"] = stage_no
        record = {
            "stage_no": stage_no,
            "name": spec["name"],
            "role": spec["role"],
            "kind": spec["kind"],
            "score_reset": True,
            "tables": [table.table_id for table in plan],
            "seat_accounting": seat_rows,
            "standings": standings,
        }
        objective = self.contract.get("objective")
        if (spec["kind"] == "group_round" and isinstance(objective, Mapping)
                and objective.get("target_id") == "group_advance_v1"):
            # group_advance_v1：阶段记录附加每人的识别区间与 U（全量，不只焦点）。
            # standings 输出保持原样：旧字典序兜底名次仍带 tie_unresolved 标记，
            # 仅供旧诊断路径；新目标只读下面两个字段。
            advance = int(objective.get("advance_count", 2))
            record["advance_intervals"] = group_advance_intervals(ledger)
            record["advance_utilities"] = [
                group_advance_utility(ledger, focal_id=row.participant_id, advance=advance)
                for row in ledger]
        return record

    def _boundary_tie(self, standings: Sequence[Mapping[str, Any]],
                      cut: int) -> Optional[Tuple[str, str]]:
        """晋级线两侧是否**两键相同**（离线缺 god_count ⇒ 名次未解决）；返回并列的两人。

        晋级轮与组内赛共用这一处判定：两处各写一份就会出现两份口径
        （组内赛初版把 boundary_unresolved 硬编码成 False，组内第 2/3 名同分时
        照样宣称「边界已解决」——复审 #17）。
        """

        if not (0 < cut < len(standings)):
            return None
        head, tail = standings[cut - 1], standings[cut]
        if (head["total_score"], head["place_points"]) == (tail["total_score"],
                                                            tail["place_points"]):
            return (str(head["participant_id"]), str(tail["participant_id"]))
        return None

    def _record_boundary_tie(self, *, stage_no: int, cut: int, tied: Tuple[str, str],
                             group_index: Optional[int] = None) -> None:
        entry: Dict[str, Any] = {
            "stage_no": stage_no,
            "kind": "advancement_boundary",
            "at_rank": cut,
            "participants": [tied[0], tied[1]],
            "reason": "两键（total_score/place_points）相同；god_count 离线不可复现 ⇒ 名次未解决",
        }
        if group_index is not None:
            entry["group_index"] = int(group_index)
        self.boundaries.append(entry)

    def _advancement(self, standings: Sequence[Mapping[str, Any]], quota: int,
                     alive: Sequence[str], stage_no: int) -> Dict[str, Any]:
        """官方 §4 的晋级与候补；两键相同的晋级边界显式标**未解决**。"""

        advanced = [row["participant_id"] for row in standings[:quota]]
        backups = [row["participant_id"] for row in standings[quota: 2 * quota]]
        eliminated = [pid for pid in alive if pid not in advanced and pid not in backups]
        tied = self._boundary_tie(standings, quota)
        if tied is not None:
            self._record_boundary_tie(stage_no=stage_no, cut=quota, tied=tied)
        boundary_unresolved = tied is not None
        return {
            "quota": quota,
            "advanced": advanced,
            "backup": backups,
            "eliminated": eliminated,
            "boundary_unresolved": boundary_unresolved,
            "basis": "官方 §4：1..G 晋级，(G+1)..2G 候补，人数不足 2G 时其余全部候补",
        }

    # -- 三个阶段类型 -------------------------------------------------------

    def _run_qualifying(self, stage_no: int, spec: Mapping[str, Any],
                        alive: Sequence[str]) -> Dict[str, Any]:
        members = [item for item in self.participants if item["participant_id"] in set(alive)]
        plan, byes = plan_qualifying_tables(
            contract=self.contract, participants=members, stage_no=stage_no,
            stage_name=str(spec["name"]), stage_role=str(spec["role"]), panel_seed=self.panel_seed)
        outcomes = self._execute(plan, stage_no)
        record = self._stage_record(stage_no=stage_no, spec=spec, participants=alive, plan=plan,
                                    outcomes=outcomes, byes=byes)
        quota = min(int(spec["target"]), len(alive))
        record["advance"] = self._advancement(record["standings"], quota, alive, stage_no)
        record["byes"] = dict(byes)
        # 逐批记账：每批应是「整桌数 = min(上限, ⌊本批人数/4⌋)」，余数记轮空（复审 #19）。
        batches: Dict[int, Dict[str, Any]] = {}
        for table in plan:
            entry = batches.setdefault(int(table.batch_index or 0),
                                       {"tables": 0, "seated": [], "byes": []})
            entry["tables"] += 1
            entry["seated"].extend(table.seats())
        for batch_index, entry in batches.items():
            entry["byes"] = sorted(pid for pid, count in byes.items()
                                   if count and pid not in entry["seated"])
        record["batch_plan"] = [dict(batches[key], batch_index=key) for key in sorted(batches)]
        return record

    def _run_groups(self, stage_no: int, spec: Mapping[str, Any], alive: Sequence[str],
                    previous_groups: Optional[Sequence[Sequence[str]]],
                    previous_standings: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
        ordered = [row["participant_id"] for row in previous_standings
                   if row["participant_id"] in set(alive)]
        groups, seeding = snake_groups(ordered, groups=int(spec["groups"]),
                                       group_size=int(spec["group_size"]),
                                       previous_groups=previous_groups)
        plan = plan_group_tables(contract=self.contract, groups=groups, policies=self.policies,
                                 stage_no=stage_no, stage_name=str(spec["name"]),
                                 panel_seed=self.panel_seed)
        outcomes = self._execute(plan, stage_no)
        group_records = []
        advanced: List[str] = []
        group_boundary_unresolved = False
        for group_index, members in enumerate(groups, start=1):
            group_plan = [table for table in plan if table.group_index == group_index]
            group_outcomes = {table.table_id: outcomes[table.table_id] for table in group_plan}
            seat_rows: List[Dict[str, Any]] = []
            ledger = accumulate_stage(plan=group_plan, outcomes=group_outcomes,
                                      participants=members, byes={}, seat_bonus_rows=seat_rows)
            standings = rank_ledger(ledger, keys=self.contract["ranking"]["qualify_keys"])
            for row in standings:
                row["stage_no"] = stage_no
                row["group_index"] = group_index
            take = int(spec["group_advance"])
            # 组内也有晋级线：组内第 2/3 名两键相同时同样是**未解决边界**（复审 #17）。
            tied = self._boundary_tie(standings, take)
            if tied is not None:
                group_boundary_unresolved = True
                self._record_boundary_tie(stage_no=stage_no, cut=take, tied=tied,
                                          group_index=group_index)
            group_records.append({
                "group_index": group_index,
                "members": list(members),
                "tables": [table.table_id for table in group_plan],
                "seat_accounting": seat_rows,
                "standings": standings,
                "advanced": [row["participant_id"] for row in standings[:take]],
                "boundary_unresolved": tied is not None,
            })
            advanced.extend(row["participant_id"] for row in standings[:take])
        return {
            "stage_no": stage_no, "name": spec["name"], "role": spec["role"],
            "kind": spec["kind"], "score_reset": True,
            "tables": [table.table_id for table in plan],
            "groups": group_records,
            "seeding": seeding,
            "standings": _group_stage_standings(group_records),
            "standings_order_basis": self.contract["group"]["next_stage_seed_order"],
            "advance": {
                "quota_per_group": int(spec["group_advance"]),
                "advanced": advanced,
                "backup": [],
                "eliminated": [pid for pid in alive if pid not in advanced],
                "boundary_unresolved": group_boundary_unresolved,
                "basis": "官方 §3.2：每组前 {0} 晋级；组与组之间的分数不互相比较".format(
                    int(spec["group_advance"])),
            },
        }

    def _run_final(self, stage_no: int, spec: Mapping[str, Any],
                   alive: Sequence[str]) -> Dict[str, Any]:
        """决赛：只看总得分；同分则加赛并把得分并入决赛总账，直到名次两两不同。"""

        finalists = list(alive)[:SEAT_COUNT]
        if len(finalists) != SEAT_COUNT:
            raise StageFailed("决赛需要 {0} 人，实际 {1}".format(SEAT_COUNT, len(finalists)))
        max_overtime = int(self.contract["final"]["max_overtime"])
        overtime_index = 0
        all_plan: List[TablePlan] = []
        record: Dict[str, Any] = {}
        while True:
            plan = plan_final_tables(contract=self.contract, finalists=finalists,
                                     policies=self.policies, stage_no=stage_no,
                                     stage_name=str(spec["name"]), panel_seed=self.panel_seed,
                                     overtime_index=overtime_index)
            self._execute(plan, stage_no)
            all_plan.extend(plan)
            record = self._stage_record(
                stage_no=stage_no, spec=spec, participants=finalists, plan=all_plan,
                outcomes={table.table_id: self.outcomes[table.table_id] for table in all_plan},
                byes={pid: 0 for pid in finalists})
            totals = [row["total_score"] for row in record["standings"]]
            if len(set(totals)) == len(totals):
                record["overtime"] = {"rounds": overtime_index, "unique_after": True,
                                      "cap_reached": False}
                break
            if overtime_index >= max_overtime:
                record["overtime"] = {"rounds": overtime_index, "unique_after": False,
                                      "cap_reached": True}
                self.boundaries.append({
                    "stage_no": stage_no, "kind": "overtime_cap", "participants": finalists,
                    "reason": "加赛达到工程上限 {0} 仍未取得唯一名次（官方加赛无上限）".format(
                        max_overtime),
                })
                break
            overtime_index += 1
        record["tables"] = [table.table_id for table in all_plan]
        record["advance"] = None
        record["final_order"] = [row["participant_id"] for row in record["standings"]]
        return record

    # -- 主循环 -------------------------------------------------------------

    def run(self) -> Dict[str, Any]:
        stages_spec = ladder_stages(self.contract, len(self.participants))
        alive = [item["participant_id"] for item in self.participants]
        stages: List[Dict[str, Any]] = []
        previous_groups: Optional[List[List[str]]] = None
        previous_standings: List[Mapping[str, Any]] = []
        for stage_no, spec in enumerate(stages_spec, start=1):
            if spec["kind"] == "qualifying_global":
                record = self._run_qualifying(stage_no, spec, alive)
            elif spec["kind"] == "group_round":
                record = self._run_groups(stage_no, spec, alive, previous_groups,
                                          previous_standings)
                previous_groups = [list(group["members"]) for group in record["groups"]]
            elif spec["kind"] == "final":
                record = self._run_final(stage_no, spec, alive)
            else:
                raise StageFailed("未知阶段类型 {0!r}".format(spec["kind"]))
            stages.append(record)
            if record.get("advance"):
                alive = list(record["advance"]["advanced"])
            else:
                alive = list(record.get("final_order", []))
            previous_standings = record["standings"]
        return {"stage_format": [dict(spec) for spec in stages_spec], "stages": stages}


# ---------------------------------------------------------------------------
# 6. 执行：受监管子进程里跑单个场次
# ---------------------------------------------------------------------------


def build_panel_policy(name: str, monotonic: Callable[[], float]):
    """按白名单装配面板策略；未知名字立即失败（**不 fallback 到候选注册表**）。"""

    if name == "weighted_heuristic_v2":
        from hangma_bot.policy.heuristic_v2 import ComparableHeuristicPolicyV2
        return ComparableHeuristicPolicyV2(monotonic=monotonic)
    if name == "weighted_heuristic_v1":
        from hangma_bot.policy.heuristic_v1 import ReliableHeuristicPolicyV1
        return ReliableHeuristicPolicyV1(monotonic=monotonic)
    if name == "weighted_heuristic_v2_white_guard":
        from hangma_bot.policy.heuristic_v2 import ComparableHeuristicPolicyV2
        from hangma_bot.policy.white_discard_guard import WhiteDiscardGuardPolicy
        return WhiteDiscardGuardPolicy(ComparableHeuristicPolicyV2(monotonic=monotonic))
    if name == "safe_fallback":
        from hangma_bot.policy.safe_fallback import SafeFallbackPolicy
        return SafeFallbackPolicy()
    raise ValueError("策略 {0!r} 不在面板白名单 {1} 内".format(name, PANEL_POLICY_NAMES))


# --- M1 阶段账：逐桌注入已完成桌的阶段积分/名次分（P13：正式阶段执行器）-------


def natural_panel_module():
    """自然面板模块（**延迟导入**：natp 反向 import 本模块，模块级导入会成环）。

    阶段账投影的**唯一实现**在自然面板（P2 的 build_stage_situation）：本执行件只
    引用、不复制语义——口径分叉过一次，配对比较里就会出现两套账。
    """

    import sitin_natural_panel

    return sitin_natural_panel


def stage_account_mode() -> str:
    """阶段账注入口径名（单一实现取自自然面板的 STAGE_ACCOUNT_MODE）。"""

    return str(natural_panel_module().STAGE_ACCOUNT_MODE)


def stage_situation_from_json(payload: Optional[Mapping[str, Any]]
                              ) -> Optional[StageSituationProjection]:
    """把场次计划载荷里的阶段账还原成投影；**缺键/空值 = None**（旧调用零变化）。

    子进程（table-worker）与父进程之间只有场次计划这一个通道，因此投影必须能
    逐字段往返；还原的是同一份可见事实（四席累计积分/名次分、已完成桌数、赛程）。
    """

    if not payload:
        return None
    from hangma_bot.offline.evaluate import StageSituationProjection

    return StageSituationProjection(
        stage_table_no=int(payload["stage_table_no"]),
        tables_in_stage=int(payload["tables_in_stage"]),
        stage_role=str(payload.get("stage_role", "qualify")),
        tables_completed=int(payload.get("tables_completed", 0)),
        rounds_per_game=int(payload.get("rounds_per_game", 8)),
        stage_scores_by_seat=tuple(int(item) for item in payload["stage_scores_by_seat"]),
        place_points_by_seat=tuple(int(item) for item in payload["place_points_by_seat"]),
        participant_ids_by_seat=tuple(str(item) for item in payload["participant_ids_by_seat"]))


class StageAccountLedger:
    """阶段账（M1）：按阶段累计**已完成桌**的积分与名次分，供逐桌注入。

    - **账按阶段隔离**：换阶段（stage_no 变化）重新从空账起算（官方阶段清零）；
    - **同一阶段跨执行调用继续累计**：决赛与加赛桌多次调用 run_tables_supervised，
      桌序 = 已完成桌数 + 1，与 plan.tables_in_stage（含加赛）自洽；
    - **不含当前桌**：本桌结果只在其完成后并入（桌内积分由驱动的
      PlayerObservation.scores 单独维护，不重复累计）；
    - 投影一律经自然面板的 build_stage_situation 构造（单一实现，防口径分叉）。
    """

    def __init__(self, *, rounds_per_game: int) -> None:
        self.rounds_per_game = int(rounds_per_game)
        self._totals: Dict[int, Dict[str, int]] = {}
        self._places: Dict[int, Dict[str, int]] = {}
        self._completed: Dict[int, int] = {}
        #: 逐桌实际注入的投影（证据：可核「哪一桌读到哪份账」）。
        self.injected: List[Dict[str, Any]] = []

    def situation_for(self, table: TablePlan) -> StageSituationProjection:
        """本桌**开始前**的阶段账（第 1 桌 = 空账表头；换座后按身份→物理座位展开）。"""

        stage_no = int(table.stage_no)
        completed = int(self._completed.get(stage_no, 0))
        situation = natural_panel_module().build_stage_situation(
            plan=table, table_no=completed + 1, tables_completed=completed,
            totals=self._totals.get(stage_no, {}),
            place_totals=self._places.get(stage_no, {}),
            rounds_per_game=self.rounds_per_game)
        self.injected.append(dict(situation.to_json(), table_id=table.table_id))
        return situation

    def record(self, table: TablePlan, scores_by_seat: Sequence[int]) -> None:
        """把一桌的**终局**积分与名次分并入账；只在它完成后调用（避免重复累计）。"""

        stage_no = int(table.stage_no)
        totals = self._totals.setdefault(stage_no, {})
        places = self._places.setdefault(stage_no, {})
        points = place_points_for_table(list(scores_by_seat))
        for seat, participant in enumerate(table.seats()):
            totals[participant] = totals.get(participant, 0) + int(scores_by_seat[seat])
            places[participant] = places.get(participant, 0) + int(points[seat])
        self._completed[stage_no] = int(self._completed.get(stage_no, 0)) + 1


def execute_table(plan_payload: Mapping[str, Any]) -> Dict[str, Any]:
    """在**当前进程**里跑一个完整场次；由 table-worker 子命令在受监管进程里调用。

    MatchExperiment 只是取组合根运行时的入口（build_evaluation_runtime("matches", exp)
    需要它的 tournament_config），本函数**不使用**它的两臂语义——座位由计划直接给定。
    """

    from hangma_bot import bootstrap
    from hangma_bot.application.deadline import BudgetPolicy, ManualClock
    from hangma_bot.hangma.engine import HangmaRules
    from hangma_bot.hangma.interface import ValueAnalysisLimits
    from hangma_bot.kernel.config import RuleConfig, TimingConfig, TournamentConfig
    from hangma_bot.offline.evaluate import (
        BOOTSTRAP_RUNTIME_HOOK,
        MatchDriverConfig,
        MatchExperiment,
        MatchSeedSpec,
        PolicyDeclaration,
        build_match_result,
        drive_match,
    )
    from hangma_bot.offline.evaluation_results import compute_rules_hash

    plan = TablePlan.from_json(plan_payload)
    # M1：本桌开始前的阶段账（已完成桌累计，**不含本桌**）。缺键 = 旧行为（None），
    # 非阶段调用方（单桌对照等）因此零变化；键由 run_tables_supervised 逐桌写入。
    situation = stage_situation_from_json(plan_payload.get("stage_situation"))
    versions_block = plan_payload["versions"]
    rules_config = RuleConfig(ruleset_version=str(versions_block["ruleset_version"]),
                              base_score=int(versions_block["base_score"]),
                              you_cai_bi_kao=bool(versions_block["you_cai_bi_kao"]))
    timing = TimingConfig(**plan_payload["timing"])
    tournament_config = TournamentConfig(max_games=1,
                                         rounds_per_game=int(versions_block["rounds_per_game"]),
                                         rules=rules_config, timing=timing)
    runtime = getattr(bootstrap, BOOTSTRAP_RUNTIME_HOOK)("matches", MatchExperiment(
        kind="matches", clock_mode=str(versions_block["clock_mode"]),
        baseline=PolicyDeclaration(policy_id="stage-slot-a", name="panel", weights=()),
        challenger=PolicyDeclaration(policy_id="stage-slot-b", name="panel", weights=()),
        opponents=tuple(PolicyDeclaration(policy_id="stage-slot-{0}".format(index),
                                          name="panel", weights=()) for index in (3, 4, 5)),
        tournament_config=tournament_config,
        seeds=(MatchSeedSpec(seed=plan.seed, scenario_id=plan.scenario_id),),
        seat_permutations=(IDENTITY_PERMUTATION,), initial_dealer=0, initial_scores=(0, 0, 0, 0),
    ))
    if not isinstance(runtime, Mapping):
        raise RuntimeError("组合根未装配 matches 运行时；本工具不伪造模拟引擎")

    clock = ManualClock(start_monotonic=800.0, wait_scale=1.0)
    now_monotonic = (clock.now if str(versions_block["clock_mode"]) == "logical"
                     else time.monotonic)
    participant_ids = tuple(plan_payload["participants_by_seat"])
    policy_names = tuple(plan_payload["policy_names_by_seat"])
    # **候选槽**（3.4 阶段比较专用）：槽名 → {candidate, weights}。表里没有的槽名一律按
    # 白名单解析（所以 3.0 的 run/fixture 走的是原来的那条路，行为逐字节不变）。
    candidate_slots = {str(key): dict(value)
                       for key, value in (plan_payload.get("candidates") or {}).items()}
    # 候选走注册表、其余走白名单：分派只有一处实现（见 resolve_seat_policies 的说明）。
    policies = resolve_seat_policies(policy_names, participant_ids, candidate_slots, now_monotonic)
    rules = HangmaRules(rules_config)
    spec = runtime["spec_factory"](match_id=plan.match_id, scenario_id=plan.scenario_id,
                                   config=tournament_config, seed=plan.seed,
                                   initial_dealer=plan.initial_dealer,
                                   initial_scores=[0, 0, 0, 0])
    # 版本块：**哪份候选代码跑过这一桌**必须能从 MatchResult 里读出来（身份可追溯）。
    version_pairs = [
        ("clock_mode", str(versions_block["clock_mode"])),
        ("driver", "tools/sitin_stage.py table-worker (offline.evaluate drive_match)"),
        ("panel_policy_names", sorted(set(str(name) for name in policy_names))),
        ("rules_hash", compute_rules_hash(REPO)),
        ("ruleset_version", rules_config.ruleset_version),
        ("stage_contract_schema", CONTRACT_SCHEMA),
    ]
    used_slots = used_candidate_slots(policy_names, candidate_slots)
    if used_slots:
        version_pairs.append(("candidate_slots", json.dumps(used_slots, ensure_ascii=False,
                                                           sort_keys=True)))
    # T08/B3 统一分析配置：计划可选携带 value_limits（与普通驱动同一
    # ValueAnalysisLimits 等值）；缺省 None 保持旧行为零变化。
    limits_payload = plan_payload.get("value_limits")
    value_limits = (None if limits_payload is None else ValueAnalysisLimits(
        max_expansions=int(limits_payload["max_expansions"]),
        max_routes_per_candidate=int(limits_payload["max_routes_per_candidate"]),
    ))
    if value_limits is not None:
        version_pairs.append(("value_limits", json.dumps(
            limits_payload, ensure_ascii=False, sort_keys=True)))
    started = time.monotonic()
    outcome = asyncio.run(drive_match(
        engine=runtime["engine"], spec=spec, policies_by_seat=tuple(policies), rules=rules,
        choice_factory=runtime["choice_factory"],
        config=MatchDriverConfig(clock_mode=str(versions_block["clock_mode"]),
                                 step_limit=int(plan_payload["step_limit"]),
                                 budget_policy=BudgetPolicy(),
                                 competition_tournament_id=plan.scenario_id),
        now_monotonic=now_monotonic, wall_clock=None, value_limits=value_limits,
        stage_situation=situation))
    wall_ms = (time.monotonic() - started) * 1000.0
    result = build_match_result(
        match_id=plan.match_id, scenario_id=plan.scenario_id, pair_id=plan.pair_id,
        config=tournament_config, policy_ids_by_seat=participant_ids,  # type: ignore[arg-type]
        seat_permutation=plan.permutation, initial_scores_physical=(0, 0, 0, 0),
        outcome=outcome,
        versions=tuple(sorted(version_pairs)),
        source_refs=({"note": "sitin stage panel table", "producer": "tools/sitin_stage.py"},),
        result_id="r-" + plan.match_id, source_kind="simulation")
    return {
        "schema": RUN_SCHEMA,
        "table_id": plan.table_id,
        "stage_no": plan.stage_no,
        "group_index": plan.group_index,
        "wall_ms": round(wall_ms, 3),
        "match_status": outcome.status,
        "completed_hands": outcome.completed_hands,
        # 证据留存：本桌策略实际收到的阶段账（None = 本桌没有阶段账通道）。
        "stage_situation": (None if situation is None else situation.to_json()),
        "result": result.to_json(),
    }


def table_worker(plan_path: Path, out_path: Path) -> int:
    """子进程入口：读场次计划、跑一个场次、写回结果行。"""

    payload = json.loads(Path(plan_path).read_text(encoding="utf-8"))
    record = execute_table(payload)
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    Path(out_path).write_text(json.dumps(record, ensure_ascii=False, sort_keys=True, indent=2)
                              + NEWLINE, encoding="utf-8")
    print(json.dumps({"table_id": record["table_id"], "status": record["result"]["status"],
                      "scores": record["result"]["scores_after"]}, ensure_ascii=False))
    return 0


def run_tables_supervised(*, out_dir: Path, timeout_sec: float, plan: Sequence[TablePlan],
                          versions_block: Mapping[str, Any], timing: Mapping[str, float],
                          step_limit: int,
                          candidates: Optional[Mapping[str, Any]] = None,
                          value_limits: Optional[Mapping[str, int]] = None,
                          stage_account: Optional[StageAccountLedger] = None
                          ) -> List[TableOutcome]:
    """每个场次一个受监管子进程：墙钟上限 + **进程组**终止 + 有界输出。

    candidates：候选槽表（槽名 → {candidate, weights}）。**只有 3.4 的阶段比较会传**；
    不传时场次计划与 3.0 逐字节相同（白名单路径）。
    value_limits：T08/B3 统一分析配置（{"max_expansions", "max_routes_per_candidate"}）；
    不传时不写键，场次计划与 3.0 逐字节相同。
    stage_account（M1）：阶段账账本。**每桌开始前**把已完成桌的阶段账写进该桌计划载荷
    （stage_situation 键），桌完成后再并入；缺省在本调用内新建（按阶段号隔离）。
    同一阶段分多次调用时（决赛加赛桌）由调用方传同一个账本，账因此跨调用连续。
    """

    process_tools = sibling("sitin_process")
    account = (stage_account if stage_account is not None
               else StageAccountLedger(rounds_per_game=int(versions_block["rounds_per_game"])))
    outcomes: List[TableOutcome] = []
    for table in plan:
        cell = Path(out_dir) / "tables" / slug(table.table_id)
        cell.mkdir(parents=True, exist_ok=True)
        payload = dict(table.to_json())
        payload["versions"] = dict(versions_block)
        payload["timing"] = dict(timing)
        payload["step_limit"] = int(step_limit)
        payload["participants_by_seat"] = list(table.seats())
        payload["policy_names_by_seat"] = list(table.policy_names_by_seat())
        # M1：本桌**开始前**注入已完成桌的阶段账（第 1 桌 = 空账表头；不含本桌）。
        payload["stage_situation"] = account.situation_for(table).to_json()
        if candidates:
            payload["candidates"] = {str(key): dict(value) for key, value in candidates.items()}
        if value_limits is not None:
            # 与 offline/evaluate drive_match 的统一分析配置同口径（T08）；
            # 缺省不写键：3.0 白名单场次的计划逐字节不变。
            payload["value_limits"] = dict(value_limits)
        plan_path = cell / "plan.json"
        plan_path.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2)
                             + NEWLINE, encoding="utf-8")
        row_path = cell / "table.json"
        command = [sys.executable, str(Path(__file__).resolve()), "table-worker",
                   "--plan", str(plan_path), "--out", str(row_path)]
        supervised = process_tools.run_supervised(command, cwd=REPO, timeout_sec=float(timeout_sec))
        (cell / "worker.log").write_text(
            "stdout:" + NEWLINE + supervised.stdout + NEWLINE + "stderr:" + NEWLINE
            + supervised.stderr + NEWLINE, encoding="utf-8")
        supervision = supervised.to_json()
        if supervised.timed_out or supervised.returncode != 0 or not row_path.exists():
            reason = "超时" if supervised.timed_out else "退出码 {0}".format(supervised.returncode)
            outcomes.append(TableOutcome(
                table_id=table.table_id, status="failed",
                participant_ids_by_seat=table.seats(), failure=reason, supervision=supervision))
            continue
        record = json.loads(row_path.read_text(encoding="utf-8"))
        result = record["result"]
        if result.get("scores_after") is not None:
            # 本桌完成才并入阶段账（失败桌由计划核验拦下，不并入、不补零）。
            account.record(table, [int(item) for item in result["scores_after"]])
        outcomes.append(TableOutcome(
            table_id=table.table_id,
            status=str(result.get("status")),
            seed=table.seed,
            scenario_id=table.scenario_id,
            participant_ids_by_seat=tuple(result.get("policy_ids_by_seat") or ()),
            scores_by_seat=(None if result.get("scores_after") is None
                            else tuple(int(item) for item in result["scores_after"])),
            invalid_reasons=tuple(str(item) for item in result.get("invalid_reasons") or ()),
            wall_ms=(None if record.get("wall_ms") is None else float(record["wall_ms"])),
            result=result, supervision=supervision, source_kind="simulation"))
    return outcomes


# ---------------------------------------------------------------------------
# 7. 构造夹具与重演（只验证编排语义）
# ---------------------------------------------------------------------------


def fixture_runner(fixture: Mapping[str, Any]) -> Callable[[Sequence[TablePlan]], List[TableOutcome]]:
    """构造夹具运行器：按**声明的**分数表出场次结果，不使用真实桌赛。

    stage_base_scores[阶段号][参赛者] 覆盖 base_scores[参赛者]；seat_bonus 按实际座位
    加分；overtime_delta 只在加赛场次生效。**它是构造集**：只证明编排语义可达，
    不是效果证据（与门禁的 trigger 证据同一口径）。
    """

    def run_tables(plan: Sequence[TablePlan]) -> List[TableOutcome]:
        outcomes: List[TableOutcome] = []
        seat_bonus = [int(item) for item in fixture.get("seat_bonus", [0, 0, 0, 0])]
        if len(seat_bonus) != SEAT_COUNT:
            raise StageFailed("seat_bonus 必须是 {0} 个座位".format(SEAT_COUNT))
        for table in plan:
            stage_base = (fixture.get("stage_base_scores") or {}).get(str(table.stage_no)) or {}
            scores_by_participant: Dict[str, int] = {}
            for participant in table.logical_participants:
                if participant in stage_base:
                    base = int(stage_base[participant])
                elif participant in (fixture.get("base_scores") or {}):
                    base = int(fixture["base_scores"][participant])
                else:
                    raise StageFailed("夹具缺少参赛者 {0} 的分数声明".format(participant))
                scores_by_participant[participant] = base
            seats = table.seats()
            for seat, participant in enumerate(seats):
                scores_by_participant[participant] += seat_bonus[seat]
                if table.stage_kind == "overtime":
                    scores_by_participant[participant] += int(
                        (fixture.get("overtime_delta") or {}).get(participant, 0))
            outcomes.append(TableOutcome(
                table_id=table.table_id, status="complete", participant_ids_by_seat=seats,
                scores_by_seat=tuple(scores_by_participant[participant] for participant in seats),
                source_kind="fixture"))
        return outcomes

    return run_tables


def recorded_runner(rows: Mapping[str, TableOutcome]
                    ) -> Callable[[Sequence[TablePlan]], List[TableOutcome]]:
    """重演运行器：只从**已落盘**的场次结果里取数；缺哪个场次就报哪个场次。"""

    def run_tables(plan: Sequence[TablePlan]) -> List[TableOutcome]:
        outcomes: List[TableOutcome] = []
        for table in plan:
            outcome = rows.get(table.table_id)
            if outcome is None:
                raise StageFailed("重演缺少场次 {0} 的记录".format(table.table_id))
            outcomes.append(outcome)
        return outcomes

    return run_tables


# ---------------------------------------------------------------------------
# 8. 产物渲染
# ---------------------------------------------------------------------------


#: 复跑命令里用到的仓库相对路径（命令由合同渲染，也由测试真的执行）。
TOOL_REL_PATH = 'tools/offline/sitin/sitin_stage.py'
TEST_REL_PATH = 'tools/offline/sitin/test_sitin_stage.py'
EVIDENCE_REL_PATH = "review/llm-guided-heuristic-route-2026-09-15/evidence/3.0-stage"


def contract_cli_args(contract: Mapping[str, Any]) -> List[str]:
    """把合同里**参与身份**的参数渲染成显式命令行参数（顺序稳定）。

    为什么全量渲染而不只写 --frozen-at：后者在合同用了非默认参数时会**静默生成另一个合同**
    （sha 不同）——命令看着能跑，其实没有复现。全量显式渲染后，"合同自带的复跑命令"
    与合同本身一一对应，且可以被测试直接执行核对。
    """

    versions = contract["versions"]
    return [
        "--ruleset-version", str(versions["ruleset_version"]),
        "--base-score", str(int(versions["base_score"])),
        "--you-cai-bi-kao", ("true" if versions["you_cai_bi_kao"] else "false"),
        "--rounds-per-game", str(int(versions["rounds_per_game"])),
        "--clock-mode", str(versions["clock_mode"]),
        "--panel-seed", str(int(contract["seeds"]["panel_seed"])),
        "--panel-policy", str(contract["panel"]["policy_pool"][0]),
        "--tables-per-batch", str(int(contract["batch"]["tables_per_batch"])),
        "--batches", str(int(contract["batch"]["batches"])),
        "--tables-per-group", str(int(contract["group"]["tables_per_group"])),
        "--tables-in-final", str(int(contract["final"]["tables_in_final"])),
        "--max-overtime", str(int(contract["final"]["max_overtime"])),
        "--table-timeout-sec", str(float(contract["stop"]["table_timeout_sec"])),
        "--step-limit", str(int(contract["stop"]["step_limit"])),
        "--frozen-at", str(contract["frozen_at"]),
    ]


def contract_repro_commands(contract: Mapping[str, Any]) -> List[str]:
    """合同自带的复跑命令；**每条都必须能直接跑通**（含 --frozen-at）。

    一处定义、两处使用：文档用它渲染 §5，自测**真的执行**其中的 contract 命令并断言
    它复现同一个合同 sha——命令写错（例如漏 --frozen-at）会在测试里当场失败。
    """

    args = " ".join(contract_cli_args(contract))
    python = ".venv/bin/python"
    tool = TOOL_REL_PATH
    evidence = EVIDENCE_REL_PATH
    return [
        "{0} {1} contract {2} --out {3}".format(python, tool, args, evidence),
        "{0} {1} check {2}".format(python, tool, args),
        "{0} {1} run {2} --out {3}/run --participants 9".format(python, tool, args, evidence),
        "{0} {1} replay {2} --tables {3}/run/tables.jsonl --expect-run {3}/run/run.json "
        "--out {3}/replay".format(python, tool, args, evidence),
        "{0} {1} fixture {2} --fixture {3}/fixture-scores.json --out {3}/fixture "
        "--participants 9".format(python, tool, args, evidence),
        "{0} -m pytest {1} -q".format(python, TEST_REL_PATH),
    ]


def render_contract_md(contract: Mapping[str, Any], *, contract_sha256: str) -> str:
    """人读版阶段合同：每条官方事实都带出处列。"""

    provenance = contract["provenance"]
    lines = [
        "# 坐隐 3.0 阶段合同（冻结）",
        "",
        "> 由 [tools/sitin_stage.py](../../tools/sitin_stage.py) 生成；"
        "机器可读件见 [stage-contract.json](./stage-contract.json)。",
        "> **每条语义都带证据级别**（根 AGENTS.md §3）："
        "官方已确认 / 当前观察 / 工程建议 / 待确认假设。",
        "> 冻结日期 frozen_at：**{0}**（写死在合同里，不随生成当天漂移）；"
        "官方指南快照：{1}。".format(contract.get("frozen_at"), GUIDE_VERSION),
        "> 合同 SHA256：{0}".format(contract_sha256),
        "",
        "## 1. 档位表（官方按开赛时到位人数自动定档）",
        "",
        "| 到位人数下界 | 阶段序列 |",
        "| ---: | --- |",
    ]
    for row in contract["ladder"]:
        stages = " → ".join("{0}（{1}）".format(stage["name"], _stage_summary(stage))
                            for stage in row["stages"])
        lines.append("| ≥ {0} | {1} |".format(row["min_participants"], stages))
    lines.append("| < {0} | 赛事作废，不产生名次 |".format(contract["void_below"]))
    downgrade = contract.get("ladder_downgrade") or {}
    if downgrade:
        lines += ["", "### 1.1 阶段间降档/翻转（官方）", "",
                  "触发时点：{0}".format(_md_cell(downgrade.get("when"))), "",
                  "| 下一阶段已确认到位人数 | 平台行为 |", "| --- | --- |"]
        for rule in downgrade.get("rules") or []:
            lines.append("| {0} | {1} |".format(_md_cell(rule.get("confirmed")),
                                               _md_cell(rule.get("behaviour"))))
        lines += ["", "阶段总数：{0}".format(_md_cell(downgrade.get("stage_total"))),
                  "", "客户端口径：{0}".format(_md_cell(downgrade.get("client_rule"))),
                  "", "**离线处理**：{0}（缺口见 §4 unresolved）".format(
                      _md_cell(downgrade.get("offline_handling")))]
    lines += ["", "## 2. 排名、晋级与清零", "",
              "| 项 | 值 | 证据级别 | 出处 |", "| --- | --- | --- | --- |"]
    ranking = contract["ranking"]
    lines.append("| 晋级轮排序键 | {0} | {1} | {2} |".format(
        " → ".join(ranking["qualify_keys"]), LEVEL_OFFICIAL,
        _md_cell(provenance["ranking.qualify_keys"]["source"])))
    lines.append("| 决赛排序键 | {0} | {1} | {2} |".format(
        " → ".join(ranking["final_keys"]), LEVEL_OFFICIAL,
        _md_cell(provenance["ranking.final_keys"]["source"])))
    lines.append("| 名次分 | {0}；{1} | {2} | {3} |".format(
        "/".join(str(item) for item in ranking["place_points_values"]),
        ranking["place_points_tie_rule"], LEVEL_OFFICIAL,
        _md_cell(provenance["ranking.place_points_values"]["source"])))
    lines.append("| 阶段清零 | 每个阶段独立计分 | {0} | {1} |".format(
        LEVEL_OFFICIAL, _md_cell(provenance["ranking.score_reset_per_stage"]["source"])))
    lines.append("| 同分兜底 | {0} | {1} | {2} |".format(
        ranking["tie_fallback"], LEVEL_OFFICIAL,
        _md_cell(provenance["ranking.tie_fallback"]["source"])))
    lines.append("| god_count 离线 | {0} | {1} | {2} |".format(
        ranking["god_count_offline"], LEVEL_OFFICIAL,
        _md_cell(provenance["ranking.god_count_offline"]["source"])))
    lines.append("| 晋级 / 候补 | {0}；{1} | {2} | {3} |".format(
        contract["advance"]["primary"], contract["advance"]["backup"], LEVEL_OFFICIAL,
        _md_cell(provenance["advance.primary"]["source"])))
    lines.append("| 决赛加赛 | {0}；**{1}** | {2} | {3} |".format(
        contract["final"]["overtime_rule"],
        ("加赛场不产生名次分与白板数" if contract["final"]["overtime_no_place_points"]
         else "加赛照常计分"),
        LEVEL_OFFICIAL, _md_cell(provenance["final.overtime_no_place_points"]["source"])))
    lines += ["", "## 2.1 规则引文（逐条可核）", "",
              "> 每条都指向官方快照的具体行；--check 会打开文件比对行号与原文，"
              "引文过期或行号漂移即失败。", "",
              "| 合同键 | 规则 | 快照 | 行 | 原文片段 |",
              "| --- | --- | --- | ---: | --- |"]
    for item in contract.get("rule_citations", []):
        lines.append("| {0} | {1} | {2} | {3} | {4} |".format(
            item["key"], _md_cell(item["rule"]), item["file"], item["line"],
            _md_cell(item["excerpt"])))
    lines += ["", "## 3. 面板参数（工程选择，不是官方参数）", "",
              "| 项 | 值 |", "| --- | --- |",
              "| 每批桌数上限 / 批数 | {0} / {1} |".format(
                  contract["batch"]["tables_per_batch"], contract["batch"]["batches"]),
              "| 每批实际整桌数 | {0} |".format(contract["batch"]["tables_per_batch_rule"]),
              "| 每组场次 / 决赛场次 | {0} / {1} |".format(contract["group"]["tables_per_group"],
                                                       contract["final"]["tables_in_final"]),
              "| Rounds（每场单局数） | {0} |".format(contract["versions"]["rounds_per_game"]),
              "| 时钟模式 | {0} |".format(contract["versions"]["clock_mode"]),
              "| 面板策略池 | {0} |".format(", ".join(contract["panel"]["policy_pool"])),
              "| 面板种子 | {0} |".format(contract["seeds"]["panel_seed"]),
              "| 场次墙钟上限（秒） | {0} |".format(contract["stop"]["table_timeout_sec"]),
              "| 加赛工程上限 | {0}（官方无上限） |".format(contract["final"]["max_overtime"]),
              "", "## 4. 未解决项（unresolved）", "",
              "| 项 | 级别 | 依据 | 影响 |", "| --- | --- | --- | --- |"]
    for item in contract["unresolved"]:
        lines.append("| {0} | {1} | {2} | {3} |".format(
            _md_cell(item["item"]), _md_cell(item["status"]), _md_cell(item["basis"]),
            _md_cell(item["impact"])))
    lines += ["", "## 5. 复跑（命令由合同渲染，且被自测真的执行过）", "",
              "> 下面每条都把合同里参与身份的参数**全量显式**写出（含 --frozen-at {0}），"
              "因此复跑会得到同一个合同 sha，而不是「另取当天日期」的新合同。"
              .format(contract.get("frozen_at")), ""]
    for command in contract_repro_commands(contract):
        lines.append("    " + command)
    lines += ["", "**标注**：§1—§2.1 为官方事实（§2.1 逐条给出官方快照行号，可机械核对）；"
                  "§3 为工程选择；§4 为未确认项。", ""]
    return NEWLINE.join(lines)


def _stage_summary(stage: Mapping[str, Any]) -> str:
    if stage["kind"] == "qualifying_global":
        return "全场排名取前 {0}".format(stage["target"])
    if stage["kind"] == "group_round":
        return "{0} 组 × {1} 人，每组前 {2}".format(stage["groups"], stage["group_size"],
                                                stage["group_advance"])
    return "4 人，只看总得分，同分加赛"


def _md_cell(text: Any) -> str:
    """表格单元格转义：竖线换全角，避免把字符串切成两列。"""

    return str(text).replace("|", "｜").replace(NEWLINE, " ")


def _standings_table(standings: Sequence[Mapping[str, Any]]) -> List[str]:
    lines = [
        "| 名次 | 参赛者 | 场次 | 轮空 | 总得分 | 名次分 | 白板数 | 名次未解决 |",
        "| ---: | --- | ---: | ---: | ---: | ---: | --- | --- |",
    ]
    for row in standings:
        lines.append("| {0} | {1} | {2} | {3} | {4} | {5} | {6} | {7} |".format(
            row["rank"], row["participant_id"], row["tables_played"], row["byes"],
            row["total_score"], row["place_points"],
            "不可复现" if row["god_count"] is None else row["god_count"],
            "是" if row["tie_unresolved"] else "否"))
    return lines


def render_run_md(run: Mapping[str, Any]) -> str:
    """人读版运行报告；三种完成状态与边界单独成节。"""

    lines = [
        "# 坐隐 3.0 小规模阶段编排验证（{0}）".format(run["mode"]),
        "",
        "> 由 [tools/sitin_stage.py](../../tools/sitin_stage.py) 生成；机器可读件见 [run.json](./run.json)，",
        "> 逐场次结果见 [tables.jsonl](./tables.jsonl)（真实运行）或本目录产物（构造夹具）。",
        "> **本产物是编排（wiring）证据，不是效果证据**：面板是同质稳定策略，样本量小，",
        "> 不构成任何强弱或晋级结论。",
        "",
        "## 1. 面板与身份",
        "",
        "| 项 | 值 |",
        "| --- | --- |",
        "| 运行模式 | {0} |".format(run["mode"]),
        "| 合同 SHA256 | {0} |".format(run["contract_sha256"]),
        "| 参赛人数 | {0} |".format(len(run["participants"])),
        "| 面板策略 | {0} |".format(", ".join(sorted({item["policy_name"]
                                                    for item in run["participants"]}))),
        "| 根组身份（按 seed） | {0} |".format(run["root_set_id"]),
        "| 面板身份 | {0} |".format(run["panel_id"]),
        "| 配置指纹 | {0} |".format(run.get("config", {}).get("config_fingerprint", "未计算")),
        "",
        "## 2. 阶段结果",
        "",
    ]
    for stage in run["stages"]:
        lines.append("### 阶段 {0}：{1}（{2}，阶段分数清零）".format(
            stage["stage_no"], stage["name"], stage["role"]))
        lines.append("")
        if stage["kind"] == "group_round":
            for group in stage["groups"]:
                lines.append("**第 {0} 组**（组内排名；组与组之间的分数不互相比较；"
                             "组内晋级边界未解决：{1}）".format(
                                 group["group_index"],
                                 "是" if group.get("boundary_unresolved") else "否"))
                lines.append("")
                lines.extend(_standings_table(group["standings"]))
                lines.append("")
            lines.append("蛇形分组诊断：{0}".format(
                json.dumps(stage["seeding"], ensure_ascii=False)))
            lines.append("")
            lines.append("下一阶段种子序：{0}".format(stage.get("standings_order_basis", "未声明")))
        else:
            lines.extend(_standings_table(stage["standings"]))
            if stage.get("byes"):
                lines.append("")
                lines.append("轮空（0 分，不计名次分）：{0}".format(
                    json.dumps(stage["byes"], ensure_ascii=False)))
            if stage.get("batch_plan"):
                lines.append("")
                lines.append("逐批记账：{0}".format(
                    json.dumps(stage["batch_plan"], ensure_ascii=False)))
        advance = stage.get("advance")
        if advance:
            lines.append("")
            lines.append("晋级：{0}；候补：{1}；淘汰：{2}；边界未解决：{3}".format(
                json.dumps(advance["advanced"], ensure_ascii=False),
                json.dumps(advance["backup"], ensure_ascii=False),
                json.dumps(advance["eliminated"], ensure_ascii=False),
                advance["boundary_unresolved"]))
        if stage.get("overtime"):
            lines.append("")
            lines.append("决赛加赛：{0}".format(json.dumps(stage["overtime"], ensure_ascii=False)))
        lines.append("")
    lines += ["## 3. 计划核验（R8-4 口径）", "",
              "| 阶段 | 计划场次 | 观测场次 | 状态分布 | 结论 |",
              "| --- | ---: | ---: | --- | --- |"]
    for verdict in run["plan_verification"]:
        lines.append("| {0} | {1} | {2} | {3} | {4} |".format(
            verdict.get("stage_no"), verdict["planned_tables"], verdict["observed_tables"],
            json.dumps(verdict["status_counts"], ensure_ascii=False),
            "通过" if verdict["ok"] else "不可排序：" + "；".join(verdict["problems"])))
    lines += ["", "## 4. 完成状态（三种分开报）", "",
              "| 状态 | 取值 | 说明 |", "| --- | --- | --- |",
              "| 工具完成 | {0} | {1} |".format(run["status"]["tool_completion"],
                                              run["status"]["tool_notes"]),
              "| 发现候选 | {0} | 本包不产生候选：面板只用冻结稳定策略 |".format(
                  run["status"]["candidates_found"]),
              "| 通过发布门禁 | {0} | 本包不触碰准入与发布门禁 |".format(
                  run["status"]["release_gate"]),
              "", "## 5. 边界与未解决", ""]
    for item in run.get("boundaries", []):
        lines.append("- **未解决**：{0}（阶段 {1}：{2}）".format(
            item["reason"], item.get("stage_no"), ", ".join(item.get("participants", []))))
    if not run.get("boundaries"):
        lines.append("- 本次运行没有触发未解决边界。")
    lines += [
        "",
        "**限制**：单次小规模编排运行只说明「这套编排能被真实桌赛驱动跑通，",
        "并按官方排序 / 晋级 / 阶段清零 / 加赛规则算名次」；它不能说明任何候选或策略更好，",
        "也不能外推为官方晋级概率。",
        "",
    ]
    return NEWLINE.join(lines)


# ---------------------------------------------------------------------------
# 9. 产物写入与运行装配
# ---------------------------------------------------------------------------


def write_json(path: Path, payload: Any) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2)
                          + NEWLINE, encoding="utf-8")


def contract_text(contract: Mapping[str, Any]) -> str:
    return json.dumps(contract, ensure_ascii=False, sort_keys=True, indent=2) + NEWLINE


def contract_versions_block(contract: Mapping[str, Any]) -> Dict[str, Any]:
    versions = contract["versions"]
    return {
        "ruleset_version": versions["ruleset_version"],
        "base_score": int(versions["base_score"]),
        "you_cai_bi_kao": bool(versions["you_cai_bi_kao"]),
        "rounds_per_game": int(versions["rounds_per_game"]),
        "clock_mode": versions["clock_mode"],
    }


def panel_identity(*, contract_sha256: str, participants: Sequence[Mapping[str, Any]],
                   plan: Sequence[TablePlan]) -> str:
    """面板身份：按**结构与 seed** 取哈希，**不按标签**（R8-5 的教训）。

    只改标签（场次号/匹配置/场景名）不该产生新身份；换 seed、换座位、
    换阶段结构必须产生新身份。因此这里哈希的是
    (阶段号, 阶段类型, 组号, 批号, seed, 逐席参赛者)，不含任何字符串标签。

    **边界**：这是**实际发生过的面板**的身份——一次因同分而多打了一场加赛的运行，
    与不需要加赛的运行不是同一个面板（多出的场次是真实执行），因此面板身份也不同；
    对照时应连同 tables.jsonl 一起看，而不是把身份差异当成异常。
    """

    blob = json.dumps({
        "contract_sha256": contract_sha256,
        "participants": sorted((str(item["participant_id"]), str(item["policy_name"]))
                               for item in participants),
        "tables": [(table.stage_no, table.stage_kind, table.group_index, table.batch_index,
                    table.seed, list(table.seats())) for table in plan],
        # M1：阶段信息投影方式（口径变更 = 新实验身份，不是同一次运行）。
        "stage_projection": stage_account_mode(),
    }, ensure_ascii=False, sort_keys=True)
    return "panel-" + sha256_text(blob)[:12]


def replace_table_labels(table: TablePlan) -> TablePlan:
    """只改**标签**、不改结构与 seed 的副本；用于验证身份不随标签漂移（R8-5）。"""

    suffix = "-renamed"
    return replace(table, table_id=table.table_id + suffix,
                   scenario_id=table.scenario_id + suffix,
                   match_id=table.match_id + suffix, pair_id=table.pair_id + suffix)


def config_snapshot(*, contract: Mapping[str, Any]) -> Dict[str, Any]:
    """复用 1.3 的配置快照工具（指纹语义一处定义），不重造第二份。"""

    config_tool = sibling("sitin_config")
    versions = contract_versions_block(contract)
    snapshot = config_tool.build_snapshot(
        REPO, ruleset_version=versions["ruleset_version"], base_score=versions["base_score"],
        you_cai_bi_kao=versions["you_cai_bi_kao"],
        rounds_per_game=versions["rounds_per_game"],
        opponents=[contract["panel"]["policy_pool"][0]] * 3,
        clock_mode=versions["clock_mode"], timing=dict(DEFAULT_TIMING))
    snapshot["config_fingerprint"] = config_tool.fingerprint(snapshot)
    return snapshot


def participants_for(count: int, policy: str, *, prefix: str = "p") -> List[Dict[str, str]]:
    if count <= 0:
        raise ValueError("参赛人数必须为正")
    if policy not in PANEL_POLICY_NAMES:
        raise ValueError("策略 {0!r} 不在面板白名单内".format(policy))
    return [{"participant_id": "{0}{1:02d}".format(prefix, index + 1), "policy_name": policy}
            for index in range(count)]


def all_planned_tables(run: Mapping[str, Any]) -> List[TablePlan]:
    """从运行记录里还原全部场次计划（重演与身份核对用）。"""

    return [TablePlan.from_json(table["plan"]) for table in run.get("tables", [])]


def read_tables_jsonl(path: Path) -> Dict[str, TableOutcome]:
    """读回 tables.jsonl：每行是 MatchResult JSON + 本包信封，按场次号索引。"""

    rows: Dict[str, TableOutcome] = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        payload = json.loads(line)
        envelope = payload.get(ROW_ENVELOPE_KEY) or {}
        table_id = str(envelope.get("table_id"))
        rows[table_id] = TableOutcome(
            table_id=table_id,
            status=str(payload.get("status")),
            seed=(None if envelope.get("seed") is None else int(envelope["seed"])),
            scenario_id=(None if envelope.get("scenario_id") is None
                         else str(envelope["scenario_id"])),
            participant_ids_by_seat=tuple(payload.get("policy_ids_by_seat") or ()),
            scores_by_seat=(None if payload.get("scores_after") is None
                            else tuple(int(item) for item in payload["scores_after"])),
            invalid_reasons=tuple(str(item) for item in payload.get("invalid_reasons") or ()),
            wall_ms=(None if envelope.get("wall_ms") is None else float(envelope["wall_ms"])),
            result=payload, supervision=envelope.get("supervision"),
            source_kind=str(payload.get("source_kind") or "simulation"))
    return rows


def _write_tables_jsonl(path: Path, out_dir: Path, run: Mapping[str, Any]) -> None:
    """逐场次产物：从**已落盘的**受监管场次结果里取 MatchResult 行 + 阶段信封。

    为什么从磁盘取而不是从内存取：这样 tables.jsonl 与
    tables/<场次>/table.json 是同一份事实的两处视图，缺哪一份都能对账；
    失败场次没有结果行，也就不会出现在这里（由计划核验拦下，不静默补零）。
    """

    lines: List[str] = []
    for table in run["tables"]:
        table_id = str(table["plan"]["table_id"])
        row_path = Path(out_dir) / "tables" / slug(table_id) / "table.json"
        if not row_path.exists():
            continue
        record = json.loads(row_path.read_text(encoding="utf-8"))
        result = record.get("result")
        if result is None:
            continue
        row = dict(result)
        row[ROW_ENVELOPE_KEY] = {
            "schema": RUN_SCHEMA,
            "table_id": table_id,
            "stage_no": table["plan"]["stage_no"],
            "group_index": table["plan"].get("group_index"),
            "seed": table["plan"]["seed"],
            "scenario_id": table["plan"]["scenario_id"],
            "seat_participants": table["plan"]["seat_participants"],
            "wall_ms": record.get("wall_ms"),
            "supervision": (table["outcome"] or {}).get("supervision"),
        }
        lines.append(json.dumps(row, ensure_ascii=False, sort_keys=True))
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(NEWLINE.join(lines) + (NEWLINE if lines else ""), encoding="utf-8")


def build_run(*, contract: Mapping[str, Any], participants: Sequence[Mapping[str, Any]],
              runner: Callable[[Sequence[TablePlan]], List[TableOutcome]], mode: str) -> Dict[str, Any]:
    """跑一次阶段编排并组装运行记录（执行方式由 runner 决定）。"""

    digest = sha256_text(contract_text(contract))
    orchestrator = StageOrchestrator(contract=contract, participants=participants,
                                     run_tables=runner, mode=mode)
    body = orchestrator.run()
    plans = all_planned_tables({"tables": orchestrator.tables})
    return {
        "schema": RUN_SCHEMA,
        "mode": mode,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "contract_sha256": digest,
        "contract_schema": contract["schema"],
        "participants": [dict(item) for item in participants],
        "root_set_id": root_set_id_of([plan.seed for plan in plans]),
        "panel_id": panel_identity(contract_sha256=digest, participants=participants, plan=plans),
        "stage_format": body["stage_format"],
        "stages": body["stages"],
        "tables": orchestrator.tables,
        "plan_verification": orchestrator.verifications,
        "boundaries": orchestrator.boundaries,
        "status": {
            "tool_completion": "completed",
            "tool_notes": "阶段编排在 {0} 个场次上跑通并通过计划核验".format(
                len(orchestrator.tables)),
            "candidates_found": "not_applicable",
            "release_gate": "not_evaluated",
        },
    }


# ---------------------------------------------------------------------------
# 10. 3.4 候选槽与阶段比较（候选 vs 基线，按场景种子配对）
#
# **本段的边界（Lead 裁决 ver 2 · 分工式）**：
#   * 本包 = **执行件**：阶段编排 + 受准入约束的候选槽 + `compare` + 自己的**执行台账**
#     （只记「我执行了多少桌」，**不是预算账本**）。
#   * 生成 → 门禁 → L1/L2 → 阶段比较 → 留存淘汰 → 反馈的**编排者只有一个**：
#     tools/sitin_search.py（searchdrv 包）。本文件**不实现**搜索闭环，也不产出 3.5 冻结件；
#     阶段比较消耗的桌数由编排者从 compare.json 的 execution 段透传进搜索账。
#   * 三道闸门：① 候选必须来自**静态注册表**（未注册直接失败）；② 必须给出门禁**准入记录**
#     且语料指纹一致，否则拒绝跑；③ 候选代码只在**受监管隔离子进程**里执行。
# ---------------------------------------------------------------------------

#: 阶段比较产物的 schema（与编排者的 STAGE-COMPARE-CONTRACT.md §3 同一名字）。
COMPARE_SCHEMA = "sitin-stage-compare/1"
#: **唯一权威报告**的文件名：编排者按名字读它（见 STAGE-COMPARE-CONTRACT.md §3）。
STAGE_COMPARE_REPORT = "stage-compare.json"
#: 执行台账 schema：**只记执行量**，与编排者的预算账（`sitin-search-ledger/1`）不是一本账。
STAGE_LEDGER_SCHEMA = "sitin-stage-ledger/1"

#: 台账两列：桌数、墙钟秒。本执行件不调用模型，因此没有调用次数/输出 token 列。
STAGE_LEDGER_COLUMNS: Tuple[str, ...] = ("tables", "wall_sec")

#: 候选槽在面板里的**槽名**：它不是白名单策略名；只有计划里声明了候选表时才可解析，
#: 其余情况一律走白名单（所以 3.0 的 run／fixture 行为不变）。
CANDIDATE_SLOT = "stagecand-slot"

#: 阶段主指标：**本项目声明的开发期代理**，不是官方指标、更不是晋级概率（PLAN-REVISION §2）。
#: 定义为 10 × 晋级过的资格阶段数 +（进决赛时的名次分 4−rank+1，否则 0）：
#: 它把「阶段晋级」写成单一可比较标量，且只由官方名次／晋级规则决定。
PRIMARY_STAGE_METRIC = "stage_advance_score"

#: 阶段比较一起报的次级指标（避免只看一个数）。
SECONDARY_STAGE_METRICS: Tuple[str, ...] = ("reached_final", "place_points_total",
                                            "final_rank", "tables_played")


class StageBudgetExceeded(RuntimeError):
    """执行台账预留不下：调用方必须停在这一步（不得「先跑完再看花了多少」）。"""


class StepFailed(RuntimeError):
    """本步不可继续：准入记录不可用、产物缺失或计划与事实不符。"""

    def __init__(self, message: str, *, detail: Optional[Mapping[str, Any]] = None) -> None:
        super().__init__(message)
        self.detail: Dict[str, Any] = dict(detail or {})


def read_json(path: Path) -> Any:
    """读 JSON；文件不存在返回 None（调用方自己决定这是不是错误）。"""

    path = Path(path)
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def read_failure_report(path: Path) -> Dict[str, Any]:
    """读失败时**当场取证**（不是事后回忆）：路径可见性、是否普通文件、大小、读错误、内容 sha256。

    为什么必须逐项分开：曾经的文案把「该路径在**那一瞬间**不可见」与「JSON 顶层不是对象」
    混成一句「门禁记录不可读」（Challenger 2026-09-16 的可定位意见），于是**下一次再发生时
    这条消息无法自证是哪一种**，也无法区分"文件被并发替换/恢复"与"内容本身不对"。
    取证只读不写，且不改变任何判定（仍然 fail-closed）。
    """

    facts: Dict[str, Any] = {"path": str(path), "exists": None, "is_file": None,
                             "size": None, "sha256": None, "read_error": None}
    try:
        facts["exists"] = bool(path.exists())
        facts["is_file"] = bool(path.is_file())
        if facts["is_file"]:
            data = path.read_bytes()
            facts["size"] = len(data)
            facts["sha256"] = hashlib.sha256(data).hexdigest()
    except OSError as error:                       # 权限/IO：也算一条可核事实
        facts["read_error"] = "{0}: {1}".format(type(error).__name__, error)
    return facts


class StageExecutionLedger:
    """阶段比较的**执行台账**：只记执行量（桌数 + 墙钟），带硬上限与先预留后执行。

    为什么仍然保留「先预留后执行」：compare 是执行件，**不能**因为编排者说过预算就无限跑；
    预留不下就在跑之前停。但它**不是预算账本**——搜索／确认两本账在 tools/sitin_search.py
    （schema `sitin-search-ledger/1`），本文件是 `sitin-stage-ledger/1`，两者不得混用。
    未结算的预留一律算已执行（崩溃后不免费重演）。
    """

    def __init__(self, path: Path, limits: Mapping[str, float]) -> None:
        self.path = Path(path)
        self.limits = {key: float(dict(limits or {}).get(key, 0.0))
                       for key in STAGE_LEDGER_COLUMNS}
        self.spent = {key: 0.0 for key in STAGE_LEDGER_COLUMNS}
        self.reservations: List[Dict[str, Any]] = []
        self.overruns: List[Dict[str, Any]] = []
        self.stale: List[str] = []

    @classmethod
    def load(cls, path: Path, limits: Mapping[str, float]) -> "StageExecutionLedger":
        ledger = cls(path, limits)
        data = read_json(Path(path))
        if not isinstance(data, Mapping):
            return ledger
        for key in STAGE_LEDGER_COLUMNS:
            ledger.spent[key] = float(dict(data.get("spent") or {}).get(key, 0.0))
        ledger.reservations = [dict(item) for item in data.get("reservations") or ()]
        ledger.overruns = [dict(item) for item in data.get("overruns") or ()]
        ledger.stale = [str(item["id"]) for item in ledger.reservations
                        if not item.get("settled")]
        return ledger

    def to_json(self) -> Dict[str, Any]:
        return {"schema": STAGE_LEDGER_SCHEMA,
                "note": "执行台账：只记本执行件跑了多少桌；预算账在 tools/sitin_search.py",
                "limits": dict(self.limits), "spent": dict(self.spent),
                "remaining": self.remaining(), "reservations": self.reservations,
                "overruns": self.overruns, "stale_reservations": self.stale}

    def save(self) -> None:
        write_json(self.path, self.to_json())

    def remaining(self) -> Dict[str, float]:
        return {key: round(self.limits[key] - self.spent[key], 6)
                for key in STAGE_LEDGER_COLUMNS}

    def add(self, amount: Mapping[str, float], *, step: str, note: str = "") -> str:
        """预留一笔（**立即计入已执行**）；任何一列超出上限即抛（不静默扩容）。"""

        if self.overruns:
            raise StageBudgetExceeded(
                "台账已记录超额 {0} 笔：先处理超额再继续".format(len(self.overruns)))
        columns = {key: float(dict(amount or {}).get(key, 0.0))
                   for key in STAGE_LEDGER_COLUMNS}
        for key, value in columns.items():
            if value < 0:
                raise ValueError("预留不得为负：{0}={1}".format(key, value))
            if self.spent[key] + value > self.limits[key] + 1e-9:
                raise StageBudgetExceeded(
                    "预留不下（{0}）：需 {1}，已用 {2}，上限 {3}".format(
                        key, value, self.spent[key], self.limits[key]))
        for key, value in columns.items():
            self.spent[key] += value
        reservation_id = "{0}-{1:03d}".format(step, len(self.reservations) + 1)
        self.reservations.append({"id": reservation_id, "step": step, "note": note,
                                  "reserved": columns, "settled": False, "actual": None})
        self.save()
        return reservation_id

    def settle(self, reservation_id: str, actual: Mapping[str, float], *,
               note: str = "") -> Dict[str, Any]:
        """按实际结算：多退少补；实际超出预留即记 `overruns`。"""

        entry = next((item for item in self.reservations
                      if item.get("id") == reservation_id), None)
        if entry is None:
            raise KeyError("未知预留 {0!r}".format(reservation_id))
        if entry.get("settled"):
            raise ValueError("预留 {0} 已结算过：不得重复结算".format(reservation_id))
        columns = {key: float(dict(actual or {}).get(key, 0.0))
                   for key in STAGE_LEDGER_COLUMNS}
        delta = {key: columns[key] - float(dict(entry["reserved"]).get(key, 0.0))
                 for key in STAGE_LEDGER_COLUMNS}
        for key, value in delta.items():
            self.spent[key] += value
        entry["settled"] = True
        entry["actual"] = columns
        entry["delta"] = delta
        entry["settle_note"] = note
        if any(value > 1e-9 for value in delta.values()):
            self.overruns.append({"reservation": reservation_id, "step": entry["step"],
                                  "delta": delta, "note": note})
        self.save()
        return dict(entry)


# --- 10.1 阶段比较的算术与统计口径 -------------------------------------------


def stage_session_table_bound(*, contract: Mapping[str, Any], participants: int) -> Dict[str, int]:
    """一次完整阶段会话的桌数**期望值与上界**（先预留用；加赛是官方规则允许的额外场次）。"""

    stages = ladder_stages(contract, participants)
    per_batch = min(int(contract["batch"]["tables_per_batch"]),
                    max(0, int(participants) // SEAT_COUNT))
    qualifying = groups = final = 0
    for spec in stages:
        if spec["kind"] == "qualifying_global":
            qualifying += int(contract["batch"]["batches"]) * per_batch
        elif spec["kind"] == "group_round":
            groups += int(spec["groups"]) * int(contract["group"]["tables_per_group"])
        elif spec["kind"] == "final":
            final += int(contract["final"]["tables_in_final"])
    expected = qualifying + groups + final
    overtime = (int(contract["final"]["max_overtime"])
                * int(contract["final"]["tables_in_final"]))
    return {"qualifying": qualifying, "groups": groups, "final": final,
            "expected": expected, "bound": expected + overtime}


def declared_base_plans(*, contract: Mapping[str, Any],
                        participants: Sequence[Mapping[str, Any]],
                        panel_seed: int) -> List[TablePlan]:
    """**声明的基础赛程**：海选 + 组内 + 决赛首轮（**不含加赛**），与臂无关。

    为什么必须能在跑之前算出来：这是配对的前提（「两臂用同一批牌山」）。
    旧实现拿**实际执行过的场次**当配对键，于是官方规则要求的决赛加赛
    （得分决定 ⇒ 与策略有关）会让两臂的场次集合不同，并把整场景判成「配对不成立」——
    那是把「同一份赛程」与「同样多的场次」混成了一件事（实测 10 场景里误废 2 个）。

    场次标签与 seed 只由（合同、人数、场景种子、阶段号、序号）决定，**不含任何臂标识**
    （见 plan_qualifying_tables／plan_group_tables／plan_final_tables 的 table_id 构造），
    因此这份赛程对两臂逐字相同；「不含臂标识」由回归守着，不靠这句注释。
    """

    ids = [str(item["participant_id"]) for item in participants]
    policies = {str(item["participant_id"]): str(item["policy_name"]) for item in participants}
    members = [{"participant_id": pid, "policy_name": policies[pid]} for pid in ids]
    plans: List[TablePlan] = []
    for stage_no, spec in enumerate(ladder_stages(contract, len(members)), start=1):
        if spec["kind"] == "qualifying_global":
            plan, _byes = plan_qualifying_tables(
                contract=contract, participants=members, stage_no=stage_no,
                stage_name=str(spec["name"]), stage_role=str(spec["role"]),
                panel_seed=int(panel_seed))
        elif spec["kind"] == "group_round":
            size = int(spec["group_size"])
            needed = int(spec["groups"]) * size
            if len(ids) < needed:
                raise StageFailed("声明赛程无法构造：组内赛需要 {0} 人，面板只有 {1} 人".format(
                    needed, len(ids)))
            groups = [ids[index * size:(index + 1) * size]
                      for index in range(int(spec["groups"]))]
            plan = plan_group_tables(contract=contract, groups=groups, policies=policies,
                                     stage_no=stage_no, stage_name=str(spec["name"]),
                                     panel_seed=int(panel_seed))
        elif spec["kind"] == "final":
            plan = plan_final_tables(contract=contract, finalists=ids[:SEAT_COUNT],
                                     policies=policies, stage_no=stage_no,
                                     stage_name=str(spec["name"]), panel_seed=int(panel_seed),
                                     overtime_index=0)
        else:
            continue
        plans.extend(plan)
    return plans


def table_seed_map(plans: Sequence[TablePlan]) -> Dict[str, int]:
    """场次号 → 牌山种子（配对核验与「执行集是否覆盖声明赛程」都用它）。"""

    return {str(plan.table_id): int(plan.seed) for plan in plans}


def execution_accounting(*, base_seeds: Mapping[str, int],
                         executed_seeds: Mapping[str, int]) -> Dict[str, Any]:
    """执行集对账：声明赛程缺项、同场次 seed 漂移、以及多出来的场次。

    三种结果的含义**必须分开**：
      * `missing_base_tables`：声明赛程里的场次没跑 ⇒ 会话不完整，**不可排序**；
      * `drifted_seeds`：同一场次号在臂之间拿到不同 seed ⇒ 派生式混进了臂相关量，
        直接违反「两臂同牌山」的硬要求 ⇒ **不可排序**（fail-closed）；
      * `extra_tables`：多出来的**只可能是官方加赛场次**（得分决定 ⇒ 两臂允许不同）
        ⇒ 只记录、**不作废场景**。
    """

    return {
        "tables": len(executed_seeds),
        "extra_tables": sorted(set(executed_seeds) - set(base_seeds)),
        "missing_base_tables": sorted(set(base_seeds) - set(executed_seeds)),
        "drifted_seeds": sorted(table_id for table_id, seed in base_seeds.items()
                                if table_id in executed_seeds and executed_seeds[table_id] != seed),
    }


def source_digest_reader() -> str:
    """本执行件源码的指纹（sha256）。**缺省实现，供命令入口在开跑前调用一次**。"""

    return sha256_file(Path(__file__).resolve())


def stage_tool_versions(*, contract: Mapping[str, Any], opponents: str,
                        source_digest: str) -> Dict[str, Any]:
    """报告里的版本块：规则、评估器、对手池、工具源指纹（换实现不改代码，换代码必换指纹）。

    **指纹纪律（时序）**：`tool_sha256` 取的是**开跑前**捕获的源码指纹，由调用方传进来，
    本函数**绝不自己读盘**——曾经在这里现读，于是「18:24 启动、18:35 源码被改」的运行
    被标成了它**从未执行过**的版本（Lead 裁定 F1）。运行期是否发生过改动，由报告顶层的
    `source_digest_at_start`／`source_digest_at_end`／`tool_source_changed_during_run` 披露。
    """

    versions = dict(contract.get("versions") or {})
    return {"tool": "tools/sitin_stage.py",
            "tool_sha256": str(source_digest),
            "tool_sha256_rule": "开跑前捕获的源码指纹（实际执行的那份），不是落盘时现读",
            "ruleset_version": versions.get("ruleset_version"),
            "base_score": versions.get("base_score"),
            "rounds_per_game": versions.get("rounds_per_game"),
            "clock_mode": versions.get("clock_mode"),
            "opponent_pool": str(opponents),
            "driver": "offline.evaluate.drive_match（每场次一个受监管子进程）",
            "stage_projection": stage_account_mode(),
            "stage_contract_schema": CONTRACT_SCHEMA,
            "python": sys.version.split()[0]}


def panel_declaration_id(*, contract_sha256: str, participants: Sequence[Mapping[str, Any]],
                         focal: str, seed_base: int, seeds: Sequence[int]) -> str:
    """面板身份：**只由声明**（合同、参赛者、焦点、场景种子）复算，不含运行期偶然量。

    为什么不直接复用 3.0 的 panel_identity：那个身份哈希的是**实际发生过的场次**
    （含加赛等运行期产物），同一声明跑两次未必相同；编排者要的是可预先复算的声明身份。
    两者互补：声明身份回答「这是哪个面板」，逐场景 root_set_id 回答「牌山是否真的一致」。
    """

    blob = json.dumps({
        "contract_sha256": str(contract_sha256),
        "participants": sorted((str(item["participant_id"]), str(item["policy_name"]))
                               for item in participants),
        "focal": str(focal), "seed_base": int(seed_base),
        "seeds": [int(item) for item in seeds],
        "stage_projection": stage_account_mode()}, ensure_ascii=False, sort_keys=True)
    return "stagecmp-" + sha256_text(blob)[:12]


def derive_scenario_seed(seed_base: int, index: int) -> int:
    """场景种子：**同一场景下两臂必须拿到完全相同的牌山**，因此只由基准与序号派生。"""

    return derive_seed(int(seed_base), "stagecand-scenario", str(int(index)))


def contract_with_panel_seed(contract: Mapping[str, Any], panel_seed: int) -> Dict[str, Any]:
    """只改阶段种子、其余逐字保留的合同副本（场景之间唯一的差别就是这个种子）。"""

    clone = json.loads(json.dumps(contract, ensure_ascii=False))
    clone["seeds"]["panel_seed"] = int(panel_seed)
    return clone


def root_level_statistics(per_scenario: Sequence[float]) -> Dict[str, Any]:
    """根级（此处独立单位 = **场景种子**）统计：点估计、sd、SE、MDE。

    与 `sitin_scheduler.root_statistics` 同口径（SE = sd/√n、MDE 用 1.96 + 0.84），
    但本包**不 import 调度器**：口径一致性由测试断言（同一个教训：不靠「看起来一样」）。
    """

    values = [float(item) for item in per_scenario]
    n = len(values)
    if n < 2:
        return {"n_roots": n, "mean": (values[0] if values else None), "sd_root": None,
                "se_root": None, "mde": None, "rankable": False,
                "rankable_reason": "零有效场景种子" if n == 0 else "有效场景种子不足（<2）"}
    mean = sum(values) / n
    sd = statistics.stdev(values)
    se = sd / math.sqrt(n)
    return {"n_roots": n, "mean": round(mean, 6), "sd_root": round(sd, 6),
            "se_root": round(se, 6),
            "mde": round((1.959963984540054 + 0.8416212335729143) * se, 6),
            "rankable": True, "rankable_reason": None}


def stage_metrics(run: Mapping[str, Any], focal: str) -> Dict[str, Any]:
    """一次完整阶段运行里**焦点参赛者**的阶段指标（口径写死在这里，便于对照复算）。

    - `stage_advance_score`：主指标 = 10 × 晋级过的资格阶段数 +（进决赛时 4 − 名次 + 1）；
    - `reached_final` / `final_rank`：是否进决赛与决赛名次；
    - `place_points_total`：逐场名次分合计（官方名次分，加赛场恒 0）；
    - `tables_played` / `raw_score_total`：打了多少场、场次得分合计（**跨阶段相加只是描述**，
      官方阶段分是清零的，不得把它当晋级判据）。
    """

    stages = list(run.get("stages") or [])
    points = 0
    raw = 0
    played = 0
    for stage in stages:
        for row in stage.get("seat_accounting") or []:
            seats = [str(item) for item in row.get("participants_by_seat") or []]
            if focal not in seats:
                continue
            index = seats.index(focal)
            scored = list(row.get("place_points_by_seat") or [0] * SEAT_COUNT)
            scores = list(row.get("scores_by_seat") or [0] * SEAT_COUNT)
            points += int(scored[index])
            raw += int(scores[index])
            played += 1
    advanced_stages = 0
    reached_stage_no = 0
    for stage in stages:
        advance = dict(stage.get("advance") or {})
        if stage.get("role") == "qualify" and focal in [str(item) for item in
                                                       advance.get("advanced") or []]:
            advanced_stages += 1
        standings = [str(row.get("participant_id")) for row in stage.get("standings") or []]
        if focal in standings:
            reached_stage_no = max(reached_stage_no, int(stage.get("stage_no") or 0))
    final_stage = next((stage for stage in stages if stage.get("kind") == "final"), None)
    final_rank: Optional[int] = None
    if final_stage is not None:
        order = [str(row.get("participant_id")) for row in final_stage.get("standings") or []]
        if focal in order:
            final_rank = order.index(focal) + 1
    reached_final = final_rank is not None
    primary = 10 * advanced_stages + ((SEAT_COUNT - final_rank + 1) if reached_final else 0)
    return {"participant": focal, "stage_advance_score": primary,
            "reached_final": reached_final, "final_rank": final_rank,
            "place_points_total": points, "tables_played": played,
            "raw_score_total": raw, "advanced_qualify_stages": advanced_stages,
            "reached_stage_no": reached_stage_no}


# --- 10.2 候选装配、准入绑定与策略分派（闸①／②） ---------------------------


def build_candidate_policy(candidate: str, weights: Mapping[str, float], monotonic):
    """按**静态注册表**装配候选策略（闸①：只有 3.4 的比较路径会调用）。

    与 `build_panel_policy` 分开写是有意的：白名单路径必须保持「绝不 import 候选注册表」，
    否则 3.0 的构造检查（子进程里装配面板再看 sys.modules）就失去意义。
    `source_fingerprint_value` 与 scripts/evaluate.py、门禁侧共用同一份闭包摘要，
    保证「过门禁的那份代码」与「实际跑桌上那份代码」是同一个身份。
    """

    from hangma_bot.policy import heuristics
    from hangma_bot.offline.scoring_sources import candidate_identity_digest

    if not heuristics.is_candidate(candidate):
        raise KeyError("未注册的候选 {0!r}；已注册 {1}".format(candidate,
                                                       heuristics.candidate_names()))
    return heuristics.build_candidate(candidate, weights=dict(weights or {}),
                                      monotonic=monotonic,
                                      source_fingerprint_value=candidate_identity_digest(candidate))


def resolve_seat_policies(policy_names: Sequence[str], participant_ids: Sequence[str],
                          candidate_slots: Mapping[str, Any], monotonic) -> List[Any]:
    """逐席装配策略：**候选槽按注册表走，其余一律走白名单**（闸①的可执行版本）。

    抽成独立函数是为了让「候选注入到底有没有生效」可以被**单独测试**：
    场次计划里写的是槽名，真正的分派只发生在这一处。
    """

    policies = []
    for seat in range(len(policy_names)):
        slot = str(policy_names[seat])
        if slot in candidate_slots:
            spec = dict(candidate_slots[slot] or {})
            # 候选代码只在这一条支路上被装载，而且整个场次都跑在受监管子进程里。
            policy = build_candidate_policy(str(spec["candidate"]),
                                            spec.get("weights") or {}, monotonic)
        else:
            policy = build_panel_policy(slot, monotonic)
        # 绑定参赛者身份：只作诊断标识，不进评分（与 scripts/evaluate.py 同一做法）。
        policy.policy_id = str(participant_ids[seat])
        policies.append(policy)
    return policies


def used_candidate_slots(policy_names: Sequence[str],
                         candidate_slots: Mapping[str, Any]) -> Dict[str, Any]:
    """本场次**实际用到**的候选槽（按这一桌座位上的策略名过滤）。

    为什么要过滤：MatchResult.versions 里的这条记录是「**这一桌真的跑了这份候选代码**」的痕迹，
    而不是「本会话声明过候选槽」的痕迹——焦点参赛者轮空或被淘汰的那些桌不该带上它。
    按座位过滤后，这条痕迹才可被下游（含第四阶段的确认实验）直接当作装载证据使用。
    """

    seated = {str(item) for item in policy_names}
    return {str(key): dict(value) for key, value in dict(candidate_slots or {}).items()
            if str(key) in seated}


def normalize_weights(weights: Mapping[str, Any]) -> Dict[str, float]:
    """参数规范化：全部转 float，用于**逐字比对准入记录**。"""

    return {str(key): float(value) for key, value in dict(weights or {}).items()}


def load_admission_binding(record_path: Path, corpus: Path, *, candidate: str,
                           weights: Mapping[str, Any]) -> Dict[str, Any]:
    """闸②：门禁准入记录必须是**这份候选 + 这份语料**的依据，否则拒绝（fail-closed）。

    四条逐条核验：① 证据种类是 admission（构造触发集不算准入）；② 候选名与参数与本次一致；
    ③ admitted=true；④ 记录里的语料 sha256 与本次声明的语料**逐字节**一致（R7-1）。
    """

    record_path = Path(record_path)
    try:
        record = read_json(record_path)
    except json.JSONDecodeError as error:
        raise StepFailed("门禁记录不是合法 JSON：{0}；取证 {1}".format(
            error, json.dumps(read_failure_report(record_path), ensure_ascii=False,
                              sort_keys=True)))
    if not isinstance(record, Mapping):
        facts = read_failure_report(record_path)
        # **两种原因必须分开写**：路径当时不可见（可能是并发替换/恢复的瞬时态）
        # 与 内容不是 JSON 对象（文件确实在、也能读到，但顶层类型不对）。
        reason = ("路径当时不可见或不是普通文件（瞬时不可读）" if not facts["is_file"]
                  else "JSON 顶层不是对象")
        raise StepFailed("门禁记录不可用（{0}）：{1}；取证 {2}".format(
            reason, record_path, json.dumps(facts, ensure_ascii=False, sort_keys=True)))
    if record.get("evidence_kind") != "admission":
        raise StepFailed("门禁记录不是准入证据（evidence_kind={0!r}）：构造触发集不得当准入依据".format(
                         record.get("evidence_kind")))
    if str(record.get("candidate")) != str(candidate):
        raise StepFailed("门禁记录属于候选 {0!r}，本次是 {1!r}".format(record.get("candidate"),
                                                               candidate))
    recorded = normalize_weights(record.get("weights") or {})
    if recorded != normalize_weights(weights):
        raise StepFailed("门禁记录的参数与本次不一致：记录 {0}，本次 {1}".format(
                         json.dumps(recorded, sort_keys=True),
                         json.dumps(normalize_weights(weights), sort_keys=True)))
    if not bool(record.get("admitted")):
        raise StepFailed("门禁未通过（admitted=false）：{0}".format(
                         record.get("failed") or record.get("insufficient") or []))
    corpus_sha = sha256_file(Path(corpus))
    recorded_corpus = dict(record.get("corpus") or {})
    if recorded_corpus.get("sha256") != corpus_sha:
        raise StepFailed("准入语料不一致：本次 {0}，记录 {1}（语料变了，原准入结论不再适用）".format(
                         corpus_sha, recorded_corpus.get("sha256")))
    return {"record": str(record_path), "record_sha256": sha256_file(Path(record_path)),
            "bound_identity": str(record.get("bound_identity")),
            "corpus_sha256": corpus_sha, "candidate": str(candidate),
            "weights": normalize_weights(weights), "evidence_kind": "admission"}


# --- 10.3 配对阶段比较 -------------------------------------------------------


def build_scenario_participants(participants: Sequence[Mapping[str, Any]], *,
                                candidate_arm: Optional[Mapping[str, Any]],
                                focal: str) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """两臂的参赛者列表：**只有焦点那一位**换策略，其余参战者逐字相同。

    这样两臂的牌山、座位排列、分组全都一样（种子只由合同种子与标签派生），
    差别只有焦点参赛者用的是候选还是基线——配对设计成立的前提就在这里。
    """

    rows: List[Dict[str, Any]] = []
    candidate_slots: Dict[str, Any] = {}
    for item in participants:
        row = {"participant_id": str(item["participant_id"]),
               "policy_name": str(item["policy_name"])}
        if candidate_arm is not None and row["participant_id"] == focal:
            row["policy_name"] = CANDIDATE_SLOT
            candidate_slots[CANDIDATE_SLOT] = {"candidate": str(candidate_arm["candidate"]),
                                               "weights": normalize_weights(candidate_arm["weights"])}
        rows.append(row)
    return rows, candidate_slots


def _collect_pair_deltas(rows: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    """把配对的逐场景结果汇总成主／次指标的根级统计。"""

    metrics = [PRIMARY_STAGE_METRIC] + list(SECONDARY_STAGE_METRICS)
    summary: Dict[str, Any] = {}
    for metric in metrics:
        deltas = [float(row["deltas"][metric]) for row in rows
                  if row.get("paired") and row.get("deltas", {}).get(metric) is not None]
        stats = root_level_statistics(deltas)
        stats["per_scenario"] = [round(item, 6) for item in deltas]
        stats["is_primary"] = metric == PRIMARY_STAGE_METRIC
        summary[metric] = stats
    return summary


def run_stage_comparison(*, contract: Mapping[str, Any], arm: Mapping[str, Any],
                         participants: Sequence[Mapping[str, Any]], scenarios: int,
                         seed_base: int, out_dir: Path, ledger: StageExecutionLedger,
                         admission: Mapping[str, Any], focal: Optional[str] = None,
                         table_timeout_sec: Optional[float] = None,
                         runner_factory: Optional[Callable[[Path, Mapping[str, Any]], Callable[
                             [Sequence[TablePlan]], List[TableOutcome]]]] = None,
                         command: Optional[Sequence[Any]] = None,
                         digest_reader: Optional[Callable[[], str]] = None) -> Dict[str, Any]:
    """跑一次**配对阶段比较**：每个场景跑两臂（候选 / 基线），逐场景取焦点参赛者指标。

    与 PLAN-REVISION §2 的口径一致：完整阶段、候选与基线配对、**以阶段随机种子为独立单位**。
    纪律（与 R8-4 同源）：
      * **整轮可行性预检**：跑第一个场景之前先按「场景数 × 每会话上界 × 臂数」检查预算，
        不足即**一个场景都不跑**地失败（退出码 2），并照样落盘报告；
      * 每个阶段执行后由编排器**对照计划矩阵**核验，缺场次／座位不符即该会话不可排序；
      * **配对键是「声明的基础赛程」**（臂无关量，跑之前算出）：声明场次缺失或同场次号 seed
        漂移 ⇒ 该场景作废（fail-closed）；**官方加赛场次**（得分决定，两臂允许不同）只记录；
      * **单侧失败 ⇒ 整次比较不可排序**（fail-closed）；两臂同时失败按对称情形记 void，
        不作选择性删样本。
    """

    # **开跑前**捕获一次源码指纹与起始时间：报告必须能回答「到底跑的是哪一版代码」。
    read_digest = digest_reader or source_digest_reader
    started_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    source_digest_at_start = str(read_digest())
    participants = [{"participant_id": str(item["participant_id"]),
                     "policy_name": str(item["policy_name"])} for item in participants]
    ids = [item["participant_id"] for item in participants]
    focal_id = str(focal or ids[0])
    if focal_id not in ids:
        raise ValueError("焦点参赛者 {0!r} 不在面板 {1} 里".format(focal_id, ids))
    for item in participants:
        if item["policy_name"] not in PANEL_POLICY_NAMES:
            raise ValueError("基线面板只能用冻结白名单 {0}，得到 {1!r}".format(
                             PANEL_POLICY_NAMES, item["policy_name"]))
    bound = stage_session_table_bound(contract=contract, participants=len(ids))
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    versions_block = contract_versions_block(contract)
    timeout = (float(table_timeout_sec) if table_timeout_sec is not None
               else float(contract["stop"]["table_timeout_sec"]))
    rows: List[Dict[str, Any]] = []
    runs_by_index: Dict[int, Dict[str, Any]] = {}
    budget_stop: Optional[str] = None
    # **整轮可行性预检**（契约 §4.1 的「开跑前预检」，按 Lead 裁定实现为**整轮**口径）：
    #   需要桌数 = 场景数 × 每会话**上界**（含加赛）× 臂数；
    #   不足即**一个场景都不跑**地失败退出（退出码 2），并照样落盘报告——
    #   理由：与「先预留后执行」同源，而且让 9 桌花在不可能配对的场景上尤其贵（实测吞吐比历史慢约 5 倍）。
    required_tables = int(scenarios) * 2 * int(bound["bound"])
    budget_limit = int(ledger.limits["tables"])
    precheck_failed = required_tables > budget_limit
    if precheck_failed:
        budget_stop = ("整轮可行性预检未通过：需要 {0} 桌（场景数 × 每会话上界 × 臂数），"
                       "而 --budget-tables 只有 {1} 桌；**一个场景都没有跑**").format(
                           required_tables, budget_limit)
        for index in range(int(scenarios)):
            rows.append({"scenario_index": index,
                         "panel_seed": derive_scenario_seed(seed_base, index),
                         "paired": False, "failure_kind": "budget_precheck_failed",
                         "reason": budget_stop,
                         "expected_table_bound": bound["bound"],
                         "expected_tables": bound["expected"]})
    for index in range(0 if precheck_failed else int(scenarios)):
        panel_seed = derive_scenario_seed(seed_base, index)
        scenario_contract = contract_with_panel_seed(contract, panel_seed)
        scenario_dir = out_dir / "scenarios" / "scenario-{0:02d}".format(index)
        runs: Dict[str, Optional[Dict[str, Any]]] = {}
        failures: Dict[str, str] = {}
        # **配对键 = 声明的基础赛程**（跑之前就能算出来，且与臂无关）：见 declared_base_plans。
        base_seeds = table_seed_map(declared_base_plans(contract=scenario_contract,
                                                        participants=participants,
                                                        panel_seed=panel_seed))
        base_root = root_set_id_of(sorted(base_seeds.values()))
        arm_reports: Dict[str, Dict[str, Any]] = {}
        for arm_name in ("baseline", "candidate"):
            arm_dir = scenario_dir / arm_name
            members, candidates = build_scenario_participants(
                participants, candidate_arm=(arm if arm_name == "candidate" else None),
                focal=focal_id)
            # 墙钟也要**先预留**：这一会话的墙钟上界 = 桌数上界 × 单桌受监管上限。
            # 不预留就只能事后结算，而事后结算的「超额」已经不是上限了。
            try:
                reservation = ledger.add(
                    {"tables": bound["bound"], "wall_sec": bound["bound"] * timeout},
                    step="table-match", note="scenario-{0:02d}/{1}".format(index, arm_name))
            except StageBudgetExceeded as error:
                # 预留不下就**在跑之前**停，但**如实落盘报告**（编排者按预留额保守计费时要有据）。
                budget_stop = str(error)
                rows.append({"scenario_index": index, "panel_seed": panel_seed,
                             "paired": False, "failure_kind": "budget_exhausted",
                             "reason": budget_stop,
                             "expected_table_bound": bound["bound"],
                             "expected_tables": bound["expected"]})
                break
            started = time.monotonic()
            # runner 由调用方注入（缺省 = 受监管子进程）；测试用夹具 runner 验证配对语义，
            # 不跑真实桌赛——「编排语义」与「真实执行」分开证。
            if runner_factory is None:
                # M1：**每臂一个阶段账**（两臂各算各的账；牌山与赛程仍逐字相同）。
                account = StageAccountLedger(
                    rounds_per_game=int(versions_block["rounds_per_game"]))
                runner = (lambda plan, _dir=arm_dir, _cands=candidates, _account=account:
                          run_tables_supervised(
                              out_dir=_dir, timeout_sec=timeout, plan=plan,
                              versions_block=versions_block, timing=DEFAULT_TIMING,
                              step_limit=int(scenario_contract["stop"]["step_limit"]),
                              candidates=_cands, stage_account=_account))
            else:
                runner = runner_factory(arm_dir, candidates)
            try:
                run = build_run(contract=scenario_contract, participants=members,
                                runner=runner, mode="simulation")
            except (StageFailed, StageVoid) as error:
                # 失败**不退还预留**：这一会话确实消耗过桌数（无法逐场核对时保守预留）。
                ledger.settle(reservation, {"tables": bound["bound"],
                                            "wall_sec": time.monotonic() - started},
                              note="会话失败：保守按上界结算")
                failures[arm_name] = "{0}: {1}".format(type(error).__name__, error)
                runs[arm_name] = None
                write_json(arm_dir / "failure.json", {"schema": FAILURE_SCHEMA,
                                                       "reason": failures[arm_name],
                                                       "panel_seed": panel_seed})
                continue
            measured = time.monotonic() - started
            ledger.settle(reservation, {"tables": len(run["tables"]), "wall_sec": measured},
                          note="scenario-{0:02d}/{1}".format(index, arm_name))
            # **执行集对账**：声明赛程必须被完整执行（缺一即不可排序）；
            # 多出来的只有官方加赛场次（得分决定 ⇒ 两臂允许不同），如实记录、不作废场景。
            executed = {str(table["plan"]["table_id"]): int(table["plan"]["seed"])
                        for table in run["tables"]}
            arm_reports[arm_name] = execution_accounting(base_seeds=base_seeds,
                                                         executed_seeds=executed)
            run["declared_base_root_set_id"] = base_root
            run["execution_accounting"] = dict(arm_reports[arm_name])
            run["config"] = config_snapshot(contract=scenario_contract)
            run["candidates"] = dict(candidates)
            run["admission"] = dict(admission)
            write_json(arm_dir / "run.json", run)
            write_json(arm_dir / "stage-contract.json", scenario_contract)
            _write_tables_jsonl(arm_dir / "tables.jsonl", arm_dir, run)
            (arm_dir / "REPORT.md").write_text(render_run_md(run), encoding="utf-8")
            runs[arm_name] = run
        if budget_stop:
            break
        base_run, cand_run = runs.get("baseline"), runs.get("candidate")
        runs_by_index[index] = {"baseline": base_run, "candidate": cand_run}
        row: Dict[str, Any] = {"scenario_index": index, "panel_seed": panel_seed,
                               "expected_table_bound": bound["bound"],
                               "expected_tables": bound["expected"],
                               "declared_base_tables": len(base_seeds),
                               "declared_base_root_set_id": base_root,
                               "execution_accounting": arm_reports}
        if base_run is None and cand_run is None:
            row.update({"paired": False, "failure_kind": "void_pair",
                        "failures": dict(failures),
                        "reason": "两臂都失败：按对称情形记 void，不作选择性删样本"})
        elif base_run is None or cand_run is None:
            row.update({"paired": False, "failure_kind": "one_sided_failure",
                        "failures": dict(failures),
                        "reason": "单侧失败：整次比较不可排序（fail-closed）"})
        elif any(arm_reports.get(name, {}).get("missing_base_tables")
                 or arm_reports.get(name, {}).get("drifted_seeds")
                 for name in ("baseline", "candidate")):
            # **fail-closed**：声明赛程没被完整执行，或同一场次的 seed 在臂之间漂移
            # （后者意味着派生式里混进了臂相关量——本项目硬要求两臂同牌山）。
            detail = {name: {"missing": arm_reports.get(name, {}).get("missing_base_tables"),
                             "drifted": arm_reports.get(name, {}).get("drifted_seeds")}
                      for name in ("baseline", "candidate")
                      if arm_reports.get(name, {}).get("missing_base_tables")
                      or arm_reports.get(name, {}).get("drifted_seeds")}
            row.update({"paired": False, "failure_kind": "root_set_mismatch",
                        "declared_base_root_set_id": base_root,
                        "execution_accounting": detail,
                        "reason": "声明赛程未被完整执行或两臂同一场次的牌山种子不同："
                                  + json.dumps(detail, ensure_ascii=False, sort_keys=True)})
        else:
            base_metrics = stage_metrics(base_run, focal_id)
            cand_metrics = stage_metrics(cand_run, focal_id)
            deltas = {}
            for metric in [PRIMARY_STAGE_METRIC] + list(SECONDARY_STAGE_METRICS):
                left = cand_metrics.get(metric)
                right = base_metrics.get(metric)
                if left is None or right is None:
                    deltas[metric] = None
                elif isinstance(left, bool) or isinstance(right, bool):
                    deltas[metric] = int(bool(left)) - int(bool(right))
                else:
                    deltas[metric] = float(left) - float(right)
            row.update({"paired": True, "root_set_id": base_root,
                        "baseline": base_metrics, "candidate": cand_metrics,
                        "deltas": deltas,
                        "tables": {"baseline": len(base_run["tables"]),
                                   "candidate": len(cand_run["tables"])},
                        "extra_tables_by_arm": {name: arm_reports[name]["extra_tables"]
                                                for name in ("baseline", "candidate")}})
        rows.append(row)

    paired_rows = [row for row in rows if row.get("paired")]
    failures_present = [row for row in rows if not row.get("paired")]
    summary = _collect_pair_deltas(paired_rows)
    rankable = not failures_present and len(rows) == int(scenarios)
    reason = None
    if failures_present:
        reason = "有 {0} 个场景未形成有效配对：{1}".format(
            len(failures_present),
            sorted({str(row.get("failure_kind")) for row in failures_present}))
    contract_digest = sha256_text(contract_text(contract))
    # 收尾时再读一次指纹：两次不同即说明**运行期间源码被改过**，报告必须说出来。
    finished_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    source_digest_at_end = str(read_digest())
    seeds = [int(row["panel_seed"]) for row in rows]
    # 预留口径按 Lead 裁定**统一用上界**（期望值只作参考）：编排者与执行件用同一个数，
    # 否则「编排者按期望预留、执行件按上界预留」必然再撞（实测第 10 个场景就是这样被挡掉的）。
    expected_tables = int(scenarios) * 2 * int(bound["expected"])
    planned_tables = int(scenarios) * 2 * int(bound["bound"])
    plan_problems: List[str] = []
    for index, runs in sorted(runs_by_index.items()):
        for arm_name in ("baseline", "candidate"):
            for verdict in (runs.get(arm_name) or {}).get("plan_verification") or ():
                if not verdict.get("ok"):
                    plan_problems.append("场景 {0}／{1}：阶段 {2} 计划核验失败：{3}".format(
                        index, arm_name, verdict.get("stage_no"),
                        "；".join(str(item) for item in verdict.get("problems") or ())))
    primary_stats = dict(summary[PRIMARY_STAGE_METRIC])
    paired_baselines = [float(row["baseline"][PRIMARY_STAGE_METRIC]) for row in paired_rows]
    paired_candidates = [float(row["candidate"][PRIMARY_STAGE_METRIC]) for row in paired_rows]
    metrics = {
        "primary": PRIMARY_STAGE_METRIC,
        "unit": "场景种子（独立单位；不得用配对×双臂推标准误）",
        "baseline_value": (round(sum(paired_baselines) / len(paired_baselines), 6)
                           if paired_baselines else None),
        "candidate_value": (round(sum(paired_candidates) / len(paired_candidates), 6)
                            if paired_candidates else None),
        "delta": primary_stats["mean"],
        "sd_root": primary_stats["sd_root"],
        "se_root": primary_stats["se_root"],
        "mde": primary_stats["mde"],
        "per_scenario": [{"seed": int(row["panel_seed"]),
                          "baseline": row["baseline"][PRIMARY_STAGE_METRIC],
                          "candidate": row["candidate"][PRIMARY_STAGE_METRIC],
                          "delta": row["deltas"][PRIMARY_STAGE_METRIC]}
                         for row in paired_rows],
        "secondary": {metric: dict(stats) for metric, stats in summary.items()
                      if metric != PRIMARY_STAGE_METRIC},
    }
    payload: Dict[str, Any] = {
        "schema": COMPARE_SCHEMA,
        # 编排者按 status 判「完成 / 不可排序」：**不得**用部分成功冒充 complete。
        "status": "complete" if rankable else "unrankable",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "arm": {"id": str(arm["id"]), "candidate": str(arm["candidate"]),
                "weights": normalize_weights(arm["weights"]),
                "family": arm.get("family"),
                "identity": admission.get("bound_identity"),
                "gate_record_sha256": admission.get("record_sha256"),
                "admission_corpus_sha256": admission.get("corpus_sha256")},
        "baseline": {"policy": participants[ids.index(focal_id)]["policy_name"],
                     "contract_sha256": contract_digest},
        "admission": dict(admission),
        "contract_sha256": contract_digest,
        "panel": {"scenarios": int(scenarios), "seeds": seeds, "seed_base": int(seed_base),
                  "participants": len(ids), "focal": focal_id,
                  "panel_id": panel_declaration_id(contract_sha256=contract_digest,
                                                   participants=participants, focal=focal_id,
                                                   seed_base=int(seed_base), seeds=seeds),
                  "baseline_policy": participants[ids.index(focal_id)]["policy_name"],
                  "tables_per_session": bound,
                  "scenario_seed_rule": "derive_seed(seed_base, stagecand-scenario, 序号)"
                                         "（**不含臂标识**：两臂同场景必须同牌山）",
                  "pairing_basis": "**声明的基础赛程**（海选 + 组内 + 决赛首轮）的 root_set_id；"
                                   "官方加赛场次按臂独立记录，不作废场景",
                  "base_root_set_ids": [row.get("declared_base_root_set_id") for row in rows],
                  "panel_id_rule": "sha256(合同 sha256 | 参赛者 | 焦点 | 种子基准 | 场景种子)"
                                   " 前 12 位，只由**声明**复算"},
        "tables": {"spent": int(round(ledger.spent["tables"])), "planned": planned_tables,
                   "planned_rule": "scenarios × 每会话**上界**（含加赛）× arms"
                                   "——与编排者预留**同口径**（上界），结算只看 spent",
                   "expected": expected_tables,
                   "expected_rule": "scenarios × 每会话期望 × arms —— 只作参考，不作预留依据",
                   "unit": "桌（双臂各算一桌）",
                   "spent_rule": "完成会话按**实际**桌数；失败会话按该会话的桌数上界保守计入"
                                 "（无法逐场核对时不免费重演）；任何会话的计入额都不超过其预留额",
                   "overruns": [dict(item) for item in ledger.overruns]},
        "budget": {"budget_tables": budget_limit, "required_tables": required_tables,
                   "precheck": "passed" if not precheck_failed else "failed",
                   "precheck_rule": "整轮可行性：场景数 × 每会话上界（含加赛）× 臂数"
                                    " ≤ --budget-tables；不足即一个场景都不跑地失败退出（退出码 2）",
                   "half_run_rule": "预检通过后若仍因超额（实际 > 该会话预留）而预留不下："
                                    "已跑场景的产物**全部保留、不删不补零**，其余场景记 budget_exhausted，"
                                    "整次比较判 unrankable，按实际已跑桌数结算",
                   "stop_reason": budget_stop,
                   "note": "执行件不得自行扩容：预留不下即在跑之前停，并如实落盘本报告"},
        "pairs": len(paired_rows),
        "pairs_unit": "一个配对 = 一个场景（该场景下基线会话与候选会话各一次完整阶段）",
        "metrics": metrics,
        "verification": {"plan_ok": not plan_problems, "problems": plan_problems,
                         "pairing_basis": "声明赛程 root_set_id（臂无关量）；"
                                          "官方加赛只作记录，不参与配对判定",
                         "extra_tables": [
                             {"scenario_index": row["scenario_index"], "arm": name,
                              "table_ids": list(ids)}
                             for row in rows if row.get("paired")
                             for name, ids in (row.get("extra_tables_by_arm") or {}).items() if ids],
                         "pairing_problems": [
                             {"scenario_index": row["scenario_index"],
                              "kind": row.get("failure_kind"), "reason": row.get("reason")}
                             for row in failures_present]},
        "wall_sec": round(float(ledger.spent["wall_sec"]), 3),
        "command": [str(item) for item in (command or ())],
        "started_at": started_at,
        "finished_at": finished_at,
        "source_digest_at_start": source_digest_at_start,
        "source_digest_at_end": source_digest_at_end,
        "tool_source_changed_during_run": (source_digest_at_start != source_digest_at_end),
        "versions": stage_tool_versions(
            contract=contract, opponents=participants[ids.index(focal_id)]["policy_name"],
            source_digest=source_digest_at_start),
        "primary_metric": PRIMARY_STAGE_METRIC,
        "secondary_metrics": list(SECONDARY_STAGE_METRICS),
        "scenarios": rows,
        "summary": summary,
        # 执行台账：只作执行记录，**不是预算账本**（预算账归编排者）。
        "execution": {"schema": STAGE_LEDGER_SCHEMA, "ledger": ledger.to_json(),
                      "tables_spent": ledger.spent["tables"],
                      "wall_sec_spent": ledger.spent["wall_sec"],
                      "note": "执行台账：只记本执行件跑了多少桌；预算账在 tools/sitin_search.py"},
        "verdict": {"rankable": rankable, "reason": reason,
                    "n_paired_scenarios": len(paired_rows),
                    "mde_note": "MDE 是规划用的不确定性说明，不是显著性阈值或自动晋级规则"},
        "three_states": {"tool_completion": "completed",
                         "tool_notes": "阶段比较跑完 {0} 个场景 × 2 臂".format(len(rows)),
                         "candidates_found": "see_orchestrator",
                         "release_gate": "not_evaluated"},
    }
    write_json(out_dir / STAGE_COMPARE_REPORT, payload)
    (out_dir / "COMPARE.md").write_text(render_compare_md(payload), encoding="utf-8")
    return payload


def render_compare_md(payload: Mapping[str, Any]) -> str:
    """阶段比较的人读件：**只说配对事实与不确定性**，不给强弱结论。"""

    arm = dict(payload["arm"])
    lines = ["# 坐隐 3.4 阶段比较（候选 vs 基线，按场景种子配对）", ""]
    lines.append("候选 `{0}`，参数 `{1}`，族 `{2}`。".format(
                 arm["candidate"], json.dumps(arm["weights"], ensure_ascii=False, sort_keys=True),
                 arm.get("family")))
    lines.append("")
    lines.append("准入依据：`{0}`（sha256 `{1}`），语料 sha256 `{2}`。".format(
                 payload["admission"]["record"],
                 payload["admission"]["record_sha256"][:16],
                 payload["admission"]["corpus_sha256"][:16]))
    panel = dict(payload["panel"])
    lines.append("")
    lines.append("面板：{0} 人完整阶段（海选 → 组内 → 决赛），焦点 `{1}`，每会话期望 {2} 桌"
                 "（加赛上界 {3} 桌）。".format(
                     panel["participants"], panel["focal"],
                     panel["tables_per_session"]["expected"],
                     panel["tables_per_session"]["bound"]))
    lines.append("")
    lines.append("**配对键 = 声明的基础赛程**（海选 + 组内 + 决赛首轮，臂无关量）："
                 "{0}。官方加赛场次按臂独立记录，**不作废场景**。".format(
                     "、".join("`{0}`".format(item)
                               for item in dict(panel).get("base_root_set_ids") or [])))
    lines.append("")
    lines.append("## 逐场景配对事实")
    lines.append("")
    lines.append("| 场景 | panel_seed | 状态 | 基线 {0} | 候选 {0} | Δ主指标 | Δ进决赛 |"
                 " 场次（基线/候选） | 加赛（基线/候选） |".format(PRIMARY_STAGE_METRIC))
    lines.append("| ---: | ---: | --- | ---: | ---: | ---: | ---: | --- | --- |")
    for row in payload["scenarios"]:
        if row.get("paired"):
            tables = dict(row.get("tables") or {})
            extras = dict(row.get("extra_tables_by_arm") or {})
            lines.append("| {0} | {1} | 配对 | {2} | {3} | {4} | {5} | {6}/{7} | {8}/{9} |".format(
                         row["scenario_index"], row["panel_seed"],
                         row["baseline"][PRIMARY_STAGE_METRIC],
                         row["candidate"][PRIMARY_STAGE_METRIC],
                         row["deltas"][PRIMARY_STAGE_METRIC],
                         row["deltas"]["reached_final"],
                         tables.get("baseline"), tables.get("candidate"),
                         len(extras.get("baseline") or []), len(extras.get("candidate") or [])))
        else:
            lines.append("| {0} | {1} | **{2}** | — | — | — | — | — | — |".format(
                         row["scenario_index"], row["panel_seed"], row.get("failure_kind")))
    lines.append("")
    lines.append("## 根级统计（独立单位 = 场景种子）")
    lines.append("")
    lines.append("| 指标 | n | 均值 | 根级 sd | SE | MDE | 可排序 |")
    lines.append("| --- | ---: | ---: | ---: | ---: | ---: | --- |")
    for metric, stats in payload["summary"].items():
        lines.append("| {0}{1} | {2} | {3} | {4} | {5} | {6} | {7} |".format(
                     metric, "（主）" if stats.get("is_primary") else "", stats["n_roots"],
                     stats["mean"], stats["sd_root"], stats["se_root"], stats["mde"],
                     "是" if stats["rankable"] else "否：{0}".format(stats["rankable_reason"])))
    extra = list((payload.get("verification") or {}).get("extra_tables") or [])
    lines.append("")
    lines.append("## 官方加赛场次（**只记录，不作废场景**）")
    lines.append("")
    if not extra:
        lines.append("无。")
    for item in extra:
        lines.append("- 场景 {0}／{1}：{2}".format(item["scenario_index"], item["arm"],
                                                   "、".join(item["table_ids"])))
    execution = dict(payload.get("execution") or {})
    lines.append("")
    lines.append("## 执行量（本执行件的台账，不是预算账）")
    lines.append("")
    lines.append("桌数 {0}，墙钟 {1} 秒（schema `{2}`）；编排者据此透传进搜索账。".format(
                 execution.get("tables_spent"), round(float(execution.get("wall_sec_spent") or 0.0), 1),
                 execution.get("schema")))
    verdict = dict(payload["verdict"])
    lines.append("")
    lines.append("## 判定边界")
    lines.append("")
    lines.append("- 可排序：**{0}**{1}".format(
                 "是" if verdict["rankable"] else "否",
                 "" if verdict["rankable"] else "（{0}）".format(verdict["reason"])))
    lines.append("- {0}".format(verdict["mde_note"]))
    lines.append("- 主指标是**本项目声明的阶段目标代理**，不是官方指标，也不能外推为真实晋级概率。")
    return NEWLINE.join(lines) + NEWLINE


def compare_command_line(args: Any) -> List[str]:
    """复算本次 compare 的等效 argv（写进报告，便于编排者对账与人工复跑）。

    为什么复算而不是照抄 sys.argv：`main(argv)` 在测试与编排器里可能带不同的前缀，
    照抄会让"报告里的命令"与"这条命令实际做了什么"对不上。
    """

    command = [sys.executable, str(Path(__file__).resolve()), "compare",
               "--candidate", str(args.candidate), "--weights", str(args.weights),
               "--gate-record", str(args.gate_record),
               "--admission-corpus", str(args.admission_corpus)]
    if getattr(args, "contract_file", None):
        command += ["--contract-file", str(args.contract_file)]
    else:
        command += ["--frozen-at", str(args.frozen_at)]
    command += ["--scenarios", str(int(args.scenarios)), "--seed-base", str(int(args.seed_base)),
                "--participants", str(int(args.participants)),
                "--participant-prefix", str(args.participant_prefix)]
    if getattr(args, "focal", None):
        command += ["--focal", str(args.focal)]
    command += ["--budget-tables", str(int(args.budget_tables))]
    if getattr(args, "budget_wall_sec", None):
        command += ["--budget-wall-sec", str(float(args.budget_wall_sec))]
    if getattr(args, "table_timeout_sec", None) is not None:
        command += ["--table-timeout-sec", str(float(args.table_timeout_sec))]
    if getattr(args, "arm_id", None):
        command += ["--arm-id", str(args.arm_id)]
    if getattr(args, "family", None):
        command += ["--family", str(args.family)]
    command += ["--out", str(args.out)]
    return command


def cmd_compare(args) -> int:
    """3.4 阶段比较：单个候选 vs 基线。**缺准入记录或语料不符直接拒绝**（闸②）。"""

    contract = _contract_from_args(args)
    out_dir = Path(args.out)
    if (out_dir / "compare.json").is_file() and not args.force:
        raise SystemExit("产物目录已有 compare.json：拒绝覆盖（换目录或显式 --force）")
    out_dir.mkdir(parents=True, exist_ok=True)
    weights = json.loads(args.weights)
    corpus = Path(args.admission_corpus)
    try:
        admission = load_admission_binding(Path(args.gate_record), corpus,
                                           candidate=args.candidate, weights=weights)
    except StepFailed as error:
        # 拒绝也要落盘：否则「为什么没跑」只能靠人回忆（与门禁 fail-closed 同一纪律）。
        write_json(out_dir / "intake.json", {
            "schema": COMPARE_SCHEMA, "status": "refused", "reason": str(error),
            "candidate": args.candidate, "weights": normalize_weights(weights),
            "gate_record": str(args.gate_record), "admission_corpus": str(args.admission_corpus)})
        raise SystemExit("拒绝跑阶段比较：{0}".format(error))
    write_json(out_dir / "intake.json", {"schema": COMPARE_SCHEMA, "status": "accepted",
                                          "admission": admission,
                                          "contract_file": args.contract_file})
    arm = {"id": args.arm_id or slug(args.candidate), "candidate": args.candidate,
           "weights": weights, "family": args.family}
    participants = participants_for(args.participants, args.panel_policy,
                                    prefix=args.participant_prefix)
    # 墙钟上限缺省按**整次比较的上界**推导：场景数 × 2 臂 × 每会话桌数上界 × 单桌受监管上限。
    # 单会话的预留只占其中一份，因此顺序执行时不会互相挤压。
    session = stage_session_table_bound(contract=contract, participants=len(participants))
    table_timeout = (float(args.table_timeout_sec) if args.table_timeout_sec is not None
                     else float(contract["stop"]["table_timeout_sec"]))
    wall_limit = (float(args.budget_wall_sec) if args.budget_wall_sec
                  else session["bound"] * table_timeout * 2 * int(args.scenarios))
    ledger = StageExecutionLedger(out_dir / "execution-ledger.json",
                                  {"tables": int(args.budget_tables), "wall_sec": wall_limit})
    payload = run_stage_comparison(
        contract=contract, arm=arm, participants=participants, scenarios=int(args.scenarios),
        seed_base=int(args.seed_base), out_dir=out_dir, ledger=ledger, admission=admission,
        focal=args.focal, table_timeout_sec=args.table_timeout_sec,
        command=compare_command_line(args))
    metrics = dict(payload["metrics"])
    # 退出码按编排者的约定（STAGE-COMPARE-CONTRACT.md §5）：
    # 0 = 完成且计划核验通过；2 = 不可排序（含到预算上限）；其它 = 执行件自身异常。
    ok = payload["status"] == "complete"
    print(json.dumps({"ok": ok, "status": payload["status"],
                      "candidate": args.candidate,
                      "scenarios": len(payload["scenarios"]), "pairs": payload["pairs"],
                      "primary_metric": PRIMARY_STAGE_METRIC,
                      "delta": metrics["delta"], "se_root": metrics["se_root"],
                      "mde": metrics["mde"], "reason": payload["verdict"]["reason"],
                      "tables": payload["tables"], "budget_stop": payload["budget"]["stop_reason"],
                      "report": str(out_dir / STAGE_COMPARE_REPORT)},
                     ensure_ascii=False))
    return 0 if ok else 2


# ---------------------------------------------------------------------------
# 11. 命令
# ---------------------------------------------------------------------------


def _contract_from_args(args) -> Dict[str, Any]:
    """取本次命令使用的合同。

    **冻结日期必须显式给出**（复审 #16）：不给 --frozen-at 又不给 --contract-file 就直接失败，
    不允许退回「当天 UTC」——那会让同一条复跑命令在不同日期产出不同 sha。
    """

    if args.contract_file:
        contract = json.loads(Path(args.contract_file).read_text(encoding="utf-8"))
        problems = validate_contract(contract)
        if problems:
            raise SystemExit("合同校验失败：" + NEWLINE + "- " + (NEWLINE + "- ").join(problems))
        return contract
    if not getattr(args, "frozen_at", None):
        raise SystemExit("必须显式给出 --frozen-at YYYY-MM-DD（或 --contract-file）："
                         "阶段合同不得默认取当天日期")
    return default_contract(
        ruleset_version=args.ruleset_version, base_score=args.base_score,
        you_cai_bi_kao=(args.you_cai_bi_kao == "true"), rounds_per_game=args.rounds_per_game,
        clock_mode=args.clock_mode, panel_seed=args.panel_seed, panel_policy=args.panel_policy,
        tables_per_batch=args.tables_per_batch, batches=args.batches,
        tables_per_group=args.tables_per_group, tables_in_final=args.tables_in_final,
        max_overtime=args.max_overtime, table_timeout_sec=args.table_timeout_sec,
        step_limit=args.step_limit, frozen_at=args.frozen_at)


def cmd_contract(args) -> int:
    contract = _contract_from_args(args)
    problems = validate_contract(contract)
    if problems:
        raise SystemExit("合同校验失败：" + NEWLINE + "- " + (NEWLINE + "- ").join(problems))
    text = contract_text(contract)
    digest = sha256_text(text)
    if args.out:
        out_dir = Path(args.out)
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "stage-contract.json").write_text(text, encoding="utf-8")
        (out_dir / "STAGE-CONTRACT.md").write_text(
            render_contract_md(contract, contract_sha256=digest), encoding="utf-8")
    print(json.dumps({"ok": True, "contract_sha256": digest,
                      "unresolved": len(contract["unresolved"])}, ensure_ascii=False))
    return 0


def cmd_check(args) -> int:
    """只核验合同：**把问题当数据报出来并返回 2**，而不是抛 SystemExit。

    为什么不让它沿用 _contract_from_args 的硬停：check 是"检查"命令，
    交付合同被篡改（例如引文被改）时应当以非零退出码 + problems 列表收场，
    这样脚本与评审都能直接读；抛 SystemExit 会让调用方拿到 traceback 而不是问题清单。
    """

    if args.contract_file:
        try:
            contract = json.loads(Path(args.contract_file).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            print(json.dumps({"ok": False, "problems": ["合同文件不可读：{0}".format(error)]},
                             ensure_ascii=False))
            return 2
    else:
        try:
            contract = _contract_from_args(args)
        except SystemExit as error:
            print(json.dumps({"ok": False, "problems": [str(error)]}, ensure_ascii=False))
            return 2
    problems = validate_contract(contract)
    print(json.dumps({"ok": not problems, "problems": problems}, ensure_ascii=False))
    return 0 if not problems else 2


def _ledger_rows_from_json(payload: Any) -> Tuple[List[LedgerRow], List[str]]:
    """把 JSON 账本转成 LedgerRow 列表；问题逐条报出（空列表 = 可用），不抛异常。"""

    if not isinstance(payload, list) or not payload:
        return [], ["ledger 必须是非空的账本数组（LedgerRow 形状对象）"]
    problems: List[str] = []
    rows: List[LedgerRow] = []
    seen = set()
    for index, item in enumerate(payload):
        if not isinstance(item, Mapping) or not str((item or {}).get("participant_id") or "").strip():
            problems.append("ledger[{0}] 不是对象或缺 participant_id".format(index))
            continue
        pid = str(item["participant_id"])
        if pid in seen:
            problems.append("ledger 里 participant_id 重复：{0}".format(pid))
            continue
        seen.add(pid)
        god = item.get("god_count")
        rows.append(LedgerRow(
            participant_id=pid,
            total_score=int(item.get("total_score") or 0),
            place_points=int(item.get("place_points") or 0),
            tables_played=int(item.get("tables_played") or 0),
            byes=int(item.get("byes") or 0),
            god_count=None if god is None else int(god),
        ))
    return rows, problems


def cmd_group_eval(args) -> int:
    """group_advance_v1 目标求值：账本 → 焦点 U 区间、全员区间表与辅助指标。

    只读合同与账本 JSON，不跑任何桌赛、不调用模型。失败（文件不可读、合同校验
    不过、缺 objective、焦点不在账本）都输出 {"ok": false, "problems": [...]} 并
    返回 2——与 cmd_check 同款「把问题当数据」的纪律，不抛 SystemExit。
    """

    def fail(problems: Sequence[str]) -> int:
        print(json.dumps({"ok": False, "problems": list(problems)}, ensure_ascii=False))
        return 2

    try:
        contract = json.loads(Path(args.contract_file).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return fail(["合同文件不可读：{0}".format(error)])
    problems = validate_contract(contract)
    if problems:
        return fail(problems)
    objective = contract.get("objective")
    if not isinstance(objective, Mapping):
        return fail(["group-eval 需要 objective 键（group_advance_v1 目标合同）"])
    if objective.get("target_id") != "group_advance_v1":
        return fail(["objective.target_id 必须是 'group_advance_v1'（收到 {0!r}）".format(
            objective.get("target_id"))])
    try:
        payload = json.loads(Path(args.ledger).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return fail(["账本文件不可读：{0}".format(error)])
    rows, problems = _ledger_rows_from_json(payload)
    if problems:
        return fail(problems)
    focal = str(args.focal)
    if focal not in {row.participant_id for row in rows}:
        return fail(["焦点参赛者 {0!r} 不在账本里".format(focal)])
    advance = int(objective.get("advance_count", 2))
    utility = group_advance_utility(rows, focal_id=focal, advance=advance)
    auxiliary = auxiliary_stage_reports(rows)
    positive = bool(auxiliary["positive_net_score"].get(focal))
    # 「前二且正积分」联合事件在这里组合（调用方语义），单独报告，不与 U 相加。
    print(json.dumps({
        "ok": True,
        "schema": "sitin-group-eval/1",
        "contract_file": str(args.contract_file),
        "contract_sha256": sha256_text(contract_text(contract)),
        "target_id": objective.get("target_id"),
        "advance_count": advance,
        "focal_utility": utility,
        "focal_advance_and_positive": {
            "low": utility["u_low"] if positive else 0,
            "high": utility["u_high"] if positive else 0,
            "positive_net_score": positive,
        },
        "intervals": group_advance_intervals(rows),
        "auxiliary": auxiliary,
    }, ensure_ascii=False))
    return 0


def cmd_run(args) -> int:
    """真实小规模编排：每个场次一个受监管子进程。"""

    contract = _contract_from_args(args)
    participants = participants_for(args.participants, args.panel_policy,
                                    prefix=args.participant_prefix)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    versions_block = contract_versions_block(contract)
    snapshot = config_snapshot(contract=contract)

    # M1：整轮一个阶段账（账按阶段号隔离；跨决赛/加赛的多次执行调用连续累计）。
    account = StageAccountLedger(rounds_per_game=int(versions_block["rounds_per_game"]))

    def runner(plan: Sequence[TablePlan]) -> List[TableOutcome]:
        return run_tables_supervised(
            out_dir=out_dir, timeout_sec=float(contract["stop"]["table_timeout_sec"]),
            plan=plan, versions_block=versions_block, timing=DEFAULT_TIMING,
            step_limit=int(contract["stop"]["step_limit"]), stage_account=account)

    try:
        run = build_run(contract=contract, participants=participants, runner=runner,
                        mode="simulation")
    except StageVoid as error:
        # 整场作废是**官方规则下的合法结局**（不是错误，也不产生名次）：显式落盘。
        write_json(out_dir / "stage-contract.json", contract)
        write_json(out_dir / "void.json", {
            "schema": VOID_SCHEMA, "reason": str(error),
            "participants": len(participants),
            "contract_sha256": sha256_text(contract_text(contract))})
        print(json.dumps({"ok": True, "void": True, "reason": str(error)}, ensure_ascii=False))
        return 0
    except StageFailed as error:
        write_json(out_dir / "stage-contract.json", contract)
        write_json(out_dir / "failure.json", {
            "schema": FAILURE_SCHEMA, "reason": str(error),
            "contract_sha256": sha256_text(contract_text(contract))})
        print(json.dumps({"ok": False, "reason": str(error)}, ensure_ascii=False))
        return 2
    run["config"] = snapshot
    write_json(out_dir / "stage-contract.json", contract)
    write_json(out_dir / "run.json", run)
    _write_tables_jsonl(out_dir / "tables.jsonl", out_dir, run)
    (out_dir / "REPORT.md").write_text(render_run_md(run), encoding="utf-8")
    print(json.dumps({"ok": True, "tables": len(run["tables"]), "panel_id": run["panel_id"],
                      "root_set_id": run["root_set_id"],
                      "stages": [stage["name"] for stage in run["stages"]]}, ensure_ascii=False))
    return 0


def cmd_fixture(args) -> int:
    """构造夹具：只验证编排语义（并列名次分 / 轮空 / 清零 / 组内排名 / 决赛加赛）。"""

    contract = _contract_from_args(args)
    fixture = json.loads(Path(args.fixture).read_text(encoding="utf-8"))
    if fixture.get("schema") != FIXTURE_SCHEMA:
        raise SystemExit("夹具 schema 必须是 {0}".format(FIXTURE_SCHEMA))
    participants = participants_for(args.participants, args.panel_policy,
                                    prefix=args.participant_prefix)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        run = build_run(contract=contract, participants=participants,
                        runner=fixture_runner(fixture), mode="fixture")
    except StageVoid as error:
        write_json(out_dir / "void.json", {"schema": VOID_SCHEMA, "reason": str(error),
                                           "participants": len(participants)})
        print(json.dumps({"ok": True, "void": True, "reason": str(error)}, ensure_ascii=False))
        return 0
    run["config"] = config_snapshot(contract=contract)
    run["fixture"] = {"path": str(args.fixture), "sha256": sha256_file(Path(args.fixture)),
                      "note": fixture.get("note")}
    write_json(out_dir / "stage-contract.json", contract)
    write_json(out_dir / "run.json", run)
    (out_dir / "REPORT.md").write_text(render_run_md(run), encoding="utf-8")
    print(json.dumps({"ok": True, "mode": "fixture", "tables": len(run["tables"])},
                     ensure_ascii=False))
    return 0


#: 重演逐场次对账的字段；**seed 与座位也必须比对**，不能只比分数。
REPLAY_TABLE_FIELDS: Tuple[str, ...] = ("seed", "scenario_id", "stage_no", "group_index",
                                        "seat_participants", "scores_by_seat", "status")
#: 逐场次信封里**不参与对账**的字段与理由（把"没比"写成明文，而不是留成盲点）。
REPLAY_NOT_COMPARED_FIELDS: Dict[str, str] = {
    "wall_ms": "墙钟耗时随机器负载变化，不是可复现的语义字段",
    "supervision": "受监管执行的结局含耗时与信号，只用于故障取证，不参与语义对账",
}
#: 重演逐阶段名次对账的字段。
REPLAY_STANDING_FIELDS: Tuple[str, ...] = ("participant_id", "rank", "total_score",
                                           "place_points", "tables_played", "byes",
                                           "god_count", "tie_unresolved", "keys_used")
#: 重演逐阶段对账的晋级字段。
REPLAY_ADVANCE_FIELDS: Tuple[str, ...] = ("quota", "quota_per_group", "advanced", "backup",
                                          "eliminated", "boundary_unresolved")
#: 逐场次记账字段：**必须覆盖承载本轮整改的字段**（加赛名次分规则就在这里），
#: 否则重演证明不了"整改过的 bug 复发会被发现"。
REPLAY_SEAT_ACCOUNTING_FIELDS: Tuple[str, ...] = ("table_id", "stage_kind", "scores_by_seat",
                                                  "place_points_by_seat", "place_points_rule",
                                                  "participants_by_seat")
#: 逐批记账字段（轮空名单 = 本轮修掉的 5/6/7 人记账洞就落在这里）。
REPLAY_BATCH_FIELDS: Tuple[str, ...] = ("batch_index", "tables", "seated", "byes")
#: **计划核验结论**字段（R8-4 口径）；逐场次计划的全部字段由 compare_plans 按键集合全比。
REPLAY_PLAN_FIELDS: Tuple[str, ...] = ("stage_no", "ok", "planned_tables", "observed_tables",
                                       "status_counts", "problems")


def _rows_signature(rows: Optional[Sequence[Mapping[str, Any]]],
                    fields: Sequence[str]) -> List[Tuple[Any, ...]]:
    """逐行取指定字段做签名（缺字段 ⇒ None，从而与有值的记录必然不等 —— fail-closed）。"""

    return [tuple(row.get(field) for field in fields) for row in rows or []]


def compare_plans(expected_run: Mapping[str, Any],
                  recomputed_run: Mapping[str, Any]) -> List[str]:
    """逐场次比对**完整计划**（所有字段），不是挑几个字段比。

    为什么按键集合全比而不是列举字段：列举必然漏——复审在上一版里数出
    permutation / initial_dealer / batch_index / match_id / pair_id / tables_in_stage
    等 31 处"改了也不会报"。这里对每张表比对**键集合**与**每个键的值**：
    多键、少键、改任一键都会进 problems，字段增减不需要维护列表。
    """

    problems: List[str] = []
    want = {str(item["plan"]["table_id"]): item["plan"] for item in expected_run.get("tables", [])}
    got = {str(item["plan"]["table_id"]): item["plan"] for item in recomputed_run.get("tables", [])}
    for table_id in sorted(set(want) - set(got)):
        problems.append("重算缺少场次 {0}".format(table_id))
    for table_id in sorted(set(got) - set(want)):
        problems.append("重算多出场次 {0}".format(table_id))
    for table_id in sorted(set(want) & set(got)):
        left, right = want[table_id], got[table_id]
        if set(left) != set(right):
            problems.append("场次 {0} 的计划字段集合不同：记录 {1}，重算 {2}".format(
                table_id, sorted(left), sorted(right)))
        for key in sorted(set(left) | set(right)):
            if left.get(key) != right.get(key):
                problems.append("场次 {0} 的计划字段 {1} 不一致：记录 {2}，重算 {3}".format(
                    table_id, key, left.get(key), right.get(key)))
    return problems


def plan_field_inventory(run: Mapping[str, Any]) -> List[str]:
    """运行记录里出现过的**全部计划字段**（用于在产物里自证对账覆盖面）。"""

    fields: set = set()
    for item in run.get("tables", []):
        fields.update((item.get("plan") or {}).keys())
    return sorted(fields)


def _envelope_of(row: "TableOutcome") -> Mapping[str, Any]:
    return dict((row.result or {}).get(ROW_ENVELOPE_KEY) or {})


def compare_expected_tables(rows: Mapping[str, TableOutcome],
                            expected_run: Mapping[str, Any]) -> List[str]:
    """把**重演输入**（tables.jsonl）与**运行记录**（run.json）逐场次对账。

    为什么必须两边都读：只把 run.json 当期望、再用同一份 tables.jsonl 重算一遍，
    等于同源再算一次——任一侧被篡改都发现不了（复审 #18）。这里两侧都读，
    改任一侧都会进 problems；且**缺字段一律 fail-closed**（不是跳过比对）。
    """

    problems: List[str] = []
    expected = {str(item["plan"]["table_id"]): item for item in expected_run.get("tables", [])}
    for table_id in sorted(expected):
        entry = expected[table_id]
        plan = entry.get("plan") or {}
        outcome = entry.get("outcome") or {}
        row = rows.get(table_id)
        if row is None:
            problems.append("重演输入缺少运行记录里的场次 {0}".format(table_id))
            continue
        # **fail-closed**：重演输入缺 seed 不是"跳过比对"，而是 problem。
        # 静默跳过与本函数"任一侧被改动都会进 problems"的自述直接冲突。
        if row.seed is None:
            problems.append("重演输入缺少场次 {0} 的 seed（fail-closed：缺失即 problem，不做跳过比对）"
                            .format(table_id))
        elif int(plan.get("seed", -1)) != int(row.seed):
            problems.append("场次 {0} 的 seed 不一致：记录 {1}，重演输入 {2}".format(
                table_id, plan.get("seed"), row.seed))
        actual_scenario = (row.scenario_id if row.scenario_id is not None
                           else (row.result or {}).get("scenario_id"))
        if str(plan.get("scenario_id")) != str(actual_scenario):
            problems.append("场次 {0} 的 scenario_id 不一致：记录 {1}，重演输入 {2}".format(
                table_id, plan.get("scenario_id"), actual_scenario))
        expected_seats = [str(item) for item in plan.get("seat_participants") or []]
        actual_seats = [str(item) for item in row.participant_ids_by_seat]
        if expected_seats != actual_seats:
            problems.append("场次 {0} 的座位身份不一致：记录 {1}，重演输入 {2}".format(
                table_id, expected_seats, actual_seats))
        # 信封里的阶段定位同样要比：输入行被改到别的阶段/组也必须报出来（缺字段 fail-closed）。
        envelope = _envelope_of(row)
        for field in ("stage_no", "group_index"):
            if field not in envelope:
                problems.append("重演输入缺少场次 {0} 的 {1}（fail-closed：缺失即 problem）".format(
                    table_id, field))
            elif envelope.get(field) != plan.get(field):
                problems.append("场次 {0} 的 {1} 不一致：记录 {2}，重演输入 {3}".format(
                    table_id, field, plan.get(field), envelope.get(field)))
        envelope_seats = [str(item) for item in envelope.get("seat_participants") or []]
        if envelope_seats and envelope_seats != actual_seats:
            problems.append("场次 {0} 的信封座位与结果行座位不一致：{1} vs {2}".format(
                table_id, envelope_seats, actual_seats))
        expected_scores = [int(item) for item in outcome.get("scores_by_seat") or []]
        actual_scores = [int(item) for item in row.scores_by_seat or []]
        if expected_scores != actual_scores:
            problems.append("场次 {0} 的分数不一致：记录 {1}，重演输入 {2}".format(
                table_id, expected_scores, actual_scores))
        if str(outcome.get("status")) != str(row.status):
            problems.append("场次 {0} 的状态不一致：记录 {1}，重演输入 {2}".format(
                table_id, outcome.get("status"), row.status))
    for table_id in sorted(set(str(item) for item in rows) - set(expected)):
        problems.append("重演输入多出运行记录之外的场次 {0}".format(table_id))
    return problems


def _standings_signature(standings: Sequence[Mapping[str, Any]]) -> List[Tuple[Any, ...]]:
    return [tuple(row.get(field) for field in REPLAY_STANDING_FIELDS) for row in standings]


def compare_runs(expected: Mapping[str, Any], recomputed: Mapping[str, Any]) -> List[str]:
    """把重算出来的编排记录与运行记录逐字段对账（身份、名次、晋级、分组、加赛、边界）。"""

    problems: List[str] = []
    # 先把**整张计划**比一遍：permutation / initial_dealer / batch_index / match_id /
    # pair_id / tables_in_stage … 这些字段只要进不了 EnumList 就会永远不被发现（复审：31 处盲点）。
    problems.extend(compare_plans(expected, recomputed))
    for key in ("contract_sha256", "root_set_id", "panel_id"):
        if expected.get(key) != recomputed.get(key):
            problems.append("{0} 不一致：记录 {1}，重算 {2}".format(
                key, expected.get(key), recomputed.get(key)))
    expected_stages = list(expected.get("stages") or [])
    recomputed_stages = list(recomputed.get("stages") or [])
    if len(expected_stages) != len(recomputed_stages):
        problems.append("阶段数不一致：记录 {0}，重算 {1}".format(
            len(expected_stages), len(recomputed_stages)))
    for index, (want, got) in enumerate(zip(expected_stages, recomputed_stages), start=1):
        if (want.get("name"), want.get("kind")) != (got.get("name"), got.get("kind")):
            problems.append("阶段 {0} 的名称/类型不一致".format(index))
        if _standings_signature(want.get("standings") or []) != _standings_signature(
                got.get("standings") or []):
            problems.append("阶段 {0} 的名次表与记录不一致".format(index))
        want_advance = want.get("advance") or {}
        got_advance = got.get("advance") or {}
        for field in REPLAY_ADVANCE_FIELDS:
            if want_advance.get(field) != got_advance.get(field):
                problems.append("阶段 {0} 晋级字段 {1} 不一致：记录 {2}，重算 {3}".format(
                    index, field, want_advance.get(field), got_advance.get(field)))
        if bool(want.get("score_reset")) is not True:
            problems.append("阶段 {0} 未声明阶段清零".format(index))
        # 逐场次记账（含名次分规则）：加赛桌恒 0 这条整改就靠它被发现复发。
        if _rows_signature(want.get("seat_accounting"), REPLAY_SEAT_ACCOUNTING_FIELDS) != \
                _rows_signature(got.get("seat_accounting"), REPLAY_SEAT_ACCOUNTING_FIELDS):
            problems.append("阶段 {0} 的逐场次记账（含名次分规则）与记录不一致".format(index))
        # 逐批记账（含轮空名单）：5/6/7 人轮空记账整改靠它被发现复发。
        if _rows_signature(want.get("batch_plan"), REPLAY_BATCH_FIELDS) != \
                _rows_signature(got.get("batch_plan"), REPLAY_BATCH_FIELDS):
            problems.append("阶段 {0} 的逐批记账（含轮空名单）与记录不一致".format(index))
        if (want.get("overtime") or None) != (got.get("overtime") or None):
            problems.append("阶段 {0} 的加赛记录不一致".format(index))
        if (want.get("byes") or None) != (got.get("byes") or None):
            problems.append("阶段 {0} 的轮空账不一致".format(index))
        want_groups = list(want.get("groups") or [])
        got_groups = list(got.get("groups") or [])
        if [item.get("members") for item in want_groups] != [
                item.get("members") for item in got_groups]:
            problems.append("阶段 {0} 的分组不一致".format(index))
        if [item.get("advanced") for item in want_groups] != [
                item.get("advanced") for item in got_groups]:
            problems.append("阶段 {0} 的组内晋级不一致".format(index))
        for want_group, got_group in zip(want_groups, got_groups):
            # 组内名次表与组内边界标记：组内 boundary_unresolved 硬编码那条整改靠它被发现复发。
            if _standings_signature(want_group.get("standings") or []) != _standings_signature(
                    got_group.get("standings") or []):
                problems.append("阶段 {0} 第 {1} 组的名次表不一致".format(
                    index, want_group.get("group_index")))
            if bool(want_group.get("boundary_unresolved")) != bool(
                    got_group.get("boundary_unresolved")):
                problems.append("阶段 {0} 第 {1} 组的组内晋级边界标记不一致".format(
                    index, want_group.get("group_index")))
    if _rows_signature(expected.get("plan_verification"), REPLAY_PLAN_FIELDS) != _rows_signature(
            recomputed.get("plan_verification"), REPLAY_PLAN_FIELDS):
        problems.append("计划核验结果不一致（ok / 计划场次 / 观测场次 / 状态分布 / problems）")
    if list(expected.get("boundaries") or []) != list(recomputed.get("boundaries") or []):
        problems.append("未解决边界记录不一致")
    return problems


def _participants_from_run(path: Path) -> List[Dict[str, str]]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return [{"participant_id": str(item["participant_id"]),
             "policy_name": str(item["policy_name"])} for item in payload["participants"]]


def cmd_replay(args) -> int:
    """重演对账：读**运行记录**当期望、读 **tables.jsonl** 当输入，两侧都核，再复算名次。

    复审 #18 指出初版只换了 runner 重跑同一 build_run：期望值和输入来自同一份数据，
    「篡改未比对字段后 problems=[]」——那就等于什么也没证明。现在：
    ① 先逐场次比对「记录的计划与结果」vs「重演输入行」（seed / 座位 / 分数 / 状态）；
    ② 再用重演输入复算整条编排；
    ③ 最后把复算结果与记录逐阶段逐字段比对（身份、名次表、晋级、分组、加赛、边界）。
    任一侧被改动都会进 problems 并以退出码 2 结束。
    """

    contract = _contract_from_args(args)
    expected = json.loads(Path(args.expect_run).read_text(encoding="utf-8"))
    participants = _participants_from_run(Path(args.expect_run))
    rows = read_tables_jsonl(Path(args.tables))
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    problems = compare_expected_tables(rows, expected)
    run: Optional[Dict[str, Any]] = None
    if not problems:
        try:
            run = build_run(contract=contract, participants=participants,
                            runner=recorded_runner(rows), mode="replay")
        except StageFailed as error:
            # 重演缺场次/结果不符一律判失败并落盘理由：**不凭空值补全、不静默降级**。
            problems.append(str(error))
        if run is not None:
            problems.extend(compare_runs(expected, run))
    verdict = {
        "ok": not problems,
        "problems": problems,
        "replayed_tables": (0 if run is None else len(run["tables"])),
        "compared_table_fields": list(REPLAY_TABLE_FIELDS),
        "compared_standing_fields": list(REPLAY_STANDING_FIELDS),
        "compared_advance_fields": list(REPLAY_ADVANCE_FIELDS),
        "compared_seat_accounting_fields": list(REPLAY_SEAT_ACCOUNTING_FIELDS),
        "compared_batch_fields": list(REPLAY_BATCH_FIELDS),
        "compared_plan_verification_fields": list(REPLAY_PLAN_FIELDS),
        # 逐场次计划的**全部字段**（运行时从记录里取，字段增减不需要维护列表）。
        "compared_table_plan_fields": plan_field_inventory(expected),
        "compared_table_envelope_fields": ["seed", "scenario_id", "stage_no", "group_index",
                                           "seat_participants"],
        # 明确写出"没有比对什么、为什么"，避免把盲点留成空白。
        "not_compared_fields": dict(REPLAY_NOT_COMPARED_FIELDS),
        "compared_group_fields": ["members", "advanced", "standings", "boundary_unresolved"],
        "compared_run_fields": ["contract_sha256", "root_set_id", "panel_id", "stages",
                                "boundaries"],
        "expect_run": str(args.expect_run),
    }
    write_json(out_dir / "replay.json", {"schema": RUN_SCHEMA, "verdict": verdict, "run": run})
    print(json.dumps({"ok": verdict["ok"], "problems": verdict["problems"],
                      "tables": verdict["replayed_tables"]}, ensure_ascii=False))
    return 0 if verdict["ok"] else 2


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="坐隐 3.0／3.4：阶段合同、编排验证，以及受准入约束的候选阶段比较")
    sub = parser.add_subparsers(dest="command", required=True)

    def add_contract_args(target: argparse.ArgumentParser) -> None:
        target.add_argument("--contract-file", default=None, help="已冻结的合同 JSON（优先）")
        target.add_argument("--ruleset-version", default="hangma-mvp-v10-public-counts")
        target.add_argument("--base-score", type=int, default=1)
        target.add_argument("--you-cai-bi-kao", choices=("true", "false"), default="false")
        target.add_argument("--rounds-per-game", type=int, default=8)
        target.add_argument("--clock-mode", choices=("logical", "real"), default="logical")
        target.add_argument("--panel-seed", type=int, default=20260915)
        target.add_argument("--panel-policy", default="weighted_heuristic_v2",
                            choices=PANEL_POLICY_NAMES)
        target.add_argument("--tables-per-batch", type=int, default=2)
        target.add_argument("--batches", type=int, default=2)
        target.add_argument("--tables-per-group", type=int, default=2)
        target.add_argument("--tables-in-final", type=int, default=1)
        target.add_argument("--max-overtime", type=int, default=3)
        target.add_argument("--table-timeout-sec", type=float, default=300.0)
        target.add_argument("--step-limit", type=int, default=100000)
        target.add_argument("--frozen-at", default=None,
                            help="合同冻结日期 YYYY-MM-DD（必填；不得默认取当天）")

    contract = sub.add_parser("contract", help="生成并核验阶段合同")
    add_contract_args(contract)
    contract.add_argument("--out", default=None)
    contract.set_defaults(func=cmd_contract)

    check = sub.add_parser("check", help="只核验合同")
    add_contract_args(check)
    check.set_defaults(func=cmd_check)

    group_eval = sub.add_parser(
        "group-eval", help="group_advance_v1 目标求值：账本 → 焦点 U 识别区间/"
                           "全员区间表/辅助指标（不跑桌赛）")
    group_eval.add_argument("--contract-file", required=True,
                            help="已冻结的 group_only 目标合同 JSON")
    group_eval.add_argument("--ledger", required=True,
                            help="阶段账本 JSON（LedgerRow 形状数组：participant_id/"
                                 "total_score/place_points/god_count 可空）")
    group_eval.add_argument("--focal", required=True, help="焦点参赛者 id")
    group_eval.set_defaults(func=cmd_group_eval)

    run = sub.add_parser("run", help="真实小规模阶段编排（受监管子进程）")
    add_contract_args(run)
    run.add_argument("--out", required=True)
    run.add_argument("--participants", type=int, default=9)
    run.add_argument("--participant-prefix", default="p")
    run.set_defaults(func=cmd_run)

    fixture = sub.add_parser("fixture", help="构造夹具：只验证编排语义")
    add_contract_args(fixture)
    fixture.add_argument("--fixture", required=True)
    fixture.add_argument("--out", required=True)
    fixture.add_argument("--participants", type=int, default=9)
    fixture.add_argument("--participant-prefix", default="p")
    fixture.set_defaults(func=cmd_fixture)

    replay = sub.add_parser("replay", help="重演对账：运行记录 vs tables.jsonl，两侧都核")
    add_contract_args(replay)
    replay.add_argument("--tables", required=True, help="重演输入（tables.jsonl）")
    replay.add_argument("--expect-run", required=True, help="期望运行记录（run.json）")
    replay.add_argument("--out", required=True)
    replay.set_defaults(func=cmd_replay)

    compare = sub.add_parser("compare", help="3.4 阶段比较：候选 vs 基线（按场景种子配对）")
    add_contract_args(compare)
    compare.add_argument("--candidate", required=True, help="已注册且已准入的候选名")
    compare.add_argument("--weights", default="{}", help="候选声明参数 JSON（adj.* 前缀）")
    compare.add_argument("--gate-record", required=True, help="该候选的**准入记录**文件")
    compare.add_argument("--admission-corpus", required=True, help="准入语料路径（逐字节比对）")
    compare.add_argument("--arm-id", default=None)
    compare.add_argument("--family", default=None)
    compare.add_argument("--scenarios", type=int, default=5, help="独立单位：场景种子个数")
    compare.add_argument("--seed-base", type=int, default=20260916)
    compare.add_argument("--participants", type=int, default=9)
    compare.add_argument("--participant-prefix", default="p")
    compare.add_argument("--focal", default=None, help="焦点参赛者 id（缺省取第一个）")
    compare.add_argument("--budget-tables", type=int, required=True, help="本次比较的桌数上限")
    compare.add_argument("--budget-wall-sec", type=float, default=None,
                         help="墙钟上限（秒）；缺省按场景数 × 2 臂 × 桌数上界 × 单桌上限推导")
    compare.add_argument("--out", required=True)
    compare.add_argument("--force", action="store_true", help="允许覆盖已有 compare.json")
    compare.set_defaults(func=cmd_compare)

    worker = sub.add_parser("table-worker", help="内部：在受监管子进程里跑一个场次")
    worker.add_argument("--plan", required=True)
    worker.add_argument("--out", required=True)
    worker.set_defaults(func=lambda args: table_worker(Path(args.plan), Path(args.out)))
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
